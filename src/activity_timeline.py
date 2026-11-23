"""The activity timeline model: the last day of a page's or a workspace's activity, laid out on the
workspace replay's clock zoomed in until seconds apart are pixels apart.

Marks come from the lifecycle log (creation, status changes, archiving) and the activity log (every
MCP call, and the links and page refs a write added). Every layout number is decided here, so the
browser only draws and animates.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .activity_log import UNRECORDED_TOOLS, WINDOW_SECONDS, ActivityEntry, entry_seconds
from .cleanup import _descendants
from .event_log import Event
from .model import Workspace
from .timeline import LINE_TYPES, _round, _seconds, playback_segments, to_playback

ACTIVITY_RATE = 20.0      # workspace seconds per playback second: at 120 px/s one second of activity is 6 px
ACTIVITY_WINDOW = 30.0    # seconds either side of a mark that play at ACTIVITY_RATE


def _title(workspace: Workspace, page_id: str) -> str:
    page = workspace.pages.get(page_id)
    return page.title if page is not None else page_id


def _entry_mark(entry: ActivityEntry, workspace: Workspace) -> dict[str, Any] | None:
    kind, to = entry.get("kind"), entry.get("to")
    if kind == "call":
        if entry.get("tool") in UNRECORDED_TOOLS:
            return None
        return {"kind": "call", "tool": entry.get("tool"), "write": entry.get("write"), "bytes": entry.get("bytes")}
    if kind == "link" and isinstance(to, str):
        return {"kind": "link", "to": to, "title": _title(workspace, to), "role": entry.get("role")}
    if kind == "ref" and isinstance(to, str):
        return {"kind": "ref", "to": to, "title": _title(workspace, to)}
    return None


def _path(workspace: Workspace, page_id: str) -> list[str]:
    """The titles from the page's root page down to it, following parent_id; a cycle stops the walk."""
    titles: list[str] = []
    seen: set[str] = set()
    page = workspace.pages.get(page_id)
    while page is not None and page.id not in seen:
        seen.add(page.id)
        titles.append(page.title)
        page = workspace.pages.get(page.parent_id) if page.parent_id else None
    return titles[::-1]


def _line_meta(workspace: Workspace, line_id: str, logged: Event | None) -> dict[str, Any]:
    if line_id == workspace.id:
        return {"id": line_id, "title": workspace.name, "colour": "workspace", "path": [workspace.name],
                "href": f"/{workspace.id}"}
    page = workspace.pages.get(line_id)
    logged = logged or {}
    title = page.title if page is not None else logged.get("title", line_id)
    page_type = page.type if page is not None else logged.get("type")
    return {"id": line_id, "title": title, "colour": page_type if page_type in LINE_TYPES else "page",
            "path": _path(workspace, line_id) if page is not None else [title],
            "href": f"/{workspace.id}/page/{line_id}"}


def _tree_order(workspace: Workspace) -> dict[str, int]:
    """Each page's position in the order the workspace tree shows it: depth first from the root pages
    through child_ids, each page once."""
    order: dict[str, int] = {}
    stack = list(reversed(workspace.root_page_ids))
    while stack:
        page_id = stack.pop()
        if page_id in order:
            continue
        order[page_id] = len(order)
        page = workspace.pages.get(page_id)
        if page is not None:
            stack.extend(reversed(page.child_ids))
    return order


def build_activity_timeline(entries: Sequence[ActivityEntry], events: Sequence[Event],
                            workspace: Workspace, scope: str | None, now: float) -> dict[str, Any]:
    """The last day of activity of `scope` - a page and every page beneath it, or the whole
    workspace when None - as plain JSON for the activity view."""
    since = now - WINDOW_SECONDS
    members = (None if scope is None
               else _descendants(workspace, scope) if scope in workspace.pages else {scope})

    # (time, events before entries, file order, line, mark, the event behind it)
    marks: list[tuple[float, int, int, str, dict[str, Any], Event | None]] = []
    for order, event in enumerate(events):
        at = _seconds(event["at"])
        if at >= since and (members is None or event["pageId"] in members):
            marks.append((at, 0, order, event["pageId"],
                          {"kind": event["event"], "status": event.get("status", "")}, event))
    for order, entry in enumerate(entries):
        at, page_id, mark = entry_seconds(entry), entry.get("pageId"), _entry_mark(entry, workspace)
        if at < since or mark is None:
            continue
        if page_id is None and members is None:
            marks.append((at, 1, order, workspace.id, mark, None))
        elif isinstance(page_id, str) and (members is None or page_id in members):
            marks.append((at, 1, order, page_id, mark, None))
    if not marks:
        return {"start": _round(now), "end": _round(now), "duration": 0, "baseRate": ACTIVITY_RATE,
                "segments": [], "lanes": 0, "lines": [], "feed": []}

    marks.sort(key=lambda mark: mark[:3])
    times = [mark[0] for mark in marks]
    segments = playback_segments(times, times[0], times[-1], base_rate=ACTIVITY_RATE,
                                 active_window=ACTIVITY_WINDOW)
    duration = segments[-1].p1 if segments else 0.0

    by_line: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    logged: dict[str, Event] = {}
    for at, _source, _order, line_id, mark, event in marks:
        by_line.setdefault(line_id, []).append((at, mark))
        if event is not None:
            logged[line_id] = event              # marks are in time order, so this ends on the latest

    # Lines follow the page hierarchy, one lane each, so a parent always sits right above its children.
    position = _tree_order(workspace)

    def line_order(line_id: str) -> tuple[int, int, float, str]:
        if line_id == workspace.id:
            return (0, 0, 0.0, "")
        if line_id in position:
            return (1, position[line_id], 0.0, "")
        return (2, 0, by_line[line_id][0][0], line_id)       # outside the tree: by first activity

    lines: list[dict[str, Any]] = [
        {**_line_meta(workspace, line_id, logged.get(line_id)), "lane": lane,
         "p0": _round(to_playback(by_line[line_id][0][0], segments)),
         "p1": _round(to_playback(by_line[line_id][-1][0], segments)),
         "marks": [{"p": _round(to_playback(at, segments)), "at": _round(at), **mark}
                   for at, mark in by_line[line_id]]}
        for lane, line_id in enumerate(sorted(by_line, key=line_order))]

    feed = sorted(({"p": mark["p"], "line": index, "mark": number}
                   for index, line in enumerate(lines) for number, mark in enumerate(line["marks"])),
                  key=lambda entry: (entry["p"], entry["line"], entry["mark"]))
    return {"start": _round(times[0]), "end": _round(times[-1]), "duration": _round(duration),
            "baseRate": ACTIVITY_RATE,
            "segments": [[_round(s.t0), _round(s.t1), _round(s.p0), _round(s.p1)] for s in segments],
            "lanes": len(lines), "lines": lines, "feed": feed}
