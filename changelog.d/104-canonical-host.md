**Changed**
- The site is also served at cad-agent.gyropup.com, a second custom domain on the same Cloudflare Pages project. Every
  page now names its cad-agent.valpatel.com address as canonical (`<link rel="canonical">`), so search engines index one
  copy; links for agents (`llms.txt`, `catalog.json`, the Markdown twins) keep using cad-agent.valpatel.com. The 404
  page names none (#104).
