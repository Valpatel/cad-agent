"""Beams: the rectangular section, hollow rectangular and round tube sections, cantilever deflection and its curve,
beam stiffness by support, and the snap-fit arm.

SI units: metres, newtons, pascals, so strain is a fraction (0.02 = 2 %) and stiffness is in N/m.

Euler-Bernoulli theory throughout: small deflection, linear elastic and isotropic, plane sections stay plane, and
shear deflection is ignored, which is fine for slender beams (length over thickness above about 10). The snap-fit
arm functions do not re-derive anything. They call :mod:`cadagent.mechanical.compliant.snapfit`, the Covestro (Bayer) method
with the factors exactly as the guide prints them, so they give the same numbers as ``cad-agent snapfit``. The exact
taper integrals here (:func:`cantilever_taper_factor`) show where those factors come from: they round to the
guide's 0.67, 1.09 and 0.86.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from cadagent.mechanical.compliant import snapfit
from cadagent.formulas._registry import cite, formula

# Covestro Table 1 designs: 1 constant section, 2 thickness tapering linearly to h/2 at the hook, 3 width tapering
# linearly to b/4 at the hook.
DESIGNS = {1: "constant section", 2: "thickness tapered to h/2 at the tip", 3: "width tapered to b/4 at the tip"}
THICKNESS_TIP_RATIO = 0.5
WIDTH_TIP_RATIO = 0.25
SMALL_DEFLECTION = 0.1            # tip deflection over length; snapfit warns beyond it as well
SUPPORTS = {                      # k = coefficient * E I / L^3 for a point load at the free end or the centre
    "cantilever": 3.0,            # fixed - free, load at the free end
    "guided": 12.0,               # fixed - guided (the end moves sideways without turning: a parallel flexure blade)
    "simply-supported": 48.0,     # pinned - pinned, load at the centre
    "fixed-fixed": 192.0,         # fixed - fixed, load at the centre
}
_EB = ("Euler-Bernoulli: small deflection, linear elastic, isotropic; shear deflection ignored (length over "
       "thickness above about 10)")


def _design(design: int) -> int:
    if design not in DESIGNS:
        raise ValueError(f"design must be one of {sorted(DESIGNS)}: {DESIGNS}")
    return design


@formula(units={"width": "m", "thickness": "m"}, returns="second moment of area I, m^4",
         limits=("solid rectangle bending about the axis parallel to its width",),
         source=cite("roark", "Table A.1 (properties of plane areas), rectangle"))
def rect_second_moment(width: float, thickness: float) -> float:
    """Second moment of area of a solid rectangle about its centroidal axis along the width: I = b h^3 / 12."""
    return width * thickness ** 3 / 12.0


def _positive(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a finite number above 0, not {v!r}")
    return float(v)


def _hollow_rect(width: float, depth: float, wall: float) -> Tuple[float, float, float]:
    b, h, t = _positive("width", width), _positive("depth", depth), _positive("wall", wall)
    if 2.0 * t >= min(b, h):
        raise ValueError(f"wall {wall!r} must be under half of the smaller side {min(b, h)!r}: at half there is no "
                         "hole (use rect_second_moment)")
    return b, h, t


def _round_tube(diameter: float, wall: float) -> Tuple[float, float]:
    d, t = _positive("diameter", diameter), _positive("wall", wall)
    if 2.0 * t >= d:
        raise ValueError(f"wall {wall!r} must be under half of the outside diameter {diameter!r}")
    return d, t


_SHARP = ("sharp corners and one wall thickness all round: a rolled or formed tube has rounded corners, so its "
          "handbook value is a few per cent lower; use the maker's table for a bought section")
_TUBE = ("a plain concentric tube of one wall thickness (use the wall as made: a welded tube's design wall is thinner "
         "than its nominal)")
_NO_BUCKLE = ("the section's shape is taken to hold: no local buckling or crushing of a thin wall, which governs before "
              "yield in a thin tube")


@formula(units={"width": "m (outside, parallel to the bending axis)", "depth": "m (outside, across the bending axis)",
                "wall": "m"},
         returns="second moment of area I, m^4", limits=(_SHARP, "wall under half of the smaller side"),
         source=cite("roark", "Table A.1 (properties of sections), hollow rectangle: the outer rectangle less the "
                     "inner one about their common centroidal axis"))
def hollow_rect_second_moment(width: float, depth: float, wall: float) -> float:
    """Second moment of area of a hollow rectangle (a box tube) about its centroidal axis along the width:
    I = (b h^3 - (b - 2t)(h - 2t)^3) / 12."""
    b, h, t = _hollow_rect(width, depth, wall)
    return (b * h ** 3 - (b - 2.0 * t) * (h - 2.0 * t) ** 3) / 12.0


@formula(units={"width": "m (outside, parallel to the bending axis)", "depth": "m (outside, across the bending axis)",
                "wall": "m"},
         returns="elastic section modulus S = I / (h / 2), m^3",
         limits=(_SHARP, _NO_BUCKLE, "elastic bending: the outer fibre's stress is M / S up to yield"),
         source=cite("roark", "Table A.1 (properties of sections), hollow rectangle, with Section 8.1 (sigma = M c / "
                     "I)"))
def hollow_rect_section_modulus(width: float, depth: float, wall: float) -> float:
    """Elastic section modulus of a hollow rectangle about its centroidal axis along the width: S = I / (h / 2), so the
    outer fibre's bending stress is M / S."""
    return hollow_rect_second_moment(width, depth, wall) / (depth / 2.0)


