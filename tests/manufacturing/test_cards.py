"""Rule cards and decision cards (#323 phase 7b): golden output, the byte budget, every citation a read record, every
applied_by real, every decision row reachable, and planted defects that must be refused.

The goldens are in tests/fixtures/cards/. A change to the data or the layout changes them on purpose: rewrite them
with CADAGENT_UPDATE_GOLDEN=1 and read the diff before committing it."""
import importlib
import itertools
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from cadagent.cli import main
from cadagent.manufacturing import cards
from cadagent.manufacturing import process as pp

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "cards"
SAMPLES = {
    "rules-insert-hole-fdm-petg-cf": ["rules", "insert-hole", "--process", "fdm", "--material", "petg-cf"],
    "rules-insert-hole-fdm-petg": ["rules", "insert-hole", "--process", "fdm", "--material", "petg"],
    "rules-why-cad-offset": ["rules", "--why", "fdm-insert-hole-cad-offset-cnckitchen"],
    "choose-joining-fdm-petg-200n-50": ["choose", "joining", "--load", "200", "--cycles", "50", "--material", "petg",
                                         "--process", "fdm"],
    "choose-joining-sheet-5052": ["choose", "joining", "--process", "sheet-metal", "--material", "5052"],
}
# one input set per row of the joining table, so every branch is exercised
ROWS = {
    "sheet": dict(process="sheet-metal", material="5052", load=100, cycles=10),
    "resin": dict(process="sla", load=50, cycles=1),
    "clip-once": dict(process="fdm", material="petg", load=0, cycles=1),
    "clip-repeated": dict(process="fdm", material="petg", load=0, cycles=20),
    "too-heavy": dict(process="fdm", material="pla", load=5000, cycles=1),
    "repeated": dict(process="fdm", material="petg", load=200, cycles=50),
    "once": dict(process="fdm", material="petg", load=50, cycles=1),
}


@pytest.fixture(scope="module")
def reg():
    return cards.registry()


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


# ----------------------------------------------------------------------------- golden cards

