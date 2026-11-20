// Build-time SVG image adapter. Canonical artwork is copied, never redrawn.
import {
  SCADA_COMPONENTS, SCADA_CATEGORIES, getScadaComponent, getScadaVariants,
  normalizeScadaState, renderScadaComponent,
} from '../../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const SVG_NS = 'http://www.w3.org/2000/svg';
const WIDTH = 480;
const HEIGHT = 360;

function node(tag, attributes = {}, text) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}

export const selections = SCADA_COMPONENTS.flatMap(component => [
  {type: component.type},
  ...getScadaVariants(component.type).map(variant => ({type: component.type, variant: variant.id})),
]);

function cardStyles(artHeight) {
  return `
.gallery-label{font-family:Arial,sans-serif;fill:#dcecf1}
.gallery-code{font-family:monospace;fill:#8fbac9}
.gallery-symbol.scada-component{display:block;width:auto;height:auto;padding:0;max-width:none;overflow:visible}
.gallery-symbol>.twin-equipment-art{display:block;width:auto;height:auto;max-width:none}
.gallery-symbol>svg,.gallery-symbol>.twin-equipment-art>svg{display:block;width:280px!important;height:${artHeight}px!important;max-width:none!important;max-height:none!important;overflow:visible}
.gallery-condition svg{width:24px;height:24px}
`;
}

function appendCard(root, descriptor, id, variant) {
  const definitions = node('defs');
  const gradient = node('linearGradient', {id: id + '-card', x2: 1, y2: 1});
  gradient.append(node('stop', {offset: 0, 'stop-color': '#102635'}), node('stop', {offset: 1, 'stop-color': '#0b1724'}));
  definitions.append(gradient);
  root.append(definitions, node('rect', {
    x: .5, y: .5, width: WIDTH - 1, height: HEIGHT - 1, rx: 14,
    fill: `url(#${id}-card)`, stroke: '#355665',
  }));
  const category = SCADA_CATEGORIES.find(item => item.id === descriptor.category);
  root.append(node('text', {
    class: 'gallery-label', x: 20, y: 28, 'font-size': 11,
    'letter-spacing': 1, style: 'fill:#7acfc9',
  }, category.label.toUpperCase()));
  root.append(node('text', {
    class: 'gallery-label', x: 20, y: 55, 'font-size': 21, 'font-weight': 600,
  }, descriptor.label));
  if (variant) root.append(node('text', {
    class: 'gallery-label', x: 20, y: 74, 'font-size': 12, style: 'fill:#a9bfd0',
  }, descriptor.selectedVariant.label));
}

function copyArtwork(root, original, artHeight) {
  const position = node('g', {transform: 'translate(100 79)'});
  const wrapper = node('g');
  for (const attribute of original.attributes) {
    if (!['aria-label', 'role'].includes(attribute.name)) wrapper.setAttribute(attribute.name, attribute.value);
  }
  wrapper.classList.add('gallery-symbol');
  wrapper.setAttribute('aria-hidden', 'true');
  const sourceArt = [], exportedArt = [];
  let shapeCount = 0;
  for (const child of original.children) {
    if (child.matches('.scada-component-gauges,.scada-component-condition')) continue;
    let copy;
    if (child.namespaceURI === SVG_NS) copy = child.cloneNode(true);
    else {
      copy = node('g');
      for (const attribute of child.attributes) copy.setAttribute(attribute.name, attribute.value);
      for (const nested of child.children) {
        if (nested.namespaceURI !== SVG_NS) throw new Error('Unsupported non-SVG artwork descendant ' + nested.tagName);
        copy.append(nested.cloneNode(true));
      }
    }
    sourceArt.push(...(child.localName === 'svg' ? [child] : [...child.querySelectorAll('svg')]).map(svg => svg.innerHTML));
    const drawings = copy.localName === 'svg' ? [copy] : [...copy.querySelectorAll('svg')];
    for (const svg of drawings) {
      svg.setAttribute('x', 0);
      svg.setAttribute('y', 0);
      svg.setAttribute('width', 280);
      svg.setAttribute('height', artHeight);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      exportedArt.push(svg.innerHTML);
    }
    wrapper.append(copy);
    shapeCount += copy.querySelectorAll('path,rect,circle,ellipse,line,polyline,polygon,text').length;
  }
  position.append(wrapper);
  root.append(position);
  const condition = original.querySelector('.scada-component-condition');
  if (condition) {
    const group = node('g', {
      class: 'scada-component-condition gallery-condition', transform: 'translate(327 7)',
      'data-condition': condition.dataset.condition,
    });
    const icon = condition.querySelector('svg').cloneNode(true);
    icon.setAttribute('width', 24);
    icon.setAttribute('height', 24);
    group.append(icon);
    wrapper.append(group);
  }
  return {shapeCount, artContentPreserved: JSON.stringify(sourceArt) === JSON.stringify(exportedArt)};
}

