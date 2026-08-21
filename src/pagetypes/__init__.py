"""Page-type registry: page types expressed as data, not code.

A `PageType` fixes a page's sections, field kinds, legal commands, and status FSM.
`createPage` initializes from it, `commands.py` enforces it, and `describePageType`
reports it.
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


_ARCHITECTURE = PageType(
    tag="architecture",
    name="Architecture node",
    description=(
        "Documents a part of the system that already exists in the codebase: its purpose, "
        "data model, code references, dependencies, and whether it is current or has drifted."
    ),
    sections=(
        SectionSpec("summary", "Summary", (
            _scalar("kind", choices=_NODE_KINDS, description="""
                The granularity of the thing this page documents, one of
                module/component/subsystem/service/layer/package. Pick the narrowest kind that
                honestly fits, and stay consistent with the sibling architecture pages so the tree
                reads at a uniform scale.
                """),
            _prose("body", description="""
                One line, in the present tense, naming what this part of the system IS and the job it
                does. Describe the code as it exists today, not as it is meant to become. Leave the
                why to Purpose and the shapes to Data model.
                """),
        )),
        SectionSpec("purpose", "Purpose", (
            _prose("body", description="""
                Why this part exists: the problem it solves and the role it plays for the rest of the
                system. Say what would break, or become much harder, if it were deleted. Do not
                restate the summary in longer words.
                """)
        ,)),
        SectionSpec("usage", "Usage", (
            _prose("body", description="""
                How callers actually use this part: the entry points they go through, who those
                callers are, and any required call order or lifecycle. Name the real functions,
                endpoints, or commands rather than describing them in the abstract, so a reader can
                grep for them.
                """)
        ,)),
        SectionSpec("dataModel", "Data model", (
            _prose("body", description="""
                The data this part owns: its key types and their fields, which values are persisted
                versus derived, and how long each lives. State who is allowed to mutate the state and
                through what path.
                """)
        ,)),
        SectionSpec("details", "Details", (
            _blocks("body", description="""
                Design notes that do not fit the fixed sections: rationale, trade-offs that were
                considered and rejected, gotchas, and worked examples. Use a code block for anything a
                reader would otherwise have to reconstruct from prose. Emphasis and links are
                structured inline runs, not markdown syntax.
                """),
        )),
        SectionSpec("codeReferences", "Code references", (
            _list("items", element_fields=("file", "symbol", "kind"), description="""
                Each a pointer into real source: the repo-relative file path, the symbol when the
                reference is narrower than the whole file, and that symbol's kind
                (file/function/class/type/interface/constant). Add one per place a reader must open to
                understand or change this node. Confirm the path and symbol exist before recording
                them; a stale pointer is worse than none.
                """),
        )),
        SectionSpec("dependencies", "Dependencies", (
            _list("items", element_fields=("target", "role", "note"), description="""
                Each an edge from this node to another page: the target, the role this node plays
                toward it (depends-on/exposes/implements/owns/calls), and a note saying what actually
                crosses the boundary. Record the direction this node experiences, not the reverse, and
                keep one edge per element.
                """),
        )),
        SectionSpec("invariants", "Invariants", (
            _list("items", element_fields=("statement",), description="""
                Each one property that must always hold for this node, written as a checkable
                assertion about state or behaviour rather than an aspiration, and paired with what
                breaks when it is violated. One invariant per element.
                """),
        )),
        SectionSpec("sync", "Sync", (
            _scalar("commit", description="""
                The commit sha this page was last reconciled against. Record the sha you actually read
                the code at, so a later reader can diff from it to find exactly what has drifted.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("summary", "kind", choices=_NODE_KINDS),
        set_prose_cmd("summary"),
        set_prose_cmd("purpose"),
        set_prose_cmd("usage"),
        set_prose_cmd("dataModel", label="data model"),
        # `details` is a `blocks` field with a deliberately narrow surface: a prose note (inline
        # runs) or a code note, plus the universal remove/reorder.
        *block_cmds(
            "details",
            *add_block_cmd("details", "paragraph", add_name="addNote"),
            *add_block_cmd("details", "code", add_name="addNoteCode"),
            remove_name="removeNote", remove_desc="remove a note block",
            reorder_name="reorderNote",
            reorder_desc="move a note block to an anchored position (precedingId guards a stale read)"),
        *list_cmds("codeReferences", label="code reference",
                   add_args=(_text("file"), _text("symbol", required=False),
                             _text("kind", required=False, choices=_CODE_REF_KINDS))),
        *list_cmds("dependencies",
                   add_args=(_text("target"), _text("role", choices=_DEP_ROLES),
                             _text("note", required=False))),
        *list_cmds("invariants", add_args=(_text("statement"),)),
        set_scalar_cmd("sync", "commit", name="recordSync", label="sync commit"),
        transition_cmd("markCurrent", "authoring -> current"),
        transition_cmd("author", "current -> authoring"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Architecture",
        initial="authoring",
        states=("authoring", "current"),
        terminal_states=("current",),
        state_guidance=(("authoring", """
            authoring - documents a part of the system that already exists, written by reading
            that code rather than recalling it. The work of it:

            - Fix the boundary first: one part, one granularity, a job stated in one line. If
              that line needs an "and", it is two nodes.
            - Describe what is there today. Aspirational architecture belongs in a feature
              brief, and a page mixing the two describes neither.
            - Write what one file cannot show: why it exists, where its boundary runs, what
              crosses it, what must stay true. Point at a symbol rather than copy it.
            - Say which side of the pure/effectful line the node sits on, and where that line
              runs inside it. A reader deciding where new behaviour belongs needs that first.
            - Write invariants that can be checked and broken, with what breaks when violated.
              "Stays consistent" is not one.
            - Record dependencies in the direction this node experiences them, naming what
              crosses the boundary.
            - Confirm each code reference by opening it, then record the commit you read at.

            Why it is shaped this way belongs in a decision record, linked from here. Keep the
            page at the scale of its siblings, and when the code moves on mark it stale rather
            than leave it describing an older system - a stale page is locked until markCurrent
            brings it back here.
            """),),
    ),
)


