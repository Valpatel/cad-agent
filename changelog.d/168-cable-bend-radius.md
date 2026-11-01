**New**
- `cadagent.mechanical.connectors.cable_bend`: checks that the cable behind a plug can turn at its minimum bend radius
  before it meets a wall, a part or the next plug. Give a mate a `cable` with its diameter and the radius as the data
  sheet states it (`{"mm": 25}` or `{"x_od": 5}`); the check turns the cable each way across the mating axis and
  returns pass, warn or fail with the clearance, the direction that works and the assumptions it made. It takes CAD
  shapes or panel-frame boxes (no CAD kernel needed for those), and `bend_reach()` gives the room a bend needs in
  closed form (#168).
- `check_ports()` runs the cable check for every mate that has a `cable`, against the printed parts and the other
  ports' plugs, and fails a port whose cable cannot turn. Mates without a `cable` are checked as before (#168).
- A figure of the check, `docs/img/motion/cable-bend.svg`, on the connector-window port: a Cat6 cord turned down runs
  1.35 mm into the shelf the enclosure stands on; turned up, it clears. "Cable routes at an impossible bend radius"
  in `docs/common-issues.md` is now a checked row (#168).
