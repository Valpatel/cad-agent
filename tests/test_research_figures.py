"""The research charts are drawn from the tables on their pages, and stay in step with them."""
import re
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
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text()
    assert md.index("**DuPont Table 10.06**") < md.index("docs/img/research/moulded-strain.svg") < md.index("## 4.")
    assert md.index("## 6. Printed") < md.index("docs/img/research/printed-strain.svg") < md.index("## 7.")


def test_every_row_with_ratios_is_drawn():
    svg = (ROOT / "docs" / "img" / "research" / "fdm-anisotropy.svg").read_text()
    for name in ("PLA Basic, Bambu", "PolyMide CoPA, wet", "TPU 95A HF, Bambu"):
        assert f">{name}</text>" in svg
    for name in ("PA6-CF, Bambu", "PETG Basic V3.0, Bambu", "PETG Basic V2.0, Bambu"):   # read from Bambu's sheets (#156)
        assert f">{name}</text>" in svg
    assert "Not drawn" not in svg                            # every row with a ratio is from a data sheet now
    assert "≥" not in svg                                    # TPU's two lower bounds give no ratio, not a bound
    assert svg.count(">not known</text>") == 1               # TPU's strain
    assert "PolyFlex TPU95" not in svg                       # no Z data: not drawn
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text()
    section = md[md.index("## 5. FDM anisotropy"):]
    lines = section.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("|"))
    table = lines[first:next(i for i in range(first, len(lines)) if not lines[i].startswith("|"))]
    rows = table[2:]                                          # without the header and the --- line
    with_ratio = [r for r in rows if any(c.strip()[:1].isdigit() for c in r.split("|")[5:7])
                  and not re.search(r"\((?:s|u)\b", r.split("|")[7])]
    assert svg.count('text-anchor="end"') == len(with_ratio) == 16   # every data-sheet row with a ratio, and no other


def _figures():
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_figures", ROOT / "tools" / "research_figures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_cell_is_a_number_or_an_explicit_gap():
    import pytest
    number = _figures().number
    assert number("22,951", "t") == (22951.0, "")
    assert number(">480", "t") == (480.0, ">")
    for gap in ("—", "— (both lower bounds)", "no Z data", "n/a"):
        assert number(gap, "t") is None
    for odd in ("0.61[^1]", "~0.6", "32.3k", "(u) 0.5", "0.5 (est.)"):
        with pytest.raises(ValueError, match="neither a number nor a gap"):
            number(odd, "t")


def test_a_strain_cell_is_a_percentage_a_range_or_a_pair():
    import pytest
    percent = _figures().percent
    assert percent("4 %", "t") == (4.0, "")
    assert percent("0.8–1.2 %", "t") == (0.8, "", 1.2)
    assert percent("1.1 / 0.6 %", "t") == (1.1, "")              # single / repeat: the single-use value
    for odd in ("4", "~4 %", "4 % (u)", "strain does not govern"):
        with pytest.raises(ValueError, match="not a strain in per cent"):
            percent(odd, "t")


def test_strain_charts_draw_every_row_and_ranges_as_ranges():
    moulded = (ROOT / "docs" / "img" / "research" / "moulded-strain.svg").read_text()
    assert moulded.count('text-anchor="end"') == 6 + 9                    # Bayer's six resins and DuPont's nine
    assert ">2–4 %</text>" in moulded and ">0.8–1.2 %</text>" in moulded   # a range keeps both ends
    assert moulded.count('fill-opacity="0.35"') == 5                       # the five ranges in DuPont's table
    printed = (ROOT / "docs" / "img" / "research" / "printed-strain.svg").read_text()
    assert printed.count('text-anchor="end"') == 13                       # every row but TPU, which strain does not govern
    assert ">CoPA, dry, Polymaker</text>" in printed and ">3.3 %</text>" in printed
    assert "TPU 95A not drawn" in printed
