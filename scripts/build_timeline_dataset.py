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
from pathlib import Path
from typing import NamedTuple

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
