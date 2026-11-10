"""The `epic` page type, the `agent-plan` pages created under it, and its pinned `solution-research`
and `solution-design` pages.

They are declared together because they are designed against each other rather than on their
own: the epic's gates read its children's statuses and the children's gates read the epic's, so
reading one without the others would hide the coupling.
"""

from __future__ import annotations

from ._stage_guidance import (
    CHECKING,
    DECIDING,
    DECOMPOSITION,
    DESIGN_REVIEW,
    DESIGNING,
    DRAFTING,
    EPIC_DRAFT,
    INVESTIGATING,
    JUDGING,
    RESEARCHING,
)
from ._workspace_guidance import (
    GROUNDING_TOOL_DESC,
    GROUNDING_TOOL_FIELD,
    GROUNDING_TOOL_LABEL,
    HUMAN_REACH_DESC,
    HUMAN_REACH_FIELD,
    HUMAN_REACH_LABEL,
    RESEARCH_SOURCES_DESC,
    RESEARCH_SOURCES_FIELD,
    RESEARCH_SOURCES_LABEL,
)
from .core.specs import (
    AutoChildSpec,
    ChildStateGuard,
    ElementFSMSpec,
    FSMSpec,
    ParentStateGuard,
    WorkspaceGuidanceSpec,
)
from .core.args import _boolean, _text, standard_blocks
from .core.commands import (
    add_link_cmd,
    blocks_cmds,
    set_title_cmd,
    element_cmds,
    list_cmds,
    set_element_field_cmd,
    set_prose_cmd,
    set_scalar_cmd,
    transition_cmd,
    transition_on_add_cmd,
)
from .core.fields import SectionSpec, _blocks, _list, _prose, _scalar
from .core.pagetype import PageType

_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)


_VERDICTS = ("build-ready", "needs-changes", "needs-human-decision")
_SEVERITIES = ("blocking", "should-fix", "nit")
_EPIC_FINDING_ACTIONS = ("addAgent", "editAgent", "addContract", "askQuestion", "editContract",
                         "reopenDesign", "edit")
_OUTCOME_KINDS = ("goal", "non-goal", "anti-goal")
_SAID_BY = ("person", "proposal")
# Every agent status but draft: a reopened decomposition must not be refused by agents already at work
_AGENT_PLANNED = ("ready", "working", "finished", "blocked", "accepted")

# Seeded into every epic as its first section and written by no command: who may edit this page.
_CONTROLLER_NOTICE = """
    This epic is the controller's page. Only the controlling agent - the session that created this
    epic and dispatches its agents - runs commands on it. Research, design and every build are done
    by dispatched agents: each is handed one agent-plan page, a child of this epic whose page id is
    the agent's id, works from that page, reports back onto it, and writes only that page and the
    pages it links to with works-on - this epic's solution-research or solution-design page, or the
    feature-briefs it builds with their child pages. It never edits this epic or another agent's
    page. The controller reads the research and design pages' digests rather than the whole pages,
    and records here what an agent raises: addFinding or editFinding for a problem, and
    editContract for a shared contract it corrected.
    """


