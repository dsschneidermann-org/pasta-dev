"""Generate the per-page-type-state Sphinx docs and write them into the docsite.

The content is produced purely by `src.docsgen` (unit-tested); this driver only does the
I/O: it splits the emitted docs into one `docsite/page-types/<tag>-<state>.md` file each, plus a
generated `docsite/page-types/states.md` toctree index, then prints what it wrote and removed.

    uv run python scripts/gen_page_type_docs.py

Every `.md` in that directory is generated, so it deletes any the registry no longer produces,
such as the page of a state dropped from a page type. Re-run after changing the page-type registry
or the doc templates.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))   # make `src` importable when run as a bare script

from src.docsgen import STATES_INDEX_STEM, all_state_docs, render_states_index, stale_stems

PAGE_TYPES_DIR = _REPO_ROOT / "docsite" / "page-types"


def main() -> None:
    PAGE_TYPES_DIR.mkdir(parents=True, exist_ok=True)

    docs = all_state_docs()
    docs[STATES_INDEX_STEM] = render_states_index()

    written, skipped = 0, 0
    for stem, markdown in docs.items():
        path = PAGE_TYPES_DIR / f"{stem}.md"
        # A missing file is the normal case on a clean checkout (and after `just docs` wipes the
        # directory), so only an existing file is read back to skip an unchanged rewrite.
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        if existing == markdown:
            skipped += 1
            continue
        path.write_text(markdown, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(PAGE_TYPES_DIR.parent.parent)}")
        written += 1

    stale = stale_stems((path.stem for path in PAGE_TYPES_DIR.glob("*.md")), docs)
    for stem in stale:
        path = PAGE_TYPES_DIR / f"{stem}.md"
        path.unlink()
        print(f"removed {path.relative_to(PAGE_TYPES_DIR.parent.parent)}")

    print(f"\n{written} files written to {PAGE_TYPES_DIR} ({skipped} unchanged, {len(stale)} removed)")


if __name__ == "__main__":
    main()
