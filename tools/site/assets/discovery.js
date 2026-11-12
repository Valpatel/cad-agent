/** Expand catalogue metadata from the existing feed only on demand; native JSON fallback remains. */
let entries;
const owned='https://cad-agent.valpatel.com';
export function detailURL(value){
 try{const u=new URL(value,location.origin);if(!/^https?:$/.test(u.protocol)||u.username||u.password)return null;return u.origin===owned?u.pathname+u.search+u.hash:u.href;}catch{return null;}
}
export function fillCatalogueDetails(host,item){
 const doc=host.ownerDocument,body=doc.createElement('div');
 const paragraph=text=>{const p=doc.createElement('p');p.textContent=text;body.append(p);return p;};
 const link=(label,url)=>{const href=detailURL(url);if(!href)return;const a=doc.createElement('a');a.textContent=label;a.href=href;const p=doc.createElement('p');p.append(a);body.append(p);};
 if(item.how){const copy=doc.createElement('cad-copy'),code=doc.createElement('code');copy.setAttribute('text',item.how);copy.setAttribute('label','Copy call');code.textContent=item.how;copy.append(code);body.append(copy);}
 if(item.notes)paragraph(item.notes);if(item.policy)paragraph('Licence policy: '+item.policy);
 if(item.audit){paragraph('Recorded observations, '+item.audit.as_of+'; not a current safety verdict.');for(const o of item.audit.observations||[])paragraph(o.title+' — '+o.evidence+(o.accepted?' Recorded disposition: '+o.accepted:''));link('Read the dated audit report',item.audit.report);}
 if(item.stars!=null)paragraph('GitHub stars: '+String(item.stars));if(item.last_push)paragraph('Last recorded push: '+item.last_push);
 if(item.markdown)link('Read Markdown',item.markdown);if(item.demo)link('Try or watch the example',item.demo);
 if(item.cover){const src=detailURL(item.cover);if(src?.startsWith('/')&&!src.startsWith('//')){const img=doc.createElement('img');Object.assign(img,{src,alt:'Example for '+item.name,width:400,height:300,loading:'lazy',className:'result-cover'});body.append(img);}}
 for(const id of item.related||[])if(/^[a-z0-9][a-z0-9-]*$/.test(id))link('Related: '+id,'/explore#'+id);
 const fallback=host.querySelector('[data-detail-fallback]');if(fallback)fallback.replaceWith(body);else host.append(body);host.dataset.detailReady='';
}
if(typeof document!=='undefined')document.addEventListener('toggle',async event=>{
 const host=event.target;if(!host.matches?.('details[data-catalogue-id]')||!host.open||host.hasAttribute('data-detail-ready')||host.hasAttribute('data-detail-loading'))return;
 host.setAttribute('data-detail-loading','');
 if(!host.querySelector('[data-detail-fallback]')){const p=document.createElement('p'),a=document.createElement('a');p.dataset.detailFallback='';a.href='/catalog.json';a.textContent='Full entry metadata (JSON)';p.append(a);host.append(p);}
 try{
  entries??=fetch('/catalog.json',{credentials:'omit'}).then(r=>{if(!r.ok)throw Error('Catalogue HTTP '+r.status);return r.json();}).then(data=>{if(data.schema!=='cad-agent-catalog/2'||data.revision!==host.closest('cad-gallery')?.dataset.revision||!Array.isArray(data.items))throw Error('Unexpected catalogue feed');return new Map(data.items.map(item=>[item.id,item]));});
  const item=(await entries).get(host.dataset.catalogueId);if(!item)throw Error('Entry not found');fillCatalogueDetails(host,item);
 }catch{entries=undefined;/* Keep the native metadata link; a later open can retry. */}
 finally{host.removeAttribute('data-detail-loading');}
},true);

if(typeof document!=='undefined')for(const host of document.querySelectorAll('details[data-catalogue-id]'))host.setAttribute('data-detail-active','');
