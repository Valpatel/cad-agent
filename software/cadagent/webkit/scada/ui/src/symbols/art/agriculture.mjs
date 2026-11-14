/** Original agriculture SVG. Draft presentation only: state belongs to an adapter.
 * The canonical wrapper will supply steel/liquid gradients and accessible labels. */
import {getAgricultureDefinition} from '../../catalog/definitions/agriculture.mjs';
const clamp=(value,fallback=0)=>Math.min(100,Math.max(0,Number.isFinite(value)?value:fallback));
const safe=value=>String(value??'agriculture').replace(/[^a-zA-Z0-9_-]/g,'-');
const steel=id=>`url(#${id}-steel)`;
const liquid=id=>`url(#${id}-liquid)`;
const path=(d,stroke='#8bb8ca',width=3,extra='')=>`<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${width}" ${extra}/>`;
const pipe=(d,air=false)=>`${path(d,'#17394e',9)}${path(d,'#82b2c5',5)}${path(d,air?'#b0d9fc':'#66f5d0',1.8,`class="scada-agri-motion scada-agri-flow ${air?'scada-agri-airflow':''}" stroke-dasharray="4 7"`)}`;
const shadow=()=>'<ellipse cx="90" cy="127" rx="68" ry="4" fill="#020c16" opacity=".65"/>';
const foot=(x,y=111)=>path(`M${x} ${y}v13m-6 0h12`,'#79a9ba',4);
const text=(x,y,value,extra='')=>`<text x="${x}" y="${y}" text-anchor="middle" class="scada-agri-label" ${extra}>${value}</text>`;
function leaf(x,y,scale=1){return `<g transform="translate(${x} ${y}) scale(${scale})"><g class="scada-agri-motion scada-agri-leaf"><path d="M0 1V-17" fill="none" stroke="#83d7ad" stroke-width="2"/><path d="M0-5Q-19-5-14-17Q-3-18 0-5M1-9Q18-12 14-24Q3-25 1-9M-1-15Q-10-27-4-32Q7-28-1-15" fill="#4dc69e" stroke="#b6f4cb" stroke-width=".8"/></g></g>`;}
function roots(x,y,height=24){return `<g class="scada-agri-roots">${path(`M${x} ${y}q-5 ${height*.45} 0 ${height}m0-${height*.6}q-11 3-9 ${height*.5}m10-${height*.6}q8 4 7 ${height*.55}`,'#d7d4ad',1.3)}</g>`;}
function bubbles(xs,y,height=44){return `<g class="scada-agri-bubbles">${xs.map((x,i)=>`<circle class="scada-agri-motion scada-agri-bubble" cx="${x}" cy="${y}" r="${1.4+i%3*.6}" fill="#c4f5f2" style="--agri-delay:${i*-.57}s;--agri-rise:${height}px"/>`).join('')}</g>`;}
function drops(xs,y,height=30){return xs.map((x,i)=>`<path class="scada-agri-motion scada-agri-drop" d="M${x} ${y}q-4 6 0 7q4-1 0-7Z" fill="#82f5de" style="--agri-delay:${i*-.37}s;--agri-drop:${height}px"/>`).join('');}
function meter(x,y,value,label,width=38){return `<g><rect x="${x}" y="${y}" width="${width}" height="17" rx="3" fill="#072533" stroke="#679bac"/>${text(x+width/2,y+11,`${label} ${value===null?'—':Math.round(clamp(value))}`)}</g>`;}
function fish(x,y,s=1,flip=false){return `<g class="scada-agri-motion scada-agri-fish" style="--agri-delay:${x*-.021}s"><g transform="translate(${x} ${y}) scale(${flip?-s:s} ${s})"><path d="M-13 0q9-11 24 0q-15 11-24 0l-8 7V-7Z" fill="#a5dee0" stroke="#daf6e6" stroke-width=".6"/><circle cx="7" cy="-1" r="1.3" fill="#0b2637"/><path d="M-3-3l-3 4 4 3" fill="none" stroke="#44798b"/></g></g>`;}
function fan(x,y,r=17){return `<circle cx="${x}" cy="${y}" r="${r+3}" fill="#082837" stroke="#80b3c3"/><g class="scada-agri-motion scada-agri-fan" style="transform-origin:${x}px ${y}px">${[0,90,180,270].map(angle=>`<path d="M${x} ${y}q${r} -${r} ${r} 0q-2 ${r*.35}-${r} 1Z" fill="#9adbdc" transform="rotate(${angle} ${x} ${y})"/>`).join('')}</g><circle cx="${x}" cy="${y}" r="4" fill="#38687d" stroke="#b1d9e2"/>`;}

