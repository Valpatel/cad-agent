"""The animated snap-fit figure (#165): a printed cantilever engaging, drawn from cad-agent's snap-fit calculator.

The committed scene is what the calculator says today (it is re-run here: it is pure Python); its numbers are the
closed form worked by hand; the figure states them and is still at the top of the lead under reduced motion;
``tools/readme_anim.py --check`` and ``--extract snapfit`` round-trip; and the pages that show the figure say what it is.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest
import yaml

from cadagent.mechanical.compliant import snapfit as sf
from cadagent.mechanical.compliant.allowables import PRINTED
from cadagent.publish.anim import snapfit as F
from cadagent.publish.anim import svg

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tools" / "anim" / "snap-engagement.yaml"
SCENE = ROOT / "tools" / "anim" / "snap-engagement.scene.json"
FIGURE = ROOT / "docs" / "img" / "compliant" / "snap-engagement.svg"
# provenance a re-record changes without any number moving
VOLATILE = ("recorded", "record_seconds")


def _tool():
    spec = importlib.util.spec_from_file_location("readme_anim", ROOT / "tools" / "readme_anim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scene():
    return json.loads(SCENE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(scene, spec):
    return F.render(scene, spec["present"])


def _numbers_match(got, want, path="scene"):
    """Recursively equal, floats to 1e-7 relative (the scene keeps 9 significant figures)."""
    if isinstance(want, dict):
        assert set(got) == set(want), (path, sorted(set(got) ^ set(want)))
        for k in want:
            _numbers_match(got[k], want[k], f"{path}.{k}")
    elif isinstance(want, list):
        assert len(got) == len(want), path
        for i, (g, w) in enumerate(zip(got, want)):
            _numbers_match(g, w, f"{path}[{i}]")
    elif isinstance(want, float):
        assert got == pytest.approx(want, rel=1e-7, abs=1e-12), path
    else:
        assert got == want, path


# ---------------------------------------------------------------------------------------------- the record is today's

def test_the_committed_scene_is_what_the_calculator_says_today(spec, scene):
    """Re-run the record: every verdict, row, material derivation, curve point and crossing is unchanged. A change
    to the calculator or the allowables that moves a number fails here until the figure is recorded again
    (tools/readme_anim.py --extract snapfit)."""
    fresh = F.record(spec, ROOT, SPEC)
    for k in VOLATILE:
        fresh.pop(k, None)
    want = {k: v for k, v in scene.items() if k not in VOLATILE}
    # the code's provenance is when it was recorded, kept as written; the numbers must be today's
    fresh["source"] = want["source"]
    _numbers_match(fresh, want)


def test_the_numbers_are_the_closed_form_by_hand(scene):
    """Covestro Table 1 for a constant rectangular arm, worked by hand: eps = y h / (0.67 L^2), P = (b h^2 / 6) E eps
    / L, W = P (mu + tan a) / (1 - mu tan a); and the allowables from the data sheets' rule, 0.7 UTS / E in-plane."""
    a = scene["arm"]
    L, h, b, y = a["length_mm"], a["thickness_mm"], a["width_mm"], a["undercut_mm"]
    eps = y * h / (0.67 * L ** 2)
    assert eps == pytest.approx(0.0137977, rel=1e-5)
    copa, petg_cf = scene["snaps"]
    assert copa["strain"] == petg_cf["strain"] == pytest.approx(eps)          # geometry alone sets the strain
    # CoPA, dry, along the layers: 0.7 x 78.0 / 2703 (Polymaker's sheet V5.4), under the moulded PA66 cap of 4 %
    assert copa["material"]["allowable"] == pytest.approx(0.7 * 78.0 / 2703)
    assert copa["material"]["allowable"] == pytest.approx(0.0202, abs=5e-5)
    # Bambu PETG-CF: the V3.0 sheet's 35 MPa over 2460 MPa governs (V2.0's 59 MPa would allow 1.7 %)
    assert petg_cf["material"]["allowable"] == pytest.approx(0.7 * 35 / 2460)
    assert petg_cf["material"]["xy"]["sheet"] == "Bambu Lab PETG-CF Technical Data Sheet V3.0"
    assert copa["pass"] and not petg_cf["pass"]
    assert [r["check"] for r in petg_cf["rows"] if not r["pass"]] == ["root strain"]
    assert F.ratio(copa) == pytest.approx(0.683, abs=1e-3) and F.ratio(petg_cf) == pytest.approx(1.385, abs=1e-3)
    p = b * h ** 2 / 6 * 2703 * eps / L
    mu, t = 0.35 * 1.5, math.tan(math.radians(30))
    assert copa["deflection_force_n"] == pytest.approx(p)
    assert copa["mating_force_n"] == pytest.approx(p * (mu + t) / (1 - mu * t))
    assert copa["mating_force_n"] == pytest.approx(10.07, abs=0.01)
    assert copa["engagement"]["points"][2]["mating_force_n"] == pytest.approx(mu * p)       # the land: friction
    assert petg_cf["mating_force_n"] is None and petg_cf["material"]["friction"] is None    # PETG: not in Table 3
    # PETG-CF passes its allowable where the lift is allowable / eps of the undercut, up a lead of y / tan 30
    lead = y / t
    assert copa["engagement"]["lead_travel_mm"] == pytest.approx(lead)
    assert petg_cf["over_from_mm"] == pytest.approx(lead * petg_cf["material"]["allowable"] / eps)
    assert copa["over_from_mm"] is None
    assert not copa["warnings"] and y / L < 0.1                                # small deflection: no warning


