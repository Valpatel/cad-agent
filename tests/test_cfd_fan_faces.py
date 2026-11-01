"""A fan's inlet and outlet temperatures are mass-flow-weighted on the faces at each end of its zone (#47), and a result
that does not conserve energy is flagged. Read from recorded-format runs (tests/fixtures/cfd_runs); no solver runs."""

from __future__ import annotations

import json
import math
import re

import numpy as np
import pytest

from cadagent.simulation import cfd
from cadagent.simulation.cfd import Fan

from .cfd_fixtures import recorded


def test_mass_flow_weighting_and_the_volume_average_differ_by_the_hand_computed_amount(tmp_path):
    # the fan's annulus in two halves of equal area, the same at both ends of its zone: 1 g/s of air at 30 °C through
    # the inner half and 3 g/s at 40 °C through the outer. By volume the zone averages (30 + 40) / 2 = 35.0 °C; by
    # mass flow (1 x 30 + 3 x 40) / 4 = 37.5 °C, 2.5 K warmer
    r = cfd.read_results(recorded('fan-faces-known-profile', tmp_path))
    f = r['fans']['fan']
    assert f['air_through_fan_c'] == 35.0
    assert f['inlet_c'] == 37.5 and f['outlet_c'] == 37.5
    assert f['inlet_kg_s'] == pytest.approx(0.004, rel=1e-9) and f['outlet_kg_s'] == pytest.approx(0.004, rel=1e-9)
    # Q = m_dot c_p (T - T_room): 0.004 kg/s x 1005 J/(kg K) x 12.5 K = 50.25 W, the 50 W put in, as the box has no
    # other way out. The volume average would give 0.004 x 1005 x 10 = 40.2 W and lose a fifth of the heat
    assert f['heat_carried_w'] == 50.25
    assert cfd.stream_heat_w(f['outlet_kg_s'], f['air_through_fan_c'], r['ambient_c']) == pytest.approx(40.2)
    assert r['heat_out_w'] == pytest.approx(50.25, abs=0.01) and r['energy_balance_pct'] == 0.5
    assert r['energy_conserved'] is True and r['warnings'] == []
    assert r['zone_faces'] == {'fanInlet': 24, 'fanOutlet': 24} and 'error' not in r
    assert r['steady'] is True and r['converged'] is True


def test_both_temperatures_are_monitored_and_held_to_1_c_like_every_other(tmp_path):
    r = cfd.read_results(recorded('fan-faces-known-profile', tmp_path))
    mon = r['monitors']
    assert mon['fan_inlet_c']['label'] == 'fan: air entering (mass-flow-weighted)'
    assert mon['fan_outlet_c']['label'] == 'fan: air leaving (mass-flow-weighted)'
    assert mon['fan_intake_c']['label'] == 'fan: mean over the fan zone (by volume)'
    assert {mon[k]['quantity'] for k in ('fan_inlet_c', 'fan_outlet_c', 'fan_intake_c')} == {'Air temperature'}
    assert mon['fan_inlet_c']['points'][-1] == [100, 37.5] and mon['fan_intake_c']['points'][-1] == [100, 35.0]
    assert r['convergence']['fan_inlet_c_change'] == 0.0 and r['convergence']['fan_outlet_c_change'] == 0.0
    assert r['convergence_limits']['fan_inlet_c_change'] == 1.0 and r['convergence_limits']['fan_outlet_c_change'] == 1.0


def _edit(path, fn):
    path.write_text(fn(path.read_text()))


def test_an_outlet_whose_temperature_still_drifts_by_1_5_c_is_not_steady(tmp_path):
    d = recorded('fan-faces-known-profile', tmp_path)
    f = d / 'postProcessing/domain0/T_outlet_fan/0/surfaceFieldValue.dat'
    _edit(f, lambda s: re.sub(r'^(\d+)(\s+)3\.10650000e\+02$',
                              lambda m: f'{m.group(1)}{m.group(2)}{cfd.T0 + 37.5 + 0.075 * (int(m.group(1)) - 100):.8e}', s, flags=re.M))
    r = cfd.read_results(d)
    assert r['convergence']['fan_outlet_c_change'] == 1.5 and r['fans']['fan']['outlet_c'] == 37.5
    assert r['steady'] is False and r['converged'] is False


