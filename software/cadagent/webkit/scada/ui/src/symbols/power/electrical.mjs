/** Original electrical power art. Conceptual mechanisms, not wiring instructions.
 * State normalization, accessible descriptions and numeric readings belong to
 * the component registry/wrapper. Current marks never bridge open contacts. */
import {clamp,prefix,steel,shadow,feet,wire,indicator,insulator,damageArt} from './primitives.mjs';

function circuit(conducting, markup, extra='') {
  return `<g class="scada-power-circuit ${extra}" data-conducting="${Boolean(conducting)}">${markup}</g>`;
}
function terminal(x,y) { return `<circle cx="${x}" cy="${y}" r="4" fill="#143348" stroke="#c9d9df" stroke-width="1.8"/>`; }
function ground(x,y) { return `<path d="M${x} ${y}v8m-12 0h24m-8 5h-8m3 5h2" fill="none" stroke="#b0cbd2" stroke-width="2"/>`; }
function coil(x,y,width=29,height=35) {
  return `<path d="M${x} ${y}v${height}" stroke="#688ea0" stroke-width="${width*.48}"/>
    ${Array.from({length:6},(_,i)=>`<ellipse cx="${x}" cy="${y+3+i*(height-6)/5}" rx="${width/2}" ry="3.5" fill="none" stroke="#cdb48c" stroke-width="2.2"/>`).join('')}`;
}
function sine(x,y,width=29) { return `<path d="M${x} ${y}q${width/4}-${width/2} ${width/2} 0t${width/2} 0" fill="none" stroke="#a5efe2" stroke-width="2"/>`; }
function dc(x,y,width=29) { return `<path d="M${x} ${y-4}h${width}m-${width} 8h${width}" fill="none" stroke="#ffd38a" stroke-width="2" stroke-dasharray="${width} 0 ${width/5} 3"/>`; }
function hot(x,y,heat) { return `<ellipse class="scada-power-thermal" cx="${x}" cy="${y}" rx="29" ry="23" fill="#e8a365" opacity="${clamp(heat)*.0024}"/>`; }

function converter(id,state,rectifier=false) {
  const allowedDirections=rectifier?['forward','idle']:['forward','reverse','idle'];
  const direction=allowedDirections.includes(state.direction)?state.direction:state.direction===undefined?'forward':'idle';
  const load=clamp(state.load,60), conducting=direction!=='idle' && load>0 && !['semiconductor-fault','cooling-loss'].includes(state.damage);
  return `${shadow()}${feet([44,135],111,12)}
    <path d="M30 35L45 23H135L151 35V113H30Z" fill="${steel(id)}" stroke="#b0d0dc" stroke-width="1.6"/>
    <path d="M38 39H143V102H38Z" fill="#103047" stroke="#80acbd"/>
    <path d="M44 96L137 46" stroke="#c1d4de" stroke-width="1.7"/>
    ${rectifier?sine(49,60):dc(49,58)}${rectifier?dc(105,85):sine(105,85)}
    <g class="scada-power-conversion" data-conducting="${conducting}" style="opacity:${.25+load*.0075}"><path class="scada-power-motion scada-power-convert-pulse" d="M77 77l12-7 12 7-12 7Z" fill="#ffd38a" stroke="#ffe9b8"/></g>
    ${circuit(conducting,wire('M8 66H30')+wire('M151 66H173'),direction==='reverse'?'scada-power-reverse-flow':'')}
    <path d="M48 108h22m8 0h22m8 0h22" stroke="#1a3c52" stroke-width="3"/>${indicator(77,25,28)}
    ${state.damage==='semiconductor-fault'?'<path d="M83 68l8 8-7 8m10-17-4 9 9 8" fill="none" stroke="#ff9fbe" stroke-width="2"/>':''}`;
}

