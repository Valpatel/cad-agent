"""cadagent.simulation.explore.optimise: the search space, the built-in samplers, resuming, and optuna's NSGA-II when
installed."""

from __future__ import annotations

import json
import random
import sys

import pytest

from cadagent.simulation.explore.config import Constraint
from cadagent.simulation.explore.evaluate import load_evaluator
from cadagent.simulation.explore.optimise import (Dimension, base_choice, change_pct, confirmed_evaluation,
                                                  constraint_values, read_records, run_search, search_config,
                                                  trial_design)
from cadagent.project import CadConfigError

from .explore_fixtures import (BRACKET, enclosure_config, restore_sys_path, write_bracket,  # noqa: F401 (a fixture)
                               write_enclosure)

pytestmark = pytest.mark.usefixtures("restore_sys_path")


def _setup(tmp_path, **search):
    root = write_enclosure(tmp_path)
    cfg, cat = enclosure_config(root)
    cfg.search.update(search)
    return root, cfg, cat, load_evaluator(cfg.evaluator, root)


def _calls(fn):
    return fn.__globals__["CALLS"]          # the fixture's evaluator records every design it sees


def test_dimensions():
    d = Dimension("param:x", "param", "x", low=120, high=200, step=20, integer=True)
    assert d.values() == [120, 140, 160, 180, 200] and d.contains(160) and not d.contains(150) and not d.contains(220)
    f = Dimension("param:w", "param", "a.w", low=2.0, high=3.0, step=0.5)
    assert f.values() == [2.0, 2.5, 3.0] and f.label == "w"
    rng = random.Random(1)
    assert all(f.sample(rng) in (2.0, 2.5, 3.0) for _ in range(20))
    log = Dimension("param:k", "param", "k", low=1.0, high=100.0, log=True)
    assert all(1.0 <= log.sample(rng) <= 100.0 for _ in range(20))
    with pytest.raises(CadConfigError, match="needs a 'step'"):
        log.values()
    c = Dimension("slot:fan", "slot", "fan", choices=["a", None])
    assert c.values() == ["a", None] and c.contains(None)


@pytest.mark.parametrize("search, fragment", [
    ({"base": None}, "base is required"),
    ({"base": "designs/none.json"}, "base not found"),
    ({"sampler": "anneal"}, "sampler must be one of"),
    ({"trials": 0}, "trials must be a whole number"),
    ({"space": []}, "at least one"),
    ({"space": [{"slot": "fan", "param": "x"}]}, "exactly one of"),
    ({"space": [{"slot": "fan", "choices": ["fan-99"]}]}, "not in the catalogue"),
    ({"space": [{"slot": "fan", "choices": ["fan-40", None]}]}, "required, so null"),
    ({"space": [{"slot": "lid"}]}, "has no category"),
    ({"space": [{"param": "x", "low": 5, "high": 1}]}, "low < high"),
    ({"space": [{"param": "x", "low": 0, "high": 1, "log": True}]}, "log range"),
    ({"space": [{"param": "x", "choices": [[1, 2]]}]}, "numbers, text"),
    ({"space": [{"slot": "fan"}, {"slot": "fan"}]}, "names something twice"),
    ({"space": [{"slot": "fan", "range": 3}]}, "unknown keys"),
    ({"budget": 3}, "unknown keys"),
    ({"base": "designs/broken.json"}, "search.base: broken.json: unreadable"),
    ({"confirm": {"mesh": 3}}, "confirm: unknown keys"),
    ({"confirm": {"top": 2}}, "needs 'args'"),
    ({"confirm": {"args": ["--mesh", 3]}}, "is a Python function"),
    ({"confirm": {"top": 0, "evaluator": "tools/evaluate.py:evaluate"}}, "top must be a whole number ≥ 1"),
    ({"confirm": {"top": 3, "limit": 2, "evaluator": "tools/evaluate.py:evaluate"}}, r"limit must be a whole number ≥ 3"),
    ({"confirm": {"tolerance_pct": -1, "evaluator": "tools/evaluate.py:evaluate"}}, "tolerance_pct must be"),
    ({"confirm": {"args": [["x"]], "evaluator": {"command": ["x"]}}}, "args must be a list"),
    ({"confirm": [3]}, "confirm must be a mapping"),
    ({"confirm": {"workers": 0, "evaluator": "tools/evaluate.py:evaluate"}}, "workers must be a whole number ≥ 1"),
])
def test_search_config_errors(tmp_path, search, fragment):
    root, cfg, cat, fn = _setup(tmp_path, **search)
    (root / "designs" / "broken.json").write_text("{")
    with pytest.raises(CadConfigError, match=fragment):
        search_config(cfg, cat)


