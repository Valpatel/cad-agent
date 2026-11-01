"""Snap-fit sizing: cantilever, torsion and annular snap joints, with deterministic pass/fail checks.

Closed-form method of the Covestro (formerly Bayer) design guide, *Snap-Fit Joints for Plastics - A Design Guide*
(Covestro LLC, 2013+; the method is the classic Bayer one, also used by the BASF and DuPont guides). Equation and
table references below ("Table 1", "Fig. 18", "Example I") are to that guide. Every result is small-deflection beam
theory with one part rigid, in the guide's terms:

* **Strain, not stress.** A snap arm is sized from the permissible strain in the outer fibre at the root, and the force
  from the strain-dependent **secant** modulus Es at that strain (the material is outside its linear range during the
  brief joining).
* **Permissible strain** is for one brief joining; for parts separated and rejoined often, use about 60 % of it
  (Table 2 note, ``repeated=True``).
* **One part rigid.** If both parts flex about equally, each takes half the deflection (pass ``share`` = 0.5).

Limits, stated in every check result (``LIMITS``): no large-deflection, contact, creep or fatigue; the hook face is not
sized. A printed (FDM) part is weaker across its layers than along them: for the filaments in
:data:`cadagent.mechanical.compliant.allowables.PRINTED` the allowable comes from the datasheet for the stated
direction; for any other material in a layered process the caller passes a measured or sourced ``process_factor``. Use
FEA for large deflection and print and measure a coupon before relying on a number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cadagent.mechanical.compliant.allowables import DIRECTIONS, PRINTED, PrintedMaterial

GUIDE = "Covestro, Snap-Fit Joints for Plastics - A Design Guide"
REPEATED_USE_FACTOR = 0.6          # Table 2 note: frequent separation and rejoining
MIN_ROOT_RADIUS_MM = 0.381         # 0.015 in: "the radius should not be less than 0.015 in. in any instance"
TARGET_ROOT_RATIO = 0.6            # Fig. 9: little further stress-concentration reduction beyond R/h = 0.6
POISSON_PLASTICS = 0.35            # Section C: Poisson's ratio for plastics, approx.
LIMITS = (
    "closed-form small-deflection beam theory (Covestro/Bayer method): no large deflection, contact, creep or fatigue",
    "one mating part assumed rigid unless share < 1 is given",
    "permissible strain and secant modulus are the caller's inputs; values in MATERIALS are guide data, not "
    "measurements of a particular batch or print",
    "a printed part's inter-layer strength and strain are lower than in-plane: the datasheet filaments carry this per "
    "direction; any other material in a layered process needs a sourced process_factor",
    "a pass has no extra margin: the guide's own examples design to half the permissible strain",
    "small deflection is assumed: when the deflection exceeds about a tenth of the arm length a warning is given "
    "and the closed form overestimates force and strain accuracy",
    "hook-face geometry, wall deflection at the root and mould release are not checked",
    "the model, not the part: print a coupon and measure the force and the strain at failure",
)


@dataclass(frozen=True)
class Material:
    """Guide data for one snap-fit material. ``strain`` is the permissible short-term strain for a single joining
    operation at 23 degC, as a fraction (0.04 = 4 %). ``secant_mpa`` maps strain fraction to secant modulus where the
    source gives curve points; otherwise give Es directly to the calculator."""
    name: str
    strain: float
    source: str
    friction: Optional[float] = None          # against steel, Table 3 mid-range
    friction_same_factor: float = 1.0         # Table 3 factor for the same plastic on itself
    secant_mpa: Dict[float, float] = field(default_factory=dict)
    note: str = ""
    strain_repeated: Optional[float] = None   # where the source gives its own value for frequent use

    def allowable(self, repeated: bool = False, process_factor: float = 1.0) -> float:
        if repeated:
            base = self.strain_repeated if self.strain_repeated is not None else self.strain * REPEATED_USE_FACTOR
        else:
            base = self.strain
        return base * process_factor

    def mu(self, same_material: bool = True) -> Optional[float]:
        if self.friction is None:
            return None
        return self.friction * (self.friction_same_factor if same_material else 1.0)


_T2 = f"{GUIDE}, Table 2 (allowable short-term strain, single joining, 23 degC)"
MATERIALS: Dict[str, Material] = {
    "pc": Material("Polycarbonate (Makrolon)", 0.04, _T2, friction=0.50, friction_same_factor=1.2,
                   secant_mpa={0.02: 1815.0, 0.005: 2200.0},
                   note="Es points from the guide's Examples I (2 %: 1,815 MPa) and the annular example (0.5 %: 2,200 MPa)"),
    "pc-high-heat": Material("High-heat PC (Apec)", 0.04, _T2, friction=0.50, friction_same_factor=1.2),
    "pc-abs": Material("PC/ABS (Bayblend)", 0.025, _T2, friction=0.575, friction_same_factor=1.2,
                       note="friction: Table 3 ABS range"),
    "pc-blend": Material("PC blends (Makroblend)", 0.035, _T2),
    "pc-gf10": Material("PC, 10 % glass (Makrolon)", 0.022, _T2),
    "pc-gf20": Material("PC, 20 % glass (Makrolon)", 0.020, _T2),
}
# DuPont, General Design Principles - Module I, Table 10.06 (lug-type snap fits; "used once" with new material /
# "used frequently"). Where a range is given the lower end is used. Friction: Covestro Table 3 mid-range.
_DUP = "DuPont, General Design Principles - Module I, Table 10.06 (allowable strain, lug-type snap fits)"
MATERIALS.update({
    "pom-delrin-100": Material("POM (Delrin 100)", 0.08, _DUP, friction=0.275, friction_same_factor=1.5,
                               strain_repeated=0.02, note="frequent use: 2-4 %, lower end"),
    "pom-delrin-500": Material("POM (Delrin 500)", 0.06, _DUP, friction=0.275, friction_same_factor=1.5,
                               strain_repeated=0.02, note="frequent use: 2-3 %, lower end"),
    "pa66-dry": Material("PA66 (Zytel 101), dry as moulded", 0.04, _DUP, friction=0.35, friction_same_factor=1.5,
                         strain_repeated=0.02),
    "pa66-50rh": Material("PA66 (Zytel 101), 50 % RH", 0.06, _DUP, friction=0.35, friction_same_factor=1.5,
                          strain_repeated=0.03),
    "pa66-gf-dry": Material("Glass-filled PA66 (Zytel GR), dry", 0.008, _DUP, friction=0.35, friction_same_factor=1.5,
                            strain_repeated=0.005, note="once: 0.8-1.2 %, frequent: 0.5-0.7 %; lower ends"),
    "pa66-gf-50rh": Material("Glass-filled PA66 (Zytel GR), 50 % RH", 0.015, _DUP, friction=0.35,
                             friction_same_factor=1.5, strain_repeated=0.01, note="once: 1.5-2.0 %, lower end"),
    "pet-gf": Material("Glass-filled PET (Rynite)", 0.01, _DUP, strain_repeated=0.005),
    "pbt-gf": Material("Glass-filled PBT (Crastin)", 0.012, _DUP, friction=0.375, strain_repeated=0.006),
    "tpc-hytrel": Material("TPC elastomer (Hytrel)", 0.20, _DUP, strain_repeated=0.10),
})


def allowable_strain_from_yield(yield_or_break_strain: float, kind: str) -> float:
    """The guide's rule (Fig. 13) when no Table 2 value exists: partially crystalline materials may be strained almost
    to the yield point, amorphous ones to about 70 % of the yield strain, and glass-filled ones without a yield point to
    about half the elongation at break. ``kind`` is 'semicrystalline', 'amorphous' or 'filled'."""
    factors = {"semicrystalline": 1.0, "amorphous": 0.7, "filled": 0.5}
    if kind not in factors:
        raise ValueError(f"kind must be one of {sorted(factors)}")
    return yield_or_break_strain * factors[kind]


# ----------------------------------------------------------------------------- sections

@dataclass(frozen=True)
class Section:
    """A beam cross-section at the root: area, second moment about the bending axis through the centroid, and the
    distances from the neutral axis to the fibre in tension (``c``) and to the opposite fibre (``c_other``)."""
    area: float
    inertia: float
    c: float
    c_other: float
    kind: str
    dims: Dict[str, float] = field(default_factory=dict)

    @property
    def modulus(self) -> float:
        """Section modulus Z = I / c for the fibre in tension (Table 1 note 4)."""
        return self.inertia / self.c


def rect_section(width: float, thickness: float) -> Section:
    """Table 1 shape A: rectangle ``width`` b across the bending plane, ``thickness`` h in it."""
    return Section(width * thickness, width * thickness ** 3 / 12.0, thickness / 2.0, thickness / 2.0, "rect",
                   {"b": width, "h": thickness})


def ring_section(r_inner: float, r_outer: float, arc_deg: float, tension: str = "convex") -> Section:
    """Table 1 shape C: an annular sector (a slotted tube's finger) of inner/outer radius and included angle,
    bending in its plane of symmetry. Computed exactly instead of read from Fig. 10/11. ``tension`` is the side whose
    fibre is stretched: 'convex' (outer arc) or 'concave' (inner arc)."""
    if not 0 < r_inner < r_outer or not 0 < arc_deg <= 360:
        raise ValueError("need 0 < r_inner < r_outer and 0 < arc_deg <= 360")
    th = math.radians(arc_deg) / 2.0                                     # half-angle from the symmetry axis
    area = th * (r_outer ** 2 - r_inner ** 2)
    ybar = (2.0 / 3.0) * (r_outer ** 3 - r_inner ** 3) * math.sin(th) / (r_outer ** 2 - r_inner ** 2) / th
    i_origin = (r_outer ** 4 - r_inner ** 4) / 8.0 * (2 * th + math.sin(2 * th))
    inertia = i_origin - area * ybar ** 2
    c_convex = r_outer - ybar
    # lowest fibre along the symmetry axis: the inner arc ends up to a half-angle of 90 deg, then the outer arc ends,
    # and the far side of the ring (-r_outer) for a full ring
    y_min = r_inner * math.cos(th) if th <= math.pi / 2 else r_outer * math.cos(min(th, math.pi))
    c_concave = ybar - y_min
    if tension not in ("convex", "concave"):
        raise ValueError("tension must be 'convex' or 'concave'")
    c, other = (c_convex, c_concave) if tension == "convex" else (c_concave, c_convex)
    return Section(area, inertia, c, other, "ring", {"r1": r_inner, "r2": r_outer, "arc_deg": arc_deg, "ybar": ybar})


# ----------------------------------------------------------------------------- cantilever

# Table 1 deflection factors: y = k * eps * l^2 / c for any section (shape D), by design:
#   1 constant section; 2 thickness tapering linearly to h/2 at the hook; 3 width tapering to b/4 at the hook.
# For a rectangle (c = h/2) these are the guide's 0.67, 1.09 and 0.86 * eps * l^2 / h.
DESIGN_K = {1: 1.0 / 3.0, 2: 0.55, 3: 0.43}   # as printed: 1/3, 0.55, 0.43
DESIGN_K_RECT = {1: 0.67, 2: 1.09, 3: 0.86}


def permissible_deflection(section: Section, length: float, strain: float, design: int = 1) -> float:
    """Table 1: the deflection (undercut) y that strains the root's outer fibre to ``strain``."""
    if section.kind == "rect":
        return DESIGN_K_RECT[design] * strain * length ** 2 / (2.0 * section.c)
    return DESIGN_K[design] * strain * length ** 2 / section.c


def root_strain(section: Section, length: float, deflection: float, design: int = 1) -> float:
    """Inverse of :func:`permissible_deflection`: root strain at a given deflection."""
    return deflection / permissible_deflection(section, length, 1.0, design)


def thickness_for(deflection: float, length: float, strain: float, design: int = 1) -> float:
    """Rectangular arm: root thickness h at which ``deflection`` gives ``strain`` (Example I, step a)."""
    return DESIGN_K_RECT[design] * strain * length ** 2 / deflection


def deflection_force(section: Section, length: float, strain: float, secant_mpa: float) -> float:
    """Table 1 bottom row: P = Z * Es * eps / l, the force at the hook that deflects the arm to ``strain`` (N, with
    mm and MPa)."""
    return section.modulus * secant_mpa * strain / length


def mating_force(deflection_force_n: float, friction: float, angle_deg: float) -> float:
    """W = P * (mu + tan a) / (1 - mu tan a) (Fig. 17/18). With the return angle instead of the lead angle it is the
    separation force. Infinite when mu * tan a >= 1: the joint is self-locking (inseparable by pulling)."""
    t = math.tan(math.radians(angle_deg))
    denom = 1.0 - friction * t
    if denom <= 0:
        return math.inf
    return deflection_force_n * (friction + t) / denom


def engagement(*, length: float, section: Section, undercut: float, lead_deg: float, design: int = 1,
               secant_mpa: Optional[float] = None, friction: Optional[float] = None, land_mm: float = 0.0,
               share: float = 1.0) -> Dict[str, Any]:
    """The cantilever's closed form along the insertion: the root strain and the forces as the mating part's edge
    rides up the hook's lead face, slides along its land and drops off behind it.

    The edge lifts the hook by ``travel * tan(lead)``, so the hook clears the undercut after ``undercut / tan(lead)``
    of travel. It then slides ``land_mm`` at that deflection and drops behind the edge (a return face steep enough to
    drop at once). The arm takes ``share`` of the lift. At each point the root strain is :func:`root_strain`, the
    deflection force :func:`deflection_force` (with ``secant_mpa``) and the push to mate :func:`mating_force` (with
    ``friction``): at the lead angle on the lead, and at 0 deg on the land, where only friction resists (mu * P).

    Every quantity is linear in the travel within a phase, so the points returned are exact and a straight line joins
    them: contact (travel 0), the top of the lead, the start and end of the land (if ``land_mm`` > 0, where the push
    falls from the lead's W to the land's mu * P), and released (the same travel, deflection 0). The peak is
    :func:`check_cantilever`'s numbers for the same arm. A self-locking lead (mu * tan(lead) >= 1) gives no push force
    and sets ``self_locking``. As in the guide, contact stiffness, the drop's dynamics and the hook's turn with the
    arm's tip are not modelled. The turn steepens the face the edge rides (a 15 mm arm lifted 1.3 mm turns its tip
    7.4 deg), so near the top of a steep lead, or on a short arm, this under-states the push to mate: check those with
    FEA or a push test."""
    _require(length > 0 and undercut > 0, "length and undercut must be positive")
    _require(0 < lead_deg < 90, "lead_deg must be between 0 and 90")
    _require(land_mm >= 0, "land_mm must be 0 or more")
    _require(0 < share <= 1, "share must be in (0, 1]")
    _require(design in DESIGN_K, "design must be 1, 2 or 3")
    lead_travel = undercut / math.tan(math.radians(lead_deg))
    y_max = undercut * share
    self_locking = friction is not None and math.isinf(mating_force(1.0, friction, lead_deg))

    def point(phase: str, travel: float, y: float, angle: Optional[float]) -> Dict[str, Any]:
        eps = root_strain(section, length, y, design)
        p = deflection_force(section, length, eps, secant_mpa) if secant_mpa is not None else None
        w = None
        if p is not None and friction is not None and not (angle and self_locking):
            w = mating_force(p, friction, angle) if angle is not None else 0.0
        return {"phase": phase, "travel_mm": travel, "deflection_mm": y, "strain": eps, "deflection_force_n": p,
                "mating_force_n": w}

    points = [point("lead", 0.0, 0.0, lead_deg), point("lead", lead_travel, y_max, lead_deg)]
    if land_mm > 0:
        points += [point("land", lead_travel, y_max, 0.0), point("land", lead_travel + land_mm, y_max, 0.0)]
    points.append(point("released", lead_travel + land_mm, 0.0, None))
    return {"points": points, "lead_travel_mm": lead_travel, "land_mm": land_mm, "lead_deg": lead_deg,
            "friction": friction, "secant_mpa": secant_mpa, "self_locking": self_locking,
            "peak": {k: points[1][k] for k in ("deflection_mm", "strain", "deflection_force_n", "mating_force_n")}}


def travel_at_strain(curve: Dict[str, Any], strain: float) -> Optional[float]:
    """The travel along an :func:`engagement` curve where the root strain first reaches ``strain`` (on the lead), or
    None if it never does."""
    a, b = curve["points"][:2]
    if strain <= 0 or b["strain"] < strain:
        return None
    return a["travel_mm"] + (b["travel_mm"] - a["travel_mm"]) * strain / b["strain"]


# ----------------------------------------------------------------------------- torsion

def torsion_allowable_shear(strain: float, poisson: float = POISSON_PLASTICS) -> float:
    """Section C: the permissible shear strain of a torsion bar from the permissible (tensile) strain, gamma_pm ~
    (1 + nu) eps_pm. It is the maximum-shear-stress (Tresca) criterion written in strain: tau_pm = E eps_pm / 2 and
    gamma = tau / G with G = E / 2(1 + nu)."""
    return (1.0 + poisson) * strain


def torsion_snap(bar_length: float, bar_radius: float, strain: float, secant_mpa: float, lever_mm: float,
                 bars: int = 2, poisson: float = POISSON_PLASTICS) -> Dict[str, float]:
    """Section C, circular torsion bar(s): permissible twist and the force at a lever arm.

    gamma_pm ~ (1 + nu) eps_pm; phi_pm = 180/pi * gamma_pm * l / r; G = Es / (2 (1 + nu)); Ip = pi r^4 / 2;
    P * lever = bars * G * Ip * gamma / r. The guide's factor 2 is for two bars (Fig. 21). For a rectangular bar and
    a given twist, see :func:`cadagent.formulas.torsion_snap_bar`."""
    gamma = torsion_allowable_shear(strain, poisson)
    phi_deg = math.degrees(gamma * bar_length / bar_radius)
    g = secant_mpa / (2.0 * (1.0 + poisson))
    ip = math.pi * bar_radius ** 4 / 2.0
    force = bars * g * ip * gamma / bar_radius / lever_mm
    return {"shear_strain": gamma, "twist_deg": phi_deg, "deflection_mm": lever_mm * math.sin(math.radians(phi_deg)),
            "shear_modulus_mpa": g, "force_n": force}


# ----------------------------------------------------------------------------- annular

def annular_factor_hub(d_outer: float, d_joint: float, poisson: float = POISSON_PLASTICS) -> float:
    """X_N, rigid shaft in an elastic tube (hub) of outside diameter ``d_outer`` (Section D)."""
    q = d_outer / d_joint
    return 0.62 * math.sqrt((q - 1) / (q + 1)) / ((q * q + 1) / (q * q - 1) + poisson)


def annular_factor_shaft(d_joint: float, d_inner: float, poisson: float = POISSON_PLASTICS) -> float:
    """X_W, rigid tube on an elastic hollow shaft of inside diameter ``d_inner`` (Section D)."""
    q = d_joint / d_inner
    return 0.62 * math.sqrt((q - 1) / (q + 1)) / ((q * q + 1) / (q * q - 1) - poisson)


def annular_snap(undercut: float, d_joint: float, wall: float, secant_mpa: float, factor: float,
                 friction: float, lead_deg: float, return_deg: Optional[float] = None, share: float = 1.0,
                 distance_from_end: float = 0.0) -> Dict[str, float]:
    """Section D: strain eps = y / d, transverse force P = y d Es X, mating force from :func:`mating_force`.

    ``share`` is the part of the undercut this part takes (0.5 when both are about equally stiff). A groove at least
    1.8 * sqrt(d t) from the tube end is 'remote': forces up to 3x (the guide's tested factor, not the theoretical 4x);
    in between it is interpolated linearly."""
    y = undercut * share
    strain = y / d_joint
    p_near = y * d_joint * secant_mpa * factor
    remote_at = 1.8 * math.sqrt(d_joint * wall)
    loc = 1.0 + 2.0 * min(1.0, max(0.0, distance_from_end / remote_at))
    p = p_near * loc
    out = {"strain": strain, "deflection_mm": y, "transverse_force_n": p, "location_factor": loc,
           "remote_from_mm": remote_at, "mating_force_n": mating_force(p, friction, lead_deg)}
    if return_deg is not None:
        out["separation_force_n"] = mating_force(p, friction, return_deg)
    return out


# ----------------------------------------------------------------------------- checks

def check_cantilever(*, length: float, section: Section, undercut: float, strain_allow: float, design: int = 1,
                     secant_mpa: Optional[float] = None, friction: Optional[float] = None,
                     lead_deg: Optional[float] = None, return_deg: Optional[float] = None,
                     root_radius: Optional[float] = None, share: float = 1.0,
                     max_mating_n: Optional[float] = None, min_retention_n: Optional[float] = None,
                     name: str = "snap", modulus_note: Optional[str] = None,
                     retention_secant_mpa: Optional[float] = None,
                     retention_note: Optional[str] = None) -> Dict[str, Any]:
    """Deterministic pass/fail rows for one cantilever snap. ``strain_allow`` already includes repeated-use and
    process derating (see :meth:`Material.allowable`). Every declared limit gives a row: one that cannot be computed
    (missing secant modulus, friction or angle; a self-locking hook's retention) fails and says what is missing, and
    a missing root radius fails, so nothing passes unchecked. ``retention_secant_mpa``, where given, replaces
    ``secant_mpa`` for the separation force: the cautious modulus is the high one for mating and the low one for
    retention."""
    _require(length > 0 and undercut > 0, f"{name}: length and undercut must be positive")
    _require(0 < strain_allow <= 0.5, f"{name}: allowable strain {strain_allow!r} is not a fraction (0.03 = 3 %)")
    _require(0 < share <= 1, f"{name}: share must be in (0, 1]")
    _require(design in DESIGN_K, f"{name}: design must be 1, 2 or 3")
    y = undercut * share
    eps = root_strain(section, length, y, design)
    rows: List[Dict[str, Any]] = [{
        "check": "root strain", "value": eps, "limit": strain_allow, "pass": eps <= strain_allow,
        "detail": f"{eps * 100:.2f} % at {y:.3f} mm deflection vs {strain_allow * 100:.2f} % allowed"}]
    h = section.c + section.c_other
    if root_radius is None:
        rows.append({"check": "root radius", "value": None, "limit": MIN_ROOT_RADIUS_MM, "pass": False,
                     "detail": "not stated: give root_radius_mm (at least 0.38 mm; R/h 0.6 is the target)"})
    else:
        rows.append({"check": "root radius", "value": root_radius, "limit": MIN_ROOT_RADIUS_MM,
                     "pass": root_radius >= MIN_ROOT_RADIUS_MM,
                     "detail": f"R {root_radius:.2f} mm (minimum 0.38 mm); R/h {root_radius / h:.2f}"
                               + ("" if root_radius / h >= TARGET_ROOT_RATIO else
                                  f" below {TARGET_ROOT_RATIO}: the root concentrates strain (Fig. 9)")})
    out: Dict[str, Any] = {"name": name, "strain": eps, "deflection_mm": y, "rows": rows, "warnings": []}
    if y / length > 0.1:
        out["warnings"].append(f"deflection {y:.2f} mm is {y / length:.2f} of the arm length: beyond small "
                               "deflection; confirm with large-deflection FEA or a coupon")
    p = deflection_force(section, length, eps, secant_mpa) if secant_mpa is not None else None
    if p is not None:
        out["deflection_force_n"] = p
    ret_secant = retention_secant_mpa if retention_secant_mpa is not None else secant_mpa
    p_ret = deflection_force(section, length, eps, ret_secant) if ret_secant is not None else None
    if p_ret is not None and ret_secant != secant_mpa:
        out["retention_deflection_force_n"] = p_ret
    suffix = f" ({modulus_note})" if modulus_note else ""
    ret_note = retention_note if retention_note is not None else modulus_note
    ret_suffix = f" ({ret_note})" if ret_note else ""

    def missing(angle_name: str, angle: Optional[float], modulus: Optional[float]) -> List[str]:
        return [k for k, v in (("secant_mpa", modulus), ("friction", friction), (angle_name, angle)) if v is None]

    if p is not None and friction is not None and lead_deg is not None:
        w = mating_force(p, friction, lead_deg)
        if math.isinf(w):
            out["mating_self_locking"] = True
            rows.append({"check": "lead angle", "value": lead_deg, "limit": "mu * tan(lead) < 1", "pass": False,
                         "detail": f"mu {friction:g} x tan {lead_deg:g} deg >= 1: the lead self-locks and the parts "
                                   "cannot be pushed together; use a shallower lead angle"})
        else:
            out["mating_force_n"] = w
    if max_mating_n is not None and not out.get("mating_self_locking"):
        if "mating_force_n" in out:
            w = out["mating_force_n"]
            rows.append({"check": "mating force", "value": w, "limit": max_mating_n, "pass": w <= max_mating_n,
                         "detail": f"{w:.1f} N to assemble vs {max_mating_n:.1f} N allowed" + suffix})
        else:
            rows.append({"check": "mating force", "value": None, "limit": max_mating_n, "pass": False,
                         "detail": "not computed: missing " + ", ".join(missing("lead_deg", lead_deg, secant_mpa))})
    if p_ret is not None and friction is not None and return_deg is not None:
        s = mating_force(p_ret, friction, return_deg)
        out["self_locking"] = math.isinf(s)
        out["separation_force_n"] = None if math.isinf(s) else s
    if min_retention_n is not None:
        if out.get("self_locking"):
            rows.append({"check": "retention force", "value": None, "limit": min_retention_n, "pass": False,
                         "detail": "self-locking: pulling cannot release it, so retention is the hook's own shear or "
                                   "bending strength, which this method does not compute; check it by FEA or a pull "
                                   "test, or drop min_retention_n"})
        elif "separation_force_n" in out:
            s = out["separation_force_n"]
            rows.append({"check": "retention force", "value": s, "limit": min_retention_n,
                         "pass": s >= min_retention_n,
                         "detail": f"{s:.1f} N to pull apart vs {min_retention_n:.1f} N required" + ret_suffix})
        else:
            rows.append({"check": "retention force", "value": None, "limit": min_retention_n, "pass": False,
                         "detail": "not computed: missing " + ", ".join(missing("return_deg", return_deg,
                                                                                ret_secant))})
    out["pass"] = all(r["pass"] for r in rows)
    out["limits"] = list(LIMITS)
    out["method"] = GUIDE
    return out


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


# ----------------------------------------------------------------------------- spec files

PROCESSES = {"moulding": "moulded", "molding": "moulded", "injection-moulding": "moulded",
             "injection-molding": "moulded", "fdm": "layered", "fff": "layered", "sla": "layered", "sls": "layered",
             "mjf": "layered"}
LAYERED_PROCESSES = tuple(k for k, v in PROCESSES.items() if v == "layered")


def _num(spec: Dict[str, Any], key: str, name: str, *, required: bool = False, gt: Optional[float] = None,
         ge: Optional[float] = None, le: Optional[float] = None, lt: Optional[float] = None,
         default: Optional[float] = None, hint: str = "") -> Optional[float]:
    """A number from a declaration, range-checked, with an error that names the snap and the field."""
    if spec.get(key) is None:
        if required:
            raise ValueError(f"snap {name!r}: missing {key}")
        return default
    raw = spec[key]
    if isinstance(raw, bool):
        raise ValueError(f"snap {name!r}: {key} must be a number, not {raw!r}")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"snap {name!r}: {key} must be a number, not {raw!r}") from None
    bad = ((gt is not None and not v > gt) or (ge is not None and not v >= ge) or (le is not None and not v <= le)
           or (lt is not None and not v < lt) or not math.isfinite(v))
    if bad:
        rng = ", ".join(f"{op} {b:g}" for op, b in ((">", gt), (">=", ge), ("<=", le), ("<", lt)) if b is not None)
        raise ValueError(f"snap {name!r}: {key} = {v:g} is out of range ({rng}){hint}")
    return v


