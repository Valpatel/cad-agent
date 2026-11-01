"""Linear-elastic stiffness and strength studies for any CAD part (STEP or a CadQuery shape).

    from cadagent.simulation.fea import Study, MATERIALS, cylinder_at, plane_at, in_box
    st = Study('exports/thigh.step', MATERIALS['petg_cf'], mesh_mm=3.0)
    st.fix(cylinder_at(center=(0, 0, 0), axis=(0, 1, 0)))                       # bolt holes at the motor flange
    st.force(cylinder_at(center=(0, 0, -200), axis=(0, 1, 0)), (0, 0, 300))     # 300 N at the knee pin
    res = st.solve()          # dict: max von Mises (MPa), max and probe displacement (mm), stiffness, safety factor
    st.render('exports/fea/thigh.png')
    st.animate('exports/fea/thigh.mp4')            # the load ramped past first failure (overstressed region black)
    st.export_viewer('exports/fea/thigh.json')     # for the web kit's interactive viewer: kit/fea.html?case=...

Units: millimetres, newtons, MPa (N/mm²), so displacements come out in mm and stresses in MPa.

How it works: gmsh meshes the solid with tetrahedra (it reads the STEP through OpenCASCADE, so every face of the CAD
keeps its identity); scikit-fem solves linear elasticity with quadratic (P2) displacement on those tetrahedra, which
handles bending well even with a few elements through a wall. Faces are picked with selectors (functions of a face's
kind, bounding box, centre and area). Loads spread over the chosen faces: a force as a uniform traction, a torque as a
tangential traction that grows with the distance from the axis (like bolts sharing a twisting load).

Solvers: PARDISO (pip install pypardiso) when available, else SciPy's direct solver, or conjugate gradients with a
smoothed-aggregation multigrid preconditioner (pyamg, with the six rigid-body modes) for big meshes.

Meshing: ``mesh_mm`` is the global element size; ``refine=[(point, radius, size)]`` makes the mesh finer round a spot
(a fillet, a hole) to converge its peak, and ``converge()`` solves again at 0.75 x the mesh to check one. A sharp
re-entrant corner is singular: its peak rises with every refinement and never converges, so model the fillet. Every
result's ``mesh`` records the mesher (gmsh and OCC versions, build, platform) and how many elements lie across the wall
at the design peak (under MIN_ELEMENTS_ACROSS it is flagged: a MeshWarning). Slivers are listed before meshing, and a
mesher refusal raises a MeshRefusal that names the faces round its point.

Limits, stated in every result: linear and small-deflection; isotropic material. Printed parts are not isotropic, so
each printed material says which modulus and strength it uses and the print direction of the modulus
(``Material.note`` and ``Material.direction``); the assumptions line of every result repeats them. The defaults take the
lowest modulus the data sheet gives across the layers (Z), so deflections come out higher than with the sheet's
in-plane values, and a force or a stress taken from the computed stiffness at a given travel lower; and a strength
below the Z tensile strength, so the safety factor uses the weak direction. Neither is a bound on a print: the mesh is
the solid CAD and the values come from 100 % infill test bars, so a print with sparse infill or thin walls can be
softer, and then it deflects more, and pushes back less at a given travel (a clip's retention, a flexure's preload),
than computed. Contact, bolt preload and buckling are not modelled. No simulation proves that a part will fit or hold:
check it against a printed coupon or the part itself.
"""
from __future__ import annotations

import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class Material:
    name: str
    E_mpa: float                 # Young's modulus; printed parts: see `note` for which sheet value (and factors)
    nu: float
    strength_mpa: float          # the strength the safety factor uses (yield for metals; weak-direction for prints)
    density_g_cm3: float
    note: str = ''               # printed parts: the sheet and edition, and what E and the strength are taken from
    source: str = ''             # the data sheet the numbers come from: its id in research/references.yaml (#118)
    direction: str = ''          # printed parts: the print direction of E ('Z': across the layers; 'X-Y': in the
                                 # layer plane); '' for an isotropic material. Change `note` with it.


_DIRECTION = {'Z': 'across the layers (Z)', 'X-Y': 'in the layer plane (X-Y)'}


def _ksi(v: float) -> float:
    """ksi to MPa, to 0.1 MPa (the handbooks below give US units)."""
    return round(v * 6.894757, 1)


def _lb_in3(v: float) -> float:
    """lb/in3 to g/cm3, to 0.01."""
    return round(v * 27.679905, 2)


def _isotropic_basis(mat: Material) -> str:
    """For the assumptions line: the modulus and strength a printed material uses everywhere, and their basis."""
    if not mat.direction:
        return ''
    return (f': E {mat.E_mpa:g} MPa, a modulus {_DIRECTION.get(mat.direction, mat.direction)}, and strength '
            f'{mat.strength_mpa:g} MPa everywhere ({mat.note}), though a printed part is not isotropic')


