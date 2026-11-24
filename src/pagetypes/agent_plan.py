"""The `agent-plan` page type: one subagent an epic or a spike dispatches.

It is created under either parent and designed against both, so it has a module of its own rather
than living beside one of them. It holds one parent guard per parent type, each enforced only when
the page hangs under a parent of that type, and the parents' own guards over their agent-plan
children name it by its tag.
"""

from __future__ import annotations

from ._workspace_guidance import (
    SUBAGENT_DISPATCH_DESC,
    SUBAGENT_DISPATCH_FIELD,
    SUBAGENT_DISPATCH_LABEL,
)
from .core.specs import FSMSpec, ParentStateGuard, WorkspaceGuidanceSpec
from .core.args import _text
from .core.commands import (
    add_link_cmd,
    set_title_cmd,
    list_cmds,
    set_prose_cmd,
    set_scalar_cmd,
    transition_cmd,
    transition_on_add_cmd,
)
from .core.fields import SectionSpec, _list, _prose, _scalar
from .core.pagetype import PageType


# An agent-plan page may only be marked ready once its epic has reached `decomposition` or later -
# not while it is still in `draft` or `grounding` (the base is still being established), nor once
# `abandoned`. Enforced in the store.
_EPIC_IN_DECOMPOSITION_OR_LATER = ParentStateGuard(
    parent_type="epic",
    required_statuses=("decomposition", "planReview", "executing", "review", "shipped"),
    message="the epic must be in decomposition or later",
)

# Under a spike, agents are dispatched only while it researches: not while the user is still
# framing it in `draft`, while they are choosing, or once it has handed off. Enforced in the store.
_SPIKE_RESEARCHING = ParentStateGuard(
    parent_type="spike",
    required_statuses=("researching",),
    message="the spike must be researching",
)


# Tiers rather than model ids: an id rots between releases, and a stale enum rejects valid input.
_MODEL_TIERS = ("cheap", "standard", "capable")


# Seeded into every agent-plan page as its first section and written by no command: who writes
# this page.
_AGENT_PLAN_NOTICE = """
    This page is one dispatched agent's whole assignment. The controller - the session that created
    the epic or spike above it - writes the assignment, task and reporting contract, links the pages
    the agent works on, and is the only one to run markReady, reopen, accept or redispatch here. The
    dispatched agent creates the worktree named here, if one is named, and works only in it, runs
    start on this page as its first command, adds a report as each step lands, and ends with finish
    or block. It writes only this page and the pages this page links to with works-on - the
    feature-briefs it builds with their child pages, or the solution-investigation page it
    investigates - and never runs a command on the epic or spike above it or on another agent's
    page.
    """


