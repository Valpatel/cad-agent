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
from urllib.parse import urlsplit

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
    return {"repository": repository, "commit": commit, "model": model, "files": files}


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