_EPIC = PageType(
    tag="epic",
    name="Epic (major feature)",
    description=(
        "The root of a major feature too large for one feature-brief. A research agent and a "
        "design agent work out the solution on its pinned solution-research and solution-design "
        "pages, a person picks the approach and signs off the design, and it then decomposes into "
        "several child feature-briefs built by subagents, each dispatched from an agent-plan page "
        "of its own under the epic. Use it when the work splits into parts that each ship on their "
        "own; for one feature use a feature-brief, and for a small self-contained change use a "
        "simple-change."
    ),
    sections=(
        SectionSpec("notice", "Controller notice", (
            _prose("body", description="Controller notice fixed text.", fixed=_CONTROLLER_NOTICE),
        )),
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                The intent in a sentence or two: what you want to build and why it is worth building.
                Write it before any code is read, because the research agent searches the repo from
                this line. State the outcome you want, not the implementation you imagine. If the
                outcome can be stated without joining two independent things with 'and', it is
                probably one feature-brief rather than an epic.
                """),
        )),
        SectionSpec("framing", "Framing", (
            _prose("why", description="""
                Why the person wants this, in their words: the problem it removes or what it makes
                possible, and why now. If they have not said, ask one open question with nothing to
                pick from; never infer it from the summary. Research ranks approaches against this
                paragraph, so a guessed why yields approaches that solve the wrong problem well.
                """),
            _list("outcomes", element_fields=("text", "kind", "said"), description="""
                Each one goal, non-goal or anti-goal (kind), where an anti-goal is something that
                would make this a failure even if it technically works. said is person when they
                stated it and proposal when you filled it in, and you present every proposal to them
                as yours. Write them before research begins: the approaches are judged against them,
                and outcomes written after the approaches get fitted to them. Write each so a
                reviewer could tell whether the built result meets it: the design copies these
                verbatim, and a vague one becomes a criterion nobody can check.
                """),
        )),
        SectionSpec("decision", "Approach decision", (
            _list("chosen", element_fields=("approachId", "takes"), description="""
                The approach the person picked, by the element id of that approach on this epic's
                solution-research page. Usually one element; a hybrid gets one per approach it draws
                from, with what it takes from each in takes. Record only a pick the person made, or,
                when they handed you the how, your recommendation with takes saying it was your
                call. The design agent is dispatched against exactly this.
                """),
        )),
        SectionSpec("contracts", "Shared contracts", (
            _list("items", element_fields=("name", "owner", "shape"), description="""
                Each one interface that crosses an agent boundary: its name, the page id of the agent
                that defines it in owner, and its exact signature or data shape in shape. Start from
                the design's interfaces: each one two feature-briefs share becomes a contract here,
                its shape copied verbatim. A dispatched agent sees only its own agent-plan page and
                the pages it links, so anything two agents must agree on is written here before
                either starts. Record the real signature rather than a description of one: 'returns
                the parsed config' is not a contract, a written-out function signature with its
                argument and return types is. Correct a contract in place with editContract: its id
                is what agent tasks and briefs point at.
                """),
        )),
        SectionSpec("scheduling", "Scheduling", (
            _prose("body", description="""
                How the controller dispatches this epic's build agent-plan pages, written as the
                instructions it follows while executing. Group the agent-plan pages into waves and
                name each page by id under its wave: the agents in one wave run at once, so none of
                them may need another's work. Say what must be true before the next wave is
                dispatched - normally that every agent in the earlier waves is accepted and its work
                integrated into the branch the next wave starts from, which may be main or a
                worktree branch of the epic's own. Keep it consistent with the depends-on links
                between agent-plan pages: the links are what each agent sees, this section is what
                the controller dispatches from. The research and design agents are dispatched by
                the researching and designing stages, not from here.
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                Each one question only the person can settle, asked as a single decidable question in
                their terms rather than a topic: the research page's questions, the design check's
                escalations and the decomposition's questions all land here, so this list is the one
                record of what the person decided, and the approach pick is always one of them. Set
                needsHuman while it waits on them, and answer it here with their words once decided,
                because a question still open when the agents start is answered differently by
                every agent that reaches it.
                """),
        )),
        # The plan review's outcome, populated in `planReview`: the decomposition and its agent-plan
        # pages are reviewed together, before any build agent is dispatched. The verdict stays
        # planReview-only; findings are also recorded in `executing` and `review`, from what
        # dispatched agents report.
        SectionSpec("review", "Plan review", (
            _scalar("verdict", choices=_VERDICTS, description="""
                The review outcome for the decomposition and its agent-plan pages together.
                build-ready: the agents cover the signed-off design with no gaps and no overlaps, and
                each could be dispatched from its page alone without getting stuck. needs-changes: at
                least one blocking finding must be applied before dispatching. needs-human-decision:
                the work cannot proceed until a person settles a question. Approve unless there are
                serious gaps, meaning an expected change in the design no agent owns, two agents
                owning the same file, an acceptance criterion no brief delivers, a contract two
                agents need that nobody defines, or an agent task too vague to act on. Minor wording
                preferences are never a reason to withhold build-ready.
                """),
            _list("findings", element_fields=("issue", "severity", "action"), description="""
                Each one finding against the plan or the work: what is wrong, why it matters, its
                severity, and the action taken to apply it. Recorded at the plan review before any
                build agent is dispatched, and again while executing and in review, where the
                controller records what a dispatched agent reported or what integration turned up.
                blocking means an agent would build the wrong thing or two agents would collide;
                should-fix is real but survivable; nit is polish. Record the finding here AND make
                the edit its action names, so the plan and this record agree, and correct a finding
                in place with editFinding. Name the agent-plan page it applies to.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("summary"),
        set_prose_cmd("framing", field="why", name="setWhy", label="why"),
        *list_cmds("framing", field="outcomes",
                   add_args=(_text(), _text("kind", choices=_OUTCOME_KINDS),
                             _text("said", choices=_SAID_BY)),
                   editable=True),
        # The pick is recorded while the person is choosing and frozen once they have chosen.
        *list_cmds("decision", field="chosen", singular="chosenApproach",
                   add_args=(_text("approachId"), _text("takes", required=False)),
                   legal_in=("deciding",)),
        *list_cmds("contracts", add_args=(_text("name"), _text("owner"), _text("shape")),
                   editable=True),
        set_prose_cmd("scheduling"),
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
        # draft -> researching needs the intent, the why and the outcomes: research reads the repo
        # from the first and judges approaches against the others, which are written before any
        # approach exists so they cannot be fitted to one.
        transition_cmd("beginResearch", "draft -> researching",
                       requires=(("summary", "body"), ("framing", "why"), ("framing", "outcomes"))),
        transition_cmd("presentFindings", "researching -> deciding", guards=(
            ChildStateGuard("solution-research", ("reported",), "the research page must be reported"),)),
        transition_cmd("reopenResearch", "deciding -> researching", agency="either"),
        # The person picks the approach; the agent records it, then stops here.
        transition_cmd("chooseApproach", "deciding -> designing (human gate)", agency="human",
                       requires=(("decision", "chosen"), ("questions", "items"))),
        transition_cmd("submitDesign", "designing -> designReview", guards=(
            ChildStateGuard("solution-design", ("ready",), "the design page must be ready"),)),
        # Nothing is decomposed or built until the person signs the design off.
        transition_cmd("approveDesign", "designReview -> decomposition (human gate)", agency="human"),
        transition_cmd("requestDesignChanges", "designReview -> designing", agency="either"),
        transition_cmd("reconsiderApproach", "designReview -> deciding", agency="either"),
        # A design found unbuildable while splitting it goes back to be redesigned and signed off
        # again, rather than being patched in a brief.
        transition_cmd("reopenDesign", "decomposition -> designing",
                       legal_in=("decomposition", "planReview"), agency="either"),
        # decomposition -> planReview reviews the split AND the agent-plan pages together, before
        # any build agent is dispatched: the design must be sealed so the split cannot drift from
        # it, and no agent-plan page may still be in draft (page-status guards, store-checked).
        transition_cmd("submitPlan", "decomposition -> planReview",
                       requires=(("questions", "items"),),
                       guards=(ChildStateGuard("solution-design", ("sealed",),
                                               "the design page must be sealed"),
                               ChildStateGuard("agent-plan", _AGENT_PLANNED,
                                               "every agent-plan page must be marked ready"))),
        # planReview -> executing requires a verdict to have been recorded (the review happened).
        # `build-ready` is the signal to proceed; `needs-changes` should `reviseDecomposition`
        # instead. The verdict's VALUE is a soft guide (requires only checks presence).
        transition_cmd("approvePlan", "planReview -> executing", requires=(("review", "verdict"),)),
        transition_cmd("reviseDecomposition", "planReview -> decomposition (send the plan back)"),
        # executing -> review is guarded on every agent-plan page having been accepted (a
        # page-status guard over the epic's agent-plan children, checked in the store).
        transition_cmd("submitForReview", "executing -> review", guards=(
            ChildStateGuard("agent-plan", ("accepted",), "every agent must be accepted"),)),
        transition_cmd("reopenDecomposition", "executing -> decomposition"),
        transition_cmd("requestChanges", "review -> executing", agency="either"),
        # `ship` is a human gate AND is guarded: every child feature-brief must itself be `shipped`
        # (a page-status guard over the epic's NON-pinned children, checked in the store).
        transition_cmd("ship", "review -> shipped (human gate)", agency="human", guards=(
            ChildStateGuard("feature-brief", ("shipped",),
                            "every child feature-brief must be shipped"),)),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "researching", "deciding", "designing", "designReview",
                                 "decomposition", "planReview", "executing", "review")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Epic",
        initial="draft",
        states=("draft", "researching", "deciding", "designing", "designReview", "decomposition",
                "planReview", "executing", "review", "shipped", "abandoned"),
        terminal_states=("shipped", "abandoned"),
        status_guidance=(
            ("draft", EPIC_DRAFT),
            ("researching", RESEARCHING),
            ("deciding", DECIDING),
            ("designing", DESIGNING),
            ("designReview", DESIGN_REVIEW),
            ("decomposition", DECOMPOSITION),
        ),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(HUMAN_REACH_FIELD, ("deciding", "designReview", "review"),
                              HUMAN_REACH_DESC, HUMAN_REACH_LABEL),
    ),
    auto_children=(AutoChildSpec("solution-research"), AutoChildSpec("solution-design")),
)


