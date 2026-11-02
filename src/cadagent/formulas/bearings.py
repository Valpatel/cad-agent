"""Rolling bearings: rating life (ISO 281), equivalent loads, static safety (ISO 76), duty cycles, oscillating joints
and the Hertz contact under the most loaded ball.

Units: newtons for loads and ratings, millions of revolutions (or of oscillations) for lives, hours, r/min, degrees
for oscillation amplitudes; the contact functions take metres and pascals like the rest of ``cadagent.formulas``.

Every life here is the **basic rating life**: the life that 90 % of a large group of identical bearings reach or
exceed under the load, before the first spall, made of standard bearing steel and run with ordinary lubrication.
It is a statistic for a population, not a promise for one part. It does not include lubrication, contamination or
the fatigue load limit (the makers' modified lives, such as SKF's aSKF, do). It does not cover wear, corrosion,
seal failure, grease life, a seat that lets the ring creep, or false brinelling. A calculated life is not proof that
a bearing survives. Test the joint. :mod:`cadagent.mechanical.bearings` holds catalogue bearings and checks a whole
bearing with these functions.

Sources: ISO 281:2007 and ISO 76:2006 as SKF's catalogue applies them (SKF, Rolling bearings, 17000/1 EN, 2018-10),
the oscillation factors as Menck and Stammler (2024) review them, and the exact Hertz point contact (Johnson,
Contact Mechanics; Hamrock and Brewe for the approximations it is tested against).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from cadagent.formulas._registry import cite, formula

_L10 = ("basic rating life (90 % reliability) of a bearing of standard bearing steel under ordinary lubrication; "
        "a population statistic, not a promise for one bearing; no lubrication, contamination or fatigue-limit "
        "factors (aSKF, aISO); no wear, false brinelling, grease or seal life")
_LOAD = ("the load constant in magnitude and direction over the life, or replaced by its equivalent (see "
         "duty_cycle_load); the makers rate a deep-groove ball bearing with the ratio C/P above about 2 "
         "(P <= 0.5 C, SKF's range for a robust life); above it the static safety governs")
_OSC = ("the Harris factor converts the distance travelled into revolutions; it ignores that a small swing loads only "
        "part of the raceway (the Rumbarger effect, below the critical amplitude) and the moving ring's uneven load "
        "zone (the Houpert effect); SKF's conversion is not valid below an amplitude of 10 degrees; at small "
        "amplitudes wear and false brinelling, not fatigue, usually end the bearing's life (check x/2b)")
_HERTZ = ("two elastic bodies in point contact, smooth, frictionless, the contact small against both bodies' radii "
          "(Hertz); linear elastic, so above the yield of the steel (about 4000-4600 MPa peak in bearing steel, where "
          "ISO 76 sets C0) the real contact deforms permanently")

# SKF 17000/1 EN, Table 9, p. 257: deep groove ball bearings, single row. Columns: f0 Fa / C0, then e, X, Y for each
# clearance. "Intermediate values can be obtained by linear interpolation." ISO 281:2007 Table 3 gives the Normal
# columns with the same f0 Fa / C0 steps.
DEEP_GROOVE_TABLE: Dict[str, Tuple[Tuple[float, float, float, float], ...]] = {
    "normal": ((0.172, 0.19, 0.56, 2.30), (0.345, 0.22, 0.56, 1.99), (0.689, 0.26, 0.56, 1.71),
               (1.03, 0.28, 0.56, 1.55), (1.38, 0.30, 0.56, 1.45), (2.07, 0.34, 0.56, 1.31),
               (3.45, 0.38, 0.56, 1.15), (5.17, 0.42, 0.56, 1.04), (6.89, 0.44, 0.56, 1.00)),
    "c3": ((0.172, 0.29, 0.46, 1.88), (0.345, 0.32, 0.46, 1.71), (0.689, 0.36, 0.46, 1.52),
           (1.03, 0.38, 0.46, 1.41), (1.38, 0.40, 0.46, 1.34), (2.07, 0.44, 0.46, 1.23),
           (3.45, 0.49, 0.46, 1.10), (5.17, 0.54, 0.46, 1.01), (6.89, 0.54, 0.46, 1.00)),
    "c4": ((0.172, 0.38, 0.44, 1.47), (0.345, 0.40, 0.44, 1.40), (0.689, 0.43, 0.44, 1.30),
           (1.03, 0.46, 0.44, 1.23), (1.38, 0.47, 0.44, 1.19), (2.07, 0.50, 0.44, 1.12),
           (3.45, 0.55, 0.44, 1.02), (5.17, 0.56, 0.44, 1.00), (6.89, 0.56, 0.44, 1.00)),
}
CLEARANCES = tuple(DEEP_GROOVE_TABLE)

# SKF 17000/1 EN, Table 3, p. 90 ("values in accordance with ISO 281"): reliability % -> a1.
RELIABILITY_TABLE = {90.0: 1.0, 95.0: 0.64, 96.0: 0.55, 97.0: 0.47, 98.0: 0.37, 99.0: 0.25}
# ISO 281:2007's Weibull slope for the lives of a group of bearings (Table A1 of Menck and Stammler 2024 lists it:
# 10/9 for point contact, 9/8 for line contact).
WEIBULL_SLOPE = {"ball": 10.0 / 9.0, "roller": 9.0 / 8.0}
STEEL = {"modulus": 208e9, "poisson": 0.3}          # bearing steel as NSK's Technical Report E728h takes it (p. 116)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _positive(name: str, v: Any, strict: bool = True) -> float:
    if not (_num(v) and (v > 0 if strict else v >= 0)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} 0, not {v!r}")
    return float(v)


def life_exponent(roller: bool) -> float:
    """The exponent p of the life equation: 3 for ball bearings (point contact), 10/3 for roller bearings."""
    return 10.0 / 3.0 if roller else 3.0


# ----------------------------------------------------------------------------- rating life

@formula(units={"dynamic_rating": "N (C, the maker's basic dynamic load rating)",
                "load": "N (P, the equivalent dynamic load)", "roller": "bool (True: roller bearing, p = 10/3)"},
         returns="basic rating life L10, millions of revolutions",
         limits=(_L10, _LOAD),
         source=cite("skf-2018", "Section B.3, Basic rating life, p. 89: L10 = (C / P)^p, p = 3 ball, 10/3 roller "
                     "(ISO 281)"))
def rating_life(dynamic_rating: float, load: float, roller: bool = False) -> float:
    """Basic rating life in millions of revolutions: L10 = (C / P)^p, with p = 3 for ball and 10/3 for roller
    bearings."""
    return (_positive("dynamic_rating", dynamic_rating) / _positive("load", load)) ** life_exponent(bool(roller))


@formula(units={"life": "millions of revolutions (or of oscillations)", "speed": "r/min (or oscillations a minute)"},
         returns="the same life in operating hours",
         limits=("a constant speed (or rate of oscillation); for a varying one, convert each block of a duty cycle",),
         source=cite("skf-2018", "Section B.3, Basic rating life, p. 89: L10h = 10^6 / (60 n) L10"))
def life_hours(life: float, speed: float) -> float:
    """A life in millions of revolutions as operating hours at a speed: L10h = 10^6 L10 / (60 n)."""
    return _positive("life", life, strict=False) * 1e6 / (60.0 * _positive("speed", speed))


@formula(units={"load": "N (P)", "life": "millions of revolutions required", "roller": "bool"},
         returns="the basic dynamic load rating C needed, N",
         limits=(_L10, _LOAD),
         source=cite("skf-2018", "Section B.3, Basic rating life, p. 89, solved for C: C = P L10^(1/p)"))
def required_dynamic_rating(load: float, life: float, roller: bool = False) -> float:
    """The dynamic load rating a bearing needs for a life: C = P L10^(1/p), the life equation solved for C."""
    return _positive("load", load) * _positive("life", life) ** (1.0 / life_exponent(bool(roller)))


@formula(units={"reliability": "% (90 to 99.95)"},
         returns="life adjustment factor a1 for reliability, dimensionless (1 at 90 %)",
         limits=("ISO 281 covers 90 to 99.95 %; a1 multiplies the basic life L10 into Ln (n = 100 - reliability)",
                 "SKF's tabulated values (90, 95 to 99 %) are returned exactly; between and beyond them the Weibull "
                 "form a1 = 0.95 (ln(100/R) / ln(100/90))^(2/3) + 0.05, which rounds to every tabulated value "
                 "(tested), interpolates",
                 "for loads below the fatigue load limit Pu, a1 matters less (SKF p. 90)"),
         source=cite("skf-2018", "Section B.3, Table 3 (Values for life adjustment factor a1), p. 90, in accordance "
                     "with ISO 281"))
def reliability_factor(reliability: float) -> float:
    """Life adjustment factor a1 for a reliability other than 90 %: SKF's (ISO 281) table where it lists the value,
    else the Weibull form a1 = 0.95 (ln(100 / R) / ln(100 / 90))^(2/3) + 0.05, which reproduces that table."""
    if not (_num(reliability) and 90.0 <= reliability <= 99.95):
        raise ValueError(f"reliability must be a percentage from 90 to 99.95 (ISO 281's range), not {reliability!r}")
    r = float(reliability)
    if r in RELIABILITY_TABLE:
        return RELIABILITY_TABLE[r]
    return 0.95 * (math.log(100.0 / r) / math.log(100.0 / 90.0)) ** (2.0 / 3.0) + 0.05


# ----------------------------------------------------------------------------- equivalent loads

@formula(units={"radial": "N (Fr)", "axial": "N (Fa)", "x": "radial factor X", "y": "axial factor Y"},
         returns="equivalent dynamic load P = X Fr + Y Fa, N",
         limits=("X and Y from the bearing type's table (deep_groove_load for deep-groove ball bearings); loads "
                 "constant in magnitude and direction",),
         source=cite("skf-2018", "Section B.3, Calculating equivalent dynamic bearing load, p. 91: P = X Fr + Y Fa"))
def equivalent_load(radial: float, axial: float, x: float, y: float) -> float:
    """Equivalent dynamic bearing load P = X Fr + Y Fa, for factors X and Y read from the bearing type's table."""
    return (_positive("x", x, strict=False) * _positive("radial", radial, strict=False)
            + _positive("y", y, strict=False) * _positive("axial", axial, strict=False))


