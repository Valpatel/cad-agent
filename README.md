<div align="center">

<img src="docs/img/hero/repository-map.svg" alt="A conceptual learning workshop: study sources, try methods, test assumptions, review evidence and learn reusable skills" width="640">

A conceptual learning loop. Virtual checks and real measurements keep their own evidence.

# cad-agent

**Your one stop shop for agentic CAD.**

Self-improving AI for designing physical objects, built with the best open source projects.

Give your AI assistant a design task. cad-agent helps it find a method, build the model, check the assumptions and keep the evidence for review.

[![CI](https://github.com/Valpatel/cad-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Valpatel/cad-agent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Valpatel/cad-agent?color=f97316)](https://github.com/Valpatel/cad-agent/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

## Build with your favorite AI agent

macOS and Linux:

```bash
curl -fsSL https://cad-agent.valpatel.com/install.sh | sh
```

Windows, in PowerShell:

```powershell
irm https://cad-agent.valpatel.com/install.ps1 | iex
```

It installs uv if missing, puts cad-agent in `~/cad-agent` with the `cad-agent` command in `~/.local/bin`, and adds
its design skills for Claude Code, Codex, Copilot CLI, Cursor, Gemini CLI and opencode. `cad-agent init my-box`
starts a project; `cad-agent update` updates.

Or paste this into your agent, followed by what you want made:

<!-- The first line of docs/agent-prompt.txt (tests/repo/test_agent_prompt.py); the site's home page shows it too. -->
```text
Install cad-agent from https://cad-agent.valpatel.com/llms.txt, then use it for:
```

cad-agent collects no telemetry. When your agent finds a gap or learns a lesson, it shows you a short report and sends
it as a pull request or an issue only if you say yes. By hand, extras and uninstall:
[Install](docs/practice/agent-workflow.md#install).

## Find your next step

| I want to… | Open this |
|---|---|
| Make and check something | [Guides](docs/README.md): CAD, assemblies, mechanisms, PCBs, manufacturing and simulation |
| Find a technique or source | [Research](docs/research/README.md): surveys, rule cards, decisions and sources |
| Give an agent a repeatable method | [Skills](.agents/skills/README.md): design, hardware, motion and review workflows |
| Inspect the implementation and evidence | [Code](software/cadagent/README.md), [tests](tests/README.md) and [lessons](docs/lessons/README.md) |

Browse the [visual catalogue](https://cad-agent.valpatel.com/catalog), or start an agent from [llms.txt](https://cad-agent.valpatel.com/llms.txt). The [topic tree](docs/areas.yaml) gives each capability one discoverable home.

## How it improves itself

A real design exposes a gap. We search existing work, reproduce its examples, encode what survives in engineering code, and keep the failed case as a regression test. Sources keep their credit; short guides and skills tell the next agent when to apply the method.

For example, [snap-fit calculations](docs/mechanical/compliant.md) reproduce the Covestro/Bayer guide’s worked examples. Their material allowables cite data sheets; no printed coupon has been measured yet. CAD and simulation check a model’s assumptions. Physical fit and strength need physical tests.

[Existing checks and their limits](docs/lessons/process/2026-11-05-recovery-audit.md#evidence-that-can-improve-the-toolkit-today) · [Vision and planned model evaluations](docs/vision.md)

## What works today

<details>
<summary>A real example: Gyropup’s CAD and results</summary>

<img src="docs/img/hero/gyropup-leg.svg" alt="Gyropup's five-bar leg drawn from its real CAD, assembled, then checked for fit, strength and motion by cad-agent" width="100%">

<sub>Drawn from the real CAD and results of <a href="https://github.com/Valpatel/gyropup">Gyropup</a> (MIT), a self-balancing wheel-legged robot designed with cad-agent: its leg's STEP file, the hip frame's FEA and the five-bar's link lengths. Made by <a href="tools/readme_anim.py"><code>tools/readme_anim.py</code></a>.</sub>

</details>

- Parametric parts, bought-hardware models, assemblies and project builds.
- Geometry, fastener, motion, snap-fit and manufacturing checks with recorded evidence.
- Structural and thermal predictions, design trade-offs, and slicer time and mass.
- 3D review sites, section review packets, STEP/STL/3MF exports and hashed packages.

The [toolkit reference](docs/toolkit.md) names every command, dependency and limit. Real projects include [Gyropup](https://github.com/Valpatel/gyropup), the [J501 enclosure](https://github.com/mvalancy/j501-agx-orin) and the [Thor CAN breakout](https://github.com/mvalancy/pcb-agx-thor-can-breakout). Product-specific designs stay in their own repos.

## Extras

The core needs Python 3.10+, NumPy and PyYAML. CAD and simulation extras need Python 3.11+. [Choose optional dependencies and manual installation](docs/practice/agent-workflow.md#extras); platform limits are stated in the [FEA guide](docs/toolkit.md).

## Contribute

Send a minimal reproducer, a source or a better technique. Changes get tests and an independent review before release. [Contributing](.github/CONTRIBUTING.md) explains the process; the [dated recovery audit](docs/lessons/process/2026-11-05-recovery-audit.md) records paused work and what remains.

MIT. [Licence](LICENSE) · [Credits and third-party notices](software/vendor/THIRD_PARTY_NOTICES.md) · [Security](.github/SECURITY.md)
