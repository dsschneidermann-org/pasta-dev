# FSM evaluation

## Summary

**Kind:** module

The thin adapter over `python-statemachine` that turns an FSM spec into a real `StateMachine`
class and evaluates one transition on an ephemeral instance, making the library the single source
of truth for status legality.

Nine symbols across 118 lines — the smallest component documented here, and the one with the
highest ratio of design decisions to code.

## Purpose

It exists so that pasta never re-implements state-machine semantics. Rather than hand-rolling a
transition table walk, the module builds a real machine from each declaration and asks it: what
events are legal here, and what state does this event reach? That makes the library's own checks —
connectivity, unreachable states, trap states — pasta's declaration checks for free.

The second reason it exists is isolation. `python-statemachine` has a specific and slightly
surprising API surface (state *values* versus attribute names, `TransitionNotAllowed`,
`configuration_values`), and every one of those details is confined to this file. The rest of
pasta deals in plain status strings and `IllegalCommandError`. Delete this module and either the
FSM semantics get re-derived by hand in `commands.py` and `store.py`, or the library's idioms leak
into both.

**Entirely pure**, with one caveat worth stating: `build_machine` calls `type(...)` to create a
class, so it has a process-level effect (a new class object) even though it touches no external
state. That is exactly why it is called once per spec at declaration time rather than per request.

## Usage

Two distinct phases, and the split is the whole design:

**Build time** — called by the page-type layer during `PageType.__post_init__`:

- `try_build_machine(fsm)` → `(machine, None)` or `(None, InvalidDefinition)`. The page type
  stores whichever it gets; a definition error is held for the validator, not raised.
- `build_machine(fsm)` is the raw builder, uncached — *the caller keeps what it builds*.

**Evaluation time** — called per request by the mutation engine and the store:

- `allowed_events(fsm, current_status)` → the set of legal event ids (4 callers: `commands`
  ×2 paths, `store.next_actions`, `docsgen`).
- `fire(fsm, current_status, event)` → the status reached, or `IllegalCommandError`.
- `is_valid_status(fsm, status)` → membership in `fsm.states`.
- `machine_class(fsm)` → the class the spec already carries. **It never builds.**

Both evaluators seed a *fresh, ephemeral* instance at the current status
(`machine_class(fsm)(start_value=current_status)`), evaluate, and discard it. No machine instance
is ever retained, so there is no per-page runtime object whose state could drift from the
persisted `page.status`.

## Data model

This module owns no data. It reads `FSMSpec` / `ElementFSMSpec` (component 05) and writes nothing
back — the *page type* stores the built machine on the spec, via its own `_store_machine`.

The one representational decision is how a state is addressed, and it is load-bearing:

- A state's **logical id** is carried in `State(value=...)`.
- The **class attribute** holding it is named `state_<value>`.
- Status is always read back from `machine.configuration_values` — state *values*, never
  attribute names.

That indirection exists so a state and an event can share a name. `bug-report` has both an `open`
state and an `open` event; without the `state_` prefix they would collide as class attributes.

Machines built here are **guardless by design**. Required-content preconditions and status-scoped
command locks live in `commands.py`, not in the machine. Two things follow: the doc generator can
replay any `:events:` path on a content-less page (component 08), and legality is never split
across two mechanisms that could disagree.

## Details

The builder does three non-obvious things.

**It infers `final=True` rather than making authors declare it.** python-statemachine's trap-state
validation requires a state with no outgoing transition to be declared final, so the builder
derives it:

```python
sources = {source for _event, source, _dest, _agency in fsm.transitions}
for value in fsm.states:
    namespace[state_attr[value]] = State(
        value, value=value, initial=(value == fsm.initial), final=(value not in sources))
```

Cyclic FSMs (`architecture`, `bug-report`) have no such states, so this leaves them unchanged.
Note this is a *library* concern and is independent of `FSMSpec.terminal_states`, which is an
explicit authoring declaration about locking content (component 05).

**It OR-combines alternatives that share an event**, so a multi-source `abandon` is one event with
several segments rather than several events.

