"""cadagent.cfd writes a complete OpenFOAM case; running it needs OpenFOAM (or Docker) and is opt-in."""

from __future__ import annotations

import json
import re
import os
import shutil

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
from cadagent import cfd  # noqa: E402
from cadagent.cfd import SOLIDS, Fan, ThermalCase  # noqa: E402


def box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return trimesh.creation.box(extents=hi - lo, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))


def small_case(fan=True, porous=True):
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10, iterations=30)
    c.wall('stand', box((0, 0, 0), (40, 40, 10)), level=1)
    c.solid('chip', box((10, 10, 10), (30, 30, 14)), SOLIDS['silicon'], power_w=5, level=2)
    c.solid('plate', box((5, 5, 14), (35, 35, 18)), SOLIDS['al6061'], level=2)
    c.contact('chip', 'plate', 0.1, 4.0)
    if porous:
        c.porous_box('fins', (5, 5, 18), (35, 35, 30), d=(1e6, 1e9, 1e6), f=(10, 0, 10), heat_w=2)
    if fan:
        c.fan(Fan('fan', centre=(20, 20, 40), axis=(0, 0, -1), d_outer=30, d_hub=10, thickness=4, dp0_pa=20, q_free_m3h=20))
    return c


def test_fan_source_gives_its_curve_whatever_the_zone_thickness():
    f = Fan('f', centre=(0, 0, 0), axis=(0, 0, -2), d_outer=76, d_hub=33, thickness=6, dp0_pa=15.2, q_free_m3h=38.9)
    F, c = f.source()                              # zone totals: N and kg/s
    assert np.allclose(F / np.linalg.norm(F), (0, 0, -1))
    assert np.linalg.norm(F) / f.area_m2 == pytest.approx(15.2)     # pressure rise at zero flow, independent of thickness
    v_free = 38.9 / 3600 / f.area_m2
    assert (np.linalg.norm(F) - c * v_free) / f.area_m2 == pytest.approx(0, abs=1e-9)   # none at the free-air flow


def test_exchanger_terms_are_ha_times_the_difference():
    ex, im = cfd.exchanger_terms(2.5, 50.0)
    # S = ex + im * hs with hs = cp (T - 298.15): at T = T_fin no heat, at T = 25 C 2.5 W/K x 25 K
    hs = lambda t_c: cfd.AIR_CP * (t_c + 273.15 - 298.15)
    assert ex + im * hs(50.0) == pytest.approx(0, abs=1e-9)
    assert ex + im * hs(25.0) == pytest.approx(2.5 * 25.0)


def test_case_files(tmp_path):
    d = small_case().write(tmp_path / 'case', np_procs=2)
    for rel in ('Allrun', 'system/blockMeshDict', 'system/snappyHexMeshDict', 'constant/regionProperties',
                'system/domain0/fvOptions', 'system/domain0/topoSetDict', 'system/chip/fvOptions', '0/domain0/U', '0/plate/T'):
        assert (d / rel).exists(), rel
    rp = (d / 'constant/regionProperties').read_text()
    assert 'fluid (domain0)' in rp and 'solid (chip plate)' in rp
    snappy = (d / 'system/snappyHexMeshDict').read_text()
    assert 'cellZone chip' in snappy and 'cellZoneInside inside' in snappy
    assert 'locationInMesh (' in snappy and 'locationsInMesh' not in snappy
    fz = (d / 'system/topoSetDict.fluidZone').read_text()
    assert 'zones (chip plate)' in fz and re.search(r'name domain0; type cellZoneSet', fz), 'the air is a named zone, not numbered by the split'
    allrun = (d / 'Allrun').read_text()
    assert allrun.index('topoSetDict.fluidZone') < allrun.index('splitMeshRegions') < allrun.index('regions this case does not define')
    assert 'explicitPorositySource' in (d / 'system/domain0/fvOptions').read_text()
    assert 'thicknessLayers (0.0001)' in (d / '0/chip/T').read_text()
    meta = json.loads((d / 'cadagent-case.json').read_text())
    assert meta['fans'][0]['q_free_cfm'] == pytest.approx(20 / 1.699, abs=0.05)
    assert any('radiation' in s for s in meta['limits'])
    assert meta['heat_input_w'] == pytest.approx(5 + 2)
    # still room air must stay still: p_rgh uniform on the open boundary (hydrostatic static pressure)
    prgh = (d / '0/domain0/p_rgh').read_text()
    assert 'ambient { type totalPressure;' in prgh and 'prghTotalPressure' not in prgh
    opts = (d / 'system/domain0/fvOptions').read_text()
    assert opts.count('volumeMode absolute') >= 2 and 'volumeMode specific' not in opts
    assert 'alphatJayatillekeWallFunction' in (d / '0/domain0/alphat').read_text()


