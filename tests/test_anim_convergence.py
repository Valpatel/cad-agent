"""The animated mesh-convergence figure (#167): a recorded run of cadagent.simulation.fea, drawn from its committed
scene. The figure states the scene's numbers and the mesher that made them; the record shows what the docs claim (a
sharp corner's peak keeps rising, a filleted one settles and converge() passes it); ``tools/readme_anim.py --check``
fails when the committed SVG is stale; and, where gmsh is the recorded build, the coarse steps reproduce."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest
import yaml

from cadagent.publish.anim import convergence as C
from cadagent.publish.anim import svg

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tools" / "anim" / "fea-convergence.yaml"
SCENE = ROOT / "tools" / "anim" / "fea-convergence.scene.json"
FIGURE = ROOT / "docs" / "img" / "fea" / "mesh-convergence.svg"


def _tool():
    spec = importlib.util.spec_from_file_location("readme_anim", ROOT / "tools" / "readme_anim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scene():
    return json.loads(SCENE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def present():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))["present"]


@pytest.fixture(scope="module")
def built(scene, present):
    return C.render(scene, present)


def _tiny_scene() -> dict:
    """A hand-made record: two corners, three steps each, a face of two triangles. Not a real study."""
    face = {"plane_y_mm": 0.0, "points": [[0, 0], [8, 0], [8, 8], [0, 8]], "edges": 5,
            "chains": [[0, 2]], "outline": [[0, 1, 2, 3, 0]]}
    corners = []
    for i, (name, peaks) in enumerate((("sharp corner", (400.0, 550.0, 750.0)), ("R1.5 fillet", (430.0, 433.0, 432.0)))):
        steps = []
        for k, (size, v) in enumerate(zip((2.0, 1.0, 0.5), peaks)):
            ok = bool(i and k)
            steps.append({"size_mm": size, "tets": 100 * (k + 1), "peak_mpa": v,
                          "peak": {"at_mm": [4.0, 0.0, 4.0], "where": "sharp inside corner" if not i else "inside fillet",
                                   "element_mm": size, "wall_mm": 2.0, "elements_across": round(2 / size, 1),
                                   "wall_resolved": 2 / size >= 3, "radius_mm": 1.5 if i else None,
                                   "radius_resolved": (size <= 1.5) if i else None},
                          "converge": {"factor": 0.75, "change": 0.1 if not ok else 0.01, "converged": ok},
                          "finer_peak": {"wall_resolved": k > 0, "radius_resolved": True if i else None},
                          "face": face})
        corners.append({"name": name, "fillet_mm": 1.5 * i, "steps": steps,
                        "uniform": [{"size_mm": 1.0, "tets": 900, "peak_mpa": peaks[1] * 0.98}]})
    return {"schema": C.SCHEMA, "name": "tiny", "recorded": "2026-01-01",
            "source": {"repo": "https://github.com/Valpatel/cad-agent", "name": "cad-agent", "licence": "MIT",
                       "commit": "0" * 40, "version": "0.0.0", "inputs": {}},
            "mesher": {"gmsh": "9.9.9", "occ": "8.8.8", "platform": {"system": "Linux", "machine": "x86_64"}},
            "study": {"window_mm": [0, 0, 8, 8]},
            "williams": {"lambda": C.williams_lambda(), "per_halving": 2 ** (1 - C.williams_lambda())},
            "corners": corners}


# ---------------------------------------------------------------------------------------------- the tool's --check

def test_check_round_trip_on_a_tiny_record(tmp_path, monkeypatch, capsys):
    """Write a tiny record's SVG, check it clean, then make the record or the SVG stale: --check fails each time."""
    tool = _tool()
    scene_path, out = tmp_path / "tiny.scene.json", tmp_path / "tiny.svg"
    C.write_scene(_tiny_scene(), scene_path)
    monkeypatch.setattr(tool, "FIGURES", {"tiny": ("convergence", SPEC, scene_path, out)})
    assert tool.main(["--check"]) == 1                                  # not written yet
    assert tool.main([]) == 0 and out.exists()
    assert tool.main(["--check"]) == 0, capsys.readouterr().out
    capsys.readouterr()
    stale = _tiny_scene()
    stale["corners"][0]["steps"][-1]["peak_mpa"] = 751.0                # a re-recorded number
    C.write_scene(stale, scene_path)
    assert tool.main(["--check"]) == 1
    assert "differs from its scene" in capsys.readouterr().out
    assert tool.main([]) == 0 and tool.main(["--check"]) == 0          # regenerated: clean again
    out.write_text(out.read_text(encoding="utf-8").replace("751", "750"), encoding="utf-8")
    assert tool.main(["--check"]) == 1                                  # an SVG edited by hand