# Printed materials (#125). Every number is from the manufacturer's technical data sheet (TDS), read on 2026-10-31.
# The sheets test bars printed at 100 % infill, dried and (except PETG Basic V3.0, not used) annealed: ISO 527 tension,
# ISO 178 bending. Each row's comment names the sheet's edition and both directions; where two editions disagree, the
# row says which it uses and why. Each row's note says what E and the strength are, and the assumptions line of a
# result repeats it.
#
# - E is the lowest modulus the sheets give in the row's direction, across the layers (Z) unless the row says X-Y:
#   the tensile modulus, except for PAHT-CF, whose Z bending modulus is lower. The in-plane (X-Y) moduli are higher.
#   The solver is isotropic and does not know how the part was printed, so it takes the weak direction: deflections
#   come out higher than with the sheet's in-plane values. They are not an upper bound on a print: the mesh is the
#   solid CAD, a print with sparse infill or thin walls is softer still, and the isotropic shear modulus does not bound
#   a print's shear stiffness between layers (short, thick parts). The humid PA6-CF rows are an exception (below).
# - These studies apply forces and torques only, so the stresses do not depend on E; the deflections and stiffnesses
#   do (they scale with 1/E). Against a solid part bent in the layer plane, the low E makes the stiffness low, so a
#   force taken from it at a given travel (a clip's retention, a flexure's preload, a spring rate) reads low, and so
#   does the stress at that travel (it scales with E): check strength at a travel with the in-plane modulus or a
#   coupon. A sparser print is softer still, and then that force reads high.
# - A part whose bending stays in the layer plane is stiffer. Give it the X-Y modulus from the comment and say so in
#   the note, keeping the weak-direction strength:
#   dataclasses.replace(MATERIALS['petg_cf'], E_mpa=2460, direction='X-Y',
#                       note='Bambu PETG-CF TDS V3.0: E is the X-Y tensile modulus; strength the Z allowable')
# - The strength is a design allowable below the TDS tensile strength across the layers.
# - Poisson's ratio is not on these sheets; it is a typical value for the polymer. Across 0.35-0.40 it changes a
#   plate's bending stiffness by about 5 % (1 - nu^2) and a beam's hardly at all.
# - Density is the sheet's (ISO 1183), for mass estimates.
#
# Before #125 the moduli were 2700 (PLA), 1800 (PETG) and 2900 (PETG-CF): close to the V2.0 sheets' X-Y *bending*
# moduli (2750, 1790, 2890), not a tensile value. They were 31-116 % above the moduli used now (PAHT-CF 147 %, TPU
# 305 %), so deflections read 24-54 % low (PAHT-CF 60 %, TPU 75 %). The humid PA6-CF rows, 3000 and 2400 MPa then,
# are 191 % and 392 % above the moduli used since #157 (41 % and 130 % above #125's), so deflections read 66 % and 80 %
# low.
#
# PA6-CF in use (#157): moisture taken up from the air, as Polymaker's Fiberon PA6-CF20 TDS V1.1 (PDF of 2024-12-08,
# p. 1) gives it, water-saturated / dry: tensile modulus 2508.1 / 8636.5 MPa X-Y and 1056.1 / 3759.5 Z, tensile
# strength 54.7 / 109.3 and 25.5 / 54.0. https://cdn.shopify.com/s/files/1/0548/7299/7945/files/TDS_FIBERON_PA6-CF20_V1.1_EN.pdf
# Its wet bars were soaked at 60 degC for 48 h (5.30 % moisture); a part in room air takes up less (Bambu's PA6-CF:
# 2.35 % at 25 degC / 55 % RH). No sheet read gives a printed CF-PA6 conditioned in room air. Moulded PA6 conditioned
# at 23 degC / 50 % RH keeps 0.31 of its dry tensile modulus unfilled (BASF Ultramid B3S HP R01, 1000 / 3200 MPa, a
# preliminary sheet of 2026-08) and 0.58 with 30 % glass (Ultramid B3EG6 SI, 5650 / 9700 MPa); a filled print
# plausibly sits between. Taking the saturated printed ratios for modulus and strength alike is a judgement for the
# cautious end: in room air these rows may be up to about 2x too soft, which is cautious for deflection, but a force or
# stress worked out at a given travel reads low. research/compliant-mechanisms.md section 5 has the links.
_HUMID_E = {'X-Y': 2508.1 / 8636.5, 'Z': 1056.1 / 3759.5}       # 0.290, 0.281
_HUMID_S = {'X-Y': 54.7 / 109.3, 'Z': 25.5 / 54.0}              # 0.500, 0.472
_PRINT = 0.8   # x0.8 for a print's voids and seams: a knock-down the original table applied to these rows only
MATERIALS = {
    # Bambu PLA Basic TDS V3.0 (Bambu's copy, PDF created 2025-04): E 2580 X-Y / 2060 Z MPa, UTS 35 / 31 MPa,
    # 1.24 g/cm3.
    # https://store.bblcdn.com/s1/default/58b85d0f3db94878854a28fdb8a0006e/Bambu_PLA_Basic_Technical_Data_Sheet.pdf
    # V2.0 (a reseller's copy, PDF created 2023-03) has 2680 / 2160 and 39 / 35: the lower V3.0 values are used.
    'pla': Material('PLA', 2060, 0.35, 25, 1.24,
                    'Bambu PLA Basic TDS V3.0: E is the Z tensile modulus (X-Y 2580 MPa); the strength is an allowable '
                    'below the Z tensile strength of 31 MPa', source='bambu-pla-basic-tds', direction='Z'),
    # Bambu PETG Basic TDS V2.0 (a reseller's copy, PDF created 2023-06): E 1460 / 1120 MPa, UTS 48 / 39 MPa,
    # 1.25 g/cm3; bars annealed and dried at 65 degC for 8 h.
    # https://www.additive-x.com/shop/mpattachments/file/viewonline/id/580/product_id/2330
    # V3.0 (Bambu's copy, PDF created 2026-01) describes a reformulated filament sold under the same name ("The
    # all-new Bambu Lab PETG Basic ... The refined formula ..."), with bars not said to be annealed (it advises against
    # annealing PETG Basic): E 2780 / 2550, bending 1950 / 1740, UTS 51 / 35 MPa.
    # https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf
    # A spool's label does not say which formulation it is, so the lower V2.0 modulus is used for both; a printed
    # coupon (#94) should record its formulation. V3.0's tensile moduli above its own bending moduli are a further
    # reason to wait for one.
    'petg': Material('PETG', 1120, 0.38, 20, 1.25,
                     'Bambu PETG Basic TDS V2.0: E is the Z tensile modulus (X-Y 1460 MPa; the reformulated V3.0 lists '
                     '2550, not used); the strength is an allowable below the Z tensile strength (39 MPa; 35 in V3.0)',
                     source='bambu-petg-basic-tds', direction='Z'),
    # Bambu PETG-CF TDS V3.0 (Bambu's copy, PDF created 2023-08): E 2460 / 1340 MPa (as V2.0), UTS 35 / 29 MPa (V2.0:
    # 59 / 38), 1.25 g/cm3. https://store.bblcdn.com/626e4f424bf345ae965ad0ddfcaf2459.pdf
    'petg_cf': Material('PETG-CF', 1340, 0.36, 22, 1.25,
                        'Bambu PETG-CF TDS V3.0: E is the Z tensile modulus (X-Y 2460 MPa); the strength is an '
                        'allowable below the Z tensile strength of 29 MPa', source='bambu-petg-cf-tds', direction='Z'),
    # Bambu PAHT-CF TDS V3.0 (Bambu's copy, PDF created 2023-08), dry: E 3860 / 2180 MPa, bending modulus 4230 / 1820
    # MPa, UTS 92 / 47 MPa, 1.06 g/cm3. https://store.bblcdn.com/7166b20bc68f4c87b32c972b856eeb4b.pdf
    # The Z bending modulus is the sheet's lowest, so it is used. Named 'PA6-CF' before #125, though its note and
    # values were PAHT-CF's; Bambu's PA6-CF is the two rows below.
    'pa_cf': Material('PAHT-CF (dry)', 1820, 0.35, 40, 1.06,
                      'Bambu PAHT-CF TDS V3.0, dry: E is the Z bending modulus, the sheet\'s lowest (Z tensile 2180, '
                      'X-Y 3860 MPa); the strength is an allowable below the Z tensile strength of 47 MPa',
                      source='bambu-paht-cf-tds', direction='Z'),
    # Bambu PA6-CF TDS V3.0 (Bambu's copy, PDF created 2023-08), dry: E 4430 / 2170 MPa, UTS 102 / 48 MPa, 1.09 g/cm3.
    # https://store.bblcdn.com/b2abc59ac250492b979a52f1ce3e61b3.pdf
    # Unlike the rows above (dry test-bar values), these two describe the material as it is in use: humid and as
    # printed, with the factors above: the wet / dry ratios of Polymaker's PA6-CF20 (modulus x0.290 X-Y, x0.281 Z;
    # strength x0.500, x0.472), applied to Bambu's dry values, and x0.8 print. Two makers' filaments: the ratio is
    # borrowed, since Bambu's sheet gives no wet values. Before #157 both rows took x0.6 on modulus and strength, a
    # strength-like ratio, so their moduli were about twice these. The other rows carry no x0.8 on E, so pa6_cf_z
    # (488) against petg_cf (1340) sets a derated, humid value against a dry sheet value.
    'pa6_cf_xy': Material('PA6-CF along the layers (humid)', 4430 * _HUMID_E['X-Y'] * _PRINT, 0.35,
                          102 * _HUMID_S['X-Y'] * _PRINT, 1.09,
                          'Bambu PA6-CF TDS V3.0: dry X-Y tensile modulus 4430 MPa x0.290 humid and strength 102 MPa '
                          'x0.500 humid (Polymaker PA6-CF20 V1.1 wet / dry), each x0.8 print. For parts printed so '
                          'their main stress runs in the layers', source='bambu-pa6-cf-tds', direction='X-Y'),
    'pa6_cf_z': Material('PA6-CF across the layers (humid)', 2170 * _HUMID_E['Z'] * _PRINT, 0.35,
                         48 * _HUMID_S['Z'] * _PRINT, 1.09,
                         'Bambu PA6-CF TDS V3.0: dry Z tensile modulus 2170 MPa x0.281 humid and strength 48 MPa '
                         'x0.472 humid (Polymaker PA6-CF20 V1.1 wet / dry), each x0.8 print. The safe strength when '
                         'the stress crosses the layers', source='bambu-pa6-cf-tds', direction='Z'),
    # Bambu TPU 95A HF TDS V1.0 (Bambu's copy, PDF created 2023-11): E 9.8 / 7.4 MPa, UTS 27.3 / 22.3 MPa, 1.22 g/cm3.
    # https://store.bblcdn.com/58df32731eab4c90a7dac9b12e13ba88.pdf
    # Polymaker's PolyFlex TPU95 (TDS V5.4) lists 33.6 MPa in X-Y (ISO 37). The sheets differ about 4x, and TPU is far
    # from linear, so a linear study of it is indicative only.
    'tpu95': Material('TPU 95A', 7.4, 0.45, 8, 1.22,
                      'Bambu TPU 95A HF TDS V1.0: E is the Z tensile modulus (X-Y 9.8 MPa); the strength is an '
                      'allowable below the Z tensile strength of 22.3 MPa; flexible, stiffness only indicative',
                      source='bambu-tpu-95a-hf-tds', direction='Z'),
    # Metals (#157): design minimums, not typical values. MIL-HDBK-5J, Metallic Materials and Elements for Aerospace
    # Vehicle Structures (31 January 2003; public, superseded by MMPDS, which is not free and was not checked):
    # https://everyspec.com/MIL-HDBK/MIL-HDBK-0001-0099/MIL_HDBK_5J_139/
    # The strength is the A-basis (or S-basis) tensile yield Fty, in the weaker of the L and LT grain directions;
    # E is the tension modulus, mu Poisson's ratio. The typical values used before #157 (6061 276 MPa, 7075 503 MPa)
    # made safety factors read 14 % and 9 % high. Protolabs' CNC data sheets agree: 6061-T651/T6 typical yield
    # 276 MPa, 2.70 g/cm3; 7075 ranges 434-476 MPa (T6 sheet) and 372-462 MPa (T651 plate to 101.6 mm), over thickness.
    # - 6061-T6 sheet and T651 plate, 0.010-6.000 in thick, Tables 3.6.2.0(b1) and (b2), pp. 3-264, 3-265: Fty 35 ksi
    #   (LT; 36 L), E 9.9e3 ksi, mu 0.33. Density from Protolabs (2.70 Mg/m3; the handbook's 0.098 lb/in3 is 2.71).
    #   Extruded 6061-T6/T6510/T6511 rod, bar and shapes, common CNC stock, are lower across the grain: A-basis Fty
    #   LT 33 ksi to 1.000 in and 28 ksi (193 MPa) from 1.001 to 6.500 in (35 L), Table 3.6.2.0(g), p. 3-272. The
    #   solver knows neither the stock form nor the grain direction: replace the row for such stock loaded across it.
    # - 7075-T6 sheet and T651 plate, 0.012-2.000 in (0.3-50.8 mm) thick, Table 3.7.6.0(b1), p. 3-371: Fty 67 ksi
    #   (LT, the lowest in that range), E 10.3e3 ksi, mu 0.33, 0.101 lb/in3. Thicker plate is weaker: 64 ksi to
    #   2.5 in, 54 ksi (372 MPa) at 3.5-4 in, and less again short-transverse; replace the row for such stock.
    #   7075-T6/T651 rolled or cold-finished bar and rod is lower too: A-basis Fty 66 ksi to 2.000 in, then 63 and
    #   60 ksi LT to 3 and 4 in, Table 3.7.6.0(d), p. 3-380.
    # - Mild steel: AISI 1025 sheet, strip, plate, tubing and bar, Table 2.2.1.0(b), p. 2-8: Fty 36 ksi (S-basis, the
    #   same 36 ksi minimum as ASTM A36 structural steel), E 29.0e3 ksi, mu 0.32, 0.284 lb/in3.
    # The carbon tube has no cited sheet: typical values, labelled as such; use the supplier's.
    'al6061': Material('Aluminium 6061-T6', _ksi(9.9e3), 0.33, _ksi(35), 2.70,
                       'yield strength 35 ksi, the A- or S-basis minimum (LT) of 6061-T6/T651 sheet and plate to '
                       '6 in (MIL-HDBK-5J Tables 3.6.2.0(b1), (b2)); extruded rod, bar and shapes are lower across '
                       'the grain (33 ksi to 1 in, 28 ksi to 6.5 in, Table 3.6.2.0(g)); typical yield is 276 MPa',
                       source='mil-hdbk-5j'),
    'al7075': Material('Aluminium 7075-T6', _ksi(10.3e3), 0.33, _ksi(67), _lb_in3(0.101),
                       'yield strength 67 ksi, the A-basis minimum (LT) of 7075-T6/T651 sheet and plate 0.012-2.000 in '
                       'thick (MIL-HDBK-5J Table 3.7.6.0(b1)); thicker plate is lower (54 ksi at 3.5-4 in), and so '
                       'is bar and rod (66 ksi to 2 in, 60 ksi at 3-4 in, Table 3.7.6.0(d)); typical yield is 503 MPa',
                       source='mil-hdbk-5j'),
    'steel': Material('Steel (mild)', _ksi(29.0e3), 0.32, _ksi(36), _lb_in3(0.284),
                      'yield strength 36 ksi, the S-basis minimum of AISI 1025 (MIL-HDBK-5J Table 2.2.1.0(b)), as '
                      'ASTM A36\'s minimum', source='mil-hdbk-5j'),
    'cf_tube': Material('Carbon tube (roll-wrapped)', 64000, 0.3, 650, 1.55,
                        'axial modulus/strength, typical values, not from a sheet and not a minimum: use the '
                        'supplier\'s; not for local crushing'),
}


@dataclass
class Face:
    tag: int
    kind: str                    # gmsh/OCC surface type: 'Plane', 'Cylinder', 'Cone', 'BSpline surface', ...
    bbox: tuple                  # (xmin, ymin, zmin, xmax, ymax, zmax)
    center: np.ndarray           # centre of mass of the face
    area: float
    radius: Optional[float] = None   # cylinders: the radius (from the surface's curvature)


Selector = Callable[[Face], bool]


