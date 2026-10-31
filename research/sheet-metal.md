# Sheet-metal design guidance: who says what (2026-10-31)

The first area sweep for Valpatel/cad-agent#118. It records the sheet-metal rules that named fabricators, hardware
makers, CAD vendors and practitioners publish, where they agree, where they disagree, and what that changes in
cad-agent. Sources are keys in [`references.yaml`](references.yaml), written `[ref:<id>]`.

**How this was checked.** Every source below was opened on 2026-10-31 and the section quoted was read. Two articles
in *The FABRICATOR* sit behind a bot check, so their Internet Archive copies were read (the registry gives the
snapshot). **[derived]** marks a number we calculated from cited data; the method is stated beside it. Copyrighted
guides are summarised, not copied: where a guide has a table, this note gives its range and points to it. Paid
standards are named by number and title only. Sources that could not be opened are listed in §14 and are not cited.

Symbols: T is the sheet thickness, R the inside bend radius, K the K-factor (neutral-axis position as a fraction of
T, measured from the inside face).

## Sources

| Who | What | Key |
|---|---|---|
| Protolabs | Sheet-metal design guidelines (web page) | [ref:protolabs-sheet-metal] |
| Protolabs Network (formerly Hubs) | Sheet-metal fabrication design guide | [ref:hubs-sheet-metal] |
| SendCutSend | Engineering specs JSON (178 materials), ordering guide, three design articles | [ref:sendcutsend-specs], [ref:sendcutsend-ordering-guide], [ref:sendcutsend-tab-slot], [ref:sendcutsend-bend-relief], [ref:sendcutsend-countersink] |
| OSH Cut | Bending design rules; 304 stainless material page | [ref:oshcut-bending-rules], [ref:oshcut-material-304] |
| Xometry | Manufacturing standards (default tolerances) | [ref:xometry-manufacturing-standards] |
| Century Tywood (fabricator) | *Manufacturing Reference for Sheet Metal Products* | [ref:century-tywood-sheet-metal-reference] |
| Boothroyd Dewhurst, Inc. | DFM design-review checklist | [ref:dfma-dfm-checklist] |
| **Gerald Davis** | *Design tips for sheet metal*, The FABRICATOR, 2001 | [ref:davis-2001-fabricator-design-tips] |
| **Steve Benson** | *Predicting the inside radius when bending with the press brake*, The FABRICATOR, 2015 | [ref:benson-2015-fabricator-inside-radius] |
| **Greg Paulsen** (Xometry) | *Tips for Making Sheet-Metal Parts*, Machine Design, 2017 | [ref:paulsen-2017-machine-design-sheet-metal] |
| **David Willson** (Fictiv) | *Tabs and Slots for Sheet Metal Part Design*, 2025 | [ref:fictiv-tabs-slots] |
| PennEngineering (PEM) | Self-clinching nut catalogue pages | [ref:pem-catalog-self-clinching-nuts] |
| Dassault Systèmes | SOLIDWORKS help: K-Factor | [ref:solidworks-k-factor] |
| PTC Onshape | Onshape help: Sheet Metal | [ref:onshape-sheet-metal] |
| **Shai Seger, Cerem Cem Aslan, Ulrich Brammer** and contributors | FreeCAD SheetMetal workbench | [ref:freecad-sheetmetal] |
| **Roger Maitland** and contributors | build123d `BuildSheet` and `unfold` (dev branch) | [ref:build123d-sheet-metal] |
| DIN | DIN 6935:2011-10 *Cold bending of flat rolled steel* (paid) | [ref:din-6935] |
| ISO | ISO 2768-1:1989 *General tolerances* (paid) | [ref:iso-2768-1] |

## 1. Minimum inside bend radius