function hvBreaker(id,state) {
  const closed=state.open!==true, load=clamp(state.load,60);
  return `${shadow()}<path d="M38 118H141m-89-2V83m75 33V83" stroke="#8cadbb" stroke-width="5"/>
    ${insulator(51,38,46,15)}${insulator(128,38,46,15)}
    <path d="M36 24H142V43H36Z" fill="${steel(id)}" stroke="#b7d6dc" stroke-width="1.5"/>
    <path d="M45 29H134V38H45Z" fill="#112c3e" stroke="#709cae"/>
    ${circuit(closed&&load>0,wire('M8 33H63')+wire('M117 33H172')+(closed?wire('M63 33H117'):'<path d="M63 33H82m17 0h18" stroke="#aac7d2" stroke-width="3"/>'))}
    ${closed?'': '<path d="M82 29v8m17-8v8" stroke="#ffd38a" stroke-width="2"/>'}
    <path d="M88 43v48" stroke="#91b6c5" stroke-width="3"/>
    <path d="M68 85H108V117H68Z" fill="#2d526a" stroke="#a2c3d2" stroke-width="1.5"/>${indicator(75,94,26)}
    <path d="M42 86h18m59 0h18" stroke="#b3d0d9" stroke-width="3"/>`;
}

function disconnect(id,state,earthing=false) {
  const closed=state.open!==true, load=earthing?0:clamp(state.load,60);
  const start={x:51,y:48}, end=earthing?{x:128,y:90}:{x:128,y:48};
  const tip=closed?end:{x:98,y:18};
  return `${shadow()}<path d="M27 121H151m-112-3V98m100 20V98" stroke="#91afbc" stroke-width="4"/>
    ${insulator(51,52,48,16)}${earthing?'':insulator(128,52,48,16)}
    ${circuit(!earthing&&closed&&load>0,wire('M8 48H51')+(earthing?'':wire('M128 48H173')))}
    <path d="M${start.x} ${start.y}L${tip.x} ${tip.y}" stroke="#a9c9d2" stroke-width="6" stroke-linecap="round"/>
    ${circuit(!earthing&&closed&&load>0,closed?wire(`M51 48L${end.x} ${end.y}`):'')}
    ${terminal(start.x,start.y)}${terminal(end.x,end.y)}
    ${earthing?`<path d="M128 90v12" stroke="#a9c8d0" stroke-width="4"/>${ground(128,102)}`:''}
    <path d="M51 99h45v12" fill="none" stroke="#7f9dad" stroke-width="3"/><circle cx="96" cy="112" r="7" fill="#173a50" stroke="#b0cbd5" stroke-width="2"/>
    <path d="M89 112h14m-7-7v14" stroke="#9dc7d2" stroke-width="1.5"/>`;
}

/** Window CT: primary conductor passes through a separate toroidal core;
 * the small paired leads are the secondary observation path, not a feeder. */
function currentTransformer(id,state) {
  const value=clamp(state.value,42),connected=state.connected!==false&&!['broken','insulation-fault'].includes(state.damage);
  const sensing=connected&&value>0;
  const conductor=d=>`<path d="${d}" fill="none" stroke="#49372b" stroke-width="12" stroke-linecap="square"/><path d="${d}" fill="none" stroke="#cda16c" stroke-width="9" stroke-linecap="square"/><path d="${d}" fill="none" stroke="#f1d6a6" stroke-width="1.4"/>`;
  return `${shadow(90,126,65)}
    <path d="M56 111H123V120H56Z" fill="${steel(id)}" stroke="#9dbfca" stroke-width="1.4"/>
    <path d="M66 104v10m46-10v10" stroke="#83aabb" stroke-width="6"/>
    <g class="scada-ct-primary scada-ct-primary-rear">${conductor('M90 59L167 26')}${circuit(sensing,wire('M90 59L167 26',{width:0}))}</g>
    <path class="scada-ct-core" d="M90 19a36 40 0 1 1 0 80a36 40 0 1 1 0-80Zm0 17a19 23 0 1 0 0 46a19 23 0 1 0 0-46Z" fill="${steel(id)}" fill-rule="evenodd" stroke="#a9d1dc" stroke-width="1.6"/>
    <path d="M90 25a30 34 0 1 1 0 68a30 34 0 1 1 0-68" fill="none" stroke="#284f65" stroke-width="7"/>
    <path d="M90 34a21 25 0 1 1 0 50a21 25 0 1 1 0-50" fill="none" stroke="#0d2b3d" stroke-width="2.4"/>
    <g class="scada-ct-secondary-winding" fill="none" stroke="#deb77f" stroke-width="2.5" stroke-linecap="round">
      ${[28,42,56,70,84].map(angle=>`<path d="M84 22q6-4 12 0v14q-6 4-12 0Z" transform="rotate(${angle} 90 59)"/>`).join('')}
    </g>
    <g class="scada-power-magnetic" data-conducting="${sensing}" style="opacity:${.18+value*.006}"><path class="scada-power-motion scada-power-field-pulse scada-ct-flux" d="M64 40a29 33 0 0 0 16 50" fill="none" stroke="#77e9dd" stroke-width="1.4" stroke-dasharray="3 5"/></g>
    <g class="scada-ct-primary scada-ct-primary-front">${conductor('M13 92L90 59')}${circuit(sensing,wire('M13 92L90 59',{width:0}))}</g>
    <g class="scada-ct-secondary" fill="none" stroke="#83b9cb" stroke-width="2"><path d="M117 76H145V103H167M114 83H137V113H167"/></g>
    <g class="scada-power-sensing" data-connected="${connected}"><path class="scada-power-motion scada-power-signal" d="M117 76H145V103H167M114 83H137V113H167" fill="none" stroke="#77ead8" stroke-width="1.2" stroke-dasharray="3 5"/></g>
    ${terminal(167,103)}${terminal(167,113)}
    <text class="scada-power-detail-label" x="19" y="110">P1</text><text class="scada-power-detail-label" x="147" y="17">P2</text>
    <text class="scada-power-detail-label" x="144" y="126">S1 · S2</text>`;
}

