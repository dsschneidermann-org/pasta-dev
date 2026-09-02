"""Concrete ``StateChart`` classes for each registered page type.

The page-type status machines are built dynamically from their ``FSMSpec`` in
``fsm``; this module binds one to a stable, importable name per page type so tools
that reference a machine by import path - notably the ``statemachine-diagram`` Sphinx
directive used by the documentation site - can find it. Each class stays in sync with
its page type because it is derived from the same ``FSMSpec`` in the registry.
"""

from __future__ import annotations

from .fsm import machine_class
from .pagetypes.core.pagetype import get_pagetype_field
from .pagetypes._registry import REGISTRY

# One binding per production page type: the documentation site publishes the production types, so
# these lookups read the production registry directly rather than whichever one is in play.


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
