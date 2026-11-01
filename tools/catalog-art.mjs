/** Catalogue covers drawn from data (tools/site-catalog.mjs): never an outside image, never a fake screenshot.
 *
 * Every glyph is a line drawing in a 100 x 100 box (stroke only; class "a" is the accent colour), one per area of
 * docs/areas.yaml plus a few for the buckets and kinds. Covers are 400 x 300 SVG files:
 * - outside projects, libraries and benchmarks: the area glyph (or the kind's, until the entry is placed) inside
 *   rings for its GitHub stars (one ring per factor of ten, the last one drawn as far as the stars reach), a licence
 *   badge coloured by family, a track for the last push (the dashed stretch is the time since), a status ribbon;
 * - our pages: the page's outline as bars, one per section, as long as its text, marked when the section has a
 *   picture, diagram or code; lessons draw one tile per lesson;
 * - commands without a figure: the command and its real flags, read from cli.py;
 * - animated figures: a still frame (stillFrame) for the page, the moving original on hover, focus or in view.
 * Tinted by domain, on engineering-paper squares, so the set reads as one family.
 */
const INK = '#173d3c', ACCENT = '#bd3a12', MUTED = '#526863';
const MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";
const SANS = "Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif";
export const W = 400, H = 300;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const r1 = n => Math.round(n * 10) / 10;

function gearPath(cx, cy, teeth, outer, inner) {
  const pts = [];
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2, s = Math.PI / teeth;
    for (const [da, r] of [[-s * 0.55, inner], [-s * 0.32, outer], [s * 0.32, outer], [s * 0.55, inner]])
      pts.push(`${r1(cx + r * Math.cos(a + da))} ${r1(cy + r * Math.sin(a + da))}`);
  }
  return `M${pts.join('L')}Z`;
}

