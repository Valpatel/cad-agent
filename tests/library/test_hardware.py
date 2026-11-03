"""The hardware tables against the source they cite: the vendored bd_warehouse CSVs (ISO 4762 socket heads, ISO 7380-1
button heads, ISO 7089, ISO 7090 and ISO 7093-1 washers), row by row; the heads' bearing faces and the washers'
tolerance limits against the standards' table rows (#292); and the registry hook #283's clinch hardware plugs into."""
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


@pytest.mark.parametrize('kind,csv_name,prefix', [('plain_washer', 'plain_washer_parameters.csv', 'iso7089:'),
                                                  ('chamfered_washer', 'chamfered_washer_parameters.csv', 'iso7090:'),
                                                  ('large_washer', 'plain_washer_parameters.csv', 'iso7093:')])
def test_washer_rows_match_bd_warehouse(kind, csv_name, prefix):
    src = rows(csv_name, prefix)
    for size, ours in hardware.table(kind)['rows'].items():
        for k in ('d1', 'd2', 'h'):
            assert float(src[size][k]) == pytest.approx(ours[k]), (kind, size, k)
    assert hardware.table(kind)['verified'] and hardware.table(kind)['hardness_hv'] == 200
    # every size from M2 (M3 for the large series, M5 for the chamfered one) to M6
    assert set(hardware.table(kind)['rows']) == {'plain_washer': {'M2', 'M2.5', 'M3', 'M4', 'M5', 'M6'},
                                                 'chamfered_washer': {'M5', 'M6'},
                                                 'large_washer': {'M3', 'M4', 'M5', 'M6'}}[kind]


def test_iso7093_m25_is_left_out_though_bd_warehouse_lists_it():
    assert 'M2.5' in rows('plain_washer_parameters.csv', 'iso7093:')
    assert 'M2.5' not in hardware.table('large_washer')['rows'] and 'starts at M3' in hardware.table('large_washer')['source']


# the standards' rows: (d2 min, h min) by thread. d2 is to h14 (ISO 286-1: 0.30 mm over 3-6 mm, 0.36 over 6-10, 0.43
# over 10-18); h to the standard's own band round its nominal (ISO 7089: 0.3 +/- 0.05, 0.5 +/- 0.05, 0.8 +/- 0.1,
# 1 +/- 0.1, 1.6 +/- 0.2; ISO 7093-1: 0.8 +/- 0.1, 1 +/- 0.1, 1.2 +/- 0.2, 1.6 +/- 0.2)
LEAST = {'plain_washer': {'M2': (4.7, 0.25), 'M2.5': (5.7, 0.45), 'M3': (6.64, 0.45), 'M4': (8.64, 0.7),
                          'M5': (9.64, 0.9), 'M6': (11.57, 1.4)},
         'chamfered_washer': {'M5': (9.64, 0.9), 'M6': (11.57, 1.4)},
         'large_washer': {'M3': (8.64, 0.7), 'M4': (11.57, 0.9), 'M5': (14.57, 1.0), 'M6': (17.57, 1.4)}}
H14_MM = ((3.0, 6.0, 0.30), (6.0, 10.0, 0.36), (10.0, 18.0, 0.43))


@pytest.mark.parametrize('kind', sorted(LEAST))
def test_washer_least_sizes_are_the_standards_tolerances(kind):
    for size, (d2_min, h_min) in LEAST[kind].items():
        r = hardware.row(kind, size)
        assert (r['d2_min'], r['h_min']) == (d2_min, h_min), (kind, size)
        tol = next(t for lo, hi, t in H14_MM if lo < r['d2'] <= hi)
        assert r['d2'] - r['d2_min'] == pytest.approx(tol), (kind, size)
        assert 0 < r['h_min'] < r['h']


# the heads' bearing faces, as the standards' Table 1 rows give them: dw min (or dk min where the standard has no
# dw) and da max
FACES = {'socket_head_bearing': {'M2': (3.48, 2.6), 'M2.5': (4.18, 3.1), 'M3': (5.07, 3.6), 'M4': (6.53, 4.7),
                                 'M5': (8.03, 5.7), 'M6': (9.38, 6.8), 'M8': (12.33, 9.2)},
         'button_head_bearing': {'M3': (5.0, 3.6), 'M4': (6.84, 4.7), 'M5': (8.74, 5.7), 'M6': (9.57, 6.8)},
         'cheese_head_bearing': {'M2': (3.62, 2.6), 'M2.5': (4.32, 3.1), 'M3': (5.32, 3.6), 'M4': (6.78, 4.7),
                                 'M5': (8.28, 5.7), 'M6': (9.78, 6.8)}}


@pytest.mark.parametrize('kind', sorted(FACES))
def test_head_bearing_faces_are_the_standards_rows(kind):
    assert {s: (r['dw'], r['da']) for s, r in hardware.table(kind)['rows'].items()} == FACES[kind]
    assert hardware.table(kind)['stands_in'] == (kind == 'cheese_head_bearing')
    for size, r in hardware.table(kind)['rows'].items():
        assert float(size[1:]) < r['da'] < r['dw'], (kind, size)        # the fillet inside the face, round the shank
    # the bearing face lies inside the head's outside, where the head's own table has the size
    head = {'socket_head_bearing': 'socket_head', 'button_head_bearing': 'button_head'}.get(kind)
    for size, r in hardware.table(kind)['rows'].items():
        if head and size in hardware.table(head)['rows']:
            assert r['dw'] < hardware.row(head, size)['dk'], (kind, size)


def test_socket_faces_agree_with_bossards_copy():
    from cadagent.mechanical.inserts import SRC
    for size, dw in (('M4', 6.53), ('M5', 8.03), ('M6', 9.38), ('M8', 12.33)):
        assert f"{size} {dw:g}/" in SRC['bossard-head'] and hardware.row('socket_head_bearing', size)['dw'] == dw


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
