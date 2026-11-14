"""Runtime closure integrity, distinct from actual browser/geometry validation."""
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cadagent.project import CadConfigError
from cadagent.publish import release, runtime
from .test_release_guides import release_project


def fixture(tmp_path):
    kit = tmp_path / "kit"
    document = json.loads(runtime.PROFILE_PATH.read_text())
    for name in document["profiles"]["assembly-reader"]["files"]:
        target = kit / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime.KIT_DIR / name, target)
    manifest = tmp_path / "profiles.json"
    manifest.write_text(json.dumps(document))
    return kit, manifest, document


def capture(kit, manifest):
    return runtime.capture_profile("assembly-reader", kit_dir=kit, manifest_path=manifest)


def test_actual_profile_is_minimal_and_does_not_grow_with_unrelated_assets(tmp_path):
    kit, manifest, _ = fixture(tmp_path)
    before = capture(kit, manifest)
    for name in ("scada/ui/img/gallery.svg", "scada/sim/scenarios/large.json", "new-viewer.js"):
        target = kit / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"unrelated" * 1024)
    after = capture(kit, manifest)
    assert dict(after) == dict(before)
    assert after.identity == before.identity
    assert {"model/viewer.html", "model/viewer.js", "assembly/guide.js", "model/stage.js", "ui/hud.css"} <= set(after)
    assert "vendor/mermaid/mermaid.min.js" not in after
    assert sum(map(len, after.values())) < 1_000_000
    with pytest.raises(TypeError):
        after.files["model/viewer.js"] = b"mutation"
    with pytest.raises(TypeError):
        after.identity["profile"] = "changed"
    old = after["model/viewer.js"]
    (kit / "model/viewer.js").write_bytes(b"changed after capture")
    assert after["model/viewer.js"] == old


@pytest.mark.parametrize("name", ["model/viewer.js", "assembly/guide.js", "vendor/fonts/fonts.css",
                                  "vendor/fonts/inter.woff2", "assembly/NOTICE.txt", "vendor/file-parsers/THREE-LICENSE.txt"])
@pytest.mark.parametrize("failure", ["missing", "changed"])
def test_missing_or_tampered_runtime_fails(tmp_path, name, failure):
    kit, manifest, _ = fixture(tmp_path)
    target = kit / name
    target.unlink() if failure == "missing" else target.write_bytes(b"tampered")
    with pytest.raises(CadConfigError, match="missing|hash mismatch"):
        capture(kit, manifest)


def test_dynamic_worker_decoder_dependencies_are_required_when_a_profile_declares_them(tmp_path):
    kit, manifest, document = fixture(tmp_path)
    files = document["profiles"]["assembly-reader"]["files"]
    files["model/viewer.js"]["requires"].append("nested/worker.js")
    for name, data, requires in (("nested/worker.js", b"// fixture worker", ["nested/decoder.wasm"]),
                                 ("nested/decoder.wasm", b"fixture decoder bytes", [])):
        target = kit / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "requires": requires}
    manifest.write_text(json.dumps(document))
    assert "nested/decoder.wasm" in capture(kit, manifest)
    (kit / "nested/decoder.wasm").unlink()
    with pytest.raises(CadConfigError, match="missing.*decoder"):
        capture(kit, manifest)
    del files["nested/decoder.wasm"]
    manifest.write_text(json.dumps(document))
    with pytest.raises(CadConfigError, match="undeclared dependency"):
        capture(kit, manifest)


@pytest.mark.parametrize("failure", ["schema", "extra-field", "hash", "missing-edge", "orphan", "duplicate", "traversal", "absolute"])
def test_invalid_manifest_is_rejected(tmp_path, failure):
    kit, manifest, document = fixture(tmp_path)
    profile = document["profiles"]["assembly-reader"]
    if failure == "schema":
        document["schema"] = "future"
    elif failure == "extra-field":
        profile["url"] = "https://example.com/kit"
    elif failure == "hash":
        profile["files"]["model/viewer.js"]["sha256"] = True
    elif failure == "missing-edge":
        del profile["files"]["ui/hud.css"]
    elif failure == "orphan":
        profile["files"]["unused.js"] = {"sha256": "0" * 64, "requires": []}
    elif failure == "duplicate":
        profile["entrypoints"].append("model/viewer.html")
    else:
        profile["entrypoints"].append("../outside" if failure == "traversal" else "/outside")
    manifest.write_text(json.dumps(document))
    with pytest.raises(CadConfigError):
        capture(kit, manifest)


def test_duplicate_keys_and_unknown_profiles_fail(tmp_path):
    kit, manifest, _ = fixture(tmp_path)
    with pytest.raises(CadConfigError, match="unknown profile"):
        runtime.capture_profile("missing", kit_dir=kit, manifest_path=manifest)
    manifest.write_text('{"schema":"cad-agent.runtime-profiles/1","schema":"other","profiles":{}}')
    with pytest.raises(CadConfigError, match="duplicate JSON key"):
        capture(kit, manifest)


@pytest.mark.parametrize("directory", [False, True])
def test_symlinked_file_or_parent_is_rejected(tmp_path, directory):
    kit, manifest, _ = fixture(tmp_path)
    target = kit / ("assembly" if directory else "model/viewer.js")
    moved = tmp_path / "moved"
    target.rename(moved)
    target.symlink_to(moved, target_is_directory=directory)
    with pytest.raises(CadConfigError, match="symlink"):
        capture(kit, manifest)


def test_other_profile_does_not_change_assembly_identity(tmp_path):
    kit, manifest, document = fixture(tmp_path)
    before = capture(kit, manifest)
    document["profiles"]["other"] = copy.deepcopy(document["profiles"]["assembly-reader"])
    manifest.write_text(json.dumps(document))
    assert capture(kit, manifest).identity == before.identity


def test_refresh_is_explicit_and_normal_capture_never_changes_manifest(tmp_path):
    kit, manifest, _ = fixture(tmp_path)
    before = manifest.read_bytes()
    (kit / "model/viewer.js").write_bytes(b"// reviewed changed source")
    with pytest.raises(CadConfigError, match="hash mismatch"):
        capture(kit, manifest)
    assert manifest.read_bytes() == before
    runtime.refresh_profiles(kit_dir=kit, manifest_path=manifest)
    assert capture(kit, manifest)["model/viewer.js"] == b"// reviewed changed source"


def test_release_uses_profile_receipt_and_rejection_preserves_previous_archive(tmp_path, monkeypatch):
    kit, manifest, _ = fixture(tmp_path)
    monkeypatch.setattr(release, "_guide_runtime", lambda: capture(kit, manifest))
    project, _ = release_project(tmp_path / "project")
    output = tmp_path / "release"
    first = release.build_release(project, out=output, date="2026-11-13")
    record = json.loads((output / "manifest.json").read_bytes())["guide_runtime"]
    bundle = capture(kit, manifest)
    assert all(record[key] == value for key, value in bundle.identity.items())
    assert record["files"] == {name: hashlib.sha256(data).hexdigest() for name, data in bundle.items()}
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    zipped = first.zip_path.read_bytes()
    (kit / "ui/hud.css").unlink()
    with pytest.raises(CadConfigError, match="missing.*hud.css"):
        release.build_release(project, out=output, date="2026-11-13")
    assert {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()} == before
    assert first.zip_path.read_bytes() == zipped
