# Validate page placement before accepting an embedded picture

## Observed on 2026-11-07 UTC

PR #416 at `b426845ba97a2ae2f17838c5062823a3e76fadba` added a small sharing badge to the README's contribution section.
The local component proof exercised Markdown rendering, sanitization, URL rewriting and both engines' actual
image motion. It omitted the site's later page-placement stage.

The complete compiled-site browser jobs caught the omission:

```text
Actions run 42347367151, Chromium job 128327907270, WebKit job 128327907539
locator('img[src="/docs/img/hero/made-with-cad-agent.svg"]') resolved to 2 elements
1) img alt="" width="248" height="56" loading="lazy" decoding="async" (section card)
2) img alt="Made with cad-agent — get the badge" (authored footer picture)
```

## Cause and corrective rule

`sectionCards` creates navigation cards when two headings have local pictures. The new badge joined the existing
CAD figure, crossing that threshold. The compiler cloned its fallback image into a large card near the title,
without the picture's explicit reduced-motion source. This was both unwanted layout and a separate image consumer.

Keep the README a deliberately small landing page. The existing page-placement configuration now accepts a
boolean `cards` setting; `README.md` alone sets it to `false`. It preserves the authored images, picture sources,
sections and links. Other pages retain their automatic cards, and configured hero/figures still work. Invalid
nonboolean settings fail. The existing actual-image browser check keeps its exactly-one-image requirement;
selecting the first match would hide the product defect.

The page-placement unit controls exercise compact, default and explicitly enabled cards, isolation to one page,
configured figures and invalid settings. The bounded component proof must include the actual placement stage;
the full compiled-site CI remains the acceptance boundary.

## Limits

This resolves the compact README's duplicate badge, not a universal rule for all image cards. Other pages may
deliberately repeat pictures. The failed jobs remain evidence; the earlier component proof did not establish
complete compiled-page behavior. Current acceptance belongs to the exact corrected revision and its CI.
