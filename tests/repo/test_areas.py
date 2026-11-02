"""docs/areas.yaml, the topic tree (#140): it parses, its slugs are unique, everything it names exists, and every page,
skill and lesson area is placed in it, so a new page cannot go missing from the map."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AREAS = ROOT / "docs" / "areas.yaml"
LEVELS = ["idea", "surveyed", "tooling", "validated", "proven"]
PRIORITIES = {"demo"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LIST_KEYS = ("priority", "pages", "cli", "api", "uses", "skills", "agents", "issues", "projects")
NODE_KEYS = {"slug", "title", "scope", "maturity", "lessons", *LIST_KEYS}
# What each depth may hold: a key at the wrong depth (a mis-indented node) is an error, not silently skipped.
DEPTH_KEYS = {1: NODE_KEYS | {"areas"}, 2: NODE_KEYS | {"topics"}, 3: NODE_KEYS}
TOP_KEYS = {"version", "maturity", "projects", "cross_cutting", "domains"}
CROSS_KEYS = {"pages", "api", "issues"}


class _Strict(yaml.SafeLoader):
    """safe_load keeps the last of two equal keys and drops the first without a word: a second `pages:` added to a node
    would lose the first one's pages. Refuse duplicates instead (review of #148)."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(k, deep=deep) for k, _ in node.value]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate keys {dup}: merge them into one", node.start_mark)
        return super().construct_mapping(node, deep)


def load_areas(text):
    return yaml.load(text, Loader=_Strict)


def read_tree(text=None):
    """The tree every test here checks: docs/areas.yaml (or planted text) through the strict loader."""
    return load_areas(AREAS.read_text(encoding="utf-8") if text is None else text)


@pytest.fixture(scope="module")
def tree():
    return read_tree()


def test_a_duplicate_key_is_refused_not_silently_dropped():
    with pytest.raises(yaml.constructor.ConstructorError, match=r"duplicate keys \['issues', 'maturity'\]"):
        read_tree("{issues: [1, 2], maturity: tooling, issues: [3], maturity: idea}")
    assert read_tree("{issues: [1], maturity: idea}") == {"issues": [1], "maturity": "idea"}
    # The real file with a second `domains:` (a pasted block, say): the first would be dropped without a word.
    with pytest.raises(yaml.constructor.ConstructorError, match=r"duplicate keys \['domains'\]"):
        read_tree(AREAS.read_text(encoding="utf-8") + "\ndomains: []\n")


def nodes(tree):
    """(path, node) for every domain, area and topic, depth first."""
    for d in tree["domains"]:
        yield (d["slug"],), d
        for a in d.get("areas", []):
            yield (d["slug"], a["slug"]), a
            for t in a.get("topics", []):
                yield (d["slug"], a["slug"], t["slug"]), t


def placed(tree, key):
    """Every item listed under `key`, by any node or as cross-cutting."""
    items = list(tree.get("cross_cutting", {}).get(key, []))
    for _, n in nodes(tree):
        items += n.get(key, [])
    return items


def test_the_maturity_levels_are_the_documented_ladder(tree):
    assert [m["level"] for m in tree["maturity"]] == LEVELS
    assert all(m["means"].strip() for m in tree["maturity"])


def test_every_node_has_the_core_fields_and_known_keys(tree):
    assert set(tree) <= TOP_KEYS, f"unknown top-level keys {set(tree) - TOP_KEYS}"
    assert set(tree.get("cross_cutting", {})) <= CROSS_KEYS, f"unknown cross_cutting keys {set(tree['cross_cutting']) - CROSS_KEYS}"
    for path, n in nodes(tree):
        where, allowed = "/".join(path), DEPTH_KEYS[len(path)]
        assert allowed >= set(n), f"{where}: keys {sorted(set(n) - allowed)} do not belong at this depth"
        assert SLUG.match(n["slug"]), f"{where}: slug must be lower-case words joined by hyphens"
        assert n["title"].strip() and n["scope"].strip(), f"{where}: needs a title and a one-line scope"
        assert "\n" not in n["scope"].strip(), f"{where}: scope is one line"
        assert n["maturity"] in LEVELS, f"{where}: maturity {n['maturity']!r} is not one of {LEVELS}"
        assert set(n.get("priority", [])) <= PRIORITIES, f"{where}: priority flags are {sorted(PRIORITIES)}"
        for key in LIST_KEYS:
            assert isinstance(n.get(key, []), list), f"{where}: {key} is a list"


def test_maturity_follows_the_written_rules(tree):
    """docs/areas.yaml header: an area is never below its most mature topic; a domain is the highest of its areas."""
    rank = LEVELS.index
    for d in tree["domains"]:
        for a in d.get("areas", []):
            top = max((rank(t["maturity"]) for t in a.get("topics", [])), default=0)
            assert rank(a["maturity"]) >= top, \
                f"{d['slug']}/{a['slug']}: below its most mature topic; set its maturity to at least {LEVELS[top]}"
        best = max((rank(a["maturity"]) for a in d.get("areas", [])), default=0)
        assert rank(d["maturity"]) == best, f"{d['slug']}: a domain's maturity is the highest of its areas' ({LEVELS[best]})"


