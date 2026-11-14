/**
 * Reusable SCADA workspace primitives. The host supplies equipment/model markup;
 * this module owns only tool dialogs, focus and modal lifecycle.
 *
 * renderScadaDialog({ id:'equipment', title:'Feed pump', body:trustedMarkup })
 * const workspace = new ScadaWorkspace(root);
 * workspace.open('equipment', { opener: equipmentButton });
 * workspace.destroy(); // Call before replacing/removing the workspace root.
 *
 * body, footer and toolbar content are trusted application HTML, not user text.
 * Other strings are escaped. Use a distinct scope for simultaneous workspaces.
 */
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));
const token = (value, name) => {
  const result = String(value ?? '');
  if (!/^[A-Za-z][A-Za-z0-9_.:-]*$/.test(result)) throw new TypeError(`Invalid SCADA ${name}.`);
  return result;
};

export function renderScadaDialog({ id, title, subtitle = '', body = '', kind = 'panel', footer = '', scope = 'scada' }) {
  const key = token(id, 'dialog ID'), prefix = token(scope, 'scope');
  const dialogId = `${prefix}-${key}-dialog`, titleId = `${dialogId}-title`, descriptionId = `${dialogId}-description`;
  const size = ['panel', 'equipment', 'wide'].includes(kind) ? kind : 'panel';
  return `<dialog id="${dialogId}" class="scada-dialog scada-dialog-${size}" data-scada-dialog="${key}" aria-labelledby="${titleId}"${subtitle ? ` aria-describedby="${descriptionId}"` : ''} tabindex="-1">
    <header class="scada-dialog-header">
      <div class="scada-dialog-heading"><h2 id="${titleId}" data-scada-dialog-title>${escapeHtml(title)}</h2>${subtitle ? `<p id="${descriptionId}" data-scada-dialog-subtitle>${escapeHtml(subtitle)}</p>` : ''}</div>
      <button type="button" class="scada-dialog-close" data-scada-close aria-label="Close ${escapeHtml(title || 'panel')}"><span aria-hidden="true">×</span><span class="scada-sr-only">Close panel</span></button>
    </header>
    <div class="scada-dialog-body" data-scada-dialog-body>${body}</div>
    ${footer ? `<footer class="scada-dialog-footer">${footer}</footer>` : ''}
  </dialog>`;
}

export function renderScadaToolbar({ label = 'SCADA workspace tools', content = '' } = {}) {
  return `<div class="scada-toolbar" role="group" aria-label="${escapeHtml(label)}">${content}</div>`;
}

const focusSelector = 'button,input,select,textarea,a[href],summary,[tabindex],[contenteditable="true"]';
const scrollLocks = new WeakMap();

function lockDocument(document, owner) {
  let lock = scrollLocks.get(document);
  if (!lock) {
    lock = { owners: [], overflow: document.documentElement.style.overflow };
    scrollLocks.set(document, lock);
  }
  lock.owners.push(owner);
  document.documentElement.style.overflow = 'hidden';
  return lock.owners.length;
}
function unlockDocument(document, owner) {
  const lock = scrollLocks.get(document);
  if (!lock) return;
  lock.owners = lock.owners.filter(item => item !== owner);
  if (lock.owners.length) return;
  document.documentElement.style.overflow = lock.overflow;
  scrollLocks.delete(document);
}
function available(element, dialog) {
  if (!element || typeof element.focus !== 'function' || !element.isConnected) return false;
  if (element.disabled || element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true' || element.type === 'hidden') return false;
  if (element.closest('[hidden],[inert]')) return false;
  const closedDialog = element.closest('dialog:not([open])');
  if (closedDialog && closedDialog !== dialog) return false;
  for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
    const style = element.ownerDocument.defaultView?.getComputedStyle(ancestor);
    if (style?.display === 'none' || style?.visibility === 'hidden') return false;
    if (ancestor.tagName === 'DETAILS' && !ancestor.open) {
      const summary = [...ancestor.children].find(child => child.tagName === 'SUMMARY');
      if (!summary?.contains(element)) return false;
    }
  }
  // JSDOM has no layout. Real browsers also exclude clipped/collapsed controls.
  return !element.ownerDocument.documentElement.getClientRects().length || element.getClientRects().length > 0;
}
function focusElement(element) {
  if (!element) return;
  try { element.focus({ preventScroll: true }); } catch { element.focus(); }
}

