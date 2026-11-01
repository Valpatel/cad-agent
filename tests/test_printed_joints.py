"""cadagent.mechanical.printed_joints: the load-bearing pitfalls of printed parts, each with golden vectors worked by
hand, a planted defect that the check catches, and the case it lets through."""
from __future__ import annotations

import math

import numpy as np
import pytest

from cadagent import formulas as fx
from cadagent.mechanical import printed_joints as pj
from cadagent.mechanical.compliant.allowables import PRINTED
from cadagent.simulation.fea import layer_modes

PLA = "pla-bambu-basic"            # strengths 35 MPa in the layer plane, 31 MPa across (Bambu PLA Basic V3.0)


def rows(result):
    return {r["check"]: r for r in result["rows"]}


# ----------------------------------------------------------------------------- pin through an eye

def test_eye_stresses_golden():
    # P = 500 N, D = 5, t = 8, e = 10, w = 16: bearing 500 / 40, shear-out 500 / (2 * 8 * 7.5), net 500 / (11 * 8)
    s = pj.eye_stresses(500, 5, 8, 10, 16)
    assert s["bearing"] == pytest.approx(12.5)
    assert s["shear-out"] == pytest.approx(4.166666666666667)
    assert s["net tension"] == pytest.approx(5.681818181818182)


@pytest.mark.parametrize("bad", [dict(edge_mm=2.5), dict(width_mm=5), dict(hole_mm=0), dict(load_n=-1)])
def test_eye_stresses_refuse_a_broken_eye(bad):
    args = dict(load_n=500, hole_mm=5, thickness_mm=8, edge_mm=10, width_mm=16) | bad
    with pytest.raises(ValueError):
        pj.eye_stresses(**args)


def test_flat_eye_is_judged_in_the_layer_plane():
    r = pj.pin_eye(PLA, 500, 5, 8, 10, 16)
    by = rows(r)
    assert PRINTED[PLA].strength("along") == 35 and PRINTED[PLA].strength("across") == 31
    assert by["bearing"]["limit"]["factor"] == pytest.approx(35 / 12.5, abs=1e-3)              # 2.8: a pass at 2
    assert by["shear-out"]["limit"]["factor"] == pytest.approx(35 / (math.sqrt(3) * 500 / 120), abs=1e-3)
    assert by["net tension"]["limit"]["factor"] == pytest.approx(35 / (500 / 88), abs=1e-3)
    assert {by[k]["verdict"] for k in ("bearing", "shear-out", "net tension")} == {"pass"}
    assert by["layers"]["verdict"] == "pass"
    assert r["margin"] == pytest.approx(2.8)
    # e/D 2 and w/D 3.2 are short of ASTM D5961's 3 and 6: a sudden failure is likely, so the check warns
    assert by["failure mode"]["verdict"] == "warn" and r["verdict"] == "warn"


def test_eye_on_its_side_puts_shear_out_on_the_layers():
    # pin along Y, load along X, layers normal to Z: the shear-out planes (normal Z) are layer planes, so the shear
    # is judged against the across-layer allowable over sqrt 3, and the layers row warns
    r = pj.pin_eye(PLA, 500, 5, 8, 10, 16, pin_axis=(0, 1, 0))
    by = rows(r)
    assert by["shear-out"]["limit"]["factor"] == pytest.approx(31 / (math.sqrt(3) * 500 / 120), abs=1e-3)
    assert "across the layers" in by["shear-out"]["detail"]
    assert by["layers"]["verdict"] == "warn" and "shear-out planes" in by["layers"]["detail"]
    # load along the build direction instead: the net section is pulled across the layers
    r = pj.pin_eye(PLA, 500, 5, 8, 10, 16, pin_axis=(0, 1, 0), load_dir=(0, 0, 1))
    assert rows(r)["net tension"]["limit"]["factor"] == pytest.approx(31 / (500 / 88), abs=1e-3)
    assert "net section across the layers" in rows(r)["layers"]["detail"]


def test_the_eye_uses_the_fea_layer_criterion():
    # the same tensor through the FEA layer check gives the same utilisation
    u, v = np.array([1.0, 0, 0]), np.array([0, 0, 1.0])
    tau = 500 / 120
    modes = layer_modes(tau * (np.outer(u, v) + np.outer(v, u)), (0, 0, 1), 35, 31)
    r = pj.pin_eye(PLA, 500, 5, 8, 10, 16, pin_axis=(0, 1, 0))
    assert rows(r)["shear-out"]["limit"]["factor"] == pytest.approx(1 / float(max(modes.values())), abs=1e-3)