def test_slugs_are_unique_among_siblings_and_areas_unique_overall(tree):
    domains = [d["slug"] for d in tree["domains"]]
    assert len(domains) == len(set(domains))
    areas = [p[1] for p, _ in nodes(tree) if len(p) == 2]
    assert len(areas) == len(set(areas)), "area slugs are unique across domains, so /areas/<area> is unambiguous"
    for path, n in nodes(tree):
        kids = [k["slug"] for k in n.get("areas", []) + n.get("topics", [])]
        assert len(kids) == len(set(kids)), f"{'/'.join(path)}: duplicate child slug"


def test_every_named_page_skill_agent_and_project_exists(tree):
    for page in placed(tree, "pages"):
        assert page.endswith(".md") and (ROOT / page).is_file(), f"{page} does not exist"
    for skill in placed(tree, "skills"):
        assert (ROOT / "skills" / skill / "SKILL.md").is_file(), f"skill {skill} does not exist"
    for agent in placed(tree, "agents"):
        assert (ROOT / "agents" / f"{agent}.md").is_file(), f"agent {agent} does not exist"
    for key in placed(tree, "projects"):
        assert key in tree["projects"], f"project {key} is not in `projects`"
    for p in tree["projects"].values():
        assert p["url"].startswith("https://")
    for n in placed(tree, "issues"):
        assert isinstance(n, int) and n > 0


def test_every_named_command_and_module_exists(tree):
    from cadagent.cli import SUBCOMMANDS
    for cmd in placed(tree, "cli"):
        assert cmd in SUBCOMMANDS, f"`cad-agent {cmd}` is not a command"
    for key in ("api", "uses"):
        for mod in placed(tree, key):
            assert mod.startswith("cadagent.") and importlib.util.find_spec(mod), \
                f"{key}: {mod} is not a cadagent module"


def uses_repeats(tree):
    """`uses` names modules a node relies on from elsewhere, so it never repeats the node's own `api` or itself."""
    bad = []
    for path, n in nodes(tree):
        uses = n.get("uses", [])
        bad += [f"{'/'.join(path)}: {m} is in both api and uses; keep it in api" for m in uses if m in n.get("api", [])]
        bad += [f"{'/'.join(path)}: {m} is named twice in uses" for m in sorted({m for m in uses if uses.count(m) > 1})]
    return bad


def test_uses_does_not_repeat_the_nodes_api(tree):
    bad = uses_repeats(tree)
    assert not bad, "\n".join(bad)


def test_uses_repeats_are_found():
    planted = read_tree("{domains: [{slug: thermal, title: T, scope: s, maturity: idea, areas: [{slug: airflow, "
                        "title: A, scope: s, maturity: idea, api: [cadagent.thermal.heatsink], "
                        "uses: [cadagent.thermal.heatsink, cadagent.simulation.cfd, cadagent.simulation.cfd]}]}]}")
    assert uses_repeats(planted) == [
        "thermal/airflow: cadagent.thermal.heatsink is in both api and uses; keep it in api",
        "thermal/airflow: cadagent.simulation.cfd is named twice in uses"]


def test_modules_are_named_by_their_current_paths(tree):
    """Once #121's package layout is on dev, old module paths only warn (until a release that the CHANGELOG announces
    a minor release ahead): name the new ones."""
    moved = pytest.importorskip("cadagent._moved", reason="old paths are current until #121 lands").MOVED
    old = sorted({m for m in placed(tree, "api") if m.split(".", 1)[1] in moved})   # a module may sit in two areas
    assert not old, f"use the new paths in docs/areas.yaml: {[(m, moved[m.split('.', 1)[1]]) for m in old]}"


def test_every_command_skill_and_agent_is_placed(tree):
    from cadagent.cli import SUBCOMMANDS
    missing = sorted(set(SUBCOMMANDS) - set(placed(tree, "cli")))
    assert not missing, f"add these `cad-agent` commands to a node's cli: in docs/areas.yaml: {missing}"
    skills = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
    missing = sorted(set(skills) - set(placed(tree, "skills")))
    assert not missing, f"add these skills to a node's skills: in docs/areas.yaml: {missing}"
    agents = sorted(p.stem for p in (ROOT / "agents").glob("*.md") if p.stem.lower() != "readme")
    missing = sorted(set(agents) - set(placed(tree, "agents")))
    assert not missing, f"add these agents to a node's agents: in docs/areas.yaml: {missing}"


def published_pages():
    """docs/ and research/ Markdown pages, except folder READMEs and moved-page stubs."""
    for folder in ("docs", "research"):
        for p in sorted((ROOT / folder).rglob("*.md")):
            if p.name.lower() == "readme.md":
                continue
            if p.read_text(encoding="utf-8").lstrip().startswith("<!-- moved-to:"):
                continue
            yield p.relative_to(ROOT).as_posix()


def test_every_docs_and_research_page_is_placed(tree):
    missing = sorted(set(published_pages()) - set(placed(tree, "pages")))
    assert not missing, f"add these pages to a node's pages: in docs/areas.yaml (or cross_cutting): {missing}"


def test_every_lesson_area_folder_is_claimed(tree):
    """Lessons are grouped by area folders (#133). Before that lands, lessons/ is flat and the names are only checked
    for form; after, every folder is claimed by exactly one node and every claim is a folder."""
    claims = [n["lessons"] for _, n in nodes(tree) if "lessons" in n]
    assert len(claims) == len(set(claims)), "each lesson area is claimed by one node"
    assert all(SLUG.match(c) for c in claims)
    folders = sorted(p.name for p in (ROOT / "lessons").iterdir() if p.is_dir())
    if folders:
        assert sorted(claims) == folders, f"lesson folders {folders} and claims {sorted(claims)} differ"