function voltageTransformer(id,state) {
  const connected=state.connected!==false && !['broken','insulation-fault'].includes(state.damage);
  const value=clamp(state.value,42);
  return `${shadow()}<path d="M52 121H127m-59-2V90m44 29V90" stroke="#87a7b7" stroke-width="4"/>
    ${insulator(90,18,67,29)}<path d="M66 85H114V110H66Z" fill="${steel(id)}" stroke="#b5d5dc" stroke-width="1.5"/>
    ${circuit(connected,wire('M8 18H172'))}<path d="M90 18v-5" stroke="#b5d6de" stroke-width="4"/>
    <path d="M111 96h34v21" fill="none" stroke="#78aabd" stroke-width="2"/>
    <g class="scada-power-sensing" data-connected="${connected}"><rect x="126" y="99" width="39" height="23" rx="3" fill="#0c283b" stroke="#86b9c9"/>
      <path d="M132 116h26M132 104v12" fill="none" stroke="#668ea0" stroke-width="1"/>
      <path class="scada-power-motion scada-power-signal" d="M133 114l6-${(value*.11).toFixed(1)} 7 ${(value*.055).toFixed(1)} 10-${(value*.075).toFixed(1)}" fill="none" stroke="#79f1d1" stroke-width="1.8"/>
    </g>`;
}

function arrester(id,state) {
  const stress=clamp(state.stress,5);
  return `${shadow(90,128,56)}<path d="M58 122H122m-44-1V105m24 16V105" stroke="#89a9b7" stroke-width="4"/>
    ${insulator(90,19,86,34)}<path d="M90 18V9H142" fill="none" stroke="#b3cbd3" stroke-width="3"/>
    <path d="M90 104v10h48" fill="none" stroke="#a9c6d0" stroke-width="3"/>${ground(138,105)}
    <g class="scada-power-stress" data-stressed="${stress>15}" style="opacity:${.1+stress*.009}"><path class="scada-power-motion scada-power-protection-pulse" d="M87 27l8 13-9 14 9 16-9 15 7 14" fill="none" stroke="#ffe1a0" stroke-width="2.2"/></g>
    <circle cx="118" cy="116" r="5" fill="#163547" stroke="#92c5d2"/><path d="M118 116v-3" stroke="#ffd38a" stroke-width="1.5" transform="rotate(${-75+stress*1.5} 118 116)"/>`;
}

