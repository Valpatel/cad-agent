# Curved-solid volume precision

Tracking: issue #70. This investigation concerns numerical volume measurement in the generic relation gate. It does not qualify hardware fit or weaken collision/volume-conservation tolerances.

A private manufacturer screw/insert fixture from Gyropup produced a default measured cut volume larger than the original solid. Holding the Common/Cut BREP results fixed and changing only the `BRepGProp.VolumeProperties` integration overload changed the results:

| Integration | A − Common − Cut(A,B), mm³ | B − Common − Cut(B,A), mm³ |
| --- | ---: | ---: |
| Default overload | -14.11652803 | -4.58890513 |
| Adaptive, requested relative error 1e-6 | 0.00023872 | 0.00007781 |
| Adaptive, requested relative error 1e-8 | 0.00027073 | 0.00006440 |

The diagnostic ran against cad-agent `28abd34` / OCP7.9.3.1.1 and took151s. This identifies a measurement problem in that fixture; it does not establish that every previously unknown Boolean relation was correct. Manufacturer geometry stays private. Numerical receipts, input hashes and a generic reproducer will accompany the implementation.

## Error estimates must match the actual algorithm

Independent review of draft PR #71 found that Gauss `VolumeProperties_s(..., Eps)` returns the **maximum face-relative error**, not a whole-solid relative bound. Multiplying it by net solid volume can underestimate uncertainty when positive and negative face contributions cancel. The initial two-refinement draft did this incorrectly and must not qualify parts.

The corrected draft uses `VolumePropertiesGK_s` with two requested tolerances, 1e-6 and 1e-8, `OnlyClosed=False`, `IsUseSpan=True`, and centroid/inertia flags disabled. In [OCCT 7.9.3 BRepGProp](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/src/BRepGProp/BRepGProp.cxx), this routine sums absolute face-error estimates at a common reference point, then divides by positive mass only above `Epsilon(1)`. The tiny positive-mass branch already returns an absolute error; multiplying it by mass would lose its uncertainty. The underlying [GK integrator](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/src/BRepGProp/BRepGProp_VinertGK.cxx) still supplies an estimate, not a mathematical interval proof.

The retained uncertainty is the larger of the fine aggregate absolute-error estimate and the two masses' difference. That uncertainty **consumes** the unchanged conservation budget, `0.01 + 1e-6 × max(part volumes)` mm³. Overlap and containment thresholds are unchanged. A threshold-straddling estimate or failed conservation check is `unknown`, never a clearance pass. Cache algorithm version 4 prevents results from older integration policies being reused.

## Validate geometry before measuring it

Solid count alone accepts an open shell wrapped as a solid. `BRepCheck_Analyzer` alone accepts an inverted closed solid whose interior includes infinity. Before broad-phase acceptance, assembly inputs must contain valid solids, exact face surfaces, no free faces outside their solids, and every solid must classify infinity as `OUT`. Source geometry is rejected, not silently repaired or reoriented. Boolean results receive the same geometric checks before measurement. A valid empty or lower-dimensional Boolean result has zero volume; it cannot serve as an assembly part.

## Centroids are optional witnesses

Enabling GK centroid moments made a public full-sphere refinement take 3.8–5.7 seconds instead of 0.0003–0.0007 seconds; span splitting did not fix this. Mass decisions therefore do not compute centroid moments. An overlap's optional centroid uses separate Gauss refinements and is labeled approximate. If those points differ by more than 1e-6 mm or are invalid, the point is omitted with its reason. This does not change the relation decision. In particular, mass-only GK properties do **not** provide a computed centroid.

## Reproduce without publishing supplier geometry

`tools/volume_probe.py prepare <private-directory> --a <a.step> --b <b.step> --location-a '<JSON translation or matrix>' --location-b '<JSON translation or matrix>'` computes Common/Cut once and saves private BREP inputs with hashes and transforms. Run `tools/volume_probe.py measure <private-directory> --method default`, `--method gauss`, and `--method gk` against those fixed files. Receipts record input and BREP hashes, source hashes, exact commit/runtime, residuals, estimated error, elapsed time and the unchanged budget. Preparation refuses to overwrite an existing bundle. The BREP bundle stays private; sanitized numerical receipts may be committed.

Public tests use analytic asymmetric Bezier solids of revolution and thin shells, rigid placements, independently calculated centroids, invalid/open/inverted solids, missing surfaces, invalid integration outputs, tiny-mass error units, threshold uncertainty, conservation-budget consumption and old-cache invalidation. Existing sphere, curved-cap, containment and synthetic 100-part timing tests remain applicable.

Next: reproduce the private pair remotely, obtain independent review and current CI. No installed toolkit or product geometry changes before review. Passing numerical controls does not qualify thread engagement, assembly access, printed fit, material strength or electrical readiness.
