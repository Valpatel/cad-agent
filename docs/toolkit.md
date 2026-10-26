# cad-agent toolkit: verification and review reports for 3D-printed CAD projects

`cad-agent` runs a CAD project's build and checks, verifies its print files,
and turns the results into a standalone HTML report and a review package. It is
generic. The geometry and the design-specific checks stay in the project;
the toolkit (Python package `cadagent`) provides the runner, the 3MF writer,
shared geometry screens, the renderer, link validation, the report, packaging
and a local server.

```bash
pip install -e ".[cad]"          # in the cad-agent checkout; or install it into the project's own venv
cd my-cad-project
cad-agent all                    # build -> export-3mf -> check + report -> package
cad-agent check                  # re-collect results; exit 1 if anything fails
cad-agent report --open          # exports/cad-agent-results.json + docs/cad-agent-report.html
cad-agent serve --port 8000      # needed for "Open in Bambu Studio" links
```

Without the console script, `python -m cadagent.cli <subcommand>` does the same.
The toolkit started as `vptest cad` in the vptest framework; projects set up for
it keep working (see [Coming from vptest](#coming-from-vptest)).

## The project contract

```
my-cad-project/
  cad-agent.yaml         # cad: section (below)
  cad/parameters.json    # the single parameter authority (dimensions, clearances, revision)
  cad/build.py           # builds every part; exposes print_parts() and the print rotations
  tools/*.py             # project-specific checks, renders, docs; one JSON per check
  exports/               # <part>.stl/.3mf/.step, geometry-checks.json, <check>.json, logs
  preview/               # renders (part-<name>.png per part) + gallery index.html
  docs/                  # engineering review pages, BOM, registers, cad-agent-report.html
```

1. **One parameter authority.** Every dimension, clearance and the `revision`
   live in `cad/parameters.json`; scripts read it, nothing restates a number.
2. **`cad/build.py`** exposes `print_parts() -> {name: cadquery.Shape}` and a
   print-rotation table. Its `__main__` writes, per part, STEP in assembly
   coordinates and STL in print orientation, and the parts file
   `exports/geometry-checks.json`:
   `{part: {cad_valid, solid_count, watertight, print_bounds_mm, ...}}`.
   `cadagent.geometry` does the generic part:
   ```python
   from cadagent.geometry import export_print_stl, solid_report, pairwise_intersections
   report = {n: export_print_stl(s, OUT / f"{n}.stl", rotation=PRINT_ROTATION.get(n))
             for n, s in print_parts().items()}          # raises on a non-watertight STL
   ```
3. **Each check is a script** in `tools/` that writes `exports/<name>.json` with
   a top-level boolean `"pass"`. A check that cannot compute its answer writes
   `"pass": false` with the reason; it never omits the file or the key.
4. **Renders** go to `preview/`; `preview/part-<name>.png` is picked up as the
   evidence image for that part. `cadagent.render.Renderer` renders cadquery
   shapes or STL files offscreen with a caption bar, subtitle, note bar and
   leader labels; set `CAD_AGENT_RENDER_ONLY=a.png,b.png` to re-render a subset.
5. **A gallery page** (`preview/index.html`) can embed the per-part download
   table from `cadagent.report.downloads_snippet(project, page_dir=...)`:
   thumbnail, STL / 3MF / STEP links and a slicer link.

### Honest evidence

- CAD checks never claim physical fit. Every check JSON that touches fit should
  carry `"physical_fit_verified": false` (and `"slicer_run": false` for print
  screens) until someone has printed and fitted the part. The report records
  both as false and says so in a banner. `cad-agent` has no way to set them true.
- A check is green only when its `pass_key` value is the boolean `true`. A
  missing file, missing key, `"yes"`, `1` or a list all count as failures.
- In the results and the report, a row status other than the known pass, fail
  and skip spellings counts as a failure, never as a pass.
- The overhang screen (`geometry.downward_area`) is a screen, not a slicer.
- `export-3mf` re-reads every 3MF it writes and deletes it unless triangle count,
  edge-manifold watertightness and volume (within 0.1 %) match the STL.

### Print files

| File | Orientation | Notes |
|------|-------------|-------|
| `exports/<part>.stl` | print orientation, lowest point on z=0 | degenerate faces removed; must be watertight |
| `exports/<part>.3mf` | print orientation, centred on `printer.bed_mm` | written by `cad-agent export-3mf`, read back and verified |
| `exports/<part>.step` | assembly coordinates | for CAD review and re-use |

"Open in Bambu Studio" uses `bambustudio://open?file=<url-encoded http URL of the 3MF>&name=<part>`.
The slicer fetches the file over http, so the link only works when the page is
served (`cad-agent serve`); from `file://` the link downloads the 3MF instead.

## The `cad:` section of `cad-agent.yaml`

`cad-agent` reads `<project>/cad-agent.yaml` when it exists, otherwise
`<project>/vptest.yaml`. Only the `cad:` section is read; other top-level
sections (such as vptest's `project:` and `projects:`) are ignored. The first
file found is the config: a `cad-agent.yaml` without a `cad:` section is an
error even if `vptest.yaml` has one.

| Key | Default | Meaning |
|-----|---------|---------|
| `name`, `title` | folder name | identity in reports and package names |
| `revision` / `revision_from` | none | literal, or `"path/file.json:dotted.key"` read at report time |
| `python` | `<root>/.venv/bin/python`, else cad-agent's python | interpreter for the steps |
| `exports_dir`, `preview_dir`, `docs_dir` | `exports`, `preview`, `docs` | |
| `steps` | `[]` | `{name, run, log?, timeout_s=1800, needs?}`; `run` is a script relative to the root, run with cwd = root and `CAD_AGENT_PROJECT` set to the root; `log` is a file in `exports_dir`; `needs` names earlier steps |
| `parts_file` | `exports/geometry-checks.json` | part -> `{cad_valid, solid_count, watertight, print_bounds_mm}` |
| `part_ids` | `{}` | part -> display id (`P1`) |
| `checks` | `[]` | `{id, title, file, pass_key="pass", evidence?, links?}`; `pass_key` may be a list (all must be `true`) |
| `printer` | none | `{name, bed_mm: [x, y, z]}`; parts must fit; 3MF files are centred on it |
| `package` | none | `{name, include: [globs]}`; zip + `<name>-manifest.json` (sha256) in `exports_dir` |
| `serve` | `127.0.0.1`, port 0 (any free) | `{host, port}` |
| `html_pages` | `[]` | HTML / Markdown pages whose local links must resolve |

Unknown keys are reported as a warning, not an error.

### Worked example: j501-agx (Jetson AGX Orin enclosure)

```yaml
cad:
  name: j501-agx
  title: reServer J501 / Jetson AGX Orin enclosure
  revision_from: cad/parameters.json:revision
  printer: {name: Bambu Lab P1S, bed_mm: [256, 256, 256]}
  steps:
    - {name: build,             run: cad/build.py,              log: build.log}
    - {name: export-3mf,        run: tools/export_3mf.py,       needs: [build]}
    - {name: clearances,        run: tools/check_clearances.py, log: carrier-clearances.log, needs: [build]}
    - {name: shells,            run: tools/check_shells.py,     log: shell-clearances.log, needs: [build]}
    - {name: assembly-paths,    run: tools/assembly_paths.py,   log: assembly-paths.log, needs: [build]}
    - {name: print-review,      run: tools/print_review.py,     needs: [build]}
    - {name: design-metrics,    run: tools/design_metrics.py,   log: design-metrics.log, needs: [build]}
    - {name: mounts,            run: tools/check_mounts.py,     needs: [build]}
    - {name: storage,           run: tools/check_storage.py,    needs: [build]}
    - {name: docs,              run: tools/write_docs.py}
    - {name: check-sheet,       run: tools/check_sheet.py}
    - {name: detailed-assembly, run: tools/detailed_assembly.py, log: detailed-assembly.log}
    - {name: render,            run: tools/render.py,           log: render.log}
    - {name: package,           run: tools/package_review.py}
    - {name: validate,          run: tools/validate_review.py}
  part_ids: {base: P1, base_mount: P1M, cover: P2, front_gmsl: P3, front_no_gmsl: P4, rear_io: P5,
             mount_fit_template: P9, side_hatch: P10, m3_insert_coupon: P11, rail_coupon: P12,
             rail_key: P13, countersink_coupon: P14}
  checks:
    - {id: carrier, title: Carrier and hardware clearances, file: exports/carrier-clearances.json, evidence: [preview/open.png]}
    - {id: shells,  title: Open-shell clearances,           file: exports/shell-clearances.json}
    - {id: paths,   title: Plate insertion paths,           file: exports/assembly-paths.json, evidence: [preview/exploded.png]}
    - {id: mounts,  title: Mounting tabs and driver access, file: exports/mount-checks.json, evidence: [preview/mount-clearance.png]}
    - {id: storage, title: Storage trays and underside slots, file: exports/storage-checks.json, evidence: [preview/storage-stack.png]}
    - id: review
      title: Review validation
      file: exports/review-validation.json
      # this file has no top-level "pass"; every listed key must be true
      pass_key: [all_parts_single_valid_watertight, plastic_intersections_zero, carrier_and_hardware_pass,
                 open_shell_pass, mount_checks_pass, assembly_paths_pass, nominal_P1S_bounds_pass]
  package:
    name: j501-agx-fit-check
    include: [README.md, requirements.txt, cad/parameters.json, "docs/*", "exports/*.stl", "exports/*.3mf",
              "exports/*.step", "exports/*.json", references/sources.json]
  html_pages: [preview/index.html, README.md, docs/engineering-review.html]
```

Migration notes for this example. `tools/export_3mf.py`, `tools/package_review.py`
and `tools/serve_preview.py` duplicate `cad-agent export-3mf`, `package` and
`serve`; once those commands are adopted, drop the matching steps. Otherwise
`cad-agent all` writes the 3MF files twice (harmless) and two packages.
`tools/validate_review.py` can stay as a project check or give way to
`cad-agent check`, which covers parts, print files, the configured checks and
local links.

A YAML flow mapping ends a value at the first comma, so a title with a comma
must be quoted: `{id: storage, title: "Storage trays, cable routes", file: ...}`.
Unquoted, the title is cut at the comma and the rest becomes a stray key.

## Commands

| Command | Does | Exit code |
|---------|------|-----------|
| `cad-agent build [--from STEP] [--only STEP ...]` | runs steps in order with the project python; per-step timing; stops at the first failure and prints the log tail | 1 on a failed step |
| `cad-agent export-3mf` | `<part>.stl` -> verified, bed-centred `<part>.3mf` for every part in the parts file | 1 on a read-back mismatch |
| `cad-agent check [--json]` | collects results (no build), prints a table or the results JSON | 1 if any row fails |
| `cad-agent report [--open]` | writes `exports/cad-agent-results.json` (schema 1.0, the vptest web shape, so `vptest web validate` and its renderer still accept it) and a standalone `docs/cad-agent-report.html` with inline styles (light and dark) that opens from `file://` | 1 if any row fails |
| `cad-agent package` | zip + sha256 manifest from `package.include` | |
| `cad-agent serve [--port N] [--host H]` | serves the project root; writes the URL to `preview/server-url.txt` | |
| `cad-agent all` | build, export-3mf, check + report, package | 1 if anything failed |

`--project PATH` (default: cwd), before or after the subcommand, selects the
project. Exit code 2 means the project or environment is unusable: a missing or
invalid `cad:` section, a missing build output, or a missing optional
dependency. cad-agent names the dependency and the `cad` extra and does not
skip the work silently.

## Python API

```python
from cadagent.project import load_project    # CadProject, Step, Check, CadConfigError
from cadagent.geometry import (solid_report, export_print_stl, pairwise_intersections,
                               min_gap, downward_area, within_bed)
from cadagent.mesh3mf import write_3mf, read_3mf, verify_3mf, export_parts_3mf, is_edge_manifold
from cadagent.render import Renderer
from cadagent.report import collect, write_report, downloads_snippet, bambu_studio_url
from cadagent.htmlreport import render_page, canonical_status, SCHEMA_VERSION
from cadagent.links import missing_links
from cadagent.package import build_package
from cadagent.serve import make_server
from cadagent.robot import (Body, combine, box_body, cylinder_body, solid_mass_properties, printed_part_body,
                            Link, Joint, Visual, Collision, Motor, write_urdf, write_mjcf, check_urdf)
```

### Robot export (`cadagent.robot`)

Turns CAD parts into a simulator model with real mass properties:

- `solid_mass_properties(shape, density)` reads mass, centre of mass and inertia from the solid (OCP `BRepGProp`).
- `printed_part_body(shape, density, wall_mm, infill)` estimates a printed part: solid perimeters and skins plus
  sparse infill, with the inertia scaled to that mass. It is an estimate, so weigh the printed part.
- `box_body`, `cylinder_body` and `point_body` model bought parts from their catalogue mass. `Body` objects add with
  the parallel-axis theorem, so a link is the sum of everything bolted to it.
- `write_urdf` and `write_mjcf` write the same link tree. The MJCF adds motors, joint armature and friction, an IMU
  site and a floor. Both refuse a closed loop: model a four-bar or five-bar leg as an equivalent serial chain.
- `check_urdf` checks the tree, inertias (positive definite, triangle inequality), mesh files and joint limits.
  text-to-cad's `cadgen urdf validate` is a second, independent validator.

## Tests

```bash
pip install -e ".[cad,dev]"
pytest
# or, with a CAD project's venv that already has cadquery, trimesh, vtk and PIL:
PYTHONPATH=src /path/to/project/.venv/bin/python -m pytest tests -q
```

The geometry and render tests skip unless cadquery and vtk are importable.

## Coming from vptest

| vptest cad | cad-agent |
|------------|-----------|
| `vptest cad <subcommand>` | `cad-agent <subcommand>` (same subcommands, options and exit codes) |
| `vptest.yaml` | `cad-agent.yaml`; `vptest.yaml` is still read when `cad-agent.yaml` is absent |
| `exports/vptest-cad-results.json` | `exports/cad-agent-results.json` (same schema) |
| `docs/vptest-cad-report.html` | `docs/cad-agent-report.html` |
| `VPTEST_CAD_PROJECT` (set for steps) | `CAD_AGENT_PROJECT`; the old name is still set |
| `VPTEST_CAD_RENDER_ONLY` | `CAD_AGENT_RENDER_ONLY`; the old name is read when the new one is unset |
| `from vptest.cad.x import ...` | `from cadagent.x import ...` |

Pages that link to the old report or results file names need their links
updated, or `html_pages` will report them as broken.
