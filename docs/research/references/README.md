# docs/research/references

The reference registry's schema-2 shards (#323): outside projects, guides, standards and data sheets that cad-agent
lists, links and, once someone has read them, cites. It grows the one-file registry of #118 into a folder without
splitting its id space. `docs/research/references.yaml` stays the core of read and cited sources. The records here share
its ids, and `cadagent.review.references` reads both.

Load the source inventory

```mermaid
flowchart TD
    C["docs/research/<br/>references.yaml<br/>core: read, cited sources"]
    L["cadagent.review.references<br/>load(): one id space"]
    S["docs/research/references/<br/>*.yaml · schema-2 shards"]
    C --> L
    S --> L
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S,L here
    class C near
```

Check and cite the loaded sources

```mermaid
flowchart TD
    L["cadagent.review.references<br/>load(): one id space"]
    V["vocab.yaml<br/>fixed vocabularies"]
    K["check()<br/>python -m ... --check"]
    U["lookup(), citation()<br/>ref tags in pages"]
    V --> K
    L --> K
    L --> U
    K ~~~ U
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class V,L here
    class K,U near
```

## What's here

| File | What it holds |
|---|---|
| `vocab.yaml` | The fixed vocabularies every schema-2 field is checked against: kinds, licence and reuse classes, the evidence ladder, confidence levels, processes, project domains and the objective assessment questions. |
| `projects-<domain>.yaml` | Open projects from the Reference Map, one shard per project domain (`vocab.yaml` `domain`): drive 39, drone 30, esc 56, general 6, legged 67, motor 31, pantilt 21, turret 38, wheel 78. |
| `guides-<group>.yaml` | Manufacturing and design guides, one shard per process group of the guide's first process: cnc 41, general 23, inserts 17, mould 30, pcb 13, print 37, sheet 40. Of these, 21 records are `extends: true` additions to guides already read in `docs/research/references.yaml`. |
| `coverage.yaml` | The map's coverage table: what cad-agent enforced per topic (16 rows), where, its gaps, and the issue drafted for each gap, never posted (`posted: false`). `wanted` lists the sources each process group still lacks. |

Every shard is at most 150 records and 150 KB.

<details>
<summary>Import provenance and rules that preserve edits</summary>

The shards and `coverage.yaml` come from the Reference Map, through
[`tools/import_refmap.py`](../../../tools/import_refmap.py), which takes the map's `data.json` by path. The data file
stays out of the repo. The import is deterministic, and its rules are in the tool's docstring:

- every new record is `snippet-only`, and every licence is unread;
- numbers are the authors' claims unless measured;
- the map's per-project verdicts stay out, and only its project-neutral `role` comes in;
- a re-import never undoes an edit. Each record it writes ends with `imported`, a digest of its text; a record whose
  text no longer matches it (any edit: a promotion, a fixed summary, the link check's withdrawn claim or moved url, a
  comment) is kept byte for byte, and so is a record the map does not make (added by hand, or since dropped: it is
  reported, never deleted). Records nobody touched are rewritten from the map, so `--check` passes after a sweep and
  a later map change to them still lands.

Two guides that `docs/research/references.yaml` lists as `unverified` were left there.

</details>

## A record

A shard record has the core entry's fields (`id`, `title`, `authors`, `org`, `year`, `url` or `isbn`, `access`,
`terms`, `areas`, `used_for`, `verified`), plus these:

