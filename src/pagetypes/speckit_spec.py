"""The `speckit-spec` page type and the `speckit-tasks` page created with it: GitHub Spec Kit's
Spec-Driven Development as one page and one child.

They are declared together because each one's gates read the other's statuses. The spec starts in
prepare, where the constitution is read and updated; after that each of its statuses is one
`/speckit-*` skill, and the child holds what the gates count, the tasks and the analyze findings.
Field descriptions are Spec Kit's own words (github/spec-kit at f201054, MIT), with only marks and
line breaks changed for reading; each notice maps the files and skills that text names onto the
page.
"""

from __future__ import annotations

from ._stage_guidance import (
    SPECKIT_PREPARE,
    SPECKIT_ANALYZE,
    SPECKIT_CHECKLIST,
    SPECKIT_CLARIFY,
    SPECKIT_CONVERGE,
    SPECKIT_DRAFTING,
    SPECKIT_IMPLEMENT,
    SPECKIT_PLAN,
    SPECKIT_SPECIFY,
    SPECKIT_TASKS,
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
    transition_on_add_cmd,
)
from .core.fields import SectionSpec, _blocks, _list, _prose, _scalar
from .core.pagetype import PageType
from .core.specs import (
    AutoChildSpec,
    ChildStateGuard,
    ElementFSMSpec,
    FSMSpec,
    ParentStateGuard,
    RefCheck,
    WorkspaceGuidanceSpec,
)

# Only the user settles a question, so both of its marks are human.
_QUESTION_FSM = ElementFSMSpec(
    name="Question",
    initial="open", states=("open", "answered", "deferred"),
    transitions=(("answer", "open", "answered", "human"),
                 ("defer", "open", "deferred", "human")),
)

# A requirements check belongs to the reviewer: the agent writes it and never ticks it.
_CHECK_FSM = ElementFSMSpec(
    name="Check",
    initial="open", states=("open", "satisfied", "waived"),
    transitions=(("satisfy", "open", "satisfied", "human"),
                 ("waive", "open", "waived", "human")),
    checkmark_done="satisfied",
)

_TASK_FSM = ElementFSMSpec(
    name="Task",
    initial="todo", states=("todo", "done", "skipped"),
    transitions=(("complete", "todo", "done", "agent"),
                 ("skip", "todo", "skipped", "human")),
    checkmark_done="done",
)

# The agent resolves a finding by fixing what it names; only the user accepts one as it is.
_FINDING_FSM = ElementFSMSpec(
    name="Finding",
    initial="open", states=("open", "resolved", "accepted"),
    transitions=(("resolve", "open", "resolved", "agent"),
                 ("accept", "open", "accepted", "human")),
    checkmark_done="resolved",
)

_PRIORITIES = ("P1", "P2", "P3")
_ASPECTS = ("Language/Version", "Primary Dependencies", "Storage", "Testing", "Target Platform",
            "Project Type", "Performance Goals", "Constraints", "Scale/Scope")
_PRINCIPLE_VERDICTS = ("pass", "violation")
_DIMENSIONS = ("Requirement Completeness", "Requirement Clarity", "Requirement Consistency",
               "Acceptance Criteria Quality", "Scenario Coverage", "Edge Case Coverage",
               "Non-Functional Requirements", "Dependencies & Assumptions", "Ambiguities & Conflicts")
_GAP_TYPES = ("missing", "partial", "contradicts", "unrequested")
_CATEGORIES = ("Duplication", "Ambiguity", "Underspecification", "Constitution", "Coverage", "Inconsistency")
_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# Spec Kit's later skills never edit an earlier one's file, so each part of the page is locked to the
# skill that owns it. clarify is the one exception: it folds the user's answers into the spec.
_IN_SPEC = ("specify", "clarify")
_IN_PLAN = ("plan",)
_IN_CHECKLIST = ("checklist",)
_IN_CONVERGE = ("converge",)

_ALL_STATUSES = ("prepare", "specify", "clarify", "plan", "checklist", "tasks", "analyze", "implement", "converge",
                 "shipped", "abandoned")

# Shown to people in the web UI only, first on the page: where its text comes from, and its licence.
_SOURCE = ("Adapted from GitHub Spec Kit, https://github.com/github/spec-kit, at commit f201054, "
           "under the MIT License.")

_SPEC_NOTICE = """
    The field instructions and stage guidance of this page are GitHub Spec Kit's own words. Spec Kit
    runs skills over files; this page stands in for both.

    Where Spec Kit names one of its files, the text names the section or field that holds it
    instead. The spec sections are Input through Assumptions, and Clarifications; `tasks.items` and
    the analyze findings are on the Spec Kit tasks child. The constitution is the
    `speckitConstitution` workspace guidance field: fetch it with `getWorkspaceGuidance` if the
    `prepare` status response did not already show it. A stage it names comes with the command that
    moves this page there, such as plan (`approveSpec`). A [NEEDS CLARIFICATION: ...] marker is an
    open question on this page, flagged needsHuman, and only the user answers one.
    """

