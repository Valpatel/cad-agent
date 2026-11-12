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
    path = Path(__file__).resolve().parents[1] / "fixtures" / "gate_bench" / "build.py"
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


# Ordered guide playback reuses the insertion sweep, with a finite authored start.
def test_finite_playback_path_excludes_an_obstacle_beyond_its_start_and_keeps_default():
    world = BoxWorld({"moving": (0, 0, 0, 1, 1, 1), "far": (8, 0, 0, 9, 1, 1)})
    assert sweep_pair(world, "moving", (-1, 0, 0), "far")["state"] == "blocked"
    finite = sweep_pair(world, "moving", (-1, 0, 0), "far", travel_mm=3)
    assert finite["state"] == "clear" and finite["travel_mm"] == 3
    assert finite["gap_lower_bound_mm"] == 4


@pytest.mark.parametrize("travel", [-1, float("nan"), float("inf"), True, "3"])
def test_finite_playback_travel_rejects_invalid_distance(travel):
    with pytest.raises(ValueError, match="finite nonnegative"):
        sweep_pair(BoxWorld(BOXES), "card", (0, 0, -1), "cover", travel_mm=travel)


def playback_fixture_data(order=None):
    from cadagent.review.gates.playback import playback_operations
    boxes = {"base": (-10, -10, -2, 10, 10, 0), "blocker": (2, -2, 0, 4, 2, 4),
             "insert": (0, -1, 0, 1, 1, 3)}
    guide = {"steps": [{"id": "stage", "parts": list(boxes),
                         "offsets_mm": {"blocker": [0, 0, 6], "insert": [6, 0, 0]}}]}
    order = {"stage": ["base", "blocker", "insert"]} if order is None else order
    assert len(playback_operations(guide, order)) == 3
    return boxes, guide, order


def test_playback_same_step_explicit_order_changes_actual_blocking_geometry():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()
    failed = run_playback_sequence(BoxWorld(boxes), guide, order)
    assert [c.id for c in failed["checks"] if c.status == "fail"] == ["operation:2:insert"]
    hit = failed["operations"][2]["pairs"][1]
    assert hit["part"] == "blocker" and hit["state"] == "blocked" and hit["overlap_mm3"] > 0
    assert 0 < hit["first_contact_mm"][1] < 6
    corrected = run_playback_sequence(BoxWorld(boxes), guide, {"stage": ["base", "insert", "blocker"]})
    assert not [c for c in corrected["checks"] if c.status == "fail"]
    assert corrected["operations"][1]["installed"] == ["base"]
    assert corrected["operations"][2]["installed"] == ["base", "insert"]
    assert failed["operations"][2]["pairs"][1] == hit  # original finding is not rewritten


@pytest.mark.parametrize("order", [{}, {"stage": ["base", "insert"]},
                                    {"stage": ["base", "insert", "insert"]},
                                    {"stage": ["base", "blocker", "unknown"]},
                                    {"stage": ["base", "blocker", "insert"], "bad": []}])
def test_playback_requires_complete_explicit_instance_order_before_geometry(order):
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, _ = playback_fixture_data()
    world = BoxWorld(boxes)
    with pytest.raises(ValueError):
        run_playback_sequence(world, guide, order)
    assert world.queries == 0


def test_playback_reference_step_and_nonmonotone_membership_match_player_contract():
    from cadagent.review.gates.playback import playback_operations
    boxes, guide, order = playback_fixture_data()
    overview = {"id": "overview", "parts": list(boxes), "offsets_mm": {}}
    guide["steps"].insert(0, overview)
    assert len(playback_operations(guide, order, ["overview"])) == 3
    with pytest.raises(ValueError, match="cover each new"):
        playback_operations(guide, order)
    guide["steps"].append({"id": "later", "parts": ["base"], "offsets_mm": {}})
    with pytest.raises(ValueError, match="monotone"):
        playback_operations(guide, {**order, "later": []}, ["overview"])


def test_playback_unknown_and_budget_remain_failed_witnesses():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()

    class UnknownWorld(BoxWorld):
        def relate_at(self, key, shift, other):
            if key == "insert" and other == "blocker":
                return Relation(key, other, "unknown", error="seeded kernel failure")
            return super().relate_at(key, shift, other)

    result = run_playback_sequence(UnknownWorld(boxes), guide, order)
    pair = result["operations"][2]["pairs"][1]
    assert pair["state"] == "unknown" and pair["error"] == "seeded kernel failure"
    assert result["checks"][-1].status == "fail"
    result = run_playback_sequence(BoxWorld(boxes), guide, order, options=AccessOptions(max_samples=1))
    assert any(p["state"] == "unchecked" for o in result["operations"] for p in o["pairs"])
    assert any(c.status == "fail" for c in result["checks"])


