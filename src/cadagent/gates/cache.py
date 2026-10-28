"""The disk cache for pairwise relations, and the placement key that goes with a content hash.

A part's cache identity is its content hash (``cadagent.evidence.shape_content_hash``, the one
hash function shared with the dossier's geometry record) plus its placement as a rounded 3x4
matrix. OCP's own ``TopoDS_Shape`` hash is identity-based and changes between processes, so it
cannot key a cache. A shape read back from a BREP file must use the hash recorded when it was
built (``Assembly.add(..., content_hash=...)``, ``Assembly.from_build``), not a re-hash.

Two shapes built differently but geometrically equal can hash differently; that only costs a
cache miss. A hash match means the BREP bytes are identical, not that the model is right.

The cache directory is not under ``exports/`` (which projects commit): the default is
``.cadagent-cache/gates/`` at the project root, which the repository ``.gitignore`` lists.
Deleting it is always safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from cadagent.evidence import shape_content_hash  # noqa: F401 (re-exported)

DEFAULT_CACHE_DIR = Path(".cadagent-cache") / "gates"


def matrix_key(matrix: Sequence[float], digits: int = 9) -> str:
    """Canonical text of a 3x4 placement matrix, rounded to ``digits`` (so -0.0 and float noise agree)."""
    return ",".join(f"{(round(float(v), digits) + 0.0):.{digits}f}" for v in matrix)


def digest(*parts: str) -> str:
    """sha256 over the given strings, separated so ("ab", "c") and ("a", "bc") differ."""
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


class PairCache:
    """JSON files keyed by a hex digest: ``<directory>/<key[:2]>/<key>.json``.

    ``hits`` and ``misses`` count lookups since construction. Writes are atomic
    (temporary file and rename), so a killed run never leaves half a record;
    an unreadable record counts as a miss and is overwritten.
    """

    def __init__(self, directory: Any = DEFAULT_CACHE_DIR):
        self.directory = Path(directory)
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        if len(key) < 8 or not all(c in "0123456789abcdef" for c in key):
            raise ValueError(f"cache key must be a hex digest, got {key!r}")
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._path(key)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.misses += 1
            return None
        self.hits += 1
        return data

    def put(self, key: str, value: Dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(value, handle)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
