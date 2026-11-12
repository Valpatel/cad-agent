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
            return '\n'.join(self.remaining)
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
    assert docker.calls[0] == ('compose', '--project-name', 'inspect-inert-1', '--file', str(work / 'compose.json'), 'down', '--timeout', '2')
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


@pytest.mark.skipif(os.environ.get('CAD_EVAL_INSPECT_WIRE') != '1',
                    reason='optional pinned Inspect/OpenAI SDK environment; enable explicitly after setup review')
def test_actual_compatible_provider_missing_usage_and_request_counts():
    source = os.environ.get('CAD_EVAL_INSPECT_SOURCE')
    assert source, 'explicit pinned Inspect source required'
    adapter.runtime(source)
    result = adapter.wire_qualification()
    assert result == dict(passed=True, requests=4, missing_usage=None, real_model_called=False)
