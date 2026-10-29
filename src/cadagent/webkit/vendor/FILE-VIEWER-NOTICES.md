# Original-file viewer dependencies

The viewer fetches no runtime CDN resources. `file-viewer-sources.json` records exact
versions, upstream revisions, npm package integrity and SHA-256 hashes of the
vendored files. No project-specific CAD models are bundled here.

## STEP: occt-import-js 0.0.23 and Open CASCADE Technology

- Importer source and build instructions: https://github.com/kovacsv/occt-import-js/tree/c2148e54b456b571238d35cac037d304053d64b2
- Exact importer source archive: https://github.com/kovacsv/occt-import-js/archive/c2148e54b456b571238d35cac037d304053d64b2.tar.gz
- npm distribution: https://registry.npmjs.org/occt-import-js/-/occt-import-js-0.0.23.tgz
- Its OCCT submodule is revision `d2abb6d844231cb8f29be6894440874a4700e4a5`:
  https://github.com/Open-Cascade-SAS/OCCT/tree/d2abb6d844231cb8f29be6894440874a4700e4a5
- Exact OCCT source archive: https://github.com/Open-Cascade-SAS/OCCT/archive/d2abb6d844231cb8f29be6894440874a4700e4a5.tar.gz

`occt-import-js/occt-import-js.js` and `.wasm` are unmodified npm distribution
binaries. The importer is licensed under LGPL 2.1. OCCT is licensed under LGPL 2.1
with its additional exception. Full texts are beside the binaries:
`license.occt-import-js.txt`, `license.occt.txt`, `LICENSE_LGPL_21.txt`, and
`OCCT_LGPL_EXCEPTION.txt`. Importer C++ sources, CMake configuration, submodule
reference (`SUBMODULES.gitconfig`, a visible copy of upstream `.gitmodules`) and upstream build scripts are also supplied in `occt-import-js/source/`.
The complete corresponding OCCT source is available from the exact archive above;
it is not a runtime dependency and is not embedded into the static site's assets.

The library runs in a separate, dedicated classic worker. Users may inspect,
modify and replace it: rebuild the exact source using its documented Emscripten
and CMake setup, then replace the adjacent `occt-import-js.js` and
`occt-import-js.wasm` files together. Preserve the `occtimportjs` factory and
`ReadStepFile` interface, or adapt `file-step-worker.js` to the replacement's API.
No application relink, account, remote service or proprietary decoder is required.
Serve the replacement with JavaScript and `application/wasm` MIME types and clear
or change the deployment cache version. The worker locates the WASM beside the JS.
The runtime WASM is 7,604,031 bytes, below Cloudflare's 25 MB per-asset limit.

The application does not restrict debugging or reverse engineering needed to
modify these libraries. These source and replacement details apply to this pinned
build; an upgraded binary requires a fresh provenance and license review.

## STL and 3MF: Three.js r160

- Official source: https://github.com/mrdoob/three.js/tree/r160
- STL: https://github.com/mrdoob/three.js/blob/r160/examples/jsm/loaders/STLLoader.js
- 3MF: https://github.com/mrdoob/three.js/blob/r160/examples/jsm/loaders/3MFLoader.js
- License: `file-parsers/THREE-LICENSE.txt` (MIT).

The parser copies differ from upstream only in import paths: `three` points to the
existing self-hosted Three module, and the 3MF loader's fflate import points to its
adjacent copy. The worker cannot inherit the document's import map. The application
wrapper validates geometry and applies the file's declared units; it does not
modify the loaders' tessellation or substitute another file.

`file-parsers/fflate.module.js` is Three r160's unmodified fflate 0.6.9 copy.
Its MIT license is `file-parsers/FFLATE-LICENSE.txt`.
Source: https://github.com/101arrowz/fflate/tree/v0.6.9

## Worker XML DOM: LinkeDOM 0.18.12

`linkedom/worker.js` is the unmodified, self-contained worker module from
https://registry.npmjs.org/linkedom/-/linkedom-0.18.12.tgz . It supplies the XML DOM
API needed by the official 3MF loader in a worker. Source:
https://github.com/WebReflection/linkedom/tree/v0.18.12 . The ISC license is in
`linkedom/LICENSE`.