def captured_playback_fixture(tmp_path, *, native=False):
    """Source fixture: meshes and BREP binding come from the same in-memory CAD shapes."""
    import hashlib
    from cadagent.publish.guides import collect_guides
    boxes, minimal, order = playback_fixture_data()
    assembly = None
    parts = []
    if native:
        cq = pytest.importorskip("cadquery")
        from cadagent.review.gates.relations import Assembly
        assembly = Assembly()
    for name, bounds in boxes.items():
        path = tmp_path / (name + ".stl")
        if native:
            lo, size = bounds[:3], [bounds[i + 3] - bounds[i] for i in range(3)]
            shape = cq.Workplane("XY").box(*size, centered=False).translate(lo).val()
            assembly.add(name, shape)
            cq.exporters.export(shape, str(path))
        else:
            path.write_bytes(("fixture mesh " + name).encode())
        parts.append({"name": name, "file": path.name, "bounds_mm": list(bounds),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    model_path = tmp_path / "view.json"
    model_path.write_text(json.dumps({"units": "mm", "up": "z", "parts": parts}))
    guide = {"schema": "cad-agent.assembly-guide/1",
             "snapshot": {"id": "fixture", "revision": "side insertion", "status": "wip", "source_commit": "a" * 40},
             "model": {"file": "view.json", "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()},
             "subassemblies": [{"id": "assembly", "title": "Assembly", "parts": list(boxes)}],
             "steps": [{**minimal["steps"][0], "title": "Install parts", "subassembly": "assembly",
                        "highlight": list(boxes), "text": "Fixture with side insertion."}],
             "source": {"install_order_by_step": order}}
    (tmp_path / "guide.json").write_text(json.dumps(guide))
    return collect_guides(tmp_path, ["guide.json"])[0], assembly


def test_playback_missing_binding_fails_before_optional_cad_import(tmp_path, monkeypatch):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("must reject before native load"))
    report = playback.playback_gate(bundle, None, {})
    assert not report["pass"] and "missing or stale" in report["checks"][0]["message"]
    assert report["operations"] == [] and report["support_stability"]["status"] == "unknown"
    assert report["physical_fit_verified"] is False


def test_real_cad_source_bound_playback_keeps_blocked_and_corrected_order(tmp_path):
    from cadagent.review.gates.playback import bind_playback_geometry, playback_gate
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    binding, breps = bind_playback_geometry(assembly, bundle)
    blocked = playback_gate(bundle, binding, breps)
    assert not blocked["pass"], blocked
    pair = blocked["operations"][2]["pairs"][1]
    assert pair["state"] == "blocked" and pair["overlap_mm3"] > 0
    corrected = playback_gate(bundle, binding, breps,
                              install_order_by_step={"stage": ["base", "insert", "blocker"]})
    assert corrected["pass"], corrected["findings"]
    assert corrected["status"] == "warn"  # support and zero-offset insertion remain unverified
    assert blocked["inputs"]["install_order_digest"] != corrected["inputs"]["install_order_digest"]
    assert blocked["inputs"]["guide_sha256"] == corrected["inputs"]["guide_sha256"]
    assert blocked["operations"][2]["pairs"][1] == pair
    assert not corrected["limits"]["physical_assembly_verified"]


@pytest.mark.parametrize("mutation, message", [
    (lambda b, p: b.update(source_commit="b" * 40), "missing or stale"),
    (lambda b, p: b.update(model_sha256="0" * 64), "missing or stale"),
    (lambda b, p: p.update(insert=p["insert"] + b"changed"), "stale BREP/mesh"),
    (lambda b, p: b["instances"]["insert"].update(mesh_sha256="0" * 64), "stale BREP/mesh"),
    (lambda b, p: b["instances"].pop("insert"), "exact guide instance"),
    (lambda b, p: b["instances"]["insert"].update(matrix=[1] * 11), "invalid CAD placement"),
])
def test_playback_stale_native_inputs_reject_before_queries(tmp_path, monkeypatch, mutation, message):
    import cadagent.review.gates.playback as playback
    # Fake BREP bytes suffice: a successful identity check has not imported CAD yet.
    from cadagent.review.evidence import brep_content_hash
    bundle, _ = captured_playback_fixture(tmp_path)
    guide, model, inputs = playback._captured(bundle)
    breps = {p["name"]: ("brep " + p["name"]).encode() for p in model["parts"]}
    binding = {"schema": playback.BINDING_SCHEMA, **inputs, "instances": {
        p["name"]: {"brep_sha256": playback._sha(breps[p["name"]]),
                    "shape_sha256": brep_content_hash(breps[p["name"]]), "mesh_sha256": p["sha256"],
                    "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]} for p in model["parts"]}}
    mutation(binding, breps)
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("must reject before native load"))
    report = playback.playback_gate(bundle, binding, breps)
    assert not report["pass"] and message in report["checks"][0]["message"]


def test_playback_query_exception_preserves_previous_collisions_and_later_operations():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()
    boxes["later"] = (20, 0, 0, 21, 1, 1)
    guide["steps"][0]["parts"].append("later")
    guide["steps"][0]["offsets_mm"]["later"] = [-20, 0, 0]
    order["stage"].append("later")

    class BrokenWorld(BoxWorld):
        def relate_at(self, key, shift, other):
            if key == "later" and other == "blocker":
                raise RuntimeError("seeded native exception")
            return super().relate_at(key, shift, other)

    result = run_playback_sequence(BrokenWorld(boxes), guide, order)
    assert result["operations"][2]["pairs"][1]["state"] == "blocked"
    assert result["operations"][3]["pairs"][1] == {
        "part": "blocker", "state": "unknown", "error": "RuntimeError: seeded native exception"}
    assert [c.id for c in result["checks"] if c.status == "fail"] == ["operation:2:insert", "operation:3:insert"]


def test_unchecked_relation_is_never_treated_as_clear_at_seat_or_on_path():
    class UncheckedWorld(BoxWorld):
        def relate_at(self, key, shift, other):
            if any(shift):
                return Relation(key, other, "unchecked", error="not computed")
            return super().relate_at(key, shift, other)

    boxes = {"moving": (0, 0, 0, 1, 1, 1), "side": (2, 0, 0, 3, 1, 1)}
    world = UncheckedWorld(boxes)
    assert sweep_pair(world, "moving", (-1, 0, 0), "side", travel_mm=4)["state"] == "unchecked"
    world.relate_at = lambda key, shift, other: Relation(key, other, "unchecked", error="seat not computed")
    assert sweep_pair(world, "moving", (-1, 0, 0), "side", travel_mm=4)["state"] == "unchecked"


@pytest.mark.parametrize("mutation, message", [
    (lambda b: b["view.json"].replace(b'"units": "mm"', b'"units": "m"'), "hash mismatch"),
    (lambda b: b["insert.stl"] + b"stale", "mesh hash mismatch"),
])
def test_playback_rechecks_captured_model_and_mesh_bytes(tmp_path, mutation, message):
    from cadagent.review.gates.playback import playback_gate
    bundle, _ = captured_playback_fixture(tmp_path)
    name = "view.json" if message == "hash mismatch" else "insert.stl"
    bundle.files[name] = mutation(bundle.files)
    report = playback_gate(bundle, None, {})
    assert not report["pass"] and message in report["checks"][0]["message"]


@pytest.mark.parametrize("field, value", [("units", "m"), ("up", "y")])
def test_playback_non_mm_or_z_up_model_rejected_even_with_rebound_hash(tmp_path, field, value):
    import hashlib
    from cadagent.review.gates.playback import playback_gate
    bundle, _ = captured_playback_fixture(tmp_path)
    model = json.loads(bundle.files["view.json"])
    model[field] = value
    bundle.files["view.json"] = json.dumps(model).encode()
    guide = json.loads(bundle.files["guide.json"])
    guide["model"]["sha256"] = hashlib.sha256(bundle.files["view.json"]).hexdigest()
    bundle.files["guide.json"] = json.dumps(guide).encode()
    report = playback_gate(bundle, None, {})
    assert not report["pass"] and "mm/z-up" in report["checks"][0]["message"]


@pytest.mark.parametrize("name,value", [("max_step_mm", float("nan")), ("margin_mm", float("inf")),
                                       ("max_samples", float("inf")), ("refine_steps", .5),
                                       ("max_samples", True), ("tool_access", "false")])
def test_insertion_options_reject_nonfinite_or_nonintegral_budgets(name, value):
    with pytest.raises(ValueError):
        AccessOptions(**{name: value})


def test_unchecked_onset_midpoint_never_becomes_a_clear_contact_bracket():
    from cadagent.review.gates.assembly import _onset

    class MidpointWorld(BoxWorld):
        def relate_at(self, key, shift, other):
            return Relation(key, other, "unchecked", error="midpoint unavailable")

    world = MidpointWorld({"moving": (0, 0, 0, 1, 1, 1), "side": (2, 0, 0, 3, 1, 1)})
    hit = Relation("moving", "side", "overlapping", overlap_mm3=.5)
    clear = Relation("moving", "side", "apart", gap_mm=1)
    result = _onset(world, "moving", (1, 0, 0), "side", 1, 4, hit, clear, AccessOptions())
    assert result["state"] == "blocked" and result["first_contact_mm"] == [4, 1]
    assert result["clear_gap_mm"] == 1 and result["refine_samples"] == 1


def test_original_brep_binder_preserves_bytes_and_producer_platform_without_native_import(tmp_path):
    from cadagent.review.gates.playback import bind_playback_breps
    from cadagent.review.evidence import brep_content_hash
    import hashlib
    bundle, _ = captured_playback_fixture(tmp_path)
    breps = {p["name"]: ("original BREP " + p["name"]).encode() for p in json.loads(bundle.files["view.json"])["parts"]}
    platform = {"machine": "aarch64", "ocp": "original producer runtime"}
    binding = bind_playback_breps(bundle, breps, producer_hash_platform=platform)
    assert binding["hash_platform"] == platform
    for name, payload in breps.items():
        entry = binding["instances"][name]
        assert entry["brep_sha256"] == hashlib.sha256(payload).hexdigest()
        assert entry["shape_sha256"] == brep_content_hash(payload)
        assert entry["matrix"] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


@pytest.mark.parametrize("kind", ["shift", "double-applied"])
def test_real_playback_rejects_stale_or_double_applied_placement_before_path_queries(tmp_path, monkeypatch, kind):
    import cadagent.review.gates.playback as playback
    from cadagent.review.gates.relations import Assembly
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    if kind == "double-applied":
        cq = pytest.importorskip("cadquery")
        local = Assembly()
        for name in assembly.names:
            # Same world geometry, now represented as local shape + one authored placement.
            shape = cq.Shape(assembly[name].shape).translate((-7, 0, 0))
            local.add(name, shape, location=(7, 0, 0))
        binding, breps = playback.bind_playback_geometry(local, bundle)
        positive = playback.playback_gate(bundle, binding, breps,
                                          install_order_by_step={"stage": ["base", "insert", "blocker"]})
        assert positive["pass"], positive["findings"]
        binding["instances"]["insert"]["matrix"][3] *= 2
    else:
        binding, breps = playback.bind_playback_geometry(assembly, bundle)
        original = playback.playback_gate(bundle, binding, breps)
        assert not original["pass"] and original["operations"][2]["pairs"][1]["state"] == "blocked"
        binding["instances"]["insert"]["matrix"][3] += 100
    monkeypatch.setattr(playback, "run_playback_sequence", lambda *a, **k: pytest.fail("reject before paths"))
    report = playback.playback_gate(bundle, binding, breps)
    assert not report["pass"] and "CAD/mesh world bounds mismatch: insert" in report["checks"][0]["message"]
    assert report["operations"] == []
    assert report["frames"][-1]["instance"] == "insert"
    assert report["frames"][-1]["cad_mesh_max_error_mm"] >= 7


@pytest.mark.parametrize("bounds_tolerance", [float("nan"), float("inf"), -1, 1.001, True])
def test_playback_invalid_bounds_tolerance_fails_before_native_load(tmp_path, monkeypatch, bounds_tolerance):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("reject before native load"))
    report = playback.playback_gate(bundle, None, {}, bounds_tolerance_mm=bounds_tolerance)
    assert not report["pass"] and "bounds_tolerance_mm" in report["checks"][0]["message"]
    json.dumps(report, allow_nan=False)


def test_playback_invalid_relation_tolerance_fails_before_native_load(tmp_path, monkeypatch):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("reject before native load"))
    report = playback.playback_gate(bundle, None, {}, tol=Tolerances(touch_mm=float("nan")))
    assert not report["pass"] and "must be finite" in report["checks"][0]["message"]
    json.dumps(report, allow_nan=False)


def test_default_metadata_filters_only_empty_explicit_reference_order(tmp_path):
    from cadagent.review.gates.playback import bind_playback_geometry, playback_gate
    from cadagent.publish.guides import collect_guides
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    guide = json.loads(bundle.files["guide.json"])
    guide["steps"].insert(0, {**guide["steps"][0], "id": "overview"})
    guide["source"]["install_order_by_step"]["overview"] = []
    (tmp_path / "guide.json").write_text(json.dumps(guide))
    bundle = collect_guides(tmp_path, ["guide.json"])[0]
    binding, breps = bind_playback_geometry(assembly, bundle)
    report = playback_gate(bundle, binding, breps, reference_step_ids=["overview"])
    assert report["operations"][2]["pairs"][1]["state"] == "blocked"  # reached the real path check
    explicit = playback_gate(bundle, binding, breps, reference_step_ids=["overview"],
                              install_order_by_step=guide["source"]["install_order_by_step"])
    assert not explicit["pass"] and "reference installation order" in explicit["checks"][0]["message"]
    guide["source"]["install_order_by_step"]["overview"] = ["base"]
    (tmp_path / "guide.json").write_text(json.dumps(guide))
    bundle = collect_guides(tmp_path, ["guide.json"])[0]
    binding, breps = bind_playback_geometry(assembly, bundle)
    nonempty = playback_gate(bundle, binding, breps, reference_step_ids=["overview"])
    assert not nonempty["pass"] and "reference installation order" in nonempty["checks"][0]["message"]


def test_playback_missing_optional_stl_parser_is_a_failure_before_path_queries(tmp_path, monkeypatch):
    import cadagent.review.gates.playback as playback
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    binding, breps = playback.bind_playback_geometry(assembly, bundle)
    monkeypatch.setitem(sys.modules, "trimesh", None)
    monkeypatch.setattr(playback, "run_playback_sequence", lambda *a, **k: pytest.fail("no path without mesh frame"))
    report = playback.playback_gate(bundle, binding, breps)
    assert not report["pass"] and "trimesh" in report["checks"][0]["message"]
    assert report["operations"] == []


def test_playback_preflight_has_distinct_scope_and_never_calls_insertion(tmp_path, monkeypatch):
    import cadagent.review.gates.playback as playback
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    binding, breps = playback.bind_playback_geometry(assembly, bundle)
    events = []
    monkeypatch.setattr(playback, "run_playback_sequence", lambda *a, **k: pytest.fail("preflight must not run paths"))
    report = playback.playback_gate(bundle, binding, breps, preflight_only=True, on_progress=events.append)
    assert report["gate"] == "assembly-playback-preflight" and report["pass"]
    assert report["limits"]["paths_checked"] is False and report["limits"]["progress_complete"] is True
    assert report["operations"] == [] and len(report["frames"]) == 3
    assert report["physical_fit_verified"] is False
    assert any(c["id"] == "paths" and c["status"] == "warn" for c in report["checks"])
    assert not [e for e in events if e["event"] in ("pair", "operation")]
    assert events[-1]["event"] == "preflight" and events[-1]["inputs"] == report["inputs"]
    phases = [(e.get("phase"), e["state"], e.get("instance")) for e in events if e["event"] == "phase"]
    for name in ("base", "blocker", "insert"):
        assert phases.index(("load", "starting", name)) < phases.index(("load", "complete", name))
        assert phases.index(("frame", "starting", name)) < phases.index(("frame", "complete", name))
    assert phases.index(("load", "starting", None)) < phases.index(("load", "starting", "base"))
    assert phases.index(("frame", "starting", None)) < phases.index(("frame", "starting", "base"))


def test_playback_progress_events_order_pair_witnesses_and_isolate_mutation():
    import copy
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()
    events = []

    def observer(event):
        events.append(copy.deepcopy(event))
        if "result" in event:
            event["result"].clear()  # callers must not mutate the internal witness/row
        event["instance"] = "caller mutation"

    result = run_playback_sequence(BoxWorld(boxes), guide, order, on_progress=observer)
    reference = run_playback_sequence(BoxWorld(boxes), guide, order)
    assert result["operations"] == reference["operations"]
    assert [c.to_dict() for c in result["checks"]] == [c.to_dict() for c in reference["checks"]]
    pairs = [e for e in events if e["event"] == "pair"]
    assert [(e["operation_index"], e["pair_index"], e["state"]) for e in pairs] == [
        (1, 0, "starting"), (1, 0, "complete"), (2, 0, "starting"), (2, 0, "complete"),
        (2, 1, "starting"), (2, 1, "complete")]
    assert pairs[-1]["result"]["state"] == "blocked" and pairs[-1]["result"]["part"] == "blocker"
    assert all(e["schema"] == "cad-agent.playback-progress/1" for e in events)
    json.dumps(events, allow_nan=False)


def test_playback_callback_failure_retains_current_blocker_and_stops_later_operations():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()
    boxes["later"] = (20, 0, 0, 21, 1, 1)
    guide["steps"][0]["parts"].append("later")
    guide["steps"][0]["offsets_mm"]["later"] = [-20, 0, 0]
    order["stage"].append("later")
    events = []

    def disk_full(event):
        events.append(event)
        if event["event"] == "pair" and event["state"] == "complete" and event["result"]["state"] == "blocked":
            raise OSError("seeded checkpoint disk full")

    result = run_playback_sequence(BoxWorld(boxes), guide, order, on_progress=disk_full)
    assert result["complete"] is False
    assert [r["instance"] for r in result["operations"]] == ["base", "blocker", "insert"]
    partial = result["operations"][-1]
    assert partial["complete"] is False and partial["pairs"][-1]["state"] == "blocked"
    assert partial["pairs"][-1]["part"] == "blocker"
    assert [c.id for c in result["checks"] if c.status == "fail"] == ["operation:2:insert", "progress"]
    assert result["checks"][-1].evidence["operation_index"] == 2
    assert not [e for e in events if e["instance"] == "later"]


def test_playback_callback_failure_after_completed_collision_preserves_earlier_check():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()

    def fail_after_operation(event):
        if event["event"] == "operation" and event["state"] == "complete" and event["operation_index"] == 2:
            raise OSError("cannot persist completed operation")

    result = run_playback_sequence(BoxWorld(boxes), guide, order, on_progress=fail_after_operation)
    assert result["complete"] is False
    assert result["operations"][-1]["pairs"][-1]["state"] == "blocked"
    assert [c.id for c in result["checks"] if c.status == "fail"] == ["operation:2:insert", "progress"]


def test_playback_preflight_callback_failure_before_native_load_is_explicit_failure(tmp_path, monkeypatch):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    from cadagent.review.evidence import brep_content_hash
    model = json.loads(bundle.files["view.json"])
    breps = {p["name"]: ("synthetic original BREP " + p["name"]).encode() for p in model["parts"]}
    binding = playback.bind_playback_breps(bundle, breps, producer_hash_platform={"machine": "synthetic"})
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("must stop before native load"))

    def failed_storage(event):
        if event.get("phase") == "load" and event["state"] == "starting":
            raise OSError("checkpoint unavailable")

    report = playback.playback_gate(bundle, binding, breps, preflight_only=True, on_progress=failed_storage)
    assert not report["pass"] and report["gate"] == "assembly-playback-preflight"
    assert report["limits"]["paths_checked"] is False and report["operations"] == []
    assert report["checks"][-2]["id"] == "progress" and "checkpoint unavailable" in report["checks"][-2]["message"]
    assert report["checks"][-2]["evidence"]["phase"] == "load"
    assert report["inputs"]["binding_digest"]


def test_playback_full_gate_callback_failure_keeps_collision_and_partial_evidence(tmp_path):
    import cadagent.review.gates.playback as playback
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    binding, breps = playback.bind_playback_geometry(assembly, bundle)
    events = []

    def checkpoint(event):
        events.append(event)
        if event["event"] == "pair" and event["state"] == "complete" and event["result"]["state"] == "blocked":
            raise OSError("cannot flush pair")

    report = playback.playback_gate(bundle, binding, breps, on_progress=checkpoint)
    assert not report["pass"] and report["limits"]["progress_complete"] is False
    assert report["limits"]["paths_checked"] is False
    assert report["operations"][-1]["pairs"][-1]["state"] == "blocked"
    assert any(c["id"] == "operation:2:insert" and c["status"] == "fail" for c in report["checks"])
    assert any(c["id"] == "progress" and c["status"] == "fail" for c in report["checks"])
    assert events[-1]["result"]["state"] == "blocked"


def test_playback_default_and_observed_full_results_have_equal_geometry(tmp_path):
    import cadagent.review.gates.playback as playback
    bundle, assembly = captured_playback_fixture(tmp_path, native=True)
    binding, breps = playback.bind_playback_geometry(assembly, bundle)
    plain = playback.playback_gate(bundle, binding, breps)
    events = []
    observed = playback.playback_gate(bundle, binding, breps, on_progress=events.append)
    assert plain["checks"] == observed["checks"] and plain["operations"] == observed["operations"]
    assert plain["frames"] == observed["frames"] and plain["inputs"] == observed["inputs"]
    assert "paths_checked" not in plain["limits"] and observed["limits"]["paths_checked"] is True
    assert plain["pass"] == observed["pass"] is False


@pytest.mark.parametrize("kwargs", [{"preflight_only": "yes"}, {"on_progress": False}])
def test_playback_bad_progress_options_fail_before_native_queries(tmp_path, monkeypatch, kwargs):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("invalid options must not load CAD"))
    report = playback.playback_gate(bundle, None, {}, **kwargs)
    assert not report["pass"] and report["operations"] == []


