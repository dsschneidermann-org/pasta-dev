"""Unit tests for registry integrity - the specs must be internally consistent.

The generic, parametrized structural invariants run over BOTH the production REGISTRY and the
hand-authored test registry (TEST_REGISTRY) - every page type, production or fixture, must be
well-formed. `test_expected_types_registered` stays pinned to the production SET so a genuinely
new or removed production type still fails loudly. The content-specific assertions further down
pin to the test fixtures (src.testtypes), so enriching a production type never breaks them.
"""

import pytest

from src.commands import is_field_setter
from src.errors import ValidationError
from src.pagetypes import (
    ADD_BLOCK,
    ADD_ELEMENT,
    ADD_LINK,
    COMPOUND,
    ELEMENT_TRANSITION,
    INLINE_RUNS,
    INLINE_RUN_GRID,
    INLINE_RUN_LISTS,
    REORDER_BLOCK,
    REORDER_ELEMENT,
    REMOVE_BLOCK,
    REMOVE_ELEMENT,
    SET_BLOCK,
    SET_ELEMENT_FIELD,
    SET_PROSE,
    SET_SCALAR,
    SET_TITLE,
    TABLE_ALIGN,
    TRANSITION,
    BLOCKS,
    LIST,
    REGISTRY,
    collect_ref_ids,
    get_page_type,
    initial_sections,
    status_transitions,
    validate_inline_content,
    validate_table,
    FSMSpec,
)
from src.testtypes import TEST_REGISTRY

# Structural invariants must hold for EVERY page type - production and hand-authored fixture alike.
ALL_TYPES = {**REGISTRY, **TEST_REGISTRY}

