from __future__ import annotations

import json
import re
from typing import Any


_PROSE = """A **structured wiki** as the main project documentation with a FSM driven workflows:

- **Find** the right workspace `listWorkspaces`; **inspect page types and authoring** with `describePageType` / `describeMutations`.
- **Orient to the pasta MCP documentation:** `tree` to list the workspace contents, find the overall project document, read with `renderMarkdown`.
- **Pasta is the main documentation:** `search` to find specific words by prefix, `renderMarkdown` to read entire pages. Always ground in existing documentation.
- **Self-directing:** the FSM encodes next steps, surfaced via `nextActions` / `next` results on writes and creates. Do not ask the user which step comes next.
- **"Agency" comes straight from the metadata:** (`agency: "agent" | "human"`). Agent edges are yours to drive; human edges are real stopping points.

## Page types

- **Always use a page type to initiate workflows before grounding in code:** this drives the self-directing FSM, create an appropriate page unless the user explicitly asks to skip using the pasta MCP.
- **The authoring responses decide the next page edit - you don't.** After every write, read the echoed `next`; call `nextActions` when unsure for `do` / `blocked` / `humanGates` / `attention`. Drive `do` edges as needed, following instructions; for each `blocked` edge author exactly the content its `reason` names, then check the `next` result. Never hardcode a command sequence - if a `reason` changes, follow the new one.
- **Stop at human gates.** `humanGates` and `attention` items are not yours to cross. Drive up to them, then stop and hand back with a summary.
- **Gates must reflect reality.** `markStepDone` only after the step's code is written; `markCasePassed` only when a test genuinely passed; Default to *not* advancing when unsure.

**How to apply:** Make these instructions the very first actions of a new user request, ahead of code exploration and grounding. Evaluate the page type to use, then create it and following the authoring `do` / `blocked` edges.

**Why:** The user runs a structured workflow discipline in the pasta MCP - features, documentation, ADRs and architecture pages all live there, and the MCP is self-directing. Working without that process leads to work that ignores the established discipline or bases it outside the established architecture (e.g. reading drifted code comments instead of the architecture and documentation pages). If pasta MCP is not loaded, stop.

## Use Pasta: Red Flags

These thoughts mean STOP — you're rationalizing how to continue without using pasta:

| Thought | Reality |
|---------|---------|
| "I need more context first" | Pasta search comes BEFORE clarifying questions. |
| "Let me explore the codebase first" | Pasta pages tell you WHEN to explore. Create a page first. |
| "I can check git/files quickly" | Files lack conversation context. Check for pasta pages. |
| "Let me gather information first" | Pasta tell you WHEN to gather information. |
| "This doesn't count as a task" | Action = task. Create a pasta page. |
| "The discipline is overkill" | Simple things become complex. Create a pasta page. |
| "I'll just do this one thing first" | Create a page first, then do the thing if it still fits. |
| "This feels productive" | Undisciplined action wastes time. Pasta prevents this. |
| "I know what that means" | Knowing the concept is not following the process. Invoke pasta. |

## Pasta setup

If calling `tree` reveals an empty workspace, no project overview doc or the `toc` pages: Documentation, ADRs, Features and Bug Reports - suggest to create and setup the workspace with these `toc` pages and a "Project Overview" page at the users request. The workspace page structure is:

- Project Overview + `architecture` and `document` pages go under the Documentation `toc` page.
- `decision-record` pages go under the ADRs `toc` page.
- `feature-brief`, `simple-change` and `epic` pages go under the Features `toc` page.
- An `epic`'s `feature-brief` children are created under the epic itself, NOT under the Features `toc` page - the epic's ship gate only sees briefs that are its own children.
- `bug-report` pages go under the Bug Reports `toc` page.

## Response shapes

`describePageType` returns:

- **Page-type commands** - the intended authoring surface. They carry a real args schema, a description, a target section/field, and for transitions the FSM event they fire. **These are what you should call.**
- **A command's `description` is a short label**, not guidance. The authoring instruction for a field lives on that field in the `sections` listing, and is echoed as `instruction` on a `next` field edge - read it there before authoring.

`mutatePageBatch` returns:

- **`mutatePageBatch` success message:** _"Ran N command(s) … in one atomic commit."_ (All-or-nothing: a rejected command aborts the whole batch, and the error names the failing index + command + reason.)
- **Every successful write echoes a `next` summary object same as `nextActions`:** `{ do: [...], blocked: [...], humanGates: [...], attention: [...] }`.

`createPage` returns:

- **Created page id and children:** author into those.
- **Every successful create echoes a `next` summary object same as `nextActions`:** `{ do: [...], blocked: [...], humanGates: [...], attention: [...] }`.

## A summary of `describePageType` to quickly evaluate against user requests

architecture: Documents a part of the system that already exists in the codebase: its purpose, data model, code references, dependencies, and whether it is current or has drifted.

document: A general-purpose prose page for content that doesn't fit a typed page - notes, guides, references, narratives. The richest block-editing surface in the wiki.

toc: A table-of-contents container whose only content is the child pages placed under it. It holds no subject matter of its own and has no authoring commands - pages are filed by reparenting them beneath the toc, and its Child pages list IS the table of contents.

bug-report: Tracks a defect in existing behavior - what's wrong, how to reproduce it, and its resolution.

simple-change: Tracks a small, self-contained change or minor feature. Use this page type ONLY when the user specifically asks to make a small/simple change or a small/simple feature; for larger work create a feature-brief, and for a defect in existing behavior use a bug-report.

feature-brief: The root of a feature the user intends to build - drives new work from intent through grounding, planning, and a plan review to build and a human ship gate. Lifecycle transitions are gated on the required content for that stage being present first.

implementation-plan: The step-by-step build plan for a feature. Auto-created as a child of a feature-brief.

testing-plan: The verification cases for a feature. Auto-created as a child of a feature-brief.

feature-spec: The detailed product/UX specification for a feature, authored during planning on top of the grounded base and sealed before the plan review. Auto-created as a child of a feature-brief.

epic: The root of a major feature too large for one feature-brief - it decomposes into several child feature-briefs and is built by subagents dispatched from its pinned agent plan. Use it when the work splits into parts that each ship on their own; when it does not, use a feature-brief.

agent-plan: Which subagents an epic creates, the order they are dispatched in, and how their results are reported back onto the feature-briefs. Auto-created as a child of an epic.
"""


