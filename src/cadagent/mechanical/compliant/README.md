# cadagent.mechanical.compliant

Compliant features that replace separate parts: snap fits now, living hinges and flexures next. The method, the
materials and the limits are on the [snap fits and compliant features](../../../../docs/compliant.md) page.

Arrows follow the data. A project declares its snaps in a file, and `cad-agent snapfit` checks each one with
`snapfit.py`, which takes printed filaments' allowables from `allowables.py`. `figures.py` draws a checked snap still.
[`cadagent.formulas`](../../formulas/__init__.py) wraps the same equations for the site's explorers, and
[`publish/anim/snapfit.py`](../../publish/anim/snapfit.py) animates one arm engaging from `engagement()`.

```mermaid
flowchart TD
    Y["snaps.yaml<br/>the project's snaps"] --> SF["snapfit.py<br/>check_spec · engagement"]
    A["allowables.py<br/>data-sheet editions"] --> SF
    SF --> J["exports/snap-checks.json<br/>rows, derivation, limits"]
    SF --> FG["figures.py<br/>a checked snap, still"]
    SF --> FM["cadagent.formulas<br/>the explorers' equations"]
    SF --> AN["publish/anim/snapfit.py<br/>a snap engaging"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class SF,A,FG here
    class Y,FM,AN near
    class J out
```

| Module | What it does |
|---|---|
| `snapfit.py` | Cantilever, torsion and annular snaps by the Covestro (Bayer) closed form: strain, deflection, forces, pass/fail rows (`cad-agent snapfit`), and `engagement()`, the root strain and push to mate along the insertion |
| `allowables.py` | Printed filaments' allowable strain by print direction, from every data-sheet edition read, the cautious one per quantity |
| `figures.py` | A checked cantilever drawn still, deflected over its catch, with the result's numbers |

![A printed snap arm 15 mm long bends as a mating part's edge rides its hook's 30° lead. Its root strain rises to 1.38 %: 68 % of the 2.02 % allowed for Polymaker PolyMide CoPA (dry), a pass, and 139 % of the 1.00 % allowed for Bambu PETG-CF, a fail](../../../../docs/img/compliant/snap-engagement.svg)

*The toolkit's closed-form calculator (`snapfit.py`, the Covestro method) on the stated arm: not a measurement.
Allowables from the data sheets Polymaker PolyMide CoPA V5.4 and Bambu Lab PETG-CF V3.0. Printed snaps need a test
print.*

Related: [mechanical](../README.md) · [snap fits and compliant features](../../../../docs/compliant.md) ·
[research note](../../../../research/compliant-mechanisms.md) · [animated figures](../../../../docs/animated-figures.md)
