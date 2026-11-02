**New**
- `cadagent.manufacturing.sheet_metal.feature_to_bend` checks a hole or cut-out near a bend against every hole-to-bend
  rule on the rule's own datum: the tangent line for Hubs and Davis, and the inside face for Century Tywood (plus
  R tan(A/2), capped at R, so a bend past 90° earns no extra distance). A rule that states no datum is read from the
  tangent and only warns (#283).
- `cadagent.manufacturing.sheet_metal.check_bends` checks a bent part's flanges, relief depth and relief width. A
  value that clears only a shop's own number (its row or its rule), and not the strictest generic rule, warns.
  `rows=False` drops the shop's tooling rows (#283).
- With a shop named, `check_bends` also checks that shop's limits: the bend angles it makes (SendCutSend: 5–130°), no
  hardware on a part with a bend past 90°, the flanges of a four-sided box (with and without hardware), the channel
  base, and the shop's own relief depth (#283).
- `sheet_metal.bend` takes `g90`, `304` and `316` and reads SendCutSend's galvanised and stainless rows for them. Off
  the table, stainless takes the generic hard-metal rules and G90 the medium (steel) ones (#283).

**Fixed**
- Five SendCutSend rules were not marked `shop: sendcutsend`, so generic checks read them. They are the K range, the
  relief depth, the relief width, the corner-relief gap and the bend-angle tolerance. Off the shop's table, the
  strictest generic relief depth is now T + R (Davis, Century Tywood), not SendCutSend's T + R + 0.5 mm. The generic
  relief width is T (Hubs, Paulsen), not SendCutSend's T/2 (#283).

**Projects must change**
- Sheet DFM reports (`cadagent.manufacturing.dfm.check`) change in two ways. A relief narrower than T now fails where
  it used to warn (for example 0.9 mm on 1.6 mm sheet). Off a shop's table, the relief depth limit is now T + R, not
  T + R + 0.5 mm. `dfm.check` cannot name a shop, so use `sheet_metal.check_bends(..., shop=...)` for the shop's own
  rules (#283).
- In `check_bends`, a flange at exactly the shop's shortest flange now warns on most stocks, because the shop's rows
  are shorter than Century Tywood's 3.5 (T + R). Keep the flange or name the shop's tooling as the reason (#283).
