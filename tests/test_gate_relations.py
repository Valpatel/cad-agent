"""Gate machinery: Assembly, broad phase, pairwise relations, the pair cache and the verdict file."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cadagent.gates import Check, PairCache, Tolerances, aabb_distances, verdict, write_verdict
from cadagent.gates import relations as relations_mod  # the module

try:
    import cadquery as cq
except ImportError:  # core CI: the verdict and broad-phase tests still run
    cq = None
needs_cad = pytest.mark.skipif(cq is None, reason="needs cadquery (the cad extra)")

ROOT = Path(__file__).resolve().parents[1]


def box(x, y, z, at=(0, 0, 0)):
    return cq.Solid.makeBox(x, y, z, cq.Vector(*at))


def ball(r, centre=None):
    """A full sphere (cq.Solid.makeSphere defaults to a hemisphere)."""
    return cq.Solid.makeSphere(r, centre or cq.Vector(0, 0, 0), angleDegrees1=-90)


def timing_module():
    spec = importlib.util.spec_from_file_location("gate_timing", ROOT / "tools" / "gate_timing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------- the four textbook pairs

@needs_cad
def test_four_textbook_pairs_give_build123d_mcp_states():
    from cadagent.gates import relate
    apart = relate(box(10, 10, 10), box(10, 10, 10, (12, 0, 0)))
    assert apart.state == "apart" and apart.gap_mm == pytest.approx(2.0)
    assert apart.witness["point_a"][0] == pytest.approx(10) and apart.witness["point_b"][0] == pytest.approx(12)

    touching = relate(box(10, 10, 10), box(10, 10, 10, (10, 5, 0)))
    assert touching.state == "touching" and touching.gap_mm == 0
    assert touching.contact_area_mm2 == pytest.approx(50.0)          # the shared 5 x 10 face patch

    over = relate(box(10, 10, 10), box(10, 10, 10, (5, 0, 0)))
    assert over.state == "overlapping" and over.overlap_mm3 == pytest.approx(500.0)
    assert over.a_outside_b_mm3 == pytest.approx(500.0) and over.witness["overlap_centroid"] == pytest.approx([7.5, 5, 5])

    sphere = ball(3, cq.Vector(5, 5, 5))
    inside = relate(sphere, box(10, 10, 10))
    assert inside.state == "contains" and inside.contained == "a_in_b"
    assert inside.a_outside_b_mm3 == pytest.approx(0.0) and inside.wall_mm == pytest.approx(2.0)
    flipped = inside.flipped()
    assert flipped.contained == "b_in_a" and flipped.b_outside_a_mm3 == pytest.approx(0.0)


@needs_cad
def test_ball_resting_on_a_cavity_wall_is_contained_and_one_poking_through_is_not():
    from cadagent.gates import relate
    cavity = box(20, 20, 20, (-10, -10, -5))
    resting = relate(ball(5), cavity)                 # tangent to the cavity floor, from inside
    assert resting.state == "contains" and resting.wall_mm == pytest.approx(0.0, abs=1e-6)
    poking = relate(ball(5, cq.Vector(0, 0, -0.3)), cavity)
    assert poking.state == "overlapping"
    cap = 3.141592653589793 * 0.3 ** 2 * (15 - 0.3) / 3                 # spherical cap below the floor
    assert poking.a_outside_b_mm3 == pytest.approx(cap, rel=1e-6)


@needs_cad
def test_touch_tolerance_and_contact_area_of_a_pin_in_its_bore():
    from cadagent.gates import relate
    near = relate(box(10, 10, 10), box(10, 10, 10, (10.005, 0, 0)))
    assert near.state == "touching" and near.gap_mm == pytest.approx(0.005) and near.contact_area_mm2 == 0.0
    assert relate(box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0))).state == "apart"
    loose = relate(box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0)), Tolerances(touch_mm=0.05))
    assert loose.state == "touching"

    block = box(10, 10, 10, (-5, -5, 0)).cut(cq.Solid.makeCylinder(2, 10))
    pin = relate(cq.Solid.makeCylinder(2, 10), block)
    assert pin.state == "touching"
    assert pin.contact_area_mm2 == pytest.approx(2 * 3.141592653589793 * 2 * 10, rel=1e-6)


@needs_cad
def test_kernel_failure_is_unknown_not_apart(monkeypatch):
    def boom(a, b):
        raise RuntimeError("BRepAlgoAPI_Common failed")
    monkeypatch.setattr(relations_mod, "_common", boom)
    rel = relations_mod.relate(box(1, 1, 1), box(1, 1, 1, (0.5, 0, 0)))
    assert rel.state == "unknown" and "Common failed" in rel.error


# ----------------------------------------------------------------------------- Assembly

@needs_cad
def test_assembly_locations_bodies_groups_and_validation():
    from cadagent.gates import Assembly, bounding_box
    asm = Assembly()
    asm.add("t", box(1, 1, 1), (10, 0, 0))
    asm.add("loc", box(1, 1, 1), cq.Location(cq.Vector(10, 0, 0)))
    asm.add("m44", box(1, 1, 1), [[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], body="arm", group="S1")
    asm.add("rot", box(2, 1, 1), cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90), body="arm", group="S1")
    for n in ("t", "loc", "m44"):
        assert bounding_box(asm.shape(n)) == pytest.approx((10, 0, 0, 11, 1, 1), abs=1e-9)
    assert bounding_box(asm.shape("rot")) == pytest.approx((-1, 0, 0, 0, 2, 1), abs=1e-9)
    assert asm["t"].key == asm["loc"].key == asm["m44"].key          # same content, same placement
    assert asm.bodies() == {"t": ["t"], "loc": ["loc"], "arm": ["m44", "rot"]}
    assert asm.groups()["S1"] == ["m44", "rot"]
    with pytest.raises(ValueError, match="already"):
        asm.add("t", box(1, 1, 1))
    with pytest.raises(ValueError, match="no solid"):
        asm.add("face", cq.Face.makePlane(1, 1))
    with pytest.raises(ValueError, match="0 0 0 1"):
        asm.add("bad", box(1, 1, 1), [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1]])

    posed = asm.posed("arm", (0, 0, 5))
    assert bounding_box(posed.shape("m44")) == pytest.approx((10, 0, 5, 11, 1, 6), abs=1e-9)
    assert posed["t"].key == asm["t"].key and posed["m44"].key != asm["m44"].key
    assert bounding_box(asm.shape("m44"))[2] == pytest.approx(0)      # the original is untouched
    with pytest.raises(KeyError):
        asm.posed("nobody", (0, 0, 1))


@needs_cad
def test_assembly_from_cadquery_composes_locations_and_labels_bodies():
    from cadagent.gates import Assembly, bounding_box
    root = cq.Assembly(name="root")
    root.add(box(5, 5, 5), name="frame", loc=cq.Location(cq.Vector(1, 2, 3)))
    arm = cq.Assembly(name="arm")
    arm.add(box(1, 1, 1), name="link", loc=cq.Location(cq.Vector(0, 0, 2)))
    root.add(arm, loc=cq.Location(cq.Vector(10, 0, 0)))
    asm = Assembly.from_cadquery(root)
    assert asm.names == ["root/frame", "root/arm/link"]
    assert bounding_box(asm.shape("root/arm/link")) == pytest.approx((10, 0, 2, 11, 1, 3), abs=1e-9)
    assert asm.bodies() == {"root/frame": ["root/frame"], "root/arm": ["root/arm/link"]}


# ----------------------------------------------------------------------------- broad phase and table

def test_aabb_distances_are_box_gaps():
    d = aabb_distances({"a": (0, 0, 0, 1, 1, 1), "b": (4, 0, 0, 5, 1, 1), "c": (4, 5, 0, 5, 6, 1),
                        "d": (0.5, 0.5, 0.5, 2, 2, 2)})
    assert d[("a", "b")] == pytest.approx(3.0)
    assert d[("a", "c")] == pytest.approx((3 ** 2 + 4 ** 2) ** 0.5)
    assert d[("a", "d")] == 0.0 and len(d) == 6


@needs_cad
def test_table_get_bounds_skipped_pairs_and_computes_them_on_request():
    from cadagent.gates import Assembly, relation_table
    asm = Assembly({"a": box(10, 10, 10), "b": box(10, 10, 10, (10, 0, 0)), "far": box(1, 1, 1, (50, 0, 0)),
                    "alt": box(10, 10, 10, (5, 0, 0))})
    table = relation_table(asm, skip_pairs=[("a", "alt")])
    assert table.get("b", "a").state == "touching" and table.get("b", "a").a == "b"
    far = table.get("far", "b")
    assert far.state == "apart" and not far.exact and far.gap_lower_bound_mm == pytest.approx(30.0)
    exact = table.get("far", "b", exact=True)
    assert exact.exact and exact.gap_mm == pytest.approx(30.0)
    assert ("a", "alt") in table.skipped and table.stats["candidates"] == 2
    assert {r.state for r in table.contacts()} == {"touching", "overlapping"}
    assert [r.b for r in table.of("alt")] == ["b"]
    data = json.loads(json.dumps(table.to_dict()))
    assert data["physical_fit_verified"] is False and len(data["relations"]) == 3
    only = relation_table(asm, only=["far"])
    assert only.stats["candidates"] == 0
    with pytest.raises(ValueError):
        table.by_state("hovering")


@needs_cad
def test_synthetic_100_parts_under_5_seconds():
    """The plan's acceptance figure; tools/gate_timing.py prints the same run."""
    from cadagent.gates import relation_table
    asm, expected = timing_module().synthetic_assembly(100)
    t0 = time.perf_counter()
    table = relation_table(asm)
    elapsed = time.perf_counter() - t0
    assert table.stats["pairs"] == 4950 and table.stats["candidates"] == 90
    assert {k: table.get(*k).state for k in expected} == expected
    assert table.stats["states"]["unknown"] == 0
    assert elapsed < 5.0, table.stats


