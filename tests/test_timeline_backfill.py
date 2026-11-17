"""Tests for the initial back-fill of pasta's own workspace log (scripts/build_timeline_dataset.py).

The pure rules are checked on small in-memory fixtures, the collect and build commands on temporary
folders, and the committed back-fill against its committed inputs - so nothing here needs the
gitignored data folder, the network or a page type.
"""

from datetime import UTC, datetime

import pytest

from scripts import build_timeline_dataset as dataset


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


# --- page-id times and the title rule ------------------------------------------

def test_id_time_ms_decodes_the_base36_milliseconds_of_a_page_id():
    assert dataset.id_time_ms("feature-brief:mtiml5v4-6c209f") == int("mtiml5v4", 36)
    assert _utc(dataset.id_time_ms("feature-brief:mtiml5v4-6c209f")).date().isoformat() == "2026-09-01"
    assert (dataset.id_time_ms("implementation-plan:mtiml5v5-6eeb03")
            == int("mtiml5v5", 36))


def test_title_type_follows_the_judged_rule_in_order():
    assert dataset.title_type("Add a fix for X") == "feature-brief"
    assert dataset.title_type("Addressing the error on load") == "bug-report"
    assert dataset.title_type("Report the revision a rejected batch leaves behind") == "bug-report"
    assert dataset.title_type("Stop the crash on load") == "bug-report"
    assert dataset.title_type("Rename state to status") == "simple-change"
    assert dataset.title_type("PEP8 style cleanup: spacing") == "simple-change"
    assert dataset.title_type("Review guidance for planReview") == "simple-change"
    assert dataset.title_type("Renamed pages keep links") == "feature-brief"
    assert dataset.title_type("Make initial_sections idempotent") == "feature-brief"


# --- the pages that carry each PR link ------------------------------------------

PULL = "https://github.com/dsschneidermann-org/pasta-dev/pull/"
FEATURES, BUG_REPORTS = "toc:ms90fb2w-721ea1", "toc:ms90fbg0-ba90c1"


def _linked(page_type: str, url: str | None, child_ids: tuple[str, ...] = ()) -> dict:
    return {"type": page_type, "title": "T", "child_ids": list(child_ids),
            "sections": {"pull_request": {"url": url}}}


def _document(pages: dict, workspace_id: str = dataset.WORKSPACE_ID, roots: tuple[str, ...] = ()) -> dict:
    return {"id": workspace_id, "root_page_ids": list(roots), "pages": pages}


def test_linked_pages_keeps_only_pr_links_of_the_workspace_in_range():
    pages = {
        "simple-change:a0000001-000001": _linked("simple-change", PULL + "3"),
        "simple-change:a0000002-000002": _linked("simple-change", PULL + "3/files"),
        "simple-change:a0000003-000003": _linked("simple-change", PULL + "3?x=1"),
        "bug-report:a0000004-000004": _linked("bug-report", PULL + "3#c"),
        "feature-brief:a0000005-000005": _linked(
            "feature-brief", "https://github.com/dsschneidermann-org/pasta-dev/tree/timeline-backfill"),
        "feature-brief:a0000006-000006": _linked("feature-brief", "https://github.com/other/repo/pull/3"),
        "feature-brief:a0000007-000007": _linked("feature-brief", PULL + "3abc"),
        "feature-brief:a0000008-000008": _linked("feature-brief", PULL + "0"),
        "feature-brief:a0000009-000009": _linked("feature-brief", PULL + "66"),
        "feature-brief:a000000a-00000a": _linked("feature-brief", None),
        "epic:a000000b-00000b": _linked("epic", PULL + "3"),
    }
    foreign = _document({"simple-change:a000000c-00000c": _linked("simple-change", PULL + "4")},
                        workspace_id="ws:other-000000")
    linked = dataset.linked_pages([_document(pages), foreign])
    assert list(linked) == [3]
    assert [record["id"] for record in linked[3]] == [
        "bug-report:a0000004-000004", "simple-change:a0000001-000001",
        "simple-change:a0000002-000002", "simple-change:a0000003-000003"]


def test_linked_pages_first_document_wins_and_plan_ids_come_from_child_prefixes():
    brief = "feature-brief:a0000001-000001"
    newer = _document({
        brief: _linked("feature-brief", PULL + "5", ("feature-spec:x-1", "implementation-plan:x-2",
                                                     "testing-plan:x-3", "testing-plan:x-4")),
        "feature-brief:a0000002-000002": _linked("feature-brief", PULL + "5", ("feature-spec:y-1",)),
        "bug-report:a0000003-000003": _linked("bug-report", PULL + "6", ("implementation-plan:z-1",)),
    })
    older = _document({brief: _linked("feature-brief", PULL + "5", ("implementation-plan:old-1",
                                                                   "testing-plan:old-2"))})
    linked = dataset.linked_pages([newer, older])
    assert linked == {
        5: [{"id": brief, "type": "feature-brief",
             "implementation_plan": "implementation-plan:x-2", "testing_plan": "testing-plan:x-3"},
            {"id": "feature-brief:a0000002-000002", "type": "feature-brief",
             "implementation_plan": None, "testing_plan": None}],
        6: [{"id": "bug-report:a0000003-000003", "type": "bug-report",
             "implementation_plan": None, "testing_plan": None}],
    }


