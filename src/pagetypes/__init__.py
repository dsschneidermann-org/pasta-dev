"""Page-type registry: page types expressed as data, not code.

A `PageType` fixes a page's sections, field kinds, legal commands, and status FSM.
`createPage` initializes from it, `commands.py` enforces it, and `describePageType`
reports it.

Each page type is declared in its own module beside this one, so it can be read and
changed on its own. This module holds what they share and the registry they go into.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from ..errors import ProductionTypeInTestError, ValidationError

# --- Command kinds -----------------------------------------------------------
SET_SCALAR = "set_scalar"
SET_PROSE = "set_prose"
ADD_ELEMENT = "add_element"                  # append to a `list` field, or positioned insert (index + precedingId)
SET_ELEMENT_FIELD = "set_element_field"
REMOVE_ELEMENT = "remove_element"
ELEMENT_TRANSITION = "element_transition"   # fire a list element's own FSM (todo->done, ...)
ADD_BLOCK = "add_block"                      # append to a `blocks` field, or positioned insert (index + precedingId)
SET_BLOCK = "set_block"                      # replace a block in place by id (id + kind preserved)
REMOVE_BLOCK = "remove_block"
REORDER_ELEMENT = "reorder_element"          # move ONE element to an anchored position in a `list` field
REORDER_BLOCK = "reorder_block"              # move ONE block to an anchored position in a `blocks` field
TRANSITION = "transition"
COMPOUND = "compound"
ADD_LINK = "add_link"                        # append a typed edge to Page.links (the universal authoring link)
SET_TITLE = "set_title"                      # set Page.title (the universal rename alias for renamePage)

# --- Field kinds -------------------------------------------------------------
SCALAR = "scalar"
PROSE = "prose"
LIST = "list"
BLOCKS = "blocks"                            # ordered typed blocks (paragraph/heading/code/list/table/quote/...)

# --- Inline-run content shapes (for `blocks` fields) -------------------------
# The rich text inside a block is an ordered array of **inline runs**. An `ArgSpec` may
# declare which inline shape its (array) value must satisfy so the command layer can
# structurally validate it before anything is written. A "run" is one of:
#   - a plain string                                    - literal text;
#   - {"text": str, "bold"?: bool, "italic"?: bool, "href"?: str} - marked/linked text;
#   - {"code": str}                                     - an inline code span;
#   - {"ref": "<pageId>"}                               - a page reference (label render-derived).
# Markdown syntax inside a text run is rejected - emphasis is expressed with a structured run.
INLINE_RUNS = "inline_runs"            # value: [run, ...]                       (a paragraph/heading body)
INLINE_RUN_LISTS = "inline_run_lists"  # value: [[run, ...], ...]                (list items / quote paragraphs / table header cells)
INLINE_RUN_GRID = "inline_run_grid"    # value: [[[run, ...], ...], ...]         (table rows of cells)
TABLE_ALIGN = "table_align"            # value: ["left"|"center"|"right"|None, ...]

_ALIGN_VALUES = ("left", "center", "right", None)
# Markdown emphasis/code/link tokens rejected inside a plain-text run. Kept deliberately narrow
# (bold/code/link markers) so ordinary prose containing a lone `*` or `_` is not falsely rejected.
_MARKDOWN_TOKENS = ("**", "__", "`", "](")


# --- Spec dataclasses --------------------------------------------------------
@dataclass(frozen=True)
class FSMSpec:
    """A page's status FSM: its state set and initial state ONLY.

    The transition table is NOT stored here - it is DERIVED from the page type's transition/compound
    commands by `status_transitions(page_type)`, where each such command declares its source state(s)
    via `legal_in=` and its destination via `dest=`. So a status edge lives in exactly one place (the
    command), and `legal_in` is the uniform "where is this command legal" declaration across every
    command kind. (Element lifecycles are a separate concept - see `ElementFSMSpec`.)

    `terminal_states` names states in which the work is finished. While a page sits in one, `legal_commands`
    locks every authoring command (describeMutations reports them unavailable; mutatePageBatch rejects
    them) - but any remaining status transitions stay legal, so a terminal state can still offer, e.g., a
    `reopen` edge. This is an explicit declaration, NOT inferred from a state merely lacking outgoing
    transitions: only states listed here are authoring-locked. An authoring command can opt out by naming
    the terminal state in `legal_in`.

    `state_guidance` is the stage instruction for a status - what the state you just entered is
    for - echoed by the write path and used to open that state's generated doc page. It is a
    tuple of `(state, text)` pairs, not a mapping, because this spec is the `@lru_cache` key in
    `fsm._machine_class`. Leaving a state undeclared is the normal case.
    """
    name: str
    initial: str
    states: tuple[str, ...]
    transitions: tuple[tuple[str, str, str, str], ...] = ()
    terminal_states: tuple[str, ...] = ()
    state_guidance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        # A bad state name is rejected at import, not silently ignored.
        seen: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for state, text in self.state_guidance:
            if state not in self.states:
                raise ValueError(f"{self.name}: state_guidance names unknown state '{state}'.")
            if state in seen:
                raise ValueError(f"{self.name}: state_guidance names '{state}' twice.")
            seen.add(state)
            normalized.append((state, dedent(text.strip("\n")).rstrip()))
        object.__setattr__(self, "state_guidance", tuple(normalized))

    def guidance_for(self, state: str) -> str | None:
        """The stage instruction for `state`, or None when the type declares none for it."""
        for name, text in self.state_guidance:
            if name == state:
                return text
        return None


@dataclass(frozen=True)
class ElementFSMSpec:
    """A list element's own tiny lifecycle (a step's todo/done, a case's pending/passed/failed, ...).

    Unlike a page's status FSM, an element FSM keeps its own transition table: an `element_transition`
    command only names the `event` it fires (its `legal_in` is the PAGE status lock, not the element
    source state), so there is nothing to derive from and no duplication to remove - this table is the
    single source of truth.

    For an element rendered as a task checkbox, `checkmark_done` names the state shown as a checked box
    `[x]`; the FSM's `initial` state is then the unchecked box `[ ]`, and every other state - and every
    element FSM that leaves this None - renders with no box.
    """
    name: str
    initial: str
    states: tuple[str, ...]
    # (event, source, dest, agency)
    transitions: tuple[tuple[str, str, str, str], ...]
    checkmark_done: str | None = None


@dataclass(frozen=True)
class FieldSpec:
    key: str
    kind: str                                   # SCALAR | PROSE | LIST | BLOCKS
    choices: tuple[str, ...] | None = None      # allowed values for a scalar enum
    element_fields: tuple[str, ...] | None = None  # for LIST: each element's field names
    element_fsm: ElementFSMSpec | None = None   # for LIST: a per-element lifecycle (todo/done, ...)
    description: str = ""

    def __post_init__(self):
        # An instruction is authored as an indented triple-quoted block wrapped at the source
        # margin; strip that shared indentation so consumers get the text as authored. The wrap
        # breaks are kept - markdown reflows a paragraph's newlines away.
        object.__setattr__(self, "description", dedent(self.description.strip("\n")).rstrip())


@dataclass(frozen=True)
class RefCheck:
    """A cross-page integrity precondition: `arg` must name an existing element id.

    Evaluated in the store (which can see other pages). `scope="parent"` means the id must
    be an element in `section.field` of this page's parent. A dangling id aborts the commit.
    """
    arg: str
    scope: str                                  # "parent"
    section: str
    field: str


@dataclass(frozen=True)
class ChildStateGuard:
    """A cross-page transition guard over the state of a page's children, evaluated in the store.

    For every child page of type `child_type`, in one of two forms:
    - element form (`section`/`field` given): every element in that list field must have status
      `required_status`;
    - page form (`section`/`field` omitted): the child page's own status must equal `required_status`.
    Otherwise the transition is rejected with `message`.
    """
    child_type: str
    required_status: str
    message: str
    section: str | None = None                  # element form; omit for the page-status form
    field: str | None = None


@dataclass(frozen=True)
class ParentStateGuard:
    """A cross-page transition guard over the state of a page's PARENT, evaluated in the store.

    The parent page's own status must be one of `required_statuses`, otherwise the transition is
    rejected with `message`. The mirror image of `ChildStateGuard` (which looks down at children):
    this looks up at the parent - e.g. to gate a pinned child's finalize transition on its parent
    having reached a given stage. Only enforced when the page actually has a parent of `parent_type`;
    a page with no parent, or a parent of another type, is unconstrained.
    """
    parent_type: str
    required_statuses: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class SectionSpec:
    key: str
    name: str
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type: str = "string"                        # JSON Schema type
    required: bool = True
    choices: tuple[str, ...] | None = None
    description: str = ""
    # for an `array` arg carrying inline runs: which inline-run shape it must satisfy
    # (INLINE_RUNS / INLINE_RUN_LISTS / INLINE_RUN_GRID / TABLE_ALIGN). None = no shape check.
    content: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    name: str
    kind: str
    description: str = ""
    section: str | None = None
    field: str | None = None
    args: tuple[ArgSpec, ...] = ()
    event: str | None = None                    # FSM event for TRANSITION / COMPOUND
    # for TRANSITION / COMPOUND: the destination state. Paired with `legal_in` (the source state(s)),
    # this is the single home for a status edge - `status_transitions(page_type)` derives the whole
    # page FSM table from these.
    dest: str | None = None
    # for ADD_ELEMENT / SET_ELEMENT_FIELD / ELEMENT_TRANSITION: (elementField, argName) pairs
    # mapping args onto the element. The id-taking kinds treat args[0] as the target element id.
    element_map: tuple[tuple[str, str], ...] = ()
    # for SET_ELEMENT_FIELD / ELEMENT_TRANSITION: literal (elementField, value) pairs to stamp
    # onto the target element (the flag-setting shape).
    element_const: tuple[tuple[str, Any], ...] = ()
    # for ADD_BLOCK: the block's kind (paragraph | heading | code | decision)
    block_kind: str | None = None
    # for COMPOUND: ordered sub-commands applied atomically. (ELEMENT_TRANSITION fires the
    # element-FSM event named in `event` on the target element.)
    steps: tuple["CommandSpec", ...] = ()
    # for TRANSITION / COMPOUND: (section, field) pairs that must be populated before the
    # transition is legal - a required-content precondition on top of the FSM topology.
    requires: tuple[tuple[str, str], ...] = ()
    # Where this command is legal (None = any status). The uniform "where-legal" declaration:
    #   - content command: the statuses it may run in (a status-scoped lock);
    #   - TRANSITION / COMPOUND: the SOURCE state(s) of the edge (paired with `dest`), from which the
    #     page FSM table is derived. Not surfaced in the command summary for transitions (the source
    #     is already reported via the derived FSM transition list), so describe output is unchanged.
    legal_in: tuple[str, ...] | None = None
    # cross-page integrity check / transition guard (evaluated in the store)
    ref_check: RefCheck | None = None
    guards: tuple[ChildStateGuard, ...] = ()
    # cross-page guard over the PARENT's state (evaluated in the store) - see ParentStateGuard
    parent_guards: tuple[ParentStateGuard, ...] = ()
    agency: str = "agent"                       # "agent" | "human" | "either" (informational this pass)
    generated: bool = False


@dataclass(frozen=True)
class AutoChildSpec:
    """A page auto-created as a pinned, protected child when a page of the declaring type is made.

    `type` is the child page-type tag. Being an auto-child is what makes a page 'pinned' - it cannot
    be reparented, reordered, or archived/unarchived on its own (the store enforces this). The fact
    lives here, on the parent type, and is never stored as a field on the child Page.
    """
    type: str


@dataclass(frozen=True)
class PageType:
    tag: str
    name: str
    description: str
    sections: tuple[SectionSpec, ...]
    commands: tuple[CommandSpec, ...]
    fsm: FSMSpec
    # auto-created pinned children minted in the same commit as this page (see AutoChildSpec)
    auto_children: tuple[AutoChildSpec, ...] = ()

    def __post_init__(self):
        object.__setattr__(self.fsm, "transitions", status_transitions(self))
        self._validate_field_setter_descriptions()

    def _validate_field_setter_descriptions(self) -> None:
        """A field setter (SET_SCALAR / SET_PROSE / ADD_ELEMENT) carries a short description of what it
        does ('set the summary', 'add a constraint'), never its field's authoring instruction: that
        lives once on the FieldSpec.description, and reaches an agent through describePageType's
        `sections` listing and the `instruction` key of a `next` field edge. Freeform blocks
        (ADD_BLOCK / SET_BLOCK) already carry a short description and are untouched.
        """
        for command in self.commands:
            if command.kind not in (SET_SCALAR, SET_PROSE, ADD_ELEMENT):
                continue
            section, field = command.section, command.field
            field_spec = (self.field_spec(section, field)
                          if section is not None and field is not None else None)
            if field_spec is None:
                raise ValueError(
                    f"{self.tag}: field setter '{command.name}' targets unknown field " +
                    f"'{command.section}.{command.field}'."
                )
            if not command.description:
                raise ValueError(
                    f"{self.tag}: field setter '{command.name}' has no description; it must carry a " +
                    f"short line saying what it sets."
                )
            if "\n" in command.description or command.description == field_spec.description:
                raise ValueError(
                    f"{self.tag}: field setter '{command.name}' carries the authoring instruction as " +
                    f"its description; that text belongs once on the " +
                    f"'{command.section}.{command.field}' FieldSpec, and the setter takes a short " +
                    f"one-line description instead."
                )

    def command(self, name: str) -> CommandSpec | None:
        for command in self.commands:
            if command.name == name:
                return command
        return None

    def field_spec(self, section_key: str, field_key: str) -> FieldSpec | None:
        for section in self.sections:
            if section.key == section_key:
                for field_spec in section.fields:
                    if field_spec.key == field_key:
                        return field_spec
        return None


def status_transitions(page_type: PageType) -> tuple[tuple[str, str, str, str], ...]:
    """The page's status-FSM transition table, DERIVED from its transition/compound commands.

    Each top-level command with a page-status event (kind TRANSITION or COMPOUND, `event` set) owns one
    edge: `legal_in` is its source state(s) and `dest` its destination. A command legal in several
    states expands to one `(event, source, dest, agency)` per source.
    Nested COMPOUND sub-steps are NOT walked - the outer command carries the edge - so the inner
    transition step does not double-count. Iteration follows command-declaration order.
    """
    edges: list[tuple[str, str, str, str]] = []
    for command in page_type.commands:
        if command.kind in (TRANSITION, COMPOUND) and command.event is not None and command.dest is not None:
            for source in (command.legal_in or ()):
                edges.append((command.event, source, command.dest, command.agency))
    return tuple(edges)


# --- Element-level FSMs (a list element's own tiny lifecycle) -----------------
_STEP_FSM = ElementFSMSpec(
    name="Step",
    initial="todo", states=("todo", "done"),
    transitions=(("markDone", "todo", "done", "agent"), ("reopen", "done", "todo", "agent")),
    checkmark_done="done",                       # a step is a checkbox: initial "todo" -> [ ], "done" -> [x]
)
_CASE_FSM = ElementFSMSpec(
    name="Case",
    initial="pending", states=("pending", "passed", "failed"),
    transitions=(("pass", "pending", "passed", "agent"), ("fail", "pending", "failed", "agent")),
    checkmark_done="passed",                     # initial "pending" -> [ ], "passed" -> [x], "failed" -> no box
)
_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)                                                # no checkmark_done -> open/answered render without a box
# One run of one agent against one workstream. `accepted` is the SINGLE success terminal, which is
# what lets an epic's `submitForReview` be a ChildStateGuard (that guard compares every element
# against exactly one required status). A fix round is a `redispatch` of the same element, not a new
# one, so the element itself records how many attempts a workstream took.
_DISPATCH_FSM = ElementFSMSpec(
    name="Dispatch",
    initial="pending", states=("pending", "dispatched", "reported", "accepted", "blocked"),
    transitions=(("dispatch", "pending", "dispatched", "agent"),
                 ("report", "dispatched", "reported", "agent"),
                 ("accept", "reported", "accepted", "agent"),
                 ("redispatch", "reported", "dispatched", "agent"),   # a fix round
                 ("redispatch", "blocked", "dispatched", "agent"),    # unblocked, try again
                 ("block", "dispatched", "blocked", "agent"),
                 ("block", "reported", "blocked", "agent")),
    checkmark_done="accepted",                   # pending -> [ ], accepted -> [x], the rest no box
)


# --- Declaration helpers (readability only) ----------------------------------
def _scalar(key: str, *, choices: tuple[str, ...] | None = None, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=SCALAR, choices=choices, description=description)


def _prose(key: str, *, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=PROSE, description=description)


def _list(key: str, element_fields: tuple[str, ...], element_fsm: ElementFSMSpec | None = None,
          *, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=LIST, element_fields=element_fields,
                     element_fsm=element_fsm, description=description)


def _blocks(key: str, *, description: str = "") -> FieldSpec:
    return FieldSpec(key=key, kind=BLOCKS, description=description)


# --- Arg helpers -------------------------------------------------------------
# Tiny ArgSpec factories so a command's arg list reads as `(_text("file"), _integer("level"), ...)`
# instead of spelling out `ArgSpec(..., type=...)` each time. `_text()` is the common single-value
# `text` arg. `_same_named` derives an element_map from an arg list (each arg -> a same-named field),
# which is why no helper call site passes element_map: the arg names ARE the field names.
def _text(name: str = "text", *, required: bool = True,
          choices: tuple[str, ...] | None = None, description: str = "") -> ArgSpec:
    return ArgSpec(name, required=required, choices=choices, description=description)


def add_link_cmd() -> CommandSpec:
    """The universal reference-link authoring command: add an outgoing typed edge (this --role--> toId)
    to Page.links. Added to every authorable page type's command surface, so linking is discoverable as
    a page command and not only through the separate top-level `link` tool. Always legal - no legal_in /
    requires - so it runs in any status. The store's _check_link precheck enforces the cross-page rules
    shared with link_page, before the pure core appends."""
    return CommandSpec(
        name="addLink",
        kind=ADD_LINK,
        description="add a typed reference link from this page to another (this --role--> toId)",
        args=(_text("toId", description="the target page id to link to"),
              _text("role", description="the edge role, e.g. depends-on / relates-to")),
    )


def set_title_cmd() -> CommandSpec:
    """The universal page-rename authoring command: set this page's title - an alias for the top-level
    renamePage tool, exposed as a page command (like add_link_cmd's addLink) so a title can be fixed in
    the same authoring surface (describeMutations / mutatePageBatch) as the content it describes. Added to
    every authorable page type EXCEPT the command-less toc. Always legal - no legal_in / requires - so it
    runs in any status (locked only in a terminal state, as all authoring is). The pure core sets
    Page.title after rejecting a blank title, exactly as renamePage does."""
    return CommandSpec(
        name="setTitle",
        kind=SET_TITLE,
        description="set this page's title (an alias for the renamePage operation)",
        args=(_text("title", description="the new page title (must be non-empty)"),),
    )


def _integer(name: str, *, required: bool = True, description: str = "") -> ArgSpec:
    return ArgSpec(name, type="integer", required=required, description=description)


def _boolean(name: str, *, required: bool = True, description: str = "") -> ArgSpec:
    return ArgSpec(name, type="boolean", required=required, description=description)


def _array(name: str, *, content: str | None = None, required: bool = True, description: str = "") -> ArgSpec:
    return ArgSpec(name, type="array", required=required, content=content, description=description)


def _same_named(args: tuple[ArgSpec, ...]) -> tuple[tuple[str, str], ...]:
    """The element_map for `args`: each arg mapped onto a same-named element/block field."""
    return tuple((arg.name, arg.name) for arg in args)


# Positioning args shared by add-block / add-element commands (both optional: omit `index` to append).
# `index` is the destination slot; `precedingId` is the stale-read guard - the id the caller expects
# immediately before that slot (null/omit for the front). The reorder_element / reorder_block kinds
# use a required `toIndex` plus this same `precedingId`. The guard itself lives in commands._resolve_slot.
_INDEX = _integer("index", required=False,
                  description="insert position (append if omitted); when given, requires precedingId")
_PRECEDING = _text("precedingId", required=False,
                   description="stale-read guard: the id expected just before the slot (null/omit for the front)")


# --- Field-op command helpers (the CommandSpec analog of _scalar/_prose/_list/_blocks) --------
# Each is a PURE factory returning a CommandSpec (or a tuple of them) to spread into a PageType's
# `commands=(...)`, in the same family/style as the FieldSpec helpers above. The first positional
# argument is the section; every other argument is named. Command names and the remove/reorder
# `<noun>Id` arg are DERIVED from the section/field so the minimal call carries no name plumbing
# (list_cmds("constraints", ...) -> addConstraint/removeConstraint/reorderConstraint). A `name=`
# override preserves a name the derivation would not produce. A flow-populated list asks list_cmds for
# a subset (e.g. reorder only, add=False/remove=False); an add-only list drops remove/reorder the same
# way.

# Enum choice tuples shared by a field's `choices` and its set/add command's arg `choices`, so the
# allowed set lives in exactly one place instead of being written twice (field + command).
_NODE_KINDS = ("module", "component", "subsystem", "service", "layer", "package")
_CODE_REF_KINDS = ("file", "function", "class", "type", "interface", "constant")
_DEP_ROLES = ("depends-on", "exposes", "implements", "owns", "calls")
_VERDICTS = ("build-ready", "needs-changes", "needs-human-decision")
_SEVERITIES = ("blocking", "should-fix", "nit")
_FINDING_ACTIONS = ("addStep", "addCase", "addConstraint", "askQuestion", "edit")
# Tiers rather than model ids: an id rots between releases, and a stale enum rejects valid input.
_MODEL_TIERS = ("cheap", "standard", "capable")
_EPIC_FINDING_ACTIONS = ("addWorkstream", "addAgent", "addDispatch", "addContract",
                         "addConstraint", "askQuestion", "edit")


def _cap(word: str) -> str:
    """'summary' -> 'Summary' (leaving the rest of the word as-is, so 'dataModel' -> 'DataModel')."""
    return word[:1].upper() + word[1:]


def _a(word: str) -> str:
    """The indefinite article for `word`, so a generated description reads 'an invariant' / 'a step'."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def _singular(word: str) -> str:
    """A small, rule-based singularizer for deriving a command noun from a (plural) field/section key
    ('codeReferences'->'codeReference', 'dependencies'->'dependency', 'documentation' unchanged). A
    plural the rule mishandles is fixed by passing `singular=` to the helper."""
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s"):
        return word[:-1]
    return word


def _setter_label(section: str, field: str, label: str | None) -> str:
    """The noun a field setter's short description reads with: the explicit `label`, else the word its
    command name is derived from - the section for the conventional 'body' field, the field key
    otherwise. A camelCase key, or a section displayed under another name, passes `label=`."""
    return label or (section if field == "body" else field)


def set_prose_cmd(section: str, *, field: str = "body", name: str | None = None,
                  label: str | None = None,
                  legal_in: tuple[str, ...] | None = None) -> CommandSpec:
    """A SET_PROSE command for a prose field; name defaults to set<Section> (setSummary, setOverview)
    and the description to 'set the <section>'. The field's instruction is not copied here."""
    return CommandSpec(name or f"set{_cap(section)}", SET_PROSE,
                       f"set the {_setter_label(section, field, label)}",
                       section=section, field=field, args=(_text(),), legal_in=legal_in)


def set_scalar_cmd(section: str, field: str, *, name: str | None = None,
                   label: str | None = None,
                   choices: tuple[str, ...] | None = None,
                   legal_in: tuple[str, ...] | None = None) -> CommandSpec:
    """A SET_SCALAR command; name defaults to set<Field> (setKind, setComponent) and the description
    to 'set the <field>'. The single arg is named after the field and carries the field's `choices`
    when it is an enum. The field's instruction is not copied here."""
    return CommandSpec(name or f"set{_cap(field)}", SET_SCALAR,
                       f"set the {_setter_label(section, field, label)}",
                       section=section, field=field,
                       args=(_text(field, choices=choices),), legal_in=legal_in)


def list_cmds(section: str, *, field: str = "items", singular: str | None = None,
              label: str | None = None, add_args: tuple[ArgSpec, ...] | None = None,
              legal_in: tuple[str, ...] | None = None, ref_check: RefCheck | None = None,
              add: bool = True, remove: bool = True, reorder: bool = True,
              add_name: str | None = None, remove_name: str | None = None,
              reorder_name: str | None = None) -> tuple[CommandSpec, ...]:
    """The add/remove/reorder commands for a LIST field; select a subset with add=/remove=/reorder=
    (a flow-populated list that is filled elsewhere asks for its reorder only). The noun (command names
    + `<noun>Id` arg) is the singular of the field when it is not the generic 'items', else of the
    section; `singular=` overrides an irregular plural. The add's element_map is derived from `add_args`
    (each mapped onto a same-named element field, so `add_args` names ARE the field names), and
    _INDEX/_PRECEDING are appended to it; the reorder carries the anchored (toIndex + precedingId)
    stale-read guard - so the 'every list field has a reorder' and 'every add supports positioned
    insert' invariants hold by construction. An add that references another page carries a
    `ref_check`, as `add_block_cmd` does; the remove and reorder name an element already on this
    page, so they do not."""
    noun = singular or _singular(field if field != "items" else section)
    cap, id_arg, label = _cap(noun), f"{noun}Id", label or noun
    out: list[CommandSpec] = []
    if add:
        out.append(CommandSpec(add_name or f"add{cap}", ADD_ELEMENT, f"add {_a(label)} {label}",
                               section=section, field=field, args=(*(add_args or tuple()), _INDEX, _PRECEDING),
                               element_map=_same_named(add_args or tuple()),
                               ref_check=ref_check, legal_in=legal_in))
    if remove:
        out.append(CommandSpec(remove_name or f"remove{cap}", REMOVE_ELEMENT, f"remove {_a(label)} {label}",
                               section=section, field=field, args=(_text(id_arg),), legal_in=legal_in))
    if reorder:
        out.append(CommandSpec(
            reorder_name or f"reorder{cap}", REORDER_ELEMENT,
            f"move {_a(label)} {label} to an anchored position (precedingId guards a stale read)",
            section=section, field=field,
            args=(_text(id_arg), _integer("toIndex"), _PRECEDING), legal_in=legal_in))
    return tuple(out)


def element_cmds(section: str, *, field: str = "items", singular: str | None = None,
                 marks: tuple[tuple[str, str, str, Any] | tuple[str, str, str], ...], legal_in: tuple[str, ...] | None = None) -> tuple[CommandSpec, ...]:
    """ELEMENT_TRANSITION commands for an element-FSM list. Each `marks` entry is
    (name, event, description) or (name, event, description, extra_args) - the derived `<noun>Id` arg
    identifies the element, and any `extra_args` are appended and mapped onto same-named element fields
    (so a transition can also write a field, not just fire its event)."""
    id_arg = f"{singular or _singular(section)}Id"
    out: list[CommandSpec] = []
    for mark in marks:
        name, event, description = mark[0], mark[1], mark[2]
        extra = mark[3] if len(mark) > 3 else ()
        out.append(CommandSpec(name, ELEMENT_TRANSITION, description, section=section, field=field,
                               event=event, args=(_text(id_arg), *extra),
                               element_map=_same_named(extra), legal_in=legal_in))
    return tuple(out)


def set_element_field_cmd(section: str, *, name: str, const: tuple[str, Any], description: str = "",
                          field: str = "items", singular: str | None = None,
                          legal_in: tuple[str, ...] | None = None) -> CommandSpec:
    """A SET_ELEMENT_FIELD command that stamps a constant `(field, value)` onto the id'd element - the
    flag-setting shape (raise a fixed flag on one element without touching the rest)."""
    id_arg = f"{singular or _singular(section)}Id"
    return CommandSpec(name, SET_ELEMENT_FIELD, description, section=section, field=field,
                       args=(_text(id_arg),), element_const=(const,), legal_in=legal_in)


# Standard args per block kind, so add_block_cmd fills them in from the kind alone (override via args=).
_BLOCK_ARGS: dict[str, tuple[ArgSpec, ...]] = {
    "paragraph": (_array("inlines", content=INLINE_RUNS),),
    "heading": (_integer("level"), _array("inlines", content=INLINE_RUNS)),
    "code": (_text("language"), _text("source")),
    "list": (_boolean("ordered"), _array("items", content=INLINE_RUN_LISTS)),
    "quote": (_array("paragraphs", content=INLINE_RUN_LISTS),),
    "table": (_array("header", content=INLINE_RUN_LISTS), _array("rows", content=INLINE_RUN_GRID),
              _array("align", required=False, content=TABLE_ALIGN)),
    "divider": (),
}


def add_block_cmd(section: str, kind: str, *, add_name: str | None = None, set_name: str | None = None,
                  add_description: str | None = None, set_description: str | None = None, field: str = "body",
                  args: tuple[ArgSpec, ...] | None = None, ref_check: RefCheck | None = None,
                  legal_in: tuple[str, ...] | None = None) -> tuple[CommandSpec, ...]:
    """The ADD_BLOCK and matching in-place SET_BLOCK for one block kind (the set is skipped only for a
    kind with no body args, e.g. divider - there is nothing to replace). Body args default to
    `_BLOCK_ARGS[kind]` (override with args=) and the element_map is derived from them (same-named);
    the add carries positioned-insert args, the set takes a leading `blockId`. `add_name` defaults to
    add<Kind>, `set_name` to that add_name with 'add'->'set' (so add<Kind>->set<Kind>)."""
    body_args = _BLOCK_ARGS[kind] if args is None else args
    emap = _same_named(body_args)
    add_name = add_name or f"add{_cap(kind)}"
    add = CommandSpec(add_name, ADD_BLOCK, add_description or f"add {_a(kind)} {kind} block to {section}",
                      section=section, field=field, block_kind=kind,
                      args=(*body_args, _INDEX, _PRECEDING), element_map=emap,
                      ref_check=ref_check, legal_in=legal_in)
    if not body_args:
        return (add,)
    set_name = set_name or (f"set{add_name[3:]}" if add_name.startswith("add") else f"set{_cap(kind)}")
    set_cmd = CommandSpec(set_name, SET_BLOCK, set_description or f"replace {_a(kind)} {kind} block in {section}",
                          section=section, field=field, block_kind=kind,
                          args=(_text("blockId"), *body_args), element_map=emap,
                          ref_check=ref_check, legal_in=legal_in)
    return (add, set_cmd)


def block_cmds(section: str, *adds: CommandSpec, field: str = "body",
               remove_name: str = "removeBlock", remove_desc: str = "remove a block",
               reorder_name: str = "reorderBlock", reorder_desc: str | None = None,
               legal_in: tuple[str, ...] | None = None) -> tuple[CommandSpec, ...]:
    """A blocks field's authoring set: the given add/set commands (spread from add_block_cmd) followed
    by the universal remove_block + reorder_block. A type with more than one blocks field must pass
    distinct remove_name/reorder_name so command names stay unique."""
    reorder_desc = reorder_desc or "move a block to an anchored position (precedingId guards a stale read)"
    remove = CommandSpec(remove_name, REMOVE_BLOCK, remove_desc, section=section, field=field,
                         args=(_text("blockId"),), legal_in=legal_in)
    reorder = CommandSpec(reorder_name, REORDER_BLOCK, reorder_desc, section=section, field=field,
                          args=(_text("blockId"), _integer("toIndex"), _PRECEDING), legal_in=legal_in)
    return (*adds, remove, reorder)


# The full rich blocks surface - one add (+ in-place set) per block kind, plus the universal
# remove/reorder. `add_block_cmd` generates each add/set description from the kind and section.
_ALL_BLOCK_KINDS = ("paragraph", "heading", "code", "list", "quote", "table", "divider")


def all_block_cmds(section: str, *, field: str = "body",
                   legal_in: tuple[str, ...] | None = None) -> tuple[CommandSpec, ...]:
    """Every block kind's add (+ in-place set where the kind has content) plus remove_block/reorder_block
    - the full rich blocks surface, in one call (one blocks field)."""
    adds: list[CommandSpec] = []
    for kind in _ALL_BLOCK_KINDS:
        adds.extend(add_block_cmd(section, kind, field=field, legal_in=legal_in))
    return block_cmds(section, *adds, field=field, legal_in=legal_in)


def transition_cmd(name: str, description: str, *, legal_in: tuple[str, ...] | None = None,
                   event: str | None = None, agency: str = "agent",
                   requires: tuple[tuple[str, str], ...] = (),
                   guards: tuple[ChildStateGuard, ...] = (),
                   parent_guards: tuple[ParentStateGuard, ...] = ()) -> CommandSpec:
    """A page-status TRANSITION command whose `description` carries the edge as 'from -> to'. A written
    '->' is substituted once to the arrow glyph '→', which the edge is then split on. The dest is the
    first word after the arrow - a trailing parenthetical is ignored (so 'a -> b (note)' resolves to
    b) - and is NOT overridable; it names the destination state. The source is the text before the
    arrow, which `legal_in` overrides (for a multi-source edge, or one whose 'from' is prose rather
    than a state name). `event` defaults to `name` (every transition fires an event of its own name)."""
    description = description.replace("->", "→")
    before, arrow, after = description.partition("→")
    words = after.split()
    if not arrow or not words:
        raise ValueError(f"transition_cmd({name!r}): description must read 'from -> to', got {description!r}")
    sources = tuple(legal_in) if legal_in is not None else (before.strip(),)
    return CommandSpec(name, TRANSITION, description, event=event or name, dest=words[0], legal_in=sources,
                       agency=agency, requires=requires, guards=guards, parent_guards=parent_guards)


def transition_on_add_cmd(name: str, t_description: str, *, legal_in: tuple[str, ...] | None = None, section: str,
                 field: str, add_args: tuple[ArgSpec, ...], description: str = "", event: str | None = None,
                 agency: str = "agent", requires: tuple[tuple[str, str], ...] = (),
                 guards: tuple[ChildStateGuard, ...] = (),
                 parent_guards: tuple[ParentStateGuard, ...] = ()) -> CommandSpec:
    """A COMPOUND that atomically adds an element to a list field AND fires a page transition.
    `t_description` carries the edge as 'from -> to'. The outer command owns
    the FSM edge (event/source/dest/agency) and its args; the element_map is derived
    from `add_args` (same-named); the two inner steps are the add and the transition."""
    t_description = t_description.replace("->", "→")
    before, arrow, after = t_description.partition("→")
    words = after.split()
    if not arrow or not words:
        raise ValueError(f"transition_on_add_cmd({name!r}): t_description must read 'from -> to', got {t_description!r}")
    sources = tuple(legal_in) if legal_in is not None else (before.strip(),)
    return CommandSpec(
        name, COMPOUND, f"{description} ({t_description})", event=event or name, dest=words[0], legal_in=sources, agency=agency,
        args=add_args, requires=requires, guards=guards, parent_guards=parent_guards,
        steps=(
            CommandSpec(f"_{name}Add", ADD_ELEMENT, section=section, field=field,
                        element_map=_same_named(add_args)),
            CommandSpec(f"_{name}", TRANSITION, event=event or name),
        ),
    )


# --- Inline-run validation (the `blocks` field grammar) ----------------------
# These are pure predicates the command layer runs before applying an add/set-block command.
# They enforce the run grammar above; a dangling `ref`'s *existence* is a cross-page concern
# checked in the store, not here (the pure core cannot see other pages).
def _reject_markdown(text: str) -> None:
    for token in _MARKDOWN_TOKENS:
        if token in text:
            raise ValidationError(
                f"Markdown syntax ('{token}') is not allowed in a text run - express emphasis " +
                f"or a link with a structured run (e.g. {{'text': '…', 'bold': true}}) instead."
            )


def _validate_run(run: Any) -> None:
    """Validate one inline run against the run grammar."""
    if isinstance(run, str):
        _reject_markdown(run)
        return
    if not isinstance(run, dict):
        raise ValidationError(f"An inline run must be a string or an object, got {type(run).__name__}.")
    keys = set(run)
    if "code" in run:
        if keys != {"code"} or not isinstance(run["code"], str):
            raise ValidationError("An inline code run must be exactly {'code': <string>}.")
        return
    if "ref" in run:
        if keys != {"ref"} or not isinstance(run["ref"], str):
            raise ValidationError("An inline ref run must be exactly {'ref': <pageId>}.")
        return
    if "text" in run:
        extra = keys - {"text", "bold", "italic", "href"}
        if extra:
            raise ValidationError(f"A text run has unknown keys: {sorted(extra)}.")
        if not isinstance(run["text"], str):
            raise ValidationError("A text run's 'text' must be a string.")
        for flag in ("bold", "italic"):
            if flag in run and not isinstance(run[flag], bool):
                raise ValidationError(f"A text run's '{flag}' must be a boolean.")
        if "href" in run and not isinstance(run["href"], str):
            raise ValidationError("A text run's 'href' must be a string.")
        _reject_markdown(run["text"])
        return
    raise ValidationError("An inline run object must be a text run, {'code': …}, or {'ref': …}.")


def _validate_runs(runs: Any) -> None:
    if not isinstance(runs, list):
        raise ValidationError("An inline-run value must be an array of runs.")
    for run in runs:
        _validate_run(run)


def validate_inline_content(content: str, value: Any) -> None:
    """Validate `value` against the declared inline-content `content` shape (raises ValidationError)."""
    if content == INLINE_RUNS:
        _validate_runs(value)
    elif content == INLINE_RUN_LISTS:
        if not isinstance(value, list):
            raise ValidationError("Expected an array of inline-run arrays.")
        for entry in value:
            _validate_runs(entry)
    elif content == INLINE_RUN_GRID:
        if not isinstance(value, list):
            raise ValidationError("Expected an array of table rows.")
        for row in value:
            if not isinstance(row, list):
                raise ValidationError("Each table row must be an array of cells.")
            for cell in row:
                _validate_runs(cell)
    elif content == TABLE_ALIGN:
        if not isinstance(value, list):
            raise ValidationError("Table 'align' must be an array.")
        for entry in value:
            if entry not in _ALIGN_VALUES:
                raise ValidationError(
                    f"Table alignment must be one of left/center/right/null, got {entry!r}."
                )


def collect_ref_ids(content: str, value: Any) -> list[str]:
    """Every `{ref: pageId}` page id carried by an inline-run arg `value` of the given `content` shape.

    Used by the store to integrity-check inline page references before a write (the pure core cannot
    see other pages). Deliberately defensive - it only pulls a string `ref` out of a dict run and
    ignores anything else - because it runs *before* the grammar validation in `apply_command`, just
    as the existing cross-page ref check does; a malformed run is left for that validation to reject.
    `TABLE_ALIGN` carries no runs, so it yields nothing.
    """
    ids: list[str] = []

    def from_runs(runs: Any) -> None:
        if isinstance(runs, list):
            ids.extend(run["ref"] for run in runs
                       if isinstance(run, dict) and isinstance(run.get("ref"), str))

    if content == INLINE_RUNS:
        from_runs(value)
    elif content == INLINE_RUN_LISTS:
        for entry in value if isinstance(value, list) else []:
            from_runs(entry)
    elif content == INLINE_RUN_GRID:
        for row in value if isinstance(value, list) else []:
            for cell in row if isinstance(row, list) else []:
                from_runs(cell)
    return ids


def validate_table(header: Any, rows: Any, align: Any) -> None:
    """Table width consistency: every row (and `align`, if given) matches the header's column count."""
    width = len(header)
    for index, row in enumerate(rows):
        if len(row) != width:
            raise ValidationError(
                f"Table row {index} has {len(row)} cells but the header has {width} - widths must match."
            )
    if align is not None and len(align) != width:
        raise ValidationError(
            f"Table 'align' has {len(align)} entries but the header has {width} columns."
        )


def initial_sections(page_type: PageType) -> dict[str, dict[str, Any]]:
    """The empty section/field state a freshly created page of this type starts with."""
    sections: dict[str, dict[str, Any]] = {}
    for section in page_type.sections:
        field_values: dict[str, Any] = {}
        for field_spec in section.fields:
            if field_spec.kind == PROSE:
                field_values[field_spec.key] = ""
            elif field_spec.kind in (LIST, BLOCKS):
                field_values[field_spec.key] = []
            else:  # SCALAR
                field_values[field_spec.key] = None
        sections[section.key] = field_values
    return sections


# --- Shared page-type declarations -------------------------------------------
# States allowing modifications to the commit log.
_COMMIT_LOG_STATES = ("building", "review", "shipped")


# The two guards that stage the pinned children, both enforced in the store: the spec is unlocked
# a stage before the plans are.
_FEATURE_IN_SPEC_OR_LATER = ParentStateGuard(
    parent_type="feature-brief",
    required_statuses=("spec", "planning", "planReview", "building", "review", "shipped"),
    message="the feature-brief must be in spec or later",
)

_FEATURE_IN_PLANNING_OR_LATER = ParentStateGuard(
    parent_type="feature-brief",
    required_statuses=("planning", "planReview", "building", "review", "shipped"),
    message="the feature-brief must be in planning or later",
)


# An epic's pinned agent plan may only be finalized once the epic has reached `decomposition` or
# later - not while it is still in `draft` or `grounding` (the base is still being established),
# nor once `abandoned`. Enforced in the store.
_EPIC_IN_DECOMPOSITION_OR_LATER = ParentStateGuard(
    parent_type="epic",
    required_statuses=("decomposition", "planReview", "executing", "review", "shipped"),
    message="the epic must be in decomposition or later",
)


# --- The page types ----------------------------------------------------------
# Imported last: a page-type module reads these declarations back out of the package as it
# builds, so anything it uses has to be declared above this point.
from .architecture import _ARCHITECTURE
from .decision_record import _DECISION_RECORD
from .bug_report import _BUG_REPORT
from .simple_change import _SIMPLE_CHANGE
from .feature import (
    _FEATURE_BRIEF,
    _FEATURE_SPEC,
    _IMPLEMENTATION_PLAN,
    _TESTING_PLAN,
)
from .epic import _EPIC
from .agent_plan import _AGENT_PLAN
from .document import _DOCUMENT
from .toc import _TOC


REGISTRY: dict[str, PageType] = {
    _ARCHITECTURE.tag: _ARCHITECTURE,
    _DECISION_RECORD.tag: _DECISION_RECORD,
    _BUG_REPORT.tag: _BUG_REPORT,
    _SIMPLE_CHANGE.tag: _SIMPLE_CHANGE,
    _FEATURE_BRIEF.tag: _FEATURE_BRIEF,
    _FEATURE_SPEC.tag: _FEATURE_SPEC,
    _IMPLEMENTATION_PLAN.tag: _IMPLEMENTATION_PLAN,
    _TESTING_PLAN.tag: _TESTING_PLAN,
    _EPIC.tag: _EPIC,
    _AGENT_PLAN.tag: _AGENT_PLAN,
    _DOCUMENT.tag: _DOCUMENT,
    _TOC.tag: _TOC,
}


# --- Test-only page types ----------------------------------------------------
# The `test-*` types (src.testtypes) are hand-authored, minimal capability fixtures - each
# demonstrates one part of the page-type system so tests exercise the full surface without pinning
# to (or cloning) any production type's shape. They are RESOLVABLE by `get_page_type` - so the
# store, renderer, and pure core all operate on a test page the same as any other - but HIDDEN from
# discovery (the `describePageType` listing and doc-gen enumeration) unless this test-only flag is
# set. Never set in production; flip it for the scope of a block with `expose_test_types()`.
_expose_test_types = False


def _test_registry() -> dict[str, PageType]:
    # Lazy import: src.testtypes imports the spec classes from THIS module, so importing it
    # at top level would be a cycle. Resolved here at call time, once both modules are loaded.
    from ..testtypes import TEST_REGISTRY

    return TEST_REGISTRY


@contextmanager
def expose_test_types() -> Generator[None]:
    """Test-only: reveal the hand-authored test-only types to `registered_tags` and
    `discoverable_registry` (hence the `describePageType` listing and doc-gen enumeration) for the
    duration of the block. Resolution via `get_page_type` is always on and is unaffected."""
    global _expose_test_types
    previous = _expose_test_types
    _expose_test_types = True
    try:
        yield
    finally:
        _expose_test_types = previous


# --- Test mode: production page types are off-limits to the test suite -------
# Separate from `_expose_test_types` (which gates only the DISCOVERY of the test-* fixtures): under
# test mode the PRODUCTION page types become inaccessible so a test can only ever exercise the
# hand-authored test-* fixtures. They stop RESOLVING (`get_page_type`), stop being LISTED
# (`registered_tags` / `discoverable_registry`, hence the describePageType listing + doc-gen), and a
# page of one cannot be CREATED - every such attempt raises `ProductionTypeInTestError`, steering the
# author to a test-* fixture. Flipped on for the whole suite by tests/conftest.py; never set in
# normal operation, where the guard is entirely inert.
_test_mode = False


def set_test_mode(on: bool = True) -> None:
    """Test-only: enter (or leave) test mode, in which production page types are off-limits - they do
    not resolve, are not listed, and cannot be instantiated (see `ProductionTypeInTestError`).
    tests/conftest.py flips this on (via a session-scoped autouse fixture, so it takes effect AFTER
    collection) for the whole run. Never called in normal operation."""
    global _test_mode
    _test_mode = on


def guard_production_type(tag: str) -> None:
    """Raise if `tag` names a production page type while in test mode - the shared guard behind both
    resolution (`get_page_type`) and creation (`commands.create_page`)."""
    if _test_mode and tag in REGISTRY:
        raise ProductionTypeInTestError(
            f"Production page type {tag!r} is off-limits in tests. Test new capabilities on a " +
            f"test-* page instead (always prefer an existing one; see src/testtypes.py)."
        )


def get_page_type(tag: str) -> PageType | None:
    """Resolve a page type by tag. The hand-authored test-only types resolve too (see
    `expose_test_types`), so the store and pure core operate on them; only their *discovery* is
    flag-gated. In test mode a PRODUCTION tag raises `ProductionTypeInTestError` instead of resolving
    (an unknown tag still returns None) - tests operate on the test-* fixtures, not production types."""
    test_type = _test_registry().get(tag)
    if test_type is not None:
        return test_type
    guard_production_type(tag)
    return REGISTRY.get(tag)


def registered_tags() -> list[str]:
    """The advertised page-type tags. The test-only types are excluded unless `_expose_test_types`
    is set - this is what keeps `describePageType`'s listing production-only in normal operation. In
    test mode the production types are hidden too (they are off-limits), so the listing shows only the
    test-* fixtures the `_expose_test_types` flag reveals."""
    tags = [] if _test_mode else list(REGISTRY.keys())
    if _expose_test_types:
        tags += list(_test_registry().keys())
    return tags


def discoverable_registry() -> dict[str, PageType]:
    """The registry that doc generation enumerates: production only, plus the hand-authored test-only
    types when `_expose_test_types` is set. Default (flag off) keeps generated docs production-only.
    In test mode the production types are hidden (off-limits), leaving only the test-* fixtures the
    `_expose_test_types` flag reveals."""
    registry: dict[str, PageType] = {} if _test_mode else dict(REGISTRY)
    if _expose_test_types:
        registry.update(_test_registry())
    return registry


def is_auto_child_type(parent_type: PageType | None, child_type: str) -> bool:
    """Whether `child_type` is an auto-created (pinned, protected) child of `parent_type`."""
    return parent_type is not None and any(spec.type == child_type for spec in parent_type.auto_children)
