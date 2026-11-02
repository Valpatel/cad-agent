**Changed**
- README: the animated hero is back at the top, above the title and the copy-to-your-agent prompt, as on
  text-to-cad's README, with two rows of badges (release, Python, site, last commit, stars, supported agents, CAD
  kernel, no telemetry). A test keeps the hero first.

**New**
- `tests/repo/test_markdown_images.py`: every local image in every Markdown page must be in git with the exact case,
  non-empty, not a Git LFS pointer, and match its extension's magic bytes.
