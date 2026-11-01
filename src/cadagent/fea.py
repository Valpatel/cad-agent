"""Linear-elastic stiffness and strength studies for any CAD part (STEP or a CadQuery shape).

    from cadagent.fea import Study, MATERIALS, cylinder_at, plane_at, in_box
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

Limits, stated in every result: linear and small-deflection; isotropic material. Printed parts are not isotropic, so
each printed material says which modulus and strength it uses and the print direction of the modulus
(``Material.note`` and ``Material.direction``); the assumptions line of every result repeats them. The defaults take the
lowest modulus the data sheet gives across the layers (Z), so deflections come out higher than with the sheet's
in-plane values, and a strength below the Z tensile strength, so the safety factor uses the weak direction. The mesh is
the solid CAD and the data sheet values come from 100 % infill test bars: a print with sparse infill or thin walls can
be softer still, and a force taken from the computed stiffness at a given travel (a clip's retention, a flexure's
preload) then reads low. Contact, bolt preload and buckling are not modelled. No simulation proves that a part will
fit or hold: check it against a printed coupon or the part itself.
"""
from __future__ import annotations

import math
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
#   do (they scale with 1/E). A low E makes the stiffness low, so a force taken from it at a given travel (a clip's
#   retention, a flexure's preload, a spring rate) reads low too.
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
# moduli (2750, 1790, 2890), not a tensile value. They were 31-116 % above the moduli used now (PAHT-CF 147 %, the
# humid PA6-CF rows 41 % and 130 %, TPU 305 %), so deflections read 24-54 % low (PAHT-CF 60 %, TPU 75 %).
_HUMID, _PRINT = 0.6, 0.8   # PA6-CF in use: x0.6 for moisture taken up from the air, x0.8 for a print's voids and seams
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
    # printed. Their factors are judgement, not data sheet values:
    # - x0.6 humid is a *strength* ratio: moisture roughly halves CF-nylon strength (Polymaker PA6-CF20 TDS V1.1,
    #   water-saturated / dry: 0.50 X-Y, 0.47 Z). It is applied to E as well, but that sheet's *modulus* ratios are
    #   0.29 X-Y and 0.28 Z, so for a part that has taken up water these moduli may be about twice too stiff and its
    #   deflections about half what they will be. Room humidity is milder than saturation; no sheet read gives E at
    #   it. Choosing a cited humid stiffness factor is #157.
    # - x0.8 print, for voids and seams, is a knock-down the original table applied to these rows only. The other
    #   rows carry none on E, so pa6_cf_z (1042) against petg_cf (1340) sets a derated value against a sheet value.
    'pa6_cf_xy': Material('PA6-CF along the layers (humid)', 4430 * _HUMID * _PRINT, 0.35, 102 * _HUMID * _PRINT, 1.09,
                          'Bambu PA6-CF TDS V3.0: dry X-Y tensile modulus 4430 MPa and strength 102 MPa, each x0.6 '
                          'humid x0.8 print (x0.48); E may be about twice too stiff for a part that has taken up water. '
                          'For parts printed so their main stress runs in the layers',
                          source='bambu-pa6-cf-tds', direction='X-Y'),
    'pa6_cf_z': Material('PA6-CF across the layers (humid)', 2170 * _HUMID * _PRINT, 0.35, 48 * _HUMID * _PRINT, 1.09,
                         'Bambu PA6-CF TDS V3.0: dry Z tensile modulus 2170 MPa and strength 48 MPa, each x0.6 humid '
                         'x0.8 print (x0.48); E may be about twice too stiff for a part that has taken up water. The '
                         'safe strength when the stress crosses the layers', source='bambu-pa6-cf-tds', direction='Z'),
    # Bambu TPU 95A HF TDS V1.0 (Bambu's copy, PDF created 2023-11): E 9.8 / 7.4 MPa, UTS 27.3 / 22.3 MPa, 1.22 g/cm3.
    # https://store.bblcdn.com/58df32731eab4c90a7dac9b12e13ba88.pdf
    # Polymaker's PolyFlex TPU95 (TDS V5.4) lists 33.6 MPa in X-Y (ISO 37). The sheets differ about 4x, and TPU is far
    # from linear, so a linear study of it is indicative only.
    'tpu95': Material('TPU 95A', 7.4, 0.45, 8, 1.22,
                      'Bambu TPU 95A HF TDS V1.0: E is the Z tensile modulus (X-Y 9.8 MPa); flexible, stiffness only '
                      'indicative', source='bambu-tpu-95a-hf-tds', direction='Z'),
    # Metals and the carbon tube: typical handbook values, not tied to a sheet in research/references.yaml. Checked
    # for #125: Protolabs' CNC data sheet for 6061-T651/T6 (2026) gives yield 276 MPa, E 10.0 Msi (68.9 GPa) and
    # 2.70 g/cm3. Its 7075-T651/T6 sheet gives only specification ranges: yield 434-476 MPa (T6 sheet) and 372-462 MPa
    # (T651 plate). Both are below the typical 503 MPa here, so a 7075 safety factor is optimistic.
    'al6061': Material('Aluminium 6061-T6', 68900, 0.33, 276, 2.70, 'typical yield strength'),
    'al7075': Material('Aluminium 7075-T6', 71700, 0.33, 503, 2.81,
                       'typical yield strength (specification minimums are lower)'),
    'steel': Material('Steel (mild)', 200000, 0.29, 250, 7.85, 'yield strength (ASTM A36 minimum)'),
    'cf_tube': Material('Carbon tube (roll-wrapped)', 64000, 0.3, 650, 1.55,
                        'axial modulus/strength, typical, not from a sheet: use the supplier\'s; not for local crushing'),
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


