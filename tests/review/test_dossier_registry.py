"""The build-script registry (plan T13): @part, @cavity, @joint, fastener(), assembly.step(), the geometry export,
the dossier_items() migration path, and the join with the YAML cards."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from cadagent.review.dossier import REGISTRY, Axis, Registry, RegistryError, join, load_dossier

# ------------------------------------------------------------------------------------------------ fixtures

# The plan's §3.4 example, made concrete: a box-shaped hopper with a declared cavity and eight loose balls, a flap on
# a revolute joint, a pan bolted to a grounded bench, and the assembly steps.
BUILD = textwrap.dedent('''\
    import cadquery as cq
    from cadagent.review.dossier import Axis, part, cavity, joint, fastener, assembly

    def hopper_shell_inner(p):
        w = p["wall"]
        return cq.Workplane().box(60 - 2 * w, 60 - 2 * w, 60 - w, centered=(True, True, False)).translate((0, 0, 10 + w)).val()

    @part("bench_base", section="S1", grounded=True)
    def bench_base(p):
        return cq.Workplane().box(120, 120, 10, centered=(True, True, False)).translate((0, 0, -10)).val()

    @part("pan_base", section="S1")
    def pan_base(p):
        return cq.Workplane().box(100, 100, 10, centered=(True, True, False)).val()

    @part("hopper", section="S3")                 # registers the shape and its dossier card
    def hopper(p):
        outer = cq.Workplane().box(60, 60, 60, centered=(True, True, False)).translate((0, 0, 10)).val()
        return outer.cut(hopper_shell_inner(p))

    @cavity("hopper", "hopper_cavity")            # the void the containment gate tests against
    def hopper_cavity(p): return hopper_shell_inner(p)

    @part("ball", section="S3", free=True, reason="loose in the hopper")
    def balls(p):
        return [cq.Solid.makeSphere(p["ball_r"], cq.Vector(x, y, 20)) for x in (-15, 15) for y in (-15, 15)] + \\
               [cq.Solid.makeSphere(p["ball_r"], cq.Vector(x, y, 35)) for x in (-15, 15) for y in (-15, 15)]

    @part("hopper_flap", section="S4")
    def hopper_flap(p):
        return cq.Workplane().box(2, 60, 30, centered=(False, True, False)).translate((30, 0, 70)).val()

    @joint("I9", kind="revolute", axis=lambda p: Axis(p["flap_pivot"], (0, 1, 0)), range_deg=(0, 70),
           parts=("hopper_flap", "hopper"), intended_contacts=[("hopper_flap", "hopper")])
    def flap_pivot(p): ...                        # optional body; the joint is what matters

    def screw(p):                                 # McMaster frame: seat at the origin, head on +Z
        head = cq.Workplane().circle(2.75).extrude(3).val()
        shank = cq.Workplane().circle(1.5).extrude(-8).val()
        return head.fuse(shank)

    fastener("screw_m3x8", clamps="hopper", into="pan_base", via="I7", tool="hex_2.5", length_mm=8,
             thread_start_mm=lambda p: p["wall"], min_engagement_mm=4,
             at=lambda p: [Axis((x, y, 10 + p["wall"]), (0, 0, -1)) for x in (-25, 25) for y in (-25, 25)],
             shape=screw)

    assembly.step(1, fit="pan_base", onto="bench_base", direction="-Z", tool="hex_2.5", fasteners=["screw_m4x12"] * 3)
    assembly.step(2, fit="hopper", onto="pan_base", direction="-Z", tool="hex_2.5", fasteners=["screw_m3x8"] * 4)
    ''')

PARAMS = {"wall": 2.4, "ball_r": 5.0, "flap_pivot": [31, 0, 70], "revision": "t"}

PROJECT = textwrap.dedent("""\
    requirements:
      - {id: R4, text: Holds the balls, verify_by: inspection}
    sections: [sections.yaml]
    interfaces:
      - {id: I7, between: [hopper, pan_base], kind: fastened, fastened_by: screw_m3x8}
      - {id: I8, between: [hopper, ball], kind: contact}
      - {id: I9, between: [hopper_flap, hopper], kind: revolute}
      - {id: I1, between: [pan_base, bench_base], kind: fastened}
    assembly:
      steps:
        - {order: 1, fit: pan_base, onto: bench_base, direction: -Z}
    """)

SECTIONS = textwrap.dedent("""\
    id: S1
    title: Base
    parts:
      - {id: bench_base, function: ground, interfaces: [I1]}
      - {id: pan_base, function: plate, interfaces: [I1, I7]}
    """)

S3 = textwrap.dedent("""\
    id: S3
    title: Hopper and feed
    requirements: [R4]
    parts:
      - id: hopper
        function: Contain the balls
        interfaces: [I7, I8, I9]
        fasteners: [{to: pan_base, screws: screw_m3x8, qty: 4, via: I7}]
        contains: [{what: ball, count: 8, cavity: hopper_cavity, free: true}]
        decisions:
          - {id: D41, decision: Box hopper, why: test, alternatives: [{option: cone, rejected: harder to test}]}
      - {id: ball, function: Loose item, interfaces: [I8]}
    """)

S4 = textwrap.dedent("""\
    id: S4
    title: Flap
    parts:
      - {id: hopper_flap, function: Closes the throat, interfaces: [I9]}
    """)


@pytest.fixture(autouse=True)
def clean_registry():
    REGISTRY.clear()
    yield
    REGISTRY.clear()


def make_project(root: Path, *, s3: str = S3, build: str = BUILD) -> Path:
    (root / "cad").mkdir(parents=True, exist_ok=True)
    (root / "cad" / "build.py").write_text(build)
    (root / "cad" / "parameters.json").write_text(json.dumps(PARAMS))
    d = root / "dossier"
    d.mkdir(exist_ok=True)
    (d / "project.yaml").write_text(PROJECT.replace("sections: [sections.yaml]",
                                                    "sections: [s1.yaml, s3.yaml, s4.yaml]"))
    (d / "s1.yaml").write_text(SECTIONS)
    (d / "s3.yaml").write_text(s3)
    (d / "s4.yaml").write_text(S4)
    return root


@pytest.fixture
def built(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    root = make_project(tmp_path)
    result = build_module(root / "cad" / "build.py", root=root)
    return root, result


# ------------------------------------------------------------------------------------- the §3.4 example builds

def test_plan_example_builds_and_writes_the_geometry_record(built):
    root, result = built
    path = root / "exports" / "dossier-geometry.json"
    assert result.path == path and path.is_file()
    geo = json.loads(path.read_text())
    assert geo["schema"] == "cad-agent.dossier-geometry/1" and geo["physical_fit_verified"] is False
    assert geo["parameters"]["file"] == "cad/parameters.json"
    assert set(geo["parts"]) == {"bench_base", "pan_base", "hopper", "ball", "hopper_flap"}
    hopper = geo["parts"]["hopper"]
    assert hopper["section"] == "S3" and hopper["count"] == 1 and hopper["instances"][0]["valid"] is True
    assert hopper["declared_at"].startswith("cad/build.py:")
    assert geo["parts"]["bench_base"]["grounded"] is True
    ball = geo["parts"]["ball"]
    assert ball["free"] is True and ball["free_reason"] == "loose in the hopper" and ball["count"] == 8
    assert [i["key"] for i in ball["instances"]][:2] == ["ball#0", "ball#1"]
    cav = geo["cavities"]["hopper_cavity"]
    assert cav["part"] == "hopper" and cav["volume_mm3"] == pytest.approx(55.2 * 55.2 * 57.6, rel=1e-6)
    assert cav["bbox"]["min"][2] == pytest.approx(12.4, abs=1e-3)
    j = geo["joints"]["I9"]
    assert (j["kind"], j["moving"], j["fixed"], j["range"], j["unit"]) == ("revolute", "hopper_flap", "hopper", [0, 70], "deg")
    assert j["axis"] == {"origin": [31.0, 0.0, 70.0], "direction": [0.0, 1.0, 0.0]}
    assert j["intended_contacts"] == [["hopper_flap", "hopper"]]
    f = geo["fasteners"]["screw_m3x8:hopper-pan_base"]
    assert f["count"] == 4 and f["thread_start_mm"] == 2.4 and f["length_mm"] == 8 and f["via"] == "I7"
    first = f["instances"][0]
    assert first["origin"] == [-25.0, -25.0, 12.4] and first["direction"] == [0.0, 0.0, -1.0]
    # the screw is placed with its head above the seat and its shank below it
    assert first["bbox"]["max"][2] == pytest.approx(15.4, abs=1e-3)
    assert first["bbox"]["min"][2] == pytest.approx(4.4, abs=1e-3)
    steps = geo["assembly"]["steps"]
    assert [s["order"] for s in steps] == [1, 2]
    assert steps[0] == {"order": 1, "fit": "pan_base", "onto": ["bench_base"], "direction": "-Z", "tool": "hex_2.5",
                        "fasteners": ["screw_m4x12"] * 3, "declared_at": steps[0]["declared_at"]}


def test_the_record_says_where_its_hashes_were_made(built):
    """The record's ``hash`` holds the recipe and the platform (#144): a key every release leaves out of the gates'
    geometry digest, so a record written by this release digests the same under an earlier one."""
    from cadagent.review import evidence
    from cadagent.review.dossier.registry import HASH_RECIPE
    from cadagent.review.gates.verdict import geometry_digest
    root, result = built
    geo = json.loads((root / "exports" / "dossier-geometry.json").read_text())
    assert geo["hash"] == {"recipe": HASH_RECIPE, "platform": evidence.hash_platform()} == result.geometry["hash"]
    assert evidence.record_hash_platform(geo) == evidence.hash_platform()
    assert set(geo["hash"]["platform"]) == set(evidence.PLATFORM_KEYS) and geo["hash"]["platform"]["ocp"] != "unknown"
    assert "hash_platform" not in geo                                    # no new top-level key
    older = dict(geo, hash=HASH_RECIPE)                                  # as a toolkit before #144 wrote it
    assert geometry_digest(older) == geometry_digest(geo)


def test_shapes_are_content_addressed_and_gitignored(built):
    import hashlib
    import re
    root, result = built
    shapes = root / "exports" / "dossier-shapes"
    assert (shapes / ".gitignore").read_text().splitlines()[-1] == "*"
    geo = result.geometry
    for info in geo["parts"]["ball"]["instances"] + [geo["cavities"]["hopper_cavity"]]:
        brep = (root / "exports" / info["file"]).read_bytes()
        # the recipe, pinned: sha256 of the BREP text with the 7-digit flag lines removed (= gates.cache.shape_hash)
        assert hashlib.sha256(re.sub(rb"^[01]{7}$", b"", brep, flags=re.M)).hexdigest() == info["sha256"]
    stale = shapes / ("0" * 64 + ".brep")
    stale.write_text("old")
    result.write()
    assert not stale.exists()


def test_assembly_shapes_is_the_gate_hand_over(built):
    _, result = built
    shapes = result.assembly_shapes()
    assert {"hopper", "bench_base", "ball#0", "ball#7", "screw_m3x8:hopper-pan_base#3"} <= set(shapes)
    assert "ball" not in shapes and result.owner("ball#7") == "ball" and result.owner("hopper") == "hopper"
    assert len(result.assembly_shapes(fasteners=False)) == 4 + 8


def test_load_geometry_reads_shapes_back_and_checks_hashes(built):
    from cadagent.review.dossier import load_geometry
    root, result = built
    again = load_geometry(root / "exports" / "dossier-geometry.json")
    hopper, original = again.parts["hopper"][0], result.parts["hopper"][0]
    assert hopper.isValid() and hopper.Volume() == pytest.approx(original.Volume(), rel=1e-9)
    assert len(again.parts["ball"]) == 8 and again.joints["I9"]["axis"] == Axis((31, 0, 70), (0, 1, 0))
    assert len(again.fasteners["screw_m3x8:hopper-pan_base"]) == 4
    assert again.fastener_axes["screw_m3x8:hopper-pan_base"][0].origin == (-25.0, -25.0, 12.4)
    target = root / "exports" / result.geometry["cavities"]["hopper_cavity"]["file"]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(RegistryError, match="does not match its recorded sha256"):
        load_geometry(root / "exports" / "dossier-geometry.json")


def test_hash_is_stable_across_processes_and_ignores_meshing(tmp_path):
    cq = pytest.importorskip("cadquery")
    from cadagent.review.dossier import shape_sha256
    box = cq.Workplane().box(10, 20, 30).edges("|Z").fillet(2).val()
    here = shape_sha256(box)
    box.tessellate(0.1)
    assert shape_sha256(box) == here
    assert shape_sha256(box.moved(cq.Location(cq.Vector(0.001, 0, 0)))) != here
    code = ("import cadquery as cq; from cadagent.review.dossier import shape_sha256; "
            "print(shape_sha256(cq.Workplane().box(10, 20, 30).edges('|Z').fillet(2).val()))")
    src = str(Path(__file__).resolve().parents[2] / "software")
    other = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={"PYTHONPATH": src, "PATH": "/usr/bin:/bin"}).stdout.strip()
    assert other == here


def test_rebuild_with_same_parameters_is_identical(built):
    from cadagent.review.dossier import build_module
    root, first = built
    again = build_module(root / "cad" / "build.py", root=root, write=False)
    strip = lambda g: {k: v for k, v in g.items() if k != "shapes_dir"}
    assert strip(again.geometry) == strip(first.geometry)
    (root / "cad" / "parameters.json").write_text(json.dumps({**PARAMS, "wall": 3.0}))
    moved = build_module(root / "cad" / "build.py", root=root, write=False)
    assert moved.geometry["parts"]["hopper"]["sha256"] != first.geometry["parts"]["hopper"]["sha256"]
    assert moved.geometry["parameters"]["sha256"] != first.geometry["parameters"]["sha256"]


# ----------------------------------------------------------------------------------- joining cards and shapes

def test_join_is_clean_on_the_example(built):
    root, result = built
    issues = join(load_dossier(root / "dossier" / "project.yaml"), result)
    # screw_m4x12 is named by step 1 but not declared with fastener(): a warning, nothing else
    assert [(i.code, i.severity) for i in issues] == [("step-fastener-unregistered", "warning")]


def test_card_without_shape_and_shape_without_card_are_findings(built):
    root, result = built
    s3 = S3 + "  - {id: ghost, function: Not modelled yet, interfaces: [I8]}\n"
    (root / "dossier" / "s3.yaml").write_text(s3)
    (root / "dossier" / "s4.yaml").write_text(S4.replace("  - {id: hopper_flap", "  - {id: spare_flap, function: x}\n"
                                                                                 "  - {id: hopper_flap"))
    d = load_dossier(root / "dossier" / "project.yaml")
    geo = json.loads((root / "exports" / "dossier-geometry.json").read_text())   # the JSON alone is enough
    geo["parts"]["orphan"] = dict(geo["parts"]["pan_base"], declared_at="cad/build.py:99", section="")
    issues = join(d, geo)
    ghost = next(i for i in issues if i.code == "card-without-shape" and "ghost" in i.message)
    assert (ghost.where.file, ghost.where.line) == ("dossier/s3.yaml", 13)
    orphan = next(i for i in issues if i.code == "shape-without-card")
    assert "orphan" in orphan.message and (orphan.where.file, orphan.where.line) == ("cad/build.py", 99)
    assert ghost.severity == orphan.severity == "error"
    assert sum(i.code == "card-without-shape" for i in join(d, geo)) == 2      # ghost and spare_flap


def test_join_reports_declaration_mismatches(built):
    root, result = built
    s3 = (S3.replace("count: 8", "count: 40").replace("cavity: hopper_cavity", "cavity: hopper_void")
          .replace("qty: 4", "qty: 6"))
    (root / "dossier" / "s3.yaml").write_text(s3)
    project = (root / "dossier" / "project.yaml").read_text()
    project = (project.replace("kind: revolute}", "kind: slider}")
               .replace("{order: 1, fit: pan_base, onto: bench_base, direction: -Z}",
                        "{order: 1, fit: pan_base, onto: bench_base, direction: +Z}")
               + "    - {order: 3, fit: hopper_flap, onto: hopper}\n")
    project = project.replace("  - {id: I1,", "  - {id: I2, between: [hopper, hopper_flap], kind: ball}\n  - {id: I1,")
    (root / "dossier" / "project.yaml").write_text(project)
    d = load_dossier(root / "dossier" / "project.yaml")
    issues = [i for i in join(d, result) if i.severity == "error"]
    assert sorted(i.code for i in issues) == ["contains-count", "fastener-count", "interface-without-joint",
                                              "joint-kind-mismatch", "step-conflict", "unknown-cavity"]
    count = next(i for i in issues if i.code == "fastener-count")
    assert (count.where.file, count.where.line) == ("dossier/s3.yaml", 8)      # the fasteners[] entry; the card is line 5


# ------------------------------------------------------------------------------ the dossier_items() migration

LEGACY = textwrap.dedent('''\
    import cadquery as cq
    from cadagent.review.dossier import Axis, part

    def _plate(p):
        return cq.Workplane().box(100, 100, 10, centered=(True, True, False)).val()

    @part("pan_base", section="S1")               # migrated first: the decorator wins over print_parts()
    def pan_base(p):
        return _plate(p)

    def print_parts():
        p = {"wall": 2.4}
        inner = cq.Workplane().box(55.2, 55.2, 57.6, centered=(True, True, False)).translate((0, 0, 12.4)).val()
        hopper = cq.Workplane().box(60, 60, 60, centered=(True, True, False)).translate((0, 0, 10)).val().cut(inner)
        return {"pan_base": _plate(p), "hopper": hopper,
                "hopper_flap": cq.Workplane().box(2, 60, 30).translate((31, 0, 85)).val()}

    def dossier_items():
        inner = cq.Workplane().box(55.2, 55.2, 57.6, centered=(True, True, False)).translate((0, 0, 12.4)).val()
        return {
            "parts": {"hopper": {"section": "S3"}, "hopper_flap": {"section": "S4"}},
            "cavities": {"hopper_cavity": {"part": "hopper", "shape": inner}},
            "joints": [{"interface": "I9", "kind": "revolute", "parts": ("hopper_flap", "hopper"),
                        "axis": Axis((31, 0, 70), (0, 1, 0)), "range_deg": (0, 70)}],
            "assembly": [{"order": 2, "fit": "hopper", "onto": "pan_base", "direction": "-Z"}],
        }
    ''')


def test_dossier_items_migration_path(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    root = make_project(tmp_path, build=LEGACY)
    result = build_module(root / "cad" / "build.py", root=root)
    geo = result.geometry
    assert set(geo["parts"]) == {"pan_base", "hopper", "hopper_flap"}
    assert geo["parts"]["pan_base"]["declared_at"].startswith("cad/build.py:")       # the decorated one
    assert "(print_parts hopper)" in geo["parts"]["hopper"]["declared_at"]
    assert geo["parts"]["hopper"]["section"] == "S3" and geo["joints"]["I9"]["range"] == [0, 70]
    assert geo["cavities"]["hopper_cavity"]["part"] == "hopper"
    codes = {i.code for i in join(load_dossier(root / "dossier" / "project.yaml"), result)}
    assert {"card-without-shape"} <= codes and "shape-without-card" not in codes   # bench_base, ball not yet


def test_dossier_items_needs_print_parts():
    from cadagent.review.dossier import build_module
    import types
    mod = types.ModuleType("m")
    mod.dossier_items = lambda: {}
    with pytest.raises(RegistryError, match="needs print_parts"):
        build_module(mod, registry=Registry(), write=False)
    reg = Registry()
    with pytest.raises(RegistryError, match="does not return"):
        reg.add_build_items({"a": object()}, {"parts": {"b": {"section": "S1"}}})
    with pytest.raises(RegistryError, match="unknown keys"):
        reg.add_build_items({"a": object()}, {"part": {}})


# ------------------------------------------------------------------------------- placement and declarations

def test_place_makes_instances_and_cavities_follow_the_part(tmp_path):
    cq = pytest.importorskip("cadquery")
    reg = Registry()

    @reg.part("cup", section="S1", place=lambda p: (0, 0, p["z"]))
    def cup():
        return cq.Workplane().box(10, 10, 10).val()

    @reg.cavity("cup", "cup_void")
    def cup_void(p):
        return cq.Workplane().box(8, 8, 8).val()

    @reg.part("peg", place=[(0, 0, 0), (20, 0, 0), cq.Location(cq.Vector(40, 0, 0))])
    def peg(p):
        return cq.Workplane().box(1, 1, 1).val()

    result = reg.build({"z": 100}, root=tmp_path, write=False)
    assert result.geometry["parts"]["cup"]["instances"][0]["bbox"]["min"][2] == pytest.approx(95, abs=1e-3)
    assert result.geometry["cavities"]["cup_void"]["bbox"]["min"][2] == pytest.approx(96, abs=1e-3)
    pegs = result.geometry["parts"]["peg"]["instances"]
    assert [round(i["bbox"]["min"][0] + 0.5, 3) for i in pegs] == [0, 20, 40]
    assert not (tmp_path / "exports").exists()                       # write=False writes nothing

    @reg.cavity("peg", "peg_void")
    def peg_void(p):
        return cq.Workplane().box(0.5, 0.5, 0.5).val()
    with pytest.raises(RegistryError, match="'peg' has 3 instances"):
        reg.build({"z": 0}, root=tmp_path, write=False)


def test_build_errors_name_the_declaration(tmp_path):
    pytest.importorskip("cadquery")
    reg = Registry()

    @reg.part("broken")
    def broken(p):
        return p["missing"]
    with pytest.raises(RegistryError, match=r"part 'broken' \(.*test_dossier_registry.py:\d+\) failed: KeyError"):
        reg.build({}, root=tmp_path, write=False)
    reg.clear()

    @reg.part("nothing")
    def nothing(p):
        return None
    with pytest.raises(RegistryError, match="returned None"):
        reg.build({}, root=tmp_path, write=False)


def test_declaration_validation_needs_no_kernel():
    reg = Registry()
    with pytest.raises(RegistryError, match="without a reason"):
        reg.part("ball", free=True)
    with pytest.raises(RegistryError, match="both grounded and free"):
        reg.part("ball", free=True, reason="x", grounded=True)
    with pytest.raises(RegistryError, match="not a valid dossier id"):
        reg.part("3d")
    with pytest.raises(RegistryError, match="kind 'hinge'"):
        reg.joint("I1", kind="hinge", parts=("a", "b"), axis=((0, 0, 0), (0, 0, 1)))
    with pytest.raises(RegistryError, match="needs range_deg"):
        reg.joint("I1", kind="revolute", parts=("a", "b"), axis=((0, 0, 0), (0, 0, 1)))
    with pytest.raises(RegistryError, match="needs range_deg and range_mm"):
        reg.joint("I1", kind="cylindrical", parts=("a", "b"), axis=((0, 0, 0), (0, 0, 1)), range_deg=(0, 1))
    with pytest.raises(RegistryError, match="low is above high"):
        reg.joint("I1", kind="slider", parts=("a", "b"), axis=((0, 0, 0), (0, 0, 1)), range_mm=(5, 1))
    with pytest.raises(RegistryError, match=r"\(moving, fixed\)"):
        reg.joint("I1", parts=("a", "a"), axis=((0, 0, 0), (0, 0, 1)), range_deg=(0, 1))
    with pytest.raises(RegistryError, match="zero vector"):
        reg.joint("I1", parts=("a", "b"), axis=((0, 0, 0), (0, 0, 0)), range_deg=(0, 1))
    with pytest.raises(RegistryError, match="direction"):
        reg.assembly.step(1, fit="a", direction="down")
    assert len(reg) == 0


def test_same_site_replaces_another_site_raises():
    reg = Registry()
    for _ in range(2):          # the same declaration run twice (a re-import) replaces itself
        reg.fastener("m3", clamps="a", into="b", at=[Axis((0, 0, 0), (0, 0, -1))])
    assert len(reg.fasteners) == 1
    with pytest.raises(RegistryError, match="declared twice"):
        reg.fastener("m3", clamps="a", into="b", at=[Axis((1, 0, 0), (0, 0, -1))])
    reg.fastener("m3", clamps="a", into="b", at=[Axis((1, 0, 0), (0, 0, -1))], name="second_row")
    assert set(reg.fasteners) == {"m3:a-b", "second_row"}

    @reg.part("a")
    def a(p): ...
    with pytest.raises(RegistryError, match="part 'a' is declared twice"):
        @reg.part("a")
        def a2(p): ...


def test_joint_works_bare_or_decorated():
    reg = Registry()
    reg.joint("I1", kind="slider", parts=("a", "b"), axis=((0, 0, 0), (1, 0, 0)), range_mm=(0, 10))

    @reg.joint("I2", kind="fixed", parts=("a", "c"), axis=((0, 0, 0), (0, 0, 2)))
    def body(p):
        return "never called by build"
    assert reg.joints["I2"].body is body and reg.joints["I2"].axis.direction == (0.0, 0.0, 1.0)
    assert reg.joints["I1"].range == (0.0, 10.0) and reg.joints["I1"].unit == "mm"


def test_join_needs_only_the_json(tmp_path):
    """The lint joins cards with dossier-geometry.json without the CAD kernel (core CI runs this)."""
    make_project(tmp_path)
    d = load_dossier(tmp_path / "dossier" / "project.yaml")
    part = lambda section, n=1: {"section": section, "count": n, "declared_at": "cad/build.py:7"}
    geo = {"parts": {"bench_base": part("S1"), "pan_base": part("S1"), "hopper": part("S3"), "ball": part("S3", 8),
                     "extra_bracket": part("S1")},
           "cavities": {"hopper_cavity": {"part": "hopper", "declared_at": "cad/build.py:9"}},
           "joints": {"I9": {"kind": "revolute", "moving": "hopper_flap", "fixed": "hopper",
                             "declared_at": "cad/build.py:12"}},
           "fasteners": {"f": {"key": "screw_m3x8", "clamps": "hopper", "into": "pan_base", "via": "I7", "count": 4,
                               "declared_at": "cad/build.py:20"}},
           "assembly": {"steps": []}}
    issues = sorted((i.code, i.message.split("'")[1]) for i in join(d, geo))
    assert issues == [("card-without-shape", "hopper_flap"), ("shape-without-card", "extra_bracket")]


# ------------------------------------------------------------------------------- review #26 regressions

PARAM_BUILD = textwrap.dedent('''\
    import json
    from pathlib import Path
    import cadquery as cq

    def print_parts():
        w = json.loads((Path(__file__).parent / "parameters.json").read_text())["width"]
        return {"plate": cq.Workplane().box(w, 10, 2).val()}
    ''')


def _project(root: Path, build: str, params=None) -> Path:
    (root / "cad").mkdir(parents=True, exist_ok=True)
    (root / "cad-agent.yaml").write_text("cad:\n  name: t\n")
    (root / "cad" / "build.py").write_text(build)
    (root / "cad" / "parameters.json").write_text(json.dumps(params or {"width": 10}))
    return root / "cad" / "build.py"


def test_second_build_records_the_new_print_parts_shapes(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    script = _project(tmp_path, PARAM_BUILD)
    first = build_module(script, write=False)
    (tmp_path / "cad" / "parameters.json").write_text(json.dumps({"width": 40}))
    second = build_module(script, write=False)
    xmax = lambda r: r.geometry["parts"]["plate"]["instances"][0]["bbox"]["max"][0]
    assert (xmax(first), xmax(second)) == (5.0, 20.0)
    # the same Registry fed twice through the migration path also takes the new shapes
    import cadquery as cq
    reg = Registry()
    reg.add_build_items({"plate": cq.Workplane().box(10, 10, 2).val()}, where="b.py:0")
    reg.add_build_items({"plate": cq.Workplane().box(40, 10, 2).val()}, where="b.py:0")
    assert reg.build({}, root=tmp_path, write=False).geometry["parts"]["plate"]["instances"][0]["bbox"]["max"][0] == 20


def test_builds_do_not_leak_between_projects(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    helper = "import cadquery as cq\nfrom cadagent.review.dossier import part\n\n@part('{name}')\ndef {name}(p):\n" \
             "    return cq.Workplane().box(1, 1, 1).val()\n"
    a = _project(tmp_path / "a", "import lid_part\nfrom cadagent.review.dossier import part\nimport cadquery as cq\n\n"
                                 "@part('base')\ndef base(p):\n    return cq.Workplane().box(5, 5, 1).val()\n")
    (tmp_path / "a" / "cad" / "lid_part.py").write_text(helper.format(name="lid"))
    b = _project(tmp_path / "b", "from cadagent.review.dossier import part\nimport cadquery as cq\n\n"
                                 "@part('bracket')\ndef bracket(p):\n    return cq.Workplane().box(2, 2, 2).val()\n")
    assert set(build_module(a, write=False).parts) == {"lid", "base"}
    assert set(build_module(b, write=False).parts) == {"bracket"}
    # a helper module imported by the script runs its declarations again on the next build
    assert set(build_module(a, write=False).parts) == {"lid", "base"}
    assert len(REGISTRY) == 0, "build_module never writes to the global registry"


def test_dossier_items_with_fasteners_and_steps_builds_twice(tmp_path):
    pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module
    script = _project(tmp_path, textwrap.dedent('''\
        import cadquery as cq
        from cadagent.review.dossier import Axis

        def print_parts():
            return {"lid": cq.Workplane().box(10, 10, 2).translate((0, 0, 1)).val(),
                    "base": cq.Workplane().box(10, 10, 2).translate((0, 0, -1)).val()}

        def dossier_items():
            return {"fasteners": [{"key": "m3x8", "clamps": "lid", "into": "base", "at": [Axis((0, 0, 2), (0, 0, -1))]}],
                    "joints": [{"interface": "I1", "kind": "fixed", "parts": ("lid", "base"),
                                "axis": Axis((0, 0, 0), (0, 0, 1))}],
                    "assembly": [{"order": 1, "fit": "lid", "onto": "base", "direction": "-Z"}]}
        '''))
    reg = Registry()
    for _ in range(2):          # the same registry, twice: re-running the declarations replaces them
        result = build_module(script, registry=reg, write=False)
    geo = result.geometry
    assert geo["fasteners"]["m3x8:lid-base"]["declared_at"] == "cad/build.py:0 (fastener m3x8:lid-base)"
    assert geo["joints"]["I1"]["declared_at"] == "cad/build.py:0 (joint I1)"
    assert geo["assembly"]["steps"][0]["declared_at"] == "cad/build.py:0 (step 1)"
    with pytest.raises(RegistryError, match="without an 'interface'"):
        Registry().add_build_items({}, {"joints": [{"kind": "fixed", "parts": ("a", "b"), "axis": ((0, 0, 0), (0, 0, 1))}]})


def test_fastener_cannot_take_a_part_name(tmp_path):
    cq = pytest.importorskip("cadquery")
    reg = Registry()
    reg.part("lid")(lambda p: cq.Workplane().box(10, 10, 2).val())
    with pytest.raises(RegistryError, match="also a part name"):
        reg.fastener("m3", name="lid", clamps="lid", into="lid", at=[Axis((0, 0, 1), (0, 0, -1))])
    with pytest.raises(RegistryError, match="no '#'"):
        reg.fastener("m3", name="m3#1", clamps="lid", into="lid", at=[Axis((0, 0, 1), (0, 0, -1))])
    late = Registry()               # fastener declared first, the part of the same name after: refused at build
    late.fastener("m3", name="lid", clamps="lid", into="lid", at=[Axis((0, 0, 1), (0, 0, -1))],
                  shape=lambda p: cq.Workplane().circle(1.5).extrude(-8).val())
    late.part("lid")(lambda p: cq.Workplane().box(10, 10, 2).val())
    with pytest.raises(RegistryError, match="also a part name"):
        late.build({}, root=tmp_path, write=False)
    ok = Registry()
    ok.part("lid")(lambda p: cq.Workplane().box(10, 10, 2).val())
    ok.fastener("m3", clamps="lid", into="lid", at=[Axis((0, 0, 1), (0, 0, -1))],
                shape=lambda p: cq.Workplane().circle(1.5).extrude(-8).val())
    result = ok.build({}, root=tmp_path, write=False)
    shapes = result.assembly_shapes()
    assert shapes["lid"].Volume() == pytest.approx(200) and result.kind("lid") == "part"
    assert result.kind("m3:lid-lid") == "fastener" and result.kind("nothing") is None


def test_cavity_needs_a_single_instance_part(tmp_path):
    cq = pytest.importorskip("cadquery")
    reg = Registry()
    reg.part("cup")(lambda p: [cq.Workplane().box(10, 10, 10).val(),
                               cq.Workplane().box(10, 10, 10).translate((50, 0, 0)).val()])
    reg.cavity("cup", "cup_void")(lambda p: cq.Workplane().box(8, 8, 8).val())
    with pytest.raises(RegistryError, match="'cup' has 2 instances"):
        reg.build({}, root=tmp_path, write=False)


def test_part_flags_are_checked_on_every_path():
    reg = Registry()
    with pytest.raises(RegistryError, match="both grounded and free"):
        reg.add_build_items({"base": object()}, {"parts": {"base": {"grounded": True, "free": True, "reason": "x"}}})
    with pytest.raises(RegistryError, match="without a reason"):
        reg.add_build_items({"base": object()}, {"parts": {"base": {"free": True, "reason": "   "}}})
    with pytest.raises(RegistryError, match="without a reason"):
        reg.part("ball", free=True, reason=" \t")


def test_root_is_the_project_and_records_hold_no_machine_paths(tmp_path, monkeypatch):
    cq = pytest.importorskip("cadquery")
    from cadagent.review.dossier import build_module, load_geometry
    script = _project(tmp_path / "proj", PARAM_BUILD.replace("def print_parts", "from cadagent.review.dossier "
                                                             "import part\n\n@part('tag')\ndef tag(p):\n"
                                                             "    return cq.Workplane().box(1, 1, 1).val()\n\n"
                                                             "def print_parts"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("CAD_AGENT_ACTOR", "agent-test-1")
    result = build_module(script, out_dir="build/geo")
    proj = (tmp_path / "proj").resolve()
    assert result.root == proj and (proj / "build" / "geo" / "dossier-geometry.json").is_file()
    assert not (elsewhere / "build").exists() and not (elsewhere / "exports").exists()
    geo = result.geometry
    assert geo["actor"] == "agent-test-1" and geo["out_dir"] == "build/geo"
    assert geo["parts"]["tag"]["declared_at"] == "cad/build.py:7"
    assert str(tmp_path) not in json.dumps(geo)
    again = load_geometry(proj / "build" / "geo" / "dossier-geometry.json", shapes=False)
    assert again.root == proj
    # a declaration from a file outside the project is recorded by its file name only
    reg = Registry()
    reg.part("ext")(lambda p: cq.Workplane().box(1, 1, 1).val())
    rec = reg.build({}, root=proj, write=False).geometry["parts"]["ext"]["declared_at"]
    assert rec.startswith("test_dossier_registry.py:")
    with pytest.raises(RegistryError, match="outside the project root"):
        reg.build({}, root=proj, out_dir="../out", write=False)


def test_use_registry_scopes_the_module_level_declarations():
    from cadagent.review.dossier import current_registry, part, use_registry
    with use_registry() as reg:
        assert current_registry() is reg

        @part("scoped")
        def scoped(p): ...
    assert "scoped" in reg.parts and len(REGISTRY) == 0 and current_registry() is REGISTRY


def test_shared_content_hash_and_hand_over_with_hashes(built):
    import cadquery as cq
    from cadagent.review import evidence
    from cadagent.review.dossier import load_geometry, shape_sha256
    root, result = built
    assert shape_sha256 is evidence.shape_content_hash
    pairs = result.assembly_shapes(with_hashes=True)
    shape, digest = pairs["ball#3"]
    assert digest == evidence.shape_content_hash(shape) == result.geometry["parts"]["ball"]["instances"][3]["sha256"]
    assert set(pairs) == set(result.assembly_shapes())
    # read back in another process: the recorded hashes travel with the shapes, nothing is re-hashed
    again = load_geometry(root / "exports" / "dossier-geometry.json")
    assert {k: h for k, (_, h) in again.assembly_shapes(with_hashes=True).items()} == \
        {k: h for k, (_, h) in pairs.items()}
    assert again.content_hashes()["hopper_cavity"] == result.geometry["cavities"]["hopper_cavity"]["sha256"]
    reg = Registry()
    reg.part("box")(lambda p: cq.Workplane().box(1, 1, 1).val())
    reg.cavity("box", "box")(lambda p: cq.Workplane().box(0.5, 0.5, 0.5).val())
    with pytest.raises(RegistryError, match="cavity name 'box'"):
        reg.build({}, root=root, write=False)


# ------------------------------------------------------------------------------- driven (mimic) joints (#581)

def test_a_driven_joint_is_checked_where_it_is_declared():
    """``follows`` and ``closes`` are validated on the call, without a kernel; what needs the whole table (an
    unknown driver, a loop) waits for the build."""
    reg, z = Registry(), ((0, 0, 0), (0, 0, 1))
    reg.joint("I1", parts=("a", "b"), axis=z, range_deg=(0, 30))
    reg.joint("I2", parts=("c", "b"), axis=z, follows="I1")                              # no range of its own
    reg.joint("I3", kind="slider", parts=("d", "b"), axis=z, range_mm=(0, 9), follows=("I1", 0.3),
              closes={"parts": ("d", "c"), "at": lambda p: (0, 0, p["h"]), "tol_mm": 0.5})
    reg.joint("I4", parts=("e", "b"), axis=z, range_deg=(-35, 5), follows=("I2", -1, 5))
    assert reg.joints["I2"].follows == {"joint": "I1", "multiplier": 1.0, "offset": 0.0}
    assert reg.joints["I2"].range is None and reg.joints["I2"].unit == "deg"
    assert reg.joints["I3"].follows == {"joint": "I1", "multiplier": 0.3, "offset": 0.0}
    assert reg.joints["I4"].follows == {"joint": "I2", "multiplier": -1.0, "offset": 5.0}
    assert reg.joints["I1"].follows is None and reg.joints["I1"].closes == []
    for kwargs, match in (
            ({"follows": "I9", "kind": "cylindrical", "range_deg": (0, 1), "range_mm": (0, 1)},
             "a cylindrical joint cannot follow another"),
            ({"follows": "I9", "kind": "fixed"}, "a fixed joint cannot follow another"),
            ({"follows": "I9", "kind": "ball"}, "a ball joint cannot follow another"),
            ({"follows": "I5"}, "follows itself"),
            ({"follows": ("I1", 0)}, "multiplier 0"),
            ({"follows": ("I1", "twice")}, r"follows is a joint id, \(joint, multiplier\)"),
            ({"follows": {"joint": "I1", "ratio": 2}}, r"follows is \{joint, multiplier, offset\}"),
            ({"follows": "I1", "range_mm": (0, 5)}, "its range is range_deg, not range_mm"),
            ({"follows": "I1", "kind": "slider", "range_deg": (0, 5)}, "its range is range_mm, not range_deg"),
            ({"range_deg": (0, 1), "closes": {"parts": ("a", "a"), "at": (0, 0, 0)}}, "closes names two different parts"),
            ({"range_deg": (0, 1), "closes": [{"parts": ("a", "b")}]}, r"closes is \{parts"),
            ({"range_deg": (0, 1), "closes": {"parts": "ab", "at": (0, 0, 0)}}, r"closes is \{parts"),
            ({"follows": "I1", "samples": 9}, "is not sampled: set samples on the joint that drives it"),
            ({"follows": "I1", "kind": "hinge"}, "kind 'hinge'"),
            ({"range_deg": (0, 1), "closes": 7}, "joint 'I5'")):
        with pytest.raises(RegistryError, match=match):
            reg.joint("I5", **{"parts": ("f", "b"), "axis": z, **kwargs})
    assert set(reg.joints) == {"I1", "I2", "I3", "I4"}
    # dossier_items() takes the same keys
    legacy = Registry()
    legacy.add_build_items({}, {"joints": [
        {"interface": "I1", "parts": ("a", "b"), "axis": z, "range_deg": (0, 30)},
        {"interface": "I2", "parts": ("c", "b"), "axis": z, "follows": ("I1", -1),
         "closes": [{"parts": ("c", "a"), "at": (1, 2, 3)}]}]})
    assert legacy.joints["I2"].follows == {"joint": "I1", "multiplier": -1.0, "offset": 0.0}
    assert legacy.joints["I2"].closes[0]["at"] == (1, 2, 3)


def test_a_build_refuses_an_unknown_driver_and_followers_in_a_loop(tmp_path):
    z = ((0, 0, 0), (0, 0, 1))
    lost = Registry()
    lost.joint("I1", parts=("a", "b"), axis=z, follows="I-nowhere")
    with pytest.raises(RegistryError, match=r"joint 'I1' \(.*\) cannot be driven: it follows 'I-nowhere', which is "
                                            "not a declared joint"):
        lost.build({}, root=tmp_path, write=False)
    loop = Registry()
    loop.joint("I1", parts=("a", "b"), axis=z, follows="I2")
    loop.joint("I2", parts=("c", "b"), axis=z, follows=("I3", 2))
    loop.joint("I3", parts=("d", "b"), axis=z, follows="I1")
    with pytest.raises(RegistryError, match="joints I1 -> I2 -> I3 -> I1 follow each other in a loop"):
        loop.build({}, root=tmp_path, write=False)
    on_cyl = Registry()
    on_cyl.joint("I1", kind="cylindrical", parts=("a", "b"), axis=z, range_deg=(0, 9), range_mm=(0, 9))
    on_cyl.joint("I2", parts=("c", "b"), axis=z, follows="I1")
    with pytest.raises(RegistryError, match="it follows I1, a cylindrical joint"):
        on_cyl.build({}, root=tmp_path, write=False)


def _lift_registry():
    """The parallelogram lift of tests/review/test_gate_motion.py, declared the way a build script does."""
    cq = pytest.importorskip("cadquery")
    reg, up = Registry(), (0, -1, 0)
    reg.part("tower", grounded=True)(lambda p: cq.Solid.makeBox(20, 10, 70, cq.Vector(-10, -10, -10)))
    reg.part("lower_arm")(lambda p: cq.Solid.makeBox(110, 5, 10, cq.Vector(-5, 1, -5)))
    reg.part("upper_arm")(lambda p: cq.Solid.makeBox(110, 5, 10, cq.Vector(-5, 1, p["rise"] - 5)))
    reg.part("cradle")(lambda p: cq.Solid.makeBox(35, 5, 70, cq.Vector(90, 7, -10)).fuse(
        cq.Solid.makeBox(13, 6, 70, cq.Vector(112, 1, -10))))
    reg.joint("I-lower", parts=("lower_arm", "tower"), axis=Axis((0, 0, 0), up), range_deg=(0, 30), samples=5)
    reg.joint("I-upper", parts=("upper_arm", "tower"), axis=lambda p: Axis((0, 0, p["rise"]), up), follows="I-lower")
    reg.joint("I-cradle", parts=("cradle", "lower_arm"), axis=Axis((100, 0, 0), up), range_deg=(-30, 0),
              follows=("I-lower", -1), closes={"parts": ("cradle", "upper_arm"), "at": lambda p: (100, 0, p["rise"])})
    return reg


def test_driven_joints_reach_the_geometry_record_and_every_reader_of_it(tmp_path):
    from cadagent.review.dossier import load_geometry
    from cadagent.review.gates import Assembly
    from cadagent.review.gates.motion import motion_from_build
    from cadagent.review.gates.relations import moving_bodies
    result = _lift_registry().build({"rise": 50}, root=tmp_path)
    geo = json.loads((tmp_path / "exports" / "dossier-geometry.json").read_text())       # plain JSON on disk
    joints = geo["joints"]
    assert joints["I-upper"]["follows"] == {"joint": "I-lower", "multiplier": 1.0, "offset": 0.0}
    assert joints["I-upper"]["range"] is None and joints["I-upper"]["unit"] == "deg"
    assert joints["I-cradle"]["follows"] == {"joint": "I-lower", "multiplier": -1.0, "offset": 0.0}
    assert joints["I-cradle"]["range"] == [-30, 0]
    assert joints["I-cradle"]["closes"] == [{"parts": ["cradle", "upper_arm"], "at": [100.0, 0.0, 50.0], "tol_mm": 0.1}]
    # a joint that declares neither keeps the record it always had, so records without driven joints keep their digest
    assert set(joints["I-lower"]) == {"kind", "moving", "fixed", "axis", "range", "unit", "intended_contacts",
                                      "samples", "declared_at"}
    assert result.joints["I-cradle"]["closes"] == joints["I-cradle"]["closes"]
    # body labels are a matter of what is fastened to what: a follower's body is its own, as any joint's is
    assert moving_bodies(joints, {}, ["tower"]) == {"lower_arm": "lower_arm", "upper_arm": "upper_arm",
                                                    "cradle": "cradle"}
    for source in (result, load_geometry(tmp_path / "exports" / "dossier-geometry.json")):
        asm = Assembly.from_build(source)
        assert {n: asm[n].body for n in asm.names} == {"tower": "tower", "lower_arm": "lower_arm",
                                                       "upper_arm": "upper_arm", "cradle": "cradle"}
        assert asm.joints["I-upper"]["follows"]["joint"] == "I-lower"
        v = motion_from_build(source)
        assert v["pass"] and v["findings"] == [], v["findings"]
        assert v["groups"][0]["poses"] == 5 and sorted(v["driven"]) == ["I-cradle", "I-upper"]
        assert v["groups"][0]["closures"][0]["status"] == "pass"


def test_the_join_names_a_follower_whose_driver_is_missing_from_a_hand_written_record(tmp_path):
    make_project(tmp_path)
    d = load_dossier(tmp_path / "dossier" / "project.yaml")
    part = lambda section, n=1: {"section": section, "count": n, "declared_at": "cad/build.py:7"}
    geo = {"parts": {"bench_base": part("S1"), "pan_base": part("S1"), "hopper": part("S3"), "ball": part("S3", 8),
                     "hopper_flap": part("S4")},
           "cavities": {"hopper_cavity": {"part": "hopper", "declared_at": "cad/build.py:9"}},
           "joints": {"I9": {"kind": "revolute", "moving": "hopper_flap", "fixed": "hopper",
                             "follows": {"joint": "I-gone", "multiplier": 1.0, "offset": 0.0},
                             "closes": [{"parts": ["hopper_flap", "ghost"], "at": [0, 0, 0], "tol_mm": 0.1}],
                             "declared_at": "cad/build.py:12"}},
           "fasteners": {"f": {"key": "screw_m3x8", "clamps": "hopper", "into": "pan_base", "via": "I7", "count": 4,
                               "declared_at": "cad/build.py:20"}},
           "assembly": {"steps": []}}
    issues = sorted((i.code, i.message) for i in join(d, geo))
    assert issues == [("unknown-joint", "joint 'I9' follows 'I-gone', which is not a declared joint"),
                      ("unknown-part", "joint 'I9' closes 'ghost', which is not a part")]
    # every spelling the motion gate reads is read here too; a malformed one is the gate's to report, not a crash
    for spelling in ("I-gone", ["I-gone", -1], ("I-gone", 2, 5)):
        geo["joints"]["I9"]["follows"] = spelling
        geo["joints"]["I9"]["closes"] = {"parts": ["hopper_flap", "ghost"], "at": [0, 0, 0]}
        assert sorted(i.code for i in join(d, geo)) == ["unknown-joint", "unknown-part"]
    geo["joints"]["I9"].update(follows=["I-gone", "twice"], closes=[{"parts": ["hopper_flap", "ball#3"], "at": [0, 0, 0]}])
    assert join(d, geo) == []
    geo["parts"]["ball"]["instances"] = [{"key": "ball#3"}]
    geo["joints"]["I9"]["follows"] = None
    assert join(d, geo) == []                               # an instance key is a place for a point
