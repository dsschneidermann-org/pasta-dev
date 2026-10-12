from __future__ import annotations

import os
import asyncio
from contextlib import contextmanager, asynccontextmanager
from typing import Any
from collections.abc import Generator
import traceback

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse

from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from . import cleanup
from .describe import describe_mutations, describe_page_type
from .errors import PastaError
from .hmr_live_refresh import ws_reloader
from .instructions import render_instructions
from .pagetypes._registry import (
    declaration_errors,
    get_page_type,
    registered_pagetypes,
    validate_registry,
    workspace_guidance_fields,
)
from .render import escape_markdown, render_workspace_links
from .render_html import md2html
from .serialize import page_to_dict
from .store import Store

# Fail fast: validate every page type once at load. This runs on a cold start and re-runs on
# every HMR reload (this module re-executes then), so a misconfigured type surfaces every error
# at once instead of piecemeal during a later request.
validate_registry()

DATA_DIR = os.environ.get("PASTA_DATA_DIR", ".pasta-data")
STORE = Store(DATA_DIR)


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    # Covers plain ASGI hosting; under the HMR dev server this never fires.
    cleanup.start_scheduler(STORE)
    yield
    await cleanup.stop_scheduler()

mcp: FastMCP = FastMCP("pasta")
mcp_app = mcp.http_app(path="/mcp")

app = FastAPI(
    title="Pasta Wiki with MCP",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))

app.mount("/static", StaticFiles(directory="src/static"), name="static")
app.mount("/sphinx", StaticFiles(directory="docsite/_build/html"), name="sphinx")

templates = Jinja2Templates(directory="src/templates")


# --- Declaration quarantine --------------------------------------------------
# Validating in this module's body guards the moment it executes, not the surface it goes on to
# serve. Under hot reload the two come apart: the page types can reload invalid while this module's
# own re-exec fails, leaving the objects built by the last good exec mounted and answering out of a
# registry that no longer validates. So ask again per request, against the live registry, at the
# two points every caller passes through - which is what lets a gate hold even from a stale module.
# Neither needs a reset: a reload that declares valid types simply answers None, and a cold start
# still fails outright above.
#
# Registered ahead of `add_no_cache_headers` so that one stays the outer middleware and stamps this
# response too, since a cached refusal would outlive the fix.
@app.middleware("http")
async def refuse_invalid_declarations(request: Request, call_next):
    errors = declaration_errors()
    # The refusal page renders with the stylesheet and theme assets served from /static.
    if errors is None or request.url.path.startswith("/static"):
        return await call_next(request)
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "message": "The page-type declarations are invalid; the wiki is not being served.",
            "trace": ("The page-type declarations are invalid, so this server is refusing to serve "
                      "rather than answer out of them:\n\n"
                      f"{errors}\n\n"
                      "Fix the declaration and save - the reload will bring this page back."),
        },
        status_code=503,
    )


# --- No HTTP caching ---------------------------------------------------------
# The server is only ever hosted locally, so browser caching buys nothing and has
# been serving stale images. Stamp a no-cache header on most responses. This wraps
# the /static and /sphinx StaticFiles mounts too (where image files live) - the
# per-route responses alone wouldn't cover those. CSS stylesheet is excepted.
# BaseHTTPMiddleware only sees HTTP scopes, the /ws/reloader websocket passes through.
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.endswith(".css"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# --- Websocket reloader ------------------------------------------------------
# The browser-facing connection manager (`ws_reloader`) lives in src.hmr_live_refresh so its
# live connections survive hot reloads. Under hot-module-reload (src.hmr_server) the
# refresh is fired on file changes; the mutation tools below also fire it on data changes.

@app.websocket("/ws/reloader")
async def fastapi_reloader(websocket: WebSocket):
    await ws_reloader.connect(websocket)

    async def send_updates():
        while True:
            await websocket.send_text('{"refresh": 0}')
            await asyncio.sleep(5)

    task = asyncio.create_task(send_updates())
    try:
        while True:
            _ = await websocket.receive_text()  # receive and do nothing
    except WebSocketDisconnect:
        _ = task.cancel()


# --- FastAPI routes ----------------------------------------------------------
@contextmanager
def _guard_http() -> Generator[None]:
    """Translate unexpected errors into internal errors with refresh support."""
    try:
        yield
    except Exception as exc:
        tb = traceback.TracebackException(type(exc), exc, exc.__traceback__)
        raise InternalError(tb)


@app.get("/", response_class=HTMLResponse)
async def route_index(request: Request, archived: str | None = None):
    with _guard_http():
        show_archived = True if archived == "true" else False
        body = md2html.render("\n\n".join(f"[{escape_markdown(x['name'])}](/{x['id']})" for x in STORE.list_workspaces()))
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "show_archived": show_archived,
                "body": body,
            }
        )