def test_contacts_must_name_solids(tmp_path):
    c = small_case()
    c.contact('chip', 'plat', 0.1, 4.0)
    with pytest.raises(ValueError, match='solid regions'):
        c.write(tmp_path / 'case', np_procs=2)


def test_write_never_wipes_a_foreign_folder(tmp_path):
    keep = tmp_path / 'project'
    keep.mkdir()
    (keep / 'important.txt').write_text('x')
    with pytest.raises(FileExistsError):
        small_case().write(keep, np_procs=2)
    assert (keep / 'important.txt').exists()
    d = small_case().write(tmp_path / 'case', np_procs=2)
    small_case().write(d, np_procs=2)              # its own case folder may be rewritten


def _fake_results(d, rows_T, rows_m, last_log_end=True, zone_size=100):
    pp = d / 'postProcessing' / 'domain0'
    for t0, rows in rows_T.items():
        f = pp / 'flux_T' / str(t0) / 'surfaceFieldValue.dat'
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('# Time  weightedSum(T)\n' + ''.join(f'{t}\t{v}\n' for t, v in rows))
    for t0, rows in rows_m.items():
        f = pp / 'flux_mass' / str(t0) / 'surfaceFieldValue.dat'
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('# Time  sum(phi)\n' + ''.join(f'{t}\t{v}\n' for t, v in rows))
    (d / 'log.solve').write_text('...\nEnd\n')
    import time
    time.sleep(0.01)
    (d / 'log.solve.2').write_text('...\nEnd\n' if last_log_end else '...\nFOAM FATAL ERROR\n')
    (d / 'log.topoSet').write_text(f'cellZoneSet fins now size {zone_size}\ncellZoneSet fan now size 50\n')


def test_read_results_heat_balance_restarts_and_empty_files(tmp_path):
    c = small_case()
    d = c.write(tmp_path / 'case', np_procs=2)
    t_amb = 25 + 273.15
    # mass in = mass out (sum phi = 0); 7 W leave: cp sum(phi T) = 7 -> sum(phi T) = 7 / cp
    rows = [(i, 7.0 / cfd.AIR_CP) for i in range(10, 310, 10)]
    _fake_results(d, {0: rows, 300: []}, {0: [(t, 0.0) for t, _ in rows], 300: []})
    r = c.results(d)
    assert r['heat_out_w'] == pytest.approx(7.0, abs=0.01)
    assert r['energy_balance_pct'] == pytest.approx(0.0, abs=0.1)
    assert r['solver_finished'] is True and r['solver_log'] == 'log.solve.2'
    assert r['zone_cells'] == {'fins': 100, 'fan': 50}
    _fake_results(d, {0: rows}, {0: [(t, 0.0) for t, _ in rows]}, last_log_end=False, zone_size=0)
    r = c.results(d)
    assert r['solver_finished'] is False and 'empty zone' in r['error'] and r['converged'] is False