/** Area, domain, bucket and kind glyphs: SVG fragments in a 100 x 100 box. */
export const GLYPHS = {
  // mechanical design
  mechanisms: '<path d="M16 80 40 34 82 54"/><circle cx="16" cy="80" r="7"/><circle cx="40" cy="34" r="7"/><circle class="a" cx="82" cy="54" r="7"/><path d="M4 92h26"/>',
  'housings-and-enclosures': '<rect x="14" y="44" width="72" height="42" rx="5"/><path class="a" d="M10 28h80v9H10z"/><path d="M28 64h16M60 58v14"/>',
  'compliant-mechanisms': '<path d="M16 10v80M16 32h54l14 18H62l-6-6H16"/><path class="a" d="M50 72h36v12H50z"/>',
  gears: `<path d="${gearPath(50, 50, 10, 40, 31)}"/><circle class="a" cx="50" cy="50" r="10"/>`,
  'belt-and-chain-drives': '<circle cx="30" cy="50" r="19"/><circle cx="76" cy="50" r="11"/><path d="M30 31 76 39M30 69 76 61"/><circle class="a" cx="30" cy="50" r="5"/>',
  'wheels-and-driving': '<circle cx="50" cy="46" r="34"/><circle class="a" cx="50" cy="46" r="8"/><path d="M50 12v26M50 54v26M16 46h26M58 46h26"/><path d="M6 88h88"/>',
  walking: '<path d="M50 12 28 44 58 72 50 90"/><circle cx="50" cy="12" r="6"/><circle cx="28" cy="44" r="6"/><circle cx="58" cy="72" r="6"/><path class="a" d="M34 92h32"/>',
  'fasteners-and-hardware': '<path d="M28 12h44l8 14H20z"/><path d="M38 26v56l12 8 12-8V26"/><path class="a" d="M38 40l24 8M38 54l24 8M38 68l24 8"/>',
  'fixtures-and-jigs': '<path d="M8 80h84M14 20h72"/><path d="M24 80V42M42 80V42M60 80V42M78 80V42"/><path class="a" d="M24 34v2M42 34v2M60 34v2M78 34v2"/>',
  'mould-design': '<rect x="12" y="14" width="76" height="32" rx="3"/><rect x="12" y="54" width="76" height="32" rx="3"/><path class="a" d="M32 46a18 11 0 0 0 36 0M32 54a18 11 0 0 1 36 0"/>',
  // manufacturing
  '3d-printing': '<path d="M34 10h32v16L50 44 34 26z"/><path class="a" d="M50 44v8"/><path d="M16 62h68M16 72h68M16 82h68"/>',
  'cnc-machining': '<path d="M42 8h16v32H42z"/><path d="M42 40l8 12 8-12"/><path d="M10 60h80v26H10z"/><path class="a" d="M32 60v10h36V60"/>',
  'laser-cutting': '<path d="M38 8h24l-7 20H45z"/><path class="a" d="M50 28v34"/><path d="M8 62h36M56 62h36M8 84h84M8 62v22M92 62v22"/>',
  'sheet-metal': '<path d="M20 12v54a18 18 0 0 0 18 18h50"/><path class="a" d="M34 12v54a4 4 0 0 0 4 4h50"/>',
  'mould-making': '<path d="M20 40h60l-7 46H27z"/><path class="a" d="M62 8c0 16-12 14-12 32"/><path d="M28 62h44"/>',
  // thermal
  'heat-sinks': '<path d="M10 80h80"/><path d="M18 80V32M32 80V22M46 80V32M60 80V22M74 80V32"/><path class="a" d="M24 92h52"/>',
  'airflow-and-fans': '<circle cx="50" cy="50" r="38"/><path class="a" d="M50 50c0-15 8-23 19-23M50 50c13 6 17 19 10 28M50 50c-13 6-27 2-31-9"/><circle cx="50" cy="50" r="5"/>',
  'thermal-validation': '<path d="M42 14a8 8 0 0 1 16 0v46a14 14 0 1 1-16 0z"/><path class="a" d="M50 30v38"/><circle class="a" cx="50" cy="72" r="6"/><path d="M68 22h14M68 36h9M68 50h14"/>',
  // simulation and validation
  'structural-fea': '<path d="M10 84 28 18 54 46 84 14 90 84z"/><path d="M10 84 54 46 90 84M28 18 54 46 84 14"/><path class="a" d="M54 46 32 84M54 46 68 84"/>',
  cfd: '<circle cx="50" cy="50" r="13"/><path class="a" d="M6 28c22 0 26 9 44 9s22-9 44-9"/><path d="M6 50h24M70 50h24M6 72c22 0 26-9 44-9s22 9 44 9"/>',
  'motion-and-dynamics': '<path d="M50 10v38"/><circle cx="50" cy="10" r="4"/><circle class="a" cx="50" cy="58" r="11"/><path d="M14 42a38 38 0 0 0 72 0" stroke-dasharray="5 7"/>',
  'topology-optimisation': '<path d="M8 82h84M12 82c6-30 22-52 38-58 16 6 32 28 38 58"/><path class="a" d="M30 82c4-17 11-28 20-32 9 4 16 15 20 32"/><path d="M50 24V10"/>',
  'design-exploration': '<path d="M12 10v78h78"/><path d="M34 62h.1M46 50h.1M58 66h.1M70 54h.1M40 74h.1M66 38h.1" stroke-width="9"/><path class="a" d="M22 26c10 22 28 38 58 46"/>',
  'results-and-visuals': '<path d="M10 88h80"/><path d="M18 88V58h14v30M42 88V38h14v50M66 88V22h14v66"/><path class="a" d="M12 50 38 30 60 38 88 12"/>',
  'physical-tests': '<path d="M8 34h22l8 9h24l8-9h22v32H70l-8-9H38l-8 9H8z"/><path class="a" d="M50 43v14M2 50h6M92 50h6"/>',
  // electrical design
  'electrical-panels': '<path d="M8 28h84M8 72h84"/><rect x="16" y="36" width="15" height="28"/><rect x="38" y="36" width="15" height="28"/><rect class="a" x="60" y="36" width="15" height="28"/>',
  'wiring-harnesses': '<path d="M8 22c30 0 30 28 58 28M8 50h58M8 78c30 0 30-28 58-28"/><rect class="a" x="66" y="36" width="24" height="28" rx="4"/>',
  'circuit-boards': '<rect x="30" y="30" width="40" height="40" rx="4"/><path d="M38 30V14M50 30V14M62 30V14M38 86V70M50 86V70M62 86V70M30 42H14M30 58H14M86 42H70M86 58H70"/><circle class="a" cx="50" cy="50" r="7"/>',
  'test-systems': '<rect x="8" y="16" width="84" height="58" rx="6"/><path class="a" d="M16 52h12l6-20 10 30 8-24 8 14h24"/><path d="M34 90h32M50 74v16"/>',
  // practice
  'agent-workflow': '<path d="M28 20v60M28 32c0 12 44 6 44 18s-44 6-44 18"/><circle cx="28" cy="14" r="6"/><circle class="a" cx="72" cy="50" r="7"/><circle cx="28" cy="86" r="6"/>',
  'design-process': '<rect x="16" y="10" width="68" height="80" rx="6"/><path class="a" d="M27 32l6 6 11-13M27 56l6 6 11-13"/><path d="M52 34h22M52 58h22M27 78h46"/>',
  'review-and-evidence': '<circle cx="42" cy="42" r="26"/><path d="M61 61l27 27"/><path class="a" d="M30 42l8 8 15-16"/>',
  publishing: '<rect x="8" y="16" width="84" height="68" rx="6"/><path d="M8 32h84"/><path class="a" d="M22 48h34M22 60h56M22 71h42"/>',
  evaluation: '<circle cx="50" cy="50" r="38"/><circle cx="50" cy="50" r="23"/><circle class="a" cx="50" cy="50" r="8"/><path d="M50 2v18M50 80v18M2 50h18M80 50h18"/>',
  // buckets and kinds
  'cross-cutting': '<circle cx="50" cy="50" r="38"/><path class="a" d="M50 16l11 34-11 34-11-34z"/><path d="M50 4v8M50 88v8M4 50h8M88 50h8"/>',
  unplaced: '<rect x="16" y="16" width="68" height="68" rx="10" stroke-dasharray="9 8"/><path class="a" d="M40 40a10 10 0 1 1 13 10c-3 1-3 3-3 7M50 66v1"/>',
  project: '<circle class="a" cx="50" cy="50" r="13"/><circle cx="16" cy="20" r="8"/><circle cx="84" cy="20" r="8"/><circle cx="16" cy="80" r="8"/><circle cx="84" cy="80" r="8"/><path d="M40 41 23 26M60 41l17-15M40 59 23 74M60 59l17 15"/>',
  library: '<path d="M32 12c-12 0-12 8-12 19s-5 19-12 19c7 0 12 8 12 19s0 19 12 19M68 12c12 0 12 8 12 19s5 19 12 19c-7 0-12 8-12 19s0 19-12 19"/><path class="a" d="M38 40h24M38 60h24"/>',
  benchmark: '<path d="M8 88h84"/><path d="M12 88V58h26v30M38 88V36h26v52M64 88V68h24v20"/><path class="a" d="M51 8l4 9 10 1-7 7 2 10-9-5-9 5 2-10-7-7 10-1z"/>',
  demo: '<circle cx="50" cy="50" r="38"/><path class="a" d="M41 31v38l29-19z"/>',
  tool: '<rect x="8" y="16" width="84" height="68" rx="8"/><path class="a" d="M22 40l12 10-12 10"/><path d="M42 62h24"/>',
};
export const DOMAIN_GLYPH = { mechanical: 'gears', manufacturing: '3d-printing', thermal: 'heat-sinks', simulation: 'structural-fea',
  electrical: 'circuit-boards', practice: 'agent-workflow' };
