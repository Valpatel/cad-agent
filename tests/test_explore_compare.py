"""cadagent.simulation.explore.compare and page: Pareto ranking, swaps, the JSON, the HTML page and the site's design
cards."""

from __future__ import annotations

import json

import pytest

from cadagent.simulation.explore.compare import (anchor, compare_designs, comparison, dominates, pareto_ranks, rank,
                                                 site_cards, swap_options, swaps, with_part, write_comparison)
from cadagent.simulation.explore.config import Objective
from cadagent.simulation.explore.design import load_design
from cadagent.simulation.explore.evaluate import evaluate_design, load_evaluator
from cadagent.simulation.explore.page import render_page

from .explore_fixtures import enclosure_config, restore_sys_path, write_enclosure  # noqa: F401 (a fixture)

pytestmark = pytest.mark.usefixtures("restore_sys_path")
OBJ = [Objective("cost", "min"), Objective("runtime", "max")]


def _ev(name, cost, runtime, verdict="ok", fails=0):
    return {"id": name, "name": name, "verdict": verdict, "counts": {"ok": 0, "warn": 0, "fail": fails},
            "metrics": {"cost": {"value": cost}, "runtime": {"value": runtime}}}


def test_dominance_and_pareto_ranks():
    assert dominates((1, 1), (1, 2)) and not dominates((1, 2), (2, 1)) and not dominates((1, 1), (1, 1))
    assert pareto_ranks([(1, 5), (2, 4), (3, 3), (2, 5), (4, 4), (5, 5)]) == [1, 1, 1, 2, 2, 3]
    assert pareto_ranks([]) == []


def test_rank_orders_fronts_then_infeasible_designs():
    evs = [_ev("pricey", 900, 120), _ev("cheap", 100, 30), _ev("mid", 400, 90), _ev("worse", 500, 80),
           _ev("twin", 100, 30), _ev("broken", 50, 500, "fail", 2), _ev("crash", None, None, "error", 1),
           _ev("nearly", 60, 400, "fail", 1)]
    out = rank(evs, OBJ)
    assert [e["name"] for e in out] == ["cheap", "twin", "mid", "pricey", "worse", "nearly", "broken", "crash"]
    assert [e["rank"] for e in out] == [1, 1, 1, 1, 2, None, None, None]
    assert [e["pareto"] for e in out][:5] == [True, True, True, True, False] and not out[5]["feasible"]
    assert "rank" not in evs[0], "the input is not changed"
    again = rank([dict(e, verdict="fail") if e["name"] == "cheap" else e for e in out], OBJ)
    cheap = next(e for e in again if e["name"] == "cheap")
    assert cheap["rank"] is None and not cheap["pareto"], "re-ranking drops a rank that no longer holds"


def _compare(root, files=None, swaps_too=False):
    cfg, cat = enclosure_config(root)
    fn = load_evaluator(cfg.evaluator, root)
    return cfg, cat, fn, compare_designs(cfg, cat, fn, files, with_swaps=swaps_too)


def test_compare_designs_ranks_the_project(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "designs" / "broken.json").write_text("{")
    cfg, cat, fn, comp = _compare(root, sorted((root / "designs").glob("*.json")))
    by = {d["id"]: d for d in comp["designs"]}
    assert comp["schema"] == "cad-agent/explore-comparison/1" and comp["kind"] == "designs"
    assert comp["summary"] == {"designs": 4, "feasible": 2, "pareto": 2, "errors": 1}
    assert by["base"]["pareto"] and by["quiet"]["pareto"], "quiet is cheaper, base runs cooler"
    assert by["hot"]["verdict"] == "fail" and by["hot"]["rank"] is None
    assert by["broken"]["verdict"] == "error" and "unreadable" in by["broken"]["errors"][0]
    assert list(comp["metrics"])[:3] == ["cost_usd", "temp_rise_c", "mass_kg"], "objectives first, then cost and mass"
    assert comp["metrics"]["cost_usd"]["digits"] == 1 and comp["metrics"]["noise_dba"]["digits"] == 0
    assert comp["evaluator"] == "tools/evaluate.py:evaluate"
    json.dumps(comp)


