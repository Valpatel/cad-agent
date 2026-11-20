**Changed**
- The web kit's shared 3D stage (file, assembly, FEA, host and replay viewers) draws only when the picture would change, not on every animation frame. An idle viewer now costs almost no CPU, and on a machine without a GPU the page stops dropping to a few frames a second; the pictures are the same (#822).
- `createStage` returns `invalidate()` for a change the stage cannot see from three.js objects (for example a canvas texture redrawn without `needsUpdate`), plus `draws` and `frames` counters; off-screen stages draw nothing until they come back into view (#822).
