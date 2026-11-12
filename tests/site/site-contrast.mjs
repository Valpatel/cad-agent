/** Existing whole-page WCAG predicate, shared by general themes and targeted outline states. */
export const lowContrast = (page, only = null) => page.evaluate(only => {
    const ctx = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d', { willReadFrequently: true });
    // Each colour is read back from the canvas once, and each element's backdrop worked out once: a page asks for the
    // same few colours thousands of times, and a canvas read is slow (in WebKit most of all).
    const seen = new Map(), backdrops = new Map();
    const rgba = c => { if (seen.has(c)) return seen.get(c); ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; seen.set(c, [d[0], d[1], d[2], d[3] / 255]); return seen.get(c); };
    const lum = ([r, g, b]) => [r, g, b].map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };
    // What can be behind: a colour, or each stop of a CSS gradient (text must read on all of them); null for a picture.
    const over = ([r, g, b, a], under) => [r, g, b].map((v, i) => v * a + under[i] * (1 - a));
    const behind = el => { if (!backdrops.has(el)) backdrops.set(el, backdrop(el)); return backdrops.get(el); };
    const backdrop = el => {
      const layers = [];
      for (let e = el; e; e = e.parentElement) {
        const cs = getComputedStyle(e), c = rgba(cs.backgroundColor);
        if (/url\(/.test(cs.backgroundImage)) return null;
        // a gradient sized to nothing (the catalogue rows' hover sweep, until hovered) is not behind anything yet
        const stops = cs.backgroundImage === 'none' || /^0(?:%|px)/.test(cs.backgroundSize) ? []
          : (cs.backgroundImage.match(/(?:rgba?|oklab|oklch|lab|lch|color)\((?:[^()]|\([^()]*\))*\)/g) || []).map(rgba);
        if (stops.length) layers.push(stops);
        if (c[3] > 0) layers.push([c]);
        if (c[3] >= 1 || (stops.length && stops.every(x => x[3] >= 1))) break;
      }
      let under = [[255, 255, 255]];
      for (const layer of layers.reverse()) under = layer.flatMap(c => under.map(u => over(c, u)));
      return under;
    };
    const SKIP = 'svg, img, video, canvas, cad-model, cad-cantilever, cad-fourbar, cad-fan-curve, cad-torsion-snap, cad-printed-boss, .cad-diagram-view, .visually-hidden, .sr, .glyph-sprite, [hidden]';
    const low = [], walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const name = el => `${el.localName}${el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''}`;
    for (const input of only ? [] : document.querySelectorAll('input[placeholder]')) {
      if (!input.getClientRects().length || input.closest(SKIP)) continue;
      const bgs = behind(input), fg = rgba(getComputedStyle(input, '::placeholder').color);
      const c = bgs && Math.min(...bgs.map(bg => ratio(over(fg, bg), bg)));
      if (c && c < 4.5) low.push(`${name(input)} placeholder "${input.placeholder.slice(0, 30)}" ${c.toFixed(2)}:1`);
    }
    for (let n; (n = walk.nextNode());) {
      const el = n.parentElement;
      if (!n.data.trim() || el.closest(SKIP) || (only && !el.closest(only))) continue;
      const cs = getComputedStyle(el), r = el.getBoundingClientRect();
      if (!r.width || !r.height || cs.visibility === 'hidden' || +cs.opacity === 0 || !el.checkVisibility?.({ opacityProperty: true, visibilityProperty: true })) continue;
      const bgs = behind(el);
      if (!bgs) continue;
      const fg = rgba(cs.color), c = Math.min(...bgs.map(bg => ratio(over(fg, bg), bg)));
      const size = parseFloat(cs.fontSize), large = size >= 24 || (size >= 18.66 && +cs.fontWeight >= 700), need = large ? 3 : 4.5;
      if (c < need) low.push(`${name(el)} "${n.data.trim().slice(0, 30)}" ${c.toFixed(2)}:1`);
    }
    return [...new Set(low)];
  }, only);
