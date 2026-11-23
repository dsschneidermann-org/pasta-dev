"""The live views' pure half: the digest a tab and the server compare to tell whether the tab's
drawing is still current."""

from __future__ import annotations

import hashlib
import json


def items_digest(items: object) -> str:
    """A short digest of the items a live view is built from: equal items in the same order give the
    same digest, and adding, removing, changing or reordering any item changes it."""
    text = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
