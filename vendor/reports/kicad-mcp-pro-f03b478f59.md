# kicad-mcp-pro f03b478f59 -> f03b478f59 (MIT)

Full scan of 2091 files.
New findings (not in the reviewed baseline): HIGH 16, MEDIUM 725, LOW 188. Suppressed by baseline: 0.

## HIGH

| rule | file:line | text |
|---|---|---|
| credential-read | `CHANGELOG.md:1118` | `* **workflows:** add GITHUB_TOKEN to release-please and scorecard ([5c51bc3](https://github.com/oaslananka/kicad-mcp-pro/commit/5c51bc3413d7` |
| credential-read | `CHANGELOG.md:1119` | `* **workflows:** pass GITHUB_TOKEN explicitly to CodeQL init and analyze steps ([3bc4083](https://github.com/oaslananka/kicad-mcp-pro/commit` |
| pipe-to-shell | `docs/agents/troubleshooting.md:9` | `curl -LsSf https://astral.sh/uv/install.sh / sh` |
| credential-read | `docs/development/release-asset-immutability.md:53` | `because it uses the release-automation GitHub App token, not `GITHUB_TOKEN`.` |
| credential-read | `docs/security/github-actions-policy.md:9` | `- read-only default `GITHUB_TOKEN` permissions;` |
| credential-read | `docs/security/scorecard-exceptions.md:54` | `query does not work with `GITHUB_TOKEN` and works only with a PAT. An` |
| credential-read | `scripts/check_staged_sensitive_paths.py:13` | `{".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials.json", "service-account.json"}` |
| credential-read | `scripts/check_staged_sensitive_paths.py:27` | `or (name.startswith("id_rsa.") and name != "id_rsa.pub")` |
| credential-read | `scripts/check_staged_sensitive_paths.py:28` | `or (name.startswith("id_ed25519.") and name != "id_ed25519.pub")` |
| credential-read | `tests/unit/test_opencode_cli_eval_adapter.py:167` | `assert "GITHUB_TOKEN" not in env` |
| credential-read | `tests/unit/test_path_safety.py:288` | `escaped_path = Path.home() / ".ssh" / "id_rsa"` |
| credential-read | `tests/unit/test_script_path_safety.py:16` | `escaped_path = Path.home() / ".ssh" / "id_rsa"` |
| credential-read | `tests/unit/test_staged_sensitive_paths.py:18` | `"keys/id_ed25519",` |
| credential-read | `tests/unit/test_staged_sensitive_paths.py:19` | `"keys/id_rsa.bak",` |
| credential-read | `tests/unit/test_staged_sensitive_paths.py:42` | `"keys/id_rsa.pub",` |
| credential-read | `tests/unit/test_staged_sensitive_paths.py:43` | `"keys/id_ed25519.pub",` |

## MEDIUM