def in_box(lo: Sequence[float], hi: Sequence[float]) -> Selector:
    """Faces that lie entirely inside the box lo..hi."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return lambda f: bool(np.all(np.asarray(f.bbox[:3]) >= lo - 1e-6) and np.all(np.asarray(f.bbox[3:]) <= hi + 1e-6))


def near(point: Sequence[float], tol: float) -> Selector:
    """Faces whose centre is within tol of a point."""
    p = np.asarray(point, float)
    return lambda f: float(np.linalg.norm(f.center - p)) <= tol


def cylinder_at(center: Sequence[float], axis: Sequence[float], radius_max: Optional[float] = None, tol: float = 0.5,
                within: Optional[float] = None) -> Selector:
    """Cylindrical faces (holes, bosses) whose axis passes through `center` along `axis`; with `within`, any cylinder
    whose centre is within that distance of the axis line near `center` (a bolt circle)."""
    c, a = np.asarray(center, float), np.asarray(axis, float) / np.linalg.norm(axis)

    def sel(f: Face) -> bool:
        if f.kind != 'Cylinder':
            return False
        d = f.center - c
        radial = d - (d @ a) * a
        if within is not None:
            if np.linalg.norm(radial) > within or abs(d @ a) > within:
                return False
        elif np.linalg.norm(radial) > tol:
            return False
        if radius_max is not None:
            ext = np.asarray(f.bbox[3:]) - np.asarray(f.bbox[:3])
            perp = [ext[i] for i in range(3) if abs(a[i]) < 0.9]
            if perp and max(perp) / 2 > radius_max + tol:
                return False
        return True
    return sel


def plane_at(axis: int, value: float, tol: float = 0.05) -> Selector:
    """Planar faces lying in the plane coordinate[axis] == value (axis 0, 1, 2 for x, y, z)."""
    return lambda f: f.kind == 'Plane' and abs(f.bbox[axis] - value) <= tol and abs(f.bbox[axis + 3] - value) <= tol


def any_of(*sels: Selector) -> Selector:
    return lambda f: any(s(f) for s in sels)


# --- meshing: refinement, the mesher's identity, slivers and refusals
MIN_ELEMENTS_ACROSS = 3      # a design peak in a wall thinner than this many elements is flagged: not a result


class MeshWarning(UserWarning):
    """A Study's mesh may not carry its result: sliver faces or edges found before meshing, a design peak in a wall
    under MIN_ELEMENTS_ACROSS elements thick, or a peak that moved on a finer mesh (Study.converge)."""


class MeshRefusal(RuntimeError):
    """gmsh would not mesh the part, or the check before meshing found slivers and the caller asked to stop on them.

    ``what`` names the problem ('segment-facet intersection', 'slivers', ...); ``point`` is where gmsh found it (mm, or
    None); ``faces`` the faces of the part nearest that point, nearest first (for 'slivers', the sliver faces), and
    ``edges`` the same for curves: dicts with the gmsh tag, kind, area or length, and distance; ``log`` gmsh's own lines
    about it."""

    def __init__(self, message: str, what: str, point=None, faces=(), edges=(), log=()):
        super().__init__(message)
        self.what, self.point = what, point
        self.faces, self.edges, self.log = list(faces), list(edges), list(log)


_XYZ = r'\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)'


def parse_gmsh_refusal(log: Sequence[str]) -> Optional[dict]:
    """The boundary-recovery refusal in a gmsh log (``gmsh.logger.get()`` lines), or None if it has none.

    gmsh's volume mesher (TetGen's boundary recovery, inside gmsh) stops on a surface mesh that cuts through itself
    with 'PLC Error:  A segment and a facet intersect at point', prints the point on the next line, and then sums it
    up as 'Invalid boundary mesh (segment-facet intersection) on surface 6, intersection (x,y,z)'. With gmsh's default
    (throw on the first error) only the first line reaches the caller, without the point, so after such a refusal
    Study meshes the part once more, in a new gmsh session with errors logged rather than thrown, and reads them here.

    Returns {'what', 'point' (mm, or None), 'surfaces' and 'curves' (gmsh tags it names), 'message' (the PLC line),
    'log' (gmsh's lines about it)}."""
    lines = [str(m) for m in log]
    bare = [re.sub(r'^(Error|Info|Warning|Progress)\s*:\s?', '', m) for m in lines]
    plc = next((i for i, m in enumerate(bare) if 'PLC Error' in m), None)
    summary = next((i for i, m in enumerate(bare) if 'Invalid boundary mesh' in m), None)
    if plc is None and summary is None:
        return None
    what, point, surfaces, curves, about = None, None, [], [], []
    if plc is not None:
        about.append(lines[plc])
        found = re.search(_XYZ, bare[plc])
        for k in range(plc + 1, min(plc + 4, len(bare))):     # the point, then the segment and the facet, if printed
            if 'PLC Error' in bare[k] or 'Invalid boundary mesh' in bare[k]:
                break
            about.append(lines[k])
            found = found or re.match(r'\s*' + _XYZ, bare[k])
            tag = re.search(r'Facet\s*:\s*\[[^\]]*\]\s*#(\d+)', bare[k])
            if tag and int(tag.group(1)) > 0:
                surfaces.append(int(tag.group(1)))
        if found:
            point = [float(v) for v in found.groups()]
        what = re.sub(r'\s+', ' ', bare[plc].split('PLC Error:', 1)[1]).strip().rstrip('.')
        what = re.sub(r'\s*at( point)?\s*(\(.*\))?$', '', what)
    if summary is not None:
        about.append(lines[summary])
        s = bare[summary]
        head = re.search(r'Invalid boundary mesh \(([^)]*)\) on([^,]*)', s)
        if head:
            what = head.group(1)
            surfaces += [int(v) for v in re.findall(r'surface (\d+)', head.group(2))]
            curves += [int(v) for v in re.findall(r'curve (\d+)', head.group(2))]
        found = re.search(r'intersection ' + _XYZ, s)
        if found:
            point = [float(v) for v in found.groups()]
    return {'what': what or 'invalid boundary mesh', 'point': point, 'surfaces': sorted(set(surfaces)),
            'curves': sorted(set(curves)), 'message': bare[plc if plc is not None else summary].strip(), 'log': about}


_MESHER = None


def _mesher_identity() -> dict:
    """Which mesher made the mesh, read from the running gmsh (call inside a gmsh session; cached per process).

    Two builds of one gmsh version can mesh one part differently (the PyPI wheel and conda-forge's 4.15.2 give a
    Gyropup frame 151,459 and 151,136 tets, and its sharp-corner peak 6 % apart), so a gate read at one mesh size says
    which build made it: the version, the OpenCASCADE version gmsh was built with, the build's OS and date, a hash of
    the library file and the platform. Host and packager names stay out (a self-built gmsh would carry a private
    host name into results that projects commit)."""
    global _MESHER
    if _MESHER is not None:
        return _MESHER
    import hashlib
    import os
    import platform

    import gmsh
    info = {}
    try:
        for part in gmsh.option.getString('General.BuildInfo').split(';'):
            key, _, value = part.partition(':')
            info[key.strip()] = value.strip()
    except Exception:                                  # an old gmsh without the option: the version alone
        pass
    lib = getattr(gmsh, 'libpath', None)
    digest = None
    if lib and os.path.isfile(lib):
        h = hashlib.sha256()
        with open(lib, 'rb') as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b''):
                h.update(chunk)
        digest = h.hexdigest()[:16]
    _MESHER = {
        'gmsh': getattr(gmsh, '__version__', None) or info.get('Version'),
        'occ': info.get('OCC version'),
        'build': {'os': info.get('Build OS'), 'date': info.get('Build date')},
        'library': {'file': os.path.basename(lib) if lib else None, 'sha256_16': digest},
        'platform': {'system': platform.system(), 'machine': platform.machine(), 'python': platform.python_version()},
    }
    return _MESHER


def _point_triangle_distance(p, A, B, C) -> np.ndarray:
    """Distance from point p to each triangle (A[i], B[i], C[i]), (n, 3) arrays."""
    p = np.asarray(p, float)
    n = np.cross(B - A, C - A)
    nn = np.maximum(np.einsum('ij,ij->i', n, n), 1e-300)
    q = p - (np.einsum('ij,ij->i', p - A, n) / nn)[:, None] * n         # p projected on each triangle's plane
    # barycentric coordinates of q: inside when all three sub-triangles turn the same way as the triangle
    inside = np.ones(len(A), dtype=bool)
    for U, V in ((A, B), (B, C), (C, A)):
        inside &= np.einsum('ij,ij->i', np.cross(V - U, q - U), n) >= 0
    def seg(U, V):
        d = V - U
        t = np.clip(np.einsum('ij,ij->i', p - U, d) / np.maximum(np.einsum('ij,ij->i', d, d), 1e-300), 0, 1)
        return np.linalg.norm(p - (U + t[:, None] * d), axis=1)
    edge = np.minimum(np.minimum(seg(A, B), seg(B, C)), seg(C, A))
    return np.where(inside, np.linalg.norm(p - q, axis=1), edge)


def _faces_near(point, faces, points, face_tris, k: int = 4) -> List[dict]:
    """The k faces nearest a point, nearest first, measured to each face's surface triangles."""
    p = np.asarray(point, float)
    out = []
    for f in faces:
        tri = face_tris.get(f.tag)
        if tri is None or not len(tri):
            continue
        d = float(_point_triangle_distance(p, points[tri[:, 0]], points[tri[:, 1]], points[tri[:, 2]]).min())
        out.append({'tag': f.tag, 'kind': f.kind, 'area_mm2': round(float(f.area), 4), 'distance_mm': round(d, 4),
                    'center_mm': [round(float(v), 3) for v in f.center],
                    **({'radius_mm': round(float(f.radius), 3)} if f.radius else {})})
    return sorted(out, key=lambda r: r['distance_mm'])[:k]


def _ray_exit(origin, direction, A, E1, E2, skip: float) -> Optional[float]:
    """Distance along a ray to the nearest triangle it crosses beyond `skip` (Möller-Trumbore), or None."""
    pv = np.cross(direction, E2)
    det = np.einsum('ij,ij->i', E1, pv)
    ok = np.abs(det) > 1e-14
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = origin - A
    u = np.einsum('ij,ij->i', tv, pv) * inv
    qv = np.cross(tv, E1)
    v = (qv @ direction) * inv
    t = np.einsum('ij,ij->i', E2, qv) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > skip)
    return float(t[hit].min()) if hit.any() else None


@dataclass
class _Load:
    faces: List[int]
    force: Optional[np.ndarray] = None
    torque: Optional[tuple] = None   # (point, axis, N·mm)


