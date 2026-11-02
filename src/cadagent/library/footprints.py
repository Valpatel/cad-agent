"""KiCad footprints as data, written to ``.kicad_mod`` text without pcbnew.

A footprint here is a :class:`Footprint`: pads, graphic lines and circles on named layers, an optional net-tie pad
group and the 3D model it carries. :func:`to_kicad_mod` writes it in KiCad 9's file format (``version 20241229``),
which KiCad 9 and 10 read. Every UUID comes from the footprint's name and the item's place, so the same footprint gives
the same bytes each time.

The generators below are parametric. Their defaults are the parts they were drawn for, from each part's datasheet
(the dimensions and their sources are in ``cadagent.library.parts``). Conventions follow KiCad's library convention
(KLC) and its generators: millimetres, the origin at the footprint's centre (between the terminals of a two-terminal
part), y down as in KiCad's editor, and the courtyard 0.25 mm outside the body or the copper.

Limits: these are copper and drawing layers only. Whether the part fits the hole pattern, solders well or carries
its rated current is the datasheet's claim and the board's own check (DRC, the copper sizing), not this module's.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from cadagent.library.sexp import Sym, dump

FORMAT_VERSION = 20241229                  # KiCad 9's footprint format; KiCad 10 reads it and saves its own
NS = uuid.UUID('0b8f7a52-5d0e-4d7b-9c4e-2a7c7f0b2871')
PTH_LAYERS = ('*.Cu', '*.Mask')
SMD_LAYERS = ('F.Cu', 'F.Mask', 'F.Paste')

Drill = Union[None, float, Tuple[float, float]]


@dataclass(frozen=True)
class Pad:
    """One pad. ``kind`` is smd, thru_hole or np_thru_hole; ``shape`` circle, rect or oval; ``drill`` a diameter or an
    oval's (w, h). ``at`` and ``size`` in mm, footprint frame."""
    number: str
    kind: str
    shape: str
    at: Tuple[float, float]
    size: Tuple[float, float]
    drill: Drill = None
    layers: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in ('smd', 'thru_hole', 'np_thru_hole'):
            raise ValueError(f'pad kind {self.kind!r}')
        if self.shape not in ('circle', 'rect', 'oval', 'roundrect'):
            raise ValueError(f'pad shape {self.shape!r}')
        if min(self.size) <= 0:
            raise ValueError('pad size must be positive')
        if (self.kind == 'smd') != (self.drill is None):
            raise ValueError('an smd pad has no drill; a hole pad has one')
        if not self.layers:
            object.__setattr__(self, 'layers', SMD_LAYERS if self.kind == 'smd' else PTH_LAYERS)

    @property
    def drill_size(self) -> Optional[Tuple[float, float]]:
        if self.drill is None:
            return None
        return (self.drill, self.drill) if isinstance(self.drill, (int, float)) else tuple(self.drill)


@dataclass(frozen=True)
class Line:
    start: Tuple[float, float]
    end: Tuple[float, float]
    layer: str
    width: float


@dataclass(frozen=True)
class Circle:
    center: Tuple[float, float]
    radius: float
    layer: str
    width: float


@dataclass
class Footprint:
    name: str
    descr: str
    tags: str = ''
    attr: Optional[str] = None                 # 'smd', 'through_hole' or None (KiCad's "unspecified")
    pads: List[Pad] = field(default_factory=list)
    graphics: List[Union[Line, Circle]] = field(default_factory=list)
    net_tie_groups: Tuple[str, ...] = ()
    model: Optional[str] = None                # the STEP file's name in the library's .3dshapes folder
    datasheet: str = ''

    def rect(self, x0, y0, x1, y1, layer, width):
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            self.graphics.append(Line(a, b, layer, width))

    def circle(self, r, layer, width, c=(0.0, 0.0)):
        self.graphics.append(Circle(c, r, layer, width))

    def pad(self, *args, **kw) -> Pad:
        p = Pad(*args, **kw)
        self.pads.append(p)
        return p


def _uid(fp: str, *parts) -> str:
    return str(uuid.uuid5(NS, '/'.join([fp, *map(str, parts)])))


def _xy(key, v):
    return [Sym(key), float(v[0]), float(v[1])]


