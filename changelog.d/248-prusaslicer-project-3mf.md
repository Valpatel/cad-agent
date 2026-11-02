**New**
- `cadagent.manufacturing.prusa3mf`: PrusaSlicer project 3MFs. `write_project` writes objects made of several
  volumes, each on its own tool (`Metadata/Slic3r_PE_model.config` volume ranges), and the wipe tower's place, which
  PrusaSlicer 2.9 reads from the project and not from the print config; `write_plates` packs every part at its
  quantity with the build-plates layout, grouped by tools or filament, one 3MF per plate, keeping parts clear of the
  tower. Each file is read back (triangles, watertightness, volume, tool and place of every volume) and is
  byte-reproducible; checked by slicing with PrusaSlicer 2.9.4 (#248).
