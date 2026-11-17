"""Tests for the initial back-fill of pasta's own workspace log (scripts/build_timeline_dataset.py).

The pure rules are checked on small in-memory fixtures, the collect and build commands on temporary
folders, and the committed back-fill against its committed inputs - so nothing here needs the
gitignored data folder, the network or a page type.
"""

import json
from datetime import UTC, datetime

import pytest

from scripts import build_timeline_dataset as dataset
from src import lifecycle_log


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


# --- building the back-fill lines ------------------------------------------------

def _base36(number: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    encoded = ""
    while number:
        number, remainder = divmod(number, 36)
        encoded = digits[remainder] + encoded
    return encoded


def _page_id(page_type: str, *parts: int) -> str:
    return f"{page_type}:{_base36(_ms(*parts))}-abc123"


FB = _page_id("feature-brief", 2026, 8, 20, 10)
FB_PLAN, FB_CASES = _page_id("implementation-plan", 2026, 8, 20, 10), _page_id("testing-plan", 2026, 8, 20, 10)
SHARED = _page_id("simple-change", 2026, 9, 1, 9)
EARLY_BUG, LATE_FEATURE = _page_id("bug-report", 2026, 9, 1, 8), _page_id("feature-brief", 2026, 9, 2, 8)
LATE_BUG = _page_id("bug-report", 2026, 9, 5, 10)
PR_ONE_AT, PR_THREE_AT = 1787683703000, _ms(2026, 9, 2, 13, 50, 5)
PR_FOUR_AT, PR_FIVE_AT = _ms(2026, 9, 3, 10), _ms(2026, 9, 4, 10)


def _record(page_id: str, plan: str | None = None, cases: str | None = None) -> dict:
    return {"id": page_id, "type": page_id.split(":")[0], "implementation_plan": plan, "testing_plan": cases}


def _fixture() -> tuple[list[dict], list[tuple[str, str]], dict]:
    prs = [_pr(1, merged="2026-08-25T18:48:23Z"),
           _pr(2, closed="2026-09-02T11:41:58Z", title="Earlier title"),
           _pr(3, merged="2026-09-02T13:50:05Z", title="Later title"),
           _pr(4, merged="2026-09-03T10:00:00Z"),
           _pr(5, merged="2026-09-04T10:00:00Z")]
    lines = [("2026-07-20", "Add X"), ("2026-07-21", "Rename Y")]
    pages = {"workspace": dataset.WORKSPACE_ID,
             "tocs": {"Features": FEATURES, "Bug Reports": BUG_REPORTS},
             "prs": {"1": [_record(FB, FB_PLAN, FB_CASES)], "2": [_record(SHARED)], "3": [_record(SHARED)],
                     "4": [_record(EARLY_BUG), _record(LATE_FEATURE, "implementation-plan:x-1", "testing-plan:x-2")],
                     "5": [_record(LATE_BUG)]}}
    return prs, lines, pages


def _by_kind(lines: list[dict], kind: str) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for line in lines:
        if line["kind"] == kind:
            found.setdefault(line["page"], []).append(line)
    return found


def test_build_backfill_uses_real_ids_and_decoded_create_times_for_linked_prs():
    lines = dataset.build_backfill(*_fixture())
    created, status = _by_kind(lines, "created"), _by_kind(lines, "status")
    assert created[FB] == [{"seq": created[FB][0]["seq"], "ts": _ms(2026, 8, 20, 10), "page": FB,
                            "kind": "created", "type": "feature-brief", "title": "PR 1",
                            "parent": FEATURES, "status": "draft"}]
    assert [(line["ts"], line["type"], line["title"], line["parent"]) for line in created[FB_PLAN] + created[FB_CASES]] == [
        (_ms(2026, 8, 20, 10), "implementation-plan", "PR 1 - implementation plan", FB),
        (_ms(2026, 8, 20, 10), "testing-plan", "PR 1 - testing plan", FB)]
    assert [(line["ts"], line["from"], line["to"]) for line in status[FB_PLAN] + status[FB_CASES] + status[FB]] == [
        (PR_ONE_AT + 1_800_000, "draft", "ready"), (PR_ONE_AT + 2_700_000, "draft", "ready"),
        (PR_ONE_AT + 3_600_000, "draft", "shipped")]
    assert EARLY_BUG in created and LATE_FEATURE not in created
    assert created[EARLY_BUG][0]["parent"] == BUG_REPORTS
    assert [(line["ts"], line["to"]) for line in status[EARLY_BUG]] == [(PR_FOUR_AT + 3_600_000, "closed")]
    assert created[LATE_BUG][0]["ts"] == PR_FIVE_AT


def test_build_backfill_makes_prs_sharing_a_page_one_page():
    lines = dataset.build_backfill(*_fixture())
    created, status = _by_kind(lines, "created"), _by_kind(lines, "status")
    assert [(line["ts"], line["title"], line["parent"]) for line in created[SHARED]] == [
        (_ms(2026, 9, 1, 9), "Later title", FEATURES)]
    assert [(line["ts"], line["to"]) for line in status[SHARED]] == [(PR_THREE_AT + 3_600_000, "closed")]


def test_build_backfill_numbers_backfill_only_pages_and_plans():
    created = _by_kind(dataset.build_backfill(*_fixture()), "created")
    backfill_only = {page_id: lines[0] for page_id, lines in created.items() if ":bf-" in page_id}
    assert {page_id: (line["ts"], line["title"], line["parent"]) for page_id, line in backfill_only.items()} == {
        "feature-brief:bf-0001": (_ms(2026, 7, 20, 15), "Add X", FEATURES),
        "implementation-plan:bf-0002": (_ms(2026, 7, 20, 15), "Add X - implementation plan", "feature-brief:bf-0001"),
        "testing-plan:bf-0003": (_ms(2026, 7, 20, 15), "Add X - testing plan", "feature-brief:bf-0001"),
        "simple-change:bf-0004": (_ms(2026, 7, 21, 15), "Rename Y", FEATURES)}


def test_build_backfill_lines_are_a_valid_backfill():
    lines = dataset.build_backfill(*_fixture())
    earliest = _ms(2026, 7, 20, 15)
    assert lines[:2] == [
        {"seq": 1, "ts": earliest, "page": FEATURES, "kind": "created", "type": "toc", "title": "Features",
         "parent": None, "status": "active"},
        {"seq": 2, "ts": earliest, "page": BUG_REPORTS, "kind": "created", "type": "toc",
         "title": "Bug Reports", "parent": None, "status": "active"}]
    assert [line["seq"] for line in lines] == list(range(1, len(lines) + 1))
    assert [line["ts"] for line in lines] == sorted(line["ts"] for line in lines)
    first_line = {}
    for index, line in enumerate(lines):
        first_line.setdefault(line["page"], (index, line["kind"]))
        if line["kind"] == "created" and line["parent"] is not None:
            assert first_line[line["parent"]][0] < index
    assert all(kind == "created" for _, kind in first_line.values())
    for line in lines:
        expected = (["seq", "ts", "page", "kind", "type", "title", "parent", "status"] if line["kind"] == "created"
                    else ["seq", "ts", "page", "kind", "from", "to"])
        assert list(line) == expected
    assert lifecycle_log.check_backfill("".join(lifecycle_log.encode(line) for line in lines)) == lines


def test_build_backfill_rejects_a_linked_feature_brief_without_plans():
    prs, lines, pages = _fixture()
    pages["prs"]["1"] = [_record(FB, FB_PLAN, None)]
    with pytest.raises(ValueError, match=FB):
        dataset.build_backfill(prs, lines, pages)


def test_summary_reports_pages_lines_mapping_and_longest_wait():
    prs, lines, pages = _fixture()
    assert dataset.summary(dataset.build_backfill(prs, lines, pages), pages) == [
        "pages: 12 (bug-report 2, feature-brief 2, implementation-plan 2, simple-change 2, testing-plan 2, toc 2)",
        "lines: 22",
        "PRs mapped to a real page: 5",
        "back-fill-only moment pages: 2",
        f"longest wait: {FB} 5.4 days"]


# --- collect and build on disk ---------------------------------------------------

def _write_json(path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2).encode("utf-8"))


