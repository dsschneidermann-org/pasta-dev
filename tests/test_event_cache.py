"""Tests for the transient per-page event record (src.event_cache)."""

import ast
import runpy
from pathlib import Path

from src import event_cache as event_cache_module
from src.event_cache import set_cache_disabled


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


def test_no_import_from_its_package():
    # A name read while a module executes ties it to that module's reloads, which is what this
    # cache has to avoid to keep its record across a reload of the server around it.
    for node in ast.walk(ast.parse(Path(event_cache_module.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("src")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("src") for alias in node.names)


def test_the_cache_is_on_by_default():
    # The test run disables the cache, so read the default off a fresh run of the module.
    assert runpy.run_path(event_cache_module.__file__)["_enabled"] is True


def test_a_disabled_cache_stores_nothing(event_cache):
    set_cache_disabled(True)
    assert _record_event(event_cache)._entries == {}


def test_nothing_is_due_on_a_disabled_cache(event_cache):
    set_cache_disabled(True)
    assert not event_cache.is_due("ws:1", "page", "event", 100.0)