@formula(units={"diameter": "m (outside)", "wall": "m"}, returns="second moment of area I, m^4",
         limits=(_TUBE, "wall under half of the outside diameter"),
         source=cite("roark", "Table A.1 (properties of sections), hollow circle"))
def round_tube_second_moment(diameter: float, wall: float) -> float:
    """Second moment of area of a round tube about a diameter: I = pi (D^4 - d^4) / 64, with d = D - 2t."""
    d, t = _round_tube(diameter, wall)
    return math.pi * (d ** 4 - (d - 2.0 * t) ** 4) / 64.0


@formula(units={"diameter": "m (outside)", "wall": "m"}, returns="elastic section modulus S = I / (D / 2), m^3",
         limits=(_TUBE, _NO_BUCKLE, "elastic bending: the outer fibre's stress is M / S up to yield"),
         source=cite("roark", "Table A.1 (properties of sections), hollow circle, with Section 8.1 (sigma = M c / I)"))
def round_tube_section_modulus(diameter: float, wall: float) -> float:
    """Elastic section modulus of a round tube: S = I / (D / 2), so the outer fibre's bending stress is M / S."""
    return round_tube_second_moment(diameter, wall) / (diameter / 2.0)


@formula(units={"force": "N", "modulus": "Pa", "inertia": "m^4", "length": "m"}, returns="tip deflection, m",
         limits=(_EB, "constant section; load at the free end"),
         source=cite("roark", "Section 8.1 and Table 8.1, case 1a (end load, left end free, right end fixed)"))
def cantilever_tip_deflection(force: float, modulus: float, inertia: float, length: float) -> float:
    """Tip deflection of a constant-section cantilever with an end load: y = F L^3 / (3 E I)."""
    return force * length ** 3 / (3.0 * modulus * inertia)


@formula(units={"modulus": "Pa", "inertia": "m^4", "length": "m", "support": "one of SUPPORTS"},
         returns="stiffness at the load point, N/m",
         limits=(_EB, "constant section; a point load at the free end (cantilever, guided) or at the centre "
                 "(simply supported, fixed-fixed)"),
         source=cite("roark", "Table 8.1, case 1 (concentrated load) with the named end conditions"))
def beam_stiffness(modulus: float, inertia: float, length: float, support: str = "cantilever") -> float:
    """Stiffness F / y of a beam under a point load: 3, 12, 48 or 192 E I / L^3 by support (see ``SUPPORTS``)."""
    if support not in SUPPORTS:
        raise ValueError(f"support must be one of {sorted(SUPPORTS)}")
    return SUPPORTS[support] * modulus * inertia / length ** 3