# Commands that target a real section.field
CONTENT_TARGETING = {
    SET_SCALAR, SET_PROSE, ADD_ELEMENT, SET_ELEMENT_FIELD, ELEMENT_TRANSITION,
    REORDER_ELEMENT, REORDER_BLOCK, REMOVE_ELEMENT, ADD_BLOCK, SET_BLOCK, REMOVE_BLOCK,
}
# Commands that edit a `blocks` field (must target a BLOCKS field). reorder_block belongs here;
# reorder_element (its list-field twin) does not - it targets a LIST field.
BLOCK_TARGETING = {ADD_BLOCK, SET_BLOCK, REMOVE_BLOCK, REORDER_BLOCK}
# List-element commands whose element_map fields must be declared on the (LIST) field
ELEMENT_MAPPING = {ADD_ELEMENT, SET_ELEMENT_FIELD, ELEMENT_TRANSITION}


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_fsm_is_well_formed(tag: str):
    page_type = ALL_TYPES[tag]
    fsm = page_type.fsm
    assert fsm.initial in fsm.states
    # The status transition table is DERIVED from the type's transition/compound commands.
    for _event, source, dest, agency in status_transitions(page_type):
        assert source in fsm.states, f"{tag}: transition source {source} not a state"
        assert dest in fsm.states, f"{tag}: transition dest {dest} not a state"
        assert agency in {"agent", "human", "either"}


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_transition_commands_declare_source_and_dest(tag: str):
    """The single-home rule: every transition/compound command declares its source state(s) via
    legal_in and a real destination via dest, and no command maps one event to two different dests."""
    page_type = ALL_TYPES[tag]
    states = set(page_type.fsm.states)
    event_dests: dict[str, str] = {}
    for command in page_type.commands:
        if command.kind in (TRANSITION, COMPOUND) and command.event is not None:
            assert command.legal_in, f"{tag}.{command.name} has no legal_in source state(s)"
            assert command.dest in states, f"{tag}.{command.name} dest {command.dest} not a state"
            for source in command.legal_in:
                assert source in states, f"{tag}.{command.name} source {source} not a state"
            prior = event_dests.setdefault(command.event, command.dest)
            assert prior == command.dest, \
                f"{tag}: event {command.event} maps to two dests ({prior}, {command.dest})"


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_content_commands_target_real_fields(tag: str):
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        if command.kind in CONTENT_TARGETING:
            field_spec = page_type.field_spec(command.section, command.field)
            assert field_spec is not None, f"{tag}.{command.name} targets missing {command.section}.{command.field}"
            if command.kind in ELEMENT_MAPPING:
                # every mapped element field must be declared on the list field
                assert field_spec.kind == LIST
                for element_field, _arg in command.element_map:
                    assert element_field in field_spec.element_fields


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_transition_commands_reference_real_events(tag: str):
    page_type = ALL_TYPES[tag]
    events = {event for event, *_ in page_type.fsm.transitions}
    for command in page_type.commands:
        if command.kind in (TRANSITION, COMPOUND) and command.event is not None:
            assert command.event in events, f"{tag}.{command.name} fires unknown event {command.event}"


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_initial_sections_cover_every_field(tag: str):
    page_type = ALL_TYPES[tag]
    sections = initial_sections(page_type)
    for section in page_type.sections:
        assert section.key in sections
        for field_spec in section.fields:
            assert field_spec.key in sections[section.key]


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_requires_reference_real_fields(tag: str):
    """Every required-content precondition must point at a field the page type actually has."""
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        for section_key, field_key in command.requires:
            assert page_type.field_spec(section_key, field_key) is not None, (
                f"{tag}.{command.name} requires missing field {section_key}.{field_key}"
            )


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_element_transitions_reference_real_element_events(tag: str):
    """An element-transition command must fire an event on a field that has an element FSM."""
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        if command.kind == ELEMENT_TRANSITION:
            field_spec = page_type.field_spec(command.section, command.field)
            assert field_spec is not None and field_spec.element_fsm is not None, (
                f"{tag}.{command.name} drives an element FSM on a field that has none"
            )
            events = {event for event, *_ in field_spec.element_fsm.transitions}
            assert command.event in events, f"{tag}.{command.name} fires unknown element event {command.event}"


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_block_commands_target_blocks_fields(tag: str):
    """add/set/move/remove-block commands must target a `blocks` field."""
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        if command.kind in BLOCK_TARGETING:
            field_spec = page_type.field_spec(command.section, command.field)
            assert field_spec is not None and field_spec.kind == BLOCKS, (
                f"{tag}.{command.name} targets {command.section}.{command.field}, which is not a blocks field"
            )


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_every_ordered_field_has_a_reorder_command(tag: str):
    """The 'extend to all fields' contract: every list field exposes a reorder_element command and
    every blocks field a reorder_block command - targeting that exact field."""
    page_type = ALL_TYPES[tag]
    reorder_kind_by_target = {
        (command.section, command.field): command.kind
        for command in page_type.commands if command.kind in (REORDER_ELEMENT, REORDER_BLOCK)
    }
    for section in page_type.sections:
        for field_spec in section.fields:
            target = (section.key, field_spec.key)
            if field_spec.kind == LIST:
                assert reorder_kind_by_target.get(target) == REORDER_ELEMENT, \
                    f"{tag}.{section.key}.{field_spec.key} (list) has no reorder_element command"
            elif field_spec.kind == BLOCKS:
                assert reorder_kind_by_target.get(target) == REORDER_BLOCK, \
                    f"{tag}.{section.key}.{field_spec.key} (blocks) has no reorder_block command"


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_every_add_command_supports_positioned_insert(tag: str):
    """Every top-level add_element / add_block command accepts the optional index + precedingId
    (internal compound sub-steps like the flow's _addCommit are append-only and not surfaced here)."""
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        if command.kind in (ADD_ELEMENT, ADD_BLOCK):
            arg_names = {arg.name for arg in command.args}
            assert {"index", "precedingId"} <= arg_names, \
                f"{tag}.{command.name} lacks positioned-insert args (index, precedingId)"


def test_list_cmds_threads_ref_check_onto_the_add_only():
    """Only the add carries the check: the remove and reorder name an element already on this
    page. `singular=` keeps the derived noun off the plural rule's 'dispatche'."""
    from src.pagetypes import ArgSpec, RefCheck, list_cmds
    ref = RefCheck(arg="workstreamId", scope="parent", section="workstreams", field="items")
    add, remove, reorder = list_cmds("dispatches", singular="dispatch",
                                     add_args=(ArgSpec("workstreamId"),), ref_check=ref)
    assert (add.name, remove.name, reorder.name) == ("addDispatch", "removeDispatch", "reorderDispatch")
    assert add.ref_check is ref
    assert remove.ref_check is None and reorder.ref_check is None


