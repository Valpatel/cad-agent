"""The animated README figures (#181): each committed SVG is exactly what its committed scene renders to, and is safe
to embed as a GitHub ``<img>`` (no script or external reference, valid XML, labelled, a reduced-motion still, at most
250 KB). Each rule is shown to fail on an SVG that breaks it, so a rule that stops checking is caught too. Then the
helpers the figures are built from: paths, timeline, rasteriser and linkage."""
from __future__ import annotations

import importlib.util
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from cadagent.publish.anim import raster, svg
from cadagent.mechanical.linkages import Linkage, circles, ellipse_path

ROOT = Path(__file__).resolve().parents[2]


def _tool():
    spec = importlib.util.spec_from_file_location("readme_anim", ROOT / "tools" / "readme_anim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    return _tool()


@pytest.fixture(scope="module")
def built(tool):
    return {name: tool.build(name) for name in tool.FIGURES}


# ---------------------------------------------------------------------------------------------- the committed figures

def test_every_committed_figure_is_what_its_scene_renders_to(tool, capsys):
    assert tool.main(["--check"]) == 0, capsys.readouterr().out


def test_rendering_is_deterministic(tool, built):
    for name in tool.FIGURES:
        assert tool.build(name) == built[name]


def test_every_figure_passes_the_embed_rules(tool, built):
    for name, text in built.items():
        assert svg.problems(text) == [], name
        size = len(text.encode())
        assert size <= svg.BUDGET_BYTES, f"{name}: {size} bytes"
        root = ET.fromstring(text)                                  # well-formed, and the root is a labelled image
        assert root.get("role") == "img" and root.get("aria-label")
        assert "<script" not in text.lower() and not re.search(r"""(?:href|src)\s*=\s*["'](?!#)""", text)
        assert svg.REDUCED_MOTION in text and "prefers-color-scheme:dark" in text


def test_the_check_fails_when_a_committed_figure_differs(tool, built, tmp_path, monkeypatch, capsys):
    name = next(iter(tool.FIGURES))
    kind, spec, scene, _ = tool.FIGURES[name]
    out = tmp_path / "fig.svg"
    monkeypatch.setitem(tool.FIGURES, name, (kind, spec, scene, out))
    assert tool.main(["--check"]) == 1                              # missing
    out.write_text(built[name].replace("cad-agent", "cad agent", 1), encoding="utf-8")
    assert tool.main(["--check"]) == 1                              # one character changed
    out.write_text(built[name], encoding="utf-8")
    assert tool.main(["--check"]) == 0
    assert "differs" in capsys.readouterr().out


def test_the_check_fails_when_a_figure_breaks_a_rule(tool, built, tmp_path, monkeypatch, capsys):
    """A scene that renders over budget fails --check even when the committed SVG matches it."""
    name = next(iter(tool.FIGURES))
    kind, spec, scene, _ = tool.FIGURES[name]
    out = tmp_path / "fig.svg"
    monkeypatch.setitem(tool.FIGURES, name, (kind, spec, scene, out))
    monkeypatch.setattr(svg, "BUDGET_BYTES", 1000)
    out.write_text(built[name], encoding="utf-8")
    assert tool.main(["--check"]) == 1
    assert "byte budget" in capsys.readouterr().out


def test_scenes_record_where_every_number_came_from(tool):
    for name, (_, spec_path, scene_path, _) in tool.FIGURES.items():
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        src = scene["source"]
        assert re.fullmatch(r"[0-9a-f]{40}", src["commit"]), name
        assert src["inputs"] and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in src["inputs"].values())
        assert all(not Path(p).is_absolute() and ".." not in Path(p).parts for p in src["inputs"])
        assert src["repo"].startswith("https://github.com/") and src["licence"]


def test_no_local_path_leaks_into_a_scene_or_figure(tool, built):
    for name, (_, _, scene_path, _) in tool.FIGURES.items():
        for text in (scene_path.read_text(encoding="utf-8"), built[name]):
            assert not re.search(r"/home/|/Users/|/tmp/|[A-Z]:\\\\", text), name


