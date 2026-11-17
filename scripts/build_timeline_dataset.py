"""Build the initial back-fill of pasta's own workspace log from this repo's real history.

    uv run python scripts/build_timeline_dataset.py collect [--data-dir PATH]
    uv run python scripts/build_timeline_dataset.py build

The timeline replays a workspace's lifecycle log, which only records from the day recording
shipped. For pasta's own workspace the time before that is rebuilt from the repo's history: one page
per pull request #1-#65 of dsschneidermann-org/pasta-dev and per dated line of the initial commit
463cf4f, finished at that moment, and created when its work really started - decoded from the id of
the page that carries the PR's GitHub link.

`collect` reads - never writes - every workspace document in the data folder (the *.json files at
its root and every *.json under backups/) and records, per PR, the pages of ws:mrteq0c5-238cf6 that
carry its link, plus the workspace's Features and Bug Reports trunks, into
scripts/timeline_dataset/workspace-pages.json. `build` turns that file and the two GitHub inputs
beside it into backfill/ws_mrteq0c5-238cf6.jsonl: lines 1..N of the workspace's lifecycle log, in
the log's own line format, which the store copies into the empty log at the workspace's first write.
Every input is committed, so `build` rebuilds the file byte for byte without the data folder.

The GitHub inputs (pull-requests.json, initial-commit-463cf4f.txt) are the copies fetched through
the GitHub MCP for the timeline spike. That source kept only the time each PR's moment uses, so
pull-requests.json holds null for the other two; the moment rule reads exactly the recorded one.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))   # make `src` importable when run as a bare script

WORKSPACE_ID = "ws:mrteq0c5-238cf6"
LIVE_FILENAME = "ws_mrteq0c5-238cf6.json"
DATASET_DIR = REPO_ROOT / "scripts" / "timeline_dataset"
BACKFILL_PATH = REPO_ROOT / "backfill" / "ws_mrteq0c5-238cf6.jsonl"
PULL_REQUESTS_FILE = "pull-requests.json"
INITIAL_COMMIT_FILE = "initial-commit-463cf4f.txt"
WORKSPACE_PAGES_FILE = "workspace-pages.json"

PR_NUMBERS = range(1, 66)
EXPECTED_MOMENTS = 127
LINKED_TYPES = ("feature-brief", "simple-change", "bug-report")
PR_URL = re.compile(r"^https://github\.com/dsschneidermann-org/pasta-dev/pull/(\d+)(?:[/?#]|$)")
COMMIT_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2})  (.+)$")

HOUR_MS = 3_600_000
IMPLEMENTATION_READY_MS = 1_800_000
TESTING_READY_MS = 2_700_000
FINISH_MS = 3_600_000
# A commit line carries a date only, so a day's lines are spread evenly over 09:00-21:00 UTC.
DAY_START_MS = 9 * HOUR_MS
DAY_SPAN_MS = 12 * HOUR_MS
# Moments that land on one instant are kept apart, in order, a second each.
BUMP_MS = 1_000
FINISH_STATUS = {"feature-brief": "shipped", "simple-change": "closed", "bug-report": "closed"}

# The title rule of the dataset the user judged, which types a moment no real page is linked to.
BUG = re.compile(r"\b(fix|crash|crashing|error)\b|against the write|rejected batch"
                 r"|instead of (rejecting|crashing)", re.IGNORECASE)
SMALL_EDIT_VERBS = frozenset((
    "Rename Retire Move Clarify Drop Remove Bump Label Keep Convert Link Include Show Upgrade Write"
    " Read Resolve Match Carry Send Allow Store Replace").split())
SMALL_EDIT_PREFIXES = ("PEP8 style cleanup", "Review guidance")


class Moment(NamedTuple):
    ts: int             # epoch milliseconds
    title: str          # the PR title or the commit line's text
    pr: int | None      # the PR number; None for a commit line


# --- pure rules ------------------------------------------------------------------

def id_time_ms(page_id: str) -> int:
    """The instant a page id was created at: the base-36 milliseconds before its token's '-'."""
    token = page_id.split(":", 1)[1]
    return int(token.split("-")[0], 36)


def title_type(title: str) -> str:
    """The page type a moment with no linked page gets from its title."""
    if title.startswith("Add "):
        return "feature-brief"
    if BUG.search(title):
        return "bug-report"
    if title.split(" ")[0] in SMALL_EDIT_VERBS or title.startswith(SMALL_EDIT_PREFIXES):
        return "simple-change"
    return "feature-brief"


