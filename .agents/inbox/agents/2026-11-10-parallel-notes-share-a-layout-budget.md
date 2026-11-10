# Parallel note additions share the final repository layout budget

Date: 2026-11-10. Two individually green feature branches added distinct incident records and then were combined.
The accepted physics branch and the playback-progress branch kept source/code/tests unchanged during the normal
merge, but together put 21 direct files in `.agents/inbox/`, exceeding its existing 20-file growth limit.

Dated command/output evidence from the combined tree:

```text
python3 -m pytest -q tests/simulation/test_robot.py tests/review/test_gate_assembly.py tests/review/test_gate_subassembly.py tests/publish/test_release_guides.py tests/repo/test_layout.py tests/repo/test_areas.py
2 failed, 288 passed in 55.34s
.agents/inbox/ holds 21 files, over the growth limit of 20
```

Cause: each branch was below the limit against its own base; independent passes did not establish the final
union's inventory. The correction moves the four review-domain incidents with `git mv` into `inbox/review/`,
adds its README/Mermaid map and parent entry, and updates every current link, including the moved numerical
incident's relative docs target. The root inbox falls to 17 direct incident files. No limit/exception is relaxed.

Corrective rule: check the real merged file inventory and all owning consumers after parallel work combines.
When a folder exceeds the existing growth rule, split by actual domain and preserve history, navigation and
references rather than adding an exception or dropping evidence. Existing integration and independent review
still apply to the resulting union.

Limits: this is a repository-structure check; it does not validate geometry, physical assembly or environment
providers. All older worktrees/providers remain untouched; only tracked notes in the owned feature tree move.

After the domain split, the identical combined command passed 290 tests in 54.44 s with only the existing
webkit-folder warning. A separate relative-link check examined 129 local links across the affected maps and
moved records, with zero missing targets. Approved playback and physics code/test bytes remained unchanged.
