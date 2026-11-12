"""Positive references, defect controls, schema failures and controller boundary checks."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('standard_eval',ROOT/'tools/evaluation/standard_eval.py')
eval=importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval)
JOBS=['connector-breakout','lid-rib-clearance','snapfit-sizing']


def reference(job_id):
    return eval.read_json(eval.CORPUS/job_id/'reference.json')


@pytest.mark.parametrize('job_id',JOBS)
def test_every_manifest_and_reference_passes(job_id):
    job,data=eval.load_job(job_id)
    checks=eval.grade_solution(job,data,reference(job_id))
    assert checks and all(checks.values()),checks


@pytest.mark.parametrize('job_id',JOBS)
def test_preparation_exposes_only_task_and_input(tmp_path,job_id):
    work=tmp_path/'run'
    preparation=eval.prepare(job_id,'bare',work)
    assert sorted(p.name for p in (work/'project').iterdir())==['input.json']
    assert preparation['kit_revision'] is None
    assert not any(word in (work/'prompt.txt').read_text() for word in ('reference.json','grade_solution','tests/fixtures'))
    with pytest.raises(ValueError,match='fresh'):
        eval.prepare(job_id,'bare',work)
    assert not eval.grade(job_id,work)['passed']
    (work/'project/solution.json').write_text(json.dumps(reference(job_id)))
    assert eval.grade(job_id,work)['passed']


def test_snap_defects_are_recomputed_instead_of_trusting_subject():
    job,data=eval.load_job('snapfit-sizing')
    for key,value in [('length_mm',14),('length_mm',18),('allowable_strain',.024),('root_strain',.001),('hook_force_n',0),('root_radius_mm',.381),('thickness_mm',1)]:
        solution=reference(job['id']);solution[key]=value
        assert not all(eval.grade_solution(job,data,solution).values()),(key,value)
    # Mutating the answer and its reported strain/force consistently still fails the chosen length.
    solution=reference(job['id']);solution.update(length_mm=14,root_strain=1.6/(.67*196),hook_force_n=4*1800*(1.6/(.67*196))/14)
    assert not eval.grade_solution(job,data,solution)['strain_within_limit']


def test_rib_defects_cover_collision_gaps_grid_and_optimization():
    job,data=eval.load_job('lid-rib-clearance')
    for centers in ([8,32],[3,3],[3,37],[3,26],[2,27],[3.1,27],[27,3]):
        solution=reference(job['id']);solution['rib_centers_y_mm']=centers
        assert not all(eval.grade_solution(job,data,solution).values()),centers
    solution=reference(job['id']);solution['rib_width_mm']=.1
    assert not eval.grade_solution(job,data,solution)['dimensions_preserved']


def test_net_defects_cover_mirror_swaps_shorts_missing_and_duplicate_nodes():
    job,data=eval.load_job('connector-breakout')
    good=reference(job['id'])
    bad=[]
    swapped=copy.deepcopy(good)
    swapped['nets'][0]['nodes'][1],swapped['nets'][3]['nodes'][1]=swapped['nets'][3]['nodes'][1],swapped['nets'][0]['nodes'][1]
    bad.append(swapped)
    missing=copy.deepcopy(good);missing['nets'][0]['nodes'].pop();bad.append(missing)
    short=copy.deepcopy(good);short['nets'][0]['nodes'].append('J1.2');bad.append(short)
    duplicate=copy.deepcopy(good);duplicate['nets'][0]['nodes'].append('J1.1');bad.append(duplicate)
    duplicate_net=copy.deepcopy(good);duplicate_net['nets'].append(duplicate_net['nets'][0]);bad.append(duplicate_net)
    for solution in bad:
        assert not all(eval.grade_solution(job,data,solution).values())
    reordered={'nets':[{**n,'nodes':n['nodes'][::-1]} for n in good['nets'][::-1]]}
    assert all(eval.grade_solution(job,data,reordered).values())


@pytest.mark.parametrize('payload',['null','[]','{"length_mm":NaN}','{"nets":[],"nets":[]}','{broken','{"rib_centers_y_mm":[true,2]}'])
def test_malformed_outputs_fail_closed(tmp_path,payload):
    work=tmp_path/'run';eval.prepare('snapfit-sizing','bare',work)
    (work/'project/solution.json').write_text(payload)
    assert not eval.grade('snapfit-sizing',work)['passed']


def test_symlink_and_large_output_fail(tmp_path):
    work=tmp_path/'run';eval.prepare('snapfit-sizing','bare',work)
    solution=work/'project/solution.json'
    solution.symlink_to(eval.CORPUS/'snapfit-sizing/reference.json')
    assert not eval.grade('snapfit-sizing',work)['passed']
    solution.unlink();solution.write_text(' '*1_000_001)
    assert not eval.grade('snapfit-sizing',work)['passed']


def test_ingest_preserves_unknown_metrics_and_trial_failure(tmp_path):
    work=tmp_path/'run';eval.prepare('connector-breakout','bare',work)
    (work/'project/solution.json').write_text(json.dumps(reference('connector-breakout')))
    (work/'metadata.json').write_text(json.dumps({'harness':'fixture','exit_code':124,'timed_out':True}))
    (work/'transcript.jsonl').write_text('{"fixture":true}\n')
    result=eval.ingest_run('connector-breakout',work)
    assert result['passed'] and not result['trial_completed']
    assert result['tokens_in'] is None and result['cost_usd'] is None and result['kit_use_observed'] is None
    assert len(result['transcript_sha256'])==64
    prep=eval.read_json(work/'preparation.json');prep['job_sha256']='changed'
    (work/'preparation.json').write_text(json.dumps(prep))
    with pytest.raises(ValueError,match='mismatch'):eval.ingest_run('connector-breakout',work)


def test_kit_must_be_explicit_clean_and_pinned(tmp_path):
    with pytest.raises(ValueError,match='explicit'):eval.prepare('snapfit-sizing','kit',tmp_path/'run')
    with pytest.raises(ValueError,match='pinned'):eval.prepare('snapfit-sizing','kit',tmp_path/'run',ROOT,'wrong')
