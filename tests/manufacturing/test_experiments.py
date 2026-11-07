"""Persistent specimen lookup binds immutable source, physical copies and actual bytes."""
import json
import subprocess
from pathlib import Path

import pytest

from cadagent.manufacturing import experiments as ex


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    git("remote", "add", "origin", "https://example.invalid/design.git")
    (root / "model.py").write_text("# immutable generator fixture\n")
    (root / "parameters.json").write_text('{"nominal_mm": 5}')
    git("add", ".")
    git("commit", "-qm", "Freeze model")
    return root


def allocate(registry, source, **kwargs):
    snapshot = ex.source_snapshot(source, "model.py", ["model.py", "parameters.json"],
                                  repository="https://example.invalid/design")
    return ex.allocate(registry, source=snapshot, parameters={"nominal_mm": 5},
                       process={"nozzle_mm": 0.4, "status": "design assumption"},
                       material={"kind": "PLA", "brand": "unknown"}, **kwargs)


def test_physical_copies_have_new_persistent_ids_and_resolve_after_reload(source, tmp_path):
    registry = tmp_path / "registry"
    a, b = allocate(registry, source), allocate(registry, source)
    assert a["identity"]["uuid"] != b["identity"]["uuid"]
    assert a["identity"]["short_id"] != b["identity"]["short_id"]
    assert a["identity"]["parameters"] == b["identity"]["parameters"]
    for row in (a, b):
        assert ex.lookup(registry, row["identity"]["short_id"].lower()) == row
        assert ex.lookup(registry, row["identity"]["uuid"]) == row
    with pytest.raises(ValueError, match="unknown"):
        ex.lookup(registry, "DEADBEEF01")


def test_collision_is_checked_against_previous_registry_not_current_plate(source, tmp_path):
    registry = tmp_path / "registry"
    a = allocate(registry, source, full_uuid="12345678-90ab-4cde-8012-345678901234")
    before = {p.name: p.read_bytes() for p in registry.iterdir()}
    with pytest.raises(ValueError, match="already allocated"):
        allocate(registry, source, full_uuid="12345678-90ff-4cde-8012-345678901235")
    assert {p.name: p.read_bytes() for p in registry.iterdir()} == before
    with pytest.raises(ValueError, match="already allocated"):
        allocate(registry, source, full_uuid=a["identity"]["uuid"])


def test_changed_or_duplicated_identity_is_rejected_on_actual_lookup(source, tmp_path):
    registry = tmp_path / "registry"
    row = allocate(registry, source)
    short = row["identity"]["short_id"]
    original = registry / (short + ".identity.json")
    raw = original.read_bytes()
    row["identity"]["parameters"]["nominal_mm"] = 7
    original.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="changed"):
        ex.lookup(registry, short)
    original.write_bytes(raw)
    (registry / "duplicate.identity.json").write_bytes(raw)
    with pytest.raises(ValueError, match="identity"):
        ex.lookup(registry, short)


def test_source_requires_actual_committed_bytes_and_origin(source):
    args = (source, "model.py", ["model.py", "parameters.json"])
    with pytest.raises(ValueError, match="origin"):
        ex.source_snapshot(*args, repository="https://wrong.invalid/design")
    (source / "model.py").write_text("# dirty generator\n")
    with pytest.raises(ValueError, match="tracked changes"):
        ex.source_snapshot(*args, repository="https://example.invalid/design")
    subprocess.run(["git", "-C", str(source), "restore", "model.py"], check=True)
    (source / "untracked.py").write_text("# not in source revision\n")
    with pytest.raises(ValueError, match="not committed"):
        ex.source_snapshot(source, "untracked.py", ["untracked.py"], repository="https://example.invalid/design")
    with pytest.raises(ValueError, match="including the model"):
        ex.source_snapshot(source, "model.py", ["parameters.json"], repository="https://example.invalid/design")