@app.get("/ws:{workspaceIdPart}", response_class=HTMLResponse)
async def route_tree(request: Request, workspaceIdPart: str, archived: str | None = None, markdown: str | None = None):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        workspace = STORE.load_workspace(workspace_id)
        show_archived = True if archived == "true" else False
        pages_tree = STORE.tree(workspace_id, show_archived)
        body = md2html.render(render_workspace_links(pages_tree, show_archived, show_meta=True, escape_plain_text=True))
        return templates.TemplateResponse(
            request=request,
            name="tree.html",
            context={
                "workspace_id": workspace_id,
                "workspace_name": workspace.name,
                "show_archived": show_archived,
                "body": body,
            }
        )


@app.get("/ws:{workspaceIdPart}/page/{pageId}", response_class=HTMLResponse)
async def route_page(request: Request, workspaceIdPart: str, pageId: str, archived: str | None = None, markdown: str | None = None):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        workspace = STORE.load_workspace(workspace_id)
        page = STORE.get_page(workspace_id, pageId)
        page_type = get_page_type(page.type)
        show_archived = True if archived == "true" else False
        nav = md2html.render(render_workspace_links(STORE.tree(workspace_id, show_archived), show_archived, show_meta=False, escape_plain_text=True))
        body = STORE.render_html(workspace_id, pageId, show_archived)
        if markdown == "true":
            body = md2html.render(STORE.render_markdown(workspace_id, pageId, show_archived, escape_plain_text=True))
        return templates.TemplateResponse(
            request=request,
            name="page.html",
            context={
                "workspace_id": workspace_id,
                "workspace_name": workspace.name,
                "show_archived": show_archived,
                "nav": nav,
                "body": body,
                # Drives the Archive/Unarchive button at the bottom of the page (see page.html).
                "page_id": page.id,
                "archived": page.archived,
                # Drives the Set to delete / Cancel delete button beside it.
                "delete_scheduled": page.delete_scheduled,
                # Drives the status dropdown next to the Archive button: every status of this
                # page's type, with the current one preselected.
                "statuses": page_type.fsm.states if page_type is not None else (),
                "status": page.status,
                # The Model overlay loads the docsite page for the page's type AND current status.
                "page_type_doc": f"{page.type}-{page.status}",
            },
        )


# Archive/unarchive a page from its web view. These mirror the archivePage / unarchivePage MCP
# tools (a browser can't call MCP), so the wiki's Archive/Unarchive button POSTs here. Each fires
# the live-reload refresh like the MCP tools do, then 303-redirects back to the page (GET) so a
# reload/back-button doesn't re-POST the mutation.
@app.post("/ws:{workspaceIdPart}/page/{pageId}/archive", response_class=PlainTextResponse)
async def route_archive_page(workspaceIdPart: str, pageId: str):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        STORE.archive_page(workspace_id, pageId)
        await ws_reloader.refresh()
        return PlainTextResponse(status_code=202)


