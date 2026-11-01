/** HTML safety for cad-agent.valpatel.com pages, shared by tools/build-site.mjs and its tests. */
import sanitizeHtml from 'sanitize-html';

// Docs are ours, but research quotes outside sources: the site never serves script from Markdown. Drop <script>,
// <iframe>/<object>/<embed>, inline handlers, and any URL scheme other than http(s), mailto and data: images.
const SAFE_URL = /^(?:https?:|mailto:|data:image\/(?:png|jpe?g|gif|webp);|[^:]*$|[^:]*[/?#])/i;
export const safeUrl = u => SAFE_URL.test(String(u ?? '').trim()) ? String(u ?? '') : '#';
// An allowlist HTML sanitizer (sanitize-html, a parser, not regexes) over the rendered Markdown: the tags and
// attributes our docs use, http(s)/mailto links, http(s)/data images; everything else, every script, handler and
// unknown scheme, is dropped. Text inside code is never touched.
export const SANITIZE = {
  allowedTags: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'img', 'ul', 'ol', 'li', 'pre', 'code', 'blockquote', 'em',
    'strong', 'del', 's', 'b', 'i', 'kbd', 'sub', 'sup', 'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'details', 'summary', 'div', 'span', 'input', 'cad-cantilever', 'cad-fourbar', 'cad-fan-curve', 'cad-torsion-snap',
    'cad-printed-boss'],
  allowedAttributes: { a: ['href', 'title', 'id', 'name'], img: ['src', 'alt', 'title', 'width', 'height'],
    '*': ['id', 'align'], code: ['class'], pre: ['class'], div: ['class'], span: ['class'], td: ['align', 'width'],
    th: ['align', 'width'], input: ['type', 'checked', 'disabled'], ol: ['start'],
    // the kit's interactive demos (kit/cantilever.js, kit/fourbar.js, kit/fan-curve.js, kit/torsion-snap.js,
    // kit/printed-boss.js): their own attributes only, no style, no handlers
    'cad-cantilever': ['material', 'direction', 'design', 'repeated', 'length', 'thickness', 'width', 'deflection'],
    'cad-fourbar': ['crank', 'coupler', 'rocker', 'ground', 'branch', 'angle', 'theme'],
    'cad-fan-curve': ['fan', 'system', 'count', 'arrangement', 'theme'],
    'cad-torsion-snap': ['material', 'bars', 'repeated', 'length', 'width', 'thickness', 'twist', 'lever', 'theme'],
    'cad-printed-boss': ['material', 'size', 'outside', 'engagement', 'torque', 'axis', 'theme'] },
  allowedClasses: { code: ['language-*'], pre: ['mermaid'], div: ['table-scroll', 'cad-table-scroll'], span: [] },
  allowedSchemes: ['http', 'https', 'mailto'], allowedSchemesByTag: { img: ['http', 'https', 'data'] },
  allowProtocolRelative: false, disallowedTagsMode: 'discard',
  exclusiveFilter: f => f.tag === 'input' && f.attribs.type !== 'checkbox',
};
export const sanitize = html => sanitizeHtml(html, SANITIZE);

const ENTITY = { '&amp;': '&', '&quot;': '"', '&#39;': "'", '&lt;': '<', '&gt;': '>' };
const decode = s => s.replace(/&(?:amp|quot|#39|lt|gt);/g, e => ENTITY[e]);
const encode = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/** Rewrite the href and src of real tags in sanitized HTML: `fn(url, attr)` gets the decoded URL and returns the new
 * one (or null to keep it). Text that only looks like a tag (`<a href=...>` in a code sample, which the sanitizer
 * leaves as `&lt;a href="..."`) is never touched, and each URL is decoded and encoded exactly once. */
export function rewriteUrls(html, fn) {
  return html.replace(/<(a|img)\b[^>]*>/gi, tag => tag.replace(/(\s)(href|src)="([^"]*)"/gi, (all, sp, attr, raw) => {
    const url = fn(decode(raw), attr.toLowerCase());
    return url == null ? all : `${sp}${attr}="${encode(url)}"`;
  }));
}

/** The intrinsic size of a PNG, GIF, JPEG or SVG image ({ width, height } in CSS pixels), or null. The build writes it
 * on every local <img>, so the browser keeps the image's space before it loads and the text never jumps. */
export function imageSize(buf, name = '') {
  const b = Buffer.from(buf);
  if (b.length >= 24 && b.readUInt32BE(0) === 0x89504e47) return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
  if (b.length >= 10 && b.toString('latin1', 0, 3) === 'GIF') return { width: b.readUInt16LE(6), height: b.readUInt16LE(8) };
  if (b.length >= 30 && b.toString('latin1', 0, 4) === 'RIFF' && b.toString('latin1', 8, 12) === 'WEBP') {
    const chunk = b.toString('latin1', 12, 16);                         // lossy, lossless or extended
    if (chunk === 'VP8 ') return { width: b.readUInt16LE(26) & 0x3fff, height: b.readUInt16LE(28) & 0x3fff };
    if (chunk === 'VP8L') { const v = b.readUInt32LE(21); return { width: (v & 0x3fff) + 1, height: ((v >>> 14) & 0x3fff) + 1 }; }
    if (chunk === 'VP8X') return { width: b.readUIntLE(24, 3) + 1, height: b.readUIntLE(27, 3) + 1 };
    return null;
  }
  if (b.length >= 4 && b[0] === 0xff && b[1] === 0xd8) {               // JPEG: walk the segments to the frame header
    for (let i = 2; i + 9 < b.length;) {
      if (b[i] !== 0xff) { i++; continue; }
      const m = b[i + 1];
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) return { width: b.readUInt16BE(i + 7), height: b.readUInt16BE(i + 5) };
      i += 2 + b.readUInt16BE(i + 2);
    }
    return null;
  }
  if (/\.svg$/i.test(name)) {
    const tag = b.toString('utf8').match(/<svg\b[^>]*>/i)?.[0] || '';
    // CSS absolute units in px (KiCad and Inkscape write mm); em as 16 px. A percentage or an unknown unit says nothing
    // about size, so the viewBox decides.
    const PX = { '': 1, px: 1, mm: 96 / 25.4, cm: 96 / 2.54, in: 96, pt: 96 / 72, pc: 16, q: 96 / 101.6, em: 16 };
    const attr = a => {
      const m = tag.match(new RegExp(`\\s${a}\\s*=\\s*(["'])\\s*([\\d.]+)\\s*([a-z]*)\\s*\\1`, 'i'));
      return m && PX[m[3].toLowerCase()] ? parseFloat(m[2]) * PX[m[3].toLowerCase()] : 0;
    };
    const box = tag.match(/\sviewBox\s*=\s*(["'])\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*\1/);
    let w = attr('width'), h = attr('height');
    if (box && !(w && h)) {                                              // keep the viewBox's proportions
      const [bw, bh] = [parseFloat(box[2]), parseFloat(box[3])];
      if (w) h = w * bh / bw; else if (h) w = h * bw / bh; else [w, h] = [bw, bh];
    }
    return w && h ? { width: Math.round(w), height: Math.round(h) } : null;
  }
  return null;
}
