"""One no-install homepage-model collection. Run only through an independently reviewed fleet packet.

Importing this module performs no network, subprocess, CAD, installation or output write.
This captures a candidate only; publication must wait for the product source's protected main incorporation.
"""
from pathlib import Path
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import pwd
import signal
import stat
import subprocess
import sys
import tarfile
import time

PRODUCT_SHA = '3a40891962b0b0a04625e070700f1d130bea3c7b'
TOOLKIT_SHA = 'e662a1ce79b4f63f7352b9d065c5027f77d53a81'
HARDWARE = '346f5a5623560177390ad8cf207e5b8331ab5bae'
PRODUCER_SHA256 = '30bf6063cd0ac21eaa194ad4c7ba827f3f4193f75ab3cfecd763eae6b54c29e1'
COLLECTOR_SHA256 = '2008d1b935203110c5218bb1fa8e660a94c7100ee3ef4a20622d6fc23920e40f'
CONFIG_SHA256 = '64af5779dbce70bfa9f646fe7cb91c8ca828b373c3cc0bc630f5a1615e85138f'
HELPER_SHA256 = '8c653277d2aee9fbfd08acb07c23c6542cdd04930804180a111352666110499e'
PROTECTED_TREES = {'hardware/cad/legs': 'd50babdc4a99f3c4256a2959174b6aa9aefe64ba',
                   'hardware/exports/leg': '0aa1ec7c9cf8f31d7039d6b2b09d64b1037ae7d0'}
RETIRED = {'adapter_plate_front', 'adapter_plate_rear', 'bay_door_front', 'bay_door_rear', 'bay_floor',
           'bay_rail_l', 'bay_rail_r', 'bay_side_l', 'bay_side_r', 'bay_skid_1', 'bay_skid_2', 'bay_skid_3', 'bay_skid_4'}
HOLDERS = {'end_pack_holder_front', 'end_pack_holder_rear', 'end_foot_front', 'end_foot_rear'}
BATTERY_BOUNDS = [-286.775, -48.5, -87.04, 286.775, 48.5, 49.96]
ROOT = OUT = None
WORK_DEADLINE = 0
processes_quiescent = True
results = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def git(root, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(root), '-C', str(root), *args],
                                   text=True, timeout=30).strip()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(root):
    """Complete regular-file bytes; reject aliases/nonregular leaves instead of omitting them."""
    rows = {}
    for path in sorted(Path(root).rglob('*')):
        st = path.lstat()
        if stat.S_ISDIR(st.st_mode):
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ValueError('Nonregular or hardlinked output: ' + str(path))
        rows[path.relative_to(root).as_posix()] = {'bytes': st.st_size, 'sha256': sha(path)}
    return rows


def tracked(root):
    return {'head': git(root, 'rev-parse', 'HEAD'),
            'status': git(root, 'status', '--porcelain', '--untracked-files=all'),
            'files': {n: sha(root / n) for n in git(root, 'ls-files', '-z').split('\0') if n}}


