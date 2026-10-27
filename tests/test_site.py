"""Project site: built from milestones, decisions, designs, Markdown pages and git history."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("markdown")
pytest.importorskip("yaml")

from cadagent import site  # noqa: E402

CFG = {"title": "Bot", "tagline": "A test robot", "notice": "Private", "milestones": "docs/milestones.yaml",
       "decisions": "docs/decisions.yaml", "designs": "exports/designs.json", "pages": ["README.md", "docs/*.md"],
       "links": [{"title": "Designer", "href": "designer/"}, {"title": "Repo", "href": "https://example.com/bot"}]}


def _project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "README.md").write_text("# Bot\n\nA robot that balances.\n\nSee [the plan](docs/plan.md#goals), "
                                        "![pic](docs/pic.png) and [code](tools/).\n\n```mermaid\nflowchart LR\n A-->B\n```\n")
    (tmp_path / "docs" / "plan.md").write_text("# The plan\n\n## Goals\n\nBack to [home](../README.md).\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    (tmp_path / "docs" / "milestones.yaml").write_text(
        "- {id: M0, title: Research, status: done, done_when: sources cited}\n"
        "- {id: M1, title: CAD, status: active, done_when: it builds}\n"
        "- {id: M2, title: Sim, status: next, done_when: it balances}\n")
    (tmp_path / "docs" / "decisions.yaml").write_text(
        "- {id: D1, date: '2026-10-25', title: Name, decision: Call it Bot, why: short, status: decided,\n"
        "   source: {kind: user, quote: call it Bot}}\n"
        "- {id: D2, date: '2026-10-25', title: MCU, decision: open, why: waiting, status: open}\n")
    (tmp_path / "exports" / "designs.json").write_text(json.dumps({"designs": [
        {"name": "Default", "file": "designs/default.json", "verdict": "warn", "summary": "**12 kg**",
         "metrics": [{"label": "mass", "value": 12.1, "unit": "kg", "estimate": True}], "checks": {"ok": 3, "warn": 1, "fail": 0}}]}))
    return tmp_path


def test_build_site_writes_index_and_pages(tmp_path):
    root = _project(tmp_path)
    s = site.build_site(root, CFG, "fallback")
    assert s["pages"] == 2 and s["milestones"] == 3 and s["decisions"] == 2 and s["designs"] == 1
    assert s["progress_pct"] == 33
    index = (root / "site" / "index.html").read_text()
    assert "A test robot" in index and "Private" in index and "1 / 3" in index
    assert index.index("MCU") < index.index("Name"), "open decisions come first"
    assert "“call it Bot”" in index and "<b>12 kg</b>" in index and "est." in index
    assert 'href="pages/readme-md.html"' in index
    assert 'href="../designer/"' in index and 'href="https://example.com/bot"' in index


def test_markdown_links_are_rewritten(tmp_path):
    root = _project(tmp_path)
    site.build_site(root, CFG, "fallback")
    readme = (root / "site" / "pages" / "readme-md.html").read_text()
    assert 'href="docs-plan-md.html#goals"' in readme, "links to rendered pages stay inside the site"
    assert 'src="../../docs/pic.png"' in readme, "other files point back into the project"
    assert 'href="../../tools/"' in readme
    assert '<pre class="mermaid">' in readme
    plan = (root / "site" / "pages" / "docs-plan-md.html").read_text()
    assert 'href="readme-md.html"' in plan and "<table>" in plan


def test_missing_sources_give_an_empty_site_not_an_error(tmp_path):
    s = site.build_site(tmp_path, {"pages": ["*.md"]}, "Empty")
    assert s["pages"] == 0 and s["progress_pct"] == 0
    assert "No milestones file yet." in (tmp_path / "site" / "index.html").read_text()


def test_site_rebuilds_when_a_source_changes(tmp_path):
    import os, time
    root = _project(tmp_path)
    cfg = site.site_config(CFG, "x")
    site.build_site(root, CFG, "x")
    assert not site._stale(root, cfg)
    later = time.time() + 5
    os.utime(root / "docs" / "milestones.yaml", (later, later))
    assert site._stale(root, cfg)


def test_serve_redirects_root_to_the_site(tmp_path):
    import threading, urllib.request
    root = _project(tmp_path)
    server, url = site.serve_site(root, CFG, "x", "127.0.0.1", 0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(url.replace("/site/", "/")) as r:
            assert r.geturl().endswith("/site/") and b"A test robot" in r.read()
    finally:
        server.shutdown()
        server.server_close()


def test_view_export_writes_meshes_and_manifest(tmp_path):
    cq = pytest.importorskip("cadquery")
    from cadagent.project import from_dict
    from cadagent.view import export_view
    (tmp_path / "exports").mkdir()
    for name, at in (("lid", (0, 0, 20)), ("base", (0, 0, 0))):
        cq.exporters.export(cq.Workplane().box(40, 30, 10).translate(at), str(tmp_path / "exports" / f"{name}.step"))
    (tmp_path / "exports" / "geometry-checks.json").write_text(json.dumps({"base": {}, "lid": {}, "ghost": {}}))
    project = from_dict(tmp_path, {"name": "box", "view": {"hidden": ["lid"], "colors": {"base": "#123456"}}})
    r = export_view(project)
    m = json.loads((tmp_path / "exports" / "view" / "view.json").read_text())
    assert r["parts"] == 2 and m["skipped"] == ["ghost"]
    by = {p["name"]: p for p in m["parts"]}
    assert by["base"]["color"] == "#123456" and by["lid"]["visible"] is False
    assert by["lid"]["bounds_mm"][2] == pytest.approx(15, abs=0.01)
    assert (tmp_path / "exports" / "view" / "lid.stl").stat().st_size > 84


def test_site_serves_the_kit_and_links_the_model(tmp_path):
    import threading, urllib.request
    root = _project(tmp_path)
    (root / "exports" / "view").mkdir()
    (root / "exports" / "view" / "view.json").write_text('{"parts": []}')
    server, url = site.serve_site(root, CFG, "x", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(url) as r:
            assert b"_cadagent/kit/viewer.html" in r.read()
        kit = url.replace("/site/", site.KIT_URL)
        with urllib.request.urlopen(kit + "viewer.html") as r:
            assert b"createViewer" in r.read()
        with urllib.request.urlopen(kit + "vendor/three/addons/loaders/STLLoader.js") as r:
            assert b"STLLoader" in r.read()
    finally:
        server.shutdown()
        server.server_close()


def test_default_nav_lists_the_project_pages(tmp_path):
    root = _project(tmp_path)
    (root / "preview").mkdir()
    (root / "preview" / "simulation.html").write_text("<html><head><title>Simulation · Bot</title></head><body></body></html>")
    (root / "docs" / "review.html").write_text("<html><head><title>Engineering review</title></head><body></body></html>")
    nav = site.default_nav(root, ["docs/review.html", "README.md", "docs/missing.html"], ["README.md"])
    assert [n["title"] for n in nav] == ["Overview", "Docs", "Engineering review", "Simulation"]
    assert nav[2]["href"] == "docs/review.html" and nav[3]["href"] == "preview/simulation.html"


def test_inject_nav_marks_the_current_page_and_respects_pages_with_their_own_bar():
    nav = [{"id": "overview", "title": "Overview", "href": "site/"}, {"id": "sim", "title": "Sim", "href": "preview/my sim.html"}]
    page = site.inject_nav(b"<html><body><h1>x</h1></body></html>", "/preview/my%20sim.html?x=1", nav)
    assert b'current: "sim"' in page and page.index(b"mountAppNav") < page.index(b"</body>")
    assert b'current: "overview"' in site.inject_nav(b"<body></body>", "/site/index.html", nav)
    own = b'<body><nav class="appnav"></nav></body>'
    assert site.inject_nav(own, "/x.html", nav) == own
    off = b'<head><meta name="cadagent-nav" content="off"></head><body></body>'
    assert site.inject_nav(off, "/x.html", nav) == off
    assert site.inject_nav(b"<p>no body tag", "/x.html", nav).endswith(b"</script>")
    assert site.inject_nav(b"<body></body>", "/x.html", []) == b"<body></body>"
    latin = "<html><body>café Müller</body></html>".encode("latin-1")
    assert site.inject_nav(latin, "/x.html", nav).startswith("<html><body>café Müller".encode("latin-1")), "bytes pass through"


def test_default_nav_normalises_and_dedupes_paths(tmp_path):
    root = _project(tmp_path)
    (root / "pages").mkdir()
    (root / "pages" / "x.html").write_text("<title>X</title>")
    nav = site.default_nav(root, ["./pages/x.html", "pages/x.html", "../outside.html"])
    assert [n["href"] for n in nav] == ["site/", "pages/x.html"]


def test_served_project_pages_get_the_top_bar(tmp_path):
    import threading, urllib.request
    root = _project(tmp_path)
    (root / "preview").mkdir()
    (root / "preview" / "index.html").write_text("<html><body><h1>Renders</h1></body></html>")
    (root / "preview" / "sim.html").write_text("<html><body><h1>Sim</h1></body></html>")
    cfg = dict(CFG, nav=[{"id": "overview", "title": "Overview", "href": "site/"}, {"id": "sim", "title": "Sim", "href": "preview/sim.html"}])
    server, url = site.serve_site(root, cfg, "x", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = url.replace("/site/", "/")
    try:
        with urllib.request.urlopen(base + "preview/sim.html") as r:
            body = r.read().decode()
            assert "mountAppNav" in body and 'current: "sim"' in body and "<h1>Sim</h1>" in body
        with urllib.request.urlopen(base + "preview/") as r:
            assert "mountAppNav" in r.read().decode(), "a folder's index.html gets the bar too"
        with urllib.request.urlopen(url) as r:
            assert r.read().decode().count('class="appnav"') == 1, "the site has its bar built in, not twice"
        with urllib.request.urlopen(base + "site/nav.json") as r:
            assert json.loads(r.read())["nav"][1]["href"] == "preview/sim.html"
        assert "mountAppNav" not in (root / "preview" / "sim.html").read_text(), "files on disk are left alone"
        head = urllib.request.Request(base + "preview/sim.html", method="HEAD")
        with urllib.request.urlopen(head) as r, urllib.request.urlopen(base + "preview/sim.html") as g:
            assert r.headers["Content-Length"] == g.headers["Content-Length"] == str(len(g.read()))
        with urllib.request.urlopen(base + site.KIT_URL.lstrip("/") + "viewer.html") as r:
            assert "mountAppNav" in r.read().decode(), "the web kit's pages get the bar too"
    finally:
        server.shutdown()
        server.server_close()


def test_default_nav_picks_up_a_report_written_while_serving(tmp_path):
    import threading, time, urllib.request
    root = _project(tmp_path)
    auto = lambda: site.default_nav(root, [], CFG["pages"])  # noqa: E731
    server, url = site.serve_site(root, {k: v for k, v in CFG.items()}, "x", "127.0.0.1", 0, auto)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(url + "nav.json") as r:
            assert [n["title"] for n in json.loads(r.read())["nav"]] == ["Overview", "Docs"]
        (root / "preview").mkdir()
        (root / "preview" / "simulation.html").write_text("<title>Simulation</title><body></body>")
        time.sleep(2.1)
        with urllib.request.urlopen(url + "nav.json") as r:
            assert json.loads(r.read())["nav"][-1]["href"] == "preview/simulation.html"
        with urllib.request.urlopen(url) as r:
            assert 'class="appnav"' in r.read().decode(), "the site's own bar uses the default nav too"
    finally:
        server.shutdown()
        server.server_close()
