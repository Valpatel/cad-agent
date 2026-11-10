# A cancelled full check needs the active test and its stack

- **Rule:** Preserve the actual job annotation and last test progress before classifying a cancelled check.
  Report test identities while the full suite runs, and use pytest's existing thread-dump option to observe a slow
  test without changing its assertions, selection, dependencies or the job's hard time limit. A thread dump is
  diagnostic output, not a new test deadline or evidence that a native library caused the stall.
- **Observed, 2026-11-07:** PR #465 source `6a5145f1`, CI run 42403450255/job 128496027486, installed its full extras
  successfully. `python -m pytest -q -rs` started 18:54:11 UTC, last printed 97% at 19:04:13 UTC and remained silent
  until 19:23:07 UTC. The check annotation says: `The job has exceeded the maximum execution time of 30m0s`.
  The job/run concluded cancelled. There was no assertion traceback, exact active test or superseding CI run;
  the test and cause remain unknown. Later wheel/floor steps did not run.
- **Comparison:** The separate main `81b9fdc2` full run 42402863701/job 128494211534 passed 3577 tests with 24 skips in 671.27s.
  That successful run does not identify why source `6a5145f1` exceeded its cap.
- **Correction:** The full job reports unbuffered verbose test node IDs and enables the built-in
  `faulthandler_timeout=120` diagnostic. The same complete suite and 30-minute job cap remain; this does not
  skip a slow test, add a dependency, increase a resource bound or establish that the earlier problem is fixed.