def test_base_choice_and_trial_designs(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path)
    sc = search_config(cfg, cat)
    base = json.loads((root / "designs" / "base.json").read_text())
    assert base_choice(base, sc.space) == {"slot:fan": "fan-60", "slot:psu": "psu-60w", "param:heat_w": 20}
    assert base_choice({**base, "params": {"heat_w": 25}}, sc.space) is None, "25 is not one of the choices"
    d = trial_design(base, sc.space, {"slot:fan": "fan-40", "slot:psu": "psu-30w", "param:heat_w": 30}, 7, "designs/base.json")
    assert d["name"] == "trial 7" and d["parts"]["fan"] == "fan-40" and d["params"]["heat_w"] == 30
    assert d["parts"]["screws"] == {"part": "m3x8", "qty": 8} and "fan fan-40 · psu psu-30w · heat_w 30" in d["notes"]


def test_grid_covers_every_combination_once_and_resumes(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path)
    r = run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    assert (r["new"], r["trials"], r["sampler"]) == (4, 4, "grid")
    r = run_search(cfg, cat, fn, trials=100, progress=lambda m: None)
    assert (r["new"], r["trials"]) == (8, 12), "3 fans x 2 supplies x 2 heats, none twice"
    records = read_records(cfg.out / "search" / "trials.jsonl")
    choices = [json.dumps(rec["choice"], sort_keys=True) for rec in records]
    assert len(set(choices)) == 12 and [rec["trial"] for rec in records] == list(range(1, 13))
    board = json.loads((cfg.out / "search" / "leaderboard.json").read_text())
    assert board["kind"] == "search" and board["summary"]["designs"] == 12 and board["summary"]["feasible"] >= 1
    best = board["designs"][0]
    assert best["pareto"] and best["choice"] and (root / best["file"]).is_file()
    assert (cfg.out / "search" / "leaderboard.html").read_text().count('class="pt"') == 12
    r = run_search(cfg, cat, fn, trials=5, fresh=True, progress=lambda m: None)
    assert (r["new"], r["trials"]) == (5, 5), "fresh starts over"


def test_random_search_starts_from_the_base_and_reuses_repeats(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path, sampler="random", seed=3)
    seen = []
    r = run_search(cfg, cat, fn, trials=30, workers=3, progress=seen.append)
    records = read_records(cfg.out / "search" / "trials.jsonl")      # in the order the trials finished
    first = next(rec for rec in records if rec["trial"] == 1)
    assert first["choice"] == {"slot:fan": "fan-60", "slot:psu": "psu-60w", "param:heat_w": 20}
    repeats = [rec for rec in records if rec["duplicate_of"]]
    assert repeats and len(_calls(fn)) == 30 - len(repeats), "a repeated combination is not evaluated again"
    assert r["trials"] == 30 and len(seen) == 30 and any(m.strip().startswith("trial 1: warn") for m in seen)
    board = json.loads((cfg.out / "search" / "leaderboard.json").read_text())
    assert board["summary"]["designs"] == 30 - len(repeats) and board["summary"]["repeats"] == len(repeats)


def test_a_failing_evaluator_gives_error_trials_not_a_crash(tmp_path):
    root = write_enclosure(tmp_path, evaluator="def evaluate(c):\n    raise RuntimeError('no solver')\n")
    cfg, cat = enclosure_config(root)
    r = run_search(cfg, cat, load_evaluator(cfg.evaluator, root), trials=3, progress=lambda m: None)
    assert r["errors"] == 3 and r["feasible"] == 0


