"""Gate machinery: Assembly, broad phase, pairwise relations, the pair cache and the verdict file."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cadagent.review.gates import Check, PairCache, Tolerances, aabb_distances, relation_table, verdict, write_verdict
from cadagent.review.gates import relations as relations_mod  # the module

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
    from cadagent.review.gates import relate
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
    from cadagent.review.gates import relate
    cavity = box(20, 20, 20, (-10, -10, -5))
    resting = relate(ball(5), cavity)                 # tangent to the cavity floor, from inside
    assert resting.state == "contains" and resting.wall_mm == pytest.approx(0.0, abs=1e-6)
    poking = relate(ball(5, cq.Vector(0, 0, -0.3)), cavity)
    assert poking.state == "overlapping"
    cap = 3.141592653589793 * 0.3 ** 2 * (15 - 0.3) / 3                 # spherical cap below the floor
    assert poking.a_outside_b_mm3 == pytest.approx(cap, rel=1e-6)


@needs_cad
def test_touch_tolerance_and_contact_area_of_a_pin_in_its_bore():
    from cadagent.review.gates import relate
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
    def boom(kind, a, b):
        raise RuntimeError("BRepAlgoAPI_Common failed")
    monkeypatch.setattr(relations_mod, "_boolean", boom)
    rel = relations_mod.relate(box(1, 1, 1), box(1, 1, 1, (0.5, 0, 0)))
    assert rel.state == "unknown" and "Common failed" in rel.error


# ----------------------------------------------------------------------------- distance first (#186)

def waffle(n, z=0.0, up=False):
    """A 40 x 40 x 10 block with an n x n grid of 2 mm pockets 4 deep in one face (down, or up when ``up``):
    a single SOLID with 5 n^2 + 6 faces, so OCCT's inner-solution test has every vertex to classify."""
    wp = cq.Workplane().box(40, 40, 10, centered=(True, True, False))
    pts = [(-16 + 32 * i / (n - 1), -16 + 32 * j / (n - 1)) for i in range(n) for j in range(n)]
    s = wp.faces("<Z").workplane().pushPoints(pts).rect(2, 2).cutBlind(-4).val()
    s = s.mirror("XY") if up else s
    return s.translate(cq.Vector(0, 0, z)).Solids()[0]


