**Fixed**
- SCADA viewer: a live simulation tick no longer replaces the camera's zoom readout (a click target) or the scale note, and no longer strips and re-applies the diagram's camera style and `data-camera-*` attributes. A tick now writes only values that changed, so a press and release that straddle a tick stay on the same nodes, and keyboard focus and hover survive (#761).

**Changed**
- `ScadaViewer.render()` now emits the same scale-note text that the mounted camera shows (`… · drag or pinch to explore` below 80% zoom); the visible text after mount is unchanged (#761).
