"""Tests for the transient per-page event record (src.event_cache)."""

import ast
from pathlib import Path

import pytest

from src import event_cache
from src.event_cache import EventCache


@pytest.fixture(autouse=True)
def cache_on(monkeypatch):
    """The cache is off in test mode, which only the switch tests below want."""
    monkeypatch.setenv("PASTA_EVENT_CACHE", "1")


def _cache_with_event(now=100.0, ttl_seconds=300.0):
    cache = EventCache()
    cache.record("ws:1", "page", "event", now, ttl_seconds)
    return cache


def test_an_event_never_recorded_is_due():
    assert EventCache().is_due("ws:1", "page", "event", 0.0)


def test_an_event_is_not_due_up_to_and_including_its_ttl():
    assert not _cache_with_event().is_due("ws:1", "page", "event", 400.0)


def test_an_event_past_its_ttl_is_due():
    assert _cache_with_event().is_due("ws:1", "page", "event", 400.1)


def test_force_makes_a_live_event_due():
    assert _cache_with_event().is_due("ws:1", "page", "event", 100.0, force=True)


def test_recording_again_restarts_the_ttl():
    cache = _cache_with_event()
    cache.record("ws:1", "page", "event", 350.0, 300.0)
    assert not cache.is_due("ws:1", "page", "event", 600.0)


def test_each_entry_keeps_its_own_ttl():
    cache = _cache_with_event(ttl_seconds=10.0)
    cache.record("ws:1", "page", "other", 100.0, 300.0)
    assert cache.is_due("ws:1", "page", "event", 200.0)
    assert not cache.is_due("ws:1", "page", "other", 200.0)


def test_events_are_kept_per_workspace_page_and_event():
    cache = _cache_with_event()
    assert cache.is_due("ws:2", "page", "event", 100.0)
    assert cache.is_due("ws:1", "other", "event", 100.0)
    assert cache.is_due("ws:1", "page", "other", 100.0)


def test_recording_drops_expired_entries():
    cache = _cache_with_event()
    cache.record("ws:1", "other", "event", 500.0, 300.0)
    assert list(cache._entries) == [("ws:1", "other", "event")]


def test_no_module_level_import_from_its_package():
    # A name read while a module executes ties it to that module's reloads, which is what this
    # cache has to avoid to keep its record across a reload of the server around it.
    for node in ast.parse(Path(event_cache.__file__).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("src")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("src") for alias in node.names)


def _assert_switch(monkeypatch, setting, on):
    monkeypatch.delenv("PASTA_EVENT_CACHE", raising=False)
    if setting is not None:
        monkeypatch.setenv("PASTA_EVENT_CACHE", setting)
    cache = _cache_with_event()
    assert bool(cache._entries) is on
    assert cache.is_due("ws:1", "other", "event", 100.0) is on          # a miss
    assert cache.is_due("ws:1", "page", "event", 100.0, force=True) is on


@pytest.mark.parametrize("setting, on", [(None, False), ("0", False), ("1", True)])
def test_the_cache_is_off_in_test_mode_unless_asked_for(monkeypatch, setting, on):
    _assert_switch(monkeypatch, setting, on)


@pytest.mark.parametrize("setting, on", [(None, True), ("0", False), ("1", True)])
def test_the_cache_is_on_outside_test_mode_unless_turned_off(monkeypatch, production_mode, setting, on):
    _assert_switch(monkeypatch, setting, on)
