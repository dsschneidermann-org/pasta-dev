"""Sphinx configuration for the pasta MCP server documentation site.

Builds an HTML site. The page-type pages render each status finite-state machine as
a Mermaid diagram via ``sphinxcontrib.mermaid``, driven by python-statemachine's
``statemachine-diagram`` directive (``:format: mermaid``).
"""

import os
import sys

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
