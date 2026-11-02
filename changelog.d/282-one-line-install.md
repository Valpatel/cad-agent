**New**
- One-line install: `curl -fsSL https://cad-agent.valpatel.com/install.sh | sh`, or on Windows
  `irm https://cad-agent.valpatel.com/install.ps1 | iex`. It needs git, installs uv if it is missing, clones `main`
  into `~/cad-agent`, installs the `cad-agent` command with `uv tool install --editable` (Python 3.12, in
  `~/.local/bin`) and adds the skills. Options: `--extras fea,sim`, `--ref vX.Y.Z`, `--dir`, `--uninstall`. Running
  it again updates (#282).
- `cad-agent update`: fast-forwards `main` (or moves to `--ref <tag>`), reinstalls only when `pyproject.toml` or
  `uv.lock` changed or `--extras` adds some, relinks the skills, prints the CHANGELOG since the old commit with
  "Projects must change" first, and in a project folder says what to re-run. It refuses a checkout with changes or
  on another branch. Its only network use is that git fetch (#282).
- `cad: {cad-agent: "0.14"}` in `cad-agent.yaml`: the oldest cad-agent a project builds with; `cad-agent all` refuses
  an older one, and notes when the checkout's last commit is more than 14 days old. `cad-agent-results.json` records
  the version that built it as `cad_agent` (#282).
- `cad-agent agents uninstall` removes every skill and subagent it placed (#282).

**Changed**
- Skills for Codex, Copilot CLI, Cursor, Gemini CLI and opencode go in `~/.agents/skills`, which they all read;
  `agents install` removes what earlier versions put in `~/.codex/skills`. `--target codex` is now `--target agents`
  (the old name still works). Where links are not allowed, it copies (#282).
- The README and the home page lead with the one-line install and an eight-word line to paste into an agent; the
  install and working rules moved into llms.txt (#282).

**Projects must change**
- Codex users: start a new Codex session after `cad-agent update` (or the installer) so it finds the skills in
  `~/.agents/skills` (#282).
