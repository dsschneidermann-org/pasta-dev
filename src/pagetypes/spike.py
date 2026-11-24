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
    RefCheck,
    WorkspaceGuidanceSpec,
)
from .core.args import _boolean, _code_block, _paragraph_runs, _text
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
)
from .core.fields import SectionSpec, _blocks, _list, _prose, _scalar
from .core.pagetype import PageType

_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered"),
    transitions=(("answer", "open", "answered", "agent"),),
)

# A reaction stays open until a later proof answers it, or the user withdraws it.
_REACTION_FSM = ElementFSMSpec(
    name="Reaction",
    initial="open", states=("open", "shown", "dropped"),
    transitions=(("show", "open", "shown", "agent"),
                 ("drop", "open", "dropped", "agent")),
    checkmark_done="shown",
)


# Seeded into every spike as its first section and written by no command: who may edit this page.
_CONTROLLER_NOTICE = """
    This spike is the controller's page. Only the controlling agent - the session that created this
    spike and dispatches its agents - runs commands on it. The research is done by dispatched
    agents: each investigator is handed one agent-plan page, a child of this spike, works from that
    page, reports back onto it, and writes only that page and the solution-investigation page it
    links to with works-on. It never edits this spike or another agent's page. The controller reads
    the investigations' digests rather than the whole pages, and the user opens and judges the
    proofs. Nothing is designed, decomposed or built from this page: once the user has picked, it
    ends by creating one feature-brief next to it for another agent to plan.
    """


