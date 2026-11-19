"""Run the timeline renderer's checks under Node against a workspace's replay. See README.md here.

    uv run python scripts/tests/timeline/run_checks.py [--data-dir DIR] [--workspace WS_ID]
                                                       [--payload FILE] [--script FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))   # make `src` importable when run as a bare script

from src.errors import PastaError
from src.store import Store
from src.timeline import build_timeline

CHECKS = ("check_replay.js", "check_marks.js", "check_drag.js")
DEFAULT_WORKSPACE = "ws:mrteq0c5-238cf6"
RENDERER = _REPO_ROOT / "src" / "templates" / "_timeline.js"


def write_payload(data_dir: Path, workspace_id: str, path: Path) -> None:
    """The workspace's replay, as the timeline view would serve it now."""
    if not data_dir.is_dir():
        raise SystemExit(f"Data dir {data_dir} does not exist.")   # a mistyped path must not leave one behind
    store = Store(data_dir)
    try:
        payload = build_timeline(store.read_events(workspace_id), store.load_workspace(workspace_id), time.time())
    except PastaError as exc:
        raise SystemExit(str(exc)) from exc
    if not payload["lines"]:
        raise SystemExit(f"Workspace {workspace_id} has no timeline events in {data_dir}; nothing to replay.")
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ = parser.add_argument("--data-dir", default=os.environ.get("PASTA_DATA_DIR", ".pasta-data"),
                            help="the data dir holding the workspace and its event log")
    _ = parser.add_argument("--workspace", default=DEFAULT_WORKSPACE, help="the workspace to replay")
    _ = parser.add_argument("--payload", help="a saved timeline payload to use instead of building one")
    _ = parser.add_argument("--script", default=str(RENDERER), help="the renderer to check")
    args = parser.parse_args()

    # Assertion messages carry the button's glyphs, which a narrow console encoding cannot print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # pyright: ignore[reportAttributeAccessIssue]
    node = shutil.which("node")
    if node is None:
        print("Node.js is not on PATH; the checks run under node.", file=sys.stderr)
        return 1

    failed: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        payload = Path(args.payload) if args.payload else Path(scratch) / "payload.json"
        if not args.payload:
            write_payload(Path(args.data_dir), args.workspace, payload)
        for check in CHECKS:
            result = subprocess.run([node, str(HERE / check), str(payload), args.script],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            passed = result.returncode == 0
            print(f"{'PASS' if passed else 'FAIL'} {check}")
            output = result.stdout.strip() if passed else (result.stdout + result.stderr).strip()
            if output:
                print(textwrap.indent(output, "    "))
            if not passed:
                failed.append(check)
    print(f"{len(CHECKS) - len(failed)} of {len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
