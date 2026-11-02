"""Blind rivets joining sheet parts: the rivets that makers and a distributor list, with their hole, grip and rated
strength, and one check of a riveted lap joint against the published rules (#283).

    from cadagent.mechanical.rivets import check_joint, rivets_for
    check_joint("pop-AD43", [("5052-h32", 1.6), ("5052-h32", 1.6)], edge_mm=6.35, pitch_mm=9.525,
                thickness_tol_mm=0.1016)
    # verdict pass / warn / fail, each check with its value, limit, rule and source, the joint's strength per pitch
    rivets_for(3.2, 0.118 * 25.4, 0.134 * 25.4)   # the 1/8 in rivets whose grip covers a stack of 3.0-3.4 mm

**What is checked**, each against the rule in ``research/process-profiles.yaml`` it names (the ``sm-rivet-*`` rules):

- the grip: the stack, with its thickness tolerance, inside the rivet's grip band;
- the hole, when given: inside the maker's drill range (an oversize hole loses strength);
- the edge distance: at least 2D (POP, the FAA, NASA nominal; MIL-HDBK-5J's allowables need it), at least 1.5D
  (NASA's minimum), a warning between;
- the pitch: at least 3D in one row (FAA), and 4D, the nominal (NASA) and the FAA's two-row value, else a warning;
- each sheet: t at least 0.18D for the bearing values to hold (MIL-HDBK-5J), and aluminium at least 0.020 in under
  an open-end rivet (POP);
- the metals: rivet body against each sheet (MIL-STD-889C, NASA RP-1228);
- the strength per pitch (:func:`cadagent.formulas.lap_joint`): the rivet's rated shear, the sheet's bearing at the
  joint's e/D, and the tear between the holes, from MIL-HDBK-5J's sheet strengths.

**Limits.** The rivets' strengths are the makers' typical values or the distributor's ratings, not design allowables:
POP says its rivets are not certified for structural aerospace use, and NASA and the FAA keep blind (pop) rivets out
of critical structure. The rivets are taken in shear only (a rivet in tension is not checked, and the FAA says to
avoid it); the bending of a single lap is not modelled; and the sheet strengths are MIL-HDBK-5J's for its tempers
(mild steel stands in as annealed AISI 1025). Nothing here proves a joint holds: test one.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cadagent import formulas as fx
from cadagent.manufacturing import process as pp

IN, LBF, KSI = 25.4, 4.4482216152605, 6.894757293168      # mm per inch, N per lbf, MPa per ksi
FAMILIES = ("aluminium", "steel", "stainless")

# Registry ids (research/references.yaml) of the sources this module reads its numbers from.
SRC = {
    "pop-rivet-catalog": "Emhart Teknologies (Stanley), POP Blind Riveting Systems, P3100 Rev. D (2012): hole, grip "
                         "codes and typical shear and tensile, pp. 14, 33; design guidelines pp. 10-12",
    "marson-rivet-catalog": "Marson (Arconic), Rivets, Rivet Nuts and Installation Tools (2018), p. 4 and the drill "
                            "table: IFI-114 drill ranges",
    "mcmaster-blind-rivets": "McMaster-Carr, blind rivet pages read 2026-11-01: part, grip and listed ratings",
    "mil-hdbk-5j": "MIL-HDBK-5J (2003): sheet Ftu, Fty, Fsu and Fbru, Tables 3.5.1.0(b1), 2.2.1.0(b), 2.7.1.0(b)",
    "mil-std-889c": "MIL-STD-889C (2016), Dissimilar Metals: 5.1.3, 5.2a and Table I",
    "nasa-1228": "R. T. Barrett, NASA RP-1228 Fastener Design Manual (1990), p. 5 (galvanic) and p. 21 (joints)",
}


@dataclass(frozen=True)
class Rivet:
    """One blind rivet as its maker or seller lists it. Inches and lbf as printed; ``rating`` says whether the strength
    is the maker's typical value or a seller's listed rating."""
    key: str
    maker: str
    part: str
    kind: str                    # "open end, dome head" or "multi-grip, dome head"
    body: str                    # aluminium, steel or stainless
    mandrel: str
    diameter_in: float
    hole_in: Tuple[float, float]
    grip_in: Tuple[float, float]
    shear_lbf: float
    tensile_lbf: float
    source: str                  # a key of SRC
    where: str
    rating: str = "typical"

    @property
    def diameter_mm(self) -> float:
        return self.diameter_in * IN

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(diameter_mm=round(self.diameter_mm, 4), hole_mm=[round(x * IN, 4) for x in self.hole_in],
                 grip_mm=[round(x * IN, 4) for x in self.grip_in], shear_n=round(self.shear_lbf * LBF, 1),
                 tensile_n=round(self.tensile_lbf * LBF, 1))
        return d


def _pop(code: str, dia: float, hole: Tuple[float, float], grip: Tuple[float, float], shear: float, tensile: float,
         page: str) -> Rivet:
    return Rivet(f"pop-{code}", "POP (Stanley Engineered Fastening)", code, "open end, dome head", "aluminium",
                 "aluminium", dia, hole, grip, shear, tensile, "pop-rivet-catalog", f"p. {page}, 5052 body, aluminium mandrel")


def _pop_mg(code: str, dia: float, hole: Tuple[float, float], grip: Tuple[float, float], shear: float,
            tensile: float) -> Rivet:
    return Rivet(f"pop-{code}-mg", "POP (Stanley Engineered Fastening)", f"{code} multi-grip", "multi-grip, dome head",
                 "aluminium", "steel", dia, hole, grip, shear, tensile, "pop-rivet-catalog", "p. 33, 5052 body, steel mandrel")


# McMaster-Carr does not print the drill on the rows read; its rivets are IFI-114 parts, so the hole is the IFI drill
# range Marson prints for that diameter.
_IFI_HOLE = {0.125: (0.129, 0.133), 0.1875: (0.192, 0.196)}


def _mc(part: str, body: str, mandrel: str, dia: float, grip: Tuple[float, float], shear: float, tensile: float) -> Rivet:
    return Rivet(f"mcmaster-{part}", "McMaster-Carr", part, "open end, dome head", body, mandrel, dia, _IFI_HOLE[dia],
                 grip, shear, tensile, "mcmaster-blind-rivets", "listed rating; hole from Marson's IFI-114 drill table",
                 rating="listed")


_H3, _H4, _H5, _H6 = (0.097, 0.100), (0.129, 0.133), (0.160, 0.164), (0.192, 0.196)
RIVETS: Dict[str, Rivet] = {r.key: r for r in (
    _pop("AD32", 0.09375, _H3, (0.032, 0.125), 85, 135, "14"),
    _pop("AD34", 0.09375, _H3, (0.126, 0.250), 85, 135, "14"),
    _pop("AD41", 0.125, _H4, (0.032, 0.062), 155, 235, "14"),
    _pop("AD42", 0.125, _H4, (0.063, 0.125), 155, 235, "14"),
    _pop("AD43", 0.125, _H4, (0.126, 0.187), 155, 235, "14"),
    _pop("AD44", 0.125, _H4, (0.188, 0.250), 155, 235, "14"),
    _pop("AD45", 0.125, _H4, (0.251, 0.312), 155, 235, "14"),
    _pop("AD46", 0.125, _H4, (0.313, 0.375), 155, 235, "14"),
    _pop("AD48", 0.125, _H4, (0.376, 0.500), 155, 235, "14"),
    _pop("AD410", 0.125, _H4, (0.501, 0.625), 155, 235, "14"),
    _pop("AD52", 0.15625, _H5, (0.063, 0.125), 225, 350, "14"),
    _pop("AD53", 0.15625, _H5, (0.126, 0.187), 225, 350, "14"),
    _pop("AD54", 0.15625, _H5, (0.188, 0.250), 225, 350, "14"),
    _pop("AD56", 0.15625, _H5, (0.251, 0.375), 225, 350, "14"),
    _pop("AD62", 0.1875, _H6, (0.063, 0.125), 315, 500, "14"),
    _pop("AD64", 0.1875, _H6, (0.126, 0.250), 315, 500, "14"),
    _pop("AD66", 0.1875, _H6, (0.251, 0.375), 315, 500, "14"),
    _pop("AD68", 0.1875, _H6, (0.376, 0.500), 315, 500, "14"),
    _pop_mg("AD41-43", 0.125, (0.129, 0.142), (0.039, 0.187), 150, 220),
    _pop_mg("AD43-45", 0.125, (0.129, 0.142), (0.157, 0.312), 150, 220),
    _pop_mg("AD45-47", 0.125, (0.129, 0.142), (0.251, 0.437), 150, 220),
    _pop_mg("AD62-64", 0.1875, (0.192, 0.205), (0.063, 0.250), 350, 505),
    _pop_mg("AD63-66", 0.1875, (0.192, 0.205), (0.188, 0.375), 350, 505),
    _pop_mg("AD66-68", 0.1875, (0.192, 0.205), (0.251, 0.500), 350, 505),
    _mc("97447A015", "aluminium", "aluminium", 0.125, (0.063, 0.125), 120, 150),
    _mc("97447A020", "aluminium", "aluminium", 0.125, (0.126, 0.187), 120, 150),
    _mc("97447A025", "aluminium", "aluminium", 0.125, (0.188, 0.250), 120, 150),
    _mc("97447A050", "aluminium", "aluminium", 0.1875, (0.126, 0.250), 260, 320),
    _mc("97517A015", "aluminium", "steel", 0.125, (0.063, 0.125), 170, 220),
    _mc("97517A050", "aluminium", "steel", 0.1875, (0.188, 0.250), 380, 500),
    _mc("97525A415", "stainless", "stainless", 0.125, (0.063, 0.125), 420, 530),
    _mc("97525A490", "stainless", "stainless", 0.1875, (0.126, 0.250), 950, 1200),
)}


@dataclass(frozen=True)
class Sheet:
    """A sheet temper's strengths, ksi as MIL-HDBK-5J prints them (Fbru by e/D)."""
    key: str
    name: str
    family: str
    ftu_ksi: float
    fty_ksi: float
    fsu_ksi: float
    fbru_ksi: Dict[float, float]       # {e/D: Fbru}
    table: str
    note: str = ""


