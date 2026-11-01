"""Geometry checks shared by CAD projects (cadquery / OCP / trimesh, all lazy).

These are screens computed from the CAD model. None of them certifies that a
printed part fits, prints without support, or survives load.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require

Rotation = Tuple[Tuple[float, float, float], float]

# The FILE_NAME time stamp export_step writes when SOURCE_DATE_EPOCH is not set: a fixed date, not the write time.
STEP_DATE = "2000-01-01T00:00:00"
# The STEP writer settings export_step uses on every call, because they are process-wide and earlier code may have
# changed them: cadquery's exportStep defaults (pcurves, precision mode 0, millimetres) and the schema, AP214 (OCCT's
# default; cadquery never sets it, but project code may choose AP242). The previous values are put back afterwards.
STEP_SETTINGS = (("write.surfacecurve.mode", 1), ("write.precision.mode", 0), ("xstep.cascade.unit", "MM"),
                 ("write.step.unit", "MM"), ("write.step.schema", "AP214IS"))
# OCCT's STEP reader ends a string early at a doubled quote followed by spaces or double quotes and then ',' or ')':
# it reads 'post (6'')' or 'a''")' back as no name at all, although Part 21 allows both. The rule matched the reader
# on 1,572 probes (review of #149). The vendored text-to-cad step_export documents the space case (_MISREAD_QUOTE)
# and rewrites the quote as \X\27 in the text; through the API that is not possible, because OCCT doubles the
# backslash, so such names are refused.
_MISREAD_QUOTE = re.compile(r"'[ \"]*[,)]")

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
    seconds raises ``ValueError`` (``cadagent.project.SourceDateEpochError``), as the convention asks, rather than
    being ignored.
    """
    from cadagent.project import source_date_epoch

    epoch = source_date_epoch()
    if epoch is None:
        return STEP_DATE
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def _step_string(value: str, what: str, fix: str) -> str:
    """``value`` if it can go in a STEP string as it is and read back the same: printable ASCII, and no quote
    followed by ``,`` or ``)`` with only spaces or double quotes between (``_MISREAD_QUOTE``). OCCT doubles quotes
    and backslashes. ``fix`` ends the error."""
    if not value or not all(" " <= c <= "~" for c in value):
        raise ValueError(f"{what} {value!r} is not printable ASCII; {fix}")
    if _MISREAD_QUOTE.search(value):
        raise ValueError(f"{what} {value!r} has a quote followed by ',' or ')', with only spaces or double quotes "
                         f"between, which OCCT's STEP reader misreads (it loses the name); {fix}")
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

    OCCT writes the name as a STEP string, doubling quotes and backslashes. The name and the file's name must be
    printable ASCII with no quote followed by ``,`` or ``)`` (spaces or double quotes between count), which OCCT's
    reader misreads (``ValueError``).
    ``shape`` is a cadquery Shape or Workplane (several objects become one compound, as ``cadquery.exporters.export``
    does), a build123d shape or an OCP ``TopoDS_Shape``, or a cadquery ``Assembly`` (#150): that is written as
    ``Assembly.save`` writes it (OCCT's XCAF writer, colours and names), with the header and link ids fixed as for a
    shape, the top product named ``name`` (default: the assembly's own name, or the file's stem when cadquery gave
    it a uuid), each node added without a name called ``<parent>.<k>`` instead of a random uuid, and the colour
    records in one order (``cadagent.geometry._assembly_step``). Sub-shape names and colours
    (``Assembly.addSubshape``) are refused (``ValueError``).

    Limits: the other header fields stay as OCCT writes them (placeholder author and organisation, OCCT's version as
    preprocessor and originating system). The writer settings in ``STEP_SETTINGS`` are set for the call and put
    back after it, so later ``cadquery.exporters.export`` calls keep the project's own. Other process-wide ones that
    cadquery never sets (``write.step.nonmanifold``, ``write.precision.val``, ...) still apply if project code
    changes them. Another OCCT version can write different bytes for the same geometry.
    The file is written next to ``path`` and renamed into place. Returns ``path``.
    """
    cq = require("cadquery", "STEP export")
    from OCP.STEPControl import STEPControl_Writer

    path = Path(path)
    _step_string(path.name, "STEP file name", "rename the file (the header's FILE_NAME is the file's own name)")
    if isinstance(shape, cq.Assembly):
        from cadagent.geometry._assembly_step import write_assembly

        write_assembly(shape, path, name, _step_string, _swap_step_settings, STEP_SETTINGS)
        return path
    name = _step_string(path.stem if name is None else name, "STEP product name", "pass export_step another name=")
    if isinstance(shape, cq.Workplane):
        objs = [o for o in shape.vals() if isinstance(o, cq.Shape)]
        if not objs:
            raise ValueError(f"{path.name}: the Workplane holds no shapes")
        shape = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)

    writer = STEPControl_Writer()                         # registers the settings swapped in below
    previous = _swap_step_settings(STEP_SETTINGS)
    try:
        _transfer_and_write(writer, getattr(shape, "wrapped", shape), path, name)
    finally:
        _swap_step_settings(previous)                     # the process keeps the project's own settings
    return path

def _swap_step_settings(settings: Sequence[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """Set OCCT's process-wide writer ``settings`` ((key, value) pairs; an int value is set as an integer) and return
    the values they replaced, last first, to pass back. If OCCT refuses one, those already set are put back and
    ``GeometryError`` is raised."""
    from OCP.Interface import Interface_Static

    previous: List[Tuple[str, Any]] = []
    for key, value in settings:
        integer = isinstance(value, int)
        old = Interface_Static.IVal_s(key) if integer else Interface_Static.CVal_s(key)
        if not (Interface_Static.SetIVal_s if integer else Interface_Static.SetCVal_s)(key, value):
            _swap_step_settings(previous[::-1])
            raise GeometryError(f"OCCT refused the STEP writer setting {key}={value}")
        previous.append((key, old))
    return previous[::-1]

def _transfer_and_write(writer: Any, topo: Any, path: Path, name: str) -> None:
    """``export_step``'s work once the settings are in place: transfer, fix the header, products and links, write."""
    from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.StepBasic import StepBasic_Product
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence
    from OCP.TCollection import TCollection_HAsciiString

    if writer.Transfer(topo, STEPControl_AsIs) != IFSelect_ReturnStatus.IFSelect_RetDone:
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
