"""Fastener and stack gate (T6): the kernel-free core on hand-written measurements, then real geometry.

The core tests feed ``evaluate`` a measurement shaped like ``measure``'s output (an M3 x 8 socket head in a 3 mm
lid, into a heat-set insert whose thread runs 3..8 mm below the seat, the host's hole bottom at 9 mm), so the rules
run in core CI without OCP. The geometry tests build small stacks through the dossier registry, as a project would,
and run the whole gate, including the existing ``blind_insert_stack`` numbers turned into solids.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

from cadagent.gates.fasteners import (DEFAULT_STOCK_MM, FastenerOptions, FastenerSpec, evaluate, fastener_gate,
                                      fasteners_from_build, install_step, present_at, table_markdown, tool_envelope,
                                      tools_from)

# ----------------------------------------------------------------------------- no CAD kernel needed

LINES = 8


def spec(**kw):
    base = dict(name="m3", key="m3x8_shcs", clamps="lid", into="insert", axes=[((0, 0, 10), (0, 0, -1))],
                tool="hex 2.5", length_mm=8.0, diameter_mm=3.0, thread_start_mm=3.0, thread_depth_mm=5.0,
                min_engagement_mm=1.5)
    base.update(kw)
    return FastenerSpec(**base)


def meas(**kw):
    """A clean measurement: the lid 0..3 and the host 3..20 under the head on every annulus line, the insert's thread
    3..8, the host's hole bottom at 9 on the axis, the lid's hole Ø3.4, the tool clear at step 4."""
    m = {"key": "m3", "origin": [0, 0, 10], "direction": [0, 0, -1], "d_mm": 3.0,
         "screw": {"length_mm": 8.0, "head_h_mm": 3.0, "head_r_mm": 2.75},
         "head": {"r_mm": 2.75, "h_mm": 3.0, "source": "solid"},
         "annulus": {"radius_mm": 2.125, "lines": [{"lid": [[0.0, 3.0]], "host": [[3.0, 20.0]]} for _ in range(LINES)]},
         "axis": {"host": [[9.0, 20.0]]},
         "thread": {"radius_mm": 1.38, "intervals": [[3.0, 8.0]], "parts": ["insert"]},
         "holes": {"lid": {"radius_mm": 1.7, "point": [1.7, 0, 8.5]}},
         "interference": {"insert": {"state": "overlapping", "overlap_mm3": 1.9, "t_range": [3.0, 8.0]}},
         "probe_end_t": 18.0, "roles": {"lid": "stack", "insert": "into"}, "excluded": [],
         "tool": {"tool": "hex 2.5", "step": 4, "step_fit": "lid", "present": ["lid", "host", "insert"],
                  "blocked": [], "clear": True}}
    m.update(kw)
    return m


def run(s=None, m=None, **opts):
    checks, row = evaluate(s or spec(), m or meas(), FastenerOptions(**opts))
    return {c.id.rsplit(":", 1)[1]: c for c in checks}, row


def failed(checks):
    return sorted(k for k, c in checks.items() if c.status == "fail")


def test_clean_stack_passes_every_check_and_fills_the_lesson_04_row():
    checks, row = run()
    assert {k: c.status for k, c in checks.items()} == {k: "pass" for k in
                                                         ("seat", "stack", "holes", "engagement", "tip", "length", "tool")}
    assert row["grip_mm"] == 3.0 and row["thread_start_mm"] == 3.0 and row["engagement_mm"] == 5.0
    assert row["engagement_threads"] == 10.0 and row["min_engagement_mm"] == 1.5
    assert row["thread_depth_required_mm"] == 5.0 and row["tip_clearance_mm"] == 1.0
    assert row["fits_mm"] == [4.5, 8.5] and row["stock"] is True and row["status"] == "pass"
    assert row["seat"] == [0, 0, 10] and row["thread_start"] == [0, 0, 7.0]
    assert checks["length"].evidence["stock_that_fits_mm"][:3] == [5.0, 6.0, 7.0]     # metric for an M3
    _, row = run(spec(diameter_mm=3.505, length_mm=3 / 8 * 25.4),
                 meas(d_mm=3.505, screw={"length_mm": 9.525, "head_h_mm": 3.0, "head_r_mm": 2.75}, axis={}))
    assert row["stock"] is True                                                     # a #6 x 3/8 in


def test_short_screw_fails_engagement_and_length():
    s = spec(length_mm=4.0)
    checks, row = run(s, meas(screw={"length_mm": 4.0, "head_h_mm": 3.0, "head_r_mm": 2.75}))
    assert failed(checks) == ["engagement", "length"]
    assert "1.00 mm of thread in insert (2.0 threads), under the minimum 1.50" in checks["engagement"].message
    assert row["engagement_mm"] == 1.0 and row["failed"] == ["engagement", "length"]


def test_screw_that_stops_before_the_thread_says_so():
    s = spec(length_mm=2.5)
    checks, _ = run(s, meas(screw={"length_mm": 2.5, "head_h_mm": 3.0, "head_r_mm": 2.75}))
    assert "stops 0.50 mm short of the thread" in checks["engagement"].message


def test_default_minimum_engagement_is_a_multiple_of_d_and_is_labelled():
    checks, row = run(spec(min_engagement_mm=None))
    assert row["min_engagement_mm"] == 2.4 and checks["engagement"].evidence["min_source"] == "default 0.8 d"


def test_long_screw_runs_into_the_host_past_its_thread():
    s = spec(length_mm=12.0)
    m = meas(screw={"length_mm": 12.0, "head_h_mm": 3.0, "head_r_mm": 2.75},
             interference={"insert": {"state": "overlapping", "overlap_mm3": 1.9, "t_range": [3.0, 8.0]},
                           "host": {"state": "overlapping", "overlap_mm3": 21.2, "t_range": [9.0, 12.0]}})
    checks, _ = run(s, m)
    assert failed(checks) == ["length", "tip"]
    assert "runs 3.00 mm into host (t 9.00..12.00)" in checks["tip"].message
    assert "host" in checks["tip"].parts and "m3" in checks["tip"].parts


def test_tip_close_to_the_hole_bottom_is_bottoming():
    checks, row = run(m=meas(axis={"host": [[8.2, 20.0]]}))
    assert failed(checks) == ["length", "tip"] and row["tip_clearance_mm"] == pytest.approx(0.2)
    assert "bottoming" in checks["tip"].message
    checks, _ = run(m=meas(axis={"host": [[8.2, 20.0]]}), tip_clearance_mm=0.1)
    assert failed(checks) == []


def test_tip_overlapping_the_receiver_beyond_its_thread_fails():
    m = meas(interference={"insert": {"state": "overlapping", "overlap_mm3": 2.4, "t_range": [3.0, 8.6]}})
    checks, _ = run(m=m)
    assert failed(checks) == ["tip"] and "past its thread" in checks["tip"].message


def test_closed_insert_end_on_the_axis_bottoms_the_screw():
    m = meas(axis={"insert": [[7.5, 8.0]], "host": [[9.0, 20.0]]})
    checks, _ = run(m=m)
    assert "tip" in failed(checks) and "runs 0.50 mm into insert" in checks["tip"].message


def test_head_gap_buried_head_other_part_and_overhang_fail_the_seat():
    lines = meas()["annulus"]["lines"]
    gap = copy.deepcopy(lines)
    for line in gap:
        line["lid"] = [[0.3, 3.0]]
    checks, _ = run(m=meas(annulus={"radius_mm": 2.125, "lines": gap}))
    assert "seat" in failed(checks) and "stands 0.300 mm off lid" in checks["seat"].message
    buried = copy.deepcopy(lines)
    for line in buried:
        line["lid"] = [[-0.5, 3.0]]
    checks, _ = run(m=meas(annulus={"radius_mm": 2.125, "lines": buried}))
    assert "buried" in checks["seat"].message
    washer = copy.deepcopy(lines)
    washer[0] = {"washer": [[0.0, 0.5]], "lid": [[0.5, 3.0]], "host": [[3.0, 20.0]]}
    checks, _ = run(m=meas(annulus={"radius_mm": 2.125, "lines": washer}))
    assert "bears on washer, not lid" in checks["seat"].message and "washer" in checks["seat"].parts
    edge = copy.deepcopy(lines)
    edge[0], edge[1] = {}, {}
    checks, _ = run(m=meas(annulus={"radius_mm": 2.125, "lines": edge}))
    assert "nothing under the head on 2 of 8 lines" in checks["seat"].message


def test_material_inside_the_head_without_a_solid_is_a_pocket_wall():
    m = meas(screw=None, head={"r_mm": 2.4, "h_mm": 3.0, "source": "default 1.6 d x 1.0 d"},
             head_clear={"lid": 2.1}, interference={})
    checks, _ = run(m=m)
    assert failed(checks) == ["seat"] and "pocket wall" in checks["seat"].message


def test_stack_gap_and_an_undeclared_part_in_the_stack_fail():
    lines = meas()["annulus"]["lines"]
    gap = copy.deepcopy(lines)
    for line in gap:
        line["host"] = [[3.5, 20.0]]
    checks, _ = run(m=meas(annulus={"radius_mm": 2.125, "lines": gap}))
    assert failed(checks) == ["stack"]
    assert "nothing under lid within 0.05 mm (next solid 0.500 mm further)" in checks["stack"].message
    assert "(lines 0, 1, 2, 3, 4, 5, 6, 7)" in checks["stack"].message
    two = spec(stack=["lid", "plate"])
    shim = copy.deepcopy(lines)
    for line in shim:
        line.update(lid=[[0.0, 3.0]], shim=[[3.0, 3.5]], plate=[[3.5, 6.0]], host=[[6.0, 20.0]])
    m = meas(annulus={"radius_mm": 2.125, "lines": shim}, roles={"lid": "stack", "plate": "stack", "insert": "into"})
    checks, _ = run(two, m)
    assert "shim sits inside the clamped stack" in checks["stack"].message and "shim" in checks["stack"].parts
    order = copy.deepcopy(lines)
    for line in order:
        line.update(lid=[[3.5, 6.0]], plate=[[0.0, 3.5]], host=[[6.0, 20.0]])
    two_rev = spec(stack=["lid", "plate"])
    checks, _ = run(two_rev, meas(annulus={"radius_mm": 2.125, "lines": order},
                                  roles={"lid": "stack", "plate": "stack", "insert": "into"}))
    assert "the stack meets ['plate', 'lid'], not ['lid', 'plate']" in checks["stack"].message


def test_missing_undersized_and_pull_through_holes_and_head_overlaps():
    checks, _ = run(m=meas(holes={"lid": {"radius_mm": 0.0, "point": [0, 0, 8.5]}}))
    assert "no hole in lid" in checks["holes"].message
    checks, _ = run(m=meas(holes={"lid": {"radius_mm": 1.52, "point": [1.52, 0, 8.5]}}))
    assert "Ø3.04, under Ø3.10" in checks["holes"].message
    checks, _ = run(m=meas(holes={"lid": {"radius_mm": 1.52, "point": [1.52, 0, 8.5]}}), hole_clearance_mm=0.0)
    assert checks["holes"].status == "pass"
    checks, _ = run(m=meas(holes={"lid": {"radius_mm": 2.9, "point": [2.9, 0, 8.5]}}))
    assert "pulls through" in checks["holes"].message
    checks, _ = run(m=meas(axis={"insert": [[3.0, 8.0]], "host": [[9.0, 20.0]]}))
    assert "no pilot or tap hole in insert" in checks["holes"].message
    m = meas(interference={"insert": {"state": "overlapping", "overlap_mm3": 1.9, "t_range": [3.0, 8.0]},
                           "lid": {"state": "overlapping", "overlap_mm3": 0.4, "t_range": [-1.0, -0.2]}})
    checks, _ = run(m=m)
    assert failed(checks) == ["seat"] and "the head cuts into lid" in checks["seat"].message


def test_an_undecided_kernel_pair_fails_where_it_belongs():
    m = meas(interference={"insert": {"state": "overlapping", "overlap_mm3": 1.9, "t_range": [3.0, 8.0]},
                           "lid": {"state": "unknown", "overlap_mm3": None, "error": "volumes disagree"},
                           "host": {"state": "unknown", "overlap_mm3": None, "error": "volumes disagree"}})
    checks, _ = run(m=m)
    assert failed(checks) == ["holes", "tip"]
    assert "could not decide the screw against lid" in checks["holes"].message
    assert "could not decide the screw against host" in checks["tip"].message


def test_record_drift_and_uncommon_lengths():
    checks, _ = run(spec(length_mm=8.5))
    assert "the placed solid is 8.00 mm long, the record says 8.5" in checks["length"].message
    checks, _ = run(spec(thread_start_mm=2.5))
    assert checks["length"].status == "fail" and "record says 2.5: recompute the stack" in checks["length"].message
    checks, _ = run(spec(thread_depth_mm=6.0))
    assert checks["length"].status == "warn" and "5.00 mm of thread modelled" in checks["length"].message
    odd = meas(screw={"length_mm": 8.3, "head_h_mm": 3.0, "head_r_mm": 2.75},
               thread={"radius_mm": 1.38, "intervals": [[3.0, 8.3]], "parts": ["insert"]})
    checks, row = run(spec(length_mm=8.3, thread_depth_mm=5.3), odd)
    assert checks["length"].status == "warn" and "not a common stock length" in checks["length"].message
    assert row["stock"] is False
    checks, _ = run(spec(length_mm=8.3, thread_depth_mm=5.3), odd, stock_lengths_mm=(8.3,))
    assert checks["length"].status == "pass"
    assert any(abs(x - 6.35) < 1e-3 for x in DEFAULT_STOCK_MM) and 8.0 in DEFAULT_STOCK_MM


def test_tool_blocked_missing_unstepped_and_swing():
    blocked = dict(meas()["tool"], blocked=[{"part": "gusset", "state": "overlapping", "overlap_mm3": 84.8,
                                             "from_head_mm": 3.0}], clear=False)
    checks, row = run(m=meas(tool=blocked))
    assert failed(checks) == ["tool"] and checks["tool"].parts == ["m3", "gusset"]
    assert "hits gusset 3.00 mm from the head" in checks["tool"].message and "at step 4" in checks["tool"].message
    assert row["tool_clear"] is False
    checks, _ = run(m=meas(tool={"tool": "", "error": "no tool declared for m3"}))
    assert failed(checks) == ["tool"]
    checks, _ = run(m=meas(tool=dict(meas()["tool"], step=None, no_step=True)))
    assert checks["tool"].status == "warn" and "no assembly step installs m3" in checks["tool"].message
    swing = dict(meas()["tool"], swing={"free_arc_deg": 30.0, "min_deg": 60.0, "ok": False, "blocked_by": ["rib"]},
                 clear=False)
    checks, _ = run(m=meas(tool=swing))
    assert "free arc of 30°, under 60°" in checks["tool"].message and "rib" in checks["tool"].parts
    checks, _ = run(m=meas(tool=None))
    assert checks["tool"].status == "warn"


def test_countersunk_head_uses_contact_not_the_annulus():
    flat = spec(head="flat")
    checks, _ = run(flat, meas(seat_contact={"state": "touching", "gap_mm": 0.0}, annulus={"radius_mm": 2, "lines": []}))
    assert checks["seat"].status == "pass"
    checks, _ = run(flat, meas(seat_contact={"state": "apart", "gap_mm": 0.4}))
    assert "0.400 mm off lid" in checks["seat"].message
    checks, _ = run(flat, meas(screw=None, seat_contact=None))
    assert checks["seat"].status == "warn"


def test_spec_validation_and_coercion_from_a_geometry_record():
    with pytest.raises(ValueError):
        spec(stack=["plate", "lid"])
    with pytest.raises(ValueError):
        spec(stack=["lid", "insert"])
    with pytest.raises(ValueError):
        spec(head="pan")
    with pytest.raises(ValueError):
        FastenerOptions(lines=2)
    rec = {"key": "m3", "clamps": "lid", "into": "insert", "tool": "hex", "length_mm": 8, "count": 2,
           "instances": [{"key": "s#0", "origin": [0, 0, 1], "direction": [0, 0, -2], "sha256": "a"},
                         {"key": "s#1", "origin": [5, 0, 1], "direction": [0, 0, -1], "sha256": "b"}]}
    s = FastenerSpec.coerce(rec, "s")
    assert s.axes[0] == ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0)) and s.instances == ["s#0", "s#1"]
    assert s.instance_key(1) == "s#1" and s.pitch is None
    axis_only = FastenerSpec.coerce({**rec, "instances": [{k: v for k, v in i.items() if k not in ("key", "sha256")}
                                                          for i in rec["instances"]]}, "s")
    assert axis_only.instances == [] and axis_only.instance_key(1) == "s#1"
    assert spec().pitch == 0.5


def test_fasteners_from_a_record_with_per_key_and_per_name_options_and_tools():
    geo = {"fasteners": {"s": {"key": "m3", "clamps": "lid", "into": "nut", "length_mm": 10, "diameter_mm": 3,
                               "instances": [{"key": "s", "origin": [0, 0, 0], "direction": [0, 0, -1]}]}}}
    extra = {"fasteners": {"m3": {"head_d_mm": 5.5, "stack": ["lid", "plate"]}, "s": {"tip_clearance_mm": 0.2}},
             "tools": {"hex": {"envelope_d": 6, "length": 40}}}
    specs = fasteners_from_build(geo, extra=extra)
    assert specs["s"].stack == ["lid", "plate"] and specs["s"].head_d_mm == 5.5 and specs["s"].tip_clearance_mm == 0.2
    assert tools_from(extra=extra) == {"hex": {"envelope_d": 6, "length": 40}}


def test_install_step_and_parts_present_at_it():
    steps = [{"order": 1, "fit": "base"}, {"order": 2, "fit": "lid", "onto": "base", "fasteners": ["m3x8_shcs"] * 2},
             {"order": 3, "fit": "cover", "onto": "lid"}, {"order": 4, "fit": "bracket", "fasteners": ["other"]}]
    s = spec(name="lid_screws", key="m3x8_shcs", axes=[((0, 0, 0), (0, 0, -1)), ((5, 0, 0), (0, 0, -1))])
    other = spec(name="other", key="m4", clamps="bracket", into="base")
    assert install_step(s, steps)["order"] == 2 and install_step(other, steps)["order"] == 4
    assert install_step(spec(name="loose", key="nope"), steps) is None
    names = ["base", "lid", "cover", "bracket", "spare", "lid_screws#0", "lid_screws#1", "other"]
    kinds = {"lid_screws#0": "fastener", "lid_screws#1": "fastener", "other": "fastener"}
    specs = {"lid_screws": s, "other": other}
    assert present_at(install_step(s, steps), steps, names, specs, kinds) == ["base", "lid", "spare", "lid_screws#0",
                                                                               "lid_screws#1"]
    assert present_at(None, steps, names, specs, kinds) == names


def test_tool_envelope_forms():
    assert tool_envelope({"envelope_d": 6, "length": 60}) == {"segments": [{"d": 6.0, "length": 60.0}],
                                                              "start": "head", "offset_mm": 0.0, "swing": None}
    env = tool_envelope({"segments": [{"d": 3, "length": 25}, {"d": 28, "length": 100}], "start": "seat",
                         "swing": {"radius": 50, "at": 10}})
    assert env["start"] == "seat" and env["swing"]["min_deg"] == 60.0 and len(env["segments"]) == 2
    for bad in ({"length": 60}, {"envelope_d": 0, "length": 1}, {"envelope_d": 6, "length": 6, "start": "tip"}, 3):
        with pytest.raises(ValueError):
            tool_envelope(bad)


def test_markdown_table_and_a_gate_with_nothing_placed():
    _, row = run()
    md = table_markdown({"table": [row]})
    assert md.splitlines()[0].startswith("| Fastener | Clamps → into | Seat |")
    assert "| m3 | lid → insert | Z 10.00 | Z 7.00 | 3.00 | 5.00 (10 thr) | 1.50 | 8.00 | 4.50–8.50 |" in md
    from cadagent.gates import Assembly
    v = fastener_gate(Assembly(), {"m3": {"clamps": "lid", "into": "insert", "axes": []}})
    assert v["pass"] is False and v["findings"][0]["id"] == "fastener:m3:declaration"
    assert "no axes" in v["findings"][0]["message"] and "'lid' is not a part" in v["findings"][0]["message"]


# ----------------------------------------------------------------------------- geometry (cadquery)

def _cq():
    return pytest.importorskip("cadquery")


def _box(cq, x0, y0, z0, x1, y1, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _cyl(cq, r, z0, z1, x=0.0, y=0.0):
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(x, y, z0))


def insert_rig(screw_length=20.0, *, gusset=None, solid=True, lid_hole=3.4, seat_z=23.5, steps=True, tool=None,
               lift=0.0, post=False):
    """``blind_insert_stack``'s recessed-lid case as solids: a base 0..7.3 with a Ø4 pilot to Z 2.3, an M3 insert
    (Ø4 x 4.3, bore Ø2.5) with its top at 7.3, a column lid 7.3..23.5 with a Ø3.4 hole; the M3 socket head seats
    at 23.5. ``gusset``: the Z of a bar over the head (fitted at step 3, after the screw, unless ``steps`` says
    otherwise). ``post``: an upright beside the screw, in no step, inside an L key's swing."""
    cq = _cq()
    from cadagent import dossier
    from cadagent.fasteners import insert_envelope, socket_head_envelope
    with dossier.use_registry() as reg:
        reg.add_part("base", _box(cq, -10, -10, 0, 10, 10, 7.3).cut(_cyl(cq, 2.0, 2.3, 7.3)), grounded=True)
        reg.add_part("insert", insert_envelope(4.0, 2.5, 4.3), place=(0, 0, 7.3))
        lid = _box(cq, -6, -6, 7.3 + lift, 6, 6, seat_z + lift).cut(_cyl(cq, lid_hole / 2, 7.3 + lift, seat_z + lift))
        reg.add_part("lid", lid)
        if gusset is not None:
            reg.add_part("gusset", _box(cq, -2, -8, gusset, 9, 8, gusset + 2).fuse(
                _box(cq, 5, -8, seat_z, 9, 8, gusset)))
        if post:
            reg.add_part("post", _box(cq, 12, -2, 23.5, 16, 2, 40))
        reg.fastener("m3_shcs", clamps="lid", into="insert", name="screw", at=[dossier.Axis((0, 0, seat_z + lift),
                                                                                           (0, 0, -1))],
                     tool=tool if tool is not None else "hex 2.5", length_mm=screw_length, diameter_mm=3.0,
                     thread_start_mm=seat_z - 7.3, thread_depth_mm=4.3, min_engagement_mm=1.5,
                     shape=socket_head_envelope(3.0, screw_length, 5.5, 3.0) if solid else None)
        if steps:
            reg.assembly.step(1, "base")
            reg.assembly.step(2, "insert", "base")
            order = 3
            if gusset is not None and steps == "gusset-first":
                reg.assembly.step(order, "gusset", "base")
                order += 1
            reg.assembly.step(order, "lid", "base", fasteners=["screw"])
            if gusset is not None and steps != "gusset-first":
                reg.assembly.step(order + 1, "gusset", "base")
        return reg.build({}, write=False)


