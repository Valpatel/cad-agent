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
import math
import textwrap
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
# Chart colours: the site palette for paper, ink and chrome; series in a fixed categorical order (adjacent pairs
# checked for colour-vision deficiency on this paper), never cycled: past seven, lines are muted and named directly.
# The accent is kept for a run that stopped early.
PAPER, INK, PANEL, MUTED, WINDOW, ACCENT = '#fffdf5', '#173d3c', '#eef1e4', '#6f8a80', '#ffe1cc', '#bd3a12'
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6']


def _change(key, v) -> str:
    return 'n/a' if v is None else (f'{v:+.1f} %' if key.endswith('_pct') else f'{v:+.2f} °C').replace('-', '−')


_CONV_WORDS = (('_max_c_change', ' hottest'), ('_T_change_c', ' air in the block'), ('_flow_change_pct', ' flow'),
               ('_intake_c_change', ' air through the fan'), ('heat_out_change_pct', 'heat leaving'))


def _conv_name(key: str) -> str:
    for end, words in _CONV_WORDS:
        if key.endswith(end):
            return key[:-len(end)] + words
    return key


def _say(ax, title, text):
    """A panel with nothing to plot says why, instead of drawing an empty frame."""
    ax.set_axis_off()
    ax.set_title(title, loc='left', fontsize=10.5, color=INK)
    ax.text(0.5, 0.5, textwrap.fill(text, 60), ha='center', va='center', fontsize=9.5, color=INK, transform=ax.transAxes,
            bbox=dict(boxstyle='round,pad=0.9', fc=PANEL, ec='none'))


def _style(ax, title, caption, ylabel, xlabel='iteration'):
    ax.set_facecolor(PAPER)
    ax.set_title(title, loc='left', fontsize=10.5, color=INK, pad=16 if caption else 6)
    if caption:
        ax.text(0, 1.015, caption, transform=ax.transAxes, fontsize=8.5, color=MUTED, va='bottom')
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK)
    ax.grid(color=PANEL, lw=0.8)
    ax.set_axisbelow(True)
    ax.margins(x=0.01)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8.5)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(MUTED)


def _marks(ax, restarts, window, stopped_at):
    """Shared x-axis furniture: the convergence window shaded, restarts as thin lines, a stop in the accent colour."""
    if window:
        ax.axvspan(window[0], window[1], color=WINDOW, lw=0, zorder=0)
    for r in restarts:
        ax.axvline(r, color=MUTED, lw=0.7, alpha=0.55, zorder=1)
    if stopped_at is not None:
        ax.axvline(stopped_at, color=ACCENT, lw=1.3, zorder=3)


def _spread(ys, gap, lo, hi):
    """Label positions at least ``gap`` apart, each run of crowded labels centred on its lines, inside [lo, hi]."""
    groups = [[y] for y in ys]                    # ys sorted; a group's labels sit evenly around its mean
    merged = True
    while merged:
        merged, out = False, []
        for g in groups:
            if out and (np.mean(g) - (len(g) - 1) * gap / 2) - (np.mean(out[-1]) + (len(out[-1]) - 1) * gap / 2) < gap:
                out[-1] = out[-1] + g
                merged = True
            else:
                out.append(g)
        groups = out
    pos = [float(np.mean(g)) + (k - (len(g) - 1) / 2) * gap for g in groups for k in range(len(g))]
    shift = max(0.0, lo + gap / 2 - pos[0]) - max(0.0, pos[-1] - (hi - gap / 2))
    return [p + shift for p in pos]


def _end_labels(ax, ends, log=False, gap=0.075):
    """Name each line just outside the plot's right edge: ink text on a short leader in the line's colour, spread so
    no two overlap."""
    if not ends:
        return
    f, g = (np.log10, lambda y: 10 ** y) if log else ((lambda y: y), (lambda y: y))
    lo, hi = (f(v) for v in ax.get_ylim())
    ends = sorted(ends, key=lambda e: f(e[1]))
    ys = _spread([f(e[1]) for e in ends], (hi - lo) * gap, lo, hi)
    for (x, y, text, col), yl in zip(ends, ys):
        ax.annotate(text, (x, y), xytext=(1.02, g(yl)), textcoords=('axes fraction', 'data'), va='center', fontsize=8.5,
                    color=INK, annotation_clip=False,
                    arrowprops=dict(arrowstyle='-', color=col, lw=1.1, shrinkA=0, shrinkB=1))


