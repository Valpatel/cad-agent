"""Slicer profile flattening (the slicer itself is only run where it is installed)."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from cadagent import slicer


@pytest.fixture
def profile_tree(tmp_path, monkeypatch):
    root = tmp_path / 'BBL'
    for kind in ('machine', 'process', 'filament'):
        (root / kind).mkdir(parents=True)
    monkeypatch.setattr(slicer, '_PROFILE_ROOTS', [root])
    return root


def write_profile(root, name, *, kind='machine', filename=None, **values):
    path = root / kind / (filename or name + '.json')
    path.write_text(json.dumps({'name': name, **values}))
    return path


def test_real_p1s_template_graph_resolves_machine_temperature_commands(profile_tree):
    fixture = Path(__file__).parent / 'fixtures/bambu_templates/profiles.json'
    profiles = json.loads(fixture.read_text())
    for filename, values in profiles.items():
        (profile_tree / 'machine' / filename).write_text(json.dumps(values))
    resolved = slicer.resolve_profile('machine', slicer.PRINTER)
    start = resolved['settings']['machine_start_gcode']
    assert 'M190 S[bed_temperature_initial_layer_single]' in start
    assert 'M109 S{nozzle_temperature_initial_layer[initial_extruder]}' in start
    assert 'M109 S205' not in start
    assert resolved['settings']['printer_settings_id'] == slicer.PRINTER
    assert not {'inherits', 'include'} & resolved['settings'].keys()
    assert set(resolved['files']) == {'machine/' + name for name in profiles}
    for name, sha in resolved['files'].items():
        assert sha == hashlib.sha256((profile_tree / name).read_bytes()).hexdigest()


def test_parent_then_ordered_recursive_includes_then_child(profile_tree):
    write_profile(profile_tree, 'base', common='base', winner='base')
    write_profile(profile_tree, 'first', inherits='base', winner='first', kept='first')
    write_profile(profile_tree, 'second', include='base', winner='second')
    write_profile(profile_tree, 'child', inherits='base', include=['first', 'second', 'first'], common='child')
    resolved = slicer.resolve_profile('machine', 'child')
    assert resolved['settings']['winner'] == 'first'  # last include wins; repeated DAG nodes are not cycles
    assert resolved['settings']['common'] == 'child'
    assert resolved['settings']['kept'] == 'first'
    assert len(resolved['files']) == 4
    write_profile(profile_tree, 'child', inherits='base', include=['first', 'second'])
    assert slicer.flatten('machine', 'child')['winner'] == 'second'


@pytest.mark.parametrize('dependency', ['inherits', 'include'])
def test_missing_dependency_is_an_error(profile_tree, dependency):
    write_profile(profile_tree, 'child', **{dependency: 'missing'})
    with pytest.raises(KeyError, match='missing'):
        slicer.flatten('machine', 'child')


@pytest.mark.parametrize('edges', [
    [{'inherits': 'a'}], [{'include': 'a'}],
    [{'inherits': 'b'}, {'include': ['a']}],
    [{'include': ['b']}, {'inherits': 'a'}],
])
def test_parent_include_cycles_fail(profile_tree, edges):
    for name, edge in zip(('a', 'b'), edges):
        write_profile(profile_tree, name, **edge)
    with pytest.raises(ValueError, match='Cyclic.*a'):
        slicer.flatten('machine', 'a')


@pytest.mark.parametrize('include', [None, 1, {}, [''], [3], ['../outside'], ['/outside'], ['a\\b']])
def test_invalid_includes_fail(profile_tree, include):
    write_profile(profile_tree, 'child', include=include)
    with pytest.raises(ValueError, match='Invalid'):
        slicer.flatten('machine', 'child')


@pytest.mark.parametrize('parent', [None, [], 0, '../outside'])
def test_invalid_parent_fails(profile_tree, parent):
    write_profile(profile_tree, 'child', inherits=parent)
    with pytest.raises(ValueError, match='Invalid'):
        slicer.flatten('machine', 'child')


def test_duplicate_profile_names_are_not_selected_by_filesystem_order(profile_tree):
    write_profile(profile_tree, 'same', filename='one.json')
    write_profile(profile_tree, 'same', filename='two.json')
    with pytest.raises(ValueError, match='Duplicate.*same'):
        slicer.flatten('machine', 'same')


@pytest.mark.parametrize('raw', [b'{', b'[]', b'\xff', b'{"name":3}'])
def test_bad_critical_template_is_not_silently_skipped(profile_tree, raw):
    write_profile(profile_tree, 'child', include='template')
    (profile_tree / 'machine/template.json').write_bytes(raw)
    with pytest.raises(ValueError):
        slicer.flatten('machine', 'child')


def test_nameless_lookup_maps_are_not_profiles(profile_tree):
    write_profile(profile_tree, 'child')
    (profile_tree / 'machine/lookup.json').write_text('{"id-to-label": {"1": "child"}}')
    assert slicer.flatten('machine', 'child')['name'] == 'child'


def test_profile_labels_can_contain_slashes_without_becoming_paths(profile_tree):
    write_profile(profile_tree, 'Support For PA/PET', filename='support.json', kind='filament', filament_density=['1.2'])
    write_profile(profile_tree, 'child', kind='filament', inherits='Support For PA/PET')
    assert slicer.flatten('filament', 'child')['filament_density'] == ['1.2']


def test_profile_symlink_cannot_escape_root(profile_tree):
    outside = profile_tree.parent / 'outside.json'
    outside.write_text('{"name":"outside"}')
    (profile_tree / 'machine/escape.json').symlink_to(outside)
    write_profile(profile_tree, 'child', include='outside')
    with pytest.raises(ValueError, match='escapes root'):
        slicer.flatten('machine', 'child')


def test_dependency_identity_uses_the_parsed_bytes_and_changes_with_template(profile_tree, monkeypatch):
    included = write_profile(profile_tree, 'template', machine_start_gcode='M109 S275')
    write_profile(profile_tree, 'child', include='template')
    first = slicer.resolve_profile('machine', 'child')
    write_profile(profile_tree, 'template', machine_start_gcode='M109 S280')
    second = slicer.resolve_profile('machine', 'child')
    assert first['files']['machine/template.json'] != second['files']['machine/template.json']
    raw = included.read_bytes()
    read_bytes = Path.read_bytes

    def captured_read(path):
        data = read_bytes(path)
        if path == included:
            path.write_text('{"name":"template", "machine_start_gcode":"changed after read"}')
        return data

    monkeypatch.setattr(Path, 'read_bytes', captured_read)
    captured = slicer.resolve_profile('machine', 'child')
    assert captured['settings']['machine_start_gcode'] == 'M109 S280'
    assert captured['files']['machine/template.json'] == hashlib.sha256(raw).hexdigest()


def test_installed_p1s_resolves_complete_start_template():
    try:
        root = slicer.profile_root()
    except FileNotFoundError:
        pytest.skip('Bambu profiles not installed')
    path = root / 'machine' / (slicer.PRINTER + '.json')
    if not path.exists():
        pytest.skip('P1S profile not installed')
    profile = json.loads(path.read_bytes())
    if not profile.get('include'):
        pytest.skip('Installed Bambu version predates included templates')
    resolved = slicer.resolve_profile('machine', slicer.PRINTER)
    template_name = slicer.PRINTER + ' template machine_start_gcode'
    template = root / 'machine' / (template_name + '.json')
    assert resolved['settings']['machine_start_gcode'] == json.loads(template.read_bytes())['machine_start_gcode']
    assert 'nozzle_temperature_initial_layer' in resolved['settings']['machine_start_gcode']
    assert resolved['files']['machine/' + template.name] == hashlib.sha256(template.read_bytes()).hexdigest()


def test_slice_consumes_resolved_templates_and_records_sources(profile_tree, tmp_path, monkeypatch):
    from types import SimpleNamespace
    write_profile(profile_tree, slicer.PRINTER, include='start')
    start = write_profile(profile_tree, 'start', machine_start_gcode='M109 S[nozzle_temperature_initial_layer]')
    write_profile(profile_tree, slicer.PROCESS, kind='process', wall_loops='2')
    write_profile(profile_tree, slicer.FILAMENTS['pla'], kind='filament', nozzle_temperature_initial_layer=['220'])
    monkeypatch.setattr(slicer, 'executable', lambda: '/fake/BambuStudio')
    model = tmp_path / 'part.stl'
    model.write_text('mock model; no slicer is run')
    work = tmp_path / 'slice'
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        machine = json.loads((work / 'machine.json').read_text())
        assert machine['machine_start_gcode'] == 'M109 S[nozzle_temperature_initial_layer]'
        assert 'include' not in machine
        assert json.loads((work / 'process.json').read_text())['wall_loops'] == '4'
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(slicer.subprocess, 'run', run)
    result = slicer.slice_part(model, workdir=work, overrides={'wall_loops': '4'})
    assert len(calls) == 1
    assert result['profile_sources']['machine']['machine/start.json'] == hashlib.sha256(start.read_bytes()).hexdigest()
    assert result['settings_sha256']['machine'] == hashlib.sha256((work / 'machine.json').read_bytes()).hexdigest()
    assert result['settings_sha256']['process'] == hashlib.sha256((work / 'process.json').read_bytes()).hexdigest()
    start.unlink()
    with pytest.raises(KeyError, match='start'):
        slicer.slice_part(model, workdir=tmp_path / 'missing-template')
    assert len(calls) == 1  # no subprocess may run with an unresolved template
    write_profile(profile_tree, 'start', machine_start_gcode='M109 S[nozzle_temperature_initial_layer]')

    def mutate_settings(cmd, **kwargs):
        (work / 'machine.json').write_text('{"machine_start_gcode":"changed"}')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(slicer.subprocess, 'run', mutate_settings)
    with pytest.raises(ValueError, match='settings changed'):
        slicer.slice_part(model, workdir=work)
    assert not (work / 'result-summary.json').exists()


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
    monkeypatch.setattr(slicer, 'resolve_profile', lambda kind, name: {'settings': {'name': name}, 'files': {}})
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
