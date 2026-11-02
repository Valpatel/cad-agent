"""Self-clinching (PEM-type) nuts, studs and standoffs pressed into sheet: a cited subset of the common parts, and one
check of a part's placement against PEM's published rules (#283).

    from cadagent.mechanical.clinch import check_placement, parts_for
    check_placement("S-M3-1", "5052-h32", 1.6, edge_mm=6.0, to_bend_mm=8.0, neighbours=[("S-M3-1", 12.0)])
    # verdict pass / warn / fail, each check with its value, limit, rule and source
    parts_for("M3", "5052-h32", 1.6)              # the listed parts that clinch into 1.6 mm 5052, nuts first

**What is checked**, each against the rule it names (the ``sm-clinch-*`` rules of ``research/process-profiles.yaml``
and the part's own row from PEM's bulletins):

- the sheet's hardness: at most the hardest sheet the part's material takes (PEM handbook HB-6), with a warning when
  the alloy's typical range straddles that limit (read the mill certificate); and no part listed here goes into
  stainless sheet, which takes only PEM's hardened-stainless types (SP, SMPP, FH4, SO4; bulletin CL-18);
- the sheet's thickness: at least the part's minimum for its shank (bulletins CL, FH, SO);
- the hole, when given: the catalogue hole +0.08 mm / -0 (HB-9);
- the edge distance, when given: at least the part's centre-to-edge distance (one edge only, HB-12);
- the bend, when given: hole centre to the bend centre line at least BA/2 + E, PEM's rule measured from the outside of
  the bend radius moved onto the bend centre line (HB-12; the same datum as SendCutSend's rule);
- each neighbour: centre to centre at least one part's E plus half the other's hole, both ways round (HB-12);
- loads, when given: push-out, torque and pull-through against PEM's averages in its test sheet, divided by ``factor``.

It also says, as a note, to press in from the punch side of a punched hole from 2.29 mm (HB-9), and that the
hardware goes in after plating or anodising and before paint or powder (HB-9, HB-12).

**Limits.** The strengths are PEM's averages in its own test sheets (5052-H34 aluminium and cold-rolled steel; the
thickness is not printed for the nuts), not allowables: PEM asks for a test in the real part. A different sheet,
thickness or hole changes them. The data is a cited subset of PEM's bulletins, by part and page, for the sizes most
enclosures use; PEM's own catalogue governs. A shop's own limits (SendCutSend's per-part K, N and M) are not checked
here: they belong to that shop's profile. Nothing here proves a part holds: test one.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cadagent.manufacturing import process as pp

IN, LBF, INLBF = 25.4, 4.4482216152605, 0.112984829      # mm per inch, N per lbf, N m per in lbf

# Registry ids (research/references.yaml) of the sources this module reads its numbers from.
SRC = {
    "pem-handbook": "PennEngineering, The Self-Clinching Fastener Handbook (2025): HB-4 hardness margin, HB-6 sheet "
                    "hardness, HB-9 hole and punch side, HB-12 edge, bend and spacing rules",
    "pem-bulletin-cl": "PennEngineering, Bulletin CL (2026): CL-4 and CL-5 dimensions, CL-9 materials, CL-13 push-out "
                       "and torque-out, CL-18 stainless sheet",
    "pem-bulletin-fh": "PennEngineering, Bulletin FH (2026): FH-5 dimensions, FH-17 materials, FH-29 push-out and "
                       "pull-through",
    "pem-bulletin-so": "PennEngineering, Bulletin SO (2026): SO-3 and SO-4 dimensions, SO-9 materials, SO-12 push-out, "
                       "pull-through and the most screw torque",
    "pem-tech-sheet-stainless": "PennEngineering, Fasteners for use in stainless steel sheets (2019): Table 1, "
                                "stainless sheet hardness under ASTM A240",
}

# The part's material class, and the rule in process-profiles.yaml that sets the hardest sheet it clinches into.
CLASSES = {"hardened steel": "sm-clinch-sheet-hardness-steel-pem",
           "300 stainless": "sm-clinch-sheet-hardness-300ss-pem"}


@dataclass(frozen=True)
class ClinchPart:
    """One PEM part as its bulletin prints it, in mm and N (inch parts converted). ``pushout_n`` and the other ratings
    are (in aluminium, in steel) as PEM tested them; None where the bulletin gives none."""
    key: str
    kind: str                    # "nut", "stud" or "standoff"
    material: str                # a key of CLASSES
    thread: str
    hole_mm: float
    min_sheet_mm: float
    edge_mm: float               # minimum hole centre to the sheet edge (PEM's C/L to edge, E)
    pushout_n: Tuple[float, float]
    torque_out_nm: Optional[Tuple[float, float]]
    pull_through_n: Optional[Tuple[float, float]]
    screw_torque_nm: Optional[float]      # the most a mating screw may be tightened (standoffs)
    source: str                  # a key of SRC
    where: str
    test_sheet: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


_NUT_SHEET = "5052-H34 aluminium / cold-rolled steel; the thickness is not printed"


def _nut(types: Tuple[str, ...], thread: str, hole: float, sheet: float, edge: float, push: Tuple[float, float],
         torque: Tuple[float, float], inch: bool) -> List[ClinchPart]:
    k = IN if inch else 1.0
    if inch:
        push = (push[0] * LBF, push[1] * LBF)
        torque = (torque[0] * INLBF, torque[1] * INLBF)
    return [ClinchPart(f"{t}-{thread}-1", "nut", "300 stainless" if t.startswith("CL") else "hardened steel",
                       thread, round(hole * k, 4), round(sheet * k, 4), round(edge * k, 4),
                       (round(push[0], 1), round(push[1], 1)), (round(torque[0], 3), round(torque[1], 3)), None, None,
                       "pem-bulletin-cl", "CL-4, CL-5 (dimensions, shank code 1) and CL-13 (strengths)", _NUT_SHEET)
            for t in types]


_PARTS: List[ClinchPart] = [
    *_nut(("S", "CLS"), "M3", 4.22, 1.0, 4.8, (400, 550), (1.13, 1.7), False),
    *_nut(("S", "CLS"), "M4", 5.41, 1.0, 6.9, (470, 645), (2.6, 4.0), False),
    *_nut(("SS", "CLSS"), "M5", 6.35, 1.0, 7.1, (480, 800), (3.6, 4.5), False),
    *_nut(("S", "CLS"), "M6", 8.75, 1.4, 8.6, (1580, 1760), (10.2, 17), False),
    *_nut(("S", "CLS"), "440", 0.166, 0.040, 0.19, (90, 125), (10, 15), True),
    *_nut(("S", "CLS"), "632", 0.1875, 0.040, 0.22, (95, 130), (17, 20), True),
    *_nut(("S", "CLS"), "832", 0.213, 0.040, 0.27, (105, 145), (23, 35), True),
    *_nut(("SS", "CLSS"), "032", 0.250, 0.040, 0.28, (110, 180), (32, 40), True),
    *_nut(("S", "CLS"), "0420", 0.344, 0.056, 0.34, (360, 400), (90, 150), True),
]
for _t, _h, _s, _e, _p, _q in (("M3", 3.0, 1.0, 5.6, (600, 820), (3150, 3840)),
                                ("M4", 4.0, 1.0, 7.2, (975, 1780), (4448, 5650)),
                                ("M5", 5.0, 1.0, 7.2, (1070, 2000), (5170, 6270)),
                                ("M6", 6.0, 1.6, 7.9, (1660, 2560), (10200, 11300))):
    _PARTS.append(ClinchPart(f"FH-{_t}", "stud", "hardened steel", _t, _h, _s, _e, _p, None, _q, None,
                             "pem-bulletin-fh", "FH-5 (dimensions) and FH-29 (strengths)",
                             "1.6 mm aluminium (HRB 29) / 1.5 mm steel (HRB 59); M6 in 2.4 / 2.2 mm"))
for _kind in ("SO", "BSO"):
    for _t, _h, _s, _e, _p, _q, _m in (("M3", 4.22, 1.0, 6.0, (710, 1000), (1245, 1465), 0.55),
                                        ("M4", 7.14, 1.27, 8.0, (1780, 2490), (2575, 3110), 2.0),
                                        ("M5", 7.14, 1.27, 8.0, (1780, 2490), (2575, 3110), 3.6)):
        _PARTS.append(ClinchPart(f"{_kind}-{_t}", "standoff", "hardened steel", _t, _h, _s, _e, _p, None, _q, _m,
                                 "pem-bulletin-so", "SO-3, SO-4 (dimensions) and SO-12 (strengths, for SO)",
                                 "1.5 mm 5052-H34 aluminium / cold-rolled steel"))
PARTS: Dict[str, ClinchPart] = {p.key: p for p in _PARTS}


@dataclass(frozen=True)
class Sheet:
    """A sheet's typical Rockwell B hardness as PEM's handbook (or its stainless sheet) gives it, and the family PEM's
    strength columns use."""
    key: str
    name: str
    family: str                  # aluminium, steel or stainless
    hrb: Tuple[float, float]     # typical (lowest, highest)
    source: str
    where: str


SHEETS: Dict[str, Sheet] = {s.key: s for s in (
    Sheet("5052-h32", "5052-H32 aluminium", "aluminium", (15, 30), "pem-handbook", "HB-6, typical sheet hardness"),
    Sheet("5052-h34", "5052-H34 aluminium", "aluminium", (15, 30), "pem-handbook", "HB-6, typical sheet hardness"),
    Sheet("6061-t6", "6061-T6 aluminium", "aluminium", (50, 55), "pem-handbook", "HB-6, typical sheet hardness"),
    Sheet("cold-rolled-steel", "cold-rolled steel", "steel", (40, 75), "pem-handbook", "HB-6, typical sheet hardness"),
    Sheet("304-annealed", "304 stainless, annealed", "stainless", (80, 92), "pem-tech-sheet-stainless",
          "Table 1: HRB 92 at most under ASTM A240; the handbook gives annealed 304 as HRB 80 and up"),
)}
# sheet_metal.bend knows these materials, so the check can work out a bend allowance itself.
_BEND_MATERIAL = {"5052-h32": "5052", "5052-h34": "5052", "cold-rolled-steel": "mild-steel"}

ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _check(name: str, verdict: str, value: Any, limit: str, rule: str, source: str, detail: str) -> Dict[str, Any]:
    return {"check": name, "verdict": verdict, "value": value, "limit": limit, "rule": rule, "source": source,
            "detail": detail}


def _num(name: str, v: Any, positive: bool = True) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (v <= 0 if positive else v < 0):
        raise ValueError(f"{name} must be a finite number {'above' if positive else 'of at least'} 0, not {v!r}")
    return float(v)


def _part(key: str) -> ClinchPart:
    if key not in PARTS:
        raise ValueError(f"unknown part {key!r}; see cadagent.mechanical.clinch.PARTS or parts_for()")
    return PARTS[key]


def _sheet(key: str) -> Sheet:
    if key not in SHEETS:
        raise ValueError(f"unknown sheet {key!r}; one of {sorted(SHEETS)}")
    return SHEETS[key]


def parts_for(thread: str, sheet: str, thickness_mm: float, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """The listed parts for ``thread`` (``M3`` or PEM's inch code such as ``440`` or ``032``) that clinch into ``sheet``
    of ``thickness_mm``: thick enough, and the sheet's typical hardness at most the part material's limit. Nuts first,
    steel before stainless (the cheaper and more stocked part, research/sheet-metal-joining.md §4)."""
    s, t = _sheet(sheet), _num("thickness_mm", thickness_mm)
    if kind is not None and kind not in ("nut", "stud", "standoff"):
        raise ValueError(f"kind is nut, stud or standoff, not {kind!r}")
    if s.family == "stainless":
        return []
    prof = pp.profile("sheet-metal")
    out = []
    for p in PARTS.values():
        if p.thread != thread or (kind is not None and p.kind != kind) or t + 1e-9 < p.min_sheet_mm:
            continue
        if s.hrb[1] <= prof.verified_rule(CLASSES[p.material]).limit().max + 1e-9:
            out.append(p)
    rank = {"nut": 0, "stud": 1, "standoff": 2}
    return [p.as_dict() for p in sorted(out, key=lambda p: (rank[p.kind], p.material != "hardened steel", p.key))]


def check_placement(part: str, sheet: str, thickness_mm: float, *, sheet_hrb: Optional[float] = None,
                    hole_mm: Optional[float] = None, edge_mm: Optional[float] = None,
                    to_bend_mm: Optional[float] = None, bend_allowance_mm: Optional[float] = None,
                    neighbours: Sequence[Tuple[str, float]] = (), pushout_n: Optional[float] = None,
                    torque_nm: Optional[float] = None, pull_n: Optional[float] = None, factor: float = 1.0,
                    path: Any = None) -> Dict[str, Any]:
    """Check one clinch part in a sheet: ``part`` a key of :data:`PARTS`; ``sheet`` a key of :data:`SHEETS` and its
    ``thickness_mm``; ``sheet_hrb`` the certified hardness, if known (else the alloy's typical range); ``hole_mm`` as
    drawn; ``edge_mm`` from the hole centre to the nearest cut edge; ``to_bend_mm`` from the hole centre to a bend's
    centre line on the flat pattern, with the bend's ``bend_allowance_mm`` (worked out with
    :func:`cadagent.manufacturing.sheet_metal.bend` for 5052 and cold-rolled steel when not given); ``neighbours`` as
    (part key, centre-to-centre mm); and, optionally, the loads on the part, compared with PEM's ratings divided by
    ``factor``."""
    p, s = _part(part), _sheet(sheet)
    t = _num("thickness_mm", thickness_mm)
    f = _num("factor", factor)
    prof = pp.profile("sheet-metal", path)
    checks: List[Dict[str, Any]] = []
    notes: List[str] = []

    # Hardness: the part's material against the sheet.
    rule = prof.verified_rule(CLASSES[p.material])
    top = rule.limit().max
    if s.family == "stainless":
        checks.append(_check("hardness", "fail", f"{s.name}", "a hardened-stainless type (SP, SMPP, FH4, SO4)",
                             "", "pem-bulletin-cl", f"PEM puts only its hardened-stainless types into stainless "
                             f"sheet (CL-18); {p.key} is {p.material} and is not hard enough to clinch it"))
    else:
        lo, hi = (s.hrb if sheet_hrb is None else (_num("sheet_hrb", sheet_hrb),) * 2)
        what = f"HRB {hi:g}" if lo == hi else f"HRB {lo:g}-{hi:g} (typical)"
        if hi <= top + 1e-9:
            v, why = "pass", f"{s.name} at {what} is at most the HRB {top:g} that {p.material} takes"
        elif lo <= top + 1e-9:
            v, why = "warn", (f"{s.name} runs {what}, across the HRB {top:g} limit for {p.material}: read the sheet's "
                              "certificate, or take a harder part")
        else:
            v, why = "fail", f"{s.name} at {what} is harder than the HRB {top:g} that {p.material} takes"
        checks.append(_check("hardness", v, what, f"at most HRB {top:g}", rule.id, rule.source, why))

    # Thickness.
    v = "pass" if t + 1e-9 >= p.min_sheet_mm else "fail"
    checks.append(_check("thickness", v, round(t, 4), f"at least {p.min_sheet_mm:.3f} mm", p.key, p.source,
                         "thick enough for this shank" if v == "pass" else
                         "thinner than this part's minimum sheet: a shorter shank code, if PEM lists one, or a "
                         "thicker sheet"))

    # Hole.
    tol = prof.verified_rule("sm-clinch-hole-tolerance-pem")
    hi_hole = p.hole_mm + tol.limit().max
    if hole_mm is not None:
        h = _num("hole_mm", hole_mm)
        v = "pass" if p.hole_mm - 1e-9 <= h <= hi_hole + 1e-9 else "fail"
        why = ("inside PEM's band; punched or drilled, not chamfered or deburred" if v == "pass" else
               "oversize: the clinch loses its grip" if h > hi_hole else "undersize: the part will not go in")
        checks.append(_check("hole", v, round(h, 4), f"{p.hole_mm:.3f}-{hi_hole:.3f} mm", tol.id, tol.source, why))

    # Edge distance.
    if edge_mm is not None:
        e = _num("edge_mm", edge_mm)
        v = "pass" if e + 1e-9 >= p.edge_mm else "fail"
        checks.append(_check("edge", v, round(e, 4), f"at least {p.edge_mm:.3f} mm", p.key, p.source,
                             "clear of the edge (PEM's distance holds for one edge only)" if v == "pass" else
                             "too close to the edge: the sheet bulges and the part pushes out"))

    # Bend.
    if to_bend_mm is not None:
        d = _num("to_bend_mm", to_bend_mm)
        if bend_allowance_mm is None:
            if sheet not in _BEND_MATERIAL:
                raise ValueError(f"give bend_allowance_mm: sheet_metal.bend has no rule for {sheet!r}")
            from cadagent.manufacturing import sheet_metal
            ba = sheet_metal.bend(_BEND_MATERIAL[sheet], t, path=path)["allowance_mm"]
        else:
            ba = _num("bend_allowance_mm", bend_allowance_mm)
        r = prof.verified_rule("sm-clinch-to-bend-pem")
        least = r.limit(BA=ba, E=p.edge_mm).min
        v = "pass" if d + 1e-9 >= least else "fail"
        checks.append(_check("bend", v, round(d, 4), f"at least {least:.3f} mm (BA/2 + E, BA {ba:.3f} mm)", r.id,
                             r.source, "the sheet under the part stays flat" if v == "pass" else
                             "inside the bend's reach: the bend distorts the hole, or the part distorts the bend"))
        notes.append("make the hole after bending when it is this close to a bend, and check the press tooling reaches")

    # Neighbours.
    sp = prof.verified_rule("sm-clinch-spacing-pem")
    for i, (other, dist) in enumerate(neighbours):
        q = _part(other)
        c = _num(f"neighbour {i + 1} distance", dist)
        least = max(sp.limit(E=p.edge_mm, hole=q.hole_mm).min, sp.limit(E=q.edge_mm, hole=p.hole_mm).min)
        v = "pass" if c + 1e-9 >= least else "fail"
        checks.append(_check(f"spacing to {q.key}", v, round(c, 4), f"at least {least:.3f} mm", sp.id, sp.source,
                             "far enough apart" if v == "pass" else
                             "too close: one part's clinch deforms the other's hole"))

    # Loads, against PEM's averages in the matching test sheet.
    col = {"aluminium": 0, "steel": 1}.get(s.family)
    for name, load, rating, unit in (("push-out", pushout_n, p.pushout_n, "N"),
                                     ("torque", torque_nm, p.torque_out_nm, "N m"),
                                     ("pull-through", pull_n, p.pull_through_n, "N")):
        if load is None:
            continue
        x = _num(f"{name} load", load)
        if name == "torque" and p.screw_torque_nm is not None:
            rating = (p.screw_torque_nm, p.screw_torque_nm)
        if rating is None or col is None:
            checks.append(_check(name, "fail", x, "no rating", p.key, p.source,
                                 f"PEM gives no {name} rating for {p.key} in {s.family} sheet"))
            continue
        v = "pass" if rating[col] >= x * f else "fail"
        checks.append(_check(name, v, x, f"at most {rating[col] / f:.3f} {unit} ({rating[col]:g} / factor {f:g})",
                             p.key, p.source, f"PEM's average in {p.test_sheet}"))

    if t + 1e-9 >= prof.verified_rule("sm-clinch-punch-side-pem").limit().min:
        notes.append("press in from the punch side of a punched hole (PEM requires it from 2.29 mm)")
    notes.append("install after plating or anodising, and before paint or powder coat")
    verdict = max((c["verdict"] for c in checks), key=ORDER.get)
    return {"verdict": verdict, "part": p.as_dict(), "sheet": asdict(s), "thickness_mm": t, "checks": checks,
            "notes": notes,
            "limits": ["strengths are PEM's averages in its own test sheets, not allowables; test in the real part",
                       "edge distances hold for one edge only; a corner or two edges needs more",
                       "a shop's own per-part limits (such as SendCutSend's K, N and M) are not checked here",
                       "a check of the published rules, not proof that the part holds"]}
