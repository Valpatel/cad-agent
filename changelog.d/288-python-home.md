**Fixed**
- `cad: python` in `cad-agent.yaml` expands `~` and `$HOME` (also `${HOME}`). `~/cad-agent/.venv/bin/python` used to be joined to the project root, so every step failed with "could not start" (#288).
