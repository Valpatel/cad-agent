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
WARN  lid: M3 94459A140 in Bambu PLA Basic, through-insert; tighten to at most 0.70 N m (head bearing)
      warn: preload kept: the clamped plastic relaxes and takes the preload with it: ...
WARN  bracket: M4 clamping Bambu PLA Basic; tighten to at most 0.68 N m (head bearing)
      warn: preload kept: the clamped plastic relaxes and takes the preload with it: ...
```

The command exits 1 when a joint fails and 2 when the file is wrong. A warning does not fail it. The JSON holds every
row with its value, limit, verdict and reason, the insert's capacities, the torque ceilings and the limits.

From Python:

```python
from cadagent.mechanical import inserts

inserts.hole_design(inserts.insert("mcmaster-94459A140"))      # 4.2 mm in CAD (the maker's 4.0 + 0.2), 6.7 mm deep
r = inserts.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, head_mm=7.0,
                        clearance_mm=3.4, clamped={"thickness_mm": 4.0})
r["verdict"], r["torque"]["allowed_nm"], r["torque"]["governed_by"]   # 'warn', 0.70, 'head_bearing'
r["capacity"]["pull_out"]                                         # low 1063, mid 1169, high 1394 N
inserts.check_clamp("M10", "pa6-cf20-polymaker-wet", 40.0, head_mm=20.0, clearance_mm=12.0, torque_nm=20.0,
                    limiter={"outside_mm": 18.0, "bore_mm": 12.0}, limiter_length_mm=39.8)
