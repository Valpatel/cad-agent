// Progressive enhancement of a real table: original rows remain useful without JS.
// Column headers opt into data-sort="text|number". Cells may carry data-sort-value;
// numeric values must be raw numbers, never parsed from currency or unit labels.
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const mounted = new WeakMap();
const node = (tag, text, className) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (className) e.className = className; return e; };

export function enhancePartTable(table, { label = table.caption?.textContent || 'Parts', tracker, statuses = [], searchable = true, pageSize = 0, printable } = {}) {
  if (mounted.has(table)) return mounted.get(table);
  const body = table.tBodies[0], head = table.tHead?.rows[0];
  if (!body || !head) throw new Error('A part table needs a header and body.');
  const rows = [...body.rows].filter(row => !row.hasAttribute('data-fixed'));
  if (tracker && statuses.some(status => !tracker.fields.includes(status.id))) throw new Error('Unknown checklist field.');
  if (tracker && statuses.length) {
    const ids = rows.map(row => row.dataset.partKey);
    if (ids.some(id => !id) || new Set(ids).size !== ids.length) throw new Error('Trackable rows need unique data-part-key values.');
  }
  table.classList.add('cad-part-table');
  const toolbar = node('div', undefined, 'cad-table-tools');
  toolbar.setAttribute('aria-label', `${label} controls`);
  const count = node('span', undefined, 'cad-table-count'); count.setAttribute('role', 'status');
  let matchedRows = rows, orderedRows = rows;
  let query = '', sorted = null, direction = 1, page = 0, filter = () => true;
  const pagination=node('nav',undefined,'cad-table-pagination');pagination.setAttribute('aria-label',`${label} pages`);
  const previousPage=node('button','←'),nextPage=node('button','→'),pageCount=node('span');previousPage.type=nextPage.type='button';previousPage.setAttribute('aria-label',`Previous page of ${label}`);nextPage.setAttribute('aria-label',`Next page of ${label}`);
  previousPage.onclick=()=>{page--;apply();};nextPage.onclick=()=>{page++;apply();};pagination.append(previousPage,pageCount,nextPage);
  const original = new Map(rows.map((row, index) => [row, index])), buttons = [], checks = [];
  const searchText = new Map(rows.map(row => [row, row.textContent.toLocaleLowerCase()]));
  let input;
  if (searchable) {
    const searchLabel = node('label', undefined, 'cad-table-search'); searchLabel.append(node('span', 'Find a part'));
    input = node('input'); input.type = 'search'; input.placeholder = `Search ${label.toLocaleLowerCase()}`; input.setAttribute('aria-label', `Search ${label}`);
    input.addEventListener('input', () => { query = input.value.trim().toLocaleLowerCase(); page=0; apply(); });
    searchLabel.append(input); toolbar.append(searchLabel);
  }
  const selectLabel = node('label', undefined, 'cad-table-sort'); selectLabel.append(node('span', 'Sort by'));
  const select = node('select'); select.setAttribute('aria-label', `Sort ${label}`);
  const defaultOption = node('option', 'Original order'); defaultOption.value = ''; select.append(defaultOption);
  for (const [index, th] of [...head.cells].entries()) {
    const type = th.dataset.sort;
    if (!['text', 'number'].includes(type)) continue;
    const title = th.textContent.trim(); th.setAttribute('aria-sort', 'none');
    const button = node('button', undefined, 'cad-table-sort-button'); button.type = 'button';
    button.append(node('span', title)); const icon = node('span', '↕'); icon.setAttribute('aria-hidden', 'true'); button.append(icon);
    th.replaceChildren(button);
    button.addEventListener('click', () => { direction = sorted === index ? -direction : 1; sorted = index; apply(); });
    buttons.push({ index, type, th, button, icon, title });
    for (const [suffix, value] of [['ascending', 1], ['descending', -1]]) {
      const option = node('option', `${title} · ${suffix}`); option.value = `${index}:${value}`; select.append(option);
    }
  }
  select.addEventListener('change', () => { [sorted, direction] = select.value ? select.value.split(':').map(Number) : [null, 1]; apply(); });
  selectLabel.append(select); if (buttons.length) toolbar.append(selectLabel); toolbar.append(count);
  // The toolbar belongs outside a horizontally scrolling wrapper when one exists.
  const wrapper = table.parentElement?.classList.contains('cad-table-scroll') ? table.parentElement : table;
  wrapper.before(toolbar);if(pageSize)wrapper.after(pagination);
  const statusesHead = [];
  if (tracker) for (const status of statuses) {
    const th = node('th', status.label); th.scope = 'col'; th.className = 'cad-status-heading'; head.append(th); statusesHead.push(th);
    for (const row of rows) {
      const cell = node('td', undefined, 'cad-status-cell'), checkLabel = node('label', undefined, 'cad-status-check');
      const check = node('input'); check.type = 'checkbox'; check.checked = tracker.get(row.dataset.partKey, status.id);
      const part = row.dataset.partLabel || row.dataset.partKey;
      check.setAttribute('aria-label', `${status.label}: ${part}`);
      check.addEventListener('change', () => {
        try { tracker.set(row.dataset.partKey, status.id, check.checked); }
        catch (error) { check.checked = tracker.get(row.dataset.partKey, status.id); count.textContent = error.message; }
      });
      checkLabel.append(check, node('span', status.label)); cell.append(checkLabel); row.append(cell);
      checks.push({ check, cell, id: row.dataset.partKey, field: status.id });
    }
  }
  const unsubscribe = tracker?.subscribe(() => { for (const item of checks) item.check.checked = tracker.get(item.id, item.field); });
  function value(row, col) {
    const cell = row.cells[col.index], raw = cell?.dataset.sortValue ?? cell?.textContent.trim() ?? '';
    if (col.type === 'number') { const n = raw.trim() === '' ? NaN : Number(raw); return Number.isFinite(n) ? n : null; }
    return raw.trim() || null;
  }
  function apply() {
    const col = buttons.find(col => col.index === sorted);
    const ordered = [...rows].sort((a, b) => {
      if (!col) return original.get(a) - original.get(b);
      const av = value(a, col), bv = value(b, col);
      if (av === null || bv === null) return av === bv ? original.get(a) - original.get(b) : av === null ? 1 : -1;
      return direction * (col.type === 'number' ? av - bv : collator.compare(av, bv)) || original.get(a) - original.get(b);
    });
    const fixed = [...body.rows].find(row => row.hasAttribute('data-fixed')) || null;
    const matched=ordered.filter(row=>(!query||searchText.get(row).includes(query))&&filter(row));
    orderedRows = ordered; matchedRows = matched;
    const pages=pageSize?Math.max(1,Math.ceil(matched.length/pageSize)):1;page=Math.max(0,Math.min(page,pages-1));
    const shown=new Set(pageSize?matched.slice(page*pageSize,(page+1)*pageSize):matched);
    for (const row of ordered) { row.hidden = !shown.has(row); body.insertBefore(row, fixed); }
    count.textContent = `${matched.length} of ${rows.length} parts`;
    pageCount.textContent=`Page ${page+1} of ${pages}`;previousPage.disabled=page===0;nextPage.disabled=page>=pages-1;pagination.hidden=!pageSize||pages===1;
    for (const item of buttons) {
      const active = item.index === sorted;
      item.th.setAttribute('aria-sort', active ? direction === 1 ? 'ascending' : 'descending' : 'none');
      item.icon.textContent = active ? direction === 1 ? '↑' : '↓' : '↕';
      item.button.setAttribute('aria-label', `${item.title}: sort ${active && direction === 1 ? 'descending' : 'ascending'}`);
    }
    select.value = col ? `${sorted}:${direction}` : '';
  }
  const snapshot = (scope = 'matched') => {
    if (!['all', 'matched'].includes(scope)) throw new Error('Checklist scope must be all or matched.');
    const selected = scope === 'all' ? orderedRows : matchedRows;
    const columns = [...head.cells].map((th, index) => ({ index, label: buttons.find(item => item.index === index)?.title || th.textContent.trim() })).filter(col => head.cells[col.index].dataset.print !== 'omit');
    return { label, project: printable?.project || '', revision: printable?.revision || '', notice: printable?.notice || '', scope,
      total: rows.length, query: scope === 'matched' ? query : '', columns: ['Part ID', ...columns.map(col => col.label)],
      rows: selected.map(row => [row.dataset.partKey || row.dataset.partLabel || '', ...columns.map(col => {
        const cell = row.cells[col.index], check = cell?.querySelector('input[type=checkbox]');
        return check ? (check.checked ? '☑' : '☐') : (cell?.dataset.printValue ?? cell?.textContent.trim() ?? '—');
      })]) };
  };
  if (printable) {
    const printScope = node('select'); printScope.setAttribute('aria-label', `Checklist scope for ${label}`);
    for (const [value, title] of [['matched', 'Matching parts (all pages)'], ['all', 'All parts']]) { const option = node('option', title); option.value = value; printScope.append(option); }
    const printLabel = node('label'); printLabel.append(node('span', 'Checklist'), printScope);
    const printButton = node('button', 'Print checklist'); printButton.type = 'button'; printButton.style.minHeight = '44px';
    const printMessage = node('span'); printMessage.setAttribute('role', 'status');
    printButton.addEventListener('click', () => {
      const data = snapshot(printScope.value);
      if (!data.rows.length) { printMessage.textContent = 'No matching parts to print.'; return; }
      const target = window.open('', '_blank');
      if (!target) { printMessage.textContent = 'Allow a new tab to open the printable checklist.'; return; }
      target.opener = null;
      renderPartChecklist(target.document, data);
      printMessage.textContent = `Opened checklist: ${data.rows.length} of ${data.total} parts.`;
    });
    toolbar.append(printLabel, printButton, printMessage);
  }
  apply();
  const api = { table, toolbar, snapshot, setFilter(predicate){filter=predicate;page=0;apply();}, dispose() {
    unsubscribe?.(); toolbar.remove();pagination.remove(); for (const item of checks) item.cell.remove(); for (const th of statusesHead) th.remove();
    for (const item of buttons) { item.th.textContent = item.title; item.th.removeAttribute('aria-sort'); }
    const fixed = [...body.rows].find(row => row.hasAttribute('data-fixed')) || null;
    for (const row of rows) { row.hidden = false; body.insertBefore(row, fixed); }
    table.classList.remove('cad-part-table'); mounted.delete(table);
  } };
  mounted.set(table, api); return api;
}