| Rule | Who | Process |
|---|---|---|
| R ≥ T | Boothroyd Dewhurst checklist [ref:dfma-dfm-checklist]; Hubs [ref:hubs-sheet-metal]; Greg Paulsen [ref:paulsen-2017-machine-design-sheet-metal] | press brake, generic |
| R ≥ T for mild steel 0.02–0.13 in. Coining can reach nearly zero. Air bending is set by the V-die, "normally" 1–2T. Shops stock radii in 1/32 in steps | Gerald Davis [ref:davis-2001-fabricator-design-tips] | press brake |
| 3003 and 5052 bend about like mild steel; 6061 or 2024 may need 4–8T | Gerald Davis [ref:davis-2001-fabricator-design-tips] | press brake |
| An air-formed radius is a share of the die opening: 20–22 % for stainless, about 16 % for 60-KSI cold-rolled steel. A starting point, not exact | Steve Benson [ref:benson-2015-fabricator-inside-radius] | air bending |
| Standard radii 0.030, 0.060, 0.090, 0.120 in; use one radius for every bend | Protolabs [ref:protolabs-sheet-metal] | press brake |
| The radius is set by the tooling and cannot be chosen. For its metals, R/T runs from 0.36 (5052, 0.090 in) to 2.67 (304, 0.030 in) [derived from `bend_radius` / `thickness`] | SendCutSend [ref:sendcutsend-ordering-guide], [ref:sendcutsend-specs] | air bending |

**Agree.** R ≥ T is the common generic default, and everyone says the material and the tooling decide.

**Disagree.**
- SendCutSend's own tooling bends at R < T for half its 5052 SKUs, four of five brass and copper SKUs and seven of
  nine mild-steel SKUs, and bends thin stainless at R > T [derived]. A blanket "R ≥ T" check would fail parts a shop makes every day, and pass a thin stainless
  part drawn at R = T that the shop will make at 2.7T.
- R ≥ T is not safe for hard aluminium. Davis gives 4–8T for 6061 and 2024, and SendCutSend bends none of its
  twelve 6061 or three 7075 SKUs, only 5052 [derived from which SKUs have `bending_specs`].
- Benson's rule over-predicts SendCutSend's listed radii [derived]: 16 % of its 0.472 in die is 0.076 in, against
  0.045–0.063 in listed for mild steel on that die; 20–22 % of its 0.984 in die is 0.197–0.216 in, against
  0.130–0.187 in for stainless. Benson says himself the rule is only a first estimate.

## 2. K-factor and bend allowance

- **Definition.** K = t/T, with t the distance from the inside face to the neutral sheet. Bend allowance
  BA = π(R + K·T)·A/180 with A in degrees (SOLIDWORKS help [ref:solidworks-k-factor]). Hubs gives the same ratio
  [ref:hubs-sheet-metal].
- **Ranges.**
  - Hubs: 0.3–0.5, "average 0.4468". The page writes the K-factor in mm, but it is a ratio with no unit. Its chart
    gives K by forming method (air bending, bottoming, coining), material hardness and R/T band, from 0.33 to 0.50.
    It suggests 3–5 test bends for a real value [ref:hubs-sheet-metal].
  - OSH Cut: about 0.4 for soft metals such as aluminium, about 0.45 for steel and stainless [ref:oshcut-material-304].
  - SendCutSend: per SKU, 0.32–0.48 for metals and 0.33 for polycarbonate [ref:sendcutsend-specs].
- **Defaults in CAD.**
  - Onshape: 0.45, and 0.5 for rolled walls [ref:onshape-sheet-metal].
  - build123d `BuildSheet`: 0.5 [ref:build123d-sheet-metal].
  - FreeCAD SheetMetal: the README's example is 0.38 (ANSI). Its example table (R/T 1 → 0.38, 3 → 0.43, above →
    0.5) is the same as the Hubs row for air bending a medium material such as steel [ref:freecad-sheetmetal].
- **Two conventions.** FreeCAD SheetMetal accepts an "ANSI" or a "DIN" K-factor, and its unfolder halves a DIN
  value to get the ANSI one [ref:freecad-sheetmetal]. DIN 6935 is the German standard for cold bending flat steel
  [ref:din-6935]; its content was not read here. A K-factor without its convention can be off by a factor of two.

