"""The timeline model: a workspace's event log laid out as a replayable metro map.

Each feature-brief, bug-report and simple-change is a line that starts at its first logged event,
stops at a station for every one after it - an archived or deleted page's only up to its last
status change - and ends delivered, dropped, or still open. The
replay runs on a playback clock rather than the wall clock: stretches near an event play at a
quarter of a day per second, and the idle time between them is squeezed, so a project months long
replays in minutes and the drawing gives its space to the moments something happened. Every
layout number is decided here, so the browser only draws and animates.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .event_log import Event
from .model import Workspace

LINE_TYPES = ("feature-brief", "bug-report", "simple-change")   # also the colour slot order
DELIVERED = {"feature-brief": "shipped", "bug-report": "closed", "simple-change": "closed"}
DROPPED = {"feature-brief": "abandoned"}

BASE_RATE = 21_600.0          # workspace seconds per playback second: 0.25 day/s
ACTIVE_WINDOW = 3 * 3600.0    # seconds either side of an event that count as activity
IDLE_PLAYBACK = 1.0           # most playback seconds an idle gap takes
LANE_GAP = 0.4                # playback seconds kept clear between lines sharing a lane
MIN_LINE = 0.15               # playback length a zero-length line occupies when packing


@dataclass(frozen=True)
class Segment:
    """A stretch of workspace time [t0, t1] (epoch seconds) played over [p0, p1] (playback
    seconds), linearly."""
    t0: float
    t1: float
    p0: float
    p1: float


def playback_segments(times: Sequence[float], start: float, end: float, base_rate: float = BASE_RATE,
                      active_window: float = ACTIVE_WINDOW, idle_playback: float = IDLE_PLAYBACK) -> list[Segment]:
    """The playback clock over [start, end]: contiguous segments from p 0, where time within
    active_window of any of `times` plays at base_rate and each idle gap plays in at most
    idle_playback seconds - never slower than the base rate."""
    if not times or end <= start:
        return []
    windows: list[list[float]] = []
    for t in sorted(times):
        low, high = max(start, t - active_window), min(end, t + active_window)
        if windows and low <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], high)
        else:
            windows.append([low, high])

    segments: list[Segment] = []
    cursor, p = start, 0.0

    def add(t1: float, playback: float) -> None:
        nonlocal cursor, p
        if t1 > cursor:
            segments.append(Segment(cursor, t1, p, p + playback))
            cursor, p = t1, p + playback

    for low, high in windows:
        add(low, min((low - cursor) / base_rate, idle_playback))
        add(high, (high - cursor) / base_rate)
    add(end, min((end - cursor) / base_rate, idle_playback))
    return segments


def to_playback(t: float, segments: Sequence[Segment]) -> float:
    """Where workspace time `t` falls on the playback clock, clamped to the segments' span."""
    if not segments:
        return 0.0
    if t <= segments[0].t0:
        return segments[0].p0
    if t >= segments[-1].t1:
        return segments[-1].p1
    segment = segments[bisect_right([s.t0 for s in segments], t) - 1]
    return segment.p0 + (t - segment.t0) / (segment.t1 - segment.t0) * (segment.p1 - segment.p0)


def is_hidden(workspace: Workspace, page_id: str) -> bool:
    """Whether the page is out of the live tree: gone, archived, or under an archived ancestor."""
    page = workspace.pages.get(page_id)
    while page is not None:
        if page.archived:
            return True
        page = workspace.pages.get(page.parent_id) if page.parent_id else None
    return page_id not in workspace.pages


def title_path(workspace: Workspace, page_id: str) -> list[str]:
    """The titles from the page's root page down to it, following parent_id; a cycle stops the walk."""
    titles: list[str] = []
    seen: set[str] = set()
    page = workspace.pages.get(page_id)
    while page is not None and page.id not in seen:
        seen.add(page.id)
        titles.append(page.title)
        page = workspace.pages.get(page.parent_id) if page.parent_id else None
    return titles[::-1]


@dataclass(frozen=True)
class _Stop:
    at: float
    kind: str
    status: str


@dataclass(frozen=True)
class _Line:
    page_id: str
    type: str
    title: str
    path: list[str]        # the titles from its root page down to it
    stops: list[_Stop]
    end: str               # delivered | dropped | open
    end_at: float | None   # None while open: the line runs to the end of the replay


def _seconds(at: str) -> float:
    return datetime.fromisoformat(at).timestamp()