function fishTank(id,s){const level=clamp(s.level,55),top=107-level*.63;return `${shadow()}${pipe('M7 69H31M149 76H173')}
 <path d="M30 38Q90 17 150 38V108Q90 132 30 108Z" fill="${steel(id)}" stroke="#a3cfd7"/>
 <defs><clipPath id="${id}-fish-water"><path d="M38 43Q90 27 142 43V104Q90 123 38 104Z"/></clipPath></defs>
 <path d="M38 43Q90 27 142 43V104Q90 123 38 104Z" fill="#082b3d"/>
 <g clip-path="url(#${id}-fish-water)"><rect x="38" y="${top}" width="104" height="${107-top+12}" fill="${liquid(id)}"/>
 ${path(`M37 ${top}q14-4 27 0t27 0t27 0t27 0`,'#b4f6e9',1.7,'class="scada-agri-motion scada-agri-wave"')}
 ${level>8?fish(75,Math.max(top+8,77),.7)+fish(110,Math.max(top+16,98),.55,true):''}${level>0?bubbles([45,49,133,137],104,Math.max(5,104-top)):''}</g>
 <ellipse cx="90" cy="38" rx="60" ry="15" fill="none" stroke="#b1dbe0" stroke-width="2"/>
 ${pipe('M19 29V102H47',true)}${path('M43 106h17M135 108v15h23','#8bb9c9',4)}${meter(72,16,s.oxygen,'O₂',40)}`;}
function biofilter(id,s){const level=clamp(s.level,55),height=level*.88,y=118-height;return `${shadow()}${pipe('M7 73H48M133 79H174')}
 <path d="M47 31Q90 12 133 31V110Q90 129 47 110Z" fill="${steel(id)}" stroke="#a2cfda"/><path d="M57 36Q90 23 123 36V106Q90 118 57 106Z" fill="#082b3c"/>
 <defs><clipPath id="${id}-bio-liquid"><path d="M57 36Q90 23 123 36V106Q90 118 57 106Z"/></clipPath></defs><g clip-path="url(#${id}-bio-liquid)"><rect class="scada-biofilter-liquid" x="57" y="${y}" width="66" height="${height}" fill="${liquid(id)}" opacity=".65"/>
 <g class="scada-biofilter-media" data-dry="${level===0}">${Array.from({length:24},(_,i)=>`<g class="scada-agri-motion scada-agri-media" style="--agri-delay:${i*-.17}s"><circle cx="${63+i%6*10}" cy="${48+Math.floor(i/6)*16}" r="4.2" fill="#28748a" stroke="#9ddccb"/><path d="M${60+i%6*10} ${48+Math.floor(i/6)*16}h6" stroke="#b0e5d7"/></g>`).join('')}</g>${level>0?`<defs><clipPath id="${id}-bio-wet"><rect x="57" y="${y}" width="66" height="${height}"/></clipPath></defs><g clip-path="url(#${id}-bio-wet)">${bubbles([64,89,114],115,Math.max(1,height-3))}</g>`:''}</g>
 ${pipe('M21 20V109H78',true)}${path('M62 108h55M90 114v14','#a3ccd6',4)}<ellipse cx="90" cy="31" rx="43" ry="12" fill="none" stroke="#abd6dd"/>${meter(72,7,s.oxygen,'O₂')}`;}
function mediaBed(id,s){const y=109-clamp(s.level,55)*.31;return `${shadow()}${foot(37)}${foot(144)}${pipe('M8 68H26M149 97H172V119')}
 <path d="M24 63l17-10h113l-6 59H32Z" fill="${steel(id)}" stroke="#9dced5"/><path d="M33 69h111l-5 35H39Z" fill="#092b3b"/>
 <defs><clipPath id="${id}-bed"><path d="M33 69h111l-5 35H39Z"/></clipPath></defs><g clip-path="url(#${id}-bed)"><rect x="31" y="${y}" width="116" height="${112-y}" fill="${liquid(id)}"/>
 ${Array.from({length:30},(_,i)=>`<circle cx="${39+i%10*10.7}" cy="${76+Math.floor(i/10)*10}" r="${3+i%2}" fill="${i%3?'#757d69':'#9e9b78'}" stroke="#b8bea0" stroke-width=".5"/>`).join('')}</g>
 ${[51,90,128].map((x,i)=>`${leaf(x,63,.85+i%2*.1)}${roots(x,69,27)}`).join('')}${path('M29 65h120','#c5e2dd',3)}${text(90,122,(s.phase??'holding').toUpperCase())}`;}
