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


## Let a transport fail before the outer process timeout restarts it

On 2026-11-11, full job 130651435918 at 9c776a7 passed the supported source guard,
then stalled three times on `https://archive.ubuntu.com/ubuntu` before extras or
tests. Microsoft HTTPS indexes succeeded. `gh api repos/Valpatel/cad-agent/actions/jobs/130651435918/logs`
showed the expected HTTPS fallback list, four sequential `Ign` lines per attempt,
and exit 1 after the unchanged 90-second process limits. Thus removing the Azure
entry alone did not establish successful provisioning.

The [pinned runner apt configuration](https://github.com/actions/runner-images/blob/c03600ca998467081ccec9bb9dbf5de6b68e862a/images/ubuntu/scripts/build/configure-apt.sh)
explains that retries remain on one URI before mirror failover. The
[apt mirror transport manual](https://manpages.ubuntu.com/manpages/bionic/man1/apt-transport-mirror.1.html)
confirms that the next mirror is tried after the current mirror fails. The CI
correction sets command-local `Acquire::Retries=0` and HTTP/HTTPS timeout 5 seconds
on both existing update/install calls. The same three outer attempts, 90-second
process limits, recovery step, required packages and hard final failure remain.
These settings allow transport failure/fallback within the process budget; they
do not guarantee that any remote mirror is reachable.

The regression uses the actual existing apt binary with temporary sources,
cache and list directories and loopback servers only: the preferred server stalls,
the fallback serves deliberately unsigned metadata. A one-second transport probe
reached fallback in 2.18 seconds; apt then returned 100 and rejected the unsigned
repository. The committed regression consumes the workflow's actual five-second
options and passed in 10.59 seconds, still rejecting unsigned metadata. It neither
installs packages nor changes system apt files. No signature-bypass option is used.
This does not resolve separate remote DNS or unrelated container provisioning.

The same source run found a 658-pixel diagram in the new tools/ci map with no
17-pixel desktop scrollbar reserve. A compact top-down, palette-mapped diagram
replaces the horizontal chain. Targeted real Chromium on its actual draft route
checks 320/360/1100/1366 pixels in both themes. The natural drawing is 196 pixels
wide, with 658 pixels available at 1100 and no page overflow. That local check
uses client drawing; normal prerendered publication and both CI engines remain
separate required acceptance evidence.
