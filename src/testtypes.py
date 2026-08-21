"""Hand-authored, minimal test-only page types - capability fixtures, NOT clones.

Each type here is a purpose-built demonstration of ONE capability cluster of the page-type
system, deliberately small and named for the mechanic it exercises rather than any production
role:

  - ``test-fields``    - every non-block field kind (scalar, enum-scalar, prose, list with a
                         required + optional element field) and the content-mutation patterns over
                         them (set, add + positioned insert, remove, reorder, set-element-field).
  - ``test-blocks``    - the ``blocks`` field: every block kind, the inline-run grammar, in-place
                         set, reorder, remove; a single terminal ``active`` state.
  - ``test-flow``      - a simple status FSM (draft → open → closed → open) with a state and event
                         that share the name ``open``, and a COMPOUND ``close`` that records a
                         commit AND transitions.
  - ``test-lifecycle`` - a rich status FSM: required-content preconditions, agency, a multi-source
                         ``abandon`` to a terminal state, a questions element-FSM + escalate, a
                         pinned auto-child, a ``beginImplementation`` guarded on that child's page
                         status (page-status guard), and a ``ship`` guarded on that child's element
                         states (element-status guards).
  - ``test-child``     - the pinned auto-child of ``test-lifecycle``: two element FSMs (todo/done
                         steps and pending/passed/failed checks, covering every checkbox render
                         case), a ``legal_in`` content lock where structural edits are draft-only
                         but element-status marks stay legal in ``ready``, a ``decisions``
                         blocks field whose ``addDecision`` carries a cross-page ref check to the
                         parent's questions, and a ``markReady`` gated on BOTH required content
                         (steps) and a PARENT-state guard - the pair behind parent-gated stage
                         exposure, where a child stays silent in ``next_actions`` until its parent
                         reaches the stage that unlocks it.

Tests assert against these fixtures so a production page type can be enriched freely without
churning the suite; production types are trusted to reuse these same patterns and are verified only
through the generic invariants, the registered set, the description directive, and doc generation.

These types are RESOLVABLE by ``get_page_type`` (so the store, renderer, and pure core operate on a
test page like any other) but HIDDEN from discovery - the ``describePageType`` listing and doc-gen
enumeration - unless the test-only ``expose_test_types()`` flag is set (see src.pagetypes). They
are deliberately NOT bound in src.statecharts, so they are not documentable.

Command DECLARATION flows through the SAME shared command-helper factories the production types use
(``set_prose_cmd`` / ``set_scalar_cmd`` / ``list_cmds`` / ``element_cmds`` / ``set_element_field_cmd`` /
``add_block_cmd`` / ``block_cmds`` / ``transition_cmd`` / ``transition_on_add_cmd``, imported from
src.pagetypes) - so a fixture reads like a production type and doubles as coverage of those
helpers, while its command surface (names, args, legality, FSM edges, guards, ref-checks) stays
exactly what it was when hand-written. Only the element FSMs and the field-spec helpers remain local,
so a fixture's SHAPE never moves when a production type does.
"""

from __future__ import annotations

from src.pagetypes import (
    BLOCKS,
    LIST,
    PROSE,
    SCALAR,
    AutoChildSpec,
    ChildStateGuard,
    ElementFSMSpec,
    FieldSpec,
    FSMSpec,
    PageType,
    ParentStateGuard,
    RefCheck,
    SectionSpec,
    _boolean,
    _text,
    add_block_cmd,
    all_block_cmds,
    block_cmds,
    element_cmds,
    list_cmds,
    set_element_field_cmd,
    set_prose_cmd,
    set_scalar_cmd,
    transition_cmd,
    transition_on_add_cmd,
    add_link_cmd,
    set_title_cmd,
)


# --- Element-level FSMs (a list element's own tiny lifecycle) -----------------
# Named distinctly from production so their diagram labels and cache identity never collide.
_STEP_FSM = ElementFSMSpec(
    name="TestStep",
    initial="todo", states=("todo", "done"),
    transitions=(("markDone", "todo", "done", "agent"), ("reopen", "done", "todo", "agent")),
    checkmark_done="done",                       # todo -> [ ], done -> [x]
)
_CHECK_FSM = ElementFSMSpec(
    name="TestCheck",
    initial="pending", states=("pending", "passed", "failed"),
    transitions=(("pass", "pending", "passed", "agent"), ("fail", "pending", "failed", "agent")),
    checkmark_done="passed",                     # pending -> [ ], passed -> [x], failed -> no box
)
_QUESTION_FSM = ElementFSMSpec(
    name="TestQuestion",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)                                                # no checkmark_done -> open/answered render without a box


