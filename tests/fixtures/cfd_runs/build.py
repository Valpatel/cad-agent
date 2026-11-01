"""Write the recorded-format CFD runs the convergence tests read, listed below. No solver runs: the numbers are
synthetic, laid out exactly as OpenFOAM v2512 writes them for a cadagent.simulation.cfd case (cadagent-case.json, the
solver logs and postProcessing/<region>/<function>/<start time>/*.dat, one start-time folder per solve).
Deterministic; rebuild with

    python tests/fixtures/cfd_runs/build.py

fins-no-solids      air only: a fan blowing into an exchanger fin block (a porous zone), 40 W. A first solve to 200,
                    then two 60-iteration continuations, as calibrate_fins makes after each fin-temperature step.
                    Every solve finished.
solids-ended-early  air and two solid regions (a 5 W chip on an aluminium plate). The first solve, to 300, saved
                    time 100 and then diverged and stopped at 150; a continuation from 100 reached 200; the next
                    one, planned to 300, stopped at 236.
solids-continued-again
                    solids-ended-early continued once more: the stopped solve saved nothing after 200, so the next
                    one starts from 200 again and finishes at 300. Its 200/ folders already hold <kind>.dat, so it
                    writes <kind>_200.dat beside them, as OpenFOAM does.
solids-crashed-restart
                    the same first solve (saved 100, diverged, stopped at 150); the continuation from 100 crashed at
                    start and left header-only files in every 100/ folder.
solids-short-continuation
                    the same first solve; the continuation from 100 diverged after 4 iterations, at 104. It logged
                    residuals (every iteration) but left header-only temperature and heat files (logged every 10).
solids-one-step-continuation
                    the same, but the continuation from 100 crashed after its first iteration, at 101.
fins-block-drifting air only, the fin-block case in one 100-iteration solve: the fan flow, the air through the fan and
                    the heat leaving have settled, the heat leaving within 1 % of the 40 W put in, but the block's
                    mean air is still rising, by 1.5 °C over the convergence window (80-100).
fan-faces-known-profile
                    air only, a vented box whose only way out is an exhaust fan, 50 W put in, in one settled
                    100-iteration solve. The fan's annulus carries a known profile, the same at both ends of its
                    zone: its inner half (by area) 1 g/s of air at 30 °C, its outer half 3 g/s at 40 °C. By volume
                    the zone averages (30 + 40) / 2 = 35.0 °C; by mass flow (1 x 30 + 3 x 40) / 4 = 37.5 °C. The
                    face rows are computed face by face, sum(phi T) / sum(phi), as surfaceFieldValue does.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
T0, CP = 273.15, 1005.0
FIELDS = ('U', 'h', 'k', 'omega', 'p_rgh')
SOLVER = {'U': 'DILUPBiCGStab', 'h': 'DILUPBiCGStab', 'k': 'DILUPBiCGStab', 'omega': 'DILUPBiCGStab', 'p_rgh': 'GAMG'}
LIMITS = ['steady RANS (k-omega SST): natural-convection plumes really fluctuate',
          'converged means the temperatures, fan flow and heat leaving stopped changing and the heat leaving matches the '
          'heat put in (energy balance), not that the residuals reached a tolerance']


def dat(folder: Path, kind: str, start: int) -> Path:
    """The file a solve starting at ``start`` writes one function object's rows to: <kind>.dat in its start-time folder,
    or <kind>_<start>.dat when an earlier solve from the same time already wrote <kind>.dat there (OpenFOAM's naming;
    it happens when a run that stopped before its next save is continued)."""
    p = folder / f'{kind}.dat'
    return folder / f'{kind}_{start}.dat' if p.exists() else p


def _num(v):
    return f'{v:.8e}'


def solver_info(path: Path, rows):
    """rows: (iteration, {Ux, Uy, Uz, h, k, omega, p_rgh: initial residual})."""
    cols = []
    for f in FIELDS:
        if f == 'U':
            cols += ['U_solver'] + [f'U{c}_{s}' for c in 'xyz' for s in ('initial', 'final', 'iters')] + ['U_converged']
        else:
            cols += [f'{f}_solver', f'{f}_initial', f'{f}_final', f'{f}_iters', f'{f}_converged']
    out = ['# Solver information', '# ' + 'Time'.ljust(14) + ''.join('\t' + c.ljust(16) for c in cols)]
    for t, r in rows:
        vals = []
        for f in FIELDS:
            if f == 'U':
                vals += [SOLVER[f]] + [x for c in 'xyz' for x in (_num(r['U' + c]), _num(r['U' + c] * 0.02), '1')] + ['false']
            else:
                vals += [SOLVER[f], _num(r[f]), _num(r[f] * 0.02), '3' if f == 'p_rgh' else '1', 'true']
        out.append(str(t).ljust(16) + '\t' + '\t'.join(vals))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(out) + '\n')


def vol_field(path: Path, region: str, columns: str, rows, cells: int, volume: float):
    head = [f'# Region        : {region}', f'# Cells         : {cells}', f'# Volume        : {_num(volume)}',
            '# Time          \t' + columns]
    body = []
    for t, *vals in rows:
        body.append(str(t).ljust(16) + '\t' + '\t'.join(
            '(' + ' '.join(_num(x) for x in v) + ')' if isinstance(v, (tuple, list)) else _num(v) for v in vals))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(head + body) + '\n')


def surface_field(path: Path, column: str, rows, weight: bool, region='patch ambient', faces=2280, area=2.21275997e-01):
    head = [f'# Region type : {region}', f'# Faces         : {faces}', f'# Area          : {_num(area)}',
            '# Scale factor  : 1.00000000e+00'] + (['# Weight field  : phi'] if weight else []) + ['# Time          \t' + column]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(head + [str(t).ljust(16) + '\t' + _num(v) for t, v in rows]) + '\n')


def log(path: Path, first: int, last: int, finished: bool, crash: str = ''):
    lines = ['/*---------------------------------------------------------------------------*\\',
             '| =========                 |                                                 |',
             'Starting time loop', '']
    for t in range(first, last + 1, max(1, (last - first) // 4)):
        lines += [f'Time = {t}', '', 'DILUPBiCGStab:  Solving for h, Initial residual = 0.0012, Final residual = 2.4e-05, No Iterations 1',
                  f'ExecutionTime = {0.4 * t:.2f} s  ClockTime = {math.ceil(0.4 * t)} s', '']
    if finished:
        lines += ['End', '', 'Finalising parallel run']
    else:
        lines += [crash or 'GAMG:  Solving for p_rgh, Initial residual = 0.0025, Final residual = 8.3e-06, No Iterations 3']
    path.write_text('\n'.join(lines) + '\n')


def residuals(rng, t, restarts, settle, diverge_from=None):
    """Initial residuals at iteration t: a decay to a floor, a kick after each restart, a blow-up when diverging."""
    base = {'Ux': (0.6, 4e-5), 'Uy': (0.6, 9e-4), 'Uz': (0.6, 1.2e-4), 'h': (0.8, 1.6e-3), 'k': (0.5, 1.1e-3),
            'omega': (0.05, 1.3e-4), 'p_rgh': (0.9, 2.5e-3)}
    out = {}
    for k, (a, floor) in base.items():
        v = a * math.exp(-t / settle) + floor
        for r in restarts:
            if t > r:
                v += 8 * floor * math.exp(-(t - r) / 12)
        if diverge_from is not None and t > diverge_from:
            v *= math.exp((t - diverge_from) / 6)
        out[k] = min(1.0, v * math.exp(rng.normal(0, 0.08)))
    return out


def approach(t, pieces, tau):
    """Piecewise first-order approach: pieces = [(start, value at start, target), ...] in order."""
    for s, v0, target in reversed(pieces):
        if t >= s:
            return target + (v0 - target) * math.exp(-(t - s) / tau)
    return pieces[0][1]


def fins_meta(name: str, iterations: int) -> dict:
    """cadagent-case.json of the air-only case: a fan blowing into an exchanger fin block (a porous zone), 40 W."""
    return {'name': name, 'solver': 'chtMultiRegionSimpleFoam (OpenFOAM v2512)', 'ambient_c': 25.0,
            'domain_mm': [[-30, -25, -3], [236, 216, 152]], 'base_cell_mm': 10.0, 'iterations': iterations,
            'ground': 'adiabatic no-slip floor (a table)', 'solids': [], 'walls': [{'name': 'enclosure', 'cell_mm': 2.5}],
            'contacts': [], 'fans': [{'name': 'fan', 'centre_mm': [105, 105, 67], 'axis': [0, 0, -1], 'd_outer_mm': 76.0,
                                      'd_hub_mm': 33.0, 'dp0_pa': 15.2, 'q_free_m3h': 38.9, 'q_free_cfm': 22.9,
                                      'note': 'an 80 mm fan, straight-line curve', 'model': 'actuator disc, linear fan curve'}],
            'porous': [{'name': 'fins', 'lo_mm': [55, 63, 45], 'hi_mm': [155, 148, 59], 'd': [7.6e6, 7.6e9, 7.6e6],
                        'f': [15.9, 0, 15.9], 'e1': [1, 0, 0], 'e2': [0, 1, 0], 'heat_w': 0.0, 'ha_w_k': 3.3,
                        'fin_temperature_c': 61.8, 'target_w': 40.0, 'note': 'compact fin block'}],
            'heat_input_w': 40.0, 'limits': LIMITS}


def fins_no_solids(case: Path):
    rng = np.random.default_rng(50)
    solves = [(0, 200), (200, 260), (260, 320)]
    restarts = [s for s, _ in solves[1:]]
    meta = fins_meta('fins-no-solids', 320)
    fin_air = [(0, 80.0, 62.0), (200, None, 50.0), (260, None, 49.2)]       # each fin-temperature step moves the target
    heat = [(0, 0.0, 34.0), (200, None, 39.0), (260, None, 39.4)]
    for pieces, tau in ((fin_air, 70), (heat, 90)):
        for i in range(1, len(pieces)):
            pieces[i] = (pieces[i][0], approach(pieces[i][0], pieces[:i], tau), pieces[i][2])
    pp = case / 'postProcessing' / 'domain0'
    for start, end in solves:
        its = range(start + 1, end + 1)
        solver_info(pp / 'residuals' / str(start) / 'solverInfo.dat', [(t, residuals(rng, t, restarts, 40)) for t in its])
        ts = range(start + 10, end + 1, 10)
        uz = [-(0.98 - 0.6 * math.exp(-t / 90)) for t in ts]
        vol_field(pp / 'zone_fan' / str(start) / 'volFieldValue.dat', 'cellZone fan', 'volAverage(U)\tvolAverage(T)',
                  [(t, (0.003, -0.002, u), T0 + approach(t, [(0, 26.0, 37.6)], 60) + rng.normal(0, 0.02)) for t, u in zip(ts, uz)],
                  11910, 2.27e-5)
        vol_field(pp / 'zone_fins' / str(start) / 'volFieldValue.dat', 'cellZone fins', 'volAverage(U)\tvolAverage(T)',
                  [(t, (0.0004, 0.0, 0.2 * u), T0 + approach(t, fin_air, 70)) for t, u in zip(ts, uz)], 66096, 1.19e-4)
        vol_field(pp / 'T_max_domain0' / str(start) / 'volFieldValue.dat', 'all domain0', 'max(T)',
                  [(t, T0 + 61.8) for t in ts], 1362340, 9.04e-3)
        phi = [-4e-7 + rng.normal(0, 5e-8) for _ in ts]
        q = [approach(t, heat, 90) + rng.normal(0, 0.15) for t in ts]
        surface_field(pp / 'flux_mass' / str(start) / 'surfaceFieldValue.dat', 'sum(phi)', list(zip(ts, phi)), weight=False)
        surface_field(pp / 'flux_T' / str(start) / 'surfaceFieldValue.dat', 'weightedSum(T)',
                      [(t, qq / CP + (25 + T0) * p) for t, qq, p in zip(ts, q, phi)], weight=True)
    for i, (start, end) in enumerate(solves):
        log(case / ('log.solve' if i == 0 else f'log.solve.{1793000000 + i}'), start + 1, end, finished=True)
    (case / 'log.topoSet').write_text('cellZoneSet fins now size 66096\ncellZoneSet fan now size 11910\n')
    (case / 'cadagent-case.json').write_text(json.dumps(meta, indent=2) + '\n')


def fins_block_drifting(case: Path):
    rng = np.random.default_rng(52)
    pp = case / 'postProcessing' / 'domain0'
    solver_info(pp / 'residuals' / '0' / 'solverInfo.dat', [(t, residuals(rng, t, [], 20)) for t in range(1, 101)])
    ts = range(10, 101, 10)
    u = (0.003, -0.002, -0.98)
    vol_field(pp / 'zone_fan' / '0' / 'volFieldValue.dat', 'cellZone fan', 'volAverage(U)\tvolAverage(T)',
              [(t, u, T0 + 37.6) for t in ts], 11910, 2.27e-5)
    vol_field(pp / 'zone_fins' / '0' / 'volFieldValue.dat', 'cellZone fins', 'volAverage(U)\tvolAverage(T)',
              [(t, (0.0004, 0.0, 0.2 * u[2]), T0 + 44.0 + 0.075 * t) for t in ts], 66096, 1.19e-4)   # 50.0 at 80, 51.5 at 100
    vol_field(pp / 'T_max_domain0' / '0' / 'volFieldValue.dat', 'all domain0', 'max(T)', [(t, T0 + 61.8) for t in ts],
              1362340, 9.04e-3)
    phi = [-4e-7 + rng.normal(0, 5e-8) for _ in ts]
    q = [39.6 + rng.normal(0, 0.05) for _ in ts]
    surface_field(pp / 'flux_mass' / '0' / 'surfaceFieldValue.dat', 'sum(phi)', list(zip(ts, phi)), weight=False)
    surface_field(pp / 'flux_T' / '0' / 'surfaceFieldValue.dat', 'weightedSum(T)',
                  [(t, qq / CP + (25 + T0) * p) for t, qq, p in zip(ts, q, phi)], weight=True)
    log(case / 'log.solve', 1, 100, finished=True)
    (case / 'log.topoSet').write_text('cellZoneSet fins now size 66096\ncellZoneSet fan now size 11910\n')
    (case / 'cadagent-case.json').write_text(json.dumps(fins_meta('fins-block-drifting', 100), indent=2) + '\n')


def fan_faces_known_profile(case: Path):
    """An exhaust fan carrying a known two-band profile through both ends of its zone, settled (see the list above)."""
    rng = np.random.default_rng(53)
    d_outer, d_hub = 50.0, 20.0
    meta = {'name': 'fan-faces-known-profile', 'solver': 'chtMultiRegionSimpleFoam (OpenFOAM v2512)', 'ambient_c': 25.0,
            'domain_mm': [[-50, -50, 0], [130, 130, 170]], 'base_cell_mm': 8.0, 'iterations': 100,
            'ground': 'adiabatic no-slip floor (a table)', 'solids': [], 'walls': [{'name': 'box', 'cell_mm': 2.0}],
            'contacts': [], 'fans': [{'name': 'fan', 'centre_mm': [40, 40, 60], 'axis': [0, 0, 1], 'd_outer_mm': d_outer,
                                      'd_hub_mm': d_hub, 'dp0_pa': 20.0, 'q_free_m3h': 30.0, 'q_free_cfm': 17.7,
                                      'note': 'exhaust fan, the box\'s only way out', 'model': 'actuator disc, linear fan curve'}],
            'porous': [{'name': 'heater', 'lo_mm': [20, 20, 24], 'hi_mm': [60, 60, 44], 'd': [2e5, 2e5, 2e5], 'f': [0, 0, 0],
                        'e1': [1, 0, 0], 'e2': [0, 1, 0], 'heat_w': 50.0, 'ha_w_k': None, 'fin_temperature_c': None,
                        'target_w': 50.0, 'note': 'evenly heated block'}],
            'heat_input_w': 50.0, 'limits': LIMITS}
    # each half of the annulus (by area) as 12 faces of equal area and flux: phi in kg/s, T in K
    area = math.pi / 4 * ((d_outer / 1000) ** 2 - (d_hub / 1000) ** 2)
    faces = [(0.001 / 12, T0 + 30.0)] * 12 + [(0.003 / 12, T0 + 40.0)] * 12
    phi_sum = sum(p for p, _ in faces)                                         # 0.004 kg/s
    t_weighted = sum(p * t for p, t in faces) / phi_sum                         # 310.65 K, 37.5 °C
    t_volume = T0 + (30.0 + 40.0) / 2                                           # equal volumes: 35.0 °C
    rho = 1e5 / (8314.462618 / 28.96 * (25 + T0))
    uz = phi_sum / (rho * area)                                                 # the zone's mean axial velocity
    pp = case / 'postProcessing' / 'domain0'
    solver_info(pp / 'residuals' / '0' / 'solverInfo.dat', [(t, residuals(rng, t, [], 20)) for t in range(1, 101)])
    ts = range(10, 101, 10)
    vol_field(pp / 'zone_fan' / '0' / 'volFieldValue.dat', 'cellZone fan', 'volAverage(U)\tvolAverage(T)',
              [(t, (0.0, 0.0, uz), t_volume) for t in ts], 1232, 9.9e-6)
    vol_field(pp / 'zone_heater' / '0' / 'volFieldValue.dat', 'cellZone heater', 'volAverage(U)\tvolAverage(T)',
              [(t, (0.0, 0.0, 0.8), T0 + 41.0) for t in ts], 354, 3.2e-5)
    vol_field(pp / 'T_max_domain0' / '0' / 'volFieldValue.dat', 'all domain0', 'max(T)', [(t, T0 + 48.0) for t in ts],
              70583, 5.2e-3)
    for side, zone in (('inlet', 'fanInlet'), ('outlet', 'fanOutlet')):
        surface_field(pp / f'T_{side}_fan' / '0' / 'surfaceFieldValue.dat', 'weightedAverage(T)',
                      [(t, t_weighted) for t in ts], weight=True, region=f'faceZone {zone}', faces=len(faces), area=area)
        surface_field(pp / f'mass_{side}_fan' / '0' / 'surfaceFieldValue.dat', 'sum(phi)',
                      [(t, phi_sum) for t in ts], weight=False, region=f'faceZone {zone}', faces=len(faces), area=area)
    # all the heat leaves through the fan: 0.004 kg/s x 1005 J/(kg K) x (37.5 - 25) K = 50.25 W, +0.5 % on the 50 W put in
    phi = [rng.normal(0, 2e-8) for _ in ts]
    surface_field(pp / 'flux_mass' / '0' / 'surfaceFieldValue.dat', 'sum(phi)', list(zip(ts, phi)), weight=False)
    surface_field(pp / 'flux_T' / '0' / 'surfaceFieldValue.dat', 'weightedSum(T)',
                  [(t, phi_sum * (t_weighted - (25 + T0)) + (25 + T0) * p) for t, p in zip(ts, phi)], weight=True)
    log(case / 'log.solve', 1, 100, finished=True)
    (case / 'log.topoSet').write_text('    cellZoneSet heater now size 354\n    cellZoneSet fan now size 1232\n'
                                      '    faceZoneSet fanInlet now size 24\n    faceZoneSet fanOutlet now size 24\n')
    (case / 'cadagent-case.json').write_text(json.dumps(meta, indent=2) + '\n')


DIVERGED = '--> FOAM FATAL ERROR: Maximum number of iterations exceeded'


def solids_run(case: Path, name: str, solves):
    """Air and two solids (a 5 W chip on an aluminium plate). solves: (start, last logged, finished, how it stopped), in
    the order they ran; a solve that crashed at start (last == start) leaves header-only files, and one that stopped
    within 9 iterations leaves residual rows beside header-only temperature and heat files. The first solve diverges
    after its save at 100."""
    rng = np.random.default_rng(51)
    restarts = sorted({s for s, *_ in solves[1:]})
    meta = {'name': name, 'solver': 'chtMultiRegionSimpleFoam (OpenFOAM v2512)', 'ambient_c': 25.0,
            'domain_mm': [[-40, -40, 0], [80, 80, 100]], 'base_cell_mm': 10.0, 'iterations': 300, 'ground': 'open',
            'solids': [{'name': 'chip', 'material': 'Silicon', 'k_w_mk': 120, 'power_w': 5.0, 'note': '', 'cell_mm': 1.25},
                       {'name': 'plate', 'material': 'Aluminium 6061', 'k_w_mk': 167, 'power_w': 0.0, 'note': '', 'cell_mm': 1.25}],
            'walls': [{'name': 'stand', 'cell_mm': 5.0}], 'contacts': [{'between': ['chip', 'plate'], 'thickness_mm': 0.1, 'k_w_mk': 4.0}],
            'fans': [], 'porous': [], 'heat_input_w': 5.0, 'limits': LIMITS}
    pp = case / 'postProcessing'
    for start, last, _, _ in solves:
        diverge = 115 if start == 0 else None
        solver_info(dat(pp / 'domain0' / 'residuals' / str(start), 'solverInfo', start),
                    [(t, residuals(rng, t, restarts, 60, diverge)) for t in range(start + 1, last + 1)])
        ts = list(range(start + 10, last + 1, 10))
        blow = [(25 * math.exp((t - 115) / 10) if diverge and t > 115 else 0.0) for t in ts]
        for solid, rise, tau, cells in (('chip', 60.0, 90, 1056), ('plate', 54.0, 100, 4200)):
            vol_field(dat(pp / solid / f'T_max_{solid}' / str(start), 'volFieldValue', start), f'all {solid}', 'max(T)',
                      [(t, T0 + 25 + rise * (1 - math.exp(-t / tau)) + b) for t, b in zip(ts, blow)], cells, 2.5e-7)
            vol_field(dat(pp / solid / f'T_volAverage_{solid}' / str(start), 'volFieldValue', start), f'all {solid}',
                      'volAverage(T)', [(t, T0 + 25 + 0.9 * rise * (1 - math.exp(-t / tau)) + b) for t, b in zip(ts, blow)],
                      cells, 2.5e-7)
        vol_field(dat(pp / 'domain0' / 'T_max_domain0' / str(start), 'volFieldValue', start), 'all domain0', 'max(T)',
                  [(t, T0 + 25 + 40 * (1 - math.exp(-t / 60))) for t in ts], 98000, 1.4e-3)
        phi = [rng.normal(0, 2e-8) for _ in ts]
        q = [5 * (1 - math.exp(-t / 140)) + rng.normal(0, 0.05) for t in ts]
        surface_field(dat(pp / 'domain0' / 'flux_mass' / str(start), 'surfaceFieldValue', start), 'sum(phi)',
                      list(zip(ts, phi)), weight=False)
        surface_field(dat(pp / 'domain0' / 'flux_T' / str(start), 'surfaceFieldValue', start), 'weightedSum(T)',
                      [(t, qq / CP + (25 + T0) * p) for t, qq, p in zip(ts, q, phi)], weight=True)
    for i, (start, last, finished, crash) in enumerate(solves):
        log(case / ('log.solve' if i == 0 else f'log.solve.{1793000000 + i}'), start + 1, last, finished, crash=crash)
    (case / 'cadagent-case.json').write_text(json.dumps(meta, indent=2) + '\n')


def solids_ended_early(case: Path):
    solids_run(case, 'solids-ended-early', [(0, 150, False, DIVERGED), (100, 200, True, ''), (200, 236, False, '')])


def solids_continued_again(case: Path):
    solids_run(case, 'solids-continued-again', [(0, 150, False, DIVERGED), (100, 200, True, ''), (200, 236, False, ''),
                                                (200, 300, True, '')])


def solids_crashed_restart(case: Path):
    solids_run(case, 'solids-crashed-restart', [(0, 150, False, DIVERGED),
                                                (100, 100, False, '--> FOAM FATAL ERROR: Floating point exception')])


def solids_short_continuation(case: Path):
    solids_run(case, 'solids-short-continuation', [(0, 150, False, DIVERGED), (100, 104, False, DIVERGED)])


def solids_one_step_continuation(case: Path):
    solids_run(case, 'solids-one-step-continuation', [(0, 150, False, DIVERGED),
                                                      (100, 101, False, '--> FOAM FATAL ERROR: Floating point exception')])


if __name__ == '__main__':
    for name, make in (('fins-no-solids', fins_no_solids), ('solids-ended-early', solids_ended_early),
                       ('solids-continued-again', solids_continued_again), ('solids-crashed-restart', solids_crashed_restart),
                       ('solids-short-continuation', solids_short_continuation),
                       ('solids-one-step-continuation', solids_one_step_continuation),
                       ('fins-block-drifting', fins_block_drifting), ('fan-faces-known-profile', fan_faces_known_profile)):
        shutil.rmtree(HERE / name, ignore_errors=True)
        (HERE / name).mkdir()
        make(HERE / name)
        print('wrote', HERE / name)
