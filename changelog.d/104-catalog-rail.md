**Changed**
- Catalogue (`/catalog`): the area index on the left is easier to read. Each domain is an outlined panel with a header in its colours and a line between rows, and the bars and counts line up in columns. Hovering a row (on screens that hover) or focusing it sweeps the domain's colour in from the left; the chosen row is dark, with an orange edge and count (#104).
- Catalogue: each domain's first row reads "All" instead of "Everything in mechanical design"; screen readers and the filter chip still name the domain ("All in mechanical design") (#104).
- Catalogue: maturity bars have five steps with gaps, one per level in `docs/areas.yaml`, in the area index, the filters, the cards and the area panels. A key above the index shows each level's bar and word, says what a level means on hover or focus, and links to "What the levels mean" in the vision. Screen readers hear "maturity 3 of 5, tooling" (#104).
- Catalogue: no project is singled out. The Gyropup dots, the card badge, the area panel's Gyropup pill, the "Needed for Gyropup" filter and its boost in the featured order are gone; cad-agent is a general toolkit, and Gyropup stays as an example and a project that used an area. Entries from areas Gyropup marked move down the featured order of their tab (#104).

**Fixed**
- Catalogue: the chip for a maturity filter reads "Tooling", not "maturity toolingTooling" (#104).

**Projects must change**
- `catalog.json` and `catalog/<area>.json` no longer have a `gyropup` field on entries, and `priority` lists only `demo` (`docs/areas.yaml` too). `/catalog?gyropup=1` is ignored. An agent that filtered on it should read `projects` on the area instead: `catalog/index.json` and each area's file now list the projects that used it (#104).
