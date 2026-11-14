/** A DOM-only camera for a fixed-size 2D world. No model, clock or framework.
 * Coordinates are CSS pixels: translate(x,y) scale(zoom), origin at top left. */
const finite = (value, name) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new TypeError(`${name} must be finite.`);
  return value;
};
const positive = (value, name) => {
  if (finite(value, name) <= 0) throw new RangeError(`${name} must be positive.`);
  return value;
};
const center = points => ({x:(points[0].x + points[1].x) / 2, y:(points[0].y + points[1].y) / 2});
const distance = points => Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);

export class ScadaCamera {
  #viewport; #canvas; #stage; #width; #height; #onChange; #fitButton;
  #state = {x:0, y:0, zoom:1, fitted:true};
  #size = {width:0, height:0}; #listeners = []; #restore = []; #observer;
  #pointers = new Map(); #dragging = false; #suppressClick = false; #destroyed = false;

  constructor({viewport, canvas = viewport?.querySelector('[data-scada-canvas]'), stage,
    width, height, fitOnMount = true, state, onChange} = {}) {
    if (!viewport?.ownerDocument || !canvas?.style || viewport === canvas || !viewport.contains(canvas)) throw new TypeError('A camera needs a viewport containing its canvas.');
    this.#width = positive(width ?? Number(canvas.dataset.scadaWidth), 'Canvas width');
    this.#height = positive(height ?? Number(canvas.dataset.scadaHeight), 'Canvas height');
    if (stage && (!viewport.contains(stage) || !stage.contains(canvas) || stage === canvas || stage === viewport)) throw new TypeError('The optional stage must contain the canvas inside the viewport.');
    if (onChange != null && typeof onChange !== 'function') throw new TypeError('onChange must be a function.');
    this.#viewport = viewport; this.#canvas = canvas;
    this.#stage = stage ?? (canvas.parentElement?.hasAttribute('data-scada-stage') ? canvas.parentElement : null);
    this.#onChange = onChange;
    if (state) this.#state = this.#validateState(state);
    else this.#state.fitted = Boolean(fitOnMount);
    this.#remember(viewport, ['overflow','position','touch-action','user-select','cursor'], ['data-scada-camera','data-camera-x','data-camera-y','data-camera-zoom','data-camera-fitted','data-camera-dragging','tabindex']);
    this.#remember(canvas, ['position','left','top','width','height','min-width','margin','transform','transform-origin'], []);
    if (this.#stage) this.#remember(this.#stage, ['position','width','height','min-width','min-height','overflow'], []);
    if (!viewport.hasAttribute('tabindex')) viewport.tabIndex = 0;
    this.#fitButton = viewport.ownerDocument.createElement('button');
    this.#fitButton.type = 'button'; this.#fitButton.className = 'scada-camera-fit';
    this.#fitButton.setAttribute('data-scada-camera-controls', '');
    this.#fitButton.setAttribute('data-scada-camera-fit', '');
    this.#fitButton.textContent = 'Zoom to fit';
    this.#fitButton.title = 'Show the complete diagram (Home or F)';
    this.#listen('pointerdown', event => this.#pointerDown(event));
    // Retain click targets until a drag starts, but still see an early release
    // outside the viewport before pointer capture has become necessary.
    const window = viewport.ownerDocument.defaultView;
    this.#listen('pointermove', event => this.#pointerMove(event), undefined, window);
    this.#listen('pointerup', event => this.#pointerEnd(event), undefined, window);
    this.#listen('pointercancel', event => this.#pointerEnd(event), undefined, window);
    this.#listen('lostpointercapture', event => { if (event.target === viewport) this.#pointerEnd(event); });
    this.#listen('click', event => {
      if (this.#suppressClick && event.detail !== 0) { event.preventDefault(); event.stopImmediatePropagation(); }
      else if (this.#fitButton.contains(event.target)) { event.preventDefault(); event.stopPropagation(); this.fit(); }
    }, true);
    this.#listen('dragstart', event => event.preventDefault());
    this.#listen('wheel', event => this.#wheel(event), {passive:false});
    this.#listen('keydown', event => this.#key(event));
    this.#listen('focusin', event => this.#reveal(event.target));
    // overflow:clip is not a scroll container. Reset legacy offsets as a fallback
    // when an embedding host/browser still treats the viewport as scrollable.
    this.#listen('scroll', () => { viewport.scrollLeft = 0; viewport.scrollTop = 0; });
    const ResizeObserver = viewport.ownerDocument.defaultView?.ResizeObserver;
    if (ResizeObserver) { this.#observer = new ResizeObserver(() => this.refresh()); this.#observer.observe(viewport); }
    try { this.refresh(); }
    catch (error) { this.destroy(); throw error; }
  }
  get state() { return {...this.#state}; }
  get viewport() { return this.#viewport; }
  get canvas() { return this.#canvas; }
  #validateState(state) {
    const zoom = positive(state.zoom, 'Zoom');
    if (zoom > 3) throw new RangeError('Zoom must not exceed 3.');
    return {x:finite(state.x, 'Camera x'), y:finite(state.y, 'Camera y'), zoom, fitted:state.fitted === true};
  }
  #remember(element, properties, attributes) {
    const styles = properties.map(name => [name, element.style.getPropertyValue(name), element.style.getPropertyPriority(name)]);
    const attrs = attributes.map(name => [name, element.getAttribute(name)]);
    this.#restore.push(() => {
      for (const [name, value, priority] of styles) value ? element.style.setProperty(name, value, priority) : element.style.removeProperty(name);
      for (const [name, value] of attrs) value == null ? element.removeAttribute(name) : element.setAttribute(name, value);
    });
  }
  #listen(type, handler, options, target = this.#viewport) {
    target.addEventListener(type, handler, options);
    this.#listeners.push([type, handler, options, target]);
  }
  #measure() {
    const rect = this.#viewport.getBoundingClientRect();
    return {width:this.#viewport.clientWidth || rect.width, height:this.#viewport.clientHeight || rect.height};
  }
  #fitScale() {
    if (!this.#size.width || !this.#size.height) return 0;
    // Leave a screen-space strip for recovery controls, plus a 12px edge gap.
    return Math.min(1, Math.max(1,this.#size.width - 24) / this.#width, Math.max(1,this.#size.height - 76) / this.#height);
  }
  #fitState() {
    if (!this.#size.width || !this.#size.height) return {...this.#state, fitted:true};
    const zoom = this.#fitScale();
    return {zoom, x:(this.#size.width - this.#width * zoom) / 2, y:(this.#size.height - this.#height * zoom + 52) / 2, fitted:true};
  }
  #apply(reason) {
    if (this.#destroyed) return this;
    const {x,y,zoom,fitted} = this.#state, viewport = this.#viewport;
    Object.assign(viewport.style, {overflow:'clip', position:'relative', touchAction:'none', userSelect:'none', cursor:this.#dragging ? 'grabbing' : 'grab'});
    viewport.setAttribute('data-scada-camera', '');
    if (this.#fitButton.parentElement !== viewport) viewport.append(this.#fitButton);
    for (const [name, value] of Object.entries({x,y,zoom,fitted,dragging:this.#dragging})) viewport.setAttribute(`data-camera-${name}`, String(value));
    if (this.#stage) Object.assign(this.#stage.style, {position:'relative', width:'100%', height:'100%', minWidth:'0', minHeight:'0', overflow:'visible'});
    Object.assign(this.#canvas.style, {position:'absolute', left:'0', top:'0', width:`${this.#width}px`, minWidth:`${this.#width}px`, height:`${this.#height}px`, margin:'0', transform:`translate(${x}px, ${y}px) scale(${zoom})`, transformOrigin:'top left'});
    viewport.scrollLeft = 0; viewport.scrollTop = 0;
    if (reason) this.#onChange?.(this.state, reason);
    return this;
  }
  /** Reapply owned styles after a host DOM patch; resize preserves manual focus. */
  refresh() {
    if (this.#destroyed) return this;
    const before = this.#size, previous = this.#state, next = this.#measure(); this.#size = next;
    const resized = before.width !== next.width || before.height !== next.height;
    if (this.#state.fitted) this.#state = this.#fitState();
    else if (resized && before.width && before.height && next.width && next.height) {
      this.#state.x += (next.width - before.width) / 2;
      this.#state.y += (next.height - before.height) / 2;
    }
    const changed = ['x','y','zoom'].some(key => previous[key] !== this.#state[key]);
    return this.#apply(resized ? 'resize' : changed ? 'fit' : undefined);
  }
  fit() { if (this.#destroyed) return this; this.#size = this.#measure(); this.#state = this.#fitState(); return this.#apply('fit'); }
  setSize(width, height, {fit = false} = {}) {
    positive(width, 'Canvas width'); positive(height, 'Canvas height');
    this.#width = width; this.#height = height;
    return fit ? this.fit() : this.refresh();
  }
  setState(state) { this.#state = this.#validateState(state); return this.#apply('restore'); }
  setZoom(value, point = {x:this.#size.width / 2, y:this.#size.height / 2}) {
    positive(value, 'Zoom'); finite(point.x, 'Anchor x'); finite(point.y, 'Anchor y');
    if (this.#destroyed) return this;
    // Keep wheel gestures continuous even when an enormous layout fits below 5%.
    const minimum = Math.min(.05, this.#fitScale() || .05), zoom = Math.min(3, Math.max(minimum, value));
    const ratio = zoom / this.#state.zoom;
    this.#state = {x:point.x - (point.x - this.#state.x) * ratio, y:point.y - (point.y - this.#state.y) * ratio, zoom, fitted:false};
    return this.#apply('zoom');
  }
  zoomBy(factor, point) { return this.setZoom(this.#state.zoom * positive(factor, 'Zoom factor'), point); }
  panBy(dx, dy) {
    finite(dx, 'Pan x'); finite(dy, 'Pan y');
    if (this.#destroyed) return this;
    this.#state = {...this.#state, x:this.#state.x + dx, y:this.#state.y + dy, fitted:false};
    return this.#apply('pan');
  }
  #point(event) {
    const rect = this.#viewport.getBoundingClientRect();
    return {x:event.clientX - rect.left - this.#viewport.clientLeft, y:event.clientY - rect.top - this.#viewport.clientTop};
  }
  #capture(id) { try { this.#viewport.setPointerCapture?.(id); } catch { /* Pointer may already have ended. */ } }
  #pointerDown(event) {
    if (event.button !== 0 && event.pointerType !== 'touch') return;
    if (!this.#pointers.size) { this.#suppressClick = false; this.#dragging = false; }
    if (this.#fitButton.contains(event.target)) return;
    const point = this.#point(event);
    this.#pointers.set(event.pointerId, {...point, start:point});
    if (this.#pointers.size > 1) {
      this.#dragging = true; this.#suppressClick = true;
      for (const id of this.#pointers.keys()) this.#capture(id);
      this.#apply();
    }
  }
  #pointerMove(event) {
    const previous = this.#pointers.get(event.pointerId);
    if (!previous) return;
    const before = [...this.#pointers.values()], point = this.#point(event);
    this.#pointers.set(event.pointerId, {...point, start:previous.start});
    const after = [...this.#pointers.values()];
    if (after.length > 1) {
      event.preventDefault();
      const a = center(before), b = center(after), length = distance(before);
      if (length > 0) this.zoomBy(distance(after) / length || 1, a);
      this.panBy(b.x - a.x, b.y - a.y);
    } else {
      const starting = !this.#dragging;
      if (starting && Math.hypot(point.x - previous.start.x, point.y - previous.start.y) < 6) return;
      this.#dragging = true; this.#suppressClick = true; this.#capture(event.pointerId);
      event.preventDefault();
      const origin = starting ? previous.start : previous;
      this.panBy(point.x - origin.x, point.y - origin.y);
    }
  }
  #pointerEnd(event) {
    if (!this.#pointers.has(event.pointerId)) return;
    this.#pointers.delete(event.pointerId);
    try { if (this.#viewport.hasPointerCapture?.(event.pointerId)) this.#viewport.releasePointerCapture(event.pointerId); } catch { /* Already released by the browser. */ }
    if (!this.#pointers.size) this.#dragging = false;
    this.#apply();
  }
  #wheel(event) {
    if (!event.deltaY) return;
    event.preventDefault();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.#size.height : 1;
    this.zoomBy(Math.exp(Math.max(-2, Math.min(2, -event.deltaY * unit * .0015))), this.#point(event));
  }
  #key(event) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest?.('input,select,textarea,[contenteditable="true"]')) return;
    const step = event.shiftKey ? 100 : 40;
    const actions = {ArrowLeft:() => this.panBy(step,0), ArrowRight:() => this.panBy(-step,0), ArrowUp:() => this.panBy(0,step), ArrowDown:() => this.panBy(0,-step), '+':() => this.zoomBy(1.25), '=':() => this.zoomBy(1.25), '-':() => this.zoomBy(.8), '_':() => this.zoomBy(.8), Home:() => this.fit(), f:() => this.fit(), F:() => this.fit()};
    if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
  }
  #reveal(element) {
    if (!this.#canvas.contains(element) || element === this.#canvas || this.#pointers.size) return;
    const bounds = element.getBoundingClientRect(), viewport = this.#viewport.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const padding = 12, left = viewport.left + this.#viewport.clientLeft + padding, top = viewport.top + this.#viewport.clientTop + 64;
    const right = left + this.#size.width - padding * 2, bottom = viewport.top + this.#viewport.clientTop + this.#size.height - padding;
    const offset = (start, end, min, max) => end - start > max - min ? (min + max - start - end) / 2 : start < min ? min - start : end > max ? max - end : 0;
    const dx = offset(bounds.left,bounds.right,left,right), dy = offset(bounds.top,bounds.bottom,top,bottom);
    if (dx || dy) this.panBy(dx,dy);
  }
  destroy() {
    if (this.#destroyed) return;
    this.#destroyed = true; this.#observer?.disconnect();
    for (const [type, handler, options, target] of this.#listeners) target.removeEventListener(type, handler, options);
    this.#listeners = [];
    for (const id of this.#pointers.keys()) { try { this.#viewport.releasePointerCapture?.(id); } catch { /* Not captured. */ } }
    this.#pointers.clear();
    this.#fitButton.remove();
    for (const restore of this.#restore.reverse()) restore();
    this.#restore = [];
  }
}