def test_playback_pair_start_callback_failure_keeps_remaining_pair_unchecked_without_query():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()

    class RecordingWorld(BoxWorld):
        def __init__(self, boxes):
            super().__init__(boxes)
            self.parties = []

        def relate_at(self, key, shift, other):
            self.parties.append((key, other))
            return super().relate_at(key, shift, other)

    world = RecordingWorld(boxes)

    def checkpoint(event):
        if event["event"] == "pair" and event["state"] == "starting" and event["obstacle"] == "blocker":
            raise OSError("cannot write pair-start checkpoint")

    result = run_playback_sequence(world, guide, order, on_progress=checkpoint)
    assert result["complete"] is False
    partial = result["operations"][-1]
    assert partial["instance"] == "insert" and partial["complete"] is False
    assert partial["unchecked_pairs"] == ["blocker"] and len(partial["pairs"]) == 1
    assert ("insert", "blocker") not in world.parties
    assert result["checks"][-1].id == "progress" and result["checks"][-1].status == "fail"


def test_playback_awaitable_callback_cannot_silently_skip_checkpoint_work():
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data()
    world = BoxWorld(boxes)

    async def checkpoint(event):
        raise OSError("would fail only if awaited")

    result = run_playback_sequence(world, guide, order, on_progress=checkpoint)
    assert result["complete"] is False and world.queries == 0
    assert result["checks"][-1].status == "fail" and "must complete synchronously" in result["checks"][-1].message


