"""Rigid modules must pass their own sequence before they enter a different surrounding assembly."""
import pytest

from cadagent.gates.assembly import AccessOptions, assembly_gate, run_sequence, steps_markdown
from cadagent.gates.fasteners import FastenerSpec
from cadagent.gates.relations import Assembly, Relation
from tests.test_gate_assembly import BoxWorld


class RecordingWorld(BoxWorld):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_parties = {}

    def tool(self, spec, *args, **kwargs):
        self.original_parties[spec.name] = (spec.clamps, spec.into, list(spec.stack))
        return super().tool(spec, *args, **kwargs)


def fixture():
    boxes = {"base": (-1, 0, 0, 0, 3, 3), "carrier": (2, 0, 0, 3, 3, 3), "board": (1, 0, 0, 2, 3, 3),
             "board_screw": (.8, -.15, .75, 2.5, .35, 1.25), "retainer": (-.5, 1.9, 1.9, 3.2, 2.1, 2.1),
             "bumper": (4, 0, 0, 5, 3, 3)}
    specs = {
        "board_screw": FastenerSpec("board_screw", "board", "carrier", axes=[((1, .1, 1), (1, 0, 0))],
                                    tool="hex", head_h_mm=.2),
        "retainer": FastenerSpec("retainer", "carrier", "base", axes=[((3, 2, 2), (-1, 0, 0))],
                                 tool="hex", head_h_mm=.2),
    }
    module = {"electronics": {"members": ["carrier", "board", "board_screw"], "steps": [
        {"order": 1, "fit": "carrier", "direction": "-Z"},
        {"order": 2, "fit": "board", "onto": "carrier", "direction": "+X", "fasteners": ["board_screw"]},
    ]}}
    steps = [{"order": 1, "fit": "base", "direction": "-Z"},
             {"order": 2, "fit": "electronics", "onto": "base", "direction": "-X", "fasteners": ["retainer"]},
             {"order": 3, "fit": "bumper", "onto": "base", "direction": "-Z"}]
    return boxes, specs, module, steps


def execute(boxes=None, specs=None, modules=None, steps=None, **kwargs):
    b, f, m, s = fixture()
    world = kwargs.pop("world", None) or RecordingWorld(boxes or b)
    result = run_sequence(world, s if steps is None else steps, f if specs is None else specs,
                          subassemblies=m if modules is None else modules,
                          tools={"hex": {"envelope_d": .2, "length": 10}}, **kwargs)
    return result, world


def failures(result):
    return [c for c in result["checks"] if c.status == "fail"]


def test_internal_tools_are_checked_off_parent_and_external_tools_keep_real_parties():
    result, world = execute(service_after={"electronics": ["bumper", "retainer"]})
    assert not failures(result), [(c.id, c.message) for c in failures(result)]
    calls = {c[0]: c for c in world.tool_calls}
    assert set(calls) == {"board_screw", "retainer"}  # internal screws are not re-driven in the parent
    assert set(calls["board_screw"][2]) == {"carrier", "board", "board_screw"}
    assert set(calls["retainer"][2]) == {"base", "carrier", "board", "board_screw", "retainer"}
    assert world.original_parties["retainer"] == ("carrier", "base", ["carrier"])
    assert {c.id for c in result["checks"] if c.id.startswith("cover:")} == {
        "cover:base", "cover:electronics", "cover:bumper", "cover:retainer"}
    evidence = result["service_after"]["electronics"]
    assert evidence["status"] == "pass" and evidence["withdrawal_direction"] == [1, 0, 0]
    assert evidence["prerequisite_removal_verified"] is False
    assert evidence["prerequisite_tool_access_verified"] is False
    assert "board_screw" in evidence["members"] and "board_screw" not in evidence["assumed_removed"]


