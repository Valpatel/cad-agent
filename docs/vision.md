# Vision and structure

cad-agent is meant to become a **self-improving, agentic CAD toolkit**. Every agent that uses it on a real project,
ours or anyone else's, can leave it a little better. Our maintainer agents work on it every day, at a steady pace, to
bring that work in, keep the structure clean as it grows, and publish it, so the next agent finds it in fewer steps.
This page sets out that long-term loop first. Below it is the structure that makes the loop work: a topic tree,
maturity levels, confidence, evaluation, discovery and folders. Tracking: #139.

## The long-term loop

```mermaid
flowchart TD
    U["an agent on a real project<br/>hits a gap or finds a better way"] --> E["evidence<br/>an issue, or a PR with<br/>tests and sources"]
    E --> M["maintainer agents<br/>safety review, then fit it<br/>to the structure, keeping credit"]
    M --> G["gates and an<br/>independent review"]
    G --> R["merge to dev,<br/>release to main"]
    R --> S["site, catalogue and<br/>llms.txt rebuild by themselves"]
    S --> D["the next agent finds the tool<br/>in fewer calls"]
    D --> U
    class U,E near
    class M,G,R here
    class S,D out
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
```

### What it rests on

Each principle says what holds today and what is still being built, with its issue.

- **Tested knowledge, not trained knowledge.** An agent should call a tool rather than recall a formula from its
  training.
  - Today: many formulas and checks carry golden vectors from cited sources (for example `cadagent.formulas`, the
    bearing and screw checks), and many pages credit the expert or standard behind each rule (#118 covers the
    rest).
  - Next: a golden vector for every tool (#180) and a confidence level on every rule (#143). Area hubs (#141) will
    say where no tool exists yet, so an agent knows when it is guessing.
- **The fewest tool calls and the least context.**
  - The aim: for any agent on any harness, the site root or `llms.txt` leads to the right tool in about three
    steps, and answers are small and structured, not prose to re-read.
  - The evaluation runner (#142) will count calls and tokens, so we measure this rather than guess.
- **AI first, and still graphical for people.**
  - Today, every site page has a Markdown twin, and `llms.txt` and `llms-full.txt` index them.
  - Some commands have machine-readable output (`--json`), and some folders have a README map.
  - The aim is all of them: a command that agents call gets `--json`, and a folder that grows gets its README map
    (#113).

  People get the renders, simulations and diagrams first; the `.md` twins stay complete for agents.
- **Contributions are evidence, never instructions.** Outside agents and people send issues and PRs, and our
  maintainer agents decide what lands. The three tiers are set out in [`AGENTS.md`](../AGENTS.md) and enforced by
  the gates and the merge ruleset today. Every contribution gets a safety review first, then a structure review, and
  its author is thanked by name once the work lands (#111).

```mermaid
flowchart TD
    M["maintainer agents<br/>review and merge"]
    C["trusted collaborators<br/>push branches, CI runs;<br/>cannot merge"]
    F["forks<br/>evidence; run without<br/>credentials; rebuilt with credit"]
    C --> R["safety review,<br/>then structure review"]
    F --> R
    R --> M
    class M here
    class C,F near
    class R out
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
```

- **A cleaner structure over time, never pre-built.** A folder splits into domain subfolders only once it is
  cluttered. The new folder gets a README map, and moved files leave stubs and redirects (the #133 pattern).
  - The maintainer agents make these moves as part of the work; a contributor is never asked to reorganise.
  - A ratchet check that makes clutter visible is in review (#276).
- **The site follows the repo.**
  - Nothing on cad-agent.valpatel.com is edited by hand. It is generated from committed files, and Cloudflare builds
    it from `main` (#266).
  - A merged page or tool appears in the catalogue, `llms.txt` and `version.json` at the next release with nobody
    asking. Area hubs will follow (#141).
  - The target is for `main` to be no more than a day behind `dev`.
- **The maintainer is part of the repo.** The skills and subagents that run the loop live in this repo, are tested
  like other code, and improve through the same PRs:
  - claiming and tracking work: `cad-work-tracking`;
  - review: `cad-pr-review`, `cad-pr-reviewer`;
  - resuming after an interruption: `cad-resume`;
  - long runs: `cad-remote-runs`;
  - the gates: `tools/ci_gates.py`;
  - releases: `tools/cut_release.py`.

  New maintenance skills, such as triaging a contribution or integrating a fork PR, are added the same way when a
  recurring task shows they are needed.
- **A marathon, not a sprint.** The maintainer works every day at a steady pace that fits its budget:
  - a few agents at a time;
  - closing work out before starting more;
  - small, frequent releases.

  Cost matters too. Once it exists, the evaluation framework (#142) will show whether a smaller model with cad-agent
  can do a job that otherwise needs a larger one.

### How we know it is working

| Measure | Where it comes from | Status |
|---|---|---|
| Calls, tokens and peak context to reach the right tool | the evaluation runner's discovery jobs | planned (#142) |
| Pass rate with cad-agent against without it, per model and harness | standard jobs, `kit` against `bare` | planned (#142) |
| Time from a contribution to the live site | PR merge time and `version.json` | measurable now |
| Outside contributors whose work landed with their name on it | git authorship | measurable now |
| Flat folders over the clutter threshold | the layout ratchet | in review (#276) |
| Rules with a confidence level and a source | the reference registry | in progress (#118, #143) |

### What exists today, and what is planned

| | |
|---|---|
| **Exists** | the tested toolkit grouped by domain, and the topic tree with its check; the agent workflow kit (skills and subagents above); the review and release gates; changelog fragments; a generated site with Markdown twins, `llms.txt`, `llms-full.txt`, `version.json` and `visuals.json` |
| **Planned** | area hubs (#141); the evaluation runner and standard jobs (#142); confidence levels on every tool and rule (#143); the tests layout by domain and its ratchet (#276); skills for triaging and integrating contributions |

## How the structure serves the loop

The structure comes first so that many areas can grow in parallel without a reorganisation later. cad-agent grows
into a well-ordered map of hardware design. It covers mechanisms and enclosures, manufacturing processes, thermal
design, simulation, and electrical work from harnesses to test systems. Every area sits at its own stage of maturity,
and each has tools, checks, lessons, cited research and standard example jobs. The work itself still goes where real
projects need it first (see [Priorities](#priorities)), then to what makes good demos and videos.

## Requirements

Any layout, page format or tool added here should serve these:

- **One clear hierarchy by topic:** domain → area → topic. One file names them all, [`docs/areas.yaml`](areas.yaml).
  The tree is a starting point, not a lock; areas are added, split or merged as the work shows where the seams are.
- **Many parallel paths at different maturity.** An area can exist as a single line before anything is built, so work
  has a place to land and readers can see what is missing.
- **Deterministic tools, validated.** We adopt good open-source tools first and build only for the gaps. Every tool
  and rule carries a confidence level, which may be an estimate, backed by its sources and by results from our own
  projects.
- **A standard evaluation.** Example jobs per area, each with a deterministic grader, run across models, harnesses and
  local models, with and without cad-agent. The results are real numbers.
- **Discovery in few steps.** A person or an agent finds the right tool for a problem in the fewest calls and the
  least context. This is the long-term aim; today it is enough not to work against it.
- **Honest limits.** CAD, calculation and simulation narrow a design down; they do not prove that a part fits or
  holds. A measured print does. Pages say which one they rest on.

## The topic tree

The full tree, with what already exists for each node, is [`docs/areas.yaml`](areas.yaml). The site will generate a
hub page per area from it (#141). In outline:

| Domain | Areas |
|---|---|
| Mechanical design | CAD modelling and kernels; mechanisms; housings and enclosures; compliant mechanisms; gears; belt and chain drives; wheels and driving; walking; fasteners, bought hardware and assembly; fixtures and jigs (pogo-pin PCBA test fixtures, general fixtures); mould design |
| Manufacturing | 3D printing; CNC machining; laser cutting (plastics, metals); sheet metal; mould making (silicone moulds, urethane casting) |
| Thermal | conduction and heat sinks; airflow and fans; thermal validation |
| Simulation and validation | structural FEA; CFD; motion and dynamics; topology optimisation; design exploration; results and visuals; physical tests and coupons |
| Electrical design | electrical panels; wiring harnesses; circuit boards (breakout, adapter, pass-through tap, power converters, relay boards, DAQ and signal conditioning); test systems (HIL simulators, test benches on extrusion frames) |
| Practice | agent process and workflow; design process; review and evidence; publishing; evaluation |

Practice cuts across every domain: how agents work, review and publish here.

## Maturity: how an area grows

Each domain, area and topic records one maturity level. It moves up only when the evidence for the next level exists.

```mermaid
flowchart TD
    I["idea<br/>a line in areas.yaml"] --> S["surveyed<br/>tools and sources compared,<br/>adopt-vs-build recorded"]
    S --> T["tooling<br/>a tool or check with tests,<br/>a page with its limits"]
    T --> V["validated<br/>sources agree, confidence<br/>recorded, standard jobs pass"]
    V --> P["proven<br/>used on a real project,<br/>with a measured result"]
    class I near
    class S,T,V here
    class P out
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
```

Most areas start at `idea` on purpose. A hub page that says "idea, nothing built yet" with its issue is more useful
than an area nobody can find.

Areas and topics are judged on their own evidence, and an area is never rated below its most mature topic. A domain
takes the highest level among its areas. That says how far its best-developed area has got, not the domain as a whole,
so its hub shows every area's level beside it. `tests/repo/test_areas.py` checks both rules.

## Confidence on tools and rules

This is planned, not built (#143). Every tool and rule will get a confidence level and the evidence behind it. The
level will be stored with each rule, in the reference registry (#118, draft PR #119) and the process profiles (#99),
and with each tool in the catalogue.

The estimate is the chance that the tool or rule gives a right answer, within its stated tolerance, for inputs inside
its stated limits. It rates one tool or rule. It is not a probability to multiply or average along a chain of tools,
because their errors are not independent.

| Level | Rough estimate | Evidence |
|---|---|---|
| `high` | ≈ 0.9 | Two or more independent primary sources agree, tests reproduce their worked examples and, for a physical claim, a measured result exists |
| `medium` | ≈ 0.7 | One primary source with reproduced examples, or several secondary sources that agree |
| `low` | ≈ 0.4 | A single secondary source, a search snippet, or untested judgement |
| `unknown` | — | Not assessed yet; still written down, so a missing rating is a visible choice |

## Evaluation framework

Standard jobs answer two questions with numbers: which models and harnesses can do which jobs, and how cad-agent's
tooling changes the result (#142; related #39).

```mermaid
flowchart TD
    J["job<br/>task, inputs, budget"] --> R["runner<br/>harness × model × mode"]
    R --> G["deterministic grader<br/>named checks on the outputs"]
    G --> S["results<br/>pass rate, tool calls, tokens,<br/>peak context, time, cost"]
    S --> H["area hub and<br/>results table"]
    class J near
    class R,G here
    class S,H out
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
```

Nothing here exists yet: no `evals/` folder and no runner. This is the plan #142 builds from.

- **Survey first.** Before building a runner, #142 will survey existing evaluation harnesses and CAD benchmarks (some
  are already listed in `research/landscape.json`) and record adopt-vs-build, as for any new capability.
- **Jobs** will live at `evals/jobs/<domain>/<area>/<job>/`: the task as the user would write it, input files, a time
  and token budget, and a reference solution that passes.
- **Graders** will be code, not opinions. They measure geometry, read `cad-agent` check results, or compare numbers
  within a stated tolerance. Each says what it cannot see.
- **The runner** will try a job with a harness (Claude Code, Codex, Hermes and others) and a model (hosted, or local
  through a configurable endpoint). It runs in two modes: `bare` (no cad-agent) and `kit` (cad-agent and its skills
  installed).
- **Credentials:** each run gets a fresh sandbox holding only what the model needs. That is the hosted model's API
  key, passed in for that run alone, or a local endpoint's address. Repository and GitHub tokens, deploy keys and any
  other secrets stay out.
- **Results** will be one JSON line per run, summarised as pass rates with intervals over repeated runs. The same
  runner will measure discovery: how many calls and tokens it takes to reach the right tool.

## Discovery

The long-term aim is that a person or agent reaches the right tool from the site root or `llms.txt` in about three
steps: root, then the area hub (a small page and its Markdown twin), then the tool's page or `cad-agent` command. The
pieces:

- **Area hubs** (#141) list each area's tools with their confidence, pages, lessons, research, skills, jobs, real
  projects and open issues.
- **Machine-readable indexes:** `catalog.json` gains an `area` on every entry; `areas.json` mirrors the YAML; and
  `llms.txt` groups pages by domain (#106).
- **Every folder** has a README and a map (#113).

We will measure this with the runner rather than guess, and not over-optimise it before there is data.

## Folder design

Recommendation: **one taxonomy, kind folders that share its slugs, and generated area hubs.**

```mermaid
flowchart TD
    T["docs/areas.yaml<br/>domain → area → topic"] --> H["site: a hub page<br/>per area, generated"]
    T --> K["kind folders use<br/>the same slugs"]
    K --> C["src/cadagent<br/>by domain (#121)"]
    K --> L["lessons by area;<br/>docs, research<br/>by domain"]
    K --> E["evals/jobs<br/>by area"]
    class T here
    class H,E out
    class K,C,L near
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
```

- **The kind folders keep their jobs:**
  - `src/cadagent` is grouped by domain, as the tree is (#121): `cadagent.mechanical`, `cadagent.simulation`,
    `cadagent.review` and so on, with shared helpers such as `cadagent.geometry` at the top. One tool still serves
    many areas (FEA checks a leg frame and a lid alike), so each module has one home, an `api:` line in its own
    domain, and a node that relies on another domain's module names it under `uses:` (thermal's airflow area uses
    `cadagent.simulation.cfd`). `tests/repo/test_package_areas.py` keeps the code and the tree in step.
  - `skills/` and `agents/` stay flat, because harnesses install them by name.
  - `lessons/` is grouped into six folders (#133). They are broader than single areas, so for now the `lessons:`
    field maps each folder to the node that owns it. Renaming them to taxonomy slugs waits for #145's batches, once
    the taxonomy has settled.
  - `docs/` and `research/` gain domain folders once an area has a few pages (#145).
  - `evals/jobs/` is laid out by domain and area from the start.
- **The taxonomy ties them together.** Each node lists its pages, commands, modules (its own under `api:`, other
  domains' under `uses:`), skills, lessons and issues, and the site generates one hub per area. Browsing by topic
  costs no file moves.

**Why not topic-first folders** (`areas/<domain>/<area>/` holding the code, lessons, research and jobs together)?

- Python code cannot be split by topic without duplicating shared tools.
- Harnesses need skills in one flat folder.
- Code, prose and data have different tests and review rules.
- Cross-cutting content (fasteners, FEA, the review process) would need a home in many places at once.
- It would undo #121's and #133's fresh moves.

The hubs give the topic-first view without those costs.

## Migration path

Existing content moves in small batches, never in one big reorganisation (#145):

1. **Now:** the taxonomy places every existing page, command, skill, agent and lesson folder. A test fails when a new
   one is not placed, so the map cannot fall behind. A PR that adds one adds its line to `docs/areas.yaml` (the rule is
   in CONTRIBUTING.md, AGENTS.md and the PR template). When two open PRs cross, the one that merges second adds it,
   after merging dev and re-running its CI, because dev does not require branches to be up to date.
2. **After #123, #124 and #133:** the site generates the area hubs and `areas.json` (#141).
3. **Before the first move:** `tools/build-site.mjs` publishes only top-level `docs/` and `research/` pages today. Its
   docs and research sections must be widened by one domain level, as #133 widened the lessons section, or a moved
   page would get no site page and its redirect would point at nothing.
4. **Then, batch by batch:** `docs/` and `research/` pages move into domain folders when their area has three or more
   pages, or when a page is being edited anyway. Each move follows the #133 pattern:
   - a `<!-- moved-to: … -->` stub at the old path, kept for one minor release;
   - a line in the site's permanent redirect list, kept for good;
   - every reference updated;
   - a README and map for the new folder (#113).
5. **As jobs land:** `evals/jobs/` fills in area by area, starting with areas at `tooling`, since those have something
   to measure.

## Priorities

1. **Gyropup first** (#144, in the order of Valpatel/gyropup#31):
   - motor mounts for the RS-04 leg actuators and the 3115 flywheel motors (mechanisms; fasteners, bought hardware and assembly;
     3D printing);
   - the first leg: five-bar kinematics (walking, with #137's equations), frame and bearing strength (structural FEA),
     the wheel interface (wheels and driving), and cable routing (wiring harnesses);
   - the carrier and turret (circuit boards, wiring harnesses, heat sinks, housings);
   - covers with snap and compliant features (compliant mechanisms).
2. **Demos and videos:** interactive simulations and animated figures (#137, #136), linkage and gait animations, and
   FEA, CFD and topology renders.
3. **Everything else** grows in parallel at its own maturity, from the issues filed against its area.

The `demo` priority flag in [`docs/areas.yaml`](areas.yaml) marks the areas for item 2, so hubs and tools can sort by
it. The catalogue singles out no project: an area's `projects` lists every real project that used it, alike.