_DECISION_RECORD = PageType(
    tag="decision-record",
    name="Decision record",
    description=(
        "Records ONE architectural decision - its context, the options weighed, the choice made, "
        "and the consequences - as a durable dated rationale. Captures WHY the system is shaped "
        "the way it is; the shape itself belongs on an architecture page."
    ),
    sections=(
        SectionSpec("meta", "Meta", (
            _scalar("date", description="""
                The date the decision was taken, as YYYY-MM-DD - the date of the decision, not of
                the page. A record's weight decays as the system moves on, and a reader can only
                judge how much of it still applies against the real date.
                """),
            _scalar("scope", description="""
                What this decision governs: the subsystem, service, or cross-cutting concern it
                binds. Keep it to the narrowest scope the reasoning actually reaches - a record
                scoped to the whole system binds work it was never reasoned about.
                """),
            _list("deciders", element_fields=("name",), description="""
                Each one person or group who took this decision, one per element. Record who
                actually decided rather than everyone who was in the room, so a later reader
                knows who to ask once the context has gone stale.
                """),
        )),
        SectionSpec("context", "Context", (
            _prose("body", description="""
                The forces that made a decision necessary, written for a reader who was not there:
                the constraints in play, the state of the system at the time, and what was being
                traded against what. Say what made it hard. This is the section worth the most
                years later and the one skipped the most often, so write it before the decision
                itself - if the context does not make the decision feel necessary, it is not
                finished.
                """),
        )),
        SectionSpec("decision", "Decision", (
            _blocks("body", description="""
                What was decided, in the active voice and stated before any supporting detail, then
                the options that were seriously weighed and what ruled each one out. Use a code
                block for anything with a precise shape: an interface, a schema, a config. A record
                that names no rejected option is a note rather than a decision, because nothing in
                it explains why the alternatives are not still open.
                """),
        )),
        SectionSpec("consequences", "Consequences", (
            _blocks("body", description="""
                What this decision makes easy and what it makes hard, including the costs now to be
                lived with, what it forecloses, and the follow-on work it creates. Consequences
                that are all benefits mean the trade-off has not been thought through yet - the
                reader inheriting the cost is the one this section is written for.
                """),
        )),
        SectionSpec("relations", "Relations", (
            _scalar("supersededBy", description="""
                The page id of the decision record that replaces this one, recorded whenever a
                later decision overtakes it. A record is never edited to reverse itself - the
                reasoning that held at the time has to stay readable - so this pointer is what
                carries a reader forward to the reasoning that replaced it, and it is the one
                field that stays writable after the record is accepted.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("meta", "date"),
        set_scalar_cmd("meta", "scope"),
        *list_cmds("meta", field="deciders", add_args=(_text("name"),)),
        set_prose_cmd("context"),
        # Two blocks fields on one type, so each passes its own remove/reorder names.
        *block_cmds(
            "decision",
            *add_block_cmd("decision", "paragraph", add_name="addDecisionBlock", args=(_text(),)),
            *add_block_cmd("decision", "code", add_name="addDecisionCode"),
            remove_name="removeDecisionBlock", remove_desc="remove a decision block",
            reorder_name="reorderDecisionBlock",
            reorder_desc="move a decision block to an anchored position (precedingId guards a stale read)"),
        *block_cmds(
            "consequences",
            *add_block_cmd("consequences", "paragraph", add_name="addConsequence", args=(_text(),)),
            remove_name="removeConsequence", remove_desc="remove a consequence",
            reorder_name="reorderConsequence",
            reorder_desc="move a consequence to an anchored position (precedingId guards a stale read)"),
        # The one authoring command that opts back into the terminal state: a record is
        # overtaken by a later one long after it was accepted.
        set_scalar_cmd("relations", "supersededBy", label="superseding record",
                       legal_in=("authoring", "accepted")),
        transition_cmd("markAccepted", "authoring -> accepted"),
        transition_cmd("author", "accepted -> authoring"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="DecisionRecord",
        initial="authoring",
        states=("authoring", "accepted"),
        terminal_states=("accepted",),
        state_guidance=(("authoring", """
            authoring - captures why one decision was taken, while the reasons are still in
            someone's head. The shape it produces belongs on an architecture page; the reasoning
            that shape cannot show belongs here. The work of it:

            - One decision per record, titled with the position taken rather than the topic:
              "store sessions in the database", not "session storage".
            - Write the context first, for someone who was not there: the forces, the
              constraints, what was traded against what. It is worth the most in a year and
              skipped the most often.
            - State the decision in the active voice, before any detail. A reader should not
              have to infer it from a discussion of the options.
            - Record the options weighed and what ruled each out. Without a rejected
              alternative, nothing stops the question being reopened.
            - Give consequences both ways. Only benefits reads as advocacy to whoever inherits
              the cost.
            - Say where the decision moves the line between pure logic and effectful code - an
              architecture page can show that boundary but not explain it.
            - Fill in date, scope and deciders, so a later reader can weigh how much still
              applies.
            """),),
    ),
)


_BUG_REPORT = PageType(
    tag="bug-report",
    name="Bug report",
    description="Tracks ONE defect in existing behavior - what's wrong, how to reproduce it, and its resolution.",
    sections=(
        SectionSpec("report", "Report", (
            _scalar("component", description="""
                The component or area of the system the defect lives in. Use the name the codebase or
                an existing architecture page already uses, so related reports group together.
                """),
            _scalar("platform", description="""
                The platform the defect was observed on: OS, browser, runtime, or device, with
                versions. Record what you actually reproduced on, not the full supported matrix.
                """),
            _scalar("version", description="""
                The version, build, or commit sha the defect was observed in. Prefer a sha when the
                build is not tagged, so the report stays pinnable to a point in history.
                """),
        )),
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                One sentence naming the wrong behaviour, specific enough to tell this defect apart
                from similar ones. State the symptom you can observe, not the cause you suspect or the
                fix you have in mind.
                """),
        )),
        SectionSpec("repro", "Reproduction", (
            _list("steps", element_fields=("text",), description="""
                Each one action that leads to the defect, in order, beginning from a stated starting
                state. Give the exact commands, inputs, and data used, so someone who has never seen
                the system can follow them. The last step is the one that exposes the defect.
                """),
        )),
        SectionSpec("expected", "Expected", (
            _prose("body", description="""
                What should have happened at the final repro step, and what makes that the correct
                behaviour: a spec line, a doc, a passing test, or an established convention. Without
                that grounding the report is an opinion.
                """),
        )),
        SectionSpec("observed", "Observed", (
            _prose("body", description="""
                What actually happened at the final repro step: the literal error message, stack
                trace, exit code, or wrong output, quoted rather than paraphrased. Say whether it
                reproduces every time or intermittently.
                """),
        )),
        SectionSpec("resolution", "Resolution", (
            _list("fixCommits", element_fields=("sha", "message", "url"), description="""
                Each a commit that fixes this defect, recorded as the bug is closed: the sha, its
                subject line, and a url when one exists. Record the commit that actually lands the
                fix, not the intermediate work that led to it.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("report", "component"),
        set_scalar_cmd("report", "platform"),
        set_scalar_cmd("report", "version"),
        set_prose_cmd("summary"),
        *list_cmds("repro", field="steps", label="repro step",
                   add_args=(_text(),)),
        set_prose_cmd("expected"),
        set_prose_cmd("observed"),
        transition_cmd("open", "draft -> open"),
        # open -> done marks the fix built but not yet verified as shippable or merged to main.
        transition_cmd("markDone", "open -> done"),
        # close is a human gate: a person confirms the fix is shippable/merged before it lands.
        transition_on_add_cmd("close", "done -> closed", section="resolution", field="fixCommits",
                     description="record a fix commit AND close the bug", agency="human",
                     add_args=(_text("sha"), _text("message"), _text("url", required=False))),
        transition_on_add_cmd("closeWithoutCommit", "done -> closed", section="resolution", field="fixCommits",
                     description="record a closing note (message only, no commit) AND close the bug", agency="human",
                     add_args=(_text("message"),)),
        # fixCommits is populated only by `close`; reorder is offered for a uniform surface.
        *list_cmds("resolution", field="fixCommits", label="fix commit", add=False, remove=False),
        transition_cmd("reopen", "closed -> open"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="BugReport",
        initial="draft",
        states=("draft", "open", "done", "closed"),
    ),
)


_SIMPLE_CHANGE = PageType(
    tag="simple-change",
    name="Simple change",
    description=(
        "Tracks ONE small, self-contained change or minor feature through a lightweight flow "
        "(draft -> open -> done -> closed) - no planning, spec, testing, or review gates. Use this "
        "page type ONLY when the user specifically asks to make a small/simple change or a small/simple "
        "feature; for larger work create a feature-brief, and for a defect in existing behavior use "
        "a bug-report."
    ),
    sections=(
        SectionSpec("change", "Change", (
            _scalar("component", description="""
                The component or area this change touches. Keep it to one: work that spans several
                components is not a simple change and belongs in a feature-brief instead.
                """),
        )),
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                What to change, in a sentence or two: the behaviour today and the behaviour you want
                in its place. Concrete enough that someone could start work from this line alone.
                """),
        )),
        SectionSpec("motivation", "Motivation", (
            _prose("body", description="""
                Why the change is worth making: who it affects and what it costs to leave things as
                they are. If someone asked for it, say who and what they actually asked for.
                """
                ),
        )),
        SectionSpec("acceptance", "Acceptance", (
            _list("criteria", element_fields=("text",), description="""
                Each one checkable statement of what done looks like, phrased so it is unambiguously
                true or false once the change is made. Cover the new behaviour AND anything nearby
                that must keep working. A criterion that can only be settled by opinion is not one.
                """),
        )),
        SectionSpec("resolution", "Resolution", (
            _list("changeCommits", element_fields=("sha", "message", "url"), description="""
                Each a commit that delivers this change, recorded as it is closed: the sha, its
                subject line, and a url when one exists.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("change", "component"),
        set_prose_cmd("summary"),
        set_prose_cmd("motivation"),
        *list_cmds("acceptance", field="criteria", singular="criterion", label="acceptance criterion",
                   add_args=(_text(),)),
        transition_cmd("open", "draft -> open"),
        # open -> done marks the change built but not yet verified as shippable or merged to main.
        transition_cmd("markDone", "open -> done"),
        # close is a human gate: a person confirms the change is shippable/merged before it lands.
        transition_on_add_cmd("close", "done -> closed", section="resolution", field="changeCommits",
                     description="record a change commit AND close the change", agency="human",
                     add_args=(_text("sha"), _text("message"), _text("url", required=False))),
        transition_on_add_cmd("closeWithoutCommit", "done -> closed", section="resolution", field="changeCommits",
                     description="record a closing note (message only, no commit) AND close the change", agency="human",
                     add_args=(_text("message"),)),
        # changeCommits is populated only by `close`; reorder is offered for a uniform surface.
        *list_cmds("resolution", field="changeCommits", label="change commit", add=False, remove=False),
        transition_cmd("reopen", "closed -> open"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SimpleChange",
        initial="draft",
        states=("draft", "open", "done", "closed"),
    ),
)


# States allowing modifications to the commit log.
_COMMIT_LOG_STATES = ("building", "review", "shipped")

_FEATURE_BRIEF = PageType(
    tag="feature-brief",
    name="Feature (root)",
    description=(
        "The root of a feature you intend to build - drives new work from intent through "
        "grounding, planning, and a plan review to a human review gate. Lifecycle transitions "
        "are gated on the required content for that stage being present first. Every stage "
        "biases toward caution over speed: surface a confusion rather than assume past it, and "
        "keep what you write to the smallest thing that solves the stated problem."
    ),
    sections=(
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                The feature intent in a sentence or two: what you want to build and why it is worth
                building, restated in your own words rather than echoed back - where your
                restatement and the ask diverge is the first thing to settle. Write it before
                reading any code, because grounding searches the repo from this line. State the
                outcome you want, not the implementation you imagine, and say so here if the ask
                itself looks wrong or underspecified rather than quietly building past it.
                """),
        )),
        SectionSpec("components", "Components", (
            _list("items", element_fields=("name",), description="""
                Each one part of the system this feature touches, named as a real file, module, or
                subsystem path you CONFIRMED exists while grounding. One per element. List only what
                the work will actually read or change: a guessed component sends the whole plan down
                the wrong path, and a missing one is discovered mid-build. Reach each one by
                following callers and imports rather than by guessing from names, so the list is the
                real blast radius. Say for each whether it holds pure logic or performs effects -
                I/O, storage, network, clock, randomness - because that is what decides where new
                code belongs.
                """),
        )),
        SectionSpec("constraints", "Constraints", (
            _list("items", element_fields=("text",), description="""
                Each one project-wide requirement the work must respect, with its exact values copied
                verbatim: version floors, dependency limits, naming and copy rules, platform and
                performance targets. Every plan step and every review inherits these, so a constraint
                recorded vaguely is a constraint that gets violated. Copy each value from where it is
                actually declared rather than from memory, and mark one you inferred rather than
                read, so a guess is not later spent as a fact.
                """),
        )),
        SectionSpec("conflicts", "Conflicts", (
            _list("items", element_fields=("text",), description="""
                Each one collision with what already exists, found while grounding: prior art that
                already solves part of this, an interface this feature would break, or a competing
                in-flight change. Name the file or page it collides with and say what has to give.
                Code that looks wrong, dead, or redundant belongs here as a collision to raise, not
                as something the build quietly deletes on its way past.
                """),
        )),
        SectionSpec("documentation", "Documentation", (
            _list("items", element_fields=("text",), description="""
                Each an existing pasta doc, architecture page or ADR this feature will make stale,
                found while grounding. Name the page and the specific part of it that will need to
                change, so reconciling it is mechanical rather than an investigation.
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"), element_fsm=_QUESTION_FSM, description="""
                Each one open question that blocks or reshapes the plan, asked as a single decidable
                question rather than a topic. A judgment call the user might reasonably disagree
                with is a question, not a decision to make quietly, and where the ask carries
                several readings all of them go here rather than one being picked in silence. Set
                needsHuman when only a person can settle it: a product call, a trade-off with no
                technically correct answer, or anything carrying cost or policy consequences.
                Answer it here once decided, then record the settled decision in the spec so it is
                not reopened during the build.
                """),
        )),
        # The plan review's outcome (populated in the `planReview` state): a verdict plus a summary
        # of the findings the review raised. The findings themselves are ALSO applied as real edits
        # (addStep / addCase / addConstraint / askQuestion); this section records what the review found.
        SectionSpec("review", "Plan review", (
            _scalar("verdict", choices=_VERDICTS, description="""
                The plan-review outcome. build-ready: an implementer could follow the plan end to end
                without getting stuck. needs-changes: at least one blocking finding must be applied
                before building. needs-human-decision: the plan cannot proceed until a person settles
                a question. Approve unless there are serious gaps, meaning a spec requirement no task
                covers, contradictory steps, placeholder content, or steps too vague to act on. A
                plan that builds more than the spec asked for, or abstracts something used once, is a
                serious gap too and not a matter of taste. Minor wording and style preferences are
                never a reason to withhold build-ready.
                """),
            _list("findings", element_fields=("issue", "severity", "action"), description="""
                Each one plan-review finding: what is wrong, why it matters for implementation, its
                severity, and the action taken to apply it to the plan. blocking means an implementer
                would build the wrong thing or get stuck; should-fix is real but survivable; nit is
                polish. Record the finding here AND make the edit its action names, so the plan and
                this record agree. Say where it applies, by step or spec section.
                """),
        )),
        SectionSpec("commits", "Commits", (
            _list("items", element_fields=("sha", "message", "url", "stale"), description="""
                Each a commit made for this feature while building: its sha, subject line, and a url
                when one exists. Record each as you make it rather than reconstructing the list at the
                end, and flag one stale once its sha has left history, for example after a rebase.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        *list_cmds("components", add_args=(_text("name"),)),
        *list_cmds("constraints", add_args=(_text(),)),
        *list_cmds("conflicts", add_args=(_text(),)),
        *list_cmds("documentation", add_args=(_text(),)),
        # Questions: a special add name (askQuestion) with an optional needsHuman flag and no remove,
        # an element-transition answer that also writes the answer, and an escalate that sets a flag.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        # Plan-review recording - legal only in the `planReview` state, where the authored plan is
        # reviewed before any code is written. `approvePlan` (planReview -> building) requires a
        # verdict to have been recorded first (see its `requires=` below).
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_VERDICTS,
                       legal_in=("planReview",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_SEVERITIES),
                             _text("action", required=False, choices=_FINDING_ACTIONS,
                                   description="how the finding was applied to the plan")),
                   legal_in=("planReview",)),
        *list_cmds("commits", add_name="recordCommit", label="recorded commit", remove=False,
                   add_args=(_text("sha"), _text("message"), _text("url", required=False)),
                   legal_in=_COMMIT_LOG_STATES),
        set_element_field_cmd("commits", name="markCommitStale", const=("stale", True),
                              description="flag a recorded commit as stale - its sha is no longer in history (e.g. after a rebase)",
                              legal_in=_COMMIT_LOG_STATES),
        # draft -> grounding needs only the intent: grounding reads the real repo from this
        # one-line summary and proposes the grounded base (components/constraints/conflicts + plans).
        transition_cmd("beginGrounding", "draft -> grounding", requires=(("summary", "body"),)),
        # grounding -> spec is gated on the grounding having produced a base: the components it
        # identified as touched, and what constrains / collides with / is made stale by the work.
        # From here only the feature-spec is authored - the two plans are held back.
        transition_cmd("beginSpec", "grounding -> spec", requires=(
            ("components", "items"),
            ("constraints", "items"),
            ("conflicts", "items"),
            ("documentation", "items"),
        )),
        transition_cmd("beginPlanning", "spec -> planning", requires=(("questions", "items"),), guards=(
            ChildStateGuard("feature-spec", "sealed", "the feature spec must be sealed"),
        )),
        # planning -> planReview is gated on the three planning artifacts being finalized: the
        # implementation-plan and testing-plan children each `ready` and the feature-spec `sealed`
        # (page-status guards checked across the brief's children by the store). The spec guard is
        # kept even though beginPlanning already required it - the spec can be `reopen`ed mid-planning,
        # and an unsealed spec must not reach review. There must be an authored plan before it can
        # be reviewed.
        transition_cmd("submitPlan", "planning -> planReview", guards=(
            ChildStateGuard("implementation-plan", "ready", "the implementation plan must be marked ready"),
            ChildStateGuard("testing-plan", "ready", "the testing plan must be marked ready"),
            ChildStateGuard("feature-spec", "sealed", "the feature spec must be sealed"),
        )),
        # planReview -> building requires a verdict to have been recorded (the review happened).
        # The verdict is a soft guide (requires only checks presence).
        transition_cmd("approvePlan", "planReview -> building", requires=(("review", "verdict"),)),
        transition_cmd("revisePlan", "planReview -> planning (send the plan back)"),
        transition_cmd("submitForReview", "building -> review"),
        transition_cmd("reopenPlanning", "building -> planning"),
        transition_cmd("requestChanges", "review -> building", agency="either"),
        # `ship` is a human gate AND is guarded: every implementation-plan step must be `done`
        # and every testing-plan case `passed` (checked across the brief's child pages by the store).
        transition_cmd("ship", "review -> shipped (human gate)", agency="human", guards=(
            ChildStateGuard("implementation-plan", "done", "every implementation-plan step must be done",
                            section="steps", field="items"),
            ChildStateGuard("testing-plan", "passed", "every testing-plan case must be passed",
                            section="cases", field="items"),
        )),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "grounding", "spec", "planning", "planReview", "building", "review")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="FeatureBrief",
        initial="draft",
        states=("draft", "grounding", "spec", "planning", "planReview", "building", "review",
                "shipped", "abandoned"),
        terminal_states=("shipped", "abandoned"),
        state_guidance=(
            ("grounding", """
                grounding - the summary is written and nothing else is known yet. This state is for
                reading the real repository and recording what is actually there. The work of it:

                - Find the code this feature touches and read it: the function, the file, the
                  callers. Understand why it exists, not just what it does. A component whose
                  purpose you cannot state is one you are not ready to plan against.
                - Record only what you confirmed by opening it. Every component, constraint,
                  conflict and stale doc here is read out of this repository, never inferred from a
                  name or remembered from somewhere else.
                - Follow callers and imports outward until the blast radius stops growing, and note
                  as you go which components hold pure logic and which perform effects.
                - Turn whatever reading could not settle into a question rather than an assumption.
                  An unsurfaced assumption is the most expensive thing to carry out of this state.

                No code is edited here and no design is started. If the summary turns out to be
                wrong or underspecified once you can see the code, say so now, while nothing has
                been built on it.
            """),
            ("spec", """
                spec - the grounded base is recorded, and the design is settled once, in the
                feature-spec child, before a single step or case exists. The work of it:

                - Author the spec from the grounded base: the behaviour, the interfaces with their
                  exact signatures, the data shapes, the states, the error paths. Decide everything
                  a plan would otherwise have to decide for itself.
                - Draw the line between pure logic and effects while designing rather than after.
                  Decide what is a function of its inputs alone and what needs I/O, storage, the
                  clock or randomness, and give each side its own interfaces. The rules live on the
                  pure side; the effectful side stays thin enough to hold none of its own.
                - Spec the smallest thing that delivers the summary. No configurability, extension
                  points or generality nobody asked for, and no abstraction over a single use.
                - Answer the brief's questions and record each decision with the alternatives it
                  rejected and why, so a settled question is not reopened mid-build.
                - Escalate what only a person can settle instead of settling it on their behalf.

                Seal the spec once it is settled; sealing is what unlocks planning. Steps and cases
                are not written here, because a design still moving is not one to plan against.
            """),
            ("planning", """
                planning - the spec is sealed and is now turned into an implementation plan and a
                testing plan detailed enough to build from without deciding anything further. The
                work of it:

                - Write each step as one action a skilled stranger to this codebase could finish in
                  a few minutes, naming the exact files and carrying the real content it needs.
                  Steps are read out of order and alone, so repeat detail rather than refer back.
                - Give every step its verification: what will be run, and what it should print or
                  return. A step with no way to tell whether it worked is not yet a step.
                - Order the work so the pure logic is built and tested before the effectful code
                  that calls it, and keep a step on one side of that line: a step that adds a rule
                  changes pure logic, a step that wires it to storage or the network changes the
                  shell around it.
                - Plan the failure paths the spec implies alongside the happy one - empty inputs,
                  missing values, malformed data, boundaries - and say what the volume this will
                  really see does to the approach.
                - Ask rather than guess. A question is cheap here and expensive once code exists.

                Keep both plans to what the spec asks for and nothing besides. Mark each ready when
                it is complete; submitting the plan needs both plans ready and the spec still
                sealed.
            """),
            ("planReview", """
                plan-review - the plan is written, and this is the last point at which fixing it is
                still cheap. This state is for reading the plan against the spec, not for building.
                The work of it:

                - Check every spec requirement against a step that delivers it, and every step
                  against a spec requirement that asked for it. A requirement no step covers and a
                  step nothing asked for are both findings.
                - Check that the testing plan can actually fail: cases that assert real behaviour,
                  that cover the spec's error paths, and that reach the pure logic directly instead
                  of through a mock.
                - Check that the plan is not larger than the problem, and that the pure and
                  effectful sides stayed separate in it.
                - Record each finding AND make the edit its action names, so the plan and this
                  record agree. A finding recorded but never applied is worse than one never
                  raised.

                Set the verdict honestly: needs-changes when an implementer would build the wrong
                thing or get stuck, needs-human-decision when a question has to go to a person.
                Wording and style preferences are not grounds to withhold build-ready.
            """),
            ("building", """
                building - the plan is approved, and this is where code is written. Work the steps
                in their order and let the plan, not improvisation, decide what gets built. The work
                of it:

                - Work test-first: write the failing test, watch it fail, write the least code that
                  passes it, watch it pass, commit. Mark a step done or a case passed only from a
                  run you actually saw.
                - Keep the pure logic pure. Decisions, derivations and transformations are functions
                  of their arguments, with no I/O, no clock, no randomness and no reaching into
                  shared mutable state, and the code that performs effects stays a thin shell that
                  calls them and applies what they return. Where a step tangles the two, split them
                  rather than reach for a mock.
                - Name things for what they mean. A longer name that carries intent beats a short
                  one that loses it, and an argument keeps its caller's name unless renaming
                  genuinely clarifies. Comments say why, not what.
                - Stay surgical. Touch only what the step needs; leave adjacent code, comments and
                  formatting exactly as found, and match the style already there even where you
                  would have chosen otherwise. Remove only the imports and helpers your own change
                  orphaned, and raise anything else you notice as a conflict or a question instead
                  of fixing it in passing.
                - Handle the realistic failure cases the plan named, and flag a limitation you are
                  knowingly leaving in rather than let it be discovered later.

                Anything the plan did not anticipate is a question, or a reopened plan, not a quiet
                improvisation. Record each commit as you make it.
            """),
            ("review", """
                review - the build is done, and this is the last stop before the human ship gate.
                This state is for verifying, not for finishing off. The work of it:

                - Re-read the spec's design section and confirm every requirement it states is
                  actually implemented, not merely planned.
                - Confirm every implementation-plan step is done and every testing-plan case passed
                  against a test that genuinely ran. A case marked passed without a run you saw is
                  the one failure this gate exists to catch.
                - Confirm nothing that worked before is broken now, and that the diff carries only
                  what the plan called for: an unrelated change here is a change nobody reviewed.
                - Confirm the pure logic stayed free of effects and the shell around it stayed free
                  of rules.
                - Review the comments added for the change. Avoid verbosity of comments and avoid
                  naming the specifics of other parts of code and instead keep comments to general
                  principles and intents. Remove uppercase words and other emphasis.

                Three things are deliberately not part of this state, so do not start them here:
                rebasing onto main happens at ship, not before; recording commits happens after ship,
                once the shas are final; and reconciling the documentation pages the brief named as
                going stale also happens at ship.

                If any of this turns up outstanding work, use requestChanges to go back to building
                rather than ship with a known gap.
            """),
        ),
    ),
    # On createPage, mint the three pinned children in the same commit; author into those.
    auto_children=(AutoChildSpec("implementation-plan"), AutoChildSpec("testing-plan"),
                   AutoChildSpec("feature-spec")),
)


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


