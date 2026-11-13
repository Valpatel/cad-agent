# Static visual state snapshots

[Parent capture map](../README.md) · [Image gallery](../../README.md) · [Package owner](../../../README.md) · [Animated state comparisons](../../states/README.md)

These JPEGs preserve selected visual states for Markdown viewers without SVG animation. They are illustrative renderer inputs, not separate process simulations. The [capture manifest](../../../metadata/thumbnails.json) records their source and image hashes; the animated state gallery provides a wider set of editable examples.

```mermaid
flowchart LR
  State["Explicit rendering state"] --> Browser["Canonical component in Chromium"]
  Browser --> JPEG["Static JPEG snapshot"]
  State --> SVG["Sibling animated state gallery"]
```

| Comparison | Preview |
| --- | --- |
| Pump running / stopped | <img src="./pump-running.jpg" alt="Running pump" width="240"> <img src="./pump-stopped.jpg" alt="Stopped pump" width="240"> |
| Tank empty / full | <img src="./tank-empty.jpg" alt="Empty tank" width="240"> <img src="./tank-full.jpg" alt="Full tank" width="240"> |
| PLC warning / fault | <img src="./plc-warning.jpg" alt="PLC warning" width="240"> <img src="./plc-fault.jpg" alt="PLC fault" width="240"> |

The owning UI capture command is `npm run thumbnails`; use `npm run thumbnails -- --check` for read-only freshness checks. Do not edit the image files. Extend the capture definitions when a new static comparison is useful, then keep this authored folder map aligned.
