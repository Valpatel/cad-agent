import json
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.view import _read_stl, _write_stl, export_view


def tetra(path, ascii=False):
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 0], [0, 1, 0], [0, 0, 1]],
                    [[0, 0, 0], [0, 0, 1], [1, 0, 0]], [[1, 0, 0], [0, 0, 1], [0, 1, 0]]], dtype=np.float32) * 10
    if ascii:
        lines = ['solid t'] + [f'facet normal 0 0 0\nouter loop\n' + '\n'.join(f'vertex {x} {y} {z}' for x, y, z in t)
                               + '\nendloop\nendfacet' for t in tri] + ['endsolid t']
        path.write_text('\n'.join(lines))
    else:
        _write_stl(path, tri)
    return tri


def project(tmp_path, view):
    return SimpleNamespace(root=tmp_path, exports_dir=tmp_path / 'exports', title='T', part_ids={}, view=view)


@pytest.mark.parametrize('ascii', [False, True])
def test_stl_round_trip(tmp_path, ascii):
    tri = tetra(tmp_path / 'a.stl', ascii)
    assert np.allclose(_read_stl(tmp_path / 'a.stl'), tri)


def test_stl_extras_offset_category_hidden_and_skipped(tmp_path):
    tetra(tmp_path / 'board.stl')
    tetra(tmp_path / 'fan.stl', ascii=True)
    r = export_view(project(tmp_path, {
        'parts': False,
        'extra': [{'name': 'board', 'file': 'board.stl', 'offset': [15, 15, 20], 'category': 'Carrier', 'hidden': True},
                  {'name': 'fan', 'file': 'fan.stl', 'category': 'Cooler', 'color': '#111111'},
                  {'name': 'vendor', 'file': 'missing.stl', 'category': 'Carrier'}]}))
    assert r['parts'] == 2 and r['skipped'] == ['vendor']
    m = json.loads((tmp_path / 'exports/view/view.json').read_text())
    board, fan = m['parts']
    assert board['bounds_mm'] == [15, 15, 20, 25, 25, 30] and board['visible'] is False and board['category'] == 'Carrier'
    assert fan['visible'] is True and fan['category'] == 'Cooler' and fan['color'] == '#111111'
    assert np.allclose(_read_stl(tmp_path / 'exports/view/board.stl').reshape(-1, 3).min(axis=0), [15, 15, 20])


def test_duplicate_names_rejected_before_writing(tmp_path):
    from cadagent.project import CadConfigError
    tetra(tmp_path / 'a.stl')
    with pytest.raises(CadConfigError):
        export_view(project(tmp_path, {'parts': False, 'extra': [{'name': 'a', 'file': 'a.stl'}, {'glob': '*.stl'}]}))
    assert not (tmp_path / 'exports/view').exists()


def test_categories_by_name(tmp_path):
    from cadagent.project import CadConfigError
    tetra(tmp_path / 'a.stl')
    tetra(tmp_path / 'b.stl')
    view = {'parts': False, 'extra': [{'glob': '*.stl', 'category': 'Parts'}], 'categories': {'Coupons': ['b']}}
    export_view(project(tmp_path, view))
    m = json.loads((tmp_path / 'exports/view/view.json').read_text())
    assert [(p['name'], p['category']) for p in m['parts']] == [('a', 'Parts'), ('b', 'Coupons')]
    with pytest.raises(CadConfigError):
        export_view(project(tmp_path, dict(view, categories={'Coupons': ['typo']})))


def test_binary_stl_with_solid_header_and_trailing_bytes(tmp_path):
    tri = tetra(tmp_path / 'a.stl')
    data = (tmp_path / 'a.stl').read_bytes()
    (tmp_path / 'a.stl').write_bytes(b'solid exported'.ljust(80, b' ') + data[80:] + b'\0\0')
    assert np.allclose(_read_stl(tmp_path / 'a.stl'), tri)


@pytest.mark.parametrize('bad', [{'extra': [{'name': 'a', 'file': 'a.stl'}, {'name': 'b', 'file': 'b.stl', 'offset': [1, 2]}]},
                                 {'extra': [{'name': 'a', 'file': 'a.stl', 'offset': 5}]},
                                 {'extra': [{'glob': '*.stl'}], 'categories': {'Carrier': 'a'}},
                                 {'extra': [{'glob': '*.stl'}], 'categories': {'X': ['a'], 'Y': ['a']}}])
def test_bad_config_rejected_before_writing(tmp_path, bad):
    from cadagent.project import CadConfigError
    tetra(tmp_path / 'a.stl')
    tetra(tmp_path / 'b.stl')
    with pytest.raises(CadConfigError):
        export_view(project(tmp_path, dict(bad, parts=False)))
    assert not (tmp_path / 'exports/view').exists()


# ---- pack_view: the compact model the site's <cad-model> loads (kit/model.js decodes it; #179) ----

import importlib.util
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "model"
REGEN_MODEL = "refresh it with `python tests/fixtures/model/make_fixture.py`"


