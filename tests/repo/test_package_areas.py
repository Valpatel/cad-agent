"""Code and topic tree in step (#121): each domain package holds one domain of docs/areas.yaml.

* every module in a domain package is listed under that domain (an ``api:`` entry);
* every ``api:`` and ``uses:`` entry imports, at its current path;
* no domain package holds a module that docs/areas.yaml places in another domain (``api:`` is one home per module);
* a ``uses:`` entry (a module a node relies on from another domain) is not one the node could list in ``api:``.

The checks take a package folder and a tree, so the tests at the end run them on planted mistakes too: each rule is
shown to catch the mistake it is for, and only that one."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

import cadagent
from cadagent import _moved

from .test_areas import nodes, read_tree

PKG = Path(cadagent.__file__).parent
# Each domain package and where in the tree it lives: a domain, and for the practice domain's two packages, its areas.
HOME = {
    "mechanical": ("mechanical", None),
    "manufacturing": ("manufacturing", None),
    "thermal": ("thermal", None),
    "simulation": ("simulation", None),
    "electrical": ("electrical", None),
    "review": ("practice", {"design-process", "review-and-evidence"}),
    "publish": ("practice", {"publishing"}),
}


def home_name(package: str) -> str:
    domain, areas = HOME[package]
    return " or ".join(f"{domain}/{a}" for a in sorted(areas)) if areas else domain


def owner(module: str):
    """(domain package, the package's own module or subpackage) for an import path inside a domain package:
    ``cadagent.review.gates.motion`` -> ``("review", "cadagent.review.gates")``; ``(None, None)`` for the shared
    core."""
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "cadagent" or parts[1] not in HOME:
        return None, None
    return parts[1], ".".join(parts[:3])


def placements(tree, key="api") -> dict:
    """{entry of `key`: {(domain, area)}}; an area's topics count as the area, cross-cutting entries as
    ("cross_cutting", None)."""
    out: dict = {}
    for module in tree.get("cross_cutting", {}).get(key, []):
        out.setdefault(module, set()).add(("cross_cutting", None))
    for path, node in nodes(tree):
        for module in node.get(key, []):
            out.setdefault(module, set()).add((path[0], path[1] if len(path) > 1 else None))
    return out


def at_home(package: str, where) -> bool:
    domain, areas = HOME[package]
    return where[0] == domain and (areas is None or where[1] in areas)


def package_modules(root: Path) -> dict:
    """{domain package: its modules and subpackages}, read from the folders (nothing is imported)."""
    return {p: sorted(f"cadagent.{p}.{m.name}" for m in pkgutil.iter_modules([str(root / p)])
                      if not m.name.startswith("_"))
            for p in HOME}


def unlisted(root: Path, tree) -> list:
    """Rule 1: modules of a domain package that its domain does not list."""
    listed: dict = {}
    for entry, where in placements(tree).items():
        package, module = owner(entry)
        if package:
            listed.setdefault(module, set()).update(w for w in where if at_home(package, w))
    return [f"{m}: list it under {home_name(p)} in docs/areas.yaml (api:)"
            for p, modules in package_modules(root).items() for m in modules if not listed.get(m)]


def unimportable(tree, load=importlib.import_module) -> list:
    """Rule 2: api and uses entries that do not import, or name an old path (which imports, with a warning, until a
    release that the CHANGELOG announces a minor release ahead; cadagent._moved)."""
    bad = []
    for entry in sorted(set(placements(tree)) | set(placements(tree, "uses"))):
        if _moved.new_name(entry):
            bad.append(f"{entry}: an old path; name {_moved.new_name(entry)}")
            continue
        try:
            load(entry)
        except ImportError as e:
            bad.append(f"{entry}: does not import ({e})")
    return bad


def misplaced(tree) -> list:
    """Rule 3: api entries for a domain package's module that the tree places outside that package's domain."""
    bad = []
    for entry, where in sorted(placements(tree).items()):
        package, _ = owner(entry)
        if not package:
            continue
        for domain, area in sorted(where, key=str):
            if not at_home(package, (domain, area)):
                there = next((p for p in HOME if at_home(p, (domain, area))), None)
                move = (f"or move it to cadagent.{there}" if there else
                        "or move it to the shared core" if domain == "cross_cutting" else "no package holds that area")
                bad.append(f"{entry} lives in cadagent.{package} ({home_name(package)}) but is placed under "
                           f"{domain}{'/' + area if area else ''}: list it under its own domain only "
                           f"(an area elsewhere that relies on it names it in its uses: list), {move}")
    return bad


def misused(tree) -> list:
    """Rule 4: uses entries that are at home where they are named, so they belong in that node's api. (One that is in
    the node's api already is test_areas' finding, not repeated here.)"""
    bad = []
    for path, node in nodes(tree):
        where = (path[0], path[1] if len(path) > 1 else None)
        for entry in node.get("uses", []):
            package, _ = owner(entry)
            if package and at_home(package, where) and entry not in node.get("api", []):
                bad.append(f"{entry} is {'/'.join(path)}'s own domain's module ({home_name(package)}): list it under "
                           f"api, not uses")
    return bad


@pytest.fixture(scope="module")
def tree():
    return read_tree()


def test_every_domain_package_is_in_the_layout():
    folders = {p.name for p in PKG.iterdir() if (p / "__init__.py").is_file()} - {"geometry", "formulas"}  # shared core
    assert folders == set(HOME), f"domain packages {sorted(folders ^ set(HOME))}: add them to HOME (and to the tree)"
    domains = {d["slug"]: {a["slug"] for a in d.get("areas", [])} for d in read_tree()["domains"]}
    for package, (domain, areas) in HOME.items():
        assert domain in domains and (areas or set()) <= domains[domain], f"{package}: {domain} {areas} not in the tree"


def test_every_module_in_a_domain_package_is_listed_under_its_domain(tree):
    missing = unlisted(PKG, tree)
    assert not missing, "\n".join(missing)


def test_every_api_entry_imports(tree):
    bad = unimportable(tree)
    assert not bad, "\n".join(bad)


def test_no_domain_package_holds_a_module_placed_in_another_domain(tree):
    bad = misplaced(tree)
    assert not bad, "\n".join(bad)


def test_uses_names_only_another_domains_modules(tree):
    bad = misused(tree)
    assert not bad, "\n".join(bad)


# The rules on planted mistakes. A small tree and package folders stand in for the real ones.
PLANTED = """
domains:
  - {slug: thermal, title: T, scope: s, maturity: idea, areas: [
      {slug: heat-sinks, title: H, scope: s, maturity: idea, api: [cadagent.thermal.heatsink]}]}
  - {slug: simulation, title: S, scope: s, maturity: idea, areas: [
      {slug: cfd, title: C, scope: s, maturity: idea, api: [cadagent.simulation.cfd]}]}
  - {slug: practice, title: P, scope: s, maturity: idea, areas: [
      {slug: review-and-evidence, title: R, scope: s, maturity: idea, api: [cadagent.review.evidence]},
      {slug: publishing, title: U, scope: s, maturity: idea, api: [cadagent.publish.site]}]}
