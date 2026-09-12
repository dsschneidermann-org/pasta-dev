# Dev server & HMR

## Summary

**Kind:** subsystem

The development-only host: one uvicorn process, one file watcher, and one reactive context that
hot-reload `src.server` in place — swapping the MCP mount without dropping client sessions and
refreshing browsers over a surviving WebSocket.

## Purpose

It exists so that editing pasta's source does not cost you your session. A process respawn would
disconnect every connected MCP client and every browser tab; this subsystem re-executes the
changed modules inside the running process instead, then tells each surface that something
changed in the way that surface understands — `tools/list_changed` for MCP, a refresh frame for
the browser.

It merges two reference patterns: `uvicorn-hmr` (serve a reloaded ASGI app, refresh the browser)
and `mcp-hmr` (a stable proxy plus a session-preserving tool swap).

This is **dev-only tooling and the most brittle component in the repo**, by its own admission. It
reaches into private `fastmcp` internals — `base_app.providers` / `FastMCPProvider` for
mount/unmount, `base_app._mcp_server.run` for session capture — which have changed across fastmcp
versions (3.4.x at the time of writing). Revisit on any fastmcp upgrade. Delete it and pasta still
runs in production via `main.py --stdio` or plain ASGI hosting; only the edit-test loop degrades.

## Usage

`main.py` is the only caller. `run_dev_server(host, port)` builds the app and blocks:

```python
uvicorn.run(build_dev_app(), host=host, port=port, timeout_graceful_shutdown=1)
```

`build_dev_app()` returns a `Starlette` app with two mounts: `/pasta` → the stable MCP proxy's
ASGI app, and `/` → `fastapi_dispatch`, which forwards every other request (including the
`/ws/reloader` WebSocket) to the freshly reloaded FastAPI app.

There is one hard usage rule, stated in the module docstring and easy to break by accident:

> `src.server` and `src.cleanup` must be imported **ONLY** through the reloader's finder — never
> at module top level — or the hot reload silently becomes a no-op.

That is why `main.py` imports `src.server` lazily inside its `--stdio` branch, and why this
module reaches its target through `import_module(TARGET_MODULE)` inside a `@derived` function
rather than with a top-level `import`.

`src/hmr_live_refresh.py` is used from both sides: the reactively-reloaded `src.server` calls
`ws_reloader.refresh()` after a mutation (17 `CALLS` edges), and the stable `src.hmr_server` calls
it after a file change.

`src/_hmr_debug.py` is wired in by an import at the *end* of `server.py`, so it hot-loads with the
server. Import-time side effect only, and idempotent.

## Data model

All state here is in-process and dev-only:

- **`ws_reloader`** — a process-wide `ReloaderConnectionManager` singleton holding the live
  browser WebSockets in `active`. **This module is deliberately excluded from the reload set**
  (`excludes=[_LIVE_REFRESH_FILE]`): if it were re-executed on every source change, the socket
  list would be dropped and browser auto-refresh would silently stop working.
- **`_active_sessions`** — a `WeakSet[ServerSession]` of live MCP sessions, so a reload can
  notify them. Weak, so a dropped session is collected rather than leaked.
- **`base_app`** — the stable `FastMCP("pasta-hmr-proxy")`, built **once** and never rebuilt; only
  what is mounted under it swaps.
- `stop_event` / `finish_event` / `mount_lock` — the handshake that guarantees only one mount is
  live at a time.
- `last_fastapi_app` — the app object last served; a changed identity *is* the reload signal.
- **`hmr_debug.log`** in the repo root — the one file this subsystem writes.

Nothing here is persisted or shared between processes, and none of it exists under production
hosting.

## Details

**Two surfaces, two reload strategies.** The MCP side cannot simply be re-pulled per request,
because a session is long-lived: so a stable proxy is mounted once, and on reload the old mount is
torn down and the reloaded `src.server.mcp` is mounted under the same proxy, after which live
sessions are sent `tools/list_changed` (plus resource and prompt equivalents). The FastAPI side
*can* be re-pulled per request, so `fastapi_dispatch` reads `current_fastapi()` on every request
and forwards to whatever is current.

**Reactive subscription is how reloads propagate.** `current_mcp()` and `current_fastapi()` are
`@derived(context=HMR_CONTEXT)` functions that call `import_module(TARGET_MODULE)`; *reading* one
inside a reactive computation subscribes that computation to reloads of `src.server` and its
dependencies. The reload effects then re-run on a change.

**Tear down before mounting.** `mcp_reload_effect` distinguishes the first mount from a reload by
whether a previous mount is live, and on a reload sets `stop_event` and *waits* for
`finish_event` before swapping:

```python
if is_reload:
    stop_event.set()
    await finish_event.wait()
mcp = current_mcp()          # subscribe to reloads
stop_event, finish_event = Event(), Event()
task_group.create_task(serve_mcp(mcp, stop_event, finish_event))
```

`serve_mcp` holds `mount_lock` for the whole life of a mount, so the two mounts can never overlap.

**Session capture is a self-restoring monkey-patch.** `_patch_session_init` wraps
`ServerSession.__init__` to record the next new session and then unpatches itself, with
`_pending_session_patches` counting outstanding patches so concurrent captures do not restore the
original too early.

