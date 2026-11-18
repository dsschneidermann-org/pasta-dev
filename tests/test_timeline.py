"""Unit tests for the timeline model (src.timeline): the playback clock that plays activity at
0.25 day/s and squeezes idle time, and the metro lines built from a workspace's event log."""

import json
from datetime import datetime, timezone

import pytest

from src.ids import _base36
from src.model import Page, Workspace
from src.timeline import (
    ACTIVE_WINDOW,
    BASE_RATE,
    IDLE_PLAYBACK,
    LANE_GAP,
    Segment,
    build_timeline,
    is_hidden,
    playback_segments,
    to_playback,
)

DAY = 86_400.0
HOUR = 3_600.0
T0 = 1_780_000_000.0          # an epoch second in 2026


def _assert_contiguous(segments: list[Segment], start: float, end: float) -> None:
    assert segments[0].t0 == start and segments[0].p0 == 0.0
    assert segments[-1].t1 == end
    for previous, current in zip(segments, segments[1:]):
        assert current.t0 == previous.t1
        assert current.p0 == previous.p1


def test_one_event_plays_its_window_at_the_base_rate_and_squeezes_the_idle_sides():
    start, end = 0.0, 10 * DAY
    event = 5 * DAY
    segments = playback_segments([event], start, end)
    _assert_contiguous(segments, start, end)
    idle_before, active, idle_after = segments
    assert (active.t0, active.t1) == (event - ACTIVE_WINDOW, event + ACTIVE_WINDOW)
    assert active.p1 - active.p0 == pytest.approx(6 * HOUR / BASE_RATE)
    assert active.p1 - active.p0 == pytest.approx(1.0)                    # 6 h at 0.25 day/s
    assert idle_before.p1 - idle_before.p0 == IDLE_PLAYBACK
    assert idle_after.p1 - idle_after.p0 == IDLE_PLAYBACK


def test_events_an_hour_apart_share_one_active_window():
    segments = playback_segments([5 * DAY, 5 * DAY + HOUR], 0.0, 10 * DAY)
    assert len(segments) == 3
    assert segments[1].t1 - segments[1].t0 == 2 * ACTIVE_WINDOW + HOUR


def test_a_short_idle_gap_plays_at_the_base_rate_rather_than_slower():
    first = 5 * DAY
    second = first + 2 * ACTIVE_WINDOW + 4 * HOUR                         # a 4 h gap between windows
    segments = playback_segments([first, second], first - ACTIVE_WINDOW, second + ACTIVE_WINDOW)
    _assert_contiguous(segments, first - ACTIVE_WINDOW, second + ACTIVE_WINDOW)
    active_1, gap, active_2 = segments
    assert gap.t1 - gap.t0 == 4 * HOUR
    assert gap.p1 - gap.p0 == pytest.approx(4 * HOUR / BASE_RATE)        # 0.667 s, not 1 s
    assert gap.p1 - gap.p0 < IDLE_PLAYBACK


@pytest.mark.parametrize("times, start, end", [([], 0.0, DAY), ([5.0], DAY, DAY), ([5.0], DAY, 0.0)])
def test_no_times_or_an_empty_span_gives_no_segments(times, start, end):
    assert playback_segments(times, start, end) == []


def test_to_playback_clamps_interpolates_and_never_runs_backwards():
    start, end = 0.0, 10 * DAY
    segments = playback_segments([2 * DAY, 7 * DAY], start, end)
    total = segments[-1].p1
    assert to_playback(-DAY, segments) == 0.0
    assert to_playback(11 * DAY, segments) == total
    active = segments[1]
    middle = (active.t0 + active.t1) / 2
    assert to_playback(middle, segments) == pytest.approx((active.p0 + active.p1) / 2)
    mapped = [to_playback(t * HOUR, segments) for t in range(0, 241)]
    assert mapped == sorted(mapped)


def test_to_playback_of_no_segments_is_zero():
    assert to_playback(123.0, []) == 0.0


# --- build_timeline ----------------------------------------------------------------------------

def _id(kind: str, created: float) -> str:
    """A page id that encodes `created`, the way the store's id factory does."""
    return f"{kind}:{_base36(int(created * 1000))}-abc123"


