// The reference pages' filters (tools/site-references.mjs writes every row, the controls and the charts). Without
// this script every row shows and the controls stay hidden; with it, the search box, the selects and the chart bars
// filter the table, and the URL keeps the filter (?evidence=read&q=hole), so a filtered view can be linked.
const form = document.querySelector('.refs-filters');
const table = document.querySelector('.refs-table');
if (form && table) {
  const rows = [...table.tBodies[0].rows];
  const count = document.querySelector('.refs-count');
  const total = Number(count?.dataset.total || rows.length);
  const controls = [...form.querySelectorAll('[data-key]')];
  const control = key => controls.find(c => c.dataset.key === key);
  const bars = [...document.querySelectorAll('.refs-chart a[data-filter]')];
  const state = () => Object.fromEntries(controls.map(c => [c.dataset.key, c.value.trim()]).filter(([, v]) => v));
  const matches = (row, s) => Object.entries(s).every(([k, v]) => k === 'q'
    ? v.toLowerCase().split(/\s+/).every(w => row.dataset.text.includes(w))
    : k === 'process' ? row.dataset.process.split(' ').includes(v) : row.dataset[k] === v);
  const apply = (push = true) => {
    const s = state();
    let shown = 0;
    for (const row of rows) { const ok = matches(row, s); row.hidden = !ok; shown += ok; }
    if (count) count.textContent = shown === total ? `${total} records` : `${shown} of ${total} records`;
    for (const a of bars) a.toggleAttribute('aria-current', s[a.dataset.filter] === a.dataset.value);
    if (push) {
      const url = new URL(location.href);
      for (const c of controls) url.searchParams.delete(c.dataset.key);
      for (const [k, v] of Object.entries(s)) url.searchParams.set(k, v);
      history.replaceState(null, '', url);
    }
  };
  // The URL's filter, if it names values the page has.
  const params = new URLSearchParams(location.search);
  for (const c of controls) {
    const v = params.get(c.dataset.key);
    if (v && (c.localName === 'input' || [...c.options].some(o => o.value === v))) c.value = v;
  }
  form.addEventListener('input', () => apply());
  form.addEventListener('submit', e => e.preventDefault());
  form.addEventListener('reset', () => setTimeout(() => apply()));
  // A chart bar sets its filter (again: clears it) and brings the table into view.
  for (const a of bars) a.addEventListener('click', e => {
    const c = control(a.dataset.filter);
    if (!c) return;
    e.preventDefault();
    c.value = c.value === a.dataset.value ? '' : a.dataset.value;
    apply();
    document.getElementById('records')?.scrollIntoView({ block: 'start' });
  });
  form.hidden = false;
  apply(false);
  // A link to one record (#<id>) shows it even when the URL also filters it away.
  let target = null;
  try { target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { /* a malformed hash names nothing */ }
  if (target && target.hidden) { form.reset(); for (const c of controls) c.value = ''; apply(); target.scrollIntoView({ block: 'center' }); }
}
