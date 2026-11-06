"""The starter's checks, each written to exports/<name>.json with a top-level "pass" that cad-agent.yaml's checks:
rows read. `cad-agent all` also checks every hole for material inside (its "Holes clear" rows), with no script.

  inserts.json    the screw joints into the heat-set inserts: hole, depth, boss, screw tip, torque (`cad-agent inserts`)
  overhangs.json  passes when no part has a downward face flatter than 45 degrees, other than on the bed, over 4 mm2
                  (`cad-agent overhangs`: a screen, not a slicer)

A check that cannot run (exit 2: a bad joint file, no parts) stops the build here, with its error in the log, rather
than leaving an earlier run's file for the report to read.
"""
import json
import sys
from pathlib import Path

from cadagent.cli import main

OUT = Path("exports")               # steps run in the project folder
for name in ("inserts.json", "overhang-screen.json", "overhangs.json"):
    (OUT / name).unlink(missing_ok=True)
if main(["inserts", str(OUT / "insert-joints.json"), "--output", str(OUT / "inserts.json")]) == 2:
    sys.exit("inserts: the check did not run (above)")
if main(["overhangs"]) == 2:
    sys.exit("overhangs: the screen did not run (above)")
screen = json.loads((OUT / "overhang-screen.json").read_text())
regions = {part: row.get("error") or row["regions"] for part, row in screen["parts"].items()}
(OUT / "overhangs.json").write_text(json.dumps({"pass": not any(regions.values()), "limit_deg": screen["limit_deg"],
                                                "regions": regions, "note": screen["note"]}, indent=1) + "\n")