def test_the_hero_states_its_checks_from_the_scene(tool, built):
    scene = json.loads(tool.FIGURES["hero"][2].read_text(encoding="utf-8"))
    lk = scene["linkage"]
    for pair, got in lk["lengths_mm"].items():                       # the CAD's link lengths, checked at extraction
        assert got > 0
    assert lk["motion_error_px"] < 2, "the drawn motion strays too far from the exact 3D motion"
    assert max(lk["motion_error_px_by_part"].values()) == lk["motion_error_px"]
    text = built["hero"]
    assert f"first failure predicted at {scene['fea']['first_failure_factor']:.2f}× load" in text
    assert lk["edge_error_px"] < 2, "drawn edges stray too far from the exact 3D motion"
    if scene.get("clearance"):
        c = scene["clearance"]
        assert f"{c['poses']} poses" in text
        # the stated gaps are the smallest of their kind in the per-solid table, rounded down
        for kind, key, words in (("running", "closest_running", "joints ≥ {} mm"),
                                 ("passing", "closest", "passing ≥ {} mm")):
            gaps = [p["min_gap_mm"] for p in c["pairs"] if p["kind"] == kind]
            assert (c[key] or {}).get("gap_mm") == (min(gaps) if gaps else None)
            if gaps:
                assert words.format(f"{math.floor(min(gaps) * 10 + 1e-9) / 10:.1f}") in text
        assert bool(c["clashes"]) == any(p["kind"] == "clash" for p in c["pairs"])


def test_the_readme_embeds_the_hero():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r'<img src="docs/img/hero/gyropup-leg\.svg" alt="([^"]+)"', readme)
    assert m and "Gyropup" in m.group(1)
    assert "github.com/Valpatel/gyropup" in readme


# ------------------------------------------------------------------------------------- each rule bites (mutations)

def _insert(text, fragment):
    return text.replace("</svg>", fragment + "</svg>")


MUTATIONS = [
    ("over budget", lambda t: _insert(t, "<!--" + "x" * svg.BUDGET_BYTES + "-->"), "byte budget"),
    ("not XML", lambda t: t.replace("</svg>", ""), "not well-formed"),
    ("script", lambda t: _insert(t, "<script>alert(1)</script>"), "<script>"),
    ("foreignObject", lambda t: _insert(t, "<foreignObject/>"), "<foreignObject>"),
    ("raster image", lambda t: _insert(t, '<image href="#x"/>'), "<image>"),
    ("use", lambda t: _insert(t, '<use href="#x"/>'), "<use>"),
    ("link", lambda t: _insert(t, '<a href="#x"/>'), "<a>"),
    ("event handler", lambda t: t.replace("<svg ", '<svg onload="x()" ', 1), "event handler"),
    ("external href", lambda t: _insert(t, '<linearGradient id="z" href="https://example.com/g.svg#a"/>'),
     "an href or src"),
    ("external xlink:href", lambda t: _insert(t, '<pattern xmlns:xlink="http://www.w3.org/1999/xlink" '
                                                 'xlink:href="https://example.com/p.svg#a"/>'), "an href or src"),
    ("external url()", lambda t: _insert(t, '<path d="M0 0" fill="url(https://example.com/p.svg#a)"/>'), "url()"),
    ("@import", lambda t: t.replace("<style>", "<style>@import 'x.css';", 1), "@import"),
    ("no label", lambda t: t.replace('role="img" ', "", 1), "aria-label"),
    ("no title", lambda t: re.sub(r"<title>[^<]*</title>", "<title> </title>", t, count=1), "<title>"),
    ("no reduced motion", lambda t: t.replace(svg.REDUCED_MOTION, ""), "prefers-reduced-motion"),
    ("no animation", lambda t: t.replace("@keyframes", "@media print"), "no CSS animation"),
    ("SMIL", lambda t: _insert(t, '<animate attributeName="opacity" dur="1s"/>'), "SMIL"),
    ("prefixed SMIL", lambda t: _insert(t, '<s:animate xmlns:s="http://www.w3.org/2000/svg" attributeName="x"/>'),
     "SMIL"),
    ("XHTML script", lambda t: _insert(t, '<h:script xmlns:h="http://www.w3.org/1999/xhtml">x()</h:script>'),
     "<script>"),
    ("reduced motion outside the style", lambda t: t.replace(svg.REDUCED_MOTION, "").replace(
        "</desc>", svg.REDUCED_MOTION + "</desc>"), "prefers-reduced-motion"),
    ("CSS escape", lambda t: t.replace("<style>", "<style>.z{fill:u\\72l(https://example.com/p.svg)}", 1),
     "backslash"),
]