@formula(units={"relative_axial": "f0 Fa / C0, dimensionless", "clearance": "'normal', 'c3' or 'c4' (operating)"},
         returns="{e, x, y, clamped}: the limit e of Fa / Fr and the factors X and Y; clamped is True outside the "
                 "table",
         limits=("single-row deep-groove ball bearings; the clearance is the operating one, which an interference "
                 "fit reduces from the catalogue class",
                 "linear interpolation between the table's rows, as SKF says; outside 0.172 to 6.89 the end row is used "
                 "and flagged (clamped)"),
         source=cite("skf-2018", "Section 1 (Deep groove ball bearings), Table 9 (Calculation factors for deep groove "
                     "ball bearings), p. 257; ISO 281:2007 Table 3 for normal clearance"))
def deep_groove_factors(relative_axial: float, clearance: str = "normal") -> Dict[str, Any]:
    """e, X and Y of a single-row deep-groove ball bearing for a relative axial load f0 Fa / C0, by linear
    interpolation in SKF's Table 9 (ISO 281 Table 3 for normal clearance)."""
    if clearance not in DEEP_GROOVE_TABLE:
        raise ValueError(f"clearance must be one of {CLEARANCES}, not {clearance!r}")
    q = _positive("relative_axial", relative_axial, strict=False)
    rows = DEEP_GROOVE_TABLE[clearance]
    if q <= rows[0][0] or q >= rows[-1][0]:
        r = rows[0] if q <= rows[0][0] else rows[-1]
        return {"e": r[1], "x": r[2], "y": r[3], "clamped": q != r[0]}
    for lo, hi in zip(rows, rows[1:]):
        if lo[0] <= q <= hi[0]:
            t = (q - lo[0]) / (hi[0] - lo[0])
            return {"e": lo[1] + t * (hi[1] - lo[1]), "x": lo[2] + t * (hi[2] - lo[2]),
                    "y": lo[3] + t * (hi[3] - lo[3]), "clamped": False}
    raise AssertionError("unreachable")


