**Fixed**
- Site: a link to `/docs/agent-workflow#install-unix` or `#install-windows` opens that install block on arrival and when the address's `#` part changes, so the command shows; the home card says to finish the pasted sentence with what you want built (#804).
- Site: "For agents" stays in the phone header, which takes a second row below 560 px (#804).
- Site: the home page's layer-cake blocks open the section their label names (for example `/docs/toolkit#commands`); the build fails on a section the page does not have (#804).
- Site: the reference line in `llms.txt` no longer glues a `;` to an address, which plain link finders read as a dead link; the 404 page's feedback link names the missing address (#804).

**New**
- Site: every page has link-card tags (`og:title`, `og:description`, `og:url`, `og:image`, `twitter:card`) from its own title, description and address, one owned card picture drawn by `tools/site/figures/social-card.mjs` with a hash record, and an `apple-touch-icon`. The build fails on a page without its own card tags, and on any address in `llms.txt` or `llms-full.txt` the built site does not serve (#804).
