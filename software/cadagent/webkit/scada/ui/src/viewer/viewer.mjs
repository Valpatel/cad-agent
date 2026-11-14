/** Framework-neutral SCADA presentation. Models, clocks and persistence belong
 * to the injected adapter. HTML returned by render hooks is trusted host code. */
import {ScadaCamera} from './camera.mjs';
import {projectProcessLayout} from './process-layout.mjs';
export {ScadaCamera} from './camera.mjs';
import {renderScadaComponent} from '../symbols/components.mjs';
import {ScadaWorkspace, renderScadaDialog} from '../workspace/workspace.mjs';
import {validateSystemDefinition, resolveBinding, resolveComponentState} from '../contracts/system-definition.mjs';

const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const own = (value, key) => value != null && Object.hasOwn(value, key);
const number = (value, label, fallback) => {
  const result = value ?? fallback;
  if (typeof result !== 'number' || !Number.isFinite(result)) throw new TypeError(`${label} must be a finite number.`);
  return result;
};
const entries = value => Array.isArray(value) ? value : Object.values(value ?? {});
function htmlAttributes(attributes = {}) {
  return Object.entries(attributes).map(([key, value]) => {
    if (!/^[a-zA-Z][a-zA-Z0-9:_-]*$/.test(key) || /^on/i.test(key)) throw new TypeError(`Invalid presentation attribute: ${key}`);
    return value === false || value == null ? '' : ` ${key}="${esc(value === true ? '' : value)}"`;
  }).join('');
}
function dimensions(view) {
  const width = number(view.width ?? view.canvas?.width, 'Canvas width', 1100);
  const height = number(view.height ?? view.canvas?.height, 'Canvas height', 680);
  if (width <= 0 || height <= 0) throw new RangeError('Canvas dimensions must be positive.');
  return {width, height};
}
function placedEquipment(view, equipment = []) {
  const registry = new Map(entries(equipment).map(item => [item.id, item]));
  const placements = view.nodes ?? view.placements?.map(item => ({...item, id:item.component})) ?? Object.entries(view.layout ?? {}).map(([id, box]) => ({id, ...box}));
  return placements.map(item => {
    const node = {...registry.get(item.id), ...item};
    node.x = number(node.x, 'Equipment x', 0);
    node.y = number(node.y, 'Equipment y', 0);
    node.w = number(node.w ?? node.width, 'Equipment width', 160);
    node.h = number(node.h ?? node.height, 'Equipment height', 160);
    if (!node.id || node.w <= 0 || node.h <= 0) throw new TypeError('Placed equipment needs an id and positive dimensions.');
    return node;
  });
}
function portPosition(node, portId) {
  const port = entries(node.ports).find(item => item.id === portId);
  if (!port) return {x:node.x + node.w / 2, y:node.y + node.h / 2};
  const offset = number(port.offset, 'Port offset', .5);
  if (offset < 0 || offset > 1) throw new RangeError('Port offset must be between zero and one.');
  if (port.side === 'left') return {x:node.x, y:node.y + node.h * offset};
  if (port.side === 'right') return {x:node.x + node.w, y:node.y + node.h * offset};
  if (port.side === 'top') return {x:node.x + node.w * offset, y:node.y};
  if (port.side === 'bottom') return {x:node.x + node.w * offset, y:node.y + node.h};
  return {x:node.x + number(port.x, 'Port x', node.w / 2), y:node.y + number(port.y, 'Port y', node.h / 2)};
}
function endpointPosition(endpoint, nodes) {
  const id = typeof endpoint === 'string' ? endpoint : endpoint?.component ?? endpoint?.node ?? endpoint?.id;
  const node = nodes.find(item => item.id === id);
  if (!node) throw new TypeError(`Connection endpoint is not placed in this view: ${id}`);
  return portPosition(node, typeof endpoint === 'object' ? endpoint.port : undefined);
}
function connectionPath(edge, nodes) {
  if (typeof edge.path === 'string') return edge.path;
  if (edge.points) {
    if (!Array.isArray(edge.points) || edge.points.length < 2) throw new TypeError('A connection route needs at least two points.');
    return edge.points.map((point, index) => `${index ? 'L' : 'M'}${number(Array.isArray(point) ? point[0] : point.x, 'Route x')} ${number(Array.isArray(point) ? point[1] : point.y, 'Route y')}`).join('');
  }
  const from = endpointPosition(edge.from, nodes), to = endpointPosition(edge.to, nodes), middle = (from.x + to.x) / 2;
  return `M${from.x} ${from.y}H${middle}V${to.y}H${to.x}`;
}
function defaultEdge(edge, context) {
  const path = connectionPath(edge, context.nodes);
  const bound = edge.flowBinding ? resolveBinding(context.snapshot, edge.flowBinding) : own(edge, 'active') ? {found:true, value:edge.active} : resolveBinding(context.snapshot, `/flows/${String(edge.id).replaceAll('~', '~0').replaceAll('/', '~1')}`);
  const available = bound.found && typeof bound.value === 'boolean';
  const active = available && bound.value === true;
  return `<g class="scada-diagram-connection ${esc(edge.className ?? '')}" data-scada-connection="${esc(edge.id)}" data-medium="${esc(edge.medium ?? edge.kind ?? 'process')}" data-active="${active}" data-data-status="${available ? 'available' : 'missing'}">${available ? '' : '<title>Flow indication unavailable</title>'}<path class="scada-diagram-pipe" d="${esc(path)}"/><path class="scada-diagram-flow" d="${esc(path)}"/></g>`;
}
function defaultLabel(label) {
  const lines = Array.isArray(label.text) ? label.text : [label.text];
  return `<text x="${number(label.x, 'Label x')}" y="${number(label.y, 'Label y')}" text-anchor="${esc(label.anchor ?? 'start')}">${lines.map((line, index) => index ? `<tspan x="${label.x}" dy="18">${esc(line)}</tspan>` : esc(line)).join('')}</text>`;
}
function defaultOverlay(overlay, context) {
  const {width, height} = dimensions(context.view);
  const style = `left:${100 * overlay.x / width}%;top:${100 * overlay.y / height}%;width:${100 * (overlay.w ?? overlay.width ?? 180) / width}%;height:${100 * (overlay.h ?? overlay.height ?? 50) / height}%`;
  if (overlay.view) return `<button type="button" class="scada-diagram-portal" data-scada-view-choice="${esc(overlay.view)}" style="${style}">${esc(overlay.label ?? overlay.view)}</button>`;
  return `<span class="scada-diagram-portal" style="${style}">${esc(overlay.label ?? '')}</span>`;
}

