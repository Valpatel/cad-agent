"""Airflow and heat: steady conjugate heat transfer (CHT) cases for OpenFOAM, written from CAD.

    from cadagent.cfd import ThermalCase, Fan, SOLIDS
    case = ThermalCase('cooled', domain=((-100, -100, -3), (306, 290, 260)), cell_mm=8, ambient_c=25)
    case.wall('enclosure', [base, cover, front, rear], level=2)          # no-slip, adiabatic obstacles
    case.solid('soc', soc_box, SOLIDS['silicon'], power_w=40, level=3)   # a heat source
    case.solid('fins', fins, SOLIDS['al6063'], level=3)
    case.contact('ttp', 'base', thickness_mm=0.5, k=6.0)                 # a thermal pad between two solids
    case.fan(Fan('fan', centre=(105, 106, 83), axis=(0, 0, -1), d_outer=88, d_hub=30, thickness=8,
                 dp0_pa=30, q_free_m3h=60))
    case.write('sim/cooled'); case.run('sim/cooled', np=20)
    res = case.results('sim/cooled')   # max/mean temperature of each solid, fan flow, energy balance, residuals

Everything is in millimetres and degrees Celsius at the interface; the case itself is SI (metres, kelvin), as
OpenFOAM expects. The solver is chtMultiRegionSimpleFoam (OpenFOAM.com, GPL, run as an external program, by default
in the official ``opencfd/openfoam-default`` Docker image): buoyant compressible air (perfect gas, k-omega SST), and
heat conduction in each solid region, coupled at the interfaces. snappyHexMesh meshes the air and the solids from
STL; each solid becomes its own region.

The fan is an actuator disc, not a rotor: a momentum source in a thin annulus whose pressure rise falls linearly
from ``dp0_pa`` at zero flow to nothing at the free-air flow (a straight-line fan curve). The fan sees the real
impedance of the fins and vents, so its operating point is computed, not assumed.

Limits, written into every result: steady RANS (natural-convection plumes really fluctuate); no radiation
(it carries a large share of the heat from a bare hot plate in still air, so passive cases are pessimistic);
isotropic solids (heat pipes are an effective conductivity, not a two-phase model); obstacles are adiabatic.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from cadagent._deps import require

_WHY = 'the CFD case writer'
IMAGE = 'opencfd/openfoam-default:2512'
T0 = 273.15
AIR_CP = 1005.0


@dataclass(frozen=True)
class ThermalMaterial:
    name: str
    rho: float      # kg/m3
    cp: float       # J/(kg K)
    k: float        # W/(m K)
    note: str = ''


# Conductivities at room temperature. Printed plastics: the bulk polymer (infill lowers it further).
SOLIDS = {
    'al6063': ThermalMaterial('Aluminium 6063 (extruded fins)', 2700, 900, 200),
    'al6061': ThermalMaterial('Aluminium 6061', 2700, 896, 167),
    'copper': ThermalMaterial('Copper C11000', 8940, 385, 390),
    'silicon': ThermalMaterial('Silicon die and package (lumped)', 2330, 700, 120, 'lumped package, not a die model'),
    'fr4': ThermalMaterial('FR-4 with copper planes (in-plane, lumped)', 1850, 1100, 20, 'isotropic stand-in for a multilayer board'),
    'heatpipe_base': ThermalMaterial('Copper base with embedded heat pipes (effective)', 6000, 385, 1500,
                                     'effective isotropic conductivity of a base with flattened heat pipes; a two-phase pipe is far '
                                     'more conductive along its axis and has a dry-out limit that this does not model'),
    'pla': ThermalMaterial('PLA', 1240, 1800, 0.13),
    'petg': ThermalMaterial('PETG', 1270, 1300, 0.20),
    'tim': ThermalMaterial('Thermal pad', 3000, 1000, 6.0),
}


@dataclass
class Fan:
    """An axial fan as an actuator disc: centre (mm), axis = direction the air is pushed, linear fan curve."""
    name: str
    centre: Sequence[float]
    axis: Sequence[float]
    d_outer: float
    d_hub: float
    thickness: float
    dp0_pa: float            # static pressure at zero flow
    q_free_m3h: float        # free-air flow (m3/h; 1 CFM = 1.699 m3/h)
    note: str = ''

    @property
    def area_m2(self) -> float:
        return math.pi / 4 * ((self.d_outer / 1000) ** 2 - (self.d_hub / 1000) ** 2)

    def source(self) -> Tuple[np.ndarray, float]:
        """Force density (N/m3) along the axis at zero flow, and the implicit drag coefficient (kg/m3/s) that makes the
        pressure rise across the disc fall to zero at the free-air velocity."""
        t = self.thickness / 1000
        a = np.asarray(self.axis, float)
        a = a / np.linalg.norm(a)
        v_free = self.q_free_m3h / 3600 / self.area_m2
        return a * self.dp0_pa / t, self.dp0_pa / (v_free * t)


@dataclass
class _Body:
    name: str
    path: Path               # STL in metres
    kind: str                # 'wall' | 'solid'
    level: Tuple[int, int]
    material: Optional[ThermalMaterial] = None
    power_w: float = 0.0
    inside: Optional[np.ndarray] = None   # a point inside the solid (m)


def _mesh_of(shape, tol=0.05):
    """A trimesh in mm from a CadQuery shape/workplane, a trimesh, an STL path, or a list of those."""
    trimesh = require('trimesh', _WHY)
    if isinstance(shape, (list, tuple)):
        return trimesh.util.concatenate([_mesh_of(s, tol) for s in shape])
    if isinstance(shape, trimesh.Trimesh):
        return shape
    if isinstance(shape, (str, Path)):
        return trimesh.load(str(shape), force='mesh')
    s = shape.val() if hasattr(shape, 'val') else shape
    verts, tris = s.tessellate(tol, 0.2)
    return trimesh.Trimesh(np.array([(v.x, v.y, v.z) for v in verts]), np.array(tris), process=True)


def interior_point(mesh) -> np.ndarray:
    """A point well inside a closed mesh (mm): the deepest of a grid of candidates."""
    lo, hi = mesh.bounds
    n = 12
    g = np.stack(np.meshgrid(*[np.linspace(lo[i], hi[i], n + 2)[1:-1] for i in range(3)], indexing='ij'), -1).reshape(-1, 3)
    inside = g[mesh.contains(g)]
    if not len(inside):
        c = mesh.centroid
        if mesh.contains([c])[0]:
            return c
        raise ValueError('no interior point found: is the solid closed and thicker than its bounding box / 13?')
    trimesh = require('trimesh', _WHY)
    d = trimesh.proximity.signed_distance(mesh, inside)
    return inside[int(np.argmax(d))]


class ThermalCase:
    def __init__(self, name: str, domain, cell_mm: float = 8.0, ambient_c: float = 25.0,
                 gravity=(0, 0, -9.81), ground: bool = True, iterations: int = 1500, write_every: int = 0,
                 fluid: str = 'domain0'):
        self.name, self.cell_mm, self.ambient_c = name, cell_mm, ambient_c
        self.lo, self.hi = (np.asarray(p, float) for p in domain)
        self.gravity, self.ground, self.iterations = gravity, ground, iterations
        self.write_every = write_every or iterations
        self.fluid = fluid
        self.bodies: List[_Body] = []
        self.fans: List[Fan] = []
        self.contacts: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.boxes: List[Tuple[np.ndarray, np.ndarray, int]] = []
        self.porous: List[dict] = []
        self.fluid_point: Optional[np.ndarray] = None
        self._meshes = {}

    # --- geometry
    def wall(self, name, shape, level=(1, 2)):
        """An obstacle with no-slip, adiabatic walls (enclosure, boards, cables)."""
        self._add(name, shape, 'wall', level)
        return self

    def solid(self, name, shape, material: ThermalMaterial, power_w: float = 0.0, level=(2, 3)):
        """A conducting solid region; ``power_w`` spreads that heat evenly through its volume."""
        self._add(name, shape, 'solid', level, material, power_w)
        return self

    def contact(self, a: str, b: str, thickness_mm: float, k: float):
        """A thin layer (thermal pad, paste, air gap) between two touching solids, as a resistance on their interface."""
        self.contacts[(a, b)] = (thickness_mm / 1000, k)
        return self

    def fan(self, fan: Fan):
        self.fans.append(fan)
        return self

    def porous_box(self, name, lo, hi, d, f, e1=(1, 0, 0), e2=(0, 1, 0), heat_w: float = 0.0, ha_w_k: Optional[float] = None,
                   fin_temperature_c: Optional[float] = None, note: str = ''):
        """A block of air with a Darcy-Forchheimer resistance (d 1/m2, f 1/m per local axis e1, e2, e3 = e1 x e2): a
        compact model of a fin block or a filter (lo, hi in mm). Heat, either way:

        - ``ha_w_k`` and ``fin_temperature_c``: isothermal fins with conductance hA (W/K, h x area x fin efficiency)
          heat each cell's air by hA/V (T_fin - T_air). Air cannot get hotter than the fins, and the heat goes where the
          air flows. ``calibrate_fins()`` then sets T_fin so the block delivers a target power. Prefer this.
        - ``heat_w``: that power released evenly through the block's volume. Simple, but air that stagnates in a corner
          of the block heats without limit."""
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', name):
            raise ValueError(f'{name!r}: zone names must be letters and digits only')
        if (ha_w_k is None) != (fin_temperature_c is None):
            raise ValueError('give both ha_w_k and fin_temperature_c, or neither')
        self.porous.append({'name': name, 'lo': np.asarray(lo, float), 'hi': np.asarray(hi, float), 'd': tuple(d), 'f': tuple(f),
                            'e1': tuple(e1), 'e2': tuple(e2), 'heat_w': heat_w, 'ha_w_k': ha_w_k,
                            'fin_temperature_c': fin_temperature_c, 'note': note})
        return self

    def refine(self, lo, hi, level: int):
        """Cells no bigger than cell_mm / 2**level inside the box lo..hi (mm)."""
        self.boxes.append((np.asarray(lo, float), np.asarray(hi, float), level))
        return self

    def _add(self, name, shape, kind, level, material=None, power_w=0.0):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', name):
            raise ValueError(f'{name!r}: region and patch names must be letters and digits only')
        lv = (level, level) if isinstance(level, int) else tuple(level)
        m = _mesh_of(shape)
        self._meshes[name] = m
        b = _Body(name, Path(f'{name}.stl'), kind, lv, material, power_w)
        if kind == 'solid' and not m.is_watertight:
            raise ValueError(f'{name}: a solid region needs a closed surface (its inside becomes the region)')
        self.bodies.append(b)

    def _fluid_point(self):  # metres
        if self.fluid_point is not None:
            return self.fluid_point / 1000
        # just inside the domain's top corner: open air, away from the model
        span = self.hi - self.lo
        return (self.lo + np.array([0.03, 0.03, 0.97]) * span) / 1000

    # --- case files
    def write(self, case_dir, np_procs: int = 16):
        case = Path(case_dir)
        if case.exists():
            shutil.rmtree(case)
        tri = case / 'constant' / 'triSurface'
        tri.mkdir(parents=True)
        for b in self.bodies:
            m = self._meshes[b.name].copy()
            m.apply_scale(0.001)
            m.export(str(tri / b.path))
        solids = [b for b in self.bodies if b.kind == 'solid']
        regions = [self.fluid] + [b.name for b in solids]
        self.np_procs = np_procs
        w = _Writer(case)
        w.dict('system/controlDict', self._control(solids))
        # top-level schemes: only the meshing utilities read these (each region has its own)
        w.dict('system/fvSchemes', 'ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n'
                                   'divSchemes { default none; }\nlaplacianSchemes { default Gauss linear corrected; }\n'
                                   'interpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\n')
        w.dict('system/fvSolution', 'solvers {}\nSIMPLE {}\n')
        w.dict('system/blockMeshDict', self._block())
        w.dict('system/snappyHexMeshDict', self._snappy(solids))
        w.dict('system/meshQualityDict', '#includeEtc "caseDicts/meshQualityDict"\n')
        w.dict('system/decomposeParDict', f'numberOfSubdomains {np_procs};\nmethod scotch;\n')
        w.dict('constant/regionProperties', f'regions\n(\n    fluid ({self.fluid})\n    solid ({" ".join(b.name for b in solids)})\n);\n')
        w.dict('constant/g', f'dimensions [0 1 -2 0 0 0 0];\nvalue ({self.gravity[0]} {self.gravity[1]} {self.gravity[2]});\n', cls='uniformDimensionedVectorField')
        for r in regions:
            w.dict(f'system/{r}/decomposeParDict', f'numberOfSubdomains {np_procs};\nmethod scotch;\n')
        self._fluid_files(w)
        for b in solids:
            self._solid_files(w, b)
        if self.fans or self.porous:
            w.dict(f'system/{self.fluid}/topoSetDict', self._zone_sets())
        (case / 'Allrun').write_text(self._allrun(regions, bool(solids)))
        (case / 'Allrun').chmod(0o755)
        (case / 'case.foam').write_text('')
        (case / 'cadagent-case.json').write_text(json.dumps(self.describe(), indent=2) + '\n')
        return case

    def describe(self) -> dict:
        return {
            'name': self.name, 'solver': 'chtMultiRegionSimpleFoam (OpenFOAM v2512)', 'ambient_c': self.ambient_c,
            'domain_mm': [self.lo.tolist(), self.hi.tolist()], 'base_cell_mm': self.cell_mm, 'iterations': self.iterations,
            'ground': 'adiabatic no-slip floor (a table)' if self.ground else 'open',
            'solids': [{'name': b.name, 'material': b.material.name, 'k_w_mk': b.material.k, 'power_w': b.power_w,
                        'note': b.material.note, 'cell_mm': self.cell_mm / 2 ** b.level[1]} for b in self.bodies if b.kind == 'solid'],
            'walls': [{'name': b.name, 'cell_mm': self.cell_mm / 2 ** b.level[1]} for b in self.bodies if b.kind == 'wall'],
            'contacts': [{'between': list(k), 'thickness_mm': v[0] * 1000, 'k_w_mk': v[1]} for k, v in self.contacts.items()],
            'fans': [{'name': f.name, 'centre_mm': list(f.centre), 'axis': list(f.axis), 'd_outer_mm': f.d_outer, 'd_hub_mm': f.d_hub,
                      'dp0_pa': f.dp0_pa, 'q_free_m3h': f.q_free_m3h, 'q_free_cfm': round(f.q_free_m3h / 1.699, 1), 'note': f.note,
                      'model': 'actuator disc, linear fan curve'} for f in self.fans],
            'porous': [{'name': z['name'], 'lo_mm': z['lo'].tolist(), 'hi_mm': z['hi'].tolist(), 'd': list(z['d']), 'f': list(z['f']),
                        'e1': list(z['e1']), 'e2': list(z['e2']), 'heat_w': z['heat_w'], 'ha_w_k': z.get('ha_w_k'),
                        'fin_temperature_c': z.get('fin_temperature_c'), 'note': z['note']} for z in self.porous],
            'limits': ['steady RANS (k-omega SST): natural-convection plumes really fluctuate',
                       'no radiation: passive cases are pessimistic (radiation can carry a third of the heat from a hot plate in still air)',
                       'isotropic solids: heat pipes are an effective conductivity, with no dry-out limit',
                       'obstacles (enclosure, boards) are adiabatic: the heat leaves only with the air',
                       'fans are actuator discs with a straight-line fan curve, no swirl'],
        }

    def _control(self, solids):
        fos = []
        for b in solids:
            for op in ('max', 'volAverage'):
                fos.append(f'''    T_{op}_{b.name}
    {{
        type volFieldValue; libs (fieldFunctionObjects); region {b.name}; fields (T); operation {op};
        writeFields false; log false; writeControl timeStep; writeInterval 10;
    }}''')
        fos.append(f'''    T_max_{self.fluid}
    {{
        type volFieldValue; libs (fieldFunctionObjects); region {self.fluid}; fields (T); operation max;
        writeFields false; log false; writeControl timeStep; writeInterval 10;
    }}''')
        for f in [x.name for x in self.fans] + [z['name'] for z in self.porous]:
            fos.append(f'''    zone_{f}
    {{
        type volFieldValue; libs (fieldFunctionObjects); region {self.fluid}; fields (U T);
        regionType cellZone; name {f}; operation volAverage;
        writeFields false; log false; writeControl timeStep; writeInterval 10;
    }}''')
        fos.append(f'''    heat_out
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType patch; name ambient;
        fields (h); operation weightedSum; weightField phi; writeFields false; log false;
        writeControl timeStep; writeInterval 10;
    }}''')
        fos.append(f'''    residuals
    {{
        type solverInfo; libs (utilityFunctionObjects); region {self.fluid}; fields (U p_rgh h k omega);
        writeResidualFields false;
    }}
    wallHeatFlux_{self.fluid}
    {{
        type wallHeatFlux; libs (fieldFunctionObjects); region {self.fluid}; writeControl writeTime;
    }}''')
        return (f'application chtMultiRegionSimpleFoam;\nstartFrom latestTime;\nstartTime 0;\nstopAt endTime;\n'
                f'endTime {self.iterations};\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval {self.write_every};\n'
                f'purgeWrite 0;\nwriteFormat binary;\nwritePrecision 8;\nwriteCompression off;\ntimeFormat general;\n'
                f'timePrecision 8;\nrunTimeModifiable true;\n\nfunctions\n{{\n' + '\n'.join(fos) + '\n}\n')

    def _block(self):
        lo, hi = self.lo / 1000, self.hi / 1000
        n = np.maximum(1, np.round((self.hi - self.lo) / self.cell_mm)).astype(int)
        v = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
             (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
        verts = '\n'.join(f'    ({a:.6f} {b:.6f} {c:.6f})' for a, b, c in v)
        ground = 'ground { type wall; faces ((0 3 2 1)); }' if self.ground else ''
        amb = '(4 5 6 7) (0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2)' + ('' if self.ground else ' (0 3 2 1)')
        return (f'scale 1;\nvertices\n(\n{verts}\n);\nblocks\n(\n    hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1)\n);\n'
                f'edges ();\nboundary\n(\n    ambient {{ type patch; faces ({amb}); }}\n    {ground}\n);\n')

    def _snappy(self, solids):
        geo = '\n'.join(f'    {b.path} {{ type triSurfaceMesh; name {b.name}; }}' for b in self.bodies)
        for i, (lo, hi, _) in enumerate(self.boxes):
            geo += f'\n    box{i} {{ type searchableBox; min ({lo[0]/1000:.6f} {lo[1]/1000:.6f} {lo[2]/1000:.6f}); max ({hi[0]/1000:.6f} {hi[1]/1000:.6f} {hi[2]/1000:.6f}); }}'
        # solids: every cell inside the closed surface joins the region (the pieces need not touch, e.g. separate fins);
        # walls: no zone, so the cells inside them are cut away
        surf = '\n'.join(f'        {b.name} {{ level ({b.level[0]} {b.level[1]}); patchInfo {{ type wall; }}'
                         + (f' faceZone {b.name}; cellZone {b.name}; cellZoneInside inside;' if b.kind == 'solid' else '') + ' }'
                         for b in self.bodies)
        reg = '\n'.join(f'        box{i} {{ mode inside; levels ((1e15 {lv})); }}' for i, (_, _, lv) in enumerate(self.boxes))
        p = self._fluid_point()  # the air is everything reachable from here; splitMeshRegions names it domain0
        return f'''castellatedMesh true;
snap true;
addLayers false;
geometry
{{
{geo}
}}
castellatedMeshControls
{{
    maxLocalCells 100000000; maxGlobalCells 200000000; minRefinementCells 10; maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3; resolveFeatureAngle 30; allowFreeStandingZoneFaces true;
    features ();
    refinementSurfaces
    {{
{surf}
    }}
    refinementRegions
    {{
{reg}
    }}
    locationInMesh ({p[0]:.6f} {p[1]:.6f} {p[2]:.6f});
}}
snapControls
{{
    nSmoothPatch 3; tolerance 2.0; nSolveIter 50; nRelaxIter 5; nFeatureSnapIter 10;
    implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap true;
}}
addLayersControls {{ layers {{}} relativeSizes true; expansionRatio 1.2; finalLayerThickness 0.5; minThickness 0.1;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50; }}
meshQualityControls {{ #include "meshQualityDict" relaxed {{ maxNonOrtho 75; }} nSmoothScale 4; errorReduction 0.75; }}
mergeTolerance 1e-6;
'''

    def _zone_sets(self):
        acts = []
        for z in self.porous:
            lo, hi = z['lo'] / 1000, z['hi'] / 1000
            acts.append(f'''    {{ name {z['name']}Set; type cellSet; action new; source boxToCell;
      box ({lo[0]:.6f} {lo[1]:.6f} {lo[2]:.6f}) ({hi[0]:.6f} {hi[1]:.6f} {hi[2]:.6f}); }}
    {{ name {z['name']}; type cellZoneSet; action new; source setToCellZone; set {z['name']}Set; }}''')
        for f in self.fans:
            c = np.asarray(f.centre, float) / 1000
            a = np.asarray(f.axis, float)
            a = a / np.linalg.norm(a)
            h = f.thickness / 2000
            p1, p2 = c - a * h, c + a * h
            acts.append(f'''    {{ name {f.name}Set; type cellSet; action new; source cylinderAnnulusToCell;
      point1 ({p1[0]:.6f} {p1[1]:.6f} {p1[2]:.6f}); point2 ({p2[0]:.6f} {p2[1]:.6f} {p2[2]:.6f});
      outerRadius {f.d_outer/2000:.6f}; innerRadius {f.d_hub/2000:.6f}; }}
    {{ name {f.name}; type cellZoneSet; action new; source setToCellZone; set {f.name}Set; }}''')
        return 'actions\n(\n' + '\n'.join(acts) + '\n);\n'

    # --- per-region files
    def _fluid_files(self, w):
        r, Ta = self.fluid, self.ambient_c + T0
        walls = [b.name for b in self.bodies if b.kind == 'wall'] + (['ground'] if self.ground else [])
        wall_re = '"(' + '|'.join(walls) + ')"' if walls else None
        cpl = f'"{r}_to_.*"'

        def field(name, cls, dims, internal, amb, wall, coupled):
            bf = ['    #includeEtc "caseDicts/setConstraintTypes"', f'    ambient {{ {amb} }}']
            if wall_re:
                bf.append(f'    {wall_re} {{ {wall} }}')
            bf.append(f'    {cpl} {{ {coupled} }}')
            w.dict(f'0/{r}/{name}', f'dimensions {dims};\ninternalField uniform {internal};\nboundaryField\n{{\n' + '\n'.join(bf) + '\n}\n', cls=cls)

        k0, om0 = 1e-4, 1.0
        field('U', 'volVectorField', '[0 1 -1 0 0 0 0]', '(0 0 0)', 'type pressureInletOutletVelocity; value uniform (0 0 0);',
              'type noSlip;', 'type noSlip;')
        field('p_rgh', 'volScalarField', '[1 -1 -2 0 0 0 0]', 1e5, 'type prghTotalPressure; p0 uniform 1e5; value uniform 1e5;',
              'type fixedFluxPressure; value uniform 1e5;', 'type fixedFluxPressure; value uniform 1e5;')
        field('p', 'volScalarField', '[1 -1 -2 0 0 0 0]', 1e5, 'type calculated; value uniform 1e5;',
              'type calculated; value uniform 1e5;', 'type calculated; value uniform 1e5;')
        field('T', 'volScalarField', '[0 0 0 1 0 0 0]', Ta, f'type inletOutlet; inletValue uniform {Ta}; value uniform {Ta};',
              'type zeroGradient;',
              f'type compressible::turbulentTemperatureRadCoupledMixed; Tnbr T; kappaMethod fluidThermo; qrNbr none; qr none; value uniform {Ta};')
        field('k', 'volScalarField', '[0 2 -2 0 0 0 0]', k0, f'type inletOutlet; inletValue uniform {k0}; value uniform {k0};',
              f'type kqRWallFunction; value uniform {k0};', f'type kqRWallFunction; value uniform {k0};')
        field('omega', 'volScalarField', '[0 0 -1 0 0 0 0]', om0, f'type inletOutlet; inletValue uniform {om0}; value uniform {om0};',
              f'type omegaWallFunction; value uniform {om0};', f'type omegaWallFunction; value uniform {om0};')
        field('nut', 'volScalarField', '[0 2 -1 0 0 0 0]', 0, 'type calculated; value uniform 0;',
              'type nutkWallFunction; value uniform 0;', 'type nutkWallFunction; value uniform 0;')
        field('alphat', 'volScalarField', '[1 -1 -1 0 0 0 0]', 0, 'type calculated; value uniform 0;',
              'type compressible::alphatWallFunction; Prt 0.85; value uniform 0;', 'type compressible::alphatWallFunction; Prt 0.85; value uniform 0;')
        w.dict(f'constant/{r}/thermophysicalProperties', '''thermoType
{
    type heRhoThermo; mixture pureMixture; transport const; thermo hConst;
    equationOfState perfectGas; specie specie; energy sensibleEnthalpy;
}
mixture
{
    specie { molWeight 28.96; }
    thermodynamics { Cp 1005; Hf 0; }
    transport { mu 1.83e-05; Pr 0.71; }
}
''')
        w.dict(f'constant/{r}/turbulenceProperties', 'simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs off; }\n')
        w.dict(f'system/{r}/fvSchemes', '''ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,K) bounded Gauss upwind;
    div(phi,h) bounded Gauss upwind;
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited 0.5; }
wallDist { method meshWave; }
''')
        w.dict(f'system/{r}/fvSolution', '''solvers
{
    "rho.*" { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    p_rgh { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    "(U|h|k|omega)" { solver PBiCGStab; preconditioner DILU; tolerance 1e-7; relTol 0.1; }
}
SIMPLE
{
    momentumPredictor true; nNonOrthogonalCorrectors 1; pRefCell 0; pRefValue 1e5;
    residualControl { default 1e-5; }
}
relaxationFactors
{
    fields { p_rgh 0.7; rho 1; }
    equations { U 0.3; h 0.7; k 0.5; omega 0.5; }
}
''')
        src = []
        for z in self.porous:
            src.append(f'''{z['name']}Resistance
{{
    type explicitPorositySource; active true; selectionMode cellZone; cellZone {z['name']};
    explicitPorositySourceCoeffs
    {{
        selectionMode cellZone; cellZone {z['name']};
        type DarcyForchheimer;
        d ({z['d'][0]:.6g} {z['d'][1]:.6g} {z['d'][2]:.6g});
        f ({z['f'][0]:.6g} {z['f'][1]:.6g} {z['f'][2]:.6g});
        coordinateSystem {{ origin (0 0 0); e1 ({z['e1'][0]} {z['e1'][1]} {z['e1'][2]}); e2 ({z['e2'][0]} {z['e2'][1]} {z['e2'][2]}); }}
    }}
}}''')
            if z.get('ha_w_k'):
                src.append(self._exchanger(z))
            elif z['heat_w']:
                src.append(f'''{z['name']}Heat
{{
    type scalarSemiImplicitSource; active true; selectionMode cellZone; cellZone {z['name']}; volumeMode absolute;
    sources {{ h {{ explicit {z['heat_w']}; implicit 0; }} }}
}}''')
        if self.fans or self.porous:
            for f in self.fans:
                F, c = f.source()
                src.append(f'''{f.name}
{{
    type vectorSemiImplicitSource; active true; selectionMode cellZone; cellZone {f.name}; volumeMode specific;
    sources {{ U {{ explicit ({F[0]:.4f} {F[1]:.4f} {F[2]:.4f}); implicit {-c:.4f}; }} }}
}}''')
            w.dict(f'system/{r}/fvOptions', '\n'.join(src) + '\n')

    @staticmethod
    def _exchanger(z) -> str:
        # S = hA/V (T_fin - T) on sensible enthalpy hs = cp (T - 298.15): explicit hA/V (T_fin - 298.15), implicit -hA/V / cp
        vol = float(np.prod((z['hi'] - z['lo']) / 1000))
        hav = z['ha_w_k'] / vol
        return f'''{z['name']}Heat
{{
    type scalarSemiImplicitSource; active true; selectionMode cellZone; cellZone {z['name']}; volumeMode specific;
    sources {{ h {{ explicit {hav * (z['fin_temperature_c'] + T0 - 298.15):.6g}; implicit {-hav / AIR_CP:.6g}; }} }}
}}'''

    def _solid_files(self, w, b):
        m, r, Ta = b.material, b.name, self.ambient_c + T0
        # walls the solid touches (e.g. a board) are adiabatic; interfaces to other regions are coupled. Regex entries
        # match last-first, so the catch-all comes first.
        bf = ['    #includeEtc "caseDicts/setConstraintTypes"', '    ".*" { type zeroGradient; }']
        for (a, c), (t, k) in self.contacts.items():
            if r in (a, c):
                other = c if r == a else a
                bf.append(f'    {r}_to_{other} {{ type compressible::turbulentTemperatureRadCoupledMixed; Tnbr T; kappaMethod solidThermo; '
                          f'qrNbr none; qr none; thicknessLayers ({t}); kappaLayers ({k}); value uniform {Ta}; }}')
        bf.append(f'    "{r}_to_.*" {{ type compressible::turbulentTemperatureRadCoupledMixed; Tnbr T; kappaMethod solidThermo; '
                  f'qrNbr none; qr none; value uniform {Ta}; }}')
        w.dict(f'0/{r}/T', 'dimensions [0 0 0 1 0 0 0];\ninternalField uniform ' + f'{Ta};\nboundaryField\n{{\n' + '\n'.join(bf) + '\n}\n', cls='volScalarField')
        w.dict(f'0/{r}/p', 'dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 1e5;\nboundaryField\n{\n    #includeEtc "caseDicts/setConstraintTypes"\n    ".*" { type calculated; value uniform 1e5; }\n}\n', cls='volScalarField')
        w.dict(f'constant/{r}/thermophysicalProperties', f'''thermoType
{{
    type heSolidThermo; mixture pureMixture; transport constIso; thermo hConst;
    equationOfState rhoConst; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight 50; }}
    transport {{ kappa {m.k}; }}
    thermodynamics {{ Hf 0; Cp {m.cp}; }}
    equationOfState {{ rho {m.rho}; }}
}}
''')
        w.dict(f'system/{r}/fvSchemes', '''ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear limited 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited 0.5; }
''')
        w.dict(f'system/{r}/fvSolution', '''solvers { h { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.01; } }
SIMPLE { nNonOrthogonalCorrectors 1; }
relaxationFactors { equations { h 1; } }
''')
        if b.power_w:
            w.dict(f'system/{r}/fvOptions', f'''heat
{{
    type scalarSemiImplicitSource; active true; selectionMode all; volumeMode absolute;
    sources {{ h {{ explicit {b.power_w}; implicit 0; }} }}
}}
''')

    def _allrun(self, regions, has_solids=True):
        n = self.np_procs
        par = f'mpirun -np {n} --oversubscribe'
        fan = f'{par} topoSet -region {self.fluid} -parallel > log.topoSet 2>&1\n' if (self.fans or self.porous) else ''
        split = (f'{par} splitMeshRegions -cellZones -overwrite -parallel > log.splitMeshRegions 2>&1' if has_solids else
                 f'# air only: the mesh is the {self.fluid} region\n'
                 f'for p in processor*; do mkdir -p "$p/constant/{self.fluid}" && mv "$p/constant/polyMesh" "$p/constant/{self.fluid}/"; done')
        return f'''#!/bin/bash
# Written by cadagent.cfd. Runs inside the OpenFOAM environment (Docker image {IMAGE} or a native install).
set -e
cd "${{0%/*}}"
blockMesh > log.blockMesh 2>&1
decomposePar -force > log.decomposePar 2>&1
{par} snappyHexMesh -parallel -overwrite > log.snappyHexMesh 2>&1
{par} checkMesh -parallel -constant > log.checkMesh 2>&1 || true
# initial fields per region into each processor, then split the cell zones into regions
for p in processor*; do cp -r 0 "$p/"; done
{split}
{fan}{par} chtMultiRegionSimpleFoam -parallel > log.solve 2>&1
reconstructParMesh -allRegions -constant > log.reconstructParMesh 2>&1
reconstructPar -allRegions -latestTime > log.reconstructPar 2>&1
foamToVTK -allRegions -latestTime -noFunctionObjects > log.foamToVTK 2>&1
'''

    # --- run and read back
    def run(self, case_dir, image: str = IMAGE, native: Optional[bool] = None, timeout: Optional[float] = None):
        """Run the Allrun script, natively when OpenFOAM is on PATH, else in Docker. Returns the process exit code."""
        case = Path(case_dir).resolve()
        if native is None:
            native = shutil.which('chtMultiRegionSimpleFoam') is not None
        if native:
            cmd = ['bash', str(case / 'Allrun')]
        else:
            if not shutil.which('docker'):
                raise RuntimeError('OpenFOAM is not installed and docker is not available: install either to run a CFD case')
            cmd = ['docker', 'run', '--rm', '--shm-size=8g', '-u', f'{os.getuid()}:{os.getgid()}', '-v', f'{case}:/case', '-w', '/case',
                   image, 'bash', '-lc', 'cd /case && ./Allrun']
        return subprocess.run(cmd, timeout=timeout).returncode

    def results(self, case_dir) -> dict:
        return read_results(case_dir, self)

    def calibrate_fins(self, case_dir, target_w: float, extra_iterations: int = 300, tolerance: float = 0.03,
                       rounds: int = 4, image: str = IMAGE, native: Optional[bool] = None) -> dict:
        """Set each exchanger block's fin temperature so the heat leaving with the air matches ``target_w``, continuing
        the solve from where it stopped. Linear in T_fin - T_in, so it converges in one or two rounds."""
        case = Path(case_dir).resolve()
        hist = []
        for k in range(rounds):
            res = read_results(case, self)
            q = res.get('heat_out_w')
            zones = [z for z in self.porous if z.get('ha_w_k')]
            if q is None or not zones:
                break
            drift = res.get('convergence', {}).get('heat_out_change_pct')
            settled = drift is not None and abs(drift) <= 5
            hist.append({'round': k, 'heat_out_w': q, 'fin_temperature_c': [z['fin_temperature_c'] for z in zones],
                         'heat_out_change_pct': drift})
            if settled and abs(q - target_w) <= tolerance * target_w:
                break
            if settled:   # only correct the fins once the heat leaving has stopped moving; otherwise just keep solving
                t_in = self.ambient_c
                factor = min(3.0, max(1 / 3, target_w / max(q, 1e-6)))   # never jump further than x3 in one round
                for z in zones:
                    z['fin_temperature_c'] = t_in + (z['fin_temperature_c'] - t_in) * factor
            self._continue(case, extra_iterations)
            native_ = shutil.which('chtMultiRegionSimpleFoam') is not None if native is None else native
            cmd = ['bash', str(case / 'Allrun.continue')] if native_ else [
                'docker', 'run', '--rm', '--shm-size=8g', '-u', f'{os.getuid()}:{os.getgid()}', '-v', f'{case}:/case', image,
                'bash', '-lc', 'cd /case && ./Allrun.continue']
            subprocess.run(cmd)
        res = read_results(case, self)
        res['fin_calibration'] = hist + [{'round': len(hist), 'heat_out_w': res.get('heat_out_w'),
                                          'fin_temperature_c': [z['fin_temperature_c'] for z in self.porous if z.get('ha_w_k')]}]
        return res

    def _continue(self, case: Path, extra: int):
        cd = case / 'system' / 'controlDict'
        txt = cd.read_text()
        end = int(re.search(r'^endTime (\d+);', txt, re.M).group(1)) + extra
        txt = re.sub(r'^endTime \d+;', f'endTime {end};', txt, flags=re.M)
        # write at intervals that land on both the restart time and the new end; keep only the last two writes
        step = math.gcd(end - extra, extra) or extra
        txt = re.sub(r'^writeInterval \d+;', f'writeInterval {step};', txt, flags=re.M)
        txt = re.sub(r'^purgeWrite \d+;', 'purgeWrite 2;', txt, flags=re.M)
        cd.write_text(txt)
        self.iterations = end
        w = _Writer(case)
        self._fluid_files(w)                      # rewrites fvOptions with the new fin temperatures
        meta = json.loads((case / 'cadagent-case.json').read_text())
        meta.update(self.describe())
        (case / 'cadagent-case.json').write_text(json.dumps(meta, indent=2) + '\n')
        n = self.np_procs
        (case / 'Allrun.continue').write_text(f'''#!/bin/bash
set -e
cd "${{0%/*}}"
mpirun -np {n} --oversubscribe chtMultiRegionSimpleFoam -parallel > log.solve.continue 2>&1
reconstructPar -allRegions -latestTime > log.reconstructPar 2>&1
rm -rf VTK
foamToVTK -allRegions -latestTime -noFunctionObjects > log.foamToVTK 2>&1
''')
        (case / 'Allrun.continue').chmod(0o755)


class _Writer:
    def __init__(self, case: Path):
        self.case = case

    def dict(self, rel, body, cls='dictionary'):
        p = self.case / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        obj = p.name
        head = ('FoamFile\n{\n    version 2.0;\n    format ascii;\n'
                f'    class {cls};\n    object {obj};\n}}\n// written by cadagent.cfd\n\n')
        p.write_text(head + body)


def _last_row(path: Path):
    rows = [l.split() for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')]
    return rows[-1] if rows else None


def _series(path: Path):
    rows = [l.split() for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')]
    return [[float(x.strip('()')) for x in r] for r in rows]


def read_results(case_dir, case: Optional[ThermalCase] = None) -> dict:
    """Temperatures (°C), fan flows and residual history from a finished case's postProcessing output."""
    cd = Path(case_dir)
    meta = json.loads((cd / 'cadagent-case.json').read_text())
    pp = cd / 'postProcessing'
    out = {'case': meta['name'], 'ambient_c': meta['ambient_c'], 'solids': {}, 'fans': {}, 'limits': meta['limits']}

    def fo(name, kind='volFieldValue'):
        hits = sorted(pp.glob(f'**/{name}/*/{kind}.dat'), key=lambda p: float(p.parent.name))
        hits = [h for h in hits if _last_row(h)]          # a restart that crashed leaves an empty file
        return hits[-1] if hits else None

    for s in meta['solids']:
        row = {}
        for op, key in (('max', 'max_c'), ('volAverage', 'mean_c')):
            f = fo(f'T_{op}_{s["name"]}')
            if f:
                r = _last_row(f)
                row[key] = round(float(r[1]) - T0, 2)
        row.update(power_w=s['power_w'], material=s['material'])
        out['solids'][s['name']] = row
    f = fo(f'T_max_{case.fluid if case else "domain0"}')
    if f:
        out['air_max_c'] = round(float(_last_row(f)[1]) - T0, 2)
    zones = {}
    for zn in [f['name'] for f in meta['fans']] + [z['name'] for z in meta.get('porous', [])]:
        f = fo(f'zone_{zn}')
        if f:
            r = [float(x.strip('()')) for x in _last_row(f)]
            zones[zn] = {'U_m_s': r[1:4], 'T_c': round(r[4] - T0, 2)}
    out['zones'] = zones
    for fan in meta['fans']:
        z = zones.get(fan['name'])
        if z:
            u = np.array(z['U_m_s'])
            a = np.asarray(fan['axis'], float)
            a /= np.linalg.norm(a)
            area = math.pi / 4 * ((fan['d_outer_mm'] / 1000) ** 2 - (fan['d_hub_mm'] / 1000) ** 2)
            q = float(u @ a) * area * 3600
            dp = fan['dp0_pa'] * (1 - q / fan['q_free_m3h'])
            out['fans'][fan['name']] = {'flow_m3h': round(q, 2), 'flow_cfm': round(q / 1.699, 2), 'pressure_rise_pa': round(dp, 2),
                                        'fraction_of_free_air': round(q / fan['q_free_m3h'], 3), 'air_through_fan_c': z['T_c']}
    f = fo('heat_out', 'surfaceFieldValue')
    if f:
        out['heat_out_w'] = round(float(_last_row(f)[1]), 2)
    res = sorted(pp.glob('**/residuals/*/solverInfo.dat'), key=lambda p: float(p.parent.name))
    if res:
        lines = res[-1].read_text().splitlines()
        hdr = next((l for l in lines if l.startswith('#') and 'Time' in l), None)
        if hdr:
            cols = hdr.lstrip('#').split('\t') if '\t' in hdr else hdr.lstrip('#').split()
            cols = [c.strip() for c in cols]
            data = [l.split('\t') if '\t' in l else l.split() for l in lines if l.strip() and not l.startswith('#')]
            keep = [i for i, c in enumerate(cols) if c.endswith('_initial')]
            hist = {cols[i].replace('_initial', ''): [float(d[i]) if i < len(d) and d[i] not in ('N/A', '') else None for d in data] for i in keep}
            out['residuals'] = {'iteration': [float(d[0]) for d in data], **hist}
            out['iterations'] = int(float(data[-1][0])) if data else 0
    logs = cd / 'log.solve'
    if logs.exists():
        txt = logs.read_text(errors='replace')
        out['solver_finished'] = 'End' in txt.splitlines()[-5:] if txt else False
        m = re.findall(r'ExecutionTime = ([\d.]+) s', txt)
        if m:
            out['wall_time_s'] = float(m[-1])
    hist = {}
    for s in meta['solids']:
        f = fo(f'T_max_{s["name"]}')
        if f:
            hist[s['name']] = [[r[0], r[1] - T0] for r in _series(f)]
    out['T_max_history'] = hist
    # how much the answer still moved over the last fifth of the iterations
    conv = {}
    for k, v in hist.items():
        a = np.array(v)
        if len(a) > 5:
            tail = a[a[:, 0] >= a[-1, 0] * 0.8]
            conv[f'{k}_max_c_change'] = round(float(tail[-1, 1] - tail[0, 1]), 2)
    for fan in meta['fans']:
        f = fo(f'zone_{fan["name"]}')
        if f:
            a = np.array(_series(f))
            if len(a) > 5:
                tail = a[a[:, 0] >= a[-1, 0] * 0.8]
                ax = np.asarray(fan['axis'], float) / np.linalg.norm(fan['axis'])
                u0, u1 = float(tail[0, 1:4] @ ax), float(tail[-1, 1:4] @ ax)
                conv[f'{fan["name"]}_flow_change_pct'] = round(100 * (u1 - u0) / u1, 1) if u1 else None
                conv[f'{fan["name"]}_intake_c_change'] = round(float(tail[-1, 4] - tail[0, 4]), 2)
    f = fo('heat_out', 'surfaceFieldValue')
    if f:
        a = np.array(_series(f))
        if len(a) > 5:
            tail = a[a[:, 0] >= a[-1, 0] * 0.8]
            conv['heat_out_change_pct'] = round(100 * (tail[-1, 1] - tail[0, 1]) / tail[-1, 1], 1) if tail[-1, 1] else None
    out['convergence'] = conv
    out['converged'] = bool(conv) and all(abs(v) < (1.0 if k.endswith('_c_change') else 2.0) for k, v in conv.items() if v is not None)
    return out