inserts.coupon_plan()                                             # what to print and measure
```

## Where the clamp goes

The insert's height against the joint face decides what carries the screw's clamp. This is the first thing the
check works out, and it changes every limit after it.

<img src="img/inserts/clamp-paths.svg" alt="Three clamp paths for a heat-set insert: pulled into a shoulder (the shoulder carries the clamp), flush (the clamped part bears on the insert) and recessed (the screw jacks the insert out of the boss: the knurl carries the whole preload)" width="870" height="360">

- **Flush, or up to 0.13 mm proud** (PEM, SPIROL). The clamped part bears on the insert's end. The clamp goes through
  the brass, and the knurl carries only what pulls the parts apart. M3 in PLA Basic, clamping metal: tighten to at
  most **0.65 N·m**, set by the insert's own thread.
- **Recessed, even by 0.05 mm.** The screw pulls the insert towards the head until the gap closes. The knurl
  carries the whole preload, so the same joint 0.2 mm recessed may take only **0.18 N·m**.
- **A clamped part whose hole is as wide as the insert** bears on the plastic round it. That jacks the insert out
  too, and the check says so.
- **Pressed in from the far side**, the insert is pulled into the boss in front of it, and that shoulder must not
  punch out.
- **The screw's tip.** Past the floor of a blind hole the screw bottoms and jacks the insert out. Past the insert's
  end it reaches the room left for the melt, which may have filled it. Give `screw_depth_mm` and the check reports
  both, and the thread length engaged.

## Compression limiters

A limiter only helps if the head lands on it. If it is longer than the plastic, the part is loose round it. If it is
shorter, the head must squeeze the plastic by the difference before it lands.

<img src="img/inserts/limiters.svg" alt="A compression limiter proud, flush and short of the plastic it passes through: proud, the plastic is loose round it; flush, the clamp goes through the metal; short, the head squeezes the plastic a few per cent before it lands on the limiter (SPIROL: at most 5 %, which printed plastic may not take)" width="870" height="330">

- **Printed plastic takes less squeeze than moulded.** SPIROL allows the plastic 3 to 5 % compression. A printed
  part's strength over its modulus is nearer 1.4 %, so the check warns past it.
- **The seating force.** SPIROL's formula 3 takes the plastic under the head as a column. When the head overhangs the
  limiter by a narrow ring on thick plastic, the load spreads and the plastic is stiffer than that, so the check also
  takes Shigley's frustum and uses the higher of the two. An 18 mm steel sleeve 0.2 mm short of 40 mm of wet PA6-CF,
  under a 20 mm washer, needs **550 N** as a column and **2935 N** as a cone. The ring then bears 49 MPa, so it warns.
- **A limiter on a straight-knurl insert.** The limiter must abut the insert. Its end then bears on the thin ring
  between its bore and the knurl, 10.00 mm² for M5. Brass's yield there caps the preload at 1240 N. Squeezing 6.1 mm
  of printed PETG by 4.9 % takes 3170 to 6338 N, so the limiter never seats and the check fails it. Make the limiter
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
    T --> C["torque ceilings: screw, torque-out,<br/>insert thread, head bearing,<br/>shoulder, insert face"]
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

<img src="img/inserts/calibration.svg" alt="Published heat-set insert pull-out tests as shear stress on the knurl's cylinder against insert size: printed PLA 16.4-21.5 MPa, moulded hosts level across M3 to M8 within their spread; the check holds Bambu PLA Basic to 12.6 MPa" width="860" height="400">

- **PLA: c from 0.81 to 1.06**, from 11 results in three publications by two groups (László 2026, CNC Kitchen 2019
  and 2026). Medium confidence, M3 × 5.7 inserts only.
- **PETG: c 0.66**, from one result of three samples (CNC Kitchen 2020). Low confidence.
- **Other families** (ASA, nylon) have no printed test. They take the lowest c of any family, and the check warns.
- **Torque-out** comes from pull-out through r = 2 T / (F D). The tests give r from 0.87 (SPIROL, M3 in nylon) to 1.41
  (PEM, M8 in ABS). One printed PETG test gives 1.12. The low end is taken.
- **Other sizes** scale by the knurl's area. The moulded makers' tables are level across M3 to M8 when drawn this
  way, which is what supports it.

<details>
<summary>Every row the check reports, and its rule</summary>

| Row | Pass | Warn | Fail |
|---|---|---|---|
| hole diameter | the maker's hole −0.1 to +0.3 mm in CAD | outside that | at or over the knurl |
| hole depth | the deepest of the makers' rules (SPIROL: the insert plus two pitches; CNC Kitchen and ruthex: +1 mm; McMaster's least material thickness) | short of it | no deeper than the insert |
| melt volume | the plastic the insert displaces fits the pocket below it | it does not | |
| screw tip | above the floor and inside the insert | past the insert's end | at or past the floor |
| boss wall | 2 × the knurl (the tests' boss) | the makers' least wall to 2 × | under the least wall or 1.5 × the knurl |
| insert axis | along the build direction | in the layer plane: no published number | |
| calibration | a family with printed tests | no printed test in the family | |
| clamp path | flush, proud to 0.13 mm, or a far-side shoulder | recessed or more proud | |
| tightening torque | at most the lowest ceiling | within the margin over it | past it |
| insert thread | the preload and load under its stripping force / 2 (ISO 68 area, brass at 124 MPa) | under the force | over it |
| pull-out, push-out, torque-out | the separating load under the low capacity / 2 | under the low capacity | over it |
| shoulder | the plug a far-side insert would punch, / 2 | under it | over it, or its hole wider than the insert |
| head bearing | the preload on the plastic under the head under its compressive strength / 2 | under the strength | over it |
| limiter length | squeeze at most 5 % | 5 to 7 %, past the printed plastic's 1.4 %, or proud | over 7 % |
| seating force | under the preload and 75 % of the proof load, the ring under its strength / 2 | the plastic crushes or creeps before the head lands | the head never lands |
| head over limiter | the head or washer reaches past it | it covers only the limiter | |
| limiter on insert, insert face | its end on the insert, the face under brass's 124 MPa | up to 310 MPa | not abutting, or over |
| limiter rating | the preload under 75 % of the proof load of the class it is rated for | under the proof load | over it |
| limiter wall (your own) | the stress in its wall under its yield / 2 | under the yield, or no yield given | over it |
| limiter press fit | the hoop stress its knurl raises in the hole under the strength along the layers / 2 | under the strength | over it |
| limiter boss | a wall of at least 0.5 d (Bulten) and the boss 2 × the limiter (SPIROL) | the boss under 2 × | the wall under 0.5 d |
| preload kept | a limiter keeps at least 0.9 of it | plastic in the clamp: it relaxes | |

The margin is 2.0 throughout (Covestro's least safety factor for plastic parts). Pass `margin` to change it.

</details>

## Worked example: a robot's inserts

[Gyropup](https://github.com/Valpatel/gyropup) has 151 heat-set inserts and a few clamped plastic joints, listed in
its insert-joint audit (its PR #138). The checks ran on all 43 joint families. 40 fit them, and 5 of those fail:

- two screws reach 2.0 and 3.0 mm past the floor of a blind pilot, so they jack their inserts out;
- a 4 mm pilot is no deeper than its 5.7 mm insert;
- an M6 at 8 N·m puts 156 MPa on wet PA6-CF under its head, against the 27 MPa allowed, and an M4 at 2.3 N·m does
  the same on PETG if what it clamps is printed.

The audit found the same problems on its own.

<details>
<summary>What the checks leave out, and where they and the audit differ</summary>

Three families are outside these checks: a bearing stack with no plastic in it, pins with no screw, and 47 printed
clamps the audit describes only in prose.

- **A sleeve recessed 0.2 mm in a knee eye.** The audit puts the whole 10 kN on the 60 mm² of plastic under the
  washer's overhang (168 MPa). Here the plastic is a spring: it takes about 2.9 kN, 49 MPa, before the washer lands
  on the sleeve. Both say: press the sleeve proud.
- **Torque ceilings for plastic under the head.** The audit uses 25 MPa for sustained load. Here the limit is the
  compressive strength over the margin, 27 MPa for wet PA6-CF, so the ceilings are a little higher (0.87 against
  0.82 N·m for an M5).

</details>

## Test coupons

The plan prints each insert upright and lying, pulls it out, turns it out, and clamps it with and without a limiter.
`python3 tools/insert_coupons.py --out exports/insert-coupons` writes each coupon's STEP and STL, in its print
orientation, and the plan as JSON.

<img src="img/inserts/coupons.svg" alt="Insert test coupons as CAD: for M3, M5 and M8, a block printed upright (the insert's axis along the build direction) and one printed lying (its axis in the layer plane), each with its designed hole" width="880" height="300">

Each cell is five specimens with the predicted value next to it, so a test can confirm or move the calibration.
Record the filament, the printer settings, the hole as printed, the iron, the insert's height afterwards, the room
and the failure mode. Pull at 2 mm/min with a reaction plate that clears the boss. Read a clamp's preload at 0, 1 h,
24 h and 168 h, then after 24 h at 50 °C.

## Limits

- **Not a rating.** The calibration is M3 × 5.7 in PLA (and one PETG result). Other sizes scale by the knurl's area,
  and other families take the lowest fit.
- **Torque-out** comes from pull-out through the tests' ratio. **Push-out** and **an insert lying in the layer plane**
  have no published number, so they are flagged, not modelled.
- **Static, short-term, room temperature.** A held load creeps. PLA inserts kept 26 to 55 % of their pull-out after a
  year outdoors (Materials 2025).
- **Solid bosses.** The tests printed the boss solid round the insert. Infill and perimeters change the capacity by up
  to 2.5 × (Kastner 2023).
- **Preload kept.** Printed PLA was measured for an hour and printed joints for a week. The long-term figure is
  moulded polycarbonate's, and PLA, nearer its glass transition, will keep less.
- **The seating force** takes the plastic as an elastic column or cone, with no edge or free face nearer than the cone.
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
SPIROL's *Inserts for Plastics Design Guide* (05/26), printed p. 5 and pp. 20 to 21, and *How to Select a Threaded Insert for Your
3D Printed Assembly* (04/26); CNC Kitchen's *Tips & Tricks for Heat-Set Inserts* (2021) and ruthex's tip set page for
the iron's temperature; McMaster-Carr's 94459A pages, read 2026-11-01. McMaster's M2.5 and M6 rows and the 93365A
family could not be read (a login was asked), so nothing is given for them.

**Tests.** K. László, B. F. Szivós and V. Nemes, *Engineering Proceedings* 157 (2026) 40; CNC Kitchen, 2019-12-07,
2020-05-30 and 2026-03-28; SPIROL's INS 19 table and PEM's IUT table, both in the guides above; T. Kastner et al.
(2023) on infill and perimeters; *Materials* 18 (2025) 2591 on ageing.

**Limiters and clamps.** SPIROL's *Compression Limiters Design Guide*, 04/21 (pp. 3, 4, 6, 7, 14) and 05/26 (pp. 6,
15, 16); SPIROL's *How To Properly Mate Compression Limiters and Threaded Inserts* (2022); Bulten's *Compression
Limiters & Captive Bolt Assemblies* (2024); Covestro's *Part and Mold Design* (2015), p. 59 and Table 3-7, and
*Snap-Fit Joints*, Table 3; Bossard's *Screws property class 4.6 to 12.9*, *Surface pressure when mounted* and
*Friction and friction coefficients* (01-2025), after ISO 898-1 and VDI 2230; ISO 273 for clearance holes; C36000
brass's yield (Smiths Metal Centres, 2023).

**Plastics.** C. G. Amza et al., *Polymers* 13 (2021), Table 4 (printed PLA and PETG in compression, and a joint's
torque after 7 days); A. Liber-Kneć and S. Łagan, *Materials* 18 (2025) 3262 (printed PLA relaxing over an hour); the
filament makers' data sheets in [`allowables.py`](../src/cadagent/mechanical/compliant/allowables.py).

**Relations.** Shigley's *Mechanical Engineering Design*, 10th ed.: Section 8-2 and Eq. 8-27 (torque and clamp),
Section 8-5 (the frustum), Section 8-7 (load sharing), Section 3-16 (press fits), Section 5-5 (shear yield), Table
A-5 (metals' moduli); ISO 68-1 (thread shear areas). Each one is in [Engineering formulas](formulas.md).

</details>

## Tests that keep it honest

`tests/test_inserts_formulas.py` checks each relation against a hand evaluation or a closed form it must reach.
`tests/test_mechanical_inserts.py` reproduces the published tests from the calibration, checks the makers' hole and
boss rules, each row's verdicts on built cases, the CLI's exit codes, and the coupons' CAD volumes.
`tests/test_insert_figures.py` redraws every figure on this page from the module and fails if one has gone stale.