def test_a_result_that_does_not_conserve_energy_is_flagged(tmp_path):
    # the same run said to have had 60 W put in: 50.25 W leave, -16.2 %, outside the 5 %
    d = recorded('fan-faces-known-profile', tmp_path)
    meta = json.loads((d / 'cadagent-case.json').read_text())
    meta['heat_input_w'] = 60.0
    (d / 'cadagent-case.json').write_text(json.dumps(meta))
    r = cfd.read_results(d)
    assert r['energy_balance_pct'] == -16.2 and r['energy_conserved'] is False
    assert r['steady'] is True and r['converged'] is False
    assert len(r['warnings']) == 1 and r['warnings'][0].startswith('energy not conserved: 50.25 W leave with the air for 60 W')
    assert '-16.2 %; tolerance ±5 %' in r['warnings'][0]


def test_energy_check_golden_vectors():
    # within 5 % of the heat put in, as reported (rounded to 0.1 %), both ends included
    assert cfd.energy_check(40.0, 39.6) == {'heat_input_w': 40.0, 'heat_out_w': 39.6, 'conserved': True,
                                            'difference_w': -0.4, 'difference_pct': -1.0, 'tolerance': '±5 %'}
    assert cfd.energy_check(40.0, 42.0)['conserved'] is True                  # +5.0 %
    assert cfd.energy_check(40.0, 37.985)['conserved'] is True                # -5.04 % reads -5.0 % (reported to 0.1 %)
    assert cfd.energy_check(40.0, 37.9)['difference_pct'] == -5.3 and cfd.energy_check(40.0, 37.9)['conserved'] is False
    # nothing put in (airflow only): within 0.5 W of nothing
    assert cfd.energy_check(0.0, 0.4) == {'heat_input_w': 0.0, 'heat_out_w': 0.4, 'conserved': True, 'difference_w': 0.4,
                                          'tolerance': '±0.5 W'}
    assert cfd.energy_check(0.0, -0.6)['conserved'] is False
    # unknown either side: not judged, and said why
    assert cfd.energy_check(None, 12.0)['conserved'] is None and 'exchanger' in cfd.energy_check(None, 12.0)['why']
    assert cfd.energy_check(12.0, None)['conserved'] is None and 'flux_T' in cfd.energy_check(12.0, None)['why']
    # a looser tolerance is the caller's to set
    assert cfd.energy_check(40.0, 37.0, tolerance_pct=10)['conserved'] is True


def test_stream_heat_golden_vectors():
    assert cfd.stream_heat_w(0.004, 37.5, 25.0) == pytest.approx(50.25)
    assert cfd.stream_heat_w(0.01, 25.0, 25.0) == 0.0
    assert cfd.stream_heat_w(0.002, 20.0, 25.0) == pytest.approx(-10.05)              # cooler than the room
    assert cfd.stream_heat_w(0.004, 37.5, 25.0, cp=1000.0) == pytest.approx(50.0)


def test_a_face_that_caught_nothing_is_an_error_not_a_temperature(tmp_path):
    # surfaceFieldValue with empty-surface warn writes NaN rows for a faceZone with no faces; topoSet says size 0
    d = recorded('fan-faces-known-profile', tmp_path)
    for kind in ('T', 'mass'):
        _edit(d / f'postProcessing/domain0/{kind}_inlet_fan/0/surfaceFieldValue.dat',
              lambda s: re.sub(r'^(\d+\s+)\S+$', r'\1NaN', s, flags=re.M))
    _edit(d / 'log.topoSet', lambda s: s.replace('fanInlet now size 24', 'fanInlet now size 0'))
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert 'inlet_c' not in f and 'inlet_kg_s' not in f and f['outlet_c'] == 37.5
    assert 'fan_inlet_c' not in r['monitors'] and 'fan_inlet_c_change' not in r['convergence']
    assert r['error'] == "empty zone(s): ['fanInlet']; refine the mesh around them" and r['converged'] is False


def test_too_little_net_flow_to_weight_by_gives_no_temperature(tmp_path):
    # 1 mg/s through the inlet, under 1 % of the fan's free-air flow (30 m3/h x 1.17 kg/m3 = 9.7 g/s): OpenFOAM's
    # weighted average divides by it, so the temperature means nothing
    d = recorded('fan-faces-known-profile', tmp_path)
    _edit(d / 'postProcessing/domain0/mass_inlet_fan/0/surfaceFieldValue.dat',
          lambda s: s.replace('4.00000000e-03', '1.00000000e-06'))
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert f['inlet_c'] is None and f['inlet_kg_s'] == pytest.approx(1e-6) and f['outlet_c'] == 37.5
    assert 'fan_inlet_c' not in r['monitors'] and 'fan_inlet_c_change' not in r['convergence']
    assert r['warnings'] == ["fan inlet: the net flow through it, 1e-06 kg/s, is under 1% of the fan's free-air flow, "
                             'too little to weight a temperature by']


