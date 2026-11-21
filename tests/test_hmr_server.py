"""Unit tests for the dev server (src.hmr_server): what a reload re-imports and how it rolls back,
reload-failure reporting, what the dev console shows of a websocket, and the framework internals the
reload swap relies on.

The watch loop as a whole needs a live uvicorn process, a file watcher and a real edit, so it is
exercised by hand against the running dev server rather than in this suite. What is pinned here is
the re-import itself, against a throwaway package, and what regressed silently: a failed reload
that left no usable trace in the console, and the fastmcp/mcp internals behind the mount swap and
the list_changed notification, which a framework upgrade can move without any error.
"""

import asyncio
import logging
import os
import sys
import uuid
from importlib import import_module
from importlib.util import cache_from_source
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from mcp.server.connection import Connection
from websockets.datastructures import Headers
from websockets.frames import Close
from websockets.http11 import Request
from websockets.server import ServerProtocol

import src.hmr_server as hmr_server
from src.live_sockets import reload_failure, set_reload_failure
from src.hmr_server import (ReloadScope, _build_proxy, _mount, _normalise, _report_reload_failure,
                            modules_to_drop, needs_reimport, reimport, reload_failure_summary)


def test_a_mounted_server_is_served_through_the_proxy_until_unmounted():
    # The reload swap leans on a fastmcp internal: mount() appends one provider to the proxy's
    # `providers`, and removing that provider unmounts it. An upgrade that moves this fails here
    # rather than leaving the dev server serving a stale or doubled tool set.
    proxy, child = FastMCP("proxy"), FastMCP("child")

    @child.tool
    def ping() -> str:
        return "pong"

    async def tool_names() -> set[str]:
        return {tool.name for tool in await proxy.list_tools()}

    unmount = _mount(proxy, child)
    assert "ping" in asyncio.run(tool_names())
    unmount()
    assert "ping" not in asyncio.run(tool_names())


# The proxy lists the mounted tools but runs every call on the served server itself, so a failure is
# logged once, by the server that ran it. An upgrade that stops a middleware answering a call on its
# own shows up here as a line logged twice.

def _served() -> FastMCP:
    served = FastMCP("served")

    @served.tool
    def echo(n: int) -> int:
        return n

    @served.tool
    def boom() -> int:
        raise KeyError("missing")

    return served


def _proxy_for(served: FastMCP) -> FastMCP:
    proxy = _build_proxy(lambda: served)
    _ = _mount(proxy, served)
    return proxy


def _call(server: FastMCP, name: str, args: dict[str, object]) -> CallToolResult:
    async def run() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool(name, args, raise_on_error=False)

    return asyncio.run(run())


def test_a_call_through_the_proxy_returns_the_served_servers_result():
    result = _call(_proxy_for(_served()), "echo", {"n": 3})
    assert not result.is_error and result.data == 3


def test_an_exception_inside_a_tool_is_logged_once_through_the_proxy(fastmcp_lines):
    result = _call(_proxy_for(_served()), "boom", {})
    assert result.is_error
    assert [block.text for block in result.content] == ["Error calling tool 'boom': 'missing'"]
    assert fastmcp_lines == ["Error calling tool 'boom'"]


def test_invalid_arguments_are_logged_once_through_the_proxy(fastmcp_lines):
    served = _served()
    direct = _call(served, "echo", {"n": "not a number"})
    fastmcp_lines.clear()
    proxied = _call(_proxy_for(served), "echo", {"n": "not a number"})
    assert proxied.is_error and proxied.content == direct.content
    assert fastmcp_lines == [
        "Invalid arguments for tool 'echo': {'error_count': 1, 'error_types': ['int_parsing']}"]


def test_an_unknown_tool_through_the_proxy_is_reported_as_unknown():
    result = _call(_proxy_for(_served()), "nope", {})
    assert result.is_error
    assert [block.text for block in result.content] == ["Unknown tool: 'nope'"]


def test_the_proxy_runs_each_call_on_the_server_served_when_it_arrives():
    first, second = _served(), _served()

    @second.tool
    def which() -> str:
        return "second"

    current = [first]
    proxy = _build_proxy(lambda: current[0])
    _ = _mount(proxy, first)
    current[0] = second
    assert _call(proxy, "which", {}).data == "second"


class _RecordingOutbound:
    """Stands in for a client's standalone stream, recording each notification sent down it."""

    def __init__(self):
        self.sent: list[str] = []

    async def notify(self, method, params, opts=None):
        self.sent.append(method)

    async def send_raw_request(self, method, params, opts=None):
        raise AssertionError("a reload sends notifications, never requests")


