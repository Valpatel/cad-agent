"""Range-of-motion clearance (#251): cadagent.mechanical.clearance.

* collisions() and sweep() on stand-in shapes (axis-aligned boxes whose overlap is computed here), so the pair logic,
  the tolerance, skip, only and the error reporting run without a CAD kernel;
* the same on real cadquery solids: two boxes, and a two-link arm swept over three poses, one of which drives the
  second link into a post;
* envelope_profile's slope limit against the pieces it covers, and swept_envelope's volume against the analytic
  cylinder, cone and cone frustum.
"""
from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.mechanical import clearance as C


class Box:
    """An axis-aligned box with the two methods collisions() uses."""

    def __init__(self, lo, hi):
        self.lo, self.hi = tuple(map(float, lo)), tuple(map(float, hi))

    def BoundingBox(self):
        (x0, y0, z0), (x1, y1, z1) = self.lo, self.hi
        return SimpleNamespace(xmin=x0, ymin=y0, zmin=z0, xmax=x1, ymax=y1, zmax=z1)

    def intersect(self, other):
        d = [max(0.0, min(a1, b1) - max(a0, b0)) for a0, a1, b0, b1 in zip(self.lo, self.hi, other.lo, other.hi)]
        return SimpleNamespace(Volume=lambda: d[0] * d[1] * d[2])


def cube(x, size=10.0):
    return Box((x, 0, 0), (x + size, size, size))


# ----------------------------------------------------------------------------- collisions, kernel-free

def test_overlapping_boxes_are_a_hit_and_apart_or_touching_ones_are_not():
    hits = C.collisions({"a": cube(0), "b": cube(5), "c": cube(30), "d": cube(40)})   # c and d touch on a face
    assert hits == [{"a": "a", "b": "b", "part_a": "a", "part_b": "b", "volume_mm3": 500.0}]


def test_the_tolerance_is_a_threshold_on_overlap_volume():
    pair = {"a": cube(0), "b": cube(9.99)}                       # 0.01 x 10 x 10 = 1 mm^3
    assert C.collisions(pair) == []                               # default 2 mm^3
    assert [h["volume_mm3"] for h in C.collisions(pair, tolerance_mm3=0.5)] == [1.0]


def test_skip_takes_instance_pairs_part_pairs_or_a_callable():
    inst = {"rod_1": ("rod", cube(0)), "gland_1": ("gland", cube(5)), "frame": ("frame", cube(8))}
    assert len(C.collisions(inst)) == 3
    by_name = C.collisions(inst, skip=[("gland_1", "rod_1")])
    assert {(h["a"], h["b"]) for h in by_name} == {("rod_1", "frame"), ("gland_1", "frame")}
    by_part = C.collisions(inst, skip={("gland", "rod")})
    assert {(h["a"], h["b"]) for h in by_part} == {("rod_1", "frame"), ("gland_1", "frame")}
    only_frame = C.collisions(inst, skip=lambda a, b: "frame" not in (a[1], b[1]))
    assert {(h["a"], h["b"]) for h in only_frame} == {("rod_1", "frame"), ("gland_1", "frame")}


def test_only_checks_pairs_with_at_least_one_selected_instance():
    inst = {"arm": cube(0), "base": cube(5), "track": cube(7)}
    hits = C.collisions(inst, only=lambda n: n == "arm")
    assert {(h["a"], h["b"]) for h in hits} == {("arm", "base"), ("arm", "track")}


def test_a_failing_boolean_is_an_error_never_a_pass(monkeypatch):
    def broken(a, b):
        raise RuntimeError("BRep_API: command not done")

    monkeypatch.setattr(C, "_overlap_volume", broken)
    hits = C.collisions({"a": cube(0), "b": cube(9.999), "c": cube(50)})
    assert len(hits) == 1 and "volume_mm3" not in hits[0]
    assert hits[0]["a"] == "a" and "command not done" in hits[0]["error"]
    # a nonsense volume is an error too, not a clear result
    monkeypatch.setattr(C, "_overlap_volume", lambda a, b: float("nan"))
    assert "error" in C.collisions({"a": cube(0), "b": cube(5)})[0]
    report = C.sweep({"p": None}, lambda _: {"a": cube(0), "b": cube(5)})
    assert report["pass"] is False and report["errors"] == 1 and report["collisions"] == 0


