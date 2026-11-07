"""Open a model in PrusaSlicer's window to look at it or screenshot it, with a private profile folder.

    from cadagent.manufacturing import prusa_view
    r = prusa_view.open_view('exports/door.3mf', screenshot='exports/door-prusa.png', close=True)
    r['pid'], r['window'], r['screenshot']

``cad-agent prusa-view <model>`` is the command. PrusaSlicer runs as a separate program (it is AGPL-3.0; nothing of it
is imported) with ``--datadir`` pointed at a private copy of the profile folder (``slicer_prusa.private_datadir``), so
your own PrusaSlicer configuration is never read for state or written to. Its ``PrusaSlicer.ini`` gets the settings
that keep start-up free of dialogs: ``version_system_info_sent`` (the "Send system info" dialog), ``version_check``,
``preset_update``, ``notify_release``, ``show_hints`` and ``show_splash_screen`` off, a large ``window_mainframe`` and
``background_processing = 1`` so the model is sliced as it loads. ``SSL_CERT_FILE`` is set as well: without it the
flatpak stops at a certificate-store dialog. The ``[presets]`` section names the printer, print and filament(s) of
the configuration loaded (one ``filament_<n>`` per further tool).

The configuration is ``--config`` (an ini PrusaSlicer wrote, such as a slice's ``config.ini``), else PrusaSlicer's own
resolution of the ``cad.slicer`` presets and overrides (``slicer_prusa.resolved_by_prusaslicer``). ``view_bed`` loads
a model larger than the printer on a bed of that size, with the wipe tower and background slicing off: the result is
for looking at only, never for printing.

The window is found with ``xwininfo`` (an X11 or XWayland display), as the new PrusaSlicer window whose title holds
the model's name (``Untitled`` for an STL), and screenshotted with ImageMagick's ``import -window``. Only processes run with this view's own
``--datadir`` are ever stopped, by PID: other PrusaSlicer windows, yours or another session's, are left alone.

PrusaSlicer 2.9 shares the objects of a project out among its virtual beds by position; an assembly meant to stay
together should be one object with a volume per part (``prusa3mf.write_project``). What the window shows is PrusaSlicer's reading of the file; it
does not prove the parts fit or print.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from cadagent.manufacturing import slicer_prusa

CA_ENV = 'CADAGENT_PRUSA_CA_FILE'
# inside the flatpak (the GNOME runtime), and on the common host distributions for a native prusa-slicer
FLATPAK_CA_FILE = '/etc/pki/tls/certs/ca-bundle.crt'
HOST_CA_FILES = ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt', '/etc/ssl/cert.pem',
                 '/etc/ssl/ca-bundle.pem')
WINDOW = (1920, 1172)
WINDOW_TIMEOUT = 180.0
MAX_PRINT_HEIGHT = 1200.0      # PrusaSlicer 2.9 refuses a larger max_print_height ("Value out of range")
_MARK = '.cadagent-prusa-view'
_WINDOW_LINE = re.compile(r'^\s*(0x[0-9a-fA-F]+) "(.*)": \("prusa-slicer" "PrusaSlicer"\)\s+(\d+)x(\d+)')
_VERSION = re.compile(r'PrusaSlicer-(\d+(?:\.\d+)+)')


class ViewError(RuntimeError):
    """The view cannot be opened or screenshotted here (no display, missing tool, bad argument)."""


def parse_bed(text: str) -> Tuple[float, float, Optional[float]]:
    """``WxD`` or ``WxDxH`` in mm (height None when not given; ``view_bed_config`` picks one)."""
    parts = str(text).lower().replace(' ', '').split('x')
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        nums = []
    if len(nums) not in (2, 3) or any(not n > 0 for n in nums):
        raise ValueError(f'--view-bed takes WIDTHxDEPTH or WIDTHxDEPTHxHEIGHT in mm, e.g. 1500x600, not {text!r}')
    if len(nums) == 3 and nums[2] > MAX_PRINT_HEIGHT:
        raise ValueError(f'--view-bed height {nums[2]:g} mm is above PrusaSlicer\'s limit of {MAX_PRINT_HEIGHT:g} mm')
    return nums[0], nums[1], nums[2] if len(nums) == 3 else None


def _num(v: float) -> str:
    return f'{v:g}'


def view_bed_config(cfg: Dict[str, str], bed: Tuple[float, float, Optional[float]]) -> Dict[str, str]:
    """``cfg`` on a ``bed`` (width, depth, height mm) viewing bed: no wipe tower and no bed model or texture. With no
    height, the printer's own, raised to the bed's larger side up to PrusaSlicer's limit (it refuses more)."""
    w, d, z = bed
    if z is None:
        try:
            own = float(cfg.get('max_print_height') or 0)
        except ValueError:
            own = 0.0
        z = min(max(own, w, d), MAX_PRINT_HEIGHT)
    out = dict(cfg)
    out.update(bed_shape=f'0x0,{_num(w)}x0,{_num(w)}x{_num(d)},0x{_num(d)}', max_print_height=_num(z), wipe_tower='0',
               bed_custom_model='', bed_custom_texture='')
    return out