class _BrokenOutbound(_RecordingOutbound):
    async def notify(self, method, params, opts=None):
        raise RuntimeError("stream gone")


@pytest.fixture
def capturing():
    restore = hmr_server._capture_connections()
    try:
        yield
    finally:
        restore()
        hmr_server._live_connections.clear()


def test_a_connection_built_while_capturing_is_recorded(capturing):
    connection = Connection.for_loop(_RecordingOutbound())
    assert connection in hmr_server._live_connections


def test_a_connection_built_after_capture_stops_is_not_recorded():
    hmr_server._capture_connections()()
    connection = Connection.for_loop(_RecordingOutbound())
    assert connection not in hmr_server._live_connections


def test_a_reload_tells_each_live_connection_every_list_may_have_changed(capturing):
    outbound = _RecordingOutbound()
    connection = Connection.for_loop(outbound)  # held, so the weak set keeps it
    asyncio.run(hmr_server._notify_list_changed())
    assert connection in hmr_server._live_connections
    assert outbound.sent == ["notifications/tools/list_changed",
                             "notifications/resources/list_changed",
                             "notifications/prompts/list_changed"]


def test_one_broken_connection_does_not_stop_the_others_hearing_of_a_reload(capturing):
    # A client that vanished mid-reload must not cost every other client its refresh.
    broken, healthy = _BrokenOutbound(), _RecordingOutbound()
    connections = [Connection.for_loop(broken), Connection.for_loop(healthy)]
    asyncio.run(hmr_server._notify_list_changed())
    assert len(connections) == 2
    assert healthy.sent == ["notifications/tools/list_changed",
                            "notifications/resources/list_changed",
                            "notifications/prompts/list_changed"]


# --- Which modules a full reload re-imports -------------------------------------------
# A made-up scope, so these do not depend on src's real module list.
_SCOPE = ReloadScope("pkg", "pkg.entry", frozenset({"pkg.reloader"}), frozenset({"pkg.cache"}))
_LOADED = {"pkg": "/r/pkg/__init__.py", "pkg.entry": "/r/pkg/entry.py",
           "pkg.reloader": "/r/pkg/reloader.py", "pkg.cache": "/r/pkg/cache.py",
           "pkgx": "/r/pkgx.py", "json": None}


def test_a_reload_drops_every_package_module_but_the_kept_ones():
    assert modules_to_drop(_SCOPE, _LOADED, frozenset()) == ["pkg", "pkg.entry"]


def test_a_module_kept_unless_changed_is_dropped_once_its_own_file_changed():
    changed = frozenset({"/r/pkg/cache.py"})
    assert modules_to_drop(_SCOPE, _LOADED, changed) == ["pkg", "pkg.cache", "pkg.entry"]


def test_an_always_kept_module_stays_even_when_its_file_changed():
    assert "pkg.reloader" not in modules_to_drop(_SCOPE, _LOADED, frozenset({"/r/pkg/reloader.py"}))


def test_a_module_outside_the_package_is_never_dropped():
    # pkgx shares the prefix but not the package.
    assert "pkgx" not in modules_to_drop(_SCOPE, _LOADED, frozenset({"/r/pkgx.py"}))


def test_only_a_batch_with_python_source_reimports():
    assert needs_reimport(frozenset({"/r/pkg/templates/page.html", "/r/pkg/entry.py"}))
    assert not needs_reimport(frozenset({"/r/pkg/static/styles.css"}))
    assert not needs_reimport(frozenset())


def test_the_failure_summary_is_the_exception_without_its_traceback():
    try:
        raise ImportError("cannot import name 'NEW' from 'pkg.a'")
    except ImportError as error:
        summary = reload_failure_summary(error)
    assert summary == "ImportError: cannot import name 'NEW' from 'pkg.a'"


def test_the_failure_summary_keeps_a_multi_line_message_whole():
    error = ValueError("Invalid page-type declarations:\n- bug-report: bad setter")
    assert reload_failure_summary(error) == (
        "ValueError: Invalid page-type declarations:\n- bug-report: bad setter")


def test_a_recorded_reload_failure_holds_until_cleared():
    assert reload_failure() is None
    set_reload_failure("ImportError: boom")
    try:
        assert reload_failure() == "ImportError: boom"
    finally:
        set_reload_failure(None)
    assert reload_failure() is None


@pytest.fixture
def report(caplog, monkeypatch):
    """Report a reload failure, capturing the console text and what reached sys.excepthook."""
    hooked: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda _type, value, _tb: hooked.append(value))

    def _run(error: BaseException):
        with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
            _report_reload_failure(error)
        return caplog.text, hooked
    return _run