@pytest.mark.parametrize("mutation, expected", [
    (lambda b,f,m,s: m["electronics"]["members"].append("missing"), "unknown member"),
    (lambda b,f,m,s: m["electronics"]["members"].append("board"), "duplicate or shared"),
    (lambda b,f,m,s: m.update(other={"members": ["board"], "steps": []}), "duplicate or shared"),
    (lambda b,f,m,s: m["electronics"]["members"].remove("board_screw"), "every attached solid"),
    (lambda b,f,m,s: m["electronics"]["members"].append("retainer"), "external retainer"),
    (lambda b,f,m,s: m["electronics"]["steps"].pop(), "fitted exactly once"),
    (lambda b,f,m,s: m["electronics"]["steps"][1].update(fasteners=[]), "installed exactly once"),
    (lambda b,f,m,s: m["electronics"]["steps"][1].update(direction=""), "direction is required"),
    (lambda b,f,m,s: s.append({"order": 4,"fit":"board","direction":"+X"}), "not a part"),
    (lambda b,f,m,s: s.append({"order": 4,"fit":"electronics","direction":"-X"}), "fitted exactly once"),
    (lambda b,f,m,s: m["electronics"].update(subassemblies={}), "exactly members and steps"),
    (lambda b,f,m,s: m.update(base=m.pop("electronics")), "ambiguous subassembly name"),
    (lambda b,f,m,s: m.update(**{"electronics#0":m.pop("electronics")}), "ambiguous subassembly name"),
    (lambda b,f,m,s: f["board_screw"].axes.append(((1, 2, 1), (1, 0, 0))), "every attached solid"),
])
def test_bad_structure_is_rejected_before_geometry(mutation, expected):
    boxes, specs, modules, steps = fixture()
    mutation(boxes, specs, modules, steps)
    result, world = execute(boxes, specs, modules, steps)
    assert len(failures(result)) == 1 and expected in failures(result)[0].message
    assert world.queries == 0 and not world.tool_calls and result["steps"] == []


@pytest.mark.parametrize("removed, expected", [
    (["bumper"], "retaining fasteners remain"),
    (["bumper", "retainer", "retainer"], "duplicate"),
    (["bumper", "retainer", "board_screw"], "target-member"),
    (["missing", "retainer"], "unknown"),
])
def test_service_prerequisites_fail_closed_before_geometry(removed, expected):
    result, world = execute(service_after={"electronics": removed})
    assert expected in failures(result)[0].message and world.queries == 0


def test_module_service_cannot_be_silently_skipped_by_ordinary_service_mode():
    result, world = execute(service=["electronics"])
    assert failures(result)[0].id == "subassemblies:service" and world.queries == 0


@pytest.mark.parametrize("service_after", [[], False, {"missing": []}])
def test_service_declaration_requires_a_mapping_of_known_modules(service_after):
    result, world = execute(service_after=service_after)
    assert failures(result) and world.queries == 0 and world.tool_calls == []


def test_internal_tool_failure_stops_parent():
    boxes, *_ = fixture()
    world = RecordingWorld(boxes, tools={"board_screw": {"blocked": [{"part": "carrier"}], "clear": False}})
    result, _ = execute(world=world)
    assert any(c.id == "subassembly:electronics:qualified" for c in failures(result))
    assert result["steps"] == [] and {c[0] for c in world.tool_calls} == {"board_screw"}


def test_scoped_qualification_cannot_disable_internal_or_external_tool_checks():
    result, world = execute(options=AccessOptions(tool_access=False))
    assert "requires internal and parent tool access" in failures(result)[0].message
    assert world.queries == 0 and world.tool_calls == []


def test_internal_insertion_failure_cannot_be_hidden_by_the_parent_group():
    boxes, specs, modules, steps = fixture()
    modules["electronics"]["steps"][1]["direction"] = "-X"  # board would pass through carrier
    result, _ = execute(boxes, specs, modules, steps)
    assert any(c.id == "subassembly:electronics:step:2:insert" for c in failures(result))
    assert result["steps"] == [] and result["service_after"] == {}


