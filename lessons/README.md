# Lessons from the J501 enclosure session

Lessons for an AI hardware-design agent, mined from **one** Claude Code session: the J501 AGX enclosure design
session (session `d8e464a0-f4a5-4edd-9190-6fd66a0508b0`, 2026-10-24 to 2026-10-25). In that session the agent and the
user designed a 3D-printed enclosure for a Seeed reServer J501 carrier with a Jetson AGX Orin module, plus storage
trays, SATA cable routing and a review website. No other session histories were mined; the user asked for this one only.

## How they were mined

- **Input:** a scrubbed, chronological transcript produced by `mining/extract_session.py`. It keeps only the prose of
  user messages, mid-turn user messages and assistant replies. Tool calls and tool output are left out. Personal data
  (addresses, paths, hostnames) is replaced with placeholders such as `<ip>` and `<scratch>`.
- **Gaps in the transcript:**
  - Context was compacted at 2026-10-24T08:35. A summary covers the 07:00–07:41 work.
  - The session restarted between 2026-10-24T18:03 and 2026-10-25T00:31. Most of the storage-tray, chimney and
    standoff work happened in that window, so it appears only in later assistant summaries.
- **Cross-check:** facts were confirmed read-only against the project files `README.md`, `cad/parameters.json` and
  `exports/*.json`. When a lesson relies on a project file, its **Source** line names the file.
- **What counts as a lesson:** user corrections, requirements as the user stated them, assumptions that turned out
  wrong, checks that caught real bugs (or raised false alarms), and process choices the user endorsed or pushed back on.
- **Limits:**
  - Nothing in this session was printed, sliced or test-fitted. Lessons about fit describe design intent and CAD checks,
    not physical validation.
  - Where the brief for this mining run mentioned an incident that could not be found in the transcript or the project
    files, the lesson says so rather than inventing details.

File 08 also includes an explicitly attributed later CAN-project wheel-zoom follow-up (2026-10-27).

File 11 comes from a different project: the incident notes of a CAN breakout PCB and housing designed on
2026-10-26. Its Source lines name those notes, which stay in that project's repository.

## Index

| File | Topic |
|---|---|
| [01-verify-from-source.md](01-verify-from-source.md) | Confirm board facts from schematics, photos and models, not from assumptions |
| [02-user-intent-and-requirements.md](02-user-intent-and-requirements.md) | How the requirements evolved, and the user's corrections |
| [03-mechanical-design-rules.md](03-mechanical-design-rules.md) | Strength, printability, landings, reliefs, windows, grilles, shell |
| [04-fasteners-and-assembly-access.md](04-fasteners-and-assembly-access.md) | Tool access, assembly order, screw length, inserts, drive screws |
| [05-cables-connectors-and-routing.md](05-cables-connectors-and-routing.md) | Mated-plug port windows (standard practice), SATA routing, plug lengths, bend radius, wiring rules |
| [06-enclosure-features.md](06-enclosure-features.md) | Antennas, service pins, storage trays, mount plate, cap, power budget |
| [07-verification-and-evidence.md](07-verification-and-evidence.md) | Checks that caught bugs, false positives, honest claims, stale outputs |
| [08-review-site-ux.md](08-review-site-ux.md) | What the user wanted to see on the review site, and why |
| [09-agent-process.md](09-agent-process.md) | Mid-turn messages, status, consent, prior art, scope, delegation |
| [10-simulation-and-material.md](10-simulation-and-material.md) | Exact bought parts, slicer grams, re-checking thinner shells, thermal models of printed enclosures, shared compute |
| [11-pcb-evidence-and-review.md](11-pcb-evidence-and-review.md) | KiCad report severities and waivers, parity, source hashes, routing geometry, STEP handedness, readback renders, release allowlists (from a second project; see below) |
| [12-original-file-viewer.md](12-original-file-viewer.md) | Original-file identity, parser units/frames, cancellable loading, dependency and wheel evidence |

## Lesson format

```markdown
### <short rule, imperative>
- **Rule:** one or two sentences, usable on any project.
- **Incident:** what happened in this session (specific and factual; brief user quotes where they matter).
- **Check:** how an agent or tool verifies it (a concrete check, threshold or artefact).
- **Source:** transcript timestamp(s) such as 2026-10-24T16:35, and/or a project file.
```

Timestamps are UTC as they appear in the transcript, truncated to the minute. Part numbers (P1, P9, P15 and so on)
are the project's printed-part IDs.