TOOLS = {"tools": {"hex 2.5": {"envelope_d": 6.0, "length": 60.0}}}


def gate(result, extra=None, **kw):
    from cadagent.gates.fasteners import fastener_gate_from_build
    return fastener_gate_from_build(result, extra={**TOOLS, **(extra or {})}, **kw)


def by_id(v):
    return {c["id"]: c for c in v["checks"]}


def test_blind_insert_stack_numbers_come_back_from_the_solids():
    """test_fasteners' recessed lid: seat 23.5, M3 x 20, insert top 7.3 x 4.3, hole bottom 2.3 -> engagement 3.8,
    tip clearance 1.2 (blind_insert_stack); the gate measures the same from the model."""
    from cadagent.fasteners import blind_insert_stack
    want = blind_insert_stack(head_seat=23.5, screw_length=20, insert_top=7.3, insert_length=4.3, hole_bottom=2.3)
    v = gate(insert_rig())
    assert v["pass"] is True and v["findings"] == [], v["findings"]
    (row,) = v["table"]
    assert row["engagement_mm"] == pytest.approx(want["engagement_mm"], abs=1e-4)
    assert row["tip_clearance_mm"] == pytest.approx(want["tip_clearance_mm"], abs=1e-4)
    assert row["grip_mm"] == pytest.approx(16.2, abs=1e-4) and row["thread_start_mm"] == pytest.approx(16.2, abs=1e-4)
    assert row["fits_mm"] == pytest.approx([17.7, 20.7], abs=1e-4) and row["step"] == 3


