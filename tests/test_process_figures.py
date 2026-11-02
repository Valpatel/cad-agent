"""docs/process-checks.md's figures are drawn by tools/process_figures.py from the modules they show (#99)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_committed_figures_match_the_code():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "process_figures.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_page_shows_every_figure():
    page = (ROOT / "docs" / "process-checks.md").read_text(encoding="utf-8")
    for name in ("dfm-wall.svg", "layer-factors.svg", "sheet-flange.svg"):
        assert f"img/process/{name}" in page, name
