# Valid CAD can hide non-manifold tangent boss contacts

2026-10-26 evidence: `cad/build.py` failed with `GeometryError: non-watertight STL: exports/2port_base.stl`. A readback showed CAD valid, one solid, 7896 mesh faces and six edges whose incidence was not two. Those edges ran from Z2.4 to Z7.4 at corner boss/wall tangencies.

Cause: a Ø9.2 boss centered 4 mm from the PCB edge touches the housing inner wall at −0.6 mm without positive overlap. Corrective rule: give joined features positive volume overlap; do not treat valid BREP or visually touching solids as sufficient print-mesh evidence. Corner bosses changed to Ø9.6, giving 0.2 mm overlap. Re-run native solid, STL and 3MF checks after geometry changes. Limits: a watertight mesh does not demonstrate strength, fit or printability.