@app.post("/ws:{workspaceIdPart}/page/{pageId}/unarchive", response_class=PlainTextResponse)
async def route_unarchive_page(workspaceIdPart: str, pageId: str):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        STORE.unarchive_page(workspace_id, pageId)
        await ws_reloader.refresh()
        return PlainTextResponse(status_code=202)


# Schedule or cancel a page's deletion from its web view, behind the button beside the archive
# control. Scheduling also archives, so a page queued for deletion is never left in a live view,
# and the sweep destroys it only once its grace period has passed. Deciding this is a human act in
# the browser, so there is no MCP counterpart.
@app.post("/ws:{workspaceIdPart}/page/{pageId}/schedule-delete", response_class=PlainTextResponse)
async def route_schedule_page_deletion(workspaceIdPart: str, pageId: str):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        STORE.schedule_page_deletion(workspace_id, pageId)
        await ws_reloader.refresh()
        return PlainTextResponse(status_code=202)


@app.post("/ws:{workspaceIdPart}/page/{pageId}/unschedule-delete", response_class=PlainTextResponse)
async def route_unschedule_page_deletion(workspaceIdPart: str, pageId: str):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        STORE.unschedule_page_deletion(workspace_id, pageId)
        await ws_reloader.refresh()
        return PlainTextResponse(status_code=202)


# Directly set a page's lifecycle status from its web view. Backs the status dropdown + Apply button
# next to the Archive control (see page.html): a deliberate FSM-bypassing admin override, so a human
# can force any of the type's declared statuses. `status` arrives as a form field. Like the archive
# routes it fires the live-reload refresh and 202s (no MCP equivalent - a browser can't call MCP).
@app.post("/ws:{workspaceIdPart}/page/{pageId}/status", response_class=PlainTextResponse)
async def route_set_page_status(workspaceIdPart: str, pageId: str, status: str = Form(...)):
    with _guard_http():
        workspace_id = f"ws:{workspaceIdPart}"
        STORE.set_page_status(workspace_id, pageId, status)
        await ws_reloader.refresh()
        return PlainTextResponse(status_code=202)


# --- FastAPI exception handlers ----------------------------------------------
class InternalError(Exception):
    tb: traceback.TracebackException

    def __init__(self, tb: traceback.TracebackException):
        super().__init__()
        self.tb = tb


@app.exception_handler(InternalError)
async def http_exception_handler(request: Request, exc: InternalError):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "message": "".join(exc.tb.format_exception_only()).strip(),
            "trace": "".join(exc.tb.format(chain=True)).strip(),
        },
        status_code=500
    )


# --- MCP -------------------------------------------------------------------
app.mount("/pasta", mcp_app)  # MCP endpoint at /pasta/mcp