def convergence_chart(results: dict, path, title='Solver convergence'):
    """The convergence of a cadagent.cfd run (the dict read_results returns), over the whole run: the air's initial
    residuals, then one panel per quantity the convergence claim rests on (the hottest temperature of each solid
    region, air temperatures in the fan and fin zones, fan flow, the heat leaving against the heat put in), each on
    its own axis. Restarts are marked, the window ``convergence`` measured is shaded and each panel states that
    window's change; a run that stopped early is marked and said so. A panel with nothing to plot says why, and a
    case with no solid regions has no solids panel. Results read before whole-run histories were kept are drawn as
    they are, with the iterations they cover stated. Residuals settling does not show the answer is right."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig = _convergence_figure(results, title)
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)
    return path


def _convergence_figure(results: dict, title: str):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    res = results.get('residuals') or {}
    its = [float(x) for x in res.get('iteration') or []]
    fields = [k for k in res if k != 'iteration']
    whole = 'restarts' in results                 # whole-run histories (older results kept the newest solve only)
    restarts = results.get('restarts') or []
    window = results.get('convergence_window')
    conv = results.get('convergence') or {}
    last = results.get('iterations') or (int(its[-1]) if its else None)
    planned = results.get('planned_iterations')
    stopped = results.get('solver_finished') is False and last is not None
    stopped_at = last if stopped else None
    solids = list(results.get('solids') or {})
    hist = results.get('T_max_history') or {}
    monitors = results.get('monitors')

    entities = solids + list(dict.fromkeys(m.get('name', k) for k, m in (monitors or {}).items()))
    colour = {e: SERIES[i] if i < len(SERIES) else MUTED for i, e in enumerate(entities)}

    def deltas(pairs):
        got = [f'{name} {_change(key, conv[key])}' for name, key in pairs if key in conv]
        return 'Change over the shaded window: ' + ' · '.join(got) if got and window else ''

    def since(points):                            # older results may start part-way through the run
        first = points[0][0] if len(points) else None
        if whole or first is None or first <= 10:
            return ''
        return f' ({first:g}–{points[-1][0]:g} only: earlier iterations are not in these results)'

    panels = []                                   # (draw(ax), full width)

    def residual_panel(ax):
        t = 'Initial residuals of the air solution'
        if not its or not fields:
            return _say(ax, t, 'No residual output found (postProcessing/<air region>/residuals): the solver may not have started.')
        every = results.get('residuals_every', 1)
        cap = 'Log scale. Air region only: solid regions\' energy residuals are not recorded.'
        if every > 1:
            cap += f' Each point is the largest residual over {every} iterations.'
        _style(ax, t, cap, 'initial residual (no unit)', 'iteration' + since([[its[0]], [its[-1]]]))
        _marks(ax, restarts, window, stopped_at)
        ends = []
        for i, k in enumerate(fields):
            y = np.array([np.nan if v is None else v for v in res[k]], float)
            col = SERIES[i] if i < len(SERIES) else MUTED
            ax.semilogy(its, y, color=col, lw=1.3, label=k, zorder=2)
            ok = np.flatnonzero(np.isfinite(y) & (y > 0))
            if len(ok):
                ends.append((its[ok[-1]], y[ok[-1]], k, col))
        ax.legend(loc='upper right', ncol=min(len(fields), 7), fontsize=8.5, labelcolor=INK, handlelength=1.4,
                  columnspacing=1.0, facecolor=PAPER, edgecolor='none', framealpha=0.9)
        if stopped:
            ax.text(stopped_at, ax.get_ylim()[0], 'stopped ', color=ACCENT, fontsize=8.5, va='bottom', ha='right')
        _end_labels(ax, ends, log=True, gap=0.055)
    panels.append((residual_panel, True))

    if solids:
        def solid_panel(ax):
            t = 'Hottest temperature in each solid region'
            have = {k: np.array(v, float) for k, v in hist.items() if len(v)}
            if not have:
                return _say(ax, t, f'No temperature history for the solid regions ({", ".join(solids)}): no T_max output was found.')
            _style(ax, t, deltas([(k, f'{k}_max_c_change') for k in have]), 'temperature (°C)',
                   'iteration' + since(next(iter(have.values()))))
            _marks(ax, restarts, window, stopped_at)
            for k, a in have.items():
                ax.plot(a[:, 0], a[:, 1], color=colour.get(k, MUTED), lw=1.6, label=k, zorder=2)
            if len(have) > 1:
                ax.legend(frameon=False, fontsize=8.5, labelcolor=INK, loc='best')
            _end_labels(ax, [(a[-1, 0], a[-1, 1], f'{k} {a[-1, 1]:.1f} °C', colour.get(k, MUTED)) for k, a in have.items()])
        panels.append((solid_panel, False))

    if monitors is None:                          # results read before monitored histories were kept
        def old_monitor_panel(ax):
            got = [f'{_conv_name(k)} {_change(k, v)}' for k, v in conv.items()]
            _say(ax, 'Monitored values', 'Their histories are not in these results. ' +
                 ('Change over the last fifth of the newest solve (convergence): ' + '; '.join(got) if got else
                  'No monitored values are recorded either.'))
        panels.append((old_monitor_panel, False))
    elif not monitors:
        panels.append((lambda ax: _say(ax, 'Monitored values', 'No fan-zone, fin-zone or heat-flux output was found.'), False))
    else:
        groups = {}
        for k, m in monitors.items():
            groups.setdefault((m['quantity'], m['unit']), []).append(m)
        for (quantity, unit), ms in groups.items():
            def monitor_panel(ax, quantity=quantity, unit=unit, ms=ms):
                cap = deltas([(m.get('name', m['label']), m['change']) for m in ms])
                q_in = results.get('heat_input_w')
                heat = unit == 'W'
                if heat and results.get('energy_balance_pct') is not None:
                    cap += (' · ' if cap else '') + f'energy balance {_change("_pct", results["energy_balance_pct"])} (within 5 % needed)'
                elif heat and q_in is None:
                    cap += (' · ' if cap else '') + 'heat put in unknown (an exchanger block has no target power): balance not checked'
                _style(ax, quantity, cap, f'{ {"°C": "temperature", "m³/h": "flow", "W": "heat"}.get(unit, quantity.lower())} ({unit})')
                _marks(ax, restarts, window, stopped_at)
                if heat and q_in is not None:
                    band = 0.05 * q_in if q_in else 0.5
                    ax.axhspan(q_in - band, q_in + band, color=MUTED, alpha=0.14, lw=0, zorder=1,
                               label=f'within {"5 %" if q_in else "0.5 W"} of the heat put in')
                    ax.axhline(q_in, color=INK, lw=1, zorder=1, label=f'heat put in, {q_in:g} W')
                ends = []
                for m in ms:
                    a = np.array(m['points'], float)
                    name = m.get('name', m['label'])
                    ax.plot(a[:, 0], a[:, 1], color=colour.get(name, MUTED), lw=1.6, label=m['label'], zorder=2)
                    ends.append((a[-1, 0], a[-1, 1], f'{name} {a[-1, 1]:.1f} {unit}', colour.get(name, MUTED)))
                if len(ms) > 1 or heat:
                    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK, loc='best')
                _end_labels(ax, ends)
            panels.append((monitor_panel, False))

    # layout: the residuals across the top, then two panels a row (the last one wide when the count is odd)
    small = [p for p in panels if not p[1]]
    rows = 1 + math.ceil(len(small) / 2)
    head = [(title, 14, INK)]
    if whole:
        span = f'Iterations 1–{last}' if last else 'No iterations'
        if restarts:
            shown = ', '.join(str(r) for r in restarts[:8]) + (', …' if len(restarts) > 8 else '')
            span += f' in {len(restarts) + 1} solves (thin lines: continuations from {shown})'
        if window:
            span += f'. Shaded: the window the convergence check measured, iterations {window[0]}–{window[1]}'
        head.append((span + '.', 9.5, INK))
    elif its:
        head.append((f'These results hold iterations {its[0]:g}–{its[-1]:g} only, from the newest solve: read the case again '
                     'with cadagent.cfd.read_results for the whole run.', 9.5, INK))
    if stopped:
        of = f' of {planned} planned' if planned and planned > last else ''
        head.append((f'Stopped early at iteration {last}{of}: the newest solve did not finish ({results.get("solver_log", "its log")} '
                     'has no End). The last values are not a converged answer.', 9.5, ACCENT))
    lines = [(textwrap.fill(t, 150 if s < 12 else 90), s, c) for t, s, c in head]
    head_in = 0.25 + sum(0.23 * (1 + t.count('\n')) * s / 9.5 for t, s, c in lines)
    foot = ('Settled residuals and monitored values show the solver stopped changing, not that the answer is right: check a '
            'finer mesh, the energy balance and the case\'s stated limits.')
    body_in = 3.4 + 2.7 * (rows - 1)
    fig = plt.figure(figsize=(12, head_in + body_in + 0.4), dpi=120, facecolor=PAPER, layout='constrained')
    top, body, bottom = fig.subfigures(3, 1, height_ratios=[head_in, body_in, 0.4])
    for sf in (top, body, bottom):
        sf.set_facecolor(PAPER)
    y = 0.12
    for t, s, c in lines:
        top.text(0.008, 1 - y / head_in, t, fontsize=s, color=c, ha='left', va='top')
        y += 0.23 * (1 + t.count('\n')) * s / 9.5 + (0.06 if s > 12 else 0)
    bottom.text(0.008, 0.5, foot, fontsize=8.5, color=MUTED, ha='left', va='center')
    gs = body.add_gridspec(rows, 2, height_ratios=[3.4] + [2.7] * (rows - 1))
    panels[0][0](body.add_subplot(gs[0, :]))
    for i, (draw, _) in enumerate(small):
        r, c = 1 + i // 2, i % 2
        draw(body.add_subplot(gs[r, :] if (i == len(small) - 1 and len(small) % 2) else gs[r, c]))
    return fig


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