def _fixture():
    spec = importlib.util.spec_from_file_location("model_fixture", FIXTURE / "make_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pack_view_writes_the_committed_fixture(tmp_path):
    import gzip
    fx = _fixture()
    model = fx.pack(tmp_path / "two-parts")
    packed, committed = (tmp_path / "two-parts.bin").read_bytes(), (FIXTURE / "two-parts.bin").read_bytes()
    # The payload exactly; the gzip stream may differ with the zlib build (zlib-ng compresses differently), so the
    # manifest is compared without the stream's size and checksum
    assert gzip.decompress(packed) == gzip.decompress(committed), REGEN_MODEL
    fresh, kept = json.loads((tmp_path / "two-parts.json").read_text()), json.loads((FIXTURE / "two-parts.json").read_text())
    assert {k: v for k, v in fresh.items() if k not in ("bytes", "sha256")} == {k: v for k, v in kept.items() if k not in ("bytes", "sha256")}, REGEN_MODEL
    # The header is the same on every Python: no timestamp, maximum compression, OS "unknown" (gzip.compress on
    # 3.11+ would write the OS byte of the machine instead)
    assert packed[:10] == bytes.fromhex("1f8b08000000000002ff")
    again = fx.pack(tmp_path / "again")                     # deterministic
    assert (tmp_path / "again.bin").read_bytes() == packed
    assert again["sha256"] == model["sha256"]


def test_pack_view_round_trip_within_one_quantisation_step(tmp_path):
    from cadagent.view import _weld, unpack_model
    fx = _fixture()
    model = fx.pack(tmp_path / "m")
    parts = unpack_model(model, (tmp_path / "m.bin").read_bytes())
    box = np.array(model["box_mm"])
    step = (box[3:] - box[:3]) / model["quant"]
    for (vertices, faces), source in zip(parts, (fx.TETRA, fx.BOX)):
        want_v, want_f = _weld(source)
        assert np.array_equal(faces, want_f)                 # the triangles exactly, in order
        assert np.abs(vertices - want_v).max(axis=0).tolist() <= (step / 2 + 1e-4).tolist()
    assert [p["triangles"] for p in model["parts"]] == [4, 12]       # the tetra's sliver is dropped
    assert model["parts"][1]["name"] == "box.v2" and (tmp_path / "m.bin").exists()   # a dotted name keeps its dot
    assert model["parts"][0]["color"] == "#9cc9e8" and model["parts"][1]["color"] == "#5a5f68"
    assert model["view"] == {"azimuth": 30, "elevation": 20}
    assert {k: model["parts"][1][k] for k in ("id", "category", "explode")} == {"id": "B-1", "category": "Frame", "explode": [1, 0, 0]}


def test_unpack_model_reads_the_decoded_fixture():
    from cadagent.view import unpack_model
    fx = _fixture()
    model = json.loads((FIXTURE / "two-parts.json").read_text())
    assert fx.decoded(model, (FIXTURE / "two-parts.bin").read_bytes()) == json.loads((FIXTURE / "two-parts.decoded.json").read_text()), REGEN_MODEL


@pytest.mark.parametrize("n, bits", [(65533, 16), (65534, 32), (65535, 32)])
def test_pack_view_index_width_at_the_16_bit_edge(tmp_path, n, bits):
    """A strip of n triangles has n + 2 vertices; one more triangle goes back to vertex 0, whose code is the vertex
    count: 16 bits hold it up to 65,535 vertices (#182 review: 65,536 wrapped to 0, read as a new vertex)."""
    from cadagent.view import pack_view, unpack_model
    xs = np.arange(n + 2, dtype=np.float32)
    pts = np.stack([xs, (np.arange(n + 2) % 2).astype(np.float32), np.zeros(n + 2, np.float32)], axis=1)
    tri = np.concatenate([np.stack([pts[:-2], pts[1:-1], pts[2:]], axis=1), [[pts[0], pts[1], pts[-1] + [0, 0, 1]]]])
    tri[-1, 2] = pts[-1]                                     # back to vertices 0 and 1 and the last one
    _write_stl(tmp_path / "strip.stl", tri)
    (tmp_path / "view.json").write_text(json.dumps({"parts": [{"name": "strip", "file": "strip.stl", "color": "#888888"}]}))
    model = pack_view(tmp_path / "view.json", tmp_path / "strip")
    assert model["parts"][0]["vertices"] == n + 2 and model["parts"][0]["index_bits"] == bits
    (vertices, faces), = unpack_model(model, (tmp_path / "strip.bin").read_bytes())
    assert faces.max() == n + 1 and faces[-1].tolist() == [0, 1, n + 1]


def test_pack_view_uses_32_bit_indices_past_65536_vertices(tmp_path):
    from cadagent.view import pack_view, unpack_model
    n = 70000                                                # a strip of triangles: n + 2 distinct vertices
    xs = np.arange(n + 2, dtype=np.float32)
    pts = np.stack([xs, (np.arange(n + 2) % 2).astype(np.float32), np.zeros(n + 2, np.float32)], axis=1)
    tri = np.stack([pts[:-2], pts[1:-1], pts[2:]], axis=1)
    _write_stl(tmp_path / "strip.stl", tri)
    (tmp_path / "view.json").write_text(json.dumps({"parts": [{"name": "strip", "file": "strip.stl", "color": "#888888"}]}))
    model = pack_view(tmp_path / "view.json", tmp_path / "strip")
    assert model["parts"][0]["index_bits"] == 32 and model["parts"][0]["vertices"] == n + 2
    (vertices, faces), = unpack_model(model, (tmp_path / "strip.bin").read_bytes())
    step = (n + 1) / model["quant"]                         # 70 m of strip in 16 bits: about 1.07 mm a step
    assert faces.shape == (n, 3) and faces.max() == n + 1 and np.abs(vertices[:, 0] - xs).max() <= step / 2 + 1e-3