def test_internal_heat_set_pair_keeps_its_explicit_reason_and_scope():
    boxes, specs, modules, steps = fixture()
    boxes["insert"] = (2.5, 1, 1, 2.8, 1.3, 1.3)
    modules["electronics"]["members"].append("insert")
    modules["electronics"]["steps"][1]["order"] = 3
    modules["electronics"]["steps"].insert(1,{"order":2,"fit":"insert","onto":"carrier","direction":"+X"})
    result, _ = execute(boxes, specs, modules, steps,
                        intended_overlaps=[{"parts":["insert","carrier"],"reason":"declared heat-set interference"}])
    assert not failures(result)
    assert result["exclusions"] == [{"parts":["insert","carrier"],"reason":"declared heat-set interference",
                                     "step":2,"scope":"electronics"}]


def test_catalogue_part_reference_crossing_module_boundaries_is_ambiguous():
    boxes, specs, modules, steps = fixture()
    boxes["board#0"] = boxes.pop("board")
    boxes["board#1"] = (20,0,0,21,3,3)
    modules["electronics"]["members"][1] = "board#0"
    modules["electronics"]["steps"][1]["fit"] = "board#0"
    steps.append({"order":4,"fit":"board#1","direction":"-Z"})
    result, world = execute(boxes, specs, modules, steps)
    assert "ambiguous part reference 'board'" in failures(result)[0].message and world.queries == 0


def test_module_and_attached_screw_both_participate_in_parent_collision():
    boxes, specs, modules, steps = fixture()
    boxes["lip"] = (6, -.14, .95, 7, -.03, 1.05)  # misses board/carrier; catches the screw head
    steps[1]["order"], steps[2]["order"] = 3, 4
    steps.insert(1, {"order": 2,"fit":"lip","direction":"-Z"})
    result, _ = execute(boxes, specs, modules, steps)
    hit = next(c for c in failures(result) if c.id == "step:3:insert")
    assert hit.evidence["near"]["electronics"][0]["member_pair"] == ["board_screw", "lip"]


def test_unknown_member_relation_cannot_be_hidden_by_clear_members():
    class Unknown(RecordingWorld):
        def relate_at(self, key, shift, other):
            if key == "board_screw" and other == "base":
                return Relation(key, other, "unknown", error="seeded kernel failure")
            return super().relate_at(key, shift, other)
    boxes = fixture()[0]
    boxes["base"] = (6, 0, 0, 7, 3, 3)  # force an exact query on the insertion path
    result, _ = execute(world=Unknown(boxes))
    assert any(c.id == "step:2:insert" and "unknown" in c.message for c in failures(result))


def test_conditional_service_checks_later_obstacles_and_earlier_parts():
    result, _ = execute(service_after={"electronics": ["retainer"]})
    assert [c.id for c in failures(result)] == ["service_after:electronics"]
    assert result["service_after"]["electronics"]["blocked"][0]["part"] == "bumper"
    assert "base" in result["service_after"]["electronics"]["remaining"]


def test_blanket_module_and_cross_boundary_overlap_waivers_are_rejected():
    for pair in (["electronics", "base"], ["board", "base"]):
        result, world = execute(intended_overlaps=[{"parts": pair, "reason": "not a valid scope"}])
        assert failures(result) and world.queries == 0


