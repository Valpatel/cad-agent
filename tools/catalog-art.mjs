/** Catalogue covers drawn from data (tools/site-catalog.mjs): never an outside image, never a fake screenshot.
 *
 * Every glyph is a line drawing in a 100 x 100 box (stroke only; class "a" is the accent colour), one per area of
 * docs/areas.yaml plus a few for the buckets and kinds. Covers are 400 x 300 SVG files:
 * - outside projects, libraries and benchmarks: what they are built on (the kernel or tool family: build123d,
 *   OpenSCAD, KiCad, FreeCAD, a mesh tool, a slicer, a solver...) as the main glyph in its own colour, the one number
 *   that matters as large type (GitHub stars, or a benchmark's size or venue), licence and status as labelled tags, and
 *   a band naming what it makes or where it runs (its processes or clients, else its areas). All of it from
 *   upstreams/registry.yaml and research/landscape.json;
 * - charts we draw from our own tools' results (docs/catalog.yaml), e.g. the trade-off cad-agent compare plots;
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
  'cad-modelling': '<path d="M14 36 50 18l36 18v38L50 92 14 74z"/><path d="M14 36l36 18 36-18M50 54v38"/><ellipse class="a" cx="68" cy="66" rx="7" ry="10"/>',
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
/** What an outside entry is built on: the main glyph of its cover, in the family's colour. `match` reads the entry's
 * own words (kernel, name, what); the first family that matches wins, so specific tools come before general ones. */
