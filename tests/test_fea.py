"""The stiffness/strength solver against textbook answers: a cantilever and a twisted round shaft."""
import math

import pytest

cq = pytest.importorskip('cadquery')
pytest.importorskip('gmsh')
pytest.importorskip('skfem')

from cadagent.fea import Material, Study, plane_at  # noqa: E402

STEEL = Material('steel', 200000, 0.3, 250, 7.85)


def test_cantilever_tip_deflection_and_root_stress():
    L, b, h, F = 100.0, 10.0, 10.0, 100.0
    st = Study(cq.Workplane('XY').box(L, b, h).translate((L / 2, 0, 0)), STEEL, mesh_mm=4.0, name='beam')
    st.fix(plane_at(0, 0.0)).force(plane_at(0, L), (0, 0, -F))
    r = st.solve()
    I = b * h ** 3 / 12
    tip = F * L ** 3 / (3 * STEEL.E_mpa * I) + F * L / (STEEL.E_mpa / 2.6 * b * h * 5 / 6)
    assert r['probe_displacement_mm'][2] == pytest.approx(-tip, rel=0.03)
    assert r['von_mises_design_mpa'] == pytest.approx(F * L * (h / 2) / I, rel=0.08)
    assert r['stiffness_n_per_mm'] == pytest.approx(F / tip, rel=0.03)


def test_shaft_torsional_stiffness():
    r0, L, T = 10.0, 100.0, 50.0
    st = Study(cq.Workplane('YZ').circle(r0).extrude(L), STEEL, mesh_mm=3.0, name='shaft')
    st.fix(plane_at(0, 0.0)).torque(plane_at(0, L), (L, 0, 0), (1, 0, 0), T)
    r = st.solve()
    J, G = math.pi * r0 ** 4 / 2, STEEL.E_mpa / 2.6
    k = T / math.degrees(T * 1000 * L / (G * J))
    assert r['torsional_stiffness_nm_per_deg'] == pytest.approx(k, rel=0.04)
    assert r['von_mises_design_mpa'] == pytest.approx(math.sqrt(3) * T * 1000 * r0 / J, rel=0.1)


@pytest.mark.parametrize('load', [100.0, 2000.0])          # safety factor above 1, and failing below the design load
def test_overload_animation(tmp_path, load):
    L, b, h = 100.0, 10.0, 10.0
    st = Study(cq.Workplane('XY').box(L, b, h).translate((L / 2, 0, 0)), STEEL, mesh_mm=5.0, name='beam')
    st.fix(plane_at(0, 0.0)).force(plane_at(0, L), (0, 0, -load))
    st.solve()
    out = st.animate(tmp_path / 'beam.gif', frames=12, fps=4)
    assert out.exists() and out.stat().st_size > 1000


def test_export_viewer(tmp_path):
    """The interactive viewer's data: arrays decode and agree, the hot spot is at the clamped root, loads and the
    overload curve are there."""
    import base64
    import json

    import numpy as np

    L, b, h, F = 100.0, 10.0, 10.0, 100.0
    st = Study(cq.Workplane('XY').box(L, b, h).translate((L / 2, 0, 0)), STEEL, mesh_mm=4.0, name='beam')
    st.fix(plane_at(0, 0.0)).force(plane_at(0, L), (0, 0, -F))
    r = st.solve()
    out = st.export_viewer(tmp_path / 'beam.json')
    assert out.exists() and out.stat().st_size < 2_000_000
    d = json.loads(out.read_text())
    assert d['format'] == 'cadagent-fea-viewer'
    s = d['surface']

    def arr(a):
        x = np.frombuffer(base64.b64decode(a['b64']), dtype=a['dtype'])
        return x.reshape(a['shape'])

    P, I, U = arr(s['positions']), arr(s['index']), arr(s['displacement'])
    vm, tvm, fl = arr(s['von_mises']), arr(s['tri_von_mises']), arr(s['flags'])
    nv, nt = s['vertices'], s['triangles']
    assert P.shape == (nv, 3) and U.shape == (nv, 3) and vm.shape == (nv,) and fl.shape == (nv,)
    assert I.shape == (nt, 3) and tvm.shape == (nt,) and I.max() == nv - 1 and I.min() == 0
    # a closed, outward-wound surface: the divergence theorem gives the box's volume
    a, bb, c = P[I[:, 0]].astype(float), P[I[:, 1]].astype(float), P[I[:, 2]].astype(float)
    assert np.einsum('ij,ij->i', a, np.cross(bb, c)).sum() / 6 == pytest.approx(L * b * h, rel=1e-3)
    # the held root face is flagged, the tip moves down by the solved amount
    assert np.all(fl[np.isclose(P[:, 0], 0.0, atol=1e-6)] & 1)
    assert U[:, 2].min() == pytest.approx(-np.linalg.norm(st.disp, axis=0).max(), rel=0.02)
    # failure: the first failure is at the safety factor, the hottest spot is near the root and fails there
    f = d['failure']
    assert f['first_failure_factor'] == pytest.approx(r['safety_factor'], rel=0.01)
    hs = d['hot_spots']
    assert 1 <= len(hs) <= 8
    assert hs[0]['position'][0] < 0.25 * L
    assert hs[0]['fails_at'] == pytest.approx(f['first_failure_factor'], rel=1e-3)
    assert all(np.linalg.norm(np.subtract(p['position'], q['position'])) >= 4 * st.mesh_mm - 1e-9
               for i, p in enumerate(hs) for q in hs[i + 1:])
    assert hs[0]['hint']
    # the share of the volume past the strength grows with the load
    ys = f['curve']['share']
    assert ys[0] == 0 and ys[-1] > 0 and all(y1 >= y0 for y0, y1 in zip(ys, ys[1:]))
    assert f['overstressed_volume']['at_1.25x_first_failure'] > 0
    ld = d['loads'][0]
    assert ld['kind'] == 'force' and ld['n'] == pytest.approx(F) and ld['origin'][0] == pytest.approx(L)