def test_the_spec_is_a_snapfit_declaration_the_cli_checks(capsys):
    """`cad-agent snapfit` on the figure's own spec: the CoPA arm passes, the PETG-CF one fails, exit 1."""
    from cadagent.cli import main

    assert main(["snapfit", str(SPEC)]) == 1
    out = capsys.readouterr().out
    assert "PASS  copa-latch: root strain 1.38 % (allowed 2.02 %)" in out and "mating force 10.1 N" in out, out
    assert "FAIL  petg-cf-latch: root strain 1.38 % (allowed 1.00 %)" in out, out


def test_the_scene_names_the_editions_and_the_code(scene):
    src = scene["source"]
    assert set(F.CODE) <= set(src["inputs"]) and "tools/anim/snap-engagement.yaml" in src["inputs"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in src["inputs"].values())
    assert re.fullmatch(r"[0-9a-f]{40}", src["commit"]) and src["version"]
    for s in scene["snaps"]:
        m = s["material"]
        assert m["source"] == PRINTED[next(e["material"] for e in yaml.safe_load(SPEC.read_text())["snaps"]
                                           if e["name"] == s["name"])].source
        assert m["status"].startswith("derived from the datasheet; a hypothesis until a printed coupon")
    assert [F.sheet(s["material"]) for s in scene["snaps"]] == ["Polymaker PolyMide CoPA V5.4",
                                                                "Bambu Lab PETG-CF V3.0"]


def test_the_shape_is_the_formula(scene):
    from cadagent.formulas import cantilever_shape

    sh, n = scene["shape"], scene["drawing"]["slices"]
    assert len(sh["xi"]) == len(sh["deflection"]) == len(sh["slope"]) == n + 1 and sh["xi"][-1] == 1.0
    for x, d, s in zip(sh["xi"], sh["deflection"], sh["slope"]):
        assert d == pytest.approx(cantilever_shape(x, 1), abs=1e-6)
        assert s == pytest.approx(3 * x - 1.5 * x * x, abs=1e-5)                 # d/dxi of xi^2 (3 - xi) / 2


# ---------------------------------------------------------------------------------------------- the tool's --check

def test_the_committed_figure_is_its_scene(built):
    assert FIGURE.read_text(encoding="utf-8") == built, "run PYTHONPATH=src python3 tools/readme_anim.py"


def test_check_and_extract_round_trip(tmp_path, monkeypatch, capsys, scene):
    """--extract writes the scene the record gives; --check is clean on what it wrote, and fails on a re-recorded
    number and on an SVG edited by hand."""
    tool = _tool()
    scene_path, out = tmp_path / "snap.scene.json", tmp_path / "snap.svg"
    monkeypatch.setattr(tool, "FIGURES", {"snapfit": ("snapfit", SPEC, scene_path, out)})
    assert tool.main(["--extract", "snapfit"]) == 0 and out.exists()
    written = json.loads(scene_path.read_text(encoding="utf-8"))
    assert written["snaps"] == scene["snaps"] and written["shape"] == scene["shape"]
    assert tool.main(["--check"]) == 0, capsys.readouterr().out
    capsys.readouterr()
    stale = copy.deepcopy(written)
    stale["snaps"][1]["material"]["allowable"] = 0.017                  # PETG-CF's V2.0 allowable, re-recorded
    F.write_scene(stale, scene_path)
    assert tool.main(["--check"]) == 1
    assert "differs from its scene" in capsys.readouterr().out
    assert tool.main([]) == 0 and tool.main(["--check"]) == 0          # regenerated: clean again
    out.write_text(out.read_text(encoding="utf-8").replace("1.70 %", "1.00 %"), encoding="utf-8")
    assert tool.main(["--check"]) == 1                                  # an SVG edited by hand


