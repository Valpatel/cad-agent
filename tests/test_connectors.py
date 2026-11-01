"""Mating-connector envelopes, windows and the 3D plug-fit check."""

from __future__ import annotations

import math

import pytest

from cadagent.mechanical import connectors as cn

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

# ----------------------------------------------------------------------------- the cable behind the plug

# A Cat6 patch cord, from Belden's data sheet (CAT6+ UTP PVC patch cord, technical data rev 0.202, 2025-02-07):
# nominal diameter 6.1 mm, "Min Bend Radius (Overall Cable): 25 mm". The shelf the enclosure stands on: its top is the
# wall slab's bottom (v = -20), 29.75 mm below the cable's axis. tools/motion_figures.py draws this port.
CAT6 = {"od": 6.1, "min_bend_radius": {"mm": 25.0},
        "basis": "Belden CAT6+ UTP PVC patch cord, technical data rev 0.202 (2025-02-07): nominal diameter 6.1 mm, "
                 "min bend radius (overall cable) 25 mm"}
SHELF = {"u": [-60.0, 80.0], "v": [-30.0, -20.0], "w": [-40.0, 120.0]}
# A USB 2.0 A-to-B cable, from Phoenix Contact's data sheet for VS-04-C-SDA/SDB/1,8 (item 1405578, 2013-11-12):
# external diameter 6.7 mm, "Minimum bending radius, fixed installation 5xD".
USB = {"od": 6.7, "min_bend_radius": {"x_od": 5}}

def wall_boxes(win):
    """The wall of ``wall_with`` as panel-frame boxes round the window, for the check without a CAD kernel."""
    u0, v0, u1, v1 = win
    return [{"u": [-20, 40], "v": [-20, v0], "w": list(WALL)}, {"u": [-20, 40], "v": [v1, 40], "w": list(WALL)},
            {"u": [-20, u0], "v": [v0, v1], "w": list(WALL)}, {"u": [u1, 40], "v": [v0, v1], "w": list(WALL)}]

def box_mate(cable, w=10.0):
    """A plug 4 x 4 mm square on the axis u = v = 0, ending at ``w``: the cable leaves at (0, 0, w)."""
    return {"face_w": 0.0, "plugs": [{"family": "box", "u": [-2, 2], "v": [-2, 2], "w": [0, w]}], "cable": cable}

def test_cable_spec_reads_the_radius_as_the_data_sheet_states_it():
    s = cn.cable_spec({"cable": USB})
    assert s["radius_mm"] == pytest.approx(33.5) and s["centreline_radius_mm"] == pytest.approx(33.5 + 3.35)
    s = cn.cable_spec({"cable": CAT6})
    assert s["radius_mm"] == 25.0 and s["centreline_radius_mm"] == pytest.approx(28.05)
    s = cn.cable_spec({"cable": dict(CAT6, measured_to="centreline")})
    assert s["centreline_radius_mm"] == 25.0
    assert [d for d, _ in s["directions"]] == ["+v", "-v", "+u", "-u"]
    assert cn.cable_spec({"plugs": []}) is None

@pytest.mark.parametrize("bad, match", [
    ({"min_bend_radius": 25}, "as the data sheet states it"),             # a bare number: mm, or times the OD?
    ({"min_bend_radius": {"inch": 1}}, "as the data sheet states it"),
    ({"measured_to": "outside"}, "measured_to"),
    ({"turn_deg": 200}, "out of range"),
    ({"directions": ["up"]}, "unknown cable direction"),
    ({"directions": []}, "at least one direction"),
])
def test_cable_spec_refuses_what_it_cannot_read(bad, match):
    with pytest.raises(ValueError, match=match):
        cn.cable_spec({"cable": {**CAT6, **bad}})

