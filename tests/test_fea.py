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
