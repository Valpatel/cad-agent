"""Local link validation for HTML and Markdown pages."""

from __future__ import annotations

from cadagent.links import is_local, missing_links, page_links

HTML = """<!doctype html><html><head><link rel="stylesheet" href='style.css'>
<script src="app.js">const x = `<img src="part-${n}.png">`; document.write('<a href="gen.html">');</script></head>
<body><!-- <a href="commented.html"> -->
<a href="ok.html#frag">ok</a><a href="ok.html?v=1">ok</a><a href="missing.html">x</a>
<a href="https://example.com/a">web</a><a href="mailto:a@b.c">mail</a><a href="#top">top</a>
<img src="data:image/png;base64,AAAA"><a href="bambustudio://open?file=x">slicer</a>
<a href="/root.txt">root</a><a href="sub/">dir</a><a href="with%20space.txt">enc</a>
</body></html>"""

MD = """# Readme
[ok](docs/ok.md) and ![img](docs/img.png "title") and [gone](docs/gone.md#x)
[web](https://example.com) [anchor](#readme)
```
[in code](docs/code-only.md)
```
`[inline](docs/inline.md)`
"""

def test_html_links_found_and_runtime_links_ignored(tmp_path):
    page = tmp_path / "index.html"
    page.write_text(HTML)
    links = page_links(page)
    assert links == ["style.css", "app.js", "ok.html#frag", "ok.html?v=1", "missing.html",
                     "/root.txt", "sub/", "with%20space.txt"]

def test_missing_links_reports_only_unresolved_local_files(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.html").write_text(HTML)
    for name in ("style.css", "app.js", "ok.html", "with space.txt"):
        (tmp_path / "pages" / name).write_text("")
    (tmp_path / "pages" / "sub").mkdir()
    (tmp_path / "root.txt").write_text("")
    assert missing_links(["pages/index.html"], tmp_path) == ["pages/index.html: missing.html"]

def test_markdown_links_skip_code(tmp_path):
    (tmp_path / "README.md").write_text(MD)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ok.md").write_text("")
    (tmp_path / "docs" / "img.png").write_text("")
    assert page_links(tmp_path / "README.md") == ["docs/ok.md", "docs/img.png", "docs/gone.md#x"]
    assert missing_links([tmp_path / "README.md"], tmp_path) == ["README.md: docs/gone.md#x"]

def test_missing_page_is_reported(tmp_path):
    assert missing_links(["preview/index.html"], tmp_path) == ["preview/index.html: page not found"]

def test_is_local():
    assert is_local("a/b.png") and is_local("../x.json")
    for link in ("http://x", "HTTPS://x", "mailto:x", "#a", "//cdn/x.js", "data:x", "javascript:void(0)",
                 "part-${n}.png", "", "{{ url }}"):
        assert not is_local(link), link
