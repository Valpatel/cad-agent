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
import warnings
from collections import Counter
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
        """Total force (N) along the axis at zero flow, and the total implicit drag (kg/s) that brings the pressure rise
        to zero at the free-air velocity. Totals (OpenFOAM ``volumeMode absolute``) make the pressure rise independent
        of how many cell layers the disc zone catches: dp = F / A whatever its thickness."""
        a = np.asarray(self.axis, float)
        a = a / np.linalg.norm(a)
        v_free = self.q_free_m3h / 3600 / self.area_m2
        return a * self.dp0_pa * self.area_m2, self.dp0_pa * self.area_m2 / v_free


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
        """A conducting solid region; ``power_w`` spreads that heat evenly through its volume. It must be one connected
        piece: separate pieces would split into regions the case does not define (model each as its own solid)."""
        self._add(name, shape, 'solid', level, material, power_w)
        pieces = len(self._meshes[name].split(only_watertight=False))
        if pieces > 1:
            warnings.warn(f'solid {name!r} is {pieces} separate pieces; the run will stop after splitMeshRegions. '
                          'Model each piece as its own solid (with contact() between touching ones).', stacklevel=2)
        return self

    def contact(self, a: str, b: str, thickness_mm: float, k: float):
        """A thin layer (thermal pad, paste, air gap) between two touching solids, as a resistance on their interface."""
        self.contacts[(a, b)] = (thickness_mm / 1000, k)
        return self

    def fan(self, fan: Fan):
        self.fans.append(fan)
        return self

    def porous_box(self, name, lo, hi, d, f, e1=(1, 0, 0), e2=(0, 1, 0), heat_w: float = 0.0, ha_w_k: Optional[float] = None,
                   fin_temperature_c: Optional[float] = None, target_w: Optional[float] = None, note: str = ''):
        """A block of air with a Darcy-Forchheimer resistance (d 1/m2, f 1/m per local axis e1, e2, e3 = e1 x e2): a
        compact model of a fin block or a filter (lo, hi in mm). Heat, either way:

        - ``ha_w_k`` and ``fin_temperature_c``: isothermal fins with conductance hA (W/K, h x area x fin efficiency)
          heat each cell's air by hA/V (T_fin - T_air). Air cannot get hotter than the fins, and the heat goes where the
          air flows. ``calibrate_fins()`` then sets T_fin so the block delivers ``target_w``. Prefer this.
        - ``heat_w``: that power released evenly through the block's volume. Simple, but air that stagnates in a corner
          of the block heats without limit."""
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', name):
            raise ValueError(f'{name!r}: zone names must be letters and digits only')
        if (ha_w_k is None) != (fin_temperature_c is None):
            raise ValueError('give both ha_w_k and fin_temperature_c, or neither')
        if fin_temperature_c is not None and fin_temperature_c <= self.ambient_c:
            raise ValueError(f'{name}: the first fin temperature must be above the room ({self.ambient_c} C)')
        self.porous.append({'name': name, 'lo': np.asarray(lo, float), 'hi': np.asarray(hi, float), 'd': tuple(d), 'f': tuple(f),
                            'e1': tuple(e1), 'e2': tuple(e2), 'heat_w': heat_w, 'ha_w_k': ha_w_k,
                            'fin_temperature_c': fin_temperature_c, 'target_w': target_w if target_w is not None else (heat_w or None),
                            'note': note})
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
        names = {b.name for b in self.bodies if b.kind == 'solid'}
        for a, b in self.contacts:
            if a not in names or b not in names:
                raise ValueError(f'contact({a!r}, {b!r}): both must be solid regions; solids are {sorted(names)}')
        if case.exists():
            # only ever remove a folder this module wrote (or an empty one): never a project folder by mistake
            if not (case / 'cadagent-case.json').exists() and any(case.iterdir()):
                raise FileExistsError(f'{case} exists and is not a cadagent.cfd case; choose an empty or new folder')
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
        if solids:
            w.dict('system/topoSetDict.fluidZone', self._fluid_zone(solids))
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
                        'fin_temperature_c': z.get('fin_temperature_c'), 'target_w': z.get('target_w'), 'note': z['note']} for z in self.porous],
            'heat_input_w': self.heat_input_w(),
            'limits': ['steady RANS (k-omega SST): natural-convection plumes really fluctuate',
                       'no radiation: passive cases are pessimistic (radiation can carry a third of the heat from a hot plate in still air)',
                       'walls use wall functions without prism layers, so wall heat transfer depends on the mesh: check a case one level '
                       'finer before trusting a small difference',
                       'converged means the temperatures, fan flow and heat leaving stopped changing and the heat leaving matches the '
                       'heat put in (energy balance), not that the residuals reached a tolerance',
                       'isotropic solids: heat pipes are an effective conductivity, with no dry-out limit',
                       'obstacles (enclosure, boards) are adiabatic: the heat leaves only with the air',
                       'fans are actuator discs with a straight-line fan curve, no swirl'],
        }

    def heat_input_w(self) -> Optional[float]:
        """Heat put into the domain: solid sources, evenly heated blocks and the target power of exchanger blocks.
        None when an exchanger block has no target (its heat is whatever its fixed fin temperature gives)."""
        if any(z.get('ha_w_k') and z.get('target_w') is None for z in self.porous):
            return None
        return float(sum(b.power_w for b in self.bodies if b.kind == 'solid') +
                     sum((z.get('target_w') or 0.0) if z.get('ha_w_k') else z['heat_w'] for z in self.porous))

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
        # heat leaving with the air, referenced to the room: cp (sum(phi T) - T_amb sum(phi)); robust to a small mass
        # imbalance and to any enthalpy reference
        fos.append(f'''    flux_T
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType patch; name ambient;
        fields (T); operation weightedSum; weightField phi; writeFields false; log false;
        writeControl timeStep; writeInterval 10;
    }}
    flux_mass
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType patch; name ambient;
        fields (phi); operation sum; writeFields false; log false;
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
        # solids: every cell inside the closed surface joins the region; it must be one connected piece (separate pieces
        # split into regions of their own, which Allrun stops on: model each piece as its own solid);
        # walls: no zone, so the cells inside them are cut away
        surf = '\n'.join(f'        {b.name} {{ level ({b.level[0]} {b.level[1]}); patchInfo {{ type wall; }}'
                         + (f' faceZone {b.name}; cellZone {b.name}; cellZoneInside inside;' if b.kind == 'solid' else '') + ' }'
                         for b in self.bodies)
        reg = '\n'.join(f'        box{i} {{ mode inside; levels ((1e15 {lv})); }}' for i, (_, _, lv) in enumerate(self.boxes))
        # the air is everything reachable from here. Before the split, topoSet puts it in a cellZone named after
        # the fluid region (see _fluid_zone), so splitMeshRegions -cellZones names the region after it and not
        # domainN by split order: identical J501 cases came out as domain0 in one run and domain1 in another.
        p = self._fluid_point()
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

    def _fluid_zone(self, solids):
        """topoSet on the meshed (not yet split) case: every cell outside the solid zones joins a cellZone named after
        the fluid region. A named location in snappyHexMesh (locationsInMesh) would do the same, but it also gives
        cells in a solid's inside corners to the air, sealed pockets that then split off as regions of their own."""
        names = ' '.join(b.name for b in solids)
        return f'''actions
(
    {{ name cadagentSolidCells; type cellSet; action new; source zoneToCell; zones ({names}); }}
    {{ name cadagentSolidCells; type cellSet; action invert; }}
    {{ name {self.fluid}; type cellZoneSet; action new; source setToCellZone; set cadagentSolidCells; }}
);
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
        # p_rgh uniform on the open boundary makes the static pressure hydrostatic there (still room air stays still);
        # a uniform static pressure (prghTotalPressure) would drive a draft through the room
        field('p_rgh', 'volScalarField', '[1 -1 -2 0 0 0 0]', 1e5, 'type totalPressure; p0 uniform 1e5; value uniform 1e5;',
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
              'type compressible::alphatJayatillekeWallFunction; Prt 0.85; value uniform 0;',
              'type compressible::alphatJayatillekeWallFunction; Prt 0.85; value uniform 0;')
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
        u_relax, h_relax = getattr(self, '_relax', (0.3, 0.7))
        w.dict(f'system/{r}/fvSolution', ('''solvers
{
    "rho.*" { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    p_rgh { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    // relaxing energy less (0.8-0.95) or solving it tighter diverged in the first iterations of the J501 case; a
    // restart, once the flow has formed, relaxes faster (see _continue)
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
    equations { U __U__; h __H__; k 0.5; omega 0.5; }
}
''').replace('__U__', str(u_relax)).replace('__H__', str(h_relax)))
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
    type vectorSemiImplicitSource; active true; selectionMode cellZone; cellZone {f.name}; volumeMode absolute;
    sources {{ U {{ explicit ({F[0]:.4f} {F[1]:.4f} {F[2]:.4f}); implicit {-c:.4f}; }} }}
}}''')
            w.dict(f'system/{r}/fvOptions', '\n'.join(src) + '\n')

    @staticmethod
    def _exchanger(z) -> str:
        # S = hA (T_fin - T) on sensible enthalpy hs = cp (T - 298.15), as zone totals (volumeMode absolute: OpenFOAM spreads
        # them over the zone's real volume, so the conductance is hA whatever cells the box catches):
        # explicit hA (T_fin - 298.15) W, implicit -hA / cp kg/s
        ex, im = exchanger_terms(z['ha_w_k'], z['fin_temperature_c'])
        return f'''{z['name']}Heat
{{
    type scalarSemiImplicitSource; active true; selectionMode cellZone; cellZone {z['name']}; volumeMode absolute;
    sources {{ h {{ explicit {ex:.6g}; implicit {im:.6g}; }} }}
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
        expected = ' '.join(regions)
        split = (f'{par} topoSet -dict system/topoSetDict.fluidZone -parallel > log.topoSet.fluidZone 2>&1\n'
                 f'{par} splitMeshRegions -cellZones -overwrite -parallel > log.splitMeshRegions 2>&1\n'
                 '# every region must be one the case defines: an extra one is air (or solid) cut off from the rest\n'
                 f'extra=$(cd processor0/constant && for d in */; do d=${{d%/}}; case " {expected} polyMesh " in *" $d "*) ;; '
                 f'*) [ -d "$d/polyMesh" ] && echo "$d";; esac; done; true)\n'
                 'if [ -n "$extra" ]; then echo "splitMeshRegions made regions this case does not define: $(echo $extra) '
                 '(a pocket of air sealed off from the rest, or a solid in pieces); see log.splitMeshRegions" | tee log.solve >&2; exit 3; fi'
                 if has_solids else
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

    def calibrate_fins(self, case_dir, target_w: Optional[float] = None, extra_iterations: int = 400, tolerance: float = 0.03,
                       rounds: int = 8, image: str = IMAGE, native: Optional[bool] = None) -> dict:
        """Set the exchanger blocks' fin temperature so they deliver their power, continuing the solve from where it
        stopped. A block's heat is exactly hA (T_fin - mean air temperature in the block), which settles long before
        the heat leaving an open room does. Each correction is a secant step on T_fin, taken once the block and fan-intake
        temperatures have stopped moving (0.5 K over the last fifth), and moves at most 20 K; otherwise the round just
        keeps solving. Faster relaxation on restarts (velocity 0.5, energy 0.85) diverged on the J501 case after a fin
        temperature step, so restarts keep the start-up values. ``calibrated`` says whether it got there;
        ``energy_balance_pct`` says whether the whole room has caught up."""
        case = Path(case_dir).resolve()
        zones = [z for z in self.porous if z.get('ha_w_k')]
        if not zones:
            raise ValueError('no exchanger blocks (porous_box with ha_w_k) to calibrate')
        if target_w is not None:
            for z in zones:
                z['target_w'] = target_w / len(zones)
        if any(z.get('target_w') is None for z in zones):
            raise ValueError('calibrate_fins needs a target power: pass target_w, or porous_box(..., target_w=)')
        want = sum(z['target_w'] for z in zones)
        others = self.heat_input_w() - want
        hist, prev, calibrated = [], None, False
        for k in range(rounds + 1):
            res = read_results(case, self)
            # the block's own heat is exact and local: sum of hA (T_fin - volume-mean air temperature in the block)
            zt = [res.get('zones', {}).get(z['name'], {}).get('T_c') for z in zones]
            if any(v is None for v in zt):
                hist.append({'round': k, 'error': 'no fin-zone temperature output'})
                break
            q = sum(z['ha_w_k'] * (z['fin_temperature_c'] - v) for z, v in zip(zones, zt))
            conv = res.get('convergence', {})
            moving = [abs(v) for kk, v in conv.items() if v is not None and (kk.endswith('_T_change_c') or kk.endswith('_intake_c_change'))]
            settled = bool(moving) and max(moving) <= 0.5
            t_fin = zones[0]['fin_temperature_c']
            hist.append({'round': k, 'block_heat_w': round(q, 2), 'heat_out_w': res.get('heat_out_w'), 'fin_temperature_c': t_fin,
                         'block_and_intake_change_c': max(moving) if moving else None, 'energy_balance_pct': res.get('energy_balance_pct'),
                         'solver_finished': res.get('solver_finished')})
            if not res.get('solver_finished'):
                break
            if settled and abs(q - want) <= tolerance * want:
                calibrated = True
                break
            if k == rounds:
                break
            if settled:
                if prev and abs(t_fin - prev[0]) > 1e-6 and abs(q - prev[1]) > 1e-6:
                    slope = (q - prev[1]) / (t_fin - prev[0])          # W per K, from the last two settled rounds
                else:
                    slope = max(q, 1e-3) / max(t_fin - self.ambient_c, 1.0)
                slope = max(slope, 1e-3)
                new = min(max(t_fin + (want - q) / slope, self.ambient_c + 1.0, t_fin - 20.0), t_fin + 20.0)   # <= 20 K a round
                prev = (t_fin, q)
                for z in zones:
                    z['fin_temperature_c'] = round(new, 3)
            rc = self._extend(case, extra_iterations, image=image, native=native)
            if rc != 0:
                hist.append({'round': k, 'error': f'continuation exited {rc}'})
                break
        res = read_results(case, self)
        res['fin_calibration'] = hist
        res['calibrated'] = calibrated
        zt = [res.get('zones', {}).get(z['name'], {}).get('T_c') for z in zones]
        if all(v is not None for v in zt):
            res['block_heat_w'] = round(sum(z['ha_w_k'] * (z['fin_temperature_c'] - v) for z, v in zip(zones, zt)), 2)
        return res

    def extend(self, case_dir, iterations: int, image: str = IMAGE, native: Optional[bool] = None) -> int:
        """Continue a finished case for ``iterations`` more, from its last written time (the Allrun.continue script),
        and rewrite its VTK. Works on a ThermalCase rebuilt with the same settings in a new process: what an earlier
        run settled (each exchanger block's calibrated fin temperature and target power) is read back from the case's
        cadagent-case.json first, so continuing never undoes a calibration. Returns the exit code."""
        case = Path(case_dir).resolve()
        meta = json.loads((case / 'cadagent-case.json').read_text())
        saved = {z['name']: z for z in meta.get('porous', [])}
        for z in self.porous:
            if z['name'] in saved:
                for k in ('fin_temperature_c', 'target_w'):
                    if saved[z['name']].get(k) is not None:
                        z[k] = saved[z['name']][k]
        return self._extend(case, iterations, image=image, native=native)

    def _extend(self, case: Path, iterations: int, image: str = IMAGE, native: Optional[bool] = None) -> int:
        m = re.search(r'numberOfSubdomains\s+(\d+);', (case / 'system' / 'decomposeParDict').read_text())
        self.np_procs = int(m.group(1)) if m else 1           # always this case's own decomposition
        self._continue(case, int(iterations))
        native = shutil.which('chtMultiRegionSimpleFoam') is not None if native is None else native
        cmd = ['bash', str(case / 'Allrun.continue')] if native else [
            'docker', 'run', '--rm', '--shm-size=8g', '-u', f'{os.getuid()}:{os.getgid()}', '-v', f'{case}:/case', image,
            'bash', '-lc', 'cd /case && ./Allrun.continue']
        return subprocess.run(cmd).returncode

    def run_until_balanced(self, case_dir, chunk: int = 1000, max_iterations: int = 10000, tolerance_pct: float = 5.0,
                           image: str = IMAGE, native: Optional[bool] = None) -> dict:
        """Keep continuing a case in steps of ``chunk`` iterations until it has converged: the heat leaving the room
        within ``tolerance_pct`` of the heat put in (``energy_balance_pct``) and the residuals and temperatures
        settled (``steady`` from read_results), or until ``max_iterations`` in total. A conjugate case with a hot
        solid in a large room can need many thousands: the solid heats up long after the flow has settled. A case
        with no energy balance to close (no heat input) is left as it is. Returns the final results with
        ``continuation`` (the balance after each step), ``balanced`` and a ``stopped`` reason."""
        case = Path(case_dir).resolve()
        hist = []
        while True:
            res = read_results(case, self)
            end = int(re.search(r'^endTime (\d+);', (case / 'system' / 'controlDict').read_text(), re.M).group(1))
            bal = res.get('energy_balance_pct')
            hist.append({'iterations': end, 'energy_balance_pct': bal, 'heat_out_w': res.get('heat_out_w'),
                         'converged': res.get('converged'),
                         'solids_max_c': {k: v.get('max_c') for k, v in res.get('solids', {}).items()}})
            if bal is None:
                stopped = 'no energy balance to close (no heat input, or no heat-out output)'
                break
            if abs(bal) <= tolerance_pct and res.get('steady') and not res.get('error'):
                stopped = 'converged'
                break
            if not res.get('solver_finished'):
                stopped = 'the solver did not finish'
                break
            if end + chunk > max_iterations:
                stopped = f'reached the {max_iterations}-iteration cap'
                break
            rc = self.extend(case, chunk, image=image, native=native)
            if rc != 0:
                res = read_results(case, self)          # the crashed chunk's own log, not the last good one
                hist.append({'iterations': end + chunk, 'error': f'continuation exited {rc}'})
                stopped = f'continuation exited {rc}'
                break
        res['continuation'] = hist
        res['stopped'] = stopped
        res['balanced'] = stopped == 'converged'
        return res

    def _continue(self, case: Path, extra: int):
        cd = case / 'system' / 'controlDict'
        txt = cd.read_text()
        end = int(re.search(r'^endTime (\d+);', txt, re.M).group(1)) + extra
        txt = re.sub(r'^endTime \d+;', f'endTime {end};', txt, flags=re.M)
        # write only the new end (interval = end); earlier times stay as restart points, purgeWrite keeps two
        txt = re.sub(r'^writeInterval \d+;', f'writeInterval {end};', txt, flags=re.M)
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
mpirun -np {n} --oversubscribe chtMultiRegionSimpleFoam -parallel > log.solve.$(date +%s) 2>&1
reconstructPar -allRegions -latestTime > log.reconstructPar 2>&1
rm -rf VTK
foamToVTK -allRegions -latestTime -noFunctionObjects > log.foamToVTK 2>&1
''')
        (case / 'Allrun.continue').chmod(0o755)


def exchanger_terms(ha_w_k: float, fin_temperature_c: float) -> Tuple[float, float]:
    """Explicit (W) and implicit (kg/s) totals of an isothermal-fin source on sensible enthalpy (hConst, Tstd 298.15 K)."""
    return ha_w_k * (fin_temperature_c + T0 - 298.15), -ha_w_k / AIR_CP


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


def _has_rows(path: Path) -> bool:
    with open(path, errors='replace') as fh:
        return any(l.strip() and not l.startswith('#') for l in fh)


def _outputs(pp: Path, name: str, kind: str = 'volFieldValue') -> list:
    """Every file one function object logged rows to, oldest solve first. Each solve (the first, then each
    continuation from the latest saved time) writes postProcessing/<region>/<name>/<start time>/<kind>.dat. A solve
    that starts from a time an earlier one already started from (a run that stopped before its next save, continued)
    finds that file there and writes <kind>_<start time>.dat beside it. A solve that crashed at start leaves a file
    with only its header: it logged nothing, so it is left out, as if it had not run (it replaces no rows and is not a
    restart)."""
    pat = re.compile(rf'{re.escape(kind)}(?:_(.+))?\.dat')

    def order(p):                                 # by start time; within a folder, <kind>.dat before <kind>_<t>.dat
        sfx = pat.fullmatch(p.name).group(1)
        try:
            return float(p.parent.name), sfx is not None, float(sfx) if sfx else 0.0
        except ValueError:
            return float(p.parent.name), True, math.inf
    return sorted((p for p in pp.glob(f'**/{name}/*/{kind}*.dat') if pat.fullmatch(p.name) and _has_rows(p)), key=order)


def _whole_run(files, rows_of=_series) -> list:
    """One function object's rows across every solve, in order. A continuation from time T replaces whatever an
    earlier solve logged after T (a solve that stops between saves has logged past the time the next one starts from)."""
    rows = []
    for f in files:
        start = float(f.parent.name)
        rows = [r for r in rows if r[0] <= start] + rows_of(f)
    return rows


def _residual_rows(path: Path) -> list:
    """[iteration, {field: initial residual, or None where that solver did not run}] for each row of a solverInfo.dat."""
    lines = path.read_text().splitlines()
    hdr = next((l for l in lines if l.startswith('#') and 'Time' in l), None)
    if not hdr:
        return []
    cols = [c.strip() for c in (hdr.lstrip('#').split('\t') if '\t' in hdr else hdr.lstrip('#').split())]
    keep = [i for i, c in enumerate(cols) if c.endswith('_initial')]

    def num(s):
        try:
            return float(s)
        except ValueError:                         # N/A, or a line cut short when the solver stopped
            return None
    rows = []
    for l in lines:
        if l.strip() and not l.startswith('#'):
            d = l.split('\t') if '\t' in l else l.split()
            if num(d[0]) is not None:
                rows.append([float(d[0]), {cols[i][:-len('_initial')]: num(d[i]) if i < len(d) else None for i in keep}])
    return rows


RESIDUAL_POINTS = 2000          # a whole-run residual history longer than this keeps the largest of each run of iterations


def _thin_max(its: list, cols: dict, most: int):
    """At most ``most`` points: the first iteration as it is, then each point the largest value over ``every``
    consecutive iterations, at the last of them (never hides a spike; the line starts at the first iteration and ends
    at the last)."""
    if len(its) <= most:
        return its, cols, 1
    every = math.ceil((len(its) - 1) / max(most - 1, 1))
    starts = range(1, len(its), every)
    return ([its[0]] + [its[min(i + every, len(its)) - 1] for i in starts],
            {k: [v[0]] + [max((x for x in v[i:i + every] if x is not None), default=None) for i in starts]
             for k, v in cols.items()},
            every)


def _change_limit(key: str) -> float:
    """How far one ``convergence`` change may go and still count as ``steady`` (strictly less, either sign). Keys ending
    ``_c_change`` (each solid's hottest temperature and the air through each fan) get 1 °C. Everything else gets 2: the
    fan flow and the heat leaving in %, and a fin block's mean air temperature in °C, because its key,
    ``<block>_T_change_c``, does not end ``_c_change``. calibrate_fins applies its own, tighter 0.5 °C to the block and
    intake air before each fin-temperature step."""
    return 1.0 if key.endswith('_c_change') else 2.0


def read_results(case_dir, case: Optional[ThermalCase] = None) -> dict:
    """Temperatures (°C), fan flows and residual history from a finished case's postProcessing output.

    The histories (``residuals``, ``T_max_history``, ``monitors``) cover the whole run, joined across continuations
    (``restarts`` lists where each began); ``convergence`` is measured over ``convergence_window``, the last fifth of the
    iterations within the newest solve."""
    cd = Path(case_dir)
    meta = json.loads((cd / 'cadagent-case.json').read_text())
    pp = cd / 'postProcessing'
    out = {'case': meta['name'], 'ambient_c': meta['ambient_c'], 'solids': {}, 'fans': {}, 'limits': meta['limits']}

    def fo(name, kind='volFieldValue'):           # the newest solve's file (one that crashed at start is left out)
        hits = _outputs(pp, name, kind)
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

    def flow_m3h(fan, u):                         # the zone's mean velocity along the fan axis, through the annulus
        a = np.asarray(fan['axis'], float)
        area = math.pi / 4 * ((fan['d_outer_mm'] / 1000) ** 2 - (fan['d_hub_mm'] / 1000) ** 2)
        return float(np.asarray(u, float) @ (a / np.linalg.norm(a))) * area * 3600

    for fan in meta['fans']:
        z = zones.get(fan['name'])
        if z:
            q = flow_m3h(fan, z['U_m_s'])
            dp = fan['dp0_pa'] * (1 - q / fan['q_free_m3h'])
            out['fans'][fan['name']] = {'flow_m3h': round(q, 2), 'flow_cfm': round(q / 1.699, 2), 'pressure_rise_pa': round(dp, 2),
                                        'fraction_of_free_air': round(q / fan['q_free_m3h'], 3), 'air_through_fan_c': z['T_c']}
    t_amb = meta['ambient_c'] + T0
    ft, fm = fo('flux_T', 'surfaceFieldValue'), fo('flux_mass', 'surfaceFieldValue')
    heat_series = None
    if ft and fm:
        a, m = np.array(_series(ft)), np.array(_series(fm))
        n = min(len(a), len(m))
        heat_series = np.stack([a[:n, 0], AIR_CP * (a[:n, 1] - t_amb * m[:n, 1])], 1)
        out['heat_out_w'] = round(float(heat_series[-1, 1]), 2)
        out['mass_imbalance_kg_s'] = float(m[n - 1, 1])
    q_in = meta.get('heat_input_w')
    if q_in is not None and out.get('heat_out_w') is not None:
        out['heat_input_w'] = q_in
        if q_in > 0:
            out['energy_balance_pct'] = round(100 * (out['heat_out_w'] - q_in) / q_in, 1)
        out['energy_balance_w'] = round(out['heat_out_w'] - q_in, 2)
    # cells each fan and fin zone actually caught (an empty zone silently does nothing)
    ts = cd / 'log.topoSet'
    if ts.exists():
        sizes = {m.group(1): int(m.group(2)) for m in re.finditer(r'cellZoneSet (\w+) now size (\d+)', ts.read_text())}
        out['zone_cells'] = sizes
        empty = [k for k, v in sizes.items() if v == 0]
        if empty:
            out['error'] = f'empty zone(s): {empty}; refine the mesh around them'
    # residuals of the air over the whole run, joined across continuations (each writes its own start-time folder)
    res = _outputs(pp, 'residuals', 'solverInfo')
    if res:
        rows = _whole_run(res, _residual_rows)
        fields = list(dict.fromkeys(k for _, r in rows for k in r))
        its, cols, every = _thin_max([t for t, _ in rows], {k: [r.get(k) for _, r in rows] for k in fields}, RESIDUAL_POINTS)
        out['residuals'] = {'iteration': its, **cols}
        out['residuals_every'] = every            # each point is the largest residual over this many iterations
        out['iterations'] = int(rows[-1][0]) if rows else 0
    # where each continuation began, one entry per solve after the first (two can start from the same saved time);
    # from whichever of the residual and heat-flux outputs holds more solves at that time
    starts = Counter()
    for files in (res, _outputs(pp, 'flux_T', 'surfaceFieldValue')):
        starts |= Counter(float(f.parent.name) for f in files)
    out['restarts'] = [int(s) for s in sorted(starts.elements())[1:]]
    out['planned_iterations'] = meta.get('iterations')
    logs = sorted(cd.glob('log.solve*'), key=lambda p: p.stat().st_mtime)
    if logs:                                  # the newest solve (a calibration restart writes its own log)
        txt = logs[-1].read_text(errors='replace')
        out['solver_finished'] = 'End' in txt.splitlines()[-5:] if txt else False
        out['solver_log'] = logs[-1].name
        m = re.findall(r'ExecutionTime = ([\d.]+) s', txt)
        if m:
            out['wall_time_s'] = float(m[-1])
    hist = {}
    for s in meta['solids']:
        rows = _whole_run(_outputs(pp, f'T_max_{s["name"]}'))
        if rows:
            hist[s['name']] = [[r[0], r[1] - T0] for r in rows]
    out['T_max_history'] = hist
    # the quantities the convergence claim rests on, over the whole run: [iteration, value] every 10 iterations
    monitors = {}

    def monitor(key, name, label, quantity, unit, change, points):
        if points:
            monitors[key] = {'name': name, 'label': label, 'quantity': quantity, 'unit': unit, 'change': change,
                             'points': [[int(round(t)), round(float(v), 4)] for t, v in points]}
    for z in meta.get('porous', []):
        a = _whole_run(_outputs(pp, f'zone_{z["name"]}'))
        monitor(f'{z["name"]}_air_c', z['name'], f'{z["name"]}: mean in the block', 'Air temperature', '°C',
                f'{z["name"]}_T_change_c', [(r[0], r[4] - T0) for r in a])
    for fan in meta['fans']:
        a = _whole_run(_outputs(pp, f'zone_{fan["name"]}'))
        monitor(f'{fan["name"]}_intake_c', fan['name'], f'{fan["name"]}: air through the fan', 'Air temperature', '°C',
                f'{fan["name"]}_intake_c_change', [(r[0], r[4] - T0) for r in a])
        monitor(f'{fan["name"]}_flow_m3h', fan['name'], f'{fan["name"]}: flow through the fan', 'Fan flow', 'm³/h',
                f'{fan["name"]}_flow_change_pct', [(r[0], flow_m3h(fan, r[1:4])) for r in a])
    phi = {r[0]: r[1] for r in _whole_run(_outputs(pp, 'flux_mass', 'surfaceFieldValue'))}
    monitor('heat_out_w', 'heat out', 'heat leaving with the air', 'Heat leaving with the air', 'W', 'heat_out_change_pct',
            [(r[0], AIR_CP * (r[1] - t_amb * phi[r[0]])) for r in _whole_run(_outputs(pp, 'flux_T', 'surfaceFieldValue')) if r[0] in phi])
    out['monitors'] = monitors
    # how much the answer still moved over the last fifth of the iterations, within the newest solve: a continuation
    # (after a fin-temperature step, say) starts a new window, so calibrate_fins judges each step on its own
    conv, window = {}, []

    def tail(a):
        t = a[a[:, 0] >= a[-1, 0] * 0.8]
        window.append((float(t[0, 0]), float(t[-1, 0])))
        return t
    for s in meta['solids']:
        f = fo(f'T_max_{s["name"]}')
        if f:
            a = np.array(_series(f))
            if len(a) > 5:
                t = tail(a)
                conv[f'{s["name"]}_max_c_change'] = round(float(t[-1, 1] - t[0, 1]), 2)
    for z in meta.get('porous', []):
        f = fo(f'zone_{z["name"]}')
        if f:
            a = np.array(_series(f))
            if len(a) > 5:
                t = tail(a)
                conv[f'{z["name"]}_T_change_c'] = round(float(t[-1, 4] - t[0, 4]), 2)
    for fan in meta['fans']:
        f = fo(f'zone_{fan["name"]}')
        if f:
            a = np.array(_series(f))
            if len(a) > 5:
                t = tail(a)
                ax = np.asarray(fan['axis'], float) / np.linalg.norm(fan['axis'])
                u0, u1 = float(t[0, 1:4] @ ax), float(t[-1, 1:4] @ ax)
                conv[f'{fan["name"]}_flow_change_pct'] = round(100 * (u1 - u0) / u1, 1) if u1 else None
                conv[f'{fan["name"]}_intake_c_change'] = round(float(t[-1, 4] - t[0, 4]), 2)
    if heat_series is not None and len(heat_series) > 5:
        t = tail(heat_series)
        conv['heat_out_change_pct'] = round(100 * (t[-1, 1] - t[0, 1]) / t[-1, 1], 1) if t[-1, 1] else None
    out['convergence'] = conv
    if window:
        out['convergence_window'] = [int(min(w[0] for w in window)), int(max(w[1] for w in window))]
    out['convergence_limits'] = {k: _change_limit(k) for k in conv}
    steady = bool(conv) and all(abs(v) < _change_limit(k) for k, v in conv.items() if v is not None)
    # within 5 % of the heat put in (or 0.5 W of nothing, for an airflow-only case); not checkable when an exchanger
    # block has no target power, and then said so
    if out.get('energy_balance_pct') is not None:
        balanced = abs(out['energy_balance_pct']) <= 5
    elif out.get('energy_balance_w') is not None:
        balanced = abs(out['energy_balance_w']) <= 0.5
    else:
        balanced = True
        out['energy_balance'] = 'not checked: an exchanger block has no target power'
    out['steady'] = steady
    out['converged'] = steady and balanced and not out.get('error')
    return out