def test_planted_overload_fails_and_the_bushing_fixes_bearing_but_costs_edge():
    # 1500 N on a 5 mm pin in an 8 mm PLA eye: 37.5 MPa bearing, over 35 MPa: fail
    bare = pj.pin_eye(PLA, 1500, 5, 8, 15, 30)
    assert rows(bare)["bearing"]["verdict"] == "fail" and bare["verdict"] == "fail"
    bushed = pj.pin_eye(PLA, 1500, 5, 8, 15, 30, bushing_mm=10)
    by = rows(bushed)
    assert by["bearing"]["limit"]["factor"] == pytest.approx(35 / 18.75, abs=1e-3)      # 18.75 MPa: a warn
    assert by["bearing"]["verdict"] == "warn"
    cmp = bushed["compare"]
    assert cmp["bearing"]["bushed_factor"] > cmp["bearing"]["bare_factor"]
    assert cmp["shear-out"]["bushed_factor"] < cmp["shear-out"]["bare_factor"]        # a larger hole, less margin
    assert "less plastic for shear-out and net tension" in by["bushing"]["detail"]


def test_bearing_mode_geometry_passes_and_a_turning_pin_needs_a_bushing():
    r = pj.pin_eye(PLA, 200, 5, 8, 15, 30, pivots=True)
    assert rows(r)["failure mode"]["verdict"] == "pass"                                # e/D 3, w/D 6
    assert rows(r)["pivot"]["verdict"] == "warn" and r["verdict"] == "warn"
    r = pj.pin_eye(PLA, 200, 5, 8, 24, 48, bushing_mm=8, pivots=True)
    assert rows(r)["pivot"]["verdict"] == "pass" and r["verdict"] == "pass"


def test_bearing_mode_ratios_follow_the_filament_tested():
    # Khosravani 2023, Table 2: PLA failed in bearing from e/D 3, w/D 6; ABS cleaved there and needed 4.5 and 9
    assert pj.bearing_mode_ratios(PLA)[0] == {"edge_over_d": 3.0, "width_over_d": 6.0}
    assert pj.bearing_mode_ratios("asa-bambu")[0] == {"edge_over_d": 4.5, "width_over_d": 9.0}
    ratios, basis = pj.bearing_mode_ratios("petg-bambu-basic")
    assert ratios == {"edge_over_d": 4.5, "width_over_d": 9.0} and "no printed test" in basis
    # the planted defect: an ASA eye at PLA's ratios warns; at ABS's it passes
    r = pj.pin_eye("asa-bambu", 200, 5, 8, 15, 30)
    assert rows(r)["failure mode"]["verdict"] == "warn" and "ABS" in rows(r)["failure mode"]["detail"]
    assert rows(pj.pin_eye("asa-bambu", 200, 5, 8, 22.5, 45))["failure mode"]["verdict"] == "pass"


@pytest.mark.parametrize("bad", [dict(material="pla"), dict(load_dir=(0, 0, 1)), dict(bushing_mm=4),
                                 dict(safety=0.5), dict(build=(0, 0, 0))])
def test_pin_eye_refuses(bad):
    args = dict(material=PLA, load_n=500, pin_mm=5, thickness_mm=8, edge_mm=10, width_mm=16) | bad
    with pytest.raises(ValueError):
        pj.pin_eye(**args)


# ----------------------------------------------------------------------------- boss or rib root

def test_sections_golden():
    t = pj.tube(12, 5.5)
    assert t["area_mm2"] == pytest.approx(math.pi / 4 * (144 - 30.25))
    assert t["second_moment_mm4"] == pytest.approx(math.pi / 64 * (12 ** 4 - 5.5 ** 4))
    assert pj.tube(10)["shear_factor"] == pytest.approx(4 / 3)                           # solid round: 4 V / 3 A
    assert pj.tube(10, 9.999)["shear_factor"] == pytest.approx(2.0, abs=1e-3)            # thin tube: 2 V / A
    r = pj.rect(3, 10)
    assert (r["area_mm2"], r["second_moment_mm4"], r["c_mm"], r["shear_factor"]) == (30, 22.5, 1.5, 1.5)


def test_through_bolt_preload_band_is_shigleys():
    b = pj.through_bolt(5, 0.8, torque_nm=3)
    assert b["preload_n"]["low"] == pytest.approx(fx.preload_from_torque(3, 5e-3, 0.30))      # 2000 N
    assert b["preload_n"]["high"] == pytest.approx(fx.preload_from_torque(3, 5e-3, 0.18))     # 3333 N
    assert pj.through_bolt(5, 0.8, preload_n=900)["preload_n"] == {"low": 900, "high": 900}
    with pytest.raises(ValueError):
        pj.through_bolt(5, 0.8)