export const FAMILIES = [
  { key: 'kicad', label: 'KiCad', color: '#2f6f39', match: /\bkicad|kipy|pcbnew|\bpcb\b|gerber/, glyph: '<rect x="10" y="16" width="80" height="68" rx="6"/><path d="M26 34h20l10 10h18M26 66h14l8-8h26"/><circle class="a" cx="26" cy="34" r="5"/><circle class="a" cx="26" cy="66" r="5"/><circle cx="78" cy="44" r="5"/><circle cx="78" cy="58" r="5"/>' },
  { key: 'slicer', label: 'Slicer', color: '#c2410c', match: /slicer|slicing|bambu|prusa|orca/, glyph: '<path d="M36 8h28v16L50 40 36 24z"/><path class="a" d="M50 40v10"/><path d="M14 60h72M20 70h60M26 80h48M32 90h36"/>' },
  { key: 'openscad', label: 'OpenSCAD', color: '#a16207', match: /openscad/, glyph: '<path d="M12 40h48v48H12z"/><circle cx="62" cy="38" r="26"/><path class="a" d="M60 64a26 26 0 0 1-24-24"/>' },
  { key: 'build123d', label: 'build123d', color: '#1f6f8b', match: /build123d|\bb123d|bd_warehouse/, glyph: '<path d="M14 34 50 16l36 18v36L50 88 14 70z"/><path d="M14 34l36 18 36-18M50 52v36"/><path class="a" d="M62 64c6-3 12 0 12 6s-6 10-12 7-6-10 0-13z"/>' },
  { key: 'cadquery', label: 'CadQuery', color: '#1f6f8b', match: /cadquery|\bocp\b|occt|open ?cascade/, glyph: '<path d="M14 34 50 16l36 18v36L50 88 14 70z"/><path d="M14 34l36 18 36-18M50 52v36"/><path class="a" d="M24 58l16 8"/>' },
  { key: 'freecad', label: 'FreeCAD', color: '#9a3412', match: /freecad/, glyph: '<path d="M14 82V30l24-14h48v32L62 82z"/><path d="M14 30h24V16"/><path class="a" d="M28 92h44M28 88v8M72 88v8"/><circle cx="50" cy="50" r="10"/>' },
  { key: 'blender', label: 'Blender', color: '#6b4fa0', match: /blender/, glyph: '<circle cx="50" cy="50" r="36"/><path d="M14 50h72M50 14c-14 10-14 62 0 72M50 14c14 10 14 62 0 72M22 30c18 6 38 6 56 0M22 70c18-6 38-6 56 0"/><circle class="a" cx="72" cy="30" r="5"/>' },
  { key: 'cloud', label: 'Cloud CAD', color: '#475569', match: /onshape|fusion|zoo|\bkcl\b|solidworks|closed/, glyph: '<path d="M28 74h46a16 16 0 0 0 2-32 22 22 0 0 0-42-6 18 18 0 0 0-6 38z"/><path class="a" d="M40 52l10-6 10 6v12l-10 6-10-6z"/>' },
  { key: 'mesh', label: 'Mesh', color: '#6b4fa0', match: /mesh|trimesh|manifold|pyvista|meshio|\bstl\b/, glyph: '<path d="M12 70 34 22l34 8 20 44-36 14z"/><path d="M34 22 52 88M12 70l56-40M34 22l54 52M12 70h76"/><circle class="a" cx="68" cy="30" r="5"/>' },
  { key: 'fea', label: 'FEA', color: '#0f766e', match: /calculix|\bfea\b|\bfem\b|fenics|elmer|scikit-fem|finite.element|stress/, glyph: '<path d="M10 84 28 18 54 46 84 14 90 84z"/><path d="M10 84 54 46 90 84M28 18 54 46 84 14"/><path class="a" d="M54 46 32 84M54 46 68 84"/>' },
  { key: 'cfd', label: 'CFD', color: '#0f766e', match: /openfoam|\bcfd\b|airflow|fluid/, glyph: '<circle cx="50" cy="50" r="13"/><path class="a" d="M6 28c22 0 26 9 44 9s22-9 44-9"/><path d="M6 50h24M70 50h24M6 72c22 0 26-9 44-9s22 9 44 9"/>' },
  { key: 'harness', label: 'Harness', color: '#b45309', match: /harness|wireviz|cable/, glyph: '<path d="M10 30h20c14 0 14 40 28 40h32M10 50h20c10 0 14 20 28 20M10 70h20c8 0 12-10 20-10"/><rect class="a" x="80" y="58" width="12" height="24" rx="2"/><path d="M6 24v52"/>' },
  { key: 'parts', label: 'Parts library', color: '#1f6f8b', match: /fastener|warehouse|partcad|package manager|parts/, glyph: '<path d="M28 12h44l8 14H20z"/><path d="M38 26v56l12 8 12-8V26"/><path class="a" d="M38 40l24 8M38 54l24 8M38 68l24 8"/>' },
  { key: 'benchmark', label: 'Benchmark', color: '#4338ca', match: /benchmark|bench\b|eval|dataset|leaderboard|arena/, glyph: '<path d="M10 88h80"/><path d="M18 88V58h14v30M42 88V38h14v50M66 88V22h14v66"/><circle class="a" cx="73" cy="12" r="6"/>' },
  { key: 'agent', label: 'Agent tools', color: '#bd3a12', match: /\bmcp\b|agent|plugin|skill|llm|claude|codex/, glyph: '<rect x="18" y="28" width="64" height="50" rx="12"/><circle class="a" cx="38" cy="52" r="6"/><circle class="a" cx="62" cy="52" r="6"/><path d="M50 28V14M42 14h16M40 66h20"/>' },
];
/** The family an outside entry belongs to, from its own text; null when nothing matches. */
export const familyOf = text => FAMILIES.find(f => f.match.test(String(text || '').toLowerCase())) || null;

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
export const LICENCE_STYLE = { permissive: ['#d8efbb', '#2f6f39'], copyleft: ['#ffe1cc', '#a42d0c'], other: ['#ffffff', '#526863'] };


/** "22.9k" for 22,951: the number a reader takes in at a glance. */
export const shortNumber = n => n >= 1e5 ? `${Math.round(n / 1e3)}k` : n >= 1e3 ? `${(Math.floor(n / 100) / 10).toFixed(1).replace(/\.0$/, '')}k` : String(n);

/** A labelled tag (text, colours, dashed edge) at x, y, at most maxW wide; returns [svg, width]. */
const pill = (text, x, y, [bg, fg], { dashed = false, size = 15, maxW = 400 } = {}) => {
  const per = size * 0.6, fit = Math.floor((maxW - 18) / per);
  text = String(text);
  if (text.length > fit) text = text.slice(0, fit - 1) + '…';
  const w = text.length * per + 18;
  return [`<g transform="translate(${r1(x)} ${r1(y)})"><rect width="${r1(w)}" height="${size + 14}" rx="${(size + 14) / 2}" fill="${bg}" stroke="${fg}" stroke-width="1.5"${dashed ? ' stroke-dasharray="4 3"' : ''}/>` +
    `<text x="${r1(w / 2)}" y="${size + 4}" text-anchor="middle" font-family="${esc(MONO)}" font-size="${size}" font-weight="700" fill="${fg}">${esc(text)}</text></g>`, w];
};

