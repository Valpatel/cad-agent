"""Real filament grams and print time from a slicer (Bambu Studio's command line, run as a separate program).

    from cadagent.manufacturing.slicer import slice_part
    r = slice_part('exports/base.3mf', workdir='build/slicer', overrides={'wall_loops': '3', 'sparse_infill_density': '15%'})
    r['grams'], r['minutes']

The slicer's own system profiles inherit from parent profiles; passed to the command line as they are, they leave
values such as the filament density unset (the slicer then reports 0 g). ``flatten`` resolves parents and ordered
included templates into one file per profile before slicing. Profiles are named as the slicer names them
(printer, process, filament). ``resolve_profile`` also returns hashes of the consumed profile files.

Bambu Studio is AGPL-3.0: it is only ever run as a separate process. The snap package cannot read hidden folders
or /tmp, so the work folder must be a normal folder under your home directory (the default is next to the model).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

PRINTER = 'Bambu Lab P1S 0.4 nozzle'
_MARK = '.cadagent-slicer'
PROCESS = '0.20mm Standard @BBL X1C'          # lists the P1S 0.4 nozzle among its compatible printers
FILAMENTS = {'pla': 'Bambu PLA Basic @BBL P1S 0.4 nozzle', 'petg': 'Bambu PETG HF @BBL P1S 0.4 nozzle'}

_PROFILE_ROOTS = [
    Path('/snap/bambu-studio/current/opt/bambu-studio/resources/profiles/BBL'),
    Path('/opt/bambu-studio/resources/profiles/BBL'),
    Path.home() / '.local/share/BambuStudio/resources/profiles/BBL',
]


def executable() -> Optional[str]:
    for name in ('bambu-studio', 'BambuStudio', 'bambu-studio.AppImage'):
        p = shutil.which(name)
        if p:
            return p
    return None


def profile_root() -> Path:
    for r in _PROFILE_ROOTS:
        if (r / 'machine').is_dir():
            return r
    raise FileNotFoundError('Bambu Studio system profiles not found; install Bambu Studio (snap install bambu-studio)')


def _profile_name(value, kind: str) -> str:
    # Names are lookup labels, never paths: real Bambu labels include PA/PET.
    if (not isinstance(value, str) or not value.strip() or '\\' in value
            or value.startswith('/') or any(p in ('.', '..') for p in value.split('/'))):
        raise ValueError(f'Invalid {kind} profile reference: {value!r}')
    return value


def _index(kind: str, root: Path) -> dict:
    """Capture each JSON once; resolution and dependency hashes use those same bytes."""
    out = {}
    for f in sorted((root / kind).glob('*.json')):
        if not f.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Profile path escapes root: {f}')
        try:
            raw = f.read_bytes()
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f'Malformed {kind} profile JSON: {f}') from None
        if not isinstance(data, dict):
            raise ValueError(f'{kind} profile JSON must be an object: {f}')
        if 'name' not in data:
            # Bambu also ships nameless lookup maps in the profile folders.
            # A named profile cannot be silently omitted from the index.
            continue
        n = _profile_name(data['name'], kind)
        if n in out:
            raise ValueError(f'Duplicate {kind} profile {n!r}: {out[n][0]} and {f}')
        out[n] = (f, data, hashlib.sha256(raw).hexdigest())
    return out


def resolve_profile(kind: str, name: str) -> dict:
    """Return ``settings`` and ``files`` (root-relative path → SHA-256) for a system profile.

    Merge parent → includes in list order → explicit keys, recursively. Include
    may be one name or a list. Missing dependencies raise KeyError; malformed,
    ambiguous, escaping or cyclic dependencies raise ValueError. Files are read
    once per call. The identities describe that capture, not ongoing filesystem
    stability, executable G-code validation or physical print qualification.
    """
    ids = {'machine': 'printer_settings_id', 'process': 'print_settings_id', 'filament': 'filament_settings_id'}
    if kind not in ids:
        raise ValueError(f'Unknown profile kind: {kind!r}')
    root = profile_root()
    idx = _index(kind, root)
    active, cache, files = [], {}, {}

    def resolve(current):
        current = _profile_name(current, kind)
        if current in active:
            raise ValueError(f'Cyclic {kind} inheritance/include: {" -> ".join(active + [current])}')
        if current not in idx:
            raise KeyError(f'{kind} profile {current!r} not found under {root / kind}')
        if current in cache:
            return dict(cache[current])
        active.append(current)
        path, data, sha = idx[current]
        files[path.relative_to(root).as_posix()] = sha
        parent = data.get('inherits', '')
        if not isinstance(parent, str):
            raise ValueError(f'Invalid {kind} parent in {current!r}: {parent!r}')
        settings = resolve(parent) if parent else {}
        included = data.get('include', [])
        if isinstance(included, str):
            included = [included]
        if not isinstance(included, list):
            raise ValueError(f'Invalid {kind} include list in {current!r}: {included!r}')
        for reference in included:
            settings.update(resolve(reference))
        settings.update({k: v for k, v in data.items() if k not in ('inherits', 'include')})
        active.pop()
        cache[current] = dict(settings)
        return settings

    out = resolve(name)
    out['name'] = name
    out['from'] = 'system'          # 'User' presets fail the CLI's printer compatibility check
    # the compatibility check matches the process's compatible_printers against the printer's settings id
    out[ids[kind]] = [name] if kind == 'filament' else name
    return {'settings': out, 'files': files}


def flatten(kind: str, name: str) -> dict:
    """A system profile with parent and ordered includes merged before explicit child keys."""
    return resolve_profile(kind, name)['settings']


def _read_result(out: Path) -> dict:
    r = {}
    rj = out / 'result.json'
    if rj.exists():
        d = json.loads(rj.read_text())
        plates = d.get('sliced_plates') or []
        g = sum(f.get('total_used_g', 0) for p in plates for f in p.get('filaments', []))
        t = sum(p.get('total_predication', 0) for p in plates)
        r.update(grams=round(float(g), 2), seconds=float(t), return_code=d.get('return_code'), error=d.get('error_string') or None)
    for z in out.glob('*.3mf'):
        try:
            with zipfile.ZipFile(z) as zf:
                info = zf.read('Metadata/slice_info.config').decode()
        except (KeyError, zipfile.BadZipFile):
            continue
        m = re.search(r'used_m="([\d.]+)"', info)
        if m:
            r['filament_m'] = float(m.group(1))
        if 'grams' not in r:
            m = re.search(r'used_g="([\d.]+)"', info)
            if m:
                r['grams'] = float(m.group(1))
    return r


def _prepare_workdir(model: Path, workdir) -> Path:
    """A fresh work folder for one slice: only ever clears a folder a slice wrote (or an empty one)."""
    work = Path(workdir).resolve() if workdir else model.parent / 'slicer' / model.stem
    if work.exists():
        ours = (work / _MARK).exists() or (work / 'result-summary.json').exists()   # the older marker too
        if not ours and any(work.iterdir()):
            raise FileExistsError(f'{work} exists and is not a slicer work folder; choose an empty or new folder')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / _MARK).write_text('cadagent.manufacturing.slicer work folder: safe to delete\n')   # first, so a crashed slice can be redone
    return work


def slice_part(model, workdir=None, printer: Optional[str] = None, process: Optional[str] = None, filament: str = 'pla',
               overrides: Optional[dict] = None, timeout: float = 900, engine: str = 'bambu') -> dict:
    """Slice one STL or 3MF (already in print orientation) and return grams, minutes and the settings used.

    ``engine`` is ``bambu`` (Bambu Studio) or ``prusa`` (PrusaSlicer); printer, process and filament default to that
    engine's, and ``filament`` may be ``pla`` or ``petg``. Overrides use the engine's own setting names."""
    if engine not in ENGINES:
        raise ValueError(f'Unknown cad.slicer.engine {engine!r}; use one of {", ".join(ENGINES)}')
    d_printer, d_process, filaments = _defaults(engine)
    printer, process = printer or d_printer, process or d_process
    if engine == 'prusa':
        from cadagent.manufacturing import slicer_prusa
        model = Path(model).resolve()
        work = _prepare_workdir(model, workdir)
        r = slicer_prusa.slice_part(model, work, printer, process, filaments.get(filament, filament), overrides,
                                    timeout=timeout)
        (work / 'result-summary.json').write_text(json.dumps(r, indent=2) + '\n')
        return r
    exe = executable()
    if not exe:
        raise RuntimeError('Bambu Studio is not installed (snap install bambu-studio); cannot measure filament')
    model = Path(model).resolve()
    work = _prepare_workdir(model, workdir)
    fil = FILAMENTS.get(filament, filament)
    profiles = {kind: resolve_profile(kind, name)
                for kind, name in (('machine', printer), ('process', process), ('filament', fil))}
    mach, proc, fl = (profiles[kind]['settings'] for kind in ('machine', 'process', 'filament'))
    for k, v in (overrides or {}).items():
        proc[k] = v if isinstance(v, list) or k not in proc or not isinstance(proc[k], list) else [str(v)] * len(proc[k])
    paths = {}
    for key, d in (('machine', mach), ('process', proc), ('filament', fl)):
        paths[key] = work / f'{key}.json'
        paths[key].write_text(json.dumps(d, indent=1))
    settings_hashes = {kind: _sha(path) for kind, path in paths.items()}
    out = work / 'out'
    out.mkdir()
    cmd = [exe, '--slice', '0', '--arrange', '1', '--orient', '0',
           '--load-settings', f"{paths['machine']};{paths['process']}", '--load-filaments', str(paths['filament']),
           '--outputdir', str(out), '--export-3mf', 'sliced.3mf', str(model)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if any(_sha(path) != settings_hashes[kind] for kind, path in paths.items()):
        raise ValueError('Resolved slicer settings changed during slicing')
    r = _read_result(out)
    r.update(model=str(model), printer=printer, process=process, filament=fil,
             overrides=dict(overrides or {}), exit_code=p.returncode,
             profile_sources={kind: p['files'] for kind, p in profiles.items()},
             settings_sha256=settings_hashes,
             slicer=Path(exe).name, minutes=round(r.get('seconds', 0) / 60, 1) if r.get('seconds') else None)
    if not r.get('grams'):
        r['log_tail'] = (p.stdout + p.stderr)[-2000:]
    (work / 'result-summary.json').write_text(json.dumps(r, indent=2) + '\n')
    return r


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


_CUBE_STL = (b"solid cube\n" + b"".join(
    b"facet normal 0 0 0\nouter loop\n" + b"".join(b"vertex %d %d %d\n" % v for v in tri) + b"endloop\nendfacet\n"
    for tri in (((0, 0, 0), (10, 10, 0), (10, 0, 0)), ((0, 0, 0), (0, 10, 0), (10, 10, 0)),
                ((0, 0, 10), (10, 0, 10), (10, 10, 10)), ((0, 0, 10), (10, 10, 10), (0, 10, 10)),
                ((0, 0, 0), (10, 0, 0), (10, 0, 10)), ((0, 0, 0), (10, 0, 10), (0, 0, 10)),
                ((0, 10, 0), (10, 10, 10), (10, 10, 0)), ((0, 10, 0), (0, 10, 10), (10, 10, 10)),
                ((0, 0, 0), (0, 0, 10), (0, 10, 10)), ((0, 0, 0), (0, 10, 10), (0, 10, 0)),
                ((10, 0, 0), (10, 10, 0), (10, 10, 10)), ((10, 0, 0), (10, 10, 10), (10, 0, 10))))
    + b"endsolid cube\n")


def default_bed_type(printer_model: str) -> Optional[str]:
    """The plate surface a printer model ships with (``default_bed_type`` in its machine model profile, e.g. the
    Textured PEI Plate for the Bambu Lab P1S); None when the profiles do not say."""
    try:
        found = _index('machine', profile_root()).get(printer_model)
    except (OSError, ValueError, RuntimeError):
        return None
    value = found[1].get('default_bed_type') if found else None
    return str(value) if value else None


def project_settings(workdir, printer: str = PRINTER, process: str = PROCESS, filaments=('pla',),
                     overrides: Optional[dict] = None, colours=(), timeout: float = 300) -> bytes:
    """Bambu Studio's own project configuration for these presets: the ``Metadata/project_settings.config`` it writes
    into a project 3MF (every printer, process and filament setting, with ``overrides`` applied to the process as
    ``slice_part`` applies them). A project 3MF needs it for Bambu Studio to keep its plates
    (``cadagent.manufacturing.plates``). Made by running the command line once on a 10 mm cube in ``workdir``, which
    must be a normal folder under your home directory (the snap package's limit) and is cleared first if this
    function wrote it. The bytes are the same for the same presets and Bambu Studio version.

    With more than one filament, Bambu Studio's command line writes the per-project lists for one: one colour
    (``filament_colour``, which is how Bambu Studio counts the filaments when it loads the file), one filament map
    entry, and a 4 x 4 purge matrix (``flush_volumes_matrix``; slicing stops unless it holds filaments² values per
    nozzle). Those three are sized to the filaments: the colours from ``colours`` (else Bambu's green), the map to
    the one nozzle, and the matrix with no purge on its diagonal and the command line's own purge volume elsewhere.
    Checked by slicing a two-filament project with the command line (each plate with its own filament).

    The plate surface (``curr_bed_type``) is the printer's own default (``default_bed_type``), as Bambu Studio's
    window sets it for a new project; its command line writes the Cool Plate whatever the printer."""
    exe = executable()
    if not exe:
        raise RuntimeError('Bambu Studio is not installed (snap install bambu-studio); no project settings')
    filaments = [FILAMENTS.get(f, f) for f in filaments] or [FILAMENTS['pla']]
    work = Path(workdir).resolve()
    if work.exists():
        if not (work / _MARK).exists() and any(work.iterdir()):
            raise FileExistsError(f'{work} exists and is not a slicer work folder; choose an empty or new folder')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / _MARK).write_text('cadagent.manufacturing.slicer work folder: safe to delete\n')
    mach, proc = flatten('machine', printer), flatten('process', process)
    for k, v in (overrides or {}).items():
        proc[k] = v if isinstance(v, list) or k not in proc or not isinstance(proc[k], list) else [str(v)] * len(proc[k])
    (work / 'machine.json').write_text(json.dumps(mach, indent=1))
    (work / 'process.json').write_text(json.dumps(proc, indent=1))
    names = []
    for i, f in enumerate(filaments):
        names.append(str(work / f'filament{i + 1}.json'))
        Path(names[-1]).write_text(json.dumps(flatten('filament', f), indent=1))
    (work / 'cube.stl').write_bytes(_CUBE_STL)
    out = work / 'out'
    out.mkdir()
    cmd = [exe, '--load-settings', f"{work / 'machine.json'};{work / 'process.json'}", '--load-filaments', ';'.join(names),
           '--outputdir', str(out), '--export-3mf', 'project.3mf', str(work / 'cube.stl')]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        with zipfile.ZipFile(out / 'project.3mf') as z:
            raw = z.read('Metadata/project_settings.config')
    except (OSError, KeyError, zipfile.BadZipFile):
        raise RuntimeError(f'Bambu Studio wrote no project settings (exit {p.returncode}): '
                           f'{(p.stdout + p.stderr)[-500:]}') from None
    n = len(filaments)
    data = json.loads(raw)
    if len(data.get('filament_settings_id') or []) != n:
        raise RuntimeError(f"Bambu Studio's project settings list {data.get('filament_settings_id')}, not the "
                           f"{n} filaments asked for")
    plate = default_bed_type(str(data.get('printer_model') or ''))
    if plate:
        data['curr_bed_type'] = plate
    if n > 1:
        colours = [str(c) for c in colours][:n]
        data['filament_colour'] = colours + ['#00AE42'] * (n - len(colours))
        data['filament_map'] = [str((data.get('filament_map') or ['1'])[0])] * n
        heads = max(1, len(data.get('flush_multiplier') or ['1']))
        matrix = data.get('flush_volumes_matrix') or ['0', '280']
        purge = str(matrix[1] if len(matrix) > 1 else '280')
        data['flush_volumes_matrix'] = ['0' if i == j else purge for _ in range(heads) for i in range(n) for j in range(n)]
    return (json.dumps(data, indent=4, sort_keys=True) + '\n').encode()


ENGINES = ('bambu', 'prusa')
ENGINE_NAMES = {'bambu': 'Bambu Studio', 'prusa': 'PrusaSlicer'}
_INSTALL = {'bambu': 'snap install bambu-studio',
            'prusa': 'prusa-slicer on PATH or flatpak com.prusa3d.PrusaSlicer'}


def _defaults(engine: str):
    """(printer, process, filament aliases) used when ``cad.slicer`` names none."""
    if engine == 'prusa':
        from cadagent.manufacturing import slicer_prusa
        return slicer_prusa.PRINTER, slicer_prusa.PROCESS, slicer_prusa.FILAMENTS
    return PRINTER, PROCESS, FILAMENTS


def engine_of(project) -> str:
    """``cad.slicer.engine``: ``bambu`` (the default) or ``prusa``."""
    engine = (getattr(project, 'slicer', None) or {}).get('engine', 'bambu')
    if engine not in ENGINES:
        raise ValueError(f'Unknown cad.slicer.engine {engine!r}; use one of {", ".join(ENGINES)}')
    return engine


def _settings(project) -> dict:
    cfg = dict(project.slicer or {})
    engine = engine_of(project)
    printer, process, filaments = _defaults(engine)
    fil = cfg.get('filament', 'pla')
    out = {'printer': cfg.get('printer', printer), 'process': cfg.get('process', process),
           'filament': filaments.get(fil, fil), 'overrides': cfg.get('overrides') or {}}
    if engine != 'bambu':                    # Bambu Studio reports and releases stay as they were before engines
        out['engine'] = engine
    return out


def engine_executable(engine: str) -> Optional[str]:
    """The command that runs the engine's slicer, as one string; None when it is not installed."""
    if engine == 'prusa':
        from cadagent.manufacturing import slicer_prusa
        exe = slicer_prusa.executable()
        return ' '.join(exe) if exe else None
    return executable()


def not_installed(engine: str) -> str:
    return f'{ENGINE_NAMES[engine]} is not installed ({_INSTALL[engine]})'


def settings_differ(report: dict, project) -> List[str]:
    """The ``cad.slicer`` settings a slice report was not made with. A report with no ``engine`` key was made with
    Bambu Studio."""
    st = dict(_settings(project), engine=engine_of(project))
    return [k for k, v in st.items() if (report.get(k, 'bambu') if k == 'engine' else report.get(k)) != v]


def part_overrides(project, name: str) -> dict:
    """``cad.slicer.parts.<name>.overrides``: the part's own settings, applied on top of ``cad.slicer.overrides``
    (``{}`` when ``cad.slicer.parts`` is a list or names none)."""
    parts = (getattr(project, 'slicer', None) or {}).get('parts')
    if isinstance(parts, dict):
        return dict((parts.get(name) or {}).get('overrides') or {})
    return {}


def _row_current(project, name: str, row) -> bool:
    """A report row is current while its part's 3MF has the sha256 recorded and its part overrides are the ones
    ``cad.slicer.parts`` names now."""
    f = project.exports_dir / f'{name}.3mf'
    return (isinstance(row, dict) and bool(row.get('grams')) and f.is_file() and _sha(f) == row.get('sha256')
            and (row.get('part_overrides') or {}) == part_overrides(project, name))


def _expected_parts(project) -> List[str]:
    from cadagent.publish.report import load_parts
    cfg = dict(project.slicer or {})
    known, _ = load_parts(project)
    return list(cfg.get('parts') or known)


def _row_ok(row: dict) -> bool:
    """A report row's ``ok``; a row without one (Bambu Studio, a missing 3MF) is ok when it has grams."""
    return bool(row.get('ok')) if 'ok' in row else bool(row.get('grams'))


def slice_project(project, parts=None) -> dict:
    """Slice each part's 3MF (``exports/<part>.3mf``) with the project's ``cad.slicer`` settings and write
    ``exports/slice-report.json``: grams and minutes per part, the totals, the settings, and each 3MF's sha256 so the
    report can tell a stale result from a current one.

    ``cad.slicer`` keys (all optional): engine, printer, process, filament (``pla``, ``petg`` or a profile name),
    overrides (process settings, e.g. ``{wall_loops: "3"}``), parts (the parts to slice; default all): a list of
    names, or a mapping of name to ``{overrides: {...}}``, the part's own settings on top of ``overrides``.

    A PrusaSlicer row also carries what PrusaSlicer's log said (``warnings``, ``errors``, ``stability_issues``,
    ``benign_log_lines``, ``log``) and ``ok``: exit code 0, G-code written and no error or stability issue. The
    report passes only when every row is ok; a Bambu Studio row is ok when it has grams."""
    from cadagent.publish.report import load_parts

    cfg = dict(project.slicer or {})
    known, error = load_parts(project)
    if error:
        raise FileNotFoundError(error)
    names = list(parts or cfg.get('parts') or known)
    st, engine = _settings(project), engine_of(project)
    work = project.root / 'build' / 'slicer'
    path = project.exports_dir / 'slice-report.json'
    rows = {}
    if parts and path.exists():   # slicing some parts updates them in a report made with the same settings
        try:
            old = json.loads(path.read_text())
            if not settings_differ(old, project):
                # only the rows still current: a part whose 3MF or own overrides changed is sliced again or left out
                rows = {n: r for n, r in (old.get('parts') or {}).items() if _row_current(project, n, r)}
        except json.JSONDecodeError:
            pass
    for name in names:
        model = project.exports_dir / f'{name}.3mf'
        if not model.exists():
            rows[name] = {'error': f'{model.name} not found'}
            continue
        own = part_overrides(project, name)
        r = slice_part(model, workdir=work / name, printer=st['printer'], process=st['process'],
                       filament=st['filament'], overrides={**st['overrides'], **own} or None, engine=engine)
        r['sha256'] = _sha(model)
        rows[name] = {k: r.get(k) for k in ('grams', 'minutes', 'filament_m', 'error', 'sha256')}
        if own:
            rows[name]['part_overrides'] = own
        if engine == 'prusa':
            rows[name].update({k: r.get(k) for k in ('warnings', 'errors', 'stability_issues', 'benign_log_lines')})
            log = r.get('log')
            if log and Path(log).resolve().is_relative_to(project.root.resolve()):
                log = str(Path(log).resolve().relative_to(project.root.resolve()))
            rows[name]['log'] = log
            rows[name]['ok'] = bool(r.get('ok', r.get('grams') and not r.get('error')))
    total_g = sum(v.get('grams') or 0.0 for v in rows.values())
    total_min = sum(v.get('minutes') or 0.0 for v in rows.values())
    exe = engine_executable(engine)
    if exe and engine == 'bambu':
        exe = str(Path(exe).resolve())
    out = {'slicer': f"{ENGINE_NAMES[engine]} (command line)", **st, 'slicer_executable': exe,
           'parts': rows, 'total_grams': round(total_g, 1), 'total_hours': round(total_min / 60, 2),
           'pass': bool(rows) and all(_row_ok(v) for v in rows.values()),
           'note': 'Slicer estimates for one copy of each part with the stated profile; supports off unless the profile turns them on.'}
    path.write_text(json.dumps(out, indent=2) + '\n')
    out['path'] = str(path)
    return out


def current_report(project) -> Optional[dict]:
    """The slice report only when it is complete and current: every expected part (``cad.slicer.parts``, else every
    part) sliced, with the settings ``cad.slicer`` names now (each part's own overrides too), from 3MF files unchanged
    since (sha256). Else None."""
    path = project.exports_dir / 'slice-report.json'
    if not path.exists():
        return None
    try:
        rep = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not rep.get('parts') or set(rep['parts']) != set(_expected_parts(project)):
        return None
    if settings_differ(rep, project):
        return None
    for name, row in rep.get('parts', {}).items():
        if not _row_current(project, name, row):
            return None
    return rep