function raft(id,s){const y=109-clamp(s.level,55)*.54,raftY=Math.max(49,y-3);return `${shadow()}${pipe('M8 80H29M151 85H174')}
 <path d="M28 48h124v62Q90 129 28 110Z" fill="${steel(id)}" stroke="#a9d1da"/><path d="M36 54h108v52Q90 120 36 106Z" fill="#092b3c"/>
 <defs><clipPath id="${id}-raft-water"><path d="M36 54h108v52Q90 120 36 106Z"/></clipPath></defs><g clip-path="url(#${id}-raft-water)"><rect x="36" y="${y}" width="108" height="${120-y}" fill="${liquid(id)}"/>${[56,89,121].map(x=>roots(x,raftY,Math.min(28,111-raftY))).join('')}${bubbles([44,71,104,136],106,Math.max(8,105-y))}</g>
 <g transform="translate(0 ${raftY-52})"><path d="M35 46h111l-8 13H42Z" fill="#afd7c8" stroke="#e4f4de"/>${[56,89,121].map(x=>`${leaf(x,48,.68)}<ellipse cx="${x}" cy="51" rx="7" ry="3" fill="#1f584f"/>`).join('')}</g>${pipe('M16 32V107H44',true)}${path('M41 109h98','#b0d7d9',3)}`;}
function nft(id,s){
 const load=clamp(s.load,60),wet=clamp(s.moisture,55)/100;
 const window='M32 72L140 83V101L32 90Z';
 const plants=[[48,64],[86,68],[124,72]];
 return `${shadow()}<g class="scada-agri-nft-support">${foot(44,94)}${foot(130,103)}${path('M44 117h86','#365c70',2)}</g>
 ${pipe('M7 81H29')}${pipe('M150 99H164Q171 99 171 106V121')}
 <path d="M26 65L40 55 159 67V94L145 107 26 95Z" fill="${steel(id)}" stroke="#acd4dc" stroke-width="1.6"/>
 <path d="M145 77L159 67V94L145 107Z" fill="#264c5d" stroke="#98bfce"/>
 <path d="M26 65L40 55 159 67 145 77Z" fill="#6b9ca5" stroke="#c3e3df"/>
 <path class="scada-agri-nft-window" d="${window}" fill="#092735" stroke="#79adba" stroke-width="1.2"/>
 <defs><clipPath id="${id}-nft-channel"><path d="${window}"/></clipPath></defs>
 <g clip-path="url(#${id}-nft-channel)">
  <path class="scada-agri-nft-film" d="M31 86L141 97V102L31 91Z" fill="${liquid(id)}" opacity="${(.2+wet*.45).toFixed(2)}"/>
  ${plants.map(([x,y])=>`<g class="scada-agri-nft-root" fill="none" stroke="${wet>.2?'#d9dfba':'#bfa989'}" stroke-width="1.3" stroke-linecap="round">${path(`M${x} ${y+3}v10q-5 8-2 15m3-13q8 7 5 13m-7-10q-6 1-8 6m15-1 4 4`,'currentColor',1.25,'style="color:inherit;stroke:inherit"')}</g>`).join('')}
  ${path('M30 88L143 99','#9cffde',1+load*.02,'class="scada-agri-motion scada-agri-flow scada-agri-nft-stream" stroke-dasharray="7 9"')}
 </g>
 ${path('M26 65L145 77M145 77v30','#d2eae6',1.6)}
 ${plants.map(([x,y])=>`<ellipse cx="${x}" cy="${y}" rx="10" ry="4.5" fill="#153b3e" stroke="#c6e1d6"/><path d="M${x-6} ${y}l2 7h8l2-7" fill="#284c47" stroke="#a0bdab" stroke-width="1"/>${leaf(x,y-1,.8)}`).join('')}
 <g class="scada-agri-nft-connection"><circle cx="27" cy="81" r="4" fill="#255462" stroke="#a2d9d1"/><circle cx="151" cy="99" r="4" fill="#255462" stroke="#a2d9d1"/></g>`;
}
function ebb(id,s){const y=91-clamp(s.level,55)*.19;return `${shadow()}${foot(34,95)}${foot(144,95)}${pipe('M7 104H23V79M151 83H170V115')}
 <path d="M24 63l15-14h119l-10 48H27Z" fill="${steel(id)}" stroke="#9ecbd6"/><path d="M31 69h119l-7 22H33Z" fill="#0b2a3a"/>
 <rect x="34" y="${y}" width="108" height="${93-y}" fill="${liquid(id)}"/>
 ${[43,67,91,115,139].map((x,i)=>`<path d="M${x-8} 60h16l-3 17h-10Z" fill="#3a6d6a" stroke="#a4d9ca"/>${leaf(x,61,.52+(i%2)*.06)}`).join('')}
 <path d="M24 66h130" stroke="#c4dfdf" stroke-width="3"/><rect x="67" y="105" width="50" height="18" rx="3" fill="#153b4e" stroke="#89bec9"/>${text(92,117,(s.phase??'holding').toUpperCase())}`;}
