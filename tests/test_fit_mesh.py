"""fit_mesh: an STL over its face budget comes back under it, and one under the budget is left alone."""
import pytest

cq = pytest.importorskip('cadquery')
pytest.importorskip('vtk')

from cadagent.sim.robot import fit_mesh, stl_faces  # noqa: E402


def test_fit_mesh_decimates_under_the_budget(tmp_path):
    f = tmp_path / 'sphere.stl'
    cq.exporters.export(cq.Workplane('XY').sphere(20), str(f), tolerance=0.01, angularTolerance=0.05)
    n0 = stl_faces(f)
    assert n0 > 4000
    n = fit_mesh(f, 2000)
    assert 0 < n <= 2000
    assert stl_faces(f) == n


def test_fit_mesh_leaves_small_meshes(tmp_path):
    f = tmp_path / 'box.stl'
    cq.exporters.export(cq.Workplane('XY').box(10, 10, 10), str(f))
    before = f.read_bytes()
    assert fit_mesh(f, 2000) == stl_faces(f)
    assert f.read_bytes() == before
