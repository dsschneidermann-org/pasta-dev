"""A transient, in-process record of recent per-page events, each expiring after its own TTL.

Nothing here is persisted, and losing an entry must only ever cost a repeated delivery, so an
event with no entry is due.

Hot reload re-executes a module when its file or a name it read while executing changes, so this
module imports nothing from its package. That keeps the record across a reload of everything
around it, while an edit to this file still takes effect at once.
"""

from __future__ import annotations

from dataclasses import dataclass

_enabled = True


def set_cache_disabled(disabled: bool) -> None:
    """Turn the cache off, or back on. It is on unless something turns it off."""
    global _enabled
    _enabled = not disabled


@dataclass(frozen=True)
class _Entry:
    recorded_at: float
    ttl_seconds: float

    def is_live(self, now: float) -> bool:
        return now - self.recorded_at <= self.ttl_seconds


class EventCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], _Entry] = {}

    def record(self, workspace_id: str, page_id: str, event: str, now: float,
               ttl_seconds: float) -> None:
        """Note that `event` happened on a page at `now`, dropping every expired entry. Stores
        nothing while the cache is off."""
        if not _enabled:
            return
        self._entries = {key: entry for key, entry in self._entries.items()
                         if entry.is_live(now)}
        self._entries[(workspace_id, page_id, event)] = _Entry(now, ttl_seconds)

    def is_due(self, workspace_id: str, page_id: str, event: str, now: float) -> bool:
        """Whether `event` should happen on a page: no live record of it. Never while the cache is
        off, because an empty cache would otherwise read as everything being due."""
        if not _enabled:
            return False
        entry = self._entries.get((workspace_id, page_id, event))
        return entry is None or not entry.is_live(now)


page_events = EventCache()
