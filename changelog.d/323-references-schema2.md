**New**
- `cadagent.review.references` reads the reference registry's schema-2 shards, `research/references/*.yaml`, beside
  `research/references.yaml`, as one id space. A schema-2 record says what it is, what its source's licence allows
  (geometry under share-alike, non-commercial or unclear licences is study-only), how far it has been checked (the
  evidence ladder from `snippet-only` to `measured`) and, for an open project, an objective assessment. Its
  vocabularies are data in `research/references/vocab.yaml` (#323).
- `check()` (and `python -m cadagent.review.references --check`) validates shards: vocabularies, `docs/areas.yaml`
  slugs, at most 150 records or 150 KB per shard, the ladder's rules, and that a stored `confidence` equals the one
  `confidence()` derives from the evidence (#143, #323).
- A rule, a check, a code table or a page may not cite a catalogued (`snippet-only`) record; a `[ref:<id>]` to one in
  `research/` is a warning (#323).

**Changed**
- `--check` reads YAML through libyaml when PyYAML has it: 1.2 s instead of 1.9 s on today's registry (#323).
