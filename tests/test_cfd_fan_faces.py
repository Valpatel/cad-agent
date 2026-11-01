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
    # every face carries air forward, so nothing flows back; both ends are the 1.65e-3 m² annulus
    assert f['inlet_backflow_kg_s'] == 0 and f['outlet_backflow_kg_s'] == 0
    assert f['inlet_area_m2'] == f['outlet_area_m2'] == pytest.approx(math.pi / 4 * (0.05 ** 2 - 0.02 ** 2), rel=1e-8)


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
    for kind in ('mass', 'massGross'):                    # all of it forward: none flows back
        _edit(d / f'postProcessing/domain0/{kind}_inlet_fan/0/surfaceFieldValue.dat',
              lambda s: s.replace('4.00000000e-03', '1.00000000e-06'))
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert f['inlet_c'] is None and f['inlet_kg_s'] == pytest.approx(1e-6) and f['outlet_c'] == 37.5
    assert 'fan_inlet_c' not in r['monitors'] and 'fan_inlet_c_change' not in r['convergence']
    assert r['warnings'] == ["fan inlet: the net flow through it, 1e-06 kg/s, is under 1% of the fan's free-air flow, "
                             'too little to weight a temperature by']


def _gross(d, side, kg_s):
    _edit(d / f'postProcessing/domain0/massGross_{side}_fan/0/surfaceFieldValue.dat',
          lambda s: s.replace('4.00000000e-03', f'{kg_s:.8e}'))


def test_a_little_backflow_keeps_the_temperature_and_says_what_it_is(tmp_path):
    # 5.2 g/s cross the inlet in all, 4 g/s net: (5.2 - 4) / 2 = 0.6 g/s flows back, 15 % of the net. The weighted value
    # is still exactly the one that carries the heat (Q = m_dot c_p dT), but it is not the temperature of the air
    d = recorded('fan-faces-known-profile', tmp_path)
    _gross(d, 'inlet', 0.0052)
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert f['inlet_c'] == 37.5 and f['inlet_backflow_kg_s'] == pytest.approx(0.0006, rel=1e-9)
    assert 'fan_inlet_c' in r['monitors']
    assert r['warnings'] == ['fan inlet: 0.0006 kg/s flows back through it, 15% of the net 0.004 kg/s, so inlet_c is the '
                             'temperature of the net heat flow (right for ṁ c_p ΔT), not of the air crossing it']


def test_backflow_up_to_the_net_flow_gives_no_temperature(tmp_path):
    # 12 g/s cross the outlet in all, 4 g/s net: 4 g/s flows back, as much as the net. The weighted value is then off
    # the forward air by at least the gap between the two streams, and can lie outside the air's own range
    d = recorded('fan-faces-known-profile', tmp_path)
    _gross(d, 'outlet', 0.012)
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert f['outlet_c'] is None and f['inlet_c'] == 37.5 and f['outlet_backflow_kg_s'] == pytest.approx(0.004)
    assert 'fan_outlet_c' not in r['monitors'] and 'fan_outlet_c_change' not in r['convergence']
    assert f['heat_carried_w'] == 50.25                        # the net heat flow is still exact
    assert r['warnings'] == ["fan outlet: 0.004 kg/s flows back through it for 0.004 kg/s net, so the mass-flow-weighted "
                             "value could lie outside the air's own range"]


def test_a_net_flow_running_backwards_gives_no_temperature(tmp_path):
    # the inlet's net flow runs against the axis: no air enters the fan there, whatever the weighting gives
    d = recorded('fan-faces-known-profile', tmp_path)
    _edit(d / 'postProcessing/domain0/mass_inlet_fan/0/surfaceFieldValue.dat',
          lambda s: s.replace('4.00000000e-03', '-3.00000000e-03'))
    r = cfd.read_results(d)
    f = r['fans']['fan']
    assert f['inlet_c'] is None and f['inlet_kg_s'] == pytest.approx(-0.003) and f['inlet_backflow_kg_s'] == pytest.approx(0.0035)
    assert r['warnings'] == ['fan inlet: the net flow through it runs backwards, -0.003 kg/s along the axis, so it has no '
                             'temperature of air entering the fan']


