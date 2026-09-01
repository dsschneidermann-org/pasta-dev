"""Concrete ``StateChart`` classes for each registered page type.

The page-type status machines are built dynamically from their ``FSMSpec`` in
``fsm``; this module binds one to a stable, importable name per page type so tools
that reference a machine by import path - notably the ``statemachine-diagram`` Sphinx
directive used by the documentation site - can find it. Each class stays in sync with
its page type because it is derived from the same ``FSMSpec`` in the registry.
"""

from __future__ import annotations

import sys
from types import ModuleType

from .fsm import machine_class
from .pagetypes.core.pagetype import get_pagetype_field
from .pagetypes._registry import REGISTRY, registered_pagetypes

# One binding per production page type, so these lookups name REGISTRY rather than
# `registered_pagetypes()`: the documentation site is generated from the production types, and a
# module binding classes at import must not depend on which registry is in play at import time.


def _page_fsm(tag: str):
    page = REGISTRY.get(tag)
    if page is None:
        raise KeyError(f"Unknown page type {tag!r}.")
    return page.fsm


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


# Page-status machines (one per registered page type).
ArchitectureMachine = machine_class(_page_fsm("architecture"))
DecisionRecordMachine = machine_class(_page_fsm("decision-record"))
BugReportMachine = machine_class(_page_fsm("bug-report"))
SimpleChangeMachine = machine_class(_page_fsm("simple-change"))
FeatureBriefMachine = machine_class(_page_fsm("feature-brief"))
FeatureSpecMachine = machine_class(_page_fsm("feature-spec"))
ImplementationPlanMachine = machine_class(_page_fsm("implementation-plan"))
TestingPlanMachine = machine_class(_page_fsm("testing-plan"))
EpicMachine = machine_class(_page_fsm("epic"))
AgentPlanMachine = machine_class(_page_fsm("agent-plan"))
DocumentMachine = machine_class(_page_fsm("document"))
TocMachine = machine_class(_page_fsm("toc"))

# Element-level machines (a list element's own lifecycle).
StepMachine = machine_class(_element_fsm("implementation-plan", "steps", "items"))
CaseMachine = machine_class(_element_fsm("testing-plan", "cases", "items"))
QuestionMachine = machine_class(_element_fsm("feature-brief", "questions", "items"))
DispatchMachine = machine_class(_element_fsm("agent-plan", "dispatches", "items"))


def _bindings() -> ModuleType:
    """The module whose bound machine classes cover the page types in play - this one for the
    production registry, ``testcharts`` for the fixtures that stand in for it under test mode."""
    if registered_pagetypes() is REGISTRY:
        return sys.modules[__name__]
    from . import testcharts

    return testcharts


def page_machine_qualname(tag: str) -> str:
    """The importable dotted path of the page-status machine bound for page type `tag`.

    Used by doc generation to point the ``statemachine-diagram`` directive at the right class.
    ``machine_class`` is cached per ``FSMSpec``, so the class for a registry type's FSM *is* the
    same object bound in that registry's module; we reverse-look-up that identity rather than
    keeping a second hand-maintained tag→name map, so a newly registered type that forgets its
    binding raises loudly instead of silently going undocumented.
    """
    page_type = registered_pagetypes().get(tag)
    if page_type is None:
        raise KeyError(f"Unknown page type {tag!r}.")
    target = machine_class(page_type.fsm)
    module = _bindings()
    for name, obj in vars(module).items():
        if obj is target:
            return f"{module.__name__}.{name}"
    raise KeyError(f"No page-status machine is bound in {module.__name__} for page type {tag!r}.")
