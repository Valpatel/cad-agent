"""The catalogue's compare cover (docs/img/explore/two-wheel-charts.json) matches the tool's output.

tools/explore_charts.py runs ``cad-agent compare`` on examples/explore-two-wheel; these tests run it with ``--check``
and check that what the cover draws is what the tool said.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "img" / "explore" / "two-wheel-charts.json"


def test_committed_numbers_are_the_tools_output():
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "explore_charts.py"), "--check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_what_the_covers_show():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    compare = {p["label"]: p for p in data["compare"]["points"]}
    assert set(compare) == {"Light", "Standard", "Strong", "Long range"}
    # The front is over every objective: Standard is on it although Light is cheaper and lighter.
    assert data["compare"]["front_over"] == ["cost", "mass", "runtime"]
    assert [n for n, p in compare.items() if p["front"]] == ["Light", "Standard"]
    assert compare["Standard"]["x"] > compare["Light"]["x"] and compare["Standard"]["y"] > compare["Light"]["y"]
    # Long range fails a constraint, and its cost leaves out the unpriced depth camera: a lower bound (≥).
    assert not compare["Long range"]["feasible"] and compare["Long range"]["lower_bound"] == ["cost_usd"]
