# Equipment variant snapshots

[Parent capture map](../README.md) · [Image gallery](../../README.md) · [Package owner](../../../README.md) · [Complete variant inventory](../../../docs/VARIANTS.md)

Each `<type>--<variant>.jpg` is a real browser capture of a declared equipment variant. The generated inventory lists every current variant with its thumbnail and normalized field inputs; the [animated family gallery](../../symbols/README.md) presents the same selections as portable SVGs.

```mermaid
flowchart LR
  Type["Equipment type"] --> Selection["Declared variant ID"]
  Selection --> Render["Canonical component renderer"]
  Render --> JPEG["type--variant.jpg"]
  JPEG --> Map["Generated variant inventory"]
```

| Sample | Preview |
| --- | --- |
| Thermal-fluid pump | <img src="./pump--thermal-fluid.jpg" alt="Thermal-fluid pump variant" width="300"> |
| Water relief valve | <img src="./relief-valve--water.jpg" alt="Water relief-valve variant" width="300"> |

Variant selection changes declared appearance and port semantics; simulation capacities and physical assumptions belong to the host model. See the [capture manifest](../../../metadata/thumbnails.json) for image provenance. Regenerate using `npm run thumbnails`, then check with `npm run thumbnails -- --check`. This folder map is authored; the inventory and images are generated.
