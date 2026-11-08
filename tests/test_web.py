"""Integration tests for the FastAPI HTML routes (src.server web layer).

The routes resolve the module-global STORE at call time, so the fixture repoints it at a
per-test temp store (same pattern as the MCP tests).

The generic web-render tests use the test-fields fixture. The model-toggle tests keep a production
type (architecture): the toggle points at that page type's generated Sphinx doc, and only
production types are documentable - a fixture has no doc to link to.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.server as server
from src.errors import ValidationError
from src.source_link import SourceLink, read_remote_url, to_source_link
from src.store import Store


@pytest.fixture
def client(tmp_path):
    server.STORE = Store(tmp_path)
    return TestClient(server.app)


def test_index_lists_workspaces(client):
    workspace = server.STORE.create_workspace("demo")
    response = client.get("/")
    assert response.status_code == 200
    assert "demo" in response.text
    assert f"/{workspace.id}" in response.text            # link to the workspace tree page


def test_tree_route_links_pages_workspace_scoped(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}")
    assert response.status_code == 200
    assert "Page title" in response.text
    assert f"/{workspace.id}/page/{page.id}" in response.text   # workspace-scoped /page link


def test_page_view_renders_body_and_sidebar(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    server.STORE.mutate_page_batch(workspace.id, page.id, [
        {"command": "setBody", "args": {"statusRevisionToken": page.status_revision_token, "text": "The body."}}
    ])
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert "The body." in response.text             # the rendered page body
    assert 'id="sidebar"' in response.text               # the nav sidebar layout


def test_page_view_has_model_toggle_to_page_type_doc(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert 'id="show-model"' in response.text                            # the Model toggle button
    # The iframe points at THIS page's type-AND-state doc (a new test-fields page is `current`),
    # and defers loading via data-src (not src).
    assert 'data-src="/sphinx/page-types/test-fields-active.html"' in response.text
    assert 'id="model-view"' in response.text and "<iframe" in response.text


def test_model_toggle_absent_on_index_and_tree(client):
    # The toggle lives in _nav.html (page view only), never in _base.html-derived views.
    workspace = server.STORE.create_workspace("demo")
    server.STORE.create_page(workspace.id, "test-fields", "Page title")
    part = workspace.id.removeprefix("ws:")
    assert 'id="show-model"' not in client.get("/").text                 # workspace index
    assert 'id="show-model"' not in client.get(f"/ws:{part}").text       # workspace tree


def test_page_view_shows_archive_button(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert "Archive page" in response.text                              # not-yet-archived label
    assert f'action="/{workspace.id}/page/{page.id}/archive"' in response.text


def test_archive_route_archives_and_flips_button(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")

    # POST the Archive button -> 303 redirect -> archived view (TestClient follows the redirect).
    response = client.post(f"/ws:{part}/page/{page.id}/archive")
    assert response.status_code == 202
    assert server.STORE.get_page(workspace.id, page.id).archived is True


def test_unarchive_route_restores_page(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    server.STORE.archive_page(workspace.id, page.id)
    part = workspace.id.removeprefix("ws:")

    response = client.post(f"/ws:{part}/page/{page.id}/unarchive")
    assert response.status_code == 202
    assert server.STORE.get_page(workspace.id, page.id).archived is False


def test_page_view_shows_set_to_delete_button(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")

    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert "Set to delete" in response.text                             # not-yet-scheduled label
    assert f'action="/{workspace.id}/page/{page.id}/schedule-delete"' in response.text


def test_page_view_button_flips_to_cancel_delete_when_scheduled(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    server.STORE.schedule_page_deletion(workspace.id, page.id)

    # No archived=true needed: the page route resolves through get_page, which does not
    # filter on archived - only the tree and search views apply the subtree rule.
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert "Cancel delete" in response.text
    assert f'action="/{workspace.id}/page/{page.id}/unschedule-delete"' in response.text


def test_schedule_delete_route_schedules_and_archives(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")

    response = client.post(f"/ws:{part}/page/{page.id}/schedule-delete")
    assert response.status_code == 202
    stored = server.STORE.get_page(workspace.id, page.id)
    assert stored.delete_scheduled is True
    assert stored.archived is True


def test_unschedule_delete_route_cancels_but_keeps_the_page_archived(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    server.STORE.schedule_page_deletion(workspace.id, page.id)

    response = client.post(f"/ws:{part}/page/{page.id}/unschedule-delete")
    assert response.status_code == 202
    stored = server.STORE.get_page(workspace.id, page.id)
    assert stored.delete_scheduled is False
    assert stored.archived is True


def test_page_view_shows_state_dropdown_next_to_archive(client):
    # test-flow's FSM is draft -> open -> closed; a fresh page is `draft`.
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    # The dropdown posts to the new /status route and offers every FSM state, current one selected.
    assert f'action="/{workspace.id}/page/{page.id}/status"' in response.text
    assert 'id="status-select"' in response.text and 'name="status"' in response.text
    assert 'value="draft" selected' in response.text          # current state preselected
    assert 'value="open"' in response.text and 'value="closed"' in response.text


def test_state_dropdown_absent_on_index_and_tree(client):
    # Like the Archive/Model controls, the dropdown lives only in the single-page view.
    workspace = server.STORE.create_workspace("demo")
    server.STORE.create_page(workspace.id, "test-flow", "Page title")
    part = workspace.id.removeprefix("ws:")
    assert 'id="status-select"' not in client.get("/").text
    assert 'id="status-select"' not in client.get(f"/ws:{part}").text


def test_status_route_sets_state_bypassing_fsm(client):
    # draft -> closed is NOT a single legal FSM transition (draft -> open -> closed); the direct
    # override sets it anyway, proving it bypasses the modelled transition guards.
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    assert page.status == "draft"
    part = workspace.id.removeprefix("ws:")

    response = client.post(f"/ws:{part}/page/{page.id}/status", data={"status": "closed"})
    assert response.status_code == 202
    assert server.STORE.get_page(workspace.id, page.id).status == "closed"


def test_set_page_status_rejects_unknown_state(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    with pytest.raises(ValidationError):
        server.STORE.set_page_status(workspace.id, page.id, "not-a-state")


def test_reloader_websocket_sends_refresh(client):
    with client.websocket_connect("/ws/reloader") as websocket:
        assert websocket.receive_json() == {"refresh": 0}   # heartbeat on connect


def test_responses_disable_caching(client):
    # No-cache is stamped by middleware, so it covers both HTML routes and - the real target -
    # the /static mount where image/asset files are served.
    assert client.get("/").headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_page_view_renders_the_structured_body(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    server.STORE.mutate_page_batch(workspace.id, page.id, [
        {"command": "setBody", "args": {"statusRevisionToken": page.status_revision_token, "text": "The body."}},
        {"command": "addItem", "args": {"statusRevisionToken": page.status_revision_token, "text": "Item one", "note": "a note"}},
    ])
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/page/{page.id}")
    assert response.status_code == 200
    assert '<article class="pasta-page">' in response.text
    assert "<dt>text</dt><dd><p>Item one</p></dd>" in response.text
    assert "<dt>note</dt><dd><p>a note</p></dd>" in response.text
    assert '<nav class="page-contents"' in response.text
    assert "The body." in response.text                 # the prose field still reaches the page
    assert 'id="sidebar"' in response.text              # the Markdown-rendered nav is untouched


def test_page_view_links_pinned_children_and_the_parent_from_the_top(client):
    workspace = server.STORE.create_workspace("demo")
    created = server.STORE.create_page(workspace.id, "test-lifecycle", "Brief")
    parent, child = created.page, created.children[0]
    part = workspace.id.removeprefix("ws:")
    link_mark = "&nbsp;\N{LINK SYMBOL}"

    def strip(page_id: str) -> str:
        text = client.get(f"/ws:{part}/page/{page_id}").text
        start = text.index('<nav class="page-contents"')
        return text[start:text.index("</nav>", start)]

    parent_strip, child_strip = strip(parent.id), strip(child.id)
    assert parent_strip.endswith('<a href="#section-children">Child pages</a>' +
                                 '<a href="#footer">Bottom</a>' +
                                 f'<a href="/{workspace.id}/page/{child.id}">Child fixture{link_mark}</a>')
    assert f"Parent{link_mark}" not in parent_strip
    assert child_strip.startswith('<nav class="page-contents" aria-label="Sections">' +
                                  f'<a href="/{workspace.id}/page/{parent.id}">Parent{link_mark}</a>')


_TOP_LINK = '<a id="to-top" href="#top">'


def test_every_view_carries_the_floating_top_link(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    for path in ("/", f"/{workspace.id}", f"/{workspace.id}/page/{page.id}"):
        response = client.get(path)
        assert response.status_code == 200
        assert _TOP_LINK in response.text


def test_the_refusal_page_carries_the_floating_top_link(client, invalid_declarations):
    response = client.get("/")
    assert response.status_code == 503
    assert _TOP_LINK in response.text


def test_top_link_style_takes_every_colour_from_both_water_css_sheets(client):
    # Literal colours read correctly in one theme only; both sheets must define each variable.
    rules = "".join(re.findall(r"#to-top(?::hover)?\s*\{([^}]*)\}", client.get("/static/styles.css").text))
    assert "position: fixed" in rules
    colours = re.findall(r"(?:^|[;\s])(?:color|background|border)\s*:\s*([^;]+);", rules)
    assert colours and all("var(--" in value for value in colours)
    names = {name for value in colours for name in re.findall(r"var\((--[a-z-]+)\)", value)}
    for theme in ("light", "dark"):
        sheet = client.get(f"/static/water.css/{theme}.min.css").text
        assert all(f"{name}:" in sheet for name in names)


# --- Declaration quarantine --------------------------------------------------
# The renderer iterates the spec, so an invalid declaration still renders a plausible page - one
# quietly missing the deleted field, on a tab the reloader has just called current. These pin the
# refusal that replaces it.

def test_a_page_is_refused_while_a_page_type_declaration_is_invalid(client, invalid_declarations):
    workspace = server.STORE.create_workspace("demo")
    response = client.get(f"/{workspace.id}")
    assert response.status_code == 503
    # The reason, not just a failure code. Asserted on the quoted names rather than the whole
    # message because the template escapes the quotes around them.
    assert "setPlatform" in response.text
    assert "report.platform" in response.text


def test_the_refusal_keeps_the_live_reload_socket_so_the_fix_lands_on_its_own(client, invalid_declarations):
    # The quarantine page is served through the ordinary error template, which carries the reloader
    # script. That is the whole recovery path: fix the file, the reload fires a refresh, and the
    # browser leaves the 503 by itself. A bare PlainTextResponse would strand it.
    response = client.get("/")
    assert response.status_code == 503
    assert "/ws/reloader" in response.text


def test_the_refusal_is_not_cached(client, invalid_declarations):
    # A cached 503 would outlive the fix and make the surface look permanently down.
    response = client.get("/")
    assert response.status_code == 503
    assert "no-store" in response.headers["cache-control"]


def test_pages_serve_normally_once_the_declarations_validate(client):
    # No lingering quarantine on the HTTP side either.
    server.STORE.create_workspace("demo")
    assert client.get("/").status_code == 200


NOTE = "AGPL software must be offered to its users as source code."


def test_footer_links_the_source_and_carries_the_agpl_note(client, monkeypatch):
    monkeypatch.setitem(server.templates.env.globals, "source_link",
                        SourceLink(href="https://example.com/o/r", text="example.com/o/r"))
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    for path in ("/", f"/ws:{part}", f"/ws:{part}/page/{page.id}"):
        response = client.get(path)
        assert 'Source: <a href="https://example.com/o/r">example.com/o/r</a>' in response.text
        assert NOTE in response.text


def test_footer_without_a_source_link_shows_only_the_note(client, monkeypatch):
    monkeypatch.setitem(server.templates.env.globals, "source_link", None)
    response = client.get("/")
    assert NOTE in response.text
    assert "Source:" not in response.text


def test_server_publishes_the_checkouts_source_link():
    src_dir = Path(server.__file__).resolve().parent
    assert server.templates.env.globals["source_link"] == to_source_link(read_remote_url(src_dir))


def test_footer_link_is_muted_without_an_underline(client):
    css = client.get("/static/styles.css").text
    assert "#footer a { color: var(--text-muted); text-decoration: none; }" in css
    assert "#footer a:hover { color: var(--links); }" in css