"""


def planted(tmp_path, extra=()):
    for f in ("thermal/heatsink.py", "simulation/cfd.py", "review/evidence.py", "publish/site.py", *extra):
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("")
    return tmp_path


def loader(root):
    """Imports for the planted folders: a module exists when its file does, so moving a real module leaves these
    tests alone."""
    def load(name):
        path = root.joinpath(*name.split(".")[1:])
        if not (path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()):
            raise ModuleNotFoundError(f"No module named {name!r}")
    return load


def test_the_planted_tree_passes_every_rule(tmp_path):
    t = read_tree(PLANTED)
    assert unlisted(planted(tmp_path), t) == [] and unimportable(t, loader(tmp_path)) == [] and misplaced(t) == []
    assert misused(t) == []


def test_rule_1_finds_a_new_module_the_tree_does_not_list(tmp_path):
    t = read_tree(PLANTED)
    assert unlisted(planted(tmp_path, ["thermal/fans.py", "review/gates/__init__.py"]), t) == [
        "cadagent.thermal.fans: list it under thermal in docs/areas.yaml (api:)",
        "cadagent.review.gates: list it under practice/design-process or practice/review-and-evidence in "
        "docs/areas.yaml (api:)"]
    assert unimportable(t, loader(tmp_path)) == [] and misplaced(t) == []


def test_rule_1_wants_the_listing_in_the_modules_own_domain(tmp_path):
    """Listed, but only under another domain: rule 1 (not listed at home) and rule 3 (placed away) both say so."""
    t = read_tree(PLANTED.replace("api: [cadagent.simulation.cfd]", "api: []")
                  .replace("api: [cadagent.thermal.heatsink]",
                           "api: [cadagent.thermal.heatsink, cadagent.simulation.cfd]"))
    assert unlisted(planted(tmp_path), t) == [
        "cadagent.simulation.cfd: list it under simulation in docs/areas.yaml (api:)"]
    assert len(misplaced(t)) == 1


def test_rule_2_finds_an_entry_that_does_not_import_or_names_an_old_path(tmp_path):
    t = read_tree(PLANTED.replace("cadagent.thermal.heatsink]", "cadagent.thermal.heatsink, cadagent.thermal.no_such]")
                  .replace("api: [cadagent.simulation.cfd]", "api: [cadagent.simulation.cfd, cadagent.cfd]"))
    bad = unimportable(t, loader(planted(tmp_path)))
    assert bad == ["cadagent.cfd: an old path; name cadagent.simulation.cfd",
                   "cadagent.thermal.no_such: does not import (No module named 'cadagent.thermal.no_such')"], bad
    assert misplaced(t) == []


def test_rule_3_finds_a_module_placed_in_another_domain_too(tmp_path):
    """Listed at home and in another domain: only rule 3 fails (the tree names a module under one domain)."""
    t = read_tree(PLANTED.replace("api: [cadagent.thermal.heatsink]",
                                  "api: [cadagent.thermal.heatsink, cadagent.simulation.cfd]"))
    assert unlisted(planted(tmp_path), t) == [] and unimportable(t, loader(tmp_path)) == []
    assert misplaced(t) == ["cadagent.simulation.cfd lives in cadagent.simulation (simulation) but is placed under "
                            "thermal/heat-sinks: list it under its own domain only "
                            "(an area elsewhere that relies on it names it in its uses: list), or move it to "
                            "cadagent.thermal"]


def test_uses_links_another_domains_module_without_a_second_home(tmp_path):
    """thermal's area relies on CFD: in uses it breaks no rule, where in api it breaks rule 3."""
    t = read_tree(PLANTED.replace("api: [cadagent.thermal.heatsink]",
                                  "api: [cadagent.thermal.heatsink], uses: [cadagent.simulation.cfd]"))
    assert unlisted(planted(tmp_path), t) == [] and unimportable(t, loader(tmp_path)) == []
    assert misplaced(t) == [] and misused(t) == []