def test_blind_insert_stack_bottomed_and_short_screws_fail_in_geometry():
    v = gate(insert_rig(25.0))
    f = by_id(v)
    assert f["fastener:screw:tip"]["status"] == "fail" and "base" in f["fastener:screw:tip"]["parts"]
    assert "runs 2.30 mm into base (t 21.20..23.50)" in f["fastener:screw:tip"]["message"]   # and out of its bottom
    v = gate(insert_rig(10.0))
    msg = by_id(v)["fastener:screw:engagement"]["message"]
    assert v["pass"] is False and "stops 6.20 mm short of the thread in insert" in msg


def test_axis_only_fastener_is_measured_with_a_default_head():
    v = gate(insert_rig(solid=False))
    assert v["pass"] is True, v["findings"]
    assert v["checks"][0]["evidence"]["head"]["source"] == "default 1.6 d x 1.0 d"
    v = gate(insert_rig(17.0, solid=False))
    assert by_id(v)["fastener:screw:engagement"]["status"] == "fail"


def test_driver_blocked_by_a_gusset_at_the_install_step_only():
    v = gate(insert_rig(gusset=30.0, steps="gusset-first"))
    tool = by_id(v)["fastener:screw:tool"]
    assert tool["status"] == "fail" and tool["parts"] == ["screw", "gusset"]
    (blk,) = tool["evidence"]["blocked"]
    assert blk["from_head_mm"] == pytest.approx(3.5, abs=1e-4)     # head top 26.5, bar from 30
    v = gate(insert_rig(gusset=30.0))                                # fitted after the screw: not in the way then
    assert by_id(v)["fastener:screw:tool"]["status"] == "pass", by_id(v)["fastener:screw:tool"]
    v = gate(insert_rig(gusset=30.0, steps=False))                   # no steps: the finished assembly
    assert by_id(v)["fastener:screw:tool"]["status"] == "fail"


