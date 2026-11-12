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
import shutil
import signal
import subprocess
import sys
import time

import standard_eval as evaluation


def command(harness, executable, model, project):
    """Version-sensitive flags, recorded verbatim with every attempted trial."""
    if harness == 'codex':
        args = [executable, 'exec', '--json', '--ephemeral', '--ignore-user-config',
                '--skip-git-repo-check', '--sandbox', 'workspace-write',
                '--model', model, '--cd', str(project), '--color', 'never']
        settings = {
            'project_doc_max_bytes': '0', 'skills.bundled.enabled': 'false',
            'skills.include_instructions': 'false',
            'features.skip_host_skill_discovery': 'true',
            'memories.use_memories': 'false', 'memories.generate_memories': 'false',
            'web_search': '"disabled"', 'model_reasoning_effort': '"medium"',
        }
        for key, value in settings.items():
            args.extend(['-c', f'{key}={value}'])
        for name in ('memories', 'hooks', 'plugins', 'apps', 'multi_agent'):
            args.extend(['--disable', name])
        return args + ['-']
    if harness == 'claude':
        return [executable, '--print', '--model', model, '--output-format', 'stream-json',
                '--verbose', '--safe-mode', '--setting-sources', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--no-session-persistence', '--no-chrome', '--disable-slash-commands',
                '--tools', 'Bash,Read,Write,Edit', '--allowedTools', 'Bash,Read,Write,Edit',
                '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
                '--max-budget-usd', '2', '--effort', 'medium']
    raise ValueError('harness must be codex or claude')


def transcript_metrics(path, harness):
    """Use completed events only. Missing usage is unknown, never zero by default.

    A shell command containing an import is not sufficient to prove execution of
    a particular toolkit function. Kit use therefore needs a separate evidence
    review; the runner does not turn a matching string into a success metric.
    """
    calls, sessions, models, usages = {}, set(), set(), []
    malformed = 0
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
        if harness == 'codex':
            if row.get('type') == 'thread.started' and isinstance(row.get('thread_id'), str):
                sessions.add(row['thread_id'])
            if row.get('type') == 'item.completed':
                item = row.get('item') or {}
                if not isinstance(item, dict):
                    malformed += 1
                    continue
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
                terminal_success_event=terminal, malformed_transcript_lines=malformed)


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


def run(job_id, mode, work, harness, model, kit=None, kit_revision=None, python=None):
    if os.name != 'posix':
        raise ValueError('this collector requires POSIX process groups')
    executable = shutil.which(harness)
    if executable is None:
        raise ValueError(f'{harness} is not installed')
    executable = str(Path(executable).resolve())
    work = Path(work).resolve()
    prep = evaluation.prepare(job_id, mode, work, kit, kit_revision)
    work.chmod(0o700)
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
    args = command(harness, executable, model, project)
    # Preserve the normal OS home/login without copying credentials or assigning
    # an alternative HOME/CODEX_HOME. Do not lend unrelated environment secrets.
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TERM',
                                          'XDG_RUNTIME_DIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    env.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2',
               CLAUDE_CODE_DISABLE_AUTO_MEMORY='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
               DO_NOT_TRACK='1')
    version = subprocess.run([executable, '--version'], env=env, cwd=project,
                             capture_output=True, text=True, timeout=15)
    harness_version = version.stdout.strip() if version.returncode == 0 else None
    write_json(work / 'invocation.json', dict(argv=args, harness_version=harness_version,
               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               job_sha256=prep['job_sha256'], toolkit_revision=prep['kit_revision'],
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
    metrics = transcript_metrics(work / 'transcript.jsonl', harness)
    metadata = dict(harness=harness, harness_version=harness_version, model=model,
                    model_source='requested; resolved_model reported separately when available',
                    seed=None, wall_seconds=round(time.monotonic()-started, 3), exit_code=code,
                    timed_out=timed_out, launch_error=launch_error, collector_settled=settled, peak_context=None,
                    fresh_session=None, fresh_conversation_requested=True, kit_use_observed=None,
                    session_boundary='new conversation and task directory; existing OS login; context controls requested, not clean OS-user isolation',
                    **metrics)
    write_json(work / 'metadata.json', metadata)
    if not settled:
        # No grader reads task files while a member of the owned group may write.
        result = dict(job=job_id, mode=mode, passed=False, trial_completed=False,
                      usable_trial=False, error='collector did not confirm owned process group settled',
                      checks={}, collector=metadata)
        write_json(work / 'result.json', result)
        return result
    result = evaluation.ingest_run(job_id, work)
    result['usable_trial'] = (result['trial_completed'] and metrics['terminal_success_event']
                              and metrics['malformed_transcript_lines'] == 0 and metrics['session_count'] == 1)
    result['collector'] = {key: metadata[key] for key in ('launch_error', 'terminal_success_event',
                          'malformed_transcript_lines', 'session_count', 'session_id_sha256',
                          'resolved_model', 'cached_input_tokens', 'cache_creation_input_tokens', 'collector_settled')}
    write_json(work / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    parser.add_argument('--mode', choices=('bare', 'kit'), required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--harness', choices=('codex', 'claude'), required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--kit', type=Path)
    parser.add_argument('--kit-revision')
    parser.add_argument('--python', type=Path)
    args = parser.parse_args()
    result = run(args.job, args.mode, args.work, args.harness, args.model,
                 args.kit, args.kit_revision, args.python)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['usable_trial'] and result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
