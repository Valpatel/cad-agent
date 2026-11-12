# Banners and sharing

Existing figures for banners and sharing. The caption/source index distinguishes illustrative diagrams from recorded outputs; these pictures do not prove current physical performance.

<img src="made-with-cad-agent.svg" width="520" alt="Banners and sharing">

```mermaid
flowchart TD
    A["README.md"]
    B["made-with-cad-agent.svg"]
    C["../../pages.yaml"]
    A --> B
    C --> B
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [learning-loop.svg](learning-loop.svg) | Original conceptual human/idea and engineering-workbench panorama, with reviewed feedback and reduced-motion still state. |
| [learning-loop-mobile.svg](learning-loop-mobile.svg) | Compact square composition of the same human learning story. |
| [thermal-history.svg](thermal-history.svg) | Animated actual heater-zone samples from the recorded 20 W box case; iterations, not elapsed seconds. |
| [airflow-balance.svg](airflow-balance.svg) | Recorded flow and heat-out comparison retaining the failed ducted case. |
| [learning-evidence.json](learning-evidence.json) | Input hashes, sampled trace count and recorded case facts. |
| [gyropup-leg.svg](gyropup-leg.svg) | SVG: cad-agent: Gyropup's five-bar leg drawn from its real CAD, assembled, then checked for fit, strength and motion |
| [made-with-cad-agent-still.svg](made-with-cad-agent-still.svg) | SVG: Made with cad-agent — still badge |
| [made-with-cad-agent.svg](made-with-cad-agent.svg) | SVG: Made with cad-agent |
| [repository-map-still.svg](repository-map-still.svg) | SVG: Build the builders — a robot-factory still |
| [repository-map.svg](repository-map.svg) | SVG: Build the builders — a robot-factory cinematic |

</details>

[Figure index](../README.md) · [Captions and tool inputs](https://github.com/Valpatel/cad-agent/blob/dev/docs/pages.yaml)

## Homepage learning loop — design and evidence plan (#605)

The new hero is an original vector explanation, not a simulated hardware result. Its
loop shows authored examples and manufacturer guides entering a messy evidence
network, being organized into topic trees and cited rules, then design → check →
simulate → print → feedback. A clear human review gate precedes contributions.
Hosted agents (including Anthropic's tooling) and local/open models are possible
clients of the same documented files; their presence is not an integration claim.

Use a dark technical canvas, warm white typography, restrained cyan/amber accents,
visible source-document shapes and evolving graph geometry. Keep three readable
stages at phone width; the animation must tell the same story as a useful still.
No logos, particle-only filler, invented benchmark values or implied autonomous
self-modification. Reduced motion freezes the complete readable state.

### Asset audit, 2026-11-11

| Existing evidence | Reuse decision and limit |
|---|---|
| `docs/img/fea/mesh-convergence.svg`, `tools/fea_mesh_figure.py` | Recorded L-bracket study; animate the existing sampled refinement sequence, not a fresh solver result. Convergence is not physical strength proof. |
| `docs/img/cfd/SOURCE.json`, `tests/fixtures/cfd_runs/` | Recorded OpenFOAM traces permit temperature/flow/balance plots. Preserve the ducted case's failed energy/steady criteria; flow markers explain direction, not invented CFD particle trajectories. |
| `docs/img/thermal/fan-curve-explorer.svg` and fan-curve module | Existing operating-point calculation can be animated from the real curve/intersection; do not present a computed operating point as a measurement. |
| `docs/img/motion/*.svg`, `docs/img/compliant/example-1.svg` | Existing computed fixture/worked-example motion, interference and snap geometry; retain their captions and source pages. |
| `tools/site/assets/models/gyropup.*` | Current collected assembly with source revision/hashes; move the existing shared viewer below the hero. Historical wheel-link FEA remains separately dated. No printed-leg changes. |
| J501 clean source `240be82ec5420e989dbfad07d76ab62ea3e83a50` | Audit its existing `exports/view/view.json` and assembly-coordinate STL outputs, including the real carrier-board mesh. Pack these outputs without regenerating CAD. Hash every selected input and preserve source/PCB attribution and fit-prototype limits. |

### Delivery and verification

1. Commit this audit before artwork/code; prototype original hero and evidenced
   output gallery, remove empty/command-only cards, skills and counter sections.
2. Reuse `<cad-model>` for independent Gyropup and J501 viewers. Add explicit
   per-instance loading progress/stage, retained poster, clear failure and retry
   where safe. No download on initial hero paint; keep independent failure states.
3. Every displayed computation image must be animated and source-bound in
   `docs/home.yaml`. Remove cards lacking real visual evidence rather than making
   decorative results. Thermal/airflow captions state solver/model assumptions.
4. Pure checks bind input hashes, numbers, source links, SVG XML, animation/still
   states and removed placeholder content. Browser acceptance covers desktop,
   phone, reduced motion, both themes, actual image loading, animation bounds,
   model progress/ready/failure, lazy independent loading and no-script posters.
5. Coordinate the capped `--client-diagrams` local producer/browser lane with the
   coordinator before launching. Review the prototype headed before final polish.
   Normal independent review/CI/release/public acceptance remain required.

The homepage owns the compiler region after `const home`; #603 owns the frame,
navigation, discovery, catalogue and timestamp regions. No editing another tree.

Owner refinement (2026-11-11): the central story is **helping anyone build what
they need, with high quality and continuously improving AI**. A person's need
starts the loop, evidence/resources support the AI, checks and making produce a
useful object, and real or simulated feedback improves the next round. Graph
cleanup supports that human story rather than replacing it. The first prototype
uses the product's existing `preview/open.png` as J501's honest interim poster;
final acceptance requires a matching shared-viewer poster and complete loading,
reduced-motion, WebGL failure and keyboard evidence.

### Owner art rejection and revised acceptance, 2026-11-11

The owner viewed prototype C and rejected its slow/simple lone-person scene:
“it needs to clearly convey the idea of humans collaborating with self-improving
machines.” The previous 16-second workbench/graph loop is **not accepted art**.
The next scene must show a recognizable capable machine partner working with the
person: a sketch/gesture, machine construction, direct handoff, human testing and
feedback, then a visibly revised second object. Shared knowledge returns to the
machine. Target an eight-second narrative with purposeful one-to-three-second
beats, articulated hands/tool head, assembly motion and clear finished solids.
The reduced-motion composition must show the completed collaboration. A denser
graph, passing loader tests or earlier screenshots cannot substitute for that
visual acceptance. The scene stays conceptual, without claiming physical autonomy
or automatic model training. Review the new source-bound producer headed again.
