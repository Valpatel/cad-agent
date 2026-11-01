"""docs/areas.yaml, the topic tree (#140): it parses, its slugs are unique, everything it names exists, and every page,
skill and lesson area is placed in it, so a new page cannot go missing from the map."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AREAS = ROOT / "docs" / "areas.yaml"
LEVELS = ["idea", "surveyed", "tooling", "validated", "proven"]
PRIORITIES = {"gyropup", "demo"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LIST_KEYS = ("priority", "pages", "cli", "api", "skills", "agents", "issues", "projects")
NODE_KEYS = {"slug", "title", "scope", "maturity", "lessons", "areas", "topics", *LIST_KEYS}


@pytest.fixture(scope="module")
def tree():
    return yaml.safe_load(AREAS.read_text(encoding="utf-8"))


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
    for path, n in nodes(tree):
        where = "/".join(path)
        assert NODE_KEYS >= set(n), f"{where}: unknown keys {set(n) - NODE_KEYS}"
        assert SLUG.match(n["slug"]), f"{where}: slug must be lower-case words joined by hyphens"
        assert n["title"].strip() and n["scope"].strip(), f"{where}: needs a title and a one-line scope"
        assert "\n" not in n["scope"].strip(), f"{where}: scope is one line"
        assert n["maturity"] in LEVELS, f"{where}: maturity {n['maturity']!r} is not one of {LEVELS}"
        assert set(n.get("priority", [])) <= PRIORITIES, f"{where}: priority flags are {sorted(PRIORITIES)}"
        for key in LIST_KEYS:
            assert isinstance(n.get(key, []), list), f"{where}: {key} is a list"


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
    for mod in placed(tree, "api"):
        assert mod.startswith("cadagent.") and importlib.util.find_spec(mod), f"{mod} is not a cadagent module"


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