_AGENT_PLAN = PageType(
    tag="agent-plan",
    name="Agent plan",
    description=(
        "One subagent an epic or a spike dispatches: its role, capability, exact task and the "
        "worktree it creates, if any, linked to the pages it works on - the feature-briefs it "
        "builds, or the investigation page it investigates. The agent reports back onto "
        "this page as it starts and works. Created by the controller as a direct child of its epic "
        "or spike."
    ),
    sections=(
        SectionSpec("notice", "Agent notice", (
            _prose("body", description="Agent notice fixed text.", fixed=_AGENT_PLAN_NOTICE),
        )),
        SectionSpec("assignment", "Assignment", (
            _scalar("role", description="""
                What this agent is, named as a role a reader recognises - implementer, test writer,
                integration reviewer, investigator. One agent-plan page is one dispatch, so the role
                describes this run rather than a definition shared with other agents.
                """),
            _scalar("capability", choices=_MODEL_TIERS, description="""
                The model tier this agent is dispatched on. Name it on every agent: an omitted tier
                silently inherits the session's most capable and most expensive model. Use cheap for
                mechanical single-file work whose content is already written down, standard for
                research, multi-file integration and judgement, and capable for architecture and
                final review.
                """),
            _scalar("worktree", description="""
                The git worktree this agent creates and works in, by name. Give every agent that
                edits code a different one: two agents in one checkout overwrite each other's edits.
                An agent that only reads code names none. An investigator names a spike worktree of
                its own, since an investigation ends in a proof the user opens; spike code is never
                integrated.
                """),
        )),
        SectionSpec("task", "Task", (
            _prose("body", description="""
                The exact work this agent does, written for a fresh agent with no history: it is
                handed this page id and nothing of the controller's context. Say which slice of the
                epic or spike it owns and what done looks like, name the shared contracts it touches
                by their id on the epic where there are any, and add only the decisions it needs that
                the pages it works on cannot tell it. Link each page it works on with addLink role
                works-on - each feature-brief it builds, or the solution-investigation page it
                investigates - and each agent-plan page that must be accepted before it starts with
                role depends-on. Point at large artifacts by file path rather than pasting them.
                """),
        )),
        SectionSpec("reporting", "Reporting contract", (
            _prose("body", description="""
                What this agent must leave behind before it runs finish, written as a checklist the
                controller verifies before accepting: which commands it must have run on the pages it
                works on, what status each of them must be left in, and what its finish report must
                say. An agent reports by driving those pages and this one, not by handing prose back,
                so name the page status you expect rather than the summary you want to read.
                """),
        )),
        SectionSpec("reports", "Reports", (
            _list("items", element_fields=("text",), description="""
                Each one report written back onto this page while the agent works: start records
                that it began and the worktree it created, a report records each step as it lands,
                and finish or block records the outcome or what stopped it. The controller adds one
                when it redispatches, saying what the next round must fix, so the list is the record
                of every attempt this agent made.
                """),
        )),
    ),
    commands=(
        # The controller's fields are draft-only, so the dispatched agent is never offered them;
        # reopen unlocks them again.
        set_scalar_cmd("assignment", "role", legal_in=("draft",)),
        set_scalar_cmd("assignment", "capability", choices=_MODEL_TIERS, legal_in=("draft",)),
        set_scalar_cmd("assignment", "worktree", legal_in=("draft",)),
        set_prose_cmd("task", legal_in=("draft",)),
        set_prose_cmd("reporting", label="reporting contract", legal_in=("draft",)),
        # The reports are the record of every attempt: they can be reordered, never removed.
        *list_cmds("reports", remove=False, add_args=(_text(),), legal_in=("working",)),
        transition_cmd("markReady", "draft -> ready",
                       requires=(("assignment", "role"), ("assignment", "capability"),
                                 ("assignment", "worktree"), ("task", "body"), ("reporting", "body")),
                       parent_guards=(_EPIC_IN_DECOMPOSITION_OR_LATER, _SPIKE_RESEARCHING)),
        transition_cmd("reopen", "ready -> draft (unlocks the assignment, task and reporting contract)"),
        # Each status change past ready writes its reason as a report in the same command.
        transition_on_add_cmd("start", "ready -> working", section="reports", field="items",
                              description="report that the agent has started, with the worktree it created",
                              add_args=(_text(),)),
        transition_on_add_cmd("finish", "working -> finished", section="reports", field="items",
                              description="report the outcome AND finish", add_args=(_text(),)),
        transition_on_add_cmd("block", "working -> blocked", section="reports", field="items",
                              description="report what stopped the work AND block", add_args=(_text(),)),
        transition_cmd("accept", "finished -> accepted"),
        transition_on_add_cmd("redispatch", "finished or blocked -> ready", legal_in=("finished", "blocked"),
                              section="reports", field="items",
                              description="report what the next round must fix AND send the agent back",
                              add_args=(_text(),)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="AgentPlan",
        initial="draft",
        states=("draft", "ready", "working", "finished", "blocked", "accepted"),
        terminal_states=("accepted",),
    ),
    # draft is where the controller defines the agent and its capability; ready is where it
    # launches it.
    workspace_guidance=(
        WorkspaceGuidanceSpec(SUBAGENT_DISPATCH_FIELD, ("draft", "ready"), SUBAGENT_DISPATCH_DESC,
                              SUBAGENT_DISPATCH_LABEL),
    ),
)
