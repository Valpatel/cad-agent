# Threaded inserts and compression limiters

A heat-set insert is a knurled brass sleeve melted into a hole in a printed part, so a machine screw has metal
threads to bite. A compression limiter is a metal tube through a clamped plastic part, so the screw's clamp goes
through metal and not through plastic that creeps. `cadagent.mechanical.inserts` designs the hole and the boss for
an insert, works out where the screw's clamp goes, holds it against the insert's pull-out, torque-out and thread, the
plastic under the head and the limiter, and says how much of the clamp the joint keeps. `cad-agent inserts` runs it
on every joint in a file. **The strengths are a shear model calibrated to published pull-out tests, so a result is a
starting point to test, not a rating. The coupon plan at the end says how to measure it.**

<img src="img/inserts/section.svg" alt="Section of a printed boss with a M3 heat-set insert (McMaster-Carr 94459A140): hole 4.20 mm, 6.7 mm deep, wall 2.7 mm" width="960" height="386">

## Check a joint

Declare each joint in a file and run the check. A joint with an `insert` is a screw into a heat-set insert. A joint
with a `thread` and no insert is a screw into metal or a nut that clamps printed plastic.

```yaml
# joints.yaml
defaults: {material: pla-bambu-basic}
joints:
  - {name: lid, insert: mcmaster-94459A140, boss_outside_mm: 9.5, head_mm: 7.0, clearance_mm: 3.4,
     clamped: {thickness_mm: 4.0}}
  - {name: bracket, thread: M4, thickness_mm: 6.0, head_mm: 7.0, clearance_mm: 4.5}
```

```text
$ cad-agent inserts joints.yaml --output result.json
WARN  lid: M3 94459A140 in Bambu PLA Basic, through-insert; tighten to at most 0.20 N m (clamped on insert)
      fix: an ISO 7089 washer between the part and the insert: at most 0.47 N m, 775 N preload (clamped on washer)
      fix: an ISO 7093-1 washer between the part and the insert: at most 0.63 N m, 1037 N preload (clamped on washer)
      warn: preload kept: the clamped plastic relaxes and takes the preload with it: ...
WARN  bracket: M4 clamping Bambu PLA Basic; tighten to at most 0.68 N m (head bearing)
      fix: an ISO 7089 washer under the head: at most 0.79 N m, 1648 N preload (head bearing)
      fix: an ISO 7093-1 washer under the head: at most 1.06 N m, 2223 N preload (head bearing)
      warn: preload kept: the clamped plastic relaxes and takes the preload with it: ...
```

It exits 1 when a joint fails, 2 when the file is wrong; a warning does not fail it. A `fix:` line lifts a limit
the printed part's bearing sets ([below](#heads-washers-and-what-lifts-the-clamp)). The JSON holds every row (value,
limit, verdict, reason), the capacities, torque ceilings and limits; its top-level `pass` is true unless a joint
fails, so a project's `cad: checks` row reads it as it is: `{id: inserts, title: Insert joints, file:
exports/inserts.json}` (`pass_key` defaults to `pass`). From Python:

```python
from cadagent.mechanical import inserts

inserts.hole_design(inserts.insert("mcmaster-94459A140"))      # 4.2 mm in CAD (the maker's 4.0 + 0.2), 6.7 mm deep
r = inserts.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, head_mm=7.0,
                        clearance_mm=3.4, clamped={"thickness_mm": 4.0})
r["verdict"], r["torque"]["allowed_nm"], r["torque"]["governed_by"]   # 'warn', 0.20, 'clamped_on_insert'
r["fixes"]["fix"]["what"], r["fixes"]["fix"]["allowed_nm"]       # 'an ISO 7089 washer between the...', 0.47
r["capacity"]["pull_out"]                                         # low 811, mid 1152, high 1394 N
inserts.check_clamp("M10", "pa6-cf20-polymaker-wet", 40.0, head_mm=20.0, clearance_mm=12.0, torque_nm=20.0,
                    limiter={"outside_mm": 18.0, "bore_mm": 12.0}, limiter_length_mm=39.8)
