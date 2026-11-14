/** Progressive search and real component-state previews for target-owned Toolkit pages. */
export function matchesToolkitCard(card, {query = '', category = '', kind = ''} = {}) {
  const words = String(query).slice(0,512).toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const haystack = String(card.search || '').toLocaleLowerCase();
  return (!category || card.category === category) && (!kind || card.kind === kind) && words.every(word => haystack.includes(word));
}

export function enhanceToolkit(root, {location = window.location, history = window.history} = {}) {
  const form = root.querySelector('[data-scada-filters]');
  if (!form) return () => {};
  const cards = [...root.querySelectorAll('[data-scada-card]')], count = root.querySelector('[data-scada-count]'), empty = root.querySelector('[data-scada-empty]');
  const fields = Object.fromEntries(['q','category','kind'].map(name => [name,form.elements.namedItem(name)]));
  const readURL = () => {
    const params = new URL(location.href).searchParams;
    for (const [name,input] of Object.entries(fields)) if (input) {
      const value = (params.get(name) || '').slice(0,512);
      input.value = input.tagName === 'SELECT' && ![...input.options].some(o=>o.value===value) ? '' : value;
    }
  };
  const apply = (save = true) => {
    let visible = 0;
    for (const card of cards) {
      const matches = matchesToolkitCard(card.dataset,{query:fields.q.value,category:fields.category.value,kind:fields.kind?.value || ''});
      card.hidden = !matches; if (matches) visible++;
    }
    count.textContent = `${visible} of ${cards.length} ${root.dataset.scadaBrowser === 'elements' ? 'elements and states' : 'simulations'}`;
    empty.hidden = visible !== 0;
    if (save) {
      const url = new URL(location.href);
      for (const [name,input] of Object.entries(fields)) if (input) { if (input.value) url.searchParams.set(name,input.value); else url.searchParams.delete(name); }
      history.replaceState(history.state,'',url);
    }
  };
  const input = () => apply(), reset = event => {
    event.preventDefault();
    for(const field of Object.values(fields))if(field)field.value='';
    apply();
  }, pop = () => {readURL();apply(false);};
  const submit = event => {event.preventDefault();apply();};
  form.addEventListener('input',input);form.addEventListener('change',input);form.addEventListener('reset',reset);
  form.addEventListener('submit',submit);
  window.addEventListener('popstate',pop);
  readURL();apply(false);form.hidden=false;
  return () => {form.removeEventListener('input',input);form.removeEventListener('change',input);form.removeEventListener('reset',reset);form.removeEventListener('submit',submit);window.removeEventListener('popstate',pop);};
}

export function enhanceComponentPreviews(documentRoot = document) {
  const dialog = documentRoot.querySelector('.toolkit-preview');
  if (!dialog || typeof dialog.showModal !== 'function') return () => {};
  const title = dialog.querySelector('#scada-preview-title'), art = dialog.querySelector('[data-scada-preview-art]');
  const form = dialog.querySelector('[data-scada-state-fields]'), description = dialog.querySelector('[data-scada-preview-description]'), error = dialog.querySelector('[data-scada-preview-error]');
  const buttons = [...documentRoot.querySelectorAll('[data-scada-preview]')];
  let task = 0, opener = null, payload, renderer;
  const load = async () => {
    payload ||= fetch('/toolkit/scada/catalog.json').then(async response => {
      if (!response.ok) throw new Error('Component metadata could not be loaded.');
      const result = await response.json();
      if (result.schema !== 'cad-agent-scada-browser/1' || !Array.isArray(result.elements)) throw new Error('Unsupported component metadata.');
      return result;
    }).catch(e => {payload = null; throw e;});
    renderer ||= import('/kit/scada/ui/src/symbols/index.mjs').catch(e=>{renderer=null;throw e;});
    return Promise.all([payload,renderer]);
  };
  const close = () => dialog.close();
  const submit = event => event.preventDefault();
  const onClose = () => { task++; art.replaceChildren(); form.replaceChildren(); if(opener?.isConnected) opener.focus(); };
  const click = async event => {
    const button = event.currentTarget, serial = ++task; opener = button;
    title.textContent = button.closest('article').querySelector('h2').textContent;
    art.textContent = 'Loading component…'; form.replaceChildren(); description.textContent=''; error.textContent=''; dialog.showModal();
    try {
      const [model,mod] = await load();
      if (serial !== task || !dialog.open) return;
      const selected = model.elements.find(e=>e.id===button.dataset.scadaPreview);
      if (!selected) throw new Error('This component is unavailable in the current library.');
      title.textContent = selected.title; description.textContent = selected.description;
      const state = {...selected.state};
      const render = () => {
        try {
          art.innerHTML = mod.renderScadaComponent(selected.type,{id:'toolkit-state-preview',variant:selected.variant || undefined,label:selected.title,state,decorative:false});
          error.textContent='';
        } catch {error.textContent='This visual state could not be rendered. Reset the field or reopen the preview.';}
      };
      for (const field of selected.fields) {
        const label = documentRoot.createElement('label'), text = documentRoot.createElement('span'); text.textContent=field.label+(field.unit?` (${field.unit})`:'');
        let input;
        if(field.type==='select') {
          input=documentRoot.createElement('select');
          for(const choice of field.options) {const option=documentRoot.createElement('option');option.value=String(choice.value);option.textContent=choice.label;input.append(option);}
          input.value=String(state[field.key] ?? field.default);
        } else {
          input=documentRoot.createElement('input');input.type=field.type==='boolean'?'checkbox':'number';
          if(field.type==='boolean') input.checked=Boolean(state[field.key]);
          else {input.value=String(state[field.key] ?? field.default);for(const key of ['min','max','step'])if(field[key]!=null)input[key]=String(field[key]);}
        }
        input.name=field.key;
        input.addEventListener('input',()=>{
          if(!input.checkValidity())return;
          const value=field.type==='boolean'?input.checked:field.type==='number'?input.valueAsNumber:input.value;
          if(field.type==='number'&&!Number.isFinite(value))return;
          state[field.key]=value;
          render();
        });
        label.append(text,input);form.append(label);
      }
      render();
    } catch {if(serial===task && dialog.open){art.replaceChildren();error.textContent='The interactive preview could not load. The SVG asset remains available on the card.';}}
  };
  dialog.querySelector('[data-scada-close]').addEventListener('click',close);dialog.addEventListener('close',onClose);
  form.addEventListener('submit',submit);
  for(const button of buttons){button.addEventListener('click',click);button.hidden=false;}
  return()=>{task++;for(const button of buttons)button.removeEventListener('click',click);dialog.querySelector('[data-scada-close]').removeEventListener('click',close);dialog.removeEventListener('close',onClose);form.removeEventListener('submit',submit);if(dialog.open)dialog.close();};
}

if (typeof document !== 'undefined') {
  document.querySelectorAll('[data-scada-browser]').forEach(root=>enhanceToolkit(root));
  enhanceComponentPreviews();
}
