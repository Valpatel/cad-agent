"""Compression limiters and the clamped joint round them: the screw's proof load, the limiter's length against the
clamped plastic, the stress in its wall, the bearing pressure under the head, its press fit in a hole, and the
preload a joint keeps when the plastic in its clamp path relaxes.

SI units: metres, newtons, pascals.

A compression limiter is a metal tube through a plastic part, round the screw. Tightened, the head (or washer) bears
on the tube and the tube on the part below, so the screw's clamp goes through metal and not through the plastic,
which would creep and let the preload fall. It works only when the tube is long enough: a tube shorter than the
plastic lets the head squeeze the plastic first, and a tube much longer leaves the plastic loose. These relations
give the numbers; :mod:`cadagent.mechanical.inserts` checks a joint with them.

Limits: linear elastic metal, the plastic as a spring of its datasheet modulus, no settling (embedding) of the metal
faces, and relaxation taken from a measured ratio, not computed. A closed form is not proof of strength. Test the
joint.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from cadagent.formulas._registry import cite, formula
from cadagent.formulas.screws import tensile_stress_area

# Shigley 10th ed., Section 8-9: the preload to aim for, as a share of the proof load, for a joint that
# is taken apart again (0.75) and for a permanent one (0.90).
PRELOAD_SHARE = {"reused": 0.75, "permanent": 0.90}
_ELASTIC = "linear elastic, static; the load uniform over the section"


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _positive(name: str, v: Any, strict: bool = True) -> float:
    if not (_num(v) and (v > 0 if strict else v >= 0)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} 0, not {v!r}")
    return float(v)


@formula(units={"diameter": "m (nominal)", "pitch": "m", "proof_strength": "Pa (the property class's, e.g. 970e6 "
                                                                                "for 12.9)"},
         returns="proof load, N",
         limits=("ISO metric 60 degree thread; the proof strength is the class minimum, so the proof load is a floor, "
                 "not the strength of one screw",),
         source=cite("shigley", "Section 8-9 (the proof load Fp = At Sp) and Table 8-11 (the classes' proof strengths)"))
def proof_load(diameter: float, pitch: float, proof_strength: float) -> float:
    """Proof load of a screw: its tensile stress area times its property class's proof strength, Fp = At Sp."""
    _positive("proof_strength", proof_strength)
    return tensile_stress_area(_positive("diameter", diameter), _positive("pitch", pitch)) * proof_strength


@formula(units={"load": "N (compressive or tensile)", "outer_diameter": "m", "inner_diameter": "m (0 for a disc)"},
         returns="stress on the annulus, Pa (load over its area)",
         limits=(_ELASTIC, "a short tube or a flat bearing face: no buckling, no stress concentration at the edges, "
                           "full contact over the annulus"),
         source=cite("shigley", "Section 3-9 (Uniformly Distributed Stresses: sigma = F / A)"))
def annulus_stress(load: float, outer_diameter: float, inner_diameter: float) -> float:
    """Stress on an annulus carrying an axial load: a limiter's wall (its outside and bore), or the bearing pressure
    under a screw head or washer (its outside and the hole under it): sigma = F / (pi / 4 (D^2 - d^2))."""
    _positive("load", load, strict=False)
    _positive("inner_diameter", inner_diameter, strict=False)
    if not (_num(outer_diameter) and outer_diameter > inner_diameter):
        raise ValueError(f"outer_diameter must be finite and above the inner diameter, not {outer_diameter!r}")
    return load / (math.pi / 4.0 * (outer_diameter ** 2 - inner_diameter ** 2))


@formula(units={"limiter_length": "m (nominal)", "plastic_thickness": "m (the clamped plastic, nominal)",
                "limiter_tolerance": "m (+/-)", "plastic_tolerance": "m (+/-)"},
         returns="dict: standout {nominal, low, high} (limiter length minus plastic thickness, m) and state: 'proud' "
                 "(always longer: the clamp goes through the limiter, the plastic is held loose up to the standout), "
                 "'short' (always shorter: the head squeezes the plastic by the shortfall before it reaches the "
                 "limiter) or 'either' (the band spans flush: some joints are each)",
         limits=("worst-case stack of two symmetric tolerances (no statistics); the plastic's thickness under load, "
                 "not as printed, is what counts, and a printed face is not flat to a few hundredths",),
         source=cite("shigley", "Section 1-14 (Dimensions and Tolerances: worst-case stack of a chain of dimensions)"))
