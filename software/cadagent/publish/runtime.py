"""Capture a checked, explicit browser runtime dependency closure.

Profiles are trusted release inputs, not package names or executable project data.
Their graph includes dynamic resources and notices that a static JS import scan
cannot establish. File hashes bind that reviewed graph to the admitted bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Iterator

from cadagent.project import CadConfigError

SCHEMA = "cad-agent.runtime-profiles/1"
PROFILE_PATH = Path(__file__).with_name("runtime-profiles.json")
KIT_DIR = Path(__file__).resolve().parents[1] / "webkit"
_HASH = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")


def _error(message):
    raise CadConfigError("runtime profile: " + message)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _error(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _fields(value, names, where):
    if not isinstance(value, dict) or set(value) != set(names):
        _error(f"invalid {where} fields")


def _path(value):
    if (not isinstance(value, str) or not value or len(value) > 500
            or "\\" in value or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or any(c in value for c in (":", "?", "#", "%"))
            or PurePosixPath(value).is_absolute()
            or any(part in ("", ".", "..") or part.startswith(".") for part in value.split("/"))):
        _error(f"invalid runtime path {value!r}")
    return value


def _list(value, where):
    if not isinstance(value, list) or len(value) != len(set(x for x in value if isinstance(x, str))):
        _error(f"invalid or duplicate {where}")
    return [_path(item) for item in value]


def _read(root: Path, name: str) -> bytes:
    path = root.joinpath(*name.split("/"))
    cursor = root
    for part in name.split("/"):
        cursor /= part
        if cursor.is_symlink():
            _error(f"symlink in runtime path {name}")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        _error(f"missing runtime file {name}")
    try:
        return path.read_bytes()
    except OSError as exc:
        _error(f"cannot read {name}: {exc}")


def _document(path):
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw, object_pairs_hook=_unique)
    except (OSError, UnicodeError, ValueError) as exc:
        _error(f"cannot read manifest: {exc}")
    _fields(value, ("schema", "profiles"), "manifest")
    if value["schema"] != SCHEMA or not isinstance(value["profiles"], dict) or not value["profiles"]:
        _error("unsupported schema or empty profiles")
    for name, profile in value["profiles"].items():
        if not _NAME.fullmatch(name):
            _error(f"invalid profile name {name!r}")
        _validate(profile)
    return value, raw


def _validate(profile):
    _fields(profile, ("entrypoints", "resources", "notices", "files"), "profile")
    entrypoints = _list(profile["entrypoints"], "entrypoints")
    resources = _list(profile["resources"], "resources")
    notices = _list(profile["notices"], "notices")
    files = profile["files"]
    if not entrypoints or not notices or not isinstance(files, dict) or not files:
        _error("profile needs entrypoints, notices and files")
    for name, record in files.items():
        _path(name)
        _fields(record, ("sha256", "requires"), f"file {name}")
        if not isinstance(record["sha256"], str) or not _HASH.fullmatch(record["sha256"]):
            _error(f"invalid hash for {name}")
        _list(record["requires"], f"dependencies of {name}")
    reached, pending = set(), entrypoints + resources + notices
    while pending:
        name = pending.pop()
        if name not in files:
            _error(f"undeclared dependency {name}")
        if name not in reached:
            reached.add(name)
            pending.extend(files[name]["requires"])
    if reached != set(files):
        _error("unreachable runtime files: " + ", ".join(sorted(set(files) - reached)))


@dataclass(frozen=True)
class RuntimeBundle(Mapping[str, bytes]):
    """Validated bytes and their profile identity, frozen before publication."""
    files: Mapping[str, bytes]
    identity: Mapping[str, str]

    def __getitem__(self, name: str) -> bytes:
        return self.files[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.files)

    def __len__(self) -> int:
        return len(self.files)


def capture_profile(name: str, *, kit_dir: Path = KIT_DIR,
                    manifest_path: Path = PROFILE_PATH) -> RuntimeBundle:
    """Validate the whole manifest, then capture only the named profile's files.

    New files in the kit cannot enlarge a profile. No project URLs, network fetches,
    glob expansion or executable content are accepted by this resolver.
    """
    document, _ = _document(manifest_path)
    if name not in document["profiles"]:
        _error(f"unknown profile {name!r}")
    profile = document["profiles"][name]
    captured = {}
    for path, record in sorted(profile["files"].items()):
        data = _read(Path(kit_dir), path)
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            _error(f"hash mismatch for {path}; review dependencies and refresh the profile")
        captured[path] = data
    # Hash this profile only: an unrelated profile change must not alter a release.
    canonical = json.dumps({"schema": SCHEMA, "profile": name, **profile}, sort_keys=True,
                           separators=(",", ":")).encode()
    identity = {"profile": name, "profile_schema": SCHEMA,
                "profile_sha256": hashlib.sha256(canonical).hexdigest()}
    return RuntimeBundle(MappingProxyType(captured), MappingProxyType(identity))


def refresh_profiles(*, manifest_path: Path = PROFILE_PATH, kit_dir: Path = KIT_DIR):
    """Refresh hashes after reviewing the explicit dependency graph; no discovery.

    This source-maintenance action intentionally accepts changed bytes. Normal
    capture never refreshes a hash or silently accepts a changed installation.
    """
    document, _ = _document(manifest_path)
    for profile in document["profiles"].values():
        for path, record in profile["files"].items():
            record["sha256"] = hashlib.sha256(_read(Path(kit_dir), path)).hexdigest()
    Path(manifest_path).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refresh reviewed source hashes; never used during publication")
    args = parser.parse_args(argv)
    if args.refresh:
        refresh_profiles()
    document, _ = _document(PROFILE_PATH)
    for name in document["profiles"]:
        bundle = capture_profile(name)
        print(f"{name}: {len(bundle)} files, {sum(map(len, bundle.values()))} bytes, {bundle.identity['profile_sha256']}")


if __name__ == "__main__":
    main()
