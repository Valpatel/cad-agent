# kicad-happy 2fd9aa0fe2 -> 2fd9aa0fe2 (MIT)

Full scan of 213 files.
New findings (not in the reviewed baseline): HIGH 25, MEDIUM 117, LOW 46. Suppressed by baseline: 0.

## HIGH

| rule | file:line | text |
|---|---|---|
| credential-read | `github-action.md:60` | `if: github.event_name == 'pull_request' && env.ANTHROPIC_API_KEY != ''` |
| credential-read | `github-action.md:62` | `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `github-action.md:64` | `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `github-action.md:65` | `github_token: ${{ secrets.GITHUB_TOKEN }}` |
| credential-read | `github-action.md:84` | `if: github.event_name == 'pull_request' && env.ANTHROPIC_API_KEY != ''` |
| credential-read | `github-action.md:86` | `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `github-action.md:88` | `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `github-action.md:89` | `github_token: ${{ secrets.GITHUB_TOKEN }}` |
| credential-read | `github-action.md:110` | `Get an API key from [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys), then add it as a repository secret n` |
| credential-read | `github-action.md:118` | `if: github.event_name == 'pull_request' && env.OPENAI_API_KEY != ''` |
| credential-read | `github-action.md:120` | `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` |
| credential-read | `github-action.md:143` | `if: github.event_name == 'pull_request' && env.ANTHROPIC_API_KEY != ''` |
| credential-read | `github-action.md:145` | `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `github-action.md:146` | `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` |
| credential-read | `github-action.md:150` | `use_github_token: true` |
| credential-read | `github-action.md:164` | `Set the `model` field to any Models.dev id (e.g. `openai/gpt-5`, `zai-coding-plan/glm-5.1`) and match the env var to that provider's key. `u` |
| credential-read | `install-guidance.md:571` | `if: github.event_name == 'pull_request' && env.ANTHROPIC_API_KEY != ''` |
| credential-read | `install-guidance.md:573` | `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `install-guidance.md:575` | `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` |
| credential-read | `install-guidance.md:576` | `github_token: ${{ secrets.GITHUB_TOKEN }}` |
| credential-read | `install-guidance.md:595` | `if: github.event_name == 'pull_request' && env.OPENAI_API_KEY != ''` |
| credential-read | `install-guidance.md:597` | `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` |
| credential-read | `install-guidance.md:616` | `/ `ANTHROPIC_API_KEY` / [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) / Claude AI review /` |
| credential-read | `install-guidance.md:617` | `/ `OPENAI_API_KEY` / OpenAI platform dashboard / Codex AI review /` |
| credential-read | `release-notes.md:196` | `/ **GitHub Action**        / Two-tier automated PR reviews: deterministic analysis (free, no API key) + optional AI-powered review via Claud` |

## MEDIUM

| rule | file:line | text |
|---|---|---|
| telemetry | `emc-precompliance.md:190` | `**Switching harmonic FFT (EE-002)** — Instead of the analytical trapezoidal envelope approximation, runs a transient SPICE simulation of the` |
| subprocess | `skills/datasheets/scripts/datasheet_page_selector.py:185` | `result = subprocess.run(` |
| subprocess | `skills/datasheets/scripts/datasheet_page_selector.py:221` | `result = subprocess.run(` |
| subprocess | `skills/datasheets/scripts/datasheet_page_selector.py:251` | `result = subprocess.run(` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:36` | `import urllib.request` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:103` | `req = urllib.request.Request(` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:108` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:143` | `req = urllib.request.Request(` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:152` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:238` | `resp = _requests.get(` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:254` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/digikey/scripts/fetch_datasheet_digikey.py:255` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| subprocess | `skills/digikey/scripts/fetch_datasheet_digikey.py:328` | `result = subprocess.run(` |
| network | `skills/digikey/scripts/sync_datasheets_digikey.py:37` | `import urllib.request` |
| network | `skills/digikey/scripts/sync_datasheets_digikey.py:104` | `req = urllib.request.Request(` |
| network | `skills/digikey/scripts/sync_datasheets_digikey.py:109` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/digikey/scripts/sync_datasheets_digikey.py:125` | `req = urllib.request.Request(` |
| network | `skills/digikey/scripts/sync_datasheets_digikey.py:134` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| subprocess | `skills/digikey/scripts/sync_datasheets_digikey.py:282` | `result = subprocess.run(` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:34` | `import urllib.request` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:116` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:117` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:228` | `resp = _requests.get(` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:244` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/element14/scripts/fetch_datasheet_element14.py:245` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| subprocess | `skills/element14/scripts/fetch_datasheet_element14.py:305` | `result = subprocess.run(` |
| subprocess | `skills/element14/scripts/sync_datasheets_element14.py:197` | `result = subprocess.run(` |
| telemetry | `skills/emc/references/pcb-emc-rules.md:75` | `- **Rationale:** SMPS harmonics in the 30–300 MHz range are the #1 cause of radiated emissions failures. The harmonic amplitude envelope fol` |
| telemetry | `skills/emc/scripts/emc_formulas.py:220` | `def trapezoidal_harmonic_amplitude(n: int, v_peak: float, duty_cycle: float,` |
| telemetry | `skills/emc/scripts/emc_formulas.py:223` | `"""Amplitude of the nth harmonic of a trapezoidal switching waveform.` |
| telemetry | `skills/emc/scripts/emc_formulas.py:235` | `Amplitude of the nth harmonic in Volts.` |
| telemetry | `skills/emc/scripts/emc_formulas.py:242` | `# Base amplitude` |
| telemetry | `skills/emc/scripts/emc_formulas.py:301` | `List of dicts with keys: harmonic, freq_hz, amplitude_v, amplitude_dbuv.` |
| telemetry | `skills/emc/scripts/emc_formulas.py:312` | `amp = trapezoidal_harmonic_amplitude(n, v_peak, duty_cycle,` |
| telemetry | `skills/emc/scripts/emc_formulas.py:318` | `'amplitude_v': amp,` |
| telemetry | `skills/emc/scripts/emc_formulas.py:319` | `'amplitude_dbuv': amp_dbuv,` |
| telemetry | `skills/emc/scripts/emc_formulas.py:772` | `# v_diff: differential signal amplitude (Volts, peak)` |
| telemetry | `skills/emc/scripts/emc_formulas.py:837` | `v_diff: Differential signal amplitude in Volts.` |
| telemetry | `skills/emc/scripts/emc_rules.py:25` | `trapezoidal_harmonic_amplitude, dm_radiation_dbuv_m, dm_max_loop_area_m2,` |
| telemetry | `skills/emc/scripts/emc_rules.py:1039` | `# Estimate amplitude of strongest harmonic in this band` |
| telemetry | `skills/emc/scripts/emc_rules.py:1041` | `amp = trapezoidal_harmonic_amplitude(` |
| telemetry | `skills/emc/scripts/emc_rules.py:1619` | `harmonic amplitudes and compares against the analytical envelope.` |
| telemetry | `skills/emc/scripts/emc_rules.py:1646` | `# SPICE FFT enhancement: get actual harmonic amplitudes` |
| telemetry | `skills/emc/scripts/emc_rules.py:1658` | `env_amp = trapezoidal_harmonic_amplitude(` |
| telemetry | `skills/emc/scripts/emc_rules.py:1662` | `f'h{h["harmonic"]}={h["amplitude_dbuv"]:.0f}dBµV '` |
| telemetry | `skills/emc/scripts/emc_spice.py:375` | `{harmonic, freq_hz, amplitude_v, amplitude_dbuv} dicts.` |
| telemetry | `skills/emc/scripts/emc_spice.py:482` | `'amplitude_v': mag,` |
| telemetry | `skills/emc/scripts/emc_spice.py:483` | `'amplitude_dbuv': mag_dbuv,` |
| eval-exec | `skills/kicad/SKILL.md:835` | ``eval()`, `exec()`, or any code execution primitive. The parser produces` |
| subprocess | `skills/kicad/review/scripts/deep_review_gate.py:227` | `text = subprocess.run(cmd, capture_output=True, text=True,` |
| subprocess | `skills/kicad/review/scripts/deep_review_gate.py:229` | `except (subprocess.CalledProcessError, OSError):` |
| subprocess | `skills/kicad/review/scripts/run_phase4_exercise.py:42` | `result = subprocess.run(cmd, cwd=cwd or REPO_ROOT,` |
| subprocess | `skills/kicad/scripts/export_issues.py:264` | `result = subprocess.run(` |
| subprocess | `skills/kicad/scripts/export_issues.py:282` | `result = subprocess.run(` |
| subprocess | `skills/kicad/scripts/export_issues.py:328` | `result = subprocess.run(` |
| network | `skills/kicad/scripts/lifecycle_audit.py:35` | `import urllib.request` |
| network | `skills/kicad/scripts/lifecycle_audit.py:195` | `req = urllib.request.Request(` |
| network | `skills/kicad/scripts/lifecycle_audit.py:200` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:219` | `req = urllib.request.Request(` |
| network | `skills/kicad/scripts/lifecycle_audit.py:228` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:282` | `req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})` |
| network | `skills/kicad/scripts/lifecycle_audit.py:283` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:318` | `req = urllib.request.Request(url, headers={"User-Agent": "kicad-happy-lifecycle/1.0"})` |
| network | `skills/kicad/scripts/lifecycle_audit.py:319` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:369` | `req = urllib.request.Request(url, headers={"Accept": "application/json"})` |
| network | `skills/kicad/scripts/lifecycle_audit.py:370` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:542` | `req = urllib.request.Request(url, data=body,` |
| network | `skills/kicad/scripts/lifecycle_audit.py:544` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:570` | `req = urllib.request.Request(` |
| network | `skills/kicad/scripts/lifecycle_audit.py:579` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/kicad/scripts/lifecycle_audit.py:608` | `req = urllib.request.Request(url, headers={"User-Agent": "kicad-happy-lifecycle/1.0"})` |
| network | `skills/kicad/scripts/lifecycle_audit.py:609` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| subprocess | `skills/kicad/scripts/what_if.py:1201` | `subprocess.run(cmd, capture_output=True, timeout=30, check=False)` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:32` | `import urllib.request` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:91` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:92` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:139` | `req = urllib.request.Request(url, headers={` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:143` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:312` | `resp = _requests.get(` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:328` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:329` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| subprocess | `skills/lcsc/scripts/fetch_datasheet_lcsc.py:389` | `result = subprocess.run(` |
| network | `skills/lcsc/scripts/search_lcsc.py:30` | `import urllib.request` |
| network | `skills/lcsc/scripts/search_lcsc.py:66` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/lcsc/scripts/search_lcsc.py:67` | `with urllib.request.urlopen(req, timeout=15) as resp:` |
| subprocess | `skills/lcsc/scripts/sync_datasheets_lcsc.py:196` | `result = subprocess.run(` |
| network | `skills/lcsc/scripts/test_search_lcsc.py:84` | `def _mock_urlopen(payload: dict):` |
| network | `skills/lcsc/scripts/test_search_lcsc.py:85` | `"""Build a urlopen replacement returning ``payload`` as JSON."""` |
| network | `skills/lcsc/scripts/test_search_lcsc.py:96` | `with patch("urllib.request.urlopen", _mock_urlopen({"components": [SEARCH_HIT]})) as mock_open:` |
| network | `skills/lcsc/scripts/test_search_lcsc.py:104` | `with patch("urllib.request.urlopen", _mock_urlopen({"resistors": [CATEGORY_ROW]})) as mock_open:` |
| network | `skills/lcsc/scripts/test_search_lcsc.py:112` | `with patch("urllib.request.urlopen", _mock_urlopen({"error": "not found"})):` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:44` | `import urllib.request` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:87` | `req = urllib.request.Request(` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:93` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:152` | `resp = _requests.get(` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:168` | `req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:169` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:273` | `resp = _requests.get(product_url, headers=headers, timeout=20,` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:283` | `req = urllib.request.Request(product_url, headers=headers)` |
| network | `skills/mouser/scripts/fetch_datasheet_mouser.py:284` | `with urllib.request.urlopen(req, timeout=20) as resp:` |
| subprocess | `skills/mouser/scripts/fetch_datasheet_mouser.py:344` | `result = subprocess.run(` |
| subprocess | `skills/mouser/scripts/sync_datasheets_mouser.py:200` | `result = subprocess.run(` |
| subprocess | `skills/spice/scripts/spice_simulator.py:113` | `result = subprocess.run(` |
| subprocess | `skills/spice/scripts/spice_simulator.py:252` | `result = subprocess.run(` |
| subprocess | `skills/spice/scripts/spice_simulator.py:365` | `result = subprocess.run(` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:18` | `import urllib.request` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:199` | `req = urllib.request.Request(url, headers={"User-Agent": "kicad-happy-spice/1.0"})` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:200` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:264` | `req = urllib.request.Request(` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:269` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:298` | `req = urllib.request.Request(` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:307` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:360` | `req = urllib.request.Request(url, headers={"Accept": "application/json"})` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:361` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:403` | `req = urllib.request.Request(` |
| network | `skills/spice/scripts/spice_spec_fetcher.py:407` | `with urllib.request.urlopen(req, timeout=10) as resp:` |
| subprocess | `skills/spice/scripts/spice_spec_fetcher.py:489` | `result = subprocess.run(` |

## LOW

| rule | file:line | text |
|---|---|---|
| home-write | `CHANGELOG.md:1035` | `- Cascading config: project-level merges with user-level `~/.kicad-happy.json`` |
| home-write | `README.md:107` | `> rm -rf ~/.claude/plugins/cache/kicad-happy ~/.claude/plugins/marketplaces/kicad-happy` |
| home-write | `README.md:118` | `If you prefer a manual install, install the skills into `~/.codex/skills/`.` |
| home-write | `README.md:163` | `mkdir -p ~/.claude/skills` |
| home-write | `README.md:165` | `ln -sf "$(pwd)/skills/$skill" ~/.claude/skills/$skill` |
| home-write | `README.md:174` | `mkdir -p ~/.codex/skills` |
| home-write | `README.md:176` | `ln -sf "$(pwd)/skills/$skill" ~/.codex/skills/$skill` |
| home-write | `install-guidance.md:118` | `mkdir -p ~/.claude/skills` |
| home-write | `install-guidance.md:120` | `ln -sf "$(pwd)/skills/$skill" ~/.claude/skills/$skill` |
| home-write | `install-guidance.md:150` | `rm -rf ~/.claude/plugins/cache/kicad-happy ~/.claude/plugins/marketplaces/kicad-happy` |
| home-write | `install-guidance.md:160` | `(`~/.claude/plugins/cache/`). Claude Code may load skills from all cached versions,` |
| home-write | `install-guidance.md:192` | `Codex looks for globally installed skills in `~/.codex/skills/`.` |
| home-write | `install-guidance.md:199` | `mkdir -p ~/.codex/skills` |
| home-write | `install-guidance.md:201` | `ln -sf "$(pwd)/skills/$skill" ~/.codex/skills/$skill` |
| home-write | `install-guidance.md:223` | `Prefer `$skill-installer` or `~/.codex/skills/`.` |
| home-write | `install-guidance.md:241` | `- **`~/.agents/skills` guidance is stale for Codex:** if you see older setup` |
| home-write | `install-guidance.md:242` | `docs telling you to install Codex skills into `~/.agents/skills`, treat that` |
| home-write | `install-guidance.md:243` | `as outdated. Use `~/.codex/skills` instead.` |
| home-write | `install-guidance.md:274` | `Copilot CLI discovers skills from `~/.copilot/skills/`, `~/.claude/skills/`, or` |
| home-write | `install-guidance.md:275` | ``~/.agents/skills/`:` |
| home-write | `install-guidance.md:280` | `mkdir -p ~/.agents/skills` |
| home-write | `install-guidance.md:282` | `ln -sf "$(pwd)/skills/$skill" ~/.agents/skills/$skill` |
| home-write | `install-guidance.md:345` | `1. Unlink legacy skills from `~/.gemini/skills`:` |
| home-write | `install-guidance.md:348` | `unlink ~/.gemini/skills/$skill` |
| home-write | `install-guidance.md:360` | `2.  **User Tier**: `~/.gemini/antigravity-cli/plugins/` or `~/.agents/plugins/`.` |
| home-write | `install-guidance.md:400` | `mkdir -p ~/.config/opencode` |
| home-write | `install-guidance.md:401` | `cat >> ~/.config/opencode/opencode.json <<'EOF'` |
| home-write | `install-guidance.md:408` | `Or, since opencode also reads `~/.claude/skills/` natively, the Claude Code manual-symlink install in the [Claude Code section](#claude-code` |
| home-write | `install-guidance.md:415` | `mkdir -p ~/.config/opencode/skills` |
| home-write | `install-guidance.md:417` | `ln -sf "$(pwd)/skills/$skill" ~/.config/opencode/skills/$skill` |
| home-write | `install-guidance.md:671` | `4. On Claude Code: check for stale cache in `~/.claude/plugins/cache/`` |
| home-write | `release-notes.md:150` | `/ **Codex support** / First-class OpenAI Codex support with agent-neutral docs, skill-installer compatibility, and global installs via `~/.c` |
| home-write | `skills/digikey/SKILL.md:48` | `If credentials are stored in a central secrets file (e.g., `~/.config/secrets.env`), load them first:` |
| home-write | `skills/digikey/SKILL.md:50` | `export $(grep -v '^#' ~/.config/secrets.env / grep -v '^$' / xargs)` |
| home-write | `skills/element14/SKILL.md:52` | `If credentials are stored in a central secrets file (e.g., `~/.config/secrets.env`), load them first:` |
| home-write | `skills/element14/SKILL.md:54` | `export $(grep -v '^#' ~/.config/secrets.env / grep -v '^$' / xargs)` |
| home-write | `skills/kicad/references/config-reference.md:21` | `The loader walks upward from the project directory, collecting every `.kicad-happy.json` it finds, then includes `~/.kicad-happy.json` as th` |
| home-write | `skills/kicad/references/config-reference.md:24` | `~/.kicad-happy.json          ← base layer (user-wide defaults)` |
| home-write | `skills/kicad/scripts/project_config.py:6` | `and ~/.kicad-happy.json serves as a user-level base layer.` |
| home-write | `skills/kicad/scripts/project_config.py:190` | `(most specific).  Also includes ~/.kicad-happy.json as the base` |
| home-write | `skills/kicad/scripts/project_config.py:207` | `# Check ~/.kicad-happy.json as a user-level base layer` |
| home-write | `skills/kicad/scripts/project_config.py:208` | `home_cfg = os.path.join(os.path.expanduser('~'), CONFIG_FILENAME)` |
| home-write | `skills/kicad/scripts/project_config.py:222` | `~/.kicad-happy.json is the base layer (lowest precedence).` |
| home-write | `skills/mouser/SKILL.md:37` | `If credentials are stored in a central secrets file (e.g., `~/.config/secrets.env`), load them first:` |
| home-write | `skills/mouser/SKILL.md:39` | `export $(grep -v '^#' ~/.config/secrets.env / grep -v '^$' / xargs)` |
| home-write | `skills/spice/scripts/spice_simulator.py:229` | `home = os.path.expanduser("~")` |
