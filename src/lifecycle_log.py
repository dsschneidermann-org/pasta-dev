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

from .model import Page, Workspace
from .pagetypes.core.fields import FieldSpec
from .pagetypes.core.pagetype import PageType, initial_sections
from .pagetypes.core.specs import LIST

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


def _edited(page_id: str, section: str, field: str) -> Event:
    return {"page": page_id, "kind": "edited", "section": section, "field": field}


def _el_added(page_id: str, section: str, field: str, el: str, el_status: str | None) -> Event:
    return {"page": page_id, "kind": "el_added", "section": section, "field": field, "el": el,
            "status": el_status}


def _el_status(page_id: str, section: str, field: str, el: str, from_: str, to: str) -> Event:
    return {"page": page_id, "kind": "el_status", "section": section, "field": field, "el": el,
            "from": from_, "to": to}


def _el_edited(page_id: str, section: str, field: str, el: str) -> Event:
    return {"page": page_id, "kind": "el_edited", "section": section, "field": field, "el": el}


def _el_removed(page_id: str, section: str, field: str, el: str) -> Event:
    return {"page": page_id, "kind": "el_removed", "section": section, "field": field, "el": el}


# --- deriving one commit's events --------------------------------------------

def diff_page(before: Page, after: Page, page_type: PageType | None) -> list[Event]:
    """The events that take `before` to `after`: renamed, linked, unlinked, edited, the element
    events, and status last.

    The before side is normalised the way the command core normalises its working copy, so a field
    the type gained since the page was stored, or a fixed field it refreshes, is not an edit. With
    no page type only the title, links and status are compared.
    """
    page_id = after.id
    events: list[Event] = []
    if before.title != after.title:
        events.append(renamed(page_id, before.title, after.title))
    before_links = [(link["to"], link["role"]) for link in before.links]
    after_links = [(link["to"], link["role"]) for link in after.links]
    events += [linked(page_id, to, role) for to, role in after_links if (to, role) not in before_links]
    events += [unlinked(page_id, to, role) for to, role in before_links if (to, role) not in after_links]
    if page_type is not None:
        before_sections = initial_sections(page_type, before.sections)
        element_events: list[Event] = []
        for section in page_type.sections:
            for field_spec in section.fields:
                old = before_sections.get(section.key, {}).get(field_spec.key)
                new = after.sections.get(section.key, {}).get(field_spec.key)
                if field_spec.kind == LIST:
                    element_events += _diff_list(page_id, section.key, field_spec, old, new)
                elif old != new:
                    events.append(_edited(page_id, section.key, field_spec.key))
        events += element_events
    if before.status != after.status:
        events.append(status(page_id, before.status, after.status))
    return events


def _elements_by_id(value: Any) -> dict[str, dict[str, Any]]:
    """A list field's elements keyed by id; an element without a string id cannot be followed."""
    if not isinstance(value, list):
        return {}
    return {element["id"]: element for element in value
            if isinstance(element, dict) and isinstance(element.get("id"), str)}


def _diff_list(page_id: str, section: str, field_spec: FieldSpec, old: Any, new: Any) -> list[Event]:
    field = field_spec.key
    has_fsm = field_spec.element_fsm is not None
    before = _elements_by_id(old)
    after = _elements_by_id(new)
    events: list[Event] = []
    for el, element in after.items():
        prior = before.get(el)
        if prior is None:
            events.append(_el_added(page_id, section, field, el,
                                    element.get("status") if has_fsm else None))
        elif has_fsm and prior.get("status") != element.get("status"):
            events.append(_el_status(page_id, section, field, el,
                                     prior.get("status"), element.get("status")))
        elif prior != element:
            events.append(_el_edited(page_id, section, field, el))
    events += [_el_removed(page_id, section, field, el) for el in before if el not in after]
    return events


def baseline(workspace: Workspace) -> list[Event]:
    """One present event per page, parents before children: the tree in pre-order from the root
    pages, archived pages included, then the pages the tree does not reach in id order, each
    preceded by its own unreached ancestors."""
    order: list[str] = []
    seen: set[str] = set()
    stack = list(reversed(workspace.root_page_ids))
    while stack:
        page_id = stack.pop()
        if page_id in seen or page_id not in workspace.pages:
            continue
        seen.add(page_id)
        order.append(page_id)
        stack.extend(reversed(workspace.pages[page_id].child_ids))
    for page_id in sorted(set(workspace.pages) - seen):
        chain: list[str] = []
        current: str | None = page_id
        while current is not None and current in workspace.pages and current not in seen \
                and current not in chain:
            chain.append(current)
            current = workspace.pages[current].parent_id
        for ancestor in reversed(chain):
            seen.add(ancestor)
            order.append(ancestor)
    return [present(workspace.pages[page_id]) for page_id in order]


def sweep_events(workspace: Workspace, pruned_ids: list[str]) -> list[Event]:
    """What a cleanup sweep that deletes `pruned_ids` does, read off the workspace before it runs:
    every link a surviving page loses, then each deleted page with its last values."""
    pruned = set(pruned_ids)
    events = [unlinked(page.id, link["to"], link["role"])
              for page in workspace.pages.values() if page.id not in pruned
              for link in page.links if link.get("to") in pruned]
    return events + [deleted(workspace.pages[page_id]) for page_id in pruned_ids
                     if page_id in workspace.pages]


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
