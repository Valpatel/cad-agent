"""cadagent.mechanical.sheet_hardware: the hardware catalogue loads and checks, every item is a part the clinch and rivet
checks know, and the choice and cost follow the prices as read (#283)."""
from __future__ import annotations

import pytest
import subprocess
import sys
from pathlib import Path

from cadagent.mechanical import clinch, rivets
from cadagent.mechanical import sheet_hardware as sh


def test_fresh_default_reader_requires_the_moved_catalogue_despite_a_stale_copy(tmp_path):
    content = sh.DATA.read_bytes()
    current, stale = tmp_path / "docs/research/sheet-hardware.yaml", tmp_path / "research/sheet-hardware.yaml"
    for path in (current, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # Separate processes test first-read behavior without depending on the catalogue cache's implementation.
    code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from cadagent.mechanical import sheet_hardware as sh
sh.ROOT = Path(sys.argv[2]); sh.DATA = sh.ROOT / "docs/research/sheet-hardware.yaml"
print(len(sh.load()))'''
    command = [sys.executable, "-c", code, str(Path(__file__).resolve().parents[2] / "software"), str(tmp_path)]
    good = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert good.returncode == 0 and int(good.stdout.strip()) == len(sh.load()), good.stderr
    current.unlink()
    bad = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode != 0 and str(current) in bad.stderr and stale.exists()


def test_the_catalogue_loads_and_every_item_is_a_checked_part():
    c = sh.load()
    assert len(c) == 30
    assert set(c.categories()) <= set(sh.CATEGORIES)
    for item in c:
        known = rivets.RIVETS if item["category"] == "blind_rivet" else clinch.PARTS
        assert item["part"] in known and item["reference"] in sh.SRC
        if item.get("price_usd") is not None:
            assert item["price_checked"] and item["buy"][0]["url"].startswith("https://")


def test_a_bad_part_key_is_refused(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("items:\n  - {id: x, category: clinch_nut, part: S-M99-1, reference: bossard-pem-prices,"
                 " price_usd: 0.1, price_checked: '2026-11-02', sources: ['https://example.com']}\n")
    with pytest.raises(sh.CatalogueError, match="S-M99-1"):
        sh.load(p)


def test_choose_clinch_puts_the_cheapest_of_each_kind_first():
    rows = sh.choose_clinch("M3", "5052-h32", 1.6)
    keys = [r["part"]["key"] for r in rows]
    # nuts, then studs, then standoffs; steel S-M3-1 at $0.0845 before stainless CLS-M3-1 at $0.1527 (Bossard)
    assert keys == ["S-M3-1", "CLS-M3-1", "FH-M3", "SO-M3", "BSO-M3"]
    assert rows[0]["offer"]["each_usd"] == 0.0845 and rows[0]["offer"]["price_checked"] == "2026-11-02"
    assert rows[0]["offer"]["installed"] is None                  # SendCutSend offers S-M3-0, not S-M3-1
    assert rows[2]["offer"]["installed"]["price_usd"] == 0.77     # FH-M3-10 pressed in by SendCutSend
    assert sh.choose_clinch("M3", "304-annealed", 1.6) == []      # no listed part goes into stainless


def test_a_part_with_no_price_comes_last_with_its_reason():
    rows = sh.choose_clinch("632", "5052-h32", 1.6)
    assert [r["part"]["key"] for r in rows] == ["S-632-1", "CLS-632-1"]
    assert rows[1]["offer"]["each_usd"] is None                   # "Request a quote" at Bossard on 2026-11-02


def test_choose_rivet_by_price_per_piece():
    # 1/8 in, 2.5 mm stack: $10.78 / 250 = $0.04312 (Al/Al) before $11.13 / 250 = $0.04452 (Al/steel) before
    # $11.54 / 100 = $0.1154 (stainless); POP rows have no price here
    rows = sh.choose_rivet(3.2, 2.5)
    assert [r["part"]["key"] for r in rows][:3] == ["mcmaster-97447A015", "mcmaster-97517A015", "mcmaster-97525A415"]
    assert rows[0]["offer"]["each_usd"] == pytest.approx(0.04312)
    assert all(r["offer"] is None for r in rows[3:])


def test_cost_counts_packs_pieces_and_the_shops_price():
    r = sh.cost({"S-632-1": 8, "mcmaster-97447A015": 24})
    nut, riv = r["lines"]
    assert nut["pieces_usd"] == pytest.approx(8 * 0.0847)
    assert nut["installed"]["usd"] == pytest.approx(8 * 0.77)
    assert riv["packs"] == 1 and riv["packs_usd"] == 10.78 and riv["pieces_usd"] == pytest.approx(24 * 0.04312, abs=1e-4)
    assert r["pieces_usd"] == pytest.approx(0.6776 + 1.03488, abs=1e-4)
    assert r["packs_usd"] == pytest.approx(0.6776 + 10.78)
    assert r["installed_usd"] == pytest.approx(6.16)
    # a clinch part SendCutSend does not press in leaves the installed total unknown
    assert sh.cost({"S-M3-1": 4})["installed_usd"] is None
    assert sh.cost({"CLS-632-1": 2})["unpriced"] == ["CLS-632-1"]


@pytest.mark.parametrize("q", [{"S-M3-1": 0}, {"S-M3-1": 1.5}, {"no-such-part": 1}])
def test_cost_refuses(q):
    with pytest.raises((ValueError, KeyError)):
        sh.cost(q)


@pytest.mark.parametrize("extra, match", [
    ("category: clinch_stud, part: S-M3-1", "category is clinch_nut"),
    ("category: clinch_nut, part: S-M3-1, installed: {shop: sendcutsend, price_usd: 0.77,"
     " generated: '2026-04-29', checked: '2026-11-02', reference: sendcutsend-catalog}", "installed needs sku"),
    ("category: clinch_nut, part: S-M3-1, installed: {shop: s, sku: S-M3-1, price_usd: 0.77,"
     " generated: '2026-04-29', checked: '2026-11-02', reference: nope}", "installed.reference"),
])
def test_the_kind_and_the_installed_block_are_checked(tmp_path, extra, match):
    p = tmp_path / "bad.yaml"
    p.write_text("items:\n  - {id: x, " + extra + ", reference: bossard-pem-prices, price_usd: 0.1,"
                 " price_checked: '2026-11-02', sources: ['https://example.com']}\n")
    with pytest.raises(sh.CatalogueError, match=match):
        sh.load(p)


def test_an_unpriced_rivet_leaves_the_installed_total_alone():
    r = sh.cost({"S-632-1": 8, "pop-AD42": 10})
    assert r["unpriced"] == ["pop-AD42"] and r["installed_usd"] == pytest.approx(6.16)


# The canonical six-step technique must exercise these APIs, not just name them in a skill.
def _sheet_skill_code():
    source = (Path(__file__).resolve().parents[2] / ".agents/skills/sheet-metal-hardware/SKILL.md").read_text()
    assert source.count("```python\n") == 1, "identify the canonical six-step example"
    return source.split("```python\n", 1)[1].split("\n```", 1)[0]


def _run_sheet_skill(code, monkeypatch):
    from cadagent.manufacturing import sheet_metal as sm
    from cadagent.mechanical import clinch, rivets
    observed = {}
    calls = ((sm, "check_bends"), (sm, "bend"), (sm, "flat_length"), (sm, "feature_to_bend"),
             (sh, "choose_clinch"), (clinch, "check_placement"), (sh, "choose_rivet"),
             (rivets, "check_joint"), (sh, "cost"))
    with monkeypatch.context() as tap:
        for module, name in calls:
            actual = getattr(module, name)
            def record(*args, _actual=actual, _name=name, **kwargs):
                result = _actual(*args, **kwargs)
                observed[_name] = result  # retain the explicit call after any nested helper calls
                return result
            tap.setattr(module, name, record)
        exec(compile(code, "<canonical sheet-metal skill>", "exec"), {})
    return observed


def _check_sheet_skill(observed, feature="pass", placement="pass"):
    assert set(observed) == {"check_bends", "bend", "flat_length", "feature_to_bend", "choose_clinch",
                             "check_placement", "choose_rivet", "check_joint", "cost"}, "missing technique steps"
    for name, verdict in (("check_bends", "pass"), ("feature_to_bend", feature),
                          ("check_placement", placement), ("check_joint", "pass")):
        assert isinstance(observed[name], dict) and observed[name].get("verdict") == verdict, name
    assert observed["bend"]["allowance_mm"] == pytest.approx(2.452, abs=0.001)
    assert observed["flat_length"]["flat_mm"] == pytest.approx(74.948, abs=0.001)
    nut, rivet = observed["choose_clinch"][0], observed["choose_rivet"][0]
    assert nut["part"]["key"] == "S-632-1" and rivet["part"]["key"] == "pop-AD41-43-mg"
    cost = observed["cost"]
    assert isinstance(cost, dict), "missing cost output"
    assert cost["unpriced"] == [rivet["part"]["key"]] and rivet["offer"] is None
    assert cost["pieces_usd"] == pytest.approx(0.6776) and cost["installed_usd"] == pytest.approx(6.16)
    assert cost["lines"][0]["price_checked"] == nut["offer"]["price_checked"] == "2026-11-02"
    assert cost["limits"], "the dated price and installation limits must survive"


def test_the_canonical_sheet_skill_example_runs(monkeypatch):
    _check_sheet_skill(_run_sheet_skill(_sheet_skill_code(), monkeypatch))


@pytest.mark.parametrize("old,new,feature,placement", [
    ("10.5 - ba / 2 - hole / 2", "8.0 - ba / 2 - hole / 2", "warn", "pass"),
    ("edge_mm=6.5", "edge_mm=4.0", "pass", "fail"),
])
def test_sheet_skill_changed_inputs_keep_warn_and_fail(monkeypatch, old, new, feature, placement):
    code = _sheet_skill_code()
    assert code.count(old) == 1
    _check_sheet_skill(_run_sheet_skill(code.replace(old, new), monkeypatch), feature, placement)


def test_sheet_skill_bad_material_does_not_pass(monkeypatch):
    code = _sheet_skill_code()
    old = 'sh.choose_clinch("632", "5052-h32", 1.6)'
    assert code.count(old) == 1
    with pytest.raises(ValueError, match="unknown sheet"):
        _run_sheet_skill(code.replace(old, 'sh.choose_clinch("632", "unlisted-sheet", 1.6)'), monkeypatch)


def test_sheet_skill_consumer_rejects_missing_or_noop_output(monkeypatch):
    with pytest.raises(AssertionError, match="missing technique steps"):
        _check_sheet_skill(_run_sheet_skill("", monkeypatch))
    code = _sheet_skill_code()
    cost_call = 'sh.cost({"S-632-1": 8, rivet: 24})'
    assert code.count(cost_call) == 1
    with pytest.raises(AssertionError, match="missing technique steps"):
        _check_sheet_skill(_run_sheet_skill(code.replace(cost_call, "None"), monkeypatch))
    monkeypatch.setattr(sh, "cost", lambda *args, **kwargs: None)
    with pytest.raises(AssertionError, match="missing cost output"):
        _check_sheet_skill(_run_sheet_skill(_sheet_skill_code(), monkeypatch))


def test_sheet_skill_consumer_rejects_forced_pass_on_warn(monkeypatch):
    from cadagent.manufacturing import sheet_metal as sm
    code = _sheet_skill_code().replace("10.5 - ba / 2 - hole / 2", "8.0 - ba / 2 - hole / 2")
    monkeypatch.setattr(sm, "feature_to_bend", lambda *args, **kwargs: {"verdict": "pass"})
    with pytest.raises(AssertionError, match="feature_to_bend"):
        _check_sheet_skill(_run_sheet_skill(code, monkeypatch), feature="warn")
