# Mutation engine

## Summary

**Kind:** module

The pure decision layer for page content: given a page, its page type, a command name and
arguments, it validates, decides legality, and returns a new page — performing no I/O and
mutating no input.

## Purpose

Every content change in pasta is decided here, exactly once, for every caller. It exists so that
"is this command allowed, and what does it do" is answerable without a filesystem, a lock, or a
server — which is what makes the rules testable and makes the store's job reduce to *load, call
this, save*.

It is also the only place that knows how to *apply* a command kind. `SET_SCALAR`, `ADD_ELEMENT`,
`ELEMENT_TRANSITION`, `REORDER_BLOCK` and the rest are declared as constants by the page-type
layer, but the dispatch that turns one into an edit of `page.sections` lives in `_apply`. Delete
this module and page types become inert data: the declarations would describe commands nothing
could execute.

**This component is entirely on the pure side of the line.** It takes model objects and page
types in and returns model objects out. Its one concession to the impure world is the
`id_factory` argument, passed in so tests can inject a deterministic counter.

## Usage

Three entry points, all pure functions:

- **`apply_command(page, page_type, command_name, args, id_factory, batch_context=None)`** — the
  write path. Validates arguments, checks legality, deep-copies the page, applies the command, and
  returns a `CommandResult`. Called only by `Store.mutate_page_batch` (8 `CALLS` edges run
  `store.py → commands.py`).
- **`create_page(page_type, title, parent_id, id_factory)`** — a fresh page in the FSM's initial
  status with empty sections. Called by `Store.create_page`.
- **`legal_commands(page, page_type, ignore_requirements=False)`** — the read-only legality map,
  used by `describe.describe_mutations`, by `Store.next_actions`, and by `_check_legal` here.
  `field_setter_edges` and `unmet_requirements` complete the read surface that powers `next`.

Required order inside `apply_command` is fixed and worth knowing before changing it:
`_validate_args` (shape) → `_check_legal` (legality) → `page.copy()` → `initial_sections`
backfill → `_apply` (dispatch). Validation precedes legality so an argument-shape error is
reported as such rather than as an illegal command.

`ignore_requirements=True` is a documentation-only affordance: it skips *only* the
required-content preconditions so doc generation can enumerate a status's outgoing transitions on
a content-less page. It is not reachable through the live `describeMutations` tool.

## Data model

This module owns no persistent state. It defines two transient carriers:

- **`CommandResult`** — the resulting `page`, plus `created_id` (the new element/block id for an
  `add_*` command, else `None`) and `created_ids` (every id created). The two differ only for a
  block add, which creates a whole run while `createdIds` stays one id per command.
- **`BatchContext`** — a frozen set of the ids created by earlier commands in the same batch.
  Constructed by the store per batch and threaded down to the placement guard.

`_PYTHON_TYPE` maps the declared argument type names (`string`, `integer`, `array`, …) to Python
types for `isinstance` checking.

All page state lives in `Page.sections[sectionKey][fieldKey]`, owned by component 04 and written
here through a returned copy — never in place.

## Details

Legality is the composition of four independent conditions, all in `legal_commands`:

```python
command.name: (
    _topology_ok(command, allowed)        # FSM permits it (content commands always pass)
    and _status_ok(page, command)         # legal_in status lock
    and (ignore_requirements or not unmet_requirements(page, command))
    and (not in_terminal or _is_status_transition(command)
         or _opts_into_terminal_status(page, command))
)
```

The fourth clause is the terminal-status authoring lock: once work is finished, authoring is
locked while transitions such as `reopen` stay legal, and a command that explicitly names the
terminal status in its `legal_in` can opt back in — which is how bookkeeping that outlives the
work stays writable. `legal_in=None` (the default) says nothing about the terminal status and
therefore stays locked.

`_check_legal` does not simply report "illegal". It distinguishes an unmet content precondition
(the FSM allows the event, but required fields are empty) from a wrong-status transition, so the
error names the fields to fill rather than the state to be in — and it attaches the currently
legal command names to `IllegalCommandError.legal`, so a client is told what it *can* do.

Note the deliberate split of responsibility: **cross-page checks are not here.** Ref integrity,
link validity, and the child/parent state guards are enforced by the store, because they need the
whole workspace. This module sees one page.

