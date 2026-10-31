"""The research charts are drawn from the tables on their pages, and stay in step with them."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_committed_charts_match_their_tables():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "research_figures.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_charts_are_embedded_where_their_tables_are():
    assert "docs/img/research/fdm-anisotropy.svg" in (ROOT / "research" / "compliant-mechanisms.md").read_text()
    assert "docs/img/research/landscape-stars.svg" in (ROOT / "research" / "landscape.md").read_text()


def test_every_row_with_ratios_is_drawn():
    svg = (ROOT / "docs" / "img" / "research" / "fdm-anisotropy.svg").read_text()
    for name in ("PLA Basic, Bambu", "PolyMide CoPA, wet", "TPU 95A HF, Bambu"):
        assert f">{name}</text>" in svg
    assert ">≥0.74<" in svg                                  # TPU's strain ratio is a lower bound and says so
    assert "PolyFlex TPU95" not in svg                       # no Z data: not drawn
