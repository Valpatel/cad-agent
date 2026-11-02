"""PrusaSlicer project 3MFs: objects made of several volumes, each volume on its own extruder (tool), the wipe tower's
place, and build plates written one 3MF per plate.

    from cadagent.manufacturing.prusa3mf import write_project, write_plates
    write_project("cab.3mf", [("cab", [(body, "body", 1), (glass, "glass", 3)], (0, 0))], bed=(360, 360, 360))
    write_plates("plates/", {"cab": [(body, "body", 1), (glass, "glass", 3)], "pin": [(pin, "pin", 2)]},
                 bed=(360, 360, 360), quantities={"pin": 4})

**Objects** are ``(name, volumes, place)``. ``volumes`` is a list of ``(mesh, volume name, extruder)``: ``mesh`` is
anything with ``vertices`` and ``faces`` (a trimesh) or a ``(vertices, faces)`` pair, in print orientation and in
the object's own coordinates, so the volumes keep their places relative to one another; ``extruder`` is the 1-based
tool that prints the volume. ``place`` is ``(dx, dy)`` or ``(dx, dy, angle_deg)``: the object is moved so the centre
of the rectangle around its outline sits at the bed's centre plus ``(dx, dy)``, its lowest point on z = 0, turned
``angle_deg`` about z. ``bed`` is ``(width, depth)`` or ``(width, depth, height)`` in mm, the bed from (0, 0).

**The file.** A 3MF core-spec model, one mesh object per object, with every volume's triangles in one block, and
PrusaSlicer's ``Metadata/Slic3r_PE_model.config``: for each object a ``<volume firstid lastid>`` triangle range per
volume, with its name and extruder. When the objects use more than one extruder, the wipe tower's place goes in
``Metadata/Prusa_Slicer_wipe_tower_information.xml`` (``position_x``, ``position_y``, ``rotation_deg`` for bed 0):
PrusaSlicer 2.9 keeps it in the project, not in the print config, and refuses ``wipe_tower_x`` as an override.
``wipe_tower=None`` puts it at ``DEFAULT_WIPE_TOWER``, ``(x, y)`` or ``(x, y, rotation_deg)`` puts it there, and
``False`` writes none. No print, printer or filament settings are written: load those in PrusaSlicer (or pass a
config to its command line).

The file is written with sorted entries and a fixed date, mode and host (``mesh3mf._entry``), so the same objects
give the same bytes. It is read back (``read_project``) and deleted unless every volume has its source mesh's
triangle count and volume (within ``mesh3mf.VOLUME_RTOL``), is watertight, is on its extruder, and every object is
where it was placed.

**Plates** (``write_plates``) pack every part at its quantity with ``cadagent.manufacturing.plates``' MaxRects
layout, grouped by the tools a part uses (or by ``groups``, e.g. filament), and write one project 3MF per plate.
On a plate that uses more than one extruder, the parts keep ``wipe_tower_size`` (an estimate: PrusaSlicer sizes the
tower from the purge volumes) plus the gap clear of the tower.

Format facts were read from PrusaSlicer's source (``src/libslic3r/Format/3mf.cpp``, 2.9; AGPL-3.0, read for the
format only, no code taken) and checked by loading and slicing written files with PrusaSlicer 2.9.4. Limits: the
read-back checks the file, not the print; that the tower clears the parts is the slicer's check (it stops with
"gcode path conflicts" when it does not), and nothing here says a part prints well.
"""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from xml.sax.saxutils import escape, quoteattr

from cadagent._deps import require
from cadagent.manufacturing import plates as P
from cadagent.manufacturing.mesh3mf import (CONTENT_TYPES, CORE_NS, RELS, VOLUME_RTOL, _entry, is_edge_manifold,
                                            mesh_volume)

np = require("numpy", "PrusaSlicer 3MF writing")

