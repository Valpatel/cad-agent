/** Shared SVG geometry for the original power-sector illustrations.
 * The public component wrapper owns validation, definitions, gauges and labels.
 * These helpers return markup only. They have no clock, DOM or model state. */

export const clamp = (value, fallback = 0) => Number.isFinite(value)
  ? Math.max(0, Math.min(100, value)) : fallback;
export const prefix = value => String(value).replace(/[^a-zA-Z0-9_-]/g, '-');
export const steel = id => `url(#${id}-steel)`;
export const liquid = id => `url(#${id}-liquid)`;

export function shadow(x = 90, y = 125, rx = 68) {
  return `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="4.5" fill="#020d18" opacity=".72"/>`;
}

export function feet(xs, y = 104, height = 17) {
  return xs.map(x => `<path d="M${x} ${y}v${height}m-7 0h14" fill="none" stroke="#6d9dad" stroke-width="4" stroke-linecap="round"/>`).join('');
}

export function pipe(path, {flow = true, warm = false, width = 7, className = 'scada-energy-flow'} = {}) {
  return `<path d="${path}" fill="none" stroke="#183c50" stroke-width="${width + 3}" stroke-linejoin="round"/>
    <path d="${path}" fill="none" stroke="#80adbd" stroke-width="${width}" stroke-linejoin="round"/>
    ${flow ? `<path class="${className} scada-power-motion${warm ? ' scada-power-warm-flow' : ''}" d="${path}" fill="none" stroke="${warm ? '#ffd38a' : '#65f6d0'}" stroke-width="2" stroke-dasharray="4 8"/>` : ''}`;
}

export function wire(path, {flow = true, className = 'scada-electrical-flow', width = 3} = {}) {
  return `<path d="${path}" fill="none" stroke="#8d9eaa" stroke-width="${width}" stroke-linejoin="round"/>
    ${flow ? `<path class="${className} scada-power-motion" d="${path}" fill="none" stroke="#ffd38a" stroke-width="1.6" stroke-dasharray="3 7"/>` : ''}`;
}

export function fan(x, y, radius, {reverse = false, className = 'scada-power-rotor'} = {}) {
  return `<g class="scada-power-motion ${className}${reverse ? ' scada-power-reverse' : ''}" style="transform-origin:${x}px ${y}px">
    ${[0, 60, 120, 180, 240, 300].map(angle => `<path d="M${x} ${y-2}Q${x+radius*.18} ${y-radius*.86} ${x+radius*.9} ${y-radius*.44}L${x+radius*.98} ${y-radius*.18}Q${x+radius*.33} ${y-radius*.5} ${x+radius*.12} ${y+radius*.12}Z" fill="#8bdadf" stroke="#b7eaf0" stroke-width=".6" transform="rotate(${angle} ${x} ${y})"/>`).join('')}
    <circle cx="${x}" cy="${y}" r="${Math.max(2.5, radius * .2)}" fill="#235067" stroke="#9bd4dd" stroke-width="1.1"/>
  </g>`;
}

export function indicator(x, y, width = 25, {amber = false} = {}) {
  return `<g class="scada-power-indicator">
    <rect x="${x}" y="${y}" width="${width}" height="15" rx="2" fill="#082633" stroke="#77a8bc"/>
    <path d="M${x + 4} ${y + 5}h${width - 8}m-${width - 8} 5h${Math.max(5, width - 14)}" stroke="${amber ? '#ffd38a' : '#75f2ce'}" stroke-width="1.5"/>
    <circle class="scada-power-monitor" cx="${x + width - 4}" cy="${y + 11}" r="1.5" fill="#8affd6"/>
  </g>`;
}

export function insulator(x, y, height = 38, width = 10, {horizontal = false} = {}) {
  const count = Math.max(3, Math.floor(height / 7));
  const body = `<path d="M${x} ${y}v${height}" stroke="#7299a7" stroke-width="${width * .55}"/>
    ${Array.from({length:count}, (_, index) => `<ellipse cx="${x}" cy="${y + 3 + index * (height - 6) / Math.max(1,count - 1)}" rx="${width / 2}" ry="2" fill="#4d8294" stroke="#a5cdd3" stroke-width=".8"/>`).join('')}`;
  return horizontal ? `<g transform="rotate(-90 ${x} ${y})">${body}</g>` : body;
}