def _material(spec: Dict[str, Any], name: str) -> Material:
    m = spec.get("material")
    if isinstance(m, str):
        if m not in MATERIALS:
            raise ValueError(f"snap {name!r}: unknown material {m!r}; moulded: {', '.join(sorted(MATERIALS))}; "
                             f"printed: {', '.join(sorted(PRINTED))}; or give {{name, strain, source, secant_mpa, "
                             "friction}}")
        return MATERIALS[m]
    if not isinstance(m, dict) or not m.get("source"):
        raise ValueError(f"snap {name!r}: material must be a known name or a mapping with strain (a fraction) and "
                         "source")
    frac = " (a fraction: 0.03 = 3 %)"
    strain = _num(m, "strain", name, required=True, gt=0, le=0.5, hint=frac)
    secant = _num(m, "secant_mpa", name, gt=0)
    return Material(str(m.get("name", "custom")), strain, str(m["source"]),
                    friction=_num(m, "friction", name, ge=0, le=1.5),
                    secant_mpa={strain: secant} if secant is not None else {})


def _section(spec: Dict[str, Any], name: str) -> Section:
    s = spec.get("section")
    if isinstance(s, dict) and isinstance(s.get("rect"), dict):
        r = s["rect"]
        return rect_section(_num(r, "width_mm", name, required=True, gt=0),
                            _num(r, "thickness_mm", name, required=True, gt=0))
    if isinstance(s, dict) and isinstance(s.get("ring"), dict):
        r = s["ring"]
        return ring_section(_num(r, "r_inner_mm", name, required=True, gt=0),
                            _num(r, "r_outer_mm", name, required=True, gt=0),
                            _num(r, "arc_deg", name, required=True, gt=0, le=360), r.get("tension", "convex"))
    raise ValueError(f"snap {name!r}: section must be {{rect: {{width_mm, thickness_mm}}}} or "
                     "{ring: {r_inner_mm, r_outer_mm, arc_deg}}")


