**Fixed**
- Printed snap-fit allowables (`cadagent.mechanical.compliant.allowables`) come from Bambu's current V3.0 data sheets,
  which give lower strengths than the V2.0 copies cited before. Single joining, along / across the layers: PETG-CF
  1.68 → 1.00 % (the old value was too generous: a snap sized with it can crack), PLA Basic 1.02 → 0.95 %, PLA Matte
  1.14 / 1.05 → 1.07 / 0.92 %, Bambu ASA 1.49 / 1.16 → 1.06 / 1.02 % (#156).
- Bambu PETG Basic V3.0 is a reformulated filament sold under the same name, and a spool does not say which it is.
  `petg-bambu-basic` takes the cautious one for each quantity, V3.0 for both: allowable 2.30 → 1.28 % along and
  0.96 % across, modulus for forces 1460 / 1120 → 2780 / 2550 MPa (#156).
- FEA humid PA6-CF rows (`pa6_cf_xy`, `pa6_cf_z`): the modulus takes the wet / dry modulus ratio of a water-saturated
  print (0.290 X-Y, 0.281 Z, Polymaker PA6-CF20 V1.1) instead of x0.6, a strength-like ratio; the strength takes the
  sheet's strength ratio (0.500, 0.472). E 2126 → 1029 MPa and 1042 → 488 MPa; strength 48.96 → 40.84 MPa and
  23.04 → 18.13 MPa (#157).
- FEA metals use design minimums from MIL-HDBK-5J instead of typical values: `al6061` yield 276 → 241.3 MPa (E 68900 →
  68258 MPa); `al7075` 503 → 461.9 MPa for sheet and plate up to 2 in thick (E 71700 → 71016 MPa, density 2.81 →
  2.80); `steel` 250 → 248.2 MPa (AISI 1025, the same 36 ksi minimum as ASTM A36; ν 0.29 → 0.32, density 7.86). Each
  note names its table; `cf_tube` is labelled a typical value (#157).

**Changed**
- `PrintedMaterial` keeps every data-sheet edition read, current first, as `sheets` (a `Sheet` each: maker, title,
  edition, PDF date, page, link and values). It takes the lowest allowable and the highest modulus for forces across
  them, and `derivation()` (the `cad-agent snapfit --output` JSON) names the edition behind each number (`xy.sheet`,
  `z.sheet`, `modulus.sheet`). `source` lists every sheet. Pinned by `tests/test_snapfit_sheets.py` (#156).

**Projects must change**
- Re-run `cad-agent snapfit` for printed snaps in `petg-cf-bambu` (allowable −41 %), `petg-bambu-basic` (−44 % along,
  −58 % across), `asa-bambu` (−29 % / −11 %), `pla-bambu-matte` (−6 % / −12 %) and `pla-bambu-basic` (−7 %): a snap
  whose root strain sits between the old and new allowable now fails. PETG Basic's mating and retention forces read
  1.9x (along) and 2.3x (across) higher (#156).
- Code that built `PrintedMaterial(name, source, e_mpa, uts_mpa, break_pct, ...)` passes `sheets=(Sheet(...), ...)`
  instead, and reads the values from `material.sheets[i]` (#156).
- Re-run FEA with `pa6_cf_xy` and `pa6_cf_z`: deflections read 2.07x and 2.14x larger (stiffness the inverse), and
  safety factors 0.83x and 0.79x; a force or stress worked out at a given travel falls with E (#157).
- Re-run FEA safety factors with `al6061` (0.87x), `al7075` (0.92x) and `steel` (0.99x); aluminium deflections read
  about 1 % larger. For 7075 cut from plate thicker than 2 in, replace the row's strength with the handbook's for the
  stock (down to 54 ksi, 372 MPa, at 3.5–4 in) (#157).
- Printed-part FEA deflection checks not re-run since #125 (v0.5.0) read 31–147 % larger now than before it (TPU
  305 %); re-run them with this release's values (#157).
