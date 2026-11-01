"""Build plates: every printed part at its quantity, packed onto as many printer beds as it takes, in one project 3MF
that Bambu Studio opens with the plates laid out. ``cad-agent export-3mf`` writes it next to the per-part 3MFs.

    from cadagent.manufacturing.plates import Copy, footprint, pack, check_plates
    lid = footprint(mesh.vertices)
    plates = pack([Copy("lid", 1, lid, "PLA"), Copy("lid", 2, lid, "PLA")], bed_xy=(256, 256), gap=5, margin=5)
    assert not check_plates(plates, (256, 256), gap=5, margin=5)

**Packing** (``pack``) places each copy's footprint: the rectangle around its outline as it prints (the convex hull of
the mesh seen from above). Parts keep their print orientation. With ``rotate`` they may turn about z, by a quarter
turn, or for a part that fits neither way (a long leg on a square bed) by the whole degree that gives the smallest
rectangle that fits. The method is MaxRects (J. Jylänki, *A Thousand Ways to Pack the Bin*, 2010, the method
``rectpack`` also implements): copies go largest first onto the first plate of their group with room, and a plate is
added when none has room. Four sort orders times four fit rules are tried; the layout with the fewest plates, then
the least on its last plate, wins. Parts with different filaments never share a plate. Sizes are whole
micrometres and every tie is broken by a fixed key, so the same parts give the same layout on every machine. Each
plate's layout is then centred on the bed, unless that would move a part onto a keep-out area. ``check_plates``
re-checks the result independently: every copy placed once, inside the bed less the margin, clear of keep-out areas
and at least ``gap`` from every other part.

**The file** (``write_plates_3mf``) is a 3MF core-spec model (one mesh object per part, one build item per copy, at
its place on Bambu Studio's grid of plates) plus Bambu Studio's ``Metadata/model_settings.config``: one ``<plate>``
per plate with its id, name and ``model_instance`` list, and each object's name and filament (``extruder``). Bambu
Studio lays plate *i* (0-based) of *n* at ``(col * 1.2 W, -row * 1.2 D)``, with ``ceil(sqrt(n))`` columns, ``W x D``
the printable area in whole mm, and at most 36 plates; on loading it puts each copy on the plate whose area holds it.
It keeps the plates only when the file carries ``Metadata/project_settings.config`` (a complete printer, process and
filament configuration); without one it loads the geometry onto a single plate. Those settings come from Bambu
Studio itself (``cadagent.manufacturing.slicer.project_settings``) when it is installed. Format facts were read from
Bambu Studio's source (``src/libslic3r/Format/bbs_3mf.cpp``, ``src/slic3r/GUI/PartPlate.cpp``, ``Plater.cpp`` at
v02.08.04.57; AGPL-3.0, read for the format only, no code taken) and checked against files it saved.

The file is written like the per-part 3MFs: sorted entries, a fixed date, mode and host, so the same parts and
settings give the same bytes (``SOURCE_DATE_EPOCH`` and the clock do not change them). It is read back
(``read_plates_3mf``) and deleted unless every copy is where the layout put it, on the plate Bambu Studio would put it
on, with the source mesh's triangles and volume.

Limits: footprints are rectangles around the outline, so an L-shaped part reserves its whole rectangle; parts are
never nested inside one another. A layout says nothing about whether a plate prints well (adhesion, warping, the
time one failure costs): that is the slicer's and the printer's evidence, not this module's.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

from cadagent._deps import require
from cadagent.manufacturing.mesh3mf import CONTENT_TYPES, CORE_NS, RELS, VOLUME_RTOL, _entry, mesh_volume

np = require("numpy", "build plates")

MARKER = "cad-agent.plates/1"
APPLICATION = "cad-agent"
BAMBU_NS = "http://schemas.bambulab.com/package/2021"
DESCRIPTION = ("Build plates laid out by cad-agent (https://github.com/Valpatel/cad-agent). The Application entry "
               "names the Bambu Studio version that wrote the project settings: Bambu Studio reads a file's plates "
               "and settings only when that entry names it.")
PLATE_GAP = 0.2                    # Bambu Studio: plates sit 1/5 of a plate apart (LOGICAL_PART_PLATE_GAP)
MAX_PLATES = 36                    # Bambu Studio: MAX_PLATE_COUNT
DEFAULT_GAP_MM = 5.0
DEFAULT_MARGIN_MM = 5.0
QUARTER_TURN_MIN_MM = 0.5         # a footprint this close to square is never turned a quarter
POSITION_TOL_MM = 2e-3             # read-back: vertices are written to 1e-4 mm, transforms to 1e-4 mm and 1e-9
MODEL_SETTINGS = "Metadata/model_settings.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"
_UM = 1000                         # packing works in whole micrometres


class PlatesError(ValueError):
    """The parts cannot be laid out as asked (a part larger than the bed, more plates than Bambu Studio holds), or a
    written plates file did not read back as laid out."""


# ---------------------------------------------------------------------------------------------------------------
# Footprints

def _hull(points: np.ndarray) -> List[Tuple[float, float]]:
    """Convex hull (Andrew's monotone chain), counter-clockwise, from the lowest-then-leftmost point. Points are
    rounded to 1e-4 mm first, so the hull does not depend on float noise or point order."""
    pts = sorted({(round(float(x), 4), round(float(y), 4)) for x, y in points})
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def rotation(angle_deg: int) -> Tuple[float, float]:
    """``(cos, sin)`` of a whole-degree turn about z: exact at quarter turns, rounded to 1e-12 elsewhere so every
    machine writes the same transform."""
    a = int(angle_deg) % 360
    exact = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
    if a in exact:
        return exact[a]
    r = math.radians(a)
    return round(math.cos(r), 12), round(math.sin(r), 12)


def _turn(points: Iterable[Tuple[float, float]], angle_deg: int) -> List[Tuple[float, float]]:
    c, s = rotation(angle_deg)
    return [(c * x - s * y, s * x + c * y) for x, y in points]


def _box(points: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _um(mm: float) -> int:
    """A size in whole micrometres, rounded up (a footprint is never made smaller than it is)."""
    return int(math.ceil(round(mm * _UM, 6)))


@dataclass(frozen=True)
class Footprint:
    """A part's outline seen from above, as it prints: the convex hull of its vertices (mm, in the mesh's own x/y),
    and its height."""
    hull: Tuple[Tuple[float, float], ...]
    height: float

    def size(self, angle_deg: int = 0) -> Tuple[float, float]:
        """Width (x) and depth (y) of the rectangle around the outline turned by ``angle_deg`` about z."""
        x0, y0, x1, y1 = _box(_turn(self.hull, angle_deg))
        return x1 - x0, y1 - y0

    def area(self) -> float:
        """Area of the outline (the hull), mm²."""
        h = self.hull
        return abs(sum(h[i][0] * h[(i + 1) % len(h)][1] - h[(i + 1) % len(h)][0] * h[i][1]
                       for i in range(len(h)))) / 2 if len(h) >= 3 else 0.0


def footprint(vertices) -> Footprint:
    """The ``Footprint`` of a mesh in print orientation (any (n, 3) vertex array)."""
    v = np.asarray(vertices, dtype=float).reshape(-1, 3)
    if len(v) < 3:
        raise PlatesError("a footprint needs a mesh with at least three vertices")
    return Footprint(tuple(_hull(v[:, :2])), float(v[:, 2].max() - v[:, 2].min()))


# ---------------------------------------------------------------------------------------------------------------
# Packing

@dataclass(frozen=True)
class Copy:
    """One printed copy of a part. ``group`` is what may not share a plate with another group (the filament)."""
    part: str
    copy: int
    footprint: Footprint
    group: str = ""


@dataclass(frozen=True)
class Placement:
    """Where one copy prints: its footprint rectangle's lower-left corner on the bed (mm), its size there, and the
    turn about z (degrees) that gives that rectangle."""
    part: str
    copy: int
    x: float
    y: float
    width: float
    depth: float
    angle: int = 0


@dataclass
class Plate:
    index: int                      # 1-based, as Bambu Studio numbers plates
    group: str
    placements: List[Placement] = field(default_factory=list)


class Layout(list):
    """The plates ``pack`` made (a list of ``Plate``), and ``method``: the sort order and fit rule that gave them."""

    def __init__(self, plates: Iterable[Plate] = (), method: Optional[Dict[str, str]] = None):
        super().__init__(plates)
        self.method = dict(method or {})


Rect = Tuple[int, int, int, int]    # x, y, w, h in micrometres


def _overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _contains(a: Rect, b: Rect) -> bool:
    return a[0] <= b[0] and a[1] <= b[1] and b[0] + b[2] <= a[0] + a[2] and b[1] + b[3] <= a[1] + a[3]


class _Bin:
    """One plate's free space as maximal free rectangles (MaxRects)."""

    def __init__(self, w: int, h: int):
        self.free: List[Rect] = [(0, 0, w, h)] if w > 0 and h > 0 else []

    def find(self, sizes: Sequence[Tuple[int, int]], rule: str = "short-side"
             ) -> Optional[Tuple[Tuple[int, ...], Rect]]:
        """The best free rectangle and size for a copy, by ``rule`` (``FIT_RULES``), then the lowest and leftmost
        spot, then the earlier size."""
        best = None
        for k, (w, h) in enumerate(sizes):
            for fx, fy, fw, fh in self.free:
                if w <= fw and h <= fh:
                    lw, lh = fw - w, fh - h
                    key = {"short-side": (min(lw, lh), max(lw, lh), fy, fx),
                           "long-side": (max(lw, lh), min(lw, lh), fy, fx),
                           "area": (fw * fh - w * h, min(lw, lh), fy, fx),
                           "bottom-left": (fy + h, fx, 0, 0)}[rule] + (k,)
                    if best is None or key < best[0]:
                        best = (key, (fx, fy, w, h))
        return best

    def place(self, r: Rect) -> None:
        free: List[Rect] = []
        x, y, w, h = r
        for f in self.free:
            if not _overlaps(f, r):
                free.append(f)
                continue
            fx, fy, fw, fh = f
            if x > fx:
                free.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                free.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                free.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                free.append((fx, y + h, fw, fy + fh - y - h))
        unique = sorted(set(f for f in free if f[2] > 0 and f[3] > 0))
        self.free = [f for f in unique if not any(g != f and _contains(g, f) for g in unique)]