def _ids(cfg: Dict[str, str]) -> Tuple[str, str, List[str]]:
    filaments = [s.strip().strip('"') for s in cfg.get('filament_settings_id', '').split(';')]
    tools = len([n for n in cfg.get('nozzle_diameter', '').split(',') if n.strip()]) or 1
    filaments = [f for f in filaments if f] or ['']
    filaments += [filaments[-1]] * (tools - len(filaments))
    return cfg.get('printer_settings_id', '').strip('"'), cfg.get('print_settings_id', '').strip('"'), filaments


def gui_settings(version: Optional[str], background: bool = True, window: Tuple[int, int] = WINDOW) -> Dict[str, str]:
    """The ``PrusaSlicer.ini`` keys that keep the window's start-up free of dialogs."""
    out = {'window_mainframe': f'0; 0; {window[0]}; {window[1]}; 1',
           'background_processing': '1' if background else '0', 'show_splash_screen': '0', 'version_check': '0',
           'preset_update': '0', 'notify_release': 'none', 'show_hints': '0'}
    if version:
        out = {'version_system_info_sent': version, **out}
    return out


def write_gui_ini(data_dir: Path, cfg: Dict[str, str], version: Optional[str], background: bool = True) -> Path:
    """Put the GUI settings at the top of ``data_dir/PrusaSlicer.ini`` and a ``[presets]`` section at its end."""
    ini = Path(data_dir) / 'PrusaSlicer.ini'
    printer, process, filaments = _ids(cfg)
    head = ''.join(f'{k} = {v}\n' for k, v in gui_settings(version, background).items())
    presets = {'printer': printer, 'print': process, 'filament': filaments[0]}
    presets.update({f'filament_{i}': f for i, f in enumerate(filaments[1:], 1)})
    tail = '[presets]\n' + ''.join(f'{k} = {v}\n' for k, v in presets.items())
    body = (ini.read_text(encoding='utf-8') if ini.exists() else '').strip()
    ini.write_text('\n'.join(p for p in (head, body + '\n' if body else '', tail) if p), encoding='utf-8')
    return ini


