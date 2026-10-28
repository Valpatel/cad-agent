"""Minimal 3MF writer with an independent read-back check.

One object per package, millimetres, centred in XY on the printer bed with its
lowest point on z=0. Written with ``zipfile`` + string XML (no networkx / lib3mf),
then re-read with a plain XML parser and compared with the source mesh: same
triangle count, edge-manifold (watertight with consistent winding), and volume
within ``VOLUME_RTOL``. A package that fails the comparison is deleted, not left
behind looking like a valid print file.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

from cadagent._deps import require

np = require("numpy", "3MF writing")

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
VOLUME_RTOL = 1e-3

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)

class Mesh3mfError(RuntimeError):
    """A written 3MF did not survive read-back intact."""

def center_on_bed(vertices: np.ndarray, bed_xy: Sequence[float]) -> np.ndarray:
    v = np.asarray(vertices, dtype=float)
    lo, hi = v.min(axis=0), v.max(axis=0)
    shift = np.array([bed_xy[0] / 2 - (lo[0] + hi[0]) / 2, bed_xy[1] / 2 - (lo[1] + hi[1]) / 2, -lo[2]])
    return v + shift

def model_xml(vertices: np.ndarray, faces: np.ndarray, name: str) -> str:
    verts = "".join(f'<vertex x="{a:.4f}" y="{b:.4f}" z="{c:.4f}"/>' for a, b, c in vertices)
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}">'
        f'<metadata name="Title">{escape(name)}</metadata>'
        f'<resources><object id="1" name={quoteattr(name)} type="model"><mesh>'
        f"<vertices>{verts}</vertices><triangles>{tris}</triangles>"
        "</mesh></object></resources><build><item objectid=\"1\"/></build></model>"
    )

def read_3mf(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Vertices and faces of every mesh in a 3MF package, concatenated."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    ns = {"m": CORE_NS}
    verts: List[List[float]] = []
    faces: List[List[int]] = []
    for mesh in root.iterfind(".//m:mesh", ns):
        base = len(verts)
        verts.extend([float(q.get(k)) for k in "xyz"] for q in mesh.iterfind("m:vertices/m:vertex", ns))
        faces.extend(
            [base + int(q.get(k)) for k in ("v1", "v2", "v3")]
            for q in mesh.iterfind("m:triangles/m:triangle", ns)
        )
    return np.array(verts, dtype=float).reshape(-1, 3), np.array(faces, dtype=np.int64).reshape(-1, 3)

def is_edge_manifold(faces: np.ndarray) -> bool:
    """Closed, consistently wound surface: every directed edge appears exactly once
    and its reverse exactly once."""
    f = np.asarray(faces, dtype=np.int64)
    if len(f) == 0:
        return False
    directed = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    if np.any(directed[:, 0] == directed[:, 1]):
        return False
    uniq, counts = np.unique(directed, axis=0, return_counts=True)
    if np.any(counts != 1):
        return False
    reverse = uniq[:, ::-1]
    reverse = reverse[np.lexsort((reverse[:, 1], reverse[:, 0]))]
    return bool(np.array_equal(reverse, uniq))

def mesh_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    tri = np.asarray(vertices, dtype=float)[np.asarray(faces, dtype=np.int64)]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)

def verify_3mf(path: Path, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, object]:
    """Compare a written package against the source mesh. ``ok`` is the verdict."""
    back_v, back_f = read_3mf(path)
    ref_volume = mesh_volume(vertices, faces)
    volume = mesh_volume(back_v, back_f) if len(back_f) else 0.0
    triangles_match = len(back_f) == len(faces)
    watertight = is_edge_manifold(back_f)
    volume_ok = ref_volume != 0 and abs(volume - ref_volume) <= VOLUME_RTOL * abs(ref_volume)
    return {
        "file": str(path),
        "triangles": int(len(back_f)),
        "source_triangles": int(len(faces)),
        "watertight": bool(watertight),
        "volume_mm3": round(volume, 3),
        "source_volume_mm3": round(ref_volume, 3),
        "ok": bool(triangles_match and watertight and volume_ok),
    }

def _entry(member: str) -> zipfile.ZipInfo:
    """A zip entry with a fixed date and mode, so the same mesh always gives the same
    bytes (the slice report keys each part on its 3MF's sha256)."""
    info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def write_3mf(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    name: str,
    bed_xy: Sequence[float],
) -> Dict[str, object]:
    """Write one centred 3MF and verify it; raises ``Mesh3mfError`` (and removes the
    file) when the read-back does not match."""
    path = Path(path)
    placed = center_on_bed(vertices, bed_xy)
    faces = np.asarray(faces, dtype=np.int64)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for member, data in (("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELS),
                             ("3D/3dmodel.model", model_xml(placed, faces, name))):
            z.writestr(_entry(member), data)
    report = verify_3mf(path, placed, faces)
    if not report["ok"]:
        path.unlink(missing_ok=True)
        raise Mesh3mfError(f"{path.name}: read-back mismatch {report}")
    return report

def export_parts_3mf(
    exports_dir: Path,
    part_names: Iterable[str],
    bed_xy: Sequence[float],
) -> List[Dict[str, object]]:
    """``<exports_dir>/<part>.stl`` -> ``<part>.3mf`` for every part, centred on the bed."""
    trimesh = require("trimesh", "3MF export (STL loading)")
    exports_dir = Path(exports_dir)
    reports = []
    for name in part_names:
        stl = exports_dir / f"{name}.stl"
        if not stl.is_file():
            raise FileNotFoundError(f"{stl} not found; run the build first")
        mesh = trimesh.load_mesh(stl, process=True)
        report = write_3mf(exports_dir / f"{name}.3mf", mesh.vertices, mesh.faces, name, bed_xy)
        report["part"] = name
        reports.append(report)
    return reports