@pytest.mark.parametrize("kind", ["generator", "async-generator"])
def test_playback_lazy_checkpoint_body_never_counts_as_completed_progress(kind):
    from cadagent.review.gates.playback import run_playback_sequence
    boxes, guide, order = playback_fixture_data({"stage": ["base", "insert", "blocker"]})
    world, written = BoxWorld(boxes), []

    def generator(event):
        written.append(event)
        yield "saved"

    async def async_generator(event):
        written.append(event)
        yield "saved"

    callback = generator if kind == "generator" else async_generator
    result = run_playback_sequence(world, guide, order, on_progress=callback)
    assert world.queries == 0 and written == [] and result["complete"] is False
    assert result["checks"][-1].id == "progress" and result["checks"][-1].status == "fail"
    assert "without yielding" in result["checks"][-1].message


@pytest.mark.parametrize("kind", ["generator", "async-generator"])
def test_playback_lazy_checkpoint_rejected_by_full_gate_before_native_work(tmp_path, monkeypatch, kind):
    import cadagent.review.gates.playback as playback
    bundle, _ = captured_playback_fixture(tmp_path)
    written = []

    def generator(event):
        written.append(event)
        yield "saved"

    async def async_generator(event):
        written.append(event)
        yield "saved"

    callback = generator if kind == "generator" else async_generator
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("lazy observer must not start native load"))
    report = playback.playback_gate(bundle, None, {}, on_progress=callback)
    assert not report["pass"] and written == [] and report["operations"] == []
    assert report["limits"]["progress_complete"] is False
    assert report["checks"][0]["id"] == "progress" and "without yielding" in report["checks"][0]["message"]


