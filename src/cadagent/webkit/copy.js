/** <cad-copy>: a one-click copy button for anything people need to paste (commands, config, prompts, part numbers).
 *
 *   <script type="module" src="/kit/copy.js"></script>
 *   <cad-copy><pre><code>pip install cad-agent</code></pre></cad-copy>
 *   <cad-copy text="the exact text to copy" label="Copy prompt"><p>What the reader sees</p></cad-copy>
 *
 * The button copies the block's text exactly (the `text` attribute if set, else the text of its <pre>, else of the
 * element), says "Copied" for a moment and announces it to screen readers. It uses the Clipboard API (HTTPS or
 * localhost) and falls back to selecting the text with a "press Ctrl+C" hint (on touch screens: "Text selected").
 * No dependencies and no shadow DOM. The kit's button rules have the specificity of one class (`:where(cad-copy) >
 * .cad-copy-btn`): a page's own rule on `cad-copy > .cad-copy-btn` (or the --cad-copy-* custom properties) wins, and
 * a plain `button {}` reset such as Tailwind's preflight does not. Focus rings stay at zero specificity, so a page's
 * own focus style wins. The button never covers text: the code keeps room on the right as wide as the button's widest
 * label (measured, and re-measured when fonts load or the button's own size changes), and code that scrolls sideways,
 * or any code on a narrow screen, gets a strip above it as tall as the button. One limit: the strip is the <pre>'s
 * own top padding, so code that also scrolls vertically (a max-height on <pre>) can scroll under the button.
 * On touch screens the button is 44 px tall.
 *
 * enhance(root, selector) wraps every matching <pre> that is not already inside a <cad-copy> (default: all <pre>
 * except Mermaid sources), for pages whose HTML you do not generate yourself.
 */
const CSS = `:where(cad-copy){display:block;position:relative}
cad-copy>pre{padding-right:var(--cad-copy-room-x,5.5em)}
cad-copy[data-wide]>pre{padding-top:var(--cad-copy-room-y,3.2em)}
:where(cad-copy)>.cad-copy-btn{position:absolute;box-sizing:border-box;top:.55em;right:.55em;display:inline-flex;align-items:center;justify-content:center;gap:.35em;
  min-height:2.2em;padding:.3em .8em;border-radius:999px;cursor:pointer;
  font:600 12px/1 var(--cad-copy-font,system-ui,sans-serif);color:var(--cad-copy-fg,#173d3c);
  background:var(--cad-copy-bg,#fffdf5);border:1px solid var(--cad-copy-border,#6f8a80);
  box-shadow:0 1px 0 #173d3c14;transition:background .15s,color .15s,border-color .15s}
:where(cad-copy)>.cad-copy-btn:hover{border-color:var(--cad-copy-fg,#173d3c)}
:where(cad-copy>.cad-copy-btn:focus-visible){outline:2px solid var(--cad-copy-focus,#bd3a12);outline-offset:2px}
:where(cad-copy)>.cad-copy-btn[data-state=copied]{background:var(--cad-copy-ok-bg,#2e9d5b);border-color:var(--cad-copy-ok-bg,#2e9d5b);color:#fff}
:where(cad-copy)>.cad-copy-btn[data-state=manual]{background:var(--cad-copy-warn-bg,#ffe1cc)}
:where(cad-copy)>.cad-copy-btn svg{width:1.1em;height:1.1em;flex:none}
cad-copy>.cad-copy-status{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(max-width:600px){cad-copy>pre{padding-top:var(--cad-copy-room-y,3.6em);padding-right:1em}}
@media(pointer:coarse){:where(cad-copy)>.cad-copy-btn{min-height:44px;min-width:44px;padding:.3em 1em}}
@media(prefers-reduced-motion:reduce){:where(cad-copy)>.cad-copy-btn{transition:none}}`;

const ICON = {
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>',
  done: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
};

let styled = false;
function addStyles() {
  if (styled || typeof document === 'undefined') return;
  styled = true;
  try {                                   // a constructable sheet needs no inline <style>, so strict CSPs allow it
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(CSS);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  } catch {
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.append(style);
  }
}

/** The text a <cad-copy> copies: its `text` attribute, else its <pre>'s text, else its own (minus the button). */
export function copyText(el) {
  if (el.hasAttribute('text')) return el.getAttribute('text');
  const source = el.querySelector(':scope > pre') || el;
  const clone = source.cloneNode(true);
  clone.querySelectorAll('.cad-copy-btn, .cad-copy-status').forEach(n => n.remove());
  return clone.textContent.replace(/\n$/, '');
}

