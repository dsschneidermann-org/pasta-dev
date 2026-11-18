"""The timeline model: a workspace's event log laid out as a replayable metro map.

Each feature-brief, bug-report and simple-change is a line that starts when its page was created,
stops at a station for every logged event, and ends delivered, dropped, or still open. The
replay runs on a playback clock rather than the wall clock: stretches near an event play at a
quarter of a day per second, and the idle time between them is squeezed, so a project months long
replays in minutes and the drawing gives its space to the moments something happened. Every
layout number is decided here, so the browser only draws and animates.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

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


def playback_segments(times: Sequence[float], start: float, end: float) -> list[Segment]:
    """The playback clock over [start, end]: contiguous segments from p 0, where time within
    ACTIVE_WINDOW of any of `times` plays at BASE_RATE and each idle gap plays in at most
    IDLE_PLAYBACK seconds - never slower than the base rate."""
    if not times or end <= start:
        return []
    windows: list[list[float]] = []
    for t in sorted(times):
        low, high = max(start, t - ACTIVE_WINDOW), min(end, t + ACTIVE_WINDOW)
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
        add(low, min((low - cursor) / BASE_RATE, IDLE_PLAYBACK))
        add(high, (high - cursor) / BASE_RATE)
    add(end, min((end - cursor) / BASE_RATE, IDLE_PLAYBACK))
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