SHEETS: Dict[str, Sheet] = {s.key: s for s in (
    Sheet("5052-h32", "5052-H32 aluminium", "aluminium", 31, 23, 19, {1.5: 50, 2.0: 65}, "Table 3.5.1.0(b1), p. 3-220"),
    Sheet("5052-h34", "5052-H34 aluminium", "aluminium", 34, 26, 20, {1.5: 54, 2.0: 71}, "Table 3.5.1.0(b1)"),
    Sheet("mild-steel", "mild steel (as annealed AISI 1025 sheet)", "steel", 55, 36, 35, {2.0: 90}, "Table 2.2.1.0(b)",
          "a stand-in: cold-rolled mild steel sheet is usually stronger, so this errs low"),
    Sheet("304-annealed", "304 stainless, annealed", "stainless", 73, 26, 50, {2.0: 162}, "Table 2.7.1.0(b)",
          "longitudinal Ftu; 75 ksi across the grain"),
)}

ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _check(name: str, verdict: str, value: Any, limit: str, rule: str, source: str, detail: str) -> Dict[str, Any]:
    return {"check": name, "verdict": verdict, "value": value, "limit": limit, "rule": rule, "source": source,
            "detail": detail}


def _limit(prof: pp.Profile, rule_id: str, **env: float) -> pp.Limit:
    return prof.verified_rule(rule_id).limit(**env)


