# README and diagram style guide

Every folder in this repo explains itself in a `README.md`, so a person or an agent landing anywhere can tell what the
folder is for, how its pieces connect, and where to go next. This page says how those READMEs look. The checker that
keeps them present and linked is tracked in #113.

The **root README is a mini hyperpage**, not a file inventory or a manual. Answer three questions: **What is it?**,
**Why this is cool**, and **How to join in**. Show the pixel workflow header beside a compact genuine CAD example
with its source revision and limits. Keep a few clear routes; installation detail, research, evidence and contributor
instructions belong one click away in the existing guides. Label a historical example honestly until a source-bound
current snapshot replaces it. A virtual check is not a physical measurement.

**Badge collections are welcome and exempt from the compact prose budget.** Keep useful workflow status, release,
language, licence and navigation badges visible, linked to real destinations and able to wrap on a phone. Do not
invent coverage, platform support or engineering qualification to fill the collection.

Folder READMEs explain their local contents. The boxes below are their sections, in order from the top; the two at the bottom sit
side by side.

```mermaid
flowchart TD
    N["# folder name<br/>one line: what it is for"] --> D["one Mermaid diagram<br/>arrows from the code"]
    D --> W["What's here<br/>a row per file"]
    W --> R["Related<br/>parent, neighbours, docs"]
    W --> C["Credits<br/>whose work it builds on"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class N,D,W here
    class R,C near
```

## Which folders

- Every folder we write has a `README.md`.
- **Vendored trees** (`software/vendor/<name>/`, `software/cadagent/webkit/vendor/<name>/`) keep their upstream layout. One README at
  the vendor root covers them, with credits and licences.
- **Skill folders** (`.agents/skills/<name>/`) have `SKILL.md` instead; their parent README lists them.
- `.github/` is documented in [CONTRIBUTING.md](../../.github/CONTRIBUTING.md).

## Shape of a README

1. `# <folder name>`, then one sentence: what the folder is for.
2. One Mermaid diagram (below).
3. **What's here**: a table, one row per file or subfolder, one plain line each.
4. **Related**: the parent README, neighbouring folders, the docs page that explains the topic.
5. Credits where the folder builds on someone's work: name the person or project and link it.

Short beats complete: details live in docstrings and the docs.

## Diagrams

The site's diagram check (#123) draws every page at a 1100 px window, the narrowest that shows the page tree, and
fails any diagram wider than the article column: 641 px, keeping 17 px spare for a classic scrollbar. These rules keep
a diagram inside that and readable on GitHub. The rule that matters most, at most three boxes per rank, looks like
this: four boxes come from one input, and an invisible link (`B ~~~ E`) moves the fourth a rank down.

```mermaid
flowchart TD
    A["one input"] --> B["first output"]
    A --> C["second output"]
    A --> D["third output"]
    A --> E["fourth output<br/>pushed a rank down"]
    B ~~~ E
    class A near
    class B,C,D here
    class E out
```

- **`flowchart TD`**, at most 12 nodes. Inputs at the top, outputs at the bottom; label an edge with a verb or the file
  it carries when that helps.
- **At most three boxes per rank.** Mermaid puts each node at least one rank below the nodes that point at it, so a
  fan-out of four lands four abreast. Push one down with an invisible link: `A ~~~ E` draws nothing and puts `E` at least one
  rank below `A`. Or group: one box can name several folders (`mechanical/ · thermal/`).
- **Labels:** the real file or folder name on the first line, plain words after it. Split lines at about 24
  characters with `<br/>`. Three boxes of 24 characters still overflow, so keep lines shorter in a full rank, and
  avoid long edges that skip ranks: each one takes a lane of its own.
- **Draw from the code.** An arrow is an import, a call, or a file one piece writes and the next reads. Check each
  import arrow with grep or an AST scan, not from memory, and say in a sentence above the diagram what the arrows mean.
- **No meaning carried by colour alone (#113).** The palette sorts boxes into this folder's pieces, neighbours and
  outputs, but each label must say it too: a piece names its file, a neighbour its package, an output the file or page
  it is (`exports/hole-checks.json`).
- **Every diagram renders** through the kit's `diagrams.js` (the site) and on GitHub.
- **Left to right only for a two-column pairing**, sized to fit, with a note saying why. The one exception is
  `docs/research/agent-workflow/design-workflows.md` (#124): each incident symptom on the left, the check that catches it on the right.

Use the shared palette, so diagrams look the same on GitHub and on cad-agent.valpatel.com. These are the values the
site adds:

```
classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c      %% this folder's pieces
classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c      %% neighbours and inputs
classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c       %% what comes out: files, pages, verdicts
```

**Skills and subagents leave the palette out.** Diagrams in `.agents/skills/` and `.agents/agents/` keep only their `class` lines
(`class A,B here`, `class M out`) and leave out the `classDef` lines, because agents load those files into their
context. The site build adds the `classDef`
lines that a diagram uses but does not define (#124); on GitHub those diagrams draw in Mermaid's default colours. Do
not paste the three `classDef` lines into a `SKILL.md` or a subagent file.

Example: four checks from one input, at most three per rank.

```mermaid
flowchart TD
    B["build script<br/>the project's input"] --> A["a.py<br/>one check"] & C["c.py<br/>another"] & D["d.py<br/>a third"]
    A ~~~ E["e.py<br/>a rank lower"]
    B --> E
    A & C & D & E --> O["exports/result.json<br/>the output"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class A,C,D,E here
    class B near
    class O out
```

## Writing

Plain, short sentences. Say what a thing does and what it assumes, not how good it is. Name sources and people.

## Folder ownership checks

Run `node tools/site/compiler/site-repo-map.mjs --check` in the existing Node22 site context; `--write` regenerates [the repository map](../map.md). The required Chromium job runs its actual structural fault controls and freshness check. Normal owned folders have a README/Mermaid/table, an up link and child-map links. Every direct file appears explicitly in a table, including package entry points. The root keeps its compact introduction.

Installer role prompts are mapped from the agent-kit owner; installed skills own their bundled resource links. GitHub policy uses CONTRIBUTING. Named fixture sets, generated figure topics and pinned upstream components retain their layouts under explicit parent owners in `tools/site/compiler/repo-map.json`; a new set/topic/component still needs a parent row. Dated incidents require actual symptom-index links, and numbered changelog fragments retain the existing release-parser contract. These are consumer-based ownership rules, not historical inventory counts or wildcard exemptions for new source folders.

The generated map distinguishes public owner pages from source-only code/tool/operational maps. Publication scope and existing routes remain unchanged; a canonical source map is not claimed to be a published guide. Local Markdown checks validate file/directory destinations; the existing site build checks public routes/anchors. Neither proves remote availability or the semantic quality of a diagram.

<details>
<summary>Immutable release records retain their original namespace</summary>

Released CHANGELOG sections remain byte-preserved by the existing integration gate. Only their valid dated history region may resolve a relative public Markdown identity through the current publication contract to a present, selected source. Unreleased and current authored guidance still require physical-relative source destinations; unknown or missing aliases fail. This preserves evidence without pretending every historical link is a current GitHub source path.

</details>