def version(exe: Sequence[str]) -> Optional[str]:
    """PrusaSlicer's version (``2.9.4``) from its ``--help``; None when it says none."""
    try:
        p = subprocess.run(list(exe) + ['--help'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VERSION.search((p.stdout or '') + (p.stderr or ''))
    return m.group(1) if m else None


def _is_flatpak(exe: Sequence[str]) -> bool:
    return Path(exe[0]).name == 'flatpak'


def ca_file(exe: Sequence[str], override: Optional[str] = None) -> Optional[str]:
    """The CA bundle given to PrusaSlicer as ``SSL_CERT_FILE``: ``override``, else ``$CADAGENT_PRUSA_CA_FILE``, else the
    flatpak runtime's own bundle (a path inside the sandbox), else the first host bundle that exists."""
    chosen = override or os.environ.get(CA_ENV)
    if chosen:
        return chosen
    if _is_flatpak(exe):
        return FLATPAK_CA_FILE
    return os.environ.get('SSL_CERT_FILE') or next((f for f in HOST_CA_FILES if Path(f).is_file()), None)


def gui_command(exe: Sequence[str], data_dir: Path, config: Path, model: Path,
                ca: Optional[str]) -> Tuple[List[str], Dict[str, str]]:
    """The command line and environment that open ``model`` in the window. The flatpak does not see the caller's
    environment, so ``SSL_CERT_FILE`` goes in as ``flatpak run --env=``."""
    exe = list(exe)
    env = dict(os.environ)
    if ca:
        if _is_flatpak(exe) and 'run' in exe:
            exe.insert(exe.index('run') + 1, f'--env=SSL_CERT_FILE={ca}')
        else:
            env['SSL_CERT_FILE'] = ca
    return exe + ['--datadir', str(data_dir), '--load', str(config), str(model)], env


def has_display() -> bool:
    return bool(os.environ.get('DISPLAY'))


def _prusa_argv0(arg0: str) -> bool:
    name = Path(arg0).name.lower()
    return 'prusa' in name or name in ('flatpak', 'bwrap')


def own_processes(data_dir: Path, ps_output: Optional[str] = None) -> List[int]:
    """PIDs of the PrusaSlicer processes (and their flatpak wrappers) run with ``--datadir data_dir``. Only a program
    named like PrusaSlicer, ``flatpak`` or ``bwrap`` counts, never a shell whose command line mentions the folder, and
    never this process or its parents."""
    if ps_output is None:
        try:
            ps_output = subprocess.run(['ps', '-ww', '-eo', 'pid=,args='], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            return []
    needle = f'--datadir {data_dir}'
    mine = {os.getpid(), os.getppid()}
    out = []
    for line in ps_output.splitlines():
        pid, _, args = line.strip().partition(' ')
        if not pid.isdigit() or int(pid) in mine:
            continue
        args = args.strip()
        at = args.find(needle)
        end = at + len(needle)
        if at < 0 or (end < len(args) and args[end] != ' ') or not _prusa_argv0(args.split(' ', 1)[0]):
            continue
        out.append(int(pid))
    return out


def windows(tree: Optional[str] = None) -> List[Tuple[str, str, int, int]]:
    """``(id, title, width, height)`` of every PrusaSlicer window on the display, from ``xwininfo -root -tree``."""
    if tree is None:
        try:
            tree = subprocess.run(['xwininfo', '-root', '-tree'], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            return []
    out = []
    for line in tree.splitlines():
        m = _WINDOW_LINE.match(line)
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    return out


def pick_window(found: List[Tuple[str, str, int, int]], stem: str, before: Sequence[str]) -> Optional[str]:
    """The largest window that was not there before launch and whose title holds the model's name, or is
    ``Untitled`` (PrusaSlicer names the project after a 3MF, not after an STL)."""
    def ours(title: str) -> bool:
        return stem in title or title.lstrip('*').startswith('Untitled - ')
    new = [w for w in found if w[0] not in set(before) and ours(w[1])]
    return max(new, key=lambda w: w[2] * w[3])[0] if new else None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                           # a zombie child of ours counts as gone
        return 'Z' not in Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
    except (OSError, IndexError):
        return True


def stop(data_dir: Path, popen: Optional[subprocess.Popen] = None, grace: float = 10.0) -> List[int]:
    """Stop the processes run with this ``--datadir`` (and ``popen``), by PID: SIGTERM, then SIGKILL after ``grace``
    seconds. Returns the PIDs signalled."""
    pids = own_processes(data_dir)
    if popen is not None and popen.poll() is None and popen.pid not in pids:
        pids.append(popen.pid)
    # the program itself first, its flatpak wrapper after (which exits with it)
    pids.sort(key=lambda p: p == (popen.pid if popen else None))
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if popen is not None:
                popen.poll()
            if not any(_alive(p) for p in pids):
                break
            time.sleep(0.25)
        else:
            continue
        break
    if popen is not None:
        try:
            popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    return pids


def work_dir(model: Path, workdir=None) -> Path:
    """``workdir``, else ``<model folder>/prusa-view/<model name>``."""
    return Path(workdir).resolve() if workdir else Path(model).resolve().parent / 'prusa-view' / Path(model).stem


def _prepare(work: Path) -> None:
    if work.exists():
        if not (work / _MARK).exists() and any(work.iterdir()):
            raise ViewError(f'{work} exists and is not a prusa-view work folder; choose an empty or new folder')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / _MARK).write_text('cadagent.manufacturing.prusa_view work folder: safe to delete\n')


def _under_tmp(path: Path) -> bool:
    return Path(path).resolve().parts[:2] == ('/', 'tmp')


def prepare(model, settings: Optional[dict] = None, config=None, view_bed: Optional[tuple] = None,
            workdir=None, exe: Optional[List[str]] = None, prusa_version: Optional[str] = None) -> dict:
    """Write the work folder: the private ``prusaslicer-datadir`` and ``view-config.ini``. ``settings`` holds
    ``printer``, ``process``, ``filament`` and ``overrides`` (PrusaSlicer's defaults when empty); ``config`` an ini
    file used instead of them. Returns the paths, the configuration and the command line (nothing is started)."""
    exe = exe or slicer_prusa.executable()
    if not exe:
        raise ViewError(f'PrusaSlicer is not installed (prusa-slicer on PATH, or flatpak install flathub '
                        f'{slicer_prusa.FLATPAK_ID})')
    model = Path(model).resolve()
    if not model.is_file():
        raise FileNotFoundError(f'{model} not found')
    work = work_dir(model, workdir)
    if _is_flatpak(exe):
        for what, path in (('model', model), ('work folder', work)) + ((('config', Path(config)),) if config else ()):
            if _under_tmp(path):
                raise ViewError(f'the PrusaSlicer flatpak cannot read /tmp: move the {what} ({path}) under your home folder')
    data_dir = work / 'prusaslicer-datadir'
    running = own_processes(data_dir)
    if running:
        raise ViewError(f'a view of {model.name} is already open from {work} (PID {", ".join(map(str, running))}); '
                        'close it first (--stop)')
    _prepare(work)
    if config:
        cfg = slicer_prusa._parse(Path(config).read_text(encoding='utf-8'), Path(config), sections=False)['']
    else:
        st = dict(settings or {})
        printer, process = st.get('printer') or slicer_prusa.PRINTER, st.get('process') or slicer_prusa.PROCESS
        fil = st.get('filament') or 'pla'
        fil = slicer_prusa.FILAMENTS.get(fil, fil)
        try:
            base = slicer_prusa.resolved_by_prusaslicer(exe, printer, process, fil, work)
            cfg = slicer_prusa.build_config(base, st.get('overrides') or None)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise ViewError(f'cannot load the presets: {exc.args[0] if exc.args else exc}') from None
    if view_bed:
        cfg = view_bed_config(cfg, view_bed)
    printer, _, filaments = _ids(cfg)
    data_dir = slicer_prusa.private_datadir(work, filaments[0], printer or None)
    write_gui_ini(data_dir, cfg, prusa_version if prusa_version is not None else version(exe), background=not view_bed)
    view_config = work / 'view-config.ini'
    view_config.write_text(''.join(f'{k} = {v}\n' for k, v in sorted(cfg.items())), encoding='utf-8')
    return {'model': str(model), 'work': str(work), 'datadir': str(data_dir), 'config': str(view_config),
            'exe': exe,
            'view_bed': [view_bed[0], view_bed[1], float(cfg['max_print_height'])] if view_bed else None, 'settings': cfg}


def open_view(model, settings: Optional[dict] = None, config=None, view_bed=None, screenshot=None, wait: float = 10.0,
              close: bool = False, workdir=None, ca: Optional[str] = None, window_timeout: float = WINDOW_TIMEOUT,
              say=lambda msg: None) -> dict:
    """Open ``model`` in PrusaSlicer's window; with ``screenshot``, wait for the window, then ``wait`` seconds more
    (slicing and drawing), and save it; with ``close``, stop this view's own process afterwards."""
    if not has_display():
        raise ViewError('no display (DISPLAY is not set): PrusaSlicer\'s window needs an X11 or XWayland display')
    if isinstance(view_bed, str):
        view_bed = parse_bed(view_bed)
    tools = ['xwininfo'] + (['import'] if screenshot else [])
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        raise ViewError(f'{" and ".join(missing)} not found (x11-utils / xorg-xwininfo'
                        f'{", ImageMagick" if "import" in missing else ""}): needed to find and screenshot the window')
    r = prepare(model, settings, config, view_bed, workdir)
    cmd, env = gui_command(r['exe'], Path(r['datadir']), Path(r['config']), Path(r['model']), ca_file(r['exe'], ca))
    before = [w[0] for w in windows()]
    log = Path(r['work']) / 'prusaslicer.log'
    with open(log, 'w') as fh:
        popen = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, env=env,
                                 start_new_session=True)
    r.update(pid=popen.pid, command=cmd, log=str(log), window=None, screenshot=None, closed=False)
    say(f'PrusaSlicer started (PID {popen.pid}), private profile folder {r["datadir"]}')
    stem = Path(r['model']).stem
    deadline = time.monotonic() + window_timeout
    while time.monotonic() < deadline and popen.poll() is None:
        r['window'] = pick_window(windows(), stem, before)
        if r['window']:
            break
        time.sleep(1.0)
    if not r['window']:
        why = (f'PrusaSlicer exited (code {popen.returncode})' if popen.poll() is not None else
               f'no new PrusaSlicer window titled {stem!r} or Untitled within {window_timeout:g} s')
        stop(Path(r['datadir']), popen)
        raise ViewError(f'{why}; see {log}')
    r['pids'] = own_processes(Path(r['datadir'])) or [popen.pid]
    say(f'window {r["window"]}')
    if screenshot:
        time.sleep(max(0.0, wait))
        out = Path(screenshot).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run(['import', '-window', r['window'], str(out)], capture_output=True, text=True, timeout=120)
        if p.returncode != 0 or not out.is_file():
            if close:
                stop(Path(r['datadir']), popen)
            raise ViewError(f'import could not screenshot window {r["window"]}: {(p.stderr or "").strip()[-300:]}')
        r['screenshot'] = str(out)
    if close:
        r['stopped'] = stop(Path(r['datadir']), popen)
        r['closed'] = True
    r.pop('settings', None)
    return r
