"""Tests for mutable per-workspace guidance texts.

The behavioural tests use the hand-authored fixtures, which declare a few guidance fields on
test-lifecycle; the cross-type validation tests build throwaway page types. The suite runs in test
mode, so the configurable-field set is the fixtures', not production's.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import src.server as server
from src.errors import ValidationError
from src.model import Workspace
from src.pagetypes.core.specs import FSMSpec, WorkspaceGuidanceSpec, status_guidance
from src.pagetypes.core.fields import SectionSpec
from src.pagetypes.core.pagetype import PageType
from src.pagetypes.core.validation import validate_page_types, validate_workspace_guidance
from src.pagetypes._registry import get_page_type, workspace_guidance_fields
from src.pagetypes._workspace_guidance import (
    GROUNDING_TOOL_DESC,
    GROUNDING_TOOL_FIELD,
    MERGE_PROCESS_FIELD,
    TESTING_TOOL_FIELD,
)
from src.pagetypes.bug_report import _BUG_REPORT
from src.pagetypes.feature import _FEATURE_BRIEF
from src.pagetypes.simple_change import _SIMPLE_CHANGE
from src.serialize import workspace_from_dict, workspace_to_dict
from src.store import Store, workspace_guidance
from src.describe import describe_page_type

LIFECYCLE = get_page_type("test-lifecycle")


# --- helpers -----------------------------------------------------------------
def _wg_type(tag, states, *specs):
    """A throwaway page type with only workspace-guidance declarations, for the validation tests."""
    return PageType(
        tag=tag, name=tag, description="x",
        sections=(SectionSpec("s", "S", ()),),
        commands=(),
        fsm=FSMSpec(name=tag, initial=states[0], states=tuple(states)),
        workspace_guidance=specs,
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture
def mcp(tmp_path):
    server.STORE = Store(tmp_path)   # tools resolve STORE from the module at call time
    return server.mcp


def call(mcp, name, args=None):
    async def _run():
        async with Client(mcp) as client:
            result = await client.call_tool(name, args or {})
            return result.data

    return asyncio.run(_run())


def _mutate_store(store, workspace_id, page_id, commands):
    token = store.get_page(workspace_id, page_id).status_revision_token
    stamped = [{**command, "args": {"statusRevisionToken": token, **(command.get("args") or {})}}
               for command in commands]
    return store.mutate_page_batch(workspace_id, page_id, stamped)


def _mutate_server(mcp, args):
    page = call(mcp, "getPage", {"workspaceId": args["workspaceId"], "pageId": args["pageId"]})
    token = page["status_revision_token"]
    stamped = {**args, "commands": [
        {**command, "args": {"statusRevisionToken": token, **(command.get("args") or {})}}
        for command in args["commands"]]}
    return call(mcp, "mutatePageBatch", stamped)


def _building_lifecycle(mcp):
    """Drive a fresh test-lifecycle page to `building` and return (workspaceId, pageId)."""
    wid = call(mcp, "createWorkspace", {"name": "demo"})["id"]
    page = call(mcp, "createPage", {"workspaceId": wid, "type": "test-lifecycle", "title": "F"})
    pid, child_id = page["id"], page["children"][0]["id"]
    _mutate_server(mcp, {"workspaceId": wid, "pageId": pid, "commands": [
        {"command": "setSummary", "args": {"text": "S"}},
        {"command": "addPart", "args": {"name": "P"}},
        {"command": "beginPlanning"}]})
    _mutate_server(mcp, {"workspaceId": wid, "pageId": child_id, "commands": [
        {"command": "addStep", "args": {"text": "build"}}, {"command": "markReady"}]})
    result = _mutate_server(mcp, {"workspaceId": wid, "pageId": pid,
                                  "commands": [{"command": "beginImplementation"}]})
    assert result["status"] == "building"
    return wid, pid


# --- WorkspaceGuidanceSpec construction --------------------------------------
def test_workspace_guidance_spec_holds_its_fields():
    spec = WorkspaceGuidanceSpec("mergeProcess", ("review",), "a desc")
    assert (spec.field, spec.guidance_for, spec.description) == ("mergeProcess", ("review",), "a desc")


def test_workspace_guidance_spec_does_not_validate_at_construction():
    # A malformed one (empty field, no statuses) constructs without raising - validation is deferred.
    spec = WorkspaceGuidanceSpec("", (), "")
    assert spec.field == "" and spec.guidance_for == ()


# --- PageType.workspace_guidance ---------------------------------------------
def test_workspace_guidance_declared_on_the_page_type():
    fields = [spec.field for spec in LIFECYCLE.workspace_guidance]
    assert fields == ["buildTool", "reviewHint", "draftHint"]


def test_workspace_guidance_empty_when_none_declared():
    assert get_page_type("test-fields").workspace_guidance == ()


# --- validate_workspace_guidance ---------------------------------------------
def test_validate_workspace_guidance_flags_each_problem():
    unknown_status = _wg_type("wg-a", ("draft",),
                              WorkspaceGuidanceSpec("f", ("nope",), "d"))
    empty_for = _wg_type("wg-b", ("draft",), WorkspaceGuidanceSpec("g", (), "d"))
    empty_field = _wg_type("wg-c", ("draft",), WorkspaceGuidanceSpec("", ("draft",), "d"))
    empty_desc = _wg_type("wg-d", ("draft",), WorkspaceGuidanceSpec("h", ("draft",), ""))
    errors = validate_workspace_guidance({t.tag: t for t in
                                          (unknown_status, empty_for, empty_field, empty_desc)})
    joined = "\n".join(errors)
    assert "wg-a" in joined and "unknown status 'nope'" in joined
    assert "wg-b" in joined and "no guidance_for" in joined
    assert "wg-c" in joined and "empty field name" in joined
    assert "wg-d" in joined and "empty description" in joined


def test_validate_workspace_guidance_flags_disagreeing_descriptions():
    a = _wg_type("wg-a", ("draft",), WorkspaceGuidanceSpec("shared", ("draft",), "one"))
    b = _wg_type("wg-b", ("draft",), WorkspaceGuidanceSpec("shared", ("draft",), "two"))
    errors = validate_workspace_guidance({a.tag: a, b.tag: b})
    assert any("description disagrees" in e for e in errors)


def test_validate_workspace_guidance_clean_when_descriptions_agree():
    a = _wg_type("wg-a", ("draft",), WorkspaceGuidanceSpec("shared", ("draft",), "same"))
    b = _wg_type("wg-b", ("open", "draft"), WorkspaceGuidanceSpec("shared", ("open",), "same"))
    assert validate_workspace_guidance({a.tag: a, b.tag: b}) == []


# --- aggregated load raise ---------------------------------------------------
def test_validate_page_types_raises_on_bad_workspace_guidance():
    bad = _wg_type("wg-bad", ("draft",), WorkspaceGuidanceSpec("f", ("missing",), "d"))
    with pytest.raises(ValueError, match="unknown status 'missing'"):
        validate_page_types({bad.tag: bad})


def test_validate_page_types_clean_for_good_workspace_guidance():
    good = _wg_type("wg-ok", ("draft",), WorkspaceGuidanceSpec("f", ("draft",), "d"))
    assert validate_page_types({good.tag: good}) is None


# --- workspace_guidance (pure emission) ----------------------------------
def test_workspace_guidance_emits_only_in_set_with_text():
    config = {"buildTool": "use pytest", "reviewHint": "look hard"}
    assert workspace_guidance(LIFECYCLE, "building", config) == {"guidance_buildTool": "use pytest"}
    # review is in both buildTool and reviewHint sets.
    assert workspace_guidance(LIFECYCLE, "review", config) == {
        "guidance_buildTool": "use pytest", "guidance_reviewHint": "look hard"}


def test_workspace_guidance_skips_out_of_set_absent_and_empty():
    assert workspace_guidance(LIFECYCLE, "planning", {"buildTool": "x"}) == {}   # out of set
    assert workspace_guidance(LIFECYCLE, "building", {}) == {}                    # absent
    assert workspace_guidance(LIFECYCLE, "building", {"buildTool": ""}) == {}     # empty clears


# --- serialization round-trip ------------------------------------------------
def test_guidance_config_round_trips():
    workspace = Workspace(id="ws:1", name="n", guidance_config={"mergeProcess": "rebase"})
    restored = workspace_from_dict(workspace_to_dict(workspace))
    assert restored.guidance_config == {"mergeProcess": "rebase"}


def test_missing_guidance_config_loads_empty():
    restored = workspace_from_dict({"id": "ws:1", "name": "n"})   # a pre-feature file
    assert restored.guidance_config == {}


# --- describe surface --------------------------------------------------------
def test_describe_page_type_surfaces_workspace_guidance():
    described = describe_page_type(LIFECYCLE)
    entries = {wg["field"]: wg for wg in described["workspaceGuidance"]}
    assert entries["buildTool"]["guidanceFor"] == ["building", "review"]
    assert entries["reviewHint"]["description"] == "a hint shown while reviewing"
    # A type with none carries an empty list, not a missing key.
    assert describe_page_type(get_page_type("test-fields"))["workspaceGuidance"] == []


# --- configurable-field set --------------------------------------------------
def test_configurable_fields_are_the_fixtures_in_test_mode():
    fields = workspace_guidance_fields()
    assert set(fields) == {"buildTool", "reviewHint", "draftHint"}
    # The production fields are not offered while in test mode.
    assert "mergeProcess" not in fields and "testingTool" not in fields
    assert fields["buildTool"].guidance_for == ("building", "review")


# --- store.set_workspace_guidance --------------------------------------------
def test_set_workspace_guidance_persists_and_validates(store):
    workspace = store.create_workspace("demo")
    wid = workspace.id
    store.set_workspace_guidance(wid, "buildTool", "use pytest")
    assert store.load_workspace(wid).guidance_config == {"buildTool": "use pytest"}
    # Empty string is accepted (a clear).
    store.set_workspace_guidance(wid, "buildTool", "")
    assert store.load_workspace(wid).guidance_config == {"buildTool": ""}
    # An undeclared field is rejected, naming the declared ones.
    with pytest.raises(ValidationError, match="not a workspace guidance field"):
        store.set_workspace_guidance(wid, "nope", "x")


# --- store.next_actions guidance injection -----------------------------------
def test_next_actions_injects_guidance_for_focused_page(store):
    workspace = store.create_workspace("demo")
    wid = workspace.id
    page = store.create_page(wid, "test-lifecycle", "F").page
    pid = page.id
    store.set_workspace_guidance(wid, "buildTool", "use pytest")
    store.set_workspace_guidance(wid, "reviewHint", "look hard")

    store.set_page_status(wid, pid, "review")
    actions = store.next_actions(wid, pid)
    assert actions["guidance_buildTool"] == "use pytest"          # review in buildTool's set
    assert actions["guidance_reviewHint"] == "look hard"          # review in reviewHint's set
    # Stage guidance for the focused page is included too.
    assert actions["guidance"] == status_guidance(LIFECYCLE.fsm, "review")

    store.set_page_status(wid, pid, "building")
    actions = store.next_actions(wid, pid)
    assert actions["guidance_buildTool"] == "use pytest"          # building in buildTool's set
    assert "guidance_reviewHint" not in actions                   # building not in reviewHint's set


def test_next_actions_whole_workspace_has_no_guidance(store):
    workspace = store.create_workspace("demo")
    wid = workspace.id
    pid = store.create_page(wid, "test-lifecycle", "F").page.id
    store.set_workspace_guidance(wid, "draftHint", "drafting")
    actions = store.next_actions(wid, None)                       # no focused page
    assert not any(key.startswith("guidance") for key in actions)


# --- server tool + response keys ---------------------------------------------
def test_set_workspace_guidance_tool_and_response_keys(mcp):
    wid, pid = _building_lifecycle(mcp)
    result = call(mcp, "setWorkspaceGuidance",
                  {"workspaceId": wid, "field": "buildTool", "text": "use pytest"})
    assert result == {"workspaceId": wid, "field": "buildTool",
                      "guidanceConfig": {"buildTool": "use pytest"}}
    # A subsequent write response carries guidance_buildTool (page is at `building`), inside `next`.
    written = _mutate_server(mcp, {"workspaceId": wid, "pageId": pid,
                                   "commands": [{"command": "setSummary", "args": {"text": "S2"}}]})
    assert written["next"]["guidance_buildTool"] == "use pytest"
    # `next` is the payload nextActions returns for the page, so the two agree by construction.
    actions = call(mcp, "nextActions", {"workspaceId": wid, "pageId": pid})
    assert actions["guidance_buildTool"] == "use pytest"


def test_create_page_response_carries_workspace_guidance(mcp):
    wid = call(mcp, "createWorkspace", {"name": "demo"})["id"]
    call(mcp, "setWorkspaceGuidance", {"workspaceId": wid, "field": "draftHint", "text": "drafting"})
    created = call(mcp, "createPage", {"workspaceId": wid, "type": "test-lifecycle", "title": "F"})
    assert created["status"] == "draft"
    assert created["next"]["guidance_draftHint"] == "drafting"   # draft is in draftHint's set


def test_set_workspace_guidance_unknown_field_is_tool_error(mcp):
    wid = call(mcp, "createWorkspace", {"name": "demo"})["id"]
    with pytest.raises(ToolError, match="not a workspace guidance field"):
        call(mcp, "setWorkspaceGuidance", {"workspaceId": wid, "field": "nope", "text": "x"})


# --- production declarations -------------------------------------------------
# The production types are named from their own modules rather than read out of REGISTRY: test mode
# empties that map, and these assertions must keep covering what a live server serves.
_GROUNDING_STATUSES = {"simple-change": ("open",), "bug-report": ("open",),
                       "feature-brief": ("grounding",)}
_GROUNDING_TYPES = (_SIMPLE_CHANGE, _BUG_REPORT, _FEATURE_BRIEF)


def _declared(page_type):
    return {spec.field: spec for spec in page_type.workspace_guidance}


@pytest.mark.parametrize("page_type", _GROUNDING_TYPES, ids=lambda t: t.tag)
def test_grounding_tool_declared_at_the_reading_statuses(page_type):
    spec = _declared(page_type)[GROUNDING_TOOL_FIELD]
    assert spec.guidance_for == _GROUNDING_STATUSES[page_type.tag]
    assert spec.description == GROUNDING_TOOL_DESC


@pytest.mark.parametrize("page_type", _GROUNDING_TYPES, ids=lambda t: t.tag)
def test_grounding_tool_emits_only_at_the_reading_statuses(page_type):
    config = {GROUNDING_TOOL_FIELD: "query the code graph"}
    emitted = {status: workspace_guidance(page_type, status, config)
               for status in page_type.fsm.states}
    assert emitted == {
        status: ({"guidance_groundingTool": "query the code graph"}
                 if status in _GROUNDING_STATUSES[page_type.tag] else {})
        for status in page_type.fsm.states}


def test_grounding_tool_is_a_configurable_field_in_production(production_mode):
    fields = workspace_guidance_fields()
    assert GROUNDING_TOOL_FIELD in fields
    assert fields[GROUNDING_TOOL_FIELD].description == GROUNDING_TOOL_DESC


def test_existing_guidance_placements_are_unchanged():
    placements = {(page_type.tag, spec.field): spec.guidance_for
                  for page_type in _GROUNDING_TYPES
                  for spec in page_type.workspace_guidance
                  if spec.field != GROUNDING_TOOL_FIELD}
    assert placements == {
        ("simple-change", MERGE_PROCESS_FIELD): ("review", "done"),
        ("simple-change", TESTING_TOOL_FIELD): ("open",),
        ("bug-report", MERGE_PROCESS_FIELD): ("review", "done"),
        ("bug-report", TESTING_TOOL_FIELD): ("open",),
        ("feature-brief", MERGE_PROCESS_FIELD): ("review",),
        ("feature-brief", TESTING_TOOL_FIELD): ("building",),
    }
