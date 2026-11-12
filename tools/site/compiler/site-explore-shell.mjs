/** Shared static Explore/reader chrome. Topic ownership comes from docs/areas.yaml. */
import {glyphSprite} from './catalog-art.mjs';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function topicNodes(areas){
 const nodes=new Map();
 const visit=(n,parent=null,domain=n.slug)=>{nodes.set(n.slug,{...n,parent,domain});for(const child of [...n.areas||[],...n.topics||[]])visit(child,n.slug,domain);};
 for(const d of areas.domains)visit(d);
 return nodes;
}
export const topicSprite=areas=>glyphSprite([...topicNodes(areas).keys(),'cross-cutting']).replace('<svg ','<svg xmlns="http://www.w3.org/2000/svg" ');
/** Exact recorded timestamp; do not fabricate a time for date-only metadata. */
export function updateTime(iso){
 if(/^\d{4}-\d{2}-\d{2}$/.test(iso||''))return {datetime:iso,label:new Intl.DateTimeFormat('en-US',{dateStyle:'long',timeZone:'UTC'}).format(new Date(iso+'T12:00:00Z'))};
 if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$/.test(iso||'')||!Number.isFinite(Date.parse(iso)))throw Error('Expected recorded date or timestamp');
 return {datetime:iso,label:new Intl.DateTimeFormat('en-US',{year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZone:'America/Los_Angeles',timeZoneName:'short'}).format(new Date(iso))};
}
export function topicPlacement(areas,pages,pageURL){
 const nodes=topicNodes(areas),byPage=new Map();
 for(const p of pages){
  const direct=[...nodes.values()].filter(n=>(n.pages||[]).includes(p.file)||(n.skills||[]).some(s=>p.file===`.agents/skills/${s}/SKILL.md`||p.file===`skills/${s}/SKILL.md`)||(n.agents||[]).some(s=>p.file===`.agents/agents/${s}.md`)||(n.lessons&&p.file.startsWith(`docs/lessons/${n.lessons}/`))).map(n=>n.slug);
  if((areas.cross_cutting?.pages||[]).includes(p.file))direct.push('cross-cutting');
  byPage.set(pageURL(p.file),direct.length?[...new Set(direct)]:['cross-cutting']);
 }
 const ancestors=slugs=>[...new Set(slugs.flatMap(slug=>{const result=[];for(let n=slug;n;n=nodes.get(n)?.parent)result.push(n);return result;}))];
 return {nodes,byPage,ancestors};
}
export function topicTree({areas,pages=[],pageURL,current='',browse=false,sprite=true,spriteURL='/web/topic-icons.svg'}){
 const {nodes,byPage,ancestors}=topicPlacement(areas,pages,pageURL),owned=new Map();
 const refTopic=current.startsWith('/references/')?current.split('/')[2]:null;
 const preferred=[...(byPage.get(current)||(nodes.has(refTopic)?[refTopic]:[]))].sort((a,b)=>ancestors([b]).length-ancestors([a]).length)[0];
 const currentPath=preferred?ancestors([preferred]):[];
 for(const n of nodes.values())owned.set(n.slug,pages.filter(p=>byPage.get(pageURL(p.file)).includes(n.slug)));
 const links=(list,owner)=>list.length?`<ul class="explore-pages">${list.map(p=>`<li><a href="${esc(pageURL(p.file))}"${pageURL(p.file)===current&&owner===preferred?' aria-current="page"':''}>${esc(p.title)}</a></li>`).join('')}</ul>`:'';
 const contains=n=>currentPath.includes(n.slug);
 const icon=slug=>`<svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><use href="${esc(spriteURL)}#g-${esc(slug)}"/></svg>`;
 const topicLink=n=>`<a href="/explore?area=${esc(n.slug)}"${browse?' data-gallery-js data-gallery-link data-facet="area" data-value="'+esc(n.slug)+'" data-label="'+esc(n.title)+'"':''}>Browse ${esc(n.title)}${browse?' <span data-count></span>':''}</a>`;
 const branch=n=>`<details class="cad-nav-group explore-topic" data-topic="${esc(n.slug)}" data-tone="${esc(n.domain||n.slug)}"${contains(n)?' open':''}><summary>${icon(n.slug)}<span>${esc(n.title)}</span></summary><div>${topicLink(n)}${browse?'':links(owned.get(n.slug)||[],n.slug)}${[...n.areas||[],...n.topics||[]].map(child=>branch(nodes.get(child.slug))).join('')}</div></details>`;
 const other=pages.filter(p=>byPage.get(pageURL(p.file)).includes('cross-cutting')&&p.section!=='folder-maps');
 return `${sprite&&!spriteURL?glyphSprite([...nodes.keys(),'cross-cutting']):''}<div class="explore-tree" data-topic-tree><a class="explore-all" href="/explore?area="${browse?' data-gallery-js data-gallery-link data-facet="area" data-value=""':''}>All topics</a>${areas.domains.map(d=>branch(nodes.get(d.slug))).join('')}<details class="cad-nav-group explore-topic" data-topic="cross-cutting"${preferred==='cross-cutting'?' open':''}><summary>${icon('cross-cutting')}<span>Across topics</span></summary><div><a href="/explore?area=cross-cutting"${browse?' data-gallery-js data-gallery-link data-facet="area" data-value="cross-cutting" data-label="Across topics"':''}>Browse across topics</a>${browse?'':links(other,'cross-cutting')}</div></details><a href="/references/unplaced">Not yet placed sources</a><a href="/docs/map">Repository map</a></div>`;
}
export function articleOutline(html){
 const heads=[...html.matchAll(/<h([23]) id="([^"]+)">([\s\S]*?)<\/h\1>/g)];
 if(heads.length<2)return '';
 return `<ol class="cad-nav-outline">${heads.map(([,level,id,title])=>`<li class="h${level}"><a href="#${esc(encodeURIComponent(id))}">${title.replace(/<[^>]+>/g,'')}</a></li>`).join('')}</ol>`;
}
export function readerNav({areas,pages,pageURL,current,outlineHTML=''}){
 return `<cad-nav class="explore-nav" topic-tree for=".doc-main" rail=".doc-rail" role="navigation" aria-label="Explore topics and pages"><details class="cad-nav-fold"><summary class="cad-nav-toggle">Explore topics</summary><div class="cad-nav-panel"><form class="explore-nav-search" action="/explore" role="search"><label for="explore-reader-search">Search all knowledge</label><div><input id="explore-reader-search" name="q" type="search" placeholder="Tools, guides, sources…"><button type="submit">Search</button></div></form><input type="search" class="cad-nav-filter" disabled placeholder="Filter this tree" aria-label="Filter topic pages"><p class="cad-nav-empty" role="status"></p>${topicTree({areas,pages,pageURL,current})}${outlineHTML?`<div class="explore-mobile-outline"><p>On this page</p>${outlineHTML}</div>`:''}</div></details></cad-nav>`;
}