def _clip(r: Tuple[int, int, int, int], w: int, h: int) -> Optional[Rect]:
    """A rectangle given by its corners, clipped to ``[0, w] x [0, h]``, as (x, y, w, h); None when nothing is left."""
    x0, y0, x1, y1 = max(r[0], 0), max(r[1], 0), min(r[2], w), min(r[3], h)
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def orientations(fp: Footprint, usable: Tuple[float, float], rotate: bool = True) -> List[Tuple[int, float, float]]:
    """The turns a copy may be packed at, as ``(angle, width, depth)``: as modelled, and a quarter turn when
    ``rotate``; for a footprint that fits the usable area neither way, the whole-degree turn whose rectangle fits with
    the smallest area. Empty when nothing fits."""
    W, D = usable
    fits = lambda w, d: _um(w) <= _um(W) and _um(d) <= _um(D)
    out = [(0, *fp.size(0))]
    if rotate:
        w, d = fp.size(0)
        if abs(w - d) > QUARTER_TURN_MIN_MM:     # a round or square part gains nothing from a quarter turn
            out.append((90, d, w))
    out = [o for o in out if fits(o[1], o[2])]
    if out or not rotate:
        return out
    best = None
    for a in range(1, 180):
        if a == 90:
            continue
        w, d = fp.size(a)
        if fits(w, d) and (best is None or (_um(w) * _um(d), a) < (_um(best[1]) * _um(best[2]), best[0])):
            best = (a, w, d)
    return [best] if best else []


def _turned_box(fp: Footprint, angle: int) -> Tuple[float, float, float, float]:
    return _box(_turn(fp.hull, angle))


def pack(copies: Sequence[Copy], bed_xy: Sequence[float], gap: float = DEFAULT_GAP_MM,
         margin: float = DEFAULT_MARGIN_MM, rotate: bool = True,
         keep_out: Sequence[Sequence[float]] = (), max_plates: int = MAX_PLATES) -> Layout:
    """Lay ``copies`` out over as few plates of a ``bed_xy`` bed as this method finds (see the module docstring).

    ``gap`` is the least distance between two footprints, ``margin`` the least distance from the bed's edge, and
    ``keep_out`` lists bed areas no footprint may cover, ``[x0, y0, x1, y1]`` in mm. Groups keep the order in which
    ``copies`` first names them, and each starts on a new plate. Raises ``PlatesError`` for a copy that fits no empty
    plate, or when more than ``max_plates`` plates would be needed."""
    if gap < 0 or margin < 0:
        raise PlatesError("gap and margin must be zero or more")
    Wb, Db = _um(float(bed_xy[0])), _um(float(bed_xy[1]))
    g, m = _um(gap), _um(margin)
    usable = ((Wb - 2 * m) / _UM, (Db - 2 * m) / _UM)
    if usable[0] <= 0 or usable[1] <= 0:
        raise PlatesError(f"a margin of {margin} mm leaves no room on a {bed_xy[0]} x {bed_xy[1]} mm bed")
    bin_w, bin_h = Wb - 2 * m + g, Db - 2 * m + g
    blocked = []
    for x0, y0, x1, y1 in keep_out:     # grown to whole micrometres, never shrunk
        lo = [int(math.floor(round(float(v) * _UM, 6))) for v in (x0, y0)]
        r = _clip((lo[0] - m, lo[1] - m, _um(float(x1)) - m, _um(float(y1)) - m), bin_w, bin_h)
        if r:
            blocked.append(r)
    groups: List[str] = []
    for c in copies:
        if c.group not in groups:
            groups.append(c.group)
    jobs = []
    for c in copies:
        turns = orientations(c.footprint, usable, rotate)
        if not turns:
            w, d = c.footprint.size(0)
            how = "at any turn about z" if rotate else "as modelled (rotate is off)"
            raise PlatesError(f"{c.part}: its {w:.1f} x {d:.1f} mm footprint does not fit the bed less its "
                              f"{margin:g} mm margins ({usable[0]:g} x {usable[1]:g} mm) {how}")
        if c.footprint.height > 0 and len(bed_xy) > 2 and _um(c.footprint.height) > _um(float(bed_xy[2])):
            raise PlatesError(f"{c.part}: {c.footprint.height:.1f} mm tall, the printer builds {bed_xy[2]:g} mm")
        sizes = [(_um(w) + g, _um(d) + g) for _, w, d in turns]
        empty = _Bin(bin_w, bin_h)
        for r in blocked:
            empty.place(r)
        if empty.find(sizes) is None:
            raise PlatesError(f"{c.part}: does not fit an empty plate around its keep-out areas")
        jobs.append((c, turns, sizes))
    best = None
    for i, (order, rule) in enumerate((o, r) for o in SORT_ORDERS for r in FIT_RULES):
        plates = _pack_once(jobs, groups, order, rule, (bin_w, bin_h), blocked, m, max_plates)
        if plates is None:
            continue
        last = sum(_um(q.width) * _um(q.depth) for q in plates[-1].placements) if plates else 0
        score = (len(plates), last, i)
        if best is None or score < best[0]:
            best = (score, plates, (order, rule))
    if best is None:
        raise PlatesError(f"the parts need more than {max_plates} plates (Bambu Studio holds at most "
                          f"{MAX_PLATES}); print them in more than one project")
    return Layout([_centred(p, (Wb, Db), keep_out) for p in best[1]], {"sort": best[2][0], "fit": best[2][1]})