def test_a_missing_tool_or_envelope_fails_and_an_unstepped_fastener_warns():
    v = gate(insert_rig(tool=""))
    assert "no tool declared" in by_id(v)["fastener:screw:tool"]["message"]
    v = gate(insert_rig(tool="pliers"))
    assert "has no envelope" in by_id(v)["fastener:screw:tool"]["message"]
    r = insert_rig()
    r.steps = [s for s in r.steps if s.fit != "lid"]
    v = gate(r)
    assert by_id(v)["fastener:screw:tool"]["status"] == "warn" and v["pass"] is True


def test_l_key_swing_reports_its_free_arc():
    extra = {"tools": {"hex 2.5": {"envelope_d": 3.0, "length": 6.0,
                                   "swing": {"radius": 40.0, "at": 4.0, "thickness": 3.0, "min_deg": 360}}}}
    r = insert_rig(post=True)
    v = gate(r, extra)
    tool = by_id(v)["fastener:screw:tool"]
    sw = tool["evidence"]["swing"]
    assert sw["ok"] is False and sw["blocked_by"] == ["post"] and 0 < sw["free_arc_deg"] < 360, tool
    assert tool["evidence"]["blocked"] == [] and tool["parts"] == ["screw", "post"]
    extra["tools"]["hex 2.5"]["swing"]["min_deg"] = sw["free_arc_deg"]
    assert by_id(gate(r, extra))["fastener:screw:tool"]["status"] == "pass"


