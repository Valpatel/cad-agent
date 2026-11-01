"""cadagent.simulation.explore.evaluate: the generic part, the project's Python or command evaluator, goals and
verdicts."""

from __future__ import annotations

import json
import os
import signal
import sys
import textwrap
import time
from datetime import date
from pathlib import Path

import pytest

from cadagent.simulation.explore.catalogue import check_catalogue
from cadagent.simulation.explore.compare import compare_designs, write_comparison
from cadagent.simulation.explore.config import EvaluatorSpec, explore_config
from cadagent.simulation.explore.design import load_design
from cadagent.simulation.explore.evaluate import evaluate_design, load_evaluator, normalise_result, safe_name
from cadagent.project import CadConfigError

from .explore_fixtures import CONFIG, enclosure_config, restore_sys_path, write_enclosure  # noqa: F401 (a fixture)

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
                                         "incomplete": True, "source": "bom", "missing": ["seal|gasket|1"]}
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
    from cadagent.simulation.explore.config import Objective
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


def test_numpy_scalars_are_plain_numbers():
    np = pytest.importorskip("numpy")
    r = normalise_result({"metrics": {"n": np.int64(3), "x": np.float32(1.5), "a": np.array([1, 2])}})
    assert r["metrics"]["n"] == {"value": 3} and type(r["metrics"]["n"]["value"]) is int
    assert r["metrics"]["x"] == {"value": 1.5} and r["metrics"]["a"]["value"] is None


def test_normalise_result_reports_problems_instead_of_crashing():
    r = normalise_result({"metrics": {"a": float("nan"), "b": {"unit": "kg"}, "c": [1], "d": True, "e": 3},
                          "checks": [{"level": "maybe", "text": "x"}, "nope", {"level": "WARN", "message": "y"}],
                          "lines": "x", "metric": {}})
    assert r["metrics"]["a"] == {"value": None} and r["metrics"]["b"] == {"value": None}
    assert r["metrics"]["c"]["value"] is None and r["metrics"]["d"] == {"value": True} and r["metrics"]["e"] == {"value": 3}
    assert r["checks"] == [{"id": "check-1", "level": "fail", "text": "x (level 'maybe' is not ok, warn or fail, so it counts as fail)"},
                           {"id": "check-3", "level": "warn", "text": "y"}]
    text = " ".join(r["problems"])
    for fragment in ("unknown keys ['metric']", "has no 'value'", "must be a number",
                     "checks[1] is not a mapping", "lines must be a list"):
        assert fragment in text
    assert r["errors"] == ["the evaluator returned nan at metrics.a, not a finite number"]
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


NATIVE = textwrap.dedent("""\
    import json, subprocess, sys
    reply = json.dumps({"metrics": {"temp_rise_c": 1.5, "noise_dba": 20}})
    if sys.argv[1] == "stdout":
        print(reply, flush=True)
    # what gmsh does from C: write to file descriptor 1 directly, past sys.stdout (a child inherits fd 1)
    subprocess.run([sys.executable, "-c", "import os; os.write(1, b'Info    : Done meshing 3D (Wall 0.1s)')"], check=True)
    if sys.argv[1] == "file":
        open(sys.argv[2], "w").write(reply)
    """)


def test_native_output_on_fd_1_breaks_a_stdout_reply_but_not_a_result_file(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "tools" / "native.py").write_text(NATIVE)
    on_stdout = load_evaluator(EvaluatorSpec(command=["{python}", "tools/native.py", "stdout"]), root, sys.executable)
    ev = _evaluate(root, "base", on_stdout)
    assert ev["verdict"] == "error" and "stdout is not a JSON object" in ev["errors"][0]
    assert "Done meshing" in ev["errors"][0] and "pass {result} in the argv" in ev["errors"][0]
    to_file = load_evaluator(EvaluatorSpec(command=["{python}", "tools/native.py", "file", "{result}"]), root, sys.executable)
    ev = _evaluate(root, "base", to_file)
    assert ev["verdict"] == "warn" and ev["metrics"]["temp_rise_c"]["value"] == 1.5, ev["errors"]


@pytest.mark.parametrize("script, fragment", [
    ("print('{\"metrics\": {}}')", "exited without writing its result to the {result} file"),
    ("import sys; open(sys.argv[1], 'w').write('Info: half a reply')", "the {result} file is not JSON: 'Info: half a reply'"),
    ("import sys; open(sys.argv[1], 'w').write('{}'); sys.exit(2)", "exit code 2"),
])
def test_result_file_failures_are_design_errors(tmp_path, script, fragment):
    root = write_enclosure(tmp_path)
    (root / "tools" / "bad.py").write_text(script)
    fn = load_evaluator(EvaluatorSpec(command=[sys.executable, "tools/bad.py", "{result}"]), root)
    ev = _evaluate(root, "base", fn)
    assert ev["verdict"] == "error" and fragment in ev["errors"][0], ev["errors"]