@pytest.mark.parametrize("what, mutate, expect", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_rule_fails_an_svg_that_breaks_it(built, what, mutate, expect):
    good = built["hero"]
    assert svg.problems(good) == []
    bad = mutate(good)
    assert bad != good, f"the {what} mutation did not change the SVG"
    found = svg.problems(bad)
    assert any(expect in p for p in found), f"{what}: {found}"


# ---------------------------------------------------------------------------------------------------- the helpers

def test_path_numbers_are_separated_where_the_grammar_needs_it():
    from cadagent.publish.anim.svg import _join

    assert _join(["1.5", "-2", ".5"]) == "1.5-2 .5"        # ".5" after "-2" would read as -2.5
    assert _join(["1.5", ".5", "-2", "3"]) == "1.5.5-2 3"


def test_numbers_are_compact():
    assert [svg.num(v, 2) for v in (0.5, -0.5, 1.0, -0.001, 12.345)] == [".5", "-.5", "1", "0", "12.35"]


def test_paths_are_relative_integers_and_continue_shared_ends():
    d = svg.segments_d([["L", 10, 10, 20, 10], ["L", 20, 10, 20, 30], ["A", 20, 30, 40, 30, 10, 10, 0, 0, 1]])
    assert d == "M10 10l10 0 0 20a10 10 0 0 1 20 0"
    assert svg.polygon_d([[(0, 0), (4, 0), (4, 4)], [(10, 10), (12, 10), (12, 12)]]) == "M0 0l4 0 0 4zm10 10l2 0 0 2z"


def test_arc_points_follow_the_svg_arc():
    up = svg.arc_points((0, 0), (2, 0), 1, 1, 0, False, True, 2)        # sweep 1 turns clockwise on screen (y down)
    down = svg.arc_points((0, 0), (2, 0), 1, 1, 0, False, False, 2)
    assert [c for p in up for c in p] == pytest.approx([0, 0, 1, -1, 2, 0])
    assert [c for p in down for c in p] == pytest.approx([0, 0, 1, 1, 2, 0])
    big = svg.arc_points((0, 0), (2, 0), 2, 2, 0, True, True, 8)        # the large arc of a radius-2 circle,
    assert [math.dist(p, (1, -math.sqrt(3))) for p in big] == pytest.approx([2] * 9)   # centred above the chord
    assert big[4] == pytest.approx((1, -math.sqrt(3) - 2))


def test_two_animations_on_one_element_are_one_rule():
    """CSS keeps only the last ``animation`` declaration an element matches, so two animations on one selector
    must be listed in one rule, not two."""
    tl = svg.Timeline(10)
    tl.opacity(".a", [(0, 0), (5, 1)])
    tl.add(".a", [(0, 0), (10, 5)], lambda v: f"transform:translateX({v}px)", "linear")
    tl.opacity(".b", [(0, 0), (5, 1)])
    css = tl.stylesheet()
    rules = re.findall(r"([^{}]+)\{animation:([^}]*)\}", css)
    a_rules = [r for r in rules if ".a" in r[0].split(",")]
    assert len(a_rules) == 1 and a_rules[0][1].count("infinite") == 2


def test_keyframe_times_must_run_forward_inside_the_loop():
    tl = svg.Timeline(10)
    with pytest.raises(ValueError):
        tl.opacity(".a", [(0, 0), (5, 1), (4, 0)])
    with pytest.raises(ValueError):
        tl.opacity(".a", [(0, 0), (11, 1)])


def test_the_theme_needs_the_same_colours_in_both_schemes():
    with pytest.raises(ValueError):
        svg.Theme({"a": "#000"}, {"b": "#fff"}).css()


def test_the_zbuffer_keeps_the_nearest_triangle():
    square = lambda x0, y0, s: np.array([[(x0, y0), (x0 + s, y0), (x0 + s, y0 + s)], [(x0, y0), (x0 + s, y0 + s),
                                                                                       (x0, y0 + s)]], float)
    tris = np.concatenate([square(0, 0, 8), square(4, 4, 8)])
    depth = np.array([[1.0] * 3] * 2 + [[2.0] * 3] * 2)
    zb, vb = raster.zbuffer(tris, depth, (0, 0, 1), (16, 16), values=np.array([10.0, 10, 20, 20]))
    assert zb[2, 2] == 1 and vb[2, 2] == 10                        # only the far square
    assert zb[6, 6] == 2 and vb[6, 6] == 20                        # both: the near one wins
    assert zb[14, 2] == -np.inf and np.isnan(vb[14, 2])


def test_outlines_follow_the_cells_and_holes_are_separate_loops():
    m = np.zeros((7, 7), bool)
    m[1:6, 1:6] = True
    m[3, 3] = False
    loops = raster.outlines(m)
    assert len(loops) == 2
    areas = sorted(abs(raster.loop_area(l)) for l in loops)
    assert areas == pytest.approx([0.5, 24.5])                    # 5 x 5 less the cut corners; the hole a diamond
    xs = [p[0] for p in max(loops, key=len)]
    assert min(xs) == pytest.approx(1) and max(xs) == pytest.approx(6)


def test_dilate_grows_by_one_cell_and_nearest_finds_the_closest_label():
    m = np.zeros((5, 5), bool)
    m[2, 2] = True
    assert raster.dilate(m).sum() == 5 and raster.dilate(m)[1, 2] and not raster.dilate(m)[1, 1]
    labels = np.full((8, 8), -1)
    labels[1, 1], labels[1, 6] = 3, 7
    assert raster.nearest(labels, 2.0, 2.0, -1) == 3              # point (x 2, y 2): cell (1, 1) is nearest
    assert raster.nearest(labels, 6.2, 1.5, -1) == 7
    assert raster.nearest(labels, 4.0, 7.5, -1, radius=2) == -1   # nothing within reach


def test_simplify_keeps_corners_and_drops_collinear_points():
    sq = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1)]
    assert sorted(raster.simplify(sq, 0.1, closed=True)) == [(0, 0), (0, 2), (2, 0), (2, 2)]


