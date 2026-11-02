"""Rolling bearings in a design: catalogue bearings with their sources, and one check of a bearing's life, static
safety, axial load and speed, turning or swinging, under one load or a duty cycle.

    from cadagent.mechanical.bearings import check_bearing
    check_bearing("skf-6201-2rsh", oscillation={"amplitude_deg": 30, "cycles_per_min": 60},
                  duty=[{"radial_n": 900, "share": 0.6}, {"radial_n": 150, "share": 0.4}], required_hours=2000,
                  static=[{"name": "fall", "radial_n": 3485, "motion": "infrequent", "certainty": "low"}])
    # verdict pass / warn / fail, each check's value, limit, verdict and why, the life, the limits

``cad-agent bearings bearings.yaml`` runs the same check on a file of bearings (docs/bearings.md).

**What is data and what is model.** The ratings and speeds are the makers' (each row names its page and the date it
was read). The life is ISO 281's basic rating life and the static safety ISO 76's, as SKF's catalogue applies them
(:mod:`cadagent.formulas.bearings`); an oscillating joint's life converts revolutions into oscillations by the
distance its rolling elements travel (Harris), shortened below the critical amplitude (Rumbarger), as Menck and
Stammler (2024) recommend. A basic rating life is a statistic for a group of bearings, not a promise for one: it
leaves out lubrication, contamination, wear, false brinelling, the seals, the grease and the seats. Nothing here
proves a bearing survives. Test the joint.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from cadagent import formulas as fx


@dataclass(frozen=True)
class Bearing:
    """One rolling bearing as its maker lists it. Lengths in mm, loads in N, speeds in r/min; ``None`` where the
    maker gives no value (a bearing with contact seals has no reference speed: its seals' friction sets the speed)."""
    key: str
    maker: str
    designation: str
    kind: str                         # "deep-groove ball" or "cylindrical roller"
    d_mm: float
    outer_mm: float
    width_mm: float
    dynamic_n: float                  # C
    static_n: float                   # C0
    fatigue_limit_n: Optional[float]  # Pu
    reference_rpm: Optional[float]
    limiting_rpm: Optional[float]
    f0: Optional[float]               # ISO 76's calculation factor (ball bearings)
    kr: Optional[float]               # SKF's minimum load factor
    diameter_series: int              # ISO 15's: 8 for 618, 0 for 60, 2 for 62, 3 for 63
    seals: str                        # "open", "shields" or "contact seals"
    source: str
    note: str = ""

    @property
    def roller(self) -> bool:
        return "roller" in self.kind

    @property
    def size(self) -> str:
        """The ISO size the designation starts with ('6201' for '6201-2RSH')."""
        m = re.search(r"\d{3,}", self.designation)
        return m.group(0) if m else self.designation

    def as_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "roller": self.roller}


_SKF = ("SKF product page {des} (https://www.skf.com/group/products/rolling-bearings/{path}/productid-{slug}), its "
        "calculation data read on 2026-11-01; the same {what} in SKF Rolling bearings 17000/1 EN (2018-10), "
        "pp. {pages}")
_DGBB = "ball-bearings/deep-groove-ball-bearings"
_CRB = "roller-bearings/cylindrical-roller-bearings/single-row-cylindrical-roller-bearings"
_KOYO = ("Koyo (JTEKT) product detail 6201, open (https://koyo.jtekt.co.jp/en/products/detail/print.php?pno=6201), "
         "read on 2026-11-01: Cr, C0r, the fatigue load limit Cu, f0 and the limiting speeds for grease (22 000) and "
         "oil (27 000); Koyo lists no reference speed")


def _skf(des: str, pages: str, what: str = "values", path: str = _DGBB) -> str:
    return _SKF.format(des=des, path=path, slug=des.replace(" ", "%20"), pages=pages, what=what)


def _b(key, des, kind, d, D, B, C, C0, Pu, ref, lim, f0, kr, series, seals, src, note="", maker="SKF") -> Bearing:
    return Bearing(key, maker, des, kind, d, D, B, C, C0, Pu, ref, lim, f0, kr, series, seals, src, note)


