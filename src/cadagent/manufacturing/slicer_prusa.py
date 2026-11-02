"""Real filament grams and print time from PrusaSlicer's command line, run as a separate program.

    from cadagent.manufacturing.slicer import slice_part
    r = slice_part('exports/vase.3mf', engine='prusa', printer='Original Prusa XL - 5T Input Shaper 0.4 nozzle',
                   process='0.20mm SPEED @XLIS 0.4', filament='Prusament PLA @XLIS', overrides={'perimeters': '3'})
    r['grams'], r['minutes']

Profiles come from PrusaSlicer's vendor bundles (``PrusaResearch.ini``: ``[printer:...]``, ``[print:...]`` and
``[filament:...]`` sections whose ``inherits`` names one or more ``;``-separated parents, later parents winning) and
from the user's own presets saved next to them (``<config>/printer/<name>.ini`` and so on). ``resolve_profile``
merges a profile's parents into one flat set of settings and returns hashes of the files it read. ``slice_part``
has PrusaSlicer resolve the three presets itself (``--save``, so a multi-tool printer gets each filament setting once
per extruder, as PrusaSlicer's window gives them, and a preset that does not fit the printer is refused), applies the
overrides, writes one ``config.ini`` and slices with ``prusa-slicer --loglevel 3 --export-gcode``.

PrusaSlicer reports a part that slices but will print badly only in its log, and exits 0: "Detected print stability
issues" (long bridging extrusions, floating bridge anchors, collapsing overhangs, low bed adhesion, loose
extrusions), or an error such as G-code paths of the wipe tower and a part conflicting. ``slice_part`` saves the log
next to the G-code (``slicer.log``) and returns its ``warnings``, ``errors`` and ``stability_issues``; ``ok`` is
true only with exit code 0, G-code written and no error or stability issue (``parse_log``).

The profiles are found in ``CADAGENT_PRUSA_PROFILES`` when set (a folder of ``*.ini`` bundles), else in the first of
``~/.config/PrusaSlicer/vendor``, the flatpak's ``~/.var/app/com.prusa3d.PrusaSlicer/config/PrusaSlicer/vendor``,
``/usr/share/PrusaSlicer/profiles`` and ``/usr/share/prusa-slicer/profiles`` that holds any. Bundles are the ones
PrusaSlicer last downloaded, so the same profile name can change between PrusaSlicer updates; the hashes recorded
with every slice say which bytes were used.

The numbers are slicer estimates for one copy of a part; they do not prove the part prints well.

PrusaSlicer is AGPL-3.0: it is only ever run as a separate process; nothing of it is imported or copied. The flatpak
cannot read /tmp, so its work folder must be under your home directory (the default is next to the model).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PRINTER = 'Original Prusa MK4S 0.4 nozzle'
PROCESS = '0.20mm SPEED @MK4S 0.4'
# The plain 'Prusament PLA' section is a generic parent; the MK4S variant carries that printer's tuning.
FILAMENTS = {'pla': 'Prusament PLA @MK4S', 'petg': 'Prusament PETG @MK4S'}

ENV = 'CADAGENT_PRUSA_PROFILES'
FLATPAK_ID = 'com.prusa3d.PrusaSlicer'
KINDS = ('printer', 'print', 'filament')
_IDS = {'printer': 'printer_settings_id', 'print': 'print_settings_id', 'filament': 'filament_settings_id'}
# Keys that steer PrusaSlicer's preset tree, not the slice; a flattened profile drops them.
_TREE_KEYS = ('inherits', 'compatible_printers', 'compatible_printers_condition', 'compatible_prints',
              'compatible_prints_condition', 'renamed_from')
_TEMPLATES = 'Templates.ini'


def _profile_roots() -> List[Path]:
    if os.environ.get(ENV):
        return [Path(os.environ[ENV]).expanduser()]
    home = Path.home()
    return [home / '.config/PrusaSlicer/vendor', home / f'.var/app/{FLATPAK_ID}/config/PrusaSlicer/vendor',
            Path('/usr/share/PrusaSlicer/profiles'), Path('/usr/share/prusa-slicer/profiles')]


def profile_root() -> Path:
    """The first folder holding PrusaSlicer ``*.ini`` vendor bundles."""
    roots = _profile_roots()
    for r in roots:
        if r.is_dir() and any(r.glob('*.ini')):
            return r
    raise FileNotFoundError(f'PrusaSlicer profiles not found in {", ".join(map(str, roots))}; install PrusaSlicer and '
                            f'run it once, or set {ENV} to a folder of vendor bundles')


def _parse(text: str, where: Path, sections: bool = True) -> Dict[str, Dict[str, str]]:
    """``key = value`` lines, under ``[section]`` headers (bundles) or none (a user preset: one section, '')."""
    out: Dict[str, Dict[str, str]] = {}
    current = out.setdefault('', {}) if not sections else None
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped[0] in '#;':
            continue
        if sections and stripped.startswith('[') and stripped.endswith(']'):
            name = stripped[1:-1]
            if name in out:
                raise ValueError(f'Duplicate section [{name}] in {where}')
            current = out[name] = {}
            continue
        key, eq, value = line.partition('=')
        if not eq or current is None:
            raise ValueError(f'{where}:{n}: not a "key = value" line: {line[:80]!r}')
        current[key.strip()] = value.strip()
    return out


def read_bundle(path: Path) -> Dict[str, Dict[str, str]]:
    """A vendor bundle's sections, keyed ``"<kind>:<name>"`` (``vendor`` and other sections kept as they are)."""
    return _parse(Path(path).read_text(encoding='utf-8'), Path(path))


