"""3D view export: every part in assembly position, for the browser viewer (webkit/viewer.html).

Works for any CAD project: a housing, a bracket set, a mechanism or a robot. ``cad-agent view`` reads each part's STEP
(assembly coordinates, as cad-agent projects export them) and writes ``exports/view/<part>.stl`` (binary, mm) plus
``exports/view/view.json``. Optional config under ``cad: view:``::

    view:
      colors: {base: "#2f343c", cover: "#e8892b"}     # per part; others get a palette colour
      hidden: [base_mount, front_gmsl]                 # alternative variants, off until ticked
      explode: {cover: [0, 0, 1]}                      # explode direction per part (default: away from the centre)
      extra: [{name: carrier, file: references/pcb-outline.step, color: "#2f8f4e"},     # non-printed parts to show
              {glob: "exports/asm_*.step", strip: "asm_"},                         # or many files at once
              {name: board, file: references/board.stl, offset: [15, 15, 20],      # an STL is copied as is (moved by
               category: Carrier, hidden: true}]                                   # offset, mm); off until ticked
      parts: false                                     # skip the parts file (when its STEPs are not in assembly position)
      parts_category: Printed parts                    # list heading for the parts file's parts
      categories: {Test coupons: [m3_insert_coupon, rail_coupon]}   # move named parts to another section
      groups: [{id: two, title: Two-port, prefix: "2port_"}]   # also write exports/view/two.json with only those parts
                                                       # (the id "view" is reserved; groups are checked before any write)

Colours match a part's name exactly, else its name without a trailing _l/_r/_1/... suffix, else its first word.
A ``category`` (on an ``extra`` entry, ``parts_category`` for the parts file, or ``categories`` by part name) heads a section of the viewer's parts
list, with one checkbox that shows or hides the whole section: one viewer for the printed parts, the bought parts and
the board they fit around. A missing extra file is listed as skipped, so reference files that are not redistributed
(a vendor board model) simply drop out of a fresh checkout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from cadagent._deps import require

PALETTE = ["#e8892b", "#5aa9e6", "#5cc8a8", "#c792ea", "#f2c14e", "#8a9099", "#ef6f6c", "#7bd389", "#6f8ab7", "#d4a373"]


def _parts_from(project) -> List[str]:
    path = Path(project.parts_file)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found: build the project first")
    return list(json.loads(path.read_text()))


RESERVED_GROUP_IDS = {"view"}   # exports/view/view.json is the full manifest


def group_manifests(manifest: Dict[str, Any], groups: List[dict]) -> Dict[str, dict]:
    """Select assemblies without duplicating meshes; each selected variant starts visible.

    Raises CadConfigError (a ValueError) for a malformed, duplicate or reserved id, an empty prefix, or a prefix
    that matches no part."""
    import re
    from cadagent.project import CadConfigError
    if not isinstance(groups, list):
        raise CadConfigError("cad.view.groups must be a list of {id, prefix, title}")
    result = {}
    for group in groups:
        if not isinstance(group, dict):
            raise CadConfigError("cad.view.groups entries must be objects {id, prefix, title}")
        identifier = group.get("id", "")
        prefix = group.get("prefix", "")
        if (not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", identifier)
                or not isinstance(prefix, str) or not prefix or identifier in result):
            raise CadConfigError("View groups need unique safe ids and nonempty part-name prefixes")
        if identifier in RESERVED_GROUP_IDS:
            raise CadConfigError(f"View group id {identifier!r} is reserved: exports/view/{identifier}.json is the full manifest")
        selected = [dict(p, visible=True) for p in manifest["parts"] if p["name"].startswith(prefix)]
        if not selected:
            raise CadConfigError(f"View group {identifier!r} has no parts starting with {prefix!r}")
        result[identifier] = dict(manifest, title=group.get("title", identifier), parts=selected)
    return result


def _read_stl(path: Path):
    """(n, 3, 3) float32 triangles from a binary or ASCII STL."""
    data = path.read_bytes()
    # ASCII starts with "solid" and has facets; a binary file's 80-byte header may also start with "solid", so the
    # facet keyword decides, and trailing bytes after the binary records are allowed
    ascii_stl = data[:5].lower() == b"solid" and b"facet" in data[:1024].lower()
    if not ascii_stl and len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if len(data) >= 84 + 50 * n:
            rec = np.frombuffer(data, dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
            return rec["v"].copy()
    text = data.decode("ascii", errors="ignore")
    vertices = [line.split()[1:4] for line in text.splitlines() if line.lstrip().lower().startswith("vertex")]
    if not vertices or len(vertices) % 3:
        raise ValueError(f"{path} is not a readable STL")
    return np.asarray(vertices, dtype=np.float32).reshape(-1, 3, 3)


def _write_stl(path: Path, tri) -> None:
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    normal = np.divide(normal, length, out=np.zeros_like(normal), where=length > 0)
    rec = np.zeros(len(tri), dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]))
    rec["normal"], rec["v"] = normal, tri
    with open(path, "wb") as f:
        f.write(b"cad-agent view mesh".ljust(80, b" "))
        f.write(len(tri).to_bytes(4, "little"))
        f.write(rec.tobytes())


def export_view(project, tolerance: float = 0.1, angular: float = 0.2, out: Optional[Path] = None) -> Dict[str, Any]:
    """Write the meshes and the manifest. Parts without a STEP (or STL) are listed as skipped, not errors.

    ``tolerance`` (mm) and ``angular`` (radians) set the STEP tessellation; ``out`` writes somewhere other than
    ``exports/view`` (a coarser copy for a web page, without touching the project's own export)."""
    cfg = dict(project.view or {})
    colors: Dict[str, str] = cfg.get("colors", {})
    hidden = set(cfg.get("hidden", []))
    explode: Dict[str, List[float]] = cfg.get("explode", {})
    out = Path(out) if out is not None else project.exports_dir / "view"

    # (name, file, colour, offset, category, hidden)
    sources = ([(name, project.exports_dir / f"{name}.step", None, None, cfg.get("parts_category"), False)
                for name in _parts_from(project)] if cfg.get("parts", True) else [])
    from cadagent.project import CadConfigError
    for e in cfg.get("extra", []):
        offset = e.get("offset")
        if offset is not None and not (isinstance(offset, (list, tuple)) and len(offset) == 3
                                       and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in offset)):
            raise CadConfigError(f"cad.view.extra offset must be [x, y, z] in mm, got {offset!r}")
        extra = (e.get("color"), offset, e.get("category"), bool(e.get("hidden")))
        if "glob" in e:
            for f in sorted(project.root.glob(e["glob"])):
                sources.append((f.stem[len(e.get("strip", "")):] if f.stem.startswith(e.get("strip", "")) else f.stem, f, *extra))
        else:
            sources.append((e["name"], project.root / e["file"], *extra))
    by_name = {}
    categories = cfg.get("categories") or {}
    if not isinstance(categories, dict):
        raise CadConfigError("cad.view.categories must map a section title to a list of part names")
    for category, members in categories.items():
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            raise CadConfigError(f"cad.view.categories[{category!r}] must be a list of part names")
        for member in members:
            if member in by_name:
                raise CadConfigError(f"cad.view.categories lists {member!r} under both {by_name[member]!r} and {category!r}")
            by_name[member] = category
    sources = [(name, source, color, offset, by_name.get(name, category), off) for name, source, color, offset, category, off in sources]
    names = [s[0] for s in sources if s[1].is_file()]
    unknown = sorted(set(by_name) - {s[0] for s in sources})
    if unknown:
        raise CadConfigError(f"cad.view.categories names parts that do not exist: {unknown}")
    if len(set(names)) != len(names):
        raise CadConfigError(f"cad.view: two parts are named {sorted({n for n in names if names.count(n) > 1})}")

    # validate the groups against the parts that will be exported before writing anything
    group_manifests({"parts": [{"name": name} for name in names]}, cfg.get("groups", []))
    cq = require("cadquery", "the 3D view export") if any(s[1].is_file() and s[1].suffix.lower() != ".stl" for s in sources) else None
    out.mkdir(parents=True, exist_ok=True)

    def colour_for(name, i):
        import re
        base = re.sub(r"_(l|r|left|right|front|rear|\d+)$", "", name)
        return colors.get(name) or colors.get(base) or colors.get(name.split("_")[0]) or PALETTE[i % len(PALETTE)]
    parts, skipped = [], []
    for i, (name, source, color, offset, category, off) in enumerate(sources):
        if not source.is_file():
            skipped.append(name)
            continue
        stl = out / f"{name}.stl"
        if source.suffix.lower() == ".stl":
            tri = _read_stl(source)
            if offset:
                tri = tri + np.asarray(offset, dtype=np.float32)
            _write_stl(stl, tri)
            flat = tri.reshape(-1, 3)
            bounds = (*flat.min(axis=0).tolist(), *flat.max(axis=0).tolist()) if len(flat) else (0.0,) * 6
        else:
            shape = cq.importers.importStep(str(source))
            if offset:
                shape = shape.translate(cq.Vector(*offset))
            cq.exporters.export(shape, str(stl), tolerance=tolerance, angularTolerance=angular, opt={"ascii": False})
            bb = shape.val().BoundingBox() if hasattr(shape, "val") else shape.BoundingBox()
            bounds = (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)
        part = {
            "name": name, "id": project.part_ids.get(name, ""), "file": stl.name,
            "color": color or colour_for(name, i),
            "visible": not off and name not in hidden and not any(name.startswith(h + "_") for h in hidden),
            "explode": explode.get(name),
            "bounds_mm": [round(float(v), 2) for v in bounds],
        }
        if category:
            part["category"] = str(category)
        parts.append(part)
    manifest = {"title": project.title, "units": "mm", "up": "z", "parts": parts, "skipped": skipped}
    (out / "view.json").write_text(json.dumps(manifest, indent=1) + "\n")
    groups = group_manifests(manifest, cfg.get("groups", []))
    for identifier, group in groups.items():
        (out / f"{identifier}.json").write_text(json.dumps(group, indent=1) + "\n")
    return {"manifest": str(out / "view.json"), "parts": len(parts), "skipped": skipped, "groups": list(groups)}


