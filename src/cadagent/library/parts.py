"""The library's parts: for each, its footprint generator, its 3D body, its datasheet numbers (the golden vectors the
tests hold the footprint and body to) and where they came from, with the licence of every source.

``build(out, ...)`` writes a KiCad library a project can point its ``fp-lib-table`` at:

    <out>/<lib>.pretty/<footprint>.kicad_mod      footprints, each carrying its model path
    <out>/<lib>.3dshapes/<model>.step             coloured STEP bodies (needs the ``cad`` extra: CadQuery)

The STEP files are built here, at use time, and never committed to cad-agent. A project may commit its own copy.
Nothing in the library is copied from KiCad's libraries or a vendor's CAD: footprints and bodies are drawn from the
datasheets' numbers, so the library is MIT like the rest of cad-agent. Parts the stock KiCad libraries already have
(0603 and 2512 chips, TSSOP-10, JST GH) are used from KiCad by name and ``${KICAD10_3DMODEL_DIR}``, not copied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from cadagent.library import footprints as F

LIBRARY = 'cad-agent'


@dataclass
class Part:
    key: str
    footprint: Callable[[], F.Footprint]
    body: Optional[Callable] = None              # cadagent.library.bodies builder; None: a hole, no part
    body_args: dict = field(default_factory=dict)
    datasheet: dict = field(default_factory=dict)  # name -> (value, tolerance or None, where on the datasheet)
    source: str = ''
    licence: str = ''
    no_body: str = ''                            # why it has no body (a hole, bare copper)


def _bodies():
    from cadagent.library import bodies
    return bodies


PARTS: Dict[str, Part] = {p.key: p for p in [
    Part('fuseholder_mini_fl1', F.fuseholder_mini_fl1, body=lambda: _bodies().fuseholder_mini_fl1(),
         datasheet={'terminal_pitch': (8.0, 0.15, 'hole pattern'), 'terminal_hole': (1.5, 0.1, 'hole pattern'),
                    'peg_hole': (2.7, 0.1, 'hole pattern'), 'peg_offset': (0.8, 0.05, 'hole pattern'),
                    'body_length': (14.2, None, 'front view'), 'body_width': (6.0, None, 'side view'),
                    'body_height': (15.6, None, 'side view'), 'overall_height': (20.0, None, 'side view'),
                    'fuse_pocket_depth': (3.0, None, 'front view'), 'current_max_a': (30.0, None, 'specifications')},
         source='Littelfuse "PCB mount fuse holder for MINI style blade fuse", 178.6764.0001, rev 111616 (2016)',
         licence='datasheet numbers only; no vendor CAD used'),
    Part('shunt_css2h_3920', F.shunt_bourns_css2h_3920_kelvin, body=lambda: _bodies().shunt_css2h_3920(),
         datasheet={'pad_length': (3.40, None, 'recommended pad layout'),
                    'pad_width': (6.20, None, 'recommended pad layout'),
                    'pad_outer_span': (11.00, None, 'recommended pad layout'),
                    'sense_points': (8.40, None, 'recommended measurements'),
                    'body_length': (10.00, 0.30, 'product dimensions'), 'body_width': (5.20, 0.30, 'product dimensions'),
                    'height_max_1L00': (0.93, None, 'dimension table, CSS2H-3920R-1L00x'),
                    'terminal_length': (3.00, 0.30, 'product dimensions')},
         source='Bourns "Model CSS2H-3920 Series Current Sense Resistor" datasheet, read 2026-11-01 '
                '(https://www.bourns.com/data/global/pdfs/CSS2H-3920.pdf)',
         licence='datasheet numbers only; no vendor CAD used'),
    Part('lug_stud_m4', lambda: F.lug_stud('M4'), body=lambda: _bodies().lug_stud('M4', 12.0),
         datasheet={'hole': (4.3, None, 'ISO 273 medium clearance for M4')},
         source='ISO 273 (clearance holes); hardware from cadagent.library.hardware', licence='MIT (ours)'),
    Part('lug_stud_m6', lambda: F.lug_stud('M6'), body=lambda: _bodies().lug_stud('M6', 12.0),
         datasheet={'hole': (6.4, None, 'ISO 273 medium clearance for M6')},
         source='ISO 273 (clearance holes); hardware from cadagent.library.hardware', licence='MIT (ours)'),
    Part('bond_hole_m5', F.bonded_mounting_hole, body=lambda: _bodies().mounting_screw('M5', 'button_head', 12.0),
         datasheet={'hole': (5.3, None, 'ISO 273 medium clearance for M5')},
         source='ISO 273 (clearance holes); hardware from cadagent.library.hardware', licence='MIT (ours)'),
    Part('slot_4x10', F.npth_slot, no_body='a non-plated slot: a hole, not a part',
         source='ours', licence='MIT (ours)'),
]}

# footprints with no part on them that a board audit should accept, with the reason (stock KiCad names)
NO_PART_FOOTPRINTS = {
    'TestPoint:TestPoint_THTPad': 'a bare test pad: copper, not a part',
    'TestPoint:TestPoint_Pad': 'a bare test pad: copper, not a part',
    'MountingHole:MountingHole': 'a bare mounting hole: nothing is fitted',
}


def footprints(keys: Optional[Sequence[str]] = None) -> List[F.Footprint]:
    return [PARTS[k].footprint() for k in (keys or PARTS)]


def build(out, model_dir: Optional[str] = None, lib: str = LIBRARY, keys: Optional[Sequence[str]] = None,
          models: bool = True, fuses: Sequence[float] = ()) -> dict:
    """Write ``<out>/<lib>.pretty`` and (with ``models``) ``<out>/<lib>.3dshapes``. ``model_dir`` is how the
    footprints name the model folder (default ``${KIPRJMOD}/<lib>.3dshapes``, right when ``out`` is the project's
    folder). ``fuses`` adds a ``MiniFuse_<A>A.step`` per rating, a second model a board places on each holder.
    Returns what was written."""
    out = Path(out)
    keys = list(keys or PARTS)
    unknown = sorted(set(keys) - set(PARTS))
    if unknown:
        raise KeyError(f'unknown parts {unknown}; the library has {", ".join(PARTS)}')
    model_dir = model_dir or f'${{KIPRJMOD}}/{lib}.3dshapes'
    written = {'footprints': F.write_pretty(footprints(keys), out / f'{lib}.pretty', model_dir), 'models': []}
    if models:
        bodies = _bodies()
        shapes = out / f'{lib}.3dshapes'
        for k in keys:
            p = PARTS[k]
            if p.body is None:
                continue
            name = p.footprint().model
            bodies.write_step(p.body(), shapes / name)
            written['models'].append(name)
        for amps in fuses:
            name = f'MiniFuse_{amps:g}A.step'
            bodies.write_step(bodies.mini_fuse(amps), shapes / name)
            written['models'].append(name)
    return written


def fp_lib_table_entry(lib: str = LIBRARY, uri: str = '${KIPRJMOD}/cad-agent.pretty') -> str:
    """The ``fp-lib-table`` line that points a project at a built library."""
    return f'  (lib (name "{lib}")(type "KiCad")(uri "{uri}")(options "")(descr "cad-agent parts library"))'