async function writeClipboard(text) {
  if (navigator.clipboard?.writeText && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  const back = document.activeElement;                       // older browsers and plain-http pages
  const area = document.createElement('textarea');
  area.value = text; area.setAttribute('readonly', ''); area.style.cssText = 'position:fixed;top:-1000px;opacity:0';
  document.body.append(area); area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  area.remove();
  back?.focus?.({ preventScroll: true });                    // keyboard users stay on the button they pressed
  return ok;
}

export class CadCopy extends HTMLElement {
  connectedCallback() {
    if (this.querySelector(':scope > .cad-copy-btn')) return;
    addStyles();
    const label = this.getAttribute('label') || 'Copy';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cad-copy-btn';
    button.setAttribute('aria-label', this.getAttribute('aria-label') || `${label} to clipboard`);
    const status = document.createElement('span');
    status.className = 'cad-copy-status';
    status.setAttribute('role', 'status');
    const show = (state, text) => {                // the label is page text, never HTML
      button.dataset.state = state;
      const span = document.createElement('span');
      span.textContent = text;
      button.innerHTML = state === 'copied' ? ICON.done : ICON.copy;
      button.append(span);
    };
    show('idle', label);
    const touch = () => matchMedia('(pointer: coarse)').matches;
    const manual = () => touch() ? 'Text selected' : /Mac/.test(navigator.platform) ? 'Press ⌘C' : 'Press Ctrl+C';
    let timer;
    button.addEventListener('click', async () => {
      const text = copyText(this);
      let ok = false;
      try { ok = await writeClipboard(text); } catch { ok = false; }
      clearTimeout(timer);
      if (ok) {
        show('copied', 'Copied');
        status.textContent = 'Copied to clipboard';
      } else {                              // leave the text selected so one key press finishes the job
        const range = document.createRange();
        range.selectNodeContents(this.querySelector(':scope > pre') || this);
        getSelection().removeAllRanges(); getSelection().addRange(range);
        show('manual', manual());
        status.textContent = 'Could not copy automatically; the text is selected';
      }
      this.dispatchEvent(new CustomEvent('cad-copy', { bubbles: true, detail: { text, ok } }));
      timer = setTimeout(() => { show('idle', label); status.textContent = ''; }, 1800);
    });
    this.append(button, status);
    const pre = this.querySelector(':scope > pre');
    if (!pre || typeof ResizeObserver === 'undefined') return;
    // Room for the button, from its real size: on the right, as wide as its widest label (so "Copied" or "Press
    // Ctrl+C" never grows over a line), and above (the strip) as tall as it is. Code that scrolls sideways, and any
    // code on a narrow screen, gets the strip, so long lines never pass under the button.
    let widest = 0;
    const measure = () => {
      if (!this.isConnected) return;
      const state = button.dataset.state, now = button.querySelector('span')?.textContent ?? label;
      button.style.minWidth = '';
      widest = 0;
      for (const [s, text] of [['idle', label], ['copied', 'Copied'], ['manual', manual()]]) {
        show(s, text);
        widest = Math.max(widest, button.offsetWidth);
      }
      show(state, now);
      button.style.minWidth = `${widest}px`;
      fit(true);
    };
    // fresh: just measured, so never measure again from here. Without it, a button wider than measure() can explain
    // (a page rule measure() does not reproduce) would make measure() and fit() call each other for ever.
    const fit = (fresh = false) => {
      if (!this.isConnected) return;
      if (!fresh && !widest && button.offsetWidth) return measure();     // first measured while hidden (a closed <details>)
      if (!fresh && button.offsetWidth > widest + 0.5) return measure(); // page CSS grew the button since it was measured
      const p = pre.getBoundingClientRect(), b = button.getBoundingClientRect(), cs = getComputedStyle(pre);
      const x = `${Math.ceil(p.right - parseFloat(cs.borderRightWidth) - (b.right - widest) + 8)}px`;
      const y = `${Math.ceil(b.bottom - p.top - parseFloat(cs.borderTopWidth) + 6)}px`;
      if (this.style.getPropertyValue('--cad-copy-room-x') !== x) this.style.setProperty('--cad-copy-room-x', x);
      if (this.style.getPropertyValue('--cad-copy-room-y') !== y) this.style.setProperty('--cad-copy-room-y', y);
      // Only the strip depends on overflow; the right-hand room never does, so this settles in one pass.
      this.toggleAttribute('data-wide', pre.scrollWidth > pre.clientWidth + 1);
    };
    const watch = new ResizeObserver(() => fit());           // not fit(entries): that would read as fresh
    watch.observe(pre);
    watch.observe(button);                                     // a stylesheet that arrives later can resize it
    measure();
    document.fonts?.ready.then(measure);
    matchMedia('(pointer: coarse)').addEventListener?.('change', measure);
  }
}

/** Wrap every matching <pre> under root in a <cad-copy>, unless it is already inside one. */
export function enhance(root = document, selector = 'pre:not(.mermaid):not(:has(> code.language-mermaid))') {
  for (const pre of root.querySelectorAll(selector)) {
    if (pre.closest('cad-copy')) continue;
    const wrap = document.createElement('cad-copy');
    const parent = pre.parentNode, next = pre.nextSibling;
    wrap.append(pre);                                          // fill it first: it sets itself up when it connects
    parent.insertBefore(wrap, next);
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-copy')) customElements.define('cad-copy', CadCopy);