function capacitorBank(id,state) {
  const steps=Math.max(0,Math.min(4,Math.round(Number.isFinite(state.steps)?state.steps:2))),closed=state.open!==true;
  return `${shadow()}<path d="M27 119H155M35 48V120m112-72v72M34 52H148" stroke="#85a6b6" stroke-width="4"/>
    ${[0,1,2,3].map((i)=>{const x=40+i*28,on=closed&&i<steps&&clamp(state.load,60)>0;
      return `<g class="scada-power-capacitor-cell" data-cell-active="${on}"><rect x="${x}" y="68" width="23" height="40" rx="3" fill="${steel(id)}" stroke="#a7cbd5"/>
        ${insulator(x+11,55,13,8)}<path d="M${x+11} 51v5" stroke="#abcdd6" stroke-width="2"/>
        <path d="M${x+5} 83h13m-13 6h13" stroke="${on?'#7ff3da':'#7296a8'}" stroke-width="2.3"/>
        <circle class="scada-power-motion scada-power-charge" cx="${x+11}" cy="99" r="2" fill="#b8f5dd"/></g>`;}).join('')}
    ${circuit(closed&&steps>0&&clamp(state.load,60)>0,wire('M8 30H76')+wire('M104 30H171')+(closed?wire('M76 30H104'):'<path d="M76 30l24-14" stroke="#adcbd6" stroke-width="3"/>'))}
    <path d="M119 30v22" stroke="#adcbd6" stroke-width="3"/>${terminal(76,30)}${terminal(104,30)}${indicator(45,113,28)}`;
}

function shunt(id,state) {
  const closed=state.open!==true,load=clamp(state.load,60),heat=clamp(state.heat,45);
  return `${shadow()}${feet([44,136],105,18)}<path d="M29 103H152V111H29Z" fill="${steel(id)}" stroke="#9cc3d0"/>
    ${[51,90,129].map(x=>`${insulator(x,37,17,13)}${coil(x,58,27,43)}`).join('')}
    ${circuit(closed&&load>0,wire('M8 22H72')+wire('M109 22H172')+(closed?wire('M72 22H109'):'<path d="M72 22l29-13" stroke="#bed4dc" stroke-width="3"/>'))}
    ${terminal(72,22)}${terminal(109,22)}<path d="M51 22v15m39-15v15m39-15v15" stroke="#a7c6d2" stroke-width="2.5"/>
    <g class="scada-power-magnetic" data-conducting="${closed&&load>0}" style="opacity:${.12+load*.006}"><path class="scada-power-motion scada-power-field-pulse" d="M34 61q-13 18 0 35m111-35q13 18 0 35" fill="none" stroke="#a5eddf" stroke-width="1.6" stroke-dasharray="3 4"/></g>${hot(90,81,heat)}`;
}