function appendReadouts(root, gauges, state) {
  const start = 288 - Math.max(0, gauges.length - 2) * 12;
  for (const [index, gauge] of gauges.entries()) {
    const y = start + index * 12;
    const group = node('g', {'data-scada-gauge': gauge.dataset.scadaGauge});
    const percentage = parseFloat(gauge.querySelector('b').style.width);
    const fill = state.fault ? '#ff77ac' : state.status === 'warning' ? '#ffd38a' : '#63e6d9';
    group.append(
      node('text', {class: 'gallery-code', x: 90, y, 'font-size': 10}, gauge.querySelector('small').textContent),
      node('rect', {x: 155, y: y - 6, width: 145, height: 5, rx: 2.5, fill: '#153c50', stroke: '#537d90', 'stroke-width': .6}),
      node('rect', {x: 155, y: y - 6, width: Math.max(0, Math.min(100, percentage)) * 1.45, height: 5, rx: 2.5, fill}),
      node('text', {class: 'gallery-code', x: 385, y, 'font-size': 10, 'text-anchor': 'end'}, gauge.querySelector('strong').textContent),
    );
    root.append(group);
  }
}

function checkLabels(root) {
  document.body.append(root);
  const bounds = [...root.children].filter(element => element.localName === 'text').map(element => {
    const box = element.getBBox();
    return {text: element.textContent, x: box.x, y: box.y, width: box.width, height: box.height};
  });
  root.remove();
  const clipped = bounds.filter(box => box.x < 12 || box.x + box.width > 468 || box.y < 8 || box.y + box.height > 353);
  if (clipped.length) throw new Error('Gallery label overflow: ' + JSON.stringify(clipped));
  return bounds;
}

export function exportCard(selection, css, {subset = true, sourceTree = null} = {}) {
  const {type, variant, state = {}, stateLabel = 'Active illustrative preview'} = selection;
  const options = variant ? {variant} : {};
  const descriptor = getScadaComponent(type, options);
  const fields = new Set(descriptor.stateFields.map(field => field.key));
  for (const key of Object.keys(state)) {
    if (!fields.has(key)) throw new Error('Unknown gallery state field ' + type + '.' + key);
  }
  const normalized = normalizeScadaState(type, state, options);
  const id = ['gallery', type, variant ?? 'base', selection.sample ?? 'active'].join('-');
  const template = document.createElement('template');
  template.innerHTML = renderScadaComponent(type, {...options, id, state: normalized});
  const original = template.content.firstElementChild;
  const gauges = [...original.querySelectorAll('[data-scada-gauge]')];
  if (gauges.length > 6) throw new Error('Gallery layout needs a separate tall card: ' + type);
  const artHeight = 194 - Math.max(0, gauges.length - 2) * 12;
  const root = node('svg', {
    xmlns: SVG_NS, width: WIDTH, height: HEIGHT, viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    role: 'img', 'aria-labelledby': id + '-title ' + id + '-desc',
  });
  root.append(
    node('title', {id: id + '-title'}, descriptor.label + (variant ? ' · ' + descriptor.selectedVariant.label : '')),
    node('desc', {id: id + '-desc'}, original.getAttribute('aria-label') + ' Standalone illustrative gallery preview; not a running model.'),
  );
  const cardCss = cardStyles(artHeight);
  const style = node('style', {}, css + '\n' + cardCss);
  root.append(style);
  appendCard(root, descriptor, id, variant);
  const artwork = copyArtwork(root, original, artHeight);
  appendReadouts(root, gauges, normalized);
  root.append(
    node('text', {class: 'gallery-label', x: 20, y: 328, 'font-size': 12, style: 'fill:#bdeee6'}, stateLabel),
    node('text', {class: 'gallery-code', x: 20, y: 346, 'font-size': 10}, type + (variant ? ' / ' + variant : '')),
  );
  const subsetReport = subset ? subsetStyles(root, style, css, cardCss, sourceTree) : null;
  const textBounds = checkLabels(root);
  const svg = new XMLSerializer().serializeToString(root);
  return {
    svg, ...artwork, subsetReport, textBounds, type, variant: variant ?? null,
    category: descriptor.category, label: descriptor.label, state: normalized,
    ariaLabel: original.getAttribute('aria-label'), stateFields: descriptor.stateFields,
    description: descriptor.description, variantLabel: descriptor.selectedVariant?.label ?? null,
  };
}

