# Rule inventory: where each rule comes from (2026-10-31)

The plan for citing every rule in `lessons/*.md` and `docs/common-issues.md` (Valpatel/cad-agent#118). This PR does
not edit those files. Each rule gets one proposed tag; the follow-up PR adds the tags and names the people or
organisations in the text.

## Tags

| Tag | Meaning |
|---|---|
| `[ref:<id>]` | The rule comes from, or is checked against, an outside source in [`references.yaml`](references.yaml) that was opened and read. |
| `[general]` | Common engineering knowledge, or geometry anyone can derive. No one person to credit. |
| `needs source` | The rule or its number came from somewhere, but no source was found or opened yet. The candidate column says where to look. |
| `[lesson]` | **Proposed fourth tag.** cad-agent's own finding from a real design session. Its evidence is the lesson's **Source** line (transcript time, project file or issue). There is no outside expert to credit, and tagging it `needs source` would leave a backlog that can never clear. |

`[lesson]` is a proposal: the issue's design has only `[ref:…]` and `[general]`. If the owner prefers two tags, the
`[lesson]` rows can be written `[general]` with a "cad-agent incident" note, but that hides where they came from.

Rules with an outside number inside an own lesson are split: the lesson is `[lesson]`, and the number gets its own
row (for example 03.8 and 05.4a). Row IDs are the lesson file number and heading order. Lesson 10's fourth heading,
*Thermal models of printed enclosures*, is a list of rules, so it appears only as 10.4a–f. Rows ci.0a–c are the
review steps at the top of `docs/common-issues.md`; ci.1–24 are its table rows in order.

## Counts

| | `[ref:…]` | `[general]` | `needs source` | `[lesson]` | Rows |
|---|---|---|---|---|---|
| `lessons/` (12 files, 92 headings) | 8 | 9 | 11 | 85 | 113 |
| `docs/common-issues.md` | 1 | 1 | 1 | 24 | 27 |
| **Total** | **9** | **10** | **12** | **109** | **140** |

Today 7 of the 140 rows name an outside source in the text, and only one links it (11.13). The others name it
without a link: SFF-8201 and SFF-8301 (04.6, 06.3, 06.4), DIN 7991 / ISO 10642 (04.4), the Bambu TDS (10.4a) and the
Phoenix datasheet (05.1a).

## lessons/01-verify-from-source.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 01.1 | Confirm a connector's board side and mating direction from datasheet photos; treat generic-height STEP bodies as placeholders | J501 transcript | `[lesson]` | |
| 01.2 | Read supply voltages off the rendered schematic, pin by pin, and trace the rail | J501 transcript | `[lesson]` | |
| 01.3 | Re-derive designators from the schematic; name by position when the model cannot tell | J501 transcript | `[lesson]` | |
| 01.4 | Infer an unknown thread from the vendor model's clearance holes, and say it is inferred | J501 transcript (user quote) | `[lesson]` | |
| 01.4a | Ø3.5 and Ø3.7 mm holes are M3 clearance holes (compare with a clearance-hole table) | none | `needs source` | ISO 273 [ref:iso-273] is the table (fine, medium, coarse series). Its values were not read, so the M3 mapping is not verified |
| 01.5 | Say what the sources do not tell you; keep the label provisional; ask one question | J501 transcript | `[lesson]` | |
| 01.6 | Use vendor-model bodies as proxies for missing data, and label them | J501 transcript | `[lesson]` | |
| 01.7 | Find parts by product name or refdes, never by size alone | J501 session record | `[lesson]` | |

## lessons/02-user-intent-and-requirements.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 02.1 | Record each mid-turn requirement verbatim and map it to a feature | J501 transcript | `[lesson]` | |
| 02.2 | Identify what a screw threads into before computing its length | J501 transcript | `[lesson]` | |
| 02.3 | Compute values the geometry sets; ask the user only for outside facts | J501 transcript | `[lesson]` | |
| 02.4 | Model every interface layer (pads, gaskets, washers) and recompute what it moves | J501 transcript | `[lesson]` | |
| 02.5 | Treat "doesn't block disassembly" as a hard requirement | J501 transcript | `[lesson]` | |
| 02.6 | Turn the user's configuration list into named test cases | J501 transcript | `[lesson]` | |
| 02.7 | Report constraints that undercut the request, with a recommendation | J501 transcript | `[lesson]` | |
| 02.8 | Make "show it on the review site" part of done | J501 transcript | `[lesson]` | |

## lessons/03-mechanical-design-rules.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 03.1 | Tie tall slender columns into the nearest wall (buttress, fillets) | J501 transcript | `[lesson]` | |
| 03.2 | When one weak feature is found, survey all similar ones | J501 transcript | `[lesson]` | |
| 03.3 | Fillet both ends of a stepped standoff with true radii, not chamfers | J501 transcript | `[lesson]` | The principle (fillets lower stress concentration) is general; DuPont gives a fillet of t/2 and at least 0.5 mm for moulded corners [ref:dupont-design-module-1], by analogy only |
| 03.4 | Size PCB landings to the pad; keep a margin to the nearest component | J501 transcript | `[lesson]` | |
| 03.5 | Envelope underside cards and relieve the supports around them | J501 transcript | `[lesson]` | |
| 03.6 | Size connector windows to the mating plug's overmould, not the receptacle | J501 transcript | `[lesson]` | |
| 03.6a | Typical overmould envelopes: USB-A 16.5 × 8.5, USB-C 13 × 8, HDMI 11.5 × 21.5 mm | "typical values" | `needs source` | USB Type-C specification (unverified), plug makers' drawings. Lesson 05 now says to model the real plug instead |
| 03.6b | Bridge webs thinner than 1.8 mm | project choice | `[lesson]` | |
| 03.7 | Make lead-ins self-supporting (45°, or narrowing as it builds); compare the overhang screen | none | `[ref:hubs-fdm-design]` | Protolabs Network: overhangs usually print up to 45° |
| 03.7a | Make horizontal holes teardrops with a 45° roof | none | `[general]` | Also b123d-print's check (research/fea-and-process-tools.md P3; not reopened) |
| 03.8 | Keep a grille's smallest opening below the 12 mm test finger | none | `needs source` | IEC 61032 [ref:iec-61032] and IEC 60529 [ref:iec-60529] name the test probes (paid; the probe size was not read). The lesson's measure is right for a round probe: the largest circle in a hex is its across-flats size |
| 03.8a | Do not claim an airflow gain without CFD or a test | J501 transcript | `[lesson]` | |
| 03.9 | Prefer a flush shell; let the lid capture the loose plates | J501 transcript | `[lesson]` | |
| 03.10 | Cut every hole last, after all added features | project issue; cad-agent#85 | `[lesson]` | |

## lessons/04-fasteners-and-assembly-access.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 04.1 | Check tool access for every fastener at the step where it goes in | J501 transcript | `[lesson]` | |
| 04.1a | A 5.5 mm nut driver is about 8 mm across | none | `needs source` | A tool maker's catalogue dimension |
| 04.1b | A 5.5 mm across-flats hex is 6.35 mm across corners | none | `[general]` | Geometry (AF / cos 30°) |
| 04.2 | Choose the assembly direction that keeps fasteners exposed | J501 transcript | `[lesson]` | |
| 04.3 | Screw length = head seat to thread start + engagement; check the thread depth available | user definition | `[general]` | |
| 04.3a | Engage about 8 threads (4 mm for M3) | user's statement | `needs source` | Engagement-length guidance; candidates are the UF design lab's "fewer than 5 threads" mistake (cited in research/fea-and-process-tools.md, not reopened) and Machinery's Handbook (unverified) |
| 04.4 | Move the head seat so a stock length gives the intended engagement; M3 × 35 to DIN 7991 / ISO 10642 | DIN 7991 / ISO 10642, no link | `[ref:iso-10642]` | The current ISO 10642 edition is 2026 (2019 withdrawn). DIN 7991 was not checked |
| 04.5 | Print coupons for inserts and countersinks before the big parts | J501 transcript | `[lesson]` | |
| 04.5a | M3 heat-set insert pilot 3.9 mm | none | `needs source` | The chosen insert's datasheet (record it with the `mcmaster-parts` skill) |
| 04.6 | Keep screw penetration into drives inside the SFF limits | SFF-8301 Rev 1.9, SFF-8201 Rev 3.4, no link | `[ref:sff-8301]` `[ref:sff-8201]` | Values match what was read: 2.39–3.56 mm (3.5 in); 2.00, 3.00 and 2.50 mm (2.5 in) |

## lessons/05-cables-connectors-and-routing.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 05.1 | Model every mating plug on the measured axis; derive the window from it; sweep it in | J501 port-fit fix | `[lesson]` | |
| 05.1a | The Phoenix MSTB 2,5/2-STF-5,08 plug is 15 mm tall and 20.17 mm wide | "Phoenix 1777989 datasheet", no link | `needs source` | phoenix-1777989 is unverified (the site returned 403 on 2026-10-31) |
| 05.1b | Take polarity from schematic net names; ask for a meter check when pin 1 is unclear | J501 transcript | `[lesson]` | |
| 05.2 | Route cables from the connector's real mating direction | J501 transcript | `[lesson]` | |
| 05.3 | Model the rigid plug and a straight lead before the first bend | J501 parameters | `[general]` | The lengths used are the project's own |
| 05.4 | With no published bend radius, state the assumed one and check every route | J501 transcript | `[lesson]` | |
| 05.4a | Rule of thumb: bend radius at least 15× the cable thickness | "a general rule of thumb" | `needs source` | A cable maker's bend-radius guidance (cable-routing sweep) |
| 05.5 | Move the connector to make room for the bend; don't shrink the radius | J501 transcript | `[lesson]` | |
| 05.6 | Publish the wiring rules the geometry forces, in words the assembler can see | J501 transcript | `[lesson]` | |
| 05.7 | Keep cable-tie anchors out of the cable paths | J501 transcript | `[lesson]` | |

## lessons/06-enclosure-features.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 06.1 | Put antenna bulkheads in the part that never comes off | J501 transcript | `[lesson]` | |
| 06.1a | RP-SMA bulkhead: Ø6.6 mm hole, ¼ in rod check, spot face to a 2.5 mm wall | none | `needs source` | The jack maker's panel cut-out drawing |
| 06.2 | Recessed buttons: a pin hole with a lead-in and a sleeve that stops short of the board | J501 transcript | `[lesson]` | |
| 06.3 | Take drive outlines and holes from the form-factor specs; make trays identical interfaces | SFF-8301, SFF-8201, no link | `[ref:sff-8301]` `[ref:sff-8201]` | |
| 06.4 | Support thin drives without bottom holes (optional at 7 mm) | SFF-8201, no link | `[ref:sff-8201]` | The side-hole positions 14.0 / 90.6 mm match A50 / A51 |
| 06.5 | Give every configuration a defined bottom part and every unused opening a closure | J501 transcript | `[lesson]` | |
| 06.6 | Do the power budget before promising a device type | J501 transcript | `[lesson]` | |
| 06.6a | Drive currents: 0.5–1 A (2.5 in SSD), about 1 A (2.5 in HDD spin-up), about 2 A at 12 V (3.5 in) | "general estimates" | `needs source` | The chosen drive's datasheet, as the lesson says |
| 06.7 | Connect insert bosses with filleted ribs and positive overlap; check the material left after cuts | Thor adapter iteration | `[lesson]` | |
| 06.8 | Fuse each text item's glyphs before cutting; judge by the exported mesh | Thor lid rebuild | `[lesson]` | |

## lessons/07-verification-and-evidence.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 07.1 | Collision-check everything and investigate every hit | J501 transcript | `[lesson]` | |
| 07.2 | Classify false positives with a named exclusion; never loosen the check | J501 transcript | `[lesson]` | |
| 07.3 | Check motions and tool sweeps, not just final positions | J501 transcript | `[lesson]` | |
| 07.4 | Never claim what was not tested; a check passes only on an explicit true | J501 transcript | `[lesson]` | |
| 07.5 | Re-run the pipeline after geometry changes; ignore stale notifications | J501 transcript | `[lesson]` | |
| 07.6 | Look at every render before showing it | J501 transcript | `[lesson]` | |
| 07.7 | Read generated files back with an independent parser (triangles, closed, volume within 0.1 %) | J501 transcript | `[lesson]` | |

## lessons/08-review-site-ux.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 08.1 | Keep a progress section (done, running, needs a decision) during long work | J501 transcript | `[lesson]` | |
| 08.2 | Give every printed part a thumbnail and STL, 3MF and STEP; say whether the slicer link was tested | J501 transcript | `[lesson]` | |
| 08.3 | Draw cable routes in 2D and 3D with a live check table | J501 transcript | `[lesson]` | |
| 08.4 | Put the source crop next to the decision it supports | J501 transcript | `[lesson]` | |
| 08.5 | Answer recurring "which part" questions with a table and a labelled render | J501 transcript | `[lesson]` | |
| 08.6 | Render close-ups of discussed features at stable file names | J501 transcript | `[lesson]` | |
| 08.7 | Keep the review URL stable across restarts | J501 transcript | `[lesson]` | |
| 08.8 | Use a moderate shared wheel-zoom sensitivity | CAN review follow-up | `[lesson]` | |

## lessons/09-agent-process.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 09.1 | Fold mid-turn messages into the plan and report on each | J501 transcript | `[lesson]` | |
| 09.2 | Post short status during long work and say what is stale | J501 transcript | `[lesson]` | |
| 09.3 | Ask before outward or irreversible actions | J501 transcript | `[lesson]` | |
| 09.4 | Check whether it already exists before building it | J501 transcript | `[lesson]` | |
| 09.5 | Mine and handle only the data the user selects | J501 transcript | `[lesson]` | |
| 09.6 | Diagnose desktop problems without disrupting the user's session | J501 transcript | `[lesson]` | |
| 09.7 | Hand long work to background jobs and agents; verify what comes back | J501 transcript | `[lesson]` | |
| 09.8 | Check facts directly instead of answering from memory | J501 transcript | `[lesson]` | |

## lessons/10-simulation-and-material.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 10.1 | Identify the exact bought part and datasheet before sizing around it | J501 thermal work | `[lesson]` | |
| 10.2 | Judge material savings on slicer grams with a named profile | J501 thermal work | `[lesson]` | |
| 10.2a | Bambu Studio's CLI needs flattened profiles and `from: system` | observed | `[lesson]` | |
| 10.3 | Re-check a thinner shell under load; report deflection, a 99.9th-percentile stress and the peak with its location | J501 FEA sweep | `[lesson]` | |
| 10.3a | One peak element at a notch is a mesh-dependent spike | none | `[general]` | FEA practice; a named source belongs to the FEA sweep |
| 10.4a | Check the plastic: PLA HDT 57 °C, PETG 69 °C | "Bambu TDS", no link | `[ref:bambu-pla-basic-tds]` `[ref:bambu-petg-basic-tds]` | These are the 0.45 MPa values. At 1.8 MPa the same sheets give 54 °C and 65 °C. The lesson should name the load |
| 10.4b | A fan is a curve, not a flow rate | none | `[general]` | |
| 10.4c | Use a hydrostatic (`p_rgh`) open boundary, not a uniform static pressure, for a buoyant room | PR review finding | `needs source` | The OpenFOAM boundary-condition documentation (FEA and CFD sweep) |
| 10.4d | Close the energy balance | none | `[general]` | |
| 10.4e | Model stacked fins as a porous block fitted to a plate-fin model | J501 thermal work | `[lesson]` | |
| 10.4f | Measure recirculation: air entering the fan against the room | J501 thermal work | `[lesson]` | |
| 10.5 | Steady CHT of a box in a room converges slowly; calibrate on local quantities | J501 thermal work | `[lesson]` | |
| 10.6 | Compute is shared: one heavy solver at a time | J501 thermal work | `[lesson]` | |

## lessons/11-pcb-evidence-and-review.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 11.1 | Keep ERC, DRC, unconnected items and schematic parity as separate results | CAN project note | `[lesson]` | |
| 11.2 | Generate ERC/DRC with `--severity-all`; accept each ignored check only by name | cad-agent PR #1 review | `[ref:kicad-cli-docs]` | The flag names were read. What a default run leaves out is the lesson's own finding |
| 11.3 | Re-run DRC on the saved bytes | CAN project note | `[lesson]` | |
| 11.4 | Check each report's declared hashes with one shared helper | CAN project note | `[lesson]` | |
| 11.5 | Measure routing geometry and the reference plane; DRC does not | CAN project note | `[general]` | Return-path continuity is standard signal-integrity practice; a named source belongs to the PCB sweep |
| 11.6 | Prove a stitching via joins the main plane, not another island | CAN project note | `[lesson]` | |
| 11.7 | A part substitution is a new design; identify by maker, MPN and supplier code | CAN project note | `[lesson]` | |
| 11.8 | Align a PCB STEP with a rotation (determinant +1), never a mirror | CAN project note | `[general]` | |
| 11.9 | Joined features need positive overlap; a valid BREP can still mesh badly | CAN project note | `[lesson]` | |
| 11.10 | Render final review images from the exported STEP | CAN project note | `[lesson]` | |
| 11.11 | Engrave panel artwork in bounded operations | CAN project note | `[lesson]` | |
| 11.12 | Package releases from the validated manifest, not a folder glob | CAN project note | `[lesson]` | |
| 11.13 | Don't let `.github/README.md` replace the repository overview | GitHub docs URL | `[ref:github-docs-about-readmes]` | The only rule in `lessons/` that links its outside source today |
| 11.14 | Keep CAD checks, physical fit and qualification as separate gates | CAN project playbook | `[lesson]` | |

## lessons/12-original-file-viewer.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| 12.1 | Parse the requested original's bytes and keep its identity during recovery | PR 63 / issue 62 | `[lesson]` | |
| 12.2 | Test the pinned parser's real behaviour; keep CPU work in a cancellable worker | PR 63 | `[lesson]` | |
| 12.3 | Inspect the built wheel for runtime, licence and source-reference files | PR 63 | `[lesson]` | |

## docs/common-issues.md

| # | Rule | Current citation | Proposed tag | Candidate source / note |
|---|---|---|---|---|
| ci.0a | Run `cad-agent all`; a failing, stale or missing row is a finding | — | `[lesson]` | |
| ci.0b | Walk the Review rows; say which were checked and how | — | `[lesson]` | |
| ci.0c | Add each new kind of mistake with the check that would catch it | — | `[lesson]` | |
| ci.1 | A feature added after the holes refills them | lesson 03 | `[lesson]` | |
| ci.2 | A rib or boss ends on air | lesson 03 | `[lesson]` | |
| ci.3 | Coplanar or flush unions; overlap joined features by 1–2 mm | none | `[lesson]` | Lesson 11.9 fixed a tangent boss with 0.2 mm overlap. The two numbers should agree, or say why they differ |
| ci.4 | Parts collide, or a clearance was checked against a bounding box | lesson 07 | `[lesson]` | |
| ci.5 | Walls or ribs too thin to print or carry load | lesson 10 | `[lesson]` | No threshold is stated. When one is added, cite it (FDM sweep) |
| ci.6 | Overhangs and unsupported bridges in the print orientation | lesson 03 | `[ref:hubs-fdm-design]` | |
| ci.7 | Engraved or embossed text not fused before cutting | lesson 06 | `[lesson]` | |
| ci.8 | Slender columns or insert bosses not tied into a wall | lesson 03 | `[lesson]` | |
| ci.9 | One weak feature fixed, its siblings left | lesson 03 | `[lesson]` | |
| ci.10 | The wrong bought part | lesson 10 | `[lesson]` | |
| ci.11 | A photo read in the wrong orientation, or a flow direction assumed | lesson 01 | `[lesson]` | |
| ci.12 | Connector windows from a bounding box, not the mating plug | lessons 03, 05 | `[lesson]` | |
| ci.13 | A vendor model used as if it were measured data | lesson 01 | `[lesson]` | |
| ci.14 | Vendor files committed or redistributed | agent workflow | `needs source` | Each vendor's terms of use (McMaster-Carr's CAD terms are paraphrased in `skills/mcmaster-parts` without a link) |
| ci.15 | Screw length from the wrong datum, or too little engagement | lesson 04 | `[lesson]` | Engagement length: see 04.3a |
| ci.16 | No tool access at the step where a fastener goes in | lesson 04 | `[lesson]` | |
| ci.17 | Inserts, countersinks or D-holes sized without a test print | lesson 04 | `[lesson]` | |
| ci.18 | Cable routes at an impossible bend radius, or tie anchors in the path | lesson 05 | `[lesson]` | Bend-radius values: see 05.4a |
| ci.19 | Stale evidence | lesson 07 | `[lesson]` | |
| ci.20 | Exports that change bytes on every rebuild | lesson 07 | `[lesson]` | |
| ci.21 | A simulation trusted before it converged, balanced and was calibrated | lesson 10 | `[general]` | Verification and validation practice; a named source belongs to the FEA sweep |
| ci.22 | Material savings judged on CAD volume | lesson 10 | `[lesson]` | |
| ci.23 | A render or report published without being looked at | lesson 07 | `[lesson]` | |
| ci.24 | Claims stronger than the evidence | lesson 07 | `[lesson]` | |

## Found while checking (outside this inventory's scope)

- **`src/cadagent/fea.py` printed-material moduli are above the TDS it cites.** The comment says the values are
  "rounded down from Bambu Lab's TDS figures". Against the V2.0 sheets read today:
  - PLA: 2700 MPa in code; TDS 2680 (X-Y) and 2160 (Z).
  - PETG: 1800 MPa; TDS 1460 and 1120.
  - PETG-CF: 2900 MPa; TDS 2460 and 1340.

  The strengths (25, 20, 22 MPa) are well below the Z values (35, 39, 38 MPa), so the strength checks are
  conservative. The stiffer moduli make deflections read low. The values may come from an older TDS version. It
  needs an issue, not a silent edit.
- **`docs/compliant.md`, `allowables.py` and the research note match** the Bambu and Polymaker sheets read today, row
  for row.
- **Sheet-metal check S1** in `research/fea-and-process-tools.md` credits the 4T minimum flange to Boothroyd
  Dewhurst too, but their checklist gives no number. See [`sheet-metal.md`](sheet-metal.md) §12 for that and S5.
