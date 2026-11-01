"""Airflow and heat: steady conjugate heat transfer (CHT) cases for OpenFOAM, written from CAD.

    from cadagent.simulation.cfd import ThermalCase, Fan, SOLIDS
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from cadagent._deps import require

_WHY = 'the CFD case writer'
IMAGE = 'opencfd/openfoam-default:2512'
T0 = 273.15
AIR_CP = 1005.0
AIR_R = 8314.462618 / 28.96      # J/(kg K): the case's air, a perfect gas of molar mass 28.96 g/mol
P_ROOM = 1e5                     # Pa: the open boundary's pressure
# The heat leaving with the air must match the heat put in within this (energy_check): 5 % of it, or 0.5 W when
# nothing is put in. read_results' `converged` and run_until_balanced's default use the same 5 %.
ENERGY_TOLERANCE_PCT = 5.0
ENERGY_TOLERANCE_W = 0.5
# Each fan's measuring planes sit this far inside the fan zone's end planes. The zone takes the cells whose centres lie
# strictly between the planes, so a cell centre exactly on an end plane is outside it; the inset puts that cell on the
# outer side of the measuring plane, with the cells further out.
FACE_INSET_M = 1e-7
# Below this fraction of the fan's free-air mass flow, the net flow through a face is too small to weight a temperature
# by: OpenFOAM's weightedAverage divides by it.
MIN_NET_FLOW = 0.01
# A fan's inlet and outlet faces are the two ends of the same columns of cells, so their areas match and, unless much
# air crosses the zone's sides, so do their net flows. Past this fraction apart, results() warns.
FACE_MISMATCH = 0.10
# Air flowing back through a face pulls the mass-flow-weighted temperature away from the air going forward, by the
# backflow over the net flow times the temperature gap between the two. Past this fraction of the net flow, results()
# says the value is the temperature of the net heat flow, not of the air; at the net flow or more, the value can lie
# outside the air's own range and is None.
BACKFLOW_WARN = 0.10
FACE_LIMIT = ("a fan's inlet and outlet temperatures are mass-flow-weighted over the faces at each end of its zone "
              '(face values interpolated between the cells either side); air through the hub is not counted, and air '
              'flowing back through a face makes its value the temperature of the net heat flow, not of the air')


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

    def ends(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The fan zone's upstream and downstream end planes, as their centres (m, to the micrometre the case file
        writes), and the unit axis."""
        c = np.asarray(self.centre, float) / 1000
        a = np.asarray(self.axis, float)
        a = a / np.linalg.norm(a)
        h = self.thickness / 2000
        return np.round(c - a * h, 6), np.round(c + a * h, 6), a

    def faces(self) -> Dict[str, np.ndarray]:
        """Where the fan's inlet and outlet temperatures are measured: a point (m) on the plane across each end of the
        fan zone, FACE_INSET_M inside it, on the axis. Each face is the set of the zone's boundary faces whose two cells
        lie either side of that plane, oriented along the axis, so a positive mass flow is air the fan pushes forward."""
        up, down, a = self.ends()
        return {'inlet': up + a * FACE_INSET_M, 'outlet': down - a * FACE_INSET_M}


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
                raise FileExistsError(f'{case} exists and is not a cadagent.simulation.cfd case; '
                                      'choose an empty or new folder')
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
                       'fans are actuator discs with a straight-line fan curve, no swirl'] + ([FACE_LIMIT] if self.fans else []),
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
        # each fan's inlet and outlet faces (see _zone_sets): the mass-flow-weighted temperature, sum(phi T) / sum(phi),
        # and the net mass flow, sum(phi) in kg/s along the axis. A face with no faces writes NaN, not a crash.
        for f in self.fans:
            for side in ('inlet', 'outlet'):
                zone = f'{f.name}{side.capitalize()}'
                fos.append(f'''    T_{side}_{f.name}
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType faceZone; name {zone};
        fields (T); operation weightedAverage; weightField phi; empty-surface warn; writeFields false; log false;
        writeControl timeStep; writeInterval 10;
    }}
    mass_{side}_{f.name}
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType faceZone; name {zone};
        fields (phi); operation sum; empty-surface warn; writeFields false; log false;
        writeControl timeStep; writeInterval 10;
    }}
    massGross_{side}_{f.name}
    {{
        type surfaceFieldValue; libs (fieldFunctionObjects); region {self.fluid}; regionType faceZone; name {zone};
        fields (phi); operation sumMag; empty-surface warn; writeFields false; log false;
        writeControl timeStep; writeInterval 10;
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
            p1, p2, a = f.ends()
            acts.append(f'''    {{ name {f.name}Set; type cellSet; action new; source cylinderAnnulusToCell;
      point1 ({p1[0]:.6f} {p1[1]:.6f} {p1[2]:.6f}); point2 ({p2[0]:.6f} {p2[1]:.6f} {p2[2]:.6f});
      outerRadius {f.d_outer/2000:.6f}; innerRadius {f.d_hub/2000:.6f}; }}
    {{ name {f.name}; type cellZoneSet; action new; source setToCellZone; set {f.name}Set; }}''')
            # the inlet and outlet faces (OpenFOAM v2512 topoSet): the faces between a zone cell and a cell beyond each
            # end plane. planeToFaceZone takes every face whose two cell centres lie either side of the plane, oriented
            # from the cell behind it to the cell ahead along the axis; subtracting every face that is not on the zone's
            # boundary (cellToFace 'outside' of the zone, synchronised across processors, then inverted) leaves the
            # zone's own end faces. Selecting by the cells, not by where a face lies, keeps the faces right where the
            # zone's end meets coarser cells, which own the faces and would put their centres over the hub or past the
            # rim (searchableDisk tests the radius at the owner's centre).
            acts.append(f'''    {{ name {f.name}OffZoneFaces; type faceSet; action new; source cellToFace; set {f.name}Set; option outside; }}
    {{ name {f.name}OffZoneFaces; type faceSet; action invert; }}''')
            for side, o in f.faces().items():
                acts.append(f'''    {{ name {f.name}{side.capitalize()}; type faceZoneSet; action new; source planeToFaceZone;
      point ({o[0]:.9f} {o[1]:.9f} {o[2]:.9f}); normal ({a[0]:.9f} {a[1]:.9f} {a[2]:.9f}); option all; }}
    {{ name {f.name}{side.capitalize()}; type faceZoneSet; action subtract; source setToFaceZone; faceSet {f.name}OffZoneFaces; }}''')
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
# Written by cadagent.simulation.cfd. Runs inside the OpenFOAM environment (Docker image {IMAGE} or a native install).
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
        temperatures have stopped moving (0.5 K over ``convergence_window``), and moves at most 20 K; otherwise the round just
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
        if not re.search(r'^\s*T_inlet_', txt, flags=re.M):   # written before the fan faces: continuing adds none
            meta['limits'] = [l for l in meta['limits'] if l != FACE_LIMIT]
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


def stream_heat_w(mass_flow_kg_s: float, temperature_c: float, ambient_c: float, cp: float = AIR_CP) -> float:
    """The heat a stream of air carries above the room, Q = m_dot c_p (T - T_room) in W, with T its mass-flow-weighted
    (bulk) temperature: the only temperature for which m_dot c_p T is the enthalpy the stream carries. A volume
    average weights stagnant and recirculating air like the air that flows, so it does not give the heat."""
    return float(mass_flow_kg_s) * cp * (float(temperature_c) - float(ambient_c))


def energy_check(heat_input_w: Optional[float], heat_out_w: Optional[float], tolerance_pct: float = ENERGY_TOLERANCE_PCT,
                 tolerance_w: float = ENERGY_TOLERANCE_W) -> dict:
    """Does a result conserve energy? In a steady case with adiabatic walls every watt put in leaves with the air, so
    the heat leaving (W, rounded to 0.01 W as read_results reports it) must match the heat put in: within
    ``tolerance_pct`` of it, or within ``tolerance_w`` of nothing when nothing is put in. A result outside that has not
    settled (or lost heat to the numerics), and its temperatures are not an answer yet. ``conserved`` is None when either
    side is unknown, with ``why``."""
    out = {'heat_input_w': heat_input_w, 'heat_out_w': heat_out_w, 'conserved': None}
    if heat_input_w is None:
        return dict(out, why='not checked: an exchanger block has no target power, so the heat put in is unknown')
    if heat_out_w is None:
        return dict(out, why='not checked: no heat-leaving output (flux_T, flux_mass) was found')
    out['difference_w'] = round(heat_out_w - heat_input_w, 2)
    if heat_input_w > 0:
        out['difference_pct'] = round(100 * (heat_out_w - heat_input_w) / heat_input_w, 1)
        out['tolerance'] = f'±{tolerance_pct:g} %'
        out['conserved'] = abs(out['difference_pct']) <= tolerance_pct
    else:
        out['tolerance'] = f'±{tolerance_w:g} W'
        out['conserved'] = abs(out['difference_w']) <= tolerance_w
    return out


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
                f'    class {cls};\n    object {obj};\n}}\n// written by cadagent.simulation.cfd\n\n')
        p.write_text(head + body)


def _series(path: Path):
    rows = [l.split() for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')]
    return [[float(x.strip('()')) for x in r] for r in rows]


def _header(path: Path) -> dict:
    """The '# Key : value' lines at the top of a function-object file (surfaceFieldValue writes Faces and Area)."""
    out = {}
    with open(path, errors='replace') as fh:
        for line in fh:
            if not line.startswith('#'):
                break
            k, sep, v = line[1:].partition(':')
            if sep:
                out[k.strip()] = v.strip()
    return out


def _has_rows(path: Path) -> bool:
    with open(path, errors='replace') as fh:
        return any(l.strip() and not l.startswith('#') for l in fh)


def _solve_of(path: Path) -> tuple:
    """The solve that wrote one function-object file, as a key that sorts in the order the solves ran: its start time
    (the folder), then <kind>.dat before the <kind>_<t>.dat a later solve from the same time writes beside it. Every
    file one solve writes has the same key (OpenFOAM's output kinds have no underscore)."""
    sfx = path.stem.partition('_')[2]
    try:
        return float(path.parent.name), bool(sfx), float(sfx) if sfx else 0.0
    except ValueError:
        return float(path.parent.name), True, math.inf


def _outputs(pp: Path, name: str, kind: str = 'volFieldValue') -> list:
    """Every file one function object logged rows to, oldest solve first. Each solve (the first, then each
    continuation from the latest saved time) writes postProcessing/<region>/<name>/<start time>/<kind>.dat. A solve
    that starts from a time an earlier one already started from (a run that stopped before its next save, continued)
    finds that file there and writes <kind>_<start time>.dat beside it. A file with only its header is left out, as
    its solve logged nothing to it: either the solve crashed at start (it logged nothing anywhere, so it is not a
    restart and replaces no rows), or it stopped before this output's first sample (every 10 iterations for all but the
    residuals), and then _whole_run still replaces the earlier rows from its start."""
    pat = re.compile(rf'{re.escape(kind)}(?:_(.+))?\.dat')
    return sorted((p for p in pp.glob(f'**/{name}/*/{kind}*.dat') if pat.fullmatch(p.name) and _has_rows(p)), key=_solve_of)


def _whole_run(files, rows_of=_series, solves=()) -> list:
    """One function object's rows across every solve, in order. A continuation from time T replaces whatever an
    earlier solve logged after T (a solve that stops between saves has logged past the time the next one starts from),
    even when it logged nothing to this function object itself: ``solves`` are the keys (_solve_of) of every solve that
    logged anything, residuals included, so one that stopped before its first sample still cuts at its start."""
    own = {_solve_of(f): f for f in files}
    rows = []
    for key in sorted(set(own) | set(solves)):
        rows = [r for r in rows if r[0] <= key[0]] + (rows_of(own[key]) if key in own else [])
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
    """How far one ``convergence`` change may go and still count as ``steady`` (strictly less, either sign): 2 % for a
    change in % (a key ending ``_pct``: the fan flow and the heat leaving) and 1 °C for every temperature (each solid's
    hottest, a fin block's mean air and the air through each fan), by the same unit rule the chart's captions use.
    calibrate_fins applies its own, tighter 0.5 °C to the block and intake air before each fin-temperature step."""
    return 2.0 if key.endswith('_pct') else 1.0


def read_results(case_dir, case: Optional[ThermalCase] = None) -> dict:
    """Temperatures (°C), fan flows and residual history from a finished case's postProcessing output.

    The histories (``residuals``, ``T_max_history``, ``monitors``) cover the whole run, joined across continuations
    (``restarts`` lists where each began), and the headline values are their last rows. ``convergence`` is how much
    each monitored value changed over ``convergence_window``: the iterations from 80 % of the last one onward, cut to
    the newest solve (so after a continuation shorter than a fifth of the run, the whole newest solve; after one that
    stopped before its first temperature sample, nothing, and no window). ``convergence_limits`` is what ``steady``
    holds each change to.

    Each fan has three temperatures. ``fans[<fan>]['inlet_c']`` and ``['outlet_c']`` are mass-flow-weighted,
    sum(phi T) / sum(phi), over the faces at each end of its zone (where a zone cell meets a cell beyond that end),
    with the net mass flow through each (``inlet_kg_s``, ``outlet_kg_s``, positive along the axis), each face's area
    (``inlet_area_m2``, ``outlet_area_m2``) and ``heat_carried_w``, the heat the outlet stream carries above the room
    (stream_heat_w). The two ends of a zone are the ends of the same cells, so a warning names any end whose area or
    net flow is more than FACE_MISMATCH off the other's. Use these in energy balances. ``air_through_fan_c`` (also
    ``zones[<fan>]['T_c']``) is the volume average over the zone: it weights still and returning air like the air that
    flows. A case written before the faces existed reports only the volume average. ``energy_conserved`` is
    energy_check's verdict, and ``warnings`` says in words what is off."""
    cd = Path(case_dir)
    meta = json.loads((cd / 'cadagent-case.json').read_text())
    pp = cd / 'postProcessing'
    out = {'case': meta['name'], 'ambient_c': meta['ambient_c'], 'solids': {}, 'fans': {}, 'limits': meta['limits']}

    # every solve that logged anything, residuals included (a solve logs them every iteration, the rest every 10)
    res = _outputs(pp, 'residuals', 'solverInfo')
    solves = sorted({_solve_of(f) for f in res + _outputs(pp, 'flux_T', 'surfaceFieldValue')})

    def run(name, kind='volFieldValue'):          # one output's rows over the whole run; the headline is the last
        return _whole_run(_outputs(pp, name, kind), solves=solves)

    def newest(name, kind='volFieldValue'):       # its rows from the newest solve, none if it logged none there
        hits = _outputs(pp, name, kind)
        return _series(hits[-1]) if hits and (not solves or _solve_of(hits[-1]) >= solves[-1]) else []

    for s in meta['solids']:
        row = {}
        for op, key in (('max', 'max_c'), ('volAverage', 'mean_c')):
            a = run(f'T_{op}_{s["name"]}')
            if a:
                row[key] = round(a[-1][1] - T0, 2)
        row.update(power_w=s['power_w'], material=s['material'])
        out['solids'][s['name']] = row
    a = run(f'T_max_{case.fluid if case else "domain0"}')
    if a:
        out['air_max_c'] = round(a[-1][1] - T0, 2)
    zones = {}
    for zn in [f['name'] for f in meta['fans']] + [z['name'] for z in meta.get('porous', [])]:
        a = run(f'zone_{zn}')
        if a:
            r = a[-1]
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
    warn = []

    def face(of, fan, side):
        """[iteration, mass-flow-weighted T (°C), net mass flow (kg/s), backflow (kg/s; NaN where not logged)] and
        the rows whose temperature means something: enough net flow forward, and less flowing back."""
        m = {r[0]: r[1] for r in of(f'mass_{side}_{fan["name"]}', 'surfaceFieldValue')}
        g = {r[0]: r[1] for r in of(f'massGross_{side}_{fan["name"]}', 'surfaceFieldValue')}
        rows = np.array([[r[0], r[1] - T0, m[r[0]], max(g[r[0]] - m[r[0]], 0.0) / 2 if r[0] in g else math.nan]
                         for r in of(f'T_{side}_{fan["name"]}', 'surfaceFieldValue')
                         if r[0] in m and math.isfinite(r[1]) and math.isfinite(m[r[0]])]).reshape(-1, 4)
        free = P_ROOM / (AIR_R * t_amb) * fan['q_free_m3h'] / 3600
        net, back = rows[:, 2], rows[:, 3]
        return rows, (net >= MIN_NET_FLOW * free) & ~(back >= net)

    def unusable(fan, side, net, back):           # why a face's temperature is None, in words
        if net < 0:
            return (f'{fan} {side}: the net flow through it runs backwards, {net:.3g} kg/s along the axis, so it has no '
                    f'temperature of air {"entering" if side == "inlet" else "leaving"} the fan')
        if back >= net:
            return (f'{fan} {side}: {back:.3g} kg/s flows back through it for {net:.3g} kg/s net, so the mass-flow-'
                    f'weighted value could lie outside the air\'s own range')
        return (f'{fan} {side}: the net flow through it, {net:.3g} kg/s, is under {MIN_NET_FLOW:.0%} of the fan\'s '
                f'free-air flow, too little to weight a temperature by')

    # each fan's inlet and outlet: mass-flow-weighted over the faces at each end of its zone (cases written before
    # these outputs existed have none, and keep only the volume average, air_through_fan_c)
    face_count = {}
    for fan in meta['fans']:
        for side in ('inlet', 'outlet'):
            rows, ok = face(run, fan, side)
            if not len(rows):
                continue
            f = out['fans'].setdefault(fan['name'], {})
            _, t, net, back = rows[-1]
            f[f'{side}_kg_s'] = float(net)
            if math.isfinite(back):
                f[f'{side}_backflow_kg_s'] = float(back)
            # the solver's own count and area, each face once (topoSet's log counts a processor boundary's twice)
            head = _header(_outputs(pp, f'T_{side}_{fan["name"]}', 'surfaceFieldValue')[-1])
            if 'Faces' in head:
                face_count[f'{fan["name"]}{side.capitalize()}'] = int(float(head['Faces']))
            if 'Area' in head:
                f[f'{side}_area_m2'] = float(head['Area'])
            f[f'{side}_c'] = round(float(t), 2) if ok[-1] else None
            if not ok[-1]:
                warn.append(unusable(fan['name'], side, net, back))
            elif back > BACKFLOW_WARN * net:
                warn.append(f'{fan["name"]} {side}: {back:.3g} kg/s flows back through it, {back / net:.0%} of the net '
                            f'{net:.3g} kg/s, so {side}_c is the temperature of the net heat flow (right for ṁ c_p ΔT), '
                            f'not of the air crossing it')
            if side == 'outlet':                  # the net heat carried along the axis, exact whatever flows back
                f['heat_carried_w'] = round(stream_heat_w(net, t, meta['ambient_c']), 2)
        f = out['fans'].get(fan['name'], {})
        # the two ends of a zone are the ends of the same cells: their areas match, and their net flows unless much air
        # crosses the zone's sides
        for key, what, unit in (('area_m2', 'areas', 'm²'), ('kg_s', 'net flows', 'kg/s')):
            a, b = f.get(f'inlet_{key}'), f.get(f'outlet_{key}')
            if key == 'kg_s' and (f.get('inlet_c') is None or f.get('outlet_c') is None):
                continue                          # a face with no temperature has its own warning
            if a is not None and b is not None and max(abs(a), abs(b)) > 0 and \
                    abs(a - b) > FACE_MISMATCH * max(abs(a), abs(b)):
                warn.append(f'{fan["name"]}: its inlet and outlet {what} differ, {a:.3g} against {b:.3g} {unit} '
                            f'(more than {FACE_MISMATCH:.0%}): '
                            + ('check the mesh at the ends of its zone, where a face may have missed cells'
                               if key == 'area_m2' else 'air crosses the sides of its zone, through the hub or round the rim'))

    def heat_out(of):                             # [iteration, heat leaving (W), mass flux (kg/s)] where both logged
        phi = {r[0]: r[1] for r in of('flux_mass', 'surfaceFieldValue')}
        return np.array([[r[0], AIR_CP * (r[1] - t_amb * phi[r[0]]), phi[r[0]]]
                         for r in of('flux_T', 'surfaceFieldValue') if r[0] in phi]).reshape(-1, 3)
    heat_run = heat_out(run)
    if len(heat_run):
        out['heat_out_w'] = round(float(heat_run[-1, 1]), 2)
        out['mass_imbalance_kg_s'] = float(heat_run[-1, 2])
    # is energy conserved? the heat leaving with the air against the heat put in (energy_check)
    energy = energy_check(meta.get('heat_input_w'), out.get('heat_out_w'))
    if energy['conserved'] is not None:
        out['heat_input_w'] = energy['heat_input_w']
        if 'difference_pct' in energy:
            out['energy_balance_pct'] = energy['difference_pct']
        out['energy_balance_w'] = energy['difference_w']
    out['energy_conserved'] = energy['conserved']
    if energy['conserved'] is False:
        off = (f'{energy["difference_pct"]:+.1f} %' if 'difference_pct' in energy else f'{energy["difference_w"]:+.2f} W')
        warn.append(f'energy not conserved: {energy["heat_out_w"]:g} W leave with the air for {energy["heat_input_w"]:g} W '
                    f'put in ({off}; tolerance {energy["tolerance"]}). The temperatures are not an answer yet: continue the '
                    'run (run_until_balanced) or refine the mesh')
    # cells each fan and fin zone, and faces each fan's inlet and outlet, actually caught (an empty zone does nothing)
    ts = cd / 'log.topoSet'
    if ts.exists():
        log_ts = ts.read_text()
        sizes = {m.group(1): int(m.group(2)) for m in re.finditer(r'cellZoneSet (\w+) now size (\d+)', log_ts)}
        # a faceZoneSet's last size is the one it ended with; the solver's own count replaces it where it logged one
        faces = {m.group(1): int(m.group(2)) for m in re.finditer(r'faceZoneSet (\w+) now size (\d+)', log_ts)}
        faces.update(face_count)
        out['zone_cells'] = sizes
        if faces:
            out['zone_faces'] = faces
        empty = [k for k, v in {**sizes, **faces}.items() if v == 0]
        if empty:
            out['error'] = f'empty zone(s): {empty}; refine the mesh around them'
    # residuals of the air over the whole run, joined across continuations (each writes its own start-time folder)
    if res:
        rows = _whole_run(res, _residual_rows, solves)
        fields = list(dict.fromkeys(k for _, r in rows for k in r))
        its, cols, every = _thin_max([t for t, _ in rows], {k: [r.get(k) for _, r in rows] for k in fields}, RESIDUAL_POINTS)
        out['residuals'] = {'iteration': its, **cols}
        out['residuals_every'] = every            # each point is the largest residual over this many iterations
        out['iterations'] = int(rows[-1][0]) if rows else 0
    # where each continuation began, one entry per solve after the first (two can start from the same saved time)
    out['restarts'] = [int(k[0]) for k in solves[1:]]
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
        rows = run(f'T_max_{s["name"]}')
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
        a = run(f'zone_{z["name"]}')
        monitor(f'{z["name"]}_air_c', z['name'], f'{z["name"]}: mean in the block', 'Air temperature', '°C',
                f'{z["name"]}_T_change_c', [(r[0], r[4] - T0) for r in a])
    for fan in meta['fans']:
        a = run(f'zone_{fan["name"]}')
        monitor(f'{fan["name"]}_intake_c', fan['name'], f'{fan["name"]}: mean over the fan zone (by volume)', 'Air temperature',
                '°C', f'{fan["name"]}_intake_c_change', [(r[0], r[4] - T0) for r in a])
        for side, words in (('inlet', 'entering'), ('outlet', 'leaving')):
            rows, ok = face(run, fan, side)
            monitor(f'{fan["name"]}_{side}_c', f'{fan["name"]} {side}', f'{fan["name"]}: air {words} (mass-flow-weighted)',
                    'Air temperature', '°C', f'{fan["name"]}_{side}_c_change', rows[ok][:, :2].tolist())
        monitor(f'{fan["name"]}_flow_m3h', fan['name'], f'{fan["name"]}: flow through the fan', 'Fan flow', 'm³/h',
                f'{fan["name"]}_flow_change_pct', [(r[0], flow_m3h(fan, r[1:4])) for r in a])
    monitor('heat_out_w', 'heat out', 'heat leaving with the air', 'Heat leaving with the air', 'W', 'heat_out_change_pct',
            heat_run[:, :2].tolist())
    out['monitors'] = monitors
    # how much the answer still moved over the iterations from 80 % of the last one on, cut to the newest solve: a
    # continuation (after a fin-temperature step, say) starts a new window, so calibrate_fins judges each step on its own,
    # and one that logged no temperature or heat rows (it stopped within 9 iterations) measured nothing: no window
    conv, window = {}, []

    def tail(a):
        t = a[a[:, 0] >= a[-1, 0] * 0.8]
        window.append((float(t[0, 0]), float(t[-1, 0])))
        return t
    for s in meta['solids']:
        a = np.array(newest(f'T_max_{s["name"]}'))
        if len(a) > 5:
            t = tail(a)
            conv[f'{s["name"]}_max_c_change'] = round(float(t[-1, 1] - t[0, 1]), 2)
    for z in meta.get('porous', []):
        a = np.array(newest(f'zone_{z["name"]}'))
        if len(a) > 5:
            t = tail(a)
            conv[f'{z["name"]}_T_change_c'] = round(float(t[-1, 4] - t[0, 4]), 2)
    for fan in meta['fans']:
        a = np.array(newest(f'zone_{fan["name"]}'))
        if len(a) > 5:
            t = tail(a)
            ax = np.asarray(fan['axis'], float) / np.linalg.norm(fan['axis'])
            u0, u1 = float(t[0, 1:4] @ ax), float(t[-1, 1:4] @ ax)
            conv[f'{fan["name"]}_flow_change_pct'] = round(100 * (u1 - u0) / u1, 1) if u1 else None
            conv[f'{fan["name"]}_intake_c_change'] = round(float(t[-1, 4] - t[0, 4]), 2)
        for side in ('inlet', 'outlet'):
            rows, ok = face(newest, fan, side)
            if ok.sum() > 5:
                t = tail(rows[ok])
                conv[f'{fan["name"]}_{side}_c_change'] = round(float(t[-1, 1] - t[0, 1]), 2)
    heat_series = heat_out(newest)
    if len(heat_series) > 5:
        t = tail(heat_series)
        conv['heat_out_change_pct'] = round(100 * (t[-1, 1] - t[0, 1]) / t[-1, 1], 1) if t[-1, 1] else None
    out['convergence'] = conv
    if window:
        out['convergence_window'] = [int(min(w[0] for w in window)), int(max(w[1] for w in window))]
    limit = out['convergence_limits'] = {k: _change_limit(k) for k in conv}      # what the chart's captions show, too
    steady = bool(conv) and all(abs(v) < limit[k] for k, v in conv.items() if v is not None)
    # within 5 % of the heat put in (or 0.5 W of nothing, for an airflow-only case); not checkable when the heat put in
    # (an exchanger block without a target power) or the heat leaving is unknown, and then said so
    balanced = energy['conserved'] is not False
    if energy['conserved'] is None:
        out['energy_balance'] = energy['why']
    out['steady'] = steady
    out['converged'] = steady and balanced and not out.get('error')
    out['warnings'] = warn
    return out
