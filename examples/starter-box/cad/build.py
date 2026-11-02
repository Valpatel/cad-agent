"""The starter box: a box and a lid held by four M3 screws in heat-set inserts.

Change the numbers below, then run `cad-agent all`. The insert's hole and boss come from cad-agent
(`cadagent.mechanical.inserts`), so they follow the insert you choose. This script writes, in exports/:
  box.step, lid.step     assembly position (the lid sits on the box)
  box.stl, lid.stl       print orientation (both print as they sit: the box open side up, the lid flat)
  geometry-checks.json   the parts file: valid, one solid, watertight, print size
  insert-joints.json     the screw joints as built, for tools/checks.py
"""
import json
import math
from pathlib import Path

import cadquery as cq

from cadagent.geometry import export_print_stl, export_step, robust_cut, robust_union
from cadagent.mechanical import inserts

SIZE_MM = (60.0, 40.0, 25.0)      # outside of the closed box: length, width, height with the lid on
WALL_MM = 2.0                      # side walls
FLOOR_MM = 2.0
LID_MM = 3.0
CORNER_MM = 3.0                    # outside corner radius
INSERT = "mcmaster-94459A140"      # M3 x 5.7 mm brass insert: any key of cadagent.mechanical.inserts.INSERTS
SCREW_MM = 8.0                     # M3 screw length under the head
HEAD_MM = 5.5                      # its head diameter: ISO 4762 socket head cap screw, M3
MATERIAL = "pla-bambu-basic"       # a datasheet filament the insert check knows (cadagent.mechanical.inserts.PRINTED)

OUT = Path(__file__).resolve().parents[1] / "exports"
ins = inserts.insert(INSERT)
hole = inserts.hole_design(ins)                    # the maker's hole + 0.2 mm, and deep enough for the melt
boss = inserts.boss_design(ins)["outside_mm"]      # the makers' full-performance boss
clearance = inserts.CLEARANCE_MM[ins.thread]       # ISO 273 medium clearance hole for the screw

length, width, height = SIZE_MM
box_height = height - LID_MM
inset = boss / 2 + WALL_MM / 2                     # each corner boss reaches halfway into both walls
corners = [(x * (length / 2 - inset), y * (width / 2 - inset)) for x in (-1, 1) for y in (-1, 1)]
# the least plastic from a boss's centre to the outside: the walls, or the rounded corner where it reaches the boss
outside = inset if inset >= CORNER_MM else CORNER_MM - math.hypot(CORNER_MM - inset, CORNER_MM - inset)
if outside < boss / 2:
    raise ValueError(f"CORNER_MM {CORNER_MM:g} rounds the corners through the {boss:g} mm insert bosses: keep it "
                     f"under {(math.sqrt(2) * inset - boss / 2) / (math.sqrt(2) - 1):.1f} mm, or move the bosses in")


def rounded(l, w, h, r, z=0.0):
    """A block l x w x h with its vertical edges rounded to r, standing on z."""
    return cq.Workplane().box(l, w, h, centered=(True, True, False)).edges("|Z").fillet(r).translate((0, 0, z))


def make_box():
    outer = rounded(length, width, box_height, CORNER_MM)
    inner = rounded(length - 2 * WALL_MM, width - 2 * WALL_MM, box_height, max(CORNER_MM - WALL_MM, 0.5), FLOOR_MM)
    shell = robust_cut(outer, inner)
    bosses = cq.Workplane().pushPoints(corners).circle(boss / 2).extrude(box_height)
    body = robust_union(shell, bosses)
    holes = (cq.Workplane().workplane(offset=box_height - hole["depth_mm"]).pushPoints(corners)
             .circle(hole["diameter_mm"] / 2).extrude(hole["depth_mm"] + 1))
    return robust_cut(body, holes)


def make_lid():
    plate = rounded(length, width, LID_MM, CORNER_MM, box_height)
    holes = (cq.Workplane().workplane(offset=box_height - 1).pushPoints(corners)
             .circle(clearance / 2).extrude(LID_MM + 2))
    return robust_cut(plate, holes)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    parts = {"box": make_box(), "lid": make_lid()}
    report = {}
    for name, shape in parts.items():
        export_step(shape, OUT / f"{name}.step")
        report[name] = export_print_stl(shape, OUT / f"{name}.stl")
    (OUT / "geometry-checks.json").write_text(json.dumps(report, indent=1) + "\n")
    joint = {"name": "lid screw", "insert": INSERT, "material": MATERIAL,
             "hole_mm": hole["diameter_mm"], "hole_depth_mm": hole["depth_mm"], "boss_outside_mm": boss,
             "edge_mm": round(outside - hole["diameter_mm"] / 2, 3),    # the least plastic to the outside
             "head_mm": HEAD_MM, "clearance_mm": clearance, "clamped": {"thickness_mm": LID_MM},
             "screw_depth_mm": SCREW_MM - LID_MM}
    (OUT / "insert-joints.json").write_text(json.dumps({"joints": [joint]}, indent=1) + "\n")
    print(f"box {length:g} x {width:g} x {height:g} mm; {ins.thread} insert hole {hole['diameter_mm']} mm, "
          f"{hole['depth_mm']} mm deep, in {boss} mm bosses")
