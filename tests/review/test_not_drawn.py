"""Components declared not drawn (#722): ``not_drawn()`` in the registry, the ``not_drawn`` table of the geometry
record, the statement ``note_not_drawn`` puts in every gate verdict, the ``cad-agent gates`` summary and the lint.

Most of this needs no CAD kernel: the verdict note and the CLI work on the geometry record as JSON, and ``run_one``
is exercised with the gate functions replaced. The registry round trip and the real gates at the bottom skip without
CadQuery.
"""

from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path

import pytest

from cadagent.cli import main
from cadagent.project import load_project
from cadagent.review.dossier import Registry, RegistryError, join, load_dossier
from cadagent.review.dossier.lint import lint_project
from cadagent.review.gates import run as gr
from cadagent.review.gates.verdict import (NOT_DRAWN_NOTE_ONLY, Check, geometry_digest, not_drawn_of,
                                           not_drawn_summary, note_not_drawn, stale_reason, verdict)

from . import test_dossier_registry as reg_fixture
from .test_dossier_lint import base_geometry, make_project
from .test_gates_cli import FAKE_WORKER

NOT_DRAWN = {"bevel_pinion": {"reason": "sized in analysis/gears.py; no solid yet", "near": ["hopper", "lid"],
                              "declared_at": "cad/build.py:40"},
             "motor_shaft": {"reason": "vendor STEP not imported", "near": [], "declared_at": "cad/build.py:41"}}
SPATIAL = [g for g in gr.GATES if g not in NOT_DRAWN_NOTE_ONLY]


def geometry_with(table=None):
    geo = base_geometry()
    geo["not_drawn"] = copy.deepcopy(NOT_DRAWN if table is None else table)
    return geo


def passing(gate: str):
    return verdict(gate, [Check(f"{gate}:x", "pass", "ok")], assumptions=["a test verdict"])


# ------------------------------------------------------------------------------------------- the declaration

def test_a_declaration_is_recorded_with_its_reason_and_neighbours():
    reg = Registry()
    decl = reg.not_drawn("bevel_pinion", reason="  sized in analysis;\n no solid yet ", near="wheel")
    assert (decl.name, decl.reason, decl.near) == ("bevel_pinion", "sized in analysis; no solid yet", ["wheel"])
    assert decl.where.rpartition(":")[0] == __file__ and len(reg) == 1
    assert reg.not_drawn("shaft", reason="vendor STEP", near=("motor", "plate", "motor")).near == ["motor", "plate"]
    reg.clear()
    assert len(reg) == 0 and not reg.undrawn


@pytest.mark.parametrize("args, kwargs, error", [
    (("bad name",), {"reason": "x"}, "not a valid dossier id"),
    (("pinion",), {"reason": "  "}, "needs a reason"),
    (("pinion",), {"reason": None}, "needs a reason"),
    (("pinion",), {"reason": "x", "near": ["bad name"]}, "not a valid dossier id"),
    (("pinion",), {"reason": "x", "near": 3}, "near is a part name or a list"),
    (("pinion",), {"reason": "x", "near": ["pinion"]}, "cannot be near itself"),
])
def test_a_bad_declaration_is_refused(args, kwargs, error):
    with pytest.raises(RegistryError, match=error):
        Registry().not_drawn(*args, **kwargs)


def test_a_component_declared_twice_is_refused():
    reg = Registry()
    reg.not_drawn("pinion", reason="one")
    with pytest.raises(RegistryError, match="declared twice"):
        reg.not_drawn("pinion", reason="two")


def test_dossier_items_takes_not_drawn_and_refuses_unknown_keys():
    reg = Registry()
    reg.add_build_items({}, {"not_drawn": [{"name": "pinion", "reason": "numbers only", "near": ["wheel"]}]},
                        where="cad/build.py:0")
    assert reg.undrawn["pinion"].near == ["wheel"] and "(not_drawn pinion)" in reg.undrawn["pinion"].where
    for items, error in (({"not_drawn": [{"reason": "x"}]}, "without a 'name'"),
                         ({"not_drawn": [{"name": "p", "reason": "x", "volume": 3}]}, "unknown keys"),
                         ({"not_drawn": [{"name": "p"}]}, "needs a reason")):
        with pytest.raises(RegistryError, match=error):
            Registry().add_build_items({}, items, where="cad/build.py:0")


# ---------------------------------------------------------------------------------------------- the verdict

def test_a_record_without_declarations_leaves_every_verdict_byte_for_byte():
    for record in (base_geometry(), {}, None, {"not_drawn": {}}, {"not_drawn": "nonsense"}):
        for gate in gr.GATES:
            data = passing(gate)
            before = json.dumps(data, indent=2)
            assert note_not_drawn(data, record) is data and json.dumps(data, indent=2) == before
            assert gr.verdict_markdown(data) == gr.verdict_markdown(json.loads(before))
        assert not_drawn_of(record) == [] and not_drawn_summary(not_drawn_of(record)) == ""


