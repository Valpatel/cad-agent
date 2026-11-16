**New**
- `cad-agent --version` prints the version and the package folder it runs from; every `cad-agent <command> --help` opens with the command's one-line description (#799).

**Fixed**
- The POSIX installer uninstalls when `CAD_AGENT_UNINSTALL=1` is set, as the install guide says; before, it updated instead. Both installers say that uv, its cache and Pythons stay, and the guide lists what uninstall leaves (#799).
- When `~/.local/bin` is not on PATH, the installers say how to use `cad-agent` in that terminal and name uv by its full path for `tool update-shell` (#799).
- The agent guide (and llms.txt) prints `cad-agent choose joining --load 20 --material petg`, a form that decides, instead of the bare command, which exits 2 by design; a test runs every `cad-agent` command the guide prints (#799).
- The Playwright hints name a command that works in the installer's uv tool environment (`uv tool install ... --with playwright`; it has no pip), and `cad-agent update` keeps packages added with `--with` when it reinstalls (#799).
- `cad-agent agents install` and `update` list only the skill links they changed, not every link on every run (#799).
- The local server's injected top bar imports `/_cadagent/kit/ui/appnav.js`, not a path that was a 404 (#799).
- The install guide states the first download (about 1.7 GB) and names the installer scripts by their repository paths; a report's "no render" says which file is missing and what writes it (#799).
