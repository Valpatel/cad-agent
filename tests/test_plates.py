"""Build plates (cadagent.manufacturing.plates): packing rules, the Bambu Studio project 3MF, byte stability and the
read-back. Hand-built prisms (numpy only), except the project export (trimesh) and the Bambu Studio run (installed)."""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from cadagent.manufacturing import plates as P
from cadagent.manufacturing import slicer
from cadagent.manufacturing.mesh3mf import CORE_NS, mesh_volume

BED = (256.0, 256.0, 256.0)
SETTINGS = {     # the keys of Bambu Studio's project settings that the plates file reads (the rest are its own)
    "version": "02.08.04.57",
    "printable_area": ["0x0", "256x0", "256x256", "0x256"],
    "bed_exclude_area": ["0x0", "18x0", "18x28", "0x28"],
    "curr_bed_type": "Cool Plate",
    "cool_plate_temp": ["35", "0"],
    "textured_plate_temp": ["65", "70"],
    "hot_plate_temp": ["55", "70"],
    "eng_plate_temp": ["0", "70"],
    "supertack_plate_temp": ["35", "70"],
}


def settings_bytes(**changes) -> bytes:
    return (json.dumps({**SETTINGS, **changes}, indent=4, sort_keys=True) + "\n").encode()


def prism(outline, height, origin=(0.0, 0.0, 0.0)):
    """A closed mesh: a convex outline (counter-clockwise, mm) extruded ``height`` up from ``origin``."""
    n = len(outline)
    ring = np.array([[x, y] for x, y in outline], dtype=float)
    v = np.vstack([np.c_[ring, np.zeros(n)], np.c_[ring, np.full(n, float(height))]]) + np.array(origin, dtype=float)
    f = [[0, i + 1, i] for i in range(1, n - 1)] + [[n, n + i, n + i + 1] for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        f += [[i, j, n + j], [i, n + j, n + i]]
    return v, np.array(f, dtype=np.int64)


def box(w, d, h=10.0, origin=(0.0, 0.0, 0.0)):
    return prism([(0, 0), (w, 0), (w, d), (0, d)], h, origin)


def disc(r, h=10.0, sides=24):
    return prism([(r * math.cos(2 * math.pi * k / sides), r * math.sin(2 * math.pi * k / sides)) for k in range(sides)], h)


def copies_of(part, mesh, n, group=""):
    fp = P.footprint(mesh[0])
    return [P.Copy(part, k, fp, group) for k in range(1, n + 1)]


def apart(a: P.Placement, b: P.Placement) -> float:
    """Distance between two footprint rectangles along the axis that separates them (negative: they overlap)."""
    return max(b.x - (a.x + a.width), a.x - (b.x + b.width), b.y - (a.y + a.depth), a.y - (b.y + b.depth))


def assert_rules(layout, copies, bed=BED, gap=5.0, margin=5.0, keep_out=()):
    """The packing rules, checked here without the module's own check_plates."""
    placed = [(p, q) for p in layout for q in p.placements]
    assert sorted((q.part, q.copy) for _, q in placed) == sorted((c.part, c.copy) for c in copies)
    group = {(c.part, c.copy): c.group for c in copies}
    for p, q in placed:
        assert group[q.part, q.copy] == p.group
        assert margin - 1e-9 <= q.x and q.x + q.width <= bed[0] - margin + 1e-9
        assert margin - 1e-9 <= q.y and q.y + q.depth <= bed[1] - margin + 1e-9
        clear = max(gap, P.KEEP_OUT_MIN_MM)
        for x0, y0, x1, y1 in keep_out:
            assert max(x0 - (q.x + q.width), q.x - x1, y0 - (q.y + q.depth), q.y - y1) >= clear - 1e-9, (q, keep_out)
    for p in layout:
        for i, a in enumerate(p.placements):
            for b in p.placements[i + 1:]:
                assert apart(a, b) >= gap - 1e-9, (a, b)
    assert [p.index for p in layout] == list(range(1, len(layout) + 1))


# ---------------------------------------------------------------------------------------------------------------
# Footprints

def test_footprint_is_the_convex_hull_whatever_the_vertex_order():
    ell = [(0, 0), (40, 0), (40, 10), (10, 10), (10, 30), (0, 30)]      # an L: its inner corner is not on the hull
    v = np.array([(x, y, z) for x, y in ell for z in (0, 5)], dtype=float)
    fp = P.footprint(v)
    assert fp.hull == ((0, 0), (40, 0), (40, 10), (10, 30), (0, 30))
    assert fp.area() == pytest.approx(40 * 10 + 10 * 20 + 30 * 20 / 2)
    rng = np.random.default_rng(3)
    assert P.footprint(rng.permutation(v)).hull == fp.hull
    v, _ = box(30, 20, 7, origin=(-5, 4, 2))
    fp = P.footprint(v)
    assert len(fp.hull) == 4 and fp.height == pytest.approx(7)
    assert fp.size(0) == pytest.approx((30, 20)) and fp.size(90) == pytest.approx((20, 30))
    assert fp.area() == pytest.approx(600)
    assert fp.size(45) == pytest.approx((50 / math.sqrt(2), 50 / math.sqrt(2)))


def test_rotation_is_exact_at_quarter_turns():
    assert [P.rotation(a) for a in (0, 90, 180, 270, 360, -90)] == [
        (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0), (1.0, 0.0), (0.0, -1.0)]
    c, s = P.rotation(30)
    assert (c, s) == (round(math.cos(math.pi / 6), 12), 0.5)


# ---------------------------------------------------------------------------------------------------------------
# Packing

def test_two_squares_golden_layout():
    """Two 100 mm squares, 5 mm apart, centred on the bed together: x 25.5 and 130.5, y 78 (whole micrometres)."""
    layout = P.pack(copies_of("sq", box(100, 100), 2), BED, gap=5, margin=5)
    assert len(layout) == 1
    assert [(q.copy, q.x, q.y, q.width, q.depth, q.angle) for q in layout[0].placements] == [
        (1, 25.5, 78.0, 100.0, 100.0, 0), (2, 130.5, 78.0, 100.0, 100.0, 0)]
    assert layout.method == {"sort": "area", "fit": "short-side"}


def test_exact_fit_with_no_gap():
    """Four 123 mm squares fill a 256 mm bed less 5 mm margins (246 mm) exactly, with gap 0."""
    copies = copies_of("sq", box(123, 123), 4)
    layout = P.pack(copies, BED, gap=0, margin=5)
    assert len(layout) == 1
    assert_rules(layout, copies, gap=0)
    assert sorted((q.x, q.y) for q in layout[0].placements) == [(5, 5), (5, 128), (128, 5), (128, 128)]
    assert len(P.pack(copies_of("sq", box(123.001, 123), 4), BED, gap=0, margin=5)) == 2


@pytest.mark.parametrize("seed", range(12))
def test_random_parts_keep_every_rule(seed):
    rng = random.Random(seed)
    copies = []
    for k in range(rng.randint(3, 9)):
        w, d = rng.uniform(5, 180), rng.uniform(5, 120)
        mesh = disc(w / 2) if rng.random() < 0.3 else box(w, d)
        copies += copies_of(f"p{k}", mesh, rng.randint(1, 6), group=rng.choice(["PLA", "PETG", "TPU"]))
    keep_out = [(0, 0, 18, 28)] if seed % 2 else []
    gap, margin = rng.choice([0, 2, 5]), rng.choice([0, 3, 5])
    layout = P.pack(copies, BED, gap=gap, margin=margin, keep_out=keep_out)
    assert_rules(layout, copies, gap=gap, margin=margin, keep_out=keep_out)
    assert not P.check_plates(layout, BED, gap, margin, keep_out,
                              quantities={c.part: sum(1 for d in copies if d.part == c.part) for c in copies})
    # a group's plates are numbered together, in the order the copies first name the groups
    order = list(dict.fromkeys(c.group for c in copies))
    assert [p.group for p in layout] == sorted((p.group for p in layout), key=order.index)


def test_same_parts_in_any_order_give_the_same_layout():
    copies = (copies_of("a", box(80, 40), 5, "PLA") + copies_of("b", disc(22), 7, "PLA")
              + copies_of("c", box(150, 30), 2, "PLA"))
    first = P.pack(copies, BED)
    shuffled = list(copies)
    random.Random(1).shuffle(shuffled)
    again = P.pack(shuffled, BED)
    assert [(p.index, p.placements) for p in again] == [(p.index, p.placements) for p in first]


def test_filaments_never_share_a_plate():
    copies = copies_of("a", box(20, 20), 3, "PLA") + copies_of("b", box(20, 20), 3, "PETG")
    layout = P.pack(copies, BED)
    assert [(p.group, len(p.placements)) for p in layout] == [("PLA", 3), ("PETG", 3)]
    assert not P.check_plates(layout, BED, 5, 5, groups={"a": "PLA", "b": "PETG"})
    assert P.check_plates(layout, BED, 5, 5, groups={"a": "PETG", "b": "PETG"})


def test_check_plates_finds_each_broken_rule():
    plate = P.Plate(1, "PLA", [P.Placement("a", 1, 2.0, 10.0, 50, 50), P.Placement("a", 2, 54.0, 10.0, 50, 50),
                               P.Placement("b", 1, 200.0, 220.0, 50, 50), P.Placement("c", 1, 120, 120, 10, 10)])
    problems = P.check_plates([plate], BED, gap=5, margin=5, keep_out=[(115, 115, 125, 125)],
                              quantities={"a": 2, "b": 2})
    text = "\n".join(problems)
    assert "a #1 is outside the bed" in text and "b #1 is outside the bed" in text
    assert "a #1 and a #2 are 2.000 mm apart" in text
    assert "c #1 is closer than 5 mm to a keep-out area" in text
    assert "b: 1 on the plates, 2 wanted" in text and "c: 1 on the plates, 0 wanted" in text
    overlap = P.Plate(1, "", [P.Placement("a", 1, 10, 10, 50, 50), P.Placement("a", 2, 30, 30, 50, 50)])
    assert "overlap" in P.check_plates([overlap], BED, 0, 0)[0]


def test_quarter_turn_only_when_it_helps():
    """A long part turns a quarter to fit beside others; a round one is never turned."""
    assert [o[0] for o in P.orientations(P.footprint(box(200, 40)[0]), (246, 246))] == [0, 90]
    assert [o[0] for o in P.orientations(P.footprint(disc(30)[0]), (246, 246))] == [0]
    assert [o[0] for o in P.orientations(P.footprint(box(200, 40)[0]), (246, 246), rotate=False)] == [0]
    copies = copies_of("bar", box(240, 40), 1) + copies_of("post", box(40, 240), 1)
    layout = P.pack(copies, BED, gap=5, margin=5)
    assert len(layout) == 1 and {q.angle for q in layout[0].placements} <= {0, 90}
    assert_rules(layout, copies)


def test_a_leg_longer_than_the_bed_is_laid_diagonally():
    """A 267 x 40 mm leg fits a 246 mm usable square only turned: the smallest box that fits, a whole degree."""
    fp = P.footprint(box(267, 40)[0])
    (angle, w, d), = P.orientations(fp, (246, 246))
    assert angle not in (0, 90) and 0 < angle < 180
    assert w <= 246 and d <= 246
    for a in range(1, 180):         # no whole-degree turn that fits has a smaller box
        aw, ad = fp.size(a)
        if aw <= 246 and ad <= 246:
            assert aw * ad >= w * d - 1e-6
    copies = [P.Copy("shin", 1, fp)]
    layout = P.pack(copies, BED)
    assert layout[0].placements[0].angle == angle
    assert_rules(layout, copies)
    with pytest.raises(P.PlatesError, match="does not fit the bed less its 5 mm margins .* as modelled"):
        P.pack(copies, BED, rotate=False)


def test_parts_that_cannot_be_laid_out_are_errors():
    with pytest.raises(P.PlatesError, match="slab: its 300.0 x 300.0 mm footprint does not fit"):
        P.pack(copies_of("slab", box(300, 300), 1), BED)
    with pytest.raises(P.PlatesError, match="tower: 300.0 mm tall"):
        P.pack(copies_of("tower", box(20, 20, 300), 1), BED)
    with pytest.raises(P.PlatesError, match="more than 36 plates"):
        P.pack(copies_of("big", box(200, 200), 37), BED)
    with pytest.raises(P.PlatesError, match="more than 3 plates"):
        P.pack(copies_of("big", box(200, 200), 4), BED, max_plates=3)
    with pytest.raises(P.PlatesError, match="around its keep-out"):
        P.pack(copies_of("big", box(240, 240), 1), BED, keep_out=[(100, 100, 120, 120)])
    with pytest.raises(P.PlatesError, match="leaves no room"):
        P.pack(copies_of("a", box(10, 10), 1), BED, margin=128)
    assert len(P.pack(copies_of("big", box(200, 200), 36), BED)) == 36


@pytest.mark.parametrize("gap", [0, 5])
def test_a_diagonal_part_keeps_clear_of_the_corner_in_the_written_file(tmp_path, gap):
    """A part turned to a whole degree is written rounded to 1e-4 mm. Touching the keep-out area in the layout could
    put a vertex nanometres inside it, which Bambu Studio refuses to slice; the layout keeps a clearance instead, and
    the written vertices keep it too."""
    keep_out = [(0, 0, 18, 28)]
    rng = random.Random(9)
    meshes = {"bar": box(287, 13.7, 5)}
    copies = copies_of("bar", meshes["bar"], 1)
    for k in range(4):
        meshes[f"f{k}"] = box(rng.uniform(20, 60), rng.uniform(20, 60), 5)
        copies += copies_of(f"f{k}", meshes[f"f{k}"], 2)
    layout = P.pack(copies, BED, gap=gap, margin=5, keep_out=keep_out)
    assert any(q.angle % 90 for p in layout for q in p.placements)
    assert_rules(layout, copies, gap=gap, keep_out=keep_out)
    out = tmp_path / "bar.3mf"
    P.write_plates_3mf(out, meshes, layout, bed_xy=BED, gap=gap, margin=5, keep_out=keep_out)
    with zipfile.ZipFile(out) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
    ns = {"m": CORE_NS}
    verts = {o.get("id"): np.array([[float(v.get(k)) for k in "xy"] for v in o.iterfind("m:mesh/m:vertices/m:vertex", ns)])
             for o in model.iterfind("m:resources/m:object", ns)}
    origin = {p.index: P.plate_origin(p.index, len(layout), (256, 256)) for p in layout}
    nearest = math.inf
    for item in model.iterfind("m:build/m:item", ns):
        t = [float(c) for c in item.get("transform").split()]
        world = verts[item.get("objectid")] @ np.array(t[:9]).reshape(3, 3)[:2, :2] + np.array(t[9:11])
        plate = next(i for i, (ox, oy) in origin.items() if ox <= world[:, 0].min() < ox + 256 and oy <= world[:, 1].min() < oy + 256)
        x, y = world[:, 0] - origin[plate][0], world[:, 1] - origin[plate][1]
        nearest = min(nearest, float(np.max([0 - x, x - 18, 0 - y, y - 28], axis=0).min()))   # each vertex's clearance
    assert nearest >= max(gap, P.KEEP_OUT_MIN_MM) - 1e-3


def test_keep_out_corner_stays_clear_on_a_full_plate():
    keep_out = [(0, 0, 18, 28)]
    copies = copies_of("chip", box(14, 14, 3), 120)
    layout = P.pack(copies, BED, gap=2, margin=2, keep_out=keep_out)
    assert_rules(layout, copies, gap=2, margin=2, keep_out=keep_out)
    assert len(layout) == 1


# ---------------------------------------------------------------------------------------------------------------
# Bambu Studio's grid of plates

def test_plate_grid_matches_bambu_studio():
    assert [P.columns(n) for n in range(1, 11)] == [1, 2, 2, 2, 3, 3, 3, 3, 3, 4]
    assert P.plate_origin(1, 1, (256, 256)) == (0, 0)
    assert P.plate_origin(2, 2, (256, 256)) == pytest.approx((307.2, 0))
    assert P.plate_origin(4, 5, (256, 256)) == pytest.approx((0, -307.2))      # 3 columns: plate 4 starts row 2
    assert P.plate_origin(6, 5, (300, 200)) == pytest.approx((720, -240))
    area, plate_mm = P.printable_area({"printable_area": ["-1.5x0", "254.7x0", "254.7x250.2", "-1.5x250.2"]}, BED)
    assert area == (-1.5, 0, 254.7, 250.2) and plate_mm == (256, 250)
    assert P.printable_area(None, (180, 180)) == ((0, 0, 180, 180), (180, 180))


def test_application_names_bambu_studio_only_for_its_own_settings():
    assert P.application({"version": "02.08.04.57"}) == "BambuStudio-02.08.04.57"
    assert P.application({"version": "2.8"}) == "cad-agent"
    assert P.application(None) == "cad-agent"


def test_bed_type_is_one_every_filament_on_the_plate_has_a_temperature_for():
    assert P.bed_type(SETTINGS, [0]) == "Cool Plate"
    assert P.bed_type(SETTINGS, [1]) == "Textured PEI Plate"             # PETG lists the Cool Plate at 0
    assert P.bed_type(SETTINGS, [1], "High Temp Plate") == "High Temp Plate"
    assert P.bed_type(SETTINGS, [0, 1], "Engineering Plate") == "Textured PEI Plate"
    assert P.bed_type({k: ["0"] for k in P.BED_TYPES.values()}, [0]) is None


# ---------------------------------------------------------------------------------------------------------------
# The project 3MF

def demo_set():
    meshes = {"base": box(120, 80, 20, origin=(30, -10, 5)), "knob": disc(14, 18), "rail": box(230, 14, 10)}
    copies = (copies_of("base", meshes["base"], 1, "PLA") + copies_of("rail", meshes["rail"], 3, "PLA")
              + copies_of("knob", meshes["knob"], 4, "PETG"))
    return meshes, copies


def write_demo(path, settings=None, **kw):
    meshes, copies = demo_set()
    layout = P.pack(copies, BED, keep_out=[(0, 0, 18, 28)])
    back = P.write_plates_3mf(path, meshes, layout, bed_xy=BED, gap=5, margin=5, keep_out=[(0, 0, 18, 28)],
                              extruders={"base": 1, "rail": 1, "knob": 2},
                              plate_names={p.index: f"{p.group} plate" for p in layout},
                              bed_types={2: "Textured PEI Plate"}, project_settings=settings, title="Demo", **kw)
    return meshes, copies, layout, back


def test_project_3mf_structure(tmp_path):
    out = tmp_path / "demo-plates.3mf"
    meshes, copies, layout, back = write_demo(out, settings_bytes())
    assert [p.group for p in layout] == ["PLA", "PETG"]
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names == sorted(names) == ["3D/3dmodel.model", "Metadata/model_settings.config",
                                          "Metadata/project_settings.config", "[Content_Types].xml", "_rels/.rels"]
        for info in z.infolist():
            assert (info.date_time, info.create_system, info.external_attr >> 16) == ((1980, 1, 1, 0, 0, 0), 3, 0o100644)
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        config = ET.fromstring(z.read("Metadata/model_settings.config"))
        assert z.read("Metadata/project_settings.config") == settings_bytes()
    ns = {"m": CORE_NS}
    meta = {m.get("name"): m.text for m in model.iterfind("m:metadata", ns)}
    assert meta["Application"] == "BambuStudio-02.08.04.57"
    assert meta["BambuStudio:3mfVersion"] == "1" and "cad-agent" in meta["Description"]
    objects = {o.get("id"): o.get("name") for o in model.iterfind("m:resources/m:object", ns)}
    assert sorted(objects.values()) == ["base", "knob", "rail"]
    items = model.findall("m:build/m:item", ns)
    assert len(items) == 8
    extruder = {o.get("id"): {m.get("key"): m.get("value") for m in o.iterfind("metadata")} for o in config.iterfind("object")}
    assert {v["name"]: v["extruder"] for v in extruder.values()} == {"base": "1", "rail": "1", "knob": "2"}
    plates = config.findall("plate")
    assert len(plates) == 2
    identify = []
    for el, p in zip(plates, layout):
        m = {x.get("key"): x.get("value") for x in el.iterfind("metadata")}
        assert m["plater_id"] == str(p.index) and m["plater_name"] == f"{p.group} plate" and m["locked"] == "false"
        assert m.get("bed_type") == ("Textured PEI Plate" if p.index == 2 else None)
        inst = [{x.get("key"): x.get("value") for x in i.iterfind("metadata")} for i in el.iterfind("model_instance")]
        assert sorted(objects[i["object_id"]] for i in inst) == sorted(q.part for q in p.placements)
        identify += [int(i["identify_id"]) for i in inst]
    assert identify == list(range(1, 9))
    # each copy lies on its plate of Bambu Studio's grid: plate 2 of 2 is 1.2 beds to the right
    for p in back["plates"]:
        assert all(abs(q["z_mm"]) < 1e-9 for q in p["placements"])
    t = [float(c) for c in items[-1].get("transform").split()]
    assert t[9] > 307.2 and t[10] < 256


def test_without_project_settings_the_file_names_cad_agent(tmp_path):
    out = tmp_path / "plain.3mf"
    write_demo(out)
    with zipfile.ZipFile(out) as z:
        assert "Metadata/project_settings.config" not in z.namelist()
        model = z.read("3D/3dmodel.model").decode()
    assert '<metadata name="Application">cad-agent</metadata>' in model and "BambuStudio" not in model


def test_same_parts_give_the_same_bytes(tmp_path, monkeypatch):
    import time
    a, b = tmp_path / "a.3mf", tmp_path / "b.3mf"
    write_demo(a, settings_bytes())
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1900000000")
    monkeypatch.setattr(time, "time", lambda: 2_000_000_000.0)
    monkeypatch.setattr(time, "localtime", lambda *_: time.struct_time((2033, 5, 18, 3, 33, 20, 2, 138, 0)))
    write_demo(b, settings_bytes())
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()


def test_read_back_round_trip(tmp_path):
    out = tmp_path / "demo-plates.3mf"
    meshes, copies, layout, back = write_demo(out, settings_bytes())
    again = P.read_plates_3mf(out)
    assert again["outside"] == [] and again["plate_mm"] == [256, 256]
    assert [p["name"] for p in again["plates"]] == ["PLA plate", "PETG plate"]
    for want, got in zip(layout, P.as_plates(again)):
        assert [(q.part, q.angle) for q in got.placements] == [(q.part, q.angle % 360) for q in want.placements]
        for q, r in zip(want.placements, got.placements):
            assert (r.x, r.y, r.width, r.depth) == pytest.approx((q.x, q.y, q.width, q.depth), abs=2e-3)
    quantities = {"base": 1, "rail": 3, "knob": 4}
    assert not P.check_plates(P.as_plates(again), BED, 5, 5, [(0, 0, 18, 28)], quantities, tol=P.POSITION_TOL_MM)
    for o in again["objects"].values():
        v, f = meshes[o["name"]]
        assert o["triangles"] == len(f) and o["volume_mm3"] == pytest.approx(mesh_volume(v, f), rel=1e-5)  # 1e-4 mm


def test_a_layout_that_breaks_the_rules_is_not_written(tmp_path):
    meshes, _ = demo_set()
    fp = P.footprint(meshes["knob"][0])
    w, d = fp.size(0)
    bad = [P.Plate(1, "PLA", [P.Placement("knob", 1, 50, 50, w, d), P.Placement("knob", 2, 60, 50, w, d)])]
    out = tmp_path / "bad.3mf"
    with pytest.raises(P.PlatesError, match="read-back does not match the layout: .*overlap"):
        P.write_plates_3mf(out, meshes, bad, bed_xy=BED, gap=5, margin=5)
    assert list(tmp_path.iterdir()) == []


def test_the_svg_shows_each_plate_and_outline():
    meshes, copies = demo_set()
    layout = P.pack(copies, BED, keep_out=[(0, 0, 18, 28)])
    fps = {n: P.footprint(m[0]) for n, m in meshes.items()}
    svg = P.plates_svg(layout, fps, BED, margin=5, keep_out=[(0, 0, 18, 28)], labels={1: "PLA 1", 2: "PETG 1"},
                       title="Demo")
    root = ET.fromstring(svg)
    _, _, vw, vh = (float(v) for v in root.get("viewBox").split())
    assert (float(root.get("width")), float(root.get("height"))) == pytest.approx((vw, vh), abs=0.5)
    assert [P._num(v, d) for v, d in ((2650.0, 0), (1.5, 2), (-0.00001, 4), (300.0, 4), (12.34567, 4))] == [
        "2650", "1.5", "0", "300", "12.3457"]
    assert svg.count("<polygon") == 8 and svg.count('fill="url(#ko)"') == 2
    assert "PLA 1" in svg and "PETG 1" in svg and root.get("viewBox")
    assert svg == P.plates_svg(layout, fps, BED, margin=5, keep_out=[(0, 0, 18, 28)],
                               labels={1: "PLA 1", 2: "PETG 1"}, title="Demo")


# ---------------------------------------------------------------------------------------------------------------
# cad.plates and export-3mf

def project_with(tmp_path, plates_yaml="", parts=None):
    from tests.test_report import GOOD, make_project
    parts = parts or {"box": dict(GOOD), "lid": dict(GOOD)}
    return make_project(tmp_path / "proj", parts=parts, checks_yaml=plates_yaml)


def config(tmp_path, plates_yaml="", parts=None):
    from cadagent.project import load_project
    root = project_with(tmp_path, plates_yaml, parts)
    return P.plates_config(load_project(root), list(parts or ["box", "lid"]))


def test_plates_config_defaults_and_forms(tmp_path):
    cfg = config(tmp_path)
    assert (cfg.parts, cfg.quantities, cfg.gap, cfg.margin, cfg.rotate, cfg.keep_out) == (
        ["box", "lid"], {"box": 1, "lid": 1}, 5.0, 5.0, True, [])
    assert set(cfg.filaments.values()) == {slicer.FILAMENTS["pla"]}
    cfg = config(tmp_path / "b", "  plates:\n    gap_mm: 2\n    rotate: false\n    keep_out: [[0, 0, 18, 28]]\n"
                                 "    parts: {lid: {quantity: 4, filament: petg}}\n")
    assert (cfg.parts, cfg.quantities, cfg.gap, cfg.rotate) == (["lid"], {"lid": 4}, 2.0, False)
    assert cfg.filaments == {"lid": slicer.FILAMENTS["petg"]} and cfg.keep_out == [(0, 0, 18, 28)]
    cfg = config(tmp_path / "c", "  plates: {parts: [lid]}\n  release:\n    quantities: {lid: 3}\n")
    assert cfg.quantities == {"lid": 3}
    assert config(tmp_path / "d", "  plates: false\n") is None


@pytest.mark.parametrize("yaml, message", [
    ("  plates: {spacing: 3}\n", "unknown keys"),
    ("  plates: {gap_mm: -1}\n", "gap_mm must be a number"),
    ("  plates: {rotate: 'yes'}\n", "rotate must be true or false"),
    ("  plates: {keep_out: [[0, 0, 10]]}\n", r"keep_out\[0\]"),
    ("  plates: {keep_out: [[0, 0, .inf, 10]]}\n", r"keep_out\[0\]"),
    ("  plates: {gap_mm: .nan}\n", "gap_mm must be a number"),
    ("  plates: {margin_mm: .inf}\n", "margin_mm must be a number"),
    ("  plates: {bed_type: Glass}\n", "bed_type must be one of"),
    ("  plates: {parts: [box, box]}\n", "listed twice: \\['box'\\]"),
    ("  plates: {parts: [gear]}\n", "not in the parts file: \\['gear'\\]"),
    ("  plates: {parts: {box: {quantity: 0}}}\n", "quantity must be a whole number"),
    ("  plates: {parts: {box: {colour: red}}}\n", "must be a mapping of"),
    ("  plates: 3\n", "must be a mapping"),
])
def test_plates_config_errors(tmp_path, yaml, message):
    from cadagent.project import CadConfigError
    with pytest.raises(CadConfigError, match=message):
        config(tmp_path, yaml)


def stl_project(tmp_path, plates_yaml="", sizes=None):
    trimesh = pytest.importorskip("trimesh")
    sizes = sizes or {"box": (120, 80, 20), "lid": (120, 80, 4)}
    from tests.test_report import GOOD
    root = project_with(tmp_path, plates_yaml, {n: dict(GOOD) for n in sizes})
    for name, (w, d, h) in sizes.items():
        trimesh.creation.box(extents=(w, d, h)).export(str(root / "exports" / f"{name}.stl"))
    return root


def test_export_plates_writes_the_project_file_picture_and_record(tmp_path):
    from cadagent.project import load_project
    root = stl_project(tmp_path, "  plates:\n    parts: {box: {quantity: 2}, lid: {quantity: 3, filament: petg}}\n")
    rec = P.export_plates(load_project(root), settings_bytes=settings_bytes())
    exports = root / "exports"
    assert {p.name for p in exports.glob("demo-plates.*")} == {"demo-plates.3mf", "demo-plates.svg", "demo-plates.json"}
    saved = json.loads((exports / "demo-plates.json").read_text())
    assert saved["format"] == P.MARKER and saved["sha256"] == hashlib.sha256((exports / "demo-plates.3mf").read_bytes()).hexdigest()
    assert saved["keep_out_mm"] == [[0.0, 0.0, 18.0, 28.0]]               # the printer's exclusion corner
    assert [(p["name"], p["bed_type"], len(p["parts"])) for p in saved["plates"]] == [
        ("Bambu PLA Basic", None, 2), ("Bambu PETG HF", "Textured PEI Plate", 3)]
    assert any("Textured PEI Plate" in w for w in saved["warnings"])
    assert saved["project_settings"]["embedded"] and saved["project_settings"]["slicer_version"] == "02.08.04.57"
    assert rec["read_back"] == {"plates": 2, "copies": 5}
    first = {p.name: p.read_bytes() for p in exports.glob("demo-plates.*")}
    P.export_plates(load_project(root), settings_bytes=settings_bytes())
    assert {p.name: p.read_bytes() for p in exports.glob("demo-plates.*")} == first


def test_export_plates_without_bambu_studio_says_what_it_left_out(tmp_path, monkeypatch):
    from cadagent.project import load_project
    monkeypatch.setattr(slicer, "executable", lambda: None)
    root = stl_project(tmp_path)
    rec = P.export_plates(load_project(root))
    assert rec["project_settings"] == {"embedded": False}
    assert any("Bambu Studio is not installed" in w for w in rec["warnings"])
    assert P.export_plates(load_project(stl_project(tmp_path / "off", "  plates: false\n"))) is None


def test_a_profile_bambu_studio_does_not_have_is_a_config_error(tmp_path, monkeypatch):
    from cadagent.project import CadConfigError, load_project
    monkeypatch.setattr(slicer, "executable", lambda: "/fake/BambuStudio")

    def missing(*a, **kw):
        raise KeyError("filament profile 'Bambu TPU 95A HF @BBL P1S 0.4 nozzle' not found")

    monkeypatch.setattr(slicer, "project_settings", missing)
    with pytest.raises(CadConfigError, match="profile Bambu Studio does not have: filament profile 'Bambu TPU"):
        P.export_plates(load_project(stl_project(tmp_path)))


def test_old_plates_files_go_when_a_run_fails_or_plates_are_off(tmp_path, monkeypatch):
    from cadagent.project import load_project
    monkeypatch.setattr(slicer, "executable", lambda: None)
    root = stl_project(tmp_path)
    exports = root / "exports"
    P.export_plates(load_project(root))
    names = {"demo-plates.3mf", "demo-plates.svg", "demo-plates.json"}
    assert names <= {p.name for p in exports.iterdir()}
    import trimesh
    trimesh.creation.box(extents=(300, 300, 4)).export(str(exports / "lid.stl"))
    with pytest.raises(P.PlatesError):
        P.export_plates(load_project(root))
    assert not names & {p.name for p in exports.iterdir()}
    trimesh.creation.box(extents=(120, 80, 4)).export(str(exports / "lid.stl"))
    P.export_plates(load_project(root))
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text() + "  plates: false\n")
    assert P.export_plates(load_project(root)) is None
    assert not names & {p.name for p in exports.iterdir()}
    (exports / "demo-plates.json").write_text('{"format": "something else"}')     # not ours: left alone
    (exports / "demo-plates.svg").write_text("<svg/>")
    P.export_plates(load_project(root))
    assert {"demo-plates.json", "demo-plates.svg"} <= {p.name for p in exports.iterdir()}