def test_a_failed_reload_reaches_the_console_as_an_error(report):
    text, _ = report(ImportError("cannot import name 'NEW'"))
    assert "ERROR" in text
    assert "[HMR]" in text


def test_a_failed_reload_report_names_its_error(report):
    text, _ = report(ValueError("Invalid page-type declarations:\n- bug-report: bad setter"))
    assert "Invalid page-type declarations" in text
    assert "bad setter" in text


def test_a_failed_reload_report_states_what_it_cost(report):
    # The error alone never said what it cost: the edit did not take, and both surfaces now refuse.
    text, _ = report(ValueError("boom"))
    assert "did not take" in text
    assert "refuse" in text


def test_the_traceback_is_handed_to_the_excepthook_that_tees_the_reload_log(report):
    error = ValueError("boom")
    _, hooked = report(error)
    assert hooked == [error]


# --- What the dev console shows of a websocket -------------------------------------------
# uvicorn hands websockets its own status logger, so the library's lines reach the dev console.
# They are driven through the library's real handshake, so a line reworded upstream fails here
# rather than quietly coming back to the console.
@pytest.fixture
def console(caplog, monkeypatch):
    """The dev console's INFO lines, with its logger set up as run_dev_server leaves it."""
    monkeypatch.setattr(hmr_server.logger, "filters", [])
    monkeypatch.setattr(hmr_server, "build_dev_app", lambda: None)
    monkeypatch.setattr(hmr_server, "uvicorn", SimpleNamespace(run=lambda *_args, **_kwargs: None))
    hmr_server.run_dev_server()
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        yield caplog


