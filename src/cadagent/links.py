"""Local link validation for the HTML and Markdown pages of a CAD project.

Only links that name a file are checked: ``http(s)``, ``mailto``, ``data``,
other URL schemes, in-page ``#anchors`` and anything built at runtime (a JS
template literal, or a link inside a ``<script>`` body) are ignored. Query
strings and fragments are stripped before the file lookup. A link starting
with ``/`` resolves against the project root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Union
from urllib.parse import unquote

_HTML_ATTR = re.compile(r"""\b(?:href|src)\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_SCRIPT_BODY = re.compile(r"(<script\b[^>]*>).*?(</script>)", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_MD_FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
_MD_CODE = re.compile(r"`[^`\n]*`")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

def is_local(link: str) -> bool:
    link = link.strip()
    if not link or link.startswith(("#", "//")):
        return False
    if "${" in link or "`" in link or "{{" in link:
        return False
    return not _SCHEME.match(link)

def page_links(page: Path) -> List[str]:
    """Every local link target in an HTML or Markdown page, in document order."""
    text = Path(page).read_text(encoding="utf-8", errors="replace")
    if Path(page).suffix.lower() in (".md", ".markdown"):
        text = _MD_CODE.sub("", _MD_FENCE.sub("", text))
        found = _MD_LINK.findall(text)
    else:
        text = _SCRIPT_BODY.sub(r"\1\2", _HTML_COMMENT.sub("", text))
        found = [m[1] for m in _HTML_ATTR.findall(text)]
    return [link.strip() for link in found if is_local(link)]

def _target(page: Path, link: str, root: Path) -> Path:
    path = unquote(re.split(r"[?#]", link, maxsplit=1)[0])
    if path.startswith("/"):
        return root / path.lstrip("/")
    return page.parent / path

def missing_links(pages: Iterable[Union[str, Path]], root: Union[str, Path]) -> List[str]:
    """``"<page>: <link>"`` for every local link that does not resolve to a file or
    directory, plus ``"<page>: page not found"`` for pages that do not exist."""
    root = Path(root).resolve()
    missing: List[str] = []
    for page in pages:
        page_path = Path(page) if Path(page).is_absolute() else root / page
        rel = _rel(page_path, root)
        if not page_path.is_file():
            missing.append(f"{rel}: page not found")
            continue
        for link in page_links(page_path):
            if not _target(page_path, link, root).exists():
                missing.append(f"{rel}: {link}")
    return missing

def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)