@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_golden_cards(name, capsys):
    code, out, err = _run(SAMPLES[name], capsys)
    assert code == 0, err
    path = GOLDEN / f"{name}.txt"
    if os.environ.get("CADAGENT_UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out, encoding="utf-8")
    assert out == path.read_text(encoding="utf-8"), \
        f"{name} changed: if on purpose, rewrite with CADAGENT_UPDATE_GOLDEN=1 and read the diff"


def test_output_is_stable_across_calls():
    a = cards.render_card(cards.card("insert-hole", process="fdm", material="petg-cf"))
    b = cards.render_card(cards.card("insert-hole", process="fdm", material="petg-cf"))
    assert a == b
    assert cards.render_choice(cards.choose("joining", **ROWS["repeated"])) == \
        cards.render_choice(cards.choose("joining", **ROWS["repeated"]))


def test_the_insert_hole_card_says_when_how_strict_and_who():
    c = cards.card("insert-hole", process="fdm", material="petg-cf")
    by_id = {ln["rule"]: ln for ln in c["lines"]}
    assert set(by_id) == {"fdm-insert-hole-m3-nominal-cnckitchen", "fdm-insert-blind-depth-cnckitchen",
                          "fdm-insert-hole-cad-offset-cnckitchen", "fdm-insert-hole-filler-spirol"}
    assert [ln["strictness"] for ln in c["lines"]][:2] == ["non-negotiable"] * 2, "non-negotiable rules come first"
    offset = by_id["fdm-insert-hole-cad-offset-cnckitchen"]
    assert offset["numbers"] == "0.2-0.3 mm" and offset["confidence"] == "high"
    assert offset["instead"] == ["fdm-insert-hole-m3-nominal-cnckitchen"]
    assert "cadagent.mechanical.inserts.printed_hole" in offset["applied_by"]
    assert by_id["fdm-insert-blind-depth-cnckitchen"]["unstated"] == ["cost"], "no source states its cost: flagged"


def test_material_leaves_out_the_rules_for_other_materials():
    unfilled = cards.card("insert-hole", process="fdm", material="petg")
    assert "fdm-insert-hole-filler-spirol" not in [ln["rule"] for ln in unfilled["lines"]]
    assert unfilled["other_materials_left_out"] == ["fdm-insert-hole-filler-spirol"]
    assert cards.material_family("fdm", "pa6-cf20-polymaker-dry") == "pa-cf"
    with pytest.raises(cards.CardError, match="not known"):
        cards.card("insert-hole", process="fdm", material="unobtainium")


def test_expressions_are_shown_as_written():
    c = cards.card("printed-hole", process="fdm")
    nums = {ln["rule"]: ln["numbers"] for ln in c["lines"]}
    assert nums["fdm-hole-arc-floor-reprap"] == "at least sqrt(D*D + track*track) mm"
    assert nums["fdm-hole-facets-nophead"] == "D / cos(pi / facets) mm"


# ----------------------------------------------------------------------------- the budget

def _every_card():
    procs = [None] + list(pp.load().profiles)
    for name in cards.card_names():
        for p in procs:
            yield name, p, cards.card(name, process=p)


def test_every_card_fits_the_byte_budget():
    over = [(n, p, len(cards.render_card(c).encode())) for n, p, c in _every_card()
            if len(cards.render_card(c).encode()) > cards.CARD_BYTES]
    assert not over, f"cards over {cards.CARD_BYTES} bytes: {over}"
    jover = [(n, p) for n, p, c in _every_card() if len(cards.as_json(cards.card_json(c)).encode()) > cards.JSON_BYTES]
    assert not jover, f"JSON cards over {cards.JSON_BYTES} bytes: {jover}"


def test_a_card_over_budget_names_what_it_left_out():
    c = cards.card("wall")                      # every process's walls: far more than 2 KB
    text, js = cards.render_card(c), cards.card_json(c)
    assert len(text.encode()) <= cards.CARD_BYTES and "more (narrow with --process" in text
    assert js["more"] and len(js["lines"]) + len(js["more"]) == len(c["lines"])
    small = cards.render_card(c, budget=600)
    assert len(small.encode()) <= 600


def test_every_decision_and_why_fits_the_byte_budget():
    grid = itertools.product(["fdm", "sls", "mjf", "injection-moulding", "sla", "sheet-metal"],
                             [0, 50, 200, 5000], [1, 2, 50])
    for process, load, cycles in grid:
        material = {"fdm": "petg", "sheet-metal": "304"}.get(process)
        c = cards.choose("joining", process=process, material=material, load=load, cycles=cycles)
        assert len(cards.render_choice(c).encode()) <= cards.CARD_BYTES, (process, load, cycles)
        assert len(cards.as_json(c).encode()) <= cards.JSON_BYTES, (process, load, cycles)
    for r in pp.load().rules():
        if r.verified and not r.shop:
            assert len(cards.render_why(cards.why(r.id)).encode()) <= cards.CARD_BYTES, r.id


# ----------------------------------------------------------------------------- citations and applied_by

def test_the_profile_cards_and_decisions_have_no_problems():
    assert cards.problems() == []


def test_every_cited_ref_resolves_to_a_read_record(reg):
    texts = [cards.render_card(c) for _, _, c in _every_card()]
    texts += [cards.render_choice(cards.choose("joining", **kw)) for kw in ROWS.values()]
    texts += [cards.render_why(cards.why(r.id)) for r in pp.load().rules() if r.verified and not r.shop and r.cards]
    keys = {k for t in texts for k in cards.REF.findall(t)}
    assert len(keys) > 20
    bad = [k for k in keys if k not in reg or reg.resolve(k).kind != "source"]
    assert not bad, f"cards cite records that are not read sources: {bad}"


def test_every_applied_by_on_a_card_resolves():
    names = {n for _, _, c in _every_card() for ln in c["lines"] for n in ln["applied_by"]}
    assert "cadagent.mechanical.inserts.printed_hole" in names
    for name in names:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            module, attr = name.rsplit(".", 1)
            assert callable(getattr(importlib.import_module(module), attr)), name
    for dec in cards.decisions().values():
        for f in dec["facts"].values():
            assert f["by"].rsplit(".", 1)[-1] in cards.FACTS
        for row in dec["rows"]:
            for name in row.get("by") or []:
                module, attr = name.rsplit(".", 1)
                assert callable(getattr(importlib.import_module(module), attr)), name


# ----------------------------------------------------------------------------- the joining decision

@pytest.mark.parametrize("row", sorted(ROWS))
def test_each_row_of_the_joining_table_is_reached(row):
    c = cards.choose("joining", **ROWS[row])
    assert c["row"] == row
    assert c["because"] and c["runner_up"] != c["choice"] and c["wins_when"]
    assert c["cards"] and all(x.startswith("cad-agent ") for x in c["cards"])


def test_the_rows_cover_the_table_and_every_option():
    dec = cards.decisions()["joining"]
    assert set(ROWS) == {r["id"] for r in dec["rows"]}, "a new row needs an input set in ROWS"
    chosen = {cards.choose("joining", **kw)["choice"] for kw in ROWS.values()}
    assert chosen == set(dec["options"]), "every option is some row's choice"


def test_the_sample_decision_names_the_insert_and_its_margin():
    c = cards.choose("joining", process="fdm", material="petg", load=200, cycles=50)
    assert (c["choice"], c["runner_up"]) == ("heat-set-insert", "through-bolt-nut")
    assert c["detail"]["insert_insert"] == "mcmaster-94459A140", "M3 x 5.7: the M3 x 4.3 holds under 200 N at margin 2"
    assert c["detail"]["insert_allowed_n"] >= 200
    assert any("a few" in g and "no registry source puts a number" in g for g in c["gaps"])
    assert "qty" in c["unused"], "an input no row reads says so"


def test_the_insert_fact_is_none_where_no_model_is():
    assert cards.insert_for_load("sls", "pa12", 100)["fits"] is None
    assert cards.insert_for_load("fdm", None, 100)["fits"] is None
    heavy = cards.insert_for_load("fdm", "pla", 5000)
    assert heavy["fits"] is False and heavy["insert"] == "mcmaster-94459A778"
    c = cards.choose("joining", process="sls", load=100, cycles=4)
    assert c["row"] == "repeated" and any("calibrated on FDM" in g for g in c["gaps"])


def test_choose_refuses_what_it_does_not_cover():
    with pytest.raises(cards.CardError, match="not covered"):
        cards.choose("joining", process="cnc")
    with pytest.raises(cards.CardError, match="takes"):
        cards.choose("joining", torque=3)
    with pytest.raises(cards.CardError, match="no decision"):
        cards.choose("tolerance")
    with pytest.raises(cards.CardError, match="at least 0"):
        cards.choose("joining", load=-1)


# ----------------------------------------------------------------------------- planted defects

def _catalogued(reg):
    return next(r.id for r in reg.of_kind("catalogued"))


def test_planted_defect_a_rule_citing_an_unread_record_is_refused(reg, monkeypatch):
    real = pp.load().rules()
    rule = next(r for r in real if r.id == "fdm-insert-hole-cad-offset-cnckitchen")
    uncited = replace(rule, source=_catalogued(reg))
    assert cards.rule_problems(uncited, reg)
    monkeypatch.setattr(cards, "_rules", lambda path=None: [uncited if r.id == rule.id else r for r in real])
    with pytest.raises(cards.CardError, match="refused"):
        cards.card("insert-hole", process="fdm")
    with pytest.raises(cards.CardError, match="refused"):
        cards.why(rule.id)


def test_planted_defect_a_when_field_citing_an_unread_record_is_refused(reg, monkeypatch):
    real = pp.load().rules()
    rule = next(r for r in real if r.id == "fdm-insert-blind-depth-cnckitchen")
    tag = "[ref" + f":{_catalogued(reg)}]"
    planted = replace(rule, wiggle=f"a snippet says so {tag}", strictness="must-ish")
    monkeypatch.setattr(cards, "_rules", lambda path=None: [planted if r.id == rule.id else r for r in real])
    problems = cards.problems()
    assert any("wiggle cites" in p for p in problems) and any("strictness 'must-ish'" in p for p in problems)
    with pytest.raises(cards.CardError, match="refused"):
        cards.card("insert-hole", process="fdm")


def test_planted_defect_an_uncited_decision_row_is_refused(monkeypatch):
    real = cards.decisions()
    dec = json.loads(json.dumps(real["joining"]))
    dec["rows"][-1]["because"] = ["screws are fine, trust me"]
    dec["rows"][-2]["wins_when"] = "unstated"
    dec["rows"][-2].pop("gap", None)
    monkeypatch.setattr(cards, "decisions", lambda path=None: {"joining": dec})
    problems = cards.decision_problems(dec, cards.registry(), list(cards.card_names()),
                                       [r.id for r in pp.load().rules()])
    assert any("once: because[0] is uncited" in p for p in problems)
    assert any("repeated: wins_when is unstated, so the row needs a `gap`" in p for p in problems)
    with pytest.raises(cards.CardError, match="not cited"):
        cards.choose("joining", process="fdm", material="petg", load=10, cycles=1)


def test_planted_defect_a_malformed_table_is_reported():
    dec = json.loads(json.dumps(cards.decisions()["joining"]))
    dec["rows"].append({"id": "after-the-catch-all", "if": {"cycles": {"min": 9}}, "choose": "glue",
                        "because": ["x [ref:covestro-joining]"], "runner_up": "pem", "wins_when": "unstated"})
    dec["options"]["rivet"] = {"name": "blind rivet", "cards": ["no-such-card"]}
    dec["rows"][0]["if"] = {"process": ["cnc"]}
    problems = cards.decision_problems(dec, cards.registry(), list(cards.card_names()), [])
    for want in ("only the last row may have no `if`", "the last row has no `if`", "choose 'glue' is not an option",
                 "option rivet links card 'no-such-card'", "option rivet is never chosen",
                 "process must be a list of", "rule 'sm-clinch-hardness-margin-pem' is not a rule id"):
        assert any(want in p for p in problems), want


# ----------------------------------------------------------------------------- the command

def test_the_commands_exit_2_with_a_reason(capsys):
    code, _, err = _run(["rules", "insert-hol"], capsys)
    assert code == 2 and "did you mean insert-hole" in err
    code, _, err = _run(["choose", "joining", "--process", "cnc"], capsys)
    assert code == 2 and "not covered" in err
    code, out, _ = _run(["rules"], capsys)
    assert code == 0 and "insert-hole" in out and "printed-hole" in out


def test_json_is_the_same_card(capsys):
    code, out, _ = _run(["rules", "insert-hole", "--process", "fdm", "--material", "petg-cf", "--json"], capsys)
    assert code == 0
    got = json.loads(out)
    assert [ln["rule"] for ln in got["lines"]] == \
        [ln["rule"] for ln in cards.card("insert-hole", process="fdm", material="petg-cf")["lines"]]
    code, out, _ = _run(SAMPLES["choose-joining-fdm-petg-200n-50"] + ["--json"], capsys)
    assert json.loads(out)["choice"] == "heat-set-insert"
