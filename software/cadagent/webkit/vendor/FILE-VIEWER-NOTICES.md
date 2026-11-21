# Original-file viewer dependencies

The viewer fetches no runtime CDN resources. `file-viewer-sources.json` records exact
versions, upstream revisions, npm package integrity and SHA-256 hashes of the
vendored files. No project-specific CAD models are bundled here.

## STEP

The viewer uses `@sunbox/occt-import-js` 0.0.29 and Open CASCADE Technology (OCCT) 8.0.0. A dedicated worker imports
the ES module, loads its WebAssembly file from the same directory and tessellates the requested STEP bytes.

- Importer release 0.0.29 and its build. [Release](https://github.com/SunboX/occt-import-js/releases/tag/0.0.29) · [Upstream build](https://github.com/SunboX/occt-import-js/actions/runs/36069746500)
- Importer source, commit `ba1decadb3d19e4585d2c54deb2c4325f64b9ae9`. [Source archive](https://github.com/SunboX/occt-import-js/archive/ba1decadb3d19e4585d2c54deb2c4325f64b9ae9.tar.gz)
- OCCT submodule, commit `d3056ef80c9668f395da40f5fd7be186cae4501f`, also tagged `V8_0_0` by Open CASCADE. [Submodule](https://github.com/SunboX/OCCT/tree/d3056ef80c9668f395da40f5fd7be186cae4501f) · [Complete source archive](https://github.com/Open-Cascade-SAS/OCCT/archive/d3056ef80c9668f395da40f5fd7be186cae4501f.tar.gz)

The importer is licensed under LGPL 2.1 (`license.occt-import-js.txt`). OCCT is licensed under LGPL 2.1
(`LICENSE_LGPL_21.txt`, also distributed as `license.occt.txt`) with the Open CASCADE exception
(`OCCT_LGPL_EXCEPTION.txt`). These texts accompany the reader. The wheel includes the importer's C++ sources,
CMake configuration and build scripts under `occt-import-js/source/`.
`SUBMODULES.gitconfig` is the visible copy of upstream's `.gitmodules`.

### Build the browser reader

Copy `occt-import-js/source/` into a build workspace and extract the exact OCCT source above into its `occt/` subdirectory.
Activate Emscripten 3.1.69 with emsdk commit `a36df02dc438e8b02f91122a4c62eeecb6784272`. The recorded
Linux build uses CMake 3.31.6 and GNU Make 4.4.1. From the copied source root run

```sh
source_dir="$(pwd -P)"
emcmake cmake -S "$source_dir" -B build -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release \
  "-DCMAKE_C_FLAGS=-ffile-prefix-map=\"$source_dir\"=." \
  "-DCMAKE_CXX_FLAGS=-ffile-prefix-map=\"$source_dir\"=." \
  -DCMAKE_EXE_LINKER_FLAGS=-sDYNAMIC_EXECUTION=0
cmake --build build --target OcctImportJS
```

Both `build/Release/occt-import-js.js` and `build/Release/occt-import-js.wasm` come from this link step. Static bindings
let the worker import the module under the site's script policy. `file-viewer-sources.json` records the hashes of both
distributed files and the inputs used for this build. The public npm archive and the GitHub release for 0.0.29 contain
different WASM bytes. The receipt records the original hashes for each pair separately. A second link from the same
compiled objects produced identical JavaScript and WebAssembly in another output directory.

To replace the reader, serve the two files together as JavaScript and `application/wasm` and update the deployment
cache. The worker uses the module's default factory and its `ReadStepFile` interface. Users may modify, debug,
reverse-engineer and replace the library independently of the application.

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

## ZIP reader: fflate 0.8.3

`file-parsers/fflate.module.js` is the unmodified ES module build (`esm/browser.js`)
of https://registry.npmjs.org/fflate/-/fflate-0.8.3.tgz , and its MIT license,
`file-parsers/FFLATE-LICENSE.txt`, is the package's `LICENSE`.
Source: https://github.com/101arrowz/fflate/tree/v0.8.3 .
It replaces the fflate 0.6.9 copy that Three r160 bundles, because `unzipSync` in
0.6.9 can loop forever on a crafted ZIP64 directory entry (GHSA-px8p-9vwx-vf98,
fixed in 0.8.3). The 3MF loader and the worker call only `unzipSync` and `strFromU8`,
which keep their signatures in 0.8. Since 0.7 fflate throws `Error` objects, not strings,
so the worker turns any fflate or loader failure into its one generic message rather
than showing fflate's internal text.

## Worker XML DOM: LinkeDOM 0.18.12

`linkedom/worker.js` is the unmodified, self-contained worker module from
https://registry.npmjs.org/linkedom/-/linkedom-0.18.12.tgz . It supplies the XML DOM
API needed by the official 3MF loader in a worker. Source:
https://github.com/WebReflection/linkedom/tree/v0.18.12 . The ISC license is in
`linkedom/LICENSE`.