class Study:
    def __init__(self, shape, material: Material, mesh_mm: float = 3.0, name: str = 'part', refine=None,
                 slivers: str = 'warn'):
        """Mesh `shape` (a STEP path or a CadQuery shape) with tetrahedra of about `mesh_mm`.

        refine: ``[(point_mm, radius_mm, size_mm), ...]``, finer elements of `size_mm` inside a ball round each point
        (a gmsh Ball field each, joined by a Min field under the global size), growing back to `mesh_mm` over a
        transition 2 x (mesh_mm - size_mm) thick. The rest of the mesh stays as it was. It converges a peak at a
        fillet or a hole without refining the whole part. A sharp re-entrant corner has no finite peak: its stress
        rises with every refinement, so refine converges a fillet, never a sharp corner.

        slivers: 'warn' (MeshWarning), 'raise' (MeshRefusal) or 'ignore', for faces under (size/10)^2 and edges under
        size/10 found before meshing, where size is mesh_mm (or the refine size inside a ball): slivers make the
        mesher fail or crowd tiny, poor elements there."""
        self.material, self.mesh_mm, self.name = material, mesh_mm, name
        if slivers not in ('warn', 'raise', 'ignore'):
            raise ValueError(f"slivers must be 'warn', 'raise' or 'ignore', not {slivers!r}")
        self.refine = self._refine_zones(refine, mesh_mm)
        self._slivers_mode = slivers
        self._shape = shape                            # kept for converge(), which meshes it again, finer
        self.fixed: List[int] = []
        self.loads: List[_Load] = []
        self.probe_faces: List[int] = []
        # a shape goes to a STEP file that only the mesher reads: in a folder of its own, gone once it is meshed (or
        # the export or the mesh fails); a STEP path the caller passes is theirs and stays
        with tempfile.TemporaryDirectory(prefix='cadagent-fea-', ignore_cleanup_errors=True) as tmp:
            self._step = self._as_step(shape, Path(tmp))
            self._mesh()

    # --- geometry and mesh
    @staticmethod
    def _as_step(shape, folder: Path) -> Path:
        if isinstance(shape, (str, Path)):
            return Path(shape)
        import cadquery as cq
        step = folder / 'part.step'
        cq.exporters.export(shape.val() if hasattr(shape, 'val') else shape, str(step))
        return step

    @staticmethod
    def _refine_zones(refine, mesh_mm: float) -> List[tuple]:
        zones = []
        for zone in refine or ():
            try:
                point, radius, size = zone
                point, radius, size = np.asarray(point, float), float(radius), float(size)
            except (TypeError, ValueError):
                raise ValueError(f'refine takes (point_mm, radius_mm, size_mm) entries, not {zone!r}') from None
            if point.shape != (3,) or not np.all(np.isfinite(point)) or not radius > 0 or not size > 0:
                raise ValueError(f'refine entry {zone!r}: a 3D point, a radius > 0 and a size > 0')
            if size >= mesh_mm:
                raise ValueError(f'refine size {size:g} mm is not under mesh_mm {mesh_mm:g} mm: it would change nothing')
            zones.append((tuple(float(v) for v in point), radius, size))
        return zones

    def _size_at(self, x) -> float:
        """The target element size at a point: the refine balls' sizes (with their transitions), else mesh_mm. The
        same formula as gmsh's Ball field, so the size callback below can keep the global lower bound outside them."""
        size = self.mesh_mm
        for c, r, s in self.refine:
            d = math.dist(x, c) - r
            t = 2 * (self.mesh_mm - s)
            size = min(size, s if d <= 0 else s + (d / t) * (self.mesh_mm - s) if d <= t else self.mesh_mm)
        return size

    def _mesh(self):
        try:
            self._mesh_once(logged=False)
        except MeshRefusal:
            raise
        except Exception as exc:
            if 'PLC Error' not in str(exc) and 'Invalid boundary mesh' not in str(exc):
                raise
            # gmsh throws on the first line of a boundary-recovery error, before it prints the point, and stays locked
            # until finalized: mesh once more in a new session with errors logged, not thrown, to say where and why
            self._mesh_once(logged=True, first=str(exc))
        # drop nodes that only belong to lower-dimensional entities, and orient every tet positively
        used = np.unique(self.tets)
        remap = -np.ones(len(self.points), dtype=np.int64)
        remap[used] = np.arange(len(used))
        self.points = self.points[used]
        self.tets = remap[self.tets]
        self.face_tris = {k: remap[v] for k, v in self.face_tris.items()}
        self.edge_segs = {k: remap[v] for k, v in self.edge_segs.items()}
        p = self.points
        a, b, c, d = (p[self.tets[:, i]] for i in range(4))
        neg = np.einsum('ij,ij->i', np.cross(b - a, c - a), d - a) < 0
        self.tets[neg, 2], self.tets[neg, 3] = self.tets[neg, 3], self.tets[neg, 2].copy()

    def _mesh_once(self, logged: bool, first: str = ''):
        """One gmsh session: read the faces, check for slivers, mesh. `logged`: mesh with errors logged rather than
        thrown and raise a MeshRefusal from the log (the second run after a refusal; `first` is what gmsh threw)."""
        import gmsh
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal', 0)
            gmsh.model.add(self.name)
            gmsh.model.occ.importShapes(str(self._step))
            gmsh.model.occ.synchronize()
            self.mesher = _mesher_identity()
            self.faces = []
            for _, tag in gmsh.model.getEntities(2):
                kind = gmsh.model.getType(2, tag)
                self.faces.append(Face(tag, kind, tuple(gmsh.model.getBoundingBox(2, tag)),
                                       np.array(gmsh.model.occ.getCenterOfMass(2, tag)), gmsh.model.occ.getMass(2, tag),
                                       self._cylinder_radius(tag) if kind == 'Cylinder' else None))
            if not logged:
                self._check_slivers()
            gmsh.option.setNumber('Mesh.MeshSizeMax', self.mesh_mm)
            gmsh.option.setNumber('Mesh.MeshSizeMin', self.mesh_mm / 4)
            gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 10)
            gmsh.option.setNumber('Mesh.Optimize', 1)
            if self.refine:
                self._refine_fields()
            if logged:
                gmsh.option.setNumber('General.AbortOnError', 0)
                gmsh.logger.start()
                try:
                    gmsh.model.mesh.generate(3)
                    log = list(gmsh.logger.get())
                finally:
                    gmsh.logger.stop()
                self.points, _, self.face_tris, self.edge_segs = self._surface_mesh()
                errors = [m for m in log if m.startswith('Error')]
                self._refuse(errors or [f'Error: {first}'], log if errors else [f'Error: {first}'])
            gmsh.model.mesh.generate(3)
            self.points, index, self.face_tris, self.edge_segs = self._surface_mesh()
            types, _, nodes = gmsh.model.mesh.getElements(3)
            tets = np.concatenate([np.asarray(n, dtype=np.int64).reshape(-1, 4) for ty, n in zip(types, nodes) if ty == 4])
            self.tets = np.vectorize(index.get)(tets)
        finally:
            gmsh.finalize()

    @staticmethod
    def _cylinder_radius(tag: int) -> Optional[float]:
        import gmsh
        try:
            lo, hi = gmsh.model.getParametrizationBounds(2, tag)
            kmax, kmin, _, _ = gmsh.model.getPrincipalCurvatures(tag, [(a + b) / 2 for a, b in zip(lo, hi)])
            k = max(abs(float(kmax[0])), abs(float(kmin[0])))
            return 1.0 / k if k > 1e-9 else None
        except Exception:                            # an odd parametrisation: no radius, the hint just says less
            return None

    def _refine_fields(self):
        """One gmsh Ball field per refine zone (VIn its size, VOut mesh_mm, a linear transition outside it), the
        background size their Min; Mesh.MeshSizeMax keeps the global size everywhere else. Mesh.MeshSizeMin has to drop
        to the smallest refine size, and it is also the floor of the curvature sizing, so a size callback puts the
        global floor (mesh_mm / 4) back outside the balls: away from them the mesh is the one the study gets without
        refine."""
        import gmsh
        balls = []
        for (x, y, z), r, s in self.refine:
            b = gmsh.model.mesh.field.add('Ball')
            for key, v in (('XCenter', x), ('YCenter', y), ('ZCenter', z), ('Radius', r),
                           ('Thickness', 2 * (self.mesh_mm - s)), ('VIn', s), ('VOut', self.mesh_mm)):
                gmsh.model.mesh.field.setNumber(b, key, float(v))
            balls.append(b)
        both = gmsh.model.mesh.field.add('Min')
        gmsh.model.mesh.field.setNumbers(both, 'FieldsList', balls)
        gmsh.model.mesh.field.setAsBackgroundMesh(both)
        floor = self.mesh_mm / 4
        gmsh.option.setNumber('Mesh.MeshSizeMin', min(floor, min(s for _, _, s in self.refine)))
        gmsh.model.mesh.setSizeCallback(lambda dim, tag, x, y, z, lc: max(lc, min(floor, self._size_at((x, y, z)))))

    def _check_slivers(self):
        """Faces under (size/10)^2 and edges under size/10 (size: mesh_mm, or the refine size where it applies), read
        off the CAD before meshing: they make the mesher refuse, or crowd tiny, poor elements there."""
        import gmsh
        faces, edges = [], []
        self.edge_lengths = {}
        for f in self.faces:
            cut = (self._size_at(f.center) / 10) ** 2
            if f.area < cut:
                faces.append({'tag': f.tag, 'kind': f.kind, 'area_mm2': round(float(f.area), 6), 'under_mm2': round(cut, 6),
                              'center_mm': [round(float(v), 3) for v in f.center]})
        for _, tag in gmsh.model.getEntities(1):
            length = self.edge_lengths[tag] = float(gmsh.model.occ.getMass(1, tag))
            lo = np.asarray(gmsh.model.getBoundingBox(1, tag))
            mid = (lo[:3] + lo[3:]) / 2
            cut = self._size_at(mid) / 10
            if 1e-9 < length < cut:                    # zero: a degenerate edge (a cone's tip), which gmsh skips
                edges.append({'tag': tag, 'length_mm': round(length, 6), 'under_mm': round(cut, 6),
                              'center_mm': [round(float(v), 3) for v in mid]})
        self.slivers = {'faces': faces, 'edges': edges}
        if not (faces or edges) or self._slivers_mode == 'ignore':
            return
        listed = [f"face {f['tag']} ({f['kind']}, {f['area_mm2']:g} mm² at {tuple(f['center_mm'])})" for f in faces[:6]]
        listed += [f"edge {e['tag']} ({e['length_mm']:g} mm at {tuple(e['center_mm'])})" for e in edges[:6]]
        more = len(faces) + len(edges) - len(listed)
        msg = (f"{self.name}: {len(faces)} sliver face(s) and {len(edges)} short edge(s) for a {self.mesh_mm:g} mm mesh: "
               f"{'; '.join(listed)}{f'; and {more} more' if more > 0 else ''}. Slivers come from booleans and fillets "
               "that meet almost tangentially; the mesher may refuse the part or crowd poor elements there. Remove "
               "them in the CAD (merge the faces, change a dimension a little), or refine there.")
        if self._slivers_mode == 'raise':
            raise MeshRefusal(msg, 'slivers', faces=faces, edges=edges)
        import warnings
        warnings.warn(msg, MeshWarning, stacklevel=4)

    def _surface_mesh(self):
        """(points, gmsh node tag -> row, face tag -> triangles, edge tag -> segments) in the current gmsh session."""
        import gmsh
        tags, coords, _ = gmsh.model.mesh.getNodes()
        index = {int(t): i for i, t in enumerate(tags)}
        def rows(dim, tag, kind, n):
            types, _, nodes = gmsh.model.mesh.getElements(dim, tag)
            got = [np.asarray(v, dtype=np.int64).reshape(-1, n) for ty, v in zip(types, nodes) if ty == kind]
            return np.vectorize(index.get)(np.concatenate(got)) if got else np.zeros((0, n), int)
        face_tris = {f.tag: rows(2, f.tag, 2, 3) for f in self.faces}
        edge_segs = {tag: rows(1, tag, 1, 2) for _, tag in gmsh.model.getEntities(1)}
        return coords.reshape(-1, 3), index, face_tris, edge_segs

    def _refuse(self, errors, log):
        """Raise for a volume mesh gmsh would not make: a MeshRefusal naming the faces and edges round the point gmsh
        gives, measured on the surface mesh it did make (self.points, self.face_tris, self.edge_segs)."""
        why = parse_gmsh_refusal(log)
        if why is None:
            raise RuntimeError(f'{self.name}: gmsh could not mesh the volume: ' +
                               '; '.join(re.sub(r'^Error\s*:\s*', '', e) for e in errors[:3]))
        faces, edges = [], []
        if why['point'] is not None:
            p = np.asarray(why['point'], float)
            faces = _faces_near(p, self.faces, self.points, self.face_tris, k=4)
            for f in faces:
                f['named_by_gmsh'] = f['tag'] in why['surfaces']
            near = []
            for tag, seg in self.edge_segs.items():
                if not len(seg):
                    continue
                A, B = self.points[seg[:, 0]], self.points[seg[:, 1]]
                d = B - A
                t = np.clip(np.einsum('ij,ij->i', p - A, d) / np.maximum(np.einsum('ij,ij->i', d, d), 1e-300), 0, 1)
                near.append((float(np.linalg.norm(p - (A + t[:, None] * d), axis=1).min()), tag))
            for dist, tag in sorted(near)[:3]:
                length = self.edge_lengths.get(tag)
                edges.append({'tag': tag, 'length_mm': round(length, 4) if length is not None else None,
                              'distance_mm': round(dist, 4), 'named_by_gmsh': tag in why['curves']})
        at = f" at ({', '.join(f'{v:.3f}' for v in why['point'])}) mm" if why['point'] is not None else ''
        listed = ', '.join(f"face {f['tag']} ({f['kind']}, {f['area_mm2']:g} mm², {f['distance_mm']:.3f} mm away"
                           f"{', named by gmsh' if f['named_by_gmsh'] else ''})" for f in faces)
        short = [f"edge {e['tag']} ({e['length_mm']:g} mm)" for e in edges
                 if e['length_mm'] is not None and e['length_mm'] < self.mesh_mm]
        sliv = len(self.slivers['faces']) + len(self.slivers['edges'])
        msg = (f"{self.name}: gmsh would not mesh the volume: {why['what']}{at} (gmsh: '{why['message']}')."
               + (f' Nearest faces: {listed}.' if listed else '')
               + (f" Short edges near it: {', '.join(short)}." if short else '')
               + (f' The check before meshing found {sliv} sliver(s): see Study.slivers.' if sliv else '')
               + f' Faces closer together than the mesh size ({self.mesh_mm:g} mm), or meeting almost tangentially, '
               'get surface triangles that cut through each other. Thicken the gap or close it, remove the sliver in '
               'the CAD, or mesh finer there: refine=[(point, radius, size)].')
        raise MeshRefusal(msg, why['what'], point=why['point'], faces=faces, edges=edges, log=why['log'])

    def faces_near(self, point: Sequence[float], k: int = 4) -> List[dict]:
        """The k faces of the part nearest a point (mm), nearest first: {'tag', 'kind', 'area_mm2', 'distance_mm',
        'center_mm', 'radius_mm' for cylinders}. Distances are to each face's surface triangles (so to the mesh's
        chords on a curved face). Useful to name what sits at a hot spot or a mesher refusal's point."""
        return _faces_near(point, self.faces, self.points, self.face_tris, k)

    def _mesh_record(self) -> dict:
        """The mesh's part of the result: the mesher, the refine zones, the slivers found before meshing, and how well
        the mesh resolves the design peak (``peak``)."""
        rec = {'mesher': self.mesher,
               'refine': [{'at_mm': list(c), 'radius_mm': r, 'size_mm': s} for c, r, s in self.refine],
               'slivers': self.slivers, 'peak': self._peak_resolution()}
        if not rec['peak'].get('wall_resolved', True):
            import warnings
            warnings.warn(f"{self.name}: {rec['peak']['note']}", MeshWarning, stacklevel=3)
        return rec

    def _peak_resolution(self) -> dict:
        """How many elements lie across the wall at the design peak (the peak the safety factor uses).

        The wall is the thinnest one round the peak: from each surface triangle within two element sizes of the peak
        corner, a ray goes straight into the material to where it leaves it again, and the shortest of those is the
        wall. Elements across it = wall / the mean edge length of the tetrahedra at the peak corner, which is the number
        of element layers a structured mesh would put there (a ray through an unstructured mesh crosses more tets than
        that, so this is the cautious count). Under MIN_ELEMENTS_ACROSS the peak is flagged: a peak in a wall one or
        two elements thick is not a result."""
        m = self._m
        P, T = m.p.T, m.t.T
        free = ~self._touches_bc
        cand = np.where(free)[0] if free.any() else np.arange(len(T))
        e = int(cand[np.argmax(self.vm_elem[cand])])
        node = int(T[e, int(np.argmax(self.vm_corner[e]))])
        x = P[node]
        around = np.where((T == node).any(axis=1))[0]
        h = float(np.mean([np.linalg.norm(P[T[around, i]] - P[T[around, j]], axis=1).mean()
                           for i in range(4) for j in range(i + 1, 4)]))
        # the boundary, wound outward (as export_viewer does)
        bf = m.boundary_facets()
        tri = m.facets[:, bf].T.copy()
        opp = T[m.f2t[0, bf]].sum(axis=1) - tri.sum(axis=1)
        nrm = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])
        flip = np.einsum('ij,ij->i', nrm, P[opp] - P[tri[:, 0]]) > 0
        tri[flip, 1], tri[flip, 2] = tri[flip, 2], tri[flip, 1].copy()
        nrm[flip] *= -1
        unit = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-30)
        A = P[tri[:, 0]]
        E1, E2 = P[tri[:, 1]] - A, P[tri[:, 2]] - A
        cen = P[tri].mean(axis=1)
        dist = np.linalg.norm(cen - x, axis=1)
        near = np.where(dist <= max(2 * h, float(dist.min()) + h))[0]
        near = near[np.argsort(dist[near])][:24]
        walls = [w for i in near if (w := _ray_exit(cen[i], -unit[i], A, E1, E2, skip=1e-6 * h)) is not None]
        wall = min(walls) if walls else None
        vnorm = np.zeros_like(P)
        for k in range(3):
            np.add.at(vnorm, tri[:, k], nrm)
        vnorm /= np.maximum(np.linalg.norm(vnorm, axis=1, keepdims=True), 1e-30)
        verts = np.unique(tri)
        sv = int(verts[np.argmin(np.linalg.norm(P[verts] - x, axis=1))])
        where = (self._hint(sv, tri, nrm, vnorm, P) if float(np.linalg.norm(P[sv] - x)) < 0.5 * h
                 else f'inside the material, {float(np.linalg.norm(P[sv] - x)):.1f} mm under the surface')
        rec = {'stress_mpa': round(float(self.vm_elem[e]), 2), 'at_mm': [round(float(v), 3) for v in x], 'where': where,
               'element_mm': round(h, 3), 'wall_mm': round(wall, 3) if wall is not None else None,
               'elements_across': round(wall / h, 1) if wall is not None else None,
               'wall_resolved': bool(wall / h >= MIN_ELEMENTS_ACROSS) if wall is not None else None}
        notes = []
        if wall is not None and wall / h < MIN_ELEMENTS_ACROSS:
            notes.append(f'the design peak sits in a {wall:.1f} mm wall only {wall / h:.1f} elements thick: a peak in a '
                         'wall one or two elements thick is not a result. Mesh finer there (refine=[(point, radius, '
                         f'size)], a size under {wall / MIN_ELEMENTS_ACROSS:.2g} mm) and check it with converge()')
        if 'sharp inside corner' in where:
            notes.append('the peak is at a sharp re-entrant corner, which is singular: its stress rises with every '
                         'refinement and never converges. Model the fillet the part will have')
        rec['note'] = '; '.join(notes)
        return rec

    def converge(self, factor: float = 0.75, tolerance: float = 0.05) -> dict:
        """Solve the study again on a mesh `factor` times finer (mesh_mm and every refine size) and compare.

        The finer study gets the same faces fixed and loaded (the same STEP gives gmsh the same face tags; checked).
        Records and returns {'mesh_mm', 'tets', 'von_mises_design_mpa', 'max_displacement_mm' (each [this, finer]),
        'change' (the design peak's relative change), 'peak_moved_mm', 'converged', 'tolerance', 'note'} in
        ``result['mesh']['convergence']``, and keeps the finer study as ``self.finer``. Converged means the design peak
        changed by at most `tolerance`; a peak that moved more than two mesh sizes is noted either way (an artefact
        when its value changed too, else two spots near the peak value). A sharp re-entrant corner never converges.
        One step is a check, not a convergence study: for that, refine the peak in steps (refine=) and plot it."""
        if not 0 < factor < 1:
            raise ValueError('factor must be between 0 and 1 (0.75: a mesh a quarter finer)')
        if not hasattr(self, 'result'):
            self.solve()
        fine = Study(self._shape, self.material, self.mesh_mm * factor, self.name,
                     refine=[(c, r, s * factor) for c, r, s in self.refine], slivers='ignore')
        same = len(fine.faces) == len(self.faces) and all(
            a.tag == b.tag and a.kind == b.kind and math.isclose(a.area, b.area, rel_tol=1e-6, abs_tol=1e-9)
            for a, b in zip(self.faces, fine.faces))
        if not same:
            raise RuntimeError(f'{self.name}: the finer mesh numbers the faces differently, so the loads cannot be '
                               'carried over; build the finer Study and its loads by hand')
        fine.fixed, fine.probe_faces = list(self.fixed), list(self.probe_faces)
        fine.loads = [_Load(list(ld.faces), ld.force, ld.torque) for ld in self.loads]
        r1, r2 = self.result, fine.solve()
        a, b = r1['von_mises_design_mpa'], r2['von_mises_design_mpa']
        change = (b - a) / a if a else 0.0
        moved = math.dist(r1['mesh']['peak']['at_mm'], r2['mesh']['peak']['at_mm'])
        ok = abs(change) <= tolerance
        notes = []
        if not ok:
            notes.append(f'the design peak changed {change:+.1%} on a mesh {factor:g} x as fine: it is not converged')
        if moved > 2 * self.mesh_mm:                   # a peak that jumps elsewhere: an artefact, or two equal spots
            notes.append(f'the design peak moved {moved:.1f} mm, to {r2["mesh"]["peak"]["where"]}'
                         + (': the coarse peak was an artefact of the mesh there' if not ok else
                            ', at about the same stress (two places near the peak value; check both)'))
        if 'sharp inside corner' in r2['mesh']['peak']['where']:
            notes.append('the peak is at a sharp re-entrant corner, which never converges')
        rec = {'factor': factor, 'mesh_mm': [self.mesh_mm, fine.mesh_mm], 'tets': [r1['mesh']['tets'], r2['mesh']['tets']],
               'von_mises_design_mpa': [a, b], 'max_displacement_mm': [r1['max_displacement_mm'], r2['max_displacement_mm']],
               'change': round(change, 4), 'peak_moved_mm': round(moved, 2), 'converged': bool(ok),
               'tolerance': tolerance, 'note': '; '.join(notes)}
        self.result['mesh']['convergence'] = rec
        self.finer = fine
        if not ok:
            import warnings
            warnings.warn(f'{self.name}: ' + rec['note'], MeshWarning, stacklevel=2)
        return rec

    def select(self, selector: Selector) -> List[int]:
        tags = [f.tag for f in self.faces if selector(f)]
        if not tags:
            raise ValueError(f'{self.name}: the selector matched no faces')
        return tags

    # --- boundary conditions
    def fix(self, selector: Selector):
        """Clamp the selected faces (all three displacements zero): a bolted joint to something much stiffer."""
        self.fixed += self.select(selector)
        return self

    def force(self, selector: Selector, f_n: Sequence[float], probe: bool = True):
        """A force (N) spread evenly over the selected faces."""
        tags = self.select(selector)
        self.loads.append(_Load(tags, force=np.asarray(f_n, float)))
        if probe:
            self.probe_faces += tags
        return self

    def torque(self, selector: Selector, point: Sequence[float], axis: Sequence[float], t_nm: float, probe: bool = True):
        """A torque (N·m) about `axis`, applied over the selected faces as a pure couple about their own area centroid:
        no net force and a moment of exactly ``t_nm`` along ``axis`` (no bending moment, even for faces not balanced
        about the axis). `point` is only recorded with the load: a couple does not depend on where it acts, so it does
        not move the axis. To load a part with a force at a distance (a lever), add that force with force() as well."""
        tags = self.select(selector)
        a = np.asarray(axis, float)
        self.loads.append(_Load(tags, torque=(np.asarray(point, float), a / np.linalg.norm(a), t_nm * 1000.0)))
        if probe:
            self.probe_faces += tags
        return self

    # --- solve
    def solve(self) -> dict:
        from skfem import Basis, ElementTetP2, ElementVector, FacetBasis, Functional, LinearForm, MeshTet, asm, condense, solve
        from skfem.helpers import dot
        from skfem.models.elasticity import lame_parameters, linear_elasticity

        mat = self.material
        m = MeshTet(self.points.T.copy(), self.tets.T.copy())
        e = ElementVector(ElementTetP2())
        ib = Basis(m, e, intorder=2)
        lam, mu = lame_parameters(mat.E_mpa, mat.nu)
        K = asm(linear_elasticity(lam, mu), ib)

        lookup = {tuple(sorted(f)): i for i, f in enumerate(m.facets.T)}
        def facets_of(tags):
            out = []
            for tg in tags:
                for tri in self.face_tris[tg]:
                    i = lookup.get(tuple(sorted(tri)))
                    if i is not None:
                        out.append(i)
            return np.unique(np.asarray(out, dtype=np.int64))

        if not self.fixed:
            raise ValueError('nothing is fixed: call fix() first')
        D = ib.get_dofs(facets=facets_of(self.fixed)).all()
        f = np.zeros(K.shape[0])
        applied = []
        centroids = {}                                 # torque loads: the axis point actually used (the faces' centroid)
        for ld in self.loads:
            fac = facets_of(ld.faces)
            fb = FacetBasis(m, e, facets=fac, intorder=3)
            area = Functional(lambda w: 1.0 + 0.0 * w.x[0]).assemble(fb)
            if ld.force is not None:
                tr = ld.force / area
                f += asm(LinearForm(lambda v, w: dot(np.asarray(tr)[:, None, None] + 0.0 * w.x, v)), fb)
                applied.append({'kind': 'force', 'n': ld.force.tolist(), 'area_mm2': round(area, 1)})
            else:
                _, a, t = ld.torque
                c = np.array([Functional(lambda w, i=i: w.x[i]).assemble(fb) for i in range(3)]) / area   # the faces' centroid
                centroids[id(ld)] = c
                # traction om × r about the centroid: no resultant force, and moment Ic om. Choosing om = Ic⁻¹ (t a), with
                # Ic the faces' area inertia tensor about the centroid, makes the moment exactly t along the axis, also
                # for faces not balanced about it (an inclined end face, an end face plus a side face), where turning
                # them about the axis alone would add a bending moment. For a face square to the axis or a full
                # cylinder this is the usual traction, linear in the distance from the axis.
                Ic = np.zeros((3, 3))
                for i in range(3):
                    for j in range(i, 3):
                        Ic[i, j] = Ic[j, i] = Functional(lambda w, i=i, j=j: (i == j) * sum((w.x[k] - c[k]) ** 2 for k in range(3))
                                                         - (w.x[i] - c[i]) * (w.x[j] - c[j])).assemble(fb)
                if np.linalg.cond(Ic) > 1e12:
                    raise ValueError('torque faces have no extent to twist (a single line or point): select a face')
                om = t * np.linalg.solve(Ic, a)
                def tang(x):
                    r = x - c[:, None, None]
                    return np.stack([om[1] * r[2] - om[2] * r[1], om[2] * r[0] - om[0] * r[2], om[0] * r[1] - om[1] * r[0]])
                f += asm(LinearForm(lambda v, w: dot(tang(w.x), v)), fb)
                applied.append({'kind': 'torque', 'nm': t / 1000.0, 'axis': a.tolist(), 'point_mm': ld.torque[0].tolist(),
                                'about_centroid_mm': [round(float(v), 3) for v in c], 'area_mm2': round(area, 1)})

        u = self._solve(K, f, D, ib)
        self._m, self._ib, self._u = m, ib, u
        self._torque_centroids = centroids               # the viewer draws each torque about the axis actually used

        # stresses at each element's corners (the P2 strain is linear inside a tet, so its extremes are at the corners,
        # on the surface where bending stress peaks); von Mises per element = the largest of its corners
        Xv = np.array([[0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
        vb = Basis(m, e, quadrature=(Xv, np.full(4, 1.0 / 24)))
        uf = vb.interpolate(u)
        G = uf.grad                                   # (3, 3, nel, nqp)
        eps = 0.5 * (G + np.transpose(G, (1, 0, 2, 3)))
        tr = eps[0, 0] + eps[1, 1] + eps[2, 2]
        sig = 2 * mu * eps
        for i in range(3):
            sig[i, i] += lam * tr
        s = sig
        vm = np.sqrt(0.5 * ((s[0, 0] - s[1, 1]) ** 2 + (s[1, 1] - s[2, 2]) ** 2 + (s[2, 2] - s[0, 0]) ** 2)
                     + 3 * (s[0, 1] ** 2 + s[1, 2] ** 2 + s[2, 0] ** 2))
        self.vm_corner = vm                            # (n elements, 4 corners), corner k at m.t[k]
        self.vm_elem = vm.max(axis=1)
        disp = u[ib.nodal_dofs]                        # (3, n vertices)
        self.disp = disp
        mag = np.linalg.norm(disp, axis=0)
        probe_nodes = np.unique(np.concatenate([self.face_tris[t].ravel() for t in self.probe_faces])) if self.probe_faces else None
        probe = disp[:, probe_nodes].mean(axis=1) if probe_nodes is not None else None
        # the clamp and the load patches make artificial stress spikes, so the design stress is the peak over elements
        # that touch neither (the real peaks: fillets, holes, thin walls)
        bc_nodes = np.unique(np.concatenate([self.face_tris[t].ravel() for t in self.fixed + [x for ld in self.loads for x in ld.faces]]))
        touches = np.isin(self.tets, bc_nodes).any(axis=1)
        self._touches_bc = touches
        vm_peak = float(self.vm_elem.max())
        vm_design = float(self.vm_elem[~touches].max()) if (~touches).any() else vm_peak
        res = {
            'part': self.name, 'material': mat.name, 'material_note': mat.note,
            'material_source': mat.source or None, 'material_direction': mat.direction or None,
            'mesh': {'nodes': int(self.points.shape[0]), 'tets': int(self.tets.shape[0]), 'size_mm': self.mesh_mm, 'element': 'P2 tetrahedra'},
            'loads': applied,
            'max_displacement_mm': round(float(mag.max()), 4),
            'probe_displacement_mm': [round(float(v), 4) for v in probe] if probe is not None else None,
            'max_von_mises_mpa': round(vm_peak, 2),
            'von_mises_design_mpa': round(vm_design, 2),
            'safety_factor': round(mat.strength_mpa / vm_design, 2) if vm_design > 0 else None,
            'assumptions': f'linear elastic, small deflection, isotropic{_isotropic_basis(mat)}; faces clamped where fixed; '
                           'no contact, preload or buckling',
        }
        for ld in self.loads:                      # stiffness along each load
            if probe is None:
                break
            if ld.force is not None:
                d = float(np.dot(probe, ld.force) / np.linalg.norm(ld.force))
                res['stiffness_n_per_mm'] = round(float(np.linalg.norm(ld.force)) / d, 1) if d > 1e-12 else None
            else:
                _, a, t = ld.torque
                c = centroids[id(ld)]
                nodes = probe_nodes
                r = self.points[nodes] - c
                rp = r - np.outer(r @ a, a)
                tang = np.cross(a, rp)
                n2 = np.einsum('ij,ij->i', tang, tang)
                ok = n2 > 1e-9
                ang = float(np.mean(np.einsum('ij,ij->i', disp[:, nodes].T[ok], tang[ok]) / n2[ok]))   # radians
                res['torsional_stiffness_nm_per_deg'] = round(t / 1000.0 / math.degrees(ang), 2) if ang > 1e-12 else None
        res['mesh'].update(self._mesh_record())          # the mesher, refine zones, slivers, the peak's resolution
        self.result = res
        return res

    def _solve(self, K, f, D, ib):
        """PARDISO (pypardiso, multithreaded) when installed: about 20 times faster than SciPy's SuperLU on these
        problems; else SuperLU for small problems and multigrid-preconditioned CG for big ones."""
        from skfem import condense, solve
        try:
            import pypardiso
        except ImportError:
            pypardiso = None
        if pypardiso is not None:
            A, b, x, I = condense(K, f, D=D)
            x = x.copy()
            x[I] = pypardiso.spsolve(A.tocsr(), b)
            return x
        if K.shape[0] > 60000:
            return self._solve_iterative(K, f, D, self._rigid_modes(ib))
        return solve(*condense(K, f, D=D))

    @staticmethod
    def _rigid_modes(ib):
        """The six rigid-body motions sampled at every degree of freedom (multigrid needs them for elasticity)."""
        n = ib.N
        comp = np.zeros(n, dtype=int)
        for attr in ('nodal_dofs', 'edge_dofs', 'facet_dofs', 'interior_dofs'):
            arr = getattr(ib, attr, None)
            if arr is not None and arr.size:
                for c in range(arr.shape[0]):
                    comp[arr[c].ravel()] = c % 3
        x = ib.doflocs                                  # (3, n)
        B = np.zeros((n, 6))
        for c in range(3):
            B[comp == c, c] = 1.0
        X, Y, Z = x
        B[:, 3] = np.where(comp == 1, -Z, np.where(comp == 2, Y, 0.0))
        B[:, 4] = np.where(comp == 0, Z, np.where(comp == 2, -X, 0.0))
        B[:, 5] = np.where(comp == 0, -Y, np.where(comp == 1, X, 0.0))
        return B

    @staticmethod
    def _solve_iterative(K, f, D, B=None):
        import scipy.sparse.linalg as spla
        from skfem import condense
        A, b, x, I = condense(K, f, D=D)
        try:
            import pyamg
            M = pyamg.smoothed_aggregation_solver(A.tocsr(), B=None if B is None else B[I], max_coarse=500).aspreconditioner(cycle='V')
        except ImportError:                          # without pyamg: a diagonal preconditioner (slower)
            dg = A.diagonal()
            M = spla.LinearOperator(A.shape, matvec=lambda v: v / dg)
        sol, info = spla.cg(A, b, M=M, rtol=1e-8, maxiter=4000)
        if info != 0:
            raise RuntimeError(f'the iterative solver did not converge (info {info})')
        x = x.copy()
        x[I] = sol
        return x

    # --- failure bookkeeping shared by animate() and export_viewer()
    def _element_volumes(self) -> np.ndarray:
        P, T = self._m.p.T, self._m.t.T
        a, b, c, d = (P[T[:, i]] for i in range(4))
        return np.abs(np.einsum('ij,ij->i', np.cross(b - a, c - a), d - a)) / 6.0

    def _design_stress(self) -> float:
        """The peak element stress away from the clamp and load patches (unrounded): what the safety factor uses."""
        free = ~self._touches_bc
        return float(self.vm_elem[free].max()) if free.any() else float(self.vm_elem.max())

    def overstressed_share(self, load_factor: float) -> float:
        """Share of the part's volume in elements whose peak stress is past the strength at `load_factor` times the
        design load. An upper bound on the overstressed volume (a whole element counts once its peak corner passes),
        and, like the safety factor, it leaves out the elements touching a clamp or load patch."""
        vol = self._element_volumes()
        hit = (~self._touches_bc) & (self.vm_elem * load_factor > self.material.strength_mpa)
        return float(vol[hit].sum() / vol.sum())

    # --- picture
    def render(self, path, scale: Optional[float] = None, view=(25, -60), title: Optional[str] = None,
               vmax: Optional[float] = None):
        """Boundary of the deformed mesh coloured by von Mises stress, with the deformation exaggerated.

        ``scale`` is the deformation's exaggeration. When it is None, it is chosen so the largest displacement shows
        as 6 % of the part's size; that differs between studies.

        ``vmax`` (MPa) is the top of the colour scale. When it is None, the colour bar runs from 0 to this study's
        design stress (``result['von_mises_design_mpa']``, else the 99.5th percentile of the element stress), so two
        studies' renders use different colour scales. To compare variants, give every render the same ``vmax`` and
        the same ``scale``, for example the larger design stress of the pair, rounded up. Stress above ``vmax`` is
        drawn in the top colour. The colour bar then says the scale is fixed, and it names this study's design stress.
        Its top is drawn as an arrow only when that stress goes past ``vmax``. Colours are absolute MPa, so compare
        renders only under the same load case.

        Raises ValueError when ``vmax`` is not a positive, finite number."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        m = self._m
        bf = m.boundary_facets()
        tris = m.facets[:, bf].T
        elem = m.f2t[0, bf]
        size = float(np.ptp(self.points, axis=0).max())
        dmax = float(np.linalg.norm(self.disp, axis=0).max())
        if scale is None:
            scale = 0.06 * size / dmax if dmax > 0 else 1.0
        P = self.points + scale * self.disp.T
        vm = self.vm_elem[elem]
        fixed = vmax is not None
        if fixed and not (math.isfinite(vmax) and vmax > 0):
            raise ValueError(f'vmax must be a positive number of MPa, not {vmax!r}')
        own = float(self.result.get('von_mises_design_mpa') or np.percentile(self.vm_elem, 99.5)) or 1.0
        if not fixed:
            vmax = own
        cmap = plt.get_cmap('turbo')
        fig = plt.figure(figsize=(8, 6), dpi=110)
        ax = fig.add_subplot(111, projection='3d')
        pc = Poly3DCollection(P[tris], facecolors=cmap(np.clip(vm / vmax, 0, 1)), edgecolors='none', linewidths=0)
        ax.add_collection3d(pc)
        lo, hi = P.min(axis=0), P.max(axis=0)
        c, r = (lo + hi) / 2, (hi - lo).max() / 2
        ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(*view)
        ax.set_axis_off()
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, vmax))
        clipped = fixed and own > vmax
        fig.colorbar(sm, ax=ax, shrink=0.6, extend='max' if clipped else 'neither',
                     label=(f'von Mises stress (MPa), fixed scale 0-{vmax:g}; this design {own:.3g}' if fixed
                            else 'von Mises stress (MPa)'))
        res = getattr(self, 'result', {})
        ax.set_title(title or f"{self.name}: {res.get('material', '')}, SF {res.get('safety_factor')}, "
                     f"max {res.get('max_displacement_mm')} mm (deformation ×{scale:.0f})", fontsize=9)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches='tight')
        plt.close(fig)
        return path

    def animate(self, path, overload: float = 1.3, frames: int = 60, fps: int = 15, view=(25, -60),
                title: Optional[str] = None, scale: Optional[float] = None):
        """An overload video: the load ramps from zero through the design load (x1) to `overload` times the load at
        which the part first reaches its strength (x SF). Linear: displacements and stresses scale with the load, so
        each frame is the solved field times the load factor. Colour is stress over strength; past x SF the regions
        above the material's strength turn black (where it yields or the layers part first). It shows where and at what
        load a part fails, not how a crack grows after that. The deformation is exaggerated by one fixed factor,
        printed on every frame with the real displacement.

        Writes MP4 (H.264, needs ffmpeg) for a .mp4 path, else an animated GIF. Returns the path."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib import animation
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        res = self.result
        sf = res.get('safety_factor') or 1.0
        strength = self.material.strength_mpa
        lam_end = max(1.2, sf * overload)
        # hold briefly at the design load and at first failure, so both are readable
        keys = sorted({0.0, 1.0, sf, lam_end})
        ramp = []
        for k0, k1 in zip(keys, keys[1:]):
            n = max(4, int(frames * (k1 - k0) / lam_end))
            ramp += list(np.linspace(k0, k1, n, endpoint=False))
            if k1 in (1.0, sf):
                ramp += [k1] * (fps // 2)
        ramp += [lam_end] * fps

        m = self._m
        bf = m.boundary_facets()
        tris = m.facets[:, bf].T
        elem = m.f2t[0, bf]
        size = float(np.ptp(self.points, axis=0).max())
        dmax = float(np.linalg.norm(self.disp, axis=0).max())
        if scale is None:                               # at the last frame the deformation shows as ~8 % of the part
            scale = 0.08 * size / (dmax * lam_end) if dmax > 0 else 1.0
        # stress over strength at the design load, per boundary face; elements touching a clamp or a load patch carry
        # artificial spikes that the safety factor leaves out: capped at the design stress (never hotter than the
        # reported peak) and kept out of the black "past the strength" test
        vm = np.where(self._touches_bc, np.minimum(self.vm_elem, self._design_stress()), self.vm_elem)
        ratio = vm[elem] / strength
        support_tri = self._touches_bc[elem]
        vol = self._element_volumes()
        free = ~self._touches_bc
        bc_nodes = set(np.unique(np.concatenate([self.face_tris[t].ravel() for t in self.fixed])).tolist()) if self.fixed else set()
        fixed_tri = np.array([all(int(n) in bc_nodes for n in t) for t in tris])

        cmap = plt.get_cmap('turbo')
        fig = plt.figure(figsize=(9.6, 7.2), dpi=100)
        ax = fig.add_axes((0.0, 0.06, 0.86, 0.84), projection='3d')
        P_end = self.points + scale * lam_end * self.disp.T
        lo, hi = np.minimum(self.points.min(axis=0), P_end.min(axis=0)), np.maximum(self.points.max(axis=0), P_end.max(axis=0))
        c, r = (lo + hi) / 2, (hi - lo).max() / 2 * 0.78
        ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(*view)
        ax.set_axis_off()
        pc = Poly3DCollection(self.points[tris], edgecolors='none', linewidths=0)
        ax.add_collection3d(pc)
        for ld in self.loads:                           # an arrow per force, at the middle of its faces
            if ld.force is None:
                continue
            nodes = np.unique(np.concatenate([self.face_tris[t].ravel() for t in ld.faces]))
            p0 = self.points[nodes].mean(axis=0)
            dvec = ld.force / (np.linalg.norm(ld.force) or 1.0) * 0.28 * size
            ax.quiver(*(p0 - dvec), *dvec, color='#d0006f', linewidth=2.5, arrow_length_ratio=0.25)
        cax = fig.add_axes((0.88, 0.25, 0.022, 0.5))
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
        fig.colorbar(sm, cax=cax, label='stress / strength (black: past it)')
        fig.text(0.02, 0.965, title or f'{self.name}: {self.material.name}', fontsize=12, weight='bold')
        line = fig.text(0.02, 0.93, '', fontsize=10)
        line2 = fig.text(0.02, 0.905, '', fontsize=10)
        fig.text(0.02, 0.02, f'Linear elastic; deformation exaggerated x{scale:.0f}; grey = held; pink arrows = loads. '
                             'It shows where and at what load the part fails first, not how it breaks after.', fontsize=8, color='#555')

        def draw(k):
            lam = ramp[k]
            pc.set_verts((self.points + scale * lam * self.disp.T)[tris])
            q = ratio * lam
            col = cmap(np.clip(q, 0, 1))
            col[(q > 1.0) & ~support_tri] = (0.05, 0.05, 0.05, 1.0)
            col[fixed_tri] = (0.62, 0.64, 0.68, 1.0)
            pc.set_facecolor(col)
            state = ('design load' if abs(lam - 1) < 1e-9 else 'first failure' if abs(lam - sf) < 1e-9
                     else 'overload, past failure' if lam > sf else 'loading')
            over = float(vol[free & (self.vm_elem * lam > strength)].sum() / vol.sum()) * 100   # = overstressed_share
            line.set_text(f'load x{lam:.2f} of the design load: {state}')
            line2.set_text(f'max displacement {dmax * lam:.2f} mm,  peak stress {res.get("von_mises_design_mpa", 0) * lam:.0f} of '
                           f'{strength:.0f} MPa,  past the strength: {"<0.1" if 0 < over < 0.1 else f"{over:.1f}"} % of the volume '
                           '(elements whose peak passes it)')
            for t in (line, line2):
                t.set_color('#b00020' if lam > sf + 1e-9 else '#222')
            return pc, line, line2

        anim = animation.FuncAnimation(fig, draw, frames=len(ramp), blit=False)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.mp4' and animation.writers.is_available('ffmpeg'):
            anim.save(str(path), writer=animation.FFMpegWriter(fps=fps, codec='libx264', extra_args=['-pix_fmt', 'yuv420p', '-crf', '28']))
        else:
            path = path.with_suffix('.gif')
            anim.save(str(path), writer=animation.PillowWriter(fps=fps))
        plt.close(fig)
        return path

    # --- interactive viewer data
    def export_viewer(self, path, overload: float = 1.3, spots: int = 8) -> Path:
        """Write the solved study for the web kit's FEA viewer (webkit/fea-viewer.js, fea.html?case=<this file>).

        Compact JSON: the boundary surface only (vertices in mm, outward-wound triangles), with base64 float32/uint32
        arrays for the per-vertex displacement (mm, at the design load); the per-vertex von Mises stress (MPa), which
        is the highest corner stress of the elements meeting at the vertex, the same no-averaging convention as the
        safety factor; the volume-weighted average of those corners as `von_mises_smoothed` (shown as "smoothed": far
        below the peak means the mesh is coarse for that gradient); each triangle's element peak stress; per-vertex
        flags (1 held, 2 loaded, 4 only support elements meet here) and per-triangle flags (1 its element touches a
        clamp or load patch). Support elements carry artificial spikes that the safety factor leaves out: they are
        capped at the design stress and left out of the failure test, and their share is reported.

        Also the material, the result, the loads (arrows for forces, an axis for torques), the overstressed volume as
        an exact step curve over the load factor (the volume of the elements whose peak is past the strength: an
        upper bound, as in overstressed_share()), and the hot spots: the highest stresses away from the supports, at
        least 4 mesh sizes apart, each with the load factor at which it reaches the strength and a plain geometric
        hint read off the CAD faces.

        Linear: every field scales with the load factor, so the viewer scales them live. Returns the path."""
        import base64
        import json

        if not hasattr(self, 'vm_corner'):
            raise RuntimeError('solve() the study before export_viewer()')
        m = self._m
        P = m.p.T                                      # (n, 3) mm
        T = m.t.T                                      # (n elements, 4)
        S = float(self.material.strength_mpa)
        touches = self._touches_bc
        free = ~touches
        vm_design = self._design_stress()
        lam_fail = S / vm_design if vm_design > 0 else float('inf')
        lam_max = max(1.2, overload * lam_fail) if np.isfinite(lam_fail) else 1.2
        # support elements (touching a clamp or load patch) carry artificial spikes that the safety factor leaves out:
        # capped at the design stress, so they never read hotter than the reported peak, and kept out of the failure test
        corner = self.vm_corner.copy()
        corner[touches] = np.minimum(corner[touches], vm_design)
        elem = corner.max(axis=1)
        vol = self._element_volumes()
        n = len(P)
        # per node: the highest corner stress of the elements meeting there (no averaging, like the safety factor);
        # support elements count only where no other element meets
        peak_free, peak_sup, has_free = np.zeros(n), np.zeros(n), np.zeros(n, dtype=bool)
        np.maximum.at(peak_free, T[free].ravel(), corner[free].ravel())
        np.maximum.at(peak_sup, T[touches].ravel(), corner[touches].ravel())
        has_free[T[free].ravel()] = True
        node_vm = np.where(has_free, peak_free, peak_sup)
        def averaged(sel):                             # volume-weighted average of the corners, over the same elements
            num, den = np.zeros(n), np.zeros(n)
            np.add.at(num, T[sel].ravel(), (corner[sel] * vol[sel, None]).ravel())
            np.add.at(den, T[sel].ravel(), np.repeat(vol[sel], 4))
            return num / np.maximum(den, 1e-30)
        node_smooth = np.where(has_free, averaged(free), averaged(touches))   # shown as "smoothed"

        # the boundary surface, wound so the normals point out of the material
        bf = m.boundary_facets()
        tri = m.facets[:, bf].T.copy()
        own = m.f2t[0, bf]
        opp = T[own].sum(axis=1) - tri.sum(axis=1)     # the owning tet's fourth vertex
        nrm = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])
        flip = np.einsum('ij,ij->i', nrm, P[opp] - P[tri[:, 0]]) > 0
        tri[flip, 1], tri[flip, 2] = tri[flip, 2], tri[flip, 1].copy()
        nrm[flip] *= -1
        vnorm = np.zeros_like(P)                       # area-weighted outward normal at every surface node
        for k in range(3):
            np.add.at(vnorm, tri[:, k], nrm)
        vnorm /= np.maximum(np.linalg.norm(vnorm, axis=1, keepdims=True), 1e-30)
        verts = np.unique(tri)
        local = -np.ones(len(P), dtype=np.int64)
        local[verts] = np.arange(len(verts))

        nodes_of = lambda tags: np.unique(np.concatenate([self.face_tris[t].ravel() for t in tags])) if tags else np.zeros(0, int)
        held = nodes_of(self.fixed)
        loaded = nodes_of([x for ld in self.loads for x in ld.faces])
        flags = np.zeros(len(P), dtype=np.uint8)
        flags[held] |= 1
        flags[loaded] |= 2
        flags[~has_free] |= 4
        tri_flags = touches[own].astype(np.uint8)       # 1: the triangle's element is a support element (excluded)
        tri_area = 0.5 * np.linalg.norm(nrm, axis=1)

        def arr(x, dtype):
            x = np.ascontiguousarray(x, dtype=dtype)
            return {'dtype': np.dtype(dtype).name, 'shape': list(x.shape), 'b64': base64.b64encode(x.tobytes()).decode('ascii')}

        # loads: where each acts, and how far that patch moves at the design load (the arrows ride on the part)
        loads = []
        for ld in self.loads:
            tr = np.concatenate([self.face_tris[t] for t in ld.faces])
            ar = 0.5 * np.linalg.norm(np.cross(P[tr[:, 1]] - P[tr[:, 0]], P[tr[:, 2]] - P[tr[:, 0]]), axis=1)
            cen = (P[tr].mean(axis=1) * ar[:, None]).sum(axis=0) / max(ar.sum(), 1e-30)
            nodes = np.unique(tr)
            moved = self.disp[:, nodes].mean(axis=1)
            if ld.force is not None:
                mag = float(np.linalg.norm(ld.force))
                loads.append({'kind': 'force', 'origin': cen.tolist(), 'dir': (ld.force / (mag or 1.0)).tolist(), 'n': round(mag, 2),
                              'vector_n': ld.force.tolist(), 'disp': moved.tolist(), 'faces': list(ld.faces)})
            else:
                _, ax, t = ld.torque
                c0 = getattr(self, '_torque_centroids', {}).get(id(ld), ld.torque[0])   # the faces' centroid once solved
                rel = P[nodes] - c0
                along = rel @ ax
                radial = rel - np.outer(along, ax)
                loads.append({'kind': 'torque', 'point': c0.tolist(), 'axis': ax.tolist(), 'nm': round(t / 1000.0, 3),
                              'center': (c0 + float(along.mean()) * ax).tolist(),
                              'radius': round(float(np.linalg.norm(radial, axis=1).mean()), 3), 'disp': moved.tolist(),
                              'faces': list(ld.faces)})

        # hot spots: the highest element stresses away from the patches, spread at least 4 mesh sizes apart
        cand = np.where(~touches)[0]
        order = cand[np.argsort(-self.vm_elem[cand])]
        peak = float(self.vm_elem[order[0]]) if len(order) else 0.0
        min_gap = 4.0 * self.mesh_mm
        spot_list = []
        surf_pts = P[verts]
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(surf_pts)
        except ImportError:                            # scipy comes with scikit-fem; a plain search otherwise
            tree = None
        for e in order:
            s = float(self.vm_elem[e])
            if len(spot_list) >= spots or s < 0.2 * peak:
                break
            node = int(T[e, int(np.argmax(self.vm_corner[e]))])
            x = P[node]
            if any(np.linalg.norm(x - np.asarray(h['position'])) < min_gap for h in spot_list):
                continue
            if tree is not None:
                dist, iv = tree.query(x)
            else:
                dd = np.linalg.norm(surf_pts - x, axis=1)
                iv = int(np.argmin(dd)); dist = float(dd[iv])
            sv = int(verts[iv])
            smooth = float(node_smooth[node])
            spot_list.append({'rank': len(spot_list) + 1, 'position': x.tolist(), 'vertex': int(iv), 'normal': vnorm[sv].tolist(),
                              'stress_mpa': round(s, 2), 'of_strength': round(s / S, 3), 'fails_at': round(S / s, 3) if s > 0 else None,
                              'smoothed_mpa': round(smooth, 2), 'depth_mm': round(float(dist), 2),
                              'mesh_note': (f'the averaged stress here is {smooth / s:.0%} of the peak: refine the mesh to pin '
                                            'this value down') if smooth < 0.7 * s else '',
                              'hint': self._hint(sv, tri, nrm, vnorm, P) if dist < 0.5 * self.mesh_mm
                              else f'inside the material, {dist:.1f} mm under the surface'})

        # overstressed volume, exactly: each non-support element joins at its own failure load factor S / peak
        vtot = float(vol.sum())
        share = self.overstressed_share
        ff = S / np.maximum(self.vm_elem[free], 1e-30)
        order = np.argsort(ff)
        ff_s, cum = ff[order], np.cumsum(vol[free][order]) / vtot
        keep = ff_s <= lam_max * 1.0001
        ff_s, cum = np.floor(ff_s[keep] * 1e4) / 1e4, cum[keep]       # rounded down: the bound stays an upper bound
        last = np.r_[ff_s[1:] != ff_s[:-1], True] if len(ff_s) else np.zeros(0, bool)
        ff_s, cum = ff_s[last], cum[last]
        sup_area = float(tri_area[tri_flags == 1].sum() / max(tri_area.sum(), 1e-30))
        size = float(np.ptp(P, axis=0).max())
        res = {k: v for k, v in self.result.items()}
        data = {
            'format': 'cadagent-fea-viewer', 'version': 1, 'name': self.name,
            'units': {'length': 'mm', 'stress': 'MPa', 'force': 'N', 'torque': 'N·m'},
            'material': {'name': self.material.name, 'E_mpa': self.material.E_mpa, 'nu': self.material.nu,
                         'strength_mpa': S, 'note': self.material.note, 'source': self.material.source or None,
                         'direction': self.material.direction or None},
            'result': res, 'mesh_mm': self.mesh_mm, 'size_mm': round(size, 3),
            'bounds_mm': [P.min(axis=0).tolist(), P.max(axis=0).tolist()],
            'max_displacement_mm': float(np.linalg.norm(self.disp, axis=0).max()),
            'surface': {
                'vertices': int(len(verts)), 'triangles': int(len(tri)),
                'positions': arr(P[verts], np.float32),
                'index': arr(local[tri], np.uint32),
                'displacement': arr(self.disp[:, verts].T, np.float32),
                'von_mises': arr(node_vm[verts], np.float32),
                'von_mises_smoothed': arr(node_smooth[verts], np.float32),
                'tri_von_mises': arr(elem[own], np.float32),
                'flags': arr(flags[verts], np.uint8),
                'tri_flags': arr(tri_flags, np.uint8),
            },
            'flag_bits': {'held': 1, 'loaded': 2, 'support_only': 4},
            'tri_flag_bits': {'support': 1},
            'loads': loads,
            'failure': {
                'design_stress_mpa': round(vm_design, 3), 'first_failure_factor': round(lam_fail, 4) if np.isfinite(lam_fail) else None,
                'max_load_factor': round(lam_max, 4), 'capped_at_mpa': round(vm_design, 3),
                'excluded': {'surface_share': round(sup_area, 5), 'volume_share': round(float(vol[touches].sum() / vtot), 5),
                             'why': 'elements touching a clamp or load patch: idealised supports make artificial spikes '
                                    'there; like the safety factor, the failure test leaves them out'},
                'overstressed_volume': {'at_design_load': share(1.0), 'at_first_failure': share(lam_fail) if np.isfinite(lam_fail) else 0.0,
                                        'at_1.25x_first_failure': share(1.25 * lam_fail) if np.isfinite(lam_fail) else 0.0,
                                        'definition': 'volume of the elements whose peak stress is past the strength '
                                                      '(an upper bound), supports excluded, over the whole volume'},
                # a step function: the share is curve.share[i] for load factors above curve.load_factor[i]
                'curve': {'load_factor': [float(v) for v in ff_s], 'share': [float(f'{v:.4g}') for v in cum]},
            },
            'hot_spots': spot_list,
            'assumptions': (f'Linear elastic, small deflection, isotropic{_isotropic_basis(self.material)}. '
                            'Every field scales with the load. It shows where and at what load the part first reaches its '
                            'strength, not how a crack grows after that. Faces clamped where held; no contact, preload or '
                            'buckling. Elements touching the clamp and load patches are left out of the failure test and '
                            'capped at the design stress (their spikes are artefacts of the idealised supports). Stresses '
                            'are element corner peaks, as the safety factor uses; the overstressed volume counts whole '
                            'elements (an upper bound). The section cut shows the surface skin, not the stress inside.'),
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(',', ':'), default=float))
        return path

    def _cylinder_shape(self, f: Face, vnorm, P):
        """(concave, full) for a cylindrical face: a hole or inside fillet is concave (its outward normals point at the
        axis); full when it wraps far enough round that its normals face each other (a hole or a pin, not a fillet)."""
        tr = self.face_tris[f.tag]
        tr = tr[::max(1, len(tr) // 1500)]
        n = np.cross(P[tr[:, 1]] - P[tr[:, 0]], P[tr[:, 2]] - P[tr[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
        n *= np.sign(np.einsum('ij,ij->i', n, vnorm[tr].sum(axis=1)) + 1e-30)[:, None]   # outward, like the surface
        c = P[tr].mean(axis=1)
        concave = float(np.mean(np.einsum('ij,ij->i', n, c - c.mean(axis=0)))) < 0
        full = float((n @ n.T).min()) < -0.5
        return concave, full

    def _hint(self, node: int, tri, nrm, vnorm, P) -> str:
        """A short, honest description of where a surface node sits, from the CAD faces it lies on."""
        on = [f for f in self.faces if node in self.face_tris.get(f.tag, ())]
        cyl = [f for f in on if f.kind == 'Cylinder' and f.radius]
        num = lambda v: f'{v:.1f}'.rstrip('0').rstrip('.')
        if cyl:
            f = min(cyl, key=lambda f: f.radius)
            concave, full = self._cylinder_shape(f, vnorm, P)
            edge = 'edge of a' if len(on) > 1 else 'wall of a'
            if full:
                return f"{edge} Ø{num(2 * f.radius)} {'hole' if concave else 'boss or pin'}"
            return f"R{num(f.radius)} {'inside fillet' if concave else 'rounded edge'}"
        at = np.where((tri == node).any(axis=1))[0]
        if len(at) >= 2:
            n = nrm[at] / np.maximum(np.linalg.norm(nrm[at], axis=1, keepdims=True), 1e-30)
            cen = P[tri[at]].mean(axis=1)
            # any two triangles here at more than 40° to each other make an edge; if one such pair is concave (one
            # triangle lies on the other's outer side), it is an inside corner, also where it meets an outside edge
            # (the end of an inside corner on a side face, where three faces meet)
            I, J = np.nonzero(n @ n.T < math.cos(math.radians(40)))
            if len(I):
                if np.any(np.einsum('ij,ij->i', n[I], cen[J] - cen[I]) > 1e-9):
                    return 'sharp inside corner (no fillet: the peak there rises as the mesh is refined)'
                return 'outside edge'
        kinds = {f.kind for f in on}
        where = 'flat face' if kinds == {'Plane'} else 'curved face' if kinds else 'surface'
        # just beside a fillet or a hole (within about a mesh size): say which, that is usually the feature to change
        best = None
        for f in self.faces:
            if f.kind != 'Cylinder' or not f.radius or f in on:
                continue
            fn = np.unique(self.face_tris.get(f.tag, np.zeros((0, 3), int)))
            if not len(fn):
                continue
            dist = float(np.linalg.norm(P[fn] - P[node], axis=1).min())
            if dist <= 1.5 * self.mesh_mm and (best is None or dist < best[0]):
                best = (dist, f, fn)
        if best:
            dist, f, fn = best
            concave, full = self._cylinder_shape(f, vnorm, P)
            what = (f"Ø{num(2 * f.radius)} {'hole' if concave else 'boss or pin'}" if full
                    else f"R{num(f.radius)} {'inside fillet' if concave else 'rounded edge'}")
            return f'{where}, {dist:.1f} mm from an {what}' if what[0] in 'AEIOUR' else f'{where}, {dist:.1f} mm from a {what}'
        return where