@pytest.mark.parametrize("gate", gr.GATES)
def test_every_gate_verdict_names_what_is_not_drawn(gate):
    data = note_not_drawn(passing(gate), geometry_with())
    assert [m["name"] for m in data["not_drawn"]] == ["bevel_pinion", "motor_shaft"]
    assert data["not_drawn"][0] == {"name": "bevel_pinion", "reason": NOT_DRAWN["bevel_pinion"]["reason"],
                                    "near": ["hopper", "lid"]}
    said = data["assumptions"][-1]
    assert "2 components of the design are declared not drawn" in said and "did not see them" in said
    assert "bevel_pinion (near hopper, lid), motor_shaft" in said
    assert data["pass"] is True and data["physical_fit_verified"] is False
    row = [c for c in data["checks"] if c["id"] == f"{gate}:not-drawn"]
    if gate in NOT_DRAWN_NOTE_ONLY:                 # the wall of a drawn part does not depend on an absent one
        assert not row and data["status"] == "pass" and data["counts"] == {"pass": 1, "warn": 0, "fail": 0}
        assert data["findings"] == []
    else:
        assert data["status"] == "warn" and data["counts"] == {"pass": 1, "warn": 1, "fail": 0}
        assert row == data["findings"] and row[0]["status"] == "warn" and row[0]["parts"] == ["hopper", "lid"]
        assert "not in the model: bevel_pinion (near hopper, lid), motor_shaft" in row[0]["message"]
        assert row[0]["evidence"]["not_drawn"] == data["not_drawn"]
    md = gr.verdict_markdown(data)
    assert "## Not in the model" in md and md.index("## Not in the model") < md.index("## Findings")
    assert "| `bevel_pinion` | hopper, lid | sized in analysis/gears.py; no solid yet |" in md
    assert "| `motor_shaft` | - | vendor STEP not imported |" in md
    again = json.dumps(data)
    assert json.dumps(note_not_drawn(data, geometry_with())) == again          # stated once


def test_one_component_reads_in_the_singular():
    data = note_not_drawn(passing("motion"), geometry_with({"pinion": {"reason": "later", "near": ["hopper"]}}))
    assert "1 component of the design is declared not drawn (pinion (near hopper)): this gate did not see it" in \
        data["assumptions"][-1]
    assert "does not cover this component" in data["findings"][0]["message"]
    assert not_drawn_summary(data["not_drawn"]) == ("1 component of the design is declared not drawn, so no gate "
                                                    "saw it: pinion (near hopper)")


def test_a_declaration_never_turns_a_fail_into_anything_else():
    failing = verdict("motion", [Check("motion:x", "fail", "collides")], assumptions=["a"])
    data = note_not_drawn(failing, geometry_with())
    assert (data["pass"], data["status"]) == (False, "fail") and data["counts"] == {"pass": 0, "warn": 1, "fail": 1}
    assert [f["id"] for f in data["findings"]] == ["motion:x", "motion:not-drawn"]
    empty = note_not_drawn(verdict("assembly", [], assumptions=["a"]), geometry_with())
    assert (empty["pass"], empty["status"]) == (False, "fail")            # an empty gate still proves nothing
    assert [f["id"] for f in empty["findings"]] == ["assembly:nothing-checked", "assembly:not-drawn"]


def test_a_declaration_is_part_of_the_geometry_digest_but_not_its_line():
    base, declared = base_geometry(), geometry_with()
    assert geometry_digest(base) != geometry_digest(declared)
    moved = geometry_with()
    moved["not_drawn"]["bevel_pinion"]["declared_at"] = "cad/build.py:99"
    assert geometry_digest(moved) == geometry_digest(declared)
    reworded = geometry_with()
    reworded["not_drawn"]["bevel_pinion"]["near"] = ["hopper"]
    assert geometry_digest(reworded) != geometry_digest(declared)
    bound = gr.bind_inputs(passing("motion"), base)
    assert "components declared not drawn" in stale_reason(bound, declared)     # declared after the gates ran


def test_many_components_are_counted_in_the_summary_line():
    table = {f"part_{i}": {"reason": "later", "near": []} for i in range(5)}
    data = note_not_drawn(passing("motion"), geometry_with(table))
    assert gr._summary(data) == "2 checks, 1 warning(s); 5 not drawn, not seen: part_0, part_1, part_2 and 2 more"
    assert gr._summary(passing("motion")) == "1 checks, 0 warning(s)"


# ------------------------------------------------------------------------------- run_one and cad-agent gates

