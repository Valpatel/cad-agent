"""What people paste and what agents read (#278, #282): docs/agent-prompt.txt.

Its first line is what a person pastes into an agent; the rest is how to install and work with the kit, which llms.txt
carries. The root README answers what/why/join, with installation detail one click away (the site's card, llms.txt and
index.md are checked in tests/site/website-build.test.mjs). Here: the README stays short; the install commands are the
public ones and name real `cad-agent` commands; the report headings match the issue form, the PR template and the
grader in tools/quickstart_eval.py; it asks nothing risky of an outside agent; and the grader reads a planted run the
way it reads a real one.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BLOCK = (ROOT / "docs" / "agent-prompt.txt").read_text()
PASTE, GUIDE = BLOCK.split("\n", 1)
README = (ROOT / "README.md").read_text()
INSTALL_URL = "https://cad-agent.valpatel.com/docs/agent-workflow#install"


def _eval():
    spec = importlib.util.spec_from_file_location("quickstart_eval", ROOT / "tools" / "quickstart_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readme_is_a_mini_hyperpage_with_install_detail_one_click_away():
    headings = re.findall(r"^## (.+)$", README, re.M)
    assert headings == ['What is it?', 'Why this is cool', 'How to join in']
    use_it = README.split('## How to join in\n', 1)[1]
    guide = (ROOT / 'docs/practice/agent-workflow.md').read_text()
    assert 'docs/practice/agent-workflow.md#install' in use_it
    assert 'docs/practice/agent-workflow.md#ask-your-assistant' in use_it
    assert '## Install\n' in guide and '### Ask your assistant\n' in guide
    assert '<details id="install-unix">' in guide and '<details id="install-windows">' in guide
    assert 'checked-installer:posix' in guide and 'checked-installer:powershell' in guide
    assert 'pinned installer' in " ".join(use_it.split()), 'one obvious checked installation route remains on the root'
    assert not re.search(r"curl.*\|\s*sh|irm.*\|\s*iex", use_it), 'do not duplicate an unchecked execution shortcut'
    assert "```text\n" + PASTE + "\n```" in guide, "the canonical paste line is one click away"
    def prose_words(text):
        # Linked image badges are navigation/status, exempt from the visitor's prose budget.
        without_badges = re.sub(r'\[!\[[^\]]*\]\([^\s)]+\)\]\([^\s)]+\)', '', text)
        return len(re.sub(r'<[^>]+>', '', without_badges).split())

    words = prose_words(README)
    assert prose_words(README + '\n' + '[![status](https://example.org/badge.svg)](https://example.org)\n' * 400) == words
    assert words <= 350, f"{words} words: keep the root a short entrance, not a manual"
    flat = " ".join(use_it.split())
    assert "collects no telemetry" in flat and "only if you say yes" in flat
    assert "## Quick start" not in README, "one quick start: the first section replaced it"


def test_the_paste_in_line_is_short_and_points_at_llms_txt():
    assert PASTE == "Install cad-agent from https://cad-agent.valpatel.com/llms.txt, then use it for:"
    assert len(PASTE.split()) == 8 and GUIDE.startswith("\n"), "one line, then a blank line"


def test_commands_are_public_and_name_real_commands(tmp_path, monkeypatch):
    qe = _eval()
    cmds = qe.commands()
    assert len(cmds) == 1 and 'Installer checksum mismatch' in cmds[0]
    assert INSTALL_URL in BLOCK and 'checksum-before-execution' in BLOCK
    for control in ('', '<!-- checked-installer:posix -->\n```sh\necho incomplete'):
        with pytest.raises(ValueError, match="exactly one"):
            qe.commands(control)
    with pytest.raises(ValueError, match="exactly one"):
        qe.commands(qe.INSTALL_GUIDE.read_text() * 2)
    assert "`cad-agent update`" in BLOCK, "an agent that finds it installed updates first"
    from cadagent.cli import build_parser
    names = set(build_parser()._subparsers._group_actions[0].choices)
    named = set(re.findall(r"(?:bin/|`)cad-agent\"? ([a-z][a-z0-9-]+)", BLOCK))
    assert named and named <= names, f"the block names commands that do not exist: {named - names}"
    for url in re.findall(r"(?:https?://)?[\w.-]+\.(?:com|org|net|dev)[\w/.<>-]*", BLOCK):
        assert re.match(r"(?:https://)?(github\.com/Valpatel/cad-agent|cad-agent\.valpatel\.com)\b", url), url

    # Exercise the evaluator's actual --local selection, not only the directly tested installer path. Appending
    # the real script's --help reaches its option parser without downloading, cloning or installing anything.
    # Stop before a second install or the separate CAD/network smoke checks: this proves dispatch, not full setup.
    run = qe._run
    calls = []
    work = tmp_path / "local evaluation"

    class LocalInstallerReached(Exception):
        pass

    def local_help(cmd, env, cwd, timeout=1800):
        assert not calls, "stop after the first local installer dispatch"
        calls.append(cmd)
        assert cwd == work / "home" and ROOT not in cwd.parents
        result = run(cmd + " --help", env, cwd, timeout=10)
        assert result["exit"] == 0, result
        assert any(line.startswith("cad-agent: install or update cad-agent:") for line in result["said"]), result
        raise LocalInstallerReached

    monkeypatch.setattr(qe, "_run", local_help)
    with pytest.raises(LocalInstallerReached):
        qe.main(["install", "--work", str(work), "--local", "--ref", "main"])
    assert len(calls) == 1 and not (work / "home" / "cad-agent").exists()


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
    piped = re.findall(r"[^\n]*\|\s*(?:ba|z)?sh\b[^\n]*|[^\n]*curl\b[^\n]*\|[^\n]*", BLOCK)
    assert not piped, "the agent reads the canonical checked guide, without an unsafe pipe shortcut"
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
    cli = work / "home" / "cad-agent" / "software" / "cadagent" / "cli.py"        # the commands the agent's clone defines
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


def test_the_grader_rejects_preloaded_current_canonical_kit_names(tmp_path):
    qe = _eval()
    work = _planted(tmp_path, "", ["cad-agent inserts spec.yaml"])
    clone = work / "home" / "cad-agent"
    skill = clone / ".agents" / "skills" / "design-process" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Design process\n")
    role = clone / ".agents" / "agents" / "cad-resume.md"
    role.parent.mkdir(parents=True)
    role.write_text("# Resume\n")
    assert qe._kit_skills(work / "home") == {"design-process", "cad-resume"}
    transcript = (work / "transcript.jsonl").read_text()
    init = {"type": "system", "subtype": "init", "cwd": str(work / "project"), "skills": [],
            "mcp_servers": [], "plugins": [],
            "memory_paths": {"auto": str(work / "home" / ".claude" / "projects" / "memory")}}
    for names, fresh in (([], True), (["design-process"], False), (["cad-resume"], False)):
        (work / "transcript.jsonl").write_text(json.dumps({**init, "skills": names}) + "\n" + transcript)
        assert qe.grade(work)["checks"]["fresh_session"] is fresh, names
    # Old real transcripts can still be graded against their actual old clone layout.
    legacy = tmp_path / "legacy" / "cad-agent" / "skills" / "old-skill" / "SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# Historical kit\n")
    assert qe._kit_skills(tmp_path / "legacy") == {"old-skill"}


@pytest.mark.skipif(__import__('os').name == 'nt', reason='the evaluator uses a POSIX tool HOME; Windows installer proof is separate')
@pytest.mark.parametrize('case', ['usable', 'logged-out', 'ambiguous-env', 'codex', 'nonempty-work'])
def test_explicit_normal_login_route_is_scoped_and_never_lends_credentials(tmp_path, monkeypatch, case):
    import sys

    qe = _eval()
    normal = tmp_path / 'existing-normal-config'
    normal.mkdir()
    credential = normal / 'private-auth-fixture.json'
    credential.write_text('{"fixture":"not a real credential; must not be copied"}')
    original = credential.read_bytes()
    work = tmp_path / 'current-flow'
    runtime = tmp_path / 'existing-runtime'
    runtime.mkdir()
    userbin = tmp_path / 'unrelated-user-bin'
    userbin.mkdir()
    fake = runtime / 'claude-fixture'
    fake.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if '--version' in args:
 print('2.1.319 (inert CLI fixture)');sys.exit(0)
if 'auth' in args and 'status' in args:
 print(json.dumps({{'loggedIn':{case != 'logged-out'!r},'authMethod':'claude.ai','configDirectory':os.environ['CLAUDE_CONFIG_DIR']}}));sys.exit(0)
work=Path(os.environ['HOME']).parent
(work/'observed-model-request.json').write_text(json.dumps({{'argv':args,'environment':dict(os.environ)}}))
print(json.dumps({{'type':'system','subtype':'init','cwd':str(Path.cwd()),'skills':[],'mcp_servers':[],'plugins':[],
                  'memory_paths':{{'auto':str(Path(os.environ['HOME'])/'.claude/memory')}}}}))
print(json.dumps({{'type':'result','subtype':'success'}}))
''')
    fake.chmod(0o755)
    link = userbin / 'claude'
    link.symlink_to(fake)
    (userbin / 'cad-agent').write_text('foreign user command must not be lent')
    which = qe.shutil.which
    monkeypatch.setattr(qe.shutil, 'which', lambda name: str(link) if name in ('claude', 'codex') else which(name))
    for name in ('CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'CODEX_API_KEY', 'OPENAI_API_KEY', 'CODEX_AUTH_FILE'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('DO_NOT_LEND_THIS_FIXTURE', 'outside context')
    if case == 'ambiguous-env':
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'inert-fixture-not-a-key')
    if case == 'nonempty-work':
        work.mkdir()
        (work / 'leave-me.txt').write_text('existing evidence stays exact')
    harness = 'codex' if case == 'codex' else 'claude'
    if case != 'usable':
        with pytest.raises(SystemExit):
            qe.agent(work, harness, 'opus', qe.REQUEST, 5, normal_auth_config=normal)
        assert not (work / 'observed-model-request.json').exists(), 'failed metadata/scope guard must reach no model'
    else:
        result = qe.agent(work, harness, 'opus', qe.REQUEST, 5, normal_auth_config=normal)
        observed = json.loads((work / 'observed-model-request.json').read_text())
        argv, env = observed['argv'], observed['environment']
        assert argv[argv.index('-p') + 1] == f'{qe.paste_line()} {qe.REQUEST}\n\n{qe.UNATTENDED}\n'
        for flag in ('--safe-mode', '--strict-mcp-config', '--no-session-persistence'):
            assert flag in argv
        assert argv[argv.index('--setting-sources') + 1] == ''
        assert argv[argv.index('--agent') + 1] == 'general-purpose'
        assert argv[argv.index('--max-budget-usd') + 1] == '5'
        assert argv[argv.index('--tools') + 1] == 'Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch'
        assert env['HOME'] == str(work / 'home') and env['CLAUDE_CONFIG_DIR'] == str(normal)
        assert env['PATH'].split(':')[0] == str(runtime) and str(userbin) not in env['PATH'].split(':')
        assert env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] == '1' and env['GIT_CONFIG_GLOBAL'] == qe.os.devnull
        assert 'DO_NOT_LEND_THIS_FIXTURE' not in env and 'ANTHROPIC_API_KEY' not in env
        assert result['session_boundary'] == 'normal-login-safe-mode'
        assert result['checks']['fresh_session'] is None and result['of'] == 12, 'normal login must not score as clean-user proof'
    assert credential.read_bytes() == original
    if (work / 'home').exists():
        assert not list((work / 'home').rglob('private-auth-fixture.json'))
    if case == 'nonempty-work':
        assert (work / 'leave-me.txt').read_text() == 'existing evidence stays exact'
