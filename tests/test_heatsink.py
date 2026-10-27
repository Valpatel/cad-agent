"""Plate-fin heatsink model: limits it must reproduce, monotonic trends, the fan operating point and the porous fit."""

from __future__ import annotations

import math

import pytest

from cadagent.heatsink import AIR, FanCurve, PlateFin, operating_point


def sink(**kw):
    d = dict(length=100, width=87, fin_height=14, fin_thickness=0.3, pitch=1.8, base_thickness=3.5, k_base=1500,
             flow_length=50, branches=2, source=(48, 48))
    d.update(kw)
    return PlateFin(**d)


def test_long_channel_friction_tends_to_parallel_plates():
    # Fully developed laminar flow between plates: Fanning f Re = 24 (Dh = 2 b). A very long, slow channel must get there.
    hs = sink(flow_length=5000, turn_loss=0.0, pitch=10.0, fin_thickness=0.5)
    q = 1e-5
    u = hs.channel_velocity(q)
    dh = 2 * hs.gap / 1000
    re = AIR['rho'] * u * dh / AIR['mu']
    dp_friction = 24 / re * 4 * 5.0 / dh * 0.5 * AIR['rho'] * u ** 2
    assert hs.pressure_drop(q) == pytest.approx(dp_friction, rel=0.05)
    assert hs.pressure_drop(q, core_only=True) <= hs.pressure_drop(q)


def test_trends():
    hs = sink()
    qs = [0.002, 0.004, 0.008]
    dps = [hs.pressure_drop(q) for q in qs]
    rs = [hs.resistance(q) for q in qs]
    assert dps == sorted(dps)
    assert rs == sorted(rs, reverse=True)
    assert 0 < hs.fin_efficiency(hs.h(0.004)) <= 1


def test_operating_point_is_on_both_curves():
    hs, fan = sink(), FanCurve(15.2, 38.9)
    op = operating_point(hs, fan)
    assert 0 < op['q_m3h'] < 38.9
    assert hs.pressure_drop(op['q_m3s']) == pytest.approx(fan.dp(op['q_m3s']), rel=1e-3)


def test_porous_fit_reproduces_the_channel_pressure_drop():
    hs = sink()
    pc = hs.porous_coefficients()
    face = hs.width * hs.fin_height * 1e-6 * hs.branches
    q = 0.006
    v = q / face
    dp = (AIR['mu'] * pc['d'] * v + 0.5 * AIR['rho'] * pc['f'] * v ** 2) * pc['flow_length_m']
    assert dp == pytest.approx(hs.pressure_drop(q, core_only=True), rel=0.1)
    assert pc['d_vector'][1] == pytest.approx(1000 * pc['d']) and pc['d_vector'][0] == pc['d_vector'][2] == pc['d']


def test_resistance_respects_the_air_limit():
    # At low flow the fins approach the air's own limit 1/(m cp) (inlet-referenced h) and never beat it; they stay
    # within 1/eta of it.
    hs = sink()
    for q in (0.0005, 0.001, 0.002):
        r = hs.resistance(q, detail=True)
        fins = r['total_k_per_w'] - r['spreading'] - r['base']
        assert fins >= r['air_limit'] * 0.999
        assert fins <= r['air_limit'] / r['fin_efficiency'] * 1.25


def test_seeed_cooler_rating_is_plausible():
    # The datasheet rates the 100 x 87 x 34 cooler at 100-120 W; at 110 W the plate must stay near the 80 C limit at 25 C.
    hs, fan = sink(), FanCurve(15.2, 38.9)
    op = operating_point(hs, fan)
    rise = 110 * hs.resistance(op['q_m3s'])
    assert 25 < rise < 60
