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

from cadagent.gates import relate, relation_table  # noqa: E402
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


def _not_built(task, gate):
    def adapter(bench):
        raise NotImplementedError(f"{task}: the {gate} gate is not built yet")
    return adapter


GATES = {
    "wall": (gate_wall, "T8"),
    "containment": (_not_built("T5", "containment"), "T5"),
    "connectivity": (_not_built("T4", "connectivity"), "T4"),
    "fasteners": (_not_built("T6", "fastener"), "T6"),
    "motion": (_not_built("T7", "motion"), "T7"),
    "assembly": (_not_built("T9", "assembly-access"), "T9"),
    "dossier-lint": (_not_built("T2", "dossier-lint"), "T2"),
}
BUILT = {"wall"}


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

def test_clean_bench_contacts_are_exactly_the_declared_ones(bench, table):
    d = bench.declarations
    declared = {frozenset(i["parts"]) for i in d["interfaces"]}
    free = set(d["free_parts"])
    intended = {frozenset(o["parts"]) for o in d["intended_overlaps"]}
    assert table.stats["states"]["unknown"] == 0
    for iface in d["interfaces"]:
        assert table.get(*iface["parts"]).in_contact, f"{iface['id']} not realised"
    for rel in table.contacts():
        pair = frozenset((rel.a, rel.b))
        assert pair in declared or pair & free, f"undeclared contact {rel.a}-{rel.b}"
        if rel.state == "overlapping":
            assert pair in intended, f"undeclared overlap {rel.a}-{rel.b}: {rel.overlap_mm3} mm3"
    names = set(bench.assembly.names)
    for i in d["interfaces"]:
        assert set(i["parts"]) <= names


def test_clean_bench_every_ball_is_inside_the_cavity(bench):
    cavity = bench.cavities["hopper_cavity"]
    for name in bench.declarations["contains"][0]["what"]:
        rel = relate(bench.shape(name), cavity, names=(name, "hopper_cavity"))
        assert rel.state == "contains" and rel.contained == "a_in_b"


def test_seed_ball_through_wall_shows_volume_outside_the_cavity():
    b = gb.build("ball_through_wall")
    rel = relate(b.shape("ball_7"), b.cavities["hopper_cavity"], names=("ball_7", "hopper_cavity"))
    assert rel.state == "overlapping" and rel.a_outside_b_mm3 > 100
    assert relation_table(b.assembly).get("ball_7", "hopper").state == "overlapping"


def test_seed_bracket_floats_and_hovers_in_the_relation_table():
    floats = relation_table(gb.build("bracket_floats").assembly)
    assert not any(r.in_contact for r in floats.of("bracket"))
    hovers = relation_table(gb.build("bracket_hovers").assembly)
    rel = hovers.get("bracket", "base")
    assert rel.state == "apart" and rel.gap_mm == pytest.approx(0.5)


def test_arm_clears_the_frame_over_its_declared_range_and_not_beyond(bench):
    lo, hi = bench.declarations["joints"][0]["range_deg"]
    first_hit = gb.arm_end_clearance_deg(bench)
    assert hi < first_hit < gb.SEEDS["flap_hits_frame"]["params"]["flap_range_deg"][1]
    for deg in range(int(lo), int(hi) + 1, 5):
        rel = relation_table(gb.arm_pose(bench, deg), only=["arm"]).get("arm", "frame", exact=True)
        assert rel.state == "apart", f"arm meets frame at {deg} deg"
    hit = relation_table(gb.arm_pose(bench, first_hit + 1), only=["arm"]).get("arm", "frame")
    assert hit.state == "overlapping"


def test_dossier_items_hook_carries_shapes_and_declarations(bench):
    items = gb.dossier_items(bench)
    assert set(items["parts"]) == set(bench.assembly.names)
    assert "hopper_cavity" in items["cavities"] and items["grounded"] == ["base"]
    assert items["decisions"][0]["alternatives"]
    assert gb.build("decision_without_alternatives").declarations["decisions"][0]["alternatives"] == []
    steps = gb.build("lid_before_board").declarations["assembly"]
    order = [s["fit"][0] for s in steps]
    assert order.index("lid") < order.index("board")
