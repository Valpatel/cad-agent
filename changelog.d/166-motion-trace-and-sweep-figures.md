**New**
- Two animated figures drawn from the real code on its kernel-free test fixtures (`tools/motion_figures.py`):
  `validate_motion_trace` on the analytic shaft, with a renderer that passes and one that spins the rotor about the
  wrong pivot and fails (docs/rendered-motion.md, #166); and the assembly gate's `sweep_pair` on its box world: the
  swept-box early-out, the exact samples with the bound `(g1 + g2 - h) / 2` between them, and a blocked insertion's
  first contact bisected (docs/gates.md, #164).