MODEL_SCHEMA = "cad-agent-model/1"
QUANT = 65535                    # positions are 16-bit steps across the assembly's box


def _weld(tri):
    """(vertices (m, 3) float32, triangles (k, 3) int) from STL triangles: equal corners become one vertex, vertices
    are numbered in the order the triangles first use them, and triangles with two corners at the same point are
    dropped (an STL writer's slivers; a thin triangle with three distinct corners is kept)."""
    flat = np.ascontiguousarray(tri.reshape(-1, 3), dtype=np.float32)
    unique, inverse = np.unique(flat, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    order, first = np.unique(faces.reshape(-1), return_index=True)
    used = order[np.argsort(first)]                    # vertex ids by first use
    renumber = np.empty(len(unique), dtype=np.int64)
    renumber[used] = np.arange(len(used))
    return unique[used], renumber[faces]


def _planes(values, width: int) -> bytes:
    """Unsigned integers as byte planes: every value's lowest byte, then every value's next byte, and so on."""
    return np.ascontiguousarray(values.astype(f"<u{width}").view(np.uint8).reshape(-1, width).T).tobytes()


def pack_view(manifest: Path, out: Path, *, title: Optional[str] = None, colors: Optional[Dict[str, str]] = None,
              source: Optional[Dict[str, Any]] = None, view: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Pack a ``cad-agent view`` export (view.json and its STLs) into one small model for a web page.

    Writes ``<out>.json`` (the parts, their colours and where each lives in the binary) and ``<out>.bin``, gzip-
    compressed here so it arrives small from any static host (the kit's ``<cad-model>``, ``kit/model.js``, inflates it
    with the browser's DecompressionStream). Each part's triangles are welded into shared vertices, numbered in the
    order the triangles first use them. Per part, at ``offset`` in the inflated binary:

    - positions: 16-bit steps across the whole assembly's box (``box_mm``; 0.012 mm on a 0.8 m robot), each
      coordinate stored as the difference from the previous vertex's (modulo 2^16), x then y then z, each as a plane
      of low bytes then a plane of high bytes: ``6 * vertices`` bytes;
    - triangles: each corner as ``next new vertex - vertex`` (0 for a vertex not used before), in ``index_bits``
      16 or 32 bits, as byte planes: ``3 * triangles * index_bits / 8`` bytes.

    The differences and byte planes make the gzip stream about a third smaller than plain arrays. ``colors``
    overrides colours by part name; ``source`` is recorded as given (what was exported, from which revision, how);
    ``view`` is the opening view, ``{"azimuth": deg, "elevation": deg}`` (azimuth from the CAD -y axis towards +x,
    so 90 looks at the +x face). Deterministic: the same input gives the same bytes. Returns the manifest written."""
    import gzip
    import hashlib
    import io

    manifest = Path(manifest)
    exported = json.loads(manifest.read_text())
    meshes = [(part, *_weld(_read_stl(manifest.parent / part["file"]))) for part in exported["parts"]]
    used = [v for _, v, _ in meshes if len(v)]
    every = np.concatenate(used) if used else np.zeros((1, 3), np.float32)
    lo, hi = every.min(axis=0).astype(np.float64), every.max(axis=0).astype(np.float64)
    span = np.where(hi - lo > 0, hi - lo, 1.0)
    blob, parts = bytearray(), []
    for part, vertices, faces in meshes:
        q = np.rint((vertices - lo) / span * QUANT).astype(np.int64)
        steps = np.diff(q, axis=0, prepend=np.zeros((1, 3), np.int64)) & 0xFFFF
        corners = faces.reshape(-1)
        fresh = np.maximum.accumulate(np.concatenate([[-1], corners]))[:-1] + 1     # the next new vertex at each corner
        bits = 16 if len(vertices) < 0x10000 else 32       # a corner's code reaches the vertex count
        entry = {k: part[k] for k in ("name", "id", "category", "visible", "explode", "bounds_mm") if part.get(k) not in (None, "")}
        entry.update(color=(colors or {}).get(part["name"], part["color"]), vertices=len(vertices), triangles=len(faces),
                     offset=len(blob), index_bits=bits)
        for axis in range(3):
            blob += _planes(steps[:, axis], 2)
        blob += _planes(fresh - corners, bits // 8)
        parts.append(entry)
    # GzipFile writes the same header on every Python (gzip.compress hands it to zlib from 3.11, which stamps its own
    # OS byte), so the same model gives the same bytes on 3.10 and 3.12
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as stream:
        stream.write(bytes(blob))
    packed = buffer.getvalue()
    out = Path(out)
    bin_path, json_path = out.parent / f"{out.name}.bin", out.parent / f"{out.name}.json"     # names may hold dots
    out.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(packed)
    model = {"schema": MODEL_SCHEMA, "title": title or exported.get("title", ""), "units": exported.get("units", "mm"),
             "up": exported.get("up", "z"), "box_mm": [round(float(x), 4) for x in (*lo, *hi)], "quant": QUANT,
             "bin": bin_path.name, "encoding": "gzip", "bytes": len(packed), "raw_bytes": len(blob),
             "sha256": hashlib.sha256(packed).hexdigest(), "triangles": sum(p["triangles"] for p in parts),
             "source": source or {}, **({"view": dict(view)} if view else {}), "parts": parts}
    json_path.write_text(json.dumps(model, indent=1) + "\n")
    return model


def unpack_model(model: Dict[str, Any], packed: bytes) -> List[tuple]:
    """[(vertices (m, 3) float mm, triangles (k, 3) int)] per part from a pack_view model and its binary: the
    reference decoder (kit/model.js does the same in the browser; the tests hold the two to each other)."""
    import gzip
    raw = np.frombuffer(gzip.decompress(packed) if packed[:2] == b"\x1f\x8b" else packed, dtype=np.uint8)
    lo, hi = np.array(model["box_mm"][:3]), np.array(model["box_mm"][3:])
    span = np.where(hi - lo > 0, hi - lo, 1.0)
    result = []
    for part in model["parts"]:
        n, m, at, width = part["vertices"], 3 * part["triangles"], part["offset"], part["index_bits"] // 8
        q = np.empty((n, 3), np.int64)
        for axis in range(3):
            plane = raw[at + 2 * n * axis: at + 2 * n * (axis + 1)].astype(np.int64)
            q[:, axis] = np.cumsum(plane[:n] | plane[n:] << 8) & 0xFFFF
        at += 6 * n
        codes = sum(raw[at + m * b: at + m * (b + 1)].astype(np.int64) << (8 * b) for b in range(width)) if m else np.zeros(0, np.int64)
        corners, fresh = np.empty(m, np.int64), 0
        for i, code in enumerate(codes.tolist()):     # sequential by nature: each corner may introduce the next vertex
            corners[i] = fresh - code
            fresh += corners[i] == fresh
        result.append((lo + q * span / model["quant"], corners.reshape(-1, 3)))
    return result
