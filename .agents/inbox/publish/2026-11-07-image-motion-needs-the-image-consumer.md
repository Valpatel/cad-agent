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

## The second engine caught the same boundary

At source `95af85bb`, the new compiled-image check passed in Chromium but failed in WebKit 26.0:

```text
Actions run 42343951245, job 128317514214, 2026-11-07T05:48:58Z
AssertionError: ['README image still animates with reduced motion']
```

The failed run is retained. A parent media-query match still did not establish the preference inside the embedded
image. Repeating that run or weakening the assertion would not fix the reader's experience.

## Corrective rule

Validate the actual embedding mode. The README now uses standard `picture`/`source` media selection to choose an
explicit still from the same producer, body and dimensions. All of that file's animations are disabled regardless
of the image document's media preference. The normal image retains its own reduced-motion rule as well. The site
compiler preserves the picture and rewrites its single source URL with the same image policy as the fallback.

The existing website browser harness compares the compiled README's actual image over time, verifies the chosen
`currentSrc`, and retains the painted frames. A deliberately broken still response restores animation with
`!important`; that control must visibly change, so a cached or animation-disabled screenshot cannot supply a false
pass. The original standalone geometry/visibility checks remain useful and remain in place. A focused run through
the real Markdown renderer, sanitizer and URL rewriter passed these controls in Chromium 151.0.7922.71 and WebKit
26.0 before the final compiled-site CI run. No browser-wide preference flag is needed by the corrected harness.

## Limits

The observations concern the recorded Chromium and WebKit runs and this SVG, not all browsers or every system preference. Pixel equality
at two times is bounded evidence, not a proof of the entire timeline; source inspection and visual review of the
full still and representative phases remain necessary. The initial size/theme screenshots proved image loading
and bounds only. Do not relabel them as reduced-motion acceptance. Final compiled-consumer results belong to
PR #412's exact source revision and CI runs.

## The homepage hit the same consumer boundary

**Evidence, 2026-11-12 UTC, #605 / #606:** source `06992ad2` passed the shared
reduced-motion SVG rule, and a bounded art-only Chromium probe sampled the full
eight-second desktop scene at 0/2/4/6/8 seconds. The actual 390px homepage image in
a `reducedMotion: 'reduce'` context still selected `learning-loop-mobile.svg`;
two raw painted image screenshots 900ms apart differed, and the first/orange part
remained visible rather than the completed corrected part. The run had zero page
errors and zero model-data requests, but that did not make its still valid.

The corrective source selects explicit generated finished desktop/mobile images
from parent `<picture>` media, retains the completed collaboration and corrected
part, and removes animated elements/declarations from the stills. It reuses the
existing actual-image comparison plus planted moving-still rejection control.
The original failed receipt is retained; a new source-bound browser pass is
required before claiming recovery. The rule above remains unchanged: inspect the
actual image consumer, not only the standalone SVG or parent preference.
