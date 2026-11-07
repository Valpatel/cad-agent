#!/usr/bin/env python3
"""Regenerate the site's Gyropup showcase from a Gyropup checkout: the home page's 3D model and its pictures.

    python3 tools/gyropup_showcase.py --only model --gyropup <checkout> --toolkit <pinned-toolkit>
    python3 tools/gyropup_showcase.py --only pictures --gyropup <historical-checkout>
    node tools/site/figures/site-model-poster.mjs                                           # then the model's still poster

Gyropup (https://gyropup.com, MIT) is a wheel-legged robot designed with cad-agent. Use a clean checkout of its
`origin/main` (a worktree or a clone), never a working tree someone is editing.

- **The model** constructs the current product collector in memory with its recorded inputs and CAD runtime,
  writes only temporary STL meshes, then reuses cadagent.publish.view.pack_view (welded, 16-bit positions, gzip).
  Run on the fleet with the product source manifest's pinned toolkit/runtime. No old engineering exports are read.
- **The pictures** are Gyropup's committed outputs of cad-agent's own tools (cadagent.simulation.fea stress maps,
  cadagent.publish.render renders), cropped to the part and saved as WebP. Which stress map to use is a manual check: its
  title's numbers were compared by eye with exports/leg/fea/summary.json, because a stale map can sit beside a fresh
  summary (at 77f6d00, leg-E1.png's title says safety factor 0.93; the summary says 2.85). The numbers recorded in
  SOURCE.json come from the summary, and the site build fails when the home page's caption does not quote them.

The checkout's revision and the settings are recorded in the model's `source` and in docs/img/gyropup/SOURCE.json.
The home page's Gyropup card (docs/img/gyropup.jpg) is the model's poster with words, made by tools/site/figures/site-model-poster.mjs,
which records it as SOURCE.json's "banner" entry; this script keeps that entry.

The model records source hashes, runtime, collector, producer and all group members, including documented hidden
interior/fastener groups. Historical FEA pictures are independent evidence; a model refresh never relabels them.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import importlib.util
import importlib.metadata
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

MODELS = ROOT / "tools" / "site" / "assets" / "models"
PICTURES = ROOT / "docs" / "img" / "gyropup"
# 0.8 mm chord and 0.8 rad (46 degrees) per facet, with FINE_PARTS finer: 118,300 triangles and 391,703 bytes for
# the robot's 33 visible groups (b79896a), against 232k triangles and 620 KB at 0.3 mm / 0.5 rad. That is 17.9 KB
# under tests/webkit/webkit-model.test.mjs's 400 KiB: an export that grows needs a coarser setting or fewer parts.
# At the home page's size a millimetre is about a pixel, so the coarser chord does not show; most triangles are holes
# and gear teeth, which any tolerance keeps. The kit's creased normals keep curved faces reading round.
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


def current_source(checkout: Path, toolkit: Path):
    """Validate the product's existing conservative source closure before constructing CAD."""
    if git(ROOT, "status", "--porcelain", "--", "tools/gyropup_showcase.py", "software"):
        raise ValueError("Commit the showcase producer and toolkit changes before extraction")
    for path in (checkout, toolkit):
        if git(path, "status", "--porcelain"):
            raise ValueError("Use clean isolated product and toolkit checkouts")
    helper_path = checkout / "tools/engineering/robot/readme_design.py"
    spec = importlib.util.spec_from_file_location("showcase_source", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    cfg = json.loads((checkout / helper.CONFIG).read_text())
    if git(toolkit, "rev-parse", "HEAD") != cfg["toolkit"]["revision"]:
        raise ValueError("Use the product's recorded CAD toolkit revision")
    # The pinned collector and the reviewed current packer must agree: no hidden
    # version substitution while source artwork is being refreshed.
    relative = "software/cadagent/publish/view.py"
    if (toolkit / relative).read_bytes() != (ROOT / relative).read_bytes():
        raise ValueError("Pinned and current view packers differ; review the migration first")
    files = helper.verify_inputs(checkout, cfg)
    helper.verify_public_tree(checkout, cfg)
    return helper, cfg, files


def group_rows(rows):
    """Preserve the product collector's assembly positions, colours and named membership."""
    groups, names = {}, set()
    for group, colour, name, shape, _ in rows:
        if name in names or shape is None:
            raise ValueError(f"Duplicate or missing CAD part: {name}")
        names.add(name)
        entry = groups.setdefault(group, {"color": colour, "members": [], "shapes": []})
        if entry["color"] != colour:
            raise ValueError(f"Conflicting colours in CAD group: {group}")
        entry["members"].append(name)
        entry["shapes"].append(shape)
    if not groups:
        raise ValueError("No current CAD parts")
    for required in (WEB_SKIP, FINE_PARTS):
        if missing := sorted(set(required) - set(groups)):
            raise ValueError(f"Current CAD grouping changed; review export policy: {missing}")
    return groups


def model(checkout: Path, revision: str, committed: str, toolkit: Path, output: Path) -> dict:
    if any(output.resolve().is_relative_to(p.resolve()) for p in (checkout, toolkit)):
        raise ValueError("Model output must be outside the product and pinned toolkit checkouts")
    helper, cfg, files = current_source(checkout, toolkit)
    if any(n == "hardware" or n.startswith("hardware.") or n == "cadagent" or n.startswith("cadagent.") for n in sys.modules):
        raise ValueError("Construct the model in a fresh process without foreign CAD imports")
    sys.path[:0] = [str(checkout), str(toolkit / "software")]
    import cadagent
    import cadquery as cq
    import numpy as np
    from cadagent.publish.view import pack_view
    from cadagent.review.gates.relations import bounding_box

    if not Path(cadagent.__file__).resolve().is_relative_to((toolkit / "software/cadagent").resolve()):
        raise ValueError("CAD toolkit imported from another checkout")
    runtime = {"cadquery": cq.__version__, "numpy": np.__version__,
               "cadquery-ocp": importlib.metadata.version("cadquery-ocp"),
               "vtk": importlib.metadata.version("vtk"), "cad_agent_revision": git(toolkit, "rev-parse", "HEAD")}
    if runtime != cfg["runtime"]:
        raise ValueError(f"CAD runtime differs: {runtime}")
    before = helper.tracked(checkout)
    previous_j501 = os.environ.get("J501_DIR")
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as work:
        tmp = Path(work)
        os.environ["J501_DIR"] = str(tmp / "no-live-j501")
        try:
            import hardware.cad.body.body_params as params
            params.CACHE = tmp / "body-measurement-cache"
            robot = helper.load_module("showcase_robot_source", checkout / helper.SOURCE_CONTEXT)
            groups = group_rows(robot.collect())  # Never use stale STEP exports or call robot.export().
            if params.j501_params().get("_source") != "hardware/vendor/j501/parameters-0.9-g48r.json":
                raise ValueError("CAD did not use the tracked J501 snapshot")
            for name, module in list(sys.modules.items()):
                if name == "hardware" or name.startswith("hardware."):
                    locations = [module.__file__] if getattr(module, "__file__", None) else list(getattr(module, "__path__", ()))
                    if not locations or any(not Path(p).resolve().is_relative_to(checkout) for p in locations):
                        raise ValueError("Project CAD imported from another checkout")
            parts = []
            for name, group in sorted(groups.items()):
                if name in WEB_SKIP:
                    continue
                shape = cq.Compound.makeCompound(group["shapes"])
                tolerance, angular = FINE if name in FINE_PARTS else (TOLERANCE_MM, ANGULAR_RAD)
                stl = tmp / f"{name}.stl"
                cq.exporters.export(shape, str(stl), tolerance=tolerance, angularTolerance=angular, opt={"ascii": False})
                parts.append({"name": name, "file": stl.name, "color": group["color"], "visible": True,
                              "bounds_mm": [round(float(v), 2) for v in bounding_box(shape)]})
            manifest = tmp / "view.json"
            manifest.write_text(json.dumps({"title": "Gyropup", "units": "mm", "up": "z", "parts": parts}))
            source = {"project": "Valpatel/gyropup", "url": "https://gyropup.com", "repo": "https://github.com/Valpatel/gyropup",
                      "license": "MIT", "revision": revision, "committed": committed,
                      "hardware_tree": cfg["source"]["hardware_tree"], "files": files,
                      "collector": helper.SOURCE_CONTEXT, "collector_sha256": helper.digest(checkout / helper.SOURCE_CONTEXT),
                      "source_guard_sha256": helper.digest(checkout / "tools/engineering/robot/readme_design.py"),
                      "runtime": runtime, "producer_revision": git(ROOT, "rev-parse", "HEAD"),
                      "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "export": f"Fresh robot_view.collect() shapes, STL {TOLERANCE_MM} mm/{ANGULAR_RAD} rad; "
                                f"{', '.join(FINE_PARTS)} at {FINE[0]} mm/{FINE[1]} rad",
                      "pack": "cadagent.publish.view.pack_view", "regenerate": "python3 tools/gyropup_showcase.py --only model --gyropup <checkout> --toolkit <pinned-toolkit> --output <fresh-model-directory>",
                      "recoloured": [], "left_out": list(WEB_SKIP),
                      "members": {name: entry["members"] for name, entry in sorted(groups.items())},
                      "limits": "Current modeled geometry; bought parts may be envelopes. Not physical fit or strength evidence."}
            if helper.tracked(checkout) != before:
                raise ValueError("CAD construction changed tracked product files")
            packed = pack_view(manifest, output / "gyropup", title="Gyropup", view=VIEW, source=source)
        finally:
            primary_error = sys.exc_info()[1]
            if previous_j501 is None:
                os.environ.pop("J501_DIR", None)
            else:
                os.environ["J501_DIR"] = previous_j501
            try:
                helper.verify_public_tree(checkout, cfg)
                if helper.tracked(checkout) != before:
                    raise ValueError("CAD construction changed tracked product files")
            except Exception as guard_error:
                if primary_error is None:
                    raise
                print(f"Additional source guard failure: {guard_error}", file=sys.stderr)
    print(f"Current Gyropup: {len(packed['parts'])} visible groups, {sum(len(g['members']) for g in groups.values())} source parts, "
          f"{packed['triangles']} triangles, {packed['bytes']} bytes; {time.monotonic() - start:.1f} s")
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
        record["banner"] = old["banner"]                 # docs/img/gyropup.jpg's record (tools/site/figures/site-model-poster.mjs)
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
    ap.add_argument("--toolkit", type=Path, help="clean checkout of the product source manifest's CAD toolkit revision")
    ap.add_argument("--output", type=Path, default=MODELS, help="model output directory (use a fresh external directory on the fleet)")
    args = ap.parse_args(argv)
    checkout = args.gyropup.resolve()
    if git(checkout, "status", "--porcelain"):
        raise SystemExit(f"{checkout} has uncommitted changes: use a clean checkout of origin/main")
    revision, committed = git(checkout, "rev-parse", "HEAD"), git(checkout, "show", "-s", "--format=%cs", "HEAD")
    print(f"Gyropup {revision[:7]} ({committed})")
    if args.only != "pictures":
        if args.toolkit is None:
            ap.error("model extraction requires --toolkit at the product manifest's pinned revision")
        model(checkout, revision, committed, args.toolkit.resolve(), args.output.resolve())
    if args.only != "model":
        pictures(checkout, revision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
