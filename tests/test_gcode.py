"""cadagent.manufacturing.gcode: the bridge and overhang-perimeter extrusions in sliced G-code.

The two fixtures are excerpts of real PrusaSlicer 2.9.4 slices (relative extrusion, arcs, wipes); the Bambu Studio
and absolute-extrusion cases are written here, in the slicers' own comment format."""
from __future__ import annotations

import math
import zipfile
from pathlib import Path

import pytest

from cadagent.manufacturing.gcode import bridge_report, extrusions

FIXTURES = Path(__file__).parent / "fixtures" / "gcode"


def test_prusaslicer_bridge_infill_lines_are_ranked_by_length():
    r = bridge_report(FIXTURES / "prusaslicer-bridge-infill.gcode", n=3)
    assert r["slicer"].startswith("PrusaSlicer 2.9.4") and r["labelled"]
    assert set(r["features"]) == {"Bridge infill"}
    top = r["longest"][0]
    assert top["start_mm"] == [183.527, 183.53] and top["end_mm"] == [176.468, 176.47]
    assert top["length_mm"] == pytest.approx(math.hypot(183.527 - 176.468, 183.53 - 176.47), abs=1e-3)
    assert (top["kind"], top["z_mm"], top["height_mm"], top["arc"]) == ("bridge", 1.8, 0.4, False)
    assert [e["length_mm"] for e in r["longest"]] == sorted((e["length_mm"] for e in r["longest"]), reverse=True)
    assert len(r["longest"]) == 3
    summary = r["features"]["Bridge infill"]
    # the block's arcs are bridge extrusions too: counted, with their arc length, and never merged with a line
    arcs = [e for e in extrusions(open(FIXTURES / "prusaslicer-bridge-infill.gcode")) if e["arc"]]
    assert arcs and all(e["moves"] == 1 for e in arcs)
    assert summary["extrusions"] > len(arcs) and summary["longest_mm"] == top["length_mm"]


def test_split_overhang_perimeter_is_one_extrusion():
    # PrusaSlicer writes the 32.7 mm overhang perimeter as two collinear moves (a speed change between them)
    r = bridge_report(FIXTURES / "prusaslicer-overhang-perimeter.gcode")
    top = r["longest"][0]
    assert (top["feature"], top["kind"], top["moves"], top["z_mm"]) == ("Overhang perimeter", "overhang", 2, 14.0)
    assert top["start_mm"] == [152.112, 163.671] and top["end_mm"] == [152.112, 196.329]
    assert top["length_mm"] == pytest.approx(196.329 - 163.671, abs=1e-3)
    assert [e["feature"] for e in r["longest"]] == ["Overhang perimeter"] * 3   # the perimeters around it are not listed


BAMBU = """\
; HEADER_BLOCK_START
; BambuStudio 01.10.01.50
; HEADER_BLOCK_END
; layer_height = 0.2
G90
M83
G1 Z0.2 F600
; CHANGE_LAYER
; Z_HEIGHT: 4.2
; LAYER_HEIGHT: 0.2
G1 Z4.2
G1 X10 Y10 F12000
; FEATURE: Outer wall
; LINE_WIDTH: 0.42
G1 X60 Y10 E2.0
; FEATURE: Bridge
G1 X10 Y20 F12000
G1 X50 Y20 E1.5
G1 X50 Y20.5 E0.02
G1 X10 Y20.5 E1.5
G1 E-0.8 F1800
G1 X10 Y30 F12000
G1 E0.8 F1800
; FEATURE: Internal Bridge
G1 X40 Y30 E1.0
G1 X70 Y30 E1.0
G91
G1 Z0.4
G1 X5 Y0
G90
; FEATURE: Overhang wall
G3 X85 Y30 I5 J0 E0.6
G2 X95 Y30 R5 E0.6
G2 X95 Y30 I5 J0 E1.9
"""


