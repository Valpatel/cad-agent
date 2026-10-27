"""Slicer profile flattening (the slicer itself is only run where it is installed)."""

from __future__ import annotations

import json

import pytest

from cadagent import slicer


def test_flatten_merges_the_inheritance_chain(tmp_path, monkeypatch):
    root = tmp_path / 'BBL'
    for kind in ('machine', 'process', 'filament'):
        (root / kind).mkdir(parents=True)
    (root / 'filament/base.json').write_text(json.dumps({'name': 'fdm_base', 'filament_density': ['1.24'], 'a': 1}))
    (root / 'filament/mid.json').write_text(json.dumps({'name': 'mid', 'inherits': 'fdm_base', 'a': 2, 'b': 3}))
    (root / 'filament/top.json').write_text(json.dumps({'name': 'PLA top', 'inherits': 'mid', 'b': 4}))
    monkeypatch.setattr(slicer, '_PROFILE_ROOTS', [root])
    d = slicer.flatten('filament', 'PLA top')
    assert d['filament_density'] == ['1.24'] and d['a'] == 2 and d['b'] == 4
    assert 'inherits' not in d and d['filament_settings_id'] == ['PLA top'] and d['from'] == 'system'
    with pytest.raises(KeyError):
        slicer.flatten('filament', 'missing')


@pytest.mark.skipif(slicer.executable() is None, reason='Bambu Studio not installed')
def test_slices_a_cube(tmp_path):
    trimesh = pytest.importorskip('trimesh')
    work = __import__('pathlib').Path.home() / 'snap' / 'bambu-studio' / 'common' / 'cadagent-test'  # the snap cannot read /tmp
    work.mkdir(parents=True, exist_ok=True)
    stl = work / 'cube.stl'
    trimesh.creation.box(extents=(20, 20, 20)).apply_translation((0, 0, 10)).export(str(stl))
    r = slicer.slice_part(stl, workdir=work / 'out')
    assert 2.5 < r['grams'] < 6


def test_work_folder_guard_and_partial_reslice(tmp_path, monkeypatch):
    import pathlib
    from tests.test_report import make_project
    from cadagent.project import load_project
    monkeypatch.setattr(slicer, 'executable', lambda: '/bin/false')
    monkeypatch.setattr(slicer, 'flatten', lambda kind, name: {'name': name})
    model = tmp_path / 'm.3mf'
    model.write_text('x')
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'mine.txt').write_text('keep')
    with pytest.raises(FileExistsError):
        slicer.slice_part(model, workdir=work)
    assert (work / 'mine.txt').exists()
    slicer.slice_part(model, workdir=tmp_path / 'w2')      # a crashed slice still leaves the marker...
    slicer.slice_part(model, workdir=tmp_path / 'w2')      # ...so it can be redone
    root = make_project(tmp_path / 'proj')
    project = load_project(root)
    grams = {'box': 5.0, 'lid': 7.0}
    monkeypatch.setattr(slicer, 'slice_part', lambda m, **kw: {'grams': grams[pathlib.Path(m).stem], 'minutes': 10.0})
    full = slicer.slice_project(project)
    assert set(full['parts']) == {'box', 'lid'} and full['total_grams'] == 12.0
    grams['box'] = 4.0
    part = slicer.slice_project(project, ['box'])
    assert set(part['parts']) == {'box', 'lid'} and part['total_grams'] == 11.0
