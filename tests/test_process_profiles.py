"""research/process-profiles.yaml: every rule is sourced, has units and a value that evaluates, every source it cites
is credited with an https link, and the page and charts stay in step with the data (#99, #118).

The sources themselves are entries of the reference registry, research/references.yaml (#163 moved them there);
tests/test_references.py checks the registry's fields. Here: the entries this file and its page use."""
import datetime as dt
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research" / "process-profiles.yaml"
REGISTRY = ROOT / "research" / "references.yaml"
PAGE = ROOT / "research" / "process-profiles.md"
# Sample values for every variable, so each expression can be evaluated; two sets catch thickness-stepped rules.
ENVS = [dict(T=1.5, R=1.5, wall=2.5, D=4.0, L=50.0, depth=12.0, width=6.0, H=8.0, nozzle=0.4, rib=1.5, texture=0.05, area=36.0),
        dict(T=0.6, R=0.4, wall=1.2, D=3.0, L=150.0, depth=3.0, width=2.0, H=3.0, nozzle=0.25, rib=0.6, texture=0.0, area=4.0)]


def _figures():
    spec = importlib.util.spec_from_file_location("process_profile_figures", ROOT / "tools" / "process_profile_figures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data():
    """The profiles, with ``sources``: the registry entries this file or its page relies on (their ``used_for``)."""
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    data["registry"] = {s["id"]: s for s in registry["sources"]}
    data["sources"] = [s for s in registry["sources"]
                       if {"research/process-profiles.yaml", "research/process-profiles.md"} & set(s["used_for"])]
    return data


def _date(text) -> dt.date:
    return dt.date.fromisoformat(str(text)[:10])


def test_the_file_parses_with_the_expected_sections(data):
    assert data["schema"] == 1
    for key in ("units", "variables", "processes", "datasets", "formulas", "rules", "shop_tables"):
        assert data[key], key
    assert "standards" not in data and "sources" not in yaml.safe_load(DATA.read_text(encoding="utf-8")), \
        "sources and standards live in research/references.yaml"
    assert len(data["rules"]) >= 100 and len(data["sources"]) >= 20


def test_ids_are_unique_and_kebab_case(data):
    for kind in ("rules", "datasets", "formulas", "shop_tables"):
        ids = [x["id"] for x in data[kind]]
        assert len(ids) == len(set(ids)), f"duplicate {kind} ids: {sorted(i for i in ids if ids.count(i) > 1)}"
        bad = [i for i in ids if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", i)]
        assert not bad, f"{kind} ids not kebab-case: {bad}"


def test_every_source_is_credited_with_an_https_link(data):
    """The page links each source, so each needs a URL (the registry also allows a book's ISBN alone)."""
    for s in data["sources"]:
        assert str(s.get("url", "")).startswith("https://"), f"{s['id']}: {s.get('url')} is not https"
        assert isinstance(s["authors"], list) and s["org"].strip(), s["id"]


def test_every_rule_has_a_source_units_a_value_and_a_date(data):
    sources = set(data["registry"])
    datasets = {d["id"] for d in data["datasets"]}
    for r in data["rules"]:
        rid = r["id"]
        for field in ("process", "feature", "quantity", "units", "applies", "source", "status", "verified"):
            assert r.get(field) not in (None, ""), f"{rid}: no {field}"
        assert r["process"] in data["processes"], f"{rid}: process {r['process']!r}"
        assert r["units"] in data["units"], f"{rid}: units {r['units']!r} not in the units list"
        src = r["source"]
        if src.startswith("dataset:"):
            assert src.split(":", 1)[1] in datasets, f"{rid}: unknown dataset {src}"
        else:
            assert src in sources, f"{rid}: unknown source {src}"
        assert r["status"] in ("read", "u"), f"{rid}: status {r['status']!r}"
        assert _date(r["verified"]) <= dt.date.today(), rid
        assert {"min", "max", "value"} & set(r), f"{rid}: no min, max or value"
        assert not ("value" in r and ({"min", "max"} & set(r))), f"{rid}: value together with min/max"
        assert "window" not in r or (r["window"] is True and {"min", "max"} <= set(r)), \
            f"{rid}: window is true, and only on a rule with both min and max"
        assert rid.startswith({"injection-moulding": "im", "sheet-metal": "sm"}.get(r["process"], r["process"]) + "-"), \
            f"{rid}: id should start with its process"


def test_every_expression_evaluates_and_ranges_are_ordered(data):
    evaluate = _figures().evaluate
    for r in data["rules"]:
        for env in ENVS:
            got = {k: evaluate(r[k], env) for k in ("min", "max", "value") if k in r}
            assert all(v == v and abs(v) < 1e6 for v in got.values()), r["id"]
            if "min" in got and "max" in got:
                assert got["min"] <= got["max"], f"{r['id']}: min {got['min']} > max {got['max']} at {env}"
            if r["units"] in ("mm", "count"):
                assert all(v >= 0 for v in got.values()), f"{r['id']}: a negative length"


def test_rules_that_compare_share_their_units(data):
    """A compare key sets rules side by side, so 45° must never be weighed against 3 mm."""
    units = {}
    for r in data["rules"]:
        if "compare" in r:
            units.setdefault(r["compare"], {}).setdefault(r["units"], []).append(r["id"])
    mixed = {key: by_unit for key, by_unit in units.items() if len(by_unit) > 1}
    assert not mixed, f"compare keys with more than one unit: {mixed}"


def test_every_source_is_used(data):
    used = {r["source"] for r in data["rules"]} | {f["source"] for f in data["formulas"]} | \
        {t["source"] for t in data["shop_tables"]}
    # A source the page cites for prose only (its used_for leaves out this file) need not back a rule.
    unused = [s["id"] for s in data["sources"] if s["id"] not in used and "research/process-profiles.yaml" in s["used_for"]]
    missing = sorted(i for i in used if not i.startswith("dataset:")
                     and "research/process-profiles.yaml" not in data["registry"][i]["used_for"])
    assert not missing, f"registry entries cited here without this file in their used_for: {missing}"
    assert not unused, f"sources no rule cites: {unused}"


def test_standards_are_cited_by_number_and_title_only(data):
    standards = [s for s in data["sources"] if s["access"] == "paid"]
    assert {"iso-2768-1", "iso-20457", "din-16742", "iso-astm-52910", "iso-astm-52911-2"} <= {s["id"] for s in standards}
    for s in standards:
        assert "by number and title only" in s["terms"], s["id"]
        assert _date(s["verified"]) <= dt.date.today(), s["id"]
    cited = {r["source"] for r in data["rules"]}
    assert not cited & {s["id"] for s in standards}, "a rule takes a value from a paid standard nobody read"


def test_the_shop_table_converts_inches_exactly(data):
    for table in data["shop_tables"]:
        assert table["source"] in data["registry"]
        cols = table["columns"]
        for row in table["rows"]:
            assert len(row) == len(cols), row
            inches = table["as_printed"][row[0]]
            for col, value in inches.items():
                assert row[cols.index(col)] == pytest.approx(round(value * 25.4, 3), abs=1e-9), (row[0], col)


def test_a_rule_printed_in_inches_converts_or_says_why_not(data):
    """Where `as_printed` is one inch value, the rule's number is its conversion (within the 3 % that sources round
    to), or `applies` gives the exact conversion, so an inch slip in a source is flagged and not silently taken."""
    one_inch_value = re.compile(r"±?(\d*\.?\d+) in")
    checked = 0
    for r in data["rules"]:
        m = one_inch_value.fullmatch(str(r.get("as_printed", "")).strip())
        numbers = [r[k] for k in ("min", "max", "value") if isinstance(r.get(k), (int, float))]
        if not m or len(numbers) != 1:
            continue
        checked += 1
        exact = float(m.group(1)) * 25.4
        if abs(numbers[0] - exact) > 0.03 * exact:
            assert f"{round(exact, 3):g} mm" in r["applies"], \
                f"{r['id']}: {numbers[0]} mm is not {r['as_printed']} ({exact:.3f} mm); say so in applies"
    assert checked >= 20


def test_the_evaluator_refuses_anything_but_arithmetic():
    evaluate = _figures().evaluate
    assert evaluate("2*T + R", {"T": 1.5, "R": 1.5}) == pytest.approx(4.5)
    assert evaluate("max(0.005*L, 0.5)", {"L": 200}) == pytest.approx(1.0)
    assert evaluate("1.574 if T <= 0.914 else 3.175", {"T": 1.0}) == pytest.approx(3.175)
    assert evaluate(0.8, {}) == 0.8
    for bad in ("__import__('os')", "T**2", "foo", "T.real", "[T]", "lambda: 1", "min()", "True", "'a'",
                "1 if T < 1 else (2 if T < 2 else 3)", "max(1 if T < 1 else 2, 3 if T > 2 else 4)", "T/(T-T)"):
        with pytest.raises(ValueError):
            evaluate(bad, {"T": 1.0})


def test_committed_charts_match_the_data():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "process_profile_figures.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_page_shows_the_charts_and_links_every_source(data):
    page = PAGE.read_text(encoding="utf-8")
    for name in _figures().FIGURES:
        assert f"docs/img/research/{name}" in page, f"{name} is not on the page"
    missing = [s["id"] for s in data["sources"] if s["url"] not in page]
    assert not missing, f"sources not linked from research/process-profiles.md: {missing}"
    named = [a for s in data["sources"] for a in s["authors"] if a not in page]
    assert not named, f"people the page does not name: {named}"
