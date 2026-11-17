"""Unit tests for the pure lifecycle-log core (src.lifecycle_log).

Everything here is a function of its arguments, so pages and workspaces are built straight from
src.model, or through the pure command core on the hand-authored test-* fixtures, with no store.
"""

import json

from src import lifecycle_log
from src.model import Page


def _page(page_id="test-fields:a", **overrides) -> Page:
    fields = {"id": page_id, "type": "test-fields", "title": "A", "status": "active"}
    fields.update(overrides)
    return Page(**fields)


# --- constructors, stamp, encode ---------------------------------------------

def test_created_carries_type_title_parent_and_status_in_order():
    event = lifecycle_log.created(_page(parent_id="test-fields:p"))
    assert list(event) == ["page", "kind", "type", "title", "parent", "status"]
    assert event == {"page": "test-fields:a", "kind": "created", "type": "test-fields",
                     "title": "A", "parent": "test-fields:p", "status": "active"}


def test_present_adds_the_archived_flag_and_links():
    page = _page(archived=True, links=[{"to": "test-fields:b", "role": "relates-to"}])
    event = lifecycle_log.present(page)
    assert list(event) == ["page", "kind", "type", "title", "parent", "status", "archived", "links"]
    assert event["kind"] == "present" and event["parent"] is None
    assert event["archived"] is True
    assert event["links"] == [{"to": "test-fields:b", "role": "relates-to"}]


def test_present_copies_only_to_and_role_of_each_link():
    page = _page(links=[{"to": "test-fields:b", "role": "x", "extra": 1}])
    assert lifecycle_log.present(page)["links"] == [{"to": "test-fields:b", "role": "x"}]


def test_each_small_constructor_has_exactly_the_contract_keys():
    assert lifecycle_log.status("p", "draft", "open") == {
        "page": "p", "kind": "status", "from": "draft", "to": "open"}
    assert lifecycle_log.renamed("p", "Old", "New") == {
        "page": "p", "kind": "renamed", "from": "Old", "title": "New"}
    assert lifecycle_log.moved("p", None, "q") == {
        "page": "p", "kind": "moved", "from_parent": None, "to_parent": "q"}
    assert lifecycle_log.linked("p", "q", "depends-on") == {
        "page": "p", "kind": "linked", "to": "q", "role": "depends-on"}
    assert lifecycle_log.unlinked("p", "q", "depends-on") == {
        "page": "p", "kind": "unlinked", "to": "q", "role": "depends-on"}
    assert lifecycle_log.archived("p") == {"page": "p", "kind": "archived"}
    assert lifecycle_log.unarchived("p") == {"page": "p", "kind": "unarchived"}
    assert list(lifecycle_log.status("p", "a", "b")) == ["page", "kind", "from", "to"]
    assert list(lifecycle_log.renamed("p", "a", "b")) == ["page", "kind", "from", "title"]
    assert list(lifecycle_log.moved("p", "a", "b")) == ["page", "kind", "from_parent", "to_parent"]


def test_deleted_carries_the_last_type_title_and_status():
    event = lifecycle_log.deleted(_page(title="Gone", status="active"))
    assert event == {"page": "test-fields:a", "kind": "deleted", "type": "test-fields",
                     "title": "Gone", "status": "active"}


def test_stamp_puts_seq_and_ts_first_and_numbers_from_first_seq():
    events = [lifecycle_log.status("p", "a", "b"), lifecycle_log.archived("q")]
    stamped = lifecycle_log.stamp(events, 41, 1_794_931_023_123)
    assert stamped == [
        {"seq": 41, "ts": 1_794_931_023_123, "page": "p", "kind": "status", "from": "a", "to": "b"},
        {"seq": 42, "ts": 1_794_931_023_123, "page": "q", "kind": "archived"},
    ]
    assert list(stamped[0]) == ["seq", "ts", "page", "kind", "from", "to"]
    assert events[0] == {"page": "p", "kind": "status", "from": "a", "to": "b"}   # inputs untouched


def test_stamp_of_nothing_is_nothing():
    assert lifecycle_log.stamp([], 1, 0) == []


def test_encode_is_compact_keeps_non_ascii_and_ends_with_one_newline():
    line = lifecycle_log.encode({"seq": 1, "ts": 2, "page": "p", "kind": "renamed",
                                 "from": "Før", "title": "Næste"})
    assert line == '{"seq":1,"ts":2,"page":"p","kind":"renamed","from":"Før","title":"Næste"}\n'
    assert json.loads(line) == {"seq": 1, "ts": 2, "page": "p", "kind": "renamed",
                                "from": "Før", "title": "Næste"}
