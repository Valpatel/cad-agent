#!/usr/bin/env python3
"""Regenerate the animated README figures (docs/img/hero/*.svg, docs/img/fea/*.svg) from their committed scenes.

    PYTHONPATH=src python3 tools/readme_anim.py              # write every SVG from its scene
    PYTHONPATH=src python3 tools/readme_anim.py --check      # exit 1 if a committed SVG differs or breaks a rule
    PYTHONPATH=src python3 tools/readme_anim.py --extract hero --source ../gyropup     # re-extract a scene
    PYTHONPATH=src python3 tools/readme_anim.py --extract convergence                  # re-record the FEA study

A figure has three committed files:
* its spec (``tools/anim/<name>.yaml``): which project files to draw, how, and the words;
* its scene (``tools/anim/<name>.scene.json``): what extraction measured from the project's real CAD and results,
  with the source commit and every input's sha256;
* its SVG.

Extraction needs CadQuery and a checkout of the source project; the convergence figure's source is this checkout, and
recording it needs gmsh and scikit-fem too. Rendering needs only cad-agent's core dependencies,
so ``--check`` (run by tests/test_readme_anim.py) works anywhere. Every SVG must also pass
``cadagent.publish.anim.svg.problems``: no script or external reference, valid XML, a title and label, a
reduced-motion still, at most 250 KB.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cadagent.publish.anim import convergence, hero, svg  # noqa: E402

ANIM = ROOT / "tools" / "anim"
# name: (kind, spec, scene, output)
FIGURES = {
    "hero": ("hero", ANIM / "gyropup-leg.yaml", ANIM / "gyropup-leg.scene.json",
             ROOT / "docs" / "img" / "hero" / "gyropup-leg.svg"),
    "convergence": ("convergence", ANIM / "fea-convergence.yaml", ANIM / "fea-convergence.scene.json",
                    ROOT / "docs" / "img" / "fea" / "mesh-convergence.svg"),
}


def _shown(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def build(name: str) -> str:
    kind, spec_path, scene_path, _ = FIGURES[name]
    spec = hero.read_spec(spec_path)
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    if kind == "hero":
        return hero.render(scene, spec["present"])
    if kind == "convergence":
        return convergence.render(scene, spec["present"])
    raise ValueError(f"unknown figure kind {kind}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare with the committed SVGs instead of writing")
    ap.add_argument("--extract", metavar="NAME", help="re-extract this figure's scene (needs CadQuery; the hero also --source)")
    ap.add_argument("--source", type=Path, help="checkout of the project the figure's spec draws (the convergence "
                    "figure records a study with this checkout's code instead)")
    ap.add_argument("--no-clearance", action="store_true", help="skip the clearance sweep when extracting")
    ap.add_argument("--workers", type=int, default=1, help="processes for the clearance sweep (each reads the STEP)")
    ap.add_argument("--fresh", action="store_true",
                    help="re-run the clearance sweep even when the committed scene's result still fits the inputs")
    a = ap.parse_args(argv)
    if a.extract:
        if a.extract not in FIGURES:
            ap.error(f"--extract needs one of {', '.join(FIGURES)}")
        kind, spec_path, scene_path, _ = FIGURES[a.extract]
        if kind == "convergence":
            scene = convergence.record(hero.read_spec(spec_path), ROOT, spec_path)
            convergence.write_scene(scene, scene_path)
            seconds = scene["record_seconds"]
        else:
            if not a.source:
                ap.error(f"--extract {a.extract} needs --source")
            previous = None if a.fresh or not scene_path.exists() else json.loads(scene_path.read_text(encoding="utf-8"))
            scene = hero.extract(hero.read_spec(spec_path), a.source, clearance=not a.no_clearance,
                                 previous=previous, workers=a.workers)
            hero.write_scene(scene, scene_path)
            seconds = scene["extract_seconds"]
        print(f"wrote {_shown(scene_path)} in {seconds} s")
    bad = 0
    for name, (_, _, _, out) in FIGURES.items():
        text = build(name)
        issues = svg.problems(text)
        for i in issues:
            print(f"{_shown(out)}: {i}")
        bad += bool(issues)
        if a.check:
            if not out.exists() or out.read_text(encoding="utf-8") != text:
                print(f"{_shown(out)} differs from its scene: run tools/readme_anim.py")
                bad += 1
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {_shown(out)} ({len(text.encode())} bytes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