# Closed-form integrals of y'' = M / (E I(x)) for an end load, x from the root (xi = x / L). For design 2 the
# thickness is h0 (1 - (1 - r) xi) with r = 1/2; for design 3 the width is b0 (1 - beta xi) with beta = 3/4. Each is
# zero with zero slope at the root; the tests check them against numerical integration.
def _shape2(xi: float) -> float:
    r = THICKNESS_TIP_RATIO
    s = 1.0 - (1.0 - r) * xi
    return ((r - 1.0) - (r / 2.0 - 1.0) * s - math.log(s) - r / (2.0 * s)) / (1.0 - r) ** 3


def _shape3(xi: float) -> float:
    beta = 1.0 - WIDTH_TIP_RATIO
    u = 1.0 - beta * xi
    integral_log = -(u / beta) * (math.log(u) - 1.0) - 1.0 / beta     # integral of ln(1 - beta t) dt from 0 to xi
    return xi * xi / (2.0 * beta) - (beta - 1.0) / beta ** 2 * integral_log


def _raw_shape(xi: float, design: int) -> float:
    """y(x) / (L^2 C), with C = 12 F L / (E b0 h0^3): the deflection per unit of the root curvature scale."""
    if design == 1:
        return xi * xi * (3.0 - xi) / 6.0
    return _shape2(xi) if design == 2 else _shape3(xi)


@formula(units={"xi": "x / L, 0 at the root to 1 at the tip", "design": "1, 2 or 3 (Covestro Table 1)"},
         returns="y(x) / y_tip, dimensionless",
         limits=(_EB, "end load only; designs 2 and 3 taper linearly to h/2 and b/4 at the tip"),
         source=cite("roark", "Section 8.1 (the elastic curve, y'' = M / E I) and Table 8.1, case 1a; the tapers "
                     "integrated in closed form, as for the beams of variable section in Chapter 8"))
def cantilever_shape(xi: float, design: int = 1) -> float:
    """The deflected shape of an end-loaded cantilever, normalised to its tip: xi^2 (3 - xi) / 2 for a constant
    section, and the closed-form integrals for the tapered designs."""
    _design(design)
    if not 0.0 <= xi <= 1.0:
        raise ValueError("xi must be between 0 (root) and 1 (tip)")
    return _raw_shape(xi, design) / _raw_shape(1.0, design)


@formula(units={"xi": "x / L, 0 at the root to 1 at the tip", "design": "1, 2 or 3 (Covestro Table 1)"},
         returns="surface strain at x over the root strain, dimensionless",
         limits=(_EB, "end load only; the root is the peak for all three designs"),
         source=cite("roark", "Section 8.1 (sigma = M c / I) applied to the tapered sections of Covestro Table 1"))
def cantilever_strain_profile(xi: float, design: int = 1) -> float:
    """Outer-fibre strain along the arm over the root strain: (1 - xi), divided by (h / h0)^2 when the thickness tapers
    and by (b / b0) when the width tapers."""
    _design(design)
    if not 0.0 <= xi <= 1.0:
        raise ValueError("xi must be between 0 (root) and 1 (tip)")
    if design == 1:
        return 1.0 - xi
    if design == 2:
        return (1.0 - xi) / (1.0 - (1.0 - THICKNESS_TIP_RATIO) * xi) ** 2
    return (1.0 - xi) / (1.0 - (1.0 - WIDTH_TIP_RATIO) * xi)


@formula(units={"xi": "x / L, 0 at the root to 1 at the tip", "design": "1, 2 or 3 (Covestro Table 1)"},
         returns="thickness at x over the root thickness, dimensionless",
         limits=("linear taper as Covestro Table 1 draws it",),
         source=cite("covestro", "Table 1 (cantilever designs 1 to 3)"))
def cantilever_thickness_profile(xi: float, design: int = 1) -> float:
    """Thickness along the arm over the root thickness: 1, except design 2, which tapers linearly to 1/2."""
    _design(design)
    return 1.0 - (1.0 - THICKNESS_TIP_RATIO) * xi if design == 2 else 1.0


