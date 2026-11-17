"""The pure core of the lifecycle log: what a page lifecycle event is, how one commit's events are
derived, stamped and encoded as lines, and how the stored lines are checked and served back.

Every persisted write appends one line per event to an append-only per-workspace file, so the
history of how a workspace came to be can be replayed. This module decides the events and the line
format only; the store owns the file, the clock and the locks. It imports src.model and the
page-type registry and nothing that performs I/O.
"""

from __future__ import annotations

import json
from typing import Any

from .model import Page

# One event: the event-line keys (seq, ts, page, kind, then the kind's own keys). The events a
# writer builds are unstamped - they carry no seq or ts until the commit stamps them.
type Event = dict[str, Any]


# --- event constructors ------------------------------------------------------

def created(page: Page) -> Event:
    return {"page": page.id, "kind": "created", "type": page.type, "title": page.title,
            "parent": page.parent_id, "status": page.status}


def present(page: Page) -> Event:
    """A page as it stands when recording starts. Claims nothing about when it was created."""
    return {"page": page.id, "kind": "present", "type": page.type, "title": page.title,
            "parent": page.parent_id, "status": page.status, "archived": page.archived,
            "links": [{"to": link["to"], "role": link["role"]} for link in page.links]}


def status(page_id: str, from_: str, to: str) -> Event:
    return {"page": page_id, "kind": "status", "from": from_, "to": to}


def renamed(page_id: str, old: str, new: str) -> Event:
    return {"page": page_id, "kind": "renamed", "from": old, "title": new}


def moved(page_id: str, from_parent: str | None, to_parent: str | None) -> Event:
    return {"page": page_id, "kind": "moved", "from_parent": from_parent, "to_parent": to_parent}


def linked(page_id: str, to: str, role: str) -> Event:
    return {"page": page_id, "kind": "linked", "to": to, "role": role}


def unlinked(page_id: str, to: str, role: str) -> Event:
    return {"page": page_id, "kind": "unlinked", "to": to, "role": role}


def archived(page_id: str) -> Event:
    return {"page": page_id, "kind": "archived"}


def unarchived(page_id: str) -> Event:
    return {"page": page_id, "kind": "unarchived"}


def deleted(page: Page) -> Event:
    """A page the cleanup sweep removed, with the last type, title and status it had."""
    return {"page": page.id, "kind": "deleted", "type": page.type, "title": page.title,
            "status": page.status}


# --- stamping and encoding ---------------------------------------------------

def stamp(events: list[Event], first_seq: int, ts: int) -> list[Event]:
    """New dicts numbered from `first_seq`, all at the commit instant `ts`, with seq and ts first."""
    return [{"seq": first_seq + offset, "ts": ts, "page": event["page"], "kind": event["kind"],
             **{key: value for key, value in event.items()
                if key not in ("seq", "ts", "page", "kind")}}
            for offset, event in enumerate(events)]


def encode(event: Event) -> str:
    """One log line: compact JSON in the event's key order, ended by a newline."""
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