@dataclass
class _Load:
    faces: List[int]
    force: Optional[np.ndarray] = None
    torque: Optional[tuple] = None   # (point, axis, N·mm)


class Study:
    def __init__(self, shape, material: Material, mesh_mm: float = 3.0, name: str = 'part'):
        self.material, self.mesh_mm, self.name = material, mesh_mm, name
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

    def _mesh(self):
        import gmsh
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal', 0)
            gmsh.model.add(self.name)
            gmsh.model.occ.importShapes(str(self._step))
            gmsh.model.occ.synchronize()
            self.faces = []
            for _, tag in gmsh.model.getEntities(2):
                kind = gmsh.model.getType(2, tag)
                self.faces.append(Face(tag, kind, tuple(gmsh.model.getBoundingBox(2, tag)),
                                       np.array(gmsh.model.occ.getCenterOfMass(2, tag)), gmsh.model.occ.getMass(2, tag),
                                       self._cylinder_radius(tag) if kind == 'Cylinder' else None))
            gmsh.option.setNumber('Mesh.MeshSizeMax', self.mesh_mm)
            gmsh.option.setNumber('Mesh.MeshSizeMin', self.mesh_mm / 4)
            gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 10)
            gmsh.option.setNumber('Mesh.Optimize', 1)
            gmsh.model.mesh.generate(3)
            tags, coords, _ = gmsh.model.mesh.getNodes()
            index = {int(t): i for i, t in enumerate(tags)}
            self.points = coords.reshape(-1, 3)
            types, _, nodes = gmsh.model.mesh.getElements(3)
            tets = np.concatenate([np.asarray(n, dtype=np.int64).reshape(-1, 4) for ty, n in zip(types, nodes) if ty == 4])
            self.tets = np.vectorize(index.get)(tets)
            self.face_tris = {}
            for f in self.faces:
                ftypes, _, fnodes = gmsh.model.mesh.getElements(2, f.tag)
                tri = [np.asarray(n, dtype=np.int64).reshape(-1, 3) for ty, n in zip(ftypes, fnodes) if ty == 2]
                self.face_tris[f.tag] = np.vectorize(index.get)(np.concatenate(tri)) if tri else np.zeros((0, 3), int)
        finally:
            gmsh.finalize()
        # drop nodes that only belong to lower-dimensional entities, and orient every tet positively
        used = np.unique(self.tets)
        remap = -np.ones(len(self.points), dtype=np.int64)
        remap[used] = np.arange(len(used))
        self.points = self.points[used]
        self.tets = remap[self.tets]
        self.face_tris = {k: remap[v] for k, v in self.face_tris.items()}
        p = self.points
        a, b, c, d = (p[self.tets[:, i]] for i in range(4))
        neg = np.einsum('ij,ij->i', np.cross(b - a, c - a), d - a) < 0
        self.tets[neg, 2], self.tets[neg, 3] = self.tets[neg, 3], self.tets[neg, 2].copy()

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
    def render(self, path, scale: Optional[float] = None, view=(25, -60), title: Optional[str] = None):
        """Boundary of the deformed mesh coloured by von Mises stress; the deformation is exaggerated (scale)."""
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
        vmax = float(self.result.get('von_mises_design_mpa') or np.percentile(self.vm_elem, 99.5)) or 1.0
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
        fig.colorbar(sm, ax=ax, shrink=0.6, label='von Mises stress (MPa)')
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
            dots = n @ n.T
            i, j = np.unravel_index(int(np.argmin(dots)), dots.shape)
            if dots[i, j] < math.cos(math.radians(40)):
                if float(n[i] @ (cen[j] - cen[i])) > 0:
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
