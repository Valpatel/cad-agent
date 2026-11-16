**New**
- Robot simulation replay: the featured example is now Gyropup, a work-in-progress wheel-legged robot, in four recorded MuJoCo scenarios from its dated snapshot (kerb drop, plank, push recovery, landing), chosen in the viewer, with the snapshot's own pass verdict and peak motor torque against its limit. Replayed, not recomputed; the two-link arm stays as the editable example (#798).
- Replay format: optional mesh parts from a packed `cad-agent-model/1` library (`loadMeshLibrary`), fixed `scenery`, `opacity`, a camera-followed body (`view.follow`), and a `cad-agent.replay-index/1` of named recordings with summaries (`loadReplayIndex`, `createReplayViewer({scenarios})`, `selectScenario`) (#798).
- `docs/examples/robot-replay/gyropup.py` converts Gyropup's recorded snapshot to that format with a receipt of source hashes; `--check` verifies. It needs no MuJoCo (#798).

**Changed**
- The home and toolkit "Robot simulation replay" cards move: a lazy still, swapped for an animated capture only once the card nears the screen, never under reduced motion or Save-Data (#798).
