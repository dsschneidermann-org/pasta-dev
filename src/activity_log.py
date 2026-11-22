"""The activity log's pure half: what an entry is, which page a tool call belongs to, what counts as
a write, what a write newly added to a page, and how old is too old.

Each workspace keeps an append-only `ws_<token>.activity.jsonl` beside its events log, one JSON
object per line recording an MCP tool call with its bytes, or a link or page ref a write added. It
is kept for the last day only. The store owns the file itself.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import cast

from .model import JSONValue, Page

LOG_SUFFIX = ".activity.jsonl"
WINDOW_SECONDS = 24 * 3600.0       # activity older than this is neither shown nor kept
PRUNE_SLACK_SECONDS = 3600.0       # how far past the window the oldest line may get before an append rewrites the file
# The tools that change data; every other tool is a read.
WRITE_TOOLS = frozenset({
    "createWorkspace", "createPage", "mutatePageBatch", "setWorkspaceGuidance",
    "archiveWorkspace", "unarchiveWorkspace", "archivePage", "unarchivePage",
    "reparentPage", "reorderPage", "renamePage", "link", "unlink",
})
PAGE_ARGS = ("pageId", "fromId", "parentId")   # the argument naming a call's page; the first present wins

# One line of the log: at, kind, pageId, then a call's tool, write and bytes, or a link's to and role, or a ref's to.
type ActivityEntry = dict[str, JSONValue]


def named_page(arguments: Mapping[str, JSONValue]) -> str | None:
    """The first of PAGE_ARGS the arguments carry as a non-empty string, else None."""
    for name in PAGE_ARGS:
        value = arguments.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def sent_bytes(arguments: Mapping[str, JSONValue]) -> int:
    """The UTF-8 size of the arguments as compact JSON - what the agent sent."""
    return len(json.dumps(dict(arguments), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def call_entry(tool: str, arguments: Mapping[str, JSONValue], returned_bytes: int,
               at: str) -> tuple[str, ActivityEntry] | None:
    """The workspace a call named and its entry: a write carries the bytes it sent, a read the bytes
    returned to it. A call naming no workspace is not recorded."""
    workspace_id = arguments.get("workspaceId")
    if not isinstance(workspace_id, str) or not workspace_id:
        return None
    write = tool in WRITE_TOOLS
    return workspace_id, {"at": at, "kind": "call", "pageId": named_page(arguments), "tool": tool,
                          "write": write, "bytes": sent_bytes(arguments) if write else returned_bytes}


def page_ref_ids(value: object) -> list[str]:
    """Every page id held by an inline ref run - a dict whose only key is "ref", with a string value -
    anywhere inside `value`, each once, first seen first."""
    found: dict[str, None] = {}

    def walk(node: JSONValue) -> None:
        if isinstance(node, dict):
            if len(node) == 1 and isinstance(ref := node.get("ref"), str):
                _ = found.setdefault(ref)
                return
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    # A page's sections are JSON as stored, typed looser only because the model leaves their shape to page types.
    walk(cast(JSONValue, value))
    return list(found)


def page_additions(before: Page, after: Page, at: str) -> list[ActivityEntry]:
    """What one write newly added to a page: each link whose (to, role) pair it did not have, then each
    page ref none of its text held before."""
    old_links = {(link.get("to"), link.get("role")) for link in before.links}
    entries: list[ActivityEntry] = [
        {"at": at, "kind": "link", "pageId": after.id, "to": link["to"], "role": link["role"]}
        for link in after.links if (link.get("to"), link.get("role")) not in old_links]
    old_refs = set(page_ref_ids(before.sections))
    refs: list[ActivityEntry] = [{"at": at, "kind": "ref", "pageId": after.id, "to": ref}
                                 for ref in page_ref_ids(after.sections) if ref not in old_refs]
    return entries + refs


def to_jsonl(entries: Iterable[ActivityEntry]) -> str:
    return "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)


def _usable(value: dict[str, JSONValue]) -> bool:
    """A line no reader can place in time, or tell the kind of, is not an entry."""
    at = value.get("at")
    if not isinstance(at, str) or not isinstance(value.get("kind"), str):
        return False
    try:
        _ = datetime.fromisoformat(at)
    except ValueError:
        return False
    return True


def parse_jsonl(text: str) -> list[ActivityEntry]:
    """Every usable line in file order, so a last line torn by an append in progress cannot break a read."""
    entries: list[ActivityEntry] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value: JSONValue = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and _usable(value):
            entries.append(value)
    return entries


def entry_seconds(entry: ActivityEntry) -> float:
    return datetime.fromisoformat(str(entry["at"])).timestamp()


def within_window(entries: Iterable[ActivityEntry], now: float) -> list[ActivityEntry]:
    """The entries no older than the window, in their order."""
    since = now - WINDOW_SECONDS
    return [entry for entry in entries if entry_seconds(entry) >= since]


def needs_prune(first_line: str, now: float) -> bool:
    """Whether a file whose oldest line is `first_line` holds activity well past the window."""
    parsed = parse_jsonl(first_line)
    return bool(parsed) and entry_seconds(parsed[0]) < now - WINDOW_SECONDS - PRUNE_SLACK_SECONDS
