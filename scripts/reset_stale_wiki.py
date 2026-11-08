"""Throw away the GitNexus wiki cache when it still documents deleted files.

`gitnexus wiki` groups files into modules once and then reuses that grouping
forever: it reads `.gitnexus/wiki/module_tree.json` before anything else (even
with `--force`, which only clears `first_module_tree.json` and the pages), and a
full run skips every module whose `<slug>.md` already exists. Nothing prunes
files that have since been deleted, so a removed folder keeps its own wiki page
and keeps showing up in the overview.

This script lists every file in the cached module tree and, if any of them no
longer exists on disk, deletes the whole `.gitnexus/wiki` directory so the next
`gitnexus wiki` regroups and rewrites every page from the current graph.

    uv run python scripts/reset_stale_wiki.py

Run it from the repo root (`just sync-wiki` does). It does nothing when the
wiki has not been generated yet or every listed file still exists.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import TypedDict

WIKI_DIR = Path(".gitnexus/wiki")


class ModuleNode(TypedDict, total=False):
    files: list[str]
    children: list["ModuleNode"]


def tree_files(nodes: list[ModuleNode]) -> list[str]:
    files: list[str] = []
    for node in nodes:
        files.extend(node.get("files", []))
        files.extend(tree_files(node.get("children", [])))
    return files


def main() -> int:
    tree_path = WIKI_DIR / "module_tree.json"
    if not tree_path.exists():
        return 0
    missing = sorted({f for f in tree_files(json.loads(tree_path.read_text("utf-8"))) if not Path(f).exists()})
    if not missing:
        return 0
    print(f"Wiki module tree references {len(missing)} deleted file(s), resetting {WIKI_DIR}:")
    for f in missing:
        print(f"  {f}")
    shutil.rmtree(WIKI_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