@pytest.mark.parametrize("tag", list(ALL_TYPES))
def test_field_setter_description_is_short_and_not_the_instruction(tag: str):
    """A field setter carries a short line saying what it sets, never its field's authoring
    instruction - that text lives once on the FieldSpec and reaches an agent through the `sections`
    listing and the `instruction` key of a `next` field edge."""
    page_type = ALL_TYPES[tag]
    for command in page_type.commands:
        if is_field_setter(command):
            field_spec = page_type.field_spec(command.section, command.field)
            assert field_spec is not None, f"{tag}.{command.name} targets a missing field"
            assert command.description, f"{tag}.{command.name} has no description"
            assert "\n" not in command.description, f"{tag}.{command.name} description is multi-line"
            assert command.description != field_spec.description, (
                f"{tag}.{command.name} still carries the {command.section}.{command.field} instruction"
            )


def _drift_type(setter_description: str, field_description: str):
    """A one-setter page type whose setter and field descriptions are both caller-controlled, so a
    test can pick which branch of the field-setter validation fires."""
    from src.pagetypes import CommandSpec, FSMSpec, PageType, SectionSpec, _prose, _text
    return PageType(
        tag="xtest-drift", name="Drift", description="ad-hoc",
        sections=(SectionSpec("summary", "Summary",
                              (_prose("body", description=field_description),)),),
        commands=(CommandSpec("setSummary", SET_PROSE, setter_description,
                              section="summary", field="body", args=(_text(),)),),
        fsm=FSMSpec(name="XDrift", initial="active", states=("active",)),
    )


def test_field_setter_with_an_empty_description_is_rejected():
    # The factories used to pass "" and rely on the mirror; nothing may ship description-less now.
    with pytest.raises(ValueError):
        _ = _drift_type("", "line one\nline two")


def test_field_setter_with_a_multiline_description_is_rejected():
    # An authoring instruction is a wrapped multi-line block; a setter takes one short line.
    with pytest.raises(ValueError):
        _ = _drift_type("line one\nline two", "line one\nline two")


def test_field_setter_repeating_a_single_line_field_instruction_is_rejected():
    # The equality branch, which is the only thing that catches a one-line instruction.
    with pytest.raises(ValueError):
        _ = _drift_type("the whole instruction", "the whole instruction")


def test_field_setter_targeting_an_unknown_field_is_still_rejected():
    # The pre-existing check must survive the guard rewrite it sat beside.
    from src.pagetypes import CommandSpec, FSMSpec, PageType, SectionSpec, _prose, _text
    with pytest.raises(ValueError):
        _ = PageType(
            tag="xtest-ghost", name="Ghost", description="ad-hoc",
            sections=(SectionSpec("summary", "Summary", (_prose("body", description="x"),)),),
            commands=(CommandSpec("setGhost", SET_PROSE, "set the ghost",
                                  section="summary", field="missing", args=(_text(),)),),
            fsm=FSMSpec(name="XGhost", initial="active", states=("active",)),
        )


# ============================================================================
# content-specific assertions - pinned to the hand-authored fixtures (src.testtypes),
# so enriching a production type never breaks them.
# ============================================================================
BLK = get_page_type("test-blocks")     # the full blocks / inline-run surface
CHILD = get_page_type("test-child")    # element-FSM lists + a blocks decisions field
LIFE = get_page_type("test-lifecycle")


def test_blocks_fixture_has_full_block_surface():
    names = {command.name for command in BLK.commands}
    assert {"addParagraph", "addHeading", "addCode", "addList", "addQuote", "addTable",
            "setParagraph", "setHeading", "setCode", "setList", "setQuote", "setTable",
            "addDivider", "reorderBlock", "removeBlock", "addLink", "setTitle"} == names