@pytest.mark.parametrize("design_id", ["result", "request"])
def test_a_design_named_like_the_reply_or_request_file_keeps_its_own_file(tmp_path, design_id):
    """{design} is <id>.json in the same private folder as the request and the reply: a design called "result" or
    "request" must not share a file with either (it once read its own design back as the reply)."""
    root = write_enclosure(tmp_path)
    (root / "designs" / f"{design_id}.json").write_text(json.dumps({"extends": "base.json"}))
    (root / "tools" / "check.py").write_text(textwrap.dedent("""\
        import json, sys
        design, request = json.load(open(sys.argv[1])), json.load(sys.stdin)
        assert "bom" in request and "bom" not in design, "the design file holds the request"
        """))                                          # and writes no reply
    fn = load_evaluator(EvaluatorSpec(command=["{python}", "tools/check.py", "{design}", "{result}"]), root, sys.executable)
    ev = _evaluate(root, design_id, fn)
    assert ev["verdict"] == "error" and "exited without writing its result" in ev["errors"][0], ev["errors"]


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


def test_safe_name_makes_a_plain_file_name():
    assert safe_name("trial-00007") == "trial-00007" and safe_name("quiet") == "quiet"
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-")
    for raw in ("designs/a/std", "/abs/shared/std", "..", "-rf", "base~fan=fan-40", "a b;$(x)"):
        name = safe_name(raw)
        assert set(name) <= allowed and not name.startswith((".", "-")), name
    assert safe_name("designs/a/std") != safe_name("designs-a/std"), "a hash keeps ids apart"


def test_a_command_evaluator_writes_only_into_its_own_temp_folder(tmp_path):
    """Same-stem designs and a design outside the project: every one is evaluated, {id} is a plain name, and no
    design file is written over (an absolute id used to replace the design outside the project)."""
    root = write_enclosure(tmp_path / "proj")
    for sub in ("a", "b"):
        (root / "designs" / sub).mkdir()
        (root / "designs" / sub / "variant.json").write_text(json.dumps({"extends": "../base.json", "name": f"V{sub}"}))
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "base.json").write_text((root / "designs" / "base.json").read_text())
    (shared / "variant.json").write_text(json.dumps({"extends": "base.json", "name": "Shared"}))
    before = (shared / "variant.json").read_bytes()
    (root / "tools" / "eval_cmd.py").write_text(textwrap.dedent("""\
        import json, os, sys
        design_file, out_id = sys.argv[1], sys.argv[2]
        os.makedirs(os.path.join("out", out_id))
        print(json.dumps({"metrics": {"temp_rise_c": 1, "noise_dba": 20}, "summary": design_file}))
        """))
    cfg, cat = enclosure_config(root)
    cfg.evaluator = EvaluatorSpec(command=["{python}", "tools/eval_cmd.py", "{design}", "{id}"])
    fn = load_evaluator(cfg.evaluator, root, sys.executable)
    files = [root / "designs" / "a" / "variant.json", root / "designs" / "b" / "variant.json", shared / "variant.json"]
    comp = compare_designs(cfg, cat, fn, files)
    by = {d["name"]: d for d in comp["designs"]}
    assert {n: d["verdict"] for n, d in by.items()} == {"Va": "warn", "Vb": "warn", "Shared": "warn"}, \
        [d["errors"] for d in comp["designs"]]
    assert (shared / "variant.json").read_bytes() == before, "the design outside the project is untouched"
    assert by["Va"]["id"] == "designs/a/variant" and by["Shared"]["id"].startswith("variant-")
    assert not any(d["id"].startswith("/") for d in comp["designs"])
    outs = list((root / "out").iterdir())
    assert len(outs) == 3 and all(o.is_dir() and not any(o.iterdir()) for o in outs), "one plain folder per {id}"
    for d in comp["designs"]:
        written = Path(d["summary"])
        assert written.name == f"{safe_name(d['id'])}.json" and written.parent.name.startswith("cadagent-eval-")
        assert root not in written.parents and shared not in written.parents


