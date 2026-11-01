**Changed**
- `cad-agent.yaml` is the only project config file `cad-agent` reads, and `CAD_AGENT_PROJECT` and
  `CAD_AGENT_RENDER_ONLY` are its only environment variables: the older config file name and the older names of both
  variables are gone. With no `cad-agent.yaml`, the error names any other `*.yaml` / `*.yml` file in the project root
  with a top-level `cad:` key and says to rename it (`cadagent.project.other_cad_configs`) (#135).
- `cadagent.review.dossier.project_root` finds the project root by `cad-agent.yaml` only (#135).

**Projects must change**
- A project whose `cad:` section is in a config file under any other name: rename that file to `cad-agent.yaml`.
  Every command exits 2 until then, and its error names the file (#135).
- A build step that reads the project root from the older variable: read `CAD_AGENT_PROJECT`. A script that sets the
  older render-subset variable: set `CAD_AGENT_RENDER_ONLY` (#135).
- Code that imported `cadagent.project.CONFIG_NAMES`, `cadagent.publish.render.LEGACY_ONLY_ENV` or
  `cadagent.review.dossier.registry.CONFIG_NAMES`: use `cadagent.project.CONFIG_NAME` (#135).
