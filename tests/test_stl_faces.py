"""stl_faces needs no optional dependencies: binary and ASCII STLs, the header pitfalls, truncated files."""
import struct

import pytest

from cadagent.robot import fit_mesh, stl_faces

TRI = struct.pack('<12fH', *([0.0] * 3), 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)


def binary(path, n, header=b'', count=None):
    path.write_bytes(header.ljust(80, b' ')[:80] + struct.pack('<I', n if count is None else count) + TRI * n)
    return path


def ascii_stl(path, n, keyword='facet normal', name='part'):
    facet = f'  {keyword} 0 0 1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n    endloop\n  end{keyword.split()[0]}\n'
    path.write_text(f'solid {name}\n' + facet * n + f'endsolid {name}\n')
    return path


def test_binary(tmp_path):
    assert stl_faces(binary(tmp_path / 'b.stl', 3)) == 3


def test_binary_header_that_looks_ascii(tmp_path):
    assert stl_faces(binary(tmp_path / 'b.stl', 3, header=b'solid exported facet normal')) == 3


def test_binary_with_a_zero_count_field(tmp_path):
    assert stl_faces(binary(tmp_path / 'b.stl', 1000, count=0)) == 1000


def test_ascii_any_case_and_whitespace(tmp_path):
    assert stl_faces(ascii_stl(tmp_path / 'a.stl', 50)) == 50
    assert stl_faces(ascii_stl(tmp_path / 'u.stl', 50, keyword='FACET NORMAL')) == 50
    assert stl_faces(ascii_stl(tmp_path / 't.stl', 2, keyword='facet\tnormal')) == 2
    assert stl_faces(ascii_stl(tmp_path / 'l.stl', 2, name='x' * 3000)) == 2


def test_truncated_binary_raises_and_fit_mesh_leaves_it(tmp_path):
    f = binary(tmp_path / 'b.stl', 10)
    f.write_bytes(f.read_bytes()[:84 + 50 * 2])
    before = f.read_bytes()
    with pytest.raises(ValueError):
        stl_faces(f)
    with pytest.raises(ValueError):
        fit_mesh(f, 1)
    assert f.read_bytes() == before


def test_fit_mesh_rejects_a_zero_budget(tmp_path):
    with pytest.raises(ValueError):
        fit_mesh(binary(tmp_path / 'b.stl', 3), 0)
