# Original-file viewer fixtures

`block.step` is a generated 10 × 20 × 30 mm rectangular solid, with its lower
corner at (0,0,0), made for this test suite (same license as cad-agent). It is
not a project or supplier model. Generate with CadQuery 2.8.0:

```python
import cadquery as cq
cq.exporters.export(cq.Workplane("XY").box(10, 20, 30, centered=False), "block.step")
```

Browser fixtures build matching STL and core 3MF documents directly. The 3MF
fixture also has an inch-unit case and translated/reflected components to test
units, handedness and original assembly placement independently of the renderer.
