**Changed**
- `cadagent.review.gates.motion`: a revolute joint that carries no other joint, and whose moving parts each measure as a body of revolution or an N-fold pattern about the joint axis, has each distinct pose queried once: one pose for a shaft, one period for a lugged wheel. The symmetry is measured from the solids (`cadagent.review.gates.symmetry.rotational_symmetry`), within the volume and boundary-point differences the verdict reports; a part that is not symmetric is queried at every sample as before. A two-joint example at `max_step_deg=2` went from 720 kernel queries to 32 (#724).
- The motion verdict gains `density[].symmetry`, `stats.symmetric_joints`, `stats.symmetry_queries`, `limits.symmetry` and one assumption line; `symmetry=False` (`cad: gates: motion: {symmetry: false}`) restores the old behaviour (#724).

**Projects must change**
- Nothing is required. A project that shortened a full-turn range by hand to one period because the motion gate was slow can declare the real range again: the gate now measures the symmetry itself and says so in the verdict (#724).