class _RefuseInvalidDeclarations(Middleware):
    """The tool-call half of the declaration quarantine above.

    Hung on the call rather than on each tool, so it covers any tool added later, and not on the
    handshake, so a client can still connect while the surface is down. The refusal carries the
    errors themselves: this surface is driven by an agent, which never sees the dev console and has
    nowhere else to learn why the server stopped answering.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        errors = declaration_errors()
        if errors is None:
            return await call_next(context)
        # Resolved from the running server's package rather than the caller's cwd: a caller is
        # often working in a different checkout than the server it is talking to. The log holds the
        # traceback behind these errors, which the aggregated message deliberately does not carry.
        from ._hmr_debug import LOG_PATH
        raise ToolError(
            "The page-type declarations are invalid, so this server is refusing to serve rather "
            f"than answer out of them:\n{errors}\n"
            f"The full reload traceback is at {LOG_PATH}.\n"
            "Fix the declaration and save; the reload restores the tools.")


mcp.add_middleware(_RefuseInvalidDeclarations())


@contextmanager
def _guard_tool() -> Generator[None]:
    """Translate expected domain errors into client-visible tool errors."""
    try:
        yield
    except PastaError as exc:
        raise ToolError(str(exc)) from exc


# --- Reads -------------------------------------------------------------------
@mcp.tool
async def instructions() -> str:
    """Retrieve instructions for pasta MCP."""
    tools = [(tool.name, tool.to_mcp_tool().inputSchema) for tool in await mcp.list_tools()]
    return render_instructions(tools, sorted(workspace_guidance_fields()))


@mcp.tool
async def listWorkspaces() -> list[dict[str, str]]:
    """List all workspaces (id, name, status)."""
    with _guard_tool():
        return STORE.list_workspaces()


@mcp.tool
async def tree(workspaceId: str) -> dict[str, Any]:
    """The ordered page tree (title, type, status, id) of LIVE work. Archived pages and their
    subtrees are always hidden - there is no flag to include them, because the archived tail is
    history and returning it inline buries the active pages. To reach an archived page, use
    `getPage` with its id (which does not filter on archived), or the web UI's ?archived=true
    view."""
    with _guard_tool():
        return STORE.tree(workspaceId)


@mcp.tool
async def getPage(workspaceId: str, pageId: str) -> dict[str, Any]:
    """Fetch one page's projected state (type, title, status, sections). Large pages exceed
    the tool response limit and are **persisted to a temp JSON file on disk** instead of being
    inlined."""
    with _guard_tool():
        return page_to_dict(STORE.get_page(workspaceId, pageId))


@mcp.tool
async def describePageType(type: str) -> dict[str, Any]:
    """Describe a page type's sections, fields, commands, and FSM."""
    with _guard_tool():
        page_type = get_page_type(type)
        if page_type is None:
            raise ToolError(
                f"Unknown page type '{type}'. Registered: {', '.join(registered_pagetypes())}.")
        return describe_page_type(page_type)


@mcp.tool
async def listPageTypes() -> dict[str, list[str]]:
    """List the tags of every registered page type."""
    with _guard_tool():
        return {"types": list(registered_pagetypes())}


@mcp.tool
async def describeMutations(workspaceId: str, pageId: str) -> dict[str, Any]:
    """List the commands a page can run now - each with its arg schema and current legality."""
    with _guard_tool():
        page = STORE.get_page(workspaceId, pageId)
        page_type = get_page_type(page.type)
        if page_type is None:
            raise ToolError(f"Page '{pageId}' has unregistered type '{page.type}'.")
        return {
            "pageId": page.id,
            "type": page.type,
            "status": page.status,
            "commands": describe_mutations(page, page_type),
        }


@mcp.tool
async def outline(workspaceId: str, pageId: str) -> dict[str, Any]:
    """A page's section tree (key, name, order, field kinds). Structure only, no body content."""
    with _guard_tool():
        return STORE.outline(workspaceId, pageId)


@mcp.tool
async def renderPage(workspaceId: str, pageId: str | None = None) -> dict[str, str]:
    """Render a page to Markdown; omit `pageId` to render the whole (non-archived) workspace tree.
    Large pages exceed the tool response limit and are **persisted to a temp JSON file on disk**
    instead of being inlined."""
    with _guard_tool():
        return {"markdown": STORE.render_markdown(workspaceId, pageId)}


