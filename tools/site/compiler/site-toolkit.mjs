/** Target-owned Toolkit pages and working examples. SCADA metadata stays library-owned.
 * This projection does not replace component, model or scenario schemas. Its JSON is a browser index.
 */
import {folderMapPath} from '../publication.mjs';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SLUG = /^[a-z][a-z0-9-]*$/;
const UI = 'software/cadagent/webkit/scada/ui/';
const SIM = 'software/cadagent/webkit/scada/sim/';
export const TOOLKIT_ROUTES = ['/toolkit', '/toolkit/scada', '/toolkit/scada/elements', '/toolkit/scada/simulations', '/toolkit/models'];
export const SCADA_INPUTS = {components:UI+'metadata/components.json', gallery:UI+'metadata/gallery.json', scenarios:SIM+'scenarios/index.json', thumbnails:SIM+'metadata/thumbnails.json'};

function requireValue(test, message) { if (!test) throw new Error(`SCADA Toolkit: ${message}`); }
function slug(value, where) { requireValue(typeof value === 'string' && SLUG.test(value), `${where}: invalid identifier`); return value; }
function words(value, where) { requireValue(typeof value === 'string' && value.trim().length > 0, `${where}: missing text`); return value; }
function localAsset(value, owner, has, extension) {
  requireValue(typeof value === 'string' && /^img\/[a-z0-9/-]+\.[a-z]+$/.test(value) && value.endsWith(extension), `invalid gallery asset ${value}`);
  requireValue(has(owner + value), `missing gallery asset ${owner + value}`);
  return '/kit/scada/' + (owner === UI ? 'ui/' : 'sim/') + value;
}