`field_setter_edges` is the mechanism behind pasta's self-direction, and it is derived generically
from the FSM with no per-page-type knowledge. A field's setter belongs in `do` only when
authoring that field is what advances the current stage — its `(section, field)` is a `requires`
precondition of a transition topologically legal from the current status, *and* the setter is
legal now. The `blocked_events` parameter carries a distinction that took thought:

- A **parent**-state guard failure *is* passed, so a pinned plan child whose feature brief is
  still `grounding` stays silent instead of advertising `addStep` before the base exists.
- A **child**-state guard failure is deliberately *not* passed — "my children are unfinished" does
  not make my own authoring premature.

`resolve_anchored_slot` is the shared stale-read guard for every positioned operation (element and
block inserts and reorders, and page reorder in the store). `preceding_id` must be the id
currently immediately before the target slot, which rejects a drifted index instead of silently
landing in the wrong place, and structurally forces `precedingId` to be supplied for any non-front
slot and omitted for the front. Inside a batch it skips left over ids the batch itself created,
because a caller cannot name a not-yet-committed id.

The graph splits this file across three single-file communities (`Cluster_14`, `Cluster_15`,
`Cluster_16`) and co-clusters it with `model.py` in the 114-symbol community that the labeller
calls `Tests`. Those four were merged into this component and component 04, split along the
`IMPORTS` edge.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/commands.py` | `apply_command` | function |
| `src/commands.py` | `create_page` | function |
| `src/commands.py` | `legal_commands` | function |
| `src/commands.py` | `_check_legal` | function |
| `src/commands.py` | `_validate_args` | function |
| `src/commands.py` | `_apply` | function |
| `src/commands.py` | `unmet_requirements` | function |
| `src/commands.py` | `field_setter_edges` | function |
| `src/commands.py` | `resolve_anchored_slot` | function |
| `src/commands.py` | `_opts_into_terminal_status` | function |
| `src/commands.py` | `CommandResult` | class |
| `src/commands.py` | `BatchContext` | class |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Domain model](04-domain-model.md) | depends-on | reads and copies `Page`; raises `ValidationError` / `IllegalCommandError` / `ConflictError` |
| [Page-type system](05-page-type-system.md) | depends-on | 6 `CALLS` edges to `pagetype.py` — command/field lookup, `initial_sections`, the command-kind constants, and `validate_blocks` for block arguments |
| [FSM evaluation](06-fsm-evaluation.md) | calls | 5 `CALLS` edges — `allowed_events` for topology, `fire` to compute the status a transition reaches |
| [Workspace store](02-workspace-store.md) | exposes | its only write-path caller; the store supplies `id_factory` and `BatchContext` and owns the transaction |

## Invariants

1. **`apply_command` never mutates its input page.** It works on `page.copy()`, a deep copy, and
   returns the copy. Violated, a rejected batch leaves edits on the caller's in-memory page even
   though nothing was written, so the abort stops being a true rollback.
2. **Argument validation precedes legality, and legality precedes any edit.** Fixed order in
   `apply_command`. Violated, a malformed argument can be partially applied before the command is
   found to be illegal.
3. **Every command a page type declares appears in `legal_commands`' map.** It is a comprehension
   over `page_type.commands`. Violated, `describeMutations` omits a command that `apply_command`
   would nonetheless accept, and a client cannot discover it.
4. **A command illegal in the current status cannot be applied.** `_check_legal` raises before
   `_apply` is reached. Violated, an FSM precondition becomes advisory and a page can hold content
   its status says was never authored.
5. **In a terminal status, only transitions and explicit `legal_in` opt-ins are legal.** Violated,
   finished work stays editable, and a page's terminal status stops meaning the content is settled.
6. **A positioned insert or reorder either lands exactly between the named neighbours or is
   rejected.** `resolve_anchored_slot` compares `preceding_id` against the current list. Violated,
   a stale read silently reorders content, and the caller's next read disagrees with what it
   believes it wrote.
7. **No filesystem, clock, or network access in this module.** Ids arrive via `id_factory`.
   Violated, the rules stop being unit-testable without a fixture, and the store loses its
   monopoly on effects.

## Sync

Reconciled against commit `a35b133`.
