"""Pictures and animations of simulation results (PyVista / VTK, rendered off screen).

    from cadagent.simviz import CFDResult, section, flow, walls, animate_flow, animate_sweep
    r = CFDResult('sim/cooled')                       # an OpenFOAM case written by cadagent.cfd, after foamToVTK
    section(r, 'preview/thermal-section.png', normal='y', title='Cooled, 40 W')
    flow(r, 'preview/thermal-flow.png')
    walls(r, 'preview/thermal-walls.png', limit_c=57, limit_label='PLA heat deflection')
    animate_flow(r, 'preview/thermal-flow.mp4')

Every picture is in millimetres and degrees Celsius, framed with a title, a subtitle and a note in the house style
(dark header band, light stage). Colour is by job: temperature on a single-hue orange ramp, speed on a single-hue
blue ramp (light = low, dark = high, never a rainbow); anything past a stated limit is drawn in the critical status
colour and named in the legend, never by colour alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np

from cadagent._deps import require

_WHY = 'simulation pictures'
T0 = 273.15

# single-hue ramps (light -> dark) and the critical status colour
TEMP_RAMP = ['#fff5eb', '#fee6ce', '#fdd0a2', '#fdae6b', '#fd8d3c', '#f16913', '#d94801', '#a63603', '#7f2704']
SPEED_RAMP = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab',
              '#184f95', '#104281', '#0d366b']
CRITICAL = '#d03b3b'
STAGE = '#eef2f5'
HEADER = '#15303b'
PLASTIC = '#9aa3ab'
METAL = '#5b636b'


def _pv():
    pv = require('pyvista', _WHY)
    pv.OFF_SCREEN = True
    return pv


def cmap(ramp):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list('ramp', ramp)


class CFDResult:
    """The latest written time of a cadagent.cfd case, in mm and °C."""

    def __init__(self, case_dir, time: Optional[str] = None):
        pv = _pv()
        self.dir = Path(case_dir)
        self.meta = json.loads((self.dir / 'cadagent-case.json').read_text())
        vtk = self.dir / 'VTK'
        regions = sorted(p.name for p in vtk.iterdir() if p.is_dir())
        self.fluid = 'domain0' if 'domain0' in regions else regions[0]
        self.regions: Dict[str, object] = {}
        self.patches: Dict[str, Dict[str, object]] = {}
        for r in regions:
            steps = sorted((p for p in (vtk / r).iterdir() if p.is_dir() and p.name.startswith('case_')),
                           key=lambda p: float(p.name.split('_')[1]))
            step = next((s for s in steps if s.name == f'case_{time}'), steps[-1]) if time else steps[-1]
            self.time = step.name.split('_')[1]
            g = pv.read(step / 'internal.vtu')
            self.regions[r] = self._prep(g)
            self.patches[r] = {p.stem: self._prep(pv.read(p)) for p in sorted((step / 'boundary').glob('*.vtp'))}
        self.air = self.regions[self.fluid]
        self.solids = {k: v for k, v in self.regions.items() if k != self.fluid}
        self.surfaces = {}
        for s in (self.dir / 'constant' / 'triSurface').glob('*.stl'):
            m = pv.read(s)
            m.points *= 1000.0
            self.surfaces[s.stem] = m

    @staticmethod
    def _prep(g):
        g.points *= 1000.0
        for data in (g.point_data, g.cell_data):
            if 'T' in data:
                data['T_c'] = np.asarray(data['T']) - T0
            if 'U' in data:
                data['speed'] = np.linalg.norm(np.asarray(data['U']), axis=1)
        return g

    def bounds_of(self, name):
        return np.array(self.surfaces[name].bounds).reshape(3, 2).T

    def t_range(self, include_air=True):
        vals = [np.asarray(g.point_data['T_c']) for g in self.solids.values()]
        if include_air:
            vals.append(np.asarray(self.air.point_data['T_c']))
        v = np.concatenate(vals)
        return float(np.percentile(v, 0.5)), float(v.max())


# --- framing ---------------------------------------------------------------------------------------------------
def frame(img_path, title: str, subtitle: str = '', note: str = '', legend: Sequence = ()):
    """Add the house header band (title, subtitle) and a footer note to a rendered image, in place."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(img_path).convert('RGB')
    w, h = im.size
    head, foot = 96, (54 if note else 0)
    out = Image.new('RGB', (w, h + head + foot), STAGE)
    out.paste(im, (0, head))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, w, head], fill=HEADER)

    def font(size, bold=False):
        for name in (('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default()
    d.text((30, 18), title, fill='white', font=font(28))
    if subtitle:
        d.text((30, 60), subtitle, fill='#b8c7cf', font=font(16))
    x = w - 30
    for label, colour in reversed(list(legend)):     # legend swatches, right-aligned in the header
        tw = d.textlength(label, font=font(16))
        x -= tw
        d.text((x, 60), label, fill='#e6edf1', font=font(16))
        x -= 24
        d.rounded_rectangle([x, 61, x + 16, 77], radius=3, fill=colour)
        x -= 22
    if note:
        d.rectangle([0, h + head, w, h + head + foot], fill='white')
        d.text((30, h + head + 17), note, fill='#55636d', font=font(15))
    out.save(img_path)
    return img_path


def _plotter(size=(1600, 1000)):
    pv = _pv()
    p = pv.Plotter(off_screen=True, window_size=size, lighting='three lights')
    p.set_background(STAGE)
    p.enable_anti_aliasing('ssaa')
    return p


def _camera(p, centre, dist, azimuth=-35, elevation=28):
    a, e = np.radians(azimuth), np.radians(elevation)
    eye = np.asarray(centre) + dist * np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
    p.camera_position = [tuple(eye), tuple(centre), (0, 0, 1)]
    p.camera.view_angle = 26


def _bar(p, title, ramp, clim, n_labels=5):
    p.add_scalar_bar(title=title, n_labels=n_labels, fmt='%.0f', color='#26323a', vertical=True,
                     position_x=0.9, position_y=0.18, width=0.035, height=0.62, title_font_size=18, label_font_size=15)


def _context(p, r: CFDResult, clip=None, plastic_opacity=1.0, skip=()):
    """Obstacles: enclosure and boards in plastic grey, everything else in metal grey; clipped to show the inside."""
    for name, m in r.surfaces.items():
        if name in skip or name in r.solids:
            continue
        mm = m.clip(normal=clip[0], origin=clip[1], invert=False) if clip else m
        if mm.n_points == 0:
            continue
        colour = PLASTIC if name in ('enclosure',) else '#2f6b4f' if name == 'pcb' else METAL
        p.add_mesh(mm, color=colour, opacity=plastic_opacity if name == 'enclosure' else 1.0, smooth_shading=False,
                   specular=0.15)


def _solids(p, r: CFDResult, clim, clip=None):
    for name, g in r.solids.items():
        s = g.extract_surface(algorithm='dataset_surface')
        if clip:
            s = s.clip(normal=clip[0], origin=clip[1], invert=False)
        if s.n_points:
            p.add_mesh(s, scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, show_scalar_bar=False)


def _enclosure_box(r):
    if 'enclosure' in r.surfaces:
        return r.bounds_of('enclosure')
    b = np.array(r.air.bounds).reshape(3, 2).T
    return b


# --- still pictures ----------------------------------------------------------------------------------------------
def section(r: CFDResult, path, normal='y', at: Optional[float] = None, title='', subtitle='', note='',
            clim=None, size=(1600, 1000)):
    """Temperature on a plane through the enclosure, with the solids and the obstacles behind it."""
    lo, hi = _enclosure_box(r)
    c = (lo + hi) / 2
    n = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[normal]
    origin = c.copy()
    if at is not None:
        origin['xyz'.index(normal)] = at
    clim = clim or r.t_range()
    p = _plotter(size)
    sl = r.air.slice(normal=n, origin=origin)
    box = sl.clip_box(list(np.ravel(np.stack([lo - 2, hi + 2], 1))), invert=False)
    p.add_mesh(box, scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, show_scalar_bar=False)
    p.add_mesh(box.glyph(orient='U', scale=False, factor=4.0, tolerance=0.025, geom=_pv().Arrow(tip_length=0.35, shaft_radius=0.04)),
               color='#26323a', opacity=0.55)
    clip = (tuple(np.array(n, float)), tuple(origin))      # keep the far side of the plane
    _context(p, r, clip=clip)
    _solids(p, r, clim, clip=clip)
    p.add_mesh(box.copy(), scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, show_scalar_bar=True, opacity=0.0,
               scalar_bar_args=dict(title='Temperature (°C)', vertical=True, position_x=0.9, position_y=0.18, width=0.035, height=0.62,
                                    color='#26323a', fmt='%.0f', title_font_size=18, label_font_size=15))
    span = float(np.max(hi - lo))
    az = {'y': -2, 'x': -88, 'z': -2}[normal]
    el = {'y': 12, 'x': 12, 'z': 70}[normal]
    _camera(p, c, 2.1 * span, az, el)
    p.screenshot(str(path))
    p.close()
    return frame(path, title or f'Temperature section ({normal} = {origin["xyz".index(normal)]:.0f} mm)', subtitle,
                 note or 'Arrows: air direction. Orange ramp: light = cool, dark = hot.')


def _seeds(r: CFDResult, n=900, seed=1):
    pv = _pv()
    lo, hi = _enclosure_box(r)
    rng = np.random.default_rng(seed)
    pts = lo + 4 + rng.random((n * 3, 3)) * (hi - lo - 8)
    inside = r.air.find_containing_cell(pts) >= 0
    return pv.PolyData(pts[inside][:n])


def streamlines(r: CFDResult, n=900):
    """Streamlines through seed points spread over the enclosure's inside, both directions (mm, mm/s time)."""
    air = r.air.cell_data_to_point_data() if 'U' not in r.air.point_data else r.air
    sl = air.streamlines_from_source(_seeds(r, n), vectors='U', integration_direction='both', max_steps=4000,
                                     max_length=2000.0, initial_step_length=0.5, step_unit='cl', terminal_speed=1e-4)
    return sl


def flow(r: CFDResult, path, colour_by='T_c', title='', subtitle='', note='', clim=None, size=(1600, 1000), n=900, lines=None):
    """Air paths through the enclosure, coloured by temperature (or speed), the lid and front cut away."""
    lo, hi = _enclosure_box(r)
    c = (lo + hi) / 2
    sl = lines if lines is not None else streamlines(r, n)
    p = _plotter(size)
    clim = clim or (r.t_range() if colour_by == 'T_c' else (0, float(np.percentile(sl['speed'], 99))))
    ramp, label = (TEMP_RAMP, 'Air temperature (°C)') if colour_by == 'T_c' else (SPEED_RAMP, 'Air speed (m/s)')
    sl = sl.clip_box(list(np.ravel(np.stack([lo - 12, hi + 12], 1))), invert=False)   # the inside, plus the vents
    tubes = sl.extract_surface(algorithm='dataset_surface').tube(radius=0.45)
    p.add_mesh(tubes, scalars=colour_by, cmap=cmap(ramp), clim=clim,
               scalar_bar_args=dict(title=label, vertical=True, position_x=0.9, position_y=0.18, width=0.035, height=0.62,
                                    color='#26323a', fmt='%.0f' if colour_by == 'T_c' else '%.2f', title_font_size=18, label_font_size=15))
    _context(p, r, clip=((0, 0, -1), (0, 0, hi[2] - 18)), plastic_opacity=0.35)
    _solids(p, r, r.t_range(), clip=None)
    _camera(p, c, 2.2 * float(np.max(hi - lo)), -32, 34)
    p.screenshot(str(path))
    p.close()
    return frame(path, title or 'Airflow', subtitle, note or 'Lines follow the air, seeded throughout the enclosure. Lid hidden, enclosure translucent.')


def walls(r: CFDResult, path, patch='enclosure', limit_c: Optional[float] = None, limit_label='', title='', subtitle='',
          note='', size=(1600, 1000)):
    """Air temperature against the enclosure's inner faces (adiabatic walls: what the plastic sits in), with the
    region past ``limit_c`` in the critical colour."""
    pv = _pv()
    surf = r.patches[r.fluid][patch]
    lo, hi = _enclosure_box(r)
    c = (lo + hi) / 2
    t = np.asarray(surf.cell_data['T_c'])
    clim = (r.ambient if hasattr(r, 'ambient') else float(np.percentile(t, 1)), max(float(t.max()), (limit_c or 0)))
    p = _plotter(size)
    cut = surf.clip(normal=(0, 0, -1), origin=(0, 0, hi[2] - 18), invert=False)    # lid off
    p.add_mesh(cut, scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, preference='cell',
               scalar_bar_args=dict(title='Wall air temperature (°C)', vertical=True, position_x=0.9, position_y=0.18, width=0.035,
                                    height=0.62, color='#26323a', fmt='%.0f', title_font_size=18, label_font_size=15))
    legend = []
    if limit_c is not None:
        hot = cut.threshold(limit_c, scalars='T_c', preference='cell')
        if hot.n_cells:
            p.add_mesh(hot, color=CRITICAL)
        legend = [(f'above {limit_c:.0f} °C {limit_label}'.strip(), CRITICAL)]
    for name in r.solids:
        p.add_mesh(r.solids[name].extract_surface(algorithm='dataset_surface'), scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, show_scalar_bar=False)
    for name, m in r.surfaces.items():
        if name not in ('enclosure', 'pcb', 'connectors') and name not in r.solids:
            p.add_mesh(m, color=METAL)
    _camera(p, c, 2.1 * float(np.max(hi - lo)), -35, 40)
    p.screenshot(str(path))
    p.close()
    return frame(path, title or 'Enclosure wall temperature', subtitle, note, legend=legend)


# --- animations --------------------------------------------------------------------------------------------------
def _writer(path, fps):
    imageio = require('imageio', _WHY)
    # imageio's ffmpeg writer already asks for yuv420p (plays everywhere)
    return imageio.get_writer(str(path), fps=fps, codec='libx264', quality=7, macro_block_size=8)


def animate_flow(r: CFDResult, path, seconds=8, fps=30, title='', n=700, size=(1280, 800), orbit_deg=50, colour_by='T_c'):
    """Moving dashes along the streamlines (each dash travels at the local air speed, time-scaled) while the camera
    turns slowly around the enclosure. MP4 (H.264)."""
    lo, hi = _enclosure_box(r)
    c = (lo + hi) / 2
    sl = streamlines(r, n).clip_box(list(np.ravel(np.stack([lo - 12, hi + 12], 1))), invert=False)
    t = np.asarray(sl['IntegrationTime'])
    t = t - t.min()
    period = float(np.percentile(t, 95)) / 6 or 1.0
    clim = r.t_range() if colour_by == 'T_c' else (0, float(np.percentile(sl['speed'], 99)))
    ramp = TEMP_RAMP if colour_by == 'T_c' else SPEED_RAMP
    frames = int(seconds * fps)
    w = _writer(path, fps)
    p = _plotter(size)
    _context(p, r, clip=((0, 0, -1), (0, 0, hi[2] - 18)), plastic_opacity=0.25)
    _solids(p, r, r.t_range())
    ghost = p.add_mesh(sl, color='#c9d3da', opacity=0.25, line_width=1)
    actor = None
    for k in range(frames):
        phase = (k / frames) * period * 3
        sl['dash'] = ((t - phase) % period) / period
        dashes = sl.threshold((0.0, 0.18), scalars='dash')
        if actor is not None:
            p.remove_actor(actor)
        actor = p.add_mesh(dashes.extract_surface(algorithm='dataset_surface').tube(radius=0.55) if dashes.n_points else dashes, scalars=colour_by,
                           cmap=cmap(ramp), clim=clim, show_scalar_bar=False) if dashes.n_points else None
        _camera(p, c, 2.2 * float(np.max(hi - lo)), -55 + orbit_deg * k / frames, 32)
        p.render()
        w.append_data(p.screenshot(return_img=True))
    w.close()
    p.close()
    return path


def animate_sweep(r: CFDResult, path, normal='x', seconds=6, fps=30, size=(1280, 800), clim=None):
    """A temperature section sweeping through the enclosure. MP4 (H.264)."""
    lo, hi = _enclosure_box(r)
    c = (lo + hi) / 2
    i = 'xyz'.index(normal)
    n = np.eye(3)[i]
    clim = clim or r.t_range()
    frames = int(seconds * fps)
    w = _writer(path, fps)
    p = _plotter(size)
    _context(p, r, clip=None, plastic_opacity=0.12, skip=('enclosure',))
    p.add_mesh(r.surfaces['enclosure'], color=PLASTIC, opacity=0.12) if 'enclosure' in r.surfaces else None
    actor = None
    for k in range(frames):
        o = c.copy()
        o[i] = lo[i] + 3 + (hi[i] - lo[i] - 6) * (0.5 - 0.5 * np.cos(2 * np.pi * k / frames))
        sl = r.air.slice(normal=n, origin=o).clip_box(list(np.ravel(np.stack([lo - 1, hi + 1], 1))), invert=False)
        if actor is not None:
            p.remove_actor(actor)
        actor = p.add_mesh(sl, scalars='T_c', cmap=cmap(TEMP_RAMP), clim=clim, show_scalar_bar=(k == 0),
                           scalar_bar_args=dict(title='Temperature (°C)', vertical=True, position_x=0.9, position_y=0.18, width=0.035,
                                                height=0.62, color='#26323a', fmt='%.0f'))
        _camera(p, c, 2.2 * float(np.max(hi - lo)), -40, 26)
        p.render()
        w.append_data(p.screenshot(return_img=True))
    w.close()
    p.close()
    return path


# --- charts ------------------------------------------------------------------------------------------------------
def convergence_chart(results: dict, path, title='Solver convergence'):
    """Initial residuals and the hottest temperature of each solid against iteration: one chart each (no dual axis)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    series = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300']
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2), dpi=120)
    res = results.get('residuals') or {}
    it = res.get('iteration', [])
    for (k, v), col in zip([(k, v) for k, v in res.items() if k != 'iteration'], series):
        y = [np.nan if x is None else x for x in v]
        axs[0].semilogy(it, y, color=col, lw=1.6, label=k)
    axs[0].set_title('Initial residuals (air)', loc='left', fontsize=11)
    axs[0].set_xlabel('iteration')
    axs[0].legend(frameon=False, fontsize=9, ncol=3)
    hist = results.get('T_max_history') or {}
    for (k, v), col in zip(hist.items(), series):
        a = np.array(v)
        axs[1].plot(a[:, 0], a[:, 1], color=col, lw=2, label=k)
        axs[1].annotate(f'{k} {a[-1, 1]:.1f} °C', (a[-1, 0], a[-1, 1]), xytext=(4, 0), textcoords='offset points', fontsize=9, color='#26323a')
    axs[1].set_title('Hottest temperature in each solid (°C)', loc='left', fontsize=11)
    axs[1].set_xlabel('iteration')
    if hist:
        axs[1].legend(frameon=False, fontsize=9)
    for ax in axs:
        ax.grid(alpha=0.25, lw=0.6)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
    fig.suptitle(title, x=0.01, ha='left', fontsize=13)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --- structural results (cadagent.fea.Study) -------------------------------------------------------------------
STRESS_RAMP = ['#f3f0fb', '#ddd6f5', '#c3b8ee', '#a597e6', '#8676dc', '#6250d6', '#4f3eb8', '#3d2f93', '#2b216b']


def _fea_grid(study, scale: float = 0.0, load: float = 1.0):
    pv = _pv()
    pts = study.points + scale * load * study.disp.T
    cells = np.hstack([np.full((len(study.tets), 1), 4), study.tets]).ravel()
    g = pv.UnstructuredGrid(cells, np.full(len(study.tets), 10, dtype=np.uint8), pts)     # 10 = VTK_TETRA
    g.cell_data['ratio'] = study.vm_elem * load / study.material.strength_mpa
    return g


def _fea_scale(study, frac=0.06):
    size = float(np.ptp(study.points, axis=0).max())
    dmax = float(np.linalg.norm(study.disp, axis=0).max())
    return frac * size / dmax if dmax > 0 else 1.0


def fea_view(study, path, title: str = '', subtitle: str = '', note: str = '', views=((-35, 30), (-35, -40)),
             size=(1600, 900), percentile: float = 99.9):
    """Stress over strength on the deformed part (one-hue ramp, scaled to the given percentile so a single notch
    element does not wash the picture out), anything past the strength in the critical colour. Two views side by side
    (default: from above and from below). The deformation is exaggerated by one stated factor."""
    pv = _pv()
    scale = _fea_scale(study)
    g = _fea_grid(study, scale)
    inner = ~study._touches_bc if hasattr(study, '_touches_bc') else np.ones(len(study.tets), bool)
    top = float(np.percentile(g.cell_data['ratio'][inner], percentile))
    surf = g.extract_surface(algorithm='dataset_surface')
    lo, hi = np.array(surf.bounds).reshape(3, 2).T
    c, span = (lo + hi) / 2, float(np.max(hi - lo))
    p = pv.Plotter(off_screen=True, window_size=size, shape=(1, len(views)), lighting='three lights', border=False)
    for i, (az, el) in enumerate(views):
        p.subplot(0, i)
        p.set_background(STAGE)
        p.add_mesh(surf, scalars='ratio', cmap=cmap(STRESS_RAMP), clim=(0, max(top, 1e-6)), show_scalar_bar=(i == len(views) - 1),
                   preference='cell', scalar_bar_args=dict(title='Stress / strength', vertical=True, position_x=0.86, position_y=0.2,
                                                           width=0.05, height=0.6, color='#26323a', fmt='%.2f'))
        over = surf.threshold(1.0, scalars='ratio', preference='cell')
        if over.n_cells:
            p.add_mesh(over, color=CRITICAL)
        _camera(p, c, 2.6 * span, az, el)
    p.screenshot(str(path))
    p.close()
    r = getattr(study, 'result', {})
    legend = [('past the strength', CRITICAL)] if (g.cell_data['ratio'] > 1).any() else []
    return frame(path, title or f'{study.name}: stress', subtitle or
                 f"{r.get('material', '')}: max deflection {r.get('max_displacement_mm')} mm; colour scaled to the {percentile:g}th-percentile "
                 f'stress ({top * study.material.strength_mpa:.1f} MPa)',
                 note or f'Linear elastic; deformation exaggerated x{scale:.0f}. Left: from above; right: from below.', legend=legend)


def fea_animate(study, path, overload: Optional[float] = None, seconds: float = 6, fps: int = 24, view=(-35, 30), size=(1280, 800),
                percentile: float = 99.9):
    """The load ramped from zero to ``overload`` x the design load (default: until the 99.9th-percentile stress
    reaches the strength, plus 30 %), deformation exaggerated, regions past the strength in the critical colour while
    the camera turns. Linear: each frame is the solved field times the load factor. MP4."""
    pv = _pv()
    scale = _fea_scale(study, 0.08)
    inner = ~study._touches_bc if hasattr(study, '_touches_bc') else np.ones(len(study.tets), bool)
    p999 = float(np.percentile(study.vm_elem[inner], percentile)) / study.material.strength_mpa
    end = overload or max(1.2, 1.3 / max(p999, 1e-6))
    frames = int(seconds * fps)
    w = _writer(path, fps)
    g0 = _fea_grid(study)
    lo, hi = np.array(g0.bounds).reshape(3, 2).T
    c, span = (lo + hi) / 2, float(np.max(hi - lo))
    for k in range(frames):
        lam = end * min(1.0, k / (frames * 0.8))
        g = _fea_grid(study, scale / end, lam)
        surf = g.extract_surface(algorithm='dataset_surface')
        p = _plotter(size)
        p.add_mesh(surf, scalars='ratio', cmap=cmap(STRESS_RAMP), clim=(0, 1), preference='cell', show_scalar_bar=False)
        over = surf.threshold(1.0, scalars='ratio', preference='cell')
        if over.n_cells:
            p.add_mesh(over, color=CRITICAL)
        state = 'design load' if abs(lam - 1) < end / frames else ('past the strength somewhere' if lam * p999 > 1 else 'loading')
        p.add_text(f'load x{lam:.2f}  ({state})', position='upper_left', font_size=12, color='#26323a')
        _camera(p, c, 2.0 * span, view[0] + 40 * k / frames, view[1])
        w.append_data(p.screenshot(return_img=True))
        p.close()
    w.close()
    return path
