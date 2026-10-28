"""Review pages of the site (plan T15): the section review, the requirements table and the gates page with the
connectivity graph, built from the gate-bench fixture project.

Core CI builds them from ``fixtures/gate_bench/site_snapshot/`` (the clean bench's exports, refreshed by
``fixtures/gate_bench/site_snapshot.py``), so no CAD kernel is needed; the last test runs the real gates on a
seeded defect and needs CadQuery.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import urllib.request
from pathlib import Path

import pytest

from cadagent import dotsvg, site, site_review
from cadagent.cli import main
from cadagent.links import missing_links

BENCH = Path(__file__).resolve().parent / "fixtures" / "gate_bench"
SNAPSHOT = BENCH / "site_snapshot"
REGEN = "refresh it with `python tests/fixtures/gate_bench/site_snapshot.py`"


@pytest.fixture
def bench(tmp_path):
    """A copy of the gate-bench project with the clean bench's exports in place."""
    dst = tmp_path / "gate_bench"
    shutil.copytree(BENCH, dst, ignore=shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site"))
    root = dst / "project"
    shutil.copytree(SNAPSHOT, root / "exports")
    return root


def _site(root: Path) -> Path:
    assert main(["site", "--project", str(root)]) == 0
    return root / "site"


def _read(root: Path, rel: str) -> str:
    return (root / "site" / rel).read_text()


def _links_ok(root: Path) -> None:
    pages = sorted((root / "site").rglob("*.html"))
    assert pages
    assert missing_links(pages, root) == []


def _json(path: Path):
    return json.loads(path.read_text())


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data))


# ------------------------------------------------------------------------------------------------- the clean bench

def test_pages_build_from_the_fixture_and_every_link_resolves(bench):
    out = _site(bench)
    review = out / "review"
    names = sorted(p.name for p in review.iterdir())
    assert names == ["connectivity.svg", "gates.html", "index.html", "requirements.html", "section-s-arm.html",
                     "section-s-bracket.html", "section-s-frame.html", "section-s-store.html"]
    _links_ok(bench)

    index = _read(bench, "review/index.html")
    for sid in ("S-arm", "S-bracket", "S-frame", "S-store"):
        assert f'href="section-{sid.lower()}.html"' in index
    assert index.count('<span class="pill gated">gated</span>') == 4, f"every clean section is gated; {REGEN}"
    assert "No lint findings." in index and "0 / 4</b><span>sections signed off" in index

    overview = _read(bench, "index.html")
    assert 'id="design-review-by-section"' in overview and 'href="review/gates.html"' in overview
    assert 'href="review/section-s-store.html"' in overview and 'href="review/requirements.html"' in overview
    assert '<a class="stat" href="review/gates.html"><b>6 / 6</b>' in overview
    nav = _json(out / "nav.json")["nav"]
    assert [n["title"] for n in nav[:4]] == ["Overview", "Review", "Requirements", "Gates"]
    assert 'class="tab on" href="../../site/review/gates.html"' in _read(bench, "review/gates.html")


def test_requirements_table(bench):
    _site(bench)
    page = _read(bench, "review/requirements.html")
    for rid, text, sec in (("R1", "Holds eight balls", "s-store"), ("R2", "The arm lifts 40 deg", "s-arm"),
                           ("R3", "Every part is held", "s-bracket")):
        row = page.split(f'id="req-{rid.lower()}"')[1].split("</tr>")[0]
        assert text in row and '<span class="pill verified">verified</span>' in row, REGEN
        assert f'href="section-{sec}.html"' in row
    assert 'href="gates.html#gate-containment"' in page and "gate:containment · pass" in page
    assert "derived: Holds eight balls" not in page and "waived" not in page.split("<table>")[1]


def test_section_page_shows_cards_decisions_checks_and_interfaces(bench):
    _site(bench)
    page = _read(bench, "review/section-s-store.html")
    assert "Hold eight loose balls under a screwed lid" in page               # purpose
    assert 'id="part-hopper"' in page and 'id="part-ball"' in page and 'id="part-insert-3"' in page
    assert "Open box that holds the eight balls" in page                       # function
    assert "PETG, FDM, print axis +Z, min wall 2.4 mm" in page
    assert "snap-fit lid" in page and "rejected: the lid must stay on when the arm shakes the bench" in page
    assert "Square hopper with corner posts for the lid screws" in page and "Why: posts give the inserts" in page
    assert '<a class="pill pass" href="gates.html#gate-containment"' in page
    assert 'id="if-i-lid"' in page and "heat-set bore" in page                  # interfaces of its parts
    assert 'class="ladder"' in page and '<li class="on at">gated</li>' in page
    assert "8 × ball in hopper_cavity (free)" in page and "1 × m3_shcs to insert_0 via I-thread-0" in page
    assert "No gate or lint finding names this section" in page
    assert "No review packet for this section yet" in page
    assert 'href="../../dossier/sections/store.yaml"' in page


