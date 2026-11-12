"""Optional Inspect boundary controls; default tests never create containers."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/evaluation'))
import inspect_runner as adapter
import inspect_runtime_probe as probe


def archive(entries):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, content, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(content) if kind == tarfile.REGTYPE else 0
            item.linkname = '/etc/passwd' if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ''
            tar.addfile(item, io.BytesIO(content) if item.size else None)
    return out.getvalue()


def attempt(tmp_path):
    work = adapter.private_root(tmp_path / 'attempt', fresh=True)
    data = dict(nonce='a' * 32, image='sha256:' + 'b' * 64, daemon='local-daemon')
    adapter.runner.write_json(work / 'compose.json', adapter.compose(data['image'], data['nonce']))
    data['compose_sha256'] = adapter.sha256((work / 'compose.json').read_bytes())
    adapter.runner.write_json(work / 'attempt.json', data)
    return work, data


def test_good_snapshot_binds_exact_bytes_and_attempt(tmp_path):
    work, _ = attempt(tmp_path)
    artifacts = adapter.snapshot(archive([('result.txt', b'qualified', tarfile.REGTYPE)]), work / 'sealed')
    adapter.runner.write_json(work / 'seal.json', dict(schema='cadagent.seal/1', artifacts=artifacts,
                             attempt_sha256=adapter.sha256((work / 'attempt.json').read_bytes())))
    assert adapter.verify_snapshot(work)['artifacts'][0]['bytes'] == 9
    # The same consumer must reject changed output, not accept the old verdict.
    result = work / 'sealed/result.txt'
    result.chmod(0o600)
    result.write_bytes(b'incorrect')
    with pytest.raises(ValueError, match='sealed bytes changed'):
        adapter.verify_snapshot(work)
    result.write_bytes(b'qualified')
    (work / 'attempt.json').write_text('{}')
    with pytest.raises(ValueError, match='seal does not describe'):
        adapter.verify_snapshot(work)


@pytest.mark.parametrize('name,kind', [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                         ('nested/output', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                         ('hardlink', tarfile.LNKTYPE), ('device', tarfile.CHRTYPE), ('fifo', tarfile.FIFOTYPE)])
def test_unsafe_archive_never_writes_partial_snapshot(tmp_path, name, kind):
    blob = archive([('good', b'first', tarfile.REGTYPE), (name, b'bad', kind)])
    with pytest.raises(ValueError):
        adapter.snapshot(blob, tmp_path / 'sealed')
    assert not (tmp_path / 'sealed').exists()
    assert not (tmp_path / 'escape').exists()


def test_duplicates_oversize_count_and_partial_archive_fail(tmp_path):
    cases = [archive([('same', b'a', tarfile.REGTYPE), ('same', b'b', tarfile.REGTYPE)]),
             archive([('large', b'a' * (adapter.MAX_BYTES + 1), tarfile.REGTYPE)]),
             archive([(str(i), b'', tarfile.REGTYPE) for i in range(adapter.MAX_FILES + 1)]),
             archive([('short', b'value', tarfile.REGTYPE)])[:600]]
    for index, blob in enumerate(cases):
        with pytest.raises((ValueError, tarfile.TarError)):
            adapter.snapshot(blob, tmp_path / str(index))
        assert not (tmp_path / str(index)).exists()


def test_hidden_second_archive_cannot_smuggle_a_link(tmp_path):
    blob = archive([('good', b'x', tarfile.REGTYPE)]) + archive([('evil', b'', tarfile.SYMTYPE)])
    with pytest.raises(ValueError, match='nonregular'):
        adapter.snapshot(blob, tmp_path / 'sealed')


def test_symlinked_work_and_sealed_file_refused(tmp_path):
    (tmp_path / 'alias').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        adapter.private_root(tmp_path / 'alias/work', fresh=True)
    work, _ = attempt(tmp_path)
    artifacts = adapter.snapshot(archive([('result.txt', b'qualified', tarfile.REGTYPE)]), work / 'sealed')
    adapter.runner.write_json(work / 'seal.json', dict(schema='cadagent.seal/1', artifacts=artifacts,
                             attempt_sha256=adapter.sha256((work / 'attempt.json').read_bytes())))
    (work / 'sealed/result.txt').unlink()
    (work / 'sealed/result.txt').symlink_to(work / 'attempt.json')
    with pytest.raises(ValueError, match='sealed bytes changed'):
        adapter.verify_snapshot(work)


class FakeDocker:
    """Simulate daemon replies only; these tests do not qualify real isolation."""
    def __init__(self, work, data):
        self.calls = []
        self.identity = data['daemon']
        self.remaining = []
        self.ids = ['c' * 64]
        self.state = dict(id=self.ids[0], nonce=data['nonce'], image=data['image'], project='inspect-inert-1',
                          config=str(work / 'compose.json'), mounts=[], network='none', privileged=False,
                          memory=268435456, cpus=1000000000, pids=64, auto_remove=False,
                          running=False, pid=0, restarting=False, dead=False, oom_killed=False, exit_code=0)

    def call(self, *args):
        self.calls.append(args)
        if args[0] == 'stop':
            self.state.update(running=False, pid=0)
        if args[0] == 'compose':
            self.ids = []
        if len(args) > 1 and args[1] == 'ls':
            return '\n'.join((self.ids if args[0] == 'container' else []) + (self.remaining if not self.ids else []))
        return ''

    def guard(self, data):
        if data['daemon'] != self.identity:
            raise ValueError('Docker daemon differs')

    def containers(self, nonce):
        return self.ids

    def inspect(self, container):
        return dict(self.state)


@pytest.mark.parametrize('change', [{'nonce': 'wrong'}, {'image': 'sha256:' + 'd' * 64},
                                  {'config': '/unrelated/compose.json'}, {'mounts': ['host-bind']},
                                  {'network': 'bridge'}, {'privileged': True}, {'memory': 0},
                                  {'pids': -1}, {'auto_remove': True}])
def test_wrong_ownership_or_weak_boundary_prevents_mutation(tmp_path, change):
    work, data = attempt(tmp_path)
    docker = FakeDocker(work, data)
    docker.state.update(change)
    owner = dict(container='c' * 64, project='inspect-inert-1', cgroup='/docker-' + 'c' * 64 + '.scope')
    with pytest.raises(ValueError):
        adapter.stopped(work, data, owner, docker)
    assert not docker.calls


def test_changed_config_or_daemon_prevents_finalization(tmp_path):
    work, data = attempt(tmp_path)
    docker = FakeDocker(work, data)
    assert adapter.attempt_read(work, docker) == data
    docker.identity = 'different-daemon'
    with pytest.raises(ValueError, match='daemon differs'):
        adapter.attempt_read(work, docker)
    docker.identity = data['daemon']
    (work / 'compose.json').write_text('{}')
    with pytest.raises(ValueError, match='configuration changed'):
        adapter.attempt_read(work, docker)
    assert not docker.calls


def test_stopped_container_is_not_enough_while_cgroup_has_writer(tmp_path):
    work, data = attempt(tmp_path)
    docker = FakeDocker(work, data)
    group = '/docker-' + 'c' * 64 + '.scope'
    directory = tmp_path / group.lstrip('/')
    directory.mkdir()
    (directory / 'memory.events').write_text('oom 1\noom_kill 1\n')
    (directory / 'cgroup.procs').write_text('123\n')
    owner = dict(container='c' * 64, project='inspect-inert-1', cgroup=group, memory_events={'oom': 0, 'oom_kill': 0})
    with pytest.raises(ValueError, match='still has writers'):
        adapter.stopped(work, data, owner, docker, tmp_path)
    (directory / 'cgroup.procs').write_text('')
    receipt = adapter.stopped(work, data, owner, docker, tmp_path)
    assert receipt['memory_events_before_stop']['oom_kill'] == 1
    assert receipt['oom_killed'] is False  # Exec-child OOM and init OOM are distinct.


def test_cleanup_success_exit_is_not_resource_absence_receipt(tmp_path):
    work, data = attempt(tmp_path)
    docker = FakeDocker(work, data)
    owner = dict(container='c' * 64, project='inspect-inert-1')
    docker.remaining = ['stopped-but-still-present']
    with pytest.raises(ValueError, match='resources remain'):
        adapter.cleanup(work, data, owner, docker)
    assert ('compose', '--project-name', 'inspect-inert-1', '--file', str(work / 'compose.json'), 'down', '--timeout', '2') in docker.calls
    assert ('container', 'ls', '-aq', '--filter', 'label=com.docker.compose.project=inspect-inert-1') in docker.calls


def test_host_settlement_must_precede_any_docker_or_artifact_access(tmp_path, monkeypatch):
    work, _ = attempt(tmp_path)
    def active(*args):
        raise ValueError('collector still active')
    monkeypatch.setattr(adapter.runner, 'unit_receipt', active)
    monkeypatch.setattr(adapter, 'Docker', lambda: pytest.fail('Docker touched before host settlement'))
    with pytest.raises(ValueError, match='collector still active'):
        adapter.finalize(work, 'cad-eval-test.service')
    assert not (work / 'seal.json').exists()


@pytest.mark.parametrize('payload,unit_success,remaining,expected', [
    (b'qualified', True, [], True), (b'wrong', True, [], False),
    (b'qualified', False, [], False), (b'qualified', True, ['leftover'], False),
])
def test_finalize_accepts_only_settled_correct_cleaned_bytes(tmp_path, monkeypatch, payload, unit_success, remaining, expected):
    work, data = attempt(tmp_path)
    data.update(schema='cadagent.inspect-qualification/1', case='normal')
    (work / 'attempt.json').write_text(json.dumps(data))
    docker = FakeDocker(work, data)
    docker.remaining = remaining
    group = '/docker-' + 'c' * 64 + '.scope'
    directory = tmp_path / group.lstrip('/')
    directory.mkdir()
    (directory / 'memory.events').write_text('oom 0\noom_kill 0\n')
    (directory / 'cgroup.procs').write_text('')
    adapter.runner.write_json(work / 'sandbox-owner.json', dict(container='c' * 64, project='inspect-inert-1',
                             cgroup=group, memory_events={'oom': 0, 'oom_kill': 0}))
    adapter.runner.write_json(work / 'collection.json', dict(status='success', tool_events=[
        dict(id='inert-bash-1', function='bash', completed='retained', error=None)]))
    host_settled = []
    def unit_receipt(*args):
        host_settled.append(True)
        return dict(unit_success=unit_success)
    def copied(container):
        assert host_settled and not docker.state['running'] and docker.state['pid'] == 0
        return archive([('result.txt', payload, tarfile.REGTYPE)])
    docker.archive = copied
    original_stop = adapter.stopped
    monkeypatch.setattr(adapter, 'stopped', lambda *args: original_stop(*args, cgroup_root=tmp_path))
    monkeypatch.setattr(adapter.runner, 'unit_receipt', unit_receipt)
    monkeypatch.setattr(adapter, 'Docker', lambda: docker)
    result = adapter.finalize(work, 'cad-eval-test.service')
    assert result['passed'] is expected
    assert adapter.verify_snapshot(work)['artifacts'][0]['sha256'] == adapter.sha256(payload)
    assert any(c[0] == 'compose' for c in docker.calls)


def test_pretool_failure_recovers_only_owned_resources_without_accepting_output(tmp_path, monkeypatch):
    work, data = attempt(tmp_path)
    data.update(schema='cadagent.inspect-qualification/1', case='pretool')
    (work / 'attempt.json').write_text(json.dumps(data))
    docker = FakeDocker(work, data)
    monkeypatch.setattr(adapter.runner, 'unit_receipt', lambda *args: dict(unit_success=False))
    monkeypatch.setattr(adapter, 'Docker', lambda: docker)
    result = adapter.finalize(work, 'cad-eval-test.service')
    assert result['passed'] is False and result['startup_recovered'] is True
    assert not (work / 'seal.json').exists() and not (work / 'sealed').exists()
    assert not docker.ids


def test_unrecorded_project_resource_prevents_compose_down(tmp_path, monkeypatch):
    work, data = attempt(tmp_path)
    docker = FakeDocker(work, data)
    monkeypatch.setattr(adapter, 'project_resources', lambda *args: dict(container=docker.ids + ['foreign'], network=[], volume=[]))
    with pytest.raises(ValueError, match='outside the ownership receipt'):
        adapter.cleanup(work, data, dict(container='c' * 64, project='inspect-inert-1'), docker)
    assert not any(c[0] == 'compose' for c in docker.calls)


@pytest.mark.skipif(sys.platform != 'linux', reason='POSIX streaming subprocess control')
def test_actual_archive_subprocess_is_killed_on_excess_output(tmp_path):
    script = tmp_path / 'fake_cp.py'
    pid = tmp_path / 'pid'
    script.write_text('import os,time\nfrom pathlib import Path\n'
                      f'Path({str(pid)!r}).write_text(str(os.getpid()))\n'
                      'os.write(1,b"x"*3000000)\ntime.sleep(60)\n')
    docker = object.__new__(adapter.Docker)
    docker.prefix = [sys.executable, str(script)]
    docker.env = {'PATH': '/usr/bin:/bin'}
    with pytest.raises(ValueError, match='exceeds byte limit'):
        docker.archive('c' * 64)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid.read_text()), 0)


def test_explicit_qualification_fails_missing_prerequisites(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'tools/evaluation/inspect_runner.py'),
                             'qualify', '--work', str(tmp_path), '--inspect-source', str(tmp_path / 'missing')],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(result.stdout)['passed'] is False


def test_phase1_uv_extraction_whitelist_prevents_executing_unexpected_members(tmp_path):
    path = tmp_path / 'uv.tar.gz'
    def packed(entries):
        with tarfile.open(path, mode='w:gz') as tar:
            for name, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = 1 if kind == tarfile.REGTYPE else 0
                info.linkname = '/unrelated/executable'
                tar.addfile(info, io.BytesIO(b'x') if info.size else None)
    prefix = 'uv-x86_64-unknown-linux-gnu/'
    packed([(prefix + 'uv', tarfile.REGTYPE), (prefix + 'uvx', tarfile.REGTYPE)])
    probe.extract_uv(path, tmp_path / 'tool')
    assert (tmp_path / 'tool/uv').read_bytes() == b'x'
    packed([(prefix + 'uv', tarfile.SYMTYPE), (prefix + 'uvx', tarfile.REGTYPE)])
    with pytest.raises(ValueError, match='member/type'):
        probe.extract_uv(path, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()
    packed([(prefix + 'uv', tarfile.REGTYPE), ('../escape', tarfile.REGTYPE)])
    with pytest.raises(ValueError, match='member/type'):
        probe.extract_uv(path, tmp_path / 'bad')
    assert not (tmp_path / 'escape').exists()
    packed([(prefix.rstrip('/'), tarfile.DIRTYPE), (prefix.rstrip('/'), tarfile.DIRTYPE),
            (prefix + 'uv', tarfile.REGTYPE), (prefix + 'uvx', tarfile.REGTYPE)])
    with pytest.raises(ValueError, match='duplicate or excessive'):
        probe.extract_uv(path, tmp_path / 'duplicate')
    assert not (tmp_path / 'duplicate').exists()


def test_phase1_bounds_decompressed_headers_before_tar_parsing(tmp_path, monkeypatch):
    import gzip
    path = tmp_path / 'uv.tar.gz'
    with gzip.open(path, 'wb') as out:
        out.write(b'x' * 10000)
    monkeypatch.setattr(probe, 'MAX_TAR_BYTES', 9999)
    with pytest.raises(ValueError, match='decompressed uv archive exceeds'):
        probe.extract_uv(path, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


@pytest.mark.skipif(sys.platform != 'linux', reason='POSIX owned-group metadata probe')
def test_phase1_actual_timeout_retains_invocation_failure_and_settlement(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'SOURCE_HASHES', {})
    command = [sys.executable, '-c', 'import time; print("partial",flush=True); time.sleep(60)']
    with pytest.raises(ValueError, match='retain its receipt'):
        probe.metadata_command(tmp_path, 0, command, tmp_path, {'PATH': '/usr/bin:/bin'}, timeout=.1)
    invocation = json.loads((tmp_path / '0.invocation.json').read_text())
    receipt = json.loads((tmp_path / '0.receipt.json').read_text())
    assert invocation['argv'] == command and receipt['argv'] == command
    assert receipt['timed_out'] is True and receipt['group_settled'] is True
    assert receipt['exit_code'] != 0
    assert receipt['stdout_sha256'] == adapter.sha256((tmp_path / '0.stdout').read_bytes())
    assert (tmp_path / '0.stdout').read_text() == 'partial\n'
    with pytest.raises(ProcessLookupError):
        os.kill(receipt['pid'], 0)


def test_phase1_missing_executable_still_records_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'SOURCE_HASHES', {})
    with pytest.raises(ValueError, match='retain its receipt'):
        probe.metadata_command(tmp_path, 0, ['/absent/uv'], tmp_path, {'PATH': '/usr/bin:/bin'})
    receipt = json.loads((tmp_path / '0.receipt.json').read_text())
    assert receipt['exit_code'] is None and receipt['pid'] is None
    assert 'FileNotFoundError' in receipt['error'] and receipt['group_settled'] is None


@pytest.mark.skipif(os.environ.get('CAD_EVAL_INSPECT_WIRE') != '1',
                    reason='optional pinned Inspect/OpenAI SDK environment; enable explicitly after setup review')
def test_actual_compatible_provider_missing_usage_and_request_counts():
    source = os.environ.get('CAD_EVAL_INSPECT_SOURCE')
    assert source, 'explicit pinned Inspect source required'
    adapter.runtime(source)
    result = adapter.wire_qualification()
    assert result == dict(passed=True, requests=5, missing_usage=None, real_model_called=False)
