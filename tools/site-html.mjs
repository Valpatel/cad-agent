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
    'details', 'summary', 'div', 'span', 'input'],
  allowedAttributes: { a: ['href', 'title', 'id', 'name'], img: ['src', 'alt', 'title', 'width', 'height'],
    '*': ['id', 'align'], code: ['class'], pre: ['class'], div: ['class'], span: ['class'], td: ['align', 'width'],
    th: ['align', 'width'], input: ['type', 'checked', 'disabled'], ol: ['start'] },
  allowedClasses: { code: ['language-*'], pre: ['mermaid'], div: false, span: false },
  allowedSchemes: ['http', 'https', 'mailto'], allowedSchemesByTag: { img: ['http', 'https', 'data'] },
  allowProtocolRelative: false, disallowedTagsMode: 'discard',
  exclusiveFilter: f => f.tag === 'input' && f.attribs.type !== 'checkbox',
};
export const sanitize = html => sanitizeHtml(html, SANITIZE);