def test_gates_page_rows_and_the_connectivity_svg(bench):
    _site(bench)
    page = _read(bench, "review/gates.html")
    table = page.split('id="summary"')[1].split("</table>")[0]
    for g in ("connectivity", "containment", "fasteners", "motion", "assembly", "wall", "dossier-lint"):
        assert f"<b>{g}</b>" in table
    assert table.count('<span class="pill pass">pass</span>') == 7, REGEN
    assert 'href="../../exports/gates/connectivity.md"' in table and 'href="../../exports/gates/connectivity.dot"' in table
    assert "motion.dot" not in table, "only files that exist are linked"
    graph = page.split('id="connectivity-graph"')[1]
    assert "<svg" in graph and "hinge_block" in graph and "static frame" in graph and 'href="connectivity.svg"' in graph
    svg = _read(bench, "review/connectivity.svg")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert 'id="gate-assembly"' in page and "Assumptions" in page


def test_a_project_without_dossier_or_gates_sees_no_change(tmp_path):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: plain\n  title: Plain\n")
    _site(tmp_path)
    assert not (tmp_path / "site" / "review").exists()
    assert "design-review" not in _read(tmp_path, "index.html")
    assert [n["title"] for n in _json(tmp_path / "site" / "nav.json")["nav"]] == ["Overview"]


def test_a_gates_only_project_gets_the_gates_page(bench):
    cfg = bench / "cad-agent.yaml"
    cfg.write_text(cfg.read_text().replace("  dossier: dossier/project.yaml\n", ""))
    _site(bench)
    assert "has no dossier" in _read(bench, "review/index.html")
    assert "<b>connectivity</b>" in _read(bench, "review/gates.html")
    assert not list((bench / "site" / "review").glob("section-*.html"))
    assert [n["title"] for n in _json(bench / "site" / "nav.json")["nav"]] == ["Overview", "Gates"]
    _links_ok(bench)


# ------------------------------------------------------------------------------------------------- failing and stale

def _fail_bracket(root: Path) -> None:
    """What the bracket_hovers seed gives: a failing connectivity finding naming the bracket, with its witness, and
    the bracket's section back at built."""
    path = root / "exports" / "gates" / "connectivity.json"
    v = _json(path)
    finding = {"id": "interface:I-bracket", "status": "fail",
               "message": "declared interface I-bracket (base / bracket) is not realised: apart by 0.500 mm",
               "parts": ["base", "bracket"],
               "evidence": {"relation": {"a": "base", "b": "bracket", "state": "apart", "gap_mm": 0.5,
                                         "witness": {"point_a": [94.0, 20.0, 7.0], "point_b": [94.0, 20.0, 7.5]}}}}
    v["findings"] = [finding]
    v["checks"].append(finding)
    v.update({"pass": False, "status": "fail"})
    v["counts"]["fail"] = 1
    _dump(path, v)
    status_path = root / "exports" / "dossier-status.json"
    st = _json(status_path)
    for pid in ("bracket", "base"):
        row = st["parts"][pid]
        row["status"] = "built"
        row["blocked_by"] = ["gate:connectivity fail (failing: interface:I-bracket)"]
        for c in row["checks"]:
            if c["id"] == "gate:connectivity":
                c.update(status="fail", message="failing: interface:I-bracket")
    st["sections"]["S-bracket"]["status"] = "built"
    st["requirements"]["R3"]["status"] = "failed"
    st["requirements"]["R3"]["checks"][0].update(status="fail")
    st["pass"] = False
    st["counts"]["error"] = 1
    st["findings"] = [{"code": "section-below-gated", "severity": "error", "message": "section 'S-bracket' is built",
                       "file": "dossier/sections/bracket.yaml", "line": 2, "item": "S-bracket", "parts": ["bracket"]}]
    _dump(status_path, st)