@formula(units={"radial": "N (Fr)", "axial": "N (Fa)", "static_rating": "N (C0)",
                "f0": "the maker's calculation factor f0", "clearance": "'normal', 'c3' or 'c4'"},
         returns="{load (P, N), x, y, e, relative_axial, axial_counts, clamped}",
         limits=("single-row deep-groove ball bearing, single or in tandem; Fa / Fr <= e gives P = Fr",
                 "pure axial load at most 0.5 C0, and 0.25 C0 for small (d <= 12 mm) and light-series bearings "
                 "(SKF p. 254); the check holds the axial load to that"),
         source=cite("skf-2018", "Section 1 (Deep groove ball bearings), Loads, p. 254 (Fa / Fr <= e: P = Fr; "
                     "Fa / Fr > e: P = X Fr + Y Fa) and Table 9, p. 257"))
def deep_groove_load(radial: float, axial: float, static_rating: float, f0: float,
                     clearance: str = "normal") -> Dict[str, Any]:
    """Equivalent dynamic load of a single-row deep-groove ball bearing: P = Fr while Fa / Fr <= e, otherwise
    P = X Fr + Y Fa, with e, X and Y from f0 Fa / C0 (SKF Table 9)."""
    fr, fa = _positive("radial", radial, strict=False), _positive("axial", axial, strict=False)
    if fr == 0 and fa == 0:
        raise ValueError("a bearing needs a radial or an axial load")
    q = _positive("f0", f0) * fa / _positive("static_rating", static_rating)
    f = deep_groove_factors(q, clearance)
    counts = fa > 0 and (fr == 0 or fa / fr > f["e"])
    load = equivalent_load(fr, fa, f["x"], f["y"]) if counts else fr
    return {"load": load, "x": f["x"] if counts else 1.0, "y": f["y"] if counts else 0.0, "e": f["e"],
            "relative_axial": q, "axial_counts": counts, "clamped": f["clamped"] and counts}


