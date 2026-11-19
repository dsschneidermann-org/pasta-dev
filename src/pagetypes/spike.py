"""The `spike` page type and the `solution-investigation` pages created under it.

They are declared together because they are designed against each other rather than on their
own: the spike's gates read its investigations' statuses and the investigations' gates read the
spike's. The agent-plan pages a spike also dispatches are declared in agent_plan.py, since they
are reusable.
"""

from __future__ import annotations

from ._stage_guidance import (
    DECIDING,
    INVESTIGATING,
    RESEARCHING,
    SPIKE_DRAFT,
)
from ._workspace_guidance import (
    GROUNDING_TOOL_DESC,
    GROUNDING_TOOL_FIELD,
    GROUNDING_TOOL_LABEL,
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


# Seeded into every spike as its first section and written by no command: who may edit this page.
_CONTROLLER_NOTICE = """
    This spike is the controller's page. Only the controlling agent - the session that created this
    spike and dispatches its agents - runs commands on it. The research is done by dispatched
    agents: each investigator is handed one agent-plan page, a child of this spike, works from that
    page, reports back onto it, and writes only that page and the solution-investigation page it
    links to with works-on. It never edits this spike or another agent's page. The controller reads
    the investigations' digests rather than the whole pages. Nothing is designed, decomposed or built
    from this page: it ends by creating one feature-brief next to it for another agent to plan.
    """


_SPIKE = PageType(
    tag="spike",
    name="Spike (solution research)",
    description=(
        "Works out how to build an idea before anything is planned: one investigator subagent per "
        "solution direction works it out on a solution-investigation page of its own, the user "
        "picks a direction, and the spike hands off a single feature-brief created next to it for "
        "another agent to specify, plan and build. Use it when the approach is still open; when it "
        "is known, create a feature-brief, and for work that splits into parts that each ship on "
        "their own, an epic."
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
            _list("outcomes", element_fields=("text",), description="""
                Each one thing that must hold, stay out of scope, or never happen for this to count
                as a success, in the user's terms. Write them before research begins: the directions
                are compared against them, and outcomes written after the directions get fitted to
                them. Write each so a reviewer could tell whether the built result meets it: the
                feature-brief carries these on, and a vague one becomes a criterion nobody can
                check. Refine one in place with editOutcome as the conversation settles it.
                """),
        )),
        SectionSpec("directions", "Solution directions", (
            _list("items", element_fields=("name", "scope"), description="""
                Each one distinct kind of solution worth investigating, named in name, with scope
                saying what it would change or add and what it assumes, so the agent investigating
                it knows what to look for. Write them with the user from the summary, the why and
                the outcomes before any code is read. Two directions that would send an investigator
                to the same code with the same question are one. Each gets one solution-investigation
                page, which records this element's id; correct a direction in place with
                editDirection so the id holds.
                """),
        )),
        SectionSpec("decision", "Approach decision", (
            _scalar("chosen", description="""
                The page id of the solution-investigation page under this spike whose direction the
                user picked. A hybrid names the investigation it starts from, and the answer to the
                pick question says what it takes from the others. Record only a pick the user made,
                or, when they handed you the how, your recommendation, saying so in that answer. The
                feature-brief is created from exactly this.
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
        *list_cmds("framing", field="outcomes", add_args=(_text(),), editable=True),
        # Editable so a refined direction keeps the id its investigation page records.
        *list_cmds("directions", add_args=(_text("name"), _text("scope")), editable=True),
        # The pick is recorded while the user is choosing and frozen once they have chosen.
        set_scalar_cmd("decision", "chosen", name="setChosenApproach", label="chosen approach",
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
        # direction's investigation reads the repo from the first and is compared against the
        # outcomes, which are written before any direction is investigated so they cannot be
        # fitted to one.
        transition_cmd("beginResearch", "draft -> researching",
                       requires=(("summary", "body"), ("framing", "why"), ("framing", "outcomes"),
                                 ("directions", "items"))),
        transition_cmd("presentFindings", "researching -> deciding", guards=(
            ChildStateGuard("solution-investigation", ("reported",), "every investigation must be reported"),)),
        transition_cmd("reopenResearch", "deciding -> researching", agency="either"),
        # A human picks the approach, which also hands the spike off: the agent records the pick,
        # creates and links the feature-brief, then stops here. The link guard holds the gate until
        # that brief is linked, live and a feature-brief.
        transition_cmd("chooseApproach", "deciding -> handedOff (human gate)", agency="human",
                       requires=(("decision", "chosen"), ("questions", "items")), link_guards=(
            LinkGuard("created-feature", "feature-brief",
                      "the feature-brief this spike created must be linked with role created-feature"),)),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("draft", "researching", "deciding")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="Spike",
        initial="draft",
        states=("draft", "researching", "deciding", "handedOff", "abandoned"),
        terminal_states=("handedOff", "abandoned"),
        status_guidance=(
            ("draft", SPIKE_DRAFT),
            ("researching", RESEARCHING),
            ("deciding", DECIDING),
        ),
    ),
    # The stage in which the controller creates agent-plan pages and launches the agents.
    workspace_guidance=(
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

# Shared by every investigation of a spike, so the directions compare like with like.
_COSTS = ("small", "medium", "large")
_TEST_RESULTS = ("held", "falsified", "untested")
_VIABILITY = ("viable", "viable-with-caveats", "not-viable")


_SOLUTION_INVESTIGATION = PageType(
    tag="solution-investigation",
    name="Solution investigation",
    description=(
        "One delegated investigation of a spike: an investigator agent takes one solution direction "
        "from the spike, works out how it would be built in this codebase and tests it, and returns "
        "a verdict and a digest, so the controller reads the digest instead of doing the research "
        "itself. Created by the controller as a child of its spike, one per direction; architecture "
        "documents how the system is shaped today instead."
    ),
    sections=(
        SectionSpec("direction", "Direction", (
            _scalar("directionId", description="""
                The element id of the direction on the spike's directions list that this page
                investigates, copied from your agent-plan task. One page investigates one direction;
                an idea that is not a variant of it is a question for the user, not a second
                direction here.
                """),
        )),
        SectionSpec("sketch", "Sketch", (
            _prose("body", description="""
                How this direction would be built here, concrete enough to picture and to size:
                which files and modules change, named as real paths you opened, what is new, and how
                data moves. It is for choosing between directions, not the design: the chosen
                direction is specified later, in the feature-brief the spike hands off.
                """),
        )),
        SectionSpec("assessment", "Assessment", (
            _scalar("cost", choices=_COSTS, description="""
                The size of building this direction - small, medium or large - judged from the
                sketch. Every investigation of the spike uses the same three sizes, so the user
                compares like with like.
                """),
        )),
        SectionSpec("test", "Test", (
            _scalar("falsifier", description="""
                The observation that would show this direction wrong for this codebase: a behaviour,
                a measurement, a call path that does not exist. A direction nothing could falsify is
                a preference, not a direction.
                """),
            _scalar("result", choices=_TEST_RESULTS, description="""
                held when you checked for the falsifier and it did not occur, falsified when it did,
                untested when neither reading nor a spike could check it. The evidence says which
                and how.
                """),
            _prose("evidence", description="""
                How the test was run: what you read, or what you ran in your spike worktree with its
                command and output, naming the worktree and commit, and any outside source it rests
                on. Spike code is never integrated; it exists only to make this observation.
                """),
        )),
        SectionSpec("conclusion", "Conclusion", (
            _scalar("viability", choices=_VIABILITY, description="""
                Your verdict on this direction: viable, viable-with-caveats when it works only if a
                caveat named in the digest is accepted, or not-viable when the falsifier fired or
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
                direction in one line, the facts that most shape it, its cost and caveats, how it
                fares on each of the spike's outcomes, the test result, the viability, and how many
                questions wait. Write it last, from the page, so it never says anything the page
                does not.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("direction", "directionId"),
        set_prose_cmd("sketch"),
        set_scalar_cmd("assessment", "cost", choices=_COSTS),
        set_scalar_cmd("test", "falsifier"),
        set_scalar_cmd("test", "result", choices=_TEST_RESULTS),
        set_prose_cmd("test", field="evidence", name="setEvidence", label="evidence"),
        set_scalar_cmd("conclusion", "viability", choices=_VIABILITY),
        *list_cmds("questions", add_args=(_text(), _text("why"), _text("changes"))),
        set_prose_cmd("digest"),
        transition_cmd("begin", "waiting -> investigating", parent_guards=(_SPIKE_RESEARCHING,)),
        transition_cmd("report", "investigating -> reported", requires=(
            ("direction", "directionId"),
            ("sketch", "body"),
            ("assessment", "cost"),
            ("test", "falsifier"),
            ("test", "result"),
            ("test", "evidence"),
            ("conclusion", "viability"),
            ("digest", "body"),
        )),
        # A reported page reopens only when the spike has gone back to researching.
        transition_cmd("reopen", "reported -> investigating", parent_guards=(_SPIKE_RESEARCHING,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SolutionInvestigation",
        initial="waiting",
        states=("waiting", "investigating", "reported"),
        terminal_states=("reported",),
        status_guidance=(("investigating", INVESTIGATING),),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(GROUNDING_TOOL_FIELD, ("investigating",), GROUNDING_TOOL_DESC,
                              GROUNDING_TOOL_LABEL),
    ),
)
