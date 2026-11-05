**Fixed**
- The existing branch-flow merge gate rejects changes to dated CHANGELOG entries already published on `main`,
  including edits, deletions, reordered entries and inserted historical sections. It reads candidate files only as
  data at fixed commits and fails closed when history cannot be read. New changes remain in `changelog.d/`.
- GitHub now requires both browser checks and all three release gates on `main`, with an up-to-date branch, matching
  the documented release process; the other protection settings remain unchanged.
