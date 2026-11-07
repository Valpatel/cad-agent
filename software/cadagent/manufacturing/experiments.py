"""Write-once physical specimen identities and observations, independent of printer transport.

Each deliberate physical copy/reprint gets a new UUID, including identical geometry.
The short stamp resolves through the entire persistent registry, never just a plate.
An uncertain submission is an observation, not permission to print the same ID again.
CAD/slicer checks do not establish physical legibility, function or durability.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit

FORMAT = "cadagent.specimen/1"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required regular file missing: {path.name}")
    return path


def _write_once(path, value):
    """Never truncate a previous record; a failed new write removes only its own file."""
    path = Path(path)
    raw = _json(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ValueError(f"record already exists: {path.name}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return value


def _repository(value):
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
        value = f"https://{host}/{path}"
    value = value.removesuffix("/").removesuffix(".git")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.path.strip("/")
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("repository must be an explicit credential-free HTTPS repository URL")
    return value


def source_snapshot(root, model, paths, *, repository):
    """Bind a declared, nonempty generator/input closure to actual clean Git bytes.

    Call before generation. This proves the declared files, not an automatically
    discovered dependency closure. The later manifest commit is not this source SHA.
    """
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    commit = git("rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("a full committed source SHA is required")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("source has tracked changes; commit required inputs before generation")
    repository = _repository(repository)
    if _repository(git("remote", "get-url", "origin").decode().strip()) != repository:
        raise ValueError("repository does not match the actual source origin")
    paths = list(paths)
    if not paths or len(set(paths)) != len(paths) or model not in paths:
        raise ValueError("declare unique source paths including the model entry point")
    files = {}
    for name in paths:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise ValueError("source paths must be canonical repository-relative files")
        path = _regular(root / rel)
        if not path.resolve().is_relative_to(root):
            raise ValueError("source file escapes its repository")
        raw = path.read_bytes()
        try:
            committed = git("show", f"{commit}:{name}")
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"required source is not committed: {name}") from exc
        if raw != committed:
            raise ValueError(f"required source differs from committed bytes: {name}")
        files[name] = hashlib.sha256(raw).hexdigest()
    snapshot = {"repository": repository, "commit": commit, "model": model, "files": files}
    if urlsplit(repository).hostname == "github.com":
        snapshot["model_url"] = repository + "/blob/" + commit + "/" + quote(model, safe="/")
    return snapshot


def short_id(full_uuid):
    return uuid.UUID(str(full_uuid)).hex[:10].upper()


def _identities(registry):
    records = []
    seen_uuid, seen_short = set(), set()
    for path in sorted(Path(registry).glob("*.identity.json")):
        record = json.loads(_regular(path).read_bytes())
        identity = record["identity"]
        full = str(uuid.UUID(identity["uuid"]))
        short = short_id(full)
        if (record.get("format") != FORMAT or identity["uuid"] != full
                or identity["short_id"] != short or path.name != short + ".identity.json"
                or record.get("identity_sha256") != _digest(identity)):
            raise ValueError("invalid or changed specimen identity")
        if full in seen_uuid or short in seen_short:
            raise ValueError("ambiguous specimen identity in persistent registry")
        seen_uuid.add(full)
        seen_short.add(short)
        records.append(record)
    return records


def allocate(registry, *, source, parameters, process, material, full_uuid=None):
    """Allocate exactly one physical specimen. Existing identities are never reused."""
    for value in (source, parameters, process, material):
        if not isinstance(value, dict) or not value:
            raise ValueError("source, resolved parameters, process and material must be nonempty objects")
    if (not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", ""))
            or source.get("model") not in source.get("files", {})):
        raise ValueError("source must include a committed model and declared input hashes")
    _repository(source.get("repository", ""))
    full = str(uuid.UUID(str(full_uuid))) if full_uuid else str(uuid.uuid4())
    short = short_id(full)
    if any(r["identity"]["uuid"] == full or r["identity"]["short_id"] == short
           for r in _identities(registry)):
        raise ValueError("UUID or short stamp already allocated; new physical copies need new UUIDs")
    # JSON roundtrip freezes caller-owned nested values and rejects NaN/Infinity.
    identity = json.loads(_json({"uuid": full, "short_id": short, "source": source,
                                "parameters": parameters, "process": process, "material": material}))
    record = {"format": FORMAT, "identity": identity, "identity_sha256": _digest(identity)}
    return _write_once(Path(registry) / (short + ".identity.json"), record)


def lookup(registry, identifier):
    """Reject ambiguity anywhere in the persistent registry before resolving an ID."""
    matches = [r for r in _identities(registry) if identifier.upper() == r["identity"]["short_id"]
               or identifier == r["identity"]["uuid"]]
    if len(matches) != 1:
        raise ValueError("unknown or ambiguous specimen ID")
    return matches[0]


def _artifact_rows(root, paths):
    root = Path(root).resolve()
    paths = list(paths)
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("declare a nonempty unique artifact set")
    rows = {}
    for name in paths:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise ValueError("artifacts must have canonical relative paths")
        path = _regular(root / rel)
        if not path.resolve().is_relative_to(root):
            raise ValueError("artifact escapes its root")
        rows[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return rows


def bind_artifacts(registry, identifier, root, paths):
    """Write once after generation; references the prior immutable identity digest."""
    record = lookup(registry, identifier)
    manifest = {"format": "cadagent.specimen-artifacts/1", "uuid": record["identity"]["uuid"],
                "identity_sha256": record["identity_sha256"], "files": _artifact_rows(root, paths)}
    return _write_once(Path(registry) / (record["identity"]["short_id"] + ".artifacts.json"), manifest)


def verify_artifacts(registry, identifier, root):
    record = lookup(registry, identifier)
    path = Path(registry) / (record["identity"]["short_id"] + ".artifacts.json")
    manifest = json.loads(_regular(path).read_bytes())
    if (manifest.get("format") != "cadagent.specimen-artifacts/1"
            or manifest.get("uuid") != record["identity"]["uuid"]
            or manifest.get("identity_sha256") != record["identity_sha256"]
            or manifest.get("files") != _artifact_rows(root, manifest.get("files", {}))):
        raise ValueError("specimen artifact bytes or identity changed")
    return manifest


def append_observation(registry, identifier, root, *, kind, payload, event_uuid=None):
    """Append a print-attempt or human-feedback event; never update original identity.

    Payload records observed facts. Unknown submission state remains unknown; this
    function neither submits nor retries jobs. A deliberate reprint is a new identity.
    """
    if kind not in {"attempt", "feedback"} or not isinstance(payload, dict) or not payload:
        raise ValueError("an attempt or feedback event needs a nonempty observation object")
    if not isinstance(payload.get("observer"), str) or not payload["observer"].strip():
        raise ValueError("an observation must name its human or agent observer")
    manifest = verify_artifacts(registry, identifier, root)
    event = {"format": "cadagent.specimen-observation/1", "event_uuid": str(uuid.UUID(str(event_uuid)))
             if event_uuid else str(uuid.uuid4()), "uuid": manifest["uuid"],
             "identity_sha256": manifest["identity_sha256"], "artifacts_sha256": _digest(manifest),
             "recorded_at": datetime.now(timezone.utc).isoformat(),
             "kind": kind, "payload": json.loads(_json(payload))}
    return _write_once(Path(registry) / (event["event_uuid"] + ".observation.json"), event)


def bind_plate(registry, identifiers, artifact_root, project_file, *, batch_uuid=None):
    """Bind one actual native-project placement per unique physical specimen.

    Reuses the plate reader and checks actual 3MF mesh vertices/faces against the
    bound STL, not just its object name or volume. This is not Bambu GUI acceptance.
    """
    import zipfile
    import xml.etree.ElementTree as ET
    from cadagent._deps import require
    from cadagent.manufacturing import plates
    from cadagent.manufacturing.mesh3mf import CORE_NS

    np = require("numpy", "experiment plate readback")
    trimesh = require("trimesh", "experiment plate readback")
    artifact_root = Path(artifact_root).resolve()
    identities = [lookup(registry, i) for i in identifiers]
    wanted = {r["identity"]["short_id"]: r for r in identities}
    if not wanted or len(wanted) != len(identities):
        raise ValueError("each physical specimen must occur once; copies need distinct UUIDs")
    project = _regular(artifact_root / project_file)
    if Path(project_file).is_absolute() or not project.resolve().is_relative_to(artifact_root):
        raise ValueError("plate artifact must stay inside its declared root")
    back = plates.read_plates_3mf(project)
    settings = back["project_settings"]
    if (not isinstance(settings, dict) or plates.application(settings) == plates.APPLICATION
            or any(not settings.get(k) for k in ("printer_settings_id", "print_settings_id", "filament_settings_id"))):
        raise ValueError("native printer/process/filament settings are required")
    held = [q for p in back["plates"] for q in p["placements"]]
    if (back["outside"] or len(held) != len(wanted)
            or {q["part"] for q in held} != set(wanted)
            or len({q["part"] for q in held}) != len(held)):
        raise ValueError("unexpected, missing or repeated physical specimen in plate readback")
    ns = {"m": CORE_NS}
    with zipfile.ZipFile(project) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("duplicate project archive member")
        tree = ET.fromstring(archive.read("3D/3dmodel.model"))
        settings_hash = hashlib.sha256(archive.read(plates.PROJECT_SETTINGS)).hexdigest()
    objects = list(tree.iterfind("m:resources/m:object", ns))
    if len(objects) != len(wanted) or {o.get("name") for o in objects} != set(wanted):
        raise ValueError("project mesh objects do not match physical specimen identities")
    artifacts = {}
    for obj in objects:
        stamp = obj.get("name")
        manifest = verify_artifacts(registry, stamp, artifact_root)
        object_record = back["objects"].get(obj.get("id"), {})
        if object_record.get("name") != stamp:
            raise ValueError("native object metadata and actual mesh identity disagree")
        identity = wanted[stamp]["identity"]
        if identity["process"].get("project_settings_sha256") != settings_hash:
            raise ValueError("native settings differ from the allocated specimen identity")
        slot = object_record.get("extruder", 0)
        filaments = settings["filament_settings_id"]
        if (not isinstance(filaments, list) or not 1 <= slot <= len(filaments)
                or identity["material"].get("profile_id") != filaments[slot - 1]):
            raise ValueError("actual filament slot differs from the allocated specimen material")
        stls = [p for p in manifest["files"] if p.endswith(".stl")]
        if len(stls) != 1:
            raise ValueError("each specimen must bind exactly one print-oriented STL")
        mesh = trimesh.load_mesh(artifact_root / stls[0], process=True)
        expected = plates._normalised(mesh.vertices)
        actual = np.array([[float(v.get(k)) for k in "xyz"]
                           for v in obj.iterfind("m:mesh/m:vertices/m:vertex", ns)])
        faces = np.array([[int(t.get(k)) for k in ("v1", "v2", "v3")]
                          for t in obj.iterfind("m:mesh/m:triangles/m:triangle", ns)])
        if (actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=0.000051)
                or not np.array_equal(faces, mesh.faces)):
            raise ValueError("project mesh differs from the bound specimen STL")
        artifacts[stamp] = _digest(manifest)
    for item in tree.iterfind("m:build/m:item", ns):
        transform = [float(v) for v in item.get("transform", "").split()]
        if len(transform) != 12:
            raise ValueError("specimen placement lacks an explicit transform")
        matrix = np.array(transform[:9]).reshape(3, 3)
        if (not np.allclose(matrix @ matrix.T, np.eye(3), rtol=0, atol=1e-8)
                or not np.isclose(np.linalg.det(matrix), 1, rtol=0, atol=1e-8)
                or not np.allclose(matrix[:, 2], [0, 0, 1], rtol=0, atol=1e-8)):
            raise ValueError("specimen transform scales, mirrors or tips its print-oriented mesh")
    area, _ = plates.printable_area(settings, (256, 256))
    problems = plates.check_plates(plates.as_plates(back), (area[2]-area[0], area[3]-area[1]),
                                   gap=0, margin=0, quantities={stamp: 1 for stamp in wanted},
                                   tol=plates.POSITION_TOL_MM)
    if problems or any(abs(q["z_mm"]) > 1e-6 for q in held):
        raise ValueError("specimens overlap, leave the bed or float above it: " + "; ".join(problems))
    rows = []
    for plate in back["plates"]:
        if sorted((q["object"], q["instance"]) for q in plate["placements"]) != sorted(plate["listed"]):
            raise ValueError("project lists different instances from its actual placements")
        for q in plate["placements"]:
            record = wanted[q["part"]]
            rows.append({"plate": plate["index"], "placement": q,
                         "uuid": record["identity"]["uuid"], "identity_sha256": record["identity_sha256"],
                         "artifacts_sha256": artifacts[q["part"]]})
    result = {"format": "cadagent.specimen-plate/1", "batch_uuid": str(uuid.UUID(str(batch_uuid)))
              if batch_uuid else str(uuid.uuid4()), "project": project_file,
              "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
              "settings_sha256": settings_hash, "settings": settings, "specimens": rows,
              "sliced": False, "gui_verified": False, "physical_qualification": False}
    return _write_once(Path(registry) / (result["batch_uuid"] + ".plate.json"), result)
