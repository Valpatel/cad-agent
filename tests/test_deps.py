"""Missing heavy dependencies raise MissingDependency naming the module — no quiet skip."""

from __future__ import annotations

import sys

import pytest

from cadagent import MissingDependency

def test_geometry_without_cadquery(monkeypatch, tmp_path):
    from cadagent import geometry

    monkeypatch.setitem(sys.modules, "cadquery", None)
    with pytest.raises(MissingDependency, match="cadquery"):
        geometry.export_print_stl(object(), tmp_path / "x.stl")
    with pytest.raises(MissingDependency, match="cadquery"):
        geometry.robust_union(object(), object())
    with pytest.raises(MissingDependency, match="cadquery"):
        geometry.robust_cut(object(), object())

def test_min_gap_without_ocp(monkeypatch):
    from cadagent import geometry

    monkeypatch.setitem(sys.modules, "OCP.BRepExtrema", None)
    with pytest.raises(MissingDependency, match="OCP.BRepExtrema"):
        geometry.min_gap(object(), object())

def test_renderer_without_vtk(monkeypatch, tmp_path):
    from cadagent.publish.render import Renderer

    monkeypatch.setitem(sys.modules, "vtk", None)
    with pytest.raises(MissingDependency, match="vtk"):
        Renderer(tmp_path)

def test_importing_the_package_pulls_in_no_heavy_dependency():
    import subprocess

    code = (
        "import sys, cadagent, cadagent.cli, cadagent.publish.report, cadagent.geometry, "
        "cadagent.publish.render, cadagent.manufacturing.mesh3mf, cadagent.publish.htmlreport, cadagent.package, "
        "cadagent.publish.serve\n"
        "heavy = {'cadquery', 'OCP', 'trimesh', 'vtk', 'matplotlib', 'PIL'} & set(sys.modules)\n"
        "assert not heavy, heavy\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