- **Evidence:** [Failed full job](https://github.com/Valpatel/cad-agent/actions/runs/42403450255/job/128496027486),
  [independent cancellation classification](https://github.com/Valpatel/cad-agent/pull/465#issuecomment-6711955442),
  [successful comparison](https://github.com/Valpatel/cad-agent/actions/runs/42402863701/job/128494211534),
  [pytest fault-handler contract](https://docs.pytest.org/en/stable/how-to/failures.html#fault-handler).
- **Limits:** A future quiet or successful run cannot supply the missing historical test identity or cause.
  The new full head must actually complete all required checks before integration; this note is not a CI waiver.

The first local layout/release check of the added note retained 67 passes and two layout failures: the incident
inbox had reached 21 direct files against its 20-file growth bound. The note moved into the existing publication
incident folder, with its map and symptom link updated; the growth check and exception list remain unchanged.


## Added browser suites need a measured whole-job budget

On 2026-11-10 UTC, PR #505 source `05486eb6`, Chromium run 42763870631/job 129655671803, ended cancelled.
The check annotation explicitly states `The job has exceeded the maximum execution time of 15m0s`. Job start
was 05:43:14 UTC; the new portable assembly-release suite started at 05:57:16 (14m02 into the job), and was
cancelled at 05:58:16. The later diagram suite did not run. No assertion failure was reported.

The actual preceding steps passed: Playwright/dependency installation took 3m26, site unit tests 3m11, site
browser tests 4m17, catalogue 51s, the new shared guide browser suite 48s, legacy file viewer 57s, and the
remaining completed setup/build/part-table steps used the balance. The separately completed PR #501 Chromium
job and both local extracted-ZIP suites had exercised the same reader/portable test bytes; they do not turn
this cancelled whole job into a pass. The portable suite emitted its summary only after completing, so this
receipt does not establish which final portable case was active at cancellation.

Correction: the existing two-engine browser job has a bounded 20-minute whole-job budget for its now larger
workload. Every test command, assertion, engine, dependency and individual test timeout stays unchanged. The
full Python job retains its separate 30-minute cap and its earlier unknown stall remains unknown. A complete
new-head browser run is still mandatory; the original cancelled result is retained, and an unchanged retry or
a successful component study cannot waive it.

Evidence: [cancelled Chromium job](https://github.com/Valpatel/cad-agent/actions/runs/42763870631/job/129655671803),
[prior same-reader portable source](https://github.com/Valpatel/cad-agent/pull/501).


## Provision browser dependencies before the test job

On 2026-11-10 UTC, PR #506 at `ed74c5e7` retained two actual push WebKit cancellations at the existing
20-minute cap. Job 129682727629 spent 14m36 in Playwright's dependency/browser install: apt reported
`Fetched 114 MB in 14min 7s (135 kB/s)`. The website consumer began at 07:15:43 and was cancelled at
07:21:01; later catalogue, guide, portable-release and diagram suites did not run. The identical-head parallel
PR WebKit job 129682757230 completed every suite in 9m17, including setup in 34s. That comparison does not
turn the incomplete push lane into a pass or establish the underlying mirror/network cause.

After independent classification, the sole failed-job-only continuation, job 129690821933, also reached the
20-minute cap. Dependency/browser installation took 10m47; apt reported `Fetched 114 MB in 10min 16s
(185 kB/s)`. The website consumer passed in 8m39, then the catalogue consumer was cancelled after 23s;
all subsequent guide, portable-release and diagram suites remained unrun. There is no third unchanged retry.

Corrective rule: use the official matching Playwright 1.56.1 Noble image with browsers and OS dependencies
already baked in, pinned by the registry manifest digest. Keep the npm lockfile/library, every test command,
engine, assertion, individual timeout and 20-minute whole-job cap. Run commands with Bash as before, and key
the diagram cache by the pinned image identity so drawings from the older runner/font snapshot cannot be
silently reused. The image replaces the redundant apt/browser install only; the Python setup and extracted-ZIP
browser chain still have to complete in the actual changed-head CI.

The registry returned image manifest `sha256:f1e7e01021efd65dd1a2c56064be399f3e4de00fd021ac561325f2bfbb2b837a`
for `mcr.microsoft.com/playwright:v1.56.1-noble`; its linux/amd64 manifest is
`sha256:42f02d323c310069b4d54c94bd91a608966a486c3492c48ae0b1cea747ec5ca2`.
The matching image has a different packaged OS/font snapshot and an approximately 878 MiB compressed download;
metadata matching is not render acceptance or a network-speed guarantee. No local image install/pull was used.
Complete current two-engine CI and independent source review are required before integration. Original capped
runs and missing later suites stay explicit; this change supplies no waiver or product/physical acceptance.

Evidence: [first capped push job](https://github.com/Valpatel/cad-agent/actions/runs/42772311917/job/129682727629),
[sole continuation](https://github.com/Valpatel/cad-agent/actions/runs/42772311917/job/129690821933),
[independent first-cap classification](https://github.com/Valpatel/cad-agent/pull/506#issuecomment-6761546180),
[official pinned image build](https://github.com/microsoft/playwright/blob/v1.56.1/utils/docker/Dockerfile.noble),
[official image/version contract](https://github.com/microsoft/playwright/blob/v1.56.1/docs/src/docker.md).


The first changed-head container attempt (`5f828bdd`, browser jobs 129699702851 and 129699703068) successfully
pulled/initialized the image and installed the locked npm packages. Both then failed before rendering/tests at
`git ls-tree`: Git rejected the host-mounted checkout's ownership inside the container. The correction adds
`git config --global --add safe.directory "$GITHUB_WORKSPACE"` inside that ephemeral test container, before
site construction. It trusts only the exact checked-out CI workspace, not `*`, other paths or a workstation
configuration. Those initial failures remain explicit; the corrected head still needs all actual suites to pass.


The corrected workspace head (`0b6d6ca1`, WebKit job 129700458733) passed the actual website, catalogue,
assembly-guide, part-table and 32-case legacy file-viewer consumers in the container. `actions/setup-python`
then selected CPython 3.12.16 under the container's `/__t` toolcache mount, but invoking its `pip` launcher
failed with `cannot execute: required file not found` (exit 127). The exact launcher's shebang was not retained,
so a host-only interpreter path is an inference, not a separately proven historical cause. Portable ZIP and
final diagram consumers remained unrun; no complete lane acceptance follows from those earlier passes.

Use `python -m pip install -e ".[site]"` to invoke pip through the selected interpreter, preserving the same
package/extras and installer arguments while avoiding the cached launcher boundary. The actual corrected
container lane must prove interpreter/module startup and the full extracted-ZIP chain; no local installation,
new Python version, test alteration or additional timeout is introduced. The failed provisioning receipt stays
retained alongside the earlier checkout-ownership and apt-cap failures.
