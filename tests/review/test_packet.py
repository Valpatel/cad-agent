"""The section review packet (plan T10, docs/review-packet.md).

The first part needs no CAD kernel: ``plan_packet`` works from a hand-written geometry record, YAML dossier and
verdicts, and ``cad-agent review-packet --list`` plans without rendering. The end of the file renders the gate
bench's sections (needs CadQuery, VTK and Pillow) and checks the images, captions and hashes.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import shutil
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from cadagent.review import packet as pk
from cadagent.cli import main
from cadagent.review.dossier import load_dossier
from cadagent.review.gates.verdict import bind_inputs


def _inst(key, lo, hi, sha, **kw):
    return {"key": key, "sha256": sha, "bbox": {"min": lo, "max": hi}, "volume_mm3": 100.0, **kw}


def record() -> Dict[str, Any]:
    def part(sec, insts, **kw):
        return {"section": sec, "sha256": insts[0]["sha256"][::-1], "count": len(insts), "instances": insts,
                "grounded": False, "free": False, **kw}
    return {
        "schema": "cad-agent.dossier-geometry/1", "actor": "builder",
        "parts": {
            "base": part("S0", [_inst("base", [0, 0, 0], [100, 60, 5], "1" * 64)], grounded=True),
            "far": part("S0", [_inst("far", [500, 500, 0], [510, 510, 10], "2" * 64)]),
            "hopper": part("S1", [_inst("hopper", [10, 10, 5], [50, 50, 45], "3" * 64)]),
            "lid": part("S1", [_inst("lid", [10, 10, 45], [50, 50, 48], "4" * 64)]),
            "ball": part("S1", [_inst("ball#0", [20, 20, 8], [30, 30, 18], "5" * 64),
                                _inst("ball#1", [32, 20, 8], [42, 30, 18], "6" * 64)], free=True),
            "pin": part("S2", [_inst("pin", [58, 18, 8], [62, 32, 12], "7" * 64)]),
            "arm": part("S2", [_inst("arm", [60, 20, 5], [95, 30, 15], "8" * 64)]),
        },
        "cavities": {"hopper_cavity": {"part": "hopper", "sha256": "9" * 64,
                                       "bbox": {"min": [12, 12, 7], "max": [48, 48, 45]}}},
        "joints": {"I-arm": {"kind": "revolute", "moving": "arm", "fixed": "pin",
                             "axis": {"origin": [60, 25, 10], "direction": [0, 1, 0]}, "range": [0, 40],
                             "unit": "deg", "intended_contacts": [["arm", "pin"]], "samples": None}},
        "fasteners": {"screw": {"key": "m3", "clamps": "lid", "into": "hopper", "count": 2, "instances": [
            _inst("screw#0", [10.5, 10.5, 40], [13.5, 13.5, 50], "a" * 64, origin=[12, 12, 48],
                  direction=[0, 0, -1]),
            _inst("screw#1", [46.5, 46.5, 40], [49.5, 49.5, 50], "b" * 64, origin=[48, 48, 48],
                  direction=[0, 0, -1])]}},
        "assembly": {"steps": [
            {"order": 1, "fit": "base", "onto": [], "direction": "-Z"},
            {"order": 2, "fit": "hopper", "onto": ["base"], "direction": "-Z"},
            {"order": 3, "fit": "ball", "onto": ["hopper"], "direction": "-Z"},
            {"order": 4, "fit": "lid", "onto": ["hopper"], "direction": "-Z", "fasteners": ["screw"]},
            {"order": 5, "fit": "pin", "onto": ["base"], "direction": "-Y"},
            {"order": 6, "fit": "arm", "onto": ["pin"], "direction": "-Z"}]},
        "physical_fit_verified": False,
    }


PROJECT = {
    "title": "Packet demo",
    "requirements": [{"id": "R1", "text": "Holds two balls", "verify_by": "analysis", "checks": ["gate:containment"]}],
    "sections": ["sections/*.yaml"],
    "interfaces": [{"id": "I-seat", "between": ["base", "hopper"], "kind": "contact", "datum": "base top"}],
}
SECTIONS = {
    "s0.yaml": {"id": "S0", "title": "Frame", "requirements": ["R1"], "parts": [
        {"id": "base", "function": "Carries everything", "interfaces": ["I-seat"]},
        {"id": "far", "function": "A part far away"}]},
    "s1.yaml": {"id": "S1", "title": "Store", "purpose": "Hold the balls", "requirements": ["R1"], "parts": [
        {"id": "hopper", "function": "Holds the balls", "interfaces": ["I-seat"],
         "contains": [{"what": "ball", "count": 2, "cavity": "hopper_cavity", "free": True}],
         "checks": ["gate:containment", "gate:fasteners"],
         "decisions": [{"id": "D1", "decision": "Square box", "why": "prints flat",
                        "alternatives": [{"option": "cone", "rejected": "supports"}]}]},
        {"id": "lid", "function": "Closes the hopper"},
        {"id": "ball", "function": "Loose item"},
        {"id": "ghost", "function": "Drawn later"}]},
    "s2.yaml": {"id": "S2", "title": "Arm", "requirements": ["R1"], "parts": [
        {"id": "pin", "function": "Pivot"}, {"id": "arm", "function": "Swings"}]},
}


def write_dossier(root: Path) -> Path:
    (root / "dossier" / "sections").mkdir(parents=True, exist_ok=True)
    (root / "dossier" / "project.yaml").write_text(yaml.safe_dump(PROJECT, sort_keys=False))
    for name, data in SECTIONS.items():
        (root / "dossier" / "sections" / name).write_text(yaml.safe_dump(data, sort_keys=False))
    return root / "dossier" / "project.yaml"


def verdicts(rec) -> Dict[str, Any]:
    containment = {"schema": "cadagent.gate/1", "gate": "containment", "pass": False, "status": "fail", "checks": [
        {"id": "contains:hopper_cavity:ball#0:inside", "status": "pass", "message": "inside", "parts": ["ball#0"]},
        {"id": "contains:hopper_cavity:ball#1:inside", "status": "fail", "message": "ball#1 escapes",
         "parts": ["ball#1", "hopper"], "evidence": {"furthest_outside_point": [41.0, 51.0, 13.0],
                                                     "nearest_cavity_point": [41.0, 48.0, 13.0],
                                                     "relation": {"witness": {"overlap_centroid": [41, 49.5, 13]}}}},
        {"id": "contains:hopper_cavity:cavity", "status": "pass", "message": "ok", "parts": ["hopper_cavity"]},
        {"id": "kernel", "status": "fail", "message": "the kernel failed on a pair it cannot name", "parts": []}]}
    wall = {"schema": "cadagent.gate/1", "gate": "wall", "pass": False, "status": "fail", "checks": [
        {"id": "wall:arm", "status": "fail", "message": "thin", "parts": ["arm"],
         "evidence": {"witnesses": [{"entry_point": [70, 25, 5], "exit_point": [70, 25, 5.8]}]}}]}
    fasteners = {"schema": "cadagent.gate/1", "gate": "fasteners", "pass": True, "status": "warn", "checks": [
        {"id": "fastener:screw#1:length", "status": "warn", "message": "uncommon length", "parts": ["screw#1"]}]}
    out = {"containment": bind_inputs(containment, rec), "wall": bind_inputs(wall, rec), "fasteners": fasteners}
    return out


def plan(tmp_path, section="S1", rec=None, verdicts_for=None, **kw):
    """The plan for ``section`` of ``rec`` (default ``record()``), with verdicts bound to ``verdicts_for`` (default:
    the same record, so they are current)."""
    rec = rec or record()
    d = load_dossier(write_dossier(tmp_path), strict=False, root=tmp_path)
    return pk.plan_packet(section, rec, d, verdicts(verdicts_for or rec), None, out_dir=f"exports/review/{section}",
                          **kw)


# ----------------------------------------------------------------------------------------------- the plan

def test_views_cover_the_section(tmp_path):
    m = plan(tmp_path)
    ids = [v["id"] for v in m["views"]]
    assert ids == ["solid-iso", "solid-rear", "xray-iso", "cut-cavity-hopper_cavity", "cut-cavity-hopper_cavity-plan",
                   "cut-fastener-screw", "access-from-top", "exploded", "findings"]
    assert m["schema"] == pk.SCHEMA and m["physical_fit_verified"] is False and m["dir"] == "exports/review/S1"
    assert m["section"] == {"id": "S1", "title": "Store", "purpose": "Hold the balls", "requirements": ["R1"],
                            "file": "dossier/sections/s1.yaml"}
    views = {v["id"]: v for v in m["views"]}
    cut = views["cut-cavity-hopper_cavity"]
    assert cut["clip"] == {"origin": [30.0, 30.0, 26.0], "normal": [0.0, 1.0, 0.0]} and cut["camera"] == [0, -1, 0]
    assert views["cut-cavity-hopper_cavity-plan"]["clip"]["normal"] == [0.0, 0.0, -1.0]
    assert cut["target"] == {"cavity": "hopper_cavity", "part": "hopper", "contains": ["ball"]}
    # the screw's cut contains its axis (-Z): a vertical plane, seen from the removed side
    fcut = views["cut-fastener-screw"]
    n = fcut["clip"]["normal"]
    assert abs(n[2]) < 1e-9 and fcut["clip"]["origin"] == [12.0, 12.0, 48.0]
    assert fcut["camera"] == [-c for c in n] and fcut["target"]["alike"] == ["screw"]
    assert views["access-from-top"]["camera"] == [0, 0, 1]
    assert {"base"} <= set(views["access-from-top"]["keys"])          # what may block the tool is drawn opaque
    for v in m["views"]:
        assert v["caption"].startswith("S1 Store: ") and v["note"] and v["sha256"] is None
        assert v["file"] == pk.safe_name(v["id"]) + ".png"
        assert v["fit"]["min"] < v["fit"]["max"]
    json.dumps(m)                                                      # plain JSON
    assert m["not_rendered"] == [{"what": "part ghost", "why": "its card has no registered shape"}]


def test_parts_hashes_and_context(tmp_path):
    m = plan(tmp_path)
    rec = record()
    assert list(m["parts"]) == ["hopper", "lid", "ball", "screw"]
    assert m["parts"]["hopper"]["sha256"] == rec["parts"]["hopper"]["sha256"]        # what a sign-off binds
    assert m["parts"]["ball"]["free"] and m["parts"]["ball"]["color"] == pk.FREE_COLOR
    assert m["parts"]["ball"]["instances"] == [{"key": "ball#0", "sha256": "5" * 64},
                                               {"key": "ball#1", "sha256": "6" * 64}]
    assert m["parts"]["screw"]["kind"] == "fastener" and m["parts"]["screw"]["clamps"] == "lid"
    assert m["parts"]["hopper"]["function"] == "Holds the balls"
    assert m["parts"]["hopper"]["decisions"] == [{"id": "D1", "decision": "Square box"}]
    assert m["section_hash"] == pk.hash_lines({n: p["sha256"] for n, p in m["parts"].items()})
    assert {c["key"] for c in m["context"]} == {"base"}                # far away and S2 are not neighbours
    assert {c["key"] for c in plan(tmp_path, context="all")["context"]} == {"base", "far", "pin", "arm"}
    assert plan(tmp_path, context="none")["context"] == []
    changed = record()
    changed["parts"]["lid"]["sha256"] = "f" * 64
    assert plan(tmp_path, rec=changed)["section_hash"] != m["section_hash"]
    with pytest.raises(pk.PacketError, match="context must be"):
        plan(tmp_path, context="some")


def test_an_interface_with_another_section_brings_its_parts_into_context(tmp_path, monkeypatch):
    monkeypatch.setitem(PROJECT, "interfaces", PROJECT["interfaces"] + [
        {"id": "I-sections", "between": ["S1", "S2"], "kind": "contact", "datum": "shared plate"}])
    assert {c["key"] for c in plan(tmp_path)["context"]} == {"base", "pin", "arm"}


def test_measurements_come_first_and_name_stale_and_missing_verdicts(tmp_path):
    m = plan(tmp_path)
    assert list(m).index("measurements") < list(m).index("views")
    g = m["measurements"]["gates"]
    assert g["containment"]["stale"] is None and g["containment"]["status"] == "fail"
    assert [c["id"] for c in g["containment"]["section_checks"]] == [
        "contains:hopper_cavity:ball#0:inside", "contains:hopper_cavity:ball#1:inside", "contains:hopper_cavity:cavity"]
    assert "not bound" in g["fasteners"]["stale"]                      # an unbound verdict is never current
    assert g["wall"]["section_checks"] == []                           # the arm is not in this section
    assert m["measurements"]["missing_gates"] == []
    rec = record()
    rec["parts"]["lid"]["instances"][0]["sha256"] = "e" * 64
    stale = plan(tmp_path, rec=rec, verdicts_for=record())["measurements"]["gates"]["containment"]["stale"]
    assert "geometry changed" in stale and "lid" in stale


def test_findings_carry_witness_points_and_callouts(tmp_path):
    m = plan(tmp_path)
    f = m["findings"]
    assert [(x["id"], x["check"], x["status"], x["scope"]) for x in f] == [
        ("F1", "contains:hopper_cavity:ball#1:inside", "fail", "section"),
        ("F2", "kernel", "fail", "unattributed"),
        ("F3", "fastener:screw#1:length", "warn", "section")]
    assert f[0]["witness"] == [{"label": "furthest_outside_point", "point": [41.0, 51.0, 13.0]},
                               {"label": "nearest_cavity_point", "point": [41.0, 48.0, 13.0]},
                               {"label": "relation.witness.overlap_centroid", "point": [41.0, 49.5, 13.0]}]
    view = next(v for v in m["views"] if v["id"] == "findings")
    assert [c["code"] for c in view["callouts"]] == ["F1.1", "F1.2", "F1.3"]
    assert f[0]["views"] == ["findings"] and f[1]["views"] == []
    arm = plan(tmp_path, "S2")
    assert [x["check"] for x in arm["findings"]] == ["wall:arm", "kernel"]
    assert arm["findings"][0]["witness"][0]["label"] == "witnesses[0].entry_point"


def test_joint_cut_and_poses(tmp_path):
    m = plan(tmp_path, "S2")
    views = {v["id"]: v for v in m["views"]}
    assert {"cut-joint-I-arm", "pose-I-arm-min", "pose-I-arm-max", "exploded"} <= set(views)
    cut = views["cut-joint-I-arm"]
    assert cut["clip"]["origin"] == [60.0, 25.0, 10.0] and cut["clip"]["normal"] == [1.0, 0.0, 0.0]
    hi = views["pose-I-arm-max"]
    assert hi["pose"]["value"] == 40 and hi["pose"]["unit"] == "deg" and hi["pose"]["keys"] == ["arm"]
    assert hi["target"]["contacts"] == [["arm", "pin"]]
    # the arm's far end turned 40 deg about +Y lands lower: the frame grows to hold it
    assert hi["fit"]["min"][2] < views["pose-I-arm-min"]["fit"]["min"][2]


def test_exploded_offsets_follow_the_steps(tmp_path):
    m = plan(tmp_path)
    off = next(v for v in m["views"] if v["id"] == "exploded")["offsets"]
    # steps fit hopper (2), ball (3), lid (4), all -Z: each backs out along +Z, later steps further
    assert off["hopper"][2] < off["ball#0"][2] == off["ball#1"][2] < off["lid"][2]
    assert all(off[k][0] == off[k][1] == 0 for k in ("hopper", "lid"))
    assert off["screw#0"][2] > off["lid"][2]                       # screws come off with the lid, then further
    assert "base" not in off                                       # context stays where it is
    assert not any(v["id"] == "exploded" for v in plan(tmp_path, explode=0)["views"])


def test_checklist_is_instantiated_per_view(tmp_path):
    m = plan(tmp_path)
    cl = m["checklist"]
    assert cl["schema"] == pk.CHECKLIST_SCHEMA and cl["answers"] == ["yes", "no", "unclear"]
    assert [i["id"] for i in cl["items"]] == [i["id"] for i in pk.CHECKLIST]
    assert {x["id"] for x in cl["measured_only"]} >= {"count", "gap", "wall", "thread"}
    q = {x["id"]: x for x in cl["questions"]}
    assert q["contained-inside:hopper_cavity:ball"]["views"] == ["cut-cavity-hopper_cavity",
                                                                 "cut-cavity-hopper_cavity-plan"]
    assert q["contained-inside:hopper_cavity:ball"]["question"] == (
        "In the cut through hopper_cavity, is every ball fully inside the inner wall of hopper?")
    assert q["fastener-stack:screw"]["question"].endswith("does the head sit on lid and does the thread end inside "
                                                          "hopper?")
    assert q["fastener-access:from-top"]["views"] == ["access-from-top"]
    assert q["plain-box"]["views"] == ["solid-iso", "solid-rear"] and q["plain-box"]["bad_answer"] == "yes"
    assert q["floating"]["views"] == ["solid-rear"]
    view_ids = {v["id"] for v in m["views"]}
    assert all(set(x["views"]) <= view_ids and x["views"] for x in cl["questions"])
    arm = {x["id"]: x for x in plan(tmp_path, "S2")["checklist"]["questions"]}
    assert "motion-contact:I-arm-max" in arm and "(arm-pin)" in arm["motion-contact:I-arm-max"]["question"]
    assert "joint-bearing:I-arm" in arm


def test_generic_checklist_is_well_formed():
    ids = [i["id"] for i in pk.CHECKLIST]
    assert len(ids) == len(set(ids))
    kinds = {"cut", "exploded", "solid", "solid-rear", "xray", "access", "pose", "findings"}
    for item in pk.CHECKLIST:
        assert item["kind"] in kinds and item["bad_answer"] in pk.ANSWERS and item["question"].endswith("?")
        assert item["per"] in (None, "cavity", "joint", "fastener", "access", "pose")
        assert item["gate"] in (None, "containment", "connectivity", "fasteners", "assembly", "motion", "wall")


def test_packet_staleness(tmp_path):
    # quoting an unbound verdict (fasteners) makes the packet stale from the start
    assert "stale when it was made (fasteners)" in pk.packet_stale(plan(tmp_path), record())
    rec = record()
    current = verdicts(rec)
    bind_inputs(current["fasteners"], rec)
    d = load_dossier(write_dossier(tmp_path), strict=False, root=tmp_path)
    lint = {"schema": "cadagent.gate/1", "gate": "dossier-lint", "pass": True, "status": "pass", "checks": []}
    m = pk.plan_packet("S1", rec, d, current, None, lint=lint, lint_current=True)
    assert m["findings"][0]["stale"] is None and m["measurements"]["lint"]["stale"] is None
    assert pk.packet_stale(m, rec) is None
    assert pk.packet_stale(m, rec, verdicts=current, lint=lint) is None
    changed = record()
    changed["parts"]["hopper"]["instances"][0]["sha256"] = "0" * 64
    assert "geometry changed" in pk.packet_stale(m, changed)
    # a verdict rewritten, added or gone since the packet
    rewritten = copy.deepcopy(current)
    rewritten["wall"]["status"] = "pass"
    assert "gate verdicts changed since the packet (wall)" in pk.packet_stale(m, rec, verdicts=rewritten)
    assert "(motion)" in pk.packet_stale(m, rec, verdicts={**current, "motion": current["wall"]})
    # the same verdict files, but the gate's declarations changed (the dossier was edited): stale now
    why = pk.packet_stale(m, rec, verdicts=current, expected={"wall": {"declarations": {"x": 1}}})
    assert why.startswith("verdict wall is stale now") and "declarations changed" in why
    assert "lint changed" in pk.packet_stale(m, rec, verdicts=current, lint={**lint, "status": "fail"})
    # a lint read from a file (no inputs) cannot vouch for itself
    m2 = pk.plan_packet("S1", rec, d, current, None, lint=lint)
    assert m2["measurements"]["lint"]["stale"] and "may not be current" in pk.packet_stale(m2, rec)
    assert pk.packet_stale({"schema": pk.SCHEMA}, rec) == "the packet records no geometry digest"
    assert pk.packet_stale(m, None)


def test_project_packet_staleness_follows_the_dossier(tmp_path):
    root = make_project(tmp_path)
    vfile = root / "exports" / "gates" / "fasteners.json"
    from cadagent.review.gates import run as gr
    from cadagent.project import load_project
    cfg = gr.gates_config(load_project(root))
    v = json.loads(vfile.read_text())
    bind_inputs(v, record(), **gr.expected_inputs("fasteners", cfg, gr.load_dossier(load_project(root)),
                                                  gr.load_extra(cfg)))
    vfile.write_text(json.dumps(v))
    m, _ = pk.plan_project_packet("S1", root=root)
    assert m["measurements"]["lint"]["stale"] is None
    assert pk.project_packet_stale(m, root) is None
    # edit the dossier only: the gates' declarations change, so the verdicts the packet quotes are stale now
    proj = root / "dossier" / "project.yaml"
    original = proj.read_text()
    data = yaml.safe_load(original)
    data["gates"] = {"intended_overlaps": [{"parts": ["screw", "hopper"], "reason": "thread in the boss"}]}
    proj.write_text(yaml.safe_dump(data, sort_keys=False))
    assert "stale now" in pk.project_packet_stale(m, root)
    proj.write_text(original)
    assert pk.project_packet_stale(m, root) is None
    # edit only the text a packet quotes (a card's function): the captions and questions are out of date
    sec = root / "dossier" / "sections" / "s1.yaml"
    sec.write_text(sec.read_text().replace("function: Closes the hopper", "function: Seals the hopper"))
    assert "dossier text" in pk.project_packet_stale(m, root)
    assert m["measurements"]["lint"]["file"] is None and m["measurements"]["lint"]["computed"]


def test_unknown_section_and_missing_record(tmp_path):
    with pytest.raises(pk.PacketError, match="unknown section 'S9'; sections: S0, S1, S2"):
        plan(tmp_path, "S9")
    with pytest.raises(pk.PacketError, match="no geometry record"):
        pk.plan_packet("S1", {})
    # without a dossier, the sections are the build's
    m = pk.plan_packet("S1", record())
    assert m["section"] == {"id": "S1"} and "function" not in m["parts"]["hopper"]
    assert pk.sections_of(record()) == ["S0", "S1", "S2"]


def test_witness_points_and_geometry_helpers():
    ev = {"a_point": [1, 2, 3], "nested": [{"overlap_centroid": [1, 2, 3.0000001]}, {"inner_point": [4, 5, 6]}],
          "not_a_point": [1, 2, 3], "point_bad": [1, 2], "point_bool": [True, 0, 0], "point_nan": [math.nan, 0, 0]}
    assert pk.witness_points(ev) == [{"label": "a_point", "point": [1.0, 2.0, 3.0]},
                                     {"label": "nested[1].inner_point", "point": [4.0, 5.0, 6.0]}]
    assert len(pk.witness_points({f"p{i}_point": [i, 0, 0] for i in range(10)})) == pk.MAX_WITNESSES
    assert pk.plane_containing((0, 0, -1)) == (1.0, 0.0, 0.0)
    assert pk.plane_containing((0, 1, 0)) == (1.0, 0.0, 0.0)
    n = pk.plane_containing((1, 1, 0))
    assert abs(n[0] + n[1]) < 1e-9 and abs(n[2]) < 1e-9          # contains the axis
    p = pk.rotate_point((1, 0, 0), (0, 0, 0), (0, 0, 1), 90)
    assert max(abs(a - b) for a, b in zip(p, (0, 1, 0))) < 1e-12
    assert pk.direction_vector("-z") == (0.0, 0.0, -1.0) and pk.direction_vector([0, 0, 2]) == (0.0, 0.0, 1.0)
    assert pk.direction_vector("") is None and pk.direction_vector([0, 0]) is None
    assert pk.owner("ball#3") == "ball" and pk.owner("m3:lid-base") == "m3:lid-base"
    assert pk.safe_name("cut-fastener-m3:lid-base") == "cut-fastener-m3_lid-base"


# ----------------------------------------------------------------------------------------------- the CLI (plan only)

def make_project(root: Path) -> Path:
    """A project with the record and the verdicts written as `cad-agent gates` writes them (bound to the gates'
    declarations and options too), except the fastener verdict, which stays unbound."""
    from cadagent.review.gates import run as gr
    from cadagent.project import load_project

    write_dossier(root)
    (root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  dossier: dossier/project.yaml\n")
    (root / "exports" / "gates").mkdir(parents=True)
    rec = record()
    (root / "exports" / "dossier-geometry.json").write_text(json.dumps(rec))
    cfg = gr.gates_config(load_project(root))
    extra, dossier = gr.load_extra(cfg), gr.load_dossier(load_project(root))
    for g, v in verdicts(rec).items():
        if v.get("inputs"):
            bind_inputs(v, rec, **gr.expected_inputs(g, cfg, dossier, extra))
        (root / "exports" / "gates" / f"{g}.json").write_text(json.dumps(v))
    return root


def test_cli_lists_the_views_without_rendering(tmp_path, capsys):
    root = make_project(tmp_path)
    assert main(["review-packet", "--project", str(root), "--list"]) == 0
    out = capsys.readouterr().out
    assert "S1  Store" in out and "cut-cavity-hopper_cavity" in out and "pose-I-arm-max" in out
    assert "not rendered: part ghost" in out and "stale verdicts: fasteners" in out
    assert not (root / "exports" / "review").exists()                   # nothing written
    assert main(["review-packet", "S9", "--project", str(root), "--list"]) == 2
    assert "unknown section 'S9'" in capsys.readouterr().err
    assert main(["review-packet", "--project", str(root), "--size", "10x10"]) == 2
    assert "--size '10x10'" in capsys.readouterr().err
    m, target = pk.plan_project_packet("S1", root=root)
    assert target == root / "exports" / "review" / "S1" and m["dir"] == "exports/review/S1"
    assert m["geometry"]["file"] == "exports/dossier-geometry.json" and m["toolkit"]
    assert pk.project_sections(root) == ["S0", "S1", "S2"]


def _have(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@pytest.mark.skipif(all(_have(m) for m in ("cadquery", "vtk", "PIL")),
                    reason="checks the error when the CAD extra is missing")
def test_rendering_without_the_cad_extra_says_what_is_missing(tmp_path):
    from cadagent import MissingDependency
    with pytest.raises(MissingDependency):
        pk.review_packet("S1", root=make_project(tmp_path))


# ----------------------------------------------------------------------------------------------- rendering
# The gate bench with one seeded defect (a ball through the hopper wall), built and its containment gate run
# through the CLI, then every section's packet rendered. Needs CadQuery, VTK and Pillow.

BENCH = Path(__file__).resolve().parents[1] / "fixtures" / "gate_bench"


@pytest.fixture(scope="module")
def bench_packets(tmp_path_factory):
    for mod in ("cadquery", "trimesh", "vtk", "PIL"):
        pytest.importorskip(mod)
    base = tmp_path_factory.mktemp("packet")
    shutil.copytree(BENCH, base / "gate_bench", ignore=shutil.ignore_patterns("__pycache__"))
    root = base / "gate_bench" / "project"
    (root / "cad" / "parameters.json").write_text(json.dumps({"seed": "ball_through_wall"}))
    assert main(["gates", "--project", str(root), "--build", "--only", "containment"]) == 1
    manifests = {sid: pk.review_packet(sid, root=root, size=(480, 360)) for sid in pk.project_sections(root)}
    return root, manifests


def test_packet_renders_every_section_with_captions_and_hashes(bench_packets):
    from PIL import Image

    root, manifests = bench_packets
    record_ = json.loads((root / "exports" / "dossier-geometry.json").read_text())
    assert set(manifests) == {"S-arm", "S-bracket", "S-frame", "S-store"}
    for sid, m in manifests.items():
        folder = root / "exports" / "review" / sid
        assert json.loads((folder / "manifest.json").read_text()) == m
        assert m["rendered"] == len(m["views"]) and pk.packet_stale(m, record_) is None
        for name, part in m["parts"].items():
            if part["kind"] == "part":
                assert part["sha256"] == record_["parts"][name]["sha256"], name
        for v in m["views"]:
            png = folder / v["file"]
            assert v["sha256"] == pk.file_sha256(png), v["id"]
            im = Image.open(png).convert("RGB")
            assert im.size == (480, 360)
            assert im.getpixel((3, 3)) == (0x14, 0x2B, 0x38)                     # the caption bar
            assert v["caption"].startswith(f"{sid} ")
            colours = im.crop((0, 100, 480, 300)).getcolors(maxcolors=100000) or []
            assert len(colours) > 20, f"{sid}/{v['id']}: nothing drawn"
        assert sorted(p.name for p in folder.glob("*.png")) == sorted(v["file"] for v in m["views"])


def test_packet_shows_the_seeded_defect(bench_packets):
    root, manifests = bench_packets
    store = manifests["S-store"]
    kinds = {v["kind"] for v in store["views"]}
    assert kinds == {"solid", "solid-rear", "xray", "cut", "access", "exploded", "findings"}
    failing = [f for f in store["findings"] if f["status"] == "fail"]
    assert {f["gate"] for f in failing} == {"containment", "dossier-lint"}     # the lint: the section is not gated
    assert any(f["check"].startswith("section-below-gated@") for f in failing if f["gate"] == "dossier-lint")
    escape = next(f for f in failing if f["check"] == "contains:hopper_cavity:ball#7:inside")
    far = next(w for w in escape["witness"] if w["label"] == "furthest_outside_point")
    assert far["point"][1] > 62.6                                       # outside the cavity's +Y wall
    assert store["measurements"]["gates"]["containment"]["stale"] is None
    assert any(v["id"] == "findings" and v["callouts"] for v in store["views"])
    arm = manifests["S-arm"]
    assert {"cut-joint-I-pin-arm", "pose-I-pin-arm-min", "pose-I-pin-arm-max"} <= {v["id"] for v in arm["views"]}
    assert arm["findings"] == []                                        # the defect is not the arm's


def test_partial_render_keeps_current_images(bench_packets):
    root, manifests = bench_packets
    before = copy.deepcopy(manifests["S-bracket"])
    m = pk.review_packet("S-bracket", root=root, size=(480, 360), only=["solid-iso"])
    assert [v["sha256"] for v in m["views"] if v["id"] != "solid-iso"] == \
        [v["sha256"] for v in before["views"] if v["id"] != "solid-iso"]
    assert m["rendered"] == len(m["views"])
    # another explode scale changes the exploded view's plan: its old image is not current, so it is dropped
    m = pk.review_packet("S-bracket", root=root, size=(480, 360), only=["solid-iso"], explode=0.5)
    exploded = next(v for v in m["views"] if v["id"] == "exploded")
    assert exploded["file"] is None and exploded["sha256"] is None
    assert not (root / "exports" / "review" / "S-bracket" / "exploded.png").exists()
    # another image size: no earlier image matches, so only the view asked for is in the packet
    m = pk.review_packet("S-bracket", root=root, size=(520, 360), only=["solid-iso"])
    assert [v["id"] for v in m["views"] if v["file"]] == ["solid-iso"] and m["render"] == {"size": [520, 360]}
    assert sorted(p.name for p in (root / "exports" / "review" / "S-bracket").glob("*.png")) == ["solid-iso.png"]
