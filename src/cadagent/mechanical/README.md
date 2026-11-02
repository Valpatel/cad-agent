# cadagent.mechanical

The mechanical domain of the [topic tree](../../../docs/areas.yaml): the features a part is built from and the checks
that they work, from holes and fasteners to bought hardware, connector windows, markings and compliant features.

Arrows follow the data. A project's build script imports the modules in the second row to make its parts
(`cad-agent mcmaster`, `cad-agent snapfit`, `cad-agent inserts` and `cad-agent bearings` run some of them from
the command line too), and `mcmaster.py` imports
`export_step` from the shared [`geometry`](../geometry/README.md) helpers. `holes.py` reads the exported STEP files and
the parts file (through `publish/report.py`'s `load_parts`). `motion_trace.py` (`cad-agent motion-trace`) stands
alone.

```mermaid
flowchart TD
    G["cadagent.geometry<br/>export_step"] --> MC["mcmaster.py<br/>bought parts"]
    G ~~~ FK["fasteners.py · bosses.py<br/>inserts.py · bearings.py · markings.py"]
    G ~~~ CC["connectors.py<br/>compliant/"]
    MC & FK & CC --> B["build script<br/>the project's CadQuery"]
    B -->|"STEP, parts file"| X["exports/<br/>STEP · parts file"]
    X --> H["holes.py<br/>cad-agent holes"]
    H --> HJ["exports/<br/>hole-checks.json"]
    HJ --> R["publish/report.py<br/>results JSON"]
    HJ ~~~ MT["motion_trace.py<br/>renders vs joints"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class MC,FK,CC,H,MT here
    class G,B,R near
    class X,HJ out
```

| Module | What it does |
|---|---|
| `holes.py` | Every hole in a part is empty of material (`cad-agent holes`); countersinks and drill points are probed as cones |
| `fasteners.py` | Dimension-driven fastener envelopes and axial stack checks |
| `bosses.py` | A thread-forming screw (DELTA PT sizes) in a printed boss: clamp, stripping force and torque, Covestro's torque window and the wall, from datasheet strengths ([screw bosses](../../../docs/screw-bosses.md)); a starting point to test, not a rating |
| `inserts.py` | Heat-set inserts and compression limiters in printed parts: the makers' hole and boss, where the screw's clamp goes, pull-out, torque-out and the insert's thread calibrated to published tests, the plastic under the head, limiters (catalogue or your own) and the preload kept; `cad-agent inserts` checks a file of joints, and the coupon plan says what to print and measure ([threaded inserts](../../../docs/inserts.md)); a starting point to test, not a rating |
| `bearings.py` | Rolling bearings: SKF and Koyo catalogue bearings with their sources, and one check of a bearing's ISO 281 life (turning or oscillating, under a load or a duty cycle), ISO 76 static safety against SKF's guideline s0, axial load, load range, minimum load and speed; for a swinging joint, the critical amplitude and the false-brinelling risk; `cad-agent bearings` checks a file of bearings ([rolling bearings](../../../docs/bearings.md)); a basic rating life, not a promise |
| `mcmaster.py` | McMaster-Carr parts: the manufacturer's STEP and product data for a part number, normalised into a known frame |
| `connectors.py` | Mating-connector envelopes: panel windows from the plug, then proof that the plug fits and that its cable can bend behind it at the data sheet's radius |
| `markings.py` | One XY drawing for engraved markings and a matching SVG proof |
| `printed_joints.py` | Load-bearing joints in printed parts, checked before printing ([printed joints](../../../docs/printed-joints.md)): a pin through an eye (bearing, shear-out, net tension against the layers, with or without a bushing), the root of a boss or rib under a side load and the through-bolt preload that keeps its layers closed, and a screw that backs out under vibration |
| [`compliant/`](compliant/README.md) | Compliant features that replace parts: snap fits now, hinges and flexures next |
| `linkages.py` | Four-bars and five-bars swept over their inputs: joint angles, locks, edges of reach, branch flips; the dyad solver for linkages measured from CAD |
| `motion_trace.py` | Compares rendered landmarks with CAD joint intent, without a CAD kernel |

Related: [package map](../README.md) · [mcmaster-parts skill](../../../skills/mcmaster-parts/SKILL.md) ·
[compliant mechanisms](../../../docs/compliant.md) · [common issues](../../../docs/common-issues.md) (the mistakes
these catch)
