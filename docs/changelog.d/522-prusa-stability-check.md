**Fixed**
- `cad-agent slice` with PrusaSlicer: the print-stability check now runs with Prusa's stock MK4S and XL input-shaper
  profiles. Those set supports "for support enforcers only", and PrusaSlicer then skips the check, so a part with a
  large unsupported overhang sliced as ok with no warning. When the profile supports enforcers only, the 3MF carries
  no support data of its own and `cad.slicer.overrides` does not set `support_material`, the part is sliced with
  `support_material = 0`: the same toolpaths, and PrusaSlicer looks (#522).

**New**
- PrusaSlicer slice rows record `supports` (`none`, `enforcers only`, `automatic` or `set in the model`),
  `stability_checked` and `stability_note`. With automatic supports, enforced layers, an override that turns supports
  on, or a 3MF that carries support data of its own (whatever the profile says), the slice is left alone,
  `stability_checked` is false and `cad-agent slice` says the check is not known to have run: `ok` then means only
  that the part sliced (#522).

**Projects must change**
- PrusaSlicer projects on a stock MK4S or XL input-shaper profile: slice again. A part with unsupported overhangs
  that sliced as ok may now be `NOT OK`, and `cad-agent slice` then exits 1. Fix the geometry, or turn supports on
  in `cad.slicer.overrides` knowing the stability check then does not run (#522).