def test_bend_reach_in_closed_form():
    # 90 degrees: R + D/2 to the centreline, and D/2 more to the cable's surface, ahead and beside alike
    assert cn.bend_reach(6.1, 28.05) == pytest.approx({"ahead": 31.1, "beside": 31.1, "behind": 3.05})
    r = cn.bend_reach(6.1, 28.05, 45)
    assert r["ahead"] == pytest.approx(28.05 * math.sqrt(0.5) + 3.05)
    assert r["beside"] == pytest.approx(28.05 * (1 - math.sqrt(0.5)) + 3.05)
    r = cn.bend_reach(6.7, 36.85, 90, run=10)          # a straight run after a right angle goes beside, not ahead
    assert r == pytest.approx({"ahead": 40.2, "beside": 50.2, "behind": 3.35})
    r = cn.bend_reach(6.7, 36.85, 180, run=10)         # a U-turn: the run comes back towards the plug
    assert r == pytest.approx({"ahead": 40.2, "beside": 2 * 36.85 + 3.35, "behind": 3.35})

def test_bend_path_is_an_arc_from_the_exit_then_a_line():
    p = cn.bend_path((1, 2, 3), (0, -2), 10, 90, run=5)
    assert p["direction"] == (0, -1) and p["centre"] == pytest.approx((1, -8, 3))
    assert p["end"] == pytest.approx((1, -8, 13)) and p["tangent"] == pytest.approx((0, -1, 0))
    for s in (0, 3, 7.5, p["arc_length"]):
        q = p["point"](s)
        assert math.dist(q, p["centre"]) == pytest.approx(10)
    assert p["point"](p["length"]) == pytest.approx((1, -13, 13))

def test_cable_exit_is_the_centre_of_the_plugs_far_end():
    assert cn.cable_exit(rj45_mate()) == pytest.approx((8.0, 9.75, 42.0))       # the RJ45 boot's centre
    trs = {"face_w": 1.0, "plugs": [{"family": "trs35", "axis": [3, 4], "length": 30}]}
    assert cn.cable_exit(trs) == pytest.approx((3, 4, 31))
    assert cn.cable_exit(dict(trs, cable=dict(CAT6, exit=[5, 6]))) == pytest.approx((5, 6, 31))

@pytest.mark.parametrize("free, status", [(33.0, "pass"), (31.6, "warn"), (30.0, "fail")])
def test_a_wall_ahead_leaves_free_depth_less_the_reach(free, status):
    """A wall across the axis, ``free`` mm past the boot: every 90-degree turn clears it by free - (R + D)."""
    m = box_mate(CAT6)
    r = cn.cable_bend(m, {"door": {"u": [-99, 99], "v": [-99, 99], "w": [10 + free, 99]}})
    assert r["status"] == status and r["clearance_mm"] == pytest.approx(free - 31.1, abs=1e-6)
    assert all(row["clearance_mm"] == pytest.approx(free - 31.1, abs=1e-6) for row in r["directions"])
    assert r["direction"] == (None if status == "fail" else "+v")              # a tie: the first direction tried

def test_a_floor_beside_blocks_only_the_turn_towards_it():
    m = box_mate(CAT6)
    r = cn.cable_bend(m, {"floor": {"u": [-99, 99], "v": [-99, -30.0], "w": [-99, 99]}})
    rows = {row["direction"]: row for row in r["directions"]}
    assert rows["-v"]["clearance_mm"] == pytest.approx(30.0 - 31.1) and not rows["-v"]["clear"]
    assert rows["+v"]["clearance_mm"] == pytest.approx(30.0 - 3.05)            # from where the cable leaves
    assert r["status"] == "pass" and r["works"] == ["+v", "+u", "-u"]
    # only down allowed: it fails, and says how deep the cable runs into the floor
    r = cn.cable_bend(box_mate(dict(CAT6, directions=["-v"])), {"floor": {"u": [-99, 99], "v": [-99, -30.0], "w": [-99, 99]}})
    assert r["status"] == "fail" and r["direction"] is None and r["clearance_mm"] == pytest.approx(-1.1)

def test_a_part_the_cable_axis_runs_into_is_named():
    m = box_mate(dict(CAT6, directions=["+u"]))
    r = cn.cable_bend(m, {"post": {"u": [10, 14], "v": [-5, 5], "w": [20, 60]}})
    row = r["directions"][0]
    assert row["axis_inside"] == ["post"] and row["clearance_mm"] == pytest.approx(-3.05) and r["status"] == "fail"

