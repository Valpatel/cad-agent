# @sunbox/occt-import-js 0.0.28

This release makes the packaged OCCT runtime directly usable by browser workers and improves STEP, IGES, and BREP import throughput.

## Changes

- Release WASM is compiled with `-O3` instead of size-first `-Oz`. On the repository STEP benchmark, median import time fell from 1674 ms in 0.0.25 to 975 ms in 0.0.28, a 41.7% improvement.
- `dist/occt-import-js-worker.js` now loads the generated ESM module correctly, caches the module, WASM bytes, and OCCT instance, preserves cache-busting query parameters, and retries resources after initialization errors.
- The worker accepts `{ format, buffer, params }` and posts the native import result. Consumers can transfer the input buffer without an additional copy.
- The distribution now marks its generated JavaScript as ESM, so the package entrypoint can be imported directly from Node.js. CommonJS `require()` consumers must move to `import`.
- Unix and Windows release builds now generate the same worker and ESM package metadata.
- The shipped Node.js and browser examples now execute the ESM entrypoint and provide WASM bytes explicitly where Node.js requires them.

## Compatibility

The generated runtime is ESM. Browser consumers should use a module import or the packaged worker; classic-script globals and `importScripts` are no longer part of the supported contract.
