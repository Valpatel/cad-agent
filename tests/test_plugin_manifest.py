"""The Claude Code plugin (.claude-plugin/): its version follows the package, and it ships skills and subagents only.

A plugin can also bring hooks, monitors, MCP/LSP servers and executables that run with the user's privileges. Ours
must not: installing it should run nothing (docs/contributing-agents.md).
"""
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]
PLUGIN = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
MARKET = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())


def _version():
    project = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", (ROOT / "pyproject.toml").read_text(), re.M | re.S).group(1)
    return re.search(r'^version\s*=\s*"([^"]+)"', project, re.M).group(1)


def test_versions_follow_the_package():
    v = _version()
    entry = next(p for p in MARKET["plugins"] if p["name"] == PLUGIN["name"])
    assert PLUGIN["version"] == v and entry["version"] == v, (
        f"bump .claude-plugin/plugin.json and marketplace.json to {v} with pyproject.toml")


def test_marketplace_lists_this_repo_as_the_plugin():
    assert PLUGIN["name"] == "cad-agent"
    entry = next(p for p in MARKET["plugins"] if p["name"] == "cad-agent")
    assert entry["source"] == "./"
    assert MARKET["name"] and MARKET["owner"]["name"]


def test_ships_skills_and_agents_only():
    for key in ("hooks", "mcpServers", "lspServers", "monitors", "commands", "outputStyles"):
        assert key not in PLUGIN, f"plugin.json must not declare {key}"
    for path in ("hooks", "hooks/hooks.json", ".mcp.json", ".lsp.json", "bin", "monitors", "commands"):
        assert not (ROOT / path).exists(), f"{path} would ship in the plugin and run on users' machines"
    assert any((ROOT / "skills").glob("*/SKILL.md")) and any((ROOT / "agents").glob("*.md"))


def test_icon_is_a_square_png():
    data = (ROOT / ".claude-plugin/icon.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert w == h and 512 <= w <= 2048 and len(data) < 2_000_000
