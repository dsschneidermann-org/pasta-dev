"""A transient, in-process record of recent per-page events, each expiring after its own TTL.

Nothing here is persisted, and losing an entry must only ever cost a repeated delivery, so an
event with no entry is due.

Hot reload re-executes a module when its file or a name it read while executing changes, so this
module has no module-level import from its package. That keeps the record across a reload of
everything around it, while an edit to this file still takes effect at once.
"""

from __future__ import annotations

from dataclasses import dataclass


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
        """Note that `event` happened on a page at `now`, dropping every expired entry."""
        self._entries = {key: entry for key, entry in self._entries.items()
                         if entry.is_live(now)}
        self._entries[(workspace_id, page_id, event)] = _Entry(now, ttl_seconds)

    def is_due(self, workspace_id: str, page_id: str, event: str, now: float, *,
               force: bool = False) -> bool:
        """Whether `event` should happen on a page: `force`, or no live record of it."""
        entry = self._entries.get((workspace_id, page_id, event))
        return force or entry is None or not entry.is_live(now)


page_events = EventCache()