def _fake_gates(monkeypatch):
    """``run_one`` with the kernel left out: the record is read as JSON and every gate passes one check."""
    from cadagent.review.dossier import registry
    monkeypatch.setattr(registry, "load_geometry",
                        lambda path, shapes=True: types.SimpleNamespace(geometry=json.loads(Path(path).read_text())))
    monkeypatch.setattr(gr, "ADAPTERS", {g: (lambda g: lambda *a: passing(g))(g) for g in gr.GATES})


def _record(geo):
    return {**geo, "out_dir": "exports"}


def test_run_one_writes_the_statement_into_every_gate_file(tmp_path, monkeypatch):
    root = make_project(tmp_path / "p", geometry=_record(geometry_with()), gates=())
    _fake_gates(monkeypatch)
    project = load_project(root)
    for gate in gr.GATES:
        gr.run_one(project, gate, no_cache=True)
        data = json.loads((root / "exports" / "gates" / f"{gate}.json").read_text())
        assert len(data["not_drawn"]) == 2 and data["pass"] is True
        assert data["status"] == ("pass" if gate in NOT_DRAWN_NOTE_ONLY else "warn"), gate
        assert stale_reason(data, json.loads((root / "exports" / "dossier-geometry.json").read_text())) is None
        assert "## Not in the model" in (root / "exports" / "gates" / f"{gate}.md").read_text()
    rows = {r["name"]: r for r in gr.gate_rows(project)}                 # cad-agent check and the report
    assert rows["gate connectivity"]["status"] == "pass"
    assert "2 not drawn, not seen: bevel_pinion (near hopper, lid), motor_shaft" in rows["gate connectivity"]["message"]


def test_run_one_without_declarations_writes_what_it_wrote_before(tmp_path, monkeypatch):
    root = make_project(tmp_path / "p", geometry=_record(base_geometry()), gates=())
    _fake_gates(monkeypatch)
    project = load_project(root)
    record = json.loads((root / "exports" / "dossier-geometry.json").read_text())
    cfg = gr.gates_config(project)
    for gate in gr.GATES:
        gr.run_one(project, gate, no_cache=True)
        expected = gr.bind_inputs(passing(gate), record, record_file="exports/dossier-geometry.json",
                                  **gr.expected_inputs(gate, cfg, gr.load_dossier(project), {}))
        assert (root / "exports" / "gates" / f"{gate}.json").read_text() == json.dumps(expected, indent=2) + "\n"
        assert "Not in the model" not in (root / "exports" / "gates" / f"{gate}.md").read_text()


@pytest.fixture
def cli_project(tmp_path, monkeypatch):
    def make(geometry):
        root = make_project(tmp_path / "p", geometry=geometry, gates=())
        script = tmp_path / "fake_worker.py"
        script.write_text(FAKE_WORKER)
        monkeypatch.setattr(gr, "worker_command", lambda r, g, no_cache=False: [sys.executable, str(script), str(r), g])
        return root
    return make


def test_the_gates_summary_says_what_is_not_in_the_model(cli_project, capsys, monkeypatch):
    root = cli_project(geometry_with())
    assert main(["gates", "--project", str(root)]) == 0                # a declaration alone fails nothing
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("not in the model:"))
    assert "2 components of the design are declared not drawn, so no gate saw them: bevel_pinion (near hopper, " \
           "lid), motor_shaft" in line and "does not cover what is not drawn" in line
    assert out.index("gates: ") < out.index("not in the model:")
    assert main(["gates", "--project", str(root), "--dry-run"]) == 0
    assert "not in the model: 2 components" in capsys.readouterr().out
    monkeypatch.setenv("FAKE_GATE_MODE", "crash")                      # a gate that died still names them
    monkeypatch.setenv("FAKE_GATE_TARGET", "connectivity")
    assert main(["gates", "--project", str(root)]) == 1
    crashed = json.loads((root / "exports" / "gates" / "connectivity.json").read_text())
    assert crashed["pass"] is False and len(crashed["not_drawn"]) == 2
    assert "2 not drawn, not seen" in capsys.readouterr().out