/** Fit a line of text into a width by dropping items from the end ("FDM · SLA · SLS +7"). */
const fitList = (items, maxChars) => {
  if (items[0].length > maxChars) return items[0].slice(0, maxChars - 1) + '…';
  const out = [];
  for (const [i, t] of items.entries()) {
    const rest = items.length - i - 1, line = [...out, t].join(' · ') + (rest ? ` +${rest}` : '');
    if (line.length > maxChars && out.length) return out.join(' · ') + ` +${items.length - out.length}`;
    out.push(t);
  }
  return out.join(' · ');
};

/** Outside project, library or benchmark: what it is built on, its one number, licence, status, what it makes. */
export function outsideCover({ kind, family, glyphSlug, tint, headline, license, licFamily, status, band, name }) {
  const color = family?.color || INK;
  const art = family ? family.glyph : glyphFor(glyphSlug);
  const cx = 104, cy = 128;
  const disc = `<circle cx="${cx}" cy="${cy}" r="76" fill="#fffdf5" fill-opacity=".94"/><circle cx="${cx}" cy="${cy}" r="76" fill="${color}" fill-opacity=".1" stroke="${color}" stroke-width="3"/>` +
    `<circle cx="${cx}" cy="${cy}" r="86" fill="none" stroke="${color}" stroke-opacity=".28" stroke-width="2" stroke-dasharray="2 6" stroke-linecap="round"/>` +
    `<g transform="translate(${cx - 46} ${cy - 46}) scale(.92)" fill="none" stroke="${color}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round">${art.replaceAll('class="a"', `stroke="${ACCENT}"`)}</g>`;
  const x = 206;
  const famLabel = family && family.label.toLowerCase() !== kind ? `<text x="${x}" y="64" font-family="${esc(MONO)}" font-size="15" font-weight="700" letter-spacing="1.4" fill="${color}">${esc(family.label.toUpperCase())}</text>` : '';
  // The headline: a number in large type (stars, or a benchmark's size), else a short fact (its venue).
  let big = '';
  if (headline?.number != null) {
    const n = String(headline.number), size = Math.min(62, Math.floor(184 / (n.length * 0.62)));
    big = `<text x="${x - 3}" y="132" font-family="${esc(SANS)}" font-size="${size}" font-weight="800" letter-spacing="-2" fill="${INK}">${esc(n)}</text>` +
      `<text x="${x}" y="158" font-family="${esc(SANS)}" font-size="16" font-weight="600" fill="${MUTED}">${esc(headline.unit)}</text>`;
  } else if (headline?.text) {
    const t = String(headline.text), size = Math.min(32, Math.floor(184 / (t.length * 0.6)));
    big = `<text x="${x}" y="122" font-family="${esc(SANS)}" font-size="${size}" font-weight="800" letter-spacing="-.5" fill="${INK}">${esc(t)}</text>` +
      (headline.unit ? `<text x="${x}" y="150" font-family="${esc(SANS)}" font-size="16" font-weight="600" fill="${MUTED}">${esc(headline.unit)}</text>` : '');
  }
  // Licence and status as words.
  const right = W - 14;
  const [licSvg, licW] = pill(String(license || 'no licence'), x, 176, LICENCE_STYLE[licFamily] || LICENCE_STYLE.other, { dashed: licFamily === 'other', maxW: right - x });
  const st = STATUS_STYLE[status] || STATUS_STYLE.reference, stW = st[2].length * 9 + 18, inline = x + licW + 8 + stW <= right;
  const [stSvg] = pill(st[2], inline ? x + licW + 8 : x, inline ? 176 : 211, [st[0], st[1]], { dashed: status === 'unverified' });
  // The band: what it makes or where it runs.
  const bandSvg = band?.items?.length ? `<rect y="246" width="${W}" height="54" fill="#ffffff" fill-opacity=".86"/><path d="M0 246h${W}" stroke="${color}" stroke-width="3"/>` +
    `<text x="24" y="266" font-family="${esc(MONO)}" font-size="12" font-weight="700" letter-spacing="1.4" fill="${MUTED}">${esc(band.label.toUpperCase())}</text>` +
    `<text x="24" y="289" font-family="${esc(SANS)}" font-size="17" font-weight="700" fill="${INK}">${esc(fitList(band.items, 36))}</text>` : '';
  const label = `${name}: ${kind}${family ? ` on ${family.label}` : ''}, ${headline?.number != null ? `${headline.number} ${headline.unit}` : headline?.text || ''}, ${license || 'no licence'}, ${st[2]}` +
    (band?.items?.length ? `; ${band.label}: ${band.items.join(', ')}` : '');
  return frame(tint, disc + tag(kind, 24, 32) + famLabel + big + licSvg + stSvg + bandSvg, label);
}