export function mountProgressTools(host, tracker) {
  let disposed = false, importGeneration = 0;
  const box = node('div', undefined, 'cad-progress-tools'), message = node('p'), receipt = node('p', '', 'cad-progress-receipt');
  receipt.setAttribute('role', 'status');
  const exportButton = node('button', 'Export progress'), importButton = node('button', 'Import progress'), file = node('input');
  exportButton.type = importButton.type = 'button'; file.type = 'file'; file.accept = '.json,application/json'; file.hidden = true;
  const paint = () => { message.textContent = tracker.warning || 'Saved in this browser for this project. Export a backup to use it elsewhere. Checking a box does not place an order.'; };
  paint(); const unsubscribe = tracker.subscribe(paint);
  exportButton.addEventListener('click', () => {
    if (disposed) return;
    const url = URL.createObjectURL(new Blob([tracker.export()], { type: 'application/json' })), link = node('a');
    link.href = url; link.download = `${tracker.project.replace(/[^a-z0-9_-]/gi, '-')}-progress.json`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000); receipt.textContent = 'Progress exported.';
  });
  importButton.addEventListener('click', () => { if (!disposed) file.click(); });
  file.addEventListener('change', async () => {
    if (disposed) return;
    const generation = ++importGeneration;
    const selected = file.files?.[0]; if (!selected) return;
    try {
      if (selected.size > 2_000_000) throw new Error('Choose a progress file smaller than 2 MB.');
      const text = await selected.text();
      if (disposed || generation !== importGeneration) return;
      const count = tracker.import(text); receipt.textContent = `Imported progress for ${count} parts. Matching statuses were updated; other progress was kept.`;
    } catch (error) { if (!disposed && generation === importGeneration) receipt.textContent = error.message; }
    finally { if (!disposed && generation === importGeneration) file.value = ''; }
  });
  box.append(message, exportButton, importButton, file, receipt); host.append(box);
  return { element: box, dispose() { disposed = true; ++importGeneration; unsubscribe(); box.remove(); } };
}

