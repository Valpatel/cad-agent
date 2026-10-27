"""House framing for simulation pictures."""

from __future__ import annotations

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from cadagent import simviz  # noqa: E402


def test_frame_adds_header_and_note(tmp_path):
    p = tmp_path / 'x.png'
    Image.new('RGB', (400, 300), 'white').save(p)
    simviz.frame(p, 'Title', 'sub', 'a note', legend=[('above 57 °C', simviz.CRITICAL)])
    im = Image.open(p)
    assert im.size == (400, 300 + 96 + 54)
    assert im.getpixel((5, 5)) == tuple(int(simviz.HEADER[i:i + 2], 16) for i in (1, 3, 5))
