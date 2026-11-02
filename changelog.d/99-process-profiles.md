**New**
- `cadagent.manufacturing.process`: the cited process profiles (research/process-profiles.yaml) as typed values. A
  project can ask for a process's rules, minimums, tolerances, FDM layer factors by filament, or a shop's bend table, and
  every value carries its rule id and source id. Rules not verified in their source are marked `(u)` and refused for
  enforcement (#99).
- `cadagent.manufacturing.dfm.check`: minimum walls, holes, pins, gaps, bridges, overhangs, flanges and hole-to-bend
  distances held against every verified source, with the spread reported (pass, warn when sources disagree, fail when
  none is met), and whether a printed feature's stress crosses the layers, with the filament's data-sheet factors (#99).
- `cadagent.manufacturing.sheet_metal`: bend allowance, deduction, flat length, K-factor, shortest flange and relief for
  5052 and mild steel, from the shop's table first and the generic rules after (#99).
- Docs: [Process profiles in code](docs/process-checks.md), with three figures drawn from these modules (#99).

**Changed**
- `cadagent.manufacturing.fit_coupons` reads its hole undersize and fit allowances from the FDM profile by rule id;
  the numbers are unchanged (0.25 mm undersize, 0.25 mm slide, 0.3 mm free) (#99).