def _label(name, kind: str) -> str:
    if (not isinstance(name, str) or not name.strip() or '/' in name or '\\' in name
            or name in ('.', '..')):
        raise ValueError(f'Invalid PrusaSlicer {kind} profile name: {name!r}')
    return name


def resolve_profile(kind: str, name: str) -> dict:
    """Return ``settings`` (flat ``key -> value`` strings) and ``files`` (path relative to the profile root's parent
    → SHA-256) for a profile. A slice uses it for the files it depends on, the printer's model and a clear error for
    a misspelt name; the settings sliced with are PrusaSlicer's own (``resolved_by_prusaslicer``), which take a user
    preset as saved, not merged with its parents.

    A user preset (``<config>/<kind>/<name>.ini`` next to ``vendor/``) is looked up first, then the vendor bundles;
    ``Templates.ini`` only when no other bundle has the name, and a name in two other bundles is ambiguous. Parents
    are resolved in the bundle that defines the profile, left to right, later parents winning, the profile's own keys
    last. Missing profiles raise KeyError; cycles, duplicates and ambiguity raise ValueError."""
    if kind not in KINDS:
        raise ValueError(f'Unknown PrusaSlicer profile kind: {kind!r} (use {", ".join(KINDS)})')
    root = profile_root()
    base = root.parent
    bundles: Dict[Path, Tuple[Dict[str, Dict[str, str]], str]] = {}
    for f in sorted(root.glob('*.ini')):
        raw = f.read_bytes()
        bundles[f] = (_parse(raw.decode('utf-8'), f), hashlib.sha256(raw).hexdigest())
    files: Dict[str, str] = {}
    active: List[str] = []

    def system(label: str) -> Tuple[Path, Dict[str, str]]:
        key = f'{kind}:{label}'
        found = [f for f in bundles if f.name != _TEMPLATES and key in bundles[f][0]]
        if len(found) > 1:
            raise ValueError(f'Ambiguous PrusaSlicer {kind} profile {label!r}: in {", ".join(f.name for f in found)}')
        if not found and root / _TEMPLATES in bundles and key in bundles[root / _TEMPLATES][0]:
            found = [root / _TEMPLATES]
        if not found:
            raise KeyError(f'PrusaSlicer {kind} profile {label!r} not found under {root}')
        return found[0], bundles[found[0]][0][key]

    def merged(label: str, bundle: Optional[Path]) -> Dict[str, str]:
        """``bundle`` None: look the name up (user presets, then bundles); else resolve inside that bundle."""
        tag = f'{bundle.name if bundle else ""}:{label}'
        if tag in active:
            raise ValueError(f'Cyclic PrusaSlicer {kind} inheritance: {" -> ".join(active + [tag])}')
        user = base / kind / f'{label}.ini'
        if bundle is None and root.name == 'vendor' and user.is_file():
            raw = user.read_bytes()
            files[user.relative_to(base).as_posix()] = hashlib.sha256(raw).hexdigest()
            section, home = _parse(raw.decode('utf-8'), user, sections=False)[''], None
        else:
            if bundle is not None:
                key = f'{kind}:{label}'
                if key not in bundles[bundle][0]:
                    raise KeyError(f'PrusaSlicer {kind} profile {label!r} not found in {bundle.name}')
                section, home = bundles[bundle][0][key], bundle
            else:
                home, section = system(label)
            files[home.relative_to(base).as_posix()] = bundles[home][1]
        active.append(tag)
        out: Dict[str, str] = {}
        for parent in (p.strip() for p in section.get('inherits', '').split(';')):
            if parent:
                out.update(merged(parent, home))   # user presets inherit from the bundles (home None)
        out.update(section)
        active.pop()
        return out

    settings = merged(_label(name, kind), None)
    for k in _TREE_KEYS:
        settings.pop(k, None)
    settings[_IDS[kind]] = name
    return {'settings': settings, 'files': dict(sorted(files.items()))}