| Field | What it says |
|---|---|
| `kind` | project, guide, standard, datasheet, paper, article, vendor-table, forum-thread, video, patent |
| `licence` | Of the source: `spdx` (or null), `class` (open, share-alike, non-commercial, unclear, proprietary), `read` (true only when the licence text itself was read), `note` |
| `reuse` | `text: cite-only`; `geometry`: copy, adapt-with-attribution, study-only or none. Share-alike, non-commercial, unclear and proprietary sources are study-only: study, never copy files, cite in the decision |
| `areas` | Slugs of [`docs/areas.yaml`](../../areas.yaml): an area, a topic, or `area/topic` |
| `processes`, `process_groups`, `domains`, `category` | From `vocab.yaml` |
| `evidence` | `class` (the ladder below), `numbers`, `tested`, `authority`; and `lowered` (`from`, `date`, `why`) when the weekly link check lowered the class because the link stayed dead (drop it when the record is promoted again) |
| `claims` | The rules a source states: `text`, `status` (unconfirmed, corroborated, conflicting, encoded), `evidence`, `corroborated_by` (ids of other records) |
| `confidence` | Optional, and only as `confidence()` derives it (#143); check() rejects a typed value that differs |
| `assessment` | For a project, objective answers only: `built`, `supply`, `cost`, `make`, `docs`, `activity`, `role`, `cad`, `answers`, `caveat`, `assessed`. `role` (leader, reference, lessons, context) names no project. It was scored while surveying for one kind of build (a printed two-wheeled, legged balancing robot), so it is not a quality grade (`vocab.yaml` says more) |
| `projects` | Optional join: a `docs/areas.yaml` project key mapped to that project's mechanism slugs |
| `rules`, `checks` | The profile rules and cad-agent checks that encode the record |
| `archive` | A pointer for the offline mirror: `sha256`, `kind`, `fetched`, `redistribute`. Never a path or a host |
| `summary` | One or two plain sentences, in our words |
| `imported` | Written by `tools/import_refmap.py`: a digest of the record's text as it wrote it. Edit the record freely and leave this line; a record whose text no longer matches it is yours, and a re-import keeps it as written |
| `extends: true` | The record adds these fields to the core *read source* with the same id, instead of being a record of its own |

Link health is not kept here. The checker's artifacts and the site JSON hold it, and only evidence-class changes land
in git. Every Monday `python3 tools/resource_audit.py references` checks up to 400 records' links (the longest
unchecked first, one request a second per host) and keeps one issue, "Reference health: open findings", up to date.
`tools/references_health_apply.py` then opens one bot PR with the changes its rules allow:

- a link gone or unreachable on two checks in a row lowers the record one rung (`evidence.lowered` says why);
- a permanent move on the same site updates `url` and keeps the old link in `mirrors`;
- a changed page sends a claim it alone corroborates back to `unconfirmed`.

Core entries, cited records and anything the rules do not cover are listed in the PR for a person.

## The evidence ladder

```mermaid
flowchart TD
    A["snippet-only"] --> B["read"]
    B --> C["verified-at-source"]
    C --> D["encoded"]
    D --> E["measured"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class A out
    class B,C,D,E here
```

- **snippet-only:** a record below `read` is *catalogued*. It may be listed and linked. A code table, a profile rule,
  a check or a `[ref:<id>]` tag outside `docs/research/` may not cite it, and `check()` warns on such a tag in `docs/research/`.