/** Validate the declared inventory and its local assets before generating a discoverable capability. */
export function scadaToolkitModel({components, gallery, scenarios, thumbnails, has}) {
  requireValue(components?.schemaVersion === 1 && Array.isArray(components.categories) && Array.isArray(components.components), 'unsupported component metadata');
  requireValue(gallery?.format === 'scada-ui-svg-gallery' && gallery.version === 1 && Array.isArray(gallery.symbols) && Array.isArray(gallery.states), 'unsupported gallery metadata');
  requireValue(scenarios?.format === 'scada-scenario-catalog' && scenarios.version === 1 && Array.isArray(scenarios.scenarios), 'unsupported scenario metadata');
  requireValue(thumbnails?.format === 'scada-scenario-thumbnails' && thumbnails.version === 1 && Array.isArray(thumbnails.scenarios), 'unsupported thumbnail metadata');
  requireValue(typeof has === 'function', 'asset membership is required');
  const categories = components.categories.map(c => ({id:slug(c.id, 'category'), label:words(c.label, 'category')}));
  const categoryIds = new Set(categories.map(c => c.id));
  requireValue(categoryIds.size === categories.length, 'duplicate category');
  const equipment = new Map();
  for (const c of components.components) {
    const id = slug(c.id, 'component');
    requireValue(!equipment.has(id) && categoryIds.has(c.category), `${id}: duplicate component or unknown category`);
    equipment.set(id, c);
  }
  const ids = new Set();
  const elements = [...gallery.symbols.map(s => [s, s.variant ? 'variant' : 'equipment']), ...gallery.states.map(s => [s, 'state'])].map(([s, kind]) => {
    const type = slug(s.type, 'gallery component'), base = equipment.get(type);
    requireValue(base && base.category === s.category, `${type}: gallery does not match component metadata`);
    const variant = s.variant == null ? null : slug(s.variant, `${type} variant`);
    requireValue(!variant || base.variants?.some(v=>v.id===variant), `${type}: unknown variant ${variant}`);
    const sample = kind === 'state' ? slug(s.sample, `${type} state`) : null;
    const id = [kind, type, variant, sample].filter(Boolean).join('--');
    requireValue(!ids.has(id), `duplicate gallery entry ${id}`); ids.add(id);
    requireValue(Array.isArray(s.stateFields) && s.state && typeof s.state === 'object' && !Array.isArray(s.state), `${id}: missing editable state`);
    const fieldKeys=new Set();
    for (const field of s.stateFields) {
      requireValue(typeof field.key === 'string' && /^[a-zA-Z][a-zA-Z0-9]*$/.test(field.key) && !fieldKeys.has(field.key) && ['boolean','number','select'].includes(field.type), `${id}: invalid state field`);
      fieldKeys.add(field.key);words(field.label,`${id} field ${field.key}`);
      if (field.type === 'select') requireValue(Array.isArray(field.options) && field.options.length > 0 && field.options.every(o=>['string','number'].includes(typeof o.value) && typeof o.label==='string' && o.label.trim()), `${id}: missing select choices`);
      if (field.type === 'number') requireValue(['min','max','step'].every(k=>field[k]==null || Number.isFinite(field[k])) && !(field.min>field.max), `${id}: invalid numeric bounds`);
    }
    return {id, kind, type, variant, sample, category:s.category, title:words(s.variantLabel ? `${s.label} · ${s.variantLabel}` : s.label, id),
      description:words(s.description || base.description, id), stateLabel:words(s.stateLabel, id),
      image:localAsset(s.path, UI, has, '.svg'), state:s.state, fields:s.stateFields,
      keywords:[type, variant, sample, s.label, s.variantLabel, s.category, ...Object.values(base.taxonomy || {}).flat()].filter(x => typeof x === 'string').join(' ')};
  });
  requireValue(equipment.size === elements.filter(e => e.kind === 'equipment').length, 'every component needs exactly one base preview');
  for (const id of equipment.keys()) requireValue(elements.some(e => e.type === id && e.kind === 'equipment'), `${id}: missing base preview`);
  for (const [id,c] of equipment) for(const v of c.variants || []) requireValue(elements.some(e=>e.type===id && e.variant===v.id && e.kind==='variant'), `${id}: missing variant preview ${v.id}`);
  const seenScenarios = new Set();
  const scenarioImages=new Map();
  for(const preview of thumbnails.scenarios) {
    const id=slug(preview.id,'thumbnail');
    requireValue(!scenarioImages.has(id),`duplicate scenario thumbnail ${id}`);
    scenarioImages.set(id,localAsset(preview.path,SIM,has,'.jpg'));
  }
  const examples = scenarios.scenarios.map(s => {
    const id = slug(s.id, 'scenario');
    requireValue(!seenScenarios.has(id), `duplicate scenario ${id}`); seenScenarios.add(id);
    requireValue(s.system === `${id}/system.json` && s.model === `${id}/model.json`, `${id}: scenario references must be local`);
    requireValue(has(SIM+'scenarios/'+s.system) && has(SIM+'scenarios/'+s.model), `${id}: missing system/model`);
    requireValue(Array.isArray(s.views) && s.views.length > 0, `${id}: missing views`);
    requireValue(scenarioImages.has(id),`${id}: missing scenario thumbnail`);
    return {id, title:words(s.title,id), description:words(s.description,id), category:words(s.sector,id),
      image:scenarioImages.get(id), views:s.views.length, experiments:Array.isArray(s.experiments) ? s.experiments.length : 0,
      href:`/kit/scada/explorer/index.html?scenario=${encodeURIComponent(id)}`,
      keywords:[s.title,s.sector,...(s.tags || []),...(s.searchTerms || []),...(s.componentTypes || [])].join(' ')};
  }).sort((a,b) => Number(b.id === 'wastewater-digester') - Number(a.id === 'wastewater-digester') || a.title.localeCompare(b.title,'en'));
  requireValue(examples.length > 0, 'no simulations');
  requireValue(scenarioImages.size===examples.length,'thumbnail inventory does not match scenarios');
  return {schema:'cad-agent-scada-browser/1', license:'UNLICENSED', categories, elements, simulations:examples,
    counts:{equipment:equipment.size,variants:elements.filter(e=>e.kind==='variant').length,states:elements.filter(e=>e.kind==='state').length,simulations:examples.length}};
}