# ----------------------------------------------------------------------------- cache

@needs_cad
def test_shape_hash_is_content_based_and_ignores_triangulation():
    from cadagent.gates import shape_hash
    a, b = box(1, 2, 3), box(1, 2, 3)
    assert shape_hash(a) == shape_hash(b)
    before = shape_hash(a)
    a.tessellate(0.1)
    assert shape_hash(a) == before
    assert shape_hash(box(1, 2, 3.001)) != before


@needs_cad
def test_cache_hit_skips_the_kernel_and_a_moved_part_requeries_only_its_pairs(tmp_path, monkeypatch):
    from cadagent.gates import Assembly, relation_table
    shapes = {"base": box(30, 30, 2), "a": box(5, 5, 5, (0, 0, 2)), "b": box(5, 5, 5, (5, 0, 2)),
              "c": box(5, 5, 5, (20, 20, 2))}
    from cadagent.gates import shape_hash
    before = {n: shape_hash(v) for n, v in shapes.items()}
    cache = PairCache(tmp_path / "cache")
    cold = relation_table(Assembly(shapes), cache=cache)
    assert cold.stats["kernel_queries"] == cold.stats["candidates"] == 4
    assert {n: shape_hash(v) for n, v in shapes.items()} == before     # booleans run non-destructive

    def no_kernel(*args, **kwargs):
        raise AssertionError("the kernel ran on a cached pair")
    monkeypatch.setattr(relations_mod, "relate", no_kernel)
    warm = relation_table(Assembly(shapes), cache=PairCache(tmp_path / "cache"))
    assert warm.stats["kernel_queries"] == 0 and warm.stats["cache_hits"] == 4
    assert all(r.cached for r in warm)
    assert {(r.a, r.b): r.to_dict() | {"cached": False} for r in warm} == \
           {(r.a, r.b): r.to_dict() for r in cold}
    monkeypatch.undo()

    asm = Assembly(shapes)
    moved = Assembly()
    for n in asm:
        moved.add(n, shapes[n], (0, 0, 1) if n == "c" else None)
    again = relation_table(moved, cache=PairCache(tmp_path / "cache"))
    assert again.stats["kernel_queries"] == 1 and again.stats["cache_hits"] == 3   # base-c only
    assert again.get("c", "base").state == "apart"

    other_tol = relation_table(Assembly(shapes), Tolerances(touch_mm=0.1), cache=PairCache(tmp_path / "cache"))
    assert other_tol.stats["cache_hits"] == 0                                         # tolerances are in the key


