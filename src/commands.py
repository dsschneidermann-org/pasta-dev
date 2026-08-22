"""The pure write path: create a page, apply a command, compute legality.

Every function here is pure - it takes a `Page` (plus its `PageType` and an
`id_factory`) and returns a *new* `Page`, or raises a `PastaError`. It never
performs I/O and never mutates its input in place (it copies, edits, returns) -
the in-memory "copy-edit" half of the storage pattern in `store.py`.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from . import fsm
from .errors import ConflictError, IllegalCommandError, NotFoundError, ValidationError
from .ids import IdFactory
from .model import Page
from .pagetypes import (
    ADD_BLOCK,
    ADD_ELEMENT,
    ADD_LINK,
    COMPOUND,
    ELEMENT_TRANSITION,
    REORDER_BLOCK,
    REORDER_ELEMENT,
    REMOVE_BLOCK,
    REMOVE_ELEMENT,
    SET_BLOCK,
    SET_ELEMENT_FIELD,
    SET_PROSE,
    SET_SCALAR,
    SET_TITLE,
    TRANSITION,
    CommandSpec,
    PageType,
    guard_production_type,
    initial_sections,
    validate_inline_content,
    validate_table,
)

_PYTHON_TYPE = {
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "array": list,
    "object": dict,
}

@dataclass(frozen=True)
class BatchContext:
    """Shared across a mutatePageBatch: the ids created by earlier commands in the batch. Positioned
    placement skips these when matching precedingId, since a not-yet-committed id cannot be named by
    the caller. A single (non-batch) mutation passes no context."""
    created_ids: frozenset[str]


@dataclass
class CommandResult:
    page: Page
    created_id: str | None = None   # the new element id for add_* commands, else None


def create_page(page_type: PageType, title: str, parent_id: str | None, id_factory: IdFactory) -> Page:
    """A fresh page of `page_type`, in its FSM's initial status, with empty sections."""
    # In test mode, refuse to instantiate a production page type even when handed a resolved
    # PageType directly (i.e. bypassing `get_page_type`) - the creation half of the off-limits guard.
    guard_production_type(page_type.tag)
    if not title or not title.strip():
        raise ValidationError("Page title must be a non-empty string.")
    return Page(
        id=id_factory(page_type.tag),
        type=page_type.tag,
        title=title,
        status=page_type.fsm.initial,
        parent_id=parent_id,
        child_ids=[],
        sections=initial_sections(page_type),
    )