def _num(name: str, v: Any, positive: bool = True) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (v <= 0 if positive else v < 0):
        raise ValueError(f"{name} must be a finite number {'above' if positive else 'of at least'} 0, not {v!r}")
    return float(v)


def rivets_for(diameter_mm: float, grip_min_mm: float, grip_max_mm: Optional[float] = None,
               body: Optional[str] = None) -> List[Dict[str, Any]]:
    """The listed rivets of this nominal diameter (within 0.15 mm, so 3.2 finds 1/8 in) whose grip band covers the
    whole stack from ``grip_min_mm`` to ``grip_max_mm``, cheapest-to-find first (POP, then McMaster-Carr)."""
    d = _num("diameter_mm", diameter_mm)
    lo = _num("grip_min_mm", grip_min_mm)
    hi = lo if grip_max_mm is None else _num("grip_max_mm", grip_max_mm)
    if hi < lo:
        raise ValueError("grip_max_mm is below grip_min_mm")
    if body is not None and body not in FAMILIES:
        raise ValueError(f"body is one of {FAMILIES}, not {body!r}")
    return [r.as_dict() for r in RIVETS.values() if abs(r.diameter_mm - d) <= 0.15
            and (body is None or r.body == body)
            and r.grip_in[0] * IN <= lo + 1e-9 and hi <= r.grip_in[1] * IN + 1e-9]


# Least to most noble, for which way round a pair corrodes (MIL-STD-889C, Table I).
_NOBLE = {"aluminium": 0, "steel": 1, "stainless": 2}


