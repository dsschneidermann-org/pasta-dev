"""Unit tests for the activity log's pure half (src.activity_log): which page and workspace a tool
call belongs to and its bytes, what a write newly added to a page, and the JSONL file's encoding and
24-hour window."""

import ast
from pathlib import Path

from src.activity_log import WRITE_TOOLS, call_entry, named_page, page_additions, page_ref_ids, sent_bytes
from src.model import Page

AT = "2026-11-22T18:45:03.120456+00:00"


def test_a_call_belongs_to_its_page_then_its_link_source_then_its_parent():
    assert named_page({"workspaceId": "ws:a", "pageId": "p", "fromId": "f"}) == "p"
    assert named_page({"workspaceId": "ws:a", "fromId": "f", "toId": "t"}) == "f"
    assert named_page({"workspaceId": "ws:a", "type": "x", "title": "T", "parentId": "par"}) == "par"
    assert named_page({"workspaceId": "ws:a", "pageId": None, "parentId": "par"}) == "par"
    assert named_page({"workspaceId": "ws:a", "query": "q"}) is None
    assert named_page({"workspaceId": "ws:a", "pageId": ""}) is None


def test_sent_bytes_is_the_utf8_size_of_the_compact_arguments():
    assert sent_bytes({"a": "é"}) == len('{"a":"é"}'.encode("utf-8")) == 10


def test_a_read_carries_the_bytes_returned_and_a_write_the_bytes_sent():
    assert call_entry("getPage", {"workspaceId": "ws:a", "pageId": "p"}, 5321, AT) == (
        "ws:a", {"at": AT, "kind": "call", "pageId": "p", "tool": "getPage", "write": False, "bytes": 5321})
    args = {"workspaceId": "ws:a", "pageId": "p", "commands": [{"command": "setSummary", "args": {"text": "hi"}}]}
    assert call_entry("mutatePageBatch", args, 99999, AT) == (
        "ws:a", {"at": AT, "kind": "call", "pageId": "p", "tool": "mutatePageBatch", "write": True,
                 "bytes": sent_bytes(args)})


def test_a_workspace_wide_call_names_no_page():
    assert call_entry("search", {"workspaceId": "ws:a", "query": "x"}, 12, AT) == (
        "ws:a", {"at": AT, "kind": "call", "pageId": None, "tool": "search", "write": False, "bytes": 12})


def test_a_call_naming_no_workspace_is_not_recorded():
    assert call_entry("listWorkspaces", {}, 40, AT) is None
    assert call_entry("describePageType", {"type": "x"}, 40, AT) is None
    assert call_entry("getPage", {"workspaceId": "", "pageId": "p"}, 40, AT) is None


def _tools_sending_update() -> set[str]:
    # Every write tool tells open tabs the data changed; no read does (tests/test_live_sockets.py).
    tree = ast.parse((Path(__file__).resolve().parent.parent / "src" / "server.py").read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
            and any(ast.unparse(decorator) == "mcp.tool" for decorator in node.decorator_list)
            and any(isinstance(sub, ast.Attribute) and sub.attr == "update"
                    and isinstance(sub.value, ast.Name) and sub.value.id == "ws_reloader" for sub in ast.walk(node))}


def test_the_writes_are_exactly_the_tools_that_change_data():
    assert WRITE_TOOLS == _tools_sending_update()


def _page(links=(), sections=None):
    return Page(id="doc", type="test-blocks", title="Doc", status="draft",
                links=[dict(link) for link in links], sections=sections or {})


def test_page_ref_ids_finds_every_ref_run_once_in_first_seen_order():
    sections = {"body": {"body": [
        {"kind": "paragraph", "inlines": ["see ", {"ref": "b"}, " and ", {"ref": "a"}]},
        {"kind": "list", "items": [[{"ref": "a"}], [{"text": "x", "bold": True}, {"ref": "c"}]]},
    ]}, "summary": {"text": "plain"}}
    assert page_ref_ids(sections) == ["b", "a", "c"]


def test_a_dict_with_more_than_a_string_ref_is_not_a_ref_run():
    assert page_ref_ids([{"ref": "a", "role": "x"}, {"ref": 3}, {"to": "b"}]) == []


def test_additions_name_new_links_then_first_mentioned_refs():
    before = _page(links=[{"to": "old", "role": "relates-to"}],
                   sections={"body": {"body": [{"kind": "paragraph", "inlines": [{"ref": "kept"}]}]}})
    after = _page(links=[{"to": "old", "role": "relates-to"}, {"to": "old", "role": "depends-on"},
                         {"to": "new", "role": "relates-to"}],
                  sections={"body": {"body": [{"kind": "paragraph", "inlines": [{"ref": "kept"}, {"ref": "fresh"}]}]}})
    assert page_additions(before, after, AT) == [
        {"at": AT, "kind": "link", "pageId": "doc", "to": "old", "role": "depends-on"},
        {"at": AT, "kind": "link", "pageId": "doc", "to": "new", "role": "relates-to"},
        {"at": AT, "kind": "ref", "pageId": "doc", "to": "fresh"},
    ]


def test_rewriting_text_that_already_held_a_ref_adds_nothing():
    before = _page(sections={"body": {"body": [{"kind": "paragraph", "inlines": ["a ", {"ref": "kept"}]}]}})
    after = _page(sections={"body": {"body": [{"kind": "paragraph", "inlines": ["b ", {"ref": "kept"}]}]}})
    assert page_additions(before, after, AT) == []