def test_ends_whose_areas_or_flows_disagree_are_named(tmp_path):
    # the two ends of a zone are the ends of the same cells: an outlet half again as large means a face missed cells
    d = recorded('fan-faces-known-profile', tmp_path)
    for kind in ('T', 'mass', 'massGross'):
        _edit(d / f'postProcessing/domain0/{kind}_outlet_fan/0/surfaceFieldValue.dat',
              lambda s: s.replace('# Area          : 1.64933614e-03', '# Area          : 2.47400421e-03'))
    r = cfd.read_results(d)
    assert r['fans']['fan']['outlet_area_m2'] == pytest.approx(2.474e-3, rel=1e-5)
    assert r['warnings'] == ['fan: its inlet and outlet areas differ, 0.00165 against 0.00247 m² (more than 10%): check '
                             'the mesh at the ends of its zone, where a face may have missed cells']
    # and net flows 20 % apart mean air crosses the zone's sides
    d = recorded('fan-faces-known-profile', tmp_path / 'flows')
    for kind in ('mass', 'massGross'):
        _edit(d / f'postProcessing/domain0/{kind}_outlet_fan/0/surfaceFieldValue.dat',
              lambda s: s.replace('4.00000000e-03', '3.20000000e-03'))
    assert cfd.read_results(d)['warnings'] == [
        'fan: its inlet and outlet net flows differ, 0.004 against 0.0032 kg/s (more than 10%): air crosses the sides of '
        'its zone, through the hub or round the rim']


def test_the_face_count_is_the_solvers_not_topoSets(tmp_path):
    # in a parallel run topoSet's log adds each processor's faces, so a face on a processor boundary counts twice; the
    # solver's own header counts each face once
    d = recorded('fan-faces-known-profile', tmp_path)
    _edit(d / 'log.topoSet', lambda s: s.replace('fanInlet now size 24', 'fanInlet now size 30'))
    assert cfd.read_results(d)['zone_faces'] == {'fanInlet': 24, 'fanOutlet': 24}


def test_continuing_a_case_written_before_the_faces_does_not_claim_them(tmp_path):
    from .test_cfd import small_case                       # needs trimesh, as that module does
    c = small_case()
    d = c.write(tmp_path / 'case', np_procs=2)
    c._continue(d, 10)                                     # a case with the faces keeps saying how they are measured
    assert cfd.FACE_LIMIT in json.loads((d / 'cadagent-case.json').read_text())['limits']
    ctl = d / 'system/controlDict'                         # one written before them has no face outputs ...
    ctl.write_text(re.sub(r'\n    (T|mass|massGross)_(inlet|outlet)_fan\n    \{.*?\n    \}', '', ctl.read_text(), flags=re.S))
    assert 'T_inlet_fan' not in ctl.read_text() and 'flux_T' in ctl.read_text()
    c._continue(d, 10)                                     # ... and continuing it adds none, so its limits do not say so
    limits = json.loads((d / 'cadagent-case.json').read_text())['limits']
    assert cfd.FACE_LIMIT not in limits and 'fans are actuator discs with a straight-line fan curve, no swirl' in limits


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


