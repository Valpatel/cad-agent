"""The threaded-insert figures are drawn from cadagent.mechanical.inserts, and stay in step with it."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_committed_diagrams_match_the_module():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "insert_figures.py"), "--check"], capture_output=True,
                       text=True, env=ENV)
    assert r.returncode == 0, r.stdout + r.stderr


def test_committed_coupon_figure_matches_the_cad():
    pytest.importorskip("cadquery")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "insert_coupons.py"), "--figure", "--check"],
                       capture_output=True, text=True, env=ENV)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_figure_is_on_the_page_and_themed():
    page = (ROOT / "docs" / "inserts.md").read_text()
    for name in ("section", "clamp-paths", "limiters", "calibration", "coupons"):
        svg = (ROOT / "docs" / "img" / "inserts" / f"{name}.svg").read_text()
        assert f"img/inserts/{name}.svg" in page
        assert "prefers-color-scheme:dark" in svg and "<title" in svg


def test_the_pages_numbers_are_what_the_module_computes():
    from cadagent.mechanical import inserts as I
    page = (ROOT / "docs" / "inserts.md").read_text()
    m3 = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", boss_outside_mm=9.5)
    lid = I.check_joint(**m3, head_mm=7.0, clearance_mm=3.4, clamped={"thickness_mm": 4.0})
    assert f"at most {lid['torque']['allowed_nm']:.2f} N m ({lid['torque']['governed_by'].replace('_', ' ')})" in page
    assert f"{lid['torque']['allowed_nm']:.2f}, '{lid['torque']['governed_by']}'" in page
    assert f"above: {lid['torque']['allowed_nm']:.2f} N·m)" in page
    pull = lid["capacity"]["pull_out"]
    assert f"low {pull['low']:.0f}, mid {pull['mid']:.0f}, high {pull['high']:.0f} N" in page
    bracket = I.check_clamp("M4", "pla-bambu-basic", 6.0, head_mm=7.0, clearance_mm=4.5)
    assert f"at most {bracket['torque']['allowed_nm']:.2f} N m (head bearing)" in page
    flush = I.check_joint(**m3, clamped={"material": "metal"})
    sunk = I.check_joint(**m3, recess_mm=0.2, clamped={"material": "metal"})
    assert f"**{flush['torque']['allowed_nm']:.2f} N·m**, set by the insert's end face" in page
    assert flush["torque"]["governed_by"] == "insert_face"
    assert f"only **{sunk['torque']['allowed_nm']:.2f} N·m**" in page and sunk["clamp"]["path"] == "jack-out"
    lim = I.check_joint("mcmaster-94459A775", "petg-bambu-basic", boss_outside_mm=15.0, limiter_key="spirol-cl6000-m5",
                        clamped={"thickness_mm": 6.1, "tolerance_mm": 0.05, "outside_mm": 18.0}, limiter_length_mm=6.0)
    rows = {c["check"]: c for c in lim["checks"]}
    assert f"{lim['torque']['preload_caps_n']['insert_face']:.0f} N" in page
    assert "(10.00 mm^2)" in rows["insert face"]["detail"] and "10.00 mm²" in page
    seat = re.search(r"\((\d+) as SPIROL's column, (\d+) as Shigley's cone\)", rows["seating force"]["detail"])
    assert f"{seat[1]} to {seat[2]} N" in page and rows["seating force"]["verdict"] == "fail"
    knee = I.check_clamp("M10", "pa6-cf20-polymaker-wet", 40.0, head_mm=20.0, clearance_mm=12.0, torque_nm=20.0,
                         limiter={"outside_mm": 18.0, "bore_mm": 12.0}, limiter_length_mm=39.8)
    detail = {c["check"]: c for c in knee["checks"]}["seating force"]["detail"]
    seat = re.search(r"\((\d+) as SPIROL's column, (\d+) as Shigley's cone\)", detail)
    assert f"**{seat[1]} N** as a column and **{seat[2]} N** as a cone" in page
    ring = re.search(r"bears (\d+) MPa", detail)[1]
    assert f"The ring then bears {ring} MPa" in page
    cal = I.calibration()
    pla, petg, r = cal["pull"]["pla"], cal["pull"]["petg"], cal["torque_ratio"]
    assert f"c from {pla['low']:.2f} to {pla['high']:.2f}" in page
    assert f"c from {petg['low']:.2f} to {petg['high']:.2f}" in page and f"{pla['cells']} results" in page
    assert f"r from {r['low']:.2f}" in page and f"to {r['high']:.2f}" in page and f"gives {r['printed'][0]:.2f}" in page
    # the strain at which printed PETG Basic and PLA Basic reach their measured compressive strength
    for mat in ("petg-bambu-basic", "pla-bambu-basic"):
        strain = I.bearing_strength(mat) / (I.PRINTED[mat].secant_upper_bound("across") * 1e6)
        assert f"**{strain * 100:.1f} %**" in page
    # the alt text of each figure is its title
    for name in ("section", "clamp-paths", "limiters", "calibration", "coupons"):
        svg = (ROOT / "docs" / "img" / "inserts" / f"{name}.svg").read_text()
        title = re.search(r"<title[^>]*>([^<]*)", svg)[1]
        assert f'alt="{title}"' in page, name
    # the worked example's two plastic-under-the-head failures, with their inputs
    wheel = I.check_clamp("M6", "pa6-cf20-polymaker-wet", 20.8, head_mm=10.0, clearance_mm=6.6, torque_nm=8.0)
    washer = I.check_clamp("M6", "pa6-cf20-polymaker-wet", 20.8, head_mm=11.0, clearance_mm=6.6, torque_nm=8.0)
    pod = I.check_joint("mcmaster-94459A160", "petg-bambu-basic", hole_mm=5.6, hole_depth_mm=9.1,
                        boss_outside_mm=10.0, torque_nm=2.3)
    head = {name: {c["check"]: c for c in r["checks"]}["head bearing"] for name, r in
            (("wheel", wheel), ("washer", washer), ("pod", pod))}
    assert f"puts {head['wheel']['value']:.0f} MPa on wet PA6-CF under its 10 mm head" in page
    assert f"({head['washer']['value']:.0f} MPa with an\n  11 mm washer)" in page
    assert f"puts {head['pod']['value']:.0f} MPa on PETG under a socket head ({I.HEAD_BEARING_MM['M4']} mm" in page
    assert all(h["verdict"] == "fail" for h in head.values())