def test_the_gates_summary_is_unchanged_without_declarations(cli_project, capsys):
    root = cli_project(None)
    assert main(["gates", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "not in the model" not in out and "not drawn" not in out
    assert main(["gates", "--project", str(root), "--dry-run"]) == 0
    assert "not in the model" not in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------- the lint

def test_the_lint_lists_each_component_as_a_warning_on_its_neighbours(tmp_path):
    root = make_project(tmp_path, geometry=geometry_with())
    res = lint_project(load_project(root))
    found = [f for f in res.warnings if f.code == "not-drawn"]
    assert res.passed and len(found) == 2, [f.code for f in res.errors]
    pinion = next(f for f in found if "'bevel_pinion'" in f.message)
    assert set(pinion.parts) == {"hopper", "lid"} and pinion.where.file == "cad/build.py" and pinion.where.line == 40
    assert "No gate saw it" in pinion.message and "sized in analysis/gears.py" in pinion.message
    assert not [f for f in lint_project(load_project(make_project(tmp_path / "q"))).warnings if f.code == "not-drawn"]


def test_the_join_refuses_a_neighbour_that_is_not_a_part(tmp_path):
    root = make_project(tmp_path)
    geo = geometry_with({"pinion": {"reason": "later", "near": ["ghost"], "declared_at": "cad/build.py:7"}})
    issues = join(load_dossier(root / "dossier" / "project.yaml", strict=False), geo)
    assert [(i.code, i.severity) for i in issues if "pinion" in i.message] == [("not-drawn", "warning"),
                                                                              ("unknown-part", "error")]


# ------------------------------------------------------------------------------ the build and the real gates

DECLARED = reg_fixture.BUILD.replace(
    "from cadagent.review.dossier import Axis, part, cavity, joint, fastener, assembly",
    "from cadagent.review.dossier import Axis, part, cavity, joint, fastener, assembly, not_drawn") + (
    '\nnot_drawn("flap_spring", reason="sized in analysis/spring.py; no solid yet", near=("hopper_flap", "hopper"))\n'
    'not_drawn("vent_plug", reason="bought part, model not imported")\n')


def test_a_build_carries_the_declarations_into_the_record_and_back(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module, load_geometry
    plain = build_module(reg_fixture.make_project(tmp_path / "plain") / "cad" / "build.py")
    assert "not_drawn" not in plain.geometry and '"not_drawn"' not in plain.path.read_text()
    root = reg_fixture.make_project(tmp_path / "declared", build=DECLARED)
    result = build_module(root / "cad" / "build.py", root=root)
    table = result.geometry["not_drawn"]
    assert list(table) == ["flap_spring", "vent_plug"]
    assert table["flap_spring"]["near"] == ["hopper_flap", "hopper"] and table["vent_plug"]["near"] == []
    assert table["flap_spring"]["declared_at"].startswith("cad/build.py:")
    assert "flap_spring" not in result.parts and "flap_spring" not in result.assembly_shapes()   # no geometry at all
    back = load_geometry(result.path, shapes=False)
    assert back.geometry["not_drawn"] == table
    assert not_drawn_of(back.geometry) == [
        {"name": "flap_spring", "reason": "sized in analysis/spring.py; no solid yet",
         "near": ["hopper_flap", "hopper"]},
        {"name": "vent_plug", "reason": "bought part, model not imported", "near": []}]
    assert set(result.geometry) - set(plain.geometry) == {"not_drawn"}          # one new key, nothing else moved
    assert {k: v["sha256"] for k, v in result.geometry["parts"].items()} == \
        {k: v["sha256"] for k, v in plain.geometry["parts"].items()}
    issues = join(load_dossier(root / "dossier" / "project.yaml", strict=False), result)
    assert sorted(i.message.split("'")[1] for i in issues if i.code == "not-drawn") == ["flap_spring", "vent_plug"]


@pytest.mark.parametrize("line, error", [
    ('not_drawn("hopper", reason="x")', "also a registered part"),
    ('not_drawn("hopper_cavity", reason="x")', "also a registered cavity"),
    ('not_drawn("spring", reason="x", near=["ghost"])', "which no part registers"),
])
def test_a_build_refuses_a_declaration_that_contradicts_the_parts(tmp_path, line, error):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    root = reg_fixture.make_project(tmp_path, build=DECLARED + line + "\n")
    with pytest.raises(RegistryError, match=error):
        build_module(root / "cad" / "build.py", root=root)


def test_the_real_gates_warn_on_a_build_with_a_declared_omission(tmp_path, capsys):
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    root = reg_fixture.make_project(tmp_path, build=DECLARED)
    (root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  dossier: dossier/project.yaml\n"
                                         "  gates:\n    build: cad/build.py\n")
    main(["gates", "--project", str(root), "--build", "--only", "connectivity", "motion", "assembly", "--jobs", "3"])
    out = capsys.readouterr().out
    assert "not in the model: 2 components of the design are declared not drawn" in out
    for gate in ("connectivity", "motion", "assembly"):
        data = json.loads((root / "exports" / "gates" / f"{gate}.json").read_text())
        assert all(c["id"] != f"{gate}:run" for c in data["checks"]), (gate, data["findings"])   # the gate ran
        row = next(c for c in data["checks"] if c["id"] == f"{gate}:not-drawn")
        assert row["status"] == "warn" and row["parts"] == ["hopper", "hopper_flap"]
        assert data["status"] != "pass" and [m["name"] for m in data["not_drawn"]] == ["flap_spring", "vent_plug"]
        assert "## Not in the model" in (root / "exports" / "gates" / f"{gate}.md").read_text()
