# MCP & HTTP transport

## Summary

**Kind:** layer

The single process boundary: it publishes the workspace store as 24 FastMCP tools and 6 FastAPI
HTML routes, translating domain errors into each surface's error type and holding no domain logic
of its own.

## Purpose

Every way into pasta from outside runs through here. It exists to keep protocol concerns — tool
registration, request parsing, template rendering, HTTP status codes, MCP error envelopes — out of
the store and the pure core, so those can be written and tested against plain Python values.

Delete it and pasta becomes a library with no callers: the FSM-driven authoring loop that the
`instructions()` tool describes has no way to reach an agent, and the HTML reading surface
disappears. Nothing else would break, which is the point — the dependency runs one way.

This layer is where the two surfaces stay honest about being *one* system. Both are served from
the same module-level `STORE` instance, so a page mutated over MCP is immediately visible to a
browser reading the HTML view, with no cache or sync step between them.

## Usage

Callers arrive on one of two surfaces, both defined in `src/server.py`:

**MCP** — `mcp: FastMCP = FastMCP("pasta")`, exposed as an ASGI app via
`mcp.http_app(path="/mcp")` and mounted into FastAPI at `/pasta`, so the endpoint is
`/pasta/mcp`. The 24 `@mcp.tool` functions split into:

- *Orientation:* `instructions`, `listWorkspaces`, `tree`, `outline`, `search`,
  `describePageType`, `describeMutations`
- *Reading:* `getPage`, `renderPage`
- *Direction:* `nextActions`, `attention`
- *Writing:* `createWorkspace`, `createPage`, `mutatePageBatch`, `setWorkspaceGuidance`,
  `archivePage`, `unarchivePage`, `archiveWorkspace`, `unarchiveWorkspace`, `reparentPage`,
  `reorderPage`, `renamePage`, `link`, `unlink`

The intended call order is stated by `instructions()` itself and is not enforced here: find a
workspace, read before writing, then follow the `next` block echoed by every write rather than
planning a command sequence up front.

**HTTP** — `app = FastAPI(...)` with six routes: `route_index` (`/`), `route_tree`,
`route_page` (`/ws:{id}/{pageId}`), plus three form-post mutations, `route_archive_page`,
`route_unarchive_page`, and `route_set_page_status`. `http_exception_handler` renders
`error.html`. Jinja templates live in `src/templates/`, with `/static` and `/sphinx`
`StaticFiles` mounts for CSS, images, and the built Sphinx docsite.

Two lifecycle entry points matter to anyone changing this file:

- `validate_registry()` runs at **module import**, before `STORE` exists. On a cold start and on
  every HMR re-execution of this module, every page-type declaration error is raised at once.
- `app_lifespan` starts and stops the cleanup scheduler — but only under plain ASGI hosting. Under
  the dev server, `hmr_server.reloader_lifespan` owns that instead (see component 09).

## Data model

This layer owns almost no state, deliberately. What it does own:

- `STORE = Store(DATA_DIR)` — one module-level store instance, rooted at `$PASTA_DATA_DIR`
  (default `.pasta-data`). Process-lifetime; re-created when the module hot-reloads.
- `mcp`, `mcp_app`, `app`, `templates` — the framework objects, also module-level and
  re-created on reload.

Everything else is per-request and derived: a tool reads through `STORE`, shapes the result with
`serialize.page_to_dict` or one of the renderers, and returns it. No request state is cached
between calls, and no page data is mutated here — writes are delegated whole to a `Store` method.

## Details

The error-translation boundary is the one piece of real logic in this layer, and it is two context
managers with opposite jobs:

```python
@contextmanager
def _guard_tool() -> Generator[None]:
    """Translate expected domain errors into client-visible tool errors."""
    try:
        yield
    except PastaError as exc:
        raise ToolError(str(exc)) from exc
```

`_guard_tool` is the most-called symbol in the repository (23 call sites — essentially every
tool body). It catches only `PastaError`, so an expected domain failure reaches the agent as a
readable `ToolError` while a genuine bug still propagates as a crash. `_guard_http` is its
counterpart for the browser: it catches *everything*, wraps the traceback in `InternalError`, and
lets `http_exception_handler` render it with reload support.

The graph makes the thinness of this layer measurable. Leiden clustering co-locates `server.py`
with `store.py` in six separate communities (`Cluster_1`, `Cluster_74`, `Cluster_75`,
`Cluster_77`, `Cluster_79`, `Cluster_81`); each pairs an MCP tool with the store method it
delegates to. With 35 `CALLS` edges from `server.py` to `store.py` — the heaviest file pair in the
repo — and 46 symbols total, there is roughly one store call per symbol in the file. A change that
adds logic here rather than in the store will show up as a new community that no longer pairs with
a store method.

The no-cache middleware exists for a mundane reason worth recording: the server is only ever
hosted locally, so browser caching buys nothing and had been serving stale images. It wraps the
`StaticFiles` mounts too.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/server.py` | *(whole module)* | file |
| `src/server.py` | `_guard_tool` | function |
| `src/server.py` | `_guard_http` | function |
| `src/server.py` | `app_lifespan` | function |
| `src/server.py` | `instructions` | function |
| `src/server.py` | `mutatePageBatch` | function |
| `src/server.py` | `route_page` | function |
| `src/server.py` | `http_exception_handler` | function |
| `src/server.py` | `fastapi_reloader` | function |
| `src/server.py` | `STORE` | constant |
| `src/server.py` | `InternalError` | class |
| `src/templates/page.html` | *(page view)* | file |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Workspace store](02-workspace-store.md) | depends-on | 35 `CALLS` edges; every tool and route body delegates to a `Store` method |
| [Domain model](04-domain-model.md) | depends-on | imports `PastaError` to decide what `_guard_tool` catches |
| [Page-type system](05-page-type-system.md) | depends-on | `get_page_type`, `registered_pagetypes`, and the load-time `validate_registry()` |
| [Rendering](07-rendering.md) | depends-on | `escape_markdown`, `render_workspace_links`, `md2html` for the HTML views |
| [Introspection & doc generation](08-introspection-docsgen.md) | depends-on | `describe_page_type` / `describe_mutations` back the two describe tools |
| [Lifecycle & cleanup](10-lifecycle-cleanup.md) | calls | `app_lifespan` starts/stops the sweep scheduler under plain ASGI hosting |
| [Dev server & HMR](09-dev-server-hmr.md) | exposes | exports `mcp` and `app` for the dev server to mount; pushes browser refreshes via `ws_reloader` (17 `CALLS` edges) |

## Invariants

1. **No tool body raises a bare `PastaError` to the client.** Every tool wraps its work in
   `_guard_tool`. Violated, an agent receives an unhandled server exception instead of a readable
   message naming what to fix, and the FSM-driven loop stalls with no recoverable signal.
2. **`validate_registry()` completes before any request is served.** It is called at module
   import, above `STORE`. Violated, a malformed page type is discovered mid-request, and the
   client gets an arbitrary failure on an unrelated call instead of a startup error listing every
   declaration problem.
3. **This layer never mutates a `Page`.** Writes go through a single `Store` method call that owns
   the transaction. Violated, a mutation escapes the store's transaction lock and revision-token
   check, so a concurrent write can be lost with no conflict reported.
4. **Exactly one `Store` instance per process.** Both surfaces read `STORE`. Violated, two
   instances hold separate per-workspace lock tables, and the locks stop excluding each other.

## Sync

Reconciled against commit `a35b133`.
