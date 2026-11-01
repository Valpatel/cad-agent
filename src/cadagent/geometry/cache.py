"""A BREP cache of built parts, so a build rebuilds only the parts whose sources changed (#250).

A project's build that makes every part on every run spends most of its time on parts nothing touched. ``PartCache``
stores each built part as a BREP file under a hash of the files and parameters it was built from, and loads it back
instead of rebuilding while that hash is unchanged::

    from cadagent.geometry.cache import PartCache

    cache = PartCache("exports/.partcache", sources=["cad/parameters.json", "cad/common.py"],
                      key_extra={"variant": "long-reach"})
    boom = cache.get_or_build("boom", build_boom, deps=["cad/boom.py"])
    parts = cache.get_all({"boom": (build_boom, ["cad/boom.py"]), "bucket": (build_bucket, ["cad/bucket.py"])})

Layout: ``<root>/<key>/<name>.brep`` and ``<root>/<key>/<name>.json``. ``key`` is 16 hex digits of a sha256 over the
cache format, the cadquery version, every ``sources`` file (name and bytes), ``key_extra`` (as sorted JSON) and the
part's own ``deps`` files, so editing a dependency rebuilds only the parts that list it; parts with no ``deps`` share
one folder. The JSON records the BREP file's sha256, the solid's validity (``isValid``), solid count and volume; on
load all four are checked, and a part whose record is missing, unreadable or different, or whose BREP does not
import, is rebuilt and stored again. Files are written next to their final name and renamed into place (BREP first,
then the JSON that vouches for it), so a parallel run or a killed one never reads half a file.

``max_bytes`` caps the folder's size: after a part is stored, the least recently used key folders are removed until
the cache fits, never one this process has used. ``clear()`` removes every key folder. The root holds a
``CACHEDIR.TAG`` (https://bford.info/cachedir/), which ``cad-agent package`` and backup tools skip.

Limits: the key covers only the files and values it is given. A part that reads a file or setting not listed in
``sources``, ``deps`` or ``key_extra`` is not rebuilt when that changes: list everything the builder reads, or call
``clear()``. The checks on load catch a damaged file, not a stale one. A cached part is the same B-rep, not a
re-run of the build: warnings or side effects of the builder do not happen on a hit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from cadagent._deps import require

PathLike = Union[str, Path]
Builder = Callable[[], Any]

# Bump when the layout or the record changes: old folders then stop matching and are rebuilt.
FORMAT = 1
KEY_LENGTH = 16
CACHE_TAG = "CACHEDIR.TAG"
CACHE_TAG_TEXT = ("Signature: 8a477f597d28d172789f06886806bc55\n"
                  "# This folder is a cad-agent part cache (cadagent.geometry.cache); it can be deleted.\n")
# Relative and absolute volume tolerance on load. A BREP round trip keeps the geometry exactly, so these only absorb
# the floating-point noise of recomputing the volume.
VOLUME_RTOL = 1e-7
VOLUME_ATOL_MM3 = 1e-6
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_KEY = re.compile(rf"^[0-9a-f]{{{KEY_LENGTH}}}$")
_SKIP_DIRS = {"__pycache__", ".git"}


def _files(paths: Iterable[PathLike], what: str) -> List[Tuple[str, Path]]:
    """``(label, file)`` for each path: a file as itself, a folder as every file under it (``__pycache__``, ``.git``
    and ``*.pyc`` left out) labelled by its path inside the folder. A missing path raises ``FileNotFoundError``: a
    source that is silently left out would keep a stale part."""
    out: List[Tuple[str, Path]] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            out.append((p.name, p))
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(p)
                if f.is_file() and f.suffix != ".pyc" and not _SKIP_DIRS.intersection(rel.parts):
                    out.append((f"{p.name}/{rel.as_posix()}", f))
        else:
            raise FileNotFoundError(f"part cache {what} {str(raw)!r} does not exist")
    return out


def _digest(files: Sequence[Tuple[str, Path]]) -> str:
    h = hashlib.sha256()
    for label, f in sorted(files, key=lambda item: (item[0], str(item[1]))):
        data = f.read_bytes()
        h.update(f"{label}\0{len(data)}\0".encode())
        h.update(data)
    return h.hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _replace_atomically(path: Path, write: Callable[[str], None]) -> None:
    """Call ``write(tmp)`` for a temporary file next to ``path``, then rename it to ``path``."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