function drip(id,s){return `${shadow()}${pipe('M8 29H156V43M24 117H164')}
 ${[43,88,133].map((x,i)=>`${path(`M${x} 29v18`,'#88b5c8',3)}<path d="M${x-4} 43h8v7h-8Z" fill="#98ccd0"/>${drops([x],52,13)}
 <path d="M${x-18} 81h36l-6 30h-24Z" fill="${steel(id)}" stroke="#9bc8ce"/><ellipse cx="${x}" cy="81" rx="18" ry="6" fill="#626e57" stroke="#b2b99b"/>${leaf(x,80,.8)}${path(`M${x} 111v7`,'#91c3ce',3)}`).join('')}`;}
function aeroponic(id,s){return `${shadow()}${foot(44)}${foot(139)}${pipe('M8 87H31M148 111H171')}
 <path d="M29 44h122v66q-61 22-122 0Z" fill="${steel(id)}" stroke="#a0ccd7"/><path d="M38 50h104v54q-52 19-104 0Z" fill="#082c3c" stroke="#507e93"/>
 <defs><clipPath id="${id}-mist"><path d="M38 50h104v54q-52 19-104 0Z"/></clipPath></defs>
 ${[54,89,125].map(x=>`${leaf(x,42,.77)}${roots(x,48,48)}<ellipse cx="${x}" cy="45" rx="9" ry="3" fill="#173f43" stroke="#9bd1c6"/>`).join('')}
 <g clip-path="url(#${id}-mist)">${[58,90,123].map((x,i)=>`<path class="scada-agri-motion scada-agri-mist" d="M${x} 105l-17-35h34Z" fill="#a3f1df" opacity="${.05+clamp(s.moisture,55)/500}" style="--agri-delay:${i*-.4}s"/>`).join('')}</g>
 ${path('M41 106h99','#9dcad4',4)}${[58,90,123].map(x=>`<path d="M${x-4} 107l4-7 4 7Z" fill="#c8e8e2"/>`).join('')}${path('M31 43h118','#c5e6e6',3)}`;}
function growLight(id,s){const illumination=clamp(s.light,60)/100;return `${shadow()}${path('M47 8v33M134 8v33','#759caf',2)}
 <path class="scada-agri-light-beam" d="M44 57h94l28 65H16Z" fill="#c4f8a3" opacity="${illumination*.18}"/>
 <path d="M30 39h119l9 15-15 11H37L23 54Z" fill="${steel(id)}" stroke="#b3d4db"/><path d="M32 53h117l-9 9H40Z" fill="#193747" stroke="#8cb2c0"/>
 ${Array.from({length:12},(_,i)=>`<rect class="scada-agri-motion scada-agri-light-cell" x="${40+i*8}" y="55" width="5" height="4" rx="1" fill="#dbffc0" opacity="${.15+illumination*.85}" style="--agri-delay:${i*-.13}s"/>`).join('')}
 ${[43,63,84,105,126].map(x=>path(`M${x} 42v8`,'#0c2738',2)).join('')}${path('M149 45h15V17h-15','#ffc986',2)}
 ${[53,89,125].map(x=>path(`M${x} 75v30m-4-5 4 6 4-6`,'#d6fac3',1.4,`class="scada-agri-motion scada-agri-light-ray" opacity="${illumination*.75}"`)).join('')}`;}
