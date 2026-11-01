"""`cad-agent catalogue`, `compare` and `optimise`, end to end: the shipped example and an enclosure project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cadagent.cli import main

from .explore_fixtures import BRACKET, restore_sys_path, write_bracket, write_enclosure  # noqa: F401 (a fixture)

pytestmark = pytest.mark.usefixtures("restore_sys_path")
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "explore-two-wheel"


@pytest.fixture
def example(tmp_path):
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("exports", "__pycache__", "site"))
    return root


def test_the_example_checks_compares_and_searches(example, capsys):
    assert main(["catalogue", "--project", str(example)]) == 0
    out = capsys.readouterr().out
    assert "12 parts in 3 file(s)" in out and "0 errors, 1 warnings" in out and "depth-camera: no price_usd" in out
    assert main(["compare", "--project", str(example), "--swaps"]) == 0
    out = capsys.readouterr().out
    assert "4 designs: 3 feasible, 2 on the Pareto front" in out and "≥ 1,682 USD est." in out
    comp = json.loads((example / "exports" / "explore" / "comparison.json").read_text())
    by = {d["id"]: d for d in comp["designs"]}
    assert by["light"]["pareto"] and by["standard"]["pareto"] and by["strong"]["rank"] == 2
    long_range = by["long-range"]
    assert long_range["verdict"] == "fail" and {"volts-legs", "volts-compute"} <= {c["id"] for c in long_range["checks"]
                                                                                   if c["level"] == "fail"}
    assert long_range["metrics"]["cost_usd"]["incomplete"], "the depth camera has no price"
    fix = next(s for s in long_range["swaps"] if s["to"] == "pack-10s-10ah")
    assert fix["feasible"] and fix["better"] == ["cost_usd", "mass_kg"], "the smaller pack makes it work"
    assert any(l["name"].startswith("Printed legs") for l in by["light"]["bom"]["lines"])
    assert (example / "exports" / "explore" / "compare.html").is_file()
    assert main(["optimise", "--project", str(example), "--trials", "12"]) == 0
    out = capsys.readouterr().out
    assert "search (random): 12 new trial(s)" in out and "front: trial 1:" in out
    assert (example / "exports" / "explore" / "search" / "leaderboard.html").is_file()


def test_compare_named_designs_and_json(tmp_path, capsys):
    root = write_enclosure(tmp_path)
    cfg = (root / "cad-agent.yaml").read_text().replace("  explore:\n", "  explore:\n    colour: blue\n")
    assert "colour: blue" in cfg
    (root / "cad-agent.yaml").write_text(cfg)
    assert main(["compare", "--project", str(root), "--json", "designs/quiet.json"]) == 0
    captured = capsys.readouterr()
    comp = json.loads(captured.out)
    assert "unknown explore: keys ignored: colour" in captured.err, "warnings keep out of the JSON"
    assert [d["name"] for d in comp["designs"]] == ["Quiet"]
    assert main(["compare", "--project", str(root), "designs/nope.json"]) == 2
    assert "design file not found" in capsys.readouterr().err


def test_compare_exit_codes(tmp_path, capsys):
    root = write_enclosure(tmp_path)
    (root / "designs" / "typo.json").write_text(json.dumps({"parts": {"fan": "fan-99", "psu": "psu-60w"}}))
    assert main(["compare", "--project", str(root)]) == 1, "a design that cannot be evaluated"
    assert "1 could not be evaluated" in capsys.readouterr().out
    assert main(["catalogue", "--project", str(root)]) == 1
    assert "ERROR design designs/typo.json: slot fan: unknown part id 'fan-99'" in capsys.readouterr().out


@pytest.mark.parametrize("config, fragment", [
    ("cad:\n  name: x\n", "no explore: section"),
    ("cad:\n  explore: {evaluator: tools/missing.py:evaluate, catalogue: [catalogue/*.json]}\n", "evaluator file not found"),
    ("cad:\n  explore: {designs: [designs/*.json], slots: {fan: fan}}\n", "lists no catalogue files, but slots are declared (fan)"),
    ("cad:\n  explore: {catalogue: [catalogue/*.json], objectives: [{metric: x, goal: up}]}\n", "goal min or max"),
])
def test_unusable_explore_config_exits_2(tmp_path, capsys, config, fragment):
    root = write_enclosure(tmp_path, config=config)
    assert main(["compare", "--project", str(root)]) == 2
    assert fragment in capsys.readouterr().err


def test_optimise_needs_a_search_section_and_optuna_for_nsga2(tmp_path, capsys, monkeypatch):
    root = write_enclosure(tmp_path, config="cad:\n  explore: {catalogue: [catalogue/*.json]}\n")
    assert main(["optimise", "--project", str(root)]) == 2
    assert "search.base is required" in capsys.readouterr().err
    root = write_enclosure(tmp_path / "b")
    import sys
    monkeypatch.setitem(sys.modules, "optuna", None)
    assert main(["optimise", "--project", str(root), "--sampler", "nsga2"]) == 2
    assert "needs 'optuna'" in capsys.readouterr().err
    assert main(["optimise", "--project", str(root), "--sampler", "grid", "--trials", "3"]) == 0


def test_json_output_parses_with_an_unknown_cad_key(tmp_path, capsys):
    root = write_enclosure(tmp_path)
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text().replace("  name: enclosure\n", "  name: enclosure\n  colour: blue\n"))
    assert main(["catalogue", "--project", str(root), "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["parts"] == 7 and "unknown cad: keys ignored: colour" in captured.err


def test_absolute_catalogue_patterns(tmp_path, capsys):
    root = write_enclosure(tmp_path / "proj")
    shared = tmp_path / "shared"
    shared.mkdir()
    (root / "catalogue" / "parts.json").rename(shared / "parts.json")
    cfg = (root / "cad-agent.yaml").read_text().replace("catalogue: [catalogue/*.json]", f"catalogue: ['{shared}/*.json']")
    (root / "cad-agent.yaml").write_text(cfg)
    assert main(["catalogue", "--project", str(root)]) == 0
    assert "7 parts in 1 file(s)" in capsys.readouterr().out


def test_a_parameter_search_needs_no_catalogue(tmp_path, capsys):
    """No catalogue and no slots: the designs differ only in their parameters, their BOMs are empty, and catalogue,
    compare and optimise (with its confirm stage) all run."""
    root = write_bracket(tmp_path)
    assert main(["catalogue", "--project", str(root)]) == 0
    assert "catalogue: none configured and no slots" in capsys.readouterr().out
    assert main(["compare", "--project", str(root)]) == 0
    comp = json.loads((root / "exports" / "explore" / "comparison.json").read_text())
    assert comp["designs"][0]["bom"]["lines"] == [] and comp["designs"][0]["verdict"] == "ok"
    assert list(comp["metrics"]) == ["safety_factor", "mesh_mm"], "no cost and mass columns when nothing is bought"
    assert "Bill of materials" not in (root / "exports" / "explore" / "compare.html").read_text()
    assert main(["optimise", "--project", str(root), "--trials", "6"]) == 0
    out = capsys.readouterr().out
    assert "search (grid): 6 new trial(s)" in out and "confirm (" in out and "--mesh 3): 3 evaluated this run" in out
    assert "2 of the top 2 feasible confirmed" in out and "flagged: trial " in out and "-18.5 %" in out
    assert main(["optimise", "--project", str(root), "--trials", "1", "--no-confirm"]) == 0
    out = capsys.readouterr().out
    assert "0 new trial(s)" in out and "0 evaluated this run (--no-confirm); 2 of the top 2" in out, "kept from before"
    (root / "designs" / "part.json").write_text(json.dumps({"parts": {"lid": "lid-1"}, "params": {"wall_mm": 3}}))
    assert main(["catalogue", "--project", str(root)]) == 1
    assert "unknown part id 'lid-1' (the catalogue is empty" in capsys.readouterr().out
    (root / "cad-agent.yaml").write_text(BRACKET.replace("space: [", "space: [{slot: lid}, "))
    assert main(["optimise", "--project", str(root), "--fresh"]) == 2
    assert "slot lid draws its parts from the catalogue, and none is configured" in capsys.readouterr().err