**It names each `Event` explicitly** — `Event(transitions, name=event)` — so diagrams label edges
with the exact command name (`markStale`) instead of python-statemachine's title-cased default
(`Markstale`). The attribute name still fixes the event id, so `send()` and `allowed_events` are
unaffected. This is a documentation-quality decision made in the builder because that is the only
place that can make it.

**`machine_class` refuses to build.** This is the invariant that the eager-build design rests on:

```python
if fsm.machine is None:
    raise LookupError(
        f"No machine was built for FSM spec {fsm.name!r}. A spec is built by the page type "
        f"that declares it; this one is declared by none, or its build failed and "
        f"validate_page_types would have reported it.")
```

A lazy fallback would hand out a *fresh class per call*, which would be both slow and subtly wrong
(class identity would stop being stable). A spec no page type declares is unreachable in normal
operation, so this is treated as a programming error rather than a cache miss.

Finally, `fire` translates `TransitionNotAllowed` into `IllegalCommandError`, which is the one
place the library's exception vocabulary is mapped onto pasta's.

The design notes in the module docstring are marked *verified against python-statemachine 3.2.0* —
worth re-checking on a dependency bump, since the state-value/attribute-name behaviour and the
trap-state validation are both things a major version could change.

On the graph: `fsm.py` shares `Cluster_33` with `core/pagetype.py` at 83% cohesion. That is the
build-time coupling made visible — the two files are one unit at declaration time and fully
separate at evaluation time.

## Code references

| File | Symbol | Kind |
|---|---|---|
| `src/fsm.py` | `build_machine` | function |
| `src/fsm.py` | `try_build_machine` | function |
| `src/fsm.py` | `machine_class` | function |
| `src/fsm.py` | `allowed_events` | function |
| `src/fsm.py` | `fire` | function |
| `src/fsm.py` | `is_valid_status` | function |
| `src/fsm.py` | `_current_value` | function |

## Dependencies

| Target | Role | Note |
|---|---|---|
| `python-statemachine` (3.2.0) | depends-on | `State`, `Event`, `StateMachine`, `InvalidDefinition`, `TransitionNotAllowed`; the only component that imports it |
| [Page-type system](05-page-type-system.md) | depends-on | reads `FSMSpec` / `ElementFSMSpec`; the page type calls back in to build and stores the result |
| [Domain model](04-domain-model.md) | depends-on | raises `IllegalCommandError` |
| [Mutation engine](03-mutation-engine.md) | exposes | `allowed_events` / `fire` back every legality decision |
| [Workspace store](02-workspace-store.md) | exposes | `allowed_events` for `next_actions`; status validity on `set_page_status` |

## Invariants

1. **A machine is built once, by the page type that declares the spec.** `machine_class` raises
   rather than building. Violated, class identity stops being stable across calls and every
   evaluation pays a class-creation cost.
2. **No `StateMachine` instance outlives the call that created it.** Both `fire` and
   `allowed_events` construct, evaluate, and discard. Violated, a retained instance's state could
   diverge from the persisted `page.status`, and there would be two competing answers to "what
   status is this page in".
3. **Status is read from `configuration_values`, never from a state attribute name.** Violated,
   a page type with a state and event sharing a name (`bug-report`'s `open`) reads back the
   attribute name `state_open` as its status and every subsequent status comparison fails.
4. **A state with no outgoing transition is built with `final=True`.** Inferred from the
   transition table. Violated, python-statemachine's trap-state validation rejects the definition
   and the page type fails to build at all.
5. **These machines carry no guards.** Content preconditions live in `commands.py`. Violated, doc
   generation can no longer replay an arbitrary `:events:` path on a content-less page, and
   legality is decided in two places that can disagree.
6. **An FSM definition error is returned, not raised, at build time.** `try_build_machine` catches
   `InvalidDefinition`. Violated, one malformed page type aborts module import, and the validator
   can never aggregate the remaining errors.

## Sync

Reconciled against commit `a35b133`.