const heading = (title, description, tag = 'SCADA toolkit') => `<header class="toolkit-heading"><p class="eyebrow">${esc(tag)}</p><h1>${esc(title)}</h1><p>${esc(description)}</p></header>`;
const tabs = current => `<nav class="toolkit-tabs" aria-label="SCADA toolkit"><a href="/toolkit/scada"${current==='overview'?' aria-current="page"':''}>Overview</a><a href="/toolkit/scada/elements"${current==='elements'?' aria-current="page"':''}>Elements & states</a><a href="/toolkit/scada/simulations"${current==='simulations'?' aria-current="page"':''}>Example simulations</a></nav>`;
const stats = m => `<dl class="toolkit-stats">${[['Equipment types',m.counts.equipment],['Variants',m.counts.variants],['State examples',m.counts.states],['Simulations',m.counts.simulations]].map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
const limits = '<p class="toolkit-note">Simulation values and fault behaviour are illustrative and editable. Animated symbols communicate state; they do not establish physical accuracy. Models and equation providers can be replaced.</p>';
const license = '<p class="toolkit-license">SCADA package terms: <strong>UNLICENSED</strong>. See the <a href="/kit/scada/README.md">library ownership and provenance</a>. Other cad-agent components retain their own licences.</p>';
const actions = '<div class="toolkit-actions"><a class="button" href="/toolkit/scada/elements">Browse elements</a><a class="button" href="/toolkit/scada/simulations">Explore simulations</a></div>';
const filters = (m, kind) => `<form class="toolkit-filters" data-scada-filters hidden role="search"><label>Search ${kind === 'elements' ? 'equipment' : 'simulations'}<input type="search" name="q" maxlength="512" placeholder="${kind === 'elements' ? 'Pump, PLC, solar, valve…' : 'Wastewater, brewing, nuclear…'}" autocomplete="off"></label><label>${kind === 'elements' ? 'Equipment family' : 'Industry'}<select name="category"><option value="">All ${kind === 'elements' ? 'families' : 'industries'}</option>${(kind==='elements'?m.categories.map(c=>[c.id,c.label]):[...new Set(m.simulations.map(s=>s.category))].sort().map(s=>[s,s])).map(([id,title])=>`<option value="${esc(id)}">${esc(title)}</option>`).join('')}</select></label>${kind==='elements'?'<label>Show<select name="kind"><option value="">Everything</option><option value="equipment">Equipment types</option><option value="variant">Variants</option><option value="state">State examples</option></select></label>':''}<button type="reset">Clear filters</button></form>`;
const elementCard = e => `<article class="toolkit-card toolkit-element" id="${esc(e.id)}" data-scada-card data-category="${esc(e.category)}" data-kind="${e.kind}" data-search="${esc(e.keywords+' '+e.description+' '+e.stateLabel)}"><a class="toolkit-image-link" href="${esc(e.image)}" aria-label="Open ${esc(e.title)} SVG"><img src="${esc(e.image)}" alt="${esc(e.title)} — ${esc(e.stateLabel)}" loading="lazy" decoding="async" width="480" height="360"></a><div class="toolkit-card-body"><p class="toolkit-card-kicker">${esc(e.kind === 'equipment' ? 'Equipment' : e.kind === 'variant' ? 'Variant' : 'State example')}</p><h2>${esc(e.title)}</h2><p>${esc(e.description)}</p><p class="toolkit-state">${esc(e.stateLabel)}</p><div class="toolkit-card-actions"><button type="button" data-scada-preview="${esc(e.id)}" hidden>Try states</button><a href="${esc(e.image)}">SVG asset ↗</a></div></div></article>`;
const exampleCard = s => `<article class="toolkit-card toolkit-example" data-scada-card data-category="${esc(s.category)}" data-search="${esc(s.keywords+' '+s.description)}"><a class="toolkit-image-link" href="${esc(s.href)}" aria-label="Open ${esc(s.title)} simulation"><img src="${esc(s.image)}" alt="${esc(s.title)} process diagram" loading="lazy" decoding="async" width="960" height="640"></a><div class="toolkit-card-body"><p class="toolkit-card-kicker">${esc(s.category)}</p><h2><a href="${esc(s.href)}">${esc(s.title)}</a></h2><p>${esc(s.description)}</p><p class="toolkit-state">${s.views} shared-session views · ${s.experiments} experiments</p><a class="button" href="${esc(s.href)}">Run simulation <span aria-hidden="true">↗</span></a></div></article>`;
const browser = (m, kind) => `<section class="toolkit-browser" data-scada-browser="${kind}" aria-label="${kind==='elements'?'SCADA element library':'Example simulations'}">${filters(m,kind)}<p class="toolkit-results" data-scada-count role="status" aria-live="polite">${kind==='elements'?m.elements.length:m.simulations.length} ${kind==='elements'?'elements and states':'simulations'}</p><p data-scada-empty hidden>No matches. Try another search or clear the filters.</p><div class="toolkit-grid">${(kind==='elements'?m.elements:m.simulations).map(kind==='elements'?elementCard:exampleCard).join('')}</div></section>`;
const preview = '<dialog class="toolkit-preview" aria-labelledby="scada-preview-title"><div class="toolkit-preview-heading"><div><p class="eyebrow">Interactive component</p><h2 id="scada-preview-title"></h2></div><button type="button" data-scada-close aria-label="Close component preview">Close ×</button></div><div class="toolkit-preview-grid"><div class="toolkit-preview-art" data-scada-preview-art></div><form data-scada-state-fields aria-label="Illustrative visual state"></form></div><p data-scada-preview-description></p><p class="toolkit-note">These controls change rendering inputs. Use an example simulation to see equipment connected to a model.</p><p role="alert" data-scada-preview-error></p></dialog>';

/** Generated pages use inline Markdown links. The combined agent document has no per-page URL base. */
export function toolkitFullText(pages, origin) {
  return pages.map(page => {
    const source=new URL(page.url+'.md',origin).href;
    const markdown=page.markdown.split(/(```[\s\S]*?```|`+[^`]*`+)/).map((chunk,index)=>index%2 ? chunk :
      chunk.replace(/(\]\()([^\s)]+)((?:\s+"[^"]*")?\))/g,(all,open,href,close)=>
        /^[a-z][a-z\d+.-]*:/i.test(href) ? all : `${open}${new URL(href,source).href}${close}`)).join('');
    return `\n\n---\n\nSource: ${source}\n\n${markdown.trim()}\n`;
  }).join('');
}