def hollow_block():
    """A 20 mm cube with a closed 12 mm cubic void at its centre: one solid, two shells."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.TopoDS import TopoDS
    outer, inner = box(20, 20, 20), box(12, 12, 12, (4, 4, 4))
    make = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(outer.Shells()[0].wrapped))
    make.Add(TopoDS.Shell_s(inner.Shells()[0].wrapped.Reversed()))
    solid = cq.Solid(make.Solid())
    assert solid.isValid() and solid.Volume() == pytest.approx(20 ** 3 - 12 ** 3)
    return solid


def relation_fixtures():
    """(label, a, b, tolerances): every pair the relation tests above use, plus the cases the distance-first
    step must hand to the full path (a part inside a compound, a torus with one vertex inside a block) or may
    decide itself (a ball in a closed void, many-faced solids)."""
    t = Tolerances()
    block = box(10, 10, 10, (-5, -5, 0)).cut(cq.Solid.makeCylinder(2, 10))
    sphere = ball(3, cq.Vector(5, 5, 5))
    cavity = box(20, 20, 20, (-10, -10, -5))
    out = [("apart boxes", box(10, 10, 10), box(10, 10, 10, (12, 0, 0)), t),
           ("touching boxes", box(10, 10, 10), box(10, 10, 10, (10, 5, 0)), t),
           ("overlapping boxes", box(10, 10, 10), box(10, 10, 10, (5, 0, 0)), t),
           ("ball in box", sphere, box(10, 10, 10), t),
           ("ball resting in cavity", ball(5), cavity, t),
           ("ball poking through cavity", ball(5, cq.Vector(0, 0, -0.3)), cavity, t),
           ("0.005 mm hover", box(10, 10, 10), box(10, 10, 10, (10.005, 0, 0)), t),
           ("0.02 mm hover", box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0)), t),
           ("0.02 mm hover, loose", box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0)), Tolerances(touch_mm=0.05)),
           ("pin in bore", cq.Solid.makeCylinder(2, 10), block, t),
           ("separate solids", cq.Compound.makeCompound([box(1, 1, 1), box(1, 1, 1, (3, 0, 0))]),
            box(1, 1, 1, (0.5, 0, 0)), t),
           ("one solid of a compound inside", cq.Compound.makeCompound([box(1, 1, 1, (4, 4, 4)), box(1, 1, 1, (30, 0, 0))]),
            box(10, 10, 10), t),
           ("buried pin", cq.Solid.makeCylinder(2, 10, cq.Vector(10, 10, 5)), box(20, 20, 20), t),
           ("ball in a compound block", sphere, cq.Compound.makeCompound([box(10, 10, 10)]), t),
           ("torus in block", cq.Solid.makeTorus(5, 1), box(40, 40, 40, (-20, -20, -20)), t),
           ("ball in a closed void", ball(3, cq.Vector(10, 10, 10)), hollow_block(), t),
           ("ball in the wall of a hollow block", ball(1, cq.Vector(2, 2, 10)), hollow_block(), t),
           ("waffles 1 mm apart", waffle(4), waffle(4, 21, up=True), t)]
    return out + [(f"{label}, flipped", b, a, tol) for label, a, b, tol in out]


def _verdict(rel):
    """A relation without the parts the distance-first step leaves out by design: the volume-integration record
    (it integrates nothing) and its method marker."""
    d = rel.to_dict()
    d["witness"] = {k: v for k, v in d.get("witness", {}).items() if k not in ("volume_integration", "method")}
    return d


@needs_cad
def test_distance_first_gives_the_full_paths_relation_on_every_fixture():
    """Every state, gap, witness point and volume is the full path's, and only proven-apart pairs skip it."""
    from cadagent.review.gates import relate
    seen = set()
    for label, a, b, tol in relation_fixtures():
        fast = relate(a, b, tol)
        full = relations_mod._relate_full(a.wrapped, b.wrapped, tol, names=("a", "b"), volumes=None,
                                          contact_area=True)
        assert _verdict(fast) == _verdict(full), label
        assert (fast.witness.get("method") == relations_mod.DISTANCE_FIRST) == (full.state == "apart"), label
        seen.add(full.state)
    assert seen == {"apart", "touching", "overlapping", "contains"}


@needs_cad
def test_a_part_inside_a_compound_is_contains_not_apart_by_distance():
    """BRepExtrema's inner-solution test runs only on SOLID shapes: against a compound it reports the boundary
    gap for a ball wholly inside, which is the trap a distance-only shortcut would fall into."""
    from cadagent.review.gates import relate
    inside, container = ball(3, cq.Vector(5, 5, 5)), cq.Compound.makeCompound([box(10, 10, 10)])
    gap = relations_mod._distance(inside.wrapped, container.wrapped)[0]
    assert gap == pytest.approx(2.0)                                     # the trap
    assert relations_mod._proven_apart(inside.wrapped, container.wrapped, Tolerances(), ("a", "b")) is None
    rel = relate(inside, container)
    assert rel.state == "contains" and rel.contained == "a_in_b" and "method" not in rel.witness


@needs_cad
def test_either_check_alone_keeps_shared_volume_out_of_distance_first(monkeypatch):
    """The classifier catches a containment the boolean missed; the common catches a crossing the distance
    missed (both faked here), so a distance-first apart needs two kernel answers to agree."""
    real_boolean, tol = relations_mod._boolean, Tolerances()
    monkeypatch.setattr(relations_mod, "_boolean",
                        lambda kind, x, y: relations_mod._compound([]) if kind == "common" else real_boolean(kind, x, y))
    inside, block = ball(3, cq.Vector(5, 5, 5)), box(10, 10, 10)
    assert relations_mod._proven_apart(inside.wrapped, block.wrapped, tol, ("a", "b")) is None
    monkeypatch.setattr(relations_mod, "_boolean", real_boolean)
    a, b = box(10, 10, 10), box(10, 10, 10, (-9.9, 2, 2))      # 0.1 mm into a; each stand-in corner is outside
    assert not relations_mod._any_point_not_outside(relations_mod._boundary_points(a.wrapped), b.wrapped)
    assert not relations_mod._any_point_not_outside(relations_mod._boundary_points(b.wrapped), a.wrapped)
    monkeypatch.setattr(relations_mod, "_distance", lambda x, y: (3.0, [0.0, 0.0, 0.0], [3.0, 0.0, 0.0]))
    assert relations_mod._proven_apart(a.wrapped, b.wrapped, tol, ("a", "b")) is None