@formula(units={"radial": "N (Fr)", "axial": "N (Fa)", "x0": "static radial factor (0.6 for radial ball bearings)",
                "y0": "static axial factor (0.5 for radial ball bearings)"},
         returns="equivalent static load P0, N (never below Fr)",
         limits=("X0 = 0.6, Y0 = 0.5 hold for single-row deep-groove ball bearings, single or in tandem (ISO 76); "
                 "a pair back-to-back or face-to-face takes P0 = Fr + 1.7 Fa (SKF p. 254)",
                 "the peak load the bearing sees standing or turning slowly, including shock"),
         source=cite("skf-2018", "Section 1 (Deep groove ball bearings), Loads, p. 254: P0 = 0.6 Fr + 0.5 Fa, "
                     "P0 < Fr -> P0 = Fr (ISO 76)"))
def static_equivalent_load(radial: float, axial: float, x0: float = 0.6, y0: float = 0.5) -> float:
    """Equivalent static load of a radial bearing: P0 = X0 Fr + Y0 Fa, and never less than Fr."""
    fr, fa = _positive("radial", radial, strict=False), _positive("axial", axial, strict=False)
    return max(fr, _positive("x0", x0, strict=False) * fr + _positive("y0", y0, strict=False) * fa)


@formula(units={"static_rating": "N (C0)", "static_load": "N (P0)"},
         returns="static safety factor s0 = C0 / P0, dimensionless",
         limits=("C0 is the load at which the most loaded contact reaches 4200 MPa in a ball bearing (4000 MPa in a "
                 "roller bearing), a permanent dent of about 1/10 000 of the rolling element's diameter (ISO 76); "
                 "s0 below 1 dents the raceways, which a turning bearing then feels as noise and roughness",
                 "compare with SKF's guideline values (s0 from 0.4 to 2 for ball bearings, Table 7 p. 106)"),
         source=cite("skf-2018", "Section B.3, Guideline values for static safety factor s0, p. 106: s0 = C0 / P0"))
def static_safety(static_rating: float, static_load: float) -> float:
    """Static safety factor s0 = C0 / P0 (ISO 76)."""
    return _positive("static_rating", static_rating) / _positive("static_load", static_load)


@formula(units={"factor": "f0 (ISO 76's, the maker's calculation factor)", "balls": "count per row",
                "ball_diameter": "m", "contact_angle": "rad (0 for a deep-groove ball bearing)", "rows": "count"},
         returns="basic static radial load rating C0, N",
         limits=("radial ball bearings; f0 depends on Dw cos(alpha) / Dpw and the groove radii (ISO 76's table); "
                 "with the maker's f0 it estimates C0 from the internal geometry, or the geometry from C0",),
         source=cite("iso76", "Section 5 (basic static radial load rating of radial ball bearings): "
                     "C0r = f0 i Z Dw^2 cos(alpha)"))
