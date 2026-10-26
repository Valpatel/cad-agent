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
