**Fixed**
- FEA `Study.converge()` compares unrounded design stresses, so tiny loads cannot falsely pass after rounding to zero; its stress pair and relative change retain full numerical precision (#687).

**Projects must change**
- Re-run FEA convergence checks whose stress changes were affected by rounding to 0.01 MPa; convergence records now contain unrounded numerical values. Display summaries remain rounded (#687).
