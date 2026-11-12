"""Source-review arithmetic and negative controls; never a board qualification."""
from decimal import Decimal as D
from pathlib import Path
import re

import pytest
from cadagent.review.references import load

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def observe():
    page = ROOT / "docs/pcb.md"
    blocks = re.findall(r"```python\n(.*?)\n```", page.read_text(), re.S)
    assert len(blocks) == 1
    namespace = {}
    exec(compile(blocks[0], str(page), "exec"), namespace)
    return namespace["selected_pcb_observation"]


def test_copper_side_and_exact_mil_conversion(observe):
    inner = observe("pcbway", "width-space", "normal-inner-70um-before-compensation")
    outer = observe("pcbway", "width-space", "normal-outer-70um-before-compensation")
    assert inner == (D("0.1524"), D("0.2032"))
    assert outer == (D("0.1778"), D("0.2032"))
    trace = D("6.5") * D("0.0254")
    assert trace >= inner[0] and trace < outer[0]
    assert outer[0] != D("0.1")  # planted headline replacement
    assert outer[0] != D("7") * D("0.001")  # planted mil/mm confusion


def test_service_substitution_rejects_pooled_example(observe):
    pooled = observe("eurocircuits", "width-space", "pooled")
    nonpooled = observe("eurocircuits", "width-space", "non-pooled")
    assert pooled == (D("0.100"),) * 2
    assert nonpooled == (D("0.090"),) * 2
    assert D("0.095") < pooled[0] and D("0.095") >= nonpooled[0]
    assert pooled[0] != D("100")  # micrometres are not millimetres


def test_finished_hole_pad_additions_are_diametral(observe):
    hole = D("0.600")
    outer = observe("eurocircuits", "pth-pad-diameter-addition", "outer-finished-hole")
    inner = observe("eurocircuits", "pth-pad-diameter-addition", "inner-finished-hole")
    assert (hole + outer, hole + inner) == (D("0.900"), D("0.950"))
    assert (outer / 2, inner / 2) == (D("0.150"), D("0.175"))
    assert hole + outer / 2 < hole + outer  # planted radial addition once


def test_profile_and_copper_side_are_independent(observe):
    outer = observe("eurocircuits", "copper-to-edge", "outer-routed")
    inner = observe("eurocircuits", "copper-to-edge", "inner-routed")
    assert outer == D("0.250") and inner == D("0.400")
    assert D("0.300") >= outer and D("0.300") < inner
    for side in ("inner", "outer"):
        assert observe("eurocircuits", "copper-to-edge", side + "-v-cut") == D("0.450")


@pytest.mark.parametrize("args", [
    ("pcbway", "width-space", "normal-outer-35um-before-compensation"),
    ("pcbway", "width-space", "normal-outer-70mm-before-compensation"),
    ("pcbway", "width-space", ""),
    ("eurocircuits", "pth-pad-diameter-addition", "outer-drill-tool"),
    ("eurocircuits", "copper-to-edge", "drill-centre-routed"),
    ("eurocircuits", "layer-pooling", "10"),
    ("eurocircuits", "finish-pooling", "immersion-silver"),
    ("other", "width-space", "pooled"),
])
def test_missing_scope_and_unresolved_choices_stay_unknown(observe, args):
    with pytest.raises(ValueError, match="confirm supplier"):
        observe(*args)


def test_readings_preserve_existing_identity_and_evidence_limits():
    reg = load()
    for key in ("pcbway-pcb-capabilities", "eurocircuits-standard-pool-services"):
        ref = reg.resolve(key)
        assert ref.data["evidence"]["class"] == "read"
        assert ref.data["confidence"] == {"level": "low", "estimate": 0.4, "sources": 1}
        assert "2026-11-12" in ref.data["verified"]
        assert "docs/pcb.md" in ref.data["used_for"]
        assert not ref.data.get("rules") and not ref.data.get("checks")
        assert ref.data["archive"]["redistribute"] is False