**Disagree.** Hubs and OSH Cut put K higher for harder metals. SendCutSend's measured values run the other way:
0.37–0.48 for 5052 against 0.34–0.38 for 304 [derived]. Use the shop's measured K, or a test bend, over any rule.

**Why it matters** [derived]: a 90° bend in 1.5 mm sheet at R = 1.5 mm has BA = 3.13 mm at K = 0.33 and 3.53 mm at
K = 0.5. That is 0.4 mm per bend, more than the cut tolerance, from the default alone.

## 3. Minimum flange length

| Rule | Who |
|---|---|
| ≥ 4T | Protolabs [ref:protolabs-sheet-metal]; Gerald Davis (shorter flanges get tool marks, need a backup strip, or must be milled after forming) [ref:davis-2001-fabricator-design-tips] |
| ≥ 3.5 × (T + R) | Century Tywood [ref:century-tywood-sheet-metal-reference] |
| "Bend height" ≥ 2T + R | Hubs [ref:hubs-sheet-metal] |
| "Minimum flange length met", no number | Boothroyd Dewhurst [ref:dfma-dfm-checklist] |
| Set by the die: a larger radius needs a larger die and more flange | OSH Cut [ref:oshcut-material-304]; SendCutSend [ref:sendcutsend-specs] |

SendCutSend's minimum flange after the bend is 0.286 in on 0.030–0.040 in stock (7–9.5T), about 3.8T on 0.125 in
5052, and 1.37–1.38 in on 0.250 in stock (5.5T) [derived]. It follows the die width (about 0.6–0.9 × the die), not
the thickness alone [derived].

**Disagree.** 4T is too short for thin sheet on SendCutSend's tooling, by up to 2.4×. Century Tywood's 3.5 × (T + R)
comes closer for thin stock (0.26 in against 0.286 in for 0.030 in mild steel) but is longer than SendCutSend needs
at 0.250 in [derived]. No generic rule fits every shop; the die decides.

## 4. Holes: size, edge distance, spacing, distance to a bend

**Minimum diameter.**
- ≥ T: Protolabs; Hubs (smaller is possible but not advised); Greg Paulsen (more for high-strength material);
  Century Tywood.
- Gerald Davis explains why: a punch thinner than about T bends or breaks, so smaller holes are laser-cut.
- Fibre laser shops go smaller. OSH Cut gives a minimum of 0.25T and a recommended 0.5T for 304
  [ref:oshcut-material-304]. SendCutSend's fibre-laser minimum holes are 0.22–0.6T, median 0.37T [derived from
  `min_hole_size` over 92 SKUs].

**Hole to edge.**
- Protolabs: 0.062 in for stock up to 0.036 in, else 0.125 in [ref:protolabs-sheet-metal].
- Century Tywood: 1/16 in for stock up to 1/32 in; thicker stock 2T but not under 1/8 in
  [ref:century-tywood-sheet-metal-reference].
- Boothroyd Dewhurst and Greg Paulsen: ≥ 2T.
- Hubs: ≥ T.
- SendCutSend (fibre laser): 0.22–0.67T per SKU, median 0.3T [derived].
- Protolabs and Century Tywood give nearly the same rule. The others differ by a factor of two.

**Hole to hole.** ≥ 2T (Hubs; Century Tywood for punched holes) against ≥ 6t (Greg Paulsen).

**Hole to bend.** Every source uses a different datum:

| Rule | Datum | Who |
|---|---|---|
| ≥ 2T + R | not stated | Boothroyd Dewhurst [ref:dfma-dfm-checklist] |
| ≥ 2T | from the start of the bend radius (tangent) | Hubs [ref:hubs-sheet-metal]; Gerald Davis, to the hole edge [ref:davis-2001-fabricator-design-tips] |
| ≥ 2.5t + r (holes), 4t + r (slots) | "from bend" | Greg Paulsen [ref:paulsen-2017-machine-design-sheet-metal] |
| ≥ 1.5 × (T + R) | inside dimension from the bend to the hole edge | Century Tywood [ref:century-tywood-sheet-metal-reference] |
| features within about 4T are at risk | "of a bend" | Protolabs [ref:protolabs-sheet-metal] |
| hardware 0.41–0.65 in centre to bend line by thickness; countersinks half the die width from the bend centre | bend line or bend centre | SendCutSend [ref:sendcutsend-specs], [ref:sendcutsend-countersink] |

