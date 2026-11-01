**New**
- `cadagent.simulation.fea.Study.layer_check(normal)` checks a printed part's stress against its layers, for a print
  whose layer normal (build direction) is `normal`. Two checks run at every element corner. The bond check takes
  √(max(σn, 0)² + 3τn²) against the across-layer allowable. The bulk check takes von Mises against the in-plane
  allowable. It returns per-element factors and modes, the safety factor, the governing check and the worst corner
  (`LayerCheck`; `as_dict()` for records). The interlayer shear allowable is on no data sheet, so it is assumed to be
  S_z / √3 unless `strength_shear` is given. It is a screening check of the isotropic stress, not a qualification:
  test a printed part (#144).
- Every printed material in `MATERIALS` has `layer_strengths_mpa` (X-Y, Z), which `layer_check` defaults to.
  - The Z allowable is the row's strength.
  - The X-Y allowable is that strength times the lowest X-Y / Z tensile strength ratio of the sheet editions read, so
    it sits at least as far below each sheet's in-plane strength, as a ratio: PLA 27.9, PETG 24.6, PETG-CF 26.6,
    PAHT-CF 78.3 and TPU 95A 9.8 MPa.
  - The humid PA6-CF rows share their two strengths, 40.8 / 18.1 MPa.
  - No existing result changes (#144).
- `Study.solve()` keeps the corner stress tensors as `Study.sig_corner` (elements × 4 corners × 3 × 3, MPa), for checks
  of your own (#144).
- `Study.result['material_data']` records the material data a study used (#144):
  - the built-in row's `key`;
  - E and the print direction it is for, ν, the strength, the layer allowables and the density;
  - `source`, and `note`, which names the data sheet and its edition;
  - `constants_hash`, a hash of the constants.
- `material_changes(old, new)` lists what differs between the material data of two records (study results, their
  `material_data`, `export_viewer()` files or `Material`s). A record made on one toolkit and checked on another then
  shows a changed material as a material change, not a design change (#144).