function vent(id,s){
 const opening=clamp(s.opening,50),angle=(Math.atan2(49,57)-opening/100*56*Math.PI/180),length=Math.hypot(57,49);
 const hinge=[86,45],depth=[10,-16],edge=[Math.cos(angle)*length,Math.sin(angle)*length];
 const at=(u,v=0)=>[hinge[0]+edge[0]*u+depth[0]*v,hinge[1]+edge[1]*u+depth[1]*v];
 const point=p=>p.map(value=>Number(value.toFixed(2))).join(' '),front=at(1),back=at(1,1),attach=at(.73,.12),base=[111,111];
 const body=[base[0]+(attach[0]-base[0])*.55,base[1]+(attach[1]-base[1])*.55];
 const pane=`M${point(at(.07,.16))}L${point(at(.93,.16))} ${point(at(.93,.84))} ${point(at(.07,.84))}Z`;
 const airY=(front[1]+94)/2;
 let damage='';
 if(s.damage==='panel-damage')damage=path(`M${point(at(.28,.22))}L${point(at(.43,.59))} ${point(at(.53,.3))} ${point(at(.64,.78))} ${point(at(.78,.47))}`,'#ffc7a4',2.2);
 if(s.damage==='actuator-fault')damage=`<circle cx="${body[0]}" cy="${body[1]}" r="7" fill="#4a3543" stroke="#ffc3a5"/>${path(`M${body[0]-3} ${body[1]-3}l6 6m0-6-6 6`,'#ffd1ba',1.6)}`;
 if(s.damage==='stuck')damage=`<path d="M81 40l10 6-5 9-9-6Z" fill="#765347" stroke="#ffcf98"/>${path('M81 45l5 4','#ffe0b5',2)}`;
 return `${shadow()}
 <path d="M26 94L86 45 143 94V123H26Z" fill="#205064" fill-opacity=".17" stroke="#638c9e" stroke-width="1.5"/>
 <path class="scada-agri-vent-aperture" d="M86 45L96 29 153 78 143 94Z" fill="#102e3e" stroke="#476f85"/>
 ${path('M26 94L86 45M26 94h117M26 94v29h117V94M153 78v29l-10 16','#82b0bd',3)}
 <path d="M33 93L82 53V93Z" fill="#2b6674" fill-opacity=".22" stroke="#457b8e"/>
 <g class="scada-agri-vent-air" style="--agri-vent-air:${(opening/100*clamp(s.airflow,50)/100).toFixed(3)}">
  ${path(`M91 113Q91 92 118 86T173 ${airY-9}`,'#a7e6f0',2,'class="scada-agri-motion scada-agri-flow" stroke-dasharray="5 7"')}
  ${path(`M169 ${airY-15}l5 6-8 2`,'#a7e6f0',2)}
 </g>
 <g class="scada-agri-vent-panel" data-vent-opening="${opening}">
  <path d="M${point(hinge)}L${point(front)} ${point(back)} ${point(at(0,1))}Z" fill="${steel(id)}" stroke="#c5e5e8" stroke-width="2" stroke-linejoin="round"/>
  <path d="${pane}" fill="#236272" stroke="#9bd8da" stroke-width="1"/>
  ${path(`M${point(at(.5,.12))}L${point(at(.5,.88))}`,'#b3dce0',1.5)}
  ${path(`M${point(at(.08,.25))}L${point(at(.85,.25))}`,'#d7f5e7',.8,'opacity=".55"')}
 </g>
 <g class="scada-agri-vent-actuator">
  ${path(`M${point(base)}L${point(attach)}`,'#c7e4e4',3.3,'stroke-linecap="round"')}
  ${path(`M${point(base)}L${point(body)}`,'#103143',8,'stroke-linecap="round"')}
  ${path(`M${point(base)}L${point(body)}`,'#73a1b2',5,'stroke-linecap="round"')}
  ${path('M111 111v11','#b6d4d9',3)}
  <circle cx="${attach[0]}" cy="${attach[1]}" r="2.7" fill="#163c4b" stroke="#d4eae3"/>
  <circle cx="111" cy="111" r="3.2" fill="#163c4b" stroke="#d4eae3"/>
 </g>
 ${path('M84 47L98 27','#c9e3dd',4,'stroke-linecap="round"')}<circle cx="86" cy="45" r="3" fill="#214759" stroke="#d2e7df"/>
 ${damage?`<g class="scada-agri-damage" data-agri-damage="${s.damage}">${damage}</g>`:''}`;
}
function shade(id,s){const width=126*(1-clamp(s.opening,50)/100);return `${shadow()}${path('M26 27v96M152 27v96M26 28h126M26 104h126','#83afc1',4)}
 <defs><pattern id="${id}-mesh" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 0l8 8M8 0L0 8" stroke="#81c3b4" stroke-width=".8"/></pattern></defs>
 <rect x="29" y="32" width="${width}" height="70" fill="#163e42"/><rect x="29" y="32" width="${width}" height="70" fill="url(#${id}-mesh)"/><path d="M${29+width} 32v70" stroke="#a9d9cb" stroke-width="3"/>
 <rect x="18" y="24" width="15" height="84" rx="7" fill="${steel(id)}" stroke="#a4cbd6"/>
 ${[53,87,121].map(x=>path(`M${x} 9v13M${x} 109v11m-3-4 3 5 3-5`,'#d0f3ae',1.5,`class="scada-agri-motion scada-agri-light-ray" opacity="${.2+clamp(s.light,50)*.008}"`)).join('')}`;}
