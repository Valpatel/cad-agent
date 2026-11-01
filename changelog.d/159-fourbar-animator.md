**New**
- `cadagent.formulas.fourbar_input_limits(a, b, c, d)`: the input angles where a four-bar locks (coupler and rocker in
  one line, Norton's toggle positions), whether the input turns fully, and whether the links close at all (#159).
- `cadagent.formulas.grashof` also returns `inversion`: crank-rocker, double-crank, rocker-crank, double-rocker,
  triple-rocker or change-point (#159).
- `kit/formulas.js` ports `grashof`, `fourbarAngles`, `transmissionAngle` and `fourbarInputLimits`, tested against the
  Python on golden vectors that cover both branches, change points and the input limits (#159).
- `<cad-fourbar>` (`kit/fourbar.js`, `kit/fourbar.css`): a four-bar linkage animator with link-length sliders, both
  assemblies, the coupler curve, the Grashof class, and the transmission angle charted against 40°. A linkage whose
  input cannot turn fully stops at its limits. On the new Four-bar linkages page and on Engineering formulas (#159).

**Changed**
- Code that compares `grashof()`'s result with a whole dict must add the `inversion` key (#159).
