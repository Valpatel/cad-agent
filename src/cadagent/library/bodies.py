"""3D bodies for the library's footprints, built in CadQuery and written as coloured STEP at use time.

Each builder returns a ``cadquery.Assembly`` in KiCad's model frame:
- millimetres, with the origin at the footprint's origin;
- z = 0 on the board's top face, the part on +z and its pins through the board on -z;
- x as in the footprint, and y **up** (KiCad's 3D viewer negates the footprint's y). A pad at footprint (x, y)
  meets the model at (x, -y).

This is the convention KiCad's own model generators use (``kicad-library-tools``, which is GPL-3.0 and so is not
vendored here). Every child is named for the pad it meets: ``pin<n>`` for a lead through pad n's hole,
``terminal<n>`` for a surface terminal on pad n, and ``peg`` for a locating peg. ``cadagent.library.audit`` checks
those names against the footprint, which is the pin-1 frame.

The bodies are **envelopes** drawn from the datasheet's dimensions (``cadagent.library.parts``). They are good for
pictures, assembly clearance and the board's 3D view, and they are not the manufacturer's model: a datasheet
dimension the drawing does not give is marked as an assumption where it is used. Hardware stacks (screw, lug, nut)
take their sizes from ``cadagent.library.hardware``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from cadagent._deps import require
from cadagent.library import hardware

# RGB 0-1
BLACK_PLASTIC = (0.10, 0.10, 0.11)
TIN = (0.80, 0.80, 0.78)
ALLOY = (0.42, 0.36, 0.30)
BLACK_OXIDE = (0.16, 0.16, 0.17)
ZINC = (0.72, 0.73, 0.75)
TINNED_COPPER = (0.84, 0.70, 0.52)
# MINI blade fuse housing colours by rating (ISO 8820-3 / SAE J2077 colour code)
FUSE_COLOURS = {2: (0.55, 0.55, 0.55), 3: (0.55, 0.30, 0.65), 4: (0.95, 0.60, 0.70), 5: (0.80, 0.65, 0.45),
                7.5: (0.45, 0.28, 0.15), 10: (0.85, 0.10, 0.10), 15: (0.15, 0.35, 0.85), 20: (0.95, 0.85, 0.10),
                25: (0.92, 0.92, 0.88), 30: (0.15, 0.65, 0.25)}


def _cq():
    return require('cadquery', 'library 3D bodies')


def _box(cq, x0, x1, y0, y1, z0, z1):
    return cq.Workplane('XY').box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0)).val()


def _color(cq, rgb):
    return cq.Color(*rgb)


def fuseholder_mini_fl1(body=(14.2, 6.0), height=15.6, pitch=8.0, peg_tip=4.4, pin_tip=3.3, peg_offset=0.8):
    """Littelfuse MINI FL1 178.6764.0001: body ``body`` x ``height`` (14.2 x 6 x 15.6) on the board, terminal pins
    ``pitch`` apart (8) reaching ``pin_tip`` below the seat, the snap-in peg ``peg_offset`` off the terminals' line
    reaching ``peg_tip`` below (20 - 15.6 = 4.4 from the drawing). Assumptions: the pins are drawn as 1.0 x 0.5 mm blades and
    the peg as a 2.4 mm round, and ``pin_tip`` (3.3) is read from the drawing's 1.1 mm step above the peg's tip. The
    datasheet does not say which side of the line the peg is on, so the footprint's oval slot takes either."""
    cq = _cq()
    w, d = body
    a = cq.Assembly(name='Fuseholder_Mini_FL1')
    shell = _box(cq, -w / 2, w / 2, -d / 2, d / 2, 0.0, height)
    pocket = _box(cq, -5.6, 5.6, -2.0, 2.0, height - 3.0, height + 1.0)      # the fuse's socket, 3 deep (drawing)
    a.add(cq.Workplane().add(shell).cut(cq.Workplane().add(pocket)), name='body', color=_color(cq, BLACK_PLASTIC))
    for n, x in (('1', -pitch / 2), ('2', pitch / 2)):
        a.add(_box(cq, x - 0.5, x + 0.5, -0.25, 0.25, -pin_tip, 0.5), name=f'pin{n}', color=_color(cq, TIN))
    peg = cq.Solid.makeCylinder(1.2, peg_tip + 0.5, cq.Vector(0.0, peg_offset, -peg_tip))
    a.add(peg, name='peg', color=_color(cq, BLACK_PLASTIC))
    return a


def mini_fuse(amps: float, holder_height=15.6, head=(10.9, 3.8), above=8.8):
    """A MINI blade fuse seated in the FL1 holder: the housing (``head``, 10.9 x 3.8) in its rating's colour, from
    the bottom of the holder's 3 mm socket to ``above`` mm proud of the holder's top. ``head`` and ``above`` (8.8) are
    assumptions: the holder's drawing gives neither, so measure a fitted fuse before relying on the height. The
    blades are inside the holder and not drawn."""
    cq = _cq()
    if amps not in FUSE_COLOURS:
        raise ValueError(f'no MINI fuse colour for {amps} A; ratings: {sorted(FUSE_COLOURS)}')
    a = cq.Assembly(name=f'MiniFuse_{amps:g}A')
    w, t = head
    a.add(_box(cq, -w / 2, w / 2, -t / 2, t / 2, holder_height - 3.0, holder_height + above), name='fuse',
          color=_color(cq, FUSE_COLOURS[amps]))
    return a


