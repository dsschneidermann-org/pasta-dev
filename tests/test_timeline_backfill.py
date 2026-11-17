"""Tests for the initial back-fill of pasta's own workspace log (scripts/build_timeline_dataset.py).

The pure rules are checked on small in-memory fixtures, the collect and build commands on temporary
folders, and the committed back-fill against its committed inputs - so nothing here needs the
gitignored data folder, the network or a page type.
"""

from datetime import UTC, datetime

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
