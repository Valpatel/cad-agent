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


## Verify priorities and active source use before declaring the mirror corrected

Independent review reproduced false success on the initial helper with Azure
`priority:99` and archive `priority:garbage`. On 2026-11-11 a temporary-file control
against the prior committed helper reproduced both successes. A dormant mirror
list also cannot prove apt uses it. The correction now requires the pinned three
URL/priority pairs (or their already-corrected two-fallback form), rejects missing,
duplicate, extra and malformed entries, and verifies active Ubuntu deb822 source
stanzas reference exactly `mirror+file:/etc/apt/apt-mirrors.txt` before any write.
Source files are read without mutation. Fixture controls reject a direct Azure or
archive source, disabled/comment-only source, and missing signature field; all
failure controls preserve both inputs byte-for-byte. This is a narrow guard for
the observed mirror/source boundary, not a complete apt configuration validator.

The original Chromium run also exposed missing tool/test ownership table entries.
The helper was moved under the actual growth split `tools/ci/`, with a mapped
README, and the test's existing README table now owns the regression harness.


A second review control showed that merely nonempty source fields accepted
`Types: deb-src`, `Suites: jammy`, `Signed-By: /tmp/other.gpg` and `Enabled: maybe`.
Temporary-file controls reproduced all four against 5758b085. The guard now
checks the workflow's actual Ubuntu 24.04/noble OS identity, derives the four
expected suite names from that codename and verifies complete nonoverlapping
suite coverage, `Types: deb`, the four default components, the Ubuntu archive
keyring and Enabled absent/yes. It rejects extra fields rather than treating a
partial parse as a known profile. Combined and producer-style split stanzas are
accepted without source mutation; altered values fail before mirror mutation.
The source field profile is grounded in Canonical's
[pinned cloud-init producer template](https://github.com/canonical/cloud-init/blob/179c69886be4c8e7e93bf22c34e97bf03e142b22/templates/sources.list.ubuntu.deb822.tmpl),
with runner URIs transformed by the pinned runner configuration above. This
supports only the named workflow image/profile, not arbitrary apt installations.