function pad(id,s){const wet=s.damage==='dry-pad'?0:clamp(s.moisture,60)/100;return `${shadow()}${pipe('M8 29H142V37M45 117H11')}
 <rect x="46" y="35" width="91" height="79" rx="3" fill="${steel(id)}" stroke="#adced8"/><rect x="54" y="42" width="75" height="65" fill="#173b40"/>
 <defs><pattern id="${id}-pad" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M0 0l12 12M12 0L0 12" stroke="#7fac97" stroke-width="1.7"/></pattern></defs><rect x="54" y="42" width="75" height="65" fill="url(#${id}-pad)"/>
 <rect x="54" y="42" width="75" height="65" fill="#57e7c5" opacity="${wet*.27}"/>${wet>0?drops([63,84,106,122],43,48):''}
 <path d="M39 112h104l-6 12H45Z" fill="${steel(id)}" stroke="#b2d3db"/><path d="M49 116h82" stroke="#6bf2cf" stroke-width="4" opacity="${wet}"/>
 ${[59,81,101].map(y=>pipe(`M8 ${y}H35M146 ${y}H174`,true)).join('')}`;}
function dehumidifier(id,s){return `${shadow()}${foot(46,115)}${foot(136,115)}
 <rect x="31" y="28" width="119" height="88" rx="8" fill="${steel(id)}" stroke="#a4cfda"/><rect x="39" y="37" width="102" height="70" rx="4" fill="#0b2b3e"/>
 ${fan(66,62,18)}${[99,109,119,129].map(x=>path(`M${x} 43v39`,'#91d2d3',3)).join('')}${[47,57,67,77].map(y=>path(`M94 ${y}h40`,'#76aab6',1)).join('')}
 <rect x="47" y="87" width="40" height="17" rx="3" fill="#143b4b" stroke="#7cbdc7"/><rect x="49" y="${102-clamp(s.level,55)*.12}" width="36" height="${clamp(s.level,55)*.12}" fill="${liquid(id)}"/>
 ${drops([108,125],82,10)}${pipe('M110 104V122H169')}${path('M8 58h20M153 58h19','#b3e2ee',3,'class="scada-agri-motion scada-agri-flow" stroke-dasharray="4 5"')}`;}
function qualityProbe(id,s){const kind={ph:'pH',ec:'EC',do:'O₂'}[s.measurement]??'O₂';return `${shadow()}${path('M81 28V12H133V37','#749fb4',4)}
 <rect x="48" y="25" width="67" height="37" rx="8" fill="${steel(id)}" stroke="#abd4df"/><rect x="57" y="33" width="49" height="21" rx="4" fill="#082b3a"/>${text(81,47,`${kind} ${s.__valid?Math.round(clamp(s.value,60)):'—'}`)}
 <path d="M73 62h16v46l-8 12-8-12Z" fill="${steel(id)}" stroke="#9bc3d2"/><path d="M77 71v32M85 71v32" stroke="#d5ece8"/>
 <path d="M39 92q19-6 39 0t40 0t22 0v34H39Z" fill="#43c8bf" opacity=".15"/>${path('M38 92q19-6 39 0t40 0t22 0','#79d9d2',1.5,'class="scada-agri-motion scada-agri-wave"')}
 <circle class="scada-agri-monitor" cx="104" cy="28" r="2" fill="#7ff1c9"/>` ;}
