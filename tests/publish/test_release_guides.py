"""Integrity of the actual guide dependency collector; no geometry claims."""
import hashlib
import json
import shutil
import zipfile
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from cadagent.project import CadConfigError
from cadagent.publish.guides import collect_guides
from cadagent.publish import release
from .test_release import project


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root, identifier="v1"):
    folder = root / "guides" / identifier
    (folder / "model").mkdir(parents=True)
    parts = []
    for name in ("base", "lid"):
        data = (identifier + " " + name + " mesh bytes").encode()
        (folder / "model" / (name + ".stl")).write_bytes(data)
        parts.append({"name": name, "file": name + ".stl", "sha256": digest(data),
                      "bounds_mm": [0, 0, 0, 10, 10, 10], "color": "#ff9900"})
    model = json.dumps({"parts": parts}).encode()
    (folder / "model/view.json").write_bytes(model)
    poster = (identifier + " poster bytes").encode()
    (folder / "step.png").write_bytes(poster)
    guide = {"schema": "cad-agent.assembly-guide/1", "title": "Fixture guide",
             "snapshot": {"id": identifier, "revision": "fixture-" + identifier, "status": "released",
                          "source_commit": digest(identifier.encode())[:40]},
             "model": {"file": "model/view.json", "sha256": digest(model)},
             "subassemblies": [{"id": "box", "title": "Box", "parts": ["base", "lid"]}],
             "steps": [{"id": "fit-lid", "title": "Fit the lid", "subassembly": "box",
                        "text": "Fit the lid.", "parts": ["base", "lid"], "highlight": ["lid"],
                        "offsets_mm": {"lid": [0, 0, 25]},
                        "poster": {"file": "step.png", "sha256": digest(poster)}}]}
    path = folder / "guide.json"
    path.write_text(json.dumps(guide))
    return path, guide


def collect(root, path):
    return collect_guides(root, [path.relative_to(root).as_posix()])


def test_collects_exact_dependencies_and_freezes_validated_bytes(tmp_path):
    path, _ = fixture(tmp_path)
    bundle, = collect(tmp_path, path)
    assert set(bundle.files) == {"guides/v1/guide.json", "guides/v1/model/view.json",
                                 "guides/v1/model/base.stl", "guides/v1/model/lid.stl", "guides/v1/step.png"}
    original = bundle.files["guides/v1/model/lid.stl"]
    (path.parent / "model/lid.stl").write_bytes(b"changed after preflight")
    assert bundle.files["guides/v1/model/lid.stl"] == original
    with pytest.raises(CadConfigError, match="hash mismatch"):
        collect(tmp_path, path)


@pytest.mark.parametrize("kind", ["missing-mesh", "changed-mesh", "changed-model", "changed-poster"])
def test_missing_or_stale_dependency_is_rejected(tmp_path, kind):
    path, _ = fixture(tmp_path)
    target = path.parent / {"missing-mesh": "model/base.stl", "changed-mesh": "model/lid.stl",
                            "changed-model": "model/view.json", "changed-poster": "step.png"}[kind]
    if kind == "missing-mesh":
        target.unlink()
    else:
        target.write_bytes(b"replacement")
    with pytest.raises(CadConfigError, match="missing|hash mismatch"):
        collect(tmp_path, path)


@pytest.mark.parametrize("reference", ["/etc/passwd", "https://example.com/model.json", "//example.com/x",
                                       "model/view.json?latest=1", "model/view.json#x", "../../../../escape.json",
                                       "%2fetc/passwd", "model%5cview.json"])
def test_unsafe_model_reference_is_rejected(tmp_path, reference):
    path, guide = fixture(tmp_path)
    guide["model"]["file"] = reference
    path.write_text(json.dumps(guide))
    with pytest.raises(CadConfigError):
        collect(tmp_path, path)


@pytest.mark.parametrize("edit", ["duplicate-step", "unknown-part", "hidden-highlight", "future-prerequisite",
                                  "nonfinite-offset", "boolean-offset", "escaping-id", "missing-commit",
                                  "unknown-subassembly", "zero-camera", "malformed-status"])
def test_invalid_instruction_identity_is_rejected(tmp_path, edit):
    path, guide = fixture(tmp_path)
    step = guide["steps"][0]
    if edit == "duplicate-step": guide["steps"].append(dict(step))
    elif edit == "unknown-part": step["parts"].append("missing")
    elif edit == "hidden-highlight": step["parts"] = ["base"]
    elif edit == "future-prerequisite": step["requires"] = ["later"]
    elif edit == "nonfinite-offset": step["offsets_mm"]["lid"] = [0, float("nan"), 0]
    elif edit == "boolean-offset": step["offsets_mm"]["lid"] = [False, 0, 0]
    elif edit == "escaping-id": guide["snapshot"]["id"] = "../escape"
    elif edit == "missing-commit": del guide["snapshot"]["source_commit"]
    elif edit == "unknown-subassembly": step["subassembly"] = "missing"
    elif edit == "zero-camera": step["camera"] = {"direction": [0, 0, 0]}
    elif edit == "malformed-status": guide["snapshot"]["status"] = []
    path.write_text(json.dumps(guide))
    with pytest.raises(CadConfigError):
        collect(tmp_path, path)


def test_duplicate_snapshot_ids_are_rejected(tmp_path):
    path, _ = fixture(tmp_path)
    with pytest.raises(CadConfigError, match="unique snapshot"):
        collect_guides(tmp_path, [path.relative_to(tmp_path).as_posix()] * 2)