export class ScadaWorkspace {
  #root;
  #document;
  #current = null;
  #opener = null;
  #onOpen;
  #onClose;
  #destroyed = false;
  #native = false;
  #listeners = [];
  #outsidePointer = false;
  #fallbackBackdrop = null;
  #fallbackZIndex = '';

  constructor(root, { onOpen, onClose } = {}) {
    if (!root?.querySelectorAll || !root?.addEventListener) throw new TypeError('A SCADA workspace root is required.');
    this.#root = root;
    this.#document = root.ownerDocument;
    this.#onOpen = typeof onOpen === 'function' ? onOpen : null;
    this.#onClose = typeof onClose === 'function' ? onClose : null;
    this.#listen(root, 'click', this.#click);
    this.#listen(root, 'pointerdown', this.#pointerDown);
    this.#listen(root, 'keydown', this.#keyDown);
    // close/cancel do not bubble; capture also supports dialogs added later.
    this.#listen(root, 'cancel', this.#cancel, true);
    this.#listen(root, 'close', this.#nativeClose, true);
    this.#listen(this.#document, 'focusin', this.#containFallbackFocus, true);
    this.#syncTriggers();
  }

  get activeId() { return this.#current?.dataset.scadaDialog ?? null; }
  get activeDialog() { return this.#current; }

  open(id, { opener, focus } = {}) {
    if (this.#destroyed) return false;
    const dialog = [...this.#root.querySelectorAll('dialog[data-scada-dialog]')]
      .find(element => element.dataset.scadaDialog === String(id));
    if (!dialog || !dialog.isConnected) return false;
    if (dialog === this.#current && dialog.open) {
      if (focus) this.#focusDialog(dialog, focus);
      return true;
    }
    let returnTo = opener ?? this.#document.activeElement;
    if (this.#current?.contains(returnTo)) returnTo = this.#opener;
    this.close({ restoreFocus: false, reason: 'switch' });
    this.#opener = returnTo && this.#root.contains(returnTo) ? returnTo : null;
    this.#native = typeof dialog.showModal === 'function';
    try {
      if (this.#native) {
        // An externally opened non-modal dialog must first leave that state.
        if (dialog.open && typeof dialog.close === 'function') dialog.close();
        dialog.showModal();
      } else {
        dialog.setAttribute('open', '');
        dialog.setAttribute('role', 'dialog');
        dialog.dataset.scadaFallback = 'true';
      }
    } catch {
      this.#opener = null;
      this.#native = false;
      return false;
    }
    this.#current = dialog;
    this.#outsidePointer = false;
    dialog.setAttribute('aria-modal', 'true');
    const depth = lockDocument(this.#document, this);
    if (!this.#native) {
      this.#fallbackBackdrop = this.#document.createElement('div');
      this.#fallbackBackdrop.className = 'scada-fallback-backdrop';
      this.#fallbackBackdrop.setAttribute('aria-hidden', 'true');
      this.#fallbackBackdrop.style.zIndex = String(999 + depth * 2);
      this.#root.append(this.#fallbackBackdrop);
      this.#fallbackZIndex = dialog.style.zIndex;
      dialog.style.zIndex = String(1000 + depth * 2);
    }
    this.#syncTriggers();
    this.#focusDialog(dialog, focus);
    this.#onOpen?.({ id: String(id), dialog });
    return true;
  }

  close({ restoreFocus = true, reason = 'close' } = {}) {
    const dialog = this.#current;
    if (!dialog) return false;
    const opener = this.#opener;
    this.#current = null;
    this.#opener = null;
    this.#outsidePointer = false;
    dialog.removeAttribute('aria-modal');
    if (this.#native && typeof dialog.close === 'function' && dialog.open) dialog.close();
    else dialog.removeAttribute('open');
    delete dialog.dataset.scadaFallback;
    if (this.#fallbackBackdrop) {
      this.#fallbackBackdrop.remove();
      this.#fallbackBackdrop = null;
      dialog.style.zIndex = this.#fallbackZIndex;
    }
    this.#native = false;
    unlockDocument(this.#document, this);
    this.#syncTriggers();
    if (restoreFocus) this.#restoreFocus(opener);
    this.#onClose?.({ id: dialog.dataset.scadaDialog, dialog, reason });
    return true;
  }

  destroy() {
    if (this.#destroyed) return;
    this.close({ restoreFocus: false, reason: 'destroy' });
    for (const [target, type, listener, capture] of this.#listeners) target.removeEventListener(type, listener, capture);
    this.#listeners = [];
    this.#destroyed = true;
  }

  #listen(target, type, listener, capture = false) {
    target.addEventListener(type, listener, capture);
    this.#listeners.push([target, type, listener, capture]);
  }
  #syncTriggers() {
    const dialogs = new Map([...this.#root.querySelectorAll('dialog[data-scada-dialog]')].map(dialog => [dialog.dataset.scadaDialog, dialog]));
    this.#root.querySelectorAll('[data-scada-open]').forEach(trigger => {
      const dialog = dialogs.get(trigger.dataset.scadaOpen);
      if (!dialog) return;
      trigger.setAttribute('aria-haspopup', 'dialog');
      trigger.setAttribute('aria-controls', dialog.id);
      trigger.setAttribute('aria-expanded', String(dialog === this.#current));
    });
  }
  #focusables(dialog) {
    return [...dialog.querySelectorAll(focusSelector)].filter(element =>
      (element.tabIndex >= 0 || element.getAttribute('contenteditable') === 'true' && !element.hasAttribute('tabindex')) && available(element, dialog));
  }
  #focusDialog(dialog, requested) {
    let target = typeof requested === 'string' ? dialog.querySelector(requested) : requested;
    if (!dialog.contains(target) || !available(target, dialog)) target = null;
    if (!target) target = dialog.querySelector('[autofocus]');
    if (!available(target, dialog)) target = null;
    // Opening a control panel should land on its title/Close, never change a value.
    focusElement(target ?? dialog.querySelector('[data-scada-close]') ?? dialog);
  }
  #restoreFocus(opener) {
    if (available(opener)) focusElement(opener);
    else {
      const fallback = this.#root.querySelector('[data-scada-open]');
      if (available(fallback)) focusElement(fallback);
      else if (this.#root.isConnected) {
        if (!this.#root.hasAttribute('tabindex')) this.#root.setAttribute('tabindex', '-1');
        focusElement(this.#root);
      }
    }
  }
  #click = event => {
    if (event.defaultPrevented || this.#destroyed) return;
    const target = event.target;
    if (target === this.#fallbackBackdrop) {
      event.preventDefault();
      this.close({ reason: 'backdrop' });
      return;
    }
    const closer = target.closest?.('[data-scada-close]');
    if (closer && this.#current?.contains(closer)) {
      event.preventDefault();
      this.close();
      return;
    }
    const trigger = target.closest?.('[data-scada-open]');
    if (trigger && this.#root.contains(trigger) && !trigger.disabled) {
      if (this.open(trigger.dataset.scadaOpen, { opener: trigger })) event.preventDefault();
      return;
    }
    if (target === this.#current && this.#outsidePointer && this.#outside(event)) {
      event.preventDefault();
      this.close({ reason: 'backdrop' });
    }
    this.#outsidePointer = false;
  };
  #outside(event) {
    if (!this.#current) return false;
    const bounds = this.#current.getBoundingClientRect();
    return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
  }
  #pointerDown = event => {
    this.#outsidePointer = event.target === this.#current && this.#outside(event);
  };
  #cancel = event => {
    if (event.target !== this.#current) return;
    event.preventDefault();
    this.close({ reason: 'escape' });
  };
  #nativeClose = event => {
    // Native close events are queued. Ignore one belonging to a previous dialog.
    if (event.target !== this.#current || event.target.open) return;
    this.close({ reason: 'native' });
  };
  #containFallbackFocus = event => {
    if (!this.#current || this.#native || this.#current.contains(event.target)) return;
    if (scrollLocks.get(this.#document)?.owners.at(-1) !== this) return;
    this.#focusDialog(this.#current);
  };
  #keyDown = event => {
    const dialog = this.#current;
    if (!dialog || event.defaultPrevented) return;
    if (event.key === 'Escape' && !this.#native) {
      event.preventDefault();
      this.close({ reason: 'escape' });
    } else if (event.key === 'Tab') {
      const candidates = this.#focusables(dialog), first = candidates[0], last = candidates.at(-1), active = this.#document.activeElement;
      if (!first) { event.preventDefault(); focusElement(dialog); }
      else if (event.shiftKey && (active === first || !dialog.contains(active))) { event.preventDefault(); focusElement(last); }
      else if (!event.shiftKey && (active === last || !dialog.contains(active))) { event.preventDefault(); focusElement(first); }
    }
  };
}
