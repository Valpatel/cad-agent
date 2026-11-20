# Original CAD file viewing

Read and inspect original CAD files with bounded parsing workers, independently scoped presentation and a standalone page. File meshes use document-local selection IDs.

```mermaid
flowchart LR
  File --> Loader
  Loader --> Worker
  Worker --> Viewer
```

| File | Responsibility |
| --- | --- |
| [file-viewer.js](file-viewer.js) | Original-file viewer lifecycle, loading, camera and status. |
| [file-viewer.html](file-viewer.html) | Standalone file-viewer entry page. |
| [file-viewer.css](file-viewer.css) | Standalone stylesheet composing page and scoped viewer styles. |
| [page.css](page.css) | Full-page layout and default palette. |
| [viewer.css](viewer.css) | Scoped viewer surface, loading, error and local controls. |
| [file-viewer-theme.js](file-viewer-theme.js) | Palette and theme validation. |
| [file-loader.js](file-loader.js) | File routing, limits, worker ownership and cancellation. |
| [file-geometry.js](file-geometry.js) | Geometry validation and normalized mesh records. |
| [file-mesh-worker.js](file-mesh-worker.js) | Bounded mesh-format parsing worker. |
| [file-step-worker.js](file-step-worker.js) | Bounded STEP parsing worker and decoder resources. |

The standalone page follows the shared [application theme](../ui/README.md), including saved choices and
system changes. An explicit `?theme=light`, `dark` or `auto` keeps its own mode and hides the page toggle.
Embedded `createFileViewer` instances retain their scoped theme options and do not read application preferences.

[Web kit](../README.md)
