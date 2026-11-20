#!/usr/bin/env python3
"""Run one analytical eval in a new CLI conversation and a new task directory.

This uses the operator's existing login. Context-disabling flags are explicit;
the task directory is not an OS isolation boundary. Raw transcripts stay local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import standard_eval as evaluation

REASONING_EFFORTS = ('low', 'medium', 'high')


def command(harness, executable, model, project, reasoning_effort='medium'):
    """Version-sensitive flags, recorded verbatim with every attempted trial."""
    if reasoning_effort not in REASONING_EFFORTS:
        raise ValueError('reasoning effort must be low, medium or high')
    if harness == 'codex':
        args = [executable, 'exec', '--json', '--ephemeral', '--ignore-user-config',
                '--skip-git-repo-check', '--sandbox', 'workspace-write',
                '--model', model, '--cd', str(project), '--color', 'never']
        settings = {
            'project_doc_max_bytes': '0', 'skills.bundled.enabled': 'false',
            'skills.include_instructions': 'false',
            'features.skip_host_skill_discovery': 'true',
            'memories.use_memories': 'false', 'memories.generate_memories': 'false',
            'web_search': '"disabled"', 'model_reasoning_effort': json.dumps(reasoning_effort),
        }
        for key, value in settings.items():
            args.extend(['-c', f'{key}={value}'])
        for name in ('memories', 'hooks', 'plugins', 'apps', 'multi_agent', 'shell_snapshot'):
            args.extend(['--disable', name])
        return args + ['-']
    if harness == 'claude':
        return [executable, '--print', '--model', model, '--output-format', 'stream-json',
                '--verbose', '--safe-mode', '--setting-sources', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--no-session-persistence', '--no-chrome', '--disable-slash-commands',
                '--tools', 'Bash,Read,Write,Edit', '--allowedTools', 'Bash,Read,Write,Edit',
                '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
                '--max-budget-usd', '2', '--effort', reasoning_effort]
    raise ValueError('harness must be codex or claude')


def transcript_metrics(path, harness):
    """Use completed events only. Missing usage is unknown, never zero by default.

    A shell command containing an import is not sufficient to prove execution of
    a particular toolkit function. Kit use therefore needs a separate evidence
    review; the runner does not turn a matching string into a success metric.
    """
    calls, sessions, models, usages = {}, set(), set(), []
    malformed = 0
    harness_errors = 0
    terminal = False
    for line in path.read_text(errors='replace').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(row, dict):
            malformed += 1
            continue
        if row.get('type') == 'error':
            harness_errors += 1
        if harness == 'codex':
            if row.get('type') == 'thread.started' and isinstance(row.get('thread_id'), str):
                sessions.add(row['thread_id'])
            if row.get('type') == 'item.completed':
                item = row.get('item') or {}
                if not isinstance(item, dict):
                    malformed += 1
                    continue
                if item.get('type') == 'error':
                    harness_errors += 1
                if item.get('type') in ('command_execution', 'file_change', 'mcp_tool_call', 'web_search'):
                    calls[item.get('id', str(len(calls)))] = item.get('type')
            if row.get('type') == 'turn.completed':
                terminal = True
                usages.append(row.get('usage') if isinstance(row.get('usage'), dict) else {})
        else:
            if row.get('type') == 'system' and row.get('subtype') == 'init':
                if isinstance(row.get('session_id'), str):
                    sessions.add(row['session_id'])
                if isinstance(row.get('model'), str):
                    models.add(row['model'])
            if row.get('type') == 'assistant':
                for part in row.get('message', {}).get('content', []):
                    if isinstance(part, dict) and part.get('type') == 'tool_use':
                        calls[part.get('id', str(len(calls)))] = part.get('name')
            if row.get('type') == 'result':
                terminal = row.get('is_error') is False
                usage = row.get('usage') if isinstance(row.get('usage'), dict) else {}
                usages.append({**usage, 'cost_usd': row.get('total_cost_usd')})

    def total(key):
        values = [usage.get(key) for usage in usages]
        return sum(values) if values and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values) else None

    # Preserve provider-specific cached-token accounting separately. These raw
    # input fields are not a cross-provider total-context or cost comparison.
    return dict(tokens_in=total('input_tokens'), tokens_out=total('output_tokens'),
                cached_input_tokens=total('cached_input_tokens') if harness == 'codex' else total('cache_read_input_tokens'),
                cache_creation_input_tokens=total('cache_creation_input_tokens'),
                cost_usd=total('cost_usd'), tool_calls=len(calls),
                session_count=len(sessions),
                session_id_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in sorted(sessions)],
                resolved_model=next(iter(models)) if len(models) == 1 else None,
                terminal_success_event=terminal, malformed_transcript_lines=malformed, harness_errors=harness_errors)


def settle_group(process):
    """Terminate the owned group even when its leader exited before its children."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def group_gone(group):
    """Fail closed if the owned group remains (including unreaped members)."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        time.sleep(.05)
    return False


def write_json(path, data):
    with path.open('x') as stream:
        os.chmod(path, 0o600)
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def collect(job_id, mode, work, harness, model, kit=None, kit_revision=None, python=None,
            reasoning_effort='medium'):
    # Reject unsupported requests before creating a trial or launching a CLI.
    if reasoning_effort not in REASONING_EFFORTS:
        raise ValueError('reasoning effort must be low, medium or high')
    if sys.platform != 'linux':
        raise ValueError('this collector requires Linux cgroup v2 and user systemd')
    executable = shutil.which(harness)
    if executable is None:
        raise ValueError(f'{harness} is not installed')
    executable = str(Path(executable).resolve())
    work = Path(work).resolve()
    prep = evaluation.prepare(job_id, mode, work, kit, kit_revision)
    work.chmod(0o700)
    groups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    if len(groups) != 1:
        raise ValueError('collection requires a Linux cgroup v2 runtime')
    write_json(work / 'cgroup.json', dict(path=groups[0]))
    prompt = (work / 'prompt.txt').read_text()
    if python:
        # A venv interpreter is commonly a symlink: resolving it would silently
        # discard pyvenv.cfg and run the system interpreter instead.
        python = Path(python).absolute()
        if not python.is_file() or not os.access(python, os.X_OK):
            raise ValueError('Python interpreter must exist and be executable')
        prompt += f'\nThe existing Python interpreter is {python}. Use it when Python is needed; do not install dependencies.\n'
        (work / 'prompt.txt').write_text(prompt)
    project = work / 'project'
    args = command(harness, executable, model, project, reasoning_effort)
    # Preserve the normal OS home/login without copying credentials or assigning
    # an alternative HOME/CODEX_HOME. Do not lend unrelated environment secrets.
    env = {key: os.environ[key] for key in ('HOME', 'LANG', 'LC_ALL', 'TERM',
                                          'XDG_RUNTIME_DIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    env.update(PATH='/usr/bin:/bin', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2',
               CLAUDE_CODE_DISABLE_AUTO_MEMORY='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
               DO_NOT_TRACK='1')
    version = subprocess.run([executable, '--version'], env=env, cwd=project,
                             capture_output=True, text=True, timeout=15)
    harness_version = version.stdout.strip() if version.returncode == 0 else None
    write_json(work / 'invocation.json', dict(argv=args, harness_version=harness_version,
               reasoning_effort_requested=reasoning_effort,
               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               job_sha256=prep['job_sha256'], toolkit_revision=prep['kit_revision'],
               python=str(python) if python else None, child_path=env['PATH'],
               wall_limit_seconds=prep['budget']['wall_seconds'],
               max_output_tokens_enforced=None, seed_enforced=None))
    started = time.monotonic()
    timed_out, code, launch_error, settled = False, None, None, False
    process = None
    with (work / 'transcript.jsonl').open('x') as stdout, (work / 'stderr.txt').open('x') as stderr:
        os.chmod(work / 'transcript.jsonl', 0o600); os.chmod(work / 'stderr.txt', 0o600)
        try:
            process = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, text=True, start_new_session=True)
            try:
                process.communicate(prompt, timeout=prep['budget']['wall_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                settle_group(process)
                process.wait(timeout=5)
                settled = group_gone(process.pid)
            code = process.returncode
        except OSError as exc:
            launch_error = str(exc)
    metadata = dict(harness=harness, harness_version=harness_version, model=model,
                    reasoning_effort_requested=reasoning_effort, reasoning_effort_effective=None,
                    model_source='requested; resolved_model reported separately when available',
                    seed=None, wall_seconds=round(time.monotonic()-started, 3), exit_code=code,
                    timed_out=timed_out, launch_error=launch_error, cli_group_gone=settled, peak_context=None,
                    fresh_session=None, fresh_conversation_requested=True, kit_use_observed=None,
                    session_boundary='new conversation and task directory; existing OS login; context controls requested, not clean OS-user isolation')
    # A child can create a new session/process group. Only the outer service's
    # later cgroup teardown settles it. Never grade from inside the collector.
    write_json(work / 'collection.json', metadata)
    return dict(job=job_id, mode=mode, collection_finished=True, awaiting_unit_settlement=True,
                exit_code=code, timed_out=timed_out)


def unit_receipt(work, unit, cgroup_root=Path('/sys/fs/cgroup')):
    """Stop a completed owned collector's retained service, then verify empty.

    RemainAfterExit retains real Result/ExecMainStatus until we capture them.
    An unloaded unit alone supplies default fields and is not provenance.
    """
    if not re.fullmatch(r'cad-eval-[a-zA-Z0-9_-]+\.service', unit):
        raise ValueError('unit must be an explicit cad-eval-*.service name')
    keys = ('ActiveState', 'SubState', 'MainPID', 'ControlPID', 'KillMode', 'Result', 'ExecMainStatus',
            'LoadState', 'RemainAfterExit', 'ControlGroup')
    def state():
        status = subprocess.run(['systemctl', '--user', 'show', unit,
                                 '--property=' + ','.join(keys)], capture_output=True, text=True, timeout=10, check=True)
        return dict(line.split('=', 1) for line in status.stdout.splitlines() if '=' in line)
    props = state()
    if (props.get('LoadState') != 'loaded' or props.get('ActiveState') not in ('active', 'inactive', 'failed')
            or props.get('SubState') not in ('exited', 'dead', 'failed') or props.get('MainPID') != '0'
            or props.get('ControlPID') != '0' or props.get('KillMode') != 'control-group'
            or props.get('RemainAfterExit') != 'yes'
            or 'Result' not in props or 'ExecMainStatus' not in props):
        raise ValueError('unit is active, unknown, or lacks the required containment state')
    group = evaluation.read_json(Path(work) / 'cgroup.json').get('path')
    if not isinstance(group, str) or not group.startswith('/') or Path(group).name != unit or '..' in Path(group).parts:
        raise ValueError('requested unit does not match the collector cgroup')
    if props.get('ControlGroup') not in (group, ''):
        raise ValueError('loaded unit cgroup differs from the collector cgroup')
    root = Path(cgroup_root).resolve()
    directory = (root / group.lstrip('/')).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('cgroup escapes the cgroup filesystem')
    # The collector has exited, but detached tools may remain. Only stop the
    # explicitly bound, retained service; never stop a live collector or caller.
    subprocess.run(['systemctl', '--user', 'stop', unit], capture_output=True, text=True, timeout=15, check=True)
    after = state()
    if (after.get('ActiveState') not in ('inactive', 'failed') or after.get('SubState') not in ('dead', 'failed')
            or after.get('MainPID') != '0' or after.get('ControlPID') != '0'):
        raise ValueError('service did not finish stopping; do not grade')
    members = directory / 'cgroup.procs'
    if members.exists() and members.read_text().strip():
        raise ValueError('owned cgroup still contains processes; do not grade')
    public_props = {key: value for key, value in props.items() if key != 'ControlGroup'}
    return dict(unit=unit, properties=public_props, collector_cgroup_sha256=hashlib.sha256(group.encode()).hexdigest(),
                cgroup_empty=True, unit_success=props['Result'] == 'success' and props['ExecMainStatus'] == '0')


def finalize(work, unit):
    """Run outside the service after its main collector exited, before grading."""
    work = Path(work).resolve()
    receipt = unit_receipt(work, unit)  # Must precede reads of any subject output.
    prep = evaluation.read_json(work / 'preparation.json')
    metadata = evaluation.read_json(work / 'collection.json') if (work / 'collection.json').exists() else {}
    if (work / 'transcript.jsonl').exists() and metadata.get('harness') in ('codex', 'claude'):
        # Detached tools can inherit stdout. Its final bytes and metrics must be
        # read only after teardown, just like the solution artifact.
        metadata.update(transcript_metrics(work / 'transcript.jsonl', metadata['harness']))
    metadata['collector_settled'] = True
    write_json(work / 'unit-receipt.json', receipt)
    write_json(work / 'metadata.json', metadata)
    result = evaluation.ingest_run(prep['job'], work)
    result['usable_trial'] = (receipt['unit_success'] and result['trial_completed']
                              and metadata.get('terminal_success_event') is True
                              and metadata.get('harness_errors') == 0
                              and metadata.get('malformed_transcript_lines') == 0 and metadata.get('session_count') == 1)
    result['collector'] = {key: metadata.get(key) for key in ('launch_error', 'terminal_success_event',
                          'malformed_transcript_lines', 'harness_errors', 'session_count', 'session_id_sha256',
                          'resolved_model', 'reasoning_effort_requested', 'reasoning_effort_effective',
                          'cached_input_tokens', 'cache_creation_input_tokens', 'collector_settled')}
    result['unit'] = receipt
    write_json(work / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('collect', 'finalize'))
    parser.add_argument('--job')
    parser.add_argument('--mode', choices=('bare', 'kit'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--harness', choices=('codex', 'claude'))
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort', choices=REASONING_EFFORTS, default='medium',
                        help='requested CLI effort (collect only; effective value is unverified)')
    parser.add_argument('--unit')
    parser.add_argument('--kit', type=Path)
    parser.add_argument('--kit-revision')
    parser.add_argument('--python', type=Path)
    args = parser.parse_args()
    if args.action == 'collect':
        if not all((args.job, args.mode, args.harness, args.model)):
            parser.error('collect requires --job --mode --harness --model')
        result = collect(args.job, args.mode, args.work, args.harness, args.model,
                         args.kit, args.kit_revision, args.python, args.reasoning_effort)
    else:
        if not args.unit:
            parser.error('finalize requires --unit')
        result = finalize(args.work, args.unit)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if args.action == 'collect' or (result['usable_trial'] and result['passed']) else 1


if __name__ == '__main__':
    sys.exit(main())