SORT_ORDERS = ("area", "long-side", "short-side", "perimeter")      # largest first, by
FIT_RULES = ("short-side", "long-side", "area", "bottom-left")      # MaxRects' choice of free rectangle (Jylänki)


def _pack_once(jobs, groups: List[str], order: str, rule: str, bin_wh: Tuple[int, int], blocked: List[Rect],
               m: int, max_plates: int) -> Optional[List[Plate]]:
    """One MaxRects pass: copies sorted by group, then largest first by ``order``; each onto the first plate of its
    group with room by ``rule``. None when it needs more than ``max_plates`` plates."""
    def size_key(job):
        c, _, sizes = job
        w, h = sizes[0]
        area, long_, short, perimeter = -(w * h), -max(w, h), -min(w, h), -(w + h)
        lead = {"area": (area, long_), "long-side": (long_, area), "short-side": (short, area),
                "perimeter": (perimeter, area)}[order]
        return (groups.index(c.group),) + lead + (c.part, c.copy)

    plates: List[Plate] = []
    bins: List[_Bin] = []
    for c, turns, sizes in sorted(jobs, key=size_key):
        found = None
        for p, b in zip(plates, bins):
            if p.group == c.group:
                hit = b.find(sizes, rule)
                if hit:
                    found = (p, b, hit)
                    break
        if found is None:
            if len(plates) >= max_plates:
                return None
            b = _Bin(*bin_wh)
            for r in blocked:
                b.place(r)
            p = Plate(len(plates) + 1, c.group)
            plates.append(p)
            bins.append(b)
            found = (p, b, b.find(sizes, rule))
        p, b, (key, (x, y, w, h)) = found
        b.place((x, y, w, h))
        angle, wf, df = turns[key[-1]]
        p.placements.append(Placement(c.part, c.copy, (m + x) / _UM, (m + y) / _UM, wf, df, angle))
    return plates


def _centred(plate: Plate, bed_um: Tuple[int, int], keep_out: Sequence[Sequence[float]]) -> Plate:
    """The plate with its layout moved to the middle of the bed, in whole micrometres, unless that puts a footprint
    on a keep-out area."""
    if not plate.placements:
        return plate
    lo_x = min(_um(q.x) for q in plate.placements)
    lo_y = min(_um(q.y) for q in plate.placements)
    hi_x = max(_um(q.x) + _um(q.width) for q in plate.placements)
    hi_y = max(_um(q.y) + _um(q.depth) for q in plate.placements)
    dx = (bed_um[0] - (hi_x - lo_x)) // 2 - lo_x
    dy = (bed_um[1] - (hi_y - lo_y)) // 2 - lo_y
    moved = [Placement(q.part, q.copy, (_um(q.x) + dx) / _UM, (_um(q.y) + dy) / _UM, q.width, q.depth, q.angle)
             for q in plate.placements]
    if any(_hits_keep_out(q, keep_out) for q in moved):
        return plate
    return Plate(plate.index, plate.group, moved)


def _hits_keep_out(q: Placement, keep_out: Sequence[Sequence[float]], tol: float = 0.0) -> bool:
    for x0, y0, x1, y1 in keep_out:
        if q.x < x1 - tol and x0 < q.x + q.width - tol and q.y < y1 - tol and y0 < q.y + q.depth - tol:
            return True
    return False


def check_plates(plates: Sequence[Plate], bed_xy: Sequence[float], gap: float, margin: float,
                 keep_out: Sequence[Sequence[float]] = (), quantities: Optional[Dict[str, int]] = None,
                 groups: Optional[Dict[str, str]] = None, tol: float = 1e-6) -> List[str]:
    """Every way the layout breaks the rules, independently of how it was made (empty when it keeps them all):
    each footprint inside the bed less ``margin``, off ``keep_out``, at least ``gap`` from every other footprint on
    its plate; with ``quantities``, every part placed exactly that many times and nothing else; with ``groups``
    (part -> group), every part on a plate of its group. ``tol`` (mm) absorbs rounding in a read-back layout."""
    problems: List[str] = []
    W, D = float(bed_xy[0]), float(bed_xy[1])
    seen: Dict[str, int] = {}
    for p in plates:
        for q in p.placements:
            seen[q.part] = seen.get(q.part, 0) + 1
            name = f"plate {p.index}: {q.part} #{q.copy}"
            if q.x < margin - tol or q.y < margin - tol or q.x + q.width > W - margin + tol \
                    or q.y + q.depth > D - margin + tol:
                problems.append(f"{name} is outside the bed less its {margin:g} mm margins "
                                f"({q.x:.3f}..{q.x + q.width:.3f} x {q.y:.3f}..{q.y + q.depth:.3f} mm)")
            if _hits_keep_out(q, keep_out, tol):
                problems.append(f"{name} covers a keep-out area")
            if groups is not None and groups.get(q.part, p.group) != p.group:
                problems.append(f"{name} is on a {p.group!r} plate, its filament is {groups.get(q.part)!r}")
        qs = p.placements
        for i in range(len(qs)):
            for j in range(i + 1, len(qs)):
                a, b = qs[i], qs[j]
                apart = max(b.x - (a.x + a.width), a.x - (b.x + b.width), b.y - (a.y + a.depth), a.y - (b.y + b.depth))
                if apart < gap - tol:
                    problems.append(f"plate {p.index}: {a.part} #{a.copy} and {b.part} #{b.copy} are {apart:.3f} mm "
                                    f"apart, less than the {gap:g} mm gap" if apart >= 0 else
                                    f"plate {p.index}: {a.part} #{a.copy} and {b.part} #{b.copy} overlap")
    if quantities is not None:
        for part in sorted(set(quantities) | set(seen)):
            if seen.get(part, 0) != quantities.get(part, 0):
                problems.append(f"{part}: {seen.get(part, 0)} on the plates, {quantities.get(part, 0)} wanted")
    return problems


# ---------------------------------------------------------------------------------------------------------------
# Bambu Studio's grid of plates

def columns(count: int) -> int:
    """Bambu Studio's plate columns for ``count`` plates: ceil(sqrt(count)) (``compute_colum_count``)."""
    c = math.isqrt(max(count, 1))
    return c if c * c >= count else c + 1


