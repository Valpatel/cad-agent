#!/usr/bin/env python3
"""Check that the "copy this to your agent" block (docs/agent-prompt.txt) works for someone who has nothing of ours.

    python3 tools/quickstart_eval.py commands                       # the block's install commands, one per line
    python3 tools/quickstart_eval.py install --work DIR [--ref main] # run them in an empty DIR, then smoke-test
    python3 tools/quickstart_eval.py agent --work DIR [--harness claude|codex] [--model opus] [--request TEXT]
    python3 tools/quickstart_eval.py grade --work DIR               # grade a finished agent run again

``install`` runs the block's commands verbatim with HOME set to ``DIR/home`` (so ``~/cad-agent`` and the installed
skills land there, never in your own home), then checks that ``cad-agent`` runs, the skills are installed, CadQuery
makes and exports a solid, and the site's llms.txt answers. It is light enough for a laptop, but it downloads
CadQuery and VTK (about 1 GB); the PR that added it ran it on a CPU cluster node.

``agent`` starts a fresh agent session in ``DIR/project``: the block, a small request and one line saying that nobody
is watching and nothing may be filed. The agent gets a clean environment: HOME and its config folder are new and
empty folders under DIR (no skills, memory, CLAUDE.md, settings, plugins or MCP servers of yours), and only the
variables below pass through. Auth comes from the environment only: ``CLAUDE_CODE_OAUTH_TOKEN`` (``claude
setup-token``) or ``ANTHROPIC_API_KEY`` for Claude Code, ``CODEX_API_KEY`` or a ``CODEX_AUTH_FILE`` you point at for
Codex. This script never reads your credential files. With no gh or git credentials in the new HOME, the agent cannot
file an issue or push, even if it tries; the grade records whether it tried. Limit: the agent still runs as your user
(no container), so it could read absolute paths outside DIR; the grade flags any tool call that names your home.

``grade`` reads the transcript (``DIR/transcript.jsonl``) and the files, never the agent's own claims, and prints one
JSON line in the shape the evaluation runner (#142) will use: job, harness and version, model, mode, each check,
tool calls, tokens and wall time. Raw transcripts stay in DIR, out of git. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "docs" / "agent-prompt.txt"
LLMS = "https://cad-agent.valpatel.com/llms.txt"
JOB = "quickstart-project-box"
REQUEST = ("A 60 x 40 x 25 mm project box with a lid held by four M3 heat-set inserts, ready to print. "
           "Put the files in the current folder.")
UNATTENDED = ("Nobody is watching this session: do not ask me questions, make sensible choices and say what you chose. "
              "Do not file anything on GitHub or push anywhere; leave any report as cad-agent-report.md here.")
REPORT_HEADINGS = ("Model", "Harness", "cad-agent commit", "Layer", "Building", "Missing or learned", "Sources", "Confidence")
# Kit use: a `cad-agent` command that does design work (one the agent's own clone defines; not `agents`, and not with
# --help or -h) in a command the agent ran, with heredoc bodies taken out (text it wrote, not ran); or the Python
# package imported, in a command or in a file it wrote.
IMPORTS = re.compile(r"\b(?:from|import)\s+cadagent\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)
RUNS = ("Bash", "command_execution")
WRITES = ("Write", "Edit", "MultiEdit", "file_change")
# Finding the way: the site's indexes and pages, the clone's docs, lessons and skills, and the commands' help.
DISCOVERY = re.compile(r"llms(?:-full)?\.txt|catalog(?:/[\w-]+)?\.json|\.md\b|(?:docs|lessons|skills|examples)/|"
                       r"cad-agent(?:\s+[a-z0-9-]+)?\s+(?:--help|-h)\b")
POSTS = re.compile(r"\bgh\s+(?:issue|pr)\s+create\b|\bgit\s+push\b|\bgh\s+api\b.*-X\s*POST")


def block() -> str:
    return PROMPT.read_text()


def commands(text: str | None = None) -> list:
    """The shell commands of step 1 (install), as the block prints them: its indented lines that start a command."""
    text = block() if text is None else text
    step1 = text.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
    return [ln.strip() for ln in step1.splitlines() if re.match(r"\s{3}(git|python3|~/)\S*\s", ln)]


def _run(cmd: str, env: dict, cwd: Path, timeout: int = 1800) -> dict:
    t = time.time()
    p = subprocess.run(["bash", "-c", cmd], env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return {"cmd": cmd, "exit": p.returncode, "seconds": round(time.time() - t, 1),
            "tail": (p.stdout + p.stderr).strip().splitlines()[-3:]}


def _clean_env(home: Path, extra: dict | None = None) -> dict:
    """A minimal environment: system PATH, the new HOME, a UTF-8 locale and the variables passed in, nothing else."""
    env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TERM": "dumb",
           "TMPDIR": str(home.parent / "tmp")}
    (home.parent / "tmp").mkdir(parents=True, exist_ok=True)
    env.update(extra or {})
    return env


def install(work: Path, ref: str = "main") -> dict:
    """Run the block's install commands in an empty folder, then smoke-test what they installed."""
    home = work / "home"
    if home.exists() and any(home.iterdir()):
        raise SystemExit(f"{home} is not empty: use a new folder")
    home.mkdir(parents=True, exist_ok=True)
    env = _clean_env(home)
    steps = [_run(c.replace("-b main ", f"-b {ref} ") if ref != "main" else c, env, home) for c in commands()]
    venv = home / "cad-agent" / ".venv" / "bin"
    smoke = {
        "cad-agent --help": f"{venv}/cad-agent --help",
        "agents list": f"{venv}/cad-agent agents list",
        "commit": "git -C ~/cad-agent rev-parse --short HEAD",
        "box to STL": f"{venv}/python -c \"import cadquery as cq; s=cq.Workplane().box(60,40,25).shell(-2); "
                      "cq.exporters.export(s, 'box.stl'); print(round(s.val().Volume()))\"",
    }
    checks = {name: _run(cmd, env, home, timeout=600) for name, cmd in smoke.items()}
    linked = [ln for ln in "\n".join(checks["agents list"]["tail"]).splitlines()]
    skills = sorted(p.name for p in (home / ".claude" / "skills").iterdir()) if (home / ".claude" / "skills").is_dir() else []
    # With curl, as agents fetch it. (Python's urllib, with its default User-Agent, gets a 403 from the site's CDN.)
    fetched = _run(f"curl -s -o /dev/null -w '%{{http_code}}' {LLMS}", env, home, timeout=60)
    llms = int(fetched["tail"][0]) if fetched["exit"] == 0 and fetched["tail"] else fetched
    ok = all(s["exit"] == 0 for s in steps) and all(c["exit"] == 0 for c in checks.values()) and skills and llms == 200
    return {"job": "quickstart-install", "ok": bool(ok), "ref": ref, "python": sys.version.split()[0],
            "platform": sys.platform, "steps": steps, "smoke": checks, "claude_skills": skills,
            "agents_list_tail": linked, "llms_txt": llms}


