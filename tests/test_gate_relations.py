"""Gate machinery: Assembly, broad phase, pairwise relations, the pair cache and the verdict file."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import time
from collections import Counter
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


# ----------------------------------------------------------------------------- the distance on solids (#186)

def waffle(n, z=0.0, up=False):
    """A 40 x 40 x 10 block with an n x n grid of 2 mm pockets 4 deep in one face (down, or up when ``up``):
    a single SOLID with 5 n^2 + 6 faces, so BRepExtrema's inner-solution test has every vertex to classify."""
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


def with_loose(shape, loose):
    """``shape`` plus a free edge or vertex in one compound: valid input that a distance between faces misses."""
    return cq.Compound.makeCompound([shape, loose])


def relation_fixtures():
    """(label, a, b, tolerances): every pair the relation tests above use, plus cases where the distance must not be
    taken between the faces (a part inside a compound, a torus with one vertex inside a block, free edges and
    vertices) and cases where it may (a ball in a closed void, many-faced solids)."""
    t = Tolerances()
    block = box(10, 10, 10, (-5, -5, 0)).cut(cq.Solid.makeCylinder(2, 10))
    sphere = ball(3, cq.Vector(5, 5, 5))
    cavity = box(20, 20, 20, (-10, -10, -5))
    far = box(10, 10, 10, (20, 0, 0))
    out = [("apart boxes", box(10, 10, 10), box(10, 10, 10, (12, 0, 0)), t),
           ("touching boxes", box(10, 10, 10), box(10, 10, 10, (10, 5, 0)), t),
           ("overlapping boxes", box(10, 10, 10), box(10, 10, 10, (5, 0, 0)), t),
           ("ball in box", sphere, box(10, 10, 10), t),
           ("ball resting in cavity", ball(5), cavity, t),
           ("ball poking through cavity", ball(5, cq.Vector(0, 0, -0.3)), cavity, t),
           ("0.005 mm hover", box(10, 10, 10), box(10, 10, 10, (10.005, 0, 0)), t),
           ("0.02 mm hover", box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0)), t),
           ("0.02 mm hover, loose", box(10, 10, 10), box(10, 10, 10, (10.02, 0, 0)), Tolerances(touch_mm=0.05)),
           ("0.5 mm hover, touch 0", box(10, 10, 10), box(10, 10, 10, (10.5, 0, 0)), Tolerances(touch_mm=0.0)),
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
           ("free edge reaching the other part",
            with_loose(box(10, 10, 10), cq.Edge.makeLine(cq.Vector(5, 5, 5), cq.Vector(20, 5, 5))), far, t),
           ("free edge 0.5 mm short",
            with_loose(box(10, 10, 10), cq.Edge.makeLine(cq.Vector(5, 5, 5), cq.Vector(19.5, 5, 5))), far, t),
           ("free vertex 0.2 mm away", with_loose(box(10, 10, 10), cq.Vertex.makeVertex(19.8, 5, 5)), far, t),
           ("waffles 1 mm apart", waffle(4), waffle(4, 21, up=True), t)]
    return out + [(f"{label}, flipped", b, a, tol) for label, a, b, tol in out]


def _faces_used(monkeypatch):
    """Record whether each ``_solid_distance`` answered from the faces (True) or handed over to ``_distance``."""
    used = []
    real = relations_mod._distance

    def solid_distance(a, b, tol):
        calls = []
        monkeypatch.setattr(relations_mod, "_distance", lambda x, y: (calls.append((x, y)), real(x, y))[1])
        try:
            out = real_solid(a, b, tol)
        finally:
            monkeypatch.setattr(relations_mod, "_distance", real)
        used.append(not any(x is a for x, _ in calls))
        return out
    real_solid = relations_mod._solid_distance
    monkeypatch.setattr(relations_mod, "_solid_distance", solid_distance)
    return used


