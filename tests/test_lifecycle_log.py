"""Unit tests for the pure lifecycle-log core (src.lifecycle_log).

Everything here is a function of its arguments, so pages and workspaces are built straight from
src.model, or through the pure command core on the hand-authored test-* fixtures, with no store.
"""

import json

from src import lifecycle_log
from src.commands import apply_command, create_page
from src.model import Page
from src.pagetypes._registry import get_page_type
from src.pagetypes.core.pagetype import initial_sections


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


# --- diff_page -----------------------------------------------------------------

FIELDS = get_page_type("test-fields")
BLOCKS = get_page_type("test-blocks")
CHILD = get_page_type("test-child")


def _counter():
    state = {"n": 0}

    def factory(prefix: str) -> str:
        state["n"] += 1
        return f"{prefix}:{state['n']}" if prefix else f"el{state['n']}"

    return factory


def _apply(page, page_type, factory, *commands):
    """Run commands through the pure command core, as a batch's working copy would."""
    for name, args in commands:
        page = apply_command(page, page_type, name, args, factory).page
    return page


def _kinds(events):
    return [event["kind"] for event in events]


def test_an_unchanged_page_diffs_to_nothing():
    page = create_page(FIELDS, "P", None, _counter())
    assert lifecycle_log.diff_page(page, page.copy(), FIELDS) == []


def test_a_title_change_is_renamed():
    factory = _counter()
    before = create_page(FIELDS, "Old", None, factory)
    after = _apply(before, FIELDS, factory, ("setTitle", {"title": "New"}))
    assert lifecycle_log.diff_page(before, after, FIELDS) == [
        {"page": before.id, "kind": "renamed", "from": "Old", "title": "New"}]


def test_links_added_and_removed_are_linked_then_unlinked():
    before = _page(links=[{"to": "x", "role": "old"}])
    after = _page(links=[{"to": "y", "role": "new"}])
    assert lifecycle_log.diff_page(before, after, None) == [
        {"page": before.id, "kind": "linked", "to": "y", "role": "new"},
        {"page": before.id, "kind": "unlinked", "to": "x", "role": "old"},
    ]


def test_each_changed_scalar_and_prose_field_is_one_edited():
    factory = _counter()
    before = create_page(FIELDS, "P", None, factory)
    after = _apply(before, FIELDS, factory, ("setLabel", {"label": "l"}),
                   ("setKind", {"kind": "beta"}), ("setBody", {"text": "body"}))
    assert lifecycle_log.diff_page(before, after, FIELDS) == [
        {"page": before.id, "kind": "edited", "section": "basics", "field": "label"},
        {"page": before.id, "kind": "edited", "section": "basics", "field": "kind"},
        {"page": before.id, "kind": "edited", "section": "basics", "field": "body"},
    ]


def test_a_changed_blocks_field_is_one_edited():
    factory = _counter()
    before = create_page(BLOCKS, "P", None, factory)
    after = _apply(before, BLOCKS, factory, ("addBody", {"blocks": [
        {"kind": "paragraph", "inlines": [{"text": "one"}]},
        {"kind": "paragraph", "inlines": [{"text": "two"}]}]}))
    assert lifecycle_log.diff_page(before, after, BLOCKS) == [
        {"page": before.id, "kind": "edited", "section": "body", "field": "body"}]


def test_a_list_without_an_element_fsm_adds_edits_and_removes_by_id():
    factory = _counter()
    base = _apply(create_page(FIELDS, "P", None, factory), FIELDS, factory,
                  ("addItem", {"text": "keep"}), ("addItem", {"text": "drop"}))
    keep, drop = (item["id"] for item in base.sections["items"]["items"])
    after = _apply(base, FIELDS, factory, ("editItem", {"itemId": keep, "text": "kept"}),
                   ("removeItem", {"itemId": drop}), ("addItem", {"text": "new"}))
    new = after.sections["items"]["items"][-1]["id"]
    assert lifecycle_log.diff_page(base, after, FIELDS) == [
        {"page": base.id, "kind": "el_edited", "section": "items", "field": "items", "el": keep},
        {"page": base.id, "kind": "el_added", "section": "items", "field": "items", "el": new,
         "status": None},
        {"page": base.id, "kind": "el_removed", "section": "items", "field": "items", "el": drop},
    ]


