"""Collect hash-bound assembly-guide inputs for an existing print release.

Only project-local data references are followed. Bytes are captured during
preflight so a later source edit cannot silently change the packaged snapshot.
The browser's guide controller additionally validates presentation semantics.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import unquote, urlsplit

from cadagent.project import CadConfigError

SCHEMA = "cad-agent.assembly-guide/1"
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass
class GuideBundle:
    identifier: str
    path: str
    guide: Dict[str, Any]
    files: Dict[str, bytes]


def collect_guides(root: Path, paths: List[str]) -> List[GuideBundle]:
    """Resolve guide → model → meshes and posters, rejecting missing/stale inputs.

    Paths in data are relative to their containing document, including parent
    references that remain inside the project. Remote/root URLs, hidden inputs,
    symlinks, queries and fragments are refused. No output is written here.
    """
    root = root.resolve()
    result, identifiers = [], set()
    for configured in paths:
        files: Dict[str, bytes] = {}

        def capture(base: Path, reference: Any, expected: Any = None) -> tuple[Path, bytes]:
            if (not isinstance(reference, str) or not reference or "\\" in reference
                    or any(ord(c) < 32 or ord(c) == 127 for c in reference)
                    or re.search(r"%(?![0-9A-Fa-f]{2})", reference)):
                raise CadConfigError("assembly guide needs a relative file reference")
            try:
                parsed = urlsplit(reference)
                decoded = unquote(reference, errors="strict")
            except (ValueError, UnicodeError):
                raise CadConfigError("invalid assembly guide file reference") from None
            if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                    or reference.startswith(("/", "~")) or "?" in reference or "#" in reference):
                raise CadConfigError("assembly guide references must be local relative paths without query/fragment")
            if "\0" in decoded or "\\" in decoded or Path(decoded).is_absolute():
                raise CadConfigError("invalid assembly guide file reference")
            lexical = base / decoded
            path = lexical.resolve()
            if not path.is_relative_to(root) or path == root:
                raise CadConfigError("assembly guide reference escapes the project")
            # Reject links even when they currently point inside the project.
            cursor = lexical
            while cursor != root and cursor != cursor.parent:
                if cursor.is_symlink():
                    raise CadConfigError("assembly guide inputs must not be symlinks")
                cursor = cursor.parent
            relative = path.relative_to(root).as_posix()
            if any(p.startswith(".") for p in path.relative_to(root).parts):
                raise CadConfigError("assembly guide inputs must not be hidden files")
            try:
                if not path.is_file():
                    raise OSError()
                data = path.read_bytes()
            except OSError:
                raise CadConfigError(f"missing or unreadable assembly guide input: {relative}") from None
            if expected is not None and (not isinstance(expected, str) or not _HASH.fullmatch(expected)
                                         or hashlib.sha256(data).hexdigest() != expected):
                raise CadConfigError(f"assembly guide input hash mismatch: {relative}")
            if relative in files and files[relative] != data:
                raise CadConfigError(f"assembly guide input changed during collection: {relative}")
            files[relative] = data
            return path, data

        def document(base: Path, reference: Any, expected: Any = None):
            path, data = capture(base, reference, expected)
            if len(data) > 8 * 1024 * 1024:
                raise CadConfigError("assembly guide JSON exceeds 8 MiB")
            try:
                value = json.loads(data)
            except (ValueError, UnicodeError):
                raise CadConfigError("invalid assembly guide JSON") from None
            if not isinstance(value, dict):
                raise CadConfigError("assembly guide JSON must be an object")
            return path, value

        path, guide = document(root, configured)
        snapshot = guide.get("snapshot")
        if (guide.get("schema") != SCHEMA or not isinstance(snapshot, dict)
                or not isinstance(snapshot.get("id"), str) or not _ID.fullmatch(snapshot["id"])
                or snapshot["id"] in identifiers or snapshot.get("status") not in ("released", "wip")
                or not isinstance(snapshot.get("source_commit"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", snapshot["source_commit"])
                or not isinstance(snapshot.get("revision"), str) or not snapshot["revision"]):
            raise CadConfigError("assembly guide needs a unique snapshot id, status, revision and source commit")
        identifiers.add(snapshot["id"])
        model = guide.get("model")
        if not isinstance(model, dict) or not isinstance(model.get("sha256"), str):
            raise CadConfigError("assembly guide model needs file and sha256")
        model_path, view = document(path.parent, model.get("file"), model["sha256"])
        parts = view.get("parts")
        if not isinstance(parts, list) or not parts:
            raise CadConfigError("assembly guide model must contain parts")
        if view.get("skipped"):
            raise CadConfigError("assembly guide model must not silently skip geometry")
        names = set()
        for part in parts:
            if (not isinstance(part, dict) or not isinstance(part.get("name"), str) or not part["name"]
                    or part["name"] in names or not isinstance(part.get("sha256"), str)):
                raise CadConfigError("assembly guide model needs unique named instances with sha256")
            names.add(part["name"])
            capture(model_path.parent, part.get("file"), part["sha256"])
        groups = guide.get("subassemblies")
        if not isinstance(groups, list) or not groups:
            raise CadConfigError("assembly guide must contain subassemblies")
        group_ids = set()
        for group in groups:
            if (not isinstance(group, dict) or not isinstance(group.get("id"), str)
                    or not _ID.fullmatch(group["id"]) or group["id"] in group_ids
                    or not isinstance(group.get("parts"), list)
                    or any(not isinstance(n, str) or n not in names for n in group["parts"])
                    or len(set(group["parts"])) != len(group["parts"])):
                raise CadConfigError("assembly guide needs unique subassemblies with known instances")
            group_ids.add(group["id"])
        steps = guide.get("steps")
        if not isinstance(steps, list) or not steps:
            raise CadConfigError("assembly guide must contain steps")
        seen = set()
        for step in steps:
            if (not isinstance(step, dict) or not isinstance(step.get("id"), str)
                    or not _ID.fullmatch(step["id"]) or step["id"] in seen
                    or not isinstance(step.get("subassembly"), str) or step["subassembly"] not in group_ids
                    or not isinstance(step.get("title"), str) or not step["title"]
                    or not isinstance(step.get("text"), str)):
                raise CadConfigError("assembly guide needs unique stable step ids")
            for field in ("parts", "highlight"):
                values = step.get(field, [] if field == "highlight" else None)
                if (not isinstance(values, list) or any(not isinstance(v, str) or v not in names for v in values)
                        or len(set(values)) != len(values)):
                    raise CadConfigError(f"assembly guide step {field} must name unique model instances")
            if not set(step.get("highlight", [])).issubset(step["parts"]):
                raise CadConfigError("assembly guide highlights must be visible in that step")
            requires = step.get("requires", [])
            if not isinstance(requires, list) or any(not isinstance(v, str) or v not in seen for v in requires):
                raise CadConfigError("assembly guide prerequisites must refer to earlier steps")
            offsets = step.get("offsets_mm", {})
            if not isinstance(offsets, dict) or any(name not in step["parts"] for name in offsets):
                raise CadConfigError("assembly guide offsets must refer to visible instances")
            for vector in offsets.values():
                if (not isinstance(vector, list) or len(vector) != 3
                        or not all(_finite(n) for n in vector)):
                    raise CadConfigError("assembly guide offsets must be finite CAD-mm vectors")
            camera = step.get("camera")
            if camera is not None:
                direction = camera.get("direction") if isinstance(camera, dict) else None
                if (not isinstance(direction, list) or len(direction) != 3
                        or not all(_finite(n) for n in direction)
                        or not any(direction)):
                    raise CadConfigError("assembly guide camera needs a finite nonzero CAD direction")
            poster = step.get("poster")
            if poster is not None:
                if not isinstance(poster, dict) or not isinstance(poster.get("sha256"), str):
                    raise CadConfigError("assembly guide poster needs file and sha256")
                capture(path.parent, poster.get("file"), poster["sha256"])
            seen.add(step["id"])
        result.append(GuideBundle(snapshot["id"], path.relative_to(root).as_posix(), guide, files))
    return result