def render_tool_schemas(tools: list[tuple[str, dict[str, Any]]], named_text: str) -> str:
    """The '## Request tool schemas' section: one JSON object per request tool giving its name and
    input_schema, so a caller authors against the real argument names instead of guessing. Only the
    tools the instructions already name are listed - a tool qualifies when its backticked reference
    (`name` or `name(`) appears in `named_text`, the instructions text above this section - so the
    prose stays the single source of truth for which tools appear. The rest are sorted by name."""
    entries = [
        {"name": name, "input_schema": schema}
        for name, schema in sorted(tools, key=lambda tool: tool[0])
        if re.search("`" + re.escape(name) + "[`(]", named_text)
    ]
    body = json.dumps(entries, indent=2)
    return (
        "## Request tool schemas\n\n"
        "Every request tool with the exact input_schema to author calls against - use these "
        "argument names and types rather than guessing:\n\n"
        f"```json\n{body}\n```"
    )


def render_guidance_fields(fields: list[str]) -> str:
    """The '## Workspace guidance setup' section: names setWorkspaceGuidance and lists the settable
    field names only, with no per-field descriptions."""
    names = ", ".join(f"`{field}`" for field in fields) if fields else "(none)"
    return (
        "## Workspace guidance setup\n\n"
        "A workspace can carry per-status house rules, set with "
        "`setWorkspaceGuidance(workspaceId, field, text)` and surfaced on a page while it sits at "
        f"the relevant status. Settable fields: {names}."
    )


def render_instructions(
    tools: list[tuple[str, dict[str, Any]]], guidance_fields: list[str]
) -> str:
    """The full instructions text: the static prose, then the workspace-guidance section, then the
    request-tool-schemas section. The two dynamic sections are projected from live inputs so they
    cannot drift from the surface they describe. The schema section lists only the tools named in
    the text above it, so `named_text` carries the prose and the guidance section together."""
    named_text = _PROSE.rstrip() + "\n\n" + render_guidance_fields(guidance_fields)
    return named_text + "\n\n" + render_tool_schemas(tools, named_text) + "\n"
