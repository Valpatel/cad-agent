"""Recorded-format CFD runs for tests (tests/fixtures/cfd_runs; see its build.py). No solver runs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / 'fixtures' / 'cfd_runs'


def recorded(name: str, tmp_path: Path) -> Path:
    """A copy of a fixture run with its solver logs dated in the order they were written: read_results takes the
    newest log by modification time, and a checkout dates them all alike."""
    d = Path(shutil.copytree(RUNS / name, tmp_path / name))
    for i, log in enumerate(sorted(d.glob('log.solve*'))):          # log.solve, then log.solve.<unix time>
        os.utime(log, (1_000_000 + i, 1_000_000 + i))
    return d
