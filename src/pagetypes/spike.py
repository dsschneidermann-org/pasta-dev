"""The `spike` page type and the `solution-investigation` pages created under it.

They are declared together because they are designed against each other rather than on their
own: the spike's gates read its investigations' statuses and the investigations' gates read the
spike's. The agent-plan pages a spike also dispatches are declared in agent_plan.py, since they
are reusable.
"""

from __future__ import annotations

from ._stage_guidance import (
    BRIEFING,
    DECIDING,
    INVESTIGATING,
    JUDGING,
    RESEARCHING,
    SPIKE_DRAFT,
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
    SUBAGENT_DISPATCH_DESC,
    SUBAGENT_DISPATCH_FIELD,
    SUBAGENT_DISPATCH_LABEL,
)
from .core.specs import (
    ChildStateGuard,
    ElementFSMSpec,
    FSMSpec,
    LinkGuard,
    ParentStateGuard,
    RefCheck,
    WorkspaceGuidanceSpec,
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
)
from .core.fields import SectionSpec, _list, _prose, _scalar
from .core.pagetype import PageType

_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)


_OUTCOME_KINDS = ("goal", "non-goal", "anti-goal")
_SAID_BY = ("user", "proposal")

# Seeded into every spike as its first section and written by no command: who may edit this page.
_CONTROLLER_NOTICE = """
    This spike is the controller's page. Only the controlling agent - the session that created this
    spike and dispatches its agents - runs commands on it. The research is done by dispatched
    agents: each investigator and the judge is handed one agent-plan page, a child of this spike,
    works from that page, reports back onto it, and writes only that page and the
    solution-investigation pages it links to with works-on. It never edits this spike or another
    agent's page. The controller reads the investigations' digests rather than the whole pages.
    Nothing is designed, decomposed or built from this page: it ends by creating one feature-brief
    next to it for another agent to plan.
    """


