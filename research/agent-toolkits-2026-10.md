# Agent toolkits for mechanical CAD, DFM/DFA and FEA: refresh since 2026-10-24 (checked 2026-10-31)

For Valpatel/cad-agent #96 (landscape refresh) and #94 (compliant-mechanism engineer). Extends `research/landscape.md`
(2026-10-24); it does not repeat the KiCad or benchmark sections.

**Method.** Licence, stars, created and pushed dates and commit counts come from `gh api repos/OWNER/REPO` on
2026-10-31. Capabilities come from each README, manifest or source file as read on that day. Candidates came from `gh
search repos … --created >=2026-10-15`, `gh search code "snap-fit filename:SKILL.md"` and web search. **(s)** means a
search snippet only. **(u)** means unverified. **Nothing was installed or run.** Stars below 20 mean "new, unproven",
not "bad".

## 1. Changes to projects already in landscape.md

| Project | Change since 2026-10-24 | Effect on our recommendation |
|---|---|---|
| [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) | **v0.8.0 (2026-10-27) → v0.8.4 (2026-10-30)**. PR #568: the "xbf engine" replaces the 0.7 file pipeline with warm workers and a `Document` API. The migration guide says "no authoring compatibility layer… no shims, no aliases… no codemod" ([migrating-0.7-to-0.8.md](https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.7-to-0.8.md)). The plugin now pins `cadgen==0.8.4` ([claude.mcp.json](https://github.com/earthtojake/text-to-cad/blob/main/claude.mcp.json)). Telemetry is **still on by default** once cadgen has shown its notice; `DO_NOT_TRACK=1` or `CADGEN_TELEMETRY=0` turn it off ([cli/telemetry.py](https://github.com/earthtojake/text-to-cad/blob/main/packages/cadgen/src/cadgen/cli/telemetry.py)). The PCB PR #518 was **closed unmerged** on 10-28. Issue #626 (large-STEP viewer memory) was closed as completed on 10-28. The sheet-metal unfold proposal #614 is still open | Still adopt, but **pin 0.7.26 or 0.8.4 deliberately**. 0.7 scripts break on 0.8. Re-test the viewer with the J501 STEP. The PCB-to-enclosure path via text-to-cad is gone for now |
| [gumyr/build123d](https://github.com/gumyr/build123d) | `BuildSheet` sheet metal is on the dev branch: `flange`, `bend`, `corner_relief`, `bend_relief`, `hem`, `jog`, `miter`, `thicken`, and **`unfold`** to a flat pattern from thickness, K-factor and bend radius ([docs/sheet_metal](https://github.com/gumyr/build123d/tree/dev/docs/sheet_metal)). First commit 2026-07-21, latest 2026-10-21. It is **not in v0.13.0** (2026-09-21): the file 404s at that tag | Watch; plan to adopt when released. It covers text-to-cad #614 and our sheet-metal checks |
| [jdilla1277/agentcad](https://github.com/jdilla1277/agentcad) | v0.7.1 (2026-10-30), comments in the live viewer; 191★ | No change |
| [KittyCAD/mcp](https://github.com/KittyCAD/mcp) | v0.33.0 (2026-10-30) | No change (closed cloud engine) |
| [pzfreo/build123d-mcp](https://github.com/pzfreo/build123d-mcp) | No release since v0.3.91 (2026-10-15) | No change |

## 2. New, or missing from landscape.md

### 2a. Slicers (process-aware loop)

| Project | Licence | Activity | What it does | Security | Rec. |
|---|---|---|---|---|---|
| **OrcaSlicer 2.5.0 built-in MCP server + Design tab** ([v2.5.0-beta](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.5.0-beta), 2026-10-27; [`McpControl.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/slic3r/GUI/CAD/McpControl.cpp)) | AGPL-3.0 | Official project; OCCT 8.0.1; kernel tests in CI ([scripts/CAD/README.md](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/scripts/CAD/README.md)) | Turned on under Preferences › General › AI features › MCP server. Loads, arranges and slices models, sets presets, supports and modifiers, runs calibration, and models parts in a parametric Design (CAD) tab | Server "accepts connections from that computer only" ([PRIVACY.md](https://github.com/OrcaSlicer/orcaslicer-mcp-skills/blob/main/PRIVACY.md)). Needs a running GUI; the GUI checks need OpenGL. Beta | **Watch** until 2.5.0 is stable, then **adopt as an external process** (AGPL: never link). It could replace our flattened-profile Bambu CLI for slice evidence |
| [OrcaSlicer/orcaslicer-mcp-skills](https://github.com/OrcaSlicer/orcaslicer-mcp-skills) | AGPL-3.0 | Created 2026-10-29, 5 commits, official org | CC and Codex plugin: one SKILL.md and references (actions, settings, supports, calibration, cad, output) | No code, no network; plugin only ([PRIVACY.md](https://github.com/OrcaSlicer/orcaslicer-mcp-skills/blob/main/PRIVACY.md)) | **Adopt as a plugin** with Orca 2.5. Do not copy its text into our MIT repo (AGPL) |
| [MaxEllis/orcaslicer-mcp](https://github.com/MaxEllis/orcaslicer-mcp) | AGPL-3.0 | 86★, v0.1.17 (10-12) | Third-party Orca MCP | — | Skip; the built-in server supersedes it |

### 2b. build123d / CadQuery agent toolkits (nearest to cad-agent)

| Project | Licence | Activity | What it does on our tasks | Security | Rec. |
|---|---|---|---|---|---|
| [KD5RYN/b123d-print](https://github.com/KD5RYN/b123d-print) | MIT | Created 2026-10-17; at least 100 commits; PyPI; docs site; CI; 2★; one maintainer | MCP + CLI + CC plugin. `check` runs: valid, overlap, overhang (bridge vs cantilever), bridge length, wall/thin (knife edges), holes (round-top horizontal holes sag), bed-edge fillet, **tip-over** (Orca auto-brim formula), **gap/pip_clearance** for print-in-place, fit, probe, mate/align ([checks.md](https://github.com/KD5RYN/b123d-print/blob/main/docs/using/checks.md)). `suggest_orientation` ([orient.py](https://github.com/KD5RYN/b123d-print/blob/main/src/b123d_print/orient.py)). Examples: flip hinge, detent, overhang/bridge coupon | `.mcp.json` pins `b123d-print==0.3.2` via `uvx`; SECURITY.md (it runs AI-written code and can serve several users over HTTP/SSH); no telemetry hits in code search | **Vendor ideas / borrow checks** (MIT): tip-over, round-top hole, bed-edge fillet, pip-gap. Watch for maturity |
| [ballerabdude/agent-cad-works](https://github.com/ballerabdude/agent-cad-works) | Apache-2.0 | Created 2026-10-26, 4 commits, 1★ | build123d motion sweep for collisions, single watertight solid, nothing printing in mid-air, OrcaSlicer times, fit against vendor STEP, BOM, FreeCAD exploded views, Blender renders; CC plugin; 16 tests | `uv sync` pinned environment | **Watch**; it overlaps cad-agent almost one for one. Compare its gates with ours |
| [gjaloyan/print3d-designer](https://github.com/gjaloyan/print3d-designer) | MIT | Created 2026-10-28, 13 commits | Skill: measures a reference picture, builds from tested shapes, silhouette IoU ≥ 0.92 per view, slices with the user's presets, **reads the G-code back layer by layer** | — | Watch; G-code readback is a good evidence idea |
| [SiddhuYen/eitri](https://github.com/SiddhuYen/eitri) | NOASSERTION (no standard LICENSE found) | 72 commits since 10-18 | Local agent: build123d, geometry report (holes, thinnest wall, knife edges, clearances), browser editor | — | Skip code (licence unclear); ideas only |
| [pzfreo/step-diff-demo](https://github.com/pzfreo/step-diff-demo) + [pzfreo/specify-core](https://github.com/pzfreo/specify-core) | Apache-2.0 | 16★; specify-core-rust 0.1.5 (2026-10-31) | A STEP diff comment on every PR: named feature changes ("depth 11 → 13"), before/after picture, volume/area/bbox, and manufacturing answers carried to the new revision | GitHub Action | **Adopt candidate** for the review packet (#97 coverage, PR reviews). Trial on one product repo |
| [naman113/Designstudio](https://github.com/naman113/Designstudio) ("Buildcore") | MIT | 8★, 3 commits | STEP → auto-dimensioned PDF drawings, grouped BOM, GLB viewer, parts catalogue (Docker) | Docker compose, local port 8800 | Watch |
| [heartland-eng/bd_hardware](https://github.com/heartland-eng/bd_hardware) | **none** | 1 commit, README only | "Function-first hardware feature library for build123d … snap fits" | — | Skip (no code, no licence) |

### 2c. Vendor MCP servers missing from landscape.md (closed CAD)

| Server | Status | Rec. |
|---|---|---|
| Autodesk **Fusion MCP** (local; Fusion must be running) and **Fusion Data MCP** (cloud) | Announced around 2026-04 ([engineering.com](https://www.engineering.com/autodesk-announces-fusion-mcp-servers-and-more-ai-updates/); [Autodesk help](https://help.autodesk.com/view/fusion360/ENU/?guid=FMCP-OVERVIEW)) | Skip (closed; no Linux Fusion) |
| Autodesk **Fusion Compute MCP** | Public beta, cloud-hosted, no local Fusion needed (s) ([blog](https://www.autodesk.com/products/fusion-360/blog/fusion-compute-mcp/); the page returned 403 to fetch) | Watch |
| PTC **Onshape FeatureScript MCP** | Launched 2026-08-13 via Onshape Labs / App Store ([press release](https://www.placera.se/pressmeddelanden/ptc-ptc-advances-leadership-in-ai-driven-design-with-launch-of-onshape-featurescript-mcp-server-20260813)) (s) | Skip (SaaS) |
| SolidWorks community MCPs, e.g. [soheil-mp/solidworks-mcp](https://github.com/soheil-mp/solidworks-mcp) (MIT, 10★, created 10-23) | Windows-only | Skip |

### 2d. FEA / simulation agents

| Project | Licence | Activity | What it does | Security | Rec. |
|---|---|---|---|---|---|
| [novasolver/novasolver-studio](https://github.com/novasolver/novasolver-studio) | GPL-3.0 | Created 2026-10-25, at least 100 commits | Local CAE with an MCP server: CalculiX structural/thermal, OpenFOAM, and a built-in quadratic-tet solver. Every result passes **ran → converged → verified** gates (Roache GCI mesh convergence; closed-form templates). The README lists nonlinear (plasticity, large deformation), and contact (mortar, tied) plus fatigue "0.7" with a Hertz check ([README](https://github.com/novasolver/novasolver-studio)) | "No account, no upload, no telemetry"; Windows download; browser demo | **Watch**; run only as an external process (GPL). **Borrow the 3-gate idea** for `cadagent.sim.fea` |
| [WifiLast/freecad-mcp](https://github.com/WifiLast/freecad-mcp) | **none** | 2 commits (10-17) | FreeCAD FEM + gmsh + CalculiX statics; SIMP topology optimisation keeping mounting faces exact; dimension optimisation | **Binds `0.0.0.0:2022` by default** (streamable HTTP) | Skip |
| [V0v1kkk/freecad-engineering](https://github.com/V0v1kkk/freecad-engineering) | MIT | 3★, 2026-08 | Skills: `fdm-structural-review` (cites ASTM F3489/F3529, ISO; a material-profile validator script), `mechanical-strength-review`, `freecad-fem-check`, `mechanical-constraint-analysis` | — | **Vendor ideas** for the compliant-mechanism agent's evidence checklist |
| [n3r/AgentCAD](https://github.com/n3r/AgentCAD) `fem-workflow` skill | Apache-2.0 | 7★, 100 commits, macOS-first | gmsh + FEM workflow; says contact and nonlinearity are out of scope | — | Watch |
| [google/feabench](https://github.com/google/feabench) ([arXiv 2504.06260](https://arxiv.org/abs/2504.06260)) | Apache-2.0 | — | LLM agents on FEA problems; **needs a COMSOL licence**; no agent fully solved a problem (s) | — | Skip (COMSOL); cite as prior art |

### 2e. DFM / DFA

| Project | Licence | What it does | Rec. |
|---|---|---|---|
| [Vivek-Boora/dfm-agent](https://github.com/Vivek-Boora/dfm-agent) | **none** | STEP → optimal pull direction, faces classed core/cavity/undercut, draft against pull, parting-line loop, Three.js view | Ideas only, for the moulding checks (no licence) |
| [shayya/dfm-agent](https://github.com/shayya/dfm-agent) | none | Claude Agent SDK + pythonOCC; "day 4", topology counts only | Skip |
| Boothroyd Dewhurst [DFM Design Review Checklist](https://www.dfma.com/resources/pdf/dfm-design-review-checklist.pdf) | vendor PDF | Process prompts (§3 of fea-and-process-tools.md) | Cite; seed #97 |

### 2f. Published skills for compliant mechanisms and snap fits

**Yes, several exist**, all created in 2026, all prompt-only, and none with tested calculators:

| Skill | Licence | Activity | Content | Quality notes | Rec. |
|---|---|---|---|---|---|
| [static74/3dp-compliant-mechanisms](https://github.com/static74/3dp-compliant-mechanisms) | MIT | Created 2026-10-26, 0★ | FDM-only skill: selection table (grip-fin lids, snap-in tabs, S-bracket clips, forked detent, flexible T-slot, fluted pins, printed vs metal springs with capture rules, glue features); `fundamentals.md` with an orientation rule, a tagged allowable-strain table (`[derived]` from Bayer rules × Prusament/Polymaker yield), perimeter quantisation and a clearance table; 3 evals with graders; sources in `docs/research` (largely Slant 3D videos) | Every number is tagged with its provenance. Its allowables are about 2× our TDS-derived values for PETG (compliant-mechanisms.md §6). No code, no FEA | **Vendor selectively**: the selection table, eval cases and provenance-tag scheme, with attribution. Recompute the strain table |
| [n3r/AgentCAD](https://github.com/n3r/AgentCAD) `skills/snap-fits` | Apache-2.0 | 2026-08 | Cantilever and annular sizing, L ≥ 5t, taper rule, `material_strain.json` (per-material %, FDM derate 50–70 % in-plane), `cantilever_lid.py` | Some rows attributed to "Bayer 1998" (ABS 4–6 %) are not in the Bayer copy we read | Borrow the JSON-schema idea; check every value |
| [MP-AI-20/mechanical-engineering-skills](https://github.com/MP-AI-20/mechanical-engineering-skills) `snap-fits`, `design-for-assembly` | MIT | 10★, one push (2026-06-09), "647 skills" | Generic textbook prompts (y = εL²/1.5h, strain tables with ranges) | Looks bulk-generated; few primary citations | Skip |
| [dwragon/Fusion360SnapFitGenerator](https://github.com/dwragon/Fusion360SnapFitGenerator) | MPL-2.0 | Created 2026-10-24, v1.1.0 | Fusion add-in (not an agent skill): 5 snap types with strain and force calculation | — | Reference for parameters |
| [Kayforkind/skill-slice](https://github.com/Kayforkind/skill-slice) `3d-articulated-print-in-place` · [laurigates/mcu-tinkering-lab](https://github.com/laurigates/mcu-tinkering-lab) `printed-mechanism` · [ghbalf/freecad-ai](https://github.com/ghbalf/freecad-ai) `enclosure` (LGPL-2.1, 601★) | MIT / MIT / LGPL | — | Print-in-place articulation; servo mechanism clash sweep; snap-fit lid option (fixed 1 mm gap, 0.5 mm tab) | Shallow on snaps | Skip |

No published skill or agent:
- reproduces design-guide worked examples in tests;
- carries **process- and orientation-specific allowables from TDS** (beyond static74's derived table);
- covers flexure pivots (notch, CAFP, LET) or bistable beams; or
- links a snap design to large-deflection FEA or to a printed coupon result.

That is the gap cad-agent #94/#95 fills.

## 3. Security notes for anything we might run

- **Network binding.** WifiLast/freecad-mcp listens on all interfaces. b123d-print can serve over HTTP/SSH (stdio by
  default per its plugin config). Orca's server is local-only. text-to-cad's viewer has no auth on 127.0.0.1
  (landscape.md).
- **Arbitrary code.** Every code-CAD MCP (b123d-print, text-to-cad, agentcad, eitri) runs model scripts written by the
  agent. Run them in the project venv or a container, never with fleet credentials in the environment.
- **Supply chain.** Pin plugin versions. Both text-to-cad and b123d-print use `uvx` with an exact version but unhashed
  dependency ranges (landscape.md §2 for text-to-cad).
- **Telemetry.** text-to-cad is on by default (off with the env vars above). NovaSolver and Orca state none. The others
  were not audited.
- **Licences.** AGPL/GPL tools (Orca, NovaSolver, MaxEllis) run only as separate processes. The Orca skills plugin is
  AGPL text: install it, do not copy it. Repos without a licence (WifiLast, Vivek-Boora, bd_hardware, eitri) are ideas
  only.

## 4. Recommendations

| # | Item | Decision |
|---|---|---|
| 1 | OrcaSlicer 2.5 MCP + official skills | **Adopt when 2.5.0 is stable** (external process). Pilot now on a non-fleet workstation for slice evidence and supports |
| 2 | text-to-cad 0.8 | **Keep pinned**; decide 0.7.26 vs 0.8.4 explicitly and record it in `docs/toolkit.md`. Keep telemetry env vars |
| 3 | step-diff (specify-core) | **Trial** in one product repo's PRs (Apache-2.0) |
| 4 | b123d-print checks | **Borrow** tip-over, round-top hole, bed-edge fillet, print-in-place gap as cad-agent checks with seeded-defect fixtures (#97) |
| 5 | static74 skill | **Vendor selectively** (MIT, attribution) into `skills/compliant-mechanisms/references/` after recomputing allowables from TDS |
| 6 | NovaSolver Studio | **Watch**; copy the ran/converged/verified gate idea, not the code |
| 7 | build123d sheet metal | **Watch**, adopt on release |
| 8 | Fusion / Onshape / SolidWorks MCPs, FEABench | **Skip** (closed, non-Linux, or COMSOL) |
