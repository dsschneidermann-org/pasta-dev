"""The lifecycle event log's pure half: which events a write produced, and their JSONL encoding.

Each workspace keeps an append-only `ws_<token>.events.jsonl` beside its workspace file, one JSON
object per line recording a page's creation, a status transition, or an archive flag flipping.
The events are derived by comparing the pages' marks before a write with the workspace after it,
so every write path that records them does it the same way. The store owns the file itself.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .model import JSONValue, Page, Workspace

LOG_SUFFIX = ".events.jsonl"
EVENT_KINDS = ("created", "status", "archived", "unarchived")

# One log line: at, event, pageId, type, title, status, plus `from` on a status event. A backfilled
# line also carries `source` (and `anchor` on its status event); readers ignore keys they do not use.
type Event = dict[str, str]

# A line lacking any of these is not an event any reader can place.
_REQUIRED = ("at", "event", "pageId")


@dataclass(frozen=True)
class PageMark:
    """What of a page the log records changes to."""
    status: str
    archived: bool


def page_marks(workspace: Workspace) -> dict[str, PageMark]:
    return {page_id: PageMark(page.status, page.archived) for page_id, page in workspace.pages.items()}


def _event(kind: str, page: Page, at: str) -> Event:
    return {"at": at, "event": kind, "pageId": page.id, "type": page.type,
            "title": page.title, "status": page.status}


def lifecycle_events(before: Mapping[str, PageMark], workspace: Workspace, at: str) -> list[Event]:
    """The events that turn the marks `before` into `workspace`, in page order. A page that is
    gone from the workspace produces nothing."""
    events: list[Event] = []
    for page in workspace.pages.values():
        mark = before.get(page.id)
        if mark is None:
            events.append(_event("created", page, at))
            continue
        if page.status != mark.status:
            events.append(_event("status", page, at) | {"from": mark.status})
        if page.archived != mark.archived:
            events.append(_event("archived" if page.archived else "unarchived", page, at))
    return events


def to_jsonl(events: Iterable[Event]) -> str:
    return "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)


def parse_jsonl(text: str) -> list[Event]:
    """Every usable line in file order. A line that is not a JSON object carrying the required
    string keys is skipped, so a last line torn by an append in progress cannot break a read."""
    events: list[Event] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value: JSONValue = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and all(isinstance(value.get(key), str) for key in _REQUIRED):
            events.append({key: field for key, field in value.items() if isinstance(field, str)})
    return events
