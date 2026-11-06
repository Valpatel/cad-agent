"""Lint for the skills shipped in ``skills/<name>/SKILL.md``: front matter, links, and that the commands, gates and
API names a skill tells an agent to use exist. CLI references include inline code and shell examples; examples are
never executed. This checks names, not argument correctness or universal lesson enforcement."""

from __future__ import annotations

import importlib
import re
import shlex
from pathlib import Path

import pytest
import yaml

from cadagent._deps import MissingDependency
from cadagent.cli import SUBCOMMANDS

ROOT = Path(__file__).resolve().parents[2]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))


def shell_commands(source: str):
    """Command words in documented shell examples, without executing them.

    Quotes, escapes, comments, assignments and command separators are supported. This is not a shell interpreter:
    substitutions, functions and control-flow syntax are outside this command-name existence check.
    """
    at_command, needs_subcommand = True, False
    start, quote, i = None, None, 0
    while i <= len(source):
        char = source[i] if i < len(source) else "\n"
        if i < len(source) and char == "\\" and quote != "'":
            if source[i:i + 2] == "\\\n":
                source = source[:i] + source[i + 2:]  # shell continuation, including inside double quotes
                continue
            if start is None:
                start = i
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
            if i == len(source):
                raise AssertionError("unclosed quote in a shell example")
        elif char in "'\"":
            if start is None:
                start = i
            quote = char
        elif char == "#" and start is None:
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            continue
        elif char.isspace() or char in ";&|":
            if start is not None:
                raw = source[start:i]
                word, = shlex.split(raw, comments=False)
                if needs_subcommand:
                    if re.fullmatch(r"[a-z][a-z0-9-]*", word):
                        yield word
                    needs_subcommand = False
                elif at_command and not re.match(r"[A-Za-z_]\w*=", raw):
                    needs_subcommand = word == "cad-agent"
                    at_command = False
                start = None
            if char == "\n" or char in ";&|":
                at_command, needs_subcommand = True, False
        elif start is None:
            start = i
        i += 1


def skill_commands(text: str):
    """Inline references plus shell fences/indented examples; other fenced languages are data."""
    fence, language, block = None, "", []
    for line in text.splitlines(keepends=True):
        if fence:
            if re.fullmatch(r"\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line):
                if language in ("sh", "bash", "shell"):
                    yield from shell_commands("".join(block))
                fence, block = None, []
            else:
                block.append(line)
            continue
        opening = re.match(r"^\s*(`{3,}|~{3,})([^\n]*)", line)
        if opening or (line.strip() and not re.match(r"^(?: {4}|\t)", line)):
            yield from shell_commands("".join(block))
            block = []
        if opening:
            fence = opening[1]
            language = opening[2].strip()
        elif (block and (not line.strip() or re.match(r"^(?: {4}|\t)", line))) or re.match(
                r"^(?: {4}|\t)\s*(?:cad-agent\b|[A-Za-z_]\w*=)", line):
            block.append(line)
        else:
            yield from re.findall(r"`cad-agent ([a-z][a-z0-9-]*)", line)
    if not fence or language in ("sh", "bash", "shell"):
        yield from shell_commands("".join(block))


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
    for cmd in sorted(set(skill_commands(text))):
        if cmd not in SUBCOMMANDS and cmd in ("review-section",):  # keep the announced T11 exception until implemented
            assert "until" in text or "T11" in text
            continue
        assert cmd in SUBCOMMANDS, f"`cad-agent {cmd}` is not a command"
    from cadagent.review.dossier.lint import KNOWN_GATES
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


@pytest.mark.parametrize("text", [
    "Use `cad-agent not-a-real-command`.",
    "```bash\ncad-agent not-a-real-command\n```\n",
    "~~~sh\ncad-agent not-a-real-command\n~~~\n",
    "    cad-agent not-a-real-command\n",
    "```shell\ncad-agent gates --build && cad-agent not-a-real-command\n```\n",
    "```bash\nCAD_AGENT_ACTOR=reviewer cad-agent not-a-real-command\n```\n",
])
def test_missing_commands_fail_through_the_real_skill_check(tmp_path, text):
    path = tmp_path / "SKILL.md"
    path.write_text(text)
    with pytest.raises(AssertionError, match="not-a-real-command.*is not a command"):
        test_skill_commands_gates_and_names_exist(path)


@pytest.mark.parametrize("text", [
    "Use `cad-agent gates --build`.",
    "```bash\ncad-agent gates --build # cad-agent not-a-real-command\n```\n",
    "```sh\n# cad-agent not-a-real-command\ncad-agent --help\ncad-agent --version\n```\n",
    "```bash\nprintf '%s\\n' 'cad-agent not-a-real-command'\necho cad-agent not-a-real-command\n```\n",
    "```bash\nprintf '%s' '&&' cad-agent not-a-real-command\n```\n",
    "```bash\nCAD_AGENT_ACTOR='separate reviewer' cad-agent gates \\\n    --build\n```\n",
    '```bash\n"cad-agent" "gates" --build\n```\n',
    '```python\nexample = "`cad-agent not-a-real-command`"\n```\n',
    "    cad-agent mcmaster 91290A242 \\\n        --kind screw --out references/vendor/mcmaster\n",
    "Until T11, `cad-agent review-section S3` is announced.\n",
    "```bash\ncad-agent review-section S3\n```\n",  # now implemented: no future-announcement text needed
])
def test_valid_shell_examples_remain_accepted_by_the_real_skill_check(tmp_path, text):
    path = tmp_path / "SKILL.md"
    path.write_text(text)
    test_skill_commands_gates_and_names_exist(path)


def test_announced_review_section_exception_still_requires_its_explanation(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "SUBCOMMANDS", tuple(c for c in SUBCOMMANDS if c != "review-section"))
    path = tmp_path / "SKILL.md"
    path.write_text("Until T11, `cad-agent review-section S3` is announced.\n")
    test_skill_commands_gates_and_names_exist(path)
    path.write_text("Use `cad-agent review-section S3`.\n")
    with pytest.raises(AssertionError):
        test_skill_commands_gates_and_names_exist(path)
