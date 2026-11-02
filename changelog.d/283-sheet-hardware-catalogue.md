**New**
- `research/sheet-hardware.yaml` is a catalogue of the bought parts for bent sheet-metal parts. It lists 26 PEM clinch
  nuts, studs and standoffs and 4 McMaster-Carr blind rivets, each with its dated price, stock count, seller page and
  source. Where SendCutSend presses a part in, it also gives SendCutSend's price for doing so. It uses cad-agent's
  part-catalogue layout (#283).
- `cadagent.mechanical.sheet_hardware` loads that catalogue and refuses any item that is not a part the clinch or
  rivet checks know. `choose_clinch` and `choose_rivet` rank, by price, only the parts the checks already accept.
  `cost` totals the pieces, the whole packs, and a shop's price to press the parts in (#283).
- The `sheet-metal-hardware` skill walks an agent through a bent plate with clinch hardware and rivets, in order:
  bends, holes near bends, clinch placement, riveted seams, then price (#283).
- `docs/sheet-metal-hardware.md` shows the prices in a chart drawn from the catalogue, the common cheap choice, where
  to buy and how to keep the data current (#283).
