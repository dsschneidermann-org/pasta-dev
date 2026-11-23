"""Unit tests for the activity timeline model (src.activity_timeline): which marks the last day of a
page's, or a workspace's, activity shows, and how they are laid out on the seconds-scale clock."""

from datetime import datetime, timezone

import pytest

from src.activity_timeline import ACTIVITY_RATE, build_activity_timeline
from src.model import Page, Workspace

NOW = datetime(2026, 11, 22, 12, tzinfo=timezone.utc).timestamp()


def _at(seconds_ago: float) -> str:
    return datetime.fromtimestamp(NOW - seconds_ago, timezone.utc).isoformat()


def _workspace() -> Workspace:
    # toc > feature > plan, and a sibling bug report beside the feature
    pages = {
        "toc": Page("toc", "toc", "Features", "active", child_ids=["feat", "other"]),
        "feat": Page("feat", "feature-brief", "Feature", "building", parent_id="toc", child_ids=["plan"]),
        "plan": Page("plan", "implementation-plan", "Plan", "draft", parent_id="feat"),
        "other": Page("other", "bug-report", "Other", "open", parent_id="toc"),
    }
    return Workspace("ws:w", "Demo", root_page_ids=["toc"], pages=pages)


def _call(page_id, seconds_ago, tool="getPage", write=False, size=100):
    return {"at": _at(seconds_ago), "kind": "call", "pageId": page_id, "tool": tool, "write": write, "bytes": size}


def _status(page_id, seconds_ago, status, page_type="feature-brief", title="Logged"):
    return {"at": _at(seconds_ago), "event": "status", "pageId": page_id, "type": page_type,
            "title": title, "status": status, "from": "x"}


def _ids(payload):
    return [line["id"] for line in payload["lines"]]


def test_a_page_shows_itself_and_every_page_beneath_it_but_not_its_siblings():
    entries = [_call("plan", 50), _call("other", 40), _call("feat", 30)]
    assert sorted(_ids(build_activity_timeline(entries, [], _workspace(), "toc", NOW))) == ["feat", "other", "plan"]
    assert sorted(_ids(build_activity_timeline(entries, [], _workspace(), "feat", NOW))) == ["feat", "plan"]


def test_a_page_missing_from_the_workspace_shows_only_its_own_activity():
    entries = [_call("gone", 20), _call("feat", 10)]
    payload = build_activity_timeline(entries, [], _workspace(), "gone", NOW)
    assert _ids(payload) == ["gone"]
    assert payload["lines"][0]["title"] == "gone"


def test_every_timeline_draws_the_calls_that_name_no_page_on_the_workspace_line_at_the_bottom():
    entries = [_call(None, 20, tool="search"), _call("feat", 10)]
    for scope in ("feat", None):
        lines = build_activity_timeline(entries, [], _workspace(), scope, NOW)["lines"]
        assert [line["id"] for line in lines] == ["feat", "ws:w"]
        workspace_line = lines[-1]
        assert (workspace_line["title"], workspace_line["colour"], workspace_line["href"]) == ("Demo", "workspace", "/ws:w")
        assert workspace_line["marks"][0]["tool"] == "search"


def test_only_the_last_24_hours_are_shown_status_changes_included():
    payload = build_activity_timeline([_call("feat", 25 * 3600)], [_status("feat", 25 * 3600, "building")],
                                      _workspace(), None, NOW)
    assert payload == {"start": NOW, "end": NOW, "duration": 0, "baseRate": ACTIVITY_RATE, "segments": [],
                       "lanes": 0, "lines": [], "feed": []}


