"""The animated concept figures (tools/motion_figures.py, docs/img/motion/*.svg) match their sources.

Without CadQuery these tests check:
* the committed SVGs against the generator;
* each figure's fixture against the test or bench it copies;
* the figures' own rules (self-contained, labelled, sized, a reduced-motion still).

With CadQuery they also check each 2D model against the real code it stands for:
* the motion gate on the gate bench;
* the hole check on the counterbore plate;
* the connector sweep in 3D;
* the cable bend on CAD solids.
"""
import ast
import importlib.util
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("motion_figures", ROOT / "tools" / "motion_figures.py")
mf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mf)
BENCH_PY = ROOT / "tests" / "fixtures" / "gate_bench" / "build.py"


def literal(path: Path, name: str):
    """A module-level literal (``NAME = ...`` or ``NAME: T = ...``) read from source, without importing it."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise KeyError(name)


def before(path: Path, marker: str) -> dict:
    """The names a test module defines before ``marker`` (its CadQuery-only part)."""
    ns: dict = {}
    exec(compile(path.read_text(encoding="utf-8").split(marker)[0], str(path), "exec"), ns)
    return ns


def test_committed_figures_match_their_sources():
    assert mf.main(["--check"]) == 0


@pytest.mark.parametrize("name", sorted(mf.FIGURES))
def test_each_figure_stands_alone_is_labelled_sized_and_has_a_still(name):
    s = (mf.OUT / name).read_text(encoding="utf-8")
    head = re.match(r"<svg [^>]*>", s).group(0)
    assert len(s.encode()) < 14_000, "keep the figures small"
    assert 'role="img"' in head and re.search(r'aria-label="[^"]{60,}"', head)
    assert re.search(r'\swidth="\d+"', head) and re.search(r'\sheight="\d+"', head)
    assert f'<rect width="680" height="' in s and f'fill="{mf.BG}"' in s           # its own light background
    assert "@media (prefers-reduced-motion:reduce){*{animation:none!important}}" in s
    assert "@keyframes" in s
    # narrow: drawn 400 px wide or less (a 360 px phone), every label hides except large ones that still read
    assert f"@media (max-width:{mf.NARROW_PX}px){{text:not(.n),.w{{visibility:hidden}}.n{{visibility:visible}}}}" in s
    narrow = re.findall(r'<text [^>]*class="n"[^>]*>', s)
    assert len(narrow) >= 3, name
    for tag in narrow:
        size = float(re.search(r'font-size="([\d.]+)"', tag).group(1))
        assert size >= mf.NARROW_MIN_SIZE and size * 324 / 680 >= 11, (name, tag)
    # an <img> loads nothing else and runs no script: no scripts, links, outside images or fonts
    assert not re.search(r"<script|<foreignObject|<image|href=|@import|@font-face|url\((?!#)", s, re.I)


def test_every_figure_is_shown_on_a_page_with_a_caption():
    pages = {p: p.read_text(encoding="utf-8") for p in (ROOT / "docs").glob("*.md")}
    for name in mf.FIGURES:
        hits = [(p, t) for p, t in pages.items() if f"img/motion/{name}" in t]
        assert hits, f"{name} is not on any docs page"
        for p, t in hits:
            after = t.split(f"img/motion/{name})", 1)[1].lstrip("\n")
            assert after.startswith("*") and "illustration" in after.split("\n\n")[0].lower(), (p, name)


# ----------------------------------------------------------------------------- the fixtures are the tests' own

def test_hinge_figure_draws_the_bench_seed():
    assert literal(BENCH_PY, "PIVOT") == mf.BENCH["pivot"]
    assert tuple(literal(BENCH_PY, "PARAMS")["flap_range_deg"]) == mf.BENCH["default_range_deg"]
    seed = literal(BENCH_PY, "SEEDS")[mf.BENCH["seed"]]
    assert seed["gate"] == "motion" and tuple(seed["params"]["flap_range_deg"]) == mf.BENCH["range_deg"]


def test_hinge_model_follows_the_gate_rules():
    h = mf.hinge_numbers()
    assert len(h["samples"]) == 12 and h["samples"][0] == 0 and h["samples"][-1] == 60
    assert h["last_clear"] < h["onset"][0] < h["onset"][1] <= h["first"]
    assert h["onset"][1] - h["onset"][0] == pytest.approx(h["step_deg"] / 2 ** h["refine_steps"])
    assert h["max_travel_per_step_mm"] == pytest.approx(4.322, abs=1e-3)


def test_counterbore_model():
    h = mf.counterbore_numbers()
    assert h["after"]["D6.4"] > 5 and h["after"]["D3.4"] > h["min_volume_mm3"]   # as test_holes asserts, and more
    assert h["last"] == {"D6.4": 0.0, "D3.4": 0.0}


def test_connector_figure_draws_the_tests_port():
    ns = before(ROOT / "tests" / "test_connectors.py", 'cq = pytest.importorskip("cadquery")')
    assert ns["rj45_mate"]() == mf.RJ45 and tuple(ns["WALL"]) == mf.WALL
    assert f"bad = {mf.BBOX_WINDOW}" in (ROOT / "tests" / "test_connectors.py").read_text(encoding="utf-8")
    h = mf.connector_numbers()
    assert h["passing"] == ["plug body + latch lever"]
    assert h["interference_mm3"]["bad"] == pytest.approx(11.7 * 0.5 * 3.0)        # the latch's 0.5 mm, through 3 mm
    assert h["interference_mm3"]["good"] == 0 and h["margins"]["good"]["min_margin_mm"] == pytest.approx(0.5)


def test_cable_figure_runs_the_check_on_the_tests_port():
    from cadagent.mechanical import connectors as cn
    ns = before(ROOT / "tests" / "test_connectors.py", 'cq = pytest.importorskip("cadquery")')
    assert ns["CAT6"] == mf.CAT6 and ns["SHELF"] == mf.SHELF and ns["rj45_mate"]() == mf.RJ45
    h = mf.cable_numbers()
    mate = dict(ns["rj45_mate"](), cable=ns["CAT6"])
    assert h["result"] == cn.cable_bend(mate, {"wall": ns["wall_boxes"](cn.window(mate, ns["WALL"])), "shelf": ns["SHELF"]})
    down, up = h["rows"]["-v"], h["rows"]["+v"]
    ue, ve, we = h["result"]["exit"]
    # the drawn gap runs from under the cable where it leaves the boot down to the shelf: that is the check's
    assert up["clearance_mm"] == pytest.approx(ve - mf.CAT6["od"] / 2 - mf.SHELF["v"][1], abs=1e-3)
    assert down["clearance_mm"] == pytest.approx(ve - mf.SHELF["v"][1] - h["result"]["reach_mm"]["beside"], abs=1e-3)
    s = (mf.OUT / "cable-bend.svg").read_text(encoding="utf-8")
    for said in ("1.35 mm into the shelf", "clear, 26.7 mm from the shelf", "R 25 inside", "needs 31.1 mm below",
                 "the shelf is 29.75 below", "pass: turn +v (+u and −u clear too)"):
        assert said in s, said


def test_subassembly_figure_runs_the_tests_fixture():
    from tests.test_gate_subassembly import fixture
    boxes, specs, module, steps = fixture()
    assert boxes == mf.SUB_BOXES and module == mf.SUB_MODULE and steps == mf.SUB_STEPS
    assert {k: {"clamps": s.clamps, "into": s.into, "axes": [tuple(map(tuple, a)) for a in s.axes]}
            for k, s in specs.items()} == {k: {**f, "axes": [tuple(map(tuple, a)) for a in f["axes"]]}
                                           for k, f in mf.SUB_FASTENERS.items()}
    h = mf.subassembly_numbers()
    assert h["failed"] == [] and h["qualified"] == "pass" and h["bench_step_2"].endswith("touching carrier")
    assert h["service"]["status"] == "pass" and h["service"]["prerequisite_removal_verified"] is False
    assert h["steps"][1]["clearance_at_least_mm"] == pytest.approx(0.8)
    assert all(q == ("board", "carrier") for q in h["queries"])      # the parent steps needed no exact query


def test_search_figure_ranks_trials_as_the_leaderboard_does():
    h = mf.search_numbers()
    s = h["summary"]
    assert len(h["records"]) == s["trials"] and len(h["fronts"][-1]) == s["pareto"]
    assert sum(1 for r in h["records"] if not r.get("duplicate_of")) == s["evaluated"]


def test_motion_trace_figure_runs_the_validator_on_the_tests_shaft():
    from cadagent.mechanical.motion_trace import required_poses, validate_motion_trace
    from tests.test_motion_trace import contract, observation, trace
    c = contract()
    assert c == mf.MT_CONTRACT and "48 if defect == \"offset-pivot\"" in (ROOT / "tests" / "test_motion_trace.py").read_text()
    h = mf.motion_trace_numbers()
    assert h["poses"] == required_poses(c)
    for i, pose in enumerate(h["poses"]):         # the figure's renderers are the test's, landmark for landmark
        for drawn, defect in ((h["A"]["points"][i], None), (h["B"]["points"][i], "offset-pivot")):
            want = observation(c, pose, defect)
            assert drawn.keys() == want.keys()
            for name in want:
                assert max(math.dist(p, q) for p, q in zip(drawn[name], want[name])) < 1e-12, (pose, name)
    assert h["A"]["report"] == validate_motion_trace(c, trace(c))
    assert h["B"]["report"] == validate_motion_trace(c, trace(c, "offset-pivot"))
    a, b = h["A"]["report"], h["B"]["report"]
    assert a["status"] == "pass" and b["status"] == "fail" and h["nested"] == [len(h["poses"]) - 1]
    rotor = b["components"]["rotor"]
    assert rotor["max_error_mm"] == pytest.approx(2 * mf.MT_OFFSET) == pytest.approx(rotor["max_anchor_error_mm"])
    # each pose's worst error is the distance from the drawn landmark to the reference ring around it
    for i, ref in enumerate(h["reference"]):
        for key in ("A", "B"):
            far = max(math.dist(p, q) for n in ref for p, q in zip(ref[n], h[key]["points"][i][n]))
            assert h[key]["per_pose_mm"][i] == pytest.approx(far, abs=1e-9)
    assert max(h["A"]["per_pose_mm"]) < h["tolerance_mm"] == 0.01
    assert [round(e, 1) for e in h["B"]["per_pose_mm"]] == [0, 0, 0, 0, 0, 67.9, 96.0, 67.9, 0, 96.0]
    assert h["without_nested"]["status"] == "fail"
    # the checks the figure names, and the pose it says is missing, are the reports'
    assert [(f["check"], f["missing_poses_deg"]) for f in h["without_nested"]["failures"]] == \
        [("pose-coverage", [h["poses"][h["nested"][0]]])]
    assert [(f["check"], f["component"]) for f in b["failures"]] == [("rendered-landmarks", "rotor")]
    s = (mf.OUT / "motion-trace.svg").read_text(encoding="utf-8")
    for said in ("A: pass. At all 10 poses, every landmark is within 0.01 mm",
                 "B: fail (rendered-landmarks). Its rotor is 96.0 mm off at spin 180°: twice its pivot's 48 mm offset.",
                 "yaw −90° with spin 180° is missing", ">67.9<", "pivot 48 mm off the shaft"):
        assert said in s, said


def test_sweep_figure_runs_the_gate_on_the_tests_boxes():
    from cadagent.review.gates.assembly import AccessOptions, direction_vector, sweep_pair
    from tests.test_gate_assembly import BOXES, BoxWorld
    source = (ROOT / "tests" / "test_gate_assembly.py").read_text(encoding="utf-8")
    assert BOXES == mf.GATE_BOXES and f"card={mf.GATE_NEAR_CARD})" in source
    assert f"BoxWorld({mf.GATE_DIAGONAL})".replace("'", '"') in source
    assert f"direction_vector({mf.GATE_DIAGONAL_DIRECTION}), \"block\", options=AccessOptions(max_step_mm=" \
           f"{mf.GATE_DIAGONAL_STEP_MM:g}))" in source
    h = mf.sweep_numbers()
    # watched, the gate returns what the tests' own world gets from it: the spy changes nothing
    near, blocked, diag = h["near"]["result"], h["blocked"]["result"], h["diagonal"]["result"]
    assert near == sweep_pair(BoxWorld(dict(BOXES, card=mf.GATE_NEAR_CARD)), "card", direction_vector("-Z"), "block")
    assert blocked == sweep_pair(BoxWorld(BOXES), "card", direction_vector("-Z"), "cover")
    assert diag == sweep_pair(BoxWorld(mf.GATE_DIAGONAL), "part", direction_vector(mf.GATE_DIAGONAL_DIRECTION), "block",
                              options=AccessOptions(max_step_mm=mf.GATE_DIAGONAL_STEP_MM))
    # 1: the swept box alone decides it
    assert near["state"] == "clear" and near["samples"] == 0 and near["gap_lower_bound_mm"] == h["near"]["swept_gap"] == 3
    assert near["travel_mm"] == 21 and h["near"]["visits"] == []
    # 3: the samples the figure draws are the gate's: the seat, then each exact one; the bound is the least V
    d = h["diagonal"]
    assert d["swept_gap"] == 0 and diag["samples"] == 1 + sum(v["exact"] for v in d["visits"])
    assert [v["exact"] for v in d["visits"]] == [True, True, True, False, False]
    assert all(v["box_gap"] >= mf.GATE_DIAGONAL_STEP_MM for v in d["visits"] if not v["exact"])
    for (s1, g1), (s2, _) in zip(h["line"], h["line"][1:]):
        assert s1 - s2 == pytest.approx(max(g1, mf.GATE_DIAGONAL_STEP_MM)) or s2 == 0      # each step: the gap
    low = min(b for *_, b in h["bounds"])
    assert diag["gap_lower_bound_mm"] == round(low, 4) and diag["min_gap_mm"] == round(
        min([d["seat_gap"]] + [v["gap"] for v in d["visits"] if v["exact"]]), 4)
    cs, cg = h["closest"]
    assert cg == pytest.approx(2.5 * math.sqrt(2)) and cs == pytest.approx(17.5 * math.sqrt(2), abs=1e-6)
    assert low <= cg <= diag["min_gap_mm"] and all(g >= low for _, g in h["true"])
    for s1, s2, g1, g2, b in h["bounds"]:         # the exact gap never dips under the V between two samples
        assert all(g >= b - 1e-9 for s, g in h["true"] if s2 <= s <= s1)
    # 2: the hit, and its contact bisected refine_steps times
    k = h["blocked"]
    assert blocked["state"] == "blocked" and blocked["first_contact_mm"] == [25.0, 24.9998]
    assert [(v["s"], v["gap"], v["overlap_mm3"]) for v in k["visits"]] == [(26, 1, None), (25, 0, None), (24, None, 40)]
    assert len(k["bisect"]) == AccessOptions().refine_steps and k["seat_gap"] == 5
    assert blocked["samples"] == 1 + len(k["visits"]) + len(k["bisect"]) == 16
    s = (mf.OUT / "insertion-sweep.svg").read_text(encoding="utf-8")
    assert h["options"].margin_mm == 1 and near["travel_mm"] == 20 + h["options"].margin_mm   # the block's top is 20 up
    for said in ("it starts 1 mm past the block: travel 21 mm", "clear, ≥ 3.00 mm, with 0 queries", "seat first: gap 5.00", "s 24: 40 mm³ shared, a hit",
                 "[25, 24] halved 12 times", "first contact between s 24.9998 and 25.0000",
                 "blocked 25.00 mm before its seat, 16 queries", "≥ (4.030 + 4.679 − 5) / 2 ≈ 1.85",
                 "clear: the closest approach lies between 1.85 and 4.03 mm; 4 queries", "dotted: the exact gap (not computed), least 3.54"):
        assert said in s, said


# ----------------------------------------------------------------------------- against the real code (CadQuery)

def test_hinge_numbers_are_the_motion_gates():
    cq = pytest.importorskip("cadquery")
    gb = sys.modules.get("gate_bench_build")         # test_gate_bench.py's copy, when it ran first
    if gb is None:
        spec = importlib.util.spec_from_file_location("gate_bench_build", BENCH_PY)
        gb = importlib.util.module_from_spec(spec)
        sys.modules["gate_bench_build"] = gb          # dataclasses need the module registered
        spec.loader.exec_module(gb)
    from cadagent.review.gates.motion import motion_gate
    bench = gb.build(mf.BENCH["seed"])
    assert gb.PIVOT == mf.BENCH["pivot"]
    arm = cq.Shape.cast(bench.shape("arm")).BoundingBox()
    assert arm.ymax - arm.ymin == pytest.approx(mf.BENCH["arm_thickness"])
    # the figure is the section through the arm; the hinge block, just behind it, is drawn dashed. The base is cut
    # to the arm's Y band: its boss, which carries another part, lies outside it
    band = cq.Solid.makeBox(400, arm.ymax - arm.ymin, 400, cq.Vector(-100, arm.ymin, -100))
    for part in ("arm", "stop", "hinge_block", "frame", "base"):
        shape = cq.Shape.cast(bench.shape(part))
        bb = (shape.intersect(band) if part == "base" else shape).BoundingBox()
        want = mf.BENCH[part] if part != "frame" else (mf.BENCH["beam"][0], mf.BENCH["post"][1], mf.BENCH["post"][2],
                                                        mf.BENCH["beam"][3])
        assert (bb.xmin, bb.zmin, bb.xmax, bb.zmax) == pytest.approx(want, abs=1e-6), part
    v = motion_gate(bench.assembly, intended_overlaps=bench.declarations["intended_overlaps"])
    ev = next(c for c in v["checks"] if c["id"] == "collision:arm|frame")["evidence"]
    h = mf.hinge_numbers()
    angle = lambda label: float(re.search(r"=([-\d.]+)deg", label).group(1))
    assert ev["poses"] == len(h["samples"]) and ev["colliding_poses"] == len(h["hits"])
    assert angle(ev["first_pose"]) == pytest.approx(h["first"], abs=1e-3)
    assert angle(ev["last_clear_pose"]) == pytest.approx(h["last_clear"], abs=1e-3)
    assert angle(ev["worst_pose"]) == pytest.approx(h["worst"], abs=1e-3)
    assert ev["overlap_mm3"] == pytest.approx(h["first_mm3"], rel=1e-4)
    assert ev["worst_overlap_mm3"] == pytest.approx(h["worst_mm3"], rel=1e-4)
    assert ev["last_clear_gap_mm"] == pytest.approx(h["last_clear_gap_mm"], abs=1e-4)
    assert [ev["onset"]["clear"], ev["onset"]["hit"]] == pytest.approx(list(h["onset"]), abs=1e-5)


def test_counterbore_numbers_are_the_hole_checks():
    pytest.importorskip("cadquery")
    from cadagent.mechanical import holes
    from tests.test_holes import plate_with_counterbore
    h = mf.counterbore_numbers()
    after = holes.check_shape(plate_with_counterbore(rib_after_holes=True))
    found = {f"D{f['diameter_mm']:g}": f["intrusion_mm3"] for f in after["findings"]}
    assert found == pytest.approx(h["after"], rel=1e-3)
    last = holes.check_shape(plate_with_counterbore(rib_after_holes=False))
    assert last["pass"] and last["holes"] == 2 and not last["findings"]


def test_connector_sweep_is_check_ports():
    pytest.importorskip("cadquery")
    from cadagent.mechanical import connectors as cn
    from tests.test_connectors import wall_with
    h = mf.connector_numbers()
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    for case in ("bad", "good"):
        win = h[case]
        r = cn.check_ports({"lan": mf.RJ45}, {"lan": frame}, {"wall": wall_with(win, frame)}, {"lan": mf.WALL},
                           {"lan": win})
        assert r["ports"]["lan"]["sweep_interference_mm3"]["wall"] == pytest.approx(h["interference_mm3"][case], abs=1e-3)
        assert r["pass"] == (case == "good")


def test_cable_figure_numbers_are_the_check_on_cad_shapes():
    pytest.importorskip("cadquery")
    from cadagent.mechanical import connectors as cn
    from tests.test_connectors import wall_with, world_box
    h = mf.cable_numbers()
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    r = cn.cable_bend(h["mate"], {"wall": wall_with(h["window"], frame), "shelf": world_box(frame, mf.SHELF)}, frame)
    for a, b in zip(h["result"]["directions"], r["directions"]):
        assert a["clearance_by_part_mm"] == pytest.approx(b["clearance_by_part_mm"], abs=1e-3), a["direction"]
    assert (r["status"], r["direction"], r["works"]) == (h["result"]["status"], "+v", h["result"]["works"])