/** Translate validated, portable JSON into the viewer's presentation registry.
 * This does not connect to an adapter or interpret command actions. */
export function normalizeViewerDefinition(input) {
  const result = validateSystemDefinition(input);
  if (!result.ok) throw new TypeError(`Invalid SCADA system definition: ${result.errors.map(error => `${error.path}: ${error.message}`).join('; ')}`);
  const definition = result.definition;
  const components = new Map(definition.components.map(component => [component.id, component]));
  const connections = new Map((definition.connections ?? []).map(connection => [connection.id, connection]));
  const views = definition.views.map(view => ({
    ...view, width:view.canvas.width, height:view.canvas.height,
    nodes:view.placements.map(placement => ({...components.get(placement.component), ...placement, id:placement.component, w:placement.width, h:placement.height})),
    edges:(view.routes ?? []).map(route => ({...connections.get(route.connection), points:route.points})),
  }));
  return {definition, system:definition.system, equipment:definition.components, views, commands:definition.commands ?? [], controls:definition.controls ?? []};
}

/** Pure geometry renderer. Node/edge/background/overlay callbacks return trusted
 * HTML or SVG. Every ordinary label and attribute is escaped. No model access,
 * subscription, events, clocks or browser globals are used here. */
export function renderScadaDiagram({view, equipment = [], snapshot = {}, selected = null, zoom = 1, scope = 'scada',
  renderNode, renderEdge = defaultEdge, renderEdges, renderBackground = () => '', renderLabel = defaultLabel,
  renderJunction = junction => `<circle cx="${number(junction.x, 'Junction x')}" cy="${number(junction.y, 'Junction y')}" r="${number(junction.r, 'Junction radius', 5)}"/>`,
  renderPort, renderOverlay = defaultOverlay, classNames = {}, attributes = {}, zoomProperty = '--scada-zoom'} = {}) {
  if (!view || typeof view !== 'object') throw new TypeError('A SCADA view is required.');
  if (typeof renderNode !== 'function') throw new TypeError('A renderNode callback is required.');
  if (!(number(zoom, 'Zoom') > 0)) throw new RangeError('Zoom must be positive.');
  if (!/^--[A-Za-z][A-Za-z0-9_-]*$/.test(zoomProperty)) throw new TypeError('Invalid zoom custom property.');
  const {width, height} = dimensions(view), nodes = placedEquipment(view, equipment);
  const context = {view, snapshot, selected, zoom, equipment, nodes, scope};
  const classes = {scroll:'scada-diagram-scroll', stage:'scada-diagram-stage', canvas:'scada-diagram-canvas', svg:'scada-diagram-svg', edges:'scada-diagram-edges', labels:'scada-diagram-labels', junctions:'scada-diagram-junctions', ports:'scada-diagram-ports', ...classNames};
  const edgeMarkup = renderEdges ? renderEdges(context) : (view.edges ?? view.connections ?? []).map(edge => renderEdge(edge, context)).join('');
  const portMarkup = nodes.flatMap(node => entries(node.ports).map(port => {
    const point = portPosition(node, port.id), item = {...port, ...point, component:node.id};
    return renderPort ? renderPort(item, context) : `<circle data-scada-port="${esc(node.id)}:${esc(port.id)}" cx="${point.x}" cy="${point.y}" r="3"><title>${esc(port.label ?? port.id)}</title></circle>`;
  })).join('');
  return `<div class="${esc(classes.scroll)}" data-scada-scroll tabindex="0" aria-label="${esc(view.ariaLabel ?? `${view.label ?? view.title ?? view.id} diagram. Drag to pan, wheel or pinch to zoom. Arrow keys pan; Home fits the diagram.`)}"${htmlAttributes(attributes.scroll)}><div class="${esc(classes.stage)}" data-scada-stage style="${zoomProperty}:${zoom};--scada-canvas-width:${width}px;--scada-canvas-height:${height}px;width:100%;height:100%"${htmlAttributes(attributes.stage)}><div class="${esc(classes.canvas)}" data-scada-canvas data-scada-width="${width}" data-scada-height="${height}" style="${zoomProperty}:${zoom};width:${width}px;min-width:${width}px;height:${height}px;transform:scale(var(${zoomProperty}));transform-origin:top left"${htmlAttributes(attributes.canvas)}><svg class="${esc(classes.svg)}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(view.ariaLabel ?? view.label ?? view.title ?? view.id)}"${htmlAttributes(attributes.svg)}>${renderBackground(context)}<g class="${esc(classes.edges)}">${edgeMarkup}</g><g class="${esc(classes.labels)}">${(view.labels ?? []).map(label => renderLabel(label, context)).join('')}</g><g class="${esc(classes.junctions)}">${(view.junctions ?? []).map(junction => renderJunction(junction, context)).join('')}</g><g class="${esc(classes.ports)}">${portMarkup}</g></svg>${nodes.map(node => renderNode(node, context)).join('')}${(view.portals ?? view.overlays ?? []).map(overlay => renderOverlay(overlay, context)).join('')}</div></div></div>`;
}