# Canonical plan fixtures are shared with both actual web consumers. The oracle below uses source bench
# datums, not evaluator output; its thin/parked/attached controls remain useful without a CAD kernel.
PLAN_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "assembly-plan"


def serial_plan_fixture():
    return json.loads((PLAN_FIXTURE / "plan.json").read_text())


def test_serial_plan_independent_corners_absolute_seek_and_reverse_order():
    from cadagent.review.dossier.plan import normalize_plan, plan_state
    plan = normalize_plan(serial_plan_fixture())
    assert plan_state(plan, .25)["plate"] == [8.75, 0, 25]
    assert plan_state(plan, .5)["plate"] == [0, 0, 22.5]
    assert plan_state(plan, 1.5)["lid"] == [7.5, 0, 20]
    assert plan_state(plan, 1.5)["fastener"] == [0, 0, 0]
    assert plan_state(plan, 0)["lid"] == [35, 0, 20]
    assert all(v == [0, 0, 0] for v in plan_state(plan, 2).values())
    for value in [2, 0, .5, 1.5, 0, 2, .25]:
        assert plan_state(plan, value) == plan_state(plan, 2 - (2 - value))
    plan_state(plan, 0)["plate"][0] = 1000
    assert plan_state(plan, .25)["plate"] == [8.75, 0, 25]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(units="m"), lambda p: p.update(frame="y-up"),
    lambda p: p["operations"][0].update(type="rotate"),
    lambda p: p["operations"][1].update(requires=[]),
    lambda p: p["operations"][0].update(requires=["lid"]),
    lambda p: p["operations"][0]["members"].append("lid"),
    lambda p: p["operations"][0]["members"].append("missing"),
    lambda p: p["operations"][0].update(concurrent=True),
    lambda p: p["operations"][0]["path_mm"].append([float("nan"), 0, 0]),
    lambda p: p["operations"][0].update(path_mm=[[0, 0, 0], [0, 0, 0]]),
    lambda p: p["source"]["instances"]["plate"]["matrix"].__setitem__(0, -1),
    lambda p: p["source"].pop("producer"), lambda p: p.update(clearance_mm=-1),
])
def test_serial_plan_rejects_unsupported_ambiguous_or_nonfinite_declarations(mutation):
    from cadagent.review.dossier.plan import normalize_plan
    plan = serial_plan_fixture()
    mutation(plan)
    with pytest.raises(ValueError):
        normalize_plan(plan)


