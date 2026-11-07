"""cad-agent prusa-view: arguments, the private profile folder, process and window matching. The GUI run is skipped
without a display, PrusaSlicer, xwininfo and ImageMagick (and unless CADAGENT_PRUSA_VIEW_GUI=1: it opens a window)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cadagent.cli import main
from cadagent.manufacturing import prusa_view, slicer_prusa
from tests.manufacturing.test_slicer_prusa import FIXTURE, RESOLVED, fake_run, read_ini


@pytest.fixture
def bundle_root(tmp_path, monkeypatch):
    config = tmp_path / 'PrusaSlicer'
    shutil.copytree(FIXTURE, config)
    monkeypatch.setenv('CADAGENT_PRUSA_PROFILES', str(config / 'vendor'))
    return config / 'vendor'


@pytest.fixture
def model(tmp_path):
    m = tmp_path / 'models' / 'door.3mf'
    m.parent.mkdir()
    m.write_text('mock model; no slicer is run')
    return m


def sections(text):
    out = {'': {}}
    cur = out['']
    for line in text.splitlines():
        if line.startswith('['):
            cur = out[line.strip('[]')] = {}
        elif '=' in line:
            k, _, v = line.partition('=')
            cur[k.strip()] = v.strip()
    return out


@pytest.mark.parametrize('text, bed', [('1500x600', (1500, 600, None)), ('300X200x150', (300, 200, 150)),
                                       ('250.5x210', (250.5, 210, None))])
def test_parse_bed(text, bed):
    assert prusa_view.parse_bed(text) == bed


@pytest.mark.parametrize('text', ['1500', '0x600', 'axb', '1x2x3x4', '-5x5'])
def test_parse_bed_rejects(text):
    with pytest.raises(ValueError, match='WIDTHxDEPTH'):
        prusa_view.parse_bed(text)
    with pytest.raises(ValueError, match="PrusaSlicer's limit"):
        prusa_view.parse_bed('1500x600x1300')


@pytest.mark.parametrize('own, bed, height', [('300', (1500, 600, None), '1200'),   # PrusaSlicer refuses > 1200
                                              ('360', (300, 200, None), '360'), ('360', (300, 200, 50), '50')])
def test_view_bed_height(own, bed, height):
    assert prusa_view.view_bed_config({'max_print_height': own}, bed)['max_print_height'] == height


def test_view_bed_config_turns_the_wipe_tower_and_bed_model_off():
    cfg = prusa_view.view_bed_config({'bed_shape': '0x0,250x0,250x210,0x210', 'wipe_tower': '1',
                                      'bed_custom_model': 'mk4.stl', 'perimeters': '2'}, (1500, 600, 400))
    assert cfg == {'bed_shape': '0x0,1500x0,1500x600,0x600', 'max_print_height': '400', 'wipe_tower': '0',
                   'bed_custom_model': '', 'bed_custom_texture': '', 'perimeters': '2'}


def test_prepare_writes_the_private_datadir_with_gui_settings(bundle_root, model, monkeypatch):
    calls = []
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', fake_run(calls))
    r = prusa_view.prepare(model, {'printer': 'Test MK4S', 'process': '0.20mm TEST', 'filament': 'Test PLA',
                                   'overrides': {'perimeters': 4}}, exe=['/fake/prusa-slicer'], prusa_version='2.9.4')
    work = model.parent / 'prusa-view' / 'door'
    assert r['work'] == str(work) and (work / '.cadagent-prusa-view').exists()
    data_dir = Path(r['datadir'])
    assert data_dir == work / 'prusaslicer-datadir' and data_dir.parent != bundle_root.parent
    assert (data_dir / 'vendor' / 'Mini.ini').read_bytes() == (bundle_root / 'Mini.ini').read_bytes()
    assert (data_dir / 'printer' / 'My MK4S.ini').exists()
    ini = sections((data_dir / 'PrusaSlicer.ini').read_text())
    assert ini[''] == {'version_system_info_sent': '2.9.4', 'window_mainframe': '0; 0; 1920; 1172; 1',
                       'background_processing': '1', 'show_splash_screen': '0', 'version_check': '0',
                       'preset_update': '0', 'notify_release': 'none', 'show_hints': '0'}
    assert ini['vendor:Mini'] == {'model:MK4S': ''} and ini['filaments'] == {'Test PLA': '1'}
    # three tools: a filament per tool
    assert ini['presets'] == {'printer': 'Test MK4S', 'print': '0.20mm TEST', 'filament': 'Test PLA',
                              'filament_1': 'Test PLA', 'filament_2': 'Test PLA'}
    assert read_ini(r['config']) == dict(RESOLVED, perimeters='4', binary_gcode='0')
    assert not (bundle_root.parent / 'PrusaSlicer.ini').exists()            # the user's own left alone
    cmd, env = prusa_view.gui_command(r['exe'], data_dir, Path(r['config']), model, '/etc/ca.pem')
    assert cmd == ['/fake/prusa-slicer', '--datadir', str(data_dir), '--load', r['config'], str(model)]
    assert env['SSL_CERT_FILE'] == '/etc/ca.pem'


def test_prepare_from_a_config_on_a_view_bed(bundle_root, model, tmp_path, monkeypatch):
    def no_run(cmd, **k):
        assert cmd[0] == 'ps', 'no preset resolution with --config'
        return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
    monkeypatch.setattr(slicer_prusa.subprocess, 'run', no_run)
    monkeypatch.setattr(prusa_view, 'version', lambda exe: None)            # a PrusaSlicer that names no version
    config = tmp_path / 'config.ini'
    config.write_text('printer_settings_id = Test MK4S\nprint_settings_id = 0.20mm TEST\nnozzle_diameter = 0.4\n'
                      'filament_settings_id = "Test PLA"\nbed_shape = 0x0,250x0,250x210,0x210\nwipe_tower = 1\n')
    r = prusa_view.prepare(model, config=config, view_bed=(1500, 600, None), exe=['/fake/prusa-slicer'],
                           workdir=tmp_path / 'w')
    cfg = read_ini(r['config'])
    assert cfg['bed_shape'] == '0x0,1500x0,1500x600,0x600' and cfg['wipe_tower'] == '0'
    assert cfg['max_print_height'] == '1200'
    ini = sections((Path(r['datadir']) / 'PrusaSlicer.ini').read_text())
    assert ini['']['background_processing'] == '0' and 'version_system_info_sent' not in ini['']
    assert ini['presets'] == {'printer': 'Test MK4S', 'print': '0.20mm TEST', 'filament': 'Test PLA'}


def test_prepare_refuses_a_foreign_work_folder_and_tmp_for_the_flatpak(bundle_root, model, tmp_path):
    (tmp_path / 'busy').mkdir()
    (tmp_path / 'busy' / 'keep.txt').write_text('mine')
    with pytest.raises(prusa_view.ViewError, match='not a prusa-view work folder'):
        prusa_view.prepare(model, config=tmp_path / 'x.ini', exe=['/fake/prusa-slicer'], workdir=tmp_path / 'busy')
    assert (tmp_path / 'busy' / 'keep.txt').exists()
    with pytest.raises(prusa_view.ViewError, match='cannot read /tmp'):
        prusa_view.prepare(model, exe=['flatpak', 'run', 'x'], workdir='/tmp/cadagent-prusa-view-test')


def test_flatpak_gets_the_ca_file_inside_the_sandbox(monkeypatch):
    monkeypatch.delenv(prusa_view.CA_ENV, raising=False)
    exe = ['flatpak', 'run', '--command=prusa-slicer', 'com.prusa3d.PrusaSlicer']
    ca = prusa_view.ca_file(exe)
    assert ca == prusa_view.FLATPAK_CA_FILE
    cmd, _ = prusa_view.gui_command(exe, Path('/h/d'), Path('/h/c.ini'), Path('/h/m.3mf'), ca)
    assert cmd[:3] == ['flatpak', 'run', f'--env=SSL_CERT_FILE={ca}'] and cmd[-5:] == [
        '--datadir', '/h/d', '--load', '/h/c.ini', '/h/m.3mf']
    monkeypatch.setenv(prusa_view.CA_ENV, '/my/ca.pem')
    assert prusa_view.ca_file(exe) == '/my/ca.pem' and prusa_view.ca_file(exe, '/given.pem') == '/given.pem'


def test_own_processes_match_only_this_datadir_and_prusaslicer_programs(monkeypatch):
    d = '/home/u/w/prusaslicer-datadir'
    argv = {
        100: ['prusa-slicer', '--datadir', d, '--load', 'c', 'm'],
        101: ['/app/bin/prusa-slicer', '--datadir', d, '--load', 'c', 'm'],
        102: ['flatpak', 'run', '--env=SSL_CERT_FILE=/etc/ca.pem', '--command=prusa-slicer',
              slicer_prusa.FLATPAK_ID, '--datadir', d, '--load', 'c', 'm'],
        103: ['/bin/bash', '-c', f'prusa-slicer --datadir {d}'],
        104: ['prusa-slicer', '--datadir', d + '-other', '--load', 'c', 'm'],
        105: ['prusa-slicer', '--datadir', '/home/u/.config/PrusaSlicer', 'm'],
        106: ['prusa-slicer', f'--description=x--datadir {d}', '--load', 'c', 'm'],
        107: ['my-prusa-wrapper', '--datadir', d],
        108: ['flatpak', 'run', 'org.example.Unrelated', '--datadir', d],
        109: ['bwrap', '--datadir', d],
        os.getpid(): ['prusa-slicer', '--datadir', d],
    }
    # ps is only discovery: even identical command text cannot override actual argv boundaries.
    ps = '\n'.join(f'{pid} ' + ' '.join(args) for pid, args in argv.items())
    monkeypatch.setattr(prusa_view, '_process_identity', lambda pid: ('1000', tuple(argv[pid])))
    assert prusa_view.own_processes(Path(d), ps) == [100, 101, 102]


def test_actual_proc_reader_preserves_space_arguments_and_rejects_missing_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(prusa_view, '_PROC', tmp_path)
    proc = tmp_path / '123'
    proc.mkdir()
    (proc / 'stat').write_text('123 (Prusa Slicer) ' + ' '.join(['S'] + ['0'] * 18 + ['9876']))
    argv = ['prusa-slicer', '--datadir', '/home/u/work space/prusaslicer-datadir']
    (proc / 'cmdline').write_bytes(b'\0'.join(os.fsencode(arg) for arg in argv) + b'\0')
    assert prusa_view._process_identity(123) == ('9876', tuple(argv))
    assert prusa_view._owned_argv(argv, Path(argv[2]))
    # Same printed command text, but a single option value, must never count.
    assert not prusa_view._owned_argv(['prusa-slicer', ' '.join(argv[1:])], Path(argv[2]))
    assert not prusa_view._owned_argv(argv + ['--datadir', '/foreign'], Path(argv[2]))
    assert not prusa_view._owned_argv(['prusa-slicer', '--', '--datadir', argv[2]], Path(argv[2]))
    (proc / 'cmdline').write_bytes(b'prusa-slicer')
    assert prusa_view._process_identity(123) is None
    assert prusa_view._process_identity(124) is None


TREE = '''
     0x8002bf "*door - PrusaSlicer-2.9.4 based on Slic3r": ("mutter-x11-frames" "mutter-x11-frames")  1920x1172+0+0  +0+0
        0xa000ff "*door - PrusaSlicer-2.9.4 based on Slic3r": ("prusa-slicer" "PrusaSlicer")  1920x1139+0+33  +0+33
     0xa00009 "prusa-slicer": ("prusa-slicer" "PrusaSlicer")  200x200+0+0  +0+0
        0xb000ff "door - PrusaSlicer-2.9.4 based on Slic3r": ("prusa-slicer" "PrusaSlicer")  1920x1139+0+33  +0+33
'''


def test_the_new_window_titled_with_the_model_is_picked():
    found = prusa_view.windows(TREE)
    assert [w[0] for w in found] == ['0xa000ff', '0xa00009', '0xb000ff']
    assert prusa_view.pick_window(found, 'door', before=['0xa000ff', '0xa00009']) == '0xb000ff'
    assert prusa_view.pick_window(found, 'door', before=['0xa000ff', '0xb000ff']) is None
    assert prusa_view.pick_window(found, 'boom', before=[]) is None
    stl = '        0xd000ff "*Untitled - PrusaSlicer-2.9.4 based on Slic3r": ("prusa-slicer" "PrusaSlicer")  1920x1139+0+33'
    assert prusa_view.pick_window(prusa_view.windows(TREE + stl), 'cube', before=['0xa000ff']) == '0xd000ff'


def test_stop_signals_only_own_pids(monkeypatch, tmp_path):
    monkeypatch.setattr(prusa_view, 'own_processes', lambda d: [4242])
    sent = []
    closed = []
    monkeypatch.setattr(prusa_view, '_process_identity', lambda pid: ('1000', ('prusa-slicer', '--datadir', str(tmp_path))))
    monkeypatch.setattr(prusa_view.os, 'pidfd_open', lambda pid, flags: 9000)
    monkeypatch.setattr(prusa_view.os, 'close', closed.append)
    monkeypatch.setattr(prusa_view.signal, 'pidfd_send_signal', lambda fd, sig: sent.append((fd, sig)))
    monkeypatch.setattr(prusa_view, '_alive', lambda pid: False)
    assert prusa_view.stop(tmp_path) == [4242]
    assert sent == [(9000, prusa_view.signal.SIGTERM)]
    assert closed == [9000]


@pytest.mark.parametrize('change_before', ['open', 'term', 'kill'])
def test_stop_revalidates_kernel_identity_before_each_signal(monkeypatch, tmp_path, change_before):
    monkeypatch.setattr(prusa_view, 'own_processes', lambda d: [4242])
    owned = ('1000', ('prusa-slicer', '--datadir', str(tmp_path)))
    reused = ('2000', ('prusa-slicer', '--datadir', str(tmp_path)))
    foreign = ('1000', ('unrelated', '--datadir', str(tmp_path)))
    identities = {'open': [foreign], 'term': [owned, reused], 'kill': [owned, owned, reused]}[change_before]
    calls, closed = [], []
    monkeypatch.setattr(prusa_view, '_process_identity', lambda pid: identities.pop(0) if len(identities) > 1 else identities[0])
    monkeypatch.setattr(prusa_view.os, 'pidfd_open', lambda pid, flags: 9000)
    monkeypatch.setattr(prusa_view.os, 'close', closed.append)
    monkeypatch.setattr(prusa_view.signal, 'pidfd_send_signal', lambda fd, sig: calls.append((fd, sig)))
    assert prusa_view.stop(tmp_path, grace=0) == ([4242] if change_before == 'kill' else [])
    assert calls == ([(9000, prusa_view.signal.SIGTERM)] if change_before == 'kill' else [])
    assert closed == [9000]


def test_stop_cannot_claim_an_unverifiable_running_child_is_closed(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(prusa_view, 'own_processes', lambda d: [])
    monkeypatch.setattr(prusa_view, '_process_identity', lambda pid: None)
    monkeypatch.setattr(prusa_view.os, 'pidfd_open', lambda pid, flags: 9000)
    closed = []
    monkeypatch.setattr(prusa_view.os, 'close', closed.append)
    child = SimpleNamespace(pid=4242, poll=lambda: None, wait=lambda timeout: None)
    with pytest.raises(prusa_view.ViewError, match='still running; not reported as closed'):
        prusa_view.stop(tmp_path, child, grace=0)
    assert closed == [9000]


def test_open_view_needs_a_display(monkeypatch, model):
    monkeypatch.delenv('DISPLAY', raising=False)
    with pytest.raises(prusa_view.ViewError, match='no display'):
        prusa_view.open_view(model)


def test_cli_prusa_view_reports_unusable_cases(monkeypatch, model, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('DISPLAY', raising=False)
    assert main(['prusa-view', str(model)]) == 2
    assert 'no display' in capsys.readouterr().err
    monkeypatch.setenv('DISPLAY', ':99')
    assert main(['prusa-view', str(model), '--view-bed', '1500']) == 2
    assert 'WIDTHxDEPTH' in capsys.readouterr().err


def test_cli_prusa_view_stop_with_nothing_open(monkeypatch, model, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prusa_view, 'own_processes', lambda d: [])
    assert main(['prusa-view', str(model), '--stop']) == 0
    assert 'no view open' in capsys.readouterr().out


def test_cli_prusa_view_passes_options(monkeypatch, model, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_open(model, settings, config, bed, screenshot, wait, close, workdir, ca, say):
        seen.update(model=model, settings=settings, config=config, bed=bed, screenshot=screenshot, wait=wait,
                    close=close, workdir=workdir, ca=ca)
        return {'screenshot': screenshot, 'closed': close, 'stopped': [7], 'pids': [7], 'view_bed': [1500, 600, 1200]}
    monkeypatch.setattr(prusa_view, 'open_view', fake_open)
    assert main(['prusa-view', str(model), '--view-bed', '1500x600', '--screenshot', 'o.png', '--wait', '3',
                 '--close', '--config', 'c.ini']) == 0
    assert seen['bed'] == (1500, 600, None) and seen['wait'] == 3 and seen['close'] and seen['config'] == 'c.ini'
    out = capsys.readouterr().out
    assert 'view bed 1500 x 600 x 1200 mm' in out and 'for looking at only' in out and 'stopped only' in out and 'screenshot: o.png' in out


GUI = (os.environ.get('CADAGENT_PRUSA_VIEW_GUI') == '1' and os.environ.get('DISPLAY') and shutil.which('xwininfo')
       and shutil.which('import') and slicer_prusa.executable())


@pytest.mark.skipif(not GUI, reason='needs CADAGENT_PRUSA_VIEW_GUI=1, a display, PrusaSlicer, xwininfo and ImageMagick')
def test_gui_opens_screenshots_and_closes_its_own_window():
    import trimesh
    work = Path(__file__).resolve().parents[2] / 'build' / 'test-prusa-view'   # the flatpak cannot read /tmp
    work.mkdir(parents=True, exist_ok=True)
    model = work / 'cube.stl'
    trimesh.creation.box((20, 20, 20)).export(model)
    others = [w[0] for w in prusa_view.windows()]
    r = prusa_view.open_view(model, screenshot=work / 'cube.png', wait=5, close=True, workdir=work / 'view')
    assert Path(r['screenshot']).stat().st_size > 1000 and r['closed']
    assert not prusa_view.own_processes(Path(r['datadir']))
    assert all(w in [x[0] for x in prusa_view.windows()] for w in others)    # other windows untouched