The vendored text-to-cad DFM checklist already says to state the convention (tangent, centreline or edge) before
comparing [ref:text-to-cad]. These sources show why.

## 5. Bend relief and corner relief

| Rule | Who |
|---|---|
| Relief ≥ T + R | Gerald Davis [ref:davis-2001-fabricator-design-tips]; Century Tywood [ref:century-tywood-sheet-metal-reference] |
| Width ≥ T | Hubs [ref:hubs-sheet-metal]; Greg Paulsen, who adds length longer than R [ref:paulsen-2017-machine-design-sheet-metal] |
| Width ≥ T/2; depth ≥ T + R + 0.02 in from the bend line | SendCutSend [ref:sendcutsend-bend-relief] |
| Corner gap between flanges ≥ 0.015 in | SendCutSend [ref:sendcutsend-bend-relief] |
| Reliefs discussed, no numbers | Protolabs [ref:protolabs-sheet-metal] |

- SendCutSend's specs file agrees with its own article: its `bend_relief_depth` equals T + R + 0.020 in for the
  SKUs checked (0.030 in mild steel, 0.063 in 5052, 0.100 in 304) [derived].
- Davis adds two reasons for reliefs: a relief keeps the part from slipping in the tooling, and a relief cut with
  curves, not sharp inside corners, stops cracks from growing under vibration.

**Disagree** on width: T/2 (SendCutSend) against T (Hubs, Paulsen).

## 6. Hems, curls, jogs and countersinks

**Hems.**
- Protolabs: inside diameter ≥ T, return 6T [ref:protolabs-sheet-metal].
- Greg Paulsen: open hems, inside diameter ≥ t and return ≥ 4t; tear-drop hems, inside diameter ≥ t, opening ≥ ¼t
  and return ≥ 4t [ref:paulsen-2017-machine-design-sheet-metal].
- Steve Benson: a closed hem has zero radius, and its bend deduction is about 43 % of T "under perfect conditions",
  depending on the operator [ref:benson-2015-fabricator-inside-radius].
- Not every shop hems. SendCutSend bends to 120–130° at most [ref:sendcutsend-ordering-guide]. Xometry quotes hems
  and curls by hand [ref:xometry-manufacturing-standards].
- **Disagree** on the return: 6T (Protolabs) against 4t (Paulsen).

**Curls** (Greg Paulsen): outside radius ≥ 2t; holes at least the curl radius plus t away. Under the same heading the
article gives bends at least 6t plus the curl radius away.

**Jogs and offsets.**
- Protolabs: recommended offset 0.030 in, standard heights 0.060–0.312 in, height tolerance ±0.012 in.
- SendCutSend gives a minimum and maximum joggle per SKU, from 0.288 in on 0.030 in mild steel to 1.425 in on
  0.250 in stock [ref:sendcutsend-specs].

**Countersinks.**
- Protolabs: major diameter 0.090–0.500 in; 82, 90, 100 or 120°; formed countersinks +0.020/−0.010 in.
- Greg Paulsen: at least 8t apart, 4t from an edge, 3t from a bend. He also gives "maximum depth 3.5t", which cannot
  be right as printed, since a countersink cannot be deeper than the sheet. Do not use that number.
- SendCutSend: edge distance per SKU (0.781 in in its 0.25 in 5052 example), and half the die width from the bend
  centre [ref:sendcutsend-countersink]. It also forms dimples, with a size table per SKU [ref:sendcutsend-specs].

## 7. PEM and other self-clinching hardware