function relay(id,state) {
  const powered=state.active!==false&&state.status!=='offline'&&state.fault!==true&&state.damage!=='power-loss';
  const connected=powered&&state.connected!==false&&state.damage!=='comms-loss',value=clamp(state.value,42),tripped=state.tripped===true;
  const asserted=powered&&tripped,tripColor=asserted?'#ff98ba':'#465266';
  return `${shadow(90,125,64)}
    <path d="M29 22L38 15H145L153 22V116H29Z" fill="${steel(id)}" stroke="#afcfda" stroke-width="1.6"/>
    <rect x="35" y="23" width="112" height="87" rx="3" fill="#102a3d" stroke="#6e9aaf"/>
    <path d="M42 29H140" stroke="#678ca1" stroke-width="1"/>
    <g class="scada-relay-display scada-power-sensing" data-connected="${connected}">
      <rect x="43" y="36" width="71" height="37" rx="3" fill="${powered?'#07343c':'#142b38'}" stroke="#80adba"/>
      <text class="scada-relay-function" x="50" y="54">I&gt;</text>
      <text class="scada-relay-reading" x="105" y="54" text-anchor="end">${connected?Math.round(value):'—'}</text>
      <path d="M50 65H106" stroke="#2c6570" stroke-width="1"/>
      <path class="scada-power-motion scada-power-signal" d="M50 64h8l6-${(value*.08+1).toFixed(1)} 7 ${(value*.12+2).toFixed(1)} 7-${(value*.1+1).toFixed(1)} 7 2h21" fill="none" stroke="#81e9d5" stroke-width="1.5"/>
    </g>
    <g class="scada-relay-targets"><circle cx="128" cy="42" r="3" fill="${connected?'#7defcf':'#485d6d'}"/><circle cx="128" cy="56" r="3" fill="${tripColor}"/><circle cx="128" cy="70" r="3" fill="${powered&&!connected?'#ffd38a':'#485d6d'}"/>
      <path d="M135 42h5m-5 14h5m-5 14h5" stroke="#99b8c8" stroke-width="1.5"/></g>
    <path class="scada-relay-shield" d="M44 84l12-5 12 5v10q-2 9-12 13q-10-4-12-13Z" fill="#153f50" stroke="#8cd7d2" stroke-width="1.5"/>
    <path d="M57 84l-7 10h6l-1 9 8-12h-7Z" fill="#b6efe0"/>
    <g class="scada-relay-trip-contact" data-tripped="${tripped}" data-output-asserted="${asserted}" fill="none" stroke="${tripColor}" stroke-width="2.2"><path d="M75 92h7m11 0h7"/><path d="${asserted?'M82 92H93':'M82 92l10-9'}"/><circle cx="82" cy="92" r="1.8"/><circle cx="93" cy="92" r="1.8"/></g>
    <rect class="scada-relay-trip-target" x="104" y="83" width="39" height="17" rx="3" fill="${powered&&tripped?'#5c3046':'#20394b'}" stroke="${tripColor}"/>
    <text class="scada-power-detail-label" x="123.5" y="94.5" text-anchor="middle" fill="${powered&&tripped?'#ffd2df':'#b1c6d1'}">TRIP OUT</text>
    <path d="M46 117v6m14-6v6m14-6v6m28-6v6m14-6v6m14-6v6" stroke="#9dbfcd" stroke-width="3"/>
    <g class="scada-power-sensing" data-connected="${connected}">${wire('M9 54H29',{flow:false})}<path class="scada-power-motion scada-power-signal" d="M9 54H29" stroke="#83e9d8" stroke-width="1.6" stroke-dasharray="3 4"/></g>
    <g class="scada-relay-output" data-output-asserted="${asserted}"><path d="M153 92h18" stroke="${tripColor}" stroke-width="2"/><circle cx="171" cy="92" r="4" fill="${tripColor}" stroke="#c5d7dd" stroke-width="1.5"/></g>`;
}

function switchgear(id,state) {
  const closed=state.open!==true,connected=state.connected!==false;
  return `${shadow()}${feet([43,138],115,8)}<path d="M27 18H153V118H27Z" fill="${steel(id)}" stroke="#b4d0d9" stroke-width="1.5"/>
    <path d="M35 26H87V110H35Zm60 0h50v84H95Z" fill="#17384d" stroke="#729eb3"/>
    ${indicator(43,36,34)}<g class="scada-power-sensing" data-connected="${connected}">${indicator(103,36,34)}</g>
    <path d="M40 89h41m-41 7h41m19-7h40m-40 7h40" stroke="#6b92a4" stroke-width="2"/>
    <path d="M78 62v13m59-13v13" stroke="#b1d0d8" stroke-width="3"/>
    <path d="M51 59h18v20H51Z" fill="#0c2638" stroke="#8bb9c5"/><path d="M59 62v13" stroke="${closed?'#8de8d0':'#ffd38a'}" stroke-width="4" transform="rotate(${closed?0:55} 59 69)"/>
    ${circuit(closed&&clamp(state.load,60)>0,wire('M9 12H171')+wire('M60 12V25')+wire('M120 12V25'))}`;
}