_SPIKE = PageType(
    tag="spike",
    name="Spike (solution research)",
    description=(
        "Works out how to build an idea before anything is planned: one investigator subagent per "
        "solution direction works it out on a solution-investigation page of its own, a judge "
        "subagent compares them, the user picks a direction, and the spike hands off a single "
        "feature-brief created next to it for another agent to specify, plan and build. Use it "
        "when the approach is still open; when it is known, create a feature-brief, and for work "
        "that splits into parts that each ship on their own, an epic."
    ),
    sections=(
        SectionSpec("notice", "Controller notice", (
            _prose("body", description="Controller notice fixed text.", fixed=_CONTROLLER_NOTICE),
        )),
        SectionSpec("summary", "Summary", (
            _prose("body", description="""
                The intent in a sentence or two: what you want to build and why it is worth building.
                Write it before any code is read, because each direction's investigator searches the
                repo from this line. State the outcome you want, not the implementation you imagine.
                """),
        )),
        SectionSpec("framing", "Framing", (
            _prose("why", description="""
                Why the user wants this, in their words: the problem it removes or what it makes
                possible, and why now. If they have not said, ask one open question with nothing to
                pick from; never infer it from the summary. Each investigation weighs its direction
                against this paragraph, so a guessed why yields directions that solve the wrong
                problem well.
                """),
            _list("outcomes", element_fields=("text", "kind", "said"), description="""
                Each one goal, non-goal or anti-goal, named in kind. An anti-goal is something that
                would make this a failure even if it technically works. Set said to user for an
                outcome the user stated and to proposal for one you filled in, and tell the user
                which outcomes are your proposals. Write them before research begins: every
                investigation assesses its direction against each one by id, and outcomes written
                after the directions get fitted to them. Write each so a reviewer could tell whether
                the built result meets it: the feature-brief carries these on, and a vague one
                becomes a criterion nobody can check.
                """),
        )),
        SectionSpec("directions", "Solution directions", (
            _list("items", element_fields=("name", "scope", "said"), description="""
                Each one distinct kind of solution worth investigating, named in name, with scope
                saying what it would change or add and what it assumes, so the agent investigating
                it knows what to look for. Write them with the user from the summary, the why and
                the outcomes before any code is read. Two directions that would send an investigator
                to the same code with the same question are one. Set said to user for a direction the
                user named and to proposal for one you added. Each gets one solution-investigation
                page, which records this element's id; correct a direction in place with
                editDirection so the id holds.
                """),
        )),
        SectionSpec("decision", "Approach decision", (
            _list("chosen", element_fields=("investigationId", "takes"), description="""
                The direction the user picked, by the page id of its solution-investigation page
                under this spike. Usually one element; a hybrid gets one per investigation it draws
                from, with what it takes from each in takes. Record only a pick the user made, or,
                when they handed you the how, your recommendation with takes saying it was your
                call. The feature-brief is created from exactly this.
                """),
        )),
        SectionSpec("questions", "Questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                Each one question only the user can settle, asked as a single decidable question in
                their terms rather than a topic: the investigations' questions and the approach pick
                all land here, so this list is the one record of what the user decided, and the ones
                that bear on the build are carried onto the feature-brief. Set needsHuman while it
                waits on them, and answer it here with their words once decided.
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
        # Editable so a refined direction keeps the id its investigation page records.
        *list_cmds("directions", add_args=(_text("name"), _text("scope"), _text("said", choices=_SAID_BY)),
                   editable=True),
        # The pick is recorded while the user is choosing and frozen once they have chosen.
        *list_cmds("decision", field="chosen", singular="chosenApproach",
                   add_args=(_text("investigationId"), _text("takes", required=False)),
                   legal_in=("deciding",)),
        # Questions carry the same surface as a feature-brief's: askQuestion (no remove), an answer
        # transition that also writes the answer, and an escalate that raises the needsHuman flag.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        # draft -> researching needs the intent, the why, the outcomes and the directions: each
        # direction's investigation reads the repo from the first and judges its direction against
        # the outcomes, which are written before any direction is investigated so they cannot be
        # fitted to one.
        transition_cmd("beginResearch", "draft -> researching",
                       requires=(("summary", "body"), ("framing", "why"), ("framing", "outcomes"),
                                 ("directions", "items"))),
        # The findings are presented once every investigation is reported and every agent the
        # spike dispatched has been accepted, so no run is still working while the user decides.
        transition_cmd("presentFindings", "researching -> deciding", guards=(
            ChildStateGuard("solution-investigation", ("reported",), "every investigation must be reported"),
            ChildStateGuard("agent-plan", ("accepted",), "every agent must be accepted"),)),
        transition_cmd("reopenResearch", "deciding -> researching", agency="either"),
        # A human picks the approach; the agent records it, then stops here.
        transition_cmd("chooseApproach", "deciding -> briefing (human gate)", agency="human",
                       requires=(("decision", "chosen"), ("questions", "items"))),
        # The spike hands off only once the feature-brief it created is linked, live and a
        # feature-brief (a link guard, checked in the store).
        transition_cmd("handOff", "briefing -> handedOff", link_guards=(
            LinkGuard("created-feature", "feature-brief",
                      "the feature-brief this spike created must be linked with role created-feature"),)),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "researching", "deciding", "briefing")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Spike",
        initial="draft",
        states=("draft", "researching", "deciding", "briefing", "handedOff", "abandoned"),
        terminal_states=("handedOff", "abandoned"),
        status_guidance=(
            ("draft", SPIKE_DRAFT),
            ("researching", RESEARCHING),
            ("deciding", DECIDING),
            ("briefing", BRIEFING),
        ),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(HUMAN_REACH_FIELD, ("deciding",), HUMAN_REACH_DESC, HUMAN_REACH_LABEL),
        # The stage in which the controller creates agent-plan pages and launches the agents.
        WorkspaceGuidanceSpec(SUBAGENT_DISPATCH_FIELD, ("researching",), SUBAGENT_DISPATCH_DESC,
                              SUBAGENT_DISPATCH_LABEL),
    ),
)


