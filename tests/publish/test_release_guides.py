"""Integrity of the actual guide dependency collector; no geometry claims."""
import hashlib
import json

import pytest

from cadagent.project import CadConfigError
from cadagent.publish.guides import collect_guides


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root, identifier="v1"):
    folder = root / "guides" / identifier
    (folder / "model").mkdir(parents=True)
    parts = []
    for name in ("base", "lid"):
        data = (name + " mesh bytes").encode()
        (folder / "model" / (name + ".stl")).write_bytes(data)
        parts.append({"name": name, "file": name + ".stl", "sha256": digest(data),
                      "bounds_mm": [0, 0, 0, 10, 10, 10], "color": "#ff9900"})
    model = json.dumps({"parts": parts}).encode()
    (folder / "model/view.json").write_bytes(model)
    poster = b"poster bytes"
    (folder / "step.png").write_bytes(poster)
    guide = {"schema": "cad-agent.assembly-guide/1", "title": "Fixture guide",
             "snapshot": {"id": identifier, "revision": "fixture-1", "status": "released", "source_commit": "a" * 40},
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
                                  "nonfinite-offset", "boolean-offset", "escaping-id", "missing-commit"])
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
