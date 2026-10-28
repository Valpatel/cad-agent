"""The design dossier's schema and loader (plan T1): round trip, unknown keys, ids with file and line."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from cadagent.dossier import DossierError, dump_yaml, load_dossier, load_project_dossier
from cadagent.project import load_project

# The part spec card example from docs/design-process-plan.md §3.2, verbatim.
HOPPER = textwrap.dedent("""\
    # dossier/sections/hopper.yaml  (one file per section; parts are nested, or `parts: [file.yaml]` to split)
    id: S3
    title: Hopper and feed
    purpose: Hold 40 foam balls and present one at a time to the feed wheel
    requirements: [R4, R7, R12]
    parts:
      - id: hopper
        function: Contain the ball store and funnel balls to the feed throat under gravity
        interfaces: [I7, I8, I9]
        loads: {static: "40 balls, 0.26 kg, on the floor cone", shock: "1 m drop on a corner (R12)"}
        material: {name: PETG, process: FDM, print_axis: "+Z", wall_mm: 2.4}
        fasteners: [{to: pan_base, screws: screw_m3x8, qty: 4, via: I7}]
        contains: [{what: ball, count: 40, cavity: hopper_cavity, free: true}]     # drives the containment gate
        decisions:
          - id: D41
            decision: Single-wall cone with a 55° floor
            why: Balls roll at 35°; 55° clears the feed throat without a stirrer
            alternatives:
              - {option: Stirrer paddle, rejected: adds a motor and a jam mode (DFMEA F3)}
              - {option: Vibrating floor, rejected: no evidence it clears 40 mm foam balls}
        checks: [gate:containment, gate:connectivity, fea:hopper-drop, print:hopper]
        status: reviewed          # draft | built | gated | reviewed | signed_off
    """)

BASE = textwrap.dedent("""\
    id: S1
    title: Base
    purpose: Carry the pan and everything on it
    requirements: [R12]
    interfaces:
      - {id: I7, between: [hopper, pan_base], kind: fastened, datum: pan top face, fastened_by: screw_m3x8, owner: S1}
    parts:
      - id: pan_base
        function: Rotating plate the hopper bolts to
        interfaces: [I7]
        decisions:
          - {id: D10, decision: Flat plate, why: simplest, alternatives: [{option: Ribbed plate, rejected: not needed}]}
      - parts/ball.yaml
    """)

BALL = textwrap.dedent("""\
    id: ball
    function: Loose ammunition
    interfaces: [I8]
    """)

FLAP = textwrap.dedent("""\
    id: S4
    title: Flap
    interfaces:
      - {id: I9, between: [hopper_flap, hopper], kind: revolute, datum: pivot axis, owner: S4}
    parts:
      - {id: hopper_flap, function: Closes the throat, interfaces: [I9]}
    """)

PROJECT = textwrap.dedent("""\
    title: Test assembly
    requirements:
      - {id: R4, text: Holds 40 balls, source: {kind: user, quote: "it has to hold forty"}, verify_by: inspection}
      - {id: R7, text: Feeds one at a time, verify_by: demo}
      - {id: R12, text: Survives a 1 m drop, verify_by: analysis, checks: [fea:hopper-drop]}
    sections: [sections/base.yaml, sections/hopper.yaml, sections/flap.yaml]
    interfaces:
      - {id: I8, between: [hopper, ball], kind: contact, datum: cone floor}
    decisions: decisions.yaml
    assembly:
      steps:
        - {order: 1, fit: pan_base, onto: hopper, direction: -Z, tool: hex_2.5, fasteners: [screw_m3x8]}
        - {order: 2, fit: hopper_flap, onto: [hopper], direction: [0, 1, 0]}
    gates:
      grounded: [pan_base]
      free_parts: [{part: ball, reason: loose in the hopper}]
      intended_overlaps: [{parts: [hopper, pan_base], reason: heat-set inserts}]
      touch_tol_mm: 0.02
    """)

DECISIONS = textwrap.dedent("""\
    - id: D1
      date: 2026-10-27
      title: Print in PETG
      decision: PETG for every printed part
      why: tougher than PLA
      status: decided
      source: {kind: user, quote: "use PETG"}
      alternatives: [PLA, ASA]
    - {id: D2, decision: Feed from above, why: gravity, scope: section, section: S3, author: agent-7}
    """)


def write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root / "dossier" / "project.yaml"


def files(override=None):
    base = {"dossier/project.yaml": PROJECT, "dossier/sections/hopper.yaml": HOPPER,
            "dossier/sections/base.yaml": BASE, "dossier/sections/flap.yaml": FLAP,
            "dossier/parts/ball.yaml": BALL, "dossier/decisions.yaml": DECISIONS}
    base.update(override or {})
    return base


@pytest.fixture
def dossier_path(tmp_path):
    return write(tmp_path, files())


def test_plan_example_round_trips(dossier_path):
    d = load_dossier(dossier_path)
    section = d.sections["S3"]
    assert section.to_dict() == yaml.safe_load(HOPPER)
    assert yaml.safe_load(dump_yaml(section.to_dict())) == yaml.safe_load(HOPPER)
    card = d.parts["hopper"]
    assert card.material.wall_mm == 2.4 and card.contains[0].free is True and card.contains[0].count == 40
    assert card.fasteners[0].qty == 4 and card.status == "reviewed"
    d41 = d.decisions["D41"]
    assert (d41.scope, d41.section, d41.part) == ("part", "S3", "hopper")
    assert [a.rejected for a in d41.alternatives][0].startswith("adds a motor")
    assert d.findings == [] and d.errors == []


def test_whole_dossier_resolves(dossier_path):
    d = load_dossier(dossier_path)
    assert list(d.sections) == ["S1", "S3", "S4"]
    assert set(d.parts) == {"pan_base", "ball", "hopper", "hopper_flap"}
    assert d.section_of("ball").id == "S1" and d.parts["ball"].file == "parts/ball.yaml"
    assert d.sections["S1"].to_dict()["parts"][1] == "parts/ball.yaml"
    assert d.interfaces["I8"].section == "" and d.interfaces["I7"].owner == "S1"
    assert d.requirements["R4"].source.quote == "it has to hold forty"
    assert [s.order for s in d.assembly] == [1, 2]
    assert d.assembly[0].onto == ["hopper"] and d.assembly[1].direction == [0, 1, 0]
    assert d.assembly[0].to_dict()["onto"] == "hopper"
    g = d.gates
    assert g.grounded == ["pan_base"] and g.free_parts[0].reason == "loose in the hopper"
    assert g.intended_overlaps[0].parts == ("hopper", "pan_base") and g.touch_tol_mm == 0.02
    assert g.motion_samples == 12
    # decisions.yaml in the site's format: string alternatives load without a reason and dump back as strings
    d1 = d.decisions["D1"]
    assert d1.scope == "project" and [a.option for a in d1.alternatives] == ["PLA", "ASA"]
    assert all(a.rejected is None for a in d1.alternatives) and d1.to_dict()["alternatives"] == ["PLA", "ASA"]
    assert d.decisions["D2"].scope == "section" and d.decisions["D2"].author == "agent-7"
    assert d.kind_of("I9") == "interface" and d.kind_of("nope") is None


def test_unknown_keys_are_reported_with_lines(tmp_path):
    hopper = HOPPER.replace("    status: reviewed", "    colour: red\n    status: reviewed")
    project = PROJECT.replace("title: Test assembly", "title: Test assembly\nowner_name: x").replace(
        "touch_tol_mm: 0.02", "touch_tol_mm: 0.02\n  new_gate_option: 3")
    d = load_dossier(write(tmp_path, files({"dossier/sections/hopper.yaml": hopper, "dossier/project.yaml": project})))
    found = {(f.where.file, f.where.line, f.message.split(" in ")[0]) for f in d.findings}
    line = hopper.splitlines().index("    colour: red") + 1
    assert ("dossier/sections/hopper.yaml", line, "unknown key 'colour'") in found
    assert ("dossier/project.yaml", 2, "unknown key 'owner_name'") in found
    assert any("new_gate_option" in f.message for f in d.findings)
    assert d.gates.extra == {"new_gate_option": 3}
    assert all(f.severity == "warning" and f.code == "unknown-key" for f in d.findings)


def _error(tmp_path, override) -> DossierError:
    with pytest.raises(DossierError) as exc:
        load_dossier(write(tmp_path, files(override)))
    return exc.value


def test_malformed_id_raises_with_file_and_line(tmp_path):
    hopper = HOPPER.replace("  - id: hopper", "  - id: 3hopper")
    err = _error(tmp_path, {"dossier/sections/hopper.yaml": hopper})
    first = err.issues[0]
    assert first.code == "bad-id" and "3hopper" in first.message
    assert (err.file, err.line) == ("dossier/sections/hopper.yaml", 7)
    assert str(err).startswith("") and "dossier/sections/hopper.yaml:7" in str(err)


def test_dangling_reference_raises_with_file_and_line(tmp_path):
    hopper = HOPPER.replace("requirements: [R4, R7, R12]", "requirements: [R4, R99, R12]")
    err = _error(tmp_path, {"dossier/sections/hopper.yaml": hopper})
    assert [i.code for i in err.issues] == ["unknown-id"]
    assert (err.file, err.line) == ("dossier/sections/hopper.yaml", 5)
    assert "R99" in str(err) and "requirement" in str(err)


def test_reference_to_wrong_kind_says_what_it_is(tmp_path):
    hopper = HOPPER.replace("interfaces: [I7, I8, I9]", "interfaces: [I7, I8, R4]")
    err = _error(tmp_path, {"dossier/sections/hopper.yaml": hopper})
    assert "(it is a requirement)" in str(err) and err.line == 9


def test_non_strict_collects_every_error(tmp_path):
    hopper = HOPPER.replace("requirements: [R4, R7, R12]", "requirements: [R4, R98, R99]").replace(
        "to: pan_base", "to: nowhere")
    d = load_dossier(write(tmp_path, files({"dossier/sections/hopper.yaml": hopper})), strict=False)
    assert sorted(i.message.split("'")[1] for i in d.errors) == ["R98", "R99", "nowhere"]
    assert all(i.where.file == "dossier/sections/hopper.yaml" for i in d.errors)


def test_duplicate_ids_across_kinds(tmp_path):
    flap = FLAP.replace("id: hopper_flap", "id: R4")
    err = _error(tmp_path, {"dossier/sections/flap.yaml": flap})
    assert any(i.code == "duplicate-id" and "requirement" in i.message for i in err.issues)
    assert err.issues[0].where.file == "dossier/sections/flap.yaml"


def test_duplicate_yaml_key_and_invalid_yaml(tmp_path):
    err = _error(tmp_path, {"dossier/parts/ball.yaml": "id: ball\nfunction: a\nfunction: b\n"})
    assert err.issues[0].code == "duplicate-key" and (err.file, err.line) == ("dossier/parts/ball.yaml", 3)
    err = _error(tmp_path, {"dossier/parts/ball.yaml": "id: ball\nfunction: [unclosed\n"})
    assert err.issues[0].code == "yaml" and err.file == "dossier/parts/ball.yaml" and err.line > 0
    assert len(err.issues) == 1     # ids in a file that failed to load do not cascade into unknown-id errors


def test_type_and_value_errors(tmp_path):
    hopper = (HOPPER.replace("qty: 4", "qty: four").replace("status: reviewed ", "status: done ")
              .replace("wall_mm: 2.4", "wall_mm: -1"))
    err = _error(tmp_path, {"dossier/sections/hopper.yaml": hopper})
    messages = " | ".join(i.message for i in err.issues)
    assert "qty must be an integer" in messages and "status is 'done'" in messages and "wall_mm must be > 0" in messages


def test_interface_needs_two_parties_and_directions_are_checked(tmp_path):
    flap = FLAP.replace("between: [hopper_flap, hopper]", "between: [hopper_flap]")
    project = PROJECT.replace("direction: -Z", "direction: down")
    err = _error(tmp_path, {"dossier/sections/flap.yaml": flap, "dossier/project.yaml": project})
    codes = {i.code for i in err.issues}
    assert {"bad-interface", "bad-value"} <= codes


def test_interface_declared_by_both_sides(tmp_path):
    hopper = HOPPER.replace("parts:\n", "interfaces:\n  - {id: I7, between: [pan_base, hopper], kind: fastened, "
                                        "datum: hopper flange, owner: S1}\nparts:\n", 1)
    d = load_dossier(write(tmp_path, files({"dossier/sections/hopper.yaml": hopper})))
    assert d.interfaces["I7"].section == "S1"            # the owner's declaration is the reference
    assert len(d.interface_declarations["I7"]) == 2
    conflict = [f for f in d.findings if f.code == "interface-conflict"]
    assert len(conflict) == 1 and "datum" in conflict[0].message and "between" not in conflict[0].message


def test_decision_scope_must_match_target(tmp_path):
    decisions = DECISIONS + "- {id: D3, decision: x, scope: part}\n"
    err = _error(tmp_path, {"dossier/decisions.yaml": decisions})
    assert err.issues[0].code == "bad-scope" and err.line == 10


def test_sections_glob_and_inline(tmp_path):
    project = PROJECT.replace("sections: [sections/base.yaml, sections/hopper.yaml, sections/flap.yaml]",
                              "sections: [\"sections/*.yaml\"]")
    d = load_dossier(write(tmp_path, files({"dossier/project.yaml": project})))
    assert list(d.sections) == ["S1", "S4", "S3"]      # base, flap, hopper: sorted file names
    missing = PROJECT.replace("sections/flap.yaml]", "sections/nope.yaml]")
    err = _error(tmp_path, {"dossier/project.yaml": missing})
    assert err.issues[0].code == "missing-file" and err.file == "dossier/project.yaml"


def test_cad_agent_yaml_dossier_key(tmp_path):
    write(tmp_path, files())
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: t\n  dossier: dossier/project.yaml\n")
    project = load_project(tmp_path)
    assert project.dossier == tmp_path.resolve() / "dossier" / "project.yaml" and project.unknown_keys == []
    d = load_project_dossier(project)
    assert d.file == "dossier/project.yaml" and "S3" in d.sections
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: t\n")
    assert load_project_dossier(load_project(tmp_path)) is None


# ------------------------------------------------------------------------------- review #26 regressions

def test_empty_section_or_part_file_is_an_error_at_the_reference(tmp_path):
    err = _error(tmp_path, {"dossier/sections/flap.yaml": "# to do\n"})
    assert [i.code for i in err.issues] == ["empty-file"]
    assert (err.file, err.line) == ("dossier/project.yaml", 6) and "dossier/sections/flap.yaml is empty" in str(err)
    err = _error(tmp_path, {"dossier/sections/flap.yaml": FLAP, "dossier/parts/ball.yaml": ""})
    assert [i.code for i in err.issues] == ["empty-file"]
    assert (err.file, err.line) == ("dossier/sections/base.yaml", 13) and "parts/ball.yaml" in str(err)


def test_empty_project_file_names_the_file(tmp_path):
    err = _error(tmp_path, {"dossier/project.yaml": ""})
    assert (err.file, err.line) == ("dossier/project.yaml", 1) and "0 dossier errors" not in str(err)
    assert "is empty" in str(err)


def test_non_scalar_key_reports_file_and_line(tmp_path):
    err = _error(tmp_path, {"dossier/project.yaml": "title: t\n? [a, b]\n: c\n"})
    assert err.issues[0].code == "bad-key" and (err.file, err.line) == ("dossier/project.yaml", 2)


def test_gate_exemptions_need_a_reason(tmp_path):
    project = PROJECT.replace("free_parts: [{part: ball, reason: loose in the hopper}]", "free_parts: [ball]")
    err = _error(tmp_path, {"dossier/project.yaml": project})
    assert [i.code for i in err.issues] == ["missing-reason"] and err.line == 16
    project = PROJECT.replace("reason: heat-set inserts", "reason: '  '")
    err = _error(tmp_path, {"dossier/project.yaml": project})
    assert [i.code for i in err.issues] == ["missing-reason"] and "intended_overlaps" in str(err)


def test_duplicate_card_does_not_cascade_from_its_decisions(tmp_path):
    # the dropped duplicate's nested decision D99 is not read, so the real D99 elsewhere is not a second duplicate
    flap = FLAP + "  - {id: hopper_flap, function: again, decisions: [{id: D99, decision: x}]}\n"
    project = PROJECT.replace("decisions: decisions.yaml", "decisions:\n  - {id: D99, decision: y}")
    err = _error(tmp_path, {"dossier/sections/flap.yaml": flap, "dossier/project.yaml": project})
    assert [(i.code, i.message.split("'")[1]) for i in err.issues] == [("duplicate-id", "hopper_flap")]


def test_fastener_entries_carry_their_line(dossier_path):
    use = load_dossier(dossier_path).parts["hopper"].fasteners[0]
    assert (use.where.file, use.where.line) == ("dossier/sections/hopper.yaml", 12)
    assert "where" not in use.to_dict()


def test_evidence_shape_content_hash():
    cq = pytest.importorskip("cadquery")
    from cadagent.evidence import brep_content_hash, shape_brep_text, shape_content_hash
    box = cq.Workplane().box(10, 20, 30).edges("|Z").fillet(2).val()
    h = shape_content_hash(box)
    box.tessellate(0.1)
    box.isValid()
    assert shape_content_hash(box) == h == brep_content_hash(shape_brep_text(box))
    assert shape_content_hash(box.moved(cq.Location(cq.Vector(0, 0, 1e-3)))) != h
    flagged = shape_brep_text(box).replace(b"\n0101000\n", b"\n0111000\n")    # the kernel's "checked" bit
    assert flagged != shape_brep_text(box) and brep_content_hash(flagged) == h


def test_gate_exemptions_take_instance_keys_and_fastener_names(tmp_path):
    # #56: a party may be a part, an instance of one, or a fastener the build registers (the lint checks those)
    pairs = ("intended_overlaps: [{parts: [hopper, pan_base], reason: heat-set inserts},\n"
             "                        {parts: [screw_0, insert_0], reason: thread envelope},\n"
             "                        {parts: ['m3:lid-base#1', 'ball#3'], reason: by instance}]\n"
             "  ignore_pairs: [{parts: [screw_1, hopper_flap], reason: shown open only}]")
    project = PROJECT.replace("intended_overlaps: [{parts: [hopper, pan_base], reason: heat-set inserts}]", pairs)
    d = load_dossier(write(tmp_path, files({"dossier/project.yaml": project})))
    assert [p.parts for p in d.gates.intended_overlaps] == [("hopper", "pan_base"), ("screw_0", "insert_0"),
                                                            ("m3:lid-base#1", "ball#3")]
    assert d.gates.ignore_pairs[0].parts == ("screw_1", "hopper_flap") and d.gates.ignore_pairs[0].where.line >= 1
    assert d.gates.intended_overlaps[1].to_dict() == {"parts": ["screw_0", "insert_0"], "reason": "thread envelope"}


@pytest.mark.parametrize("parties, message", [
    ("[R4, hopper]", "which is not a part, part instance or fastener in this dossier (it is a requirement)"),
    ("['S3#2', hopper]", "names 'S3', which is not a part, part instance or fastener in this dossier (it is a section)"),
    ("[hopper, hopper]", "names 'hopper' twice"),
])
def test_gate_exemption_parties_that_cannot_be_right(tmp_path, parties, message):
    project = PROJECT.replace("parts: [hopper, pan_base], reason: heat-set inserts",
                              f"parts: {parties}, reason: heat-set inserts")
    err = _error(tmp_path, {"dossier/project.yaml": project})
    assert message in str(err) and err.file == "dossier/project.yaml", str(err)