@mcp.tool
async def search(workspaceId: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Full-text search over page content in a workspace: ranked hits with a snippet each.
    Case-insensitive, matches by word prefix, and excludes archived pages AND their descendants -
    the same subtree rule `tree` applies, so the two agree on what is live. Prefix the query
    with `id:` to resolve a full or partial page id instead (e.g. `id:msakene4`); id search
    spans archived pages too, and every hit carries an `archived` flag."""
    with _guard_tool():
        return STORE.search(workspaceId, query, limit)


@mcp.tool
async def nextActions(workspaceId: str, pageId: str | None = None) -> dict[str, Any]:
    """Roll up FSM edges over a page's subtree (or the whole workspace) into `do` (agent edges
    legal now), `blocked` (agent edges with the unmet precondition to fix), `humanGates`
    (sign-off edges - stop), and `attention` (items awaiting a human)."""
    with _guard_tool():
        return STORE.next_actions(workspaceId, pageId)


@mcp.tool
async def attention(workspaceId: str) -> dict[str, Any]:
    """Scan a workspace for element instances awaiting a human (e.g. an escalated open question)."""
    with _guard_tool():
        return STORE.attention(workspaceId)


# --- Writes ------------------------------------------------------------------
@mcp.tool
async def createWorkspace(name: str) -> dict[str, str]:
    """Create a new workspace and return its id."""
    with _guard_tool():
        workspace = STORE.create_workspace(name)
        await ws_reloader.refresh()
        return {"id": workspace.id, "name": workspace.name, "status": workspace.status}


@mcp.tool
async def createPage(workspaceId: str, type: str, title: str, parentId: str | None = None) -> dict[str, Any]:
    """Create a new page of a registered type, optionally under a parent.
    If the type declares pinned children, they are auto-created in the same commit and returned
    under `children` - author into those, do not create your own. Returns the page id, status
    and next actions.
    """
    with _guard_tool():
        result = STORE.create_page(workspaceId, type, title, parentId)
        page = result.page
        next_actions = STORE.next_actions(workspaceId, page.id)
        await ws_reloader.refresh()
        return {
            "id": page.id,
            "type": page.type,
            "title": page.title,
            "status": page.status,
            "parentId": page.parent_id,
            "statusRevisionToken": page.status_revision_token,
            # Guidance is not shown for auto-pinned child pages.
            "children": [
                {"id": child.id, "type": child.type, "title": child.title, "status": child.status}
                for child in result.children
            ],
            "next": next_actions,
        }


@mcp.tool
async def mutatePageBatch(
    workspaceId: str, pageId: str, commands: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run an ordered batch of commands on a page as a single atomic commit (each `{command, args}`
    decided against the state left by the previous). Every command must carry the page's current
    `statusRevisionToken` as the first entry in its `args` - a short token read from getPage, the
    render* meta line, or a prior write/nextActions echo. A status transition regenerates it, so at
    most one transition is legal per batch and only as the final command: a command after a transition
    carries a now-stale token. All-or-nothing: any rejection aborts the whole batch and nothing commits
    - the error names the failing index and command. Echoes the new status, the current
    `statusRevisionToken`, and next actions."""
    with _guard_tool():
        page, created = STORE.mutate_page_batch(workspaceId, pageId, commands)
        next_actions = STORE.next_actions(workspaceId, pageId)
        await ws_reloader.refresh()
        return {
            "pageId": page.id,
            "status": page.status,
            "statusRevisionToken": page.status_revision_token,
            "count": len(created),
            "createdIds": created,
            "next": next_actions,
        }


# --- Workspace guidance configuration ----------------------------------------
@mcp.tool
async def setWorkspaceGuidance(workspaceId: str, field: str, text: str) -> dict[str, Any]:
    """Set the workspace's stored guidance text for a configurable guidance field.

    An unknown field is rejected, listing the ones that are declared. `text` is a single string,
    and an empty string clears the field. Once set, the text is surfaced to pages that declare the
    field while they sit at one of its statuses. Returns the workspace id, the field, and the config.
    """
    with _guard_tool():
        workspace = STORE.set_workspace_guidance(workspaceId, field, text)
        await ws_reloader.refresh()
        return {"workspaceId": workspace.id, "field": field,
                "guidanceConfig": dict(workspace.guidance_config)}


# --- Archiving ---------------------------------------------------------------
@mcp.tool
async def archiveWorkspace(workspaceId: str) -> dict[str, str]:
    """Archive a whole workspace - mark it archived in listings. Reversible; pages preserved."""
    with _guard_tool():
        workspace = STORE.archive_workspace(workspaceId)
        await ws_reloader.refresh()
        return {"id": workspace.id, "name": workspace.name, "status": workspace.status}


