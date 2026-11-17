**New**
- The toolkit's build-guide demo and the home page's "Assembly & build guides" card now step through a real assembly: Gyropup's turret, twelve steps over 55 parts in the order Gyropup's own recipe gives, each step's new parts highlighted and drawn back along the way they go in, earlier parts ghosted. It is an example sequence from a work-in-progress prototype, not a verified build procedure; a CAD step order does not prove the parts can physically be assembled in that order. Converter, receipt and `--check`: `docs/examples/build-guide/`. Gyropup's design-log codes (D42, v1) are dropped from its instruction text by stated rules, every edit recorded so the original text can be restored and checked (#811).
- Assembly guides may bind a packed `cad-agent-model/1` (from `pack_view`) instead of an STL manifest; the reader and release packaging accept it. The turret's 55 meshes take 306 KB this way instead of 4.4 MB of STL (#811).
- Assembly reader: a guide's optional plain-text `source.qualification` (what the guide is and is not) is shown under its version line (#811).

**Changed**
- Assembly reader: Previous and Next sit above the step's text; on phones the step list, the buttons and the text come before the version line, so a long step keeps its buttons on a 390 × 664 screen. At phone widths every control is at least 44 px, and each part's show and colour inputs carry the part's name (#811).
- The installed wheel now includes the assembly reader's examples (`webkit/assembly/examples/`): about 350 KB more (#811).
- The synthetic rail bench is no longer published under `/web/toolkit/assembly/`; it stays as the reader's test fixture in `tests/fixtures/assembly-plan/` (#811).