def _at(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _event(t: float, kind: str, page_id: str, status: str, previous: str | None = None,
           title: str = "Logged title") -> dict[str, str]:
    event = {"at": _at(t), "event": kind, "pageId": page_id, "type": page_id.split(":")[0],
             "title": title, "status": status}
    if previous is not None:
        event["from"] = previous
    return event


def _workspace(*pages: Page) -> Workspace:
    return Workspace(id="ws:x", name="x", pages={page.id: page for page in pages})


def _page(page_id: str, status: str, title: str = "Current title", parent: str | None = None,
          archived: bool = False) -> Page:
    return Page(id=page_id, type=page_id.split(":")[0], title=title, status=status,
                parent_id=parent, archived=archived)


def _only_line(payload):
    [line] = payload["lines"]
    return line


def test_a_shipped_feature_ends_delivered_at_its_ship_station():
    page = _id("feature-brief", T0)
    events = [
        _event(T0, "created", page, "draft"),
        _event(T0 + HOUR, "status", page, "grounding", "draft"),
        _event(T0 + 2 * HOUR, "status", page, "shipped", "done"),
    ]
    payload = build_timeline(events, _workspace(_page(page, "shipped")), T0 + 10 * DAY)
    line = _only_line(payload)
    assert line["end"] == "delivered"
    assert [stop["status"] for stop in line["stops"]] == ["draft", "grounding", "shipped"]
    assert [stop["kind"] for stop in line["stops"]] == ["created", "status", "status"]
    assert line["p1"] == line["stops"][-1]["p"]
    assert line["p1"] < payload["duration"]


def test_an_abandoned_feature_ends_dropped():
    page = _id("feature-brief", T0)
    events = [_event(T0, "created", page, "draft"), _event(T0 + HOUR, "status", page, "abandoned", "draft")]
    line = _only_line(build_timeline(events, _workspace(_page(page, "abandoned")), T0 + DAY))
    assert line["end"] == "dropped"
    assert line["p1"] == line["stops"][-1]["p"]


def test_archiving_an_unfinished_page_ends_its_line_and_unarchiving_resumes_it():
    page = _id("bug-report", T0)
    archived = [_event(T0, "created", page, "draft"), _event(T0 + HOUR, "archived", page, "draft")]
    line = _only_line(build_timeline(archived, _workspace(_page(page, "draft", archived=True)), T0 + DAY))
    assert line["end"] == "dropped"
    assert line["p1"] == line["stops"][-1]["p"]

    restored = archived + [_event(T0 + 2 * HOUR, "unarchived", page, "draft")]
    payload = build_timeline(restored, _workspace(_page(page, "draft")), T0 + DAY)
    line = _only_line(payload)
    assert line["end"] == "open"
    assert line["p1"] == payload["duration"]


def test_a_closed_bug_report_that_reopened_is_open_again():
    page = _id("bug-report", T0)
    events = [
        _event(T0, "created", page, "draft"),
        _event(T0 + HOUR, "status", page, "closed", "done"),
        _event(T0 + 2 * HOUR, "status", page, "open", "closed"),
    ]
    payload = build_timeline(events, _workspace(_page(page, "open")), T0 + DAY)
    assert _only_line(payload)["end"] == "open"


def test_a_page_hidden_under_an_archived_parent_ends_dropped_at_its_last_event():
    epic = "epic:parent"
    page = _id("feature-brief", T0)
    events = [_event(T0, "created", page, "draft"), _event(T0 + HOUR, "status", page, "review", "building")]
    workspace = _workspace(_page(epic, "review", archived=True), _page(page, "review", parent=epic))
    line = _only_line(build_timeline(events, workspace, T0 + DAY))
    assert line["end"] == "dropped"
    assert line["p1"] == line["stops"][-1]["p"]


def test_a_page_gone_from_the_workspace_ends_dropped_and_keeps_its_logged_title():
    page = _id("simple-change", T0)
    events = [_event(T0, "created", page, "draft", title="First"),
              _event(T0 + HOUR, "status", page, "open", "draft", title="Last")]
    line = _only_line(build_timeline(events, _workspace(), T0 + DAY))
    assert line["end"] == "dropped"
    assert line["title"] == "Last"


def test_the_current_workspace_title_wins_over_the_logged_one():
    page = _id("feature-brief", T0)
    events = [_event(T0, "created", page, "draft", title="Old name")]
    line = _only_line(build_timeline(events, _workspace(_page(page, "draft", title="New name")), T0 + DAY))
    assert line["title"] == "New name"
    assert line["end"] == "open"


def test_a_page_first_seen_at_a_transition_starts_at_its_id_time_in_the_status_it_left():
    page = _id("feature-brief", T0)
    events = [_event(T0 + 3 * HOUR, "status", page, "grounding", "draft")]
    payload = build_timeline(events, _workspace(_page(page, "grounding")), T0 + DAY)
    line = _only_line(payload)
    assert line["stops"][0]["at"] == T0
    assert line["stops"][0]["status"] == "draft"
    assert line["stops"][0]["kind"] == "created"
    assert payload["start"] == T0
    assert [stop["status"] for stop in line["stops"]] == ["draft", "grounding"]


def test_the_created_event_is_the_first_station_and_never_a_second_one():
    page = _id("feature-brief", T0)
    events = [_event(T0 + 0.004, "created", page, "draft")]    # logged a few ms after the id time
    line = _only_line(build_timeline(events, _workspace(_page(page, "draft")), T0 + DAY))
    assert len(line["stops"]) == 1


def test_only_feature_briefs_bug_reports_and_simple_changes_become_lines():
    doc = _id("architecture", T0)
    plan = _id("implementation-plan", T0)
    events = [_event(T0, "created", doc, "current"), _event(T0, "created", plan, "draft")]
    payload = build_timeline(events, _workspace(), T0 + DAY)
    assert payload["lines"] == []


def test_overlapping_lines_take_separate_lanes_and_a_later_line_reuses_a_freed_one():
    first, second, third = _id("feature-brief", T0), _id("bug-report", T0 + HOUR), _id("simple-change", T0 + 5 * DAY)
    events = [
        _event(T0, "created", first, "draft"),
        _event(T0 + HOUR, "created", second, "draft"),
        _event(T0 + 2 * HOUR, "status", first, "shipped", "done"),
        _event(T0 + 3 * HOUR, "status", second, "closed", "done"),
        _event(T0 + 5 * DAY, "created", third, "draft"),
    ]
    workspace = _workspace(_page(first, "shipped"), _page(second, "closed"), _page(third, "draft"))
    payload = build_timeline(events, workspace, T0 + 6 * DAY)
    lanes = {line["id"]: line["lane"] for line in payload["lines"]}
    assert lanes == {first: 0, second: 1, third: 0}
    assert payload["lanes"] == 2
    by_id = {line["id"]: line for line in payload["lines"]}
    assert by_id[third]["p0"] >= by_id[first]["p1"] + LANE_GAP


def test_the_feed_lists_every_station_in_playback_order():
    first, second = _id("feature-brief", T0), _id("bug-report", T0 + HOUR)
    events = [
        _event(T0, "created", first, "draft"),
        _event(T0 + HOUR, "created", second, "draft"),
        _event(T0 + 2 * HOUR, "status", first, "shipped", "done"),
    ]
    payload = build_timeline(events, _workspace(_page(first, "shipped"), _page(second, "draft")), T0 + DAY)
    feed = payload["feed"]
    assert len(feed) == 3
    ps = [entry["p"] for entry in feed]
    assert ps == sorted(ps)
    resolved = [payload["lines"][entry["line"]]["stops"][entry["stop"]]["status"] for entry in feed]
    assert resolved == ["draft", "draft", "shipped"]
    json.dumps(payload)


def test_no_line_events_give_the_empty_payload():
    payload = build_timeline([], _workspace(), T0)
    assert (payload["duration"], payload["segments"], payload["lanes"]) == (0, [], 0)
    assert (payload["lines"], payload["feed"]) == ([], [])


def test_is_hidden_follows_archived_ancestors_and_missing_pages():
    workspace = _workspace(_page("epic:a", "open", archived=True),
                           _page("feature-brief:b", "draft", parent="epic:a"),
                           _page("feature-brief:c", "draft"))
    assert is_hidden(workspace, "epic:a")
    assert is_hidden(workspace, "feature-brief:b")
    assert not is_hidden(workspace, "feature-brief:c")
    assert is_hidden(workspace, "feature-brief:gone")
