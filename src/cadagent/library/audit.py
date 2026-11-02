"""Checks that a board shows every part: the model audit, and the registration of a 3D body on its footprint.

``model_audit(path)`` reads a ``.kicad_pcb`` (each placed footprint) or a ``.pretty`` folder or ``.kicad_mod`` file
(each library footprint) and reports, per footprint:

* ``no_model``: it carries no 3D model and no waiver says why (a test pad or a slot is copper or a hole, not a part:
  waive it with the reason);
* ``missing_model``: a model path that does not resolve to a file. ``${KIPRJMOD}`` is the board's folder, and other
  ``${VARS}`` come from ``env`` (KiCad's own, such as ``${KICAD10_3DMODEL_DIR}``, which an install sets);
* ``unresolved_var``: a model path whose variable is not set, so it cannot be checked (fails, unless ``env`` names it);
* ``absolute_path``: a model given by an absolute path, which works on one machine only.

``registration(pads, boxes)`` checks a body against its footprint, without CadQuery:

* **seat**: the body sits on the board's top face (z = 0), not floating above it or sunk into it;
* **pins**: each ``pin<n>`` passes through pad n's hole, each ``peg`` through a non-plated hole, and nothing else
  passes through the board;
* **terminals**: each ``terminal<n>`` lies over pad n's copper (this is the pin-1 frame: a body turned or mirrored
  puts its terminal 1 on the wrong pad).

Both read the files as text (``cadagent.library.sexp``) and need neither KiCad nor CadQuery. They check what the
files say. They do not check that the vendor's part matches its datasheet, or that a model looks like the part.
"""
from __future__ import annotations

import fnmatch
import math
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from cadagent.library import sexp as S

VAR = re.compile(r'\$\{([^}]+)\}|\$\(([^)]+)\)')
TOL = 0.05


def _pads(fp: list) -> List[dict]:
    out = []
    for p in S.find(fp, 'pad'):
        kind, shape = str(p[2]), str(p[3])
        at = S.nums(S.first(p, 'at'), 3)
        size = S.nums(S.first(p, 'size'), 2)
        dr = S.first(p, 'drill')
        drill = None
        if dr is not None:
            vals = [float(x) for x in dr[1:] if not isinstance(x, list) and S._is_num(x)]
            drill = (vals[0], vals[1] if len(vals) > 1 else vals[0]) if vals else None
        out.append({'number': str(p[1]), 'kind': kind, 'shape': shape, 'at': (at[0], at[1]), 'rot': at[2],
                    'size': size, 'drill': drill})
    return out


def _models(fp: list) -> List[dict]:
    out = []
    for m in S.find(fp, 'model'):
        hide = S.first(m, 'hide')
        out.append({'path': str(m[1]), 'hidden': bool(hide and str(hide[-1]) == 'yes') or 'hide' in m[2:]})
    return out


def _footprint(fp: list, ref: Optional[str] = None) -> dict:
    """One footprint's reference, library id, pads, models and attributes. ``ref=''``: a library footprint, whose
    REF** placeholder is not a reference."""
    if ref is None:
        for p in S.find(fp, 'property'):
            if len(p) > 2 and p[1] == 'Reference':
                ref = str(p[2])
        for t in S.find(fp, 'fp_text'):
            if len(t) > 2 and str(t[1]) == 'reference':
                ref = str(t[2])
    attr = S.first(fp, 'attr')
    return {'ref': ref or '', 'lib_id': str(fp[1]), 'pads': _pads(fp), 'models': _models(fp),
            'attr': [str(x) for x in (attr or [])[1:]]}


def read(path) -> List[dict]:
    """The footprints in a ``.kicad_pcb``, a ``.kicad_mod`` or a ``.pretty`` folder."""
    path = Path(path)
    if path.is_dir():
        return [f for p in sorted(path.glob('*.kicad_mod')) for f in read(p)]
    tree = S.parse(path.read_text())
    if not isinstance(tree, list) or not tree:
        raise ValueError(f'{path.name} is not a KiCad file')
    if tree[0] in ('footprint', 'module'):
        return [_footprint(tree, ref='')]
    if tree[0] != 'kicad_pcb':
        raise ValueError(f'{path.name}: expected a kicad_pcb or footprint file, got ({tree[0]} ...)')
    return [_footprint(fp) for fp in S.find(tree, 'footprint') + S.find(tree, 'module')]


