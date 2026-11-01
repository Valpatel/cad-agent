"""PrusaSlicer support: vendor-bundle profiles, G-code statistics and slicing (the slicer only runs where installed)."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

import pytest

from cadagent.manufacturing import slicer_prusa

FIXTURE = Path(__file__).parent / 'fixtures' / 'prusa_config'


@pytest.fixture
def bundle_root(tmp_path, monkeypatch):
    config = tmp_path / 'PrusaSlicer'
    shutil.copytree(FIXTURE, config)
    monkeypatch.setenv('CADAGENT_PRUSA_PROFILES', str(config / 'vendor'))
    return config / 'vendor'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_multi_parent_inherits_later_parent_wins(bundle_root):
    r = slicer_prusa.resolve_profile('print', '0.20mm TEST')
    s = r['settings']
    assert s['perimeters'] == '2'                 # own key beats both parents
    assert s['fill_density'] == '20%'             # *mk4s* (later parent) beats *common*
    assert s['layer_height'] == '0.2' and s['gcode_label_objects'] == 'firmware'
    assert not {'inherits', 'compatible_printers_condition'} & s.keys()
    assert s['print_settings_id'] == '0.20mm TEST'
    assert r['files'] == {'vendor/Mini.ini': sha(bundle_root / 'Mini.ini')}
    p = slicer_prusa.resolve_profile('printer', 'Test MK4S')['settings']
    assert p['bed_shape'] == '0x0,250x0,250x210,0x210' and 'renamed_from' not in p


def test_value_with_semicolons_and_braces_is_kept_verbatim(bundle_root):
    s = slicer_prusa.resolve_profile('filament', 'Test PLA')['settings']
    assert s['start_filament_gcode'] == '"M572 S{if nozzle_diameter[0]==0.4}0.05{endif} ; 100% [comment]\\nM900"'
    assert s['filament_cost'] == '' and s['cooling'] == '1'
    assert s['filament_density'] == '1.24'        # the vendor bundle's own parent, not Templates.ini's


def test_missing_parent_is_keyerror_and_cycle_is_valueerror(bundle_root):
    with pytest.raises(KeyError, match='Missing Parent'):
        slicer_prusa.resolve_profile('filament', 'Orphan')
    with pytest.raises(KeyError, match='No Such'):
        slicer_prusa.resolve_profile('filament', 'No Such')
    with pytest.raises(ValueError, match='Cyclic.*Loop A'):
        slicer_prusa.resolve_profile('filament', 'Loop A')
    with pytest.raises(ValueError, match='Unknown PrusaSlicer profile kind'):
        slicer_prusa.resolve_profile('machine', 'Test MK4S')


def test_same_profile_in_two_bundles_is_ambiguous(bundle_root):
    shutil.copy(bundle_root / 'Mini.ini', bundle_root / 'Other.ini')
    with pytest.raises(ValueError, match='Ambiguous'):
        slicer_prusa.resolve_profile('print', '0.20mm TEST')


def test_templates_bundle_is_only_a_fallback(bundle_root):
    s = slicer_prusa.resolve_profile('filament', 'Template Only PLA')['settings']
    assert s['filament_density'] == '9.99' and s['filament_type'] == 'PLA'


def test_user_preset_inherits_from_system_profile(bundle_root):
    r = slicer_prusa.resolve_profile('printer', 'My MK4S')
    s = r['settings']
    assert s['printer_notes'] == 'MY OWN NOTES' and s['nozzle_diameter'] == '0.4'
    assert s['printer_settings_id'] == 'My MK4S'
    assert set(r['files']) == {'printer/My MK4S.ini', 'vendor/Mini.ini'}


@pytest.mark.parametrize('name', ['../vendor/Mini', 'a/b', 'a\\b', ''])
def test_profile_names_are_labels_not_paths(bundle_root, name):
    with pytest.raises((ValueError, KeyError)):
        slicer_prusa.resolve_profile('printer', name)


def test_duplicate_section_in_one_bundle_fails(bundle_root):
    (bundle_root / 'Mini.ini').write_text((bundle_root / 'Mini.ini').read_text() + '\n[print:0.20mm TEST]\nperimeters = 9\n')
    with pytest.raises(ValueError, match='Duplicate'):
        slicer_prusa.resolve_profile('print', '0.20mm TEST')


def test_profile_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv('CADAGENT_PRUSA_PROFILES', str(tmp_path / 'nowhere'))
    with pytest.raises(FileNotFoundError, match='CADAGENT_PRUSA_PROFILES'):
        slicer_prusa.profile_root()
    (tmp_path / 'nowhere').mkdir()
    (tmp_path / 'nowhere' / 'X.ini').write_text('[vendor]\n')
    assert slicer_prusa.profile_root() == tmp_path / 'nowhere'


def test_gcode_stats_parse_multi_extruder_and_days():
    text = ('; filament used [mm] = 1000.0, 0.0, 500.0\n; filament used [g] = 1.20, 0.00, 3.40\n'
            '; estimated printing time (normal mode) = 1d 2h 3m 4s\n'
            '; estimated printing time (silent mode) = 9d 9h 9m 9s\n')
    assert slicer_prusa.parse_gcode_stats(text) == {'grams': 4.6, 'seconds': 93784.0, 'filament_m': 1.5}
    assert slicer_prusa.parse_gcode_stats('; estimated printing time (normal mode) = 42s\n')['seconds'] == 42.0


def test_gcode_stats_absent_footer_gives_none():
    assert slicer_prusa.parse_gcode_stats('G1 X0\n') == {'grams': None, 'seconds': None, 'filament_m': None}


# --- slicing ---

FOOTER = ('; filament used [mm] = 1284.93, 0.00\n; filament used [g] = 3.83, 0.00\n'
          '; estimated printing time (normal mode) = 19m 18s\n')
# what PrusaSlicer's --save writes for a three-tool printer: each filament setting once per extruder
RESOLVED = {'printer_settings_id': 'Test MK4S', 'print_settings_id': '0.20mm TEST', 'nozzle_diameter': '0.4,0.4,0.4',
            'filament_settings_id': '"Test PLA";"Test PLA";"Test PLA"', 'filament_type': 'PLA;PLA;PLA',
            'temperature': '215,215,215', 'perimeters': '2', 'binary_gcode': '1'}


def fake_run(calls, footer=FOOTER, returncode=0, stderr='', resolved=RESOLVED):
    """PrusaSlicer: ``--save`` writes ``resolved``, ``--export-gcode`` writes G-code ending in ``footer``."""
    from types import SimpleNamespace

    def run(cmd, **kwargs):
        calls.append(cmd)
        if resolved is not None and '--save' in cmd:
            Path(cmd[cmd.index('--save') + 1]).write_text(''.join(f'{k} = {v}\n' for k, v in resolved.items()))
        if footer is not None and '--export-gcode' in cmd:
            Path(cmd[cmd.index('--output') + 1]).write_text('G1 X0\n' + footer)
        return SimpleNamespace(returncode=returncode, stdout='Slicing...\n', stderr=stderr)
    return run


def read_ini(path):
    return slicer_prusa._parse(Path(path).read_text(), Path(path), sections=False)['']


def test_prusa_slice_uses_prusaslicers_own_resolution(bundle_root, tmp_path, monkeypatch):
    """A five-tool XL's G-code named a filament for tool 1 only (and PrusaSlicer's window showed 'config.ini' for
    tools 2-5) when the profiles were flattened by hand. PrusaSlicer's own --save gives them per extruder."""
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    calls = []
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run(calls))
    model = tmp_path / 'part.3mf'
    model.write_text('mock model; no slicer is run')
    work = tmp_path / 'work'
    r = slicer_prusa.slice_part(model, work, 'Test MK4S', '0.20mm TEST', 'Test PLA', {'perimeters': 5})
    cfg = read_ini(work / 'config.ini')
    assert cfg == dict(RESOLVED, perimeters='5', binary_gcode='0')
    cmd = calls[-1]
    assert cmd[0] == '/fake/prusa-slicer' and '--export-gcode' in cmd and cmd[cmd.index('--load') + 1] == str(work / 'config.ini')
    assert cmd[-1] == str(model.resolve())
    assert r['grams'] == 3.83 and r['seconds'] == 1158.0 and r['minutes'] == 19.3 and r['filament_m'] == 1.285
    assert r['settings_sha256'] == {'config': sha(work / 'config.ini')}
    assert r['profile_sources']['print'] == {'vendor/Mini.ini': sha(bundle_root / 'Mini.ini')}
    assert r['slicer'] == 'prusa-slicer' and r['exit_code'] == 0 and r['error'] is None and 'log_tail' not in r
    assert r['printer'] == 'Test MK4S' and r['overrides'] == {'perimeters': 5}


