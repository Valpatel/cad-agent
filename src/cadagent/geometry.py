"""Geometry checks shared by CAD projects (cadquery / OCP / trimesh, all lazy).

These are screens computed from the CAD model. None of them certifies that a
printed part fits, prints without support, or survives load.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require

Rotation = Tuple[Tuple[float, float, float], float]

# The FILE_NAME time stamp export_step writes when SOURCE_DATE_EPOCH is not set: a fixed date, not the write time.
STEP_DATE = "2000-01-01T00:00:00"

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

def step_timestamp() -> str:
    """The time stamp ``export_step`` writes in the STEP header's ``FILE_NAME``; never the write time.

    ``SOURCE_DATE_EPOCH`` when it is set: the reproducible-builds convention
    (https://reproducible-builds.org/specs/source-date-epoch/), seconds since 1970-01-01 UTC, written in UTC as
    ``YYYY-MM-DDThh:mm:ss``. Otherwise ``STEP_DATE``, a fixed date. A value that is not a whole number of
    seconds raises ``ValueError``, as the convention asks, rather than being ignored.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw:
        return STEP_DATE
    try:
        if not (raw.isascii() and raw.isdigit()):
            raise ValueError
        stamp = datetime.datetime.fromtimestamp(int(raw), datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise ValueError(f"SOURCE_DATE_EPOCH={raw!r} is not a whole number of seconds since 1970-01-01") from None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")

def _step_string(value: str, what: str) -> str:
    """``value`` if it can go in a STEP string as it is: printable ASCII. OCCT doubles quotes and backslashes."""
    if not value or not all(" " <= c <= "~" for c in value):
        raise ValueError(f"{what} {value!r} is not printable ASCII; pass export_step a name= that is")
    return value

def export_step(shape: Any, path: Path, name: Optional[str] = None) -> Path:
    """Write ``shape`` as a STEP file that has the same bytes every time the same model is exported.

    ``cadquery.exporters.export`` puts three things in a STEP file that change with no geometry change: the write
    time (header ``FILE_NAME``); the product name ``Open CASCADE STEP translator <version> <n>``, where ``n`` counts
    the exports made in the process; and, for a shape of several solids, assembly-link
    (``NEXT_ASSEMBLY_USAGE_OCCURRENCE``) ids counted across the process. This writes the same geometry with the same
    writer and settings (AP214, millimetres, pcurves), and sets those three through OCCT's model after the transfer
    and before the file is written, so no text is rewritten:

    * ``FILE_NAME``: the file's name, and ``step_timestamp()`` (``SOURCE_DATE_EPOCH``, else ``STEP_DATE``);
    * the product: ``name`` (default: the file's stem). The products of a multi-solid shape keep OCCT's numbering
      under it: ``<name>.1``, ``<name>.2``, ...;
    * assembly-link ids: 1, 2, ... in file order.

    OCCT writes the name as a STEP string, doubling quotes and backslashes; the name and the file's name must be
    printable ASCII (``ValueError``). ``shape`` is a cadquery Shape or Workplane (several objects become one
    compound, as ``cadquery.exporters.export`` does), a build123d shape or an OCP ``TopoDS_Shape``. A cadquery
    ``Assembly`` is refused (``TypeError``): it needs the XCAF writer, which this does not make reproducible (#150).

    Limits: the other header fields stay as OCCT writes them (placeholder author and organisation, OCCT's version as
    preprocessor and originating system), and another OCCT version can write different bytes for the same geometry.
    The file is written next to ``path`` and renamed into place. Returns ``path``.
    """
    cq = require("cadquery", "STEP export")
    from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.StepBasic import StepBasic_Product
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence
    from OCP.TCollection import TCollection_HAsciiString

    path = Path(path)
    name = _step_string(path.stem if name is None else name, "STEP product name")
    _step_string(path.name, "STEP file name")
    if isinstance(shape, cq.Assembly):
        raise TypeError("export_step writes shapes, not a cadquery Assembly (Assembly.save writes those, "
                        "with a time stamp and ids that are not reproducible yet: #150)")
    if isinstance(shape, cq.Workplane):
        objs = [o for o in shape.vals() if isinstance(o, cq.Shape)]
        if not objs:
            raise ValueError(f"{path.name}: the Workplane holds no shapes")
        shape = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)

    writer = STEPControl_Writer()
    # cadquery's exportStep settings, set on every call: they are process-wide, and an earlier export may have
    # changed them.
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    Interface_Static.SetIVal_s("write.precision.mode", 0)
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    if writer.Transfer(getattr(shape, "wrapped", shape), STEPControl_AsIs) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise GeometryError(f"{path.name}: OCCT could not transfer the shape to STEP")
    model = writer.Model()

    # Edited after Transfer, which builds the model the header and entities belong to. Techniques adopted:
    # - the header through APIHeaderSection_MakeHeader (SetName, SetTimeStamp): build123d's export_step
    #   (https://github.com/gumyr/build123d, src/build123d/exporters3d.py, Apache-2.0);
    # - assembly-link ids renumbered 1..N on the model, and a fixed date: text-to-cad's cadgen step_export
    #   (https://github.com/earthtojake/text-to-cad, packages/cadgen/src/cadgen/step_export.py, MIT; vendored here);
    # - the fixed date 2000-01-01T00:00:00 and the product named after the file: the J501 enclosure's export_step
    #   (https://github.com/mvalancy/j501-agx-orin/issues/12), which rewrote the text after writing.
    header = APIHeaderSection_MakeHeader(model)
    if not header.IsDone():
        raise GeometryError(f"{path.name}: OCCT made no STEP header")
    header.SetName(TCollection_HAsciiString(path.name))
    header.SetTimeStamp(TCollection_HAsciiString(step_timestamp()))

    def entities(kind: Any) -> List[Any]:
        found, it = [], model.Entities()
        it.SelectType(kind.get_type_descriptor_s(), True)
        it.Start()
        while it.More():
            found.append(it.Value())
            it.Next()
        return found

    products = entities(StepBasic_Product)
    links = entities(StepRepr_NextAssemblyUsageOccurrence)
    children = {link.RelatedProductDefinition().Formation().OfProduct().Name().ToCString() for link in links}
    roots = [p for p in products if p.Name().ToCString() not in children]
    if len(roots) != 1:
        raise GeometryError(f"{path.name}: expected one top-level STEP product, found {len(roots)}")
    old = roots[0].Name().ToCString()
    for product in products:
        current = product.Name().ToCString()
        if current != old and not current.startswith(old + "."):
            # Every product of one transferred shape is numbered under the top one; anything else would keep
            # OCCT's per-process counter, so stop rather than write a file that is not reproducible.
            raise GeometryError(f"{path.name}: product {current!r} is not numbered under {old!r}")
        renamed = TCollection_HAsciiString(name + current[len(old):])
        product.SetName(renamed)
        product.SetId(renamed)
    for number, link in enumerate(links, 1):
        link.SetId(TCollection_HAsciiString(str(number)))

    part = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        if writer.Write(str(part)) != IFSelect_ReturnStatus.IFSelect_RetDone or not part.is_file():
            raise GeometryError(f"OCCT could not write {path}")
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    return path

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
