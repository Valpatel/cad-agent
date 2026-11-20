/** Pure catalog search: aliases belong to data, not scenario-specific UI code.
 * Every query token must match a word prefix in the searchable metadata. */
export function searchTokens(value) {
  return String(value ?? '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
}

export function scenarioMatchesQuery(entry, query = '') {
  const wanted = searchTokens(query);
  if (!wanted.length) return true;
  const words = searchTokens([
    entry.id, entry.title, entry.description, entry.sector,
    ...(entry.tags ?? []), ...(entry.searchTerms ?? []),
    ...(entry.componentTypes ?? []), ...(entry.technologies ?? []), entry.facility,
  ].join(' '));
  return wanted.every(token => words.some(word => word.startsWith(token)));
}

export function filterScenarios(entries, {query = '', sector = '', technology = '', facility = ''} = {}) {
  return entries.filter(entry => (!sector || entry.sector === sector) && (!technology || entry.technologies?.includes(technology)) && (!facility || entry.facility === facility) && scenarioMatchesQuery(entry, query));
}

export function scenarioFacets(entries) {
  return {
    sectors:[...new Set(entries.map(entry=>entry.sector).filter(Boolean))].sort(),
    technologies:[...new Set(entries.flatMap(entry=>entry.technologies??[]))].sort(),
    facilities:[...new Set(entries.map(entry=>entry.facility).filter(Boolean))].sort(),
  };
}