def test_constraint_values_follow_optunas_sign_convention(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path)
    cfg.constraints = [Constraint("noise_dba", max=32), Constraint("temp_rise_c", min=2.0), Constraint("missing", min=1),
                       Constraint("margin", min=0)]
    ev = {"checks": [{"id": "psu", "level": "fail"}, {"id": "constraint-noise_dba", "level": "fail"}],
          "metrics": {"noise_dba": {"value": 40}, "temp_rise_c": {"value": 3.0}, "margin": {"value": -0.5}}}
    assert constraint_values(ev, cfg) == pytest.approx([1.0, 0.25, -0.5, 1.0, 0.5, 0.0]), "a bound of 0: the absolute gap"
    ev["metrics"]["cost_usd"] = {"value": 20, "incomplete": True, "missing": ["seal|gasket|1", "psu|psu-x|1"]}
    assert constraint_values(ev, cfg, {"cost_usd": 1})[-1] == 1.0, "one more unpriced line than the base design"
    assert constraint_values(ev, cfg, {"cost_usd": 2})[-1] == 0.0


def test_nsga2_with_optuna(tmp_path):
    pytest.importorskip("optuna")
    root, cfg, cat, fn = _setup(tmp_path, sampler="nsga2", population=4, seed=2,
                                space=[{"slot": "fan"}, {"slot": "psu"}, {"param": "heat_w", "low": 10, "high": 40, "step": 5}])
    r = run_search(cfg, cat, fn, trials=10, workers=2, progress=lambda m: None)
    assert r["new"] == 10 and r["feasible"] >= 1 and (cfg.out / "search" / "study.db").is_file()
    records = read_records(cfg.out / "search" / "trials.jsonl")
    first = next(rec for rec in records if rec["trial"] == 1)
    assert first["choice"] == {"slot:fan": "fan-60", "slot:psu": "psu-60w", "param:heat_w": 20}, "the base first"
    r = run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    assert r["trials"] == 14 and read_records(cfg.out / "search" / "trials.jsonl")[-1]["trial"] == 14
    import optuna
    study = optuna.load_study(study_name="explore", storage=f"sqlite:///{cfg.out / 'search' / 'study.db'}")
    assert len(study.trials) == 14, "the second run continued the same study"
    complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    recorded = [getattr(t, "constraints", None) or t.system_attrs.get("constraints") for t in complete]
    assert complete and all(recorded), "every complete trial carries its constraints"
    values = [list(c.values()) if isinstance(c, dict) else list(c) for c in recorded]
    assert any(max(v) > 0 for v in values) and any(max(v) <= 0 for v in values), "feasible and infeasible trials both"


def test_a_continued_optuna_search_gets_a_new_seed(tmp_path, monkeypatch):
    pytest.importorskip("optuna")
    from cadagent.simulation.explore import optimise

    seeds = []
    real = optimise.OptunaSampler

    class Spy(real):
        def __init__(self, kind, space, cfg, seed, *rest):
            seeds.append(seed)
            super().__init__(kind, space, cfg, seed, *rest)

    monkeypatch.setattr(optimise, "OptunaSampler", Spy)
    root, cfg, cat, fn = _setup(tmp_path, sampler="tpe", seed=7)
    run_search(cfg, cat, fn, trials=3, progress=lambda m: None)
    run_search(cfg, cat, fn, trials=3, progress=lambda m: None)
    assert seeds == [7, 10], "the seeded startup draws are not replayed"


def test_tpe_with_optuna(tmp_path):
    pytest.importorskip("optuna")
    root, cfg, cat, fn = _setup(tmp_path, sampler="tpe", seed=1)
    r = run_search(cfg, cat, fn, trials=6, progress=lambda m: None)
    assert r["new"] == 6 and r["sampler"] == "tpe"