def test_failing_findings_and_witnesses_reach_the_sections_that_own_the_parts(bench):
    _fail_bracket(bench)
    _site(bench)
    page = _read(bench, "review/section-s-bracket.html")
    findings = page.split('id="findings"')[1].split('id="packet"')[0]
    assert "interface:I-bracket" in findings and "apart by 0.500 mm" in findings
    assert "relation.gap_mm 0.5" in findings and "relation.witness.point_b (94, 20, 7.5)" in findings
    assert "section-below-gated" in findings and 'href="../../dossier/sections/bracket.yaml"' in findings
    assert 'href="section-s-frame.html#part-base"' in findings, "a part of another section links to its card"
    assert '<li class="on at">built</li>' in page and "The dossier lint fails" in page
    assert "interface:I-bracket" in _read(bench, "review/section-s-frame.html"), "base is named too"
    assert "interface:I-bracket" not in _read(bench, "review/section-s-store.html")
    gates = _read(bench, "review/gates.html")
    assert '<b>connectivity</b></td><td><span class="pill fail">fail</span>' in gates
    table = gates.split('id="summary"')[1].split("</table>")[0]
    assert table.count('<span class="pill pass">pass</span>') == 5      # the other gates; the lint fails
    assert '<span class="pill failed">failed</span>' in _read(bench, "review/section-s-bracket.html")  # R3
    _links_ok(bench)


def test_stale_and_missing_verdicts_are_shown(bench):
    geo = bench / "exports" / "dossier-geometry.json"
    record = _json(geo)
    record["parts"]["bracket"]["sha256"] = "0" * 64      # the geometry changed since the gates ran
    _dump(geo, record)
    (bench / "exports" / "gates" / "motion.json").unlink()
    _site(bench)
    gates = _read(bench, "review/gates.html")
    assert '<b>motion</b></td><td><span class="pill missing">missing</span>' in gates
    assert '<b>wall</b></td><td><span class="pill stale">stale</span>' in gates
    assert "this graph is from an earlier build" in gates


def test_review_record_stale_badge_and_review_packet(bench):
    st_path = bench / "exports" / "dossier-status.json"
    st = _json(st_path)
    reviews = bench / "dossier" / "reviews"
    reviews.mkdir()
    record = "dossier/reviews/S-arm-2026-10-28.json"
    _dump(bench / record, {"schema": "cad-agent.review/1", "section": "S-arm", "date": "2026-10-28", "actor": "rev-1",
                           "signed_off": False, "hashes": {},
                           "findings": [{"severity": "major", "render": "iso.png", "text": "the stop has no fillet"},
                                        {"severity": "minor", "text": "caption the pin"}]})
    sec = st["sections"]["S-arm"]
    sec.update(status="reviewed", review={"record": record, "date": "2026-10-28", "actor": "rev-1",
                                          "signed_off": False, "findings": 2})
    st["parts"]["arm"]["invalidated"] = {"record": "dossier/reviews/S-arm-2026-10-01.json", "date": "2026-10-01",
                                         "signed_off": True, "changed": ["arm"]}
    _dump(st_path, st)
    packet = bench / "exports" / "review" / "S-arm"
    packet.mkdir(parents=True)
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
    (packet / "iso.png").write_bytes(png)
    (packet / "section-cut.png").write_bytes(png)
    _dump(packet / "manifest.json", {      # the shape of cad-agent.review-packet/1 (docs/review-packet.md, T10)
        "schema": "cad-agent.review-packet/1", "section": {"id": "S-arm"},
        "parts": {"arm": {"sha256": "f" * 64}, "pin": {"sha256": st["parts"]["pin"]["sha256"]}},
        "views": [{"id": "solid-iso", "kind": "solid", "file": "iso.png", "caption": "S-arm iso", "sha256": "abc123"},
                  {"id": "cut-joint-I-pin-arm", "kind": "cut", "file": "section-cut.png", "caption": "through the pin",
                   "note": "a plane containing the joint axis"},
                  {"id": "opposite iso", "kind": "solid", "file": "missing.png"},
                  {"id": "exploded", "kind": "exploded", "file": None}],
        "checklist": {"questions": [{"id": "q1", "question": "Is the pin seated in both cheeks?",
                                     "views": ["cut-joint-I-pin-arm"]}]},
        "not_rendered": [{"what": "joint I12", "why": "planar joints have no range to pose"}]})
    _site(bench)
    page = _read(bench, "review/section-s-arm.html")
    assert "stale: geometry changed since the review of 2026-10-01" in page
    assert '2 finding(s) open' in page and 'href="../../dossier/reviews/S-arm-2026-10-28.json"' in page
    pk = page.split('id="packet"')[1]
    assert 'src="../../exports/review/S-arm/iso.png"' in pk and "through the pin" in pk
    iso = pk.split("<b>solid-iso</b>")[1].split("</figure>")[0]
    assert "the stop has no fillet" in iso, "a reviewer finding sits beside the image it names"
    assert "caption the pin" in pk.split("Reviewer findings")[1]
    assert "Missing image: missing.png" in pk
    assert "rendered from older geometry (arm changed)" in pk, "pin's hash matches, arm's does not"
    cut = pk.split("<b>cut-joint-I-pin-arm</b>")[1].split("</figure>")[0]
    assert "a plane containing the joint axis" in cut and "Is the pin seated in both cheeks?" in cut
    assert "Not rendered in this packet" in pk and "planar joints have no range to pose" in pk
    _links_ok(bench)


