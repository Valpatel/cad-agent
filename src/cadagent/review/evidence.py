"""Shared integrity screen for source-bound CAD and PCB report records, and the content hash of a shape.

A shape's content hash (``shape_content_hash``) is exact and cheap, but it is bound to the platform that made it: the
CPU architecture and the OCP (OCCT) build as well as the geometry. ``hash_platform()`` names that platform, and is
recorded next to the hashes (the dossier's geometry record, a reviewer's record). ``geometry_identity`` is an
optional identity that does not depend on the platform: volume, centre of mass and inertia, rounded, with the
tolerance they match to.
"""
import hashlib
import math
import platform
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


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

    **The hash is tied to the platform**, not only to the OCCT version: the CPU architecture (and the OCP build)
    changes the last digits of the numbers the kernel computes, and the text carries them. The same vendor STEP,
    imported with cadquery 2.8.0 and cadquery-ocp 7.9.3.1.1 from PyPI, gave 43 solids whose hashes agreed between two
    x86-64 hosts, while an aarch64 host shared only 4 of the 43 hashes (#144); their volumes agreed to 1e-13. So a
    record that pins these hashes can be checked only on the platform that made it: record ``hash_platform()`` next
    to them, and use ``geometry_identity`` to tell a platform's mismatch from a change of geometry.
    """
    return brep_content_hash(shape_brep_text(shape))


# ------------------------------------------------------------------------------------ the platform behind a hash

_OCP_PACKAGES = ("cadquery-ocp", "cadquery-ocp-novtk", "ocp")
PLATFORM_KEYS = ("machine", "system", "ocp", "ocp_package")


def hash_platform() -> Dict[str, str]:
    """What a ``shape_content_hash`` depends on besides the shape: ``machine`` (``platform.machine()``, the CPU
    architecture, e.g. ``x86_64`` or ``aarch64``), ``system`` (``platform.system()``), ``ocp`` (``OCP.__version__``;
    its first three numbers are the OCCT version it wraps) and ``ocp_package`` (the installed distribution that
    provides OCP, e.g. ``cadquery-ocp 7.9.3.1.1``, or ``unknown`` for a conda or source build). Record it next to
    content hashes; ``hash_platform_note`` says when two differ."""
    try:
        import OCP
        ocp = str(getattr(OCP, "__version__", "") or "unknown")
    except ImportError:
        ocp = "unknown"
    package = "unknown"
    for name in _OCP_PACKAGES:
        try:
            package = f"{name} {version(name)}"
            break
        except PackageNotFoundError:
            continue
    return {"machine": platform.machine() or "unknown", "system": platform.system() or "unknown", "ocp": ocp,
            "ocp_package": package}


def _platform_text(p: Mapping[str, Any]) -> str:
    return f"{p.get('machine', 'unknown')} {p.get('system', 'unknown')}, OCP {p.get('ocp', 'unknown')} " \
           f"({p.get('ocp_package', 'unknown')})"


def hash_platform_note(recorded: Any, current: Any = None) -> Optional[str]:
    """None when content hashes made on the ``recorded`` platform are expected to match ones made on ``current``
    (default: this process, ``hash_platform()``), or when either is not a platform record (an older record without
    one); else a sentence saying the two platforms differ, so differing hashes may not mean differing geometry."""
    if not isinstance(recorded, Mapping) or not recorded:
        return None
    current = hash_platform() if current is None else current
    if not isinstance(current, Mapping) or not current:
        return None
    if all(str(recorded.get(k)) == str(current.get(k)) for k in PLATFORM_KEYS):
        return None
    return (f"the recorded hashes were made on {_platform_text(recorded)} and the current ones on "
            f"{_platform_text(current)}; content hashes differ between platforms, so this need not be a change of "
            "geometry: rebuild on the recorded platform, or compare geometry_identity records")


# ------------------------------------------------------------------------- a platform-stable geometry identity

IDENTITY_SCHEMA = "cadagent.geometry-identity/1"
IDENTITY_TOLERANCE = 1e-6           # relative: of the volume, of the cube root of the volume, of the largest moment
IDENTITY_METHOD = ("OCCT BRepGProp.VolumeProperties (Gauss integration, default order, the same as CadQuery's "
                   "Volume()), density 1; inertia about the centre of mass along the assembly axes, OCCT's signs")


def _rounded(value: float, tol: float) -> float:
    """``value`` rounded one decimal finer than ``tol`` (so the rounding is a tenth of the tolerance at most)."""
    out = round(float(value), 1 - math.floor(math.log10(tol)) if tol > 0 else 12)
    return 0.0 if out == 0 else out


def geometry_identity(shape: Any, rel_tol: float = IDENTITY_TOLERANCE) -> Dict[str, Any]:
    """A platform-stable identity of a solid (or a compound of solids): its volume, centre of mass, inertia tensor
    about that centre and principal moments, each rounded, with the tolerance they match to in the record::

        {"schema": "cadagent.geometry-identity/1", "volume_mm3": 46.881888, "centre_mm": [x, y, z],
         "inertia_mm5": [[Ixx, Ixy, Ixz], [...], [...]], "principal_mm5": [I1, I2, I3],      # I1 <= I2 <= I3
         "tolerance": {"relative": 1e-6, "volume_mm3": ..., "length_mm": ..., "inertia_mm5": ...},
         "method": "..."}

    The tolerances are ``rel_tol`` times the volume, times the cube root of the volume (a length, for the centre)
    and times the largest principal moment (for every inertia term). Values are rounded a tenth of their tolerance
    finer. Compare two identities with ``identity_mismatches`` (within the looser tolerance), not by equality:
    rounding puts two values a hair apart on either side of a step now and then.

    Where it helps: a ``shape_content_hash`` made on another platform (or by another OCP build) does not match,
    and the question is whether the geometry changed. On the vendor STEP in ``shape_content_hash``'s note, x86-64
    and aarch64 volumes agreed to 1e-13, far inside the default 1e-6. Like the hash, it moves with placement (the
    centre and the inertia axes) and with any change of geometry larger than the tolerance.

    Limits: it is not a hash. Two different solids can share it (a mirror image across a plane of symmetry of the
    mass, or any two solids with the same volume, centre and inertia), and a change smaller than the tolerance is not
    seen, so a match says "not told apart by mass properties", never "the same shape": it can explain a platform's
    hash mismatch, but never sign off geometry. The default integration can be off by more than the tolerance on
    some freeform solids (docs/volume-precision.md); the same geometry gives the same error on any platform, which is
    all an identity needs, but two constructions with different faces may not match (a miss, the safe side). Needs
    OCP and a solid with a positive volume (ValueError otherwise).
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    if not (isinstance(rel_tol, (int, float)) and 0 < rel_tol < 1):
        raise ValueError(f"rel_tol must be a number between 0 and 1, got {rel_tol!r}")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(getattr(shape, "wrapped", shape), props)
    volume = props.Mass()
    if not (math.isfinite(volume) and volume > 0):
        raise ValueError(f"geometry_identity needs a solid with a positive volume, got {volume!r} mm3")
    c = props.CentreOfMass()
    m = props.MatrixOfInertia()
    tensor = [[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]
    principal = sorted(props.PrincipalProperties().Moments())
    if not all(math.isfinite(v) for v in (c.X(), c.Y(), c.Z(), *principal, *sum(tensor, []))):
        raise ValueError("geometry_identity: the kernel returned a non-finite centre or inertia")
    tol = {"relative": float(rel_tol), "volume_mm3": rel_tol * volume, "length_mm": rel_tol * volume ** (1 / 3),
           "inertia_mm5": rel_tol * max(abs(v) for v in principal)}
    ti = tol["inertia_mm5"]
    return {"schema": IDENTITY_SCHEMA,
            "volume_mm3": _rounded(volume, tol["volume_mm3"]),
            "centre_mm": [_rounded(v, tol["length_mm"]) for v in (c.X(), c.Y(), c.Z())],
            "inertia_mm5": [[_rounded(v, ti) for v in row] for row in tensor],
            "principal_mm5": [_rounded(v, ti) for v in principal],
            "tolerance": {k: (v if k == "relative" else float(f"{v:.3g}")) for k, v in tol.items()},
            "method": IDENTITY_METHOD}


def identity_mismatches(a: Mapping[str, Any], b: Mapping[str, Any]) -> List[str]:
    """What tells two ``geometry_identity`` records apart: an empty list when every value agrees within the looser
    of the two records' tolerances, else one line per value that does not (or why the two cannot be compared)."""
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return ["not a geometry identity"]
    for name, rec in (("first", a), ("second", b)):
        if rec.get("schema") != IDENTITY_SCHEMA:
            return [f"the {name} record is not a {IDENTITY_SCHEMA} identity (schema {rec.get('schema')!r})"]
    out: List[str] = []
    try:
        if any(len(r[k]) != 3 for r in (a, b) for k in ("centre_mm", "principal_mm5", "inertia_mm5")) or \
                any(len(row) != 3 for r in (a, b) for row in r["inertia_mm5"]):
            return ["a centre, the inertia or the principal moments are not three numbers (or 3 x 3)"]
        ta, tb = a["tolerance"], b["tolerance"]
        tol = {k: max(float(ta[k]), float(tb[k])) for k in ("volume_mm3", "length_mm", "inertia_mm5")}
        pairs = [("volume_mm3", a["volume_mm3"], b["volume_mm3"], tol["volume_mm3"])]
        pairs += [(f"centre_mm[{i}]", a["centre_mm"][i], b["centre_mm"][i], tol["length_mm"]) for i in range(3)]
        pairs += [(f"inertia_mm5[{i}][{j}]", a["inertia_mm5"][i][j], b["inertia_mm5"][i][j], tol["inertia_mm5"])
                  for i in range(3) for j in range(i, 3)]
        pairs += [(f"principal_mm5[{i}]", a["principal_mm5"][i], b["principal_mm5"][i], tol["inertia_mm5"])
                  for i in range(3)]
        for what, x, y, t in pairs:
            if not abs(float(x) - float(y)) <= t:
                out.append(f"{what}: {x} and {y} differ by {abs(float(x) - float(y)):.3g}, more than {t:.3g}")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return [f"malformed geometry identity: {type(exc).__name__}: {exc}"]
    return out
