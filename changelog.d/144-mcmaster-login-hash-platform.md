**New**
- `cadagent.review.evidence.geometry_identity(shape)`: an optional identity of a solid that does not depend on the
  platform. It holds the volume, the centre of mass and the inertia (tensor and principal moments), rounded, with the
  tolerance it matches to (relative 1e-6 by default) in the record. Compare two with `identity_mismatches(a, b)`. An
  x86-64 and an aarch64 host gave matching identities for all 43 solids of a vendor STEP and for 12 public test
  solids, while they shared 4 of 43 and 4 of 12 content hashes. It is not a hash: different solids can share one, so
  it explains a hash mismatch and never signs anything off (#144).
- `cadagent.review.evidence.hash_platform()` names what a content hash depends on besides the shape: the CPU
  architecture, the system, and the OCP version and package. `hash_platform_note(recorded, current)` says when two
  differ (#144).

**Changed**
- `exports/dossier-geometry.json` records `hash_platform` next to `hash`. The gates leave it out of the geometry
  digest (`VOLATILE_TOP`), so a record rebuilt with this release has the same digest as before and no verdict goes
  stale. Committed records show the new field once, and it differs between builders on different machines, like
  `actor` (#144).
- Reviewer records (`dossier/reviews/*.json`) carry the `hash_platform` of the bundle they were written against.
  When a review goes stale (`review-stale`, `stale-hashes`) and the geometry was rebuilt on another platform, the
  message names both platforms: the hashes may have changed with the platform, not the geometry (#144).
- `shape_content_hash`'s docstring says the hash is tied to the CPU architecture as well as to the OCCT version.
  `tools/volume_probe.py` receipts record `machine` (#144).
- `cad-agent mcmaster`: after McMaster asks for a login, the run asks for no more product pages. Each part still to
  download is reported as not fetched, and the command exits 1 (#144).
- The FEA docs (`docs/toolkit.md`) and the `cad-remote-runs` skill explain how to run the FEA on aarch64 Linux.
  PyPI has no aarch64 wheel for gmsh 4.15.2 (nor for pypardiso's MKL). Use conda-forge's gmsh, from micromamba,
  linked into the venv, and preload that environment's OpenSSL if `import gmsh` asks for `OPENSSL_3.4.0` (#144).

**Fixed**
- `cadagent.mechanical.mcmaster`: a product page that shows McMaster's login prompt ("Log in to view Product Detail")
  raises `LoginRequired`, a `RuntimeError`. Its message says McMaster asked for a login and the part number may be
  fine. It points to the public search page for the price and to the maker's datasheet for the ratings. It used to
  say "not a product page (no specification table)", which read as a wrong part number. The prompt is read from
  the page's visible text only, so the header's "Log in" link does not count (#144).

**Projects must change**
- Once a reviewer record has been submitted with this release, lint the dossier with this release or a later one.
  Earlier releases reject the record's new `hash_platform` key as unknown and count the review as invalid. No
  existing hash, record or verdict changes (#144).
- A receipt that pins `shape_content_hash` values (a vendor-solid probe, for example) can be checked only on the
  platform that made it. Record `hash_platform()` with it, and match solids by `geometry_identity` where a check
  must pass on any host (#144).
