"""Tests for the page-status machine bindings (src.statecharts).

Page machines are served by a module-level ``__getattr__`` derived from the registry, so there is
no binding to keep in step with the page types; the element machines are bound directly, at import.
These cover that split: what resolves, what does not, and which half is a real module attribute.
"""

import pytest

from src import statecharts
from src.fsm import machine_class
from src.pagetypes._registry import REGISTRY


def test_page_machine_resolves_from_the_registry(production_mode):
    """A page type's machine is reachable under its derived name, and is the same class the FSM
    builds - which is what makes the dotted path the diagram directive imports point somewhere."""
    for page_type in REGISTRY.values():
        resolved = getattr(statecharts, f"{page_type.fsm.name}Machine")
        assert resolved is machine_class(page_type.fsm), page_type.tag


def test_unknown_machine_name_raises(production_mode):
    with pytest.raises(AttributeError, match="No page-status machine is bound"):
        getattr(statecharts, "NoSuchMachine")


def test_element_machines_are_bound_directly():
    """The element machines are real module attributes rather than resolved on access, so normal
    lookup finds them before `__getattr__` is consulted."""
    for name in ("StepMachine", "CaseMachine", "QuestionMachine", "DispatchMachine"):
        assert name in vars(statecharts)
