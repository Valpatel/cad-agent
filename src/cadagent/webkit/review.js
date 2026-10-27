// Reusable local review panels; each workbench keeps its own selected views.
// Progressive enhancement: the page renders every panel visible; this script turns them into tabs. It is inlined
// into the generated page (cadagent.review) so a static copy works without the local server.
for (const root of document.querySelectorAll('.review-workbench')) {
  if (root.dataset.reviewReady) continue;
  root.dataset.reviewReady = '1';
  const show = (panels, attr, id) => { for (const p of panels) p.hidden = p.getAttribute(attr) !== id; };
  show(root.querySelectorAll('[data-review-group-panel]'), 'data-review-group-panel', '0');
  for (const group of root.querySelectorAll('[data-review-group-panel]'))
    show(group.querySelectorAll('[data-review-panel]'), 'data-review-panel', '0');
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-review-group')) {
      const id = button.dataset.reviewGroup;
      for (const tab of root.querySelectorAll('[data-review-group]')) tab.setAttribute('aria-pressed', String(tab === button));
      show(root.querySelectorAll('[data-review-group-panel]'), 'data-review-group-panel', id);
    } else if (button.hasAttribute('data-review-view')) {
      const panel = button.closest('[data-review-group-panel]');
      for (const tab of panel.querySelectorAll('[data-review-view]')) tab.setAttribute('aria-pressed', String(tab === button));
      show(panel.querySelectorAll('[data-review-panel]'), 'data-review-panel', button.dataset.reviewView);
    }
  });
}