def test_circle_intersections():
    got = sorted(circles((0, 0), 5, (8, 0), 5))
    assert [c for p in got for c in p] == pytest.approx([4, -3, 4, 3])
    assert circles((0, 0), 1, (5, 0), 1) == []


def _five_bar():
    """Two 150 mm cranks 150 mm apart and two 250 mm links meeting at E, as in a five-bar leg."""
    ref = {"A": (-75.0, 0.0), "B": (75.0, 0.0)}
    ref["C"] = (-75 - 150 * math.cos(math.radians(60)), -150 * math.sin(math.radians(60)))
    ref["D"] = (75 + 150 * math.cos(math.radians(60)), -150 * math.sin(math.radians(60)))
    h = math.sqrt(250 ** 2 - (ref["D"][0] - ref["C"][0]) ** 2 / 4)
    ref["E"] = (0.0, ref["C"][1] - h)
    link = Linkage(ground={"A": ref["A"], "B": ref["B"]},
                   links={"crank_a": ("A", "C"), "crank_b": ("B", "D"), "link_c": ("C", "E"), "link_d": ("D", "E")},
                   reference=ref, solve=[("C", "A", "E"), ("D", "B", "E")])
    return link, ref


def test_a_five_bar_keeps_its_lengths_and_its_branch_along_a_path():
    link, ref = _five_bar()
    path = ellipse_path((ref["E"][0], ref["E"][1] + 30), (60, 30), -90, 36)
    assert math.dist(path[0], ref["E"]) < 1e-9 and math.dist(path[0], path[-1]) < 1e-9
    poses = link.sweep("E", path)
    for p in poses:
        for body, (a, b) in link.links.items():
            assert math.dist(p[a], p[b]) == pytest.approx(math.dist(ref[a], ref[b]))
        assert p["C"][0] < p["A"][0] and p["D"][0] > p["B"][0]     # knees stay out: no jump to the other branch
    assert poses[-1]["C"] == pytest.approx(poses[0]["C"])
    turn, r0, p0 = link.body_motion("crank_a", poses[0])
    assert turn == pytest.approx(0) and p0 == pytest.approx(r0)


def test_a_path_out_of_reach_is_an_error():
    link, ref = _five_bar()
    with pytest.raises(ValueError, match="reach"):
        link.sweep("E", [ref["E"], (ref["E"][0], ref["E"][1] - 400)])


