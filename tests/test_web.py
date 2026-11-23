"""Integration tests for the FastAPI HTML routes (src.server web layer).

The routes resolve the module-global STORE at call time, so the fixture repoints it at a
per-test temp store (same pattern as the MCP tests).

The generic web-render tests use the test-fields fixture. The model-toggle tests keep a production
type (architecture): the toggle points at that page type's generated Sphinx doc, and only
production types are documentable - a fixture has no doc to link to.
"""

import asyncio
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.server as server
from src.errors import ValidationError
from src.event_log import to_jsonl
from src.live_digest import items_digest
from src.live_sockets import ActivityConnectionManager
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

    # POST the Archive button -> 303 back to the page, so the browser loads it again with a GET.
    response = client.post(f"/ws:{part}/page/{page.id}/archive", follow_redirects=False)
    assert response.status_code == 303
    assert server.STORE.get_page(workspace.id, page.id).archived is True


def test_a_page_action_post_redirects_back_to_the_page_and_updates_open_tabs(client, monkeypatch):
    sent = []

    async def record_update():
        sent.append("update")

    async def record_reload():
        sent.append("reload")

    monkeypatch.setattr(server.ws_reloader, "update", record_update)
    monkeypatch.setattr(server.ws_reloader, "reload", record_reload)
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    view = f"http://testserver/ws:{part}/page/{page.id}?archived=true"
    response = client.post(f"/ws:{part}/page/{page.id}/archive", headers={"referer": view},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/ws:{part}/page/{page.id}?archived=true"
    assert sent == ["update"]


def test_a_page_action_returns_to_the_page_view_it_was_posted_from():
    page = "/ws:demo/page/test-fields:p1"
    assert server.page_view_after_action("demo", "test-fields:p1", f"http://host{page}?archived=true") == \
        f"{page}?archived=true"
    assert server.page_view_after_action("demo", "test-fields:p1", f"http://host{page}?markdown=true&archived=true") == \
        f"{page}?markdown=true&archived=true"
    assert server.page_view_after_action("demo", "test-fields:p1", f"http://host{page}") == page


def test_a_page_action_never_returns_anywhere_but_its_own_page():
    page = "/ws:demo/page/test-fields:p1"
    assert server.page_view_after_action("demo", "test-fields:p1", None) == page
    assert server.page_view_after_action("demo", "test-fields:p1", "http://host/ws:demo/page/test-fields:p2") == page
    assert server.page_view_after_action("demo", "test-fields:p1", "https://elsewhere.example/?next=/") == page


def test_unarchive_route_restores_page(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    server.STORE.archive_page(workspace.id, page.id)
    part = workspace.id.removeprefix("ws:")

    response = client.post(f"/ws:{part}/page/{page.id}/unarchive", follow_redirects=False)
    assert response.status_code == 303
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

    response = client.post(f"/ws:{part}/page/{page.id}/schedule-delete", follow_redirects=False)
    assert response.status_code == 303
    stored = server.STORE.get_page(workspace.id, page.id)
    assert stored.delete_scheduled is True
    assert stored.archived is True


def test_unschedule_delete_route_cancels_but_keeps_the_page_archived(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    part = workspace.id.removeprefix("ws:")
    server.STORE.schedule_page_deletion(workspace.id, page.id)

    response = client.post(f"/ws:{part}/page/{page.id}/unschedule-delete", follow_redirects=False)
    assert response.status_code == 303
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

    response = client.post(f"/ws:{part}/page/{page.id}/status", data={"status": "closed"}, follow_redirects=False)
    assert response.status_code == 303
    assert server.STORE.get_page(workspace.id, page.id).status == "closed"


def test_set_page_status_rejects_unknown_state(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    with pytest.raises(ValidationError):
        server.STORE.set_page_status(workspace.id, page.id, "not-a-state")


def test_reloader_websocket_sends_a_heartbeat(client):
    with client.websocket_connect("/ws/reloader") as websocket:
        assert websocket.receive_json() == {"heartbeat": 1}   # on connect, then every 5 s


def test_the_vendored_morph_library_is_served_locally(client):
    response = client.get("/static/idiomorph/idiomorph.min.js")
    assert response.status_code == 200
    assert "Idiomorph" in response.text


def test_the_reloader_updates_in_place_on_a_data_change(client):
    text = client.get("/").text
    assert "data.reload === 1" in text
    assert "data.update === 1" in text
    assert "fetch(location.href" in text
    assert "Idiomorph.morph(document.body, fetched.body.childNodes" in text
    assert 'morphStyle: "innerHTML"' in text
    assert "beforeAttributeUpdated" in text


def test_a_live_view_loads_the_morph_library_before_the_reloader(client):
    text = client.get("/").text
    assert '<script src="/static/idiomorph/idiomorph.min.js"></script>' in text
    assert text.index("/static/idiomorph/idiomorph.min.js") < text.index("/ws/reloader")


def test_the_theme_choice_is_kept_out_of_the_morph(client):
    text = client.get("/").text
    assert 'id="theme-light" data-morph-keep="checked"' in text
    assert 'id="theme-dark" data-morph-keep="checked"' in text


def test_the_view_toggle_state_is_kept_out_of_the_morph(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-fields", "Page title").page
    text = client.get(f"/ws:{workspace.id.removeprefix('ws:')}/page/{page.id}").text
    assert 'id="show-page" data-morph-keep="aria-pressed"' in text
    assert 'id="show-model" data-morph-keep="aria-pressed"' in text
    assert 'id="view-body" data-morph-keep="class"' in text
    assert 'id="model-view" data-morph-keep="src hidden"' in text
    assert 'modelView.getAttribute("src") !== modelView.dataset.src' in text


def _shipped_feature_log(workspace_id: str) -> None:
    page_id = "feature-brief:mrw7chrt-def44a"
    server.STORE.events_path(workspace_id).write_text(to_jsonl([
        {"at": "2026-07-22T14:53:00+00:00", "event": "created", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "draft"},
        {"at": "2026-07-22T16:20:00+00:00", "event": "status", "pageId": page_id,
         "type": "feature-brief", "title": "Anchored insert", "status": "shipped", "from": "draft"},
    ]), encoding="utf-8")


def _next_live(websocket):
    # The heartbeat and a round's payload are sent independently, so either may come first.
    for _ in range(3):
        message = websocket.receive_json()
        if "timeline" in message:
            return message
    raise AssertionError("no timeline arrived")


def test_an_events_tab_behind_the_log_is_sent_the_rebuilt_timeline_on_connect(client, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")     # entering the client runs the app's lifespan
    workspace = server.STORE.create_workspace("demo")
    _shipped_feature_log(workspace.id)
    # Entered, the client shares one event loop between its requests and its sockets, so the round a
    # connect starts runs on the loop the socket lives on.
    with TestClient(server.app) as live, \
            live.websocket_connect(f"/ws/events/{workspace.id}?digest=stale") as websocket:
        message = _next_live(websocket)
    assert message["digest"] == items_digest(server.STORE.read_events(workspace.id))
    assert len(message["timeline"]["lines"]) == 1
    assert server.ws_events.active == []                     # a closed tab stops watching


def test_an_events_tab_drawn_from_the_current_log_is_sent_nothing_until_a_write_changes_it(client, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    rendered = items_digest(server.STORE.read_events(workspace.id))
    part = workspace.id.removeprefix("ws:")
    with TestClient(server.app) as live, \
            live.websocket_connect(f"/ws/events/{workspace.id}?digest={rendered}") as websocket:
        assert websocket.receive_json() == {"heartbeat": 1}
        posted = live.post(f"/ws:{part}/page/{page.id}/status", data={"status": "open"}, follow_redirects=False)
        assert posted.status_code == 303
        message = _next_live(websocket)
    # Had the connect re-sent what the tab was drawn from, this would carry the rendered digest.
    assert message["digest"] == items_digest(server.STORE.read_events(workspace.id)) != rendered
    assert message["timeline"]["lines"] == []          # a fixture type is logged but draws no line


def test_events_socket_of_an_unknown_workspace_stays_open_on_heartbeats(client):
    with client.websocket_connect("/ws/events/ws:nope-000000") as websocket:
        assert websocket.receive_json() == {"heartbeat": 1}


def _recent_call(page_id, tool="getPage"):
    return {"at": datetime.now(timezone.utc).isoformat(), "kind": "call", "pageId": page_id, "tool": tool,
            "write": False, "bytes": 10}


def _next_timeline(websocket):
    return _next_live(websocket)["timeline"]


def test_the_activity_socket_sends_its_page_s_timeline_on_connect(client, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")     # entering the client runs the app's lifespan
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page").page
    server.STORE.create_page(workspace.id, "test-flow", "Other")
    server.STORE.append_activity(workspace.id, [_recent_call(page.id)])
    with TestClient(server.app) as live, \
            live.websocket_connect(f"/ws/activity/{workspace.id}?page={page.id}") as websocket:
        timeline = _next_timeline(websocket)
    assert [line["id"] for line in timeline["lines"]] == [page.id]
    assert [mark["kind"] for mark in timeline["lines"][0]["marks"]] == ["created", "call"]
    assert server.ws_activity.active == []                  # a closed tab stops watching


def test_a_status_change_in_the_browser_streams_to_a_watching_activity_tab(client, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page title").page
    part = workspace.id.removeprefix("ws:")
    with TestClient(server.app) as live, live.websocket_connect(f"/ws/activity/{workspace.id}") as websocket:
        _next_timeline(websocket)                              # the catch-up on connect
        posted = live.post(f"/ws:{part}/page/{page.id}/status", data={"status": "open"}, follow_redirects=False)
        assert posted.status_code == 303
        timeline = _next_timeline(websocket)
    [line] = timeline["lines"]
    assert [(mark["kind"], mark["status"]) for mark in line["marks"]] == [("created", "draft"), ("status", "open")]


def test_an_activity_socket_of_an_unknown_workspace_stays_open_on_heartbeats(client):
    with client.websocket_connect("/ws/activity/ws:nope-000000") as websocket:
        assert websocket.receive_json() == {"heartbeat": 1}


class _Tab:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)


def _publish_burst(monkeypatch, during_rebuild: int, before_rebuild: int = 1):
    """Ask for publishes before a rebuild starts and while it runs; return the rebuilds and what the tab got."""
    builds, release = [], threading.Event()

    def build(workspace_id, scopes):
        builds.append(workspace_id)
        _ = release.wait(5)
        return {scope: {"lines": []} for scope in scopes}
    monkeypatch.setattr(server, "_activity_payloads", build)
    manager, tab = ActivityConnectionManager(), _Tab()
    monkeypatch.setattr(server, "ws_activity", manager)

    async def run():
        await manager.connect(tab, "ws:a", None)  # pyright: ignore[reportArgumentType]
        for _ in range(before_rebuild):
            server.schedule_activity_publish("ws:a")
        while not builds:
            await asyncio.sleep(0.01)              # the first rebuild is under way
        for _ in range(during_rebuild):
            server.schedule_activity_publish("ws:a")
        release.set()
        while server._activity_tasks:
            await asyncio.gather(*list(server._activity_tasks))
    asyncio.run(run())
    return builds, tab.sent


def test_publishes_asked_for_before_a_rebuild_starts_share_it(monkeypatch):
    builds, sent = _publish_burst(monkeypatch, during_rebuild=0, before_rebuild=5)
    assert builds == ["ws:a"] and sent == [{"timeline": {"lines": []}}]


def test_publishes_asked_for_while_a_rebuild_runs_cost_exactly_one_more(monkeypatch):
    builds, sent = _publish_burst(monkeypatch, during_rebuild=4)
    assert builds == ["ws:a", "ws:a"] and len(sent) == 2


def test_nothing_is_rebuilt_while_no_tab_watches(monkeypatch):
    monkeypatch.setattr(server, "ws_activity", ActivityConnectionManager())
    monkeypatch.setattr(server, "_activity_payloads", lambda *args: pytest.fail("rebuilt with no tab watching"))

    async def run():
        server.schedule_activity_publish("ws:a")
        return set(server._activity_tasks)
    assert asyncio.run(run()) == set()


def _activity(html: str) -> tuple[dict, str]:
    match = re.search(r'<script type="application/json" id="activity-data" data-workspace="[^"]*" '
                      r'data-page="([^"]*)">(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(2)), match.group(1)


def test_a_page_view_shows_the_activity_of_the_page_and_every_page_beneath_it(client):
    workspace = server.STORE.create_workspace("demo")
    parent = server.STORE.create_page(workspace.id, "test-flow", "Parent").page
    child = server.STORE.create_page(workspace.id, "test-flow", "Child", parent.id).page
    sibling = server.STORE.create_page(workspace.id, "test-flow", "Sibling").page
    server.STORE.append_activity(workspace.id, [_recent_call(child.id), _recent_call(sibling.id),
                                                _recent_call(None, "tree")])
    data, scope = _activity(client.get(f"/{workspace.id}/page/{parent.id}").text)
    assert scope == parent.id
    assert [line["id"] for line in data["lines"]] == [parent.id, child.id, workspace.id]


def test_the_workspace_index_shows_every_page_and_the_calls_that_name_none(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page").page
    server.STORE.append_activity(workspace.id, [_recent_call(None, "search")])
    data, scope = _activity(client.get(f"/{workspace.id}").text)
    assert scope == ""
    assert {line["id"]: line["colour"] for line in data["lines"]} == {page.id: "page", workspace.id: "workspace"}


def test_the_activity_sits_at_the_top_and_out_of_the_in_place_update(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page").page
    page_html = client.get(f"/{workspace.id}/page/{page.id}").text
    tree_html = client.get(f"/{workspace.id}").text
    for html in (page_html, tree_html):
        assert '<section id="activity" class="activity" data-morph-skip' in html
    assert page_html.index('id="page-view"') < page_html.index('id="activity"') < page_html.index('id="page-actions"')
    assert tree_html.index(">Guidance</a>") < tree_html.index('id="activity"')


def test_a_section_a_script_owns_is_left_out_of_the_in_place_update(client):
    workspace = server.STORE.create_workspace("demo")
    text = client.get(f"/{workspace.id}").text
    assert ('beforeNodeMorphed: (oldNode) => !(oldNode instanceof Element && oldNode.hasAttribute("data-morph-skip"))'
            in text)


def test_a_scope_with_nothing_in_the_last_day_says_so(client):
    workspace = server.STORE.create_workspace("demo")          # no pages, so nothing was logged
    html = client.get(f"/{workspace.id}").text
    assert '<p class="ac-empty" id="ac-empty">No activity in the last 24 hours.</p>' in html
    assert '<div id="ac-live" hidden>' in html


def test_activity_colours_are_theme_tokens_defined_for_both_themes():
    css = (Path(server.__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")
    for theme in ("body.light {", "body.dark {"):
        block = css[css.index(theme):]
        block = block[:block.index("}")]
        assert "--line-page:" in block and "--line-workspace:" in block
    section = css[css.index("/* Activity timeline"):]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", section)


def _activity_section(html: str) -> str:
    return html[html.index('<section id="activity"'):html.index("</section>")]


def test_the_latest_changes_start_hidden_behind_a_symbol_in_the_legend(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page").page
    section = _activity_section(client.get(f"/{workspace.id}/page/{page.id}").text)
    legend = section[section.index('<ul class="ac-legend">'):]
    legend = legend[:legend.index("</ul>")]
    assert ('<button type="button" class="ac-symbol" id="ac-feed-toggle" aria-expanded="false" '
            'aria-controls="ac-feed" aria-label="Show the latest changes" title="Latest changes">▸</button>') in legend
    assert '<ol class="ac-feed" id="ac-feed" hidden></ol>' in section and "<details" not in section
    assert '<ol class="tl-feed" id="tl-feed"></ol>' in client.get(f"/{workspace.id}/timeline").text


OPEN_LINK = ('<button type="button" class="ac-open" id="ac-open" aria-expanded="false" '
             'aria-controls="ac-body" data-morph-keep="hidden aria-expanded">Activity ▸</button>')


def test_the_index_puts_the_activity_link_in_its_top_line_after_guidance(client):
    workspace = server.STORE.create_workspace("demo")
    html = client.get(f"/{workspace.id}").text
    assert re.search(r'>Guidance</a>\s*<span class="ac-sep">·</span>\s*' + re.escape(OPEN_LINK), html)
    assert html.index(OPEN_LINK) < html.index('<section id="activity"')
    assert 'id="ac-open"' not in _activity_section(html)
    css = (Path(server.__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")
    assert ".ac-sep:has(+ #ac-open[hidden]) { display: none; }" in css


def test_the_activity_starts_collapsed_to_a_link_and_closes_from_a_symbol_after_the_caption(client):
    workspace = server.STORE.create_workspace("demo")
    page = server.STORE.create_page(workspace.id, "test-flow", "Page").page
    html = client.get(f"/{workspace.id}/page/{page.id}").text
    section = _activity_section(html)
    assert html.index(OPEN_LINK) < html.index('<section id="activity"')
    assert '<div id="ac-body" hidden>' in section
    assert re.search(r'<span class="ac-caption">Activity, last 24 hours</span>\s*'
                     r'<button type="button" class="ac-symbol" id="ac-close"', section)
    assert section.index('class="ac-controls"') < section.index('id="ac-empty"') < section.index('id="ac-live"')


def test_every_call_takes_one_symbol_and_one_legend_entry(client):
    workspace = server.STORE.create_workspace("demo")
    html = client.get(f"/{workspace.id}").text
    legend = html[html.index('<ul class="ac-legend">'):]
    legend = legend[:legend.index("</ul>")]
    assert legend.count('class="ac-call"') == 1 and ">Call</li>" in legend
    css = (Path(server.__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")
    assert "ac-write" not in html and "ac-write" not in css
    assert ".ac-call { stroke: var(--c); stroke-width: 3; }" in css


def test_every_time_both_timelines_show_is_24_hour():
    templates = Path(server.__file__).parent / "templates"
    for name in ("_activity.js", "_timeline.js"):
        source = (templates / name).read_text(encoding="utf-8")
        formats = re.findall(r"toLocale\w*String\(undefined, \{([^}]*)\}", source)
        with_hours = [options for options in formats if "hour" in options]
        assert with_hours and all('hourCycle: "h23"' in options for options in with_hours), name


def test_the_activity_play_button_matches_the_timeline_s_and_the_section_keeps_half_a_rem_below(client):
    css = (Path(server.__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")
    assert "#ac-play { min-width: 6.5rem; margin: 0; }" in css
    assert ".activity { margin: 0 0 0.5rem; }" in css
    workspace = server.STORE.create_workspace("demo")
    assert "#tl-play { min-width: 6.5rem; margin: 0; }" in client.get(f"/{workspace.id}/timeline").text


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
    assert "idiomorph" not in response.text
    assert '<p class="tl-empty" id="tl-empty" hidden>' in response.text
    assert '<div id="tl-live">' in response.text


def test_timeline_page_carries_the_digest_of_its_log_for_the_live_socket(client):
    workspace = server.STORE.create_workspace("demo")
    _shipped_feature_log(workspace.id)
    html = client.get(f"/ws:{workspace.id.removeprefix('ws:')}/timeline").text
    digest = items_digest(server.STORE.read_events(workspace.id))
    assert re.search(rf'<script type="application/json" id="timeline-data"[^>]*data-digest="{digest}"', html)


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
    assert f'data-digest="{items_digest([])}"' in response.text


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
