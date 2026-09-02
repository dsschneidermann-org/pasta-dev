"""Pure FSM evaluation via python-statemachine.

For each `FSMSpec` we build one `StateMachine` subclass - held by the page type that
declares it, memoized here otherwise - then evaluate a transition on an *ephemeral*
instance seeded at the page's current status. The machine is the single source of truth
for legality and for the resulting state.

Design notes (verified against python-statemachine 3.2.0):

- A state's logical id is carried in `State(value=...)`, while the class attribute
  name is `state_<value>`. This lets a state and an event share a name (bug-report's
  `open` state and `open` event) without an attribute clash. The status is read back
  from `configuration_values` (state *values*), never the attribute name.
- The classic `StateMachine` rejects an out-of-state event with `TransitionNotAllowed`,
  which we surface as an `IllegalCommandError`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from statemachine import Event, State, StateMachine
from statemachine.exceptions import InvalidDefinition, TransitionNotAllowed

from .errors import IllegalCommandError
from .pagetypes.core.specs import ElementFSMSpec, FSMSpec


def build_machine(fsm: FSMSpec | ElementFSMSpec) -> type[StateMachine]:
    """Build a StateMachine subclass from an FSM spec.

    Uncached - the caller keeps what it builds. Raises `InvalidDefinition` when the graph is
    not well formed, which is python-statemachine's own check.
    """
    namespace: dict[str, object] = {}
    state_attr = {value: f"state_{value}" for value in fsm.states}

    # A state with no outgoing transition is terminal. python-statemachine's "trap state"
    # validation requires such states to be declared final=True, so we infer it here rather
    # than making every FSMSpec author remember to. (Cyclic FSMs like architecture/bug-report
    # have no such states, so this leaves them unchanged.)
    sources = {source for _event, source, _dest, _agency in fsm.transitions}

    for value in fsm.states:
        namespace[state_attr[value]] = State(
            value, value=value, initial=(value == fsm.initial), final=(value not in sources)
        )

    # Group transitions by event, OR-combining alternatives that share an event. Each event is
    # wrapped in an Event whose name is its id, so diagrams label edges with the exact command
    # name (e.g. "markStale") instead of python-statemachine's title-cased default ("Markstale").
    # The attribute name still fixes the event id, so send()/allowed_events are unaffected.
    by_event: dict[str, object] = {}
    for event, source, dest, _agency in fsm.transitions:
        segment = namespace[state_attr[source]].to(namespace[state_attr[dest]])  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
        by_event[event] = segment if event not in by_event else by_event[event] | segment
    for event, transitions in by_event.items():
        namespace[event] = Event(transitions, name=event)  # pyright: ignore[reportArgumentType]

    return type(fsm.name, (StateMachine,), namespace)


def try_build_machine(
    fsm: FSMSpec | ElementFSMSpec,
) -> tuple[type[StateMachine] | None, InvalidDefinition | None]:
    """The machine built from `fsm`, or the definition error that stopped it.

    Building is the well-formedness check, so a spec that cannot build hands its error back
    rather than raising out of the class creation that triggered it.
    """
    try:
        return build_machine(fsm), None
    except InvalidDefinition as exc:
        return None, exc


@lru_cache(maxsize=None)
def _cached_machine(fsm: FSMSpec | ElementFSMSpec) -> type[StateMachine]:
    """Build (once) a StateMachine subclass from an FSM spec, keyed on the spec itself."""
    return build_machine(fsm)


def _current_value(machine: StateMachine) -> str:
    """The single active state's value (these FSMs are flat, so there is exactly one)."""
    return next(iter(machine.configuration_values))


def machine_class(fsm: FSMSpec | ElementFSMSpec) -> Any:
    """The StateMachine subclass for an FSM spec: the one its owner built, else a cached build.

    A page type builds its machine as it is declared and keeps it, so that machine is collected
    with the declaration rather than held in the cache. Anything else - an element spec, or a
    page spec no page type owns - goes through the cache. Either way the same class comes back
    every time, which is what ``src.statecharts`` binds for docs/introspection.
    """
    owned = fsm.machine if isinstance(fsm, FSMSpec) else None
    return owned if owned is not None else _cached_machine(fsm)


def allowed_events(fsm: FSMSpec | ElementFSMSpec, current_status: str) -> set[str]:
    """The set of FSM event ids legal from `current_status` (topology only)."""
    machine = machine_class(fsm)(start_value=current_status)
    return {event.id for event in machine.allowed_events}


def fire(fsm: FSMSpec | ElementFSMSpec, current_status: str, event: str) -> str:
    """Return the status reached by firing `event` from `current_status`.

    Raises `IllegalCommandError` if the event is not legal from that state.
    """
    machine = machine_class(fsm)(start_value=current_status)
    try:
        machine.send(event)
    except TransitionNotAllowed as exc:
        raise IllegalCommandError(str(exc)) from exc
    return _current_value(machine)


def is_valid_status(fsm: FSMSpec | ElementFSMSpec, status: str) -> bool:
    return status in fsm.states