function humidity(id,s){return `${shadow()}${path('M92 21V9h42','#779bad',3)}
 <path d="M60 25h61l9 78H51Z" fill="${steel(id)}" stroke="#b0d4dd"/>
 ${[38,48,58,68].map(y=>path(`M64 ${y}h51`,'#163a4c',5)).join('')}
 <rect x="61" y="79" width="58" height="18" rx="4" fill="#082b3a"/>${text(90,91,`RH ${s.__valid?Math.round(clamp(s.humidity,55)):'—'}`)}
 <path d="M40 72q-13 17 0 20q13-3 0-20Z" fill="#91d9e8" opacity=".85"/>
 ${path('M81 104v17m18-17v17M71 122h38','#90b8c7',4)}${path('M139 43q8 7 0 14t0 14','#8bcacb',1.8,'class="scada-agri-motion scada-agri-sensor-wave"')}`;}
function lightSensor(id,s){return `${shadow()}${path('M90 77v44M63 123h54','#8ebac9',6)}
 <path d="M60 61Q60 41 90 41T120 61v18H60Z" fill="${steel(id)}" stroke="#b2d9e0"/><ellipse cx="90" cy="58" rx="31" ry="12" fill="#d8f0d7" stroke="#f1f8e9"/><ellipse cx="90" cy="58" rx="22" ry="7" fill="#95baaf"/>
 ${[[90,10,90,30],[52,20,66,36],[128,20,114,36],[34,53,49,56],[146,53,131,56]].map(([a,b,c,d])=>path(`M${a} ${b}L${c} ${d}`,'#daf9b6',2,`class="scada-agri-motion scada-agri-light-ray" opacity="${.15+clamp(s.light,60)*.0085}"`)).join('')}
 ${meter(69,91,s.__valid?s.light:null,'PAR',43)}`;}
function diffuser(id,s){return `${shadow()}${pipe('M8 112H67V102',true)}
 <path d="M42 95Q90 80 139 95v12q-49 18-97 0Z" fill="${steel(id)}" stroke="#b5d8e1"/><ellipse cx="90" cy="95" rx="49" ry="13" fill="#28748a" stroke="#8fd4d4"/>
 ${Array.from({length:24},(_,i)=>`<circle cx="${51+i%8*11}" cy="${89+Math.floor(i/8)*5}" r="1" fill="#c5eddf"/>`).join('')}
 ${bubbles([51,64,77,91,105,117,130],87,64)}${path('M25 29q17-5 34 0t34 0t34 0t30 0','#638fa5',1.5,'opacity=".5"')}`;}

