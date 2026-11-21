var importerPromise = null;
var occtPromise = null;
var wasmBinaryPromise = null;

/**
 * Resolves one sibling runtime asset while preserving the worker cache key.
 * @param {string} fileName
 * @returns {URL}
 */
function ResolveAssetUrl (fileName)
{
    var workerUrl = new URL (self.location.href);
    var assetUrl = new URL (fileName, workerUrl);
    assetUrl.search = workerUrl.search;
    return assetUrl;
}

/**
 * Loads the ESM importer module once.
 * @returns {Promise<any>}
 */
function LoadImporterModule ()
{
    if (importerPromise === null) {
        var importerUrl = ResolveAssetUrl ('occt-import-js.js');
        importerPromise = import (importerUrl.href).catch (function (error) {
            importerPromise = null;
            throw error;
        });
    }
    return importerPromise;
}

/**
 * Loads and caches the wasm bytes once.
 * @returns {Promise<ArrayBuffer>}
 */
function GetWasmBinary ()
{
    if (wasmBinaryPromise === null) {
        var wasmUrl = ResolveAssetUrl ('occt-import-js.wasm');
        wasmBinaryPromise = fetch (wasmUrl.href, {
            credentials : 'same-origin'
        }).then (function (response) {
            if (!response.ok) {
                throw new Error (
                    'Failed to load wasm: ' + response.status + ' ' + response.url
                );
            }
            return response.arrayBuffer ();
        }).catch (function (error) {
            wasmBinaryPromise = null;
            throw error;
        });
    }
    return wasmBinaryPromise;
}

/**
 * Creates and caches one OCCT importer instance.
 * @returns {Promise<any>}
 */
function LoadOcct ()
{
    if (occtPromise === null) {
        occtPromise = Promise.all ([
            LoadImporterModule (),
            GetWasmBinary ()
        ]).then (function (values) {
            var module = values[0];
            var wasmBinary = values[1];
            var occtFactory = module?.default || module?.occtimportjs;
            if (typeof occtFactory !== 'function') {
                throw new Error ('occt-import-js did not export a factory.');
            }
            return occtFactory ({
                locateFile : function (path) {
                    return ResolveAssetUrl (path).href;
                },
                wasmBinary : wasmBinary
            });
        }).catch (function (error) {
            occtPromise = null;
            throw error;
        });
    }
    return occtPromise;
}

/**
 * Imports one model and posts its result.
 * @param {MessageEvent} ev
 * @returns {Promise<void>}
 */
async function HandleMessage (ev)
{
    try {
        var occt = await LoadOcct ();
        var result = occt.ReadFile (
            ev.data.format,
            ev.data.buffer,
            ev.data.params
        );
        postMessage (result);
    } catch (error) {
        postMessage ({
            success : false,
            error : {
                message : String (error?.message || error || 'OCCT worker failed.')
            }
        });
    }
}

onmessage = HandleMessage;
