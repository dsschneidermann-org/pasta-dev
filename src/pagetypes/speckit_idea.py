"""The `speckit-idea` page type: GitHub Spec Kit's idea assessment as one page.

It starts in prepare, where the constitution is read and updated; after that each status is one
`/speckit-assess-*` skill. Field descriptions are Spec Kit's own words (github/spec-kit at f201054,
MIT), with only marks and line breaks changed for reading; the notice maps the files and skills that
text names onto this page.
"""

from __future__ import annotations

from ._stage_guidance import (
    SPECKIT_PREPARE,
    SPECKIT_CLARIFYING,
    SPECKIT_DECIDE,
    SPECKIT_DEFINE,
    SPECKIT_INTAKE,
    SPECKIT_RESEARCH,
    SPECKIT_SHAPE,
    SPECKIT_VERDICT_REVIEW,
)
from ._workspace_guidance import SPECKIT_CONSTITUTION_DESC, SPECKIT_CONSTITUTION_FIELD, SPECKIT_CONSTITUTION_LABEL
from .core.args import _boolean, _text
from .core.commands import (
    add_link_cmd,
    element_cmds,
    list_cmds,
    set_element_field_cmd,
    set_prose_cmd,
    set_scalar_cmd,
    set_title_cmd,
    transition_cmd,
    transition_on_add_cmd,
)
from .core.fields import SectionSpec, _list, _prose, _scalar
from .core.pagetype import PageType
from .core.specs import ElementFSMSpec, FSMSpec, WorkspaceGuidanceSpec

# Only the user settles a question, so both of its marks are human.
_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered", "deferred"),
    transitions=(("answer", "open", "answered", "human"),
                 ("defer", "open", "deferred", "human")),
)

_IDEA_TYPES = ("new-capability", "improvement", "fix", "exploration", "cost-saving", "compliance", "other")
_STAGES = ("intake", "research", "define", "shape")
_CONFIDENCE = ("high", "medium", "low")
_LENSES = ("users", "prior-art", "market", "data")
_BASIS = ("cited", "assumption")
_URL_POLICY = ("allowlisted", "confirmed-by-user", "auto-refused", "skipped")
_APPETITE = ("small", "medium", "large")
_VERDICTS = ("go", "needs-clarification", "kill")
_CRITERIA = ("Problem validity", "Evidence strength", "Value vs. inaction", "Feasibility / appetite",
             "Strategic fit", "Risk posture")
_RATINGS = ("strong", "adequate", "weak", "unknown")

# Each skill owns one part of the page, so its fields are locked to its status - and to clarifying,
# where the facts the user supplied are worked into whichever part they change.
_IN_INTAKE = ("intake", "clarifying")
_IN_RESEARCH = ("research", "clarifying")
_IN_DEFINE = ("define", "clarifying")
_IN_SHAPE = ("shape", "clarifying")
_IN_DECIDE = ("decide",)

_NOTICE = """
    The field instructions and stage guidance of this page are GitHub Spec Kit's own words. Spec Kit
    runs skills over files; this page stands in for both.

    A file it names is a section here: intake.md is Intake, research.md is Research, problem.md is
    Problem, concept.md is Concept, and decision.md is Decision and Handoff. A directory it names is
    this page. A skill it names is the status of that name, so /speckit-assess-define is the define
    status, and /speckit-specify is a new speckit-spec page. A [NEEDS CLARIFICATION: ...] marker is
    an open question on this page, flagged needsHuman, and only the user answers one.
    """

# Everything intake must hold before any later stage, whichever one the user goes to next.
_INTAKE_DONE = (("intake", "source"), ("intake", "type"), ("intake", "captured"), ("intake", "restated"),
                ("intake", "origin"), ("questions", "items"))