SLIC3RPE_NS = "http://schemas.slic3r.org/3mf/2017/06"
MODEL_CONFIG = "Metadata/Slic3r_PE_model.config"
WIPE_TOWER_INFO = "Metadata/Prusa_Slicer_wipe_tower_information.xml"
DEFAULT_WIPE_TOWER = (20.0, 20.0, 0.0)          # the front-left corner, clear of parts centred on the bed
DEFAULT_WIPE_TOWER_SIZE = (60.0, 60.0)          # PrusaSlicer's default tower width; its depth is an estimate
POSITION_TOL_MM = 2e-3

Mesh = Any
Volume = Tuple[Mesh, str, int]
Place = Union[Tuple[float, float], Tuple[float, float, float]]
Obj = Tuple[str, Sequence[Volume], Place]
WipeTower = Union[None, bool, Tuple[float, float], Tuple[float, float, float]]


class Prusa3mfError(ValueError):
    """The objects cannot be written as asked (an empty object, a bad extruder, a part off the bed), or a written
    file did not read back as written."""


def _arrays(mesh: Mesh) -> Tuple[np.ndarray, np.ndarray]:
    if hasattr(mesh, "vertices") and hasattr(mesh, "faces"):
        v, f = mesh.vertices, mesh.faces
    else:
        v, f = mesh
    return np.asarray(v, dtype=float).reshape(-1, 3), np.asarray(f, dtype=np.int64).reshape(-1, 3)


def _place(place: Place) -> Tuple[float, float, int]:
    if len(place) == 2:
        return float(place[0]), float(place[1]), 0
    if len(place) == 3:
        return float(place[0]), float(place[1]), int(place[2])
    raise Prusa3mfError(f"a place is (dx, dy) or (dx, dy, angle_deg), not {place!r}")


def _tower(wipe_tower: WipeTower, extruders: Sequence[int]) -> Optional[Tuple[float, float, float]]:
    """The wipe tower's ``(x, y, rotation_deg)`` to write, or None."""
    if wipe_tower is False:
        return None
    if wipe_tower is None or wipe_tower is True:
        return DEFAULT_WIPE_TOWER if (len(set(extruders)) > 1 or wipe_tower is True) else None
    t = tuple(float(v) for v in wipe_tower)
    if len(t) == 2:
        return (t[0], t[1], 0.0)
    if len(t) == 3:
        return t
    raise Prusa3mfError(f"wipe_tower is None, False, (x, y) or (x, y, rotation_deg), not {wipe_tower!r}")


def tower_keep_out(tower: Tuple[float, float, float], size: Sequence[float] = DEFAULT_WIPE_TOWER_SIZE
                   ) -> Tuple[float, float, float, float]:
    """The bed area ``[x0, y0, x1, y1]`` the wipe tower may cover: its rectangle from its front-left corner, or, when
    it is rotated, the square that holds it at any turn about any of its corners."""
    x, y, rot = tower
    w, d = float(size[0]), float(size[1])
    if abs(rot) % 360 < 1e-9:
        return (x, y, x + w, y + d)
    r = math.hypot(w, d)
    return (x - r, y - r, x + r, y + r)