def test_calibrate_fins_targets_the_block_and_steps_by_secant(tmp_path, monkeypatch):
    # a 40 W solid plus an exchanger block (hA 1 W/K) that must deliver 20 W; in the fake solver the block's air sits at
    # 25 + 0.2 (T_fin - 25), so the block gives 0.8 (T_fin - 25) W and needs T_fin = 50 C
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10)
    c.solid('chip', box((10, 10, 10), (30, 30, 14)), SOLIDS['silicon'], power_w=40)
    c.porous_box('fins', (5, 5, 18), (35, 35, 30), d=(1e6, 1e9, 1e6), f=(0, 0, 0), ha_w_k=1.0, fin_temperature_c=35.0, target_w=20.0)
    d = c.write(tmp_path / 'case', np_procs=2)
    state = {'tfin': 35.0}

    def fake_read(case_dir, case=None):
        t_block = 25.0 + 0.2 * (state['tfin'] - 25.0)
        return {'zones': {'fins': {'T_c': t_block}}, 'heat_out_w': 40.0 + (state['tfin'] - t_block), 'solver_finished': True,
                'convergence': {'fins_T_change_c': 0.1, 'fan_intake_c_change': 0.0}}

    def fake_run(cmd, **kw):
        state['tfin'] = c.porous[0]['fin_temperature_c']
        return type('R', (), {'returncode': 0})()

    monkeypatch.setattr(cfd, 'read_results', fake_read)
    monkeypatch.setattr(cfd.subprocess, 'run', fake_run)
    res = c.calibrate_fins(d)
    assert res['calibrated'] is True and res['block_heat_w'] == pytest.approx(20.0, rel=0.03)
    assert c.porous[0]['fin_temperature_c'] == pytest.approx(50.0, abs=0.8)


def test_fin_temperature_must_start_above_the_room():
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), ambient_c=25)
    with pytest.raises(ValueError, match='above the room'):
        c.porous_box('fins', (0, 0, 0), (1, 1, 1), d=(1, 1, 1), f=(0, 0, 0), ha_w_k=1.0, fin_temperature_c=25.0)


def test_air_only_case_moves_the_mesh_into_the_region(tmp_path):
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10)
    c.wall('stand', box((0, 0, 0), (40, 40, 10)))
    c.porous_box('fins', (5, 5, 10), (35, 35, 20), d=(1e6, 1e9, 1e6), f=(0, 0, 0), heat_w=2)
    d = c.write(tmp_path / 'case', np_procs=2)
    assert 'splitMeshRegions' not in (d / 'Allrun').read_text()
    assert 'constant/domain0' in (d / 'Allrun').read_text()


def test_open_solids_are_rejected():
    m = box((0, 0, 0), (1, 1, 1))
    m.faces = m.faces[:-2]
    with pytest.raises(ValueError, match='closed surface'):
        ThermalCase('t', domain=((-5, -5, -5), (5, 5, 5))).solid('x', m, SOLIDS['copper'])


@pytest.mark.skipif(os.environ.get('CADAGENT_RUN_CFD') != '1' or not (shutil.which('docker') or shutil.which('chtMultiRegionSimpleFoam')),
                    reason='set CADAGENT_RUN_CFD=1 with OpenFOAM or Docker to run a real case')
def test_small_case_runs(tmp_path):
    c = small_case()
    d = c.write(tmp_path / 'case', np_procs=2)
    assert c.run(d) == 0
    res = c.results(d)
    assert res['solids']['chip']['max_c'] > res['ambient_c']
    assert 0 < res['fans']['fan']['flow_m3h'] < 20


@pytest.mark.skipif(os.environ.get('CADAGENT_RUN_CFD') != '1' or not (shutil.which('docker') or shutil.which('chtMultiRegionSimpleFoam')),
                    reason='set CADAGENT_RUN_CFD=1 with OpenFOAM or Docker to run a real case')
def test_still_room_stays_still(tmp_path):
    # no heat, no fan: the open boundary must not drive a draft (it did with a uniform static pressure)
    c = ThermalCase('still', domain=((-60, -60, 0), (100, 100, 120)), cell_mm=10, iterations=100)
    c.wall('block', box((0, 0, 0), (40, 40, 30)), level=1)
    c.solid('cold', box((10, 10, 30), (30, 30, 34)), SOLIDS['al6061'], power_w=0.0, level=1)
    d = c.write(tmp_path / 'case', np_procs=2)
    assert c.run(d) == 0
    import pyvista as pv
    g = pv.read(sorted((d / 'VTK' / 'domain0').glob('case_*/internal.vtu'))[-1])
    u = np.linalg.norm(np.asarray(g.cell_data['U']), axis=1)
    # measured: fixed BC mean 0.009 / max 0.031 m/s (buoyancy noise on a snapped mesh); the old uniform-static-pressure
    # BC gave mean 0.62 / max 1.47 m/s on this same case
    assert float(u.mean()) < 0.02 and float(u.max()) < 0.1


