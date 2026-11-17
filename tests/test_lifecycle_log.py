"""Unit tests for the pure lifecycle-log core (src.lifecycle_log).

Everything here is a function of its arguments, so pages and workspaces are built straight from
src.model, or through the pure command core on the hand-authored test-* fixtures, with no store.
"""

import json

from src import lifecycle_log
from src.commands import apply_command, create_page
from src.model import Page, Workspace
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


# --- baseline and sweep_events -------------------------------------------------

def _ws(*pages: Page, roots: list[str]) -> Workspace:
    return Workspace(id="ws:t", name="t", root_page_ids=roots, pages={p.id: p for p in pages})


def _p(page_id, children=(), parent=None, archived=False, links=()) -> Page:
    return Page(id=page_id, type="test-fields", title=page_id.upper(), status="active",
                parent_id=parent, child_ids=list(children), archived=archived, links=list(links))


def _pages(events):
    return [event["page"] for event in events]


def test_baseline_walks_the_tree_in_pre_order_including_archived_pages():
    ws = _ws(_p("a", ["a1", "a2"]), _p("a1", ["a11"], parent="a"), _p("a11", parent="a1"),
             _p("a2", parent="a", archived=True), _p("b"), roots=["a", "b"])
    events = lifecycle_log.baseline(ws)
    assert _pages(events) == ["a", "a1", "a11", "a2", "b"]
    assert all(event["kind"] == "present" for event in events)
    assert events[3]["archived"] is True and events[3]["parent"] == "a"


def test_baseline_lists_each_page_once_despite_a_cycle_and_skips_a_dangling_id():
    ws = _ws(_p("a", ["b", "gone"]), _p("b", ["a"], parent="a"), roots=["a"])
    assert _pages(lifecycle_log.baseline(ws)) == ["a", "b"]


def test_baseline_puts_unreached_pages_last_in_id_order_with_their_parents_first():
    # "y" is filed nowhere and its child "c" sorts before it: the parent is pulled ahead.
    ws = _ws(_p("root"), _p("c", parent="y"), _p("y", ["c"]), _p("x"), roots=["root"])
    assert _pages(lifecycle_log.baseline(ws)) == ["root", "y", "c", "x"]


def test_baseline_of_an_empty_workspace_is_empty():
    assert lifecycle_log.baseline(_ws(roots=[])) == []


def test_sweep_events_unlink_survivors_then_delete_in_the_given_order():
    survivor = _p("live", links=[{"to": "gone", "role": "relates-to"}, {"to": "live2", "role": "x"}])
    gone = _p("gone", ["kid"], archived=True, links=[{"to": "kid", "role": "inner"}])
    kid = _p("kid", parent="gone")
    kid.status = "done-ish"
    ws = _ws(_p("root", ["live", "gone", "live2"]), survivor, gone, kid, _p("live2"),
             roots=["root"])
    assert lifecycle_log.sweep_events(ws, ["gone", "kid", "missing"]) == [
        {"page": "live", "kind": "unlinked", "to": "gone", "role": "relates-to"},
        {"page": "gone", "kind": "deleted", "type": "test-fields", "title": "GONE",
         "status": "active"},
        {"page": "kid", "kind": "deleted", "type": "test-fields", "title": "KID",
         "status": "done-ish"},
    ]


# --- check_backfill --------------------------------------------------------------

BACKFILL_LINES = [
    {"seq": 1, "ts": 1000, "page": "toc:f", "kind": "created", "type": "toc", "title": "Features",
     "parent": None, "status": "active"},
    {"seq": 2, "ts": 2000, "page": "feature-brief:x", "kind": "created", "type": "feature-brief",
     "title": "Add a thing", "parent": "toc:f", "status": "draft"},
    {"seq": 3, "ts": 2000, "page": "feature-brief:x", "kind": "status", "from": "draft",
     "to": "shipped"},
]


def _text(lines):
    return "".join(lifecycle_log.encode(line) for line in lines)


