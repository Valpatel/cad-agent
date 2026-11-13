#!/usr/bin/env python3
"""Optional, inert Inspect qualification. Never runs a real model or grades CAD.

Collect in a retained user service; finalize outside it. Docker containers are
not members of that service's cgroup. No output is accepted before both settle.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import uuid

import runner
from standard_eval import read_json

INSPECT_REVISION = 'ff0acb3de3cb2fec0b1b35d0f46d40e234289dc8'
LABEL = 'org.valpatel.cad-eval.attempt'
OUTPUT = '/tmp/cad-eval-output'
MAX_ARCHIVE = 2_000_000
MAX_FILES = 16
MAX_BYTES = 1_000_000
HEX_ID = re.compile(r'[0-9a-f]{64}')
CASES = ('normal', 'detached', 'timeout', 'oom', 'pretool', 'interrupted', 'symlink', 'wrong')


def controller_hashes():
    return {Path(p).name: sha256(Path(p).read_bytes()) for p in (__file__, runner.__file__)}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def private_root(work, *, fresh=False):
    work = Path(work).absolute()
    if '..' in work.parts or any(p.is_symlink() for p in (work, *work.parents)):
        raise ValueError('work path must not contain symlinks')
    if fresh:
        work.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(work.iterdir()):
            raise ValueError('work must be fresh and empty')
        work.chmod(0o700)
    elif not work.is_dir():
        raise ValueError('missing attempt directory')
    return work


def runtime(source):
    """Require the reviewed source, not a matching package version alone."""
    source = Path(source).resolve()
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if head != INSPECT_REVISION or dirty:
        raise ValueError('Inspect source must be clean at the exact reviewed revision')
    spec = importlib.util.find_spec('inspect_ai')
    if not spec or not spec.origin or not Path(spec.origin).resolve().is_relative_to(source / 'src'):
        raise ValueError('this interpreter must import Inspect from that pinned source checkout')
    if sys.version_info < (3, 11):
        raise ValueError('Inspect requires Python 3.11+')
    return dict(revision=head, python=sys.version.split()[0], source=str(source))


def preflight(source=None):
    """Read-only prerequisite availability, never retained-service qualification."""
    checks = {}

    def record(name, available, detail):
        checks[name] = dict(state='available' if available else 'unavailable', detail=detail)

    record('python', sys.version_info >= (3, 11), sys.version.split()[0])
    record('linux', sys.platform == 'linux', sys.platform)
    record('cgroup_v2', Path('/sys/fs/cgroup/cgroup.controllers').is_file(),
           'requires the unified cgroup hierarchy')
    record('systemd_run', shutil.which('systemd-run') is not None,
           'required to launch the retained user service')
    try:
        status = subprocess.run(['systemctl', '--user', 'is-system-running'],
                                capture_output=True, text=True, timeout=10, check=False)
        state = status.stdout.strip()
        available = ((state == 'running' and status.returncode == 0)
                     or (state == 'degraded' and status.returncode == 1))
        record('user_manager', available, dict(state=state, exit_code=status.returncode))
    except (OSError, subprocess.SubprocessError) as exc:
        record('user_manager', False, f'{type(exc).__name__}: {exc}')
    try:
        docker = Docker()
        record('docker', True, dict(daemon=docker.identity, endpoint='unix:///var/run/docker.sock'))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        record('docker', False, f'{type(exc).__name__}: {exc}')
        checks['compose'] = dict(state='not_checked', detail='local Docker prerequisite unavailable')
    else:
        try:
            version = docker.call('compose', 'version', '--short').strip()
            record('compose', bool(version), version)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            record('compose', False, f'{type(exc).__name__}: {exc}')
    if source is None:
        checks['inspect_source'] = dict(state='not_checked', detail='optional --inspect-source omitted')
    else:
        try:
            record('inspect_source', True, runtime(source))
        except (OSError, ValueError, subprocess.SubprocessError, ImportError) as exc:
            record('inspect_source', False, f'{type(exc).__name__}: {exc}')
    required = [name for name in checks if name != 'inspect_source' or source is not None]
    return dict(schema='cadagent.inspect-prerequisites/1',
                passed=all(checks[name]['state'] == 'available' for name in required),
                checks=checks, runtime_qualified=False, real_model_called=False,
                note='Availability only; retained service, sandbox and provider controls remain required.')


class Docker:
    """Only an explicitly local daemon; never enumerate or mutate by broad name."""
    def __init__(self):
        # Explicit context prevents ambient DOCKER_HOST/DOCKER_CONTEXT overrides.
        executable = shutil.which('docker')
        if not executable:
            raise ValueError('Docker executable is unavailable on PATH')
        self.prefix = [str(Path(executable).absolute()), '--context', 'default']
        self.env = {k: os.environ[k] for k in ('HOME', 'XDG_RUNTIME_DIR', 'LANG') if k in os.environ}
        self.env['PATH'] = '/usr/bin:/bin'
        endpoint = self.call('context', 'inspect', 'default', '--format', '{{.Endpoints.docker.Host}}').strip()
        if endpoint != 'unix:///var/run/docker.sock':
            raise ValueError('qualification requires the default local Unix Docker daemon')
        self.identity = self.call('info', '--format', '{{.ID}}').strip()
        if not self.identity:
            raise ValueError('Docker daemon identity is unavailable')

    def call(self, *args):
        result = subprocess.run(self.prefix + list(args), env=self.env, capture_output=True,
                                text=True, timeout=20, check=True)
        if len(result.stdout) > MAX_ARCHIVE:
            raise ValueError('Docker metadata exceeds the bound')
        return result.stdout

    def guard(self, attempt):
        if self.call('info', '--format', '{{.ID}}').strip() != attempt['daemon']:
            raise ValueError('Docker daemon differs from attempt ownership')

    def image(self, image):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('image must be an explicit local immutable sha256 image ID')
        actual = self.call('image', 'inspect', image, '--format', '{{.Id}}').strip()
        if actual != image:
            raise ValueError('local image identity mismatch')
        return actual

    def containers(self, nonce):
        ids = self.call('ps', '-aq', '--no-trunc', '--filter', f'label={LABEL}={nonce}').split()
        if any(not HEX_ID.fullmatch(i) for i in ids) or len(ids) > 1:
            raise ValueError('unexpected attempt container identities/count')
        return ids

    def inspect(self, container):
        if not HEX_ID.fullmatch(container):
            raise ValueError('container must be an immutable ID')
        # Deliberately do not read Config.Env or dump complete inspect output.
        fields = {'id': '.Id', 'image': '.Image', 'running': '.State.Running', 'pid': '.State.Pid',
                  'oom_killed': '.State.OOMKilled', 'exit_code': '.State.ExitCode',
                  'restarting': '.State.Restarting', 'dead': '.State.Dead', 'mounts': '.Mounts',
                  'network': '.HostConfig.NetworkMode', 'privileged': '.HostConfig.Privileged',
                  'memory': '.HostConfig.Memory', 'cpus': '.HostConfig.NanoCpus',
                  'pids': '.HostConfig.PidsLimit', 'auto_remove': '.HostConfig.AutoRemove'}
        for key, label in (('nonce', LABEL), ('project', 'com.docker.compose.project'),
                           ('config', 'com.docker.compose.project.config_files')):
            fields[key] = f'index .Config.Labels "{label}"'
        template = '{' + ','.join(json.dumps(k) + ':{{json ' + v + '}}' for k, v in fields.items()) + '}'
        return json.loads(self.call('inspect', container, '--format', template))

    def archive(self, container):
        """Bound bytes while streaming, rather than buffering an unbounded cp."""
        with subprocess.Popen(self.prefix + ['cp', f'{container}:{OUTPUT}/.', '-'], env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
            try:
                chunks, size, deadline = [], 0, time.monotonic() + 15
                import select
                while True:
                    if time.monotonic() >= deadline:
                        raise ValueError('container archive deadline exceeded')
                    ready, _, _ = select.select([child.stdout], [], [], min(1, deadline-time.monotonic()))
                    if not ready:
                        continue
                    data = os.read(child.stdout.fileno(), 65536)
                    if not data:
                        break
                    size += len(data)
                    if size > MAX_ARCHIVE:
                        raise ValueError('container archive exceeds byte limit')
                    chunks.append(data)
                if child.wait(timeout=3) != 0:
                    raise ValueError('container archive copy failed')
                return b''.join(chunks)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=3)


def compose(image, nonce):
    return {'services': {'default': {
        'image': image, 'x-local': True, 'pull_policy': 'never',
        'command': ['sleep', 'infinity'], 'working_dir': '/tmp', 'user': '1000:1000',
        'network_mode': 'none', 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'cpus': 1.0, 'mem_limit': '256m', 'pids_limit': 64,
        'labels': {LABEL: nonce},
    }}}


def attempt_read(work, docker):
    work = private_root(work)
    attempt = read_json(work / 'attempt.json')
    if not re.fullmatch(r'[0-9a-f]{32}', attempt['nonce']):
        raise ValueError('invalid attempt nonce')
    data = (work / 'compose.json').read_bytes()
    if sha256(data) != attempt['compose_sha256'] or read_json(work / 'compose.json') != compose(attempt['image'], attempt['nonce']):
        raise ValueError('attempt Compose configuration changed')
    docker.guard(attempt)
    return attempt


def owned_state(work, attempt, docker, container):
    state = docker.inspect(container)
    if (state['id'] != container or state['nonce'] != attempt['nonce'] or state['image'] != attempt['image']
            or not isinstance(state['project'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}', state['project'])
            or state['config'] != str(Path(work) / 'compose.json')
            or state['mounts'] or state['network'] != 'none' or state['privileged'] or state['auto_remove']
            or state['memory'] != 268435456 or state['cpus'] != 1000000000 or state['pids'] != 64):
        raise ValueError('container ownership/configuration is not established')
    return state


def capture_ownership(work, attempt, docker):
    ids = docker.containers(attempt['nonce'])
    if len(ids) != 1:
        raise ValueError('expected exactly one owned sandbox container')
    state = owned_state(work, attempt, docker, ids[0])
    if not state['running'] or state['pid'] <= 0:
        raise ValueError('sandbox must be running before tools')
    groups = [s[3:] for s in Path(f'/proc/{state["pid"]}/cgroup').read_text().splitlines() if s.startswith('0::')]
    if len(groups) != 1 or ids[0] not in groups[0] or '..' in Path(groups[0]).parts:
        raise ValueError('local sandbox cgroup ownership is unavailable')
    receipt = dict(container=ids[0], project=state['project'], cgroup=groups[0])
    events = Path('/sys/fs/cgroup') / groups[0].lstrip('/') / 'memory.events'
    receipt['memory_events'] = memory_events(events)
    runner.write_json(Path(work) / 'sandbox-owner.json', receipt)
    return receipt


def memory_events(path):
    return {k: int(v) for k, v in (line.split() for line in Path(path).read_text().splitlines())}


def stopped(work, attempt, owner, docker, cgroup_root=Path('/sys/fs/cgroup')):
    docker.guard(attempt)
    if docker.containers(attempt['nonce']) != [owner['container']]:
        raise ValueError('owned container set changed')
    before = owned_state(work, attempt, docker, owner['container'])
    if before['project'] != owner['project']:
        raise ValueError('Compose project changed')
    group = Path(owner['cgroup'])
    if not group.is_absolute() or '..' in group.parts or owner['container'] not in str(group):
        raise ValueError('invalid sandbox cgroup receipt')
    directory = Path(cgroup_root) / str(group).lstrip('/')
    events = memory_events(directory / 'memory.events') if (directory / 'memory.events').exists() else None
    live_processes = len((directory / 'cgroup.procs').read_text().split()) if (directory / 'cgroup.procs').exists() else None
    docker.call('stop', '--time', '2', owner['container'])
    after = owned_state(work, attempt, docker, owner['container'])
    if after['running'] or after['pid'] != 0 or after['restarting'] or after['dead']:
        raise ValueError('sandbox process settlement is unknown')
    members = directory / 'cgroup.procs'
    if members.exists() and members.read_text().strip():
        raise ValueError('sandbox cgroup still has writers')
    return dict(container=owner['container'], stopped=True, cgroup_empty=True,
                oom_killed=after['oom_killed'], exit_code=after['exit_code'],
                live_processes_before_stop=live_processes,
                memory_events_before_stop=events, memory_events_at_start=owner.get('memory_events'))


def snapshot(archive, folder):
    """Validate all archive entries before writing any extracted member."""
    if len(archive) > MAX_ARCHIVE:
        raise ValueError('archive exceeds byte limit')
    if len(archive) < 1024 or len(archive) % 512 or archive[-1024:] != bytes(1024):
        raise ValueError('incomplete tar stream')
    files, names, total = [], set(), 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:', ignore_zeros=True) as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or '\\' in member.name:
                raise ValueError('unsafe archive path')
            name = path.as_posix().removeprefix('./')
            if name in names:
                raise ValueError('duplicate archive member')
            names.add(name)
            if len(names) > MAX_FILES or not (member.isfile() or member.isdir()):
                raise ValueError('nonregular or excessive archive members')
            if member.isdir():
                continue
            if len(path.parts) != 1 or name in ('', '.') or member.size < 0:
                raise ValueError('qualification output must be flat regular files')
            total += member.size
            if total > MAX_BYTES:
                raise ValueError('unpacked output exceeds byte limit')
            stream = tar.extractfile(member)
            data = stream.read(MAX_BYTES + 1)
            if len(data) != member.size:
                raise ValueError('truncated archive member')
            files.append((name, data))
    if not files:
        raise ValueError('no regular output files')
    folder = Path(folder)
    folder.mkdir(mode=0o700)
    manifest = []
    for name, data in sorted(files):
        path = folder / name
        with path.open('xb') as out:
            os.chmod(path, 0o400)
            out.write(data)
        manifest.append(dict(path=name, bytes=len(data), sha256=sha256(data)))
    return manifest


def verify_snapshot(work):
    work = private_root(work)
    seal = read_json(work / 'seal.json')
    if seal.get('schema') != 'cadagent.seal/1' or seal.get('attempt_sha256') != sha256((work / 'attempt.json').read_bytes()):
        raise ValueError('seal does not describe this attempt')
    folder = work / 'sealed'
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('invalid sealed directory')
    if sorted(p.name for p in folder.iterdir()) != sorted(r['path'] for r in seal['artifacts']):
        raise ValueError('sealed artifact set changed')
    for entry in seal['artifacts']:
        if PurePosixPath(entry['path']).name != entry['path']:
            raise ValueError('invalid sealed path')
        path = folder / entry['path']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['bytes'] or sha256(path.read_bytes()) != entry['sha256']:
            raise ValueError('sealed bytes changed')
    return seal


def cleanup(work, attempt, owner, docker):
    """Only the exact recorded project/config. Never call Inspect CLI cleanup."""
    docker.guard(attempt)
    state = owned_state(work, attempt, docker, owner['container'])
    if state['running'] or state['pid'] or state['project'] != owner['project']:
        raise ValueError('refuse cleanup before owned container settlement')
    attempt_read(work, docker)
    resources = project_resources(docker, owner['project'])
    if resources != dict(container=[owner['container']], network=[], volume=[]):
        raise ValueError('project contains resources outside the ownership receipt')
    docker.call('compose', '--project-name', owner['project'], '--file', str(Path(work) / 'compose.json'), 'down', '--timeout', '2')
    # This config declares no networks or volumes. Any project resource remaining
    # is a failure, even when compose down returned success.
    remaining = project_resources(docker, owner['project'])
    if any(remaining.values()) or docker.containers(attempt['nonce']):
        raise ValueError('owned Compose resources remain after cleanup')
    return dict(project=owner['project'], resources_absent=True)


def project_resources(docker, project):
    return {kind: docker.call(kind, 'ls', '-aq' if kind == 'container' else '-q', '--filter', f'label=com.docker.compose.project={project}').split()
            for kind in ('container', 'network', 'volume')}


def collect(work, image, source, case='normal'):
    groups = [s[3:] for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')]
    if len(groups) != 1 or not re.fullmatch(r'cad-eval-[a-zA-Z0-9_-]+\.service', Path(groups[0]).name):
        raise ValueError('collect must run in a retained cad-eval-*.service user unit')
    runtime_info = runtime(source)
    docker = Docker()
    docker.image(image)
    work = private_root(work, fresh=True)
    nonce = uuid.uuid4().hex
    runner.write_json(work / 'compose.json', compose(image, nonce))
    runner.write_json(work / 'cgroup.json', dict(path=groups[0]))
    attempt = dict(schema='cadagent.inspect-qualification/1', nonce=nonce, daemon=docker.identity,
                   image=image, runtime=runtime_info, case=case,
                   controller_sha256=controller_hashes(),
                   compose_sha256=sha256((work / 'compose.json').read_bytes()))
    runner.write_json(work / 'attempt.json', attempt)  # Before Inspect can create resources.
    # Inspect's own Docker subprocesses must use this same daemon. This changes
    # only the already isolated collector process, not the user's configuration.
    os.environ['DOCKER_CONTEXT'] = 'default'
    from inspect_ai import Task, eval as inspect_eval
    from inspect_ai.agent import react
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ModelOutput, get_model
    from inspect_ai.solver import solver
    from inspect_ai.tool import bash
    from inspect_ai.util import sandbox

    @solver
    def ownership():
        async def execute(state, generate):
            if case == 'pretool':
                raise ValueError('scripted failure before tool ownership receipt')
            connection = await sandbox().connection()
            owner = capture_ownership(work, attempt, docker)
            actual = docker.call('inspect', connection.container, '--format', '{{.Id}}').strip()
            if actual != owner['container']:
                raise ValueError('Inspect sandbox connection differs from owned container')
            if case == 'interrupted':
                import signal
                os.kill(os.getpid(), signal.SIGTERM)
            return state
        return execute

    # Host-only synthetic sentinels, never real credentials. No host path is mounted.
    sentinel = work / 'controller-answer.txt'
    sentinel.write_text('synthetic controller answer and credential sentinel\n')
    command = f'set -eu; mkdir -p {OUTPUT}; test ! -e {shlex.quote(str(sentinel))}; test ! -S /var/run/docker.sock; printf qualified > {OUTPUT}/result.txt'
    if case == 'detached':
        command += f'; python3 -c "import os,time; os.setsid(); open(\'{OUTPUT}/writer.ready\',\'w\').write(\'ready\'); time.sleep(60); open(\'{OUTPUT}/late.txt\',\'w\').write(\'late\')" </dev/null >/dev/null 2>&1 &'
        command += f'\nfor i in $(seq 1 100); do test ! -f {OUTPUT}/writer.ready || exit 0; sleep 0.01; done; exit 1'
    elif case == 'timeout':
        command += '; sleep 60'
    elif case == 'oom':
        command += '; python3 -c "x=bytearray(1024*1024*1024)"'
    elif case == 'symlink':
        command += f'; ln -s /etc/passwd {OUTPUT}/unsafe'
    elif case == 'wrong':
        command += f'; printf wrong > {OUTPUT}/result.txt'
    elif case not in ('normal', 'pretool', 'interrupted'):
        raise ValueError('unsupported inert qualification case')
    model = get_model('mockllm/model', custom_outputs=[
        ModelOutput.for_tool_call('mockllm', 'bash', {'command': command}, tool_call_id='inert-bash-1'),
        ModelOutput.from_content('mockllm', 'complete'),
    ])
    logs = inspect_eval(Task(dataset=[Sample(input='Execute the supplied inert control.')],
                             setup=ownership(), solver=react(tools=[bash(timeout=3)], submit=False, attempts=1),
                             sandbox=('docker', str(work / 'compose.json')), message_limit=6),
                        model=model, sandbox_cleanup=False, sandbox_prebuilt=True, score=False,
                        retry_on_error=0, task_retry_attempts=0, epochs=1, max_samples=1,
                        time_limit=30, max_tokens=128, max_retries=0, cache=False,
                        log_dir=str(work / 'logs'), log_format='json', display='none')
    events = [event.model_dump(mode='json', include={'event', 'id', 'function', 'completed', 'error', 'result'})
              for sample in (logs[0].samples or []) for event in sample.events if event.event == 'tool']
    runner.write_json(work / 'collection.json', dict(status=logs[0].status, model='mockllm/model', tool_events=events,
                       usage_source='synthetic; not provider measurement', collector_finished=True))
    return dict(awaiting_external_finalization=True, status=logs[0].status)


def finalize(work, unit):
    work = private_root(work)
    unit_state = runner.unit_receipt(work, unit)  # Before reading subject outputs/logs.
    runner.write_json(work / 'unit-receipt.json', unit_state)
    docker = Docker()
    attempt = attempt_read(work, docker)
    owner_path = work / 'sandbox-owner.json'
    if not owner_path.exists():
        # Startup can fail before the solver records ownership. Recover only the
        # controller-labelled container; no snapshot is accepted in this route.
        ids = docker.containers(attempt['nonce'])
        if not ids:
            raise ValueError('startup left no owned container; no qualifying output')
        state = owned_state(work, attempt, docker, ids[0])
        # Recovery may find a container that already exited before setup. There
        # is then no trustworthy pre-tool cgroup receipt: clean only these exact
        # owned resources, and never seal/qualify outputs in the recovery route.
        docker.call('stop', '--time', '2', ids[0])
        state = owned_state(work, attempt, docker, ids[0])
        if state['running'] or state['pid'] or state['restarting'] or state['dead']:
            raise ValueError('startup recovery could not stop the owned container')
        owner = dict(container=ids[0], project=state['project'])
        runner.write_json(work / 'sandbox-recovery.json', dict(**owner, cgroup_settlement='unknown; no output accepted'))
        cleanup_receipt = cleanup(work, attempt, owner, docker)
        runner.write_json(work / 'sandbox-cleanup.json', cleanup_receipt)
        result = dict(schema=attempt['schema'], passed=False, startup_recovered=True,
                      errors=['no pre-tool ownership receipt; output not accepted'],
                      physical_fit_verified=False, model_usefulness_measured=False)
        runner.write_json(work / 'result.json', result)
        return result
    else:
        owner, recovered = read_json(owner_path), False
    receipt = stopped(work, attempt, owner, docker)
    runner.write_json(work / 'sandbox-stop.json', receipt)
    errors = []
    try:
        artifacts = snapshot(docker.archive(owner['container']), work / 'sealed')
        runner.write_json(work / 'seal.json', dict(schema='cadagent.seal/1', artifacts=artifacts,
                                                 attempt_sha256=sha256((work / 'attempt.json').read_bytes())))
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
    try:
        cleanup_receipt = cleanup(work, attempt, owner, docker)
        runner.write_json(work / 'sandbox-cleanup.json', cleanup_receipt)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
    collection = read_json(work / 'collection.json') if (work / 'collection.json').exists() else {}
    before, start = receipt['memory_events_before_stop'], receipt['memory_events_at_start']
    oom_observed = before['oom_kill'] > start['oom_kill'] if before is not None and start is not None else None
    passed = (not errors and not recovered and unit_state['unit_success'] and not receipt['oom_killed']
              and oom_observed is False and collection.get('status') == 'success' and attempt['case'] in ('normal', 'detached'))
    tool_events = collection.get('tool_events', [])
    passed = passed and len(tool_events) == 1 and tool_events[0].get('completed') is not None and tool_events[0].get('error') is None
    if passed:
        verify_snapshot(work)
        passed = (work / 'sealed/result.txt').read_bytes() == b'qualified'
        if attempt['case'] == 'detached':
            passed = passed and receipt['live_processes_before_stop'] is not None and receipt['live_processes_before_stop'] > 1 and not (work / 'sealed/late.txt').exists()
    result = dict(schema=attempt['schema'], passed=passed, startup_recovered=recovered, errors=errors,
                  exec_oom_kill_observed=oom_observed,
                  physical_fit_verified=False, model_usefulness_measured=False)
    runner.write_json(work / 'result.json', result)
    return result


def qualify(work, source):
    """Require the complete retained inert control suite, not one happy path."""
    runtime(source)
    work = private_root(work)
    identities, controls = set(), {}
    for case in CASES:
        directory = private_root(work / case)
        attempt = read_json(directory / 'attempt.json')
        result = read_json(directory / 'result.json')
        unit = read_json(directory / 'unit-receipt.json')
        cleanup_state = read_json(directory / 'sandbox-cleanup.json')
        if (attempt.get('case') != case or attempt.get('runtime', {}).get('revision') != INSPECT_REVISION
                or attempt.get('controller_sha256') != controller_hashes()
                or cleanup_state.get('resources_absent') is not True):
            raise ValueError(f'{case}: incompatible attempt or missing cleanup evidence')
        identities.add((attempt['image'], attempt['daemon']))
        if case in ('normal', 'detached'):
            verify_snapshot(directory)
            if result.get('passed') is not True or unit.get('unit_success') is not True:
                raise ValueError(f'{case}: positive control failed')
        elif result.get('passed') is not False:
            raise ValueError(f'{case}: wrong output/execution was accepted')
        if case == 'pretool':
            if not result.get('startup_recovered') or (directory / 'seal.json').exists():
                raise ValueError('pretool: recovery incorrectly accepted output')
        elif case == 'interrupted':
            if unit.get('unit_success') is not False:
                raise ValueError('interrupted: no actual unsuccessful service result')
        elif case == 'oom':
            if result.get('exec_oom_kill_observed') is not True:
                raise ValueError('oom: no actual cgroup oom_kill increase observed')
        elif case == 'timeout':
            events = read_json(directory / 'collection.json').get('tool_events', [])
            if not any((event.get('error') or {}).get('type') == 'timeout' for event in events):
                raise ValueError('timeout: no actual tool timeout observed')
        elif case == 'symlink':
            if (directory / 'seal.json').exists() or not any('nonregular' in error for error in result.get('errors', [])):
                raise ValueError('symlink: unsafe output rejection not established')
        elif case == 'wrong':
            verify_snapshot(directory)
            if (directory / 'sealed/result.txt').read_bytes() != b'wrong':
                raise ValueError('wrong: no actual incorrect artifact retained')
        controls[case] = result['passed']
    if len(identities) != 1:
        raise ValueError('control suite used different image/daemon identities')
    return dict(passed=True, controls=controls, provider=wire_qualification(),
                real_model_called=False, native_cad_qualified=False)


def wire_qualification():
    """Real compatible-provider serialization against bounded host-only HTTP.

    This is not MockLLM: omitted usage must survive the actual SDK/adapter.
    No sandbox tool or real model is invoked by this fixture.
    """
    if any(k in os.environ for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')):
        raise ValueError('wire qualification requires proxy variables unset; loopback only')
    from inspect_ai.model import ChatMessageTool, ChatMessageUser, GenerateConfig, get_model
    from inspect_ai.tool import ToolInfo

    requests, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.connection.settimeout(3)
            length = int(self.headers.get('Content-Length', '0'))
            if self.path != '/v1/chat/completions' or not 0 < length <= 65536:
                self.send_error(400)
                return
            try:
                payload = json.loads(self.rfile.read(length))
                requests.append(payload)
                index = len(requests)
                if index > 5:
                    failures.append('unexpected retry/cache request')
                    self.send_error(400)
                    return
                if index == 5:
                    data = b'{"error":{"message":"scripted failure","type":"server_error"}}'
                    status = 500
                else:
                    message = {'role': 'assistant', 'content': 'complete'}
                    finish = 'stop'
                    if index in (1, 3):
                        message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                            'id': f'wire-{index}', 'type': 'function',
                            'function': {'name': 'bash', 'arguments': '{"command":"true"}' if index == 1 else '{broken'},
                        }]}
                        finish = 'tool_calls'
                    data = json.dumps({'id': f'response-{index}', 'object': 'chat.completion',
                                       'created': 1, 'model': 'inert', 'choices': [
                                           {'index': 0, 'message': message, 'finish_reason': finish}]}).encode()
                    status = 200  # Deliberately no usage field.
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                failures.append(type(exc).__name__)

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = False
        block_on_close = True

    server = Server(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    models = []

    async def exercise():
        config = GenerateConfig(max_retries=0, timeout=3, max_tokens=32, cache=False)
        model = get_model('openai-api/qualification/inert',
                          base_url=f'http://127.0.0.1:{server.server_port}/v1',
                          api_key='inert-synthetic-key', stream=False, responses_api=False, config=config)
        models.append(model)
        tools = [ToolInfo(name='bash', description='Inert schema only', parameters={
            'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command'],
        })]
        messages = [ChatMessageUser(content='inert')]
        first = await model.generate(messages, tools=tools)
        if first.usage is not None or not first.message.tool_calls:
            raise ValueError('provider invented missing usage or lost tool call')
        call = first.message.tool_calls[0]
        if call.id != 'wire-1' or call.function != 'bash' or call.arguments != {'command': 'true'}:
            raise ValueError('provider tool-call identity/arguments changed')
        messages += [first.message, ChatMessageTool(content='done', tool_call_id=call.id, function='bash')]
        second = await model.generate(messages, tools=tools)
        third = await model.generate([ChatMessageUser(content='malformed')], tools=tools)
        if second.usage is not None or third.usage is not None:
            raise ValueError('provider invented missing usage')
        if not third.message.tool_calls or not third.message.tool_calls[0].parse_error:
            raise ValueError('malformed tool arguments were accepted')
        # An identical request must hit the wire again with cache=False.
        repeated = await model.generate([ChatMessageUser(content='inert')], tools=tools)
        if repeated.usage is not None or repeated.message.tool_calls:
            raise ValueError('unexpected cached result for repeated request')
        try:
            await model.generate([ChatMessageUser(content='server-error')], tools=tools)
        except Exception:
            pass
        else:
            raise ValueError('scripted provider failure was accepted')

    async def exercise_and_close():
        try:
            await exercise()
        finally:
            for model in models:
                await model.api.aclose()

    try:
        asyncio.run(exercise_and_close())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    if thread.is_alive() or failures or len(requests) != 5:
        raise ValueError('wire fixture did not settle with exactly five requests')
    first, second = requests[:2]
    if (first.get('model') != 'inert' or first.get('max_tokens') != 32
            or first.get('tools', [{}])[0].get('function', {}).get('name') != 'bash'
            or not any(m.get('role') == 'tool' and m.get('tool_call_id') == 'wire-1' for m in second.get('messages', []))):
        raise ValueError('actual wire serialization does not match the fixture contract')
    return dict(passed=True, requests=5, missing_usage=None, real_model_called=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'collect', 'finalize', 'wire', 'qualify'))
    parser.add_argument('--work', type=Path)
    parser.add_argument('--image')
    parser.add_argument('--inspect-source', type=Path)
    parser.add_argument('--unit')
    parser.add_argument('--case', choices=CASES, default='normal')
    args = parser.parse_args()
    try:
        if args.action == 'preflight':
            result = preflight(args.inspect_source)
            print(json.dumps(result, allow_nan=False))
            return 0 if result['passed'] else 1
        if args.work is None:
            parser.error(f'{args.action} requires --work')
        if args.action == 'collect':
            if not args.image or not args.inspect_source:
                parser.error('collect requires --image and --inspect-source')
            result = collect(args.work, args.image, args.inspect_source, args.case)
        elif args.action == 'finalize':
            if not args.unit:
                parser.error('finalize requires --unit')
            result = finalize(args.work, args.unit)
        else:
            if not args.inspect_source:
                parser.error('qualify requires --inspect-source')
            if args.action == 'wire':
                runtime(args.inspect_source)
                result = wire_qualification()
            else:
                result = qualify(args.work, args.inspect_source)
        print(json.dumps(result, allow_nan=False))
    except (OSError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        print(json.dumps(dict(passed=False, error=str(exc))))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