inserts.coupon_plan()                                             # what to print and measure
```

## The hole, by filament and nozzle

`inserts.printed_hole` sizes the hole for the filament and the nozzle you print with. `hole_design` and `check_joint`
use it when you give `line_mm`, `filler_pct`, `undersize_mm` (from a hole coupon) or `facets`, and on their own for a
fibre-filled filament. With none of these, the hole is the maker's plus 0.2 mm, as before.

```mermaid
flowchart TD
    M["the maker's hole"] --> F["+ filler:<br/>0.08 mm at 15 %,<br/>0.15 mm at 35 %"]
    F --> S["- 0.05 mm<br/>to pre-seat"]
    S --> A["the hole<br/>as printed"]
    A --> U{"undersize"}
    U -->|"your coupon"| C["its undersize"]
    U -->|"no coupon"| K["0.25 mm<br/>(CNC Kitchen 2026)"]
    C --> N["at least the<br/>nozzle's arc floor"]
    K --> N
    N --> G{"facets?"}
    G -->|"no"| H["the CAD hole"]
    G -->|"yes"| P["÷ cos(π/n):<br/>the flats on the hole"]
    P --> H
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class H out
```

```python
inserts.printed_hole(inserts.insert("mcmaster-94459A140"))                        # 4.20 mm, band 4.20-4.30
inserts.printed_hole(inserts.insert("mcmaster-94459A140"), "pa6-cf20-polymaker-dry", filler_pct=30)   # 4.33 mm
inserts.printed_hole(inserts.insert("mcmaster-94459A140"), undersize_mm=0.1)     # your coupon: 4.05 mm
inserts.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=7.2, line_mm=0.8)   # 1 perimeter: warn
```

Where the sources disagree, the range is kept and the one that governs is named.

<details>
<summary>Each number and where it comes from</summary>

- **As printed, the hole is the maker's less 0.05 mm,** so the insert pre-seats with slight resistance. CNC Kitchen's
  4.2 mm CAD hole printed 0.25 mm small, landing just under its 4.0 mm data-sheet hole. Drilled M3 holes lost most
  of their pull-out between 4.1 and 4.2 mm [ref:cnckitchen-heat-set-hole-size]. SPIROL agrees: a larger hole loses
  performance, and a smaller one stresses the plastic [ref:spirol-how-to-design-the-proper-hole-for-heat-ultrasonic].
- **Filled plastics take a larger hole:** +0.08 mm at 15 % glass or mineral filler, +0.15 mm at 35 % and over,
  interpolated between [ref:spirol-how-to-design-the-proper-hole-for-heat-ultrasonic]. SPIROL wrote this for moulded
  parts. A fibre-filled filament takes it by extension, because its fibres do not melt either. Neither data sheet in the
  table states its carbon-fibre content, so for those filaments the band widens by the whole 0 to 0.15 mm and the hole
  takes the low end. A hole too large loses pull-out fast, while one too small only seats harder. The check warns until
  you give `filler_pct` or print the coupon.
- **The printed hole's undersize** was 0.25 mm on CNC Kitchen's printer in 2026
  [ref:cnckitchen-heat-set-hole-size] and 0.1 mm on another in 2019 [ref:cnck-2019]. The range is kept and 0.25 mm is
  taken, because it is the measurement behind the pull-out tests. **Your coupon governs:** pass its undersize and the
  whole band moves with it. Hole sizes vary with material and tools [ref:e-z-lok-brochure-2026], and PETG can shrink a
  little after printing [ref:epfl-make-how-to-use-threaded-inserts-epfl-makerspace-wiki].
- **The nozzle sets a floor.** A track t wide, bent round a hole of diameter D, leaves it at least √(D² − t²). This
  is the RepRap wiki's arc balance [ref:reprap-arc-compensation], and the tests reproduce its table. Nophead found the
  real shrink larger [ref:nophead-polyholes], so the floor binds only for a wide track in a small hole, or under a
  coupon printed with a narrower one.
- **A coarse mesh shrinks the hole by cos(π/n).** Given `facets`, the circle is drawn at d / cos(π/n), so the flats
  land on the hole [ref:nophead-polyholes]. Nophead's polyhole, max(round(2 d), 3) sides, is reported beside it. It is
  untested with inserts, so the round hole governs.
- **The boss is whole perimeters of your line width.** Make the wall a multiple of the extrusion width, so it prints
  solid, with two or more perimeters [ref:lulzbot-tips-and-tricks-heat-set-inserts]. Stratasys's slicer sets four to
  six contours [ref:padt-adding-inserts-to-3d-printed-parts-hardware-tips]. SPIROL's at-least-the-metric-size governs,
  because only it has pull-out tests against wall loops. `boss_design` gives the solid outside for the line width, and
  `check_joint` with `line_mm` counts the whole perimeters that fit.
- **No chamfer, by default.** CNC Kitchen asks none for its inserts [ref:cnckitchen-heat-set-tips]. EPFL's wiki asks
  0.3 to 0.5 mm, and LulzBot asks a chamfer for the melt. The check draws none and leaves the choice to you.

</details>

## Where the clamp goes

The insert's height against the joint face decides what carries the screw's clamp. This is the first thing the
check works out, and it changes every limit after it.

<img src="img/inserts/clamp-paths.svg" alt="Three clamp paths for a heat-set insert: pulled into a shoulder (the shoulder carries the clamp), flush (the clamped part bears on the insert) and recessed (the screw jacks the insert out of the boss: the knurl carries the whole preload)" width="870" height="360">

- **Flush, or up to 0.13 mm proud** (PEM, SPIROL). The clamped part bears on the insert's end. The clamp goes through
  the brass, and the knurl carries only what pulls the parts apart. M3 in PLA Basic, clamping metal: tighten to at
  most **0.40 N·m**, set by the insert's end face: the ring round the clamped part's hole takes nearly all the clamp,
  held to brass's 124 MPa. A printed clamped part sits on that same ring, so its plastic sets a lower limit (the lid
  above: 0.20 N·m). That limit puts the whole clamp on the ring, the cautious bound: once the plastic yields, the
  boss face takes some, which the check does not size. A metal washer between the printed part and the insert
  (not under the head) spreads it. A catalogue limiter does not lift it for M3: see the next section.
- **Recessed, even by 0.05 mm.** The screw pulls the insert towards the head until the gap closes. The knurl
  carries the whole preload, so the same joint 0.2 mm recessed may take only **0.13 N·m**.
- **A clamped part whose hole is as wide as the insert** bears on the plastic round it. That jacks the insert out
  too, and the check says so.
- **Pressed in from the far side**, the insert is pulled into the boss in front of it, and that shoulder must not
  punch out.
- **The screw's tip.** Past the floor of a blind hole the screw bottoms and jacks the insert out. Past the insert's
  end it reaches the room left for the melt, which may have filled it. Give `screw_depth_mm` and the check reports
  both, and the thread length engaged.

## Heads, washers and what lifts the clamp

A printed part bears on two faces: under the screw's head, and, on a flush insert, on the insert's end. Either can
set the torque. The check computes both from cited dimensions in `cadagent.library.hardware`.

<img src="img/inserts/washers.svg" alt="The issue's M3 lid in PLA with ISO 7089 washers under the head and between the lid and the insert: the lid bears on 19.8 mm² of washer instead of 8.4 mm² of the insert's ring, so its preload cap rises from 329 N to 774 N; the pressure is full over the ring and falls off over the washer's overhang, 0.70 of 0.96 mm of which bears" width="900" height="570">

The issue's lid (#292) above: `mcmaster-94459A140` in PLA Basic, `boss_outside_mm: 8`, a 3 mm lid, socket head,
3.4 mm hole. The washer between the lid and the insert bears on 19.8 mm² against the bare ring's 8.4 mm². Only 0.70
of its 0.96 mm overhang counts: past that, a 0.45 mm washer would bend over 320 MPa. With the lid off the ring, the
head sets the next limit, so a second washer goes under it.

- **Heads.** `head` is `socket` (ISO 4762, the default), `button` (ISO 7380-1) or `cheese` (ISO 14580, ISO 1207).
  Each bears on its least bearing face `dw`. The cheese heads give no `dw`, so their least outside stands in: an
  upper bound, never offered as a larger head. `head_mm` still overrides. A hole narrower than the fillet under the
  head (`da`) gets a note to chamfer it.
- **Washers.** `head_washer` goes under the head, `insert_washer` between the printed part and the insert's end:
  `iso7089` (plain), `iso7090` (chamfered, M5 and up) or `iso7093` (large), M2 to M6, at the standard's largest
  hole, least outside and least thickness.
- **The bearing face** is the annulus outside the hole and its 45° chamfer (`chamfer_mm`, `under_chamfer_mm`):
  `formulas.bearing_area`. A washer's overhang is a beam on the plastic, a bed of springs of its modulus over its
  least thickness (`formulas.washer_bearing`). It stops where it would lift off, or where its bending at the support,
  counting the pressure further out on its longer ring, reaches the washer's strength (200 HV, 640 MPa) over the
  margin.
- **Friction.** A head on a washer turns on steel, so a washer lowers the torque for the same preload. Compare
  options by **preload**; the torque is what to set the wrench to.

When the printed part's bearing sets the torque (`head bearing`, `clamped on insert` or `clamped on washer`), the
result's `fixes` tries, in order, a larger head, a washer, a large washer, and a compression limiter (at the longest
standard length no longer than the plastic and the shortest that stands proud of it). Each is the same check run
again with the option fitted; a washer goes on the face that sets the limit, then on the next if that one then sets
it. An option is named only if it lifts the preload and fails no row the joint did not already fail, so a limiter
whose seating force or press fit fails is never named. `fix` is the first named; `lasting` the first named that keeps
the preload in metal (kept at least 0.9), in practice a limiter.

<img src="img/inserts/fix-ladder.svg" alt="The fix ladder in order, larger head, washer, large washer, limiter, each re-checked: on the issue's M3 lid the ISO 7089 washers lift the preload cap from 329 N to 774 N at 0.30 N·m and the catalogue limiters fail their own rows; on an M5 under a 3.8 mm PETG lid a proud limiter passes and is the lasting fix" width="900" height="422">

On the M3 lid a catalogue limiter does not help: its 4.15 mm bore lands on a thinner brass ring than the lid did,
and its seating force and press fit fail in 3 mm. On the M5 (`mcmaster-94459A775`, PETG Basic, 3.8 ± 0.05 mm lid)
washers lift the cap from 526 N to 1564 N (ISO 7089) and 1921 N (ISO 7093-1), but the lid stays in the clamp and
relaxes. A 4 mm CL6000 stands proud of the lid even at its least length, so the head lands on metal: it passes every
row and keeps the preload, 1240 N at 0.79 N·m, set by the insert's face.

## Compression limiters

A limiter only helps if the head lands on it. If it is longer than the plastic, the part is loose round it. If it is
shorter, the head must squeeze the plastic by the difference before it lands.

<img src="img/inserts/limiters.svg" alt="A compression limiter proud, flush and short of the plastic it passes through: proud, the plastic is loose round it; flush, the clamp goes through the metal; short, the head squeezes the plastic a few per cent before it lands on the limiter (SPIROL: at most 5 %, which printed plastic may not take)" width="870" height="330">

- **Some printed plastics take less squeeze than SPIROL allows.** SPIROL allows 3 to 5 % compression. A printed
  plastic reaches its compressive strength at **2.6 %** (PETG Basic) to **3.6 %** (PLA Basic), so the check warns
  past that.
- **The seating force.** SPIROL's formula 3 takes the plastic under the head as a column. A narrow ring of head on
  thick plastic spreads the load, and the far face sits on a broad face, so the check also takes Shigley's frustum
  through the whole thickness and uses the higher. An 18 mm steel sleeve 0.2 mm short of 40 ± 0.1 mm of wet PA6-CF,
  under a 20 mm washer, needs **550 N** as a column and **5055 N** as a cone. The ring then bears 85 MPa, so it warns.
- **A limiter on a straight-knurl insert.** The limiter must abut the insert. Its end then bears on the thin ring
  between its bore and the knurl, 10.00 mm² for M5. Brass's yield there caps the preload at 1240 N. Squeezing 6.1 mm
  of printed PETG by 4.9 % takes 3170 to 9146 N, so the limiter never seats and the check fails it. Make the limiter
  as long as the measured plastic, or use one with a proud knurl (Bulten), or a flanged insert.
- **Limiters of your own.** `check_clamp` takes a sleeve, a bushing or a spacer as `limiter` (its outside, bore,
  metal and, for the wall, its yield). Catalogue limiters are SPIROL's CL6000 (aluminium) and CL8000 (brass), M3 to
  M8, rated for 10.9 screws.

```mermaid
flowchart TD
    I["insert, hole, boss,<br/>material, axis"] --> P{"where does<br/>the clamp go?"}
    P -->|"flush or proud"| T["through the brass"]
    P -->|"recessed, wide hole<br/>or the tip bottoms"| J["jack-out: the knurl<br/>takes the preload"]
    P -->|"far side"| S["the shoulder<br/>takes it"]
    T --> C["torque ceilings: screw (75 % of proof),<br/>torque-out, insert thread, head,<br/>shoulder, limiter"]
    J --> C
    S --> C
    C --> L{"limiter?"}
    L -->|"no"| R["plastic in the clamp:<br/>it relaxes (warn)"]
    L -->|"yes"| K["length, seating force,<br/>wall, press fit, boss"]
    K --> V["pass, warn or fail<br/>with the most to tighten to"]
    R --> V
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class J out
```

## What the numbers rest on

The pull-out force is the knurl's cylinder sheared, F = c τ π D L. τ is half the filament's tensile strength across
the layers, from the maker's data sheet, and c is fitted to published tests.

<img src="img/inserts/calibration.svg" alt="Published heat-set insert pull-out tests as shear stress on the knurl's cylinder against insert size: printed PLA 16.4-21.5 MPa at M3 and 12.5-16.0 MPa at M6, so the larger insert sits lower; the check holds Bambu PLA Basic to 9.6 MPa" width="860" height="400">

- **PLA: c from 0.62 to 1.06**, from 13 results in four publications by three groups (László 2026, CNC Kitchen 2019
  and 2026, SPIROL 2026). Medium confidence. SPIROL's two M6 results set the low end.
- **PETG: c from 0.51 to 0.73**, from three results: CNC Kitchen's M3 and SPIROL's two M6. Low confidence.
- **SPIROL's M6 values are read off its bar charts** (its 3D-printing paper, Figures 10 and 12), to about 20 N.
- **Other families** (ASA, nylon) have no printed test with a data sheet in the table. They take the lowest c of any
  family, and the check warns.
- **Torque-out** comes from pull-out through r = 2 T / (F D). The tests give r from 0.66 (SPIROL, printed
  glass-filled PA6) to 1.41 (PEM, M8 in ABS). CNC Kitchen's printed PETG gives 1.12. The low end is taken.
- **Other sizes** scale by the knurl's area. SPIROL's printed M6 results sit below the M3 ones, so area alone would
  overstate a larger insert. The low end is the M6's.

<details>
<summary>Every row the check reports, and its rule</summary>

| Row | Pass | Warn | Fail |
|---|---|---|---|
| hole diameter | the maker's hole +0.2 to +0.3 mm in CAD (CNC Kitchen), or the printed hole's band | outside that | at or over the knurl |
| hole depth | the deepest of the makers' rules (SPIROL: the insert plus two pitches; CNC Kitchen and ruthex: +1 mm; McMaster's least material thickness); from the far face, for a far-side insert, no deeper than the insert, so it lands on the shoulder | short of it; for a far-side insert, deeper | no deeper than the insert |
| melt volume | the plastic the insert displaces fits the pocket below it | it does not | |
| screw tip | above the floor and inside the insert | past the insert's end | at or past the floor |
| printed hole (#323) | the hole for the filament and nozzle; given `filler_pct`, or an unfilled filament | a fibre-filled filament whose filler content is unknown: print the coupon | |
| boss perimeters (with `line_mm`) | at least SPIROL's metric size in whole line widths (LulzBot: two; Stratasys: four to six) | fewer | |
| boss wall | 2 × the knurl (the makers' full performance; the tests behind the low end used about 1.5 ×) | the makers' least wall to 2 × | under the least wall or 1.5 × the knurl |
| insert axis | along the build direction | in the layer plane: no published number | |
| calibration, calibration size | a family with printed tests, an insert no larger than the fitted ones | no printed test in the family, or a larger insert | |
| clamp path | flush, proud to 0.13 mm, or a far-side shoulder | recessed or more proud | |
| tightening torque | at most the lowest ceiling, the screw's at 75 % of its proof load (SPIROL) | within the margin over it | past it |
| insert thread | the preload and load under its stripping force / 2 (ISO 68 area, brass at 124 MPa) | under the force | over it |
| pull-out, push-out, torque-out | the separating load under the low capacity / 2 | under the low capacity | over it |
| shoulder | the plug a far-side insert would punch, / 2 | under it | over it, or its hole wider than the insert |
| head bearing | the preload on the plastic under the head (its listed bearing face, or a washer's spread) under its compressive strength / 2 | under the strength | over it |
| limiter length | squeeze at most 5 %, the limiter's own included | 5 to 7 %, past the plastic's compressive strength over its modulus, or proud | over 7 % |
| seating force | under the preload and 75 % of the proof load, the ring under its strength / 2 | the plastic crushes or creeps before the head lands | the head never lands |
| head over limiter | the head or washer reaches past it | it covers only the limiter | |
| limiter on insert | its bore smaller than the insert's face | | not abutting |
| insert face | the clamped part's or the limiter's end on the insert: the ring under brass's 124 MPa | up to 310 MPa | over it |
| clamped on insert | a printed clamped part on that ring under its compressive strength / 2 | under the strength | over it |
| clamped on washer | a printed clamped part on a washer on the insert's end (`insert_washer`), its spread face, under its compressive strength / 2 | under the strength | over it |
| limiter end (far-side insert) | its end on the shoulder's plastic under its compressive strength / 2 | under the strength | over it |
| limiter rating | the preload under 75 % of the proof load of the class it is rated for | under the proof load | over it |
| limiter wall (your own) | the stress in its wall under its yield / 2 | under the yield, or no yield given | over it |
| limiter press fit | the hoop stress its knurl raises in the hole under the strength along the layers / 2 | under the strength | over it |
| limiter boss | a wall of at least 0.5 d (Bulten) and the boss 2 × the limiter (SPIROL) | the boss under 2 × | the wall under 0.5 d |
| preload kept | at least 0.9 of it (an assumed level), the screw, limiter and plastic as springs | plastic in the clamp: it relaxes | |

The margin is 2.0 throughout (Covestro's least safety factor for plastic parts). Pass `margin` to change it.

</details>

## Worked example: a robot's inserts

[Gyropup](https://github.com/Valpatel/gyropup) has 151 heat-set inserts and many clamped plastic joints, listed in
its insert-joint audit (its PR #138, as merged). The checks ran on 41 of its 46 joint families and on 43 of the 47
printed clamps. Five joints fail:

- two screws reach 2.0 and 3.0 mm past the floor of a blind pilot, so they jack their inserts out;
- a 4 mm pilot is no deeper than its 5.7 mm insert;
- an M6 at 8 N·m puts 156 MPa on wet PA6-CF under its 10 mm head, against the 27 MPa allowed (114 MPa with an
  11 mm washer), and an M4 at 2.3 N·m puts 160 MPa on PETG under a socket head (6.53 mm bearing face) if what it clamps is
  printed.

The audit found the same problems on its own. The printed clamps pass at the torque the check gives them (0.23 to
1.24 N·m) and warn only because their plastic relaxes.

<details>
<summary>What the checks leave out, and where they and the audit differ</summary>

Outside these checks: a bearing stack with no plastic in it, pins with no screw, a lid with no receiver, an
adapter whose pattern is unpublished, four TPU isolators (no TPU data sheet in the table) and a nyloc whose bearing
face is not given.

- **A sleeve recessed 0.2 mm in a knee eye.** The audit puts the whole 10 kN on the 60 mm² of plastic under the
  washer's overhang (168 MPa). Here the plastic is a spring: with the eye's 40 ± 0.15 mm it takes about 5.8 kN,
  97 MPa, before the washer lands on the sleeve. Both say: press the sleeve proud.
- **Torque ceilings for plastic under the head.** The audit uses 25 MPa for sustained load. Here the limit is the
  compressive strength over the margin, 27 MPa for wet PA6-CF, so the ceilings are about 9 % higher.
- **Every pilot is drawn at the maker's hole**, which the audit also notes. CNC Kitchen measured printed holes about
  0.25 mm small, so each one warns.

</details>

## Test coupons

The plan prints each insert upright and lying, pulls it out, turns it out, and clamps it with and without a limiter.
The limiter stands proud of its plate, so that cell measures an all-metal clamp against the plastic one.
`python3 tools/insert_coupons.py --out exports/insert-coupons` writes each coupon's STEP and STL, in its print
orientation, and the plan as JSON.

<img src="img/inserts/coupons.svg" alt="Insert test coupons as CAD: for M3, M5 and M8, a block printed upright (the insert's axis along the build direction) and one printed lying (its axis in the layer plane), each with its designed hole" width="880" height="300">

Each cell is five specimens with the predicted value next to it, so a test can confirm or move the calibration.
Record the filament, the printer settings, the hole as printed, the iron, the insert's height afterwards, the room
and the failure mode. Pull at 2 mm/min with a reaction plate that clears the boss. Read a clamp's preload at 0, 1 h,
24 h and 168 h, then after 24 h at 50 °C.

## Limits

- **Not a rating.** The calibration is M3 × 5.7 and M6 × 12.7 in PLA and PETG. Other sizes scale by the knurl's
  area, from the M6's lower fit, and other families take the lowest fit.
- **Torque-out** comes from pull-out through the tests' ratio. **Push-out** and **an insert lying in the layer plane**
  have no published number, so they are flagged, not modelled.
- **Static, short-term, room temperature.** A held load creeps. PLA inserts kept 26 to 55 % of their pull-out after a
  year outdoors (Materials 2025).
- **Bosses as tested.** SPIROL printed 5 wall loops at 55 % infill, László a 1.3 to 1.9 mm solid sleeve in 40 %
  infill. Fewer walls hold less: one loop at 15 % infill held about a quarter of eleven (SPIROL, Figure 8).
- **Preload kept.** Printed PLA was measured for an hour and printed joints for a week. The long-term figure is
  moulded polycarbonate's, and PLA, nearer its glass transition, will keep less.
- **The seating force** takes the plastic as an elastic column or cone, with no edge or free face nearer than the cone.
- **A washer's spread** is a beam per unit length of the support's edge on a bed of springs, the pressure further
  out weighted by its longer ring. The bed is the plastic's whole thickness, backed flat on its far face. A lid under
  a washer on the insert is backed by the head, which may be narrower than the washer. Past the head's edge the lid
  is softer than the bed assumes, and the model does not size this. The ring's hoop stiffness, which helps, is left
  out. So is the boss face under a washer on the insert, so the washer carries the whole clamp to the brass. The free
  end is not modelled. A washer that yields would dish, and the spread would shrink.
- CAD and closed forms do not prove a joint holds. Print the coupons and measure.

## Sources and survey

<details>
<summary>What the survey of 2026-11-01 found, and every document the numbers come from</summary>

**Adopt or build.** bd_warehouse and cq_warehouse (Apache-2.0) hold heat-set insert dimensions and make a straight
hole as deep as the insert. FreeCAD's Fasteners workbench (GPL/LGPL) holds PEM's IUT table. NopSCADlib (GPL-3.0)
holds holes and a boss of two extrusion widths. BOSL2 has no insert module. None models a tapered or deeper hole, a
least wall, pull-out, torque-out, jack-out or a limiter, and no maker publishes a calculator (SABIC's boss calculator
is closed and for moulded parts). So the checks are built here. The 94459A120 row and the 94459A130 knurl come from bd_warehouse's
table (Apache-2.0); the rest is read from the makers' pages, documents and CAD below.

**Inserts and holes.** CNC Kitchen's *Heat-Set Insert Dimensions and Design Guidelines* (2025-06-30); ruthex's size
table; PennEngineering's *SI Threaded Inserts for Plastics* (2026-07-16), pp. SI-5, SI-6, SI-10, SI-25 and SI-26;
SPIROL's *Inserts for Plastics Design Guide* (05/26), printed pp. 5, 8, 9, 18, 20 and 21, and *How to Select a
Threaded Insert for Your 3D Printed Assembly* (04/26), pp. 2 to 5; CNC Kitchen's *Tips & Tricks for Heat-Set Inserts* (2021) and ruthex's tip set page for
the iron's temperature; McMaster-Carr's 94459A pages, read 2026-11-01. McMaster's M2.5 and M6 rows and the 93365A
family could not be read (a login was asked), so nothing is given for them.

**The printed hole (#323, read 2026-11-04).** The registry's threaded-insert sweep read 41 guides at the source. The hole rule above rests on SPIROL's *How to Design the Proper Hole for Heat / Ultrasonic Inserts*, CNC Kitchen's 2019 and 2026 tests, LulzBot's *Tips and Tricks: Heat-Set Inserts* (2017), PADT's *Adding Inserts to 3D Printed Parts* (2019), the EPFL MAKE wiki, Nophead's *Polyholes* (2011) and the RepRap wiki's *Arc Compensation*. Each record says what was read, and when.

**Tests.** K. László, B. F. Szivós and V. Nemes, *Engineering Proceedings* 157 (2026) 40; CNC Kitchen, 2019-12-07,
2020-05-30 and 2026-03-28; SPIROL's printed M6 tests (its 3D-printing paper, Figures 8 to 12, read off the charts);
SPIROL's INS 19 table and PEM's IUT table, both in the guides above; T. Kastner et al.
(2023) on infill and perimeters; *Materials* 18 (2025) 2591 on ageing.

**Limiters and clamps.** SPIROL's *Compression Limiters Design Guide*, 04/21 (pp. 3, 4, 6, 7, 14) and 05/26 (pp. 6,
15, 16); SPIROL's *How To Properly Mate Compression Limiters and Threaded Inserts* (2022); Bulten's *Compression
Limiters & Captive Bolt Assemblies* (2024); Covestro's *Part and Mold Design* (2015), p. 59 and Table 3-7, and
*Snap-Fit Joints*, Table 3; Bossard's *Screws property class 4.6 to 12.9*, *Surface pressure when mounted* and
*Friction and friction coefficients* (01-2025), after ISO 898-1 and VDI 2230; ISO 273 for clearance holes; C36000
brass's yield (Smiths Metal Centres, 2023).

**Heads and washers (#292).** The washers' holes, outsides and thicknesses are bd_warehouse's ISO 7089, ISO 7090 and
ISO 7093-1 tables (Apache-2.0), adopted as they are. Their least outside and thinnest thickness come from the
standards' tolerances, and the hardness class's tensile strength from ISO 18265's conversion (200 HV, 640 MPa). The
heads' bearing faces are not in any vendored table, so they are entered here from the standards' Table 1: ISO 4762
and ISO 7380-1 (dw min, da max), and ISO 14580 and ISO 1207 (dk min standing in, da max). The washer's spread is
Roark's beam on an elastic foundation (8th ed., Chapter 8).

**Plastics.** C. G. Amza et al., *Polymers* 13 (2021), Table 4 (printed PLA and PETG in compression, and a joint's
torque after 7 days); A. Liber-Kneć and S. Łagan, *Materials* 18 (2025) 3262 (printed PLA relaxing over an hour); the
filament makers' data sheets in [`allowables.py`](../src/cadagent/mechanical/compliant/allowables.py).

**Relations.** Shigley's *Mechanical Engineering Design*, 10th ed.: Section 8-2 and Eq. 8-27 (torque and clamp),
Section 8-5 (the frustum), Section 8-7 (load sharing), Section 8-9 (75 % of the proof load), Section 3-16 (press
fits), Section 5-5 (shear yield), Table A-5 (metals' moduli); ISO 68-1 (thread shear areas). Each one is in [Engineering formulas](formulas.md).

</details>

## Tests that keep it honest

`tests/formulas/test_inserts_formulas.py` checks each relation against a hand evaluation or a closed form it must reach.
`tests/mechanical/test_mechanical_inserts.py` reproduces the published tests from the calibration, checks the makers' hole and
boss rules, each row's verdicts on built cases, the CLI's exit codes, and the coupons' CAD volumes.
The printed hole's tests check SPIROL's filler steps, CNC Kitchen's 4.2 mm, the RepRap table and Nophead's faceting numbers as golden vectors. They also plant three defects the check must catch: a filled joint drawn with the unfilled hole, a coarse mesh drawn at the round hole, and a boss too thin for the nozzle.
`tests/library/test_hardware.py` holds the washer and head rows to bd_warehouse's files and the standards' rows.
`tests/mechanical/test_insert_figures.py` redraws every figure on this page from the module and fails if one has gone stale.
