#!/usr/bin/env python3
"""Regenerate the animated README figures (docs/img/hero/*.svg) from their committed scenes.

    PYTHONPATH=src python3 tools/readme_anim.py              # write every SVG from its scene
    PYTHONPATH=src python3 tools/readme_anim.py --check      # exit 1 if a committed SVG differs or breaks a rule
    PYTHONPATH=src python3 tools/readme_anim.py --extract hero --source ../gyropup     # re-extract a scene

A figure has three committed files:
* its spec (``tools/anim/<name>.yaml``): which project files to draw, how, and the words;
* its scene (``tools/anim/<name>.scene.json``): what extraction measured from the project's real CAD and results,
  with the source commit and every input's sha256;
* its SVG.

Extraction needs CadQuery and a checkout of the source project. Rendering needs only cad-agent's core dependencies,
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

from cadagent.publish.anim import hero, svg  # noqa: E402

ANIM = ROOT / "tools" / "anim"
# name: (kind, spec, scene, output)
FIGURES = {
    "hero": ("hero", ANIM / "gyropup-leg.yaml", ANIM / "gyropup-leg.scene.json",
             ROOT / "docs" / "img" / "hero" / "gyropup-leg.svg"),
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
    raise ValueError(f"unknown figure kind {kind}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare with the committed SVGs instead of writing")
    ap.add_argument("--extract", metavar="NAME", help="re-extract this figure's scene (needs CadQuery and --source)")
    ap.add_argument("--source", type=Path, help="checkout of the project the figure's spec draws")
    ap.add_argument("--no-clearance", action="store_true", help="skip the clearance sweep when extracting")
    a = ap.parse_args(argv)
    if a.extract:
        if a.extract not in FIGURES or not a.source:
            ap.error(f"--extract needs one of {', '.join(FIGURES)} and --source")
        kind, spec_path, scene_path, _ = FIGURES[a.extract]
        scene = hero.extract(hero.read_spec(spec_path), a.source, clearance=not a.no_clearance)
        hero.write_scene(scene, scene_path)
        print(f"wrote {_shown(scene_path)} in {scene['extract_seconds']} s")
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