def test_add_link_on_every_authorable_type_but_not_toc():
    # add_link_cmd() is added to every authorable production page type; the command-less toc is the
    # sole exception - it has no authoring surface at all, so it must NOT carry addLink.
    for tag, page_type in REGISTRY.items():
        command = page_type.command("addLink")
        if tag == "toc":
            assert command is None, "toc cannot be authored - it must not carry addLink"
        else:
            assert command is not None and command.kind == ADD_LINK, f"{tag} is missing addLink"
    # a single `active` state, no transitions
    assert BLK.fsm.initial == "active" and BLK.fsm.transitions == ()


def test_set_title_on_every_authorable_type_but_not_toc():
    # set_title_cmd() - the universal rename alias - is added to every authorable production page type
    # alongside addLink; the command-less toc is the sole exception with no authoring surface.
    for tag, page_type in REGISTRY.items():
        command = page_type.command("setTitle")
        if tag == "toc":
            assert command is None, "toc cannot be authored - it must not carry setTitle"
        else:
            assert command is not None and command.kind == SET_TITLE, f"{tag} is missing setTitle"


def test_reorder_split_into_two_kinds_with_anchored_args():
    # The list-field and blocks-field reorders are two parallel kinds; both carry (id, toIndex, precedingId).
    child_names = {command.name for command in CHILD.commands}
    assert "reorderStep" in child_names and "moveStep" not in child_names and "reorderSteps" not in child_names
    assert CHILD.command("reorderStep").kind == REORDER_ELEMENT
    assert [arg.name for arg in CHILD.command("reorderStep").args] == ["stepId", "toIndex", "precedingId"]
    assert BLK.command("reorderBlock").kind == REORDER_BLOCK
    assert [arg.name for arg in BLK.command("reorderBlock").args] == ["blockId", "toIndex", "precedingId"]


def test_blocks_body_is_an_inline_run_blocks_field():
    assert BLK.field_spec("body", "body").kind == BLOCKS
    add_paragraph = BLK.command("addParagraph")
    assert add_paragraph.kind == ADD_BLOCK and add_paragraph.block_kind == "paragraph"
    assert add_paragraph.args[0].content == INLINE_RUNS   # paragraphs carry inline runs


def test_element_fsms_declare_checkmark_done():
    """The checkbox mapping lives on the element FSM (ElementFSMSpec): checkmark_done names the [x]
    state, `initial` is the [ ] state, and an element FSM without checkmark_done renders no box. A
    page-status FSMSpec has no checkmark_done at all - page states are never checkboxes."""
    step_fsm = CHILD.field_spec("steps", "items").element_fsm
    check_fsm = CHILD.field_spec("checks", "items").element_fsm
    question_fsm = LIFE.field_spec("questions", "items").element_fsm
    assert step_fsm.checkmark_done == "done"         # initial "todo" -> [ ], "done" -> [x]
    assert check_fsm.checkmark_done == "passed"      # "pending" -> [ ], "passed" -> [x], "failed" -> no box
    assert question_fsm.checkmark_done is None       # open/answered render without a box
    assert not hasattr(LIFE.fsm, "checkmark_done")   # a page-status FSM is not a checkbox FSM


def test_auto_children_are_specs_and_pinned_detection():
    from src.pagetypes import AutoChildSpec, is_auto_child_type
    # auto_children are AutoChildSpec instances naming the pinned child types (the test-child fixture)
    assert all(isinstance(spec, AutoChildSpec) for spec in LIFE.auto_children)
    assert {spec.type for spec in LIFE.auto_children} == {"test-child"}
    # is_auto_child_type: true for a declared auto-child; false otherwise, for a childless type, or None
    assert is_auto_child_type(LIFE, "test-child") is True
    assert is_auto_child_type(LIFE, "test-fields") is False
    assert is_auto_child_type(CHILD, "test-child") is False
    assert is_auto_child_type(None, "test-child") is False


# --- inline-run grammar validation (pure, not tied to any page type) ---------
def test_validate_inline_runs_accepts_the_run_grammar():
    validate_inline_content(INLINE_RUNS, [
        "plain",
        {"text": "bold", "bold": True},
        {"text": "linked", "href": "https://x"},
        {"code": "x = 1"},
        {"ref": "architecture:abc"},
    ])


