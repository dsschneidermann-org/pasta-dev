"""The `agent-plan` page type."""

from __future__ import annotations

from . import (
    FSMSpec,
    PageType,
    RefCheck,
    SectionSpec,
    _DISPATCH_FSM,
    _EPIC_IN_DECOMPOSITION_OR_LATER,
    _MODEL_TIERS,
    _integer,
    _list,
    _prose,
    _text,
    add_link_cmd,
    element_cmds,
    list_cmds,
    set_prose_cmd,
    set_title_cmd,
    transition_cmd,
)

_AGENT_PLAN = PageType(
    tag="agent-plan",
    name="Agent plan",
    description=(
        "Which subagents an epic creates, the order they are dispatched in, and how their results "
        "are reported back onto the feature-briefs. Auto-created as a child of an epic."
    ),
    sections=(
        SectionSpec("agents", "Agents", (
            _list("items", element_fields=("role", "model", "mission", "reports"), description="""
                Each ONE subagent this epic creates: the role it plays, the model tier it runs on,
                the mission it is given, and what it must hand back. Write the mission for a fresh
                agent with no history, because a dispatched agent is given exactly this and never
                inherits the controller's context. Name the tier on every agent: an omitted model
                silently inherits the session's most capable and most expensive one. Use cheap for
                mechanical single-file work whose content is already written down, standard for
                multi-file integration and judgement, and capable for architecture and final review.
                Define a role once and dispatch it many times rather than writing a near-identical
                agent per workstream.
                """),
        )),
        SectionSpec("dispatches", "Dispatches", (
            _list("items",
                  element_fields=("agentId", "workstreamId", "wave", "worktree", "handoff",
                                  "outcome", "blocker", "status"),
                  element_fsm=_DISPATCH_FSM, description="""
                Each ONE run of one agent against one workstream, in the order they are sent: the
                agent element id in agentId, the parent epic's workstream element id in
                workstreamId, the parallel group in wave, the checkout it works in in worktree, and
                in handoff the facts this run needs that neither the agent definition nor the target
                brief can know. Dispatches sharing a wave may run at once; a higher wave starts only
                once every lower one is accepted. Give every dispatch in a wave a DIFFERENT
                worktree - concurrent runs in one checkout overwrite each other's edits - and record
                it here rather than on the agent, because a role is defined once and dispatched many
                times, so it is the run that occupies a checkout and not the definition. Keep
                handoff to the contracts and decisions this run actually touches, never the
                session's accumulated history, and point at large artifacts such as diffs and
                reports by file path so they stay out of the controller's context. Record what came
                back in outcome and what stopped it in blocker. A fix round is a redispatch of this
                element, not a new one, so the element stays the record of how many attempts the
                workstream took (element-FSM pending -> dispatched -> reported -> accepted).
                """),
        )),
        SectionSpec("reporting", "Reporting contract", (
            _prose("body", description="""
                How a finished agent's work lands back on its feature-brief, written as a checklist
                the controller can verify before accepting a dispatch: which of the brief's own
                commands must have been run, what status the brief and its plans must be left in,
                and where the agent's full written report lives. An agent reports by driving its own
                brief, not by handing prose back, so name the page state you expect rather than the
                summary you want to read. Accepting a dispatch without this check is how a
                workstream comes to be believed done while its brief still says otherwise.
                """),
        )),
    ),
    commands=(
        *list_cmds("agents", label="agent", legal_in=("draft",),
                   add_args=(_text("role"), _text("model", choices=_MODEL_TIERS),
                             _text("mission"), _text("reports"))),
        # `singular=` is required on both list_cmds and element_cmds here: the plural rule would
        # derive 'dispatche' from 'dispatches' and name the commands addDispatche / dispatcheId.
        # workstreamId is integrity-checked against the PARENT epic's workstreams list.
        # `worktree` is required like agentId/workstreamId/wave: a run without a named checkout is
        # the one gap that turns a same-wave parallel dispatch into two agents editing one copy.
        *list_cmds("dispatches", singular="dispatch", label="dispatch", legal_in=("draft",),
                   add_args=(_text("agentId"), _text("workstreamId"), _integer("wave"),
                             _text("worktree"), _text("handoff", required=False)),
                   ref_check=RefCheck(arg="workstreamId", scope="parent",
                                      section="workstreams", field="items")),
        # Run marks stay legal once the plan is `ready`: the record moves while the plan does not.
        # Only the structural edits above are `draft`-only.
        *element_cmds("dispatches", singular="dispatch", legal_in=("draft", "ready"), marks=(
            ("markDispatched", "dispatch", "mark a dispatch as sent to its agent"),
            ("reportDispatch", "report", "record what the agent returned", (_text("outcome"),)),
            ("acceptDispatch", "accept", "accept a reported dispatch as done"),
            ("redispatch", "redispatch", "send a reported or blocked dispatch back to an agent"),
            ("blockDispatch", "block", "record a dispatch as blocked", (_text("blocker"),)),
        )),
        set_prose_cmd("reporting", label="reporting contract", legal_in=("draft",)),
        transition_cmd("markReady", "draft -> ready",
                       requires=(("agents", "items"), ("dispatches", "items"), ("reporting", "body")),
                       parent_guards=(_EPIC_IN_DECOMPOSITION_OR_LATER,)),
        transition_cmd("reopen", "ready -> draft (unlocks structural edits)"),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="AgentPlan",
        initial="draft",
        states=("draft", "ready"),
    ),
)
