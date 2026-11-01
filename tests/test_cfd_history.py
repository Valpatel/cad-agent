"""read_results keeps the whole run: residual and temperature histories joined across continuations, the monitored
values the convergence claim rests on, and where the convergence window lies. Read from recorded-format runs
(tests/fixtures/cfd_runs); no solver runs."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cadagent.simulation import cfd

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
    # what steady holds each change to: every temperature to 1 °C, the fin block's air too, and the changes in % to 2.
    # Pinned so the numbers calibrate_fins and run_until_balanced rely on cannot change unnoticed
    assert r['convergence_limits'] == {'fins_T_change_c': 1.0, 'fan_flow_change_pct': 2.0, 'fan_intake_c_change': 1.0,
                                       'heat_out_change_pct': 2.0}


def test_every_temperature_change_is_held_to_1_c_and_every_percentage_to_2():
    # by unit, the rule the chart's captions use (a key ending _pct is in %, any other in °C); a fin block's key ends
    # _T_change_c, not _c_change, and once got 2 °C (#175)
    assert {k: cfd._change_limit(k) for k in ('chip_max_c_change', 'fins_T_change_c', 'fan_intake_c_change',
                                              'fan_flow_change_pct', 'heat_out_change_pct')} == \
        {'chip_max_c_change': 1.0, 'fins_T_change_c': 1.0, 'fan_intake_c_change': 1.0, 'fan_flow_change_pct': 2.0,
         'heat_out_change_pct': 2.0}


def test_a_fin_block_whose_air_still_drifts_by_1_5_c_is_not_steady(tmp_path):
    # the fan flow, the air through the fan and the heat leaving have settled and the heat balances, but the block's
    # mean air still rose 1.5 °C over the window: past its 1 °C, so neither steady nor converged (#175)
    r = cfd.read_results(recorded('fins-block-drifting', tmp_path))
    assert r['convergence_window'] == [80, 100] and r['convergence']['fins_T_change_c'] == 1.5
    assert r['convergence_limits']['fins_T_change_c'] == 1.0
    others = {k: v for k, v in r['convergence'].items() if k != 'fins_T_change_c'}
    assert set(others) == {'fan_flow_change_pct', 'fan_intake_c_change', 'heat_out_change_pct'}
    assert all(abs(v) < r['convergence_limits'][k] for k, v in others.items())
    assert abs(r['energy_balance_pct']) <= 5 and 'error' not in r
    assert r['steady'] is False and r['converged'] is False


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


def test_a_continuation_from_the_same_saved_time_is_read(tmp_path):
    # solids-ended-early continued again: the stopped solve saved nothing after 200, so the next one starts from 200
    # too, and OpenFOAM writes its rows to <kind>_200.dat beside the stopped solve's <kind>.dat
    d = recorded('solids-continued-again', tmp_path)
    r = cfd.read_results(d)
    assert r['solver_finished'] is True and r['solver_log'] == 'log.solve.1793000003'
    assert r['iterations'] == 300 and r['restarts'] == [100, 200, 200]      # one entry per continuation
    assert r['residuals']['iteration'] == [float(i) for i in range(1, 301)]
    for name, h in r['T_max_history'].items():
        its = [p[0] for p in h]
        assert its[-1] == 300 and its == sorted(set(its))      # the stopped solve's rows after 200 replaced, not repeated
        assert h[-1][1] == pytest.approx(r['solids'][name]['max_c'], abs=0.01)
    assert r['monitors']['heat_out_w']['points'][-1] == [300, pytest.approx(r['heat_out_w'], abs=0.01)]
    # judged on the newest solve's rows (210-300), not the stopped one's (210-230)
    newest = np.array(cfd._series(d / 'postProcessing/chip/T_max_chip/200/volFieldValue_200.dat'))
    tail = newest[newest[:, 0] >= newest[-1, 0] * 0.8]
    assert r['convergence']['chip_max_c_change'] == round(float(tail[-1, 1] - tail[0, 1]), 2)
    assert r['convergence_window'] == [240, 300]


def test_a_continuation_that_crashed_at_start_replaces_nothing(tmp_path):
    # the first solve saved 100, diverged and logged to 150; the continuation from 100 crashed at start and left
    # header-only files. It logged nothing, so the histories, the headline values and the convergence window all
    # describe the same rows: the first solve's, divergence included
    r = cfd.read_results(recorded('solids-crashed-restart', tmp_path))
    assert r['solver_finished'] is False and r['solver_log'] == 'log.solve.1793000001'
    assert r['iterations'] == 150 and r['restarts'] == []
    assert r['residuals']['iteration'] == [float(i) for i in range(1, 151)]
    for name, h in r['T_max_history'].items():
        assert h[-1][0] == 150 and h[-1][1] == pytest.approx(r['solids'][name]['max_c'], abs=0.01)
        assert h[-1][1] > 500                                   # the divergence is shown, not cut off at the save
    assert r['monitors']['heat_out_w']['points'][-1] == [150, pytest.approx(r['heat_out_w'], abs=0.01)]
    assert r['convergence_window'] == [120, 150]
    assert r['steady'] is False and r['converged'] is False


@pytest.mark.parametrize('name, last', [('solids-short-continuation', 104), ('solids-one-step-continuation', 101)])
def test_a_continuation_that_stopped_before_its_first_sample_still_replaces_the_rows_after_its_start(tmp_path, name, last):
    # the first solve saved 100, diverged and logged to 150; the continuation from 100 stopped at `last`, before its first
    # temperature and heat sample at 110, so it logged residuals and nothing else. It still replaces whatever the first
    # solve logged after 100: the histories and the headline values end at 100, before the divergence, and the newest
    # solve measured no change, so there is no window and nothing is claimed steady (#176)
    r = cfd.read_results(recorded(name, tmp_path))
    assert r['solver_finished'] is False and r['solver_log'] == 'log.solve.1793000001'
    assert r['iterations'] == last and r['restarts'] == [100]
    res = r['residuals']
    assert res['iteration'] == [float(i) for i in range(1, last + 1)]
    assert max(v for k in FIELDS for t, v in zip(res['iteration'], res[k]) if t > 100) < 0.5    # the continuation's
    assert set(r['T_max_history']) == {'chip', 'plate'}
    for solid, h in r['T_max_history'].items():
        its = [p[0] for p in h]
        assert its[0] == 10 and its[-1] == 100 and its == sorted(set(its))
        assert max(p[1] for p in h) < 100                       # the diverged rows the first solve logged after 100 are gone
        assert h[-1][1] == pytest.approx(r['solids'][solid]['max_c'], abs=0.01)
        assert r['solids'][solid]['mean_c'] < r['solids'][solid]['max_c']
    assert r['air_max_c'] < 100
    assert set(r['monitors']) == {'heat_out_w'}
    assert r['monitors']['heat_out_w']['points'][-1] == [100, pytest.approx(r['heat_out_w'], abs=0.01)]
    assert r['convergence'] == {} and 'convergence_window' not in r and r['convergence_limits'] == {}
    assert r['steady'] is False and r['converged'] is False


def test_a_short_continuation_then_a_full_one_from_the_same_saved_time(tmp_path):
    # the first solve saved 100, diverged and logged to 150; a continuation from 100 stopped at 104, before its first
    # temperature sample; the next one starts from 100 again (nothing was saved after it) and finishes at 300, writing
    # <kind>_100.dat beside the stopped one's files. Each continuation replaces the rows after 100: the result is the
    # first solve to 100, then the full one, with the short one's residuals gone too (#193 follow-up)
    d = recorded('solids-short-then-full-continuation', tmp_path)
    r = cfd.read_results(d)
    assert r['solver_finished'] is True and r['solver_log'] == 'log.solve.1793000002'
    assert r['iterations'] == 300 and r['restarts'] == [100, 100]          # one entry per continuation
    res = r['residuals']
    assert res['iteration'] == [float(i) for i in range(1, 301)]
    full = {int(t): v for t, v in cfd._residual_rows(d / 'postProcessing/domain0/residuals/100/solverInfo_100.dat')}
    short = {int(t): v for t, v in cfd._residual_rows(d / 'postProcessing/domain0/residuals/100/solverInfo.dat')}
    assert sorted(short) == [101, 102, 103, 104]
    for i in range(101, 105):                                  # the full solve's, not the short one's
        assert all(res[k][i - 1] == full[i][k] for k in FIELDS) and any(full[i][k] != short[i][k] for k in FIELDS)
    for solid, h in r['T_max_history'].items():
        its = [p[0] for p in h]
        assert its == [float(t) for t in range(10, 301, 10)]   # 10-100 from the first solve, 110-300 from the full one
        assert max(p[1] for p in h) < 100                       # the first solve's diverged rows after 100 are gone
        assert h[-1][1] == pytest.approx(r['solids'][solid]['max_c'], abs=0.01)
    assert r['monitors']['heat_out_w']['points'][-1] == [300, pytest.approx(r['heat_out_w'], abs=0.01)]
    # judged on the full solve's rows, from 80 % of its last iteration
    newest = np.array(cfd._series(d / 'postProcessing/chip/T_max_chip/100/volFieldValue_100.dat'))
    tail = newest[newest[:, 0] >= 240]
    assert r['convergence']['chip_max_c_change'] == round(float(tail[-1, 1] - tail[0, 1]), 2)
    assert r['convergence_window'] == [240, 300]


def test_a_long_residual_history_keeps_the_largest_value_of_each_run(tmp_path, monkeypatch):
    d = recorded('fins-no-solids', tmp_path)
    monkeypatch.setattr(cfd, 'RESIDUAL_POINTS', 50)
    r = cfd.read_results(d)
    every = r['residuals_every']
    assert every == math.ceil(319 / 49)                         # iteration 1 kept, then runs of `every`
    raw = cfd._whole_run(cfd._outputs(d / 'postProcessing', 'residuals', 'solverInfo'), cfd._residual_rows)
    its = r['residuals']['iteration']
    assert its[0] == 1 and r['residuals']['p_rgh'][0] == raw[0][1]['p_rgh']     # the first iteration, exact
    assert len(its) == 1 + math.ceil(319 / every) <= 50 and its[-1] == 320
    for j, i in enumerate(range(1, 320, every), start=1):
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
