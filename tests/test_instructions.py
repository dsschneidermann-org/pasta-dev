"""Unit tests for the pure instructions-text assembly (src.instructions).

These are pure: each function is a function of its inputs alone, so the tests pass plain
data - a list of (name, input_schema) tuples, a stretch of instructions text, and a list of
field-name strings - with no fastmcp server or store in sight.
"""

from src.instructions import (
    render_guidance_fields,
    render_instructions,
    render_tool_schemas,
)


def _tools():
    return [
        ("getPage", {"type": "object",
                     "properties": {"workspaceId": {"type": "string"},
                                    "pageId": {"type": "string"}},
                     "required": ["workspaceId", "pageId"]}),
        ("search", {"type": "object",
                    "properties": {"workspaceId": {"type": "string"},
                                   "query": {"type": "string"}},
                    "required": ["workspaceId", "query"]}),
        ("setWorkspaceGuidance", {"type": "object",
                                  "properties": {"workspaceId": {"type": "string"},
                                                 "field": {"type": "string"}}}),
    ]


# --- render_tool_schemas -----------------------------------------------------
def test_render_tool_schemas_lists_only_named_tools():
    # `search` is named in the text; getPage is not, so only search gets a schema entry.
    text = "Use `search` to find pages."
    out = render_tool_schemas(_tools(), text)
    assert "## Request tool schemas" in out
    assert '"name": "search"' in out
    assert "query" in out
    assert '"name": "getPage"' not in out


def test_render_tool_schemas_matches_a_backticked_call_form():
    # A name written with a call signature, e.g. `setWorkspaceGuidance(workspaceId, field, text)`,
    # still counts as named.
    text = "Configure with `setWorkspaceGuidance(workspaceId, field, text)`."
    out = render_tool_schemas(_tools(), text)
    assert '"name": "setWorkspaceGuidance"' in out
    assert '"name": "getPage"' not in out


def test_render_tool_schemas_ignores_unbackticked_mentions():
    # A bare mention (no backticks) does not qualify a tool - only a real reference does.
    out = render_tool_schemas(_tools(), "please search the pages and open a getPage view")
    assert out.count('"name"') == 0


def test_render_tool_schemas_is_sorted_by_name():
    tools = [("createPage", {"type": "object"}), ("archivePage", {"type": "object"})]
    out = render_tool_schemas(tools, "`archivePage` and `createPage` are both named")
    assert out.index("archivePage") < out.index("createPage")


# --- render_guidance_fields --------------------------------------------------
def test_render_guidance_fields_lists_names_without_descriptions():
    out = render_guidance_fields(["groundingTool", "mergeProcess", "testingTool"])
    assert "## Workspace guidance setup" in out
    assert "setWorkspaceGuidance" in out
    assert "groundingTool" in out and "mergeProcess" in out and "testingTool" in out


def test_render_guidance_fields_handles_empty():
    out = render_guidance_fields([])
    assert "## Workspace guidance setup" in out
    assert "setWorkspaceGuidance" in out


# --- render_instructions -----------------------------------------------------
def test_render_instructions_composes_all_sections_in_order():
    out = render_instructions(_tools(), ["mergeProcess"])
    assert "structured wiki" in out                      # prose preamble
    guidance_at = out.index("## Workspace guidance setup")
    schemas_at = out.index("## Request tool schemas")
    assert out.index("structured wiki") < guidance_at    # prose precedes both
    assert guidance_at < schemas_at                      # guidance section precedes schemas


def test_render_instructions_schema_section_follows_the_prose_names():
    # The real prose names search but not getPage; the guidance section names setWorkspaceGuidance.
    out = render_instructions(_tools(), ["mergeProcess"])
    assert '"name": "search"' in out
    assert '"name": "setWorkspaceGuidance"' in out
    assert '"name": "getPage"' not in out
