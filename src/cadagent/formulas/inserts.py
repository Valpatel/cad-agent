"""Threaded inserts in plastic: the plastic a heat-set insert pushes aside, the pocket below it that takes the melt,
its pull-out, push-out and torque-out from a shear model calibrated to published tests, which way the screw's
tension loads it, and the tightening torque the insert (not the screw) allows.

SI units: metres, newtons, pascals; torque in N m.

**The shear model.** An insert pulled, pushed or turned out of plastic fails by shearing the plastic round its knurl,
on a cylinder near the knurl's crests. Its capacity is then a shear strength times that cylinder's area (or its area
times its radius, for torque), times a calibration factor c that lumps everything the model leaves out: the knurl's
interlock, the shape of the shear surface, how well the melt bonded, and the strength of plastic that was melted and
cooled round the insert. c is fitted to published tests, not derived; :mod:`cadagent.mechanical.inserts` holds the
tests, fits c from them and passes it here. Outside the inserts, materials and holes it was fitted on, the result is
a guess with a band.

**The clamp path.** Tightening a screw pulls its insert towards the head. Whether that pull goes into the knurl
(the insert is jacked out of the boss: the classic failure) or into a face that carries it (a shoulder in front of
the insert, or the clamped part itself) decides how much torque the joint takes. :func:`insert_clamp_path` names
the path from where the insert sits; :func:`insert_limited_torque` gives the torque each path allows, with
:func:`cadagent.formulas.nut_factor` for the split of torque between the thread (which turns the insert) and the
head.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from cadagent.formulas._registry import cite, formula
from cadagent.formulas.screws import nut_factor

PATHS = ("seat", "through-insert", "jack-out")
INSTALLED_FROM = ("joint face", "far side")
_SHEAR = ("the plastic shears on a cylinder at the knurl's crests over the engaged length; c, fitted to published "
          "tests, carries the knurl's interlock and the melt's bond, so the result holds near the tests it came from")
_STATIC = "static, short-term load at room temperature; a held load creeps and a hot one is weaker"


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _positive(name: str, v: Any, strict: bool = True) -> float:
    if not (_num(v) and (v > 0 if strict else v >= 0)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} 0, not {v!r}")
    return float(v)


@formula(units={"insert_volume": "m^3 (the insert's metal, from its CAD)", "hole_diameter": "m",
                "bore_diameter": "m (the insert's threaded bore, which stays empty)", "length": "m (the insert's)"},
         returns="volume of plastic the insert pushes aside, m^3: above 0 it must flow somewhere (up round the insert "
                 "or into the pocket below), below 0 the knurl's valleys are left partly empty",
         limits=("a straight hole as deep as the insert; the volume of the metal, not of the knurl's envelope; the "
                 "plastic is incompressible and none is lost to the iron",),
         source=cite("shigley", "Section 1-14 (Dimensions and Tolerances: a volume balance of the parts as drawn)"))
def insert_displaced_volume(insert_volume: float, hole_diameter: float, bore_diameter: float, length: float) -> float:
    """Plastic an insert displaces as it goes into its hole: its metal plus its empty bore, less the hole it fills,
    V = V_insert - pi / 4 (Dh^2 - db^2) L."""
    V = _positive("insert_volume", insert_volume)
    Dh, db = _positive("hole_diameter", hole_diameter), _positive("bore_diameter", bore_diameter)
    if db >= Dh:
        raise ValueError(f"bore_diameter must be below the hole diameter, not {bore_diameter!r}")
    return V - math.pi / 4.0 * (Dh ** 2 - db ** 2) * _positive("length", length)


@formula(units={"hole_diameter": "m", "depth": "m (of the blind hole)", "length": "m (the insert's)"},
         returns="volume of the pocket below a seated insert, m^3 (0 when the hole is no deeper than the insert)",
         limits=("a straight blind hole; a cone at the bottom adds a little; melt that freezes on the way does not "
                 "reach the pocket",),
         source=cite("shigley", "Section 1-14 (Dimensions and Tolerances: the space left in a blind hole)"))
def overflow_volume(hole_diameter: float, depth: float, length: float) -> float:
    """Volume of the pocket below an insert seated flush in a blind hole, pi / 4 Dh^2 (depth - L): where pushed-aside
    melt can go instead of welling up round the insert."""
    Dh = _positive("hole_diameter", hole_diameter)
    return math.pi / 4.0 * Dh ** 2 * max(_positive("depth", depth) - _positive("length", length), 0.0)


@formula(units={"outer_diameter": "m (the knurl's crests)", "length": "m (engaged in plastic)",
                "shear_strength": "Pa (the plastic's, across its weakest plane)",
                "calibration": "dimensionless (c, fitted to published tests of this load direction)"},
         returns="force that pulls (or pushes) the insert out, N",
         limits=(_SHEAR, _STATIC),
         source=cite("shigley", "Section 3-9 (Uniformly Distributed Stresses: tau = F / A on the shear cylinder), "
                     "with c fitted to the published tests listed in cadagent.mechanical.inserts"))
def insert_shear_force(outer_diameter: float, length: float, shear_strength: float, calibration: float) -> float:
    """Axial force that shears an insert out of plastic: F = c tau pi D L, on the cylinder through the knurl's crests.
    The same form gives pull-out and push-out, each with its own c."""
    return (_positive("calibration", calibration) * _positive("shear_strength", shear_strength) * math.pi
            * _positive("outer_diameter", outer_diameter) * _positive("length", length))


@formula(units={"outer_diameter": "m (the knurl's crests)", "length": "m (engaged in plastic)",
                "shear_strength": "Pa", "calibration": "dimensionless (c, fitted to published torque-out tests)"},
         returns="torque that turns the insert in the plastic, N m",
         limits=(_SHEAR, _STATIC),
         source=cite("shigley", "Section 3-9 (Uniformly Distributed Stresses: tau on the shear cylinder, times its "
                     "radius), with c fitted to the published tests listed in cadagent.mechanical.inserts"))
def insert_shear_torque(outer_diameter: float, length: float, shear_strength: float, calibration: float) -> float:
    """Torque that turns an insert in plastic: T = c tau pi D^2 L / 2, the shear on the cylinder through the knurl's
    crests times its radius."""
    D = _positive("outer_diameter", outer_diameter)
    return (_positive("calibration", calibration) * _positive("shear_strength", shear_strength) * math.pi * D * D
            * _positive("length", length) / 2.0)


@formula(units={"recess": "m (the insert's head-side end below the joint face; below 0: proud of it)",
                "tolerance": "m (how far either way still counts as flush)",
                "installed_from": "'joint face' (pressed in from the face the clamped part sits on) or 'far side' "
                                  "(pressed in from the back, with boss material between it and the joint face)"},
         returns="dict: path ('seat', 'through-insert' or 'jack-out'), knurl_preload (the share of the preload the "
                 "knurl carries, 0 or 1), why and instead (what to do about it)",
         limits=("the screw's tension pulls the insert towards the head; a face in front of the insert carries it "
                 "only when it touches. Flush within the tolerance counts as touching the clamped part: a slightly "
                 "recessed insert jacks out until the gap closes, then carries the clamp",),
         source=cite("shigley", "Section 8-7 (Tension Joints: the clamp follows the stiff path between the head and "
                     "the thread)"))
def insert_clamp_path(recess: float, tolerance: float = 0.0, installed_from: str = "joint face") -> Dict[str, Any]:
    """Which way the screw's tension loads an insert: into its seat (a shoulder of the boss in front of it, when it
    was pressed in from the far side), through the insert to the clamped part (flush or proud), or into the knurl,
    pulling it out of the boss (recessed from the joint face: jack-out)."""
    if not _num(recess):
        raise ValueError(f"recess must be a finite number, not {recess!r}")
    tol = _positive("tolerance", tolerance, strict=False)
    if installed_from not in INSTALLED_FROM:
        raise ValueError(f"installed_from must be one of {INSTALLED_FROM}, not {installed_from!r}")
    if installed_from == "far side":
        if recess <= 0:
            raise ValueError("an insert pressed in from the far side sits behind a shoulder: its recess (the "
                             "shoulder's thickness) must be above 0")
        return {"path": "seat", "knurl_preload": 0.0,
                "why": "pressed in from the far side, the insert is pulled against the shoulder in front of it: the "
                       "shoulder carries the clamp in bearing, and the knurl only keeps the insert from turning",
                "instead": "check the shoulder against being punched through, and that the hole in it clears the "
                           "screw"}
    if recess <= tol:
        proud = recess < -tol
        return {"path": "through-insert", "knurl_preload": 0.0,
                "why": ("the insert stands proud, so the clamped part bears on it and not on the boss: the clamp "
                        "goes through the insert alone, and the boss is held to the joint only by the knurl"
                        if proud else
                        "flush, the insert's end bears on the clamped part: the clamp goes through the insert, and "
                        "the knurl carries only what pulls the parts apart"),
                "instead": ("set it flush: proud, the boss can rattle by the standout and any load that separates the "
                            "parts pulls the insert" if proud else
                            "keep it flush to within the tolerance; a separating load still pulls on the knurl")}
    return {"path": "jack-out", "knurl_preload": 1.0,
            "why": "recessed below the joint face, the insert is pulled towards the head until the gap closes: the "
                   "whole preload goes into the knurl, pulling the insert out of the boss",
            "instead": "press the insert in flush (the clamped part then bears on it), or from the far side against a "
                       "shoulder, or put a compression limiter or a flanged insert in the clamp path; otherwise keep "
                       "the torque under the pull-out limit"}


@formula(units={"diameter": "m (the screw's nominal)", "pitch": "m",
                "path": "'seat', 'through-insert' or 'jack-out' (insert_clamp_path)",
                "pull_out": "N (the insert's pull-out force, the low end of its band)",
                "torque_out": "N m (the insert's torque-out, the low end of its band)",
                "proof_load": "N (the screw's)",
                "thread_friction": "(low, high), dimensionless (the screw in the insert's thread)",
                "collar_friction": "(low, high), dimensionless (under the head or washer)",
                "margin": "dimensionless (the factor kept under each insert limit)",
                "flank_angle": "rad (included: 60 degrees for ISO metric)"},
         returns="dict: torque (the most to tighten to, N m), governed_by, the ceilings each limit sets (N m), "
                 "preload {low, high} at that torque (N), thread_share (the most of the torque the thread passes to "
                 "the insert) and nut_factor {low, high}",
         limits=("the thread torque turns the insert; friction on its end face, which also resists, is left out (the "
                 "cautious side)",
                 "jack-out: the knurl carries the preload and the thread torque together, combined as a linear "
                 "interaction F / F_out + T / T_out <= 1 / margin (cautious; no published combined test was found)",
                 "the screw's ceiling takes it to its proof load at the least friction",
                 "the nut factor's friction band gives the preload only to about +/- 25 % even when it is known"),
         source=cite("shigley", "Section 8-8 (Relating Bolt Torque to Bolt Tension: the thread's and the collar's "
                     "shares of the torque) and Section 8-9 (proof load)"))
def insert_limited_torque(diameter: float, pitch: float, path: str, pull_out: float, torque_out: float,
                          proof_load: float, thread_friction=(0.15, 0.25), collar_friction=(0.15, 0.25),
                          margin: float = 2.0, flank_angle: float = math.radians(60.0)) -> Dict[str, Any]:
    """The most a screw in an insert should be tightened: the lowest of the screw's ceiling (its proof load at the
    least friction), the insert's torque-out (the thread's share of the torque turns it) and, when it jacks out, its
    pull-out under the preload. Each insert limit is divided by ``margin``."""
    d, p = _positive("diameter", diameter), _positive("pitch", pitch)
    if path not in PATHS:
        raise ValueError(f"path must be one of {PATHS}, not {path!r}")
    Fout, Tout, Fp = (_positive(n, v) for n, v in (("pull_out", pull_out), ("torque_out", torque_out),
                                                      ("proof_load", proof_load)))
    bands = {}
    for name, band in (("thread_friction", thread_friction), ("collar_friction", collar_friction)):
        if not (isinstance(band, (tuple, list)) and len(band) == 2 and _num(band[0]) and _num(band[1])
                and 0 < band[0] <= band[1]):
            raise ValueError(f"{name} must be a (low, high) pair of numbers with 0 < low <= high, not {band!r}")
        bands[name] = (float(band[0]), float(band[1]))
    (ft_lo, ft_hi), (fc_lo, fc_hi) = bands["thread_friction"], bands["collar_friction"]
    if not (_num(margin) and margin >= 1.0):
        raise ValueError(f"margin must be a finite number of at least 1, not {margin!r}")
    k = {"low": nut_factor(d, p, ft_lo, fc_lo, flank_angle), "high": nut_factor(d, p, ft_hi, fc_hi, flank_angle)}
    # the thread's share of the torque is largest with the most thread friction and the least under the head
    share = nut_factor(d, p, ft_hi, 0.0, flank_angle) / nut_factor(d, p, ft_hi, fc_lo, flank_angle)
    ceilings = {"screw": k["low"] * Fp * d, "torque_out": Tout / (margin * share)}
    if path == "jack-out":
        # F = T / (K_low d) at the least friction, the thread torque T * share; F/Fout + Tth/Tout <= 1/margin
        ceilings["jack_out"] = 1.0 / (margin * (1.0 / (k["low"] * d * Fout) + share / Tout))
    governed = min(ceilings, key=ceilings.get)
    T = ceilings[governed]
    return {"torque": T, "governed_by": governed, "ceilings": ceilings,
            "preload": {"low": T / (k["high"] * d), "high": T / (k["low"] * d)},
            "thread_share": share, "nut_factor": k, "path": path, "margin": margin}
