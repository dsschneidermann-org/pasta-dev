# Page-type system

## Summary

**Kind:** subsystem

The declarative vocabulary pasta's page types are written in, the twelve registered production
declarations themselves, and the load-time validator that proves each one is well-formed.

## Purpose

This is the component that makes pasta extensible without being programmable. A page type declares
*as data* what a page of that type is made of — its sections and fields, the commands that author
them, its status FSM, its pinned children, its workspace-configurable guidance — and every other
component reads those declarations generically. Adding a page type means writing one module; it
requires no change to the store, the mutation engine, either renderer, or the transport.

It exists to hold three things that would otherwise scatter:

1. **The vocabulary** (`core/specs.py`, `core/args.py`, `core/fields.py`, `core/commands.py`) — the
   kind constants and the frozen spec dataclasses, plus the helper factories a declaration is
   actually written with, so a page type reads as a declaration rather than as construction code.
2. **The setup a declaration needs before anything reads it** (`core/pagetype.py`) — resolving
   block vocabularies, deriving the FSM transition table, building the state machines.
3. **The proof that a declaration is usable** (`core/validation.py`) — one aggregated failure at
   load, rather than a surprise mid-request.

Delete it and pasta has no notion of a document *kind*: pages become untyped bags of fields, the
FSM-driven authoring loop has nothing to derive next steps from, and `describePageType` has
nothing to describe.

**The pure/effectful line:** this whole subsystem is pure. It performs no I/O and reads no clock.
The one piece of process-global mutable state is the registry map itself, and the one mutator is
the test-mode switch.

## Usage

**Consumers** read the registry through `pagetypes/_registry.py`, never by importing a
declaration module:

- `registered_pagetypes()` — the types that exist *right now* (7 callers). The one map every
  consumer reads, so what resolves is exactly what is advertised.
- `get_page_type(tag)` — resolve one, or `None` (16 callers — the busiest symbol in the
  subsystem).
- `validate_registry()` — called once at load by `src/server.py`, and again on every HMR reload.
- `is_auto_child_type`, `workspace_guidance_fields`, `is_test_mode`, `guard_production_type`.

Then, per page type: `get_pagetype_command(page_type, name)`,
`get_pagetype_field(page_type, section, field)`, `initial_sections(page_type)`, and
`element_fsm_sites(page_type)` for every list field carrying an element FSM.

**Authors** of a page type write a module beside the others in `src/pagetypes/` and add one
line to `REGISTRY`. The declaration is assembled from the factory helpers rather than from raw
specs: field helpers `_scalar` / `_prose` / `_list` / `_blocks`, command factories
`set_prose_cmd`, `set_scalar_cmd`, `list_cmds`, `element_cmds`, `blocks_cmds`,
`element_blocks_cmds`, `transition_cmd`, `transition_on_add_cmd`, plus the universal
`add_link_cmd()` and `set_title_cmd()`. Twelve types are registered: `architecture`,
`decision-record`, `bug-report`, `simple-change`, the feature brief/spec pair, implementation and
testing plans, `epic`, `agent-plan`, `document`, and `toc`.

Required order is enforced by construction, not convention: `PageType.__post_init__` runs the
setup, and `validate_page_types` must pass before the registry serves a request.

## Data model

The declarations are frozen dataclasses, so a page type is a value:

- **`PageType`** — `tag`, `name`, `description`, `sections`, `commands`, `fsm`, `auto_children`,
  `workspace_guidance`.
- **`SectionSpec`** → **`FieldSpec`** — `key`, `kind` (`SCALAR` | `PROSE` | `LIST` | `BLOCKS`),
  `choices` for a scalar enum, `element_fields` and `element_fsm` for a list, `block_kinds` and
  `element_blocks` for block content.
- **`CommandSpec`** — the command's name, kind, target section/field, `legal_in`, `requires`,
  `agency`, `event`/`dest`, and its `ArgSpec` tuple.
- **`FSMSpec`** — `name`, `initial`, `states`, `terminal_states`, `status_guidance`, and a
  `transitions` table that is **derived, not authored**.
- **`ElementFSMSpec`** — a list element's own tiny lifecycle, which *does* keep its own
  transition table, plus `checkmark_done` for checkbox rendering.
- **Cross-page preconditions:** `RefCheck`, `ChildStateGuard`, `ParentStateGuard` — declared here,
  **evaluated in the store**, which is the only component that can see other pages.
- **`AutoChildSpec`** — a pinned, protected child created in the same commit as its parent.
- **`WorkspaceGuidanceSpec`** — `field`, `guidance_for`, `description`.

