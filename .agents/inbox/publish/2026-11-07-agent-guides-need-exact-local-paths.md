# Read the actual installed guide when a web summary loses its requirements

On 2026-11-07, the single current Opus trial under #282 installed cad-agent and produced a part, but its unchanged grader failed five report requirements: headings, model, harness, source citation and installed commit. [Independent actual disposition](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6709824302) retained the overall FAILED 7/12 result. The existing [discovery boundary lesson](../agents/2026-11-06-agent-discovery-and-resource-boundaries.md) already distinguishes installed instructions, native discovery and clean-user evidence; none makes a fetched summary complete.

**Evidence:** read-only JSONL inspection of the retained transcript (SHA-256 `be2a144bbdb06c7d3116c451a836aefa7493e0062f7d781db2487224f718639f`) found:

- Line 3 (zero-based record 2) asked WebFetch for the full `llms.txt`, especially installation and usage.
- Line 5 returned a summary starting “I can't reproduce the full page verbatim”. It kept the permission-to-post requirement but omitted the report field contract. The following workflow fetch requested installation commands only.
- No recorded tool call read the installed `docs/agent-prompt.txt` or kit skill instructions. The installed v0.27.0 canonical guide contains every report field; the generated report instead uses project-summary headings.
- `rg` against reviewed source `ed00fdd8397a26370531c6b21320d34feaff8938` found the canonical guide still naming `~/cad-agent/skills/*/SKILL.md`; listing the installed checkout found `.agents/skills/` and no root `skills/` directory. This is a separate hierarchy-move defect.

**Cause and corrective rule:** the observed web-tool output lost requirements before the main model continued, and the documented skill path had drifted from its owner. Keep the short entry line, correct the source path, and direct readers to the full installed guide after installation. Validate the documented paths against the actual native kit inventory, including a missing-guide control and the old root-glob control. Heading-presence tests alone did not catch the relocated path.

**Limits:** this identifies an observable information loss, not a unique internal model cause. A web summary might omit the new local-guide instruction too. The source checks establish reachable instructions, not model compliance, successful native discovery or a clean machine. No prompt/grader relaxation or new model trial is part of this correction; the original 7/12 failure and the separate Windows automatic-copy boundary remain unproved. The previous emitted installer shortcut was already repaired before this change and is not credited here.
