"""Small non-robot projects for the explore tests: an electronics enclosure that picks a fan, a power supply, screws
sold in packs and a gasket with no public price; and a bracket whose search changes only parameters (no catalogue),
judged by a fake FEA command evaluator with a mesh setting."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

CATALOGUE = {
    "defaults": {"price_checked": "2026-10-01", "sources": ["https://example.com/datasheet"]},
    "items": [
        {"id": "fan-40", "category": "fan", "name": "40 mm fan", "price_usd": 6.0, "mass_g": 12,
         "specs": {"airflow_cfm": 7, "noise_dba": 25}},
        {"id": "fan-60", "category": "fan", "name": "60 mm fan", "price_usd": 9.0, "mass_g": 30, "preferred": True,
         "specs": {"airflow_cfm": 18, "noise_dba": 30}},
        {"id": "fan-80", "category": "fan", "name": "80 mm fan", "price_usd": 12.0, "mass_g": 55,
         "specs": {"airflow_cfm": 35, "noise_dba": 34}},
        {"id": "psu-30w", "category": "psu", "name": "30 W supply", "price_usd": 15.0, "mass_g": 150, "specs": {"power_w": 30}},
        {"id": "psu-60w", "category": "psu", "name": "60 W supply", "price_usd": 22.0, "mass_g": 260, "specs": {"power_w": 60}},
        {"id": "m3x8", "category": "fastener", "name": "M3x8 screw", "price_usd": 4.0, "pack_qty": 50, "mass_g": 0.6},
        {"id": "gasket", "category": "seal", "name": "Gasket", "price_usd": None, "mass_g": 8},
    ],
}

EVALUATOR = textwrap.dedent('''\
    CALLS = []

    def evaluate(c):
        CALLS.append(c.id)
        heat_w = c.param("heat_w", 20)
        cfm = c.spec("fan", "airflow_cfm", 0) * c.qty("fan")
        checks = []
        if c.spec("psu", "power_w", 0) < heat_w * 1.25:
            checks.append({"id": "psu", "level": "fail", "text": "The supply is too small."})
        return {"metrics": {"temp_rise_c": {"value": round(heat_w * 1.76 / cfm, 2) if cfm else None, "estimate": True},
                            "noise_dba": c.spec("fan", "noise_dba")},
                "checks": checks,
                "lines": [{"name": "Printed shell", "qty": 1, "price_usd": 3.5, "mass_g": 180, "estimate": True}],
                "summary": f"{c.part('fan')['name']} and {c.part('psu')['name']}"}
    ''')

DESIGNS = {
    "base": {"name": "Base", "parts": {"fan": "fan-60", "psu": "psu-60w", "screws": {"part": "m3x8", "qty": 8},
                                        "seal": "gasket"}, "params": {"heat_w": 20}},
    "quiet": {"extends": "base.json", "name": "Quiet", "parts": {"fan": "fan-40"}},
    "hot": {"extends": "base.json", "name": "Hot", "parts": {"psu": "psu-30w"}, "params": {"heat_w": 30}},
}

CONFIG = textwrap.dedent("""\
    cad:
      name: enclosure
      title: Enclosure options
      explore:
        catalogue: [catalogue/*.json]
        categories: [fan, psu, fastener, seal]
        slots:
          fan: {category: fan, required: true}
          psu: {category: psu, required: true}
          screws: {category: fastener, qty: 4}
          seal: {category: seal}
        evaluator: tools/evaluate.py:evaluate
        objectives: [{metric: cost_usd, goal: min}, {metric: temp_rise_c, goal: min}]
        constraints: [{metric: noise_dba, max: 32}]
        search:
          base: designs/base.json
          sampler: grid
          space: [{slot: fan}, {slot: psu}, {param: heat_w, choices: [20, 30]}]
    """)


# A parameter-only project: no catalogue, no slots. A bracket's wall and its inner corner are searched; a fake FEA
# command evaluator reads the safety factor, and a sharp corner's peak is a mesh artefact (it is singular, so a coarse
# mesh under-reads the stress and the factor keeps dropping as the mesh refines: it has no converged value), as the
# hip-frame study met (#144).
FEA = textwrap.dedent('''\
    import argparse, json, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--mesh", type=float, default=4.0)          # the last --mesh wins, so confirm args override
    a = ap.parse_args()
    req = json.load(sys.stdin)
    wall, corner = req["params"]["wall_mm"], req["params"]["corner"]
    if corner == "sharp":
        sf = 0.4 * wall + 0.6 + 0.5 * (a.mesh - 3.0)          # 0.5 higher at 4 mm than at 3 mm, and still falling
    else:
        sf = (0.4 * wall + 0.8) * (1 - 0.002 * (4.0 - a.mesh))  # a filleted corner converges: 0.2 % per mm
    json.dump({"metrics": {"safety_factor": round(sf, 4), "mesh_mm": a.mesh}, "summary": req["id"]}, open(a.result, "w"))
    ''')

BRACKET = textwrap.dedent("""\
    cad:
      name: bracket
      explore:
        evaluator: {command: ["{python}", tools/fea.py, "{result}", --mesh, "4"], timeout_s: 60}
        objectives: [{metric: safety_factor, goal: max}]
        constraints: [{metric: safety_factor, min: 1.85}]
        search:
          base: designs/base.json
          sampler: grid
          space: [{param: wall_mm, choices: [2, 3, 4]}, {param: corner, choices: [sharp, round]}]
          confirm: {top: 2, args: [--mesh, 3]}
    """)


def write_bracket(root: Path, config: str = BRACKET) -> Path:
    for d in ("designs", "tools"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "designs" / "base.json").write_text(json.dumps({"name": "Base", "params": {"wall_mm": 3, "corner": "round"}}))
    (root / "tools" / "fea.py").write_text(FEA)
    (root / "cad-agent.yaml").write_text(config)
    return root


def write_enclosure(root: Path, config: str = CONFIG, evaluator: str = EVALUATOR) -> Path:
    for d in ("catalogue", "designs", "tools"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "catalogue" / "parts.json").write_text(json.dumps(CATALOGUE, indent=1))
    for name, design in DESIGNS.items():
        (root / "designs" / f"{name}.json").write_text(json.dumps(design, indent=1))
    (root / "tools" / "evaluate.py").write_text(evaluator)
    (root / "cad-agent.yaml").write_text(config)
    return root


def enclosure_config(root: Path):
    """The parsed explore config and catalogue of a written enclosure (or bracket) project."""
    import yaml

    from cadagent.simulation.explore.catalogue import load_configured
    from cadagent.simulation.explore.config import explore_config

    cfg = explore_config(root, yaml.safe_load((root / "cad-agent.yaml").read_text())["cad"]["explore"], "Enclosure")
    catalogue, issues = load_configured(cfg)
    assert not [i for i in issues if i.level == "error"], issues
    return cfg, catalogue


@pytest.fixture
def restore_sys_path(monkeypatch):
    """Python evaluators put their folder on sys.path, as running them as a script would; undo it after a test."""
    import sys

    monkeypatch.setattr(sys, "path", list(sys.path))
