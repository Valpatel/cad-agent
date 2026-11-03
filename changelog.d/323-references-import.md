**New**
- The reference registry now holds the Reference Map: 546 new records in 16 shards
  (`research/references/projects-<domain>.yaml`, `guides-<group>.yaml`), and 21 additions to guides already read in
  `research/references.yaml` (#323). Every new record is catalogued (`snippet-only`): listed and linked, never cited
  by a rule, check or page until someone reads it at source. Licences are as the map states them, unread;
  share-alike, non-commercial and unclear geometry is study-only. Numbers are the authors' claims unless measured.
- `research/references/coverage.yaml`: what cad-agent enforces per topic (16 rows), its gaps, and the issue drafted
  for each gap, never posted; plus the sources each process group still lacks (#323).
- `tools/import_refmap.py <data.json>`: the deterministic, idempotent import (`--check` exits 1 when it would change
  a file). The map's data stays out of the repo (#323).
