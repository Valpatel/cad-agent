"""cadagent.mechanical.rivets: the listed rivets and the riveted lap-joint check, against the sources' own numbers
[ref:pop-rivet-catalog] [ref:mil-hdbk-5j] [ref:faa-ac-43-13-1b] [ref:nasa-1228] [ref:mil-std-889c]."""
import pytest

from cadagent.mechanical import rivets as R

IN, LBF = 25.4, 4.4482216152605
T063 = 0.063 * IN                 # SendCutSend's ALU-063, held to +/- 0.004 in
TOL = 0.004 * IN


def joint(rivet="pop-AD43", t=T063, edge=2 * 3.175, pitch=3 * 3.175, **kw):
    return R.check_joint(rivet, [("5052-h32", t), ("5052-h32", t)], edge_mm=edge, pitch_mm=pitch, **kw)


def by(res, name):
    return next(c for c in res["checks"] if c["check"] == name)


def test_the_rivets_are_the_catalogues_numbers():
    ad43 = R.RIVETS["pop-AD43"]                         # POP p. 14: 1/8 in, hole .129-.133, grip .126-.187, 155/235 lbf
    assert (ad43.diameter_in, ad43.hole_in, ad43.grip_in, ad43.shear_lbf, ad43.tensile_lbf) == \
        (0.125, (0.129, 0.133), (0.126, 0.187), 155, 235)
    assert R.RIVETS["mcmaster-97447A015"].shear_lbf == 120 and R.RIVETS["mcmaster-97447A015"].rating == "listed"
    for r in R.RIVETS.values():
        assert r.source in R.SRC and r.hole_in[0] < r.hole_in[1] and r.grip_in[0] < r.grip_in[1]
        assert r.hole_in[0] > r.diameter_in and r.body in R.FAMILIES


def test_worked_example_two_1_6_mm_5052_sheets():
    # research/sheet-metal-joining.md section 8: hole 0.1285 in, 2D edge, 3D pitch, MIL-HDBK-5J 5052-H32 (Ftu 31 ksi,
    # Fbru 50 / 65 ksi at e/D 1.5 / 2.0): rivet 155 lbf, tearing 481 lbf, solid 732 lbf, efficiency 0.21. e/D is on the
    # hole: 0.25 / 0.130 = 1.923, so Fbru = 50 + 15 x 0.423 / 0.5 = 62.69 ksi (MIL-HDBK-5J 1.4.7.1: linear between).
    s = R.check_joint("pop-AD43", [("5052-h32", T063), ("5052-h32", T063)], edge_mm=6.35, pitch_mm=9.525,
                      hole_mm=0.130 * IN)
    one = s["per_sheet"][0]
    assert one["e_over_d"] == pytest.approx(0.25 / 0.130, abs=1e-4) and s["mode"] == "shear"
    assert one["fbru_ksi"] == pytest.approx(50 + 15 * (0.25 / 0.130 - 1.5) / 0.5, abs=1e-3)
    assert one["bearing_n"] / LBF == pytest.approx(one["fbru_ksi"] * 1000 * 0.130 * 0.063, rel=1e-4)
    assert one["shear_n"] / LBF == pytest.approx(155, abs=0.01)
    import cadagent.formulas as fx
    ksi = R.KSI * 1e6
    j = fx.lap_joint(0.1285 * 0.0254, 0.063 * 0.0254, 0.375 * 0.0254, 31 * ksi, None, 65 * ksi, rivet_shear=155 * LBF)
    assert (j["bearing_n"] / LBF, j["tearing_n"] / LBF, j["solid_n"] / LBF) == pytest.approx((526.2, 481.4, 732.4),
                                                                                                 abs=0.1)
    assert j["efficiency"] == pytest.approx(0.2116, abs=1e-4)
    assert s["efficiency"] == pytest.approx(155 / 732.4, abs=1e-3)


def test_two_1_6_mm_sheets_straddle_the_grip_codes():
    # 2 x 0.063 = 0.126 in, AD43's first value; at +/- 0.004 in each, 0.118-0.134 in spans AD42 and AD43.
    assert by(joint(), "grip")["verdict"] == "pass"
    g = by(joint(thickness_tol_mm=TOL), "grip")
    assert g["verdict"] == "warn" and "pop-AD41-43-mg" in g["detail"]
    assert by(joint("pop-AD42", thickness_tol_mm=TOL), "grip")["verdict"] == "fail"
    assert [x["key"] for x in R.rivets_for(3.175, 0.118 * IN, 0.134 * IN)] == ["pop-AD41-43-mg"]


@pytest.mark.parametrize("edge_d,verdict", [(2.0, "pass"), (1.75, "warn"), (1.5, "warn"), (1.4, "fail")])
def test_edge_distance_2d_full_1_5d_floor(edge_d, verdict):
    c = by(joint(edge=edge_d * 3.175), "edge")
    assert c["verdict"] == verdict and c["rule"] == "sm-rivet-edge-pop, sm-rivet-edge-min-nasa"


