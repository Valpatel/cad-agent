#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f build/wasm/emsdk/emsdk_env.sh ]; then
    source build/wasm/emsdk/emsdk_env.sh
fi

if ! command -v emcmake >/dev/null 2>&1 || ! command -v emmake >/dev/null 2>&1; then
    echo "Emscripten tools were not found. Install/source emsdk so emcmake and emmake are on PATH."
    exit 1
fi

emcmake cmake -B build/wasm -G "Unix Makefiles" -DEMSCRIPTEN=1 -DCMAKE_BUILD_TYPE=Release .
emmake make -C build/wasm

npm run test

mkdir -p dist
cp build/wasm/Release/occt-import-js.js dist/occt-import-js.js
cp build/wasm/Release/occt-import-js.wasm dist/occt-import-js.wasm
cp src/occt-import-js-worker.js dist/occt-import-js-worker.js
cp src/dist-package.json dist/package.json
cp occt/LICENSE_LGPL_21.txt dist/license.occt.txt
cp occt/OCCT_LGPL_EXCEPTION.txt dist/OCCT_LGPL_EXCEPTION.txt
cp LICENSE.md dist/license.occt-import-js.txt

echo "Distribution Succeeded."