def limiter_stack(limiter_length: float, plastic_thickness: float, limiter_tolerance: float = 0.0,
                  plastic_tolerance: float = 0.0) -> Dict[str, Any]:
    """The limiter's standout over the plastic it passes through, with the tolerances stacked worst case: s = L - t,
    from (L - tol_L) - (t + tol_t) to (L + tol_L) - (t - tol_t)."""
    L, t = _positive("limiter_length", limiter_length), _positive("plastic_thickness", plastic_thickness)
    tl = _positive("limiter_tolerance", limiter_tolerance, strict=False)
    tp = _positive("plastic_tolerance", plastic_tolerance, strict=False)
    low, high = (L - tl) - (t + tp), (L + tl) - (t - tp)
    state = "proud" if low > 0 else "short" if high < 0 else "either"
    return {"standout": {"nominal": L - t, "low": low, "high": high}, "state": state}


@formula(units={"shortfall": "m (how much shorter the limiter is than the plastic; 0 or less: none)",
                "plastic_stiffness": "N/m (the plastic under the head: E A / t)", "preload": "N"},
         returns="load the plastic carries, N (at most the whole preload)",
         limits=("the plastic as a linear spring of its datasheet modulus over the bearing annulus, until the head "
                 "meets the limiter; past its compressive yield it crushes and carries less than this",
                 "the metal is rigid next to the plastic"),
         source=cite("shigley", "Section 8-7 (Tension Joints: the external load shared by stiffness), with the "
                     "head meeting the limiter as a gap that closes"))
def limiter_plastic_load(shortfall: float, plastic_stiffness: float, preload: float) -> float:
    """Load the plastic takes when the limiter is short: the head must squeeze it by the shortfall before it reaches
    the limiter, so it carries k s, up to the whole preload (then the limiter never takes any)."""
    _positive("plastic_stiffness", plastic_stiffness)
    _positive("preload", preload, strict=False)
    if not _num(shortfall):
        raise ValueError(f"shortfall must be a finite number, not {shortfall!r}")
    return min(plastic_stiffness * max(shortfall, 0.0), preload)


@formula(units={"interference": "m (diametral: the tube's outside minus the hole)", "diameter": "m (nominal fit)",
                "hub_outer_diameter": "m (the plastic round the hole)", "hub_modulus": "Pa", "hub_poisson": "-",
                "shaft_modulus": "Pa (the tube's)", "shaft_poisson": "-",
                "shaft_inner_diameter": "m (the tube's bore; 0 for a solid pin)"},
         returns="contact pressure at the fit, Pa",
         limits=("Lame thick-walled cylinders, linear elastic, isotropic, plane stress, the same length; a printed "
                 "hole is neither round nor isotropic, and the plastic relaxes, so the pressure falls with time",),
         source=cite("shigley", "Section 3-16 (Press and Shrink Fits: the interface pressure of two cylinders of different "
                     "materials)"))
def press_fit_pressure(interference: float, diameter: float, hub_outer_diameter: float, hub_modulus: float,
                       hub_poisson: float, shaft_modulus: float, shaft_poisson: float,
                       shaft_inner_diameter: float = 0.0) -> float:
    """Contact pressure of a press fit: p = delta / (R/Eo ((ro^2 + R^2)/(ro^2 - R^2) + nu_o) + R/Ei ((R^2 + ri^2) /
    (R^2 - ri^2) - nu_i)), with delta the radial interference, half the diametral one."""
    _positive("interference", interference, strict=False)
    d = _positive("diameter", diameter)
    di = _positive("shaft_inner_diameter", shaft_inner_diameter, strict=False)
    if not (_num(hub_outer_diameter) and hub_outer_diameter > d):
        raise ValueError(f"hub_outer_diameter must be finite and above the diameter, not {hub_outer_diameter!r}")
    if di >= d:
        raise ValueError(f"shaft_inner_diameter must be below the diameter, not {shaft_inner_diameter!r}")
    for name, v in (("hub_modulus", hub_modulus), ("shaft_modulus", shaft_modulus)):
        _positive(name, v)
    for name, v in (("hub_poisson", hub_poisson), ("shaft_poisson", shaft_poisson)):
        if not (_num(v) and 0.0 <= v < 0.5):
            raise ValueError(f"{name} must be from 0 to below 0.5, not {v!r}")
    R, ro, ri = d / 2.0, hub_outer_diameter / 2.0, di / 2.0
    hub = R / hub_modulus * ((ro ** 2 + R ** 2) / (ro ** 2 - R ** 2) + hub_poisson)
    shaft = R / shaft_modulus * ((R ** 2 + ri ** 2) / (R ** 2 - ri ** 2) - shaft_poisson)
    return (interference / 2.0) / (hub + shaft)


