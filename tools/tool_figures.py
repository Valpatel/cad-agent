#!/usr/bin/env python3
"""Make the catalogue's tool covers from what the tools produce on the repo's own test projects.

    PYTHONPATH=src python3 tools/tool_figures.py             # write the kernel-free figure (below)
    PYTHONPATH=src python3 tools/tool_figures.py --check     # exit 1 if it differs (tests/test_tool_figures.py)
    PYTHONPATH=src python3 tools/tool_figures.py --renders   # also the review-packet renders (needs the cad extra)
    PYTHONPATH=src python3 tools/tool_figures.py --shots     # also the site screenshots (needs Node, Playwright, Chrome)

Every figure is a tool's real output on a project in this repo, made in a scratch copy:

* ``gates-connectivity.svg`` (cad-agent gates): the connectivity gate's graph of the gate bench
  (tests/fixtures/gate_bench), as ``cad-agent site`` draws it from ``exports/gates/connectivity.dot``. It is built from
  the bench's committed gate output (``site_snapshot/``, refreshed by ``site_snapshot.py``), with the built-in layout
  (Graphviz is hidden from the run, so every machine draws the same SVG), and ``--check`` compares it byte for byte.
* ``review-packet-store.jpg`` (cad-agent review-packet) and ``review-section-arm.jpg`` (cad-agent review-section,
  whose reviewer bundle carries the packet): renders of the gate bench's Store and Arm sections, after
  ``cad-agent gates --build``. VTK's pixels differ between machines and versions, so these are not compared; rerun
  ``--renders`` after a change to the bench or the renderer.
* ``site-designs.jpg`` (cad-agent site) and ``dossier-review.jpg`` (cad-agent dossier): ``cad-agent site`` for
  examples/explore-two-wheel (its design cards, after ``cad-agent compare``) and the review page it builds for the
  gate bench from ``cad-agent dossier``'s statuses, photographed by tools/page-shot.mjs at 1200 x 900.

The tools run as ``python -m cadagent.cli``, the same entry point as the ``cad-agent`` command.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "tools"
BENCH = ROOT / "tests" / "fixtures" / "gate_bench"
EXPLORE = ROOT / "examples" / "explore-two-wheel"
SKIP = shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site", "*.pyc")


def env(no_graphviz: bool = False) -> dict:
    e = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")])))
    if no_graphviz:          # the built-in layout on every machine: drop any PATH folder that has Graphviz's `dot`
        e["PATH"] = os.pathsep.join(d for d in e.get("PATH", "").split(os.pathsep) if d and not (Path(d) / "dot").exists())
    return e


def cli(cwd: Path, *args: str, ok=(0,), no_graphviz: bool = False) -> str:
    done = subprocess.run([sys.executable, "-m", "cadagent.cli", *args], cwd=cwd, env=env(no_graphviz),
                          capture_output=True, text=True)
    if done.returncode not in ok:
        raise SystemExit(f"cad-agent {' '.join(args)} failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")
    return done.stdout


def bench_copy(tmp: Path, snapshot: bool) -> Path:
    """The gate bench in a scratch folder; with ``snapshot``, its committed gate output as exports/."""
    dst = tmp / "gate_bench"
    shutil.copytree(BENCH, dst, ignore=SKIP)
    if snapshot:
        shutil.copytree(BENCH / "site_snapshot", dst / "project" / "exports")
    return dst / "project"


def connectivity() -> str:
    with tempfile.TemporaryDirectory(prefix="tool-figures-") as tmp:
        project = bench_copy(Path(tmp), snapshot=True)
        cli(project, "site", "--project", str(project), no_graphviz=True)
        return (project / "site" / "review" / "connectivity.svg").read_text(encoding="utf-8")


def jpeg(src: Path, dst: Path, width: int = 960) -> None:
    from PIL import Image                               # the cad extra has Pillow; --check does not need it
    im = Image.open(src).convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, quality=84, optimize=True, progressive=True)
    print(f"wrote {dst.relative_to(ROOT)}")


def renders() -> None:
    with tempfile.TemporaryDirectory(prefix="tool-figures-") as tmp:
        project = bench_copy(Path(tmp), snapshot=False)
        cli(project, "gates", "--project", str(project), "--build", "--jobs", "2")
        cli(project, "review-packet", "--project", str(project), "S-store", "S-arm", "--size", "1200x900")
        review = project / "exports" / "review"
        jpeg(review / "S-store" / "xray-iso.png", OUT / "review-packet-store.jpg")
        jpeg(review / "S-arm" / "pose-I-pin-arm-max.png", OUT / "review-section-arm.jpg")


def shots() -> None:
    def shot(page: Path, dst: Path) -> None:
        png = dst.with_suffix(".png")
        subprocess.run(["node", str(ROOT / "tools" / "page-shot.mjs"), str(page), str(png), "1200", "900"], check=True, cwd=ROOT)
        jpeg(png, dst)
        png.unlink()
    with tempfile.TemporaryDirectory(prefix="tool-figures-") as tmp:
        ex = Path(tmp) / EXPLORE.name
        shutil.copytree(EXPLORE, ex, ignore=SKIP)
        cli(ex, "compare", ok=(0, 1))                     # exit 1: a design fails, which the page shows
        cli(ex, "site")
        shot(ex / "site" / "index.html", OUT / "site-designs.jpg")
        project = bench_copy(Path(tmp), snapshot=True)
        cli(project, "site", "--project", str(project), no_graphviz=True)
        shot(project / "site" / "review" / "index.html", OUT / "dossier-review.jpg")


def main(argv: list[str]) -> int:
    svg, dst = connectivity(), OUT / "gates-connectivity.svg"
    if "--check" in argv:
        if not dst.exists() or dst.read_text(encoding="utf-8") != svg:
            print(f"{dst.relative_to(ROOT)} is stale: run PYTHONPATH=src python3 tools/tool_figures.py", file=sys.stderr)
            return 1
        print(f"{dst.relative_to(ROOT)} matches cad-agent site's drawing of the bench's connectivity gate")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    dst.write_text(svg, encoding="utf-8")
    print(f"wrote {dst.relative_to(ROOT)}")
    if "--renders" in argv:
        renders()
    if "--shots" in argv:
        shots()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