def test_the_tiny_record_renders_its_own_numbers(present):
    text = C.render(_tiny_scene(), present)
    assert svg.problems(text) == []
    assert "751" not in text and "750 MPa" in text and "433 MPa" in text
    assert "gmsh 9.9.9" in text and "OpenCASCADE 8.8.8" in text
    with pytest.raises(ValueError):
        C.render({**_tiny_scene(), "schema": "other/1"}, present)
    bad = _tiny_scene()
    bad["corners"][1]["steps"].pop()
    with pytest.raises(ValueError, match="same steps"):
        C.render(bad, present)


def test_the_committed_figure_is_its_scene(built):
    assert FIGURE.read_text(encoding="utf-8") == built, "run PYTHONPATH=src python3 tools/readme_anim.py"


# ---------------------------------------------------------------------------------------------- what the figure says

def test_the_figure_states_every_step_from_the_record(scene, built):
    for c in scene["corners"]:
        for s in c["steps"]:
            cv = s["converge"]
            assert f"{s['peak_mpa']:,.0f} MPa" in built
            assert f">{s['tets']:,} tets<" in built
            assert C._finer(s) in built and f"{cv['factor']:g}× mesh: {cv['change']:+.1%}, " in built
            assert all(line in built for line in C._flags(s["peak"]))
    passed = sum(s["converge"]["converged"] for c in scene["corners"] for s in c["steps"])
    total = sum(len(c["steps"]) for c in scene["corners"])
    assert built.count("converge(): converged") == passed
    assert built.count("converge(): not converged") == total - passed
    m = scene["mesher"]
    assert f"gmsh {m['gmsh']}" in built and f"OpenCASCADE {m['occ']}" in built
    assert "Linear-elastic FEA" in built and "not proof that the part holds" in built
    a = C.summary(scene)[scene["corners"][0]["name"]]
    assert f"×{a['per_halving']:.2f} per halving" in built


def test_the_figure_is_safe_themed_and_still_under_reduced_motion(built):
    assert svg.problems(built) == []
    assert "prefers-color-scheme:dark" in built and svg.REDUCED_MOTION in built
    assert len(built.encode()) < 120_000
    # the still frame (each element's own style) is the last step: only its groups are drawn without opacity 0
    n = len(json.loads(SCENE.read_text(encoding="utf-8"))["corners"][0]["steps"])
    for k in range(n):
        tags = re.findall(rf'<g[^>]*class="s{k}[" ][^>]*>', built)
        assert tags and all(('opacity="0"' in t) == (k < n - 1) for t in tags), k


# ---------------------------------------------------------------------------------------------- what the record shows

