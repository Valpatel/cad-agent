"""cadagent.simulation.explore.design: design files, extends, resolving slots and the bill of materials."""

from __future__ import annotations

import json

import pytest

from cadagent.simulation.explore.catalogue import Catalogue
from cadagent.simulation.explore.config import SlotSpec
from cadagent.simulation.explore.design import (DesignError, bom, bom_checks, bom_metrics, deep_merge, load_design,
                                                resolve)

from .explore_fixtures import CATALOGUE

CAT = Catalogue({it["id"]: {**CATALOGUE["defaults"], **it} for it in CATALOGUE["items"]})
SLOTS = {"fan": SlotSpec("fan", "fan", required=True), "psu": SlotSpec("psu", "psu", group="Power"),
         "screws": SlotSpec("screws", "fastener", qty=4)}


def _design(tmp_path, name, data):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data))
    return path


def test_extends_merges_mappings_replaces_values_and_does_not_inherit_the_name(tmp_path):
    _design(tmp_path, "base", {"name": "Base", "parts": {"fan": "fan-60", "screws": {"part": "m3x8", "qty": 8},
                                                         "seal": "gasket"}, "params": {"a": {"b": 1, "c": 2}}, "notes": "n"})
    _design(tmp_path, "mid", {"extends": "base.json", "parts": {"screws": {"qty": 12}, "seal": None}, "params": {"a": {"c": 3}}})
    _design(tmp_path, "top", {"extends": "mid.json", "name": "Top", "parts": {"fan": "fan-80"}})
    top = load_design(tmp_path / "top.json")
    assert top["name"] == "Top" and "extends" not in top and top["notes"] == "n"
    assert top["parts"] == {"fan": "fan-80", "screws": {"part": "m3x8", "qty": 12}, "seal": None}
    assert top["params"] == {"a": {"b": 1, "c": 3}}
    assert load_design(tmp_path / "mid.json")["name"] == "mid", "the name defaults to the file, not the parent's"
    assert deep_merge({"x": [1]}, {"x": [2]}) == {"x": [2]}


def test_extends_overrides_a_bare_id_slot_and_switches_between_part_and_custom(tmp_path):
    custom = {"name": "Printed fan duct", "category": "fan", "price_usd": 2.0, "price_checked": "2026-10-01", "mass_g": 9}
    _design(tmp_path, "base", {"parts": {"fan": "fan-60", "psu": {"custom": {**custom, "category": "psu"}},
                                         "screws": {"part": "m3x8", "qty": 8}}})
    _design(tmp_path, "two", {"extends": "base.json", "parts": {"fan": {"qty": 2}, "psu": {"part": "psu-30w"},
                                                                "screws": {"custom": {**custom, "category": "fastener"}}}})
    _design(tmp_path, "back", {"extends": "two.json", "parts": {"screws": {"part": "m3x8"}}})
    two = load_design(tmp_path / "two.json")
    assert two["parts"]["fan"] == {"part": "fan-60", "qty": 2}, "a bare id counts as {part: id}"
    assert two["parts"]["psu"] == {"part": "psu-30w"}, "naming part drops the inherited custom part"
    assert two["parts"]["screws"] == {"custom": {**custom, "category": "fastener"}, "qty": 8}, "custom drops part, keeps qty"
    cand, errors, _ = resolve(two, CAT, SLOTS)
    assert errors == [] and cand.qty("fan") == 2 and cand.part("psu")["id"] == "psu-30w" and cand.picks["screws"].custom
    back = load_design(tmp_path / "back.json")
    assert back["parts"]["screws"] == {"part": "m3x8", "qty": 8}
    assert resolve(back, CAT, SLOTS)[1] == []


def test_non_finite_numbers_in_a_part_or_the_design_are_errors():
    cat = Catalogue({**CAT.items, "fan-nan": {**CAT["fan-60"], "id": "fan-nan", "price_usd": float("nan")}})
    cand, errors, _ = resolve({"parts": {"fan": "fan-nan"}}, cat, SLOTS)
    assert cand is None and errors[0] == ("slot fan: part fan-nan has numbers that are not finite (price_usd = nan); "
                                          "cad-agent catalogue reports them")
    cand, errors, _ = resolve({"parts": {"fan": "fan-60"}, "params": {"heat_w": float("inf")}}, CAT, SLOTS)
    assert cand is None and errors == ["design: params.heat_w is inf, not a finite number"]
    cand, errors, _ = resolve({"parts": {"fan": {"custom": {"category": "fan", "mass_g": float("nan")}}}}, CAT, SLOTS)
    assert cand is None and any("mass_g is nan, not a finite number" in e for e in errors)


