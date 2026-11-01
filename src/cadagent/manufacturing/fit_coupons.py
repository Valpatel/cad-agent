"""Fit coupons: print the holes of a part's fits first, so the first print calibrates them.

    from cadagent.manufacturing import fit_coupons as fc
    fits = [fc.Fit("pivot pin", 5.0, "slide"), fc.Fit("bushing seat", 8.0, "press", depth_mm=8),
            fc.Fit("608 bearing", 22.0, "press", depth_mm=7, axis="horizontal", count=5)]
    fc.plan(fits)                       # every hole's CAD diameter, and where its allowance came from
    fc.write(fits, "exports/coupons")   # a STEP and a print-oriented STL per coupon, and the measurement sheet
    fc.from_coupon(fits[0], 5.45)       # the hole that fitted: the offset to use for this printer and filament

A printed hole comes out smaller than drawn, by an amount that depends on the printer, the filament, the slicer and
whether the hole's axis stands along the build direction or lies in the bed plane. A part designed at nominal sizes
finds this out after the long print: a pin that will not go in, a bearing that falls out. A coupon is a plate per
fit with a sweep of holes round the expected CAD size: nominal, plus the fit's allowance, plus the process
profile's undersize, plus or minus ``step_mm``. Print it in the part's filament and orientation, try the real pin,
bushing, bearing or insert in each hole, write down which one fits, and draw the part's hole at that size.

The numbers are research/process-profiles.yaml's (tests/test_fit_coupons.py keeps them in step):

* undersize, ``fdm-hole-undersize-cnckitchen``: printed holes came out about 0.25 mm under CAD (one printer, PLA);
* ``slide``, ``fdm-clearance-sliding-xometry-eu``: 0.2-0.3 mm clearance for a sliding fit (0.25 taken);
* ``free``, ``fdm-clearance-moving-prusa``: at least 0.3 mm for parts that move;
* ``insert``: the insert maker's hole, plus the undersize, which is CNC Kitchen's 0.2-0.3 mm CAD allowance
  (``fdm-insert-hole-cad-offset-cnckitchen``);
* ``press``: no allowance (line to line once the undersize is added); no published interference for a press fit in a
  printed hole was found, so the sweep is how you find it.

Limits: one row of holes per fit, no threads, no pegs. A coupon calibrates the printer, filament and slicer settings
it was printed with: print it again when any of them changes. The sizes are where to start, not a promise of fit.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from cadagent._deps import require

UNDERSIZE_MM = 0.25            # fdm-hole-undersize-cnckitchen
ALLOWANCE_MM = {"press": 0.0, "slide": 0.25, "free": 0.3, "insert": 0.0}
ALLOWANCE_SOURCE = {
    "press": "none published for a printed hole: the sweep finds it",
    "slide": "research/process-profiles.yaml fdm-clearance-sliding-xometry-eu (0.2-0.3 mm; 0.25 taken)",
    "free": "research/process-profiles.yaml fdm-clearance-moving-prusa (at least 0.3 mm)",
    "insert": "the insert maker's hole; the undersize is CNC Kitchen's 0.2-0.3 mm CAD allowance "
              "(research/process-profiles.yaml fdm-insert-hole-cad-offset-cnckitchen)",
}
UNDERSIZE_SOURCE = ("research/process-profiles.yaml fdm-hole-undersize-cnckitchen: printed holes about 0.25 mm under "
                    "CAD (one printer, PLA); every printer and filament differs, which is why the coupon is printed")
AXES = ("vertical", "horizontal")       # the hole's axis along the build direction, or lying in the bed plane
MIN_WALL_MM = 2.0
NOTCH_MM = 3.0


@dataclass(frozen=True)
class Fit:
    """A hole a bought part goes into: ``nominal_mm`` is the part's diameter (or the insert maker's hole), ``kind``
    one of ALLOWANCE_MM (or ``allowance_mm`` set), ``axis`` the hole's axis against the build direction, as the part
    will be printed. ``count`` holes, ``step_mm`` apart, centred on the expected CAD size."""
    name: str
    nominal_mm: float
    kind: str = "slide"
    axis: str = "vertical"
    depth_mm: Optional[float] = None
    allowance_mm: Optional[float] = None
    undersize_mm: float = UNDERSIZE_MM
    step_mm: float = 0.05
    count: int = 9

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("a fit needs a name")
        for key in ("nominal_mm", "step_mm"):
            v = getattr(self, key)
            if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
                raise ValueError(f"{key} must be a positive number, not {v!r}")
        if self.kind not in ALLOWANCE_MM and self.allowance_mm is None:
            raise ValueError(f"kind must be one of {sorted(ALLOWANCE_MM)}, or give allowance_mm")
        if self.axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, not {self.axis!r}")
        if not (isinstance(self.count, int) and self.count >= 1 and self.count % 2 == 1):
            raise ValueError(f"count must be an odd whole number, so one hole sits at the expected size: {self.count!r}")
        if self.depth_mm is not None and not (math.isfinite(self.depth_mm) and self.depth_mm > 0):
            raise ValueError(f"depth_mm must be positive, not {self.depth_mm!r}")
        if not (math.isfinite(self.undersize_mm) and self.undersize_mm >= 0):
            raise ValueError(f"undersize_mm must be at least 0, not {self.undersize_mm!r}")
        if self.diameters()[0] <= 0:
            raise ValueError(f"{self.name}: the sweep's smallest hole is not above 0 mm")

    @property
    def allowance(self) -> float:
        return ALLOWANCE_MM[self.kind] if self.allowance_mm is None else float(self.allowance_mm)

    @property
    def centre_mm(self) -> float:
        """The expected CAD size: nominal + allowance + undersize."""
        return self.nominal_mm + self.allowance + self.undersize_mm

    def diameters(self) -> List[float]:
        half = self.count // 2
        return [round(self.centre_mm + k * self.step_mm, 4) for k in range(-half, half + 1)]

    @property
    def depth(self) -> float:
        return self.depth_mm if self.depth_mm is not None else max(4.0, min(self.nominal_mm, 10.0))

    @property
    def slug(self) -> str:
        return "".join(c if c.isalnum() else "-" for c in self.name.lower()).strip("-") or "fit"


def layout(fit: Fit) -> Dict[str, Any]:
    """The coupon's plate: hole centres (row by row from the notched corner, sizes rising), its size and thickness."""
    ds = fit.diameters()
    wall = max(MIN_WALL_MM, 0.25 * max(ds))
    pitch = max(ds) + wall
    # a coupon printed flat is a square grid; one printed standing (horizontal holes) is one row, so it stands low
    cols = len(ds) if fit.axis == "horizontal" else math.ceil(math.sqrt(len(ds)))
    rows = math.ceil(len(ds) / cols)
    centres = [(wall / 2 + pitch * (i % cols) + pitch / 2, wall / 2 + pitch * (i // cols) + pitch / 2)
               for i in range(len(ds))]
    return {"diameters_mm": ds, "centres_mm": [(round(x, 4), round(y, 4)) for x, y in centres],
            "size_mm": (round(cols * pitch + wall, 4), round(rows * pitch + wall, 4)),
            "thickness_mm": fit.depth, "wall_mm": wall, "notch_mm": NOTCH_MM}


def plan(fits: Iterable[Fit]) -> List[Dict[str, Any]]:
    """Every coupon's holes, as plain data: for the measurement sheet and for a reviewer."""
    out = []
    for fit in fits:
        lay = layout(fit)
        out.append({"fit": asdict(fit), "slug": fit.slug, "centre_mm": round(fit.centre_mm, 4),
                    "allowance_mm": fit.allowance, "allowance_source": ALLOWANCE_SOURCE.get(fit.kind, "given"),
                    "undersize_source": UNDERSIZE_SOURCE, "print": "standing on its edge, hole axes in the bed plane"
                    if fit.axis == "horizontal" else "flat on the bed, hole axes upright", **lay})
    return out


def coupon(fit: Fit):
    """The coupon as a CadQuery solid, in the part's frame (holes along Z, the notch at the origin corner)."""
    cq = require("cadquery", "fit coupons")
    lay = layout(fit)
    w, h = lay["size_mm"]
    t = lay["thickness_mm"]
    body = cq.Workplane("XY").box(w, h, t, centered=False)
    for (x, y), d in zip(lay["centres_mm"], lay["diameters_mm"]):
        body = body.cut(cq.Workplane("XY").center(x, y).circle(d / 2).extrude(t))
    notch = cq.Workplane("XY").polyline([(0, 0), (NOTCH_MM, 0), (0, NOTCH_MM)]).close().extrude(t)
    return body.cut(notch).val()


def sheet(fits: Iterable[Fit]) -> str:
    """The measurement sheet as CSV: a row per hole, with blank columns to fill in after printing."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(["coupon", "hole", "cad_mm", "offset_mm", "nominal_mm", "allowance_mm", "undersize_mm", "axis",
                  "measured_mm", "fit"])
    for fit in fits:
        for i, d in enumerate(fit.diameters(), start=1):
            out.writerow([fit.slug, i, f"{d:.3f}", f"{d - fit.centre_mm:+.3f}", f"{fit.nominal_mm:g}",
                          f"{fit.allowance:g}", f"{fit.undersize_mm:g}", fit.axis, "", ""])
    return buf.getvalue()


def write(fits: Iterable[Fit], out_dir: Any) -> Dict[str, Any]:
    """Write each coupon as ``<slug>.step`` (the part's frame) and ``<slug>.stl`` (print orientation), the
    measurement sheet ``fit-coupons.csv`` and the plan ``fit-coupons.json``. Returns the paths and the STL reports."""
    import json

    from cadagent.geometry import export_print_stl, export_step
    fits = list(fits)
    slugs = [f.slug for f in fits]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"two fits share a name: {slugs}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Any] = {"coupons": {}}
    for fit in fits:
        solid = coupon(fit)
        step = export_step(solid, out / f"{fit.slug}.step", name=fit.slug)
        rotation = ((1, 0, 0), 90.0) if fit.axis == "horizontal" else None
        stl = export_print_stl(solid, out / f"{fit.slug}.stl", rotation=rotation)
        files["coupons"][fit.slug] = {"step": str(step), "stl": str(out / f"{fit.slug}.stl"), "stl_report": stl}
    (out / "fit-coupons.csv").write_text(sheet(fits))
    (out / "fit-coupons.json").write_text(json.dumps(plan(fits), indent=2, sort_keys=True) + "\n")
    files.update(sheet=str(out / "fit-coupons.csv"), plan=str(out / "fit-coupons.json"))
    return files


def from_coupon(fit: Fit, cad_mm: float, measured_mm: Optional[float] = None) -> Dict[str, Any]:
    """Read a printed coupon back: ``cad_mm`` is the CAD diameter of the hole that gave the fit wanted. Returns the
    printer's offset for this filament and axis (what to add to nominal + allowance for holes of about this size),
    and, with ``measured_mm`` (that hole measured with a pin gauge), how much under CAD it printed."""
    if not any(abs(d - cad_mm) < 1e-6 for d in fit.diameters()):
        raise ValueError(f"{cad_mm!r} is not one of {fit.name}'s holes: {fit.diameters()}")
    out = {"fit": fit.name, "cad_mm": cad_mm, "printer_offset_mm": round(cad_mm - fit.nominal_mm - fit.allowance, 4)}
    if measured_mm is not None:
        out["printed_under_cad_mm"] = round(cad_mm - measured_mm, 4)
    return out
