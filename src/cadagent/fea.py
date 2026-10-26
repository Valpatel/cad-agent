"""Linear-elastic stiffness and strength studies for any CAD part (STEP or a CadQuery shape).

    from cadagent.fea import Study, MATERIALS, cylinder_at, plane_at, in_box
    st = Study('exports/thigh.step', MATERIALS['petg_cf'], mesh_mm=3.0)
    st.fix(cylinder_at(center=(0, 0, 0), axis=(0, 1, 0)))                       # bolt holes at the motor flange
    st.force(cylinder_at(center=(0, 0, -200), axis=(0, 1, 0)), (0, 0, 300))     # 300 N at the knee pin
    res = st.solve()          # dict: max von Mises (MPa), max and probe displacement (mm), stiffness, safety factor
    st.render('exports/fea/thigh.png')

Units: millimetres, newtons, MPa (N/mm²), so displacements come out in mm and stresses in MPa.

How it works: gmsh meshes the solid with tetrahedra (it reads the STEP through OpenCASCADE, so every face of the CAD
keeps its identity); scikit-fem solves linear elasticity with quadratic (P2) displacement on those tetrahedra, which
handles bending well even with a few elements through a wall. Faces are picked with selectors (functions of a face's
kind, bounding box, centre and area). Loads spread over the chosen faces: a force as a uniform traction, a torque as a
tangential traction that grows with the distance from the axis (like bolts sharing a twisting load).

Solvers: PARDISO (pip install pypardiso) when available, else SciPy's direct solver, or conjugate gradients with a
smoothed-aggregation multigrid preconditioner (pyamg, with the six rigid-body modes) for big meshes.

Limits, stated in every result: linear and small-deflection; isotropic material. Printed parts are not isotropic, so
the printed materials carry an effective modulus and a strength for the weak (layer) direction, and the safety factor
uses the weak-direction strength. Contact, bolt preload and buckling are not modelled.
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
    E_mpa: float                 # Young's modulus (effective, for printed parts)
    nu: float
    strength_mpa: float          # the strength the safety factor uses (yield for metals; weak-direction for prints)
    density_g_cm3: float
    note: str = ''


# Printed values: effective moduli and layer-direction strengths for well-printed parts (100 % walls near loads),
# rounded down from Bambu Lab's TDS figures; treat them as design allowables to check against tests.
MATERIALS = {
    'pla': Material('PLA', 2700, 0.35, 25, 1.24, 'Bambu PLA Basic: Z (layer) strength used'),
    'petg': Material('PETG', 1800, 0.38, 20, 1.27, 'Bambu PETG Basic: Z (layer) strength used'),
    'petg_cf': Material('PETG-CF', 2900, 0.36, 22, 1.29, 'Bambu PETG-CF: Z (layer) strength used'),
    'pa_cf': Material('PA6-CF', 4500, 0.35, 40, 1.17, 'Bambu PAHT-CF (dry): Z (layer) strength used'),
    # PA6-CF as it is in use: nylon takes up moisture from the air and loses ~40 % of its strength and stiffness
    # (x0.6 on Bambu's dry TDS), and a print has voids and seams (x0.8): design allowables, to confirm with coupons
    'pa6_cf_xy': Material('PA6-CF along the layers (humid)', 3000, 0.35, 49, 1.17,
                          'Bambu PA6-CF TDS 102 MPa dry in the layers, x0.6 humid, x0.8 print: for parts printed so their main stress runs in the layers'),
    'pa6_cf_z': Material('PA6-CF across the layers (humid)', 2400, 0.35, 23, 1.17,
                         'Bambu PA6-CF TDS 48 MPa dry across the layers, x0.6 humid, x0.8 print: the safe value when the stress crosses the layers'),
    'tpu95': Material('TPU 95A', 30, 0.45, 8, 1.22, 'flexible: stiffness only indicative'),
    'al6061': Material('Aluminium 6061-T6', 68900, 0.33, 276, 2.70, 'yield strength'),
    'al7075': Material('Aluminium 7075-T6', 71700, 0.33, 503, 2.81, 'yield strength'),
    'steel': Material('Steel (mild)', 200000, 0.29, 250, 7.85, 'yield strength'),
    'cf_tube': Material('Carbon tube (roll-wrapped)', 64000, 0.3, 650, 1.55, 'axial modulus/strength; not for local crushing'),
}


@dataclass
class Face:
    tag: int
    kind: str                    # gmsh/OCC surface type: 'Plane', 'Cylinder', 'Cone', 'BSpline surface', ...
    bbox: tuple                  # (xmin, ymin, zmin, xmax, ymax, zmax)
    center: np.ndarray           # centre of mass of the face
    area: float


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
        self._step = self._as_step(shape)
        self.fixed: List[int] = []
        self.loads: List[_Load] = []
        self.probe_faces: List[int] = []
        self._mesh()

    # --- geometry and mesh
    @staticmethod
    def _as_step(shape) -> Path:
        if isinstance(shape, (str, Path)):
            return Path(shape)
        import cadquery as cq
        tmp = Path(tempfile.mkdtemp(prefix='cadagent-fea-')) / 'part.step'
        cq.exporters.export(shape.val() if hasattr(shape, 'val') else shape, str(tmp))
        return tmp

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
                self.faces.append(Face(tag, gmsh.model.getType(2, tag), tuple(gmsh.model.getBoundingBox(2, tag)),
                                       np.array(gmsh.model.occ.getCenterOfMass(2, tag)), gmsh.model.occ.getMass(2, tag)))
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
        """A torque (N·m) about the axis through point, applied over the selected faces as tangential traction."""
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
        for ld in self.loads:
            fac = facets_of(ld.faces)
            fb = FacetBasis(m, e, facets=fac, intorder=3)
            area = Functional(lambda w: 1.0 + 0.0 * w.x[0]).assemble(fb)
            if ld.force is not None:
                tr = ld.force / area
                f += asm(LinearForm(lambda v, w: dot(np.asarray(tr)[:, None, None] + 0.0 * w.x, v)), fb)
                applied.append({'kind': 'force', 'n': ld.force.tolist(), 'area_mm2': round(area, 1)})
            else:
                c, a, t = ld.torque
                def rperp(x):
                    r = x - c[:, None, None]
                    return r - np.einsum('i,ijk->jk', a, r)[None] * a[:, None, None]
                J = Functional(lambda w: np.sum(rperp(w.x) ** 2, axis=0)).assemble(fb)
                def tang(x):
                    r = rperp(x)
                    return (t / J) * np.stack([a[1] * r[2] - a[2] * r[1], a[2] * r[0] - a[0] * r[2], a[0] * r[1] - a[1] * r[0]])
                f += asm(LinearForm(lambda v, w: dot(tang(w.x), v)), fb)
                applied.append({'kind': 'torque', 'nm': t / 1000.0, 'axis': a.tolist(), 'point_mm': c.tolist(), 'area_mm2': round(area, 1)})

        u = self._solve(K, f, D, ib)
        self._m, self._ib, self._u = m, ib, u

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
            'mesh': {'nodes': int(self.points.shape[0]), 'tets': int(self.tets.shape[0]), 'size_mm': self.mesh_mm, 'element': 'P2 tetrahedra'},
            'loads': applied,
            'max_displacement_mm': round(float(mag.max()), 4),
            'probe_displacement_mm': [round(float(v), 4) for v in probe] if probe is not None else None,
            'max_von_mises_mpa': round(vm_peak, 2),
            'von_mises_design_mpa': round(vm_design, 2),
            'safety_factor': round(mat.strength_mpa / vm_design, 2) if vm_design > 0 else None,
            'assumptions': 'linear elastic, small deflection, isotropic; faces clamped where fixed; no contact, preload or buckling',
        }
        for ld in self.loads:                      # stiffness along each load
            if probe is None:
                break
            if ld.force is not None:
                d = float(np.dot(probe, ld.force) / np.linalg.norm(ld.force))
                res['stiffness_n_per_mm'] = round(float(np.linalg.norm(ld.force)) / d, 1) if d > 1e-12 else None
            else:
                c, a, t = ld.torque
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
        # artificial spikes (the safety factor ignores them too), so they are capped just under the strength
        vm = np.where(self._touches_bc, np.minimum(self.vm_elem, 0.99 * strength / lam_end), self.vm_elem)
        ratio = vm[elem] / strength
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
            col[q > 1.0] = (0.05, 0.05, 0.05, 1.0)
            col[fixed_tri] = (0.62, 0.64, 0.68, 1.0)
            pc.set_facecolor(col)
            state = ('design load' if abs(lam - 1) < 1e-9 else 'first failure' if abs(lam - sf) < 1e-9
                     else 'overload, past failure' if lam > sf else 'loading')
            over = float((vm * lam > strength).mean()) * 100
            line.set_text(f'load x{lam:.2f} of the design load: {state}')
            line2.set_text(f'max displacement {dmax * lam:.2f} mm,  peak stress {res.get("von_mises_design_mpa", 0) * lam:.0f} of '
                           f'{strength:.0f} MPa,  past the strength: {over:.1f} % of the part')
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