_SPECKIT_IDEA = PageType(
    tag="speckit-idea",
    name="Spec Kit idea",
    description=(
        "Spec Kit's idea assessment: decides whether an idea is worth building by capturing it, "
        "gathering evidence for and against it, defining the problem, shaping options and recording a "
        "go, needs-clarification or kill verdict the user accepts. Use it only when the user asks for "
        "a Spec Kit assessment; use a spike when the idea is worth doing and the open question is how, "
        "and a speckit-spec when it is already decided and ready to specify."
    ),
    sections=(
        SectionSpec("notice", "Spec Kit notice", (
            _prose("body", description="Spec Kit notice fixed text.", fixed=_NOTICE),
        )),
        SectionSpec("intake", "Intake", (
            _scalar("source", description="""
                **Source**: sanitized URL, "pasted text", or repo path

                Record in `intake.md`: the **sanitized URL** (strip any `user:password@` userinfo and
                drop query/fragment parameters that may carry credentials or signatures — e.g.
                `token`, `sig`, `signature`, `key`, `password`, `access_token`, and anything under a
                `X-Amz-*`/`Goog-*` signed-URL scheme; keep the scheme, host, and path), the parsed
                host (no redirect following), and the policy branch taken (`allowlisted` /
                `confirmed-by-user` / `auto-refused: <reason>`). Never persist a verbatim URL that may
                embed secrets. Never issue a preflight `HEAD` (or any) request to "see what it is" —
                that probe is itself the gated request.
                """),
            _scalar("type", choices=_IDEA_TYPES, description="""
                **Note the idea type** so downstream stages know what to weigh: `new-capability` |
                `improvement` | `fix` | `exploration` | `cost-saving` | `compliance` | `other`.
                """),
            _prose("captured", description="""
                **Capture the idea, redacting secrets.** Preserve the original wording (quoted) plus
                the source (URL, pasted block, or repo path) — but apply the same sanitization as the
                Source field *inside the quoted text too*: sanitize any credential-bearing URL and
                redact tokens, passwords, API keys, or cookies. Never persist a secret just because it
                appeared in the original.

                Quoted original, with any credential-bearing URL sanitized and secrets (tokens,
                passwords, keys, cookies) redacted. If a URL was fetched, include the title and a
                short excerpt; link the sanitized URL and record the URL Trust Policy branch taken.
                """),
            _prose("restated", description="""
                **Restate it in one or two neutral sentences.** What is being proposed, in plain
                language, without endorsing or dismissing it.
                """),
            _prose("origin", description="""
                **Record origin and context.** Who raised it, when, and any triggering event (a
                complaint, an outage, a sales ask, a strategy shift). Mark unknowns as
                `[NEEDS CLARIFICATION: …]`.
                - **Raised by**: <who / [NEEDS CLARIFICATION]>
                - **Trigger**: what prompted it / [NEEDS CLARIFICATION]
                """),
        )),
        SectionSpec("questions", "Open questions", (
            _list("items", element_fields=("text", "stage", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                **List first-glance unknowns** — the obvious questions that must be answered before
                anyone decides. Do not answer them here.

                **Carry forward open questions** from intake/research that must be resolved before or
                during specification.

                - **Blocking questions**: [NEEDS CLARIFICATION: …]
                - **Revisit stage**: intake | research | define | shape
                """),
        )),
        SectionSpec("research", "Research", (
            _scalar("confidence", choices=_CONFIDENCE, description="""
                **Evidence confidence (overall)**: high | medium | low
                """),
            _list("findings", element_fields=("lens", "text", "source", "confidence", "basis"), description="""
                Investigate the idea across these lenses. Skip any that genuinely do not apply, and
                mark gaps as `[NEEDS CLARIFICATION: …]` rather than guessing. **Every claim must carry
                a citation or be flagged as an assumption.**

                1. **Users & demand** — Who actually has this problem, and how strong is the signal?
                   Support tickets, interviews, usage data, requests. Distinguish *stated* wants from
                   *observed* behavior.
                2. **Prior art** — Has this been tried before, here or elsewhere? Existing internal
                   features, past specs/decisions in `.specify/`, competitor products, open-source
                   alternatives. Why did prior attempts succeed or fail?
                3. **Market & context** — Trends, alternatives users cope with today, the cost of
                   doing nothing.
                4. **Data & constraints** — Relevant metrics, volumes, compliance/legal factors,
                   platform limits.
                5. **Evidence quality** — For each finding, tag confidence `high | medium | low` and
                   whether it is `cited` (source given) or `assumption` (no source).

                <finding> — [source: <url/system> | ASSUMPTION] (confidence: high/medium/low)
                """),
            _list("against", element_fields=("text", "source"), description="""
                the strongest reasons this may not be worth building — [source]

                Include an **Evidence Against the Idea** section every time — if you cannot find any,
                say so explicitly; do not omit it.
                """),
            _list("sources", element_fields=("url", "host", "policy"), description="""
                Record each source's **sanitized URL** (strip `user:password@` userinfo and drop
                credential/signature query parameters, per the intake policy), parsed host, and policy
                branch in `research.md`. Never persist a verbatim URL that may embed secrets.

                <sanitized URL> (host: <host>, policy: allowlisted/confirmed-by-user/auto-refused)
                """),
        )),
        SectionSpec("problem", "Problem", (
            _prose("statement", description="""
                **State the problem** in one or two sentences: who is affected, what hurts today,
                under what conditions, and why it matters now. Keep it in the *problem space* — no
                features, no architecture.
                """),
            _list("users", element_fields=("who", "effect"), description="""
                **Identify users and stakeholders.** Users experience the problem; stakeholders
                decide, fund, or are impacted. Cite research where available; mark invented entries
                `[NEEDS CLARIFICATION: …]`.

                **Users**: <persona> — <how they are affected>
                """),
            _list("stakeholders", element_fields=("role", "interest"), description="""
                **Identify users and stakeholders.** Users experience the problem; stakeholders
                decide, fund, or are impacted. Cite research where available; mark invented entries
                `[NEEDS CLARIFICATION: …]`.

                **Stakeholders**: <role> — <interest / decision power>
                """),
            _list("goals", element_fields=("text",), description="""
                **Set goals** — the outcomes that would make solving this worthwhile.
                """),
            _list("nonGoals", element_fields=("text",), description="""
                **Set non-goals** — what is explicitly out of scope, to bound the work and prevent
                creep.
                """),
            _list("metrics", element_fields=("text", "baseline"), description="""
                **Define success metrics** — how you would know it worked. Prefer measurable signals;
                use qualitative ones only when necessary, and label them as such.

                <measurable signal> (baseline: <current value / unknown>)
                """),
            _prose("inaction", description="""
                **Establish a baseline** — what happens if nothing is built (the cost of inaction).
                This is what `/speckit-assess-decide` weighs against.
                """),
        )),
        SectionSpec("concept", "Concept", (
            _list("options", element_fields=("name", "sketch", "appetite", "tradeoffs", "rabbitHoles"), description="""
                **Generate 2–3 distinct options**, spanning the trade-off space. Always include a
                lightweight "smallest thing that could work" option and, where relevant, a "do nothing
                / buy instead of build" option. Each option:
                - **Sketch**: one paragraph describing the approach at concept level (what the user
                  experiences / what changes), not how it is engineered.
                - **Appetite**: a rough size — `small` (days) | `medium` (weeks) | `large` (months) —
                  as a budget, not an estimate.
                - **Trade-offs**: what it wins and what it sacrifices; key risks and unknowns.
                - **Rabbit holes**: the parts most likely to blow up scope, so
                  `/speckit-assess-decide` sees them.
                """),
            _scalar("recommended", description="""
                **Recommended option**: <name> | none

                It is a valid outcome to recommend that **no** option is worth building; say so rather
                than manufacturing a winner.
                """),
            _prose("recommendation", description="""
                **Recommend one option** with a short rationale tied to the problem's goals and
                metrics — or explicitly recommend *not proceeding* if no option clears the bar.
                """),
            _list("outOfScope", element_fields=("text",), description="""
                **Bound the concept**: restate what is explicitly out of scope for the recommended
                option (inherited from non-goals plus anything newly excluded).
                """),
            _list("assumptions", element_fields=("text",), description="""
                **List the assumptions** the recommendation depends on, so they can be validated
                during specification.
                """),
        )),
        SectionSpec("decision", "Decision", (
            _scalar("verdict", choices=_VERDICTS, description="""
                **Reach a verdict**:
                - **go** — the idea is worth specifying. Requires problem validity `adequate`+,
                  **evidence strength `adequate`+ (never `weak` or `unknown`)**, and a recommended
                  concept option. If evidence is `weak`/`unknown`, the verdict is
                  `needs-clarification`, not `go`.
                - **needs-clarification** — promising but blocked on specific unknowns. List exactly
                  what must be answered and which stage to revisit.
                - **kill** — not worth building now. State the decisive reason plainly (weak problem,
                  better alternative exists, cost > value, out of scope, superseded).
                """),
            _list("scorecard", element_fields=("criterion", "rating", "justification"), description="""
                **Score the idea** against explicit criteria, each rated
                `strong | adequate | weak | unknown` with a one-line justification drawn from the
                artifacts:
                - **Problem validity** — is the problem real and worth solving? (from `problem.md` +
                  `research.md`)
                - **Evidence strength** — how well-supported, vs. assumption-driven? (from
                  `research.md`)
                - **Value vs. cost of inaction** — does solving it beat doing nothing? (from
                  `problem.md`)
                - **Feasibility / appetite fit** — is there a credible option within a sane appetite?
                  (from `concept.md`)
                - **Strategic fit** — does it align with the project's constitution/goals, if known?
                - **Risk posture** — are the major risks understood and acceptably mitigated? Rate
                  with the same positive polarity as the other criteria: `strong` = key risks
                  identified and credibly mitigated; `weak` = serious, unmitigated risk. (from all
                  artifacts)
                """),
            _prose("rationale", description="""
                **Record the rationale** so the decision is auditable months later. Any `unknown`
                score must be acknowledged, not glossed.

                The call and why, in a short paragraph. Reference the scorecard.
                """),
        )),
        SectionSpec("handoff", "Handoff to specify", (
            _prose("summary", description="""
                **Define the handoff (go only)**: summarize what `/speckit-specify` should receive —
                the problem statement, the recommended option, in/out of scope, success metrics, and
                open questions carried forward.

                - **Problem**: <one-line problem statement>
                - **Chosen approach**: <recommended concept option>
                - **In scope / out of scope**: <summary>
                - **Success metrics**: <summary>
                - **Carried-forward open questions**: <list>
                """),
        )),
        SectionSpec("clarifications", "Facts supplied", (
            _list("facts", element_fields=("stage", "text"), description="""
                you can supply the missing facts and ask the agent to revise the scorecard, rationale,
                verdict, or handoff.

                When you add evidence, keep the source and confidence tags the research stage already
                uses (`ASSUMPTION` vs cited claims). Do not invent citations.
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("intake", "source", legal_in=_IN_INTAKE),
        set_scalar_cmd("intake", "type", choices=_IDEA_TYPES, legal_in=_IN_INTAKE),
        set_prose_cmd("intake", field="captured", name="setCaptured", label="captured idea", legal_in=_IN_INTAKE),
        set_prose_cmd("intake", field="restated", name="setRestated", label="restated idea", legal_in=_IN_INTAKE),
        set_prose_cmd("intake", field="origin", name="setOrigin", legal_in=_IN_INTAKE),
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _text("stage", choices=_STAGES), _boolean("needsHuman", required=False))),
        *element_cmds("questions", agency="human", marks=(
            ("answerQuestion", "answer", "answer a question in the user's words (open -> answered)",
             (_text("answer"),)),
            ("deferQuestion", "defer", "defer a question the user leaves open (open -> deferred)"))),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        set_scalar_cmd("research", "confidence", label="evidence confidence", choices=_CONFIDENCE,
                       legal_in=_IN_RESEARCH),
        *list_cmds("research", field="findings", editable=True, legal_in=_IN_RESEARCH,
                   add_args=(_text("lens", choices=_LENSES), _text(), _text("source"),
                             _text("confidence", choices=_CONFIDENCE), _text("basis", choices=_BASIS))),
        *list_cmds("research", field="against", singular="evidenceAgainst",
                   label="piece of evidence against the idea", legal_in=_IN_RESEARCH,
                   add_args=(_text(), _text("source"))),
        *list_cmds("research", field="sources", legal_in=_IN_RESEARCH,
                   add_args=(_text("url"), _text("host"), _text("policy", choices=_URL_POLICY))),
        set_prose_cmd("problem", field="statement", name="setProblemStatement", label="problem statement",
                      legal_in=_IN_DEFINE),
        *list_cmds("problem", field="users", legal_in=_IN_DEFINE, add_args=(_text("who"), _text("effect"))),
        *list_cmds("problem", field="stakeholders", legal_in=_IN_DEFINE,
                   add_args=(_text("role"), _text("interest"))),
        *list_cmds("problem", field="goals", legal_in=_IN_DEFINE, add_args=(_text(),)),
        *list_cmds("problem", field="nonGoals", label="non-goal", legal_in=_IN_DEFINE, add_args=(_text(),)),
        *list_cmds("problem", field="metrics", label="success metric", legal_in=_IN_DEFINE,
                   add_args=(_text(), _text("baseline"))),
        set_prose_cmd("problem", field="inaction", name="setInaction", label="cost of inaction",
                      legal_in=_IN_DEFINE),
        *list_cmds("concept", field="options", editable=True, legal_in=_IN_SHAPE,
                   add_args=(_text("name"), _text("sketch"), _text("appetite", choices=_APPETITE),
                             _text("tradeoffs"), _text("rabbitHoles"))),
        set_scalar_cmd("concept", "recommended", label="recommended option", legal_in=_IN_SHAPE),
        set_prose_cmd("concept", field="recommendation", name="setRecommendation", label="recommendation",
                      legal_in=_IN_SHAPE),
        *list_cmds("concept", field="outOfScope", label="out-of-scope item", legal_in=_IN_SHAPE,
                   add_args=(_text(),)),
        *list_cmds("concept", field="assumptions", label="assumption to validate", legal_in=_IN_SHAPE,
                   add_args=(_text(),)),
        set_scalar_cmd("decision", "verdict", choices=_VERDICTS, legal_in=_IN_DECIDE),
        *list_cmds("decision", field="scorecard", singular="score", editable=True, legal_in=_IN_DECIDE,
                   add_args=(_text("criterion", choices=_CRITERIA), _text("rating", choices=_RATINGS),
                             _text("justification"))),
        set_prose_cmd("decision", field="rationale", name="setRationale", legal_in=_IN_DECIDE),
        # Written with the verdict when it is a go, and still writable at the gate that needs it.
        set_prose_cmd("handoff", field="summary", name="setHandoff", label="handoff",
                      legal_in=("decide", "verdictReview")),
        # The gate below records the fact it was sent back with; the rest are added while refining.
        *list_cmds("clarifications", field="facts", label="supplied fact", remove=False,
                   legal_in=("clarifying",), add_args=(_text("stage", choices=_STAGES), _text())),
        transition_cmd("proceed", "prepare -> intake"),
        transition_cmd("beginResearch", "intake -> research", requires=_INTAKE_DONE),
        transition_cmd("skipResearch", "intake -> define (human gate)", agency="human", requires=_INTAKE_DONE),
        transition_cmd("beginDefine", "research -> define",
                       requires=(("research", "confidence"), ("research", "findings"), ("research", "against"))),
        transition_cmd("beginShape", "define -> shape",
                       requires=(("problem", "statement"), ("problem", "users"), ("problem", "stakeholders"),
                                 ("problem", "goals"), ("problem", "nonGoals"), ("problem", "metrics"),
                                 ("problem", "inaction"))),
        transition_cmd("beginDecide", "shape -> decide",
                       requires=(("concept", "options"), ("concept", "recommended"),
                                 ("concept", "recommendation"), ("concept", "outOfScope"),
                                 ("concept", "assumptions"))),
        transition_cmd("submitVerdict", "decide -> verdictReview",
                       requires=(("decision", "verdict"), ("decision", "scorecard"), ("decision", "rationale"))),
        # The three ways out of the verdict gate are the user's.
        transition_cmd("acceptGo", "verdictReview -> closed (human gate)", agency="human",
                       requires=(("handoff", "summary"),)),
        transition_cmd("confirmKill", "verdictReview -> abandoned (human gate)", agency="human"),
        transition_on_add_cmd("supplyFacts", "verdictReview -> clarifying", section="clarifications",
                              field="facts", agency="human",
                              description="record a fact the user supplied AND go back to refining",
                              add_args=(_text("stage", choices=_STAGES), _text())),
        transition_cmd("reviseVerdict", "verdictReview -> decide", agency="either"),
        transition_cmd("redecide", "clarifying -> decide"),
        # An idea abandoned before it had a verdict never went through every stage, so it stays closed.
        transition_cmd("reopen", "closed or abandoned -> clarifying", legal_in=("closed", "abandoned"),
                       agency="human", requires=(("decision", "verdict"),)),
        transition_cmd("abandon", "drop the idea -> abandoned", agency="human",
                       legal_in=("prepare", "intake", "research", "define", "shape", "decide", "verdictReview",
                                 "clarifying")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SpeckitIdea",
        initial="prepare",
        states=("prepare", "intake", "research", "define", "shape", "decide", "verdictReview", "clarifying",
                "closed", "abandoned"),
        terminal_states=("closed", "abandoned"),
        status_guidance=(
            ("prepare", SPECKIT_PREPARE),
            ("intake", SPECKIT_INTAKE),
            ("research", SPECKIT_RESEARCH),
            ("define", SPECKIT_DEFINE),
            ("shape", SPECKIT_SHAPE),
            ("decide", SPECKIT_DECIDE),
            ("verdictReview", SPECKIT_VERDICT_REVIEW),
            ("clarifying", SPECKIT_CLARIFYING),
        ),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(SPECKIT_CONSTITUTION_FIELD, ("prepare", "decide"), SPECKIT_CONSTITUTION_DESC, SPECKIT_CONSTITUTION_LABEL),
    ),
)
