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
