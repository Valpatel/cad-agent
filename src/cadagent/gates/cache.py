"""Content hashes for shapes and a disk cache for pairwise relations.

OCP's own ``TopoDS_Shape`` hash is identity-based: it changes from one process
to the next, so it cannot key a cache that outlives a build. The hash here is a
sha256 of a canonical BREP text export of the shape, written *without*
triangulation (otherwise tessellating a shape for a render would change its
hash), and the placement is hashed separately as its rounded 3x4 matrix.

Two shapes built differently but geometrically equal can hash differently;
that only costs a cache miss. A hash match means the BREP bytes are identical,
not that the model is right.

The cache directory is not under ``exports/`` (which projects commit): the
default is ``.cadagent-cache/gates/`` at the project root, which the repository
``.gitignore`` lists. Deleting it is always safe.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from cadagent._deps import require

DEFAULT_CACHE_DIR = Path(".cadagent-cache") / "gates"


_FLAGS_LINE = re.compile(rb"^[01]{7}$", re.M)


def shape_hash(shape: Any) -> str:
    """sha256 of the shape's BREP text (format version 1, no triangles, no normals).

    The per-shape state flags (free, modified, checked, ...) are dropped from the text:
    the kernel flips them on its own (tessellating clears "checked"), and they say
    nothing about the geometry. Accepts a CadQuery or build123d shape (anything with ``.wrapped``) or a raw
    ``TopoDS_Shape``. The shape's own location, if it carries one, is part of the
    BREP text and therefore of the hash.
    """
    breptools = require("OCP.BRepTools", "shape content hash")
    toptools = require("OCP.TopTools", "shape content hash")
    buffer = io.BytesIO()
    breptools.BRepTools.Write_s(getattr(shape, "wrapped", shape), buffer, False, False,
                                toptools.TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1)
    return hashlib.sha256(_FLAGS_LINE.sub(b"", buffer.getvalue())).hexdigest()


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