def test_artifact_and_observations_never_rewrite_identity_or_previous_records(source, tmp_path):
    registry, outputs = tmp_path / "registry", tmp_path / "outputs"
    outputs.mkdir()
    row = allocate(registry, source)
    short = row["identity"]["short_id"]
    identity_file = registry / (short + ".identity.json")
    raw = identity_file.read_bytes()
    (outputs / "coupon.stl").write_bytes(b"actual artifact fixture")
    manifest = ex.bind_artifacts(registry, short, outputs, ["coupon.stl"])
    assert ex.verify_artifacts(registry, short, outputs) == manifest
    with pytest.raises(ValueError, match="already exists"):
        ex.bind_artifacts(registry, short, outputs, ["coupon.stl"])
    event = ex.append_observation(registry, short, outputs, kind="attempt",
                                  payload={"observer": "fixture reviewer", "state": "unknown", "job_id": None})
    feedback = ex.append_observation(registry, short, outputs, kind="feedback",
                                     payload={"observer": "fixture reviewer", "function": "not tested", "cycles": None})
    assert event["uuid"] == feedback["uuid"] == row["identity"]["uuid"]
    assert event["artifacts_sha256"] == feedback["artifacts_sha256"]
    assert identity_file.read_bytes() == raw
    saved = {p.name: p.read_bytes() for p in registry.iterdir()}
    with pytest.raises(ValueError, match="already exists"):
        ex.append_observation(registry, short, outputs, kind="feedback", payload={"observer": "fixture reviewer", "different": True},
                              event_uuid=event["event_uuid"])
    assert {p.name: p.read_bytes() for p in registry.iterdir()} == saved
    (outputs / "coupon.stl").write_bytes(b"wrong replacement")
    with pytest.raises(ValueError, match="artifact bytes"):
        ex.verify_artifacts(registry, short, outputs)
    with pytest.raises(ValueError, match="artifact bytes"):
        ex.append_observation(registry, short, outputs, kind="feedback", payload={"observer": "fixture reviewer", "function": "pass"})
    assert {p.name: p.read_bytes() for p in registry.iterdir()} == saved


def test_invalid_artifact_set_cannot_publish_a_manifest(source, tmp_path):
    registry = tmp_path / "registry"
    row = allocate(registry, source)
    short = row["identity"]["short_id"]
    before = {p.name: p.read_bytes() for p in registry.iterdir()}
    for names in ([], ["missing.stl"], ["../escape.stl"]):
        with pytest.raises(ValueError):
            ex.bind_artifacts(registry, short, tmp_path, names)
        assert {p.name: p.read_bytes() for p in registry.iterdir()} == before


def plate_fixture(tmp_path, source):
    """Real STL/project writers, hand-built boxes; no CAD kernel, GUI or slicing."""
    import hashlib
    import numpy as np
    import trimesh
    from cadagent.manufacturing import plates as p
    from tests.manufacturing.test_plates import settings_bytes, box
    registry, root = tmp_path / "registry", tmp_path / "artifacts"
    root.mkdir()
    settings = settings_bytes(printer_settings_id="Fixture printer", print_settings_id="Fixture process",
                              filament_settings_id=["Fixture PLA"])
    snapshot = ex.source_snapshot(source, "model.py", ["model.py"], repository="https://example.invalid/design")
    stamps, meshes = [], {}
    for dimensions in ((6, 5, 2), (8, 4, 3)):
        row = ex.allocate(registry, source=snapshot, parameters={"box_mm": list(dimensions)},
                          process={"project_settings_sha256": hashlib.sha256(settings).hexdigest()},
                          material={"profile_id": "Fixture PLA"})
        stamp = row["identity"]["short_id"]
        vertices, faces = box(*dimensions)
        trimesh.Trimesh(vertices=vertices, faces=faces).export(root / (stamp + ".stl"))
        mesh = trimesh.load_mesh(root / (stamp + ".stl"), process=True)
        meshes[stamp] = (p._normalised(mesh.vertices), np.asarray(mesh.faces))
        ex.bind_artifacts(registry, stamp, root, [stamp + ".stl"])
        stamps.append(stamp)
    copies = [p.Copy(s, 1, p.footprint(meshes[s][0]), "Fixture PLA") for s in stamps]
    packed = p.pack(copies, (256, 256), keep_out=[(0, 0, 18, 28)])
    p.write_plates_3mf(root / "plate.3mf", meshes, packed, bed_xy=(256, 256), gap=2, margin=5,
                       keep_out=[(0, 0, 18, 28)], extruders={s: 1 for s in stamps}, project_settings=settings)
    return registry, root, stamps


