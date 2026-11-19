"""Unit tests for the backfill's pure half (src.backfill): reading the history sources, dating each
page's latest status, and merging the result into a log that may already hold live events."""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.backfill import (
    LIST_TZ,
    ListedFeature,
    PullRequest,
    Snapshot,
    backfill_events,
    match_listed,
    merge_log,
    parse_feature_list,
    parse_pull_requests,
    pr_numbers,
    status_time,
    typical_lifetime,
)
from src.ids import _base36

UTC = timezone.utc
CREATED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _id(kind: str, created: datetime) -> str:
    return f"{kind}:{_base36(int(created.timestamp() * 1000))}-abc123"


PAGE = _id("feature-brief", CREATED)


# --- parsers -----------------------------------------------------------------------------------

def test_parse_feature_list_keeps_only_the_dated_lines():
    message = ("Initial version cut\n\npasta - a structured wiki over MCP: typed pages.\n\n"
               "2026-07-20  First pass: file-backed pasta MCP server\n"
               "2026-07-22  Anchored reorder and positioned insert (stale-read-safe)\n")
    assert parse_feature_list(message) == [
        ListedFeature(date(2026, 7, 20), "First pass: file-backed pasta MCP server"),
        ListedFeature(date(2026, 7, 22), "Anchored reorder and positioned insert (stale-read-safe)"),
    ]


def test_parse_pull_requests_reads_github_rows_with_and_without_a_merge():
    rows = [
        {"number": 21, "created_at": "2026-09-02T12:07:05Z", "merged_at": "2026-09-02T13:50:05Z",
         "closed_at": "2026-09-02T13:50:05Z"},
        {"number": 20, "created_at": "2026-09-01T15:07:24Z", "merged_at": None, "closed_at": "2026-09-02T11:41:58Z"},
        {"number": 44, "created_at": "2026-10-20T13:02:47Z"},
    ]
    prs = parse_pull_requests(rows)
    assert prs[21].merged == datetime(2026, 9, 2, 13, 50, 5, tzinfo=UTC)
    assert prs[20].merged is None and prs[20].closed == datetime(2026, 9, 2, 11, 41, 58, tzinfo=UTC)
    assert prs[44].merged is None and prs[44].closed is None
    assert prs[44].created == datetime(2026, 10, 20, 13, 2, 47, tzinfo=UTC)


def test_pr_numbers_reads_the_pull_request_url_only():
    page = {"sections": {"pull_request": {"url": "https://github.com/o/r/pull/21"},
                         "conflicts": {"items": [{"text": "see https://github.com/o/r/pull/9"}]}}}
    assert pr_numbers(page) == [21]
    assert pr_numbers({"sections": {}}) == []
    assert pr_numbers({"sections": {"pull_request": {"url": None}}}) == []


def test_typical_lifetime_is_stable_per_page_and_an_hour_or_two():
    assert typical_lifetime(PAGE) == typical_lifetime(PAGE)
    for page_id in (PAGE, "bug-report:abc", "simple-change:xyz-1"):
        assert timedelta(minutes=60) <= typical_lifetime(page_id) <= timedelta(minutes=120)


FEATURES = [
    ListedFeature(date(2026, 7, 20), "Store: auto-created children, ref integrity, ship guard"),
    ListedFeature(date(2026, 7, 22), "Anchored reorder and positioned insert (stale-read-safe)"),
    ListedFeature(date(2026, 7, 24), "Add test-variant page types to decouple tests from the live registry"),
]


def test_match_listed_pairs_a_page_with_its_feature_line():
    created = datetime(2026, 7, 22, 14, 53, tzinfo=UTC)
    assert match_listed("Anchored relocate & positioned insert (stale-read-safe)", created, FEATURES) == FEATURES[1]


def test_match_listed_never_returns_a_feature_dated_before_the_page_existed():
    created = datetime(2026, 7, 28, 10, 39, tzinfo=UTC)
    assert match_listed("Add test-variant page types to decouple tests", created, FEATURES) is None


def test_match_listed_returns_none_for_an_unrelated_title():
    created = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
    assert match_listed("Pink colour theme for the web UI", created, FEATURES) is None


# --- status_time -------------------------------------------------------------------------------

def _pr(number: int, created: datetime, merged: datetime | None = None,
        closed: datetime | None = None) -> PullRequest:
    return PullRequest(number, created, merged, closed)


def test_a_merged_pr_dates_the_status():
    merged = CREATED + timedelta(days=2)
    prs = {7: _pr(7, CREATED + timedelta(hours=1), merged, merged)}
    assert status_time(PAGE, "shipped", [], prs, [7], None, NOW) == (merged, "pr")


def test_the_latest_merge_wins_over_an_earlier_closed_attempt():
    first_closed = CREATED + timedelta(days=1)
    merged = CREATED + timedelta(days=2)
    prs = {20: _pr(20, CREATED, None, first_closed), 21: _pr(21, first_closed, merged, merged)}
    assert status_time(PAGE, "shipped", [], prs, [20, 21], None, NOW) == (merged, "pr")


def test_a_pr_closed_without_merging_dates_the_status_by_its_close():
    closed = CREATED + timedelta(days=3)
    prs = {5: _pr(5, CREATED + timedelta(hours=1), None, closed)}
    assert status_time(PAGE, "abandoned", [], prs, [5], None, NOW) == (closed, "pr")


