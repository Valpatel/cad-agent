**Changed**

- The original-file viewer reads STEP files with Open CASCADE 8.0.0 in its browser worker. The wheel includes the updated reader, license texts and rebuild instructions (#848).

**Projects must change**

- Projects that load the vendored `occt-import-js.js` directly must import its default ES-module factory. The shared file viewer handles this import for applications that embed it.