def test_runs_recorded_before_the_faces_keep_only_the_volume_average(tmp_path):
    r = cfd.read_results(recorded('fins-block-drifting', tmp_path))
    assert set(r['fans']['fan']) == {'flow_m3h', 'flow_cfm', 'pressure_rise_pa', 'fraction_of_free_air', 'air_through_fan_c'}
    assert 'zone_faces' not in r and r['energy_conserved'] is True and r['warnings'] == []
    assert not any('inlet' in k or 'outlet' in k for k in list(r['monitors']) + list(r['convergence']))


def test_the_recorded_runs_that_were_not_converged_now_say_so(tmp_path):
    # the same verdicts as before (converged is False on each), now with the reason in words
    for name, pct in (('fins-no-solids', -7.8), ('solids-ended-early', -19.2), ('solids-continued-again', -10.8)):
        r = cfd.read_results(recorded(name, tmp_path / name))
        assert r['energy_balance_pct'] == pct and r['energy_conserved'] is False and r['converged'] is False
        assert [w.split(' (')[0] for w in r['warnings']] == [
            f'energy not conserved: {r["heat_out_w"]:g} W leave with the air for {r["heat_input_w"]:g} W put in']


def test_the_faces_sit_just_inside_the_zone_whatever_the_axis():
    f = Fan('f', centre=(10, -20, 30), axis=(1, 2, -2), d_outer=60, d_hub=20, thickness=9, dp0_pa=20, q_free_m3h=30)
    up, down, a = f.ends()
    assert np.allclose(a, np.array([1, 2, -2]) / 3)
    assert np.allclose(up, np.round((np.array([10, -20, 30]) - a * 4.5) / 1000, 6), atol=0)
    assert np.allclose(down, np.round((np.array([10, -20, 30]) + a * 4.5) / 1000, 6), atol=0)
    faces = f.faces()
    assert np.allclose(faces['inlet'] - up, a * cfd.FACE_INSET_M, rtol=0, atol=1e-15)
    assert np.allclose(faces['outlet'] - down, -a * cfd.FACE_INSET_M, rtol=0, atol=1e-15)
    # inside the zone, and far closer to its plane than any cell is thin
    assert 0 < float((faces['inlet'] - up) @ a) < 1e-6 and 0 < float((down - faces['outlet']) @ a) < 1e-6


def test_the_case_builds_and_logs_both_faces_of_every_fan(tmp_path):
    from .test_cfd import small_case                       # needs trimesh, as that module does
    c = small_case()
    d = c.write(tmp_path / 'case', np_procs=2)
    ts = (d / 'system/domain0/topoSetDict').read_text()
    f = c.fans[0]
    for side in ('inlet', 'outlet'):
        o = f.faces()[side]
        name = f'fan{side.capitalize()}'
        block = re.search(rf'\{{ name {name}; type faceZoneSet; action new; source searchableSurfaceToFaceZone;(.*?)\}}', ts, re.S)
        assert block, name
        body = block.group(1)
        assert 'surfaceType disk;' in body and 'normal (0.000000000 0.000000000 -1.000000000);' in body
        assert f'origin ({o[0]:.9f} {o[1]:.9f} {o[2]:.9f});' in body
        assert 'radius 0.015000;' in body and 'innerRadius 0.005000;' in body
    # the zone is z from 38 to 42 mm, pushed down (-z): the inlet just under its top, the outlet just over its bottom
    assert f.faces()['inlet'][2] == pytest.approx(0.042 - 1e-7, abs=1e-12)
    assert f.faces()['outlet'][2] == pytest.approx(0.038 + 1e-7, abs=1e-12)
    cd = (d / 'system/controlDict').read_text()
    for side, zone in (('inlet', 'fanInlet'), ('outlet', 'fanOutlet')):
        t = re.search(rf'T_{side}_fan\s*\{{(.*?)\}}', cd, re.S).group(1)
        assert f'regionType faceZone; name {zone};' in t and 'fields (T); operation weightedAverage; weightField phi;' in t
        assert 'empty-surface warn;' in t and 'writeInterval 10;' in t
        m = re.search(rf'mass_{side}_fan\s*\{{(.*?)\}}', cd, re.S).group(1)
        assert f'name {zone};' in m and 'fields (phi); operation sum;' in m and 'empty-surface warn;' in m
    assert any('mass-flow-weighted' in s for s in json.loads((d / 'cadagent-case.json').read_text())['limits'])


