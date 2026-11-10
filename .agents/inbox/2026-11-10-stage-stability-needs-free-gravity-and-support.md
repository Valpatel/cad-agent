# A still assembly stage needs free gravity and force-bearing support before a stability claim

Date: 2026-11-10. Scope: generic explicit stage settling through the existing MuJoCo robot capability (#515).

## Evidence

A bounded 500-step study at 0.002 s on MuJoCo 3.17.0 used a 20 mm, 0.1 kg cube. With gravity -9.81 m/s² Z,
the floor-supported cube moved at most 0.1751305 mm, carried 0.981 N in contacts and settled. Without its
support it fell 4914.81 mm and reached 9810 mm/s. Both zero-gravity and implicitly fixed-body controls showed
zero drift with no support contact. Zero drift by itself therefore accepts two invalid stability claims.

The first timestep regression imposed a 0.05 mm coarse-to-fine transient agreement:

```text
python3 -m pytest -q tests/simulation/test_robot.py -k stage
1 failed, 22 passed, 22 deselected in 1.44s
assert 0.06072981203104727 < 0.05
```

The failed bound was retained and the response was to investigate the numerical behavior:

| Timestep | Peak COM drift/penetration (mm) | Final COM displacement (mm) | Final normal force (N) |
| --- | ---: | ---: | ---: |
| 0.002 s | 0.1751305273 | 0.1077554202 | 0.9810000000 |
| 0.001 s | 0.1144007152 | 0.1077554202 | 0.9810000000 |
| 0.0005 s | 0.1077554232 | 0.1077554202 | 0.9810000000 |
| 0.00025 s | 0.1077554302 | 0.1077554205 | 0.9810000000 |

All four remain inside the declared 0.5 mm criterion, with zero solver warnings, but the 2 ms transient peak
is not converged. The regression retains three timestep levels, requires unchanged classification and weight
balance, and checks the 1 ms to 0.5 ms peak difference against 0.02 mm. These are analytic fixture controls,
not product evidence or permission to choose a criterion after observing a product failure.

The complete existing robot and new stage/layout/areas suite then passed:

```text
python3 -m pytest -q tests/simulation/test_robot.py tests/repo/test_layout.py tests/repo/test_areas.py
81 passed, 1 pre-existing webkit-folder warning in 9.03s
```

## Cause and corrective rule

Kinematic fixing, zero/cancelled gravity, hidden controllers/constraints or damping can create apparent stability.
Require explicitly free monitored rigid groups, declared fixed primitive fixtures, actual nonzero gravity and
enabled contacts. Reject implicit retention, gravity compensation, ambient callbacks and external files.
Check maximum motion over the entire finite window, terminal speeds, force-bearing support paths, penetration,
solver warnings/nonfinite values and time resets. Preserve the complete model/asset hashes and effective settings.
A warning/reset cannot be accepted merely because the simulator restored the starting pose.

Use refinement controls for a numerical stability claim and distinguish classification robustness from a
converged transient measurement. MuJoCo soft contact penetration is a modeled solver result, not manufactured
interference clearance. Its [collision documentation](https://mujoco.readthedocs.io/en/stable/computation/#checking)
also explains why a nonconvex mesh hull cannot represent a bearing bore or other insertion passage.

## Limits

First scope: independent rigid groups, fixed descendants and primitive collision geoms; no inferred masses,
retention, internal assembly or fixtures from viewer meshes. A passing finite settle does not establish
indefinite stability, source-to-product correspondence, tolerance/compliance, fastening or physical readiness.
Long native product scenarios remain detached compute-host runs with external runtime caps and receipts.
