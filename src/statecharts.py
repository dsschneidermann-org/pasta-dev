"""Concrete ``StateChart`` classes for each registered page type.

The page-type status machines are built dynamically from their ``FSMSpec`` in
``fsm``; this module serves one under a stable, importable name per page type so tools
that reference a machine by import path - notably the ``statemachine-diagram`` Sphinx
directive used by the documentation site - can find it. Each class stays in sync with
its page type because it is derived from the same ``FSMSpec`` in the registry.
"""

from __future__ import annotations

from .fsm import machine_class
from .pagetypes.core.pagetype import get_pagetype_field
from .pagetypes._registry import REGISTRY

# The documentation site publishes the production types, so these lookups read the production
# registry directly rather than whichever one is in play.


def __getattr__(name: str):
    """The page-status machine bound under `name`, derived from the registry.

    Resolved per call against the live ``REGISTRY`` rather than a snapshot taken at
    import, so an HMR reload of the page types cannot leave a stale class bound here.
    Reached only when normal attribute lookup fails (PEP 562), so the element bindings
    below shadow it and are unaffected.
    """
    for page_type in REGISTRY.values():
        if f"{page_type.fsm.name}Machine" == name:
            return machine_class(page_type.fsm)
    raise AttributeError(f"No page-status machine is bound as {name!r}.")


def _element_fsm(tag: str, section: str, field: str):
    page = REGISTRY.get(tag)
    if page is None:
        raise KeyError(f"Unknown page type {tag!r}.")
    field_spec = get_pagetype_field(page, section, field)
    if field_spec is None:
        raise KeyError(f"Unknown field {section!r} {field!r}.")
    element_fsm = field_spec.element_fsm
    if element_fsm is None:
        raise LookupError(f"Missing element_fsm on field {section!r} {field!r}.")
    return element_fsm


# Element-level machines (a list element's own lifecycle).
StepMachine = machine_class(_element_fsm("implementation-plan", "steps", "items"))
CaseMachine = machine_class(_element_fsm("testing-plan", "cases", "items"))
QuestionMachine = machine_class(_element_fsm("feature-brief", "questions", "items"))
DispatchMachine = machine_class(_element_fsm("agent-plan", "dispatches", "items"))