def to_kicad_mod(fp: Footprint, model_dir: Optional[str] = None) -> str:
    """The footprint as ``.kicad_mod`` text. ``model_dir`` is the folder its model path starts with, written as KiCad
    expects it (``${KIPRJMOD}/lib/cad-agent.3dshapes``, an environment variable such as
    ``${CADAGENT_3DMODEL_DIR}``, never an absolute home path); without it the footprint carries no model."""
    n = fp.name
    S = Sym
    out: list = [S('footprint'), n, [S('version'), FORMAT_VERSION], [S('generator'), 'cad-agent'],
                 [S('layer'), 'F.Cu'], [S('descr'), fp.descr]]
    if fp.tags:
        out.append([S('tags'), fp.tags])

    def prop(name, value, hide):
        p = [S('property'), name, value, [S('at'), 0.0, 0.0, 0], [S('layer'), 'F.Fab']]
        if hide:
            p.append([S('hide'), S('yes')])
        p += [[S('uuid'), _uid(n, 'property', name)], [S('effects'), [S('font'), [S('size'), 1.0, 1.0],
                                                                    [S('thickness'), 0.15]]]]
        return p
    out += [prop('Reference', 'REF**', False), prop('Value', n, True), prop('Datasheet', fp.datasheet, True),
            prop('Description', fp.descr, True)]
    if fp.attr:
        out.append([S('attr'), S(fp.attr)])
    if fp.net_tie_groups:
        out.append([S('net_tie_pad_groups'), *fp.net_tie_groups])
    for i, g in enumerate(fp.graphics):
        stroke = [S('stroke'), [S('width'), g.width], [S('type'), S('solid')]]
        if isinstance(g, Line):
            out.append([S('fp_line'), _xy('start', g.start), _xy('end', g.end), stroke, [S('layer'), g.layer],
                        [S('uuid'), _uid(n, 'g', i)]])
        else:
            out.append([S('fp_circle'), _xy('center', g.center), _xy('end', (g.center[0] + g.radius, g.center[1])),
                        stroke, [S('fill'), S('no')], [S('layer'), g.layer], [S('uuid'), _uid(n, 'g', i)]])
    for i, p in enumerate(fp.pads):
        row = [S('pad'), p.number, S(p.kind), S(p.shape), _xy('at', p.at), [S('size'), float(p.size[0]),
                                                                           float(p.size[1])]]
        if p.drill is not None:
            if isinstance(p.drill, (int, float)):
                row.append([S('drill'), float(p.drill)])
            else:
                row.append([S('drill'), S('oval'), float(p.drill[0]), float(p.drill[1])])
        row.append([S('layers'), *p.layers])
        if p.kind == 'thru_hole':
            row.append([S('remove_unused_layers'), S('no')])
        row.append([S('uuid'), _uid(n, 'pad', i)])
        out.append(row)
    if fp.model and model_dir:
        out.append([S('model'), f'{model_dir.rstrip("/")}/{fp.model}', [S('offset'), [S('xyz'), 0, 0, 0]],
                    [S('scale'), [S('xyz'), 1, 1, 1]], [S('rotate'), [S('xyz'), 0, 0, 0]]])
    return dump(out) + '\n'


# ------------------------------------------------------------------------------------------------ the generators

def fuseholder_mini_fl1(pitch: float = 8.0, terminal_drill: float = 1.5, terminal_pad: float = 3.2,
                        peg_slot: Tuple[float, float] = (2.7, 4.3), body: Tuple[float, float] = (14.2, 6.0)
                        ) -> Footprint:
    """Littelfuse MINI FL1 PCB holder 178.6764.0001 for MINI (FK1) blade fuses (datasheet rev 111616).

    Terminals ``pitch`` apart along x in ``terminal_drill`` holes (8 +-0.15 in 1.5 +-0.1). The snap-in peg needs a
    2.7 +-0.1 hole 0.8 off the terminals' line, and the datasheet does not say which side, so an oval NPTH slot on
    the centre (``peg_slot``, 2.7 x 4.3) takes either. Body ``body`` (14.2 x 6). Pads ``terminal_pad`` (3.2) leave
    0.85 mm of annular ring for the leaf-spring terminals' current."""
    w, h = body
    fp = Footprint('Fuseholder_Blade_Mini_Littelfuse_FL1_178.6764.0001',
                   'Littelfuse MINI FL1 PCB holder 178.6764.0001 for MINI (FK1) blade fuses, 30 A max, 22 A continuous',
                   tags='fuse holder blade mini FL1 Littelfuse', attr='through_hole', model='Fuseholder_Mini_FL1.step',
                   datasheet='https://www.littelfuse.com/products/fuses-overcurrent-protection/fuse-holders-fuse-blocks'
                             '-accessories/fuse-holders/in-line-fuse-holders/mini-fl1/178-6764-0001')
    fp.rect(-w / 2 - 0.12, -h / 2 - 0.12, w / 2 + 0.12, h / 2 + 0.12, 'F.SilkS', 0.15)
    fp.rect(-w / 2 - 0.25, -h / 2 - 0.25, w / 2 + 0.25, h / 2 + 0.25, 'F.CrtYd', 0.05)
    fp.rect(-w / 2, -h / 2, w / 2, h / 2, 'F.Fab', 0.1)
    fp.pad('', 'np_thru_hole', 'oval', (0.0, 0.0), peg_slot, drill=peg_slot)
    fp.pad('1', 'thru_hole', 'circle', (-pitch / 2, 0.0), (terminal_pad, terminal_pad), drill=terminal_drill)
    fp.pad('2', 'thru_hole', 'circle', (pitch / 2, 0.0), (terminal_pad, terminal_pad), drill=terminal_drill)
    return fp