@needs_cad
def test_cache_hits_across_processes(tmp_path):
    """OCP's TopoDS hash changes per process; the content hash must not."""
    cache = tmp_path / "cache"
    env_path = str(ROOT / "src")
    cmd = [sys.executable, str(ROOT / "tools" / "gate_timing.py"), "--parts", "20", "--cache", str(cache), "--json"]
    first = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True,
                                      env={"PYTHONPATH": env_path, "PATH": ""}).stdout)
    assert first["kernel_queries"] == first["candidates"] > 0
    from cadagent.gates import relation_table
    asm, _ = timing_module().synthetic_assembly(20)
    table = relation_table(asm, cache=PairCache(cache))
    assert table.stats["kernel_queries"] == 0 and table.stats["cache_hits"] == first["candidates"]


def test_pair_cache_round_trip_and_bad_records(tmp_path):
    cache = PairCache(tmp_path)
    key = "ab" * 32
    assert cache.get(key) is None and cache.misses == 1
    cache.put(key, {"state": "touching"})
    assert cache.get(key) == {"state": "touching"} and cache.hits == 1
    (tmp_path / key[:2] / f"{key}.json").write_text("{not json")
    assert cache.get(key) is None
    with pytest.raises(ValueError):
        cache.get("../../etc/passwd")


