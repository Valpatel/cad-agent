**New**
- `research/references.yaml`, the reference registry: 161 read sources, each with its authors or publisher, year, an
  https link or ISBN, access, terms, the design areas it supports, the repo files that rely on it, and what was read
  and when. It merges the first sweep of #119 with the sources of `research/process-profiles.yaml`, and adds every
  source that `cadagent.formulas` (with the rolling-bearing sources of #180), `cadagent.mechanical.inserts`,
  `cadagent.mechanical.printed_joints` and `cadagent.simulation.fea` cite by key. Sources are cited, never copied:
  paid standards by number and title only, paid papers by author, title and equation, and no PDF of a source is kept
  in the repo (#118).
- `cadagent.review.references`: `lookup("covestro")` and `citation("roark")` resolve an id or a module's own key (an
  alias such as `shigley-torque`) to its entry. `check()` finds every place the code cites by id and reports a key
  that resolves to nothing, a malformed entry, or a citing file missing from the entry's `used_for`. From a shell:
  `python -m cadagent.review.references roark` or `--check` (#118).

**Changed**
- `research/process-profiles.yaml` no longer has its own `sources` and `standards` blocks: its rules cite registry
  ids, and `tools/process_profile_figures.py` reads the credits from the registry. The charts are unchanged (#118,
  #163).
- `cadagent.manufacturing.process` reads its sources from the registry, so the FDM data-sheet ids of its material
  factors (`bambu-petg-basic-tds` and the rest) now resolve to an entry instead of falling back to the sheet's link.
  A data file with no registry beside it still loads, with those ids unresolved (#118, #99).
- `cadagent.mechanical.bearings.SRC` (#180) is now `WHERE`: its keys are the checks (`life`, `load`, ...), not source
  ids, and a module-level `SRC` or `SOURCES` table is where the registry's check looks for ids (#118).
- `tests/test_fea_materials.py` now checks that every material's `source` is a read entry of the registry. It was
  skipped while the registry was missing (#118).
- A PR into cad-agent that adds a `[ref:<id>]` tag, a `source=` on an FEA material, a key to a module's `SRC` or
  `SOURCES` table, or a sheet to `FDM_MATERIALS` must add that source to `research/references.yaml`, or
  `tests/test_references.py` fails (#118).
- The registry records two out-of-date citations, for follow-up. ISO 68-1:1998, which `cadagent.formulas` cites for
  the metric thread profile, was withdrawn on 2023-10-05 and replaced by ISO 68-1:2023. Freudenstein's 1955 paper is
  pp. 853-859; the discussion after it runs to p. 861, which the formulas' citation includes (#118).
