**New**
- `cadagent.mechanical.linkages`: sweep a closed loop through its inputs. It handles a four-bar from its crank, and a
  five-bar from both cranks or along a tip path. Each step reports the joint angles, the pins, the transmission angle
  and the Jacobian determinants. Locks, cranks falling in line, the edge of reach and assembly flips are bisected
  between samples. Each report has a pass, warn or fail status, its reachable range and its stated limits.
  `fivebar_workspace` maps a grid of crank angles (#187).
- `cadagent.formulas`: the five-bar's closed forms `fivebar_point`, `fivebar_inputs` and `fivebar_jacobians`. Their
  positions are checked against the closed forms of Gonçalves, Carvalho and Santos (COBEM 2009). The Jacobians follow
  Gosselin and Angeles (1990) and are checked against finite differences (#187).
- `cadagent.simulation.robot.write_mjcf(..., loops=[LoopClosure(...)])` closes a loop in MuJoCo with an equality
  constraint. It first checks that the two links' pins meet at home (`loop_gaps`, `home_frames`) (#187).
- `cad-agent motion-trace`: a contract can declare closed loops under `loops`. Their inputs are sampled together and
  their other joints solved, on the circuit the loop reaches from home. A new `loop-pose` check fails a renderer
  that leaves a loop open, assembles it the other way or shows another circuit (#187).
- Linkages page: sweeping four- and five-bars, with an animated five-bar figure generated from the solver (#187).

**Changed**
- `Linkage`, `circles` and `ellipse_path` (the README hero's linkage helpers) moved to `cadagent.mechanical.linkages`.
  `cadagent.publish.anim.linkage` still re-exports them (#187).