def test_a_repeat_proposed_while_its_original_runs_waits_for_it(tmp_path, monkeypatch):
    """Two workers, and a sampler that proposes the same combination twice in a row: evaluated once."""
    import threading

    from cadagent.simulation.explore import optimise

    root, cfg, cat, fn = _setup(tmp_path, sampler="random")
    gate = threading.Event()
    asked = []

    def slow(c):
        assert gate.wait(10), "the second proposal never came"
        return fn(c)

    class Twice(optimise.RandomSampler):
        def ask(self, fixed=None):
            asked.append(1)
            if len(asked) == 2:          # the original is still waiting on the gate: the repeat must wait for it
                gate.set()
            return None, {"slot:fan": "fan-40", "slot:psu": "psu-60w", "param:heat_w": 20}

    monkeypatch.setattr(optimise, "RandomSampler", Twice)
    r = run_search(cfg, cat, slow, trials=2, workers=2, progress=lambda m: None)
    records = sorted(read_records(cfg.out / "search" / "trials.jsonl"), key=lambda rec: rec["trial"])
    assert [rec["duplicate_of"] for rec in records] == [None, 1] and r["new"] == 2
    assert len(_calls(fn)) == 1, "the repeat used the first trial's result"


def test_an_interrupted_search_keeps_its_leaderboard(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path, sampler="random", seed=5)
    calls = []

    def stop_on_the_fourth(c):
        calls.append(c.id)
        if len(calls) == 4:
            raise KeyboardInterrupt
        return fn(c)

    seen = []
    r = run_search(cfg, cat, stop_on_the_fourth, trials=20, progress=seen.append)
    assert r["interrupted"] and r["evaluated"] == 3 and r["new"] == 3 + r["repeats"]
    assert any(m.startswith("stopping: the leaderboard has the") for m in seen)
    board = json.loads((cfg.out / "search" / "leaderboard.json").read_text())
    assert board["summary"]["designs"] == 3, "written before the run returned"


def test_a_search_does_not_continue_on_changed_inputs(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path, sampler="random", seed=2)
    run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    assert json.loads((cfg.out / "search" / "search.json").read_text())["parts"]
    cat["fan-40"]["price_usd"] = 60.0                       # a part in the space changes price
    with pytest.raises(CadConfigError, match=r"4 earlier trials .* different .*catalogue parts: run with --fresh"):
        run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    cat["fan-40"]["price_usd"] = 6.0
    cfg.constraints[0].max = 30                              # back to the old prices, but a new limit
    with pytest.raises(CadConfigError, match="different constraints"):
        run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    (root / "tools" / "evaluate.py").write_text((root / "tools" / "evaluate.py").read_text() + "\n# changed\n")
    with pytest.raises(CadConfigError, match="different constraints, evaluator"):
        run_search(cfg, cat, fn, trials=4, progress=lambda m: None)
    r = run_search(cfg, cat, fn, trials=4, fresh=True, progress=lambda m: None)
    assert r["trials"] == 4, "--fresh starts over with the new inputs"
    cat["psu-30w"]["notes"] = "unrelated edit"
    cat["gasket"]["notes"] = "not in the space, not in the base"   # base has the gasket: it is in the fingerprint
    with pytest.raises(CadConfigError, match="catalogue parts"):
        run_search(cfg, cat, fn, trials=1, progress=lambda m: None)


def test_the_leaderboard_json_is_slim(tmp_path):
    root, cfg, cat, fn = _setup(tmp_path)
    run_search(cfg, cat, fn, trials=3, progress=lambda m: None)
    board = json.loads((cfg.out / "search" / "leaderboard.json").read_text())
    first = board["designs"][0]
    assert board["records"] == "trials.jsonl" and set(first["bom"]) == {"currency", "totals"}
    assert "lines" in read_records(cfg.out / "search" / "trials.jsonl")[0]["evaluation"]["bom"]
    assert "<h3>Bill of materials" in (cfg.out / "search" / "leaderboard.html").read_text(), "the page still has them"


def _bracket(tmp_path, config=BRACKET):
    root = write_bracket(tmp_path, config)
    cfg, cat = enclosure_config(root)
    assert len(cat) == 0, "a parameter search has no catalogue"
    return root, cfg, cat, load_evaluator(cfg.evaluator, root, sys.executable)