def test_the_record_shows_a_sharp_corner_rising_and_a_fillet_settling(scene):
    sharp, fillet = scene["corners"]
    assert sharp["fillet_mm"] == 0 and fillet["fillet_mm"] > 0
    v = [s["peak_mpa"] for s in sharp["steps"]]
    assert all(b > a * 1.1 for a, b in zip(v, v[1:])), v               # rises at every halving
    rate = C.summary(scene)[sharp["name"]]["per_halving"]
    assert 1.2 < rate < 1.6, rate                                       # near Williams' 2^(1-λ) = 1.37
    assert not any(s["converge"]["converged"] for s in sharp["steps"])
    assert all("sharp inside corner" in s["peak"]["where"] for s in sharp["steps"])
    f = [s["peak_mpa"] for s in fillet["steps"]]
    assert max(f) / min(f) - 1 < 0.05, f
    # converge() passes the fillet when the peak moved within the tolerance and the finer mesh resolves it (its wall
    # and radius flags); the radius flag is the element size against the fillet's radius
    for s in fillet["steps"]:
        cv = s["converge"]
        for pk in (s["peak"], s["finer_peak"]):
            assert pk["radius_mm"] == fillet["fillet_mm"]
            assert pk["radius_resolved"] == (pk["element_mm"] <= pk["radius_mm"])
        resolved = s["finer_peak"]["wall_resolved"] and s["finer_peak"]["radius_resolved"]
        assert cv["converged"] == (abs(cv["change"]) <= cv["tolerance"] and resolved)
    assert fillet["steps"][-1]["converge"]["converged"]


def test_the_record_is_complete_and_consistent(scene):
    study = scene["study"]
    assert scene["schema"] == C.SCHEMA and re.fullmatch(r"\d{4}-\d\d-\d\d", scene["recorded"])
    m = scene["mesher"]
    assert m["gmsh"] and m["occ"] and m["library"]["sha256_16"] and m["platform"]["machine"]
    assert abs(scene["williams"]["lambda"] - C.williams_lambda()) < 1e-6
    for c in scene["corners"]:
        sizes = [s["size_mm"] for s in c["steps"]]
        assert sizes == [study["mesh_mm"]] + study["refine"]["sizes_mm"]
        assert [s["size_mm"] for s in c["uniform"]] == study["uniform_mm"]
        for k, s in enumerate(c["steps"]):
            cv = s["converge"]
            assert cv["von_mises_design_mpa"][0] == s["peak_mpa"] and cv["tets"][0] == s["tets"]
            assert cv["mesh_mm"] == [study["mesh_mm"], study["mesh_mm"] * study["converge"]["factor"]]
            if k:                                                      # refined round the corner, at this size
                (zone,) = s["refine"]
                assert zone["size_mm"] == s["size_mm"]
                assert zone["at_mm"] == pytest.approx(c["refine_at_mm"], abs=1e-4)
                assert math.dist(s["peak"]["at_mm"], zone["at_mm"]) <= zone["radius_mm"] + 0.5
            else:
                assert s["refine"] == []
            face = s["face"]
            n = len(face["points"])
            drawn = sum(len(ch) - 1 for ch in face["chains"] + face["outline"])
            assert drawn == face["edges"] and all(0 <= j < n for ch in face["chains"] + face["outline"] for j in ch)
        for u in c["uniform"]:                                         # refine= reaches that size for fewer tets
            same = next(s for s in c["steps"] if s["size_mm"] == u["size_mm"])
            assert same["tets"] < u["tets"] and u["refine"] == []
        # the drawing gets finer step by step
        assert [len(s["face"]["points"]) for s in c["steps"]] == sorted(len(s["face"]["points"]) for s in c["steps"])