/** Two-stop background tints by domain, from the site's palette. */
export const TINT = {
  mechanical: ['#eef8fb', '#cfe3ec'], manufacturing: ['#fff7d9', '#f4e1a2'], thermal: ['#ffefe3', '#f6d3b8'],
  simulation: ['#eef8e4', '#d0e8b6'], electrical: ['#eef1fb', '#d3dbf0'], practice: ['#f7f5ea', '#e5e7d3'],
  'cross-cutting': ['#f4f8ee', '#dde8d4'], unplaced: ['#f6f6f0', '#e4e6dc'],
};
export const glyphFor = slug => GLYPHS[slug] || GLYPHS[DOMAIN_GLYPH[slug]] || GLYPHS.unplaced;

/** One <symbol> per glyph, for the page to <use> (the area tree's icons). */
export const glyphSprite = slugs => `<svg class="glyph-sprite" width="0" height="0" aria-hidden="true" focusable="false"><defs>${slugs
  .map(s => `<symbol id="g-${s}" viewBox="0 0 100 100">${glyphFor(s).replaceAll('class="a"', 'style="stroke:var(--glyph-accent,#bd3a12)"')}</symbol>`).join('')}</defs></svg>`;

const frame = (tint, body, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(label)}">
<defs><linearGradient id="t" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${tint[0]}"/><stop offset="1" stop-color="${tint[1]}"/></linearGradient>
<pattern id="p" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="${INK}" stroke-opacity=".07"/></pattern></defs>
<rect width="${W}" height="${H}" fill="url(#t)"/><rect width="${W}" height="${H}" fill="url(#p)"/>
${body}</svg>
`;
const glyph = (slug, x, y, size, { stroke = INK, accent = ACCENT, width = 5, opacity = 1 } = {}) =>
  `<g transform="translate(${r1(x)} ${r1(y)}) scale(${r1(size / 100 * 1000) / 1000})" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"${opacity < 1 ? ` opacity="${opacity}"` : ''}>${glyphFor(slug).replaceAll('class="a"', `stroke="${accent}"`)}</g>`;