def expand(model: str, env: Dict[str, str]) -> Tuple[Optional[str], List[str]]:
    """``model`` with its ``${VAR}``s from ``env``; (None, the missing names) if any is not set."""
    missing: List[str] = []

    def sub(m):
        name = m.group(1) or m.group(2)
        if name in env:
            return env[name]
        missing.append(name)
        return m.group(0)
    out = VAR.sub(sub, model)
    return (None, missing) if missing else (out, [])


def _resolves(path: Path) -> bool:
    if path.is_file():
        return True
    # KiCad loads a .step in place of a .wrl it cannot find (and the other way), so the audit accepts the swap
    return any(path.with_suffix(s).is_file() for s in ('.step', '.stp', '.wrl') if s != path.suffix)


def _waived(fp: dict, waivers: Dict[str, str]) -> Optional[str]:
    for pattern, reason in waivers.items():
        if fnmatch.fnmatchcase(fp['ref'], pattern) or fnmatch.fnmatchcase(fp['lib_id'], pattern):
            return reason
    return None


def project_dir(path) -> Path:
    """The folder ``${KIPRJMOD}`` stands for: a board's folder, or the folder that holds a ``.pretty`` library."""
    path = Path(path).resolve()
    if path.is_dir():
        return path.parent if path.suffix == '.pretty' else path
    return path.parent.parent if path.parent.suffix == '.pretty' else path.parent


def model_audit(path, env: Optional[Dict[str, str]] = None, waivers: Optional[Dict[str, str]] = None,
                use_os_env: bool = True) -> dict:
    """Audit every footprint in ``path`` for a 3D model that resolves (the module docstring lists the findings).

    ``waivers`` maps a reference or library id pattern (``TP*``, ``*:TieSlot*``) to the reason it needs no model;
    an empty reason is refused. ``env`` adds variables to the process environment's (``use_os_env``); ``KIPRJMOD``
    is the board's folder. Returns ``{'pass', 'footprints', 'findings', 'waived', 'unused_waivers'}``."""
    path = Path(path)
    waivers = dict(waivers or {})
    bad = [k for k, v in waivers.items() if not isinstance(v, str) or not v.strip()]
    if bad:
        raise ValueError(f'a waiver needs a reason: {bad}')
    var = dict(os.environ) if use_os_env else {}
    var.update(env or {})
    var.setdefault('KIPRJMOD', str(project_dir(path)))
    fps = read(path)
    findings, waived, used = [], [], set()
    for fp in fps:
        who = f"{fp['ref']} ({fp['lib_id']})" if fp['ref'] else fp['lib_id']
        shown = [m for m in fp['models'] if not m['hidden']]
        if not shown:
            reason = _waived(fp, waivers)
            if reason:
                waived.append({'footprint': who, 'reason': reason})
                used.update(k for k in waivers if fnmatch.fnmatchcase(fp['ref'], k)
                            or fnmatch.fnmatchcase(fp['lib_id'], k))
            else:
                findings.append({'check': 'no_model', 'footprint': who,
                                 'detail': 'no 3D model: add one, or waive it with the reason it is not a part'})
        for m in shown:
            if os.path.isabs(m['path']) and not m['path'].startswith('$'):
                findings.append({'check': 'absolute_path', 'footprint': who, 'detail': m['path']})
            full, missing = expand(m['path'], var)
            if full is None:
                findings.append({'check': 'unresolved_var', 'footprint': who,
                                 'detail': f"{m['path']}: set {', '.join(missing)}"})
            elif not _resolves(Path(full)):
                findings.append({'check': 'missing_model', 'footprint': who, 'detail': m['path']})
    findings.sort(key=lambda f: (f['footprint'], f['check'], f['detail']))
    waived.sort(key=lambda w: w['footprint'])
    return {'pass': not findings, 'footprints': len(fps), 'with_model': sum(1 for f in fps if any(
        not m['hidden'] for m in f['models'])), 'findings': findings, 'waived': waived,
        'unused_waivers': sorted(set(waivers) - used)}


# ------------------------------------------------------------------------------------------------ registration

