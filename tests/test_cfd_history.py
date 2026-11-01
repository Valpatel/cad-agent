"""read_results keeps the whole run: residual and temperature histories joined across continuations, the monitored
values the convergence claim rests on, and where the convergence window lies. Read from recorded-format runs
(tests/fixtures/cfd_runs); no solver runs."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cadagent import cfd

from .cfd_fixtures import recorded

FIELDS = {'Ux', 'Uy', 'Uz', 'h', 'k', 'omega', 'p_rgh'}


def test_histories_cover_the_whole_run_across_continuations(tmp_path):
    # air only (a fin block as a porous zone), a first solve to 200, then continuations from 200 and 260
    r = cfd.read_results(recorded('fins-no-solids', tmp_path))
    res = r['residuals']
    assert set(res) == {'iteration'} | FIELDS                     # all seven, p_rgh included
    assert res['iteration'][0] == 1 and res['iteration'][-1] == 320 and len(res['iteration']) == 320
    assert r['residuals_every'] == 1 and r['iterations'] == 320 and r['planned_iterations'] == 320
    assert r['restarts'] == [200, 260]
    assert r['solids'] == {} and r['T_max_history'] == {}
    assert r['solver_finished'] is True

    mon = r['monitors']
    assert set(mon) == {'fins_air_c', 'fan_intake_c', 'fan_flow_m3h', 'heat_out_w'}
    assert {m['unit'] for m in mon.values()} == {'°C', 'm³/h', 'W'}
    for m in mon.values():
        its = [p[0] for p in m['points']]
        assert its[0] == 10 and its[-1] == 320 and its == sorted(set(its))       # whole run, every 10, no repeats
        assert m['change'] in r['convergence']
    # each history ends on the headline value read_results reports
    assert mon['fan_flow_m3h']['points'][-1][1] == pytest.approx(r['fans']['fan']['flow_m3h'], abs=0.01)
    assert mon['fan_intake_c']['points'][-1][1] == pytest.approx(r['fans']['fan']['air_through_fan_c'], abs=0.01)
    assert mon['fins_air_c']['points'][-1][1] == pytest.approx(r['zones']['fins']['T_c'], abs=0.01)
    assert mon['heat_out_w']['points'][-1][1] == pytest.approx(r['heat_out_w'], abs=0.01)


def test_convergence_is_still_measured_within_the_newest_solve(tmp_path):
    # calibrate_fins relies on it: after a fin-temperature step, only the new solve shows whether the block settled
    d = recorded('fins-no-solids', tmp_path)
    r = cfd.read_results(d)
    newest = np.array(cfd._series(d / 'postProcessing/domain0/zone_fins/260/volFieldValue.dat'))
    tail = newest[newest[:, 0] >= newest[-1, 0] * 0.8]
    assert r['convergence']['fins_T_change_c'] == round(float(tail[-1, 4] - tail[0, 4]), 2)
    assert r['convergence_window'] == [int(tail[0, 0]), 320] and r['convergence_window'][0] > 260


def test_multi_region_run_that_ended_early(tmp_path):
    # air plus two solids; the first solve logged to 150 after saving 100 and diverged, a continuation from 100 reached
    # 200, and the last one, planned to 300, stopped at 236
    r = cfd.read_results(recorded('solids-ended-early', tmp_path))
    assert r['solver_finished'] is False and r['solver_log'] == 'log.solve.1793000002'
    assert r['iterations'] == 236 and r['planned_iterations'] == 300 and r['restarts'] == [100, 200]
    assert set(r['T_max_history']) == {'chip', 'plate'}
    for name, h in r['T_max_history'].items():
        its = [p[0] for p in h]
        assert its[0] == 10 and its[-1] == 230 and its == sorted(set(its))
        assert max(p[1] for p in h) < 100            # the diverged rows the first solve logged after 100 are dropped
        assert h[-1][1] == pytest.approx(r['solids'][name]['max_c'], abs=0.01)
    res = r['residuals']
    assert res['iteration'] == [float(i) for i in range(1, 237)]
    late = [v for k in FIELDS for t, v in zip(res['iteration'], res[k]) if t > 100]
    assert max(late) < 0.5                          # from the continuation, not the diverging first solve
    assert set(r['monitors']) == {'heat_out_w'}     # no fans or fin zones in this case
    # the last solve wrote three samples: too few to measure a change, so nothing is claimed steady
    assert r['convergence'] == {} and 'convergence_window' not in r
    assert r['steady'] is False and r['converged'] is False


def test_a_long_residual_history_keeps_the_largest_value_of_each_run(tmp_path, monkeypatch):
    d = recorded('fins-no-solids', tmp_path)
    monkeypatch.setattr(cfd, 'RESIDUAL_POINTS', 50)
    r = cfd.read_results(d)
    every = r['residuals_every']
    assert every == math.ceil(320 / 50)
    raw = cfd._whole_run(cfd._outputs(d / 'postProcessing', 'residuals', 'solverInfo'), cfd._residual_rows)
    its = r['residuals']['iteration']
    assert len(its) == math.ceil(320 / every) and its[-1] == 320
    for j, i in enumerate(range(0, 320, every)):
        rows = raw[i:i + every]
        assert its[j] == rows[-1][0]
        assert r['residuals']['p_rgh'][j] == max(row[1]['p_rgh'] for row in rows)    # a spike is never thinned away


def test_residual_rows_tolerate_missing_and_cut_short_values(tmp_path):
    f = tmp_path / 'residuals' / '0' / 'solverInfo.dat'
    f.parent.mkdir(parents=True)
    f.write_text('# Solver information\n# Time          \tU_solver        \tUx_initial      \th_initial       \n'
                 '1               \tDILUPBiCGStab\t1.0e-01\tN/A\n'
                 '2               \tDILUPBiCGStab\t9.0e-02\t5.0e-03\n'
                 '3               \tDILUPBiCGStab\t8.0e-')                  # the solver stopped mid-line
    rows = cfd._residual_rows(f)
    assert rows == [[1.0, {'Ux': 0.1, 'h': None}], [2.0, {'Ux': 0.09, 'h': 0.005}], [3.0, {'Ux': None, 'h': None}]]
