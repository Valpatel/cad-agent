import {equipmentArt} from './art/twin.mjs';
import {renderControlArt} from './art/control.mjs';
import {renderIndustrialArt} from './art/industrial.mjs';
import {renderProcessArt,renderDamageArt} from './art/process.mjs';
import {renderAgricultureArt} from './art/agriculture.mjs';
import {renderEnergyArt,ENERGY_ART_TYPES} from './power/energy.mjs';
import {renderElectricalArt,ELECTRICAL_ART_TYPES} from './power/electrical.mjs';
import {renderNuclearArt} from './power/nuclear.mjs';
import {renderGensetArt} from './power/generators.mjs';
import {getScadaComponent,normalizeScadaState} from '../catalog/registry.mjs';

const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function definitions(id){return `<defs>
 <linearGradient id="${id}-steel"><stop stop-color="#16374a"/><stop offset=".3" stop-color="#659bae"/><stop offset=".5" stop-color="#acd5de"/><stop offset=".72" stop-color="#396a81"/><stop offset="1" stop-color="#122e42"/></linearGradient>
 <linearGradient id="${id}-glass" x2=".8" y2="1"><stop stop-color="#69eff1" stop-opacity=".18"/><stop offset="1" stop-color="#081827" stop-opacity=".65"/></linearGradient>
 <linearGradient id="${id}-liquid" x2="0" y2="1"><stop stop-color="#57ffd0" stop-opacity=".85"/><stop offset="1" stop-color="#087a92" stop-opacity=".55"/></linearGradient>
 <radialGradient id="${id}-glow"><stop stop-color="#00e5e9" stop-opacity=".18"/><stop offset="1" stop-color="#00e5e9" stop-opacity="0"/></radialGradient>
 </defs>`;}