function gisBay(id,state) {
  const closed=state.open!==true,pressure=clamp(state.pressure,60);
  return `${shadow()}${feet([42,133],106,17)}
    <path d="M24 57Q24 42 40 42H143Q158 42 158 58V85Q158 102 143 102H40Q24 102 24 85Z" fill="${steel(id)}" stroke="#b2d0db" stroke-width="1.5"/>
    <path d="M40 43v58m16-58v58m66-58v58m16-58v58" stroke="#79a1b3" stroke-width="3"/>
    <path d="M60 53H118V91H60Z" fill="#0d2d40" stroke="#8bb4c5"/>
    ${circuit(closed&&clamp(state.load,60)>0,wire('M8 71H76')+wire('M106 71H173')+(closed?wire('M76 71H106'):'<path d="M76 71h8m14 0h8" stroke="#b6cdd6" stroke-width="3"/>'))}
    <path d="M57 42V30m66 12V30" stroke="#a4c7d2" stroke-width="12"/>${insulator(57,9,22,18)}${insulator(123,9,22,18)}
    <circle cx="89" cy="114" r="11" fill="#102e40" stroke="#a2cad5" stroke-width="1.5"/><path d="M89 114v-7" stroke="#7df2d5" stroke-width="2" transform="rotate(${-70+pressure*1.4} 89 114)"/>
    ${state.damage==='gas-leak'?'<g class="scada-power-incident"><path d="M137 48l5-7 5 8" fill="none" stroke="#ff9cbd" stroke-width="2"/><path class="scada-power-motion scada-power-gas-plume" d="M143 39q-8-9 0-15m8 14q8-9 0-17" fill="none" stroke="#badbe3" stroke-width="3" opacity=".8"/></g>':''}`;
}

function transferSwitch(id,state) {
  const source=['a','b','off'].includes(state.source)?state.source:'a',load=clamp(state.load,60),automatic=state.automatic!==false;
  return `${shadow()}${feet([49,133],111,12)}<path d="M27 29H152V114H27Z" fill="${steel(id)}" stroke="#b6d3dc" stroke-width="1.5"/>
    <path d="M36 39H142V98H36Z" fill="#0e2d41" stroke="#83adbf"/>
    ${circuit(source==='a'&&load>0,wire('M8 50H65'))}${circuit(source==='b'&&load>0,wire('M8 86H65'))}
    ${circuit(source!=='off'&&load>0,wire('M98 68H173'))}
    <path d="M98 68L${source==='off'?'98 43':source==='a'?'65 50':'65 86'}" stroke="#bad3dc" stroke-width="5" stroke-linecap="round"/>
    ${source==='off'?'':circuit(load>0,wire(source==='a'?'M65 50L98 68':'M65 86L98 68'))}
    ${terminal(65,50)}${terminal(65,86)}${terminal(98,68)}
    <g class="scada-power-automatic" data-automatic="${automatic}"><circle class="scada-power-monitor" cx="123" cy="105" r="3" fill="${automatic?'#7bf3cf':'#819aa9'}"/><path d="M46 105h49" stroke="#8fb3c2" stroke-width="2"/></g>`;
}

function excitation(id,state) {
  const connected=state.connected!==false&&!['field-loss','power-loss'].includes(state.damage),field=clamp(state.field,60),load=clamp(state.load,60);
  return `${shadow()}${feet([43,133],110,13)}<path d="M26 25H92V114H26Z" fill="${steel(id)}" stroke="#b0cfd9" stroke-width="1.5"/>
    <path d="M34 33H84V105H34Z" fill="#14364b" stroke="#7ba6b9"/>${indicator(41,40,36)}
    ${[66,78,90].map(y=>`<path d="M42 ${y}h33" stroke="#8cb4c2" stroke-width="2"/><path d="M49 ${y-4}v8l9-4Z" fill="#c5bd98" stroke="#d6d1ad" stroke-width=".8"/>`).join('')}
    <path d="M112 67H151V111H112Z" fill="#19394f" stroke="#96bdcd"/>
    ${coil(132,73,26,32)}
    ${circuit(connected&&load>0&&field>0,wire('M8 65H26')+wire('M92 62H132V73')+wire('M132 109V119H166'))}
    <g class="scada-power-magnetic" data-conducting="${connected&&field>0}" style="opacity:${.15+field*.0085}"><path class="scada-power-motion scada-power-field-pulse" d="M107 72q-11 17 0 34m49-34q11 17 0 34" fill="none" stroke="#a0f0d8" stroke-width="1.5" stroke-dasharray="3 4"/></g>
    ${state.damage==='field-loss'?'<path d="M124 85l8 8 7-8m-13 12 11 0" fill="none" stroke="#ff9dbd" stroke-width="2"/>':''}`;
}