/** A chart from one of our tools' results (docs/catalog.yaml): points on two axes, the Pareto front joined. */
export function chartCover({ title, x: xLabel, y: yLabel, points = [], tint, name }) {
  const L = 62, R = 376, T = 58, B = 236;
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const pad = (lo, hi) => { const d = (hi - lo) || 1; return [lo - d * 0.12, hi + d * 0.12]; };
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
  const px = v => L + (v - x0) / (x1 - x0) * (R - L), py = v => B - (v - y0) / (y1 - y0) * (B - T);
  const grid = [0.25, 0.5, 0.75].map(f => `M${L} ${r1(T + f * (B - T))}H${R}M${r1(L + f * (R - L))} ${T}V${B}`).join('');
  const front = points.filter(p => p.front).sort((a, b) => a.x - b.x);
  const line = front.length > 1 ? `<path d="M${front.map(p => `${r1(px(p.x))} ${r1(py(p.y))}`).join('L')}" fill="none" stroke="${ACCENT}" stroke-width="4" stroke-linecap="round"/>` : '';
  const dots = points.map(p => {
    const cxp = r1(px(p.x)), cyp = r1(py(p.y)), right = px(p.x) < (L + R) / 2;
    const mark = p.fail ? `<circle cx="${cxp}" cy="${cyp}" r="8" fill="#fff" stroke="${MUTED}" stroke-width="3"/>`
      : `<circle cx="${cxp}" cy="${cyp}" r="${p.front ? 10 : 8}" fill="${p.front ? ACCENT : MUTED}" stroke="#fff" stroke-width="2.5"/>`;
    return mark + `<text x="${r1(px(p.x) + (right ? 15 : -15))}" y="${r1(py(p.y) + 6)}" text-anchor="${right ? 'start' : 'end'}" font-family="${esc(SANS)}" font-size="17" font-weight="700" fill="${p.fail ? MUTED : INK}">${esc(p.label)}${p.fail ? ' ✕' : ''}</text>`;
  }).join('');
  const body = `<rect x="12" y="12" width="${W - 24}" height="${H - 24}" rx="14" fill="#ffffff" fill-opacity=".92" stroke="${INK}" stroke-opacity=".15"/>` +
    `<text x="28" y="42" font-family="${esc(SANS)}" font-size="17" font-weight="800" fill="${INK}">${esc(title)}</text>` +
    `<path d="${grid}" stroke="${INK}" stroke-opacity=".08" stroke-width="1.5"/><path d="M${L} ${T}V${B}H${R}" fill="none" stroke="${INK}" stroke-width="2"/>` +
    line + dots +
    `<text x="${R}" y="${B + 26}" text-anchor="end" font-family="${esc(SANS)}" font-size="14" font-weight="600" fill="${MUTED}">${esc(xLabel)} →</text>` +
    `<text transform="translate(${L - 16} ${B}) rotate(-90)" font-family="${esc(SANS)}" font-size="14" font-weight="600" fill="${MUTED}">${esc(yLabel)} →</text>` +
    (front.length ? `<text x="${L + 6}" y="${B + 26}" font-family="${esc(MONO)}" font-size="12" font-weight="700" fill="${ACCENT}">— PARETO FRONT</text>` : '');
  const label = `${name}: ${title}. ${points.map(p => `${p.label} ${p.x} ${xLabel}, ${p.y} ${yLabel}${p.front ? ' (on the front)' : ''}${p.fail ? ' (fails a requirement)' : ''}`).join('; ')}`;
  return frame(tint, body, label);
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
