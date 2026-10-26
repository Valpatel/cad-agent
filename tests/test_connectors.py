"""Mating-connector envelopes, windows and the 3D plug-fit check."""

from __future__ import annotations

import pytest

from cadagent import connectors as cn

# A front wall 3 mm thick whose inner face is 1.5 mm in front of a receptacle face at w = 2.
WALL = (3.5, 6.5)

def rj45_mate(**kw):
    return {"face": [0.0, 0.5, 16.0, 14.0], "face_w": 2.0, "centre_on": "receptacle", "clearance": 0.5,
            "plugs": [{"family": "rj45", "cavity": [2.0, 3.0, 14.0, 13.0]}], **kw}

def test_rj45_body_and_boot_from_the_cavity():
    body, boot = cn.rj45([2.0, 3.0, 14.0, 13.0])
    assert body["u"] == pytest.approx([2.15, 13.85]) and body["v"] == pytest.approx([3.0, 14.5])
    assert boot["w"][0] == body["w"][1]

def test_only_segments_that_cross_the_wall_size_the_window():
    segs = cn.passing_segments(rj45_mate(), WALL)
    assert [s["what"] for s in segs] == ["plug body + latch lever"]  # the boot starts outside the wall

def test_receptacle_centred_window_is_symmetric_about_the_face():
    m = rj45_mate()
    w = cn.window(m, WALL)
    face = m["face"]
    assert (w[0] + w[2]) / 2 == pytest.approx((face[0] + face[2]) / 2)
    assert (w[1] + w[3]) / 2 == pytest.approx((face[1] + face[3]) / 2)
    assert w[3] >= 14.5 + 0.5 - 1e-9  # latch lever + clearance

def test_flanged_terminal_plug_is_taller_than_its_header():
    # Header 8.4 tall with flange screws at v = 5.33; the Phoenix STF plug is 15 tall and 20.17 wide.
    body, leads = cn.terminal_plug_flanged([[2.38, 5.33], [17.62, 5.33]])
    assert body["u"][1] - body["u"][0] == pytest.approx(20.17)
    assert body["v"] == pytest.approx([1.43, 16.43])
    m = {"face": [0.0, 1.58, 20.32, 9.98], "face_w": 2.7, "centre_on": "plug", "clearance": 0.5,
         "plugs": [{"family": "terminal_plug_flanged", "screws": [[2.38, 5.33], [17.62, 5.33]]}]}
    w = cn.window(m, WALL)
    assert w[3] == pytest.approx(16.93) and w[1] == pytest.approx(0.93)

def test_margins_report_offsets_and_flag_a_window_that_is_too_low():
    m = rj45_mate()
    low = [-0.5, -3.0, 16.5, 14.0]  # a bbox-with-pins style window: room below the board, none for the latch
    r = cn.window_margins(m, low, WALL)
    assert r["margins_mm"]["top"] == pytest.approx(-0.5)
    assert r["window_centre_minus_face_centre_mm"][1] < -1.0

def test_unknown_family_is_an_error():
    with pytest.raises(ValueError, match="unknown plug family"):
        cn.plug_segments({"family": "nope"})

cq = pytest.importorskip("cadquery")

def wall_with(win, frame):
    """A 3 mm wall in front of the receptacle, with ``win`` cut through it."""
    u0, v0, u1, v1 = win
    a, b = frame.point(-20, -20, WALL[0]), frame.point(40, 40, WALL[1])
    lo, hi = [min(p, q) for p, q in zip(a, b)], [max(p, q) for p, q in zip(a, b)]
    slab = cq.Solid.makeBox(*(h - l for h, l in zip(hi, lo)), cq.Vector(*lo))
    c0, c1 = frame.point(u0, v0, WALL[0] - 1), frame.point(u1, v1, WALL[1] + 1)
    lo, hi = [min(p, q) for p, q in zip(c0, c1)], [max(p, q) for p, q in zip(c0, c1)]
    return slab.cut(cq.Solid.makeBox(*(h - l for h, l in zip(hi, lo)), cq.Vector(*lo)))

@pytest.mark.parametrize("frame", [
    cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0)),  # front wall
    cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0)),   # rear wall, left-handed: mirrored internally
])
def test_derived_window_passes_and_bbox_window_fails_in_3d(frame):
    m = rj45_mate()
    good = cn.window(m, WALL)
    r = cn.check_ports({"lan": m}, {"lan": frame}, {"wall": wall_with(good, frame)}, {"lan": WALL}, {"lan": good})
    assert r["pass"], r
    bad = [-0.5, -3.0, 16.5, 14.0]
    r = cn.check_ports({"lan": m}, {"lan": frame}, {"wall": wall_with(bad, frame)}, {"lan": WALL}, {"lan": bad})
    row = r["ports"]["lan"]
    assert not r["pass"] and row["sweep_interference_mm3"]["wall"] > 0

def test_envelope_lands_where_the_frame_says():
    frame = cn.PanelFrame((10, 20, 30), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    m = {"face_w": 0.0, "plugs": [{"family": "box", "u": [0, 2], "v": [0, 3], "w": [0, 4]}]}
    bb = cn.envelope(m, frame, sweep=False).BoundingBox()
    assert [bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax] == pytest.approx([10, 12, 16, 20, 30, 33])

def test_plug_to_plug_collisions_are_reported():
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    a = {"face_w": 0.0, "plugs": [{"family": "trs35", "axis": [0, 0], "overmold_d": 10}]}
    b = {"face_w": 0.0, "plugs": [{"family": "trs35", "axis": [9, 0], "overmold_d": 10}]}
    r = cn.check_ports({"a": a, "b": b}, {"a": frame, "b": frame}, {}, {"a": WALL, "b": WALL})
    assert not r["pass"] and r["plug_to_plug"][0]["ports"] == ["a", "b"]

def test_clearance_grown_envelope_is_an_offset_with_round_corners():
    # A sharp 10 x 10 plug in a window 0.5 larger all round with R0.5 corners meets a 0.5 clearance exactly.
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    m = {"face_w": 0.0, "clearance": 0.5, "plugs": [{"family": "box", "u": [0, 10], "v": [0, 10], "w": [0, 20]}]}
    win = [-0.5, -0.5, 10.5, 10.5]
    slab = cq.Solid.makeBox(60, 3, 60, cq.Vector(-20, -6.5, -20))
    hole = cq.Workplane().box(11, 11, 10).edges("|Z").fillet(0.5).val().rotate((0, 0, 0), (1, 0, 0), 90).translate((5, -5, 5))
    r = cn.check_ports({"p": m}, {"p": frame}, {"wall": slab.cut(hole)}, {"p": WALL}, {"p": win})
    assert r["pass"], r["ports"]["p"]

def test_rounded_overmold_corners_are_modelled():
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    m = {"face_w": 0.0, "plugs": [{"family": "overmold", "centre": [0, 0], "width": 10, "height": 6, "r": 3, "length": 10}]}
    v = cn.envelope(m, frame, sweep=False).Volume()
    assert v == pytest.approx((10 * 6 - (4 - 3.141592653589793) * 9) * 10, rel=1e-3)
