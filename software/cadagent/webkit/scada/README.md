# SCADA toolkit

Animated process diagrams, reusable equipment, headless models and a complete
simulation example, maintained together in cad-agent.

The arrows show runtime dependencies. The Explorer owns a session and supplies
its state to the UI; the model never imports a browser renderer.

```mermaid
flowchart TD
  E["explorer/<br/>example host"] --> U["ui/<br/>symbols and viewer"]
  E --> M["sim/<br/>headless models"]
  M --> A["snapshot adapter"]
  A --> U
  classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
  classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
  class U,M,A here
  class E near
```

| Owner | Contents and next step |
| --- | --- |
| [ui/](ui/README.md) | Equipment registry, SVG states, diagram/viewer controls, system schema, API/style guides and the library's [image gallery](ui/img/README.md) |
| [sim/](sim/README.md) | Independent v1/v2 engines, replaceable equations, model/snapshot schemas, scenarios and the model library's [image gallery](sim/img/README.md) |
| [explorer/](explorer/README.md) | Runnable host: scenario selection, one clock/session, editable assumptions, faults, sound and shared views |
| [AGENTS.md](AGENTS.md) | Domain boundaries and maintenance rules |
| [LICENSE.txt](LICENSE.txt) | MIT license for project-owned SCADA code, artwork and documentation |
| [SOURCE.json](SOURCE.json) | Source identity, licensing authorization and local ownership |

<a href="ui/img/README.md"><img src="ui/img/symbols/automation/plc-rack/default.svg" width="220" alt="Animated PLC rack from the SCADA equipment library"></a>
<a href="sim/img/README.md"><img src="sim/img/thumbnails/food-beverage/winery/preview.jpg" width="320" alt="An illustrative winery process rendered by the shared viewer"></a>

## Use and maintain

Serve the copied web kit over HTTP(S) and open `scada/explorer/index.html`.
The public Toolkit presents equipment and simulations under `/toolkit/scada/`.
The code, symbols, scenario data and maintenance sources are physically present
here; the historical development repository is not needed to run or maintain them.

Project-owned SCADA source, symbols, scenarios and documentation use the [MIT license](LICENSE.txt), like the rest of cad-agent. Third-party dependencies and external publications retain their own terms.

The two libraries retain their public package names and source exports. Their
`img/` folders stay with the libraries. Generators live under the repository's
[SCADA tools](https://github.com/Valpatel/cad-agent/tree/dev/tools/webkit/scada), and executable
regressions live under [SCADA tests](https://github.com/Valpatel/cad-agent/tree/dev/tests/webkit/scada).
This separates reusable assets from maintenance commands without duplicating them.

Models are explicitly illustrative unless an independently qualified provider is
installed. Equipment artwork does not establish physical accuracy. Keep assumptions
editable and preserve the documented SI/index conversions when changing equations.

[Web kit](../README.md) · [User and integration guides](https://github.com/Valpatel/cad-agent/tree/dev/docs/practice/scada)