const tag = (text, x = 24, y = 34, fill = INK) => `<text x="${x}" y="${y}" font-family="${esc(MONO)}" font-size="13" font-weight="700" letter-spacing="1.6" fill="${fill}">${esc(text.toUpperCase())}</text>`;

export const STATUS_STYLE = {
  ours: ['#ffe1cc', '#7f260e', 'built here'], adopted: ['#2f6f39', '#ffffff', 'adopted'], used: ['#2f6f39', '#ffffff', 'used'],
  trial: ['#ffe48a', '#5b4700', 'in trial'], candidate: ['#d7e9f1', '#1d4b5c', 'candidate'], rejected: ['#d9d8d0', '#3e4a47', 'rejected'],
  reference: ['#eef1e4', '#2f4b46', 'tracked'], unverified: ['#ffffff', '#6a4b00', 'unverified'],
};
const ribbon = status => {
  const [bg, fg, text] = STATUS_STYLE[status] || STATUS_STYLE.reference;
  return `<g transform="translate(${W} 0) rotate(45)"><rect x="-110" y="40" width="220" height="32" fill="${bg}"${status === 'unverified' ? ` stroke="${fg}" stroke-dasharray="5 4"` : ''}/>` +
    `<text x="0" y="61" text-anchor="middle" font-family="${esc(MONO)}" font-size="14" font-weight="700" letter-spacing="1.2" fill="${fg}">${esc(text.toUpperCase())}</text></g>`;
};
export const LICENCE_STYLE = { permissive: ['#d8efbb', '#2f6f39'], copyleft: ['#ffe1cc', '#a42d0c'], other: ['#ffffff', '#526863'] };
const licenceBadge = (license, family, x, y) => {
  const [bg, fg] = LICENCE_STYLE[family] || LICENCE_STYLE.other, text = String(license || 'no licence');
  const w = Math.max(56, text.length * 8.6 + 24);
  return `<g transform="translate(${x} ${y})"><rect width="${r1(w)}" height="28" rx="14" fill="${bg}" stroke="${fg}" stroke-width="1.5"${family === 'other' ? ' stroke-dasharray="4 3"' : ''}/>` +
    `<text x="${r1(w / 2)}" y="19" text-anchor="middle" font-family="${esc(MONO)}" font-size="13" font-weight="700" fill="${fg}">${esc(text)}</text></g>`;
};

/** Months between two ISO dates (b after a), as a fraction. */
const months = (a, b) => (Date.parse(b) - Date.parse(a)) / (30.44 * 864e5);