def test_bambu_studio_features_relative_moves_and_arcs(tmp_path):
    path = tmp_path / "plate.gcode"
    path.write_text(BAMBU)
    r = bridge_report(path, n=20)
    assert r["slicer"] == "BambuStudio 01.10.01.50"
    rows = r["longest"]
    assert {e["feature"] for e in rows} == {"Bridge", "Internal Bridge", "Overhang wall"}    # not the outer wall
    # two collinear moves are one 60 mm extrusion; the retraction and travel end the bridge before it
    internal = next(e for e in rows if e["feature"] == "Internal Bridge")
    assert (internal["length_mm"], internal["moves"], internal["start_mm"], internal["end_mm"]) == (
        60.0, 2, [10.0, 30.0], [70.0, 30.0])
    assert [e["length_mm"] for e in rows if e["feature"] == "Bridge"] == [40.0, 40.0, 0.5]
    assert all(e["z_mm"] == 4.2 and e["height_mm"] == 0.2 for e in rows if "Bridge" in e["feature"])
    # G91 moves are relative: the arcs start at X75 Y30, Z4.6
    arcs = sorted((e for e in rows if e["arc"]), key=lambda e: e["line"])
    assert [e["start_mm"] for e in arcs] == [[75.0, 30.0], [85.0, 30.0], [95.0, 30.0]]
    assert arcs[0]["length_mm"] == pytest.approx(math.pi * 5, abs=1e-3)          # G3 about X80: half circle
    assert arcs[1]["length_mm"] == pytest.approx(math.pi * 5, abs=1e-3)          # R5 over a 10 mm chord: half circle
    assert arcs[2]["length_mm"] == pytest.approx(2 * math.pi * 5, abs=1e-3)      # start == end with I/J: full circle
    assert all(e["z_mm"] == 4.6 for e in arcs)
    assert r["features"]["Overhang wall"]["extrusions"] == 3


def test_absolute_extrusion_and_g92(tmp_path):
    path = tmp_path / "abs.gcode"
    path.write_text("M82\nG92 E0\n;TYPE:Bridge infill\nG1 X0 Y0 F9000\nG1 X30 Y0 E1.0\nG1 X30 Y5 E1.0\n"
                    "G1 X0 Y5 E2.0\nG92 E0\nG1 X0 Y40 E1.0\nG1 X0 Y50 E0.5\n")
    rows = bridge_report(path)["longest"]
    # E1.0 -> E1.0 is no filament (a move, ending the first line); E2.0 is; after G92 E0, E1.0 is again
    assert [(e["length_mm"], e["start_mm"]) for e in rows] == [(35.0, [0.0, 5.0]), (30.0, [0.0, 0.0]), (30.0, [30.0, 5.0])]


def test_custom_features_inches_and_no_labels(tmp_path):
    path = tmp_path / "in.gcode"
    path.write_text("G20\nM83\n;TYPE:Support material interface\nG1 X0 Y0\nG1 X1 Y0 E0.1\n")
    assert bridge_report(path)["longest"] == []
    r = bridge_report(path, features={"Support material interface": "bridge"})
    assert r["longest"][0]["length_mm"] == pytest.approx(25.4)
    unlabelled = tmp_path / "plain.gcode"
    unlabelled.write_text("M83\nG1 X0 Y0\nG1 X10 Y0 E1\n")
    r = bridge_report(unlabelled)
    assert (r["labelled"], r["longest"], r["slicer"]) == (False, [], None)
    with pytest.raises(ValueError):
        bridge_report(unlabelled, n=-1)


def test_arcs_in_inches_and_binary_gcode(tmp_path):
    path = tmp_path / "arc.gcode"
    path.write_text("G20\nM83\n;TYPE:Overhang perimeter\nG1 X0 Y0\nG3 X2 Y0 I1 J0 E0.1\n")
    assert bridge_report(path)["longest"][0]["length_mm"] == pytest.approx(math.pi * 25.4, abs=1e-3)
    binary = tmp_path / "part.bgcode"
    binary.write_bytes(b"GCDE\x01\x00\x00\x00")
    with pytest.raises(ValueError, match="binary G-code"):
        bridge_report(binary)


def test_sliced_bambu_project_3mf(tmp_path):
    path = tmp_path / "part.gcode.3mf"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Metadata/plate_1.gcode", BAMBU)
        z.writestr("Metadata/plate_1.gcode.md5", "x")
    assert bridge_report(path, n=1)["longest"][0]["length_mm"] == 60.0
    empty = tmp_path / "unsliced.3mf"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
    with pytest.raises(ValueError, match="no .gcode"):
        bridge_report(empty)