def test_a_misspelt_profile_fails_before_prusaslicer_runs(bundle_root, tmp_path, monkeypatch):
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', lambda *a, **k: pytest.fail('must not run PrusaSlicer'))
    with pytest.raises(KeyError, match='0.20mm TSET'):
        slicer_prusa.slice_part(tmp_path / 'm.3mf', tmp_path / 'w', 'Test MK4S', '0.20mm TSET', 'Test PLA')


def test_prusa_config_forces_text_gcode():
    assert slicer_prusa.build_config(RESOLVED, {'binary_gcode': '1'})['binary_gcode'] == '0'


def test_prusa_unknown_override_key_is_an_error():
    with pytest.raises(ValueError, match="wall_loops"):
        slicer_prusa.build_config(RESOLVED, {'wall_loops': '3'})
    assert slicer_prusa.build_config(RESOLVED, {'perimeters': True})['perimeters'] == '1'


def test_prusa_override_lists_are_refused():
    """PrusaSlicer joins string vectors with ';' and numbers with ',': a list cannot say which."""
    with pytest.raises(ValueError, match='single values'):
        slicer_prusa.build_config(RESOLVED, {'temperature': [215, 220]})
    assert slicer_prusa.build_config(RESOLVED, {'temperature': '215,220'})['temperature'] == '215,220'