def test_the_weighting_is_the_bulk_temperature_that_carries_the_heat():
    # the identity read_results relies on: with T_bulk = sum(phi T) / sum(phi), m_dot c_p (T_bulk - T_room) is the
    # enthalpy the faces carry above the room, sum(phi c_p (T - T_room)), whatever the profile, backflow included
    rng = np.random.default_rng(47)
    phi = rng.uniform(-0.2e-3, 1e-3, 40)                    # some faces carry air backwards (tip recirculation)
    t = 25 + rng.uniform(0, 20, 40)
    bulk = float((phi * t).sum() / phi.sum())
    assert cfd.stream_heat_w(phi.sum(), bulk, 25.0) == pytest.approx(float((phi * cfd.AIR_CP * (t - 25)).sum()), rel=1e-12)
    assert not math.isclose(bulk, float(t.mean()), abs_tol=0.1)          # and it is not the plain average


# Two real runs (OpenFOAM v2512 in its official image, 1500 iterations), recorded by tools/cfd_fan_figure.py: a vented
# 20 W box with an exhaust fan, once just under its opening and once in a duct with its hub plugged.

def test_a_recorded_ducted_fan_carries_the_heat_put_in(tmp_path):
    # the duct is the box's only way out and the plug shuts the hub, so all the air the fan moves was heated once and
    # leaves: it carries the 20 W put in. Nothing crosses the zone's sides, so the two faces see the same mass flow, and
    # the fan adds no heat, so the same temperature
    r = cfd.read_results(recorded('exhaust-ducted', tmp_path))
    f = r['fans']['fan']
    assert r['zone_faces'] == {'fanInlet': 392, 'fanOutlet': 392} and 'error' not in r
    assert f['inlet_kg_s'] == pytest.approx(f['outlet_kg_s'], rel=1e-4)
    assert abs(f['inlet_c'] - f['outlet_c']) <= 0.05
    assert f['heat_carried_w'] == pytest.approx(r['heat_input_w'], rel=0.02)
    assert r['energy_conserved'] is True and r['warnings'] == []
    # as recorded: 2.81 g/s at 32.06 °C, 19.94 W; the zone's volume average 32.13 °C
    assert (f['inlet_c'], f['outlet_c'], f['air_through_fan_c'], f['heat_carried_w']) == (32.06, 32.06, 32.13, 19.94)
    assert f['outlet_kg_s'] == pytest.approx(0.00280931034, rel=1e-9)
    assert cfd.stream_heat_w(f['outlet_kg_s'], f['outlet_c'], r['ambient_c']) == pytest.approx(f['heat_carried_w'], abs=0.02)


def test_a_recorded_fan_under_its_opening_carries_more_heat_than_is_put_in(tmp_path):
    # 3 mm under its opening, the fan takes back air it has pushed out, down through its dead hub and round its rim: that
    # air is counted each time it passes, so the fan's stream carries 32.65 W above the room for 20 W put in. Its ṁ is
    # not the flow through the box, and T_fan - Q / (ṁ c_p) would not give the air upstream
    r = cfd.read_results(recorded('exhaust-under-opening', tmp_path))
    f = r['fans']['fan']
    assert f['heat_carried_w'] == 32.65 and f['heat_carried_w'] > 1.5 * r['heat_input_w']
    assert (f['inlet_c'], f['outlet_c'], f['air_through_fan_c']) == (33.03, 33.0, 33.02)
    # air also crosses the zone's open rim and hub, so the two faces' mass flows differ (by 1.3 % here)
    assert f['inlet_kg_s'] / f['outlet_kg_s'] == pytest.approx(1.0136, abs=1e-4)
    # its last iterate sits on a swing of the plume: 21.15 W leave, +5.7 %, and the check says so
    assert r['energy_balance_pct'] == 5.7 and r['energy_conserved'] is False and r['converged'] is False
    assert r['warnings'][0].startswith('energy not conserved: 21.15 W leave with the air for 20 W put in (+5.7 %')


def test_the_docs_figure_states_what_the_recorded_runs_say(tmp_path):
    # docs/img/cfd/fan-faces.webp is drawn from these runs; its SOURCE.json records the numbers it shows
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('cfd_fan_figure', root / 'tools' / 'cfd_fan_figure.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    source = json.loads((root / 'docs' / 'img' / 'cfd' / 'SOURCE.json').read_text())
    assert source['recorded_runs'] == [f'tests/fixtures/cfd_runs/{n}' for n in tool.CASES]
    for name in tool.CASES:
        assert tool.facts(recorded(name, tmp_path / name)) == source['facts'][name], name
