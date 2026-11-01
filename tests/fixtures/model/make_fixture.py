#!/usr/bin/env python3
"""The packed-model fixture both decoders are held to: two small parts packed by cadagent.view.pack_view.

    python tests/fixtures/model/make_fixture.py      # rewrites two-parts.{json,bin} and two-parts.decoded.json

tests/test_view.py checks that pack_view still writes these exact bytes and that cadagent.view.unpack_model reads
back two-parts.decoded.json; tests/webkit-model.test.mjs checks that kit/model.js's decodeModel reads back the same.
The parts: a tetrahedron (with one triangle whose corners meet, which the packer drops) and a box offset in x,
so the delta coding, the vertex numbering and the assembly-wide quantisation are all exercised."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))

from cadagent.view import _write_stl, pack_view, unpack_model  # noqa: E402

TETRA = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]], [[0, 0, 0], [0, 10, 0], [0, 0, 10]],
                  [[0, 0, 0], [0, 0, 10], [10, 0, 0]], [[10, 0, 0], [0, 0, 10], [0, 10, 0]],
                  [[0, 0, 0], [10, 0, 0], [10, 0, 0]]], dtype=np.float32)         # two corners at one point


def box(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    c = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], np.float32)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return np.array([[c[a], c[b], c[d]] for a, b, _, d in quads] + [[c[b], c[cc], c[d]] for _, b, cc, d in quads], np.float32)


BOX = box((30.0, -7.5, 0.0), (52.25, 7.5, 12.4))
EXPORT = {"title": "Fixture", "units": "mm", "up": "z", "parts": [
    {"name": "tetra", "file": "tetra.stl", "color": "#e8892b", "bounds_mm": [0, 0, 0, 10, 10, 10]},
    {"name": "box.v2", "id": "B-1", "category": "Frame", "file": "box.stl", "color": "#5a5f68", "explode": [1, 0, 0],
     "bounds_mm": [30, -7.5, 0, 52.25, 7.5, 12.4]}]}


def export(folder: Path) -> Path:
    """A `cad-agent view` export of the two parts in ``folder``; returns its view.json."""
    _write_stl(folder / "tetra.stl", TETRA)
    _write_stl(folder / "box.stl", BOX)
    (folder / "view.json").write_text(json.dumps(EXPORT))
    return folder / "view.json"


def pack(out: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        return pack_view(export(Path(tmp)), out, colors={"tetra": "#9cc9e8"}, view={"azimuth": 30, "elevation": 20},
                         source={"fixture": "tests/fixtures/model/make_fixture.py"})


def decoded(model: dict, packed: bytes) -> list:
    return [{"name": p["name"], "vertices": v.round(6).tolist(), "triangles": t.tolist()}
            for p, (v, t) in zip(model["parts"], unpack_model(model, packed))]


if __name__ == "__main__":
    model = pack(HERE / "two-parts")
    (HERE / "two-parts.decoded.json").write_text(json.dumps(decoded(model, (HERE / "two-parts.bin").read_bytes())) + "\n")
    print(f"two-parts: {model['triangles']} triangles, {model['bytes']} bytes")