# The investigation pages are created under the spike, one per direction, and are kept waiting
# until it researches. Enforced in the store.
_SPIKE_RESEARCHING = ParentStateGuard(
    parent_type="spike",
    required_statuses=("researching",),
    message="the spike must be researching",
)

# The judge's verdict: a page goes forward or goes back, nothing in between.
_JUDGE_VERDICTS = ("pass", "revise")
_JUDGE_SEVERITIES = ("blocking", "minor")
_SIDES = ("pure", "effectful")
# How far a recon entry can be trusted: opened, followed from something opened, or neither.
_BASES = ("observed", "inferred", "assumed")
# Shared by every investigation of a spike, so the directions compare like with like.
_COSTS = ("small", "medium", "large")
_HOLDS = ("yes", "partly", "no")
_TEST_RESULTS = ("held", "falsified", "untested")
_VIABILITY = ("viable", "viable-with-caveats", "not-viable")


_SOLUTION_INVESTIGATION = PageType(
    tag="solution-investigation",
    name="Solution investigation",
    description=(
        "One delegated investigation of a spike: an investigator agent takes one solution direction "
        "from the spike, grounds it in the codebase and outside sources, works it out and tests it, "
        "and returns a verdict and a digest, so the controller reads the digest instead of doing the "
        "research itself. One judge agent checks every investigation of the spike side by side. "
        "Created by the controller as a child of its spike, one per direction; architecture "
        "documents how the system is shaped today instead."
    ),
    sections=(
        SectionSpec("understanding", "Understanding", (
            _prose("body", description="""
                The direction restated in your own words from the spike's summary, framing and this
                direction's scope: what it would build, and how that serves the why. Where the
                direction as written and the ask diverge, say so; that gap is the first question for
                the user.
                """),
        )),
        SectionSpec("direction", "Direction", (
            _scalar("directionId", description="""
                The element id of the direction on the spike's directions list that this page
                investigates, copied from your agent-plan task. One page investigates one direction;
                an idea that is not a variant of it is a question for the user, not a second
                direction here.
                """),
        )),
        SectionSpec("components", "Components", (
            _list("items", element_fields=("name", "role", "side", "basis"), description="""
                Each one file, module or subsystem this direction would read or change, named in name
                as a real path. role says what it does today and why it exists; side is pure or
                effectful - I/O, storage, network, clock, randomness; basis is observed when you
                opened it, inferred when it follows from something you opened, assumed when neither.
                Reach each by following callers and imports from where this direction lands, not by
                matching names: a guessed component sends the sketch down the wrong path, and a
                missed one is found mid-build.
                """),
        )),
        SectionSpec("constraints", "Constraints", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one hard requirement this direction must respect, its exact value copied from
                the file that declares it, which you name: version floors, dependency limits, naming
                and copy rules, platform and performance targets. basis is observed when you read the
                value there, inferred or assumed otherwise, so a guess is not later spent as a fact.
                """),
        )),
        SectionSpec("conflicts", "Conflicts", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one collision this direction would have with what already exists: code here that
                already does part of this, an interface it would break, or a competing in-flight
                change, named by file or page with what has to give, and its basis - observed,
                inferred or assumed. If you searched and found none, add one element saying where
                you looked.
                """),
        )),
        SectionSpec("documentation", "Documentation", (
            _list("items", element_fields=("text", "basis"), description="""
                Each one pasta doc, architecture page or decision record covering the area this
                direction touches, and the part of it this direction would make stale, so reconciling
                it once the work lands is mechanical, with its basis - observed when you opened the
                page. If there is none, say where you looked.
                """),
        )),
        SectionSpec("priorArt", "Prior art", (
            _list("items", element_fields=("name", "finding", "bearing"), description="""
                Each one outside source you actually opened, through a source this workspace allows:
                a library, an upstream document, a known pattern, a comparable project, named in
                name. finding is what it says or does; bearing is what it means for this direction,
                such as a part it makes cheap or a pitfall it warns of. If nothing outside bears on
                an internal change, add one element saying what you checked.
                """),
        )),
        SectionSpec("sketch", "Sketch", (
            _prose("body", description="""
                How this direction would be built here, concrete enough to picture: which components
                change, what is new, how data moves, citing the component paths above. It is for
                choosing between directions, not the design: the chosen direction is specified
                later, in the feature-brief the spike hands off.
                """),
        )),
        SectionSpec("variants", "Dropped variants", (
            _list("items", element_fields=("name", "reason"), description="""
                Each variant of this direction you generated and culled, with what ruled it out: it
                works against the why, the code rules it out, or the variant you sketched dominates
                it. This is what stops 'did you consider X' once the direction is picked. When there
                was one sensible way to build this direction, say so in one element.
                """),
        )),
        SectionSpec("assessment", "Assessment", (
            _prose("tradeoffs", description="""
                What this direction costs and what it buys: complexity added, code touched, risk
                carried, and what it makes easy or hard later, written to be read beside the spike's
                other investigations.
                """),
            _scalar("cost", choices=_COSTS, description="""
                The size of building this direction - small, medium or large - judged from the
                components it changes and what is new. Every investigation of the spike uses the same
                three sizes, so the user compares like with like.
                """),
            _list("fit", element_fields=("outcomeId", "holds", "note"), description="""
                One element per outcome on the spike, by its element id in outcomeId. holds is yes
                when the outcome holds if this direction is built - a goal met, a non-goal kept out,
                an anti-goal avoided - and partly or no otherwise; note says why, citing the sketch
                or a recon entry. An outcome left out is one the user cannot compare the directions
                on.
                """),
        )),
        SectionSpec("test", "Test", (
            _scalar("predicts", description="""
                An observation that should hold if this direction is right for this codebase: a
                behaviour, a measurement, a call path that exists.
                """),
            _scalar("falsifier", description="""
                The observation that would show this direction wrong. A direction nothing could
                falsify is a preference, not a direction.
                """),
            _scalar("result", choices=_TEST_RESULTS, description="""
                held when you checked for the falsifier and it did not occur, falsified when it did,
                untested when neither reading nor a spike could check it. The evidence says which
                and how.
                """),
            _prose("evidence", description="""
                How the test was run: what you read, or what you ran in your spike worktree with its
                command and output, naming the worktree and commit. Spike code is never integrated;
                it exists only to make this observation.
                """),
        )),
        SectionSpec("conclusion", "Conclusion", (
            _scalar("viability", choices=_VIABILITY, description="""
                Your verdict on this direction: viable, viable-with-caveats when it works only if a
                caveat named in the tradeoffs is accepted, or not-viable when the falsifier fired or
                the code rules it out. Make the strongest honest case for the direction and say
                not-viable when that is what you found.
                """),
        )),
        SectionSpec("questions", "Questions for the user", (
            _list("items", element_fields=("text", "why", "changes"), description="""
                Each one question neither the spike nor the codebase answers and only the user can
                settle, asked as a single decidable question in their terms. why is what you hope to
                learn; changes names what the answer changes for this direction - whether it stays
                viable, or what gets built. Anything you could settle by reading further is not a
                question here.
                """),
        )),
        SectionSpec("digest", "Digest", (
            _prose("body", description="""
                At most 150 words, the only part of this page the controller reads by default: the
                direction in one line, the facts that most shape it, its cost, how it fares on the
                outcomes, the test result, the viability, and how many questions wait. Write it
                last, from the page, so it never says anything the page does not.
                """),
        )),
        # Written by the judge, a fresh agent that wrote none of the spike's investigations, in
        # `judging` only.
        SectionSpec("review", "Judge review", (
            _scalar("verdict", choices=_JUDGE_VERDICTS, description="""
                pass only when the sampled entries marked observed checked out on reading, the page
                stays inside its direction, the sketch is grounded in the recon, every outcome is
                assessed, the test result is backed by its evidence, and the digest matches the
                page; revise otherwise. Set it afresh on every pass, as the judge - never as the
                agent that wrote the page.
                """),
            _list("findings", element_fields=("issue", "severity"), description="""
                Each one problem the judge found: what is wrong and where on the page, with severity
                blocking when the direction rests on a false fact or a wrong component, or states a
                fact that another investigation of the spike contradicts and the code bears the other
                out - name that page - and minor otherwise. Minor findings alone are never a reason
                to revise.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("understanding"),
        set_scalar_cmd("direction", "directionId"),
        *list_cmds("components", add_args=(_text("name"), _text("role"), _text("side", choices=_SIDES),
                                          _text("basis", choices=_BASES))),
        *list_cmds("constraints", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("conflicts", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("documentation", add_args=(_text(), _text("basis", choices=_BASES))),
        *list_cmds("priorArt", label="prior art", add_args=(_text("name"), _text("finding"), _text("bearing"))),
        set_prose_cmd("sketch"),
        *list_cmds("variants", add_args=(_text("name"), _text("reason"))),
        set_prose_cmd("assessment", field="tradeoffs", name="setTradeoffs", label="tradeoffs"),
        set_scalar_cmd("assessment", "cost", choices=_COSTS),
        # Checked against the parent spike's outcomes, so every investigation is assessed on the
        # same ones.
        *list_cmds("assessment", field="fit",
                   add_args=(_text("outcomeId"), _text("holds", choices=_HOLDS), _text("note")),
                   ref_check=RefCheck(arg="outcomeId", scope="parent", section="framing", field="outcomes")),
        set_scalar_cmd("test", "predicts"),
        set_scalar_cmd("test", "falsifier"),
        set_scalar_cmd("test", "result", choices=_TEST_RESULTS),
        set_prose_cmd("test", field="evidence", name="setEvidence", label="evidence"),
        set_scalar_cmd("conclusion", "viability", choices=_VIABILITY),
        *list_cmds("questions", add_args=(_text(), _text("why"), _text("changes"))),
        set_prose_cmd("digest"),
        set_scalar_cmd("review", "verdict", name="setReviewVerdict", choices=_JUDGE_VERDICTS,
                       legal_in=("judging",)),
        *list_cmds("review", field="findings", label="finding",
                   add_args=(_text("issue"), _text("severity", choices=_JUDGE_SEVERITIES)),
                   legal_in=("judging",)),
        transition_cmd("begin", "waiting -> investigating", parent_guards=(_SPIKE_RESEARCHING,)),
        transition_cmd("submitForJudging", "investigating -> judging", requires=(
            ("understanding", "body"),
            ("direction", "directionId"),
            ("components", "items"),
            ("constraints", "items"),
            ("conflicts", "items"),
            ("documentation", "items"),
            ("priorArt", "items"),
            ("sketch", "body"),
            ("variants", "items"),
            ("assessment", "tradeoffs"),
            ("assessment", "cost"),
            ("assessment", "fit"),
            ("test", "predicts"),
            ("test", "falsifier"),
            ("test", "result"),
            ("test", "evidence"),
            ("conclusion", "viability"),
            ("digest", "body"),
        )),
        # `report` requires only that a verdict was recorded; a `revise` verdict should `revise`.
        transition_cmd("report", "judging -> reported", requires=(("review", "verdict"),)),
        transition_cmd("revise", "judging -> investigating (send the investigation back)"),
        # A reported page reopens only when the spike has gone back to researching.
        transition_cmd("reopen", "reported -> investigating", parent_guards=(_SPIKE_RESEARCHING,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SolutionInvestigation",
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