def shunt_css2h_3920(length=10.0, width=5.2, height=0.93, terminal=3.0):
    """Bourns CSS2H-3920: a metal strip ``length`` x ``width`` (10.00 x 5.20), ``height`` thick (H max 0.93 for
    the 1L00 value), tinned copper terminals ``terminal`` long (3.00) welded to the resistive alloy between them. Pad
    1 is at -x and pad 4 at +x, as in the footprint."""
    cq = _cq()
    a = cq.Assembly(name='R_Shunt_Bourns_CSS2H-3920')
    L, W = length / 2, width / 2
    a.add(_box(cq, -L, -L + terminal, -W, W, 0.0, height), name='terminal1', color=_color(cq, TIN))
    a.add(_box(cq, -L + terminal, L - terminal, -W, W, 0.0, height), name='element', color=_color(cq, ALLOY))
    a.add(_box(cq, L - terminal, L, -W, W, 0.0, height), name='terminal4', color=_color(cq, TIN))
    return a


def _hex_prism(cq, s, z0, z1, bore):
    nut = cq.Workplane('XY').polygon(6, s / 0.8660254).extrude(z1 - z0).translate((0, 0, z0))
    return nut.cut(cq.Workplane('XY').circle(bore / 2).extrude(z1 - z0).translate((0, 0, z0))).val()


def _screw(cq, size, head, length, seat):
    """A screw with its head's underside at z = ``seat`` and the shank down to ``seat - length``, as (head, shank):
    two children, so the head is what seats and the shank is what passes through the hole."""
    d = float(size[1:])
    h = hardware.row(head, size)
    dk, k, s = h['dk'], h['k'], h['s']
    shank = cq.Solid.makeCylinder(d / 2, length, cq.Vector(0, 0, seat - length))
    if head == 'button_head':
        top = cq.Workplane('XY').circle(dk / 2).extrude(k).edges('>Z').fillet(k * 0.6).translate((0, 0, seat))
    else:
        top = cq.Workplane('XY').circle(dk / 2).extrude(k).translate((0, 0, seat))
    sock = cq.Workplane('XY').polygon(6, s / 0.8660254).extrude(k * 0.6).translate((0, 0, seat + k * 0.4 + 0.01))
    return top.cut(sock).val(), shank


def lug_stud(size='M4', screw_length=12.0, board=1.6, head='socket_head'):
    """A lug stud's hardware on the board: the ring lug on the top pad, a ``head`` screw ``screw_length`` long down
    through it and the board, and a nyloc nut on the board's underside (in a project, often held in a printed
    standoff's pocket). The lug is drawn as its ring only; its tongue and barrel point along the wire, which the
    footprint does not know."""
    cq = _cq()
    lug = hardware.row('ring_lug', size)
    nut = hardware.row('nyloc_nut', size)
    d = float(size[1:])
    a = cq.Assembly(name=f'LugStud_{size}')
    ring = cq.Workplane('XY').circle(lug['od'] / 2).circle(d / 2 + 0.2).extrude(lug['t']).val()
    a.add(ring, name='lug', color=_color(cq, TINNED_COPPER))
    top, shank = _screw(cq, size, head, screw_length, lug['t'])
    a.add(top, name='head', color=_color(cq, BLACK_OXIDE))
    a.add(shank, name='pin1', color=_color(cq, BLACK_OXIDE))
    a.add(_hex_prism(cq, nut['s'], -board - nut['m'], -board, d), name='nut', color=_color(cq, ZINC))
    return a


def mounting_screw(size='M5', head='button_head', screw_length=12.0):
    """A screw in a plated mounting hole: the head on the top pad, the shank down through the board into whatever
    it bonds to (a flush nut in a plate; not drawn)."""
    cq = _cq()
    a = cq.Assembly(name=f'MountingScrew_{size}_{head.split("_")[0]}')
    top, shank = _screw(cq, size, head, screw_length, 0.0)
    a.add(top, name='head', color=_color(cq, BLACK_OXIDE))
    a.add(shank, name='pin1', color=_color(cq, BLACK_OXIDE))
    return a


def boxes(assy, board: float = 1.6) -> List[Dict]:
    """Each named child's axis-aligned box, in the model frame: ``[{'name', 'min': (x, y, z), 'max': (x, y, z),
    'through'}]``. ``through`` is the xy box ``((x0, y0), (x1, y1))`` of the part of the child inside the board's
    thickness (``board`` mm under z = 0), or None when nothing of it is there. ``cadagent.library.audit.registration``
    checks these against the footprint without needing CadQuery."""
    cq = _cq()
    out = []
    for child in assy.children:
        shape = child.obj if isinstance(child.obj, cq.Shape) else cq.Compound.makeCompound(
            [o for o in child.obj.vals() if isinstance(o, cq.Shape)])
        shape = shape.moved(child.loc)
        bb = shape.BoundingBox()
        through = None
        slab = cq.Solid.makeBox(1e3, 1e3, board - 0.02, cq.Vector(-500, -500, -board + 0.01))
        cut = shape.intersect(slab)
        if cut.isValid() and cut.Volume() > 1e-6:
            tb = cut.BoundingBox()
            through = ((tb.xmin, tb.ymin), (tb.xmax, tb.ymax))
        out.append({'name': child.name, 'min': (bb.xmin, bb.ymin, bb.zmin), 'max': (bb.xmax, bb.ymax, bb.zmax),
                    'through': through})
    return out


def write_step(assy, path: Path, name: Optional[str] = None) -> Path:
    """Write ``assy`` as coloured STEP with the same bytes every time (``cadagent.geometry.export_step``)."""
    from cadagent.geometry import export_step
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return export_step(assy, path, name=name or path.stem)