/** Damage stays physically anchored to the equipment. Production gating is
 * independent of incident motion, which can persist after a drive trips. */
export function damageArt(mode, {x = 92, y = 70, radius = 35, poolY = 123, medium = 'liquid'} = {}) {
  const value = typeof mode === 'string' && /^[a-z][a-z0-9-]*$/.test(mode) ? mode : 'none';
  if (value === 'none') return '';
  const crack = /ruptur|fractur|crack|broken|blade-damage|embankment-damage|insulation|flashover/.test(value);
  const leak = /leak|ruptur/.test(value) && medium !== 'gas';
  const heat = /heat|burn|short|flashover|overload/.test(value);
  const wear = /worn|corrod|deposit|erosion|bearing/.test(value);
  const blockage = /jam|block|seiz|obstruct/.test(value);
  const electrical = /short|flashover|insulation|arc/.test(value);
  const unavailable = /signal|sensor|offline|failed|control-fault/.test(value);
  return `<g class="scada-power-damage" data-power-damage="${value}">
    ${wear ? `<g class="scada-power-wear" fill="#a77d57" stroke="#d2aa7e" stroke-width=".9"><path d="M${x-17} ${y-8}l6-3 5 5-2 6-7-1Z"/><path d="M${x+15} ${y+12}l5-2 4 5-3 4-6-2Z"/><path d="M${x-14} ${y-7}l5 4m-5 0 5 3m27 15-4-4" fill="none" stroke="#674d40"/></g>` : ''}
    ${crack ? `<path class="scada-power-crack" d="M${x-8} ${y-18}l9 12-7 8 13 7-5 13m-1-26 10-2m-8 15 10 4" fill="none" stroke="#ffa6c4" stroke-width="2.2" stroke-linejoin="round"/>` : ''}
    ${blockage ? `<g class="scada-power-blockage" fill="#827965" stroke="#d5b99c" stroke-width="1"><path d="M${x-12} ${y-3}l6-9 10 2 4 11-9 6Z"/><path d="M${x+3} ${y+2}l6-8 10 3 1 10-12 3Z"/><path d="M${x-15} ${y+9}l4-8 8 3 1 8Z"/></g>` : ''}
    ${leak ? `<g class="scada-power-incident scada-power-leak"><path d="M${x+5} ${y+4}l5-4 4 7" fill="none" stroke="#ffa6c4" stroke-width="2"/><path class="scada-power-motion scada-power-drips" d="M${x+12} ${y+8}q16 17 13 ${poolY-y-8}m-9-${poolY-y-11}q14 18 10 ${poolY-y-11}" fill="none" stroke="#7cf5e3" stroke-width="2" stroke-dasharray="3 5"/><ellipse cx="${x+26}" cy="${poolY}" rx="17" ry="2.6" fill="#58bdb6" opacity=".8"/></g>` : ''}
    ${heat ? `<g class="scada-power-incident scada-power-heat"><ellipse cx="${x}" cy="${y}" rx="${radius}" ry="${radius*.7}" fill="#f6a262" opacity=".11"/><path class="scada-power-motion scada-power-heat-rise" d="M${x-17} ${Math.max(40,y-radius*.65)}q-6-8 0-16t0-13m16 26q7-10 0-18t0-12m15 32q-6-8 0-16t0-10" fill="none" stroke="#ffd0a0" stroke-width="2" opacity=".8"/></g>` : ''}
    ${medium==='gas'&&/leak/.test(value)?`<g class="scada-power-incident"><path d="M${x-5} ${y+4}l5-6 5 6" fill="none" stroke="#ffb2cd" stroke-width="2"/><path class="scada-power-motion scada-power-gas-plume" d="M${x} ${y-1}q-6-8 0-15m8 16q7-9 0-18" fill="none" stroke="#d5d0ad" stroke-width="2.5" opacity=".75"/></g>`:''}
    ${electrical ? `<path class="scada-power-incident scada-power-arc" d="M${x-18} ${y-7}l10 3-4 8 12-3-3 9 16-4" fill="none" stroke="#ffe9ae" stroke-width="2.2"/>` : ''}
    ${unavailable ? `<g class="scada-power-invalid"><path d="M${x-13} ${y-10}h26v20h-26Z" fill="#412738" stroke="#ff94b8"/><path d="M${x-7} ${y-5}l14 10m0-10-14 10" stroke="#ffc6d9" stroke-width="1.6"/></g>` : ''}
    ${/foul/.test(value) ? `<g fill="#8e9272" stroke="#bec099" stroke-width=".7" opacity=".9"><path d="M${x-19} ${y-13}l11-5 10 7 12-3 9 8-7 12-13-4-11 5-12-8Z"/><circle cx="${x-8}" cy="${y-3}" r="2"/><circle cx="${x+9}" cy="${y+6}" r="3"/></g>` : ''}
    ${value==='contact-wear' ? `<g fill="#4f3442" stroke="#e6b19c" stroke-width=".9"><circle cx="${x-6}" cy="${y-3}" r="3"/><circle cx="${x+3}" cy="${y+4}" r="2.5"/><path d="M${x-11} ${y+9}l7-3 9 4" fill="none" stroke-width="2"/></g>` : ''}
    ${value==='degraded' ? `<path d="M${x-14} ${y-12}l28 9m-28 2 28 9m-28 2 28 9" fill="none" stroke="#d4af8b" stroke-width="2"/>` : ''}
    ${value==='stuck' ? `<g fill="none" stroke="#ffc1d4" stroke-width="2"><rect x="${x-8}" y="${y-1}" width="17" height="13" rx="2" fill="#6b3b50"/><path d="M${x-5} ${y-1}v-6a5 5 0 0 1 10 0v6"/></g>` : ''}
    ${value==='cavitating' ? `<g class="scada-power-incident" fill="none" stroke="#b2efef" stroke-width="1.3">${[[-13,-8,4],[4,-13,3],[14,5,5],[-7,12,3]].map(([dx,dy,r])=>`<circle class="scada-power-motion scada-power-bubble" cx="${x+dx}" cy="${y+dy}" r="${r}"/>`).join('')}</g>` : ''}
    ${value==='winding-fault' ? `<path d="M${x-16} ${y-7}q4-11 8 0t8 0m3 3q4 11 8 0m-15-4 7 10m-8 0 8-10" fill="none" stroke="#ffc6a1" stroke-width="2"/>` : ''}
    ${/drive-fault|pto-fault/.test(value) ? `<g fill="none" stroke="#ffa8c7" stroke-width="2"><circle cx="${x}" cy="${y}" r="11" stroke-dasharray="5 3"/><path d="M${x-7} ${y-7}l6 6-3 4 7 5m-2-7 6 5"/></g>` : ''}
    ${value==='cooling-loss' ? `<g fill="none" stroke="#ffc7ac" stroke-width="2"><path d="M${x-16} ${y-10}h30m-30 8h30m-30 8h30m-30 8h30" stroke="#6e7e8d"/><path d="M${x-10} ${y-13}l20 31m-20 0 20-31"/></g>` : ''}
    ${value==='drift' ? `<g fill="none" stroke-width="2"><path d="M${x-13} ${y+10}l11-22" stroke="#72e1d0"/><path d="M${x-13} ${y+10}l28-10" stroke="#ffbd9e"/><path d="M${x-3} ${y-10}q14-3 17 10" stroke="#ffbd9e" stroke-dasharray="2 3"/></g>` : ''}
    ${value==='comms-loss' ? `<g fill="none" stroke="#ffb3cc" stroke-width="2"><path d="M${x-17} ${y+4}q8-13 16-11m5 1q9 3 12 10m-25 5q4-7 9-7m5 1 5 6m-16 5 4-4m-3-14 5 6-4 5"/></g>` : ''}
    ${value==='power-loss' ? `<g><rect x="${x-17}" y="${y-10}" width="34" height="23" rx="3" fill="#07151e" stroke="#607588"/><path d="M${x-5} ${y+1}h10m-5-5v10" stroke="#7b8d9b" stroke-width="1.5"/></g>` : ''}
  </g>`;
}