@mcp.tool
async def unarchiveWorkspace(workspaceId: str) -> dict[str, str]:
    """Unarchive a previously archived workspace - restore it to active. Runnable while archived."""
    with _guard_tool():
        workspace = STORE.unarchive_workspace(workspaceId)
        await ws_reloader.refresh()
        return {"id": workspace.id, "name": workspace.name, "status": workspace.status}


@mcp.tool
async def archivePage(workspaceId: str, pageId: str) -> dict[str, Any]:
    """Archive a page - hide it (and its subtree) from default tree views. It cannot be mutated
    while archived (unarchive first). Reversible."""
    with _guard_tool():
        page = STORE.archive_page(workspaceId, pageId)
        await ws_reloader.refresh()
        return {"id": page.id, "archived": page.archived}


@mcp.tool
async def unarchivePage(workspaceId: str, pageId: str) -> dict[str, Any]:
    """Unarchive a page - restore it to default tree views. Lifecycle status is unchanged."""
    with _guard_tool():
        page = STORE.unarchive_page(workspaceId, pageId)
        await ws_reloader.refresh()
        return {"id": page.id, "archived": page.archived}


# --- Page-tree structure -----------------------------------------------------
@mcp.tool
async def reparentPage(
    workspaceId: str, pageId: str, newParentId: str | None = None
) -> dict[str, Any]:
    """Move a page under a new parent (or to top level when newParentId is null), appended to the
    new parent's children - use reorderPage to position it. Rejects a cycle (the new parent being
    the page or one of its descendants). Sibling titles are not reserved."""
    with _guard_tool():
        page, sibling_ids = STORE.reparent_page(workspaceId, pageId, newParentId)
        await ws_reloader.refresh()
        return {"id": page.id, "parentId": page.parent_id, "siblingIds": sibling_ids}


@mcp.tool
async def reorderPage(
    workspaceId: str, pageId: str, toIndex: int, precedingId: str | None = None
) -> dict[str, Any]:
    """Move a page to an anchored position among its siblings, mirroring block/element reorder:
    toIndex is the resting index and precedingId is the sibling expected just before it (null for
    the front). A drifted index or a mismatched precedingId is rejected as a stale read."""
    with _guard_tool():
        page, sibling_ids = STORE.reorder_page(workspaceId, pageId, toIndex, precedingId)
        await ws_reloader.refresh()
        return {"id": page.id, "parentId": page.parent_id, "siblingIds": sibling_ids}


@mcp.tool
async def renamePage(workspaceId: str, pageId: str, title: str) -> dict[str, Any]:
    """Change a page's title. Sibling titles are not reserved - renaming to a title already used by
    a sibling is allowed (titles are display labels, not identifiers). Works on archived and pinned
    pages. Rejects a blank title."""
    with _guard_tool():
        page = STORE.rename_page(workspaceId, pageId, title)
        await ws_reloader.refresh()
        return {"id": page.id, "title": page.title}


# --- Page reference graph ----------------------------------------------------
@mcp.tool
async def link(workspaceId: str, fromId: str, toId: str, role: str) -> dict[str, Any]:
    """Create a typed reference link `fromId --role--> toId`: a directed edge between two pages beyond
    the parent/child tree, listed in the source page's 'References' section. The source must be
    non-archived; the target may be archived. Rejects a self-link, an empty role, and a duplicate
    (toId, role) edge."""
    with _guard_tool():
        page, links = STORE.link_page(workspaceId, fromId, toId, role)
        await ws_reloader.refresh()
        return {"id": page.id, "links": links}


@mcp.tool
async def unlink(workspaceId: str, fromId: str, toId: str, role: str) -> dict[str, Any]:
    """Remove the typed reference link `fromId --role--> toId`. Rejects a missing endpoint, an
    archived source, or an edge that isn't present."""
    with _guard_tool():
        page, links = STORE.unlink_page(workspaceId, fromId, toId, role)
        await ws_reloader.refresh()
        return {"id": page.id, "links": links}


# --- capture HMR reload errors to hmr_debug.log (see src/_hmr_debug.py) -------
from . import _hmr_debug  # noqa: E402, F401
