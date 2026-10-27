# Measure the remaining web and connect insert bosses to real supports

2026-10-26 evidence: `python -m pytest tests/test_fasteners.py -q` reports `3 passed`. The new wall-rib test verifies curved root edges, a valid single solid, positive intersection with a receiving wall and a single fused result. In the Thor design, arithmetic on the original parameters found a 1.35 mm outer seam wall and 1.8 mm clamp edge web despite nominal 3 mm walls and 9.2 mm insert bosses.

Cause: reviewing nominal dimensions missed the material removed by counterbores and the seam groove. A central blade supported the clamp deck but did not brace both insert bosses directly to the rear wall.

Corrective rule: compute the post-cut webs, add filleted ribs from each loaded boss to the floor/wall with positive overlap, and verify tool and cable paths after fusion. `cadagent.fasteners.filleted_wall_rib` and its geometry regression make this repeatable. See [enclosure guidance](../../lessons/06-enclosure-features.md).

Limits: the helper creates geometry, not a structural rating. Printed coupons, torque, pull-out, creep and service-cycle tests remain required for the chosen material and manufacturing process.

A subsequent lid rebuild exposed a separate typography defect: `AUX + PROTOTYPING INSIDE` in DejaVu Sans bold at 2.2 mm contains a 0.0000426 mm³ overlap between two glyph solids (at 0.6 mm extrusion). Cutting the raw glyph compound yielded a non-watertight STL even though the lettering looked plausible. The new `test_kerned_bold_letters_export_as_a_watertight_engraving` failed before the correction with `GeometryError: non-watertight STL`. The engraver now fuses each text item's glyphs, as it already did for a line's overlapping stroke caps, before the boolean cut. Keep unions bounded to an individual drawing item rather than one large compound for an entire panel. Check the printable mesh, not just BREP appearance.