def test_swaps_try_every_other_part_of_the_slot_category(tmp_path):
    root = write_enclosure(tmp_path)
    cfg, cat, fn, _ = _compare(root)
    design = load_design(root / "designs" / "base.json")
    assert swap_options(design, cat, cfg) == [("fan", "fan-40"), ("fan", "fan-80"), ("psu", "psu-30w")]
    assert with_part(design, "screws", "m3x8")["parts"]["screws"] == {"part": "m3x8", "qty": 8}, "the quantity stays"
    base = evaluate_design(design, cat, cfg, fn, "base")
    out = {s["to"]: s for s in swaps(design, base, cat, cfg, fn)}
    assert out["fan-40"]["better"] == ["cost_usd"] and out["fan-40"]["worse"] == ["temp_rise_c"]
    assert out["fan-40"]["delta"]["cost_usd"] == pytest.approx(-3.0) and out["fan-40"]["feasible"]
    assert not out["fan-80"]["feasible"] and "above the maximum 32" in out["fan-80"]["problems"][0]
    assert out["psu-30w"]["dominates"], "cheaper and as cool: better on every objective"
    assert [s["to"] for s in swaps(design, base, cat, cfg, fn)][0] == "psu-30w", "dominating swaps come first"
    assert swaps(design, base, cat, cfg, fn, workers=3) == swaps(design, base, cat, cfg, fn), "threads change nothing"


def test_write_comparison_writes_json_page_and_site_cards(tmp_path):
    root = write_enclosure(tmp_path)
    cfg, cat, fn, comp = _compare(root, swaps_too=True)
    written = write_comparison(comp, cfg.out, cfg=cfg)
    assert json.loads(written["json"].read_text())["summary"]["designs"] == 3
    page = written["html"].read_text()
    assert page.startswith("<!doctype html>") and "<svg" in page and 'id="d-base"' in page and "One-part swaps" in page
    assert "prefers-color-scheme:dark" in page and "http" not in page.split("<body>")[0], "no external files"
    cards = json.loads(written["cards"].read_text())["designs"]
    base = next(c for c in cards if c["name"] == "Base")
    assert base["link"] == "exports/explore/compare.html#d-base" and base["verdict"] == "warn"
    assert base["metrics"][0]["label"] == "cost" and base["metrics"][0]["value"] == "≥ 38.5"
    assert {"label": "Pareto front", "level": "done", "title": "No feasible design beats it on every objective"} in base["badges"]
    assert sorted(cards[0]) == ["badges", "checks", "file", "link", "metrics", "name", "summary", "verdict"]


def test_site_shows_the_cards(tmp_path):
    pytest.importorskip("markdown")
    from cadagent.publish.site import build_site
    root = write_enclosure(tmp_path)
    cfg, cat, fn, comp = _compare(root)
    write_comparison(comp, cfg.out, cfg=cfg)
    s = build_site(root, {"designs": "exports/explore/designs.json"}, "Enclosure")
    index = (root / "site" / "index.html").read_text()
    assert s["designs"] == 3 and "Quiet" in index and "Pareto front" in index
    assert 'href="../exports/explore/compare.html#d-quiet"' in index


def test_the_page_escapes_names_and_handles_edge_cases(tmp_path):
    root = write_enclosure(tmp_path)
    cfg, cat, fn, comp = _compare(root)
    comp["designs"][0]["name"] = '<script>alert("x")</script>'
    page = render_page(comp)
    assert "<script>alert" not in page and "&lt;script&gt;alert" in page
    empty = comparison([], cfg)
    assert "0 designs" in render_page(empty) and "<svg" not in render_page(empty)
    cfg.objectives = cfg.objectives[:1]
    one = comparison(comp["designs"], cfg)
    assert "<svg" not in render_page(one), "a trade-off chart needs two objectives"
    assert anchor("a b/c~d=e") == "d-a-b-c-d-e" and anchor("") == "d-design"


def test_only_http_sources_become_links(tmp_path):
    root = write_enclosure(tmp_path)
    data = json.loads((root / "catalogue" / "parts.json").read_text())
    data["items"][0]["sources"] = ["javascript:alert(document.domain)"]                      # fan-40
    data["items"][3]["buy"] = [{"seller": "x", "url": "JavaScript:alert(1)", "in_stock": True}]   # psu-30w
    (root / "catalogue" / "parts.json").write_text(json.dumps(data))
    cfg, cat, fn, comp = _compare(root, swaps_too=True)
    page = render_page(comp)
    assert 'href="javascript' not in page.lower() and "source: javascript:alert(document.domain)" in page
    assert '<a href="https://example.com/datasheet" rel="noopener noreferrer">source</a>' in page