# An agent-plan page may only be marked ready once its epic is dispatching agents: researching or
# designing for the research and design agents, decomposition or later for the build agents - not
# while the epic is still in `draft`, while the person is deciding or signing off, nor once
# `abandoned`. Enforced in the store.
_EPIC_DISPATCHING = ParentStateGuard(
    parent_type="epic",
    required_statuses=("researching", "designing", "decomposition", "planReview", "executing",
                       "review", "shipped"),
    message="the epic must be researching, designing, or in decomposition or later",
)


# Tiers rather than model ids: an id rots between releases, and a stale enum rejects valid input.
_MODEL_TIERS = ("cheap", "standard", "capable")


# Seeded into every agent-plan page as its first section and written by no command: who writes
# this page.
_AGENT_PLAN_NOTICE = """
    This page is one dispatched agent's whole assignment, and its page id is the agent's id. The
    controller - the session that created the epic above it - writes the assignment, task and
    reporting contract, links the pages the agent works on, and is the only one to run markReady,
    reopen, accept or redispatch here. The dispatched agent creates the worktree named here, if one
    is named, and works only in it, runs start on this page as its first command, adds a report as
    each step lands, and ends with finish or block. It writes only this page and the pages this page
    links to with works-on - the epic's solution-research or solution-design page, or the
    feature-briefs it builds with their child pages - and never runs a command on the epic or on
    another agent's page.
    """


