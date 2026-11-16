**New**
- CI: when the SCADA gallery and scenario provenance check fails, the `scada (chromium)` job regenerates the stale outputs on its pinned shell and uploads them, with a hash manifest, as the `scada-recapture-<head SHA>` artifact; an author without that shell commits it unchanged instead of editing capture hashes (#762).