def _layout(objects: Sequence[Obj], bed: Sequence[float]):
    """Per object: the normalised vertices of every volume, faces, ranges and the build-item transform."""
    if not objects:
        raise Prusa3mfError("a project needs at least one object")
    W, D = float(bed[0]), float(bed[1])
    out = []
    for name, vols, place in objects:
        if not vols:
            raise Prusa3mfError(f"{name}: an object needs at least one volume")
        dx, dy, angle = _place(place)
        arrays = []
        for mesh, vname, ext in vols:
            v, f = _arrays(mesh)
            if len(f) == 0 or len(v) < 3:
                raise Prusa3mfError(f"{name}/{vname}: an empty mesh")
            if f.min() < 0 or f.max() >= len(v):
                raise Prusa3mfError(f"{name}/{vname}: a face refers to a vertex that does not exist")
            if not isinstance(ext, (int, np.integer)) or isinstance(ext, bool) or int(ext) < 1:
                raise Prusa3mfError(f"{name}/{vname}: the extruder is a whole number from 1, not {ext!r}")
            arrays.append((v, f, str(vname), int(ext)))
        allv = np.vstack([a[0] for a in arrays])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        shift = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        normed = [(np.round(v - shift, 4) + 0.0, f, vn, e) for v, f, vn, e in arrays]
        fp = P.footprint(np.vstack([a[0] for a in normed]))
        bx0, by0, bx1, by1 = P._box(P._turn(fp.hull, angle))
        tx, ty = round(W / 2 + dx, 4), round(D / 2 + dy, 4)
        if bx0 + tx < -1e-3 or by0 + ty < -1e-3 or bx1 + tx > W + 1e-3 or by1 + ty > D + 1e-3:
            raise Prusa3mfError(f"{name}: placed at ({tx:g}, {ty:g}) it reaches outside the {W:g} x {D:g} mm bed "
                                f"({bx0 + tx:.2f}..{bx1 + tx:.2f} x {by0 + ty:.2f}..{by1 + ty:.2f} mm)")
        if len(bed) > 2 and fp.height > float(bed[2]) + 1e-6:
            raise Prusa3mfError(f"{name}: {fp.height:.1f} mm tall, the printer builds {float(bed[2]):g} mm")
        out.append({"name": str(name), "volumes": normed, "angle": angle, "position": (tx, ty),
                    "box": (bx0 + tx, by0 + ty, bx1 + tx, by1 + ty)})
    return out


def project_members(objects: Sequence[Obj], bed: Sequence[float], wipe_tower: WipeTower = None,
                    title: str = "") -> Tuple[Dict[str, bytes], List[Dict[str, Any]], Optional[Tuple[float, ...]]]:
    """The files of the project 3MF by archive path, the layout written, and the wipe tower written (or None)."""
    lay = _layout(objects, bed)
    resources, items, configs = [], [], []
    for oid, o in enumerate(lay, start=1):
        verts, tris, vol_xml, off, first = [], [], [], 0, 0
        for v, f, vname, ext in o["volumes"]:
            verts.append("".join(f'<vertex x="{P._num(a, 4)}" y="{P._num(b, 4)}" z="{P._num(c, 4)}"/>'
                                 for a, b, c in v))
            tris.append("".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f + off))
            vol_xml.append(f'  <volume firstid="{first}" lastid="{first + len(f) - 1}">\n'
                           f'   <metadata type="volume" key="name" value={quoteattr(vname)}/>\n'
                           f'   <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
                           f'   <metadata type="volume" key="extruder" value="{ext}"/>\n  </volume>\n')
            off += len(v)
            first += len(f)
        resources.append(f'<object id="{oid}" name={quoteattr(o["name"])} type="model"><mesh><vertices>'
                         + "".join(verts) + "</vertices><triangles>" + "".join(tris) + "</triangles></mesh></object>")
        tx, ty = o["position"]
        items.append(f'<item objectid="{oid}" transform="{P._transform(o["angle"], tx, ty)}" printable="1"/>')
        configs.append(f' <object id="{oid}" instances_count="1">\n'
                       f'  <metadata type="object" key="name" value={quoteattr(o["name"])}/>\n'
                       f'  <metadata type="object" key="extruder" value="{o["volumes"][0][3]}"/>\n'
                       + "".join(vol_xml) + " </object>\n")
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" xmlns:slic3rpe="{SLIC3RPE_NS}">'
             '<metadata name="slic3rpe:Version3mf">1</metadata>'
             '<metadata name="Application">cad-agent</metadata>'
             + (f'<metadata name="Title">{escape(title)}</metadata>' if title else "")
             + "<resources>" + "".join(resources) + "</resources><build>" + "".join(items) + "</build></model>")
    config = '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(configs) + "</config>\n"
    members = {"[Content_Types].xml": CONTENT_TYPES.encode(), "_rels/.rels": RELS.encode(),
               "3D/3dmodel.model": model.encode(), MODEL_CONFIG: config.encode()}
    tower = _tower(wipe_tower, [e for o in lay for *_, e in o["volumes"]])
    if tower is not None:
        members[WIPE_TOWER_INFO] = ('<?xml version="1.0" encoding="utf-8"?>\n<wipe_tower_information bed_idx="0" '
                                    f'position_x="{P._num(tower[0], 4)}" position_y="{P._num(tower[1], 4)}" '
                                    f'rotation_deg="{P._num(tower[2], 4)}"/>\n').encode()
    return members, lay, tower


