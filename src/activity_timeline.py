"""The activity timeline model: the last day of a page's or a workspace's activity, laid out on the
workspace replay's clock zoomed in until seconds apart are pixels apart.

Marks come from the lifecycle log (creation, status changes, archiving) and the activity log (every
MCP call, and the links and page refs a write added). Every layout number is decided here, so the
browser only draws and animates.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .activity_log import WINDOW_SECONDS, ActivityEntry, entry_seconds
from .cleanup import _descendants
from .event_log import Event
from .model import Workspace
from .timeline import LANE_GAP, LINE_TYPES, MIN_LINE, _round, _seconds, playback_segments, to_playback

ACTIVITY_RATE = 20.0      # workspace seconds per playback second: at 120 px/s one second of activity is 6 px
ACTIVITY_WINDOW = 30.0    # seconds either side of a mark that play at ACTIVITY_RATE


def _title(workspace: Workspace, page_id: str) -> str:
    page = workspace.pages.get(page_id)
    return page.title if page is not None else page_id


def _entry_mark(entry: ActivityEntry, workspace: Workspace) -> dict[str, Any] | None:
    kind, to = entry.get("kind"), entry.get("to")
    if kind == "call":
        return {"kind": "call", "tool": entry.get("tool"), "write": entry.get("write"), "bytes": entry.get("bytes")}
    if kind == "link" and isinstance(to, str):
        return {"kind": "link", "to": to, "title": _title(workspace, to), "role": entry.get("role")}
    if kind == "ref" and isinstance(to, str):
        return {"kind": "ref", "to": to, "title": _title(workspace, to)}
    return None


def _line_meta(workspace: Workspace, line_id: str, logged: Event | None) -> dict[str, Any]:
    if line_id == workspace.id:
        return {"id": line_id, "title": workspace.name, "colour": "workspace", "href": f"/{workspace.id}"}
    page = workspace.pages.get(line_id)
    logged = logged or {}
    title = page.title if page is not None else logged.get("title", line_id)
    page_type = page.type if page is not None else logged.get("type")
    return {"id": line_id, "title": title, "colour": page_type if page_type in LINE_TYPES else "page",
            "href": f"/{workspace.id}/page/{line_id}"}


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

    placed = sorted(((to_playback(line_marks[0][0], segments), to_playback(line_marks[-1][0], segments), line_id)
                     for line_id, line_marks in by_line.items()), key=lambda item: (item[0], item[2]))
    lane_ends: list[float] = []
    lines: list[dict[str, Any]] = []
    for p0, p1, line_id in placed:
        occupied = max(p1, p0 + MIN_LINE)
        lane = next((index for index, lane_end in enumerate(lane_ends) if lane_end + LANE_GAP <= p0), None)
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(occupied)
        else:
            lane_ends[lane] = occupied
        lines.append({**_line_meta(workspace, line_id, logged.get(line_id)), "lane": lane,
                      "p0": _round(p0), "p1": _round(p1),
                      "marks": [{"p": _round(to_playback(at, segments)), "at": _round(at), **mark}
                                for at, mark in by_line[line_id]]})

    feed = sorted(({"p": mark["p"], "line": index, "mark": number}
                   for index, line in enumerate(lines) for number, mark in enumerate(line["marks"])),
                  key=lambda entry: (entry["p"], entry["line"], entry["mark"]))
    return {"start": _round(times[0]), "end": _round(times[-1]), "duration": _round(duration),
            "baseRate": ACTIVITY_RATE,
            "segments": [[_round(s.t0), _round(s.t1), _round(s.p0), _round(s.p1)] for s in segments],
            "lanes": len(lane_ends), "lines": lines, "feed": feed}
