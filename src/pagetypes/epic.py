"""The `epic` page type, and the `agent` pages created under it.

The two are declared together because they are designed against each other rather than
on their own, and reading one without the other would hide the coupling.
"""

from __future__ import annotations

from .core.specs import (
    ChildStateGuard,
    ElementFSMSpec,
    FSMSpec,
    ParentStateGuard,
)
from .core.args import _boolean, _text
from .core.commands import (
    add_link_cmd,
    set_title_cmd,
    element_cmds,
    list_cmds,
    set_element_field_cmd,
    set_prose_cmd,
    set_scalar_cmd,
    transition_cmd,
    transition_on_add_cmd,
)
from .core.fields import SectionSpec, _list, _prose, _scalar
from .core.pagetype import PageType

_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)


_VERDICTS = ("build-ready", "needs-changes", "needs-human-decision")
_SEVERITIES = ("blocking", "should-fix", "nit")
_EPIC_FINDING_ACTIONS = ("addAgent", "editAgent", "addContract", "addConstraint", "askQuestion",
                         "editContract", "edit")
# every agent status but draft: a reopened decomposition must not be refused by agents already at work
_AGENT_PLANNED = ("ready", "working", "finished", "blocked", "accepted")

# Seeded into every epic as its first section and written by no command: who may edit this page.
_CONTROLLER_NOTICE = """
    This epic is the controller's page. Only the controlling agent - the session that created this
    epic and dispatches its agents - runs commands on it. Each dispatched agent is handed one agent
    page, a child of this epic whose page id is the agent's id; it works from that page, reports back
    onto it, and writes only that page and the feature-briefs it links to, with their child pages.
    It never edits this epic or another agent's page. The controller records here what an agent
    raises: addFinding or editFinding for a problem, and editContract for a shared contract it
    corrected.
    """