def test_rule_2_checks_uses_entries_too(tmp_path):
    t = read_tree(PLANTED.replace("api: [cadagent.thermal.heatsink]",
                                  "api: [cadagent.thermal.heatsink], uses: [cadagent.cfd, cadagent.simulation.nope]"))
    assert unimportable(t, loader(planted(tmp_path))) == [
        "cadagent.cfd: an old path; name cadagent.simulation.cfd",
        "cadagent.simulation.nope: does not import (No module named 'cadagent.simulation.nope')"]
    assert misused(t) == []


def test_rule_4_finds_a_uses_entry_at_home():
    """simulation's own module in a simulation area's uses, and a publish module in publishing's: both belong in api.
    A review module in publishing's uses is another home (practice's other package), so it is fine."""
    t = read_tree(PLANTED.replace("api: [cadagent.simulation.cfd]",
                                  "api: [cadagent.simulation.cfd], uses: [cadagent.simulation.fea]")
                  .replace("api: [cadagent.publish.site]",
                           "api: [cadagent.publish.site], uses: [cadagent.publish.render, cadagent.review.evidence]"))
    assert misused(t) == [
        "cadagent.simulation.fea is simulation/cfd's own domain's module (simulation): list it under api, not uses",
        "cadagent.publish.render is practice/publishing's own domain's module (practice/publishing): list it under "
        "api, not uses"]
    assert misplaced(t) == []


def test_rule_3_tells_the_practice_packages_apart():
    """review and publish share the practice domain; a review module listed under publishing is misplaced."""
    t = read_tree(PLANTED.replace("api: [cadagent.publish.site]",
                                  "api: [cadagent.publish.site, cadagent.review.evidence]"))
    assert misplaced(t) == ["cadagent.review.evidence lives in cadagent.review (practice/design-process or "
                            "practice/review-and-evidence) but is placed under practice/publishing: list it under its "
                            "own domain only (an area elsewhere that relies on it names it in its uses: list), "
                            "or move it to cadagent.publish"]
