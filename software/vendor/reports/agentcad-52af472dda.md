# agentcad 52af472dda -> 52af472dda (Apache-2.0)

Full scan of 234 files.
New findings (not in the reviewed baseline): HIGH 0, MEDIUM 105, LOW 5. Suppressed by baseline: 0.

## MEDIUM

| rule | file:line | text |
|---|---|---|
| dependency-file | `pyproject.toml:0` | `pyproject.toml` |
| env-dump | `scripts/verify_daemon_progress.py:70` | `env = dict(os.environ)` |
| subprocess | `scripts/verify_daemon_progress.py:75` | `server = subprocess.Popen(` |
| network | `src/agentcad/commands/feedback.py:6` | `from urllib.request import Request, urlopen` |
| network | `src/agentcad/commands/feedback.py:45` | `with urlopen(req, timeout=10) as resp:` |
| network | `src/agentcad/commands/subscribe.py:16` | `from urllib.request import Request, urlopen` |
| network | `src/agentcad/commands/subscribe.py:44` | `with urlopen(req, timeout=10) as resp:` |
| network | `src/agentcad/commands/view.py:1291` | `const response = await fetch(reviewBase + path, { ...options, headers });` |
| network | `src/agentcad/commands/view.py:3213` | `// at a cross-origin script directly. fetch() succeeds (jsdelivr sends` |
| network | `src/agentcad/commands/view.py:3218` | `const src = await fetch('https://cdn.jsdelivr.net/npm/gif.js@0.2.0/dist/gif.worker.js').then(r => r.text());` |
| network | `src/agentcad/daemon.py:292` | `server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| network | `src/agentcad/daemon.py:649` | `sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| subprocess | `src/agentcad/daemon.py:1150` | `proc = subprocess.Popen(` |
| network | `src/agentcad/project_viewer.py:19` | `from urllib.request import ProxyHandler, Request, build_opener` |
| subprocess | `src/agentcad/project_viewer.py:186` | `process = subprocess.Popen(` |
| network | `src/agentcad/project_viewer_page.py:85` | `const response = await fetch('state?client=' + client, {cache:'no-store', signal:AbortSignal.timeout(4000)});` |
| eval-exec | `src/agentcad/runners/build123d.py:340` | `exec(code, script_globals)` |
| subprocess | `src/agentcad/solid_compare.py:472` | `completed = subprocess.run(` |
| subprocess | `src/agentcad/solid_compare.py:1035` | `completed = subprocess.run(` |
| subprocess | `src/agentcad/validation.py:935` | `process = subprocess.Popen(` |
| env-dump | `src/agentcad/validation.py:1088` | `env = dict(os.environ)` |
| subprocess | `src/agentcad/validation.py:1130` | `completed = subprocess.run(` |
| subprocess | `src/agentcad/written_mesh.py:329` | `proc = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,` |
| eval-exec | `tests/test_bbox_coordinates.py:113` | `assert eval(expression, {"bbox": bbox}) == pytest.approx(coordinates["xyz".index(axis)])` |
| eval-exec | `tests/test_build123d_primitive_aliases.py:549` | `reference = eval(native_call, {**vars(build123d)}).bounding_box()` |
| eval-exec | `tests/test_build123d_primitive_aliases.py:819` | `tool = eval(point_along_x, namespace)` |
| subprocess | `tests/test_cli_input_recovery.py:210` | `result = subprocess.run(` |
| subprocess | `tests/test_comparison_fixtures.py:232` | `completed = subprocess.run(` |
| subprocess | `tests/test_comparison_fixtures.py:252` | `completed = subprocess.run(` |
| subprocess | `tests/test_comparison_fixtures.py:276` | `completed = subprocess.run(` |
| network | `tests/test_daemon.py:33` | `listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| network | `tests/test_daemon.py:68` | `listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| subprocess | `tests/test_daemon.py:130` | `proc = subprocess.Popen(` |
| network | `tests/test_daemon.py:207` | `reader, writer = socket.socketpair()` |
| network | `tests/test_daemon.py:225` | `reader, writer = socket.socketpair()` |
| network | `tests/test_daemon.py:255` | `s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| network | `tests/test_daemon.py:432` | `reader, writer = socket.socketpair()` |
| network | `tests/test_daemon.py:464` | `reader, writer = socket.socketpair()` |
| network | `tests/test_daemon.py:792` | `blocker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| network | `tests/test_daemon.py:823` | `attacker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| subprocess | `tests/test_daemon.py:1314` | `proc = subprocess.Popen(` |
| subprocess | `tests/test_daemon.py:1370` | `unrelated = subprocess.Popen(` |
| network | `tests/test_daemon.py:1373` | `listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` |
| subprocess | `tests/test_daemon.py:1533` | `# Replace the real subprocess.Popen with one that spawns a hung` |
| subprocess | `tests/test_daemon.py:1536` | `real_popen = subprocess.Popen` |
| subprocess | `tests/test_daemon.py:1546` | `monkeypatch.setattr("agentcad.daemon.subprocess.Popen", fake_popen)` |
| subprocess | `tests/test_daemon.py:2006` | `These tests use a real ``subprocess.run`` rather than ``CliRunner``` |
| env-dump | `tests/test_daemon.py:2029` | `env = dict(os.environ)` |
| subprocess | `tests/test_daemon.py:2047` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2056` | `r1 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2083` | `r2 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2143` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2149` | `r1 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2168` | `r2 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2217` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2223` | `r1 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2242` | `r2 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2286` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2293` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2311` | `r = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2349` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2356` | `first = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2376` | `second = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2423` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2432` | `r = subprocess.run(` |
| env-dump | `tests/test_daemon.py:2465` | `env = dict(os.environ)` |
| subprocess | `tests/test_daemon.py:2482` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2489` | `r1 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2516` | `r2 = subprocess.run(` |
| subprocess | `tests/test_daemon.py:2545` | `r3 = subprocess.run(` |
| env-dump | `tests/test_daemon.py:2909` | `env = dict(os.environ)` |
| subprocess | `tests/test_daemon.py:2934` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:2938` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:3022` | `subprocess.run(` |
| subprocess | `tests/test_daemon.py:3033` | `subprocess.run(` |
| subprocess | `tests/test_generate_skill_md.py:15` | `result = subprocess.run(` |
| subprocess | `tests/test_import.py:608` | `return subprocess.run(` |
| subprocess | `tests/test_inspect_graceful.py:498` | `return subprocess.run(` |
| subprocess | `tests/test_inspect_validation_budget.py:129` | `result = subprocess.run(` |
| subprocess | `tests/test_malformed_step_contracts.py:41` | `return subprocess.run(` |
| env-dump | `tests/test_module_execution.py:27` | `env = dict(os.environ)` |
| subprocess | `tests/test_module_execution.py:29` | `return subprocess.run(` |
| network | `tests/test_project_layout.py:32` | `from urllib.request import urlopen` |
| network | `tests/test_project_layout.py:43` | `with urlopen(url + "state", timeout=3) as response:` |
| network | `tests/test_project_layout.py:46` | `with urlopen(url + state["latest"]["artifact"], timeout=3) as response:` |
| network | `tests/test_project_layout.py:54` | `with urlopen(url + "state", timeout=3) as response:` |
| network | `tests/test_project_viewer.py:12` | `from urllib.request import Request, urlopen` |
| network | `tests/test_project_viewer.py:41` | `with urlopen(url, timeout=3) as response:` |
| network | `tests/test_project_viewer.py:146` | `with socket.socket() as listener:` |
| subprocess | `tests/test_project_viewer.py:223` | `child = subprocess.Popen([sys.executable, "-m", "agentcad.viewer_service"],` |
| subprocess | `tests/test_render_input_validation.py:87` | `result = subprocess.run(` |
| network | `tests/test_review.py:4` | `import urllib.request` |
| network | `tests/test_review.py:356` | `request = urllib.request.Request(` |
| network | `tests/test_review.py:361` | `with urllib.request.urlopen(request, timeout=3) as response:` |
| telemetry | `tests/test_run_dispatch.py:157` | `"""The on-disk meta.json carries the runtime for telemetry (Phase 6)."""` |
| subprocess | `tests/test_script_stdout_contract.py:27` | `"child_process": (` |
| subprocess | `tests/test_script_stdout_contract.py:29` | `"subprocess.run([sys.executable, '-c', 'print(\"child debug\")'], check=True)\n"` |
| subprocess | `tests/test_script_stdout_contract.py:36` | `"child_process": "child debug\n",` |
| env-dump | `tests/test_script_stdout_contract.py:51` | `env = dict(os.environ)` |
| subprocess | `tests/test_script_stdout_contract.py:59` | `return subprocess.run(` |
| subprocess | `tests/test_script_stdout_contract.py:158` | `"subprocess.run([sys.executable, '-c', 'print(\"stray child\")'], check=True)\n"` |
| subprocess | `tests/test_script_stdout_contract.py:162` | `result = subprocess.run(` |
| subprocess | `tests/test_script_stdout_contract.py:183` | `result = subprocess.run(` |
| subprocess | `tests/test_subprocess_contract.py:43` | `return subprocess.run(` |
| subprocess | `tests/test_validation_fixtures.py:164` | `completed = subprocess.run(` |

## LOW

| rule | file:line | text |
|---|---|---|
| home-write | `README.md:199` | `identity. Viewer state lives in `~/.cache/agentcad/viewer` (override with` |
| home-write | `src/agentcad/commands/diff.py:101` | `p = Path(ref).expanduser()` |
| home-write | `src/agentcad/commands/diff.py:106` | `p = Path(ref).expanduser()` |
| home-write | `src/agentcad/commands/docs.py:85` | `"  State: ~/.cache/agentcad/viewer (AGENTCAD_VIEWER_HOME overrides it).\n"` |
| home-write | `src/agentcad/project_viewer.py:37` | `else Path(os.environ.get("AGENTCAD_VIEWER_HOME", Path.home() / ".cache/agentcad/viewer")))` |
