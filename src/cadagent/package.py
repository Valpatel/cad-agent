"""Review package: a zip of the files named by ``cad.package.include`` plus a
sha256 manifest, written to the exports directory. Files inside a folder tagged with ``CACHEDIR.TAG`` (a part cache,
``cadagent.geometry.cache``) are never packaged, even when an include glob reaches them.

The zip is reproducible (#150): the same files give the same bytes on every rebuild and in every checkout. Its
entries are sorted by path, and each has the same date, mode and host instead of the file's own: the date is
``SOURCE_DATE_EPOCH``, else the time of the last commit that changed the project (``cadagent.project.source_time``),
else ``ZIP_DATE``; the mode is ``rw-r--r--`` and the host Unix. Limit: another zlib build (stock zlib or zlib-ng) can
compress the same files to different bytes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cadagent.project import CadProject, source_time

# The entry date when there is no SOURCE_DATE_EPOCH or commit to take it from: the earliest a zip can store.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)

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
    tagged: Dict[Path, bool] = {}
    for pattern in project.package.include:
        matched = sorted(p for p in project.root.glob(pattern) if p.is_file() and p.resolve() not in own
                         and not in_cache_dir(p, project.root, tagged))
        if not matched:
            unmatched.append(pattern)
        files.extend(p for p in matched if p not in files)
    if not files:
        raise FileNotFoundError(f"no files matched cad.package.include {project.package.include}")
    found = source_time(project.root, outputs=[zip_path, manifest_path])    # first: a bad SOURCE_DATE_EPOCH stops here
    date = zip_date(found[0] if found else None)
    manifest = {p.relative_to(project.root).as_posix(): sha256(p) for p in files}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    entries = sorted([(p.relative_to(project.root).as_posix(), p) for p in files]
                     + [(manifest_path.relative_to(project.root).as_posix(), manifest_path)])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, p in entries:
            info = zip_entry(name, date)
            info.file_size = p.stat().st_size         # so a file over 2 GiB gets its zip64 header
            with open(p, "rb") as src, z.open(info, "w") as dst:      # streamed: big files stay out of memory
                shutil.copyfileobj(src, dst, 1 << 20)
    return PackageResult(zip_path, manifest_path, manifest, unmatched)

def _tagged(folder: Path) -> bool:
    """``folder/CACHEDIR.TAG`` starts with the spec's signature line (what tar's ``--exclude-caches`` checks)."""
    try:
        with open(folder / "CACHEDIR.TAG", "rb") as fh:
            return fh.read(43) == b"Signature: 8a477f597d28d172789f06886806bc55"
    except OSError:
        return False

def in_cache_dir(path: Path, root: Path, seen: Optional[Dict[Path, bool]] = None) -> bool:
    """True when a folder between ``root`` and ``path`` holds a ``CACHEDIR.TAG`` (https://bford.info/cachedir/), such
    as a part cache (``cadagent.geometry.cache``): caches are never packaged, even when a glob reaches into them."""
    seen = {} if seen is None else seen
    for folder in path.parents:
        if folder == root or root not in folder.parents:
            return False
        if folder not in seen:
            seen[folder] = _tagged(folder)
        if seen[folder]:
            return True
    return False

def zip_date(when: Optional[datetime.datetime]) -> Tuple[int, int, int, int, int, int]:
    """A zip entry date from a time (taken as UTC): ``ZIP_DATE`` for None, and clamped to the years a zip can store
    (1980 to 2107). Zip dates have no time zone and a two-second step."""
    if when is None:
        return ZIP_DATE
    if when.tzinfo is not None:
        when = when.astimezone(datetime.timezone.utc)
    if when.year < 1980:
        return ZIP_DATE
    if when.year > 2107:
        return (2107, 12, 31, 23, 59, 58)
    return (when.year, when.month, when.day, when.hour, when.minute, when.second - when.second % 2)

def zip_entry(name: str, date: Tuple[int, int, int, int, int, int]) -> zipfile.ZipInfo:
    """A deflated zip entry with a fixed date, mode (regular file, ``rw-r--r--``) and host (Unix), whatever the
    file's own and the machine's are: the pattern of ``cadagent.publish.release`` and
    ``cadagent.manufacturing.mesh3mf``."""
    info = zipfile.ZipInfo(name, date_time=date)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info