def test_undersized_lid_hole_and_hovering_lid_fail():
    v = gate(insert_rig(lid_hole=2.0))
    holes = by_id(v)["fastener:screw:holes"]
    assert holes["status"] == "fail" and "Ø2.00, under Ø3.10" in holes["message"]
    assert "the screw overlaps lid" in holes["message"]
    v = gate(insert_rig(lift=0.5))
    stack = by_id(v)["fastener:screw:stack"]
    assert stack["status"] == "fail" and "nothing under lid" in stack["message"]


def nut_rig(*, gap=0.0, hole_b=3.4, length=16.0, x_axis=False):
    """Two plates and a nut (Ø5.5 x 2.4, minor bore Ø2.5) on an M3 x 16, optionally laid along +X."""
    cq = _cq()
    from cadagent import dossier
    from cadagent.fasteners import socket_head_envelope
    a = _box(cq, -8, -8, 6, 8, 8, 10).cut(_cyl(cq, 1.7, 6, 10))
    b = _box(cq, -8, -8, 2 - gap, 8, 8, 6 - gap)
    if hole_b:
        b = b.cut(_cyl(cq, hole_b / 2, 2 - gap, 6 - gap))
    nut = _cyl(cq, 2.75, -0.4 - gap, 2 - gap).cut(_cyl(cq, 1.25, -0.4 - gap, 2 - gap))
    loc = cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 90) if x_axis else None
    shapes = {"plate_a": a, "plate_b": b, "nut": nut}
    if loc is not None:
        shapes = {k: s.moved(loc) for k, s in shapes.items()}
    origin, direction = ((10, 0, 0), (-1, 0, 0)) if x_axis else ((0, 0, 10), (0, 0, -1))
    with dossier.use_registry() as reg:
        for k, s in shapes.items():
            reg.add_part(k, s, grounded=k == "plate_a")
        reg.fastener("m3_shcs", clamps="plate_a", into="nut", name="bolt", at=[dossier.Axis(origin, direction)],
                     tool="hex 2.5", length_mm=length, diameter_mm=3.0, thread_start_mm=8.0, thread_depth_mm=2.4,
                     min_engagement_mm=2.0, shape=socket_head_envelope(3.0, length, 5.5, 3.0))
        return reg.build({}, write=False)


