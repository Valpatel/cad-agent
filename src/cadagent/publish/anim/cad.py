"""Real CAD to 2D: solids read from STEP, their visible edges by OpenCASCADE's exact hidden-line removal (HLR), and
their triangles for silhouettes and depth. Needs CadQuery (``pip install cad-agent[cad]``).

Each solid gets its own HLR, so its edges hide only behind itself. Hiding between parts is left to the drawing,
which stacks filled silhouettes in depth order (``cadagent.publish.anim.hero``). That stays right while the parts
move, which one HLR of the whole assembly would not.

Projection is orthographic. ``View.direction`` points from the scene towards the viewer, and ``View.up`` is the
world direction that appears up. Drawing coordinates are millimetres with x right and y down, as in SVG, and depth
grows towards the viewer. HLR's edges come back as lines and ellipse arcs, and are kept as ``L`` and ``A``
segments rather than sampled.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np

from cadagent._deps import require


@dataclass(frozen=True)
class View:
    direction: Tuple[float, float, float]
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)

    def basis(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(d, right, up): unit vectors, d towards the viewer."""
        d = np.asarray(self.direction, float)
        d = d / np.linalg.norm(d)
        r = np.cross(self.up, d)
        if np.linalg.norm(r) < 1e-9:
            raise ValueError("the view direction is parallel to up")
        r /= np.linalg.norm(r)
        return d, r, np.cross(d, r)

    def project(self, pts) -> Tuple[np.ndarray, np.ndarray]:
        """(N, 3) world points to (N, 2) drawing points (x right, y down) and (N,) depth (towards the viewer)."""
        d, r, u = self.basis()
        p = np.asarray(pts, float).reshape(-1, 3)
        return np.stack([p @ r, -(p @ u)], axis=1), p @ d

    def vector(self, v) -> np.ndarray:
        """A world displacement as a drawing displacement."""
        return self.project([v])[0][0]


def read_solids(path: Path) -> List[object]:
    """The solids of a STEP file, in the file's order, as ``cadquery.Solid``."""
    cq = require("cadquery", "cad")
    return list(cq.importers.importStep(str(path)).solids().vals())


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def moved(solid, matrix: Sequence[float]):
    """``solid`` moved by a 3x4 row-major matrix (rotation | translation)."""
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    cq = require("cadquery", "cad")
    t = gp_Trsf()
    m = list(matrix)
    t.SetValues(*m)
    return cq.Shape.cast(BRepBuilderAPI_Transform(solid.wrapped, t, True).Shape())


def hlr_segments(solid, view: View, deflection: float = 0.02) -> List[list]:
    """The visible edges of ``solid`` alone, seen along ``view``: sharp edges, smooth-surface outlines and smooth
    seams, as drawing segments in mm. ``["L", x0, y0, x1, y1]`` for lines, ``["A", x0, y0, x1, y1, rx, ry, rot,
    large, sweep]`` for ellipse arcs, ``["P", x0, y0, ...]`` for anything else (sampled within ``deflection``)."""
    require("cadquery", "cad")
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Ellipse, GeomAbs_Line, GeomAbs_Circle
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    d, r, _ = view.basis()
    algo = HLRBRep_Algo()
    algo.Add(solid.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d), gp_Dir(*r))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    out: List[list] = []
    for comp in (h.VCompound(), h.OutLineVCompound(), h.Rg1LineVCompound()):
        if comp is None or comp.IsNull():
            continue
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            edge = TopoDS.Edge_s(ex.Current())
            c = BRepAdaptor_Curve(edge)
            u0, u1 = c.FirstParameter(), c.LastParameter()
            if edge.Orientation() == TopAbs_REVERSED:
                u0, u1 = u1, u0
            p0, p1 = c.Value(u0), c.Value(u1)
            a, b = (p0.X(), -p0.Y()), (p1.X(), -p1.Y())          # projector (x, y up) to drawing (x, y down)
            kind = c.GetType()
            if kind == GeomAbs_Line:
                out.append(["L", *a, *b])
            elif kind in (GeomAbs_Ellipse, GeomAbs_Circle) and abs(u1 - u0) > 1e-9:
                if kind == GeomAbs_Ellipse:
                    e = c.Ellipse()
                    rx, ry = e.MajorRadius(), e.MinorRadius()
                else:
                    e = c.Circle()
                    rx = ry = e.Radius()
                ax = e.Position()
                xd, zd = ax.XDirection(), ax.Direction()
                rot = math.degrees(math.atan2(-xd.Y(), xd.X()))
                ccw = (zd.Z() > 0) == (u1 > u0)          # counter-clockwise in projector (y up) coordinates
                span = abs(u1 - u0)
                pieces = 2 if span > math.pi * 1.999 else 1      # a full ellipse is two arcs
                for k in range(pieces):
                    ua = u0 + (u1 - u0) * k / pieces
                    ub = u0 + (u1 - u0) * (k + 1) / pieces
                    qa, qb = c.Value(ua), c.Value(ub)
                    out.append(["A", qa.X(), -qa.Y(), qb.X(), -qb.Y(), rx, ry, rot,
                                int(span / pieces > math.pi), int(ccw)])   # ccw with y up is clockwise in SVG: sweep 1
            else:
                s = GCPnts_QuasiUniformDeflection(c, deflection, u0, u1) if u0 < u1 else \
                    GCPnts_QuasiUniformDeflection(c, deflection, u1, u0)
                pts = [(s.Value(i).X(), -s.Value(i).Y()) for i in range(1, s.NbPoints() + 1)]
                if u0 > u1:
                    pts.reverse()
                out.append(["P", *[v for p in pts for v in p]])
            ex.Next()
    return out


def triangles(solid, tolerance: float = 0.2, angular: float = 0.3) -> Tuple[np.ndarray, np.ndarray]:
    """The solid's surface as (vertices (N, 3), triangles (M, 3)), tessellated within ``tolerance`` mm."""
    v, t = solid.tessellate(tolerance, angular)
    return np.array([(p.x, p.y, p.z) for p in v], float), np.array(t, int).reshape(-1, 3)


def transform_segments(segments: Iterable[list], scale: float, offset: Tuple[float, float]) -> List[list]:
    """Segments scaled about the origin and moved (mm to drawing units)."""
    ox, oy = offset
    out = []
    for s in segments:
        k = s[0]
        if k == "A":
            out.append(["A", s[1] * scale + ox, s[2] * scale + oy, s[3] * scale + ox, s[4] * scale + oy,
                        s[5] * scale, s[6] * scale, s[7], s[8], s[9]])
        else:
            vals = s[1:]
            out.append([k] + [v * scale + (ox if i % 2 == 0 else oy) for i, v in enumerate(vals)])
    return out
