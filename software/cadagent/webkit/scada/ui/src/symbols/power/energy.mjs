/** Original generation, heat-transfer and renewable-energy illustrations.
 * Every quantity is supplied visual state. No engineering model lives here. */
import {clamp, prefix, steel, liquid, shadow, feet, pipe, wire, fan, indicator, damageArt} from './primitives.mjs';

const flowLane = (value, markup, extra = '') => `<g class="scada-power-flow-lane ${extra}" data-flowing="${clamp(value) > 0}" style="--scada-power-flow-opacity:${(.12 + clamp(value) * .0088).toFixed(3)}">${markup}</g>`;
const heatGlow = (x, y, rx, ry, heat) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="#ffae70" opacity="${(clamp(heat) * .0025).toFixed(3)}"/>`;
const ribs = (start, count, y, height, spacing = 6) => Array.from({length:count}, (_, i) => `<path d="M${start+i*spacing} ${y}v${height}" stroke="#a0c6d0" stroke-width="1.4"/>`).join('');

function gasTurbine(id, state) {
  const load = clamp(state.load, 60), heat = clamp(state.heat, 45);
  return `${shadow()}${feet([46,133],106,16)}
    ${flowLane(state.flow, pipe('M8 76H29', {width:14}) + pipe('M150 76H172V43', {width:13,warm:true}))}
    <path d="M27 51H60L76 40H107L123 52H152V101H122L105 111H73L59 100H27Z" fill="${steel(id)}" stroke="#b5d6df" stroke-width="1.6"/>
    <path d="M34 60H65L78 51H103L118 61H145V92H119L103 101H76L64 91H34Z" fill="#0b293c" stroke="#669cac"/>
    <path d="M20 77H163" stroke="#b5ccd3" stroke-width="4"/>
    <g class="scada-power-drive">${[42,52,62].map((x,i) => `<g class="scada-power-motion scada-power-blade-shimmer" style="animation-delay:-${i*.2}s"><path d="M${x} 60l5 16-5 15m5-31-5 16 5 15" fill="none" stroke="#80c1cd" stroke-width="3"/></g>`).join('')}
    ${fan(126,77,16)}</g>
    <g class="scada-power-combustion" data-lit="${state.active !== false && load > 0}" style="--scada-power-flame:${(.35 + load*.0065).toFixed(3)}"><path class="scada-power-motion scada-power-flame" d="M74 85Q89 77 88 58Q100 72 113 77Q99 82 109 94Q91 88 74 85Z" fill="#f0ae69" opacity=".86"/><path class="scada-power-motion scada-power-flame-core" d="M80 83q13-2 13-13l14 8-12 7Z" fill="#ffe0a2"/></g>
    ${heatGlow(93,79,28,24,heat)}
    <path d="M90 40V20h24" fill="none" stroke="#91bdc8" stroke-width="5"/>
    <path d="M106 14h18v12h-18Z" fill="#245b70" stroke="#9dcbd6"/>
    ${indicator(41,107,30)}<path d="M153 82h20" stroke="#ffd38a" stroke-width="3"/>`;
}

function heatRecovery(id, state) {
  const level = clamp(state.level,55);
  return `${shadow()}${feet([47,139],112,11)}
    <path d="M38 27H144V110H38Z" fill="${steel(id)}" stroke="#a7d1db" stroke-width="1.5"/>
    <path d="M46 36H136V102H46Z" fill="#0b293b" stroke="#75a8b8"/>
    <path d="M144 30h20V13h-17v13" fill="#3d6f83" stroke="#abd0d9"/>
    ${flowLane(state.primaryFlow, pipe('M8 81H45', {warm:true,width:13}) + `<path class="scada-power-motion scada-energy-flow" d="M47 80H133V43H157V14" fill="none" stroke="#e8b270" stroke-width="2.6" stroke-dasharray="4 7"/>`)}
    <g class="scada-power-thermal">${heatGlow(90,75,42,25,state.heat)}</g>
    <path d="M65 40V95H79V40H94V95H109V40H124V95" fill="none" stroke="#64a1b5" stroke-width="6"/>
    ${flowLane(state.secondaryFlow, `<path class="scada-power-motion scada-energy-flow" d="M12 115H65V40H79V95H94V40H109V95H124V28H82V10" fill="none" stroke="#80f7db" stroke-width="2.1" stroke-dasharray="4 8"/>`)}
    <path d="M64 28h68" stroke="#94cfdd" stroke-width="9"/>
    <rect x="72" y="23" width="54" height="10" rx="5" fill="#0a2d3c" stroke="#a3d6df"/>
    <rect x="75" y="26" width="${48*level/100}" height="4" rx="2" fill="#6cf1d4"/>
    ${indicator(113,106,27)}<path d="M52 42v58" stroke="#214456" stroke-width="2"/>`;
}

function condenser(id, state) {
  const level = clamp(state.level,55), fillY = 94 - level*.36;
  return `${shadow()}${feet([51,130],103,20)}
    <defs><clipPath id="${id}-condensate"><path d="M33 56Q33 45 45 45H139Q153 45 153 58V94Q153 106 139 106H45Q33 106 33 94Z"/></clipPath></defs>
    <path d="M29 55Q29 41 45 41H140Q158 41 158 58V95Q158 110 140 110H45Q29 110 29 96Z" fill="${steel(id)}" stroke="#aed4dc" stroke-width="1.7"/>
    <path d="M37 55H146V99H37Z" fill="#0c2e40" stroke="#659bad"/>
    <g clip-path="url(#${id}-condensate)"><rect x="34" y="${fillY}" width="118" height="48" fill="${liquid(id)}" opacity=".65"/><path class="scada-power-motion scada-power-waterline" d="M33 ${fillY}q11-3 22 0t22 0t22 0t22 0t23 0" fill="none" stroke="#8ff4df" stroke-width="1.7"/></g>
    ${flowLane(state.primaryFlow, pipe('M18 16H86V42', {warm:true,width:12}) + pipe('M101 108V124H169', {width:7}))}
    <path d="M8 68H136q10 0 10 10t-10 10H8" fill="none" stroke="#4a91af" stroke-width="7"/>
    ${flowLane(state.secondaryFlow, `<path class="scada-power-motion scada-energy-flow" d="M8 68H136q10 0 10 10t-10 10H8" fill="none" stroke="#96dff7" stroke-width="2.4" stroke-dasharray="4 8"/>`)}
    <g class="scada-power-thermal">${heatGlow(89,61,48,14,state.heat)}</g>
    ${state.damage === 'air-ingress' ? `<g class="scada-power-incident">${[62,82,103,124].map((x,i) => `<circle class="scada-power-motion scada-power-bubble" cx="${x}" cy="${86-i*5}" r="${2+i%2}" fill="none" stroke="#ffd38a" stroke-width="1.4"/>`).join('')}</g>` : ''}
    ${indicator(118,18,28)}`;
}

function deaerator(id, state) {
  const level = clamp(state.level,55), y = 103-level*.27;
  return `${shadow()}${feet([49,133],109,14)}
    <defs><clipPath id="${id}-tank"><rect x="28" y="66" width="130" height="42" rx="21"/></clipPath></defs>
    <rect x="26" y="64" width="134" height="47" rx="23" fill="${steel(id)}" stroke="#b2d5df" stroke-width="1.6"/>
    <rect x="34" y="71" width="118" height="32" rx="16" fill="#123647" stroke="#6da6b6"/>
    <g clip-path="url(#${id}-tank)"><rect x="29" y="${y}" width="128" height="45" fill="${liquid(id)}" opacity=".7"/><path class="scada-power-motion scada-power-waterline" d="M30 ${y}q12-3 24 0t24 0t24 0t24 0t22 0" fill="none" stroke="#8cf1d8" stroke-width="1.6"/></g>
    <path d="M65 64V31Q65 20 78 20H103Q116 20 116 33V64" fill="${steel(id)}" stroke="#abd3dc" stroke-width="1.5"/>
    <path d="M73 34H108V62H73Z" fill="#0c2c40" stroke="#76a8ba"/>
    ${[40,49,58].map(y => `<path d="M75 ${y}h31" stroke="#90cbd1" stroke-width="2"/>`).join('')}
    ${flowLane(state.flow, pipe('M10 38H65', {width:7}) + pipe('M90 111V123H170', {width:7}) + `<path class="scada-power-motion scada-power-drips" d="M79 36v24m10-24v24m10-24v24" stroke="#77efd1" stroke-width="1.6" stroke-dasharray="2 5"/>`)}
    <path d="M90 20V8h24" fill="none" stroke="#91c7d2" stroke-width="4"/>
    <g class="scada-power-thermal" style="opacity:${state.damage==='vent-blocked'?0:clamp(state.heat)/100}"><path class="scada-power-motion scada-power-heat-rise" d="M119 18q6-4 2-9m9 10q6-5 2-10" fill="none" stroke="#a9d5d8" stroke-width="2"/></g>
    ${indicator(129,42,29)}`;
}

function radiator(id, state) {
  return `${shadow()}${feet([41,139],108,15)}
    <path d="M27 29H151V111H27Z" fill="${steel(id)}" stroke="#a9cdd9" stroke-width="1.5"/>
    <path d="M36 36H141V102H36Z" fill="#14354a" stroke="#719aac"/>
    ${ribs(40,17,39,60,6)}
    <circle cx="89" cy="70" r="30" fill="#143349" stroke="#a3d2dc" stroke-width="2"/>
    <g class="scada-power-drive" data-drive-blocked="${state.damage==='fan-fault'}">${fan(89,70,25)}</g>
    <path d="M69 46l40 48m0-48L69 94" stroke="#456a7e" stroke-width="2" opacity=".6"/>
    ${flowLane(state.flow, pipe('M9 43H28V97H9', {width:7,warm:true}) + pipe('M151 43H171V97H151', {width:7}))}
    <g class="scada-power-thermal">${heatGlow(41,69,9,28,state.heat)}</g>
    ${indicator(111,112,27)}
    ${state.damage==='fan-fault'?'<path d="M85 51l8 12-8 9 12 15" fill="none" stroke="#ff9cbe" stroke-width="2.3"/>':''}`;
}

function regulator(id, state) {
  const opening = state.open === false ? 0 : clamp(state.opening,100), needle = -60+clamp(state.pressure,45)*1.2;
  return `${shadow()}${feet([54,128],101,22)}
    ${flowLane(opening > 0 ? state.flow : 0, pipe('M8 85H171', {width:13}))}
    <path d="M59 68H118V102H59Z" fill="${steel(id)}" stroke="#a9d0da" stroke-width="1.6"/>
    <path d="M64 73l25 12 24-12v23L89 85 64 96Z" fill="#163b4f" stroke="#7fc7cc"/>
    <path d="M90 75V43" stroke="#a5cbd5" stroke-width="5"/>
    <g transform="translate(0 ${-opening*.065})"><path d="M62 44a28 18 0 0 1 56 0Z" fill="#315f77" stroke="#a9cfd8" stroke-width="1.5"/><path d="M69 47h42" stroke="#96cbd8" stroke-width="3"/></g>
    <path d="M116 71h24V47" fill="none" stroke="#7db4c4" stroke-width="3"/>
    <circle cx="140" cy="32" r="16" fill="#0b2b3d" stroke="#afd8de" stroke-width="2"/>
    <path d="M140 32v-11" stroke="#8af6df" stroke-width="2" transform="rotate(${needle} 140 32)"/><circle cx="140" cy="32" r="2.5" fill="#b9dce0"/>
    <path d="M45 83v-9m0 9v9m87-9v-9m0 9v9" stroke="#a2d4dd" stroke-width="3"/>`;
}

function alternator(id, state) {
  const field = clamp(state.field,60), load = clamp(state.load,60);
  return `${shadow()}${feet([49,131],108,15)}
    <path d="M27 58L45 39H129L150 56V101L131 113H46L27 99Z" fill="${steel(id)}" stroke="#afd3dc" stroke-width="1.6"/>
    <path d="M51 49H130V102H51Z" fill="#0b2a3d" stroke="#699bb0"/>
    ${[55,65,75,85,95,105,115,125].map(x => `<path d="M${x} 50v12m0 27v12" stroke="#d6b884" stroke-width="4" opacity="${(.2+field*.008).toFixed(2)}"/>`).join('')}
    <ellipse cx="78" cy="76" rx="34" ry="21" fill="#20465b" stroke="#9ec6d3"/>
    <g class="scada-power-drive">${fan(78,76,18)}<path class="scada-power-motion scada-power-blade-shimmer" d="M89 63h36m-36 8h36m-36 9h36m-36 9h36" stroke="#8ebdca" stroke-width="2"/></g>
    <path d="M7 76H46" stroke="#afc7d0" stroke-width="8"/><path d="M8 76H45" stroke="#ffd38a" stroke-width="2" stroke-dasharray="5 3"/>
    ${flowLane(load, wire('M149 78H173V105'))}
    <path d="M107 39V22h27" fill="none" stroke="#7d9eaf" stroke-width="3"/>
    <path d="M112 22h19" stroke="#ffdb8b" stroke-width="2" opacity="${field/100}"/>
    <g class="scada-power-thermal">${heatGlow(98,78,38,26,state.heat)}</g>${indicator(115,111,27)}`;
}

function reservoir(id, state) {
  const level = clamp(state.level,55), y = 104-level*.58;
  const contamination = state.damage === 'contaminated';
  return `${shadow(89,126,79)}
    <defs><clipPath id="${id}-reservoir"><path d="M17 40H155L139 115H37Z"/></clipPath></defs>
    <path d="M12 35H161L144 120H32Z" fill="#33576b" stroke="#9ec3ce" stroke-width="1.5"/>
    <path d="M19 41H153L138 112H38Z" fill="#0e2a3b" stroke="#648e9e"/>
    <g clip-path="url(#${id}-reservoir)"><rect x="18" y="${y}" width="140" height="90" fill="${contamination?'#738d6c':liquid(id)}" opacity=".75"/>
    <path class="scada-power-motion scada-power-waterline" d="M18 ${y}q10-4 20 0t20 0t20 0t20 0t20 0t20 0t20 0" stroke="#97e6d8" fill="none" stroke-width="1.8"/>
    ${contamination ? '<g fill="#c7bc7b"><circle cx="52" cy="85" r="3"/><circle cx="78" cy="95" r="2.5"/><circle cx="114" cy="88" r="3"/></g>' : ''}</g>
    <path d="M124 37h24v83h-26Z" fill="${steel(id)}" stroke="#bad4dc" stroke-width="1.5"/>
    <path d="M130 46h11m-11 13h11m-11 13h11m-11 13h11m-11 13h11" stroke="#426c81" stroke-width="3"/>
    ${flowLane(state.flow, pipe('M141 104H171', {width:10}))}
    <path d="M22 31q9-18 18 0m7 0q12-21 23 0" fill="#294b5d" stroke="#638794" stroke-width="1.4"/>`;
}

function intakeGate(id, state) {
  const opening = state.open === false ? 0 : clamp(state.opening,100);
  return `${shadow()}<path d="M29 121V28H145V121" fill="none" stroke="#6f97aa" stroke-width="9"/>
    <path d="M29 27H145" stroke="#b3cfd9" stroke-width="3"/>
    <path d="M41 52H133V118H41Z" fill="#103344" stroke="#4d7e90"/>
    ${flowLane(opening, `<path class="scada-power-motion scada-energy-flow" d="M11 102H169m-158 10h158" fill="none" stroke="#58d7c6" stroke-width="3" stroke-dasharray="7 10"/>`)}
    <defs><clipPath id="${id}-gate-clip"><path d="M35 28H139V119H35Z"/></clipPath></defs>
    <g clip-path="url(#${id}-gate-clip)"><g transform="translate(0 ${-opening*.68})"><path d="M39 47H135V119H39Z" fill="${steel(id)}" stroke="#b1d2db" stroke-width="1.6"/><path d="M43 57h88m-88 16h88m-88 16h88m-88 16h88" stroke="#3b657d" stroke-width="4"/></g></g>
    <path d="M87 13V${50-opening*.23}" stroke="#b5d4da" stroke-width="5"/>
    <ellipse cx="87" cy="14" rx="24" ry="5" fill="#1c4255" stroke="#9ccbd4" stroke-width="2"/>
    <path d="M65 14h44M87 8v12" stroke="#a3d2d8" stroke-width="1.5"/>${indicator(117,8,28)}`;
}

function hydroTurbine(id, state, reversible = false) {
  const mode = reversible ? state.mode ?? 'generating' : 'generating';
  const flow = mode === 'stopped' ? 0 : clamp(state.flow,60);
  return `${shadow()}${feet([52,127],108,15)}
    ${flowLane(flow, pipe('M8 49H43V65', {width:13}) + pipe('M112 104V119H171', {width:13}), mode === 'pumping' ? 'scada-power-reverse-flow' : '')}
    <path d="M35 77Q35 42 78 41Q130 40 139 76Q146 111 107 115H69Q36 111 35 77Z" fill="${steel(id)}" stroke="#afd4dd" stroke-width="1.6"/>
    <path d="M45 76Q45 50 80 50Q124 50 129 77Q135 102 105 106H72Q46 102 45 76Z" fill="#123c50" stroke="#6fb5c2" stroke-width="2"/>
    <circle cx="89" cy="77" r="27" fill="#0c283a" stroke="#98cdd4" stroke-width="2"/>
    <g class="scada-power-drive" data-drive-blocked="${mode==='stopped'}">${fan(89,77,23,{reverse:mode==='pumping'})}</g>
    <path d="M89 50V13" stroke="#adcbd5" stroke-width="8"/><path class="scada-power-load-mark" d="M89 48V14" stroke="#ffd38a" stroke-width="2" stroke-dasharray="4 5"/>
    <path d="M69 12h40v14H69Z" fill="#264c64" stroke="#a4cbd7"/>
    ${reversible ? `<path d="M137 26h27l-6-5m6 5-6 5m6 9h-27l6-5m-6 5 6 5" fill="none" stroke="${mode==='pumping'?'#b1e7ff':'#ffd38a'}" stroke-width="2"/>` : ''}
    ${indicator(39,110,28)}`;
}

function heliostat(id, state) {
  const angle = -22 + clamp(state.position,50)*.44 + (state.damage==='misaligned'?14:0);
  const irradiance = clamp(state.irradiance,60);
  return `${shadow(90,125,65)}<path d="M78 84v38m24-39v39M62 123h56" stroke="#6c9aac" stroke-width="7"/>
    <path d="M67 99l21-21 25 24" fill="none" stroke="#a6cbd4" stroke-width="3"/>
    <g transform="rotate(${angle} 90 66)"><path d="M30 28H147L159 94H42Z" fill="${steel(id)}" stroke="#bddae1" stroke-width="1.5"/>
    <path d="M37 35H141L151 87H47Z" fill="#23546b" stroke="#91c5d6"/>
    ${[0,1,2,3].map(i => `<path d="M${38+i*26} 35l10 52" stroke="#a5d6e4" stroke-width="1.2"/>`).join('')}<path d="M42 60h104" stroke="#a5d6e4" stroke-width="1.2"/>
    <g class="scada-power-environment" style="opacity:${(.12+irradiance*.005).toFixed(2)}"><path class="scada-power-motion scada-power-solar-glint" d="M43 40l19 4 69 35-18 3Z" fill="#acf3f8"/></g>
    ${state.damage==='soiled'?'<path d="M63 48l13-3 15 8-8 10-17-4Zm48 22 13-4 11 8-10 8-12-4Z" fill="#8c8e70" opacity=".8"/>':''}</g>
    <g class="scada-power-environment" style="opacity:${irradiance/100}"><path d="M14 8L54 37m-17-30 41 29m-18-29 40 29" stroke="#ffe7a7" stroke-width="1.5"/><path class="scada-power-motion scada-power-solar-glint" d="M121 40l45-27m-37 36 42-25" stroke="#a5f4f5" stroke-width="1.4" stroke-dasharray="6 5"/></g>
    ${indicator(116,104,26)}`;
}

function solarReceiver(id, state) {
  return `${shadow()}<path d="M68 45H112L128 123H52Z" fill="${steel(id)}" stroke="#a8ccd9" stroke-width="1.5"/>
    <path d="M78 48L66 119M101 48l13 71" stroke="#426b80" stroke-width="4"/>
    <path d="M63 18H117V49H63Z" fill="#203c4f" stroke="#aac9d5" stroke-width="1.5"/>
    <path d="M70 22H110V45H70Z" fill="#b17552" stroke="#edc68e"/>
    ${[75,83,91,99,107].map(x => `<path d="M${x} 24v18" stroke="#ffe2a0" stroke-width="2" opacity="${(.25+clamp(state.heat)*.0075).toFixed(2)}"/>`).join('')}
    <g class="scada-power-thermal">${heatGlow(90,33,28,21,state.heat)}</g>
    ${flowLane(state.flow, pipe('M9 120H55V53H70V45', {width:5}) + pipe('M111 45V58H135V120H171', {width:5,warm:true}))}
    <path d="M10 78L63 33m-45 74 48-69m101 37-49-42m38 70-39-66" stroke="#ffe2a1" stroke-width="1.3" opacity=".45"/>
    ${indicator(77,98,27)}`;
}

function trough(id, state) {
  const angle = -15 + clamp(state.position,50)*.3, irradiance = clamp(state.irradiance,60);
  const radians=angle*Math.PI/180;
  const rotated=(x,y)=>({x:90+(x-90)*Math.cos(radians)-(y-75)*Math.sin(radians),y:75+(x-90)*Math.sin(radians)+(y-75)*Math.cos(radians)});
  const inlet=rotated(18,48),outlet=rotated(161,48);
  return `${shadow()}${feet([41,140],103,20)}
    <g transform="rotate(${angle} 90 75)"><path d="M24 44Q87 122 153 44L163 78Q91 140 14 78Z" fill="${steel(id)}" stroke="#b3d6df" stroke-width="1.6"/>
    <path d="M26 46Q90 109 151 46M18 78Q88 130 159 78" fill="none" stroke="#d0e5e8" stroke-width="1.3"/>
    ${[45,69,94,119,143].map(x => `<path d="M${x} 64v29" stroke="#53849a" stroke-width="1.4"/>`).join('')}
    <path d="M18 48H161" stroke="#285267" stroke-width="7"/><path d="M18 48H161" stroke="#e7bd83" stroke-width="4" opacity="${.12+clamp(state.heat,45)*.007}"/>
    ${flowLane(state.flow, `<path class="scada-power-motion scada-energy-flow" d="M18 48H161" fill="none" stroke="#ffd38a" stroke-width="2.2" stroke-dasharray="4 8"/>`)}
    <g class="scada-power-environment" style="opacity:${(.2+irradiance*.006).toFixed(2)}"><path class="scada-power-motion scada-power-solar-glint" d="M36 68l23-10m13 27 18-30m14 30 16-28m16 11 14-10" stroke="#b5edf2" stroke-width="1.5"/></g>
    ${state.damage==='soiled'?'<path d="M57 76l18 8 6 12-17-5Zm53 10 14-10 12-1-7 13Z" fill="#9a936b" opacity=".75"/>':''}</g>
    <g class="scada-power-environment" style="opacity:${irradiance/100}"><path d="M41 8v25m22-25v28m23-28v28m22-28v28m22-28v25" stroke="#ffe3a1" stroke-width="1.4"/></g>
    ${flowLane(state.flow, pipe(`M8 49H${inlet.x-5}V${inlet.y}H${inlet.x}`, {width:5}) + pipe(`M${outlet.x} ${outlet.y}H${outlet.x+4}V49H172`, {width:5,warm:true}))}
    ${indicator(120,106,28)}`;
}

function tidal(id, state) {
  const direction = ['flood','ebb','stopped'].includes(state.direction) ? state.direction : 'flood';
  return `${shadow(90,128,59)}<path d="M89 74V124m-25 1h50" stroke="#658fa5" stroke-width="8"/>
    <path d="M81 78h16v43H81Z" fill="${steel(id)}" stroke="#a1c4d3"/>
    <path d="M79 56H118Q137 67 118 78H79Z" fill="${steel(id)}" stroke="#a8ced8" stroke-width="1.6"/>
    <circle cx="79" cy="67" r="29" fill="#113647" stroke="#426e83" stroke-width="2"/>
    <g class="scada-power-drive" data-drive-blocked="${direction==='stopped'}">${fan(79,67,24,{reverse:direction==='ebb'})}</g>
    <g class="scada-power-environment scada-power-current" data-current="${clamp(state.current,60)>0}" style="--scada-power-current-duration:${(5-clamp(state.current,60)*.04).toFixed(2)}s" data-direction="${direction}"><path class="scada-power-motion scada-power-current-lines" d="M12 36h41m-41 63h41m78-63h37m-37 63h37" fill="none" stroke="#61c4d3" stroke-width="1.5" stroke-dasharray="8 8" opacity=".65"/></g>
    ${flowLane(direction==='stopped'?0:clamp(state.load,60),wire('M118 78v38h45'))}
    <path d="M18 117q8-5 16 0t16 0m85 5q8-4 16 0t16 0" fill="none" stroke="#4a6e7e" stroke-width="2"/>`;
}

function waveConverter(id, state) {
  const wave = clamp(state.wave,60), load = clamp(state.load,60);
  return `${shadow(90,128,63)}
    <path d="M18 91H163V128H18Z" fill="#154356" opacity=".45"/>
    <g class="scada-power-environment" data-wave="${wave>0}" style="--scada-power-wave-height:${(wave*.045).toFixed(2)}px;--scada-power-wave-duration:${(4.5-wave*.026).toFixed(2)}s">
      <path class="scada-power-motion scada-power-ocean-wave" d="M10 89q10-5 20 0t20 0t20 0t20 0t20 0t20 0t20 0t20 0" fill="none" stroke="#8bdedc" stroke-width="2"/>
      <g class="scada-power-motion scada-power-buoy"><path d="M49 69Q86 50 126 69V87Q87 108 49 87Z" fill="${steel(id)}" stroke="#afd4dc" stroke-width="1.5"/><ellipse cx="87" cy="69" rx="38" ry="14" fill="#397d88" stroke="#b4dedc"/>
      <path d="M62 69h50" stroke="#80e0cf" stroke-width="3"/><path d="M86 58V26" stroke="#abcdd5" stroke-width="7"/>
      <path d="M73 20h27v25H73Z" fill="#153a50" stroke="#94becf"/><path d="M79 25h15v15H79Z" fill="#224f63" stroke="#77a4b7"/>
      <path class="scada-power-drive" d="M86 28v10" stroke="#ffd58a" stroke-width="4" opacity="${(.2+load*.008).toFixed(2)}"/></g>
    </g>
    <path d="M86 92V127" stroke="#7ca6b7" stroke-width="4"/>
    <path d="M56 91L35 126m82-35 22 35" stroke="#9cb6bd" stroke-width="1.5" stroke-dasharray="3 2"/>
    <path d="M77 128h18" stroke="#b3c8c7" stroke-width="4"/>
    <path d="M99 39h23V115h43" fill="none" stroke="#7b9cab" stroke-width="3"/>
    ${flowLane(load, wire('M99 39h23V115h43'))}
    ${state.damage==='mooring-damage'?'<path d="M40 116l7-1m-2 6 7-1" stroke="#ff9dbe" stroke-width="2.5"/>':''}`;
}

const DRAWINGS = Object.freeze({
  'gas-turbine': gasTurbine,
  'heat-recovery-steam-generator': heatRecovery,
  'surface-condenser': condenser,
  deaerator,
  'cooling-radiator': radiator,
  'fuel-pressure-regulator': regulator,
  alternator,
  reservoir,
  'intake-gate': intakeGate,
  'hydro-turbine': hydroTurbine,
  'reversible-pump-turbine': (id,state) => hydroTurbine(id,state,true),
  heliostat,
  'solar-receiver': solarReceiver,
  'parabolic-trough': trough,
  'tidal-turbine': tidal,
  'wave-energy-converter': waveConverter,
});

const ANCHORS = Object.freeze({
  'gas-turbine': {x:125,y:75,radius:24},
  'heat-recovery-steam-generator': {x:91,y:71,radius:35},
  'surface-condenser': {x:104,y:77,radius:33},
  deaerator: {x:122,y:87,radius:28},
  'cooling-radiator': {x:118,y:79,radius:31},
  'fuel-pressure-regulator': {x:94,y:88,radius:24},
  alternator: {x:105,y:77,radius:33},
  reservoir: {x:136,y:93,radius:24},
  'intake-gate': {x:98,y:81,radius:29},
  'hydro-turbine': {x:112,y:88,radius:25},
  'reversible-pump-turbine': {x:112,y:88,radius:25},
  heliostat: {x:102,y:66,radius:30},
  'solar-receiver': {x:91,y:35,radius:25},
  'parabolic-trough': {x:108,y:78,radius:30},
  'tidal-turbine': {x:79,y:67,radius:26},
  'wave-energy-converter': {x:89,y:71,radius:29},
});

export function renderEnergyArt(type, {id = 'scada-energy', state = {}} = {}) {
  if (!Object.hasOwn(DRAWINGS,type)) return '';
  const instance = prefix(id), speed = clamp(state.speed,60);
  const damage = typeof state.damage === 'string' && /^[a-z][a-z0-9-]*$/.test(state.damage) ? state.damage : 'none';
  const driveBlocked = /bearing-fault|blade-damage|fan-fault|drive-fault|pto-fault|stuck|obstructed/.test(damage);
  let anchor=ANCHORS[type];
  if(type==='deaerator'&&damage==='vent-blocked')anchor={x:110,y:16,radius:12};
  if(type==='gas-turbine'&&damage==='fuel-leak')anchor={x:107,y:38,medium:'gas'};
  if(type==='fuel-pressure-regulator'&&damage==='leaking')anchor={x:110,y:79,medium:'gas'};
  if(type==='intake-gate')anchor=damage==='obstructed'?{x:87,y:108}:damage==='stuck'?{x:87,y:23}:{x:87,y:Math.max(40,83-(state.open===false?0:clamp(state.opening,100))*.5)};
  return `<g class="scada-power-art scada-energy-art" data-power-type="${type}" data-power-speed-zero="${speed===0}" data-power-drive-blocked="${driveBlocked}" style="--scada-power-cycle:${(4.6-speed*.036).toFixed(2)}s;--scada-power-load:${clamp(state.load,60)/100}">
    ${DRAWINGS[type](instance,state)}
    ${damageArt(damage,anchor)}
  </g>`;
}

export const ENERGY_ART_TYPES = Object.freeze(Object.keys(DRAWINGS));
