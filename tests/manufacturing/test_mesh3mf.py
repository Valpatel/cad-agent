"""3MF writer + read-back verification, on hand-built meshes (numpy only)."""

from __future__ import annotations

import sys
import zipfile

import numpy as np
import pytest

from cadagent import MissingDependency
from cadagent.manufacturing import mesh3mf

def cube(size=10.0, origin=(0.0, 0.0, 0.0)):
    v = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=float,
    ) * size + np.array(origin)
    # outward-facing, counter-clockwise seen from outside
    f = np.array(
        [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
         [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]],
        dtype=np.int64,
    )
    return v, f

def test_cube_reference_mesh_is_closed_with_its_true_volume():
    v, f = cube(10)
    assert mesh3mf.is_edge_manifold(f)
    assert mesh3mf.mesh_volume(v, f) == pytest.approx(1000.0)

def test_same_mesh_gives_the_same_bytes(tmp_path, monkeypatch):
    import hashlib, time
    v, f = cube(10)
    a, b = tmp_path / "a.3mf", tmp_path / "b.3mf"
    mesh3mf.write_3mf(a, v, f, "cube", bed_xy=(256, 256))
    monkeypatch.setattr(time, "time", lambda: 2_000_000_000.0)          # a later write time
    monkeypatch.setattr(time, "localtime", lambda *_: time.struct_time((2033, 5, 18, 3, 33, 20, 2, 138, 0)))
    mesh3mf.write_3mf(b, v, f, "cube", bed_xy=(256, 256))
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    import zipfile
    for info in zipfile.ZipFile(b).infolist():
        assert (info.date_time, info.create_system, info.external_attr >> 16) == ((1980, 1, 1, 0, 0, 0), 3, 0o100644)


def test_cube_round_trip_is_centred_on_the_bed_and_verified(tmp_path):
    v, f = cube(10, origin=(-40, 7, 3))
    out = tmp_path / "cube.3mf"
    report = mesh3mf.write_3mf(out, v, f, "cube", bed_xy=(256, 256))
    assert report["ok"] and report["watertight"]
    assert report["triangles"] == report["source_triangles"] == 12
    assert report["volume_mm3"] == pytest.approx(1000.0, rel=1e-6)

    back_v, back_f = mesh3mf.read_3mf(out)
    assert len(back_f) == 12
    lo, hi = back_v.min(axis=0), back_v.max(axis=0)
    assert (lo[:2] + hi[:2]) / 2 == pytest.approx([128, 128])
    assert lo[2] == pytest.approx(0.0)
    assert hi - lo == pytest.approx([10, 10, 10])
    with zipfile.ZipFile(out) as z:
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= set(z.namelist())

def test_part_name_is_escaped_in_the_model_xml(tmp_path):
    v, f = cube(5)
    out = tmp_path / "odd.3mf"
    mesh3mf.write_3mf(out, v, f, 'a<b & "c"', bed_xy=(200, 200))
    assert len(mesh3mf.read_3mf(out)[1]) == 12

@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f[:-1],                                    # hole: one face missing
        lambda f: np.vstack([f[:-1], f[-1][::-1][None]]),    # one face flipped
        lambda f: np.vstack([f, f[:1]]),                     # duplicated face
    ],
    ids=["open", "flipped", "duplicate"],
)
def test_non_manifold_meshes_are_detected(mutate):
    _, f = cube()
    assert not mesh3mf.is_edge_manifold(mutate(f))

def test_open_mesh_is_refused_and_no_file_is_left_behind(tmp_path):
    v, f = cube()
    out = tmp_path / "open.3mf"
    with pytest.raises(mesh3mf.Mesh3mfError):
        mesh3mf.write_3mf(out, v, f[:-1], "open", bed_xy=(256, 256))
    assert not out.exists()

def test_export_without_trimesh_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "trimesh", None)
    with pytest.raises(MissingDependency, match="trimesh"):
        mesh3mf.export_parts_3mf(tmp_path, ["x"], (256, 256))
