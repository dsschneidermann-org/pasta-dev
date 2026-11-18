"""The backfill's pure half: dating the history of pages that predate the lifecycle log.

A workspace's log only records what happens after it starts, so pasta's own earlier history is
reconstructed once from what survives of it: the workspace backups (each page's id encodes when it
was created, and the backups show which status it reached), the pull requests the pages link to,
and the dated feature list of the repository's first commit. Every page gets its creation and, when
it moved on from draft, one transition to its latest status - dated by its pull request, else by
its listed feature, else by the usual hour or two a change takes, kept consistent with the backups.
Intermediate stations are not reconstructed: the backups are days apart, so any time given to them
would be invented. The script in scripts/backfill_timeline.py gathers the inputs and writes the log.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from .event_log import Event
from .ids import id_time
from .timeline import LINE_TYPES

TYPICAL_MINUTES = (60, 120)
MATCH_THRESHOLD = 0.55
LIST_TZ = timezone(timedelta(hours=2))   # the first commit's dates are +0200 local days
PROBE_PREFIX = "[probe]"                 # pages created by the lifecycle probe script, not work
INITIAL_STATUS = "draft"                 # where every tracked page type starts

_LISTED = re.compile(r"^(\d{4}-\d{2}-\d{2})\s{2,}(\S.*)$")
_PULL = re.compile(r"/pull/(\d+)")


@dataclass(frozen=True)
class Snapshot:
    taken: datetime
    pages: Mapping[str, Mapping[str, Any]]   # page dicts as stored in the workspace file


@dataclass(frozen=True)
class PullRequest:
    number: int
    created: datetime
    merged: datetime | None
    closed: datetime | None


@dataclass(frozen=True)
class ListedFeature:
    day: date
    text: str


def parse_feature_list(message: str) -> list[ListedFeature]:
    """The 'YYYY-MM-DD  feature' lines of a commit message."""
    return [ListedFeature(date.fromisoformat(match[1]), match[2].strip())
            for line in message.splitlines() if (match := _LISTED.match(line.strip()))]


def _instant(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def parse_pull_requests(rows: Sequence[Mapping[str, Any]]) -> dict[int, PullRequest]:
    """Pull requests by number, from rows shaped like GitHub's pull request listing."""
    prs: dict[int, PullRequest] = {}
    for row in rows:
        created = _instant(row.get("created_at"))
        if isinstance(number := row.get("number"), int) and created is not None:
            prs[number] = PullRequest(number, created, _instant(row.get("merged_at")),
                                      _instant(row.get("closed_at")))
    return prs


def pr_numbers(page: Mapping[str, Any]) -> list[int]:
    """The pull request numbers in a stored page's pull_request url."""
    url = page.get("sections", {}).get("pull_request", {}).get("url")
    return sorted({int(number) for number in _PULL.findall(url)}) if isinstance(url, str) else []


def typical_lifetime(page_id: str) -> timedelta:
    """An hour or two, fixed per page so lines differ from each other but not between runs."""
    low, high = TYPICAL_MINUTES
    return timedelta(minutes=low + zlib.crc32(page_id.encode()) % (high - low + 1))


def match_listed(title: str, created: datetime, features: Sequence[ListedFeature]) -> ListedFeature | None:
    """The listed feature that names this page, if one dated no earlier than the page scores
    MATCH_THRESHOLD; the earliest wins a tie."""
    day = created.astimezone(LIST_TZ).date()
    best: ListedFeature | None = None
    best_score = -1.0
    for feature in features:
        if feature.day < day:
            continue
        score = SequenceMatcher(None, title.lower(), feature.text.lower()).ratio()
        if score > best_score:
            best, best_score = feature, score
    return best if best_score >= MATCH_THRESHOLD else None


def _created(page_id: str) -> datetime:
    born = id_time(page_id)
    if born is None:
        raise ValueError(f"Page id '{page_id}' carries no creation time.")
    return datetime.fromtimestamp(born, timezone.utc)


def status_time(page_id: str, status: str, history: Sequence[tuple[datetime, str]],
                prs: Mapping[int, PullRequest], numbers: Sequence[int],
                listed: ListedFeature | None, now: datetime) -> tuple[datetime, str]:
    """When the page reached `status`, and which source said so: 'pr', 'list' or 'estimate'.

    `history` is the page's (snapshot time, status) in snapshot order. The result is never
    before the page was created nor after `now`.
    """
    created = _created(page_id)
    typical = created + typical_lifetime(page_id)
    known = [prs[number] for number in numbers if number in prs]
    anchor = (max((pr.merged for pr in known if pr.merged), default=None)
              or max((pr.closed for pr in known if pr.closed), default=None)
              or min((pr.created for pr in known), default=None))
    if anchor is not None and anchor >= created:
        when, kind = anchor, "pr"
    elif listed is not None:
        when, kind = max(typical, datetime.combine(listed.day, typical.astimezone(LIST_TZ).timetz())), "list"
    else:
        # Keep the estimate inside the backups' window for the change: after the last one that
        # still showed another status, and no later than the first one that showed this one.
        first = next((index for index, (_, seen) in enumerate(history) if seen == status), None)
        upper = history[first][0] if first is not None else now
        lower = max((taken for taken, seen in history[:first or 0] if seen != status), default=created)
        when, kind = min(max(typical, lower), upper), "estimate"
    return min(max(when, created), now).astimezone(timezone.utc), kind


def backfill_events(snapshots: Sequence[Snapshot], prs: Mapping[int, PullRequest],
                    features: Sequence[ListedFeature], skip_page_ids: Set[str], now: datetime) -> list[Event]:
    """Creation and latest-status events for every tracked page in the snapshots, oldest first.

    Each page is read in its latest stored form. Probe pages, pages in `skip_page_ids` (the log
    already has their live history) and ids carrying no creation time are left out.
    """
    latest: dict[str, Mapping[str, Any]] = {}
    history: dict[str, list[tuple[datetime, str]]] = {}
    for snapshot in sorted(snapshots, key=lambda snapshot: snapshot.taken):
        for page_id, page in snapshot.pages.items():
            latest[page_id] = page
            history.setdefault(page_id, []).append((snapshot.taken, page.get("status", "")))

    events: list[Event] = []
    for page_id, page in latest.items():
        page_type, title, status = page.get("type"), page.get("title", ""), page.get("status", "")
        if (page_type not in LINE_TYPES or title.startswith(PROBE_PREFIX)
                or page_id in skip_page_ids or id_time(page_id) is None):
            continue
        created = _created(page_id)
        base = {"pageId": page_id, "type": page_type, "title": title}
        events.append({"at": created.isoformat(), "event": "created", **base,
                       "status": INITIAL_STATUS, "source": "backfill"})
        if status != INITIAL_STATUS:
            when, kind = status_time(page_id, status, history[page_id], prs, pr_numbers(page),
                                     match_listed(title, created, features), now)
            events.append({"at": when.isoformat(), "event": "status", **base, "status": status,
                           "from": INITIAL_STATUS, "source": "backfill", "anchor": kind})
    return sorted(events, key=lambda event: datetime.fromisoformat(event["at"]))


def merge_log(existing: Sequence[Event], backfill: Sequence[Event]) -> list[Event]:
    """The log with any earlier backfill replaced by `backfill`, sorted by time. Live lines keep
    their order, so re-running with the same backfill changes nothing."""
    live = [event for event in existing if event.get("source") != "backfill"]
    return sorted([*backfill, *live], key=lambda event: datetime.fromisoformat(event["at"]))