def test_validate_inline_runs_rejects_markdown_in_a_text_run():
    with pytest.raises(ValidationError):
        validate_inline_content(INLINE_RUNS, ["**bold**"])            # bare string
    with pytest.raises(ValidationError):
        validate_inline_content(INLINE_RUNS, [{"text": "a `code` b"}])  # inside a text run


def test_validate_inline_runs_rejects_malformed_runs():
    with pytest.raises(ValidationError):
        validate_inline_content(INLINE_RUNS, [{"ref": "x", "text": "y"}])   # ref must stand alone
    with pytest.raises(ValidationError):
        validate_inline_content(INLINE_RUNS, [{"text": "x", "bogus": 1}])   # unknown key
    with pytest.raises(ValidationError):
        validate_inline_content(INLINE_RUNS, [123])                         # not a run


def test_validate_run_lists_and_grid_and_align():
    validate_inline_content(INLINE_RUN_LISTS, [["a"], [{"text": "b", "italic": True}]])
    validate_inline_content(INLINE_RUN_GRID, [[["r0c0"], ["r0c1"]]])
    validate_inline_content(TABLE_ALIGN, ["left", "center", "right", None])
    with pytest.raises(ValidationError):
        validate_inline_content(TABLE_ALIGN, ["middle"])


def test_validate_table_width_consistency():
    validate_table(["h0", "h1"], [["a", "b"], ["c", "d"]], ["left", None])
    with pytest.raises(ValidationError):
        validate_table(["h0", "h1"], [["a"]], None)                 # row too narrow
    with pytest.raises(ValidationError):
        validate_table(["h0", "h1"], [["a", "b"]], ["left"])        # align width mismatch


def test_collect_ref_ids_across_shapes():
    # INLINE_RUNS: refs are gathered; non-ref runs (str/text/code) are ignored.
    assert collect_ref_ids(INLINE_RUNS, ["x", {"ref": "a:1"}, {"text": "t"}, {"code": "c"}]) == ["a:1"]
    # INLINE_RUN_LISTS: list items / quote paragraphs / table header cells.
    assert collect_ref_ids(INLINE_RUN_LISTS, [["x", {"ref": "a:1"}], [{"ref": "a:2"}]]) == ["a:1", "a:2"]
    # INLINE_RUN_GRID: table rows of cells.
    assert collect_ref_ids(INLINE_RUN_GRID, [[[{"ref": "a:1"}], ["x"]], [[{"ref": "a:2"}]]]) == ["a:1", "a:2"]
    # TABLE_ALIGN carries no runs; and a non-string ref is ignored (left for grammar validation).
    assert collect_ref_ids(TABLE_ALIGN, ["left", "center"]) == []
    assert collect_ref_ids(INLINE_RUNS, [{"ref": 123}]) == []


# --- FSMSpec.state_guidance --------------------------------------------------
def test_state_guidance_normalizes_authored_text():
    # Authored as an indented block; it must arrive as written, wrap breaks kept.
    spec = FSMSpec(name="G", initial="a", states=("a", "b"),
                   state_guidance=(("b", "\n    line one\n    line two\n  "),))
    assert spec.guidance_for("b") == "line one\nline two"


def test_guidance_for_returns_none_for_undeclared_state():
    # None rather than "", so the caller can tell undeclared from empty.
    spec = FSMSpec(name="G", initial="a", states=("a", "b"),
                   state_guidance=(("b", "some guidance"),))
    assert spec.guidance_for("a") is None


def test_state_guidance_rejects_unknown_state():
    # A typo in a state name fails at import rather than silently never appearing.
    with pytest.raises(ValueError, match="unknown state"):
        FSMSpec(name="G", initial="a", states=("a",), state_guidance=(("nope", "x"),))


def test_state_guidance_rejects_duplicate_state():
    with pytest.raises(ValueError, match="twice"):
        FSMSpec(name="G", initial="a", states=("a",),
                state_guidance=(("a", "x"), ("a", "y")))