def test_each_end_is_measured_across_two_planes_either_side_of_it_whatever_the_axis():
    f = Fan('f', centre=(10, -20, 30), axis=(1, 2, -2), d_outer=60, d_hub=20, thickness=9, dp0_pa=20, q_free_m3h=30)
    up, down, a = f.ends()
    assert np.allclose(a, np.array([1, 2, -2]) / 3)
    assert np.allclose(up, np.round((np.array([10, -20, 30]) - a * 4.5) / 1000, 6), atol=0)
    assert np.allclose(down, np.round((np.array([10, -20, 30]) + a * 4.5) / 1000, 6), atol=0)
    faces = f.faces()
    for (inside, outside), end, inward in ((faces['inlet'], up, a), (faces['outlet'], down, -a)):
        assert np.allclose(inside - end, inward * cfd.FACE_INSET_M, rtol=0, atol=1e-15)
        assert np.allclose(outside - end, -inward * cfd.FACE_INSET_M, rtol=0, atol=1e-15)
        # one each side of the end plane, both far closer to it than any cell is thin
        assert 0 < float((inside - end) @ inward) < 1e-6 and 0 < float((end - outside) @ inward) < 1e-6


def test_the_case_builds_and_logs_both_faces_of_every_fan(tmp_path):
    from .test_cfd import small_case                       # needs trimesh, as that module does
    c = small_case()
    d = c.write(tmp_path / 'case', np_procs=2)
    ts = (d / 'system/domain0/topoSetDict').read_text()
    f = c.fans[0]
    # every face not on the zone's boundary (cellToFace 'outside', synchronised across processors, then inverted) ...
    off = ('{ name fanOffZoneFaces; type faceSet; action new; source cellToFace; set fanSet; option outside; }\n'
           '    { name fanOffZoneFaces; type faceSet; action invert; }')
    assert off in ts and ts.index('name fanSet;') < ts.index(off)
    for side in ('inlet', 'outlet'):
        inside, outside = f.faces()[side]
        name = f'fan{side.capitalize()}'
        # ... is taken away from the faces that cross a plane just inside each end or one just outside it, oriented
        # along the axis (-z)
        blocks = []
        for act, o in (('new', inside), ('add', outside)):
            m = re.search(rf'\{{ name {name}; type faceZoneSet; action {act}; source planeToFaceZone;(.*?)\}}', ts, re.S)
            assert m, (name, act)
            assert m.group(1).split() == f'point ({o[0]:.9f} {o[1]:.9f} {o[2]:.9f}); normal (0.000000000 0.000000000 -1.000000000); option all;'.split()
            blocks.append(m.start())
        sub = f'{{ name {name}; type faceZoneSet; action subtract; source setToFaceZone; faceSet fanOffZoneFaces; }}'
        assert ts.index(off) < blocks[0] < blocks[1] < ts.index(sub)
        assert 'searchableSurfaceToFaceZone' not in ts                     # never by where a face lies (#224 review)
    # the zone is z from 38 to 42 mm, pushed down (-z): the inlet across its top, the outlet across its bottom
    assert [o[2] for o in f.faces()['inlet']] == pytest.approx([0.042 - 1e-7, 0.042 + 1e-7], abs=1e-12)
    assert [o[2] for o in f.faces()['outlet']] == pytest.approx([0.038 + 1e-7, 0.038 - 1e-7], abs=1e-12)
    cd = (d / 'system/controlDict').read_text()
    for side, zone in (('inlet', 'fanInlet'), ('outlet', 'fanOutlet')):
        t = re.search(rf'T_{side}_fan\s*\{{(.*?)\}}', cd, re.S).group(1)
        assert f'regionType faceZone; name {zone};' in t and 'fields (T); operation weightedAverage; weightField phi;' in t
        assert 'empty-surface warn;' in t and 'writeInterval 10;' in t
        m = re.search(rf'mass_{side}_fan\s*\{{(.*?)\}}', cd, re.S).group(1)
        assert f'name {zone};' in m and 'fields (phi); operation sum;' in m and 'empty-surface warn;' in m
        g = re.search(rf'massGross_{side}_fan\s*\{{(.*?)\}}', cd, re.S).group(1)
        assert f'name {zone};' in g and 'fields (phi); operation sumMag;' in g and 'empty-surface warn;' in g
    assert cfd.FACE_LIMIT in json.loads((d / 'cadagent-case.json').read_text())['limits']


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

