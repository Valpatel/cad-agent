"""Every image a Markdown page shows on GitHub must exist and be the image its name says.

A broken picture on the repo page is the first thing a visitor sees, so this walks every tracked ``.md`` outside
``software/vendor/`` (vendored projects keep their own paths) and checks each local image reference the way GitHub resolves
it: relative to the page, or to the repo root for a leading ``/``, with exact case. The file must be in git, not
empty, not a Git LFS pointer (GitHub shows those as broken), and start with the magic bytes of its extension.
Remote images (badges) are not fetched here, so the suite stays offline.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]

IMAGE_INLINE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<bare>[^)\s]+))(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
IMAGE_REFUSE = re.compile(r'!\[(?P<alt>[^\]]*)\]\[(?P<ref>[^\]]*)\]')
REF_DEF = re.compile(r'^ {0,3}\[(?P<ref>[^\]]+)\]:\s*(?:<(?P<angle>[^>]+)>|(?P<bare>\S+))', re.M)
HTML_IMG = re.compile(r'<(?:img|source)\b[^>]*>', re.I)
HTML_ATTR = re.compile(r'\s(?P<name>src|srcset)\s*=\s*(?:"(?P<dq>[^"]*)"|\'(?P<sq>[^\']*)\'|(?P<uq>[^\s>]+))', re.I)
FENCE = re.compile(r'^ {0,3}(?P<f>`{3,}|~{3,}).*?^ {0,3}(?P=f)[`~]*[ \t]*$', re.M | re.S)
REMOTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)
MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}
# Rendered-site tests separately check that embedded local images are copied byte-for-byte.
# Images may live beside an example README as well as in docs/img/.


def tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return {p for p in out.decode().split("\0") if p}


def visible(text: str) -> str:
    """The text GitHub renders as markup: no fenced code, inline code or HTML comments."""
    text = FENCE.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"(`+)(?!`).+?(?<!`)\1(?!`)", "", text, flags=re.S)


def image_refs(text: str):
    text = visible(text)
    refs = {m["ref"].strip().lower(): m["angle"] or m["bare"] for m in REF_DEF.finditer(text)}
    for m in IMAGE_INLINE.finditer(text):
        yield m["angle"] or m["bare"]
    for m in IMAGE_REFUSE.finditer(text):
        key = (m["ref"] or m["alt"]).strip().lower()
        yield refs.get(key, f"[missing reference: {key}]")
    for tag in HTML_IMG.finditer(text):
        for a in HTML_ATTR.finditer(tag.group(0)):
            value = a["dq"] if a["dq"] is not None else a["sq"] if a["sq"] is not None else a["uq"]
            if a["name"].lower() == "src":
                yield value
            else:
                yield from (c.split()[0] for c in value.split(",") if c.strip())


def resolve(page: str, url: str) -> str:
    path = unquote(url.split("#")[0].split("?")[0])
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(page), path))


def is_svg(head: bytes) -> bool:
    text = re.sub(rb"<!--.*?-->|<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", b"", head, flags=re.S | re.I)
    return text.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<svg")


def problems(page: str, text: str, files: set[str], read=lambda p: (ROOT / p).read_bytes()) -> list[str]:
    found = []
    for url in image_refs(text):
        if url.startswith("[missing reference"):
            found.append(f"{page}: image {url}")
            continue
        if REMOTE.match(url):
            continue
        path = resolve(page, url)
        if path not in files:
            near = [f for f in files if f.lower() == path.lower()]
            found.append(f"{page}: {url} -> {path} is not in git" + (f" (case differs: {near[0]})" if near else ""))
            continue
        head = read(path)[:4096]
        kind = posixpath.splitext(path)[1].lower()
        if not head:
            found.append(f"{page}: {url} is empty")
        elif head.startswith(b"version https://git-lfs"):
            found.append(f"{page}: {url} is a Git LFS pointer, which GitHub shows as a broken image")
        elif kind == ".svg" and not is_svg(head):
            found.append(f"{page}: {url} is not a svg file")
        elif kind in MAGIC and not head.startswith(MAGIC[kind]):
            found.append(f"{page}: {url} is not a {kind[1:]} file")
    return found


def markdown_pages(files):
    metadata = {"software/vendor/README.md", "software/vendor/upstreams/README.md", "software/vendor/THIRD_PARTY_NOTICES.md"}
    return sorted(f for f in files if f.endswith(".md") and (not f.startswith("software/vendor/") or f in metadata))


def test_repository_metadata_stays_in_the_image_audit():
    metadata = {"software/vendor/README.md", "software/vendor/upstreams/README.md", "software/vendor/THIRD_PARTY_NOTICES.md"}
    assert set(markdown_pages(metadata | {"software/vendor/imported/README.md", "software/vendor/upstreams/registry.yaml"})) == metadata


def test_every_markdown_image_exists_and_is_an_image():
    files = tracked()
    pages = markdown_pages(files)
    assert "README.md" in pages
    bad = [p for page in pages for p in problems(page, (ROOT / page).read_text(encoding="utf-8", errors="replace"), files)]
    assert not bad, "broken images:\n" + "\n".join(bad)


@pytest.mark.parametrize(
    "page, text, data, expect",
    [
        ("docs/a.md", "![x](img/gone.png)", {}, "not in git"),
        ("docs/a.md", '<img src="img/P.png">', {"docs/img/p.png": b"\x89PNG\r\n\x1a\n"}, "case differs"),
        ("docs/a.md", "![x](img/p.png)", {"docs/img/p.png": b""}, "is empty"),
        ("docs/a.md", "![x](img/p.png)", {"docs/img/p.png": b"version https://git-lfs.github.com/spec/v1\n"}, "LFS"),
        ("docs/a.md", "![x](img/p.jpg)", {"docs/img/p.jpg": b"\x89PNG\r\n\x1a\n"}, "not a jpg"),
        ("README.md", "![x](/docs/img/p.svg)", {"docs/img/p.svg": b"<html>"}, "not a svg"),
        ("docs/a.md", "![x][fig]\n\n[fig]: img/gone.png", {}, "not in git"),
        ("docs/a.md", "![x][nope]", {}, "missing reference"),
        ("docs/a.md", "<img src=img/gone.png>", {}, "not in git"),
        ("docs/a.md", "![x](img/gone.png 'title')", {}, "not in git"),
        ("docs/a.md", "![x](<img/my gone.png>)", {}, "not in git"),
        ("docs/a.md", '<source srcset="img/p.png 1x, img/gone.png 2x">', {"docs/img/p.png": b"\x89PNG\r\n\x1a\n"}, "gone.png"),
    ],
)
def test_each_rule_catches_its_break(page, text, data, expect):
    out = problems(page, text, set(data), read=lambda p: data[p])
    assert len(out) == 1 and expect in out[0], out


def test_good_remote_and_hidden_images_pass():
    data = {
        "docs/img/p.png": b"\x89PNG\r\n\x1a\n",
        "docs/img/h.svg": b'<?xml version="1.0"?>\n<!-- made by a tool -->\n<!DOCTYPE svg>\n<svg/>',
        "docs/img/my pic.png": b"\x89PNG\r\n\x1a\n",
        "docs/examples/e.png": b"\x89PNG\r\n\x1a\n",
    }
    text = (
        '![a](img/p.png) <img src="../docs/img/h.svg"> ![b](https://img.shields.io/x.svg) ![s](img/my%20pic.png)\n'
        "```\n![c](gone.png)\n```\n~~~\n![d](gone.png)\n~~~\n<!-- ![e](gone.png) -->\nuse `![f](gone.png)` to embed\n"
    )
    assert problems("docs/a.md", text, set(data), read=lambda p: data[p]) == []
    assert problems("docs/examples/x/README.md", "![e](../e.png)", set(data), read=lambda p: data[p]) == []