def archive_model():
    """Seal all available candidate bytes before decoding/asserting; safe after owned groups settle."""
    model = OUT / 'model'
    if not model.exists():
        return {}
    members = inventory(model)
    if len(members) > 20 or sum(p['bytes'] for p in members.values()) > 128 * 1024 * 1024:
        raise ValueError('Unexpected candidate inventory size')
    save('model-members.json', members)
    path = OUT / 'model-produced.tgz'
    with tarfile.open(path, 'x:gz') as tar:
        for name in members:
            info = tar.gettarinfo(str(model / name), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            with (model / name).open('rb') as stream:
                tar.addfile(info, stream)
    results['candidate_archive_sha256'] = sha(path)
    return members


def validate_end_packs(model):
    """The old model shares battery names; source/group bounds and removed bay members are essential."""
    source = model['source']
    names = [n for group in source['members'].values() for n in group]
    if len(names) != len(set(names)) or len(names) != 224:
        raise ValueError('Unexpected actual source-member count; investigate, never force it')
    if source['revision'] != PRODUCT_SHA or source['hardware_tree'] != HARDWARE:
        raise ValueError('Wrong original end-pack source')
    if not HOLDERS <= set(names) or RETIRED & set(names):
        raise ValueError('Old belly enclosure or missing end-pack supports')
    if set(source['members']['battery']) != {'item.battery_front', 'item.battery_rear'}:
        raise ValueError('Missing original pair of packs')
    actual = next(p['bounds_mm'] for p in model['parts'] if p['name'] == 'battery')
    if len(actual) != 6 or any(abs(a - b) > .02 for a, b in zip(actual, BATTERY_BOUNDS)):
        raise ValueError('Battery placement differs from accepted original end-pack bounds')
    return {'source_parts': len(names), 'visible_groups': len(model['parts']), 'battery_bounds_mm': actual}


def decode(directory, toolkit, expected_producer):
    """Executed only as a separate retained-runtime child; no CAD kernel is imported here."""
    sys.path.insert(0, str(toolkit / 'software'))
    import numpy as np
    import cadagent
    from cadagent.publish.view import unpack_model
    assert Path(cadagent.__file__).resolve().is_relative_to((toolkit / 'software/cadagent').resolve())
    model = json.loads((directory / 'gyropup.json').read_text())
    data = (directory / 'gyropup.bin').read_bytes()
    save('observed-model.json', {'source_parts': sum(map(len, model['source']['members'].values())),
                                'visible_groups': len(model['parts']), 'bytes': len(data),
                                'triangles': model['triangles'],
                                'battery_bounds_mm': [p['bounds_mm'] for p in model['parts'] if p['name'] == 'battery']})
    actual = validate_end_packs(model)
    actual.update(bytes=len(data), triangles=model['triangles'])
    save('observed-model.json', actual)
    assert set(inventory(directory)) == {'gyropup.json', 'gyropup.bin'}
    assert model['schema'] == 'cad-agent-model/1' and model['bin'] == 'gyropup.bin'
    assert len(data) == model['bytes'] and sha(directory / 'gyropup.bin') == model['sha256']
    assert len(data) < 400 * 1024, 'Unchanged homepage byte budget exceeded; no policy change authorized'
    source = model['source']
    assert source['producer_revision'] == expected_producer and source['producer_sha256'] == PRODUCER_SHA256
    assert source['collector_sha256'] == COLLECTOR_SHA256 and len(source['files']) == 95
    cfg = json.loads((Path(os.environ['SHOWCASE_PRODUCT']) / 'tools/engineering/robot/readme-design.json').read_text())
    assert source['files'] == cfg['source']['files'] and source['runtime'] == cfg['runtime']
    visible = sorted(set(source['members']) - set(source['left_out']))
    assert visible == sorted(p['name'] for p in model['parts']) and len(visible) == 32
    producer = load('original_showcase_policy', ROOT / 'tools/gyropup_showcase.py')
    assert source['left_out'] == list(producer.WEB_SKIP)
    parts = unpack_model(model, data)
    assert len(parts) == len(model['parts'])
    assert sum(len(tri) for _, tri in parts) == model['triangles']
    for meta, (vertices, triangles) in zip(model['parts'], parts):
        assert len(vertices) == meta['vertices'] and len(triangles) == meta['triangles']
        assert np.isfinite(vertices).all() and triangles.min() >= 0 and triangles.max() < len(vertices)
        bounds = np.array(meta['bounds_mm'])
        got = np.r_[vertices.min(axis=0), vertices.max(axis=0)]
        inward = np.r_[got[:3] - bounds[:3], bounds[3:] - got[3:]]
        assert (inward > -.02).all() and (inward < 1).all(), meta['name']
    save('decode.json', {'status': 'PASS_MODEL_ONLY', **actual, 'physical_qualified': False})


def settle_owned_group(proc):
    """Kill and reap our group even after its original leader has exited."""
    signalled=False;reaped=[]
    try:os.killpg(proc.pid,signal.SIGKILL);signalled=True
    except ProcessLookupError:pass
    proc.wait(timeout=5)
    deadline=time.monotonic()+3
    while True:
        while True:
            try:pid,status=os.waitpid(-proc.pid,os.WNOHANG)
            except ChildProcessError:break
            if pid==0:break
            reaped.append({'pid':pid,'status':status})
        try:os.killpg(proc.pid,0)
        except ProcessLookupError:return {'group_gone':True,'signalled':signalled,'reaped':reaped}
        if time.monotonic()>=deadline:return {'group_gone':False,'signalled':signalled,'reaped':reaped}
        time.sleep(.02)


def phase(name,command,expected=0,timeout=120):
 global processes_quiescent
 timeout=min(timeout,WORK_DEADLINE-time.monotonic());assert timeout>0,'Work deadline reached before '+name
 start=time.monotonic();record={'command':command,'expected_exit':expected,'timeout_seconds':timeout};child=None;cleanup_errors=[]
 print('START '+name,flush=True)
 try:
  with (OUT/(name+'.log')).open('x') as stream:
   processes_quiescent=False
   blocked_before_spawn=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
   def child_unmask():signal.pthread_sigmask(signal.SIG_SETMASK,blocked_before_spawn)
   try:child=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=child_unmask)
   finally:signal.pthread_sigmask(signal.SIG_SETMASK,blocked_before_spawn)
   try:record['exit']=child.wait(timeout=timeout)
   except subprocess.TimeoutExpired:record['timed_out']=True
 except BaseException as exc:
  record['original_error']=type(exc).__name__+': '+str(exc)
  raise
 finally:
  if child is not None:
   record['pid']=child.pid
   try:
    cleanup=settle_owned_group(child);record['process_cleanup']=cleanup;processes_quiescent=cleanup['group_gone']
   except BaseException as exc:
    processes_quiescent=False;cleanup_errors.append('Settle: '+type(exc).__name__+': '+str(exc))
  record['seconds']=time.monotonic()-start
  if cleanup_errors:record['cleanup_errors']=cleanup_errors
  results['phases'][name]=record
  try:save('phase-results.json',results)
  except BaseException as exc:cleanup_errors.append('Phase record: '+type(exc).__name__+': '+str(exc))
  try:print('END '+name+' '+json.dumps(record),flush=True)
  except BaseException as exc:cleanup_errors.append('Phase log: '+type(exc).__name__+': '+str(exc))
 if cleanup_errors:raise RuntimeError('; '.join(cleanup_errors))
 assert processes_quiescent,'Owned group not quiescent; no archive'
 assert record.get('exit')==expected,name+' failed/incomplete; retain actual logs'


