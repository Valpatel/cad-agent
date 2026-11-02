# Rendered joint motion validation

The maintained [trace protocol](../skills/cad-motion-validation/references/trace-protocol.md) ships with the
[cad-motion-validation skill](../skills/cad-motion-validation/SKILL.md), including when the workflow installer
copies the skill to a different machine. It documents the independent CAD reference, actual renderer capture,
`cad-agent motion-trace` CLI, required coverage, diagnostics and evidence limits.

```mermaid
flowchart TD
    CAD["CAD source<br/>axes, landmarks"] --> Ref["reference<br/>home frame"]
    Scene["browser scene<br/>matrices × vertices"] --> Obs["observed<br/>trace"]
    Ref & Obs --> T["motion-trace<br/>compares each range"]
    G["motion gate<br/>interference"] -.->|"complements"| T
    T --> Rep["report<br/>coverage, diagnostics,<br/>input hashes"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class Ref,Obs,T here
    class CAD,Scene,G near
    class Rep out
```

Two independent paths meet only in the comparison: the reference comes from the CAD, the observation from the
renderer that people actually look at, so a pivot error in either shows up.

![A shaft that yaws a housing and spins a rotor on it, at each of its ten required poses: renderer A draws every landmark on the CAD's reference and passes; renderer B spins the rotor about a pivot 48 mm off the shaft and fails, its rotor 96 mm off at spin 180 degrees; without the nested pose, yaw -90 with spin 180, A would fail its coverage](img/motion/motion-trace.svg)

*`validate_motion_trace` compares, pose by pose, where a renderer drew each landmark with where the CAD's own joint
matrices put it. An illustration of the analytic shaft in `tests/mechanical/test_motion_trace.py`: renderer A is the test's
independent renderer, B its offset-pivot defect; the poses, errors and verdicts are the validator's.*

A closed loop, such as a four-bar or a five-bar leg, is declared under `loops` on top of the joint tree. Its inputs are
sampled together, its other joints are solved, and each sample's loop must close where the solver closes it. See the
protocol, and [Linkages](linkages.md) for the solver.
