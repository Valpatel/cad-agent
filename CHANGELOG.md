# Changelog

Every release of cad-agent: what projects using it gain and what they must change. Each PR adds its lines as a
fragment in [`docs/changelog.d/`](docs/changelog.d/README.md). Releasing is part of the development loop
([CONTRIBUTING.md](.github/CONTRIBUTING.md#releases)): `tools/cut_release.py` folds the fragments into `## Unreleased` and
dates that entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check requires. Merging the release PR
(`dev` → `main`) tags the release, and Cloudflare Pages builds and deploys the site from `main` by itself. Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## Unreleased

## v0.34.3 (2026-11-11)

**New**
- Read a bounded Smooth-On mold-making source batch and add cited planning prompts for mix basis, material estimates and printed-master compatibility, with product-specific limits and remaining reading tracked in #552.

**Changed**
- Reference publication guidance now distinguishes public source membership from the internal registry and derives release checks from committed IDs (#323).
- Printed snap and hinge reviews now distinguish initial fit, dwell and repeated operation, with explicit material conditioning and support geometry. Two Fictiv guides are marked read and the original BASF manual is recovered with bounded coverage; vendor allowables and cycle claims are not manufacturing guarantees (#551).

## v0.34.2 (2026-11-11)

**Changed**
- Linkage and rendered-motion reviews now include source-backed questions about wheel-leg balance, contact states, sensor bases, motor signs and the causes of joint limits. The Ascento paper and selected Upkie model documentation are marked read with explicit remaining coverage; this adds no dynamics or passive-stability certification (#545).
- Dossier and design-process reviews now prompt separate-part justification, handling/insertion review and explicit tolerance assumptions, based on bounded readings of Nicholas P. Dewhurst and Fritz Scholz. The general DFA worksheet and statistical stack-up helper remain deferred (#547).

## v0.34.1 (2026-11-11)

**Fixed**
- `cad-agent check`, `report` and `all`: a part in `cad.holes.skip` is a `skip` row under "Holes clear", not a
  `pass`: it was not checked, so it no longer adds to the pass count. The report's overall result and
  `exports/hole-checks.json` are unchanged (#526).

## v0.34.0 (2026-11-11)

**New**
- PrusaSlicer slice rows record `supports` (`none`, `enforcers only`, `automatic` or `set in the model`),
  `stability_checked` and `stability_note`. With automatic supports, enforced layers, an override that turns supports
  on, or a 3MF that carries support data of its own (whatever the profile says), the slice is left alone,
  `stability_checked` is false and `cad-agent slice` says the check is not known to have run: `ok` then means only
  that the part sliced (#522).

**Fixed**
- `cad-agent slice` with PrusaSlicer: the print-stability check now runs with Prusa's stock MK4S and XL input-shaper
  profiles. Those set supports "for support enforcers only", and PrusaSlicer then skips the check, so a part with a
  large unsupported overhang sliced as ok with no warning. When the profile supports enforcers only, the 3MF carries
  no support data of its own and `cad.slicer.overrides` does not set `support_material`, the part is sliced with
  `support_material = 0`: the same toolpaths, and PrusaSlicer looks (#522).
- Verification reports show “stability not checked” and the recorded reason on current Prusa slice rows whose stability check did not run. This disclosure does not change optional slicing or turn an unchecked slice into a slicer failure (#522).

**Projects must change**
- PrusaSlicer projects on a stock MK4S or XL input-shaper profile: slice again. A part with unsupported overhangs
  that sliced as ok may now be `NOT OK`, and `cad-agent slice` then exits 1. Fix the geometry, or turn supports on
  in `cad.slicer.overrides` knowing the stability check then does not run (#522).

## v0.33.0 (2026-11-10)

**Changed**
- The maintainer homepage-model collection reuses an exact retained CAD runtime without installation, seals candidate bytes before decode checks, and preserves independent source/runtime/hardware guards (#104).
- The homepage model, matching poster and project card now bind the collected front/rear-pack Gyropup source, with checks rejecting the former belly layout despite its identical battery names. Historical leg illustrations and their source record remain unchanged. Publication requires the accepted product CAD source in protected main; model collection does not establish physical fit or printer readiness (#104).

**Fixed**
- `cad-agent check`, `report` and `all`: a part the slicer did not report as ok (`ok: false` in a current
  `exports/slice-report.json`: a slicer error or a print-stability issue PrusaSlicer names) is now a failing row in a
  new "Slicer" feature (`cad-slicer`), with the slicer's own words. Before, it was footer text only and the report
  still passed. Each sliced part that is ok gets a passing row with its grams and minutes (#520).
- The homepage model maintenance guide now describes the front and rear battery envelopes shown by the collected Gyropup CAD and records their remaining physical qualification limits (#104).

**Projects must change**
- A project that runs `cad-agent slice` and has a flagged part now gets exit 1 from `check`, `report` and `all` until
  the part is fixed and sliced again. Projects that do not slice, or whose slice report is stale, see no change (#520).

## v0.32.0 (2026-11-10)

**New**
- Validate finite ordered assembly-guide paths through the existing insertion engine, with captured guide/mesh hashes and a BREP export binding. Reports retain blocked and undecided pairs and explicitly leave support, retention and physical assembly unverified (#512).
- `cadagent.simulation.robot.settle_stage` simulates explicitly authored rigid assembly stages with MuJoCo, retaining support contacts, maximum drift/rotation, final speeds, penetration and solver warnings. It rejects false stability from disabled gravity/contact, static monitored bodies, implicit constraints and mesh collision hulls; finite modeled stability does not prove physical assembly readiness (#515).
- The existing playback gate offers explicit input/frame-only preflight with a distinct verdict scope, plus optional JSON-safe progress before native load/frame and each pair/operation. Checkpoint failures stop and fail the run while preserving recorded collision/partial evidence; default full path behavior is unchanged (#517).

**Fixed**
- Assembly insertion sweeps retain an explicitly unchecked geometry relation as an unchecked failure, including at the final pose (#512).

## v0.31.0 (2026-11-10)

**New**
- Extend assembly guides with orthogonal CAD section axes and flip, shared hover/selection interaction callbacks, and explicitly ordered per-instance playback over the existing viewer and frame loop. Preserve scalar section behavior and require authored operation order.

**Changed**
- Agent and contributor examples keep the canonical checkout and linked worktrees inside one project container,
  preserving existing owners and dependency paths. The read-only `dev` example now updates its detached HEAD
  explicitly rather than relying on an absent pull upstream (#503).

## v0.30.0 (2026-11-10)

**New**
- Optional `cad.release.assembly_guides` packages hash-bound model, mesh and poster
  inputs with the pinned shared viewer and readable static instructions. Rejected
  guide inputs preserve an existing release; captured inputs and ZIPs are
  reproducible. This does not qualify a product's instructions or physical build (#302).
- Optional hash-bound assembly guides over the existing 3D viewer, with reversible instruction states, selected-part transparency/wireframe, and coherent loading/reset/cleanup. Broader build-package and physical qualification remain separate.

## v0.29.1 (2026-11-08)

**Fixed**
- The page outline keeps the active entry visible when page scrolling stays within the same section after a reader moves its panel. Browser checks observe actual scroll/frame delivery before the same strict visibility assertion.
- Print releases link the complete current native plate project, with per-plate copies and filament identities. Stale or unsupported handoffs are withheld; per-part estimates are not reported as plate slice results. Different extra CAD files cannot overwrite the verified whole-set download.

## v0.29.0 (2026-11-08)

**New**
- `cad-agent bambu-status` reuses an existing private Bambu cloud session to list owned printers or obtain fresh status and correlated firmware for one selected device. The optional `bambu` extra supplies MQTT; no service, camera or physical printer control is added.

## v0.28.2 (2026-11-08)

**Fixed**
- Catalogue cards now carry dated warnings from the committed supply-chain report, including archived repositories
  and activity that needs review. One compact fold retains the evidence and accepted disposition; the catalogue
  JSON and area files carry the same observations. Adoption status is unchanged, and missing warnings do not mean
  a resource is safe. The build rejects a missing, incompatible or mismatched report instead of hiding its findings.

## v0.28.1 (2026-11-08)

**Fixed**
- The agent quickstart points to the relocated native skills and the full installed guide, so a web summary is not its only instruction source (#282).
- Record provider cache plan limits and the distinction between saved configuration, delivered asset policy and browser acceptance in the existing verification guidance.
- Record current-manifest and exact-Markdown preflight guidance for replaying publication checks after repository restructuring.

## v0.28.0 (2026-11-07)

**New**
- Rectangular torsion snaps can declare their demanded twist and lever-force limit through the existing snap-fit CLI, with typed shear checks, sourced material/process evidence, a small-twist limit and the existing project step/check contract. Annular declarations, flexures and physical coupon qualification remain separate.

**Fixed**
- Published HTML protects technical code such as package-version identifiers from provider email obfuscation, with compiled-page contract checks; ordinary deployed readbacks remain required to verify the provider honors the guard (#113).

## v0.27.4 (2026-11-07)

**Changed**
- Add short visual README maps to the remaining owned skill, role, image and recorded-data folders. Each points to its actual instructions, pictures or evidence; generated data keeps its recorded layout (#113).
- Publish owned folder maps behind the repository map, with their own HTML/Markdown pages and parent navigation. These detail pages stay out of the main catalogue, homepage and agent index (#113).

**Fixed**
- Agent installation and inventory reserve `README.md` as the role folder's human map, while malformed role prompts still fail and skill maps remain available in copy-mode installs (#113).
- Derive weekly link-check inputs from actual published sources, and publish their embedded example images and preserve image URLs in Markdown twins of deep folder pages (#113).
- Split wide folder diagrams into readable flows, fold optional reference detail, retain natural-size labels with accessible phone scrolling, and verify actual keyboard and no-script browsing (#113).
- Record the exact native CSP and capture-phase script-resource evidence used by publication checks, retaining failed runs, strict single-event controls and the finite composite limits (#450).

## v0.27.3 (2026-11-07)

**Fixed**
- Correct the dependency policy to describe the range-based Python installs used by CI and the normal installer; source and installer checksums do not imply hash-locked runtime dependencies (#154).
- Copy buttons defer font-ready measurement to the next frame, avoiding geometry writes during resize delivery. Browser checks now observe window ErrorEvents as well as Playwright errors and exercise the font-ready scheduling boundary (#450).
- Full CI reports active test IDs and dumps threads for a slow test, preserving its complete test selection and 30-minute job cap (#463).

## v0.27.2 (2026-11-07)

**Fixed**
- The homepage Gyropup model, poster and project card are regenerated from the accepted current CAD, retaining the tracked inputs, pinned runtime and immutable source link (#104).
- Observe the asynchronous copy-layout probe through bounded plain-state snapshots, preserving task errors and cleanup without returning a pending serialization promise through the browser protocol.
- Direct ordinary reviewer updates through the comment commands, preserving issue and pull-request descriptions after an observed wrong-resource write.

## v0.27.1 (2026-11-07)

**Fixed**
- Replace the stale unverified dependency-graph note with the actual saved setting and discovered manifest/SBOM evidence, preserving the limits on dependency and alert coverage.
- Fresh-agent evaluation reads current canonical skill and role names, so preloaded toolkit instructions cannot pass as a clean session.
- Add explicit Windows installer/receipt and copy-mode evidence consumers; distinguish actual copy resources from an unproved OS-denied automatic fallback and retain ordinary fast guard scope.
- Add an explicitly scoped normal-login evaluation route with a fresh project/tool home; retain unknown freshness and disabled native discovery instead of claiming clean-user parity.
- The agent indexes now direct installers to the existing pinned, checksum-checked guide; an unchecked shortcut no longer precedes that guide in `llms.txt` or the homepage Markdown (#322).
- Independent review guidance now prohibits executing extracted operational assignments and requires preserving unexpected mutations for a fresh review before continuing.
- Keep the asynchronous browser copy-layout probe alive until its result is consumed; require completion and retain action/cleanup errors without weakening layout checks.

## v0.27.0 (2026-11-07)

**New**
- Check repository folder owners, file tables and local Markdown destinations, and publish a generated ownership map.

**Fixed**
- Copy-button layout updates coalesce outside ResizeObserver delivery, preventing the observer-loop error reproduced by the existing late-stylesheet consumer. Copy and navigation-resize checks now retain unfiltered runtime errors alongside their geometry checks (#450).

## v0.26.1 (2026-11-07)

**Fixed**
- Existing linkage and insert checks now resolve their six missing source records to named original proceedings
  and manufacturer documents. The citation warning allowance falls from six records to zero, while a planted
  unverified-source control retains warning and citation-label coverage. Each source records its actual read
  scope; the PEM catalog retains its cached-text and unavailable-download limits (#118).
- Align the vision and taxonomy commentary with the existing area catalogue views and small JSON indexes,
  rather than promising a duplicate hub tree. Record an actual snap-fit discovery path and require every
  tool's guide to remain directly advertised in `llms.txt`; confidence and evaluation work stay separate (#141).
- Preserve operational lessons from actual release integration: enumerate current check instances and prove
  inherited renderer bytes unchanged instead of normalizing them during an unrelated merge.
- Keep the discovery diagram within the narrow desktop column. Defer navigation fold resizing to the next
  frame so WebKit reads the current responsive style and closes a fold opened for the wider window.
- Installation entrances now lead to a single immutable, SHA-256-checked procedure for macOS/Linux and Windows;
  failed downloads or mismatched bytes stop before execution. The quickstart evaluator uses that real procedure (#322).
- Repair canonical reference links while preserving cited editions and earlier reading evidence. Old research options
  stay visible with dated retention/decline decisions; licence exceptions and shipped-parser age decisions bind to
  the actual archived inputs rather than every future package with the same name (#322).
- Keep the supply-chain report's explicit npm/pip version-update policy consistent with the repository's reviewed
  maintenance decision, while retaining the limits of weekly auditing and unverified dependency discovery (#322).

## v0.26.0 (2026-11-07)

**New**
- HP MJF powder-removal rule cards from the openly available original cleaning chapter, with its distinct drain and lattice-opening scopes; refresh source-access evidence and withdrawn-standard metadata (#163).

**Fixed**
- The workflow kit connects an existing project goal graph to issue work and published evidence. Optional
  `project.goals` metadata leaves CAD builds unchanged; resume reports goal coverage without writing to the
  graph, and unavailable access leaves an explicit pending handoff (#103).
- Correct the research map's canonical skill path and document the current hierarchy boundary and six explicit lesson-topic aliases. Preserve established source names and public routes; future grouping follows the existing growth rule (#145).
- The thermal research guide and generated figure use reread official PLA/PETG Basic V3.0 data and preserve
  each sheet's edition in the figure. Older PETG formulation and test-conditioning limits remain explicit;
  mechanical allowables, FEA values and physical coupon status are unchanged (#157).
- Preserve the compact hierarchy when the original Reference Map is imported again: translate recorded repository paths without rewriting external URLs, historical observations or unposted drafts (#163).
- Remove an unsupported EOS gap/diameter limit after reading the source images; keep unverified-rule rejection covered by planted data instead of an incorrect production row (#163).
- Audit the separate maintainer-only Mermaid security build context with the same source, integrity, advisory, install-script and PR-row checks as the site dependency context. Production site installation remains separate.
- Rebuild the existing Mermaid11 core with fixed DOMPurify3.4.17 and non-deprecated KaTeX0.18.10, with reproducible inputs, original upstream hash and full emitted dependency notices. Preserve the strict browser API and verify real math labels in both browser engines; no Mermaid12/ELK migration is introduced.
- Record publication-probe runtime, artifact-namespace and enforced-CSP diagnostic lessons, including retained failure scopes and limits. No provider setting or CSP policy is changed.

## v0.25.2 (2026-11-07)

**Fixed**
- The repository supply-chain audit checks secret-scanning push protection separately from scanning, distinguishes
  disabled settings from unavailable values, and reports empty or unavailable dependency inventories without
  inventing their cause or alert coverage. Projects need no changes.
- FEA installs select Intel PARDISO only on x86-64 Linux and Windows; macOS and other architectures keep the
  existing SciPy/pyamg fallback. The updater evaluates platform markers when retaining installed extras, using
  the standard `packaging` parser. Linux ARM still needs the documented external Gmsh setup; a metadata fix does
  not create a missing upstream wheel. Projects need no source changes; reinstall to use the corrected metadata.

## v0.25.1 (2026-11-07)

**Changed**
- Refresh the homepage Gyropup model from current source CAD, with pinned runtime, source membership and artifact provenance; preserve historical engineering illustrations separately.
- The README uses the animated Made with cad-agent badge beneath its cinematic header, with an explicit reduced-motion still and reusable examples linked near the bottom.

## v0.25.0 (2026-11-07)

**New**
- `cad-agent prusa-view MODEL`: opens a 3MF or STL in PrusaSlicer's window with a private copy of the profile folder,
  so your own PrusaSlicer configuration is never read or written. Start-up has no dialogs (system info, updates,
  hints, the flatpak's certificate store), the window is large and the model is sliced as it loads, with the
  `cad.slicer` presets or `--config INI`. `--screenshot PNG` saves the window (X11/XWayland, ImageMagick `import`);
  `--close` or a later `--stop` stops only that view's own process, by PID, never other PrusaSlicer windows.
  `--view-bed WxD` shows a model larger than the printer on a viewing bed with no wipe tower, for looking at only
  (#252).
- Maintainer intake preserves the contributor's command and GUI evidence, folds its long reference, and binds
  shutdown to actual Prusa argv/start time with Linux pidfds instead of command-text substring matches (#252).
- Reject a work folder containing the model/config before cleanup, and honor requested shutdown after screenshot
  errors while retaining the original failure and separate cleanup diagnostics (#252).

**Changed**
- Added numbered fit-coupon specimens with shared CAD/SVG engraving, persistent UUID/short-stamp source identities, immutable artifact/native-plate read-back and separate attempt/feedback records; printer transport and physical qualification remain separate.
- Projects can share a compact, animated “Made with cad-agent” vector badge based on Valpatel's crystal/V emblem. The README links to copyable Markdown and website examples, downloadable artwork and a complete reduced-motion still.
- The compiled README keeps its CAD figure and sharing badge in their authored sections, without additional automatic picture cards above the introduction.

## v0.24.1 (2026-11-07)

**Changed**
- Manufacturing research records actual Bambu cloud login, fresh P1S/X1E telemetry and a decoded P1S frame, with a reusable investigation method, inspected agent skills and the unresolved X1E preparation failure (#405). This documents evidence; it does not add a printer-control command.
- The manufacturing package map defines where future device integrations and job execution belong alongside existing process rules, artifact preparation and evidence, without adding empty packages or changing public imports (#405).
- Maintainer guidance records how negated issue-closing keywords caused an unintended closure during release preparation, and how to reference incomplete broader work safely (#404).
- The compact README opens with an original animated pixel-art robot factory: builders create new builders beneath an orbital network and a distant robot battle. The script-free SVG has a complete reduced-motion still, preserves the badges and stays separate from the recorded real-CAD illustration.

**Fixed**
- The browser's header check distinguishes hidden theme icons from painted content even when an icon reports a stale rectangle. It retains narrow-screen geometry and screenshots, and still rejects a genuinely visible icon outside the viewport.

## v0.24.0 (2026-11-07)

**New**
- `export-3mf --require-project-settings` rejects missing or incomplete native Bambu project settings before updating exports, preserving prior files on settings/layout rejection (#84).

**Changed**
- The root README answers what cad-agent is, why its learning loop is useful and how to join in; installation detail and evidence stay one click away, with the pixel header and visibly dated real CAD example preserved (#139).

**Fixed**
- A failed Bambu settings-export command can no longer supply accepted project settings through a freshly written ZIP (#84).

## v0.23.1 (2026-11-06)

**Changed**
- The existing design-process skill routes laser-cut/bent-sheet joints to the sheet-metal-hardware workflow. Its canonical Python example now runs through the existing hardware consumer, including WARN/FAIL, unpriced costs and real bad-input/no-op controls (#283).
- Lead the README and guide index with a compact conceptual learning workshop; retain the original Gyropup artwork and actual producer credit together as a real example, and keep technical file wiring in a named disclosure (#396).

**Fixed**
- The cube slicer smoke test uses an independent Snap-readable workspace, cleans it after failures and rejects nonzero slicer exits (#84).

## v0.23.0 (2026-11-06)

**Changed**
- Eight repository diagram generators now live under `tools/figures/`, reducing the directly counted tools files from 28 to 20 and retiring that folder's clutter exception. Their published image paths and calculated results are preserved (#113).
- The existing verification lesson records commit and control-input preconditions for long validation recipes, distinguishing setup failures from actual consumer rejections.
- The canonical agent-kit assets live under `.agents/skills/` and `.agents/agents/`, with a native manifest retaining the repository as plugin root. The Python package and pinned third-party source share `software/`; release fragments live under `docs/changelog.d/`. The root shrinks from 17 entries to 14. Current published identities and installed destinations remain stable (#145, #111).
- The design-process skill routes insert and printed-clamp joints to the existing checked declaration, CLI report and coupon plan, preserving the distinction between a passing warning and a failed joint (#230).

**Fixed**
- Upgrades recognize their owned old instruction links inside live custom-named checkouts, including paths with spaces; unrelated user links remain protected (#145).
- The existing insert-guide consumer checks the actual YAML through the CLI and fresh JSON, so a bad declaration cannot hide behind separately reconstructed prose values. Numeric and source checks remain (#230).
- Stable website vendor assets explicitly require revalidation even if a downstream policy raises their freshness lifetime. Already cached responses still require separate public verification (#381).

**Projects must change**
- Maintainers invoking these repository figure generators must use `tools/figures/<name>.py`; the old top-level script paths are removed. Seven retain `--check`; `snapfit_figures.py` remains regeneration-only (#113).
- Maintainer references to the kit's source assets use `.agents/skills/` and `.agents/agents/`; the old root directories are moved. Source imports use `software/cadagent/`, third-party tooling uses `software/vendor/`, and new release fragments use `docs/changelog.d/`; installed Python modules and CLI names stay the same. Follow the existing installer to repair its owned links; other authors' files remain protected (#145).
- Use `cad-agent update` to reinstall and relink across this move. After a manual pull, reinstall the affected editable environment and rerun `cad-agent agents install`; the old source paths are no longer import or link targets (#145).

## v0.22.2 (2026-11-06)

**Fixed**
- The vision describes the implemented layout checks and their named clutter exceptions, and requires timestamped deployment or readback evidence when measuring publication latency; the reproducible build timestamp alone is the commit time (#145).
- The local quickstart evaluator follows the installer into `tools/site/assets/`; its existing command check now exercises the actual local dispatch and rejects the removed root path (#378).
- Stable vendored website asset URLs now require revalidation between releases; the existing emitted-header check covers every vendor asset and preserves the source/checksum mismatch lesson.
- The design-process skill now routes snap-fit lids and covers to the existing sourced calculator, its declaration example and model limits. The guide example is checked through the actual CLI/JSON interface with orientation faults; the research survey now distinguishes the implemented snap subset from the remaining compliant-mechanism work (#94).

## v0.22.1 (2026-11-06)

**Changed**
- Reconcile contributor guidance with the verified steady Pages command and record actual production-versus-browserless-fleet evidence in the existing verification lesson.

**Fixed**
- Point the owned font CSS comment at the current style guide and refresh only its declared owned-file checksum, preserving all font and licence bytes. Include the existing bearing formulas, source-worked evidence and model limits in the package map; distinguish generated port-parity fixtures from independent source expectations.
- Migration guidance distinguishes physical source moves from public URL changes, records the published v0.22.0 hierarchy and verified nested site build command, and keeps remaining incremental taxonomy work explicit (#145).
- Validate whole literal skill CLI references in inline, fenced and indented shell examples, including chained commands and actor assignments, while preserving quoted data, comments and options. Keep the historical review-section announcement exception only while that command is absent; it is implemented today.
- Keep the documented research/ branch prefix aligned with the existing gate; the docs/research/ folder move does not rename branch types.
- Diagram browser checks retain route, viewport, theme and pending-resource evidence when navigation fails, and release their owned contexts without disrupting another test lane. Real held-resource controls verify the diagnostics and cleanup; normal navigation limits are unchanged (#371).

## v0.22.0 (2026-11-06)

**Changed**
- Group mechanical and practice guides by domain, and move research, lessons and examples under `docs/`. Public documentation URLs and catalogue IDs remain stable; runtime source readers and installed-starter inputs follow their actual files. Retire the numbered lesson stubs after their announced v0.6.0 window while keeping permanent redirects.
- Validate a real wheel starter installation outside its removed build source in full CI, including a missing-installed-data control.
- Correct physical-path labels in the repository maps and extend the existing CI lesson with measured provisioning, exact-attempt log attribution and current-source receipt limits.
- Co-locate website entry scripts, compiler helpers, figure producers, assets and npm/Wrangler configuration under tools/site; retain explicit SDK module scope when the root npm package moves.

**Fixed**
- Website navigation keeps the wordmark, Catalogue, GitHub and theme control separated at narrow phone and tablet widths. The browser guard now checks visible text around responsive breakpoints, including cases with no page overflow (#104).

**Projects must change**
- Repository scripts or explicit overrides pointing to the toolkit's former `research/`, `lessons/` or `examples/` files must use their new `docs/` locations. Explicit independent profile copies keep their existing API behavior.
- Developer npm commands use npm --prefix tools/site; repository-relative site script and asset paths follow their new owners. Public page, asset and installer addresses retain their existing contract.

## v0.21.0 (2026-11-06)

**New**
- `cad-agent rules <feature> [--process P --material M] [--json] [--why RULE]`: a rule card. It gives a feature's cited rules in about 2 KB, one line each, with the numbers, when each applies and when not (and what to use then), whether it is non-negotiable or a guideline with wiggle room, what tightening it costs, the confidence from the source's evidence, the function that enforces it, and `[ref:<id>]`. The cards are generated from `research/process-profiles.yaml` and the reference registry; `insert-hole`, `printed-hole`, `insert-boss`, `insert-install` and `snap-clip` gather rules across features (#323).
- `cad-agent choose joining --load N [--cycles N --qty N --material M --process P] [--json]`: the first decision card. It chooses between a heat-set insert, a glued insert (resin), a thread-forming screw, a through-bolt and nut, a PEM and a snap or clip from a cited decision table, sizes the insert with `cadagent.mechanical.inserts.capacity`, names the runner-up and when it would win, and says where no source covers a branch and which linked cards hold no rule for the process. `--load` is required. With a load and no capacity model (an FDM part with no `--material`, or another process) it answers "not decided" and names what is missing, rather than choose unchecked (#323).
- `cadagent.manufacturing.cards`: the cards, the decision-table format later decisions reuse, and the validation that `python -m cadagent.review.references --check` and the profile tests run (#323).

**Changed**
- Check the rendered reduced-motion hero still and reject a hidden-drawing control, rather than relying only on media-rule presence or zero animation counts. Document the page-emulation limit for external SVG images; generated geometry and animation remain unchanged.
- Add a dated recovery audit and entry maps for the repository’s sources, methods and evaluation evidence.
- Condense the tracked repository root from 30 to 24 entries: transcript mining moves under tools, the weekly upstream procedure under docs, GitHub policies under .github, and upstream metadata under vendor.
- `research/process-profiles.yaml`: rules may carry `when`, `not_when`, `instead`, `strictness`, `wiggle`, `cost`, `materials` and `cards`, filled from their sources for the insert and thread rules, and `unstated` where no source says. New rule `fdm-insert-infill-min-spirol` (at least 50 % infill round an insert, SPIROL) (#323).
- Move contribution and security policies into .github/, preserving GitHub discovery and the public contribution page/Markdown URLs and catalogue identity.
- Correct the contributor gate table to match the independently reviewed 2026-11-05 main-branch protection settings (#112).
- Check actual site publication selection and moved/missing/stale source handling, including whitespace-containing tracked filenames.
- Group the tracked-upstream registry and third-party notices under `vendor/`, preserving published notice addresses and dependency identities across historical comparisons. Audit controls still reject unexpected files alongside repository metadata.

**Fixed**
- The existing branch-flow merge gate rejects changes to dated CHANGELOG entries already published on `main`,
  including edits, deletions, reordered entries and inserted historical sections. It reads candidate files only as
  data at fixed commits and fails closed when history cannot be read. New changes remain in `changelog.d/`.
- GitHub now requires both browser checks and all three release gates on `main`, with an up-to-date branch, matching
  the documented release process; the other protection settings remain unchanged.
- The shallow-crossing regression accepts either a measured CAD-kernel crossing or a contact-probe finding, without assuming a particular OCCT build misses it. A planted boolean miss independently exercises the real fallback probe.
- Website copy buttons switch foreground and background together when the page theme changes, keeping labels readable through the change. The browser contrast check also samples transition frames.
- Decision cards reject NaN and infinite loads, cycle counts and quantities before choosing a joint. The CLI reports invalid loads as input errors instead of emitting nonstandard JSON.

**Projects must change**
- Repo maintainers run `python tools/mining/extract_session.py` instead of `python mining/extract_session.py`.
- Repository maintainers use .github/CONTRIBUTING.md and .github/SECURITY.md; public website addresses remain unchanged.
- Repository maintainers use vendor/upstreams/registry.yaml instead of upstreams/registry.yaml, and vendor/THIRD_PARTY_NOTICES.md for the notice source; the public notice address remains unchanged.

## v0.20.0 (2026-11-05)

**New**
- `cadagent.mechanical.inserts.printed_hole`: the insert's hole for the filament and the nozzle (#323). It takes
  SPIROL's larger hole for filled plastics, a coupon's undersize (which governs; CNC Kitchen's published 0.1 to
  0.25 mm otherwise), the RepRap arc balance as a floor for the line width, and the mesh's facets. `hole_design` and
  `check_joint` take `line_mm`, `filler_pct`, `undersize_mm` and `facets`. A fibre-filled filament adds a `printed hole`
  row, and `line_mm` adds a `boss perimeters` row.
- `cadagent.formulas`: `facet_diameter`, `polyhole` (Nophead), `arc_path_radius` and `arc_printed_diameter` (RepRap
  wiki), with golden vectors from the sources' own numbers.
- The first reference promotion sweep (#323 phase 7), on threaded inserts. It read 41 insert guides at the source:
  22 snippet-only records were promoted to read or above, and 4 read records went up to verified-at-source or encoded.
  Two new sources were added (Nophead's *Polyholes*, the RepRap wiki's *Arc Compensation*). The sweep's checklist is
  in `research/references/README.md`.
- `research/process-profiles.yaml`: four rules, the filled-plastic hole (SPIROL), the 2019 undersize (CNC Kitchen) and
  the perimeters round an insert (LulzBot, PADT), each with the source that governs where they differ.
- `python3 tools/resource_audit.py references`: the reference registry's link health, with no AI. It sends conditional requests (ETag, Last-Modified), hashes each page's normalised visible text, finds soft-404s by rule, reads GitHub repository metadata (gone, renamed, archived, last push, licence, default-branch head), sends at most one request a second to any host, leaves a host that answers 401 or 403 alone for 30 days, and rotates through the records (400 a run, the longest unchecked first) (#323).
- The weekly supply-chain workflow runs it on `dev`, with lychee for every link in the published Markdown (anchors and files included). It keeps one issue, "Reference health: open findings", and opens one bot PR into `dev` with the evidence changes its rules allow (`tools/references_health_apply.py`) (#323).
- Link health stays out of git (#323, Q5). It lives in the workflow's `references-health` artifact. A site build given that file (`CAD_AGENT_REFERENCES_HEALTH`) adds each record's `health` to `catalog/references/*.json` (#323).

**Changed**
- `tools/import_refmap.py` reconciles instead of overwriting. A re-import keeps every record someone has read,
  verified or lowered, and every record the map does not make, byte for byte. It still applies the map's changes
  to the rest, so `--check` passes after a promotion sweep.
- `research/process-profiles.yaml` rules may name what applies them (`applied_by`, checked by the tests), and
  expressions may use `sqrt()` and `cos()`. The insert hole's arc floor, facets and SPIROL perimeter rules are
  profile lines that `printed_hole` and `perimeter_counts` evaluate.
- `check_joint` on a fibre-filled filament (PETG-CF, PA6-CF20) now warns until you give `filler_pct` or print the
  hole coupon, because neither data sheet states the fibre content. Its hole band widens by SPIROL's 0 to 0.15 mm.
- Registry records may carry `evidence.lowered` (`from`, `date`, `why`). The weekly bot PR writes it when a record's link stays dead for two checks and its evidence class falls one rung. `--check` validates it (#323).
- The README hero holds its finished frame (wordmark and every check) for about 4 s before it fades and the loop
  restarts, up from 1.4 s; its cycle is 13.2 s (#339).
- `cadagent.publish.anim.svg.problems` refuses an animation that plays once and stops: every animated figure must
  loop, so a reader who scrolls to it late still sees it play (`svg.timed` lists the ones that do not) (#339).

## v0.19.0 (2026-11-04)

**New**
- The site shows the reference knowledge base (#323):
  - `/references` charts every area's records;
  - `/references/<area>` charts its records by evidence, confidence, kind, licence and process, has a table you can
    filter, search and link to, and lists what cad-agent checked for those topics (each drafted issue never posted).
  - Agents read `catalog/references/index.json`, then one `catalog/references/<area>.json`, and every page has a
    Markdown twin. llms.txt has one line per area; records are not catalogue entries and are not in llms-full.txt.
- `[ref:<id>]` in any page now links to the record's row and to the source (#118).
- `docs/experts.md`: the publishers and named authors behind the read sources, what each contributed and the files
  that cite them, generated by `node tools/site-references.mjs --experts` (#118).

## v0.18.2 (2026-11-03)

**Changed**
- Website (cad-agent.valpatel.com): a new dark theme in valpatel.com's mission-control style. It has a near-black page with a faint hairline grid, cyan hairlines and corner brackets on panels, mono status labels and a glowing status dot, with cad-agent's orange as the second accent. The green "What the code computes." band is now a dark panel (#330).
- Website: a new friendly light theme. It has a warm-white page, sunny yellow, sky blue, coral and mint, rounder corners and soft shadows, and a highlighter stroke under the headline accent. Both themes are token swaps in `web/site.css` and `web/catalog.css`, and the layouts are unchanged (#330).
- Website diagrams are drawn in each theme's palette (`PALETTES` in `tools/site-diagrams.mjs`) (#330).

**Fixed**
- The home page's 3D Gyropup, its poster and its projects card show the current robot (two five-bar legs, the P3
  body, the turret), not the retired serial leg. The card is now made by `tools/site-model-poster.mjs` and recorded
  in `docs/img/gyropup/SOURCE.json` (#331).
- `cadagent.publish.view.export_view`: a part's `bounds_mm` is the solid's box, measured before meshing, not the box
  enlarged by the mesh's deflection (up to 1.4 mm at 0.8 mm tolerance) (#331).

## v0.18.1 (2026-11-03)

**Changed**
- The README hero (`docs/img/hero/gyropup-leg.svg`) is transparent on GitHub's page instead of a panel (cream in the light scheme, dark green in the dark one). Its words get a halo in the page colour (`anim.svg.HALO`: white or `#0d1117`), so they stand out whichever colour scheme the SVG picks. `anim.svg.document(background=False)` makes any figure transparent; the FEA and snap-fit figures keep their panels.

**Fixed**
- The v0.18.0 entry's M3 clamp figure (2.12 → 0.25 N·m without `head_mm`) is for PLA Basic; the same joint in PETG Basic gets 0.21 N·m. `thread:` clamp results (`check_clamp`) also gain the `fixes` and `head` keys (#292).

## v0.18.0 (2026-11-03)

**New**
- `cadagent.library.hardware`: ISO 7089, ISO 7090 and ISO 7093-1 washers (from bd_warehouse, with their largest hole, least outside and thinnest thickness from the standards' tolerances), and the heads' bearing faces for ISO 4762, ISO 7380-1, ISO 14580 and ISO 1207, M2 to M6 (#292).
- `formulas.bearing_area` (the face under a head or washer, its hole widened by a chamfer) and `formulas.washer_bearing` (how far a steel washer spreads a clamp on printed plastic: a beam on an elastic bed, cut where it lifts off or bends too far) (#292).
- `inserts.check_joint` and `check_clamp` take `head` (socket, button or cheese), `head_washer`, `chamfer_mm` and, into an insert, `insert_washer` and `under_chamfer_mm`. When the printed part's bearing sets the torque, the result's `fixes` lists, in order, a larger head, a washer, a large washer and a limiter, each with the torque and preload it allows. `cad-agent inserts` prints a `fix:` line for each one named. The issue's M3 lid in PLA (0.20 N·m) gets ISO 7089 washers between the lid and the insert and under the head: 0.30 N·m and 775 N of preload, against 329 N (#292).
- `docs/inserts.md` draws the issue's lid with its washers and the pressure under them, and the fix ladder's options as bars, both from the module (`tools/insert_figures.py`) (#292).
- The reference registry now holds the Reference Map: 546 new records in 16 shards
  (`research/references/projects-<domain>.yaml`, `guides-<group>.yaml`), and 21 additions to guides already read in
  `research/references.yaml` (#323). Every new record is catalogued (`snippet-only`): listed and linked, never cited
  by a rule, check or page until someone reads it at source. Licences are as the map states them, unread;
  share-alike, non-commercial and unclear geometry is study-only. Numbers are the authors' claims unless measured.
- `research/references/coverage.yaml`: the map's snapshot of what cad-agent enforced per topic on 2026-11-02 (16 rows), its gaps, and the issue drafted
  for each gap, never posted; plus the sources each process group still lacks (#323).
- `tools/import_refmap.py <data.json>`: the deterministic, idempotent import (`--check` exits 1 when it would change
  a file). The map's data stays out of the repo (#323).
- `cadagent.review.references` reads the reference registry's schema-2 shards, `research/references/*.yaml`, beside
  `research/references.yaml`, as one id space. A schema-2 record says what it is, what its source's licence allows
  (geometry under share-alike, non-commercial or unclear licences is study-only), how far it has been checked (the
  evidence ladder from `snippet-only` to `measured`) and, for an open project, an objective assessment. Its
  vocabularies are data in `research/references/vocab.yaml` (#323).
- `check()` (and `python -m cadagent.review.references --check`) validates shards: vocabularies, `docs/areas.yaml`
  slugs, at most 150 records or 150 KB per shard, the ladder's rules, and that a stored `confidence` equals the one
  `confidence()` derives from the evidence (#143, #323).
- A rule, a check, a code table or a page may not cite a catalogued (`snippet-only`) record; a `[ref:<id>]` to one in
  `research/` is a warning (#323).

**Changed**
- `--check` reads YAML through libyaml when PyYAML has it: about half the time (1.4 s instead of about 3 s on the registry as released) (#323).
- The home page explains itself to a newcomer. Under "Your one stop shop for agentic CAD", it now says "AI helping AI build
  anything you want", then what cad-agent is in plain words: a free toolkit an AI assistant installs in one line, which
  helps it design real things, check them for problems before anything is made, and, with your OK, share what it learns
  as a pull request. It replaces "Checks, simulation and cited engineering for the hardware agents design, in tested
  code."
- The README opens like the home page: "Your one stop shop for agentic CAD", then "Self-improving AI for designing
  physical objects, built with the best open source projects", then one plain sentence on what it does. It replaces "A
  workshop where AI agents get better at CAD by learning from everyone else."

**Fixed**
- `docs/inserts.md` no longer says a limiter spreads a printed lid's load on an M3 insert's ring: the catalogue M3 limiters lower the torque and fail their own seating-force and press-fit rows. A limiter is now named only where every row of its own passes (#292).

**Projects must change**
- Re-run `cad-agent inserts` on M2, M2.5 and M3 joints without `head_mm`. Their head bearing row used to say "not checked". It now checks against the ISO 4762 socket head and can set a much lower torque: an M3 `thread:` clamp joint (`check_clamp`) without `head_mm` drops from 2.12 N·m on v0.17.0 to 0.25 N·m. Pass the real head (`head_mm`, `head`) or add a washer; the result's `fixes` lists what lifts it. Every insert-joint result gains the `fixes`, `head`, `insert_washer` and `clamped_on_washer` keys (the last two null without a washer), and `fixes=True` is a new keyword (#292).

## v0.17.0 (2026-11-02)

**New**
- `cad-agent init [DIR]` starts a project from the starter box: it copies `examples/starter-box` (a 60 x 40 x 25 mm box and lid on four M3 heat-set inserts) into `DIR` and prints the next commands; `cad-agent all` passes on it as copied. It refuses a folder that is not empty unless `--force` is given. A wheel install carries the starter under `<prefix>/share/cad-agent/` (#291).
- `examples/starter-box`: the smallest cad-agent project, to change. Its holes and bosses come from `inserts.hole_design` and `inserts.boss_design` (the 4.20 mm M3 hole), and its `checks:` read `cad-agent inserts --output` and the overhang screen; CI runs `cad-agent all` on a fresh copy (#291).
- `cad-agent inserts --output` and `inserts.check_spec` give a top-level boolean `pass`, true unless a joint fails, so a `cad: checks` row reads the file without a wrapper script (#292).

**Changed**
- The paste-in guide (`docs/agent-prompt.txt`, llms.txt) and the README's quick start now start a project with `cad-agent init` instead of writing `cad-agent.yaml` by hand. A project command run where there is no `cad-agent.yaml` now points at `cad-agent init` (#291).

**Fixed**
- `cad: python` in `cad-agent.yaml` expands `~` and `$HOME` (also `${HOME}`). `~/cad-agent/.venv/bin/python` used to be joined to the project root, so every step failed with "could not start" (#288).
- `cadagent.publish.render.Renderer.render` adds `.png` to a name with no extension, and refuses an extension Pillow cannot write before rendering. A bare name used to render the whole scene, then fail in Pillow (#289).
- `cadagent.manufacturing.fit_coupons`: an `insert` fit's sweep centres on the hole `inserts.hole_design` draws: the maker's hole plus 0.2 mm, 4.2 mm for a 4.0 mm M3 hole. It used to centre on 4.25 mm. CNC Kitchen's sweet spot for its M3 was 4.2 mm in CAD (about 90 % of the highest pull-out), and the 0.2-0.3 mm offset already includes the printed hole's undersize, so the `insert` allowance is now -0.05 mm (#290).

**Projects must change**
- An insert coupon printed before this has its holes 0.05 mm larger than a new one. Pick the hole that fitted by its CAD size, not by its place in the row (#290).

## v0.16.0 (2026-11-02)

**New**
- `research/sheet-hardware.yaml` is a catalogue of the bought parts for bent sheet-metal parts. It lists 26 PEM clinch
  nuts, studs and standoffs and 4 McMaster-Carr blind rivets, each with its dated price, stock count, seller page and
  source. Where SendCutSend presses a part in, it also gives SendCutSend's price for doing so. It uses cad-agent's
  part-catalogue layout (#283).
- `cadagent.mechanical.sheet_hardware` loads that catalogue and refuses any item that is not a part the clinch or
  rivet checks know. `choose_clinch` and `choose_rivet` rank, by price, only the parts the checks already accept.
  `cost` totals the pieces, the whole packs, and a shop's price to press the parts in (#283).
- The `sheet-metal-hardware` skill walks an agent through a bent plate with clinch hardware and rivets, in order:
  bends, holes near bends, clinch placement, riveted seams, then price (#283).
- `docs/sheet-metal-hardware.md` shows the prices in a chart drawn from the catalogue, the common cheap choice, where
  to buy and how to keep the data current (#283).
- The website has a dark theme (#305). It follows the reader's system setting, and a button in the header switches it;
  the choice is kept in that browser only (localStorage) and nothing is sent anywhere. Every page, the catalogue, the
  "copy this to your agent" card, the page tree and the kit's demos follow it. Mermaid diagrams are drawn at build time
  in both themes, so dark pages show dark diagrams without script and without downloading Mermaid.
- `webkit/diagrams.js` (`src/cadagent/webkit/diagrams.js`, published as `kit/diagrams.js`) exports
  `refreshDiagramThemes()`, which redraws diagrams after a page switches theme with its own button, and leaves alone
  figures drawn ahead of time for one theme (`data-theme-only`) (#305).

**Changed**
- `web/site.css` and `web/catalog.css` keep their colours as tokens on `:root`, a light set and a dark one; a
  catalogue domain's tone is now `--tone-ink`, with `--tone` and the tints mixed from it in the dark theme (#305).

**Fixed**
- The `sheet-metal-hardware` skill's worked example now runs all six steps. It adds the blank (`flat_length`), the
  nut's own hole checked near the bend (`feature_to_bend`), the channel base, and the rivet choice (`choose_rivet`)
  for two 1.6 mm sheets with their tolerance. The where-to-buy diagram on `docs/sheet-metal-hardware.md` shows that a
  part the shop has pressed only needs riveting (#283).
- The site's copy buttons read in every state: "Copied" is a darker green under its white text (was 3.45:1), and the
  home page's orange buttons keep white text readable when the clipboard refuses (was 1.24:1) (#305).
- The headers of `install.sh` and `install.ps1` name every folder the installer writes, including the subagents in
  `~/.claude/agents`, and say that it removes the kit's own old links from `~/.codex/skills` (#308 review).

## v0.15.0 (2026-11-02)

**New**
- One-line install: `curl -fsSL https://cad-agent.valpatel.com/install.sh | sh`, or on Windows
  `irm https://cad-agent.valpatel.com/install.ps1 | iex`. It needs git, installs uv if it is missing, clones `main`
  into `~/cad-agent`, installs the `cad-agent` command with `uv tool install --editable` (Python 3.12, in
  `~/.local/bin`) and adds the skills. Options: `--extras fea,sim`, `--ref vX.Y.Z`, `--dir`, `--uninstall`. Running
  it again updates (#282).
- `cad-agent update`: fast-forwards `main` (or moves to `--ref <tag>`), reinstalls only when `pyproject.toml` or
  `uv.lock` changed or `--extras` adds some, relinks the skills, prints the CHANGELOG since the old commit with
  "Projects must change" first, and in a project folder says what to re-run. It refuses a checkout with changes or
  on another branch. Its only network use is that git fetch (#282).
- `cad: {cad-agent: "0.14"}` in `cad-agent.yaml`: the oldest cad-agent a project builds with; `cad-agent all` refuses
  an older one, and notes when the checkout's last commit is more than 14 days old. `cad-agent-results.json` records
  the version that built it as `cad_agent` (#282).
- `cad-agent agents uninstall` removes every skill and subagent it placed (#282).
- `cadagent.mechanical.clinch` checks where a self-clinching (PEM-type) nut, stud or standoff may go in a sheet:
  - the sheet's hardness against the part's material, with no listed part allowed in stainless sheet;
  - the thickness for its shank;
  - the hole band (+0.08 mm / −0);
  - the edge distance;
  - the distance to a bend (BA/2 + E from the bend centre line, with the bend allowance from `sheet_metal.bend`);
  - the spacing to each neighbour;
  - push-out, torque and pull-through loads against PEM's averages.
  Each check names its `sm-clinch-*` rule or the PEM bulletin it uses. It holds a cited subset of PEM's common S, SS, CLS, CLSS, FH, SO and BSO parts, and `parts_for()` lists the ones that clinch into a given sheet (#283).
- `cadagent.mechanical.rivets` checks a riveted lap joint of sheet parts: the grip band with each sheet's thickness
  tolerance, the hole against the maker's drill range, edge distance (2D full strength, 1.5D floor), pitch (3D, 4D
  for several rows), t/D, the thinnest aluminium under an open-end rivet, the rivet's metal against each sheet, and
  the strength per pitch. Each check names its `sm-rivet-*` rule in `research/process-profiles.yaml`. It lists POP and
  McMaster-Carr blind rivets with hole, grip and rated strength, and `rivets_for()` finds those whose grip covers a
  stack (#283).
- `cadagent.formulas` gains riveted lap-joint equations: `rivet_shear_force`, `bearing_force`, `tearing_force`,
  `solid_sheet_force` and `lap_joint` (strength and efficiency per pitch). They are tested against MIL-HDBK-5J's shear
  and bearing tables and the worked lap joints of Abbud's lecture notes (#283).
- The rivet check takes e/D on the hole, as MIL-HDBK-5J does, with Fbru linear between e/D 1.5 and 2.0. When a
  sheet has no bearing value at the joint's e/D, it says which edge distance would give one. Rows follow the FAA's
  layouts: two rows at 4D with the rows 4D apart, and for three or more rows the outer rows at 6D and the inner rows
  at 3D, with the rows 3D apart (#283).
- `cadagent.manufacturing.sheet_metal.feature_to_bend` checks a hole or cut-out near a bend against every hole-to-bend
  rule on the rule's own datum: the tangent line for Hubs and Davis, and the inside face for Century Tywood (plus
  R tan(A/2), capped at R, so a bend past 90° earns no extra distance). A rule that states no datum is read from the
  tangent and only warns (#283).
- `cadagent.manufacturing.sheet_metal.check_bends` checks a bent part's flanges, relief depth and relief width. A
  value that clears only a shop's own number (its row or its rule), and not the strictest generic rule, warns.
  `rows=False` drops the shop's tooling rows (#283).
- With a shop named, `check_bends` also checks that shop's limits: the bend angles it makes (SendCutSend: 5–130°), no
  hardware on a part with a bend past 90°, the flanges of a four-sided box (with and without hardware), the channel
  base, and the shop's own relief depth (#283).
- `sheet_metal.bend` takes `g90`, `304` and `316` and reads SendCutSend's galvanised and stainless rows for them. Off
  the table, stainless takes the generic hard-metal rules and G90 the medium (steel) ones (#283).

**Changed**
- Skills for Codex, Copilot CLI, Cursor, Gemini CLI and opencode go in `~/.agents/skills`, which they all read;
  `agents install` removes what earlier versions put in `~/.codex/skills`. `--target codex` is now `--target agents`
  (the old name still works). Where links are not allowed, it copies (#282).
- The README and the home page lead with the one-line install and an eight-word line to paste into an agent; the
  install and working rules moved into llms.txt (#282).

**Fixed**
- Five SendCutSend rules were not marked `shop: sendcutsend`, so generic checks read them. They are the K range, the
  relief depth, the relief width, the corner-relief gap and the bend-angle tolerance. Off the shop's table, the
  strictest generic relief depth is now T + R (Davis, Century Tywood), not SendCutSend's T + R + 0.5 mm. The generic
  relief width is T (Hubs, Paulsen), not SendCutSend's T/2 (#283).

**Projects must change**
- Codex users: start a new Codex session after `cad-agent update` (or the installer) so it finds the skills in
  `~/.agents/skills` (#282).
- Sheet DFM reports (`cadagent.manufacturing.dfm.check`) change in two ways. A relief narrower than T now fails where
  it used to warn (for example 0.9 mm on 1.6 mm sheet). Off a shop's table, the relief depth limit is now T + R, not
  T + R + 0.5 mm. `dfm.check` cannot name a shop, so use `sheet_metal.check_bends(..., shop=...)` for the shop's own
  rules (#283).
- In `check_bends`, a flange at exactly the shop's shortest flange now warns on most stocks, because the shop's rows
  are shorter than Century Tywood's 3.5 (T + R). Keep the flange or name the shop's tooling as the reason (#283).
- The five rules above are now shop rules everywhere: `Profile.rules_for()` and `limits()` leave them out unless the
  caller names the shop. Code that reads the K range, relief, corner-relief or bend-angle tolerance directly passes
  `shop="sendcutsend"` to keep them (#283).
- `cad-agent-results.json` gains a `cad_agent` key holding the version that built it, so a project that commits its
  results file or compares the whole dict in a test sees it change with each release (#282).

## v0.14.0 (2026-11-02)

**New**
- `research/references.yaml`, the reference registry: 213 read sources, each with its authors or publisher, year, an
  https link or ISBN, access, terms, the design areas it supports, the repo files that rely on it, and what was read
  and when. It merges the first sweep of #119 with the sources of `research/process-profiles.yaml`, and adds every
  source that `cadagent.formulas` (with the rolling-bearing sources of #180), `cadagent.mechanical.inserts`,
  `cadagent.mechanical.printed_joints` and `cadagent.simulation.fea` cite by key. Sources are cited, never copied:
  paid standards by number and title only, paid papers by author, title and equation, and no PDF of a source is kept
  in the repo (#118).
- `cadagent.review.references`: `lookup("covestro")` and `citation("roark")` resolve an id or a module's own key (an
  alias such as `shigley-torque`) to its entry. `check()` finds every place the code cites by id and reports a key
  that resolves to nothing, a malformed entry, or a citing file missing from the entry's `used_for`. From a shell:
  `python -m cadagent.review.references roark` or `--check` (#118).
- `cad-agent slice` with PrusaSlicer: set `cad.slicer.engine: prusa` (the default stays `bambu`).
  `cadagent.manufacturing.slicer_prusa` runs `prusa-slicer` (on PATH or the flatpak) as a separate process. PrusaSlicer
  itself resolves the named printer, print and filament presets, user presets included, so a multi-tool printer such
  as the XL gets every filament setting once per tool, and it refuses a preset that does not fit the printer. Overrides
  use PrusaSlicer's names; an unknown key such as Bambu's `wall_loops` is an error. Grams and time come from the
  G-code footer, and the slice records the SHA-256 of its config and of every profile file read (#242, by Jeff Patrick).
- A PrusaSlicer slice report records `engine: prusa` and is not current for a Bambu Studio project, or the other way
  round. The release page says which slicer's presets it lists (#242, by Jeff Patrick).
- `cad-agent slice` with PrusaSlicer keeps what PrusaSlicer said about each part: it runs with `--loglevel 3`, saves
  the log next to the G-code (`build/slicer/<part>/out/slicer.log`) and records each part's `warnings`, `errors`,
  `stability_issues` (the categories after "Detected print stability issues", such as `Long bridging extrusions`) and
  `benign_log_lines` (a count of PrusaSlicer's notes that say nothing about the print).
  `cadagent.manufacturing.slicer_prusa.parse_log` reads a log (#246, by Jeff Patrick).
- Per-part slicer settings: `cad.slicer.parts` may be a mapping of part name to `{overrides: {...}}`, applied on top
  of `cad.slicer.overrides` (a brim for a tall part, more perimeters for a pin-loaded link). A report row records its
  `part_overrides` and is stale once they change (#246, by Jeff Patrick).
- `cadagent.manufacturing.prusa3mf`: PrusaSlicer project 3MFs. `write_project` writes objects made of several
  volumes, each on its own tool (`Metadata/Slic3r_PE_model.config` volume ranges), and the wipe tower's place, which
  PrusaSlicer 2.9 reads from the project and not from the print config; `write_plates` packs every part at its
  quantity with the build-plates layout, grouped by tools or filament, one 3MF per plate, keeping parts clear of the
  tower. Each file is read back (triangles, watertightness, volume, tool and place of every volume) and is
  byte-reproducible; checked by slicing with PrusaSlicer 2.9.4 (#248, by Jeff Patrick).
- `cadagent.mechanical.clearance`: a range-of-motion collision check. `collisions(instances)` relates every pair of
  placed solids whose bounding boxes meet with the relation gate's exact narrow phase (`relate`) and reports pairs
  overlapping by more than `tolerance_mm3` (2 mm³ by default), with `skip` for intended overlaps and `only` to limit
  the check; a pair the gate cannot decide is an error, never a pass. `sweep(poses, place_fn)` runs it at every named
  pose and writes a check JSON with a top-level `pass` and `physical_fit_verified: false`; with `travel_mm` it also
  proves each pair clear between consecutive poses by the gap bound `(g1 + g2 - travel) / 2`, or fails the step.
  `swept_envelope(pieces)` builds a revolved swept-volume cutter with slopes capped at 45°, as one revolve (no flat
  ceilings, no many-tool fuse). Contributed by Jeff Patrick (docs/toolkit.md, #251).
- "Copy this to your agent": one block, in `docs/agent-prompt.txt`, that a person pastes into Claude Code, Codex, Copilot CLI or any agent with a shell. The agent installs cad-agent and its skills from the public repository, finds the tool through `llms.txt`, builds with the kit's tested checks, and drafts what it learned as a pull request or an issue that the person approves. It is the README's first section, under the animated hero ("Build with your favorite AI agent", which replaces the old Quick start) and in a card on the site's home page, with a copy button; `llms.txt` and `index.md` carry it too. Tests keep all of them identical (#278).
- Provenance on reports: the feedback issue form takes optional Model, Harness, cad-agent commit, Layer (a cad-agent tool or the upstream under it), Building, Sources and Confidence fields, and the PR template has a "Made with" section. With these, the project counts which models, harnesses and layers work from GitHub data alone. cad-agent collects no telemetry (#278).
- `tools/quickstart_eval.py` checks the block for someone with nothing of ours. `install` runs its commands in an empty folder and smoke-tests the result. `agent` gives the block and a small request to a fresh Claude Code or Codex session, in a new home with none of your skills, memory, settings or MCP servers. `grade` scores the run from its transcript and files, and prints tool calls, tokens and checks as one JSON line: a first job for the evaluation runner (#142).
- Usage reporting off: every project step `cad-agent` runs gets `DO_NOT_TRACK=1`, `CADGEN_TELEMETRY=0` and `CADGEN_UPDATE_CHECK=0` (text-to-cad's cadgen), `KICAD_MCP_TELEMETRY_ENABLED=false` (kicad-mcp-pro), `WRANGLER_SEND_METRICS=false` and `WRANGLER_SEND_ERROR_REPORTS=false` (Cloudflare wrangler), unless a variable is already set; the calling shell is left as it was. `npm run deploy:site` sets both wrangler opt-outs too. cad-agent itself sends nothing. The survey behind the list is in `docs/supply-chain.md` ("Usage reporting"), and a test fails when a vendored tool names a switch the list does not cover (#278).
- `cad-agent agents install` and `agents list` say which skills and agents you can't use yet and why (`gh` not logged in; `git`, `ssh` or `rsync` not on PATH; Playwright or Google Chrome missing), which ones work with some steps left out, and what they cannot check from here (write access to the repository, a compute host). The checks run on this computer with no network call. Each skill or agent declares its needs as `metadata: {requires: ..., optional: ...}` in its frontmatter and opens with a `> **Needs:**` line saying the same. Everything is still installed for everyone (#282).
- `cadagent.library`, the parts library (#287). It holds KiCad footprints and CadQuery 3D bodies for real parts, drawn from their datasheets, with the datasheet numbers as golden vectors. It starts with the parts Gyropup's fuse board needed: the Littelfuse MINI FL1 holder (and MINI fuses by rating), the Bourns CSS2H-3920 shunt on a Kelvin layout, M4 and M6 lug studs, an M5 bonding mounting hole and a non-plated slot. cad-agent commits no footprint or STEP files. `cad-agent library build OUT --project DIR` writes `cad-agent.pretty` and `cad-agent.3dshapes` (coloured, reproducible STEP) for a project's `fp-lib-table`.
- `cad-agent library audit board.kicad_pcb` fails on any footprint with no 3D model, or whose model does not resolve, unless a waiver gives the reason it is not a part (`--waive 'TP*=bare test pad'`). `cadagent.library.audit.registration` checks that a body sits on the board, that its pins pass through their pads' holes, and that its terminals lie over the right pads (the pin-1 frame).
- `cadagent.library.hardware`: socket-head and button-head dimensions, tested against the vendored `bd_warehouse` tables. It also has nyloc and ring-lug envelopes (marked unverified) and `register()`, where other families such as clinch hardware (#283) plug in.
- `tests/repo/test_markdown_images.py`: every local image in every Markdown page must be in git with the exact case,
  non-empty, not a Git LFS pointer, and match its extension's magic bytes.
  It ignores fenced and inline code and HTML comments, follows reference-style images, unquoted `src=`, every
  `srcset` entry and percent-encoded paths, and fails an image on a site-rendered page that sits outside `docs/img/`
  (the only image folder the site copies) (#294).
- `research/sheet-metal-guides.md` surveys the design guides for bent sheet metal, self-clinching (PEM-type) hardware
  and blind rivets before any rule is written. It covers SendCutSend, Protolabs, OSH Cut, PEM, Stanley POP, Marson,
  Avdel, GESIPA, FAA AC 43.13-1B, NASA RP-1228 and MIL-HDBK-5J, plus the paid standards cited by number and title. For
  each guide it records authority, coverage, terms and date, picks a primary source per topic, and lists where the
  sources disagree and by how much. It also decides whether to adopt, wrap, borrow or build for each open-source tool.
  The registry gains 52 sources and 11 unread entries, among them the gated guides from Xometry, Fictiv and Protocase
  (#283).
- `research/sheet-metal.md` is a deep dive into SendCutSend (materials, cutting, bending, hardware, taps, countersinks,
  dimples, finishes and pricing) beside the generic bending and cutting rules. The bend-deduction formula reproduces
  SendCutSend's published values within 0.005 in for 53 of its 56 bend stocks (#283).
- `research/sheet-metal-joining.md` covers PEM nuts, studs and standoffs (hardness, hole, edge, bend and spacing rules,
  strengths and prices for the common sizes) and blind rivets (types, strength by maker, grip, hole, edge distance,
  pitch, the joint checks with a worked example, and galvanic pairing). It also lists where SendCutSend's hardware data
  disagrees with PEM's (#283).
- `research/process-profiles.yaml` gains named shop profiles. SendCutSend's limits and tables are rules marked
  `shop: sendcutsend`, which `cadagent.manufacturing.process` loads only when a caller names the shop
  (`rules_for(..., shop="sendcutsend")`, `limits(..., shop=...)`, `Profiles.shop(id)`), so the generic rules stay
  supplier-neutral. New supplier-neutral `sm-clinch-*` and `sm-rivet-*` rules cite PEM, POP, the FAA, NASA, MIL-HDBK-5J
  and GESIPA (#283, #284).
- Four new figures in `docs/img/sheet-metal/`: a bent plate with a clinch nut and rivets laid out by the rules, the
  shop's hardware distances, the hardest sheet for each clinch-fastener material, and rivet edge distance and pitch by
  source (#283).

**Changed**
- `tests/` is grouped by domain: each test sits in `tests/<domain>/`, the folder named after the
  `src/cadagent/<domain>/` package it tests, or in `tests/cli/`, `tests/site/` (the website and its build) or
  `tests/repo/` (the repo's own rules and tooling); design exploration's are in `tests/simulation/explore/`. File
  names are unchanged, and `git log --follow` keeps each file's history. The same tests are collected and pass. Every folder has a README with a map, and `tests/README.md` lists
  them (#113).
- `tests/repo/test_layout.py` checks where files go. It fails on a test file directly in `tests/`, a `tests/` folder
  that is neither a package nor a listed area, a new top-level folder in the repo, a new file at the top of `src/` or
  `src/cadagent/`, and a folder newly over 20 files. Each failure names the folder the file belongs in. The folders
  over 20 files today (`docs/`, `tools/`, `src/cadagent/webkit/`) are on a list that may only shrink (#113).
- `AGENTS.md` has a "Repo structure and where files go" section with the growth rule: split a folder when it gets
  cluttered, not before, with a README and map for each new folder. `CONTRIBUTING.md` has a "Where files go" table.
  The `cad-pr-reviewer` agent and the `cad-pr-review` skill check structure and sprawl, so projects that install the
  kit get the same check against their own map (#113).
- `research/process-profiles.yaml` no longer has its own `sources` and `standards` blocks: its rules cite registry
  ids, and `tools/process_profile_figures.py` reads the credits from the registry. The charts are unchanged (#118,
  #163).
- `cadagent.manufacturing.process` reads its sources from the registry, so the FDM data-sheet ids of its material
  factors (`bambu-petg-basic-tds` and the rest) now resolve to an entry instead of falling back to the sheet's link.
  A data file with no registry beside it still loads, with those ids unresolved (#118, #99).
- `cadagent.mechanical.bearings.SRC` (#180) is now `WHERE`: its keys are the checks (`life`, `load`, ...), not source
  ids, and a module-level `SRC` or `SOURCES` table is where the registry's check looks for ids (#118).
- `tests/simulation/test_fea_materials.py` now checks that every material's `source` is a read entry of the registry. It was
  skipped while the registry was missing (#118).
- A PR into cad-agent that adds a `[ref:<id>]` tag, a `source=` on an FEA material, a key to a module's `SRC` or
  `SOURCES` table, or a sheet to `FDM_MATERIALS` must add that source to `research/references.yaml`, or
  `tests/review/test_references.py` fails (#118).
- The registry records two out-of-date citations, for follow-up. ISO 68-1:1998, which `cadagent.formulas` cites for
  the metric thread profile, was withdrawn on 2023-10-05 and replaced by ISO 68-1:2023. Freudenstein's 1955 paper is
  pp. 853-859; the discussion after it runs to p. 861, which the formulas' citation includes (#118).
- `export-3mf` for a PrusaSlicer project writes plates without Bambu Studio project settings, and says so (#242, by Jeff Patrick).
- A PrusaSlicer slice report gives each part an `ok`: true only with exit code 0, G-code written and no error or print
  stability issue. The report's `pass` needs every part ok, and `cad-agent slice` exits 1 otherwise, so a part that
  slices but PrusaSlicer says will print badly no longer reports as fine. Bambu Studio reports are unchanged (#246, by Jeff Patrick).
- A part PrusaSlicer flagged keeps its grams and time, and says so: its print-release card carries a `slicer: …` pill,
  the release warnings (and `manifest.json`) name it, and the results report's slicer line adds `NOT OK, flagged by
  the slicer` (#270).
- Slicing some parts (`cad-agent slice PART ...`) keeps only the old rows that are still current; `pass` is about the
  rows in the report, so a part left out is reported as not sliced (#270).
- The README's Quick start is folded into "Build with your favorite AI agent". The table of extras moved to its own "Extras" section after "What's in the box" (#278).
- README: the animated hero is back at the top, above the title and the copy-to-your-agent prompt, as on
  text-to-cad's README, with two rows of badges (release, Python, site, last commit, stars, supported agents, CAD
  kernel, no telemetry). A test keeps the hero first (#294).

**Projects must change**
- `cadagent.mechanical.bearings.SRC` is now `WHERE`, with no alias: code that imports `SRC` from it must import
  `WHERE` (#118).
- If a project or CI job runs cad-agent's tests by file path, add the domain folder:
  `tests/test_fea.py` is now `tests/simulation/test_fea.py`, and `tests/webkit-*.test.mjs` is now
  `tests/webkit/webkit-*.test.mjs`. `tests/README.md` lists every folder. Running `pytest tests` or `npm run test:*`
  works as before.
- Code that imports a test module as a helper takes the new module path: `tests.test_report` is now
  `tests.publish.test_report` (#113).
- PrusaSlicer projects: re-run `cad-agent slice`. A part with a stability issue or slicer error now fails it; fix the
  geometry, or set that part's own overrides under `cad.slicer.parts` (#246, by Jeff Patrick).

## v0.13.0 (2026-11-02)

**New**
- `cadagent.mechanical.bearings.check_bearing` and `cad-agent bearings bearings.yaml`: check a rolling bearing's ISO 281 basic rating life (turning or oscillating, under one load or a duty cycle, at any reliability from 90 to 99.95 %), its ISO 76 static safety at running and peak loads against SKF's guideline s0, its axial load, load range, minimum load and speed. A swinging joint, such as a robot's knee, also gets its critical amplitude and a false-brinelling warning. It returns pass, warn or fail rows; the CLI exits 1 on a fail and 2 on a bad file (#180).
- `cadagent.mechanical.bearings.BEARINGS`: SKF's 6201 (open, 2Z, 2RSH), 6301, 6301-2RSH, 61800 to 61806, 61812, 6207-2RSH, NU 202 ECP and NU 311 ECP, and Koyo's 6201, each with C, C0, Pu, speeds, f0 and its source. Give `check_bearing` a mapping for any other bearing (#180).
- 21 bearing formulas in `cadagent.formulas`: `rating_life`, `reliability_factor`, `deep_groove_load` (SKF's X, Y and e by clearance), `static_safety`, `duty_cycle_load` and `miner_life`, the oscillation factors `harris_factor` and `rumbarger_factor`, and an exact Hertz contact (`hertz_point_contact`, `ball_raceway_contact`). They are tested against SKF's and NSK's worked examples in `tests/fixtures/bearing-vectors.json` (#180).
- [Rolling bearings](docs/bearings.md): the check, a robot knee worked through, and four figures drawn from the code (#180).
- `cadagent.geometry.robust_union` and `robust_cut`: booleans that check every result (not null, valid by the relation gate's strict checks, at least one solid, a volume within the inputs' bounds by its adaptive integration) and fall back to one shape at a time, then, for a cut, to tools nudged by 0.01 mm. Each fallback and nudge is reported (`report=[]`) and logged; when nothing passes they raise `GeometryError` instead of returning a bad shape. Contributed by Jeff Patrick, from failures he met on a real build (#249).
- `cadagent.geometry.cache.PartCache`: caches built parts as BREP under a hash of the listed source files, parameters
  (`key_extra`) and each part's own `deps`, so a build rebuilds only the parts whose sources changed.
  `get_or_build(name, fn, deps=None)`, `get_all(builders)`, `clear()` and an optional `max_bytes` cap. Each part's
  sha256, validity, solid count and volume are checked on load, and a damaged or changed file is rebuilt; writes are
  atomic, so parallel runs never read half a file. It lives in `.cadagent-cache/parts` by default and writes its own
  `.gitignore`, so it is never committed. Contributed by Jeff Patrick (#250).
- `cad-agent package` skips folders tagged with `CACHEDIR.TAG`, such as the part cache, even when an include glob
  reaches into them (#250).
- `cadagent.manufacturing.process`: the cited process profiles (research/process-profiles.yaml) as typed values. A
  project can ask for a process's rules, minimums, tolerances, FDM layer factors by filament, or a shop's bend table, and
  every value carries its rule id and source id. Rules not verified in their source are marked `(u)` and refused for
  enforcement (#99).
- `cadagent.manufacturing.dfm.check`: minimum walls, holes, pins, gaps, bridges, overhangs, flanges and hole-to-bend
  distances held against every verified source, with the spread reported (pass, warn when sources disagree, fail when
  none is met), and whether a printed feature's stress crosses the layers, with the filament's data-sheet factors (#99).
- `cadagent.manufacturing.sheet_metal`: bend allowance, deduction, flat length, K-factor, shortest flange and relief for
  5052 and mild steel, from the shop's table first and the generic rules after (#99).
- Docs: [Process profiles in code](docs/process-checks.md), with three figures drawn from these modules (#99).
- `cad-agent overhangs [PART ...] [--limit 45] [--min-area 4]`: groups each part STL's downward faces flatter than the limit (slope from horizontal, 0° a flat ceiling) into connected regions, each with area, bounds, centre and flattest angle, in `exports/overhang-screen.json`. A screen, not a slicer: bridges anchored on both sides are listed too (#247, by Jeff Patrick).
- `cadagent.geometry.overhang_regions(mesh, limit_deg=45, min_area=4)` (`mesh` is a mesh or an STL path): the regions behind that command; `downward_area` still gives one total (#247, by Jeff Patrick).
- `cadagent.manufacturing.gcode.bridge_report(path, n)`: the longest bridge and overhang-perimeter extrusions in PrusaSlicer, Bambu Studio or OrcaSlicer G-code (or a sliced `.gcode.3mf`), with height and position, to find what a "long bridging extrusions" warning is about (#247, by Jeff Patrick).
- Lessons on printing agent-designed parts without supports (`lessons/mechanical/printing-without-supports.md`, #253, by Jeff Patrick),
  from a 46-part excavator for a Prusa XL 5T: teardrop horizontal holes, 45° cone ends on clearance cutters, clevis
  sections standing on their splice face, 45°-capped bosses on shells printed upside down, bottom cuts that keep the
  walls, roofs steeper than 45°, cutter tips kept off the faces they meet, finding a "long bridging" warning in the
  G-code (often an internal bridge over sparse infill), and slicing one part of each class early.
- Two agent-process lessons (`lessons/process/agent-process.md`, #253, by Jeff Patrick): never `pkill -f`/`pgrep -f` a pattern that is
  in your own command line, and test a flagged part alone before rerunning the full pipeline.

**Changed**
- `CONTRIBUTING.md`: a new workflow step 1, "Look before building". Before writing a new command, check, calculator,
  generator or skill, search the catalogue, `research/landscape.md`, `upstreams/registry.yaml`, `skills/` and the
  open-source libraries and agent skills outside them, and record in the PR what was adopted, wrapped, borrowed from or
  passed on, and why. The later steps move down one (#106).
- The PR template has a "Considered existing tools" section for that record. "None: no new capability" is an
  answer (#106).
- Merge gates: a review verdict counts only from a maintainer (`MAINTAINERS` in `tools/ci_gates.py`) who still has
  write access. Write access alone no longer lets a collaborator pass the review gate on their own PR. Collaborators
  push branches and run CI, and a maintainer reviews before anything merges (#111).
- The `cad-pr-reviewer` subagent checks PRs from collaborators and forks for unsafe code, CI or agent edits and
  prompt injection, and blocks with a neutral note. AGENTS.md and CONTRIBUTING.md set out three contributor tiers
  (maintainers, trusted collaborators, forks), and a repository ruleset lets only maintainers merge into `dev` and
  `main` (#111).
- The site is built and published by Cloudflare Pages from Git: every push to `main` runs `npm ci && npm run build`,
  the same settings as every other Valpatel Pages site.
  The new `npm run build` (`tools/pages-build.mjs`) fetches the full history, `origin/main` and `origin/dev`, which
  Cloudflare's clone lacks, then runs the release build.
- `release.yml` only tags and publishes the GitHub release. Its token-gated deploy job is gone, so a green release run
  can no longer hide a skipped deploy. `npm run deploy:site` stays as the by-hand fallback (#112).
- `docs/vision.md` now opens with the long-term loop (#139). Agents using cad-agent on real projects send evidence.
  Maintainer agents review it, fit it to the structure and credit the author. Releases rebuild the site and indexes
  by themselves. Two measures, the fewest tool calls and tested knowledge rather than trained knowledge, show whether
  the loop is working.
- CONTRIBUTING.md: the `main` "gate" legend now says that `ci_gates.py all` checks only the three `cad-gates` rows, so
  confirm the browser runs with `gh pr checks` (#112).
- `cadagent.formulas.nut_factor` now checks every argument, not only the flank angle. A NumPy array, which used to
  give an array of K, is refused, and so are a bool and a NaN (#230).
- `cadagent.manufacturing.fit_coupons` reads its hole undersize and fit allowances from the FDM profile by rule id;
  the numbers are unchanged (0.25 mm undersize, 0.25 mm slide, 0.3 mm free). It now needs the cad-agent checkout's
  `research/process-profiles.yaml` when imported (an editable install, as CONTRIBUTING.md asks, has it), or
  `CADAGENT_PROCESS_PROFILES` naming the file (#99).

**Fixed**
- `cadagent.mechanical.inserts.check_joint`, the `clamped on insert` row: the advice now names the washer that helps,
  a metal one between the printed part and the insert (not under the head), or a limiter. It also says that the
  whole clamp is taken on the insert's ring (the cautious bound), and that once the plastic yields the boss face
  takes some, which the check does not size. The page and the limits say the same (#230).
- `check_joint` with `installed_from="far side"`: `r["hole"]["overflow_mm3"]` is 0, since the hole is the insert's
  length; it used to report a joint-face blind hole's pocket (#230).
- `cadagent.formulas.nut_factor`, `thread_radial_pressure`, `boss_hoop_stress` and `screw_boss` take any real number.
  `np.float32`, NumPy integers such as `np.int64`, and `Decimal` used to be refused even in range wherever they
  were checked (`nut_factor`'s flank angle, and every argument of the other three), with a message that wrongly said
  they were out of range; `nut_factor`'s other arguments were not checked, and a `Decimal` there raised a
  `TypeError`. They are now used as their float values. (`np.float64` subclasses
  `float` and was always accepted.) A bool, a string or `None` is refused with a message saying it is not a real
  number. The range checks are unchanged (#230).
- `cadagent.geometry.export_print_stl`: open-edge vertices within 1 µm are welded before the watertight check, so a valid solid whose tessellation split a vertex no longer fails as non-watertight. The report adds `vertices_welded`, `mesh_volume_before_weld_mm3` and `mesh_volume_mm3`; a real hole still fails. Contributed by Jeff Patrick (#249).

**Projects must change**
- To sweep `nut_factor` over several diameters, pitches or frictions, call it once per value (#230).
- Install cad-agent editable (as CONTRIBUTING.md asks), or set `CADAGENT_PROCESS_PROFILES` to the profiles file,
  before importing `cadagent.manufacturing.fit_coupons` (#99).

## v0.12.0 (2026-11-02)

**New**
- `kit/gallery.js`: a tab's `data-item-noun` and `data-items-noun` name its cards in the status line, so a tab with one
  card can say "1 tool". Without them the tab's text names them, as before. `countLine` is exported for tests (#104).
- Two animated figures drawn from the real code on its kernel-free test fixtures (`tools/motion_figures.py`):
  `validate_motion_trace` on the analytic shaft, with a renderer that passes and one that spins the rotor about the
  wrong pivot and fails (docs/rendered-motion.md, #166); and the assembly gate's `sweep_pair` on its box world: the
  swept-box early-out, the exact samples with the bound `(g1 + g2 - h) / 2` between them, and a blocked insertion's
  first contact bisected (docs/gates.md, #164).
- `cadagent.mechanical.inserts`: heat-set inserts and compression limiters in printed parts. `check_joint` checks a
  screw into an insert: the makers' hole (CAD allowance included) and boss, the melt's room, the screw's tip against
  the hole's floor, where the clamp goes (through the insert, a far-side shoulder, or jack-out when the insert is
  recessed or the clamped hole is as wide as it), pull-out, torque-out and push-out from a shear model calibrated to
  published tests (13 PLA results and three PETG, M3 and M6, SPIROL's read off its charts; a larger insert is
  flagged), the insert's own thread and end face, a printed part clamped on that face, the plastic under the
  head, a SPIROL limiter and the preload kept (the screw, limiter and plastic as springs). It returns pass, warn or
  fail per row and the most to tighten to, which passes every row the preload loads: the screw at 75 % of its proof
  load, the limiter's rating, the insert and the plastic. `check_clamp` does the same for printed plastic clamped by
  a screw into metal or a nut, with a catalogue limiter or your own sleeve or spacer. `hole_design`,
  `boss_design`, `capacity`, `calibration`, `install_notes` and `coupon_plan` give the parts on their own, and
  every number names its document (#230).
- `cad-agent inserts joints.yaml`: checks every joint in a YAML or JSON file; exits 1 on a fail, 2 on a bad file (#230).
- `cadagent.formulas`: fifteen formulas for inserts and limiters, each with its source and golden tests:
  `insert_displaced_volume`, `overflow_volume`, `insert_shear_force`, `insert_shear_torque`, `insert_clamp_path`,
  `insert_limited_torque`, `proof_load`, `annulus_stress`, `limiter_stack`, `limiter_plastic_load`,
  `frustum_stiffness` (Shigley's clamped-member cone), `press_fit_pressure`, `press_fit_force`, `preload_retained`
  and `preload_retained_limited` (#230).
- `docs/inserts.md` with five figures drawn from the module, and `tools/insert_coupons.py`, which writes the test
  coupons as STEP and STL in their print orientation (#230).
- `cadagent.mechanical.printed_joints.pin_eye`: a pin through a printed eye, checked before printing: bearing, shear-out
  and net tension resolved on the print's layers with the FEA layer check's criterion, whether the eye fails gradually
  (bearing, from e/D 3 and w/D 6 in PLA, 4.5 and 9 in ABS and untested filaments) or suddenly, a pin turning in plastic,
  and what a metal bushing gains and costs. Pass, warn or fail with the safety factor (#97).
- `cadagent.mechanical.printed_joints.root_peel`: the root of a boss or rib loaded from the side, where the layers peel
  when it is built upright, and the preload a through-bolt (threaded rod and nuts) must keep to hold the layer seam
  closed, as tightened and after the plastic relaxes, with the torque window that closes it without crushing the boss
  (#97).
- `cadagent.mechanical.printed_joints.thread_locking`: a screw backing out under vibration: transverse slip against
  friction on the kept preload (Junker), the locking element against the thread it is in (an anaerobic threadlocker on a
  printed thread fails, a jam nut or spring washer warns), and preload held by plastic (#97).
- `cadagent.manufacturing.fit_coupons`: a printable coupon per fit, holes swept round nominal + allowance + the process
  profile's undersize, as STEP and print-oriented STL with a measurement sheet, so the first print calibrates pins,
  bushings, bearings and inserts; `from_coupon` reads the result back (#97).
- `docs/printed-joints.md`: the four pitfalls, three of them with figures drawn from the checks, and new rows in
  `docs/common-issues.md` (#97).

**Changed**
- `catalog.json`: `fields.removed` records that v0.10.0 took `gyropup` off entries while the schema stayed
  `cad-agent-catalog/2`, so a reader that checks for `/2` still runs. Do not rely on `gyropup`; read `projects` on the
  area (#104).
- `cadagent.formulas.nut_factor` refuses a flank angle outside 0 to π/2 radians. 60 passed as degrees used to give
  about three times the nut factor without complaint (#230).
  `kit/formulas.js`'s `nutFactor` refuses it the same way, and `screwBoss` with it. For now the angle must be a
  Python `int` or `float`: a NumPy scalar or a `Decimal` inside the range is refused too, wrongly reported as out of
  range; a follow-up accepts any real number (#230).

**Fixed**
- Catalogue: the status line reads "1 of 181 entries", not "1 of 181 entry". Its noun now agrees with the total it
  follows, and a tab names its cards by their own noun: "1 of 8 research pages" (#104).
- Catalogue under forced colours (Windows High Contrast and the like): the maturity bars show filled steps in
  `CanvasText` and empty ones as outlined `Canvas`, and the chosen area row takes the system's selection colours
  (`Highlight`, `HighlightText`). Before, every step and the chosen row painted the same `Canvas`, so the bars vanished
  and only bold text marked the choice (#104).
- Kit `<cad-nav>`: on a wide screen, at the end of a long page, the sticky page tree no longer slides up under the
  header. It shrinks to the room its column leaves, so its filter stays in view and typing in it no longer scrolls the
  page. Adding a page to the site's tree had pushed it under (#230).

**Projects must change**
- Pass `flank_angle` in radians to `nut_factor` (default `math.radians(60.0)`) and to the functions that pass it on
  (`screw_boss`, `insert_limited_torque`). A call that passed degrees now raises `ValueError` instead of returning
  a wrong number. Convert a NumPy angle with `float()` first (#230).
- In the browser kit (`kit/formulas.js`), pass `nutFactor`'s and `screwBoss`'s flank angle in radians too (ISO's
  60 degrees is `Math.PI / 3`). Degrees now throw `RangeError` (#230).

## v0.11.0 (2026-11-01)

**New**
- `tools/site-packet-pictures.py` renders the gate bench's review packets, as built and with one seeded defect per
  gate, into `docs/img/packets/` with a `SOURCE.json` of each run's gate counts and findings;
  `tests/test_packet_pictures.py` holds every caption on a seeded picture to its seed (#122).
- `tools/site-explore-pictures.mjs` runs the explore worked example's `catalogue`, `compare --swaps` and `optimise`
  and crops their pages into `docs/img/explore/`, dated from the example's last commit so a rebuild matches (#122).
- `tools/research_figures.py` charts the moulded and printed allowable strains (ranges drawn as ranges) and the
  printed materials' softening temperatures against a module's thermal plate limit, read from the research pages'
  tables; `tools/process_profile_figures.py` draws a chart per process section from the profile rules (#122).
- `cadagent.mechanical.connectors.cable_bend`: checks that the cable behind a plug can turn at its minimum bend radius
  before it meets a wall, a part or the next plug. Give a mate a `cable` with its diameter and the radius as the data
  sheet states it (`{"mm": 25}` or `{"x_od": 5}`); the check turns the cable each way across the mating axis and
  returns pass, warn or fail with the clearance, the direction that works and the assumptions it made. It takes CAD
  shapes or panel-frame boxes (no CAD kernel needed for those), and `bend_reach()` gives the room a bend needs in
  closed form (#168).
- `check_ports()` runs the cable check for every mate that has a `cable`, against the printed parts and the other
  ports' plugs, and fails a port whose cable cannot turn. Mates without a `cable` are checked as before (#168).
- A figure of the check, `docs/img/motion/cable-bend.svg`, on the connector-window port: a Cat6 cord turned down runs
  1.35 mm into the shelf the enclosure stands on; turned up, it clears. "Cable routes at an impossible bend radius"
  in `docs/common-issues.md` is now a checked row (#168).

**Changed**
- The eight longest text walls on the site now lead with real outputs: the toolkit, gates, explore and dossier
  pages, and the process-profiles, design-workflows, compliant-mechanisms and simulation-tools research pages. Each
  section shows a review-packet render, a command's own page, a chart drawn from the table beside it or a Mermaid
  flow, with a caption that says what it shows and what it was computed on; long reference tables fold into
  `<details>`. The wall backlog drops from 33 pages to 25 (#122).
- Erratum for v0.10.0: `cadagent.simulation.cfd` `results()` changed in three ways v0.10.0's entry did not list (#47).
  A case with fans gets one more `limits` entry. A fan's inlet or outlet face zone that catches no mesh faces sets
  `error`, so the run is not `converged`. Every result has a new `warnings` key, and fan cases written from v0.10.0 on
  have `zone_faces`. Code that compares the whole result, or counts its `limits`, must expect them.

**Fixed**
- `cadagent.review.gates.relations.relate`: a shallow near-tangent crossing that OCCT's boolean misses is no longer
  read as `touching` or `contains`. Where the two boundaries meet, the curves found by `BRepAlgoAPI_Section` guide
  samples that are classified against the other solid. A crossing outside the kernel's own common or cut makes the
  pair `unknown`, with the point and depth in `witness["crossing_probe"]`. A ball of 4 mm radius 0.011–0.23 mm
  through a cone wall had read `contains` or `touching` in 24 of 500 checks (250 positions, each against the cavity and
  the wall's part) (#46).
- Containment gate: an instance whose relation finds such a crossing fails as an escape, with the depth found (#46).

**Projects must change**
- `RELATIONS_VERSION` is now 5, so cached relations (`.cadagent-cache/gates/`) and the containment gate's cached
  checks recompute on the next run. A pair that crossed where the kernel saw no crossing now reads `unknown`, and
  every gate fails on it; nudge the parts apart or into a clear overlap. A pair whose crossing probe itself fails also
  reads `unknown`, even with no crossing found. No answer changed on the README hero's clearance sweep (811 calls) or
  the gate bench (#46).
- `RelationTable.to_dict()["method"]` now names the crossing probe, so a stored relation table compared whole with a
  new one differs even where every answer is the same (#46).

## v0.10.0 (2026-11-01)

**New**
- `kit/gallery.js`: a facet link, or a checkbox's label, can carry `data-label`: the name its chip and the empty-state
  messages use when its own text would not say it (#104).
- `cadagent.mechanical.compliant.snapfit.engagement()`: a cantilever snap's closed form along the insertion. It gives
  the root strain, the deflection force and the push to mate as the mating edge rides the hook's lead, slides along its
  land and drops off. Its peak is `check_cantilever`'s numbers, the guide's Example I among them (P 32.5 N, W 58.5 N).
  `travel_at_strain()` gives where the strain first reaches an allowable (#165).
- An animated figure of a printed snap arm engaging, on the snap-fit page, the new `compliant/` README and the animated
  figures page (`docs/img/compliant/snap-engagement.svg`). One arm laid flat in two filaments: its root strain rises to
  1.38 %, a pass at 68 % of Polymaker PolyMide CoPA's 2.02 % and a fail at 139 % of Bambu PETG-CF's 1.00 % (the V3.0
  sheet), with CoPA's push to mate peaking at 10.1 N into a CoPA part. It is the calculator's output on stated inputs,
  recorded in `tools/anim/snap-engagement.scene.json`, not a measurement. The scene also records the hook's 7.4° turn
  with the tip, which the closed form ignores, and the push on the turned face (13.7 N for CoPA): near the top of a
  steep lead the closed form under-states the push. `tools/readme_anim.py --extract snapfit` records it again, and
  `--check` fails when the SVG is stale (#165).
- `cadagent.simulation.cfd`: each fan's inlet and outlet air temperatures, mass-flow-weighted over the faces at each end
  of its zone and computed by the solver (`surfaceFieldValue`, `weightedAverage` with `weightField phi`). They come with
  the net mass flows, the backflow, each face's area and the heat the outlet stream carries above the room:
  `fans[<fan>]['inlet_c']`, `['outlet_c']`, `['inlet_kg_s']`, `['outlet_kg_s']`, `['inlet_backflow_kg_s']`,
  `['outlet_backflow_kg_s']`, `['inlet_area_m2']`, `['outlet_area_m2']` and `['heat_carried_w']`. Use them in energy
  balances (Q = ṁ c_p ΔT). `air_through_fan_c` stays the fan zone's volume average. `warnings` names a face whose
  backflow passes 10 % of its net flow, and ends whose areas or net flows are more than 10 % apart. A face with as much
  backflow as net flow, a reversed net flow, or a net flow under 1 % of the fan's free-air flow (`MIN_NET_FLOW`) has no
  temperature (#47).
- `cadagent.simulation.cfd.energy_check()` and `results()['energy_conserved']`: a result whose heat leaving is more than
  5 % off the heat put in (0.5 W when nothing is put in) says so in `warnings`. `stream_heat_w()` gives ṁ c_p (T −
  T_room) (#47).
- `tools/cfd_fan_figure.py`: two real runs of a 20 W box with an exhaust fan, recorded for the tests and drawn in the
  toolkit docs. A fan just under its opening carries more heat than leaves the room, because air goes round it again; a
  ducted fan with its hub plugged carries what leaves (#47).

**Changed**
- The site is also served at cad-agent.gyropup.com, a second custom domain on the same Cloudflare Pages project. Every
  published page now names its cad-agent.valpatel.com address as canonical, so search engines index one copy: site pages
  with `<link rel="canonical">`, and the web kit's own pages (`/kit/viewer`, `/kit/fea`, `/kit/file-viewer`), which are
  copied byte for byte from the kit, with a `Link` header. The 404 page names none. `llms.txt`, `catalog.json` and the
  sitemap already give cad-agent.valpatel.com addresses (#104).
- Catalogue (`/catalog`): the area index on the left is easier to read. Each domain is an outlined panel with a header
  in its colours and a line between rows, and the bars and counts line up in columns. Hovering a row (on screens that
  hover) or focusing it sweeps the domain's colour in from the left; the chosen row is dark, with an orange edge and
  count (#104).
- Catalogue: each domain's first row reads "All" instead of "Everything in mechanical design". Screen readers hear "All
  in mechanical design", and the filter chip and the "nothing here" messages name the domain: "Mechanical design"
  (#104).
- Catalogue: maturity bars have five steps with gaps, one per level in `docs/areas.yaml`, in the area index, the
  filters, the cards and the area panels. A key above the index shows each level's bar and word, says what a level means
  on hover or focus, and links to "What the levels mean" in the vision. Screen readers hear "maturity 3 of 5, tooling"
  (#104).
- Catalogue: no project is singled out. The Gyropup dots, the card badge, the area panel's Gyropup pill, the "Needed for
  Gyropup" filter and its boost in the featured order are gone; cad-agent is a general toolkit, and Gyropup stays as an
  example and a project that used an area. Entries from areas Gyropup marked move down the featured order of their tab
  (#104).
- `pyproject.toml` floors: `pillow>=13.0` (every older release has critical advisories), `vtk>=9.5.2` (past three
  advisories fixed in 9.5.1; the lowest VTK that cadquery-ocp 7.9.3 pins), so `cadquery>=2.8`, `markdown>=3.8.1`,
  `numpy>=1.22`, `pyyaml>=6.0` and `pytest>=9.0.3` (they had none). The package still runs on Python 3.10, but the `cad`
  and `sim` extras now need 3.11 or newer: Pillow 13 and CadQuery 2.8 dropped 3.10, and every Pillow for 3.10 has
  critical advisories. CI now also runs the core suite at the numpy, PyYAML and pytest floors, and the site and release
  tests at markdown 3.8.1 (#151).
- The web kit's `three/` and `fonts/` folders have SHA-256 receipts (`SOURCE.json`), so a silent change to any of them
  fails `tests/webkit-vendor.test.mjs` and the supply-chain report; every vendored kit file now has one. The receipt for
  three.js names its npm tarball and records the one local patch to OrbitControls; the fonts' receipt names the Google
  Fonts and licence URLs the files came from (#151).
- `tools/resource_audit.py`: a web kit receipt can list a `patched` file (expected to differ from its package, and it
  must record the SHA-256 of the package's file it was made against) while every other file must still match byte for
  byte; a receipt for files not from npm says `"npm": false` and names a source for every file (a receipt that just
  leaves out its package, or says `"npm": false` beside npm fields, is flagged and still checked as npm); an
  install-script finding is per version, and accepting one needs its fingerprint, so the next version's script is read
  again; `npx --no-install` counts as pinned, since it runs only what the lockfile installed (#151).
- Catalogue and pages: moved repositories point at their new owners (BackplaneWorks/kistack, BackplaneWorks/Backplane,
  the-dual-space/pymoo, meta/Ax), the OpenFOAM starter script's dead link points at its new GitLab home, the plain-HTTP
  CalculiX links are fixed, install advice no longer tells readers to install from a plugin marketplace or run `uvx`
  unpinned, and a `curl | sh` installer is described as the risk it is. The supply-chain report's open findings fall
  from 1 critical, 15 medium, 37 low and 12 info to 1 critical, 0 medium, 24 low and 9 info, with 3 read and accepted in
  `research/security-accepted.yaml`. What is left: DOMPurify and KaTeX inside Mermaid (#154), repositories with no push
  for a year (#154's automatic badges), Dependabot (owner, #153), and sites that refuse scripts or did not answer
  (info).
- `cad-agent snapfit --output` and `check_spec_entry()`: each snap's `material` names the `friction` its forces used, or
  `null` where the guide's table has none (PLA, PETG) and none was declared, and its `friction_basis`: `given`,
  `same material` (the default: the plastic on itself) or `against steel` (#165).
- `steady` now also holds each fan's inlet and outlet temperatures to 1 °C, like every other temperature, in cases
  written from this release on. The convergence chart draws them, and labels the volume-average line "mean over the fan
  zone (by volume)" (#47).
- `cad-agent motion-trace`: every report's `limits` list has a fourth entry, on how a declared loop is solved (rigid
  links on ideal pins in one plane, on the home assembly and circuit), even for a contract with no `loops`. It came with
  v0.9.0's closed loops and was not in that entry. A project that stores reports and compares them whole will see the
  extra entry (#187).

**Fixed**
- Catalogue: the chip for a maturity filter reads "Tooling", not "maturity toolingTooling" (#104).

**Projects must change**
- `catalog.json` and `catalog/<area>.json` no longer have a `gyropup` field on entries, and `priority` lists only `demo`
  (`docs/areas.yaml` too). `/catalog?gyropup=1` is ignored. An agent that filtered on it should read `projects` on the
  area instead: `catalog/index.json` and each area's file now list the projects that used it (#104).
- A project that pins pillow below 13.0, vtk below 9.5.2 or markdown below 3.8.1 must raise those pins before installing
  this cad-agent with the `cad`, `sim` or `site` extra (pip stops with `ResolutionImpossible`); pip upgrades unpinned
  ones as it installs. A project that pins cadquery 2.6 or 2.7 (cadquery-ocp 7.8, which pins vtk 9.3.1) must move to
  cadquery 2.8 (#151).
- A project that installs the `cad` or `sim` extra on Python 3.10 (for example a JetPack 6 system Python) must use a
  Python 3.11 or newer virtual environment; the core package and its required dependencies still install on 3.10 (#151).
- To get the weighted temperatures, write the case again (`ThermalCase.write`) and run it. A case written before this
  has no inlet or outlet faces, and continuing it does not add them, so its results keep only `air_through_fan_c`.
  Re-reading an old run moves no number (#47).
- Replace energy balances that use `air_through_fan_c` or `zones[<fan>]['T_c']` with `inlet_c` or `outlet_c` and that
  face's mass flow. A back-calculated temperature such as T_fan − Q/(ṁ c_p) moves by the gap between the two averages:
  #47 expects about 1 K with a dead hub and tip recirculation, and it is 0.1 K or less in the two recorded runs. Check
  `heat_carried_w` against the heat leaving (`heat_out_w`): more means the fan moves recirculated air, and its ṁ is not
  the flow through the parts upstream (#47).
- New runs judge two more temperatures per fan for `steady`, so `run_until_balanced` may continue a case longer (#47).

## v0.9.0 (2026-11-01)

**New**
- `tools/resource_audit.py`: a deterministic supply-chain and resource report of what cad-agent depends on, vendors and
  links to: OSV advisories and malicious packages for Python (newest and lowest allowed releases, and the transitive
  packages deps.dev resolves) and npm, pins and recorded hashes, vendored files against upstream at the pinned commit,
  web kit files against the npm tarballs their receipts name, licences, and links that died, moved or redirect
  elsewhere. The latest run is `research/security-report.md`, with a figure, and `docs/supply-chain.md` explains it
  (#117).
- CI's new `supply-chain` job (offline, not required) fails a PR into `dev` that adds a dependency, vendored file or
  catalogue entry without its report row in the description, or with a medium or worse finding; every event also fails
  on a high finding anywhere. Release PRs into `main` get only that whole-checkout check (#117).
- A weekly `supply-chain.yml` workflow runs the online checks and keeps one "Supply-chain report: open findings" issue
  current; its report job reads only, and only its issue job can write issues (#117).
- The `cad-supply-chain` skill: when to run the report, how to read it, and what blocks a merge or an adoption (#117).
- `cadagent.__version__`: the toolkit's version, for a record of what made a result. It reads the checkout's
  `pyproject.toml` when the package sits in a source tree (a checkout run with `PYTHONPATH=src`, or an editable install,
  whose installed metadata can be stale), else the installed metadata, else `0+unknown`. It imports nothing heavy
  (#144).
- `Study.layer_check(..., criterion='max-stress')`: the layers' bond as two separate checks, `tension` (max(σn, 0)
  against S_z) and `shear` (τn against S_s), instead of the combined quadratic one. `bulk_stress='in-plane'` takes the
  bulk check's von Mises of the layer plane's own stress, leaving σn and τn to the bond. With `strength_shear=S_z / 2`
  the two options give a project's own three maximum-stress checks, such as Gyropup's turret, so it can keep one
  implementation. `layer_modes()` and `in_plane_von_mises()` give the same for stress tensors (#144).
- `LayerCheck.stats`: how far past the worst corner the stress reaches. Per check it gives the 99th percentile over the
  judged volume and the elements past the allowable, with their volume. The percentile is weighted by volume, so a finer
  mesh round a peak does not raise it; a project's own p99 over element count reads differently on the same field.
  `LayerCheck.modes` gives each check per element. `worst['resolution']` measures the mesh at the worst corner, as
  `result['mesh']['peak']` does at the design peak (#144).
- `Study.render(path, field=lc)` colours a part by its layer check, or by any per-element utilisation. Elements past the
  allowable are black, and the ones not judged are grey (#144).
- `cadagent.formulas`: `torsion_shear_strain_rect` and `torsion_snap_bar` (a rectangular bar twisted by a lever, one bar
  or a rocker on two, against the Covestro allowable shear strain (1 + ν) ε), checked against Saint-Venant's series
  solution. It flags a twist large enough for the trapeze effect to add more than a tenth to the torque (#161).
- `cadagent.formulas`: `thread_radial_pressure`, `boss_hoop_stress` and `screw_boss` (a thread-forming screw in a
  plastic boss: the clamp band from a friction band, the stripping force and torque, Covestro's tightening window, the
  hoop stress at the bore and the DELTA PT maker's 2 d proportions) (#161). The drive torque makes no clamp: pass a
  measured `drive_torque`, or the clamp band allows for as much as the window permits.
- `cadagent.mechanical.bosses.printed_boss`: the same check for a boss printed in a datasheet filament, upright or
  lying, with DELTA PT sizes and where each number comes from. No published pull-out data for printed bosses was found,
  so it says the result is a starting point to test, not a rating (#161).
- Two site demos: the torsion-snap explorer, `<cad-torsion-snap>`, on Snap fits, and the screw-boss explorer,
  `<cad-printed-boss>`, on the new Screw bosses page. Both run the browser port of the Python, tested on shared vectors
  (#161).
- An animated figure of a recorded FEA mesh-convergence study, in the toolkit's meshing section and the simulation
  README (`docs/img/fea/mesh-convergence.svg`). An L-bracket's sharp and R1.5-filleted inside corner are refined step by
  step with `refine=`. It shows the mesh at the corner, the design peak, the result's flags and `converge()`'s verdict.
  The sharp peak keeps rising; the fillet's settles. It is drawn from a committed record of a real run
  (`tools/anim/fea-convergence.scene.json`) that names the gmsh and OpenCASCADE versions. `tools/readme_anim.py
  --extract convergence` records it again, and `--check` fails when the SVG is stale (#167).
- `cadagent.publish.anim.convergence`: `record()` runs this study from its spec (the bracket's size, the material, the
  load, the sizes asked for at the corner) and `render()` draws two corners' records (#167).
- `cadagent.mechanical.linkages`: sweep a closed loop through its inputs. It handles a four-bar from its crank, and a
  five-bar from both cranks or along a tip path. Each step reports the joint angles, the pins, the transmission angle
  and the Jacobian determinants. Locks, cranks falling in line, the edge of reach and assembly flips are bisected
  between samples. Each report has a pass, warn or fail status, its reachable range and its stated limits.
  `fivebar_workspace` maps a grid of crank angles (#187).
- `cadagent.formulas`: the five-bar's closed forms `fivebar_point`, `fivebar_inputs` and `fivebar_jacobians`. Their
  positions are checked against the closed forms of Gonçalves, Carvalho and Santos (COBEM 2009). The Jacobians follow
  Gosselin and Angeles (1990) and are checked against finite differences (#187).
- `cadagent.simulation.robot.write_mjcf(..., loops=[LoopClosure(...)])` closes a loop in MuJoCo with an equality
  constraint. When the `LoopClosure` gives `other_anchor`, it first checks that the two links' pins meet at home
  (`loop_gaps`, `home_frames`); without it, that home check is skipped (#187).
- `cad-agent motion-trace`: a contract can declare closed loops under `loops`. Their inputs are sampled together and
  their other joints solved, on the circuit the loop reaches from home. A new `loop-pose` check fails a renderer that
  leaves a loop open, assembles it the other way or shows another circuit (#187).
- Linkages page: sweeping four- and five-bars, with an animated five-bar figure generated from the solver (#187).

**Changed**
- The old flat import paths (`cadagent.fea` and the rest) are no longer said to go in v0.7.0, which shipped with them.
  They stay until a release whose CHANGELOG announces their removal at least one minor release ahead, under **Projects
  must change**. Their `DeprecationWarning` now says to move the import and points to the table in docs/toolkit.md
  (Package layout). No old path is removed (#144).
- `nut_factor` takes the thread's flank angle in radians (default `math.radians(60)`, the ISO thread); pass
  `math.radians(30)` for 30° thread-forming screws. It does not check the range, so an angle given in degrees is
  silently wrong: 60 gives about three times the ISO nut factor, and so about three times the tightening torque,
  while 30 gives about a sixth of it (#161).
- `PrintedMaterial` gains `strength(direction)`: the lowest datasheet tensile strength along or across the layers
  (#161).
- `Linkage`, `circles` and `ellipse_path` (the README hero's linkage helpers) moved to `cadagent.mechanical.linkages`.
  `cadagent.publish.anim.linkage` still re-exports them (#187).

**Fixed**
- `cadagent.simulation.fea.Study.converge()` no longer passes a peak at a sharp inside corner when the two meshes happen
  to agree. An L-bracket's corner refined to 0.25 mm moved only +1.8 % on the finer mesh and was called converged, while
  its own note said the corner never converges (#167).
- `cadagent.simulation.cfd.read_results`: a fin block's air temperature now has to settle within 1 °C, like every other
  temperature, not 2 °C. `steady` takes its limits from `convergence_limits`, the same numbers the chart's captions show
  (#175).
- `cadagent.simulation.cfd.read_results`: a continuation that stopped before its first temperature sample (within 9
  iterations) now replaces what the solve before it logged after its start. The histories, the headline values and the
  chart stop where it began, and it gets no convergence window, so nothing is judged steady on the solve before (#176).
- Release notes: the v0.8.0 entry read as if every site doc page opens with a picture band. At v0.8.0 three pages had
  one (Gates, Dossier and the design-process plan), one of them with input → tool → output tiles, and nine had placed
  pictures. The v0.8.0 GitHub release notes were corrected the same day (#179).

**Projects must change**
- Nothing for existing layer checks: the defaults (`criterion='combined'`, `bulk_stress='full'`) give the same numbers
  as before. `LayerCheck.as_dict()` adds `criterion`, `bulk_stress`, `stats` and `worst['resolution']`, and every key it
  had keeps its value. A test that compares the whole dict must allow the new keys (#144).
- A project that hashes its source folders in evidence receipts can move its old-path imports when it next regenerates
  them: no removal release is set yet (#144).
- The old paths' warning text changed. It still starts `cadagent.<old> moved to cadagent.<new>`, but no longer says "the
  old path goes in v0.7.0". A warnings filter or a test that matches the old ending must match the start instead (#144).
- `converge()` on a peak at a sharp inside corner now always returns `converged: False` with a `MeshWarning`, even when
  the change is within the tolerance. Model the fillet the part will have, or filter `MeshWarning` where warnings are
  errors (#167).
- Cases with an exchanger fin block whose air still moves by 1–2 °C over the window no longer count as `steady` or
  `converged`, and `run_until_balanced` keeps going there. Re-read such results; none of 13 recorded runs flips (#175).
- When the newest solve stopped within 9 iterations, `convergence` is now empty, `convergence_window` is absent and
  `steady` is False. Continue the case to judge it (#176).

## v0.8.0 (2026-11-01)

**New**
- `cadagent.simulation.fea.Study(refine=[(point_mm, radius_mm, size_mm), ...])`: a finer mesh round a spot (a gmsh
  Ball field each, under a Min field). The rest of the mesh stays as it was, so one fillet or hole converges without
  refining the whole part (#144).
- `Study.converge(factor=0.75)`: the same loads on a finer mesh; it gives the design peak's change and whether it
  moved. Past 5 %, or when the finer mesh does not resolve the peak either, it is not converged (a `MeshWarning`)
  (#144).
- `result['mesh']` records the mesher (`mesher`: the gmsh and OpenCASCADE versions, the build's OS and date, a hash of
  the gmsh library, the platform) and the design peak's resolution (`peak`: where it sits, the thinnest wall round it,
  the element size there and `elements_across`). Under 3 elements across, it is flagged (`wall_resolved` false, a
  `MeshWarning`): a peak in a wall one or two elements thick is not a result. At an inside fillet or a hole,
  elements larger than its radius are flagged too (`radius_mm`, `radius_resolved`) (#144).
- A check before meshing lists faces under (mesh_mm/10)² in area, long faces under mesh_mm/10 in width, and edges under
  mesh_mm/10 (`Study.slivers`). It warns by default; `slivers='raise'` stops in seconds with a `MeshRefusal`, before a
  long mesh (#144).
- When gmsh refuses a part ("PLC Error: A segment and a facet intersect at point", or "Could not recover boundary
  mesh"), `Study` raises a `MeshRefusal` with the point and the nearest faces with their areas when gmsh gives a
  point, not gmsh's bare message (`parse_gmsh_refusal()` reads the log). A second try that meshes is used, with a
  `MeshWarning`. `Study.faces_near(point)` names the faces round any point (#144).
- `cadagent.formulas`: `fans_in_series` and `fans_in_parallel` (identical fans: pressures add at one flow, flows add
  at one pressure) and `fan_stall_flow` (the peak that ends the curve's last rise; below it, the stall region), with
  hand-solved tests (#160).
- `cadagent.thermal.fans`: the ebm-papst W2G115-AD15-13's curves at 8, 12 and 16 V, read from the datasheet's vector
  chart. Solved on the datasheet's own system curves, they give back every operating point it tabulates, within the
  table's rounding and the chart reading (the test allows 3.5 m³/h and 1 Pa) (#160).
- The fan-curve explorer, `<cad-fan-curve>`, on the new Airflow and fans page and on Engineering formulas. Pick the
  voltage, the pressure your enclosure needs at 100 m³/h, and one to four fans in parallel or in series. It marks the
  operating point and the stall region, and warns when the point lands in it (#160).
- Site doc pages open with a picture band: a hero figure and, where a page has them, input → tool → output tiles, then
  cards for the sections that have pictures. `docs/pages.yaml` places them and figures inside sections, on the site
  only; the Markdown twins and `llms.txt` are unchanged (#179).
- Every placed picture says what it is, above its caption: "Real output of `<tool>`" or "Diagram of `<tool>`, drawn by
  `<script>`", and what it was computed on (Gyropup, a test fixture, a worked example, published sources). A figure
  opens its full-size image; a tile links to the section that explains it (#179).
- The build refuses a `docs/pages.yaml` entry with an unknown or misspelled key, an entry that places nothing, a picture
  that is not committed under `docs/img/`, a tool that is not a `cad-agent` command, a `cadagent` module, a web kit file
  or a script under `tools/`, a diagram without the `tools/` script that drew it, and a tile link or `below:` target
  that is not there (#179).
- `tools/site-bench-pictures.mjs` captures the review site that `cad-agent site` builds for the gate bench, cropped to
  whole lines. `tools/site-kit-pictures.mjs` captures the web kit at work: the part table and tracker on the gate
  bench's parts, and the file viewer on a Gyropup STEP file in its default, front, themed and broken-file states (#179).
- `cad-agent export-3mf` also writes `exports/<name>-plates.3mf`: every printed part at its quantity, in print
  orientation, packed onto as many build plates as the bed needs, in one Bambu Studio project. Where Bambu Studio is
  installed at export time, the file carries its project settings, opens with the plates laid out and slices plate
  by plate; without it, Bambu Studio opens the parts on one plate. Parts with different filaments never share a
  plate. Next to it, `<name>-plates.svg` shows the plates from above and `<name>-plates.json` records the layout
  (#84).
- `cadagent.manufacturing.plates`: `pack` (MaxRects over footprints, with gap, margin, keep-out areas, quarter turns
  and the diagonal turn a long part needs), `check_plates`, `write_plates_3mf` and `read_plates_3mf` (read back and
  verified; the same bytes for the same parts, settings and Bambu Studio version), `plates_svg` and `export_plates`
  (#84).
- `cadagent.manufacturing.slicer.project_settings`: Bambu Studio's own project settings for a printer, process and
  filaments, and `default_bed_type`: the plate surface a printer ships with (#84).
- `cad.plates` in `cad-agent.yaml`: `parts` (with each part's `quantity` and `filament`), `gap_mm`, `margin_mm`,
  `rotate`, `keep_out` and `bed_type`. Parts and quantities default to `cad.release` (#84).

**Changed**
- Kit `<cad-nav>` (`webkit/nav.js`, `nav.css`): on narrow screens the "Pages and contents" toggle is a native `<details
  class="cad-nav-fold"><summary class="cad-nav-toggle">` around the panel, so the tree opens with a tap, Enter or Space
  even when `nav.js` is slow, blocked or fails, and without script. On wide screens the fold takes no box and its
  summary hides, so the panel stays a sticky column; `nav.js` keeps the fold open there for browsers without
  `::details-content`, and never closes a fold the reader opened (#134).
- The site's doc pages write that fold; phones without script now get it too, in place of the tree moved below the
  article (#134).
- `fan_operating_point` also returns `stall`, true when the point is below `fan_stall_flow` (#160).
- `fan_operating_point`, `fan_curve_line` and `system_coefficient` refuse what has no answer with `ValueError`: NaN or
  infinite losses, a system point at zero or negative flow or with a negative pressure drop, and a shut-off pressure
  or free-air flow of 0 or less (#160).
- On the site, a table of more than 12 rows or a code block of more than 24 lines folds into a `<details>` that says
  what is inside. Chrome's find-in-page opens a fold that has a match, and the Markdown twin keeps it all open (#179).
- The pictures of the hinge sweep say they show the gate bench with a seeded fault (`flap_hits_frame`, its arm's range
  raised to 60 degrees). As built, the arm sweeps 0 to 40 degrees with 1.60 mm clearance (#179, #184 review).
- The "Hinge sweep" and "Module insertion" demos link to their sections in `docs/catalog.yaml` (#179).
- The site preloads its mono font, so the home page no longer shifts at 360 px when the font arrives (#179).
- The wall-of-text backlog is down from 39 pages to 33. The longest stretch without a picture is down from 20,202 px
  (`/docs/dossier`) to 12,296 px (`/research/design-workflows`), in Chrome at 1366 × 800 (#179).

**Fixed**
- `<cad-nav>`: a wheel over the rail or the tree while an outline jump is still scrolling releases the jump again, so
  the section being read is marked, not the heading the reader turned away from; a wheel that only scrolls the tree
  still keeps it (#134, #123 review 4).
- `<cad-nav>`: a jump ends when the page shows its heading, not after 150 ms without a scroll, so a frame slow to paint
  no longer drops the mark to another section partway through (#134, #158).
- `<cad-nav>`: no link text shows in the corners beside the filter pill while the tree is scrolled (#134).
- The FEA hot-spot hint reads "sharp inside corner" where an inside corner meets a side face; it could read "outside
  edge" there (#144).

**Projects must change**
- Pages that write `<cad-nav>` markup with the old `<button class="cad-nav-toggle">` should write the `<details
  class="cad-nav-fold">` fold instead (the markup is in the `nav.js` header). The script wraps the old button into a
  fold when it runs, but until then, or without it, the button does nothing and the tree shows open on narrow screens
  (#134).
- `Study()` now warns (`MeshWarning`) when the part has sliver faces or edges, and `Study.solve()` when the design
  peak's wall is under 3 elements thick or its inside fillet or hole is smaller than the elements there. A study that
  treats warnings as errors fails on them: mesh finer there (`refine=`), remove the sliver, or filter `MeshWarning`.
  Without `refine=`, meshes and computed values are unchanged, bit for bit, apart from the hot-spot hint fix above.
  Every result gains `result['mesh']` keys (`mesher`, `refine`, `slivers`, `peak`), so committed result and viewer
  JSON changes, and differs between machines: `mesher` records the gmsh library hash and the Python version (#144).
- Code that compares the whole result of `fan_operating_point` with a dict must add the `stall` key (#160).
- Code that caught `ZeroDivisionError` from `system_coefficient` at zero flow must catch `ValueError`. A negative
  flow or pressure drop, which used to return a coefficient, now raises it too (#160).
- `export-3mf` (and `all`) now exits 1 when a part fits no build plate or the parts need more than 36 plates. Set
  `cad.plates.parts` to the parts you print, or `cad.plates: false` to write no plates file. Where Bambu Studio is
  installed, it also exits 1 when `cad.printer.bed_mm` is larger than the printable area of the `cad.slicer.printer`
  profile (the P1S's 256 × 256 mm when `cad.slicer.printer` is not set): set `cad.slicer.printer` to your printer, or
  `cad.plates: false` (#84).
- `exports/` gains three files per project, deleted again by a run that fails or by `cad.plates: false`. A part
  named `<name>-plates` must be renamed, or plates turned off (#84).
- A `cad.slicer` printer, process or filament (or a `cad.plates` filament) that Bambu Studio has no profile for now
  stops `export-3mf` with a config error (exit 2) where Bambu Studio is installed (#84).

## v0.7.0 (2026-11-01)

**New**
- cad-agent's own website (not yet sites made with `cad-agent site`, which still draw diagrams in the reader's browser):
  the build draws every Mermaid diagram itself, in headless Chromium through Playwright, and writes the finished
  `<figure class="cad-diagram" data-state="ready">` into the page (`tools/site-diagrams.mjs`). Pages no longer move
  while they load: the worst layout shift on a page with a diagram falls from 0.58 to 0.012, against Google's "good"
  limit of 0.1. Diagrams show without script, and no page downloads Mermaid to draw them. On one machine and browser
  build, output is the same bytes for the same source, theme, Mermaid and kit, and is cached in `.cache/site-diagrams/`;
  the build log names label characters the site's font lacks, which another machine measures differently. A gantt chart
  is drawn without its "today" line. With no browser, or with `--client-diagrams`, the build warns and leaves the
  diagrams to the reader's browser; `npm run deploy:site` still deploys (#132).
- Web kit: `drawDiagram(source, {theme, id, fontFamily, fontSize, mermaid})` in `diagrams.js` draws one diagram ahead
  of time and returns the finished figure. `observeDiagrams` keeps such figures as they are, and draws one again only
  when the page's theme is not the one it was drawn in (#132).
- `cadagent.review.evidence.geometry_identity(shape)`: an optional identity of a solid that does not depend on the
  platform. It holds the volume, the centre of mass and the inertia (tensor and principal moments), rounded, with the
  tolerances it matches to (relative 1e-6 by default) in the record. Each principal moment has its own tolerance, never
  below a thousandth of the largest moment's, so a slender part's small moment is compared to itself, not to its length.
  Compare two identities with `identity_mismatches(a, b)`. An x86-64 and an aarch64 host gave matching identities for
  all 43 solids of a vendor STEP and for 12 public test solids, while they shared 4 of 43 and 4 of 12 content hashes.
  Those counts were made with the earlier, looser tolerance on the small moments, and were not re-run; the differences
  seen were about 1e-13 relative. It is not a hash: different solids can share one, and a change below the tolerance is
  not seen, so it explains a hash mismatch and never signs anything off (#144).
- `cadagent.review.evidence.hash_platform()` names what a content hash depends on besides the shape: the CPU
  architecture, the system, the C library, and the OCP version and package. `record_hash_platform(record)` reads it
  from a geometry record. `hash_platform_note(recorded, current)` says when two records differ. Equal records do not
  promise equal hashes, since not everything the kernel's arithmetic depends on is named (#144).
- `cadagent.geometry.export_step` writes a cadquery `Assembly` too, with the same bytes on every export: the file
  `Assembly.save` writes (colours, names, placements), with a fixed header date, link ids 1, 2, ... in file order,
  each node added without a name called `<parent>.<k>` instead of a random uuid, and the colour records in one order
  (OCCT writes them in heap-address order). Sub-shape names and colours (`Assembly.addSubshape`) are refused, and
  so are written names cadquery's reader would refuse or misread: a child with its parent's name or a sibling's (an
  unnamed root takes the file's name, so `frame.step` with a child `frame` needs `name=`) (#150).
- `cadagent.project.source_date_epoch`, `source_time` and `source_stamp`: the date a build output records instead of the
  wall clock, `SOURCE_DATE_EPOCH` ([reproducible-builds.org](https://reproducible-builds.org/specs/source-date-epoch/)),
  else the last commit that changed the project outside its outputs (#150).
- `cadagent.formulas.fourbar_input_limits(a, b, c, d)`: the input angles where a four-bar locks (coupler and rocker in
  one line, Norton's toggle positions), whether the input turns fully, and whether the links close at all (#159).
- `cadagent.formulas.grashof` also returns `inversion`: crank-rocker, double-crank, rocker-crank, double-rocker,
  triple-rocker or change-point (#159).
- `kit/formulas.js` ports `grashof`, `fourbarAngles`, `transmissionAngle` and `fourbarInputLimits`, tested against the
  Python on golden vectors that cover both branches, change points and the input limits (#159).
- `<cad-fourbar>` (`kit/fourbar.js`, `kit/fourbar.css`): a four-bar linkage animator with link-length sliders, both
  assemblies, the coupler curve, the Grashof class, and the transmission angle charted against 40°. A linkage whose
  input cannot turn fully stops at its limits. On the new Four-bar linkages page and on Engineering formulas (#159).

**Changed**
- Web kit: the sideways-scroll hint is shown or folded away by `diagrams.css`, from the drawing's width
  (`--cad-diagram-w`) and the figure's, so it shows when it should without script and nothing moves when the script
  runs. A hint that wraps keeps both lines. `.cad-diagram` is now a size container (`container-type: inline-size`), and
  the source in the disclosure is `pre.cad-diagram-source` (#132).
- `exports/dossier-geometry.json`: `hash` is now `{"recipe": ..., "platform": hash_platform()}`, where it was the
  recipe string. Every release, this one and earlier ones, leaves `hash` out of the gates' geometry digest, so a
  record rebuilt with this release has the same digest and no verdict or packet goes stale. Committed records show
  the change once, and the platform differs between builders on different machines, like `actor` (#144).
- Reviewer records (`dossier/reviews/*.json`) carry the platform of the bundle they were written against, in
  `bundle.hash_platform`. Earlier releases accept and ignore it. When a review goes stale (`review-stale`,
  `stale-hashes`) and the geometry was rebuilt on another platform, the message names both platforms: the hashes may
  have changed with the platform, not the geometry. A geometry or reviewer record from before this release names no
  platform, and the message stays as it was (#144).
- `shape_content_hash`'s docstring says the hash is tied to the CPU architecture as well as to the OCCT version.
  `tools/volume_probe.py` receipts record `hash_platform` (#144).
- `cad-agent mcmaster`: after McMaster asks for a login, the run asks for no more product pages. Each part still to
  download is reported as not fetched, and the command exits 1 (#144).
- The FEA docs (`docs/toolkit.md`) and the `cad-remote-runs` skill explain how to run the FEA on aarch64 Linux.
  PyPI has no aarch64 wheel for gmsh 4.15.2 (nor for pypardiso's MKL). Use conda-forge's gmsh, from micromamba,
  linked into the venv, and preload that environment's OpenSSL if `import gmsh` asks for `OPENSSL_3.4.0` (#144).
- `cad-agent package`: the same files give the same zip on every rebuild and in every checkout. Entries are sorted by
  path and carry the source date, mode `rw-r--r--` and a Unix host, not each file's own time and mode (#150).
- Report time stamps are the source date, never the build time, shown with where it came from
  (`2026-10-30 12:00 UTC (last commit)`): `header_meta.generated` in the results JSON and the report page,
  `simreport`'s `Generated`, the site's footer, the explore comparison's `generated` and the review bundle's
  `created`. The site's document cards show each page's last commit date, not its file time. A `simreport` page is
  dated by the project that holds it, wherever the script runs from. A project that commits these pages no longer
  gets a diff on every rebuild, and committing them does not change them (#150).
- The site's "Recent changes" table lists the commits that changed the project's sources: a commit of only its
  outputs (exports, previews, the site, the release folder, the report page) is left out, and so are commits outside
  the project's folder, so committing the site does not change the site again (#150).
- `cad-agent release` and `step_timestamp` share one `SOURCE_DATE_EPOCH` parser: a malformed value stops the command
  with exit 2 (`release` used to ignore it and take the commit's date) (#150).
- `cadagent.review.gates.relations.relate` and the relation table measure the distance between two solids faster (#186).
  On solids, `BRepExtrema_DistShapeShape` first checks whether any vertex of one lies inside the other. OCCT 7.9 builds
  a new point classifier for each small chunk of vertices, which was most of the time of an apart pair of many-faced
  parts. The gates now run that check once, with one classifier per solid. When no vertex is inside, neither part has a
  free edge or vertex and the faces are clear of each other, they take BRepExtrema's distance between the faces, which
  gives the same gap and points. Every relation, witness included, is byte-identical to before on the 811 pairs of the
  README hero's clearance sweep on Gyropup's leg. On a 24-core workstation the sweep takes 685 s of calls instead of
  951 s (183 s to 134 s on 6 workers). Pairs of many-faced links run up to 2.7× faster, and a synthetic pocketed
  block 2–5×. Machines with fewer cores gain less, because OCCT builds about ten classifiers per thread. Pairs whose
  time is BRepExtrema's own search gain little. Cached relations stay valid.

**Fixed**
- `cadagent.mechanical.mcmaster`: a product page that shows McMaster's login prompt ("Log in to view Product Detail")
  raises `LoginRequired`, a `RuntimeError`. Its message says McMaster asked for a login and the part number may be
  fine. It points to the public search page for the price and to the maker's datasheet for the ratings. It used to
  say "not a product page (no specification table)", which read as a wrong part number. The prompt is read from the
  text a reader sees: the browser's rendered text, or, from saved HTML, the text outside scripts, styles and hidden
  elements. So neither the header's "Log in" link nor a hidden login dialog counts (#144).
- `<cad-cantilever>` and `<cad-fourbar>` (`kit/cantilever.js`, `kit/fourbar.js`): Pause works in WebKit. The demos
  rewrote the button's label on every animation frame, and WebKit drops the click of a press that started on the old
  text, so a press of a few frames never paused them. In Playwright's WebKit it failed on every one of 20 presses.
  Safari uses the same engine; it was not tried on a Mac. The label is now written only when it changes (#211).

**Projects must change**
- A `.cad-diagram` placed where its width depends on its content (a float, an inline-block, a shrink-to-fit cell) now
  needs a width of its own, because a size container does not take its width from its children. Projects with a
  copied kit can rerun `cad-agent webkit <dir>` to get `drawDiagram` (#132).
- Code that reads `hash` in `exports/dossier-geometry.json` as the recipe string reads `hash["recipe"]` now (a
  record from an earlier release still has the string). No shape content hash, geometry digest or verdict changes,
  under this release or an earlier one; the committed geometry record shows the new `hash` object once (#144).
- A receipt that pins `shape_content_hash` values (a vendor-solid probe, for example) can be checked only on the
  platform that made it. Record `hash_platform()` with it, and match solids by `geometry_identity` where a check
  must pass on any host (#144).
- Hashes that change once, then stay the same for the same files at the same commit: the review package zip
  (`exports/<name>.zip`; its `-manifest.json` is unchanged), `exports/cad-agent-results.json`,
  `docs/cad-agent-report.html`, `site/index.html`, `simreport` pages, `comparison.json` / `leaderboard.json`,
  `compare.html` / `leaderboard.html` and review `bundle.json`. Re-record any sha256 of these (an evidence record's
  `artifact_sha256` or `report_sha256`, a release note), and commit the regenerated pages once (#150).
- Code that reads `header_meta.generated`, `comparison.json`'s `generated` or a `Generated` meta entry as a date: it
  now ends in `(last commit)` or `(SOURCE_DATE_EPOCH)`, is UTC (the comparison's was local time), and reads
  `undated (...)` outside git; `bundle.json`'s `created` can be `null` (#150).
- Write assembly STEP files with `export_step(assy, path)` instead of `assy.save(path)` or `assy.export(path)` (#150).
- Set `SOURCE_DATE_EPOCH` to a whole number of seconds, or leave it unset. A malformed value now stops `report`,
  `site`, `package`, `compare` and `release` with exit 2, and nothing is written; v0.6.0 ignored a malformed value
  (#150).
- Code that compares `grashof()`'s whole result with a dict: add the `inversion` key. Code that reads `kind` or
  `crank_rotates` is unchanged (#159).
- Projects with a copied kit: rerun `cad-agent webkit <dir>` (and rebuild sites made with `cad-agent site`) to ship the
  fixed `cantilever.js` and `fourbar.js` (#211).

## v0.6.0 (2026-11-01)

**New**
- `cadagent.simulation.fea.Study.layer_check(normal)` checks a printed part's stress against its layers, for a print
  whose layer normal (build direction) is `normal`. Two checks run at every element corner. The bond check takes
  √(max(σn, 0)² + 3τn²) against the across-layer allowable. The bulk check takes von Mises against the in-plane
  allowable. It returns per-element factors and modes, the safety factor, the governing check and the worst corner
  (`LayerCheck`; `as_dict()` for records). The interlayer shear allowable is on no data sheet, so it is assumed to be
  S_z / √3 unless `strength_shear` is given. It is a screening check of the isotropic stress, not a qualification:
  test a printed part (#144).
- Every printed material in `MATERIALS` has `layer_strengths_mpa` (X-Y, Z), which `layer_check` defaults to.
  - The Z allowable is the row's strength.
  - The X-Y allowable is that strength times the lowest X-Y / Z tensile strength ratio of the sheet editions read, so
    it sits at least as far below each sheet's in-plane strength, as a ratio: PLA 27.9, PETG 24.6, PETG-CF 26.6,
    PAHT-CF 78.3 and TPU 95A 9.8 MPa.
  - The humid PA6-CF rows share their two strengths, 40.8 / 18.1 MPa.
  - No existing result changes (#144).
- `Study.solve()` keeps the corner stress tensors as `Study.sig_corner` (elements × 4 corners × 3 × 3, MPa), for checks
  of your own (#144).
- `Study.result['material_data']` records the material data a study used (#144):
  - the built-in row's `key`;
  - E and the print direction it is for, ν, the strength, the layer allowables and the density;
  - `source`, and `note`, which names the data sheet and its edition;
  - `constants_hash`, a hash of the constants.
- `material_changes(old, new)` lists what differs between the material data of two records (study results, their
  `material_data`, `export_viewer()` files or `Material`s). A record made on one toolkit and checked on another then
  shows a changed material as a material change, not a design change (#144).
- `cad-agent optimise`: `search.confirm` evaluates the first `top` feasible trials again at a higher fidelity once the
  trials are done, with `args` appended to the evaluator's command (`[--mesh, "3"]`) or its own `evaluator`. The
  leaderboard ranks each confirmed trial on its confirmed values and keeps the screening values beside them (`confirm`
  in `leaderboard.json`, a Confirmed column on the page). It flags a change of more than `tolerance_pct` (default 5 %)
  in an objective or constraint, a trial that becomes infeasible, and a confirmation that fails.
  Confirmations are kept in `confirm.jsonl` and reused while the confirm evaluator is unchanged; `--no-confirm` skips
  the stage for one run (#144, [docs/explore.md](docs/explore.md#confirm-the-leaders)).
- Command evaluators: `{result}` in the argv is a file path the evaluator writes its JSON reply to, read after the
  command exits, so output that native code writes to fd 1 (gmsh, from C) can no longer corrupt the reply. Without
  `{result}`, stdout is read as before. An evaluator that runs gmsh, OpenCASCADE or a solver can take `{result}` in
  place of an `os.dup2` workaround (#144).

**Changed**
- `cad-agent.yaml` is the only project config file `cad-agent` reads, and `CAD_AGENT_PROJECT` and
  `CAD_AGENT_RENDER_ONLY` are its only environment variables: the older config file name and the older names of both
  variables are gone. With no `cad-agent.yaml`, the error names any other `*.yaml` / `*.yml` file in the project root
  with a top-level `cad:` key and says to rename it (`cadagent.project.other_cad_configs`) (#135).
- `cadagent.review.dossier.project_root` finds the project root by `cad-agent.yaml` only (#135).
- `cad-agent catalogue`, `compare` and `optimise` run without a catalogue when no slots are declared: a search that
  changes only parameters needs none, and each design's BOM is empty. With slots and no catalogue it is still an error,
  which now names the slots. When no design has a BOM line, the always-0 cost and mass are left out of the comparison's
  columns unless they are objectives or constraints. A parameter-only project can delete the empty catalogue file it
  kept only to satisfy `cad-agent` (#144).
- `PrintedMaterial` keeps every data-sheet edition read, current first, as `sheets` (a `Sheet` each: maker, title,
  edition, PDF date, page, link and values). Across them it takes the lowest allowable, the highest modulus for the
  mating force (`secant_upper_bound()`) and the lowest for the retention force (`retention_modulus()`), and
  `derivation()` (the `cad-agent snapfit --output` JSON) names the edition behind each number (`xy.sheet`, `z.sheet`,
  `modulus.mating.sheet`, `modulus.retention.sheet`). `source` lists every sheet. Pinned by
  `tests/test_snapfit_sheets.py` (#156).
- `check_cantilever()` takes `retention_secant_mpa` for the separation force; the snapfit output adds
  `material.retention_secant_mpa` and, where it differs, `retention_deflection_force_n` (#156).

**Fixed**
- Web kit: vendored Mermaid 11.4.1 → 11.17.2, which clears its nine OSV advisories, among them the two label XSS
  (sequence-diagram KaTeX labels, GHSA-7rqq-prvp-x9jh; architecture `iconText`, GHSA-8gwm-58g9-j8pw), CSS injection,
  prototype pollution and the XY and Gantt chart infinite loops. A browser test now renders both XSS payloads and fails
  if either runs (it does on 11.4.1). Still open: the DOMPurify 3.4.12 and KaTeX 0.16.47 that `mermaid.min.js`
  bundles have five and one advisories of their own (fixed in DOMPurify 3.4.17 and KaTeX 0.18.2), which a check on
  Mermaid does not show. No Mermaid release bundles a fixed DOMPurify yet; `SOURCE.json` records them (#152).
- Web kit file viewer: the 3MF loader's fflate 0.6.9 (three.js r160's copy) → fflate 0.8.3 from npm. 0.6.9's
  `unzipSync` loops forever on a crafted ZIP64 directory entry (GHSA-px8p-9vwx-vf98); a unit test feeds it that archive
  and requires an error within 5 s. The viewer's own ZIP layout check already refused that archive before the parser saw
  it; the fix covers any other code that imports the kit's `fflate.module.js`. Unzip filters now work as documented (#152).
- `src/cadagent/webkit/vendor/mermaid/SOURCE.json` and `src/cadagent/webkit/vendor/file-viewer-sources.json`
  record each package's npm URL, integrity and file SHA-256s; `tests/webkit-vendor.test.mjs` checks the files and
  the notices against them (#152).
- Printed snap-fit allowables (`cadagent.mechanical.compliant.allowables`) come from Bambu's current V3.0 data sheets,
  which give lower strengths than the V2.0 copies cited before. Single joining, along / across the layers: PETG-CF
  1.68 → 1.00 % (the old value was too generous: a snap sized with it can crack), PLA Basic 1.02 → 0.95 %, PLA Matte
  1.14 / 1.05 → 1.07 / 0.92 %, Bambu ASA 1.49 / 1.16 → 1.06 / 1.02 % (#156).
- Bambu PETG Basic V3.0 is a reformulated filament sold under the same name, and a spool does not say which it is.
  `petg-bambu-basic` takes the cautious one for each quantity: the allowable from V3.0 (2.30 → 1.28 % along, 0.96 %
  across), the mating force from V3.0's modulus (1460 / 1120 → 2780 / 2550 MPa) and the retention force from V2.0's
  (1460 / 1120 MPa, as before) (#156).
- FEA humid PA6-CF rows (`pa6_cf_xy`, `pa6_cf_z`): the modulus takes the wet / dry modulus ratio of a water-saturated
  print (0.290 X-Y, 0.281 Z, Polymaker PA6-CF20 V1.1) instead of x0.6, a strength-like ratio; the strength takes the
  sheet's strength ratio (0.500, 0.472). E 2126 → 1029 MPa and 1042 → 488 MPa; strength 48.96 → 40.84 MPa and 23.04 →
  18.13 MPa (#157).
- FEA metals use design minimums from MIL-HDBK-5J instead of typical values: `al6061` yield 276 → 241.3 MPa (E 68900 →
  68258 MPa); `al7075` 503 → 461.9 MPa for sheet and plate up to 2 in thick (E 71700 → 71016 MPa, density 2.81 →
  2.80); `steel` 250 → 248.2 MPa (AISI 1025, the same 36 ksi minimum as ASTM A36; E 200000 → 199948 MPa,
  ν 0.29 → 0.32, so the shear modulus falls 2.3 %, density 7.85 → 7.86). Each note names its table and the weaker
  stock the row does not cover (extruded 6061 rod, bar and shapes across the grain, 33 / 28 ksi; 7075 bar and rod,
  66–60 ksi; 7075 plate over 2 in); `cf_tube` is labelled a typical value (#157).

**Projects must change**
- A project whose `cad:` section is in a config file under any other name: rename that file to `cad-agent.yaml`.
  Every command that reads the project exits 2 until then, and its error names the file (#135).
- A build step that reads the project root from the older variable: read `CAD_AGENT_PROJECT`. A script that sets the
  older render-subset variable: set `CAD_AGENT_RENDER_ONLY` (#135).
- Code that imported `cadagent.project.CONFIG_NAMES`, `cadagent.publish.render.LEGACY_ONLY_ENV` or
  `cadagent.review.dossier.registry.CONFIG_NAMES`: use `cadagent.project.CONFIG_NAME` (#135).
- Adding `{result}` to the evaluator of an existing search changes the evaluator in its `search.json`, so
  `cad-agent optimise` refuses to continue those trials: run it once with `--fresh`. Adding or changing `confirm` does
  not (#144).
- Projects with a copied kit: rerun `cad-agent webkit <dir>` (and rebuild sites made with `cad-agent site`) to ship the
  fixed files: the new Mermaid and fflate (#152), and the V3.0 snap-fit data in `formulas-data.js` that the
  `<cad-cantilever>` widget reads (#156). Diagrams keep Mermaid 11's layout and theme; Mermaid 12 (ELK layout and a new
  default look) is not taken.
- Re-run `cad-agent snapfit` for printed snaps in `petg-cf-bambu` (allowable −41 %), `petg-bambu-basic` (−44 % along,
  −58 % across), `asa-bambu` (−29 % / −11 %), `pla-bambu-matte` (−6 % / −12 %) and `pla-bambu-basic` (−7 %): a snap
  whose root strain sits between the old and new allowable now fails. PETG Basic's mating force reads 1.9x (along) and
  2.3x (across) higher, its retention force as before; PLA Basic's retention force reads 4 % / 5 % lower (#156).
- Code that built `PrintedMaterial(name, source, e_mpa, uts_mpa, break_pct, ...)` passes `sheets=(Sheet(...), ...)`
  instead, and reads the values from `material.sheets[i]`. `PrintedMaterial.rule(axis)` returns three values,
  `(strain, limit, sheet)`, not two: code that unpacks two raises `ValueError` (#156).
- Re-run FEA with `pa6_cf_xy` and `pa6_cf_z`: deflections read 2.07x and 2.14x larger than with v0.5.0 (2.9x and 4.9x
  than with v0.4.2; stiffness the inverse), and safety factors 0.83x and 0.79x; a force or stress worked out at a
  given travel falls with E (#157).
- Re-run FEA safety factors with `al6061` (0.87x), `al7075` (0.92x) and `steel` (0.99x); aluminium deflections read
  about 1 % larger. For a part cut from weaker stock, replace the row's strength with the handbook's for that stock:
  extruded 6061 loaded across the grain (28 ksi, 193 MPa, over 1 in), 7075 plate thicker than 2 in (down to 54 ksi,
  372 MPa, at 3.5–4 in), 7075 bar and rod (66 ksi to 2 in) (#157).
- Printed-part FEA deflection checks not re-run since #125 (v0.5.0) read 31–147 % larger now than before it (TPU
  305 %; the humid PA6-CF rows 191 % and 392 % with this release); re-run them with this release's values (#157).

## v0.5.0 (2026-11-01)

**New**
- `cad-agent snapfit`: cantilever, torsion and annular snap-fit sizing by the Covestro method, with allowable strain
  for moulded resins and, by print direction, for 11 filaments (13 entries: two have dry and wet values) (#105, [docs/compliant.md](docs/compliant.md)).
- `cadagent.formulas`: closed-form engineering equations (beams and snap arms, torsion bars, coil springs, screw preload
  and thread strip, four-bar linkages, conduction and fan operating points), each with its SI units, validity limits
  and source; `catalogue()` lists them. A browser port drives the site's snap-arm explorer, tested against golden
  vectors from the Python (#146, [docs/formulas.md](docs/formulas.md)).
- `cad-agent holes`: the standard hole-clearance check, and [docs/common-issues.md](docs/common-issues.md), the index
  of recurring CAD mistakes and the checks that catch them (#88). Countersinks, chamfers and drill points are probed as
  cones and counted apart from cylindrical holes (#101).
- Release page: a browsable print page with thumbnails, print settings, CAD files and source (#87), pick-one groups
  and a one-build total (#89).
- Merge gates: `cad-gates/<base>/branch-flow`, `…/review` and `cad-gates/main/release` statuses, run from the default
  branch's (dev's) copy of the gates, on every push and every 15 minutes; tagged releases and the site deploy from `main` (#112).
- The website, [cad-agent.valpatel.com](https://cad-agent.valpatel.com), built from this repo: every page also as
  Markdown, plus `llms.txt` and `catalog.json` for agents (#108). Long pages get a page tree and outline (#123); every
  page has a diagram, chart, render or animation, and a test keeps it so (#124); animated figures are drawn by the code
  they explain (`tools/motion_figures.py`, #158); copy buttons never cover the code (#130).
- The catalogue as a gallery: demos first, then every entry by kind and by topic-tree area, with our own covers for
  the 50 outside projects and a JSON file per area for agents (`catalog/index.json`, `catalog/<area>.json`).
  `catalog.json` moves to schema 2, which only adds fields (#174). Every outside entry says what it does and which
  areas it serves (#173). If the gallery's script fails, the page falls back to its no-script form. Outside covers
  pick their family from the entry's kernel and tools first. Tool covers show a committed still of their result, and
  the design comparison's chart is drawn from `cad-agent compare --json`, which a `--check` keeps current (#189).
- The topic tree: [docs/vision.md](docs/vision.md) and [docs/areas.yaml](docs/areas.yaml) map six domains and 35
  areas, each at its maturity; a test keeps every page, command, skill and agent on the map (#148).
- [Manufacturing-process profiles](research/process-profiles.md): design limits for FDM, SLA, SLS, MJF, injection
  moulding, sheet metal and CNC in one table, every rule credited to its source, with charts (#162).
- `tools/cut_release.py`: cuts a release (dates the Unreleased entry, bumps the version) and checks the result against
  CI's release gate.
- `Study.render(..., vmax=)` draws at a fixed colour scale (MPa), so the renders of two variants compare by eye
  (before, each render ran from 0 to its own design stress). The colour bar says the scale is fixed and names the
  study's own design stress; stress above `vmax` takes the top colour, with an arrow when the study goes past it.
  `scale` remains the deformation exaggeration (#191).

- Site home page: Gyropup in 3D, its 58 parts exported from STEP by `cad-agent view`, packed small with
  `cadagent.publish.view.pack_view` and shown by the kit's new `<cad-model>` (`kit/model.js`); a reel of real outputs with
  the numbers they computed; and "where cad-agent fits", the tools we build on beside what cad-agent adds, each with
  its maturity from `docs/areas.yaml` (#179). The browser suite fails a page with more than one and a half screens of
  text and nothing to look at; the pages still over are listed with their issues and the list only shrinks.
- The README's animated hero, drawn from Gyropup's real CAD by `tools/readme_anim.py` (`cadagent.publish.anim`): the
  five-bar leg as hidden-line edges from its STEP, assembled, its stride solved from link lengths measured in the CAD,
  its gaps from the assembly gates' relation engine and its hip frame's FEA stress. One CSS-only SVG under 250 KB that
  GitHub shows in an `<img>`, with rules a test enforces ([docs/animated-figures.md](docs/animated-figures.md), #183).

**Changed**
- `src/cadagent/` is laid out by domain, as the topic tree ([docs/areas.yaml](docs/areas.yaml)) groups the work:
  `cadagent.mechanical` (`holes`, `fasteners`, `mcmaster`, `connectors`, `markings`, `compliant`, `motion_trace`),
  `cadagent.manufacturing` (`slicer`, `mesh3mf`), `cadagent.thermal` (`heatsink`), `cadagent.simulation` (`fea`, `cfd`,
  `topopt`, `explore`, `robot`, `simviz`, `simreport`), `cadagent.electrical` (`pcb`, `pcb_routing`), and for the
  practice domain `cadagent.review` (`gates`, `dossier`, `packet`, `evidence`) and `cadagent.publish` (`report`,
  `htmlreport`, `site`, `site_review`, `view`, `serve`, `release`, `render`, `dotsvg`). `project`, `cli`, `geometry`,
  `links`, `package` and `agentkit` stay at the top (#114; the table is in
  [docs/toolkit.md](docs/toolkit.md#package-layout-v050)). `cadagent.geometry` and `cadagent.review` were modules and
  are now packages at the same paths, unchanged for code that imports them. The old paths (`import cadagent.fea`,
  `from cadagent import mcmaster`, `cadagent.gates.motion`, ...) still work: each gives the same module object, so
  patching a name through it reaches the code, and so does `python -m` (`python -m cadagent.gates.run`, the v0.4 gate
  worker, runs `cadagent.review.gates.run`). The first import through an old path raises a `DeprecationWarning`
  naming the new path, reported at the line that imported it. **The old paths are removed in v0.7.0.**
  `tests/test_package_areas.py` keeps the packages and the tree in step: a module has one home, an `api:` line in its
  own domain, and a node that relies on another domain's module names it in the new optional `uses:` list.

**Fixed**
- Bambu slicer templates that include other templates are resolved before profiles are flattened (#93).
- Reproducible STEP files: `cadagent.geometry.export_step(shape, path)` writes the same bytes for the same model, with
  a fixed header date (`SOURCE_DATE_EPOCH` when set), the product named after the file and assembly links numbered
  within the file. `mcmaster normalise` writes `<PN>.norm.step` with it (#91).
- FEA printed materials take their modulus from the filament data sheet they cite: the lowest the sheet gives, across
  the layers (PLA 2060, PETG 1120, PETG-CF 1340, PAHT-CF 1820, TPU 7.4 MPa; the humid PA6-CF rows 2126 and 1042).
  Before, they were 31-147 % higher (TPU about 4x), so deflections read 24-60 % low (TPU 75 %). Each printed
  material now names its sheet (`source`), what E and the strength are taken from (`note`) and the print direction of
  E (`direction`); results repeat them in their assumptions line, and the viewer shows the direction. Densities follow
  the sheets, and `pa_cf` is named PAHT-CF, as its values always were (#125).

- The convergence chart shows the whole run and the monitored values, and no longer draws an empty solids panel
  (#155).
- The gates sweep no longer re-posts an unchanged status (#129).

**Docs and research**
- The README says what cad-agent is: agents that find, test, condense and credit the best published CAD techniques
  (#115). The toolkit page is now [Tools](docs/toolkit.md), the reference for the `cad-agent` command and the
  `cadagent` package; cad-agent itself is the whole toolkit (#178).
- Work-claim comments for sharing issues between agents (#102); the 2026-10-31 survey of agent toolkits, compliant
  mechanisms and FEA/process tools, and its catalogue entries (#109, #110). Corrected since: OrcaSlicer's own MCP server,
  slicing included, is in development on its `feature/mcp` branch, not yet in a release (#177).
- Lessons grouped by area (`lessons/process/`, `mechanical/`, `wiring/`, `electronics/`, `simulation/`, `review/`),
  with a diagram on every page (#133). The site redirects every old page for good (`tools/site-redirects.txt`).

**Projects must change:**
- `cad-agent check` and `cad-agent report` have a **Holes clear** row per part, and it fails ("hole check not run")
  until `cad-agent holes` has run on the current STEP or the part is listed in `cad.holes.skip` (#88). A project
  whose CI runs `build` then `check` exits 1 after the upgrade: run `cad-agent holes` (or `cad-agent all`, which now
  runs it) before `check` and `report`, then fix each hole with material inside or list it as an exception.
- Write STEP files with `cadagent.geometry.export_step` instead of `cadquery.exporters.export` (or a project's own
  header rewrite); each STEP file changes once, then stays the same across rebuilds (#91).
- Hole-check counts now separate holes from cones. A countersunk seat that used to count as a hole reads as a
  countersink, so recorded counts and findings can change on the next run.
- Links to the numbered lessons (`lessons/NN-….md`) still work through one-line stubs on GitHub until v0.6.0,
  which removes them: point such links at the new paths before then (the stubs name them).
- FEA deflections and stiffnesses with the printed materials change with the new moduli (#125): re-run deflection,
  stiffness, flexure-travel and clearance-under-load checks against their limits. Under the same forces, stresses and
  safety factors do not change (the PA6-CF rows' strengths are now computed exactly, 48.96 and 23.04 MPa instead of 49
  and 23). A force or a stress worked out at a given travel (a clip's retention, a flexure at full travel) falls with
  E, so re-check strength at travel too, with the in-plane modulus or a coupon.
- Densities change, so mass estimates move by 1.6–9.4 %, and `MATERIALS['pa_cf'].name` is now `'PAHT-CF (dry)'`
  (was `'PA6-CF'`), so report titles that print it change (#147).
- The CFD `read_results` `residuals` and `T_max_history` cover the whole run, not only the newest solve (#155).
- Slicer include trees that are invalid or ambiguous now fail instead of degrading (#93).
- The catalogue's `schema` value is now `cad-agent-catalog/2`: a reader that checks for `/1` must accept `/2` (#174).
- Move imports to the new package paths before v0.7.0 (#114). The old → new list:
  `python -c "from cadagent._moved import MOVED; print(*(f'cadagent.{o} -> {n}' for o, n in MOVED.items()), sep='\n')"`
  (an old package's submodules move with it: `cadagent.gates.motion` → `cadagent.review.gates.motion`).
- Run the gate worker, and any module run with `python -m`, at its new path: `python -m cadagent.review.gates.run`
  instead of `python -m cadagent.gates.run`. The old one still runs, with a warning, until v0.7.0.
- Type checkers and IDEs do not run import finders, so they report the old paths as missing modules at once (mypy:
  `Cannot find implementation or library stub for module named "cadagent.fea"`), though they still run. A
  type-checked project moves its imports when it upgrades.
- After pulling, a git checkout keeps `src/cadagent/compliant/`, `dossier/`, `explore/` and `gates/` holding only
  their `__pycache__`; `tests/test_package_layout.py` names each one. Delete them (this removes only caches and the
  folders they leave empty):
  `find src/cadagent -name __pycache__ -type d -prune -exec rm -rf {} + && find src/cadagent -type d -empty -delete`
- A test that replaces a *whole module* through its old path (`sys.modules["cadagent.report"] = fake`, or
  `cadagent.report = fake`) no longer reaches cad-agent's own code, which imports the new paths. Replace it at the new
  path: `monkeypatch.setitem(sys.modules, "cadagent.publish.report", fake)`.
- 44 of the 61 moved library files changed bytes: their imports, two paths to `webkit/`, and text that names module
  paths, including what they write into outputs (the slicer's work-folder marker, the CFD case headers, the
  simulation report's and the design comparison's footers, the gate worker's command line, the dossier lint's rule
  titles, a line on the site's review pages, and the geometry record's `hash` line, which gate inputs leave out, so
  verdicts stay current). A project that binds evidence to a library file's sha256 (`Path(cadagent.slicer.__file__)`)
  gets new hashes for those 44 from the move alone, and must measure again. The move leaves the other 17 byte for
  byte (`geometry`, `fasteners`, `connectors`, `markings`, `mcmaster`, `motion_trace`, `compliant/__init__`,
  `compliant/allowables`, `compliant/figures`, `mesh3mf`, `robot`, `pcb_routing`, `evidence`, `dossier/load`,
  `gates/verdict`, `view`, `serve`); `geometry` and `mcmaster` change in this release anyway, for `export_step` (#91),
  and so does `view`, for the home page's 3D model (`pack_view`, #182).