class PartCache:
    """Built parts cached as BREP under ``root``, keyed by the hash of ``sources``, ``key_extra`` and each part's
    ``deps`` (module docstring).

    ``hits`` and ``misses`` count lookups since construction; ``rebuilt`` maps a part that had a record which failed
    its check on load to the reason (``"brep sha256 differs"``, ``"volume differs"``, ...).
    """

    def __init__(self, root: PathLike, sources: Iterable[PathLike] = (), key_extra: Any = None,
                 max_bytes: Optional[int] = None):
        if max_bytes is not None and max_bytes < 0:
            raise ValueError(f"max_bytes must be at least 0, got {max_bytes}")
        self.root = Path(root)
        self.sources = [Path(s) for s in sources]
        self.key_extra = key_extra
        self.max_bytes = max_bytes
        self.hits = 0
        self.misses = 0
        self.rebuilt: Dict[str, str] = {}
        try:
            extra = json.dumps(key_extra, sort_keys=True, default=repr)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"key_extra must be JSON-like (dicts, lists, numbers, text): {exc}") from None
        self._base = hashlib.sha256("\0".join(
            [f"cadagent.partcache/{FORMAT}", _cadquery_version(), _digest(_files(self.sources, "source")), extra]
        ).encode()).hexdigest()
        self._used: set = set()
        self._memo: Dict[Tuple[str, str], Any] = {}

    def key(self, deps: Optional[Iterable[PathLike]] = None) -> str:
        """The key folder name for a part with these ``deps`` (the shared one without)."""
        deps = list(deps or ())
        if not deps:
            return self._base[:KEY_LENGTH]
        return hashlib.sha256(f"{self._base}\0{_digest(_files(deps, 'dependency'))}".encode()).hexdigest()[:KEY_LENGTH]

    def path(self, name: str, deps: Optional[Iterable[PathLike]] = None) -> Path:
        """Where part ``name`` with these ``deps`` is stored (``<root>/<key>/<name>.brep``)."""
        if not isinstance(name, str) or not _NAME.match(name):
            raise ValueError(f"part name {name!r} is not usable as a file name (letters, digits, '_', '-', '.')")
        return self.root / self.key(deps) / f"{name}.brep"

    def get_or_build(self, name: str, fn: Builder, deps: Optional[Iterable[PathLike]] = None) -> Any:
        """Part ``name``: loaded from the cache when its record checks out, else ``fn()`` built and stored.

        ``fn`` takes no arguments and returns a cadquery ``Shape`` or a ``Workplane`` (its objects become one compound,
        as in ``export_step``). Returns a cadquery ``Shape`` either way; the same object on later calls in this
        process.
        """
        cq = require("cadquery", "the part cache")
        brep = self.path(name, deps)
        key = brep.parent.name
        self._used.add(key)
        memo = self._memo.get((key, name))
        if memo is not None:
            self.hits += 1
            return memo
        shape, reason = self._load(cq, brep)
        if shape is not None:
            self.hits += 1
            try:
                os.utime(brep.parent)                     # recently used: the size cap removes others first
            except OSError:
                pass
        else:
            self.misses += 1
            if reason:
                self.rebuilt[name] = reason
            shape = _as_shape(cq, fn(), name)
            self._store(shape, brep)
            self.prune()
        self._memo[(key, name)] = shape
        return shape

    def get_all(self, builders: Mapping[str, Union[Builder, Tuple[Builder, Iterable[PathLike]]]]) -> Dict[str, Any]:
        """``{name: shape}`` for every builder, in order: each value is a builder, or ``(builder, deps)``."""
        out: Dict[str, Any] = {}
        for name, spec in builders.items():
            fn, deps = (spec if isinstance(spec, tuple) else (spec, None))
            out[name] = self.get_or_build(name, fn, deps)
        return out

    def clear(self) -> None:
        """Remove every key folder (and anything else this cache wrote) under ``root``; other files are kept."""
        self._memo.clear()
        if not self.root.is_dir():
            return
        for child in self.root.iterdir():
            if child.is_dir() and _KEY.match(child.name):
                shutil.rmtree(child, ignore_errors=True)
        (self.root / CACHE_TAG).unlink(missing_ok=True)
        try:
            self.root.rmdir()
        except OSError:
            pass                                          # not empty: something else lives there

    def size(self) -> int:
        """Bytes in the key folders under ``root``."""
        return sum(size for _, _, size in self._folders())

    def prune(self, max_bytes: Optional[int] = None) -> List[Path]:
        """Remove the least recently used key folders until the cache is at most ``max_bytes`` (default: the
        constructor's; no cap: nothing is removed). Folders this process used are kept even if the cache stays over.
        Returns the folders removed."""
        cap = self.max_bytes if max_bytes is None else max_bytes
        if cap is None:
            return []
        folders = self._folders()
        total = sum(size for _, _, size in folders)
        removed: List[Path] = []
        for _, folder, size in sorted(folders):
            if total <= cap:
                break
            if folder.name in self._used:
                continue
            shutil.rmtree(folder, ignore_errors=True)
            total -= size
            removed.append(folder)
        return removed

    # internals

    def _folders(self) -> List[Tuple[float, Path, int]]:
        """``(mtime, folder, bytes)`` for each key folder."""
        out = []
        if not self.root.is_dir():
            return out
        for child in self.root.iterdir():
            if not (child.is_dir() and _KEY.match(child.name)):
                continue
            try:
                size = sum(f.stat().st_size for f in child.iterdir() if f.is_file())
                out.append((child.stat().st_mtime, child, size))
            except OSError:
                continue                                  # removed by a parallel run
        return out

    def _load(self, cq: Any, brep: Path) -> Tuple[Any, str]:
        """``(shape, "")`` when the stored part checks out, else ``(None, reason)``; reason is "" with no record."""
        record_path = brep.with_suffix(".json")
        if not record_path.exists():
            return None, ""
        try:
            record = json.loads(record_path.read_text())
            expected = (record["format"], record["brep_sha256"], bool(record["valid"]), int(record["solids"]),
                        float(record["volume_mm3"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None, "record unreadable"
        if expected[0] != FORMAT:
            return None, "record format differs"
        try:
            if _sha256(brep) != expected[1]:
                return None, "brep sha256 differs"
            shape = cq.Shape.importBrep(str(brep))
        except Exception:                                # OSError, or OCCT's ValueError on a damaged file
            return None, "brep does not import"
        if shape is None or shape.wrapped is None or shape.wrapped.IsNull():
            return None, "brep does not import"
        valid, solids, volume = _measure(shape)
        if valid != expected[2]:
            return None, "validity differs"
        if solids != expected[3]:
            return None, "solid count differs"
        if abs(volume - expected[4]) > VOLUME_ATOL_MM3 + VOLUME_RTOL * abs(expected[4]):
            return None, "volume differs"
        return shape, ""

    def _store(self, shape: Any, brep: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tag = self.root / CACHE_TAG
        if not tag.exists():
            _replace_atomically(tag, lambda tmp: Path(tmp).write_text(CACHE_TAG_TEXT))
        brep.parent.mkdir(parents=True, exist_ok=True)

        def write_brep(tmp: str) -> None:
            if shape.exportBrep(tmp) is False:
                raise OSError(f"OCCT could not write {brep}")

        _replace_atomically(brep, write_brep)
        valid, solids, volume = _measure(shape)
        record = {"format": FORMAT, "name": brep.stem, "key": brep.parent.name, "brep_sha256": _sha256(brep),
                  "valid": valid, "solids": solids, "volume_mm3": volume}
        _replace_atomically(brep.with_suffix(".json"),
                            lambda tmp: Path(tmp).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n"))


def _measure(shape: Any) -> Tuple[bool, int, float]:
    return bool(shape.isValid()), len(shape.Solids()), float(shape.Volume())


def _as_shape(cq: Any, built: Any, name: str) -> Any:
    if isinstance(built, cq.Workplane):
        objs = [o for o in built.vals() if isinstance(o, cq.Shape)]
        if not objs:
            raise ValueError(f"part {name!r}: the builder's Workplane holds no shapes")
        built = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)
    if not isinstance(built, cq.Shape):
        raise TypeError(f"part {name!r}: the builder returned {type(built).__name__}, not a cadquery Shape or Workplane")
    return built


def _cadquery_version() -> str:
    """cadquery's version, part of every key: another version can build or read the same source differently."""
    try:
        import cadquery
    except ImportError:
        return "no-cadquery"
    return str(getattr(cadquery, "__version__", "unknown"))
