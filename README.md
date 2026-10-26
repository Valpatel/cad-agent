# cad-agent

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

## Principles
- **Modular and flexible for any CAD project.** cad-agent knows nothing about a particular product. Projects plug in
  through files and config (`cad-agent.yaml`, parameter files, check JSONs, milestone and decision files). Anything
  specific to one product stays in that product's repository.
- **Cover the whole job:** CAD, BOM and cost, exploded diagrams and renders, decision records, standard design rules,
  checks with evidence, robot and simulation export, and a project site that shows all of it.
- **Bake in the best CAD agents in the world** rather than rebuild them: adopt, pin, review and test them, and only
  write what nobody else provides.

## What we add (gaps found so far)
- Designing an enclosure around a real board: STEP and schematic ingestion, and clearance against thousands of vendor solids.
- Connector windows sized to the mating plugs, standoffs, and the cooler/heatsink stack.
- Cable routing with plug lengths and minimum bend radius.
- Fastener length from the assembly stack and thread engagement.
- An evidence-first review site: renders, PDF check sheets, STL/3MF/Bambu links, live check tables, and a progress log.
- Mechanical-PCB co-design: KiCad board to enclosure, and back again for the outline, holes and connectors.

## Toolkit
`cad-agent` (Python package `cadagent` in `src/`) runs a CAD project's build steps and checks, writes and verifies
bed-centred 3MF files, and produces a standalone HTML review report and a review package. It never claims physical
fit. Install it with the CAD dependencies:

```bash
pip install -e ".[cad]"
cad-agent check --project path/to/cad-project
```

The project contract, the `cad-agent.yaml` format and every command are in [`docs/toolkit.md`](docs/toolkit.md).

**Stiffness and strength studies** (`pip install -e ".[cad,fea]"`): `cadagent.fea.Study` meshes a STEP or CadQuery
part with gmsh, solves linear elasticity with quadratic tetrahedra in scikit-fem, and reports deflection, stiffness
(linear or torsional), the design von Mises stress and a safety factor against a material table that includes
printed materials with layer-direction strengths. Faces are picked with selectors (`plane_at`, `cylinder_at`,
`in_box`, `near`). It is checked against a cantilever and a twisted shaft in `tests/test_fea.py` (within 3–6 %).

## Vendored tools
Six upstreams are vendored under `vendor/`, pinned by commit, and updated weekly through a reviewed, scanned and
sandboxed process (see `SECURITY.md` and `WEEKLY-UPDATE.md`): text-to-cad, kicad-happy and kicad-mcp-pro (MIT);
build123d-mcp, agentcad and bd_warehouse (Apache-2.0). text-to-cad's telemetry, update check and outbound API are
patched off. Licences and pins are listed in `THIRD_PARTY_NOTICES.md`.

## Layout
- `src/cadagent/`: the toolkit; `tests/` its tests; `docs/toolkit.md` its guide
- `vendor/`: vendored upstream code, with its manifest, patches, scan baselines and review reports
- `tools/`: `vendor_sync.py` (safe import and update) and `security_scan.py` (red-flag scan)
- `upstreams/`: registry of all surveyed tools, including those not vendored
- `mining/`: the session-history miner (local only)
- `lessons/`: rules mined from sessions, with provenance
- `knowledge/`: sourced design rules, materials and costs, in a citable form
- `skills/`: our skills; they fill gaps and do not duplicate the upstreams
- `evals/`: benchmark tasks and the scoring harness
- `research/`: landscape surveys
- `examples/`: worked examples (vendor files are fetched by URL and hash, never committed)

## Status
Phase 0. Repo created; the landscape survey and the session miner are in progress.
