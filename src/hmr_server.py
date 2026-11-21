"""Combined hot-module-reload dev server for pasta.

Runs one uvicorn server and one file watcher that serve both surfaces of `src.server`
with in-process hot reload - no process respawn:

* FastMCP tools  -> a stable proxy (`base_app`). The reloaded `src.server.mcp`
  is mounted under it; on a source change the old mount is swapped for the reloaded
  one and connected MCP client sessions are sent tools/list_changed, so sessions
  SURVIVE the reload instead of dropping.

* FastAPI HTML   -> a dispatcher that forwards every request to the freshly
  reloaded `src.server.app`. On a source change connected browsers are told to
  reload over the existing /ws/reloader WebSocket (`ws_reloader.reload`).

This merges the two reference patterns - uvicorn-hmr (serve a reloaded ASGI app +
browser refresh) and mcp-hmr (stable proxy + session-preserving tool swap) - into
one module, started from main.py.

On a settled batch of source changes the whole src package is re-imported from disk,
all or nothing. A failed import keeps the last good build loaded, and both surfaces
refuse until a reload succeeds.

Two brittleness notes (dev-only tool):
* It reaches into a few private fastmcp/mcp internals (`base_app.providers` /
  `FastMCPProvider` for mount/unmount, the constructor of `mcp.server.connection.Connection`
  for connection capture). These changed across fastmcp versions; revisit on a fastmcp upgrade.
* `src.hmr_server` and `src.live_sockets` are never re-imported, so an edit to
  either needs a restart.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import traceback
from asyncio import Event, Lock, TaskGroup
from collections.abc import Callable, Mapping, Set
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any
from weakref import WeakSet

import uvicorn
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans
from mcp.server.connection import Connection
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send
from watchfiles import awatch  # pyright: ignore[reportUnknownVariableType]

from .live_sockets import set_reload_failure, ws_reloader

# The module a reload imports through; it pulls in the rest of the package.
TARGET_MODULE = "src.server"

# Watch the src package; SCOPE below says which of its modules a reload leaves loaded.
_PACKAGE_DIR = str(Path(__file__).resolve().parent)

# Reload notifications go through uvicorn's status logger so they land in the dev server
# console next to uvicorn's own output. A standalone module logger at INFO would be
# dropped: uvicorn configures only its own loggers, not the root logger.
logger = logging.getLogger("uvicorn.error")

# uvicorn hands websockets this same logger, and websockets logs every connection opening and
# closing on it at INFO. uvicorn's own line for the accept already names the client and path.
WEBSOCKET_LIFECYCLE_LINES = ("connection open", "connection closed")


def shows_on_console(record: logging.LogRecord) -> bool:
    """A filter for the dev console: False for websockets' per-connection lifecycle lines."""
    return record.msg not in WEBSOCKET_LIFECYCLE_LINES


# --- What a reload re-imports -----------------------------------------------------------
QUIET_WINDOW_MS = 300  # watchfiles awatch step: the quiet time before a batch of changes is reloaded


@dataclass(frozen=True)
class ReloadScope:
    """The package a reload re-imports, the module it imports through, and what it leaves loaded."""
    package: str
    entry: str
    always_kept: frozenset[str]
    kept_unless_changed: frozenset[str]


# State that has to outlive a reload is kept: always for the reloader and the state it shares with
# the server, and, for a module that holds state but imports nothing from the package, until its own
# file changes.
SCOPE = ReloadScope(
    package="src",
    entry=TARGET_MODULE,
    always_kept=frozenset({"src.hmr_server", "src.live_sockets"}),
    kept_unless_changed=frozenset({"src.event_cache", "src._hmr_debug"}),
)


def _in_package(name: str, package: str) -> bool:
    return name == package or name.startswith(f"{package}.")


def modules_to_drop(scope: ReloadScope, loaded: Mapping[str, str | None],
                    changed: Set[str]) -> list[str]:
    """The loaded modules a reload re-imports, sorted by name.

    `loaded` maps module names to their normalised file path, None when a module has no file, and
    `changed` holds the batch's normalised paths."""
    return sorted(
        name for name, path in loaded.items()
        if _in_package(name, scope.package)
        and name not in scope.always_kept
        and not (name in scope.kept_unless_changed and path not in changed))


def needs_reimport(changed: Set[str]) -> bool:
    """Whether a batch touches Python source, which is all a re-import reads."""
    return any(path.endswith(".py") for path in changed)


