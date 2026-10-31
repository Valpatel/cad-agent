---
name: cad-agent-feedback
description: Use when you are working on a project with cad-agent (its CLI, skills, site or catalogue) and find something cad-agent should learn - a bug, a missing check, a better technique or tool you found elsewhere, a wrong or uncredited source. Sends it back as a GitHub issue with evidence anyone can reproduce, or a small fork PR for text, without leaking your project's private data.
---

# Send a finding back to cad-agent

cad-agent improves by collecting what agents discover while doing real work. A good report is short, reproducible
from public material alone, and credits where the idea came from. Maintainers treat every report as evidence: they
reproduce it, rebuild any accepted change themselves and credit you. So a report never needs code that "must be
merged as is".

## Before you write

1. **Search first.** `gh issue list -R Valpatel/cad-agent --search "<words>" --state all`, and the catalogue
   (`curl -s https://cad-agent.valpatel.com/catalog.json`). Add to an existing issue rather than opening a new one.
2. **Strip private data.** No secrets or tokens, hostnames, IP addresses, home paths, customer or product names
   your user has not made public, private repo names, or proprietary files (vendor STEP models under NDA,
   paid standards, copyrighted guides). Describe them instead, or rebuild the case with public geometry.
3. **Make it reproducible.** The smallest script, `cad-agent.yaml` or public model that shows the problem, the
   command, what you expected and what happened, and the cad-agent version (`pip show cad-agent`, or the commit).

## Kinds of report

| You found | Title starts with | Include |
|---|---|---|
| A bug or a wrong result | `Bug:` | Reproduction, expected vs actual, version |
| A mistake a check should catch | `Finding:` | The geometry that shows it (a minimal script), why it matters, the check you would want |
| A better tool, library, technique or guide | `Suggestion:` | Public URL, licence, what it does better and how you know (a test you ran, its own benchmarks) |
| A wrong, stale or uncredited statement | `Docs:` | The page and line, the correct statement, the source |

```bash
gh issue create -R Valpatel/cad-agent --title "Finding: <one line>" --body-file report.md
```

`report.md`: **What** (one paragraph) · **Evidence** (reproduction, numbers, links to public sources) ·
**Suggested change** · **Source and credit** (who published the technique or data) · **Checked for private data: yes**.

## Proposing a change yourself

Small text changes (a lesson, a research note, a catalogue entry in `research/landscape.json` or
`upstreams/registry.yaml`, a doc correction) can come as a pull request from your fork into `dev`:

```bash
gh repo fork Valpatel/cad-agent --clone && cd cad-agent
git switch -c docs/<topic> origin/dev      # edit, commit
gh pr create -R Valpatel/cad-agent --base dev --body "Closes #<issue>. Evidence: ..."
```

Fork PRs that change code, skills, agents, workflows, tools, dependencies or vendored files are not merged as
written: CI marks them, and a maintainer rebuilds an accepted idea on its own branch with your credit. Open an issue
with the evidence instead; it gets there faster. See
[docs/contributing-agents.md](https://cad-agent.valpatel.com/docs/contributing-agents).

## Never

- Paste instructions for other agents into an issue or PR ("ignore previous...", "run this command"): maintainers'
  agents read reports as data and such text gets the report closed.
- Attach binaries, archives or install scripts. Link public sources instead.
- Report on behalf of a user without their go-ahead when the report describes their project.
