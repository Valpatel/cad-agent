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
    "choose-joining-sheet-5052": ["choose", "joining", "--process", "sheet-metal", "--material", "5052", "--load", "100"],
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


@pytest.mark.parametrize("feature, rule_id", [
    ("escape-hole", "mjf-escape-hole-hp-cleaning"),
    ("lattice-gap", "mjf-lattice-gap-hp-cleaning"),
])
def test_hp_cleaning_dimensions_reach_the_actual_rule_card(feature, rule_id, capsys):
    # HP 4AA7-4109ENW page 1: both dimensions are 5 mm, for distinct cleaning features.
    rule = pp.profile("mjf").verified_rule(rule_id)
    assert rule.limit().min == 5 and rule.source == "hp-mjf-design-for-cleaning"
    code, out, err = _run(["rules", feature, "--process", "mjf"], capsys)
    assert code == 0, err
    assert rule_id in out and "5 mm" in out and "HP" in out
    moving = cards.render_card(cards.card("clearance", process="mjf"))
    assert rule_id not in moving, "a cleaning opening must not become moving-part clearance"


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
    sheet = cards.card("hole", material="5052")         # no process: an alloy leaves out the printed holes
    assert "fdm" not in {ln["process"] for ln in sheet["lines"]} and "sheet-metal" in {ln["process"] for ln in sheet["lines"]}
    with pytest.raises(cards.CardError, match="not known"):
        cards.card("hole", material="unobtainium")


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
                             [0, 50, 200, 5000], [1, 2, 50], [True, False])
    for process, load, cycles, with_material in grid:
        material = {"fdm": "petg", "sheet-metal": "304"}.get(process) if with_material else None
        c = cards.choose("joining", process=process, material=material, load=load, cycles=cycles)
        assert len(cards.render_choice(c).encode()) <= cards.CARD_BYTES, (process, load, cycles, material)
        assert len(cards.as_json(c).encode()) <= cards.JSON_BYTES, (process, load, cycles, material)
    for r in pp.load().rules():
        if r.verified and not r.shop:
            w = cards.why(r.id)
            assert len(cards.render_why(w).encode()) <= cards.CARD_BYTES, r.id
            assert len(cards.as_json(cards.why_json(w)).encode()) <= cards.JSON_BYTES, r.id


def test_why_json_drops_claims_then_sources_and_names_them():
    w = cards.why("fdm-insert-hole-m3-nominal-cnckitchen")
    full = cards.why_json(w, budget=10 ** 6)
    assert full["more"] == [] and full["sources"] == w["sources"]
    small = cards.why_json(w, budget=1800)
    assert len(cards.as_json(small).encode()) <= 1800
    assert small["more"] and small["sources"][0]["id"] == w["sources"][0]["id"], "the rule's own source stays"
    assert small["rule"] == w["rule"] and small["numbers"] == w["numbers"]


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
    assert c["row"] == row and c["decided"] and not c["missing"]
    assert c["because"] and c["runner_up"] != c["choice"] and c["wins_when"]
    assert (c["cards"] or c["cards_empty"]) and all(x.startswith("cad-agent ") for x in c["cards"])


def test_the_rows_cover_the_table_and_every_option():
    dec = cards.decisions()["joining"]
    assert set(ROWS) == {r["id"] for r in dec["rows"]}, "a new row needs an input set in ROWS"
    chosen = {cards.choose("joining", **kw)["choice"] for kw in ROWS.values()}
    assert chosen == set(dec["options"]), "every option is some row's choice"


def test_the_sample_decision_names_the_insert_and_its_margin():
    c = cards.choose("joining", process="fdm", material="petg", load=200, cycles=50)
    assert (c["choice"], c["runner_up"]) == ("heat-set-insert", "thread-forming-screw"), \
        "a few re-assemblies: the screw put back into its own thread is the sourced runner-up"
    ins = c["detail"]["insert_fits"]
    assert ins["insert"] == "mcmaster-94459A140", "M3 x 5.7: the M3 x 4.3 holds under 200 N at margin 2"
    assert ins["allowed_n"] >= 200 and "fits" not in ins
    assert c["schema"] == cards.DECISION_SCHEMA and set(c["detail"]) <= set(c["facts"])
    assert any("a few" in g and "no registry source puts a number" in g for g in c["gaps"])
    assert "qty" in c["unused"], "an input no row reads says so"


