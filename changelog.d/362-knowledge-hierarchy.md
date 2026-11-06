**Changed**
- Group mechanical and practice guides by domain, and move research, lessons and examples under `docs/`. Public documentation URLs and catalogue IDs remain stable; runtime source readers and installed-starter inputs follow their actual files. Retire the numbered lesson stubs after their announced v0.6.0 window while keeping permanent redirects.
- Validate a real wheel starter installation outside its removed build source in full CI, including a missing-installed-data control.

**Projects must change**
- Repository scripts or explicit overrides pointing to the toolkit's former `research/`, `lessons/` or `examples/` files must use their new `docs/` locations. Explicit independent profile copies keep their existing API behavior.
