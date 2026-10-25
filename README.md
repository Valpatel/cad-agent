# cad-agent (private)

One agent setup for hardware design on frontier models (Claude Code first, plus Codex, Cursor and Gemini). It covers
3D-printed parts, sheet metal, laser-cut parts, CNC, enclosures around real PCBs, and KiCad PCB design.

Rather than build another CAD framework, this repo combines what already exists. It works on three fronts:

1. **Adopt the best public tools.**
   - Track them in `upstreams/registry.yaml`, pinned by commit, with licence, install method and a security review.
   - Candidates include text-to-cad (MIT), the KiCad MCP servers, the build123d/CadQuery skills, and FreeCAD/OpenSCAD bridges.
   - Never copy code across licence boundaries: MIT, BSD or Apache-2.0 code may be incorporated with attribution, while
     GPL and AGPL tools run only as external programs.
2. **Mine the J501 design session.**
   - Lessons come only from the explicitly selected session: the J501 enclosure design session. Other session
     histories are out of scope.
   - We extract corrections, failed assumptions, checks that caught real bugs, and what the user actually asked for.
   - The miner runs locally (`mining/`). Output is scrubbed of personal data and cites its sources (session ID and date)
     in `lessons/`.
3. **Continuously integrate and test.**
   - `evals/` holds design tasks with machine-checked acceptance criteria: geometry validity, clearances, DFM rules,
     cable bend radius, fastener engagement, cost.
   - Each candidate tool or skill set is scored on the same tasks. A scheduled job checks the upstreams for changes and
     re-runs the evals.
   - Tools that win get adopted, the gaps go upstream as pull requests, and only what nobody else provides lives here
     in `skills/`.

## What we add (gaps found so far)
- Designing an enclosure around a real board: STEP and schematic ingestion, and clearance against thousands of vendor solids.
- Connector windows sized to the mating plugs, standoffs, and the cooler/heatsink stack.
- Cable routing with plug lengths and minimum bend radius.
- Fastener length from the assembly stack and thread engagement.
- An evidence-first review site: renders, PDF check sheets, STL/3MF/Bambu links, live check tables, and a progress log.
- Mechanical-PCB co-design: KiCad board to enclosure, and back again for the outline, holes and connectors.

## Layout
- `upstreams/`: registry of external tools, plus the sync and check scripts
- `mining/`: the session-history miner (local only)
- `lessons/`: rules mined from sessions, with provenance
- `knowledge/`: sourced design rules, materials and costs, in a citable form
- `skills/`: our skills; they fill gaps and do not duplicate the upstreams
- `evals/`: benchmark tasks and the scoring harness
- `research/`: landscape surveys
- `examples/`: worked examples (vendor files are fetched by URL and hash, never committed)

## Status
Phase 0. Repo created; the landscape survey and the session miner are in progress.
