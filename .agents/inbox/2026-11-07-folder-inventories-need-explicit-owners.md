# Folder inventories need NUL-safe names and explicit consumer ownership

On 2026-11-07 UTC, the #113 read-only map study first split ordinary `git ls-tree` output on lines. Git quoted a vendored Unicode filename, producing invented quoted parent paths in that rejected inventory. The corrected inventory used `git ls-files -z`, decoded UTF-8 and split only on NUL. Historical 58/110 and 61/112 counts used declared exclusions; they are dated inventories, not completeness percentages or asserted missing-README defect counts.

The actual installer also treats every `.agents/agents/*.md` as a role prompt. An ordinary README there fails the existing frontmatter/discovery control. Generated figures, fixture trees and imported projects have different consumers from owned source packages; blindly adding READMEs or suppressing all unmatched folders would misrepresent ownership.

## Evidence and correction

- `node tools/site/compiler/site-repo-map.mjs --check` derives folders from a NUL-delimited Git inventory. Its current snapshot has 1,034 folders including fixture/upstream descendants; the number is not a quality score.
- `node --test tests/site/website-repo-map.test.mjs`: 18 structural tests pass locally. The actual Git fixture preserves a space/Unicode name and a filename containing a newline. Missing owner/diagram/table/up/down/member links, a new unmapped source child, a new unmapped fixture set and an unindexed incident are rejected.
- `python -m pytest -q tests/repo/test_layout.py tests/repo/test_areas.py tests/repo/test_cut_release.py tests/cli/test_agentkit.py`: 119 pass. Existing role discovery/frontmatter behavior and the root 14 budget remain enforced. The existing 42-file web-kit namespace warning remains; this map change moves no served module URLs and adds no executable module there.
- Initial structural run failed on its own newly added test missing from the site README and on a synthetic index self-link requirement. The owner row was added and the checker now excludes only the authoritative index itself from indexing itself. The original 16-pass/2-failure result is retained in the PR evidence; no defective run is counted as a pass.

## Corrective rule

Use the existing NUL-safe inventory convention and a real consumer-based owner for every directory. Ordinary owned folders require an authored map, explicit direct-file table, up link and child ownership links. A group delegates only to its actual named parent/index/validator: new fixture sets or figure topics still need parent rows, new prompt/resources need explicit owner links, dated incidents need real symptom-index entries, and temporary release fragments still pass the actual release parser. Do not preserve omissions by copying a baseline allowlist.

Keep publication scope separate: `docs/map.md` distinguishes public pages from canonical source-only code/tool/operational maps. It does not add broad new catalogue routes. The existing required Chromium job checks freshness and controls and renders source owner diagrams through the actual kit in both themes; local structural success is not that browser evidence.

## Limits

Relative file/directory destinations are checked; public route/anchor consumers remain the existing site build and browser checks. Source-only Markdown anchors and remote availability are not newly claimed. A diagram rendering successfully does not prove its semantic correctness or physical CAD performance. Upstream and data descendants retain their recorded layouts; parent ownership does not turn them into reviewed toolkit source.