def main(argv=None):
    global ROOT, OUT, WORK_DEADLINE, processes_quiescent, results
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Exact committed cad-agent producer checkout')
    parser.add_argument('--contract-json', required=True, help='Reviewed existing runtime/toolkit identity, no install')
    parser.add_argument('--decode-only', action='store_true')
    args = parser.parse_args(argv)
    ROOT = Path(__file__).resolve().parents[3]
    OUT = Path(os.environ['FLEET_RUN_OUT']).resolve()
    contract = json.loads(args.contract_json)
    toolkit = Path(contract['toolkit']).resolve()
    venv = Path(contract['venv']).resolve()
    product = Path(os.environ['FLEET_RUN_DIR']).resolve() / 'showcase-gyropup'
    if args.decode_only:
        decode(OUT / 'model', toolkit, args.source)
        return
    os.umask(0o077)
    sys.dont_write_bytecode = True
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', GIT_OPTIONAL_LOCKS='0',
                      GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                      SHOWCASE_PRODUCT=str(product))
    for key in ('PYTHONPATH', 'PYTHONHOME', 'GIT_CONFIG_COUNT', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        os.environ.pop(key, None)
    assert not any(k.startswith('GYROPUP_') for k in os.environ)
    assert not os.environ.get('LD_PRELOAD') and not os.environ.get('LD_LIBRARY_PATH')
    assert pwd.getpwuid(os.getuid()).pw_name == contract['slot_user'], 'Wrong retained-runtime sharing slot'
    assert os.environ.get('SLURM_CPUS_PER_TASK') == '4'
    allowed = sorted(os.sched_getaffinity(0)); assert len(allowed) >= 4
    os.sched_setaffinity(0, set(allowed[:4]))
    assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    def interrupted(signum, frame):
        raise KeyboardInterrupt('received signal ' + str(signum))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    WORK_DEADLINE = time.monotonic() + 1140
    results = {'status': 'FAILED_OR_INCOMPLETE', 'adoption_approved': False, 'phases': {}, 'guards': {},
               'errors': [], 'product_source': PRODUCT_SHA, 'producer_source': args.source}
    before, captures, members = {}, {}, {}
    passed = False
    primary = None
    try:
        assert ROOT == Path.cwd().resolve() and git(ROOT, 'rev-parse', 'HEAD') == args.source
        assert not git(ROOT, 'status', '--porcelain', '--untracked-files=all')
        for a in (ROOT, OUT, product, toolkit, venv):
            for b in (ROOT, OUT, product, toolkit, venv):
                assert a == b or (not a.is_relative_to(b) and not b.is_relative_to(a)), 'Overlapping source/output/runtime'
        assert OUT.is_dir() and not product.exists() and not (OUT / 'model').exists()
        assert sha(ROOT / 'tools/gyropup_showcase.py') == PRODUCER_SHA256
        captures['producer'] = lambda: tracked(ROOT)
        before['producer'] = captures['producer'](); save('producer-before.json', before['producer'])
        phase('product-init', ['git', 'init', '-q', str(product)], timeout=30)
        phase('product-remote', ['git', '-C', str(product), 'remote', 'add', 'origin',
                                 'https://github.com/Valpatel/gyropup.git'], timeout=30)
        phase('product-fetch', ['git', '-C', str(product), '-c', 'credential.helper=', '-c', 'core.askPass=',
                                'fetch', '--progress', '--depth', '1', 'origin', PRODUCT_SHA], timeout=240)
        phase('product-checkout', ['git', '-C', str(product), 'checkout', '-q', '--detach', 'FETCH_HEAD'], timeout=30)
        assert git(product, 'rev-parse', 'HEAD') == PRODUCT_SHA
        assert git(product, 'rev-parse', 'HEAD:hardware') == HARDWARE
        assert not git(product, 'status', '--porcelain', '--untracked-files=all')
        for path, expected in PROTECTED_TREES.items():
            assert git(product, 'rev-parse', 'HEAD:' + path) == expected
        hashes = {'tools/engineering/robot/readme_design.py': HELPER_SHA256,
                  'tools/engineering/robot/readme-design.json': CONFIG_SHA256,
                  'tools/engineering/robot/robot_view.py': COLLECTOR_SHA256,
                  'tools/site/assembly/robot_runtime.py': '1a6a7cabee06b4a17802dd8086b1eb1a8840027504de74a9b145e5681399a753'}
        for path, expected in hashes.items():
            assert sha(product / path) == expected
        runtime_guard = load('retained_identity', product / 'tools/site/assembly/robot_runtime.py')
        captures.update(product=lambda: tracked(product), hardware=lambda: inventory(product / 'hardware'),
                        runtime=lambda: runtime_guard.tree(venv), toolkit=lambda: runtime_guard.tree(toolkit))
        for role in ('product', 'hardware', 'runtime', 'toolkit'):
            before[role] = captures[role](); save(role + '-before.json', before[role])
        for role in ('runtime', 'toolkit'):
            assert runtime_guard.fingerprint(before[role]) == contract[role + '_fingerprint'], role + ' changed'
        assert git(toolkit, 'rev-parse', 'HEAD') == TOOLKIT_SHA and not git(toolkit, 'status', '--porcelain')
        producer = load('showcase_preflight', ROOT / 'tools/gyropup_showcase.py')
        helper, cfg, files = producer.current_source(product, toolkit)
        assert len(files) == 95 and cfg['source']['hardware_tree'] == HARDWARE
        baseline = json.loads((product / '.agents/plans/end-packs/baseline.json').read_text())
        assert len(baseline['collection261_leg_mesh_sha256']) == 80
        for path, expected in baseline['protected_leg_sources_sha256'].items():
            assert sha(product / path) == expected
        save('input-preflight.json', {'producer': args.source, 'product': PRODUCT_SHA, 'toolkit': TOOLKIT_SHA,
                                     'source': cfg['source'], 'runtime': cfg['runtime'],
                                     'protected_leg_trees': PROTECTED_TREES,
                                     'protected_leg_sources': baseline['protected_leg_sources_sha256'],
                                     'preserved_80_reference_meshes': baseline['collection261_leg_mesh_sha256'],
                                     'limits': '80 original leg meshes accepted separately in job266; grouped tessellation is not byte-identity proof'})
        python = str(venv / 'bin/python')
        phase('extract', [python, '-I', '-B', str(ROOT / 'tools/gyropup_showcase.py'), '--only', 'model',
                          '--gyropup', str(product), '--toolkit', str(toolkit), '--output', str(OUT / 'model')], timeout=600)
        members = archive_model()  # Archive actual complete product before its acceptance assertions.
        phase('decode', [python, '-I', '-B', str(Path(__file__)), '--source', args.source,
                         '--contract-json', args.contract_json, '--decode-only'], timeout=120)
        assert members == inventory(OUT / 'model'), 'Candidate changed after sealing'
        passed = True
    except BaseException as exc:
        primary = exc
        results['original_error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if processes_quiescent:
            for role in ('producer', 'product', 'runtime', 'toolkit', 'hardware'):
                try:
                    assert role in captures and role in before, 'No initial identity; incomplete preparation'
                    after = captures[role](); save(role + '-after.json', after)
                    results['guards'][role] = after == before[role]
                    if role in ('producer', 'product'):
                        results['guards'][role] &= not after['status']
                except BaseException as exc:
                    results['guards'][role] = False
                    results['errors'].append(role + ': ' + str(exc))
            try:
                if not (OUT / 'model-produced.tgz').exists():
                    members = archive_model()  # Failed/partial native output is retained too.
            except BaseException as exc:
                results['errors'].append('Archive: ' + str(exc))
        else:
            results['errors'].append('Owned process groups not quiescent; no racing archive/source read')
        results['processes_quiescent'] = processes_quiescent
        results['model_members'] = sorted(members)
        ok = (passed and processes_quiescent and not results['errors']
              and len(results['guards']) == 5 and all(results['guards'].values())
              and sorted(members) == ['gyropup.bin', 'gyropup.json'])
        results['status'] = 'PASS_SCOPED_MODEL_CANDIDATE' if ok else 'FAILED_OR_INCOMPLETE'
        try:
            save('final-result.json', results); print(json.dumps(results), flush=True)
        except BaseException:
            if primary is None:
                raise
        if not ok and primary is None:
            raise SystemExit(1)


if __name__ == '__main__':
    main()

