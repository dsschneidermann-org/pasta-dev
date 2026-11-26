"""The docsite's Sphinx configuration, built in-process over a small fixture module.

The build reads docsite/conf.py itself but a throwaway source tree, so the fixture's generated API
reference is the only content and the repository is left untouched.
"""

import io
from pathlib import Path

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace, patch_docutils

CONFDIR = Path(__file__).resolve().parent.parent / "docsite"


def _api_reference_warnings(tmp_path: Path, module: str, builder: str = "dummy") -> str:
    package = tmp_path / "pkg.py"
    package.write_text(module, encoding="utf-8")
    srcdir = tmp_path / "docsite"
    srcdir.mkdir()
    (srcdir / "index.md").write_text("# API\n\n```{toctree}\napidocs/index\n```\n", encoding="utf-8")
    warnings = io.StringIO()
    with patch_docutils(CONFDIR), docutils_namespace():
        app = Sphinx(
            srcdir,
            CONFDIR,
            tmp_path / "out",
            tmp_path / "doctrees",
            builder,
            confoverrides={"autodoc2_packages": [str(package)]},
            status=None,
            warning=warnings,
            freshenv=True,
        )
        app.build()
    return warnings.getvalue()


def test_a_builtin_in_a_signature_is_not_matched_to_a_same_named_attribute(tmp_path: Path):
    module = "class A:\n    type: str\n\n\nclass B:\n    type: str\n\n\ndef f() -> type[int]: ...\n"

    assert "more than one target found" not in _api_reference_warnings(tmp_path, module)


def test_an_angle_bracket_placeholder_in_a_docstring_is_shown_as_text(tmp_path: Path):
    module = '"""The name defaults to set<Section>."""\n'

    _api_reference_warnings(tmp_path, module, builder="html")

    page = next((tmp_path / "out" / "apidocs").rglob("pkg.html")).read_text(encoding="utf-8")
    assert "set&lt;Section&gt;" in page
    assert "<Section>" not in page