function patchElement(target, source, document) {
  if (target.nodeType !== source.nodeType || target.nodeName !== source.nodeName) { target.replaceWith(source.cloneNode(true)); return; }
  if (target.nodeType === 3) { if (target.nodeValue !== source.nodeValue) target.nodeValue = source.nodeValue; return; }
  if (target.nodeType !== 1) return;
  const editing = target === document.activeElement && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName);
  const modalAttribute = name => target.tagName === 'DIALOG' && target.hasAttribute('open') && ['open','role','aria-modal','data-scada-fallback','style'].includes(name);
  for (const attribute of [...target.attributes]) {
    if (modalAttribute(attribute.name) || (editing && attribute.name === 'value')) continue;
    if (!source.hasAttribute(attribute.name)) target.removeAttribute(attribute.name);
  }
  for (const attribute of [...source.attributes]) {
    if (modalAttribute(attribute.name) || (editing && attribute.name === 'value')) continue;
    if (target.getAttribute(attribute.name) !== attribute.value) target.setAttribute(attribute.name, attribute.value);
  }
  if (!editing && 'value' in target && target.value !== source.value) target.value = source.value;
  if (!editing && 'checked' in target) target.checked = source.checked;
  // Camera chrome stays in screen space and retains focus across model updates.
  const oldChildren = [...target.childNodes].filter(child => !child.hasAttribute?.('data-scada-camera-controls')), newChildren = [...source.childNodes];
  for (let index = 0; index < Math.max(oldChildren.length, newChildren.length); index++) {
    if (!newChildren[index]) oldChildren[index]?.remove();
    else if (!oldChildren[index]) target.append(newChildren[index].cloneNode(true));
    else patchElement(oldChildren[index], newChildren[index], document);
  }
}
function safeFocus(element) { try { element?.focus({preventScroll:true}); } catch { element?.focus(); } }
let nextViewerId = 0;