def test_the_docs_show_the_figure_and_say_what_it_is(scene):
    """Each page's alt text states the record's numbers, and its caption says what the figure is: a recorded run, on
    which gmsh and OpenCASCADE, and that linear FEA does not prove strength. A re-record that changes them fails
    here until the words are changed too."""
    m = scene["mesher"]
    sharp, fillet = scene["corners"]
    v = [s["peak_mpa"] for s in fillet["steps"]]
    first_pass = next(s["size_mm"] for s in fillet["steps"] if s["converge"]["converged"])
    claims = [f"from {sharp['steps'][0]['peak_mpa']:,.0f} to {sharp['steps'][-1]['peak_mpa']:,.0f} MPa",
              f"between {min(v):,.0f} and {max(v):,.0f} MPa"]
    pages = {ROOT / "docs" / "toolkit.md": "img/fea/mesh-convergence.svg",
             ROOT / "src" / "cadagent" / "simulation" / "README.md": "../../../docs/img/fea/mesh-convergence.svg",
             ROOT / "docs" / "animated-figures.md": "img/fea/mesh-convergence.svg"}
    for page, src in pages.items():
        text = page.read_text(encoding="utf-8")
        at = text.index(f"]({src})")
        alt = text[text.rindex("![", 0, at):at]
        caption = text[at:at + 900]
        assert "recorded run" in caption, page
        assert f"gmsh {m['gmsh']}" in caption and f"OpenCASCADE {m['occ']}" in caption, page
        assert "does not prove" in caption, page
        if page.name != "animated-figures.md":
            assert all(c in alt for c in claims), (page, alt)
    toolkit = (ROOT / "docs" / "toolkit.md").read_text(encoding="utf-8")
    assert f"from the {first_pass:g} mm step" in toolkit
    whole = next(u for u in sharp["uniform"] if u["size_mm"] == 0.5)
    refined = next(s for s in sharp["steps"] if s["size_mm"] == 0.5)
    assert f"{whole['tets']:,} tets at\n0.5 mm for the sharp bracket, against {refined['tets']:,} refined" in toolkit


# ---------------------------------------------------------------------------------------------- the helpers

def test_williams_lambda_for_an_l_corner():
    lam = C.williams_lambda(270.0)
    assert abs(lam - 0.544484) < 1e-6                                  # Williams (1952), 270° of material
    assert abs(math.sin(1.5 * math.pi * lam) - lam) < 1e-12
    assert abs(2 ** (1 - lam) - 1.371) < 1e-3                          # the peak's growth per halving


def test_chains_draw_every_edge_once():
    edges = [(0, 1), (1, 2), (2, 0), (2, 3), (5, 6)]
    chains = C._chains(edges)
    seen = sorted(tuple(sorted(p)) for ch in chains for p in zip(ch, ch[1:]))
    assert seen == sorted(tuple(sorted(e)) for e in edges)
    assert chains[0] == [0, 1, 2, 0] and len(chains) == 3             # a closed loop comes back to its start


def test_a_summary_is_computed_from_the_scene_alone():
    s = C.summary(_tiny_scene())
    assert s["sharp corner"]["per_halving"] == pytest.approx((750 / 400) ** 0.5)
    assert s["R1.5 fillet"]["spread"] == pytest.approx(433 / 430 - 1)
    assert s["R1.5 fillet"]["converged"] == [False, True, True]


# ---------------------------------------------------------------------------------------------- the code reproduces it

def test_the_coarse_steps_reproduce_on_the_recorded_mesher(scene):
    """The 2 mm steps run again with today's code: on the gmsh build that made the record, the same tets and peak.
    On another build the mesh may differ, which the record's mesher says; then this skips."""
    pytest.importorskip("cadquery")
    pytest.importorskip("gmsh")
    pytest.importorskip("skfem")
    from cadagent.simulation.fea import Material, _mesher_identity  # noqa: F401  (gmsh session per Study)

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    m = spec["material"]
    mat = Material(m["name"], m["E_mpa"], m["nu"], m["strength_mpa"], m["density_g_cm3"])
    for c in scene["corners"]:
        rec = c["steps"][0]
        got = C._step(C.bracket(spec["part"], c["fillet_mm"]), mat, spec, spec["mesh_mm"], None,
                      window=spec["window_mm"])
        if got["mesher"] != scene["mesher"]:
            pytest.skip(f"gmsh here is not the recorded build ({got['mesher']['gmsh']}, "
                        f"{got['mesher']['library']['sha256_16']})")
        assert got["tets"] == rec["tets"], c["name"]
        assert got["peak_mpa"] == pytest.approx(rec["peak_mpa"], rel=1e-3), c["name"]
        assert got["converge"]["converged"] == rec["converge"]["converged"]
        assert got["face"]["points"] == rec["face"]["points"]


def test_the_scene_is_written_deterministically(tmp_path, scene):
    p = tmp_path / "s.json"
    C.write_scene(copy.deepcopy(scene), p)
    assert p.read_text(encoding="utf-8") == SCENE.read_text(encoding="utf-8")