def test_an_open_pr_dates_the_status_by_when_it_was_opened():
    opened = CREATED + timedelta(hours=3)
    prs = {44: _pr(44, opened)}
    assert status_time(PAGE, "done", [], prs, [44], None, NOW) == (opened, "pr")


def test_a_pr_older_than_the_page_is_not_used():
    old = CREATED - timedelta(days=5)
    prs = {3: _pr(3, old - timedelta(hours=1), old, old)}
    when, kind = status_time(PAGE, "closed", [], prs, [3], None, NOW)
    assert kind == "estimate"
    assert when == CREATED + typical_lifetime(PAGE)


def test_a_listed_feature_on_a_later_day_dates_the_status_that_day():
    listed = ListedFeature(date(2026, 9, 4), "Something")
    typical = CREATED + typical_lifetime(PAGE)
    when, kind = status_time(PAGE, "shipped", [], {}, [], listed, NOW)
    assert kind == "list"
    assert when.astimezone(LIST_TZ).date() == date(2026, 9, 4)
    assert when.astimezone(LIST_TZ).time() == typical.astimezone(LIST_TZ).time()


def test_a_listed_feature_on_the_creation_day_gives_the_typical_lifetime():
    listed = ListedFeature(date(2026, 9, 1), "Something")
    assert status_time(PAGE, "shipped", [], {}, [], listed, NOW) == (CREATED + typical_lifetime(PAGE), "list")


def test_without_an_anchor_the_estimate_is_the_typical_lifetime():
    history = [(CREATED + timedelta(days=10), "shipped")]
    assert status_time(PAGE, "shipped", history, {}, [], None, NOW) == (CREATED + typical_lifetime(PAGE), "estimate")


def test_the_estimate_is_clamped_up_to_the_last_backup_showing_another_status():
    last_building = CREATED + timedelta(days=4)
    history = [(CREATED + timedelta(days=2), "building"), (last_building, "building"),
               (CREATED + timedelta(days=6), "shipped")]
    assert status_time(PAGE, "shipped", history, {}, [], None, NOW) == (last_building, "estimate")


def test_the_estimate_is_clamped_down_to_the_first_backup_showing_the_status():
    first_seen = CREATED + timedelta(minutes=30)
    history = [(first_seen, "closed")]
    assert status_time(PAGE, "closed", history, {}, [], None, NOW) == (first_seen, "estimate")


def test_a_status_time_never_lands_after_now():
    now = CREATED + timedelta(minutes=10)
    when, _ = status_time(PAGE, "done", [], {}, [], None, now)
    assert when == now


# --- backfill_events / merge_log ---------------------------------------------------------------

def _stored(page_id: str, status: str, title: str, pr: int | None = None) -> dict:
    sections = {"pull_request": {"url": f"https://github.com/o/r/pull/{pr}"}} if pr else {}
    return {"id": page_id, "type": page_id.split(":")[0], "title": title, "status": status,
            "sections": sections}


def test_backfill_events_dates_each_tracked_page_from_its_latest_snapshot():
    shipped = _id("feature-brief", CREATED)
    draft = _id("bug-report", CREATED + timedelta(days=1))
    probe = _id("feature-brief", CREATED + timedelta(days=2))
    skipped = _id("simple-change", CREATED + timedelta(days=3))
    doc = _id("architecture", CREATED)
    merged = CREATED + timedelta(days=4)
    early = Snapshot(CREATED + timedelta(days=3), {shipped: _stored(shipped, "building", "Old title")})
    late = Snapshot(CREATED + timedelta(days=5), {
        shipped: _stored(shipped, "shipped", "Final title", pr=9),
        draft: _stored(draft, "draft", "A bug"),
        probe: _stored(probe, "review", "[probe] feature-brief lifecycle walk"),
        skipped: _stored(skipped, "closed", "Live already"),
        doc: _stored(doc, "current", "Docs"),
    })
    prs = {9: _pr(9, CREATED + timedelta(days=3), merged, merged)}
    events = backfill_events([late, early], prs, [], {skipped}, NOW)

    assert [(e["pageId"], e["event"]) for e in events] == [
        (shipped, "created"), (draft, "created"), (shipped, "status"),
    ]
    created, bug, status = events
    assert created["at"] == CREATED.isoformat() and created["status"] == "draft"
    assert created["title"] == "Final title" and status["title"] == "Final title"
    assert status == {"at": merged.isoformat(), "event": "status", "pageId": shipped, "type": "feature-brief",
                      "title": "Final title", "status": "shipped", "from": "draft",
                      "source": "backfill", "anchor": "pr"}
    assert all(event["source"] == "backfill" for event in events)
    assert "anchor" not in created and "anchor" not in bug


def _line(at: str, page_id: str, source: str | None = None) -> dict[str, str]:
    event = {"at": at, "event": "created", "pageId": page_id}
    return event | {"source": source} if source else event


def test_merge_log_replaces_earlier_backfill_and_keeps_live_lines_in_order():
    live_1 = _line("2026-11-18T10:00:00.500000+00:00", "a")
    live_2 = _line("2026-11-18T10:00:00.500000+00:00", "b")          # same instant, logged after live_1
    stale = _line("2026-07-01T00:00:00+00:00", "old", "backfill")
    fresh = _line("2026-08-01T00:00:00+00:00", "new", "backfill")
    merged = merge_log([live_1, stale, live_2], [fresh])
    assert merged == [fresh, live_1, live_2]
    assert merge_log(merged, [fresh]) == merged