function damageArt(type,s){const mode=s.damage??'none';if(mode==='none'||type==='greenhouse-vent')return'';let art='';
 const x=type==='fish-tank'?140:type==='grow-light'?130:134,y=type==='grow-light'?51:96;
 if(['leaking','cracked'].includes(mode))art=path(`M${x-6} ${y-18}l-5 8 8 5-7 7 6 5`,'#ffd2b3',2.3)+(mode==='leaking'?`${path(`M${x} ${y}q21 4 25 29`,'#8ff3df',2,'class="scada-agri-incident scada-agri-leak" stroke-dasharray="3 4"')}<ellipse cx="152" cy="128" rx="18" ry="3" fill="#5edbc8" opacity=".7"/>`:'');
 else if(['blocked','blocked-drain','nozzle-fault'].includes(mode)){const pos=mode==='blocked-drain'?[139,119]:mode==='nozzle-fault'?[91,103]:type==='drip-zone'?[43,47]:type==='air-diffuser'?[65,99]:[30,81];art=`<circle cx="${pos[0]}" cy="${pos[1]}" r="9" fill="#513e48" stroke="#efb68a"/>${path(`M${pos[0]-6} ${pos[1]-6}l12 12m0-12-12 12`,'#ffd0b2',2)}`;}
 else if(['fouled','dry-pad','condensation','iced-coil','occluded'].includes(mode)){
  if(mode==='occluded')art='<path d="M57 57q14-17 29-7t36 6l-3 13H60Z" fill="#675e4f" stroke="#afa485"/>';
  else if(mode==='iced-coil')art=path('M96 41l9 9-7 11 10 8-9 12M119 42l12 12-13 10 11 16','#e5f7ff',5);
  else if(mode==='condensation')art=drops([65,88,111],56,13).replaceAll('scada-agri-motion','scada-agri-incident');
  else{const centers=type==='air-diffuser'?[61,91,18,8]:type==='media-grow-bed'?[47,76,22,13]:type==='nft-channel'?[53,80,26,7]:type==='water-quality-probe'?[77,82,2.5,13]:[61,58,17,21];art=`<g fill="${mode==='dry-pad'?'#b49462':'#a59765'}" stroke="#d1be8f" opacity=".85">${[0,1,2,3,4,5,6,7].map(i=>`<circle cx="${centers[0]+i%4*centers[2]}" cy="${centers[1]+Math.floor(i/4)*centers[3]}" r="${type==='water-quality-probe'?1.8:3+i%3}"/>`).join('')}</g>`;}
 }else if(['stuck','timer-stall','actuator-fault','driver-fault','compressor-fault'].includes(mode))art=`<rect x="108" y="72" width="28" height="23" rx="4" fill="#433442" stroke="#f4bd91"/>${path('M114 77l16 13m0-13-16 13','#ffd2b3',2)}`;
 else if(['torn','panel-damage'].includes(mode))art='<path d="M71 52l13 9-7 16 16-9 12 20 8-20-16-17 5-14-19 8Z" fill="#0a1d2e" stroke="#d4c1a7" stroke-width="2"/>';
 else if(['disconnected','air-loss'].includes(mode))art=path('M24 32l19 18m0-18-19 18M17 45h11m10-14v-9','#ffbfac',2.5);
 else if(mode==='uneven-feed')art=path('M125 46l15 12m0-12-15 12','#ffd0a0',2.3);
 else if(mode==='drift')art=path('M121 69l8-14 7 7 10-23M137 42l9-3 1 9','#ffd08a',2.2);
 else if(['overheated','burnt'].includes(mode)){art=path('M64 38q-8-10 0-20M88 33q-8-10 0-20M113 39q8-10 0-20','#ffb18f',3,'class="scada-agri-incident scada-agri-heat"');if(mode==='burnt')art+='<path d="M96 39l18 3 20 9-15 12-24-7-10-10Z" fill="#30282d" stroke="#845f55"/>';}
 return `<g class="scada-agri-damage" data-agri-damage="${mode}">${art}</g>`;
}
const artByType={'fish-tank':fishTank,biofilter,'media-grow-bed':mediaBed,'dwc-raft-bed':raft,'nft-channel':nft,'ebb-flow-table':ebb,'drip-zone':drip,'aeroponic-chamber':aeroponic,'grow-light':growLight,'greenhouse-vent':vent,'shade-screen':shade,'evaporative-pad':pad,dehumidifier,'water-quality-probe':qualityProbe,'humidity-sensor':humidity,'light-sensor':lightSensor,'air-diffuser':diffuser};
export function renderAgricultureArt(type,{id,state={}}={}){
 const descriptor=getAgricultureDefinition(type),prefix=safe(id),normalized={...Object.fromEntries(descriptor.fields.map(field=>[field.key,field.default])),...state};
 for(const field of descriptor.fields)if(field.type==='select'&&!field.options.some(option=>option.value===normalized[field.key]))throw new TypeError(`Invalid ${type} ${field.key}.`);
 const damaged=['blocked','timer-stall','stuck','actuator-fault','driver-fault','compressor-fault','disconnected','air-loss','burnt'].includes(normalized.damage);
 normalized.__valid=state.active!==false&&state.connected!==false&&state.status!=='offline'&&!state.fault&&normalized.damage!=='disconnected';
 const active=normalized.__valid&&!damaged;
 const value=normalized.load??normalized.airflow??normalized.light??normalized.moisture??normalized.opening??normalized.value??normalized.humidity??60;
 const moving=active&&clamp(value)>0&&(type!=='greenhouse-vent'||clamp(normalized.opening)>0),running=state.running!==false;
 return `<g class="scada-agri-art" data-agri-type="${type}" data-agri-active="${moving}" data-agri-running="${running}" data-agri-phase="${normalized.phase??'continuous'}" style="--agri-duration:${(3.8-clamp(value)*.028).toFixed(2)}s;--agri-air-opacity:${(clamp(normalized.airflow??normalized.oxygen??value)/100).toFixed(2)}">${artByType[type](prefix,normalized)}${damageArt(type,normalized)}</g>`;
}
