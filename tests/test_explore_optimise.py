"""cadagent.explore.optimise: the search space, the built-in samplers, resuming, and optuna's NSGA-II when installed."""

from __future__ import annotations

import json
import random

import pytest

from cadagent.explore.config import Constraint
from cadagent.explore.evaluate import load_evaluator
from cadagent.explore.optimise import (Dimension, base_choice, constraint_values, read_records, run_search,
                                       search_config, trial_design)
from cadagent.project import CadConfigError

from .explore_fixtures import enclosure_config, restore_sys_path, write_enclosure  # noqa: F401 (a fixture)

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
    cfg.constraints = [Constraint("noise_dba", max=32), Constraint("temp_rise_c", min=2.0), Constraint("missing", min=1)]
    ev = {"checks": [{"id": "psu", "level": "fail"}, {"id": "constraint-noise_dba", "level": "fail"}],
          "metrics": {"noise_dba": {"value": 40}, "temp_rise_c": {"value": 3.0}}}
    assert constraint_values(ev, cfg) == pytest.approx([1.0, 0.25, -0.5, 1.0])


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


def test_tpe_with_optuna(tmp_path):
    pytest.importorskip("optuna")
    root, cfg, cat, fn = _setup(tmp_path, sampler="tpe", seed=1)
    r = run_search(cfg, cat, fn, trials=6, progress=lambda m: None)
    assert r["new"] == 6 and r["sampler"] == "tpe"


def test_a_repeat_proposed_while_its_original_runs_waits_for_it(tmp_path, monkeypatch):
    """Two workers, and a sampler that proposes the same combination twice in a row: evaluated once."""
    import threading

    from cadagent.explore import optimise

    root, cfg, cat, fn = _setup(tmp_path, sampler="random")
    gate = threading.Event()

    def slow(c):
        gate.wait(5)
        return fn(c)

    class Twice(optimise.RandomSampler):
        def ask(self, fixed=None):
            return None, {"slot:fan": "fan-40", "slot:psu": "psu-60w", "param:heat_w": 20}

    monkeypatch.setattr(optimise, "RandomSampler", Twice)
    threading.Timer(0.3, gate.set).start()
    r = run_search(cfg, cat, slow, trials=2, workers=2, progress=lambda m: None)
    records = sorted(read_records(cfg.out / "search" / "trials.jsonl"), key=lambda rec: rec["trial"])
    assert [rec["duplicate_of"] for rec in records] == [None, 1] and r["new"] == 2
    assert len(_calls(fn)) == 1, "the repeat used the first trial's result"