_AGENT_PLAN = PageType(
    tag="agent-plan",
    name="Agent plan",
    description=(
        "One subagent an epic dispatches: its role, capability, exact task and the worktree it "
        "creates, linked to the pages it works on - the epic's research or design page, or the "
        "feature-briefs it builds. Its page id is the agent's id, and the agent reports back onto "
        "this page as it starts and works. Created by the controller as a direct child of its epic."
    ),
    sections=(
        SectionSpec("notice", "Agent notice", (
            _prose("body", description="Agent notice fixed text.", fixed=_AGENT_PLAN_NOTICE),
        )),
        SectionSpec("assignment", "Assignment", (
            _scalar("role", description="""
                What this agent is, named as a role a reader recognises - researcher, research judge,
                designer, design reviewer, implementer, integration reviewer. One agent-plan page is
                one dispatch, so the role describes this run rather than a definition shared with
                other agents.
                """),
            _scalar("capability", choices=_MODEL_TIERS, description="""
                The model tier this agent is dispatched on. Name it on every agent: an omitted tier
                silently inherits the session's most capable and most expensive model. Use cheap for
                mechanical single-file work whose content is already written down, standard for
                research, multi-file integration and judgement, and capable for design, architecture
                and final review. A judge or reviewer runs at the tier of the work it checks.
                """),
            _scalar("worktree", description="""
                The git worktree this agent creates and works in, by name. Give every agent that
                edits code a different one: two agents in one checkout overwrite each other's edits.
                An agent that only reads code - a researcher, a judge, a designer or a design
                reviewer - names none.
                """),
        )),
        SectionSpec("task", "Task", (
            _prose("body", description="""
                The exact work this agent does, written for a fresh agent with no history: it is
                handed this page id and nothing of the controller's context. Say which slice of the
                epic it owns and what done looks like, name the shared contracts it touches by their
                id on the epic, and add only the decisions it needs that the pages it works on cannot
                tell it. Link each page it works on with addLink role works-on - the epic's
                solution-research or solution-design page, or each feature-brief it builds - and each
                agent-plan page that must be accepted before it starts with role depends-on. Point
                at large artifacts by file path rather than pasting them.
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
                       parent_guards=(_EPIC_DISPATCHING,)),
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
)


# The research and design pages are pinned children of the epic, created with it and each kept
# waiting until the epic reaches the stage that is theirs: research while it is researching,
# design while it is designing. Sealing the design waits for the person's sign-off. Enforced in
# the store.
_EPIC_RESEARCHING = ParentStateGuard(
    parent_type="epic",
    required_statuses=("researching",),
    message="the epic must be researching",
)
_EPIC_DESIGNING = ParentStateGuard(
    parent_type="epic",
    required_statuses=("designing",),
    message="the epic must be designing",
)
_EPIC_IN_DECOMPOSITION = ParentStateGuard(
    parent_type="epic",
    required_statuses=("decomposition",),
    message="the epic must be in decomposition, after the person approved the design",
)

# The judge's and reviewer's verdict: a page goes forward or goes back, nothing in between.
_JUDGE_VERDICTS = ("pass", "revise")
_JUDGE_SEVERITIES = ("blocking", "minor")
_SIDES = ("pure", "effectful")
# How far a recon entry can be trusted: opened, followed from something opened, or neither.
_BASES = ("observed", "inferred", "assumed")


_SOLUTION_RESEARCH = PageType(
    tag="solution-research",
    name="Solution research",
    description=(
        "The delegated research and brainstorming step of an epic: a research agent reads the "
        "codebase and outside sources and returns grounded facts, two or three candidate "
        "approaches and a digest, so the controller reads the digest instead of doing the research "
        "itself. A judge agent checks it before the person sees it. Auto-created as a child of an "
        "epic; architecture documents how the system is shaped today instead."
    ),
    sections=(
        SectionSpec("understanding", "Understanding", (
            _prose("body", description="""
                The epic's ask restated in your own words from its summary and framing: what is
                wanted, for whom, and why. Where your restatement and the ask diverge, say so; that
                gap is the first question for the person.
                """),
        )),
        SectionSpec("components", "Components", (
            _list("items", element_fields=("name", "role", "side", "basis"), description="""
                Each one file, module or subsystem the work would read or change, named in name as a
                real path. role says what it does today and why it exists; side is pure or effectful
                - I/O, storage, network, clock, randomness; basis is observed when you opened it,
                inferred when it follows from something you opened, assumed when neither. Reach each
                by following callers and imports, not by matching names: a guessed component sends
                every approach down the wrong path, and a missed one is work no agent owns.
                """),
        )),
        SectionSpec("constraints", "Constraints", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one hard requirement any approach must respect, its exact value copied from the
                file that declares it, which you name: version floors, dependency limits, naming and
                copy rules, platform and performance targets. basis is observed when you read the
                value there, inferred or assumed otherwise, so a guess is not later spent as a fact.
                """),
        )),
        SectionSpec("conflicts", "Conflicts", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one collision with what already exists: code here that already does part of
                this, an interface an approach would break, or a competing in-flight change, named by
                file or page with what has to give, and its basis - observed, inferred or assumed.
                If you searched and found none, add one element saying where you looked.
                """),
        )),
        SectionSpec("documentation", "Documentation", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one pasta doc, architecture page or decision record covering the area this
                touches, and the part of it any approach would make stale, so reconciling it once the
                work lands is mechanical, with its basis - observed when you opened the page. If
                there is none, say where you looked.
                """),
        )),
        SectionSpec("priorArt", "Prior art", (
            _list("items", element_fields=("name", "finding", "bearing"), description="""
                Each one outside source you actually opened, through a source this workspace allows:
                a library, an upstream document, a known pattern, a comparable project, named in
                name. finding is what it says or does; bearing is what it means for this epic, such
                as an approach it makes cheap or a pitfall it warns of. If nothing outside bears on
                an internal change, add one element saying what you checked.
                """),
        )),
        SectionSpec("approaches", "Approaches", (
            _list("items", element_fields=("name", "sketch", "tradeoffs", "fit", "predicts",
                                           "falsifier", "recommended"),
                  description="""
                Each one of the two or three ways of building this that survived your culling,
                concrete enough to picture in sketch: which components change, what is new, how data
                moves, citing the component paths above. tradeoffs is what it costs and what it buys;
                fit is how it serves the why and the outcomes on the epic and avoids its anti-goals.
                predicts is an observation that should hold if the approach is right, and falsifier
                the observation that would show it wrong; an approach nothing could falsify is a
                preference, not an approach. Set recommended on exactly one and say why in its fit.
                Two approaches that differ only in naming are one approach. Correct an approach in
                place with editApproach: the epic's chosen approach points at its id.
                """),
        )),
        SectionSpec("dropped", "Dropped approaches", (
            _list("items", element_fields=("name", "reason"), description="""
                Each alternative you generated and culled, with what ruled it out: it works against
                the why, the code rules it out, or a kept approach dominates it. This is what stops
                'did you consider X' once the design is drawn. When there is genuinely one sensible
                way, the others and why they do not fit go here.
                """),
        )),
        SectionSpec("questions", "Questions for the person", (
            _list("items", element_fields=("text", "why", "changes"), description="""
                Each one question neither the epic nor the codebase answers and only the person can
                settle, asked as a single decidable question in their terms. why is what you hope to
                learn; changes names the approach it rules in or out, or what it changes in what gets
                built. Anything you could settle by reading further is not a question here.
                """),
        )),
        SectionSpec("digest", "Digest", (
            _prose("body", description="""
                At most 200 words, the only part of this page the controller reads by default: the
                ask as you understood it, the three facts that most shape the choice, each approach
                in one line with the recommendation marked, and how many questions wait. Write it
                last, from the page, so it never says anything the page does not.
                """),
        )),
        # Written by the judge, a fresh agent that did not write this page, in `judging` only.
        SectionSpec("review", "Judge review", (
            _scalar("verdict", choices=_JUDGE_VERDICTS, description="""
                pass only when the sampled entries marked observed checked out on reading, the
                approaches are real alternatives grounded in the recon, each with a falsifier that
                could actually be observed, and the digest matches the page; revise otherwise. Set it afresh on every pass, as the judge -
                never as the agent that wrote the page.
                """),
            _list("findings", element_fields=("issue", "severity"), description="""
                Each one problem the judge found: what is wrong and where on the page, with severity
                blocking when an approach rests on a false fact or a wrong component, and minor
                otherwise. Minor findings alone are never a reason to revise.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("understanding"),
        *list_cmds("components", add_args=(_text("name"), _text("role"), _text("side", choices=_SIDES),
                                          _text("basis", choices=_BASES))),
        *list_cmds("constraints", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("conflicts", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("documentation", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("priorArt", label="prior art", add_args=(_text("name"), _text("finding"), _text("bearing"))),
        # Editable so a revised approach keeps the id the epic's chosen approach points at.
        *list_cmds("approaches", singular="approach",
                   add_args=(_text("name"), _text("sketch"), _text("tradeoffs"), _text("fit"),
                             _text("predicts"), _text("falsifier"), _boolean("recommended", required=False)),
                   editable=True),
        *list_cmds("dropped", singular="droppedApproach", label="dropped approach",
                   add_args=(_text("name"), _text("reason"))),
        *list_cmds("questions", add_args=(_text(), _text("why"), _text("changes"))),
        set_prose_cmd("digest"),
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_JUDGE_VERDICTS,
                       legal_in=("judging",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_JUDGE_SEVERITIES)),
                   legal_in=("judging",)),
        transition_cmd("begin", "waiting -> investigating", parent_guards=(_EPIC_RESEARCHING,)),
        transition_cmd("submitForJudging", "investigating -> judging", requires=(
            ("understanding", "body"),
            ("components", "items"),
            ("constraints", "items"),
            ("conflicts", "items"),
            ("documentation", "items"),
            ("priorArt", "items"),
            ("approaches", "items"),
            ("dropped", "items"),
            ("digest", "body"),
        )),
        # `report` requires only that a verdict was recorded; a `revise` verdict should `revise`.
        transition_cmd("report", "judging -> reported", requires=(("review", "verdict"),)),
        transition_cmd("revise", "judging -> investigating (send the research back)"),
        # A reported page reopens only when the epic has gone back to researching.
        transition_cmd("reopen", "reported -> investigating", parent_guards=(_EPIC_RESEARCHING,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SolutionResearch",
        initial="waiting",
        states=("waiting", "investigating", "judging", "reported"),
        terminal_states=("reported",),
        status_guidance=(
            ("investigating", INVESTIGATING),
            ("judging", JUDGING),
        ),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(GROUNDING_TOOL_FIELD, ("investigating",), GROUNDING_TOOL_DESC,
                              GROUNDING_TOOL_LABEL),
        WorkspaceGuidanceSpec(RESEARCH_SOURCES_FIELD, ("investigating",), RESEARCH_SOURCES_DESC,
                              RESEARCH_SOURCES_LABEL),
    ),
)


_BUILDER_QUESTION_FSM = ElementFSMSpec(
    name="BuilderQuestion",
    initial="open", states=("open", "resolved"),
    transitions=(("resolve", "open", "resolved", "agent"),),
    checkmark_done="resolved",
)

_DECIDED_BY = ("person", "proposal")
_CHANGE_KINDS = ("create", "modify", "delete")
_CHECK_OUTCOMES = ("nothing-important-left", "questions-raised")
_PILES = ("answered", "minor", "theirs")


_SOLUTION_DESIGN = PageType(
    tag="solution-design",
    name="Solution design",
    description=(
        "The delegated design step of an epic: a design agent turns the approach the person chose "
        "into a design a builder could plan from without asking anyone, a reviewer agent reads it "
        "cold as that builder, and the person then signs it off on the epic. Auto-created as a "
        "child of an epic; a feature-spec designs one feature-brief instead."
    ),
    sections=(
        SectionSpec("intent", "Intent", (
            _blocks("body", block_kinds=standard_blocks(), description="""
                The why, then the goals, non-goals and anti-goals, copied from the epic's framing
                with each proposal still marked as one. The builder reads only this page, so it must
                stand without the epic; copy rather than paraphrase, because a reworded goal is a
                different goal.
                """),
        )),
        SectionSpec("approach", "Approach", (
            _prose("chosen", description="""
                The approach the person picked on the epic, restated in full from its research
                sketch and grown into what will actually be built. For a hybrid, say what comes
                from which approach.
                """),
            _list("alternatives", element_fields=("name", "tradeoff", "whyNot"), description="""
                Each other approach from the research page, what it would have traded, and in whyNot
                why it lost, in the person's reason where they gave one. This is what keeps the
                choice from being reopened during the build.
                """),
        )),
        SectionSpec("strategy", "Solution strategy", (
            _blocks("body", block_kinds=standard_blocks(), description="""
                How the chosen approach works: the parts, what each is responsible for, how data and
                control move between them, and where pure logic ends and effects begin. Use a
                heading per part, a code block for any shape and a table where parts are compared.
                Cite the research page's component paths for anything that exists today, and write
                for a builder who never saw the research.
                """),
        )),
        SectionSpec("decisions", "Decisions", (
            _list("items", element_fields=("decision", "alternatives", "reason", "by"), description="""
                Each one choice that shapes what gets built, stated in the active voice, with the
                alternatives weighed, the reason this one won, and by: person when they decided it,
                proposal when you did. A default the person never heard is one they could not
                reject, so every call of yours is here marked proposal.
                """),
        )),
        SectionSpec("interfaces", "Interfaces", (
            _list("items", element_fields=("name", "shape"), description="""
                Each one interface the design introduces or changes, with its exact signature or data
                shape written out in shape: argument and return types, fields and their types, error
                cases. 'Returns the config' is not a shape. These become the epic's shared contracts
                at decomposition, so a vague one is a collision between two agents later. If the
                design adds none, say so in one element.
                """),
        )),
        SectionSpec("changes", "Expected changes", (
            _list("items", element_fields=("path", "change", "why"), description="""
                Each one file or module that will be created, modified or deleted (change), with why.
                An existing path must appear in the research page's components; a new one names
                where it will live. The work is split into feature-briefs along these, so a missing
                one is work no agent owns.
                """),
        )),
        SectionSpec("criteria", "Acceptance criteria", (
            _list("items", element_fields=("text", "verify"), description="""
                Each one observable thing that is true when the epic is done, and in verify how a
                reviewer checks it: the command, the test, the screen. Cover every goal and guard
                every anti-goal. Each feature-brief delivers some of these, so one nobody can verify
                is one nobody delivers.
                """),
        )),
        SectionSpec("builder", "Left to the builder", (
            _list("items", element_fields=("text",), description="""
                Each one choice the design deliberately leaves to the builder because any sensible
                answer works, such as an internal helper's name or a file split. Naming them stops a
                builder mistaking them for gaps and a reviewer flagging them. If nothing is left, say
                so in one element.
                """),
        )),
        # The builder check: the reviewer adds questions and sets the outcome in `checking`; the
        # designer resolves or escalates them.
        SectionSpec("check", "Builder check", (
            _scalar("outcome", choices=_CHECK_OUTCOMES, description="""
                Set by the reviewer afresh on every pass, after reading this page cold as the
                builder who must plan from it: nothing-important-left, or questions-raised when it
                added builder questions.
                """),
            _list("questions", element_fields=("question", "why", "pile", "resolution", "needsHuman",
                                               "status"),
                  element_fsm=_BUILDER_QUESTION_FSM, description="""
                Each one question the reviewer would still need answered before planning, where a
                wrong guess would change the build, with why. The designer resolves each into a pile:
                answered when the page, the epic or the research already say (put the answer into the
                design), minor when a sensible builder could settle it (settle it as a proposal
                decision), or theirs when only the person can answer. Escalate a theirs question
                while it waits on them, and resolve it only once its answer is on the epic, naming
                that epic question's id in resolution.
                """),
        )),
        SectionSpec("digest", "Digest", (
            _prose("body", description="""
                At most 200 words for the controller to put in front of the person: what will be
                built in two sentences, the decisions marked proposal they should check, and what is
                left to the builder. Write it last; it is what the person reads before opening the
                page to sign it off.
                """),
        )),
        # Written by the reviewer, a fresh agent that did not write the design, in `checking` only.
        SectionSpec("review", "Design review", (
            _scalar("verdict", choices=_JUDGE_VERDICTS, description="""
                pass only when the strategy is clear, every decision has its reason and rejected
                alternatives, the expected changes agree with the research page's components, every
                criterion is verifiable, and nothing is built that no outcome asked for; revise
                otherwise. Set it afresh on every pass, as the reviewer - never as the designer.
                """),
            _list("findings", element_fields=("issue", "severity"), description="""
                Each one problem with the design: where it is, why it matters to a builder, and
                severity blocking or minor. Minor findings alone are never a reason to revise.
                """),
        )),
    ),
    commands=(
        *blocks_cmds("intent", remove_name="removeIntentBlock", remove_desc="remove an intent block",
                     reorder_name="reorderIntentBlock",
                     reorder_desc="move an intent block to an anchored position (precedingId guards a stale read)"),
        set_prose_cmd("approach", field="chosen", name="setChosenApproach", label="chosen approach"),
        *list_cmds("approach", field="alternatives",
                   add_args=(_text("name"), _text("tradeoff"), _text("whyNot"))),
        *blocks_cmds("strategy", remove_name="removeStrategyBlock", remove_desc="remove a strategy block",
                     reorder_name="reorderStrategyBlock",
                     reorder_desc="move a strategy block to an anchored position (precedingId guards a stale read)"),
        *list_cmds("decisions", add_args=(_text("decision"), _text("alternatives"), _text("reason"),
                                          _text("by", choices=_DECIDED_BY)),
                   editable=True),
        *list_cmds("interfaces", add_args=(_text("name"), _text("shape")), editable=True),
        *list_cmds("changes", add_args=(_text("path"), _text("change", choices=_CHANGE_KINDS), _text("why"))),
        *list_cmds("criteria", singular="criterion", add_args=(_text(), _text("verify"))),
        *list_cmds("builder", singular="builderChoice", label="choice left to the builder",
                   add_args=(_text(),)),
        set_scalar_cmd("check", "outcome", name="setCheckOutcome", label="builder-check outcome",
                       choices=_CHECK_OUTCOMES, legal_in=("checking",)),
        *list_cmds("check", field="questions", singular="builderQuestion", label="builder question",
                   add_args=(_text("question"), _text("why")), legal_in=("checking",)),
        *element_cmds("check", field="questions", singular="builderQuestion", marks=(
            ("resolveBuilderQuestion", "resolve", "resolve a builder question into its pile (open -> resolved)",
             (_text("pile", choices=_PILES), _text("resolution"))),)),
        set_element_field_cmd("check", field="questions", singular="builderQuestion",
                              name="escalateBuilderQuestion", const=("needsHuman", True),
                              description="flag a builder question as awaiting a human"),
        set_prose_cmd("digest"),
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_JUDGE_VERDICTS,
                       legal_in=("checking",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_JUDGE_SEVERITIES)),
                   legal_in=("checking",)),
        transition_cmd("begin", "waiting -> drafting", parent_guards=(_EPIC_DESIGNING,)),
        transition_cmd("submitForCheck", "drafting -> checking", requires=(
            ("intent", "body"),
            ("approach", "chosen"),
            ("approach", "alternatives"),
            ("strategy", "body"),
            ("decisions", "items"),
            ("interfaces", "items"),
            ("changes", "items"),
            ("criteria", "items"),
            ("builder", "items"),
            ("digest", "body"),
        )),
        # `markReady` requires only that the check ran and a verdict was recorded; a `revise`
        # verdict should `revise`.
        transition_cmd("markReady", "checking -> ready", requires=(("check", "outcome"), ("review", "verdict"))),
        transition_cmd("revise", "checking -> drafting (send the design back)"),
        # ready and sealed are both terminal, so what the person signs off and what is built from
        # cannot drift; either reopens only when the epic has gone back to designing.
        transition_cmd("reopen", "ready -> drafting", legal_in=("ready", "sealed"),
                       parent_guards=(_EPIC_DESIGNING,)),
        transition_cmd("seal", "ready -> sealed (frozen for the build)", parent_guards=(_EPIC_IN_DECOMPOSITION,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SolutionDesign",
        initial="waiting",
        states=("waiting", "drafting", "checking", "ready", "sealed"),
        terminal_states=("ready", "sealed"),
        status_guidance=(
            ("drafting", DRAFTING),
            ("checking", CHECKING),
        ),
    ),
)
