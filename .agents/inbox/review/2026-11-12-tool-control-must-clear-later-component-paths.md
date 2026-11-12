# A tool-only obstruction control must also clear every later component path

2026-11-12, #542/PR637: the first native tool-approach control put a fixed 1×2×1 mm obstruction at
CAD [3,-1,31]. `PYTHONPATH=software <existing CAD python> -m pytest -q tests/review/test_gate_assembly.py -k serial`
returned `1 failed, 16 passed`: the assertion that every insertion was sampled-clear failed. The obstruction
correctly blocked the ordinary driver's handle during approach, but the later lid also crossed z31 while
lowering at x0. This was a fixture-scope error, not evidence of tool-only failure.

Keep the same blocker/tool geometry. In this control only, lower the lid beside the bench at x35, then translate
it below the blocker at z13. The regression requires all component insertions clear, engaged tool clear, and
the same ordinary handle blocked during its finite approach. The corrected narrow run returned
`17 passed, 85 deselected in 3.81s` before later coverage additions.

Rule: verify all other occupied paths before naming a seeded obstruction “tool-only.” Preserve the ordinary
tool dimensions and disclose any alternative component route. Limits: this is a synthetic rigid bench with
finite envelope samples; it proves neither real driver compatibility nor assembly/support/process qualification.
