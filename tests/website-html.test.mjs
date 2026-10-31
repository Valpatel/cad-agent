// The site's HTML sanitizer (tools/site-html.mjs): rendered Markdown may quote outside sources, so no script, handler
// or unsafe URL survives, while the markup our docs use (and text inside code) comes through unchanged.
import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitize, safeUrl, rewriteUrls, imageSize } from '../tools/site-html.mjs';

const ATTACKS = {
  'nested script': '<scr<script>x</script>ipt>window.__x=1</script>',
  'plain script': '<script>alert(1)</script>',
  'img onerror': '<img src=x onerror=alert(1)>',
  'handler without space': '<a href="/x"/onclick="alert(1)">x</a>',
  'unquoted javascript href': '<a href=javascript:alert(1)>x</a>',
  'mixed-case scheme': '<a href="JaVaScRiPt:alert(1)">x</a>',
  'entity-encoded scheme': '<a href="&#106;avascript:alert(1)">x</a>',
  'data html link': '<a href="data:text/html,<script>alert(1)</script>">x</a>',
  'svg animate': '<svg><animate attributeName="href" values="javascript:alert(1)"/><a><text>x</text></a></svg>',
  'meta refresh': '<meta http-equiv="refresh" content="0;url=https://example.com">',
  'iframe': '<iframe src="https://example.com"></iframe>',
  'form action': '<form action="https://example.com"><button>go</button></form>',
  'style tag': '<style>body{display:none}</style>',
  'object': '<object data="x.swf"></object>',
  'base tag': '<base href="https://example.com/">',
  'protocol-relative image': '<img src="//example.com/x.png">',
};

for (const [name, html] of Object.entries(ATTACKS)) {
  test(`sanitizer removes: ${name}`, () => {
    const out = sanitize(html);
    assert.doesNotMatch(out, /<script|<iframe|<object|<embed|<meta|<style|<form|<base|<svg|<animate/i, out);
    assert.doesNotMatch(out, /\son[a-z]+\s*=/i, out);
    assert.doesNotMatch(out, /(?:href|src|action|values)\s*=\s*["']?\s*(?:javascript|vbscript|data:text)/i, out);
    assert.doesNotMatch(out, /src="\/\//, out);
  });
}

test('text that looks like attributes is kept inside code', () => {
  const code = '<pre><code class="language-python">assembly.step(order, fit, *, onto=None, only=None)\nx.on(onto="a")\n</code></pre>';
  assert.equal(sanitize(code), code);
  assert.equal(sanitize('<p>Use <code>onload=</code> carefully</p>'), '<p>Use <code>onload=</code> carefully</p>');
});

test('the markup our docs use survives', () => {
  for (const html of [
    '<h2 id="what-it-does">What it does</h2>',
    '<p align="center"><img src="/docs/img/gyropup.jpg" alt="Gyropup" width="640"></p>',
    '<pre><code class="language-mermaid">flowchart LR\n  A --&gt; B\n</code></pre>',
    '<div class="table-scroll"><table><thead><tr><th align="left">a</th></tr></thead><tbody><tr><td>b</td></tr></tbody></table></div>',
    '<details><summary>More</summary><p>x</p></details>',
    '<ul><li><input type="checkbox" checked disabled /> done</li></ul>',
    '<a href="https://github.com/Valpatel/cad-agent" title="repo">repo</a>',
    '<a href="mailto:hello@example.com">mail</a>',
    '<a href="../docs/toolkit.md#commands">toolkit</a>',
    '<img src="data:image/png;base64,iVBORw0KGgo=" alt="dot">',
  ]) {
    const out = sanitize(html);
    for (const piece of html.match(/<[a-z][a-z0-9]*[^>]*>/g)) {
      const tag = piece.match(/<([a-z][a-z0-9]*)/)[1];
      assert.match(out, new RegExp(`<${tag}\\b`), `${tag} dropped from ${html} → ${out}`);
    }
    for (const attr of html.matchAll(/\s(href|src|class|id|align|alt|title|type|width)="([^"]*)"/g))
      assert.ok(out.includes(`${attr[1]}="${attr[2].replace(/&gt;/g, '>')}"`) || out.includes(`${attr[1]}="${attr[2]}"`), `${attr[0]} dropped → ${out}`);
  }
  assert.doesNotMatch(sanitize('<input type="text" value="x">'), /<input/, 'only task-list checkboxes are inputs');
});

test('safeUrl keeps web, mail, data-image and relative URLs only', () => {
  for (const ok of ['https://x.org/a', 'http://x.org', 'mailto:a@b.c', 'data:image/png;base64,AAA', '/docs/toolkit', 'docs/a.md#b', '#top', '?q=1'])
    assert.equal(safeUrl(ok), ok);
  for (const bad of ['javascript:alert(1)', ' JavaScript:alert(1)', 'vbscript:x', 'data:text/html,x', 'file:///etc/passwd'])
    assert.equal(safeUrl(bad), '#', bad);
});

test('link rewriting touches real tags only, and decodes and encodes each URL once', () => {
  // Review of #108: a snippet showing <a href="kit/file-viewer.html?file=...&back=..."> was rewritten into a GitHub URL.
  const html = sanitize('<p><a href="docs/a.md?x=1&amp;y=2">real</a></p>'
    + '<pre><code>&lt;a href="kit/file-viewer.html?file=a.step&amp;back=index.html"&gt;open&lt;/a&gt;</code></pre>');
  const seen = [];
  const out = rewriteUrls(html, url => { seen.push(url); return `/x/${url}`; });
  assert.deepEqual(seen, ['docs/a.md?x=1&y=2'], 'only the real link is offered, decoded');
  assert.match(out, /<a href="\/x\/docs\/a\.md\?x=1&amp;y=2">/);
  assert.ok(out.includes('href="kit/file-viewer.html?file=a.step&amp;back=index.html"'), out);
  assert.ok(!out.includes('&amp;amp;'));
  assert.equal(rewriteUrls(html, () => null), html, 'returning null keeps the tag as it was');
});

test('image sizes come from the file, so pages keep the space before images load', () => {
  const png = Buffer.alloc(24); png.writeUInt32BE(0x89504e47, 0); png.write('IHDR', 12, 'latin1'); png.writeUInt32BE(640, 16); png.writeUInt32BE(360, 20);
  assert.deepEqual(imageSize(png, 'a.png'), { width: 640, height: 360 });
  const gif = Buffer.from('GIF89a\x20\x00\x10\x00', 'latin1');
  assert.deepEqual(imageSize(gif, 'a.gif'), { width: 32, height: 16 });
  // JPEG: SOI, an APP0 segment to skip, then the SOF0 frame header (precision, height 200, width 300)
  const jpg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x04, 0x00, 0x00, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x00, 0xc8, 0x01, 0x2c, 0x03]);
  assert.deepEqual(imageSize(jpg, 'a.jpg'), { width: 300, height: 200 });
  assert.deepEqual(imageSize(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 716">'), 'a.svg'), { width: 680, height: 716 });
  assert.deepEqual(imageSize(Buffer.from('<svg width="200px" viewBox="0 0 400 100">'), 'a.svg'), { width: 200, height: 50 });
  assert.equal(imageSize(Buffer.from('<svg viewBox="nonsense">'), 'a.svg'), null);
  assert.equal(imageSize(Buffer.from('not an image'), 'a.webp'), null);
});