**The cleanup scheduler is owned here, not by `server.app_lifespan`.** Under the dev server,
`app_lifespan` never fires (the FastAPI app is mounted as a dispatch target, not hosted
directly), so `reloader_lifespan` starts and stops the sweep — and `cleanup_reload_effect`
restarts it on the new code after each reload. The effect reads a module attribute specifically to
subscribe itself to `src.cleanup`, because `ReactiveModule.load` is otherwise lazy. `cleanup`'s own
`on_dispose` hook has already cancelled the old task by the time the effect runs.

**Browser refresh rides on the file watcher.** `Reloader.on_changes` reloads the changed modules
via reactive propagation and *then* creates a task for `ws_reloader.refresh()`, wrapped in
`suppress(RuntimeError)` for the no-running-loop case.

**Reload failures are otherwise invisible**, which is why `_hmr_debug.py` exists: `reactivity.hmr`
only *prints* a module's re-exec error and then swallows it (`ErrorFilter` → `sys.excepthook`),
and errors raised inside the async reload effect go to the event loop's exception handler. Both
sinks are teed to `hmr_debug.log`, making the load-ordering races a multi-file change can trigger
diagnosable after the fact rather than only visible as console output.

Logging goes through `logging.getLogger("uvicorn.error")` in both this module and `cleanup`,
because uvicorn configures only its own loggers — a standalone module logger at INFO would be
dropped.

On the graph: this is the largest non-test cluster in `src/` — `Cluster_76` (12 symbols) spans
`hmr_server.py`, `hmr_live_refresh.py`, `store.py`, and `server.py`, with six further
single-file `hmr_server.py` clusters (`Cluster_3`, `Cluster_35`–`Cluster_39`) and `Cluster_9` for
`_hmr_debug.py` at 100% cohesion. `Cluster_78` pairs `hmr_live_refresh.py` with `server.py` — the
mutation-refresh path.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/hmr_server.py` | `build_dev_app` | function |
| `src/hmr_server.py` | `run_dev_server` | function |
| `src/hmr_server.py` | `mcp_reload_effect` | function |
| `src/hmr_server.py` | `cleanup_reload_effect` | function |
| `src/hmr_server.py` | `reloader_lifespan` | function |
| `src/hmr_server.py` | `serve_mcp` | function |
| `src/hmr_server.py` | `mount_mcp` | function |
| `src/hmr_server.py` | `notify_sessions` | function |
| `src/hmr_server.py` | `fastapi_dispatch` | function |
| `src/hmr_server.py` | `_patch_session_init` | function |
| `src/hmr_server.py` | `Reloader` | class |
| `src/hmr_server.py` | `TARGET_MODULE` | constant |
| `src/hmr_live_refresh.py` | `ReloaderConnectionManager` | class |
| `src/hmr_live_refresh.py` | `ws_reloader` | constant |
| `src/_hmr_debug.py` | `_log` | function |
| `main.py` | `main` | function |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [MCP & HTTP transport](01-mcp-http-transport.md) | depends-on | the reload target; reached only as `import_module("src.server")` inside a reactive function |
| [Lifecycle & cleanup](10-lifecycle-cleanup.md) | calls | owns the sweep's start/stop under the dev server and restarts it after each reload |
| `reactivity` / `reactivity.hmr` | depends-on | `HMR_CONTEXT`, `@derived`, `@async_effect`, `AsyncReloader`, the import finder |
| `fastmcp` (3.4.x, private internals) | depends-on | `base_app.providers`, `FastMCPProvider`, `base_app._mcp_server.run` — brittle across versions |
| `uvicorn`, `starlette` | depends-on | the host process and the outer two-mount ASGI app |
| `mcp.server.session` | depends-on | `ServerSession.__init__` is patched to capture sessions |

## Invariants

1. **`src.server` and `src.cleanup` are imported only through the reloader's finder.** Never at
   module top level. Violated, the modules are not reactive and hot reload silently becomes a
   no-op — the worst failure mode here, because nothing errors.
2. **`hmr_live_refresh.py` stays out of the reload set.** It is named in the reloader's
   `excludes`. Violated, the live browser socket list is dropped on the first source change and
   auto-refresh stops working with no error.
3. **Exactly one MCP mount is live at a time.** `serve_mcp` holds `mount_lock`, and a reload sets
   `stop_event` and awaits `finish_event` before mounting the replacement. Violated, two mounts
   answer the same proxy and a client sees duplicated or stale tools.
4. **The MCP proxy is built once per process.** `base_app` is created in `build_dev_app` and only
   its mounts swap. Violated, connected sessions are attached to an app that no longer serves
   them — exactly the session drop this subsystem exists to avoid.
5. **Live sessions are notified after every successful swap.** `notify_sessions` runs inside
   `serve_mcp`. Violated, a client keeps calling a tool list that no longer matches the server.
6. **`ServerSession.__init__` is restored after capture.** `capture_init` self-unpatches, guarded
   by `_pending_session_patches`. Violated, the patch leaks across reloads and stacks wrappers on
   every session construction.
7. **The cleanup scheduler has exactly one owner per hosting mode.** `reloader_lifespan` under the
   dev server; `app_lifespan` under plain ASGI. Violated, two sweep tasks run concurrently and
   both try to prune the same workspace.
8. **Nothing in this subsystem is required in production.** `main.py --stdio` bypasses it
   entirely. Violated, a dev-only dependency on private fastmcp internals becomes a production
   dependency.

## Sync

Reconciled against commit `a35b133`.