def secant_at(points: Dict[float, float], strain: float) -> float:
    """Secant modulus at ``strain`` from (strain -> Es) points: linear between points, the end value outside them."""
    pts = sorted(points.items())
    if strain <= pts[0][0]:
        return pts[0][1]
    for (e0, s0), (e1, s1) in zip(pts, pts[1:]):
        if strain <= e1:
            return s0 + (s1 - s0) * (strain - e0) / (e1 - e0)
    return pts[-1][1]


def check_spec_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    """One cantilever snap from a declaration (see docs/compliant.md for the fields). Inputs are range-checked (a
    ValueError names the snap and field). The process must be stated; a layered part needs its orientation (and,
    unless it is a datasheet filament, a sourced ``process_factor``); a missing one is a failing row, so layer lines
    are never forgotten."""
    if not isinstance(spec, dict):
        raise ValueError(f"each snap must be a mapping, not {spec!r}")
    name = str(spec.get("name", "snap"))
    if spec.get("type", "cantilever") != "cantilever":
        raise ValueError(f"snap {name!r}: only cantilever snaps are declared in files so far; use the Python API "
                         "for torsion and annular joints")
    for flag in ("repeated", "same_material"):
        if flag in spec and not isinstance(spec[flag], bool):
            raise ValueError(f"snap {name!r}: {flag} must be true or false")
    printed = PRINTED.get(spec["material"]) if isinstance(spec.get("material"), str) else None
    length = _num(spec, "length_mm", name, required=True, gt=0)
    undercut = _num(spec, "undercut_mm", name, required=True, gt=0)
    share = _num(spec, "share", name, gt=0, le=1, default=1.0)
    design = spec.get("design", 1)
    if design not in DESIGN_K:
        raise ValueError(f"snap {name!r}: design must be 1, 2 or 3, not {design!r}")
    pf = _num(spec, "process_factor", name, gt=0, le=1, hint=": a derating cannot raise the allowable")
    section = _section(spec, name)
    repeated = bool(spec.get("repeated", False))
    raw_process = spec.get("process")
    process = str(raw_process).strip().lower() if raw_process is not None else ("fdm" if printed else "")
    extra: List[Dict[str, Any]] = []
    if process and process not in PROCESSES:
        raise ValueError(f"snap {name!r}: unknown process {process!r}; one of {', '.join(PROCESSES)}")
    eps = root_strain(section, length, undercut * share, design)
    modulus_note = retention_note = retention_secant = None
    if printed is not None:
        if PROCESSES.get(process) != "layered" or process not in ("fdm", "fff"):
            raise ValueError(f"snap {name!r}: {printed.name} is a filament datasheet; process must be fdm")
        orientation = spec.get("orientation")
        if orientation not in DIRECTIONS:
            extra.append({"check": "print orientation", "value": orientation, "limit": "stated", "pass": False,
                          "detail": "state orientation: 'along' (bending stress along the layers, arm lies in XY) "
                                    "or 'across' (arm built along Z); checked here as 'across'"})
            orientation = "across"
        allow = printed.allowable(orientation, repeated) * (pf if pf is not None else 1.0)
        secant = _num(spec, "secant_mpa", name, gt=0)
        retention_secant = secant
        secant_basis = retention_basis = "given"
        if secant is None:
            secant, retention_secant = printed.secant_upper_bound(orientation), printed.retention_modulus(orientation)
            secant_basis = "datasheet tensile modulus (an upper bound on the secant modulus)"
            retention_basis = secant_basis
            modulus_note = retention_note = "upper bound: datasheet modulus"
            if retention_secant != secant:
                secant_basis = ("the highest datasheet tensile modulus of its editions, for mating force (an upper "
                                "bound on the secant modulus)")
                retention_basis = ("the lowest datasheet tensile modulus of its editions, for retention force (still "
                                   "above the secant modulus)")
                modulus_note = "upper bound: the highest edition's datasheet modulus"
                retention_note = "upper bound: the lowest edition's datasheet modulus"
        friction = _num(spec, "friction", name, ge=0, le=1.5, default=printed.mu(spec.get("same_material", True)))
        material = dict(printed.derivation(orientation, repeated), allowable=allow, process=process,
                        process_factor=pf, secant_mpa=secant, secant_basis=secant_basis,
                        retention_secant_mpa=retention_secant, retention_secant_basis=retention_basis,
                        friction=friction)
    else:
        mat = _material(spec, name)
        if not process:
            extra.append({"check": "process", "value": None, "limit": "stated", "pass": False,
                          "detail": f"state process ({', '.join(PROCESSES)}): a printed part is weaker across its "
                                    "layers than the moulded data assume"})
        elif PROCESSES[process] == "layered" and (pf is None or not spec.get("process_source")
                                                  or spec.get("orientation") not in DIRECTIONS):
            extra.append({"check": "process derating", "value": pf, "limit": "stated", "pass": False,
                          "detail": f"a {process} part in a moulding-guide material needs orientation (along or "
                                    "across the layers), process_factor and process_source"})
        allow = mat.allowable(repeated, pf if pf is not None else 1.0)
        secant = _num(spec, "secant_mpa", name, gt=0)
        secant_basis = "given"
        if secant is None and mat.secant_mpa:
            secant = secant_at(mat.secant_mpa, eps)
            lo, hi = min(mat.secant_mpa), max(mat.secant_mpa)
            secant_basis = (f"interpolated at the root strain {eps * 100:.2f} % from the guide's points" if lo <= eps <= hi
                            else f"the guide's nearest point ({(lo if eps < lo else hi) * 100:g} %), held: the root "
                                 f"strain {eps * 100:.2f} % is outside the points")
        friction = _num(spec, "friction", name, ge=0, le=1.5, default=mat.mu(spec.get("same_material", True)))
        material = {"name": mat.name, "strain": mat.strain, "source": mat.source, "allowable": allow,
                    "repeated": repeated, "process": process or None, "orientation": spec.get("orientation"),
                    "process_factor": pf, "process_source": spec.get("process_source"), "secant_mpa": secant,
                    "secant_basis": secant_basis if secant is not None else None, "friction": friction}
    r = check_cantilever(length=length, section=section, undercut=undercut, strain_allow=allow, design=design,
                         secant_mpa=secant, friction=friction,
                         lead_deg=_num(spec, "lead_deg", name, gt=0, lt=90),
                         return_deg=_num(spec, "return_deg", name, gt=0, le=90),
                         root_radius=_num(spec, "root_radius_mm", name, ge=0), share=share,
                         max_mating_n=_num(spec, "max_mating_n", name, gt=0),
                         min_retention_n=_num(spec, "min_retention_n", name, gt=0), name=name,
                         modulus_note=modulus_note, retention_secant_mpa=retention_secant,
                         retention_note=retention_note)
    r["rows"] = extra + r["rows"]
    r["pass"] = all(row["pass"] for row in r["rows"])
    r["material"] = material
    return r


def check_spec(data: Any) -> Dict[str, Any]:
    snaps = data.get("snaps") if isinstance(data, dict) else None
    if not isinstance(snaps, list) or not snaps:
        raise ValueError("the file needs a non-empty 'snaps' list")
    results = [check_spec_entry(s) for s in snaps]
    return {"pass": all(r["pass"] for r in results), "snaps": results, "method": GUIDE, "limits": list(LIMITS)}
