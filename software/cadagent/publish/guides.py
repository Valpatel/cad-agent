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
from urllib.parse import quote, unquote, urlsplit

from cadagent.project import CadConfigError

SCHEMA = "cad-agent.assembly-guide/1"
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _fields(value: Any, allowed, where: str) -> None:
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise CadConfigError(f"assembly guide {where} has unsupported fields or is not an object")


def _text(value: Any, limit: int = 4000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _vector(value: Any, nonzero: bool = False) -> bool:
    return (isinstance(value, list) and len(value) == 3 and all(_finite(n) and abs(n) <= 1e9 for n in value)
            and (not nonzero or any(value)))


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
                    or len(reference) > 2000 or any(ord(c) <= 32 or ord(c) == 127 for c in reference)
                    or re.search(r"%(?:2e|2f|5c|00)", reference, re.I)
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
                if path.stat().st_size > 128 * 1024 * 1024:
                    raise CadConfigError("assembly guide asset exceeds the reader's 128 MiB limit")
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
            if len(data) > 2 * 1024 * 1024:
                raise CadConfigError("assembly guide JSON exceeds the reader's 2 MiB limit")
            try:
                def non_json_constant(value):
                    raise ValueError("non-JSON numeric constant")
                value = json.loads(data, parse_constant=non_json_constant)
                # Static instruction output must also be valid UTF-8.
                json.dumps(value, ensure_ascii=False).encode("utf-8")
            except (ValueError, UnicodeError):
                raise CadConfigError("invalid assembly guide JSON") from None
            if not isinstance(value, dict):
                raise CadConfigError("assembly guide JSON must be an object")
            return path, value

        # Config entries are filesystem paths; references inside JSON are URLs.
        path, guide = document(root, quote(configured, safe="/"))
        _fields(guide, ("schema", "snapshot", "model", "subassemblies", "steps", "source"), "document")
        snapshot = guide.get("snapshot")
        _fields(snapshot, ("id", "revision", "status", "source_commit"), "snapshot")
        if (guide.get("schema") != SCHEMA or not isinstance(snapshot, dict)
                or not isinstance(snapshot.get("id"), str) or not _ID.fullmatch(snapshot["id"])
                or snapshot["id"] in identifiers or snapshot.get("status") not in ("released", "wip")
                or not isinstance(snapshot.get("source_commit"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", snapshot["source_commit"])
                or not _text(snapshot.get("revision"), 200)):
            raise CadConfigError("assembly guide needs a unique snapshot id, status, revision and source commit")
        identifiers.add(snapshot["id"])
        if "source" in guide and not isinstance(guide["source"], dict):
            raise CadConfigError("assembly guide source metadata must be an object")
        model = guide.get("model")
        _fields(model, ("file", "sha256"), "model binding")
        if not isinstance(model, dict) or not isinstance(model.get("sha256"), str):
            raise CadConfigError("assembly guide model needs file and sha256")
        model_path, view = document(path.parent, model.get("file"), model["sha256"])
        parts = view.get("parts")
        if (view.get("units") != "mm" or view.get("up") != "z"
                or not isinstance(parts, list) or not 1 <= len(parts) <= 2000):
            raise CadConfigError("assembly guide model must declare mm/z-up and contain 1..2000 parts")
        if view.get("skipped"):
            raise CadConfigError("assembly guide model must not silently skip geometry")
        names = set()
        for part in parts:
            if (not isinstance(part, dict) or not _text(part.get("name"), 200)
                    or part["name"] in names or not isinstance(part.get("sha256"), str)):
                raise CadConfigError("assembly guide model needs unique named instances with sha256")
            bounds = part.get("bounds_mm")
            color = part.get("color")
            if (not isinstance(bounds, list) or len(bounds) != 6
                    or not all(_finite(n) and abs(n) <= 1e9 for n in bounds)
                    or any(bounds[i] > bounds[i + 3] for i in range(3))
                    or ("color" in part and not ((isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color))
                                                  or (type(color) is int and 0 <= color <= 0xffffff)))
                    or ("visible" in part and type(part["visible"]) is not bool)
                    or (part.get("explode") is not None and not _vector(part["explode"], True))):
                raise CadConfigError("assembly guide model has invalid bounds or presentation fields")
            names.add(part["name"])
            capture(model_path.parent, part.get("file"), part["sha256"])
        groups = guide.get("subassemblies")
        if not isinstance(groups, list) or not 1 <= len(groups) <= 2000:
            raise CadConfigError("assembly guide must contain subassemblies")
        group_ids = set()
        group_parts = {}
        for group in groups:
            _fields(group, ("id", "title", "parts"), "subassembly")
            if (not isinstance(group, dict) or not isinstance(group.get("id"), str)
                    or not _ID.fullmatch(group["id"]) or group["id"] in group_ids
                    or not _text(group.get("title"))
                    or not isinstance(group.get("parts"), list) or not 1 <= len(group["parts"]) <= 2000
                    or any(not isinstance(n, str) or n not in names for n in group["parts"])
                    or len(set(group["parts"])) != len(group["parts"])):
                raise CadConfigError("assembly guide needs unique subassemblies with known instances")
            group_ids.add(group["id"])
            group_parts[group["id"]] = set(group["parts"])
        steps = guide.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 2000:
            raise CadConfigError("assembly guide must contain steps")
        seen = set()
        for step in steps:
            _fields(step, ("id", "title", "subassembly", "parts", "highlight", "offsets_mm", "text",
                           "poster", "camera", "requires"), "step")
            if (not isinstance(step, dict) or not isinstance(step.get("id"), str)
                    or not _ID.fullmatch(step["id"]) or step["id"] in seen
                    or not isinstance(step.get("subassembly"), str) or step["subassembly"] not in group_ids
                    or not _text(step.get("title")) or not _text(step.get("text"), 20000)):
                raise CadConfigError("assembly guide needs unique stable step ids")
            for field in ("parts", "highlight"):
                values = step.get(field)
                if (not isinstance(values, list) or len(values) > 2000 or (field == "parts" and not values)
                        or any(not isinstance(v, str) or v not in names for v in values)
                        or len(set(values)) != len(values)):
                    raise CadConfigError(f"assembly guide step {field} must name unique model instances")
            if not set(step.get("highlight", [])).issubset(step["parts"]):
                raise CadConfigError("assembly guide highlights must be visible in that step")
            if not set(step["highlight"]).issubset(group_parts[step["subassembly"]]):
                raise CadConfigError("assembly guide highlights must belong to the active subassembly")
            requires = step.get("requires", [])
            if (not isinstance(requires, list) or len(requires) > 2000
                    or any(not isinstance(v, str) or v not in seen for v in requires)
                    or len(set(requires)) != len(requires)):
                raise CadConfigError("assembly guide prerequisites must refer to earlier steps")
            offsets = step.get("offsets_mm")
            if not isinstance(offsets, dict) or any(name not in step["parts"] for name in offsets):
                raise CadConfigError("assembly guide offsets must refer to visible instances")
            for vector in offsets.values():
                if not _vector(vector):
                    raise CadConfigError("assembly guide offsets must be finite CAD-mm vectors")
            camera = step.get("camera")
            if "camera" in step:
                _fields(camera, ("direction",), "camera")
                direction = camera.get("direction") if isinstance(camera, dict) else None
                if not _vector(direction, True):
                    raise CadConfigError("assembly guide camera needs a finite nonzero CAD direction")
            poster = step.get("poster")
            if "poster" in step:
                _fields(poster, ("file", "sha256"), "poster binding")
                if not isinstance(poster, dict) or not isinstance(poster.get("sha256"), str):
                    raise CadConfigError("assembly guide poster needs file and sha256")
                capture(path.parent, poster.get("file"), poster["sha256"])
            seen.add(step["id"])
        result.append(GuideBundle(snapshot["id"], path.relative_to(root).as_posix(), guide, files))
    return result