# --- Field-spec helpers (readability only, mirroring src.pagetypes) -------
# The FIELD helpers stay local so a fixture's SHAPE never moves when a production type does; only the
# COMMAND declaration below is routed through the shared src.pagetypes factories.
def _scalar(key: str, choices: tuple[str, ...] | None = None, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=SCALAR, choices=choices, description=description)


def _prose(key: str, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=PROSE, description=description)


def _list(key: str, element_fields: tuple[str, ...], element_fsm: ElementFSMSpec | None = None,
          description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=LIST, element_fields=element_fields,
                     element_fsm=element_fsm, description=description)


def _blocks(key: str, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=BLOCKS, description=description)


# ============================================================================
# test-fields - every non-block field kind + the content-mutation patterns.
# scalar (plain), scalar (enum), prose, and a plain list (multi element fields, one optional,
# no element FSM). Commands cover set_scalar, set_prose, add_element (append + positioned insert),
# remove_element, reorder_element, and set_element_field (a boolean const). Single `active` state:
# this fixture has no lifecycle of its own - it is purely a content surface.
# ============================================================================
TEST_FIELDS = PageType(
    tag="test-fields",
    name="Fields fixture",
    description="Test fixture: every non-block field kind and the content-mutation patterns over them.",
    sections=(
        SectionSpec("basics", "Basics", (
            _scalar("label", description="a plain scalar"),
            _scalar("kind", choices=("alpha", "beta", "gamma"), description="an enum scalar"),
            _prose("body", "a prose body"),
        )),
        SectionSpec("items", "Items", (
            _list("items", element_fields=("text", "note", "flagged"),
                  description="a plain list: a required field, an optional field, and a set-able flag"),
        )),
    ),
    commands=(
        set_scalar_cmd("basics", "label"),
        set_scalar_cmd("basics", "kind", choices=("alpha", "beta", "gamma")),
        set_prose_cmd("basics", name="setBody", label="body"),
        *list_cmds("items", add_args=(_text("text"), _text("note", required=False))),
        set_element_field_cmd("items", name="flagItem", const=("flagged", True), description="set an item's flag"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(name="TestFields", initial="active", states=("active",)),
)


# ============================================================================
# test-blocks - the `blocks` field: the full inline-run grammar and every block kind.
# The richest content surface: add of every block kind, in-place `set…`, reorder, remove, and
# positioned insert. Single terminal `active` state (also the single-state / terminal case for
# render and reachable_states). `code` deliberately has no in-place set, so it is composed as an
# add-only kind (add_block_cmd(...)[:1]).
# ============================================================================
TEST_BLOCKS = PageType(
    tag="test-blocks",
    name="Blocks fixture",
    description="Test fixture: the blocks field - every block kind and the inline-run grammar.",
    sections=(
        SectionSpec("body", "Body", (_blocks("body", "a rich-text blocks body"),)),
    ),
    # The full rich blocks surface - add + in-place set per kind, plus remove/reorder - in one call.
    commands=(*all_block_cmds("body"), add_link_cmd(), set_title_cmd()),
    fsm=FSMSpec(name="TestBlocks", initial="active", states=("active",)),
)


# ============================================================================
# test-flow - the simple status FSM: draft -> open -> closed, closed -> open.
# The `open` STATE and the `open` EVENT deliberately share a name (the FSM engine must handle
# this). `close` is a COMPOUND that records a commit AND fires the transition, atomically.
# `closed` is declared TERMINAL yet keeps its `reopen` edge - the fixture for the terminal-state
# authoring lock's "transitions still allowed if any" branch (authoring locked, reopen still legal)
# and for the `legal_in` override of it - `reorderCommit` names `closed` and stays legal there.
# ============================================================================
TEST_FLOW = PageType(
    tag="test-flow",
    name="Flow fixture",
    description="Test fixture: a simple 3-state status FSM with a state/event name collision and a compound transition.",
    sections=(
        SectionSpec("summary", "Summary", (_prose("body", "what changed"),)),
        SectionSpec("resolution", "Resolution", (
            _list("commits", element_fields=("sha", "message", "url"), description="commits recorded via close"),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        transition_cmd("open", "draft -> open"),
        transition_on_add_cmd("close", "open -> closed", section="resolution", field="commits",
                              description="record a commit AND close",
                              add_args=(_text("sha"), _text("message"), _text("url", required=False))),
        # commits is populated only by `close`; a reorder is offered so every ordered field has one.
        # Its legal_in names the terminal `closed`, so it also fixtures the terminal-lock override.
        *list_cmds("resolution", field="commits", add=False, remove=False,
                   legal_in=("draft", "open", "closed")),
        transition_cmd("reopen", "closed -> open"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="TestFlow",
        initial="draft",
        states=("draft", "open", "closed"),
        terminal_states=("closed",),
        # Only `open` is guided, leaving draft and closed to fixture the unguided paths.
        state_guidance=(("open", """
            open - the work is under way.
            Record a commit with close when it is finished.
            """),),
    ),
)


# ============================================================================
# test-lifecycle - the rich status FSM: required-content preconditions on transitions, agency
# variety (agent / human / either), a multi-source `abandon` OR-combined to a terminal state,
# terminal states, a questions element-FSM + escalate (feeds `attention`), a pinned auto-child,
# a `beginImplementation` guarded on that child's page status (a page-status ChildStateGuard),
# and a `ship` guarded on that child's element states (two element-status ChildStateGuards).
# ============================================================================
TEST_LIFECYCLE = PageType(
    tag="test-lifecycle",
    name="Lifecycle fixture",
    description="Test fixture: a rich status FSM with required-content gates, agency, guards, questions, and a pinned auto-child.",
    sections=(
        SectionSpec("summary", "Summary", (_prose("body", "the intent (gates beginPlanning)"),)),
        SectionSpec("parts", "Parts", (
            _list("items", element_fields=("name",), description="parts touched (gates beginImplementation)"),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="open questions (element-FSM open -> answered)"),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        *list_cmds("parts", add_args=(_text("name"),)),
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        transition_cmd("beginPlanning", "draft -> planning", requires=(("summary", "body"),)),
        # beginImplementation carries BOTH a required-content precondition (parts) AND a page-status
        # guard: the pinned test-child must be `ready` before building (exercises the page-status
        # form of ChildStateGuard, evaluated in the store).
        transition_cmd("beginImplementation", "planning -> building", requires=(("parts", "items"),),
                       guards=(ChildStateGuard("test-child", "ready", "the test-child must be marked ready"),)),
        transition_cmd("submitForReview", "building -> review (human gate)", agency="human"),
        transition_cmd("reopenPlanning", "building -> planning", agency="either"),
        transition_cmd("requestChanges", "review -> building", agency="either"),
        # `ship` is a human gate AND is guarded: every child step must be `done` and every child
        # check `passed` (element-status guards checked across the page's child pages by the store).
        transition_cmd("ship", "review -> done (human gate)", agency="human", guards=(
            ChildStateGuard("test-child", "done", "every test-child step must be done",
                            section="steps", field="items"),
            ChildStateGuard("test-child", "passed", "every test-child check must be passed",
                            section="checks", field="items"),
        )),
        transition_cmd("abandon", "drop the work -> abandoned", agency="either",
                       legal_in=("draft", "planning", "building", "review")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="TestLifecycle",
        initial="draft",
        states=("draft", "planning", "building", "review", "done", "abandoned"),
        terminal_states=("done", "abandoned"),
        state_guidance=(("review", """
            review - the build is done.
            Check the child steps and checks before the ship gate.
            """),),
    ),
    # On createPage, mint the pinned child in the same commit; author into it.
    auto_children=(AutoChildSpec("test-child"),),
)


# A pinned child may only be finalized once its test-lifecycle parent has reached `planning` or
# later - not while the parent is still `draft` (its base is not established), nor once `abandoned`.
# The ParentStateGuard fixture: attached to markReady below and evaluated in the store, it is what
# makes the child's stage-required content (steps) not yet the child's work - so `next_actions`
# withholds addStep from `do` until the parent unlocks the stage.
_PARENT_IN_PLANNING_OR_LATER = ParentStateGuard(
    parent_type="test-lifecycle",
    required_statuses=("planning", "building", "review", "done"),
    message="the test-lifecycle parent must be in planning or later",
)


# ============================================================================
# test-child - the pinned auto-child of test-lifecycle. Two element FSMs (todo/done steps and
# pending/passed/failed checks - covering every checkbox render case), a `legal_in` content lock
# where structural edits (add/remove/reorder, addDecision) are `draft`-only while element-status
# marks stay legal in `ready`, two cross-page ref checks to the PARENT's questions - one on the
# `decisions` blocks field (addDecision), one on the `notes` list field (addNote), covering both the
# block and the list add path - and a `markReady` carrying BOTH a required-content precondition
# (steps) and a PARENT-state guard, the pair that fixtures parent-gated stage exposure. `decision`
# has no in-place set, so it is composed as an add-only block kind (add_block_cmd(...)[:1]).
# ============================================================================
TEST_CHILD = PageType(
    tag="test-child",
    name="Child fixture",
    description="Test fixture: element FSMs + checkbox rendering, a legal_in content lock, and a cross-page ref check.",
    sections=(
        SectionSpec("steps", "Steps", (
            _list("items", element_fields=("text", "status"), element_fsm=_STEP_FSM,
                  description="build steps (element-FSM todo <-> done)"),
        )),
        SectionSpec("checks", "Checks", (
            _list("items", element_fields=("text", "status"), element_fsm=_CHECK_FSM,
                  description="verification checks (element-FSM pending -> passed/failed)"),
        )),
        SectionSpec("notes", "Notes", (
            _list("items", element_fields=("questionId", "text"),
                  description="notes, each linked to a parent question (a ref-checked list add)"),
        )),
        SectionSpec("decisions", "Decisions", (
            _blocks("body", "decisions, each linked to a parent question"),
        )),
    ),
    commands=(
        *list_cmds("steps", label="step", add_args=(_text(),), legal_in=("draft",)),
        # Element-status marks stay legal in `ready` (progress recorded on a finalized plan); only
        # the structural add/remove/reorder commands are `draft`-only.
        *element_cmds("steps", legal_in=("draft", "ready"), marks=(
            ("markStepDone", "markDone", "mark a step done"),
            ("markStepTodo", "reopen", "reopen a step"))),
        *list_cmds("checks", label="check", add_args=(_text(),), legal_in=("draft",)),
        *element_cmds("checks", legal_in=("draft", "ready"), marks=(
            ("markCheckPassed", "pass", "mark a check passed"),
            ("markCheckFailed", "fail", "mark a check failed"))),
        # The list twin of addDecision below: the same ref check, on an add_element.
        *list_cmds("notes", label="note", add_args=(_text("questionId"), _text()),
                   ref_check=RefCheck(arg="questionId", scope="parent", section="questions", field="items"),
                   legal_in=("draft",)),
        *block_cmds(
            "decisions",
            *add_block_cmd("decisions", "decision", args=(_text("questionId"), _text()),
                           ref_check=RefCheck(arg="questionId", scope="parent", section="questions", field="items"),
                           legal_in=("draft",))[:1],
            remove_name="removeDecision", remove_desc="remove a decision",
            reorder_name="reorderDecision",
            reorder_desc="move a decision to an anchored position (precedingId guards a stale read)",
            legal_in=("draft",)),
        transition_cmd("markReady", "draft -> ready", requires=(("steps", "items"),),
                       parent_guards=(_PARENT_IN_PLANNING_OR_LATER,)),
        transition_cmd("reopen", "ready -> draft (unlocks structural edits)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="TestChild",
        initial="draft",
        states=("draft", "ready"),
        # A guided initial state, which is what makes createPage's echo testable.
        state_guidance=(("draft", "draft - write the steps and checks here."),),
    ),
)


TEST_REGISTRY: dict[str, PageType] = {
    page_type.tag: page_type
    for page_type in (TEST_FIELDS, TEST_BLOCKS, TEST_FLOW, TEST_LIFECYCLE, TEST_CHILD)
}
