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
sized; a printed (FDM) part is weaker across its layers than along them, which this module does not know unless the
caller passes a process factor from a measured or sourced value (``process_factor``). Use FEA for large deflection
and print and measure a coupon before relying on a number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    "a printed part's inter-layer strength and strain are lower than in-plane; pass a sourced process_factor and "
    "orient arms so bending stress runs along the layers",
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

    def allowable(self, repeated: bool = False, process_factor: float = 1.0) -> float:
        return self.strain * (REPEATED_USE_FACTOR if repeated else 1.0) * process_factor

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
    c_concave = ybar - r_inner * math.cos(th)
    if tension not in ("convex", "concave"):
        raise ValueError("tension must be 'convex' or 'concave'")
    c, other = (c_convex, c_concave) if tension == "convex" else (c_concave, c_convex)
    return Section(area, inertia, c, other, "ring", {"r1": r_inner, "r2": r_outer, "arc_deg": arc_deg, "ybar": ybar})


# ----------------------------------------------------------------------------- cantilever

# Table 1 deflection factors: y = k * eps * l^2 / c for any section (shape D), by design:
#   1 constant section; 2 thickness tapering linearly to h/2 at the hook; 3 width tapering to b/4 at the hook.
# For a rectangle (c = h/2) these are the guide's 0.67, 1.09 and 0.86 * eps * l^2 / h.
DESIGN_K = {1: 0.33, 2: 0.55, 3: 0.43}
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


# ----------------------------------------------------------------------------- torsion

def torsion_snap(bar_length: float, bar_radius: float, strain: float, secant_mpa: float, lever_mm: float,
                 bars: int = 2, poisson: float = POISSON_PLASTICS) -> Dict[str, float]:
    """Section C, circular torsion bar(s): permissible twist and the force at a lever arm.

    gamma_pm ~ (1 + nu) eps_pm; phi_pm = 180/pi * gamma_pm * l / r; G = Es / (2 (1 + nu)); Ip = pi r^4 / 2;
    P * lever = bars * G * Ip * gamma / r. The guide's factor 2 is for two bars (Fig. 21)."""
    gamma = (1.0 + poisson) * strain
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
                     name: str = "snap") -> Dict[str, Any]:
    """Deterministic pass/fail rows for one cantilever snap. ``strain_allow`` already includes repeated-use and
    process derating (see :meth:`Material.allowable`)."""
    y = undercut * share
    eps = root_strain(section, length, y, design)
    rows: List[Dict[str, Any]] = [{
        "check": "root strain", "value": eps, "limit": strain_allow, "pass": eps <= strain_allow,
        "detail": f"{eps * 100:.2f} % at {y:.3f} mm deflection vs {strain_allow * 100:.2f} % allowed"}]
    h = section.c + section.c_other
    if root_radius is not None:
        rows.append({"check": "root radius", "value": root_radius, "limit": MIN_ROOT_RADIUS_MM,
                     "pass": root_radius >= MIN_ROOT_RADIUS_MM,
                     "detail": f"R {root_radius:.2f} mm (minimum 0.38 mm); R/h {root_radius / h:.2f}"
                               + ("" if root_radius / h >= TARGET_ROOT_RATIO else
                                  f" below {TARGET_ROOT_RATIO}: the root concentrates strain (Fig. 9)")})
    out: Dict[str, Any] = {"name": name, "strain": eps, "deflection_mm": y, "rows": rows}
    if secant_mpa is not None:
        p = deflection_force(section, length, eps, secant_mpa)
        out["deflection_force_n"] = p
        if friction is not None and lead_deg is not None:
            w = mating_force(p, friction, lead_deg)
            out["mating_force_n"] = w
            if max_mating_n is not None:
                rows.append({"check": "mating force", "value": w, "limit": max_mating_n, "pass": w <= max_mating_n,
                             "detail": f"{w:.1f} N to assemble vs {max_mating_n:.1f} N allowed"})
        if friction is not None and return_deg is not None:
            s = mating_force(p, friction, return_deg)
            out["separation_force_n"] = s
            if min_retention_n is not None:
                rows.append({"check": "retention force", "value": s, "limit": min_retention_n,
                             "pass": s >= min_retention_n,
                             "detail": ("self-locking (inseparable by pulling)" if math.isinf(s) else
                                        f"{s:.1f} N to pull apart") + f" vs {min_retention_n:.1f} N required"})
    out["pass"] = all(r["pass"] for r in rows)
    out["limits"] = list(LIMITS)
    out["method"] = GUIDE
    return out


