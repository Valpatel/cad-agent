#!/usr/bin/env python3
"""Regenerate the site's Gyropup showcase from a Gyropup checkout: the home page's 3D model and its pictures.

    python3 tools/gyropup_showcase.py --gyropup <checkout of Valpatel/gyropup>   # web/models/gyropup.{json,bin}
                                                                               # + docs/img/gyropup/*.webp
    node tools/site-model-poster.mjs                                           # then the model's still poster

Gyropup (https://gyropup.com, MIT) is a wheel-legged robot designed with cad-agent. Use a clean checkout of its
`origin/main` (a worktree or a clone), never a working tree someone is editing.

- **The model** is `cad-agent view`'s export (cadagent.publish.view.export_view: every part's STEP in assembly position) at a
  web tessellation, written to a temporary folder (the project's own exports/view is left alone), then packed by
  cadagent.publish.view.pack_view: welded, 16-bit positions, gzip. Needs cadquery: run it with the project's own Python.
- **The pictures** are Gyropup's committed outputs of cad-agent's own tools (cadagent.simulation.fea stress maps,
  cadagent.publish.render renders), cropped to the part and saved as WebP. Which stress map to use is a manual check: its
  title's numbers were compared by eye with exports/leg/fea/summary.json, because a stale map can sit beside a fresh
  summary (at 77f6d00, leg-E1.png's title says safety factor 0.93; the summary says 2.85). The numbers recorded in
  SOURCE.json come from the summary, and the site build fails when the home page's caption does not quote them.

The checkout's revision and the settings are recorded in the model's `source` and in docs/img/gyropup/SOURCE.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MODELS = ROOT / "web" / "models"
PICTURES = ROOT / "docs" / "img" / "gyropup"
# 0.3 mm chord and 0.5 rad (29 degrees) per facet: 87k triangles and 312 KB for Gyropup's 58 parts, against 198k and
# ~690 KB at the viewer's default 0.1 mm / 0.2 rad. The kit's creased normals keep curved faces reading round.
TOLERANCE_MM, ANGULAR_RAD = 0.3, 0.5
VIEW = {"azimuth": 55, "elevation": 16}       # front three-quarter: the face, the turret's barrel and a whole leg
# Gyropup's cad-agent.yaml gives its turret and some body parts no colour, so `cad-agent view` cycles its default
# palette over them (purple, mint, sky blue), which reads as unrelated parts. Here they take greys and the orange
# accent from Gyropup's own palette (its configured colours are kept), close to the renders on gyropup.com.
GYROPUP_COLOURS = {
    "electronics_bay": "#5a5f68", "bumper_ring": "#3b3f46", "pan_base": "#b8bec7", "pan_ring": "#9aa3ad",
    "pan_pinion": "#d6dbe1", "pan_clamp": "#3b3f46", "tilt_yoke": "#d6dbe1", "cradle": "#c9ced6",
    "cartridge_body": "#b8bec7", "dial": "#3b3f46", "hopper": "#9cc9e8", "hopper_lid": "#9cc9e8",
    "hopper_flap": "#e8892b", "barrel": "#e8892b", "flywheel": "#3b3f46", "flywheel_tyre": "#1d2025",
    "laser_mount": "#3b3f46",
}
# name: (source in the Gyropup checkout, pixels to drop from the top first (a title band), the FEA case it shows)
PICTURE_SOURCES = {
    "wheel-link-fea": ("exports/leg/fea/wheel_link-E1.png", 34, ("wheel_link", "E1")),
    "leg-render": ("exports/leg/leg-stand-iso.png", 96, None),
}


def git(checkout: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True).stdout.strip()


def model(checkout: Path, revision: str, committed: str) -> dict:
    from cadagent.project import load_project
    from cadagent.publish.view import export_view, pack_view

    project = load_project(str(checkout))
    with tempfile.TemporaryDirectory() as tmp:
        start = time.monotonic()
        exported = export_view(project, tolerance=TOLERANCE_MM, angular=ANGULAR_RAD, out=Path(tmp))
        seconds = round(time.monotonic() - start, 1)
        if exported["skipped"]:
            raise SystemExit(f"parts without a STEP: {exported['skipped']}")
        packed = pack_view(Path(tmp) / "view.json", MODELS / "gyropup", title="Gyropup", colors=GYROPUP_COLOURS, view=VIEW, source={
            "project": "Valpatel/gyropup", "url": "https://gyropup.com", "repo": "https://github.com/Valpatel/gyropup",
            "license": "MIT", "revision": revision, "committed": committed,
            "export": f"cadagent.publish.view.export_view (cad-agent view), tolerance {TOLERANCE_MM} mm, angular {ANGULAR_RAD} rad",
            "pack": "cadagent.publish.view.pack_view", "regenerate": "python3 tools/gyropup_showcase.py --gyropup <checkout>",
            "recoloured": sorted(GYROPUP_COLOURS),
        })
    print(f"web/models/gyropup: {len(packed['parts'])} parts, {packed['triangles']} triangles, {packed['bytes']} bytes "
          f"(export {seconds} s)")
    return packed


def crop(path: Path, top: int, margin: int = 16):
    """The picture without its top band, cropped to what differs from its background (the corner pixel)."""
    from PIL import Image, ImageChops
    image = Image.open(path).convert("RGB")
    image = image.crop((0, top, image.width, image.height))
    background = Image.new("RGB", image.size, image.getpixel((image.width - 1, image.height - 1)))
    box = ImageChops.difference(image, background).convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
    if not box:
        raise SystemExit(f"{path}: nothing but background")
    left, upper, right, lower = box
    return image.crop((max(0, left - margin), max(0, upper - margin), min(image.width, right + margin), min(image.height, lower + margin)))


def pictures(checkout: Path, revision: str) -> dict:
    summary = json.loads((checkout / "exports/leg/fea/summary.json").read_text())
    PICTURES.mkdir(parents=True, exist_ok=True)
    record = {"project": "Valpatel/gyropup", "license": "MIT", "revision": revision,
              "regenerate": "python3 tools/gyropup_showcase.py --gyropup <checkout>", "pictures": {}}
    for name, (source, top, case) in PICTURE_SOURCES.items():
        entry = {"source": source}
        if case:
            result = next(r for r in summary["results"] if (r["part"], r["case"]) == case)
            entry.update(part=case[0], case=case[1], safety_factor=result["safety_factor"], target=result["target"],
                         ok=result["ok"], material=result["material"], tets=result["mesh"]["tets"],
                         element=result["mesh"]["element"])
        image = crop(checkout / source, top)
        image.save(PICTURES / f"{name}.webp", "WEBP", quality=86, method=6)
        entry.update(width=image.width, height=image.height)
        record["pictures"][name] = entry
        print(f"docs/img/gyropup/{name}.webp: {image.width}x{image.height}")
    (PICTURES / "SOURCE.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gyropup", type=Path, required=True, help="a clean checkout of Valpatel/gyropup (origin/main)")
    ap.add_argument("--only", choices=["model", "pictures"], help="regenerate one half")
    args = ap.parse_args(argv)
    checkout = args.gyropup.resolve()
    if git(checkout, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit(f"{checkout} has uncommitted changes: use a clean checkout of origin/main")
    revision, committed = git(checkout, "rev-parse", "HEAD"), git(checkout, "show", "-s", "--format=%cs", "HEAD")
    print(f"Gyropup {revision[:7]} ({committed})")
    if args.only != "pictures":
        model(checkout, revision, committed)
    if args.only != "model":
        pictures(checkout, revision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