/** Capability cards are a presentation index of existing, locally owned examples. */
export function toolkitCapabilities(m, {catalog = [], has} = {}) {
  const scenario = m.simulations.find(s=>s.id==='wastewater-digester') || m.simulations[0];
  const demo = (id, fallback) => {
    const url = new URL(catalog.find(c=>c.id===id)?.url || fallback, 'https://cad-agent.valpatel.com');
    if (url.origin !== 'https://cad-agent.valpatel.com') throw new Error(`Toolkit: example ${id} must be locally published`);
    return url.pathname + url.search + url.hash;
  };
  const cards = [
    {id:'scada-elements', title:'SCADA elements', kind:'Visual component library',
      description:'Explore animated equipment and change its operating, warning and fault states.',
      image:m.elements.find(e=>e.kind==='equipment' && e.type==='pump')?.image || m.elements[0].image, alt:'Animated centrifugal pump with operating gauges',
      href:'/toolkit/scada/elements', action:'Try equipment states', docs:'/kit/scada/ui/README.md', fit:'contain'},
    {id:'scada-simulations', title:'Connected systems', kind:'Shared simulation',
      description:'Run a wastewater digester or another process. Operate equipment, inject faults and change assumptions.',
      image:scenario.image, alt:`${scenario.title}: connected equipment in the shared simulation`,
      href:scenario.href, action:'Run the digester', docs:'/toolkit/scada/simulations'},
    {id:'models', title:'3D model review', kind:'Interactive CAD assembly',
      description:'Orbit and explode the source-bound Gyropup robot model. Inspect geometry without a CAD installation.',
      image:'/web/models/gyropup.webp', alt:'Gyropup wheel-legged robot, captured from the owned 3D CAD model',
      href:'/toolkit/models', action:'Open 3D model', docs:'/docs/web-parts', fit:'contain'},
    {id:'robot-replay', title:'Robot simulation replay', kind:'Recorded dynamics',
      description:'Replay a real MuJoCo run of an illustrative two-link arm. Orbit, scrub time and change playback speed; source inputs are editable.',
      image:'/kit/simulation/examples/two-link-arm/preview.webp', alt:'Two-link robot arm rendered from an actual MuJoCo recording at 3.2 seconds',
      href:'/kit/simulation/viewer.html', action:'Play robot recording', docs:'/'+folderMapPath('docs/examples/robot-replay/README.md').replace(/\.md$/,'')},
    {id:'files', title:'Original CAD files', kind:'File viewer',
      description:'Inspect an original STL with the shared camera and display tools. The viewer also supports STEP and other CAD formats.',
      image:'/web/toolkit/file-review.webp', alt:'The original-file viewer displaying the example fixture STL',
      href:'/kit/files/file-viewer.html?file=/kit/host/example.stl', action:'Open file example', docs:'/docs/file-viewer'},
    {id:'assembly', title:'Assembly & build guides', kind:'Step-by-step instructions',
      description:'Inspect a synthetic rail assembly and step through its declared insertion sequence.',
      image:'/web/toolkit/assembly.webp', alt:'The build-guide viewer displaying the synthetic rail assembly and its instruction controls',
      href:'/kit/model/viewer.html?guide=/web/toolkit/assembly/guide.json', action:'Follow the build', docs:'/docs/practice/assembly-guide'},
    {id:'mechanisms', title:'Mechanism motion', kind:'Interactive kinematics',
      description:'Change a four-bar linkage’s dimensions and drive its motion. See reachable positions and geometric limits.',
      image:'/docs/img/formulas/fourbar-animator.svg', alt:'Four-bar linkage with a driven crank and moving coupler',
      href:demo('demo-fourbar-animator','/docs/linkages#try-it-the-four-bar-animator'), action:'Try the linkage', docs:'/docs/linkages', fit:'contain'},
    {id:'calculators', title:'Engineering calculators', kind:'Editable equations',
      description:'Adjust a cantilever snap arm and compare deflection, strain and force under the stated assumptions.',
      image:'/docs/img/compliant/cantilever-explorer.svg', alt:'Cantilever snap-arm explorer showing geometry, load and deflection',
      href:demo('demo-snap-arm-explorer','/docs/compliant#try-it-the-snap-arm-explorer'), action:'Try the snap arm', docs:'/docs/compliant', fit:'contain'},
  ];
  if (has) for (const card of cards) {
    for (const asset of [card.image, card.href]) {
      const pathname = new URL(asset, 'https://cad.example').pathname;
      const source = pathname.startsWith('/kit/') ? 'software/cadagent/webkit/' + pathname.slice(5)
        : pathname.startsWith('/web/') ? 'tools/site/assets/' + pathname.slice(5)
        : pathname.startsWith('/docs/img/') ? pathname.slice(1) : null;
      if (source && !has(source)) throw new Error(`Toolkit: missing example asset ${source}`);
    }
  }
  return cards;
}