/**
 * Mount a complete viewer, or attach its selection/subscription controller to
 * trusted host markup with mount(root,{render:false,bindEvents:false,workspace:false}).
 * A missing adapter.dispatch creates a read-only viewer. The adapter owns all
 * commands and model state; destroying a viewer never stops or destroys it.
 */
export class ScadaViewer {
  #projection = null; #projectionPending = false;
  #adapter; #equipment; #views; #commands; #controls; #hooks; #options;
  #viewId; #selected; #zoom; #zoomRequested = false; #fitMaxZoom; #snapshot; #root = null; #workspace = null; #camera = null; #cameraView = null;
  #unsubscribe = null; #listeners = []; #managed = true; #error = ''; #fieldErrors = new Map(); #revision = 0; #attachmentEpoch = 0; #scope;

  constructor(options = {}) {
    const {adapter, definition, hooks = {}, fitMaxZoom = 1, responsiveLayout = null} = options;
    if (responsiveLayout !== null && responsiveLayout !== 'process-chain') throw new TypeError('responsiveLayout must be null or process-chain.');
    if (!adapter || typeof adapter.getSnapshot !== 'function' || typeof adapter.subscribe !== 'function' || (adapter.dispatch != null && typeof adapter.dispatch !== 'function')) throw new TypeError('A viewer adapter needs getSnapshot(), subscribe(), and optional dispatch().');
    if (typeof fitMaxZoom !== 'number' || !Number.isFinite(fitMaxZoom) || fitMaxZoom <= 0 || fitMaxZoom > 3) throw new RangeError('fitMaxZoom must be a finite positive number up to 3.');
    this.#fitMaxZoom = fitMaxZoom;
    const normalized = definition ? normalizeViewerDefinition(definition) : options;
    this.#equipment = entries(normalized.equipment);
    this.#views = entries(normalized.views);
    for (const [label, registry] of [['equipment', this.#equipment], ['view', this.#views]]) {
      if (!registry.length || registry.some(item => !item?.id) || new Set(registry.map(item => item.id)).size !== registry.length) throw new TypeError(`Unique ${label} IDs are required.`);
    }
    this.#adapter = adapter; this.#commands = entries(normalized.commands); this.#controls = options.controls ?? normalized.controls ?? [];
    this.#options = {...options, system:normalized.system ?? options.system}; this.#hooks = hooks;
    this.#viewId = options.initialView ?? this.#views[0].id;
    if (!this.#views.some(view => view.id === this.#viewId)) throw new RangeError('Unknown initial view.');
    this.#selected = options.selected ?? this.#equipment[0].id;
    if (!this.#equipment.some(item => item.id === this.#selected)) throw new RangeError('Unknown selected equipment.');
    this.#zoom = this.#validZoom(options.zoom ?? 1);
    this.#zoomRequested = options.zoom != null;
    this.#scope = options.scope ?? `scada-viewer-${++nextViewerId}`;
    if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(this.#scope)) throw new TypeError('Invalid viewer scope.');
    this.#snapshot = adapter.getSnapshot();
  }
  get snapshot() { return this.#snapshot; }
  get view() { return this.#projection?.id === this.#viewId ? this.#projection : this.#views.find(view => view.id === this.#viewId); }
  get selected() { return this.#selected; }
  get zoom() { return this.#zoom; }
  get root() { return this.#root; }
  get workspace() { return this.#workspace; }
  get camera() { return this.#camera; }
  get readOnly() { return typeof this.#adapter.dispatch !== 'function'; }
  get equipment() { return [...this.#equipment]; }
  get views() { return [...this.#views]; }
  #context() { return {viewer:this, snapshot:this.#snapshot, view:this.view, selected:this.#selected, zoom:this.#zoom, equipment:this.#equipment, scope:this.#scope}; }
  #validZoom(value) { if (typeof value !== 'number' || !Number.isFinite(value) || value < .05 || value > 3) throw new RangeError('Zoom must be between 0.05 and 3.'); return value; }
  #state(component) {
    return resolveComponentState(component, this.#snapshot);
  }
  #node(node, context) {
    if (this.#options.renderNode) return this.#options.renderNode(node, {...context, viewer:this});
    const {width, height} = dimensions(context.view), resolved = this.#state(node);
    const visualId = `${this.#scope}-${node.id}`.replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 100);
    const art = renderScadaComponent(node.type ?? 'pump', {id:visualId, variant:node.variant, label:node.label ?? node.id, state:resolved.state, decorative:true});
    const status = resolved.state.fault ? 'Fault' : resolved.state.status === 'offline' ? 'Offline' : resolved.state.status === 'warning' ? 'Warning' : resolved.state.active ? 'Active' : 'Inactive';
    return `<button type="button" class="scada-viewer-equipment" data-scada-equipment="${esc(node.id)}" data-data-status="${resolved.ok ? 'available' : 'missing'}" aria-pressed="${node.id === this.#selected}" aria-haspopup="dialog" aria-controls="${this.#scope}-inspector-dialog" style="left:${100 * node.x / width}%;top:${100 * node.y / height}%;width:${100 * node.w / width}%;height:${100 * node.h / height}%"><span class="scada-viewer-equipment-label">${esc(node.label ?? node.id)}</span>${art}<span class="scada-viewer-equipment-status">${resolved.ok ? esc(status) : 'Data unavailable'}</span></button>`;
  }
  #controlList(component) {
    const controls = typeof this.#controls === 'function' ? this.#controls(component, this.#context()) : this.#controls;
    return controls.filter(control => !control.component || control.component === component.id);
  }
  #controlValue(control) {
    const result = typeof control.getValue === 'function' ? {found:true, value:control.getValue(this.#snapshot, this.#context())} : control.binding ? resolveBinding(this.#snapshot, control.binding) : {found:own(control, 'value'), value:control.value};
    if (result.found && ((control.kind === 'toggle' && typeof result.value !== 'boolean') || (['range','number'].includes(control.kind) && (typeof result.value !== 'number' || !Number.isFinite(result.value))))) return {found:false, error:{message:'Control reading has the wrong type.'}};
    return result;
  }
  #controlMarkup(control) {
    const current = this.#controlValue(control), disabled = this.readOnly || (control.kind !== 'button' && !current.found);
    const description = this.readOnly ? 'Read-only adapter: commands are unavailable.' : disabled ? 'A current value is unavailable.' : control.description ?? '';
    const fieldError = this.#fieldErrors.get(control.id), errorId = `${this.#scope}-control-${control.id}-error`;
    const feedback = fieldError ? `<small id="${esc(errorId)}" class="scada-viewer-field-error">${esc(fieldError)}</small>` : '';
    const attributes = `${fieldError ? `aria-invalid="true" aria-describedby="${esc(errorId)}" ` : ''}data-scada-control="${esc(control.id)}"${disabled ? ' disabled' : ''}${description ? ` title="${esc(description)}"` : ''}`;
    if (control.kind === 'button') return `<button type="button" class="scada-viewer-button" ${attributes}>${esc(control.label ?? control.id)}</button>`;
    if (control.kind === 'toggle') return `<button type="button" class="scada-viewer-button scada-viewer-toggle" ${attributes} aria-pressed="${Boolean(current.value)}">${esc(control.label ?? control.id)} <span>${current.found ? current.value ? 'On / open' : 'Off / closed' : 'Unavailable'}</span></button>`;
    if (!['range','number','select'].includes(control.kind)) throw new TypeError(`Unsupported control kind: ${control.kind}`);
    if (control.kind === 'select') return `<label class="scada-viewer-field"><span>${esc(control.label ?? control.id)}</span><select ${attributes}>${(control.options ?? []).map(option => `<option value="${esc(option.value)}"${option.value === current.value ? ' selected' : ''}>${esc(option.label)}</option>`).join('')}</select>${feedback}</label>`;
    return `<label class="scada-viewer-field"><span>${esc(control.label ?? control.id)} <output>${current.found ? esc(current.value) : 'Unavailable'}</output></span><input type="${control.kind}" ${attributes} value="${current.found ? esc(current.value) : ''}"${control.min == null ? '' : ` min="${esc(control.min)}"`}${control.max == null ? '' : ` max="${esc(control.max)}"`} step="${esc(control.step ?? 'any')}">${feedback}</label>`;
  }
  #inspector() {
    const component = this.#equipment.find(item => item.id === this.#selected), context = this.#context();
    if (this.#options.renderInspector) return this.#options.renderInspector(component, context);
    const resolved = this.#state(component);
    return `${component.description ? `<p>${esc(component.description)}</p>` : ''}${!resolved.ok ? `<p class="scada-viewer-data-note" role="status">${resolved.errors.map(error => esc(error.message)).join(' ')}</p>` : ''}<dl class="scada-viewer-readings">${Object.entries(resolved.state).map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd></div>`).join('')}</dl><div class="scada-viewer-controls">${this.#controlList(component).map(control => this.#controlMarkup(control)).join('')}</div>${this.readOnly ? '<p class="scada-viewer-data-note">Read-only view. The connected adapter does not accept commands.</p>' : ''}`;
  }
  render() {
    const context = this.#context(), component = this.#equipment.find(item => item.id === this.#selected);
    if (this.#options.renderShell) return this.#options.renderShell(context);
    const diagram = renderScadaDiagram({view:this.view, equipment:this.#equipment, snapshot:this.#snapshot, selected:this.#selected, zoom:this.#zoom, scope:this.#scope, ...this.#options.diagram, renderNode:(node, itemContext) => this.#node(node, itemContext)});
    return `<section class="scada-viewer" data-scada-viewer="${this.#scope}" data-readonly="${this.readOnly}" data-running="${this.#snapshot?.running !== false}"><header class="scada-viewer-header"><div><span class="scada-viewer-eyebrow">${this.readOnly ? 'READ-ONLY SCADA VIEW' : 'CONNECTED SCADA VIEW'}</span><h2>${esc(this.#options.system?.label ?? 'System viewer')}</h2></div><p>${esc(this.#options.system?.description ?? 'Select equipment to inspect its state and available commands.')}</p></header><nav class="scada-viewer-tabs" aria-label="System views">${this.#views.map(view => `<button type="button" data-scada-view-choice="${esc(view.id)}"${view.id === this.#viewId ? ' aria-current="page"' : ''}>${esc(view.label ?? view.shortTitle ?? view.title ?? view.id)}</button>`).join('')}</nav><div class="scada-viewer-toolbar"><label>Equipment <select data-scada-picker>${this.#equipment.map(item => `<option value="${esc(item.id)}"${item.id === this.#selected ? ' selected' : ''}>${esc(item.label ?? item.id)}</option>`).join('')}</select></label><div class="scada-viewer-zoom"><button type="button" data-scada-zoom="fit" title="Fit the complete layout; use 100% to read equipment details">Zoom to fit</button><button type="button" data-scada-zoom="out" aria-label="Zoom diagram out">−</button><button type="button" data-scada-zoom="reset" title="Return to readable 100% scale; drag to explore">${Math.round(this.#zoom * 100)}%</button><button type="button" data-scada-zoom="in" aria-label="Zoom diagram in">+</button></div></div>${diagram}<footer class="scada-viewer-status"><span data-scada-scale-note>${this.#zoom < .8 ? 'Overview scale · use 100% for details' : 'Drag to pan · wheel or pinch to zoom · Home to fit'}</span><span>Selected: <strong>${esc(component.label ?? component.id)}</strong></span><button type="button" data-scada-inspect>Equipment controls</button></footer><p class="scada-viewer-error" data-scada-viewer-error role="alert"${this.#error ? '' : ' hidden'}>${esc(this.#error)}</p>${renderScadaDialog({id:'inspector', title:component.label ?? component.id, scope:this.#scope, kind:'equipment', body:`<p id="${this.#scope}-inspector-error" class="scada-viewer-error" data-scada-viewer-dialog-error role="alert"${this.#error ? '' : ' hidden'}>${esc(this.#error)}</p>${this.#inspector()}`})}</section>`;
  }
  #paint() {
    if (!this.#root || !this.#managed) return;
    const template = this.#root.ownerDocument.createElement('template');
    template.innerHTML = this.render();
    const holder = this.#root.cloneNode(false); holder.append(template.content);
    patchElement(this.#root, holder, this.#root.ownerDocument);
    this.#syncCamera();
  }
  #cameraControls() {
    const reset = this.#root?.querySelector('[data-scada-zoom="reset"]');
    if (reset) reset.textContent = `${Math.round(this.#zoom * 100)}%`;
    const note = this.#root?.querySelector('[data-scada-scale-note]');
    if (note) note.textContent = this.#zoom < .8 ? 'Overview scale · use 100% for details · drag or pinch to explore' : 'Drag to pan · wheel or pinch to zoom · Home to fit';
  }
  #syncCamera() {
    const viewport = this.#root.querySelector('[data-scada-scroll]'), canvas = viewport?.querySelector('[data-scada-canvas]');
    if (!viewport || !canvas) { this.#camera?.destroy(); this.#camera = null; return; }
    const changedView = this.#cameraView !== this.#viewId, {width,height} = dimensions(this.view);
    if (!this.#camera || this.#camera.viewport !== viewport || this.#camera.canvas !== canvas) {
      const state = changedView ? undefined : this.#camera?.state;
      this.#camera?.destroy();
      this.#camera = new ScadaCamera({viewport, canvas, width, height, state, fitMaxZoom:this.#fitMaxZoom,
        fitOnMount:!this.#zoomRequested,
        ...(state || !this.#zoomRequested ? {} : {state:{x:0,y:0,zoom:this.#zoom,fitted:false}}),
        onChange:(camera, reason) => {
          const zoomChanged = this.#zoom !== camera.zoom;
          if (camera.fitted) this.#zoomRequested = false;
          this.#zoom = camera.zoom; this.#cameraControls();
          if (zoomChanged) this.#hooks.zoomChange?.({zoom:camera.zoom, viewer:this, reason});
          if (camera.fitted && ['resize','fit'].includes(reason)) this.#scheduleProjection();
        }});
    } else this.#camera.setSize(width,height,{fit:changedView});
    this.#cameraView = this.#viewId;
    this.#zoom = this.#camera.state.zoom; this.#cameraControls();
  }
  #scheduleProjection() {
    if (this.#options.responsiveLayout !== 'process-chain' || this.#projectionPending) return;
    this.#projectionPending = true;
    const epoch = this.#attachmentEpoch;
    queueMicrotask(() => {
      this.#projectionPending = false;
      if (epoch !== this.#attachmentEpoch || !this.#root || !this.#camera?.state.fitted) return;
      const viewport = this.#camera.viewport, authored = this.#views.find(view => view.id === this.#viewId);
      const next = projectProcessLayout(authored,{width:viewport.clientWidth,height:viewport.clientHeight,fitMaxZoom:this.#fitMaxZoom});
      const current = this.view;
      if (next.width === current.width && next.height === current.height &&
          next.layoutProjection?.columns === current.layoutProjection?.columns) return;
      this.#projection = next === authored ? null : next;
      this.#paint();
    });
  }
  refresh(reason = 'refresh', event = null) {
    this.#snapshot = this.#adapter.getSnapshot(); this.#revision++;
    this.#paint();
    this.#hooks.update?.({snapshot:this.#snapshot, event, viewer:this, reason});
    return this;
  }
  mount(root, {render = true, bindEvents = true, workspace = true} = {}) {
    if (!root?.ownerDocument || typeof root.addEventListener !== 'function') throw new TypeError('A DOM mount element is required.');
    this.destroy(); this.#root = root; this.#managed = render;
    try {
      this.refresh('mount');
      if (workspace) this.#workspace = new ScadaWorkspace(root);
      if (bindEvents) {
        for (const type of ['click', 'change', 'focusout']) { const handler = event => this.#handle(event); root.addEventListener(type, handler); this.#listeners.push([type, handler]); }
      }
      const unsubscribe = this.#adapter.subscribe((snapshotOrEvent, event) => this.refresh('snapshot', event ?? (snapshotOrEvent?.type ? snapshotOrEvent : null)));
      if (typeof unsubscribe !== 'function') throw new TypeError('adapter.subscribe() must return an unsubscribe function.');
      this.#unsubscribe = unsubscribe;
    } catch (error) { this.destroy(); throw error; }
    return this;
  }
  setView(id) {
    if (!this.#views.some(view => view.id === id)) throw new RangeError(`Unknown view: ${id}`);
    if (id === this.#viewId) return this;
    this.closeInspector(); this.#projection = null; this.#viewId = id;
    this.#hooks.viewChange?.({id, viewer:this}); this.refresh('view');
    return this;
  }
  select(id, {open = false, opener} = {}) {
    if (!this.#equipment.some(item => item.id === id)) throw new RangeError(`Unknown equipment: ${id}`);
    if (id !== this.#selected) this.#fieldErrors.clear();
    this.#selected = id; this.#hooks.selectionChange?.({id, viewer:this}); this.refresh('selection');
    if (open) this.openInspector({opener});
    return this;
  }
  setZoom(zoom) {
    this.#validZoom(zoom);
    this.#zoomRequested = true;
    if (this.#camera) this.#camera.setZoom(zoom);
    else { this.#zoom = zoom; this.#hooks.zoomChange?.({zoom, viewer:this}); }
    this.refresh('zoom'); return this;
  }
  fit() { this.#zoomRequested = false; this.#camera?.fit(); return this; }
  openInspector({opener} = {}) {
    this.#hooks.openInspector?.({id:this.#selected, opener, viewer:this});
    return this.#workspace?.open(this.#options.inspectorId ?? 'inspector', {opener}) ?? false;
  }
  closeInspector() { this.#hooks.closeInspector?.({viewer:this}); this.#workspace?.close(); return this; }
  dispatch(command) {
    if (this.readOnly) throw new Error('This viewer is read-only; its adapter does not accept commands.');
    this.#error = ''; const revision = this.#revision, epoch = this.#attachmentEpoch;
    const finish = result => { if (this.#attachmentEpoch === epoch && this.#revision === revision) this.refresh('command'); return result; };
    const fail = error => { if (this.#attachmentEpoch === epoch) { this.#error = error?.message ?? String(error); this.#paint(); } throw error; };
    try { const result = this.#adapter.dispatch(command); return result?.then ? result.then(finish, fail) : finish(result); } catch (error) { return fail(error); }
  }
  #runControl(control, value) {
    if (typeof control.command === 'function') return this.dispatch(control.command(value, this.#context()));
    const base = typeof control.command === 'string' ? this.#commands.find(command => command.id === control.command) : control.command;
    if (!base || typeof base !== 'object') throw new TypeError(`Unknown command for control ${control.id}.`);
    const command = {...base, ...(value === undefined ? {} : {arguments:{...base.arguments, value}})};
    return this.dispatch(command);
  }
  #handle(event) {
    const target = event.target, field = target.closest?.('[data-scada-control]');
    try {
      if (event.type === 'click') {
        const node = target.closest('[data-scada-equipment]'); if (node) { this.select(node.dataset.scadaEquipment, {open:true, opener:node}); return; }
        const view = target.closest('[data-scada-view-choice]'); if (view) { this.setView(view.dataset.scadaViewChoice); safeFocus([...this.#root.querySelectorAll('[data-scada-view-choice]')].find(item => item.dataset.scadaViewChoice === this.#viewId)); return; }
        const inspect = target.closest('[data-scada-inspect]'); if (inspect) { this.openInspector({opener:inspect}); return; }
        const zoom = target.closest('[data-scada-zoom]'); if (zoom) {
          const action = zoom.dataset.scadaZoom;
          if (action === 'fit') this.fit();
          else if (this.#camera) action === 'reset' ? this.#camera.setZoom(1) : this.#camera.zoomBy(action === 'in' ? 1.25 : .8);
          else this.setZoom(Math.max(.05, Math.min(3, action === 'reset' ? 1 : this.#zoom * (action === 'in' ? 1.25 : .8))));
          return;
        }
      }
      if (event.type === 'change' && target.matches('[data-scada-picker]')) { this.select(target.value, {open:true, opener:target}); return; }
      const element = field;
      if (!element || element.disabled) return;
      const component = this.#equipment.find(item => item.id === this.#selected), control = this.#controlList(component).find(item => item.id === element.dataset.scadaControl);
      if (!control) return;
      if (event.type === 'focusout' && this.#fieldErrors.has(control.id)) {
        const current = this.#controlValue(control); if (current.found && 'value' in element) element.value = String(current.value);
        this.#fieldErrors.delete(control.id); this.#error = 'Invalid draft discarded; the last accepted value was kept.'; this.#paint(); return;
      }
      if (event.type === 'click' && control.kind === 'button') void Promise.resolve(this.#runControl(control)).catch(() => {});
      if (event.type === 'click' && control.kind === 'toggle') void Promise.resolve(this.#runControl(control, !this.#controlValue(control).value)).catch(() => {});
      if (event.type === 'change' && ['range','number','select'].includes(control.kind)) {
        const value = control.kind === 'select' ? element.value : Number(element.value);
        if (element.value === '' || (typeof value === 'number' && (!Number.isFinite(value) || (control.min != null && value < control.min) || (control.max != null && value > control.max)))) throw new RangeError('Enter a value within the control limits.');
        this.#fieldErrors.delete(control.id);
        void Promise.resolve(this.#runControl(control, value)).catch(() => {});
      }
    } catch (error) { this.#error = error.message; if (field && event.type === 'change') this.#fieldErrors.set(field.dataset.scadaControl, error.message); this.#paint(); }
  }
  destroy() {
    this.#attachmentEpoch++;
    const unsubscribe = this.#unsubscribe; this.#unsubscribe = null;
    try { unsubscribe?.(); }
    finally {
      for (const [type, handler] of this.#listeners) this.#root?.removeEventListener(type, handler);
      this.#listeners = []; this.#camera?.destroy(); this.#camera = null; this.#cameraView = null; this.#workspace?.destroy(); this.#workspace = null; this.#root = null;
    }
  }
}
