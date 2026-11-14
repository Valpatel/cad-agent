**New**
- `cadagent.review.dossier.not_drawn(name, reason=..., near=...)`: a build script declares a component that is part of the design and has no shape in the build (a gear that is only numbers in an analysis script). The geometry record lists it under `not_drawn`, and `cad-agent gates` names it in every verdict (`not_drawn`, an assumption, and a "Not in the model" section in `<gate>.md`), in each gate's row and in a "not in the model" line after the counts. The dossier lint lists each as a `not-drawn` warning (#722).
- `cadagent.review.gates.verdict.note_not_drawn(data, record)` applies the same statement to a verdict from a gate called directly or from a project's own gate (#722).

**Changed**
- With a `not_drawn` declaration, the connectivity, containment, fasteners, motion and assembly gates add a `<gate>:not-drawn` warning, so they read `warn` where they read `pass`. `pass` stays true and no exit code changes. A project that declares nothing gets the same record and the same verdicts as before (#722).
