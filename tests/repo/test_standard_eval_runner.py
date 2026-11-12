"""Real inert subprocess controls for the fresh-session collector; no model calls."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux cgroup v2/user-service collector')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/evaluation'))
spec = importlib.util.spec_from_file_location('standard_eval_runner', ROOT / 'tools/evaluation/runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def write_rows(tmp_path, rows):
    path = tmp_path / 'transcript.jsonl'
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    return path


def test_unknown_usage_is_not_zero_and_text_is_not_toolkit_execution(tmp_path):
    path = write_rows(tmp_path, [dict(type='item.completed', item=dict(
        id='x', type='agent_message', text='I imported cadagent and passed everything.'))])
    result = runner.transcript_metrics(path, 'codex')
    assert result['tokens_in'] is None
    assert result['tokens_out'] is None
    assert result['cost_usd'] is None
    assert result['tool_calls'] == 0
    assert not result['terminal_success_event']


def test_codex_events_count_completed_calls_once_and_keep_cached_usage(tmp_path):
    item = dict(id='x', type='command_execution', command='echo cad-agent', exit_code=0)
    path = write_rows(tmp_path, [dict(type='thread.started', thread_id='new-a'),
        dict(type='item.started', item=item), dict(type='item.completed', item=item),
        dict(type='item.completed', item=item),
        dict(type='turn.completed', usage=dict(input_tokens=150, cached_input_tokens=100, output_tokens=20))])
    result = runner.transcript_metrics(path, 'codex')
    assert result['tool_calls'] == 1
    assert result['session_count'] == 1
    assert result['tokens_in'] == 150 and result['cached_input_tokens'] == 100
    assert result['cost_usd'] is None
    assert 'kit_use_observed' not in result


def test_claude_result_error_is_not_a_success(tmp_path):
    path = write_rows(tmp_path, [dict(type='system', subtype='init', model='observed-model', session_id='new-b'),
        dict(type='result', is_error=True, usage=dict(input_tokens=2, output_tokens=3), total_cost_usd=.01)])
    result = runner.transcript_metrics(path, 'claude')
    assert not result['terminal_success_event']
    assert result['resolved_model'] == 'observed-model'
    assert result['cost_usd'] == .01


def test_codex_sandbox_error_survives_a_normal_final_message(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n'
        'print(json.dumps({"type":"thread.started","thread_id":"control"}))\n'
        'print(json.dumps({"type":"item.completed","item":{"type":"error","message":"sandbox failed"}}))\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}))\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    result = collected_result(monkeypatch, 'snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['trial_completed']
    assert result['collector']['harness_errors'] == 1
    assert not result['usable_trial']


def test_malformed_and_nonfinite_metrics_cannot_be_a_usable_success(tmp_path):
    path = write_rows(tmp_path, [dict(type='turn.completed', usage=dict(input_tokens=float('nan')))])
    path.write_text(path.read_text() + '\nnot JSON\n[]\n')
    result = runner.transcript_metrics(path, 'codex')
    assert result['tokens_in'] is None
    assert result['malformed_transcript_lines'] == 2


@pytest.mark.parametrize('harness', ['codex', 'claude'])
def test_cli_requests_new_conversation_without_permission_bypass(harness):
    args = runner.command(harness, '/bin/example', 'requested-model', Path('/tmp/example'))
    assert not any('resume' in arg or 'bypass' in arg for arg in args)
    assert '--model' in args
    if harness == 'codex':
        assert '--ephemeral' in args and '--ignore-user-config' in args
        assert 'project_doc_max_bytes=0' in args
        assert 'memories.use_memories=false' in args
    else:
        assert '--safe-mode' in args and '--no-session-persistence' in args


def fake_harness(tmp_path, body):
    executable = tmp_path / 'fake-cli'
    executable.write_text('#!/usr/bin/python3\nimport json, sys, time\n'
        'if "--version" in sys.argv:\n print("fake-cli 1"); sys.exit(0)\n' + body)
    executable.chmod(0o700)
    return executable


def mock_terminal_unit(monkeypatch):
    # These process controls are not cgroup-teardown evidence; the opt-in actual
    # service test below covers the detached-child boundary.
    monkeypatch.setattr(runner, 'unit_receipt', lambda *args: dict(unit_success=True, cgroup_empty=True))


def collected_result(monkeypatch, *args, **kwargs):
    result = runner.collect(*args, **kwargs)
    assert result['awaiting_unit_settlement']
    work = Path(args[2])
    assert not (work / 'result.json').exists()
    mock_terminal_unit(monkeypatch)
    return runner.finalize(work, 'cad-eval-test.service')


def test_actual_inert_process_is_collected_and_wrong_answer_fails(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'prompt = sys.stdin.read()\n'
        'from pathlib import Path\nPath("solution.json").write_text("{}")\n'
        'print(json.dumps({"type":"thread.started","thread_id":"control"}))\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}))\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    work = tmp_path / 'run'
    result = collected_result(monkeypatch, 'snapfit-sizing', 'bare', work, 'codex', 'fake')
    assert result['usable_trial']
    assert not result['passed']
    assert result['collector']['collector_settled']
    assert (work.stat().st_mode & 0o777) == 0o700
    assert ((work / 'transcript.jsonl').stat().st_mode & 0o777) == 0o600
    with pytest.raises(ValueError, match='fresh'):
        runner.collect('snapfit-sizing', 'bare', work, 'codex', 'fake')


def test_actual_timeout_cannot_pass_even_with_artifact(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n'
        'from pathlib import Path\nPath("solution.json").write_text("{}")\ntime.sleep(30)\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    original = runner.evaluation.prepare
    def short(*args, **kwargs):
        prepared = original(*args, **kwargs)
        prepared['budget']['wall_seconds'] = .1
        return prepared
    monkeypatch.setattr(runner.evaluation, 'prepare', short)
    result = collected_result(monkeypatch, 'snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['timed_out']
    assert not result['usable_trial']
    assert result['collector']['collector_settled']


def test_missing_terminal_event_is_infrastructure_failure(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\nprint("{}")\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    result = collected_result(monkeypatch, 'snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['trial_completed']  # the subprocess exited normally
    assert not result['usable_trial']  # a model completion was not observed


def test_no_grading_in_collector_and_unsettled_unit_refuses_finalize(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    monkeypatch.setattr(runner.evaluation, 'ingest_run', lambda *args: pytest.fail('must not grade active writer'))
    work = tmp_path / 'run'
    runner.collect('snapfit-sizing', 'bare', work, 'codex', 'fake')
    def unsettled(*args):
        raise ValueError('active')
    monkeypatch.setattr(runner, 'unit_receipt', unsettled)
    with pytest.raises(ValueError, match='active'):
        runner.finalize(work, 'cad-eval-test.service')
    assert not (work / 'result.json').exists()


def test_venv_interpreter_path_is_preserved(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    venv_python = tmp_path / 'venv-python'
    venv_python.symlink_to(sys.executable)
    work = tmp_path / 'run'
    runner.collect('snapfit-sizing', 'bare', work, 'codex', 'fake', python=venv_python)
    assert str(venv_python) in (work / 'prompt.txt').read_text()


def test_final_metrics_include_bytes_written_until_unit_teardown(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n'
        'print(json.dumps({"type":"thread.started","thread_id":"control"}))\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}))\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    work = tmp_path / 'run'
    runner.collect('snapfit-sizing', 'bare', work, 'codex', 'fake')
    assert 'tokens_in' not in json.loads((work / 'collection.json').read_text())
    def stop_then_settle(*args):
        with (work / 'transcript.jsonl').open('a') as stream:
            stream.write('detached child late bytes\n')
        return dict(unit_success=True, cgroup_empty=True)
    monkeypatch.setattr(runner, 'unit_receipt', stop_then_settle)
    result = runner.finalize(work, 'cad-eval-test.service')
    assert result['collector']['malformed_transcript_lines'] == 1
    assert not result['usable_trial']


def unit_fixture(tmp_path, monkeypatch, changes=None, members=''):
    work = tmp_path / 'run'; work.mkdir()
    group = '/slice/cad-eval-test.service'
    (work / 'cgroup.json').write_text(json.dumps(dict(path=group)))
    root = tmp_path / 'cgroups'
    procs = root / group.lstrip('/') / 'cgroup.procs'
    procs.parent.mkdir(parents=True); procs.write_text(members)
    state = dict(LoadState='loaded', ActiveState='active', SubState='exited', MainPID='0', ControlPID='0',
                 KillMode='control-group', RemainAfterExit='yes', Result='success', ExecMainStatus='0', ControlGroup=group)
    state.update(changes or {})
    calls = []
    def call(args, **kwargs):
        calls.append(args)
        if 'stop' in args:
            state.update(ActiveState='inactive', SubState='dead', LoadState='not-found')
        return subprocess.CompletedProcess(args, 0, '\n'.join(f'{k}={v}' for k,v in state.items()), '')
    monkeypatch.setattr(runner.subprocess, 'run', call)
    return work, root, calls


@pytest.mark.parametrize('change', [dict(LoadState='not-found'), dict(MainPID='123'),
    dict(ActiveState='active', SubState='running'), dict(KillMode='process'), dict(RemainAfterExit='no')])
def test_unit_guard_refuses_unknown_active_self_or_weak_containment(tmp_path, monkeypatch, change):
    work, root, calls = unit_fixture(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError):
        runner.unit_receipt(work, 'cad-eval-test.service', root)
    assert not any('stop' in args for args in calls)


def test_wrong_unit_cannot_stop_another_service(tmp_path, monkeypatch):
    work, root, calls = unit_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='does not match'):
        runner.unit_receipt(work, 'cad-eval-other.service', root)
    assert not any('stop' in args for args in calls)


def test_nonempty_cgroup_after_stop_refuses_grading(tmp_path, monkeypatch):
    work, root, calls = unit_fixture(tmp_path, monkeypatch, members='123\n')
    with pytest.raises(ValueError, match='still contains'):
        runner.unit_receipt(work, 'cad-eval-test.service', root)
    assert any('stop' in args for args in calls)


def test_terminal_unit_error_is_preserved(tmp_path, monkeypatch):
    work, root, _ = unit_fixture(tmp_path, monkeypatch, dict(Result='timeout', ExecMainStatus='15'))
    receipt = runner.unit_receipt(work, 'cad-eval-test.service', root)
    assert receipt['cgroup_empty'] and not receipt['unit_success']
    assert receipt['properties']['Result'] == 'timeout'


@pytest.mark.skipif(os.environ.get('CAD_EVAL_SYSTEMD_CONTROL') != '1', reason='opt-in actual user-service control')
def test_actual_detached_child_stops_before_grading(tmp_path):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n'
        'import subprocess\nfrom pathlib import Path\n'
        'child = subprocess.Popen(["/usr/bin/sleep", "60"], start_new_session=True)\n'
        'Path("child.pid").write_text(str(child.pid))\nPath("solution.json").write_text("{}")\n'
        'print(json.dumps({"type":"thread.started","thread_id":"control"}))\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}))\n')
    (tmp_path / 'codex').symlink_to(executable)
    unit = 'cad-eval-control-' + uuid.uuid4().hex + '.service'
    work = tmp_path / 'attempt'
    args = ['systemd-run', '--user', '--unit=' + unit, '--property=RemainAfterExit=yes',
            '--property=KillMode=control-group', '--property=TimeoutStopSec=3', '--property=RuntimeMaxSec=20',
            '--property=MemoryMax=256M', '--property=TasksMax=32',
            '--setenv=PATH=' + str(tmp_path) + ':/usr/bin:/bin',
            '/usr/bin/python3', str(ROOT / 'tools/evaluation/runner.py'), 'collect', '--job', 'snapfit-sizing',
            '--mode', 'bare', '--work', str(work), '--harness', 'codex', '--model', 'fake']
    subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = subprocess.run(['systemctl','--user','show',unit,'--property=SubState','--value'],
                                   capture_output=True,text=True,timeout=5).stdout.strip()
            if state in ('exited','failed'):
                break
            time.sleep(.05)
        assert state == 'exited'
        child = int((work / 'project/child.pid').read_text())
        os.kill(child, 0)  # The test genuinely produced a surviving detached child.
        assert not (work / 'result.json').exists()
        result = runner.finalize(work, unit)
        assert result['harness_version'] == 'fake-cli 1'
        assert result['usable_trial'] and not result['passed']
        assert result['unit']['cgroup_empty']
        assert not Path(f'/proc/{child}').exists()
    finally:
        subprocess.run(['systemctl','--user','stop',unit],capture_output=True,text=True,timeout=10)
