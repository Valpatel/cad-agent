**Changed**
- The site is also served at cad-agent.gyropup.com, a second custom domain on the same Cloudflare Pages project. Every
  published page now names its cad-agent.valpatel.com address as canonical, so search engines index one copy: site
  pages with `<link rel="canonical">`, and the web kit's own pages (`/kit/viewer`, `/kit/fea`, `/kit/file-viewer`),
  which are copied byte for byte from the kit, with a `Link` header. The 404 page names none. `llms.txt`,
  `catalog.json` and the sitemap already give cad-agent.valpatel.com addresses (#104).