_DG, _CR = "deep-groove ball", "cylindrical roller"
_F0_ROUNDED = "the catalogue prints f0 rounded to {}"
BEARINGS: Dict[str, Bearing] = {b.key: b for b in (
    _b("skf-6201", "6201", _DG, 12, 32, 10, 7280, 3100, 132, 50000, 32000, 12, 0.025, 2, "open",
       _skf("6201", "266-267")),
    _b("skf-6201-2rsh", "6201-2RSH", _DG, 12, 32, 10, 7280, 3100, 132, None, 15000, 12.2, 0.025, 2, "contact seals",
       _skf("6201-2RSH", "266-267"), _F0_ROUNDED.format(12)),
    _b("skf-6201-2z", "6201-2Z", _DG, 12, 32, 10, 7280, 3100, 132, 50000, 26000, 12.2, 0.025, 2, "shields",
       _skf("6201-2Z", "266-267"), _F0_ROUNDED.format(12)),
    _b("skf-6301", "6301", _DG, 12, 37, 12, 10100, 4150, 176, 45000, 28000, 11, 0.03, 3, "open",
       _skf("6301", "266-267")),
    _b("skf-6301-2rsh", "6301-2RSH", _DG, 12, 37, 12, 10100, 4150, 176, None, 14000, 11, 0.03, 3, "contact seals",
       _skf("6301-2RSH", "266-267")),
    _b("skf-61800", "61800", _DG, 10, 19, 5, 1720, 830, 36, 80000, 48000, 14.8, 0.015, 8, "open",
       _skf("61800", "264-265", "ratings and speeds")),
    _b("skf-61801", "61801", _DG, 12, 21, 5, 1740, 915, 39, 70000, 43000, 13.4, 0.015, 8, "open",
       _skf("61801", "266-267", "ratings and speeds"), _F0_ROUNDED.format(13)),
    _b("skf-61802", "61802", _DG, 15, 24, 5, 1900, 1100, 48, 60000, 38000, 13.8, 0.015, 8, "open",
       _skf("61802", "266-267", "ratings and speeds"), _F0_ROUNDED.format(14)),
    _b("skf-61803", "61803", _DG, 17, 26, 5, 2030, 1270, 54, 56000, 34000, 14.1, 0.015, 8, "open",
       _skf("61803", "268-269", "ratings and speeds")),
    _b("skf-61804", "61804", _DG, 20, 32, 7, 4030, 2320, 104, 45000, 28000, 14.5, 0.015, 8, "open",
       _skf("61804", "270-271", "ratings and speeds")),
    _b("skf-61804-2rs1", "61804-2RS1", _DG, 20, 32, 7, 4030, 2320, 104, None, 13000, 14.5, 0.015, 8, "contact seals",
       _skf("61804-2RS1", "270-271", "ratings and speeds")),
    _b("skf-61805", "61805", _DG, 25, 37, 7, 4360, 2600, 125, 38000, 24000, 14.2, 0.015, 8, "open",
       _skf("61805", "272-273", "ratings and speeds")),
    _b("skf-61806", "61806", _DG, 30, 42, 7, 4100, 2900, 146, 32000, 20000, 13.9, 0.015, 8, "open",
       _skf("61806", "272-273", "C0, Pu and speeds"), "the 2018 catalogue lists C as 4.49 kN; the product page, "
       "read later, 4.1 kN, which is used"),
    _b("skf-61806-2rs1", "61806-2RS1", _DG, 30, 42, 7, 4100, 2900, 146, None, 9500, 13.9, 0.015, 8, "contact seals",
       _skf("61806-2RS1", "272-273", "C0, Pu and speed"), "the 2018 catalogue lists C as 4.49 kN; the product page, "
       "read later, 4.1 kN, which is used"),
    _b("skf-61812", "61812", _DG, 60, 78, 10, 11400, 8800, 465, 17000, 11000, 13.7, 0.015, 8, "open",
       _skf("61812", "282-283", "speeds"), "the 2018 catalogue lists C 11.9 kN, C0 11.4 kN and Pu 0.49 kN; the "
       "product page, read later, 11.4, 8.8 and 0.465 kN, which are used"),
    _b("skf-61812-2rs1", "61812-2RS1", _DG, 60, 78, 10, 11400, 8800, 465, None, 4800, 13.7, 0.015, 8,
       "contact seals", _skf("61812-2RS1", "282-283", "speed"), "the 2018 catalogue lists C 11.9 kN, C0 11.4 kN and "
       "Pu 0.49 kN; the product page, read later, 11.4, 8.8 and 0.465 kN, which are used"),
    _b("skf-6207-2rsh", "6207-2RSH", _DG, 35, 72, 17, 27000, 15300, 660, None, 6300, 13.8, 0.025, 2, "contact seals",
       _skf("6207-2RSH", "274-275", "C, C0 and speed"), "the 2018 catalogue lists Pu 0.655 kN and f0 14; its rope "
       "sheave example (p. 223) uses this bearing"),
    _b("skf-nu-202-ecp", "NU 202 ECP", _CR, 15, 35, 11, 12500, 10200, 1220, 22000, 26000, None, 0.15, 2, "open",
       _skf("NU 202 ECP", "520-521", "values", _CRB), "an NU carries no axial load (no flanges on its inner ring)"),
    _b("skf-nu-311-ecp", "NU 311 ECP", _CR, 55, 120, 29, 156000, 143000, 18600, 6000, 7000, None, 0.15, 3, "open",
       _skf("NU 311 ECP", "522-523", "values", _CRB), "an NU carries no axial load; its centrifugal pump example "
       "(p. 229) uses this bearing"),
    Bearing("koyo-6201", "Koyo (JTEKT)", "6201", _DG, 12, 32, 10, 8500, 3050, 240, None, 22000, 12.3, None, 2, "open",
            _KOYO, "the limiting speed is Koyo's for grease; another maker's 6201 has other ratings: check the one "
                   "you buy"),
)}

# NSK Ltd., Technical Report E728h, Section 5.4, Table 1, p. 117: Pmax = K1 Fr^(1/3) MPa, 2a = K2 Fr^(1/3) mm and
# 2b = K3 Fr^(1/3) mm at the inner raceway of NSK's deep-groove ball bearing of that size, under a pure radial load
# Fr in N (Qmax = 5 Fr / Z). For another maker's bearing of the same size it is an estimate: internal geometries differ.
NSK_CONTACT: Dict[str, Tuple[float, float, float]] = {}
for _bore, _rows in {"00": ((324, .215, .020), (303, .205, .019), (215, .404, .018)),
                     "01": ((305, .205, .019), (226, .352, .017), (200, .423, .019)),
                     "02": ((287, .196, .019), (211, .336, .017), (184, .401, .019)),
                     "03": ((274, .189, .018), (193, .356, .017), (171, .415, .019)),
                     "04": ((191, .332, .017), (172, .382, .018), (161, .431, .020)),
                     "05": ((181, .320, .016), (162, .367, .018), (142, .426, .020)),
                     "06": ((160, .326, .017), (143, .395, .019), (129, .450, .021)),
                     "07": ((148, .342, .017), (128, .420, .020), (118, .474, .021)),
                     "08": ((182, .205, .021), (157, .262, .026), (112, .469, .023)),
                     "09": ((166, .206, .021), (150, .252, .025), (129, .308, .030)),
                     "10": ((161, .201, .021), (143, .258, .026), (122, .318, .031))}.items():
    for _series, _k in zip(("60", "62", "63"), _rows):
        NSK_CONTACT[_series + _bore] = _k
