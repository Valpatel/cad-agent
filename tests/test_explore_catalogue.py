"""cadagent.explore.catalogue: layouts, loading problems and per-item checks."""

from __future__ import annotations

import json
from datetime import date

import pytest

from cadagent.explore.catalogue import (Catalogue, check_catalogue, check_item, display_name, in_stock, is_estimate,
                                        load_catalogue, load_configured, mass_of, normal_confidence, price_of)
from cadagent.explore.config import explore_config

TODAY = date(2026, 10, 26)
GOOD = {"id": "fan-60", "category": "fan", "name": "60 mm fan", "price_usd": 9.0, "price_checked": "2026-10-01",
        "mass_g": 30, "sources": ["https://example.com/fan"]}


def _write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def _texts(issues, level=None):
    return [i.text for i in issues if level is None or i.level == level]


def test_three_layouts_and_yaml_load_into_one_catalogue(tmp_path):
    a = _write(tmp_path / "a.json", [GOOD])
    b = _write(tmp_path / "b.json", {"defaults": {"category": "psu", "price_checked": "2026-10-01"},
                                     "items": [{"id": "psu-30w", "price_usd": 15}, {"id": "psu-60w", "category": "big"}]})
    c = _write(tmp_path / "c.json", {"items": {"91290A111": {"description": "M3 screw", "category": "fastener"}}})
    d = _write(tmp_path / "d.yaml", "items:\n  - {id: gasket, category: seal, mass_g: 8}\n")
    cat, issues = load_catalogue([a, b, c, d], root=tmp_path)
    assert issues == []
    assert sorted(cat.items) == ["91290A111", "fan-60", "gasket", "psu-30w", "psu-60w"]
    assert cat["psu-30w"]["category"] == "psu" and cat["psu-60w"]["category"] == "big", "defaults sit under items"
    assert cat.files["gasket"] == "d.yaml" and display_name(cat["91290A111"]) == "M3 screw"


def test_loading_problems_are_errors_and_the_first_id_wins(tmp_path):
    good = _write(tmp_path / "good.json", [GOOD])
    dup = _write(tmp_path / "dup.json", [{**GOOD, "name": "other"}, {"category": "fan"}, "not an item"])
    bad = _write(tmp_path / "bad.json", "{not json")
    keyed = _write(tmp_path / "keyed.json", {"items": {"x": {"id": "y", "category": "fan"}}})
    wrong = _write(tmp_path / "wrong.json", {"parts": []})
    cat, issues = load_catalogue([good, dup, bad, keyed, wrong], root=tmp_path)
    text = " | ".join(f"{i.where}: {i.text}" for i in issues)
    assert all(i.level == "error" for i in issues)
    assert "duplicate id (also in good.json)" in text and "missing id" in text and "an item must be a mapping" in text
    assert "unreadable" in text and "differs from its key" in text and "must be a list of items" in text
    assert cat["fan-60"]["name"] == "60 mm fan"


def test_a_good_item_has_no_issues():
    assert check_item(GOOD, "x", today=TODAY) == []


@pytest.mark.parametrize("change, level, fragment", [
    ({"price_checked": None}, "error", "a price needs price_checked"),
    ({"price_checked": "26/10/2026"}, "error", "is not YYYY-MM-DD"),
    ({"price_checked": "2027-01-01"}, "error", "in the future"),
    ({"price_checked": "2026-01-01"}, "warn", "days old"),
    ({"price_usd": -1}, "error", "must be a number ≥ 0"),
    ({"price_usd": True}, "error", "must be a number ≥ 0"),
    ({"price_usd": None, "price_checked": None}, "warn", "left out of cost totals"),
    ({"price_usd": None, "price_eur": 8.0}, "warn", "has price_eur"),
    ({"mass_g": None}, "warn", "no mass_g"),
    ({"specs": {"mass_g": 31}}, "error", "disagree"),
    ({"specs": [1, 2]}, "error", "specs must be a mapping"),
    ({"category": None}, "error", "missing category"),
    ({"id": "bad id/x"}, "error", "may only use"),
    ({"confidence": "a guess"}, "error", "is not one of"),
    ({"estimates": "mass_g"}, "error", "estimates must be a list"),
    ({"preferred": "yes"}, "error", "preferred must be true or false"),
    ({"pack_qty": 0}, "error", "pack_qty must be a whole number"),
    ({"sources": None}, "warn", "cannot be checked"),
])
def test_item_checks(change, level, fragment):
    issues = check_item({**GOOD, **change}, "x", today=TODAY)
    assert any(fragment in i.text for i in issues if i.level == level), [str(i) for i in issues]


def test_categories_and_price_age_are_configurable():
    assert "unknown category 'fan'" in " ".join(_texts(check_item(GOOD, "x", categories=["psu"], today=TODAY)))
    old = {**GOOD, "price_checked": "2025-01-01"}
    assert check_item(old, "x", max_price_age_days=None, today=TODAY) == []
    assert _texts(check_item(old, "x", max_price_age_days=1000, today=TODAY)) == []


def test_reading_values_off_items():
    assert normal_confidence("Product page") == "product_page" and normal_confidence(None) is None
    assert check_item({**GOOD, "confidence": "Seller listing"}, "x", today=TODAY) == []
    assert mass_of({"specs": {"mass_g": 12}}) == 12 and mass_of({"mass_g": "12"}) is None
    assert price_of({"price_eur": 5}, "eur") == 5 and price_of({"price_eur": 5}) is None
    assert is_estimate({"confidence": "estimate"}, "price_usd")
    assert is_estimate({"estimates": ["specs.mass_g"]}, "mass_g") and not is_estimate({"estimates": ["mass_g"]}, "price_usd")
    assert in_stock({"buy": [{"in_stock": False}, {"in_stock": True}]}) is True
    assert in_stock({"buy": [{"in_stock": False}, {"in_stock": False}]}) is False
    assert in_stock({"buy": [{"in_stock": None}]}) is None and in_stock({}) is None


def test_in_category_puts_preferred_first_then_price_with_unpriced_last():
    cat = Catalogue({"a": {"id": "a", "category": "fan", "price_usd": 9}, "b": {"id": "b", "category": "fan"},
                     "c": {"id": "c", "category": "fan", "price_usd": 5}, "d": {"id": "d", "category": "fan", "price_usd": 20,
                                                                                "preferred": True},
                     "e": {"id": "e", "category": "psu", "price_usd": 1}})
    assert [it["id"] for it in cat.in_category("fan")] == ["d", "c", "a", "b"]
    assert cat.categories() == ["fan", "psu"]


def test_check_catalogue_names_the_file(tmp_path):
    f = _write(tmp_path / "parts.json", [{**GOOD, "price_checked": None}])
    cat, _ = load_catalogue([f], root=tmp_path)
    issues = check_catalogue(cat, today=TODAY)
    assert issues and issues[0].where == "parts.json fan-60" and str(issues[0]).startswith("ERROR parts.json fan-60:")


def test_load_configured_reports_patterns_that_match_nothing(tmp_path):
    _write(tmp_path / "parts.json", [GOOD])
    cfg = explore_config(tmp_path, {"catalogue": ["parts.json", "missing/*.json", "nope.json"]})
    cat, issues = load_configured(cfg)
    assert len(cat) == 1
    assert sorted(i.where for i in issues) == ["catalogue pattern 'missing/*.json'", "catalogue pattern 'nope.json'"]