def _snapshot(folder) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def _data_folder(tmp_path):
    data = tmp_path / "data"
    _write_json(data / dataset.LIVE_FILENAME, _live())
    backup_only = "feature-brief:a0000009-000009"
    _write_json(data / "backups" / dataset.LIVE_FILENAME, _document({
        backup_only: _linked("feature-brief", PULL + "40", ("implementation-plan:p-1", "testing-plan:p-2"))}))
    _write_json(data / "backups" / "ws_mrteq0c5-238cf6" / "20260901T120502Z.json", _document({
        "simple-change:a0000003-000003": _linked("simple-change", PULL + "2"),
        "bug-report:a0000004-000004": _linked("bug-report", PULL + "2")}))
    _write_json(data / "ws_other-000000.json", _document(
        {"simple-change:a000000c-00000c": _linked("simple-change", PULL + "3")}, workspace_id="ws:other-000000"))
    return data


def test_collect_writes_only_its_output_and_leaves_the_data_folder_unchanged(tmp_path):
    data = _data_folder(tmp_path)
    before = _snapshot(data)
    out = tmp_path / "out" / "workspace-pages.json"
    assert dataset.collect(data, out) == 0
    expected = {
        "workspace": dataset.WORKSPACE_ID,
        "tocs": {"Features": FEATURES, "Bug Reports": BUG_REPORTS},
        "prs": {
            "2": [_record("bug-report:a0000004-000004"), _record("simple-change:a0000003-000003")],
            "12": [_record("bug-report:a0000002-000002")],
            "40": [_record("feature-brief:a0000009-000009", "implementation-plan:p-1", "testing-plan:p-2")]}}
    assert out.read_bytes() == (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert _snapshot(data) == before


def test_collect_fails_without_writing_on_a_missing_live_file_toc_or_bad_json(tmp_path):
    out = tmp_path / "workspace-pages.json"
    data = _data_folder(tmp_path)
    live = data / dataset.LIVE_FILENAME

    live.rename(tmp_path / "moved.json")
    assert dataset.collect(data, out) == 1
    assert not out.exists()

    without_bug_reports = _live()
    without_bug_reports["root_page_ids"].remove(BUG_REPORTS)
    _write_json(live, without_bug_reports)
    assert dataset.collect(data, out) == 1
    assert not out.exists()

    _write_json(live, _live())
    (data / "backups" / "ws_mrteq0c5-238cf6" / "20260902T120522Z.json").write_bytes(b"{not json")
    assert dataset.collect(data, out) == 1
    assert not out.exists()


def test_build_fails_without_writing_on_a_missing_or_incomplete_input(tmp_path):
    out = tmp_path / "out.jsonl"
    missing = tmp_path / "missing"
    missing.mkdir()
    for name in (dataset.PULL_REQUESTS_FILE, dataset.INITIAL_COMMIT_FILE):
        (missing / name).write_bytes((dataset.DATASET_DIR / name).read_bytes())
    assert dataset.build(missing, out) == 1
    assert not out.exists()

    prs, lines, pages = _fixture()
    incomplete = tmp_path / "incomplete"
    _write_json(incomplete / dataset.PULL_REQUESTS_FILE, prs)
    (incomplete / dataset.INITIAL_COMMIT_FILE).write_bytes(
        "".join(f"{date}  {text}\n" for date, text in lines).encode("utf-8"))
    _write_json(incomplete / dataset.WORKSPACE_PAGES_FILE, pages)
    assert dataset.build(incomplete, out) == 1
    assert not out.exists()


def test_build_writes_a_backfill_the_store_accepts(tmp_path):
    out = tmp_path / "backfill" / "out.jsonl"
    assert dataset.build(dataset.DATASET_DIR, out) == 0
    assert lifecycle_log.check_backfill(out.read_bytes().decode("utf-8")) is not None
