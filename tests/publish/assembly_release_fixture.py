"""Build and extract a real guide release for the persistent browser test.

Synthetic geometry and named fixture releases are deliberately distinct. This
does not depend on another checkout, CAD extras, a network fetch or pytest.
"""
import argparse
import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

from cadagent.project import from_dict
from cadagent.publish.release import build_release


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cube(origin, size):
    vertices = [[origin[j] + (size[j] if i & (1 << j) else 0) for j in range(3)] for i in range(8)]
    faces = [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4],
             [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]]
    return (b"guide fixture".ljust(80, b" ") + struct.pack("<I", len(faces))
            + b"".join(struct.pack("<12fH", 0, 0, 0, *(n for i in face for n in vertices[i]), 0) for face in faces))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    out = parser.parse_args().out.resolve()
    source = out / "source"
    source.mkdir(parents=True)  # refuse an existing fixture instead of deleting it
    (source / "exports").mkdir()
    (source / "exports/geometry-checks.json").write_text('{"base":{}}')
    (source / "exports/base.stl").write_bytes(cube([0, 0, 0], [40, 30, 8]))
    paths = []
    for index, identifier in enumerate(("v1", "v2", "wip")):
        folder = source / "instructions" / identifier
        folder.mkdir(parents=True)
        origins = [[0, 0, 0], [8, 8, 8], [28, 8, 8]]
        sizes = [[40 + index * 10, 30, 8], [5, 5, 20], [5, 5, 20]]
        names = ["base", "screw#1", "screw#2"]
        parts = []
        for number, (name, origin, size) in enumerate(zip(names, origins, sizes)):
            data = cube(origin, size)
            file = f"mesh-{number}.stl"
            (folder / file).write_bytes(data)
            parts.append({"name": name, "file": file, "sha256": sha(data), "color": "#dca44e" if number else "#477a97",
                          "bounds_mm": origin + [n + s for n, s in zip(origin, size)]})
        raw = json.dumps({"units": "mm", "up": "z", "parts": parts}).encode()
        (folder / "view.json").write_bytes(raw)
        steps = []
        for i in range(2):
            # A labelled plan-view fixture diagram: stage 1 base, stage 2 base
            # plus both screws. Product posters have their own render contract.
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" viewBox="0 0 240 180">'
                   '<rect width="240" height="180" fill="#faf9f5"/><rect x="30" y="50" width="180" height="100" rx="8" fill="#477a97"/>'
                   + ('<circle cx="75" cy="90" r="12" fill="#dca44e"/><circle cx="165" cy="90" r="12" fill="#dca44e"/>' if i else '')
                   + f'<text x="20" y="28" font-size="16">Fixture {identifier}: step {i + 1}</text></svg>').encode()
            poster = f"step-{i + 1}.svg"
            (folder / poster).write_bytes(svg)
            steps.append({"id": "base" if i == 0 else "screws", "title": "Seat base" if i == 0 else "Fit both screws",
                          "text": f"Fixture {identifier}: " + ("seat the base." if i == 0 else "fit both screws."),
                          "subassembly": "base" if i == 0 else "fasteners", "parts": names[:1] if i == 0 else names,
                          "highlight": names[:1] if i == 0 else names[1:],
                          "offsets_mm": {} if i == 0 else {n: [0, 0, 25 + index * 5] for n in names[1:]},
                          "poster": {"file": poster, "sha256": sha(svg)}, "camera": {"direction": [0.6, -1, 0.7]}})
        guide = {"schema": "cad-agent.assembly-guide/1",
                 "snapshot": {"id": identifier, "revision": "Fixture " + identifier,
                              "status": "wip" if identifier == "wip" else "released", "source_commit": str(index + 1) * 40},
                 "model": {"file": "view.json", "sha256": sha(raw)},
                 "subassemblies": [{"id": "base", "title": "Base", "parts": names[:1]},
                                   {"id": "fasteners", "title": "Fasteners", "parts": names[1:]}], "steps": steps}
        (folder / "guide.json").write_text(json.dumps(guide))
        paths.append((folder / "guide.json").relative_to(source).as_posix())
    p = from_dict(source, {"name": "assembly-fixture", "release": {"include": [], "assembly_guides": paths}})
    result = build_release(p, out=out / "bundle", date="2026-11-09", revision="fixture")
    extracted = out / "extracted"
    with zipfile.ZipFile(result.zip_path) as archive:
        archive.extractall(extracted)
    # A live source-tree fallback cannot make the browser test pass.
    shutil.rmtree(source)
    shutil.rmtree(result.folder)
    print(json.dumps({"root": str(extracted / "bundle"), "zip": str(result.zip_path)}))


if __name__ == "__main__":
    main()
