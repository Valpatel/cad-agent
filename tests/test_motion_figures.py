"""The animated concept figures (tools/motion_figures.py, docs/img/motion/*.svg) match their sources.

Without CadQuery these tests check:
* the committed SVGs against the generator;
* each figure's fixture against the test or bench it copies;
* the figures' own rules (self-contained, labelled, sized, a reduced-motion still).

With CadQuery they also check each 2D model against the real code it stands for:
* the motion gate on the gate bench;
* the hole check on the counterbore plate;
* the connector sweep in 3D.
"""
import ast
import importlib.util
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


# ----------------------------------------------------------------------------- against the real code (CadQuery)

def test_hinge_numbers_are_the_motion_gates():
    cq = pytest.importorskip("cadquery")
    gb = sys.modules.get("gate_bench_build")         # test_gate_bench.py's copy, when it ran first
    if gb is None:
        spec = importlib.util.spec_from_file_location("gate_bench_build", BENCH_PY)
        gb = importlib.util.module_from_spec(spec)
        sys.modules["gate_bench_build"] = gb          # dataclasses need the module registered
        spec.loader.exec_module(gb)
    from cadagent.gates.motion import motion_gate
    bench = gb.build(mf.BENCH["seed"])
    assert gb.PIVOT == mf.BENCH["pivot"]
    for part in ("arm", "stop", "hinge_block", "frame"):
        bb = cq.Shape.cast(bench.shape(part)).BoundingBox()
        want = mf.BENCH[part] if part != "frame" else (mf.BENCH["beam"][0], mf.BENCH["post"][1], mf.BENCH["post"][2],
                                                        mf.BENCH["beam"][3])
        assert (bb.xmin, bb.zmin, bb.xmax, bb.zmax) == pytest.approx(want, abs=1e-6), part
    arm = cq.Shape.cast(bench.shape("arm")).BoundingBox()
    assert arm.ymax - arm.ymin == pytest.approx(mf.BENCH["arm_thickness"])
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
    from cadagent import holes
    from tests.test_holes import plate_with_counterbore
    h = mf.counterbore_numbers()
    after = holes.check_shape(plate_with_counterbore(rib_after_holes=True))
    found = {f"D{f['diameter_mm']:g}": f["intrusion_mm3"] for f in after["findings"]}
    assert found == pytest.approx(h["after"], rel=1e-3)
    last = holes.check_shape(plate_with_counterbore(rib_after_holes=False))
    assert last["pass"] and last["holes"] == 2 and not last["findings"]


def test_connector_sweep_is_check_ports():
    pytest.importorskip("cadquery")
    from cadagent import connectors as cn
    from tests.test_connectors import wall_with
    h = mf.connector_numbers()
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    for case in ("bad", "good"):
        win = h[case]
        r = cn.check_ports({"lan": mf.RJ45}, {"lan": frame}, {"wall": wall_with(win, frame)}, {"lan": mf.WALL},
                           {"lan": win})
        assert r["ports"]["lan"]["sweep_interference_mm3"]["wall"] == pytest.approx(h["interference_mm3"][case], abs=1e-3)
        assert r["pass"] == (case == "good")