def test_bad_design_files_raise_design_error(tmp_path):
    _design(tmp_path, "a", {"extends": "b.json"})
    _design(tmp_path, "b", {"extends": "a.json"})
    with pytest.raises(DesignError, match="extends loop: a.json -> b.json -> a.json"):
        load_design(tmp_path / "a.json")
    with pytest.raises(DesignError, match="unreadable"):
        load_design(_design(tmp_path, "c", {"extends": "missing.json"}))
    with pytest.raises(DesignError, match="'parts' must be a mapping"):
        load_design(_design(tmp_path, "d", {"parts": ["fan-60"]}))
    (tmp_path / "e.json").write_text("[1, 2]")
    with pytest.raises(DesignError, match="must be a mapping"):
        load_design(tmp_path / "e.json")


def test_resolve_picks_parts_with_quantities_and_custom_parts():
    design = {"name": "D", "parts": {"fan": "fan-60", "screws": "m3x8", "psu": {"part": "psu-60w", "qty": 2},
                                     "frame": {"custom": {"name": "Frame", "category": "frame", "price_usd": 10,
                                                          "price_checked": "2026-10-01", "mass_g": 400}},
                                     "seal": None}, "params": {"heat_w": 20}}
    cand, errors, checks = resolve(design, CAT, SLOTS, "d")
    assert errors == []
    assert {s: (p.item["id"], p.qty, p.custom) for s, p in cand.picks.items()} == {
        "fan": ("fan-60", 1, False), "screws": ("m3x8", 4, False), "psu": ("psu-60w", 2, False),
        "frame": ("custom-frame", 1, True)}
    assert [c["text"] for c in checks] == ["slot frame is not one of the configured slots",
                                           "slot seal is not one of the configured slots"], "typos in slot names show"
    assert cand.spec("fan", "airflow_cfm") == 18 and cand.spec("fan", "mass_g") == 30 and cand.spec("fan", "price_usd") == 9.0
    assert cand.spec("seal", "x", "none") == "none" and cand.qty("seal") == 0 and cand.param("heat_w") == 20
    req = cand.request()
    assert req["parts"]["psu"]["qty"] == 2 and req["currency"] == "usd" and json.dumps(req)


@pytest.mark.parametrize("parts, fragment", [
    ({"fan": "fan-99"}, "unknown part id 'fan-99'"),
    ({"fan": "psu-30w"}, "slot fan takes category 'fan'; psu-30w is 'psu'"),
    ({"psu": "psu-30w"}, "slot fan is required but empty"),
    ({"fan": {"part": "fan-60", "qty": -1}}, "qty must be a whole number"),
    ({"fan": {"part": "fan-60", "custom": {}}}, "either 'part'"),
    ({"fan": {"part": "fan-60", "count": 2}}, "unknown keys"),
    ({"fan": 7}, "expected a catalogue id"),
    ({"fan": "fan-60", "frame": {"custom": {"name": "Frame", "price_usd": 5}}}, "missing category"),
])
def test_resolve_errors(parts, fragment):
    cand, errors, _ = resolve({"parts": parts}, CAT, SLOTS)
    assert cand is None and any(fragment in e for e in errors), errors


def test_bom_totals_packs_groups_and_honest_flags():
    design = {"parts": {"fan": "fan-60", "psu": "psu-60w", "screws": {"part": "m3x8", "qty": 60}, "seal": "gasket"}}
    cand, _, _ = resolve(design, CAT, SLOTS)
    b = bom(cand, SLOTS, extra_lines=[{"name": "Filament", "qty": 0.25, "price_usd": 20, "mass_g": 1000, "estimate": True}])
    lines = {l["name"]: l for l in b["lines"]}
    assert lines["M3x8 screw"]["packs"] == 2 and lines["M3x8 screw"]["line_price"] == 8.0, "60 screws = two packs of 50"
    assert lines["M3x8 screw"]["line_mass_g"] == pytest.approx(36.0)
    assert lines["Filament"]["line_price"] == 5.0 and lines["Filament"]["from_evaluator"], "a fraction of a bulk unit"
    t = b["totals"]
    assert t["cost"] == pytest.approx(9 + 22 + 8 + 5) and not t["cost_complete"], "the gasket has no price"
    assert t["mass_kg"] == pytest.approx((30 + 260 + 36 + 8 + 250) / 1000) and t["mass_complete"]
    assert t["cost_estimate"] and t["mass_estimate"], "the filament line is an estimate"
    assert t["groups"] == {"": pytest.approx(22.0), "Power": 22.0}
    assert [c["id"] for c in bom_checks(b)] == ["price-seal"]
    m = bom_metrics(b)
    assert m["cost_usd"]["incomplete"] and m["cost_usd"]["unit"] == "USD" and m["mass_kg"]["estimate"]


