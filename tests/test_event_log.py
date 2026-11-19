"""Unit tests for the lifecycle event log's pure half (src.event_log): deriving the events a
write produced, and the JSONL encoding they are stored in."""

import json

from src.event_log import PageMark, lifecycle_events, page_marks, parse_jsonl, to_jsonl
from src.model import Page, Workspace

AT = "2026-11-18T10:00:00+00:00"


def _workspace(*pages: Page) -> Workspace:
    return Workspace(id="ws:x", name="x", pages={page.id: page for page in pages})


def _page(page_id: str, status: str = "draft", archived: bool = False) -> Page:
    return Page(id=page_id, type="feature-brief", title=f"Title of {page_id}", status=status,
                archived=archived)


def test_a_new_page_gives_one_created_event_with_its_current_status():
    workspace = _workspace(_page("a", status="open"))
    assert lifecycle_events({}, workspace, AT) == [{
        "at": AT, "event": "created", "pageId": "a", "type": "feature-brief",
        "title": "Title of a", "status": "open",
    }]


def test_a_moved_status_gives_a_status_event_naming_where_it_came_from():
    before = {"a": PageMark("draft", False)}
    [event] = lifecycle_events(before, _workspace(_page("a", status="grounding")), AT)
    assert event["event"] == "status"
    assert event["status"] == "grounding"
    assert event["from"] == "draft"


def test_a_flipped_archive_flag_gives_archived_and_unarchived():
    archived = lifecycle_events({"a": PageMark("draft", False)}, _workspace(_page("a", archived=True)), AT)
    restored = lifecycle_events({"a": PageMark("draft", True)}, _workspace(_page("a")), AT)
    assert [e["event"] for e in archived] == ["archived"]
    assert [e["event"] for e in restored] == ["unarchived"]


def test_a_page_whose_status_and_flag_both_moved_lists_the_status_first():
    before = {"a": PageMark("draft", False)}
    events = lifecycle_events(before, _workspace(_page("a", status="open", archived=True)), AT)
    assert [e["event"] for e in events] == ["status", "archived"]


def test_an_unchanged_workspace_gives_no_events():
    workspace = _workspace(_page("a"), _page("b", status="open", archived=True))
    assert lifecycle_events(page_marks(workspace), workspace, AT) == []


def test_a_page_gone_from_the_workspace_gives_no_event():
    before = {"a": PageMark("draft", False), "gone": PageMark("open", False)}
    assert lifecycle_events(before, _workspace(_page("a")), AT) == []


def test_page_marks_records_status_and_archived_per_page():
    workspace = _workspace(_page("a", status="open"), _page("b", archived=True))
    assert page_marks(workspace) == {"a": PageMark("open", False), "b": PageMark("draft", True)}


def test_jsonl_round_trips_non_ascii_titles_unescaped():
    events = [{"at": AT, "event": "created", "pageId": "a", "type": "bug-report",
               "title": "Café – résumé", "status": "draft"}]
    text = to_jsonl(events)
    assert "Café – résumé" in text
    assert text.endswith("\n") and text.count("\n") == 1
    assert parse_jsonl(text) == events


def test_parse_jsonl_skips_lines_it_cannot_use_and_keeps_the_rest_in_order():
    good_1 = {"at": AT, "event": "created", "pageId": "a"}
    good_2 = {"at": AT, "event": "status", "pageId": "b", "status": "open"}
    text = "\n".join([
        json.dumps(good_1),
        "",
        '{"at": "2026-11-18T10:00:00+00:00", "event": "sta',       # torn by an append in progress
        json.dumps([1, 2]),                                         # not an object
        json.dumps({"at": AT, "event": "created"}),                 # no pageId
        json.dumps({"at": AT, "event": "created", "pageId": 3}),    # pageId not a string
        json.dumps(good_2),
    ])
    assert parse_jsonl(text) == [good_1, good_2]