def test_the_insert_fact_is_none_where_no_model_is():
    assert cards.insert_for_load("sls", "pa12", 100)["fits"] is None
    assert cards.insert_for_load("fdm", None, 100)["fits"] is None
    heavy = cards.insert_for_load("fdm", "pla", 5000)
    assert heavy["fits"] is False and heavy["insert"] == "mcmaster-94459A778"
    c = cards.choose("joining", process="sls", load=100, cycles=4)
    assert not c["decided"] and c["choice"] is None and "calibrated on FDM" in c["missing"]["insert_fits"]


# the review of #346: with a load and no capacity model, the table used to pick a screw or an insert unchecked
@pytest.mark.parametrize("kw, row, says", [
    (dict(process="fdm", load=5000, cycles=1), "once", "--material"),
    (dict(process="fdm", load=50, cycles=1), "once", "--material"),
    (dict(process="fdm", load=200, cycles=50), "repeated", "--material"),
    (dict(process="sls", load=5000, cycles=1), "once", "no capacity model for sls"),
    (dict(process="mjf", load=50, cycles=1), "once", "no capacity model for mjf"),
    (dict(process="injection-moulding", load=5000, cycles=10), "repeated", "no capacity model for injection-moulding"),
])
def test_a_load_with_no_capacity_model_is_not_decided(kw, row, says, capsys):
    c = cards.choose("joining", **kw)
    assert (c["decided"], c["choice"], c["row"]) == (False, None, row)
    assert says in c["missing"]["insert_fits"]
    text = cards.render_choice(c)
    assert "choice: not decided" in text and says in text and "screw" not in text and "insert (" not in text
    argv = ["choose", "joining"] + [x for k, v in kw.items() for x in (f"--{k}", str(v))]
    code, out, err = _run(argv, capsys)
    assert code == 0 and "not decided" in out and not err
    assert json.loads(_run(argv + ["--json"], capsys)[1])["decided"] is False


def test_with_a_material_the_same_load_is_checked():
    assert cards.choose("joining", process="fdm", material="petg", load=5000, cycles=1)["choice"] == "through-bolt-nut"
    assert cards.choose("joining", process="fdm", material="petg", load=5000, cycles=50)["choice"] == "through-bolt-nut"


def test_the_screw_row_says_its_own_capacity_is_unchecked():
    c = cards.choose("joining", **ROWS["once"])
    assert c["choice"] == "thread-forming-screw"
    gap = next(g for g in c["gaps"] if "screw's own pull-out is not computed" in g)
    assert "no margin" in gap and "[ref:embedded-inserts]" in gap
    assert f"{c['detail']['insert_fits']['allowed_n']} N allowed" in gap


def test_the_load_is_required_not_assumed(capsys):
    with pytest.raises(cards.CardError, match="needs load"):
        cards.choose("joining", process="fdm", material="petg")
    code, out, err = _run(["choose", "joining"], capsys)
    assert code == 2 and "needs load (--load" in err and not out
    assert cards.choose("joining", process="fdm", load=0)["choice"] == "snap-clip", "an explicit 0 holds closed only"


def test_resin_takes_a_glued_insert_and_says_where_no_rule_is():
    c = cards.choose("joining", **ROWS["resin"])
    assert c["choice"] == "glued-insert" and "glued" in c["choice_name"] and "heat-set" not in c["choice_name"]
    assert "insert-install" not in c["cards_empty"] + c["cards"], "the iron-set card is not a resin card"
    assert c["cards"] == [] and c["cards_empty"] == ["insert-hole", "insert-boss"]
    assert "insert-hole, insert-boss: no verified rule for sla yet" in cards.render_choice(c)
    for kw in ROWS.values():                 # every command a card prints returns a card with rules
        c = cards.choose("joining", **kw)
        for cmd in c["cards"] + c["runner_up_cards"]:
            parts = cmd.split()
            if parts[1] == "rules":
                p = parts[parts.index("--process") + 1]
                m = parts[parts.index("--material") + 1] if "--material" in parts else None
                assert cards.card(parts[2], process=p, material=m)["lines"], cmd