def _live() -> dict:
    pages = {
        "toc:ms90f9jm-c68d70": {"type": "toc", "title": "Documentation"},
        FEATURES: {"type": "toc", "title": "Features"},
        BUG_REPORTS: {"type": "toc", "title": "Bug Reports"},
        "toc:nested-000001": {"type": "toc", "title": "Features"},
        "document:a0000001-000001": {"type": "document", "title": "Bug Reports"},
        "bug-report:a0000002-000002": _linked("bug-report", PULL + "12"),
        "simple-change:a0000003-000003": _linked("simple-change", PULL + "2"),
    }
    return _document(pages, roots=("toc:ms90f9jm-c68d70", "document:a0000001-000001", FEATURES,
                                   BUG_REPORTS))


def test_workspace_pages_finds_the_root_tocs_and_rejects_a_missing_one():
    live = _live()
    value = dataset.workspace_pages(live, [live])
    assert value["workspace"] == dataset.WORKSPACE_ID
    assert value["tocs"] == {"Features": FEATURES, "Bug Reports": BUG_REPORTS}
    assert list(value["prs"]) == ["2", "12"]

    without_bug_reports = _live()
    without_bug_reports["root_page_ids"].remove(BUG_REPORTS)
    with pytest.raises(ValueError, match="Bug Reports"):
        dataset.workspace_pages(without_bug_reports, [])
    with pytest.raises(ValueError, match="ws:other"):
        dataset.workspace_pages({**live, "id": "ws:other-000000"}, [])


# --- commit lines, input checks and moments --------------------------------------

def _ms(*parts: int) -> int:
    return int(datetime(*parts, tzinfo=UTC).timestamp() * 1000)


def _pr(number: int, merged: str | None = None, closed: str | None = None, created: str | None = None,
        title: str | None = None) -> dict:
    return {"number": number, "title": title or f"PR {number}", "created_at": created,
            "merged_at": merged, "closed_at": closed}


def test_parse_commit_lines_reads_dated_lines_and_rejects_others():
    assert dataset.parse_commit_lines("2026-07-20  First pass\n2026-07-21  Second\n") == [
        ("2026-07-20", "First pass"), ("2026-07-21", "Second")]
    for bad in ("2026-07-20 One space\n", "First pass\n", "2026-07-20  First\n\n2026-07-21  Second\n"):
        with pytest.raises(ValueError, match="not a dated commit line"):
            dataset.parse_commit_lines(bad)


def test_input_problems_names_missing_prs_timeless_prs_and_a_wrong_count():
    prs = [_pr(number, merged="2026-08-25T18:48:23Z") for number in dataset.PR_NUMBERS]
    lines = [("2026-07-20", f"line {index}") for index in range(62)]
    assert dataset.input_problems(prs, lines) == []

    without_seven = [pr for pr in prs if pr["number"] != 7]
    problems = dataset.input_problems(without_seven, lines)
    assert any("#7" in problem for problem in problems)
    assert any("126" in problem for problem in problems)

    timeless = [_pr(3) if pr["number"] == 3 else pr for pr in prs]
    assert dataset.input_problems(timeless, lines) == [
        "PR #3 has no merged_at, closed_at or created_at"]


def test_moments_take_the_recorded_pr_time_by_precedence():
    prs = [_pr(1, merged="2026-08-25T18:48:23Z", closed="2026-08-26T00:00:00Z",
               created="2026-08-20T00:00:00Z"),
           _pr(2, closed="2026-08-27T10:00:00Z", created="2026-08-21T00:00:00Z"),
           _pr(3, created="2026-08-28T10:00:00Z")]
    assert [(moment.ts, moment.pr) for moment in dataset.moments(prs, [])] == [
        (1787683703000, 1), (_ms(2026, 8, 27, 10), 2), (_ms(2026, 8, 28, 10), 3)]


def test_moments_spread_a_days_commit_lines_over_nine_to_twenty_one_utc():
    lines = [("2026-07-20", "one"),
             ("2026-07-21", "first of two"), ("2026-07-21", "second of two"),
             ("2026-07-22", "a"), ("2026-07-22", "b"), ("2026-07-22", "c")]
    assert [(moment.ts, moment.title, moment.pr) for moment in dataset.moments([], lines)] == [
        (_ms(2026, 7, 20, 15), "one", None),
        (_ms(2026, 7, 21, 12), "first of two", None), (_ms(2026, 7, 21, 18), "second of two", None),
        (_ms(2026, 7, 22, 11), "a", None), (_ms(2026, 7, 22, 15), "b", None),
        (_ms(2026, 7, 22, 19), "c", None)]


def test_moments_put_prs_first_on_a_tie_and_bump_by_a_second():
    at_three = _ms(2026, 7, 20, 15)
    moments = dataset.moments([_pr(1, merged="2026-07-20T15:00:00Z")], [("2026-07-20", "line")])
    assert [(moment.ts, moment.pr) for moment in moments] == [(at_three, 1), (at_three + 1000, None)]

    moments = dataset.moments([_pr(1, merged="2026-07-20T15:00:00Z"),
                               _pr(2, merged="2026-07-20T15:00:00Z")], [("2026-07-20", "line")])
    assert [(moment.ts, moment.pr) for moment in moments] == [
        (at_three, 1), (at_three + 1000, 2), (at_three + 2000, None)]