def test_below_e_over_d_1_5_the_joint_has_no_bearing_value():
    s = joint(edge=1.4 * 3.175, load_per_pitch_n=100)
    assert s["strength_n"] is None and by(s, "strength")["verdict"] == "fail"
    s = joint(edge=1.7 * 3.175)                        # e/D on the hole (0.131 in): 1.622, linear between 50 and 65 ksi
    eod = 1.7 * 3.175 / (0.131 * IN)
    assert s["e_over_d"] == pytest.approx(eod, abs=1e-4)
    assert s["per_sheet"][0]["fbru_ksi"] == pytest.approx(50 + 15 * (eod - 1.5) / 0.5, abs=1e-3)
    assert joint(edge=1.5 * 3.175)["strength_n"] is None    # 2D-style multiples are of the rivet; e/D on the hole is 1.45


def test_rows_are_spaced_4d_too():
    assert by(joint(pitch=4 * 3.175, rows=2), "pitch")["rule"] == "sm-rivet-pitch-faa, sm-rivet-pitch-double-faa"
    assert by(joint(pitch=4 * 3.175, rows=2), "row spacing")["verdict"] == "warn"         # not given
    assert by(joint(pitch=4 * 3.175, rows=2, row_spacing_mm=4 * 3.175), "row spacing")["verdict"] == "pass"
    assert by(joint(pitch=4 * 3.175, rows=2, row_spacing_mm=3 * 3.175), "row spacing")["verdict"] == "warn"
    assert not [c for c in joint()["checks"] if c["check"] == "row spacing"]


def test_t_over_d_between_0_18_and_0_25_warns_for_blind_rivets():
    t = 0.22 * 0.131 * IN                                    # t/D 0.22 on the hole
    s = R.check_joint("pop-AD41-43-mg", [("5052-h32", t), ("5052-h32", 1.6)], edge_mm=6.35, pitch_mm=9.525)
    c = by(s, "sheet 1 t/D")
    assert c["verdict"] == "warn" and "8.1.3" in c["detail"]


def test_a_large_tolerance_gives_a_verdict_not_an_error():
    assert by(joint(thickness_tol_mm=1.0), "grip")["verdict"] in ("warn", "fail")


@pytest.mark.parametrize("pitch_d,rows,verdict", [(3, 1, "pass"), (2.8, 1, "fail"), (3, 2, "warn"), (4, 2, "pass")])
def test_pitch_3d_one_row_4d_for_more(pitch_d, rows, verdict):
    assert by(joint(pitch=pitch_d * 3.175, rows=rows), "pitch")["verdict"] == verdict


def test_hole_inside_the_makers_range():
    assert by(joint(hole_mm=0.131 * IN), "hole")["verdict"] == "pass"
    assert "oversize" in by(joint(hole_mm=0.140 * IN), "hole")["detail"]
    assert by(joint(hole_mm=0.1285 * IN), "hole")["verdict"] == "fail"        # MIL's nominal is under POP's range
    assert all(c["check"] != "hole" for c in joint()["checks"])


def test_thin_sheet():
    s = R.check_joint("pop-AD41", [("5052-h32", 0.5), ("5052-h32", 0.5)], edge_mm=6.35, pitch_mm=9.525)
    assert by(s, "sheet 1 t/D")["verdict"] == "warn"               # 0.5 / 3.175 = 0.157 < 0.18
    assert by(s, "sheet 2 thickness")["verdict"] == "fail"         # the formed head's sheet, under POP's 0.020 in
    assert not [c for c in s["checks"] if c["check"] == "sheet 1 thickness"]   # the factory head's side: no floor
    assert s["verdict"] == "fail"


def test_metals():
    s = R.check_joint("mcmaster-97525A415", [("5052-h32", T063), ("5052-h32", T063)], edge_mm=6.35, pitch_mm=9.525)
    assert by(s, "sheet 1 metals")["verdict"] == "warn" and "5.2a" in by(s, "sheet 1 metals")["detail"]
    s = R.check_joint("pop-AD43", [("304-annealed", T063), ("304-annealed", T063)], edge_mm=6.35, pitch_mm=9.525)
    assert "less noble" in by(s, "sheet 1 metals")["detail"]
    s = R.check_joint("mcmaster-97525A415", [("304-annealed", T063), ("304-annealed", T063)], edge_mm=6.35,
                      pitch_mm=9.525)
    assert by(s, "sheet 1 metals")["verdict"] == "pass"
    s = R.check_joint("pop-AD41-43-mg", [("5052-h32", T063), ("5052-h32", T063)], edge_mm=6.35, pitch_mm=9.525)
    assert "steel mandrel head" in by(s, "sheet 1 metals")["detail"]


def test_a_more_noble_rivet_corrodes_the_sheet():
    sheet = R.SHEETS["5052-h32"]
    v, why = R._galvanic("steel", sheet)
    assert v == "warn" and "the sheet is the less noble" in why


def test_load_against_strength():
    assert by(joint(load_per_pitch_n=400), "strength")["verdict"] == "pass"         # 689 N rated shear per pitch
    assert by(joint(load_per_pitch_n=400, factor=2.0), "strength")["verdict"] == "fail"


@pytest.mark.parametrize("kw", [dict(rivet="nope"), dict(edge=0), dict(pitch=-1), dict(rows=0), dict(factor=0),
                                dict(thickness_tol_mm=-0.1)])
def test_bad_inputs(kw):
    with pytest.raises(ValueError):
        joint(**kw)
    with pytest.raises(ValueError):
        R.check_joint("pop-AD43", [("5052-h32", 1.6)], edge_mm=6.35, pitch_mm=9.525)
