"""Catalogue content for outside entries (#106): every upstream in upstreams/registry.yaml and every library and
benchmark in research/landscape.json has a plain one-line `what` (what the project is and does, from its own README or
site) and `areas` placing it in the topic tree of docs/areas.yaml. Our assessment stays in `notes`, `status` and
`policy`; `what` is the line the catalogue shows first, so it must not just repeat the notes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MAX_WHAT = 120
MAX_AREAS = 3

# Entries with no area yet, each with the reason. Keep it short: add an area to docs/areas.yaml rather than grow this.
NO_AREA: dict[str, str] = {}


@pytest.fixture(scope="module")
def landscape():
    return json.loads((ROOT / "research" / "landscape.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(landscape):
    """(kind, entry, notes) for every outside entry the catalogue shows. An upstream's notes live in landscape.json."""
    upstreams = yaml.safe_load((ROOT / "upstreams" / "registry.yaml").read_text(encoding="utf-8"))
    notes = {p["name"]: p.get("notes", "") for p in landscape["projects"]}
    out = [("upstream", u, notes.get(u["name"], "")) for u in upstreams]
    out += [("library", lib, lib.get("notes", "")) for lib in landscape["libraries"]]
    out += [("benchmark", b, b.get("notes", "")) for b in landscape["benchmarks"]]
    return out


@pytest.fixture(scope="module")
def slugs():
    """Domain and area slugs: an entry names an area, or a domain when no area fits. Topics are too fine for cards."""
    tree = yaml.safe_load((ROOT / "docs" / "areas.yaml").read_text(encoding="utf-8"))
    return {d["slug"] for d in tree["domains"]} | {a["slug"] for d in tree["domains"] for a in d.get("areas", [])}


def test_every_landscape_project_is_a_registry_upstream(entries, landscape):
    """The catalogue reads `what` for projects from the registry, so a landscape project missing there has none."""
    upstreams = {e["name"] for kind, e, _ in entries if kind == "upstream"}
    missing = [p["name"] for p in landscape["projects"] if p["name"] not in upstreams]
    assert not missing, f"landscape projects not in upstreams/registry.yaml: {missing}"


def test_every_entry_has_a_plain_one_line_what(entries):
    problems = []
    for kind, e, notes in entries:
        what = e.get("what")
        where = f"{kind} {e['name']}"
        if not isinstance(what, str) or not what.strip():
            problems.append(f"{where}: no `what`")
            continue
        if what != what.strip() or "\n" in what:
            problems.append(f"{where}: `what` must be one line without surrounding spaces")
        if len(what) > MAX_WHAT:
            problems.append(f"{where}: `what` is {len(what)} characters (at most {MAX_WHAT})")
        if what.endswith("."):
            problems.append(f"{where}: `what` ends with a period")
        if notes and what.strip().casefold() == notes.strip().casefold():
            problems.append(f"{where}: `what` repeats its notes; say what the project is, keep the assessment in notes")
    assert not problems, "\n".join(problems)


def test_every_area_slug_exists_in_the_topic_tree(entries, slugs):
    problems = []
    for kind, e, _ in entries:
        areas = e.get("areas", [])
        where = f"{kind} {e['name']}"
        if not isinstance(areas, list) or not all(isinstance(a, str) for a in areas):
            problems.append(f"{where}: `areas` must be a list of slugs")
            continue
        if len(areas) > MAX_AREAS or len(set(areas)) != len(areas):
            problems.append(f"{where}: `areas` takes one to {MAX_AREAS} different slugs, got {areas}")
        unknown = [a for a in areas if a not in slugs]
        if unknown:
            problems.append(f"{where}: {unknown} are not domain or area slugs in docs/areas.yaml")
    assert not problems, "\n".join(problems)


def test_every_entry_has_an_area_or_a_stated_reason(entries):
    names = {e["name"] for _, e, _ in entries}
    unplaced = [f"{kind} {e['name']}" for kind, e, _ in entries if not e.get("areas") and e["name"] not in NO_AREA]
    assert not unplaced, f"no `areas` (add one, or list the entry in NO_AREA with its reason): {unplaced}"
    stale = [n for n in NO_AREA if n not in names or any(e["name"] == n and e.get("areas") for _, e, _ in entries)]
    assert not stale, f"NO_AREA lists entries that are gone or now have areas: {stale}"
    assert len(NO_AREA) <= 5 and all(r.strip() for r in NO_AREA.values()), "NO_AREA must stay short, each with a reason"