/** Outside entry: glyph in its star rings, licence, last push, status. */
export function outsideCover({ kind, glyphSlug, tint, stars, license, family, lastPush, status, asOf, name }) {
  const cx = 200, cy = 146, base = 46, step = 21;
  let rings = '';
  const decades = stars > 0 ? Math.log10(stars) : 0;
  if (!(stars > 0)) rings += `<circle cx="${cx}" cy="${cy}" r="${base + step}" fill="none" stroke="${INK}" stroke-opacity=".18" stroke-width="1.6" stroke-dasharray="1 7" stroke-linecap="round"/>`;
  for (let k = 1; k <= 5; k++) {
    const r = base + step * k;
    if (decades >= k) rings += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${INK}" stroke-opacity=".38" stroke-width="1.6" stroke-dasharray="3 5"/>`;
    else if (decades > k - 1) {                    // the decade it is in, drawn as far as it reaches, clockwise from the top
      const f = decades - (k - 1), a = -Math.PI / 2 + f * Math.PI * 2;
      const ex = cx + r * Math.cos(a), ey = cy + r * Math.sin(a);
      rings += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${INK}" stroke-opacity=".14" stroke-width="1.6"/>` +
        `<path d="M${cx} ${cy - r}A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${r1(ex)} ${r1(ey)}" fill="none" stroke="${ACCENT}" stroke-width="5" stroke-linecap="round"/>` +
        `<circle cx="${r1(ex)}" cy="${r1(ey)}" r="7" fill="${ACCENT}"/>`;
    }
  }
  // Last push on a two-year track ending at the catalogue's date: solid up to the push, dashed after it (quiet time).
  let track = '';
  if (lastPush && asOf) {
    const x0 = 230, x1 = 376, y = 268, span = 24, ago = Math.min(span, Math.max(0, months(lastPush, asOf)));
    const x = x1 - (ago / span) * (x1 - x0);
    const ticks = Array.from({ length: span + 1 }, (_, i) => x0 + (i / span) * (x1 - x0))
      .map((t, i) => `M${r1(t)} ${y - (i % 12 === 0 ? 7 : 3)}v${i % 12 === 0 ? 14 : 6}`).join('');
    const fresh = ago <= 1 ? ACCENT : ago <= 6 ? INK : MUTED;
    track = `<path d="${ticks}" stroke="${INK}" stroke-opacity=".35" stroke-width="1.5"/><path d="M${x0} ${y}H${r1(x)}" stroke="${INK}" stroke-width="3"/>` +
      `<path d="M${r1(x)} ${y}H${x1}" stroke="${INK}" stroke-opacity=".5" stroke-width="3" stroke-dasharray="2 5"/><circle cx="${r1(x)}" cy="${y}" r="7" fill="${fresh}" stroke="#fff" stroke-width="2"/>`;
  }
  const label = `${name}: ${kind}, ${license || 'no licence'}, ${stars != null ? `${stars} GitHub stars` : 'stars not recorded'}${lastPush ? `, last push ${lastPush}` : ''}, ${(STATUS_STYLE[status] || STATUS_STYLE.reference)[2]}`;
  return frame(tint, `${rings}<circle cx="${cx}" cy="${cy}" r="${base - 2}" fill="#fffdf5" fill-opacity=".9" stroke="${INK}" stroke-opacity=".25"/>` +
    glyph(glyphSlug, cx - 30, cy - 30, 60) + tag(kind) + licenceBadge(license, family, 22, 254) + track + ribbon(status), label);
}