_TIME = re.compile(r'(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?')


def _sum(value: str) -> float:
    return sum(float(v) for v in value.split(',') if v.strip())


def parse_gcode_stats(text: str) -> Dict[str, Optional[float]]:
    """Grams, seconds and metres of filament from a G-code footer (summed over extruders); None where absent."""
    out: Dict[str, Optional[float]] = {'grams': None, 'seconds': None, 'filament_m': None}
    for line in text.splitlines():
        if not line.startswith(';'):
            continue
        key, _, value = line[1:].partition('=')
        key, value = key.strip(), value.strip()
        if key == 'filament used [g]':
            out['grams'] = round(_sum(value), 2)
        elif key == 'filament used [mm]':
            out['filament_m'] = round(_sum(value) / 1000, 3)
        elif key == 'estimated printing time (normal mode)':
            m = _TIME.fullmatch(value)
            if m and any(m.groups()):
                d, h, mi, s = (int(g or 0) for g in m.groups())
                out['seconds'] = float(((d * 24 + h) * 60 + mi) * 60 + s)
    return out


# PrusaSlicer's own log lines that say nothing about the print being sliced: a multi-tool printer makes the support-spot
# search note on every slice that it reads one material, and Arachne notes when it re-runs a Voronoi diagram with
# rotated input. They are counted (``benign_log_lines``), not listed.
BENIGN = re.compile(r'SupportSpotsGenerator does not currently handle different materials|Voronoi')
# "[2026-11-01 15:31:12.011855] [0x00007759b5089ec0] [warning] message", as --loglevel 3 writes to stderr
_LOGGED = re.compile(r'^\[[^\]]*\]\s+\[0x[0-9a-fA-F]+\]\s+\[(\w+)\]\s*(.*)$')
# "print warning: message", "error: message", as PrusaSlicer's command line prints a print's own warnings
_SAID = re.compile(r'^(?:[a-z]+ )?(warning|error):\s*(.*)$', re.I)
_PROGRESS = re.compile(r'^\d+ => ')
_STABILITY = 'Detected print stability issues'
# what ends the stability block: PrusaSlicer's advice, its next progress line, or another log line
_BLOCK_END = re.compile(r'^(?:Consider |Also consider |\d+ => |\[)')


def _stability_block(lines: List[str]) -> List[str]:
    """The categories in the block after "Detected print stability issues:": a blank line, then for each object its
    name on one line and its issues on the next, comma-separated."""
    said = []
    for ln in lines:
        ln = ln.strip()
        if _BLOCK_END.match(ln) or _SAID.match(ln):
            break
        if ln:
            said.append(ln)
    named = said[1::2] if len(said) > 1 else said     # (object, issues) pairs; one line alone is the issues
    out: List[str] = []
    for line in named:
        for cat in line.split(','):
            if cat.strip() and cat.strip() not in out:
                out.append(cat.strip())
    return out


def parse_log(text: str) -> dict:
    """What PrusaSlicer's log (stdout and stderr of a ``--loglevel 3`` slice) says about the print: ``warnings`` and
    ``errors`` (the messages at those levels, each once, in order; fatal counts as error), ``stability_issues`` (the
    categories named after "Detected print stability issues:", e.g. ``Long bridging extrusions``) and
    ``benign_log_lines`` (how many warning lines ``BENIGN`` matched, which are not listed)."""
    lines = (text or '').splitlines()
    out = {'warnings': [], 'errors': [], 'stability_issues': [], 'benign_log_lines': 0}
    for i, raw in enumerate(lines):
        ln = raw.strip()
        m = _LOGGED.match(ln) or _SAID.match(ln)
        if not m:
            continue
        level, msg = m.group(1).lower(), m.group(2).strip()
        if level not in ('warning', 'error', 'fatal'):
            continue
        if BENIGN.search(msg):
            out['benign_log_lines'] += 1
            continue
        kept = out['warnings'] if level == 'warning' else out['errors']
        if msg not in kept:
            kept.append(msg)
        if _STABILITY in msg:
            for cat in _stability_block(lines[i + 1:]):
                if cat not in out['stability_issues']:
                    out['stability_issues'].append(cat)
    return out


