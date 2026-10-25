# 06 — Enclosure features

### Put antenna bulkheads in the part that never comes off
- **Rule:** Mount panel connectors that carry cables to the internals (RP-SMA pigtails and the like) on the fixed base.
  Size the wall locally for the hardware stack-up: body, washer, nut and mating thread.
- **Incident:** There are four RP-SMA holes, Ø6.6, in the base side walls: WIFI 1/2 on the left and CELL 1/2 on the
  right, 92 mm apart on each side, above the vents and below the lid joint, with debossed labels. Each hole is
  spot-faced on the inside to a 2.5 mm wall, so a short-thread jack still leaves room for the washer, the nut and about
  4 mm for the antenna. The pigtails fit from inside, with the nut outside. The jack's thread length was left for the
  user to check against the parts they buy.
- **Check:** A ¼-inch rod passes all four holes. The jack models report no collisions. The wall thickness at the
  spot face plus the nut and washer must be less than the jack's thread length (a supplier check).
- **Source:** 2026-10-24T16:40, 17:10; `README.md` (Assembly step 7).

### Give recessed buttons a pin hole and a guide sleeve that clears installation
- **Rule:** For right-angle buttons behind a panel, add a pin hole with a lead-in and an inner guide sleeve. Stop the
  sleeve short of the board, so the panel still installs along its path.
- **Incident:** The reset and recovery switches sit 4.8 mm behind the rear plate. The plate has two Ø1.6 pin holes,
  angled at the opening, for a SIM tool or paper clip. A guide tube on the inside of each stops 0.35 mm short of the
  board edge, so the plate still slides straight down.
- **Check:** A 1 mm pin passes through both bores. A slide-in sweep check confirms that nothing is in the sleeve's
  path. The label stays provisional ("RST/REC") until the switch identity is confirmed (see 01).
- **Source:** 2026-10-24T16:39, 16:40, 16:53, 17:10.

### Build storage trays from the drive specs and make them stack in any order
- **Rule:** Take drive outlines and hole patterns from the official form-factor specs. Design the trays as identical
  interfaces, so any mix stacks in any order.
- **Incident:** P15 holds one 3.5 in drive (SFF-8301, all three 6-32 hole pairs) and is 32 mm tall. P16 holds two 2.5 in
  drives up to 15 mm (SFF-8201, M3 holes) and is 22 mm tall. They are clamped by M3 M-F hex standoffs (M3 × 30 for P15,
  M3 × 20 for P16), with heat-set inserts in the base column feet. Two of each tray add 108 mm, for 220 mm overall.
- **Check:** Every stack the user named passes in `storage-checks.json` (no plastic or hardware overlap, chimney open,
  bends OK). Hole positions are traceable to the spec table in `parameters.json` `drives`.
- **Source:** 2026-10-24T17:48; 2026-10-25T00:36, 01:23; `README.md` (Trays); `cad/parameters.json` (`basis`).

### Support thin drives that lack bottom holes
- **Rule:** Check which mounting holes the spec makes optional, and provide a holder that uses the holes that must be
  there.
- **Incident:** SFF-8201 makes bottom holes optional on drives 7 mm or thinner. P19 is a printed clip, four per drive.
  It takes an M3 × 5 through its wall into the drive's side hole (14.0 / 90.6 mm from the connector, 3.0 mm above the
  bottom) and an M3 × 6 from under the tray into a captive nut. It uses the tray's existing bottom-hole pattern, so no
  extra holes are needed.
- **Check:** The clip stacks report no `drive_clip_overlaps`. Side-screw penetration stays within 2.0 mm (see 04).
- **Source:** 2026-10-25T01:23; `cad/parameters.json` (`ssd_clip`, `bottom_holes_note`).

### Provide a mount plate and a blanking cap for the configurations
- **Rule:** Every configuration needs a defined bottom part and every unused opening needs a closure. Say which base to
  print for which use.
- **Incident:**
  - P1 is the base for desktop use and for every storage stack.
  - P1M is only for wall or robot mounting without storage.
  - With storage on a wall or robot, use P1 + trays + P17 (storage mount plate).
  - P18 (chimney cap) plugs the SATA floor opening when no storage is fitted.
- **Check:** A "Which base do I print?" table on the review site and in the README. Each configuration in the checks
  names its bottom part.
- **Source:** 2026-10-25T00:36, 01:36; `README.md` (Parts).

### Do the power budget before promising a device type
- **Rule:** Before supporting a device class, compare its supply rails and current draw with what the board actually
  provides (from the schematic), and design the extra power entry if one is needed.
- **Incident:** Each SATA power header supplies switched 5 V only, with a 2 A bead per port. One transistor, Q59 (CJ3407, marked "30V; 4.3A" on
  schematic sheet 27), switches both ports. The agent's rough figures were 0.5–1 A at 5 V for a 2.5 in SSD and about
  1 A at spin-up for a 2.5 in HDD. These are general estimates, not taken from a drive datasheet. A 3.5 in HDD also
  needs 12 V (about 2 A peak at spin-up, also an estimate). The 3.5 in tray therefore got an 8 mm "12V IN" hole and tie
  anchors for a 12 V-to-SATA adapter. The board input is 12–36 V, so DC-IN can be shared only if the supply is 12 V.
- **Check:** A power table per configuration: rail, source, per-port limit, worst-case draw (cite the drive datasheet
  once chosen).
- **Source:** 2026-10-25T01:30, 01:36; `README.md` (Power).