@needs_cad
def test_one_point_per_connected_set_of_faces_and_none_without_a_vertex():
    from OCP.BRep import BRep_Builder
    from OCP.Geom import Geom_Plane
    from OCP.TopoDS import TopoDS_Face
    from OCP.gp import gp_Pln
    assert len(relations_mod._boundary_points(box(1, 1, 1).wrapped)) == 1
    assert len(relations_mod._boundary_points(hollow_block().wrapped)) == 2           # the outer shell and the void's
    two = cq.Compound.makeCompound([box(1, 1, 1), box(1, 1, 1, (3, 0, 0))])
    assert len(relations_mod._boundary_points(two.wrapped)) == 2
    bare = TopoDS_Face()
    BRep_Builder().MakeFace(bare, Geom_Plane(gp_Pln()), 1e-7)                        # natural bounds: no edge, no vertex
    assert relations_mod._boundary_points(bare) is None


@needs_cad
def test_a_kernel_failure_in_the_distance_first_step_falls_back_to_the_full_path(monkeypatch):
    from cadagent.review.gates import relate
    a, b = box(10, 10, 10), box(10, 10, 10, (12, 0, 0))
    expected = relate(a, b)
    monkeypatch.setattr(relations_mod, "_boundary_points", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    rel = relate(a, b)
    assert rel.state == "apart" and "method" not in rel.witness and "volume_integration" in rel.witness
    assert _verdict(rel) == _verdict(expected)


@needs_cad
def test_distance_first_skips_the_volume_work_and_beats_the_full_path(monkeypatch):
    """The budget (#186): an apart pair of many-faced solids integrates nothing and runs one boolean (the common,
    which must come back empty), and takes under a quarter of the full path's time. On Gyropup's leg (PR #186's
    body) the full path spent most of its time in BRepExtrema's inner-solution test, as here."""
    from cadagent.review.gates import relate
    a, b = waffle(5), waffle(5, 21, up=True)
    calls = {"volume": 0, "boolean": []}
    real_volume, real_boolean = relations_mod._measure_volume, relations_mod._boolean

    def volume(shape):
        calls["volume"] += 1
        return real_volume(shape)

    def boolean(kind, x, y):
        calls["boolean"].append(kind)
        return real_boolean(kind, x, y)
    monkeypatch.setattr(relations_mod, "_measure_volume", volume)
    monkeypatch.setattr(relations_mod, "_boolean", boolean)
    t0 = time.perf_counter()
    fast = relate(a, b, validated=True)
    fast_s = time.perf_counter() - t0
    assert fast.state == "apart" and fast.gap_mm == pytest.approx(1.0) and fast.witness["method"] == "distance-first"
    assert calls == {"volume": 0, "boolean": ["common"]}
    t0 = time.perf_counter()
    full = relations_mod._relate_full(a.wrapped, b.wrapped, Tolerances(), names=("a", "b"), volumes=None,
                                      contact_area=True)
    full_s = time.perf_counter() - t0
    assert _verdict(fast) == _verdict(full)
    assert fast_s < full_s / 4, (fast_s, full_s)


@needs_cad
def test_the_table_never_integrates_a_part_measured_only_against_far_parts(monkeypatch):
    from cadagent.review.gates import Assembly
    asm = Assembly({"a": box(10, 10, 10), "near": box(10, 10, 10, (10.5, 0, 0)), "over": box(10, 10, 10, (0, 5, 0))})
    measured = []
    real = relations_mod._measure_volume
    monkeypatch.setattr(relations_mod, "_measure_volume", lambda s: (measured.append(s), real(s))[1])
    table = relation_table(asm)
    assert table.get("a", "near").state == "apart" and table.get("a", "near").witness["method"] == "distance-first"
    assert table.get("a", "over").state == "overlapping"
    assert not any(s.IsSame(asm.shape("near")) for s in measured)
    assert any(s.IsSame(asm.shape("a")) for s in measured) and any(s.IsSame(asm.shape("over")) for s in measured)


# ----------------------------------------------------------------------------- Assembly

@needs_cad
def test_assembly_locations_bodies_groups_and_validation():
    from cadagent.review.gates import Assembly, bounding_box
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
    from cadagent.review.gates import Assembly, bounding_box
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
    from cadagent.review.gates import Assembly, relation_table
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
    from cadagent.review.gates import relation_table
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
def test_content_hash_is_the_shared_evidence_function_and_bound_to_content():
    from cadagent.review.evidence import shape_content_hash
    from cadagent.review.gates import Assembly
    a, b = box(1, 2, 3), box(1, 2, 3)
    assert shape_content_hash(a) == shape_content_hash(b)
    assert shape_content_hash(box(1, 2, 3.001)) != shape_content_hash(a)
    asm = Assembly()
    assert asm.add("a", a).content_hash == shape_content_hash(a)
    recorded = "ab" * 32
    assert asm.add("b", b, content_hash=recorded).content_hash == recorded       # never re-hashed
    with pytest.raises(ValueError, match="sha256"):
        asm.add("c", box(1, 1, 1), content_hash="not-a-hash")


@needs_cad
def test_read_back_shapes_keep_the_cache_warm_through_recorded_hashes(tmp_path):
    """A shape read back from BREP re-hashes differently; the hash recorded at build time does not."""
    import io
    from cadagent.review.evidence import shape_content_hash
    from cadagent.review.gates import Assembly
    built = {"a": box(5, 5, 5).rotate(cq.Vector(), cq.Vector(0, 0, 1), 30).moved(cq.Location(cq.Vector(1.1, 2.2, 0))),
             "b": box(5, 5, 5, (5, -3, 0))}
    recorded = {n: shape_content_hash(s) for n, s in built.items()}

    def read_back(shape):
        buf = io.BytesIO()
        shape.exportBrep(buf)
        buf.seek(0)
        return cq.Shape.importBrep(buf)

    cold = relation_table(Assembly(built), cache=PairCache(tmp_path))
    assert cold.stats["kernel_queries"] == 1
    loaded = Assembly()
    for n, s in built.items():
        loaded.add(n, read_back(s), content_hash=recorded[n])
    warm = relation_table(loaded, cache=PairCache(tmp_path))
    assert warm.stats["cache_hits"] == 1 and warm.stats["kernel_queries"] == 0


@needs_cad
def test_cache_hit_skips_the_kernel_and_a_moved_part_requeries_only_its_pairs(tmp_path, monkeypatch):
    from cadagent.review.gates import Assembly, relation_table
    shapes = {"base": box(30, 30, 2), "a": box(5, 5, 5, (0, 0, 2)), "b": box(5, 5, 5, (5, 0, 2)),
              "c": box(5, 5, 5, (20, 20, 2))}
    from cadagent.review.gates import shape_content_hash
    before = {n: shape_content_hash(v) for n, v in shapes.items()}
    cache = PairCache(tmp_path / "cache")
    cold = relation_table(Assembly(shapes), cache=cache)
    assert cold.stats["kernel_queries"] == cold.stats["candidates"] == 4
    assert {n: shape_content_hash(v) for n, v in shapes.items()} == before     # booleans run non-destructive

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
    from cadagent.review.gates import relation_table
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


# ----------------------------------------------------------------------------- review regressions (PR #27)

def overlapping_compound():
    """Two solids sharing 1 mm of height: a compound the boolean kernel silently mishandles."""
    return cq.Compound.makeCompound([box(2, 2, 1.5), box(2, 2, 1.5, (0, 0, 0.5))])


@needs_cad
def test_a_compound_of_interfering_solids_is_refused_or_unknown_never_touching():
    from cadagent.review.gates import Assembly, relate, solid_interference
    bad = overlapping_compound()
    assert solid_interference(bad) and solid_interference(box(1, 1, 1)) == []
    rel = relate(box(2, 2, 3), bad)
    assert rel.state == "unknown" and "fuse" in rel.error
    with pytest.raises(ValueError, match="fuse"):
        Assembly().add("bad", bad)
    root = cq.Assembly(name="root")
    root.add(cq.Workplane().add([box(2, 2, 1.5), box(2, 2, 1.5, (0, 0, 0.5))]), name="node")
    with pytest.raises(ValueError, match="fuse"):
        Assembly.from_cadquery(root)
    ok = cq.Compound.makeCompound([box(1, 1, 1), box(1, 1, 1, (3, 0, 0))])   # separate solids are fine
    assert relate(ok, box(1, 1, 1, (0.5, 0, 0))).state == "overlapping"


@needs_cad
def test_volume_cross_check_turns_a_silent_kernel_error_into_unknown(monkeypatch):
    """If Common came back empty (or over-counted) without an error, the Cut volumes disagree."""
    real = relations_mod._boolean
    a, b = box(10, 10, 10), box(10, 10, 10, (5, 0, 0))

    def empty_common(kind, x, y):
        return relations_mod._compound([]) if kind == "common" else real(kind, x, y)
    monkeypatch.setattr(relations_mod, "_boolean", empty_common)
    rel = relations_mod.relate(a, b)
    assert rel.state == "unknown" and "volumes disagree" in rel.error

    def overcounted_common(kind, x, y):                 # common = all of a: would read as a_in_b
        return x if kind == "common" else real(kind, x, y)
    monkeypatch.setattr(relations_mod, "_boolean", overcounted_common)
    rel = relations_mod.relate(a, b)
    assert rel.state == "unknown"


@needs_cad
def test_unexamined_pairs_read_unchecked_unless_their_boxes_prove_a_gap():
    from cadagent.review.gates import Assembly
    asm = Assembly({"a": box(10, 10, 10), "alt": box(10, 10, 10, (5, 0, 0)), "m": box(1, 1, 1, (40, 0, 0)),
                    "far": box(1, 1, 1, (80, 0, 0))})
    skipped = relation_table(asm, skip_pairs=[("a", "alt")]).get("a", "alt")
    assert skipped.state == "unchecked" and not skipped.exact
    only = relation_table(asm, only=["m"])
    assert only.get("a", "alt").state == "unchecked"
    assert only.get("a", "far").state == "apart" and only.get("a", "far").gap_lower_bound_mm > 60
    assert only.get("a", "alt", exact=True).state == "overlapping"


@needs_cad
def test_a_buried_part_is_contains_and_counts_as_interference():
    from cadagent.review.gates import Assembly
    asm = Assembly({"block": box(20, 20, 20), "pin": cq.Solid.makeCylinder(2, 10, cq.Vector(10, 10, 5))})
    table = relation_table(asm)
    rel = table.get("pin", "block")
    assert rel.state == "contains" and rel.contained == "a_in_b" and rel.interferes
    assert table.interferences() == [table.get("block", "pin")]
    assert not relation_table(Assembly({"a": box(1, 1, 1), "b": box(1, 1, 1, (1, 0, 0))})).get("a", "b").interferes


@needs_cad
def test_cavities_are_cached_items_outside_the_pair_table_and_move_with_their_part(tmp_path, monkeypatch):
    from cadagent.review.gates import Assembly, relate_pair
    shell = box(20, 20, 20).cut(box(16, 16, 18, (2, 2, 2)))
    asm = Assembly()
    asm.add("hopper", shell, body="hopper")
    asm.add_cavity("void", box(16, 16, 18, (2, 2, 2)), part="hopper")
    asm.add("ball", ball(3, cq.Vector(10, 10, 5)))
    asm.add("base", box(40, 40, 2, (-10, -10, -2)))
    assert "void" not in asm.names and relation_table(asm).stats["candidates"] == 2     # hopper-ball, hopper-base
    rel = relate_pair(asm, "ball", "void", cache=PairCache(tmp_path))
    assert rel.state == "contains" and rel.contained == "a_in_b" and rel.wall_mm == pytest.approx(0.0, abs=1e-6)
    monkeypatch.setattr(relations_mod, "relate", lambda *a, **k: pytest.fail("kernel ran on a cached pair"))
    assert relate_pair(asm, "ball", "void", cache=PairCache(tmp_path)).cached
    monkeypatch.undo()
    with pytest.raises(KeyError):
        asm.add_cavity("orphan", box(1, 1, 1), part="nobody")
    lifted = asm.posed("hopper", (0, 0, 30))
    assert relate_pair(lifted, "ball", "void").state == "apart"          # the void went up with the hopper
    assert lifted.shape("base") is asm.shape("base")                       # static parts are not re-located


@needs_cad
def test_the_kernel_version_is_part_of_the_cache_key(tmp_path, monkeypatch):
    from cadagent.review.gates import Assembly
    shapes = {"a": box(1, 1, 1), "b": box(1, 1, 1, (1, 0, 0))}
    relation_table(Assembly(shapes), cache=PairCache(tmp_path))
    assert relation_table(Assembly(shapes), cache=PairCache(tmp_path)).stats["cache_hits"] == 1
    monkeypatch.setattr(relations_mod, "_kernel_version", lambda: "99.0")
    assert relation_table(Assembly(shapes), cache=PairCache(tmp_path)).stats["cache_hits"] == 0


@needs_cad
def test_from_build_takes_placed_shapes_recorded_hashes_cavities_joints_and_fasteners(tmp_path, monkeypatch):
    """The dossier hand-over: live result and a read-back from BREP give the same keys, places and cache keys."""
    from cadagent.review import dossier
    from cadagent.mechanical.fasteners import socket_head_envelope
    from cadagent.review.gates import Assembly
    with dossier.use_registry() as reg:
        reg.add_part("base", lambda p: box(40, 40, 4), grounded=True, section="S1")
        reg.add_part("tub", lambda p: box(20, 20, 10).cut(box(16, 16, 8, (2, 2, 2))), section="S2",
                     place=cq.Location(cq.Vector(5, 5, 4)))
        reg.add_cavity("tub", "tub_void", lambda p: box(16, 16, 8, (2, 2, 2)))
        reg.add_part("lid", lambda p: box(20, 20, 2, (5, 5, 14)).cut(cq.Solid.makeCylinder(1.7, 2, cq.Vector(8, 8, 14))),
                     section="S2")
        reg.add_part("flap", lambda p: box(10, 2, 10, (30, 0, 4)), section="S3")
        reg.joint("J1", "revolute", parts=("flap", "base"), axis=((30, 0, 4), (0, 1, 0)), range_deg=(0, 90))
        reg.fastener("m3x6", clamps="lid", into="tub", name="lid_screw", at=[dossier.Axis((8, 8, 16), (0, 0, -1))],
                     shape=lambda p: socket_head_envelope(3, 6, 5.5, 3))
        reg.fastener("m3x4", clamps="flap", into="base", name="hinge_screw",
                     at=[dossier.Axis((35, 0, 9), (0, 1, 0))], shape=lambda p: socket_head_envelope(3, 4, 5.5, 3))
        live = reg.build({}, out_dir="exports", root=tmp_path)
    asm = Assembly.from_build(live)
    assert sorted(asm.names) == ["base", "flap", "hinge_screw", "lid", "lid_screw", "tub"]
    assert asm["lid_screw"].kind == "fastener" and asm["tub"].kind == "part" and asm["tub"].group == "S2"
    hashes = live.content_hashes()
    assert all(asm[n].content_hash == hashes[n] for n in asm.names)
    assert relations_mod.bounding_box(asm.shape("lid_screw"))[2] == pytest.approx(10, abs=1e-6)   # seat 16, 6 long
    assert relations_mod.bounding_box(asm.shape("tub"))[:3] == pytest.approx((5, 5, 4), abs=1e-6)
    assert asm.cavities["tub_void"].container == "tub" and asm.cavities["tub_void"].content_hash == hashes["tub_void"]
    assert asm["flap"].body == "flap" and asm["hinge_screw"].body == "flap" and asm["lid_screw"].body == "lid_screw"
    assert set(asm.joints) == {"J1"} and set(asm.fastener_axes) == {"lid_screw", "hinge_screw"}

    cold = relation_table(asm, cache=PairCache(tmp_path / "cache"))
    assert cold.get("lid_screw", "lid").state == "touching" and cold.get("flap", "base").state == "touching"
    loaded = dossier.load_geometry(tmp_path / "exports" / "dossier-geometry.json")
    monkeypatch.setattr(relations_mod, "shape_content_hash", lambda s: pytest.fail("a read-back shape was re-hashed"))
    warm = relation_table(Assembly.from_build(loaded), cache=PairCache(tmp_path / "cache"))
    assert warm.stats["kernel_queries"] == 0 and warm.stats["cache_hits"] == cold.stats["candidates"]
