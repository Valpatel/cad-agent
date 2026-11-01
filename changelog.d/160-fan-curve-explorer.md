**New**
- `cadagent.formulas`: `fans_in_series` and `fans_in_parallel` (identical fans: pressures add at one flow, flows add
  at one pressure) and `fan_stall_flow` (the peak that ends the curve's last rise; below it, the stall region), with
  hand-solved tests (#160).
- `cadagent.thermal.fans`: the ebm-papst W2G115-AD15-13's curves at 8, 12 and 16 V, read from the datasheet's vector
  chart. Solved on the datasheet's own system curves, they give back every operating point it tabulates (#160).
- The fan-curve explorer, `<cad-fan-curve>`, on the new Airflow and fans page and on Engineering formulas. Pick the
  voltage, the pressure your enclosure needs at 100 m³/h, and one to four fans in parallel or in series. It marks the
  operating point and the stall region, and warns when the point lands in it (#160).

**Changed**
- `fan_operating_point` also returns `stall`, true when the point is below `fan_stall_flow`. Code that compares its
  whole result with a dict must add the key (#160).
- `fan_operating_point`, `fan_curve_line` and `system_coefficient` refuse what has no answer with `ValueError`: NaN or
  infinite losses, a flow of 0 for the system point, and a shut-off pressure or free-air flow of 0 or less. A system
  point at zero flow used to raise `ZeroDivisionError` (#160).