def _board(cfg):
    board = json.loads((cfg.out / "search" / "leaderboard.json").read_text())
    return board, {(d["choice"]["param:wall_mm"], d["choice"]["param:corner"]): d for d in board["designs"]}


def test_confirm_reranks_the_leaders_on_a_finer_mesh_and_flags_the_artefacts(tmp_path):
    """At 4 mm a sharp corner reads 0.5 too high. Confirming the top 2 at 3 mm drops the leader (4 mm wall, sharp) below
    the filleted one, which brings the next sharp trial into the top 2; that one is confirmed too and fails the
    constraint. The leaderboard ranks on the confirmed values and keeps the screening ones beside them."""
    root, cfg, cat, fn = _bracket(tmp_path)
    seen = []
    r = run_search(cfg, cat, fn, trials=10, progress=seen.append)
    assert r["trials"] == 6 and r["confirm"]["new"] == 3 and r["confirm"]["leaders_confirmed"] == 2
    board, by = _board(cfg)
    screen = sorted(read_records(cfg.out / "search" / "trials.jsonl"),
                    key=lambda rec: -rec["evaluation"]["metrics"]["safety_factor"]["value"])
    assert [rec["choice"]["param:corner"] for rec in screen[:2]] == ["sharp", "round"], "at 4 mm, sharp leads"
    leaders = [(d["choice"]["param:wall_mm"], d["choice"]["param:corner"]) for d in board["designs"][:2]]
    assert leaders == [(4, "round"), (4, "sharp")], "ranked on the confirmed values"
    lead = by[(4, "round")]
    assert lead["confirm"]["values"]["safety_factor"] == {"screen": 2.4, "confirmed": 2.3952, "change_pct": -0.2}
    assert not lead["confirm"]["flag"] and lead["verdict"] == "ok" and lead["metrics"]["mesh_mm"]["value"] == 3.0
    assert lead["summary"].endswith("-confirm"), "{id} of a confirmation is the trial's id + -confirm"
    sharp = by[(4, "sharp")]
    assert sharp["confirm"]["values"]["safety_factor"] == {"screen": 2.7, "confirmed": 2.2, "change_pct": -18.52}
    assert sharp["confirm"]["flag"] and sharp["confirm"]["flagged"] == ["safety_factor"] and sharp["verdict"] == "warn"
    assert "safety_factor 2.7 → 2.2 (-18.5 %)" in next(c["text"] for c in sharp["checks"] if c["id"] == "confirm")
    fallen = by[(3, "sharp")]
    assert not fallen["feasible"] and fallen["confirm"]["reasons"][-1] == "infeasible once confirmed (fail)"
    assert "confirm" not in by[(3, "round")] and by[(3, "round")]["rank"] == 3, "unconfirmed: screening values"
    assert board["confirm"]["confirmed"] == 3 and board["summary"]["flagged"] == 2
    assert any(n.startswith("2 of the first 2 feasible trials (3 trial(s) in all) are confirmed") for n in board["notes"])
    assert any(m.startswith("  confirm trial") and "-18.5 %" in m for m in seen)
    page = (cfg.out / "search" / "leaderboard.html").read_text()
    assert ">Confirmed</button>" in page and "was 2.7" in page and "<h3>Confirmation</h3>" in page
    assert len(read_records(cfg.out / "search" / "confirm.jsonl")) == 3

    r = run_search(cfg, cat, fn, trials=5, progress=lambda m: None)
    assert (r["new"], r["confirm"]["new"]) == (0, 0), "nothing new to search or to confirm"
    cfg.search["confirm"]["tolerance_pct"] = 20
    r = run_search(cfg, cat, fn, trials=5, progress=lambda m: None)
    board, by = _board(cfg)
    assert r["confirm"]["new"] == 0 and not by[(4, "sharp")]["confirm"]["flag"], "the tolerance applies without a rerun"
    assert by[(3, "sharp")]["confirm"]["flag"], "a trial that became infeasible stays flagged"
    cfg.search["confirm"].update(args=["--mesh", 2.5], workers=2)
    r = run_search(cfg, cat, fn, trials=5, confirm=False, progress=lambda m: None)
    assert r["confirm"]["new"] == 0 and r["confirm"]["confirmed"] == 0, "made with other args: not used, not rerun"
    assert any(n.startswith("0 of the first 2 feasible trials (0 trial(s) in all)") for n in _board(cfg)[0]["notes"])
    assert "Confirmed: 0 of the first 2 feasible trials" in (cfg.out / "search" / "leaderboard.html").read_text()
    r = run_search(cfg, cat, fn, trials=5, progress=lambda m: None)
    board, by = _board(cfg)
    assert r["confirm"]["new"] == 4 and by[(4, "round")]["metrics"]["mesh_mm"]["value"] == 2.5
    assert [(d["choice"]["param:wall_mm"], d["choice"]["param:corner"]) for d in board["designs"][:2]] == \
        [(4, "round"), (3, "round")], "at 2.5 mm (4, sharp) drops below (3, round), which is then confirmed as well"
    run_search(cfg, cat, fn, trials=2, fresh=True, confirm=False, progress=lambda m: None)
    assert not (cfg.out / "search" / "confirm.jsonl").exists(), "--fresh starts the confirmations over too"