def plate_origin(index: int, count: int, plate_mm: Tuple[int, int]) -> Tuple[float, float]:
    """Where Bambu Studio puts plate ``index`` (1-based) of ``count``: its printable area's origin in the project's
    coordinates (``PartPlateList::compute_shape_position``)."""
    row, col = divmod(index - 1, columns(count))
    return col * plate_mm[0] * (1 + PLATE_GAP), -row * plate_mm[1] * (1 + PLATE_GAP)


def plate_at(x: float, y: float, count: int, plate_mm: Tuple[int, int],
             area: Tuple[float, float, float, float]) -> Optional[int]:
    """The plate (1-based) whose printable area holds the point, as Bambu Studio assigns copies to plates; None
    when it lies on none. ``area`` is the printable area on plate 1, ``(x0, y0, x1, y1)``."""
    for i in range(1, count + 1):
        ox, oy = plate_origin(i, count, plate_mm)
        if area[0] + ox <= x <= area[2] + ox and area[1] + oy <= y <= area[3] + oy:
            return i
    return None


def printable_area(settings: Optional[Dict[str, Any]], bed_xy: Sequence[float]
                   ) -> Tuple[Tuple[float, float, float, float], Tuple[int, int]]:
    """The printable area on plate 1 ``(x0, y0, x1, y1)`` and the plate size Bambu Studio steps its grid by (whole
    mm, as its ``PartPlateList::reset_size`` takes them): from the project settings' ``printable_area`` when given,
    else ``bed_xy`` from the origin."""
    pts = None
    if settings and isinstance(settings.get("printable_area"), list):
        try:
            pts = [tuple(float(c) for c in str(p).split("x")) for p in settings["printable_area"]]
        except ValueError:
            pts = None
    if not pts:
        pts = [(0.0, 0.0), (float(bed_xy[0]), float(bed_xy[1]))]
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
    return (x0, y0, x1, y1), (int(x1 - x0), int(y1 - y0))


# ---------------------------------------------------------------------------------------------------------------
# The project 3MF

def _num(v: float, digits: int) -> str:
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _normalised(vertices: np.ndarray) -> np.ndarray:
    """The mesh moved so its footprint's centre is on the z axis and its lowest point on z=0, rounded to the 1e-4 mm
    the file stores, so the layout is computed from exactly the vertices written."""
    v = np.asarray(vertices, dtype=float)
    lo, hi = v.min(axis=0), v.max(axis=0)
    return np.round(v - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]), 4) + 0.0


def _transform(angle: int, tx: float, ty: float) -> str:
    """A 3MF build-item transform (row vectors: ``p' = p M``) for a turn about z and a move in x and y."""
    c, s = rotation(angle)
    return " ".join([_num(c, 12), _num(s, 12), "0", _num(-s, 12), _num(c, 12), "0", "0", "0", "1",
                     _num(tx, 4), _num(ty, 4), "0"])


def _placed_offset(fp_box: Tuple[float, float, float, float], q: Placement, origin: Tuple[float, float]
                   ) -> Tuple[float, float]:
    """The move that puts a turned footprint's lower-left corner at the placement on its plate."""
    return round(origin[0] + q.x - fp_box[0], 4), round(origin[1] + q.y - fp_box[1], 4)


def application(settings: Optional[Dict[str, Any]]) -> str:
    """The 3MF's ``Application`` entry: ``BambuStudio-<version>`` when the file carries project settings that Bambu
    Studio ``<version>`` wrote, else ``cad-agent``. Bambu Studio loads a file's settings, and so its plates, only when
    this entry starts with ``BambuStudio-`` (``bbs_3mf.cpp``: without a generator version it sets
    ``dont_load_config``); its command line also re-arranges every other file onto plates of its own. The
    ``Description`` entry says that cad-agent laid the plates out."""
    import re
    version = str((settings or {}).get("version") or "")
    return f"BambuStudio-{version}" if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", version) else APPLICATION


def plates_3mf_members(meshes: Dict[str, Tuple[Any, Any]], plates: Sequence[Plate], *, bed_xy: Sequence[float],
                       extruders: Dict[str, int], plate_names: Optional[Dict[int, str]] = None,
                       bed_types: Optional[Dict[int, str]] = None, project_settings: Optional[bytes] = None,
                       title: str = "") -> Dict[str, bytes]:
    """The files of the project 3MF, by archive path. ``meshes`` maps each part to ``(vertices, faces)`` in print
    orientation; ``extruders`` maps each part to its 1-based filament slot."""
    settings = json.loads(project_settings) if project_settings else None
    area, plate_mm = printable_area(settings, bed_xy)
    order = []
    for p in plates:
        for q in p.placements:
            if q.part not in order:
                order.append(q.part)
    missing = [n for n in order if n not in meshes]
    if missing:
        raise PlatesError(f"no mesh for {missing}")
    obj_id = {n: i + 1 for i, n in enumerate(order)}
    resources, items, configs, plate_xml = [], [], [], []
    norm = {n: _normalised(meshes[n][0]) for n in order}
    hulls = {n: footprint(norm[n]) for n in order}
    for n in order:
        v, f = norm[n], np.asarray(meshes[n][1], dtype=np.int64)
        verts = "".join(f'<vertex x="{_num(a, 4)}" y="{_num(b, 4)}" z="{_num(c, 4)}"/>' for a, b, c in v)
        tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
        resources.append(f'<object id="{obj_id[n]}" name={quoteattr(n)} type="model"><mesh><vertices>{verts}'
                         f"</vertices><triangles>{tris}</triangles></mesh></object>")
        configs.append(f'  <object id="{obj_id[n]}">\n    <metadata key="name" value={quoteattr(n)}/>\n'
                       f'    <metadata key="extruder" value="{int(extruders.get(n, 1))}"/>\n  </object>\n')
    instance = {n: 0 for n in order}
    identify = 0
    for p in plates:
        ox, oy = plate_origin(p.index, len(plates), plate_mm)
        origin = (ox + area[0], oy + area[1])         # the bed's origin on this plate
        inst_xml = []
        for q in p.placements:
            tx, ty = _placed_offset(_turned_box(hulls[q.part], q.angle), q, origin)
            items.append(f'<item objectid="{obj_id[q.part]}" transform="{_transform(q.angle, tx, ty)}"/>')
            identify += 1
            inst_xml.append(f'    <model_instance>\n      <metadata key="object_id" value="{obj_id[q.part]}"/>\n'
                            f'      <metadata key="instance_id" value="{instance[q.part]}"/>\n'
                            f'      <metadata key="identify_id" value="{identify}"/>\n    </model_instance>\n')
            instance[q.part] += 1
        name = (plate_names or {}).get(p.index, "")
        plate_xml.append(f'  <plate>\n    <metadata key="plater_id" value="{p.index}"/>\n'
                         f'    <metadata key="plater_name" value={quoteattr(name)}/>\n'
                         f'    <metadata key="locked" value="false"/>\n'
                         + (f'    <metadata key="bed_type" value={quoteattr(bed_types[p.index])}/>\n'
                            if (bed_types or {}).get(p.index) else "")
                         + "".join(inst_xml) + "  </plate>\n")
    app, bambu = application(settings), ""
    if app != APPLICATION:      # the project format Bambu Studio reads its plates and settings from
        bambu = (f' xmlns:BambuStudio="{BAMBU_NS}"', '<metadata name="BambuStudio:3mfVersion">1</metadata>'
                 f'<metadata name="Description">{escape(DESCRIPTION)}</metadata>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}"{bambu[0] if bambu else ""}>'
             f'<metadata name="Application">{escape(app)}</metadata>' + (bambu[1] if bambu else "")
             + (f'<metadata name="Title">{escape(title)}</metadata>' if title else "")
             + "<resources>" + "".join(resources) + "</resources><build>" + "".join(items) + "</build></model>")
    config = '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(configs) + "".join(plate_xml) + "</config>\n"
    members = {"[Content_Types].xml": CONTENT_TYPES.encode(), "_rels/.rels": RELS.encode(),
               "3D/3dmodel.model": model.encode(), MODEL_SETTINGS: config.encode()}
    if project_settings:
        members[PROJECT_SETTINGS] = project_settings
    return members


