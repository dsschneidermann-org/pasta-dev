"""Write pasta's own history into its workspace event log, which only records from its start on.

    uv run python scripts/backfill_timeline.py [--data-dir DIR] [--workspace WS_ID] [--dry-run]

Every feature-brief, bug-report and simple-change found in the workspace's backups and live file
gets its creation and its latest status, dated from the pull request it links to, else the first
commit's dated feature list, else the usual hour or two (see src/backfill.py). The pull requests
are read from the snapshot in scripts/timeline_backfill/pull_requests.json, taken from GitHub.

Re-running replaces the earlier backfill and leaves live events alone. The log is rewritten from
this process, which takes none of the server's locks, so run it while the server is not writing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))   # make `src` importable when run as a bare script

from src.backfill import Snapshot, backfill_events, merge_log, parse_feature_list, parse_pull_requests
from src.event_log import to_jsonl
from src.store import BACKUP_DIRNAME, Store

PULL_REQUESTS = Path(__file__).resolve().parent / "timeline_backfill" / "pull_requests.json"
DEFAULT_WORKSPACE = "ws:mrteq0c5-238cf6"


def _snapshot(path: Path, taken: datetime) -> Snapshot:
    return Snapshot(taken, json.loads(path.read_text(encoding="utf-8"))["pages"])


def load_snapshots(data_dir: Path, workspace_id: str, now: datetime) -> list[Snapshot]:
    """The timestamped backups, the loose backup copy if one exists, and the live file."""
    token = workspace_id.replace(":", "_")
    snapshots = [
        _snapshot(path, datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc))
        for path in sorted((data_dir / BACKUP_DIRNAME / token).glob("*.json"))
    ]
    loose = data_dir / BACKUP_DIRNAME / f"{token}.json"
    if loose.exists():
        snapshots.append(_snapshot(loose, datetime.fromtimestamp(loose.stat().st_mtime, timezone.utc)))
    snapshots.append(_snapshot(data_dir / f"{token}.json", now))
    return snapshots


def first_commit_message() -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=_REPO_ROOT, check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout
    root = git("rev-list", "--max-parents=0", "HEAD").split()[0]
    return git("show", "-s", "--format=%B", root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ = parser.add_argument("--data-dir", default=os.environ.get("PASTA_DATA_DIR", ".pasta-data"))
    _ = parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    _ = parser.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    data_dir = Path(args.data_dir)
    store = Store(data_dir)
    existing = store.read_events(args.workspace)
    live_pages = {event["pageId"] for event in existing if event.get("source") != "backfill"}

    backfill = backfill_events(
        load_snapshots(data_dir, args.workspace, now),
        parse_pull_requests(json.loads(PULL_REQUESTS.read_text(encoding="utf-8"))),
        parse_feature_list(first_commit_message()),
        live_pages,
        now,
    )
    merged = merge_log(existing, backfill)

    created = sum(event["event"] == "created" for event in backfill)
    anchors = Counter(event["anchor"] for event in backfill if event["event"] == "status")
    print(f"backfilled {created} pages: " + ", ".join(f"{kind} {count}" for kind, count in sorted(anchors.items()))
          + f", created-only {created - sum(anchors.values())}; {len(live_pages)} pages already logged live")
    if args.dry_run:
        return

    path = store.events_path(args.workspace)
    tmp = path.with_name(f"{path.name}.tmp")
    _ = tmp.write_text(to_jsonl(merged), encoding="utf-8")
    os.replace(tmp, path)
    print(f"wrote {len(merged)} events to {path}")


if __name__ == "__main__":
    main()