export function subsetStyles(root, style, css, cardCss, sourceTree) {
  // Native selectors apply to this fixed image. This is not a runtime CSS bundler.
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(css);
  document.body.append(root);
  const names = new Set([...root.querySelectorAll('*'), root]
    .flatMap(element => getComputedStyle(element).animationName.split(',').map(name => name.trim()))
    .filter(name => name !== 'none'));
  const stats = {
    originalRules: 0, retainedRules: 0, retainedKeyframes: [],
    effectiveAnimationNames: [...names].sort(), unknownRuleTypes: [], selectorFailures: [],
  };
  function visit(rules, sources) {
    if (rules.length !== sources.length) throw new Error('CSS parser rule count disagreement');
    const output = [];
    for (let index = 0; index < rules.length; index++) {
      const rule = rules[index], source = sources[index];
      if (rule.type !== source.type) throw new Error('CSS parser rule type disagreement');
      stats.originalRules++;
      if (rule.type === CSSRule.STYLE_RULE) {
        const comparison = new CSSStyleSheet();
        comparison.replaceSync(source.source);
        if (rule.selectorText !== comparison.cssRules[0]?.selectorText) throw new Error('CSS parser selector disagreement: ' + rule.selectorText);
        let matches = false;
        try { matches = root.matches(rule.selectorText) || !!root.querySelector(rule.selectorText); }
        catch (error) { stats.selectorFailures.push({selector: rule.selectorText, error: String(error)}); matches = true; }
        // Pseudo-elements have no DOM node, so conservatively retain their rules.
        if (matches || rule.selectorText.includes('::')) { output.push(source.source); stats.retainedRules++; }
      } else if (rule.type === CSSRule.KEYFRAMES_RULE) {
        if (rule.name !== source.name) throw new Error('CSS parser keyframe disagreement');
        if (names.has(rule.name)) {
          output.push(source.source); stats.retainedRules++; stats.retainedKeyframes.push(rule.name);
        }
      } else if (rule.type === CSSRule.MEDIA_RULE) {
        if (rule.conditionText !== '(prefers-reduced-motion: reduce)') throw new Error('Review new gallery media condition: ' + rule.conditionText);
        const children = visit(rule.cssRules, source.children);
        if (children) { output.push(source.before + children + source.after); stats.retainedRules++; }
      } else {
        throw new Error('Review conditional animation names before supporting CSS rule ' + rule.type);
      }
    }
    return output.join('\n');
  }
  try { style.textContent = visit(sheet.cssRules, sourceTree) + '\n' + cardCss; }
  finally { root.remove(); }
  return stats;
}

window.scadaGallery = {selections, exportCard, categories: SCADA_CATEGORIES, components: SCADA_COMPONENTS};