def reload_failure_summary(error: BaseException) -> str:
    """The exception's own lines without its traceback."""
    return "".join(traceback.format_exception_only(error)).strip()


def _normalise(path: str) -> str:
    """Make a watcher path and a module's __file__ comparable, case included on Windows."""
    return os.path.normcase(str(Path(path).resolve()))


def reimport(scope: ReloadScope, changed: Set[str]) -> Exception | None:
    """Re-import the scope's entry from disk, all or nothing.

    Every droppable module leaves sys.modules first, so the import runs each one again from what is
    on disk now, in the order the imports themselves ask for. When it raises, the modules loaded
    before are put back exactly as they were and the error is returned instead."""
    snapshot = {name: module for name, module in sys.modules.items()
                if _in_package(name, scope.package)}
    loaded = {name: _normalise(file) if (file := getattr(module, "__file__", None)) else None
              for name, module in snapshot.items()}
    for name in modules_to_drop(scope, loaded, changed):
        del sys.modules[name]
    # Bytecode is checked against the source's mtime in whole seconds and its size, so a same-size
    # rewrite within a second of the last compile would otherwise load the old code.
    for path in changed:
        if path.endswith(".py"):
            Path(importlib.util.cache_from_source(path)).unlink(missing_ok=True)
    importlib.invalidate_caches()
    try:
        _ = import_module(scope.entry)
    except Exception as error:
        for name in [name for name in sys.modules if _in_package(name, scope.package)]:
            del sys.modules[name]
        sys.modules.update(snapshot)
        return error
    return None


# --- Reload failure reporting ----------------------------------------------------------
def _report_reload_failure(error: BaseException) -> None:
    """Say on the dev console what a failed reload cost, and hand its traceback to sys.excepthook,
    which tees it to the reload log."""
    logger.error(
        "[HMR] reload FAILED - the edit did not take; the build loaded before it stays loaded " +
        "and both surfaces refuse until a reload succeeds:\n%s", reload_failure_summary(error))
    sys.excepthook(type(error), error, error.__traceback__)


# --- MCP connection capture ------------------------------------------------------------
# So we can push tools/list_changed to live clients on reload, every Connection the SDK builds is
# recorded. A Connection is the per-client object that outlives its requests; one with no
# standalone stream has nowhere to deliver a notification, and the SDK drops it there.
_live_connections: WeakSet[Connection] = WeakSet()