def test_angles_and_a_run_after_the_bend():
    # 45 degrees from +u towards +v, a 45-degree turn, then 20 mm straight: the end lands where the closed form says
    m = box_mate(dict(CAT6, directions=[45], turn_deg=45, run=20))
    r = cn.cable_bend(m, {})
    assert r["directions"][0]["direction"] == "45 deg" and r["status"] == "pass" and r["clearance_mm"] is None
    d = 28.05 * (1 - math.sqrt(0.5)) + 20 * math.sqrt(0.5)
    assert r["directions"][0]["end"] == pytest.approx([round(d * math.sqrt(0.5), 3)] * 2 +
                                                      [round(10 + 28.05 * math.sqrt(0.5) + 20 * math.sqrt(0.5), 3)])
    # the run reaches a part the bend alone would miss
    post = {"u": [-99, 99], "v": [-99, 99], "w": [10 + 28.05 * math.sqrt(0.5) + 10, 99]}
    assert cn.cable_bend(box_mate(dict(CAT6, directions=[45], turn_deg=45)), {"p": post})["status"] == "pass"
    assert cn.cable_bend(m, {"p": post})["status"] == "fail"

def test_the_figures_port_turns_up_not_down_onto_the_shelf():
    m = dict(rj45_mate(), cable=CAT6)
    r = cn.cable_bend(m, {"wall": wall_boxes(cn.window(m, WALL)), "shelf": SHELF})
    rows = {row["direction"]: row for row in r["directions"]}
    # the shelf is 9.75 + 20 = 29.75 mm below the axis; turning down needs 25 + 6.1 = 31.1
    assert rows["-v"]["clearance_mm"] == pytest.approx(29.75 - 31.1) and rows["-v"]["nearest"] == "shelf"
    assert rows["+v"]["clearance_mm"] == pytest.approx(29.75 - 3.05)
    assert r["status"] == "pass" and r["direction"] == "+v" and r["works"] == ["+v", "+u", "-u"]
    text = " ".join(r["assumptions"])
    for said in ("one bend of 90 degrees in one plane", "starting at the boot's end", "a rigid boot",
                 "measured to the inside", "+v, -v, +u, -u", "wall, shelf", "not checked past the end of the bend",
                 "only the minimum radius is tried"):
        assert said in text, said
    with_run = cn.cable_bend(dict(m, cable=dict(CAT6, run=10)), {"shelf": SHELF})
    assert "not checked past the end of the run" in " ".join(with_run["assumptions"])

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

def world_box(frame, box):
    """A panel-frame box as a world solid."""
    a, b = frame.point(box["u"][0], box["v"][0], box["w"][0]), frame.point(box["u"][1], box["v"][1], box["w"][1])
    lo, hi = [min(p, q) for p, q in zip(a, b)], [max(p, q) for p, q in zip(a, b)]
    return cq.Solid.makeBox(*(h - l for h, l in zip(hi, lo)), cq.Vector(*lo))

@pytest.mark.parametrize("frame", [
    cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0)),   # front wall
    cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0)),    # rear wall, left-handed
    cn.PanelFrame((5, 7, 9), (0, 1, 0), (0, 0, 1), (1, 0, 0)),    # a side wall, away from the origin
])
def test_cable_bend_on_cad_shapes_matches_the_boxes(frame):
    """The same port, wall and shelf as CAD solids: OpenCASCADE's distances give the clearances the boxes give."""
    m = dict(rj45_mate(), cable=CAT6)
    win = cn.window(m, WALL)
    boxes = cn.cable_bend(m, {"wall": wall_boxes(win), "shelf": SHELF})
    shapes = cn.cable_bend(m, {"wall": wall_with(win, frame), "shelf": world_box(frame, SHELF)}, frame)
    for a, b in zip(boxes["directions"], shapes["directions"]):
        assert a["clearance_by_part_mm"] == pytest.approx(b["clearance_by_part_mm"], abs=1e-3), a["direction"]
    assert shapes["status"] == boxes["status"] == "pass" and shapes["direction"] == "+v"