_EPIC = PageType(
    tag="epic",
    name="Epic (major feature)",
    description=(
        "The root of a major feature too large for one feature-brief: it decomposes into several "
        "child feature-briefs and is built by subagents, each dispatched from an agent page of its "
        "own under the epic. Use it when the work splits into parts that each ship on their own; "
        "for one feature use a feature-brief, and for a small self-contained change use a "
        "simple-change."
    ),
    sections=(
        SectionSpec("notice", "Controller notice", (
            _prose("body", description="Controller notice fixed text.", fixed=_CONTROLLER_NOTICE),
        )),
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                The intent in a sentence or two: what you want to build and why it is worth building.
                Write it before reading any code, because grounding searches the repo from this line.
                State the outcome you want, not the implementation you imagine. If the outcome can be
                stated without joining two independent things with 'and', it is probably one
                feature-brief rather than an epic.
                """),
        )),
        SectionSpec("components", "Components", (
            _list("items", element_fields=("name",), description="""
                Each one part of the system this epic touches, named as a real file, module, or
                subsystem path you CONFIRMED exists while grounding. One per element. This is the
                epic's whole surface area: a component missed here is one no agent owns, and a
                component two agents both touch is a collision found only when the second agent's
                edits land on the first agent's file.
                """),
        )),
        SectionSpec("constraints", "Constraints", (
            _list("items", element_fields=("text",), description="""
                Each one project-wide requirement every agent must respect, with its exact
                values copied verbatim: version floors, dependency limits, naming and copy rules,
                platform and performance targets. Every dispatched agent inherits these and none of
                them can see the others' work, so a constraint recorded vaguely here is one that
                each agent interprets differently and the integration review has to reconcile.
                """),
        )),
        SectionSpec("conflicts", "Conflicts", (
            _list("items", element_fields=("text",), description="""
                Each one collision with what already exists, found while grounding: prior art that
                already solves part of this, an interface this epic would break, or a competing
                in-flight change. Name the file or page it collides with and say what has to give.
                Record collisions BETWEEN the intended agents here too, because two agents editing
                one file is the failure this list exists to catch before either is dispatched.
                """),
        )),
        SectionSpec("documentation", "Documentation", (
            _list("items", element_fields=("text",), description="""
                Each an existing pasta doc or architecture page this epic will make stale, found
                while grounding. Name the page and the specific part of it that will need to change,
                so reconciling it when the work lands is mechanical rather than a fresh investigation.
                """),
        )),
        SectionSpec("contracts", "Shared contracts", (
            _list("items", element_fields=("name", "owner", "shape"), description="""
                Each one interface that crosses an agent boundary: its name, the page id of the agent
                that defines it in owner, and its exact signature or data shape in shape. A dispatched
                agent sees only its own agent page and the briefs it links, so anything two agents
                must agree on is written here before either starts. Record the real signature rather
                than a description of one: 'returns the parsed config' is not a contract, a
                written-out function signature with its argument and return types is. Correct a
                contract in place with editContract: its id is what agent tasks and briefs point at.
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                Each one open question that blocks or reshapes the decomposition, asked as a single
                decidable question rather than a topic. Set needsHuman when only a person can settle
                it: a product call, a trade-off with no technically correct answer, or anything
                carrying cost or policy consequences. Answer it here once decided, because a question
                still open when the agents start is answered differently by every agent that reaches
                it.
                """),
        )),
        # The plan review's outcome, populated in `planReview`: the decomposition and its agent pages
        # are reviewed together, before any agent is dispatched. The verdict stays planReview-only;
        # findings are also recorded in `executing` and `review`, from what dispatched agents report.
        SectionSpec("review", "Plan review", (
            _scalar("verdict", choices=_VERDICTS, description="""
                The review outcome for the decomposition and its agent pages together. build-ready:
                the agents cover the epic with no gaps and no overlaps, and each could be dispatched
                from its page alone without getting stuck. needs-changes: at least one blocking
                finding must be applied before dispatching. needs-human-decision: the work cannot
                proceed until a person settles a question. Approve unless there are serious gaps,
                meaning a component no agent owns, two agents owning the same file, a contract two
                agents need that nobody defines, or an agent task too vague to act on. Minor wording
                preferences are never a reason to withhold build-ready.
                """),
            _list("findings", element_fields=("issue", "severity", "action"), description="""
                Each one finding against the plan or the work: what is wrong, why it matters, its
                severity, and the action taken to apply it. Recorded at the plan review before any
                agent is dispatched, and again while executing and in review, where the controller
                records what a dispatched agent reported or what integration turned up. blocking
                means an agent would build the wrong thing or two agents would collide; should-fix
                is real but survivable; nit is polish. Record the finding here AND make the edit its
                action names, so the plan and this record agree, and correct a finding in place
                with editFinding. Name the agent page it applies to.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        *list_cmds("components", add_args=(_text("name"),)),
        *list_cmds("constraints", add_args=(_text(),)),
        *list_cmds("conflicts", add_args=(_text(),)),
        *list_cmds("documentation", add_args=(_text(),)),
        *list_cmds("contracts", add_args=(_text("name"), _text("owner"), _text("shape")),
                   editable=True),
        # Questions carry the same surface as a feature-brief's: askQuestion (no remove), an answer
        # transition that also writes the answer, and an escalate that raises the needsHuman flag.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_VERDICTS,
                       legal_in=("planReview",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_SEVERITIES),
                             _text("action", required=False, choices=_EPIC_FINDING_ACTIONS,
                                   description="how the finding was applied to the plan")),
                   legal_in=("planReview", "executing", "review"), editable=True),
        # draft -> grounding needs only the intent: grounding reads the real repo from that one line.
        transition_cmd("beginGrounding", "draft -> grounding", requires=(("summary", "body"),)),
        # grounding -> decomposition is gated on the grounding having produced a base. From here the
        # child feature-briefs and the agent pages are created.
        transition_cmd("beginDecomposition", "grounding -> decomposition", requires=(
            ("components", "items"),
            ("constraints", "items"),
            ("conflicts", "items"),
            ("documentation", "items"),
        )),
        # decomposition -> planReview reviews the split AND the agent pages together, before any agent
        # is dispatched: no agent page may still be in draft (a page-status guard, store-checked).
        transition_cmd("submitPlan", "decomposition -> planReview",
                       requires=(("questions", "items"),),
                       guards=(ChildStateGuard("agent", _AGENT_PLANNED,
                                               "every agent page must be marked ready"),)),
        # planReview -> executing requires a verdict to have been recorded (the review happened).
        # `build-ready` is the signal to proceed; `needs-changes` should `reviseDecomposition`
        # instead. The verdict's VALUE is a soft guide (requires only checks presence).
        transition_cmd("approvePlan", "planReview -> executing", requires=(("review", "verdict"),)),
        transition_cmd("reviseDecomposition", "planReview -> decomposition (send the plan back)"),
        # executing -> review is guarded on every agent page having been accepted (a page-status
        # guard over the epic's agent children, checked in the store).
        transition_cmd("submitForReview", "executing -> review", guards=(
            ChildStateGuard("agent", ("accepted",), "every agent must be accepted"),)),
        transition_cmd("reopenDecomposition", "executing -> decomposition"),
        transition_cmd("requestChanges", "review -> executing", agency="either"),
        # `ship` is a human gate AND is guarded: every child feature-brief must itself be `shipped`
        # (a page-status guard over the epic's NON-pinned children, checked in the store).
        transition_cmd("ship", "review -> shipped (human gate)", agency="human", guards=(
            ChildStateGuard("feature-brief", ("shipped",),
                            "every child feature-brief must be shipped"),)),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "grounding", "decomposition", "planReview",
                                 "executing", "review")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Epic",
        initial="draft",
        states=("draft", "grounding", "decomposition", "planReview",
                "executing", "review", "shipped", "abandoned"),
        terminal_states=("shipped", "abandoned"),
    ),
)