def linked_pages(documents: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Per PR #1-#65, the workspace's feature-brief, simple-change and bug-report pages whose pull
    request url names it, sorted by id. A page seen in several documents keeps the record of the
    first one, so the live document is read before its backups."""
    found: dict[int, dict[str, dict[str, Any]]] = {}
    for document in documents:
        if document.get("id") != WORKSPACE_ID:
            continue
        for page_id, page in document.get("pages", {}).items():
            if page.get("type") not in LINKED_TYPES:
                continue
            url = (page.get("sections", {}).get("pull_request") or {}).get("url")
            match = PR_URL.match(url) if isinstance(url, str) else None
            if match is None or int(match.group(1)) not in PR_NUMBERS:
                continue
            found.setdefault(int(match.group(1)), {}).setdefault(page_id, _page_record(page_id, page))
    return {number: [records[page_id] for page_id in sorted(records)]
            for number, records in sorted(found.items())}


def _page_record(page_id: str, page: dict[str, Any]) -> dict[str, Any]:
    def first_child(prefix: str) -> str | None:
        if page["type"] != "feature-brief":
            return None
        return next((child for child in page.get("child_ids", []) if child.startswith(prefix)), None)

    return {"id": page_id, "type": page["type"],
            "implementation_plan": first_child("implementation-plan:"),
            "testing_plan": first_child("testing-plan:")}


def workspace_pages(live: dict[str, Any], documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The workspace-pages.json value: the live document's Features and Bug Reports trunks and the
    pages carrying each PR's link across every document."""
    if live.get("id") != WORKSPACE_ID:
        raise ValueError(f"the live document is {live.get('id')!r}, not {WORKSPACE_ID}")
    pages = live.get("pages", {})
    tocs: dict[str, str] = {}
    for title in ("Features", "Bug Reports"):
        toc = next((page_id for page_id in live.get("root_page_ids", [])
                    if pages.get(page_id, {}).get("type") == "toc"
                    and pages[page_id].get("title") == title), None)
        if toc is None:
            raise ValueError(f"the live document has no root toc titled {title!r}")
        tocs[title] = toc
    return {"workspace": WORKSPACE_ID, "tocs": tocs,
            "prs": {str(number): records for number, records in linked_pages(documents).items()}}


def parse_commit_lines(text: str) -> list[tuple[str, str]]:
    """The (date, text) of each line of the initial commit's dated message lines."""
    pieces = text.split("\n")
    if pieces and pieces[-1] == "":
        pieces.pop()
    lines: list[tuple[str, str]] = []
    for piece in pieces:
        match = COMMIT_LINE.match(piece)
        if match is None:
            raise ValueError(f"not a dated commit line: {piece!r}")
        lines.append((match.group(1), match.group(2)))
    return lines


def input_problems(prs: list[dict[str, Any]], commit_lines: list[tuple[str, str]]) -> list[str]:
    """What keeps the inputs from being the repo's whole history; [] when they are complete."""
    numbers = {pr.get("number") for pr in prs}
    problems = [f"PR #{number} is missing from {PULL_REQUESTS_FILE}"
                for number in PR_NUMBERS if number not in numbers]
    problems += [f"PR #{pr.get('number')} has no merged_at, closed_at or created_at"
                 for pr in prs if _pr_time(pr) is None]
    if len(prs) + len(commit_lines) != EXPECTED_MOMENTS:
        problems.append(f"{len(prs)} PRs and {len(commit_lines)} commit lines make "
                        f"{len(prs) + len(commit_lines)} moments, not {EXPECTED_MOMENTS}")
    return problems


def _pr_time(pr: dict[str, Any]) -> str | None:
    return pr.get("merged_at") or pr.get("closed_at") or pr.get("created_at")


def _iso_ms(text: str) -> int:
    return round(datetime.fromisoformat(text).timestamp() * 1000)


def moments(prs: list[dict[str, Any]], commit_lines: list[tuple[str, str]]) -> list[Moment]:
    """Every PR and commit line as a moment, in time order and strictly increasing."""
    ranked: list[tuple[Moment, int]] = []
    for pr in prs:
        time = _pr_time(pr)
        if time is None:
            raise ValueError(f"PR #{pr['number']} has no merged_at, closed_at or created_at")
        ranked.append((Moment(_iso_ms(time), pr["title"], pr["number"]), 0))
    by_day: dict[str, list[str]] = {}
    for date, text in commit_lines:
        by_day.setdefault(date, []).append(text)
    for date, texts in by_day.items():
        day_ms = _iso_ms(f"{date}T00:00:00+00:00")
        for index, text in enumerate(texts):
            # (index + 0.5) / len(texts) of the span, rounded half up in integers
            numerator, denominator = (2 * index + 1) * DAY_SPAN_MS, 2 * len(texts)
            offset = (2 * numerator + denominator) // (2 * denominator)
            ranked.append((Moment(day_ms + DAY_START_MS + offset, text, None), 1))
    ordered: list[Moment] = []
    for moment, _ in sorted(ranked, key=lambda pair: (pair[0].ts, pair[1])):
        if ordered and moment.ts <= ordered[-1].ts:
            moment = moment._replace(ts=ordered[-1].ts + BUMP_MS)
        ordered.append(moment)
    return ordered