NUT = {"fasteners": {"bolt": {"stack": ["plate_a", "plate_b"], "tip_clearance_mm": 0.0}}}


@pytest.mark.parametrize("x_axis", [False, True])
def test_bolt_through_two_plates_into_a_nut_passes_along_any_axis(x_axis):
    v = gate(nut_rig(length=10.0, x_axis=x_axis), NUT)
    assert v["pass"] is True and v["findings"] == [], v["findings"]
    (row,) = v["table"]
    assert row["grip_mm"] == pytest.approx(8.0, abs=1e-4) and row["engagement_mm"] == pytest.approx(2.0, abs=1e-4)
    assert row["tip_clearance_mm"] is None and row["fits_mm"][1] is None       # nothing past the nut


def test_bolt_stack_with_a_gap_or_no_hole_in_the_second_plate_fails():
    v = gate(nut_rig(length=10.0, gap=0.3), NUT)
    stack = by_id(v)["fastener:bolt:stack"]
    assert stack["status"] == "fail" and "0.300 mm gap" in stack["message"]
    v = gate(nut_rig(length=10.0, hole_b=None), NUT)
    holes = by_id(v)["fastener:bolt:holes"]
    assert holes["status"] == "fail" and "plate_b" in holes["parts"]


def test_head_in_a_pocket_too_narrow_and_over_an_edge():
    cq = _cq()
    from cadagent import dossier
    from cadagent.fasteners import insert_envelope, socket_head_envelope

    def rig(pocket_d=None, x=0.0):
        with dossier.use_registry() as reg:
            base = _box(cq, -10, -10, 0, 10, 10, 8).cut(_cyl(cq, 2.0, 1.0, 8, x=x))
            reg.add_part("base", base, grounded=True)
            reg.add_part("insert", insert_envelope(4.0, 2.5, 5.0), place=(x, 0, 8))
            lid = _box(cq, -10, -10, 8, 10, 10, 14).cut(_cyl(cq, 1.7, 8, 14, x=x))
            if pocket_d:
                lid = lid.cut(_cyl(cq, pocket_d / 2, 11, 14, x=x))
            reg.add_part("lid", lid)
            reg.fastener("m3_shcs", clamps="lid", into="insert", name="screw",
                         at=[dossier.Axis((x, 0, 11 if pocket_d else 14), (0, 0, -1))], tool="hex 2.5",
                         length_mm=6.0 if pocket_d else 10.0, diameter_mm=3.0, min_engagement_mm=1.5,
                         shape=socket_head_envelope(3.0, 6.0 if pocket_d else 10.0, 5.5, 3.0))
            return reg.build({}, write=False)

    v = gate(rig(pocket_d=5.0))
    seat = by_id(v)["fastener:screw:seat"]
    assert seat["status"] == "fail" and "the head cuts into lid" in seat["message"]
    assert by_id(v)["fastener:screw:holes"]["status"] == "pass"
    v = gate(rig(pocket_d=6.5))
    assert by_id(v)["fastener:screw:seat"]["status"] == "pass", by_id(v)["fastener:screw:seat"]
    v = gate(rig(x=9.0))                                              # the head hangs 1.75 mm off the lid's edge
    seat = by_id(v)["fastener:screw:seat"]
    assert seat["status"] == "fail" and "nothing under the head" in seat["message"]


def test_gate_writes_the_verdict_and_the_markdown_table(tmp_path):
    v = gate(insert_rig(), out=tmp_path / "gates" / "fasteners.json")
    data = json.loads((tmp_path / "gates" / "fasteners.json").read_text())
    assert data["pass"] is True and data["table"] == v["table"] and data["physical_fit_verified"] is False
    md = (tmp_path / "gates" / "fasteners.md").read_text()
    assert "| screw | lid → insert | Z 23.50 | Z 7.30 |" in md
    assert math.isclose(data["limits"]["tip_clearance_mm"], 0.5)
