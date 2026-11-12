#!/usr/bin/env python3
"""Controller-side analytical starter evals. No subject code is executed by graders."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'tests/fixtures/evaluation/jobs'
GRADERS = {'snapfit-v1', 'lid-v1', 'breakout-v1'}


def read_json(path):
    # Reject non-JSON floats and duplicate keys: do not accept ambiguous artifacts.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate key: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'non-finite JSON number: {value}')
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid)


def load_job(job_id):
    if job_id not in {p.name for p in CORPUS.iterdir() if p.is_dir()}:
        raise ValueError(f'unknown job: {job_id}')
    path = CORPUS / job_id
    job = read_json(path / 'job.json')
    required = {'schema_version','id','version','domain','area','grader','task','input_file','output_file','budget','limits'}
    if (not isinstance(job, dict) or set(job) != required
            or type(job['schema_version']) is not int or job['schema_version'] != 1
            or type(job['version']) is not int or job['version'] != 1 or job['id'] != job_id):
        raise ValueError('unsupported or malformed job manifest')
    if job['grader'] not in GRADERS or job['input_file'] != 'input.json' or job['output_file'] != 'solution.json':
        raise ValueError('unsupported grader or artifact paths')
    if not all(isinstance(job[k], str) and job[k] for k in ('task','domain','area','limits')):
        raise ValueError('job text fields must be nonempty strings')
    budget = job['budget']
    if set(budget) != {'wall_seconds','max_output_tokens'} or not all(type(v) is int and v > 0 for v in budget.values()):
        raise ValueError('invalid budget')
    return job, read_json(path / 'input.json')


def digest(job_id):
    h = hashlib.sha256()
    for name in ('job.json','input.json'):
        h.update(name.encode()); h.update((CORPUS / job_id / name).read_bytes())
    return h.hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def close(value, expected):
    return number(value) and math.isclose(value, expected, rel_tol=1e-6, abs_tol=1e-8)


def grade_solution(job, data, s):
    """Independent arithmetic/graph checks; never trust subject pass/fail assertions."""
    if not isinstance(s, dict):
        return {'object_schema': False}
    if job['grader'] == 'snapfit-v1':
        keys = {'length_mm','thickness_mm','width_mm','root_radius_mm','root_strain','allowable_strain','hook_force_n'}
        if set(s) != keys or not all(number(v) for v in s.values()):
            return {'numeric_schema': False}
        allowable = data['allowable_single'] * data['repeated_factor'] * data['process_factor']
        strain = lambda length: data['deflection_mm'] * data['thickness_mm'] / (data['deflection_factor'] * length ** 2)
        valid = [v for v in data['length_choices_mm'] if strain(v) <= allowable]
        length = s['length_mm']
        actual = strain(length) if length > 0 else math.inf
        force = data['width_mm'] * data['thickness_mm'] ** 2 / 6 * data['secant_mpa'] * actual / length if length > 0 else math.inf
        return dict(numeric_schema=True, shortest_valid_length=close(length,min(valid)),
                    fixed_section=close(s['thickness_mm'],data['thickness_mm']) and close(s['width_mm'],data['width_mm']),
                    allowable_includes_repeated_and_process=close(s['allowable_strain'],allowable),
                    root_strain_recomputed=close(s['root_strain'],actual), strain_within_limit=actual <= allowable,
                    root_radius=close(s['root_radius_mm'],max(data['radius_min_mm'], data['radius_ratio']*data['thickness_mm'])),
                    hook_force_recomputed=close(s['hook_force_n'],force))
    if job['grader'] == 'lid-v1':
        keys = {'rib_centers_y_mm','rib_width_mm','rib_height_mm','x_min_mm','x_max_mm'}
        centers = s.get('rib_centers_y_mm')
        if set(s) != keys or not isinstance(centers,list) or len(centers)!=2 or not all(number(v) for v in centers):
            return {'rib_schema':False}
        def valid(pair):
            half = data['rib_width_mm']/2
            return (all(v in data['center_grid_mm'] and data['y_min_mm'] <= v-half and v+half <= data['y_max_mm'] for v in pair)
                    and pair[1]-pair[0]-2*half >= data['rib_gap_mm']
                    and all(abs(v-c['y_mm'])-half >= c['radius_mm']+data['clearance_mm'] for v in pair for c in data['counterbores']))
        candidates = [p for p in itertools.combinations(data['center_grid_mm'],2) if valid(p)]
        best = min(candidates,key=lambda p:(sum(abs(a-b) for a,b in zip(p,data['original_centers_y_mm'])),p))
        return dict(rib_schema=True, dimensions_preserved=all(close(s[k],data[k]) for k in keys-{'rib_centers_y_mm'}),
                    envelope_clearance=valid(centers), minimum_movement_and_tie_break=tuple(centers)==best)
    nets = s.get('nets')
    if set(s) != {'nets'} or not isinstance(nets,list):
        return {'net_schema':False}
    expected = {}
    for pin in data['j1_mating_face_left_to_right']:
        expected.setdefault(pin['signal'],set()).add('J1.'+pin['pin'])
    for pin in data['j2_wire_side_left_to_right']:
        expected.setdefault(pin['signal'],set()).add('J2.'+pin['pin'])
    for signal,node in data['testpoints'].items():
        expected.setdefault(signal,set()).add(node)
    actual = {}; endpoints=[]
    for net in nets:
        if not isinstance(net,dict) or set(net)!={'name','nodes'} or not isinstance(net['name'],str) or not isinstance(net['nodes'],list) or not all(isinstance(n,str) for n in net['nodes']):
            return {'net_schema':False}
        if net['name'] in actual:
            return {'net_schema':True,'unique_net_names':False}
        actual[net['name']] = set(net['nodes']); endpoints += net['nodes']
    return dict(net_schema=True, unique_net_names=True, unique_endpoints=len(endpoints)==len(set(endpoints)),
                exact_pin_net_graph=actual==expected)


def grade(job_id, work):
    job, data = load_job(job_id)
    output = Path(work) / 'project' / job['output_file']
    error = None
    try:
        if output.parent.is_symlink() or output.is_symlink() or not output.is_file() or output.stat().st_size > 1_000_000:
            raise ValueError('output missing, symlinked, or exceeds 1 MB')
        checks = grade_solution(job,data,read_json(output))
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        checks = {'readable_valid_solution':False}; error = str(exc)
    return dict(job=job_id,job_version=job['version'],job_sha256=digest(job_id),
                grader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),checks=checks,
                passed=bool(checks) and all(checks.values()),error=error,limits=job['limits'])


def prepare(job_id, mode, work, kit=None, kit_revision=None):
    job, _ = load_job(job_id)
    work = Path(work).resolve()
    if mode not in ('bare','kit'):
        raise ValueError('mode must be bare or kit')
    if work.exists() and any(work.iterdir()):
        raise ValueError('work must be fresh and empty')
    if mode == 'kit':
        if not kit or not kit_revision:
            raise ValueError('kit requires an explicit checkout path and full pinned revision')
        kit = Path(kit).resolve()
        actual = subprocess.check_output(['git','-C',str(kit),'rev-parse','HEAD'],text=True).strip()
        if len(kit_revision)!=40 or actual != kit_revision:
            raise ValueError('kit checkout does not match full pinned revision')
        if subprocess.check_output(['git','-C',str(kit),'status','--porcelain'],text=True).strip():
            raise ValueError('kit checkout must be clean')
    project = work / 'project'; project.mkdir(parents=True)
    shutil.copyfile(CORPUS / job_id / 'input.json',project / 'input.json')
    prompt = job['task']+'\n'
    if mode == 'kit':
        prompt += f'\nThe cad-agent toolkit is available at {kit} pinned to {kit_revision}. Inspect its catalogue/docs or canonical .agents skills and use a relevant existing toolkit API or check when one applies. Import its Python package with PYTHONPATH={kit}/software when useful. If none applies, explain the tooling gap in toolkit-gap.md instead of invoking an unrelated command. No installation is needed.\n'
    (work / 'prompt.txt').write_text(prompt)
    preparation = dict(job=job_id,job_version=job['version'],job_sha256=digest(job_id),mode=mode,
                       kit_revision=kit_revision if mode=='kit' else None,kit_path=str(kit) if mode=='kit' else None,
                       budget=job['budget'],workspace_boundary='directory-only; same OS user; no security isolation')
    (work / 'preparation.json').write_text(json.dumps(preparation,indent=2)+'\n')
    return preparation


def ingest_run(job_id, work):
    """Combine collector metadata with checks; missing measurements stay null."""
    work = Path(work)
    preparation = read_json(work / 'preparation.json')
    if preparation['job'] != job_id or preparation['job_sha256'] != digest(job_id):
        raise ValueError('preparation job/revision mismatch')
    metadata = read_json(work / 'metadata.json')
    transcript = work / 'transcript.jsonl'
    result = grade(job_id,work)
    fields = ('harness','harness_version','model','seed','wall_seconds','exit_code','timed_out','tokens_in','tokens_out','peak_context','cost_usd','tool_calls','fresh_session','kit_use_observed','session_boundary')
    result.update({key:metadata.get(key) for key in fields})
    result.update(mode=preparation['mode'],kit_revision=preparation['kit_revision'],
                  transcript_sha256=hashlib.sha256(transcript.read_bytes()).hexdigest() if transcript.exists() else None,
                  workspace_boundary=preparation['workspace_boundary'])
    # Artifact correctness is distinct from a usable completed trial.
    result['trial_completed'] = metadata.get('exit_code') == 0 and metadata.get('timed_out') is False
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('list','validate','prepare','grade','ingest-run'))
    parser.add_argument('--job');parser.add_argument('--work',type=Path)
    parser.add_argument('--mode',choices=('bare','kit'),default='bare')
    parser.add_argument('--kit',type=Path);parser.add_argument('--kit-revision')
    args=parser.parse_args()
    if args.action in ('list','validate'):
        jobs=sorted(p.name for p in CORPUS.iterdir() if p.is_dir())
        for job in jobs:load_job(job)
        result=jobs
    else:
        if not args.job or not args.work:parser.error('--job and --work required')
        if args.action=='prepare':result=prepare(args.job,args.mode,args.work,args.kit,args.kit_revision)
        elif args.action=='grade':result=grade(args.job,args.work)
        else:result=ingest_run(args.job,args.work)
    print(json.dumps(result,sort_keys=True,allow_nan=False))

if __name__=='__main__':main()