def static_rating_iso76(factor: float, balls: int, ball_diameter: float, contact_angle: float = 0.0,
                        rows: int = 1) -> float:
    """Basic static radial rating of a radial ball bearing from its internal geometry: C0 = f0 i Z Dw^2 cos(alpha),
    with Dw in mm and f0 in N/mm^2 as ISO 76 states it."""
    if not (isinstance(balls, int) and balls > 0 and isinstance(rows, int) and rows > 0):
        raise ValueError(f"balls and rows must be whole counts above 0, not {balls!r} and {rows!r}")
    dw_mm = _positive("ball_diameter", ball_diameter) * 1e3
    return _positive("factor", factor) * rows * balls * dw_mm ** 2 * math.cos(contact_angle)


# ----------------------------------------------------------------------------- duty cycles

@formula(units={"lives": "millions of revolutions, one per block", "fractions": "share of the revolutions in each "
                                                                                "block (summing to 1)"},
         returns="the life under the whole duty cycle, millions of revolutions",
         limits=("linear damage accumulation (Palmgren-Miner): the order of the blocks does not matter, and a block "
                 "below the fatigue load limit still uses up life (the basic L10 has no limit)",),
         source=cite("skf-2018", "Section B.3, Calculating bearing life with variable operating conditions, p. 90: "
                     "L = 1 / (U1 / L1 + U2 / L2 + ...)"))
def miner_life(lives: Sequence[float], fractions: Sequence[float]) -> float:
    """Life under a duty cycle of constant-load blocks (Palmgren-Miner): L = 1 / sum(U_i / L_i), with U_i each
    block's share of the revolutions."""
    u = _fractions(fractions)
    if len(lives) != len(u):
        raise ValueError(f"{len(lives)} lives for {len(u)} fractions")
    return 1.0 / sum(ui / _positive("life", li) for ui, li in zip(u, lives))


@formula(units={"loads": "N, one equivalent load P per block", "fractions": "share of the revolutions in each block "
                                                                           "(summing to 1)",
                "roller": "bool"},
         returns="equivalent mean load of the duty cycle, N",
         limits=("linear damage accumulation, so (C / Pm)^p equals miner_life over the blocks' lives exactly "
                 "(tested); fractions by revolutions: for blocks by time at different speeds, use "
                 "revolution_fractions first",),
         source=cite("skf-2018", "Section B.3, Calculating bearing life with variable operating conditions, p. 90 "
                     "(the same sum written as one load)"))
def duty_cycle_load(loads: Sequence[float], fractions: Sequence[float], roller: bool = False) -> float:
    """The constant load that uses up a bearing as fast as a duty cycle does: Pm = (sum U_i P_i^p)^(1/p), the
    cubic mean for ball bearings."""
    u = _fractions(fractions)
    if len(loads) != len(u):
        raise ValueError(f"{len(loads)} loads for {len(u)} fractions")
    p = life_exponent(bool(roller))
    return sum(ui * _positive("load", pi, strict=False) ** p for ui, pi in zip(u, loads)) ** (1.0 / p)


@formula(units={"times": "share of the time in each block", "speeds": "r/min in each block"},
         returns="each block's share of the revolutions",
         limits=("constant speed within a block",),
         source=cite("skf-2018", "Section B.3, Calculating bearing life with variable operating conditions, p. 90 "
                     "(U is a share of the revolutions: N1 / N)"))
def revolution_fractions(times: Sequence[float], speeds: Sequence[float]) -> List[float]:
    """Each block's share of the revolutions from its share of the time and its speed: U_i = t_i n_i / sum t n."""
    if len(times) != len(speeds) or not times:
        raise ValueError("give one speed for each time share, and at least one")
    revs = [_positive("time", t, strict=False) * _positive("speed", n, strict=False) for t, n in zip(times, speeds)]
    if sum(revs) <= 0:
        raise ValueError("the duty cycle turns no revolutions")
    return [r / sum(revs) for r in revs]


@formula(units={"low": "N (Fmin)", "high": "N (Fmax)"},
         returns="mean load of a load that varies linearly between two values, N",
         limits=("a load constant in direction, varying steadily between its least and its most at a steady speed",),
         source=cite("skf-2018", "Section B.3, Mean load within a duty interval, p. 92: Fm = (Fmin + 2 Fmax) / 3"))