def test_upright_boss_peels_across_the_layers():
    # 100 N at 20 mm on a 12 / 5.5 mm PLA boss: M c / I = 2000 * 6 / 972.96 = 12.33 MPa across the layers (31 MPa)
    sec = pj.tube(12, 5.5)
    r = pj.root_peel(PLA, 100, 20, sec)
    bend = 2000 * 6 / sec["second_moment_mm4"]
    assert r["states"]["no bolt"]["bending_mpa"] == pytest.approx(bend)
    assert r["margin"] == pytest.approx(31 / bend)
    assert r["verdict"] == "pass" and "peels first" in rows(r)["orientation"]["detail"]
    assert r["advice"]["preload_to_close_n"] == pytest.approx(bend * sec["area_mm2"])     # 1102 N closes the seam
    # lying in the layer plane, the same bending runs along the layers (35 MPa)
    lying = pj.root_peel(PLA, 100, 20, sec, axis=(1, 0, 0), load_dir=(0, 0, 1))
    assert lying["margin"] == pytest.approx(35 / bend)


def test_through_bolt_closes_the_seam_but_too_much_crushes_the_column():
    sec = pj.tube(16, 5.5)
    r = pj.root_peel(PLA, 100, 20, sec, bolt=pj.through_bolt(5, 0.8, torque_nm=3))
    by = rows(r)
    kept = 0.5 * 2000
    assert by["layers closed"]["value"] == pytest.approx(kept) and by["layers closed"]["verdict"] == "pass"
    assert r["states"]["kept"]["layer_tension_mpa"] == 0.0
    # the most preload (3333 N) plus the bending squeezes the compression side: judged in the layer plane at 35 MPa
    squeeze = 3333.3333333333335 / sec["area_mm2"] + r["states"]["no bolt"]["bending_mpa"]
    assert r["states"]["tightened"]["factor"] == pytest.approx(35 / squeeze)
    assert r["verdict"] == "warn"
    lo, hi = r["advice"]["torque_window_nm"]
    assert lo == pytest.approx(fx.torque_for_preload(r["advice"]["preload_to_close_n"] / 0.5, 5e-3, 0.30))
    assert lo > hi and "no torque does both" in by["layers closed"]["detail"]


def test_planted_slack_rod_leaves_the_seam_opening():
    r = pj.root_peel(PLA, 100, 20, pj.tube(12, 5.5), bolt=pj.through_bolt(5, 0.8, preload_n=1200))
    assert rows(r)["layers closed"]["verdict"] == "warn"                    # 600 N kept, 1102 N needed
    assert "opens each time" in rows(r)["layers closed"]["detail"]


def test_a_boss_lying_in_the_layer_plane_has_no_seam_to_close():
    # bending along the layers: the rod's preload has no seam to hold closed, whatever it is
    r = pj.root_peel(PLA, 100, 20, pj.tube(12, 5.5), axis=(1, 0, 0), load_dir=(0, 0, 1),
                     bolt=pj.through_bolt(5, 0.8, preload_n=1200))
    assert rows(r)["layers closed"]["verdict"] == "pass" and "no layer seam" in rows(r)["layers closed"]["detail"]
    assert "lying in the layer plane" in rows(r)["orientation"]["detail"]
    # and the advice sizes no rod against a seam that is not there: only the crush end of the window is left
    assert r["advice"]["seam"] is False and r["advice"]["preload_to_close_n"] is None
    assert r["advice"]["preload_window_n"][0] is None and r["advice"]["preload_window_n"][1] > 0
    assert r["advice"]["torque_window_nm"][0] is None and r["advice"]["torque_window_nm"][1] > 0
    # the same boss upright, the same 600 N kept: below the 1102 N that closes the seam
    upright = pj.root_peel(PLA, 100, 20, pj.tube(12, 5.5), bolt=pj.through_bolt(5, 0.8, preload_n=1200))
    assert rows(upright)["layers closed"]["verdict"] == "warn" and upright["advice"]["seam"] is True
    assert upright["advice"]["preload_to_close_n"] == pytest.approx(1102, abs=1)


