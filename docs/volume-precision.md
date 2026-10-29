# Curved-solid volume precision

Tracking: issue #70. This investigation concerns numerical volume measurement in the generic relation gate. It does not qualify hardware fit or weaken collision/volume-conservation tolerances.

A private manufacturer screw/insert fixture from Gyropup produced a default measured cut volume larger than the original solid. Holding the Common/Cut BREP results fixed and changing only the `BRepGProp.VolumeProperties` integration overload changed the results:

| Integration | A − Common − Cut(A,B), mm³ | B − Common − Cut(B,A), mm³ |
| --- | ---: | ---: |
| Default overload | -14.11652803 | -4.58890513 |
| Adaptive, requested relative error 1e-6 | 0.00023872 | 0.00007781 |
| Adaptive, requested relative error 1e-8 | 0.00027073 | 0.00006440 |

The diagnostic ran against cad-agent `28abd34` / OCP7.9.3.1.1 and took151s. This identifies a measurement problem in that fixture; it does not establish that every previously unknown Boolean relation was correct. Manufacturer geometry stays private. Numerical receipts, input hashes and a generic reproducer will accompany the implementation.

OCCT documents the explicit floating-point Eps overload as adaptive integration, returning an estimated relative error. A requested precision is not itself evidence of the achieved accuracy. See the [OCCT BRepGProp reference](https://occt3d.com/dev/doc/refman/html/class_b_rep_g_prop.html) and installed OCP7.9 bindings for the runtime API. The correction must inspect returned estimates, compare refinements and keep numerical uncertainty from silently deciding a near-threshold relation.

Next: implement and test bounded integration, cache-version invalidation and non-finite/error handling; exercise public authored curved solids and rigid transforms; reproduce the private pair remotely; obtain independent review and current CI. No installed toolkit or product geometry changes before review.