# ----------------------------------------------------------------------------- verdict

def test_verdict_pass_warn_fail_and_honesty_rules(tmp_path):
    ok = verdict("demo", [Check("a", "pass", "fine")], assumptions=["boxes only"])
    assert ok["pass"] is True and ok["status"] == "pass" and ok["findings"] == []
    assert ok["physical_fit_verified"] is False and ok["schema"] == "cadagent.gate/1"
    warn = verdict("demo", [Check("a", "pass", "fine"), Check("b", "warn", "close", parts=("x",))],
                   assumptions=["boxes only"])
    assert warn["pass"] is True and warn["status"] == "warn" and [f["id"] for f in warn["findings"]] == ["b"]
    fail = verdict("demo", [Check("a", "fail", "thin", evidence={"min_mm": 0.8, "points": ((1, 2, 3),)})],
                   assumptions=["rays at face centres"], limits={"wall_mm": 2.4},
                   exclusions=[{"parts": ["insert", "boss"], "reason": "heat-set knurl"}])
    assert fail["pass"] is False and fail["counts"] == {"pass": 0, "warn": 0, "fail": 1}
    assert fail["checks"][0]["evidence"]["points"] == [[1, 2, 3]]
    empty = verdict("demo", [], assumptions=["nothing declared"])
    assert empty["pass"] is False and empty["findings"][0]["id"] == "demo:nothing-checked"

    with pytest.raises(ValueError, match="assumption"):
        verdict("demo", [Check("a", "pass", "fine")], assumptions=[])
    with pytest.raises(ValueError, match="duplicate"):
        verdict("demo", [Check("a", "pass", ""), Check("a", "fail", "")], assumptions=["x"])
    with pytest.raises(ValueError, match="reason"):
        verdict("demo", [Check("a", "pass", "")], assumptions=["x"], exclusions=[{"parts": ["a"]}])
    with pytest.raises(ValueError, match="status"):
        Check("a", "ok", "")
    with pytest.raises(ValueError, match="overwrite"):
        verdict("demo", [Check("a", "pass", "")], assumptions=["x"], extra={"pass": True})

    path = write_verdict(tmp_path / "gates" / "demo.json", fail)
    assert json.loads(path.read_text()) == fail
    first = path.read_bytes()
    write_verdict(path, fail)
    assert path.read_bytes() == first                                   # no timestamp: identical bytes
    with pytest.raises(ValueError):
        write_verdict(tmp_path / "x.json", {"pass": True})


def test_verdict_converts_numpy_evidence():
    np = pytest.importorskip("numpy")
    v = verdict("demo", [Check("a", "pass", "", evidence={"t": np.float64(2.4), "arr": np.arange(3)})],
                assumptions=["x"])
    assert json.loads(json.dumps(v))["checks"][0]["evidence"] == {"t": 2.4, "arr": [0, 1, 2]}
    with pytest.raises(ValueError, match="NaN"):
        verdict("demo", [Check("a", "pass", "", evidence={"t": float("nan")})], assumptions=["x"])