- **PEM catalogue, M3 nuts** [ref:pem-catalog-self-clinching-nuts]:
  - CLS-M3-1 and SP-M3-1: minimum sheet 1.00 mm, hole 4.22 +0.08 mm, hole centreline at least 4.8 mm from the edge.
    PEM's note: a larger edge distance lowers distortion.
  - Each type has a maximum sheet hardness. CLS (300-series stainless): HRB 70 / HB 125 or less. SP (A286):
    HRB 90 / HB 185 or less.
  - Use the longest shank that suits the sheet.
- **Cross-check** [derived]: SendCutSend lists 304 at HB 123 and 316 at HB 149 [ref:sendcutsend-specs]. A CLS nut
  sits at its limit in 304 sheet and is over it in 316. SP covers both. "Stainless nut for stainless sheet" is the
  wrong rule; read the hardness column.
- Protolabs and Century Tywood both say to follow the hardware maker's distances. SendCutSend gives hardware
  centre-to-edge and centre-to-bend distances per SKU.

## 8. Tabs, slots and notches

The word "tab" means two features here. Protolabs and Paulsen mean a finger in the cut outline. SendCutSend and
Fictiv mean a tab that locates in a slot in another part.

- **Outline tabs and notches.**
  - Protolabs: tab at least the larger of 2T and 0.126 in; notch at least the larger of T and 0.04 in; either no
    longer than 5× its width [ref:protolabs-sheet-metal].
  - Greg Paulsen gives the same numbers, plus notch spacing ≥ 1/8 in and a notch ≥ 3t + r from a bend.
- **Tab-and-slot joints.**
  - SendCutSend: slot width = tab width + 2 × the tab material's cut tolerance. Slot height = tab thickness + its
    plus thickness tolerance + 2 × the slot material's cut tolerance. Allow 0.002–0.005 in per powder-coated
    surface. Make tabs 0.5–0.75 of the mating part's depth [ref:sendcutsend-tab-slot]. The specs file gives a
    `tab_slot_tolerance` per SKU; most are 0.010–0.035 in [ref:sendcutsend-specs].
  - David Willson (Fictiv): tab width 1.0–1.5T (1.2–1.8T for a press fit) and length 1.0–1.2T. Clearance 0.05–0.1 mm
    per side for laser, 0.15–0.2 mm for waterjet. Slot corner radius 0.1–0.2 mm (laser) or 0.2–0.3 mm (waterjet).
    At least 2T from the sheet edge and 1.5T from the bend tangent; tabs 3–6T apart; 2–4 tabs per joint
    [ref:fictiv-tabs-slots].
- **Disagree** on tab length: 1.0–1.2T (Willson) against 0.5–0.75 of the mating depth (SendCutSend). They may
  measure different things; neither defines the datum.

## 9. Laser and waterjet: kerf and the smallest features

**Kerf.**
- Hubs: about 0.3 mm on average for laser, 0.5–1 mm for waterjet [ref:hubs-sheet-metal].
- OSH Cut: 0.006 in (0.15 mm) on 304 at every thickness [ref:oshcut-material-304].
- David Willson (Fictiv): 0.1–0.3 mm [ref:fictiv-tabs-slots].
- Compensate for mating parts. Hubs adds half the kerf to the inner part and takes half off the outer. Willson
  enlarges slots by half the kerf per side.
- **Disagree**: 0.15 mm against 0.3 mm. Ask the shop, or measure.

**Smallest features.**
- Laser corners: fillet T/2 (Hubs).
- OSH Cut, 304: minimum channel about 0.2T and wall about 0.33T [derived from its table].
- SendCutSend: minimum bridge per SKU.
- Protolabs: smallest flat part 0.25 × 0.25 in; smallest formed part 0.5 × 0.5 in.

## 10. Grain direction

- Gerald Davis: aluminium "tends to crack, particularly when bending parallel to the natural material grain"; the
  harder alloys need the larger radii in §1 [ref:davis-2001-fabricator-design-tips].
- Century Tywood: bend across the grain, or at 45° to it, whenever the part allows
  [ref:century-tywood-sheet-metal-reference].
