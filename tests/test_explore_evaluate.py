"""cadagent.explore.evaluate: the generic part, the project's Python or command evaluator, goals and verdicts."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from cadagent.explore.config import EvaluatorSpec, explore_config
from cadagent.explore.design import load_design
from cadagent.explore.evaluate import evaluate_design, load_evaluator, normalise_result
from cadagent.project import CadConfigError

from .explore_fixtures import enclosure_config, restore_sys_path, write_enclosure  # noqa: F401 (a fixture)

pytestmark = pytest.mark.usefixtures("restore_sys_path")


def _evaluate(root, name, evaluator=None, cfg=None):
    cfg, cat = enclosure_config(root) if cfg is None else (cfg, enclosure_config(root)[1])
    path = root / "designs" / f"{name}.json"
    return evaluate_design(load_design(path), cat, cfg, evaluator, name, f"designs/{name}.json", path)


def test_without_an_evaluator_a_design_still_gets_cost_and_mass(tmp_path):
    root = write_enclosure(tmp_path)
    cfg, cat = enclosure_config(root)
    cfg.objectives, cfg.constraints = cfg.objectives[:1], []
    ev = _evaluate(root, "base", None, cfg)
    assert ev["verdict"] == "warn", "the gasket has no price"
    assert ev["metrics"]["cost_usd"] == {"value": 35.0, "unit": "USD", "label": "cost", "estimate": False,
                                         "incomplete": True, "source": "bom"}
    assert ev["parts"] == {"fan": "fan-60", "psu": "psu-60w", "screws": "m3x8", "seal": "gasket"}
    assert ev["counts"] == {"ok": 0, "warn": 1, "fail": 0}


def test_a_python_evaluator_adds_metrics_checks_and_bom_lines(tmp_path):
    root = write_enclosure(tmp_path)
    fn = load_evaluator(EvaluatorSpec(python="tools/evaluate.py:evaluate"), root)
    base = _evaluate(root, "base", fn)
    assert base["verdict"] == "warn" and base["summary"] == "60 mm fan and 60 W supply"
    assert base["metrics"]["temp_rise_c"] == {"value": 1.96, "estimate": True}
    assert base["metrics"]["cost_usd"]["value"] == pytest.approx(38.5), "the printed shell counts in the cost"
    assert base["metrics"]["cost_usd"]["estimate"], "and it is an estimate"
    assert base["metrics"]["noise_dba"]["level"] == "ok"
    assert {c["id"] for c in base["checks"]} == {"price-seal", "constraint-noise_dba"}
    hot = _evaluate(root, "hot", fn)
    assert hot["verdict"] == "fail" and any(c["id"] == "psu" and c["level"] == "fail" for c in hot["checks"])
    assert hot["params"] == {"heat_w": 30}


def test_constraints_and_missing_objectives_fail_the_design(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "designs" / "loud.json").write_text(json.dumps({"extends": "base.json", "parts": {"fan": "fan-80"}}))
    fn = load_evaluator(EvaluatorSpec(python="tools/evaluate.py:evaluate"), root)
    loud = _evaluate(root, "loud", fn)
    assert loud["verdict"] == "fail" and loud["metrics"]["noise_dba"]["level"] == "fail"
    assert "noise_dba = 34: above the maximum 32." in [c["text"] for c in loud["checks"]]
    cfg, _ = enclosure_config(root)
    from cadagent.explore.config import Objective
    cfg.objectives.append(Objective("runtime_min", "max"))
    ev = _evaluate(root, "base", fn, cfg)
    assert ev["verdict"] == "fail" and "No numeric value for the objective runtime_min." in [c["text"] for c in ev["checks"]]


def test_an_evaluator_that_raises_makes_only_that_design_an_error(tmp_path):
    root = write_enclosure(tmp_path, evaluator="def evaluate(c):\n    if c.id == 'hot':\n        raise ValueError('boom')\n"
                                               "    return {'metrics': {'temp_rise_c': 1, 'noise_dba': 20}}\n")
    fn = load_evaluator(EvaluatorSpec(python="tools/evaluate.py:evaluate"), root)
    hot, base = _evaluate(root, "hot", fn), _evaluate(root, "base", fn)
    assert hot["verdict"] == "error" and hot["errors"][0].startswith("evaluator raised ValueError: boom (evaluate.py:3)")
    assert hot["metrics"]["cost_usd"]["value"] == 28.0, "cost and mass are still shown"
    assert base["verdict"] == "warn"


def test_normalise_result_reports_problems_instead_of_crashing():
    r = normalise_result({"metrics": {"a": float("nan"), "b": {"unit": "kg"}, "c": [1], "d": True, "e": 3},
                          "checks": [{"level": "maybe", "text": "x"}, "nope", {"level": "WARN", "message": "y"}],
                          "lines": "x", "metric": {}})
    assert r["metrics"]["a"] == {"value": None} and r["metrics"]["b"] == {"value": None}
    assert r["metrics"]["c"]["value"] is None and r["metrics"]["d"] == {"value": True} and r["metrics"]["e"] == {"value": 3}
    assert r["checks"] == [{"id": "check-1", "level": "fail", "text": "x (level 'maybe' is not ok, warn or fail, so it counts as fail)"},
                           {"id": "check-3", "level": "warn", "text": "y"}]
    text = " ".join(r["problems"])
    for fragment in ("unknown keys ['metric']", "not a finite number", "has no 'value'", "must be a number",
                     "checks[1] is not a mapping", "lines must be a list"):
        assert fragment in text
    with pytest.raises(Exception, match="must return a mapping"):
        normalise_result([1])


def test_a_command_evaluator_reads_the_request_on_stdin(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "tools" / "eval_cmd.py").write_text(textwrap.dedent("""\
        import json, sys
        req = json.load(sys.stdin)
        design = json.load(open(sys.argv[1]))
        assert design["parts"]["fan"] == req["parts"]["fan"]["item"]["id"] and sys.argv[2] == req["id"] == "quiet"
        print("some log line")
        print(json.dumps({"metrics": {"temp_rise_c": 2.5, "noise_dba": 20, "fans": req["parts"]["fan"]["qty"]},
                          "summary": req["name"] + " " + str(req["bom"]["totals"]["cost"])}))
        """))
    spec = EvaluatorSpec(command=["{python}", "tools/eval_cmd.py", "{design}", "{id}"])
    ev = _evaluate(root, "quiet", load_evaluator(spec, root, sys.executable))
    assert ev["verdict"] == "warn" and ev["summary"] == "Quiet 32.0" and ev["metrics"]["fans"] == {"value": 1}


@pytest.mark.parametrize("script, fragment", [
    ("import sys; sys.exit(3)", "exit code 3"),
    ("print('not json')", "stdout is not a JSON object"),
    ("import time; time.sleep(5)", "timed out after 0.5 s"),
])
def test_command_evaluator_failures_are_design_errors(tmp_path, script, fragment):
    root = write_enclosure(tmp_path)
    (root / "tools" / "bad.py").write_text(script)
    fn = load_evaluator(EvaluatorSpec(command=[sys.executable, "tools/bad.py"], timeout_s=0.5), root)
    ev = _evaluate(root, "base", fn)
    assert ev["verdict"] == "error" and fragment in ev["errors"][0]


def test_loading_evaluators(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "evalpkg").mkdir()
    (root / "evalpkg" / "__init__.py").write_text("")
    (root / "evalpkg" / "model.py").write_text("def run(c):\n    return {}\n")
    assert load_evaluator(EvaluatorSpec(python="evalpkg.model:run"), root)(None) == {}
    assert load_evaluator(None, root) is None
    with pytest.raises(CadConfigError, match="not found"):
        load_evaluator(EvaluatorSpec(python="tools/missing.py:evaluate"), root)
    with pytest.raises(CadConfigError, match="'nope' is not a function"):
        load_evaluator(EvaluatorSpec(python="tools/evaluate.py:nope"), root)
    (root / "tools" / "broken.py").write_text("import not_a_module_anywhere\n")
    with pytest.raises(CadConfigError, match="failed to import"):
        load_evaluator(EvaluatorSpec(python="tools/broken.py:evaluate"), root)


@pytest.mark.parametrize("raw, fragment", [
    ({"evaluator": {"python": "a.py:f", "command": ["x"]}}, "exactly one"),
    ({"evaluator": "tools/evaluate.py"}, "path/to/file.py:function"),
    ({"objectives": [{"metric": "x", "goal": "lowest"}]}, "goal min or max"),
    ({"constraints": [{"metric": "x"}]}, "'min' and/or 'max'"),
    ({"constraints": [{"metric": "x", "min": "5"}]}, "must be a number"),
    ({"currency": "dollars"}, "three-letter code"),
    ({"slots": {"fan": {"qty": -1}}}, "whole number"),
    ({"categories": ["fan"], "slots": {"psu": "psu"}}, "is not in categories"),
    ({"max_price_age_days": "never"}, "whole number of days"),
])
def test_config_errors(tmp_path, raw, fragment):
    with pytest.raises(CadConfigError, match=fragment.replace("(", r"\(").replace(")", r"\)")):
        explore_config(tmp_path, raw)


def test_config_defaults(tmp_path):
    cfg = explore_config(tmp_path, {"currency": "EUR", "evaluator": {"command": "node tools/e.mjs {design}"}, "typo": 1}, "T")
    assert [(o.metric, o.goal) for o in cfg.objectives] == [("cost_eur", "min"), ("mass_kg", "min")]
    assert cfg.evaluator.command == ["node", "tools/e.mjs", "{design}"] and cfg.unknown_keys == ["typo"]
    assert cfg.title == "T" and cfg.out == tmp_path.resolve() / "exports/explore" and cfg.designs == ["designs/*.json"]
