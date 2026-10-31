"""Geometry checks shared by CAD projects (cadquery / OCP / trimesh, all lazy).

These are screens computed from the CAD model. None of them certifies that a
printed part fits, prints without support, or survives load.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require

Rotation = Tuple[Tuple[float, float, float], float]

class GeometryError(RuntimeError):
    """A part failed a hard geometry requirement (e.g. a non-watertight STL)."""

def solid_report(shape: Any) -> Dict[str, Any]:
    """Validity, solid count, volume and bounding box of a cadquery Shape."""
    bb = shape.BoundingBox()
    return {
        "cad_valid": bool(shape.isValid()),
        "solid_count": len(shape.Solids()),
        "volume_cm3": round(shape.Volume() / 1000.0, 3),
        "bounds_mm": [round(v, 3) for v in (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)],
        "size_mm": [round(v, 3) for v in (bb.xlen, bb.ylen, bb.zlen)],
    }

def flatten_to_bed(shape: Any) -> Any:
    """Translate so the bounding box minimum sits at the origin (z=0 is the bed)."""
    bb = shape.BoundingBox()
    return shape.translate((-bb.xmin, -bb.ymin, -bb.zmin))

def export_print_stl(
    shape: Any,
    path: Path,
    rotation: Optional[Rotation] = None,
    tolerance: float = 0.05,
    angular: float = 0.12,
) -> Dict[str, Any]:
    """Export ``shape`` as an STL in print orientation and report on the mesh.

    ``rotation`` is ``(axis, degrees)`` about the origin, applied before the part
    is flattened onto z=0. Degenerate tessellation faces are removed and the STL
    rewritten. Raises ``GeometryError`` if the resulting mesh is not watertight.
    """
    cq = require("cadquery", "STL export")
    trimesh = require("trimesh", "STL watertight check")
    path = Path(path)
    print_shape = shape
    if rotation is not None:
        axis, degrees = rotation
        print_shape = print_shape.rotate((0, 0, 0), tuple(axis), degrees)
    print_shape = flatten_to_bed(print_shape)
    cq.exporters.export(print_shape, str(path), tolerance=tolerance, angularTolerance=angular)
    mesh = trimesh.load_mesh(path)
    keep = mesh.nondegenerate_faces()
    removed = int((~keep).sum())
    if removed:
        mesh.update_faces(keep)
        mesh.remove_unreferenced_vertices()
        mesh.export(path)
    report = {
        "degenerate_tessellation_faces_removed": removed,
        "cad_valid": bool(shape.isValid()),
        "solid_count": len(shape.Solids()),
        "watertight": bool(mesh.is_watertight),
        "print_bounds_mm": [round(float(v), 3) for v in mesh.extents],
        "volume_cm3": round(shape.Volume() / 1000.0, 3),
    }
    if not report["watertight"]:
        raise GeometryError(f"non-watertight STL: {path}")
    return report

def pairwise_intersections(
    named_shapes: Mapping[str, Any],
    skip_pairs: Iterable[Sequence[str]] = (),
) -> List[Dict[str, Any]]:
    """Exact boolean intersection volume (mm^3) for every unordered pair.

    ``skip_pairs`` lists pairs that never coexist (alternative variants of one part).
    """
    skip = {frozenset(p) for p in skip_pairs}
    names = list(named_shapes)
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if frozenset((a, b)) in skip:
                continue
            volume = named_shapes[a].intersect(named_shapes[b]).Volume()
            rows.append({"parts": [a, b], "intersection_mm3": round(float(volume), 6)})
    return rows

def min_gap(a: Any, b: Any) -> float:
    """Minimum distance (mm) between two shapes; 0 when they touch or overlap."""
    extrema = require("OCP.BRepExtrema", "minimum-gap measurement")
    dist = extrema.BRepExtrema_DistShapeShape(_wrapped(a), _wrapped(b))
    dist.Perform()
    if not dist.IsDone():
        raise GeometryError("BRepExtrema_DistShapeShape did not converge")
    return float(dist.Value())

def _wrapped(shape: Any) -> Any:
    return getattr(shape, "wrapped", shape)

def downward_area(
    mesh: Any,
    max_angle_deg: float = 47.0,
    bed_z: float = 0.3,
    large_face_mm2: float = 0.5,
) -> Dict[str, Any]:
    """Overhang screen for a mesh in print orientation.

    Counts faces whose normal points down more steeply than ``max_angle_deg``
    below horizontal, excluding faces within ``bed_z`` of the bed (they sit on it).
    Accepts a trimesh-like object or an STL path. A screen, not a slicer: short
    bridges and chamfers are counted too.
    """
    np = require("numpy", "overhang screen")
    if isinstance(mesh, (str, Path)):
        mesh = require("trimesh", "overhang screen").load_mesh(mesh)
    normals = np.asarray(mesh.face_normals)
    centers = np.asarray(mesh.triangles_center)
    areas = np.asarray(mesh.area_faces)
    mask = (normals[:, 2] < -np.sin(np.deg2rad(max_angle_deg))) & (centers[:, 2] > bed_z)
    faces = np.flatnonzero(mask)
    large = faces[areas[faces] > large_face_mm2]
    return {
        "downward_area_mm2": round(float(areas[faces].sum()), 3),
        "max_angle_deg": max_angle_deg,
        "large_face_centers_mm": centers[large].round(3).tolist(),
    }

def within_bed(bounds: Sequence[float], bed: Sequence[float]) -> bool:
    """True when every extent fits the bed; a 2-value bed checks X and Y only."""
    if len(bounds) < len(bed):
        raise ValueError(f"bounds {list(bounds)} has fewer axes than bed {list(bed)}")
    return all(float(b) <= float(limit) for b, limit in zip(bounds, bed))
