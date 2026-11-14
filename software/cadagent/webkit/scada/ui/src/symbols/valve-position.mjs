/** Internal presentation of supplied valve position, never flow or feedback. */
const TYPES = new Set(['gate-valve', 'control-valve', 'check-valve', 'relief-valve', 'butterfly-valve', 'fuel-pressure-regulator', 'intake-gate']);
const PALETTE = {
  open: {color:'#62ffbc', fill:'#16563f'},
  closed: {color:'#ff8585', fill:'#6b2935'},
  partial: {color:'#7ee9ef', fill:'#1d5365'},
  unavailable: {color:'#b4c4d0', fill:'#334856'},
};

export function getValvePosition(type, state) {
  if (!TYPES.has(type)) return null;
  const opening = state.open === false ? 0 : state.opening ?? 100;
  // Offline values may be retained or filled by normalization. The visual
  // contract has no independent position quality, so do not claim a reading.
  const available = state.status !== 'offline' && state.connected !== false;
  const kind = !available ? 'unavailable' : opening === 0 ? 'closed' : opening === 100 ? 'open' : 'partial';
  // Keep rounded partial values distinct from the two exact endpoints.
  const percent = Number(Math.max(.1, Math.min(99.9, opening)).toFixed(1));
  const label = kind === 'partial' ? `${percent}% OPEN` : kind === 'unavailable' ? 'POSITION UNAVAILABLE' : kind.toUpperCase();
  return {kind, opening, available, label, shortLabel:available ? label : 'UNKNOWN', ...PALETTE[kind]};
}