def _galvanic(body: str, sheet: Sheet) -> Tuple[str, str]:
    s = sheet.family
    a = "an" if body[0] in "aeiou" else "a"
    if body == s:
        return "pass", f"{a} {body} rivet in {sheet.name}: the same metal (MIL-STD-889C 5.1.3)"
    if body == "stainless" and s == "aluminium":
        return "warn", ("a stainless rivet in aluminium: acceptable with the faying edges sealed (MIL-STD-889C 5.2a), "
                        "but Table I marks the pair incompatible in marine and industrial air")
    if body == "stainless" and s == "steel":
        return "warn", ("a stainless rivet in carbon steel: acceptable to NASA RP-1228 (p. 5), but MIL-STD-889C Table I "
                        "marks the pair incompatible in marine and industrial air")
    if _NOBLE[body] > _NOBLE[s]:
        return "warn", (f"{a} {body} rivet in {sheet.name}: the sheet is the less noble metal and corrodes around the "
                        "rivet; MIL-STD-889C Table I marks aluminium with carbon steel incompatible in marine and "
                        "industrial air, so seal or coat the joint")
    return "warn", (f"{a} {body} rivet in {sheet.name}: the rivet is the less noble metal, so it corrodes (MIL-STD-889C "
                    "5.1.3 asks for the same or a more noble fastener)")


def _fbru(sheet: Sheet, eod: float) -> Optional[float]:
    """The sheet's Fbru (ksi) at ``eod``: MIL-HDBK-5J's value at e/D 2.0 from there up, linear between its 1.5 and 2.0
    values (1.4.7.1), and None below the lowest e/D it gives (or below 2.0 where it gives only that one)."""
    keys = sorted(sheet.fbru_ksi)
    if eod + 1e-9 < keys[0]:
        return None
    if eod + 1e-9 >= keys[-1]:
        return sheet.fbru_ksi[keys[-1]]
    lo = max(k for k in keys if k <= eod + 1e-9)
    hi = min(k for k in keys if k > eod + 1e-9)
    a, b = sheet.fbru_ksi[lo], sheet.fbru_ksi[hi]
    return a + (b - a) * (eod - lo) / (hi - lo)