@needs_cad
def test_every_fixture_relation_is_byte_identical_to_brepextrema_on_the_solids(monkeypatch):
    """The whole Relation (state, gap, points, volumes, witness) is what the old call gave, and the faces answer
    exactly for the apart pairs that have no loose sub-shape."""
    from cadagent.review.gates import relate
    seen = set()
    for label, a, b, tol in relation_fixtures():
        with monkeypatch.context() as m:
            used = _faces_used(m)
            new = relate(a, b, tol).to_dict()
        with monkeypatch.context() as m:
            m.setattr(relations_mod, "_solid_distance", lambda x, y, t: relations_mod._distance(x, y))
            old = relate(a, b, tol).to_dict()
        assert new == old, label
        loose = "free" in label
        assert used == ([] if old["state"] not in ("apart", "touching") else [old["state"] == "apart" and not loose]), label
        seen.add(old["state"])
    assert seen == {"apart", "touching", "overlapping", "contains", "unknown"}   # unknown: Cut fails on a free edge


@needs_cad
def test_the_inner_vertex_test_answers_as_brepextrema_does():
    """``_inner_vertex`` against BRepExtrema's own InnerSolution: a ball in a box, a one-vertex torus in a block,
    a ball in a closed void (outside), a compound container (BRepExtrema does not test it) and a far box."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    block = box(40, 40, 40, (-20, -20, -20))
    cases = [(ball(3, cq.Vector(5, 5, 5)), box(10, 10, 10)), (cq.Solid.makeTorus(5, 1), block),
             (ball(3, cq.Vector(10, 10, 10)), hollow_block()), (ball(3, cq.Vector(5, 5, 5)),
                                                                 cq.Compound.makeCompound([box(10, 10, 10)])),
             (box(1, 1, 1, (30, 0, 0)), block)]
    for inner, outer in cases:
        d = BRepExtrema_DistShapeShape(inner.wrapped, outer.wrapped)
        d.Perform()
        ours = relations_mod._inner_vertex(inner.wrapped, outer.wrapped) or relations_mod._inner_vertex(outer.wrapped, inner.wrapped)
        assert ours == d.InnerSolution(), (inner, outer)
    assert [relations_mod._inner_vertex(o.wrapped, i.wrapped) for i, o in cases] == [True, True, False, False, False]


@needs_cad
def test_loose_sub_shapes_send_the_distance_to_brepextrema_on_the_whole_shape():
    edge = with_loose(box(10, 10, 10), cq.Edge.makeLine(cq.Vector(5, 5, 5), cq.Vector(20, 5, 5)))
    point = with_loose(box(10, 10, 10), cq.Vertex.makeVertex(19.8, 5, 5))
    assert relations_mod._loose(edge.wrapped) and relations_mod._loose(point.wrapped)
    assert not any(relations_mod._loose(s.wrapped) for s in (box(1, 1, 1), ball(2), cq.Solid.makeTorus(5, 1),
                                                             cq.Solid.makeCone(2, 0, 3), hollow_block()))
    far, tol = box(10, 10, 10, (20, 0, 0)), Tolerances()
    assert relations_mod._solid_distance(point.wrapped, far.wrapped, tol)[0] == pytest.approx(0.2)
    assert relations_mod._distance(relations_mod._faces(point.wrapped), far.wrapped)[0] == pytest.approx(10.0)  # the trap


@needs_cad
def test_a_kernel_failure_between_the_faces_falls_back_to_brepextrema_on_the_solids(monkeypatch):
    from cadagent.review.gates import relate
    a, b = box(10, 10, 10), box(10, 10, 10, (12, 0, 0))
    expected = relate(a, b).to_dict()
    monkeypatch.setattr(relations_mod, "_inner_vertex", lambda s, o: (_ for _ in ()).throw(RuntimeError("boom")))
    assert relate(a, b).to_dict() == expected


@needs_cad
def test_the_distance_on_many_faced_solids_beats_brepextrema_on_the_solids(monkeypatch):
    """The budget (#186): two pocketed blocks 1 mm apart. relate() gives the same relation as with BRepExtrema on
    the solids, from the faces alone. The distance step alone (``_solid_distance`` against ``_distance``) must take
    under half the time. Measured: about 9x on 24 OCCT threads, 5-6x on 4 and about 4x on 2. OCCT builds about ten
    classifiers per thread, so the old step gets cheaper on smaller machines. On Gyropup's leg (PR #198) that
    inner-solution test was most of the time of an apart pair, as here."""
    from cadagent.review.gates import relate
    a, b = waffle(5), waffle(5, 21, up=True)
    with monkeypatch.context() as m:
        used = _faces_used(m)
        new = relate(a, b, validated=True)
    assert used == [True]                                         # BRepExtrema never ran on the solids
    with monkeypatch.context() as m:
        m.setattr(relations_mod, "_solid_distance", lambda x, y, t: relations_mod._distance(x, y))
        old = relate(a, b, validated=True)
    assert new.state == "apart" and new.gap_mm == pytest.approx(1.0) and new.to_dict() == old.to_dict()

    def best_of_two(step):
        times = []
        for _ in range(2):
            t0 = time.perf_counter()
            step()
            times.append(time.perf_counter() - t0)
        return min(times)
    sa, sb, tol = a.wrapped, b.wrapped, Tolerances()
    new_s = best_of_two(lambda: relations_mod._solid_distance(sa, sb, tol))
    old_s = best_of_two(lambda: relations_mod._distance(sa, sb))
    assert new_s < old_s / 2, (new_s, old_s)


# ----------------------------------------------------------------------------- near-tangent crossings (#46)

CONE_SIN = (2 / 3) / math.sqrt(1 + 4 / 9)     # a move down by h puts the ball h * CONE_SIN into the wall


def cone_cavity():
    """The issue's cavity: a cone, radius 20 + 2/3 z for z in 0..30."""
    return cq.Solid.makeCone(20, 40, 30, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))


