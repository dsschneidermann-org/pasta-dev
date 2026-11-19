"""Integration tests for the FastAPI HTML routes (src.server web layer).

The routes resolve the module-global STORE at call time, so the fixture repoints it at a
per-test temp store (same pattern as the MCP tests).

The generic web-render tests use the test-fields fixture. The model-toggle tests keep a production
type (architecture): the toggle points at that page type's generated Sphinx doc, and only
production types are documentable - a fixture has no doc to link to.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.server as server
from src.errors import ValidationError
from src.event_log import to_jsonl
from src.serialize import workspace_to_dict
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


def test_sidebar_workspace_link_keeps_the_archived_view(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    workspace_link = '<a href="/{}"><strong>Workspace</strong></a>'
    shown = client.get(f"/ws:{part}/page/{page.id}?archived=true").text
    assert f'<a href="/{workspace.id}/page/{page.id}?archived=true">' in shown   # tree links keep it
    assert workspace_link.format(f"{workspace.id}?archived=true") in shown
    hidden = client.get(f"/ws:{part}/page/{page.id}").text
    assert workspace_link.format(workspace.id) in hidden


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


def _shipped_feature_log(workspace_id: str) -> None:
    page_id = "feature-brief:mrw7chrt-def44a"
    server.STORE.events_path(workspace_id).write_text(to_jsonl([
        {"at": "2026-07-22T14:53:00+00:00", "event": "created", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "draft"},
        {"at": "2026-07-22T16:20:00+00:00", "event": "status", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "shipped", "from": "draft"},
    ]), encoding="utf-8")


def test_events_socket_catches_up_on_connect(client):
    workspace = server.STORE.create_workspace("demo")
    _shipped_feature_log(workspace.id)
    with client.websocket_connect(f"/ws/events/{workspace.id}?since=0") as websocket:
        caught_up = websocket.receive_json()
        assert [event["event"] for event in caught_up["events"]] == ["created", "status"]
        assert len(caught_up["timeline"]["lines"]) == 1
        assert websocket.receive_json() == {"events": []}    # then the heartbeat
    assert server.ws_events.active == []                     # a closed tab stops watching


def test_events_socket_sends_heartbeats_when_up_to_date(client):
    workspace = server.STORE.create_workspace("demo")
    _shipped_feature_log(workspace.id)
    with client.websocket_connect(f"/ws/events/{workspace.id}?since=2") as websocket:
        assert websocket.receive_json() == {"events": []}


def test_events_socket_of_an_unknown_workspace_stays_open_on_heartbeats(client):
    with client.websocket_connect("/ws/events/ws:nope-000000") as websocket:
        assert websocket.receive_json() == {"events": []}


def test_a_status_write_streams_its_event_to_a_watching_tab(client, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")     # entering the client runs the app's lifespan
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    seen = len(server.STORE.read_events(workspace.id))
    part = workspace.id.removeprefix("ws:")
    # Entered, the client shares one event loop between its requests and its sockets, so the
    # POST publishes on the loop the socket lives on.
    with TestClient(server.app) as live, \
            live.websocket_connect(f"/ws/events/{workspace.id}?since={seen}") as websocket:
        assert websocket.receive_json() == {"events": []}
        assert live.post(f"/ws:{part}/page/{page.id}/status", data={"status": "open"}).status_code == 202
        streamed = websocket.receive_json()
    [event] = streamed["events"]
    assert (event["event"], event["pageId"], event["from"], event["status"]) == ("status", page.id, "draft", "open")
    assert streamed["timeline"]["lines"] == []          # a fixture type is logged but draws no line


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


def test_a_page_is_refused_after_a_failed_reload(client, failed_reload):
    response = client.get("/")
    assert response.status_code == 503
    assert "DECOMPOSITION" in response.text


def test_the_reload_refusal_keeps_the_live_reload_socket_and_is_not_cached(client, failed_reload):
    response = client.get("/")
    assert response.status_code == 503
    assert "/ws/reloader" in response.text
    assert "no-store" in response.headers["cache-control"]


def test_static_assets_are_served_after_a_failed_reload(client, failed_reload):
    assert client.get("/static/styles.css").status_code == 200


def test_footer_links_the_source_and_carries_the_agpl_note(client, monkeypatch):
    monkeypatch.setitem(server.templates.env.globals, "source_link",
                        SourceLink(href="https://example.com/o/r", text="example.com/o/r"))
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    for path in ("/", f"/ws:{part}", f"/ws:{part}/page/{page.id}"):
        response = client.get(path)
        assert 'href="https://example.com/o/r"' in response.text
        assert "AGPL" in response.text


def test_footer_without_a_source_link_shows_only_the_note(client, monkeypatch):
    monkeypatch.setitem(server.templates.env.globals, "source_link", None)
    response = client.get("/")
    assert "AGPL" in response.text
    assert "Source:" not in response.text


def test_server_publishes_the_checkouts_source_link():
    src_dir = Path(server.__file__).resolve().parent
    assert server.templates.env.globals["source_link"] == to_source_link(read_remote_url(src_dir))


# --- timeline view -----------------------------------------------------------------------------

def _timeline_data(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="timeline-data"[^>]*>(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_timeline_replays_the_workspace_log_without_the_live_reload_socket(client):
    workspace = server.STORE.create_workspace("demo")
    page_id = "feature-brief:mrw7chrt-def44a"
    server.STORE.events_path(workspace.id).write_text(to_jsonl([
        {"at": "2026-07-22T14:53:00+00:00", "event": "created", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "draft"},
        {"at": "2026-07-22T16:20:00+00:00", "event": "status", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "shipped", "from": "draft"},
    ]), encoding="utf-8")
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/timeline")
    assert response.status_code == 200
    [line] = _timeline_data(response.text)["lines"]
    assert (line["id"], line["end"], line["title"]) == (page_id, "delivered", "Anchored insert")
    assert "/ws/reloader" not in response.text
    assert '<p class="tl-empty" id="tl-empty" hidden>' in response.text
    assert '<div id="tl-live">' in response.text


def test_timeline_page_carries_its_event_count_for_the_live_socket(client):
    workspace = server.STORE.create_workspace("demo")
    _shipped_feature_log(workspace.id)
    html = client.get(f"/ws:{workspace.id.removeprefix('ws:')}/timeline").text
    assert re.search(r'<script type="application/json" id="timeline-data"[^>]*data-events="2"', html)


def test_timeline_times_sit_on_the_page_background_and_the_legend_checks_delivered(client):
    workspace = server.STORE.create_workspace("demo")
    page_id = "bug-report:mrw7chrt-def44a"
    server.STORE.events_path(workspace.id).write_text(to_jsonl([
        {"at": "2026-07-22T14:53:00+00:00", "event": "created", "pageId": page_id,
         "type": "bug-report", "title": "A bug", "status": "draft"},
    ]), encoding="utf-8")
    html = client.get(f"/ws:{workspace.id.removeprefix('ws:')}/timeline").text
    assert ".timeline time { background: var(--background-body); }" in html
    assert re.search(r'<li><svg[^>]*><circle class="tl-delivered"[^>]*/><path class="tl-check"', html)


def test_timeline_play_button_is_plain_text_and_feed_rows_are_bordered_only_between(client):
    workspace = server.STORE.create_workspace("demo")
    page_id = "bug-report:mrw7chrt-def44a"
    server.STORE.events_path(workspace.id).write_text(to_jsonl([
        {"at": "2026-07-22T14:53:00+00:00", "event": "created", "pageId": page_id,
         "type": "bug-report", "title": "A bug", "status": "draft"},
    ]), encoding="utf-8")
    html = client.get(f"/ws:{workspace.id.removeprefix('ws:')}/timeline").text
    assert '<button type="button" id="tl-play">Play</button>' in html
    assert ".tl-feed li + li { border-top: 1px solid var(--border); }" in html


def test_timeline_of_a_workspace_with_no_log_says_so_and_waits_for_its_first_event(client):
    workspace = server.STORE.create_workspace("demo")
    part = workspace.id.removeprefix("ws:")
    response = client.get(f"/ws:{part}/timeline")
    assert response.status_code == 200
    assert '<p class="tl-empty" id="tl-empty">No page events are recorded yet' in response.text
    assert '<div id="tl-live" hidden>' in response.text
    assert _timeline_data(response.text)["lines"] == []     # drawn by the script once events stream in
    assert 'data-events="0"' in response.text


def test_workspace_tree_links_to_its_timeline(client):
    workspace = server.STORE.create_workspace("demo")
    response = client.get(f"/{workspace.id}")
    assert f'href="/{workspace.id}/timeline"' in response.text
    assert "/ws/reloader" in response.text                     # the other views keep live reload


def test_timeline_of_an_unknown_workspace_is_an_error_page(client):
    response = client.get("/ws:nope-000000/timeline")
    assert response.status_code == 500


# --- guidance view -----------------------------------------------------------------------------

def test_workspace_tree_links_to_its_guidance_next_to_the_timeline(client):
    workspace = server.STORE.create_workspace("demo")
    response = client.get(f"/{workspace.id}")
    assert re.search(rf'href="/{workspace.id}/timeline">Timeline</a>\s*·\s*'
                     rf'<a href="/{workspace.id}/guidance">Guidance</a>', response.text)


def test_guidance_lists_every_declared_field_with_its_description_and_text(client):
    workspace = server.STORE.create_workspace("demo")
    server.STORE.set_workspace_guidance(workspace.id, "buildTool", "use pytest")
    response = client.get(f"/{workspace.id}/guidance")
    assert response.status_code == 200
    for field in server.STORE.get_workspace_guidance(workspace.id)["fields"]:
        assert field["field"] in response.text
        assert field["description"] in response.text
    assert "use pytest" in response.text
    assert response.text.count("Not set") == 2                # draftHint and reviewHint are unset


def test_guidance_names_are_bold_descriptions_italic_and_values_spaced(client):
    workspace = server.STORE.create_workspace("demo")
    html = client.get(f"/{workspace.id}/guidance").text
    assert "<strong>buildTool</strong> - <em>the build tool this workspace uses</em>" in html
    assert "<code>" not in html
    assert ".guidance dd { margin-top: 0.5rem; margin-bottom: 1.75rem; }" in html


def test_guidance_shows_stored_text_of_an_undeclared_field(client):
    workspace = server.STORE.create_workspace("demo")
    stored = server.STORE.load_workspace(workspace.id)
    stored.guidance_config["retiredField"] = "old rule"
    server.STORE._touch_and_save(stored)
    response = client.get(f"/{workspace.id}/guidance")
    assert "retiredField" in response.text
    assert "old rule" in response.text


def test_guidance_text_is_escaped(client):
    workspace = server.STORE.create_workspace("demo")
    server.STORE.set_workspace_guidance(workspace.id, "buildTool", "<script>alert(1)</script>")
    response = client.get(f"/{workspace.id}/guidance")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_guidance_keeps_the_live_reload_socket(client):
    workspace = server.STORE.create_workspace("demo")
    response = client.get(f"/{workspace.id}/guidance")
    assert "/ws/reloader" in response.text


def test_guidance_view_does_not_write(client):
    workspace = server.STORE.create_workspace("demo")
    server.STORE.set_workspace_guidance(workspace.id, "buildTool", "use pytest")
    before = workspace_to_dict(server.STORE.load_workspace(workspace.id))
    _ = client.get(f"/{workspace.id}/guidance")
    assert workspace_to_dict(server.STORE.load_workspace(workspace.id)) == before


def test_guidance_of_an_unknown_workspace_is_an_error_page(client):
    response = client.get("/ws:nope-000000/guidance")
    assert response.status_code == 500
