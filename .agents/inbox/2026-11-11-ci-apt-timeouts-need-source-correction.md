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


## A Canonical DNS outage needs a different registered mirror hostname

The 0ce30bbb full job 130659597482 still failed provisioning, now explicitly
reporting `Temporary failure resolving 'archive.ubuntu.com'` while Microsoft
indexes succeeded. The five-second transport settings were not a DNS repair;
per-URI DNS waits still took about twenty seconds and all three outer attempts
exhausted their process caps. No timeout values were tuned again.

On 2026-11-11, the independently fetched [Canonical RSS](https://status.canonical.com/rss)
reported `DNS - Major Outage` dated 14:26 UTC; parent receipt SHA-256
`628c7cf1a9b885d0a15b7872d5235923c6068a8888b4867086cd1a9a7f89329b`.
[runner-images #15296](https://github.com/actions/runner-images/issues/15296)
also reports contemporaneous Ubuntu DNS failures while unrelated services work.
Older archive/security Operational timestamps do not contradict a newer DNS outage.

The [Ubuntu Official Archive Mirrors listing](https://launchpad.net/ubuntu/+archivemirrors)
links Pilot Fiber's HTTPS base `https://mirror.pilotfiber.com/ubuntu/` and its
[registration](https://launchpad.net/ubuntu/+mirror/mirror.pilotfiber.com-archive).
Direct Launchpad fetches timed out during the outage; the retrieved primary listing
is cached evidence of registration, not a fresh probe/status guarantee. Enzu was
considered but rejected when noble metadata returned 404. Pilot's direct HTTPS
metadata was fetched successfully for all four noble suites and verified with the
existing `/usr/share/keyrings/ubuntu-archive-keyring.gpg`, signer fingerprint
`F6ECB3762474EDA9D21B7022871920D1991BC93C`:

```text
2026-11-11 UTC: curl -fsSL --max-time 20 https://mirror.pilotfiber.com/ubuntu/dists/<suite>/InRelease
2026-11-11 UTC: gpgv --keyring /usr/share/keyrings/ubuntu-archive-keyring.gpg <downloaded-InRelease>
noble: good Ubuntu signature; immutable base dated 2024-04-25
noble-updates: good Ubuntu signature; Date 2026-11-11 05:14:56 UTC
noble-backports: good Ubuntu signature; Date 2026-11-10 07:35:30 UTC
noble-security: good Ubuntu signature; Date 2026-11-11 07:35:28 UTC
```

The helper now replaces only the validated Azure priority-1 URL with that registered
HTTPS base; Canonical archive/security priorities 2/3 and every source/signature
setting remain. Only the exact original and exact corrected profiles are accepted,
including idempotence and altered-preferred-mirror negative controls. There is no
OS DNS modification, address pinning, TLS/signature bypass, dependency change or
failed-job rerun. This workstation readback does not establish hosted-runner
reachability: new normal CI must still provision, import all extras and execute
the full suite, and both browser jobs must pass before any merge.

## Capture the rejected producer profile before changing its allowlist

On 2026-11-12, `gh api repos/Valpatel/cad-agent/actions/jobs/131327824668/logs`
reported `ValueError: unexpected hosted runner mirror entry or priority` before
apt, extras or tests in #616. A prior #611 attempt had the same rejection. The
failed log does not contain the mirror bytes. Its AWS backend/image metadata
does not establish the rejected entry; the advertised image ref returned 404,
while the current public producer still showed the original Azure profile.
The exact cause remains unknown at this checkpoint (#617).

The diagnostic now records line numbers, URI scheme/host/standard Ubuntu path,
numeric priority and token count on rejection, bounded to twelve entries. It
omits credentials, query/fragment, nonstandard paths and arbitrary extra fields.
Tests exercise the actual rejection, confirm both files stay unchanged, and
plant private strings to check they are absent from the message. Accepted
profiles, active-source/keyring validation and CI failure conditions are unchanged.
Use a fresh observed profile to justify a correction; a later pass on another
runner does not explain or repair this rejection. This diagnostic itself is
not a provisioning fix or successful full-suite evidence.

## An observed cloud profile is not a wildcard

On 2026-11-12, [full job 131436221538](https://github.com/Valpatel/cad-agent/actions/runs/43290750907/job/131436221538)
on PR634 finally provided the producer evidence missing from #617. `configure` rejected this profile before apt,
extras or tests ran:

```text
http://us-east-2.ec2.archive.ubuntu.com/ubuntu/ priority:1
https://archive.ubuntu.com/ubuntu/ priority:2
https://security.ubuntu.com/ubuntu/ priority:3
```

The URI/priority tuples come from the bounded rejection diagnostic, not a guess based on the cloud host.
The source file was not logged: isolated replay uses the already-supported noble/source/keyring fixture and
does not pretend to recover the failed runner's complete filesystem. Before correction,
`PYTHONPATH=software python -m pytest -q tests/repo/test_ci_apt_mirror.py -k observed_ec2`
reported **2 failed, 2 passed, 10 deselected, 15 subtests passed**; the exact primary was rejected without writes.

Accept only that additional exact primary URI and priority, with the existing complete Canonical fallback set.
Replace it with the same registered HTTPS preference used for Azure. Keep active-source, suite, component,
keyring, duplicate and malformed-input guards unchanged. Report the recognized input primary after validation
so a future successful hosted run identifies which path it exercised.

Controls cover byte-preserving source/comment/whitespace handling and idempotence, plus rejection without writes
for another EC2 region, lookalike host, userinfo, query, unobserved scheme/path, wrong priority, mixed/duplicate
primaries, missing fallbacks, incomplete suites, another keyring, inactive mirror source and `Trusted: yes`.
The existing loopback apt test still reaches its fallback and rejects unsigned metadata; no system apt files or
packages are changed by that test. The complete focused apt/release/area/layout suite passed after correction.

**Rule:** use captured producer input to extend an exact recognized profile; do not replace a failed guard with
a wildcard, a cloud-brand inference or a retry. A successful job on Azure does not prove the EC2 runner ran the
corrected path. Fresh ordinary CI and its recognized-input log remain separate evidence. Other unobserved profiles
must still fail with bounded diagnostics, and this correction does not promise all future provisioning succeeds.


## Retain the rejected source shape without admitting it

2026-11-12 UTC: release649 full job131538546246 (run43320195481, headf0ae99d6)
failed before apt/extras/tests at `validate_source`: `active Ubuntu source must use the expected mirror file`.
The actual Ubuntu source bytes were absent. Raw job-log SHA256:
`ada6ee7f2157da06e6a79a5f1afe3711b5613177ad07effe1b4ff8e59ab23fd8`.
Ubuntu24.04.5/image20261111.127.1/AWS us-west-2 metadata does not establish the missing URI or cause.
The earlier observed mirror-list tuple correction and successful Azure-path runs remain separate evidence.

**Correction and rule:** when the existing source validator rejects, emit bounded known-field and redacted
URI-shape records plus the input hash, then rethrow the original ValueError before any write or success log.
Credentials, queries, arbitrary paths/field values and excess data stay hidden; visibility of an alternate
system path is not acceptance. Keep `validate_source`, mirror priorities, signatures and retry/deadline policy
unchanged. Independent synthetic configure controls preserve both files/the original error, reject alternate
source paths, and exercise continuation, malformed input, redaction and output bounds.19 tests and39 subtests
passed locally; no real rejected runner source was reconstructed or newly admitted.

**Limits and next:** the root cause remains UNKNOWN until a normal authorized diagnostic checkpoint captures
sufficient actual producer evidence. The original failure is not rerun or waived by adding diagnostics. A
source/configuration correction needs that evidence, independent review and all new normal CI. Release649
remains held; no local apt configuration, dependency, workflow or model runtime was changed.

## Recognize only the observed split security stanza

2026-11-12 [full job 131567345145](https://github.com/Valpatel/cad-agent/actions/runs/43327783983/job/131567345145)
rejected a two-stanza source before apt/tests. The untruncated diagnostic records the mirror-file source for
`noble noble-updates noble-backports` and `http://security.ubuntu.com/ubuntu` for `noble-security`, both with
`deb`, the four standard components and the Ubuntu archive keyring. Original source hash:
`fc0fadce467e557a358c63f5532de4590c02933dfff8016028bb0a319b0e8b44`.
This diagnoses that observed job; it does not reconstruct comments, blank lines, redacted URI components or
identify the missing source of historical release649f0ae. The original failed runs remain failures.

The bounded correction recognizes only that literal security URI with only the security suite, alongside
exactly one mirror-file stanza covering the remaining suites. Existing all-mirror profiles still work.
Complete suite/component coverage, no duplicates or unknown fields, active `deb` and the exact signed-by
keyring remain required before writes. The security source is retained byte for byte, not rewritten to HTTP
or added to the mirror list. The registered HTTPS preference affects the existing mirror file only. This
preserves upstream transport and authentication; it does not claim security traffic uses that preference.

Controls retain sources and verify idempotence for all three recognized mirror primaries. Modified hosts,
credentials, queries/fragments, schemes, trailing slashes, paths, extra URIs, wrong suites/keyrings, unsigned
options, inactive entries and extra stanzas fail without changing either file. The loopback apt test remains
responsible for proving unsigned metadata is rejected. Hosted success on another profile cannot establish
that the split profile was exercised, and no signature, retry, deadline or package-source bypass is introduced.