def cone_wall():
    """The part around that cavity: a block with the cone taken out."""
    return box(100, 100, 35, (-50, -50, -5)).cut(cone_cavity())


def ball_in_cone(h, phi, r=4.0):
    """A ball tangent to the cone wall from inside at z = 15 and azimuth ``phi``, then moved down ``h``."""
    k = 1 / math.sqrt(1 + 4 / 9)
    rho, z = 30 - r * k, 15 + r * CONE_SIN
    return ball(r, cq.Vector(rho * math.cos(phi), rho * math.sin(phi), z - h))


def cap(d, r=4.0):
    """The volume of a ball's cap ``d`` deep (a flat wall)."""
    return math.pi * d * d * (3 * r - d) / 3


def plate():
    return box(60, 60, 5, (-30, -30, -5))           # its top face at z = 0


def tilted_cylinder(d, alpha=0.5, r=3.0, length=20.0):
    """A cylinder lying on the plate at ``alpha`` degrees to it, its lowest point (the low end's rim) ``d`` below
    z = 0: a crossing at a grazing angle."""
    c = cq.Solid.makeCylinder(r, length, cq.Vector(0, 0, 0), cq.Vector(1, 0, 0)).rotate(
        cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), alpha)
    a = math.radians(alpha)
    return c.translate(cq.Vector(-length / 2, 0, length * math.sin(a) + r * math.cos(a) - d))


def tilted_box(d, ax=0.3, ay=0.2):
    """A 10 x 10 x 5 box tilted 0.3 and 0.2 degrees, its lowest corner ``d`` below z = 0."""
    b = box(10, 10, 5, (-5, -5, 0)).rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), ax).rotate(
        cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), ay)
    return b.translate(cq.Vector(0, 0, -b.BoundingBox().zmin - d))


def without_probe(monkeypatch):
    monkeypatch.setattr(relations_mod, "_crossing_probe", lambda *args: None)


