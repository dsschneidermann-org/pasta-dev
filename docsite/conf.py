"""Sphinx configuration for the pasta MCP server documentation site.

Builds an HTML site. The page-type pages render each status finite-state machine as
a Mermaid diagram via ``sphinxcontrib.mermaid``, driven by python-statemachine's
``statemachine-diagram`` directive (``:format: mermaid``).
"""

import builtins
import inspect
import os
import sys

from sphinx import addnodes

# Make the `src` package importable so the statemachine-diagram directive can
# resolve the machine classes exposed in src.statecharts.
sys.path.insert(0, os.path.abspath(".."))

project = "pasta MCP"
author = "pasta"

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "statemachine.contrib.diagram.sphinx_ext",
    "autodoc2",
]

autodoc2_packages = [
    "../src",
]
autodoc2_render_plugin = "myst"
autodoc2_hidden_objects = ["inherited", "private"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

html_theme = "alabaster"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


def _resolve_builtins_exactly(app, doctree):
    """Look up a builtin class named in a signature by its exact name.

    Sphinx resolves signature names by suffix with a fallback to attributes, so a builtin such as
    `type` would otherwise match every documented attribute of that name. Remove once Sphinx's
    lookup itself resolves builtins exactly (sphinx-doc/sphinx#14223): a fix to how autodoc writes
    annotations does not reach the signatures autodoc2 writes.
    """
    for node in doctree.findall(addnodes.pending_xref):
        if (
            node.get("refdomain") == "py"
            and node.get("refspecific") is False
            and inspect.isclass(getattr(builtins, node.get("reftarget", ""), None))
        ):
            del node["refspecific"]


def setup(app):
    app.connect("doctree-read", _resolve_builtins_exactly)
