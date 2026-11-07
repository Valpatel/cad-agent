# A page's reduced-motion match does not prove that its embedded SVG is still

## Observed on 2026-11-07 UTC

While reviewing the new conceptual README header for #411, the standalone SVG reported zero animations under
Playwright's reduced-motion emulation. The actual phone `<img>` screenshot nevertheless showed the animated
opening pose, with the third robot absent. Existing `tests/site/site-motion.mjs` already noted this consumer
boundary for the historical real-CAD figure, but tested that figure as a standalone document only.

A bounded Chromium 151.0.7922.71 probe loaded the same bytes through both a local file URL and a data URL in fresh
contexts, then compared the image's screenshots 1.6 seconds apart:

```text
newContext({ reducedMotion: 'reduce' })
file SVG: parent matchMedia=true; imageStatic=false
data SVG: parent matchMedia=true; imageStatic=false
newContext({ reducedMotion: 'no-preference' })
file SVG: parent matchMedia=false; imageStatic=false
data SVG: parent matchMedia=false; imageStatic=false

launch({ args: ['--force-prefers-reduced-motion'] })
newContext({ reducedMotion: 'reduce' })
file SVG: parent matchMedia=true; imageStatic=true
data SVG: parent matchMedia=true; imageStatic=true
```

The SVG bytes and their `@media (prefers-reduced-motion:reduce)` rule were unchanged between those probes. The
browser process preference reaches the image consumer; the page/context emulation did not in this observed
version. Chromium documents the flag in its [switches source](https://chromium.googlesource.com/chromium/src/+/refs/tags/126.0.6466.0/ui/gfx/switches.cc).
No desktop accessibility setting or existing browser profile was changed.

## Corrective rule

Validate the actual embedding mode. The existing website browser harness now compares the compiled README's
real image over time with motion enabled and disabled. It uses an isolated Chromium process for the browser
preference, and the ordinary WebKit reduced-motion setting. A deliberately broken image response restores an
animation with `!important`; that control must visibly change, so a cached or animation-disabled screenshot cannot
supply a false pass. The original standalone geometry/visibility checks remain useful and remain in place.

## Limits

The observation concerns Chromium 151 and this SVG, not all browsers or every system preference. Pixel equality
at two times is bounded evidence, not a proof of the entire timeline; source inspection and visual review of the
full still and representative phases remain necessary. The initial size/theme screenshots proved image loading
and bounds only. Do not relabel them as reduced-motion acceptance. Final compiled-consumer results belong to
PR #412's exact source revision and CI runs.