def test_non_finite_numbers_never_reach_the_ranking_or_the_json(tmp_path):
    root = write_enclosure(tmp_path, evaluator=(
        "def evaluate(c):\n"
        "    shell = float('nan') if c.param('nan_line') else 3.0\n"
        "    return {'metrics': {'temp_rise_c': 1.0, 'noise_dba': 20},\n"
        "            'lines': [{'name': 'Shell', 'price_usd': shell, 'mass_g': 10}]}\n"))
    data = json.loads((root / "catalogue" / "parts.json").read_text())
    data["items"].append({"id": "fan-nan", "category": "fan", "name": "NaN fan", "price_usd": float("nan"), "mass_g": 5})
    (root / "catalogue" / "parts.json").write_text(json.dumps(data))          # Python's json writes and reads NaN
    (root / "designs" / "nanpart.json").write_text(json.dumps({"extends": "base.json", "name": "NaN part",
                                                               "parts": {"fan": "fan-nan"}}))
    (root / "designs" / "nanline.json").write_text(json.dumps({"extends": "base.json", "name": "NaN line",
                                                               "params": {"nan_line": True}}))
    files = [root / "designs" / f"{n}.json" for n in ("base", "nanpart", "nanline")]
    cfg, cat, fn, comp = _compare(root, files)
    by = {d["name"]: d for d in comp["designs"]}
    assert by["NaN part"]["verdict"] == "error" and "part fan-nan has numbers that are not finite" in by["NaN part"]["errors"][0]
    assert by["NaN line"]["verdict"] == "error" and "nan at lines[0].price_usd" in by["NaN line"]["errors"][0]
    assert comp["summary"]["pareto"] == 1 and by["Base"]["pareto"], "a NaN cost cannot sit on the front"
    written = write_comparison(comp, cfg.out, cfg=cfg)
    text = written["json"].read_text()

    def strict(constant):
        raise AssertionError(f"{constant} in comparison.json")
    assert json.loads(text, parse_constant=strict)["summary"]["errors"] == 2
    comp["designs"][0]["metrics"]["cost_usd"]["value"] = float("nan")       # a regression fails loudly, not silently
    with pytest.raises(ValueError):
        write_comparison(comp, cfg.out, cfg=cfg)


def test_site_cards_mark_errors_and_ranks(tmp_path):
    cfg, _ = enclosure_config(write_enclosure(tmp_path))
    cfg.objectives = OBJ
    comp = comparison([_ev("a", 1, 9), _ev("b", 2, 8), _ev("c", None, None, "error")], cfg)
    cards = {c["name"]: c for c in site_cards(comp, cfg, "x.html")["designs"]}
    assert cards["b"]["badges"][0]["label"] == "front 2"
    assert cards["c"]["verdict"] == "fail" and cards["c"]["badges"][0]["label"] == "error"


def test_swaps_and_search_respect_narrowed_slots(tmp_path):
    from cadagent.simulation.explore.optimise import search_config
    from cadagent.project import CadConfigError

    root = write_enclosure(tmp_path)
    cfg, cat = enclosure_config(root)
    cfg.slots["fan"].where = {"specs.noise_dba": [25, 30]}
    design = load_design(root / "designs" / "base.json")
    assert swap_options(design, cat, cfg) == [("fan", "fan-40"), ("psu", "psu-30w")], "the loud fan does not fit"
    assert [d.choices for d in search_config(cfg, cat).space][0] == ["fan-60", "fan-40"]
    cfg.search["space"] = [{"slot": "fan", "choices": ["fan-40", "fan-80"]}]
    with pytest.raises(CadConfigError, match="do not fit slot fan: fan-80"):
        search_config(cfg, cat)


def test_the_site_top_bar_lists_the_comparison(tmp_path):
    from cadagent.publish import site

    root = write_enclosure(tmp_path)
    cfg, cat, fn, comp = _compare(root)
    write_comparison(comp, cfg.out, cfg=cfg)
    nav = site.default_nav(root)
    assert {"id": "exports/explore/compare.html", "title": "Design comparison", "href": "exports/explore/compare.html"} in nav


def test_tick_labels_and_links_on_the_page():
    from cadagent.simulation.explore.catalogue import link_url
    from cadagent.simulation.explore.page import _nice_ticks, _tick_label

    lo, hi, ticks = _nice_ticks(1, 12)
    assert [_tick_label(t, ticks[1] - ticks[0]) for t in ticks] == ["0", "2.5", "5", "7.5", "10", "12.5"]
    lo, hi, ticks = _nice_ticks(1000, 12000)
    assert [_tick_label(t, ticks[1] - ticks[0]) for t in ticks] == ["0", "2.5K", "5K", "7.5K", "10K", "12.5K"]
    assert [_tick_label(t, 0.25) for t in (0.25, 0.5, 1.0)] == ["0.25", "0.5", "1"]
    assert link_url("javascript:alert(1)") is None and link_url("JavaScript:x") is None
    assert link_url("https://example.com/a") == "https://example.com/a"