def serial_box_world(plan, blocker=None):
    data = json.loads((PLAN_FIXTURE / "fixture.json").read_text())
    # Independent axis-aligned solids, including both rail walls, implemented as a compound-aware test world.
    boxes = data["boxes"]
    if blocker:
        boxes["blocker"] = [blocker]
        plan["fixed"].append("blocker")
        plan["source"]["instances"]["blocker"] = dict(plan["source"]["instances"]["base"])

    class CompoundBoxWorld(BoxWorld):
        def __init__(self):
            bounds = {name: tuple(min(b[i] for b in members) for i in range(3)) +
                      tuple(max(b[i] + b[i+3] for b in members) for i in range(3)) for name, members in boxes.items()}
            super().__init__(bounds)

        def relate_at(self, key, shift, other):
            relations = []
            for a in boxes[key]:
                for b in boxes[other]:
                    world = BoxWorld({"a": (*a[:3], *(a[i]+a[i+3] for i in range(3))),
                                      "b": (*b[:3], *(b[i]+b[i+3] for i in range(3)))})
                    relations.append(world.relate_at("a", shift, "b"))
            hit = next((r for r in relations if r.interferes), None)
            return hit or min(relations, key=lambda r: r.gap_mm)
    return CompoundBoxWorld()


def test_serial_plan_intermediate_parked_attached_and_clearance_controls():
    from cadagent.review.gates.playback import run_plan_sequence
    plan = serial_plan_fixture()
    result = run_plan_sequence(serial_box_world(plan), plan)
    assert all(row["insertion"] == "sampled-clear" for row in result["operations"])
    assert result["operations"][0]["tools"][0]["state"] == "unknown"  # no fake tool clearance on a box world
    reverse = run_plan_sequence(serial_box_world(plan), plan, reverse=True)
    assert [r["id"] for r in reverse["operations"]] == ["lid", "plate"]
    assert all(row["insertion"] == "sampled-clear" for row in reverse["operations"])
    for blocker, moving in [([-4,-4,16,8,8,.2], "plate"), ([9.5,-.5,29,.2,1,.2], "fastener")]:
        control = serial_plan_fixture()
        result = run_plan_sequence(serial_box_world(control, blocker), control)
        hits = [p for p in result["operations"][0]["pairs"] if p["part"] == "blocker" and p["state"] == "blocked"]
        assert any(p["moving"] == moving for p in hits), result
        assert all(p["first_contact_mm"][0] is not None for p in hits)
        if moving == "fastener":
            assert not any(p["moving"] == "plate" for p in hits)
    control = serial_plan_fixture()
    control["operations"][1]["path_mm"][0] = [0,0,10]
    result = run_plan_sequence(serial_box_world(control), control)
    assert any(p["part"] == "lid" and p["state"] == "blocked" for p in result["operations"][0]["pairs"])
    wrong_order = serial_plan_fixture()
    wrong_order["operations"].reverse()
    wrong_order["operations"][0]["requires"] = []
    wrong_order["operations"][1]["requires"] = ["lid"]
    result = run_plan_sequence(serial_box_world(wrong_order), wrong_order)
    assert any(p["part"] == "lid" and p["state"] == "blocked" for p in result["operations"][1]["pairs"])
    exhausted = run_plan_sequence(serial_box_world(plan), plan, options=AccessOptions(max_samples=0))
    assert any(p["state"] == "unchecked" for r in exhausted["operations"] for p in r["pairs"])
    control = serial_plan_fixture()
    control["clearance_mm"] = 2
    result = run_plan_sequence(serial_box_world(control), control)
    assert any(p["state"] in ("insufficient-clearance", "clearance-unresolved") for p in result["operations"][0]["pairs"])


