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
      groups: [{id: two, title: Two-port, prefix: "2port_"}]   # also write exports/view/two.json with only those parts
                                                       # (the id "view" is reserved; groups are checked before any write)

Colours match a part's name exactly, else its name without a trailing _l/_r/_1/... suffix, else its first word.
A ``category`` (on an ``extra`` entry, or ``parts_category`` for the parts file) heads a section of the viewer's parts
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
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * n:
            rec = np.frombuffer(data, dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
            return rec["v"].copy()
    text = data.decode("ascii", errors="ignore")
    vertices = [line.split()[1:4] for line in text.splitlines() if line.lstrip().startswith("vertex")]
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


def export_view(project, tolerance: float = 0.1, angular: float = 0.2) -> Dict[str, Any]:
    """Write the meshes and the manifest. Parts without a STEP (or STL) are listed as skipped, not errors."""
    cfg = dict(project.view or {})
    colors: Dict[str, str] = cfg.get("colors", {})
    hidden = set(cfg.get("hidden", []))
    explode: Dict[str, List[float]] = cfg.get("explode", {})
    out = project.exports_dir / "view"

    # (name, file, colour, offset, category, hidden)
    sources = ([(name, project.exports_dir / f"{name}.step", None, None, cfg.get("parts_category"), False)
                for name in _parts_from(project)] if cfg.get("parts", True) else [])
    for e in cfg.get("extra", []):
        extra = (e.get("color"), e.get("offset"), e.get("category"), bool(e.get("hidden")))
        if "glob" in e:
            for f in sorted(project.root.glob(e["glob"])):
                sources.append((f.stem[len(e.get("strip", "")):] if f.stem.startswith(e.get("strip", "")) else f.stem, f, *extra))
        else:
            sources.append((e["name"], project.root / e["file"], *extra))
    names = [s[0] for s in sources if s[1].is_file()]
    if len(set(names)) != len(names):
        from cadagent.project import CadConfigError
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