const DRAWINGS=Object.freeze({
  'power-inverter':converter,'power-rectifier':(id,s)=>converter(id,s,true),
  'hv-circuit-breaker':hvBreaker,'disconnect-switch':disconnect,'earthing-switch':(id,s)=>disconnect(id,s,true),
  'current-transformer':currentTransformer,'voltage-transformer':voltageTransformer,
  'surge-arrester':arrester,'capacitor-bank':capacitorBank,'shunt-reactor':shunt,'protection-relay':relay,
  'switchgear-panel':switchgear,'gis-bay':gisBay,'automatic-transfer-switch':transferSwitch,'excitation-system':excitation,
});
const ANCHORS=Object.freeze({
  'power-inverter':{x:106,y:76},'power-rectifier':{x:106,y:76},'hv-circuit-breaker':{x:92,y:34},
  'disconnect-switch':{x:77,y:46},'earthing-switch':{x:86,y:70},'current-transformer':{x:106,y:38},
  'voltage-transformer':{x:90,y:69},'surge-arrester':{x:90,y:63},'capacitor-bank':{x:106,y:88},
  'shunt-reactor':{x:90,y:79},'protection-relay':{x:81,y:55},'switchgear-panel':{x:119,y:76},
  'gis-bay':{x:95,y:76},'automatic-transfer-switch':{x:92,y:65},'excitation-system':{x:132,y:86},
});
function instrumentDamage(type,damage) {
  if(type==='current-transformer'&&damage==='drift')return `<g class="scada-power-damage scada-ct-drift" data-power-damage="drift"><path d="M141 93l6-5 5 9 7-5" fill="none" stroke="#ffd38a" stroke-width="1.5" stroke-dasharray="3 2"/><path d="M129 81l8 12h-16Z" fill="#453c32" stroke="#ffd38a"/><path d="M129 84v4m0 1v1" stroke="#ffe9b5" stroke-width="1.4"/></g>`;
  if(type!=='protection-relay')return null;
  if(damage==='drift')return `<g class="scada-power-damage scada-relay-drift" data-power-damage="drift"><path d="M49 68l12-9 11 6 13-4 21 6" fill="none" stroke="#ffd38a" stroke-width="1.4" stroke-dasharray="3 2"/><path d="M127 64l6 10h-12Z" fill="#443f35" stroke="#ffd38a"/></g>`;
  if(damage==='comms-loss')return `<g class="scada-power-damage scada-relay-disconnected" data-power-damage="comms-loss"><path d="M9 50h7v8H9Zm13 3h7v8h-7Z" fill="#152c3e" stroke="#f5c79c" stroke-width="1.2"/><path d="M17 48l4-4m-2 14 4 4" fill="none" stroke="#ffc5ac" stroke-width="1.5"/></g>`;
  if(damage==='power-loss')return `<g class="scada-power-damage scada-relay-power-loss" data-power-damage="power-loss"><path d="M124 51a7 7 0 1 0 8 0m-4-4v10" fill="none" stroke="#8ca5b6" stroke-width="1.8"/><path d="M121 48l14 16" stroke="#d7b29b" stroke-width="1.6"/></g>`;
  return null;
}

export function renderElectricalArt(type,{id='scada-electrical',state={}}={}) {
  if (!Object.hasOwn(DRAWINGS,type)) return '';
  const damage=typeof state.damage==='string'&&/^[a-z][a-z0-9-]*$/.test(state.damage)?state.damage:'none';
  let anchor=ANCHORS[type];
  if(type==='earthing-switch')anchor=damage==='stuck'?{x:51,y:49}:damage==='contact-wear'?(state.open===false?{x:128,y:90}:{x:96,y:20}):{x:51,y:76};
  return `<g class="scada-power-art scada-electrical-art" data-power-type="${type}" style="--scada-power-cycle:${(3.8-clamp(state.load,60)*.025).toFixed(2)}s;--scada-power-current-opacity:${.2+clamp(state.load,60)*.008}">
    ${DRAWINGS[type](prefix(id),state)}
    ${damage==='gas-leak'?'':instrumentDamage(type,damage)??damageArt(damage,{...anchor,radius:25})}
  </g>`;
}
export const ELECTRICAL_ART_TYPES=Object.freeze(Object.keys(DRAWINGS));
