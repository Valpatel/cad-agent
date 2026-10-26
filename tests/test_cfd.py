"""cadagent.cfd writes a complete OpenFOAM case; running it needs OpenFOAM (or Docker) and is opt-in."""

from __future__ import annotations

import json
import os
import shutil

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
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


def test_fan_source_gives_its_curve():
    f = Fan('f', centre=(0, 0, 0), axis=(0, 0, -2), d_outer=76, d_hub=33, thickness=6, dp0_pa=15.2, q_free_m3h=38.9)
    F, c = f.source()
    t = 0.006
    assert np.allclose(F / np.linalg.norm(F), (0, 0, -1))
    assert np.linalg.norm(F) * t == pytest.approx(15.2)              # pressure rise at zero flow
    v_free = 38.9 / 3600 / f.area_m2
    assert (np.linalg.norm(F) - c * v_free) * t == pytest.approx(0, abs=1e-9)   # none at the free-air flow


def test_case_files(tmp_path):
    d = small_case().write(tmp_path / 'case', np_procs=2)
    for rel in ('Allrun', 'system/blockMeshDict', 'system/snappyHexMeshDict', 'constant/regionProperties',
                'system/domain0/fvOptions', 'system/domain0/topoSetDict', 'system/chip/fvOptions', '0/domain0/U', '0/plate/T'):
        assert (d / rel).exists(), rel
    rp = (d / 'constant/regionProperties').read_text()
    assert 'fluid (domain0)' in rp and 'solid (chip plate)' in rp
    snappy = (d / 'system/snappyHexMeshDict').read_text()
    assert 'cellZone chip' in snappy and 'cellZoneInside inside' in snappy
    assert 'explicitPorositySource' in (d / 'system/domain0/fvOptions').read_text()
    assert 'thicknessLayers (0.0001)' in (d / '0/chip/T').read_text()
    meta = json.loads((d / 'cadagent-case.json').read_text())
    assert meta['fans'][0]['q_free_cfm'] == pytest.approx(20 / 1.699, abs=0.05)
    assert any('radiation' in s for s in meta['limits'])


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
    assert res['fans']['fan']['flow_m3h'] > 0
