"""Load-bearing joints in printed parts: the pitfalls found only after printing, as deterministic checks.

    from cadagent.mechanical import printed_joints as pj
    pj.pin_eye("petg-bambu-basic", load_n=400, pin_mm=5, thickness_mm=8, edge_mm=10, width_mm=16)
    pj.pin_eye(..., bushing_mm=8, pivots=True)        # a metal bushing in the eye: the plastic bears on 8 mm
    pj.root_peel("pla-bambu-basic", side_load_n=100, height_mm=20, section=pj.tube(12, 5.5),
                 bolt=pj.through_bolt(5, 0.8, torque_nm=3))   # a threaded rod through the boss: layers closed?
    pj.thread_locking("printed", "anaerobic", transverse_load_n=40, preload_n=500)

Each check returns ``verdict`` (pass, warn or fail, the worst of its ``rows``), ``margin`` (the lowest safety factor
of its stress rows, strength over stress), the rows (check, verdict, value, limit, detail, source), its inputs, the
material's strengths and where they came from, and its ``limits``. A stress row passes at a safety factor of at least
``safety`` (2 by default), warns from 1 to that and fails below 1.

* :func:`pin_eye`: a pin through a printed eye (a lug): bearing on the hole, shear-out to the end, tension across the
  net section, each resolved against the print's layers; whether the geometry fails gradually (bearing) or suddenly;
  with or without a metal bushing; and a pin that turns in plastic.
* :func:`root_peel`: a boss or rib standing on a part and loaded from the side: the bending stress at its root, which
  crosses the layers when the feature is built upright, and how much a through-bolt's preload (a threaded rod and
  nuts) closes it, as tightened and after the plastic relaxes.
* :func:`thread_locking`: a screw that backs out under vibration: transverse slip (Junker), the locking element
  against what the thread is in, and preload held by plastic.

The stresses are the nominal ones on the classic sections (Shigley 10th ed., Sections 3-9 to 3-11 and 8-12), resolved
on the layer plane by the same criterion as :meth:`cadagent.simulation.fea.Study.layer_check`
(:func:`cadagent.simulation.fea.layer_modes`): the opening stress across the layers and the shear along them against
the across-layer allowable, the rest against the in-plane one. Strengths are the datasheet tensile strengths of
:data:`cadagent.mechanical.compliant.allowables.PRINTED` (100 % infill bars, short-term). A check screens a design
before it is printed; it does not rate it. Print the part (or the coupons of
:mod:`cadagent.manufacturing.fit_coupons`) and test it.

Heat-set inserts, compression limiters and the preload a clamped printed joint keeps are cad-agent #230's
(``cadagent.mechanical.inserts``); these checks take the share of preload kept as an input (``retained``).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from cadagent import formulas as fx
from cadagent.mechanical.bosses import FRICTION_BAND, FRICTION_SOURCE
from cadagent.mechanical.compliant.allowables import PRINTED, STATUS
from cadagent.simulation.fea import layer_modes

SAFETY = 2.0          # the default safety factor a stress row must reach to pass: a judgement for short-term datasheet
                      # strengths of 100 % infill bars, not a published value; pass a project's own
RETAINED = 0.5        # the default share of preload plastic in the clamp path keeps for the life of the joint: assumed
                      # (no long-term printed figure was found, 2026-11-01); see root_peel's limits and cad-agent #230
FLAT_DEG = 10.0       # an axis within this of the build direction counts as along it, and within it of the layer
                      # plane as in the plane
# The edge and width (over the hole) from which a printed eye fails in bearing, gradually, rather than suddenly in net
# tension, shear-out or cleavage (Khosravani et al. 2023, Table 2). PLA's are ASTM D5961's advice; printed ABS cleaved
# there and needed 4.5 and 9. ASA (a styrenic like ABS) takes ABS's, and a filament with no test the stricter pair.
BEARING_MODE = {"pla": {"edge_over_d": 3.0, "width_over_d": 6.0}, "abs": {"edge_over_d": 4.5, "width_over_d": 9.0}}
VERDICTS = ("pass", "warn", "fail")

SRC: Dict[str, str] = {
    "shigley-shear": "R. G. Budynas and J. K. Nisbett, Shigley's Mechanical Engineering Design, 10th ed., "
                     "McGraw-Hill, 2015, Section 8-12 (Bolted and Riveted Joints Loaded in Shear: the failure "
                     "modes, bearing F / (t d) and tension on the net section; a metal joint keeps its bolt 1.5 d "
                     "from the edge against tear-out)",
    "lug-shear-out": "the usual lug shear-out convention: the end tears out along two planes from the hole's sides to "
                     "the end, each (e - D/2) long, so tau = P / (2 t (e - D/2)); Shigley 8-12 names the mode and "
                     "gives only a 1.5 d edge rule for metal",
    "shigley-beam": "Shigley 10th ed., Sections 3-9 (uniform axial stress F / A), 3-10 (bending, M c / I) and 3-11 "
                    "(the largest transverse shear: 3 V / 2 A for a rectangle, 4 V / 3 A for a solid circle, 2 V / A "
                    "for a thin tube)",
    "gere": "J. M. Gere and B. J. Goodno, Mechanics of Materials, 8th ed., Cengage, 2013, Section 5.9 (the largest "
            "shear stress in a hollow circular beam, 4 V / 3 A (r2^2 + r2 r1 + r1^2) / (r2^2 + r1^2))",
    "shigley-torque": "Shigley 10th ed., Section 8-8, Eq. (8-27) and Table 8-15 (preload from torque, T = K F d; K "
                      "0.18 lubricated to 0.30 non-plated black steel)",
    "astm-d5961": "ASTM D5961/D5961M, Standard Test Method for Bearing Response of Polymer Matrix Composite Laminates "
                  "(paid; cited by number and title): a width of at least 6 D and an edge distance of at least 3 D "
                  "for the joint to fail in bearing, as Khosravani et al. (2023) quote it",
    "khosravani-2023": "M. R. Khosravani, H. Sadeghian, M. R. Ayatollahi and T. Reinicke, On the Pin-Bearing Strength "
                       "of Additively Manufactured Polymer Parts, Polymers 15 (2023) 1660, doi:10.3390/"
                       "polym15071660 (CC BY), Tables 2 and 3: printed PLA and ABS double-shear coupons (ASTM D5961, "
                       "100 % infill, +/-45 degree raster, 36 mm wide, 5 mm thick, the hole 18 mm from the end). "
                       "PLA failed in net tension at W/D 3 and e/D 1.5 and in bearing from W/D 6 and e/D 3; ABS "
                       "cleaved up to W/D 6 and e/D 3 and failed in bearing from 9 and 4.5. Ultimate bearing "
                       "strength in the bearing mode: PLA 107-184 MPa, ABS 154-189 MPa",
    "fea-layer": "cadagent.simulation.fea.layer_modes, the criterion of Study.layer_check: bond sqrt((<sigma_n> / "
                 "S_z)^2 + (tau_n / S_s)^2) with S_s = S_z / sqrt(3), after Brewer and Lagace (J. Compos. Mater. 22 "
                 "(1988) 1141-1155); bulk von Mises / S_xy",
    "printed": "cadagent.mechanical.compliant.allowables.PRINTED: the lowest datasheet tensile strength any edition "
               "gives, in the layer plane (X-Y) and across the layers (the lower of X-Y and Z); " + STATUS,
    "junker-1969": "G. H. Junker, New criteria for self-loosening of fasteners under vibration, SAE Transactions 78 "
                   "(1969) 314-335, SAE paper 690055: a joint loosens when it slips sideways under the head or nut "
                   "and in the thread, so the clamp must carry the side load by friction",
    "nasa-1228": "R. T. Barrett, Fastener Design Manual, NASA Reference Publication 1228 (March 1990), pp. 6-8 "
                 "(locking methods: a prevailing-torque locknut binds the thread; a jam nut is too unpredictable to "
                 "be reliable, and a locknut is the more practical choice (p. 7); a nylon patch grips a metal mating "
                 "thread; a helical spring lock washer is flat once the bolt is tight, and its locking ability is "
                 "nonexistent): https://ntrs.nasa.gov/citations/19900009424",
    "henkel-243": "Henkel, LOCTITE 243 Technical Data Sheet (April 2025), General Information: not normally "
                  "recommended for use on plastics, particularly thermoplastics, where stress cracking of the "
                  "plastic could result; the other anaerobic threadlockers' sheets say the same: "
                  "https://datasheets.tdx.henkel.com/LOCTITE-243-en_GL.pdf",
    "covestro-friction": FRICTION_SOURCE,
    "covestro-relaxation": "Covestro LLC, Engineering Polymers Part and Mold Design - Thermoplastics, A Design Guide "
                           "(PDF of 2015-10), p. 75, Table 3-7: moulded polycarbonate at 1.2 % strain and 40 degC kept "
                           "0.75 of its stress after a month, 0.67 after a year and 0.59 after six (the figures "
                           "cad-agent #230 uses)",
    "judgement": "no published source: a stated judgement of this module (2026-11-01), to be replaced by a test",
}

LIMITS_COMMON = (
    "nominal stresses on the classic sections, not the peak at a hole's edge or a sharp root: a printed part is notch "
    "sensitive, so model the fillet and run cadagent.simulation.fea's layer_check for the peak",
    "short-term datasheet strengths of 100 % infill test bars: a part with fewer walls or sparse infill round the "
    "joint is weaker, and a held load creeps below them",
    "a screening check for a transversely isotropic print, not a qualification: print the part or a coupon and test "
    "it",
)


# ----------------------------------------------------------------------------- shared pieces

def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _positive(name: str, v: Any, strict: bool = True) -> float:
    if not (_num(v) and (v > 0 if strict else v >= 0)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} 0, not {v!r}")
    return float(v)


def _unit(name: str, v: Sequence[float]) -> np.ndarray:
    a = np.asarray(v, float).reshape(-1)
    size = float(np.linalg.norm(a)) if a.shape == (3,) and np.all(np.isfinite(a)) else 0.0
    if size == 0.0:
        raise ValueError(f"{name} is three finite numbers, not all zero: {v!r}")
    return a / size


def _material(material: str):
    if material not in PRINTED:
        raise ValueError(f"material must be one of {sorted(PRINTED)}, not {material!r}")
    m = PRINTED[material]
    return m, m.strength("along"), m.strength("across")


def _material_info(m, sxy: float, sz: float) -> Dict[str, Any]:
    return {"name": m.name, "strength_xy_mpa": sxy, "strength_z_mpa": sz,
            "shear_mpa": sz / math.sqrt(3.0), "xy_sheet": m.strength_sheet("along").label,
            "z_sheet": m.strength_sheet("across").label, "source": m.source, "status": STATUS}


def _graded(factor: float, safety: float) -> str:
    """pass at a safety factor of at least ``safety``, warn from 1, fail below 1."""
    return "fail" if factor < 1.0 else "warn" if factor < safety else "pass"


def _row(check: str, verdict: str, value: Any, limit: Any, detail: str, *sources: str) -> Dict[str, Any]:
    return {"check": check, "verdict": verdict, "value": value, "limit": limit, "detail": detail,
            "source": "; ".join(SRC[s] for s in sources)}


def _result(check: str, rows: List[Dict[str, Any]], factors: List[float], **extra: Any) -> Dict[str, Any]:
    verdict = max((r["verdict"] for r in rows), key=VERDICTS.index)
    margin = min(factors) if factors else None
    return {"check": check, "verdict": verdict, "margin": margin, "rows": rows, **extra}


def _layer(sig: np.ndarray, n: np.ndarray, sxy: float, sz: float) -> Tuple[float, str]:
    """(utilisation, what governs) of one nominal stress tensor (MPa) against the print's layers: the larger of the
    bond (across the layers) and the bulk (in the layer plane) checks of the FEA layer check."""
    modes = {k: float(v) for k, v in layer_modes(sig, n, sxy, sz).items()}
    key = max(modes, key=modes.get)
    return modes[key], {"bond": "across the layers", "bulk": "in the layer plane"}[key]


def _angle(a: np.ndarray, b: np.ndarray) -> float:
    """Angle between two unit lines (not directions), degrees, 0 to 90."""
    return math.degrees(math.acos(min(1.0, abs(float(a @ b)))))


# ----------------------------------------------------------------------------- a pin through a printed eye

def eye_stresses(load_n: float, hole_mm: float, thickness_mm: float, edge_mm: float, width_mm: float
                 ) -> Dict[str, float]:
    """Nominal stresses (MPa) in an eye carrying a pin load P (N) through a hole of diameter D, a plate t thick, its
    centre e from the end and the eye w wide across the hole:

    * bearing on the hole's projected area, sigma_br = P / (D t) (Shigley 10th ed., Section 8-12);
    * shear-out along two planes from the hole's sides to the end, tau = P / (2 t (e - D/2)) (the usual lug
      convention; Shigley 8-12 names the mode);
    * tension across the net section beside the hole, sigma_nt = P / ((w - D) t) (Shigley 8-12)."""
    P = _positive("load_n", load_n, strict=False)
    D, t = _positive("hole_mm", hole_mm), _positive("thickness_mm", thickness_mm)
    e, w = _positive("edge_mm", edge_mm), _positive("width_mm", width_mm)
    if e <= D / 2:
        raise ValueError(f"edge_mm ({e:g}) must be more than half the hole ({D / 2:g}): the hole breaks out")
    if w <= D:
        raise ValueError(f"width_mm ({w:g}) must be more than the hole ({D:g})")
    return {"bearing": P / (D * t), "shear-out": P / (2.0 * t * (e - D / 2.0)), "net tension": P / ((w - D) * t)}


def _eye_case(load_n: float, hole: float, t: float, e: float, w: float, u: np.ndarray, a: np.ndarray,
              n: np.ndarray, sxy: float, sz: float) -> Dict[str, Dict[str, Any]]:
    v = np.cross(a, u)
    s = eye_stresses(load_n, hole, t, e, w)
    tensors = {"bearing": -s["bearing"] * np.outer(u, u),
               "shear-out": s["shear-out"] * (np.outer(u, v) + np.outer(v, u)),
               "net tension": s["net tension"] * np.outer(u, u)}
    out = {}
    for mode, sig in tensors.items():
        util, governs = _layer(sig, n, sxy, sz)
        out[mode] = {"stress_mpa": s[mode], "utilisation": util, "factor": math.inf if util == 0 else 1.0 / util,
                     "governs": governs}
    return out


_EYE_DETAIL = {
    "bearing": "the pin presses on the hole: P / (D t) against the in-plane strength, a stand-in below every measured "
               "printed bearing strength (PLA 107-184 MPa ultimate, Khosravani 2023), near where the hole starts to "
               "yield and creep oval",
    "shear-out": "the end tears out along two planes from the hole's sides: P / (2 t (e - D/2)), resolved on the "
                 "layers",
    "net tension": "the eye breaks across the hole: P / ((w - D) t), resolved on the layers",
}


def pin_eye(material: str, load_n: float, pin_mm: float, thickness_mm: float, edge_mm: float, width_mm: float, *,
            bushing_mm: Optional[float] = None, load_dir: Sequence[float] = (1, 0, 0),
            pin_axis: Sequence[float] = (0, 0, 1), build: Sequence[float] = (0, 0, 1), pivots: bool = False,
            safety: float = SAFETY) -> Dict[str, Any]:
    """Check a pin through an eye printed in ``material`` (a key of PRINTED), carrying ``load_n`` towards the eye's
    end. ``edge_mm`` is from the hole's centre to the end, along the load; ``width_mm`` is the eye across the hole.
    With ``bushing_mm`` (a metal bushing's outside diameter, pressed into the eye) the plastic bears on the bushing,
    and its hole is that wide. ``pin_axis``, ``load_dir`` and ``build`` (the layer normal) are directions in the
    part's frame; the default is an eye printed flat, its pin upright. ``pivots``: the pin turns in the eye.

    Rows: bearing, shear-out and net tension (graded against ``safety``); the failure mode the geometry leads to
    (bearing is gradual, the others sudden); the layers the sections cross; a pin turning in plastic; and, with a
    bushing, what it changed against the bare eye (``compare``)."""
    m, sxy, sz = _material(material)
    P = _positive("load_n", load_n)
    d, t = _positive("pin_mm", pin_mm), _positive("thickness_mm", thickness_mm)
    _positive("safety", safety)
    if safety < 1.0:
        raise ValueError(f"safety must be at least 1, not {safety!r}")
    u, a, n = _unit("load_dir", load_dir), _unit("pin_axis", pin_axis), _unit("build", build)
    if abs(float(u @ a)) > math.sin(math.radians(1.0)):
        raise ValueError("load_dir must be square to pin_axis: the pin carries a side load")
    hole = d if bushing_mm is None else _positive("bushing_mm", bushing_mm)
    if hole < d:
        raise ValueError(f"bushing_mm ({hole:g}) must be at least the pin ({d:g})")
    case = _eye_case(P, hole, t, edge_mm, width_mm, u, a, n, sxy, sz)
    bare = case if bushing_mm is None else _eye_case(P, d, t, edge_mm, width_mm, u, a, n, sxy, sz)

    rows, factors = [], []
    for mode, c in case.items():
        factors.append(c["factor"])
        rows.append(_row(mode, _graded(c["factor"], safety), round(c["stress_mpa"], 4),
                         {"factor": round(c["factor"], 3), "safety": safety},
                         f"{_EYE_DETAIL[mode]}; {c['stress_mpa']:.2f} MPa, factor {c['factor']:.2f} "
                         f"({c['governs']} governs)", "lug-shear-out" if mode == "shear-out" else "shigley-shear",
                         "fea-layer", "printed"))
    # the failure mode: wide and long enough, the hole yields in bearing first, with warning; otherwise it breaks
    ratios, basis = bearing_mode_ratios(material)
    eod, wod = edge_mm / hole, width_mm / hole
    gradual = eod >= ratios["edge_over_d"] and wod >= ratios["width_over_d"]
    rows.append(_row("failure mode", "pass" if gradual else "warn", {"edge_over_d": round(eod, 3),
                     "width_over_d": round(wod, 3)}, dict(ratios),
                     (f"bearing first: the hole yields and stretches before anything breaks ({basis})" if gradual else
                      f"e/D {eod:.2f} and w/D {wod:.2f}, under {ratios['edge_over_d']:g} and "
                      f"{ratios['width_over_d']:g} ({basis}): the eye is more likely to break in net tension, "
                      "shear-out or cleavage, suddenly, than to yield in bearing"),
                     "astm-d5961", "khosravani-2023"))
    # the layers: printed flat (pin along the build direction), every section lies in the layer plane
    tilt = _angle(a, n)
    v = np.cross(a, u)
    if tilt <= FLAT_DEG:
        lay, why = "pass", "printed flat: the pin stands along the build direction, so every section lies in the layers"
    else:
        crossing = []
        if abs(float(u @ n)) > math.sin(math.radians(FLAT_DEG)):
            crossing.append("the load pulls the net section across the layers")
        if abs(float(v @ n)) > math.sin(math.radians(FLAT_DEG)):
            crossing.append("the shear-out planes, and the split line through the hole to the end, lie along layers")
        lay = "warn"
        why = (f"the pin is {tilt:.0f} degrees off the build direction, so the hole's hoop stress crosses the layers "
               "somewhere round it" + (": " + "; ".join(crossing) if crossing else "") +
               ". Print the eye flat, or carry the load on a bushing clamped by a through-bolt")
    rows.append(_row("layers", lay, round(tilt, 3), FLAT_DEG, why, "fea-layer"))
    if pivots:
        rows.append(_row("pivot", "pass" if bushing_mm is not None else "warn", bushing_mm is not None, True,
                         "the pin turns in the metal bushing, not in the plastic" if bushing_mm is not None else
                         "the pin turns in a printed bore: the bore wears and the hole grows, so the joint gets "
                         "slack; no wear data for printed bores was found. Press a metal (or plastic "
                         "plain-bearing) bushing into the eye", "judgement"))
    compare = None
    if bushing_mm is not None:
        compare = {mode: {"bare_factor": bare[mode]["factor"], "bushed_factor": case[mode]["factor"]}
                   for mode in case}
        worse = [mode for mode in ("shear-out", "net tension") if case[mode]["factor"] < bare[mode]["factor"]]
        rows.append(_row("bushing", "pass", {k: round(v["bushed_factor"], 3) for k, v in compare.items()},
                         {k: round(v["bare_factor"], 3) for k, v in compare.items()},
                         f"the bushing spreads the bearing over {hole:g} mm (factor {bare['bearing']['factor']:.2f} "
                         f"bare, {case['bearing']['factor']:.2f} bushed)" +
                         (f"; its larger hole leaves less plastic for {' and '.join(worse)}" if worse else ""),
                         "shigley-shear"))
    return _result("pin_eye", rows, factors, compare=compare,
                   inputs={"material": material, "load_n": P, "pin_mm": d, "thickness_mm": t, "edge_mm": edge_mm,
                           "width_mm": width_mm, "bushing_mm": bushing_mm, "load_dir": u.tolist(),
                           "pin_axis": a.tolist(), "build": n.tolist(), "pivots": pivots, "safety": safety},
                   material=_material_info(m, sxy, sz),
                   limits=list(LIMITS_COMMON) + [
                       "the pin is rigid and fits the hole: a loose pin bears on a narrower arc, at a higher peak",
                       "the bearing allowable is the in-plane tensile strength, a stand-in: printed PLA and ABS "
                       "reached 107-189 MPa ultimate in bearing (Khosravani 2023), but a held bearing load creeps the "
                       "hole oval long before that",
                       "the pin's own shear and bending, and the bushing's press fit, are not checked"])


# ----------------------------------------------------------------------------- a boss or rib loaded from the side

def tube(outer_mm: float, inner_mm: float = 0.0) -> Dict[str, Any]:
    """A boss's root: a round section, hollow when ``inner_mm`` > 0 (the bore a screw or rod passes through)."""
    o, i = _positive("outer_mm", outer_mm), _positive("inner_mm", inner_mm, strict=False)
    if i >= o:
        raise ValueError(f"inner_mm ({i:g}) must be below outer_mm ({o:g})")
    ro, ri = o / 2.0, i / 2.0
    area = math.pi * (ro ** 2 - ri ** 2)
    return {"shape": "tube", "outer_mm": o, "inner_mm": i, "area_mm2": area,
            "second_moment_mm4": math.pi / 4.0 * (ro ** 4 - ri ** 4), "c_mm": ro,
            "shear_factor": 4.0 / 3.0 * (ro ** 2 + ro * ri + ri ** 2) / (ro ** 2 + ri ** 2)}


def rect(along_mm: float, across_mm: float) -> Dict[str, Any]:
    """A rib's root: a solid rectangle, ``along_mm`` in the direction of the side load and ``across_mm`` square to
    it (bending about the axis across)."""
    h, b = _positive("along_mm", along_mm), _positive("across_mm", across_mm)
    return {"shape": "rect", "along_mm": h, "across_mm": b, "area_mm2": h * b, "second_moment_mm4": b * h ** 3 / 12.0,
            "c_mm": h / 2.0, "shear_factor": 1.5}


def through_bolt(diameter_mm: float, pitch_mm: float, *, torque_nm: Optional[float] = None,
                 preload_n: Optional[float] = None,
                 nut_factor: Tuple[float, float] = (fx.NUT_FACTORS["lubricated"], fx.NUT_FACTORS["nonplated-black"])
                 ) -> Dict[str, Any]:
    """A screw or threaded rod along a boss's bore, clamping it between a head or nut and the part below: its preload
    band, from ``torque_nm`` through the nut factor band (Shigley's Table 8-15, steel on steel), or ``preload_n`` as
    measured. The low end (the highest nut factor) is the least the joint can count on."""
    d = _positive("diameter_mm", diameter_mm)
    p = _positive("pitch_mm", pitch_mm)
    if (torque_nm is None) == (preload_n is None):
        raise ValueError("give torque_nm or preload_n, not both")
    k_lo, k_hi = (_positive("nut_factor", k) for k in nut_factor)
    if k_lo > k_hi:
        raise ValueError(f"nut_factor is (low, high), not {nut_factor!r}")
    if torque_nm is not None:
        T = _positive("torque_nm", torque_nm)
        low, high = (fx.preload_from_torque(T, d * 1e-3, k) for k in (k_hi, k_lo))
        basis = f"{T:g} N m at a nut factor of {k_lo:g} to {k_hi:g}"
    else:
        low = high = _positive("preload_n", preload_n)
        basis = "measured"
    return {"diameter_mm": d, "pitch_mm": p, "torque_nm": torque_nm, "nut_factor": (k_lo, k_hi),
            "preload_n": {"low": low, "high": high}, "basis": basis,
            "stress_area_mm2": fx.tensile_stress_area(d * 1e-3, p * 1e-3) * 1e6}


def _root_points(sec: Dict[str, Any], side_n: float, height: float, axial_n: float, clamp_n: float,
                 a: np.ndarray, u: np.ndarray, n: np.ndarray, sxy: float, sz: float) -> Dict[str, Any]:
    A, I, c = sec["area_mm2"], sec["second_moment_mm4"], sec["c_mm"]
    bend = side_n * height * c / I
    mean = (axial_n - clamp_n) / A
    shear = sec["shear_factor"] * side_n / A
    aa = np.outer(a, a)
    points = {"tension side": (mean + bend) * aa, "compression side": (mean - bend) * aa,
              "neutral axis": mean * aa + shear * (np.outer(a, u) + np.outer(u, a))}
    worst = {}
    for name, sig in points.items():
        util, governs = _layer(sig, n, sxy, sz)
        worst[name] = {"utilisation": util, "governs": governs}
    key = max(worst, key=lambda k: worst[k]["utilisation"])
    util = worst[key]["utilisation"]
    return {"bending_mpa": bend, "mean_mpa": mean, "shear_mpa": shear, "layer_tension_mpa": max(mean + bend, 0.0),
            "points": worst, "governs": key, "utilisation": util, "factor": math.inf if util == 0 else 1.0 / util}


def root_peel(material: str, side_load_n: float, height_mm: float, section: Dict[str, Any], *,
              axial_n: float = 0.0, axis: Sequence[float] = (0, 0, 1), load_dir: Sequence[float] = (1, 0, 0),
              build: Sequence[float] = (0, 0, 1), bolt: Optional[Dict[str, Any]] = None,
              retained: float = RETAINED, safety: float = SAFETY) -> Dict[str, Any]:
    """Check the root of a boss or rib printed in ``material``, standing along ``axis`` with ``section`` (:func:`tube`
    or :func:`rect`) at its root, carrying ``side_load_n`` along ``load_dir`` at ``height_mm`` above the root, and
    ``axial_n`` along the axis (tension positive). With ``bolt`` (:func:`through_bolt`), a screw or threaded rod
    through the boss's bore clamps it: its preload is spread over the root as compression. ``retained`` is the share
    of the least preload the plastic keeps for the life of the joint.

    The root is checked at three points (the tension and compression sides, and the neutral axis for shear), with
    the bolt's least preload kept and its most as tightened, against the layers (``build``). Rows: the root (graded
    against ``safety``); whether the kept preload holds the layer seam closed, and the torque that would; the
    feature's axis against the layers. ``advice`` gives the clamp that keeps the seam closed even when no bolt is
    given: what a threaded rod and nuts through the boss must keep to hold the seam closed."""
    m, sxy, sz = _material(material)
    P = _positive("side_load_n", side_load_n)
    h = _positive("height_mm", height_mm)
    if not _num(axial_n):
        raise ValueError(f"axial_n must be a finite number, not {axial_n!r}")
    if section.get("shape") not in ("tube", "rect"):
        raise ValueError("section must be tube(...) or rect(...)")
    _positive("safety", safety)
    if safety < 1.0:
        raise ValueError(f"safety must be at least 1, not {safety!r}")
    if not (_num(retained) and 0.0 < retained <= 1.0):
        raise ValueError(f"retained must be above 0 and at most 1, not {retained!r}")
    a, u, n = _unit("axis", axis), _unit("load_dir", load_dir), _unit("build", build)
    if abs(float(a @ u)) > math.sin(math.radians(1.0)):
        raise ValueError("load_dir must be square to axis: a side load")
    if bolt is not None:
        if section["shape"] != "tube" or section["inner_mm"] < bolt["diameter_mm"]:
            raise ValueError("a through-bolt passes through a tube section's bore, at least as wide as the bolt")
    A = section["area_mm2"]
    states = {"no bolt": _root_points(section, P, h, axial_n, 0.0, a, u, n, sxy, sz)}
    if bolt is not None:
        low, high = bolt["preload_n"]["low"], bolt["preload_n"]["high"]
        states["kept"] = _root_points(section, P, h, axial_n, retained * low, a, u, n, sxy, sz)
        states["tightened"] = _root_points(section, P, h, axial_n, high, a, u, n, sxy, sz)
        design = min((states["kept"], states["tightened"]), key=lambda s: s["factor"])
    else:
        design = states["no bolt"]
    bend = states["no bolt"]["bending_mpa"]
    close_n = max(A * bend + axial_n, 0.0)               # the clamp at which the tension side just stays closed
    crush_n = A * (sxy / safety - bend) + axial_n        # the most clamp the compression side takes at the margin
    rows = [_row("root", _graded(design["factor"], safety), round(design["factor"], 3), safety,
                 f"bending {bend:.2f} MPa at the root (M c / I), shear {states['no bolt']['shear_mpa']:.2f} MPa; "
                 + "; ".join(f"{k}: factor {s['factor']:.2f} ({s['governs']}, {s['points'][s['governs']]['governs']})"
                             for k, s in states.items())
                 + ("" if bolt is None else "; 'kept' is the least preload after the plastic relaxes, 'tightened' "
                                            "the most as tightened, which squeezes the compression side hardest"),
                 "shigley-beam", "gere", "fea-layer", "printed")]
    tilt = _angle(a, n)
    across = tilt < 90.0 - FLAT_DEG       # the bending crosses the layers, so there is a seam to hold closed
    # the clamp window: enough kept to hold the seam closed, not so much as tightened that the column is crushed; with
    # no seam across the bending (the feature lying in the layer plane) only the crush end applies
    least_n = close_n / retained if across else None
    advice: Dict[str, Any] = {"seam": across, "preload_to_close_n": close_n if across else None, "kept_share": retained,
                              "preload_window_n": (least_n, max(crush_n, 0.0))}
    if bolt is not None:
        kept = retained * bolt["preload_n"]["low"]
        d, (k_lo, k_hi) = bolt["diameter_mm"] * 1e-3, bolt["nut_factor"]
        t_lo = fx.torque_for_preload(least_n, d, k_hi) if across else None
        t_hi = fx.torque_for_preload(max(crush_n, 0.0), d, k_lo)
        advice["torque_window_nm"] = (t_lo, t_hi)
        window = ("" if not across else
                  f"tighten to {t_lo:.2f} N m or more to keep it closed, and to at most {t_hi:.2f} N m so the most "
                  "preload does not overload the compression side" if t_lo <= t_hi else
                  f"no torque does both: keeping it closed takes {t_lo:.2f} N m, and the compression side takes at "
                  f"most {t_hi:.2f} N m. Widen the boss (more area at the root) or shorten the lever")
        if not across:
            closed = ("pass", "lying in the layer plane: no layer seam crosses the bending, so the preload has none to "
                              "hold closed; the root row judges the stress along the layers")
        elif kept >= close_n:
            closed = ("pass", f"the kept preload, {kept:.0f} N ({retained:g} of the least, {bolt['basis']}), holds "
                              f"the tension side's layer seam closed ({close_n:.0f} N needed): it never opens under "
                              f"the load; {window}")
        else:
            closed = ("warn", f"the kept preload, {kept:.0f} N ({retained:g} of the least, {bolt['basis']}), is below "
                              f"the {close_n:.0f} N that holds the tension side closed: the layer seam opens each time "
                              f"the load comes, and a bond that opens and closes fatigues; {window}")
        rows.append(_row("layers closed", closed[0], round(kept, 3), round(close_n, 3), closed[1],
                         "shigley-beam", "shigley-torque"))
    if tilt <= FLAT_DEG:
        why = ("built upright: the root's bending stress crosses the layers, so the bond peels first" +
               ("" if bolt is not None else f"; a through-bolt kept at {close_n:.0f} N would hold it closed"))
    elif tilt >= 90.0 - FLAT_DEG:
        why = "lying in the layer plane: the root's bending stress runs along the layers"
    else:
        why = f"{tilt:.0f} degrees off the build direction: the bending stress crosses the layers in part"
    rows.append(_row("orientation", "pass", round(tilt, 3), FLAT_DEG, why, "fea-layer"))
    return _result("root_peel", rows, [design["factor"]], states=states, advice=advice,
                   inputs={"material": material, "side_load_n": P, "height_mm": h, "section": dict(section),
                           "axial_n": axial_n, "axis": a.tolist(), "load_dir": u.tolist(), "build": n.tolist(),
                           "bolt": bolt, "retained": retained, "safety": safety},
                   material=_material_info(m, sxy, sz),
                   limits=list(LIMITS_COMMON) + [
                       "the clamp is spread evenly over the root, and the bolt sits on the section's centroid, so "
                       "bending does not change its load; a bolt in a clearance bore carries no bending until the "
                       "boss deflects onto it",
                       f"retained is assumed ({RETAINED:g} by default): no long-term preload figure for printed "
                       "plastic was found; moulded polycarbonate kept 0.59 of its stress after six years at 40 degC "
                       f"({SRC['covestro-relaxation']}), and printed PLA and PETG, nearer their glass transition, are "
                       "likely to keep less",
                       "the plastic under the head or washer, and the rod's own strength, are not checked here: "
                       "cad-agent #230's check_clamp does them",
                       "a metal sleeve the full length of the boss takes the preload itself, so the plastic gets none "
                       "and the seam is not closed by it; the sleeve then carries the bending, which this check does "
                       "not model",
                       "compression is judged against the in-plane tensile strength, as the FEA layer check does: a "
                       "stand-in below the compressive strength printed PLA and PETG reached in tests (cad-agent #230 "
                       "cites them), for a held clamp that creeps",
                       "compression across the layers is not counted as opening them, and gives the bond no credit "
                       "in shear (no friction between layers is assumed)"])


# ----------------------------------------------------------------------------- a screw that backs out

THREAD_IN = ("printed", "thread-forming", "insert", "nut")
LOCKING = ("none", "anaerobic", "nylon-patch", "nylon-insert-nut", "all-metal-locknut", "jam-nut", "spring-washer",
           "safety-wire")
_NUT_ONLY = ("nylon-insert-nut", "all-metal-locknut", "jam-nut")


def _locking_row(thread_in: str, locking: str, vibration: bool) -> Dict[str, Any]:
    plastic = thread_in in ("printed", "thread-forming")
    if locking == "anaerobic":
        v = "fail" if plastic else "warn" if thread_in == "insert" else "pass"
        why = ("an anaerobic threadlocker on a printed thread: Henkel's sheets do not recommend it on thermoplastics, "
               "where it can stress-crack the plastic" if plastic else
               "an anaerobic threadlocker in an insert: keep it on the metal, since it wicks out onto the plastic "
               "round the insert and can stress-crack it" if thread_in == "insert" else
               "an anaerobic threadlocker on a metal nut: keep it off the printed part")
        return _row("locking", v, locking, "not on plastic", why, "henkel-243")
    if locking == "jam-nut":
        return _row("locking", "warn" if vibration else "pass", locking, "a prevailing-torque locknut",
                    "a jam nut tightened against the nut: NASA's manual finds it too unpredictable to be reliable and "
                    "a locknut the more practical choice" if vibration else
                    "a jam nut, and no vibration declared: preload alone holds", "nasa-1228")
    if locking in _NUT_ONLY:
        return _row("locking", "pass", locking, "binds the thread",
                    "a prevailing-torque locknut binds the thread on metal: it keeps the nut from turning off, "
                    "though a joint that slips sideways still loses its preload", "nasa-1228", "junker-1969")
    if locking == "nylon-patch":
        v = "warn" if plastic else "pass"
        return _row("locking", v, locking, "a metal mating thread",
                    "a nylon patch on the screw cuts a printed thread rather than gripping it" if plastic else
                    "a nylon patch grips the metal thread it runs in", "nasa-1228")
    if locking == "spring-washer":
        return _row("locking", "warn" if vibration else "pass", locking, "a locking element",
                    "a helical spring lock washer is flat once the screw is tight and does not lock: it counts as "
                    "none", "nasa-1228")
    if locking == "safety-wire":
        return _row("locking", "pass", locking, "captive", "the screw is held by wire or a pin and cannot turn out",
                    "nasa-1228")
    if not vibration:
        return _row("locking", "pass", locking, "none needed", "no vibration declared: preload alone holds", "nasa-1228")
    return _row("locking", "warn", locking, "a locking element",
                "nothing locks the screw and the joint vibrates: it relies on its preload alone" +
                (", held by a plastic thread" if plastic else ""), "nasa-1228", "junker-1969")


def thread_locking(thread_in: str, locking: str = "none", *, vibration: bool = True,
                   transverse_load_n: Optional[float] = None, preload_n: Optional[float] = None,
                   plastic_in_clamp: bool = True, friction: Optional[float] = None, interfaces: int = 1,
                   retained: float = RETAINED, safety: float = SAFETY) -> Dict[str, Any]:
    """Check a screw against backing out under vibration. ``thread_in``: what its thread engages, one of
    ``THREAD_IN`` (a printed or tapped plastic thread, a thread-forming screw in a boss, a metal insert, a metal nut);
    ``locking``: one of ``LOCKING``. With ``transverse_load_n`` (the side load across the joint) and ``preload_n``
    (the least clamp as tightened), the joint must carry the side load by friction at ``interfaces`` faces, or it
    slips and loosens (Junker). The friction is the low end of steel on plastic (Covestro) when ``plastic_in_clamp``,
    else ``friction`` must be given; plastic in the clamp keeps ``retained`` of the preload.

    Rows: the locking element against the thread; the transverse slip margin (graded against ``safety``); preload
    held by plastic."""
    if thread_in not in THREAD_IN:
        raise ValueError(f"thread_in must be one of {THREAD_IN}, not {thread_in!r}")
    if locking not in LOCKING:
        raise ValueError(f"locking must be one of {LOCKING}, not {locking!r}")
    if locking in _NUT_ONLY and thread_in != "nut":
        raise ValueError(f"{locking} is a nut: thread_in must be 'nut'")
    _positive("safety", safety)
    if safety < 1.0:
        raise ValueError(f"safety must be at least 1, not {safety!r}")
    if not (_num(retained) and 0.0 < retained <= 1.0):
        raise ValueError(f"retained must be above 0 and at most 1, not {retained!r}")
    if plastic_in_clamp and friction is not None:
        raise ValueError("with plastic in the clamp the friction is the low end of Covestro's steel-on-plastic band; "
                         "give friction only for metal faces (plastic_in_clamp=False)")
    if not (isinstance(interfaces, int) and not isinstance(interfaces, bool) and interfaces >= 1):
        raise ValueError(f"interfaces must be a whole number of at least 1, not {interfaces!r}")
    rows = [_locking_row(thread_in, locking, vibration)]
    factors: List[float] = []
    if (transverse_load_n is None) != (preload_n is None):
        raise ValueError("give transverse_load_n and preload_n together, or neither")
    if transverse_load_n is not None:
        q = _positive("transverse_load_n", transverse_load_n)
        F = _positive("preload_n", preload_n)
        if plastic_in_clamp:
            mu, mu_src = FRICTION_BAND[0], "covestro-friction"
        elif friction is None:
            raise ValueError("give friction for a clamp with no plastic in it (metal faces)")
        else:
            mu, mu_src = _positive("friction", friction), "junker-1969"
        kept = F * (retained if plastic_in_clamp else 1.0)
        capacity = interfaces * mu * kept
        factor = capacity / q
        factors.append(factor)
        rows.append(_row("slip", _graded(factor, safety), round(factor, 3), safety,
                         f"friction holds {capacity:.0f} N sideways ({interfaces} x {mu:g} x {kept:.0f} N kept) "
                         f"against {q:g} N: " + ("it slips: a joint that slips loses its preload, and friction or "
                                                 "prevailing-torque locking does not stop it turning off; carry the "
                                                 "side load on a pin, bushing or shoulder (pin_eye)"
                                                 if factor < 1 else "it holds" if factor >= safety else
                                                 "it holds, with less margin than asked"),
                         "junker-1969", mu_src))
    if plastic_in_clamp:
        rows.append(_row("preload in plastic", "warn" if vibration else "pass", retained, 1.0,
                         f"plastic in the clamp path relaxes, taking the preload down to about {retained:g} of what "
                         "was tightened (assumed); a metal sleeve or bushing through the plastic keeps the clamp in "
                         "metal (cad-agent #230)", "covestro-relaxation", "judgement"))
    return _result("thread_locking", rows, factors,
                   inputs={"thread_in": thread_in, "locking": locking, "vibration": vibration,
                           "transverse_load_n": transverse_load_n, "preload_n": preload_n,
                           "plastic_in_clamp": plastic_in_clamp, "friction": friction, "interfaces": interfaces,
                           "retained": retained, "safety": safety},
                   limits=["Junker's criterion as a static friction margin: no slip, no self-loosening; it does not "
                           "count cycles, and an axial vibration loosens a joint far less",
                           "the friction of steel on a printed face is not measured: the low end of Covestro's "
                           "moulded band is taken",
                           f"retained is assumed ({RETAINED:g} by default; cad-agent #230 holds the relaxation data)",
                           "a jam nut warns under vibration (NASA RP-1228 p. 7); a captive screw (wire or pin) "
                           "passes, though a joint that slips still loses its preload",
                           "the locking rows are rules from the makers' and NASA's guidance, not a test: shake the "
                           "joint (a transverse vibration test, DIN 65151 / ISO 16130) when it matters"])


def bearing_mode_ratios(material: str) -> Tuple[Dict[str, float], str]:
    """The edge and width over the hole from which an eye in ``material`` fails in bearing first, and their basis:
    measured on printed PLA, measured on printed ABS (ASA taken as ABS), or the stricter pair for a filament with no
    test (Khosravani et al. 2023, Table 2)."""
    _material(material)
    if material.startswith("pla-"):
        return dict(BEARING_MODE["pla"]), "ratios measured on printed PLA"
    if material.startswith(("abs-", "asa-")):
        return dict(BEARING_MODE["abs"]), "ratios measured on printed ABS; ASA taken as ABS"
    return dict(BEARING_MODE["abs"]), "no printed test of this filament: the stricter ratios, printed ABS's"


def sources() -> Dict[str, str]:
    """Every outside document these checks take a number or a rule from, by key; ``judgement`` marks a rule with none."""
    return dict(SRC)