def shunt_bourns_css2h_3920_kelvin(pad: Tuple[float, float] = (3.40, 6.20), span: float = 11.00,
                                   probes: float = 8.40, body: Tuple[float, float] = (10.00, 5.20),
                                   tap: float = 0.5) -> Footprint:
    """Bourns CSS2H-3920 current-sense resistor (2-terminal metal strip) on a 4-terminal (Kelvin) layout.

    Pads ``pad`` (3.40 x 6.20) with outer edges ``span`` apart (11.00): centres at +-3.80, Bourns' recommended
    layout. The sense taps (pads 2 and 3, ``tap`` square) sit at Bourns' recommended measurement points, ``probes``
    (8.40) apart, on the pads' -y edges, so the sense lines leave sideways of the current. Pads 1-2 and 3-4 are
    net-tie groups: 1 and 4 carry the current, 2 and 3 are the Kelvin taps."""
    px = (span - pad[0]) / 2
    ty = -pad[1] / 2 - tap - 0.05
    fp = Footprint('R_Shunt_Bourns_CSS2H-3920_Kelvin',
                   'Bourns CSS2H-3920 current-sense resistor, 4-terminal (Kelvin) layout, net-tied sense pads',
                   tags='shunt kelvin current sense Bourns CSS2H 3920', attr='smd', model='R_Shunt_Bourns_CSS2H-3920.step',
                   net_tie_groups=('1, 2', '3, 4'), datasheet='https://www.bourns.com/data/global/pdfs/CSS2H-3920.pdf')
    fp.graphics.append(Line((-probes / 2, ty), (-probes / 2, -pad[1] / 2 + 0.2), 'F.Cu', 0.3))
    fp.graphics.append(Line((probes / 2, ty), (probes / 2, -pad[1] / 2 + 0.2), 'F.Cu', 0.3))
    sy = pad[1] / 2 + 0.25                                  # silk between the pads, clear of their edges
    fp.graphics.append(Line((-1.6, -sy), (1.6, -sy), 'F.SilkS', 0.15))
    fp.graphics.append(Line((-1.6, sy), (1.6, sy), 'F.SilkS', 0.15))
    fp.rect(-span / 2 - 0.25, ty - tap / 2 - 0.25, span / 2 + 0.25, pad[1] / 2 + 0.25, 'F.CrtYd', 0.05)
    fp.rect(-body[0] / 2, -body[1] / 2, body[0] / 2, body[1] / 2, 'F.Fab', 0.1)
    fp.pad('1', 'smd', 'rect', (-px, 0.0), pad)
    fp.pad('2', 'smd', 'rect', (-probes / 2, ty), (tap, tap))
    fp.pad('3', 'smd', 'rect', (probes / 2, ty), (tap, tap))
    fp.pad('4', 'smd', 'rect', (px, 0.0), pad)
    return fp


def _via_ring(fp: Footprint, radius: float, n: int = 8, via: float = 0.95, drill: float = 0.4):
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        fp.pad('1', 'thru_hole', 'circle', (round(radius * math.cos(a), 6), round(radius * math.sin(a), 6)),
               (via, via), drill=drill)