- No source read here gives a number for how much larger the radius must be when bending with the grain. The
  candidate tables (Machinery's Handbook, the Aluminum Association) were not opened (§14).

## 11. Tolerances by process

| Process | Tolerance | Who |
|---|---|---|
| Cut, one surface | ±0.005 in under 0.13 in stock, ±0.015 in above | Protolabs |
| Cut, fibre laser | ±0.005 in | SendCutSend |
| Cut, CO2 laser and waterjet | ±0.009 in | SendCutSend |
| Cut, generic | ±0.010 in edge to edge | Xometry |
| Cut, by process | laser 0.05 mm, waterjet 0.2 mm, plasma 0.5 mm | Hubs |
| Cut, laser | ±0.1 mm | David Willson (Fictiv) |
| Bend to edge, bend to hole | ±0.010–0.025 in by thickness (Protolabs); ±0.015 in (Xometry) | Protolabs; Xometry |
| Across bends | ±0.015–0.025 in for 2 bends; ±0.030–0.040 in for 3 or more (Protolabs); ±0.030 in (Xometry) | Protolabs; Xometry |
| Bend angle | ±1° (Protolabs, Xometry, SendCutSend up to 24 in); ±2° over 24 in; ±5° polycarbonate (SendCutSend) | as listed |
| Flatness | grows with length; e.g. 0.005 in up to 1 in | Century Tywood |
| General tolerances | ISO 2768-1 applies to parts formed from sheet metal (scope only; content not read) | [ref:iso-2768-1] |

**Agree.** Protolabs, Xometry and SendCutSend all give bend angle ±1°. Tolerance grows with each bend between two features, so dimension
critical features from one flat face.

## 12. What this changes in cad-agent

Current cad-agent sheet-metal rules are planned checks S1–S8 in
[`fea-and-process-tools.md`](fea-and-process-tools.md) §5 and two rows in
[`compliant-mechanisms.md`](compliant-mechanisms.md) §7. Nothing in `src/` checks sheet metal yet.

| Planned rule | What the sources say | Change |
|---|---|---|
| S1 minimum flange ≥ 4T, cited [PL-SM][BD] | The Boothroyd Dewhurst checklist gives no number; only Protolabs and Davis say 4T. SendCutSend's tooling needs 7–9.5T on thin stock | Cite Protolabs and Davis only. Check against the chosen shop's table; use 4T only as a labelled fallback |
| S2 hole ≥ T | A punching rule (Davis). Fibre-laser shops go to about 0.25–0.5T | Keep as the generic default; say that it is conservative for laser |
| S3 hole to edge ≥ 2T, or Protolabs' absolute values | Hubs says T; Century Tywood agrees with Protolabs | Cite each value with its source |
| S4 hole to bend ≥ 2T + R | Five rules with different datums (§4) | Every check states its datum |
| S5 R ≥ T, cited [BD] | Fails SendCutSend's own 5052 radii; unsafe for 6061-T6 and 2024 (Davis: 4–8T) | Material-aware: a shop table, or a per-alloy minimum |
| S6 relief sizing "(u)" | Now sourced: SendCutSend T/2 and T + R + 0.5 mm; Davis and Century Tywood T + R; Hubs width T | Size from a cited rule and name it |
| S7 hem return ≥ 6T | Protolabs 6T, Paulsen 4t; some shops do not hem | Cite both; flag hems as shop-dependent |
| S8 tabs and notches | Agrees with Protolabs and Paulsen | Keep |

New check candidates:
- **K-factor provenance.** Every flat pattern names its K, where it came from (shop table, test bend, default) and
  its convention (ANSI or DIN). A bare default fails the review.
- **Shop profile.** Load a shop's table (radius, K, minimum flange, relief depth, hole limits) by SKU, the way
  text-to-cad's `sendcutsend` skill reads SendCutSend's JSON, and check against it before any generic rule.

## 13. Open-source tools: adopt or reference

From `gh api` and the READMEs on 2026-10-31. build123d and FreeCAD SheetMetal were checked twice (registry entries);
the other rows come from a separate survey on the same day and were not re-opened.

| Project | Licence | Activity | What it does | Use |
|---|---|---|---|---|
| [gumyr/build123d](https://github.com/gumyr/build123d) `BuildSheet`, `unfold`, `sheet_shells` | Apache-2.0 | dev branch, pushed 2026-10-30; not in v0.13.0 (2026-09-21) | Flange, bend, jog, hem, miter, bend and corner relief; unfold with a face map (bend line, angle, radius, up or down); `sheet_shells` takes a solid back to sheet surfaces. One K (default 0.5, ANSI-style); no K table, no DIN | **Adopt** on release: our kernel, pure OCP, permissive |
| [shaise/FreeCAD_SheetMetal](https://github.com/shaise/FreeCAD_SheetMetal) | LGPL-2.1 (from GPL-3 in 2024) | pushed 2026-10-17, 350★ | The most complete set: relief and hem types, K tables by R/T, ANSI and DIN, DXF and SVG export | **Reference**, or run as a separate `freecadcmd` process for a second flat pattern. Do not copy code into the MIT package |
| [andymai/brepjs](https://github.com/andymai/brepjs) `brepjs-sheetmetal` | Apache-2.0 | pushed 2026-10-31, "experimental" | Tab and slot, bend tables, unfold of imported solids, nesting, a JSON bend report, unfold-and-refold tests | **Reference** for features and test ideas (TypeScript) |
| [ManuelMRosa/SheetNest](https://github.com/ManuelMRosa/SheetNest) | MIT | pushed 2026-10-29 | Nesting; unfolds STEP to DXF through `freecadcmd` and the SheetMetal unfolder | **Reference** for the headless pattern |
| [KanadeK/bendseq](https://github.com/KanadeK/bendseq) | MIT | pushed 2026-08-30, 1★ | Press-brake bend-order search with collision checks | Reference (very young) |
| [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) `dfm`, `sendcutsend` skills | MIT | vendored | A sheet-metal review checklist; a SendCutSend preflight against its JSON. Its unfold proposal (#614) is still open | Already vendored; **reference** |
| [richiewillmott/FreeShape](https://github.com/richiewillmott/FreeShape) | GPL-3.0 | pushed 2026-10-30 | Desktop app: flanges, K-factor flat pattern, DXF | Skip (an app, GPL) |
| [alexneufeld/YouCanNotUnfold](https://github.com/alexneufeld/YouCanNotUnfold), [ulrich1a/sheet_ufo](https://github.com/ulrich1a/sheet_ufo) | LGPL-2.1; GPL-2.0+ | merged into SheetMetal; 2018 | Earlier FreeCAD unfolders | Skip (superseded) |

No open-source tool measures a sheet-metal part against DFM rules (hole to bend, flange length, radius against a
shop table). That checker, on top of build123d's face map and the cited rules above, is the real gap. The small
pieces cad-agent would add are a K table by R/T with an ANSI/DIN switch, and the shop-profile reader.

## 14. Not verified, and next steps

Not opened, so not cited (see `unverified` in [`references.yaml`](references.yaml)):
- Boothroyd, Dewhurst and Knight, *Product Design for Manufacture and Assembly* (print).
- *Machinery's Handbook* bend-allowance and minimum-radius tables (print).
- Xometry's sheet-metal design eBook (behind a form). Its rules here come from Greg Paulsen's article instead.
- Steve Benson's other columns: die width, minimum flange, 6061 (bot-blocked, no archive copy found).
- PEM's general design and installation bulletins (pemnet.com returned empty pages); only the catalogue pages were read.
- Standards content: DIN 6935, ISO 2768-1 (paid). The Aluminum Association bend-radius tables were not looked up.

Next:
- Read a waterjet maker's kerf and taper data, and an aluminium producer's bend-radius table by temper and grain.
- Turn §12 into check rows once #97 and #99 give parts a process and a shop.
- Re-fetch the SendCutSend JSON before relying on any value here; it changes.