_FEATURE_SPEC = PageType(
    tag="feature-spec",
    name="Spec",
    description=(
        "The detailed product/UX specification for a feature, authored during the brief's `spec` "
        "stage on top of the grounded base. Sealing it allows advancing the brief to planning, so "
        "it is settled before a single step or case is written. Auto-created as a child of a "
        "feature-brief."
    ),
    sections=(
        SectionSpec("overview", "Overview", (
            _prose("body", description="""
                What this spec covers and what it deliberately leaves out, in a short paragraph
                written for someone who knows the codebase but not this feature. Keep the scope to one
                subsystem: a spec spanning several independent subsystems should be split into
                separate features, each able to ship on its own.
                """),
        )),
        SectionSpec("design", "Design", (
            _blocks("body", description="""
                The design in enough detail that a plan can be written from it without making further
                decisions: the behaviour, the interfaces with their exact signatures and types, the
                data shapes, the states, and the error paths. Separate the pure logic from the code
                that performs effects and give each its own interfaces: what is a function of its
                inputs alone, and what needs I/O, storage, the clock or randomness. The rules belong
                on the pure side, and the effectful side should be thin enough to hold none of them.
                Use a heading per area and a code block for anything with a precise shape. No TBDs
                and no 'handle edge cases' placeholders, nothing that contradicts another part of the
                spec, and nothing that was not asked for. Emphasis and links are structured inline
                runs, not markdown syntax.
                """),
        )),
        SectionSpec("decisions", "Decisions", (
            _blocks("body", description="""
                One decision block per resolved question, linking the brief question it answers: the
                decision taken, the alternatives rejected, and why. This is what keeps a settled
                question from being reopened mid-build, so record the reasoning, not just the outcome.
                """),
        )),
    ),
    # Every authoring command is allowed in `draft`: sealing the spec locks ALL edits, so a
    # `sealed` spec is frozen and must be `reopen`ed to change.
    commands=(
        set_prose_cmd("overview"),
        # design blocks use a plain `text` arg (not the inline-run `inlines`), so override _BLOCK_ARGS.
        *block_cmds(
            "design",
            *add_block_cmd("design", "paragraph", add_name="addParagraph", args=(_text(),)),
            *add_block_cmd("design", "heading", add_name="addHeading",
                           args=(_integer("level"), _text())),
            *add_block_cmd("design", "code", add_name="addDesignCode"),
            remove_name="removeDesignBlock", remove_desc="remove a design block",
            reorder_name="reorderDesignBlock",
            reorder_desc="move a design block to an anchored position (precedingId guards a stale read)"),
        *block_cmds(
            "decisions",
            *add_block_cmd("decisions", "decision", add_name="addDecision",
                           args=(_text("questionId"), _text()),
                           ref_check=RefCheck(arg="questionId", scope="parent", section="questions", field="items")),
            remove_name="removeDecision", remove_desc="remove a decision",
            reorder_name="reorderDecision",
            reorder_desc="move a decision to an anchored position (precedingId guards a stale read)"),
        transition_cmd("markSealed", "draft -> sealed (locks authoring)",
                       requires=(("overview", "body"), ("design", "body"), ("decisions", "body")),
                       parent_guards=(_FEATURE_IN_SPEC_OR_LATER,)),
        transition_cmd("reopen", "sealed -> draft (unlocks authoring)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="FeatureSpec",
        initial="draft",
        states=("draft", "sealed"),
        terminal_states=("sealed",),
    ),
)


_IMPLEMENTATION_PLAN = PageType(
    tag="implementation-plan",
    name="Implementation plan",
    description="The step-by-step build plan for a feature. Auto-created as a child of a feature-brief.",
    sections=(
        SectionSpec("steps", "Steps", (
            _list("items", element_fields=("text", "status"), element_fsm=_STEP_FSM, description="""
                Each ONE action an implementer can finish in a few minutes, ordered, written for a
                skilled developer who knows nothing about this codebase or its domain. Name the exact
                files to create or modify. Work test-first: write the failing test, run it and see it
                fail, write the minimal code to pass, run it and see it pass, commit. Keep a step on
                one side of the pure/effectful line - a step that adds a rule changes pure logic, a
                step that wires it to storage, the network or the clock changes the shell around it -
                and order the pure side first, so what depends on it has something settled to call.
                Put the actual content the step needs in the step: real code, the exact command to
                run, the output to expect. Never write 'TBD', 'add error handling', 'write tests for
                the above', or 'same as step N' - repeat the detail instead, because steps are read
                out of order and in isolation. Mark a step done only once its test passes
                (element-FSM todo <-> done).
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "status"), element_fsm=_QUESTION_FSM, description="""
                Each one question about this plan that must be settled before or during the build,
                asked as a single decidable question. Prefer asking over guessing: a wrong assumption
                is cheap here and expensive once code is written. Record the answer here when it is
                settled, so an implementer sees the resolution beside the steps it affects
                (element-FSM open -> answered).
                """),
        )),
        SectionSpec("dataModels", "Data models", (
            _blocks("models", description="""
                One code block per data shape this feature introduces or changes, written as real
                declarations rather than prose: field names, types, and which are optional. Steps
                refer to these by name, so the names and types here must match the ones the steps use
                exactly - a shape called one thing here and another in a step is a bug.
                """),
        )),
    ),
    commands=(
        *list_cmds("steps", label="step", legal_in=("draft",),
                   add_args=(_text(),)),
        # Execution-status marks stay legal once the plan is `ready`: progress is recorded while
        # building against a finalized plan. Only the structural edits above are `draft`-only.
        *element_cmds("steps", legal_in=("draft", "ready"),
                      marks=(("markStepDone", "markDone", "mark a step done"),
                             ("markStepTodo", "reopen", "reopen a step"))),
        # Questions: askQuestion (special add name, no remove) + a reorder, plus an answer transition.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   legal_in=("draft",),
                   add_args=(_text(),)),
        *element_cmds("questions", legal_in=("draft",), marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        *block_cmds(
            "dataModels",
            *add_block_cmd("dataModels", "code", field="models", add_name="addDataModel", legal_in=("draft",)),
            field="models", remove_name="removeDataModel", remove_desc="remove a data-model block",
            reorder_name="reorderDataModel",
            reorder_desc="move a data-model block to an anchored position (precedingId guards a stale read)",
            legal_in=("draft",)),
        transition_cmd("markReady", "draft -> ready", requires=(("steps", "items"),),
                       parent_guards=(_FEATURE_IN_PLANNING_OR_LATER,)),
        transition_cmd("reopen", "ready -> draft (unlocks structural edits)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="ImplementationPlan",
        initial="draft",
        states=("draft", "ready"),
    ),
)


_TESTING_PLAN = PageType(
    tag="testing-plan",
    name="Testing plan",
    description="The verification cases for a feature. Auto-created as a child of a feature-brief.",
    sections=(
        SectionSpec("cases", "Cases", (
            _list("items", element_fields=("text", "status"), element_fsm=_CASE_FSM, description="""
                Each ONE concrete check that proves the feature works, written so its outcome is
                unambiguous: the setup, the action, and the expected result. Verify real behaviour
                rather than mocked behaviour, and cover the failure and edge paths the spec implies,
                not just the happy one. Check pure logic directly - inputs in, result out, no setup
                and no test doubles - and keep the heavier setup for the thin effectful shell, where
                a few cases usually cover it. Name the test that carries the case where one exists.
                A case that cannot fail proves nothing. Mark a case passed only from a run you
                actually saw, and failed rather than quietly leaving it pending (element-FSM pending
                -> passed/failed).
                """),
        )),
    ),
    commands=(
        *list_cmds("cases", label="case", legal_in=("draft",),
                   add_args=(_text(),)),
        # Execution-status marks stay legal once the plan is `ready`: test results are recorded
        # while building against a finalized plan. Only the structural edits above are `draft`-only.
        *element_cmds("cases", legal_in=("draft", "ready"),
                      marks=(("markCasePassed", "pass", "mark a case passed"),
                             ("markCaseFailed", "fail", "mark a case failed"))),
        transition_cmd("markReady", "draft -> ready", requires=(("cases", "items"),),
                       parent_guards=(_FEATURE_IN_PLANNING_OR_LATER,)),
        transition_cmd("reopen", "ready -> draft (unlocks structural edits)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="TestingPlan",
        initial="draft",
        states=("draft", "ready"),
    ),
)


_EPIC = PageType(
    tag="epic",
    name="Epic (major feature)",
    description=(
        "The root of a major feature too large for one feature-brief: it decomposes into several "
        "child feature-briefs and is built by subagents dispatched from its pinned agent plan. Use "
        "it when the work splits into parts that each ship on their own; for one feature use a "
        "feature-brief, and for a small self-contained change use a simple-change."
    ),
    sections=(
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                The intent in a sentence or two: what you want to build and why it is worth building.
                Write it before reading any code, because grounding searches the repo from this line.
                State the outcome you want, not the implementation you imagine. If the outcome can be
                stated without joining two independent things with 'and', it is probably one
                feature-brief rather than an epic.
                """),
        )),
        SectionSpec("components", "Components", (
            _list("items", element_fields=("name",), description="""
                Each one part of the system this epic touches, named as a real file, module, or
                subsystem path you CONFIRMED exists while grounding. One per element. This is the
                epic's whole surface area: a component missed here becomes a workstream nobody owns,
                and a component two workstreams both touch is a collision found only when the second
                agent's edits land on the first agent's file.
                """),
        )),
        SectionSpec("constraints", "Constraints", (
            _list("items", element_fields=("text",), description="""
                Each one project-wide requirement every workstream must respect, with its exact
                values copied verbatim: version floors, dependency limits, naming and copy rules,
                platform and performance targets. Every dispatched agent inherits these and none of
                them can see the others' work, so a constraint recorded vaguely here is one that
                each agent interprets differently and the integration review has to reconcile.
                """),
        )),
        SectionSpec("conflicts", "Conflicts", (
            _list("items", element_fields=("text",), description="""
                Each one collision with what already exists, found while grounding: prior art that
                already solves part of this, an interface this epic would break, or a competing
                in-flight change. Name the file or page it collides with and say what has to give.
                Record collisions BETWEEN the intended workstreams here too, because two agents
                editing one file is the failure this list exists to catch before either is dispatched.
                """),
        )),
        SectionSpec("documentation", "Documentation", (
            _list("items", element_fields=("text",), description="""
                Each an existing pasta doc or architecture page this epic will make stale, found
                while grounding. Name the page and the specific part of it that will need to change,
                so reconciling it when the work lands is mechanical rather than a fresh investigation.
                """),
        )),
        SectionSpec("workstreams", "Workstreams", (
            _list("items", element_fields=("name", "briefId", "scope", "dependsOn"), description="""
                Each ONE child feature-brief of this epic: its name, the page id of that brief in
                briefId, the slice of the epic it owns in scope, and the workstreams that must finish
                before it in dependsOn. CREATE the feature-brief as a child of this epic and record
                its id here. The ship gate can only check briefs that exist, so a workstream listed
                without a brief page lets an epic ship having built nothing. Split along seams where
                one agent can work without reading another's code, and keep each slice something that
                could ship on its own.
                """),
        )),
        SectionSpec("contracts", "Shared contracts", (
            _list("items", element_fields=("name", "owner", "shape"), description="""
                Each one interface that crosses a workstream boundary: its name, the workstream that
                defines it in owner, and its exact signature or data shape in shape. A dispatched
                agent sees only its own brief, so anything two workstreams must agree on is written
                here before either starts. Record the real signature rather than a description of
                one: 'returns the parsed config' is not a contract, a written-out function signature
                with its argument and return types is.
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                Each one open question that blocks or reshapes the decomposition, asked as a single
                decidable question rather than a topic. Set needsHuman when only a person can settle
                it: a product call, a trade-off with no technically correct answer, or anything
                carrying cost or policy consequences. Answer it here once decided, because a question
                still open when the dispatches begin is answered differently by every agent that
                reaches it.
                """),
        )),
        # The plan review's outcome, populated in `planReview`: the decomposition and the agent plan
        # are reviewed together, before any agent is dispatched.
        SectionSpec("review", "Plan review", (
            _scalar("verdict", choices=_VERDICTS, description="""
                The review outcome for the decomposition and the agent plan together. build-ready:
                the workstreams cover the epic with no gaps and no overlaps, and an agent could be
                dispatched against any one of them without getting stuck. needs-changes: at least one
                blocking finding must be applied before dispatching. needs-human-decision: the work
                cannot proceed until a person settles a question. Approve unless there are serious
                gaps, meaning a component no workstream owns, two workstreams owning the same file, a
                contract two workstreams need that nobody defines, or an agent mission too vague to
                act on. Minor wording preferences are never a reason to withhold build-ready.
                """),
            _list("findings", element_fields=("issue", "severity", "action"), description="""
                Each one plan-review finding: what is wrong, why it matters before any agent is
                dispatched, its severity, and the action taken to apply it. blocking means an agent
                would build the wrong thing or two agents would collide; should-fix is real but
                survivable; nit is polish. Record the finding here AND make the edit its action
                names, so the plan and this record agree. Say which workstream or agent it applies to.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        *list_cmds("components", add_args=(_text("name"),)),
        *list_cmds("constraints", add_args=(_text(),)),
        *list_cmds("conflicts", add_args=(_text(),)),
        *list_cmds("documentation", add_args=(_text(),)),
        *list_cmds("workstreams", add_args=(
            _text("name"), _text("briefId", required=False), _text("scope"),
            _text("dependsOn", required=False))),
        *list_cmds("contracts", add_args=(_text("name"), _text("owner"), _text("shape"))),
        # Questions carry the same surface as a feature-brief's: askQuestion (no remove), an answer
        # transition that also writes the answer, and an escalate that raises the needsHuman flag.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_VERDICTS,
                       legal_in=("planReview",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_SEVERITIES),
                             _text("action", required=False, choices=_EPIC_FINDING_ACTIONS,
                                   description="how the finding was applied to the plan")),
                   legal_in=("planReview",)),
        # draft -> grounding needs only the intent: grounding reads the real repo from that one line.
        transition_cmd("beginGrounding", "draft -> grounding", requires=(("summary", "body"),)),
        # grounding -> decomposition is gated on the grounding having produced a base. From here the
        # child feature-briefs and the agent plan are authored.
        transition_cmd("beginDecomposition", "grounding -> decomposition", requires=(
            ("components", "items"),
            ("constraints", "items"),
            ("conflicts", "items"),
            ("documentation", "items"),
        )),
        # decomposition -> planReview reviews the split AND the agent plan together, before any agent
        # is dispatched: the agent-plan child must be `ready` (a page-status guard, store-checked).
        transition_cmd("submitPlan", "decomposition -> planReview",
                       requires=(("workstreams", "items"), ("questions", "items")),
                       guards=(ChildStateGuard("agent-plan", "ready",
                                               "the agent plan must be marked ready"),)),
        # planReview -> executing requires a verdict to have been recorded (the review happened).
        # `build-ready` is the signal to proceed; `needs-changes` should `reviseDecomposition`
        # instead. The verdict's VALUE is a soft guide (requires only checks presence).
        transition_cmd("approvePlan", "planReview -> executing", requires=(("review", "verdict"),)),
        transition_cmd("reviseDecomposition", "planReview -> decomposition (send the plan back)"),
        # executing -> review is guarded on every dispatch having been accepted (an element-status
        # guard across the pinned agent plan, checked in the store).
        transition_cmd("submitForReview", "executing -> review", guards=(
            ChildStateGuard("agent-plan", "accepted", "every dispatch must be accepted",
                            section="dispatches", field="items"),)),
        transition_cmd("reopenDecomposition", "executing -> decomposition"),
        transition_cmd("requestChanges", "review -> executing", agency="either"),
        # `ship` is a human gate AND is guarded: every child feature-brief must itself be `shipped`
        # (a page-status guard over the epic's NON-pinned children, checked in the store).
        transition_cmd("ship", "review -> shipped (human gate)", agency="human", guards=(
            ChildStateGuard("feature-brief", "shipped",
                            "every child feature-brief must be shipped"),)),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "grounding", "decomposition", "planReview",
                                 "executing", "review")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Epic",
        initial="draft",
        states=("draft", "grounding", "decomposition", "planReview",
                "executing", "review", "shipped", "abandoned"),
        terminal_states=("shipped", "abandoned"),
    ),
    # On createPage, mint the pinned agent plan in the same commit; author into it.
    auto_children=(AutoChildSpec("agent-plan"),),
)


# An epic's pinned agent plan may only be finalized once the epic has reached `decomposition` or
# later - not while it is still in `draft` or `grounding` (the base is still being established),
# nor once `abandoned`. Attached to markReady below and enforced in the store.
_EPIC_IN_DECOMPOSITION_OR_LATER = ParentStateGuard(
    parent_type="epic",
    required_statuses=("decomposition", "planReview", "executing", "review", "shipped"),
    message="the epic must be in decomposition or later",
)


_AGENT_PLAN = PageType(
    tag="agent-plan",
    name="Agent plan",
    description=(
        "Which subagents an epic creates, the order they are dispatched in, and how their results "
        "are reported back onto the feature-briefs. Auto-created as a child of an epic."
    ),
    sections=(
        SectionSpec("agents", "Agents", (
            _list("items", element_fields=("role", "model", "mission", "reports"), description="""
                Each ONE subagent this epic creates: the role it plays, the model tier it runs on,
                the mission it is given, and what it must hand back. Write the mission for a fresh
                agent with no history, because a dispatched agent is given exactly this and never
                inherits the controller's context. Name the tier on every agent: an omitted model
                silently inherits the session's most capable and most expensive one. Use cheap for
                mechanical single-file work whose content is already written down, standard for
                multi-file integration and judgement, and capable for architecture and final review.
                Define a role once and dispatch it many times rather than writing a near-identical
                agent per workstream.
                """),
        )),
        SectionSpec("dispatches", "Dispatches", (
            _list("items",
                  element_fields=("agentId", "workstreamId", "wave", "worktree", "handoff",
                                  "outcome", "blocker", "status"),
                  element_fsm=_DISPATCH_FSM, description="""
                Each ONE run of one agent against one workstream, in the order they are sent: the
                agent element id in agentId, the parent epic's workstream element id in
                workstreamId, the parallel group in wave, the checkout it works in in worktree, and
                in handoff the facts this run needs that neither the agent definition nor the target
                brief can know. Dispatches sharing a wave may run at once; a higher wave starts only
                once every lower one is accepted. Give every dispatch in a wave a DIFFERENT
                worktree - concurrent runs in one checkout overwrite each other's edits - and record
                it here rather than on the agent, because a role is defined once and dispatched many
                times, so it is the run that occupies a checkout and not the definition. Keep
                handoff to the contracts and decisions this run actually touches, never the
                session's accumulated history, and point at large artifacts such as diffs and
                reports by file path so they stay out of the controller's context. Record what came
                back in outcome and what stopped it in blocker. A fix round is a redispatch of this
                element, not a new one, so the element stays the record of how many attempts the
                workstream took (element-FSM pending -> dispatched -> reported -> accepted).
                """),
        )),
        SectionSpec("reporting", "Reporting contract", (
            _prose("body", description="""
                How a finished agent's work lands back on its feature-brief, written as a checklist
                the controller can verify before accepting a dispatch: which of the brief's own
                commands must have been run, what status the brief and its plans must be left in,
                and where the agent's full written report lives. An agent reports by driving its own
                brief, not by handing prose back, so name the page state you expect rather than the
                summary you want to read. Accepting a dispatch without this check is how a
                workstream comes to be believed done while its brief still says otherwise.
                """),
        )),
    ),
    commands=(
        *list_cmds("agents", label="agent", legal_in=("draft",),
                   add_args=(_text("role"), _text("model", choices=_MODEL_TIERS),
                             _text("mission"), _text("reports"))),
        # `singular=` is required on both list_cmds and element_cmds here: the plural rule would
        # derive 'dispatche' from 'dispatches' and name the commands addDispatche / dispatcheId.
        # workstreamId is integrity-checked against the PARENT epic's workstreams list.
        # `worktree` is required like agentId/workstreamId/wave: a run without a named checkout is
        # the one gap that turns a same-wave parallel dispatch into two agents editing one copy.
        *list_cmds("dispatches", singular="dispatch", label="dispatch", legal_in=("draft",),
                   add_args=(_text("agentId"), _text("workstreamId"), _integer("wave"),
                             _text("worktree"), _text("handoff", required=False)),
                   ref_check=RefCheck(arg="workstreamId", scope="parent",
                                      section="workstreams", field="items")),
        # Run marks stay legal once the plan is `ready`: the record moves while the plan does not.
        # Only the structural edits above are `draft`-only.
        *element_cmds("dispatches", singular="dispatch", legal_in=("draft", "ready"), marks=(
            ("markDispatched", "dispatch", "mark a dispatch as sent to its agent"),
            ("reportDispatch", "report", "record what the agent returned", (_text("outcome"),)),
            ("acceptDispatch", "accept", "accept a reported dispatch as done"),
            ("redispatch", "redispatch", "send a reported or blocked dispatch back to an agent"),
            ("blockDispatch", "block", "record a dispatch as blocked", (_text("blocker"),)),
        )),
        set_prose_cmd("reporting", label="reporting contract", legal_in=("draft",)),
        transition_cmd("markReady", "draft -> ready",
                       requires=(("agents", "items"), ("dispatches", "items"), ("reporting", "body")),
                       parent_guards=(_EPIC_IN_DECOMPOSITION_OR_LATER,)),
        transition_cmd("reopen", "ready -> draft (unlocks structural edits)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="AgentPlan",
        initial="draft",
        states=("draft", "ready"),
    ),
)


_DOCUMENT = PageType(
    tag="document",
    name="Document",
    description=(
        "A general-purpose prose page for content that doesn't fit a typed page - notes, guides, "
        "references, narratives. The richest block-editing surface in the wiki."
    ),
    sections=(
        SectionSpec("body", "Body", (
            _blocks("body", description="""
                The document body, built from structured blocks: headings so a reader can navigate,
                paragraphs for prose, code blocks for anything with a precise shape, and tables for
                anything genuinely tabular. Lead with what the reader needs first. Emphasis and links
                are structured inline runs, not markdown syntax.
                """),
        )),
    ),
    # The full rich blocks surface - add + in-place set per kind, plus remove/reorder - in one call.
    commands=(*all_block_cmds("body"), add_link_cmd(), set_title_cmd()),
    fsm=FSMSpec(
        name="Document",
        initial="active",
        states=("active",),
    ),
)


_TOC = PageType(
    tag="toc",
    name="Table of contents",
    description=(
        "A container / landing node whose only content is the child pages placed under it. It holds "
        "no subject matter of its own - pages are filed by reparenting them beneath the toc (normal "
        "reparent rules apply), and the rendered Child pages list IS the table of contents. There are "
        "no authoring commands: a toc is shaped entirely by what lives under it, not by editing it."
    ),
    # No content sections and no authoring commands - a toc carries nothing of its own. Its single
    # purpose is to be a parent you place child pages under, so the whole page IS its Child pages list.
    # It is the one page type WITHOUT the universal addLink command: it cannot be authored at all.
    sections=(),
    commands=(),
    fsm=FSMSpec(
        name="Toc",
        initial="active",
        states=("active",),
    ),
)


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