- **read:** someone opened the source and wrote the dated `verified` note, as every core entry has.
- **verified-at-source:** an independent record corroborates a claim, named in `claims[].corroborated_by`.
- **encoded:** a profile rule or a check with tests encodes the claim (`rules` or `checks`). A secondary source
  needs a corroborating record first. A primary one (the maker's own, or an independent test) may stand alone, which
  is #143's "one primary source with reproduced examples".
- **measured:** a physical result on a real project backs the claim.

## A promotion sweep

<details>
<summary>Read, corroborate, promote and encode each source</summary>

One process group (or one area) per PR. The first, threaded inserts (#323 phase 7), is the pattern.

1. **List the records.** Take every non-project record whose `processes`, `process_groups` or `areas` name the group,
   core entries included, and save the list with each record's `url` and claims.
2. **Fetch at the source.** Use the real page or PDF, never the snippet. Make at most 1 request a second per host,
   honour `robots.txt`, and give up on a 403 or 429 after one later retry. Keep the downloads in a scratch folder
   outside the repo, and never commit or mirror them.
3. **Read each one.** For every claim, find its words on the page. If they are not there, rewrite the claim to what
   the page says, and record in `evidence` what the snippet had wrong.
4. **Look for a second source.** A claim is `corroborated` only by another read record from a different publisher,
   named in `corroborated_by`. A retelling of the same test does not count. Where sources disagree, mark the claim
   `conflicting` and name the other source in `evidence`, not in `corroborated_by`.
5. **Promote.** Write a dated `verified` note that says what was read. Then set `evidence.class`:
   - `read` once the page is read;
   - `verified-at-source` when a claim is corroborated;
   - `encoded` when a profile rule (`rules`) and a tested check (`checks`) carry it.

   Fix `year`, `authors`, `kind` and `summary` from the page: no snippet-era note stays. Edit the record where it
   is; the importer keeps it from now on (see above). A source the map lacks goes in the group's shard as a new
   record, read, with its `verified` note.
6. **Leave the rest as they are.** A record you could not read stays `snippet-only`. Name it and the reason (403,
   429, `robots.txt`, a bot check, a script-only page, a moved page) in the PR body, not in the shard. Raw link health
   stays out of git (#323 Q5).
7. **Encode what governs.** Put each number in `docs/research/process-profiles.yaml`, with `note` saying which source
   governs where they differ. The code reads the number with `verified_rule`. Add golden vectors taken from the
   source's own table and a planted-defect test that the check must catch. Never average two sources silently: keep the
   range and name the governing one.
8. **Cite in the page.** Add a `[ref:<id>]` beside each number in the topic's `docs/` page, and add that page to the
   record's `used_for`.
9. **Settle the derived fields.** Rewrite each touched record's `confidence` from `confidence()`. Run
   `python -m cadagent.review.references --check` (no problems, and the catalogued count only falls),
   `node tools/site/compiler/site-references.mjs --experts`, `python3 tools/import_refmap.py <data.json> --check` (it must pass:
   the import keeps every promoted record), and the topic's tests.
10. **Report** the counts promoted and left, each source you could not read, and its reason.
11. **Distil each confirmed rule into `docs/research/process-profiles.yaml`:** one line, cited by its `source` (what a
    page cites as `[ref:<id>]`), with `applied_by` naming the function or gate that applies it, so `cad-agent rules`
    can serve it. The tests check that each `applied_by` reads the rule by id.

</details>

## Rules check() enforces

- One id across the core file and every shard. An id in two files is a problem, unless the shard's record says
  `extends: true`.
- A shard holds at most 150 records and 150 KB. Past either, split it by topic slug.
- Every vocabulary value and every area slug resolves. The licence class decides geometry reuse. The ladder's rules
  hold, and a stored `confidence` equals the derived one.

`python -m cadagent.review.references --check` runs all of these, and `tests/review/test_references.py` plants one
mistake of each kind.

## On the site

<details>
<summary>Published routes and required index refresh</summary>

`tools/site/compiler/site-references.mjs` publishes the records with the site build:

- `/references` charts every area;
- `/references/<area>` has charts by evidence, confidence, kind, licence and process, a table you can filter, and the
  coverage rows; each has a `.md` twin;
- `catalog/references/index.json` and `<area>.json` hold the same records for agents;
- `[ref:<id>]` in any page links to the record's row and to the source;
- `docs/practice/experts.md` is generated from the read sources.

After changing a record, run `node tools/site/compiler/site-references.mjs --experts` and commit `docs/practice/experts.md`
(`tests/site/website-references.test.mjs` fails until it is current). A record whose `areas` match no slug is listed on
`/references/unplaced`. That count may only fall.

</details>

## Related

- [`docs/research/references.yaml`](../references.yaml): the core registry and its field notes.
- [`software/cadagent/review/references.py`](../../../software/cadagent/review/references.py): the loader and the checks.
- [`docs/areas.yaml`](../../areas.yaml): the topic tree records are placed in.
- #118 (cite every rule by name), #143 (confidence levels), #323 (this knowledge base).

[Research](../README.md)

## File and child ownership

| File or folder | Purpose |
|---|---|
| [guides-cnc.yaml](guides-cnc.yaml) | Guide source records for cnc. |
| [guides-general.yaml](guides-general.yaml) | Guide source records for general. |
| [guides-inserts.yaml](guides-inserts.yaml) | Guide source records for inserts. |
| [guides-mould.yaml](guides-mould.yaml) | Guide source records for mould. |
| [guides-pcb.yaml](guides-pcb.yaml) | Guide source records for pcb. |
| [guides-print.yaml](guides-print.yaml) | Guide source records for print. |
| [guides-sheet.yaml](guides-sheet.yaml) | Guide source records for sheet. |
| [projects-drive.yaml](projects-drive.yaml) | Project source records for drive. |
| [projects-drone.yaml](projects-drone.yaml) | Project source records for drone. |
| [projects-esc.yaml](projects-esc.yaml) | Project source records for esc. |
| [projects-general.yaml](projects-general.yaml) | Project source records for general. |
| [projects-legged.yaml](projects-legged.yaml) | Project source records for legged. |
| [projects-motor.yaml](projects-motor.yaml) | Project source records for motor. |
| [projects-pantilt.yaml](projects-pantilt.yaml) | Project source records for pantilt. |
| [projects-turret.yaml](projects-turret.yaml) | Project source records for turret. |
| [projects-wheel.yaml](projects-wheel.yaml) | Project source records for wheel. |