@formula(units={"design": "1, 2 or 3 (Covestro Table 1)"},
         returns="k in y = k * strain * L^2 / h, dimensionless",
         limits=(_EB, "rectangular section, end load"),
         source=cite("roark", "Section 8.1, integrated exactly; compare Covestro Table 1 (0.67, 1.09, 0.86)"))
def cantilever_taper_factor(design: int = 1) -> float:
    """Exact deflection factor of a rectangular arm: y = k eps L^2 / h with eps the root strain. 2/3 for a constant
    section, 1.0904 for the thickness taper and 0.8552 for the width taper."""
    _design(design)
    return 2.0 * _raw_shape(1.0, design)


_GUIDE = ("Covestro/Bayer closed form: small deflection, one part rigid, strain at the root's outer fibre; the "
          "factors are the guide's (0.67, 1.09, 0.86), as cad-agent snapfit uses them",)


@formula(units={"length": "m", "thickness": "m (at the root)", "deflection": "m (at the hook)",
                "design": "1, 2 or 3 (Covestro Table 1)"},
         returns="root strain, fraction", limits=_GUIDE + ("rectangular section",),
         source=cite("covestro", "Table 1 (permissible deflection y = k eps l^2 / h); computed by "
                     "cadagent.mechanical.compliant.snapfit"))
def snap_root_strain(length: float, thickness: float, deflection: float, design: int = 1) -> float:
    """Root strain of a rectangular snap arm deflected by ``deflection`` at the hook: eps = y h / (k L^2)."""
    return snapfit.root_strain(snapfit.rect_section(1.0, thickness), length, deflection, _design(design))


@formula(units={"length": "m", "width": "m", "thickness": "m (at the root)", "strain": "fraction (at the root)",
                "modulus": "Pa (secant modulus at that strain)"},
         returns="deflection force at the hook, N", limits=_GUIDE + ("rectangular section",),
         source=cite("covestro", "Table 1, bottom row (P = Z Es eps / l); computed by cadagent.mechanical.compliant.snapfit"))
def snap_deflection_force(length: float, width: float, thickness: float, strain: float, modulus: float) -> float:
    """Force that deflects a rectangular snap arm to the given root strain: P = (b h^2 / 6) Es eps / L."""
    return snapfit.deflection_force(snapfit.rect_section(width, thickness), length, strain, modulus)


@formula(units={"length": "m", "thickness": "m (at the root)", "width": "m (at the root)", "deflection": "m",
                "modulus": "Pa", "allowable_strain": "fraction", "design": "1, 2 or 3 (Covestro Table 1)"},
         returns="dict: strain, force (N), stiffness (N/m: P / y, the same at any deflection in this linear model, "
                 "zero deflection included), ratio, passes, small_deflection, permissible_deflection (m)",
         limits=_GUIDE + ("rectangular section; a pass has no extra margin (the guide designs to half the "
                          "permissible strain)", "not proof of strength: print a coupon and measure"),
         source=cite("covestro", "Table 1; computed by cadagent.mechanical.compliant.snapfit"))
def snap_arm(length: float, thickness: float, width: float, deflection: float, modulus: float,
             allowable_strain: float, design: int = 1) -> Dict[str, Any]:
    """One rectangular snap arm: root strain, deflection force and stiffness, strain over the allowable, pass or fail,
    and whether the deflection is still small (at most a tenth of the length)."""
    section = snapfit.rect_section(width, thickness)
    strain = snap_root_strain(length, thickness, deflection, design)
    force = snap_deflection_force(length, width, thickness, strain, modulus)
    # P / y = b h^3 Es / (6 k L^3) whatever the deflection: the force at a unit deflection, so an arm at rest still
    # reports its stiffness rather than 0
    stiffness = snap_deflection_force(length, width, thickness, snap_root_strain(length, thickness, 1.0, design), modulus)
    return {"strain": strain, "force": force, "stiffness": stiffness,
            "ratio": strain / allowable_strain, "passes": strain <= allowable_strain,
            "small_deflection": deflection <= SMALL_DEFLECTION * length,
            "permissible_deflection": snapfit.permissible_deflection(section, length, allowable_strain, design)}
