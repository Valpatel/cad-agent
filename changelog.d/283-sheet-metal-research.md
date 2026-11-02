**New**
- `research/sheet-metal-guides.md` surveys the design guides for bent sheet metal, self-clinching (PEM-type) hardware
  and blind rivets before any rule is written. It covers SendCutSend, Protolabs, OSH Cut, PEM, Stanley POP, Marson,
  Avdel, GESIPA, FAA AC 43.13-1B, NASA RP-1228 and MIL-HDBK-5J, plus the paid standards cited by number and title. For
  each guide it records authority, coverage, terms and date, picks a primary source per topic, and lists where the
  sources disagree and by how much. It also decides whether to adopt, wrap, borrow or build for each open-source tool.
  The registry gains 52 sources and 11 unread entries, among them the gated guides from Xometry, Fictiv and Protocase
  (#283).
- `research/sheet-metal.md` is a deep dive into SendCutSend (materials, cutting, bending, hardware, taps, countersinks,
  dimples, finishes and pricing) beside the generic bending and cutting rules. The bend-deduction formula reproduces
  SendCutSend's published values within 0.005 in for 53 of its 56 bend stocks (#283).
- `research/sheet-metal-joining.md` covers PEM nuts, studs and standoffs (hardness, hole, edge, bend and spacing rules,
  strengths and prices for the common sizes) and blind rivets (types, strength by maker, grip, hole, edge distance,
  pitch, the joint checks with a worked example, and galvanic pairing). It also lists where SendCutSend's hardware data
  disagrees with PEM's (#283).
- `research/process-profiles.yaml` gains named shop profiles. SendCutSend's limits and tables are rules marked
  `shop: sendcutsend`, which `cadagent.manufacturing.process` loads only when a caller names the shop
  (`rules_for(..., shop="sendcutsend")`, `limits(..., shop=...)`, `Profiles.shop(id)`), so the generic rules stay
  supplier-neutral. New supplier-neutral `sm-clinch-*` and `sm-rivet-*` rules cite PEM, POP, the FAA, NASA, MIL-HDBK-5J
  and GESIPA (#283, #284).
- Four new figures in `docs/img/sheet-metal/`: a bent plate with a clinch nut and rivets laid out by the rules, the
  shop's hardware distances, the hardest sheet for each clinch-fastener material, and rivet edge distance and pitch by
  source (#283).