def lug_stud(size: str = 'M4', pad: Optional[float] = None, drill: Optional[float] = None,
             via_ring: Optional[float] = None) -> Footprint:
    """A power stud for a ring lug: a plated clearance hole in a round pad on both layers, ringed with 8 stitching
    vias (0.4 drill, 0.95 pad) that share the current between the layers. The screw goes through from above with the
    lug on the top pad; the nut is under the board. Defaults per size: M4 pad 7.0, hole 4.3 (ISO 273 medium); M6 pad
    12.0, hole 6.4. The via ring sits midway between the hole and the pad edge, plus 0.15."""
    d = {'M4': (7.0, 4.3), 'M5': (10.0, 5.3), 'M6': (12.0, 6.4)}
    if size not in d and (pad is None or drill is None):
        raise ValueError(f'no default pad and hole for {size}: give pad= and drill=')
    pad = pad if pad is not None else d[size][0]
    drill = drill if drill is not None else d[size][1]
    if drill >= pad:
        raise ValueError('the hole must be smaller than the pad')
    rv = via_ring if via_ring is not None else (drill / 2 + pad / 2) / 2 + 0.15
    fp = Footprint(f'LugStud_{size}_Pad{pad:.1f}mm_Drill{drill:.1f}mm_Via8',
                   f'{size} lug stud: plated {drill:g} mm hole, {pad:g} mm pad both sides, 8 stitching vias',
                   tags=f'stud lug ring terminal {size} power', model=f'LugStud_{size}.step')
    fp.circle(pad / 2 + 0.25, 'F.CrtYd', 0.05)
    fp.circle(pad / 2 + 0.15, 'F.Fab', 0.1)
    fp.pad('1', 'thru_hole', 'circle', (0.0, 0.0), (pad, pad), drill=drill)
    _via_ring(fp, rv)
    return fp


def bonded_mounting_hole(size: str = 'M5', pad: float = 10.0, drill: float = 5.3, via_ring: float = 4.0,
                         standoff_d: Optional[float] = 12.0, head: str = 'socket') -> Footprint:
    """A plated mounting hole that bonds the board's net to the metal it is screwed to: a pad on both layers ringed
    with 8 vias. ``standoff_d`` draws the standoff under the board on B.Fab. ``head`` names the screw the 3D model
    shows (``socket`` or ``button``; ``parts.PARTS['bond_hole_m5']`` builds the M5 x 14 socket head). Defaults: M5,
    10 mm pad, 5.3 hole, vias on a 4.0 radius."""
    fp = Footprint(f'MountingHole_{size}_Pad{pad:.1f}mm_Drill{drill:.1f}mm_Via8_Bond',
                   f'{size} mounting hole, plated, {pad:g} mm pad both sides with 8 vias: bonds the net to the plate',
                   tags=f'mounting hole bond {size}', model=f'MountingScrew_{size}_{head}.step')
    fp.circle(pad / 2 + 0.5, 'F.CrtYd', 0.05)
    if standoff_d:
        fp.circle(standoff_d / 2, 'B.Fab', 0.1)
    fp.pad('1', 'thru_hole', 'circle', (0.0, 0.0), (pad, pad), drill=drill)
    _via_ring(fp, via_ring)
    return fp


def npth_slot(width: float = 4.0, length: float = 10.0) -> Footprint:
    """A non-plated slot (a cable tie, a key). A hole, not a part: it has no 3D model, by design."""
    fp = Footprint(f'Slot_NPTH_{width:.1f}x{length:.1f}mm', f'non-plated slot {width:g} x {length:g} mm',
                   tags='slot NPTH cable tie')
    fp.rect(-width / 2 - 0.5, -length / 2 - 0.5, width / 2 + 0.5, length / 2 + 0.5, 'F.CrtYd', 0.05)
    fp.pad('', 'np_thru_hole', 'oval', (0.0, 0.0), (width, length), drill=(width, length))
    return fp


def write_pretty(footprints: Sequence[Footprint], folder, model_dir: Optional[str] = None) -> List[str]:
    """Write each footprint to ``folder`` (a ``.pretty`` folder) and return the file names written."""
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for fp in footprints:
        p = folder / f'{fp.name}.kicad_mod'
        text = to_kicad_mod(fp, model_dir)
        if not p.exists() or p.read_text() != text:
            p.write_text(text)
        names.append(p.name)
    return names
