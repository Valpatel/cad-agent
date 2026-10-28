import json
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.view import _read_stl, _write_stl, export_view


def tetra(path, ascii=False):
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 0], [0, 1, 0], [0, 0, 1]],
                    [[0, 0, 0], [0, 0, 1], [1, 0, 0]], [[1, 0, 0], [0, 0, 1], [0, 1, 0]]], dtype=np.float32) * 10
    if ascii:
        lines = ['solid t'] + [f'facet normal 0 0 0\nouter loop\n' + '\n'.join(f'vertex {x} {y} {z}' for x, y, z in t)
                               + '\nendloop\nendfacet' for t in tri] + ['endsolid t']
        path.write_text('\n'.join(lines))
    else:
        _write_stl(path, tri)
    return tri


def project(tmp_path, view):
    return SimpleNamespace(root=tmp_path, exports_dir=tmp_path / 'exports', title='T', part_ids={}, view=view)


@pytest.mark.parametrize('ascii', [False, True])
def test_stl_round_trip(tmp_path, ascii):
    tri = tetra(tmp_path / 'a.stl', ascii)
    assert np.allclose(_read_stl(tmp_path / 'a.stl'), tri)


def test_stl_extras_offset_category_hidden_and_skipped(tmp_path):
    tetra(tmp_path / 'board.stl')
    tetra(tmp_path / 'fan.stl', ascii=True)
    r = export_view(project(tmp_path, {
        'parts': False,
        'extra': [{'name': 'board', 'file': 'board.stl', 'offset': [15, 15, 20], 'category': 'Carrier', 'hidden': True},
                  {'name': 'fan', 'file': 'fan.stl', 'category': 'Cooler', 'color': '#111111'},
                  {'name': 'vendor', 'file': 'missing.stl', 'category': 'Carrier'}]}))
    assert r['parts'] == 2 and r['skipped'] == ['vendor']
    m = json.loads((tmp_path / 'exports/view/view.json').read_text())
    board, fan = m['parts']
    assert board['bounds_mm'] == [15, 15, 20, 25, 25, 30] and board['visible'] is False and board['category'] == 'Carrier'
    assert fan['visible'] is True and fan['category'] == 'Cooler' and fan['color'] == '#111111'
    assert np.allclose(_read_stl(tmp_path / 'exports/view/board.stl').reshape(-1, 3).min(axis=0), [15, 15, 20])


def test_duplicate_names_rejected_before_writing(tmp_path):
    from cadagent.project import CadConfigError
    tetra(tmp_path / 'a.stl')
    with pytest.raises(CadConfigError):
        export_view(project(tmp_path, {'parts': False, 'extra': [{'name': 'a', 'file': 'a.stl'}, {'glob': '*.stl'}]}))
    assert not (tmp_path / 'exports/view').exists()


def test_categories_by_name(tmp_path):
    from cadagent.project import CadConfigError
    tetra(tmp_path / 'a.stl')
    tetra(tmp_path / 'b.stl')
    view = {'parts': False, 'extra': [{'glob': '*.stl', 'category': 'Parts'}], 'categories': {'Coupons': ['b']}}
    export_view(project(tmp_path, view))
    m = json.loads((tmp_path / 'exports/view/view.json').read_text())
    assert [(p['name'], p['category']) for p in m['parts']] == [('a', 'Parts'), ('b', 'Coupons')]
    with pytest.raises(CadConfigError):
        export_view(project(tmp_path, dict(view, categories={'Coupons': ['typo']})))