NSK_SOURCE = "NSK Ltd., Technical Report CAT. No. E728h, Section 5.4, Table 1 (constants K1, K2, K3), p. 117"

# SKF 17000/1 EN, Tables 7 and 8, p. 106: guideline static safety s0 by the certainty of the load, the motion and the
# permanent deformation accepted. Infrequent motion has a column for "yes" only.
S0_GUIDE = {
    ("ball", "high", "continuous", "yes"): 0.5, ("ball", "high", "continuous", "some"): 1.0,
    ("ball", "high", "continuous", "no"): 2.0, ("ball", "high", "infrequent", "yes"): 0.4,
    ("ball", "low", "continuous", "yes"): 1.5, ("ball", "low", "continuous", "some"): 1.5,
    ("ball", "low", "continuous", "no"): 2.0, ("ball", "low", "infrequent", "yes"): 1.0,
    ("roller", "high", "continuous", "yes"): 1.0, ("roller", "high", "continuous", "some"): 1.5,
    ("roller", "high", "continuous", "no"): 3.0, ("roller", "high", "infrequent", "yes"): 0.8,
    ("roller", "low", "continuous", "yes"): 2.5, ("roller", "low", "continuous", "some"): 3.0,
    ("roller", "low", "continuous", "no"): 4.0, ("roller", "low", "infrequent", "yes"): 2.0,
}
WHERE = {
    "life": "ISO 281 basic rating life as SKF 17000/1 EN applies it, Section B.3, p. 89; a1 from Table 3, p. 90; the "
            "duty cycle by Palmgren-Miner, p. 90",
    "load": "SKF 17000/1 EN, Section 1, Loads, p. 254 and Table 9, p. 257 (e, X, Y by f0 Fa / C0)",
    "axial": "SKF 17000/1 EN, Section 1, Loads, p. 254: pure axial load at most 0.5 C0; 0.25 C0 for small bearings "
             "(d <= 12 mm) and light series (diameter series 8, 9, 0 and 1)",
    "ratio": "SKF 17000/1 EN, Section B.3, p. 93: SKF's life is robust for Pu <= P <= 0.5 C (ball), 0.33 C (roller)",
    "minimum": "SKF 17000/1 EN, Section B.3, Requisite minimum load, p. 106: as a general rule 0.01 C for ball and "
               "0.02 C for roller bearings",
    "speed": "SKF 17000/1 EN, Section 1, Permissible speed, p. 256 (reference speed: thermal; limiting speed: "
             "mechanical) and Thermal equilibrium, p. 130 (no detailed thermal analysis needed below 50 % of the "
             "limiting speed with C / P > 10)",
    "static": "ISO 76 (s0 = C0 / P0) and SKF 17000/1 EN, Tables 7 and 8, p. 106 (guideline s0); p. 104: a bearing "
              "that oscillates slowly under load is sized on its static load too",
    "oscillation": "Menck and Stammler, Wind Energy Science 9 (2024) 777-798: Harris factor Eq. (3), critical amplitude "
                   "Eq. (4), Rumbarger factor Eq. (5); SKF 17000/1 EN Table 4, p. 91: not valid below 10 degrees",
    "travel": "x / 2b, the arc a contact rolls over the raceway in a stroke against the contact's width in the rolling "
              "direction: a low ratio marks a risk of wear and false brinelling (Menck and Stammler 2024, footnote 39, "
              "after Schwack 2020); below 1 the contact never leaves its own footprint",
}
LIMITS = (
    "Basic rating life (ISO 281) at the reliability asked: a statistic for a group of bearings of standard steel "
    "with ordinary lubrication. It leaves out the makers' modified life (aSKF, aISO: lubrication, contamination, the "
    "fatigue load limit), which can be much longer or shorter.",
    "Not covered: wear, false brinelling and fretting, corrosion, the grease's and the seals' life, the seats (a ring "
    "that creeps on its shaft or in its housing), misalignment, a preload or clearance that changes the load zone, "
    "and moment loads on a single bearing.",
    "An oscillating joint: the Harris and Rumbarger factors convert travelled distance; they do not model the moving "
    "ring's load zone (Houpert), and at small amplitudes the bearing usually wears out before it fatigues.",
    "Loads as given: the check does not find them. A load spectrum is reduced to blocks by Palmgren-Miner, whose "
    "order does not matter to it.",
    "Ratings are the maker's, for its bearing: a bearing of the same size from another maker has other ratings.",
    "A calculated life is not proof that a bearing survives. Test the joint.",
)
MOTIONS = ("continuous", "infrequent")
CERTAINTIES = ("high", "low")
DEFORMATIONS = ("yes", "some", "no")