def _open_websocket() -> ServerProtocol:
    server = ServerProtocol(logger=logging.getLogger("uvicorn.error"))
    request = Request("/ws/reloader", Headers({
        "Host": "localhost", "Upgrade": "websocket", "Connection": "Upgrade",
        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Version": "13"}))
    server.send_response(server.accept(request))
    return server


def _close_websocket(server: ServerProtocol) -> None:
    server.send_close(1001)
    # The client's answering close frame, masked as every client frame must be.
    payload = Close(1001, "").serialize()
    server.receive_data(bytes([0x88, 0x80 | len(payload)]) + b"\x00\x00\x00\x00" + payload)
    server.receive_eof()


def test_an_accepted_websocket_logs_no_connection_open_line(console):
    _open_websocket()
    assert "connection open" not in console.text


def test_a_closed_websocket_logs_no_connection_closed_line(console):
    _close_websocket(_open_websocket())
    assert "connection closed" not in console.text


def test_the_console_still_shows_uvicorns_accept_line_and_the_reload_lines(console):
    hmr_server.logger.info('%s - "WebSocket %s" [accepted]', "127.0.0.1:58681", "/ws/reloader")
    hmr_server.logger.info("[HMR] FastAPI app reloaded (src.server.app)")
    assert '"WebSocket /ws/reloader" [accepted]' in console.text
    assert "[HMR] FastAPI app reloaded" in console.text


# --- Re-importing a package, all or nothing ----------------------------------------------
# Driven against a throwaway package, never against src. The shapes are the ones the HMR bug
# logged: an importer and the exporter of a new name changed together, and a class gaining a field
# that an unchanged module instantiates and a changed module reads.
@pytest.fixture
def package(tmp_path, monkeypatch):
    """A throwaway package on sys.path. write() rewrites one of its files and returns the path as a
    reload batch names it."""
    name = f"rpkg_{uuid.uuid4().hex[:8]}"
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))

    def write(relative: str, source: str) -> str:
        (root / relative).write_text(source)
        return _normalise(str(root / relative))

    def scope(always=(), unless_changed=()) -> ReloadScope:
        return ReloadScope(name, f"{name}.entry", frozenset(f"{name}.{m}" for m in always),
                           frozenset(f"{name}.{m}" for m in unless_changed))

    def modules() -> dict:
        return {n: m for n, m in sys.modules.items() if n == name or n.startswith(f"{name}.")}

    yield SimpleNamespace(name=name, root=root, write=write, scope=scope, modules=modules)
    for module_name in list(modules()):
        del sys.modules[module_name]


def test_an_importer_and_the_exporter_of_a_new_name_reload_together(package):
    package.write("a.py", "OLD = 1\n")
    package.write("entry.py", "from .a import OLD\n")
    import_module(f"{package.name}.entry")
    changed = {package.write("entry.py", "from .a import NEW\n"),
               package.write("a.py", "OLD = 1\nNEW = 2\n")}
    assert reimport(package.scope(), changed) is None
    assert sys.modules[f"{package.name}.entry"].NEW == 2


def test_a_new_field_read_through_an_unchanged_module_reloads_together(package):
    # The FieldSpec.fixed shape: fields gains a field, unchanged kinds builds an instance of it,
    # validation's new code reads the field, and unchanged entry runs validation on the instance.
    package.write("fields.py", "class F:\n    def __init__(self):\n        self.kind = 'k'\n")
    package.write("kinds.py", "from .fields import F\nINSTANCE = F()\n")
    package.write("validation.py", "def check(f):\n    return f.kind\n")
    package.write("entry.py",
                  "from .kinds import INSTANCE\nfrom .validation import check\nRESULT = check(INSTANCE)\n")
    import_module(f"{package.name}.entry")
    changed = {package.write("validation.py", "def check(f):\n    return f.fixed\n"),
               package.write("fields.py",
                             "class F:\n    def __init__(self):\n        self.kind = 'k'\n"
                             "        self.fixed = 'yes'\n")}
    assert reimport(package.scope(), changed) is None
    assert sys.modules[f"{package.name}.entry"].RESULT == "yes"


def test_a_failed_reimport_puts_back_the_modules_loaded_before(package):
    package.write("a.py", "OLD = 1\n")
    package.write("entry.py", "from .a import OLD\n")
    import_module(f"{package.name}.entry")
    before = package.modules()
    error = reimport(package.scope(), {package.write("entry.py", "from .a import NEW\n")})
    assert isinstance(error, ImportError)
    after = package.modules()
    assert after.keys() == before.keys()
    assert all(after[name] is before[name] for name in before)


def test_the_batch_after_a_failed_one_brings_the_package_up_to_date(package):
    package.write("a.py", "OLD = 1\n")
    package.write("entry.py", "from .a import OLD\n")
    import_module(f"{package.name}.entry")
    assert reimport(package.scope(), {package.write("entry.py", "from .a import NEW\n")}) is not None
    assert reimport(package.scope(), {package.write("a.py", "NEW = 2\n")}) is None
    assert sys.modules[f"{package.name}.entry"].NEW == 2


def test_an_always_kept_module_is_the_same_object_after_a_reimport(package):
    package.write("state.py", "ITEMS = []\n")
    package.write("entry.py", "from . import state\n")
    import_module(f"{package.name}.entry")
    state = sys.modules[f"{package.name}.state"]
    changed = {package.write("entry.py", "from . import state\nVERSION = 2\n"),
               package.write("state.py", "ITEMS = [1]\n")}
    assert reimport(package.scope(always=["state"]), changed) is None
    assert sys.modules[f"{package.name}.entry"].state is state


def test_a_module_kept_unless_changed_survives_until_its_own_file_changes(package):
    package.write("cache.py", "ITEMS = []\n")
    package.write("entry.py", "from .cache import ITEMS\n")
    import_module(f"{package.name}.entry")
    cache = sys.modules[f"{package.name}.cache"]
    scope = package.scope(unless_changed=["cache"])
    assert reimport(scope, {package.write("entry.py", "from .cache import ITEMS\nV = 2\n")}) is None
    assert sys.modules[f"{package.name}.cache"] is cache
    assert reimport(scope, {package.write("cache.py", "ITEMS = [1]\n")}) is None
    assert sys.modules[f"{package.name}.entry"].ITEMS == [1]


def test_a_same_size_rewrite_in_the_same_second_is_not_served_from_old_bytecode(package):
    package.write("a.py", "X = 1\n")
    package.write("entry.py", "from .a import X\n")
    import_module(f"{package.name}.entry")
    source = package.root / "a.py"
    assert Path(cache_from_source(str(source))).exists()  # the stale bytecode this guards against
    stamp = source.stat().st_mtime
    changed = package.write("a.py", "X = 2\n")
    os.utime(source, (stamp, stamp))
    assert reimport(package.scope(), {changed}) is None
    assert sys.modules[f"{package.name}.entry"].X == 2


def test_a_file_added_in_the_batch_is_importable(package):
    package.write("entry.py", "Y = 0\n")
    import_module(f"{package.name}.entry")
    changed = {package.write("b.py", "Y = 3\n"), package.write("entry.py", "from .b import Y\n")}
    assert reimport(package.scope(), changed) is None
    assert sys.modules[f"{package.name}.entry"].Y == 3