def test_a_failed_confirmation_keeps_the_screening_values_and_is_flagged(tmp_path):
    root, cfg, cat, fn = _bracket(tmp_path)
    cfg.search["confirm"] = {"top": 1, "evaluator": {"command": [sys.executable, "-c", "import sys; sys.exit(4)"]}}
    r = run_search(cfg, cat, fn, trials=6, progress=lambda m: None)
    board, by = _board(cfg)
    lead = board["designs"][0]
    assert (lead["choice"]["param:wall_mm"], lead["choice"]["param:corner"]) == (4, "sharp"), "screening values rank"
    assert lead["confirm"]["flag"] and "exit code 4" in lead["confirm"]["errors"][0] and lead["verdict"] == "warn"
    assert "ranked on its screening values" in lead["confirm"]["reasons"][0]
    assert r["confirm"]["new"] == 1 and r["confirm"]["leaders_confirmed"] == 0, "tried once this run, not again"
    assert run_search(cfg, cat, fn, trials=1, progress=lambda m: None)["confirm"]["new"] == 1, "retried on the next"


def test_change_pct_and_flags_at_the_edges(tmp_path):
    root, cfg, cat, fn = _bracket(tmp_path)
    assert change_pct(2.0, 2.0) == 0.0 and change_pct(2.0, 1.5) == -25.0 and change_pct(-2.0, -1.0) == 50.0
    assert change_pct(0.0, 0.0) == 0.0 and change_pct(0.0, 0.1) is None and change_pct(None, 1.0) is None
    ev = lambda v, verdict="ok": {"id": "trial-00001", "name": "trial 1", "verdict": verdict,  # noqa: E731
                                  "metrics": {"safety_factor": {"value": v}}, "checks": [], "errors": []}
    within = confirmed_evaluation(ev(2.0), ev(2.09), cfg, 5.0, "fine")
    assert not within["confirm"]["flag"] and within["verdict"] == "ok"
    from_zero = confirmed_evaluation(ev(0.0), ev(0.1), cfg, 5.0, "fine")
    assert from_zero["confirm"]["flagged"] == ["safety_factor"] and from_zero["confirm"]["reasons"] == ["safety_factor 0 → 0.1"]
    gone = confirmed_evaluation(ev(2.0), ev(None), cfg, 5.0, "fine")
    assert gone["confirm"]["flagged"] == ["safety_factor"] and gone["confirm"]["values"]["safety_factor"]["confirmed"] is None
    from cadagent.simulation.explore.page import _confirm_cell
    block = {"flag": True, "flagged": ["margin"], "values": {"margin": {"screen": 0, "confirmed": 0.4, "change_pct": None},
                                                             "safety_factor": {"screen": 2, "confirmed": 1.99, "change_pct": -0.5}}}
    assert ">changed</span>" in _confirm_cell({"confirm": block}), "not the other metric's -0.5 %"
    assert "−0.5 %" in _confirm_cell({"confirm": {**block, "flag": False, "flagged": []}})
