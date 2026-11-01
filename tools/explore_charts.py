#!/usr/bin/env python3
"""Regenerate the numbers behind the catalogue's compare cover from the tool's own output.

    PYTHONPATH=src python3 tools/explore_charts.py            # write docs/img/explore/two-wheel-charts.json
    PYTHONPATH=src python3 tools/explore_charts.py --check    # exit 1 if the committed file differs (tests run this)

It copies the worked example (examples/explore-two-wheel) to a scratch folder and runs ``cad-agent compare --json``
there: the four designs, as the comparison page ranks them.

Nothing is typed by hand: each point is a design with its cost and mass, whether it meets the constraints,
whether it is on the Pareto front (over all the objectives in cad-agent.yaml: cost, mass and runtime, so a point on
the front can look dominated on a cost and mass chart), and which totals are only lower bounds (``≥``: a part without
a price or a mass). tools/site-catalog.mjs draws the covers from this file (catalog-art.mjs ``chartCover``).

The tools run as ``python -m cadagent.cli``, the same entry point as the ``cad-agent`` command, so this script needs
only cadagent's core dependencies (numpy, pyyaml).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "explore-two-wheel"
OUT = ROOT / "docs" / "img" / "explore" / "two-wheel-charts.json"
X, Y = "cost_usd", "mass_kg"


def run(cwd: Path, *args: str) -> str:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")])))
    done = subprocess.run([sys.executable, "-m", "cadagent.cli", *args], cwd=cwd, env=env, capture_output=True, text=True)
    if done.returncode not in (0, 1):            # compare exits 1 when a design fails; that is a result, not an error
        raise SystemExit(f"cad-agent {' '.join(args)} failed ({done.returncode}):\n{done.stderr}")
    return done.stdout


def axis(doc: dict, metric: str) -> dict:
    m = doc["metrics"][metric]
    return {"metric": metric, "label": m.get("label", metric), "unit": m.get("unit", "")}


def point(d: dict) -> dict:
    """One design: its cost and mass as the tool computed them, and what the tool says about it."""
    m = d["metrics"]
    return {
        "label": d["name"],
        "x": m[X]["value"], "y": m[Y]["value"],
        "feasible": bool(d["feasible"]), "front": bool(d["pareto"]),
        "lower_bound": [k for k in (X, Y) if k in (d.get("lower_bounds") or [])],
    }


def chart(doc: dict, command: str, what: str) -> dict:
    objectives = [doc["metrics"][o["metric"]].get("label", o["metric"]) for o in doc["objectives"]]
    return {
        "command": command, "title": doc["title"], "what": what,
        "x": axis(doc, X), "y": axis(doc, Y), "front_over": objectives,
        "points": [point(d) for d in doc["designs"]],
    }


def build() -> dict:
    with tempfile.TemporaryDirectory(prefix="explore-charts-") as tmp:
        work = Path(tmp) / EXAMPLE.name
        shutil.copytree(EXAMPLE, work, ignore=shutil.ignore_patterns("exports", "site", "__pycache__"))
        compare = json.loads(run(work, "compare", "--json"))
    return {
        "source": "examples/explore-two-wheel",
        "generated_by": "tools/explore_charts.py (run it with --check to compare)",
        "compare": chart(compare, "cad-agent compare", f"{len(compare['designs'])} designs"),
    }


def text(data: dict) -> str:
    """Indented JSON with one point per line, so a changed number shows as a one-line diff."""
    points = {}
    for name in ("compare",):
        points[name] = data[name]["points"]
        data = {**data, name: {**data[name], "points": f"@{name}@"}}
    out = json.dumps(data, indent=1, ensure_ascii=False)
    for name, pts in points.items():
        rows = ",\n".join("   " + json.dumps(p, ensure_ascii=False) for p in pts)
        out = out.replace(f'"@{name}@"', "[\n" + rows + "\n  ]")
    return out + "\n"


def main(argv: list[str]) -> int:
    new = text(build())
    if "--check" in argv:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old != new:
            print(f"{OUT.relative_to(ROOT)} is stale: run PYTHONPATH=src python3 tools/explore_charts.py", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} matches the tools' output")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(new, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