def test_symlink_dependency_is_rejected_even_inside_project(tmp_path):
    path, _ = fixture(tmp_path)
    mesh = path.parent / "model/base.stl"
    actual = path.parent / "actual.stl"
    mesh.rename(actual)
    mesh.symlink_to(actual)
    with pytest.raises(CadConfigError, match="symlinks"):
        collect(tmp_path, path)


@pytest.fixture
def runtime(monkeypatch):
    # Packaging fixture, deliberately not a claim that a browser can run these
    # stub bytes. The actual pinned runtime/extracted-ZIP browser check is separate.
    files = {"viewer.html": b"<title>Reader fixture</title>", "viewer.js": b"// viewer fixture",
             "assembly/guide.js": b"// guide fixture", "vendor/three/three.module.min.js": b"// engine fixture"}
    monkeypatch.setattr(release, "_guide_runtime", lambda: dict(files))
    return files


def release_project(tmp_path, count=1):
    p = project(tmp_path, {"include": [], "assembly_guides": []})
    paths = []
    for identifier in ["v1", "v2", "wip"][:count]:
        path, guide = fixture(p.root, identifier)
        if identifier == "wip":
            guide["snapshot"]["status"] = "wip"
            path.write_text(json.dumps(guide))
        paths.append(path)
    p.release["assembly_guides"] = [path.relative_to(p.root).as_posix() for path in paths]
    return p, paths


def test_release_contains_distinct_snapshots_runtime_and_static_fallback(tmp_path, runtime):
    p, paths = release_project(tmp_path, count=3)
    result = release.build_release(p, out=tmp_path / "release", date="2026-11-09")
    manifest = json.loads((result.folder / "manifest.json").read_text())
    assert [entry["id"] for entry in manifest["assembly_guides"]] == ["v1", "v2", "wip"]
    assert [entry["snapshot"]["status"] for entry in manifest["assembly_guides"]] == ["released", "released", "wip"]
    assert manifest["guide_runtime"]["files"] == {name: digest(data) for name, data in runtime.items()}
    for entry, path in zip(manifest["assembly_guides"], paths):
        assert (result.folder / entry["guide"]).read_bytes() == path.read_bytes()
        assert entry["sha256"] == digest(path.read_bytes())
        static = (result.folder / entry["href"]).read_text()
        assert "Fit the lid." in static and "step.png" in static
        assert entry["href"] in (result.folder / "index.html").read_text()
        # Exercise the actual query and relative path the generated link uses.
        import re
        link = re.search(r'href="([^\"]+)">Open interactive', static).group(1)
        viewer = (result.folder / entry["href"]).parent / unquote(urlsplit(link).path)
        assert viewer.resolve() == (result.folder / "guides/_cadagent/viewer.html").resolve()
        selected = parse_qs(urlsplit(link).query)["guide"][0]
        assert (viewer.parent / selected).resolve() == (result.folder / entry["guide"]).resolve()
    meshes = [(result.folder / entry["guide"]).parent / "model/lid.stl" for entry in manifest["assembly_guides"]]
    assert len({mesh.read_bytes() for mesh in meshes}) == 3
    # The project and toolkit installation are not needed to retain these bytes.
    shutil.rmtree(p.root)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(result.zip_path) as archive:
        archive.extractall(extracted)
    for relative, expected in manifest["files"].items():
        assert digest((extracted / result.folder.name / relative).read_bytes()) == expected


@pytest.mark.parametrize("bad", ["model/view.json", "model/lid.stl", "step.png", "guide.json"])
def test_bad_guide_preserves_previous_release_folder_and_zip(tmp_path, runtime, bad):
    p, paths = release_project(tmp_path)
    output = tmp_path / "release"
    first = release.build_release(p, out=output, date="2026-11-09")
    before = {file.relative_to(output).as_posix(): file.read_bytes() for file in output.rglob("*") if file.is_file()}
    before_zip = first.zip_path.read_bytes()
    (paths[0].parent / bad).write_bytes(b"invalid replacement")
    with pytest.raises(CadConfigError):
        release.build_release(p, out=output, date="2026-11-09")
    assert {file.relative_to(output).as_posix(): file.read_bytes() for file in output.rglob("*") if file.is_file()} == before
    assert first.zip_path.read_bytes() == before_zip


def test_source_mutation_after_preflight_cannot_change_release_inputs(tmp_path, runtime, monkeypatch):
    p, paths = release_project(tmp_path)
    mesh = paths[0].parent / "model/lid.stl"
    expected = mesh.read_bytes()
    original = release._prepare
    def change_then_prepare(folder):
        mesh.write_bytes(b"changed between preflight and output")
        original(folder)
    monkeypatch.setattr(release, "_prepare", change_then_prepare)
    result = release.build_release(p, out=tmp_path / "release", date="2026-11-09")
    copied = result.folder / "guides/v1/project/guides/v1/model/lid.stl"
    assert copied.read_bytes() == expected


def test_guide_release_is_byte_reproducible(tmp_path, runtime):
    p, _ = release_project(tmp_path, count=2)
    output = tmp_path / "release"
    first = release.build_release(p, out=output, date="2026-11-09")
    before = first.zip_path.read_bytes()
    expected = dict(first.files)
    second = release.build_release(p, out=output, date="2026-11-09")
    assert second.files == expected
    assert second.zip_path.read_bytes() == before


def test_model_cannot_silently_skip_an_instance(tmp_path):
    path, guide = fixture(tmp_path)
    model = path.parent / "model/view.json"
    value = json.loads(model.read_bytes())
    value["skipped"] = ["missing-fastener"]
    model.write_text(json.dumps(value))
    guide["model"]["sha256"] = digest(model.read_bytes())
    path.write_text(json.dumps(guide))
    with pytest.raises(CadConfigError, match="skip geometry"):
        collect(tmp_path, path)
