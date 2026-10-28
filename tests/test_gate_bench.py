"""Gate bench: the clean fixture and the plan's seeded defects (§6), one parametrised case per seed.

Each gate has an adapter below that turns a ``Bench`` into that gate's verdict dict. A gate that
is not built yet has an adapter raising ``NotImplementedError`` naming its task, and its cases are
strict xfails: when the task lands, its implementer writes the adapter and removes the mark (a
passing strict xfail fails the run, so the mark cannot be forgotten).

Every seed must make its gate fail with a finding that names the seeded part; the clean bench must
pass every gate with no finding. The relation-level tests check the raw evidence the gates will read.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

cq = pytest.importorskip("cadquery")
pytest.importorskip("trimesh")

from cadagent.gates import relate_pair, relation_table  # noqa: E402
from cadagent.gates.containment import containment_gate  # noqa: E402
from cadagent.gates.wall import wall_gate  # noqa: E402

_PATH = Path(__file__).resolve().parent / "fixtures" / "gate_bench" / "build.py"
_spec = importlib.util.spec_from_file_location("gate_bench_build", _PATH)
gb = importlib.util.module_from_spec(_spec)
sys.modules["gate_bench_build"] = gb          # dataclasses need the module registered
_spec.loader.exec_module(gb)


@pytest.fixture(scope="module")
def bench():
    return gb.build()


@pytest.fixture(scope="module")
def table(bench):
    return relation_table(bench.assembly)


# ----------------------------------------------------------------------------- gate adapters

def gate_wall(bench):
    return wall_gate({n: {"wall_mm": w, "mesh": bench.shape(n), "shape": bench.shape(n)}
                      for n, w in bench.print_parts.items()})


def gate_containment(bench):
    return containment_gate(bench.assembly, bench.declarations["contains"], support="fail")


def _not_built(task, gate):
    def adapter(bench):
        raise NotImplementedError(f"{task}: the {gate} gate is not built yet")
    return adapter


GATES = {
    "wall": (gate_wall, "T8"),
    "containment": (gate_containment, "T5"),
    "connectivity": (_not_built("T4", "connectivity"), "T4"),
    "fasteners": (_not_built("T6", "fastener"), "T6"),
    "motion": (_not_built("T7", "motion"), "T7"),
    "assembly": (_not_built("T9", "assembly-access"), "T9"),
    "dossier-lint": (_not_built("T2", "dossier-lint"), "T2"),
}
BUILT = {"wall", "containment"}


def _marks(gate):
    if gate in BUILT:
        return ()
    return (pytest.mark.xfail(raises=NotImplementedError, strict=True,
                              reason=f"{GATES[gate][1]}: {gate} gate not built yet"),)


@pytest.mark.parametrize("gate", [pytest.param(g, marks=_marks(g)) for g in GATES])
def test_clean_bench_passes_every_gate_with_no_finding(bench, gate):
    v = GATES[gate][0](bench)
    assert v["pass"] is True and v["findings"] == [], v["findings"]


@pytest.mark.parametrize("seed", [pytest.param(s, marks=_marks(spec["gate"])) for s, spec in gb.SEEDS.items()])
def test_seeded_defect_is_caught_by_its_gate(seed):
    spec = gb.SEEDS[seed]
    v = GATES[spec["gate"]][0](gb.build(seed))
    assert v["pass"] is False, f"{seed}: {spec['what']} was not caught"
    named = [f for f in v["findings"] if set(f.get("parts", [])) & set(spec["parts"])]
    assert named, f"{seed}: no finding names {spec['parts']}: {v['findings']}"


def test_every_plan_seed_is_a_case():
    assert len(gb.SEEDS) == 10
    assert {s["gate"] for s in gb.SEEDS.values()} == set(GATES)
    with pytest.raises(KeyError):
        gb.build("no_such_seed")


# ----------------------------------------------------------------------------- the fixture's raw evidence (T3)

def _free(bench, key):
    return bool(bench.result.geometry["parts"].get(bench.result.owner(key), {}).get("free"))


def test_clean_bench_contacts_are_exactly_the_declared_ones(bench, table):
    d = bench.declarations
    declared = {frozenset(i["parts"]) for i in d["interfaces"]}
    intended = {frozenset(o["parts"]) for o in d["intended_overlaps"]}
    assert table.stats["states"]["unknown"] == 0
    for iface in d["interfaces"]:
        assert table.get(*iface["parts"]).in_contact, f"{iface['id']} not realised"
    for rel in table.contacts():
        pair = frozenset((rel.a, rel.b))
        assert pair in declared or _free(bench, rel.a) or _free(bench, rel.b), f"undeclared contact {rel.a}-{rel.b}"
        if rel.interferes:                                   # overlapping or contains: shared volume
            assert pair in intended, f"undeclared interference {rel.a}-{rel.b}: {rel.overlap_mm3} mm3"
    names = set(bench.assembly.names)
    for i in d["interfaces"]:
        assert set(i["parts"]) <= names


def test_clean_bench_every_ball_is_inside_the_cavity(bench):
    for i in range(8):
        rel = relate_pair(bench.assembly, f"ball#{i}", "hopper_cavity")
        assert rel.state == "contains" and rel.contained == "a_in_b"


def test_bench_is_declared_through_the_dossier_registry(bench):
    geo = bench.result.geometry
    assert geo["parts"]["base"]["grounded"] and geo["parts"]["ball"]["free"] and geo["parts"]["ball"]["count"] == 8
    assert geo["cavities"]["hopper_cavity"]["part"] == "hopper"
    assert geo["joints"]["I-pin-arm"]["moving"] == "arm" and geo["joints"]["I-pin-arm"]["range"] == [0.0, 40.0]
    f0 = geo["fasteners"]["screw_0"]
    assert f0["clamps"] == "lid" and f0["into"] == "insert_0" and f0["min_engagement_mm"] == 1.5
    assert bench.assembly["screw_0"].kind == "fastener" and bench.assembly["hopper"].group == "store"
    # the screws sit where they are placed: head on the lid (Z=47..50), tip at the insert bottom (Z=39)
    from cadagent.gates.relations import bounding_box
    z0, z1 = bounding_box(bench.shape("screw_0"))[2::3]
    assert (z0, z1) == (pytest.approx(39.0), pytest.approx(50.0))
    steps = [s.fit for s in bench.result.steps]
    assert steps.index("board") < steps.index("lid")
    order = [s.fit for s in gb.build("lid_before_board").result.steps]
    assert order.index("lid") < order.index("board")
    assert gb.build("decision_without_alternatives").declarations["decisions"][0]["alternatives"] == []


def test_seed_ball_through_wall_shows_volume_outside_the_cavity():
    b = gb.build("ball_through_wall")
    rel = relate_pair(b.assembly, "ball#7", "hopper_cavity")
    assert rel.state == "overlapping" and rel.a_outside_b_mm3 > 100
    assert relation_table(b.assembly).get("ball#7", "hopper").state == "overlapping"


def test_seed_ball_through_wall_gate_reports_half_the_ball_outside():
    """Seed 1 puts ball#7's centre on the cavity's +Y face: half the ball (r 5 mm) is outside, and its
    far pole is 5 mm out (2.6 mm past the hopper's outer face)."""
    v = gate_containment(gb.build("ball_through_wall"))
    (inside,) = [f for f in v["findings"] if f["id"].endswith("ball#7:inside")]
    assert inside["evidence"]["outside_mm3"] == pytest.approx(2 / 3 * 3.141592653589793 * 125, rel=1e-6)
    assert inside["evidence"]["depth_mm"] == pytest.approx(5.0, abs=1e-3)
    assert inside["evidence"]["furthest_outside_point"] == pytest.approx([41.0, 67.6, 21.4], abs=1e-3)
    (wall,) = [f for f in v["findings"] if f["id"].endswith("ball#7:wall")]
    assert wall["evidence"]["relation"]["overlap_mm3"] == pytest.approx(3.141592653589793 * (25 * 2.4 - 2.4 ** 3 / 3),
                                                                        rel=1e-6)
    # moved off the ball it stood on, it rests on nothing (the wall it crosses is vertical)
    (support,) = [f for f in v["findings"] if f["id"].endswith(":support")]
    assert support["evidence"]["unsupported"] == ["ball#7"]
    assert len(v["findings"]) == 3


def test_seed_bracket_floats_and_hovers_in_the_relation_table():
    floats = relation_table(gb.build("bracket_floats").assembly)
    assert not any(r.in_contact for r in floats.of("bracket"))
    hovers = relation_table(gb.build("bracket_hovers").assembly)
    rel = hovers.get("bracket", "base")
    assert rel.state == "apart" and rel.gap_mm == pytest.approx(0.5)


def test_seed_thin_wall_witness_lies_on_the_thinned_wall():
    v = gate_wall(gb.build("thin_wall"))
    (finding,) = v["findings"]
    for w in finding["evidence"]["witnesses"]:
        xs = sorted((w["point"][0], w["exit_point"][0]))
        assert xs == [pytest.approx(57.6, abs=1e-3), pytest.approx(58.4, abs=1e-3)], w
        assert w["thickness_mm"] == pytest.approx(0.8, abs=1e-3)


def test_arm_clears_the_frame_over_its_declared_range_and_not_beyond(bench):
    lo, hi = bench.result.geometry["joints"]["I-pin-arm"]["range"]
    first_hit = gb.arm_frame_contact_deg()
    assert hi < first_hit < gb.SEEDS["flap_hits_frame"]["params"]["flap_range_deg"][1]
    for deg in range(int(lo), int(hi) + 1, 5):
        rel = relation_table(gb.arm_pose(bench, deg), only=["arm"]).get("arm", "frame", exact=True)
        assert rel.state == "apart", f"arm meets frame at {deg} deg"
    hit = relation_table(gb.arm_pose(bench, first_hit + 1), only=["arm"]).get("arm", "frame")
    assert hit.state == "overlapping"