**Nothing here is persisted.** Every spec is built at import time and lives for the process. Two
fields are filled in *after* construction and excluded from identity (`compare=False`):
`FSMSpec.machine` / `ElementFSMSpec.machine` hold the built `StateMachine` subclass, and
`machine_error` holds the definition error that stopped it — never both.

The single piece of mutable module state is `REGISTRY: dict[str, PageType]`, plus
`_stashed_registry` and the `_test_mode` flag behind the test-mode switch.

## Details

**A status edge lives in exactly one place.** `FSMSpec` stores only the status set and the initial
status; the transition table is derived by `_status_transitions(page_type)` from the page type's
own transition and compound commands, each of which declares its source statuses via `legal_in`
and its destination via `dest`. So `legal_in` is the uniform "where is this command legal"
declaration across every command kind, and a transition cannot disagree with the command that
fires it. Element FSMs are the deliberate exception: an `element_transition` command names only
the event it fires, so the element table has nothing to derive from and is the source of truth.

**`terminal_states` is declared, never inferred.** A status lacking outgoing transitions is *not*
automatically authoring-locked — only a status named in `terminal_states` is. (Note this is a
different question from the `final=True` inference in the FSM builder, which is about
python-statemachine's trap-state validation; see component 06.)

**Setup happens with the declaration, in `__post_init__`:**

```python
def __post_init__(self):
    self._resolve_block_vocabularies()
    object.__setattr__(self.fsm, "transitions", _status_transitions(self))
    self._build_machines()
```

`_resolve_block_vocabularies` fills each block-carrying argument's accepted kinds in from the
field it targets — this is the first point in the program that holds both the command's stated
target and the field's declared vocabulary. It is best-effort by design: an argument whose target
does not resolve keeps `block_kinds=None`, the "not a block argument" sentinel, and
`validate_pagetype_block_args` reports it. That is safe *only* because the primary flows validate
before serving.

`_build_machines` then builds the status machine and every element machine the type declares.
Building is each spec's own well-formedness check, so it runs at declaration time and a failure is
*held* (`machine_error`) rather than raised out of class creation — which is what lets the
validator report every problem at once. An element spec declared by several page types carries one
machine either way: a spec already built is left alone.

**Validation is one pass, one exception.** `validate_page_types(registry)` walks every type —
every section's every field (`validate_field_spec`), the FSM (`validate_fsm_spec`), the machines
already built (`validate_page_machine`), the field-setter rules, the setter descriptions, the
block arguments — then the cross-registry workspace-guidance rules, and raises a single
`ValueError` listing everything found. `validate_page_machine` re-derives nothing; it reads the
`machine_error` the build left, and rewrites the library's `state_<value>` attribute names back
into the names the author declared (longest state first, so one state name cannot be substituted
inside another).

**Test mode swaps the whole registry.** `set_test_mode(True)` *empties* `REGISTRY` into a private
stash and puts the hand-authored `test-*` fixtures (`src/testtypes.py`) in its place — mutating
the map in place, never rebinding, so a reference taken before the switch stays live. Production
types become unreachable through the map itself rather than merely behind the accessors, and
`guard_production_type` raises `ProductionTypeInTestError` at both resolution
(`get_page_type`) and creation (`commands.create_page`) — so even a caller holding a resolved
`PageType` cannot instantiate one. `tests/conftest.py` flips it on at import, ahead of
collection. The fixtures are capability demonstrations (`test-fields`, `test-blocks`,
`test-element-blocks`, `test-flow`, `test-lifecycle`, …), never clones of production types.

**Guidance text lives in its own modules** — `_stage_guidance.py` (per-status stage instructions,
so one working discipline can reach several page types and be read as prose) and
`_workspace_guidance.py` (field descriptions, which must match across types that share a field).
The leading underscores sort them above the page-type modules that draw on them.

On the graph: `pagetype.py` and `fsm.py` share `Cluster_33` (cohesion 83%), which is the
machine-building coupling showing up as community structure; `core/commands.py` and `core/args.py`
share a 28-symbol community (18 `CALLS` edges between them); `core/fields.py` and `core/args.py` a
20-symbol one. `_registry.py` holds the only community the labeller actually named `Pagetypes`.
Every declaration module calls into `core/commands.py` (7–11 edges each), and into nothing else of
substance — the declarations really are leaves.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/pagetypes/core/pagetype.py` | `PageType` | class |
| `src/pagetypes/core/pagetype.py` | `PageType._build_machines` | function |
| `src/pagetypes/core/pagetype.py` | `PageType._resolve_block_vocabularies` | function |
| `src/pagetypes/core/pagetype.py` | `_status_transitions` | function |
| `src/pagetypes/core/pagetype.py` | `initial_sections` | function |
| `src/pagetypes/core/pagetype.py` | `element_fsm_sites` | function |
| `src/pagetypes/core/specs.py` | `FSMSpec` | class |
| `src/pagetypes/core/specs.py` | `ElementFSMSpec` | class |
| `src/pagetypes/core/specs.py` | `ChildStateGuard` | class |
| `src/pagetypes/core/specs.py` | `ParentStateGuard` | class |
| `src/pagetypes/core/specs.py` | `AutoChildSpec` | class |
| `src/pagetypes/core/specs.py` | `RefCheck` | class |
| `src/pagetypes/core/fields.py` | `FieldSpec` | class |
| `src/pagetypes/core/commands.py` | `CommandSpec` | class |
| `src/pagetypes/core/commands.py` | `list_cmds` | function |
| `src/pagetypes/core/commands.py` | `transition_cmd` | function |
| `src/pagetypes/core/args.py` | `ArgSpec` | class |
| `src/pagetypes/core/args.py` | `standard_blocks` | function |
| `src/pagetypes/core/validation.py` | `validate_page_types` | function |
| `src/pagetypes/core/validation.py` | `validate_page_machine` | function |
| `src/pagetypes/core/validation.py` | `validate_blocks` | function |
| `src/pagetypes/_registry.py` | `REGISTRY` | constant |
| `src/pagetypes/_registry.py` | `registered_pagetypes` | function |
| `src/pagetypes/_registry.py` | `get_page_type` | function |
| `src/pagetypes/_registry.py` | `set_test_mode` | function |
| `src/pagetypes/_registry.py` | `guard_production_type` | function |
| `src/pagetypes/architecture.py` | *(a worked declaration)* | file |
| `src/testtypes.py` | `TEST_REGISTRY` | constant |

## Dependencies

| Target | Role | Note |
|---|---|---|
| [Domain model](04-domain-model.md) | depends-on | raises `ValidationError`; `ProductionTypeInTestError` for the test-mode guard |
| [FSM evaluation](06-fsm-evaluation.md) | calls | `try_build_machine` during `PageType.__post_init__` — the declaration builds its own machines |
| [Mutation engine](03-mutation-engine.md) | exposes | supplies the command/field specs and kind constants the engine dispatches on |
| [Workspace store](02-workspace-store.md) | exposes | declares `RefCheck` / `ChildStateGuard` / `ParentStateGuard`, which the store evaluates |

## Invariants

1. **A page type's status transition table is derived from its commands, never authored.**
   `__post_init__` overwrites `fsm.transitions` with `_status_transitions(self)`. Violated, a
   declared edge can disagree with the command that fires it, and the FSM would permit a
   transition no command can perform (or vice versa).
2. **Every FSM spec a page type declares carries either a built machine or the error that stopped
   it — never both, never neither.** Violated, `machine_class` raises `LookupError` at request
   time for a spec the validator reported as fine.
3. **`validate_page_types` reports every declaration error in one exception.** It accumulates into
   a list and raises once. Violated, fixing a malformed page type becomes a restart-per-error
   loop.
4. **No request is served from an unvalidated registry.** `src/server.py` calls
   `validate_registry()` at module import. Violated, `_resolve_block_vocabularies`' best-effort
   sentinel (`block_kinds=None`) reaches a consumer, and a block argument is accepted with no
   vocabulary to check it against.
5. **A page type declares at most one field setter per `(section, field)`.** Checked in the
   post-init/validation path. Violated, `field_setter_edges` would have to choose between two
   commands for one `do` edge, and the "first legal one found is the only one there is" assumption
   in the mutation engine breaks.
6. **Exactly one registry is reachable at a time.** `registered_pagetypes()` returns the
   production map or the fixtures, and test mode physically empties the other into a stash.
   Violated, a test can bind to a production page type, coupling the suite to content the
   fixtures are meant to isolate it from.
7. **A spec's built machine takes no part in its identity.** `machine` / `machine_error` are
   `compare=False`. Violated, one `ElementFSMSpec` shared by several page types would stop
   comparing equal after the first build, and value-equality of declarations would break.
8. **This subsystem performs no I/O.** Declarations are data. Violated, importing a page type
   could fail or block on the environment, and `validate_registry()` at load stops being a pure
   check.

## Sync

Reconciled against commit `a35b133`.
