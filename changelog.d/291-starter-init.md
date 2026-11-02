**New**
- `cad-agent init [DIR]` starts a project from the starter box: it copies `examples/starter-box` (a 60 x 40 x 25 mm box and lid on four M3 heat-set inserts) into `DIR` and prints the next commands; `cad-agent all` passes on it as copied. It refuses a folder that is not empty unless `--force` is given. A wheel install carries the starter under `<prefix>/share/cad-agent/` (#291).
- `examples/starter-box`: the smallest cad-agent project, to change. Its holes and bosses come from `inserts.hole_design` and `inserts.boss_design` (the 4.20 mm M3 hole), and its `checks:` read `cad-agent inserts --output` and the overhang screen; CI runs `cad-agent all` on a fresh copy (#291).

**Changed**
- The paste-in guide (`docs/agent-prompt.txt`, llms.txt) and the README's quick start now start a project with `cad-agent init` instead of writing `cad-agent.yaml` by hand. A project command run where there is no `cad-agent.yaml` now points at `cad-agent init` (#291).