def bearing(key: Any) -> Bearing:
    """A catalogue bearing by key, or your own from a mapping of :class:`Bearing`'s fields (key, maker, designation,
    kind, d_mm, outer_mm, width_mm, dynamic_n, static_n, and optionally fatigue_limit_n, reference_rpm, limiting_rpm,
    f0, kr, diameter_series, seals, source)."""
    if isinstance(key, Bearing):
        return key
    if isinstance(key, dict):
        fields = {"fatigue_limit_n": None, "reference_rpm": None, "limiting_rpm": None, "f0": None, "kr": None,
                  "diameter_series": 2, "seals": "open", "source": "given by the caller", "maker": "unknown",
                  "key": key.get("designation", "custom"), **key}
        try:
            b = Bearing(**fields)
        except TypeError as exc:
            raise ValueError(f"a custom bearing needs {sorted(Bearing.__dataclass_fields__)}: {exc}") from None
        if b.kind not in (_DG, _CR):
            raise ValueError(f"kind must be {_DG!r} or {_CR!r}, not {b.kind!r}")
        for name in ("d_mm", "outer_mm", "width_mm", "dynamic_n", "static_n"):
            if not (isinstance(getattr(b, name), (int, float)) and getattr(b, name) > 0):
                raise ValueError(f"{name} must be a number above 0")
        return b
    if key not in BEARINGS:
        raise ValueError(f"bearing must be one of {sorted(BEARINGS)} or a mapping of its fields, not {key!r}")
    return BEARINGS[key]


def _row(check: str, value: Any, limit: Any, verdict: str, detail: str, source: str = "") -> Dict[str, Any]:
    return {"check": check, "value": value, "limit": limit, "verdict": verdict, "detail": detail,
            **({"source": source} if source else {})}


def _worst(rows: List[Dict[str, Any]]) -> str:
    verdicts = {r["verdict"] for r in rows}
    return "fail" if "fail" in verdicts else "warn" if "warn" in verdicts else "pass"


def _num(name: str, v: Any, low: float = 0.0, strict: bool = False) -> float:
    if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            and (v > low if strict else v >= low)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} {low:g}, not {v!r}")
    return float(v)


def s0_guideline(roller: bool, certainty: str = "low", motion: str = "continuous", deformation: str = "some") -> float:
    """SKF's guideline static safety factor (Tables 7 and 8, p. 106) for the certainty of the load ('high': gravity,
    no vibration; 'low': peaks), the motion ('continuous' or 'infrequent') and the permanent deformation accepted
    ('yes', 'some', 'no'; infrequent motion has 'yes' only)."""
    if certainty not in CERTAINTIES or motion not in MOTIONS or deformation not in DEFORMATIONS:
        raise ValueError(f"certainty in {CERTAINTIES}, motion in {MOTIONS}, deformation in {DEFORMATIONS}; not "
                         f"{certainty!r}, {motion!r}, {deformation!r}")
    key = ("roller" if roller else "ball", certainty, motion, deformation)
    if key not in S0_GUIDE:
        raise ValueError("SKF lists infrequent motion with permanent deformation accepted ('yes') only")
    return S0_GUIDE[key]


def _blocks(b: Bearing, radial_n: float, axial_n: float, duty: Optional[List[Dict[str, Any]]],
            rotating: bool) -> List[Dict[str, Any]]:
    """The duty cycle as blocks {radial_n, axial_n, share (of the revolutions or oscillations), speed_rpm?}."""
    if duty is None:
        return [{"radial_n": _num("radial_n", radial_n), "axial_n": _num("axial_n", axial_n), "share": 1.0}]
    if not isinstance(duty, list) or not duty:
        raise ValueError("duty is a list of blocks [{radial_n, axial_n, share}, ...]")
    out = []
    for i, blk in enumerate(duty):
        if not isinstance(blk, dict) or set(blk) - {"radial_n", "axial_n", "share", "speed_rpm", "name"}:
            raise ValueError(f"duty block {i} takes radial_n, axial_n, share, speed_rpm and name, not {blk!r}")
        out.append({"name": blk.get("name", f"block {i + 1}"), "radial_n": _num("radial_n", blk.get("radial_n", 0)),
                    "axial_n": _num("axial_n", blk.get("axial_n", 0)), "share": _num("share", blk.get("share", 0)),
                    **({"speed_rpm": _num("speed_rpm", blk["speed_rpm"])} if "speed_rpm" in blk else {})})
    speeds = [blk.get("speed_rpm") for blk in out]
    if any(s is not None for s in speeds):
        if not rotating or any(s is None for s in speeds):
            raise ValueError("give speed_rpm in every block of a turning bearing's duty cycle, or in none")
        if abs(sum(blk["share"] for blk in out) - 1.0) > 1e-6:
            raise ValueError("the duty blocks' shares of the time must sum to 1, not "
                             f"{sum(blk['share'] for blk in out):g}")
        shares = fx.revolution_fractions([blk["share"] for blk in out], speeds)
        mean = sum(blk["share"] * s for blk, s in zip(out, speeds)) / sum(blk["share"] for blk in out)
        for blk, u in zip(out, shares):
            blk["time_share"], blk["share"] = blk["share"], u
        out[0]["_mean_speed"] = mean
    if abs(sum(blk["share"] for blk in out) - 1.0) > 1e-6:
        raise ValueError(f"the duty blocks' shares must sum to 1, not {sum(blk['share'] for blk in out):g}")
    return out