def test_dates_from_yaml_reach_a_command_evaluator_and_the_page(tmp_path):
    """yaml reads an unquoted 2026-10-01 as a date; JSON cannot carry one, so catalogues and designs get ISO text."""
    root = write_enclosure(tmp_path, CONFIG.replace("catalogue: [catalogue/*.json]",
                                                    "catalogue: [catalogue/*.json, catalogue/*.yaml]"))
    (root / "catalogue" / "more.yaml").write_text(
        "- {id: fan-50, category: fan, name: 50 mm fan, price_usd: 7, price_checked: 2026-10-01, mass_g: 20,\n"
        "   sources: ['https://example.com/fan-50'], specs: {airflow_cfm: 12, noise_dba: 28}}\n")
    (root / "designs" / "dated.yaml").write_text("extends: base.json\nname: Dated\nparts: {fan: fan-50}\n"
                                                 "params: {heat_w: 20, built: 2026-10-20}\n")
    (root / "tools" / "eval_cmd.py").write_text(textwrap.dedent("""\
        import json, sys
        req = json.load(sys.stdin)
        json.load(open(sys.argv[1]))
        print(json.dumps({"metrics": {"temp_rise_c": 2, "noise_dba": 20},
                          "summary": str(req["parts"]["fan"]["item"]["price_checked"]) + " " + str(req["params"]["built"])}))
        """))
    cfg, cat = enclosure_config(root)
    assert cat["fan-50"]["price_checked"] == "2026-10-01"
    assert not [i for i in check_catalogue(cat, cfg.categories, None) if i.level == "error"], "catalogue agrees"
    cfg.evaluator = EvaluatorSpec(command=["{python}", "tools/eval_cmd.py", "{design}"])
    fn = load_evaluator(cfg.evaluator, root, sys.executable)
    comp = compare_designs(cfg, cat, fn, [root / "designs" / "dated.yaml"])
    ev = comp["designs"][0]
    assert ev["verdict"] == "warn" and ev["summary"] == "2026-10-01 2026-10-20", ev["errors"]
    assert "2026-10-20" in write_comparison(comp, cfg.out, cfg=cfg)["html"].read_text()
    # a date that did not come through read_data (a design built in Python) is sent as ISO text too
    design = {"parts": {"fan": "fan-50", "psu": "psu-60w"}, "params": {"heat_w": 20, "built": date(2026, 10, 21)}}
    ev = evaluate_design(design, cat, cfg, fn, "direct")
    assert ev["verdict"] == "ok" and ev["summary"] == "2026-10-01 2026-10-21", ev["errors"]


def _gone(pid, wait=5.0):
    """True once ``pid`` has exited (a zombie waiting for init counts as exited)."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        try:
            if Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[-1].split()[0] == "Z":
                return True
        except (OSError, IndexError):
            pass
        time.sleep(0.05)
    return False


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
@pytest.mark.parametrize("mode, timeout_s", [("hang", 1), ("exit", 30)])
def test_a_command_evaluator_takes_what_it_started_with_it(tmp_path, mode, timeout_s):
    """On a timeout the evaluator's children die with it; a child left running after the evaluator printed its result
    neither holds the result up (it keeps stdout open) nor outlives it."""
    root = write_enclosure(tmp_path)
    pidfile = tmp_path / "child.pid"
    (root / "tools" / "spawn.py").write_text(textwrap.dedent("""\
        import json, subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])   # inherits stdout
        open(sys.argv[2], "w").write(str(child.pid))
        if sys.argv[1] == "hang":
            time.sleep(60)
        print(json.dumps({"metrics": {"temp_rise_c": 1, "noise_dba": 20}}))
        """))
    fn = load_evaluator(EvaluatorSpec(command=[sys.executable, "tools/spawn.py", mode, str(pidfile)],
                                      timeout_s=timeout_s), root)
    started = time.monotonic()
    ev = _evaluate(root, "base", fn)
    took = time.monotonic() - started
    pid = int(pidfile.read_text())
    try:
        if mode == "hang":
            assert ev["verdict"] == "error" and "timed out after 1 s" in ev["errors"][0] and took < 10
        else:
            assert ev["verdict"] == "warn" and took < 10, (ev["errors"], took)
        assert _gone(pid), "the evaluator's child was left running"
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_non_finite_numbers_from_the_evaluator_make_the_design_an_error(tmp_path):
    root = write_enclosure(tmp_path, evaluator="def evaluate(c):\n"
                                               "    return {'metrics': {'temp_rise_c': 1, 'noise_dba': 20},\n"
                                               "            'lines': [{'name': 'Shell', 'price_usd': float('nan'), 'mass_g': 5}],\n"
                                               "            'data': {'peak': float('inf')}}\n")
    fn = load_evaluator(EvaluatorSpec(python="tools/evaluate.py:evaluate"), root)
    ev = _evaluate(root, "base", fn)
    assert ev["verdict"] == "error"
    assert ev["errors"] == ["the evaluator returned nan at lines[0].price_usd, not a finite number",
                            "the evaluator returned inf at data.peak, not a finite number"]
    assert ev["bom"]["lines"][-1]["unit_price"] is None and ev["bom"]["totals"]["cost_complete"] is False
    json.dumps(ev, allow_nan=False)


def test_the_evaluator_folder_never_shadows_a_library(tmp_path):
    root = write_enclosure(tmp_path)
    (root / "tools" / "platform.py").write_text("NOT_THE_STDLIB = True\n")
    fn = load_evaluator(EvaluatorSpec(python="tools/evaluate.py:evaluate"), root)
    import importlib
    import platform
    importlib.reload(platform)
    assert hasattr(platform, "system") and sys.path[-1] == str((root / "tools").resolve()) and callable(fn)
