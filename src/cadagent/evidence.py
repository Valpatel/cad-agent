"""Shared integrity screen for source-bound CAD and PCB report records."""
import hashlib
import re
from pathlib import Path


def hashes_are_current(root: Path, data: dict) -> bool:
    """Check declared project-local hash maps; legacy records may omit them.

    This verifies bytes, not the truth of a reported physical or CAD result.
    A declared empty/invalid hash map fails instead of silently dropping evidence.
    """
    root = Path(root).resolve()
    try:
        for key in ('source_sha256', 'report_sha256', 'mechanical_sources', 'artifact_sha256'):
            if key not in data:
                continue
            values = data[key]
            if not isinstance(values, dict) or not values:
                return False
            for relative, expected in values.items():
                path = (root / relative).resolve()
                if root not in path.parents or not path.is_file():
                    return False
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    return False
        return True
    except (OSError, TypeError, ValueError):
        return False


# ------------------------------------------------------------------------------------- shape content hashes

_FLAG_LINES = re.compile(rb"^[01]{7}$", re.M)


def shape_brep_text(shape) -> bytes:
    """A shape's BREP text: OCCT format version 1, without triangulation or normals (so meshing a shape for an STL
    or a render does not change it). A normal BREP file (``cq.Shape.importBrep`` reads it). Needs OCP."""
    from io import BytesIO
    from OCP.BRepTools import BRepTools
    from OCP.TopTools import TopTools_FormatVersion
    buf = BytesIO()
    BRepTools.Write_s(getattr(shape, "wrapped", shape), buf, False, False,
                      TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1)
    return buf.getvalue()


def brep_content_hash(brep: bytes) -> str:
    """sha256 of a ``shape_brep_text`` with the per-shape flag lines (free, modified, checked, ...) removed: the
    kernel flips those on its own and they say nothing about the geometry. Use it to check a stored BREP file
    against the hash recorded when it was written."""
    return hashlib.sha256(_FLAG_LINES.sub(b"", brep)).hexdigest()


def shape_content_hash(shape) -> str:
    """The content hash of a CadQuery / build123d shape or a ``TopoDS_Shape``, shared by the dossier registry and
    the gates: ``brep_content_hash(shape_brep_text(shape))``.

    The same shape built the same way gives the same hash in any process and run; a change of geometry or of
    placement (the shape's location is part of the text) changes it; queries (volume, bounding box, ``isValid``,
    ``fix``) and tessellation do not. Two different constructions of the same geometry may hash differently (a
    cache miss, never a false match), and an OCCT upgrade may change every hash (sign-offs fall back to unreviewed,
    the safe direction). A shape *read back* from its BREP file is not guaranteed to hash the same, because the
    reader recomputes frame directions and location matrices: keep the hash recorded at build time and pass it
    along (``BuildResult.assembly_shapes(with_hashes=True)``); never re-hash a loaded shape to identify it.
    """
    return brep_content_hash(shape_brep_text(shape))