def _equivalent(b: Bearing, fr: float, fa: float, clearance: str) -> Dict[str, Any]:
    if b.roller:
        return {"load": fr, "x": 1.0, "y": 0.0, "axial_counts": False, "clamped": False}
    if b.f0 is None:
        raise ValueError(f"{b.designation}: the maker's f0 is needed for an axial load's X and Y")
    return fx.deep_groove_load(fr, fa, b.static_n, b.f0, clearance)


def contact_width(b: Bearing, radial_n: float, internal: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The contact's full width 2b (m) in the rolling direction at the inner raceway under a radial load: from the
    Hertz contact (:func:`cadagent.formulas.ball_raceway_contact`) when the internal geometry is given, else NSK's
    constants for a bearing of the same size, else None."""
    if b.roller or radial_n <= 0:
        return None
    internal = internal or {}
    if internal.get("balls") and internal.get("ball_mm"):
        dm = internal.get("pitch_mm") or (b.d_mm + b.outer_mm) / 2.0
        q = fx.stribeck_ball_load(radial_n, int(internal["balls"]))
        c = fx.ball_raceway_contact(q, internal["ball_mm"] * 1e-3, dm * 1e-3, internal.get("osculation", 0.52))
        return {"width": 2.0 * c["b"], "p_max": c["p_max"], "basis": f"Hertz contact of a {internal['ball_mm']:g} mm "
                f"ball (one of {internal['balls']}) at osculation {internal.get('osculation', 0.52):g}, Qmax = 5 Fr / Z"}
    k = NSK_CONTACT.get(b.size)
    if k:
        root = radial_n ** (1.0 / 3.0)
        return {"width": k[2] * root * 1e-3, "p_max": k[0] * root * 1e6,
                "basis": f"NSK's constants for its {b.size} (K3 {k[2]:g}: 2b = K3 Fr^(1/3)); {NSK_SOURCE}; another "
                         "maker's internal geometry differs"}
    return None


def check_bearing(bearing_key: Any, radial_n: float = 0.0, axial_n: float = 0.0, speed_rpm: Optional[float] = None,
                  oscillation: Optional[Dict[str, Any]] = None, duty: Optional[List[Dict[str, Any]]] = None,
                  required_hours: Optional[float] = None, required_millions: Optional[float] = None,
                  reliability: float = 90.0, clearance: str = "normal",
                  static: Optional[List[Dict[str, Any]]] = None, running: Optional[Dict[str, Any]] = None,
                  internal: Optional[Dict[str, Any]] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """Check one rolling bearing: its life, static safety, axial load, load range and speed, turning at
    ``speed_rpm`` or swinging (``oscillation`` {amplitude_deg: from the centre to one end, cycles_per_min}), under
    ``radial_n`` / ``axial_n`` or a ``duty`` cycle of blocks [{radial_n, axial_n, share, speed_rpm?}] (share of the
    revolutions or oscillations; with speed_rpm in every block of a turning bearing, the share of the time).

    ``required_hours`` (or ``required_millions`` of revolutions or oscillations) is the life to reach at
    ``reliability`` %. ``static`` lists peak loads [{name, radial_n, axial_n, motion, certainty, deformation}] checked
    against SKF's guideline s0; the duty's heaviest block is always checked too, as continuous motion with
    ``running`` {certainty, deformation} (default low certainty, some deformation). ``internal`` {balls, ball_mm,
    pitch_mm, osculation} is the internal geometry, which makers rarely publish: an oscillating joint needs it for
    the critical amplitude, and uses it for the contact's width (else NSK's constants for the size).

    Returns verdict (pass / warn / fail: the worst row), each check's value, limit, verdict and why, the life and
    the limits. Loads in N, speeds in r/min, angles in degrees."""
    b = bearing(bearing_key)
    if speed_rpm is not None and oscillation is not None:
        raise ValueError("a bearing turns (speed_rpm) or swings (oscillation), not both")
    rotating = speed_rpm is not None or (isinstance(duty, list) and any(isinstance(d, dict) and "speed_rpm" in d
                                                                          for d in duty))
    if clearance not in fx.CLEARANCES:
        raise ValueError(f"clearance must be one of {fx.CLEARANCES}, not {clearance!r}")
    if speed_rpm is not None and rotating and duty is not None and any("speed_rpm" in d for d in duty):
        raise ValueError("give speed_rpm for the whole duty cycle or a speed_rpm in each block, not both")
    if oscillation is not None and rotating:
        raise ValueError("a bearing turns (speed_rpm, here in the duty blocks) or swings (oscillation), not both")
    moving = speed_rpm is not None or oscillation is not None or rotating
    if not moving:
        given = [k for k, v in (("radial_n", radial_n), ("axial_n", axial_n), ("duty", duty),
                                ("required_hours", required_hours), ("required_millions", required_millions))
                 if v not in (None, 0, 0.0)]
        if given:
            raise ValueError(f"{', '.join(given)} need a motion: give speed_rpm or an oscillation (or put a load that "
                             "only stands still in static)")
    rows: List[Dict[str, Any]] = []
    p = fx.life_exponent(b.roller)
    blocks: List[Dict[str, Any]] = []
    life: Dict[str, Any] = {}
    speed = None
    if moving:
        blocks = _blocks(b, radial_n, axial_n, duty, rotating)
        mean_speed = blocks[0].pop("_mean_speed", None)
        speed = _num("speed_rpm", speed_rpm, strict=True) if speed_rpm is not None else mean_speed

        # -- equivalent load of each block, and the duty cycle's
        for blk in blocks:
            blk["equivalent"] = _equivalent(b, blk["radial_n"], blk["axial_n"], clearance)
        loads = [blk["equivalent"]["load"] for blk in blocks]
        if max(loads) <= 0:
            raise ValueError("the bearing carries no load")
        pm = fx.duty_cycle_load(loads, [blk["share"] for blk in blocks], b.roller) if len(blocks) > 1 else loads[0]
        clamped = any(blk["equivalent"].get("clamped") for blk in blocks)
        axial_used = [blk for blk in blocks if blk["equivalent"].get("axial_counts")]
        rows.append(_row("equivalent load", round(pm, 1), None, "warn" if clamped else "pass",
                         (f"P = {pm:.0f} N" + (f", the {'cubic' if p == 3 else '10/3-power'} mean of {len(blocks)} "
                                               "blocks (Palmgren-Miner)" if len(blocks) > 1 else "") +
                          ("; " + "; ".join(f"{blk.get('name', 'the load')}: X {blk['equivalent']['x']:.2f}, Y "
                                            f"{blk['equivalent']['y']:.2f} (Fa / Fr above e {blk['equivalent']['e']:.2f})"
                                            for blk in axial_used) if axial_used else "; the axial load is below e Fr, "
                           "so P = Fr" if any(blk["axial_n"] for blk in blocks) else "") +
                          ("; f0 Fa / C0 lies outside SKF's table (0.172 to 6.89): its end row is used" if clamped else "")),
                         WHERE["load"]))

        # -- axial load against what the type takes
        fa_max = max(blk["axial_n"] for blk in blocks)
        if b.roller:
            rows.append(_row("axial load", fa_max, 0.0, "fail" if fa_max > 0 else "pass",
                             f"an {b.designation.split(' ')[0]} carries no axial load: locate the shaft with another "
                             "bearing" if fa_max > 0 else "radial load only, as this type needs", b.note or ""))
        elif fa_max > 0:
            small = b.d_mm <= 12 or b.diameter_series in (8, 9, 0, 1)
            share = 0.25 if small else 0.5
            lim = share * b.static_n
            rows.append(_row("axial load", fa_max, round(lim, 1), "fail" if fa_max > lim else "pass",
                             f"Fa {fa_max:.0f} N against {share:g} C0 = {lim:.0f} N" +
                             (" (a small or light-series bearing)" if small else "") +
                             "; more cuts the bearing's life considerably", WHERE["axial"]))

        # -- life
        life: Dict[str, Any] = {"equivalent_load_n": pm, "exponent": p}
        a1 = fx.reliability_factor(reliability)
        l10 = fx.rating_life(b.dynamic_n, pm, b.roller)
        life.update({"l10_million_rev": l10, "a1": a1, "reliability": reliability})
        unit, rate, life_m = "revolutions", speed, a1 * l10
        if oscillation is not None:
            if not isinstance(oscillation, dict) or set(oscillation) - {"amplitude_deg", "cycles_per_min"}:
                raise ValueError("oscillation is {amplitude_deg, cycles_per_min}")
            theta = _num("amplitude_deg", oscillation.get("amplitude_deg"), strict=True)
            if theta > 180:
                raise ValueError("an amplitude above 180 degrees is a turning bearing: give speed_rpm")
            rate = _num("cycles_per_min", oscillation["cycles_per_min"], strict=True) \
                if oscillation.get("cycles_per_min") is not None else None
            a_h = fx.harris_factor(theta)
            crit = None
            if internal and internal.get("balls") and internal.get("ball_mm"):
                dm = internal.get("pitch_mm") or (b.d_mm + b.outer_mm) / 2.0
                gamma = internal["ball_mm"] / dm
                crit = {r: fx.critical_amplitude(int(internal["balls"]), gamma, r) for r in ("inner", "outer")}
            a_osc = fx.rumbarger_factor(theta, crit["outer"], b.roller) if crit else a_h
            unit, life_m = "oscillations", a1 * l10 * a_osc
            life.update({"amplitude_deg": theta, "harris_factor": a_h, "oscillation_factor": a_osc,
                         "critical_amplitude_deg": crit})
            rows.append(_row("amplitude", theta, 10.0, "warn" if theta < 10 else "pass",
                             f"a swing of +/-{theta:g} degrees: {a_osc:.3g} million oscillations per million revolutions"
                             + ("; SKF's conversion is not valid below 10 degrees, where wear and false brinelling "
                                "usually end the bearing first" if theta < 10 else ""), WHERE["oscillation"]))
            if crit:
                below = theta < crit["outer"]
                rows.append(_row("critical amplitude", theta, round(crit["outer"], 2), "warn" if below else "pass",
                                 (f"below the outer raceway's critical amplitude {crit['outer']:.1f} degrees (inner "
                                  f"{crit['inner']:.1f}): parts of the raceway are never rolled over and the rest more "
                                  f"often, so the Rumbarger factor is used, {a_osc / a_h:.0%} of Harris's"
                                  if below else f"every part of both raceways is rolled over (critical amplitude outer "
                                                f"{crit['outer']:.1f}, inner {crit['inner']:.1f} degrees): Harris's factor"),
                                 WHERE["oscillation"]))
            else:
                rows.append(_row("critical amplitude", theta, None, "warn",
                                 "no internal geometry (balls, ball_mm): the critical amplitude is not checked and Harris's "
                                 "factor is used; below it the life is shorter (for balls by (theta / theta_crit)^0.1)",
                                 WHERE["oscillation"]))
            fr_max = max(blk["radial_n"] for blk in blocks)
            width = contact_width(b, fr_max, internal)
            if width:
                dm = (internal or {}).get("pitch_mm") or (b.d_mm + b.outer_mm) / 2.0
                dw = (internal or {}).get("ball_mm") or 0.3 * (b.outer_mm - b.d_mm)
                x = fx.rolling_travel(theta, dm * 1e-3, dw * 1e-3)
                ratio = x / width["width"]
                life["contact"] = {"travel_m": x, "width_m": width["width"], "x_over_2b": ratio, "basis": width["basis"]}
                rows.append(_row("contact travel", round(ratio, 2), 1.0, "warn" if ratio < 1 else "pass",
                                 f"x / 2b = {x * 1e3:.2f} mm rolled from the swing's centre to one end against a "
                                 f"contact {width['width'] * 1e3:.3f} mm wide at "
                                 f"{fr_max:.0f} N ({width['basis']})" +
                                 (("" if (internal or {}).get("ball_mm") else "; the ball is taken as 0.3 (D - d)")) +
                                 ("; below 1 the contact never leaves its footprint: false brinelling and wear, not "
                                  "fatigue, set the life" if ratio < 1 else ""), WHERE["travel"]))
            elif not b.roller:
                rows.append(_row("contact travel", None, 1.0, "warn",
                                 "no internal geometry and no published contact constants for this size: the wear and "
                                 "false-brinelling risk of a small swing is not checked", WHERE["travel"]))
        life["life_million"] = life_m
        life["unit"] = unit
        hours = fx.life_hours(life_m, rate) if rate else None
        life["hours"] = hours
        req = None
        if required_hours is not None:
            if not rate:
                raise ValueError("required_hours needs a speed (speed_rpm, a duty with speeds, or cycles_per_min)")
            req = ("hours", _num("required_hours", required_hours, strict=True), hours)
        elif required_millions is not None:
            req = ("millions", _num("required_millions", required_millions, strict=True), life_m)
        lname = f"L{100 - reliability:g}" if reliability != 90 else "L10"
        what = (f"{lname} = {life_m:.3g} million {unit}" + (f" = {hours:,.0f} h" if hours else "") +
                (f" (a1 {a1:.3g} for {reliability:g} %)" if reliability != 90 else "") +
                (f"; C / P = {b.dynamic_n / pm:.2f}") +
                (f"; P is below the fatigue load limit Pu {b.fatigue_limit_n:.0f} N, so with clean full-film lubrication "
                 "the maker expects a much longer life than this basic one" if b.fatigue_limit_n and pm <= b.fatigue_limit_n
                 else ""))
        if req:
            kind, need, got = req
            ok = got >= need
            rows.append(_row("rating life", round(got, 4 if kind == "millions" else 0), need, "pass" if ok else "fail",
                             what + f"; {'reaches' if ok else 'falls short of'} the {need:g}"
                             f"{' h' if kind == 'hours' else ' million ' + unit} asked", WHERE["life"]))
        elif speed is not None or oscillation is not None:
            rows.append(_row("rating life", round(life_m, 4), None, "warn",
                             what + "; no required life given (required_hours or required_millions)", WHERE["life"]))

        # -- the load range the life equation is robust in, and the minimum load
        if speed is not None or oscillation is not None:
            top = 0.33 if b.roller else 0.5
            pmax = max(loads)
            rows.append(_row("load range", round(pmax / b.dynamic_n, 3), top, "warn" if pmax > top * b.dynamic_n else "pass",
                             f"the heaviest block's P = {pmax / b.dynamic_n:.2f} C" +
                             (f", above {top:g} C: the life is sensitive to the load there, and the static safety and "
                              "plastic deformation may govern" if pmax > top * b.dynamic_n else
                              f", within the {top:g} C in which the makers' life is robust"), WHERE["ratio"]))
        if speed is not None:
            share = 0.02 if b.roller else 0.01
            pmin = min(loads)
            rows.append(_row("minimum load", round(pmin, 1), round(share * b.dynamic_n, 1),
                             "warn" if pmin < share * b.dynamic_n else "pass",
                             f"the lightest block's P = {pmin:.0f} N against {share:g} C = {share * b.dynamic_n:.0f} N" +
                             (": too light a load lets the balls or rollers skid and smear the raceways; preload the "
                              "bearing or choose a smaller one" if pmin < share * b.dynamic_n else ""), WHERE["minimum"]))

        # -- speed
        top_speed = None
        if speed is not None:
            top_speed = max([blk.get("speed_rpm", speed) for blk in blocks])
            how = "the fastest block" if any("speed_rpm" in blk for blk in blocks) else "the speed"
        elif oscillation is not None and rate:
            top_speed = math.radians(life["amplitude_deg"]) * rate     # a sinusoidal swing's peak, r/min
            how = "the swing's peak (sinusoidal)"
        if top_speed is not None:
            lim, ref = b.limiting_rpm, b.reference_rpm
            if lim and top_speed > lim:
                v, why = "fail", f"above the limiting speed {lim:,.0f} r/min, a mechanical limit"
            elif ref and top_speed > ref:
                v, why = "warn", f"above the reference speed {ref:,.0f} r/min: check the temperature (a thermal limit)"
            elif lim and speed is not None and (top_speed > 0.5 * lim or b.dynamic_n / max(loads) < 10):
                v, why = "warn", ((f"over half the limiting speed {lim:,.0f} r/min" if top_speed > 0.5 * lim else
                                   f"C / P = {b.dynamic_n / max(loads):.1f}, below 10,") +
                                  ": SKF asks for a thermal analysis")
            else:
                v, why = "pass", ((f"below half the limiting speed {lim:,.0f} r/min with C / P above 10: no thermal "
                                   "analysis needed" if speed is not None else f"far below the limiting speed "
                                   f"{lim:,.0f} r/min") if lim else "no speed rating given")
            rows.append(_row("speed", round(top_speed, 1), lim, v, f"{how} {top_speed:,.1f} r/min: {why}"
                             + ("; contact seals: no reference speed, the seals' friction sets it" if b.seals ==
                                "contact seals" else ""), WHERE["speed"]))

    # -- static safety: the heaviest running block, and each peak
    run = {"certainty": "low", "deformation": "some", **(running or {})}
    heavy = max(blocks or [{"radial_n": 0, "axial_n": 0}], key=lambda blk: fx.static_equivalent_load(blk["radial_n"], blk["axial_n"]) if not b.roller
                else blk["radial_n"])
    cases = ([{"name": "running (heaviest block)", "radial_n": heavy["radial_n"],
               "axial_n": 0.0 if b.roller else heavy["axial_n"],          # a roller's axial load fails its own row
               "motion": "continuous", **run}] if moving else [])
    for i, case in enumerate(static or []):
        if not isinstance(case, dict) or set(case) - {"name", "radial_n", "axial_n", "motion", "certainty",
                                                      "deformation", "s0_required"}:
            raise ValueError(f"static case {i} takes name, radial_n, axial_n, motion, certainty, deformation and "
                             f"s0_required, not {case!r}")
        cases.append({"name": f"peak {i + 1}", "motion": "infrequent", "certainty": "low", "deformation": "yes",
                      **case})
    if not cases:
        raise ValueError("give a speed, an oscillation or a static load to check")
    statics = []
    for case in cases:
        fr = _num("radial_n", case.get("radial_n", 0))
        fa = _num("axial_n", case.get("axial_n", 0))
        if b.roller and fa > 0:
            raise ValueError(f"{case['name']}: an {b.designation} carries no axial load")
        p0 = fr if b.roller else fx.static_equivalent_load(fr, fa)
        if p0 <= 0:
            raise ValueError(f"{case['name']}: no load")
        need = case.get("s0_required") or s0_guideline(b.roller, case["certainty"], case["motion"],
                                                       case["deformation"])
        s0 = fx.static_safety(b.static_n, p0)
        statics.append({"name": case["name"], "p0_n": p0, "s0": s0, "required": need})
        rows.append(_row(f"static safety: {case['name']}", round(s0, 3), need, "pass" if s0 >= need else "fail",
                         f"s0 = C0 / P0 = {b.static_n:.0f} / {p0:.0f} N = {s0:.2f} against {need:g} ({case['motion']} "
                         f"motion, {case['certainty']} certainty, permanent deformation accepted: "
                         f"{case['deformation']})" + ("; below 1 the raceways dent (brinell): a turning bearing then "
                                                      "runs rough" if s0 < 1 else ""), WHERE["static"]))

    return {"verdict": _worst(rows), "name": name or f"{b.maker} {b.designation}", "bearing": b.as_dict(),
            "motion": ("oscillating" if oscillation is not None else "turning" if speed is not None else "static"),
            "speed_rpm": speed, "blocks": [{k: v for k, v in blk.items() if k != "equivalent"} | {
                "equivalent_n": blk["equivalent"]["load"]} for blk in blocks],
            "life": life, "static": statics, "checks": rows, "limits": list(LIMITS)}


SPEC_KEYS = {"name", "bearing", "radial_n", "axial_n", "speed_rpm", "oscillation", "duty", "required_hours",
             "required_millions", "reliability", "clearance", "static", "running", "internal"}


def check_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Every bearing of a spec ({'bearings': [...]}, plus defaults for all of them under 'defaults'): {verdict (the
    worst), bearings: [each result]}. Each entry is check_bearing's arguments, its bearing a catalogue key or a
    mapping of a bearing's fields."""
    if not isinstance(spec, dict) or not isinstance(spec.get("bearings"), list) or not spec["bearings"]:
        raise ValueError("a spec is {'bearings': [{bearing, radial_n, speed_rpm or oscillation, ...}, ...]} with at "
                         "least one bearing")
    defaults = dict(spec.get("defaults") or {})
    unknown = set(defaults) - SPEC_KEYS
    if unknown:
        raise ValueError(f"defaults: unknown keys {sorted(unknown)}")
    out = []
    for i, entry in enumerate(spec["bearings"]):
        if not isinstance(entry, dict) or "bearing" not in {**defaults, **entry}:
            raise ValueError(f"bearing {i} must be a mapping with a 'bearing', not {entry!r}")
        unknown = set(entry) - SPEC_KEYS
        if unknown:
            raise ValueError(f"bearing {i}: unknown keys {sorted(unknown)} (known: {sorted(SPEC_KEYS)})")
        args = {**defaults, **entry}
        out.append(check_bearing(args.pop("bearing"), **args))
    return {"verdict": _worst([{"verdict": r["verdict"]} for r in out]), "bearings": out}


def life_curve(bearing_key: Any, loads_n: List[float], reliability: float = 90.0) -> List[Dict[str, float]]:
    """L10 (millions of revolutions, at the reliability) against the equivalent load, for a chart."""
    b = bearing(bearing_key)
    a1 = fx.reliability_factor(reliability)
    return [{"load_n": p, "life_million": a1 * fx.rating_life(b.dynamic_n, p, b.roller)} for p in loads_n]