@needs_cad
@pytest.mark.parametrize("phi", [0.3, 0.7, 1.0])
def test_a_ball_through_a_cone_wall_is_never_read_touching_or_inside(phi, monkeypatch):
    """The issue's case. On OCP 7.9.3 (x86_64) the boolean reads no crossing at all at some of these depths:
    at phi = 0.3 at 0.033 mm, at 0.7 at 0.022 and 0.033 mm, at 1.0 at 0.011 mm (as ``contains`` against the
    cavity and ``touching`` against the wall's part). Whatever the kernel does, a crossing that shares more than
    ``overlap_mm3`` reads ``overlapping`` with about the cap's volume, or ``unknown`` with the depth found;
    a tangent ball and the 0.0055 mm crossing (0.0004 mm3, inside the tolerances) keep their answers."""
    from cadagent.review.gates import relate
    cavity, wall = cone_cavity(), cone_wall()
    for h in (0.0, 0.01, 0.02, 0.04, 0.06, 0.12):
        d = h * CONE_SIN
        b = ball_in_cone(h, phi)
        for other, inside in ((cavity, True), (wall, False)):
            rel = relate(b, other, contact_area=False)
            with monkeypatch.context() as m:
                without_probe(m)
                old = relate(b, other, contact_area=False)
            if cap(d) < 0.001:
                assert rel.to_dict() == old.to_dict(), (h, inside)
                # unknown only as before: OCP 7.9.3 makes an invalid cut of some tangent balls (see containment)
                assert rel.state in ("contains" if inside else "touching", "unknown"), (h, inside, rel)
                continue
            assert rel.state in ("overlapping", "unknown"), (h, inside, rel)
            if rel.state == "overlapping":
                shared = rel.a_outside_b_mm3 if inside else rel.overlap_mm3
                assert shared == pytest.approx(cap(d), rel=0.1), (h, inside)   # the cone's wall curves: about +6 %
                assert rel.to_dict() == old.to_dict()
            else:
                assert old.state in ("contains", "touching", "unknown"), (h, inside, old)
                if old.state != "unknown":                  # the boolean alone misread it: the probe caught it
                    hit = rel.witness["crossing_probe"]
                    assert hit["depth_mm"] == pytest.approx(d, abs=0.002), (h, inside, hit)
                    assert "crossing probe" in rel.error and "#46" in rel.error


def _kernel_misses(monkeypatch, kind):
    """Make the boolean miss every crossing the way it does in #46, so the cross-check still holds:
    ``"touching"``: the common empty, each cut the whole part; ``"contains"``: the common all of ``a``, a's cut
    empty (``b``'s cut is the real one)."""
    real = relations_mod._boolean

    def boolean(op, x, y):
        if kind == "touching":
            return relations_mod._compound([]) if op == "common" else x
        if op == "common":
            return x
        return relations_mod._compound([]) if x is first[0] else real(op, x, y)
    first = []

    def relate(a, b, *args, **kw):
        first[:] = [getattr(a, "wrapped", a)]
        return real_relate(a, b, *args, **kw)
    real_relate = relations_mod.relate
    monkeypatch.setattr(relations_mod, "_boolean", boolean)
    return relate


@needs_cad
@pytest.mark.parametrize("family", ["sphere through a face", "cylinder at a grazing angle", "boxes at a tilt"])
@pytest.mark.parametrize("kind", ["touching", "contains"])
def test_a_crossing_the_boolean_misses_is_unknown_with_its_depth(family, kind, monkeypatch):
    """The three fixture families, with the boolean made to miss the crossing as it does in #46 (the real
    kernel measures these planar crossings correctly; the cone above is where it misses). Below the probe's
    floor (a tenth of ``touch_mm``) the kernel's answer stands; from there on the answer is ``unknown`` with the
    depth, never ``touching`` or ``contains``."""
    floor = relations_mod._probe_floor(Tolerances())
    assert floor == pytest.approx(0.001)
    cavity = box(60, 60, 30, (-30, -30, 0))        # its floor at z = 0: the part crosses it from inside
    for d in (0.0005, 0.002, 0.005, 0.02):          # the simulated cut of b stays within the volume check
        part = {"sphere through a face": ball(4, cq.Vector(0, 0, 4 - d)),
                "cylinder at a grazing angle": tilted_cylinder(d),
                "boxes at a tilt": tilted_box(d)}[family]
        other = plate() if kind == "touching" else cavity
        with monkeypatch.context() as m:
            relate = _kernel_misses(m, kind)
            rel = relate(part, other, contact_area=False)
        if d < floor:
            assert rel.state == kind, (d, rel)
            continue
        assert rel.state == "unknown", (d, rel)
        hit = rel.witness["crossing_probe"]
        assert hit["depth_mm"] == pytest.approx(d, rel=0.1), (d, hit)
        assert hit["floor_mm"] == floor and hit["section_patches"] >= 1
        assert (hit["surface"], hit["other"]) in (("a", "b"), ("b", "a"))
        assert hit["lies"] == ("outside" if kind == "contains" and hit["surface"] == "a" else "inside")