def test_marks_carry_their_fields_and_name_the_page_they_point_at():
    entries = [_call("feat", 30, tool="mutatePageBatch", write=True, size=2140),
               {"at": _at(20), "kind": "link", "pageId": "feat", "to": "other", "role": "relates-to"},
               {"at": _at(10), "kind": "ref", "pageId": "feat", "to": "gone"}]
    [line] = build_activity_timeline(entries, [_status("feat", 40, "building")], _workspace(), "feat", NOW)["lines"]
    assert [{key: value for key, value in mark.items() if key not in ("p", "at")} for mark in line["marks"]] == [
        {"kind": "status", "status": "building"},
        {"kind": "call", "tool": "mutatePageBatch", "write": True, "bytes": 2140},
        {"kind": "link", "to": "other", "title": "Other", "role": "relates-to"},
        {"kind": "ref", "to": "gone", "title": "gone"},
    ]
    assert (line["title"], line["colour"], line["href"]) == ("Feature", "feature-brief", "/ws:w/page/feat")


def test_a_page_of_another_type_takes_the_page_colour_and_a_deleted_page_its_logged_title():
    events = [_status("plan", 30, "ready", page_type="implementation-plan"),
              _status("gone", 20, "closed", page_type="bug-report", title="Deleted bug")]
    lines = {line["id"]: line for line in build_activity_timeline([], events, _workspace(), None, NOW)["lines"]}
    assert lines["plan"]["colour"] == "page"
    assert (lines["gone"]["title"], lines["gone"]["colour"]) == ("Deleted bug", "bug-report")


def test_marks_at_the_same_instant_keep_events_before_entries():
    [line] = build_activity_timeline([_call("feat", 10)], [_status("feat", 10, "review")], _workspace(), "feat", NOW)["lines"]
    assert [mark["kind"] for mark in line["marks"]] == ["status", "call"]


def test_calls_seconds_apart_play_apart():
    [line] = build_activity_timeline([_call("feat", 12), _call("feat", 10)], [], _workspace(), "feat", NOW)["lines"]
    first, second = line["marks"]
    assert second["p"] - first["p"] == pytest.approx(2 / ACTIVITY_RATE)      # 0.1 playback s, 12 px at 120 px/s


def test_an_idle_hour_plays_in_at_most_a_second():
    payload = build_activity_timeline([_call("feat", 3700), _call("feat", 10)], [], _workspace(), "feat", NOW)
    assert payload["duration"] <= 30 / ACTIVITY_RATE * 2 + 1.0


def test_each_line_carries_its_whole_hierarchy_path():
    entries = [_call("plan", 30), _call(None, 20, tool="tree")]
    events = [_status("gone", 10, "closed", page_type="bug-report", title="Deleted bug")]
    lines = build_activity_timeline(entries, events, _workspace(), None, NOW)["lines"]
    assert {line["id"]: line["path"] for line in lines} == {
        "ws:w": ["Demo"], "plan": ["Features", "Feature", "Plan"], "gone": ["Deleted bug"]}


def test_a_create_page_call_recorded_before_is_never_shown():
    payload = build_activity_timeline([_call("toc", 10, tool="createPage", write=True)], [], _workspace(), None, NOW)
    assert payload["lines"] == []


def test_lines_follow_the_page_hierarchy_each_on_its_own_lane():
    # the sibling bug report is busy first, the plan beneath the feature next, the feature itself last
    entries = [_call("other", 100), _call("plan", 50), _call("feat", 10)]
    lines = build_activity_timeline(entries, [], _workspace(), None, NOW)["lines"]
    assert [(line["id"], line["lane"]) for line in lines] == [("feat", 0), ("plan", 1), ("other", 2)]


def test_pages_outside_the_tree_come_after_it_and_the_workspace_line_last():
    entries = [_call("gone-b", 40), _call("gone-a", 30), _call("plan", 20), _call(None, 10, tool="search")]
    payload = build_activity_timeline(entries, [], _workspace(), None, NOW)
    assert [line["id"] for line in payload["lines"]] == ["plan", "gone-b", "gone-a", "ws:w"]
    assert payload["lanes"] == 4


def test_the_feed_lists_every_mark_in_playback_order():
    entries = [_call("plan", 30), _call("feat", 20), _call("plan", 10)]
    payload = build_activity_timeline(entries, [], _workspace(), None, NOW)
    ordered = [payload["lines"][entry["line"]]["marks"][entry["mark"]]["p"] for entry in payload["feed"]]
    assert len(payload["feed"]) == 3 and ordered == sorted(ordered)