def test_the_scene_is_written_deterministically(tmp_path, scene):
    p = tmp_path / "s.json"
    F.write_scene(copy.deepcopy(scene), p)
    assert p.read_text(encoding="utf-8") == SCENE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- what the figure says

def test_the_figure_states_the_calculators_numbers(scene, built):
    copa, petg_cf = scene["snaps"]
    for s in scene["snaps"]:
        a = F.pct(s["material"]["allowable"])
        assert f"{100 * F.ratio(s):.0f} % of {a}" in built
        assert f">{a} {'CoPA' if s is copa else 'PETG-CF'}<" in built                   # the allowable's line
    assert ">peak 1.38 %<" in built and F.pct(copa["strain"]) == "1.38 %"
    assert "68 % of 2.02 %" in built and "139 % of 1.00 %" in built
    assert built.count("✓ PASS") == 1 and built.count("✗ FAIL") == 1
    assert f">{copa['mating_force_n']:.1f} N<" in built and f"{copa['mating_force_n']:.1f}" == "10.1"
    assert f"PETG-CF: over its allowable {petg_cf['over_from_mm']:.2f} mm up the 2.25 mm lead" in built
    assert "CoPA: 10.1 N at the top of the lead; μ 0.525 on the land" in built
    assert "PETG-CF: no friction in the guide's table, so no push force" in built
    assert "a 15 mm arm, 1.6 × 6 mm, R1 root, laid flat on the bed; its hook rides a 30° lead over a 1.3 mm undercut" in built


def test_the_caption_says_what_the_figure_is(built):
    """The calculator on stated inputs, not a measurement; the data sheets named; a test print needed."""
    words = " ".join(re.findall(r">([^<>]+)</text>", built))
    assert "closed-form calculator (cadagent.mechanical.compliant.snapfit, Covestro method) on the stated arm" in words
    assert "not a measurement" in words and "Printed snaps need a test print" in words
    assert "Polymaker PolyMide CoPA V5.4 and Bambu Lab PETG-CF V3.0" in words
    desc = re.search(r"<desc>(.*?)</desc>", built, re.S).group(1)
    assert "Not a measurement" in desc and "test print" in desc and "cadagent.mechanical.compliant.snapfit" in desc


def test_the_figure_is_safe_themed_and_small(built):
    assert svg.problems(built) == []
    assert "prefers-color-scheme:dark" in built and svg.REDUCED_MOTION in built
    assert len(built.encode()) < 30_000


def _base_rule(built: str, selector: str) -> str:
    """The still: the selector's own rule (the one without an animation)."""
    css = re.search(r"<style>(.*?)</style>", built, re.S).group(1)
    rules = [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if sel == selector
             and "animation" not in body]
    assert rules, selector
    return ";".join(rules)


def test_the_still_is_the_top_of_the_lead(scene, spec, built):
    """Under reduced motion each element shows its own style: the arm bent by the whole undercut, the edge at the top
    of the drawn lead, the curves whole with their dots at the peak, the gauges full and both verdicts shown."""
    a, sh = scene["arm"], scene["shape"]
    y = scene["snaps"][0]["engagement"]["peak"]["deflection_mm"]
    U = svg.UNITS_PER_PX
    for i in range(scene["drawing"]["slices"]):
        lift = svg.num(-y * sh["deflection"][i] * F.K_MM * U, 1)
        turn = svg.num(-math.degrees(math.atan(y * sh["slope"][i] / a["length_mm"])), 3)
        assert f"translate(0,{lift}px) rotate({turn}deg)" in _base_rule(built, f".a{i}"), i
    edge = F.edge_x(a, sh, scene["drawing"]["clearance_mm"], y)
    assert f"translateX({svg.num((56 + F.K_MM * edge) * U, 0)}px)" in _base_rule(built, ".mp")
    assert "stroke-dashoffset:0" in _base_rule(built, ".cs")
    for sel in (".g0", ".g1", ".o1"):
        assert "scaleX(1)" in _base_rule(built, sel)
    # the verdicts, the crossing and the peak labels fade in during the loop: shown in the still (no opacity of
    # their own), hidden at the loop's start by their animation
    for cls in ("v0", "v1", "x1", "pk", "pk0"):
        assert re.search(rf'class="[^"]*\b{cls}\b[^"]*"', built), cls
        assert not re.search(rf'<[^>]*class="[^"]*\b{cls}\b[^"]*"[^>]*opacity=', built), cls