def brep_fixture(blocker=False):
    cq = pytest.importorskip("cadquery")
    boxes, specs, modules, steps = fixture()
    def box(b):
        return cq.Solid.makeBox(b[3]-b[0], b[4]-b[1], b[5]-b[2], cq.Vector(*b[:3]))
    bore = cq.Solid.makeCylinder(.12, 3, cq.Vector(0, .1, 1), cq.Vector(1, 0, 0))
    asm = Assembly()
    for key in ["base", "carrier", "board", "bumper"]:
        shape = box(boxes[key])
        if key in ("carrier", "board"):
            shape = shape.cut(bore)
        asm.add(key, shape)
    screw = cq.Solid.makeCylinder(.1, 1.5, cq.Vector(1,.1,1), cq.Vector(1,0,0)).fuse(
        cq.Solid.makeCylinder(.25,.2,cq.Vector(.8,.1,1),cq.Vector(1,0,0)))
    asm.add("board_screw", screw).kind = "fastener"
    asm.add("retainer", box(boxes["retainer"])).kind = "fastener"
    if blocker:
        asm.add("lip", box((6,-.14,.95,7,-.03,1.05)))
        steps[1]["order"], steps[2]["order"] = 3, 4
        steps.insert(1, {"order":2,"fit":"lip","direction":"-Z"})
    return asm, specs, modules, steps


def test_brep_rigid_module_and_real_tool_scope(tmp_path):
    asm, specs, modules, steps = brep_fixture()
    out = tmp_path / "assembly.json"
    v = assembly_gate(asm, steps, fasteners=specs, subassemblies=modules,
                      tools={"hex":{"envelope_d":.2,"length":10}},
                      service_after={"electronics":["bumper","retainer"]}, out=out)
    assert v["pass"], v["findings"]
    assert "Internal assembly: electronics" in out.with_suffix(".md").read_text()
    assert "Prerequisites are assumed already removed" in steps_markdown(v)
    assert v["physical_fit_verified"] is False
    assert v["limits"]["conditional_service"] is True
    assert v["limits"]["prerequisite_removal_verified"] is False
    # Running the same internal screw's real tool against the parent base fails: scoping is consequential.
    from cadagent.gates.fasteners import tool_access
    tool = tool_access(asm, specs["board_screw"], 0, "hex", {"envelope_d":.2,"length":10},
                       list(asm.names), {"order":2,"fit":"board"})
    assert not tool["clear"] and "base" in {b["part"] for b in tool["blocked"]}


def test_brep_attached_screw_head_blocks_the_whole_module():
    asm, specs, modules, steps = brep_fixture(blocker=True)
    v = assembly_gate(asm, steps, fasteners=specs, subassemblies=modules,
                      tools={"hex":{"envelope_d":.2,"length":10}})
    hits = [c for c in v["checks"] if c["id"] == "step:3:insert"]
    assert len(hits) == 1 and hits[0]["status"] == "fail"
    assert hits[0]["evidence"]["near"]["electronics"][0]["member_pair"] == ["board_screw", "lip"]


def test_brep_external_retainer_tool_is_still_checked_against_real_parent_parts():
    cq = pytest.importorskip("cadquery")
    asm, specs, modules, steps = brep_fixture()
    asm.add("tool_guard", cq.Solid.makeBox(1,.2,.2,cq.Vector(4,3.2,1.9)))
    steps[1]["order"], steps[2]["order"] = 3, 4
    steps.insert(1,{"order":2,"fit":"tool_guard","direction":"-Z"})
    v = assembly_gate(asm, steps, fasteners=specs, subassemblies=modules,
                      tools={"hex":{"envelope_d":3,"length":10}})
    by_id = {c["id"]:c for c in v["checks"]}
    assert by_id["step:3:insert"]["status"] == "pass"
    assert by_id["step:3:tool:retainer"]["status"] == "fail"
    assert "tool_guard" in by_id["step:3:tool:retainer"]["parts"]
    assert by_id["subassembly:electronics:qualified"]["status"] == "pass"


def test_brep_conditional_service_fails_if_the_later_bumper_remains():
    asm, specs, modules, steps = brep_fixture()
    v = assembly_gate(asm, steps, fasteners=specs, subassemblies=modules,
                      tools={"hex":{"envelope_d":.2,"length":10}},
                      service_after={"electronics":["retainer"]})
    assert [c["id"] for c in v["findings"]] == ["service_after:electronics"]
    assert v["service_after"]["electronics"]["blocked"][0]["part"] == "bumper"