def test_the_sweep_summary_tells_contacts_running_gaps_and_passing_parts_apart():
    from cadagent.publish.anim.hero import summarise_sweep

    part_of = {1: "link", 2: "frame", 3: "pin", 4: "bearing", 5: "spacer", 6: "screw", 7: "link"}
    results = [
        (0, [(1, 2, "apart", 4.0, 0, [0, 0, 0], [4, 0, 0]),       # a link passing the frame: its gap changes
             (3, 4, "touching", 0.0, 0, [0, 0, 0], [0, 0, 0]),    # a pin in its bearing: touching at every pose
             (5, 4, "apart", 0.1, 0, [0, 0, 0], [0, 0, .1]),      # a spacer beside it: 0.1 mm at every pose
             (7, 2, "apart", 1.0, 0, [0, 0, 0], [0, 0, 1])]),     # the link's other solid turns 1 mm from the frame
        (2, [(1, 2, "apart", 1.5, 0, [1, 0, 0], [2.5, 0, 0]),
             (3, 4, "touching", 0.0, 0, [0, 0, 0], [0, 0, 0]),
             (5, 4, "apart", 0.1, 0, [0, 0, 0], [0, 0, .1]),
             (2, 7, "apart", 1.0, 0, [0, 0, 1], [0, 0, 0]),
             (6, 2, "overlapping", 0.0, 3.2, None, None)]),
    ]
    s = summarise_sweep(results, part_of, [0, 2])
    assert s["clashes"] == [{"pose": 2, "a": "frame", "b": "screw", "overlap_mm3": 3.2}]
    # per solid: the link's passing solid is not hidden by its other solid's constant 1 mm
    assert s["closest"]["part_a"] == "link" and s["closest"]["gap_mm"] == 1.5 and s["closest"]["pose"] == 2
    assert {s["closest_running"]["part_a"], s["closest_running"]["part_b"]} == {"spacer", "bearing"}
    assert s["closest_running"]["gap_mm"] == 0.1
    assert s["contacts"] == [["bearing", "pin"]]
    assert s["kinds"] == {"clash": 1, "contact": 1, "running": 2, "passing": 1}
    # a pair measured at only some poses (out of reach at the others) passes; it is never running or a contact
    s = summarise_sweep(results[:1], part_of, [0, 2])
    assert s["contacts"] == [] and s["closest_running"] is None and s["closest"]["gap_mm"] == 0.0


def test_the_fit_row_states_running_and_passing_gaps_and_never_overstates():
    from cadagent.publish.anim.hero import _check_rows

    def fit(**c):
        scene = {"clearance": {"poses": 12, "clashes": [], "near_mm": 10.0, **c},
                 "linkage": {"samples": 24, "dead_point_margin_deg": []}}
        return _check_rows(scene)[0]

    run, pas = {"gap_mm": 0.098}, {"gap_mm": 7.308}
    assert fit(closest_running=run, closest=pas)[1] == "no clash in 12 poses · joints ≥ 0.0 mm, passing ≥ 7.3 mm"
    assert fit(closest_running=None, closest=pas)[1] == "no clash in 12 poses · passing parts ≥ 7.3 mm apart"
    assert fit(closest_running=None, closest=None)[1] == "no clash in 12 poses · nothing passes within 10.0 mm"
    assert fit(clashes=[{"pose": 1}], closest=pas)[3] is False


def test_painting_breaks_a_cycle_where_it_costs_fewest_cells():
    from cadagent.publish.anim.hero import painter_order

    # wheel in front of link over 9000 cells; link in front of pin over 50; pin in front of wheel over 40: a cycle.
    # The cheapest break draws the pin wrong against the wheel (40 cells), never the link over the wheel.
    front = {("wheel", "link"): 9000, ("link", "pin"): 50, ("pin", "wheel"): 40, ("link", "wheel"): 3}
    order, wrong = painter_order(["wheel", "link", "pin"], front, {"wheel": 0, "link": 0, "pin": 0})
    assert order.index("link") < order.index("wheel") and wrong == 43
    order, wrong = painter_order(["a", "b"], {}, {"a": 1.0, "b": 0.0})    # no overlap: farther first
    assert order == ["b", "a"] and wrong == 0


def test_the_hero_paints_almost_every_overlapping_cell_in_order(tool):
    scene = json.loads(tool.FIGURES["hero"][2].read_text(encoding="utf-8"))
    p = scene["painter"]
    # beyond what interlocking parts force, at most 1 % of the overlapping cells are painted in the wrong order
    assert p["overlap_cells"] > 0 and p["misordered_cells"] - p["unavoidable_cells"] <= 0.01 * p["overlap_cells"], p
