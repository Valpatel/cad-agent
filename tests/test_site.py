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