# An agent page may only be marked ready once its epic has reached `decomposition` or later - not
# while it is still in `draft` or `grounding` (the base is still being established), nor once
# `abandoned`. Enforced in the store.
_EPIC_IN_DECOMPOSITION_OR_LATER = ParentStateGuard(
    parent_type="epic",
    required_statuses=("decomposition", "planReview", "executing", "review", "shipped"),
    message="the epic must be in decomposition or later",
)


# Tiers rather than model ids: an id rots between releases, and a stale enum rejects valid input.
_MODEL_TIERS = ("cheap", "standard", "capable")


# Seeded into every agent page as its first section and written by no command: who writes this page.
_AGENT_NOTICE = """
    This page is one dispatched agent's whole assignment, and its page id is the agent's id. The
    controller - the session that created the epic above it - writes the assignment, task and
    reporting contract, links the feature-briefs the agent works on, and is the only one to run
    markReady, reopen, accept or redispatch here. The dispatched agent creates the worktree named
    here and works only in it, runs start on this page as its first command, adds a report as each
    step lands, and ends with finish or block. It writes only this page and the feature-briefs this
    page links to, with their child pages, and never runs a command on the epic or on another
    agent's page.
    """


_AGENT = PageType(
    tag="agent",
    name="Agent",
    description=(
        "One subagent an epic dispatches: its role, capability, exact task and the worktree it "
        "creates, linked to the feature-briefs it works on. Its page id is the agent's id, and the "
        "agent reports back onto this page as it starts and works. Created by the controller as a "
        "direct child of its epic."
    ),
    sections=(
        SectionSpec("notice", "Agent notice", (
            _prose("body", description="Agent notice fixed text.", fixed=_AGENT_NOTICE),
        )),
        SectionSpec("assignment", "Assignment", (
            _scalar("role", description="""
                What this agent is, named as a role a reader recognises - implementer, test writer,
                integration reviewer. One agent page is one dispatch, so the role describes this run
                rather than a definition shared with other agents.
                """),
            _scalar("capability", choices=_MODEL_TIERS, description="""
                The model tier this agent is dispatched on. Name it on every agent: an omitted tier
                silently inherits the session's most capable and most expensive model. Use cheap for
                mechanical single-file work whose content is already written down, standard for
                multi-file integration and judgement, and capable for architecture and final review.
                """),
            _scalar("worktree", description="""
                The git worktree this agent creates and works in, by name. Give every agent a
                different one: two agents in one checkout overwrite each other's edits.
                """),
        )),
        SectionSpec("task", "Task", (
            _prose("body", description="""
                The exact work this agent does, written for a fresh agent with no history: it is
                handed this page id and nothing of the controller's context. Say which slice of the
                epic it owns and what done looks like, name the shared contracts it touches by their
                id on the epic, and add only the decisions it needs that its feature-briefs cannot
                tell it. Link each feature-brief it works on with addLink role works-on, and each
                agent page that must be accepted before it starts with role depends-on. Point at
                large artifacts by file path rather than pasting them.
                """),
        )),
        SectionSpec("reporting", "Reporting contract", (
            _prose("body", description="""
                What this agent must leave behind before it runs finish, written as a checklist the
                controller verifies before accepting: which commands it must have run on its linked
                feature-briefs, what status each brief and its plans must be left in, and what its
                finish report must say. An agent reports by driving its briefs and this page, not by
                handing prose back, so name the page status you expect rather than the summary you
                want to read.
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
        # The controller's fields are draft-only, so a dispatched agent's own nextActions never
        # offers them; reopen unlocks them again.
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
                       parent_guards=(_EPIC_IN_DECOMPOSITION_OR_LATER,)),
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
        name="Agent",
        initial="draft",
        states=("draft", "ready", "working", "finished", "blocked", "accepted"),
        terminal_states=("accepted",),
    ),
)