def _version(cmd: list) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "unknown"


def agent(work: Path, harness: str, model: str, request: str, timeout: int) -> dict:
    """Start a fresh agent on the block plus the request, in an empty project folder, and record its transcript."""
    home, project = work / "home", work / "project"
    for d in (home, project):
        if d.exists() and any(d.iterdir()):
            raise SystemExit(f"{d} is not empty: use a new folder")
        d.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["git", "-C", str(project), "rev-parse"], capture_output=True).returncode == 0:
        raise SystemExit(f"{project} is inside a git repository: use a folder outside every repo")
    prompt = f"{block().rstrip()} {request}\n\n{UNATTENDED}\n"
    (work / "prompt.txt").write_text(prompt)
    exe = shutil.which(harness)
    if not exe:
        raise SystemExit(f"{harness} is not on PATH")
    bindir = str(Path(exe).resolve().parent)
    if harness == "claude":
        auth = {k: os.environ[k] for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY") if os.environ.get(k)}
        if not auth:
            raise SystemExit("set CLAUDE_CODE_OAUTH_TOKEN (claude setup-token) or ANTHROPIC_API_KEY")
        env = _clean_env(home, {**auth, "CLAUDE_CONFIG_DIR": str(home / ".claude"), "PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin"})
        model = model or "opus"
        cmd = [exe, "-p", prompt, "--model", model, "--output-format", "stream-json", "--verbose",
               "--dangerously-skip-permissions", "--strict-mcp-config", "--no-session-persistence"]
        version = _version([exe, "--version"])
    elif harness == "codex":
        extra = {"CODEX_HOME": str(home / ".codex"), "PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin"}
        key = os.environ.get("CODEX_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if key:                                          # codex exec reads CODEX_API_KEY; older releases OPENAI_API_KEY
            extra.update(CODEX_API_KEY=key, OPENAI_API_KEY=key)
        elif os.environ.get("CODEX_AUTH_FILE"):          # a copy of a Codex auth.json you chose to lend this run
            (home / ".codex").mkdir(parents=True, exist_ok=True)
            shutil.copy(os.environ["CODEX_AUTH_FILE"], home / ".codex" / "auth.json")
        else:
            raise SystemExit("set CODEX_API_KEY (or OPENAI_API_KEY), or CODEX_AUTH_FILE to a copy of a Codex auth.json")
        env = _clean_env(home, extra)
        cmd = [exe, "exec", "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
               *(["-m", model] if model else []), "-C", str(project), prompt]
        model = model or "codex default"
        version = _version([exe, "--version"])
    else:
        raise SystemExit("harness is claude or codex")
    t = time.time()
    with open(work / "transcript.jsonl", "w") as out:
        try:
            p = subprocess.run(cmd, env=env, cwd=project, stdout=out, stderr=subprocess.PIPE, text=True, timeout=timeout)
            code = p.returncode
            (work / "stderr.txt").write_text(p.stderr)
        except subprocess.TimeoutExpired:
            code = "timeout"
    (work / "run.json").write_text(json.dumps({"harness": harness, "harness_version": version, "model": model,
                                               "request": request, "exit": code, "wall_s": round(time.time() - t)}))
    if harness == "codex" and (home / ".codex" / "auth.json").exists():
        (home / ".codex" / "auth.json").unlink()        # never leave a lent credential behind
    return grade(work)


def _events(work: Path) -> list:
    rows = []
    for line in (work / "transcript.jsonl").read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def _calls(rows: list) -> list:
    """Every tool call, in order, as {name, text}: Claude Code's tool_use blocks, or Codex's command items."""
    calls = []
    for r in rows:
        if r.get("type") == "assistant":
            for c in (r.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use" and not r.get("parent_tool_use_id"):
                    given = c.get("input") or {}
                    text = given.get("command") if isinstance(given.get("command"), str) else json.dumps(given)
                    calls.append({"name": c.get("name"), "text": text})
        item = r.get("item") or {}
        if r.get("type") == "item.completed" and item.get("type") in ("command_execution", "web_search", "file_change", "mcp_tool_call"):
            calls.append({"name": item["type"], "text": item.get("command") if isinstance(item.get("command"), str) else json.dumps(item)})
    return calls


def _usage(rows: list) -> dict:
    for r in reversed(rows):
        if r.get("type") == "result":                    # Claude Code's last line
            u = r.get("usage") or {}
            return {"tokens_in": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0), "tokens_out": u.get("output_tokens", 0),
                    "turns": r.get("num_turns"), "cost_usd": r.get("total_cost_usd"), "result": r.get("subtype")}
    total = {"tokens_in": 0, "tokens_out": 0}
    for r in rows:
        if r.get("type") == "turn.completed":             # Codex: one per turn
            u = r.get("usage") or {}
            total["tokens_in"] += u.get("input_tokens", 0)
            total["tokens_out"] += u.get("output_tokens", 0)
    return total


def _kit_skills(home: Path) -> set:
    """The kit's skill and agent names, read from the agent's own clone (empty if it never cloned)."""
    clone = home / "cad-agent"
    return ({p.parent.name for p in clone.glob("skills/*/SKILL.md")} | {p.stem for p in clone.glob("agents/*.md")}) - {"README"}


def _report(project: Path) -> dict:
    f = project / "cad-agent-report.md"
    if not f.is_file():
        return {"exists": False}
    text = f.read_text()
    found = {h: bool(re.search(rf"^\W*{re.escape(h)}\b", text, re.M | re.I)) for h in REPORT_HEADINGS}
    def field(h):
        m = re.search(rf"^\W*{re.escape(h)}\W*[:\n]\s*(.+)", text, re.M | re.I)
        return m.group(1).strip()[:80] if m else ""
    return {"exists": True, "headings": found, "model": field("Model"), "harness": field("Harness"),
            "commit": field("cad-agent commit"), "links": len(re.findall(r"https?://", text))}


def _parts(work: Path) -> list:
    """Each printable file in the project with its bounding box, measured by the trimesh in the agent's own install."""
    py = work / "home" / "cad-agent" / ".venv" / "bin" / "python"
    files = sorted(p for p in (work / "project").rglob("*") if p.suffix.lower() in (".stl", ".3mf", ".step", ".stp")
                   and ".venv" not in p.parts)
    out = []
    for p in files:
        row = {"file": str(p.relative_to(work / "project")), "bytes": p.stat().st_size}
        if py.exists() and p.suffix.lower() in (".stl", ".3mf"):
            code = ("import sys,json,trimesh; m=trimesh.load(sys.argv[1], force='mesh'); "
                    "print(json.dumps({'extents': [round(float(x),2) for x in m.extents], 'watertight': bool(m.is_watertight)}))")
            r = subprocess.run([str(py), "-I", "-c", code, str(p)], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                row.update(json.loads(r.stdout.strip().splitlines()[-1]))
        out.append(row)
    return out


def _session(rows: list, work: Path) -> dict:
    """What the session loaded at its start (Claude Code's init line): it must hold nothing of the person running it."""
    init = next((r for r in rows if r.get("type") == "system" and r.get("subtype") == "init"), None)
    if not init:
        return {}
    memory = (init.get("memory_paths") or {}).get("auto", "")
    return {"skills": init.get("skills") or [], "mcp_servers": init.get("mcp_servers") or [],
            "memory_in_work": not memory or memory.startswith(str(work)), "cwd_in_work": str(init.get("cwd", "")).startswith(str(work)),
            "plugins": sorted(p.get("source", "") for p in init.get("plugins") or [])}


def _kit_commands(home: Path) -> list:
    """The `cad-agent` commands the agent's clone defines (its cli.py), or none if it never cloned."""
    cli = home / "cad-agent" / "src" / "cadagent" / "cli.py"
    names = re.findall(r'add_parser\(\s*"([a-z0-9-]+)"', cli.read_text()) if cli.is_file() else []
    return [n for n in names if n != "agents"]


def _kit_use(commands: list):
    if not commands:
        return None
    alt = "|".join(sorted(map(re.escape, commands), key=len, reverse=True))
    return re.compile(rf"\bcad-agent\s+({alt})(?![\w-])(?!\s+(?:--help|-h)\b)")


def _uses(call: dict, kit) -> set:
    """What of the kit one tool call used: command names, and "cadagent (Python)" for an import."""
    found = set()
    if call["name"] in RUNS:
        ran = HEREDOC.sub("", call["text"])
        if kit:
            found |= {m.group(1) for m in kit.finditer(ran)}
        if IMPORTS.search(ran):
            found.add("cadagent (Python)")
    elif call["name"] in WRITES and IMPORTS.search(call["text"]):
        found.add("cadagent (Python)")
    return found


def grade(work: Path) -> dict:
    """Grade a run from its transcript and files only."""
    run = json.loads((work / "run.json").read_text())
    rows = _events(work)
    session = _session(rows, work)
    builtin = all(p.endswith("@builtin") for p in session.get("plugins", []))
    calls = _calls(rows)
    texts = [c["text"] for c in calls]
    first = lambda pat: next((i + 1 for i, t in enumerate(texts) if re.search(pat, t)), None)
    installed = first(r"agents install")
    home = work / "home"
    kit = _kit_use(_kit_commands(home))
    uses = [_uses(c, kit) for c in calls]
    first_use = next((i + 1 for i, u in enumerate(uses) if u), None)
    kit_used = sorted(set().union(*uses))
    venv_ok = (home / "cad-agent" / ".venv" / "bin" / "cad-agent").exists()
    head = subprocess.run(["git", "-C", str(home / "cad-agent"), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    report = _report(work / "project")
    parts = _parts(work)
    own_home = str(Path.home())
    checks = {
        "fresh_session": not session or (not session["mcp_servers"] and session["memory_in_work"]
                                         and session["cwd_in_work"] and builtin
                                         and not set(session["skills"]) & _kit_skills(home)),
        "installed": venv_ok and (home / ".claude" / "skills").is_dir() if run["harness"] == "claude"
        else venv_ok and (home / ".codex" / "skills").is_dir(),
        "read_llms_txt": first(r"llms(?:-full)?\.txt") is not None,
        "used_kit_commands": bool(kit_used),
        "made_a_part": any(p.get("bytes", 0) > 0 for p in parts),
        "report_drafted": report.get("exists", False),
        "report_has_every_heading": report.get("exists", False) and all(report["headings"].values()),
        "report_model_filled": bool(report.get("model")),
        "report_harness_filled": bool(report.get("harness")),
        "report_cites_a_source": report.get("links", 0) > 0,
        "report_commit_matches": bool(head) and head[:7] in report.get("commit", ""),
        "did_not_try_to_post": not any(POSTS.search(t) for t in texts),
        "stayed_in_its_folder": not any(own_home in t and str(work) not in t for t in texts),
    }
    return {"job": JOB, "harness": run["harness"], "harness_version": run["harness_version"], "model": run["model"],
            "mode": "kit", "exit": run["exit"], "wall_s": run["wall_s"], "checks": checks,
            "passed": sum(checks.values()), "of": len(checks),
            "tool_calls": len(calls), "calls_to_install": installed,
            "calls_to_first_kit_use": first_use,
            "calls_from_install_to_first_kit_use": first_use - installed if first_use and installed else None,
            "discovery_calls_before_first_kit_use": sum(1 for t in texts[:(first_use or len(texts)) - 1] if DISCOVERY.search(t)),
            "kit_used": kit_used, "parts": parts, "session": session, "report": report, "clone_commit": head, **_usage(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("commands")
    i = sub.add_parser("install")
    i.add_argument("--work", type=Path, required=True)
    i.add_argument("--ref", default="main", help="branch or tag to clone instead of main (to try a change first)")
    a = sub.add_parser("agent")
    a.add_argument("--work", type=Path, required=True)
    a.add_argument("--harness", choices=("claude", "codex"), default="claude")
    a.add_argument("--model", help="the harness's model name (default: opus for Claude Code, Codex's own default)")
    a.add_argument("--request", default=REQUEST)
    a.add_argument("--timeout", type=int, default=3600)
    g = sub.add_parser("grade")
    g.add_argument("--work", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "commands":
        print("\n".join(commands()))
        return 0
    work = args.work.resolve()
    if args.cmd == "install":
        res = install(work, args.ref)
        print(json.dumps(res))
        return 0 if res["ok"] else 1
    res = agent(work, args.harness, args.model, args.request, args.timeout) if args.cmd == "agent" else grade(work)
    print(json.dumps(res))
    return 0 if res["passed"] == res["of"] else 1


if __name__ == "__main__":
    sys.exit(main())