def test_a_slicer_that_hangs_leaves_the_file_without_settings(tmp_path, monkeypatch):
    from cadagent.project import load_project
    monkeypatch.setattr(slicer, "executable", lambda: "/fake/BambuStudio")

    def hang(*a, **kw):
        raise subprocess.TimeoutExpired("bambu-studio", 300)

    monkeypatch.setattr(slicer, "project_settings", hang)
    rec = P.export_plates(load_project(stl_project(tmp_path)))
    assert rec["project_settings"] == {"embedded": False}
    assert any("no project settings" in w and "timed out" in w for w in rec["warnings"])


def test_export_3mf_command_writes_the_plates(tmp_path, capsys, monkeypatch):
    from cadagent.cli import main
    monkeypatch.setattr(slicer, "executable", lambda: None)
    root = stl_project(tmp_path, "  plates: {parts: {box: {quantity: 6}}}\n")
    assert main(["export-3mf", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "plate 2" in out and "6 copies on 2 plate(s), read back -> demo-plates.3mf" in out
    root = stl_project(tmp_path / "big", sizes={"box": (120, 80, 20), "lid": (300, 300, 4)})
    assert main(["export-3mf", "--project", str(root)]) == 1
    assert "plates: FAILED: lid: its 300.0 x 300.0 mm footprint does not fit" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------------------------
# Bambu Studio itself

@pytest.mark.skipif(slicer.executable() is None, reason="Bambu Studio not installed: a person must open the file once")
def test_bambu_studio_slices_each_plate_as_laid_out():
    """Bambu Studio's command line loads the project with its plates (no re-arranging) and slices each plate with its
    own filament. The snap cannot read /tmp, so the project sits in its own folder under the home directory."""
    from cadagent.project import load_project
    trimesh = pytest.importorskip("trimesh")
    import tempfile
    common = Path.home() / "snap" / "bambu-studio" / "common"
    common.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=common, prefix="cadagent-test-plates-"))
    try:
        root = stl_project(work, "  plates:\n    parts: {box: {quantity: 2}, bar: {}, lid: {quantity: 3, filament: petg}}\n",
                           sizes={"box": (60, 40, 6), "bar": (287, 13.7, 4), "lid": (40, 30, 3)})
        rec = P.export_plates(load_project(root))
        assert rec["project_settings"]["embedded"], rec["warnings"]
        out = work / "sliced"
        p = subprocess.run([slicer.executable(), "--slice", "0", "--outputdir", str(out), rec["path"]],
                           capture_output=True, text=True, timeout=600)
        result = json.loads((out / "result.json").read_text())
        assert p.returncode == 0, result.get("error_string")
        sliced = sorted(result["sliced_plates"], key=lambda s: s["id"])
        assert [len(s["objects"]) for s in sliced] == [len(q["parts"]) for q in rec["plates"]] == [3, 3]
        assert [q["turn_deg"] % 90 != 0 for q in rec["plates"][0]["parts"] if q["part"] == "bar"] == [True]
        assert [[f["id"] for f in s["filaments"]] for s in sliced] == [[1], [2]]
        assert trimesh  # the STLs above were written with it
    finally:
        shutil.rmtree(work, ignore_errors=True)