# ----------------------------------------------------------------------------- spec files

LAYERED_PROCESSES = ("fdm", "fff")


def _material(spec: Dict[str, Any]) -> Material:
    m = spec.get("material")
    if isinstance(m, str):
        if m not in MATERIALS:
            raise ValueError(f"unknown material {m!r}; known: {', '.join(sorted(MATERIALS))}, or give "
                             "{strain, source, secant_mpa, friction}")
        return MATERIALS[m]
    if not isinstance(m, dict) or "strain" not in m or not m.get("source"):
        raise ValueError("material must be a known name or a mapping with strain (fraction) and source")
    secant = {float(m["strain"]): float(m["secant_mpa"])} if "secant_mpa" in m else {}
    return Material(m.get("name", "custom"), float(m["strain"]), str(m["source"]), friction=m.get("friction"),
                    secant_mpa=secant)


def _section(spec: Dict[str, Any]) -> Section:
    s = spec.get("section") or {}
    if "rect" in s:
        return rect_section(float(s["rect"]["width_mm"]), float(s["rect"]["thickness_mm"]))
    if "ring" in s:
        r = s["ring"]
        return ring_section(float(r["r_inner_mm"]), float(r["r_outer_mm"]), float(r["arc_deg"]),
                            r.get("tension", "convex"))
    raise ValueError("section must be {rect: {width_mm, thickness_mm}} or {ring: {r_inner_mm, r_outer_mm, arc_deg}}")


def check_spec_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    """One cantilever snap from a declaration (see docs/compliant.md for the fields). A part made in layers (FDM)
    must state its build orientation relative to the arm's bending stress and a sourced ``process_factor``; a missing
    one fails, so layer lines are never forgotten."""
    if spec.get("type", "cantilever") != "cantilever":
        raise ValueError("only cantilever snaps are declared in files so far; use the Python API for torsion/annular")
    mat = _material(spec)
    process = str(spec.get("process", "")).lower()
    pf = spec.get("process_factor")
    extra: List[Dict[str, Any]] = []
    if process in LAYERED_PROCESSES and (pf is None or not spec.get("process_source") or not spec.get("orientation")):
        extra.append({"check": "process derating", "value": pf, "limit": "stated", "pass": False,
                      "detail": "a layered (FDM) part needs orientation (bending along or across layers), "
                                "process_factor and process_source"})
    allow = mat.allowable(bool(spec.get("repeated", False)), float(pf) if pf is not None else 1.0)
    secant = spec.get("secant_mpa")
    if secant is None and mat.secant_mpa:
        target = allow
        secant = min(mat.secant_mpa.items(), key=lambda kv: abs(kv[0] - target))[1]
    friction = spec.get("friction", mat.mu(bool(spec.get("same_material", True))))
    r = check_cantilever(length=float(spec["length_mm"]), section=_section(spec), undercut=float(spec["undercut_mm"]),
                         strain_allow=allow, design=int(spec.get("design", 1)), secant_mpa=secant, friction=friction,
                         lead_deg=spec.get("lead_deg"), return_deg=spec.get("return_deg"),
                         root_radius=spec.get("root_radius_mm"), share=float(spec.get("share", 1.0)),
                         max_mating_n=spec.get("max_mating_n"), min_retention_n=spec.get("min_retention_n"),
                         name=str(spec.get("name", "snap")))
    r["rows"] = extra + r["rows"]
    r["pass"] = all(row["pass"] for row in r["rows"])
    r["material"] = {"name": mat.name, "strain": mat.strain, "source": mat.source, "allowable": allow,
                     "repeated": bool(spec.get("repeated", False)), "process": process or None,
                     "orientation": spec.get("orientation"), "process_factor": pf,
                     "process_source": spec.get("process_source")}
    return r


def check_spec(data: Dict[str, Any]) -> Dict[str, Any]:
    snaps = data.get("snaps")
    if not isinstance(snaps, list) or not snaps:
        raise ValueError("the file needs a non-empty 'snaps' list")
    results = [check_spec_entry(s) for s in snaps]
    return {"pass": all(r["pass"] for r in results), "snaps": results, "method": GUIDE, "limits": list(LIMITS)}
