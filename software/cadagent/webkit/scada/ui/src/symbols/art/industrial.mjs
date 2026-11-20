/** Original manufacturing and solids-handling illustrations, 180 × 136 units.
 * Inner SVG only: the component renderer supplies instance-scoped definitions,
 * accessible labels and normalized visual state. No process model or timers. */
const steel=id=>`url(#${id}-steel)`;
const clamp=value=>Number.isFinite(value)?Math.max(0,Math.min(100,value)):0;
const shadow=(x=90,y=124,rx=72)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="5" fill="#020d18" opacity=".7"/>`;
const legs=(xs,y=102,height=20)=>xs.map(x=>`<path d="M${x} ${y}v${height}m-5 0h10" fill="none" stroke="#6799ad" stroke-width="4" stroke-linecap="round"/>`).join('');
const bolts=points=>points.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="1.5" fill="#bad9e2"/><path d="M${x-1} ${y}h2" stroke="#294e65" stroke-width=".7"/>`).join('');
const panel=(x,y,w=22)=>`<rect x="${x}" y="${y}" width="${w}" height="18" rx="2" fill="#0a2434" stroke="#6b9cae"/><path class="scada-industrial-readout" d="M${x+4} ${y+6}h${w-8}m-${w-8} 5h${(w-8)*.65}" stroke="#62ffbc" stroke-width="2"/><circle class="scada-led" cx="${x+w-4}" cy="${y+13}" r="1.6" fill="#477082"/>`;
const motor=(id,x,y,w=27)=>`<rect x="${x}" y="${y}" width="${w}" height="20" rx="4" fill="${steel(id)}" stroke="#8ec3d2"/><path d="M${x+7} ${y+3}v14m5-14v14m5-14v14" stroke="#335e77" stroke-width="2"/><rect x="${x-4}" y="${y+4}" width="5" height="12" rx="1" fill="#244b63" stroke="#78a9bd"/>`;
const wheel=(cx,cy,r=11,reverse=false)=>`<circle cx="${cx}" cy="${cy}" r="${r}" fill="#173b51" stroke="#93c5d1" stroke-width="1.5"/><g class="scada-industrial-motion scada-industrial-rotate${reverse?' scada-industrial-reverse':''}" style="transform-origin:${cx}px ${cy}px"><path d="M${cx-r+3} ${cy}h${2*r-6}M${cx} ${cy-r+3}v${2*r-6}" stroke="#65c6cc" stroke-width="2.5"/><circle cx="${cx}" cy="${cy}" r="3" fill="#c8f4ee"/></g>`;
const belt=(id,x=15,y=97,w=150)=>`<rect x="${x}" y="${y}" width="${w}" height="15" rx="7.5" fill="#0c2639" stroke="#76aabd" stroke-width="1.6"/><path class="scada-industrial-motion scada-industrial-belt" d="M${x+8} ${y+3}H${x+w-8}M${x+w-8} ${y+12}H${x+8}" fill="none" stroke="#7cafa9" stroke-width="2" stroke-dasharray="4 9"/>${wheel(x+8,y+7.5,5)}${wheel(x+w-8,y+7.5,5)}${legs([x+18,x+w-18],y+15,11)}`;
const hopper=(id,x=45,y=18,w=65,h=44)=>`<path d="M${x} ${y}h${w}l-${w*.32} ${h}h-${w*.36}Z" fill="${steel(id)}" stroke="#a0ced8" stroke-width="1.4"/><path d="M${x+4} ${y+4}h${w-8}l-${w*.18} ${h*.4}h-${w*.64-8}Z" fill="#133d4d"/><path class="scada-industrial-inventory" d="M${x+8} ${y+8}h${w-16}l-${w*.11} ${h*.23}h-${w*.78-16}Z" fill="#81c7b8" opacity=".75"/>`;
const bottle=(x,y,color='#57dcc4')=>`<path d="M${x+4} ${y}h6v5l4 5v24H${x}V${y+10}l4-5Z" fill="#163f50" stroke="#9bcfd6"/><path d="M${x+2} ${y+17}h10v15H${x+2}Z" fill="${color}" opacity=".7"/><path d="M${x+4} ${y-1}h6" stroke="#d4e3dc" stroke-width="3"/>`;
const carton=(x,y,w=20,h=23)=>`<path d="M${x} ${y+5}l5-5h${w-5}v${h}H${x}Z" fill="#b69e78" stroke="#ecdec0"/><path d="M${x} ${y+5}h${w}M${x+w*.55} ${y+1}v${h-1}" stroke="#756d5b"/><path d="M${x+4} ${y+11}h5m-5 4h8" stroke="#e8e1c9" stroke-width="1.5"/>`;
const heatingCoil=(x,y,w)=>`<path d="M${x} ${y}h${w}" stroke="#5b524b" stroke-width="4"/><g class="scada-industrial-hot-window"><path class="scada-industrial-motion scada-oven-coil" d="M${x} ${y}${Array.from({length:Math.max(2,Math.floor(w/8))},()=>`l2-3 4 6 2-3`).join('')}" fill="none" stroke="#ffbb73" stroke-width="1.7" stroke-linejoin="round"/></g>`;
const hotWindow=(x,y,w,h)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="#392b24" stroke="#b9b290"/><g class="scada-industrial-hot-window"><rect x="${x+3}" y="${y+3}" width="${w-6}" height="${h-6}" rx="2" fill="#b55e39" opacity=".6"/><path d="M${x+7} ${y+h-6}q-3-6 0-12m8 12q-3-6 0-12m8 12q-3-6 0-12" fill="none" stroke="#ffcf86" stroke-width="2"/></g>`;

function conveyor(id){return `${shadow()}
 <path d="M24 93L48 119H134L156 93M48 119l22-26 23 26 22-26 19 26" fill="none" stroke="#4b7890" stroke-width="3"/>
 <rect x="13" y="76" width="154" height="23" rx="11.5" fill="${steel(id)}" stroke="#98c8d4" stroke-width="1.6"/>
 <path class="scada-industrial-motion scada-industrial-belt" d="M25 79H155M155 96H25" fill="none" stroke="#1f4b5a" stroke-width="3" stroke-dasharray="5 8"/>
 ${wheel(25,87.5,8)}${wheel(155,87.5,8)}${[53,79,105,131].map(x=>wheel(x,88,5)).join('')}
 <g class="scada-industrial-motion scada-industrial-products scada-industrial-material">${[32,65,98,131].map((x,i)=>`<path d="M${x} 75l3-12 10-${i%2?8:3} 11 9-4 6Z" fill="${i%2?'#8cafb0':'#7fbba7'}" stroke="#c8e3cf" stroke-width="1.2"/>`).join('')}</g>
 <path d="M19 70v-9m142 9v-9" stroke="#75a9b8" stroke-width="3"/>${motor(id,119,104,30)}${panel(19,103,24)}`;}

function crusher(id){return `${shadow()}
 ${legs([40,118],105,18)}<path d="M34 40H130V105H34Z" fill="${steel(id)}" stroke="#a1cbd7" stroke-width="1.6"/>
 ${hopper(id,35,15,90,31)}
 <path d="M47 44H117L101 97H73Z" fill="#0b2636" stroke="#638d9f"/>
 <path class="scada-crusher-fixed-jaw" d="M48 46l11 5-5 5 11 4-5 5 11 4-4 5 10 4-3 5 9 5-5 8H71Z" fill="#799eac" stroke="#c6e1e3" stroke-width="1.2"/>
 <g class="scada-industrial-motion scada-crusher-moving-jaw"><path d="M115 46l-11 5 5 5-10 5 5 5-10 5 4 5-9 5 4 5-7 10h14Z" fill="#527e91" stroke="#b9dce1" stroke-width="1.2"/><circle cx="112" cy="46" r="3" fill="#d5efeb"/></g>
 <g class="scada-industrial-material"><path d="M72 48l7-8 11 4 4 10-12 5Z" fill="#a7d5bb" stroke="#d8ead3"/><path class="scada-industrial-motion scada-industrial-fall" d="M82 65l6-5 7 5-3 7-7 1Z" fill="#84bfa9" stroke="#c9e8cc"/></g>
 <path d="M76 98h27v13l-15 6-12-6Z" fill="#244a5c" stroke="#99c4cc"/><g class="scada-industrial-motion scada-industrial-fall scada-industrial-material"><path d="M82 114l4-3 4 4-4 4Zm12 1 4-2 3 4-5 3Z" fill="#b1dfbf"/></g>
 <path d="M130 63h14M145 84v15" fill="none" stroke="#82b5c4" stroke-width="5"/>${wheel(145,66,17)}<circle cx="145" cy="66" r="20" fill="none" stroke="#527f93" stroke-width="2"/>
 ${motor(id,129,99,34)}${panel(39,84,23)}${bolts([[38,44],[126,44],[38,101],[126,101]])}`;}

function vibratingScreen(id){return `${shadow()}
 <path d="M24 104v18h18M132 114v8h20" fill="none" stroke="#628fa4" stroke-width="5"/>
 <g class="scada-screen-support-springs" fill="none" stroke="#b2cdd4" stroke-width="2"><path d="M24 83l-5 4 10 4-10 4 10 4-5 5M139 96l-5 4 10 4-10 4 5 6"/></g>
 <g class="scada-industrial-motion scada-industrial-vibrate">
 <path d="M17 57L145 76V91L17 72Z" fill="${steel(id)}" stroke="#9ec9d3" stroke-width="1.5"/>
 <path d="M17 57L32 33 160 52 145 76Z" fill="#123e4d" stroke="#a6d3d8" stroke-width="1.6"/>
 ${[0,1,2,3,4,5,6,7].map(i=>`<path d="M${31+i*16} ${36+i*2.4}l-10 18" stroke="#527f91" stroke-width="1"/>`).join('')}
 <path d="M28 43L152 61M23 51L148 69" stroke="#79aab4" stroke-width="1.2"/>
 <path d="M18 65L145 84" stroke="#91c4c6" stroke-width="2" stroke-dasharray="3 4"/>
 <g class="scada-industrial-material scada-industrial-motion scada-screen-stones">${[[42,44],[63,47],[83,52],[108,54],[130,63]].map(([x,y],i)=>`<path d="M${x} ${y}l4-${i%2?5:7} 7 3-1 6-7 2Z" fill="#a5cfb7" stroke="#d8e8cf" stroke-width="1"/>`).join('')}</g>
 <path class="scada-screen-fines-chute" d="M42 77L123 89 96 109H74Z" fill="#2d586d" stroke="#81b1bf" stroke-width="1.3"/><path d="M74 109h22v7H74Z" fill="#1b4052" stroke="#93bcc8"/>
 <path class="scada-screen-coarse-chute" d="M145 78l22 8v13l-22-8Z" fill="#47758a" stroke="#a6ccd4"/>
 <circle cx="92" cy="79" r="9" fill="#264d63" stroke="#b0d5d8" stroke-width="1.4"/>${wheel(92,79,6)}
 </g><g class="scada-industrial-motion scada-industrial-fall scada-industrial-material"><circle cx="79" cy="119" r="1.8" fill="#b0dec0"/><circle cx="88" cy="120" r="1.6" fill="#9fceb2"/><path d="M164 102l4-2 3 5-5 2Z" fill="#a5cfb7"/></g>`;
}

function grindingMill(id){return `${shadow()}
 ${legs([48,126],100,23)}<path d="M42 42H128Q155 45 155 74T128 106H42Z" fill="${steel(id)}" stroke="#a4d1dc" stroke-width="1.5"/>
 <path d="M65 42v64m56-64v64" stroke="#c2dce0" stroke-width="6"/><path d="M65 42v64m56-64v64" stroke="#345f75" stroke-width="2"/>
 <ellipse cx="42" cy="74" rx="25" ry="32" fill="#163b50" stroke="#a1d0d8" stroke-width="2"/>
 <g class="scada-industrial-motion scada-industrial-rotate" style="transform-origin:42px 74px"><ellipse cx="42" cy="74" rx="19" ry="25" fill="#0e293b" stroke="#4f8298"/><path d="M42 50v48M23 74h38M28 57l28 34M28 91l28-34" stroke="#679aac" stroke-width="3"/><circle cx="42" cy="74" r="6" fill="#93ddd3"/></g>
 <path d="M75 56h34m-34 12h34m-34 12h34m-34 12h34" stroke="#29596e" stroke-width="2"/>
 <path d="M8 53H27V65M151 79h16v23" fill="none" stroke="#719cae" stroke-width="9" stroke-linejoin="round"/>${motor(id,91,106,31)}${panel(78,19,32)}
 <g class="scada-industrial-motion scada-industrial-fall scada-industrial-material"><circle cx="165" cy="109" r="3" fill="#a3d7bd"/><circle cx="158" cy="115" r="2" fill="#81bdab"/></g>`;}

function rotaryKiln(id){return `${shadow()}
 <path d="M37 95v25m91-33v33M26 120h112" stroke="#527f95" stroke-width="5"/>
 <path d="M18 70L139 35Q157 29 165 52T151 82L31 110Z" fill="${steel(id)}" stroke="#a0ced8" stroke-width="1.7"/>
 <path d="M46 63l12 40m63-57 12 41" stroke="#b4d2d6" stroke-width="7"/><path d="M46 63l12 40m63-57 12 41" stroke="#2c566c" stroke-width="2"/>
 <path class="scada-industrial-motion scada-industrial-belt" d="M64 65L114 53M69 85L119 73" stroke="#426f84" stroke-width="3" stroke-dasharray="7 5"/>
 <ellipse cx="27" cy="90" rx="16" ry="21" transform="rotate(-15 27 90)" fill="#203341" stroke="#b3d3d8" stroke-width="2"/>
 <ellipse class="scada-industrial-hot-window" cx="27" cy="90" rx="10" ry="15" transform="rotate(-15 27 90)" fill="#db8651" stroke="#ffd19a"/>
 <path d="M141 35V18h14V37" fill="#315e73" stroke="#8bbac7"/><path class="scada-industrial-motion scada-industrial-exhaust" d="M145 15q-3-6 1-11m7 11q4-5 1-10" fill="none" stroke="#a6bbc5" stroke-width="3" opacity=".5"/>
 ${wheel(53,112,7)}${wheel(131,99,7)}${motor(id,68,108,28)}${panel(94,87,21)}`;}

function oven(id){return `${shadow()}
 ${legs([39,143],103,20)}<path d="M33 34L43 24H139L149 34Z" fill="#547c8b" stroke="#b1d2d8"/>
 <rect x="33" y="34" width="116" height="70" rx="5" fill="${steel(id)}" stroke="#aad1db" stroke-width="1.5"/>
 <path d="M56 24V14h13v10m43 0V14h13v10" fill="#2c5268" stroke="#8bb5c2"/>
 <path d="M39 43H143V94H39Z" fill="#142432" stroke="#8eb7bf"/>
 <rect class="scada-industrial-hot-window" x="42" y="45" width="98" height="46" rx="2" fill="#b9673c" opacity=".32"/>
 <g class="scada-oven-upper-coils">${heatingCoil(48,51,84)}</g>
 <g class="scada-oven-lower-coils">${heatingCoil(48,87,84)}</g>
 <rect x="10" y="71" width="160" height="9" rx="4.5" fill="#244456" stroke="#a1c7ce" stroke-width="1.5"/>
 <path class="scada-industrial-motion scada-industrial-belt" d="M16 73H164M164 78H16" fill="none" stroke="#b4d4d3" stroke-width="1.5" stroke-dasharray="2 4"/>
 ${wheel(15,75.5,3)}${wheel(165,75.5,3)}
 <defs><clipPath id="${id}-oven-travel"><rect x="10" y="56" width="160" height="16"/></clipPath></defs>
 <g clip-path="url(#${id}-oven-travel)"><g class="scada-industrial-motion scada-oven-trays scada-industrial-material">${[5,35,65,95,125,155].map(x=>`<path d="M${x} 68h21l-2 2H${x+2}Z" fill="#c1d9dc" stroke="#779eac" stroke-width=".7"/><path d="M${x+5} 67v-7h11v7" fill="#beaa82" stroke="#efd7a7" stroke-width="1"/>`).join('')}</g></g>
 <path d="M34 40v29m114-29v29" stroke="#c4dadd" stroke-width="3"/>
 ${panel(75,106,30)}<path class="scada-industrial-motion scada-industrial-exhaust" d="M62 11q-4-4 0-8m56 8q4-4 0-8" fill="none" stroke="#a4b9bd" stroke-width="2" opacity=".5"/>`;
}

function rackOven(id,state){const open=state.open===true;return `${shadow(90,127,62)}
 ${legs([43,137],115,10)}<path d="M36 25L46 16H139L149 25V115L139 121H36Z" fill="#284e64" stroke="#8fbcc9" stroke-width="1.5"/>
 <rect x="36" y="25" width="103" height="96" rx="4" fill="${steel(id)}" stroke="#afd4dc" stroke-width="1.5"/>
 <path d="M61 16V8h25v8" fill="#335c70" stroke="#98c1cc"/>
 <rect x="43" y="33" width="68" height="78" rx="3" fill="#132b3a" stroke="#96bec7"/>
 <rect class="scada-industrial-hot-window" x="46" y="36" width="62" height="72" rx="2" fill="#b9663a" opacity=".3"/>
 <path d="M52 40V105M102 40V105" stroke="#99bac4" stroke-width="2"/>
 <g class="scada-rack-oven-shelves">${[48,66,84,102].map(y=>`<path d="M50 ${y}h54" stroke="#bad4d8" stroke-width="2"/><path d="M56 ${y-2}v-7h16v7m9 0v-7h15v7" fill="#a69b79" stroke="#dece9f" stroke-width="1"/>`).join('')}</g>
 <path class="scada-industrial-motion scada-industrial-air" d="M48 101V40M106 40V101" fill="none" stroke="#a5e5d8" stroke-dasharray="3 7" stroke-width="1.3"/>
 <g class="scada-rack-oven-door" data-door-open="${open}" transform="${open?'matrix(-.35 .08 0 1 55.35 -3.28)':'translate(0 0)'}"><rect x="41" y="31" width="72" height="82" rx="3" fill="${open?steel(id):'#80bec51c'}" stroke="#bad7db" stroke-width="2"/><rect x="47" y="37" width="56" height="70" rx="2" fill="${open?'#1b394b':'#07253126'}" stroke="#618d9f"/><path d="M107 63v20" stroke="#d5e8e7" stroke-width="3" stroke-linecap="round"/></g>
 ${panel(116,37,18)}<path d="M120 64h10m-10 6h10m-10 6h10m-10 6h10" stroke="#32566d" stroke-width="2"/>
 <g class="scada-rack-oven-elements">${heatingCoil(118,94,13)}</g>
 <g class="scada-industrial-element-fault"><path d="M121 90l7 7m-7 0 7-7" stroke="#ff9cbe" stroke-width="2"/><path d="M121 105h8" stroke="#343a43" stroke-width="3"/></g>
 <g class="scada-industrial-door-leak"><path d="M109 53q10-4 16 0m-16 7q10-4 19 0m-19 7q11-4 16 0" fill="none" stroke="#ffd3a1" stroke-width="1.5"/><path d="M110 48v24" stroke="#ffad9b" stroke-width="2"/></g>`;
}

function dryer(id){return `${shadow(90,126,61)}
 ${legs([46,130],109,15)}<path d="M35 30L46 20H137L146 30V110L137 118H35Z" fill="#274f67" stroke="#8bb8c9"/><rect x="35" y="30" width="102" height="88" rx="4" fill="${steel(id)}" stroke="#b4d7df" stroke-width="1.5"/>
 <rect x="43" y="40" width="62" height="65" rx="2" fill="#153447" stroke="#81abb9"/>
 <g class="scada-industrial-hot-window">${[0,1,2,3,4].map(i=>`<path d="M49 ${48+i*11}h50" stroke="#d1a770" stroke-width="3"/>`).join('')}</g>
 <path class="scada-industrial-motion scada-industrial-air" d="M53 99V44M73 99V44M93 99V44" stroke="#8de0d5" stroke-width="1.5" stroke-dasharray="4 8" opacity=".7"/>
 ${panel(111,41,20)}<path d="M116 67h10m-10 6h10m-10 6h10m-10 6h10" stroke="#335b71" stroke-width="2"/>
 <path d="M65 20V9h33v11" fill="#325c71" stroke="#8cb9c7"/>${wheel(81.5,18,12)}
 <path d="M146 69h14v34h-14" fill="#23475e" stroke="#709faf"/><path class="scada-industrial-motion scada-industrial-exhaust" d="M155 63q-5-7 0-15m8 12q3-6 0-11" fill="none" stroke="#9ebbc4" stroke-width="2"/>`;
}

function extruder(id){return `${shadow()}
 <path d="M35 102H153V118H35Z" fill="#1d4056" stroke="#7baaba"/>${legs([44,144],118,6)}
 ${motor(id,13,73,34)}<path d="M47 73H145V98H47Z" fill="${steel(id)}" stroke="#b2d6dc" stroke-width="1.4"/>
 ${[61,82,103,124].map(x=>`<rect x="${x}" y="70" width="10" height="31" rx="2" fill="#426c80" stroke="#a4ccd4"/><path d="M${x+2} 75h6m-6 21h6" stroke="#ffd38a" stroke-width="2"/>`).join('')}
 <path class="scada-industrial-motion scada-industrial-belt" d="M48 85H144" stroke="#8be3d4" stroke-width="2" stroke-dasharray="3 8"/>
 ${hopper(id,45,22,48,38)}<path d="M60 60h18v13H60Z" fill="#476e83" stroke="#9fc7d2"/>
 <path d="M145 77l13 4v10l-13 4Z" fill="#7ba3b0" stroke="#c6dee0"/>
 <g class="scada-industrial-motion scada-industrial-extrusion scada-industrial-material"><path d="M158 82h10q5 0 4 6m-14-2h11q4 0 3 6m-14-2h10q5 0 4 6" fill="none" stroke="#83dcbd" stroke-width="2.5"/></g>${panel(99,38,31)}`;}

function tabletPress(id){return `${shadow()}
 ${legs([44,136],113,12)}<path d="M35 96H145V116H35Z" fill="${steel(id)}" stroke="#a8cdd5" stroke-width="1.5"/>
 <path d="M38 35H142V97H38Z" fill="#173c4a66" stroke="#91bac7" stroke-width="1.5"/>
 <path d="M42 36V96M138 36V96" stroke="#759eae" stroke-width="5"/>
 <path d="M36 26H144V38H36Z" fill="${steel(id)}" stroke="#b3d2db" stroke-width="1.5"/>
 ${hopper(id,47,5,40,27)}<path d="M60 32v19h17" fill="none" stroke="#96c8ce" stroke-width="6" stroke-linejoin="round"/>
 <ellipse cx="90" cy="82" rx="36" ry="12" fill="#244b61" stroke="#92bfcb" stroke-width="1.5"/>
 <path d="M54 76v6M126 76v6" stroke="#9ac5ce" stroke-width="1.5"/>
 <g transform="translate(90 76) scale(1 .31)"><g class="scada-industrial-motion scada-tablet-turret"><circle r="36" fill="#437985" stroke="#c1dedc" stroke-width="1.5"/>${[0,1,2,3,4,5,6,7,8,9].map(i=>{const a=i*Math.PI/5;return `<circle cx="${27*Math.cos(a)}" cy="${27*Math.sin(a)}" r="3.7" fill="#102d3d" stroke="#96c6cb" stroke-width="1.2"/>`;}).join('')}<circle r="11" fill="#719eab" stroke="#c5e1e1"/></g></g>
 <path d="M90 39v28" stroke="#8fb8c6" stroke-width="7"/><path d="M90 40v25" stroke="#d4e5e5" stroke-width="1.4"/>
 <g class="scada-industrial-motion scada-tablet-punches"><path d="M112 43v24" stroke="#a4c9d2" stroke-width="5"/><path d="M106 43h12v7h-12Z" fill="#476f85" stroke="#c0dbdf"/><path d="M108 67h8v5h-8Z" fill="#bad7d9" stroke="#5a8396"/></g>
 <path d="M111 84v9h12" fill="none" stroke="#b2d2d7" stroke-width="4"/><circle cx="112" cy="42" r="6" fill="#284f65" stroke="#9ac5d0"/><path d="M109 42h6" stroke="#6bd8ca" stroke-width="2"/>
 <path class="scada-tablet-outlet" d="M122 77l40 17v10l-40-18Z" fill="#567f91" stroke="#b0d2d7" stroke-width="1.3"/>
 <g class="scada-industrial-motion scada-tablet-discharge scada-industrial-material"><ellipse cx="140" cy="89" rx="4.3" ry="2" fill="#dcead6"/><ellipse cx="151" cy="94" rx="4.3" ry="2" fill="#c1dccb"/></g>
 <path d="M47 42h4v47" fill="none" stroke="#b8ece8" opacity=".27" stroke-width="2"/>${panel(52,101,28)}<path d="M99 106h28m-28 4h28" stroke="#32596f" stroke-width="2"/>`;
}

function fillingLine(id){return `${shadow()}
 ${belt(id)}<path d="M37 97V34H145V97" fill="none" stroke="#396b83" stroke-width="8"/><path d="M37 97V34H145V97" fill="none" stroke="#a1c9d5" stroke-width="1.5"/>
 <rect x="50" y="20" width="75" height="26" rx="4" fill="${steel(id)}" stroke="#accfda"/><path d="M64 20V12h49v8" fill="#295e72" stroke="#89bcca"/>
 <g class="scada-industrial-motion scada-industrial-nozzles"><path d="M63 45v12m25-12v12m25-12v12" stroke="#9ad3d8" stroke-width="4"/><path class="scada-industrial-fill-stream scada-industrial-material" d="M63 57v18m25-18v18m25-18v18" stroke="#60efd0" stroke-width="2" stroke-dasharray="3 3"/></g>
 <g class="scada-industrial-motion scada-industrial-products">${[21,56,81,106,145].map(x=>bottle(x,62)).join('')}</g>
 ${panel(132,43,22)}<path d="M21 52V19h29" fill="none" stroke="#74adbf" stroke-width="6"/>
 <path class="scada-industrial-motion scada-industrial-belt" d="M21 52V19h29" fill="none" stroke="#62ffbc" stroke-width="2" stroke-dasharray="3 7"/>`;
}

function packagingLine(id){return `${shadow()}
 ${belt(id)}<path d="M58 96V42H127V96" fill="none" stroke="#426e82" stroke-width="9"/><path d="M58 96V42H127V96" fill="none" stroke="#a8d1d8" stroke-width="1.5"/>
 <rect x="67" y="31" width="52" height="22" rx="3" fill="${steel(id)}" stroke="#a8d1db"/>
 <circle cx="94" cy="25" r="17" fill="#bbbc9a" stroke="#e0e1c4" stroke-width="1.6"/>
 <g class="scada-industrial-motion scada-industrial-rotate" style="transform-origin:94px 25px"><path d="M94 10v30M79 25h30" stroke="#737e73" stroke-width="2"/><circle cx="94" cy="25" r="5" fill="#254556" stroke="#c7ddda"/></g>
 <g class="scada-industrial-motion scada-industrial-press"><rect x="75" y="53" width="35" height="12" rx="2" fill="#4d8394" stroke="#acd9dc"/><path d="M81 65v9m23-9v9" stroke="#cae3df" stroke-width="3"/></g>
 <g class="scada-industrial-motion scada-industrial-products scada-industrial-material">${carton(20,70,23,25)}${carton(78,70,25,25)}${carton(139,70,22,25)}</g>
 ${panel(132,43,28)}<path d="M146 61v34" stroke="#6e98ab" stroke-width="3"/>`;
}

function granulator(id){return `${shadow()}
 ${legs([44,134],104,19)}<path d="M40 100H139V113H40Z" fill="#31586d" stroke="#8ab5c4"/>
 <path d="M54 47Q92 19 137 51L129 88Q93 114 56 86Z" fill="${steel(id)}" stroke="#a8d2d9" stroke-width="1.6"/>
 <ellipse cx="94" cy="62" rx="42" ry="29" fill="#113448" stroke="#a3d2d8" stroke-width="2"/>
 <g class="scada-industrial-motion scada-industrial-rotate" style="transform-origin:94px 62px"><ellipse cx="94" cy="62" rx="34" ry="23" fill="#1b535a"/><path d="M94 40v44M63 62h62M72 46l44 32M72 78l44-32" stroke="#4e9c9e" stroke-width="2"/><g class="scada-industrial-material">${[[76,60],[91,48],[111,58],[93,74],[72,73],[114,73]].map(([x,y])=>`<circle cx="${x}" cy="${y}" r="3" fill="#b1dfbf" stroke="#e3ecd3" stroke-width=".7"/>`).join('')}</g></g>
 ${motor(id,18,67,29)}<path d="M130 83l31 14v15l-34-18" fill="#416f80" stroke="#9bc5cf"/>
 <g class="scada-industrial-motion scada-industrial-fall scada-industrial-material"><circle cx="158" cy="113" r="3" fill="#b3d8b8"/><circle cx="165" cy="119" r="2.3" fill="#7ebba6"/></g>${panel(83,106,25)}`;
}

function formingMachine(id){return `${shadow()}
 ${belt(id)}<path d="M48 92V39H129V92" fill="none" stroke="#4c8297" stroke-width="7"/><path d="M48 92V39H129V92" fill="none" stroke="#b4d5dc" stroke-width="1.4"/>
 ${hopper(id,60,13,60,30)}<rect x="57" y="46" width="64" height="32" rx="4" fill="${steel(id)}" stroke="#a7cdd5"/>
 ${wheel(75,62,12)}${wheel(103,62,12,true)}
 <g class="scada-industrial-motion scada-industrial-press"><path d="M77 77h24v7l-12 9-12-9Z" fill="#5e94a4" stroke="#d0e5dd"/><path d="M81 80h16" stroke="#edcd96" stroke-width="3"/></g>
 <g class="scada-industrial-motion scada-industrial-products scada-industrial-material">${[23,132,151].map(x=>`<path d="M${x} 93q7-17 15 0l-7-4Z" fill="#c6a16d" stroke="#ffe0a1" stroke-width="1.2"/><path d="M${x+7} 89l2-5" stroke="#795e48"/>`).join('')}</g>${panel(129,49,27)}`;
}

function drumMixer(id){return `${shadow()}
 <path d="M44 109l15-23h65l18 23M55 105v15m77-15v15" fill="none" stroke="#6899ac" stroke-width="5"/>
 <path d="M46 55Q53 34 85 35L131 60 118 102 66 93Q38 79 46 55Z" fill="${steel(id)}" stroke="#acd1da" stroke-width="1.6"/>
 <path d="M62 38Q47 64 66 93M92 40Q72 65 95 99" fill="none" stroke="#96c3cc" stroke-width="4"/>
 <g class="scada-industrial-motion scada-industrial-drum"><path d="M58 54l31 11m-29 5 30 10M83 47l29 16" stroke="#2e687d" stroke-width="4" stroke-linecap="round"/></g>
 <ellipse cx="125" cy="79" rx="18" ry="25" transform="rotate(18 125 79)" fill="#173849" stroke="#b2d7dc" stroke-width="2"/><ellipse cx="125" cy="79" rx="12" ry="18" transform="rotate(18 125 79)" fill="#0a2334" stroke="#4d8495"/>
 <path class="scada-industrial-material" d="M115 83q11 9 20-2l-4 11q-10 5-16-2Z" fill="#91a6a0" stroke="#c2d0b9"/>
 ${motor(id,22,83,27)}${wheel(63,118,7)}${wheel(129,118,7)}${wheel(155,73,11)}<path d="M145 76l-10 3" stroke="#abc9ce" stroke-width="3"/>`;
}

function paperMachine(id){return `${shadow()}
 <path d="M20 102H161V116H20Z" fill="#254f68" stroke="#89b4c6"/>${legs([30,149],116,7)}
 <path d="M20 87V47h17m19 55V56h17m20 46V41h17m28 61V51h17" fill="none" stroke="#789fb1" stroke-width="4"/>
 <path d="M17 67Q32 40 48 67T80 67T112 67T148 67H166V87H143Q128 109 111 85T79 85T47 85H17Z" fill="#a6c6ba" stroke="#d4e4d3" stroke-width="1.3"/>
 <path class="scada-industrial-motion scada-industrial-belt" d="M18 70Q32 44 47 70T79 70T111 70T147 70H164" fill="none" stroke="#517f81" stroke-width="2" stroke-dasharray="5 9"/>
 ${wheel(33,68,16)}${wheel(65,85,14,true)}${wheel(97,68,16)}${wheel(129,85,14,true)}
 <path d="M150 47h17v48h-17" fill="${steel(id)}" stroke="#add1d7"/><ellipse cx="158" cy="47" rx="9" ry="5" fill="#e0e8d3" stroke="#b7d4cf"/>${panel(17,22,30)}${motor(id,90,108,31)}`;
}

function weighHopper(id,state){const level=clamp(state.level);return `${shadow(90,126,63)}
 <path d="M36 70v45m108-45v45M29 115H151" stroke="#608fa5" stroke-width="4"/>
 <path d="M37 25H141V68L107 99H71L37 68Z" fill="${steel(id)}" stroke="#add4dc" stroke-width="1.6"/>
 <rect x="48" y="34" width="83" height="30" rx="2" fill="#0e3041" stroke="#70a9b7"/>
 <rect class="scada-industrial-inventory" x="51" y="${61-24*level/100}" width="77" height="${24*level/100}" fill="#92cdb7" opacity=".8"/>
 <path d="M53 44h9m-9 8h9M68 74h42l-13 12H81Z" fill="#285367" stroke="#5d92a1"/>
 <path d="M75 99h28v14H75Z" fill="#254f63" stroke="#aad3da"/><path class="scada-industrial-motion scada-industrial-gate" d="M75 105h28" stroke="#94d3c6" stroke-width="3"/>
 ${[34,136].map(x=>`<rect x="${x}" y="99" width="11" height="11" rx="2" fill="#19394d" stroke="#a2c9d3"/><path d="M${x+3} 103h5m-5 3h5" stroke="#78cfcc"/>`).join('')}
 ${panel(117,76,31)}<path d="M132 94v17" stroke="#83b1bf" stroke-width="2"/>${bolts([[42,29],[136,29],[42,66],[136,66]])}`;}

function screwFeeder(id){return `${shadow()}
 ${legs([58,133],103,20)}<path d="M34 72L145 55 153 83 42 101Z" fill="${steel(id)}" stroke="#a7d0d8" stroke-width="1.5"/>
 <path d="M47 76L139 62 144 80 52 94Z" fill="#113647" stroke="#83c1c6"/>
 <path class="scada-industrial-motion scada-industrial-screw" d="M50 91l2-17 13 15 2-17 13 15 2-17 13 15 2-17 13 15 2-17 13 15 2-17 13 15" fill="none" stroke="#88d2c1" stroke-width="3" stroke-linejoin="round"/>
 ${hopper(id,41,22,48,37)}<path d="M56 59h18v10l-18 3Z" fill="#49758b" stroke="#a2c7d4"/>
 ${motor(id,9,82,29)}<path d="M148 72h13v33h-16V88" fill="#416c82" stroke="#a2c9d2"/>
 <g class="scada-industrial-motion scada-industrial-fall scada-industrial-material"><circle cx="151" cy="111" r="3" fill="#b5ddc0"/><circle cx="157" cy="118" r="2.5" fill="#8fc6ac"/></g>${panel(105,25,31)}`;}

function damageEffects(){return `
 <g class="scada-industrial-wear" fill="none" stroke="#e8c58d" stroke-width="1.6"><path d="M77 76l8-7m-3 11 9-8m-3 11 10-8"/><path d="M111 93l6-5m-2 9 7-6"/></g>
 <g class="scada-industrial-crack" fill="none" stroke="#ff9cbe" stroke-width="2" stroke-linejoin="round"><path d="M84 61l6 11-8 6 13 10-4 12m-3-26 11-3m-6 15 10 3"/></g>
 <g class="scada-industrial-jam"><path d="M111 89l9-6 10 10-7 9-11-4Z" fill="#71364d" stroke="#ffb1c7" stroke-width="1.5"/><path d="M117 90l7 6m0-7-7 8" stroke="#ffd1df" stroke-width="1.7"/></g>
 <g class="scada-industrial-spill"><ellipse cx="113" cy="123" rx="24" ry="3" fill="#b0bd8a" opacity=".7"/><g class="scada-industrial-motion scada-industrial-fall"><path d="M97 100l4 4-2 4-4-3Zm8 10 4-3 4 5-5 3Zm12 4 3 4-4 3-3-3Z" fill="#c0d6a4" stroke="#e6e6bd" stroke-width=".7"/></g></g>
 <g class="scada-industrial-fuel-leak"><ellipse cx="129" cy="122" rx="25" ry="3" fill="#d5a96b" opacity=".65"/><path class="scada-industrial-motion scada-industrial-fall" d="M123 99q-6 9 0 10t0-10M134 109q-5 7 0 8t0-8" fill="#ffe0a3"/></g>
 <g class="scada-industrial-overheat"><ellipse cx="91" cy="69" rx="45" ry="31" fill="#ed8d58" opacity=".11"/><path class="scada-industrial-motion scada-industrial-exhaust" d="M74 42q-7-10 0-22m15 21q8-12 0-26m15 28q-7-8 0-19" fill="none" stroke="#ffd3a1" stroke-width="2.5" opacity=".8"/></g>`;}

const DRAWINGS=Object.freeze({conveyor,crusher,'vibrating-screen':vibratingScreen,'grinding-mill':grindingMill,'rotary-kiln':rotaryKiln,oven,'rack-oven':rackOven,dryer,extruder,'tablet-press':tabletPress,'filling-line':fillingLine,'packaging-line':packagingLine,granulator,'forming-machine':formingMachine,'drum-mixer':drumMixer,'paper-machine':paperMachine,'weigh-hopper':weighHopper,'screw-feeder':screwFeeder});
const DAMAGE=new Set(['none','jammed','worn','overheated','leaking','ruptured','corroded','refractory-damage','fuel-leak','element-fault','door-seal-leak']);

export function renderIndustrialArt(type,{id='scada-industrial',state={}}={}){
 const draw=Object.hasOwn(DRAWINGS,type)?DRAWINGS[type]:null;if(!draw)return '';
 const prefix=String(id).replace(/[^a-zA-Z0-9_-]/g,'-'),load=clamp(state.load),speed=state.speed===undefined?60:clamp(state.speed);
 const damage=DAMAGE.has(state.damage)?state.damage:'none',heat=Number.isFinite(state.temperature)?Math.max(0,Math.min(1,state.temperature/(type==='rack-oven'?100:300))):0;
 return `<g class="scada-industrial-art scada-industrial-${type}" data-industrial-damage="${damage}" data-industrial-stopped="${speed===0}" style="--scada-industrial-cycle:${(4.5-speed*.035).toFixed(2)}s;--scada-industrial-material:${(.18+load*.0082).toFixed(3)};--scada-industrial-heat:${(.12+heat*.88).toFixed(3)}"><g class="scada-industrial-machine">${draw(prefix,state)}</g>${damageEffects()}</g>`;
}