def test_cable_bend_needs_the_frame_for_cad_shapes():
    with pytest.raises(ValueError, match="PanelFrame"):
        cn.cable_bend(box_mate(CAT6), {"slab": cq.Solid.makeBox(1, 1, 1)})

def test_cable_axis_inside_a_compound_is_found():
    # OCC gives 0 for a curve inside a solid but not inside a compound: each solid is measured on its own
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    block = cq.Compound.makeCompound([cq.Solid.makeBox(200, 200, 200, cq.Vector(-100, -100, 5)),
                                      cq.Solid.makeBox(1, 1, 1, cq.Vector(500, 500, 500))])
    r = cn.cable_bend(box_mate(dict(CAT6, directions=["+u"])), {"block": block}, frame)
    assert r["directions"][0]["axis_inside"] == ["block"] and r["status"] == "fail"

def test_check_ports_refuses_a_panel_frame_box():
    """A box is in one port's panel frame, and the plug sweep needs a solid: check_ports says so rather than failing
    the port with a NaN interference."""
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    m = dict(rj45_mate(), cable=CAT6)
    with pytest.raises(ValueError, match="shelf is a panel-frame box"):
        cn.check_ports({"lan": m}, {"lan": frame}, {"shelf": SHELF}, {"lan": WALL})

def test_check_ports_runs_the_cable_bend_and_fails_a_port_whose_cable_cannot_turn():
    frame = cn.PanelFrame((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    m = dict(rj45_mate(), cable=CAT6)
    win = cn.window(m, WALL)
    parts = {"wall": wall_with(win, frame), "shelf": world_box(frame, SHELF)}
    r = cn.check_ports({"lan": m}, {"lan": frame}, parts, {"lan": WALL}, {"lan": win})
    assert r["pass"] and r["ports"]["lan"]["cable_bend"]["direction"] == "+v"
    down = dict(m, cable=dict(CAT6, directions=["-v"]))      # say the cable must go down: it cannot
    r = cn.check_ports({"lan": down}, {"lan": frame}, parts, {"lan": WALL}, {"lan": win})
    assert not r["pass"] and r["ports"]["lan"]["cable_bend"]["status"] == "fail"
    assert r["ports"]["lan"]["sweep_interference_mm3"]["wall"] == 0     # the plug itself still fits
    # a neighbouring port's plug is in the way of a cable turned towards it
    near = {"face_w": 2.0, "plugs": [{"family": "box", "u": [30, 40], "v": [0, 20], "w": [0, 90]}]}
    side = dict(m, cable=dict(CAT6, directions=["+u"]))
    r = cn.check_ports({"lan": side, "near": near}, {"lan": frame, "near": frame}, {}, {"lan": WALL, "near": WALL})
    bend = r["ports"]["lan"]["cable_bend"]
    assert bend["status"] == "fail" and bend["directions"][0]["nearest"] == "plug near"

def test_box_distances_match_opencascade_on_random_bends():
    """The kernel-free distance (sampled, then refined) against OCC's exact one, on seeded random bends and boxes."""
    import random
    rnd = random.Random(168)
    frame = cn.PanelFrame((3, -2, 1), (0, 0, 1), (1, 0, 0), (0, 1, 0))
    for _ in range(40):
        cable = dict(CAT6, directions=[rnd.uniform(0, 360)], turn_deg=rnd.uniform(20, 180), run=rnd.choice([0, 15]))
        lo = [rnd.uniform(-45, 35), rnd.uniform(-45, 35), rnd.uniform(5, 60)]
        box = {k: [a, a + rnd.uniform(2, 30)] for k, a in zip("uvw", lo)}
        m = box_mate(cable)
        a = cn.cable_bend(m, {"b": box})["directions"][0]
        b = cn.cable_bend(m, {"b": world_box(frame, box)}, frame)["directions"][0]
        assert a["clearance_mm"] == pytest.approx(b["clearance_mm"], abs=2e-3), (cable, box)
        assert a["axis_inside"] == b["axis_inside"]