def _reason(stdout: str, stderr: str) -> Optional[str]:
    """PrusaSlicer's last word on a failed slice: the last line it printed that is not an info, debug or progress line
    (stderr first, then stdout)."""
    for text in (stderr, stdout):
        said = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
        said = [ln for ln in said if not _PROGRESS.match(ln) and not (
            _LOGGED.match(ln) and _LOGGED.match(ln).group(1).lower() not in ('warning', 'error', 'fatal'))]
        if said:
            return said[-1]
    return None


def executable() -> Optional[List[str]]:
    """The command that runs PrusaSlicer: a ``prusa-slicer`` on PATH, else the flatpak; None if neither."""
    for name in ('prusa-slicer', 'PrusaSlicer', 'prusa-slicer.AppImage', 'PrusaSlicer.AppImage'):
        p = shutil.which(name)
        if p:
            return [p]
    if shutil.which('flatpak'):
        try:
            ok = subprocess.run(['flatpak', 'info', FLATPAK_ID], capture_output=True, text=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if ok:
            return ['flatpak', 'run', '--command=prusa-slicer', FLATPAK_ID]
    return None


def _installed(printer: Optional[str]) -> str:
    """The ``[vendor:<bundle>]`` section that installs ``printer``'s model and nozzle variant, as PrusaSlicer's
    configuration wizard writes it (``model:XL5IS = 0.4``). PrusaSlicer hides the system printer profiles of models
    that are not installed and falls back to another printer; '' when the printer names no model."""
    if not printer:
        return ''
    try:
        r = resolve_profile('printer', printer)
    except (KeyError, ValueError, OSError):
        return ''
    model, variant = r['settings'].get('printer_model'), r['settings'].get('printer_variant')
    bundles = [Path(f).stem for f in r['files'] if f.split('/')[0] not in KINDS and Path(f).name != _TEMPLATES]
    if not model or not bundles:
        return ''
    return f'[vendor:{bundles[0]}]\nmodel:{model} = {variant or ""}\n\n'


def private_datadir(work: Path, filament: str, printer: Optional[str] = None) -> Path:
    """A private copy of the profile folder (``work/prusaslicer-datadir``): the vendor bundles, the user's own presets,
    and a ``PrusaSlicer.ini`` with ``printer``'s model and ``filament`` the ones installed. PrusaSlicer is pointed at
    it with ``--datadir``, so the user's own PrusaSlicer configuration is never read for state or written to."""
    data_dir = Path(work) / 'prusaslicer-datadir'
    root = profile_root()
    if data_dir.exists():
        shutil.rmtree(data_dir)
    (data_dir / 'vendor').mkdir(parents=True)
    for f in root.glob('*.ini'):
        shutil.copyfile(f, data_dir / 'vendor' / f.name)
    for kind in KINDS:
        (data_dir / kind).mkdir()
        if root.name == 'vendor':
            for f in (root.parent / kind).glob('*.ini'):
                shutil.copyfile(f, data_dir / kind / f.name)
    (data_dir / 'PrusaSlicer.ini').write_text(f'{_installed(printer)}[filaments]\n{filament} = 1\n', encoding='utf-8')
    return data_dir


def resolved_by_prusaslicer(exe: List[str], printer: str, process: str, filament: str, work: Path,
                            timeout: float = 900) -> Dict[str, str]:
    """The full configuration PrusaSlicer itself builds from the three named presets (``--save``), as its window
    does: every option, with each filament setting given once per extruder (``filament_settings_id =
    "Prusament PLA @XLIS";...`` five times on a five-tool XL). PrusaSlicer also refuses a print or filament preset
    that does not fit the printer. A ValueError with PrusaSlicer's reason when it writes nothing, or resolves other
    presets than the ones named."""
    out = Path(work) / 'prusaslicer-resolved.ini'
    data_dir = private_datadir(work, filament, printer)
    if out.exists():
        out.unlink()
    try:
        p = subprocess.run(exe + ['--datadir', str(data_dir), '--printer-profile', printer, '--print-profile', process,
                                  '--material-profile', filament, '--save', str(out)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ValueError(f'PrusaSlicer did not finish loading the presets in {timeout:g} s') from None
    if not out.is_file():
        said = [ln.strip() for ln in (p.stderr or p.stdout or '').splitlines() if ln.strip()]
        raise ValueError(f'PrusaSlicer could not load printer {printer!r}, print {process!r} and filament '
                         f'{filament!r}: {said[-1] if said else f"exit code {p.returncode}"}')
    cfg = _parse(out.read_text(encoding='utf-8'), out, sections=False)['']
    ids = [s.strip().strip('"') for s in cfg.get('filament_settings_id', '').split(';')]
    got = (cfg.get('printer_settings_id'), cfg.get('print_settings_id'), sorted(set(ids)))
    if got != (printer, process, [filament]):
        raise ValueError(f'PrusaSlicer loaded printer {got[0]!r}, print {got[1]!r} and filament(s) '
                         f'{", ".join(map(repr, got[2]))}, not the presets named')
    return cfg


def _ini_value(v) -> str:
    if isinstance(v, bool):
        return '1' if v else '0'
    if v is None or isinstance(v, (list, tuple, dict)):
        raise ValueError(f'cad.slicer.overrides values are single values, not {v!r}; one value applies to every '
                         'extruder, or give PrusaSlicer\'s own text (e.g. "#FF0000;#00FF00", "215,220")')
    return str(v)


def build_config(base: Dict[str, str], overrides: Optional[dict] = None) -> Dict[str, str]:
    """``base`` (PrusaSlicer's own resolution of the presets, ``resolved_by_prusaslicer``) with ``overrides``. An
    override key the configuration lacks is a ValueError: a Bambu Studio key such as ``wall_loops`` would otherwise be
    dropped without a word. G-code is always written as text (``binary_gcode = 0``): grams and time are read from it."""
    unknown = sorted(k for k in (overrides or {}) if k not in base)
    if unknown:
        raise ValueError(f'Unknown PrusaSlicer setting(s) {", ".join(map(repr, unknown))} in cad.slicer.overrides '
                         '(overrides use PrusaSlicer names, e.g. perimeters, fill_density, spiral_vase)')
    cfg = dict(base)
    cfg.update({k: _ini_value(v) for k, v in (overrides or {}).items()})
    cfg['binary_gcode'] = '0'
    return cfg


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slice_part(model, workdir, printer: str, process: str, filament: str, overrides: Optional[dict] = None,
               timeout: float = 900) -> dict:
    """Slice one STL or 3MF (already in print orientation) in ``workdir`` and return grams, minutes and the settings
    used. ``cadagent.manufacturing.slicer.slice_part(..., engine='prusa')`` is the entry point that also guards the work folder."""
    exe = executable()
    if not exe:
        raise RuntimeError('PrusaSlicer is not installed (prusa-slicer on PATH, or flatpak install flathub '
                           f'{FLATPAK_ID}); cannot measure filament')
    model = Path(model).resolve()
    work = Path(workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # the files read, and a clear error for a misspelt name before PrusaSlicer runs
    sources = {kind: resolve_profile(kind, name)['files']
               for kind, name in (('printer', printer), ('print', process), ('filament', filament))}
    cfg = build_config(resolved_by_prusaslicer(exe, printer, process, filament, work, timeout), overrides)
    config = work / 'config.ini'
    config.write_text(''.join(f'{k} = {v}\n' for k, v in sorted(cfg.items())), encoding='utf-8')
    settings_hash = _sha(config)
    out = work / 'out'
    out.mkdir(exist_ok=True)
    gcode = out / 'sliced.gcode'
    if gcode.exists():
        gcode.unlink()
    cmd = exe + ['--loglevel', '3', '--export-gcode', '--load', str(config), '--output', str(gcode), str(model)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    log_text = (p.stdout or '') + '\n' + (p.stderr or '')
    log = out / 'slicer.log'
    log.write_text(log_text, encoding='utf-8')
    said = parse_log(log_text)
    stats = parse_gcode_stats(gcode.read_text(encoding='utf-8', errors='replace')) if gcode.exists() else \
        {'grams': None, 'seconds': None, 'filament_m': None}
    r = dict(stats, model=str(model), printer=printer, process=process, filament=filament,
             overrides=dict(overrides or {}), exit_code=p.returncode, profile_sources=sources,
             settings_sha256={'config': settings_hash}, slicer=Path(exe[-1] if exe[0] != 'flatpak' else 'prusa-slicer').name,
             minutes=round(stats['seconds'] / 60, 1) if stats['seconds'] else None, error=None, log=str(log), **said)
    if not r['grams']:
        # PrusaSlicer prints its reason last, on stderr or stdout, and exits 0 for some failures (2.9.4: "All
        # objects are outside of the print volume.")
        reason = said['errors'][-1] if said['errors'] else _reason(p.stdout, p.stderr)
        r['error'] = ('no "filament used [g]" in the G-code (is filament_density 0?)' if gcode.exists() else
                      reason or 'no G-code produced')
        r['log_tail'] = log_text[-2000:]
    # a slice that exits 0 with G-code can still say the part will print badly
    r['ok'] = (p.returncode == 0 and gcode.exists() and r['error'] is None and not said['errors']
               and not said['stability_issues'])
    return r
