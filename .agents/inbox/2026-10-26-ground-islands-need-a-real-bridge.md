# Stitching vias must join distinct ground regions, not the same isolated island

2026-10-26: four-port native DRC reported one `unconnected_items` finding between ground zones even though all signal nets routed and nearby vias touched copper on both layers. Inspecting the filled polygon outlines showed a small bottom island under J1 and a separate front region. A via at (76.595, 52) joined those two isolated regions without joining the main return plane.

Correction: add the second bridge at (77.865, 56.72), where the bottom island overlaps the front region connected to the main plane. Trial Y56.5 violated CAN via spacing; Y56.9 violated the adjacent GPIO track clearance. The final location passes the conservative 0.2 mm copper and 0.45 mm hole-spacing rules. `kicad-cli pcb drc --format json --schematic-parity --refill-zones --save-board` then reports zero violations, zero unconnected items and zero parity issues. Current numeric evidence is in `exports/4port/drc.json`.

Rule: seeing a via touch both pours is insufficient. Inspect actual filled connected regions and rerun native connectivity after each stitch. A successful route process exit code is not electrical evidence. Do not disable the unconnected check or assume a zone-to-zone finding is cosmetic.

Limits: this proves CAD connectivity and clearance. Return inductance, EMC and physical assembly still need testing.
