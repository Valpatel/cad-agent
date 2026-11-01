**New**
- Site doc pages open with a picture band: a hero figure and, where a page has them, input → tool → output tiles, then cards for the sections that have pictures. `docs/pages.yaml` places them and figures inside sections, on the site only; the Markdown twins and `llms.txt` are unchanged (#179).
- Every placed picture says what it is, above its caption: "Real output of `<tool>`" or "Diagram of `<tool>`, drawn by `<script>`", and what it was computed on (Gyropup, a test fixture, a worked example, published sources). A figure opens its full-size image; a tile links to the section that explains it (#179).
- The build refuses a `docs/pages.yaml` entry with an unknown or misspelled key, an entry that places nothing, a picture that is not committed under `docs/img/`, a tool that is not a `cad-agent` command, a `cadagent` module, a web kit file or a script under `tools/`, a diagram without the `tools/` script that drew it, and a tile link or `below:` target that is not there (#179).
- `tools/site-bench-pictures.mjs` captures the review site that `cad-agent site` builds for the gate bench, cropped to whole lines. `tools/site-kit-pictures.mjs` captures the web kit at work: the part table and tracker on the gate bench's parts, and the file viewer on a Gyropup STEP file in its default, front, themed and broken-file states (#179).

**Changed**
- On the site, a table of more than 12 rows or a code block of more than 24 lines folds into a `<details>` that says what is inside. Chrome's find-in-page opens a fold that has a match, and the Markdown twin keeps it all open (#179).
- The pictures of the hinge sweep say they show the gate bench with a seeded fault (`flap_hits_frame`, its arm's range raised to 60 degrees). As built, the arm sweeps 0 to 40 degrees with 1.60 mm clearance (#179, #184 review).
- The "Hinge sweep" and "Module insertion" demos link to their sections in `docs/catalog.yaml` (#179).
- The site preloads its mono font, so the home page no longer shifts at 360 px when the font arrives (#179).
- The wall-of-text backlog is down from 39 pages to 33. The longest stretch without a picture is down from 20,202 px (`/docs/dossier`) to 12,296 px (`/research/design-workflows`), in Chrome at 1366 × 800 (#179).