def test_the_loop_is_in_step_with_the_calculator(scene):
    """The moments the figure keys on come from the record: contact after the approach, the top of the lead after
    its travel, PETG-CF's crossing in between, at one speed."""
    t = F.times(scene)
    v = F.Phases.speed
    e = scene["snaps"][0]["engagement"]
    assert t["top"] - t["contact"] == pytest.approx(e["lead_travel_mm"] / v)
    assert t["land"] - t["top"] == pytest.approx(e["land_mm"] / v)
    assert t["contact"] < t["over_1"] < t["top"] and "over_0" not in t
    assert t["over_1"] - t["contact"] == pytest.approx(scene["snaps"][1]["over_from_mm"] / v)


def test_the_drawn_edge_stays_on_the_drawn_hook(scene):
    """The drawing turns the hook with the tip, which the closed form does not: the edge meets the lead where the
    calculator says at contact, stays on the drawn lead face up to its top, and reaches the top less than 0.35 mm of
    travel away from the calculator's (the figure's docstring says 0.3 mm)."""
    a, sh, c = scene["arm"], scene["shape"], scene["drawing"]["clearance_mm"]
    t = math.tan(math.radians(a["lead_deg"]))
    lead = scene["snaps"][0]["engagement"]["lead_travel_mm"]
    assert F.edge_x(a, sh, c, 0.0) == pytest.approx(a["length_mm"] + a["undercut_mm"] / t)
    y_top = a["undercut_mm"]
    drawn = F.edge_x(a, sh, c, 0.0) - F.edge_x(a, sh, c, y_top)
    assert 0 < lead - drawn < 0.35
    xs = [F.edge_x(a, sh, c, y_top * k / 8) for k in range(9)]
    assert all(b < x for x, b in zip(xs, xs[1:]))                       # the edge only moves in


# ---------------------------------------------------------------------------------------------- refusals

def test_the_figure_draws_one_arm(spec):
    two = copy.deepcopy(spec)
    two["snaps"][1]["length_mm"] = 16
    with pytest.raises(ValueError, match="length_mm"):
        F.arm(two)
    three = copy.deepcopy(spec)
    three["snaps"].append(copy.deepcopy(spec["snaps"][0]))
    with pytest.raises(ValueError, match="two snaps"):
        F.arm(three)
    ring = copy.deepcopy(spec)
    for s in ring["snaps"]:
        s["section"] = {"ring": {"r_inner_mm": 5, "r_outer_mm": 6, "arc_deg": 60}}
    with pytest.raises(ValueError, match="rectangular"):
        F.arm(ring)


def test_render_refuses_another_scene(scene, spec):
    with pytest.raises(ValueError, match="not a"):
        F.render({**scene, "schema": "other/1"}, spec["present"])
    odd = copy.deepcopy(scene)
    odd["snaps"][1]["engagement"]["points"][1]["strain"] *= 1.1
    with pytest.raises(ValueError, match="strain alike"):
        F.render(odd, spec["present"])


# ---------------------------------------------------------------------------------------------- the pages

PAGES = {ROOT / "docs" / "compliant.md": "img/compliant/snap-engagement.svg",
         ROOT / "src" / "cadagent" / "mechanical" / "compliant" / "README.md":
             "../../../../docs/img/compliant/snap-engagement.svg",
         ROOT / "docs" / "animated-figures.md": "img/compliant/snap-engagement.svg"}


@pytest.mark.parametrize("page", list(PAGES), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_the_pages_show_the_figure_and_say_what_it_is(page, scene):
    """Each page's alt text states the record's numbers, and its caption says what the figure is: the calculator's
    closed form on stated inputs, not a measurement, the data sheets it took the allowables from, and that a
    printed snap needs a test print. A re-record that changes the numbers fails here until the words change too."""
    text = page.read_text(encoding="utf-8")
    src = PAGES[page]
    at = text.index(f"]({src})")
    alt = text[text.rindex("![", 0, at):at]
    caption = " ".join(text[at:at + 900].split())
    copa, petg_cf = scene["snaps"]
    for claim in (F.pct(copa["strain"]), f"{100 * F.ratio(copa):.0f} %", F.pct(copa["material"]["allowable"]),
                  f"{100 * F.ratio(petg_cf):.0f} %", F.pct(petg_cf["material"]["allowable"])):
        assert claim in alt, (page.name, claim)
    assert "closed-form" in caption and "not a measurement" in caption, page.name
    assert "test print" in caption, page.name
    assert "PolyMide CoPA" in caption and "V5.4" in caption and "PETG-CF" in caption and "V3.0" in caption, page.name