def test_a_javascript_source_is_shown_as_text(tmp_path):
    root = write_enclosure(tmp_path)
    cat_file = root / "catalogue" / "parts.json"
    data = json.loads(cat_file.read_text())
    data["items"][1]["sources"] = ["javascript:alert(document.domain)"]
    cat_file.write_text(json.dumps(data))
    cfg, cat, fn, comp = _compare(root)
    page = render_page(comp)
    assert 'href="javascript:' not in page and "source: javascript:alert(document.domain)" in page


def test_design_ids_are_never_absolute_and_never_clash(tmp_path):
    from cadagent.simulation.explore.compare import design_ids

    root = tmp_path / "root"
    paths = [root / "a" / "v.json", root / "b" / "v.json", tmp_path / "elsewhere" / "v.json", root / "w.json"]
    ids = design_ids(paths, root)
    assert ids[:2] == ["a/v", "b/v"] and ids[3] == "w" and ids[2].startswith("v-") and "/" not in ids[2]
    two = design_ids([tmp_path / "x" / "v.json", tmp_path / "y" / "v.json"], root)
    assert len(set(two)) == 2 and all(i.startswith("v-") for i in two)


def test_a_part_without_a_price_never_reads_as_a_saving(tmp_path):
    """The reviewer's case: a supply identical to psu-60w but with no price."""
    from cadagent.simulation.explore.config import Constraint

    root = write_enclosure(tmp_path)
    cat_file = root / "catalogue" / "parts.json"
    data = json.loads(cat_file.read_text())
    data["items"].append({"id": "psu-60w-oem", "category": "psu", "name": "60 W supply (OEM)", "price_usd": None,
                          "mass_g": 260, "specs": {"power_w": 60}})
    cat_file.write_text(json.dumps(data))
    (root / "designs" / "oem.json").write_text(json.dumps({"extends": "base.json", "name": "OEM", "parts": {"psu": "psu-60w-oem"}}))
    cfg, cat, fn, comp = _compare(root)
    by = {d["id"]: d for d in comp["designs"]}
    assert by["base"]["pareto"] and by["quiet"]["pareto"], "the unpriced supply does not push the others off the front"
    assert by["oem"]["lower_bounds"] == ["cost_usd"]
    design = load_design(root / "designs" / "base.json")
    swap = next(s for s in swaps(design, by["base"], cat, cfg, fn) if s["to"] == "psu-60w-oem")
    assert swap["delta"]["cost_usd"] == pytest.approx(-22.0) and "cost_usd" in swap["unsure"]
    assert not swap["dominates"] and "cost_usd" not in swap["better"]
    fan = next(s for s in swaps(design, by["base"], cat, cfg, fn) if s["to"] == "fan-40")
    assert fan["better"] == ["cost_usd"], "both leave out the same gasket: the saving is exact"
    cfg.constraints.append(Constraint("cost_usd", max=20))
    ev = evaluate_design(load_design(root / "designs" / "oem.json"), cat, cfg, fn, "oem")
    check = next(c for c in ev["checks"] if c["id"] == "constraint-cost_usd")
    assert check["level"] == "warn" and "cannot confirm" in check["text"] and check["text"].startswith("cost_usd ≥ 16.5")


def test_dominance_with_lower_bounds():
    inf = float("inf")
    assert not dominates([(10, inf), (1, 1)], [(30, 30), (1, 1)]), "a lower bound does not beat a value it might exceed"
    assert dominates([(10, 10), (1, 1)], [(30, inf), (1, 1)]), "an exact value below a lower bound does"
    same = "seal|gasket|1"
    assert dominates([(10, inf, 10, same)], [(30, inf, 30, same)]), "the same lines left out: compare what is shown"
    assert pareto_ranks([[(10, inf, 10, "a"), 1], [(30, inf, 30, "a"), 1], [(5, inf, 5, "b"), 1]]) == [1, 2, 1]
    assert pareto_ranks([[1, 2], [2, 1], [3, 3], [1, 2]]) == [1, 1, 2, 1]
