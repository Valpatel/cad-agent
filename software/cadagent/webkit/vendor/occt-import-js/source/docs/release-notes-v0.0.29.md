# @sunbox/occt-import-js 0.0.29

The browser worker posts `{ success: false, error: { message } }` when loading
the importer or WASM fails. The failure stays attached to the request instead
of becoming an uncaught worker exception. Failed resources are evicted from the
worker cache so a later request can retry.

The ESM factory, WASM binary, and successful import result shape are unchanged.
