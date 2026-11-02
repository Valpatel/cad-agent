// The site's light and dark themes (#305): web/site.css keeps its colours as tokens on :root, a light set and a dark
// one, the dark set chosen by the reader's system or the header's theme button (web/theme.js). This checks the token
// sets match, that text and controls keep their contrast in both, and that no rule outside the token blocks brings a
// light-only colour back. The pages themselves, in both themes: tests/site/website-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const show = f => execFileSync('git', ['show', `HEAD:${f}`], { cwd: root }).toString();
const css = show('web/site.css'), catalog = show('web/catalog.css');

const tokens = block => Object.fromEntries([...block.matchAll(/--([\w-]+):([^;}]+)/g)].map(m => [m[1], m[2].trim()]));
const LIGHT = css.match(/^:root\{(--cream:[^}]*)\}/m)?.[1];
const MEDIA = css.match(/@media\(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{([^}]*)\}\}/)?.[1];
const CHOSEN = css.match(/^:root\[data-theme=dark\]\{([^}]*)\}/m)?.[1];
export const THEMES = { light: tokens(LIGHT ?? ''), dark: tokens(CHOSEN ?? '') };

// WCAG 2 relative luminance and contrast ratio, for #rgb and #rrggbb colours.
const hex6 = c => (c.length === 4 ? '#' + [...c.slice(1)].map(x => x + x).join('') : c).toLowerCase();
const luminance = c => {
  const h = hex6(c);
  const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

test('the light and dark token sets name the same tokens, and both dark blocks say the same', () => {
  assert.ok(LIGHT && MEDIA && CHOSEN, 'web/site.css: the light :root block, the prefers-color-scheme block and the [data-theme=dark] block');
  assert.equal(MEDIA, CHOSEN, 'the system-dark block and the chosen-dark block differ');
  assert.deepEqual(Object.keys(THEMES.dark).sort(), Object.keys(THEMES.light).sort());
  assert.match(LIGHT, /color-scheme:light/); assert.match(CHOSEN, /color-scheme:dark/);
  // the catalogue's tones: the same dark rule twice
  const tone = [...catalog.matchAll(/(?:@media\(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)|:root\[data-theme=dark\]) \[data-tone\]\{([^}]*)\}/g)].map(m => m[1]);
  assert.equal(tone.length, 2, 'web/catalog.css: the dark tone rule, for the system and for the button');
  assert.equal(tone[0], tone[1]);
});

// [text, background, minimum]: body text 4.5:1; large or bold display text and UI parts (borders of inputs, focus rings,
// the orange headline accent) 3:1.
const PAIRS = [
  ['ink', 'cream', 4.5], ['ink', 'card', 4.5], ['ink', 'soft', 4.5], ['ink', 'soft-2', 4.5], ['ink', 'soft-3', 4.5], ['ink', 'code', 4.5],
  ['muted', 'cream', 4.5], ['muted', 'card', 4.5], ['muted', 'soft-2', 4.5], ['text-2', 'card', 4.5], ['text-2', 'soft', 4.5],
  ['text-2', 'green-2', 4.5], ['text-2', 'peach', 4.5], ['faint', 'card', 4.5], ['faint', 'cream', 4.5], ['eyebrow', 'cream', 4.5],
  ['link', 'cream', 4.5], ['link', 'card', 4.5], ['teal', 'card', 4.5], ['teal', 'cream', 4.5], ['orange', 'cream', 4.5],
  ['ink', 'peach', 4.5], ['ink', 'peach-2', 4.5], ['ink', 'green', 4.5], ['ink', 'green-2', 4.5], ['ink', 'yellow', 4.5], ['ink', 'blue', 4.5],
  ['ink', 'grey', 4.5], ['brown', 'peach', 4.5], ['brown', 'peach-2', 4.5], ['brown', 'cream', 4.5], ['sky-ink', 'sky-a', 4.5], ['sky-ink', 'sky-b', 4.5],
  ['ink', 'sky-a', 4.5], ['cream', 'ink', 4.5], ['focus', 'cream', 3], ['focus', 'card', 3], ['line-3', 'card', 3], ['line-3', 'cream', 3],
];
for (const theme of ['light', 'dark']) {
  test(`${theme} theme: text and controls keep their contrast`, () => {
    const t = THEMES[theme], low = [];
    for (const [fg, bg, min] of PAIRS) {
      assert.match(t[fg] ?? '', /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i, `--${fg} is an opaque colour`);
      assert.match(t[bg] ?? '', /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i, `--${bg} is an opaque colour`);
      const c = contrast(t[fg], t[bg]);
      if (c < min) low.push(`--${fg} ${t[fg]} on --${bg} ${t[bg]}: ${c.toFixed(2)}:1 (${min} needed)`);
    }
    assert.deepEqual(low, []);
  });
}

// Rules that keep fixed colours in both themes: the always-dark panels (the reel, the install and prompt boxes, the
// command tiles), the orange buttons and badges with white text, and picture frames. Any other literal colour outside
// the token blocks would show light in the dark theme.
const FIXED = /^(?:\.reel|\.install-|\.use-card \.agent-|\.fit-cmd|\.band-flow code|\.button\.primary|\.rung|\.status-dot|\.hero-scene|\.hero-model cad-model|\.projects img|\.scene-|\.area-link(?:\.dom-all)?\[aria-current|\.key-means|\.sheet-open \.count|\.cat-side\[data-open\]|:root(?::not\(\[data-theme=light\]\)|\[data-theme=dark\]) \[data-tone\])/;
test('outside the token blocks, colours are tokens (or one of the fixed, always-dark parts)', () => {
  const stray = [];
  for (const [file, text] of [['web/site.css', css], ['web/catalog.css', catalog]]) {
    const body = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^:root\{--cream:[^}]*\}$/m, '').replace(/^@media\(prefers-color-scheme:dark\)\{:root:not\(\[data-theme=light\]\)\{[^}]*\}\}$/m, '')
      .replace(/^:root\[data-theme=dark\]\{[^}]*\}$/m, '').replace(/\[data-tone=[\w-]+\]\{[^}]*\}/g, '');
    for (const m of body.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = m[1].trim(), colours = m[2].match(/#[0-9a-f]{3,8}\b/gi);
      if (colours && !FIXED.test(selector) && !/var\(--[\w-]+,#/.test(m[2])) stray.push(`${file}: ${selector.slice(0, 70)} { ${colours.join(' ')} }`);
    }
  }
  assert.deepEqual(stray, []);
});

test('every page loads the theme script first, has the theme button, and no inline script', () => {
  const build = show('tools/build-site.mjs');
  assert.match(build, /<head><meta charset="utf-8">[^\n]*\n<title>[^\n]*\n[^\n]*\n<script src="\/web\/theme\.js"><\/script><link rel="icon"/, 'web/theme.js in <head>, before the stylesheets');
  assert.match(build, /class="theme-toggle" aria-pressed="false" title="Dark theme" hidden>/, 'the button starts hidden (it needs the script)');
  const script = show('web/theme.js');
  assert.match(script, /localStorage/); assert.doesNotMatch(script, /fetch\(|XMLHttpRequest|sendBeacon|navigator\.|document\.cookie/, 'the theme choice stays in this browser');
});
