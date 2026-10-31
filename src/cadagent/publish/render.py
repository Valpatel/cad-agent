"""Offscreen VTK renders of cadquery shapes and STL meshes, captioned with PIL.

Usage::

    from cadagent.publish.render import Renderer

    r = Renderer("preview", subtitle="REV 3 | FIT-CHECK PROTOTYPE")
    r.render("assembled.png", shapes=[(base, (.2, .2, .25)), (lid, (.25, .27, .3, .6))],
             caption="Assembled", note="Screws shown are illustrative.")
    r.render("section.png", shapes=[(base, (.2, .2, .25))], view="section",
             clip=((0, 60, 0), (0, 1, 0)))

``review_packet(section, root=...)`` renders a dossier section's review packet (``cadagent.publish.packet``,
``docs/review-packet.md``).

Colors are ``(r, g, b)`` or ``(r, g, b, opacity)`` floats in 0..1. Views are
directions from the scene centre; the camera is parallel-projection and fitted
to the scene, so only the direction matters. ``only`` (or the environment
variable named by ``only_env``, comma-separated) restricts which file names are
rendered, for iterating on one picture without re-rendering the gallery.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from cadagent._deps import require

Color = Sequence[float]
View = Union[str, Tuple[float, float, float]]
Plane = Tuple[Sequence[float], Sequence[float]]

# direction from the focal point to the camera, and the camera's up vector
VIEWS: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = {
    "iso": ((1.0, -1.05, 0.85), (0, 0, 1)),
    "front": ((0.0, -1.0, 0.25), (0, 0, 1)),
    "rear": ((-0.6, 1.0, 0.7), (0, 0, 1)),
    "side": ((1.0, -0.12, 0.3), (0, 0, 1)),
    "top": ((0.0, 0.0, 1.0), (0, 1, 0)),
    "bottom": ((0.75, -0.85, -0.8), (0, 0, 1)),
    "section": ((0.0, -1.0, 0.0), (0, 0, 1)),
}

# read when ``only_env`` is unset, so vptest-era scripts keep working
LEGACY_ONLY_ENV = "VPTEST_CAD_RENDER_ONLY"

CAPTION_BAR_PX = 94
NOTE_BAR_PX = 54

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

class Renderer:
    def __init__(
        self,
        out_dir: Union[str, Path],
        *,
        size: Tuple[int, int] = (1600, 1100),
        background: Color = (0.93, 0.95, 0.97),
        subtitle: str = "",
        branding: str = "",
        font: Optional[str] = None,
        tessellation: Tuple[float, float] = (0.18, 0.3),
        only: Optional[Iterable[str]] = None,
        only_env: str = "CAD_AGENT_RENDER_ONLY",
        bar_color: str = "#142b38",
        accent: str = "#b75a18",
    ) -> None:
        self.vtk = require("vtk", "CAD rendering")
        self.pil = require("PIL.Image", "render captions")
        self.draw_mod = require("PIL.ImageDraw", "render captions")
        self.font_mod = require("PIL.ImageFont", "render captions")
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.background = background
        self.subtitle = subtitle
        self.branding = branding
        self.font_path = font or next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
        self.tessellation = tessellation
        if only is None:
            env = os.environ.get(only_env, "") or os.environ.get(LEGACY_ONLY_ENV, "")
            only = [n for n in env.split(",") if n.strip()] or None
        self.only = {n.strip() for n in only} if only is not None else None
        self.bar_color = bar_color
        self.accent = accent
        self._stl_cache: Dict[str, Any] = {}
        self._shape_cache: Dict[int, Tuple[Any, Any]] = {}     # id(shape) -> (shape, polydata): tessellate once

    def font(self, px: int) -> Any:
        if self.font_path:
            return self.font_mod.truetype(self.font_path, px)
        return self.font_mod.load_default()

    def wanted(self, name: str) -> bool:
        return self.only is None or name in self.only

    def shape_actor(self, shape: Any, color: Color, offset: Sequence[float] = (0, 0, 0)) -> Any:
        cached = self._shape_cache.get(id(shape))
        if cached is not None and cached[0] is shape:
            actor = self._poly_actor(cached[1], color)
            actor.SetPosition(*offset)
            return actor
        vtk = self.vtk
        verts, tris = shape.tessellate(*self.tessellation)
        pts = vtk.vtkPoints()
        pts.SetDataTypeToDouble()
        for v in verts:
            pts.InsertNextPoint(v.x, v.y, v.z)
        cells = vtk.vtkCellArray()
        for t in tris:
            cells.InsertNextCell(3)
            for i in t:
                cells.InsertCellPoint(i)
        poly = vtk.vtkPolyData()
        poly.SetPoints(pts)
        poly.SetPolys(cells)
        self._shape_cache[id(shape)] = (shape, poly)     # the shape is kept, so its id cannot be reused
        actor = self._poly_actor(poly, color)
        actor.SetPosition(*offset)
        return actor

    def stl_actor(self, path: Union[str, Path], color: Color, offset: Sequence[float] = (0, 0, 0)) -> Any:
        key = str(path)
        if key not in self._stl_cache:
            if not Path(key).is_file():
                raise FileNotFoundError(key)
            reader = self.vtk.vtkSTLReader()
            reader.SetFileName(key)
            reader.Update()
            self._stl_cache[key] = reader.GetOutput()
        actor = self._poly_actor(self._stl_cache[key], color)
        actor.SetPosition(*offset)
        return actor

    def _poly_actor(self, poly: Any, color: Color) -> Any:
        vtk = self.vtk
        clean = vtk.vtkCleanPolyData()
        clean.SetInputData(poly)
        clean.ToleranceIsAbsoluteOn()
        clean.SetAbsoluteTolerance(1e-6)
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(clean.GetOutputPort())
        normals.SetFeatureAngle(35)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*color[:3])
        prop.SetOpacity(color[3] if len(color) > 3 else 1.0)
        prop.SetSpecular(0.25)
        prop.SetSpecularPower(30)
        prop.SetDiffuse(0.85)
        prop.SetAmbient(0.12)
        return actor

    def render(
        self,
        name: str,
        shapes: Iterable[Tuple[Any, ...]] = (),
        meshes: Iterable[Tuple[Any, ...]] = (),
        caption: str = "",
        *,
        view: View = "iso",
        note: str = "",
        subtitle: Optional[str] = None,
        labels: Iterable[Tuple[str, str, Sequence[float], Tuple[int, int]]] = (),
        size: Optional[Tuple[int, int]] = None,
        clip: Union[Plane, List[Plane], None] = None,
        zoom: Optional[float] = None,
        fit: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
    ) -> Optional[Path]:
        """Render one PNG into ``out_dir``; returns its path, or None when filtered out.

        ``shapes``: ``(shape, color[, offset])``; ``meshes``: ``(stl_path, color[, offset])``.
        ``labels``: ``(code, text, world_point, (text_x, text_y))`` leader callouts.
        ``clip``: one ``(origin, normal)`` plane or a list of them; geometry on the
        side the normal points away from is cut.
        ``fit``: a ``(min, max)`` box to frame instead of everything drawn (parts outside it are cropped).
        """
        if not self.wanted(name):
            return None
        vtk = self.vtk
        labels = list(labels)
        size = size or self.size
        actors = [self.shape_actor(*item) for item in shapes]
        actors += [self.stl_actor(*item) for item in meshes]
        if not actors:
            raise ValueError(f"{name}: nothing to render")
        planes = [] if clip is None else ([clip] if _is_plane(clip) else list(clip))
        subtitle = self.subtitle if subtitle is None else subtitle
        top_bar = CAPTION_BAR_PX if (caption or subtitle or self.branding) else 0
        bottom_bar = NOTE_BAR_PX if note else 0
        ren = vtk.vtkRenderer()
        ren.SetBackground(*self.background[:3])
        # fit the model into the band the caption/note bars leave uncovered
        ren.SetViewport(0, bottom_bar / size[1], 1, 1 - top_bar / size[1])
        for actor in actors:
            for origin, normal in planes:
                plane = vtk.vtkPlane()
                plane.SetOrigin(*origin)
                plane.SetNormal(*normal)
                actor.GetMapper().AddClippingPlane(plane)
            ren.AddActor(actor)
        ren.SetTwoSidedLighting(True)
        bounds = ren.ComputeVisiblePropBounds() if fit is None else \
            [float(fit[i % 2][i // 2]) for i in range(6)]
        center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
        diag = max(1.0, ((bounds[1] - bounds[0]) ** 2 + (bounds[3] - bounds[2]) ** 2 + (bounds[5] - bounds[4]) ** 2) ** 0.5)
        key = vtk.vtkLight()
        key.SetLightTypeToSceneLight()
        key.SetPosition(center[0] + 2.5 * diag, center[1] - 3.5 * diag, center[2] + 4.5 * diag)
        key.SetFocalPoint(*center)
        key.SetIntensity(0.55)
        ren.AddLight(key)
        fill = vtk.vtkLight()
        fill.SetLightTypeToHeadlight()
        fill.SetIntensity(0.6)
        ren.AddLight(fill)
        win = vtk.vtkRenderWindow()
        win.SetOffScreenRendering(1)
        win.SetSize(*size)
        backdrop = vtk.vtkRenderer()
        backdrop.SetBackground(*self.background[:3])
        backdrop.SetLayer(0)
        backdrop.InteractiveOff()
        ren.SetLayer(1)
        win.SetNumberOfLayers(2)
        win.AddRenderer(backdrop)
        win.AddRenderer(ren)
        win.SetMultiSamples(4)
        direction, up = _view(view)
        cam = ren.GetActiveCamera()
        cam.SetFocalPoint(*center)
        cam.SetPosition(*(c + 3 * diag * d for c, d in zip(center, _unit(direction))))
        cam.SetViewUp(*up)
        cam.ParallelProjectionOn()
        if fit is None:
            ren.ResetCamera()
        else:
            ren.ResetCamera(bounds)
        cam.Zoom(zoom if zoom is not None else (0.93 if labels else 1.04))
        win.Render()
        grab = vtk.vtkWindowToImageFilter()
        grab.SetInput(win)
        grab.Update()
        out = self.out_dir / name
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(out))
        writer.SetInputConnection(grab.GetOutputPort())
        writer.Write()
        projected = []
        for code, text, point, xy in labels:
            ren.SetWorldPoint(*point, 1)
            ren.WorldToDisplay()
            q = ren.GetDisplayPoint()
            projected.append((code, text, (q[0], size[1] - q[1]), xy))
        win.Finalize()
        self._annotate(out, size, caption, subtitle, note, projected)
        print(name, flush=True)
        return out

    def _annotate(self, out: Path, size, caption, subtitle, note, labels) -> None:
        im = self.pil.open(out).convert("RGB")
        d = self.draw_mod.Draw(im)
        if caption or subtitle or self.branding:
            d.rectangle((0, 0, size[0], CAPTION_BAR_PX), fill=self.bar_color)
            d.text((30, 16), caption, font=self.font(26), fill="white")
            if subtitle:
                d.text((30, 56), subtitle, font=self.font(16), fill="#b8d1dc")
            if self.branding:
                f = self.font(16)
                w = d.textbbox((0, 0), self.branding, font=f)[2]
                d.text((size[0] - w - 30, 20), self.branding, font=f, fill="#b8d1dc")
        f = self.font(20)
        for code, text, (qx, qy), (tx, ty) in labels:
            label = f"{code}  {text}"
            bb = d.textbbox((tx, ty), label, font=f)
            d.line((qx, qy, tx, ty + 12), fill=self.accent, width=3)
            d.ellipse((qx - 6, qy - 6, qx + 6, qy + 6), fill=self.accent)
            d.rounded_rectangle((bb[0] - 9, bb[1] - 7, bb[2] + 9, bb[3] + 7), 6,
                                fill="#ffffff", outline=self.accent, width=2)
            d.text((tx, ty), label, font=f, fill="#16303f")
        if note:
            d.rectangle((0, size[1] - NOTE_BAR_PX, size[0], size[1]), fill="white")
            d.text((30, size[1] - 40), note, font=self.font(17), fill="#516571")
        im.save(out)

def review_packet(section: str, **kwargs: Any) -> Dict[str, Any]:
    """The review packet of one dossier section: solid, opposite iso, x-ray, cuts through its cavities, joint axes
    and fastener axes, exploded along its assembly steps, access along its screws, its joints' range ends and its
    gate findings at their witness points, captioned with the section and content hashes, with
    ``exports/review/<section>/manifest.json`` (``cad-agent.review-packet/1``). Keyword arguments and the manifest
    schema: ``cadagent.publish.packet.review_packet`` and ``docs/review-packet.md``."""
    from cadagent.publish.packet import review_packet as _review_packet
    return _review_packet(section, **kwargs)


def _is_plane(clip: Any) -> bool:
    return len(clip) == 2 and all(isinstance(v, (int, float)) for v in clip[0])

def _view(view: View):
    if isinstance(view, str):
        if view not in VIEWS:
            raise ValueError(f"unknown view {view!r}; use one of {sorted(VIEWS)} or an (x, y, z) offset")
        return VIEWS[view]
    direction = tuple(float(v) for v in view)
    up = (0, 1, 0) if abs(direction[0]) < 1e-9 and abs(direction[1]) < 1e-9 else (0, 0, 1)
    return direction, up

def _unit(v: Sequence[float]) -> Tuple[float, ...]:
    n = sum(c * c for c in v) ** 0.5
    if n == 0:
        raise ValueError("view direction must be non-zero")
    return tuple(c / n for c in v)