# ----------------------------------------------------------------------------- sweep, kernel-free

def slider(x):
    """A block sliding along x past a fixed wall at x = 50..60."""
    return {"block": ("block", cube(x)), "wall": ("wall", Box((50, -5, -5), (60, 15, 15)))}


def test_sweep_reports_each_pose_and_fails_on_one_collision(tmp_path):
    out = tmp_path / "exports" / "clearance-checks.json"
    report = C.sweep({"home": 0.0, "mid": 20.0, "far": 45.0}, slider, out_path=out)
    assert report["pass"] is False and report["physical_fit_verified"] is False
    assert report["collisions"] == 1 and report["errors"] == 0 and report["poses_checked"] == 3
    assert [report["poses"][p]["pass"] for p in ("home", "mid", "far")] == [True, True, False]
    assert report["poses"]["far"]["collisions"][0]["volume_mm3"] == 500.0
    assert report["poses"]["far"]["params"] == 45.0
    assert "not a continuous sweep" in report["limits"]
    assert json.loads(out.read_text(encoding="utf-8")) == report


def test_sweep_passes_only_when_every_pose_was_placed_and_clear():
    assert C.sweep({"home": 0.0, "mid": 20.0}, slider)["pass"] is True

    def place(x):
        if x > 30:
            raise ValueError("pose out of reach")
        return slider(x)

    report = C.sweep({"home": 0.0, "far": 45.0}, place)
    assert report["pass"] is False and "out of reach" in report["poses"]["far"]["error"]
    empty = C.sweep({}, slider)
    assert empty["pass"] is False and "nothing was checked" in empty["note"]


# ----------------------------------------------------------------------------- envelope profile, kernel-free

@pytest.mark.parametrize("slope_deg", [45.0, 30.0, 60.0])
def test_the_profile_covers_every_piece_and_never_exceeds_the_slope(slope_deg):
    pieces = [(0, 40, 6, 6), (40, 41, 18, 18), (41, 90, 4, 9), (60, 70, 12, 12)]
    xs, rs = C.envelope_profile(pieces, step=0.5, max_slope_deg=slope_deg)
    slopes = abs((rs[1:] - rs[:-1]) / (xs[1:] - xs[:-1]))
    assert slopes.max() <= math.tan(math.radians(slope_deg)) + 1e-9
    for x0, x1, r0, r1 in pieces:
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = x0 + t * (x1 - x0)
            assert float(np.interp(x, xs, rs)) >= r0 + t * (r1 - r0) - 1e-9


def test_a_radius_step_becomes_a_cone_at_the_slope_limit():
    xs, rs = C.envelope_profile([(0, 50, 5, 5), (50, 100, 20, 20)], step=0.5, max_slope_deg=45)
    assert list(zip(xs.round(9), rs.round(9))) == [(0, 5), (35, 5), (50, 20), (100, 20)]
    xs, rs = C.envelope_profile([(0, 100, 10, 10)], taper_ends=True)
    assert list(zip(xs.round(9), rs.round(9))) == [(-10, 0), (0, 10), (100, 10), (110, 0)]


def test_bad_pieces_are_refused():
    for bad in ([], [(10, 0, 1, 1)], [(0, 1, -1, 1)], [(0, 10, 1, 1), (100, 110, 1, 1)]):
        with pytest.raises(ValueError):
            C.envelope_profile(bad)
    with pytest.raises(ValueError):
        C.envelope_profile([(0, 1, 1, 1)], max_slope_deg=90)


# ----------------------------------------------------------------------------- real solids (cadquery)

def test_real_boxes_overlapping_touching_and_apart():
    cq = pytest.importorskip("cadquery")
    box = lambda x: cq.Solid.makeBox(10, 10, 10, pnt=cq.Vector(x, 0, 0))
    hits = C.collisions({"a": box(0), "b": box(5), "c": box(15), "d": box(40)})   # b and c touch on a face
    assert [(h["a"], h["b"]) for h in hits] == [("a", "b")]
    assert hits[0]["volume_mm3"] == pytest.approx(500.0, rel=1e-6)


