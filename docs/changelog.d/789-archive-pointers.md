**New**
- `tools/archive_pointers.py`: adds offline-mirror `archive` pointers (`sha256`, `kind`, `fetched`, `redistribute: false`) to reference records whose url is in a mirror's JSONL manifest kept outside the repo. Dry run by default, `--write` to apply; existing pointers are never overwritten and a sha256 mismatch is reported. Shards keep the importer's exact layout and the core file keeps its comments (#789).

**Changed**
- The build-plates figure generator moved to `tools/figures/plates_figure.py`, beside the other figure generators (#789).
