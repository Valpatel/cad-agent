"""Real inert subprocess controls for the fresh-session collector; no model calls."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

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


def test_actual_inert_process_is_collected_and_wrong_answer_fails(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'prompt = sys.stdin.read()\n'
        'from pathlib import Path\nPath("solution.json").write_text("{}")\n'
        'print(json.dumps({"type":"thread.started","thread_id":"control"}))\n'
        'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}))\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    work = tmp_path / 'run'
    result = runner.run('snapfit-sizing', 'bare', work, 'codex', 'fake')
    assert result['usable_trial']
    assert not result['passed']
    assert result['collector']['collector_settled']
    assert (work.stat().st_mode & 0o777) == 0o700
    assert ((work / 'transcript.jsonl').stat().st_mode & 0o777) == 0o600
    with pytest.raises(ValueError, match='fresh'):
        runner.run('snapfit-sizing', 'bare', work, 'codex', 'fake')


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
    result = runner.run('snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['timed_out']
    assert not result['usable_trial']
    assert result['collector']['collector_settled']


def test_missing_terminal_event_is_infrastructure_failure(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\nprint("{}")\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    result = runner.run('snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['trial_completed']  # the subprocess exited normally
    assert not result['usable_trial']  # a model completion was not observed


def test_unsettled_group_prevents_grading(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    monkeypatch.setattr(runner, 'group_gone', lambda _: False)
    monkeypatch.setattr(runner.evaluation, 'ingest_run', lambda *args: pytest.fail('must not grade active writer'))
    result = runner.run('snapfit-sizing', 'bare', tmp_path / 'run', 'codex', 'fake')
    assert result['checks'] == {} and not result['usable_trial']


def test_venv_interpreter_path_is_preserved(tmp_path, monkeypatch):
    executable = fake_harness(tmp_path, 'sys.stdin.read()\n')
    monkeypatch.setattr(runner.shutil, 'which', lambda harness: str(executable))
    venv_python = tmp_path / 'venv-python'
    venv_python.symlink_to(sys.executable)
    work = tmp_path / 'run'
    runner.run('snapfit-sizing', 'bare', work, 'codex', 'fake', python=venv_python)
    assert str(venv_python) in (work / 'prompt.txt').read_text()
