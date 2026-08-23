"""Unit tests for the recurring cleanup sweep (src.cleanup).

Classification is pure, so these build workspaces straight from src.model rather
than going through the store or the page-type registry. The store-backed transaction
is covered in test_store.py.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from src import cleanup
from src.model import Page, Workspace
from src.store import Store


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    """cleanup._task is module-global; without a reset the scheduler assertions pass
    or fail depending on which tests ran first."""
    cleanup._task = None
    yield
    cleanup._task = None


def _ws(*pages: Page, roots: list[str]) -> Workspace:
    return Workspace(id="ws:t", name="t", root_page_ids=roots, pages={p.id: p for p in pages})


def _p(page_id, children=(), archived=False, expires_at=None) -> Page:
    return Page(id=page_id, type="test-fields", title=page_id, status="active",
                child_ids=list(children), archived=archived, expires_at=expires_at)


def test_expiry_is_noon_utc_five_days_out():
    now = datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc)
    assert cleanup.expiry_for(now) == "2026-08-18T12:00:00+00:00"


def test_expiry_is_uniform_across_the_same_day():
    early = cleanup.expiry_for(datetime(2026, 8, 13, 0, 5, tzinfo=timezone.utc))
    late = cleanup.expiry_for(datetime(2026, 8, 13, 23, 5, tzinfo=timezone.utc))
    assert early == late == "2026-08-18T12:00:00+00:00"


def test_seconds_until_next_run_targets_five_past():
    assert cleanup.seconds_until_next_run(
        datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc)) == 300.0


def test_seconds_until_next_run_never_returns_zero():
    # Exactly on the boundary must schedule the next hour, not spin.
    assert cleanup.seconds_until_next_run(
        datetime(2026, 8, 13, 9, 5, 0, tzinfo=timezone.utc)) == 3600.0


def test_the_tick_counts_as_just_passed_for_one_sleep():
    def elapsed_since_tick(moment):
        return cleanup.SWEEP_PERIOD_SECONDS - cleanup.seconds_until_next_run(moment)

    assert elapsed_since_tick(datetime(2026, 8, 13, 9, 5, 0, tzinfo=timezone.utc)) == 0
    assert elapsed_since_tick(datetime(2026, 8, 13, 9, 5, 29, tzinfo=timezone.utc)) == 29
    # 30s on, the window has closed and the next wake sweeps nothing.
    assert elapsed_since_tick(datetime(2026, 8, 13, 9, 5, 30, tzinfo=timezone.utc)) == 30


def test_reachability_sorts_the_three_buckets():
    ws = _ws(_p("root", ["live", "arch"]), _p("live"),
             _p("arch", ["shadowed"], archived=True), _p("shadowed"),
             _p("lost"), roots=["root"])
    reach = cleanup.reachability(ws)
    assert reach.findable == {"root", "live"}
    assert reach.hidden == {"arch", "shadowed"}   # the archived page and its shadowed child
    assert reach.unfiled == {"lost"}


def test_reachability_ignores_parent_id_entirely():
    # A stale parent_id pointing at an archived page must not hide a properly filed page.
    good = _p("good")
    good.parent_id = "arch"
    ws = _ws(_p("root", ["good", "arch"]), good, _p("arch", archived=True), roots=["root"])
    assert "good" in cleanup.reachability(ws).findable


def test_reachability_terminates_on_a_child_id_cycle():
    ws = _ws(_p("a", ["b"]), _p("b", ["a"]), roots=["a"])
    assert cleanup.reachability(ws).findable == {"a", "b"}   # returns; does not hang


def test_reachability_tolerates_a_dangling_child_id():
    ws = _ws(_p("root", ["gone"]), roots=["root"])
    assert cleanup.reachability(ws).findable == {"root"}


NOW = datetime(2026, 8, 13, 9, 5, tzinfo=timezone.utc)
SOON = "2026-08-18T12:00:00+00:00"      # what expiry_for(NOW) returns
PAST = "2026-08-01T12:00:00+00:00"      # already elapsed


def test_classify_stamps_hidden_and_unfiled_only():
    ws = _ws(_p("root", ["live", "arch"]), _p("live"), _p("arch", archived=True),
             _p("lost"), roots=["root"])
    assert cleanup.classify(ws, NOW).stamp == {"arch": SOON, "lost": SOON}


def test_classify_never_restamps_an_existing_expiry():
    ws = _ws(_p("root", ["arch"]), _p("arch", archived=True, expires_at=PAST), roots=["root"])
    assert cleanup.classify(ws, NOW).stamp == {}


def test_classify_clears_a_stamp_when_the_page_is_findable_again():
    ws = _ws(_p("root", ["back"]), _p("back", expires_at=SOON), roots=["root"])
    assert cleanup.classify(ws, NOW).clear == ["back"]


def test_classify_prunes_only_maximal_subtree_roots():
    # Parent and child both expired: only the parent is named.
    ws = _ws(_p("root", ["arch"]),
             _p("arch", ["kid"], archived=True, expires_at=PAST),
             _p("kid", expires_at=PAST), roots=["root"])
    assert cleanup.classify(ws, NOW).prune == ["arch"]


def test_classify_prunes_an_expired_unfiled_orphan():
    ws = _ws(_p("root"), _p("lost", expires_at=PAST), roots=["root"])
    assert cleanup.classify(ws, NOW).prune == ["lost"]


def test_classify_does_not_prune_an_unfiled_orphan_before_its_expiry():
    ws = _ws(_p("root"), _p("lost", expires_at=SOON), roots=["root"])
    assert cleanup.classify(ws, NOW).prune == []


def test_delete_subtree_removes_every_descendant():
    ws = _ws(_p("root", ["arch"]), _p("arch", ["kid"], archived=True), _p("kid"), roots=["root"])
    assert cleanup.delete_subtree(ws, "arch") == {"arch", "kid"}
    assert set(ws.pages) == {"root"}


def test_delete_subtree_unlinks_from_its_parent():
    ws = _ws(_p("root", ["arch"]), _p("arch", archived=True), roots=["root"])
    cleanup.delete_subtree(ws, "arch")
    assert ws.pages["root"].child_ids == []


def test_delete_subtree_unlinks_a_top_level_page_from_root_page_ids():
    ws = _ws(_p("a", archived=True), _p("b"), roots=["a", "b"])
    cleanup.delete_subtree(ws, "a")
    assert ws.root_page_ids == ["b"]


def test_delete_subtree_strips_inbound_links_from_survivors():
    survivor = _p("live")
    survivor.links = [{"to": "arch", "role": "relates-to"}, {"to": "live2", "role": "x"}]
    ws = _ws(_p("root", ["live", "arch", "live2"]), survivor, _p("arch", archived=True),
             _p("live2"), roots=["root"])
    cleanup.delete_subtree(ws, "arch")
    assert ws.pages["live"].links == [{"to": "live2", "role": "x"}]


def test_run_once_sweeps_every_workspace(tmp_path):
    store = Store(tmp_path)
    for name in ("one", "two"):
        workspace = store.create_workspace(name)
        page = store.create_page(workspace.id, "test-fields", "Bye").page
        store.archive_page(workspace.id, page.id)

    reports = cleanup.run_once(store, now=NOW)

    assert len(reports) == 2
    assert all(report.stamped == 1 for report in reports)


def test_run_once_survives_one_bad_workspace(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.create_workspace("good")
    bad = store.create_workspace("bad")
    real = Store.cleanup_workspace

    def selective(self, workspace_id, *args, **kwargs):
        if workspace_id == bad.id:
            raise RuntimeError("corrupt")
        return real(self, workspace_id, *args, **kwargs)
    monkeypatch.setattr(Store, "cleanup_workspace", selective)

    reports = cleanup.run_once(store, now=NOW)

    assert len(reports) == 2                                    # both reported
    failed = [report for report in reports if report.error is not None]
    assert len(failed) == 1 and "corrupt" in failed[0].error    # the good one still ran


def test_start_scheduler_is_idempotent(tmp_path):
    store = Store(tmp_path)

    async def scenario():
        cleanup.start_scheduler(store)
        first = cleanup._task
        assert first is not None
        cleanup.start_scheduler(store)          # second call must not replace the task
        assert cleanup._task is first
        await cleanup.stop_scheduler()
        assert cleanup._task is None

    asyncio.run(scenario())


def test_stop_scheduler_is_safe_when_nothing_is_running():
    asyncio.run(cleanup.stop_scheduler())       # must not raise


def test_scheduler_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTA_CLEANUP", "0")
    store = Store(tmp_path)

    async def scenario():
        cleanup.start_scheduler(store)
        assert cleanup._task is None

    asyncio.run(scenario())