def varying_load_mean(low: float, high: float) -> float:
    """Mean load of a load that varies steadily between Fmin and Fmax: Fm = (Fmin + 2 Fmax) / 3."""
    lo, hi = _positive("low", low, strict=False), _positive("high", high, strict=False)
    if lo > hi:
        raise ValueError(f"low ({lo}) must not be above high ({hi})")
    return (lo + 2.0 * hi) / 3.0


def _fractions(fractions: Sequence[float]) -> List[float]:
    u = [_positive("fraction", f, strict=False) for f in fractions]
    if not u or abs(sum(u) - 1.0) > 1e-6:
        raise ValueError(f"the fractions must sum to 1, not {sum(u) if u else 0!r}")
    return u


# ----------------------------------------------------------------------------- oscillating bearings

@formula(units={"amplitude": "degrees (theta: from the centre of the swing to one end; a swing from -30 to +30 is "
                             "30)"},
         returns="Harris oscillation factor a_osc = 90 / theta: millions of oscillations per million revolutions",
         limits=(_OSC,),
         source=cite("menck-2024", "Section 2.1.1 (Harris: traveled distance), Eq. (3); SKF 17000/1 EN Table 4, "
                     "p. 91 gives the same 180 / (2 gamma), not valid below 10 degrees"))
def harris_factor(amplitude: float) -> float:
    """Oscillations per revolution of equal fatigue: a_osc = 90 / theta, since one oscillation of amplitude theta
    travels 4 theta (Harris; SKF's 180 / (2 gamma))."""
    return 90.0 / _positive("amplitude", amplitude)


@formula(units={"balls": "count per row (Z)", "gamma": "Dw cos(alpha) / dm", "raceway": "'inner' or 'outer'"},
         returns="critical amplitude theta_crit, degrees: the swing that rolls an element on to where its neighbour "
                 "started",
         limits=("rigid rings; the rolling elements roll without slip; the outer raceway's angle is the larger, so it "
                 "is the cautious one for the whole bearing",),
         source=cite("menck-2024", "Section 2.1.2 (Rumbarger: partially loaded volume), Eq. (4): "
                     "theta_crit = 360 / (Z (1 +/- gamma)), + inner, - outer"))
def critical_amplitude(balls: int, gamma: float, raceway: str = "outer") -> float:
    """Critical oscillation amplitude theta_crit = 360 / (Z (1 + gamma)) on the inner raceway and 360 / (Z (1 - gamma))
    on the outer: below it, parts of the raceway are never rolled over."""
    if not (isinstance(balls, int) and balls > 1):
        raise ValueError(f"balls must be a whole count above 1, not {balls!r}")
    if not (_num(gamma) and 0 < gamma < 1):
        raise ValueError(f"gamma (Dw cos(alpha) / dm) must lie between 0 and 1, not {gamma!r}")
    if raceway not in ("inner", "outer"):
        raise ValueError(f"raceway must be 'inner' or 'outer', not {raceway!r}")
    return 360.0 / (balls * (1.0 + gamma if raceway == "inner" else 1.0 - gamma))


@formula(units={"amplitude": "degrees (theta)", "critical": "degrees (theta_crit, see critical_amplitude)",
                "roller": "bool (Weibull slope e: 10/9 ball, 9/8 roller)"},
         returns="Rumbarger oscillation factor a_osc, millions of oscillations per million revolutions",
         limits=(_OSC, "Menck and Stammler's corrected form, with ISO 281's Weibull slopes; equals the Harris factor "
                       "from the critical amplitude up"),
         source=cite("menck-2024", "Section 2.1.2, Eq. (5): a = (theta / theta_crit)^(1 - 1/e) a_Harris below "
                     "theta_crit; Table A1 for e"))
def rumbarger_factor(amplitude: float, critical: float, roller: bool = False) -> float:
    """Oscillation factor with the Rumbarger effect: below the critical amplitude only part of the raceway is loaded,
    but more often, which shortens the life: a = (theta / theta_crit)^(1 - 1/e) 90 / theta."""
    theta, crit = _positive("amplitude", amplitude), _positive("critical", critical)
    e = WEIBULL_SLOPE["roller" if roller else "ball"]
    return (theta / crit) ** (1.0 - 1.0 / e) * harris_factor(theta) if theta < crit else harris_factor(theta)


