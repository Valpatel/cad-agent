# Correct the failing apt source before collecting fresh CI evidence

**2026-11-11 UTC evidence:** `gh api repos/Valpatel/cad-agent/actions/jobs/130638645274/logs`
showed `file:/etc/apt/apt-mirrors.txt Mirrorlist`, repeated `Ign` responses from
`http://azure.archive.ubuntu.com/ubuntu`, three `apt try ... failed or timed out`
messages and `Process completed with exit code 1`. The failure preceded extras
installation and tests. No secrets appear in this evidence.

**Cause:** the hosted runner prefers the unresponsive Azure HTTP entry. The
[pinned image source](https://github.com/actions/runner-images/blob/c74a28e5f8943ae6a39cac7c3701dd6bd0a2ea51/images/ubuntu/scripts/build/configure-apt-sources.sh)
confirms Azure priority 1, Canonical HTTPS archive priority 2 and HTTPS security
priority 3. This is a provisioning failure, not feature test evidence.

**Corrective rule:** change the failing source path, preserve all dependencies,
signature verification and test/failure conditions, and collect fresh normal CI.
Never erase the failed attempt with a rerun or treat absent tests as passes.
`tools/ci/apt_mirror.py` removes only the exact Azure HTTP entry and requires the
existing expected HTTPS archive. Its regression tests cover the actual layout,
idempotence, preservation and failure without mutation on an unknown layout.

**Limits:** this is specific to the hosted runner mirror-list contract. It does
not prove runner network health or guarantee endpoint availability. #576's new
normal full job 130644697101 passed the system-library step; subsequent imports
and tests remain separate gates. `python3 tests/repo/test_ci_apt_mirror.py` passed
3/3 on this date; actual full and browser CI remain mandatory before merging.

Durable explanation: [process lesson](../../docs/lessons/process/agent-process.md#correct-a-failing-ci-mirror-before-retrying-the-same-provisioning-path).
Tracking: #575, PR #576.