def arm_at(q):
    """A two-link planar arm about z (link 1 in z 0..10, link 2 above it in z 10..20, so the links meet on a face)
    and a fixed post centred on (100, -50)."""
    import cadquery as cq
    q1, q2 = q
    link1 = cq.Solid.makeBox(100, 10, 10, pnt=cq.Vector(0, -5, 0)).rotate((0, 0, 0), (0, 0, 1), q1)
    tip = (100 * math.cos(math.radians(q1)), 100 * math.sin(math.radians(q1)), 0)
    link2 = (cq.Solid.makeBox(80, 10, 10, pnt=cq.Vector(0, -5, 10)).rotate((0, 0, 0), (0, 0, 1), q1 + q2)
             .translate(cq.Vector(*tip)))
    post = cq.Solid.makeBox(20, 20, 100, pnt=cq.Vector(90, -60, -50))
    return {"link1": ("link", link1), "link2": ("link", link2), "post": ("post", post)}


def test_a_two_link_arm_sweep_finds_the_one_colliding_pose(tmp_path):
    pytest.importorskip("cadquery")
    poses = {"straight": (0.0, 0.0), "raised": (30.0, 20.0), "elbow_down": (0.0, -90.0)}
    report = C.sweep(poses, arm_at, out_path=tmp_path / "clearance.json")
    assert report["pass"] is False and report["physical_fit_verified"] is False
    assert [report["poses"][p]["pass"] for p in poses] == [True, True, False]
    (hit,) = report["poses"]["elbow_down"]["collisions"]
    assert (hit["a"], hit["b"]) == ("link2", "post")
    assert hit["volume_mm3"] == pytest.approx(10 * 20 * 10, rel=1e-6)   # x 95..105, y -60..-40, z 10..20
    assert report["poses"]["elbow_down"]["params"] == [0.0, -90.0]


def test_the_swept_envelope_matches_the_analytic_volumes():
    pytest.importorskip("cadquery")
    pi = math.pi
    cyl = C.swept_envelope([(0, 100, 10, 10)])
    assert cyl.isValid() and cyl.Volume() == pytest.approx(pi * 10 ** 2 * 100, rel=1e-6)
    bb = cyl.BoundingBox()
    assert (bb.xmin, bb.xmax) == (pytest.approx(0, abs=1e-6), pytest.approx(100, abs=1e-6))
    cone = C.swept_envelope([(0, 100, 0, 10)], max_slope_deg=10)       # 10 / 100 is within tan(10°)
    assert cone.Volume() == pytest.approx(pi * 10 ** 2 * 100 / 3, rel=1e-6)
    frustum = lambda h, r, R: pi * h / 3 * (R * R + R * r + r * r)
    stepped = C.swept_envelope([(0, 50, 5, 5), (50, 100, 20, 20)])     # 45°: a cone from x = 35 to 50
    assert stepped.Volume() == pytest.approx(pi * 25 * 35 + frustum(15, 5, 20) + pi * 400 * 50, rel=1e-6)
    ramp = 15 / math.tan(math.radians(30))
    shallow = C.swept_envelope([(0, 50, 5, 5), (50, 100, 20, 20)], max_slope_deg=30)
    # the cone's foot (x = 24.02) falls between samples 0.5 mm apart: the profile is right to a fraction of a step
    assert shallow.Volume() == pytest.approx(pi * 25 * (50 - ramp) + frustum(ramp, 5, 20) + pi * 400 * 50, rel=1e-5)
    capped = C.swept_envelope([(0, 100, 10, 10)], taper_ends=True)
    assert capped.isValid() and capped.Volume() == pytest.approx(pi * 100 * 100 + 2 * pi * 100 * 10 / 3, rel=1e-6)


def test_a_swept_envelope_cuts_a_neighbour_in_one_piece():
    cq = pytest.importorskip("cadquery")
    block = cq.Solid.makeBox(160, 60, 60, pnt=cq.Vector(-30, -30, -30))   # holds the cutter, x -20..120
    cutter = C.swept_envelope([(0, 40, 8, 8), (40, 100, 20, 20)], taper_ends=True)
    cut = block.cut(cutter)
    assert cut.isValid()
    assert cut.Volume() == pytest.approx(block.Volume() - cutter.Volume(), rel=1e-6)
    assert C.collisions({"block": cut, "cutter": cutter}) == []
