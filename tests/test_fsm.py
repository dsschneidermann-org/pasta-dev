"""Unit tests for the pure FSM evaluator (src.fsm)."""

import pytest

from statemachine import StateMachine
from statemachine import registry as sm_registry

from src import fsm
from src.errors import IllegalCommandError
from src.pagetypes.core.commands import CommandSpec, transition_cmd
from src.pagetypes.core.fields import SectionSpec, _prose
from src.pagetypes.core.pagetype import PageType
from src.pagetypes.core.specs import ElementFSMSpec, FSMSpec
from src.pagetypes._registry import get_page_type, registered_pagetypes

# Two hand-authored fixtures cover the FSM engine's cases: `test-child` is a simple 2-state cyclic
# machine (draft <-> ready); `test-flow` is a 3-state cycle whose STATE `open` and EVENT `open`
# deliberately share a name (the engine must keep those distinct).
CHILD = get_page_type("test-child").fsm
FLOW = get_page_type("test-flow").fsm


def test_two_state_cycle_allowed_and_fire():
    assert fsm.allowed_events(CHILD, "draft") == {"markReady"}
    assert fsm.fire(CHILD, "draft", "markReady") == "ready"
    assert fsm.allowed_events(CHILD, "ready") == {"reopen"}
    assert fsm.fire(CHILD, "ready", "reopen") == "draft"


def test_illegal_transition_raises():
    with pytest.raises(IllegalCommandError):
        fsm.fire(CHILD, "draft", "reopen")   # reopen is legal only from ready


def test_shared_state_and_event_name_full_cycle():
    # The event `open` and the state `open` share a name - this must still work.
    assert fsm.allowed_events(FLOW, "draft") == {"open"}
    assert fsm.fire(FLOW, "draft", "open") == "open"
    assert fsm.allowed_events(FLOW, "open") == {"close"}
    assert fsm.fire(FLOW, "open", "close") == "closed"
    assert fsm.allowed_events(FLOW, "closed") == {"reopen"}
    assert fsm.fire(FLOW, "closed", "reopen") == "open"


def test_flow_illegal_transition_raises():
    with pytest.raises(IllegalCommandError):
        fsm.fire(FLOW, "closed", "open")  # can only reopen from closed


def test_is_valid_status():
    assert fsm.is_valid_status(CHILD, "draft")
    assert not fsm.is_valid_status(CHILD, "nonexistent")


def test_status_guidance_keeps_fsmspec_hashable_for_the_machine_cache():
    # A dict field here would raise "unhashable type" at the _cached_machine cache.
    made = [FSMSpec(name="Guided", initial="draft", states=("draft", "open"),
                    transitions=(("open", "draft", "open", "agent"),),
                    status_guidance=(("open", "do the open work"),))
            for _ in range(2)]
    assert fsm.machine_class(made[0]) is fsm.machine_class(made[1])


# --- Page types own their status machine -------------------------------------
def _ad_hoc_type(tag: str, name: str, states: tuple[str, ...], *commands: CommandSpec) -> PageType:
    """An ad-hoc page type whose FSM table derives from the transition commands it is given."""
    return PageType(
        tag=tag, name=name, description="ad-hoc",
        sections=(SectionSpec("body", "Body", (_prose("body"),)),),
        commands=commands,
        fsm=FSMSpec(name=name, initial=states[0], states=states))


def test_a_page_type_builds_its_status_machine_as_it_is_constructed():
    built = _ad_hoc_type("xtest-owned", "XOwned", ("draft", "done"),
                         transition_cmd("finish", "draft → done"))
    assert built.machine_error is None
    assert issubclass(built.machine, StateMachine)
    # python-statemachine registers every class it creates, so the machine being there is the
    # library's own record that the build happened - under a name only this type declares.
    assert sm_registry._REGISTRY[f"src.fsm.{built.fsm.name}"] is built.machine
    first = built.machine
    assert built.machine is first


def test_a_machine_that_cannot_be_built_is_kept_as_an_error_rather_than_raised():
    # `orphan` is unreachable from `draft`, which python-statemachine rejects when the class is
    # created. Constructing the page type must not raise; the error is held for the validator.
    built = _ad_hoc_type("xtest-orphan", "XOrphan", ("draft", "done", "orphan"),
                         transition_cmd("finish", "draft → done"))
    assert built.machine is None
    assert "orphan" in str(built.machine_error)


def test_every_production_page_type_holds_its_machine(production_mode):
    """Nothing in this test builds a machine, so finding one on every type is evidence they were
    built with the declarations rather than on first use."""
    for tag, page_type in registered_pagetypes().items():
        assert page_type.machine is not None, tag
        assert page_type.machine_error is None, tag


def test_page_status_machines_do_not_enter_the_machine_cache(production_mode):
    """A page type carries its own machine, so evaluating every production status leaves the cache
    exactly as it was - while an element FSM, which no page type owns, still lands in it."""
    before = fsm._cached_machine.cache_info().currsize
    for page_type in registered_pagetypes().values():
        for status in page_type.fsm.states:
            fsm.allowed_events(page_type.fsm, status)
    assert fsm._cached_machine.cache_info().currsize == before

    element = ElementFSMSpec(name="XElement", initial="todo", states=("todo", "done"),
                             transitions=(("markDone", "todo", "done", "agent"),))
    fsm.allowed_events(element, "todo")
    assert fsm._cached_machine.cache_info().currsize == before + 1


def test_production_status_evaluation_matches_the_declared_transition_table(production_mode):
    """Legality and the status reached are read off the machine; both must still agree with the
    table the page type derived, for every (page type, status) pair the registry declares."""
    for tag, page_type in registered_pagetypes().items():
        spec = page_type.fsm
        declared = {event for event, _source, _dest, _agency in spec.transitions}
        for status in spec.states:
            legal = {event for event, source, _dest, _agency in spec.transitions if source == status}
            assert fsm.allowed_events(spec, status) == legal, (tag, status)
            for event, source, dest, _agency in spec.transitions:
                if source == status:
                    assert fsm.fire(spec, status, event) == dest, (tag, status, event)
            for event in declared - legal:
                with pytest.raises(IllegalCommandError):
                    fsm.fire(spec, status, event)