@formula(units={"amplitude": "degrees (theta, the ring's swing from centre to one end)",
                "pitch_diameter": "m (dm)", "ball_diameter": "m (Dw)", "raceway": "'inner' or 'outer'"},
         returns="x: the arc each contact rolls over the raceway in one stroke from the centre to an end, m",
         limits=("the inner ring swings and the outer stands (or the reverse, on the outer raceway); rolling without "
                 "slip; deep-groove geometry (contact angle 0)",),
         source=cite("menck-2024", "Section 4.1, footnote 42: the rolling elements move theta_c = 0.5 theta_i (1 - "
                     "gamma) against the stationary ring, theta_i - theta_c against the moving one"))
def rolling_travel(amplitude: float, pitch_diameter: float, ball_diameter: float, raceway: str = "inner") -> float:
    """How far a contact rolls over the raceway while the moving ring swings theta: on the moving (inner) ring
    0.5 theta (1 + gamma) of its raceway radius dm (1 - gamma) / 2, on the stationary (outer) ring 0.5 theta (1 - gamma)
    of dm (1 + gamma) / 2; both come to theta dm (1 - gamma^2) / 4. Theta is the amplitude, centre to one end, so
    this is the roll from the swing's centre to one end: over a full stroke the contact travels 2 x. Wear studies
    that quote x / 2b over the full stroke give twice this ratio."""
    th = math.radians(_positive("amplitude", amplitude))
    dm, dw = _positive("pitch_diameter", pitch_diameter), _positive("ball_diameter", ball_diameter)
    g = dw / dm
    if not g < 1:
        raise ValueError("the ball must be smaller than the pitch diameter")
    if raceway not in ("inner", "outer"):
        raise ValueError(f"raceway must be 'inner' or 'outer', not {raceway!r}")
    return th * dm * (1.0 - g * g) / 4.0


# ----------------------------------------------------------------------------- the most loaded ball's contact

@formula(units={"radial": "N (Fr)", "balls": "count (Z)", "contact_angle": "rad"},
         returns="load on the most loaded ball, N",
         limits=("a single-row radial ball bearing under pure radial load with a small operating clearance: 4.37 / Z "
                 "for zero clearance, 5 / Z (Stribeck) as the practical value; ISO 76 derives C0 with it",),
         source=cite("nsk-e728", "Section 5.2 (Eqs. 4 and 7: 4.37 Fr / Z at zero clearance) and Section 5.4 (Eq. 6: "
                     "Qmax = 5 Fr / Z)"))
def stribeck_ball_load(radial: float, balls: int, contact_angle: float = 0.0) -> float:
    """The most loaded ball's share of a radial load: Qmax = 5 Fr / (Z cos(alpha)) (Stribeck)."""
    if not (isinstance(balls, int) and balls > 0):
        raise ValueError(f"balls must be a whole count above 0, not {balls!r}")
    return 5.0 * _positive("radial", radial, strict=False) / (balls * math.cos(contact_angle))


def _agm_elliptic(m: float) -> Tuple[float, float]:
    """Complete elliptic integrals K(m) and E(m) of the parameter m = e^2, by the arithmetic-geometric mean."""
    a, b, c2 = 1.0, math.sqrt(1.0 - m), m
    s, power = 0.5 * c2, 0.5
    for _ in range(40):
        c = 0.5 * (a - b)
        a, b = 0.5 * (a + b), math.sqrt(a * b)
        power *= 2.0
        s += power * c * c
        if abs(c) < 1e-17:
            break
    k = math.pi / (2.0 * a)
    return k, k * (1.0 - s)


@formula(units={"load": "N", "rx": "m (equivalent radius in the rolling direction, 1/Rx = 1/r1x + 1/r2x)",
                "ry": "m (across it; Ry >= Rx)", "modulus": "Pa (both bodies)", "poisson": "ratio (both bodies)"},
         returns="{a (semi-axis across, m), b (semi-axis along the rolling, m), p_max (Pa), k = a / b, "
                 "ellipticity integral E}",
         limits=(_HERTZ, "both bodies of one material; a conforming groove (Ry > Rx) gives a long narrow ellipse "
                         "across the rolling direction"),
         source=cite("johnson", "Chapter 4 (Normal contact of elastic solids: Hertz theory): the ellipse's "
                     "eccentricity from the curvature ratio through the complete elliptic integrals K and E; the "
                     "semi-axes in the form of Hamrock and Brewe (1983)"))
