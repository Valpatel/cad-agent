# occt-import-js

The [emscripten](https://emscripten.org) interface for [OpenCascade](https://www.opencascade.com) import functionalities. It runs entirely in the browser, and allows you to import brep, step and iges files and access the result in JSON format.

[![npm package](https://img.shields.io/npm/v/%40sunbox%2Focct-import-js?label=npm%20package)](https://www.npmjs.com/package/@sunbox/occt-import-js)
[![WASM Build](https://github.com/SunboX/occt-import-js/actions/workflows/wasm_build.yml/badge.svg)](https://github.com/SunboX/occt-import-js/actions/workflows/wasm_build.yml)
[![Native Build](https://github.com/SunboX/occt-import-js/actions/workflows/native_build.yml/badge.svg)](https://github.com/SunboX/occt-import-js/actions/workflows/native_build.yml)

See it in action in [Online 3D Viewer](https://3dviewer.net/#model=https://dl.dropbox.com/s/utieopxrxwujgmd/as1_pe_203.stp), or check [this fiddle](https://jsfiddle.net/kovacsv/rzhq9gxj) for a code example.

## 0.0.29 release

The packaged worker now posts initialization and fetch failures to its caller
without an uncaught worker exception. The next request can retry a failed
resource. See the [0.0.29 release notes](docs/release-notes-v0.0.29.md).

## 0.0.28 release

Version 0.0.28 ships an ESM factory and reusable module worker, builds the
release WASM with `-O3`, and caches the factory, WASM bytes, and OCCT instance
across imports. The repository STEP benchmark improved from a 1674 ms median
in 0.0.25 to 975 ms in 0.0.28, a 41.7% reduction.

This is an intentional compatibility change: use an ESM import or the packaged
worker. Classic-script globals, CommonJS `require()`, and `importScripts` are
not supported by the 0.0.28 runtime. See the
[0.0.28 release notes](docs/release-notes-v0.0.28.md) for the complete API,
worker, build, and migration details.

## How to install?

You can get `@sunbox/occt-import-js` from [npm](https://www.npmjs.com/package/@sunbox/occt-import-js):

```
npm install @sunbox/occt-import-js
```

## How to use?

The library runs in the browser and as a node.js module as well.

The `dist` folder contains the ESM factory, its WASM binary, and a reusable browser worker. Keep those files together when serving them. There are four public functions in the library:

- `ReadFile` to import a file by format name.
- `ReadBrepFile` to import brep file.
- `ReadStepFile` to import step file.
- `ReadIgesFile` to import iges file.

The format-specific functions have two parameters. `ReadFile` takes the format name first and then the same two parameters:

- `format`: The lowercase format name, for example `step`, `iges`, or `brep`; used only by `ReadFile`.
- `content`: The file content as a `Uint8Array` object.
- `params`: Triangulation parameters as an object, can be `null`.
  - `linearUnit`: Defines the linear unit of the output. Possible values: `millimeter`, `centimeter`, `meter`, `inch`, `foot`. Default is `millimeter`. Has no effect on brep files.
  - `linearDeflectionType`: Defines what the linear deflection value means. Default is `bounding_box_ratio`. Possible values:
    - `bounding_box_ratio`: The `linearDeflection` value contains a ratio of the average bounding box.
    - `absolute_value`: The `linearDeflection` value contains an absolute value in the unit defined by `linearUnit`.
  - `linearDeflection`: The linear deflection value based on the value of the `linearDeflectionType` parameter.
  - `angularDeflection`: The angular deflection value.

You can find more information about deflection values [here](https://dev.opencascade.org/doc/overview/html/occt_user_guides__mesh.html).

### Use from the browser

Import the generated ESM factory. It resolves `occt-import-js.wasm` relative to the module URL.

```html
<script type="module">
    import occtImportJs from './dist/occt-import-js.js'

    const response = await fetch('./cube.stp')
    const fileBuffer = new Uint8Array(await response.arrayBuffer())
    const occt = await occtImportJs()
    const result = occt.ReadStepFile(fileBuffer, null)
    console.log(result)
</script>
```

### Use in a browser worker

The packaged worker loads and caches the ESM factory, WASM bytes, and OCCT instance. It accepts `{ format, buffer, params }` messages and posts the import result. Initialization and fetch failures are returned as `{ success: false, error: { message } }` so callers can report the failure and retry a later request. Transfer the typed array's backing buffer to avoid copying large CAD files.

```js
const worker = new Worker(
    './node_modules/@sunbox/occt-import-js/dist/occt-import-js-worker.js'
)

worker.onmessage = ({ data }) => console.log(data)

const response = await fetch('./cube.stp')
const buffer = new Uint8Array(await response.arrayBuffer())
worker.postMessage({ format: 'step', buffer, params: null }, [buffer.buffer])
```

The worker, ESM module, and WASM file must be served from the same directory. Query parameters on the worker URL are also applied to the sibling assets, which allows one cache-busting version across all three files.

### Use as a Node.js ES module

The package entrypoint is ESM. In Node.js, provide the WASM bytes explicitly because the generated runtime targets browsers.

```js
import fs from 'node:fs'
import occtImportJs from '@sunbox/occt-import-js'

const moduleUrl = import.meta.resolve('@sunbox/occt-import-js')
const wasmBinary = fs.readFileSync(
    new URL('./occt-import-js.wasm', moduleUrl)
)
const occt = await occtImportJs({ wasmBinary })
const fileContent = fs.readFileSync('./cube.stp')
const result = occt.ReadStepFile(fileContent, null)
console.log(result)
```

### Processing the result

The result of the import is a JSON object with the following structure.

- **success** (boolean): Tells if the import was successful.
- **root** (object): The root node of the hierarchy.
  - **name** (string): Name of the node.
  - **meshes** (array): Indices of the meshes in the meshes array for this node.
  - **children** (array): Array of child nodes for this node.
- **meshes** (array): Array of mesh objects. The geometry representation is compatible with [three.js](https://github.com/mrdoob/three.js).
  - **name** (string): Name of the mesh.
  - **color** (array, optional): Array of r, g, and b values of the mesh color.
  - **brep_faces** (array): Array representing the faces of the source b-rep.
    - **first** (number): The first triangle index of the face.
    - **last** (number): The last triangle index of the face.
    - **color** (array): Array of r, g, and b values of the color or null.
  - **attributes** (object)
    - **position** (object)
      - **array** (array): Array of number triplets defining the vertex positions.
    - **normal** (object, optional)
      - **array** (array): Array of number triplets defining the normal vectors.
  - **index** (object):
    - **array** (array): Array of number triplets defining triangles by indices.

## How to build on Windows?

A set of batch scripts are prepared for building on Windows.

### 1. Install Prerequisites

Install [CMake](https://cmake.org) (3.6 minimum version is needed). Make sure that the cmake executable is in the PATH.

### 2. Install Emscripten SDK

Run the Emscripten setup script.

```
tools\setup_emscripten_win.bat
```

### 3. Compile the WASM library

Run the release build script.

```
tools\build_wasm_win_release.bat
```

### 4. Build the native project (optional)

If you want to debug the code, it's useful to build a native project. To do that, just use cmake to generate the project of your choice.

## How to run locally?

To run the demo and the examples locally, you have to start a web server. Run `npm install` from the root directory, run `npm start` and visit `http://localhost:8080`.