/** Our page: its sections as bars (length = words), marked for pictures and code; lessons as one tile per lesson. */
export function pageCover({ kind, glyphSlug, tint, sections = [], lessons = 0, title }) {
  let body = '';
  if (lessons) {
    const n = Math.min(lessons, 20), cols = n > 12 ? 5 : 4, w = n > 12 ? 34 : 40, h = n > 12 ? 26 : 30, gx = 9, gy = 10;
    for (let i = 0; i < n; i++) {
      const x = 24 + (i % cols) * (w + gx), y = 56 + Math.floor(i / cols) * (h + gy);
      body += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="#fffdf5" stroke="${INK}" stroke-width="1.8"/><path d="M${x + 9} ${y + h / 2 - 4}h${w - 18}M${x + 9} ${y + h / 2 + 4}h${w / 2 - 8}" stroke="${i % 3 ? INK : ACCENT}" stroke-width="2.5" stroke-linecap="round" stroke-opacity=".8"/>`;
    }
  } else {
    const list = sections.slice(0, 9), most = Math.max(1, ...list.map(s => s.words));
    list.forEach((s, i) => {
      const y = 60 + i * 23, w = 24 + 176 * Math.sqrt(s.words / most);
      body += `<rect x="24" y="${y}" width="${r1(w)}" height="12" rx="6" fill="${s.figure ? ACCENT : INK}" fill-opacity="${s.figure ? 0.9 : 0.72}"/>` +
        (s.code ? `<rect x="${r1(30 + w)}" y="${y}" width="16" height="12" rx="3" fill="#28736c" fill-opacity=".85"/>` : '');
    });
    if (!list.length) body += `<rect x="24" y="60" width="180" height="12" rx="6" fill="${INK}" fill-opacity=".72"/>`;
  }
  return frame(tint, `<circle cx="306" cy="160" r="80" fill="#fffdf5" fill-opacity=".72" stroke="${INK}" stroke-opacity=".18"/>` +
    glyph(glyphSlug, 252, 106, 108, { width: 4.5 }) + body + tag(kind), `${title}: ${kind}`);
}

/** A command with no figure: its call and its real flags, as a terminal. */
export function toolCover({ name, flags = [], glyphSlug, title }) {
  const shown = flags.slice(0, 5);
  const lines = shown.map((f, i) => `<text x="34" y="${150 + i * 25}" font-family="${esc(MONO)}" font-size="16" fill="#cfe8b4">  ${esc(f)}</text>`).join('');
  const more = flags.length > shown.length ? `<text x="34" y="${150 + shown.length * 25}" font-family="${esc(MONO)}" font-size="16" fill="#8fb3a9">  … ${flags.length - shown.length} more</text>` : '';
  const size = Math.min(25, Math.floor(352 / ((12 + name.length) * 0.62)));   // monospace: about 0.6 em a character
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(title)}: cad-agent ${esc(name)} and its options">
<defs><linearGradient id="t" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1d4a48"/><stop offset="1" stop-color="#0f2c2b"/></linearGradient></defs>
<rect width="${W}" height="${H}" fill="url(#t)"/>${glyph(glyphSlug, 262, 150, 130, { stroke: '#fffdf5', accent: '#f39a6b', width: 4, opacity: 0.22 })}
<circle cx="28" cy="26" r="6" fill="#f39a6b"/><circle cx="48" cy="26" r="6" fill="#ffe48a"/><circle cx="68" cy="26" r="6" fill="#9ed27a"/>
<text x="24" y="96" font-family="${esc(MONO)}" font-size="${size}" font-weight="700" fill="#fffdf5"><tspan fill="#f39a6b">$ </tspan>cad-agent <tspan fill="#ffe48a">${esc(name)}</tspan></text>
${lines}${more}</svg>
`;
}

/** A still frame of an animated SVG figure (CSS keyframes or SMIL): every animation paused `at` of the way through the
 * longest one, SMIL elements dropped, so an <img> of it stays still. */
export function stillFrame(svg, at = 0.5) {
  const durations = [...svg.matchAll(/animation(?:-duration)?\s*:[^;}]*?(\d*\.?\d+)(m?s)\b/g)].map(m => parseFloat(m[1]) / (m[2] === 'ms' ? 1000 : 1));
  const t = (Math.max(0, ...durations) * at).toFixed(3);
  const style = `<style>*{animation-delay:-${t}s!important;animation-play-state:paused!important}</style>`;
  return svg.replace(/<(animate|animateTransform|animateMotion|set)\b[^>]*?(?:\/>|>[\s\S]*?<\/\1>)/g, '').replace(/<\/svg>\s*$/, `${style}</svg>\n`);
}
/** True when an SVG figure moves by itself (CSS keyframes or SMIL). */
export const isAnimated = svg => /@keyframes|<animate|<animateTransform|<animateMotion|<set\b/.test(svg);
