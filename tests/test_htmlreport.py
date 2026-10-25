"""canonical_status never upgrades to pass; render_page shows every row and the honesty note."""

from __future__ import annotations

import html
import json

import pytest

from cadagent import htmlreport, report
from cadagent.project import load_project

from .test_report import CHECKS, make_project

@pytest.mark.parametrize("raw", ["pass", "PASSED", " ok ", "true", True, "green"])
def test_pass_aliases(raw):
    assert htmlreport.canonical_status(raw) == "pass"

@pytest.mark.parametrize("raw", ["fail", "Failed", "error", "false", False, "red"])
def test_fail_aliases(raw):
    assert htmlreport.canonical_status(raw) == "fail"

@pytest.mark.parametrize("raw", ["skip", "SKIPPED", "n/a", "none"])
def test_skip_aliases(raw):
    assert htmlreport.canonical_status(raw) == "skip"

@pytest.mark.parametrize("raw", [None, "", "yes", "passing", "unknown", 1, 0, [], {}, "pending"])
def test_unknown_status_is_a_failure(raw):
    assert htmlreport.canonical_status(raw) == "fail"

def test_summarize_counts_unknown_status_as_fail():
    results = {"features": [{"checks": [{"status": "pass"}, {"status": "maybe"}, {}, {"status": "skip"}]}]}
    assert report.summarize(results) == {"pass": 1, "fail": 2, "skip": 1}
    assert len(report.failures(results)) == 2

def test_rendered_page_has_every_row_and_the_honesty_note(tmp_path):
    root = make_project(tmp_path, checks_yaml=CHECKS)
    (root / "exports" / "fit.json").write_text(json.dumps({"pass": True}))
    (root / "exports" / "vague.json").write_text(json.dumps({"pass": "yes"}))
    (root / "exports" / "multi.json").write_text(json.dumps({"a": {"ok": True}, "b": False}))
    results = report.collect(load_project(root))
    page = report.render_html(results)
    assert page.startswith("<!doctype html>")
    rows = [c for f in results["features"] for c in f["checks"]]
    assert page.count('<div class="check ') == len(rows)
    for feature in results["features"]:
        assert html.escape(feature["feature_title"]) in page
    for check in rows:
        assert html.escape(check["name"]) in page
        if check.get("message"):
            assert html.escape(check["message"]) in page
    assert report.HONESTY_NOTE in page
    for value in list(results["header_meta"].values()) + list(results["footer_meta"].values()):
        assert html.escape(value) in page
    assert '<img loading="lazy" src="../preview/part-box.png"' in page
    assert 'href="../exports/fit.json"' in page
    assert "not a boolean" in page

def test_evidence_kinds_links_and_escaping():
    results = {
        "title": "T <&>",
        "features": [{"feature_id": "f", "feature_title": "F", "checks": [
            {"name": "shot", "status": "pass", "evidence": {"type": "screenshot", "path": "a b.png", "title": "A"}},
            {"name": "link", "status": "pass", "evidence": {"type": "link", "url": "x.json", "label": "X"},
             "links": [{"url": "notes.html", "label": "Notes"}]},
            {"name": "log", "status": "fail", "evidence": {"type": "log", "content": "trace <1>"}},
            {"name": "<script>alert(1)</script>", "status": "weird", "error": "boom"},
        ]}],
    }
    page = htmlreport.render_page(results, alerts=[{"title": "Heads up", "body": "careful"}],
                                  extra_panels=["<p id=extra>extra</p>"])
    assert "<title>T &lt;&amp;&gt;</title>" in page
    assert 'src="a b.png"' in page and 'alt="A"' in page
    assert '<a href="x.json">X</a>' in page and '<a href="notes.html">Notes</a>' in page
    assert "<pre>trace &lt;1&gt;</pre>" in page and "<pre>boom</pre>" in page
    assert "<script>alert(1)</script>" not in page
    assert page.count('<span class="badge fail">fail</span>') == 4   # two rows, the feature, the verdict
    assert "Heads up" in page and "careful" in page
    assert page.index("<p id=extra>") > page.index("&lt;script&gt;")

def test_empty_results_still_render():
    page = htmlreport.render_page({})
    assert "<title>CAD verification</title>" in page and "</html>" in page