def read_project(path: Path) -> Dict[str, Any]:
    """What a PrusaSlicer project 3MF holds: per object its name, build-item transform, and per volume its name,
    extruder, vertices and faces (indices into that volume's own vertices); and the wipe tower's place, if any."""
    ns = {"m": CORE_NS}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        config = ET.fromstring(z.read(MODEL_CONFIG)) if MODEL_CONFIG in names else None
        tower_xml = ET.fromstring(z.read(WIPE_TOWER_INFO)) if WIPE_TOWER_INFO in names else None
    meshes = {}
    for obj in root.iterfind("m:resources/m:object", ns):
        v = np.array([[float(q.get(k)) for k in "xyz"] for q in obj.iterfind("m:mesh/m:vertices/m:vertex", ns)],
                     dtype=float).reshape(-1, 3)
        f = np.array([[int(q.get(k)) for k in ("v1", "v2", "v3")]
                      for q in obj.iterfind("m:mesh/m:triangles/m:triangle", ns)], dtype=np.int64).reshape(-1, 3)
        meshes[obj.get("id")] = (obj.get("name") or "", v, f)
    cfg = {}
    for obj in (config.iterfind("object") if config is not None else ()):
        name = next((m.get("value") for m in obj.iterfind("metadata") if m.get("key") == "name"), "")
        vols = []
        for vol in obj.iterfind("volume"):
            meta = {m.get("key"): m.get("value") for m in vol.iterfind("metadata")}
            vols.append((int(vol.get("firstid")), int(vol.get("lastid")), meta.get("name", ""),
                         int(meta.get("extruder", "0") or 0)))
        cfg[obj.get("id")] = (name, vols)
    objects = []
    for item in root.iterfind("m:build/m:item", ns):
        oid = item.get("objectid")
        mname, v, f = meshes[oid]
        cname, ranges = cfg.get(oid, (mname, [(0, len(f) - 1, mname, 0)]))
        m = [float(x) for x in (item.get("transform") or "1 0 0 0 1 0 0 0 1 0 0 0").split()]
        vols = []
        for first, last, vname, ext in ranges:
            sub = f[first:last + 1]
            used = np.unique(sub)
            remap = np.full(len(v), -1, dtype=np.int64)
            remap[used] = np.arange(len(used))
            vols.append({"name": vname, "extruder": ext, "first": first, "last": last,
                         "vertices": v[used], "faces": remap[sub]})
        objects.append({"name": cname, "transform": m, "triangles": len(f), "volumes": vols})
    tower = None
    if tower_xml is not None:
        tower = {"bed_idx": int(tower_xml.get("bed_idx", "0")), "x": float(tower_xml.get("position_x")),
                 "y": float(tower_xml.get("position_y")), "rotation_deg": float(tower_xml.get("rotation_deg", "0"))}
    return {"objects": objects, "wipe_tower": tower}


