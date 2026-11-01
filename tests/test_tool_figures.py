"""The catalogue's tool covers in docs/img/tools/ are the tools' own output (tools/tool_figures.py).

The connectivity graph is kernel-free and compared byte for byte. The renders and screenshots need CadQuery or a
browser, so here they are only checked to exist where docs/catalog.yaml names them.
"""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_the_gates_cover_is_cad_agent_sites_drawing_of_the_bench():
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "tool_figures.py"), "--check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_every_tool_figure_is_named_and_exists():
    data = yaml.safe_load((ROOT / "docs" / "catalog.yaml").read_text(encoding="utf-8"))
    named = {f for t in data["tools"].values() for f in (t or {}).get("figures", []) if f.startswith("docs/img/tools/")}
    on_disk = {f"docs/img/tools/{p.name}" for p in (ROOT / "docs" / "img" / "tools").iterdir()}
    assert named == on_disk, f"named but missing: {named - on_disk}; on disk but unused: {on_disk - named}"