def native_serial_fixture(tmp_path):
    pytest.importorskip("cadquery")
    spec = importlib.util.spec_from_file_location("serial_native_bench", PLAN_FIXTURE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(tmp_path)


def test_native_serial_plan_source_bound_forward_reverse_and_ordinary_driver(tmp_path):
    from cadagent.review.gates.playback import playback_gate
    assembly, bundle, binding, breps, spec, tool = native_serial_fixture(tmp_path)
    for reverse in (False, True):
        report = playback_gate(bundle, binding, breps, fastener_specs=[spec], tools={"ordinary-driver": tool}, reverse=reverse)
        assert report["pass"], report["findings"]
        assert all(r["insertion"] == "sampled-clear" for r in report["operations"])
        plate = next(r for r in report["operations"] if r["id"] == "plate")
        assert plate["tools"][0]["state"] == "sampled-clear"
        assert plate["internal_qualification"] == "unknown"
        assert report["physical_fit_verified"] is False
    # Hash agreement cannot validate wrong physical intent: wrong lateral arrival crosses a rail wall.
    from cadagent.review.gates.assembly import AssemblySequenceWorld
    from cadagent.review.gates.playback import run_plan_sequence
    wrong = serial_plan_fixture()
    wrong["operations"][0]["path_mm"] = [[20,0,0],[0,0,0]]
    result = run_plan_sequence(AssemblySequenceWorld(assembly), wrong)
    assert any(p["part"] == "rail" and p["state"] == "blocked" for p in result["operations"][0]["pairs"])


def test_native_serial_tool_approach_obstruction_and_stale_source_controls(tmp_path, monkeypatch):
    import cadquery as cq
    import cadagent.review.gates.playback as playback
    from cadagent.review.gates.assembly import AssemblySequenceWorld
    assembly, bundle, binding, breps, spec, tool = native_serial_fixture(tmp_path)
    # At z31 the fixed obstruction misses every component path and engaged tool, but blocks the handle
    # during ordinary straight approach. This is independent source geometry, not a fabricated tool result.
    assembly.add("blocker", cq.Solid.makeBox(1,2,1,cq.Vector(3,-1,31)))
    plan = serial_plan_fixture()
    plan["fixed"].append("blocker")
    plan["source"]["instances"]["blocker"] = dict(plan["source"]["instances"]["base"])
    plan["operations"][1]["path_mm"] = [[35,0,20],[35,0,0],[0,0,0]]  # lower the lid beside, then below the fixed approach blocker
    result = playback.run_plan_sequence(AssemblySequenceWorld(assembly), plan, fastener_specs=[spec], tools={"ordinary-driver":tool})
    assert all(r["insertion"] == "sampled-clear" for r in result["operations"])
    access = result["operations"][0]["tools"][0]
    assert access["state"] == "blocked" and access["first_blocked_mm"] == 10
    assert any(p["part"] == "blocker" for p in access["samples"][0]["blocked"])
    from cadagent.review.gates.fasteners import tool_access
    stage = AssemblySequenceWorld(assembly).staged({n:[0,0,0] if n != "lid" else [35,0,20] for n in assembly.names})
    assert tool_access(stage,spec,0,"ordinary-driver",tool,stage.names)["clear"]
    monkeypatch.setattr(playback, "_load_world", lambda *a: pytest.fail("stale source must reject before CAD load"))
    smaller = {**tool, "segments":[{"d":1,"length":18}]}
    report = playback.playback_gate(bundle,binding,breps,fastener_specs=[spec],tools={"ordinary-driver":smaller})
    assert not report["pass"] and "stale assembly plan tooling" in report["checks"][0]["message"]
    for field in ("producer", "source_closure_sha256"):
        stale = {**binding, field: "0"*64}
        report = playback.playback_gate(bundle, stale, breps)
        assert not report["pass"] and "stale assembly plan source" in report["checks"][0]["message"]