def _is_populated(value: Any) -> bool:
    """Whether a field value counts as "set" for a required-content precondition.

    Prose must be non-blank, a list must be non-empty, a scalar must be non-null.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return True


def unmet_requirements(page: Page, command: CommandSpec) -> list[tuple[str, str]]:
    """The (section, field) preconditions of `command` that `page` does not yet satisfy."""
    unmet: list[tuple[str, str]] = []
    for section_key, field_key in command.requires:
        value = page.sections.get(section_key, {}).get(field_key)
        if not _is_populated(value):
            unmet.append((section_key, field_key))
    return unmet


def _is_status_transition(command: CommandSpec) -> bool:
    """Whether `command` fires a PAGE status transition (a TRANSITION/COMPOUND carrying an event).

    Everything else - set/add/remove/reorder, and an `element_transition` (which fires an element's
    own FSM, not the page's) - is an AUTHORING command from the page's point of view.
    """
    return command.kind in (TRANSITION, COMPOUND) and command.event is not None


def is_field_setter(command: CommandSpec) -> bool:
    """Whether `command` writes typed FIELD content into a (section, field): a SET_SCALAR, SET_PROSE,
    or ADD_ELEMENT (the add of a LIST field - including the element-FSM adds addStep/addCase/askQuestion).

    The shared, page-type-agnostic classifier behind the self-direction `do` list: a field setter gets
    its own entry carrying its field's instruction, while a blocks field is grouped into one entry per
    field. Deliberately kind-based, no per-type knowledge.
    NOT field setters: ADD_BLOCK / SET_BLOCK (freeform blocks - grouped in `do`, never exploded),
    REMOVE_* / REORDER_* (structure, not content), SET_ELEMENT_FIELD (a flag on an existing element),
    ELEMENT_TRANSITION (fires an element's own FSM), TRANSITION / COMPOUND (page-status edges), and the
    universal ADD_LINK / SET_TITLE.
    """
    return command.kind in (SET_SCALAR, SET_PROSE, ADD_ELEMENT)


def _topology_ok(command: CommandSpec, allowed_events: set[str]) -> bool:
    """Whether the FSM permits `command` from the current status (topology only)."""
    if _is_status_transition(command):
        return command.event in allowed_events
    return True


def _status_ok(page: Page, command: CommandSpec) -> bool:
    """Whether a content command is allowed in the page's current status (the plan `ready` lock)."""
    return command.legal_in is None or page.status in command.legal_in


def _opts_into_terminal_status(page: Page, command: CommandSpec) -> bool:
    """Whether `command` names the page's (terminal) status in an explicit `legal_in`, overriding the
    terminal-state authoring lock - how bookkeeping that outlives the work stays writable.

    Always explicit: `legal_in=None` (the default) says nothing about the terminal state and stays
    locked, as does a `legal_in` that omits it.
    """
    return command.legal_in is not None and page.status in command.legal_in


def legal_commands(page: Page, page_type: PageType, ignore_requirements: bool = False) -> dict[str, bool]:
    """Map each command name to whether it is legal for `page` right now.

    A command is legal when: the FSM permits it from the current status (content commands
    always pass this) AND, for a content command, its status is allowed by `legal_in`
    (the plan "ready" lock) AND every required-content precondition it declares is satisfied
    AND, in a terminal status (`fsm.terminal_states`), the command is either a status transition or
    one that names that status in its `legal_in` (see `_opts_into_terminal_status`) - authoring is
    locked once the work is finished, while any remaining transitions (e.g. `reopen`) stay legal.
    Cross-page checks (ref integrity, the `ship` guard) are enforced in the store, not here.

    `ignore_requirements=True` skips *only* the required-content preconditions, so a transition
    gated on unfilled required content still reports legal on the FSM topology alone. Used by doc
    generation to enumerate a state's outgoing transitions on a content-less page; FSM topology, the
    `legal_in` status-lock, and the terminal-state authoring lock are unaffected. Not exposed through
    the live describeMutations tool.
    """
    allowed = fsm.allowed_events(page_type.fsm, page.status)
    in_terminal = page.status in page_type.fsm.terminal_states
    return {
        command.name: (
            _topology_ok(command, allowed)
            and _status_ok(page, command)
            and (ignore_requirements or not unmet_requirements(page, command))
            # Terminal state: lock authoring, leave transitions (e.g. reopen) legal, and let a
            # command naming this state in `legal_in` opt back in.
            and (not in_terminal or _is_status_transition(command)
                 or _opts_into_terminal_status(page, command))
        )
        for command in page_type.commands
    }


def _field_setter_edge(page: Page, page_type: PageType, section: str, field: str,
                       command_names: list[str]) -> dict[str, Any]:
    """One self-instructing `do` FIELD edge: kind='field' with the (section, field), the field's
    instruction (its FieldSpec.description) and the `commands` that write it, all inline - so a `next`
    consumer needs no describePageType round-trip to know what to author."""
    field_spec = page_type.field_spec(section, field)
    return {
        "pageId": page.id, "pageType": page.type, "kind": "field",
        "section": section, "field": field,
        "instruction": field_spec.description.strip() if field_spec is not None else "",
        "commands": command_names,
    }


def field_setter_edges(page: Page, page_type: PageType,
                       blocked_events: Collection[str] = ()) -> list[dict[str, Any]]:
    """The stage-relevant field-setter `do` edges for `page` in its current status (pure).

    A field's setter belongs in `do` only when authoring that field is what advances the current
    stage: its (section, field) is a required precondition (`requires`) of a transition TOPOLOGICALLY
    legal from the current status, AND the setter is legal right now. Derived generically from the
    FSM - no per-page-type knowledge - so a status-scoped setter surfaces only where its field is a
    stage requirement, and the `legal_in=None` 'always legal' setters no longer add noise in states
    where their field is not the goal (e.g. setSummary while building).

    `blocked_events` names events the CALLER has determined cannot fire for a reason that no
    authoring on this page can clear - it is dropped from the topology before requirements are
    collected, so a transition waiting on the outside world does not advertise its content as this
    page's work yet. The store passes the page's parent-state-guard failures here: a pinned plan
    child whose feature-brief is still `grounding` therefore stays silent instead of emitting
    addStep/addCase while the base is still being established. A CHILD-state guard is deliberately
    NOT passed - 'my children are unfinished' does not make my own authoring premature (a brief in
    `planning` must still surface askQuestion while its plan children are unready).

    Two entry shapes, both carrying a `commands` array and `kind='field'` (see `_field_setter_edge`):
      - a scalar/prose/list FIELD SETTER -> one entry, commands=[the setter];
      - a BLOCKS field                   -> ONE grouped entry, commands=[its add-block variants]
        (SET_BLOCK edit-in-place, remove, and reorder are never surfaced here - describeMutations only).
    """
    allowed = fsm.allowed_events(page_type.fsm, page.status) - set(blocked_events)
    required = {
        section_field
        for command in page_type.commands
        if _is_status_transition(command) and command.event in allowed
        for section_field in command.requires
    }
    if not required:
        return []
    legal = legal_commands(page, page_type)
    edges: list[dict[str, Any]] = []
    block_variants: dict[tuple[str, str], list[str]] = {}
    for command in page_type.commands:
        section, field = command.section, command.field
        if section is None or field is None:      # transitions / addLink / setTitle target no field
            continue
        target = (section, field)
        if target not in required or not legal.get(command.name):
            continue
        if is_field_setter(command):
            edges.append(_field_setter_edge(page, page_type, section, field, [command.name]))
        elif command.kind == ADD_BLOCK and command.element_field is None:
            # An element-scoped add cannot run until the element exists, so it is authored from
            # describeMutations, never advertised as this stage's work.
            block_variants.setdefault(target, []).append(command.name)
    for (section, field), variants in block_variants.items():
        edges.append(_field_setter_edge(page, page_type, section, field, variants))
    return edges


def transition_guidance(
    page_type: PageType, batch: list[dict[str, Any]], status: str
) -> str | None:
    """The stage guidance for the state a committed `batch` left the page in (pure).

    The coarser sibling of `field_setter_edges`: that says which field to author next, this says
    what the stage just entered is for. None unless the batch moved the status - which it did
    exactly when it held a page-status transition, so the store never has to report it. `status`
    is the status after the batch, so several transitions yield only the final state's text.
    """
    for entry in batch:
        command = page_type.command(entry.get("command") or "")
        if command is not None and _is_status_transition(command):
            return page_type.fsm.guidance_for(status)
    return None


def apply_command(
    page: Page,
    page_type: PageType,
    command_name: str,
    args: dict[str, Any] | None,
    id_factory: IdFactory,
    batch_context: BatchContext | None = None,
) -> CommandResult:
    """Validate and apply one command, returning the resulting page (a fresh copy)."""
    args = args or {}
    command = page_type.command(command_name)
    if command is None:
        raise ValidationError(
            f"Unknown command '{command_name}' for page type '{page_type.tag}'. " +
            f"Known commands: {', '.join(c.name for c in page_type.commands)}."
        )
    _validate_args(command, args)
    _check_legal(page, page_type, command)

    working = page.copy()
    created_id = _apply(working, page_type, command, args, id_factory, batch_context)
    return CommandResult(page=working, created_id=created_id)


# --- validation --------------------------------------------------------------
def _validate_args(command: CommandSpec, args: dict[str, Any]) -> None:
    known = {arg.name for arg in command.args}
    for key in args:
        if key not in known:
            raise ValidationError(f"Unknown argument '{key}' for command '{command.name}'.")
    for arg in command.args:
        present = arg.name in args and args[arg.name] is not None
        if arg.required and not present:
            raise ValidationError(f"Command '{command.name}' requires argument '{arg.name}'.")
        if not present:
            continue
        value = args[arg.name]
        expected = _PYTHON_TYPE.get(arg.type, str)
        # bool is a subclass of int - guard against int slipping through as bool and vice versa
        if arg.type == "integer" and isinstance(value, bool):
            raise ValidationError(f"Argument '{arg.name}' must be an integer, got a boolean.")
        if not isinstance(value, expected):
            raise ValidationError(
                f"Argument '{arg.name}' must be of type '{arg.type}', got {type(value).__name__}."
            )
        if arg.choices is not None and value not in arg.choices:
            raise ValidationError(
                f"Argument '{arg.name}' must be one of {list(arg.choices)}, got {value!r}."
            )
        # Structurally validate an inline-run array arg against its declared shape.
        if arg.content is not None:
            validate_inline_content(arg.content, value)
    # A table's rows (and align, if given) must match the header width - a cross-arg check.
    if command.block_kind == "table":
        validate_table(args.get("header", []), args.get("rows", []), args.get("align"))


def _check_legal(page: Page, page_type: PageType, command: CommandSpec) -> None:
    legal = legal_commands(page, page_type)
    if legal.get(command.name, False):
        return
    legal_now = sorted(name for name, ok in legal.items() if ok)
    # Distinguish an unmet content precondition (the FSM allows the event, but required
    # fields are still empty) from a wrong-status transition, so the message names what to fix.
    allowed = fsm.allowed_events(page_type.fsm, page.status)
    unmet = unmet_requirements(page, command)
    if _topology_ok(command, allowed) and unmet:
        missing = ", ".join(f"{section}.{field}" for section, field in unmet)
        raise IllegalCommandError(
            f"Command '{command.name}' is blocked until these fields are set: {missing}.",
            legal=legal_now,
        )
    raise IllegalCommandError(
        f"Command '{command.name}' is not legal for a '{page.type}' page in status " +
        f"'{page.status}'. Legal commands now: {', '.join(legal_now) or '(none)'}.",
        legal=legal_now,
    )


# --- application (dispatch by command kind) ----------------------------------
def _apply(
    page: Page,
    page_type: PageType,
    command: CommandSpec,
    args: dict[str, Any],
    id_factory: IdFactory,
    batch_context: BatchContext | None = None,
) -> str | None:
    if command.kind == SET_SCALAR:
        page.sections[command.section][command.field] = args[command.args[0].name]
        return None
    if command.kind == SET_PROSE:
        page.sections[command.section][command.field] = args[command.args[0].name]
        return None
    if command.kind == ADD_ELEMENT:
        return _add_element(page, page_type, command, args, id_factory, batch_context)
    if command.kind == SET_ELEMENT_FIELD:
        _set_element_field(page, command, args)
        return None
    if command.kind == ELEMENT_TRANSITION:
        _element_transition(page, page_type, command, args)
        return None
    if command.kind in (REORDER_ELEMENT, REORDER_BLOCK):
        _reorder_entry(page, command, args, batch_context)
        return None
    if command.kind in (REMOVE_ELEMENT, REMOVE_BLOCK):
        _remove_by_id(page, command, args)
        return None
    if command.kind == ADD_LINK:
        # Append a typed outgoing edge to Page.links. The cross-page rules (target exists, source
        # non-archived, no self-link, no duplicate edge) are enforced in the store's _check_link
        # precheck before this runs - the pure core, like inline-ref handling, trusts that check.
        page.links.append({"to": args["toId"], "role": args["role"].strip()})
        return None
    if command.kind == SET_TITLE:
        # Rename the page in place - the page-command alias for the top-level renamePage tool. Reject a
        # blank title with the SAME message as store.rename_page / create_page (a title is a display
        # label, never an identifier, so no uniqueness or cross-page check applies).
        title = args["title"]
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("Page title must be a non-empty string.")
        page.title = title
        return None
    if command.kind == ADD_BLOCK:
        return _add_block(page, command, args, id_factory, batch_context)
    if command.kind == SET_BLOCK:
        _set_block(page, command, args)
        return None
    if command.kind == TRANSITION:
        page.status = fsm.fire(page_type.fsm, page.status, command.event)
        return None
    if command.kind == COMPOUND:
        created_id: str | None = None
        for step in command.steps:
            step_created = _apply(page, page_type, step, args, id_factory, batch_context)
            if step_created is not None:
                created_id = step_created
        return created_id
    raise ValidationError(f"Unsupported command kind '{command.kind}'.")


def _add_element(page: Page, page_type: PageType, command: CommandSpec,
                 args: dict[str, Any], id_factory: IdFactory,
                 batch_context: BatchContext | None = None) -> str:
    element: dict[str, Any] = {"id": id_factory("")}
    for element_field, arg_name in command.element_map:
        element[element_field] = args.get(arg_name)   # optional args default to None
    # If the list has an element-FSM, the new element starts at that FSM's initial status.
    field_spec = page_type.field_spec(command.section, command.field)
    if field_spec is not None:
        if field_spec.element_fsm is not None:
            element["status"] = field_spec.element_fsm.initial
        # A declared block field starts as an empty array, so the element carries its shape.
        for block_field in field_spec.block_element_fields():
            element[block_field] = []
    _place_entry(page.sections[command.section][command.field], element, command, args, batch_context)
    return element["id"]


def _apply_element_writes(element: dict[str, Any], command: CommandSpec, args: dict[str, Any]) -> None:
    """Set an element's mapped-arg fields and any literal `element_const` fields in place."""
    for element_field, arg_name in command.element_map:
        if arg_name in args:
            element[element_field] = args[arg_name]
    for element_field, value in command.element_const:
        element[element_field] = value


def _find_entry(entries: list[dict[str, Any]], target_id: str, context: str) -> dict[str, Any]:
    """The block with `target_id` in `entries`; `context` names the list for the error message."""
    for entry in entries:
        if entry.get("id") == target_id:
            return entry
    raise NotFoundError(f"No entry with id '{target_id}' in {context}.")


def _find_element_by_id(entries: list[dict[str, Any]], target_id: str, context: str) -> dict[str, Any]:
    """The list element with `target_id` in `entries`. The same scan as `_find_entry` under the
    wording elements have always used, so an author can tell which of the two ids was wrong."""
    for element in entries:
        if element.get("id") == target_id:
            return element
    raise NotFoundError(f"No element with id '{target_id}' in {context}.")


def _entry_context(command: CommandSpec, args: dict[str, Any]) -> str:
    """The list a command addresses, named for an error message: `steps.items`, or
    `steps.items[<elementId>].detail` when the command is element-scoped."""
    base = f"{command.section}.{command.field}"
    if command.element_field is None:
        return base
    return f"{base}[{args[command.args[0].name]}].{command.element_field}"


def _target_entries(page: Page, command: CommandSpec, args: dict[str, Any]) -> list[dict[str, Any]]:
    """The entry list a list/blocks command operates on: the section's own field, or - when the
    command is element-scoped - the block array on the element named by args[0].

    The array is created when the element does not carry it yet, which is what lets an element
    stored before the field was declared accept its first block.
    """
    entries: list[dict[str, Any]] = page.sections[command.section][command.field]
    if command.element_field is None:
        return entries
    element = _find_element_by_id(entries, args[command.args[0].name],
                                  f"{command.section}.{command.field}")
    blocks = element.get(command.element_field)
    if not isinstance(blocks, list):
        blocks = []
        element[command.element_field] = blocks
    return blocks


def _entry_id(command: CommandSpec, args: dict[str, Any]) -> str:
    """The id of the entry a command targets. args[0] is the id by convention; an element-scoped
    block command spends args[0] on the element that holds the field, so its entry id is args[1]."""
    return args[command.args[1 if command.element_field is not None else 0].name]


def _find_element(page: Page, command: CommandSpec, args: dict[str, Any]) -> dict[str, Any]:
    return _find_element_by_id(page.sections[command.section][command.field],
                               args[command.args[0].name],   # args[0] is the id by convention
                               f"{command.section}.{command.field}")


def _set_element_field(page: Page, command: CommandSpec, args: dict[str, Any]) -> None:
    """Set fields on an existing list element (args[0] identifies it by id), id preserved."""
    _apply_element_writes(_find_element(page, command, args), command, args)


def _element_transition(page: Page, page_type: PageType, command: CommandSpec, args: dict[str, Any]) -> None:
    """Fire the element's own FSM event (e.g. a step todo->done), then apply any field writes."""
    field_spec = page_type.field_spec(command.section, command.field)
    if field_spec is None or field_spec.element_fsm is None:
        raise ValidationError(f"{command.section}.{command.field} has no element FSM to drive.")
    element = _find_element(page, command, args)
    current = element.get("status", field_spec.element_fsm.initial)
    element["status"] = fsm.fire(field_spec.element_fsm, current, command.event)   # rejects illegal marks
    _apply_element_writes(element, command, args)


def resolve_anchored_slot(ids: list[str], index: int, preceding_id: str | None, context: str,
                          batch_context: BatchContext | None = None) -> int:
    """The validated insert/move slot for an anchored, stale-read-safe operation - the shared guard.

    `ids` is the ordered list the entry will occupy (for a move: with the moving entry already
    removed). The slot is `index`, and `preceding_id` must be the id currently immediately before it
    (None iff `index` is 0). One check makes the operation safe under a stale read - a drifted index
    or a predecessor that is no longer there is rejected instead of silently landing in the wrong
    place. Because the expected predecessor is derived from the current list, it also enforces that
    `preceding_id` is supplied for any non-front slot (a null can only match `index` 0) and omitted
    for the front. `context` names the list for the error message (e.g. `steps.items`, or the
    children of a page). Shared by block/element reorder + positioned insert (via `_resolve_slot`)
    and page reorder (store.reorder_page).
    """
    if not 0 <= index <= len(ids):
        raise ValidationError(f"index {index} is out of range [0, {len(ids)}] for {context}.")
    # Opaque-id placement: skip left over ids the batch created earlier (the caller cannot name a
    # not-yet-committed id), so precedingId anchors on the first COMMITTED id. No batch => strict.
    created_ids: frozenset[str] = batch_context.created_ids if batch_context is not None else frozenset()
    j = index - 1
    while j >= 0 and ids[j] in created_ids:
        j -= 1
    expected = None if j < 0 else ids[j]
    if preceding_id != expected:
        raise ConflictError(
            f"Stale read: expected the entry before position {index} in {context} to be " +
            f"{expected!r}, but precedingId={preceding_id!r}. Re-read and retry."
        )
    return index


def _resolve_slot(entries: list[dict[str, Any]], index: int, preceding_id: str | None,
                  context: str, batch_context: BatchContext | None = None) -> int:
    """The anchored slot for a positioned add or a block/element reorder (see resolve_anchored_slot).

    `entries` is the list[dict] the item will occupy - for a reorder, with the moving item already
    removed - and `context` names that list, so an element-scoped block reports the element it
    happened in. Delegates to the shared id-list guard on the entries' ids.
    """
    return resolve_anchored_slot([entry["id"] for entry in entries], index, preceding_id,
                                 context, batch_context)


def _place_entry(entries: list[dict[str, Any]], entry: dict[str, Any],
                 command: CommandSpec, args: dict[str, Any],
                 batch_context: BatchContext | None = None) -> None:
    """Append `entry`, or insert it at a guarded position when the command was given an `index`.

    `index` / `precedingId` are positional args (never in `element_map`), so they never leak into
    the entry body. Omit `index` -> append (and `precedingId` must be omitted too); give `index` ->
    the shared anchor guard runs against the current list before inserting.
    """
    index = args.get("index")
    preceding_id = args.get("precedingId")
    if index is None:
        if preceding_id is not None:
            raise ValidationError(
                f"Command '{command.name}': precedingId requires an index - it anchors a positioned insert."
            )
        entries.append(entry)
        return
    slot = _resolve_slot(entries, index, preceding_id, _entry_context(command, args), batch_context)
    entries.insert(slot, entry)


def _reorder_entry(page: Page, command: CommandSpec, args: dict[str, Any],
                   batch_context: BatchContext | None = None) -> None:
    """Move one element/block to an anchored position within its list/blocks field.

    Backs both reorder_element and reorder_block (one implementation, two kinds - as remove_element /
    remove_block already are). Names only the moved id (args[0]), its destination `toIndex`, and the
    `precedingId` that must sit just before it - so a concurrent edit elsewhere can neither drop an id
    (the old whole-list reorder's failure) nor let the item land in a stale slot (the old index-only
    move's failure). `toIndex` is the resting index in the list *after* the item is removed.
    """
    target_id = _entry_id(command, args)
    to_index = args["toIndex"]
    preceding_id = args.get("precedingId")
    context = _entry_context(command, args)
    entries = _target_entries(page, command, args)
    for index, entry in enumerate(entries):
        if entry.get("id") == target_id:
            moving = entries.pop(index)
            slot = _resolve_slot(entries, to_index, preceding_id, context, batch_context)
            entries.insert(slot, moving)
            return
    raise NotFoundError(f"No entry with id '{target_id}' in {context}.")


def _add_block(page: Page, command: CommandSpec, args: dict[str, Any], id_factory: IdFactory,
               batch_context: BatchContext | None = None) -> str:
    """Add a typed block to a blocks field - the section's own, or an element's when the command is
    element-scoped; append, or insert at a guarded `index` (see _place_entry)."""
    block: dict[str, Any] = {"id": id_factory(""), "kind": command.block_kind}
    for block_field, arg_name in command.element_map:
        block[block_field] = args.get(arg_name)
    _place_entry(_target_entries(page, command, args), block, command, args, batch_context)
    return block["id"]


def _set_block(page: Page, command: CommandSpec, args: dict[str, Any]) -> None:
    """Replace a block's fields in place by id, preserving its id and kind.

    Rejects if the target block is a different kind (e.g. `setParagraph` on a heading), matching
    the reference behaviour. The mapped fields are fully replaced (an omitted optional -> None).
    """
    block = _find_entry(_target_entries(page, command, args), _entry_id(command, args),
                        _entry_context(command, args))
    if block.get("kind") != command.block_kind:
        raise ValidationError(
            f"Command '{command.name}' edits a '{command.block_kind}' block, but block " +
            f"'{block.get('id')}' is a '{block.get('kind')}'."
        )
    for block_field, arg_name in command.element_map:
        block[block_field] = args.get(arg_name)


def _remove_by_id(page: Page, command: CommandSpec, args: dict[str, Any]) -> None:
    """Remove an id'd entry (list element or block) from a list/blocks field."""
    target_id = _entry_id(command, args)
    context = _entry_context(command, args)
    entries = _target_entries(page, command, args)
    for index, entry in enumerate(entries):
        if entry.get("id") == target_id:
            del entries[index]
            return
    raise NotFoundError(f"No entry with id '{target_id}' in {context}.")