def test_status_file_missing_or_older_than_the_yaml(bench):
    status = bench / "exports" / "dossier-status.json"
    sec = bench / "dossier" / "sections" / "arm.yaml"
    os.utime(sec, (status.stat().st_mtime + 60, status.stat().st_mtime + 60))
    _site(bench)
    assert "The dossier changed after the status file was written" in _read(bench, "review/index.html")
    status.unlink()
    _site(bench)
    index = _read(bench, "review/index.html")
    assert "No dossier status yet" in index and 'href="section-s-arm.html"' in index
    assert "Status not computed yet" in _read(bench, "review/section-s-arm.html")
    assert "Hold eight loose balls" in _read(bench, "review/section-s-store.html"), "the words still come from the YAML"
    _links_ok(bench)


def test_a_removed_section_loses_its_page(bench):
    _site(bench)
    st_path = bench / "exports" / "dossier-status.json"
    st = _json(st_path)
    del st["sections"]["S-frame"]
    _dump(st_path, st)
    (bench / "dossier" / "sections" / "frame.yaml").unlink()
    _site(bench)
    assert not (bench / "site" / "review" / "section-s-frame.html").exists()


# ------------------------------------------------------------------------------------------------- serving

def test_serve_rebuilds_on_a_new_status_and_shows_verdicts_as_text(bench):
    from cadagent.project import load_project
    project = load_project(bench)
    server, url = site.serve_site(bench, project.site, project.title, "127.0.0.1", 0,
                                  gates_exports=project.exports_dir, review_project=project)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = url.replace("/site/", "/")
    try:
        with urllib.request.urlopen(base + "exports/gates/connectivity.md") as r:
            assert r.headers["Content-Type"].startswith("text/plain") and b"# Gate: connectivity" in r.read()
        _fail_bracket(bench)
        later = (bench / "site" / "index.html").stat().st_mtime + 5
        os.utime(bench / "exports" / "dossier-status.json", (later, later))
        with urllib.request.urlopen(url + "review/section-s-bracket.html") as r:
            assert b"interface:I-bracket" in r.read(), "the review pages rebuild when the status file changes"
    finally:
        server.shutdown()
        server.server_close()


# ------------------------------------------------------------------------------------------------- DOT to SVG

DOT = """
// a comment
graph g {
  graph [rankdir=LR]; node [shape=box, style=rounded];
  subgraph cluster_0 { label="static frame"; color=gray60;
    "base" [peripheries=2]; a; "b#1" [style="rounded,dashed"]; s [shape=ellipse]; }
  subgraph cluster_1 { label="body arm"; arm [color=red, fontcolor=red]; }
  base -- a -- "b#1";
  a -- s [style=bold, label="m3 (axis)"];
  base -- a [style=dotted, label="in cavity"];
  arm -- a [style=dashed, color=blue, label="I9 revolute"];
  /* block comment */ x -- y;
}
"""


def test_parse_dot_reads_the_subset_the_toolkit_writes():
    g = dotsvg.parse_dot(DOT)
    assert list(g.clusters) == ["cluster_0", "cluster_1"] and g.clusters["cluster_0"]["label"] == "static frame"
    assert g.node_cluster["b#1"] == "cluster_0" and g.node_cluster["arm"] == "cluster_1" and g.node_cluster["x"] == ""
    assert g.nodes["base"]["peripheries"] == "2" and g.nodes["a"]["shape"] == "box"
    assert g.nodes["b#1"]["style"] == "rounded,dashed" and g.nodes["s"]["shape"] == "ellipse"
    assert [(a, b) for a, b, _ in g.edges] == [("base", "a"), ("a", "b#1"), ("a", "s"), ("base", "a"), ("arm", "a"),
                                              ("x", "y")]
    assert g.edges[2][2] == {"style": "bold", "label": "m3 (axis)"} and not g.directed
    assert dotsvg.parse_dot("digraph { a -> b }").directed
    with pytest.raises(ValueError):
        dotsvg.parse_dot("graph { a -- ")
    with pytest.raises(ValueError):
        dotsvg.parse_dot("nonsense { }")


