"""The planning catalog stays distinct from executable v1 manifests and controller answers."""
import json
from pathlib import Path
import re

import yaml

from tests.repo.test_areas import load_areas

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'tests/fixtures/evaluation'
FIELDS = {'id', 'version', 'status', 'domain', 'area', 'difficulty', 'job_manifest', 'prompt',
          'required_inputs', 'success_criteria', 'artifacts', 'limits', 'sources'}
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def catalog():
    return load_areas((FIXTURES / 'candidates.yaml').read_text())


def test_catalog_fields_sources_and_domain_vocabulary():
    data = catalog()
    assert set(data) == {'schema', 'purpose', 'sources', 'tasks'}
    assert data['schema'] == 'cad-agent-candidate-catalog/1'
    assert data['purpose'] and data['tasks'] and data['sources']
    for key, source in data['sources'].items():
        assert SLUG.fullmatch(key)
        assert set(source) == {'url', 'reuse', 'license_note'}
        assert source['url'].startswith('https://')
        assert all(isinstance(value, str) and value.strip() for value in source.values())
    tree = yaml.safe_load((ROOT / 'docs/areas.yaml').read_text())
    areas = {(domain['slug'], area['slug']) for domain in tree['domains'] for area in domain['areas']}
    ids = [task['id'] for task in data['tasks']]
    assert len(ids) == len(set(ids))
    for task in data['tasks']:
        assert set(task) == FIELDS, task['id']
        assert SLUG.fullmatch(task['id'])
        assert type(task['version']) is int and task['version'] > 0
        assert (task['domain'], task['area']) in areas, task['id']
        assert task['difficulty'] in {'starter', 'intermediate', 'advanced', 'expert'}
        assert task['status'] in {'candidate', 'existing-v1'}
        assert isinstance(task['limits'], str) and task['limits'].strip()
        assert task['sources'] and len(task['sources']) == len(set(task['sources']))
        assert set(task['sources']) <= set(data['sources'])
        for field in ('required_inputs', 'success_criteria', 'artifacts'):
            assert isinstance(task[field], list)
            assert all(isinstance(value, str) and value.strip() for value in task[field])


def test_candidates_cannot_masquerade_as_runnable_jobs():
    for task in catalog()['tasks']:
        if task['status'] == 'candidate':
            assert task['job_manifest'] is None
            assert isinstance(task['prompt'], str) and task['prompt'].strip()
            assert all(task[field] for field in ('required_inputs', 'success_criteria', 'artifacts'))
            assert not (FIXTURES / 'jobs' / task['id']).exists(), 'promote explicitly, not by shadowing a job'
        else:
            assert task['prompt'] is None, 'existing job prompt must not acquire a second authority'
            assert all(task[field] == [] for field in ('required_inputs', 'success_criteria', 'artifacts'))
            assert task['job_manifest'] == f"jobs/{task['id']}/job.json"
            manifest = json.loads((FIXTURES / task['job_manifest']).read_text())
            assert manifest['schema_version'] == 1
            for field in ('id', 'version', 'domain'):
                assert task[field] == manifest[field]
            # Preserve historical manifest hashes; the planning index uses today's topic vocabulary.
            assert task['area'] == {'housings': 'housings-and-enclosures', 'pcb': 'circuit-boards'}.get(
                manifest['area'], manifest['area'])


def test_catalog_links_all_existing_jobs_without_claiming_all_candidates_are_qualified():
    tasks = catalog()['tasks']
    assert {t['id'] for t in tasks if t['status'] == 'existing-v1'} == {
        path.parent.name for path in (FIXTURES / 'jobs').glob('*/job.json')}
    assert {t['difficulty'] for t in tasks} == {'starter', 'intermediate', 'advanced', 'expert'}
    assert {t['domain'] for t in tasks} == {'practice', 'mechanical', 'manufacturing', 'electrical', 'thermal', 'simulation'}
