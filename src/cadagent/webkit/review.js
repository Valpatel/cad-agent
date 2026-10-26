// Reusable local review panels; each workbench keeps its own selected views.
for (const root of document.querySelectorAll('.review-workbench')) {
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-review-group')) {
      const id = button.dataset.reviewGroup;
      for (const tab of root.querySelectorAll('[data-review-group]')) tab.setAttribute('aria-pressed', String(tab === button));
      for (const panel of root.querySelectorAll('[data-review-group-panel]')) panel.hidden = panel.dataset.reviewGroupPanel !== id;
    } else if (button.hasAttribute('data-review-view')) {
      const panel = button.closest('[data-review-group-panel]');
      for (const tab of panel.querySelectorAll('[data-review-view]')) tab.setAttribute('aria-pressed', String(tab === button));
      for (const view of panel.querySelectorAll('[data-review-panel]')) view.hidden = view.dataset.reviewPanel !== button.dataset.reviewView;
    }
  });
}