def test_prusa_failed_slice_reports_log_tail(bundle_root, tmp_path, monkeypatch):
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run(
        [], footer=None, returncode=1, stderr='Objects are outside the print volume.\n'))
    model = tmp_path / 'big.3mf'
    model.write_text('x')
    r = slicer_prusa.slice_part(model, tmp_path / 'w', 'Test MK4S', '0.20mm TEST', 'Test PLA', {})
    assert r['grams'] is None and r['exit_code'] == 1
    assert 'outside the print volume' in r['error'] and 'outside the print volume' in r['log_tail']


def test_prusa_reason_is_kept_when_slicer_exits_0_without_gcode(bundle_root, tmp_path, monkeypatch):
    """PrusaSlicer 2.9.4 exits 0 for a part outside the print volume and writes no G-code."""
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    run = fake_run([], footer=None)

    def outside(cmd, **kw):
        r = run(cmd, **kw)
        r.stdout = '10 => Processing triangulated mesh\nAll objects are outside of the print volume.\n'
        return r
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', outside)
    model = tmp_path / 'bar.3mf'
    model.write_text('x')
    r = slicer_prusa.slice_part(model, tmp_path / 'w', 'Test MK4S', '0.20mm TEST', 'Test PLA', {})
    assert r['grams'] is None and r['error'] == 'All objects are outside of the print volume.'


def test_prusa_not_installed_is_a_runtime_error(bundle_root, tmp_path, monkeypatch):
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: None)
    with pytest.raises(RuntimeError, match='PrusaSlicer is not installed'):
        slicer_prusa.slice_part(tmp_path / 'm.3mf', tmp_path / 'w', 'Test MK4S', '0.20mm TEST', 'Test PLA', {})