def check_joint(rivet: str, sheets: Sequence[Tuple[str, float]], edge_mm: float, pitch_mm: float, *, rows: int = 1,
                row_spacing_mm: Optional[float] = None, hole_mm: Optional[float] = None, thickness_tol_mm: float = 0.0, load_per_pitch_n: Optional[float] = None,
                factor: float = 1.0, path: Any = None) -> Dict[str, Any]:
    """Check a riveted lap joint: ``rivet`` a key of :data:`RIVETS`; ``sheets`` the stack as (key of :data:`SHEETS`,
    thickness in mm), at least two; ``edge_mm`` from the hole centre to the sheet edge; ``pitch_mm`` centre to centre
    along a row; ``rows`` of rivets (one rivet per row in each pitch) and, with two or more, ``row_spacing_mm`` between
    them; ``hole_mm`` as drilled or cut, or None for the
    middle of the maker's range; ``thickness_tol_mm`` each sheet's +/- tolerance; and, optionally, the load one pitch
    of the joint carries, to compare with its strength divided by ``factor``. The stack runs from the factory head to
    the formed (blind) head, so the last sheet is the one the formed head sits on."""
    if rivet not in RIVETS:
        raise ValueError(f"unknown rivet {rivet!r}; see cadagent.mechanical.rivets.RIVETS or rivets_for()")
    r = RIVETS[rivet]
    if len(sheets) < 2:
        raise ValueError("give the stack as at least two (sheet, thickness_mm) pairs")
    stack = []
    for key, t in sheets:
        if key not in SHEETS:
            raise ValueError(f"unknown sheet {key!r}; one of {sorted(SHEETS)}")
        stack.append((SHEETS[key], _num("a sheet thickness", t)))
    e, p = _num("edge_mm", edge_mm), _num("pitch_mm", pitch_mm)
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
        raise ValueError(f"rows must be a whole number of at least 1, not {rows!r}")
    tol = _num("thickness_tol_mm", thickness_tol_mm, positive=False)
    f = _num("factor", factor)
    D = r.diameter_mm
    h_lo, h_hi = (x * IN for x in r.hole_in)
    hole = (h_lo + h_hi) / 2.0 if hole_mm is None else _num("hole_mm", hole_mm)
    prof = pp.profile("sheet-metal", path)
    checks: List[Dict[str, Any]] = []

    # Grip: the stack and its tolerance inside the rivet's band.
    grip = sum(t for _, t in stack)
    g_lo, g_hi = grip - tol * len(stack), grip + tol * len(stack)
    b_lo, b_hi = (x * IN for x in r.grip_in)
    if b_lo - 1e-9 <= g_lo and g_hi <= b_hi + 1e-9:
        v, why = "pass", "the whole stack, with its tolerance, is inside the grip band"
    elif b_lo - 1e-9 <= grip <= b_hi + 1e-9:
        v, why = "warn", "the nominal stack fits but its tolerance runs outside the grip band"
    else:
        v, why = "fail", "the stack is outside the rivet's grip band"
    if v != "pass":
        fits = [x["key"] for x in rivets_for(D, max(g_lo, 1e-6), g_hi, r.body)]
        why += f"; rivets that cover {g_lo:.3f}-{g_hi:.3f} mm: {', '.join(fits) or 'none listed'}"
    checks.append(_check("grip", v, round(grip, 4), f"{b_lo:.3f}-{b_hi:.3f} mm", r.part, r.source, why))

    # Hole.
    if hole_mm is not None:
        v = "pass" if h_lo - 1e-9 <= hole <= h_hi + 1e-9 else "fail"
        why = ("inside the maker's drill range" if v == "pass" else
               "larger than the maker's range: an oversize hole loses strength" if hole > h_hi else
               "smaller than the maker's range: the rivet will not go in")
        checks.append(_check("hole", v, round(hole, 4), f"{h_lo:.3f}-{h_hi:.3f} mm", r.part, r.source, why))

    # Edge distance.
    full = _limit(prof, "sm-rivet-edge-pop", D=D)
    floor = _limit(prof, "sm-rivet-edge-min-nasa", D=D)
    v = "pass" if e + 1e-9 >= full.min else ("warn" if e + 1e-9 >= floor.min else "fail")
    checks.append(_check("edge", v, round(e, 4), f"at least {full.min:.3f} mm (2D); never below {floor.min:.3f} mm "
                         "(1.5D)", f"{full.rule}, {floor.rule}", f"{full.source}, {floor.source}",
                         {"pass": "full strength", "warn": "weaker than at 2D; MIL-HDBK-5J's allowables need 2D",
                          "fail": "below NASA's minimum"}[v]))

    # Pitch.
    least = _limit(prof, "sm-rivet-pitch-faa", D=D)
    nominal = _limit(prof, "sm-rivet-pitch-nasa", D=D)
    double = _limit(prof, "sm-rivet-pitch-double-faa", D=D)
    second = double if rows > 1 else nominal
    if p + 1e-9 < least.min:
        v, why = "fail", "below the FAA's 3D"
    elif rows > 1 and p + 1e-9 < double.value:
        v, why = "warn", "the FAA spaces two or more rows at 4D"
    else:
        v, why = "pass", ("at least 4D, the nominal" if p + 1e-9 >= nominal.value else "between 3D and 4D (one row)")
    checks.append(_check("pitch", v, round(p, 4), f"at least {least.min:.3f} mm (3D); {second.value:.3f} mm (4D) "
                         "nominal", f"{least.rule}, {second.rule}", f"{least.source}, {second.source}", why))
    if rows > 1:
        if row_spacing_mm is None:
            checks.append(_check("row spacing", "warn", None, f"at least {double.value:.3f} mm (4D)", double.rule,
                                 double.source, "not given: the FAA spaces the rows 4D apart too"))
        else:
            g = _num("row_spacing_mm", row_spacing_mm)
            v = "pass" if g + 1e-9 >= double.value else "warn"
            checks.append(_check("row spacing", v, round(g, 4), f"at least {double.value:.3f} mm (4D)", double.rule,
                                 double.source, "the rows are 4D apart" if v == "pass" else
                                 "closer than the FAA's 4D between rows"))

    # Each sheet: t/D, the thinnest aluminium, and the metals.
    thin_al = _limit(prof, "sm-rivet-sheet-min-pop")
    ratio = _limit(prof, "sm-rivet-sheet-ratio-mil5j", D=hole)      # MIL-HDBK-5J's D is the hole (1.4.7)
    for i, (s, t) in enumerate(stack):
        tod = t / hole
        if t + 1e-9 < ratio.min:
            v, why = "warn", "below MIL-HDBK-5J's 0.18: its bearing values do not hold, and thin sheet buckles"
        elif tod + 1e-9 < 0.25:
            v, why = "warn", ("between 0.18 and 0.25: MIL-HDBK-5J's bearing values apply from 0.25 (1.4.7.1), and 8.1.3 "
                              "asks for care with blind rivets in sheet this thin")
        else:
            v, why = "pass", "the bearing values hold"
        checks.append(_check(f"sheet {i + 1} t/D", v, round(tod, 4), "at least 0.18 (0.25 for blind rivets)",
                             ratio.rule, ratio.source, why))
        if s.family == "aluminium" and r.kind.startswith("open end") and i == len(stack) - 1:
            v = "pass" if t + 1e-9 >= thin_al.min else "fail"
            checks.append(_check(f"sheet {i + 1} thickness", v, round(t, 4), f"at least {thin_al.min:.3f} mm",
                                 thin_al.rule, thin_al.source, "POP sets the formed head of an open-end rivet against aluminium from 0.020 in"))
        v, why = _galvanic(r.body, s)
        if r.mandrel != r.body:
            why += (f"; its {r.mandrel} mandrel head stays in the set rivet, a second metal against the sheet that "
                    "MIL-STD-889C 5.1.3 applies to as well")
        checks.append(_check(f"sheet {i + 1} metals", v, f"{r.body} in {s.family}", "the same metal, or a more "
                             "noble fastener", "", "mil-std-889c" if "889C" in why else "nasa-1228", why))

    # Strength per pitch, sheet by sheet; the weakest sheet sets the joint.
    eod = e / hole                     # MIL-HDBK-5J takes e/D with D the hole (1.4.7; Table 9.7.1.1(a))
    per_sheet = []
    for s, t in stack:
        fbru = _fbru(s, eod)
        if fbru is None:
            per_sheet.append({"sheet": s.key, "thickness_mm": t, "bearing_note": f"no Fbru for e/D {eod:.2f}"})
            continue
        j = fx.lap_joint(hole * 1e-3, t * 1e-3, p * 1e-3, s.ftu_ksi * KSI * 1e6, None, fbru * KSI * 1e6, rivets=rows,
                         rivet_shear=r.shear_lbf * LBF)
        per_sheet.append({"sheet": s.key, "thickness_mm": t, "fbru_ksi": round(fbru, 3), "e_over_d": round(eod, 4),
                          **{k: (round(v, 4 if k == "efficiency" else 2) if isinstance(v, float) else v) for k, v in j.items()}})
    strong = [x for x in per_sheet if "strength_n" in x]
    strength = min(strong, key=lambda x: x["strength_n"]) if len(strong) == len(per_sheet) else None
    if load_per_pitch_n is not None:
        load = _num("load_per_pitch_n", load_per_pitch_n)
        if strength is None:
            checks.append(_check("strength", "fail", None, f"{load * f:.1f} N", "", "mil-hdbk-5j",
                                 "no bearing strength at this edge distance, so the joint's strength is unknown"))
        else:
            v = "pass" if strength["strength_n"] >= load * f else "fail"
            checks.append(_check("strength", v, strength["strength_n"], f"at least {load * f:.1f} N (load x factor)",
                                 "", "mil-hdbk-5j", f"set by {strength['mode']} in {strength['sheet']}"))
    verdict = max((c["verdict"] for c in checks), key=ORDER.get)
    return {"verdict": verdict, "rivet": r.as_dict(), "stack_mm": round(grip, 4), "hole_mm": round(hole, 4),
            "e_over_d": round(eod, 4), "checks": checks, "per_sheet": per_sheet,
            "strength_n": None if strength is None else strength["strength_n"],
            "mode": None if strength is None else strength["mode"],
            "efficiency": None if strength is None else strength["efficiency"],
            "limits": [f"the rivet's strength is {'its maker' if r.rating == 'typical' else 'the seller'}'s "
                       f"{r.rating} value, not a design allowable; blind rivets are kept out of critical structure",
                       "rivets in shear only; a single lap's bending and any rivet tension are not modelled",
                       "sheet strengths are MIL-HDBK-5J's for the named tempers; mild steel as annealed AISI 1025; its bearing "
                       "values apply for t/D 0.25-0.50 (1.4.7.1) and are used as printed outside that band",
                       "a check of the published rules, not proof: test a joint"]}
