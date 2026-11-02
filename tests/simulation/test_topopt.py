"""Topology optimisation (pyMOTO) on a small cantilever: meets the volume, stiffens as it goes, keeps what it must."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pymoto")
trimesh = pytest.importorskip("trimesh")
from cadagent.simulation.topopt import TopOpt  # noqa: E402


def test_cantilever():
    t = TopOpt((0, 0, 0), (40, 10, 10), voxel_mm=2.0)
    t.design()
    keep = trimesh.creation.box(extents=(4, 10, 10), transform=trimesh.transformations.translation_matrix((38, 5, 5)))
    t.keep(keep)
    t.fix((0, 0, 0), (0, 10, 10))
    t.load((40, 4, 0), (40, 6, 2), (0, 0, -50))
    res = t.run(volfrac=0.3, filter_mm=3.0, maxit=25)
    assert res['volfrac_result'] == pytest.approx(0.3, abs=0.02)
    assert t.log[-1]['compliance_nmm'] < t.log[0]['compliance_nmm']
    kept = t.state == 2
    assert np.all(t.density[kept] > 0.99)
    assert len(t.history) >= 2


def test_hex_vents_only_where_material_is_not_needed():
    from cadagent.simulation.topopt import hex_vents
    t = TopOpt((0, 0, 0), (60, 40, 4), voxel_mm=2.0)
    d = np.zeros(t.domain.nel).reshape(t.n[::-1])
    d[:, :, :15] = 1.0                              # x < 30 mm is needed material
    pts = hex_vents(t, d.ravel(), threshold=0.3, across_flats=8, web=2)
    assert pts and all(u - 8 / 3 ** 0.5 >= 30 - 1e-6 for u, _ in pts)
