"""Review package: a zip of the files named by ``cad.package.include`` plus a
sha256 manifest, written to the exports directory."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from cadagent.project import CadProject

@dataclass
class PackageResult:
    zip_path: Path
    manifest_path: Path
    files: Dict[str, str]
    unmatched: List[str] = field(default_factory=list)

def package_name(project: CadProject) -> str:
    if project.package.name:
        name = project.package.name
        return name if name.endswith(".zip") else name + ".zip"
    revision = project.resolve_revision()
    return f"{project.name}-rev{revision}.zip" if revision else f"{project.name}.zip"

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def build_package(project: CadProject) -> PackageResult:
    """Zip every file matched by the include globs (relative to the project root).

    Patterns that match nothing are returned in ``unmatched`` for the caller to
    report; a package with no files at all raises ``FileNotFoundError``.
    """
    if not project.package.include:
        raise ValueError("cad.package.include is empty; nothing to package")
    project.exports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = project.exports_dir / package_name(project)
    manifest_path = zip_path.with_name(zip_path.stem + "-manifest.json")
    own = {zip_path.resolve(), manifest_path.resolve()}
    files: List[Path] = []
    unmatched: List[str] = []
    for pattern in project.package.include:
        matched = sorted(p for p in project.root.glob(pattern) if p.is_file() and p.resolve() not in own)
        if not matched:
            unmatched.append(pattern)
        files.extend(p for p in matched if p not in files)
    if not files:
        raise FileNotFoundError(f"no files matched cad.package.include {project.package.include}")
    manifest = {p.relative_to(project.root).as_posix(): sha256(p) for p in files}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(project.root).as_posix())
        z.write(manifest_path, manifest_path.relative_to(project.root).as_posix())
    return PackageResult(zip_path, manifest_path, manifest, unmatched)
