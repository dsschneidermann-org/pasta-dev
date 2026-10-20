"""Integration tests for the FastAPI HTML routes (src.server web layer).

The routes resolve the module-global STORE at call time, so the fixture repoints it at a
per-test temp store (same pattern as the MCP tests).

The generic web-render tests use the test-fields fixture. The model-toggle tests keep a production
type (architecture): the toggle points at that page type's generated Sphinx doc, and only
production types are documentable - a fixture has no doc to link to.
"""

import colorsys
import re

import pytest
from fastapi.testclient import TestClient

import src.server as server
from src.errors import ValidationError
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


# --- Pink palette ------------------------------------------------------------
# The web UI's theme is water.css's colour custom properties, redefined per theme in the
# overrides sheet. These pin that each theme reads as pink and keeps its text readable.

_TEXT_COLOURS = ("--text-main", "--text-bright", "--text-muted", "--links", "--code", "--text-error")
_SURFACES = ("--background-body", "--background", "--background-alt")


def _theme_palette(css: str, theme: str) -> dict[str, str]:
    """Custom properties a theme defines in the overrides sheet: the declarations of the
    ':root:has(> body.<theme>)' block, then of the 'body.<theme>' block, later winning."""
    palette: dict[str, str] = {}
    for selector in (f":root:has(> body.{theme})", f"body.{theme}"):
        block = re.search(rf"^{re.escape(selector)}\s*\{{(.*?)\}}", css, re.MULTILINE | re.DOTALL)
        if block:
            palette.update(re.findall(r"(--[\w-]+)\s*:\s*([^;]+?)\s*;", block.group(1)))
    return palette


def _rgb(colour: str) -> tuple[float, float, float]:
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", colour), f"{colour} is not #rrggbb"
    red, green, blue = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return red, green, blue


def _contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two '#rrggbb' colours."""
    def luminance(colour: str) -> float:
        red, green, blue = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                            for c in _rgb(colour))
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _hue(colour: str) -> float | None:
    """HSL hue in degrees [0, 360) of a '#rrggbb' colour, None for a grey with no hue."""
    hue, _, saturation = colorsys.rgb_to_hls(*_rgb(colour))
    return hue * 360 if saturation else None


def test_palette_helpers_measure_known_colours():
    assert _contrast_ratio("#000000", "#ffffff") == pytest.approx(21)
    assert _contrast_ratio("#ffffff", "#000000") == pytest.approx(21)   # order-independent
    assert _contrast_ratio("#777777", "#777777") == pytest.approx(1)
    assert _hue("#ff0000") == pytest.approx(0)
    assert _hue("#ff00ff") == pytest.approx(300)
    assert _hue("#808080") is None
    css = ":root:has(> body.dark) {\n  --links: #111111;\n  --code: #222222;\n}\nbody.dark {\n  --code: #333333;\n}\n"
    assert _theme_palette(css, "dark") == {"--links": "#111111", "--code": "#333333"}
    assert _theme_palette(css, "light") == {}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_each_theme_has_a_pink_palette(client, theme):
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    palette = _theme_palette(response.text, theme)
    for prop in ("--background-body", "--links"):
        hue = _hue(palette[prop])
        assert hue is not None and 300 <= hue <= 350, f"{theme} {prop} {palette[prop]} is not pink"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_each_theme_keeps_text_legible(client, theme):
    palette = _theme_palette(client.get("/static/styles.css").text, theme)
    pairs = [(text, surface) for text in _TEXT_COLOURS for surface in _SURFACES]
    pairs += [("--form-text", "--button-base"), ("--form-text", "--button-hover")]
    for foreground, background in pairs:
        ratio = _contrast_ratio(palette[foreground], palette[background])
        assert ratio >= 4.5, f"{theme} {foreground} on {background} is {ratio:.2f}:1"