def _line(page_id: str, events: list[Event], workspace: Workspace) -> _Line:
    """One page's line from its events, already in time order."""
    times = [_seconds(event["at"]) for event in events]
    start = times[0]
    page_type = events[0]["type"]
    status, status_at = events[0].get("status", ""), start

    # The line starts at its creation; every other event adds a station.
    stops = [_Stop(start, "created", status)]
    archived = False
    for event, at in zip(events, times):
        kind = event["event"]
        if kind == "status":
            status, status_at = event.get("status", status), at
        elif kind == "archived":
            archived = True
        elif kind == "unarchived":
            archived = False
        else:
            continue
        stops.append(_Stop(at, kind, status))

    # A page still archived, or deleted, shows only its work: the line stops at its last status.
    put_away = archived or page_id not in workspace.pages
    if put_away:
        stops = [stop for stop in stops if stop.kind not in ("archived", "unarchived")]

    if status == DELIVERED.get(page_type):
        end, end_at = "delivered", status_at
    elif put_away or status == DROPPED.get(page_type):
        end, end_at = "dropped", status_at
    elif is_hidden(workspace, page_id):
        end, end_at = "dropped", max(times[-1], stops[-1].at)
    else:
        end, end_at = "open", None

    page = workspace.pages.get(page_id)
    title = page.title if page is not None else events[-1].get("title", page_id)
    path = title_path(workspace, page_id) if page is not None else [title]
    return _Line(page_id, page_type, title, path, stops, end, end_at)


def _round(value: float) -> float:
    return round(value, 3)


def build_event_timeline(events: Sequence[Event], workspace: Workspace, now: float) -> dict[str, Any]:
    """The replay of a workspace's log as plain JSON for the timeline view: the playback clock,
    one line per tracked page packed into lanes, and every station in the order it is narrated.
    The replay ends on its last station, so no time is spent on a stretch where nothing happened."""
    by_page: dict[str, list[Event]] = {}
    for event in sorted(events, key=lambda event: _seconds(event["at"])):
        if event.get("type") in LINE_TYPES:
            by_page.setdefault(event["pageId"], []).append(event)
    if not by_page:
        return {"start": _round(now), "end": _round(now), "duration": 0, "baseRate": BASE_RATE,
                "segments": [], "lanes": 0, "lines": [], "feed": []}

    lines = [_line(page_id, page_events, workspace) for page_id, page_events in by_page.items()]
    stop_times = [stop.at for line in lines for stop in line.stops]
    start, end = min(stop_times), max(stop_times)
    segments = playback_segments(stop_times, start, end)
    duration = segments[-1].p1 if segments else 0.0

    placed: list[tuple[float, float, _Line]] = []
    for line in lines:
        p0 = to_playback(line.stops[0].at, segments)
        p1 = to_playback(line.end_at, segments) if line.end_at is not None else duration
        placed.append((p0, p1, line))
    placed.sort(key=lambda item: (item[0], item[2].page_id))

    lane_ends: list[float] = []
    payload_lines: list[dict[str, Any]] = []
    for p0, p1, line in placed:
        occupied = max(p1, p0 + MIN_LINE)
        lane = next((index for index, lane_end in enumerate(lane_ends) if lane_end + LANE_GAP <= p0), None)
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(occupied)
        else:
            lane_ends[lane] = occupied
        payload_lines.append({
            "id": line.page_id, "type": line.type, "title": line.title, "path": line.path, "lane": lane,
            "p0": _round(p0), "p1": _round(p1), "end": line.end,
            # A creation only shows the initial status, so the first status change is the first station.
            "stops": [{"p": _round(to_playback(stop.at, segments)), "at": _round(stop.at),
                       "kind": stop.kind, "status": stop.status} for stop in line.stops if stop.kind != "created"],
        })

    feed = sorted(
        ({"p": stop["p"], "line": index, "stop": number}
         for index, line in enumerate(payload_lines) for number, stop in enumerate(line["stops"])),
        key=lambda entry: (entry["p"], entry["line"]),
    )
    return {
        "start": _round(start), "end": _round(end), "duration": _round(duration), "baseRate": BASE_RATE,
        "segments": [[_round(s.t0), _round(s.t1), _round(s.p0), _round(s.p1)] for s in segments],
        "lanes": len(lane_ends), "lines": payload_lines, "feed": feed,
    }