def test_layout_layers_from_the_grounded_node_and_keeps_clusters_apart():
    g = dotsvg.parse_dot(DOT)
    boxes, clusters, w, h = dotsvg.layout(g)
    assert boxes["base"].x < boxes["a"].x < boxes["b#1"].x, "layers run left to right from the grounded node"
    c0, c1 = clusters["cluster_0"], clusters["cluster_1"]
    for n in ("base", "a", "b#1", "s"):
        b = boxes[n]
        assert c0.x <= b.x and b.x + b.w <= c0.x + c0.w and c0.y <= b.y and b.y + b.h <= c0.y + c0.h
    assert c1.y >= c0.y + c0.h and boxes["arm"].y > c1.y
    assert boxes["y"].y > c1.y + c1.h, "nodes outside every cluster come last"
    assert 0 < max(b.x + b.w for b in boxes.values()) <= w and 0 < max(b.y + b.h for b in boxes.values()) <= h
    assert dotsvg.layout(dotsvg.parse_dot(DOT))[0] == boxes, "deterministic"


def test_dot_to_svg_without_graphviz(monkeypatch):
    monkeypatch.setattr(dotsvg.shutil, "which", lambda name: None)
    svg, engine = dotsvg.dot_to_svg(DOT, title="g")
    assert engine == "python" and svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "<title>base</title>" in svg and "static frame" in svg and "I9 revolute" in svg
    assert 'stroke-dasharray="1.5 3.5"' in svg and "var(--fail,#d1453b)" in svg and "<ellipse" in svg
    assert svg.count(">in cavity</text>") == 1, "a label repeated on edges into one node is drawn once"
    svg2, engine2 = dotsvg.dot_to_svg(DOT, engine="graphviz")
    assert engine2 == "python", "graphviz falls back when it is not installed"
    with pytest.raises(ValueError):
        dotsvg.dot_to_svg(DOT, engine="neato")


def test_dot_to_svg_draws_the_bench_graph():
    svg, _ = dotsvg.dot_to_svg((SNAPSHOT / "gates" / "connectivity.dot").read_text(), engine="python")
    for node in ("base", "hopper", "ball#7", "screw_3", "arm"):
        assert f"<title>{node}</title>" in svg
    assert len(re.findall(r"<path [^>]*><title>", svg)) == len(dotsvg.parse_dot((SNAPSHOT / "gates" / "connectivity.dot").read_text()).edges)


def test_witness_summary_picks_measures_and_points():
    ev = {"islands": [{"nearest": {"part": "bracket", "gap_mm": 0.5, "point_a": [94.0, 20.0, 7.5], "group": "static"}}]}
    s = site_review.witness_summary(ev)
    assert "islands[0].nearest.gap_mm 0.5" in s and "islands[0].nearest.point_a (94, 20, 7.5)" in s
    assert "group" not in s


# ------------------------------------------------------------------------------------------------- end to end (CAD)

def test_a_seeded_defect_reaches_its_section_page_through_the_cli(tmp_path):
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    dst = tmp_path / "gate_bench"
    shutil.copytree(BENCH, dst, ignore=shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site"))
    root = dst / "project"
    (root / "cad" / "parameters.json").write_text(json.dumps({"seed": "bracket_hovers"}))
    assert main(["gates", "--project", str(root), "--build", "--jobs", "2"]) == 1
    _site(root)
    page = _read(root, "review/section-s-bracket.html")
    findings = page.split('id="findings"')[1].split('id="packet"')[0]
    assert "connect:static" in findings and "interface:I-bracket" in findings and "gap_mm 0.5" in findings
    assert '<li class="on at">built</li>' in page
    gates = _read(root, "review/gates.html")
    assert '<b>connectivity</b></td><td><span class="pill fail">fail</span>' in gates
    assert "static frame (not grounded)" in gates
    _links_ok(root)