def test_a_not_computed_gap_shows_only_where_a_row_reads_the_fact():
    sheet = cards.choose("joining", **ROWS["sheet"])
    assert not any("not computed" in g for g in sheet["gaps"])
    clip = cards.choose("joining", process="fdm", load=0, cycles=1)
    assert clip["row"] == "clip-once" and not any("not computed" in g for g in clip["gaps"])
    assert sheet["facts"]["insert_fits"] is None and "insert_fits" in sheet["detail"], "the JSON still carries it"


def test_the_folded_reasons_have_no_broken_words():
    for kw in ROWS.values():
        c = cards.choose("joining", **kw)
        for text in c["because"] + c["gaps"] + [c["wins_when"]]:
            assert "- " not in text.replace(" - ", " "), text


def test_choose_refuses_what_it_does_not_cover():
    with pytest.raises(cards.CardError, match="not covered"):
        cards.choose("joining", process="cnc")
    with pytest.raises(cards.CardError, match="takes"):
        cards.choose("joining", torque=3)
    with pytest.raises(cards.CardError, match="no decision"):
        cards.choose("tolerance")
    with pytest.raises(cards.CardError, match="at least 0"):
        cards.choose("joining", load=-1)


@pytest.mark.parametrize("field", ["load", "cycles", "qty"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_choose_refuses_nonfinite_numeric_inputs(field, value):
    values = {**ROWS["repeated"], field: value}
    with pytest.raises(cards.CardError, match=rf"{field} must be a finite number"):
        cards.choose("joining", **values)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_cli_load_is_an_error_not_a_decision_or_json(value, capsys):
    code, out, err = _run(["choose", "joining", f"--load={value}", "--material", "petg", "--json"], capsys)
    assert code == 2 and not out
    assert "load must be a finite number" in err


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
    dec["rows"][0]["needs"] = ["insert_capacity"]
    dec["rows"][1]["gap"] = "see {insert_why} and {torque}"
    dec["inputs"]["load"]["default"] = 0
    problems = cards.decision_problems(dec, cards.registry(), list(cards.card_names()), [])
    for want in ("only the last row may have no `if`", "the last row has no `if`", "choose 'glue' is not an option",
                 "option rivet links card 'no-such-card'", "option rivet is never chosen",
                 "process must be a list of", "rule 'sm-clinch-hardness-margin-pem' is not a rule id",
                 "needs 'insert_capacity', which is not a fact", "fills {insert_why}, which is not",
                 "fills {torque}, which is not", "input load is required and has a default"):
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
    # Python otherwise accepts NaN and Infinity extensions that strict JSON consumers refuse.
    strict = lambda text: json.loads(text, parse_constant=lambda token: pytest.fail(f"nonstandard JSON: {token}"))
    code, out, _ = _run(["rules", "insert-hole", "--process", "fdm", "--material", "petg-cf", "--json"], capsys)
    assert code == 0
    got = strict(out)
    assert [ln["rule"] for ln in got["lines"]] == \
        [ln["rule"] for ln in cards.card("insert-hole", process="fdm", material="petg-cf")["lines"]]
    code, out, _ = _run(SAMPLES["choose-joining-fdm-petg-200n-50"] + ["--json"], capsys)
    assert code == 0 and strict(out)["choice"] == "heat-set-insert"


def test_pem_micro_standoff_worked_shield_screen_and_tolerance_controls():
    """CE printed pp.12/19: distinguish cold-flow and flaring standard M2 geometry.

    This screens dimensional intervals only; it does not produce a strength or
    installation pass. The same nominal part can fail when its tolerance grows.
    """
    profile = pp.profile("sheet-metal")

    def rejected(family, dimensions):
        failures = set()
        for feature, (actual_min, actual_max) in dimensions.items():
            limit = profile.verified_rule(f"sm-pem-{family}-m2-{feature}").limit()
            if ((limit.min is not None and actual_min < limit.min)
                    or (limit.max is not None and actual_max > limit.max)):
                failures.add(feature)
        return failures

    shield = dict(sheet=(0.23, 0.27), hole=(3.51, 3.53), edge=(2.45, 2.55))
    assert rejected("mso4", shield) == {"sheet", "hole", "edge"}
    assert rejected("msofs", shield) == set()  # candidate geometry, still unqualified
    assert rejected("msofs", {**shield, "sheet": (0.19, 0.31)}) == {"sheet"}
    assert rejected("msofs", {**shield, "hole": (3.49, 3.56)}) == {"hole"}
    assert rejected("msofs", {**shield, "edge": (1.99, 2.09)}) == {"edge"}
    # Correct clinch geometry does not become flaring geometry by sharing M2.
    clinch = dict(sheet=(0.31, 0.35), hole=(3.19, 3.21), edge=(3.05, 3.15))
    assert rejected("mso4", clinch) == set()
    assert rejected("msofs", clinch) == {"sheet", "hole"}


def test_pem_cards_keep_families_and_printed_materials_separate():
    for family in ("mso4", "msofs"):
        name = f"pem-{family}-m2"
        card = cards.card(name, process="sheet-metal")
        rendered = cards.render_card(card)
        canonical = "pem-consumer-electronics-design-guide-2021"
        # The short display key must still identify this exact read manufacturer source.
        emitted = cards.REF.findall(rendered)
        assert emitted == ["pem-ce-guide-2021"] * 3
        reg = cards.registry()
        assert all(reg.resolve(key).id == canonical and reg.resolve(key).kind == "source" for key in emitted)
        assert reg.resolve(emitted[0]).data["evidence"]["class"] == "read"
        assert {row["rule"] for row in card["lines"]} == {
            f"sm-pem-{family}-m2-{feature}" for feature in ("sheet", "hole", "edge")
        }
        assert len(card["lines"]) == 3
        assert all(row["source"] == canonical and row["confidence"] == "low" for row in card["lines"])
        assert rendered.count("conf low") == 3 and "geometry screening only" in rendered
        assert f"sm-pem-{'msofs' if family == 'mso4' else 'mso4'}" not in rendered
        # A process filter must not publish these sheet dimensions as FDM rules.
        polymer = cards.card(name, process="fdm", material="petg")
        assert "sm-pem-" not in cards.render_card(polymer)


def test_plastic_screw_family_guidance_does_not_supply_a_missing_joint_rating(capsys):
    """A family preference is not a capacity model: apply the same 10 N case to four processes."""
    source = "bossard-fastening-technology-self-tapping-screws-for-plastic"
    for material in ("abs", "thermoset"):
        code, out, err = _run(["choose", "joining", "--process", "injection-moulding", "--material", material,
                               "--load", "10", "--cycles", "1", "--json"], capsys)
        assert code == 0 and not err
        result = json.loads(out)
        assert result["choice"] is None and not result["decided"]
        assert result["facts"]["insert_fits"] is None
        assert "no capacity model for injection-moulding" in result["missing"]["insert_fits"]

    sla = cards.choose("joining", process="sla", material="resin", load=10, cycles=1)
    assert sla["choice"] == "glued-insert" and sla["facts"]["insert_fits"] is None
    assert any("load is not checked" in gap for gap in sla["gaps"])
    assert source not in cards.render_choice(sla), "general thermoset advice does not authorize cutting a brittle SLA part"

    pla = cards.choose("joining", process="fdm", material="pla", load=10, cycles=1)
    assert pla["choice"] == "thread-forming-screw"
    text = cards.render_choice(pla)
    assert f"[ref:{source}]" in text and "forming generally suits thermoplastics, cutting thermosets" in text
    assert "screw's own pull-out is not computed" in text and "insert's capacity" in text
    assert "no printed-joint capacity or wall dimension" in text
    assert not any(rule.source == source for rule in pp.load().rules()), "a qualitative article cannot create numerical rules"
