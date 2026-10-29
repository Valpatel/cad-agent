"""Lint for the skills shipped in ``skills/<name>/SKILL.md``: front matter, links, and that the commands, gates and
API names a skill tells an agent to use exist. A skill that names a command or a function that is not there sends
every agent that follows it down a dead end."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
import yaml

from cadagent._deps import MissingDependency
from cadagent.cli import SUBCOMMANDS

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))


def front_matter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no front matter (--- name/description ---)"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), "front matter is not a mapping"
    return data


def test_there_are_skills():
    assert any(p.parent.name == "design-process" for p in SKILLS)


@pytest.mark.parametrize("path", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_skill_front_matter(path):
    fm = front_matter(path.read_text())
    assert fm.get("name") == path.parent.name, "name must match the folder"
    desc = fm.get("description")
    assert isinstance(desc, str) and 40 <= len(desc) <= 1024, "a description of 40 to 1024 characters"
    assert desc.startswith("Use "), "the description says when to use the skill"


@pytest.mark.parametrize("path", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_skill_links_resolve(path):
    text = path.read_text()
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+://", target) or target.startswith("#"):
            continue
        assert (path.parent / target.split("#")[0]).resolve().exists(), f"broken link {target}"


@pytest.mark.parametrize("path", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_skill_commands_gates_and_names_exist(path):
    text = path.read_text()
    for cmd in re.findall(r"`cad-agent ([a-z][a-z0-9-]*)", text):
        if cmd in ("review-section",):              # announced for the reviewer pass (T11), named as future
            assert "until" in text or "T11" in text
            continue
        assert cmd in SUBCOMMANDS, f"`cad-agent {cmd}` is not a command"
    from cadagent.dossier.lint import KNOWN_GATES
    for gate in re.findall(r"gate:([a-z-]+)", text):
        assert gate in KNOWN_GATES, f"gate:{gate} is not a gate"
    for dotted in sorted(set(re.findall(r"`(cadagent(?:\.[A-Za-z_]\w*)+)", text))):
        parts = dotted.split(".")
        obj = None
        for i in range(len(parts), 0, -1):
            try:
                obj = importlib.import_module(".".join(parts[:i]))
            except MissingDependency:
                pytest.skip(f"{dotted} needs an optional dependency")
            except ImportError:
                continue
            for attr in parts[i:]:
                assert hasattr(obj, attr), f"{dotted} does not exist"
                obj = getattr(obj, attr)
            break
        assert obj is not None, f"{dotted} does not import"
