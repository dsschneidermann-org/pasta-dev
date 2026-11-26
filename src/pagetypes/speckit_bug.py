"""The `speckit-bug` page type: GitHub Spec Kit's bug triage as one page.

It starts in prepare, where the constitution is read and updated. assess, fix and test are then the
three `/speckit-bug-*` skills, and the two review statuses are where the user decides. Field
descriptions are Spec Kit's own words (github/spec-kit at f201054, MIT), with only marks and line
breaks changed for reading; the notice maps the files and skills that text names onto this page.
"""

from __future__ import annotations

from ._stage_guidance import (
    SPECKIT_ASSESS,
    SPECKIT_ASSESSMENT_REVIEW,
    SPECKIT_FIX,
    SPECKIT_PREPARE,
    SPECKIT_RESULT_REVIEW,
    SPECKIT_TEST,
)
from ._workspace_guidance import (
    SPECKIT_CONSTITUTION_DESC,
    SPECKIT_CONSTITUTION_FIELD,
    SPECKIT_CONSTITUTION_LABEL,
    GROUNDING_TOOL_DESC,
    GROUNDING_TOOL_FIELD,
    GROUNDING_TOOL_LABEL,
    MERGE_PROCESS_DESC,
    MERGE_PROCESS_FIELD,
    MERGE_PROCESS_LABEL,
    TESTING_TOOL_DESC,
    TESTING_TOOL_FIELD,
    TESTING_TOOL_LABEL,
)
from .core.args import _boolean, _text, standard_blocks
from .core.commands import (
    add_link_cmd,
    blocks_cmds,
    element_cmds,
    list_cmds,
    set_element_field_cmd,
    set_prose_cmd,
    set_scalar_cmd,
    set_title_cmd,
    transition_cmd,
)
from .core.fields import SectionSpec, _blocks, _list, _prose, _scalar
from .core.pagetype import PageType
from .core.specs import ElementFSMSpec, FSMSpec, WorkspaceGuidanceSpec

# Only the user settles a question, so both of its marks are human.
_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered", "deferred"),
    transitions=(("answer", "open", "answered", "human"),
                 ("defer", "open", "deferred", "human")),
)

_VERDICTS = ("valid", "likely valid, needs reproduction", "invalid")
_SEVERITIES = ("critical", "high", "medium", "low")
_CONFIDENCE = ("high", "medium", "low")
_FIX_STATUSES = ("applied", "partial", "not-applied")
_CHANGES = ("added", "modified", "removed")
_RESULTS = ("verified", "partial", "failed")
_OUTCOMES = ("pass", "fail", "skipped", "not-run")

# Each skill writes only its own report: the assessment is the contract the fix is held to, so it is
# frozen once assessed, and the fix and the verification are each written in their own status.
_IN_ASSESS = ("assess",)
_IN_FIX = ("fix",)
_IN_TEST = ("test",)

_NOTICE = """
    The field instructions and stage guidance of this page are GitHub Spec Kit's own words. Spec Kit
    runs skills over files; this page stands in for both.

    A file it names is part of this page: assessment.md is Report through Open questions, fix.md is
    Fix, and test.md is Verification. A directory it names is this page. A skill it names is the
    status of that name, so /speckit-bug-fix is the fix status. A [NEEDS CLARIFICATION: ...] marker is
    an open question on this page, flagged needsHuman, and only the user answers one.
    """