@pytest.mark.parametrize("bad", [dict(section={"shape": "star"}), dict(load_dir=(0, 0, 1)), dict(retained=0),
                                 dict(section=pj.rect(3, 10), bolt=pj.through_bolt(3, 0.5, preload_n=100)),
                                 dict(section=pj.tube(12, 4), bolt=pj.through_bolt(5, 0.8, preload_n=100))])
def test_root_peel_refuses(bad):
    args = dict(material=PLA, side_load_n=100, height_mm=20, section=pj.tube(12, 5.5)) | bad
    with pytest.raises(ValueError):
        pj.root_peel(**args)


# ----------------------------------------------------------------------------- backing out

def test_threadlocker_on_a_printed_thread_fails():
    r = pj.thread_locking("printed", "anaerobic")
    assert r["verdict"] == "fail" and "stress-crack" in rows(r)["locking"]["detail"]
    assert rows(pj.thread_locking("insert", "anaerobic"))["locking"]["verdict"] == "warn"
    assert rows(pj.thread_locking("nut", "anaerobic", plastic_in_clamp=False))["locking"]["verdict"] == "pass"


def test_spring_washers_and_no_locking_warn_under_vibration():
    assert rows(pj.thread_locking("printed", "spring-washer"))["locking"]["verdict"] == "warn"
    assert rows(pj.thread_locking("insert", "none"))["locking"]["verdict"] == "warn"
    assert rows(pj.thread_locking("insert", "none", vibration=False))["locking"]["verdict"] == "pass"
    assert rows(pj.thread_locking("nut", "all-metal-locknut"))["locking"]["verdict"] == "pass"
    with pytest.raises(ValueError):
        pj.thread_locking("printed", "nylon-insert-nut")


def test_a_jam_nut_warns_under_vibration():
    # NASA RP-1228 p. 7: a jam nut is too unpredictable to be reliable; a locknut is the more practical choice
    r = pj.thread_locking("nut", "jam-nut")
    assert rows(r)["locking"]["verdict"] == "warn" and "unpredictable" in rows(r)["locking"]["detail"]
    assert rows(pj.thread_locking("nut", "jam-nut", vibration=False))["locking"]["verdict"] == "pass"
    assert rows(pj.thread_locking("nut", "safety-wire"))["locking"]["verdict"] == "pass"


def test_thread_locking_refuses_a_friction_it_would_ignore_and_a_safety_under_one():
    with pytest.raises(ValueError, match="metal faces"):
        pj.thread_locking("nut", "all-metal-locknut", transverse_load_n=40, preload_n=500, friction=0.5)
    with pytest.raises(ValueError, match="safety"):
        pj.thread_locking("nut", "all-metal-locknut", safety=0.5)


def test_transverse_slip_golden():
    # 500 N tightened, plastic in the clamp: 250 N kept, 0.20 friction: 50 N sideways
    r = pj.thread_locking("nut", "all-metal-locknut", transverse_load_n=40, preload_n=500)
    assert r["margin"] == pytest.approx(50 / 40)
    assert rows(r)["slip"]["verdict"] == "warn"
    r = pj.thread_locking("nut", "all-metal-locknut", transverse_load_n=60, preload_n=500)
    assert rows(r)["slip"]["verdict"] == "fail" and "carry the side load on a pin" in rows(r)["slip"]["detail"]
    # metal faces (a sleeve through the plastic), two interfaces, friction given: 2 x 0.15 x 500 = 150 N
    r = pj.thread_locking("nut", "all-metal-locknut", transverse_load_n=60, preload_n=500, plastic_in_clamp=False,
                          friction=0.15, interfaces=2)
    assert r["margin"] == pytest.approx(150 / 60) and r["verdict"] == "pass"
    with pytest.raises(ValueError):
        pj.thread_locking("nut", "jam-nut", transverse_load_n=60, preload_n=500, plastic_in_clamp=False)


def test_every_row_cites_a_source_and_every_check_states_limits():
    results = [pj.pin_eye(PLA, 500, 5, 8, 10, 16, bushing_mm=8, pivots=True, pin_axis=(0, 1, 0)),
               pj.root_peel(PLA, 100, 20, pj.tube(12, 5.5), bolt=pj.through_bolt(5, 0.8, torque_nm=3)),
               pj.thread_locking("printed", "none", transverse_load_n=10, preload_n=500)]
    for r in results:
        assert r["limits"] and r["verdict"] in pj.VERDICTS
        for row in r["rows"]:
            assert row["source"] and row["verdict"] in pj.VERDICTS, row
    assert set(pj.sources()) == set(pj.SRC)


def test_figures_are_current():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "tools" / "printed_joint_figures.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
