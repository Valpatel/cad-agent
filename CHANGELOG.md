# Changelog

Every release of cad-agent: what projects using it gain and what they must change. Each PR adds its lines as a
fragment in [`changelog.d/`](changelog.d/README.md). Releasing is part of the development loop
([CONTRIBUTING.md](CONTRIBUTING.md#releases)): `tools/cut_release.py` folds the fragments into `## Unreleased` and
dates that entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check requires. Merging the release PR
(`dev` → `main`) tags the release and deploys the site, when the owner has set the `production` environment's deploy
secret; until then the site job warns and skips, and the site is deployed by hand from `main`. Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## Unreleased

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
