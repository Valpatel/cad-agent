/** Explicit generator variants. The legacy generator path never calls this
 * module implicitly; callers select a documented fuel/enclosure variant. */
import {clamp,prefix,steel,shadow,feet,wire,fan,indicator,damageArt} from './primitives.mjs';

export const GENSET_ART_VARIANTS=Object.freeze(['natural-gas-enclosed','natural-gas-industrial','diesel-skid','diesel-enclosed','gasoline-portable']);

function alternator(id,x=121,y=81,r=22) {
  return `<path d="M${x-r-6} ${y-r+3}h${r+15}v${r*2-6}h-${r+15}Z" fill="${steel(id)}" stroke="#9bc5d2"/>
    <circle cx="${x}" cy="${y}" r="${r}" fill="${steel(id)}" stroke="#accfd8" stroke-width="1.4"/>
    <circle cx="${x}" cy="${y}" r="${r-5}" fill="#133b50" stroke="#7cafbf"/>
    <g class="scada-power-drive">${fan(x,y,r-8)}</g>`;
}
function fuelFeed(id,gas,portable=false){
  if(gas)return `<path d="M9 112H46V91" fill="none" stroke="#95bfcc" stroke-width="5"/><path d="M18 107h16v10H18Z" fill="#19465c" stroke="#90c5d1"/><path d="M26 107v-7m-6 0h12" stroke="#99c4cf" stroke-width="2"/><path d="M12 112h8m14 0h9" stroke="#e4cb95" stroke-width="1.4" stroke-dasharray="3 2"/>`;
  if(portable)return `<path d="M40 35H113V52H40Z" fill="${steel(id)}" stroke="#bad5dc" stroke-width="1.3"/><path d="M69 31h15v5H69Z" fill="#1c3f53" stroke="#a9ccd6"/><path d="M107 49v19H89" fill="none" stroke="#c6b793" stroke-width="2"/>`;
  return `<path d="M34 104H149V117H34Z" fill="#20495e" stroke="#a0c6d1" stroke-width="1.2"/><path d="M40 101h12v4H40Z" fill="#8eb5c4" stroke="#c4d8db"/><path d="M43 105v8h101" fill="none" stroke="#ad9b72" stroke-width="1.6"/>`;
}
function engine(id,load,{x=43,y=60,width=53}={}){
  return `<path d="M${x} ${y+12}h${width}v33H${x}Z" fill="${steel(id)}" stroke="#a4cbd6" stroke-width="1.2"/>
    ${[0,1,2].map(i=>`<path d="M${x+3+i*(width-4)/3} ${y}h13v21h-13Z" fill="#234c63" stroke="#8cb9c9"/>
      <path d="M${x+5+i*(width-4)/3} ${y+4}h9m-9 5h9m-9 5h9" stroke="#90b9c8" stroke-width="1.3"/>`).join('')}
    <g class="scada-power-drive">${[0,1,2].map(i=>`<path class="scada-power-motion scada-genset-piston" d="M${x+8+i*(width-4)/3} ${y+23}v14" stroke="#b9d3da" stroke-width="3.3" style="animation-delay:-${i*.25}s;--scada-genset-stroke:${.6+load*.018}px"/>`).join('')}</g>
    <path d="M${x+5} ${y+43}h${width-10}" stroke="#6b95a8" stroke-width="3"/>`;
}
function exhaust(path,load){
  return `<path d="${path}" fill="none" stroke="#90b2c2" stroke-width="5"/>
    <g class="scada-genset-exhaust scada-power-drive" style="opacity:${.15+load*.004}"><path class="scada-power-motion scada-power-heat-rise" d="M107 18q-5-6 0-12m9 13q5-6 0-12" fill="none" stroke="#abc7d0" stroke-width="2"/></g>`;
}
function output(load,path='M145 91H169V113'){
  return `<g class="scada-power-circuit" data-conducting="${load>0}">${wire(path)}</g>`;
}
function skid(id,state,gas){
  const load=clamp(state.load,60);
  return `${shadow(90,127,77)}${feet([39,145],116,9)}
    <path d="M19 111H160V119H19Z" fill="${steel(id)}" stroke="#9bc2cf"/>
    ${fuelFeed(id,gas)}${engine(id,load)}${alternator(id)}
    <path d="M39 55h53v9H39Z" fill="#274f66" stroke="#9bc6d3"/>
    ${exhaust('M68 55V37H110V20',load)}
    <path d="M96 29h26v10H96Z" fill="${steel(id)}" stroke="#aacdd7"/>
    <path d="M31 72V36H53V46" fill="none" stroke="#82aebf" stroke-width="4"/>
    <path d="M25 35h12v24H25Z" fill="#1d4259" stroke="#9bc2d1"/>
    ${indicator(126,38,29)}${output(load)}`;
}
function cabinet(id,state,gas){
  const load=clamp(state.load,60);
  return `${shadow()}${feet([43,138],114,10)}
    <path d="M25 39L39 26H143L156 39V112L142 119H25Z" fill="${steel(id)}" stroke="#b3d1dc" stroke-width="1.5"/>
    <path d="M30 44H112V106H30Z" fill="#20485f" stroke="#91b7c8"/>
    <path d="M117 44H147V106H117Z" fill="#16394f" stroke="#92bbcd"/>
    <path d="M35 50h71m-71 8h71m-71 8h71" stroke="#799fb0" stroke-width="2"/>
    <path d="M74 72v27M68 83v10m12-10v10" stroke="#a5c7d1" stroke-width="2"/>
    <circle cx="132" cy="75" r="12" fill="#0c293b" stroke="#7da9bc"/><g class="scada-power-drive">${fan(132,75,9)}</g>
    <path d="M120 97h24m-24 5h24" stroke="#7ea8bb" stroke-width="2"/>
    ${indicator(40,80,25)}
    ${exhaust('M103 26V20H110',load)}
    ${gas?fuelFeed(id,true):`<path d="M28 109H144V119H28Z" fill="#284b60" stroke="#a6c5d1"/><path d="M45 112h13" stroke="#d7bb88" stroke-width="2"/><circle cx="32" cy="34" r="4" fill="#33495b" stroke="#b6c8d2"/>`}
    ${output(load,'M155 88H170V118')}`;
}
function portable(id,state){
  const load=clamp(state.load,60);
  return `${shadow(90,126,65)}
    <path d="M28 115V35Q28 26 38 26H141Q151 26 151 36V115H28Z" fill="none" stroke="#729bab" stroke-width="7" stroke-linejoin="round"/>
    <path d="M31 31H145m-117 80h123" stroke="#c4d9dd" stroke-width="1.5"/>
    ${fuelFeed(id,false,true)}${engine(id,load,{x:43,y:62,width:44})}${alternator(id,111,88,20)}
    <path d="M119 49h23v24h-23Z" fill="#15384e" stroke="#a5c7d3"/>
    <circle cx="126" cy="57" r="3" fill="#0a2031" stroke="#b2cbd3"/><circle cx="136" cy="57" r="3" fill="#0a2031" stroke="#b2cbd3"/>
    <path d="M126 65h9" stroke="#84edcf" stroke-width="2"/>
    <path d="M30 116h16v8H30Zm105 0h16v8h-16Z" fill="#15283b" stroke="#80a7b8"/>
    <path d="M42 88H33V65h10" fill="none" stroke="#a6c1c9" stroke-width="4"/>
    <g class="scada-power-drive scada-genset-exhaust"><path class="scada-power-motion scada-power-heat-rise" d="M19 61q-5-6 0-14m8 14q4-6 0-13" fill="none" stroke="#b3c8cc" stroke-width="1.8" opacity="${.15+load*.0035}"/></g>
    ${output(load,'M143 65H165V119H155')}`;
}
export function renderGensetArt(variant,{id='scada-genset',state={}}={}){
  if(!GENSET_ART_VARIANTS.includes(variant))return '';
  const instance=prefix(id),speed=clamp(state.speed,60),load=clamp(state.load,60),gas=variant.startsWith('natural-gas');
  const portableVariant=variant==='gasoline-portable';
  const art=portableVariant?portable(instance,state):variant.endsWith('enclosed')?cabinet(instance,state,gas):skid(instance,state,gas);
  const damage=typeof state.damage==='string'&&/^[a-z][a-z0-9-]*$/.test(state.damage)?state.damage:'none';
  return `<g class="scada-power-art scada-genset-art" data-genset-variant="${variant}" data-power-speed-zero="${speed===0}" data-power-drive-blocked="${damage==='burnt'||damage==='short-circuit'}" style="--scada-power-cycle:${(4.6-speed*.036).toFixed(2)}s;--scada-genset-stroke:${.6+load*.018}px;--scada-power-current-opacity:${.2+load*.008}">
    ${art}${damage==='burnt'?'<path d="M89 58l17-4 15 13-3 25-19 5-13-21Z" fill="#312b32" stroke="#9c7683" stroke-width="1.2" opacity=".9"/>':''}
    ${damageArt(damage,{x:portableVariant?111:variant.endsWith('enclosed')?132:122,y:78,radius:24})}
  </g>`;
}
