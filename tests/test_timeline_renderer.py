"""The timeline renderer (src/static/timeline/timeline.js): its pure core is checked by a node script
over the committed back-fill and fixtures, and the script and stylesheet are held to the clean, sharp
look - no glow, shadow, gradient or filter, and no colour that does not come from the theme."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src import lifecycle_log

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src" / "static" / "timeline" / "timeline.js"
NODE_CHECK = ROOT / "tests" / "timeline" / "check_timeline.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_node_check_passes_on_the_production_types(tmp_path, production_mode):
    types = tmp_path / "types.json"
    types.write_text(json.dumps(lifecycle_log.timeline_types()), encoding="utf-8")
    run = subprocess.run(["node", str(NODE_CHECK), "--types", str(types)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all checks passed" in run.stdout


def test_the_script_draws_no_glow_shadow_gradient_or_filter():
    source = SCRIPT.read_text(encoding="utf-8")
    for construct in ("shadowBlur", "shadowColor", "createLinearGradient", "createRadialGradient",
                      "globalCompositeOperation"):
        assert construct not in source, construct
    assert not re.search(r"\.filter\s*=", source)
    assert "ctx.filter" not in source


def test_the_script_hard_codes_no_colour():
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert not re.search(r"\b(?:rgba?|hsla?)\(", source)