def test_executable_finds_path_binary_then_flatpak(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(slicer_prusa.shutil, 'which', lambda n: '/usr/bin/prusa-slicer' if n == 'prusa-slicer' else None)
    assert slicer_prusa.executable() == ['/usr/bin/prusa-slicer']
    monkeypatch.setattr(slicer_prusa.shutil, 'which', lambda n: '/usr/bin/flatpak' if n == 'flatpak' else None)
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', lambda cmd, **kw: SimpleNamespace(returncode=0, stdout='', stderr=''))
    assert slicer_prusa.executable() == ['flatpak', 'run', '--command=prusa-slicer', 'com.prusa3d.PrusaSlicer']
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', lambda cmd, **kw: SimpleNamespace(returncode=1, stdout='', stderr=''))
    assert slicer_prusa.executable() is None


def test_slicer_dispatches_on_engine(monkeypatch, tmp_path):
    from cadagent.manufacturing import slicer
    seen = {}

    def fake(model, work, printer, process, filament, overrides, timeout=900):
        seen.update(model=model, work=work, printer=printer, process=process, filament=filament)
        return {'grams': 1.0}
    monkeypatch.setattr(slicer_prusa, 'slice_part', fake)
    model = tmp_path / 'm.3mf'
    model.write_text('x')
    assert slicer.slice_part(model, workdir=tmp_path / 'w', engine='prusa') == {'grams': 1.0}
    assert seen['printer'] == slicer_prusa.PRINTER and seen['process'] == slicer_prusa.PROCESS
    assert seen['filament'] == slicer_prusa.FILAMENTS['pla']
    assert (tmp_path / 'w' / '.cadagent-slicer').exists()       # the shared work-folder guard ran
    with pytest.raises(ValueError, match='Unknown'):
        slicer.slice_part(model, workdir=tmp_path / 'w', engine='cura')


def test_resolved_by_prusaslicer_runs_save_on_the_private_datadir(bundle_root, tmp_path, monkeypatch):
    seen = []
    written = dict(RESOLVED, printer_settings_id='My MK4S')
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run(seen, resolved=written))
    cfg = slicer_prusa.resolved_by_prusaslicer(['ps'], 'My MK4S', '0.20mm TEST', 'Test PLA', tmp_path)
    assert cfg == written
    cmd = seen[0]
    assert cmd[cmd.index('--printer-profile') + 1] == 'My MK4S' and cmd[cmd.index('--print-profile') + 1] == '0.20mm TEST'
    assert cmd[cmd.index('--material-profile') + 1] == 'Test PLA'
    data_dir = Path(cmd[cmd.index('--datadir') + 1])
    assert data_dir == tmp_path / 'prusaslicer-datadir' and data_dir != bundle_root.parent    # a private copy
    # the printer's model installed (else PrusaSlicer hides its system profile), and the one filament
    assert (data_dir / 'PrusaSlicer.ini').read_text() == '[vendor:Mini]\nmodel:MK4S = \n\n[filaments]\nTest PLA = 1\n'
    assert (data_dir / 'vendor' / 'Mini.ini').read_bytes() == (bundle_root / 'Mini.ini').read_bytes()
    assert (data_dir / 'printer' / 'My MK4S.ini').exists()                                     # user presets too
    assert not (bundle_root.parent / 'PrusaSlicer.ini').exists()                                # the user's left alone


@pytest.mark.parametrize('field, value', [('print_settings_id', '0.15mm OTHER'),
                                          ('filament_settings_id', '"Test PLA";"Other PLA"')])
def test_prusaslicer_loading_other_presets_is_an_error(bundle_root, tmp_path, monkeypatch, field, value):
    """PrusaSlicer falls back to another preset when it cannot use the one named."""
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run([], resolved=dict(RESOLVED, **{field: value})))
    with pytest.raises(ValueError, match='not the presets named'):
        slicer_prusa.resolved_by_prusaslicer(['ps'], 'Test MK4S', '0.20mm TEST', 'Test PLA', tmp_path)


def test_prusaslicer_refusing_the_presets_is_an_error_with_its_reason(bundle_root, tmp_path, monkeypatch):
    reason = 'Material profile "Test PLA" is not compatible with printer profile Test MK4S.'
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run([], returncode=1, stderr=reason + '\n', resolved=None))
    with pytest.raises(ValueError, match='is not compatible with printer profile Test MK4S'):
        slicer_prusa.resolved_by_prusaslicer(['ps'], 'Test MK4S', '0.20mm TEST', 'Test PLA', tmp_path)


def test_bundles_outside_a_vendor_folder_install_the_printer_model(tmp_path, monkeypatch):
    """/usr/share/PrusaSlicer/profiles (or CADAGENT_PRUSA_PROFILES) is not named vendor: the model must still be
    installed, or PrusaSlicer hides the printer and loads its default one."""
    shutil.copytree(FIXTURE / 'vendor', tmp_path / 'profiles')
    monkeypatch.setenv('CADAGENT_PRUSA_PROFILES', str(tmp_path / 'profiles'))
    data_dir = slicer_prusa.private_datadir(tmp_path / 'w', 'Test PLA', 'Test MK4S')
    assert (data_dir / 'PrusaSlicer.ini').read_text().startswith('[vendor:Mini]\nmodel:MK4S = ')


def test_prusaslicer_timing_out_on_save_is_an_error(bundle_root, tmp_path, monkeypatch):
    seen = []

    def slow(cmd, **kw):
        seen.append(kw.get('timeout'))
        raise slicer_prusa.subprocess.TimeoutExpired(cmd, kw.get('timeout'))
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', slow)
    with pytest.raises(ValueError, match='did not finish'):
        slicer_prusa.slice_part(tmp_path / 'm.3mf', tmp_path / 'w', 'Test MK4S', '0.20mm TEST', 'Test PLA', timeout=42)
    assert seen == [42]


def test_prusa_empty_override_is_refused():
    with pytest.raises(ValueError, match='single values'):
        slicer_prusa.build_config(RESOLVED, {'perimeters': None})