def test_out_of_stock_parts_are_flagged():
    cat = Catalogue({"f": {"id": "f", "category": "fan", "price_usd": 1, "mass_g": 1,
                           "buy": [{"url": "https://x", "in_stock": False}]}})
    cand, _, _ = resolve({"parts": {"fan": "f"}}, cat)
    checks = bom_checks(bom(cand))
    assert [c["id"] for c in checks] == ["stock-fan"] and bom(cand)["lines"][0]["source"] == "https://x"


def test_slot_choices_and_where_narrow_what_fits():
    from cadagent.simulation.explore.design import candidates, check_slots, fits

    quiet = SlotSpec("fan", "fan", where={"specs.noise_dba": [25, 30]})
    picked = SlotSpec("fan", "fan", choices=["fan-80", "fan-40"])
    assert [it["id"] for it in candidates(CAT, quiet)] == ["fan-60", "fan-40"]
    assert [it["id"] for it in candidates(CAT, picked)] == ["fan-40", "fan-80"], "catalogue order: by price"
    assert fits(CAT["fan-80"], quiet) == "needs specs.noise_dba = [25, 30]; fan-80 has 34"
    assert fits(CAT["fan-60"], picked).startswith("takes only fan-80, fan-40")
    assert fits(CAT["gasket"], SlotSpec("seal", where={"specs.colour": None})) is None, "a missing field counts as null"
    cand, errors, _ = resolve({"parts": {"fan": "fan-80"}}, CAT, {"fan": quiet})
    assert cand is None and errors == ["slot fan needs specs.noise_dba = [25, 30]; fan-80 has 34"]
    only = SlotSpec("x", choices=["psu-30w", "nope"])
    assert [it["id"] for it in candidates(CAT, only)] == ["psu-30w"], "choices alone, without a category"
    issues = check_slots({"x": only, "fan": SlotSpec("fan", "fan", where={"specs.noise_dba": 99}),
                          "frame": SlotSpec("frame", "frame")}, CAT)
    assert [(i.level, i.where, i.text) for i in issues] == [
        ("error", "slot x", "choices not in the catalogue: nope"), ("warn", "slot fan", "no catalogue part fits it")]


def test_extends_changes_a_quantity_whatever_form_the_parent_used(tmp_path):
    _design(tmp_path, "base", {"parts": {"fan": "fan-60", "psu": {"custom": {"name": "PSU", "category": "psu", "mass_g": 9}}}})
    _design(tmp_path, "child", {"extends": "base.json", "parts": {"fan": {"qty": 2}, "psu": {"part": "psu-30w"}}})
    child = load_design(tmp_path / "child.json")
    assert child["parts"] == {"fan": {"part": "fan-60", "qty": 2}, "psu": {"part": "psu-30w"}}, "custom dropped for part"
    cand, errors, _ = resolve(child, CAT, SLOTS)
    assert errors == [] and cand.qty("fan") == 2 and cand.part("psu")["id"] == "psu-30w"
    _design(tmp_path, "back", {"extends": "child.json", "parts": {"psu": {"custom": {"name": "Own", "category": "psu"}}}})
    assert load_design(tmp_path / "back.json")["parts"]["psu"] == {"custom": {"name": "Own", "category": "psu"}}


def test_unquoted_yaml_dates_stay_json(tmp_path):
    from cadagent.simulation.explore.catalogue import load_catalogue
    (tmp_path / "parts.yaml").write_text("- {id: f, category: fan, price_usd: 5, price_checked: 2026-10-20, mass_g: 3}\n")
    (tmp_path / "d.yaml").write_text("parts: {fan: f}\nparams: {built: 2026-10-21}\n")
    cat, issues = load_catalogue([tmp_path / "parts.yaml"])
    assert issues == [] and cat["f"]["price_checked"] == "2026-10-20"
    design = load_design(tmp_path / "d.yaml")
    assert design["params"]["built"] == "2026-10-21" and json.dumps(design)


def test_the_evaluator_gets_copies_of_catalogue_parts():
    cand, _, _ = resolve({"parts": {"fan": "fan-60"}}, CAT, SLOTS)
    cand.part("fan")["specs"]["airflow_cfm"] *= 0.5
    assert CAT["fan-60"]["specs"]["airflow_cfm"] == 18
