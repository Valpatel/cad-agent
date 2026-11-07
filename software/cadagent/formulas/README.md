# cadagent.formulas

Closed-form engineering equations that every domain keeps needing. Each one gives its SI units, the limits where it
stops being valid, and its source by author, title, edition and section:
- beams and snap arms;
- torsion bars;
- coil springs;
- screw preload and thread strip;
- heat-set inserts (pull-out, torque-out, the clamp path, the most to tighten) and compression limiters (proof load,
  stack, press fit, a clamped member's stiffness, the preload kept);
- riveted lap joints (shear, bearing, tearing, efficiency);
- four-bar and five-bar linkages;
- rolling bearings: rating life, equivalent loads, static safety, duty cycles and oscillation limits;
- conduction, film resistance, fans in series and parallel, fan operating points and the stall region.

`from cadagent import formulas as fx`, then `fx.catalogue()` lists every formula. It sits in the shared core, beside
`geometry/`, because its users span mechanical and thermal design. See [docs/formulas.md](../../../docs/formulas.md).

Arrows follow the data and the imports:
- the books and standards give the equations, never copied text;
- `beams.py` calls `mechanical/compliant/snapfit.py`, so a snap arm here matches `cad-agent snapfit` exactly, and
  `torsion.py` takes its allowable shear strain from there too;
- `tools/formula_vectors.py` generates cross-language fixtures from the browser-supported Python subset, and
  `webkit/formulas.js` is tested against them (`--check` keeps the two in step). Generated parity fixtures alone
  do not independently validate an equation;
- [bearing-vectors.json](../../../tests/fixtures/bearing-vectors.json) records cited maker examples, tables and
  published cross-checks. [test_bearings.py](../../../tests/formulas/test_bearings.py) checks those expectations and
  states the model assumptions, separately from the browser port.

```mermaid
flowchart TD
    S["cited sources<br/>books · guides · standards"] --> F["cadagent.formulas<br/>units · limits · source"]
    S -->|"equations"| B["bearings.py"]
    S -->|"published cases"| E["tests/fixtures/<br/>bearing-vectors.json"]
    C["mechanical/compliant/<br/>snapfit.py"] -->|"snap arms, torsion allowable"| F
    F -->|"browser-supported subset"| V["tools/formula_vectors.py<br/>parity fixtures"]
    V --> W["webkit/formulas.js<br/>the site's demos"]
    B -->|"registered equations"| F
    B --> T["tests/formulas/<br/>test_bearings.py"]
    E -->|"source expectations"| T
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class F,B here
    class S,C,V,E near
    class W,T out
```

| Module | What it computes |
|---|---|
| `_registry.py` | The registry: every public function's units, limits and source; `catalogue()` lists them |
| `beams.py` | Second moment, cantilever deflection and shape, strain profile, tapered arms, snap-arm strain and force |
| `torsion.py` | Torsion constants and shear stress of round and rectangular bars, torsion-bar twist and stiffness, the peak shear strain of a twisted rectangle and a torsion-bar snap against the Covestro allowable |
| `springs.py` | Coil-spring index, Bergsträsser factor, rate and shear stress |
| `screws.py` | Tensile stress area, nut factor (any flank angle), preload from torque and back, thread shear areas and strip force, the thread's radial push and the boss's hoop stress, and a thread-forming screw in a plastic boss against Covestro's torque window |
| `inserts.py` | A heat-set insert's displaced melt and the pocket below it, its pull-out and torque-out as a sheared knurl, where the screw's clamp goes (seat, through the insert, or jack-out) and the most to tighten it |
| `limiters.py` | Proof load, stress on an annulus, a limiter's stack against the plastic, the plastic's share when it is short, a clamped member's frustum stiffness, press-fit pressure and force, and the preload a joint keeps when its plastic relaxes |
| `rivets.py` | A riveted lap joint per pitch: rivet shear, bearing, tearing between holes, the solid sheet, and the joint's strength and efficiency |
| `linkages.py` | Grashof class and inversion, four-bar angles from the input angle, transmission angle, the input's limits; a five-bar's tip, crank angles and singularities |
| [`bearings.py`](bearings.py) | Rolling-bearing rating life, equivalent loads, static safety, duty cycles, oscillation factors and Hertz contact; source-worked examples above and [model limits](../../../docs/mechanical/bearings.md#limits) |
| `thermal.py` | Wall and film resistance, wall heat flow, straight-line fan curve, system coefficient, fans in series and parallel, fan operating point, stall flow |

A closed form is not proof of fit or strength. Each result holds only within the limits it states, and a printed part
is weaker across its layers than any isotropic formula assumes. Test the part.
Bearing life is a statistic for a group, not a promise for one bearing; lubrication/contamination life modification
and small-angle wear are not predicted by these models.

Related: [package map](../README.md) · [compliant features](../mechanical/README.md) ·
[formulas reference](../../../docs/formulas.md)

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package entry point; public imports and compatibility behavior are defined here. |
