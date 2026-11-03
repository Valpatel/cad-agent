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
The home page's Gyropup card (docs/img/gyropup.jpg) is the model's poster with words, made by tools/site-model-poster.mjs,
which records it as SOURCE.json's "banner" entry; this script keeps that entry.

Gyropup's `cad-agent view` reads exports/robot/*.step, its whole robot as drawn today (P3 body, five-bar legs, turret),
written by its tools/robot_view.py. Before that it read the serial-leg robot's exports/asm_*.step (rev 0.1).
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
# 0.8 mm chord and 0.8 rad (46 degrees) per facet: about 112k triangles and 375 KB for the robot's 33 visible groups,
# against 232k and 620 KB at 0.3 mm / 0.5 rad. At the home page's size a millimetre is about a pixel, so the coarser
# chord does not show; most triangles are holes and gear teeth, which any tolerance keeps. The kit's creased normals
# keep curved faces reading round.
TOLERANCE_MM, ANGULAR_RAD = 0.8, 0.8
# Groups of Gyropup's view (its tools/robot_view.py) left out of the web copy: what sits inside the shell (the frame's
# inner plates, the compute and power electronics, the bus bars) and the fasteners, bearings and pins (body, legs,
# turret), which are inside the links or under a pixel here. `cad-agent view` in Gyropup still shows them.
WEB_SKIP = ("frame_inner", "compute", "electronics", "bus_bars", "hardware", "leg_hardware_l", "leg_hardware_r",
            "turret_hardware")
# Big round parts the coarse angle would show as polygons (a tyre in 8 facets): tessellated again at FINE (mm, rad).
FINE_PARTS = ("tyre_l", "tyre_r", "hub_l", "hub_r", "lidar", "lidar_housing", "turret_hopper")
FINE = (0.3, 0.2)
VIEW = {"azimuth": 55, "elevation": 16}       # front three-quarter: the face, the turret's barrel and a whole leg
# Colour overrides by part name, for parts Gyropup's cad-agent.yaml leaves uncoloured (`cad-agent view` would cycle its
# default palette over them). Its robot view (exports/robot/*.step) colours every group, so none are needed today; the
# serial-leg view this replaced needed greys for its turret and some body parts.
GYROPUP_COLOURS: dict = {}
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
        manifest = json.loads((Path(tmp) / "view.json").read_text())
        missing = sorted(set(WEB_SKIP) - {p["name"] for p in manifest["parts"]})
        if missing:
            raise SystemExit(f"WEB_SKIP names groups the view does not have: {missing}")
        manifest["parts"] = [p for p in manifest["parts"] if p["name"] not in WEB_SKIP]
        import cadquery as cq
        for p in manifest["parts"]:
            if p["name"] in FINE_PARTS:
                shape = cq.importers.importStep(str(checkout / "exports" / "robot" / f"{p['name']}.step"))
                cq.exporters.export(shape, str(Path(tmp) / p["file"]), tolerance=FINE[0], angularTolerance=FINE[1],
                                    opt={"ascii": False})
        (Path(tmp) / "view.json").write_text(json.dumps(manifest, indent=1) + "\n")
        packed = pack_view(Path(tmp) / "view.json", MODELS / "gyropup", title="Gyropup", colors=GYROPUP_COLOURS, view=VIEW, source={
            "project": "Valpatel/gyropup", "url": "https://gyropup.com", "repo": "https://github.com/Valpatel/gyropup",
            "license": "MIT", "revision": revision, "committed": committed,
            "export": f"cadagent.publish.view.export_view (cad-agent view), tolerance {TOLERANCE_MM} mm, angular {ANGULAR_RAD} rad; "
                      f"{', '.join(FINE_PARTS)} at {FINE[0]} mm, {FINE[1]} rad",
            "pack": "cadagent.publish.view.pack_view", "regenerate": "python3 tools/gyropup_showcase.py --gyropup <checkout>",
            "recoloured": sorted(GYROPUP_COLOURS), "left_out": list(WEB_SKIP),
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
    previous = PICTURES / "SOURCE.json"
    if previous.is_file() and "banner" in (old := json.loads(previous.read_text())):
        record["banner"] = old["banner"]                 # docs/img/gyropup.jpg's record (tools/site-model-poster.mjs)
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