def verify_project(path: Path, layout: List[Dict[str, Any]], tower: Optional[Tuple[float, ...]]) -> Dict[str, Any]:
    """Compare a written project with what was meant to be written. ``ok`` is the verdict; ``problems`` says why."""
    back = read_project(path)
    problems: List[str] = []
    objs = []
    if len(back["objects"]) != len(layout):
        problems.append(f"{len(back['objects'])} objects read back, {len(layout)} written")
    for o, b in zip(layout, back["objects"]):
        vols = []
        covered = sum(vb["last"] - vb["first"] + 1 for vb in b["volumes"])
        if covered != b["triangles"]:
            problems.append(f"{o['name']}: the volume ranges cover {covered} of {b['triangles']} triangles")
        c, s = P.rotation(o["angle"])
        want = [c, s, 0, -s, c, 0, 0, 0, 1, o["position"][0], o["position"][1], 0]
        if b["name"] != o["name"] or len(b["transform"]) != 12 or \
                max(abs(x - y) for x, y in zip(b["transform"], want)) > POSITION_TOL_MM:
            problems.append(f"{o['name']}: read back as {b['name']!r} with transform {b['transform']}")
        if len(b["volumes"]) != len(o["volumes"]):
            problems.append(f"{o['name']}: {len(b['volumes'])} volumes read back, {len(o['volumes'])} written")
        for (v, f, vname, ext), vb in zip(o["volumes"], b["volumes"]):
            ref = mesh_volume(v, f)
            vol = mesh_volume(vb["vertices"], vb["faces"]) if len(vb["faces"]) else 0.0
            r = {"name": vb["name"], "extruder": vb["extruder"], "triangles": int(len(vb["faces"])),
                 "source_triangles": int(len(f)), "watertight": bool(is_edge_manifold(vb["faces"])),
                 "volume_mm3": round(vol, 3), "source_volume_mm3": round(ref, 3)}
            r["ok"] = bool(vb["name"] == vname and vb["extruder"] == ext and r["triangles"] == len(f)
                           and r["watertight"] and ref != 0 and abs(vol - ref) <= VOLUME_RTOL * abs(ref))
            if not r["ok"]:
                problems.append(f"{o['name']}/{vname}: read back {r}, extruder {ext} written")
            vols.append(r)
        objs.append({"name": o["name"], "position": list(o["position"]), "angle": o["angle"],
                     "bounds_xy": [round(x, 4) for x in o["box"]], "volumes": vols})
    bt = back["wipe_tower"]
    if (tower is None) != (bt is None) or (tower is not None and (
            bt["bed_idx"] != 0 or max(abs(bt[k] - t) for k, t in zip(("x", "y", "rotation_deg"), tower)) > 1e-3)):
        problems.append(f"wipe tower read back as {bt}, {tower} written")
    return {"file": str(path), "objects": objs,
            "extruders": sorted({v["extruder"] for o in objs for v in o["volumes"]}),
            "wipe_tower": None if tower is None else {"x": tower[0], "y": tower[1], "rotation_deg": tower[2]},
            "problems": problems, "ok": not problems}