| rule | file:line | text |
|---|---|---|
| telemetry | `CHANGELOG.md:46` | `* **deps:** patch OpenTelemetry API and ChatGPT app ip-address advisories ([c736824](https://github.com/oaslananka/kicad-mcp-pro/commit/c736` |
| telemetry | `CHANGELOG.md:88` | `* **telemetry:** simplify secret-field redaction pattern ([#1312](https://github.com/oaslananka/kicad-mcp-pro/issues/1312)) ([6da4fed](https` |
| telemetry | `CHANGELOG.md:334` | `* **evals:** tolerate shared NIM telemetry jitter ([#931](https://github.com/oaslananka/kicad-mcp-pro/issues/931)) ([12ab803](https://github` |
| subprocess | `CHANGELOG.md:1029` | `* add errors='replace' to subprocess.run for Turkish Windows encoding ([#21](https://github.com/oaslananka/kicad-mcp-pro/issues/21)) ([911d3` |
| telemetry | `CHANGELOG.md:1143` | `* **readme:** point telemetry note to privacy docs ([5ebef49](https://github.com/oaslananka/kicad-mcp-pro/commit/5ebef49ab835a2f5f1c872fd4d9` |
| telemetry | `CHANGELOG.md:1456` | `- **kicad-mcp-pro:** add OpenTelemetry observability ([b34ab19](https://github.com/oaslananka/kicad-mcp-pro/commit/b34ab192f59c6186a60909511` |
| telemetry | `CHANGELOG.md:1457` | `- **kicad-mcp-pro:** add OpenTelemetry observability ([b4f38b8](https://github.com/oaslananka/kicad-mcp-pro/commit/b4f38b80b4c4ceeecd2acf73e` |
| network | `Dockerfile:75` | `CMD python -c "import urllib.request; exit(0 if urllib.request.urlopen('http://127.0.0.1:3334/api/health').status == 200 else 1)" 2>/dev/nul` |
| telemetry | `README.md:56` | `Telemetry and error reporting are disabled by default. Opt-in OpenTelemetry` |
| telemetry | `README.md:58` | `[`docs/configuration.md`](docs/configuration.md#opentelemetry), and privacy rules` |
| telemetry | `ROADMAP.md:48` | `- OpenTelemetry observability and structured logging lifecycle.` |
| telemetry | `SECURITY.md:71` | `- Telemetry and error reporting are disabled by default.` |
| env-dump | `benchmarks/conftest.py:51` | `for name in tuple(os.environ):` |
| telemetry | `docs/adr/0006-mcp-2026-stateless-compatibility-lane.md:40` | `/ Telemetry and benchmarks / Request telemetry can associate lifecycle/session fields / Candidate telemetry records protocol method without ` |
| telemetry | `docs/configuration.md:79` | `/ `OTEL_EXPORTER_OTLP_ENDPOINT` / OpenTelemetry OTLP collector endpoint /` |
| telemetry | `docs/configuration.md:80` | `/ `OTEL_EXPORTER_OTLP_HEADERS`  / OpenTelemetry OTLP exporter headers   /` |
| telemetry | `docs/configuration.md:82` | `/ `OTEL_SERVICE_NAME`           / OpenTelemetry service name            /` |
| telemetry | `docs/configuration.md:144` | `## OpenTelemetry` |
| telemetry | `docs/configuration.md:146` | `OpenTelemetry is disabled by default. It is enabled when` |
| telemetry | `docs/configuration.md:148` | ``--telemetry`:` |
| telemetry | `docs/configuration.md:151` | `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 kicad-mcp-pro --telemetry` |
| telemetry | `docs/configuration.md:164` | `same opt-in switch is available as `KICAD_MCP_TELEMETRY_ENABLED=true` for` |
| telemetry | `docs/configuration.md:167` | `If telemetry is enabled without an explicit endpoint, the server uses local` |
| telemetry | `docs/configuration.md:170` | `default. Set `KICAD_MCP_TELEMETRY_BUFFER_MAX_EVENTS` to control the bounded` |
| telemetry | `docs/configuration.md:184` | `Telemetry attributes intentionally avoid project paths, board contents,` |
| telemetry | `docs/deployment/http-mode.md:11` | `- Optional OpenTelemetry OTLP export when `OTEL_EXPORTER_OTLP_ENDPOINT` is set or `--telemetry` is passed` |
| telemetry | `docs/deployment/http-mode.md:49` | `- OpenTelemetry emits MCP request, tool, KiCad CLI, and PCB parser spans plus` |
| telemetry | `docs/development/codecov.md:22` | `validation remains enabled, and Codecov telemetry is disabled.` |
| telemetry | `docs/development/codecov.md:66` | `production bundle pipeline; at that point use OIDC, disable plugin telemetry,` |
| telemetry | `docs/development/engineering-acceptance-loop.md:149` | `telemetry.` |
| telemetry | `docs/development/testing-policy.md:43` | `Test Analytics. Upload steps run after test failures, but the original pytest` |
| telemetry | `docs/engineering/ci-cd-policy.md:234` | `Scorecard and the source of Codecov Python coverage and JUnit test analytics.` |
| telemetry | `docs/evidence/kicad-10-0-7/2026-10-12-feature-parity-audit.md:308` | `telemetry permission, third-party browser terms or user configuration is` |
| telemetry | `docs/faq.md:21` | `## Is telemetry enabled?` |
| telemetry | `docs/faq.md:23` | `No. Telemetry is disabled by default. Operators can explicitly opt in to` |
| telemetry | `docs/faq.md:24` | `OpenTelemetry by setting `OTEL_EXPORTER_OTLP_ENDPOINT` or passing `--telemetry`;` |
| telemetry | `docs/privacy.md:15` | `configure OpenTelemetry export to their own OTLP collector for operational` |
| telemetry | `docs/privacy.md:26` | `/ Usage telemetry                  / **No by default** / Optional OpenTelemetry export must be explicitly configured /` |
| telemetry | `docs/privacy.md:31` | `any user data. Optional OpenTelemetry export sends only operational spans and` |
| telemetry | `docs/privacy.md:44` | `OpenTelemetry export to a collector they control.` |
| telemetry | `docs/repo-maturity-report.md:129` | `/ Time to first response / Needs human confirmation / Requires periodic GitHub issue analytics. /` |
| telemetry | `docs/security/requirements.md:28` | `/ SR-10 / Telemetry, external network use, and credentialed integrations must be opt-in and documented. / Privacy policy, configuration docs` |
| subprocess | `docs/security/threat-model.md:39` | ``subprocess.run([binary, *args], shell=False)` with the operator-configured binary, so` |
| subprocess | `docs/security/threat-model.md:41` | `no `os.system`, `os.popen`, `subprocess.getoutput`, or `shell=True` anywhere in `src/`.` |
| telemetry | `docs/submission/README.md:39` | `- [ ] Confirm `docs/privacy.md` states telemetry is disabled by default and optional OpenTelemetry export is explicit.` |
| telemetry | `docs/submission/anthropic-directory.md:42` | `- [ ] Telemetry is disabled by default; optional OpenTelemetry export requires explicit operator configuration.` |
| telemetry | `docs/submission/anthropic-directory.md:124` | `- [ ] Verify the privacy URL renders the current no-telemetry statement.` |
| telemetry | `docs/submission/anthropic-directory.md:132` | `- [ ] Confirm the safety answer mentions telemetry is disabled by default and optional OpenTelemetry export is explicit.` |
| telemetry | `docs/submission/chatgpt-apps.md:46` | `- [ ] Long description: `KiCad MCP Pro connects ChatGPT-compatible MCP clients to local KiCad projects for project setup, schematic review, ` |
| telemetry | `docs/submission/chatgpt-apps.md:137` | `- [ ] Confirm the app says OpenTelemetry export is disabled by default and operator-configured only.` |
| telemetry | `docs/submission/chatgpt-apps.md:154` | `- [ ] Confirm the privacy page states telemetry is disabled by default and optional OpenTelemetry export is explicit.` |
| telemetry | `docs/submission/safety-and-permissions.md:10` | `- Telemetry is disabled by default; OpenTelemetry export requires explicit operator configuration.` |
| telemetry | `docs/submission/safety-and-permissions.md:38` | `## Network and Telemetry` |
| telemetry | `docs/submission/safety-and-permissions.md:48` | `- [ ] Usage telemetry is disabled by default and optional OpenTelemetry export is explicit.` |
| telemetry | `docs/submission/safety-and-permissions.md:107` | `- [ ] Confirm the server itself is described as not collecting telemetry.` |
| telemetry | `docs/workflows/high-speed-review.md:60` | `## 5. Route and Inspect FreeRouting Telemetry` |
| telemetry | `evals/README.md:248` | `case IDs, normalized tool calls, telemetry, failure classifications, scorer` |
| telemetry | `evals/README.md:299` | `ceiling is enforced only when the endpoint reports cost telemetry. Promotion therefore` |
| telemetry | `evals/README.md:451` | `evidence and no safety, quality, infrastructure, telemetry, or per-case failure:` |
| telemetry | `evals/README.md:485` | `provider telemetry such as p95 hosted-endpoint latency and mean token usage remains` |
| telemetry | `evals/README.md:487` | `configured absolute telemetry ceilings still fail closed. The aggregate job distinguishes:` |
| telemetry | `evals/README.md:492` | `- unavailable token or latency telemetry.` |
| telemetry | `evals/README.md:504` | `missing counters remain a telemetry-availability result rather than being mislabeled` |
| dependency-file | `evals/live/package-lock.json:0` | `package-lock.json` |
| dependency-file | `evals/live/package.json:0` | `package.json` |
| telemetry | `evals/tool_selection/thresholds.yaml:4` | `# Hosted-provider latency and token usage remain reviewable telemetry while these` |
| telemetry | `evals/tool_selection/thresholds.yaml:23` | `# Provider telemetry values remain in comparison reports; absolute ceilings above control` |
| telemetry | `evals/tool_selection/thresholds.yaml:24` | `# whether latency/token telemetry becomes release-blocking.` |
| dependency-file | `integrations/chatgpt-app/apps-sdk/package-lock.json:0` | `package-lock.json` |
| dependency-file | `integrations/chatgpt-app/apps-sdk/package.json:0` | `package.json` |
| subprocess | `integrations/chatgpt-app/apps-sdk/src/server.ts:25` | `import { spawn } from "node:child_process";` |
| subprocess | `integrations/chatgpt-app/apps-sdk/src/server.ts:388` | `const proc = spawn("uvx", ["kicad-mcp-pro", method, "--json"], {` |
| subprocess | `integrations/chatgpt-app/apps-sdk/test/app-smoke.test.mjs:2` | `import { spawn } from "node:child_process";` |
| subprocess | `integrations/chatgpt-app/apps-sdk/test/app-smoke.test.mjs:42` | `const child = spawn(process.execPath, ["dist/server.js"], {` |
| network | `integrations/chatgpt-app/apps-sdk/test/app-smoke.test.mjs:57` | `const response = await fetch(`http://127.0.0.1:${port}/`);` |
| network | `integrations/chatgpt-app/apps-sdk/test/app-smoke.test.mjs:119` | `const response = await fetch(`http://127.0.0.1:${port}/widgets/${widget}`);` |
| subprocess | `integrations/claude-code/install.mjs:6` | `const { execSync } = require("child_process");` |
| subprocess | `integrations/claude-code/install.mjs:12` | `execSync(`claude mcp add --transport stdio --scope ${scope} kicad -- uvx kicad-mcp-pro`, {` |
| subprocess | `integrations/claude-code/kicad-pcb-review-skill/scripts/verify_kicad_mcp.py:33` | `result = subprocess.run(` |
| subprocess | `integrations/claude-code/kicad-pcb-review-skill/scripts/verify_kicad_mcp.py:56` | `result = subprocess.run(` |
| subprocess | `integrations/common/doctor.py:35` | `result = subprocess.run([path, "version"], capture_output=True, text=True, timeout=10)` |
| subprocess | `integrations/common/doctor.py:49` | `result = subprocess.run(` |
| subprocess | `integrations/common/install-kicad-mcp.mjs:13` | `import { spawnSync } from "node:child_process";` |
| subprocess | `integrations/common/install-kicad-mcp.mjs:103` | `const result = spawnSync("kicad-mcp-pro", argv, {` |
| subprocess | `integrations/opencode/plugins/kicad-mcp-plugin/index.ts:23` | `const { execSync } = await import("child_process");` |
| subprocess | `integrations/opencode/plugins/kicad-mcp-plugin/index.ts:25` | `const output = execSync("kicad-mcp-pro doctor --json", { encoding: "utf-8" });` |
| dependency-file | `integrations/opencode/plugins/kicad-mcp-plugin/package.json:0` | `package.json` |
| dependency-file | `package.json:0` | `package.json` |
| dependency-file | `packages/kicad-fixtures/package.json:0` | `package.json` |
| subprocess | `packages/kicad-plugin/companion_core.py:146` | `runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,` |
| network | `packages/kicad-plugin/context.py:17` | `import urllib.request` |
| network | `packages/kicad-plugin/context.py:197` | `Opener = Callable[[urllib.request.Request], _HttpResponse]` |
| network | `packages/kicad-plugin/context.py:253` | `def _default_opener(self, request: urllib.request.Request) -> _HttpResponse:` |
| network | `packages/kicad-plugin/context.py:254` | `# urlopen is typed to return Any-ish; localhost-only call, narrow to our Protocol.` |
| network | `packages/kicad-plugin/context.py:257` | `urllib.request.urlopen(  # noqa: S310  # nosec B310` |
| network | `packages/kicad-plugin/context.py:265` | `request = urllib.request.Request(  # noqa: S310 - validated loopback http(s) endpoint` |
| network | `packages/kicad-plugin/context.py:332` | `request = urllib.request.Request(  # noqa: S310 - fixed loopback http(s) endpoint` |
| dependency-file | `packages/kicad-plugin/requirements.txt:0` | `requirements.txt` |
| subprocess | `packages/mcp-npm/CHANGELOG.md:380` | `* add errors='replace' to subprocess.run for Turkish Windows encoding ([#21](https://github.com/oaslananka/kicad-mcp-pro/issues/21)) ([911d3` |
| subprocess | `packages/mcp-npm/CHANGELOG.md:454` | `* add errors='replace' to subprocess.run for Turkish Windows encoding ([#21](https://github.com/oaslananka/kicad-mcp-pro/issues/21)) ([911d3` |
| subprocess | `packages/mcp-npm/bin/kicad-mcp-pro.js:6` | `const { spawn } = require("node:child_process");` |
| subprocess | `packages/mcp-npm/bin/kicad-mcp-pro.js:41` | `const child = spawn(uvx, [pythonPackage, ...process.argv.slice(2)], {` |
| dependency-file | `packages/mcp-npm/package-lock.json:0` | `package-lock.json` |
| dependency-file | `packages/mcp-npm/package.json:0` | `package.json` |
| subprocess | `packages/mcp-npm/scripts/build-smoke.js:5` | `const { spawnSync } = require("node:child_process");` |
| subprocess | `packages/mcp-npm/scripts/build-smoke.js:10` | `const result = spawnSync(process.execPath, [wrapperPath, "--help"], {` |
| dependency-file | `packages/protocol-schemas/package.json:0` | `package.json` |
| dependency-file | `pnpm-lock.yaml:0` | `pnpm-lock.yaml` |
| dependency-file | `pyproject.toml:0` | `pyproject.toml` |
| telemetry | `pyproject.toml:45` | `"opentelemetry-exporter-otlp>=1.45.1,<2.0.0",` |
| telemetry | `pyproject.toml:46` | `"opentelemetry-sdk>=1.45.1,<2.0.0",` |
| subprocess | `scripts/advanced_testing/report_collector.py:34` | `return subprocess.check_output(cmd, text=True).strip()  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_fuzz.py:92` | `proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_mutation.py:73` | `proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_mutation.py:77` | `stats_proc = subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_mutation.py:89` | `results_proc = subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_security_audit.py:20` | `proc = subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `scripts/advanced_testing/run_security_audit.py:122` | `proc = subprocess.run(  # nosec B603  # nosemgrep` |
| network | `scripts/attest_reference_pcb_ipc_process.py:24` | `with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:` |
| subprocess | `scripts/audit_dependencies.py:61` | `subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603  # argv-only command.` |
| subprocess | `scripts/audit_dependencies.py:65` | `return subprocess.run(  # noqa: S603  # argv-only command.` |
| subprocess | `scripts/audit_native_board_fixtures.py:106` | `process = subprocess.run(  # nosec B603` |
| subprocess | `scripts/audit_native_board_fixtures.py:236` | `version = subprocess.run(  # nosec B603` |
| subprocess | `scripts/audit_native_board_fixtures.py:284` | `sha = subprocess.run(  # nosec B603` |
| subprocess | `scripts/benchmark_kicad_large_demo.py:160` | `result = subprocess.run(  # nosec B603` |
| subprocess | `scripts/benchmark_kicad_large_demo.py:309` | `source_sha = subprocess.run(  # nosec B603` |
| subprocess | `scripts/branch_hygiene_report.py:35` | `return subprocess.run([gh_exe, *args], text=True, capture_output=True, check=False)` |
| subprocess | `scripts/check_bandit_policy.py:55` | `result = subprocess.run(` |
| subprocess | `scripts/check_patch_coverage.py:142` | `completed = subprocess.run(command, check=True, capture_output=True, text=True)` |
| subprocess | `scripts/check_patch_coverage.py:165` | `subprocess.CalledProcessError,` |
| subprocess | `scripts/check_release_preflight.py:201` | `result = subprocess.run(` |
| network | `scripts/check_submission_readiness.py:11` | `from urllib.request import urlopen` |
| subprocess | `scripts/check_submission_readiness.py:95` | `result = subprocess.run(` |
| network | `scripts/check_submission_readiness.py:208` | `with urlopen("https://pypi.org/pypi/kicad-mcp-pro/json", timeout=10) as response:  # noqa: S310` |
| telemetry | `scripts/check_submission_readiness.py:227` | `if "data" not in text or "telemetry" not in text:` |
| telemetry | `scripts/check_submission_readiness.py:228` | `return CheckResult(PRIVACY_POLICY_CHECK, "FAIL", "missing data or telemetry language")` |
| telemetry | `scripts/check_submission_readiness.py:229` | `return CheckResult(PRIVACY_POLICY_CHECK, "PASS", "privacy.md covers data and telemetry")` |
| subprocess | `scripts/check_workflows.py:25` | `result = subprocess.run(_resolve_command(command), cwd=REPO_ROOT, check=False)` |
| subprocess | `scripts/classify-gh-failure.mjs:3` | `import { execFileSync } from "node:child_process";` |
| network | `scripts/dev_environment.py:19` | `import urllib.request` |
| network | `scripts/dev_environment.py:206` | `urllib.request.urlopen(url, timeout=120) as response,  # noqa: S310` |
| subprocess | `scripts/dev_environment.py:291` | `return subprocess.run(` |
| env-dump | `scripts/dev_environment.py:358` | `env = dict(os.environ)` |
| subprocess | `scripts/dev_environment.py:534` | `except (OSError, subprocess.CalledProcessError):` |
| telemetry | `scripts/evaluate_live_model_release_gate.py:54` | `"telemetry_unavailable": len(report["classifications"]["telemetry_unavailable"]),` |
| network | `scripts/generate_release_evidence.py:13` | `import urllib.request` |
| network | `scripts/generate_release_evidence.py:202` | `with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310` |
| network | `scripts/generate_release_evidence.py:255` | `request = urllib.request.Request(  # noqa: S310` |
| network | `scripts/generate_release_evidence.py:259` | `with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310` |
| subprocess | `scripts/generate_synthetic_demo.py:114` | `result = subprocess.run(command, check=False)` |
| subprocess | `scripts/generate_synthetic_demo.py:122` | `result = subprocess.run(retry, check=False)` |
| telemetry | `scripts/generate_synthetic_demo.py:176` | `(104, height - 118), "local stdio MCP server - no telemetry", fill=muted, font=font` |
| subprocess | `scripts/hook_pre_push.py:342` | `completed = subprocess.run(` |
| subprocess | `scripts/hook_pre_push.py:396` | `completed = subprocess.run(check.command, cwd=ROOT, check=False)` |
| subprocess | `scripts/install_git_hooks.py:17` | `return subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `scripts/kicad11_headless_canary.py:98` | `return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)` |
| subprocess | `scripts/kicad11_headless_canary.py:349` | `result = subprocess.run(` |
| subprocess | `scripts/kicad_107_macos_bom_gui.py:28` | `result = subprocess.run(  # nosec B603` |
| subprocess | `scripts/kicad_107_macos_bom_gui.py:87` | `process = subprocess.Popen(  # nosemgrep  # nosec B603` |
| subprocess | `scripts/kicad_canary.py:911` | `result = subprocess.run(` |
| subprocess | `scripts/kicad_canary.py:1009` | `status = subprocess.run(` |
| subprocess | `scripts/kicad_canary.py:1020` | `result = subprocess.run(` |
| network | `scripts/publish_mcp_registry.py:16` | `from urllib.request import Request, urlopen` |
| subprocess | `scripts/publish_mcp_registry.py:64` | `login = subprocess.run(` |
| subprocess | `scripts/publish_mcp_registry.py:71` | `publish = subprocess.run([publisher, "publish"], cwd=ROOT, check=False)` |
| network | `scripts/publish_mcp_registry.py:92` | `with urlopen(request, timeout=30) as response:  # noqa: S310 - request URL is validated.` |
| subprocess | `scripts/run-package-tests.cjs:1` | `const { spawnSync } = require("node:child_process");` |
| subprocess | `scripts/run-package-tests.cjs:26` | `const result = spawnSync(process.execPath, ["--test", ...testFiles], {` |
| subprocess | `scripts/run_uv.py:28` | `completed = subprocess.run(` |
| env-dump | `scripts/run_uv.py:92` | `environment = dict(os.environ)` |
| subprocess | `scripts/run_uv.py:94` | `completed = subprocess.run(` |
| network | `scripts/runtime_policy.py:16` | `import urllib.request` |
| network | `scripts/runtime_policy.py:147` | `request = urllib.request.Request(_validated_https_url(url), headers=HTTP_HEADERS)  # noqa: S310` |
| network | `scripts/runtime_policy.py:148` | `with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310` |
| network | `scripts/runtime_policy.py:153` | `request = urllib.request.Request(_validated_https_url(url), headers=HTTP_HEADERS)  # noqa: S310` |
| network | `scripts/runtime_policy.py:154` | `with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310` |
| subprocess | `scripts/runtime_policy.py:355` | `result = subprocess.run(` |
| subprocess | `scripts/runtime_policy.py:369` | `result = subprocess.run(` |
| subprocess | `scripts/runtime_policy.py:383` | `except subprocess.CalledProcessError:` |
| subprocess | `scripts/runtime_policy.py:404` | `result = subprocess.run(` |
| subprocess | `scripts/security_local.py:65` | `result = subprocess.run(command, check=False)` |
| subprocess | `scripts/stage_draft_release_assets.py:48` | `result = subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `scripts/stage_draft_release_assets.py:82` | `result = subprocess.run(  # nosec B603  # nosemgrep` |
| network | `scripts/verify-npm-release.mjs:43` | `const response = await fetch(url, { redirect: "error" });` |
| network | `scripts/verify-npm-release.mjs:50` | `const response = await fetch(url, { redirect: "error" });` |
| subprocess | `scripts/workflow_security.py:63` | `raise SystemExit(subprocess.run(command, check=False).returncode)  # nosec B603  # nosemgrep` |
| network | `src/kicad_mcp/bridge.py:89` | `s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)` |
| network | `src/kicad_mcp/bridge.py:448` | `async with httpx.AsyncClient(base_url=state.target_url, timeout=30.0) as client:` |
| network | `src/kicad_mcp/bridge.py:452` | `except httpx.HTTPStatusError as exc:` |
| network | `src/kicad_mcp/bridge.py:463` | `except (httpx.RequestError, ValueError) as exc:` |
| subprocess | `src/kicad_mcp/bridge.py:533` | `proc = subprocess.Popen(` |
| network | `src/kicad_mcp/companion/context.py:17` | `import urllib.request` |
| network | `src/kicad_mcp/companion/context.py:197` | `Opener = Callable[[urllib.request.Request], _HttpResponse]` |
| network | `src/kicad_mcp/companion/context.py:253` | `def _default_opener(self, request: urllib.request.Request) -> _HttpResponse:` |
| network | `src/kicad_mcp/companion/context.py:254` | `# urlopen is typed to return Any-ish; localhost-only call, narrow to our Protocol.` |
| network | `src/kicad_mcp/companion/context.py:257` | `urllib.request.urlopen(  # noqa: S310  # nosec B310` |
| network | `src/kicad_mcp/companion/context.py:265` | `request = urllib.request.Request(  # noqa: S310 - validated loopback http(s) endpoint` |
| network | `src/kicad_mcp/companion/context.py:332` | `request = urllib.request.Request(  # noqa: S310 - fixed loopback http(s) endpoint` |
| telemetry | `src/kicad_mcp/config.py:111` | `telemetry_enabled: bool = Field(default=False)` |
| telemetry | `src/kicad_mcp/config.py:116` | `telemetry_buffer_max_events: int = Field(default=100, ge=0, le=1000)` |
| telemetry | `src/kicad_mcp/config.py:233` | `updated["telemetry_enabled"] = True` |
| telemetry | `src/kicad_mcp/config.py:678` | `"telemetry_enabled": self.telemetry_enabled,` |
| telemetry | `src/kicad_mcp/config.py:683` | `"telemetry_buffer_max_events": self.telemetry_buffer_max_events,` |
| subprocess | `src/kicad_mcp/diagnostics.py:284` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/diagnostics.py:351` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/diagnostics.py:649` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/discovery.py:169` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/discovery.py:194` | `result = subprocess.run(` |
| telemetry | `src/kicad_mcp/evals/baseline_promotion.py:97` | `telemetry = _string_list(classifications.get("telemetry_unavailable", []), "Telemetry failures")` |
| telemetry | `src/kicad_mcp/evals/baseline_promotion.py:105` | `if telemetry:` |
| telemetry | `src/kicad_mcp/evals/baseline_promotion.py:106` | `raise BaselinePromotionError("Unavailable telemetry prevents baseline promotion.")` |
| subprocess | `src/kicad_mcp/evals/live_adapters.py:392` | `completed = subprocess.run(` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:612` | `def _provider_request_failure_detail(response: httpx.Response) -> FailureDetail:` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:1362` | `transport: httpx.BaseTransport / None = None,` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:1379` | `with httpx.Client(timeout=timeout_seconds, transport=transport) as client:` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:1388` | `except httpx.TimeoutException:` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:1390` | `except httpx.HTTPError:` |
| network | `src/kicad_mcp/evals/nvidia_nim_adapter.py:1427` | `transport: httpx.BaseTransport / None = None,` |
| network | `src/kicad_mcp/evals/openai_adapter.py:26` | `transport: httpx.BaseTransport / None = None,` |
| subprocess | `src/kicad_mcp/evals/opencode_cli_adapter.py:223` | `run_process: RunProcess = subprocess.run,` |
| network | `src/kicad_mcp/evals/opencode_zen_adapter.py:34` | `transport: httpx.BaseTransport / None = None,` |
| subprocess | `src/kicad_mcp/evals/reference_agent_runner.py:158` | `completed = subprocess.run(` |
| subprocess | `src/kicad_mcp/evals/reference_agent_runner.py:173` | `status = subprocess.run(` |
| subprocess | `src/kicad_mcp/evals/reference_agent_runner.py:991` | `completed = subprocess.run(` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:24` | `_PROVIDER_TELEMETRY_METRICS = frozenset({"p95_latency_ms", "mean_tokens"})` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:25` | `_TELEMETRY_METRIC_PREFIXES = ("mean_tokens", "p95_" + "latency_ms")` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:70` | `"telemetry_unavailable": [],` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:266` | `elif "=None" in failure and failure.startswith(_TELEMETRY_METRIC_PREFIXES):` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:267` | `_append(classifications, "telemetry_unavailable", f"{config_id}: {failure}")` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:308` | `"telemetry_unavailable"` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:314` | `if metric in _PROVIDER_TELEMETRY_METRICS:` |
| telemetry | `src/kicad_mcp/evals/release_gate.py:374` | `"telemetry_unavailable",` |
| subprocess | `src/kicad_mcp/evals/release_policy.py:282` | `result = subprocess.run(` |
| telemetry | `src/kicad_mcp/evals/tool_selection.py:423` | `"""Score recall, response behavior, safety, efficiency, and telemetry."""` |
| telemetry | `src/kicad_mcp/evals/tool_selection.py:488` | `"""Roll case results up into quality, safety, efficiency, and telemetry metrics."""` |
| telemetry | `src/kicad_mcp/i18n.py:28` | `"Enable OpenTelemetry export": "OpenTelemetry dışa aktarımını etkinleştir.",` |
| telemetry | `src/kicad_mcp/ipc/capabilities.py:159` | `"""Return the active IPC backend identifier for telemetry and diagnostics."""` |
| telemetry | `src/kicad_mcp/models/signal_integrity.py:42` | `amplitude_v: float = Field(default=1.0, gt=0.0, le=10.0)` |
| telemetry | `src/kicad_mcp/routing/length_tuning.py:74` | `meander_amplitude_mm: float = 0.5,` |
| telemetry | `src/kicad_mcp/routing/length_tuning.py:98` | `f"Suggested meander amplitude: {meander_amplitude_mm:.3f} mm"` |
| telemetry | `src/kicad_mcp/server.py:115` | `from .utils import telemetry as otel` |
| telemetry | `src/kicad_mcp/server.py:168` | `_CliTelemetry = Annotated[` |
| telemetry | `src/kicad_mcp/server.py:170` | `typer.Option("--telemetry/--no-telemetry", help=option_help("Enable OpenTelemetry export")),` |
| telemetry | `src/kicad_mcp/server.py:914` | `_telemetry_catalog_hash: str / None = None` |
| telemetry | `src/kicad_mcp/server.py:915` | `_telemetry_kicad_version: str / None = None` |
| telemetry | `src/kicad_mcp/server.py:1283` | `def _telemetry_tool_catalog_hash(self) -> str:` |
| telemetry | `src/kicad_mcp/server.py:1284` | `if self._telemetry_catalog_hash is not None:` |
| telemetry | `src/kicad_mcp/server.py:1285` | `return self._telemetry_catalog_hash` |
| telemetry | `src/kicad_mcp/server.py:1287` | `self._telemetry_catalog_hash = catalog_hash` |
| telemetry | `src/kicad_mcp/server.py:1290` | `def _telemetry_kicad_major_minor(self) -> str / None:` |
| telemetry | `src/kicad_mcp/server.py:1291` | `if self._telemetry_kicad_version is not None:` |
| telemetry | `src/kicad_mcp/server.py:1292` | `return self._telemetry_kicad_version or None` |
| telemetry | `src/kicad_mcp/server.py:1294` | `self._telemetry_kicad_version = version or ""` |
| telemetry | `src/kicad_mcp/server.py:1297` | `def _telemetry_context_attributes(self) -> dict[str, object]:` |
| telemetry | `src/kicad_mcp/server.py:1298` | `if not otel.telemetry_enabled():` |
| telemetry | `src/kicad_mcp/server.py:1302` | `"tool_catalog_hash": self._telemetry_tool_catalog_hash(),` |
| telemetry | `src/kicad_mcp/server.py:1303` | `"kicad_cli_version": self._telemetry_kicad_major_minor() or "unknown",` |
| telemetry | `src/kicad_mcp/server.py:1374` | `**self._telemetry_context_attributes(),` |
| telemetry | `src/kicad_mcp/server.py:1394` | `**self._telemetry_context_attributes(),` |
| telemetry | `src/kicad_mcp/server.py:1414` | `**self._telemetry_context_attributes(),` |
| telemetry | `src/kicad_mcp/server.py:1429` | `**self._telemetry_context_attributes(),` |
| telemetry | `src/kicad_mcp/server.py:2224` | `otel.ensure_telemetry_configured(cfg)` |
| telemetry | `src/kicad_mcp/server.py:2402` | `telemetry: bool / None = None,` |
| telemetry | `src/kicad_mcp/server.py:2422` | `if _is_cli_provided(telemetry):` |
| telemetry | `src/kicad_mcp/server.py:2423` | `os.environ["KICAD_MCP_TELEMETRY_ENABLED"] = "true" if telemetry else "false"` |
| telemetry | `src/kicad_mcp/server.py:2438` | `telemetry: bool / None = None,` |
| telemetry | `src/kicad_mcp/server.py:2452` | `telemetry=telemetry,` |
| telemetry | `src/kicad_mcp/server.py:2457` | `otel.configure_telemetry(cfg)` |
| telemetry | `src/kicad_mcp/server.py:2536` | `telemetry: _CliTelemetry = None,` |
| telemetry | `src/kicad_mcp/server.py:2551` | `telemetry=telemetry,` |
| telemetry | `src/kicad_mcp/server.py:2568` | `telemetry=telemetry,` |
| telemetry | `src/kicad_mcp/server.py:2586` | `telemetry: _CliTelemetry = None,` |
| telemetry | `src/kicad_mcp/server.py:2602` | `telemetry=telemetry,` |
| telemetry | `src/kicad_mcp/server.py:2616` | `telemetry=telemetry,` |
| telemetry | `src/kicad_mcp/server.py:3391` | `telemetry: bool / None = None,` |
| telemetry | `src/kicad_mcp/server.py:3411` | `if isinstance(telemetry, bool):` |
| telemetry | `src/kicad_mcp/server.py:3412` | `cmd.append("--telemetry" if telemetry else "--no-telemetry")` |
| subprocess | `src/kicad_mcp/server.py:3416` | `def _terminate_watch_process(proc: subprocess.Popen[bytes] / None, timeout: float = 5.0) -> None:` |
| telemetry | `src/kicad_mcp/server.py:3450` | `telemetry: bool / None = None,` |
| telemetry | `src/kicad_mcp/server.py:3482` | `telemetry=telemetry,` |
| subprocess | `src/kicad_mcp/server.py:3485` | `proc: subprocess.Popen[bytes] / None = None` |
| subprocess | `src/kicad_mcp/server.py:3488` | `proc = subprocess.Popen(` |
| subprocess | `src/kicad_mcp/server.py:3509` | `proc = subprocess.Popen(` |
| network | `src/kicad_mcp/server.py:3541` | `with contextlib.closing(socket.socket(socket.AF_INET, socket.AF_INET)) as s:` |
| subprocess | `src/kicad_mcp/server.py:3564` | `server_proc = subprocess.Popen(` |
| dependency-file | `src/kicad_mcp/setup.py:0` | `setup.py` |
| subprocess | `src/kicad_mcp/setup.py:902` | `result = subprocess.run(` |
| telemetry | `src/kicad_mcp/signal_integrity/high_speed_channel.py:42` | `f"({metrics.eye_height_ratio * 100.0:.1f}% of drive amplitude)",` |
| telemetry | `src/kicad_mcp/signal_integrity/high_speed_channel.py:65` | `amplitude_v: float = 1.0,` |
| telemetry | `src/kicad_mcp/signal_integrity/high_speed_channel.py:75` | `amplitude_v=amplitude_v,` |
| telemetry | `src/kicad_mcp/signal_integrity/high_speed_channel.py:85` | `amplitude_v=payload.amplitude_v,` |
| telemetry | `src/kicad_mcp/tools/board_file.py:12` | `from ..utils import telemetry as otel` |
| subprocess | `src/kicad_mcp/tools/export.py:58` | `# kicad_mcp.tools.export.subprocess.run or .time.sleep still affects _run_cli's` |
| telemetry | `src/kicad_mcp/tools/export_support.py:15` | `from ..utils import telemetry as otel` |
| subprocess | `src/kicad_mcp/tools/export_support.py:68` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/tools/manufacturing_panelization.py:30` | `return subprocess.run(  # nosec B603  # nosemgrep` |
| telemetry | `src/kicad_mcp/tools/routing_length_tuning.py:52` | `meander_amplitude_mm: float = 0.5,` |
| telemetry | `src/kicad_mcp/tools/routing_length_tuning.py:59` | `meander_amplitude_mm,` |
| telemetry | `src/kicad_mcp/tools/signal_integrity_high_speed_channel.py:40` | `amplitude_v: float = 1.0,` |
| telemetry | `src/kicad_mcp/tools/signal_integrity_high_speed_channel.py:59` | `amplitude_v=amplitude_v,` |
| subprocess | `src/kicad_mcp/tools/version_control.py:70` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/tray.py:90` | `self._server_proc: subprocess.Popen[bytes] / None = None` |
| subprocess | `src/kicad_mcp/tray.py:174` | `self._server_proc = subprocess.Popen(` |
| subprocess | `src/kicad_mcp/tray.py:274` | `subprocess.run(` |
| telemetry | `src/kicad_mcp/utils/channel.py:41` | `amplitude_v: float = 1.0` |
| telemetry | `src/kicad_mcp/utils/channel.py:130` | `eye_height_v=spec.amplitude_v * ratio,` |
| telemetry | `src/kicad_mcp/utils/channel.py:146` | ```reference_mag`` is the matched-through reference amplitude (0.5 for a source and` |
| telemetry | `src/kicad_mcp/utils/channel.py:254` | `eye_height_v=spec.amplitude_v * ratio,` |
| network | `src/kicad_mcp/utils/component_search.py:11` | `import urllib.request` |
| network | `src/kicad_mcp/utils/component_search.py:17` | `from http.client import HTTPMessage` |
| network | `src/kicad_mcp/utils/component_search.py:114` | `class SafeSearchRedirectHandler(urllib.request.HTTPRedirectHandler):` |
| network | `src/kicad_mcp/utils/component_search.py:123` | `req: urllib.request.Request,` |
| network | `src/kicad_mcp/utils/component_search.py:129` | `) -> urllib.request.Request / None:` |
| network | `src/kicad_mcp/utils/component_search.py:162` | `request: urllib.request.Request,` |
| network | `src/kicad_mcp/utils/component_search.py:169` | `return cast(IO[bytes], urllib.request.build_opener(handler).open(request, timeout=timeout))` |
| network | `src/kicad_mcp/utils/component_search.py:182` | `request = urllib.request.Request(  # noqa: S310 - scheme and host are validated above` |
| network | `src/kicad_mcp/utils/component_search.py:271` | `request = urllib.request.Request(  # noqa: S310 - endpoint allow-list is enforced above` |
| network | `src/kicad_mcp/utils/component_search.py:419` | `request = urllib.request.Request(url, data=body, headers=merged, method="POST")  # noqa: S310` |
| subprocess | `src/kicad_mcp/utils/freerouting.py:154` | `result = subprocess.run(  # noqa: S603` |
| subprocess | `src/kicad_mcp/utils/freerouting.py:328` | `result = subprocess.run(` |
| subprocess | `src/kicad_mcp/utils/ngspice.py:502` | `result = subprocess.run(` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:1` | `"""OpenTelemetry runtime wiring for KiCad MCP Pro."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:16` | `from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:19` | `from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:22` | `from opentelemetry.exporter.otlp.proto.http.metric_exporter import (` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:25` | `from opentelemetry.exporter.otlp.proto.http.trace_exporter import (` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:28` | `from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:29` | `from opentelemetry.sdk.metrics import MeterProvider` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:30` | `from opentelemetry.sdk.metrics.export import MetricExporter, PeriodicExportingMetricReader` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:31` | `from opentelemetry.sdk.resources import Resource` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:32` | `from opentelemetry.sdk.trace import TracerProvider` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:33` | `from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:34` | `from opentelemetry.trace import Span, Status, StatusCode, Tracer` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:61` | `class _TelemetryRuntime:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:77` | `_runtime = _TelemetryRuntime()` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:81` | `def _telemetry_requested(cfg: object) -> bool:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:82` | `return bool(getattr(cfg, "telemetry_enabled", False) or getattr(cfg, "otel_endpoint", None))` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:166` | `def configure_telemetry(` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:172` | `"""Configure the process-local telemetry runtime."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:175` | `reset_telemetry(shutdown_managed=True)` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:176` | `if not _telemetry_requested(cfg):` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:177` | `_runtime = _TelemetryRuntime(configured=True)` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:193` | `event_buffer_max_events = int(getattr(cfg, "telemetry_buffer_max_events", 100) or 0)` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:194` | `_runtime = _TelemetryRuntime(` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:231` | `def ensure_telemetry_configured(cfg: object) -> None:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:232` | `"""Configure telemetry once for server entrypoints."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:236` | `if not configured or (_telemetry_requested(cfg) and not enabled):` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:237` | `configure_telemetry(cfg)` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:240` | `def reset_telemetry(*, shutdown_managed: bool = False) -> None:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:241` | `"""Reset process-local telemetry state for tests and config reloads."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:245` | `_runtime = _TelemetryRuntime()` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:255` | `def _current_runtime() -> _TelemetryRuntime:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:322` | `"""Record a bounded, redacted telemetry event for offline retry/debug inspection."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:363` | `def telemetry_buffer_snapshot() -> list[dict[str, object]]:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:364` | `"""Return a copy of the redacted offline telemetry buffer for tests and diagnostics."""` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:371` | `def telemetry_enabled() -> bool:` |
| telemetry | `src/kicad_mcp/utils/telemetry.py:372` | `"""Return True when process telemetry is currently enabled."""` |
| network | `src/kicad_mcp/web/dashboard.py:626` | `fetch('/api/status').then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:643` | `fetch('/api/metrics').then(r => r.json()).then(m => {` |
| network | `src/kicad_mcp/web/dashboard.py:790` | `fetch('/api/tools').then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:893` | `fetch('/api/tools/' + encodeURIComponent(selectedTool.name) + '/test', {` |
| network | `src/kicad_mcp/web/dashboard.py:909` | `fetch('/api/artifacts/schematic').then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:940` | `fetch('/api/config').then(r => r.json()).then(payload => {` |
| network | `src/kicad_mcp/web/dashboard.py:961` | `fetch('/api/config', {` |
| network | `src/kicad_mcp/web/dashboard.py:973` | `fetch('/api/config/export/' + encodeURIComponent(client))` |
| network | `src/kicad_mcp/web/dashboard.py:1006` | `fetch('/api/status').then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:1066` | `fetch('/api/config/export/' + encodeURIComponent(client))` |
| network | `src/kicad_mcp/web/dashboard.py:1096` | `fetch('/api/health').then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:1176` | `fetch('/api/server/' + action, { method: 'POST' }).then(r => r.json()).then(d => {` |
| network | `src/kicad_mcp/web/dashboard.py:1189` | `fetch('/api/server/restart', { method: 'POST' }).then(r => r.json()).then(d => {` |
| subprocess | `src/kicad_mcp/web/routes.py:572` | `os.execl(sys.executable, sys.executable, "-m", "kicad_mcp.server", *sys.argv[1:])  # noqa: S606` |
| subprocess | `tests/advanced/test_kicad_differential.py:45` | `cli_res = subprocess.run(  # nosec B603  # nosemgrep` |
| subprocess | `tests/advanced/test_kicad_differential.py:93` | `res = subprocess.run(  # nosec B603  # nosemgrep` |
| env-dump | `tests/conftest.py:133` | `for name in tuple(os.environ):` |
| telemetry | `tests/conftest.py:151` | `from kicad_mcp.utils.telemetry import reset_telemetry` |
| telemetry | `tests/conftest.py:157` | `reset_telemetry(shutdown_managed=True)` |
| telemetry | `tests/conftest.py:190` | `monkeypatch.delenv("KICAD_MCP_TELEMETRY_ENABLED", raising=False)` |
| telemetry | `tests/conftest.py:200` | `reset_telemetry(shutdown_managed=True)` |
| subprocess | `tests/e2e/test_generated_board_clean.py:49` | `subprocess.run(  # noqa: S603` |
| subprocess | `tests/e2e/test_professional_workflows.py:76` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/e2e/test_professional_workflows.py:77` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| subprocess | `tests/e2e/test_stdio_startup.py:25` | `process = subprocess.Popen(` |
| telemetry | `tests/gui/manual_kicad_107_bom_gui.sh:160` | `'update_check_prompt': True,` |
| subprocess | `tests/gui/test_kicad_gui_live_context.py:55` | `process: subprocess.Popen[str]` |
| subprocess | `tests/gui/test_kicad_gui_live_context.py:214` | `process = subprocess.Popen(` |
| subprocess | `tests/gui/test_kicad_gui_live_context.py:283` | `result = subprocess.run(` |
| subprocess | `tests/gui/test_kicad_gui_live_context.py:298` | `result = subprocess.run(` |
| subprocess | `tests/integration/test_export_tools.py:31` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:32` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:84` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:85` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:130` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:232` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:305` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:306` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:358` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:425` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:426` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:569` | `monkeypatch.setattr("kicad_mcp.tools.export.subprocess.run", fake_run)` |
| subprocess | `tests/integration/test_export_tools.py:570` | `monkeypatch.setattr("kicad_mcp.discovery.subprocess.run", fake_run)` |
| ... | 325 more | |

## LOW

| rule | file:line | text |
|---|---|---|
| home-write | `.codex/config.example.toml:2` | `# ~/.codex/config.toml (or your trusted project's .codex/config.toml).` |
| home-write | `docs/agents/antigravity.md:9` | `Or manually add to `~/.gemini/config/mcp_config.json`:` |
| home-write | `docs/agents/claude-code.md:31` | `cp -r integrations/claude-code/kicad-pcb-review-skill ~/.claude/skills/` |
| home-write | `docs/agents/claude-desktop.md:18` | ``~/.config/Claude/claude_desktop_config.json`` |
| home-write | `docs/agents/cline.md:13` | `- **CLI:** edit `~/.cline/mcp.json`, or run `cline config mcp`.` |
| home-write | `docs/agents/codex.md:9` | `Or add the verified `[mcp_servers.kicad]` block to `~/.codex/config.toml`.` |
| home-write | `docs/agents/continue.md:10` | `Add the server to your assistant config — global `~/.continue/config.yaml`, or a` |
| home-write | `docs/agents/gemini-cli.md:9` | `Or manually add to `~/.gemini/settings.json`:` |
| home-write | `docs/agents/install.md:69` | `- [Codex CLI](codex.md) — `config.toml` in `~/.codex/`` |
| home-write | `docs/agents/install.md:70` | `- [Gemini CLI](gemini-cli.md) — `settings.json` in `~/.gemini/`` |
| home-write | `docs/agents/install.md:77` | `- [Antigravity](antigravity.md) — `~/.gemini/config/mcp_config.json`` |
| home-write | `docs/agents/quickstart.md:20` | `/ Windsurf / [Windsurf](windsurf.md) / `~/.codeium/windsurf/mcp_config.json` / Confirm the Cascade MCP panel shows the `kicad` server. /` |
| home-write | `docs/agents/quickstart.md:21` | `/ Cline / [Cline](cline.md) / Cline MCP settings or `~/.cline/mcp.json` / Confirm the Cline panel lists the server and tools. /` |
| home-write | `docs/agents/security.md:55` | `- Deny access to sensitive paths (`~/.ssh`, `~/.gnupg`, etc.)` |
| home-write | `docs/agents/troubleshooting.md:29` | `- **Claude Code:** Run `/mcp` to verify. Check `.mcp.json` or `~/.claude.json`` |
| home-write | `docs/agents/troubleshooting.md:30` | `- **Codex CLI:** Check `~/.codex/config.toml` for `[mcp_servers.kicad]`` |
| home-write | `docs/agents/troubleshooting.md:31` | `- **Gemini CLI:** Run `/mcp`. Check `~/.gemini/settings.json`` |
| home-write | `docs/agents/troubleshooting.md:61` | `1. **Claude Desktop config path:** `~/.config/Claude/claude_desktop_config.json`` |
| home-write | `docs/agents/windsurf.md:8` | `Add the server to `~/.codeium/windsurf/mcp_config.json` (the file Cascade reads),` |
| home-write | `docs/agents/zed.md:9` | `Open **`zed: open settings`** (or edit `~/.config/zed/settings.json`) and add:` |
| home-write | `docs/client-configuration.md:125` | `/ Codex CLI / IDE extension  / `~/.codex/config.toml`, or a trusted `<project>/.codex/config.toml`                                          ` |
| home-write | `docs/client-configuration.md:128` | `/ Cursor                     / `<project>/.cursor/mcp.json` or `~/.cursor/mcp.json`                                                         ` |
| home-write | `docs/client-configuration.md:129` | `/ Gemini CLI                 / `~/.gemini/settings.json` or `<project>/.gemini/settings.json`                                               ` |
| home-write | `docs/client-configuration.md:135` | `Codex stores MCP servers in `~/.codex/config.toml` or a trusted project-scoped` |
| home-write | `docs/client-configuration.md:148` | ``~/.codex/config.toml`:` |
| home-write | `docs/client-configuration.md:220` | `Use `.cursor/mcp.json` for project configuration or `~/.cursor/mcp.json` for global` |
| home-write | `docs/client-configuration.md:242` | `Add the server to `~/.gemini/settings.json`:` |
| home-write | `docs/configuration.md:8` | `4. `~/.config/kicad-mcp-pro/config.toml`` |
| home-write | `docs/development/testing-policy.md:35` | `Tests that initialize or mutate Git repositories must use test-owned temporary directories and an isolated process environment. Set `HOME`, ` |
| home-write | `docs/examples/clients/codex-config.toml:2` | `# ~/.codex/config.toml (or your trusted project's .codex/config.toml).` |
| home-write | `integrations/antigravity/README.md:13` | `1. Copy `mcp_config.example.json` to `~/.gemini/config/mcp_config.json`.` |
| home-write | `integrations/antigravity/README.md:20` | `Antigravity uses a shared config file with Gemini CLI. Both IDE and CLI read from `~/.gemini/config/mcp_config.json`.` |
| home-write | `integrations/claude-code/README.md:43` | `cp -r kicad-pcb-review-skill ~/.claude/skills/` |
| home-write | `integrations/claude-desktop/README.md:20` | `Config path: `~/.config/Claude/claude_desktop_config.json`` |
| home-write | `integrations/codex/README.md:13` | `1. Copy `config.toml.example` to `~/.codex/config.toml`.` |
| home-write | `integrations/codex/install.mjs:16` | `: path.join(os.homedir(), ".codex");` |
| home-write | `integrations/common/doctor.py:88` | `"codex": lambda: Path.home() / ".codex" / "config.toml",` |
| home-write | `integrations/common/doctor.py:89` | `"gemini": lambda: Path.home() / ".gemini" / "settings.json",` |
| home-write | `integrations/common/doctor.py:90` | `"antigravity": lambda: Path.home() / ".gemini" / "config" / "mcp_config.json",` |
| home-write | `integrations/common/doctor.py:97` | `else Path.home()` |
| home-write | `integrations/common/doctor.py:103` | `else Path.home() / ".config" / "Claude" / "claude_desktop_config.json"` |
| home-write | `integrations/common/validate-mcp-config.py:116` | `"codex": Path.home() / ".codex" / "config.toml",` |
| home-write | `integrations/common/validate-mcp-config.py:117` | `"gemini": Path.home() / ".gemini" / "settings.json",` |
| home-write | `integrations/common/validate-mcp-config.py:118` | `"antigravity": Path.home() / ".gemini" / "config" / "mcp_config.json",` |
| home-write | `integrations/common/validate-mcp-config.py:122` | `"claude-desktop": Path.home() / ".config" / "Claude" / "claude_desktop_config.json",` |
| home-write | `integrations/gemini-cli/README.md:13` | `1. Copy `settings.example.json` to `~/.gemini/settings.json`.` |
| home-write | `integrations/vscode/README.md:65` | `- Use `denyRead` for sensitive paths like `~/.ssh`.` |
| home-write | `packages/kicad-plugin/README.md:30` | `~/.local/share/kicad/10.0/plugins/kicad-mcp-pro (Linux; lowercase` |
| home-write | `scripts/check_github_actions_policy.py:37` | `resolved_root = allowed_root.expanduser().resolve(strict=True)` |
| home-write | `scripts/check_github_actions_policy.py:38` | `candidate = path.expanduser()` |
| home-write | `scripts/check_github_actions_policy.py:278` | `root = args.root.expanduser().resolve(strict=True)` |
| home-write | `scripts/check_reference_board_attempt_readiness.py:73` | `_OPS_CONFIG = Path.home() / ".config/ops-node/mcp.json"` |
| home-write | `scripts/check_reference_board_attempt_readiness.py:110` | `home = Path.home()` |
| home-write | `scripts/check_release_asset_mutations.py:620` | `root = args.root.expanduser().resolve(strict=True)` |
| home-write | `scripts/check_rustsec_audit.py:39` | `root = allowed_root.expanduser().resolve(strict=True)` |
| home-write | `scripts/check_rustsec_audit.py:40` | `resolved = path.expanduser().resolve(strict=True)` |
| home-write | `scripts/kicad11_headless_canary.py:62` | `resolved = path.expanduser().resolve(strict=True)` |
| home-write | `scripts/kicad11_headless_canary.py:74` | `resolved = path.expanduser().resolve(strict=True)` |
| home-write | `scripts/kicad_canary.py:830` | `candidates.append(Path(raw).expanduser())` |
| home-write | `scripts/run_uv.py:55` | `candidates.append(Path(override).expanduser())` |
| home-write | `scripts/runtime_path_safety.py:18` | `resolved = Path(raw_path).expanduser().resolve()` |
| home-write | `scripts/runtime_path_safety.py:22` | `*(Path(root).expanduser().resolve() for root in extra_roots),` |
| home-write | `scripts/security_local.py:53` | `Path.home() / "go" / "bin",` |
| home-write | `scripts/security_local.py:54` | `Path.home() / ".local" / "bin",` |
| home-write | `scripts/security_local.py:55` | `Path.home() / ".cargo" / "bin",` |
| home-write | `src/kicad_mcp/bridge.py:130` | `base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))` |
| home-write | `src/kicad_mcp/bridge.py:132` | `base = Path.home() / "Library" / "Application Support"` |
| home-write | `src/kicad_mcp/bridge.py:134` | `base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))` |
| home-write | `src/kicad_mcp/cli_init.py:41` | `_ZED_UNIX_CONFIG_PATH = "~/.config/zed/settings.json"` |
| home-write | `src/kicad_mcp/cli_init.py:53` | `"linux": "~/.config/Claude/claude_desktop_config.json",` |
| home-write | `src/kicad_mcp/cli_init.py:57` | `"darwin": "~/.cursor/mcp.json",` |
| home-write | `src/kicad_mcp/cli_init.py:58` | `"linux": "~/.cursor/mcp.json",` |
| home-write | `src/kicad_mcp/cli_init.py:63` | `"linux": "~/.config/Code/User/settings.json",` |
| home-write | `src/kicad_mcp/cli_init.py:67` | `"darwin": "~/.codeium/windsurf/mcp_config.json",` |
| home-write | `src/kicad_mcp/cli_init.py:68` | `"linux": "~/.codeium/windsurf/mcp_config.json",` |
| home-write | `src/kicad_mcp/cli_init.py:101` | `expanded = os.path.expandvars(os.path.expanduser(raw))` |
| home-write | `src/kicad_mcp/cli_init.py:115` | `write_target = config_path.expanduser().resolve()` |
| home-write | `src/kicad_mcp/cli_init.py:162` | `"""Write ``~/.kicad-mcp/config.json`` with the wizard choices."""` |
| home-write | `src/kicad_mcp/cli_init.py:163` | `config_path = output or (Path.home() / ".kicad-mcp" / "config.json")` |
| home-write | `src/kicad_mcp/cli_init.py:234` | `# Write ~/.kicad-mcp/config.json` |
| home-write | `src/kicad_mcp/cli_init.py:283` | `candidate = Path(os.path.expandvars(os.path.expanduser(raw.strip())))` |
| home-write | `src/kicad_mcp/config.py:22` | `CONFIG_FILE = Path.home() / ".config" / "kicad-mcp-pro" / "config.toml"` |
| home-write | `src/kicad_mcp/config.py:259` | `return value.expanduser()` |
| home-write | `src/kicad_mcp/config.py:261` | `return Path(value).expanduser()` |
| home-write | `src/kicad_mcp/config.py:271` | `return value.expanduser()` |
| home-write | `src/kicad_mcp/config.py:276` | `return Path(endpoint).expanduser()` |
| home-write | `src/kicad_mcp/config.py:528` | `setattr(self, field_name, path.expanduser().resolve())` |
| home-write | `src/kicad_mcp/config.py:547` | `project_root = self.project_dir.expanduser().resolve()` |
| home-write | `src/kicad_mcp/diagnostics.py:265` | `current = start.expanduser().resolve()` |
| home-write | `src/kicad_mcp/discovery.py:273` | `resolved = cli_path.expanduser().resolve(strict=False)` |
| home-write | `src/kicad_mcp/discovery.py:340` | `expanded_cli = cli_path.expanduser()` |
| home-write | `src/kicad_mcp/discovery.py:365` | `Path.home() / "AppData" / "Roaming" / "kicad" / "11.0",` |
| home-write | `src/kicad_mcp/discovery.py:366` | `Path.home() / "AppData" / "Roaming" / "kicad" / "10.0",` |
| home-write | `src/kicad_mcp/discovery.py:370` | `Path.home() / "Library" / "Preferences" / "kicad" / "11.0",` |
| home-write | `src/kicad_mcp/discovery.py:371` | `Path.home() / "Library" / "Preferences" / "kicad" / "10.0",` |
| home-write | `src/kicad_mcp/discovery.py:374` | `Path.home() / ".config" / "kicad" / "11.0",` |
| home-write | `src/kicad_mcp/discovery.py:375` | `Path.home() / ".config" / "kicad" / "10.0",` |
| home-write | `src/kicad_mcp/discovery.py:393` | `candidate = Path(raw).expanduser()` |
| home-write | `src/kicad_mcp/discovery.py:403` | `root = directory.expanduser().resolve()` |
| home-write | `src/kicad_mcp/discovery.py:404` | `resolved = candidate.expanduser().resolve()` |
| home-write | `src/kicad_mcp/discovery.py:489` | `candidate = Path(active_file).expanduser()` |
| home-write | `src/kicad_mcp/discovery.py:561` | `resolved_root = watch_dir.expanduser().resolve()` |
| home-write | `src/kicad_mcp/evals/live_object_identity_differential.py:30` | `normalized_path = str(Path(raw_path).expanduser().resolve(strict=False))` |
| home-write | `src/kicad_mcp/evals/live_object_identity_differential.py:47` | `resolved = project_or_board.expanduser().resolve(strict=True)` |
| home-write | `src/kicad_mcp/evals/opencode_cli_adapter.py:200` | `"XDG_CONFIG_HOME": str(root / "config"),` |
| home-write | `src/kicad_mcp/evals/reference_agent_runner.py:141` | `Path.home() / "AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe",` |
| home-write | `src/kicad_mcp/evals/roundtrip_differential.py:65` | `resolved = project_or_board.expanduser().resolve(strict=True)` |
| home-write | `src/kicad_mcp/file_formats.py:32` | `resolved_root = allowed_root.expanduser().resolve(strict=True)` |
| home-write | `src/kicad_mcp/file_formats.py:33` | `resolved_path = path.expanduser().resolve(strict=True)` |
| home-write | `src/kicad_mcp/ipc/discovery.py:40` | `return Path(endpoint).expanduser()` |
| home-write | `src/kicad_mcp/ir/from_kicad.py:183` | `sch_file = Path(sch_path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:16` | `return fallback.expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:17` | `return Path(path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:25` | `resolved_root = root.expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:26` | `resolved_path = path.expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:41` | `candidate = Path(raw_path).expanduser()` |
| home-write | `src/kicad_mcp/path_safety.py:63` | `resolved = Path(raw_path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/path_safety.py:66` | `approved_roots = (repo_root.expanduser().resolve(), Path(tempfile.gettempdir()).resolve())` |
| home-write | `src/kicad_mcp/path_safety.py:76` | `candidate = Path(raw_path).expanduser()` |
| home-write | `src/kicad_mcp/pcb/transaction_lifecycle.py:69` | `normalized_path = str(Path(project_path).expanduser().resolve(strict=False))` |
| home-write | `src/kicad_mcp/project/context.py:42` | `project_path = Path(project_dir).expanduser().resolve()` |
| home-write | `src/kicad_mcp/project/context.py:47` | `selected_pcb = Path(pcb_file).expanduser().resolve() if pcb_file else scan.get("pcb")` |
| home-write | `src/kicad_mcp/project/context.py:48` | `selected_sch = Path(sch_file).expanduser().resolve() if sch_file else scan.get("schematic")` |
| home-write | `src/kicad_mcp/project/context.py:57` | `Path(output_dir).expanduser().resolve() if output_dir else project_path / "output"` |
| home-write | `src/kicad_mcp/project/creation.py:58` | `base_dir = Path(path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/project/design_spec.py:524` | `candidate = raw_path.expanduser().resolve()` |
| home-write | `src/kicad_mcp/project/discovery.py:28` | `directory = Path(path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/routing/autorouter.py:83` | `freerouting_jar_path=Path(freerouting_jar_path).expanduser()` |
| home-write | `src/kicad_mcp/server_info.py:169` | `resolved = cli_path.expanduser().resolve(strict=False)` |
| home-write | `src/kicad_mcp/setup.py:153` | `"user": "~/.claude.json",` |
| home-write | `src/kicad_mcp/setup.py:157` | `"user": "~/.codex/config.toml",` |
| home-write | `src/kicad_mcp/setup.py:161` | `"user": "~/.gemini/settings.json",` |
| home-write | `src/kicad_mcp/setup.py:166` | `"user": "~/.config/opencode/opencode.json",` |
| home-write | `src/kicad_mcp/setup.py:171` | `"user": "~/.cursor/mcp.json",` |
| home-write | `src/kicad_mcp/setup.py:183` | `"user": "~/.gemini/config/mcp_config.json",` |
| home-write | `src/kicad_mcp/setup.py:198` | `Path.home()` |
| home-write | `src/kicad_mcp/setup.py:204` | `return Path.home() / ".config" / "Claude" / _CLAUDE_DESKTOP_CONFIG_FILENAME` |
| home-write | `src/kicad_mcp/setup.py:233` | `path = Path(raw).expanduser()` |
| home-write | `src/kicad_mcp/setup.py:235` | `path = Path(project_dir).expanduser() / path` |
| home-write | `src/kicad_mcp/tools/export.py:84` | `candidate = Path(name).expanduser()` |
| home-write | `src/kicad_mcp/tools/footprint.py:128` | `in_path = Path(input_path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/footprint.py:141` | `out_dir = Path(output_dir).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/footprint.py:163` | `return str(Path(out_path).expanduser().resolve())` |
| home-write | `src/kicad_mcp/tools/footprint.py:209` | `in_path_obj = Path(in_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/jobset.py:121` | `out_path = Path(output).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/jobset.py:161` | `jobset_path = Path(jobset_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/jobset.py:202` | `jobset_path = Path(jobset_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/manufacturing_imports.py:28` | `return Path(path_text).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/pcb.py:3320` | `image_path = Path(source_image).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/symbol.py:39` | `in_path = Path(in_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/symbol.py:51` | `out_path = str(Path(out_path).expanduser().resolve())` |
| home-write | `src/kicad_mcp/tools/symbol.py:167` | `in_path = Path(input_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/symbol.py:180` | `out_dir = Path(output_dir).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/upgrade.py:41` | `in_path = Path(in_file).expanduser().resolve()` |
| home-write | `src/kicad_mcp/tools/upgrade.py:53` | `out_path = str(Path(out_raw).expanduser().resolve())` |
| home-write | `src/kicad_mcp/tools/version_control.py:43` | `path = Path(project_dir).expanduser().resolve()` |
| home-write | `src/kicad_mcp/utils/library_tables.py:54` | `os.path.expanduser("~/.config"),` |
| home-write | `src/kicad_mcp/utils/library_tables.py:55` | `os.path.expanduser("~/Library/Preferences"),` |
| home-write | `src/kicad_mcp/utils/logging.py:105` | `resolved_log_file = log_file.expanduser()` |
| home-write | `src/kicad_mcp/utils/ngspice.py:68` | `candidates.append(configured.expanduser())` |
| home-write | `src/kicad_mcp/utils/ngspice.py:85` | `resolved = candidate.expanduser()` |
| home-write | `src/kicad_mcp/utils/schematic_roundtrip.py:103` | `target = Path(path).expanduser().resolve()` |
| home-write | `src/kicad_mcp/web/routes.py:170` | `return "~/.codex/config.toml"` |
| home-write | `tests/gui/manual_kicad_107_bom_gui.sh:91` | `export HOME="$workspace/home" XDG_CONFIG_HOME="$workspace/home/.config"` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:75` | `root = Path(raw_path).expanduser() if raw_path else tmp_path / "kicad-gui-smoke-artifacts"` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:130` | `expanded = path.expanduser()` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:172` | `bin_dirs.append(Path(raw).expanduser())` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:178` | `bin_dirs.append(Path(raw).expanduser().parent)` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:695` | `default_cache = Path.home() / "Library/Caches/KiCad/10.0/python-environments"` |
| home-write | `tests/gui/test_kicad_gui_live_context.py:696` | `default_docs = Path.home() / "Documents/KiCad/10.0/plugins"` |
| home-write | `tests/integration/test_kicad_cli_smoke.py:30` | `candidates.append(Path(raw_path).expanduser())` |
| home-write | `tests/integration/test_version_control_tools.py:57` | `monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))` |
| home-write | `tests/unit/test_cli_init.py:40` | `assert paths["darwin"] == "~/.config/zed/settings.json"` |
| home-write | `tests/unit/test_cli_init.py:41` | `assert paths["linux"] == "~/.config/zed/settings.json"` |
| home-write | `tests/unit/test_cli_init.py:168` | `# output through Path.home(), and a developer machine may already hold an` |
| home-write | `tests/unit/test_cli_init.py:169` | `# unrelated ~/.kicad-mcp whose contents break the cleanup below.` |
| home-write | `tests/unit/test_draft_release_inventory.py:293` | `outside_path = Path.home().parent / "unapproved-release-fixture.txt"` |
| home-write | `tests/unit/test_draft_release_inventory.py:299` | `outside_directory = Path.home().parent / "unapproved-release-fixture"` |
| home-write | `tests/unit/test_draft_release_retry_plan.py:232` | `case["manifest_path"] = Path.home().parent / "unapproved-release-fixture.txt"` |
| home-write | `tests/unit/test_draft_release_retry_plan.py:239` | `case["downloaded_existing_dir"] = Path.home().parent / "unapproved-release-fixture"` |
| home-write | `tests/unit/test_kicad_107_bom_gui_manual.py:21` | `assert 'XDG_CONFIG_HOME="$workspace/home/.config"' in source` |
| home-write | `tests/unit/test_path_safety.py:288` | `escaped_path = Path.home() / ".ssh" / "id_rsa"` |
| home-write | `tests/unit/test_reference_agent_runner.py:792` | `assert Path.home() / "AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe" in candidates` |
| home-write | `tests/unit/test_reference_board_attempt_preflight.py:181` | `executable = Path.home() / ".local/bin/uv"` |
| home-write | `tests/unit/test_script_path_safety.py:16` | `escaped_path = Path.home() / ".ssh" / "id_rsa"` |
| home-write | `tests/unit/test_script_path_safety.py:22` | `trusted = Path.home() / ".github-output-test"` |
| home-write | `tests/unit/test_setup.py:80` | `== Path.home()` |
| home-write | `tests/unit/test_setup.py:92` | `assert path == Path.home() / ".config" / "Claude" / "claude_desktop_config.json"` |