_TASKS_NOTICE = """
    The field instructions and stage guidance of this page are GitHub Spec Kit's own words. Where
    Spec Kit names one of its files, the text names the section or field that holds it instead:
    `tasks.items` is on this page, and the spec sections, the `plan` section, `dataModel.entities`,
    `contracts.items`, `research.decisions` and `quickstart.guide` are on the Spec Kit spec above
    it. A stage it names comes with the command that moves the spec there.
    """

# What the spec's gates count on its one pinned child. A list with nothing in it passes.
_TASKS_READY = ChildStateGuard("speckit-tasks", ("ready",), "the Spec Kit tasks child must be marked ready")
_TASKS_DONE = ChildStateGuard("speckit-tasks", ("done", "skipped"), "every task must be done or skipped",
                              section="tasks", field="items")
_FINDINGS_CLOSED = ChildStateGuard("speckit-tasks", ("resolved", "accepted"),
                                   "every analyze finding must be resolved or accepted",
                                   section="findings", field="items")


_SPECKIT_SPEC = PageType(
    tag="speckit-spec",
    name="Spec Kit spec",
    description=(
        "Spec Kit's Spec-Driven Development: carries one feature from a plain-language description "
        "through specify, clarify, plan, checklist, tasks, analyze, implement and converge, with the "
        "user approving the spec and then the plan before anything is built. Use it only when the user "
        "asks for a Spec Kit spec; otherwise use a feature-brief, a spike when the way to build it is "
        "open, or a speckit-idea when it is undecided whether to build it at all."
    ),
    sections=(
        SectionSpec("source", "Spec Kit source", (
            _prose("body", description="Spec Kit source fixed text, shown in the web UI only.",
                   fixed=_SOURCE, web_only=True),
        )),
        SectionSpec("notice", "Spec Kit notice", (
            _prose("body", description="Spec Kit notice fixed text.", fixed=_SPEC_NOTICE),
        )),
        SectionSpec("input", "Input", (
            _prose("description", description="""
                **Input**: User description: "$ARGUMENTS"

                The text the user typed in the message that asked for specify (`proceed`) **is** the
                feature description.
                """),
        )),
        SectionSpec("stories", "User scenarios", (
            _list("items", element_fields=("title", "priority", "journey", "why", "independentTest", "scenarios"),
                  description="""
                IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
                Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just
                ONE of them, you should still have a viable MVP (Minimum Viable Product) that delivers
                value.

                Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
                Think of each story as a standalone slice of functionality that can be:
                - Developed independently
                - Tested independently
                - Deployed independently
                - Demonstrated to users independently

                ### User Story 1 - [Brief Title] (Priority: P1)

                [Describe this user journey in plain language]

                **Why this priority**: [Explain the value and why it has this priority level]

                **Independent Test**: [Describe how this can be tested independently - e.g., "Can be
                fully tested by [specific action] and delivers [specific value]"]

                **Acceptance Scenarios**:

                1. **Given** [initial state], **When** [action], **Then** [expected outcome]
                2. **Given** [initial state], **When** [action], **Then** [expected outcome]
                """),
        )),
        SectionSpec("edges", "Edge cases", (
            _list("items", element_fields=("text",), description="""
                - What happens when [boundary condition]?
                - How does system handle [error scenario]?
                """),
        )),
        SectionSpec("requirements", "Requirements", (
            _list("functional", element_fields=("key", "text"), description="""
                Generate Functional Requirements
                Each requirement must be testable
                Use reasonable defaults for unspecified details (document assumptions in Assumptions
                section)

                - **FR-001**: System MUST [specific capability, e.g., "allow users to create
                  accounts"]
                - **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
                - **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
                - **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
                - **FR-005**: System MUST [behavior, e.g., "log all security events"]

                *Example of marking unclear requirements:*

                - **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not
                  specified - email/password, SSO, OAuth?]
                - **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period
                  not specified]
                """),
            _list("entities", element_fields=("name", "text"), description="""
                Identify Key Entities (if data involved)

                - **[Entity 1]**: [What it represents, key attributes without implementation]
                - **[Entity 2]**: [What it represents, relationships to other entities]
                """),
        )),
        SectionSpec("success", "Success criteria", (
            _list("outcomes", element_fields=("key", "text"), description="""
                ### Success Criteria Guidelines

                Success criteria must be:

                1. **Measurable**: Include specific metrics (time, percentage, count, rate)
                2. **Technology-agnostic**: No mention of frameworks, languages, databases, or tools
                3. **User-focused**: Describe outcomes from user/business perspective, not system
                   internals
                4. **Verifiable**: Can be tested/validated without knowing implementation details

                **Good examples**:

                - "Users can complete checkout in under 3 minutes"
                - "System supports 10,000 concurrent users"
                - "95% of searches return results in under 1 second"
                - "Task completion rate improves by 40%"

                **Bad examples** (implementation-focused):

                - "API response time is under 200ms" (too technical, use "Users see results
                  instantly")
                - "Database can handle 1000 TPS" (implementation detail, use user-facing metric)
                - "React components render efficiently" (framework-specific)
                - "Redis cache hit rate above 80%" (technology-specific)

                - **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under
                  2 minutes"]
                - **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without
                  degradation"]
                - **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete
                  primary task on first attempt"]
                - **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]
                """),
        )),
        SectionSpec("assumptions", "Assumptions", (
            _list("items", element_fields=("text",), description="""
                **Document assumptions**: Record reasonable defaults in the Assumptions section

                - [Assumption about target users, e.g., "Users have stable internet connectivity"]
                - [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
                - [Assumption about data/environment, e.g., "Existing authentication system will be
                  reused"]
                - [Dependency on existing system/service, e.g., "Requires access to the existing user
                  profile API"]
                """),
        )),
        SectionSpec("quality", "Spec quality", (
            _prose("criteria", description="Spec quality criteria fixed text.", fixed="""
                ## Content Quality

                - [ ] No implementation details (languages, frameworks, APIs)
                - [ ] Focused on user value and business needs
                - [ ] Written for non-technical stakeholders
                - [ ] All mandatory sections completed

                ## Requirement Completeness

                - [ ] No [NEEDS CLARIFICATION] markers remain
                - [ ] Requirements are testable and unambiguous
                - [ ] Success criteria are measurable
                - [ ] Success criteria are technology-agnostic (no implementation details)
                - [ ] All acceptance scenarios are defined
                - [ ] Edge cases are identified
                - [ ] Scope is clearly bounded
                - [ ] Dependencies and assumptions identified

                ## Feature Readiness

                - [ ] All functional requirements have clear acceptance criteria
                - [ ] User scenarios cover primary flows
                - [ ] Feature meets measurable outcomes defined in Success Criteria
                - [ ] No implementation details leak into specification
                """),
            _prose("result", description="""
                **Run Validation Check**: Review the spec against each checklist item:
                - For each item, determine if it passes or fails
                - Document specific issues found (quote relevant spec sections)

                **If items fail (excluding [NEEDS CLARIFICATION])**:
                1. List the failing items and specific issues
                2. Update the spec to address each issue
                3. Re-run validation until all items pass (max 3 iterations)
                4. If still failing after 3 iterations, document remaining issues in checklist notes
                   and warn user
                """),
        )),
        SectionSpec("questions", "Clarifications", (
            _list("items", element_fields=("text", "why", "options", "answer", "needsHuman", "status"),
                  element_fsm=_QUESTION_FSM, description="""
                For unclear aspects:
                - Make informed guesses based on context and industry standards
                - Only mark with [NEEDS CLARIFICATION: specific question] if:
                  - The choice significantly impacts feature scope or user experience
                  - Multiple reasonable interpretations exist with different implications
                  - No reasonable default exists
                - **LIMIT: Maximum 3 [NEEDS CLARIFICATION] markers total**
                - Prioritize clarifications by impact: scope > security/privacy > user experience >
                  technical details

                **Question writing quality (applies to every question, MC or short-answer):**
                 - Lead with `**Question:**` followed by a full interrogative that ends with `?`. The
                   question text before the `?` must make sense on its own.
                 - NEVER use a topic label, section heading, or requirement id as the question itself.
                   For example, `Acceptance device/runtime matrix (FR-023)` is INVALID — it is a
                   label, not a question.
                 - After the `?`, the only permitted suffix is an optional parenthesized
                   requirement/question id. Exact format: `**Question:** <interrogative>?` or
                   `**Question:** <interrogative>? (FR-023)`. Never put the id before the `?`, and
                   never use the id (alone or with a topic label) as the whole prompt.
                 - Immediately after the question line, add one plain-language "Why it matters"
                   sentence (the stake for acceptance or shipping) before the recommendation/options.
                 - Use everyday wording; introduce jargon only if defined in the same sentence.
                   Self-check: a reader who does not know Spec Kit must be able to answer from the
                   Question line alone. Terse is fine; cryptic labels are not.

                For multiple‑choice questions:
                 - **Analyze all options** and determine the **most suitable option** based on:
                    - Best practices for the project type
                    - Common patterns in similar implementations
                    - Risk reduction (security, performance, maintainability)
                    - Alignment with any explicit project goals or constraints visible in the spec
                 - Present your **recommended option prominently** at the top with clear reasoning
                   (1-2 sentences explaining why this is the best choice).
                 - Format as: `**Recommended:** Option [X] - <reasoning>`
                 - Then render all options as a Markdown table:

                   | Option | Description |
                   |--------|-------------|
                   | A | <Option A description> |
                   | B | <Option B description> |
                   | C | <Option C description> (add D/E as needed up to 5) |
                   | Short | Provide a different short answer (<=5 words) (Include only if free-form alternative is appropriate) |

                   - After the table, add: `You can reply with the option letter (e.g., "A"), accept
                     the recommendation by saying "yes" or "recommended", or provide your own short
                     answer.`

                For short‑answer style (no meaningful discrete options):
                 - Provide your **suggested answer** based on best practices and context.
                 - Format as: `**Suggested:** <your proposed answer> - <brief reasoning>`
                 - Then output: `Format: Short answer (<=5 words). You can accept the suggestion by
                   saying "yes" or "suggested", or provide your own answer.`
                """),
        )),
        SectionSpec("plan", "Plan", (
            _list("direction", element_fields=("text",), description="""
                This is where implementation detail belongs — provide your tech stack, architecture,
                and technical constraints as arguments.
                """),
            _prose("summary", description="""
                [Extract from feature spec: primary requirement + technical approach from research]
                """),
            _list("context", element_fields=("aspect", "value"), description="""
                Fill Technical Context (mark unknowns as "NEEDS CLARIFICATION")

                **Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

                **Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

                **Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

                **Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

                **Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

                **Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or
                NEEDS CLARIFICATION]

                **Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or
                NEEDS CLARIFICATION]

                **Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or
                NEEDS CLARIFICATION]

                **Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS
                CLARIFICATION]
                """),
            _list("constitutionCheck", element_fields=("principle", "verdict", "evidence"), description="""
                *GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

                [Gates determined based on the `speckitConstitution` workspace guidance field (fetch
                it with `getWorkspaceGuidance` if the `prepare` status response did not already show
                it)]

                - Fill Constitution Check section from the `speckitConstitution` workspace guidance
                  field
                - Evaluate gates (ERROR if violations unjustified)
                - Re-evaluate Constitution Check post-design
                """),
            _list("complexity", element_fields=("violation", "whyNeeded", "simplerRejected"), description="""
                > **Fill ONLY if Constitution Check has violations that must be justified**

                | Violation | Why Needed | Simpler Alternative Rejected Because |
                |-----------|------------|-------------------------------------|
                | [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
                | [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
                """),
            _blocks("structure", block_kinds=standard_blocks(), description="""
                ACTION REQUIRED: Replace the placeholder tree below with the concrete layout for this
                feature. Delete unused options and expand the chosen structure with real paths (e.g.,
                apps/admin, packages/something). The delivered plan must not include Option labels.

                **Structure Decision**: [Document the selected structure and reference the real
                directories captured above]
                """),
        )),
        SectionSpec("research", "Research", (
            _list("decisions", element_fields=("topic", "decision", "rationale", "alternatives"), description="""
                **Extract unknowns from Technical Context** above:
                - For each NEEDS CLARIFICATION → research task
                - For each dependency → best practices task
                - For each integration → patterns task

                **Consolidate findings** in `research.decisions` using format:
                - Decision: [what was chosen]
                - Rationale: [why chosen]
                - Alternatives considered: [what else evaluated]
                """),
        )),
        SectionSpec("dataModel", "Data model", (
            _list("entities", element_fields=("name", "fields", "relationships", "rules", "states"), description="""
                **Extract entities from feature spec** → `dataModel.entities`:
                - Entity name, fields, relationships
                - Validation rules from requirements
                - State transitions if applicable

                `dataModel.entities` is the canonical source for field constraints (max/min length,
                nullable/required, enum values, validation rules), including constraints encoded in
                field types
                """),
        )),
        SectionSpec("contracts", "Contracts", (
            _list("items", element_fields=("name", "format", "shape"), description="""
                **Define interface contracts** (if project has external interfaces) →
                `contracts.items`:
                - Identify what interfaces the project exposes to users or other systems
                - Document the contract format appropriate for the project type
                - Examples: public APIs for libraries, command schemas for CLI tools, endpoints for
                  web services, grammars for parsers, UI contracts for applications
                - Skip if project is purely internal (build scripts, one-off tools, etc.)
                """),
        )),
        SectionSpec("quickstart", "Quickstart", (
            _blocks("guide", block_kinds=standard_blocks(), description="""
                **Create quickstart validation guide** → `quickstart.guide`:
                - Document runnable validation scenarios that prove the feature works end-to-end
                - Include prerequisites, setup commands, test/run commands, and expected outcomes
                - Use links or references to contracts and data model details instead of duplicating
                  them
                - Do not include full implementation code, model/service/controller bodies,
                  migrations, or complete test suites
                - Keep this artifact as a validation/run guide; implementation details belong in
                  `tasks.items` and the implementation phase
                """),
        )),
        SectionSpec("checklist", "Requirements checklist", (
            _list("items", element_fields=("domain", "dimension", "text", "trace", "status"),
                  element_fsm=_CHECK_FSM, description="""
                **ITEM STRUCTURE**:
                Each item should follow this pattern:
                - Question format asking about requirement quality
                - Focus on what's WRITTEN (or not written) in the spec/plan
                - Include quality dimension in brackets [Completeness/Clarity/Consistency/etc.]
                - Reference spec section `[Spec §X.Y]` when checking existing requirements
                - Use `[Gap]` marker when checking for missing requirements

                **Traceability Requirements**:
                - MINIMUM: ≥80% of items MUST include at least one traceability reference
                - Each item should reference: spec section `[Spec §X.Y]`, or use markers: `[Gap]`,
                  `[Ambiguity]`, `[Conflict]`, `[Assumption]`
                - If no ID system exists: "Is a requirement & acceptance criteria ID scheme
                  established? [Traceability]"

                **🚫 ABSOLUTELY PROHIBITED** - These make it an implementation test, not a requirements
                test:
                - ❌ Any item starting with "Verify", "Test", "Confirm", "Check" + implementation
                  behavior
                - ❌ References to code execution, user actions, system behavior
                - ❌ "Displays correctly", "works properly", "functions as expected"
                - ❌ "Click", "navigate", "render", "load", "execute"
                - ❌ Test cases, test plans, QA procedures
                - ❌ Implementation details (frameworks, APIs, algorithms)

                **✅ REQUIRED PATTERNS** - These test requirements quality:
                - ✅ "Are [requirement type] defined/specified/documented for [scenario]?"
                - ✅ "Is [vague term] quantified/clarified with specific criteria?"
                - ✅ "Are requirements consistent between [section A] and [section B]?"
                - ✅ "Can [requirement] be objectively measured/verified?"
                - ✅ "Are [edge cases/scenarios] addressed in requirements?"
                - ✅ "Does the spec define [missing aspect]?"

                Leave every newly generated item unchecked (`[ ]`); checkbox state belongs to the
                reviewer
                """),
        )),
        SectionSpec("analysis", "Analysis", (
            _list("reports", element_fields=("text",), description="""
                ### 6. Produce Compact Analysis Report

                Output a Markdown report (no file writes) with the following structure:

                ## Specification Analysis Report

                | ID | Category | Severity | Location(s) | Summary | Recommendation |
                |----|----------|----------|-------------|---------|----------------|
                | A1 | Duplication | HIGH | `requirements.functional` | Two similar requirements ... | Merge phrasing; keep clearer version |

                (Add one row per finding; generate stable IDs prefixed by category initial.)

                **Coverage Summary Table:**

                | Requirement Key | Has Task? | Task IDs | Notes |
                |-----------------|-----------|----------|-------|

                **Constrained-Field Coverage (when applicable):**

                | Field (`Entity.field`) | Canonical Location | Implementing Task IDs | Coverage / Consistency Notes |
                |------------------------|--------------------|-----------------------|------------------------------|

                Use the existing finding table for field findings, including source locations and
                actionable recommendations. Field findings share the 50-finding limit and overflow
                summary; do not change the existing requirement coverage denominator or FR/SC coverage
                table semantics.

                **Constitution Alignment Issues:** (if any)

                **Unmapped Tasks:** (if any)

                **Metrics:**

                - Total Requirements
                - Total Tasks
                - Coverage % (requirements with >=1 task)
                - Ambiguity Count
                - Duplication Count
                - Critical Issues Count
                """),
        )),
        SectionSpec("convergence", "Convergence", (
            _list("summaries", element_fields=("text",), description="""
                ### 6. Present the In-Session Findings Summary

                Before appending anything, output a compact, severity-graded summary (no file writes
                yet):

                ## Convergence Findings

                | ID | Gap Type | Severity | Source | Evidence | Remaining Work |
                |----|----------|----------|--------|----------|----------------|
                | F1 | missing  | HIGH     | FR-008 | Example: no append-only guard detected in path/to/module.py when writing `tasks.items` | Add append-only enforcement |

                **Summary metrics:**

                - Requirements / acceptance criteria checked
                - Plan decisions checked
                - Constitution principles checked (or "skipped — template")
                - Findings by gap type (missing / partial / contradicts / unrequested)
                - Findings by severity
                """),
        )),
        SectionSpec("pull_request", "Pull Request", (
            _scalar("url", description="""
                The pull request URL created for this feature review.
                """),
        )),
    ),
    commands=(
        set_prose_cmd("input", field="description", name="setDescription", label="feature description",
                      legal_in=("specify",)),
        *list_cmds("stories", singular="story", label="user story", editable=True, legal_in=_IN_SPEC,
                   add_args=(_text("title"), _text("priority", choices=_PRIORITIES), _text("journey"),
                             _text("why"), _text("independentTest"), _text("scenarios"))),
        *list_cmds("edges", singular="edgeCase", label="edge case", legal_in=_IN_SPEC, add_args=(_text(),)),
        *list_cmds("requirements", field="functional", singular="requirement", editable=True,
                   legal_in=_IN_SPEC, add_args=(_text("key"), _text())),
        *list_cmds("requirements", field="entities", singular="entity", legal_in=_IN_SPEC,
                   add_args=(_text("name"), _text())),
        *list_cmds("success", field="outcomes", editable=True, legal_in=_IN_SPEC,
                   add_args=(_text("key"), _text())),
        *list_cmds("assumptions", legal_in=_IN_SPEC, add_args=(_text(),)),
        set_prose_cmd("quality", field="result", name="setQualityResult", label="spec quality result",
                      legal_in=_IN_SPEC),
        *list_cmds("questions", add_name="askQuestion", label="question", remove=False,
                   add_args=(_text(), _text("why"), _text("options"), _boolean("needsHuman", required=False))),
        *element_cmds("questions", agency="human", marks=(
            ("answerQuestion", "answer", "answer a question in the user's words (open -> answered)",
             (_text("answer"),)),
            ("deferQuestion", "defer", "defer a question the user leaves open (open -> deferred)"))),
        set_element_field_cmd("questions", name="escalateQuestion",
                              description="flag a question as awaiting a human", const=("needsHuman", True)),
        # Written only by the gate that approves the spec, so the list needs no add of its own.
        *list_cmds("plan", field="direction", add=False, remove=False, legal_in=_IN_PLAN),
        set_prose_cmd("plan", field="summary", name="setPlanSummary", label="plan summary", legal_in=_IN_PLAN),
        *list_cmds("plan", field="context", singular="contextEntry", label="technical-context entry",
                   editable=True, legal_in=_IN_PLAN,
                   add_args=(_text("aspect", choices=_ASPECTS), _text("value"))),
        *list_cmds("plan", field="constitutionCheck", label="constitution check", editable=True,
                   legal_in=_IN_PLAN,
                   add_args=(_text("principle"), _text("verdict", choices=_PRINCIPLE_VERDICTS),
                             _text("evidence"))),
        *list_cmds("plan", field="complexity", label="justified violation", legal_in=_IN_PLAN,
                   add_args=(_text("violation"), _text("whyNeeded"), _text("simplerRejected"))),
        *blocks_cmds("plan", field="structure", add_name="addStructure",
                     remove_name="removeStructureBlock", remove_desc="remove a structure block",
                     reorder_name="reorderStructureBlock",
                     reorder_desc="move a structure block to an anchored position (precedingId guards a stale read)",
                     legal_in=_IN_PLAN),
        *list_cmds("research", field="decisions", editable=True, legal_in=_IN_PLAN,
                   add_args=(_text("topic"), _text("decision"), _text("rationale"), _text("alternatives"))),
        *list_cmds("dataModel", field="entities", singular="dataEntity", label="data-model entity",
                   editable=True, legal_in=_IN_PLAN,
                   add_args=(_text("name"), _text("fields"), _text("relationships", required=False),
                             _text("rules", required=False), _text("states", required=False))),
        *list_cmds("contracts", legal_in=_IN_PLAN, editable=True,
                   add_args=(_text("name"), _text("format"), _text("shape"))),
        *blocks_cmds("quickstart", field="guide", add_name="addQuickstart",
                     remove_name="removeQuickstartBlock", remove_desc="remove a quickstart block",
                     reorder_name="reorderQuickstartBlock",
                     reorder_desc="move a quickstart block to an anchored position (precedingId guards a stale read)",
                     legal_in=_IN_PLAN),
        *list_cmds("checklist", singular="check", label="requirements check", legal_in=_IN_CHECKLIST,
                   add_args=(_text("domain"), _text("dimension", choices=_DIMENSIONS), _text(), _text("trace"))),
        *element_cmds("checklist", singular="check", agency="human", legal_in=_IN_CHECKLIST, marks=(
            ("satisfyCheck", "satisfy", "tick a check the reviewer judged satisfied (open -> satisfied)"),
            ("waiveCheck", "waive", "waive a check the reviewer leaves unsatisfied (open -> waived)"))),
        # beginImplement adds the report it is fired with, so each visit's report is its own entry.
        *list_cmds("analysis", field="reports", add=False, remove=False, legal_in=("analyze",)),
        *list_cmds("convergence", field="summaries", singular="convergenceSummary",
                   label="convergence summary", remove=False, legal_in=_IN_CONVERGE, add_args=(_text(),)),
        # Open in every status: a pull request can be opened early and outlive the page's last status.
        set_scalar_cmd("pull_request", "url", name="setPullRequestUrl", label="pull request url",
                       legal_in=_ALL_STATUSES),
        transition_cmd("proceed", "prepare -> specify"),
        transition_cmd("submitSpec", "specify -> clarify",
                       requires=(("input", "description"), ("stories", "items"), ("edges", "items"),
                                 ("requirements", "functional"), ("success", "outcomes"),
                                 ("assumptions", "items"), ("quality", "result"))),
        # The gate carries the user's technical direction, which is what plan starts from.
        transition_on_add_cmd("approveSpec", "clarify -> plan", section="plan", field="direction",
                              agency="human",
                              description="approve the spec AND record the user's technical direction",
                              add_args=(_text(),)),
        transition_cmd("submitPlan", "plan -> checklist",
                       requires=(("plan", "summary"), ("plan", "context"), ("plan", "constitutionCheck"),
                                 ("plan", "structure"), ("research", "decisions"), ("quickstart", "guide"))),
        transition_cmd("approvePlan", "checklist -> tasks (human gate)", agency="human"),
        transition_cmd("beginAnalyze", "tasks -> analyze", guards=(_TASKS_READY,)),
        transition_cmd("skipAnalyze", "tasks -> implement (human gate)", agency="human", guards=(_TASKS_READY,)),
        transition_on_add_cmd("beginImplement", "analyze -> implement", section="analysis", field="reports",
                              description="record this visit's analysis report AND start implementing",
                              add_args=(_text(),), guards=(_TASKS_READY, _FINDINGS_CLOSED)),
        transition_cmd("beginConverge", "implement -> converge", guards=(_TASKS_DONE,)),
        transition_on_add_cmd("appendWork", "converge -> implement", section="convergence", field="summaries",
                              description="record this pass's convergence summary AND implement the appended tasks",
                              add_args=(_text(),)),
        # Shipping is the user's, and is held while any task is open.
        transition_cmd("ship", "converge -> shipped (human gate)", agency="human",
                       requires=(("convergence", "summaries"),), guards=(_TASKS_DONE,)),
        transition_cmd("requestChanges", "converge -> implement", agency="either"),
        transition_cmd("reviseSpec", "back to the spec -> specify", agency="either",
                       legal_in=("clarify", "checklist", "analyze", "implement", "converge")),
        transition_cmd("revisePlan", "back to the plan -> plan", agency="either",
                       legal_in=("checklist", "analyze", "implement", "converge")),
        transition_cmd("reviseTasks", "back to the tasks -> tasks", agency="either",
                       legal_in=("analyze", "implement")),
        transition_cmd("reopen", "shipped -> specify (human gate)", agency="human"),
        transition_cmd("abandon", "drop the work -> abandoned", agency="human",
                       legal_in=("prepare", "specify", "clarify", "plan", "checklist", "tasks", "analyze",
                                 "implement", "converge")),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SpeckitSpec",
        initial="prepare",
        states=_ALL_STATUSES,
        terminal_states=("shipped", "abandoned"),
        status_guidance=(
            ("prepare", SPECKIT_PREPARE),
            ("specify", SPECKIT_SPECIFY),
            ("clarify", SPECKIT_CLARIFY),
            ("plan", SPECKIT_PLAN),
            ("checklist", SPECKIT_CHECKLIST),
            ("tasks", SPECKIT_TASKS),
            ("analyze", SPECKIT_ANALYZE),
            ("implement", SPECKIT_IMPLEMENT),
            ("converge", SPECKIT_CONVERGE),
        ),
    ),
    auto_children=(AutoChildSpec("speckit-tasks"),),
    workspace_guidance=(
        WorkspaceGuidanceSpec(SPECKIT_CONSTITUTION_FIELD,
                              ("prepare", "specify", "clarify", "plan", "checklist", "tasks", "analyze",
                               "implement", "converge"),
                              SPECKIT_CONSTITUTION_DESC, SPECKIT_CONSTITUTION_LABEL),
        WorkspaceGuidanceSpec(GROUNDING_TOOL_FIELD, ("plan",), GROUNDING_TOOL_DESC, GROUNDING_TOOL_LABEL),
        WorkspaceGuidanceSpec(TESTING_TOOL_FIELD, ("implement",), TESTING_TOOL_DESC, TESTING_TOOL_LABEL),
        WorkspaceGuidanceSpec(MERGE_PROCESS_FIELD, ("implement", "converge"), MERGE_PROCESS_DESC,
                              MERGE_PROCESS_LABEL),
    ),
)


