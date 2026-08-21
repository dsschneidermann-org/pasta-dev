"""The recurring workspace cleanup job: stamp, back up, prune.

Hourly at five past, each workspace is swept and a uniform expiry stamped on pages
that can no longer be found - archived pages, the pages hidden underneath them, and
pages filed nowhere. Once that expiry passes the page and its subtree are deleted,
backup first.

Classification is pure, so it unit-tests with no filesystem; the store owns the
transaction. This module never imports store - the dependency runs store -> cleanup.

The timer is one module-level task, started through an idempotent `start_scheduler`
from both `server.app_lifespan` and `hmr_server.reloader_lifespan` (only the latter
runs under the dev server). The module is hot-reloadable: it cancels the running task
before the reloader replaces it, and hmr_server restarts it on the new code.

The loop wakes every `MAX_SLEEP_SECONDS` and sweeps when the tick has just gone by,
rather than sleeping the whole hour to it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from reactivity.hmr.hooks import on_dispose

from .model import Workspace

CLEANUP_MINUTE = 5           # the sweep fires at :05 past every hour
GRACE_DAYS = 5               # an expiry lands this many days ahead...
EXPIRY_HOUR_UTC = 12         # ...at exactly 12:00 UTC
MAX_SLEEP_SECONDS = 30       # the loop wakes this often instead of sleeping to the tick
SWEEP_PERIOD_SECONDS = 3600  # the hour that seconds_until_next_run counts down within

# Uvicorn's status logger, so sweep results land beside its own output (see hmr_server).
logger = logging.getLogger("uvicorn.error")


def expiry_for(now: datetime) -> str:
    """12:00 UTC on the date `GRACE_DAYS` after `now`.

    Uniform, so pages stamped on the same day share one deadline; real grace therefore
    ranges from 4 days 12 hours to 5 days 12 hours.
    """
    day = (now.astimezone(timezone.utc) + timedelta(days=GRACE_DAYS)).date()
    return datetime(day.year, day.month, day.day, EXPIRY_HOUR_UTC, tzinfo=timezone.utc).isoformat()


def seconds_until_next_run(now: datetime) -> float:
    """Seconds to the next HH:05:00 UTC - never 0, so the loop cannot spin."""
    now = now.astimezone(timezone.utc)
    target = now.replace(minute=CLEANUP_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(hours=1)
    return (target - now).total_seconds()


# --- classification (pure) ---------------------------------------------------


@dataclass(frozen=True)
class Reachability:
    findable: set[str]   # reached from root_page_ids via child_ids, nothing archived on the path
    hidden: set[str]     # reached, but some page on the path (maybe itself) is archived
    unfiled: set[str]    # never reached by the walk at all


def reachability(workspace: Workspace) -> Reachability:
    """Sort every page into findable / hidden / unfiled.

    Walks down from root_page_ids through child_ids - the structure the tree renders
    from. `parent_id` is ignored, so a stale pointer cannot cause a deletion. `hidden`
    covers an archived page and the pages beneath it, which keep `archived=False` yet
    cannot be found.
    """
    findable: set[str] = set()
    hidden: set[str] = set()
    seen: set[str] = set()
    stack: list[tuple[str, bool]] = [(page_id, False) for page_id in reversed(workspace.root_page_ids)]
    while stack:
        page_id, shadowed = stack.pop()
        if page_id in seen:
            continue                       # cycle guard
        page = workspace.pages.get(page_id)
        if page is None:
            continue                       # dangling child id; the validator reports it
        seen.add(page_id)
        shadowed = shadowed or page.archived
        (hidden if shadowed else findable).add(page_id)
        stack.extend((child_id, shadowed) for child_id in reversed(page.child_ids))
    return Reachability(findable=findable, hidden=hidden, unfiled=set(workspace.pages) - seen)


@dataclass(frozen=True)
class Sweep:
    stamp: dict[str, str]   # page id -> expiry to write; only pages carrying none today
    clear: list[str]        # page ids findable again - drop the stamp
    prune: list[str]        # maximal subtree-root ids whose expiry is at or before now


@dataclass(frozen=True)
class SweepReport:
    """What one workspace's pass did. `error` set means nothing was written."""
    workspace_id: str
    stamped: int
    cleared: int
    pruned: list[str]       # every page id removed, subtrees expanded
    backup: str | None      # path written, or None when nothing was pruned
    error: str | None


def _descendants(workspace: Workspace, page_id: str) -> set[str]:
    """`page_id` and every page reachable from it through child_ids (cycle-safe)."""
    out: set[str] = set()
    stack = [page_id]
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        page = workspace.pages.get(current)
        if page is not None:
            stack.extend(page.child_ids)
    return out