def test_airflow_only_case_can_converge(tmp_path):
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10)
    c.wall('stand', box((0, 0, 0), (40, 40, 10)))
    c.fan(Fan('fan', centre=(20, 20, 40), axis=(0, 0, -1), d_outer=30, d_hub=10, thickness=4, dp0_pa=20, q_free_m3h=20))
    d = c.write(tmp_path / 'case', np_procs=2)
    rows = [(i, 0.0) for i in range(10, 310, 10)]
    _fake_results(d, {0: rows}, {0: rows})
    r = c.results(d)
    assert r['heat_input_w'] == 0 and r['energy_balance_w'] == pytest.approx(0.0) and r['converged'] is True


def test_calibrate_without_a_target_says_so(tmp_path):
    c = ThermalCase('t', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10)
    c.porous_box('fins', (5, 5, 18), (35, 35, 30), d=(1e6, 1e9, 1e6), f=(0, 0, 0), ha_w_k=1.0, fin_temperature_c=35.0)
    assert c.heat_input_w() is None
    d = c.write(tmp_path / 'case', np_procs=2)
    with pytest.raises(ValueError, match='target power'):
        c.calibrate_fins(d)


def _frame(**kw):
    # a square ring open at the top: snappy's named location (locationsInMesh) once gave its inside corners to the air
    import trimesh as tm
    c = ThermalCase('frame', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10, iterations=30, **kw)
    c.wall('stand', box((-10, -10, 0), (50, 50, 10)), level=1)
    ring = box((0, 0, 10), (40, 40, 22)).difference(box((6, 6, 9), (34, 34, 23)))
    c.solid('frame', ring, SOLIDS['al6061'], power_w=5, level=2)
    c.fan(Fan('fan', centre=(20, 20, 40), axis=(0, 0, -1), d_outer=30, d_hub=10, thickness=4, dp0_pa=20, q_free_m3h=20))
    c.refine((0, 0, 30), (40, 40, 50), 2)
    return c


@pytest.mark.skipif(os.environ.get('CADAGENT_RUN_CFD') != '1' or not (shutil.which('docker') or shutil.which('chtMultiRegionSimpleFoam')),
                    reason='set CADAGENT_RUN_CFD=1 with OpenFOAM or Docker to run a real case')
@pytest.mark.parametrize('fluid', ['domain0', 'air'])
def test_open_frame_splits_into_the_named_regions(tmp_path, fluid):
    c = _frame(fluid=fluid)
    d = c.write(tmp_path / 'case', np_procs=2)
    assert c.run(d) == 0, (d / 'log.splitMeshRegions').read_text()[-2000:]
    regions = sorted(p.name for p in (d / 'processor0' / 'constant').iterdir() if (p / 'polyMesh').is_dir())
    assert regions == sorted([fluid, 'frame'])
    assert c.results(d)['fans']['fan']['flow_m3h'] > 0


@pytest.mark.skipif(os.environ.get('CADAGENT_RUN_CFD') != '1' or not (shutil.which('docker') or shutil.which('chtMultiRegionSimpleFoam')),
                    reason='set CADAGENT_RUN_CFD=1 with OpenFOAM or Docker to run a real case')
def test_sealed_air_pocket_stops_with_a_clear_message(tmp_path):
    c = ThermalCase('pocket', domain=((-40, -40, 0), (80, 80, 100)), cell_mm=10, iterations=30)
    c.wall('stand', box((-10, -10, 0), (50, 50, 10)), level=1)
    c.solid('frame', box((0, 0, 10), (40, 40, 22)).difference(box((6, 6, 9), (34, 34, 23))), SOLIDS['al6061'], level=2)
    c.solid('lid', box((0, 0, 22), (40, 40, 26)), SOLIDS['al6061'], power_w=5, level=2)
    d = c.write(tmp_path / 'case', np_procs=2)
    assert c.run(d) == 3
    assert 'regions this case does not define' in (d / 'log.solve').read_text()
