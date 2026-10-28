"""Shared integrity screen for source-bound CAD and PCB report records."""
import hashlib
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


def shape_content_hash(shape) -> str:
    """sha256 of a shape's BREP text: OCCT format version 1, no triangulation, no normals.

    The one content hash for shapes in cad-agent (the dossier's geometry record and the gates' pair
    cache both use it). Building the same shape gives the same bytes in any process. Two cautions:

    * the text includes the kernel's per-shape state flags, and meshing some shapes (a plain box,
      for one) clears a flag, so hash a shape before it is tessellated for an STL or a render;
    * a shape *read back* from BREP text may not write the same bytes again (the reader recomputes
      frames and matrices), so keep the hash recorded when the shape was built and never re-hash a
      loaded shape to identify it.

    Accepts a CadQuery or build123d shape (``.wrapped``) or a raw ``TopoDS_Shape``.
    """
    from io import BytesIO

    from cadagent._deps import require
    breptools = require("OCP.BRepTools", "shape content hash")
    toptools = require("OCP.TopTools", "shape content hash")
    buf = BytesIO()
    breptools.BRepTools.Write_s(getattr(shape, "wrapped", shape), buf, False, False,
                                toptools.TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1)
    return hashlib.sha256(buf.getvalue()).hexdigest()
