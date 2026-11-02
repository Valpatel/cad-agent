"""The hardware tables against the source they cite: the vendored bd_warehouse CSVs (ISO 4762 socket heads, ISO 7380-1
button heads), row by row, and the registry hook #283's clinch hardware plugs into."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cadagent.library import hardware

DATA = Path(__file__).resolve().parents[2] / 'vendor' / 'bd_warehouse' / 'src' / 'bd_warehouse' / 'data'


def rows(name, prefix):
    path = DATA / name
    if not path.exists():
        pytest.skip('the vendored bd_warehouse is not in this checkout (an sdist)')
    with path.open() as f:
        out = {}
        for r in csv.DictReader(f):
            out[r['Size'].split('-')[0]] = {k.split(':')[1].strip(): v for k, v in r.items()
                                            if k.startswith(prefix) and v}
        return out


@pytest.mark.parametrize('kind,csv_name,prefix', [('socket_head', 'socket_head_cap_parameters.csv', 'iso4762:'),
                                                  ('button_head', 'button_head_parameters.csv', 'iso7380_1:')])
def test_head_rows_match_bd_warehouse(kind, csv_name, prefix):
    src = rows(csv_name, prefix)
    for size, ours in hardware.table(kind)['rows'].items():
        for k, v in ours.items():
            assert float(src[size][k]) == pytest.approx(v), (kind, size, k)
    assert hardware.table(kind)['verified']


def test_unverified_tables_say_so():
    assert not hardware.table('nyloc_nut')['verified'] and 'unverified' in hardware.table('nyloc_nut')['source']
    assert not hardware.table('ring_lug')['verified']


def test_register_hook_adds_a_family_once():
    hardware.register('test_clinch_nut_xyz', {'M4': {'h': 1.0}}, source='a test')
    try:
        assert hardware.row('test_clinch_nut_xyz', 'M4') == {'h': 1.0}
        assert 'test_clinch_nut_xyz' in hardware.kinds()
        with pytest.raises(ValueError):
            hardware.register('test_clinch_nut_xyz', {'M4': {'h': 2.0}}, source='another')
    finally:
        hardware._TABLES.pop('test_clinch_nut_xyz', None)
    with pytest.raises(ValueError):
        hardware.register('x', {}, source='s')
    with pytest.raises(KeyError):
        hardware.row('socket_head', 'M99')
