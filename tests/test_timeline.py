"""Unit tests for the timeline model (src.timeline): the playback clock that plays activity at
0.25 day/s and squeezes idle time, and the metro lines built from a workspace's event log."""

import pytest

from src.timeline import (
    ACTIVE_WINDOW,
    BASE_RATE,
    IDLE_PLAYBACK,
    Segment,
    playback_segments,
    to_playback,
)

DAY = 86_400.0
HOUR = 3_600.0


def _assert_contiguous(segments: list[Segment], start: float, end: float) -> None:
    assert segments[0].t0 == start and segments[0].p0 == 0.0
    assert segments[-1].t1 == end
    for previous, current in zip(segments, segments[1:]):
        assert current.t0 == previous.t1
        assert current.p0 == previous.p1


def test_one_event_plays_its_window_at_the_base_rate_and_squeezes_the_idle_sides():
    start, end = 0.0, 10 * DAY
    event = 5 * DAY
    segments = playback_segments([event], start, end)
    _assert_contiguous(segments, start, end)
    idle_before, active, idle_after = segments
    assert (active.t0, active.t1) == (event - ACTIVE_WINDOW, event + ACTIVE_WINDOW)
    assert active.p1 - active.p0 == pytest.approx(6 * HOUR / BASE_RATE)
    assert active.p1 - active.p0 == pytest.approx(1.0)                    # 6 h at 0.25 day/s
    assert idle_before.p1 - idle_before.p0 == IDLE_PLAYBACK
    assert idle_after.p1 - idle_after.p0 == IDLE_PLAYBACK


def test_events_an_hour_apart_share_one_active_window():
    segments = playback_segments([5 * DAY, 5 * DAY + HOUR], 0.0, 10 * DAY)
    assert len(segments) == 3
    assert segments[1].t1 - segments[1].t0 == 2 * ACTIVE_WINDOW + HOUR


def test_a_short_idle_gap_plays_at_the_base_rate_rather_than_slower():
    first = 5 * DAY
    second = first + 2 * ACTIVE_WINDOW + 4 * HOUR                         # a 4 h gap between windows
    segments = playback_segments([first, second], first - ACTIVE_WINDOW, second + ACTIVE_WINDOW)
    _assert_contiguous(segments, first - ACTIVE_WINDOW, second + ACTIVE_WINDOW)
    active_1, gap, active_2 = segments
    assert gap.t1 - gap.t0 == 4 * HOUR
    assert gap.p1 - gap.p0 == pytest.approx(4 * HOUR / BASE_RATE)        # 0.667 s, not 1 s
    assert gap.p1 - gap.p0 < IDLE_PLAYBACK


@pytest.mark.parametrize("times, start, end", [([], 0.0, DAY), ([5.0], DAY, DAY), ([5.0], DAY, 0.0)])
def test_no_times_or_an_empty_span_gives_no_segments(times, start, end):
    assert playback_segments(times, start, end) == []


def test_to_playback_clamps_interpolates_and_never_runs_backwards():
    start, end = 0.0, 10 * DAY
    segments = playback_segments([2 * DAY, 7 * DAY], start, end)
    total = segments[-1].p1
    assert to_playback(-DAY, segments) == 0.0
    assert to_playback(11 * DAY, segments) == total
    active = segments[1]
    middle = (active.t0 + active.t1) / 2
    assert to_playback(middle, segments) == pytest.approx((active.p0 + active.p1) / 2)
    mapped = [to_playback(t * HOUR, segments) for t in range(0, 241)]
    assert mapped == sorted(mapped)


def test_to_playback_of_no_segments_is_zero():
    assert to_playback(123.0, []) == 0.0
