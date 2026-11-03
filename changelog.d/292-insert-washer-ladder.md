**New**
- `cadagent.library.hardware`: ISO 7089, ISO 7090 and ISO 7093-1 washers (from bd_warehouse, with their least outside and thinnest thickness from the standards' tolerances), and the heads' bearing faces for ISO 4762, ISO 7380-1, ISO 14580 and ISO 1207, M2 to M6 (#292).
- `formulas.bearing_area` (the face under a head or washer, its hole widened by a chamfer) and `formulas.washer_bearing` (how far a steel washer spreads a clamp on printed plastic: a beam on an elastic bed, cut where it lifts off or bends too far) (#292).
- `inserts.check_joint` and `check_clamp` take `head` (socket, button or cheese), `head_washer`, `chamfer_mm` and, into an insert, `insert_washer` and `under_chamfer_mm`. When the printed part's bearing sets the torque, the result's `fixes` lists, in order, a larger head, a washer, a large washer and a limiter, each with the torque and preload it allows. `cad-agent inserts` prints a `fix:` line for each one named. The issue's M3 lid in PLA (0.20 N·m) gets ISO 7089 washers between the lid and the insert and under the head: 0.32 N·m and 821 N of preload, against 329 N (#292).

**Fixed**
- `docs/inserts.md` no longer says a limiter spreads a printed lid's load on an M3 insert's ring: the catalogue M3 limiters lower the torque and fail their own seating-force and press-fit rows. A limiter is now named only where every row of its own passes (#292).

**Projects must change**
- Re-run `cad-agent inserts` on M2, M2.5 and M3 joints without `head_mm`. Their head bearing row used to say "not checked". It now checks against the ISO 4762 socket head and may set a lower torque. Results gain the `fixes`, `head` keys and, with `insert_washer`, a `clamped on washer` row and `clamped_on_washer` cap (#292).
