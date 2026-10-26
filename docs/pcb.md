# PCB and assembly review workflow

cad-agent supports electronics and mechanical evidence in the same local project site. KiCad remains the electrical source of truth; cad-agent consumes its native reports and displays the files. The same embedded review groups work for a PCB, printed housing, robot assembly or any combination.

## Embedded review pattern

Set `cad.site.review: exports/review.json` in `cad-agent.yaml`:

```json
{"groups":[{"title":"Two-port adapter","summary":"Engineering prototype; fit testing pending","views":[{"title":"Schematic","kind":"pdf","file":"exports/2port/schematic.pdf"},{"title":"Top copper","kind":"svg","file":"exports/2port/pcb-top.svg"},{"title":"Housing","kind":"image","file":"preview/2port-open.png"}],"reports":[{"title":"Electrical CAD","file":"exports/2port/pcb-evidence.json"}],"downloads":[{"title":"PCB source","file":"hardware/2port/thor-2port.kicad_pcb"}]}]}
```

All drawings are embedded directly in the status page. Variants and views use reusable controls shipped in the web kit. `image`, `svg`, `pdf` and local `html` views are supported. Missing assets stay visible as pending, and missing reports never show a pass. Supply meaningful captions stating geometry provenance and qualification limits. The local server reloads after source changes, including KiCad, CSV and PDF files. Use `?live=0` to disable reload for an inspection.

## Source-bound electrical evidence

Run KiCad's full ERC and DRC, including schematic parity, immediately before binding the results. Use `--format json`; DRC reports must include `violations`, `unconnected_items` and `schematic_parity`. Do not use severity filters that omit warnings, exclude meaningful checks silently, or reuse old reports after changing a board. The adapter does not invoke KiCad and cannot prove that an arbitrary report was actually produced from an arbitrary source; the build orchestrator must run checks before the snapshot.

An evidence manifest supplies:

```json
{"reports":{"erc":"exports/erc.json","drc":"exports/drc.json"},"sources":["hardware/board.kicad_pcb","hardware/board.kicad_sch","hardware/board.kicad_pro","hardware/board.kicad_dru"],"release_gates":[{"id":"physical-fit","pass":false},{"id":"protection-tests","pass":false}]}
```

Run `cad-agent pcb-check hardware/evidence-manifest.json --output exports/pcb-evidence.json`. Both ERC and DRC plus nonempty source lists are required for a passing bundle. Missing/malformed reports, unknown violation severity, exclusions, unconnected items and parity findings fail closed. Changing a recorded source or report invalidates freshness in the site. Hash equality establishes the recorded snapshot, not physical correctness.

Design cards can reference `pcb_evidence: exports/pcb-evidence.json`; they show CAD status separately from open release gates and production qualification. Never turn fabrication, fit, transient protection, CAN timing, stock or supplier orientation gates green based only on clean CAD checks.

## JLC assembly files

`cadagent.pcb.check_jlc_files(bom, cpl)` checks required columns, exact C-codes, duplicate references, finite coordinates, layers and BOM/CPL set equality. Build separate explicit populations for SMT-only versus SMT+THT assembly, and keep manual/consigned components visible in another file. CSV parity does not verify part availability, library zero-angle convention, solder process, panelization or quoted pricing.

## Mechanical enclosure checks

Import the native PCB STEP in the documented coordinate frame, and also check the nominal PCB outline and holes. Include connector mating envelopes, screws, captive nuts, cable paths and tool access. A board-only collision proxy misses components. Use measured/manufacturer dimensions when available and flag generic geometry. For ribbon relief, model hard stops, actual jacket thickness, compliant pads and a physical pull-test target; a cable hole alone is not strain relief.

[Operational lessons](../.agents/SYMPTOM-INDEX.md) record pitfalls found in the Thor adapter project. The originating project is [pcb-agx-thor-can-breakout](https://github.com/mvalancy/pcb-agx-thor-can-breakout).
