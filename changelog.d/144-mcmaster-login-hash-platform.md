**New**
- `cadagent.review.evidence.geometry_identity(shape)`: an optional identity of a solid that does not depend on the
  platform. It holds the volume, the centre of mass and the inertia (tensor and principal moments), rounded, with the
  tolerances it matches to (relative 1e-6 by default) in the record. Each principal moment has its own tolerance,
  never below a thousandth of the largest moment's, so a slender part's small moment is compared to itself, not to
  its length. Compare two identities with `identity_mismatches(a, b)`. An x86-64 and an aarch64 host gave matching
  identities for all 43 solids of a vendor STEP and for 12 public test solids, while they shared 4 of 43 and 4 of 12
  content hashes. It is not a hash: different solids can share one, and a change below the tolerance is not seen, so
  it explains a hash mismatch and never signs anything off (#144).
- `cadagent.review.evidence.hash_platform()` names what a content hash depends on besides the shape: the CPU
  architecture, the system, the C library, and the OCP version and package. `record_hash_platform(record)` reads it
  from a geometry record. `hash_platform_note(recorded, current)` says when two records differ. Equal records do not
  promise equal hashes, since not everything the kernel's arithmetic depends on is named (#144).

**Changed**
- `exports/dossier-geometry.json`: `hash` is now `{"recipe": ..., "platform": hash_platform()}`, where it was the
  recipe string. Every release, this one and earlier ones, leaves `hash` out of the gates' geometry digest, so a
  record rebuilt with this release has the same digest and no verdict or packet goes stale. Committed records show
  the change once, and the platform differs between builders on different machines, like `actor` (#144).
- Reviewer records (`dossier/reviews/*.json`) carry the platform of the bundle they were written against, in
  `bundle.hash_platform`. Earlier releases accept and ignore it. When a review goes stale (`review-stale`,
  `stale-hashes`) and the geometry was rebuilt on another platform, the message names both platforms: the hashes may
  have changed with the platform, not the geometry. A geometry or reviewer record from before this release names no
  platform, and the message stays as it was (#144).
- `shape_content_hash`'s docstring says the hash is tied to the CPU architecture as well as to the OCCT version.
  `tools/volume_probe.py` receipts record `hash_platform` (#144).
- `cad-agent mcmaster`: after McMaster asks for a login, the run asks for no more product pages. Each part still to
  download is reported as not fetched, and the command exits 1 (#144).
- The FEA docs (`docs/toolkit.md`) and the `cad-remote-runs` skill explain how to run the FEA on aarch64 Linux.
  PyPI has no aarch64 wheel for gmsh 4.15.2 (nor for pypardiso's MKL). Use conda-forge's gmsh, from micromamba,
  linked into the venv, and preload that environment's OpenSSL if `import gmsh` asks for `OPENSSL_3.4.0` (#144).

**Fixed**
- `cadagent.mechanical.mcmaster`: a product page that shows McMaster's login prompt ("Log in to view Product Detail")
  raises `LoginRequired`, a `RuntimeError`. Its message says McMaster asked for a login and the part number may be
  fine. It points to the public search page for the price and to the maker's datasheet for the ratings. It used to
  say "not a product page (no specification table)", which read as a wrong part number. The prompt is read from the
  text a reader sees: the browser's rendered text, or, from saved HTML, the text outside scripts, styles and hidden
  elements. So neither the header's "Log in" link nor a hidden login dialog counts (#144).

**Projects must change**
- Code that reads `hash` in `exports/dossier-geometry.json` as the recipe string reads `hash["recipe"]` now (a
  record from an earlier release still has the string). No hash, digest, record or verdict changes, under this
  release or an earlier one (#144).
- A receipt that pins `shape_content_hash` values (a vendor-solid probe, for example) can be checked only on the
  platform that made it. Record `hash_platform()` with it, and match solids by `geometry_identity` where a check
  must pass on any host (#144).
