"""Usage reporting off (#278): cad-agent sends nothing, and every project step it runs gets reporting turned off.

The opt-outs are ``OPT_OUTS`` in ``cadagent/cli.py``; docs/practice/supply-chain.md ("Usage reporting") is the survey behind
them. A vendored tool that names a new telemetry, update-check or export switch fails here until the list covers it or
``NOT_SWITCHES`` says why it is not one to set.
"""
from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from pathlib import Path

from cadagent import cli

ROOT = Path(__file__).resolve().parents[2]
SWITCH = re.compile(r"\b[A-Z][A-Z0-9_]*(?:TELEMETRY|ANALYTICS|SEND_METRICS|SEND_ERROR_REPORTS|DO_NOT_TRACK|USAGE_STATS"
                    r"|UPDATE_CHECK|CRASH_REPORT|OTLP_[A-Z_]*ENDPOINT|OTEL_ENDPOINT|SENTRY_DSN)[A-Z0-9_]*\b"
                    r"|\bPOSTHOG_[A-Z0-9_]+\b")
SUFFIXES = {".py", ".mjs", ".js", ".ts", ".tsx", ".md", ".rst", ".txt", ".example", ".env", ".toml", ".sh",
            ".json", ".yaml", ".yml", ".cfg", ".ini"}
# Names that match the pattern but are not an opt-out to set.
NOT_SWITCHES = {
    "CADGEN_TELEMETRY_NOTICE": "cadgen's record that it showed its notice once; not a switch",
    "KICAD_MCP_TELEMETRY_BUFFER_MAX_EVENTS": "the size of kicad-mcp-pro's local event buffer; no effect while telemetry is off",
    "KICAD_MCP_OTEL_ENDPOINT": "kicad-mcp-pro exports only when an endpoint is set: leave it unset (docs/practice/supply-chain.md)",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "the same, through OpenTelemetry's own variable: leave it unset for the MCP server",
}
# text-to-cad's maintainers' own PostHog credentials for their hosted service; nothing a user runs reads them.
NOT_SWITCH_PREFIXES = ("POSTHOG_",)


def _steps_project(root: Path, names) -> Path:
    (root / "tools").mkdir(parents=True)
    (root / "exports").mkdir()
    code = f"import os, json; json.dump({{k: os.environ.get(k) for k in {sorted(names)!r}}}, open('exports/env.json', 'w'))"
    (root / "tools" / "env.py").write_text(code + "\n")
    (root / "cad-agent.yaml").write_text(textwrap.dedent(f"""\
        cad:
          name: privacy
          python: {sys.executable}
          steps:
            - {{name: env, run: tools/env.py}}
        """))
    return root


def test_every_step_runs_with_reporting_off_and_an_explicit_choice_stands(tmp_path, monkeypatch):
    for k in cli.OPT_OUTS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DO_NOT_TRACK", "0")                 # a person's explicit choice stands
    root = _steps_project(tmp_path, cli.OPT_OUTS)
    assert cli.main(["build", "--project", str(root)]) == 0
    seen = json.loads((root / "exports" / "env.json").read_text())
    assert seen == {k: ("0" if k == "DO_NOT_TRACK" else v) for k, (v, _) in cli.OPT_OUTS.items()}
    # ...and the calling process is left as it was.
    assert os.environ["DO_NOT_TRACK"] == "0" and not any(k in os.environ for k in set(cli.OPT_OUTS) - {"DO_NOT_TRACK"})


def test_opt_out_sets_only_what_is_missing():
    env = {"CADGEN_TELEMETRY": "1"}
    added = cli.opt_out(env)
    assert "CADGEN_TELEMETRY" not in added and env["CADGEN_TELEMETRY"] == "1"
    assert set(added) == set(cli.OPT_OUTS) - {"CADGEN_TELEMETRY"}
    assert cli.opt_out(env) == []


def test_every_switch_a_vendored_tool_names_is_covered():
    named = set()
    for path in (ROOT / "vendor").rglob("*"):
        if path.is_file() and (path.suffix in SUFFIXES or path.name.startswith(".env")):
            named |= set(SWITCH.findall(path.read_text(errors="replace")))
    assert named, "the survey found nothing: the pattern or the vendor folder moved"
    named = {n for n in named if not n.startswith(NOT_SWITCH_PREFIXES)}
    missing = named - set(cli.OPT_OUTS) - set(NOT_SWITCHES)
    assert not missing, f"a vendored tool names a telemetry switch: add it to OPT_OUTS in cadagent/cli.py: {sorted(missing)}"
    stale = set(NOT_SWITCHES) - named
    assert not stale, f"NOT_SWITCHES names what no vendored file mentions any more: {sorted(stale)}"


def test_scripts_that_run_wrangler_keep_its_metrics_off():
    scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
    for name, line in scripts.items():
        if "wrangler" in line:
            before = line.split("wrangler")[0]
            assert "WRANGLER_SEND_METRICS=false" in before and "WRANGLER_SEND_ERROR_REPORTS=false" in before, name


def test_the_survey_page_lists_every_opt_out():
    page = (ROOT / "docs" / "practice" / "supply-chain.md").read_text().split("## Usage reporting", 1)[1].split("\n## ", 1)[0]
    for k, (v, _) in cli.OPT_OUTS.items():
        assert f"{k}={v}" in page, f"docs/practice/supply-chain.md's Usage reporting table names {k}={v}"


def test_the_package_has_no_telemetry_client():
    hits = [str(p.relative_to(ROOT)) for p in (ROOT / "src" / "cadagent").rglob("*.py")
            if re.search(r"posthog|sentry_sdk|mixpanel|segment\.io|google-analytics|api\.amplitude\.com", p.read_text(), re.I)]
    assert not hits, hits
