"""Every image a Markdown page shows on GitHub must exist and be the image its name says.

A broken picture on the repo page is the first thing a visitor sees, so this walks every tracked ``.md`` outside
``vendor/`` (vendored projects keep their own paths) and checks each local image reference the way GitHub resolves
it: relative to the page, or to the repo root for a leading ``/``, with exact case. The file must be in git, not
empty, not a Git LFS pointer (GitHub shows those as broken), and start with the magic bytes of its extension.
Remote images (badges) are not fetched here, so the suite stays offline.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

IMAGE_REF = re.compile(
    r'!\[[^\]]*\]\(\s*<?(?P<md>[^)\s>]+)>?(?:\s+"[^"]*")?\s*\)'
    r'|<img\b[^>]*?\ssrc\s*=\s*["\'](?P<img>[^"\']+)["\']'
    r'|<source\b[^>]*?\ssrcset\s*=\s*["\'](?P<src>[^"\'\s,]+)',
    re.I,
)
REMOTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)
MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
    ".svg": (b"<svg", b"<?xml"),
}


def tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return {p for p in out.decode().split("\0") if p}


def image_refs(text: str):
    # Code blocks show markup as text, not images.
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    for m in IMAGE_REF.finditer(text):
        yield next(g for g in m.groups() if g)


def resolve(page: str, url: str) -> str:
    path = url.split("#")[0].split("?")[0]
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(page), path))


def problems(page: str, text: str, files: set[str], read=lambda p: (ROOT / p).read_bytes()) -> list[str]:
    found = []
    for url in image_refs(text):
        if REMOTE.match(url):
            continue
        path = resolve(page, url)
        if path not in files:
            near = [f for f in files if f.lower() == path.lower()]
            found.append(f"{page}: {url} -> {path} is not in git" + (f" (case differs: {near[0]})" if near else ""))
            continue
        head = read(path)[:256]
        kind = posixpath.splitext(path)[1].lower()
        if not head:
            found.append(f"{page}: {url} is empty")
        elif head.startswith(b"version https://git-lfs"):
            found.append(f"{page}: {url} is a Git LFS pointer, which GitHub shows as a broken image")
        elif kind in MAGIC and not head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(MAGIC[kind]):
            found.append(f"{page}: {url} is not a {kind[1:]} file")
    return found


def test_every_markdown_image_exists_and_is_an_image():
    files = tracked()
    pages = sorted(f for f in files if f.endswith(".md") and not f.startswith("vendor/"))
    assert "README.md" in pages
    bad = [p for page in pages for p in problems(page, (ROOT / page).read_text(encoding="utf-8", errors="replace"), files)]
    assert not bad, "broken images:\n" + "\n".join(bad)


@pytest.mark.parametrize(
    "page, text, data, expect",
    [
        ("docs/a.md", "![x](img/gone.png)", {}, "not in git"),
        ("docs/a.md", '<img src="IMG/p.png">', {"docs/img/p.png": b"\x89PNG\r\n\x1a\n"}, "case differs"),
        ("docs/a.md", "![x](p.png)", {"docs/p.png": b""}, "is empty"),
        ("docs/a.md", "![x](p.png)", {"docs/p.png": b"version https://git-lfs.github.com/spec/v1\n"}, "LFS"),
        ("docs/a.md", "![x](p.jpg)", {"docs/p.jpg": b"\x89PNG\r\n\x1a\n"}, "not a jpg"),
        ("README.md", "![x](/docs/p.svg)", {"docs/p.svg": b"<html>"}, "not a svg"),
    ],
)
def test_each_rule_catches_its_break(page, text, data, expect):
    out = problems(page, text, set(data), read=lambda p: data[p])
    assert len(out) == 1 and expect in out[0]


def test_good_and_remote_images_pass():
    data = {"docs/img/p.png": b"\x89PNG\r\n\x1a\n", "docs/img/h.svg": b'<?xml version="1.0"?><svg/>'}
    text = '![a](img/p.png) <img src="../docs/img/h.svg"> ![b](https://img.shields.io/x.svg)\n```\n![c](gone.png)\n```'
    assert problems("docs/a.md", text, set(data), read=lambda p: data[p]) == []
