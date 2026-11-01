"""Renderer produces a captioned PNG offscreen (needs vtk + PIL)."""

from __future__ import annotations

import pytest

pytest.importorskip("vtk")
Image = pytest.importorskip("PIL.Image")

from cadagent.publish.render import Renderer  # noqa: E402

CUBE_STL = """solid cube
{facets}endsolid cube
"""

def cube_stl(path, s=20.0):
    v = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    facets = "".join(
        "facet normal 0 0 0\nouter loop\n" + "".join("vertex %g %g %g\n" % v[i] for i in f) + "endloop\nendfacet\n"
        for f in faces
    )
    path.write_text(CUBE_STL.format(facets=facets))
    return path

def test_render_writes_a_captioned_png(tmp_path):
    stl = cube_stl(tmp_path / "cube.stl")
    r = Renderer(tmp_path / "out", size=(400, 300), subtitle="REV T | TEST", branding="demo")
    out = r.render("cube.png", meshes=[(stl, (0.2, 0.5, 0.8))], caption="Cube", note="note text",
                   view="iso", clip=((10, 0, 0), (1, 0, 0)))
    assert out == tmp_path / "out" / "cube.png"
    im = Image.open(out).convert("RGB")
    assert im.size == (400, 300)
    assert im.getpixel((5, 5)) == (0x14, 0x2B, 0x38)       # caption bar
    assert im.getpixel((5, 295)) == (255, 255, 255)        # note bar
    centre = im.getpixel((200, 150))
    assert centre != im.getpixel((395, 150)), "model not drawn: centre matches background"

def test_only_filter_skips_other_names(tmp_path, monkeypatch):
    stl = cube_stl(tmp_path / "cube.stl")
    monkeypatch.setenv("CAD_AGENT_RENDER_ONLY", "b.png")
    r = Renderer(tmp_path, size=(200, 150))
    assert r.render("a.png", meshes=[(stl, (1, 0, 0))]) is None
    assert not (tmp_path / "a.png").exists()
    assert r.render("b.png", meshes=[(stl, (1, 0, 0))], view=(1, 1, 1)) is not None
    with pytest.raises(ValueError, match="unknown view"):
        Renderer(tmp_path, only=["c.png"]).render("c.png", meshes=[(stl, (1, 0, 0))], view="diagonal")

def test_only_filter_reads_the_legacy_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("CAD_AGENT_RENDER_ONLY", raising=False)
    monkeypatch.setenv("VPTEST_CAD_RENDER_ONLY", "b.png")
    assert Renderer(tmp_path, size=(200, 150)).only == {"b.png"}