def test_a_recorded_ducted_fan_carries_the_heat_that_leaves(tmp_path):
    # the duct is the box's only way out and the plug shuts the hub, so all the air the fan moves was heated once and
    # leaves: at any iteration it carries the heat leaving the room. Nothing crosses the zone's sides, so both ends see
    # the same mass flow through the same area, and the fan adds no heat, so the same temperature
    r = cfd.read_results(recorded('exhaust-ducted', tmp_path))
    f = r['fans']['fan']
    assert r['zone_faces'] == {'fanInlet': 392, 'fanOutlet': 392} and 'error' not in r
    assert f['inlet_area_m2'] == pytest.approx(f['outlet_area_m2'], rel=1e-3)
    assert f['inlet_kg_s'] == pytest.approx(f['outlet_kg_s'], rel=1e-4)
    assert f['inlet_backflow_kg_s'] < 1e-3 * f['inlet_kg_s'] and f['outlet_backflow_kg_s'] < 1e-3 * f['outlet_kg_s']
    assert abs(f['inlet_c'] - f['outlet_c']) <= 0.05
    assert f['heat_carried_w'] == pytest.approx(r['heat_out_w'], rel=0.03)
    # as recorded: 2.77 g/s at 31.32 / 31.33 °C, 17.60 W; the zone's volume average 31.23 °C. The run ends on a swing of
    # its plume, 17.83 W leaving for 20 W put in (-10.9 %), and the energy check says so
    assert (f['inlet_c'], f['outlet_c'], f['air_through_fan_c'], f['heat_carried_w']) == (31.32, 31.33, 31.23, 17.6)
    assert f['outlet_kg_s'] == pytest.approx(0.00276766409, rel=1e-9)
    assert cfd.stream_heat_w(f['outlet_kg_s'], f['outlet_c'], r['ambient_c']) == pytest.approx(f['heat_carried_w'], abs=0.02)
    assert r['energy_balance_pct'] == -10.9 and r['energy_conserved'] is False and r['converged'] is False
    assert len(r['warnings']) == 1 and r['warnings'][0].startswith('energy not conserved: 17.83 W leave')


def test_a_recorded_fan_under_its_opening_carries_more_heat_than_leaves(tmp_path):
    # 3 mm under its opening, the fan takes back air it has pushed out, down through its dead hub and round its rim: that
    # air is counted each time it passes, so the fan's stream carries 32.26 W above the room while 19.61 W leave it. Its
    # m_dot is not the flow through the box, and T_fan - Q / (m_dot c_p) would not give the air upstream
    r = cfd.read_results(recorded('exhaust-under-opening', tmp_path))
    f = r['fans']['fan']
    assert f['heat_carried_w'] == 32.26 and r['heat_out_w'] == 19.61
    assert f['heat_carried_w'] > 1.5 * r['heat_out_w'] and f['heat_carried_w'] > 1.5 * r['heat_input_w']
    assert (f['inlet_c'], f['outlet_c'], f['air_through_fan_c']) == (33.64, 33.57, 33.56)
    # the outlet has the inlet's 408 faces across the zone's end plus 16 at its rim, where cells beyond that end flank
    # it: 2.8 % more area. Air crosses the zone's sides, so the net flows differ by 3.7 %; both under the 10 % that
    # warns. 0.05 g/s flows back through the outlet, 1.3 % of the net, too little to warn about
    assert r['zone_faces'] == {'fanInlet': 408, 'fanOutlet': 424}
    assert f['outlet_area_m2'] / f['inlet_area_m2'] == pytest.approx(1.0284, abs=1e-4)
    assert f['inlet_kg_s'] / f['outlet_kg_s'] == pytest.approx(0.9630, abs=1e-4)
    assert f['outlet_backflow_kg_s'] == pytest.approx(4.7458e-05, rel=1e-4)
    # its last iteration happens to balance: 19.61 W leave for 20 W put in, -2.0 %
    assert r['energy_balance_pct'] == -2.0 and r['energy_conserved'] is True and r['converged'] is True
    assert r['warnings'] == []


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
