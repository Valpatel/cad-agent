"""What people paste and what agents read (#278, #282): docs/agent-prompt.txt.

Its first line is what a person pastes into an agent; the rest is how to install and work with the kit, which llms.txt
carries. The README opens with the one-line install commands and that line (the site's card, llms.txt and index.md are
checked in tests/site/website-build.test.mjs). Here: the README section stays short; the install commands are the
public ones and name real `cad-agent` commands; the report headings match the issue form, the PR template and the
grader in tools/quickstart_eval.py; it asks nothing risky of an outside agent; and the grader reads a planted run the
way it reads a real one.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BLOCK = (ROOT / "docs" / "agent-prompt.txt").read_text()
PASTE, GUIDE = BLOCK.split("\n", 1)
README = (ROOT / "README.md").read_text()
USE_HEADING = "Build with your favorite AI agent"     # the site's card says the same (tests/site/website-build.test.mjs)
ONE_LINERS = ("curl -fsSL https://cad-agent.valpatel.com/install.sh | sh",
              "irm https://cad-agent.valpatel.com/install.ps1 | iex")


def _eval():
    spec = importlib.util.spec_from_file_location("quickstart_eval", ROOT / "tools" / "quickstart_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readme_opens_with_one_command_and_the_paste_in_line():
    headings = re.findall(r"^## (.+)$", README, re.M)
    assert headings[0] == USE_HEADING, f"'## {USE_HEADING}' is the README's first section, not {headings[0]!r}"
    use_it = README.split(f"## {USE_HEADING}\n", 1)[1].split("\n## ", 1)[0]
    for cmd in ONE_LINERS:
        assert f"\n{cmd}\n" in use_it, f"the README gives {cmd!r} on a line of its own"
    assert "```text\n" + PASTE + "\n```" in use_it, "and the first line of docs/agent-prompt.txt to paste"
    words = len(re.sub(r"<!--.*?-->", "", use_it, flags=re.S).split())
    assert words <= 140, f"{words} words: keep the section about as short as text-to-cad's quick start (~125)"
    flat = " ".join(use_it.split())
    assert "collects no telemetry" in flat and "only if you say yes" in flat
    assert "docs/agent-workflow.md#install" in use_it, "the long form is one link away"
    assert "## Quick start" not in README, "one quick start: the first section replaced it"


def test_the_paste_in_line_is_short_and_points_at_llms_txt():
    assert PASTE == "Install cad-agent from https://cad-agent.valpatel.com/llms.txt, then use it for:"
    assert len(PASTE.split()) == 8 and GUIDE.startswith("\n"), "one line, then a blank line"


def test_commands_are_public_and_name_real_commands():
    qe = _eval()
    cmds = qe.commands(BLOCK)
    assert cmds == ["curl -fsSLO https://cad-agent.valpatel.com/install.sh && sh install.sh"], cmds
    assert "Windows: irm https://cad-agent.valpatel.com/install.ps1 | iex" in BLOCK
    assert "`cad-agent update`" in BLOCK, "an agent that finds it installed updates first"
    from cadagent.cli import build_parser
    names = set(build_parser()._subparsers._group_actions[0].choices)
    named = set(re.findall(r"(?:bin/|`)cad-agent\"? ([a-z][a-z0-9-]+)", BLOCK))
    assert named and named <= names, f"the block names commands that do not exist: {named - names}"
    for url in re.findall(r"(?:https?://)?[\w.-]+\.(?:com|org|net|dev)[\w/.<>-]*", BLOCK):
        assert re.match(r"(?:https://)?(github\.com/Valpatel/cad-agent|cad-agent\.valpatel\.com)\b", url), url


def test_report_fields_match_the_form_the_pr_template_and_the_grader():
    qe = _eval()
    for heading in qe.REPORT_HEADINGS:
        assert heading in BLOCK.replace("\n   ", " "), f"the block asks for {heading!r}"
    form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "feedback.yml").read_text())
    fields = {f.get("id"): f for f in form["body"] if f.get("id")}
    labels = {f["attributes"]["label"] for f in fields.values()}
    for heading in ("Model", "Harness", "cad-agent commit", "Layer", "Building", "Sources", "Confidence"):
        assert heading in labels, f"the issue form has a {heading!r} field"
    optional = [k for k in ("model", "harness", "version", "layer", "building", "sources", "confidence")
                if not (fields[k].get("validations") or {}).get("required")]
    assert len(optional) == 7, "the provenance fields stay optional for people"
    pr = (ROOT / ".github" / "pull_request_template.md").read_text()
    made = pr.split("## Made with", 1)[1].split("\n## ", 1)[0]
    for field in ("Model:", "Harness:", "cad-agent commit", "Layer", "Confidence"):
        assert field in made, f"the PR template's Made with asks for {field!r}"
    assert '"Made with"' in BLOCK


def test_the_block_asks_nothing_risky():
    flat = " ".join(BLOCK.split())
    assert "send it only if they say yes" in flat, "the person approves every report before it is sent"
    assert "no telemetry" in flat and "through GitHub only" in flat
    assert "Leave out anything private" in flat
    assert not re.search(r"\|\s*(?:ba|z)?sh\b|curl\b[^\n]*\|", BLOCK), "the agent downloads the script, then runs it"
    assert not re.search(r"sudo|--force|rm -rf|token|password|secret|ignore (?:previous|all)|maintainer", BLOCK, re.I)
    assert "gh issue create -R Valpatel/cad-agent" in BLOCK and "--label" not in BLOCK   # outsiders cannot set labels


def _planted(tmp_path: Path, report: str, calls: list) -> Path:
    work = tmp_path / "run"
    (work / "project").mkdir(parents=True)
    (work / "home" / ".claude" / "skills").mkdir(parents=True)
    (work / "run.json").write_text(json.dumps({"harness": "claude", "harness_version": "test", "model": "opus",
                                               "request": "x", "exit": 0, "wall_s": 1}))
    rows = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": c}}]}}
            for c in calls]
    rows.append({"type": "result", "subtype": "success", "num_turns": len(calls), "total_cost_usd": 0.5,
                 "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 7}})
    (work / "transcript.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (work / "project" / "cad-agent-report.md").write_text(report)
    (work / "project" / "box.stl").write_text("solid x\nendsolid x\n")
    cli = work / "home" / "cad-agent" / "src" / "cadagent" / "cli.py"        # the commands the agent's clone defines
    cli.parent.mkdir(parents=True)
    cli.write_text('sub.add_parser("inserts", help="x")\nsub.add_parser("all", help="x")\nsub.add_parser("agents", help="x")\n')
    return work


def test_the_grader_reads_the_transcript_and_the_files(tmp_path):
    qe = _eval()
    report = "\n".join(f"## {h}\n{v}\n" for h, v in zip(qe.REPORT_HEADINGS, (
        "claude-opus-5-5", "Claude Code 2.1", "abc1234", "cad-agent inserts", "a box", "nothing", "https://x.org", "high")))
    calls = ["git clone --depth 1 -b main https://github.com/Valpatel/cad-agent ~/cad-agent",
             "~/cad-agent/.venv/bin/cad-agent agents install", "curl -s https://cad-agent.valpatel.com/llms.txt",
             "curl -s https://cad-agent.valpatel.com/docs/inserts.md", "cad-agent inserts --help",
             "cad-agent inserts spec.yaml", "python -c 'from cadagent.mechanical import inserts'"]
    g = qe.grade(_planted(tmp_path, report, calls))
    assert g["tool_calls"] == 7 and g["calls_to_install"] == 2 and g["calls_to_first_kit_use"] == 6
    assert g["discovery_calls_before_first_kit_use"] == 3
    assert g["kit_used"] == ["cadagent (Python)", "inserts"]
    assert g["clone_commit"] == "", "the planted clone is not a git checkout"
    c = g["checks"]
    assert c["read_llms_txt"] and c["used_kit_commands"] and c["made_a_part"] and c["report_has_every_heading"]
    assert c["report_model_filled"] and c["report_harness_filled"] and c["did_not_try_to_post"] and c["report_cites_a_source"]
    assert not c["installed"], "no venv in the planted home: graded from the files, not from the transcript"
    assert (g["tokens_in"], g["tokens_out"], g["turns"]) == (100, 7, 7)
    # Text the agent wrote (a heredoc, a report) is not a run; `git -C ~/cad-agent ...` is not a kit command; an import in
    # a file it wrote is kit use.
    written = ["cat > README.md <<'EOF'\nI did not run `cad-agent all`.\nEOF", "git -C ~/cad-agent rev-parse --short HEAD",
               "echo '## cad-agent commit'"]
    g2 = qe.grade(_planted(tmp_path / "c", report, written))
    assert g2["kit_used"] == [] and g2["calls_to_first_kit_use"] is None
    quoted = qe.grade(_planted(tmp_path / "q", report, ['"$HOME/cad-agent/.venv/bin/cad-agent" all']))
    assert quoted["kit_used"] == ["all"], "the block's own quoted form is a run"
    work = _planted(tmp_path / "d", report, ["$P/cad-agent all"])
    rows = (work / "transcript.jsonl").read_text().splitlines()
    wrote = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write",
                                                             "input": {"file_path": "b.py", "content": "from cadagent import geometry"}}]}}
    (work / "transcript.jsonl").write_text("\n".join([json.dumps(wrote), *rows]) + "\n")
    g3 = qe.grade(work)
    assert g3["kit_used"] == ["all", "cadagent (Python)"] and g3["calls_to_first_kit_use"] == 1
    posted = qe.grade(_planted(tmp_path / "b", "", calls + ["gh issue create -R Valpatel/cad-agent -t x -F r.md"]))
    assert not posted["checks"]["did_not_try_to_post"] and not posted["checks"]["report_has_every_heading"]


def test_the_grader_fails_a_session_that_loaded_someone_elses_setup(tmp_path):
    qe = _eval()
    work = _planted(tmp_path, "", ["cad-agent inserts spec.yaml"])
    rows = (work / "transcript.jsonl").read_text()
    init = {"type": "system", "subtype": "init", "cwd": str(work / "project"), "skills": ["simplify"],
            "mcp_servers": [], "plugins": [{"source": "x@builtin"}],
            "memory_paths": {"auto": str(work / "home" / ".claude" / "projects" / "m")}}
    (work / "transcript.jsonl").write_text(json.dumps(init) + "\n" + rows)
    assert qe.grade(work)["checks"]["fresh_session"]
    for change in ({"mcp_servers": [{"name": "mine"}]}, {"memory_paths": {"auto": "/elsewhere/memory"}},
                   {"plugins": [{"source": "mine@marketplace"}]}):
        (work / "transcript.jsonl").write_text(json.dumps({**init, **change}) + "\n" + rows)
        assert not qe.grade(work)["checks"]["fresh_session"], change


def test_the_grader_reads_empty_fields_posts_and_imports_honestly(tmp_path):
    qe = _eval()
    empty = "\n".join(f"## {h}\n" for h in qe.REPORT_HEADINGS)       # the template, nothing filled in
    g = qe.grade(_planted(tmp_path / "a", empty, ["cad-agent all"]))
    assert g["report"]["model"] == "" and not g["checks"]["report_model_filled"] and not g["checks"]["report_harness_filled"]
    assert g["checks"]["report_has_every_heading"] and not g["checks"]["report_cites_a_source"]
    bold = "**Model:** claude-x\n- Harness: Codex CLI\n"
    assert qe._sections(bold) == {"model": "claude-x", "harness": "Codex CLI"}
    assert qe._sections("## Model: claude-x\n## Harness\n") == {"model": "claude-x", "harness": ""}
    assert qe._sections("| Field | Value |\n|---|---|\n| Model | claude-x |\n| **Harness** | Codex CLI |\n") == {
        "model": "claude-x", "harness": "Codex CLI"}
    for post in ['git -C "$HOME/cad-agent" push origin x', "gh api repos/x/y/issues -f title=t", "gh issue comment 1 -b x",
                 "gh api --method POST repos/x/y/pulls", "curl -X POST https://api.github.com/repos/x/y/issues"]:
        assert not qe.grade(_planted(tmp_path / str(abs(hash(post))), empty, [post]))["checks"]["did_not_try_to_post"], post
    mention = ["cat > notes.md <<'EOF'\nfile it with gh issue create -R x/y\nEOF", "git -C ~/cad-agent rev-parse HEAD",
               "git config push.default simple", "gh api -X GET search/issues -f q=cad-agent"]
    assert qe.grade(_planted(tmp_path / "m", empty, mention))["checks"]["did_not_try_to_post"], "text it wrote is not a post"
    fed = ["python3 - <<'PY'\nfrom cadagent.mechanical import inserts\nPY", "cat > b.py <<'EOF'\nimport cadagent\nEOF\npython b.py"]
    assert qe.grade(_planted(tmp_path / "p", empty, fed))["kit_used"] == ["cadagent (Python)"]
    assert qe.grade(_planted(tmp_path / "e", empty, ["echo 'next: cad-agent all'"]))["kit_used"] == [], "printed, not run"
    assert qe.grade(_planted(tmp_path / "r", empty, ["cat /run/user/1000/bus"]))["checks"]["stayed_in_its_folder"] is False