_SPECKIT_BUG = PageType(
    tag="speckit-bug",
    name="Spec Kit bug",
    description=(
        "Spec Kit's bug triage: assesses a report against the code, has the user approve the "
        "assessment before any code changes, applies the fix, and records a verified, partial or failed "
        "result the user closes on. Use it only when the user asks for Spec Kit bug fixing; otherwise "
        "use a bug-report."
    ),
    sections=(
        SectionSpec("notice", "Spec Kit notice", (
            _prose("body", description="Spec Kit notice fixed text.", fixed=_NOTICE),
        )),
        SectionSpec("report", "Report", (
            _scalar("source", description="""
                **Source**: <URL or "pasted text">

                In every case, record in `assessment.md`:

                - The verbatim URL the user supplied.
                - The host parsed from that URL (no redirect following — see the rule above).
                - Which branch of the policy was taken: `allowlisted` / `confirmed-by-user` /
                  `auto-refused: <reason>`.
                """),
            _prose("body", description="""
                Quoted/condensed report content. If a URL was fetched, include the title and a short
                excerpt; link the URL.

                Capture the verbatim source (URL or pasted block) so it can be quoted in the report.
                """),
        )),
        SectionSpec("triage", "Triage", (
            _scalar("verdict", choices=_VERDICTS, description="""
                Decide whether the report is:
                - **Valid** — reproducible or clearly grounded in code behavior.
                - **Likely valid, needs reproduction** — plausible but unverified.
                - **Invalid / not a bug** — misuse, expected behavior, duplicate, or out of scope.
                  State why.
                """),
            _scalar("severity", choices=_SEVERITIES, description="""
                Assign a severity (`critical`, `high`, `medium`, `low`) and a short rationale (user
                impact, blast radius, data risk, regression vs. long-standing).
                """),
            _prose("rationale", description="""
                a short rationale (user impact, blast radius, data risk, regression vs. long-standing)

                **Invalid / not a bug** — misuse, expected behavior, duplicate, or out of scope. State
                why.
                """),
        )),
        SectionSpec("symptom", "Symptom", (
            _prose("body", description="""
                Reproduce the bug in one or two sentences: what happens, what was expected, under
                which conditions.

                One or two sentences describing the observed behavior and the expected behavior.
                """),
        )),
        SectionSpec("reproduction", "Reproduction", (
            _list("steps", element_fields=("text",), description="""
                List concrete reproduction steps if discoverable; mark unknowns as
                `[NEEDS CLARIFICATION]` rather than guessing.

                Never invent reproduction steps or file paths that are not supported by either the
                report or the codebase.
                """),
        )),
        SectionSpec("cause", "Cause", (
            _list("codePaths", element_fields=("location", "why"), description="""
                - Search the codebase for the relevant symbols, file paths, error messages, log
                  strings, route names, or component identifiers mentioned in the report.
                - List the candidate files / functions / lines with brief justifications. Do not
                  exceed what the evidence supports.

                - `path/to/file.py:42` — <why>
                - `path/to/other.ts:func()` — <why>
                """),
            _prose("hypothesis", description="""
                One paragraph. State confidence: high / medium / low.
                """),
            _scalar("confidence", choices=_CONFIDENCE, description="""
                State confidence: high / medium / low.
                """),
        )),
        SectionSpec("remediation", "Remediation", (
            _prose("preferred", description="""
                Outline one preferred fix and, if non-obvious, one or two alternatives with
                trade-offs.

                **Preferred**: one or two paragraphs describing the change.
                """),
            _list("alternatives", element_fields=("text",), description="""
                **Alternatives** (optional):
                <alternative + trade-off>
                """),
            _list("files", element_fields=("path",), description="""
                Identify files to change and the shape of the change (without writing the patch yet —
                that is `/speckit-bug-fix`'s job).
                """),
            _list("tests", element_fields=("text",), description="""
                Call out tests that should exist or be added to lock the fix in.
                """),
            _list("risks", element_fields=("text",), description="""
                Flag risks: API breakage, migrations, performance, security, observability.
                """),
        )),
        SectionSpec("questions", "Open questions", (
            _list("items", element_fields=("text", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                Mark unknowns as [NEEDS CLARIFICATION: …].

                - [NEEDS CLARIFICATION: …]
                """),
        )),
        SectionSpec("fix", "Fix", (
            _scalar("status", choices=_FIX_STATUSES, description="""
                **Status**: applied | partial | not-applied
                """),
            _prose("summary", description="""
                One or two sentences describing what was changed and why.
                """),
            _list("changes", element_fields=("file", "change", "notes"), description="""
                | File | Change | Notes |
                |------|--------|-------|
                | `path/to/file.py` | <added / modified / removed> | <short note> |
                | `path/to/test_file.py` | added test | <short note> |
                """),
            _blocks("highlights", block_kinds=standard_blocks(), description="""
                Short, illustrative snippets of the most important hunks — not a full diff dump.
                """),
            _list("tests", element_fields=("test", "pins"), description="""
                Add or update the tests called out in the assessment so the bug cannot regress
                silently.

                `path/to/test_file.py::test_name` — <what it pins down>
                """),
            _list("verification", element_fields=("command", "result"), description="""
                - If the project has obvious test commands (e.g., `pytest`, `npm test`, `cargo test`),
                  run the tests that exercise the changed paths. Capture pass/fail and key output.
                - Do not run destructive or network-dependent suites without the user's consent.

                - Commands run: `<command>` → <result, brief>
                - Manual checks: what was verified by hand, if anything
                """),
            _list("deviations", element_fields=("text",), description="""
                Empty if none. Otherwise, list any places where the actual fix departed from the
                proposed remediation and why.
                """),
            _list("followUps", element_fields=("text",), description="""
                suggested cleanup, monitoring, doc update, etc.
                """),
        )),
        SectionSpec("verification", "Verification", (
            _scalar("result", choices=_RESULTS, description="""
                Mark the fix as:
                - **verified** — all critical checks pass and the original symptom no longer
                  reproduces.
                - **partial** — the original symptom is gone but unrelated regressions appeared, or
                  some checks are inconclusive.
                - **failed** — the symptom still reproduces or the regression suite is broken by the
                  fix.

                - Do not over-claim. If reproduction was not actually performed (e.g., the bug
                  required a production environment), say so explicitly.
                - Never mark a fix as `verified` based on tests alone if the original assessment
                  listed a reproduction that you did not actually exercise — downgrade to `partial`
                  and say so.
                """),
            _prose("summary", description="""
                One or two sentences: does the bug reproduce, did the fix hold, were any regressions
                found.
                """),
            _list("checks", element_fields=("check", "action", "outcome", "notes"), description="""
                | Check | Command / Action | Result | Notes |
                |-------|------------------|--------|-------|
                | Reproduction (post-fix) | <command or manual steps> | pass / fail / skipped / not-run | <short note> |
                | New / updated tests | `<command>` | pass / fail | <short note> |
                | Regression suite | `<command>` | pass / fail / skipped | <short note> |
                | Lint / type-check | `<command>` | pass / fail / skipped | <short note> |

                - Execute each planned check. Capture command, exit status, and a short excerpt of
                  relevant output (last few lines, or the failing assertion).
                - If a check is destructive, network-dependent, or expensive, skip it and record it as
                  `skipped` with a reason; do not run it without explicit user consent.
                - If you cannot run a check at all (missing tooling, no test framework configured),
                  record it as `not-run` with a reason instead of fabricating a result.
                """),
            _blocks("excerpts", block_kinds=standard_blocks(), description="""
                Short snippets of relevant output (e.g., final summary line of a test run, the failing
                assertion). Keep it tight — no full logs.
                """),
            _list("residualRisks", element_fields=("text",), description="""
                known limitation, environment not covered, etc.
                """),
            _prose("recommendation", description="""
                One paragraph. Examples:
                - "Close the bug — verified end-to-end."
                - "Hold — reproduction inconclusive; needs verification in staging."
                - "Reopen — symptom still reproduces; rerun `/speckit-bug-assess`."
                """),
        )),
    ),
    commands=(
        set_scalar_cmd("report", "source", legal_in=_IN_ASSESS),
        set_prose_cmd("report", legal_in=_IN_ASSESS),
        set_scalar_cmd("triage", "verdict", choices=_VERDICTS, legal_in=_IN_ASSESS),
        set_scalar_cmd("triage", "severity", choices=_SEVERITIES, legal_in=_IN_ASSESS),
        set_prose_cmd("triage", field="rationale", name="setRationale", legal_in=_IN_ASSESS),
        set_prose_cmd("symptom", legal_in=_IN_ASSESS),
        *list_cmds("reproduction", field="steps", label="reproduction step", legal_in=_IN_ASSESS,
                   add_args=(_text(),)),
        *list_cmds("cause", field="codePaths", label="suspected code path", legal_in=_IN_ASSESS,
                   add_args=(_text("location"), _text("why"))),
        set_prose_cmd("cause", field="hypothesis", name="setHypothesis", label="root cause hypothesis",
                      legal_in=_IN_ASSESS),
        set_scalar_cmd("cause", "confidence", choices=_CONFIDENCE, legal_in=_IN_ASSESS),
        set_prose_cmd("remediation", field="preferred", name="setPreferredFix", label="preferred fix",
                      legal_in=_IN_ASSESS),
        *list_cmds("remediation", field="alternatives", label="alternative fix", legal_in=_IN_ASSESS,
                   add_args=(_text(),)),
        *list_cmds("remediation", field="files", singular="file", label="file likely to change",
                   legal_in=_IN_ASSESS, add_args=(_text("path"),)),
        *list_cmds("remediation", field="tests", singular="testToAdd", label="test to add or update",
                   legal_in=_IN_ASSESS, add_args=(_text(),)),
        *list_cmds("remediation", field="risks", legal_in=_IN_ASSESS, add_args=(_text(),)),
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _boolean("needsHuman", required=False))),
        *element_cmds("questions", agency="human", marks=(
            ("answerQuestion", "answer", "answer a question in the user's words (open -> answered)",
             (_text("answer"),)),
            ("deferQuestion", "defer", "defer a question the user leaves open (open -> deferred)"))),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        set_scalar_cmd("fix", "status", name="setFixStatus", label="fix status", choices=_FIX_STATUSES,
                       legal_in=_IN_FIX),
        set_prose_cmd("fix", field="summary", name="setFixSummary", label="fix summary", legal_in=_IN_FIX),
        *list_cmds("fix", field="changes", legal_in=_IN_FIX,
                   add_args=(_text("file"), _text("change", choices=_CHANGES), _text("notes", required=False))),
        *blocks_cmds("fix", field="highlights", add_name="addHighlights",
                     remove_name="removeHighlightBlock", remove_desc="remove a diff highlight block",
                     reorder_name="reorderHighlightBlock",
                     reorder_desc="move a diff highlight block to an anchored position (precedingId guards a stale read)",
                     legal_in=_IN_FIX),
        *list_cmds("fix", field="tests", singular="fixTest", label="test added or updated", legal_in=_IN_FIX,
                   add_args=(_text("test"), _text("pins"))),
        *list_cmds("fix", field="verification", singular="localCheck", label="local check", legal_in=_IN_FIX,
                   add_args=(_text("command"), _text("result"))),
        *list_cmds("fix", field="deviations", legal_in=_IN_FIX, add_args=(_text(),)),
        *list_cmds("fix", field="followUps", label="follow-up", legal_in=_IN_FIX, add_args=(_text(),)),
        set_scalar_cmd("verification", "result", choices=_RESULTS, legal_in=_IN_TEST),
        set_prose_cmd("verification", field="summary", name="setVerificationSummary",
                      label="verification summary", legal_in=_IN_TEST),
        *list_cmds("verification", field="checks", legal_in=_IN_TEST,
                   add_args=(_text("check"), _text("action"), _text("outcome", choices=_OUTCOMES),
                             _text("notes", required=False))),
        *blocks_cmds("verification", field="excerpts", add_name="addExcerpts",
                     remove_name="removeExcerptBlock", remove_desc="remove an output excerpt block",
                     reorder_name="reorderExcerptBlock",
                     reorder_desc="move an output excerpt block to an anchored position (precedingId guards a stale read)",
                     legal_in=_IN_TEST),
        *list_cmds("verification", field="residualRisks", label="residual risk", legal_in=_IN_TEST,
                   add_args=(_text(),)),
        set_prose_cmd("verification", field="recommendation", name="setRecommendation",
                      label="recommendation", legal_in=_IN_TEST),
        transition_cmd("proceed", "prepare -> assess"),
        transition_cmd("submitAssessment", "assess -> assessmentReview",
                       requires=(("report", "source"), ("report", "body"), ("triage", "verdict"),
                                 ("triage", "severity"), ("triage", "rationale"), ("symptom", "body"),
                                 ("reproduction", "steps"), ("cause", "codePaths"), ("cause", "hypothesis"),
                                 ("cause", "confidence"), ("remediation", "preferred"),
                                 ("remediation", "files"), ("remediation", "tests"), ("remediation", "risks"))),
        # A report that is not a bug has no remediation to write.
        transition_cmd("submitAsInvalid", "assess -> assessmentReview",
                       requires=(("report", "source"), ("report", "body"), ("triage", "verdict"),
                                 ("triage", "rationale"))),
        # No code changes before the user approves; an assessment submitted as invalid has no
        # remediation, so it cannot be approved, only closed or reassessed.
        transition_cmd("approveAssessment", "assessmentReview -> fix (human gate)", agency="human",
                       requires=(("remediation", "preferred"), ("remediation", "files"))),
        transition_cmd("closeInvalid", "assessmentReview -> closed (human gate)", agency="human"),
        transition_cmd("submitFix", "fix -> test",
                       requires=(("fix", "status"), ("fix", "summary"), ("fix", "changes"), ("fix", "tests"),
                                 ("fix", "verification"))),
        transition_cmd("submitResult", "test -> resultReview",
                       requires=(("verification", "result"), ("verification", "summary"),
                                 ("verification", "checks"), ("verification", "recommendation"))),
        transition_cmd("close", "resultReview -> closed (human gate)", agency="human"),
        transition_cmd("refix", "resultReview -> fix", agency="either"),
        transition_cmd("retest", "resultReview -> test", agency="either"),
        transition_cmd("reassess", "back to the assessment -> assess", agency="either",
                       legal_in=("assessmentReview", "fix", "test", "resultReview")),
        transition_cmd("reopen", "closed -> assess", agency="either"),
        transition_cmd("abandon", "drop the bug -> abandoned", agency="human",
                       legal_in=("prepare", "assess", "assessmentReview", "fix", "test", "resultReview")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SpeckitBug",
        initial="prepare",
        states=("prepare", "assess", "assessmentReview", "fix", "test", "resultReview", "closed", "abandoned"),
        terminal_states=("closed", "abandoned"),
        status_guidance=(
            ("prepare", SPECKIT_PREPARE),
            ("assess", SPECKIT_ASSESS),
            ("assessmentReview", SPECKIT_ASSESSMENT_REVIEW),
            ("fix", SPECKIT_FIX),
            ("test", SPECKIT_TEST),
            ("resultReview", SPECKIT_RESULT_REVIEW),
        ),
    ),
    workspace_guidance=(
        WorkspaceGuidanceSpec(SPECKIT_CONSTITUTION_FIELD, ("prepare",), SPECKIT_CONSTITUTION_DESC,
                              SPECKIT_CONSTITUTION_LABEL),
        WorkspaceGuidanceSpec(GROUNDING_TOOL_FIELD, ("assess",), GROUNDING_TOOL_DESC, GROUNDING_TOOL_LABEL),
        WorkspaceGuidanceSpec(TESTING_TOOL_FIELD, ("fix", "test"), TESTING_TOOL_DESC, TESTING_TOOL_LABEL),
        WorkspaceGuidanceSpec(MERGE_PROCESS_FIELD, ("resultReview",), MERGE_PROCESS_DESC, MERGE_PROCESS_LABEL),
    ),
)