# The child waits until its spec is in tasks, and goes back to drafting only while it is there again.
_SPEC_IN_TASKS = ParentStateGuard(
    parent_type="speckit-spec",
    required_statuses=("tasks",),
    message="the Spec Kit spec must be in tasks",
)
_SPEC_FINISHED = ParentStateGuard(
    parent_type="speckit-spec",
    required_statuses=("shipped", "abandoned"),
    message="the Spec Kit spec must be shipped or abandoned",
)

# converge appends tasks to a finished list but never rewrites one.
_TASKS_WRITABLE = ("drafting", "ready")


_SPECKIT_TASKS = PageType(
    tag="speckit-tasks",
    name="Spec Kit tasks",
    description=(
        "The task list and the analyze findings of a Spec Kit spec, which the spec's gates count. "
        "Auto-created as a child of a speckit-spec."
    ),
    sections=(
        SectionSpec("notice", "Spec Kit notice", (
            _prose("body", description="Spec Kit notice fixed text.", fixed=_TASKS_NOTICE),
        )),
        SectionSpec("tasks", "Tasks", (
            _list("items", element_fields=("key", "phase", "parallel", "storyId", "text", "sourceRef", "gapType",
                                           "status"),
                  element_fsm=_TASK_FSM, description="""
                ### Checklist Format (REQUIRED)

                Every task MUST strictly follow this format:

                ```text
                - [ ] [TaskID] [P?] [Story?] Description with file path
                ```

                **Format Components**:

                1. **Checkbox**: ALWAYS start with `- [ ]` (markdown checkbox)
                2. **Task ID**: Sequential number (T001, T002, T003...) in execution order
                3. **[P] marker**: Include ONLY if task is parallelizable (different files, no
                   dependencies on incomplete tasks)
                4. **[Story] label**: REQUIRED for user story phase tasks only
                   - Format: [US1], [US2], [US3], etc. (maps to user stories from `stories.items`)
                   - Setup phase: NO story label
                   - Foundational phase: NO story label
                   - User Story phases: MUST have story label
                   - Polish phase: NO story label
                5. **Description**: Clear action with exact file path

                **Examples**:

                - ✅ CORRECT: `- [ ] T001 Create project structure per implementation plan`
                - ✅ CORRECT:
                  `- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.py`
                - ✅ CORRECT: `- [ ] T012 [P] [US1] Create User model in src/models/user.py`
                - ✅ CORRECT: `- [ ] T014 [US1] Implement UserService in src/services/user_service.py`
                - ❌ WRONG: `- [ ] Create User model` (missing ID and Story label)
                - ❌ WRONG: `T001 [US1] Create model` (missing checkbox)
                - ❌ WRONG: `- [ ] [US1] Create User model` (missing Task ID)
                - ❌ WRONG: `- [ ] T001 [US1] Create model` (missing file path)
                """),
            _prose("execution", description="""
                - Generate dependency graph showing user story completion order
                - Create parallel execution examples per user story
                - Dependencies section showing story completion order
                - Parallel execution examples per story
                - Implementation strategy section (MVP first, incremental delivery)
                """),
        )),
        SectionSpec("findings", "Analyze findings", (
            _list("items", element_fields=("key", "category", "severity", "location", "summary", "recommendation",
                                           "status"),
                  element_fsm=_FINDING_FSM, description="""
                | ID | Category | Severity | Location(s) | Summary | Recommendation |
                |----|----------|----------|-------------|---------|----------------|
                | A1 | Duplication | HIGH | `requirements.functional` | Two similar requirements ... | Merge phrasing; keep clearer version |

                (Add one row per finding; generate stable IDs prefixed by category initial.)

                ### 5. Severity Assignment

                Use this heuristic to prioritize findings:

                - **CRITICAL**: Violates constitution MUST, missing core spec artifact, or requirement
                  with zero coverage that blocks baseline functionality
                - **HIGH**: Duplicate or conflicting requirement, ambiguous security/performance
                  attribute, untestable acceptance criterion, missing/unresolved constrained-field
                  citations (Coverage), or contradictory task constraints (Inconsistency); retain
                  CRITICAL escalation above
                - **MEDIUM**: Terminology drift, missing non-functional task coverage, underspecified
                  edge case
                - **LOW**: Style/wording improvements, minor redundancy not affecting execution order
                """),
        )),
    ),
    commands=(
        # storyId is left out of Setup, Foundational, Polish and Convergence tasks, and gapType is
        # sent only by converge.
        *list_cmds("tasks", reorder=False, remove=False, legal_in=_TASKS_WRITABLE,
                   add_args=(_text("key"), _text("phase"), _boolean("parallel", required=False),
                             _text("storyId", required=False), _text(), _text("sourceRef", required=False),
                             _text("gapType", choices=_GAP_TYPES, required=False)),
                   ref_check=RefCheck(arg="storyId", scope="parent", section="stories", field="items")),
        *list_cmds("tasks", add=False, legal_in=("drafting",)),
        *element_cmds("tasks", legal_in=("ready",), marks=(
            ("markTaskDone", "complete", "mark a task done (todo -> done)"),)),
        *element_cmds("tasks", legal_in=("ready",), agency="human", marks=(
            ("skipTask", "skip", "skip a task the user drops (todo -> skipped)"),)),
        set_prose_cmd("tasks", field="execution", name="setExecution", label="execution order",
                      legal_in=("drafting",)),
        *list_cmds("findings", legal_in=("ready",),
                   add_args=(_text("key"), _text("category", choices=_CATEGORIES),
                             _text("severity", choices=_SEVERITIES), _text("location"), _text("summary"),
                             _text("recommendation"))),
        *element_cmds("findings", legal_in=("ready",), marks=(
            ("resolveFinding", "resolve", "resolve a finding that was fixed (open -> resolved)"),)),
        *element_cmds("findings", legal_in=("ready",), agency="human", marks=(
            ("acceptFinding", "accept", "accept a finding the user leaves as it is (open -> accepted)"),)),
        transition_cmd("openTasks", "waiting -> drafting", parent_guards=(_SPEC_IN_TASKS,)),
        transition_cmd("markReady", "drafting -> ready", requires=(("tasks", "items"), ("tasks", "execution"))),
        transition_cmd("reviseTasks", "ready -> drafting", parent_guards=(_SPEC_IN_TASKS,)),
        transition_cmd("closeTasks", "ready -> closed", parent_guards=(_SPEC_FINISHED,)),
        transition_cmd("reopenTasks", "closed -> drafting", parent_guards=(_SPEC_IN_TASKS,)),
        add_link_cmd(),
        set_title_cmd(),
    ),
    fsm=FSMSpec(
        name="SpeckitTasks",
        initial="waiting",
        states=("waiting", "drafting", "ready", "closed"),
        terminal_states=("closed",),
        status_guidance=(("drafting", SPECKIT_DRAFTING),),
    ),
)
