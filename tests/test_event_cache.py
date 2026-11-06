"""Tests for the transient per-page event record (src.event_cache)."""

import ast
from pathlib import Path

import pytest

from src import event_cache as event_cache_module
from src.event_cache import set_enabled


def _record_event(cache, now=100.0, ttl_seconds=300.0):
    cache.record("ws:1", "page", "event", now, ttl_seconds)
    return cache


def test_an_event_never_recorded_is_due(event_cache):
    assert event_cache.is_due("ws:1", "page", "event", 0.0)


def test_an_event_is_not_due_up_to_and_including_its_ttl(event_cache):
    assert not _record_event(event_cache).is_due("ws:1", "page", "event", 400.0)


def test_an_event_past_its_ttl_is_due(event_cache):
    assert _record_event(event_cache).is_due("ws:1", "page", "event", 400.1)


def test_recording_again_restarts_the_ttl(event_cache):
    cache = _record_event(event_cache)
    cache.record("ws:1", "page", "event", 350.0, 300.0)
    assert not cache.is_due("ws:1", "page", "event", 600.0)


def test_each_entry_keeps_its_own_ttl(event_cache):
    cache = _record_event(event_cache, ttl_seconds=10.0)
    cache.record("ws:1", "page", "other", 100.0, 300.0)
    assert cache.is_due("ws:1", "page", "event", 200.0)
    assert not cache.is_due("ws:1", "page", "other", 200.0)


def test_events_are_kept_per_workspace_page_and_event(event_cache):
    cache = _record_event(event_cache)
    assert cache.is_due("ws:2", "page", "event", 100.0)
    assert cache.is_due("ws:1", "other", "event", 100.0)
    assert cache.is_due("ws:1", "page", "other", 100.0)


def test_recording_drops_expired_entries(event_cache):
    cache = _record_event(event_cache)
    cache.record("ws:1", "other", "event", 500.0, 300.0)
    assert list(cache._entries) == [("ws:1", "other", "event")]


def test_no_module_level_import_from_its_package():
    # A name read while a module executes ties it to that module's reloads, which is what this
    # cache has to avoid to keep its record across a reload of the server around it.
    for node in ast.parse(Path(event_cache_module.__file__).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("src")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("src") for alias in node.names)


def _assert_switch(cache, setting, on):
    set_enabled(setting)
    _record_event(cache)
    assert bool(cache._entries) is on
    assert cache.is_due("ws:1", "other", "event", 100.0) is on          # a miss


@pytest.mark.parametrize("setting, on", [(None, False), (False, False), (True, True)])
def test_the_cache_is_off_in_test_mode_unless_asked_for(event_cache, setting, on):
    _assert_switch(event_cache, setting, on)


@pytest.mark.parametrize("setting, on", [(None, True), (False, False), (True, True)])
def test_the_cache_is_on_outside_test_mode_unless_turned_off(event_cache, production_mode, setting, on):
    _assert_switch(event_cache, setting, on)
