# Engrave overlapping panel strokes in bounded operations

2026-10-26: a Thor lid probe subtracting an entire compound of overlapping text/stroke/cap tools ran for more than twelve minutes without completing. The process was stopped; no result was accepted. Applying the same artwork one item at a time, fusing only each polyline’s own stroke/cap solids, completed a flat-lid probe in 108.76 seconds with `isValid=True` and one solid. The production housing builds subsequently completed with valid printable parts.

Cause: the aggregate tool contained many intersecting solids, creating an unnecessarily expensive Boolean arrangement. This is an observed workload failure, not proof of a general kernel bug.

Rule: use `PanelMarkings.engrave` for the staged cuts. Keep `solids` for paint/reference geometry. Validate final solid count and exported mesh; a faster operation is not enough. The shared markings tests cover CAD validity and the SVG/geometry primitive contract.

Limits: text-heavy engraving remains expensive. Timing depends on the artwork and kernel; no fixed performance guarantee is implied.