def _in_hole(pt: Tuple[float, float], pad: dict) -> bool:
    """Is ``pt`` (model frame) inside pad's drilled hole? An oval hole is a stadium along its long side."""
    cx, cy = pad['at'][0], -pad['at'][1]                   # the footprint's y is down, the model's is up
    w, h = pad['drill']
    if pad['rot']:
        a = math.radians(pad['rot'])
        dx, dy = pt[0] - cx, pt[1] - cy
        pt = (cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a))
    dx, dy = abs(pt[0] - cx), abs(pt[1] - cy)
    r = min(w, h) / 2
    half = max(w, h) / 2 - r                                # half the straight part of a stadium
    if w >= h:
        dx = max(0.0, dx - half)
    else:
        dy = max(0.0, dy - half)
    return dx * dx + dy * dy <= r * r + 1e-9


def _outline(b) -> List[Tuple[float, float]]:
    """Points on the ellipse inscribed in the xy box ``b``: a pin is taken as round or rounded (a blade's sharp
    corners are not checked), so a round pin that fits its hole passes and one that does not, fails."""
    (x0, y0), (x1, y1) = b
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in range(0, 360, 15)]


def _over_pad(box, pad: dict) -> bool:
    """Do the box's xy and the pad's copper rectangle overlap (model frame)?"""
    cx, cy = pad['at'][0], -pad['at'][1]
    w, h = pad['size'] if not (pad['rot'] and round(pad['rot']) % 180 == 90) else pad['size'][::-1]
    (x0, y0), (x1, y1) = box
    return x0 < cx + w / 2 and x1 > cx - w / 2 and y0 < cy + h / 2 and y1 > cy - h / 2


def registration(pads: Sequence[dict], boxes: Iterable[dict], board: float = 1.6, tol: float = TOL) -> List[dict]:
    """Check a body (``boxes``: each named child's box, with ``through``, the xy box of what lies inside the
    board's thickness, or None) against its footprint's ``pads`` (``read()``'s form). Returns the failures."""
    fails: List[dict] = []
    boxes = list(boxes)
    holes = [p for p in pads if p['drill']]
    above = [b for b in boxes if not re.fullmatch(r'pin\w+|peg\d*', b['name']) and b['min'][2] > -tol]
    if not above:
        fails.append({'check': 'seat', 'detail': 'no part of the body sits above the board'})
    elif abs(min(b['min'][2] for b in above)) > tol:
        fails.append({'check': 'seat', 'detail': f"the body's lowest face is at z = {min(b['min'][2] for b in above):.3f}"
                                                 ' mm, not on the board (z = 0)'})
    for b in boxes:
        name, thr = b['name'], b.get('through')
        if thr is None:
            if b['max'][2] > -board + tol and b['min'][2] < -tol:
                fails.append({'check': 'pins', 'detail': f'{name} sinks into the board without passing through it'})
            m = re.fullmatch(r'pin(\w+)', name)
            if m:
                fails.append({'check': 'pins', 'detail': f'{name} does not pass through the board'})
            mt = re.fullmatch(r'terminal(\w+)', name)
            if mt:
                mine = [p for p in pads if p['number'] == mt.group(1)]
                if not mine:
                    fails.append({'check': 'terminals', 'detail': f'{name}: the footprint has no pad {mt.group(1)}'})
                elif not any(_over_pad((b['min'][:2], b['max'][:2]), p) for p in mine):
                    fails.append({'check': 'terminals', 'detail': f'{name} is not over pad {mt.group(1)} (turned or '
                                                                  'mirrored?)'})
                others = [p for p in pads if p['number'] != mt.group(1) and p['kind'] == 'smd'
                          and _over_pad((b['min'][:2], b['max'][:2]), p) and max(p['size']) > 1.0]
                for p in others:
                    fails.append({'check': 'terminals', 'detail': f"{name} also lies over pad {p['number']}"})
            continue
        m = re.fullmatch(r'pin(\w+)', name)
        if m:
            cand = [p for p in holes if p['number'] == m.group(1) and p['kind'] == 'thru_hole']
            what = f"pad {m.group(1)}'s hole"
        elif re.fullmatch(r'peg\d*', name):
            cand = [p for p in holes if p['kind'] == 'np_thru_hole']
            what = 'a non-plated hole'
        else:
            fails.append({'check': 'pins', 'detail': f'{name} passes through the board outside any hole'})
            continue
        if not any(all(_in_hole(c, p) for c in _outline(thr)) for p in cand):
            fails.append({'check': 'pins', 'detail': f'{name} does not pass through {what}'})
    return fails
