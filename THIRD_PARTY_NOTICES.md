# Third-party notices

Code under `vendor/` is copied from the projects below at the pinned commit. Each directory keeps its
upstream LICENSE/NOTICE files; those terms apply to that code. Our changes are listed as patches in `vendor/patches/`.

| Project | Licence | Upstream | Pinned commit | Imported |
|---|---|---|---|---|
| text-to-cad | MIT | https://github.com/earthtojake/text-to-cad | `2f793659fb7b` | 2026-10-24 |
| kicad-happy | MIT | https://github.com/aklofas/kicad-happy | `2fd9aa0fe2d6` | 2026-10-24 |
| kicad-mcp-pro | MIT | https://github.com/oaslananka/kicad-mcp-pro | `f03b478f597d` | 2026-10-24 |
| build123d-mcp | Apache-2.0 | https://github.com/pzfreo/build123d-mcp | `59b256121886` | 2026-10-24 |
| agentcad | Apache-2.0 | https://github.com/jdilla1277/agentcad | `52af472ddade` | 2026-10-24 |
| bd_warehouse | Apache-2.0 | https://github.com/gumyr/bd_warehouse | `e6ae6e7bae74` | 2026-10-24 |

## Runtime dependencies and external programs (not vendored)

The simulation modules use these at run time. None of their code is copied into this repository.

| Project | Licence | How cad-agent uses it |
|---|---|---|
| OpenFOAM v2512 (OpenCFD) | GPL-3.0 | External program (`cadagent.cfd` writes a case and runs it natively or in the `opencfd/openfoam-default` Docker image) |
| Bambu Studio | AGPL-3.0 | External program (`cadagent.slicer` runs its command line; profiles are read, flattened and passed back as files) |
| gmsh | GPL-2.0-or-later | Imported by the optional `fea` extra. Our source stays MIT; distributing a bundle that includes gmsh falls under the GPL |
| scikit-fem | BSD-3-Clause | Imported (`fea`) |
| pyMOTO | MIT | Imported (`sim`, topology optimisation) |
| PyVista, VTK | MIT, BSD-3-Clause | Imported (`sim`, pictures and animations) |
| trimesh, manifold3d, Rtree | MIT, Apache-2.0, MIT | Imported (`sim`, mesh booleans and point-in-solid tests) |
| imageio, imageio-ffmpeg (FFmpeg) | BSD-2-Clause (FFmpeg LGPL/GPL binary, run as a process) | Imported (`sim`, MP4 writing) |

## Web kit (copied into project sites and published on cad-agent.valpatel.com)

`src/cadagent/webkit/vendor/` holds these files unchanged unless noted; each keeps its licence text beside it, and
`cad-agent site` copies the licence files with the code.

| Project | Licence | Version | Licence file in the kit |
|---|---|---|---|
| three.js (core and the controls, geometry, loader and utility add-ons) | MIT | r160 | header of `three/three.module.min.js`; `file-parsers/THREE-LICENSE.txt` |
| three.js STL and 3MF loaders | MIT | r160, import paths changed to the local copies | `file-parsers/THREE-LICENSE.txt` |
| fflate | MIT | as bundled with three.js r160 | `file-parsers/FFLATE-LICENSE.txt` |
| Mermaid | MIT | 11.4.1 | `mermaid/LICENSE` |
| linkedom | ISC | 0.18.12 | `linkedom/LICENSE` |
| occt-import-js (Open CASCADE Technology compiled to WebAssembly) | LGPL-2.1 with the OCCT exception | 0.0.23 | `occt-import-js/` (four licence files; sources in `occt-import-js/source`) |
| Inter | SIL Open Font License 1.1 | variable, Latin subset | `fonts/OFL-Inter.txt` |
| JetBrains Mono | SIL Open Font License 1.1 | variable, Latin subset | `fonts/OFL-JetBrainsMono.txt` |