def test_a_list_with_an_element_fsm_reports_the_added_status_and_status_moves():
    factory = _counter()
    base = _apply(create_page(CHILD, "C", None, factory), CHILD, factory,
                  ("addStep", {"text": "one"}))
    step = base.sections["steps"]["items"][0]["id"]
    after = _apply(base, CHILD, factory, ("markStepDone", {"stepId": step}),
                   ("addCheck", {"text": "c"}))
    check = after.sections["checks"]["items"][0]["id"]
    events = lifecycle_log.diff_page(base, after, CHILD)
    assert events == [
        {"page": base.id, "kind": "el_status", "section": "steps", "field": "items", "el": step,
         "from": "todo", "to": "done"},
        {"page": base.id, "kind": "el_added", "section": "checks", "field": "items", "el": check,
         "status": "pending"},
    ]
    assert list(events[0]) == ["page", "kind", "section", "field", "el", "from", "to"]
    assert list(events[1]) == ["page", "kind", "section", "field", "el", "status"]


def test_an_element_whose_status_and_text_both_change_is_one_el_status():
    factory = _counter()
    base = _apply(create_page(CHILD, "C", None, factory), CHILD, factory, ("addStep", {"text": "a"}))
    after = base.copy()
    after.sections["steps"]["items"][0].update({"status": "done", "text": "b"})
    assert _kinds(lifecycle_log.diff_page(base, after, CHILD)) == ["el_status"]


def test_the_order_is_renamed_links_edited_elements_then_status_last():
    before = Page(id="test-child:1", type="test-child", title="Old", status="draft",
                  sections=initial_sections(CHILD))
    after = before.copy()
    after.title = "New"
    after.status = "ready"
    after.links = [{"to": "x", "role": "r"}]
    after.sections["steps"]["items"] = [{"id": "s1", "text": "s", "status": "todo"}]
    after.sections["decisions"]["body"] = [{"id": "b1", "kind": "paragraph", "text": "t"}]
    events = lifecycle_log.diff_page(before, after, CHILD)
    assert _kinds(events) == ["renamed", "linked", "edited", "el_added", "status"]
    assert events[-1] == {"page": "test-child:1", "kind": "status", "from": "draft", "to": "ready"}


def test_a_section_the_stored_page_lacks_is_not_an_edit():
    # A page stored before its type gained a section, or with a stale fixed field, is backfilled by
    # apply_command; that bookkeeping is not something the batch changed.
    factory = _counter()
    stored = create_page(FIELDS, "P", None, factory)
    del stored.sections["items"]
    stored.sections["notice"]["body"] = "an older fixed text"
    after = _apply(stored, FIELDS, factory, ("setLabel", {"label": "l"}))
    assert lifecycle_log.diff_page(stored, after, FIELDS) == [
        {"page": stored.id, "kind": "edited", "section": "basics", "field": "label"}]


def test_without_a_page_type_only_title_links_and_status_are_diffed():
    before = _page(title="A", status="draft")
    after = _page(title="B", status="open", links=[{"to": "x", "role": "r"}])
    after.sections = {"basics": {"label": "changed"}}
    assert _kinds(lifecycle_log.diff_page(before, after, None)) == ["renamed", "linked", "status"]


def test_elements_without_a_string_id_are_skipped_and_a_non_list_value_is_empty():
    before = Page(id="test-fields:1", type="test-fields", title="P", status="active",
                  sections=initial_sections(FIELDS))
    before.sections["items"]["items"] = None
    after = before.copy()
    after.sections["items"]["items"] = [{"text": "no id"}, {"id": "e1", "text": "x"}]
    assert lifecycle_log.diff_page(before, after, FIELDS) == [
        {"page": "test-fields:1", "kind": "el_added", "section": "items", "field": "items",
         "el": "e1", "status": None}]
