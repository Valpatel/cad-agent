**New**
- The website has a dark theme (#305). It follows the reader's system setting, and a button in the header switches it;
  the choice is kept in that browser only (localStorage) and nothing is sent anywhere. Every page, the catalogue, the
  "copy this to your agent" card, the page tree and the kit's demos follow it. Mermaid diagrams are drawn at build time
  in both themes, so dark pages show dark diagrams without script and without downloading Mermaid.
- `kit/diagrams.js` exports `refreshDiagramThemes()`, which redraws diagrams after a page switches theme with its own
  button, and leaves alone figures drawn ahead of time for one theme (`data-theme-only`).

**Changed**
- `web/site.css` and `web/catalog.css` keep their colours as tokens on `:root`, a light set and a dark one; a
  catalogue domain's tone is now `--tone-ink`, with `--tone` and the tints mixed from it in the dark theme.

**Fixed**
- The site's copy buttons read in every state: "Copied" is a darker green under its white text (was 3.45:1), and the
  home page's orange buttons keep white text readable when the clipboard refuses (was 1.24:1).
- The headers of `install.sh` and `install.ps1` name every folder the installer writes, including the subagents in
  `~/.claude/agents`, and say that it removes the kit's own old links from `~/.codex/skills` (#308 review).