@formula(units={"pressure": "Pa (at the fit)", "diameter": "m", "length": "m (engaged)", "friction": "-"},
         returns="force to push the fit apart, N",
         limits=("Coulomb friction over the whole engaged surface at the elastic pressure; the static friction of "
                 "steel on a printed wall is not measured, and the pressure relaxes",),
         source=cite("shigley", "Section 3-16 (Press and Shrink Fits) for the pressure; the force is Coulomb "
                     "friction over the contact area"))
def press_fit_force(pressure: float, diameter: float, length: float, friction: float) -> float:
    """Force to push a press fit apart: F = f p pi d L."""
    for name, v in (("pressure", pressure), ("friction", friction)):
        _positive(name, v, strict=False)
    return friction * pressure * math.pi * _positive("diameter", diameter) * _positive("length", length)


@formula(units={"relaxation": "dimensionless (stress kept by the plastic at constant strain, 0 to 1, measured)",
                "stiffness_ratio": "dimensionless (the plastic's clamp stiffness over the screw's, km / kb)"},
         returns="share of the preload kept, 0 to 1",
         limits=("the quasi-elastic method: the plastic's modulus replaced by its relaxation modulus E(t) = r E0 at "
                 "a fixed total length (the nut does not turn); one plastic member in series with an elastic screw",
                 "the relaxation ratio is taken from published data at the right stress, temperature and time; it is "
                 "not computed, and printed parts relax faster than moulded ones"),
         source=cite("shigley", "Section 8-7 (Tension Joints: screw and members as springs in series), with the "
                     "member's modulus replaced by the relaxation modulus"))
def preload_retained(relaxation: float, stiffness_ratio: float) -> float:
    """Preload kept when the plastic in the clamp path relaxes to r of its stress at a fixed length: F/F0 = r (1 +
    phi) / (1 + r phi), phi = km / kb. A soft plastic member (phi small) passes its relaxation straight to the
    preload; a stiff one next to a long screw (phi large) keeps more."""
    if not (_num(relaxation) and 0.0 <= relaxation <= 1.0):
        raise ValueError(f"relaxation must be from 0 to 1, not {relaxation!r}")
    phi = _positive("stiffness_ratio", stiffness_ratio, strict=False)
    return relaxation * (1.0 + phi) / (1.0 + relaxation * phi)


@formula(units={"plastic_load": "N (the plastic's share of the preload)", "preload": "N",
                "relaxation": "dimensionless (0 to 1, measured)"},
         returns="share of the preload kept, 0 to 1",
         limits=("the limiter and screw as rigid next to the plastic: the plastic holds its strain and relaxes to r "
                 "of its load, the limiter keeps its own; metal settling (embedding) is not modelled",),
         source=cite("shigley", "Section 8-7 (Tension Joints: parallel members share a fixed deflection)"))
def preload_retained_limited(plastic_load: float, preload: float, relaxation: float) -> float:
    """Preload kept by a joint with a compression limiter: the limiter's share stays and the plastic's relaxes, F/F0 =
    (F0 - Fp + r Fp) / F0. With no load in the plastic (a flush or proud limiter) it is all kept."""
    F0 = _positive("preload", preload)
    Fp = _positive("plastic_load", plastic_load, strict=False)
    if Fp > F0:
        raise ValueError(f"plastic_load cannot exceed the preload, not {plastic_load!r}")
    if not (_num(relaxation) and 0.0 <= relaxation <= 1.0):
        raise ValueError(f"relaxation must be from 0 to 1, not {relaxation!r}")
    return (F0 - Fp + relaxation * Fp) / F0
