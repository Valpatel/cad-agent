**Changed**
- The eight longest text walls on the site now lead with real outputs: the toolkit, gates, explore and dossier
  pages, and the process-profiles, design-workflows, compliant-mechanisms and simulation-tools research pages. Each
  section shows a review-packet render, a command's own page, a chart drawn from the table beside it or a Mermaid
  flow, with a caption that says what it shows and what it was computed on; long reference tables fold into
  `<details>`. The wall backlog drops from 33 pages to 25 (#122).

**New**
- `tools/site-packet-pictures.py` renders the gate bench's review packets, as built and with one seeded defect per
  gate, into `docs/img/packets/` with a `SOURCE.json` of each run's gate counts and findings;
  `tests/test_packet_pictures.py` holds every caption on a seeded picture to its seed (#122).
- `tools/site-explore-pictures.mjs` runs the explore worked example's `catalogue`, `compare --swaps` and `optimise`
  and crops their pages into `docs/img/explore/`, dated from the example's last commit so a rebuild matches (#122).
- `tools/research_figures.py` charts the moulded and printed allowable strains (ranges drawn as ranges) and the
  printed materials' softening temperatures against a module's thermal plate limit, read from the research pages'
  tables; `tools/process_profile_figures.py` draws a chart per process section from the profile rules (#122).
