**Fixed**
- Site: a link to `/docs/agent-workflow#install-unix` or `#install-windows` opens that install block on arrival and when the address's `#` part changes, so the command shows; the home card says to finish the pasted sentence with what you want built (#804).
- Site: "For agents" stays in the phone header, which takes a second row below 560 px (#804).
- Site: the home page's layer-cake blocks open the section their label names (for example `/docs/toolkit#commands`); the build fails on a section the page does not have (#804).
- Site: the toolkit's build-guide and original-file demos show the site's top bar (Explore, Toolkit, For agents; the name leads home), read from the host's `site/nav.json` the way a project's `cad-agent site` pages do, so the generic kit names no site of its own; `&nav=0` leaves it out. The assembly example's guide line says it is a synthetic fixture (`source commit 1111111111`) (#804).
- Site: on phones the whole hero recording fits the first screen at 390x664 (a tighter lede and action rows; the wording and order are unchanged) (#804).
- Site: "Open the playground" opens Gyropup's playground on the recorded turret (`?design=turret-box`), not its default robot (#804).
- Web kit: a viewer's top bar (`ui/appnav.js`) turns live reload on only when `site/nav.json` says the server offers it, which `cad-agent site --serve` now does; a static copy served from `localhost` no longer gets a 404 poll every two seconds (#804).
- Site: the reference line in `llms.txt` no longer glues a `;` to an address, which plain link finders read as a dead link; the 404 page's feedback link names the missing address (#804).

**New**
- Site: every page has link-card tags (`og:title`, `og:description`, `og:url`, `og:image`, `twitter:card`) from its own title, description and address, one owned card picture drawn by `tools/site/figures/social-card.mjs` with a hash record, and an `apple-touch-icon`. The build fails on a page without its own card tags, and on any address in `llms.txt` or `llms-full.txt` the built site does not serve (#804).
