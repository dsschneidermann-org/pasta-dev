"""Integration tests for the store's lifecycle log: which writes append which events to the
workspace's `.events.jsonl`, and that the log can never cost a write."""

import pytest

from src.errors import ConflictError
from src.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def _mutate(store, workspace_id, page_id, commands):
    token = store.get_page(workspace_id, page_id).status_revision_token
    stamped = [{**command, "args": {"statusRevisionToken": token, **(command.get("args") or {})}}
               for command in commands]
    return store.mutate_page_batch(workspace_id, page_id, stamped)


def _kinds(store, workspace_id):
    return [(event["event"], event["pageId"]) for event in store.read_events(workspace_id)]


def test_creating_a_page_logs_it_and_its_pinned_children(store):
    workspace = store.create_workspace("demo")
    result = store.create_page(workspace.id, "test-lifecycle", "Feature")
    [child] = result.children
    assert _kinds(store, workspace.id) == [("created", result.page.id), ("created", child.id)]
    created = store.read_events(workspace.id)[0]
    assert created["type"] == "test-lifecycle"
    assert created["title"] == "Feature"
    assert created["status"] == result.page.status


def test_a_transition_logs_one_status_event_and_a_content_edit_logs_none(store):
    workspace = store.create_workspace("demo")
    page = store.create_page(workspace.id, "test-flow", "Change").page
    _mutate(store, workspace.id, page.id, [{"command": "setSummary", "args": {"text": "Why."}}])
    assert len(store.read_events(workspace.id)) == 1
    _mutate(store, workspace.id, page.id, [{"command": "open"}])
    *_, status = store.read_events(workspace.id)
    assert (status["event"], status["from"], status["status"]) == ("status", "draft", "open")


def test_a_rejected_batch_logs_nothing(store):
    workspace = store.create_workspace("demo")
    page = store.create_page(workspace.id, "test-flow", "Change").page
    with pytest.raises(ConflictError):
        store.mutate_page_batch(workspace.id, page.id, [
            {"command": "open", "args": {"statusRevisionToken": "stale!"}}])
    assert _kinds(store, workspace.id) == [("created", page.id)]


def test_the_web_status_override_logs_a_status_event(store):
    workspace = store.create_workspace("demo")
    page = store.create_page(workspace.id, "test-flow", "Change").page
    store.set_page_status(workspace.id, page.id, "closed")
    *_, status = store.read_events(workspace.id)
    assert (status["event"], status["from"], status["status"]) == ("status", "draft", "closed")


def test_archive_and_unarchive_log_the_page_and_its_pinned_child(store):
    workspace = store.create_workspace("demo")
    result = store.create_page(workspace.id, "test-lifecycle", "Feature")
    [child] = result.children
    store.archive_page(workspace.id, result.page.id)
    store.unarchive_page(workspace.id, result.page.id)
    assert _kinds(store, workspace.id)[2:] == [
        ("archived", result.page.id), ("archived", child.id),
        ("unarchived", result.page.id), ("unarchived", child.id),
    ]


def test_scheduling_a_deletion_logs_the_archive_it_implies(store):
    workspace = store.create_workspace("demo")
    page = store.create_page(workspace.id, "test-flow", "Change").page
    store.schedule_page_deletion(workspace.id, page.id)
    store.unschedule_page_deletion(workspace.id, page.id)          # stays archived: nothing to log
    assert _kinds(store, workspace.id) == [("created", page.id), ("archived", page.id)]


def test_renaming_and_reparenting_log_nothing(store):
    workspace = store.create_workspace("demo")
    parent = store.create_page(workspace.id, "test-flow", "Parent").page
    page = store.create_page(workspace.id, "test-flow", "Change").page
    store.rename_page(workspace.id, page.id, "Renamed")
    store.reparent_page(workspace.id, page.id, parent.id)
    assert len(store.read_events(workspace.id)) == 2


def test_an_event_carries_the_instant_the_workspace_was_saved(store):
    workspace = store.create_workspace("demo")
    store.create_page(workspace.id, "test-flow", "Change")
    [event] = store.read_events(workspace.id)
    assert event["at"] == store.load_workspace(workspace.id).updated_at


def test_the_log_beside_a_workspace_is_not_listed_as_a_workspace(store, tmp_path):
    workspace = store.create_workspace("demo")
    store.create_page(workspace.id, "test-flow", "Change")
    assert store.events_path(workspace.id).parent == tmp_path
    assert store.events_path(workspace.id).name == f"{workspace.id.replace(':', '_')}.events.jsonl"
    assert [listed["id"] for listed in store.list_workspaces()] == [workspace.id]


def test_a_log_that_cannot_be_written_never_fails_the_write(store):
    workspace = store.create_workspace("demo")
    store.events_path(workspace.id).mkdir()                  # appending to a directory raises OSError
    page = store.create_page(workspace.id, "test-flow", "Change").page
    assert store.get_page(workspace.id, page.id).title == "Change"


def test_a_workspace_without_a_log_reads_no_events(store):
    workspace = store.create_workspace("demo")
    assert store.read_events(workspace.id) == []