def _capture_connections() -> Callable[[], None]:
    """Record every Connection the SDK builds from now on; return the function that stops it."""
    original_init = Connection.__init__

    def capture_init(self: Connection, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _live_connections.add(self)

    Connection.__init__ = capture_init

    def restore() -> None:
        Connection.__init__ = original_init

    return restore


async def _notify_list_changed() -> None:
    """Tell every live client connection its tool, resource and prompt lists may have changed."""
    for connection in list(_live_connections):
        for send in (
            connection.send_tool_list_changed,
            connection.send_resource_list_changed,
            connection.send_prompt_list_changed,
        ):
            with suppress(Exception):
                await send()


# Mounting forwards live calls to `mcp`; each mount appends one FastMCPProvider to
# base_app.providers, an internal we pop to unmount on the next reload.
def _mount(base_app: FastMCP, mcp: FastMCP) -> Callable[[], None]:
    """Mount `mcp` under the proxy; return the function that unmounts it again."""
    base_app.mount(mcp)
    mounted_provider = base_app.providers[-1]

    def unmount() -> None:
        if mounted_provider in base_app.providers:
            base_app.providers.remove(mounted_provider)

    return unmount


def build_dev_app() -> Starlette:
    """Build the stable outer ASGI app: /pasta/mcp -> proxy, everything else -> reloaded FastAPI."""

    # The proxy is built ONCE and never rebuilt; only what is mounted under it swaps.
    base_app: FastMCP = FastMCP(name="pasta-hmr-proxy")

    # The src.server module serving now; a reload that imports cleanly replaces it.
    serving: ModuleType | None = None

    # Only one mount is live at a time; a reload tears the old one down before mounting new.
    mount_lock = Lock()
    task_group: TaskGroup | None = None
    stop_event: Event | None = None
    finish_event: Event | None = None
    watch_stop = Event()

    async def serve_mcp(mcp: FastMCP, stop: Event, finish: Event):
        async with mount_lock:
            unmount = _mount(base_app, mcp)
            try:
                await _notify_list_changed()  # tell live clients the tool set may have changed
                _ = await stop.wait()
            finally:
                unmount()
                finish.set()

    async def swap_in(server: ModuleType) -> None:
        """Serve `server`: mount its tools in place of the previous ones and route to its app."""
        nonlocal serving, stop_event, finish_event
        # A live previous mount means this is a reload, not the initial mount.
        is_reload = stop_event is not None and finish_event is not None
        if stop_event is not None and finish_event is not None:
            stop_event.set()
            _ = await finish_event.wait()
        if is_reload:
            logger.info("[HMR] FastMCP server reloaded (src.server.mcp)")
        serving = server
        stop_event, finish_event = Event(), Event()
        assert task_group is not None
        _ = task_group.create_task(serve_mcp(server.mcp, stop_event, finish_event))

    async def reload(changed: frozenset[str]) -> None:
        """Re-import the package and serve the result, or keep the last good build and refuse."""
        assert serving is not None
        previous = serving
        error = reimport(SCOPE, changed)
        if error is not None:
            set_reload_failure(reload_failure_summary(error))
            _report_reload_failure(error)
            return
        server = sys.modules[SCOPE.entry]
        await previous.cleanup.stop_scheduler()
        await swap_in(server)
        server.cleanup.start_scheduler(server.STORE)
        set_reload_failure(None)

    async def watch() -> None:
        # Browsers are refreshed after every batch, a failed reload included: what a tab should land
        # on then is the refusal, and since that page keeps the socket it is also how the tab recovers.
        async for changes in awatch(_PACKAGE_DIR, step=QUIET_WINDOW_MS, stop_event=watch_stop):
            changed = frozenset(_normalise(path) for _, path in changes)
            if needs_reimport(changed):
                try:
                    await reload(changed)
                except Exception as error:  # a failed swap must not end the watcher
                    set_reload_failure(reload_failure_summary(error))
                    _report_reload_failure(error)
            await ws_reloader.reload()

    # /pasta/mcp is served by the stable proxy's ASGI app (built once). Its session manager is
    # started by mcp_asgi.lifespan; the reloader lifespan drives module reloads + mounts.
    mcp_asgi = base_app.http_app(path="/mcp")

    @asynccontextmanager
    async def reloader_lifespan(_app: Starlette):
        nonlocal task_group
        restore_connection_init = _capture_connections()
        async with TaskGroup() as tg:
            task_group = tg
            # A cold start that cannot import raises out of here, before uvicorn binds the port.
            server = import_module(SCOPE.entry)
            await swap_in(server)
            server.cleanup.start_scheduler(server.STORE)
            watch_task = tg.create_task(watch())
            try:
                yield
            finally:
                watch_stop.set()
                if serving is not None:
                    await serving.cleanup.stop_scheduler()
                if stop_event is not None:
                    stop_event.set()
                _ = watch_task.cancel()
                restore_connection_init()

    # The FastAPI app object last served; a reload swaps in a new one (see below).
    last_fastapi_app: object = None

    async def fastapi_dispatch(scope: Scope, receive: Receive, send: Send):
        # Forward every non-/pasta/mcp request (incl. the /ws/reloader websocket) to the app of the
        # build serving now.
        nonlocal last_fastapi_app
        assert serving is not None
        fastapi_app = serving.app
        # src.server re-executing on reload rebuilds `app` as a new object; a changed
        # identity is the reload signal. Log the first request that observes each reload
        # (the initial startup request is skipped since there is nothing to compare to).
        if last_fastapi_app is not None and fastapi_app is not last_fastapi_app:
            logger.info("[HMR] FastAPI app reloaded (src.server.app)")
        last_fastapi_app = fastapi_app
        await fastapi_app(scope, receive, send)

    return Starlette(
        routes=[Mount("/pasta", app=mcp_asgi), Mount("/", app=fastapi_dispatch)],
        lifespan=combine_lifespans(mcp_asgi.lifespan, reloader_lifespan),
    )


def run_dev_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Serve the combined HMR dev app. Dev-only; blocks until interrupted."""
    logger.addFilter(shows_on_console)
    uvicorn.run(build_dev_app(), host=host, port=port, timeout_graceful_shutdown=1)