def classify(workspace: Workspace, now: datetime) -> Sweep:
    """Decide one workspace's pass: what to stamp, clear and prune.

    A page already carrying an expiry is never re-stamped, or the deadline would move
    every hour and nothing would ever expire; a page that is findable again has its
    stamp dropped. `prune` names only maximal subtree roots, so a nested expired page
    is removed once, with its parent.
    """
    reach = reachability(workspace)
    targets = reach.hidden | reach.unfiled          # both orphan arms
    expiry = expiry_for(now)
    stamp = {page_id: expiry for page_id in sorted(targets)
             if workspace.pages[page_id].expires_at is None}
    clear = [page_id for page_id in sorted(workspace.pages)
             if page_id not in targets and workspace.pages[page_id].expires_at is not None]
    expired = {page_id for page_id in targets
               if (stamped := workspace.pages[page_id].expires_at) is not None
               and datetime.fromisoformat(stamped) <= now}
    covered = {child for page_id in expired for child in _descendants(workspace, page_id) - {page_id}}
    return Sweep(stamp=stamp, clear=clear, prune=sorted(expired - covered))


def delete_subtree(workspace: Workspace, root_id: str) -> set[str]:
    """Remove `root_id` and every descendant in place, returning the ids removed.

    The whole subtree goes and the root is unlinked from wherever it was filed;
    deleting the flagged page alone would leave its children filed nowhere. Links from
    surviving pages to removed ones are stripped so none dangle.
    """
    removed = _descendants(workspace, root_id)
    for page_id in removed:
        _ = workspace.pages.pop(page_id, None)
    if root_id in workspace.root_page_ids:
        workspace.root_page_ids.remove(root_id)
    for page in workspace.pages.values():
        if root_id in page.child_ids:
            page.child_ids.remove(root_id)
        page.links = [link for link in page.links if link.get("to") not in removed]
    return removed


# --- the sweep pass ----------------------------------------------------------


def run_once(store: Any, now: datetime | None = None) -> list[SweepReport]:
    """One pass over every workspace. Blocking; the scheduler runs it in a thread.

    Each workspace is swept in its own try/except, so one bad workspace neither ends
    the pass nor kills the timer. `store` is loosely typed to keep this module free of
    a store import.
    """
    now = now or datetime.now(timezone.utc)
    reports: list[SweepReport] = []
    for entry in store.list_workspaces():
        workspace_id = entry["id"]
        try:
            report = store.cleanup_workspace(workspace_id, now)
        except Exception as exc:               # one bad workspace must not end the pass
            logger.exception("[cleanup] %s failed", workspace_id)
            report = SweepReport(workspace_id, 0, 0, [], None, str(exc))
        if report.stamped or report.cleared or report.pruned or report.error:
            logger.info("[cleanup] %s stamped=%d cleared=%d pruned=%d backup=%s",
                        workspace_id, report.stamped, report.cleared,
                        len(report.pruned), report.backup)
        reports.append(report)
    return reports


# --- the timer ---------------------------------------------------------------

# The single live sweep task, module-level so start_scheduler is idempotent across the
# two lifespans that both call it.
_task: asyncio.Task[None] | None = None


def scheduler_enabled() -> bool:
    """False when PASTA_CLEANUP=0; any other value (or unset) enables the timer."""
    return os.environ.get("PASTA_CLEANUP", "1") != "0"


async def _loop(store: Any) -> None:
    while True:
        await asyncio.sleep(MAX_SLEEP_SECONDS)
        # Sweep when the tick has just gone by - within one sleep of waking.
        elapsed = SWEEP_PERIOD_SECONDS - seconds_until_next_run(datetime.now(timezone.utc))
        if elapsed >= MAX_SLEEP_SECONDS:
            continue
        try:
            _ = await asyncio.to_thread(run_once, store)   # blocking I/O off the loop
        except asyncio.CancelledError:
            raise                              # stop_scheduler's cancel must propagate
        except Exception:
            logger.exception("[cleanup] sweep failed; the timer continues")


def start_scheduler(store: Any) -> None:
    """Start the hourly sweep. Idempotent, so both lifespans can safely call it."""
    global _task
    if _task is not None and not _task.done():
        return
    if not scheduler_enabled():
        logger.info("[cleanup] disabled by PASTA_CLEANUP=0")
        return
    _task = asyncio.create_task(_loop(store))
    logger.info("[cleanup] scheduled hourly at :%02d UTC", CLEANUP_MINUTE)


async def stop_scheduler() -> None:
    """Cancel the sweep task and await its exit. Safe when none is running."""
    global _task
    task, _task = _task, None
    if task is None:
        return
    _ = task.cancel()
    with suppress(asyncio.CancelledError):
        await task


# --- hot reload --------------------------------------------------------------


def _stop_for_reload() -> None:
    """Cancel the sweep just before the reloader replaces this module.

    Without it the old task survives into the new namespace, still running the old
    code with nothing left holding a handle to cancel it. Restarting is hmr_server's
    job (`cleanup_reload_effect`).
    """
    global _task
    if _task is not None:
        _ = _task.cancel()
        _task = None


with suppress(KeyError):   # not a reactive module under pytest or --stdio
    on_dispose(_stop_for_reload)