def _with(index, **changes):
    lines = [dict(line) for line in BACKFILL_LINES]
    lines[index].update(changes)
    return lines


def test_check_backfill_accepts_a_valid_file_and_its_lines_re_encode_byte_for_byte():
    text = _text(BACKFILL_LINES)
    checked = lifecycle_log.check_backfill(text)
    assert checked == BACKFILL_LINES
    assert _text(checked) == text


def test_check_backfill_accepts_unknown_extra_keys():
    assert lifecycle_log.check_backfill(_text(_with(2, note="later key"))) is not None


def test_check_backfill_rejects_a_seq_hole_or_a_first_seq_other_than_one():
    assert lifecycle_log.check_backfill(_text(_with(2, seq=4))) is None
    assert lifecycle_log.check_backfill(_text(BACKFILL_LINES[1:])) is None


def test_check_backfill_rejects_a_decreasing_ts():
    assert lifecycle_log.check_backfill(_text(_with(2, ts=1500))) is None


def test_check_backfill_rejects_lines_that_are_not_events():
    good = _text(BACKFILL_LINES)
    assert lifecycle_log.check_backfill(good + "not json\n") is None
    assert lifecycle_log.check_backfill(good + "\n") is None                      # blank line
    assert lifecycle_log.check_backfill(good + "[4]\n") is None                   # not an object
    assert lifecycle_log.check_backfill(_text(_with(2, kind="exploded"))) is None
    assert lifecycle_log.check_backfill(_text(_with(1, title=7))) is None
    assert lifecycle_log.check_backfill(_text(_with(0, seq=True))) is None
    assert lifecycle_log.check_backfill(_text(_with(0, ts="1000"))) is None
    missing_parent = [dict(line) for line in BACKFILL_LINES]
    del missing_parent[1]["parent"]
    assert lifecycle_log.check_backfill(_text(missing_parent)) is None


def test_check_backfill_rejects_a_missing_final_newline_and_empty_text():
    assert lifecycle_log.check_backfill(_text(BACKFILL_LINES)[:-1]) is None
    assert lifecycle_log.check_backfill("") is None


# --- serve_lines -----------------------------------------------------------------

def _line(seq, ts=None, **extra):
    return lifecycle_log.encode({"seq": seq, "ts": ts if ts is not None else seq * 10,
                                 "page": "p", "kind": "archived", **extra})


def test_serve_lines_of_nothing_is_nothing():
    assert lifecycle_log.serve_lines("") == []


def test_serve_lines_parses_in_disk_order():
    served = lifecycle_log.serve_lines(_line(1) + _line(2))
    assert [event["seq"] for event in served] == [1, 2]
    assert served[0] == {"seq": 1, "ts": 10, "page": "p", "kind": "archived"}


def test_serve_lines_skips_bad_lines_and_drops_an_unterminated_tail():
    text = _line(1) + "garbage\n" + '"a string"\n' + '{"seq": "2"}\n' + _line(2) + '{"seq":3,"ts'
    assert [event["seq"] for event in lifecycle_log.serve_lines(text)] == [1, 2]


def test_serve_lines_marks_a_hole_with_a_gap_event():
    served = lifecycle_log.serve_lines(_line(1) + _line(2) + _line(5, ts=77))
    assert served[2] == {"seq": 3, "ts": 77, "page": None, "kind": "gap", "missing": 2}
    assert [event["kind"] for event in served] == ["archived", "archived", "gap", "archived"]


def test_serve_lines_marks_a_leading_hole():
    served = lifecycle_log.serve_lines(_line(4, ts=40))
    assert served[0] == {"seq": 1, "ts": 40, "page": None, "kind": "gap", "missing": 3}
    assert served[1]["seq"] == 4


def test_serve_lines_puts_no_gap_before_a_seq_that_does_not_advance():
    served = lifecycle_log.serve_lines(_line(1) + _line(2) + _line(2) + _line(3))
    assert [event["kind"] for event in served] == ["archived"] * 4
