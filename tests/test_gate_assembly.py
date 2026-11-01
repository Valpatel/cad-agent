"""Assembly-sequence access gate (T9): the kernel-free core on a world of boxes, then real geometry.

The core tests run ``run_sequence`` on ``BoxWorld``, whose parts are axis-aligned boxes with exact box relations
(overlap volume, gap), so the rules (coverage, references, fastener order, the insertion sweep and its witness,
tool reach, service removal) run in core CI without OCP. The geometry tests run the whole gate on the gate bench
and on small builds through the dossier registry.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

from cadagent.review.gates.assembly import (AccessOptions, SequenceWorld, direction_vector, normalise_steps,
                                            run_sequence, steps_markdown, sweep_pair)
from cadagent.review.gates.fasteners import FastenerSpec
from cadagent.review.gates.relations import Relation, Tolerances
from cadagent.review.gates.verdict import verdict

# ----------------------------------------------------------------------------- no CAD kernel needed


class BoxWorld(SequenceWorld):
    """Parts are boxes ``(x0, y0, z0, x1, y1, z1)``; relations are exact for boxes. ``tools`` maps a fastener
    instance to the tool sweep result to return (default: clear)."""

    def __init__(self, boxes, kinds=None, tools=None, tol=Tolerances()):
        self.boxes, self.kinds, self.tools, self.tol = dict(boxes), dict(kinds or {}), dict(tools or {}), tol
        self.names = list(self.boxes)
        self.queries = 0
        self.tool_calls = []

    def kind(self, key):
        return self.kinds.get(key, "part")

    def box(self, key):
        return self.boxes[key]

    def relate_at(self, key, shift, other):
        self.queries += 1
        a = [c + shift[i % 3] for i, c in enumerate(self.boxes[key])]
        b = self.boxes[other]
        span = [min(a[i + 3], b[i + 3]) - max(a[i], b[i]) for i in range(3)]
        if all(x > 0 for x in span):
            vol = span[0] * span[1] * span[2]
            if vol > self.tol.overlap_mm3:
                lo = [max(a[i], b[i]) for i in range(3)]
                return Relation(key, other, "overlapping", gap_mm=0.0, overlap_mm3=vol,
                                witness={"overlap_centroid": [lo[i] + span[i] / 2 for i in range(3)]})
        gap = math.sqrt(sum(max(0.0, -x) ** 2 for x in span))
        return Relation(key, other, "touching" if gap <= self.tol.touch_mm else "apart", gap_mm=gap,
                        witness={"point_a": [0, 0, 0], "point_b": [0, 0, 0]})

    def tool(self, spec, i, tool_name, decl, present, step, later=()):
        inst = spec.instance_key(i)
        self.tool_calls.append((inst, tool_name, list(present), step["order"]))
        res = {"tool": tool_name, "step": step["order"], "present": list(present), "blocked": [], "clear": True}
        res.update(self.tools.get(inst, {}))
        return res


# a base plate, a block on it, a card standing on the base beside the block (touching its +X face), and a
# cover over both (Z 25..30); the card must go in before the cover
BOXES = {"base": (0, 0, 0, 100, 100, 5), "block": (10, 10, 5, 30, 30, 25), "card": (30, 10, 5, 32, 30, 20),
         "cover": (0, 0, 25, 40, 40, 30)}
CLEAN = [{"order": 1, "fit": "base", "direction": "-Z"},
         {"order": 2, "fit": "block", "onto": "base", "direction": "-Z"},
         {"order": 3, "fit": "card", "onto": "base", "direction": "-Z"},
         {"order": 4, "fit": "cover", "onto": ["block"], "direction": "-Z"}]


def steps(*changes, base=CLEAN):
    out = [dict(s) for s in base]
    for order, kw in changes:
        for s in out:
            if s["order"] == order:
                s.update(kw)
    return out


def run(boxes=None, step_list=None, **kw):
    world = kw.pop("world", None) or BoxWorld(boxes or BOXES, kw.pop("kinds", None), kw.pop("tools_result", None))
    res = run_sequence(world, CLEAN if step_list is None else step_list, **kw)
    return {c.id: c for c in res["checks"]}, res, world


def failed(checks):
    return sorted(k for k, c in checks.items() if c.status == "fail")


def findings(checks):
    return sorted(k for k, c in checks.items() if c.status != "pass")


def test_direction_forms_and_errors():
    assert direction_vector("-Z") == (0.0, 0.0, -1.0) and direction_vector("+x") == (1.0, 0.0, 0.0)
    assert direction_vector((0, 3, 4)) == pytest.approx((0, 0.6, 0.8))
    assert direction_vector("") is None and direction_vector(None) is None
    for bad in ("down", "Z", (0, 0, 0), (1, 2)):
        with pytest.raises(ValueError):
            direction_vector(bad)


def test_steps_are_normalised_from_mappings_and_objects():
    class Step:
        order, fit, onto, direction, where = 2, "lid", "base", "-Z", "b.py:9"
    out = normalise_steps([Step(), {"order": 1, "fit": "base", "fasteners": ["m3", "m3"]}])
    assert [s["order"] for s in out] == [1, 2]
    assert out[0]["onto"] == [] and out[0]["fasteners"] == ["m3", "m3"]
    assert out[1]["onto"] == ["base"] and out[1]["declared_at"] == "b.py:9"


def test_clean_sequence_passes_with_no_finding_and_reports_sliding_contact():
    checks, res, _ = run()
    assert findings(checks) == [], [checks[k].message for k in findings(checks)]
    card = checks["step:3:insert"]
    assert "block" in card.evidence["touching"] and "base" in card.evidence["touching"]
    row = {r["order"]: r for r in res["steps"]}[3]
    assert row["present"] == 2 and row["blocked"] == []
    data = verdict("assembly", res["checks"], assumptions=["boxes"], extra={"steps": res["steps"]})
    assert data["pass"] and "| 3 | card | base | -Z | 2 |" in steps_markdown(data)


def test_cover_fitted_before_the_card_blocks_it_with_the_first_contact_bisected():
    swapped = steps((3, {"fit": "cover", "onto": ["block"]}), (4, {"fit": "card", "onto": ["base"]}))
    checks, res, _ = run(step_list=swapped)
    assert failed(checks) == ["step:4:insert"]
    c = checks["step:4:insert"]
    assert set(c.parts) == {"card", "cover"}
    (hit,) = [r for r in c.evidence["near"]["card"] if r["state"] == "blocked"]
    clear, first = hit["first_contact_mm"]
    # the card's bottom (Z 5) meets the cover's top (Z 30) 25 mm above its seat
    assert clear > first and first == pytest.approx(25.0, abs=2e-3) and clear == pytest.approx(25.0, abs=2e-3)
    assert hit["overlap_centroid"][2] == pytest.approx(30.0, abs=1e-2)
    assert "card meets cover 25.00 mm before its seat" in c.message
    (row,) = [r for r in res["steps"] if r["order"] == 4]
    assert row["blocked"][0]["instance"] == "card" and row["blocked"][0]["part"] == "cover"


def test_a_part_that_overlaps_a_present_part_at_its_seat_fails_unless_intended():
    boxes = dict(BOXES, card=(29, 10, 5, 31, 30, 20))          # 1 mm into the block
    checks, _, _ = run(boxes)
    assert failed(checks) == ["step:3:insert"] and "overlaps block at its seat" in checks["step:3:insert"].message
    checks, res, _ = run(boxes, intended_overlaps=[{"parts": ["card", "block"], "reason": "press fit"}])
    assert findings(checks) == []
    assert res["exclusions"] == [{"parts": ["card", "block"], "reason": "press fit", "step": 3}]


def test_a_side_entry_is_checked_along_its_own_direction():
    # the card slid in along +X under the cover from the -X side passes through the block
    checks, _, _ = run(step_list=steps((3, {"order": 5, "direction": "+X"})))
    assert failed(checks) == ["step:5:insert"]
    # from +X (moving -X) nothing is in the way, and it ends touching the block
    checks, _, _ = run(step_list=steps((3, {"order": 5, "direction": "-X"})))
    assert findings(checks) == []


def test_conservative_advancement_takes_gap_sized_steps_far_from_contact():
    world = BoxWorld({"part": (0, 0, 0, 10, 10, 10), "wall": (0, 0, -300, 10, 10, -200)})
    # the wall is 200 mm below and behind the travel: nothing on the line is closer than the boxes say
    r = sweep_pair(world, "part", (0.0, 0.0, -1.0), "wall")
    assert r["state"] == "clear" and r["samples"] == 0
    world = BoxWorld({"part": (0, 0, 0, 10, 10, 10), "shelf": (-20, -20, 100, 30, 30, 101),
                      "rail": (10, 0, -50, 12, 10, 200)})
    r = sweep_pair(world, "part", (0.0, 0.0, -1.0), "shelf")
    # its bottom (Z 0) meets the shelf's top (Z 101) on the way down
    assert r["state"] == "blocked" and r["first_contact_mm"][1] == pytest.approx(101.0, abs=2e-3)
    assert r["samples"] < 25          # the box gap carries it most of the way; only the bisection samples
    r = sweep_pair(world, "part", (0.0, 0.0, -1.0), "rail")
    assert r["state"] == "clear" and r["touching"] and r["samples"] >= 200   # sliding along: sampled at 1 mm


def test_clearance_is_the_smallest_gap_measured_and_a_bound_that_holds_between_samples():
    # coming in diagonally (down and to +X) past a block below and behind: the true closest approach is
    # 2.5 * sqrt(2) = 3.536 mm (box world: exact = box distance)
    world = BoxWorld({"part": (0, 0, 0, 10, 10, 10), "block": (-30, 0, 5, -20, 10, 15)})
    true_gap = 2.5 * math.sqrt(2)
    r = sweep_pair(world, "part", direction_vector((1, 0, -1)), "block")
    # the closest approach lies between the bound and the smallest gap measured (the first sample and the seat
    # are measured; in between the box gap carries it)
    assert r["state"] == "clear" and 0 < r["gap_lower_bound_mm"] <= true_gap <= r["min_gap_mm"]
    r = sweep_pair(world, "part", direction_vector((1, 0, -1)), "block", options=AccessOptions(max_step_mm=5))
    assert true_gap - 1e-6 <= r["min_gap_mm"] < true_gap + 0.5 and r["gap_lower_bound_mm"] <= true_gap
    # a start offset no longer reads as the clearance
    near = dict(BOXES, card=(33, 10, 5, 35, 30, 20))                   # 3 mm off the block
    checks, res, _ = run(near)
    row = {r["order"]: r for r in res["steps"]}[3]
    # its swept box stays 3 mm from the block's, so nothing is measured and the bound is that box gap
    assert row["min_clearance_mm"] is None and row["clearance_at_least_mm"] == pytest.approx(3.0)
    data = verdict("assembly", res["checks"], assumptions=["boxes"], extra={"steps": res["steps"]})
    assert "| 3 | card | base | -Z | 2 | ≥ 3.00 |" in steps_markdown(data)


def test_sampling_limits_are_reported_not_hidden():
    world = BoxWorld({"part": (0, 0, 0, 10, 10, 10), "rail": (10, 0, -50, 12, 10, 200)})
    r = sweep_pair(world, "part", (0.0, 0.0, -1.0), "rail", options=AccessOptions(max_samples=20))
    assert r["state"] == "unchecked" and "max_samples" in r["error"]
    with pytest.raises(ValueError):
        AccessOptions(max_step_mm=0)
    with pytest.raises(ValueError):
        AccessOptions(missing_direction="ignore")


def test_every_part_in_exactly_one_step():
    missing = [s for s in CLEAN if s["fit"] != "card"]
    checks, _, _ = run(step_list=missing)
    assert failed(checks) == ["cover:card"] and "no step fits card" in checks["cover:card"].message
    doubled = CLEAN + [{"order": 5, "fit": "card", "onto": "base", "direction": "-Z"}]
    checks, _, _ = run(step_list=doubled)
    assert "cover:card" in failed(checks) and "card is fitted at steps 3, 5" in checks["cover:card"].message
    assert checks["cover:base"].status == "pass"


def test_instances_are_covered_by_their_part_name_or_one_by_one():
    boxes = dict(BOXES, **{"peg#0": (50, 50, 5, 52, 52, 15), "peg#1": (60, 50, 5, 62, 52, 15)})
    checks, res, _ = run(boxes, CLEAN + [{"order": 5, "fit": "peg", "onto": "base", "direction": "-Z"}])
    assert findings(checks) == [] and checks["step:5:insert"].evidence["instances"] == ["peg#0", "peg#1"]
    checks, _, _ = run(boxes, CLEAN + [{"order": 5, "fit": "peg#0", "onto": "base", "direction": "-Z"}])
    assert failed(checks) == ["cover:peg"] and "no step fits peg#1" in checks["cover:peg"].message


def test_steps_and_references_must_resolve_and_onto_must_come_earlier():
    checks, _, _ = run(step_list=[])
    assert failed(checks) == ["steps"] and "no assembly steps" in checks["steps"].message
    checks, _, _ = run(step_list=steps((4, {"order": 3})))
    assert failed(checks) == ["steps"] and "share order 3" in checks["steps"].message
    checks, _, _ = run(step_list=steps((2, {"onto": ["card"]})))
    assert "step:2:refs" in failed(checks) and "onto 'card' is fitted at step 3, not before step 2" in \
        checks["step:2:refs"].message
    checks, _, _ = run(step_list=steps((2, {"onto": ["nope", "block"]}), (3, {"direction": "sideways"})))
    msg2, msg3 = checks["step:2:refs"].message, checks["step:3:refs"].message
    assert "onto 'nope' is not a part" in msg2 and "onto 'block' is the part this step fits" in msg2
    assert "direction 'sideways'" in msg3 and "step:3:insert" not in checks      # no sweep without a direction
    checks, _, _ = run(step_list=CLEAN + [{"order": 5, "fit": "ghost", "direction": "-Z"}])
    assert "fit 'ghost' is not a part" in checks["step:5:refs"].message


def test_a_step_without_a_direction_warns_or_fails_as_configured():
    checks, res, _ = run(step_list=steps((3, {"direction": ""})))
    assert checks["step:3:insert"].status == "warn" and failed(checks) == []
    assert res["not_checked"] == [{"step": 3, "what": "insertion", "reason": "no direction"}]
    checks, _, _ = run(step_list=steps((3, {"direction": ""})), options=AccessOptions(missing_direction="fail"))
    assert failed(checks) == ["step:3:insert"]


# fasteners: two screws through the cover into the block, one catalogue key
SCREW = dict(key="m3", clamps="cover", into="block", tool="hex 2.5", diameter_mm=3.0, length_mm=8.0)


def screws(n=2, **kw):
    out = {}
    for j in range(n):
        name = kw.pop("name", None) or f"s{j}"
        out[name] = FastenerSpec(name=name, axes=[((15 + 5 * j, 15, 30), (0, 0, -1))], **{**SCREW, **kw})
    return out


def test_fasteners_by_name_go_in_after_what_they_hold_and_their_tool_is_swept():
    st = steps((4, {"fasteners": ["s0", "s1"], "tool": "hex 2.5"}))
    checks, res, world = run(step_list=st, fasteners=screws(), tools={"hex 2.5": {"envelope_d": 6, "length": 60}})
    assert findings(checks) == [], [checks[k].message for k in findings(checks)]
    assert checks["cover:s0"].evidence == {"step": 4} and checks["step:4:fasteners"].status == "pass"
    assert {c[0] for c in world.tool_calls} == {"s0", "s1"}
    inst, tool, present, order = world.tool_calls[0]
    assert tool == "hex 2.5" and order == 4 and set(present) == {"base", "block", "card", "cover"}
    assert {r["order"]: r for r in res["steps"]}[4]["installs"] == ["s0", "s1"]


def test_a_screw_driven_before_its_clamped_part_is_fitted_fails_the_order():
    st = steps((3, {"fasteners": ["s0"]}), (4, {"fasteners": ["s1"]}))
    checks, _, _ = run(step_list=st, fasteners=screws(), tools={"hex 2.5": {"envelope_d": 6, "length": 60}})
    assert failed(checks) == ["step:3:fasteners"]
    c = checks["step:3:fasteners"]
    assert "s0 clamps cover, fitted at step 4" in c.message and "s0" in c.parts and "cover" in c.parts


def test_fasteners_by_catalogue_key_are_counted_and_none_is_doubled_or_lost():
    tools = {"hex 2.5": {"envelope_d": 6, "length": 60}}
    checks, _, _ = run(step_list=steps((4, {"fasteners": ["m3"]})), fasteners=screws(), tools=tools)
    assert findings(checks) == []
    checks, _, _ = run(step_list=steps((4, {"fasteners": ["m3", "m3"]})), fasteners=screws(), tools=tools)
    assert findings(checks) == []                       # listed once per screw: two listed, two go in
    checks, _, _ = run(step_list=steps((4, {"fasteners": ["m3"] * 3})), fasteners=screws(), tools=tools)
    assert failed(checks) == ["step:4:refs"] and "listed 3 times but 2 go in here" in checks["step:4:refs"].message
    # the key listed again at a later step installs nothing there: doubled
    st = steps((4, {"fasteners": ["m3"]})) + [{"order": 5, "fit": "lid2", "onto": "cover", "direction": "-Z",
                                               "fasteners": ["m3"]}]
    checks, _, _ = run(dict(BOXES, lid2=(0, 0, 30, 40, 40, 32)), st, fasteners=screws(), tools=tools)
    assert "installs nothing here: every m3 goes in at step 4" in checks["step:5:refs"].message
    # named in two steps; unknown entry; installed by no step
    st = steps((4, {"fasteners": ["s0", "s1", "s0x"]}), (3, {"fasteners": ["s0"]}))
    checks, _, _ = run(step_list=st, fasteners=screws(), tools=tools)
    assert "listed by name at steps 3, 4" in checks["cover:s0"].message
    assert "'s0x' names no declared fastener" in checks["step:4:refs"].message
    checks, _, _ = run(fasteners=screws(), tools=tools)
    assert failed(checks) == ["cover:s0", "cover:s1"] and "no step installs it" in checks["cover:s0"].message
    checks, _, _ = run(step_list=steps((4, {"fasteners": ["s0", "s0", "s1"]})), fasteners=screws(), tools=tools)
    assert failed(checks) == ["step:4:refs"] and "fastener 's0' is listed 2 times" in checks["step:4:refs"].message


def test_a_blocked_tool_fails_at_the_step_and_a_tool_with_nothing_to_drive_warns():
    st = steps((4, {"fasteners": ["s0", "s1"], "tool": "hex 2.5"}))
    blocked = {"s1": {"blocked": [{"part": "card", "state": "overlapping", "overlap_mm3": 4.0, "from_head_mm": 3.0}],
                      "clear": False}}
    checks, _, _ = run(step_list=st, fasteners=screws(), tools_result=blocked)
    assert failed(checks) == ["step:4:tool:s1"]
    assert "envelope hits card" in checks["step:4:tool:s1"].message and "card" in checks["step:4:tool:s1"].parts
    checks, res, _ = run(step_list=steps((2, {"tool": "mallet"})))
    assert checks["step:2:tool"].status == "warn" and failed(checks) == []
    assert {"step": 2, "what": "tool", "reason": "no fastener installed at the step"} in res["not_checked"]
    checks, _, _ = run(step_list=st, fasteners=screws(), tools_result=blocked, options=AccessOptions(tool_access=False))
    assert findings(checks) == []


def test_service_removal_names_the_parts_fitted_later_that_must_come_off_first():
    checks, _, _ = run(service=True)
    assert checks["service:card"].status == "warn" and checks["service:card"].evidence["remove_first"] == ["cover"]
    assert checks["service:cover"].status == "pass"
    checks, _, _ = run(service="card")
    assert [k for k in checks if k.startswith("service:")] == ["service:card"]
    # a part no step fits is not 'fitted later'; one instance can be asked for on its own
    boxes = dict(BOXES, loose=(30, 10, 22, 32, 30, 24), **{"peg#0": (50, 50, 5, 52, 52, 15),
                                                            "peg#1": (60, 50, 5, 62, 52, 15)})
    checks, res, _ = run(boxes, CLEAN + [{"order": 5, "fit": "peg", "onto": "base", "direction": "-Z"}],
                         service=["card", "peg#0"])
    assert checks["service:card"].evidence["remove_first"] == ["cover"]
    assert sorted(k for k in checks if k.startswith("service:")) == ["service:card", "service:peg#0"]
    assert any(n.get("parts") == ["loose"] for n in res["not_checked"])
    st = steps((4, {"fasteners": ["s0", "s1"], "tool": "hex 2.5"}))
    boxes = dict(BOXES, **{"s0": (14, 14, 22, 16, 16, 33), "s1": (19, 14, 22, 21, 16, 33)})
    kinds = {"s0": "fastener", "s1": "fastener"}
    fs = screws()
    for n, sp in fs.items():
        sp.instances = [n]
    checks, _, _ = run(boxes, st, kinds=kinds, fasteners=fs, service=["cover", "block"])
    cover = checks["service:cover"]
    assert cover.status == "pass" and cover.evidence["own_fasteners_first"] == ["s0", "s1"]
    assert checks["service:block"].evidence["remove_first"] == ["cover"]
    assert "service:card" not in checks


def test_tool_access_without_a_head_height_fails_rather_than_sweep_from_the_seat():
    from cadagent.review.gates.fasteners import tool_access, tool_check
    sp = FastenerSpec(name="x", clamps="lid", into="nut", axes=[((0, 0, 10), (0, 0, -1))], tool="hex 2.5")
    res = tool_access({}, sp, 0, "hex 2.5", {"envelope_d": 6, "length": 60}, ["lid"], {"order": 3, "fit": "lid"})
    c = tool_check("step:3:tool:x", "x", sp, res)
    assert c.status == "fail" and "no head height" in c.message


# ----------------------------------------------------------------------------- real geometry

def _cq():
    return pytest.importorskip("cadquery")


def _bench():
    _cq()
    pytest.importorskip("trimesh")
    path = Path(__file__).resolve().parent / "fixtures" / "gate_bench" / "build.py"
    if "gate_bench_build" in sys.modules:
        return sys.modules["gate_bench_build"]
    spec = importlib.util.spec_from_file_location("gate_bench_build", path)
    gb = importlib.util.module_from_spec(spec)
    sys.modules["gate_bench_build"] = gb
    spec.loader.exec_module(gb)
    return gb


def _gate(bench, **kw):
    from cadagent.review.gates.assembly import assembly_from_build
    return assembly_from_build(bench.result, extra=bench.declarations, assembly=bench.assembly, **kw)


def test_bench_clean_passes_and_every_part_and_screw_is_in_exactly_one_step():
    gb = _bench()
    b = gb.build()
    v = _gate(b)
    assert v["pass"] and v["findings"] == [], v["findings"]
    covered = {c["id"][6:] for c in v["checks"] if c["id"].startswith("cover:")}
    parts = set(b.result.geometry["parts"]) | set(b.result.geometry["fasteners"])
    assert covered == parts
    rows = {r["order"]: r for r in v["steps"]}
    pin = [r for r in rows.values() if r["fit"] == "pin"][0]
    assert pin["direction"] == "-Y" and {"arm", "hinge_block"} <= set(pin["touching"])   # slides through both bores
    lid = [r for r in rows.values() if r["fit"] == "lid"][0]
    assert lid["installs"] == ["screw_0", "screw_1", "screw_2", "screw_3"]
    assert all(t["status"] == "pass" for t in lid["tools"])


def test_bench_seed_lid_before_board_blocks_the_board_on_the_lid():
    gb = _bench()
    v = _gate(gb.build("lid_before_board"))
    assert not v["pass"]
    (board,) = [f for f in v["findings"] if f["parts"][0] == "board"]
    assert board["status"] == "fail" and set(board["parts"]) == {"board", "lid"}
    (hit,) = [r for r in board["evidence"]["near"]["board"] if r["part"] == "lid"]
    # the board's bottom (Z 6.4) meets the lid's top (Z 47) 40.6 mm above its seat
    assert hit["first_contact_mm"][1] == pytest.approx(40.6, abs=2e-3)
    assert hit["overlap_centroid"][2] == pytest.approx(47.0, abs=1e-2)
    # the balls, now also after the lid, are blocked the same way; nothing else fails
    assert {f["id"] for f in v["findings"]} == {"step:8:insert", "step:9:insert"}


def test_bench_gusset_seed_blocks_the_hex_key_at_the_screws_step():
    gb = _bench()
    v = _gate(gb.build("gusset_over_screw"))
    failed_ids = {f["id"] for f in v["findings"] if f["status"] == "fail"}
    assert failed_ids == {"step:10:tool:screw_0"}, v["findings"]
    (f,) = [f for f in v["findings"] if f["id"] == "step:10:tool:screw_0"]
    assert "gusset" in f["parts"]


def test_bench_service_check_says_the_lid_comes_off_before_the_board():
    gb = _bench()
    v = _gate(gb.build(), service=["board", "lid"])
    (board,) = [f for f in v["findings"] if f["id"] == "service:board"]
    assert board["status"] == "warn" and board["evidence"]["remove_first"] == ["lid"]
    lid = [c for c in v["checks"] if c["id"] == "service:lid"][0]
    assert lid["status"] == "pass" and lid["evidence"]["own_fasteners_first"] == [f"screw_{i}" for i in range(4)]
    assert v["pass"] and v["limits"]["service"] is True


def test_registry_build_with_a_diagonal_entry_and_the_verdict_files(tmp_path):
    cq = _cq()
    from cadagent.review import dossier
    from cadagent.review.gates import Assembly, PairCache
    from cadagent.review.gates.assembly import assembly_from_build

    def box(x0, y0, z0, x1, y1, z1):
        return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))

    with dossier.use_registry() as reg:
        reg.add_part("tray", box(0, 0, 0, 60, 40, 4).fuse(box(0, 0, 4, 60, 4, 30)).clean(), section="s", grounded=True)
        reg.add_part("roof", box(0, 0, 30, 30, 40, 33), section="s")
        reg.add_part("cart", box(40, 10, 4, 50, 20, 14), section="s")
        reg.assembly.step(1, "tray", direction="-Z")
        reg.assembly.step(2, "roof", "tray", direction="-Z")
        reg.assembly.step(3, "cart", "tray", direction=(1, 0, -1))    # diagonally down and to +X: under the roof
        result = reg.build({}, write=False)
    asm = Assembly.from_build(result)
    cache = PairCache(tmp_path / "cache")
    out = tmp_path / "gates" / "assembly.json"
    v = assembly_from_build(result, assembly=asm, cache=cache, out=out)
    assert not v["pass"]
    (f,) = v["findings"]
    assert f["id"] == "step:3:insert" and set(f["parts"]) == {"cart", "roof"}
    assert json.loads(out.read_text())["gate"] == "assembly"
    assert "| 3 | cart | tray |" in out.with_suffix(".md").read_text()
    # moved against the tray's back wall and dropped straight down, the cart clears the roof's edge (X 30) and
    # slides down the wall
    with dossier.use_registry() as reg:
        reg.add_part("tray", box(0, 0, 0, 60, 40, 4).fuse(box(0, 0, 4, 60, 4, 30)).clean(), section="s", grounded=True)
        reg.add_part("roof", box(0, 0, 30, 30, 40, 33), section="s")
        reg.add_part("cart", box(40, 4, 4, 50, 14, 14), section="s")
        reg.assembly.step(1, "tray", direction="-Z")
        reg.assembly.step(2, "roof", "tray", direction="-Z")
        reg.assembly.step(3, "cart", "tray", direction="-Z")
        result = reg.build({}, write=False)
    v = assembly_from_build(result, cache=cache)
    assert v["pass"] and v["findings"] == []
    cart = {r["order"]: r for r in v["steps"]}[3]
    assert cart["touching"] == ["tray"]
    # an unchanged rerun reads the cache
    again = assembly_from_build(result, cache=cache)
    assert again["world_stats"]["kernel_queries"] == 0 and again["world_stats"]["cache_hits"] > 0
