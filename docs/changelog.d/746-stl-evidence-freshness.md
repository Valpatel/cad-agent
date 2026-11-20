**Fixed**
- Printed-part checks verify a declared `stl_sha256` against the current STL and fail with a rebuild action when it cannot be verified. `export_print_stl` records the digest after any mesh rewrite; legacy records keep their status with an explicit freshness-not-recorded note (#746). This checks byte drift, not geometry correctness or physical print quality.