const capabilityCard = c => `<article class="toolkit-card toolkit-capability" data-toolkit-capability="${esc(c.id)}"><a class="toolkit-image-link" href="${esc(c.href)}" tabindex="-1"><img src="${esc(c.image)}" alt="${esc(c.alt)}" width="800" height="500" loading="lazy"${c.fit==='contain'?' class="toolkit-contain"':''}></a><div class="toolkit-card-body"><p class="toolkit-card-kicker">${esc(c.kind)}</p><h2>${esc(c.title)}</h2><p>${esc(c.description)}</p><div class="toolkit-card-actions"><a class="button" data-toolkit-launch href="${esc(c.href)}">${esc(c.action)}</a><a href="${esc(c.docs)}">${c.id==='scada-simulations'?'All simulations':'Guide'}</a></div></div></article>`;

/** Generated routes remain in the existing site frame, with Markdown twins and a machine-readable index. */
export function toolkitPages(m, {catalog = [], has} = {}) {
  const capabilities = toolkitCapabilities(m,{catalog,has});
  const feature = m.simulations.find(s=>s.id==='wastewater-digester') || m.simulations[0];
  const body = content => `<div class="toolkit-shell">${content}</div>`;
  const pages = [
    {url:'/toolkit',title:'Engineering toolkit',description:'Reusable viewers, SCADA elements, simulations, build instructions and agent workflows.',
      body:body(heading('Tools that make designs understandable.','Open a working example, explore its controls, then use the same components in your own project.','cad-agent toolkit')+
        `<div class="toolkit-grid toolkit-capabilities">${capabilities.map(capabilityCard).join('')}</div><section class="toolkit-roadmap"><h2>Connect the work</h2><p>Keep assumptions, checks and instructions with the source that produced them.</p><div class="toolkit-actions"><a href="/docs/review-packet">Review packets</a><a href="/docs/agent-workflow">Agent skills & workflows</a><a href="/docs/toolkit">Command & Python reference</a></div></section><section class="toolkit-roadmap"><h2>Growing the workbench</h2><p>PCB layer review, electrical-panel diagrams and harness views are planned extensions. Existing <a href="/docs/toolkit">electrical checks</a> remain available; KiCad stays the PCB editor.</p><a href="/explore">Explore designs, guides and evidence →</a></section>`),
      markdown:'# Engineering toolkit\n\nOpen working examples of reusable viewers, simulation and build instructions.\n\n'+capabilities.map(c=>`- [${c.title}: ${c.action}](${c.href}) — ${c.description} [Guide](${c.docs})`).join('\n')+'\n\n[Agent workflows](/docs/agent-workflow) · [Review packets](/docs/review-packet) · [Command and Python reference](/docs/toolkit)\n\nPCB, panel and harness viewers are planned, not launched capabilities.\n'},
    {url:'/toolkit/scada',title:'SCADA toolkit',description:'Animated equipment and connected simulation examples, owned and maintained in cad-agent.',body:body(tabs('overview')+heading('Build a living system.','Animated SCADA elements and shared simulation models for process, energy, manufacturing and growing systems.')+stats(m)+actions+`<section class="toolkit-feature-row"><a href="${esc(feature.href)}"><img src="${esc(feature.image)}" alt="${esc(feature.title)} diagram" width="960" height="640"></a><div><p class="eyebrow">Start with a system</p><h2>${esc(feature.title)}</h2><p>${esc(feature.description)}</p><p>Open equipment, change operating values, close valves and inject faults. Every layout observes the same session.</p><a class="button" href="${esc(feature.href)}">Open simulation ↗</a></div></section>`+limits+`<section class="toolkit-roadmap"><h2>Use it in your own project</h2><p>The viewer, headless model and equation providers are separate library modules. Keep the artwork, replace the equations, or connect a complete external model through the adapter.</p><div class="toolkit-actions"><a href="/kit/scada/ui/README.md">UI library</a><a href="/kit/scada/sim/README.md">Models & equations</a><a href="/kit/scada/sim/examples/model-switching/">Equation switching example</a></div></section>`+license),markdown:`# SCADA toolkit\n\n${m.counts.equipment} equipment types, ${m.counts.variants} variants, ${m.counts.states} visual state examples and ${m.counts.simulations} simulations.\n\n- [Elements and states](/toolkit/scada/elements)\n- [Example simulations](/toolkit/scada/simulations)\n- [Machine-readable browser index](/toolkit/scada/catalog.json)\n- [UI library](/kit/scada/ui/README.md)\n- [Models and equations](/kit/scada/sim/README.md)\n\nIllustrative editable models; package terms remain UNLICENSED.\n`},
    {url:'/toolkit/scada/elements',title:'SCADA elements & states',description:'Browse animated SCADA symbols, variants and states, then try editable visual inputs.',body:body(tabs('elements')+heading('Equipment with character.','Pumps, vessels, generators, PLCs and more — one consistent visual language, with editable operating and fault states.')+browser(m,'elements')+preview+limits+license),markdown:'# SCADA elements and states\n\nBrowse and filter the [equipment gallery](/toolkit/scada/elements).\n\n[Metadata and state fields](/toolkit/scada/catalog.json) describe the [SVG library](/kit/scada/ui/img/README.md). State controls are visual inputs, not physical simulations.\n'},
    {url:'/toolkit/scada/simulations',title:'SCADA example simulations',description:'Run connected simulations for wastewater, food, energy, manufacturing and agriculture.',body:body(tabs('simulations')+heading('Turn the system on.','Explore connected equipment, try failures and change assumptions. Each example offers multiple views of one shared simulation.')+limits+browser(m,'simulations')+license),markdown:'# SCADA example simulations\n\nIllustrative, editable process models with one session across named views.\n\n'+m.simulations.map(s=>`- [${s.title}](${s.href}): ${s.description}`).join('\n')+'\n'},
    {url:'/toolkit/models', title:'3D model review', description:'Inspect the source-bound Gyropup robot CAD assembly with the shared model viewer.',
      css:['/kit/model/model.css'],
      body:body(heading('Inspect a real CAD assembly.','Orbit and explode Gyropup with the same model component used in other cad-agent pages.','3D model viewer')+
        '<cad-model class="toolkit-model-stage" src="/web/models/gyropup.json" label="Gyropup robot CAD assembly"><img class="cad-model-poster" src="/web/models/gyropup.webp" width="1200" height="1200" alt="Gyropup robot CAD assembly"></cad-model><p class="toolkit-note">This is a source-bound CAD display, not a robot dynamics simulation. The simplified model omits interior hardware; viewing it does not verify physical fit or strength.</p><div class="toolkit-actions"><a href="/web/models/gyropup.json">Model and source identity</a><a href="/docs/web-parts">Use the model component</a><a href="/toolkit">All Toolkit examples</a></div>'),
      markdown:'# 3D model review\n\nInspect the [interactive Gyropup CAD assembly](/toolkit/models). Orbit and explode the model.\n\n[Model and source identity](/web/models/gyropup.json) · [Component guide](/docs/web-parts)\n\nThis is a simplified CAD display, not a robot dynamics simulation or a physical fit/strength qualification.\n'},
  ];
  return {pages, files:new Map([['toolkit/scada/catalog.json',JSON.stringify(m)+'\n']])};
}