_SPIKE = PageType(
    tag="spike",
    name="Spike (solution research)",
    description=(
        "Works out how to build an idea before anything is planned: one investigator subagent per "
        "solution direction works it out on a solution-investigation page of its own and builds a "
        "proof the user can open, the user picks a direction, and the spike hands off a single "
        "feature-brief created next to it for another agent to specify, plan and build. Pick it "
        "whenever the user is unsure about the outcome - what it should be, or which way gets "
        "there - without waiting for them to ask for research; when they know both, create a "
        "feature-brief, and for work that splits into parts that each ship on their own, an epic."
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
                feature-brief carries each on as a sentence of its summary, and a vague one
                becomes a criterion nobody can check. Refine one in place with editOutcome as the
                conversation settles it.
                """),
            _prose("scenario", description="""
                One real case from the user's own data that shows the problem today: which workspace,
                files, dates or records, and what they see now. Every proof runs on it, so the
                directions compare on the same thing and the user judges them on something they
                recognise. An invented case proves nothing to them; ask for a real one.
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
        SectionSpec("tryout", "Try-out", (
            _list("reactions", element_fields=("investigationId", "said", "status"),
                  element_fsm=_REACTION_FSM, description="""
                Each one thing the user said after opening a proof, in their words, with the page id
                of the solution-investigation whose proof it was. The controller's own opinion of a
                proof is not a reaction. Mark one shown once a later proof answers it, or dropped when
                the user withdraws it; a reaction that changes what a direction must show goes back to
                its investigator with research reopened.
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
            _scalar("proof", description="""
                The candidate the user picked, as path@commit, exactly as they ran it: the proof file
                of the chosen investigation and the commit it was shown at. The feature-brief's summary
                names it as a reference to plan from, so whoever plans the brief opens the same proof
                the user judged.
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
        set_prose_cmd("framing", field="scenario", name="setScenario", label="scenario"),
        # Editable so a refined direction keeps the id its investigation page records.
        *list_cmds("directions", add_args=(_text("name"), _text("scope")), editable=True),
        # What the user said about a proof, and what they picked, are recorded while they are choosing
        # and frozen once they have chosen.
        *list_cmds("tryout", field="reactions", legal_in=("deciding",),
                   add_args=(_text("investigationId"), _text("said"))),
        *element_cmds("tryout", field="reactions", singular="reaction", legal_in=("deciding",), marks=(
            ("markReactionShown", "show", "mark a reaction shown - a later proof answers it"),
            ("dropReaction", "drop", "drop a reaction the user withdrew"))),
        set_scalar_cmd("decision", "chosen", name="setChosenApproach", label="chosen approach",
                       legal_in=("deciding",)),
        set_scalar_cmd("decision", "proof", name="setChosenProof", label="chosen proof",
                       legal_in=("deciding",)),
        # Questions carry the same surface as a feature-brief's: askQuestion (no remove), an answer
        # transition that also writes the answer, and an escalate that raises the needsHuman flag.
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", marks=(
            ("answerQuestion", "answer", "answer a question (open -> answered)", (_text("answer"),)),)),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        # draft -> researching needs the intent, the why, the outcomes, the scenario and the
        # directions: each direction's investigation reads the repo from the first, runs its proof on
        # the scenario and is compared against the outcomes, which are written before any direction is
        # investigated so they cannot be fitted to one.
        transition_cmd("beginResearch", "draft -> researching",
                       requires=(("summary", "body"), ("framing", "why"), ("framing", "outcomes"),
                                 ("framing", "scenario"), ("directions", "items"))),
        # A ruled-out direction needs no proof, so it does not hold the user's choice up.
        transition_cmd("presentFindings", "researching -> deciding", guards=(
            ChildStateGuard("solution-investigation", ("reported", "ruledOut"),
                            "every investigation must be reported or ruled out"),)),
        transition_cmd("reopenResearch", "deciding -> researching", agency="either"),
        # A human picks the approach after opening the proofs; the agent records what they said and
        # what they picked, then stops here. No feature-brief is created before this gate.
        transition_cmd("chooseApproach", "deciding -> briefing (human gate)", agency="human",
                       requires=(("tryout", "reactions"), ("decision", "chosen"), ("decision", "proof"),
                                 ("questions", "items"))),
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
# What running the proof shows of an outcome; "could be reached" is not a verdict.
_FIT_VERDICTS = ("shown", "partly", "not-shown", "not-visible")


_SOLUTION_INVESTIGATION = PageType(
    tag="solution-investigation",
    name="Solution investigation",
    description=(
        "One delegated investigation of a spike: an investigator agent takes one solution direction "
        "from the spike, works out how it would be built in this codebase, builds a proof the user "
        "can open, and returns a verdict and a digest, so the controller reads the digest instead of "
        "doing the research itself. Created by the controller as a child of its spike, one per "
        "direction; architecture documents how the system is shaped today instead."
    ),
    sections=(
        SectionSpec("direction", "Direction", (
            _list("items", element_fields=("directionId",), description="""
                The direction this page investigates, added once by the element id of a direction on
                the spike's directions list, copied from your agent-plan task; an id that names no
                direction on this spike is refused. Several investigations may take the same
                direction. An idea that is not a variant of it is a question for the user, not a
                second direction here.
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
            _prose("falsifier", description="""
                The observation that would show this direction wrong for this codebase: a behaviour,
                a measurement, a call path that does not exist. Write a second half for the user: what
                they would see in the proof if the direction did not solve their why. A direction
                nothing could falsify is a preference, not a direction.
                """),
            _scalar("result", choices=_TEST_RESULTS, description="""
                held when you checked for the falsifier and it did not occur, falsified when it did,
                untested when neither reading nor a spike could check it. The evidence says which
                and how.
                """),
            _blocks("evidence", block_kinds=(_paragraph_runs(), _code_block()), description="""
                How the test was run: what you read, or what you ran in your spike worktree, naming
                the worktree and commit, and any outside source it rests on. Put each command and its
                output in a code block and each file path in an inline code run. Spike code is never
                integrated; it exists only to make this observation.
                """),
        )),
        SectionSpec("proof", "Proof", (
            _list("items", element_fields=("name", "path", "shows"), description="""
                Each one proof the user opens or runs to see this direction handle the scenario, in
                the form your task names: path is the file inside your spike worktree, ready to use as
                it is, with the data it needs already in it. When the direction has nothing to look at,
                it shows the values before and after. shows names what to look for and what to do with
                it. Correct one in place with editProof.
                """),
            _scalar("commit", description="""
                The commit on your spike branch that holds every proof listed, so the user, and whoever
                plans the feature-brief, open exactly what you tested. Update it whenever a proof
                changes.
                """),
            _prose("data", description="""
                The real data the proof runs on and how you captured it, then everything simulated,
                hard-coded or left out, so the user never judges a stand-in as the real thing. A proof
                on invented data does not show an outcome.
                """),
            _blocks("howItWorks", block_kinds=(_paragraph_runs(), _code_block()), description="""
                What building the proof taught about building the feature: for each part, the real file
                and function it stands for, what can be kept, what has to be rewritten, and what
                surprised you. Name each path in an inline code run. This is what the user learns the
                build from, and what whoever plans the brief starts from.
                """),
        )),
        SectionSpec("fit", "Outcomes shown", (
            _list("items", element_fields=("outcomeId", "verdict", "where"), description="""
                Each one spike outcome this direction bears on, added by its id, with the verdict from
                running the proof - shown, partly, not-shown, or not-visible when the proof has nothing
                that would show it - and where to look. You choose which outcomes belong here: an
                outcome this direction has nothing to do with is left out. A verdict comes from running
                the proof, so an outcome the direction could only reach is not shown.
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
            _list("items", element_fields=("text", "changes"), description="""
                Each one question neither the spike nor the codebase answers and only the user can
                settle, asked as a single decidable question in their terms. changes names what the
                answer changes for this direction - whether it stays viable, or what gets built.
                Anything you could settle by reading further is not a question here.
                """),
        )),
        SectionSpec("digest", "Digest", (
            _prose("body", description="""
                At most 150 words, the only part of this page the controller reads by default: the
                direction in one line, the facts that most shape it, its cost and caveats, the proofs'
                paths and what they simulate, how it fares on the outcomes it lists, the test result,
                the viability, and how many questions wait. Write it last, from the page, so it never
                says anything the page does not.
                """),
        )),
    ),
    commands=(
        # Checked against the parent spike's directions; nothing stops two investigations taking
        # the same one.
        *list_cmds("direction", add_args=(_text("directionId"),),
                   ref_check=RefCheck(arg="directionId", scope="parent", section="directions", field="items")),
        set_prose_cmd("sketch"),
        set_scalar_cmd("assessment", "cost", choices=_COSTS),
        set_prose_cmd("test", field="falsifier", name="setFalsifier", label="falsifier"),
        set_scalar_cmd("test", "result", choices=_TEST_RESULTS),
        *blocks_cmds("test", field="evidence", add_name="addEvidence",
                     remove_name="removeEvidenceBlock", remove_desc="remove an evidence block",
                     reorder_name="reorderEvidenceBlock",
                     reorder_desc="move an evidence block to an anchored position (precedingId guards a stale read)"),
        *list_cmds("proof", add_args=(_text("name"), _text("path"), _text("shows")), editable=True),
        set_scalar_cmd("proof", "commit", name="setProofCommit", label="proof commit"),
        set_prose_cmd("proof", field="data", name="setProofData", label="proof data"),
        *blocks_cmds("proof", field="howItWorks", add_name="addHowItWorks",
                     remove_name="removeHowItWorksBlock", remove_desc="remove a how-it-works block",
                     reorder_name="reorderHowItWorksBlock",
                     reorder_desc="move a how-it-works block to an anchored position (precedingId guards a stale read)"),
        # Checked against the parent spike's outcomes; which of them belong here is the investigator's
        # call, so nothing asks for one entry per outcome.
        *list_cmds("fit", add_args=(_text("outcomeId"), _text("verdict", choices=_FIT_VERDICTS),
                                    _text("where")),
                   ref_check=RefCheck(arg="outcomeId", scope="parent", section="framing", field="outcomes")),
        set_scalar_cmd("conclusion", "viability", choices=_VIABILITY),
        *list_cmds("questions", add_args=(_text(), _text("changes"))),
        set_prose_cmd("digest"),
        transition_cmd("begin", "waiting -> investigating", parent_guards=(_SPIKE_RESEARCHING,)),
        transition_cmd("report", "investigating -> reported", requires=(
            ("direction", "items"),
            ("sketch", "body"),
            ("assessment", "cost"),
            ("test", "falsifier"),
            ("test", "result"),
            ("test", "evidence"),
            ("proof", "items"),
            ("proof", "commit"),
            ("proof", "data"),
            ("proof", "howItWorks"),
            ("fit", "items"),
            ("conclusion", "viability"),
            ("digest", "body"),
        )),
        # A direction its falsifier killed ends here, with the test that killed it and no proof.
        transition_cmd("ruleOut", "investigating -> ruledOut", requires=(
            ("direction", "items"),
            ("test", "falsifier"),
            ("test", "result"),
            ("test", "evidence"),
            ("conclusion", "viability"),
            ("digest", "body"),
        )),
        # A reported or ruled-out page reopens only when the spike has gone back to researching.
        transition_cmd("reopen", "reported or ruledOut -> investigating", legal_in=("reported", "ruledOut"),
                       parent_guards=(_SPIKE_RESEARCHING,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SolutionInvestigation",
        initial="waiting",
        states=("waiting", "investigating", "reported", "ruledOut"),
        terminal_states=("reported", "ruledOut"),
        status_guidance=(("investigating", INVESTIGATING),),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(GROUNDING_TOOL_FIELD, ("investigating",), GROUNDING_TOOL_DESC,
                              GROUNDING_TOOL_LABEL),
    ),
)
