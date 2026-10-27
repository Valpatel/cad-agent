# Review a PCB and enclosure together

1. Establish carrier revision, connector drawing, net mapping and populated circuits.
2. Generate/check KiCad; preserve separate ERC, DRC, connectivity and schematic parity evidence.
3. Audit exact BOM footprints and source stock; recheck after substitutions.
4. Export native PCB STEP and document its frame before using it for enclosure collision checks.
5. Model mating plugs, cable retention, fasteners and assembly access; export printable orientations and verify meshes/3MF readback.
6. Publish in-page schematic/layers/housing views using `cad.site.review`.
7. Bind current source/artifact hashes; package prototypes separately from production readiness.
8. Record physical qualification as pending until actual measured evidence exists.

## Differential buses and enclosure markings

Treat connectivity, pair routing and return continuity as separate evidence. Use native copper measurements, excluding branches from the main path; require protection pads in the signal path. Reserve the reference plane below pairs before routing auxiliary nets. `cadagent.pcb_routing` supplies layer-aware graph/path and paired-spacing measurements without requiring KiCad in the review server. A project must define tolerances and model limits; these routines do not solve impedance or certify a bus speed.

`cadagent.markings.PanelMarkings` describes text, strokes and circles once and produces both engraved CAD tools and an SVG proof. Label the connector gender and viewing direction; numbered pin diagrams must be checked against the actual mating face. Keep identification legible at the intended print scale and check remaining roof thickness and exported STEP/mesh.

For GitHub projects, do not create `.github/README.md` when the root README is the intended overview. Keep workflow documentation under `.github/workflows/README.md` and regression-check precedence.

Preserve the handedness of imported manufacturer/native STEP assemblies. Reorient using proper rotations/translations; a mirror may make a symmetric outline fit while reversing connector placement. Record the transform and check an asymmetric feature. Apply the same map to labels, mating envelopes and cable clamps.
