"""Integration tests for the store's activity log: the per-workspace `.activity.jsonl`, what reads it
back, what keeps it to the last day, and which writes record the links and refs they added."""

import logging
import time
from datetime import datetime, timezone

import pytest

from src.activity_log import to_jsonl
from src.errors import ValidationError
from src.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def _entry(hours_ago: float, tool: str = "getPage") -> dict:
    at = datetime.fromtimestamp(time.time() - hours_ago * 3600, timezone.utc).isoformat()
    return {"at": at, "kind": "call", "pageId": "p", "tool": tool, "write": False, "bytes": 1}


def test_appended_entries_read_back_in_order(store):
    workspace = store.create_workspace("demo")
    first, second = _entry(0.1, "getPage"), _entry(0, "tree")
    store.append_activity(workspace.id, [first])
    store.append_activity(workspace.id, [second])
    assert store.read_activity(workspace.id) == [first, second]


def test_a_workspace_without_activity_reads_none(store):
    assert store.read_activity(store.create_workspace("demo").id) == []


def test_the_activity_file_is_not_listed_as_a_workspace(store, tmp_path):
    workspace = store.create_workspace("demo")
    store.append_activity(workspace.id, [_entry(0)])
    assert store.activity_path(workspace.id) == tmp_path / f"{workspace.id.replace(':', '_')}.activity.jsonl"
    assert [entry["id"] for entry in store.list_workspaces()] == [workspace.id]


def test_an_append_rewrites_the_file_once_its_oldest_line_is_an_hour_past_the_window(store):
    workspace = store.create_workspace("demo")
    stale, fresh = _entry(26), _entry(0)
    store.activity_path(workspace.id).write_text(to_jsonl([stale]), encoding="utf-8")
    store.append_activity(workspace.id, [fresh])
    assert store.read_activity(workspace.id) == [fresh]


def test_an_append_leaves_lines_just_past_the_window_on_disk(store):
    workspace = store.create_workspace("demo")
    recent_past, fresh = _entry(24.5), _entry(0)
    store.activity_path(workspace.id).write_text(to_jsonl([recent_past]), encoding="utf-8")
    store.append_activity(workspace.id, [fresh])
    assert store.read_activity(workspace.id) == [recent_past, fresh]


def test_prune_drops_every_line_older_than_the_window(store):
    workspace = store.create_workspace("demo")
    old, fresh = _entry(24.5), _entry(1)
    store.activity_path(workspace.id).write_text(to_jsonl([old, fresh]), encoding="utf-8")
    store.prune_activity(workspace.id, time.time())
    assert store.read_activity(workspace.id) == [fresh]


def test_prune_of_a_workspace_without_activity_writes_nothing(store):
    workspace = store.create_workspace("demo")
    store.prune_activity(workspace.id, time.time())
    assert not store.activity_path(workspace.id).exists()


def test_an_activity_log_that_cannot_be_written_never_raises(store, caplog):
    workspace = store.create_workspace("demo")
    store.activity_path(workspace.id).mkdir()           # a directory where the file should be
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        store.append_activity(workspace.id, [_entry(0)])
        store.prune_activity(workspace.id, time.time())
    assert "could not append to the" in caplog.text and "could not prune the" in caplog.text


def _mutate(store, workspace_id, page_id, commands):
    token = store.get_page(workspace_id, page_id).status_revision_token
    stamped = [{**command, "args": {"statusRevisionToken": token, **(command.get("args") or {})}}
               for command in commands]
    return store.mutate_page_batch(workspace_id, page_id, stamped)


def _ref_paragraph(target_id: str) -> dict:
    return {"command": "addBody", "args": {"blocks": [{"kind": "paragraph", "inlines": ["see ", {"ref": target_id}]}]}}


def _added(store, workspace_id):
    return [(entry["kind"], entry["pageId"], entry["to"]) for entry in store.read_activity(workspace_id)]


def test_a_batch_records_the_link_and_ref_it_newly_added_at_its_save_instant(store):
    workspace = store.create_workspace("demo")
    target = store.create_page(workspace.id, "test-fields", "Target").page
    doc = store.create_page(workspace.id, "test-blocks", "Doc").page
    _mutate(store, workspace.id, doc.id, [{"command": "addLink", "args": {"toId": target.id, "role": "relates-to"}},
                                          _ref_paragraph(target.id)])
    assert _added(store, workspace.id) == [("link", doc.id, target.id), ("ref", doc.id, target.id)]
    saved_at = store.load_workspace(workspace.id).updated_at
    assert {entry["at"] for entry in store.read_activity(workspace.id)} == {saved_at}


def test_mentioning_a_page_again_records_nothing_more(store):
    workspace = store.create_workspace("demo")
    target = store.create_page(workspace.id, "test-fields", "Target").page
    doc = store.create_page(workspace.id, "test-blocks", "Doc").page
    _mutate(store, workspace.id, doc.id, [_ref_paragraph(target.id)])
    _mutate(store, workspace.id, doc.id, [_ref_paragraph(target.id)])
    assert _added(store, workspace.id) == [("ref", doc.id, target.id)]


def test_a_rejected_batch_records_nothing(store):
    workspace = store.create_workspace("demo")
    target = store.create_page(workspace.id, "test-fields", "Target").page
    doc = store.create_page(workspace.id, "test-blocks", "Doc").page
    with pytest.raises(ValidationError):
        _mutate(store, workspace.id, doc.id, [_ref_paragraph(target.id), _ref_paragraph("test-fields:nope")])
    assert store.read_activity(workspace.id) == []


def test_the_link_tool_path_records_its_link(store):
    workspace = store.create_workspace("demo")
    source = store.create_page(workspace.id, "test-fields", "Source").page
    target = store.create_page(workspace.id, "test-fields", "Target").page
    store.link_page(workspace.id, source.id, target.id, "depends-on")
    [entry] = store.read_activity(workspace.id)
    assert (entry["kind"], entry["pageId"], entry["to"], entry["role"]) == ("link", source.id, target.id, "depends-on")


def test_creating_renaming_and_unlinking_record_nothing(store):
    workspace = store.create_workspace("demo")
    source = store.create_page(workspace.id, "test-fields", "Source").page
    target = store.create_page(workspace.id, "test-fields", "Target").page
    store.link_page(workspace.id, source.id, target.id, "depends-on")
    store.unlink_page(workspace.id, source.id, target.id, "depends-on")
    store.rename_page(workspace.id, source.id, "Renamed")
    assert [entry["kind"] for entry in store.read_activity(workspace.id)] == ["link"]
