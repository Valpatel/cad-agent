"""Closed-loop linkages (#187): the five-bar closed forms in cadagent.formulas and the sweeps in
cadagent.mechanical.linkages, against published closed forms written out here and derived by hand.

* The five-bar's direct and inverse kinematics against Liu, Wang and Zheng's closed forms as Goncalves, Carvalho and
  Santos restate them (COBEM 2009, Section 2, Eqs. (3)-(15)): a different algebra (a line and a quadratic, and the
  tangent of the half angle), not two circles.
* The four-bar against Norton's Example 4-1, the toggle positions by the law of cosines, and Freudenstein's equation.
* The Jacobians against finite differences of the solved positions, so a determinant means what it says.
* The docs figure (tools/linkage_figures.py) against its generator and the closed-form lock it quotes.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import pytest

from cadagent import formulas as fx
from cadagent.mechanical import linkages as L

ROOT = Path(__file__).resolve().parents[2]

DEG = math.radians


# ----------------------------------------------------------------------------- the published closed forms

def liu_direct(r1, r2, r3, t1, t2):
    """The 5R's tip from its inputs, Goncalves et al. Eqs. (10)-(15): frame at the base's centre, A1 = (-r3, 0),
    A2 = (r3, 0), cranks r1, distal links r2. Returns both solutions, or [] where they are complex. None where the line
    x = e y + f is undefined (the knees one above the other)."""
    den = 2 * r3 + r1 * math.cos(t2) - r1 * math.cos(t1)
    if abs(den) < 1e-9 * r1:
        return None
    e = r1 * (math.sin(t1) - math.sin(t2)) / den
    f = r1 * r3 * (math.cos(t2) + math.cos(t1)) / den
    dd = 1 + e * e
    g = 2 * (e * f - e * r1 * math.cos(t1) + e * r3 - r1 * math.sin(t1))
    h = f * f - 2 * f * (r1 * math.cos(t1) - r3) - 2 * r1 * r3 * math.cos(t1) + r3 * r3 + r1 * r1 - r2 * r2
    disc = g * g - 4 * dd * h
    if disc < 0:
        return []
    return [(e * y + f, y) for y in ((-g + s * math.sqrt(disc)) / (2 * dd) for s in (1, -1))]


def liu_inverse(r1, r2, r3, x, y):
    """The 5R's four input pairs for a tip (x, y), Goncalves et al. Eqs. (5)-(7): theta_i = 2 atan z_i, z_i the roots
    of a_i z^2 + b_i z + c_i = 0. [] where the tip is out of reach."""
    roots = []
    for sx in (r3, -r3):                                   # arm 1 has x + r3, arm 2 x - r3
        k = r1 * r1 + y * y + (x + sx) ** 2 - r2 * r2
        a, b, c = k + 2 * (x + sx) * r1, -4 * y * r1, k - 2 * (x + sx) * r1
        if abs(a) < 1e-12 * r1 * r1:
            return None                                    # a root at infinity (theta = 180 degrees): not covered
        disc = b * b - 4 * a * c
        if disc < 0:
            return []
        roots.append([2 * math.atan((-b + s * math.sqrt(disc)) / (2 * a)) for s in (1, -1)])
    return [(t1, t2) for t1 in roots[0] for t2 in roots[1]]


def same_angle(a, b, tol):
    return abs(math.remainder(a - b, 2 * math.pi)) <= tol


# Symmetric 5Rs: Goncalves et al.'s example (r1 = r2 = r3 = 0.1 m, Section 3.3), and one with longer distal links.
FIVEBARS = [(0.1, 0.1, 0.1), (0.1, 0.15, 0.04)]


@pytest.mark.parametrize("r1,r2,r3", FIVEBARS)
def test_fivebar_point_gives_the_published_direct_kinematics(r1, r2, r3):
    checked = 0
    for d1, d2 in itertools.product(range(-180, 180, 15), repeat=2):
        t1, t2 = DEG(d1), DEG(d2)
        theirs = liu_direct(r1, r2, r3, t1, t2)
        if theirs is None:
            continue
        ours = {m: fx.fivebar_point(r1, r2, r1, r2, 2 * r3, t1, t2, m) for m in (1, -1)}
        if not theirs:
            # complex roots: no tip, unless the distal links are in line to round-off, where ours closes them
            j = fx.fivebar_jacobians(r1, r2, r1, r2, 2 * r3, t1, t2)
            assert ours == {1: None, -1: None} or j["transmission"] < 1e-6, (d1, d2)
            continue
        c1 = (r1 * math.cos(t1) - r3, r1 * math.sin(t1))
        c2 = (r3 + r1 * math.cos(t2), r1 * math.sin(t2))
        # where the distal links line up the two tips are a double root, which either algebra finds only to about
        # the square root of round-off
        near_lock = fx.fivebar_jacobians(r1, r2, r1, r2, 2 * r3, t1, t2)["transmission"] < 1e-4
        for m, p in ours.items():
            assert p is not None, (d1, d2, m)
            q = (p[0] - r3, p[1])                         # into their frame
            assert min(math.dist(q, t) for t in theirs) < (1e-7 if near_lock else 1e-12) * r1, (d1, d2, m)
            # mode +1 is the tip left of the line from knee 1 to knee 2
            side = (c2[0] - c1[0]) * (q[1] - c1[1]) - (c2[1] - c1[1]) * (q[0] - c1[0])
            assert side * m >= -1e-15, (d1, d2, m)
        checked += 1
    assert checked > 200


@pytest.mark.parametrize("r1,r2,r3", FIVEBARS)
def test_fivebar_inputs_gives_the_published_inverse_kinematics(r1, r2, r3):
    checked = 0
    span = 2 * (r1 + r2)
    for i, k in itertools.product(range(-30, 31), range(-30, 31)):
        x, y = span * i / 30, span * k / 30
        theirs = liu_inverse(r1, r2, r3, x, y)
        if theirs is None:
            continue
        ours = [fx.fivebar_inputs(r1, r2, r1, r2, 2 * r3, x + r3, y, w) for w in itertools.product((1, -1), repeat=2)]
        if not theirs:
            # out of reach, unless the tip is on an arm's edge to round-off, where ours reaches it
            edge = min(abs(math.dist((x, y), (sx, 0)) - lim) for sx in (-r3, r3) for lim in (r1 + r2, abs(r1 - r2)))
            assert all(o is None for o in ours) or edge < 1e-12 * r1, (x, y)
            continue
        assert all(o is not None for o in ours), (x, y)
        for o in ours:
            assert any(same_angle(o[0], t[0], 1e-9) and same_angle(o[1], t[1], 1e-9) for t in theirs), (x, y, o)
            # and the tip they give is the tip asked for, on one of the two assemblies
            tips = [fx.fivebar_point(r1, r2, r1, r2, 2 * r3, *o, m) for m in (1, -1)]
            # at an arm's edge its two knees are a double root, and with the distal links in line the two tips are:
            # either is found to about the square root of round-off
            j = [fx.fivebar_jacobians(r1, r2, r1, r2, 2 * r3, *o, m) for m in (1, -1)]
            edge = min(abs(v) for jm in j if jm for v in (jm["direct"], *jm["inverse"])) < 1e-4
            assert min(math.dist(t, (x + r3, y)) for t in tips if t) < (1e-7 if edge else 1e-12) * r1
        checked += 1
    assert checked > 200


def test_the_tip_reaches_exactly_the_two_annuli():
    # Each arm reaches |a - b| <= |P - pivot| <= a + b, so the workspace is where the two annuli overlap.
    a1, b1, a2, b2, d = 100, 60, 80, 120, 70
    reach = L.fivebar_reach(a1, b1, a2, b2, d)
    assert [(r["inner"], r["outer"]) for r in reach] == [(40, 160), (40, 200)]
    inside = outside = 0
    for i, k in itertools.product(range(-60, 61), repeat=2):
        p = (5.0 * i, 5.0 * k)
        rs = [math.dist(p, r["pivot"]) for r in reach]
        if any(min(abs(x - r["inner"]), abs(x - r["outer"])) < 1e-6 for x, r in zip(rs, reach)):
            continue
        want = all(r["inner"] < x < r["outer"] for x, r in zip(rs, reach))
        got = fx.fivebar_inputs(a1, b1, a2, b2, d, *p)
        assert (got is not None) == want, p
        inside += want
        outside += not want
    assert inside > 1000 and outside > 1000


def test_the_jacobians_are_what_finite_differences_say():
    # A dP = B dtheta: rows (P - C_i) of A, B_ii = cross(C_i - pivot_i, P - C_i). Solve dP/dtheta by finite
    # differences and check the identity column by column, and that det A and B_ii are the normalised values.
    a1, b1, a2, b2, d = 0.1, 0.15, 0.08, 0.12, 0.07
    h = 1e-7
    checked = 0
    for d1, d2 in itertools.product(range(-170, 180, 20), repeat=2):
        for m in (1, -1):
            t1, t2 = DEG(d1), DEG(d2)
            j = fx.fivebar_jacobians(a1, b1, a2, b2, d, t1, t2, m)
            if j is None or j["transmission"] < DEG(5) or min(abs(v) for v in j["inverse"]) < 0.05:
                continue
            p = j["tip"]
            c = [(a1 * math.cos(t1), a1 * math.sin(t1)), (d + a2 * math.cos(t2), a2 * math.sin(t2))]
            assert math.dist(p, c[0]) == pytest.approx(b1, rel=1e-12)
            assert math.dist(p, c[1]) == pytest.approx(b2, rel=1e-12)
            cols = []
            for k in range(2):
                hi = fx.fivebar_point(a1, b1, a2, b2, d, t1 + h * (k == 0), t2 + h * (k == 1), m)
                lo = fx.fivebar_point(a1, b1, a2, b2, d, t1 - h * (k == 0), t2 - h * (k == 1), m)
                cols.append(((hi[0] - lo[0]) / (2 * h), (hi[1] - lo[1]) / (2 * h)))
            pivots = [(0.0, 0.0), (d, 0.0)]
            for i in range(2):
                row = (p[0] - c[i][0], p[1] - c[i][1])
                knee = (c[i][0] - pivots[i][0], c[i][1] - pivots[i][1])
                bii = knee[0] * row[1] - knee[1] * row[0]
                for k in range(2):
                    lhs = row[0] * cols[k][0] + row[1] * cols[k][1]
                    assert lhs == pytest.approx(bii if i == k else 0.0, abs=1e-8 * b1 * a1), (d1, d2, m, i, k)
                assert j["inverse"][i] == pytest.approx(bii / ((a1, a2)[i] * (b1, b2)[i]), abs=1e-12)
            det_a = (p[0] - c[0][0]) * (p[1] - c[1][1]) - (p[1] - c[0][1]) * (p[0] - c[1][0])
            assert j["direct"] == pytest.approx(det_a / (b1 * b2), abs=1e-12)
            assert math.copysign(1, j["direct"]) == m
            checked += 1
    assert checked > 50


def test_a_four_bar_is_a_five_bar_without_a_second_crank():
    # a1 = a, b1 = b, a2 = 0, b2 = c: the tip is the coupler-rocker pin, mode +1 the open branch, and the transmission
    # angle the same as transmission_angle's. Two derivations (Freudenstein's equation and two circles) agree.
    checked = 0
    for a, b, c, d in itertools.product((1, 2, 3, 5), repeat=4):
        for deg in range(-175, 180, 10):
            t2 = DEG(deg)
            for m, crossed in ((1, False), (-1, True)):
                r = fx.fourbar_angles(a, b, c, d, t2, crossed=crossed)
                p = fx.fivebar_point(a, b, 0, c, d, t2, 0.0, m)
                if r is None or p is None:
                    assert r is None and p is None or fx.transmission_angle(a, b, c, d, t2) < 1e-6, (a, b, c, d, deg)
                    continue
                assert math.dist(p, (d + c * math.cos(r[1]), c * math.sin(r[1]))) < 1e-9 * max(a, b, c, d)
                j = fx.fivebar_jacobians(a, b, 0, c, d, t2, 0.0, m)
                assert j["transmission"] == pytest.approx(fx.transmission_angle(a, b, c, d, t2), abs=1e-9)
                assert j["inverse"][1] is None
                checked += 1
    assert checked > 2000


def test_fivebar_formulas_refuse_what_is_not_a_five_bar():
    with pytest.raises(ValueError):
        fx.fivebar_point(1, 0, 1, 1, 1, 0, 0)
    with pytest.raises(ValueError):
        fx.fivebar_point(-1, 1, 1, 1, 1, 0, 0)
    with pytest.raises(ValueError):
        fx.fivebar_point(1, 1, 1, 1, 1, 0, 0, mode=0)
    with pytest.raises(ValueError):
        fx.fivebar_inputs(0, 1, 1, 1, 1, 0.5, 0.5)
    with pytest.raises(ValueError):
        fx.fivebar_inputs(1, 1, 1, 1, 1, 0.5, 0.5, working=(1, 2))
    # knees that coincide have a circle of tips (equal distal links) or none: no answer
    assert fx.fivebar_point(1, 1, 1, 1, 2, 0.0, math.pi) is None


# ----------------------------------------------------------------------------- four-bar sweeps

def test_sweep_fourbar_matches_norton_example_4_1_on_both_branches():
    # Norton, Design of Machinery, Example 4-1: a = 40, b = 120, c = 80, d = 100 at theta2 = 40 degrees.
    for branch, want in (("open", [20.298, 57.325]), ("crossed", [-60.978, -98.005])):
        r = L.sweep_fourbar(40, 120, 80, 100, [40], branch=branch)
        ang = r["steps"][0]["angles_deg"]
        assert [ang["theta3"], ang["theta4"]] == pytest.approx(want, abs=5e-4)
        assert r["steps"][0]["branch"] == branch
        assert r["steps"][0]["transmission_deg"] == pytest.approx(math.degrees(fx.transmission_angle(
            40, 120, 80, 100, DEG(40))), abs=1e-9)


def test_every_pose_closes_and_satisfies_freudensteins_equation():
    for a, b, c, d in ((40, 120, 80, 100), (100, 80, 70, 60), (80, 40, 120, 100), (50, 100, 50, 100)):
        k1, k2, k3 = d / a, d / c, (a * a - b * b + c * c + d * d) / (2 * a * c)
        for branch in ("open", "crossed"):
            r = L.sweep_fourbar(a, b, c, d, range(-180, 181, 3), branch=branch)
            for s in r["steps"]:
                if not s["reachable"]:
                    continue
                t2, t3, t4 = (DEG(s["angles_deg"][k]) for k in ("theta2", "theta3", "theta4"))
                assert k1 * math.cos(t4) - k2 * math.cos(t2) + k3 == pytest.approx(math.cos(t2 - t4), abs=1e-9)
                pins = s["pins"]
                assert math.dist(pins["B"], (0, 0)) == pytest.approx(a)
                assert math.dist(pins["B"], pins["C"]) == pytest.approx(b)
                assert math.dist(pins["C"], (d, 0)) == pytest.approx(c)
                # the sign of det_direct is the branch (where they meet, at a change point, it is 0 to round-off)
                assert s["det_direct"] * (1 if branch == "open" else -1) > -1e-12


def test_the_rockers_extremes_are_the_toggle_positions_by_the_law_of_cosines():
    # A crank-rocker's rocker stops where crank and coupler line up: the pin C is a + b (stretched) or b - a (folded)
    # from the crank pivot, so cos(theta2) = (e^2 + d^2 - c^2) / (2 e d) with e that distance (Norton 4-1: 24.147 and
    # 231.318 degrees).
    a, b, c, d = 40, 120, 80, 100
    r = L.sweep_fourbar(a, b, c, d, [i * 2.5 for i in range(145)])
    got = sorted(e["at_deg"]["theta2"] for e in r["events"] if e["kind"] == "in-line")
    stretched = math.degrees(math.acos(((a + b) ** 2 + d * d - c * c) / (2 * (a + b) * d)))
    folded = 180 + math.degrees(math.acos(((b - a) ** 2 + d * d - c * c) / (2 * (b - a) * d)))
    assert got == pytest.approx([stretched, folded], abs=1e-9)
    assert stretched == pytest.approx(24.147, abs=1e-3) and folded == pytest.approx(231.318, abs=1e-3)
    # the rocker's range is between them: theta4 at the two extremes
    lo, hi = r["summary"]["angle_ranges_deg"]["theta4"]
    assert hi - lo < 90 and r["summary"]["reachable_steps"] == 145
    # its crank turns fully, and its lowest transmission angle is 26.4 degrees at 0: a warning, not a failure
    assert r["grashof"]["inversion"] == "crank-rocker" and r["input_limits_deg"]["full_turn"]
    assert r["summary"]["min_transmission_deg"] == pytest.approx(26.384, abs=1e-3)
    assert r["steps"][r["summary"]["min_transmission_step"]]["inputs_deg"]["theta2"] % 360 == 0
    assert r["status"] == "warn" and not r["problems"]


@pytest.mark.parametrize("links", [(100, 80, 70, 60), (80, 40, 120, 100), (60, 30, 50, 70)])
def test_the_locks_found_by_bisection_are_fourbar_input_limits(links):
    lim = fx.fourbar_input_limits(*links)
    edges = sorted(math.degrees(v) * s for v in (lim["folded"], lim["stretched"]) if v is not None for s in (1, -1))
    r = L.sweep_fourbar(*links, [-180 + i * 0.7 for i in range(515)])
    locks = sorted(e["at_deg"]["theta2"] for e in r["events"] if e["kind"] == "lock")
    assert locks == pytest.approx(edges, abs=1e-9)
    for e in r["events"]:
        if e["kind"] == "lock":
            assert e["transmission_deg"] < 1e-3                 # coupler and rocker in line at the edge
    assert r["status"] == "fail" and r["summary"]["unreachable_steps"]
    # the reachable runs lie inside the exact limits
    for first, last in r["summary"]["reachable_runs"]:
        for i in (first, last):
            t = abs(r["steps"][i]["inputs_deg"]["theta2"])
            assert (lim["folded"] is None or t >= math.degrees(lim["folded"])) and \
                   (lim["stretched"] is None or t <= math.degrees(lim["stretched"]))


def test_hold_keeps_the_branch_and_nearest_flags_a_flip_at_a_lock():
    # A triple rocker one millionth of a degree inside its limit, then a degree back: the branches have met, and the
    # crossed one is nearer the last pose. 'hold' stays open; 'nearest' takes crossed and says so.
    a, b, c, d = 100, 80, 70, 60
    edge = math.degrees(fx.fourbar_input_limits(a, b, c, d)["stretched"])
    path = [edge - 1e-6, edge - 1 - 1e-6, edge - 2]
    hold = L.sweep_fourbar(a, b, c, d, path)
    near = L.sweep_fourbar(a, b, c, d, path, track="nearest")
    assert [s["branch"] for s in hold["steps"]] == ["open"] * 3 and hold["summary"]["flips"] == 0
    assert [s["branch"] for s in near["steps"]] == ["open", "crossed", "crossed"]
    assert near["summary"]["flips"] == 1 and "flip" in near["steps"][1]["flags"]
    assert [e["kind"] for e in near["events"]] == ["flip"] and near["events"][0]["between"] == [0, 1]
    assert near["status"] == "fail" and any("flip" in p for p in near["problems"])
    # at the lock itself both reports flag it
    assert "lock" in hold["steps"][0]["flags"] and hold["status"] == "fail"


def test_nearest_does_not_flip_where_the_steps_are_small():
    # A double rocker driven to just short of both limits and back in 0.5 degree steps: no flip on either branch.
    lim = fx.fourbar_input_limits(80, 40, 120, 100)
    lo, hi = math.degrees(lim["folded"]) + 0.3, math.degrees(lim["stretched"]) - 0.3
    n = 140
    there = [lo + (hi - lo) * i / n for i in range(n + 1)]
    for branch in ("open", "crossed"):
        r = L.sweep_fourbar(80, 40, 120, 100, there + there[::-1], branch=branch, track="nearest")
        assert r["summary"]["flips"] == 0 and r["summary"]["reachable_steps"] == 2 * (n + 1)
        assert {s["branch"] for s in r["steps"]} == {branch}


def test_sweep_reports_are_plain_json_and_refuse_bad_arguments():
    r = L.sweep_fourbar(100, 80, 70, 60, range(-180, 181, 30))
    json.dumps(r, allow_nan=False)
    assert r["limits"] == L.LIMITS and r["schema_version"] == 1
    with pytest.raises(ValueError):
        L.sweep_fourbar(40, 120, 80, 100, [0], branch="up")
    with pytest.raises(ValueError):
        L.sweep_fourbar(40, 120, 80, 100, [0], track="closest")
    with pytest.raises(ValueError):
        L.sweep_fourbar(40, 120, 80, 100, [0], guideline_deg=0.5)
    with pytest.raises(ValueError):
        L.sweep_fourbar(0, 120, 80, 100, [0])


# ----------------------------------------------------------------------------- five-bar sweeps

def test_a_symmetric_five_bar_locks_where_its_distal_links_line_up():
    # Cranks a, distal links b, ground d, moved symmetrically (theta2 = 180 - theta1): the knees are d - 2 a cos theta1
    # apart, so the distal links stretch into one line where cos theta1 = (d - 2 b) / (2 a).
    a, b, d = 100, 120, 80
    path = [(120 + 0.5 * i, 60 - 0.5 * i) for i in range(81)]
    r = L.sweep_fivebar(a, b, a, b, d, path)
    want = math.degrees(math.acos((d - 2 * b) / (2 * a)))
    locks = [e for e in r["events"] if e["kind"] == "lock"]
    assert len(locks) == 1 and locks[0]["at_deg"]["theta1"] == pytest.approx(want, abs=1e-9)
    assert locks[0]["at_deg"]["theta2"] == pytest.approx(180 - want, abs=1e-9)
    assert r["summary"]["unreachable_steps"] and r["status"] == "fail"
    assert r["summary"]["input_ranges"]["theta1"][1] <= want
    for s in r["steps"]:
        if s["reachable"]:
            assert s["pins"]["P"][0] == pytest.approx(d / 2, abs=1e-9)      # the tip stays on the axis
            assert s["branch"] == 1 and s["det_direct"] > 0


def test_a_five_bar_reports_where_an_arm_lines_up_on_the_way():
    # Both cranks turned together: wherever an arm's det_inverse changes sign the bisected point has its tip a + b or
    # |a - b| from the arm's pivot.
    a1, b1, a2, b2, d = 100, 150, 90, 140, 80
    path = [(150 - 1.5 * i, 30 + 1.0 * i) for i in range(121)]
    r = L.sweep_fivebar(a1, b1, a2, b2, d, path, mode=-1)
    inline = [e for e in r["events"] if e["kind"] == "in-line"]
    assert inline
    for e in inline:
        t1, t2 = DEG(e["at_deg"]["theta1"]), DEG(e["at_deg"]["theta2"])
        p = fx.fivebar_point(a1, b1, a2, b2, d, t1, t2, -1)
        arm = e["arm"]
        pivot, a, b = ((0, 0), a1, b1) if arm == "arm1" else ((d, 0), a2, b2)
        dist = math.dist(p, pivot)
        assert min(abs(dist - (a + b)), abs(dist - abs(a - b))) < 1e-7, e


def test_the_tip_driven_sweep_stops_at_the_edge_of_an_arms_reach():
    # The tip straight up the axis of a symmetric five-bar: it leaves both arms' reach where (d/2)^2 + y^2 = (a + b)^2.
    a, b, d = 100, 150, 80
    path = [(d / 2, 100 + 5 * i) for i in range(40)]
    r = L.sweep_fivebar_tip(a, b, a, b, d, path)
    edge = [e for e in r["events"] if e["kind"] == "in-line"]
    assert len(edge) == 1 and edge[0]["at"]["y"] == pytest.approx(math.sqrt((a + b) ** 2 - (d / 2) ** 2), abs=1e-9)
    assert r["status"] == "fail"
    reached = [s for s in r["steps"] if s["reachable"]]
    assert all(s["working"] == [-1, 1] for s in reached)
    for s in reached:                                  # the cranks put the tip where the path asked
        t1, t2 = DEG(s["angles_deg"]["theta1"]), DEG(s["angles_deg"]["theta2"])
        tips = [fx.fivebar_point(a, b, a, b, d, t1, t2, m) for m in (1, -1)]
        assert min(math.dist(t, (s["tip"]["x"], s["tip"]["y"])) for t in tips if t) < 1e-9


def test_a_foot_path_inside_the_reach_passes_with_its_margins():
    # An ellipse well inside the reach, as a leg's stride: every step closes, no lock or flip, and the margins (the
    # smallest folded angle between each crank and its distal link) are reported.
    path = L.ellipse_path((40, 180), (60, 30), 0, 72)
    r = L.sweep_fivebar_tip(100, 150, 100, 150, 80, path)
    assert r["status"] == "pass" and not r["events"]
    m = r["summary"]["in_line_margin_deg"]
    assert m["arm1"] == pytest.approx(m["arm2"], abs=1e-6) and 30 < m["arm1"] < 89
    assert r["summary"]["min_transmission_deg"] > 40
    json.dumps(r, allow_nan=False)


def test_the_workspace_grid_and_the_sweep_agree():
    a1, b1, a2, b2, d = 100, 120, 100, 120, 80
    w = L.fivebar_workspace(a1, b1, a2, b2, d, (0, 180), (0, 180), samples=(19, 19), cells=True)
    assert w["cells_total"] == 361 and 0 < w["reachable"] < 361
    for cell in w["cells"]:
        p = fx.fivebar_point(a1, b1, a2, b2, d, DEG(cell["theta1"]), DEG(cell["theta2"]), 1)
        assert (p is not None) == cell["reachable"]
        if p is not None:
            assert cell["tip"] == pytest.approx(list(p))
    best = min((c for c in w["cells"] if c["reachable"]), key=lambda c: c["transmission_deg"])
    assert w["min_transmission_deg"] == best["transmission_deg"]
    json.dumps(w, allow_nan=False)


# ----------------------------------------------------------------------------- the CAD dyad solver

def test_the_cad_dyad_solver_never_flips_a_branch_along_a_smooth_path():
    ref = {"A": (-75.0, 0.0), "B": (75.0, 0.0)}
    ref["C"] = (-75 - 150 * math.cos(DEG(60)), -150 * math.sin(DEG(60)))
    ref["D"] = (75 + 150 * math.cos(DEG(60)), -150 * math.sin(DEG(60)))
    h = math.sqrt(250 ** 2 - (ref["D"][0] - ref["C"][0]) ** 2 / 4)
    ref["E"] = (0.0, ref["C"][1] - h)
    link = L.Linkage(ground={"A": ref["A"], "B": ref["B"]},
                     links={"crank_a": ("A", "C"), "crank_b": ("B", "D"), "link_c": ("C", "E"), "link_d": ("D", "E")},
                     reference=ref, solve=[("C", "A", "E"), ("D", "B", "E")])
    home = link.sides(ref)
    poses = link.sweep("E", L.ellipse_path((ref["E"][0], ref["E"][1] + 30), (60, 30), -90, 36))
    assert all(link.sides(p) == home for p in poses)
    # and it is the same five-bar the sweeps solve: the cranks it finds put the tip where it is
    for p in poses:
        t1 = math.atan2(p["C"][1] - ref["A"][1], p["C"][0] - ref["A"][0])
        t2 = math.atan2(p["D"][1] - ref["B"][1], p["D"][0] - ref["B"][0])
        tips = [fx.fivebar_point(150, 250, 150, 250, 150, t1, t2, m) for m in (1, -1)]
        assert min(math.dist((t[0] - 75, t[1]), p["E"]) for t in tips if t) < 1e-9


def test_the_old_import_path_still_works():
    from cadagent.publish.anim import linkage
    assert linkage.Linkage is L.Linkage and linkage.circles is L.circles


# ----------------------------------------------------------------------------- the docs figure

def _figures():
    import importlib.util
    spec = importlib.util.spec_from_file_location("linkage_figures", ROOT / "tools" / "linkage_figures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_figure_matches_its_generator_and_is_safe_to_embed():
    from cadagent.publish.anim import svg as S
    lf = _figures()
    assert lf.main(["--check"]) == 0, "run PYTHONPATH=src python3 tools/linkage_figures.py"
    content = (ROOT / "docs" / "img" / "linkages" / "fivebar.svg").read_text(encoding="utf-8")
    assert S.problems(content) == []


def test_the_figure_quotes_the_closed_form_lock_and_a_passing_stride():
    lf = _figures()
    stride, sym, grid, lock = lf.solve()
    # symmetric, the leg hanging (theta1 below the ground link): the knees 2b apart
    want = -math.degrees(math.acos((lf.D - 2 * lf.B1) / (2 * lf.A1)))
    assert lock["at_deg"]["theta1"] == pytest.approx(want, abs=1e-9)
    assert stride["status"] == "pass" and stride["summary"]["flips"] == 0
    # knees out all the way round with the foot below them, on one assembly, which the dash-dot links are the other of
    assert {tuple(s["working"]) for s in stride["steps"]} == {lf.WORKING} == {(1, -1)}
    assert {s["assembly"] for s in stride["steps"]} == {lf.MODE} == {-1}
    assert max(s["tip"]["y"] for s in stride["steps"]) < 0                    # the foot below the hips
    content = (ROOT / "docs" / "img" / "linkages" / "fivebar.svg").read_text(encoding="utf-8")
    assert f"θ1 = {lf.deg(want)}" in content and f"{stride['summary']['min_transmission_deg']:.1f}°" in content
    assert f"{grid['reachable']} of {grid['cells_total']}" in content


@pytest.mark.parametrize("step_mm", [2.0, 5.0, 10.0])
def test_a_tip_path_that_crosses_a_lock_between_samples_fails_whatever_the_step(step_mm):
    # Straight down the symmetric five-bar's middle, the tip crosses two locks (the distal links in line). Whether or
    # not a sample lands within lock_deg of them, the bisected crossings fail the sweep.
    path = [(40.0, 197.5 - step_mm * i) for i in range(int(380 / step_mm))]
    r = L.sweep_fivebar_tip(100, 120, 100, 120, 80, path)
    crossed = r["summary"]["crossed_between_steps"]
    assert [c["kind"] for c in crossed] == ["lock", "lock"] and r["status"] == "fail"
    assert any("between samples" in p for p in r["problems"])
    locks = [e["at"]["y"] for e in r["events"] if e["kind"] == "lock"]
    # By symmetry: stretched, the knees are level with the tip and b either side of x = d/2, so a knee is d/2 - b from
    # its hip and the tip at y = sqrt(a^2 - (b - d/2)^2) = 60; folded, both knees meet over x = d/2, at
    # sqrt(a^2 - (d/2)^2), and the tip hangs b below them, at -28.35.
    assert locks == pytest.approx([math.sqrt(100 ** 2 - (120 - 40) ** 2), math.sqrt(100 ** 2 - 40 ** 2) - 120],
                                  abs=1e-9)