def test_real_project_readback_binds_one_actual_mesh_and_settings_per_physical_id(tmp_path, source):
    registry, root, stamps = plate_fixture(tmp_path, source)
    record = ex.bind_plate(registry, stamps, root, "plate.3mf")
    assert {r["placement"]["part"] for r in record["specimens"]} == set(stamps)
    assert len({r["uuid"] for r in record["specimens"]}) == 2
    assert record["settings"]["printer_settings_id"] == "Fixture printer"
    assert record["sliced"] is record["gui_verified"] is record["physical_qualification"] is False
    with pytest.raises(ValueError, match="occur once"):
        ex.bind_plate(registry, stamps + stamps[:1], root, "plate.3mf")


@pytest.mark.parametrize("fault", ["wrong-object", "wrong-mesh", "wrong-settings", "scaled-transform", "missing-specimen"])
def test_real_project_faults_cannot_publish_a_fresh_plate_record(tmp_path, source, fault):
    import zipfile
    registry, root, stamps = plate_fixture(tmp_path, source)
    path = root / "plate.3mf"
    with zipfile.ZipFile(path) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    model = members["3D/3dmodel.model"].decode()
    if fault == "wrong-object":
        model = model.replace('name="' + stamps[0] + '"', 'name="DEADBEEF01"', 1)
    elif fault == "wrong-mesh":
        import re
        model, count = re.subn(r'(<vertex x=")[^"]+', r'\g<1>999', model, count=1)
        assert count == 1
    elif fault == "scaled-transform":
        import re
        def scale(match):
            values = [float(v) for v in match[1].split()]
            assert len(values) == 12
            return 'transform="' + ' '.join(str(v*2 if i < 9 else v) for i, v in enumerate(values)) + '"'
        model, count = re.subn(r'transform="([^"]+)"', scale, model, count=1)
        assert count == 1
    elif fault == "missing-specimen":
        import re
        model, count = re.subn(r'<item [^>]+/>', '', model, count=1)
        assert count == 1
    else:
        settings = json.loads(members["Metadata/project_settings.config"])
        settings["print_settings_id"] = "Changed process"
        members["Metadata/project_settings.config"] = json.dumps(settings).encode()
    members["3D/3dmodel.model"] = model.encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    before = {p.name: p.read_bytes() for p in registry.iterdir()}
    with pytest.raises(ValueError):
        ex.bind_plate(registry, stamps, root, "plate.3mf")
    assert {p.name: p.read_bytes() for p in registry.iterdir()} == before


def example_module():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "docs/examples/numbered-coupons/build.py"
    spec = importlib.util.spec_from_file_location("numbered_coupon_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_example_output_is_rejected_before_allocating_or_importing_cad(tmp_path):
    output, registry = tmp_path / "previous", tmp_path / "registry"
    output.mkdir()
    (output / "old.3mf").write_bytes(b"prior real work")
    with pytest.raises(ValueError, match="output already exists"):
        example_module().build(registry, output, b"invalid settings")
    assert not registry.exists()
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {"old.3mf": b"prior real work"}


def test_numbered_example_real_native_plate_and_new_copy_preserve_prior_artifacts(tmp_path):
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    from tests.manufacturing.test_plates import settings_bytes
    native = settings_bytes(printer_settings_id="Fixture printer", print_settings_id="Fixture process",
                             filament_settings_id=["Fixture PLA"])
    registry = tmp_path / "version-controlled-records"
    module = example_module()
    first = module.build(registry, tmp_path / "first", native, count=1)
    stamp = first["specimens"][0]["placement"]["part"]
    assert ex.verify_artifacts(registry, stamp, tmp_path / "first")
    previous = {p.relative_to(tmp_path / "first").as_posix(): p.read_bytes()
                for p in (tmp_path / "first").rglob("*") if p.is_file()}
    second = module.build(registry, tmp_path / "deliberate-new-copy", native, count=1)
    assert first["specimens"][0]["uuid"] != second["specimens"][0]["uuid"]
    assert first["specimens"][0]["placement"]["part"] != second["specimens"][0]["placement"]["part"]
    assert ex.verify_artifacts(registry, stamp, tmp_path / "first")
    assert previous == {p.relative_to(tmp_path / "first").as_posix(): p.read_bytes()
                        for p in (tmp_path / "first").rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="output already exists"):
        module.build(registry, tmp_path / "first", native, count=1)