def split_at_plate(part):
    """``part`` cut by the plate's top plane (z = 0) and glued back: the same solid, its faces split where they
    meet the plate, so the crossing runs along an existing edge (the review of #228)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Splitter
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopTools import TopTools_ListOfShape
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(part.wrapped)
    tools.Append(BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), -50, 50, -50, 50).Face())
    split = BRepAlgoAPI_Splitter()
    split.SetArguments(args)
    split.SetTools(tools)
    split.Build()
    halves = cq.Shape.cast(split.Shape()).Solids()
    assert len(halves) == 2
    glued = BRepAlgoAPI_Fuse(halves[0].wrapped, halves[1].wrapped)
    glued.Build()
    (whole,) = cq.Shape.cast(glued.Shape()).Solids()
    assert len(whole.Faces()) > len(part.Faces()) and whole.Volume() == pytest.approx(part.Volume(), rel=1e-6)
    return whole


@needs_cad
@pytest.mark.parametrize("family", ["ball", "cylinder"])
@pytest.mark.parametrize("kind", ["touching", "contains"])
def test_a_crossing_along_an_existing_edge_is_unknown_too(family, kind, monkeypatch):
    """A part whose faces are split exactly at the plate's face, sunk into it: the section's only edge lies
    along that split edge, and the kernel names no face pair for it. The faces next to the edge are sampled
    (a coarse pass, then the full grid), so the crossing the boolean is made to miss is still ``unknown``."""
    floor = relations_mod._probe_floor(Tolerances())
    cavity = box(60, 60, 30, (-30, -30, 0))
    # depths where the simulated cut of b stays within the volume check (a cylinder's crossing is wide)
    for d in {"ball": (0.0005, 0.002, 0.02), "cylinder": (0.0005, 0.002, 0.003)}[family]:
        part = split_at_plate({"ball": ball(4, cq.Vector(0, 0, 4 - d)),
                               "cylinder": cq.Solid.makeCylinder(3, 10, cq.Vector(0, 0, -d))}[family])
        a, b = part.wrapped, (plate() if kind == "touching" else cavity).wrapped
        assert all(entry[3] for entry in relations_mod._section_patches(a, b))   # no face pair named anywhere
        with monkeypatch.context() as m:
            relate = _kernel_misses(m, kind)
            rel = relate(part, plate() if kind == "touching" else cavity, contact_area=False)
        if d < floor:
            assert rel.state == kind, (d, rel)
            continue
        assert rel.state == "unknown", (d, rel)
        assert rel.witness["crossing_probe"]["depth_mm"] == pytest.approx(d, rel=0.1), (d, rel.witness)


@needs_cad
def test_a_curve_along_an_iso_line_gets_samples_across_it():
    """A cylinder standing 0.02 mm into the plate: the section is a circle at constant height on its side face,
    so the UV box of the curve has no height. The rows across it then run at the face's height halved again and
    again from the curve: four rings in the 0.02 mm band below the plate's face, without the face's edges or
    vertices, and evenly up the face."""
    side = next(f for f in cq.Solid.makeCylinder(3, 10, cq.Vector(0, 0, -0.02)).Faces() if f.geomType() == "CYLINDER")
    circle = [cq.Vector(3 * math.cos(t), 3 * math.sin(t), 0).toPnt() for t in (k * math.pi / 12 for k in range(25))]
    zs = sorted({round(p.Z(), 9) for p in relations_mod._patch_grid(side.wrapped, circle, 12, boundary=False)})
    assert [z for z in zs if z < 0] == pytest.approx([-10 / 2 ** k for k in (9, 10, 11, 12)], abs=1e-9)
    assert zs[-1] == pytest.approx(-0.02 + 10 * 12 / 13, abs=1e-9)      # and evenly up the 10 mm face
    # The circle goes once round the periodic face: the coarse pass's 4 columns are a quarter turn apart.
    coarse = relations_mod._patch_grid(side.wrapped, circle, relations_mod._PROBE_COARSE, boundary=False)
    counts = Counter(round(math.degrees(math.atan2(p.Y(), p.X())) % 360, 6) for p in coarse)
    turns = sorted(t for t, k in counts.items() if k > 1)          # columns, not the one centroid sample
    assert len(turns) == 4 and all(b - a == pytest.approx(90) for a, b in zip(turns, turns[1:]))


@needs_cad
def test_tangent_contacts_and_crossings_the_kernel_measured_keep_their_answers(monkeypatch):
    """The probe runs wherever the boundaries meet, and changes nothing where the boolean was right: tangent
    contacts (a point, a line, a face) and small crossings the kernel measured (a sharp corner 0.02 mm in shares
    7e-6 mm3: ``touching`` by the tolerances)."""
    from cadagent.review.gates import relate
    corner = box(2, 2, 2, (-1, -1, -1)).rotate(cq.Vector(0, 0, 0), cq.Vector(1, -1, 0), 54.7356103)
    corner = corner.translate(cq.Vector(0, 0, -corner.BoundingBox().zmin - 0.02))
    bore_block = box(20, 20, 10, (-10, -10, 0)).cut(cq.Solid.makeCylinder(4, 10))
    cases = [("ball tangent in the cone", ball_in_cone(0.0, 0.3), cone_cavity(), "contains"),
             ("ball tangent to the cone's part", ball_in_cone(0.0, 0.3), cone_wall(), "touching"),
             ("ball on a plate", ball(4, cq.Vector(0, 0, 4)), plate(), "touching"),
             ("cylinder on a plate", tilted_cylinder(0.0, alpha=0.0), plate(), "touching"),
             ("ball tangent in a bore", ball(4), cq.Solid.makeCylinder(4, 10, cq.Vector(0, 0, -5)), "contains"),
             ("pin in its bore", cq.Solid.makeCylinder(4, 10), bore_block, "touching"),
             ("touching boxes", box(10, 10, 10), box(10, 10, 10, (10, 5, 0)), "touching"),
             ("ball 0.005 mm into a plate", ball(4, cq.Vector(0, 0, 3.995)), plate(), "touching"),
             ("corner 0.02 mm into a plate", corner, plate(), "touching")]
    calls = []
    real = relations_mod._crossing_probe
    for label, a, b, state in cases:
        with monkeypatch.context() as m:
            m.setattr(relations_mod, "_crossing_probe", lambda *args: calls.append(label) or real(*args))
            rel = relate(a, b, contact_area=False)
        with monkeypatch.context() as m:
            without_probe(m)
            old = relate(a, b, contact_area=False)
        assert rel.state == state and rel.to_dict() == old.to_dict(), (label, rel)
        assert calls[-1:] == [label], label                       # the probe ran and found nothing to add
    assert 0 < relate(cases[-1][2], cases[-1][1]).overlap_mm3 < 1e-3   # the corner's crossing, measured


@needs_cad
def test_the_probe_runs_only_where_the_boundaries_meet_and_its_failure_is_unknown(monkeypatch):
    from cadagent.review.gates import relate
    calls = []
    monkeypatch.setattr(relations_mod, "_crossing_probe", lambda *args: calls.append(1))
    assert relate(box(10, 10, 10), box(10, 10, 10, (10.005, 0, 0))).state == "touching"    # a 0.005 mm gap
    assert relate(box(10, 10, 10), box(10, 10, 10, (12, 0, 0))).state == "apart"
    assert relate(ball(3, cq.Vector(5, 5, 5)), box(10, 10, 10)).state == "contains"         # a 2 mm wall
    assert relate(box(10, 10, 10), box(10, 10, 10, (5, 0, 0))).state == "overlapping"
    assert calls == []
    monkeypatch.undo()

    def boom(a, b):
        raise RuntimeError("section broke")
    monkeypatch.setattr(relations_mod, "_section_patches", boom)
    rel = relate(box(10, 10, 10), box(10, 10, 10, (10, 5, 0)))
    assert rel.state == "unknown" and "crossing probe failed on a touching pair" in rel.error
    assert "section broke" in rel.error


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
