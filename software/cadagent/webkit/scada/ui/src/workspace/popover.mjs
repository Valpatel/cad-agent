/** Nonmodal, screen-space controls. The host owns panel markup and commands. */
const openPopovers = new WeakMap();
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const finite = (value, label) => {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite.`);
  return value;
};
const area = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
  Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));

/** Pure placement calculation in CSS pixels, shared by native and fallback UI. */
export function placeScadaPopover(anchor, panel, viewport, {gap = 12, padding = 12} = {}) {
  const left = finite(viewport.left ?? 0, 'Viewport left'), top = finite(viewport.top ?? 0, 'Viewport top');
  const width = finite(viewport.width, 'Viewport width'), height = finite(viewport.height, 'Viewport height');
  if (width <= 0 || height <= 0 || finite(gap, 'Gap') < 0 || finite(padding, 'Padding') < 0) throw new RangeError('Popover viewport and spacing must be positive.');
  const inset = Math.min(padding, width / 4, height / 4);
  const bounds = {left:left + inset, top:top + inset, right:left + width - inset, bottom:top + height - inset};
  const panelWidth = clamp(finite(panel.width, 'Panel width'), 0, bounds.right - bounds.left);
  const panelHeight = clamp(finite(panel.height, 'Panel height'), 0, bounds.bottom - bounds.top);
  if (panelWidth <= 0 || panelHeight <= 0) throw new RangeError('Popover dimensions must be positive.');
  const target = {left:finite(anchor.left, 'Anchor left'), top:finite(anchor.top, 'Anchor top'),
    right:finite(anchor.right, 'Anchor right'), bottom:finite(anchor.bottom, 'Anchor bottom')};
  const centerX = (target.left + target.right) / 2, centerY = (target.top + target.bottom) / 2;
  const candidates = [
    {placement:'top', left:centerX - panelWidth / 2, top:target.top - gap - panelHeight},
    {placement:'bottom', left:centerX - panelWidth / 2, top:target.bottom + gap},
    {placement:'right', left:target.right + gap, top:centerY - panelHeight / 2},
    {placement:'left', left:target.left - gap - panelWidth, top:centerY - panelHeight / 2},
  ].map(candidate => ({...candidate, right:candidate.left + panelWidth, bottom:candidate.top + panelHeight}));
  // Prefer the first side that fits; otherwise keep the largest visible portion
  // before clamping, rather than jumping to an unrelated corner of the viewport.
  const fits = item => item.left >= bounds.left && item.top >= bounds.top && item.right <= bounds.right && item.bottom <= bounds.bottom;
  const best = candidates.find(fits) ?? candidates.reduce((winner, item) => area(item, bounds) > area(winner, bounds) ? item : winner);
  return {left:clamp(best.left, bounds.left, bounds.right - panelWidth), top:clamp(best.top, bounds.top, bounds.bottom - panelHeight),
    width:panelWidth, height:panelHeight, placement:best.placement};
}

function focus(element) {
  if (!element?.isConnected || typeof element.focus !== 'function' || element.disabled || element.closest('[hidden],[inert]')) return false;
  try { element.focus({preventScroll:true}); } catch { element.focus(); }
  return element.ownerDocument.activeElement === element;
}
function viewport(window) {
  const visual = window.visualViewport;
  return {left:visual?.offsetLeft ?? 0, top:visual?.offsetTop ?? 0,
    width:visual?.width ?? window.innerWidth, height:visual?.height ?? window.innerHeight};
}

export class ScadaPopover {
  #root; #document; #window; #onClose; #panel = null; #anchor = null; #opener = null;
  #native = false; #originalPopover = null; #destroyed = false; #listeners = []; #observer = null;

  constructor(root, {onClose} = {}) {
    if (!root?.ownerDocument || typeof root.addEventListener !== 'function') throw new TypeError('A popover root is required.');
    this.#root = root; this.#document = root.ownerDocument; this.#window = this.#document.defaultView;
    this.#onClose = typeof onClose === 'function' ? onClose : null;
    this.#listen(this.#document, 'click', this.#click);
    // Capture Escape before an enclosing fallback/native dialog can dismiss.
    this.#listen(this.#document, 'keydown', this.#keyDown, true);
    this.#listen(this.#document, 'toggle', this.#toggle, true);
    this.#listen(this.#document, 'scroll', this.#reposition, true);
    this.#listen(this.#window, 'resize', this.#reposition);
    this.#listen(this.#window.visualViewport, 'resize', this.#reposition);
    this.#listen(this.#window.visualViewport, 'scroll', this.#reposition);
  }

  get activePanel() { return this.#panel; }

  open(panel, {anchor, opener, focus:requestedFocus} = {}) {
    if (this.#destroyed || !panel?.isConnected || !this.#root.contains(panel) || !panel.hasAttribute('data-scada-popover')) return false;
    if (panel === this.#panel) {
      if (anchor) this.#anchor = anchor;
      this.reposition();
      if (requestedFocus) this.#focus(requestedFocus);
      return true;
    }
    this.close({restoreFocus:false, reason:'switch'});
    this.#panel = panel; this.#anchor = anchor ?? opener; this.#opener = opener ?? this.#document.activeElement;
    this.#native = typeof panel.showPopover === 'function' && typeof panel.hidePopover === 'function';
    this.#originalPopover = panel.getAttribute('popover');
    panel.hidden = false;
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'false');
    // Some DOM implementations hide [popover] even without the native methods.
    // The fallback must be ordinarily focusable without relying on a CSS override.
    if (this.#native) panel.setAttribute('popover', 'manual'); else panel.removeAttribute('popover');
    panel.dataset.scadaPopoverOpen = 'true';
    try {
      if (this.#native) panel.showPopover();
      const stack = openPopovers.get(this.#document) ?? [];
      stack.push(this); openPopovers.set(this.#document, stack);
      this.reposition();
      const Observer = this.#window.ResizeObserver;
      if (Observer) {
        this.#observer = new Observer(this.#reposition);
        this.#observer.observe(panel);
        const element = this.#anchorElement(); if (element && element !== panel) this.#observer.observe(element);
      }
      this.#focus(requestedFocus);
      return true;
    } catch (error) {
      this.close({restoreFocus:false, reason:'open-failed'});
      throw error;
    }
  }

  close({restoreFocus = true, reason = 'close'} = {}) {
    const panel = this.#panel;
    if (!panel) return false;
    const opener = this.#opener;
    this.#panel = null; this.#anchor = null; this.#opener = null;
    this.#observer?.disconnect(); this.#observer = null;
    const stack = (openPopovers.get(this.#document) ?? []).filter(item => item !== this);
    if (stack.length) openPopovers.set(this.#document, stack); else openPopovers.delete(this.#document);
    if (this.#native) {
      try { panel.hidePopover(); } catch { /* The host may already have detached or hidden it. */ }
    }
    this.#native = false;
    panel.hidden = true; delete panel.dataset.scadaPopoverOpen;
    if (this.#originalPopover === null) panel.removeAttribute('popover');
    else panel.setAttribute('popover', this.#originalPopover);
    this.#originalPopover = null;
    if (restoreFocus) focus(opener);
    this.#onClose?.({panel, reason});
    return true;
  }

  reposition() {
    const panel = this.#panel;
    if (!panel) return false;
    if (!panel.isConnected || !this.#root.contains(panel)) { this.close({restoreFocus:false, reason:'removed'}); return false; }
    const bounds = viewport(this.#window), inset = Math.min(12, bounds.width / 4, bounds.height / 4);
    panel.style.position = 'fixed'; panel.style.margin = '0';
    // Leave the computed left and top in place while measuring an open panel.
    panel.style.right = 'auto'; panel.style.bottom = 'auto';
    panel.style.maxWidth = `${Math.max(1, bounds.width - 2 * inset)}px`;
    panel.style.maxHeight = `${Math.max(1, Math.min(440, bounds.height - 2 * inset))}px`;
    const measured = panel.getBoundingClientRect();
    // A hidden test DOM has no layout; the fallback defaults match the CSS.
    const size = {width:measured.width || Math.min(360, bounds.width - 2 * inset), height:measured.height || Math.min(440, bounds.height - 2 * inset)};
    const element = this.#anchorElement(), anchor = element?.getBoundingClientRect() ?? {
      left:bounds.left + bounds.width / 2, right:bounds.left + bounds.width / 2,
      top:bounds.top + bounds.height / 2, bottom:bounds.top + bounds.height / 2,
    };
    const next = placeScadaPopover(anchor, size, bounds);
    panel.style.left = `${next.left}px`; panel.style.top = `${next.top}px`;
    return true;
  }

  destroy() {
    if (this.#destroyed) return;
    this.close({restoreFocus:false, reason:'destroy'});
    for (const [target, type, listener, capture] of this.#listeners) target.removeEventListener(type, listener, capture);
    this.#listeners = []; this.#destroyed = true;
  }

  #listen(target, type, listener, capture = false) {
    if (!target) return;
    target.addEventListener(type, listener, capture); this.#listeners.push([target, type, listener, capture]);
  }
  #anchorElement() {
    const anchor = typeof this.#anchor === 'function' ? this.#anchor() : this.#anchor;
    return anchor?.isConnected ? anchor : this.#opener?.isConnected ? this.#opener : null;
  }
  #focus(requested) {
    const target = typeof requested === 'string' ? this.#panel.querySelector(requested) : requested;
    if (target && this.#panel.contains(target) && focus(target)) return;
    if (!focus(this.#panel.querySelector('[data-scada-popover-close]'))) focus(this.#panel);
  }
  #topmost() { return openPopovers.get(this.#document)?.at(-1) === this; }
  #reposition = () => { this.reposition(); };
  #click = event => {
    if (!this.#panel || event.defaultPrevented || !this.#topmost()) return;
    const target = event.target;
    if (this.#panel.contains(target)) {
      if (target.closest?.('[data-scada-popover-close]')) { event.preventDefault(); this.close(); }
    } else if (!this.#anchorElement()?.contains(target) && !this.#opener?.contains(target)) {
      this.close({restoreFocus:false, reason:'outside'});
    }
  };
  #keyDown = event => {
    if (!this.#panel || event.key !== 'Escape' || event.defaultPrevented || !this.#topmost()) return;
    const focusedDialog = this.#document.activeElement?.closest('dialog[open]');
    if (focusedDialog && !focusedDialog.contains(this.#panel)) return;
    event.preventDefault(); event.stopPropagation(); this.close({reason:'escape'});
  };
  #toggle = event => {
    if (!this.#panel || event.target !== this.#panel || event.newState !== 'closed') return;
    // Native toggle events are queued; reopening the same panel supersedes its old close.
    if (this.#native && this.#panel.matches(':popover-open')) return;
    this.close({reason:'native'});
  };
}
