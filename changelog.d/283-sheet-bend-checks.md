**New**
- `cadagent.manufacturing.sheet_metal.feature_to_bend` checks a hole or cut-out near a bend against every hole-to-bend
  rule on the rule's own datum: the tangent line for Hubs and Davis, and the inside face (plus R tan(A/2)) for Century
  Tywood. A rule that states no datum is read from the tangent and only warns (#283).
- `cadagent.manufacturing.sheet_metal.check_bends` checks a bent part's flanges, relief depth and relief width. With a
  shop named, it also checks that shop's largest bend angle, four-sided box flanges (with and without hardware) and
  channel base (#283).
- `sheet_metal.bend` takes `g90`, `304` and `316` and reads SendCutSend's galvanised and stainless rows for them. Off
  the table, it uses the generic rules for hard metal (#283).

**Fixed**
- Five SendCutSend rules (K range, relief depth, relief width, corner-relief gap, bend-angle tolerance) were not marked
  `shop: sendcutsend`, so generic checks read them. Off the shop's table, the strictest generic relief depth is now
  T + R (Davis, Century Tywood), not SendCutSend's T + R + 0.5 mm (#283).

**Projects must change**
- Sheet DFM reports off a shop's table may show a shallower generic relief depth. Name the shop to check its own
  (#283).
