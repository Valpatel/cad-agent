"""Topology optimisation of a part's material layout (pyMOTO, MIT): where must material be, for a given load?

    from cadagent.topopt import TopOpt
    t = TopOpt(lo=(0, 0, 0), hi=(206, 181, 8), voxel_mm=2.0, E_mpa=2060)   # a voxel box around the design region
    t.design(roof_slab)                 # CAD solid (CadQuery shape / trimesh / STL) the optimiser may hollow out
    t.keep(rim)                         # must stay solid (joints, bosses, sealing faces)
    t.void(fan_hole)                    # must stay empty (holes, clearances)
    t.fix((0, 0, 0), (12, 181, 8))      # supports: nodes inside a box (mm) held in all directions
    t.load((93, 80, 6), (113, 100, 8), (0, 0, -150))        # 150 N spread over the nodes inside a box
    res = t.run(volfrac=0.35, filter_mm=4.0, overhang='+z', maxit=80)
    t.render('preview/roof-topology.png'); t.animate('preview/roof-topology.mp4'); t.export_stl('exports/roof-topology.stl')

The problem is the classic minimum compliance (stiffest layout) for a volume fraction of the design region, with
SIMP penalisation (p = 3), a density filter of radius ``filter_mm`` (it sets the thinnest member, about twice the
radius) and, optionally, Langelaar's overhang filter so the layout prints without supports in the build direction.
Solved with MMA (Svanberg), linear elastic, small deflection. It is a design guide: its output is a density field
to read and turn into printable CAD (ribs, pockets, lattices), not a part to print as is.

The default modulus is PLA's across the layers (2060 MPa, ``cadagent.fea.MATERIALS['pla']``). With one material the
stiffest layout does not depend on E; only the compliance it reports does (it scales with 1/E).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from cadagent._deps import require

_WHY = 'topology optimisation'


def _mesh(shape):
    from cadagent.cfd import _mesh_of
    return _mesh_of(shape)


class TopOpt:
    def __init__(self, lo, hi, voxel_mm: float = 2.0, E_mpa: float = 2060.0, nu: float = 0.35):
        pym = require('pymoto', _WHY)
        self.lo, self.hi = np.asarray(lo, float), np.asarray(hi, float)
        self.h = float(voxel_mm)
        self.n = np.maximum(1, np.round((self.hi - self.lo) / self.h)).astype(int)
        self.hi = self.lo + self.n * self.h
        self.domain = pym.VoxelDomain(*self.n, unitx=self.h, unity=self.h, unitz=self.h)
        self.E, self.nu = E_mpa, nu
        self.centres = self.lo[:, None] + self.domain.get_element_position()      # (3, nel) mm
        self.nodes = self.lo[:, None] + self.domain.get_node_position()            # (3, nnodes) mm
        nel = self.domain.nel
        self.state = np.zeros(nel, dtype=np.int8)     # 0 outside, 1 design, 2 keep solid
        self.fixed: List[int] = []
        self.f = np.zeros(3 * self.domain.nnodes)
        self.history: List[np.ndarray] = []
        self.log: List[dict] = []
        self.loads = []

    def _inside(self, shape):
        m = _mesh(shape)
        lo, hi = m.bounds
        c = self.centres.T
        near = np.all((c >= lo - self.h) & (c <= hi + self.h), axis=1)
        out = np.zeros(len(c), bool)
        out[near] = m.contains(c[near])
        return out

    def design(self, shape=None):
        """Elements the optimiser may fill or empty (default: the whole box)."""
        mask = np.ones(self.domain.nel, bool) if shape is None else self._inside(shape)
        self.state[mask & (self.state == 0)] = 1
        return self

    def keep(self, shape):
        self.state[self._inside(shape)] = 2
        return self

    def void(self, shape):
        self.state[self._inside(shape)] = 0
        return self

    def _nodes_in(self, lo, hi):
        p = self.nodes.T
        return np.where(np.all((p >= np.asarray(lo) - 1e-6) & (p <= np.asarray(hi) + 1e-6), axis=1))[0]

    def fix(self, lo, hi, dofs: str = 'xyz'):
        nodes = self._nodes_in(lo, hi)
        if not len(nodes):
            raise ValueError(f'no nodes inside {lo}..{hi}')
        for d in dofs:
            self.fixed += list(3 * nodes + 'xyz'.index(d))
        return self

    def load(self, lo, hi, force_n: Sequence[float]):
        nodes = self._nodes_in(lo, hi)
        if not len(nodes):
            raise ValueError(f'no nodes inside {lo}..{hi}')
        for d in range(3):
            self.f[3 * nodes + d] += force_n[d] / len(nodes)
        self.loads.append({'lo': list(lo), 'hi': list(hi), 'force_n': list(force_n)})
        return self

    def run(self, volfrac: float = 0.3, filter_mm: float = 4.0, overhang: Optional[str] = None, maxit: int = 80,
            penal: float = 3.0, record_every: int = 2, verbose: bool = False) -> dict:
        pym = require('pymoto', _WHY)
        design = np.where(self.state == 1)[0]
        solid = np.where(self.state == 2)[0]
        empty = np.where(self.state == 0)[0]
        if not len(design):
            raise ValueError('no design elements: call design() first')
        if not self.fixed or not self.f.any():
            raise ValueError('add supports (fix) and at least one load first')
        xmin = 1e-6
        x0 = np.zeros(self.domain.nel)
        x0[design], x0[solid] = volfrac, 1.0
        sx = pym.Signal('x', state=x0)
        rec = self

        class _Record(pym.Module):
            k = 0

            def __call__(self, x):
                if self.k % record_every == 0:
                    rec.history.append(np.asarray(x, float).copy())
                self.k += 1
                return x

            def _sensitivity(self, dy):
                return dy

        n_design = len(design)
        mask = np.zeros(self.domain.nel)
        mask[design] = 1.0
        with pym.Network() as func:
            xf = pym.DensityFilter(self.domain, radius=filter_mm / self.h)(sx)
            if overhang:
                xf = pym.OverhangFilter(self.domain, direction=overhang)(xf)
            if len(solid):
                xf = pym.SetValue(solid, 1.0)(xf)
            if len(empty):
                xf = pym.SetValue(empty, 0.0)(xf)
            xa = _Record()(xf)
            simp = pym.MathExpression(f'{xmin} + {1 - xmin}*inp0^{penal}')(xa)
            K = pym.AssembleStiffness(self.domain, bc=np.unique(self.fixed), e_modulus=self.E, poisson_ratio=self.nu)(simp)
            u = pym.LinSolve(hermitian=True)(K, self.f)
            c = pym.EinSum('i,i->')(u, self.f)
            self._u, self._x = u, xa
            g0 = pym.Scaling(scaling=100.0)(c)
            vol = pym.EinSum('i,i->')(xa, mask)
            g1 = pym.MathExpression(f'10*(inp0/{n_design} - {volfrac})')(vol)
            logm = self

            class _Log(pym.Module):
                def __call__(self, cc, vv):
                    logm.log.append({'compliance_nmm': float(cc), 'volume_fraction': float(vv) / n_design})
                    return cc

                def _sensitivity(self, dy):
                    return dy, 0 * dy

            _Log()(c, vol)
        variables = sx
        # the passive elements are design variables too (their value is overwritten), so bound them to 0..1 freely
        pym.minimize_mma([variables], [g0, g1], function=func, maxit=maxit, verbosity=1 if verbose else 0)
        self.density = np.asarray(xa.state, float)
        self.history.append(self.density.copy())
        nd = self.density[design]
        res = {'voxel_mm': self.h, 'grid': self.n.tolist(), 'elements': int(self.domain.nel), 'design_elements': int(n_design),
               'keep_elements': int(len(solid)), 'volfrac_target': volfrac, 'volfrac_result': round(float(nd.mean()), 4),
               'solid_fraction_above_half': round(float((nd > 0.5).mean()), 4),
               'grey_fraction': round(float(((nd > 0.1) & (nd < 0.9)).mean()), 4),
               'compliance_nmm': round(float(np.asarray(self.f) @ np.asarray(self._u.state)), 4),
               'filter_mm': filter_mm, 'overhang': overhang, 'iterations': len(self.log), 'E_mpa': self.E, 'loads': self.loads,
               'method': 'SIMP p=3, density filter, MMA (pyMOTO); minimum compliance at a volume fraction of the design region'}
        self.result = res
        return res

    # --- geometry out
    def grid(self, density=None):
        pv = require('pyvista', _WHY)
        # one empty layer all round, so the iso-surface closes where material meets the box
        g = pv.ImageData(dimensions=tuple(self.n + 3), spacing=(self.h,) * 3, origin=tuple(self.lo - self.h))
        d = np.asarray(self.density if density is None else density, float).reshape(self.n[::-1])   # (z, y, x), x fastest
        g.cell_data['density'] = np.pad(d, 1).ravel()
        return g

    def surface(self, density=None, iso=0.5):
        g = self.grid(density).cell_data_to_point_data()
        s = g.contour([iso], scalars='density')
        return s.smooth_taubin(n_iter=30, pass_band=0.1) if s.n_points else s

    def export_stl(self, path, iso=0.5):
        s = self.surface(iso=iso)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        s.save(str(path))
        return path

    # --- pictures
    def _scene(self, p, density, context=()):
        from cadagent.simviz import SPEED_RAMP, cmap
        s = self.surface(density)
        if s.n_points:
            p.add_mesh(s, color='#2a78d6', smooth_shading=True, specular=0.3)
        for m, colour, op in context:
            p.add_mesh(m, color=colour, opacity=op)
        for ld in self.loads:
            lo, hi = np.asarray(ld['lo']), np.asarray(ld['hi'])
            c = (lo + hi) / 2
            f = np.asarray(ld['force_n'], float)
            d = f / (np.linalg.norm(f) or 1)
            L = 0.12 * float(np.max(self.hi - self.lo))
            pv = require('pyvista', _WHY)
            p.add_mesh(pv.Arrow(start=c - d * L, direction=d, scale=L), color='#d03b3b')

    def render(self, path, title='Topology optimisation', subtitle='', note='', view=(-35, 35), context=(), size=(1600, 1000)):
        from cadagent.simviz import _plotter, _camera, frame
        p = _plotter(size)
        self._scene(p, self.density, context)
        c = (self.lo + self.hi) / 2
        _camera(p, c, 2.4 * float(np.max(self.hi - self.lo)), *view)
        p.screenshot(str(path))
        p.close()
        r = getattr(self, 'result', {})
        return frame(path, title, subtitle or f"{r.get('volfrac_result', 0) * 100:.0f} % of the design region kept, "
                                             f"{self.h:g} mm voxels, filter {r.get('filter_mm')} mm" +
                     (f", overhang-free toward {r.get('overhang')}" if r.get('overhang') else ''),
                     note or 'Blue: material the load needs (density above 0.5). Red arrows: loads. A design guide, not a part to print as is.')

    def animate(self, path, fps=12, view=(-35, 35), context=(), size=(1280, 800), hold=1.5):
        from cadagent.simviz import _plotter, _camera, _writer
        w = _writer(path, fps)
        c = (self.lo + self.hi) / 2
        frames = self.history + [self.history[-1]] * int(hold * fps)
        for k, d in enumerate(frames):
            p = _plotter(size)
            self._scene(p, d, context)
            _camera(p, c, 2.4 * float(np.max(self.hi - self.lo)), view[0] + 25 * k / len(frames), view[1])
            p.add_text(f'iteration {min(k, len(self.history) - 1) * 2}', position='upper_left', font_size=12, color='#26323a')
            w.append_data(p.screenshot(return_img=True))
            p.close()
        w.close()
        return path


def hex_vents(t: 'TopOpt', density=None, threshold: float = 0.3, across_flats: float = 10.0, web: float = 1.8,
              region=None, axis: str = 'z', samples: int = 7) -> list:
    """Hexagonal openings that fit entirely where the optimised material is not needed: a printable reading of a
    topology result for a plate (floor, roof, wall). Every hex is sampled on a grid; it is kept only when the
    density, taken as the maximum through the plate's thickness (``axis``), stays below ``threshold`` everywhere in it
    and inside ``region`` (lo_u, lo_v, hi_u, hi_v) if given. Returns hex centres (u, v) in mm, on a honeycomb with
    ``across_flats`` cells and ``web`` walls (flat sides facing +/- v)."""
    import math
    d = np.asarray(t.density if density is None else density, float).reshape(t.n[::-1])   # (z, y, x)
    ax = 'xyz'.index(axis)
    plane = d.max(axis=2 - ax)                       # collapse the thickness axis
    uv = [i for i in range(3) if i != ax]
    lo, h = t.lo, t.h
    if plane.shape != (t.n[uv[1]], t.n[uv[0]]):
        plane = plane.T

    def dens(u, v):
        i = int((u - lo[uv[0]]) // h)
        j = int((v - lo[uv[1]]) // h)
        if not (0 <= i < t.n[uv[0]] and 0 <= j < t.n[uv[1]]):
            return 1.0
        return plane[j, i]

    s = across_flats
    R = s / math.sqrt(3)
    pitch = s + web
    dx = pitch * math.sqrt(3) / 2
    u0, v0 = lo[uv[0]], lo[uv[1]]
    u1, v1 = lo[uv[0]] + t.n[uv[0]] * h, lo[uv[1]] + t.n[uv[1]] * h
    if region:
        u0, v0, u1, v1 = max(u0, region[0]), max(v0, region[1]), min(u1, region[2]), min(v1, region[3])
    pts = []
    k = np.linspace(-1, 1, samples)
    offs = [(a * R, b * s / 2) for a in k for b in k if abs(b * s / 2) <= s / 2 and abs(a * R) + abs(b * s / 2) / math.sqrt(3) <= R + 1e-9]
    i = 0
    u = u0 + R
    while u + R <= u1:
        v = v0 + s / 2 + (pitch / 2 if i % 2 else 0)
        while v + s / 2 <= v1:
            if all(dens(u + a, v + b) < threshold for a, b in offs):
                pts.append((round(u, 3), round(v, 3)))
            v += pitch
        u += dx
        i += 1
    return pts