def write_plates_3mf(path: Path, meshes: Dict[str, Tuple[Any, Any]], plates: Sequence[Plate], *,
                     bed_xy: Sequence[float], gap: float, margin: float, keep_out: Sequence[Sequence[float]] = (),
                     extruders: Optional[Dict[str, int]] = None, plate_names: Optional[Dict[int, str]] = None,
                     bed_types: Optional[Dict[int, str]] = None, project_settings: Optional[bytes] = None,
                     title: str = "") -> Dict[str, Any]:
    """Write the project 3MF (sorted entries, fixed dates) and read it back; ``PlatesError`` (and no file) when the
    read-back does not match the layout or the source meshes. Returns the read-back (``read_plates_3mf``)."""
    path = Path(path)
    members = plates_3mf_members(meshes, plates, bed_xy=bed_xy, extruders=extruders or {}, plate_names=plate_names,
                                 bed_types=bed_types, project_settings=project_settings, title=title)
    tmp = path.with_name(path.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(members):
            z.writestr(_entry(name), members[name])
    try:
        back = read_plates_3mf(tmp, bed_xy)
        problems = _compare(back, plates, meshes, bed_xy, gap, margin, keep_out)
    except (KeyError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        problems = [f"unreadable: {exc}"]
    if problems:
        tmp.unlink(missing_ok=True)
        raise PlatesError(f"{path.name}: the read-back does not match the layout: " + "; ".join(problems[:5]))
    tmp.replace(path)
    back["file"] = path.name
    return back


def read_plates_3mf(path: Path, bed_xy: Sequence[float] = (256, 256)) -> Dict[str, Any]:
    """Read a project 3MF's plates back the way Bambu Studio places them: ``plates`` (each with ``index``, ``name``,
    ``listed`` (object, instance) pairs from ``model_settings.config`` and ``placements`` worked out from the build
    items' world positions, assigned to a plate by where they lie), ``objects`` (id -> name, extruder, triangles,
    volume), ``outside`` (copies on no plate) and ``project_settings`` (parsed, or None). ``bed_xy`` sizes the grid
    when the file has no project settings."""
    ns = {"m": CORE_NS}
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        config = ET.fromstring(z.read(MODEL_SETTINGS))
        settings = json.loads(z.read(PROJECT_SETTINGS)) if PROJECT_SETTINGS in z.namelist() else None
    area, plate_mm = printable_area(settings, bed_xy)
    meshes = {}
    for obj in root.iterfind("m:resources/m:object", ns):
        v = np.array([[float(q.get(k)) for k in "xyz"] for q in obj.iterfind("m:mesh/m:vertices/m:vertex", ns)])
        f = np.array([[int(q.get(k)) for k in ("v1", "v2", "v3")]
                      for q in obj.iterfind("m:mesh/m:triangles/m:triangle", ns)], dtype=np.int64)
        meshes[obj.get("id")] = (obj.get("name") or "", v.reshape(-1, 3), f.reshape(-1, 3))
    objects = {}
    for obj in config.iterfind("object"):
        meta = {m.get("key"): m.get("value") for m in obj.iterfind("metadata")}
        oid = obj.get("id")
        name, v, f = meshes.get(oid, (meta.get("name", ""), np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)))
        objects[oid] = {"name": meta.get("name", name), "extruder": int(meta.get("extruder", 1)),
                        "triangles": int(len(f)), "volume_mm3": mesh_volume(v, f) if len(f) else 0.0}
    plates = []
    for el in config.iterfind("plate"):
        meta = {m.get("key"): m.get("value") for m in el.iterfind("metadata")}
        listed = []
        for inst in el.iterfind("model_instance"):
            im = {m.get("key"): m.get("value") for m in inst.iterfind("metadata")}
            listed.append((im.get("object_id"), int(im.get("instance_id", -1))))
        plates.append({"index": int(meta["plater_id"]), "name": meta.get("plater_name", ""),
                       "bed_type": meta.get("bed_type"), "listed": listed, "placements": []})
    plates.sort(key=lambda p: p["index"])
    count = len(plates)
    outside, seen = [], {}
    for item in root.iterfind("m:build/m:item", ns):
        oid = item.get("objectid")
        name, v, _ = meshes[oid]
        t = [float(c) for c in (item.get("transform") or "1 0 0 0 1 0 0 0 1 0 0 0").split()]
        M, T = np.array(t[:9]).reshape(3, 3), np.array(t[9:])
        world = v @ M + T
        lo, hi = world.min(axis=0), world.max(axis=0)
        k = seen.get(oid, 0)
        seen[oid] = k + 1
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        plate = plate_at(cx, cy, count, plate_mm, area) if count else None
        c, s = t[0], t[1]
        angle = int(round(math.degrees(math.atan2(s, c)))) % 360
        rec = {"object": oid, "instance": k, "part": objects.get(oid, {}).get("name", name), "angle": angle,
               "z_mm": float(lo[2]), "height_mm": float(hi[2] - lo[2])}
        if plate is None:
            outside.append(rec)
            continue
        ox, oy = plate_origin(plate, count, plate_mm)
        rec.update(x=float(lo[0] - ox - area[0]), y=float(lo[1] - oy - area[1]), width=float(hi[0] - lo[0]), depth=float(hi[1] - lo[1]))
        plates[plate - 1]["placements"].append(rec)
    return {"plates": plates, "objects": objects, "outside": outside, "plate_mm": list(plate_mm),
            "project_settings": settings}


def as_plates(back: Dict[str, Any]) -> List[Plate]:
    """A read-back's plates as ``Plate`` objects (copies numbered in file order), for ``check_plates``."""
    out = []
    for p in back["plates"]:
        out.append(Plate(p["index"], p["name"], [Placement(q["part"], q["instance"] + 1, q["x"], q["y"], q["width"],
                                                           q["depth"], q["angle"]) for q in p["placements"]]))
    return out


def _compare(back: Dict[str, Any], plates: Sequence[Plate], meshes: Dict[str, Tuple[Any, Any]],
             bed_xy: Sequence[float], gap: float, margin: float, keep_out: Sequence[Sequence[float]]) -> List[str]:
    """Where a read-back differs from the layout written: plate count, which copies each plate lists and holds,
    each copy's place and turn, the rules (``check_plates``), and each object's triangles and volume."""
    problems = []
    if len(back["plates"]) != len(plates):
        problems.append(f"{len(back['plates'])} plates read back, {len(plates)} written")
    if back["outside"]:
        problems.append(f"{len(back['outside'])} copies lie on no plate")
    for p, got in zip(plates, back["plates"]):
        held = sorted((q["object"], q["instance"]) for q in got["placements"])
        if held != sorted(got["listed"]):
            problems.append(f"plate {p.index} lists {sorted(got['listed'])} but holds {held}")
        if len(got["placements"]) != len(p.placements):
            problems.append(f"plate {p.index}: {len(got['placements'])} copies read back, {len(p.placements)} placed")
            continue
        for want, q in zip(p.placements, got["placements"]):
            off = max(abs(want.x - q["x"]), abs(want.y - q["y"]), abs(want.width - q["width"]),
                      abs(want.depth - q["depth"]))
            if want.part != q["part"] or want.angle % 360 != q["angle"] or off > POSITION_TOL_MM or abs(q["z_mm"]) > 1e-6:
                problems.append(f"plate {p.index}: {want.part} #{want.copy} read back as {q['part']} at "
                                f"({q['x']:.4f}, {q['y']:.4f}) turned {q['angle']}, placed at ({want.x:.4f}, "
                                f"{want.y:.4f}) turned {want.angle}")
    problems += check_plates(as_plates(back), bed_xy, gap, margin, keep_out, tol=POSITION_TOL_MM)
    for oid, o in back["objects"].items():
        src = meshes.get(o["name"])
        if src is None:
            problems.append(f"object {oid} ({o['name']}) is not a part written")
            continue
        ref = mesh_volume(np.asarray(src[0], dtype=float), np.asarray(src[1], dtype=np.int64))
        if o["triangles"] != len(src[1]) or abs(o["volume_mm3"] - ref) > VOLUME_RTOL * abs(ref):
            problems.append(f"{o['name']}: {o['triangles']} triangles and {o['volume_mm3']:.1f} mm3 read back, "
                            f"{len(src[1])} and {ref:.1f} written")
    return problems


# ---------------------------------------------------------------------------------------------------------------
# The top-down picture

PALETTE = ("#2f7f73", "#bd3a12", "#4b6cb7", "#b8860b", "#7a4f9a", "#5a7d2a")   # one fill per filament group


def plates_svg(plates: Sequence[Plate], footprints: Dict[str, Footprint], bed_xy: Sequence[float], *,
               margin: float = 0.0, keep_out: Sequence[Sequence[float]] = (), labels: Optional[Dict[int, str]] = None,
               columns_max: int = 4, title: str = "") -> str:
    """The plates seen from above, as one standalone SVG (1 unit = 1 mm): each bed, its margin (dashed) and keep-out
    areas (hatched), and each copy's real outline turned and placed as laid out, coloured by group and named."""
    W, D = float(bed_xy[0]), float(bed_xy[1])
    cols = max(1, min(columns_max, len(plates)))
    rows = max(1, math.ceil(len(plates) / cols))
    pad, head = 16.0, 22.0
    cell_w, cell_h = W + pad, D + head + pad
    width, height = cols * cell_w + pad, rows * cell_h + pad + (14.0 if title else 0.0)
    groups = []
    for p in plates:
        if p.group not in groups:
            groups.append(p.group)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_num(width, 2)} {_num(height, 2)}" '
           f'width="{_num(width * 2.4, 0)}" height="{_num(height * 2.4, 0)}" font-family="system-ui, sans-serif" '
           'role="img">',
           f"<title>{escape(title or 'Build plates')}</title>",
           '<defs><pattern id="ko" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="4" stroke="#8a8f87" stroke-width="1.2"/></pattern></defs>',
           f'<rect width="{_num(width, 2)}" height="{_num(height, 2)}" fill="#fffdf5"/>']
    top = pad + (14.0 if title else 0.0)
    if title:
        out.append(f'<text x="{_num(pad, 2)}" y="{_num(pad + 6, 2)}" font-size="9" font-weight="600" '
                   f'fill="#173d3c">{escape(title)}</text>')
    for k, p in enumerate(plates):
        cx, cy = pad + (k % cols) * cell_w, top + (k // cols) * cell_h
        bx, by = cx, cy + head
        label = (labels or {}).get(p.index) or f"Plate {p.index}"
        cover = sum(footprints[q.part].area() for q in p.placements) / (W * D) * 100
        out.append(f'<g><text x="{_num(bx, 2)}" y="{_num(cy + 8, 2)}" font-size="7.5" font-weight="600" '
                   f'fill="#173d3c">{escape(label)}</text>'
                   f'<text x="{_num(bx, 2)}" y="{_num(cy + 17, 2)}" font-size="6" fill="#4d5f5a">'
                   f'{len(p.placements)} part{"s" if len(p.placements) != 1 else ""} · {cover:.0f} % of the bed covered'
                   '</text>')
        out.append(f'<rect x="{_num(bx, 2)}" y="{_num(by, 2)}" width="{_num(W, 2)}" height="{_num(D, 2)}" rx="3" '
                   'fill="#eef1e4" stroke="#6f8a80" stroke-width="1"/>')
        if margin > 0:
            out.append(f'<rect x="{_num(bx + margin, 2)}" y="{_num(by + margin, 2)}" width="{_num(W - 2 * margin, 2)}" '
                       f'height="{_num(D - 2 * margin, 2)}" fill="none" stroke="#9fb0a8" stroke-width="0.6" '
                       'stroke-dasharray="3 2"/>')
        for x0, y0, x1, y1 in keep_out:
            out.append(f'<rect x="{_num(bx + x0, 2)}" y="{_num(by + D - y1, 2)}" width="{_num(x1 - x0, 2)}" '
                       f'height="{_num(y1 - y0, 2)}" fill="url(#ko)" stroke="#8a8f87" stroke-width="0.6"/>')
        colour = PALETTE[groups.index(p.group) % len(PALETTE)]
        for q in p.placements:
            fp = footprints[q.part]
            turned = _turn(fp.hull, q.angle)
            x0, y0, _, _ = _box(turned)
            pts = " ".join(f"{_num(bx + q.x + x - x0, 2)},{_num(by + D - (q.y + y - y0), 2)}" for x, y in turned)
            name = q.part.replace("_", " ")
            tip = f"{q.part} #{q.copy}" + (f", turned {q.angle}°" if q.angle else "")
            out.append(f'<polygon points="{pts}" fill="{colour}" fill-opacity="0.82" stroke="#173d3c" '
                       f'stroke-width="0.6"><title>{escape(tip)}</title></polygon>')
            size = min(6.0, q.width / max(len(name), 1) * 1.7, q.depth * 0.5)
            if size >= 2.6:
                out.append(f'<text x="{_num(bx + q.x + q.width / 2, 2)}" y="{_num(by + D - q.y - q.depth / 2 + size * 0.35, 2)}" '
                           f'font-size="{_num(size, 2)}" text-anchor="middle" fill="#ffffff">{escape(name)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# A project's plates (``cad-agent export-3mf``)

_KEYS = {"gap_mm", "margin_mm", "rotate", "keep_out", "parts", "bed_type"}
_PART_KEYS = {"quantity", "filament"}


@dataclass
class PlatesConfig:
    """``cad.plates``, resolved: the parts to print and how many, each part's filament, and the layout rules."""
    parts: List[str]
    quantities: Dict[str, int]
    filaments: Dict[str, str]                  # part -> filament profile name
    gap: float = DEFAULT_GAP_MM
    margin: float = DEFAULT_MARGIN_MM
    rotate: bool = True
    keep_out: List[Tuple[float, float, float, float]] = field(default_factory=list)
    bed_type: str = ""                          # Bambu Studio plate surface; "" = the project settings' own
    warnings: List[str] = field(default_factory=list)


def _number(raw: Dict[str, Any], key: str, default: float) -> float:
    v = raw.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        from cadagent.project import CadConfigError
        raise CadConfigError(f"cad.plates.{key} must be a number of mm, zero or more")
    return float(v)


def plates_config(project, known_parts: Sequence[str]) -> Optional[PlatesConfig]:
    """Parse ``cad.plates`` (None when it is ``false``). The parts default to ``cad.release.build``, else every part
    the release lists; quantities to ``cad.release.quantities``, else 1; filaments to ``cad.slicer.filament``."""
    from cadagent.manufacturing.slicer import FILAMENTS, _settings
    from cadagent.project import CadConfigError
    from cadagent.publish.release import release_config

    raw = project.plates
    if raw is False:
        return None
    if raw is None or raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raise CadConfigError("cad.plates must be a mapping (or false to write no plates file)")
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise CadConfigError(f"cad.plates: unknown keys {unknown}; known: {sorted(_KEYS)}")
    gap, margin = _number(raw, "gap_mm", DEFAULT_GAP_MM), _number(raw, "margin_mm", DEFAULT_MARGIN_MM)
    rotate = raw.get("rotate", True)
    if not isinstance(rotate, bool):
        raise CadConfigError("cad.plates.rotate must be true or false")
    keep_out = []
    for i, k in enumerate(raw.get("keep_out") or []):
        if not (isinstance(k, list) and len(k) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                            for v in k) and k[2] > k[0] and k[3] > k[1]):
            raise CadConfigError(f"cad.plates.keep_out[{i}] must be [x0, y0, x1, y1] in mm with x1 > x0 and y1 > y0")
        keep_out.append(tuple(float(v) for v in k))
    bed = raw.get("bed_type", "")
    if bed and bed not in BED_TYPES:
        raise CadConfigError(f"cad.plates.bed_type must be one of {sorted(BED_TYPES)}")
    release = release_config(project, list(known_parts))
    default_filament = _settings(project)["filament"]
    warnings = []
    spec = raw.get("parts")
    overrides: Dict[str, Dict[str, Any]] = {}
    if spec is None:
        if release.build:
            parts = list(release.build.parts)
        else:
            parts = [p for g in release.groups for p in g.parts]
            loose = [g.title for g in release.groups if g.pick_one or g.optional]
            if loose:
                warnings.append(f"the plates hold every part of the pick-one or optional groups {loose}; set "
                                "cad.release.build or cad.plates.parts to print one build")
    elif isinstance(spec, list) and spec and all(isinstance(p, str) for p in spec):
        parts = list(spec)
    elif isinstance(spec, dict) and spec:
        parts = [str(p) for p in spec]
        for p, v in spec.items():
            v = v or {}
            if not isinstance(v, dict) or set(v) - _PART_KEYS:
                raise CadConfigError(f"cad.plates.parts.{p} must be a mapping of {sorted(_PART_KEYS)}")
            q = v.get("quantity", None)
            if q is not None and (isinstance(q, bool) or not isinstance(q, int) or q < 1):
                raise CadConfigError(f"cad.plates.parts.{p}.quantity must be a whole number >= 1")
            if "filament" in v and (not isinstance(v["filament"], str) or not v["filament"].strip()):
                raise CadConfigError(f"cad.plates.parts.{p}.filament must be pla, petg or a filament profile name")
            overrides[str(p)] = v
    else:
        raise CadConfigError("cad.plates.parts must be a non-empty list of parts, or a mapping of part -> "
                             "{quantity, filament}")
    twice = sorted({p for p in parts if parts.count(p) > 1})
    unknown_parts = [p for p in parts if p not in known_parts]
    if twice or unknown_parts:
        raise CadConfigError(f"cad.plates.parts: parts must be in the parts file, each once (listed twice: "
                             f"{twice or 'none'}; not in the parts file: {unknown_parts or 'none'})")
    quantities = {p: int(overrides.get(p, {}).get("quantity") or release.quantities.get(p, 1)) for p in parts}
    filaments = {p: FILAMENTS.get(overrides.get(p, {}).get("filament", default_filament),
                                  overrides.get(p, {}).get("filament", default_filament)) for p in parts}
    return PlatesConfig(parts, quantities, filaments, gap, margin, rotate, keep_out, bed, warnings)


def plates_file(project) -> Path:
    """``<exports_dir>/<name>-plates.3mf``."""
    import re
    return project.exports_dir / (re.sub(r"[^A-Za-z0-9._-]+", "-", project.name).strip("-") + "-plates.3mf")


def _short(filament: str) -> str:
    return filament.split(" @")[0]


BED_TYPES = {"Textured PEI Plate": "textured_plate_temp", "High Temp Plate": "hot_plate_temp",
             "Supertack Plate": "supertack_plate_temp", "Engineering Plate": "eng_plate_temp",
             "Cool Plate": "cool_plate_temp"}     # Bambu Studio's plate surfaces, and each filament's bed temperature


def bed_type(settings: Dict[str, Any], filament_slots: Sequence[int], wanted: str = "") -> Optional[str]:
    """The plate surface for a plate printing the filaments in ``filament_slots`` (0-based): ``wanted`` (else the
    project's ``curr_bed_type``) when every one of them has a bed temperature for it, else the first in ``BED_TYPES``
    order that all of them have one for. Bambu Studio refuses to slice a plate whose surface a filament lists at 0 °C
    (PETG on the Cool Plate). None when none suits them all."""
    def ok(name):
        temps = settings.get(BED_TYPES.get(name, ""))
        return isinstance(temps, list) and all(i < len(temps) and str(temps[i]).strip() not in ("", "0")
                                               for i in filament_slots)
    for name in [wanted or str(settings.get("curr_bed_type") or "")] + list(BED_TYPES):
        if name in BED_TYPES and ok(name):
            return name
    return None


def _exclude_box(settings: Optional[Dict[str, Any]], area) -> Optional[Tuple[float, float, float, float]]:
    """The printer's bed exclusion area (``bed_exclude_area``, Bambu's wiper corner) as a box in bed coordinates."""
    pts = []
    for p in (settings or {}).get("bed_exclude_area") or []:
        try:
            pts.append(tuple(float(c) for c in str(p).split("x")))
        except ValueError:
            return None
    if len(pts) < 3:
        return None
    x0, y0 = min(p[0] for p in pts) - area[0], min(p[1] for p in pts) - area[1]
    x1, y1 = max(p[0] for p in pts) - area[0], max(p[1] for p in pts) - area[1]
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def export_plates(project, known_parts: Optional[Sequence[str]] = None, settings_bytes: Optional[bytes] = None,
                  use_slicer: bool = True) -> Optional[Dict[str, Any]]:
    """Write ``<name>-plates.3mf`` (verified), ``<name>-plates.json`` (the layout) and ``<name>-plates.svg`` (the
    plates from above) into ``exports_dir``; None when ``cad.plates`` is false. The project settings are
    ``settings_bytes`` when given, else Bambu Studio's for ``cad.slicer`` when it is installed and ``use_slicer``,
    else left out (the record and the warnings say so: Bambu Studio then opens the file on one plate)."""
    from cadagent.manufacturing import slicer
    from cadagent.publish.report import load_parts

    trimesh = require("trimesh", "build plates (STL loading)")
    if known_parts is None:
        known, error = load_parts(project)
        if error:
            raise FileNotFoundError(error)
        known_parts = list(known)
    cfg = plates_config(project, known_parts)
    if cfg is None:
        return None
    bed = project.printer.bed_mm
    if not bed:
        raise PlatesError("cad.printer.bed_mm is required to lay out build plates")
    path = plates_file(project)
    if path.stem in known_parts:
        raise PlatesError(f"a part is named {path.stem!r}, the plates file's name; rename it or set cad.plates: false")
    meshes = {}
    for part in cfg.parts:
        stl = project.exports_dir / f"{part}.stl"
        if not stl.is_file():
            raise FileNotFoundError(f"{stl} not found; run the build first")
        mesh = trimesh.load_mesh(stl, process=True)
        meshes[part] = (_normalised(mesh.vertices), np.asarray(mesh.faces, dtype=np.int64))
    groups = []
    for part in cfg.parts:
        if cfg.filaments[part] not in groups:
            groups.append(cfg.filaments[part])
    warnings = list(cfg.warnings)
    settings = _settings_record = None
    sl = slicer._settings(project)
    if settings_bytes is None and use_slicer and slicer.executable():
        try:
            settings_bytes = slicer.project_settings(project.root / "build" / "slicer" / "plates", sl["printer"],
                                                     sl["process"], groups, sl["overrides"],
                                                     colours=[PALETTE[i % len(PALETTE)] for i in range(len(groups))])
        except (OSError, RuntimeError, KeyError, ValueError, FileExistsError) as exc:
            warnings.append(f"no project settings ({exc}); Bambu Studio will open the file on one plate")
    elif settings_bytes is None:
        warnings.append("Bambu Studio is not installed, so the file carries no project settings: Bambu Studio "
                        "will open it on one plate (run export-3mf where it is installed)" if use_slicer else
                        "no project settings asked for: Bambu Studio will open the file on one plate")
    if settings_bytes:
        settings = json.loads(settings_bytes)
        _settings_record = {"embedded": True, "slicer_version": settings.get("version"), "printer": sl["printer"],
                            "process": sl["process"], "filaments": groups, "overrides": sl["overrides"]}
    area, plate_mm = printable_area(settings, bed)
    if float(bed[0]) > area[2] - area[0] + 1e-6 or float(bed[1]) > area[3] - area[1] + 1e-6:
        raise PlatesError(f"cad.printer.bed_mm {bed[0]:g} x {bed[1]:g} mm is larger than the printable area of "
                          f"{sl['printer']} ({area[2] - area[0]:g} x {area[3] - area[1]:g} mm)")
    keep_out = list(cfg.keep_out)
    exclude = _exclude_box(settings, area)
    if exclude and not any(k[0] <= exclude[0] and k[1] <= exclude[1] and k[2] >= exclude[2] and k[3] >= exclude[3]
                           for k in keep_out):
        keep_out.append(exclude)
    fps = {part: footprint(meshes[part][0]) for part in cfg.parts}
    copies = [Copy(part, k, fps[part], cfg.filaments[part]) for part in cfg.parts
              for k in range(1, cfg.quantities[part] + 1)]
    plates = pack(copies, bed, cfg.gap, cfg.margin, cfg.rotate, keep_out)
    problems = check_plates(plates, bed, cfg.gap, cfg.margin, keep_out, cfg.quantities, cfg.filaments)
    if problems:
        raise PlatesError("the layout breaks its own rules: " + "; ".join(problems[:5]))
    count = {g: sum(1 for p in plates if p.group == g) for g in groups}
    seen: Dict[str, int] = {}
    names = {}
    for p in plates:
        seen[p.group] = seen.get(p.group, 0) + 1
        names[p.index] = _short(p.group) + (f" {seen[p.group]} of {count[p.group]}" if count[p.group] > 1 else "")
    beds: Dict[int, str] = {}       # written only where the plate differs from the project's surface, or asked for
    if settings:
        for p in plates:
            chosen = bed_type(settings, [groups.index(p.group)], cfg.bed_type)
            if chosen is None:
                raise PlatesError(f"plate {p.index} ({_short(p.group)}): no plate surface has a bed temperature for "
                                  "its filament in the project settings")
            if cfg.bed_type or chosen != settings.get("curr_bed_type"):
                beds[p.index] = chosen
            if chosen != (cfg.bed_type or settings.get("curr_bed_type")):
                warnings.append(f"plate {p.index}: {_short(p.group)} has no "
                                f"{cfg.bed_type or settings.get('curr_bed_type')} temperature, so the plate is set to "
                                f"the {chosen}")
    elif cfg.bed_type:
        warnings.append("cad.plates.bed_type needs the project settings (Bambu Studio installed); not written")
    back = write_plates_3mf(path, meshes, plates, bed_xy=bed, gap=cfg.gap, margin=cfg.margin, keep_out=keep_out,
                            extruders={part: groups.index(cfg.filaments[part]) + 1 for part in cfg.parts},
                            plate_names=names, bed_types=beds, project_settings=settings_bytes,
                            title=project.title or project.name)
    svg_path = path.with_suffix(".svg")
    svg_path.write_text(plates_svg(plates, fps, bed, margin=cfg.margin, keep_out=keep_out, labels=names,
                                   title=f"{project.title or project.name}: {sum(cfg.quantities.values())} parts on "
                                         f"{len(plates)} plate{'s' if len(plates) != 1 else ''}"))
    import hashlib
    record = {
        "format": MARKER,
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "picture": svg_path.name,
        "bed_mm": [float(b) for b in bed],
        "plate_mm": list(plate_mm),
        "gap_mm": cfg.gap, "margin_mm": cfg.margin, "rotate": cfg.rotate, "packing": plates.method,
        "keep_out_mm": [list(k) for k in keep_out],
        "quantities": cfg.quantities,
        "filaments": {part: cfg.filaments[part] for part in cfg.parts},
        "plates": [{"plate": p.index, "name": names[p.index], "filament": p.group, "bed_type": beds.get(p.index),
                    "covered": round(sum(fps[q.part].area() for q in p.placements) / (float(bed[0]) * float(bed[1])), 3),
                    "parts": [{"part": q.part, "copy": q.copy, "x_mm": q.x, "y_mm": q.y, "width_mm": round(q.width, 4),
                               "depth_mm": round(q.depth, 4), "turn_deg": q.angle} for q in p.placements]}
                   for p in plates],
        "project_settings": _settings_record or {"embedded": False},
        "warnings": warnings,
        "note": ("CAD layout from footprint rectangles: not sliced, and not proof that a plate prints well "
                 "(adhesion, warping, supports)."),
    }
    path.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    record["path"] = str(path)
    record["read_back"] = {"plates": len(back["plates"]), "copies": sum(len(p["placements"]) for p in back["plates"])}
    return record
