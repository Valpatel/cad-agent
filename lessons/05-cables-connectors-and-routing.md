# 05 — Cables, connectors and routing

### Route cables from the connector's real mating direction
- **Rule:** Start every route at the connector's actual board side and mating axis, and give the cable a defined entry
  and exit through the housing.
- **Incident:** The SATA receptacles and PH power headers are vertical connectors on the underside (see 01), so the
  plugs mate straight up from below. The route is as follows:
  - the leads drop through a base-floor opening directly beneath the connectors;
  - they continue down a chimney that lines up through every tray floor;
  - they turn into a cable gutter on the left side that runs the full depth of each tray;
  - they run straight into the drive plug.

  A printed cap (P18) closes the floor opening when there is no storage. This answered the user's "cables can be exposed
  but need entry/exit points".
- **Check:** For each stack, the chimney zones (`sata_plugs`, `sata_power_plugs`) report 0 mm³ blocked in
  `storage-checks.json`.
- **Source:** 2026-10-25T00:36, 00:39; `README.md` (Cable routing); `exports/storage-checks.json`.

### Model plug bodies and a straight lead before the first bend
- **Rule:** A cable cannot bend at the connector face. Model the rigid plug length and a straight lead-in at each end,
  then start the bend.
- **Incident:** The model uses SATA data plugs of 12 mm at the board and 11 mm at the drive, with an 8 mm straight lead.
  The PH power plug is 7 mm at the board, the drive power plug 11 mm, with a 6 mm straight lead. Lead diameters are
  modelled (2.2 mm data, 1.8 mm power, 2.0 mm for 12 V).
- **Check:** Each route's geometry includes plug and straight segments sized from `cables` in `parameters.json`.
- **Source:** 2026-10-25T01:23; `cad/parameters.json` (`cables`).

### When no standard exists, state the assumed bend radius and check every route
- **Rule:** If no published minimum bend radius exists, choose conservative values, label them as assumptions with
  their basis, and check each route against them in every configuration.
- **Incident:** The user asked: "What about the bend radius for the sata cables coming out of drives and so on?" No
  published SATA bend-radius standard was found. The basis notes that 3M sells a foldable SATA cable and that a general
  rule of thumb is at least 15× the cable thickness. The design values are 12 mm for data, 6 mm for the 4-wire PH power
  lead and 8 mm for 12 V. The tightest route is the 3.5 in data lead: 12.06 mm available against 12 mm required.
- **Check:** For every route in every stack, `max_uniform_bend_available_mm` ≥ `min_bend_required_mm`. Show the table on
  the review site.
- **Source:** 2026-10-25T00:58, 01:23; `exports/storage-checks.json` (`cables.basis`, `bend_radius`).

### Move the connector to make room for the bend; don't squeeze the cable
- **Rule:** When a route fails its bend radius, move the mating connector (or the device) to lengthen the run before
  the bend. Do not shrink the radius.
- **Incident:** After the bend checks were added, two configurations failed: "1 of each: 2.5 over 3.5, on plate" and "2 of each, on plate". In both, the rear SATA connector fed the 3.5 in drive, leaving only 9.1 mm of bend radius against the 12 mm required. The fix was the wiring rule: the front connector feeds the 3.5 in drive. An earlier round had already found routes with only 3.6–11.5 mm available.
  The drives were moved so their connector ends sit at X 48 (3.5 in) and X 62 (2.5 in) from the left outer face. The
  3.5 in drive also shifted rearward, clear of the standoff columns.
- **Check:** Re-run the bend and clearance checks for all stacks after the move. All seven stacks pass in
  `storage-checks.json`.
- **Source:** 2026-10-25T01:08, 01:23; `cad/parameters.json` (`connector_x`, `connector_x_note`).

### Write down the wiring rules the geometry forces
- **Rule:** If only one port-to-device pairing satisfies the routing limits, publish it as a wiring rule, written in
  terms the assembler can see.
- **Incident:** The 3.5 in drive must take the front SATA connector and a 2.5 in drive the rear one. The other way
  round, the turn into a 3.5 in drive's data plug allows only about a 9 mm bend. The rule is phrased by position because
  the STEP does not map J21/J24 to physical connectors.
- **Check:** The wiring rule appears in the parameters, the README, the cable diagram and the assembly steps, with the
  same wording.
- **Source:** 2026-10-25T01:23, 01:30; `cad/parameters.json` (`cables.wiring_rule`).

### Keep cable-tie anchors out of the cable paths
- **Rule:** Place tie anchors beside the route, against a wall, and include them in the cable collision check.
- **Incident:** As part of the bend-radius rework, the cable-tie anchors were moved against the tray wall, out of the
  cable paths (`gutter_anchors` at X 9). Before that, the cable-clearance check had caught the port-2 data lead to the second 2.5 in bay running through the gutter tie anchor at X 22, Y 90 (7.5 mm³). A flat SATA cable would thread under the anchor's bridge, but the round tube model could not.
- **Check:** `cable_route_hits` is empty for every stack in `storage-checks.json`.
- **Source:** 2026-10-25T01:23; `cad/parameters.json` (`gutter_anchors`); `exports/storage-checks.json`.
