# Weekly upstream update (run by the agent)

1. `python tools/vendor_sync.py check`: list the upstreams that moved. No code is downloaded.
2. For each project that moved:
   1. Run `python tools/vendor_sync.py import <name>`. It creates `vendor-update/<name>-<sha>`, imports, re-applies
      our patches and writes `vendor/reports/<name>-<sha>.md`.
   2. Read the report. Every new HIGH finding needs an explanation. Read new network, subprocess and telemetry code
      and dependency-file diffs for intent.
   3. Run the sandboxed tests and the evals: J501 geometry, clearance, storage, cable routes and fasteners.
   4. If the update is clean, run `python tools/vendor_sync.py accept <name>`, commit the report, merge to main and
      push. Otherwise discard the branch and record the reason in the report.
3. If a patch no longer applies, port it and keep it minimal. Offer generally useful fixes upstream.
4. Note what changed (new skills, fixed bugs, regressions) in `upstreams/CHANGELOG.md`.
