"""cadagent.mechanical.mcmaster without the network.

The page parsing, part-number checks, download checks, SOURCE.txt, the catalogue helpers and the CLI (with a fake
Session) need neither Playwright nor CadQuery, so they run in the core CI job. normalise() is tested on synthetic
CadQuery parts placed in odd frames, one per kind's convention; those tests skip without CadQuery."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from cadagent.mechanical import mcmaster as mc
from cadagent.cli import main

STEP_TEXT = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


# ----------------------------------------------------------------------------------- page data (no CadQuery)

def test_price_and_pack():
    assert mc.parse_price("$10.91 each") == (10.91, 1)
    assert mc.parse_price(" $13.96 per pack of 100 ") == (13.96, 100)
    assert mc.parse_price("$1,233.64 each") == (1233.64, 1)
    assert mc.parse_price("") == (None, None)


def test_spec_rows_group_and_parse():
    rows = [("For Shaft Diameter", "12 mm", False), ("Width Tolerance", "-0.12 mm to 0 mm", False),
            ("Dynamic Radial Load Capacity", "1,100 lb.", False), ("Temperature Range", "", False),
            ("Minimum", "-20° F", True), ("Max.", "230° F", True), ("Material", "Steel", False),
            ("Thread Size", "M5 × 0.8 mm", False), ("Length", "3/4\"", False), ("Weight", "0.05 lb.", False)]
    raw, parsed = mc.parse_specs(rows)
    assert raw["Temperature Range Minimum"] == "-20° F" and "Temperature Range" not in raw
    assert parsed["For Shaft Diameter"] == {"value": 12.0, "unit": "mm"}
    assert parsed["Width Tolerance"] == {"min": -0.12, "max": 0.0, "unit": "mm"}
    assert parsed["Dynamic Radial Load Capacity"]["unit"] == "N"
    assert parsed["Dynamic Radial Load Capacity"]["value"] == pytest.approx(4893.04, abs=0.01)
    assert parsed["Temperature Range Max."]["value"] == pytest.approx(110.0)
    assert parsed["Thread Size"]["thread"] == "M5x0.8"
    assert parsed["Length"]["value"] == pytest.approx(19.05)
    assert parsed["Weight"] == {"value": pytest.approx(22.68, abs=0.01), "unit": "g"}
    assert "Material" not in parsed
    assert mc.listed_weight_g(parsed) == pytest.approx(22.68, abs=0.01)


def test_a_weight_capacity_is_a_load_not_the_parts_weight():
    raw, parsed = mc.parse_specs([("Weight Capacity", "500 lb.", False), ("Load Capacity", "20 lb.", False)])
    assert parsed["Weight Capacity"]["unit"] == "N"
    assert parsed["Weight Capacity"]["value"] == pytest.approx(2224.1, abs=0.1)
    assert mc.listed_weight_g(parsed) is None
    page = mc.page_data("1234A5", {"rows": [("Weight Capacity", "500 lb.", False)], "price_text": "$1.00 each",
                                   "title": "Caster", "subtitle": "", "options": [], "breadcrumbs": []})
    assert page["listed_weight_g"] is None


@pytest.mark.parametrize("pn", ["5972K82", "91290a242", " 9307K884 ", "1061T17", "92981A411"])
def test_part_numbers_accepted(pn):
    assert mc.validate_pn(pn) == pn.strip().upper()
    assert mc.product_url(pn) == f"https://www.mcmaster.com/{pn.strip().upper()}/"


@pytest.mark.parametrize("bad", ["products/ball-bearings", "../x", "6001-2RS", "https://www.mcmaster.com/5972K82/",
                                 "", "5972K82/../../etc", "ball bearings", "K82"])
def test_anything_but_a_part_number_is_refused(bad):
    with pytest.raises(ValueError, match="not a McMaster-Carr part number"):
        mc.product_url(bad)


def test_the_pause_between_pages_has_a_floor():
    assert mc.Session(delay_s=0).delay_s == mc.MIN_DELAY_S
    assert mc.Session(delay_s=5).delay_s == 5


def test_accept_download_keeps_only_step_files(tmp_path):
    out = tmp_path / "5972K82.step"
    t = tmp_path / "dl1"
    t.write_text(STEP_TEXT)
    assert mc.accept_download(t, out, "5972K82_Bearing.STEP") == out and out.read_text() == STEP_TEXT
    assert not t.exists()
    z = tmp_path / "dl2"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("readme.txt", "x")
        zz.writestr("part.stp", STEP_TEXT)
    out2 = tmp_path / "zipped.step"
    assert mc.accept_download(z, out2).read_text() == STEP_TEXT
    bad = tmp_path / "dl3"
    bad.write_text("%PDF-1.7 a drawing")
    out3 = tmp_path / "x.step"
    with pytest.raises(RuntimeError, match="not a STEP file"):
        mc.accept_download(bad, out3, "drawing.pdf")
    assert not out3.exists() and not bad.exists()


def test_catalog_entry_prefers_listed_weight_and_keeps_extra_fields(tmp_path):
    page = {"pn": "1234A5", "description": "Thing", "url": mc.product_url("1234a5"), "price_usd": 2.5, "pack_qty": 10,
            "listed_weight_g": 3.2, "specs": {"raw": {"Material": "Brass", "Length": "8 mm"},
                                              "parsed": {"Length": {"value": 8.0, "unit": "mm"}}}}
    info = {"mass_g_est": 9.9, "density_g_cm3": 8.5, "frame": mc.FRAMES["pin"], "kind": "pin", "bbox_mm": {}}
    e = mc.catalog_entry(page, info, cad="x/1234A5.norm.step")
    assert e["mass_g"] == 3.2 and e["mass_basis"] == "McMaster listed weight"
    assert e["dims_mm"]["length"] == 8.0 and e["material"] == "Brass"
    cat = tmp_path / "hardware.json"
    cat.write_text(json.dumps({"source": "s", "items": {"pin": {"used_for": "keep me", "qty": 4}}}))
    mc.update_catalog(cat, "pin", e)
    item = json.loads(cat.read_text())["items"]["pin"]
    assert item["used_for"] == "keep me" and item["qty"] == 4 and item["mcmaster"] == "1234A5"
    page.pop("listed_weight_g")
    assert "estimate" in mc.catalog_entry(page, info)["mass_basis"]


def test_update_catalog_list_layout(tmp_path):
    cat = tmp_path / "parts.json"
    cat.write_text(json.dumps([{"id": "a", "notes": "keep"}, {"id": "b"}]))
    mc.update_catalog(cat, "a", {"mcmaster": "1A1", "notes": None})
    mc.update_catalog(cat, "c", {"mcmaster": "3C3"})
    items = json.loads(cat.read_text())
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert items[0] == {"id": "a", "notes": "keep", "mcmaster": "1A1"}


def test_source_txt_keeps_one_entry_per_part(tmp_path):
    mc.write_source(tmp_path, "91290A242", "M5 x 20 SHCS", when="2026-01-02")
    mc.write_source(tmp_path, "91290A232", "M5 x 16 SHCS", when="2026-01-02")
    mc.write_source(tmp_path, "91290A242", "M5 x 20 SHCS", when="2026-02-03")      # refreshed, not duplicated
    t = (tmp_path / "SOURCE.txt").read_text()
    assert t.count("not redistributed") == 1
    assert t.count("https://www.mcmaster.com/91290A242/") == 1 and "https://www.mcmaster.com/91290A232/" in t
    assert "2026-02-03" in t and "2026-01-02" in t
    with pytest.raises(ValueError):
        mc.write_source(tmp_path, "../x")


def test_material_of_falls_back_to_finished_material():
    assert mc.material_of({"Finished Material": "Zinc-Plated Steel", "Insert Material": "Nylon"}) == "Zinc-Plated Steel"
    assert mc.density_for(mc.material_of({"Material": "18-8 Stainless Steel"})) == 8.0


def test_fetch_without_playwright_says_how_to_install(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_pw(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pw)
    with pytest.raises(mc.MissingDependency, match="pip install playwright"):
        mc._playwright()


def test_chrome_missing_stops_the_driver_and_explains(monkeypatch):
    stopped = []

    class Driver:
        class chromium:
            @staticmethod
            def launch(**kw):
                raise RuntimeError("Executable doesn't exist at /opt/google/chrome/chrome\nmore")

        def stop(self):
            stopped.append(True)

    class Starter:
        def start(self):
            return Driver()

    monkeypatch.setattr(mc, "_playwright", lambda: (lambda: Starter()))
    with pytest.raises(mc.MissingDependency, match="install Google Chrome"):
        with mc.Session():
            pass
    assert stopped == [True]


# ----------------------------------------------------------------------------------- not a product page

PAGES = Path(__file__).parent / "fixtures" / "mcmaster"          # hand-written pages, never fetched
GATE_HTML = (PAGES / "login-gate.html").read_text()
OTHER_HTML = (PAGES / "not-a-product.html").read_text()


def test_the_login_gate_is_read_from_the_visible_text_only():
    assert mc.login_gate(GATE_HTML) == "Log in to view Product Detail"   # across tags, spaces and &nbsp;
    assert "in a script" not in mc.page_text(GATE_HTML)
    assert mc.login_gate(OTHER_HTML) is None      # the header's "Log in" link and a script string do not count


@pytest.mark.parametrize("text, prompt", [
    ("<p>Login to view Product Detail.</p>", "Login to view Product Detail"),
    ("<p>SIGN IN TO SEE pricing</p>", "SIGN IN TO SEE pricing"),
    ("<p>Please log in to continue</p>", "log in to continue"),
    ("<a>Log in</a> <p>Log in or create an account</p>", None),
    ("<p>Our blog in to view-only mode</p>", None),
    ("", None),
])
def test_login_gate_phrases(text, prompt):
    assert mc.login_gate(text) == prompt


def test_a_login_gate_says_the_part_number_may_be_fine():
    url = mc.product_url("5972K86")
    err = mc.page_error("5972K86", url, GATE_HTML)
    assert isinstance(err, mc.LoginRequired) and isinstance(err, RuntimeError)
    msg = str(err)
    assert msg.startswith("5972K86: McMaster asked for a login (\"Log in to view Product Detail\" at " + url)
    assert "the part number may be fine" in msg and "not a product page" not in msg
    assert "https://www.mcmaster.com/6301-2RS/" in msg and "datasheet" in msg    # where to look instead
    for html in (OTHER_HTML, ""):                 # no prompt: the old message, not a login
        plain = mc.page_error("5972K86", url, html)
        assert type(plain) is RuntimeError
        assert str(plain) == f"5972K86: {url} is not a product page (no specification table)"


class FakePage:
    """The Playwright page calls Session._open makes, on a saved page that has no specification table."""

    def __init__(self, html=None):
        self.html, self.url, self.visited = html, "", []

    def goto(self, url, **kw):
        self.url = url
        self.visited.append(url)

    def wait_for_selector(self, selector):
        raise TimeoutError(f"Timeout waiting for {selector}")

    def content(self):
        if self.html is None:
            raise RuntimeError("page crashed")
        return self.html

    def wait_for_timeout(self, ms):
        pass


@pytest.mark.parametrize("html, login", [(GATE_HTML, True), (OTHER_HTML, False), (None, False)])
def test_session_tells_a_login_gate_from_a_missing_page(html, login):
    s = mc.Session()
    s.page = FakePage(html)
    with pytest.raises(RuntimeError) as caught:
        s.read("5972K86")
    assert isinstance(caught.value, mc.LoginRequired) is login
    assert ("part number may be fine" in str(caught.value)) is login
    assert caught.value.__suppress_context__                 # no Playwright timeout traceback behind it
    assert s.page.visited == ["https://www.mcmaster.com/5972K86/"]


# ----------------------------------------------------------------------------------- the CLI, offline

PAGE = {"pn": "", "url": "", "description": "Thing", "price_text": "$1.00 each", "price_usd": 1.0, "pack_qty": 1,
        "listed_weight_g": None, "options": [], "specs": {"raw": {"Material": "Steel"}, "parsed": {}}, "read": "2026-01-01"}


class FakeSession:
    """Stands in for mc.Session: records what it was asked to fetch and writes a page and a stub STEP."""
    started = 0
    fetched: list = []

    def __init__(self, delay_s=3.0, **kw):
        self.delay_s = max(delay_s, mc.MIN_DELAY_S)

    def __enter__(self):
        FakeSession.started += 1
        return self

    def __exit__(self, *exc):
        pass

    def fetch(self, pn, out_dir, choose=None):
        FakeSession.fetched.append((pn, choose))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{pn}.step").write_text(STEP_TEXT)
        (out_dir / f"{pn}.page.json").write_text(json.dumps(dict(PAGE, pn=pn, url=mc.product_url(pn))))
        return out_dir / f"{pn}.step"


@pytest.fixture
def fake(monkeypatch):
    FakeSession.started, FakeSession.fetched = 0, []
    monkeypatch.setattr(mc, "Session", FakeSession)
    return FakeSession


def test_cli_downloads_then_reuses_without_a_browser(tmp_path, fake, capsys):
    out = tmp_path / "v"
    assert main(["mcmaster", "5972K82", "91290A242", "--out", str(out)]) == 0
    assert fake.started == 1 and [p for p, _ in fake.fetched] == ["5972K82", "91290A242"]
    assert main(["mcmaster", "5972K82", "--out", str(out)]) == 0
    assert fake.started == 1                       # everything already here: no browser
    assert "already here" in capsys.readouterr().out


def test_cli_refuses_bad_input(tmp_path, fake, capsys):
    out = str(tmp_path / "v")
    assert main(["mcmaster", "products/ball-bearings", "--out", out]) == 2
    assert main(["mcmaster", "../x", "--out", out]) == 2
    assert main(["mcmaster", "5972K82", "--catalog", str(tmp_path / "c.json"), "--out", out]) == 2
    assert "need --kind" in capsys.readouterr().err
    assert main(["mcmaster", "5972K82", "91290A242", "--choose", "Right Hand", "--out", out]) == 2
    assert fake.started == 0 and not (tmp_path / "v").exists()


def test_cli_choose_per_part_and_before_the_part_numbers(tmp_path, fake):
    out = str(tmp_path / "v")
    assert main(["mcmaster", "--choose", "59935K53:Right Hand", "59935K53", "91290A242", "--out", out]) == 0
    assert fake.fetched == [("59935K53", ["Right Hand"]), ("91290A242", None)]
    fake.fetched.clear()
    assert main(["mcmaster", "--choose", "Left Hand", "59935K73", "--out", out]) == 0
    assert fake.fetched == [("59935K73", ["Left Hand"])]


def test_cli_after_a_login_gate_asks_for_no_more_pages(tmp_path, fake, monkeypatch, capsys):
    out = tmp_path / "v"
    FakeSession().fetch("91290A242", out / "91290A242")         # already here: still reported, offline
    fake.fetched.clear()

    def gated(self, pn, out_dir, choose=None):
        fake.fetched.append((pn, choose))
        raise mc.page_error(pn, mc.product_url(pn), GATE_HTML)

    monkeypatch.setattr(FakeSession, "fetch", gated)
    assert main(["mcmaster", "5972K86", "5972K82", "91290A242", "--out", str(out)]) == 1
    assert [p for p, _ in fake.fetched] == ["5972K86"]         # one gated page, then no more requests
    cap = capsys.readouterr()
    assert "mcmaster 5972K86: 5972K86: McMaster asked for a login" in cap.err
    assert "mcmaster 5972K82: not fetched: McMaster asked for a login at 5972K86 in this run" in cap.err
    assert "91290A242: already here" in cap.out


def test_cli_low_delay_is_raised_to_the_floor(tmp_path, fake, capsys):
    assert main(["mcmaster", "5972K82", "--delay", "0", "--out", str(tmp_path / "v")]) == 0
    assert "below the minimum" in capsys.readouterr().out


# ----------------------------------------------------------------------------------- normalise (CadQuery)

@pytest.fixture
def cq():
    return pytest.importorskip("cadquery")


def _step(tmp_path, cq, name, shape):
    p = tmp_path / f"{name}.step"
    cq.exporters.export(shape if isinstance(shape, cq.Workplane) else cq.Workplane(obj=shape), str(p), exportType="STEP")
    return p


def _odd_frame(wp, flip=False):
    """Lay a part built on +Z along X instead (head/flange first towards +X or, flipped, -X), rotated about its
    axis and moved off the origin."""
    if flip:
        wp = wp.rotate((0, 0, 0), (0, 1, 0), 180)
    return wp.rotate((0, 0, 0), (0, 0, 1), 17).rotate((0, 0, 0), (0, 1, 0), 90).translate((40.0, -12.0, 7.5))


def test_bearing_ring_lands_on_z0_centred(tmp_path, cq):
    ring = cq.Workplane("XY").circle(14).circle(6).extrude(8)
    p = _step(tmp_path, cq, "ring", _odd_frame(ring))
    out, info = mc.normalise(p, "bearing", density=7.85)
    assert out.name == "ring.norm.step" and out.exists()
    first = out.read_bytes()
    assert b"= PRODUCT('ring.norm','ring.norm'," in first                    # named after the file (#91)
    assert mc.normalise(p, "bearing", density=7.85)[0].read_bytes() == first  # and the same bytes again
    b = info["bbox_mm"]
    assert b["min"][2] == pytest.approx(0, abs=1e-3) and b["max"][2] == pytest.approx(8, abs=1e-3)
    assert b["min"][0] == pytest.approx(-14, abs=1e-3) and b["max"][1] == pytest.approx(14, abs=1e-3)
    assert abs(abs(info["axis_found"][0]) - 1) < 1e-6           # it lay along X
    vol = 3.14159265 * (14 ** 2 - 6 ** 2) * 8
    assert info["volume_mm3"] == pytest.approx(vol, rel=1e-3)
    assert info["mass_g_est"] == pytest.approx(vol * 7.85 / 1000, rel=1e-3)


@pytest.mark.parametrize("flip", [False, True])
def test_flanged_bearing_flange_down_whichever_way_it_was_modelled(tmp_path, cq, flip):
    part = (cq.Workplane("XY").circle(16).circle(6).extrude(1.5)
            .union(cq.Workplane("XY").circle(14).circle(6).extrude(8)))
    p = _step(tmp_path, cq, "flanged", _odd_frame(part, flip))
    _, info = mc.normalise(p, "bearing")
    norm = cq.importers.importStep(str(tmp_path / "flanged.norm.step")).val()
    low = norm.intersect(cq.Workplane("XY").box(50, 50, 1.0).translate((0, 0, 0.5)).val()).BoundingBox()
    assert low.xlen == pytest.approx(32, abs=1e-2)               # the flange is the slice at z = 0..1
    assert info["end_down"] == "larger end"
    assert info["bbox_mm"]["max"][2] == pytest.approx(8, abs=1e-3)


def test_pin_with_a_flat_is_centred_on_its_axis_not_its_centre_of_mass(tmp_path, cq):
    pin = cq.Workplane("XY").circle(5).extrude(30).cut(cq.Workplane("XY").box(10, 10, 40).translate((8.5, 0, 0)))
    p = _step(tmp_path, cq, "dpin", _odd_frame(pin))
    out, info = mc.normalise(p, "pin")
    norm = cq.importers.importStep(str(out)).val()
    r = max(r for _, r in mc._profile(norm))
    assert r == pytest.approx(5.0, abs=1e-3)                    # off the axis, the round side would reach further
    assert info["bbox_mm"]["max"][2] == pytest.approx(30, abs=1e-3)


def _socket_screw(cq, head_d=8.5, head_h=5.0, d=5.0, length=20.0):
    return (cq.Workplane("XY").circle(head_d / 2).extrude(head_h)
            .faces(">Z").workplane().polygon(6, 4.0).cutBlind(-2.5)
            .union(cq.Workplane("XY").circle(d / 2).extrude(-length)))


@pytest.mark.parametrize("flip", [False, True])
def test_screw_head_up_underside_at_z0(tmp_path, cq, flip):
    p = _step(tmp_path, cq, "screw", _odd_frame(_socket_screw(cq), flip))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(5.0, abs=1e-3)           # head on +z, 5 tall
    assert b["min"][2] == pytest.approx(-20.0, abs=1e-3)         # shank 20 long towards -z
    assert b["max"][0] == pytest.approx(4.25, abs=1e-3)
    assert info["head_d"] == pytest.approx(8.5, abs=1e-3) and info["head"] == "flat underside"


def test_screw_with_a_stepped_head_underside(tmp_path, cq):
    # some imported screw models: a slightly smaller bearing-face step (1.1 mm) under the full head diameter
    s = (cq.Workplane("XY").circle(4.25).extrude(3.9)
         .union(cq.Workplane("XY").workplane(offset=-1.1).circle(4.15).extrude(1.1))
         .union(cq.Workplane("XY").workplane(offset=-1.1).circle(2.5).extrude(-22)))
    p = _step(tmp_path, cq, "stepped", _odd_frame(s))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(5.0, abs=1e-3) and b["min"][2] == pytest.approx(-22.0, abs=1e-3)


@pytest.mark.parametrize("flip", [False, True])
def test_hex_head_screw(tmp_path, cq, flip):
    s = (cq.Workplane("XY").polygon(6, 9.24).extrude(3.5)          # M5 hex head, 8 across flats
         .union(cq.Workplane("XY").circle(2.5).extrude(-20)))
    p = _step(tmp_path, cq, "hexhead", _odd_frame(s, flip))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(3.5, abs=1e-3) and b["min"][2] == pytest.approx(-20, abs=1e-3)
    assert info["head_d"] == pytest.approx(9.24, abs=1e-2)


@pytest.mark.parametrize("flip", [False, True])
def test_countersunk_screw_top_face_at_z0(tmp_path, cq, flip):
    head = cq.Solid.makeCone(2.5, 5.0, 2.7, cq.Vector(0, 0, -2.7))  # 90 deg flat head, 10 across, 2.7 tall
    s = cq.Workplane(obj=head).union(cq.Workplane("XY").workplane(offset=-2.7).circle(2.5).extrude(-17.3))
    p = _step(tmp_path, cq, "flathead", _odd_frame(s, flip))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert info["head"] == "countersunk"
    assert b["max"][2] == pytest.approx(0.0, abs=1e-3) and b["min"][2] == pytest.approx(-20.0, abs=1e-3)


def test_button_head_screw(tmp_path, cq):
    dome = cq.Workplane("XY").sphere(5).intersect(cq.Workplane("XY").box(20, 20, 2.75).translate((0, 0, 1.375)))
    s = dome.union(cq.Workplane("XY").circle(2.5).extrude(-12))
    p = _step(tmp_path, cq, "button", _odd_frame(s, True))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(2.75, abs=1e-3) and b["min"][2] == pytest.approx(-12, abs=1e-3)


def test_headless_part_as_screw_is_an_error(tmp_path, cq):
    p = _step(tmp_path, cq, "stud", _odd_frame(cq.Workplane("XY").circle(2.5).extrude(20)))
    with pytest.raises(ValueError, match="no head wider than the shank"):
        mc.normalise(p, "screw")


def test_shoulder_screw(tmp_path, cq):
    s = (cq.Workplane("XY").circle(9).extrude(9)
         .union(cq.Workplane("XY").circle(6).extrude(-30))
         .union(cq.Workplane("XY").workplane(offset=-30).circle(5).extrude(-16)))
    p = _step(tmp_path, cq, "shoulder", _odd_frame(s, True))
    _, info = mc.normalise(p, "shoulder_screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(9, abs=1e-3) and b["min"][2] == pytest.approx(-46, abs=1e-3)


def _rod_end(cq, with_ball=True):
    # built with the ball at (0,0,0), bore along Z and the shank along +X (centre to shank end 36)
    housing = cq.Workplane("XY").circle(11).extrude(9).translate((0, 0, -4.5))
    shank = cq.Workplane("YZ").circle(5.0).extrude(36 - 9).translate((9, 0, 0))
    if with_ball:
        ball = cq.Workplane("XY").sphere(7).intersect(cq.Workplane("XY").box(20, 20, 12)).cut(
            cq.Workplane("XY").circle(3).extrude(20).translate((0, 0, -10)))
        body = housing.cut(cq.Workplane("XY").sphere(7)).union(shank).union(ball)
    else:                                         # a simplified model: a plain eye with a bore, no sphere
        body = housing.union(shank).cut(cq.Workplane("XY").circle(4).extrude(20).translate((0, 0, -10)))
    return body.rotate((0, 0, 0), (1, 1, 0), 33).translate((5, 6, 7))


@pytest.mark.parametrize("with_ball", [True, False])
def test_rod_end_ball_at_origin_bore_y_shank_minus_z(tmp_path, cq, with_ball):
    p = _step(tmp_path, cq, "rodend", _rod_end(cq, with_ball))
    _, info = mc.normalise(p, "rod_end")
    b = info["bbox_mm"]
    if with_ball:
        assert info["ball_d"] == pytest.approx(14, abs=1e-3)
        assert b["max"][1] == pytest.approx(6, abs=1e-2)         # ball width 12 along the bore (Y)
    else:
        assert info["ball_d"] is None and "bore midpoint" in info["centre_from"]
        assert b["max"][1] == pytest.approx(5, abs=1e-2)         # shank radius; the eye is 9 wide, centred
        assert b["min"][1] == pytest.approx(-5, abs=1e-2)
    assert b["min"][2] == pytest.approx(-36, abs=1e-2)           # the shank's end, 36 from the ball centre
    assert b["max"][2] == pytest.approx(11, abs=1e-2)            # the housing's far side
    assert b["max"][0] == pytest.approx(11, abs=1e-2)


def test_rod_end_without_cylinders_is_a_clear_error(tmp_path, cq):
    p = _step(tmp_path, cq, "blob", cq.Workplane("XY").box(10, 20, 30))
    with pytest.raises(ValueError, match="no cylindrical faces"):
        mc.normalise(p, "rod_end")


def test_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        mc.normalise(tmp_path / "x.step", "sprocket")


def test_cli_normalises_offline_and_records_the_catalogue(tmp_path, cq, fake, monkeypatch):
    out = tmp_path / "v"
    folder = out / "91290A242"
    folder.mkdir(parents=True)
    _step(tmp_path, cq, "s", _odd_frame(_socket_screw(cq)))
    (folder / "91290A242.step").write_bytes((tmp_path / "s.step").read_bytes())
    (folder / "91290A242.page.json").write_text(json.dumps(dict(PAGE, pn="91290A242", url=mc.product_url("91290A242"))))
    monkeypatch.chdir(tmp_path)
    cat = tmp_path / "hw.json"
    assert main(["mcmaster", "91290A242", "--kind", "screw", "--out", str(out), "--catalog", str(cat),
                 "--key", "screw_m5x20"]) == 0
    assert fake.started == 0                                    # all local: no browser
    e = json.loads(cat.read_text())["items"]["screw_m5x20"]
    assert e["cad"] == "v/91290A242/91290A242.norm.step" and e["kind"] == "screw"
    assert e["bbox_mm"]["max"][2] == pytest.approx(5.0, abs=1e-3)
