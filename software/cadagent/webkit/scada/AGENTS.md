# SCADA ownership and maintenance

Read the repository [AGENTS.md](https://github.com/Valpatel/cad-agent/blob/dev/AGENTS.md), this [owner map](README.md), and the affected
library's README before changing source. This is maintained cad-agent source;
do not edit or fetch the historical example repository as a build step.

- Keep `ui/` model-free and `sim/` headless. The host supplies the session, clock,
  commands, persistence, audio permission and navigation. Every view borrows that
  session; removing one view must not reset or destroy it.
- Equations are executable provider modules with explicit versions, schemas,
  units, owned state and independent tests. Preserve atomic binding swaps,
  snapshot validation and replay. A complete external solver can supply the
  same snapshot/subscription/command adapter without adopting the example kernel.
- Separate system topology, model configuration, snapshots and view state. Stable
  equipment/port IDs belong to documents; screen positions and display names do
  not establish identity. Record assumptions and source/measurement provenance.
- Contained diagrams pan/zoom with mouse, touch and keyboard and keep Fit visible.
  They have no canvas scrollbars. Preserve accessible inspector/form scrolling,
  focus, reduced motion and host-owned sound controls.
- Every equipment addition needs distinct artwork, meaningful operating/warning/
  failure states, metadata/schema coverage, a placeholder or explicit model limit,
  and an owned gallery preview. Do not advertise unsupported states or physics.
- Maintain source-owned generators under `tools/webkit/scada/` and tests under
  `tests/webkit/scada/`. Use those entrypoints; do not repair generated metadata,
  galleries, topology maps or provenance hashes by hand.
- Keep each library's `img/` with it. Minimal runtime profiles may omit galleries
  and tooling; this distribution decision must not scatter their source ownership.
- Preserve the MIT license in each package's LICENSE.txt and every third-party notice. New resources need provenance,
  declared rights and deterministic local inputs; no hidden remote runtime imports.
- Update affected folder maps and canonical agent skills, register user guides in
  `docs/areas.yaml`, and regenerate `docs/map.md` after changing the folder tree.

Run model/UI and generation checks from the SCADA tools package, plus affected
installed/offline and browser consumers. Follow the repository's independent
review, CI and release gates. Report exact evidence; simulation visuals do not
qualify a real system by themselves.
