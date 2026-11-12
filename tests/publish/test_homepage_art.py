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
        assert 'Human-reviewed' in svg or 'HUMAN REVIEW' in svg
        assert 'not a hardware simulation or automatic model training' in svg
        assert 'MANUFACTURER GUIDE' in svg and 'source, edition, limits' in svg.lower()