// Build a separate print document; never hide or mutate the live table to print it.
export function renderPartChecklist(doc, data) {
  const make = (tag, text) => { const element = doc.createElement(tag); if (text !== undefined) element.textContent = text; return element; };
  doc.documentElement.lang = 'en'; doc.head.replaceChildren(); doc.body.replaceChildren();
  doc.head.append(make('title', `${data.label} · checklist`));
  const viewport = make('meta'); viewport.name = 'viewport'; viewport.content = 'width=device-width, initial-scale=1'; doc.head.append(viewport);
  const style = make('style', `@page{margin:12mm}*{box-sizing:border-box}body{font:11pt/1.4 system-ui,sans-serif;color:#111;background:white;margin:20px}h1{font-size:20pt;margin-bottom:8px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:9pt}th,td{border:1px solid #777;padding:5px;text-align:left;vertical-align:top;overflow-wrap:anywhere}thead{display:table-header-group}tr{break-inside:avoid}button{font:inherit;padding:10px;margin-bottom:12px}@media print{body{margin:0}button{display:none}}`); doc.head.append(style);
  const print = make('button', 'Print / Save PDF'); print.type = 'button'; print.onclick = () => doc.defaultView.print();
  doc.body.append(print, make('h1', data.label), make('p', `${data.project || 'Project unspecified'} · Revision: ${data.revision || 'unavailable'}`),
    make('p', `${data.scope === 'all' ? 'All parts' : 'Matching parts, all pages'}: ${data.rows.length} of ${data.total}${data.query ? ` · Search: ${data.query}` : ''}`));
  if (data.notice) doc.body.append(make('p', data.notice));
  const table = make('table'), head = make('thead'), headers = make('tr'), body = make('tbody');
  for (const title of ['Done', ...data.columns]) { const th = make('th', title); th.scope = 'col'; headers.append(th); }
  const columns = make('colgroup');
  const weights = [6, ...data.columns.map((title,index) => Math.max(5, Math.min(36, data.rows.reduce((max,row) => Math.max(max,String(row[index] || '').length),title.length))) )];
  const totalWeight = weights.reduce((sum,value) => sum+value,0);
  for (const weight of weights) { const col=make('col'); col.style.width=`${100*weight/totalWeight}%`; columns.append(col); }
  head.append(headers); table.append(columns, head, body);
  for (const values of data.rows) { const row = make('tr'); for (const value of ['☐', ...values]) row.append(make('td', value)); body.append(row); }
  doc.body.append(table);
}
