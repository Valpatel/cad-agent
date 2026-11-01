**New**
- `cadagent.geometry.cache.PartCache`: caches built parts as BREP under a hash of the listed source files, parameters
  (`key_extra`) and each part's own `deps`, so a build rebuilds only the parts whose sources changed.
  `get_or_build(name, fn, deps=None)`, `get_all(builders)`, `clear()` and an optional `max_bytes` cap. Each part's
  sha256, validity, solid count and volume are checked on load, and a damaged or changed file is rebuilt; writes are
  atomic, so parallel runs never read half a file (#250).
- `cad-agent package` skips folders tagged with `CACHEDIR.TAG`, such as the part cache, even when an include glob
  reaches into them (#250).

**Projects must change**
- Nothing is required. To use the part cache, keep it under `exports_dir` and add `exports/.partcache/` (or your
  chosen folder) to `.gitignore` (#250).