def hertz_point_contact(load: float, rx: float, ry: float, modulus: float = STEEL["modulus"],
                        poisson: float = STEEL["poisson"]) -> Dict[str, float]:
    """The contact ellipse and peak pressure of two elastic bodies pressed together, solved exactly: the eccentricity
    from Ry / Rx = (E(e) / (1 - e^2) - K(e)) / (K(e) - E(e)), then a = (6 k^2 E W R / (pi E'))^(1/3),
    b = a / k and p_max = 3 W / (2 pi a b), with E' = E / (1 - nu^2) for two bodies of one material."""
    w, rx, ry = _positive("load", load), _positive("rx", rx), _positive("ry", ry)
    if ry < rx:
        raise ValueError(f"ry ({ry}) must not be below rx ({rx}): give the rolling direction's radius as rx")
    e_star = _positive("modulus", modulus) / (1.0 - _positive("poisson", poisson, strict=False) ** 2)
    ratio = ry / rx
    if ratio - 1.0 < 1e-12:
        m = 0.0
    else:
        def curvature_ratio(mm: float) -> float:
            kk, ee = _agm_elliptic(mm)
            return (ee / (1.0 - mm) - kk) / (kk - ee)
        lo, hi = 1e-12, 1.0 - 1e-15
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if curvature_ratio(mid) < ratio else (lo, mid)
            if hi - lo < 1e-15:
                break
        m = 0.5 * (lo + hi)
    _k, ee = _agm_elliptic(m)
    k = 1.0 / math.sqrt(1.0 - m)
    r = 1.0 / (1.0 / rx + 1.0 / ry)
    a = (6.0 * k * k * ee * w * r / (math.pi * e_star)) ** (1.0 / 3.0)
    b = a / k
    return {"a": a, "b": b, "p_max": 3.0 * w / (2.0 * math.pi * a * b), "k": k, "ellipticity_integral": ee}


@formula(units={"ball_load": "N (Q)", "ball_diameter": "m (Dw)", "pitch_diameter": "m (dm)",
                "osculation": "groove radius over ball diameter, f (0.52 inner, 0.53 outer are ISO 76's)",
                "raceway": "'inner' or 'outer'", "modulus": "Pa", "poisson": "ratio"},
         returns="hertz_point_contact's result for a ball on a deep-groove raceway, with rx and ry (m)",
         limits=(_HERTZ, "contact angle 0 (a deep-groove ball bearing under radial load)",
                 "the groove's osculation is the maker's internal geometry, rarely published; ISO 76 bases C0 on "
                 "f <= 0.52 inner and 0.53 outer"),
         source=cite("nsk-e728", "Section 5.4 (contact ellipse of ball bearings, Eq. 4: the curvature sum "
                     "1/Dw (4 - 1/f +/- 2 gamma / (1 +/- gamma)))"))
def ball_raceway_contact(ball_load: float, ball_diameter: float, pitch_diameter: float, osculation: float = 0.52,
                         raceway: str = "inner", modulus: float = STEEL["modulus"],
                         poisson: float = STEEL["poisson"]) -> Dict[str, float]:
    """The Hertz contact of a ball in a deep-groove raceway: rolling direction Rx = Dw (1 -/+ gamma) / 2 (inner /
    outer), across it Ry = f Dw / (2 f - 1), solved by hertz_point_contact."""
    dw, dm = _positive("ball_diameter", ball_diameter), _positive("pitch_diameter", pitch_diameter)
    f = _positive("osculation", osculation)
    if not 0.5 < f < 1.0:
        raise ValueError(f"osculation (groove radius over ball diameter) must lie between 0.5 and 1, not {f!r}")
    if raceway not in ("inner", "outer"):
        raise ValueError(f"raceway must be 'inner' or 'outer', not {raceway!r}")
    g = dw / dm
    rx = dw / 2.0 * ((1.0 - g) if raceway == "inner" else (1.0 + g))
    ry = f * dw / (2.0 * f - 1.0)
    return {**hertz_point_contact(ball_load, rx, ry, modulus, poisson), "rx": rx, "ry": ry}
