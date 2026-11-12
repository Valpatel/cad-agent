"""Homepage claims remain anchored to existing recorded evidence, not decorative results."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]

def test_homepage_temperature_trace_quotes_actual_samples_and_units():
    record = json.loads((ROOT / 'docs/img/hero/learning-evidence.json').read_text())['figures']['thermal-history']
    source = ROOT / record['input']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256']
    rows = [line.split() for line in source.read_text().splitlines() if line and not line.startswith('#')]
    actual = float(rows[-1][-1]) - 273.15
    assert len(rows) == record['samples'] == 150
    assert abs(record['final_c'] - actual) < 1e-10
    svg = (ROOT / 'docs/img/hero/thermal-history.svg').read_text()
    assert f'{actual:.2f} °C' in svg
    assert 'iterations — not seconds' in svg
    assert 'not a measurement' in svg

def test_homepage_airflow_preserves_a_failed_solver_case():
    facts = json.loads((ROOT / 'docs/img/cfd/SOURCE.json').read_text())['facts']
    svg = (ROOT / 'docs/img/hero/airflow-balance.svg').read_text()
    assert facts['exhaust-ducted']['steady'] is False
    assert facts['exhaust-ducted']['energy_conserved'] is False
    assert '-10.9%' in svg and 'energy check fails' in svg
    for case in facts.values():
        assert f"{case['mass_flow_g_s']:.2f} g/s" in svg
        assert f"{case['heat_out_w']:.2f} W" in svg

def test_learning_hero_has_readable_still_and_no_integration_or_physics_claim():
    for name in ['learning-loop.svg', 'learning-loop-mobile.svg']:
        svg = (ROOT / 'docs/img/hero' / name).read_text()
        ET.fromstring(svg)
        assert 'prefers-reduced-motion:reduce' in svg
        assert 'Original 16-bit science-fiction adventure illustration' in svg
        assert 'not an engineering simulation or a claim of automatic model training' in svg
        assert 'People review and share the real project knowledge' in svg


def test_learning_hero_uses_the_existing_safe_vector_contract_and_explicit_finished_images():
    from cadagent.publish.anim import svg as contract
    for name in ['learning-loop', 'learning-loop-mobile']:
        animated = (ROOT / 'docs/img/hero' / (name+'.svg')).read_text()
        assert contract.problems(animated) == []
        still = (ROOT / 'docs/img/hero' / (name+'-still.svg')).read_text()
        ET.fromstring(still)
        assert '*{animation:none!important}' in still
        assert '<animate' not in still and '@keyframes' not in still
        # The preference-only still retains the next build and the newly joined crew member.
        assert '.new-builder{transform:translate(110px,25px)}' in still
        assert '.next-chassis{transform:none}' in still

    # Exported artwork must come from its committed producer, including the authored final pose.
    import importlib.util
    import sys
    figures = ROOT / 'tools/site/figures'
    sys.path.insert(0, str(figures))
    try:
        spec = importlib.util.spec_from_file_location('learning_home_art_test', figures / 'learning-home.py')
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        for mobile, name in [(False, 'learning-loop'), (True, 'learning-loop-mobile')]:
            generated = producer.cinematic_hero(mobile)
            assert (ROOT / 'docs/img/hero' / (name+'.svg')).read_text() == generated
            assert (ROOT / 'docs/img/hero' / (name+'-still.svg')).read_text() == producer.finished_still(generated)
    finally:
        sys.path.remove(str(figures))


def test_computation_stills_preserve_the_recorded_sources_and_finished_pose():
    """Explicit stills keep the original authors' final states and numerical evidence."""
    from cadagent.publish.anim import svg as contract
    figures = json.loads((ROOT / 'docs/img/hero/learning-evidence.json').read_text())['figures']
    stills = figures['result_stills']
    assert len(stills) == 8
    for record in stills.values():
        original = ROOT / record['input']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == record['sha256']
        still = (ROOT / record['output']).read_text()
        assert '<animate' not in still and '@keyframes' not in still
        ET.fromstring(still)
    thermal = (ROOT / 'docs/img/hero/result-stills/thermal-history-still.svg').read_text()
    assert f"{figures['thermal-history']['final_c']:.2f} °C" in thermal
    assert 'solver iterations — not seconds' in thermal
    assert 'stroke-dashoffset:0' in thermal  # Complete recorded trace, not its hidden first frame.
    flow = (ROOT / 'docs/img/hero/result-stills/airflow-balance-still.svg').read_text()
    assert '-10.9%' in flow and 'energy check fails' in flow
