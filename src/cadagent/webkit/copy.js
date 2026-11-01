/** <cad-copy>: a one-click copy button for anything people need to paste (commands, config, prompts, part numbers).
 *
 *   <script type="module" src="/kit/copy.js"></script>
 *   <cad-copy><pre><code>pip install cad-agent</code></pre></cad-copy>
 *   <cad-copy text="the exact text to copy" label="Copy prompt"><p>What the reader sees</p></cad-copy>
 *
 * The button copies the block's text exactly (the `text` attribute if set, else the text of its <pre>, else of the
 * element), says "Copied" for a moment and announces it to screen readers. It uses the Clipboard API (HTTPS or
 * localhost) and falls back to selecting the text with a "press Ctrl+C" hint (on touch screens: "Text selected").
 * No dependencies and no shadow DOM: the kit's rules sit in :where(), so any page rule (the --cad-copy-* custom
 * properties, or plain CSS on `cad-copy > .cad-copy-btn`) wins over them. Long lines that scroll sideways get a strip
 * above the code for the button, so it never covers text; on touch screens the button is 44 px tall.
 *
 * enhance(root, selector) wraps every matching <pre> that is not already inside a <cad-copy> (default: all <pre>
 * except Mermaid sources), for pages whose HTML you do not generate yourself.
 */
const CSS = `:where(cad-copy){display:block;position:relative}
cad-copy>pre{padding-right:5.5em}
cad-copy[data-wide]>pre{padding-top:3.2em}
:where(cad-copy>.cad-copy-btn){position:absolute;top:.55em;right:.55em;display:inline-flex;align-items:center;gap:.35em;
  min-height:2.2em;padding:.3em .8em;border-radius:999px;cursor:pointer;
  font:600 12px/1 var(--cad-copy-font,system-ui,sans-serif);color:var(--cad-copy-fg,#173d3c);
  background:var(--cad-copy-bg,#fffdf5);border:1px solid var(--cad-copy-border,#6f8a80);
  box-shadow:0 1px 0 #173d3c14;transition:background .15s,color .15s,border-color .15s}
:where(cad-copy>.cad-copy-btn:hover){border-color:var(--cad-copy-fg,#173d3c)}
:where(cad-copy>.cad-copy-btn:focus-visible){outline:2px solid var(--cad-copy-focus,#bd3a12);outline-offset:2px}
:where(cad-copy>.cad-copy-btn[data-state=copied]){background:var(--cad-copy-ok-bg,#2e9d5b);border-color:var(--cad-copy-ok-bg,#2e9d5b);color:#fff}
:where(cad-copy>.cad-copy-btn[data-state=manual]){background:var(--cad-copy-warn-bg,#ffe1cc)}
:where(cad-copy>.cad-copy-btn svg){width:1.1em;height:1.1em;flex:none}
cad-copy>.cad-copy-status{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media(max-width:600px){cad-copy>pre{padding-top:3.6em;padding-right:1em}}
@media(pointer:coarse){:where(cad-copy>.cad-copy-btn){min-height:44px;min-width:44px;padding:.3em 1em}cad-copy[data-wide]>pre{padding-top:4em}}
@media(prefers-reduced-motion:reduce){:where(cad-copy>.cad-copy-btn){transition:none}}`;

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
        const touch = matchMedia('(pointer: coarse)').matches;
        show('manual', touch ? 'Text selected' : /Mac/.test(navigator.platform) ? 'Press ⌘C' : 'Press Ctrl+C');
        status.textContent = 'Could not copy automatically; the text is selected';
      }
      this.dispatchEvent(new CustomEvent('cad-copy', { bubbles: true, detail: { text, ok } }));
      timer = setTimeout(() => { show('idle', label); status.textContent = ''; }, 1800);
    });
    this.append(button, status);
    // Code that scrolls sideways gets a strip above it for the button, so long lines never pass under it.
    const pre = this.querySelector(':scope > pre');
    if (pre && typeof ResizeObserver !== 'undefined') {
      const fit = () => this.toggleAttribute('data-wide', pre.scrollWidth > pre.clientWidth + 1);
      new ResizeObserver(fit).observe(pre);
      fit();
    }
  }
}

/** Wrap every matching <pre> under root in a <cad-copy>, unless it is already inside one. */
export function enhance(root = document, selector = 'pre:not(.mermaid):not(:has(> code.language-mermaid))') {
  for (const pre of root.querySelectorAll(selector)) {
    if (pre.closest('cad-copy')) continue;
    const wrap = document.createElement('cad-copy');
    pre.replaceWith(wrap);
    wrap.append(pre);
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('cad-copy')) customElements.define('cad-copy', CadCopy);
