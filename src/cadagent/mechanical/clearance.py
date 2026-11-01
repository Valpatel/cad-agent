"""Range-of-motion clearance (#251): do the moving parts of an assembly hit each other anywhere over their range?

* ``collisions(instances)`` intersects every pair of placed solids whose bounding boxes overlap and reports each pair
  that overlaps by more than ``tolerance_mm3``. A boolean that fails is reported as an error, never as a pass.
* ``sweep(poses, place_fn)`` runs ``collisions`` at every named pose and returns (and optionally writes) a check JSON
  with a top-level ``pass`` and ``physical_fit_verified: false``.
* ``swept_envelope(pieces)`` builds the cutter for a neighbour's clearance: a solid of revolution about +x whose radius
  at each x is the largest of the axial ``pieces``, with its slopes capped (45 degrees by default), made as one
  revolved profile. One revolve leaves no flat ceilings in the cut and avoids the failures of fusing many tools.
  ``envelope_profile`` gives the same profile as numbers, without a CAD kernel.

Limits, stated in every report: the poses are samples, not a continuous sweep, so two parts can pass through each
other between two poses and no pose sees it; sample the range densely where parts come close. Only the solids passed
in are checked: pins, bolts or bought parts left out of the model are not. Parts meant to touch on a face intersect
with near-zero volume and pass the tolerance; parts meant to overlap (a rod in its gland) need ``skip``. CAD
clearance does not prove physical fit: tolerances, deflection under load and wear are not modelled.

cadquery is needed only to build or intersect real solids; it is imported where it is used.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

LIMITS = ("Poses are samples, not a continuous sweep: parts can pass through each other between two poses unseen. "
          "Only the solids passed in are checked. Overlaps up to the tolerance pass (parts touching on a face). "
          "CAD clearance does not prove physical fit: tolerances, deflection and wear are not modelled.")

Pair = Tuple[str, Any]                       # (instance name, part)
Skip = Union[None, Callable[[Pair, Pair], bool], Iterable[Sequence[str]]]


def _bbox(shape) -> Tuple[float, ...]:
    b = shape.BoundingBox()
    return (b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax)


def _boxes_overlap(a, b, pad: float = 1e-6) -> bool:
    return all(a[i] <= b[i + 3] + pad and b[i] <= a[i + 3] + pad for i in range(3))


def _overlap_volume(a, b) -> float:
    """Volume (mm^3) of the boolean intersection of two solids (one OCC boolean; may raise)."""
    return float(a.intersect(b).Volume())


def _skipper(skip: Skip) -> Callable[[Pair, Pair], bool]:
    if skip is None:
        return lambda a, b: False
    if callable(skip):
        return skip
    pairs = {frozenset(p) for p in skip}
    # a pair names two instances, or two parts (every instance of one with every instance of the other)
    return lambda a, b: frozenset((a[0], b[0])) in pairs or frozenset((str(a[1]), str(b[1]))) in pairs


def _check(instances: Mapping[str, Any], tolerance_mm3: float, skip: Skip, only: Optional[Callable[[str], bool]]):
    is_skipped = _skipper(skip)
    items = []
    for name, value in instances.items():
        part, shape = value if isinstance(value, tuple) else (name, value)
        items.append((name, part, shape))
    boxes = {}
    hits: List[Dict[str, Any]] = []
    for name, part, shape in items:
        try:
            boxes[name] = _bbox(shape)
        except Exception as e:                                       # noqa: BLE001 - reported, never a pass
            hits.append({"a": name, "b": None, "part_a": str(part), "part_b": None,
                         "error": f"bounding box failed: {type(e).__name__}: {e}"})
    intersected = 0
    for (ka, pa, sa), (kb, pb, sb) in itertools.combinations(items, 2):
        if ka not in boxes or kb not in boxes:
            continue
        if only is not None and not (only(ka) or only(kb)):
            continue
        if not _boxes_overlap(boxes[ka], boxes[kb]) or is_skipped((ka, pa), (kb, pb)):
            continue
        intersected += 1
        row = {"a": ka, "b": kb, "part_a": str(pa), "part_b": str(pb)}
        try:
            v = _overlap_volume(sa, sb)
        except Exception as e:                                       # noqa: BLE001 - reported, never a pass
            hits.append({**row, "error": f"boolean intersection failed: {type(e).__name__}: {e}"})
            continue
        if not math.isfinite(v) or v < -tolerance_mm3:
            hits.append({**row, "error": f"boolean intersection gave volume {v!r}"})
        elif v > tolerance_mm3:
            hits.append({**row, "volume_mm3": round(v, 3)})
    return hits, intersected


def collisions(instances: Mapping[str, Any], tolerance_mm3: float = 2.0, skip: Skip = None,
               only: Optional[Callable[[str], bool]] = None) -> List[Dict[str, Any]]:
    """Pairs of placed solids that overlap by more than ``tolerance_mm3``.

    ``instances`` maps an instance name to ``(part, shape)`` (``part`` names what the instance is, so several
    instances of one part can share a ``skip`` rule) or to a bare shape (``part`` is then the name). Shapes are
    cadquery shapes, or anything with ``BoundingBox()`` and ``intersect(other).Volume()``, already placed at the pose.

    ``skip``: pairs meant to overlap. Either a callable ``skip((name_a, part_a), (name_b, part_b)) -> bool``, or pairs
    of names, each matching two instance names or two part names, in either order.
    ``only``: a predicate on instance names; a pair is checked only if it holds for at least one of the two.

    Returns one dict per hit: ``{"a", "b", "part_a", "part_b", "volume_mm3"}``, or ``{..., "error": text}`` where the
    boolean (or a bounding box) failed. An error is a failure: an empty list is the only clear result.
    """
    return _check(instances, tolerance_mm3, skip, only)[0]


def _json_default(value):
    if isinstance(value, (np.ndarray, np.generic)):
        return value.tolist()
    return repr(value)


def _jsonable(value):
    """``value`` as it reads back from the check JSON (tuples become lists, numpy values plain numbers)."""
    return json.loads(json.dumps(value, default=_json_default))


def sweep(poses: Mapping[str, Any], place_fn: Callable[[Any], Mapping[str, Any]],
          out_path: Union[str, Path, None] = None, tolerance_mm3: float = 2.0, skip: Skip = None,
          only: Optional[Callable[[str], bool]] = None) -> Dict[str, Any]:
    """Run ``collisions`` at every pose of a range of motion.

    ``poses`` maps a pose name to its parameters (joint angles, cylinder extensions, anything); ``place_fn(params)``
    returns the ``instances`` placed at that pose. A ``place_fn`` that raises (an unreachable pose, say) is recorded as
    that pose's error. ``tolerance_mm3``, ``skip`` and ``only`` go to ``collisions``.

    Returns the check, and writes it as JSON to ``out_path`` if given: ``pass`` is true only when at least one pose was
    checked and no pose has a collision or an error. ``physical_fit_verified`` is always false (see ``LIMITS``).
    """
    report: Dict[str, Any] = {"check": "clearance-sweep", "tolerance_mm3": tolerance_mm3, "poses": {}}
    n_hits = n_errors = 0
    for name, params in poses.items():
        row: Dict[str, Any] = {"params": _jsonable(params)}
        try:
            instances = place_fn(params)
        except Exception as e:                                       # noqa: BLE001 - reported, never a pass
            row["error"] = f"placing the pose failed: {type(e).__name__}: {e}"
            n_errors += 1
            report["poses"][str(name)] = row
            continue
        hits, intersected = _check(instances, tolerance_mm3, skip, only)
        row.update({"instances": len(instances), "pairs_intersected": intersected, "collisions": hits,
                    "pass": not hits})
        n_hits += sum(1 for h in hits if "error" not in h)
        n_errors += sum(1 for h in hits if "error" in h)
        report["poses"][str(name)] = row
    report.update({"poses_checked": len(report["poses"]), "collisions": n_hits, "errors": n_errors,
                   "pass": bool(report["poses"]) and n_hits == 0 and n_errors == 0,
                   "physical_fit_verified": False, "limits": LIMITS})
    if not report["poses"]:
        report["note"] = "no poses given: nothing was checked"
    if out_path is not None:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


def envelope_profile(pieces: Sequence[Sequence[float]], step: float = 0.5, max_slope_deg: float = 45.0,
                     taper_ends: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """The radius profile ``(xs, rs)`` of ``swept_envelope``, without a CAD kernel.

    ``pieces`` are ``(x0, x1, r0, r1)``: a radius linear from ``r0`` at ``x0`` to ``r1`` at ``x1`` (``x1 >= x0``; a
    piece with ``x0 == x1`` is a disc of radius ``max(r0, r1)``). The radius at each x is the largest piece covering
    it, then raised where needed so that it never changes by more than ``tan(max_slope_deg)`` per mm along x: a step
    becomes a cone growing out of the smaller radius, never a flat shoulder facing along the axis. Where no piece
    covers x (a gap between pieces) the radius starts at 0 and the slope limit bridges the gap with cones; a gap too
    long to bridge is a ValueError (the solid would pinch to the axis).
    ``taper_ends``: also close both ends with cones at the slope limit (the profile then runs past the pieces by
    about ``r_end / tan(max_slope_deg)``, to the sample where the radius reaches 0) instead of ending in flat discs.

    Sampled every ``step`` mm, plus every piece's ends: two pieces whose lines cross between samples can be
    under-filled there by a fraction of ``step``. Collinear samples are dropped.
    """
    if not pieces:
        raise ValueError("swept_envelope needs at least one piece")
    if step <= 0:
        raise ValueError("step must be positive")
    if not 0 < max_slope_deg < 90:
        raise ValueError("max_slope_deg must be between 0 and 90 degrees")
    ps = np.asarray(pieces, float)
    if ps.ndim != 2 or ps.shape[1] != 4:
        raise ValueError("each piece is (x0, x1, r0, r1)")
    if np.any(ps[:, 1] < ps[:, 0]) or np.any(ps[:, 2:] < 0):
        raise ValueError("a piece needs x1 >= x0 and radii >= 0")
    slope = math.tan(math.radians(max_slope_deg))
    lo, hi = float(ps[:, 0].min()), float(ps[:, 1].max())
    if taper_ends:
        reach = float(ps[:, 2:].max()) / slope
        lo, hi = lo - reach, hi + reach
    n = max(1, int(math.ceil((hi - lo) / step - 1e-9)))
    xs = np.unique(np.concatenate([np.linspace(lo, hi, n + 1), ps[:, 0], ps[:, 1]]))
    rs = np.zeros_like(xs)
    for x0, x1, r0, r1 in ps:
        m = (xs >= x0 - 1e-9) & (xs <= x1 + 1e-9)
        r = np.full(m.sum(), max(r0, r1)) if x1 - x0 < 1e-9 else r0 + (r1 - r0) * (xs[m] - x0) / (x1 - x0)
        rs[m] = np.maximum(rs[m], r)
    for i in range(1, len(xs)):                                      # falling: no faster than the slope
        rs[i] = max(rs[i], rs[i - 1] - slope * (xs[i] - xs[i - 1]))
    for i in range(len(xs) - 2, -1, -1):                             # rising: the same, seen from the other end
        rs[i] = max(rs[i], rs[i + 1] - slope * (xs[i + 1] - xs[i]))
    if taper_ends:                                                   # one point on the axis at each end, not a run
        nz = np.flatnonzero(rs > 1e-9)
        first, last = max(int(nz[0]) - 1, 0), min(int(nz[-1]) + 1, len(xs) - 1)
        xs, rs = xs[first:last + 1], rs[first:last + 1]
    if np.any(rs[1:-1] <= 1e-9):
        raise ValueError("the pieces leave a gap the slope limit cannot bridge (the radius reaches 0 inside the "
                         "profile): make one envelope per run of pieces")
    keep = [0]
    for i in range(1, len(xs) - 1):
        a = (xs[i] - xs[keep[-1]], rs[i] - rs[keep[-1]])
        b = (xs[i + 1] - xs[i], rs[i + 1] - rs[i])
        if abs(a[0] * b[1] - a[1] * b[0]) > 1e-9 * max(1.0, abs(a[0]) + abs(b[0])):
            keep.append(i)
    keep.append(len(xs) - 1)
    return xs[keep], rs[keep]


def swept_envelope(pieces: Sequence[Sequence[float]], step: float = 0.5, max_slope_deg: float = 45.0,
                   taper_ends: bool = False):
    """A cadquery Solid of revolution about the +x axis through the origin, with the radius profile of
    ``envelope_profile`` (see there for ``pieces``, ``step``, ``max_slope_deg`` and ``taper_ends``).

    Use it as the cutter for a moving part's clearance: describe the part's swept radius along its own axis as pieces
    (a barrel, a rod, an eye body), place one envelope per pose on that axis (``Shape.moved`` or
    ``Shape.transformShape``) and cut them from the neighbour. The profile is one closed polygon revolved once, so the
    cutter has no internal faces and no flat ceilings where the radius steps.
    """
    import cadquery as cq

    xs, rs = envelope_profile(pieces, step, max_slope_deg, taper_ends)
    if float(rs.max()) <= 0:
        raise ValueError("swept_envelope: every radius is zero")
    prof = [(float(xs[0]), 0.0)] + [(float(x), float(r)) for x, r in zip(xs, rs)] + [(float(xs[-1]), 0.0)]
    pts = [prof[0]]
    for p in prof[1:]:                                               # no zero-length edges (a tapered end is on axis)
        if abs(p[0] - pts[-1][0]) > 1e-9 or abs(p[1] - pts[-1][1]) > 1e-9:
            pts.append(p)
    if abs(pts[-1][0] - pts[0][0]) < 1e-9 and abs(pts[-1][1] - pts[0][1]) < 1e-9:
        pts.pop()
    wire = cq.Wire.makePolygon([cq.Vector(x, 0, r) for x, r in pts], close=True)
    face = cq.Face.makeFromWires(wire)
    return cq.Solid.revolve(face, 360, cq.Vector(0, 0, 0), cq.Vector(1, 0, 0))