const steel=id=>`url(#${id}-steel)`;
const pipe=(path,accent='')=>`<path d="${path}" fill="none" stroke="#28566d" stroke-width="12" stroke-linejoin="round"/><path d="${path}" fill="none" stroke="#88bdd0" stroke-width="7" stroke-linejoin="round"/><path class="scada-flow ${accent}" d="${path}" fill="none" stroke-width="2.4"/>`;
const screw=(x,y)=>`<circle cx="${x}" cy="${y}" r="1.5" fill="#c1e4ec"/><path d="M${x-1} ${y}h2" stroke="#21445a" stroke-width=".6"/>`;
const rotor=(x,y,r=24)=>`<g class="scada-rotor" style="transform-origin:${x}px ${y}px">${[0,60,120,180,240,300].map(angle=>`<path d="M${x} ${y}q${-r*.9} ${-r*.18} ${-r*.65} ${-r*.78}Q${x+r*.2} ${y-r*.8} ${x+3} ${y-4}Z" fill="#8de9ec" transform="rotate(${angle} ${x} ${y})"/>`).join('')}<circle cx="${x}" cy="${y}" r="5" fill="#164d67" stroke="#d9f7ff"/></g>`;
const display=(x,y,w=42,text='42',unit='')=>`<rect x="${x}" y="${y}" width="${w}" height="25" rx="3" fill="#061725" stroke="#4d8fa3"/><text class="scada-readout" x="${x+w/2}" y="${y+15}" text-anchor="middle">${esc(text)}</text>${unit?`<text class="scada-unit" x="${x+w/2}" y="${y+22}" text-anchor="middle">${esc(unit)}</text>`:''}`;
const dial=(x,y,r=20,value=42)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="#0a2435" stroke="#a1cfd9" stroke-width="2"/><path d="M${x-r*.7} ${y+3}a${r*.75} ${r*.75} 0 0 1 ${r*1.4} 0" fill="none" stroke="#558f9e" stroke-width="3"/><path class="scada-needle" d="M${x} ${y}v-${r*.65}" stroke="#62ffbc" stroke-width="2" style="transform-origin:${x}px ${y}px;transform:rotate(${Math.max(-70,Math.min(70,(value-50)*1.4))}deg)"/><circle cx="${x}" cy="${y}" r="2.4" fill="#b6f5ec"/>`;

function vessel(type,id,state){
 const fill=state.level/100;
 if(type==='clarifier')return `<ellipse cx="90" cy="81" rx="66" ry="28" fill="#16394b" stroke="#7cbdcb" stroke-width="2"/><path d="M24 80v20c0 35 132 35 132 0V80" fill="${steel(id)}" stroke="#77b4c7"/><ellipse cx="90" cy="81" rx="60" ry="23" fill="url(#${id}-liquid)" opacity="${fill*.9}"/><ellipse cx="90" cy="81" rx="48" ry="17" fill="none" stroke="#7cebdc" stroke-dasharray="4 5" opacity=".45"/><g class="scada-scraper" style="transform-origin:90px 81px"><path d="M35 81H145" stroke="#badbe3" stroke-width="4"/><path d="M43 76v10M137 76v10" stroke="#5f91a5" stroke-width="2"/></g><ellipse cx="90" cy="81" rx="13" ry="9" fill="#173a50" stroke="#8cd3df"/><path d="M90 81V36H26M90 120v10" fill="none" stroke="#80b4c6" stroke-width="6"/>`;
 if(type==='reactor')return `${pipe('M10 79H36M144 79H170')}<rect x="32" y="41" width="116" height="67" rx="31" fill="${steel(id)}" stroke="#8fc3d2"/><ellipse cx="49" cy="74" rx="12" ry="32" fill="none" stroke="#c2e0e6" opacity=".6"/><ellipse cx="131" cy="74" rx="12" ry="32" fill="none" stroke="#183f56" stroke-width="3"/><path d="M58 105v16M125 105v16" stroke="#528096" stroke-width="7"/><rect x="65" y="58" width="48" height="31" rx="8" fill="#0a283a" stroke="#6bbbc5"/><rect x="69" y="${85-23*fill}" width="40" height="${23*fill}" rx="4" fill="url(#${id}-liquid)"/>${dial(100,32,15)}<path d="M100 47V58" stroke="#9bc7d6" stroke-width="4"/>`;
 if(type==='silo')return `<defs><clipPath id="${id}-silo-fill"><path d="M59 34H121V89L96 112H84L59 89Z"/></clipPath></defs><path d="M49 29Q90 4 131 29V91L101 119H79L49 91Z" fill="${steel(id)}" stroke="#a0cbd7"/><path d="M59 34H121V89L96 112H84L59 89Z" fill="#0a2539"/><rect x="59" y="${112-78*fill}" width="62" height="${78*fill}" fill="url(#${id}-liquid)" clip-path="url(#${id}-silo-fill)"/><path d="M49 29Q90 52 131 29M49 91H131" fill="none" stroke="#b3d7df"/><path d="M55 89v39M125 89v39M84 119v12h12v-12" fill="none" stroke="#57899e" stroke-width="5"/><path class="scada-flow" d="M90 113v21" fill="none" stroke-width="3"/>`;
 const mixing=type==='mixing-tank';
 return `${pipe('M13 88H43M137 98H167')}<defs><clipPath id="${id}-tank-clip"><path d="M43 39V108Q90 128 137 108V39Z"/></clipPath></defs><path d="M43 39V108Q90 128 137 108V39Z" fill="#102d42" stroke="#8cc3d1" stroke-width="1.5"/><g clip-path="url(#${id}-tank-clip)"><rect x="43" y="${115-72*fill}" width="94" height="${72*fill}" fill="url(#${id}-liquid)"/><path class="scada-wave" d="M0 ${115-72*fill}q15-6 30 0t30 0t30 0t30 0t30 0t30 0" fill="none" stroke="#93ffe0" stroke-width="2"/><path d="M52 42v66" stroke="#d7f7fb" stroke-width="4" opacity=".19"/><path d="M43 39V108Q90 128 137 108V39Z" fill="url(#${id}-glass)"/></g><ellipse cx="90" cy="39" rx="47" ry="13" fill="${mixing?'#123c4a':steel(id)}" stroke="#b4d5df"/><path d="M43 108Q90 128 137 108" fill="none" stroke="#9ed8df"/><path d="M144 51h8M144 66h5M144 81h8M144 96h5M144 111h8" stroke="#71acbe" stroke-width="2"/>${mixing?`<path d="M90 23V103" stroke="#b9e0ea" stroke-width="3"/><rect x="73" y="7" width="34" height="22" rx="4" fill="${steel(id)}" stroke="#9bd2df"/><g class="scada-mixer" style="transform-origin:90px 91px"><path d="M66 91h48M72 85l-7 6 7 6M108 85l7 6-7 6" fill="none" stroke="#b8f4ef" stroke-width="4"/></g>`:'<path d="M85 25V13h10v12" fill="#5794a8"/>'}`;
}

function machinery(type,id,state){
 if(type==='submersible-pump')return `<g class="scada-submersible-pump">
  ${pipe('M108 94H143V43H173')}
  <path d="M69 36V24a9 9 0 0 1 9-9h15a9 9 0 0 1 9 9v12" fill="none" stroke="#173d51" stroke-width="9"/><path class="scada-pump-handle" d="M69 35V24a9 9 0 0 1 9-9h15a9 9 0 0 1 9 9v11" fill="none" stroke="#a2d5df" stroke-width="4"/>
  <path class="scada-pump-cable" d="M108 39V24q0-10 10-10h16q8 0 8-9" fill="none" stroke="#07131d" stroke-width="6"/><path d="M108 39V24q0-10 10-10h16q8 0 8-9" fill="none" stroke="#587a8b" stroke-width="2"/>
  <path d="M56 40Q85 23 114 40V83Q85 96 56 83Z" fill="${steel(id)}" stroke="#afdce4" stroke-width="1.5"/><ellipse cx="85" cy="40" rx="29" ry="9" fill="#315c72" stroke="#a9d7e1"/>
  <path d="M64 48v29M74 51v30M96 51v30M106 48v29" stroke="#183f53" stroke-width="3"/><path d="M60 83Q85 94 111 83" fill="none" stroke="#c5e8ec" stroke-width="2"/>
  <rect x="102" y="33" width="12" height="12" rx="3" fill="#26465b" stroke="#9ec4d1"/><rect x="77" y="52" width="16" height="24" rx="3" fill="#0b283a" stroke="#78b5c3"/><path d="M81 57h8M81 62h8M81 67h5" stroke="#91ccd5" stroke-width="1.5"/>
  <path d="M61 84Q82 70 105 80q14 6 14 19v10H63q-12-12-2-25Z" fill="${steel(id)}" stroke="#a7d7df" stroke-width="1.6"/><circle class="scada-pump-cutaway" cx="84" cy="94" r="20" fill="#092b3b" stroke="#80c1cb" stroke-width="2"/>${rotor(84,94,16)}<circle cx="84" cy="94" r="17" fill="none" stroke="#79d8db" stroke-width=".8"/>
  <path d="M61 111h49v15H61Z" fill="#0c293b" stroke="#8bb9c8" stroke-width="1.5"/>${[66,74,82,90,98,106].map(x=>`<path d="M${x} 115v8" stroke="#7eb8c9" stroke-width="2.5"/>`).join('')}
  <path class="scada-flow" d="M73 134v-10M96 134v-10" fill="none" stroke-width="2.3"/><path d="M58 126h55" stroke="#99c9d3" stroke-width="3"/><path d="M137 52h12M137 84h12" stroke="#385e73" stroke-width="3"/>
 </g>`;
 if(type==='dosing-pump')return `${pipe('M29 11V44M29 88V128')}<rect x="68" y="33" width="83" height="69" rx="8" fill="${steel(id)}" stroke="#8fc4d3"/><path d="M78 91h60M82 97v15M135 97v15" stroke="#355f77" stroke-width="6"/>${display(92,43,42,state.active?'RUN':'OFF')}<circle cx="42" cy="66" r="25" fill="#164257" stroke="#a5d6dd" stroke-width="2"/><circle cx="42" cy="66" r="15" fill="#092238" stroke="#68bcc6"/><g class="scada-piston"><path d="M45 66H84" stroke="#a7d9e1" stroke-width="8"/><circle cx="42" cy="66" r="8" fill="#68d8d5"/></g>${[48,84].map(y=>screw(73,y)).join('')}`;
 if(type==='blower')return `${pipe('M109 43V21H165')}<path d="M38 110V99M119 110V97" stroke="#588da4" stroke-width="8"/><path d="M33 109H132" stroke="#2a4f66" stroke-width="8"/><path d="M120 36C62 7 21 44 30 85C39 127 112 112 127 79V36Z" fill="${steel(id)}" stroke="#96c8d5" stroke-width="2"/><circle cx="77" cy="70" r="31" fill="#0a2338" stroke="#8bd5dc"/>${rotor(77,70,27)}<circle cx="77" cy="70" r="26" fill="none" stroke="#b7d9df" stroke-dasharray="2 6"/>`;
 if(type==='compressor')return `<rect x="25" y="86" width="128" height="34" rx="16" fill="${steel(id)}" stroke="#86c2d0"/><path d="M47 118v10M133 118v10" stroke="#538397" stroke-width="6"/><path d="M44 47l18 36h48l18-36" stroke="#39667c" stroke-width="15"/><g class="scada-piston"><path d="M56 57l12 22M120 57l-13 22" stroke="#b5e2e9" stroke-width="6"/></g>${[39,102].map(x=>`<rect x="${x}" y="31" width="39" height="34" rx="4" fill="${steel(id)}" stroke="#8fc9d3"/><path d="M${x+4} 36h31M${x+4} 43h31M${x+4} 50h31" stroke="#1c435a" stroke-width="3"/>`).join('')}<circle cx="89" cy="82" r="13" fill="#112c41" stroke="#6dbfce"/>${rotor(89,82,11)}${pipe('M18 30H42M139 30H166V101H153')}`;
 return `<path d="M25 112H148M47 95v16M124 95v16" stroke="#426e87" stroke-width="7"/><path d="M35 44H132Q155 68 132 95H35Z" fill="${steel(id)}" stroke="#8fc5d5"/>${[60,72,84,96,108,120].map(x=>`<path d="M${x} 47v45" stroke="#244a61" stroke-width="4"/>`).join('')}<ellipse cx="37" cy="70" rx="19" ry="26" fill="#0c2d42" stroke="#a3d9e4"/>${rotor(37,70,18)}<path d="M140 70h32" stroke="#95c3d2" stroke-width="10"/><path class="scada-shaft" d="M148 67h19" stroke="#2d647d" stroke-width="3"/><rect x="82" y="29" width="35" height="17" rx="3" fill="#3f768d" stroke="#95c4d0"/><circle class="scada-led" cx="92" cy="37" r="3"/>`;
}

function power(type,id,state){
 if(type==='transformer')return `<path d="M37 113H145M45 106v15M136 106v15" stroke="#456e87" stroke-width="7"/><rect x="36" y="47" width="111" height="64" rx="5" fill="${steel(id)}" stroke="#90c2d1"/>${[42,54,66,114,126,138].map(x=>`<rect x="${x}" y="55" width="5" height="49" rx="2" fill="#1b425a" stroke="#6c9caf"/>`).join('')}${[57,89,122].map(x=>`<path d="M${x} 47V17" stroke="#b0cad5" stroke-width="6"/><path d="M${x-9} 25h18M${x-8} 33h16M${x-7} 41h14" stroke="#476d86" stroke-width="5"/>`).join('')}<path class="scada-electric" d="M94 65L80 85H91L85 101L105 77H94Z" fill="#ffd38a"/>`;
 if(type==='breaker')return `${pipe('M90 8V40M90 98V129','scada-electric-flow')}<rect x="48" y="27" width="84" height="84" rx="8" fill="${steel(id)}" stroke="#96c4d3"/><rect x="62" y="39" width="56" height="58" rx="5" fill="#0a2538" stroke="#78aebf"/><circle cx="90" cy="47" r="4" fill="#ffd38a"/><circle cx="90" cy="88" r="4" fill="#ffd38a"/><path class="scada-contact" d="M90 88V49" stroke="#a4f0e7" stroke-width="5" style="transform-origin:90px 88px;transform:rotate(${state.open?-32:0}deg)"/><rect x="119" y="57" width="14" height="25" rx="3" fill="${state.open?'#d99d69':'#37b9ac'}"/>`;
 if(type==='busbar')return `<rect x="17" y="29" width="146" height="78" rx="7" fill="#0e263b" stroke="#4e8198"/>${[46,67,88].map((y,index)=>`<path d="M23 ${y}H157" stroke="#bf9966" stroke-width="8"/><path class="scada-flow scada-electric-flow" d="M23 ${y}H157" stroke-width="2"/><path d="M${55+index*34} ${y}v${118-y}" stroke="#8cc0cf" stroke-width="5"/>${screw(28,y)}${screw(151,y)}`).join('')}`;
 if(type==='battery')return `${[23,68,113].map((x,index)=>`<rect x="${x}" y="38" width="39" height="77" rx="5" fill="${steel(id)}" stroke="#9ccdd9"/><path d="M${x+8} 38V27h23v11" fill="#3c6c84" stroke="#92bdcd"/><rect x="${x+7}" y="51" width="25" height="51" rx="3" fill="#092a3b"/><rect class="scada-charge-fill" x="${x+10}" y="${98-state.level*.42}" width="19" height="${state.level*.42}" rx="2" fill="url(#${id}-liquid)"/><text x="${x+20}" y="46" text-anchor="middle" class="scada-unit">${index%2?'−':'+'}</text>`).join('')}<path d="M42 28V17H132V28" fill="none" stroke="#8cc0cf" stroke-width="4"/>`;
 if(type==='ups')return `<rect x="48" y="14" width="84" height="112" rx="8" fill="${steel(id)}" stroke="#94cbd5"/><path d="M55 122v9M123 122v9" stroke="#22485f" stroke-width="7"/>${display(65,27,50,state.load.toFixed(0),'% LOAD')}<rect x="61" y="65" width="58" height="44" rx="3" fill="#102c40" stroke="#527f98"/><rect x="68" y="74" width="40" height="22" rx="3" fill="#071d2d" stroke="#9dcbd5" stroke-width="1.5"/><path d="M108 80h5v10h-5" fill="#7aaabb"/><rect class="scada-charge-fill scada-ups-charge" x="72" y="78" width="${32*state.level/100}" height="14" rx="1" fill="url(#${id}-liquid)"/><path d="M80 78v14M88 78v14M96 78v14" stroke="#1b4a5b" stroke-width="1"/><text class="scada-unit" x="90" y="104" text-anchor="middle">BATTERY</text><circle class="scada-led" cx="71" cy="58" r="3"/><path d="M132 110h19V83" fill="none" stroke="#80b5c8" stroke-width="5"/>`;
 const point=(u,v)=>{const left=[25+12*v,58+58*v],right=[134+21*v,42+61*v];return [left[0]+(right[0]-left[0])*u,left[1]+(right[1]-left[1])*u].map(n=>Number(n.toFixed(2)));};
 const cells=Array.from({length:3},(_,row)=>Array.from({length:6},(_,col)=>{const u0=(col+.075)/6,u1=(col+.925)/6,v0=(row+.08)/3,v1=(row+.92)/3;const corners=[point(u0,v0),point(u1,v0),point(u1,v1),point(u0,v1)];const a=point((col+.5)/6,v0),b=point((col+.5)/6,v1);return `<polygon class="scada-solar-cell" points="${corners.map(p=>p.join(',')).join(' ')}" fill="#155c89" stroke="#6fbed8" stroke-width=".65" style="--scada-delay:${(row+col)*-.22}s"/><path d="M${a.join(' ')}L${b.join(' ')}" stroke="#82c7e3" stroke-width=".45" opacity=".75"/>`;}).join('')).join('');
 return `<g class="scada-solar-array" data-output-zero="${state.load===0}"><defs><clipPath id="${id}-solar-face"><path d="M25 58L134 42 155 103 37 116Z"/></clipPath><linearGradient id="${id}-solar-glint"><stop stop-color="#d5fdff" stop-opacity="0"/><stop offset=".5" stop-color="#d5fdff" stop-opacity=".45"/><stop offset="1" stop-color="#d5fdff" stop-opacity="0"/></linearGradient></defs>
  <path d="M56 111l-5 17M127 108l9 20M40 129h105" fill="none" stroke="#527f96" stroke-width="4"/>
  <circle cx="30" cy="22" r="9" fill="#ffd98a"/><g class="scada-solar-rays" stroke="#ffe3a5" stroke-width="1.8" stroke-linecap="round">${[0,45,90,135,180,225,270,315].map(angle=>`<path d="M30 8V4" transform="rotate(${angle} 30 22)"/>`).join('')}</g><path class="scada-solar-light" d="M45 30l22 13M36 38l13 14M54 23l25 10" fill="none" stroke="#ffe7a8" stroke-width="2"/>
  <path d="M20 54L137 36 164 108 31 124Z" fill="#112f47" stroke="#b1dce8" stroke-width="2"/><path d="M31 124l1 4 132-16v-4" fill="#2d526b" stroke="#659caf"/><path d="M20 54l11 70" stroke="#d4f0f2" stroke-width="2"/>
  ${cells}<g clip-path="url(#${id}-solar-face)"><path class="scada-solar-glint" d="M-5 31h22l59 109H54Z" fill="url(#${id}-solar-glint)"/></g>
  <path d="M162 105h12v20h-20" fill="none" stroke="#304a60" stroke-width="6" stroke-linejoin="round"/><path d="M162 105h12v20h-20" fill="none" stroke="#8ca9b6" stroke-width="3" stroke-linejoin="round"/><path class="scada-solar-current" d="M162 105h12v20h-20" fill="none" stroke="#ffe09b" stroke-width="2"/><path d="M157 122l-4 3 4 3" fill="none" stroke="#ffe5ad" stroke-width="1.5"/><text class="scada-unit" x="155" y="135">DC</text>
 </g>`;
}

function valveArt(type,id,state){
 const opening=state.open?(state.opening??100)/100:0;
 const standard=`${pipe('M8 88H172')}<path d="M38 72v32M142 72v32" stroke="#b0d6df" stroke-width="5"/>`;
 if(type==='relief-valve')return `${pipe('M90 128V91H154V64')}<path d="M68 65h44v44H68Z" fill="${steel(id)}" stroke="#9ecbd6"/><path d="M76 65V22h28v43" fill="#12364c" stroke="#82b6c8"/><path class="scada-spring" d="M78 29l24 5-24 6 24 6-24 6 24 5" fill="none" stroke="#b9e3e7" stroke-width="2.2"/><path class="scada-valve-disc" d="M72 80h36" stroke="#62ffbc" stroke-width="5" style="transform:translateY(${state.open?-10:0}px)"/><path d="M79 17h23" stroke="#83baca" stroke-width="5"/>`;
 if(type==='butterfly-valve')return `${standard}<circle cx="90" cy="88" r="28" fill="#0b2a3c" stroke="#99cbd6" stroke-width="5"/><ellipse class="scada-valve-disc" cx="90" cy="88" rx="${23-18*opening}" ry="23" fill="${steel(id)}" stroke="#5af4d0"/><path d="M90 64V30" stroke="#8bbccd" stroke-width="6"/><g class="scada-valve-lever" style="transform-origin:90px 30px;transform:rotate(${-60*opening}deg)"><path d="M90 30h41" stroke="#8bbccd" stroke-width="6"/><path d="M128 24h14v11h-14Z" fill="#33b6af"/></g>`;
 if(type==='check-valve')return `${standard}<path d="M55 63h70v50H55Z" fill="${steel(id)}" stroke="#8ec9d7"/><path d="M66 74l21 14-21 14Z" fill="#102c42" stroke="#81d2d7"/><path class="scada-valve-disc" d="M100 73v30" stroke="#91eee5" stroke-width="5" style="transform-origin:100px 73px;transform:rotate(${state.open?-45:0}deg)"/><circle cx="100" cy="72" r="4" fill="#c8e7ee"/>`;
 return `${standard}<path d="M51 65l39 23 39-23v46L90 88l-39 23Z" fill="${steel(id)}" stroke="#9fd6dc"/><path d="M77 91h26" stroke="#173e50" stroke-width="4"/><path class="scada-valve-disc" d="M79 88h22" stroke="#5af4d0" stroke-width="5" style="transform:translateY(${-12*opening}px)"/><path class="scada-valve-stem" d="M90 89V43" stroke="#8ec8d5" stroke-width="5" style="transform:translateY(${-12*opening}px)"/>${type==='control-valve'?'<path d="M62 43a28 19 0 0 1 56 0Z" fill="#2b687c" stroke="#9fd6dc"/><path d="M68 47h44" stroke="#9fd6dc" stroke-width="4"/><path class="scada-signal" d="M118 32h30v-17" fill="none" stroke="#63e8dd" stroke-width="2"/>':'<ellipse cx="90" cy="33" rx="29" ry="8" fill="none" stroke="#87d8d7" stroke-width="4"/><path d="M61 33h58M90 25v16" stroke="#b3dfe3" stroke-width="2"/>'}`;
}

function instrument(type,id,state){
 const valid=state.active!==false&&!state.fault&&state.status!=='offline'&&state.connected!==false&&!['broken','disconnected','comms-loss','power-loss'].includes(state.damage);
 const reading=valid?Number(state.value.toFixed(1)).toString():'—';
 if(type==='pressure-transmitter')return `<path d="M90 101v27" stroke="${steel(id)}" stroke-width="11"/><path d="M79 118h22" stroke="#9dcad5" stroke-width="5"/>${dial(90,67,37,Math.abs(state.value)%101)}<circle class="scada-sensor-pulse" cx="90" cy="67" r="45" fill="none" stroke="#4ce5e7" stroke-width="1.5"/><path d="M127 61h30v-25" fill="none" stroke="#6ba4bc" stroke-width="4"/>${display(66,79,48,reading,'kPa')}`;
 if(type==='flow-meter')return `<g class="scada-flow-meter" data-meter-flow="${state.value===0?'stopped':state.value<0?'reverse':'forward'}">${pipe('M8 94H172')}<rect x="52" y="76" width="76" height="37" rx="15" fill="${steel(id)}" stroke="#8fc4d4"/><path d="M48 73v43M132 73v43" stroke="#8dbdcc" stroke-width="5"/><path d="M90 77V60" stroke="#7eb3c7" stroke-width="9"/><rect x="56" y="20" width="68" height="45" rx="7" fill="#275369" stroke="#8dc9d7"/>${display(64,28,52,reading,'m³/h')}<path class="scada-flow" d="M62 95h57" stroke-width="3"/></g>`;
 if(type==='temperature-sensor')return `<path d="M99 64v56" stroke="#badce6" stroke-width="8"/><path d="M99 76v42" stroke="#ffd38a" stroke-width="3"/><circle cx="99" cy="118" r="8" fill="#ffd38a"/><circle class="scada-sensor-pulse" cx="99" cy="117" r="14" fill="none" stroke="#ffc97e"/><rect x="62" y="22" width="74" height="46" rx="12" fill="${steel(id)}" stroke="#a1cbd8"/>${display(74,31,49,reading,'°C')}<path d="M135 43h27" stroke="#76afc5" stroke-width="5"/>`;
 if(type==='level-sensor')return `<path d="M47 42H29v82h108" fill="none" stroke="#7eafc4" stroke-width="4"/><rect x="58" y="16" width="64" height="31" rx="5" fill="${steel(id)}" stroke="#8fc6d5"/><path d="M80 47h20l-3 11H83Z" fill="#386d83"/><path class="scada-sensor-pulse" d="M86 61l-29 50M94 61l29 50M72 83q18 12 36 0M62 101q28 18 56 0" fill="none" stroke="#4fe9df" stroke-width="1.6"/><rect x="38" y="${122-state.level*.6}" width="100" height="${state.level*.6}" fill="url(#${id}-liquid)" opacity=".55"/>${display(68,20,44,reading,'%')}<path d="M145 64h8M145 78h5M145 92h8M145 106h5M145 120h8" stroke="#7cafc2" stroke-width="2"/>`;
 return `<rect x="43" y="15" width="95" height="110" rx="7" fill="${steel(id)}" stroke="#92c5d5"/>${display(60,29,62,reading,'ppm')}<rect x="57" y="64" width="67" height="32" rx="3" fill="#082438"/><path class="scada-trace" d="M61 86h8l5-7 4 10 6-19 7 18 5-9 6 6h16" fill="none" stroke="#62ffd0" stroke-width="2"/><circle class="scada-led" cx="66" cy="108" r="3"/><path d="M43 105H20V78M138 105h21v-27" fill="none" stroke="#8cbdcd" stroke-width="5"/>`;
}

function processAccessory(type,id){
 if(type==='heat-exchanger')return `${pipe('M12 83H40M140 83H168')}<rect x="37" y="44" width="106" height="65" rx="13" fill="${steel(id)}" stroke="#95c8d7"/><rect x="49" y="53" width="82" height="47" rx="8" fill="#092b3d"/><path class="scada-flow scada-hot-flow" d="M12 60H64V71H116V83H64V94H168" fill="none" stroke="#ffd38a" stroke-width="4"/><path class="scada-flow" d="M55 14V116M82 14V116M109 14V116" fill="none" stroke="#58dfe8" stroke-width="3"/><path d="M47 44V108M133 44V108" stroke="#b4d6df" stroke-width="3"/>`;
 return `${pipe('M14 82H59M122 82H168')}<path d="M54 35Q90 9 126 35V105Q90 126 54 105Z" fill="${steel(id)}" stroke="#9cc9d6"/><rect x="66" y="43" width="48" height="61" rx="12" fill="#0e3446" stroke="#74abb9"/>${[52,62,72,82,92].map(y=>`<path d="M72 ${y}h36" stroke="#79c9c4" stroke-dasharray="2 4" stroke-width="3"/>`).join('')}<path class="scada-flow" d="M90 43V104" stroke-width="3"/>${dial(90,27,14)}<path d="M66 115v15M114 115v15" stroke="#4b7d94" stroke-width="5"/>`;
}

function customArt(type,id,state){
 if(['tank','mixing-tank','reactor','clarifier','silo'].includes(type))return vessel(type,id,state);
 if(['heat-exchanger','filter'].includes(type))return processAccessory(type,id);
 if(['submersible-pump','dosing-pump','blower','compressor','motor'].includes(type))return machinery(type,id,state);
 if(['transformer','breaker','busbar','battery','ups','solar-panel'].includes(type))return power(type,id,state);
 if(type.endsWith('-valve'))return valveArt(type,id,state);
 if(['pressure-transmitter','flow-meter','temperature-sensor','level-sensor','gas-analyzer'].includes(type))return instrument(type,id,state);
 if(['plc-rack','plc-cpu','remote-io','hmi','scada-server','network-switch','radio'].includes(type))return renderControlArt(type,{id,state});
 if(type==='pipe')return `${pipe('M13 102H78Q96 102 96 84V35H163')}<path d="M24 91v22M60 91v22M85 55h22M144 24v22" stroke="#b3d7df" stroke-width="4"/>`;
 if(type==='junction')return `${pipe('M10 74H170M90 12V128')}<circle cx="90" cy="74" r="20" fill="${steel(id)}" stroke="#9bd2dc"/><circle cx="90" cy="74" r="9" fill="#0f4b5a" stroke="#6affd2"/><path d="M25 63v22M155 63v22M79 27h22M79 113h22" stroke="#a0cbd8" stroke-width="4"/>`;
 throw new RangeError(`No drawing for ${type}`);
}

let automaticId=0;
/** Pure presentation: callers own readings, interactions and animation state. */
export function renderScadaComponent(type,{id,label,state={},variant,decorative=false,hostState=false}={}){
 const descriptor=getScadaComponent(type,{variant}),current=normalizeScadaState(type,state,{variant});
 if(typeof decorative!=='boolean'||typeof hostState!=='boolean')throw new TypeError('decorative and hostState must be boolean.');
 if(hostState&&variant!==undefined)throw new TypeError('hostState uses the existing twin artwork contract; select variants in standalone mode.');
 if(id!==undefined&&(typeof id!=='string'||!/^[A-Za-z][A-Za-z0-9_-]{0,99}$/.test(id)))throw new TypeError('Component id must start with a letter and contain only letters, numbers, underscore or dash.');
 const instanceId=`scada-${id??`${type}-${++automaticId}`}`;
 // A closed isolation command overrides the supplied position. Keeping the
 // default at 100 preserves the original boolean-only open/closed API.
 if(current.opening!==undefined&&current.open===false)current.opening=0;
 const controlPowerLost=['plc-rack','plc-cpu','remote-io','hmi','scada-server','network-switch','radio'].includes(type)&&current.damage==='power-loss';
 const active=current.active&&!current.fault&&current.status!=='offline'&&current.connected!==false&&!controlPowerLost;
 const electricalSwitch=['breaker','hv-circuit-breaker','disconnect-switch','earthing-switch','capacitor-bank','shunt-reactor','switchgear-panel','gis-bay'].includes(type);
 const flow=active&&(type!=='flow-meter'||current.value!==0)&&current.speed!==0&&current.opening!==0&&(electricalSwitch?!current.open:current.open!==false)&&current.direction!=='idle'&&current.mode!=='stopped'&&current.source!=='off';
 const numericFields=descriptor.stateFields.filter(field=>field.type==='number');
 // Relay VALUE is an observed measurement; controller family alone also covers
 // commanded PLC loads, whose supplied values remain meaningful when offline.
 const instrumentType=descriptor.modelFamily==='sensor'||descriptor.category==='instruments'||['protection-relay','electrical-meter'].includes(type);
 const damagedObservation=['broken','disconnected','comms-loss','power-loss'].includes(current.damage)||(['current-transformer','voltage-transformer'].includes(type)&&current.damage==='insulation-fault');
 const invalidReading=instrumentType&&(!active||damagedObservation);
 const readings=numericFields.map(field=>invalidReading?`, ${field.key} unavailable`:', illustrative '+field.key+' '+current[field.key]+(field.unit||'')).join('');
 const description=`${label??descriptor.label}${variant?` (${descriptor.selectedVariant.label})`:''}. ${current.fault?'Fault':current.status==='offline'?'Offline':current.status==='warning'?`Warning, ${active?'active':'inactive'}`:active?'Active':'Inactive'}${current.open===undefined?'':`, ${current.open&&current.opening!==0?'open':'closed'}`}${readings}${current.damage&&current.damage!=='none'?`, damage: ${current.damage.replaceAll('-',' ')}`:''}.`;
 const gauges=hostState?[]:numericFields;
 const activity=current.speed??current.load??60;
 const visualStyle=hostState?'':` style="--scada-level:${current.level??55};--scada-load:${current.load??60};--scada-flow-opacity:${.95*(current.opening??100)/100};--scada-gauge-height:${gauges.length*13+4}px;--scada-activity-duration:${4-activity*.03}s;--activity-speed:${4-activity*.03}s;--buffer-fraction:${(current.level??55)/100};--scada-level-offset:${(55-(current.level??55))*.68}px;--flame-scale:${.45+(current.load??75)*.007}"`;
 const attrs=`class="scada-component${hostState?' scada-component-host':''}${gauges.length?' scada-component-with-gauges':''}" data-scada-type="${type}" data-scada-instance="${instanceId}"${variant?` data-scada-variant="${esc(variant)}"`:''} data-scada-host-state="${hostState}" data-active="${active}" data-failed="${current.fault}" data-running="${current.running}" data-status="${current.status}" data-flow="${flow}" data-damage="${current.damage||'none'}" data-speed-zero="${current.speed===0}"${instrumentType?` data-reading-valid="${!invalidReading}"`: ''}${current.open===undefined?'':` data-open="${current.open}"`}${current.opening===undefined?'':` data-opening="${current.opening}"`}${current.connected===undefined?'':` data-connected="${current.connected}"`}${visualStyle}`;
 const accessible=decorative?'aria-hidden="true"':`role="img" aria-label="${esc(description)}"`;
 let drawing;
 const explicitGenset=type==='generator'&&variant!==undefined;
 if(explicitGenset){
  drawing=`<svg class="scada-component-svg" viewBox="0 0 180 136" aria-hidden="true" focusable="false">${definitions(instanceId)}<g class="scada-drawing">${renderGensetArt(variant,{id:instanceId,state:current})}</g></svg>`;
 }else if(descriptor.sharedKind){
  const kind=descriptor.sharedKind==='othergas'?'conditioning':descriptor.sharedKind;
  // The other-gas illustration is selected by its canonical id in the legacy
  // renderer. Replace its generated definition prefix to isolate each instance.
  drawing=equipmentArt({id:descriptor.sharedKind==='othergas'?'othergas':instanceId,kind});
  if(descriptor.sharedKind==='othergas')drawing=drawing.replaceAll('twin-art-othergas',`twin-art-${instanceId}`);
 }else{
  const independent=['energy','electrical','nuclear','agriculture'].includes(descriptor.drawingFamily);
  const drawState=independent?current:{...current,active};
  let art;
  if(descriptor.drawingFamily==='industrial')art=renderIndustrialArt(type,{id:instanceId,state:drawState});
  else if(descriptor.drawingFamily==='process')art=renderProcessArt(type,{id:instanceId,state:drawState,variant});
  else if(descriptor.drawingFamily==='agriculture')art=renderAgricultureArt(type,{id:instanceId,state:drawState});
  else if(descriptor.drawingFamily==='nuclear')art=renderNuclearArt(type,{id:instanceId,state:drawState});
  else if(ENERGY_ART_TYPES.includes(type))art=renderEnergyArt(type,{id:instanceId,state:drawState});
  else if(ELECTRICAL_ART_TYPES.includes(type))art=renderElectricalArt(type,{id:instanceId,state:drawState});
  else art=customArt(type,instanceId,drawState);
  drawing=`<svg class="scada-component-svg" viewBox="0 0 180 136" aria-hidden="true" focusable="false">${definitions(instanceId)}<ellipse cx="90" cy="75" rx="83" ry="59" fill="url(#${instanceId}-glow)"/><ellipse cx="90" cy="128" rx="67" ry="5" fill="#030d19" opacity=".65"/><g class="scada-drawing">${art}</g>${!hostState&&!descriptor.drawingFamily?renderDamageArt(type,{state:drawState}):''}</svg>`;
 }
 if(!hostState&&!explicitGenset&&descriptor.sharedKind&&current.damage!=='none')drawing+=`<svg class="scada-damage-overlay" viewBox="0 0 180 136" aria-hidden="true" focusable="false">${renderDamageArt(type,{state:current})}</svg>`;
 const gaugeLabels={temperature:'TEMP',opening:'OPEN',rodPosition:'RODS',primaryFlow:'PRI',secondaryFlow:'SEC',integrity:'INT',pressure:'PRESS',irradiance:'SUN',humidity:'RH',moisture:'MOIST',airflow:'AIR',oxygen:'O₂',position:'POS',current:'CURR'};
 const gaugeMarkup=gauges.length?`<span class="scada-component-gauges" aria-hidden="true">${gauges.map(field=>{
  const unit=field.unit==='index'?'idx':field.unit||'';
  const value=invalidReading?'—':`${Number(current[field.key].toFixed(1))}${unit&&unit!=='%'?' ':''}${unit}`;
  const width=invalidReading?0:100*(current[field.key]-field.min)/(field.max-field.min);
  return `<span data-scada-gauge="${field.key}"${invalidReading?' data-reading-valid="false"':''}><small title="${esc(field.label)}">${esc(field.shortLabel??gaugeLabels[field.key]??field.key.toUpperCase())}</small><i><b style="width:${width}%"></b></i><strong data-scada-reading="${field.key}">${esc(value)}</strong></span>`;
 }).join('')}</span>`:'';
 const condition=!hostState&&(current.fault||current.status==='warning')?`<span class="scada-component-condition" data-condition="${current.fault?'fault':'warning'}" aria-hidden="true"><svg viewBox="0 0 28 28" focusable="false">${current.fault?'<path d="M9 2h10l7 7v10l-7 7H9l-7-7V9Z"/><path d="M9 9l10 10M19 9L9 19"/>':'<path d="M14 2L27 25H1Z"/><path d="M14 10v7m0 4v1"/>'}</svg></span>`:'';
 return `<span ${attrs} ${accessible}>${drawing}${gaugeMarkup}${condition}</span>`;
}