def test_gcode_without_a_weight_says_so(bundle_root, tmp_path, monkeypatch):
    monkeypatch.setattr(slicer_prusa, 'executable', lambda: ['/fake/prusa-slicer'])
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run([], footer='; estimated printing time (normal mode) = 1m\n'))
    model = tmp_path / 'm.3mf'
    model.write_text('x')
    r = slicer_prusa.slice_part(model, tmp_path / 'w', 'Test MK4S', '0.20mm TEST', 'Test PLA')
    assert r['grams'] is None and 'filament used [g]' in r['error']


# --- the real PrusaSlicer, where installed ---

def _has_profile(kind, name):
    try:
        slicer_prusa.resolve_profile(kind, name)
        return True
    except (KeyError, ValueError, FileNotFoundError):
        return False


def _installed(printer):
    return slicer_prusa.executable() is not None and _has_profile('printer', printer)


@pytest.fixture
def home_work(request):
    """A work folder under the home directory (the flatpak cannot read /tmp), removed afterwards."""
    work = Path.home() / '.cache' / 'cadagent-test' / request.node.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    yield work
    shutil.rmtree(work, ignore_errors=True)
    if not any(work.parent.iterdir()):
        work.parent.rmdir()


def _cube(work):
    trimesh = pytest.importorskip('trimesh')
    stl = work / 'cube.stl'
    trimesh.creation.box(extents=(20, 20, 20)).apply_translation((0, 0, 10)).export(str(stl))
    return stl


@pytest.mark.skipif(not _installed(slicer_prusa.PRINTER), reason='PrusaSlicer or its MK4S profile not installed')
def test_prusaslicer_slices_a_cube(home_work):
    r = slicer_prusa.slice_part(_cube(home_work), home_work / 'out', slicer_prusa.PRINTER, slicer_prusa.PROCESS,
                                slicer_prusa.FILAMENTS['pla'], {})
    assert 2.5 < r['grams'] < 6, r
    assert r['minutes'] and r['minutes'] > 1


@pytest.mark.skipif(not _installed(slicer_prusa.PRINTER), reason='PrusaSlicer or its MK4S profile not installed')
def test_prusaslicer_takes_user_presets_and_refuses_unfit_ones(home_work, monkeypatch):
    """A user's own print preset is accepted and sliced with its settings (PrusaSlicer takes a user preset as saved,
    not merged with its parents, so only the setting the preset holds is checked); a filament made for another
    printer is refused."""
    config = home_work / 'PrusaSlicer'
    (config / 'print').mkdir(parents=True)
    shutil.copytree(slicer_prusa.profile_root(), config / 'vendor')
    (config / 'print' / 'My SPEED.ini').write_text(f'inherits = {slicer_prusa.PROCESS}\nperimeters = 4\n'
                                                   'compatible_printers_condition = printer_notes=~/.*MK4S.*/\n')
    monkeypatch.setenv('CADAGENT_PRUSA_PROFILES', str(config / 'vendor'))
    stl = _cube(home_work)
    r = slicer_prusa.slice_part(stl, home_work / 'mine', slicer_prusa.PRINTER, 'My SPEED', slicer_prusa.FILAMENTS['pla'])
    assert r['grams'] and read_ini(home_work / 'mine' / 'config.ini')['perimeters'] == '4'
    assert set(r['profile_sources']['print']) >= {'print/My SPEED.ini'}
    if _has_profile('filament', 'Prusament PLA @XLIS'):
        with pytest.raises(ValueError, match='not compatible'):
            slicer_prusa.slice_part(stl, home_work / 'xl', slicer_prusa.PRINTER, slicer_prusa.PROCESS,
                                    'Prusament PLA @XLIS')


XL5 = 'Original Prusa XL - 5T Input Shaper 0.4 nozzle'


@pytest.mark.skipif(not _installed(XL5), reason='PrusaSlicer or its XL 5T profile not installed')
def test_prusaslicer_names_the_filament_on_every_tool_of_an_xl(home_work):
    slicer_prusa.slice_part(_cube(home_work), home_work / 'out', XL5, '0.20mm SPEED @XLIS 0.4', 'Prusament PLA @XLIS', {})
    gcode = (home_work / 'out' / 'out' / 'sliced.gcode').read_text()
    ids = re.search(r'^; filament_settings_id = (.*)$', gcode, re.M).group(1)
    assert ids == ';'.join(['"Prusament PLA @XLIS"'] * 5), ids
    assert re.search(r'^; filament_type = (.*)$', gcode, re.M).group(1) == 'PLA;PLA;PLA;PLA;PLA'