def write_project(path: Path, objects: Sequence[Obj], bed: Sequence[float], wipe_tower: WipeTower = None,
                  title: str = "") -> Dict[str, Any]:
    """Write one PrusaSlicer project 3MF and verify it (see the module docstring). Returns the read-back report,
    with the file's ``sha256``; raises ``Prusa3mfError`` (and removes the file) when it does not read back as
    written."""
    path = Path(path)
    members, lay, tower = project_members(objects, bed, wipe_tower, title or path.stem)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for member in sorted(members):
            z.writestr(_entry(member), members[member])
    report = verify_project(path, lay, tower)
    if not report["ok"]:
        path.unlink(missing_ok=True)
        raise Prusa3mfError(f"{path.name}: read-back mismatch: {'; '.join(report['problems'])}")
    report["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return report


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "plate"


def tools_group(volumes: Sequence[Volume]) -> str:
    """The default plate group of a part: the tools it uses, ``T1`` or ``T1+T3``."""
    return "+".join(f"T{e}" for e in sorted({int(e) for _, _, e in volumes}))


def write_plates(directory: Path, parts: Dict[str, Sequence[Volume]], bed: Sequence[float], *,
                 quantities: Optional[Dict[str, int]] = None, groups: Optional[Dict[str, str]] = None,
                 gap: float = P.DEFAULT_GAP_MM, margin: float = P.DEFAULT_MARGIN_MM, rotate: bool = True,
                 keep_out: Sequence[Sequence[float]] = (), wipe_tower: WipeTower = None,
                 wipe_tower_size: Sequence[float] = DEFAULT_WIPE_TOWER_SIZE, stem: str = "plate",
                 max_plates: int = 99) -> Dict[str, Any]:
    """Pack every part at its quantity onto plates of the ``bed`` and write one PrusaSlicer project 3MF per plate,
    ``<directory>/<stem>-NN-<group>.3mf``. Earlier ``<stem>-NN-*.3mf`` files there are removed first.

    ``parts`` maps a part to its volumes (as in ``write_project``); ``quantities`` to its copies (default 1);
    ``groups`` to what may not share a plate with another group (default: the tools it uses, ``tools_group``).
    ``gap``, ``margin``, ``rotate`` and ``keep_out`` are ``plates.pack``'s. On a plate with more than one extruder
    the wipe tower (``wipe_tower`` as in ``write_project``) is written, and the parts keep ``wipe_tower_size`` from
    its corner clear of it. Returns the layout and each plate's read-back report."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    quantities = dict(quantities or {})
    unknown = sorted(set(quantities) - set(parts)) + sorted(set(groups or {}) - set(parts))
    if unknown:
        raise Prusa3mfError(f"no volumes for {unknown}")
    norm_parts: Dict[str, List[Tuple[Tuple[np.ndarray, np.ndarray], str, int]]] = {}
    fps = {}
    for name, vols in parts.items():
        if not vols:
            raise Prusa3mfError(f"{name}: a part needs at least one volume")
        arrays = [(_arrays(m), str(vn), e) for m, vn, e in vols]
        allv = np.vstack([a[0][0] for a in arrays])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        shift = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        norm_parts[name] = [((np.round(v - shift, 4) + 0.0, f), vn, e) for (v, f), vn, e in arrays]
        fps[name] = P.footprint(np.vstack([a[0][0] for a in norm_parts[name]]))
    group_of = {n: (groups or {}).get(n) or tools_group(parts[n]) for n in parts}
    order: List[str] = []
    for n in parts:
        if group_of[n] not in order:
            order.append(group_of[n])
    W, D = float(bed[0]), float(bed[1])
    plates: List[Tuple[P.Plate, Optional[Tuple[float, float, float]]]] = []
    method = {}
    for g in order:
        members = [n for n in parts if group_of[n] == g]
        exts = sorted({int(e) for n in members for _, _, e in parts[n]})
        tower = _tower(wipe_tower, exts)
        ko = list(keep_out) + ([list(tower_keep_out(tower, wipe_tower_size))] if tower else [])
        copies = [P.Copy(n, i + 1, fps[n], g) for n in members for i in range(int(quantities.get(n, 1)))]
        if not copies:
            continue
        try:
            lay = P.pack(copies, tuple(bed), gap=gap, margin=margin, rotate=rotate, keep_out=ko,
                         max_plates=max_plates - len(plates))
        except P.PlatesError as exc:
            raise Prusa3mfError(str(exc)) from exc
        method[g] = lay.method
        for p in lay:
            plates.append((P.Plate(len(plates) + 1, g, p.placements), tower))
    for old in directory.glob(f"{stem}-[0-9][0-9]-*.3mf"):
        old.unlink()
    written = []
    for plate, tower in plates:
        objs = []
        for q in plate.placements:
            bx0, by0, _, _ = P._box(P._turn(fps[q.part].hull, q.angle))
            dx, dy = round(q.x - bx0 - W / 2, 4), round(q.y - by0 - D / 2, 4)
            name = q.part if quantities.get(q.part, 1) == 1 else f"{q.part} #{q.copy}"
            objs.append((name, norm_parts[q.part], (dx, dy, q.angle)))
        path = directory / f"{stem}-{plate.index:02d}-{_slug(plate.group)}.3mf"
        report = write_project(path, objs, bed, wipe_tower=tower if tower else False, title=path.stem)
        written.append({"plate": plate.index, "group": plate.group, "file": str(path), "sha256": report["sha256"],
                        "copies": [{"part": q.part, "copy": q.copy, "x": q.x, "y": q.y, "width": q.width,
                                    "depth": q.depth, "angle": q.angle} for q in plate.placements],
                        "wipe_tower": report["wipe_tower"], "report": report})
    return {"plates": written, "method": method}
