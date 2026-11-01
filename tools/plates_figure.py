#!/usr/bin/env python3
"""Regenerate the build-plates figure (docs/img/plates/gyropup-plates.svg) from a Gyropup checkout.

    python3 tools/plates_figure.py --gyropup <checkout of Valpatel/gyropup>

Gyropup (https://gyropup.com, MIT) is a wheel-legged robot designed with cad-agent. Use a clean checkout of its
`origin/main` (a worktree or a clone), never a working tree someone is editing. The figure is the picture
`cad-agent export-3mf` writes (cadagent.manufacturing.plates.export_plates), made in a temporary project from the
checkout's committed print files: every part's STL, its parts file, and the quantity and material of each part from
its print plan (exports/print-plan.json). Each material is named by the Bambu Studio filament profile a P1S would
print it with, and the P1S's bed exclusion corner is a keep-out area, as export-3mf adds it from the printer profile
when Bambu Studio is installed. Bambu Studio is not run here: the figure needs only the layout.

The checkout's revision, the settings and the plate summary are recorded in docs/img/plates/SOURCE.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "docs" / "img" / "plates"
FILAMENTS = {"pa6-cf": "Bambu PA6-CF @BBL X1C", "petg": "Bambu PETG HF @BBL P1S 0.4 nozzle",
             "tpu95": "Bambu TPU 95A @BBL X1C"}
P1S_EXCLUDE = [0, 0, 18, 28]     # Bambu Lab P1S 0.4 nozzle: bed_exclude_area 0x0, 18x0, 18x28, 0x28


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gyropup", required=True, type=Path, help="a clean checkout of Valpatel/gyropup")
    args = ap.parse_args()
    from cadagent.manufacturing.plates import export_plates
    from cadagent.project import load_project

    src = args.gyropup.resolve()
    rev = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    plan = json.loads((src / "exports" / "print-plan.json").read_text())
    parts = {name: {"quantity": int(p["qty"]), "filament": FILAMENTS[p["material"]]}
             for name, p in plan["parts"].items()}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "exports").mkdir()
        for name in parts:
            shutil.copy(src / "exports" / f"{name}.stl", root / "exports" / f"{name}.stl")
        shutil.copy(src / "exports" / "geometry-checks.json", root / "exports" / "geometry-checks.json")
        config = {"cad": {"name": "gyropup", "title": "Gyropup",
                          "printer": {"name": "Bambu Lab P1S", "bed_mm": plan["bed_mm"]},
                          "plates": {"keep_out": [P1S_EXCLUDE], "parts": parts}}}
        (root / "cad-agent.yaml").write_text(json.dumps(config, indent=1))     # JSON is YAML
        rec = export_plates(load_project(root), use_slicer=False)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "gyropup-plates.svg").write_text((root / "exports" / "gyropup-plates.svg").read_text())
    source = {
        "project": "Valpatel/gyropup", "license": "MIT", "revision": rev,
        "regenerate": "python3 tools/plates_figure.py --gyropup <checkout>",
        "inputs": ["exports/<part>.stl", "exports/geometry-checks.json", "exports/print-plan.json (qty, material)"],
        "bed_mm": rec["bed_mm"], "gap_mm": rec["gap_mm"], "margin_mm": rec["margin_mm"], "rotate": rec["rotate"],
        "keep_out_mm": rec["keep_out_mm"], "packing": rec["packing"],
        "copies": sum(rec["quantities"].values()),
        "plates": [{"plate": p["plate"], "name": p["name"], "parts": len(p["parts"]), "covered": p["covered"],
                    "turned": sorted({f"{q['part']} {q['turn_deg']}°" for q in p["parts"] if q["turn_deg"]})}
                   for p in rec["plates"]],
    }
    (OUT / "SOURCE.json").write_text(json.dumps(source, indent=1, ensure_ascii=False) + "\n")
    print(f"{source['copies']} copies on {len(rec['plates'])} plates -> {OUT / 'gyropup-plates.svg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
