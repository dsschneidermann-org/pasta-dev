"""The descriptions of the workspace-configurable guidance fields.

A page type declares a `WorkspaceGuidanceSpec` under one of its sections naming a field, the
statuses that field surfaces at, and a description of what the field means. The DESCRIPTIONS live
here, beside `_stage_guidance.py`, so a field several page types declare says the same thing
everywhere - the load-time validator rejects a field whose description disagrees across types, and
sourcing it from one constant is how they agree. The stored TEXT itself is not here: it is mutable
per workspace, set at runtime through `setWorkspaceGuidance`.

Like `_stage_guidance.py` this module imports NOTHING - not the package, not core, not the standard
library - so it stays clear of the partially-initialized-package hazard, and its leading underscore
sorts it above every page-type module that draws on it.

A field name is a constant too, so the same string names the field in every declaration and cannot
drift into a second, silently-separate field.
"""


MERGE_PROCESS_FIELD = "mergeProcess"
MERGE_PROCESS_DESC = (
    "How this workspace integrates finished work when shipping - for example, rebase onto main "
    "with no merge commit, or merge through a pull request."
)

TESTING_TOOL_FIELD = "testingTool"
TESTING_TOOL_DESC = (
    "The test runner and command this workspace uses to write and run tests - for example, "
    "pytest, run with --testmon for red-green testing."
)
