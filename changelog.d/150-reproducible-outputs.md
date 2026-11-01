**New**
- `cadagent.geometry.export_step` writes a cadquery `Assembly` too, with the same bytes on every export: the file
  `Assembly.save` writes (colours, names, placements), with a fixed header date, link ids 1, 2, ... in file order,
  each node added without a name called `<parent>.<k>` instead of a random uuid, and the colour records in one order
  (OCCT writes them in heap-address order). Sub-shape names and colours (`Assembly.addSubshape`) are refused (#150).
- `cadagent.project.source_date_epoch`, `source_time` and `source_stamp`: the date a build output records instead of
  the wall clock, `SOURCE_DATE_EPOCH` ([reproducible-builds.org](https://reproducible-builds.org/specs/source-date-epoch/)),
  else the last commit that changed the project outside its outputs (#150).

**Changed**
- `cad-agent package`: the same files give the same zip on every rebuild and in every checkout. Entries are sorted by
  path and carry the source date, mode `rw-r--r--` and a Unix host, not each file's own time and mode (#150).
- Report time stamps are the source date, never the build time, shown with where it came from
  (`2026-10-30 12:00 UTC (last commit)`): `header_meta.generated` in the results JSON and the report page,
  `simreport`'s `Generated`, the site's footer, the explore comparison's `generated` and the review bundle's
  `created`. The site's document cards show each page's last commit date, not its file time. A project that commits
  these pages no longer gets a diff on every rebuild, and committing them does not move their date (#150).
- `cad-agent release` and `step_timestamp` share one `SOURCE_DATE_EPOCH` parser: a malformed value stops the command
  with exit 2 (`release` used to ignore it and take the commit's date) (#150).

**Projects must change**
- Hashes that change once, then stay the same for the same files at the same commit: the review package zip
  (`exports/<name>.zip`; its `-manifest.json` is unchanged), `exports/cad-agent-results.json`,
  `docs/cad-agent-report.html`, `site/index.html`, `simreport` pages, `comparison.json` / `leaderboard.json` and
  review `bundle.json`. Re-record any sha256 of these (an evidence record's `artifact_sha256` or `report_sha256`, a
  release note), and commit the regenerated pages once (#150).
- Code that reads `header_meta.generated`, `comparison.json`'s `generated` or a `Generated` meta entry as a date: it
  now ends in `(last commit)` or `(SOURCE_DATE_EPOCH)`, is UTC (the comparison's was local time), and reads
  `undated (...)` outside git; `bundle.json`'s `created` can be `null` (#150).
- Write assembly STEP files with `export_step(assy, path)` instead of `assy.save(path)` or `assy.export(path)`, and set
  `SOURCE_DATE_EPOCH` to a whole number of seconds or leave it unset (#150).
