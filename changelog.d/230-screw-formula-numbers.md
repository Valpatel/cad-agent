**Fixed**
- `cadagent.formulas.nut_factor`, `thread_radial_pressure`, `boss_hoop_stress` and `screw_boss` take any real number.
  `np.float32`, NumPy integers such as `np.int64`, and `Decimal` used to be refused even in range wherever they
  were checked (`nut_factor`'s flank angle, and every argument of the other three), with a message that wrongly said
  they were out of range; `nut_factor`'s other arguments were not checked, and a `Decimal` there raised a
  `TypeError`. They are now used as their float values. (`np.float64` subclasses
  `float` and was always accepted.) A bool, a string or `None` is refused with a message saying it is not a real
  number. The range checks are unchanged (#230).

**Changed**
- `cadagent.formulas.nut_factor` now checks every argument, not only the flank angle. A NumPy array, which used to
  give an array of K, is refused, and so are a bool and a NaN (#230).

**Projects must change**
- To sweep `nut_factor` over several diameters, pitches or frictions, call it once per value (#230).
