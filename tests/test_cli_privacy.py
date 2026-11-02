"""Usage reporting off (#278): cad-agent sends nothing, and every command turns reporting off for what it runs.

The opt-outs are ``OPT_OUTS`` in ``cadagent/cli.py``; docs/supply-chain.md ("Usage reporting") is the survey behind
them. A vendored tool that names a new telemetry switch fails here until the list covers it or ``NOT_SWITCHES`` says why
it is not one.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from cadagent import cli

ROOT = Path(__file__).resolve().parents[1]
SWITCH = re.compile(r"\b[A-Z][A-Z0-9_]*(?:TELEMETRY|ANALYTICS|SEND_METRICS|DO_NOT_TRACK|USAGE_STATS)[A-Z0-9_]*\b")
# Names that match the pattern but switch nothing on or off.
NOT_SWITCHES = {
    "CADGEN_TELEMETRY_NOTICE": "cadgen's record that it showed its notice once; not a switch",
    "KICAD_MCP_TELEMETRY_BUFFER_MAX_EVENTS": "the size of kicad-mcp-pro's local event buffer; no effect while telemetry is off",
}


def test_every_command_turns_reporting_off_and_keeps_an_explicit_choice():
    env = {k: v for k, v in os.environ.items() if k not in cli.OPT_OUTS}
    env["DO_NOT_TRACK"] = "0"                               # a person's explicit choice stands
    code = ("import os, json; from cadagent.cli import main\n"
            "try: main(['--help'])\nexcept SystemExit: pass\n"
            f"print(json.dumps({{k: os.environ.get(k) for k in {sorted(cli.OPT_OUTS)!r}}}))")
    out = subprocess.run([sys.executable, "-c", code], env={**env, "PYTHONPATH": str(ROOT / "src")},
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    seen = json.loads(out)
    assert seen == {k: ("0" if k == "DO_NOT_TRACK" else v) for k, (v, _) in cli.OPT_OUTS.items()}


def test_opt_out_sets_only_what_is_missing():
    env = {"CADGEN_TELEMETRY": "1"}
    added = cli.opt_out(env)
    assert "CADGEN_TELEMETRY" not in added and env["CADGEN_TELEMETRY"] == "1"
    assert set(added) == set(cli.OPT_OUTS) - {"CADGEN_TELEMETRY"}
    assert cli.opt_out(env) == []


def test_every_switch_a_vendored_tool_names_is_covered():
    named = set()
    for path in (ROOT / "vendor").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".mjs", ".js", ".ts", ".tsx", ".md", ".example", ".toml", ".sh"}:
            named |= set(SWITCH.findall(path.read_text(errors="replace")))
    assert named, "the survey found nothing: the pattern or the vendor folder moved"
    missing = named - set(cli.OPT_OUTS) - set(NOT_SWITCHES)
    assert not missing, f"a vendored tool names a telemetry switch: add it to OPT_OUTS in cadagent/cli.py: {sorted(missing)}"
    stale = set(NOT_SWITCHES) - named
    assert not stale, f"NOT_SWITCHES names what no vendored file mentions any more: {sorted(stale)}"


def test_scripts_that_run_wrangler_keep_its_metrics_off():
    scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
    for name, line in scripts.items():
        if "wrangler" in line:
            assert "WRANGLER_SEND_METRICS=false" in line.split("wrangler")[0], name


def test_the_survey_page_lists_every_opt_out():
    page = (ROOT / "docs" / "supply-chain.md").read_text().split("## Usage reporting", 1)[1].split("\n## ", 1)[0]
    for k, (v, _) in cli.OPT_OUTS.items():
        assert f"{k}={v}" in page, f"docs/supply-chain.md's Usage reporting table names {k}={v}"


def test_the_package_has_no_telemetry_client():
    hits = [str(p.relative_to(ROOT)) for p in (ROOT / "src" / "cadagent").rglob("*.py")
            if re.search(r"posthog|sentry_sdk|mixpanel|segment\.io|google-analytics|api\.amplitude\.com", p.read_text(), re.I)]
    assert not hits, hits
