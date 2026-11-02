**Fixed**
- `cadagent.formulas.nut_factor`, `thread_radial_pressure`, `boss_hoop_stress` and `screw_boss` take any real number.
  `np.float32`, NumPy integers such as `np.int64`, and `Decimal` used to be refused even in range, with a message
  that wrongly said they were out of range. They are now used as their float values. (`np.float64` subclasses
  `float` and was always accepted.) A bool, a string or `None` is refused with a message saying it is not a real
  number. The range checks are unchanged (#230).
