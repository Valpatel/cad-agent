/** Original, conceptual nuclear equipment artwork.
 * Inner SVG at 180 × 136. No model, neutronics, operating limits or timers.
 * Heat, transport and source activity are independent supplied visual fields.
 * All numeric values are normalized fictional indices, not physical ratings.
 */
const pct=(value,fallback=0)=>typeof value==='number'&&Number.isFinite(value)?Math.max(0,Math.min(100,value)):fallback;
const steel=id=>`url(#${id}-steel)`;
const path=(d,fill,stroke='#98cad6',width=1.4)=>`<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${width}" stroke-linejoin="round"/>`;
const shadow=(x=90,y=126,rx=62)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="5" fill="#020b15" opacity=".7"/>`;
const bolts=points=>points.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="1.5" fill="#c6e5e8"/><path d="M${x-1} ${y}h2" stroke="#31596c" stroke-width=".7"/>`).join('');
const feet=(xs,y=113,h=10)=>xs.map(x=>`<path d="M${x} ${y}v${h}m-6 0h12" fill="none" stroke="#729daf" stroke-width="4" stroke-linecap="round"/>`).join('');
const pipe=(d,circuit='primary',width=8)=>`<path d="${d}" fill="none" stroke="#16384e" stroke-width="${width+3}" stroke-linecap="round" stroke-linejoin="round"/><path d="${d}" fill="none" stroke="#76a8ba" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"/><path d="${d}" class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-${circuit}" fill="none" stroke-width="${Math.max(1.6,width*.3)}" stroke-dasharray="4 7" stroke-linecap="round" stroke-linejoin="round"/>`;
const core=(x=68,y=67,w=45,h=39)=>`<rect class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" x="${x-5}" y="${y-5}" width="${w+10}" height="${h+10}" rx="8" fill="#ffbb72"/><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="#112e3d" stroke="#709da8"/>${Array.from({length:7},(_,i)=>`<path d="M${x+4+i*(w-8)/6} ${y+3}v${h-6}" stroke="${i%2?'#81b5ba':'#b1c7b7'}" stroke-width="2.8"/>`).join('')}<path class="scada-nuclear-motion scada-nuclear-production" d="M${x+4} ${y+8}h${w-8}m-${w-8} 12h${w-8}m-${w-8} 12h${w-8}" stroke="#ffd89b" stroke-width="1.4" stroke-dasharray="3 4"/>`;
const rodBank=(position,{x=73,y=23,w=36,h=53,travel=32,bottom=false}={})=>{
 const shift=(bottom?-1:1)*travel*pct(position)/100;
 return `<g class="scada-nuclear-rods" style="transform:translateY(${shift}px)">${[0,1,2,3].map(i=>`<path d="M${x+i*w/3} ${y}v${h}" stroke="#445b76" stroke-width="3"/><path d="M${x+i*w/3-.7} ${y}v${h}" stroke="#a7afc9" stroke-width=".8"/>`).join('')}<path d="M${x-4} ${y}h${w+8}" stroke="#b4c5da" stroke-width="4"/></g>`;
};
const bubble=(x,y,index=0)=>`<circle class="scada-nuclear-motion scada-nuclear-steam" cx="${x}" cy="${y}" r="${2+index%2}" fill="#c2f9ed" opacity=".7" style="--scada-nuclear-phase:${-index*.4}s"/>`;
const instrument=(x,y,value,{invalid=false,width=29}={})=>`<rect x="${x}" y="${y}" width="${width}" height="20" rx="3" fill="#071c2c" stroke="#6494a9"/><text class="scada-nuclear-readout" x="${x+width/2}" y="${y+13.5}" text-anchor="middle">${invalid?'—':Math.round(pct(value))}</text>`;
const indicator=(x,y)=>`<circle cx="${x}" cy="${y}" r="2.4" class="scada-nuclear-indicator" fill="#58c5be"/>`;
const glass=(d)=>`${path(d,'#0d334552','#86cbd2',1.3)}<path d="${d}" fill="none" stroke="#c0f3ec" stroke-width=".5" opacity=".4"/>`;

function usedFuelPool(id,state){const level=pct(state.level),top=115-56*level/100;return `${shadow(90,128,77)}
 ${path('M22 48L42 31H164V107L145 124H22Z','#233c50','#7fa7bb',1.7)}
 ${path('M29 54L47 39H155L138 54Z','#557b8a','#abc9d2',1.4)}
 ${path('M29 54H145V117H29Z','#0a2537','#74abbc',1.6)}
 ${path('M145 54L156 42V106L145 117Z','#17445a','#7cb5c2')}
 <path d="M36 111h102M36 102h102M36 93h102" stroke="#25546b" stroke-width="1"/>
 <g class="scada-nuclear-pool-racks">${[0,1,2,3,4].map(i=>{const x=46+i*18;return `<rect x="${x}" y="78" width="12" height="34" rx="1" fill="#567c8d" stroke="#b3c8cc"/><path d="M${x+3} 80v29m3-29v29m3-29v29" stroke="#d5d8c2" stroke-width="1.4"/><rect class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" x="${x+1}" y="83" width="10" height="27" fill="#ffc888"/>`;}).join('')}</g>
 <rect class="scada-nuclear-water" x="30" y="${top}" width="114" height="${115-top}" fill="#1ca0b8" opacity=".4"/>
 <path class="scada-nuclear-motion scada-nuclear-surface" d="M32 ${top+1}q9-3 18 0t18 0t18 0t18 0t18 0t18 0" fill="none" stroke="#97f0ed" stroke-width="1.6"/>
 ${pipe('M12 72H28M145 88H168','primary',6)}
 <path d="M35 57v58m-4-5h4m-4-10h4m-4-10h4m-4-10h4m-4-10h4" stroke="#94c3d1" stroke-width="1.2"/>
 <path d="M34 31V18H151V31M48 18v13" fill="none" stroke="#8bafc0" stroke-width="3"/><rect x="54" y="13" width="26" height="10" rx="2" fill="${steel(id)}" stroke="#b2d4db"/>
 <path d="M67 23v18m-4 0q4 8 8 0" fill="none" stroke="#c8d9d8" stroke-width="2"/>
 ${indicator(135,38)}${bolts([[25,51],[148,51],[25,120],[148,120]])}`;}

function controlRodDrive(id,state){return `${shadow(91,128,47)}
 ${feet([66,118],115,8)}${path('M61 75H122V118H61Z','#102f43','#79a9bc',1.5)}
 <path d="M66 112h51m-51-8h51m-51-8h51m-51-8h51" stroke="#315970"/>
 ${rodBank(state.rodPosition,{x:75,y:37,w:31,h:32,travel:49})}
 ${path('M63 15L70 8H113L120 15V54L113 61H63Z','#2c546e','#96c4d2',1.5)}
 <rect x="63" y="15" width="50" height="46" rx="4" fill="${steel(id)}" stroke="#b6d4dc"/>
 <rect x="74" y="21" width="27" height="32" rx="3" fill="#0b2c3e" stroke="#6ba3b6"/>
 <path class="scada-nuclear-motion scada-nuclear-actuator" d="M79 25h17m-17 6h17m-17 6h17m-17 6h17m-17 6h17" stroke="#87d6d1" stroke-width="2" stroke-dasharray="5 5"/>
 <path d="M54 64v50m-5-2h5m-5-9h5m-5-9h5m-5-9h5m-5-9h5m-5-9h5" stroke="#a0bfcd" stroke-width="1.5"/>
 <path d="M45 ${68+42*pct(state.rodPosition)/100}h7" stroke="#ffd38a" stroke-width="3"/>
 <path d="M120 34h21v50h-9" fill="none" stroke="#3c677e" stroke-width="3"/>
 ${instrument(131,82,state.rodPosition,{width:34})}${indicator(106,55)}
 <path class="scada-nuclear-motion scada-nuclear-monitor-scan" d="M67 68h43" stroke="#63d5d1" stroke-width="1.3" stroke-dasharray="5 4"/>`;
}

function neutronMonitor(id,state,valid){const value=pct(state.value);return `${shadow(90,126,62)}
 ${path('M22 36L31 28H106L114 36V111L106 119H22Z','#274d64','#87b7ca',1.4)}
 <rect x="22" y="36" width="84" height="83" rx="4" fill="${steel(id)}" stroke="#b1d3dd" stroke-width="1.5"/>
 <rect x="31" y="46" width="65" height="42" rx="3" fill="#071d30" stroke="#5c94ad"/>
 <path d="M37 79h52m-52-26v26" stroke="#315d78"/>
 <g class="scada-nuclear-monitor-bars" fill="${state.damage==='drift'?'#ffd38a':'#80e6d2'}">${[0,1,2,3,4,5].map((index)=>`<rect x="${41+index*8}" y="${77-(valid?(6+(index%3)*5)*value/100:0)}" width="4" height="${valid?(6+(index%3)*5)*value/100:0}" rx="1"/>`).join('')}</g>
 ${instrument(34,94,value,{invalid:!valid,width:43})}${indicator(88,103)}
 <path d="M116 106h8V48" fill="none" stroke="#416b85" stroke-width="3"/>
 ${path('M131 26Q142 19 151 26V101Q142 109 131 101Z',steel(id),'#b6d4dc',1.5)}
 <path d="M136 30V99m11-69v69" stroke="#315e78" stroke-width="2"/>
 <path d="M132 39h18m-18 49h18" stroke="#b2cfdb" stroke-width="3"/>
 <circle cx="142" cy="65" r="12" fill="#0c2b3e" stroke="#76b8c8"/>
 <g class="scada-nuclear-motion scada-nuclear-monitor-scan" fill="#9bf5df"><circle cx="137" cy="61" r="2"/><circle cx="145" cy="62" r="2"/><circle cx="141" cy="69" r="2"/></g>
 <path d="M131 49h-7M142 26V15" stroke="#92becb" stroke-width="3"/>${bolts([[26,40],[102,40],[26,115],[102,115]])}`;}

function radiationMonitor(id,state,valid){const value=pct(state.value),angle=-65+130*value/100;return `${shadow(90,125,64)}
 ${path('M29 32L39 23H121L132 33V111L122 121H29Z','#2d526a','#8fbdcb',1.6)}
 <rect x="29" y="32" width="93" height="89" rx="7" fill="${steel(id)}" stroke="#b4d4dc" stroke-width="1.5"/>
 <circle cx="76" cy="66" r="27" fill="#102a3b" stroke="#9fc3cc" stroke-width="2"/>
 <path d="M55 72a22 22 0 0 1 42 0" fill="none" stroke="#5e8b9f" stroke-width="4"/>
 <g class="scada-nuclear-radiation-mark" transform="translate(76 61)" fill="#d6c884"><circle r="3"/><path d="M-3-5L-8-13A15 15 0 0 1 8-13L3-5ZM6 0H15A15 15 0 0 1 7 13L3 5ZM-6 0H-15A15 15 0 0 0-7 13L-3 5Z"/></g>
 <path d="M76 76v-17" stroke="${valid?'#a1f4dc':'#647f91'}" stroke-width="2.4" stroke-linecap="round" transform="rotate(${valid?angle:-75} 76 76)"/><circle cx="76" cy="76" r="3" fill="#cde7e1"/>
 ${instrument(45,98,value,{invalid:!valid,width:47})}${indicator(106,106)}
 <path d="M122 99h17V58" fill="none" stroke="#446e84" stroke-width="3"/>
 <rect x="132" y="35" width="26" height="40" rx="12" fill="#25465f" stroke="#9cc4d1" stroke-width="1.5"/>
 <path d="M137 45h16m-16 6h16m-16 6h16m-16 6h16" stroke="#6d9eb3" stroke-width="2"/>
 <g class="scada-nuclear-motion scada-nuclear-monitor-scan" fill="none" stroke="#91dfd5" stroke-width="1.4"><path d="M161 42q7 10 0 21M166 37q11 15 0 31"/></g>
 <path d="M52 23V13h48v10" fill="none" stroke="#8cb5c5" stroke-width="5"/>${bolts([[34,38],[116,38],[34,115],[116,115]])}`;}

function pwrVessel(id,state){const level=pct(state.level),waterTop=110-61*level/100;return `${shadow()}
 ${feet([63,120],113,10)}${pipe('M11 79H51','primary')}${pipe('M130 58H168','primary')}
 ${path('M50 46Q50 29 91 29T132 46V96Q132 120 91 122T50 96Z',steel(id),'#b2d5de',1.8)}
 ${path('M59 48Q59 39 91 39T123 48V96Q123 113 91 114T59 96Z','#09273a','#426e86',1.8)}
 <rect class="scada-nuclear-water" x="61" y="${waterTop}" width="60" height="${110-waterTop}" fill="#228eaa" opacity=".28"/>
 ${core(72,73,39,33)}
 <path d="M62 57V97Q62 109 73 109H108Q120 109 120 97V57" fill="none" stroke="#315f79" stroke-width="6"/>
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M51 79H64V96Q64 106 76 106H90V75Q90 57 109 57H132" fill="none" stroke-width="2.5" stroke-dasharray="4 7"/>
 ${rodBank(state.rodPosition,{x:77,y:22,w:28,h:45,travel:38})}
 <path d="M51 44H131" stroke="#bcd6dd" stroke-width="7"/><path d="M51 44H131" stroke="#4d7f94" stroke-width="2"/>
 ${[72,84,96,108].map(x=>`<path d="M${x} 31V15" stroke="#4a7a94" stroke-width="6"/><path d="M${x} 15v16" stroke="#b6d6dd" stroke-width="1.4"/>`).join('')}
 <path d="M66 15h49" stroke="#d0e5e5" stroke-width="3"/>
 <path d="M57 51V91Q57 107 68 112" fill="none" stroke="#e1faf4" stroke-width="1" opacity=".5"/>
 ${bolts([[54,44],[65,44],[117,44],[129,44]])}${indicator(145,43)}${instrument(136,90,state.heat,{width:29})}`;}

function bwrVessel(id,state){const level=pct(state.level),waterTop=110-58*level/100;return `${shadow(90,129,65)}
 ${pipe('M12 70H52','primary',7)}${pipe('M128 33H167','secondary',8)}
 ${path('M51 35Q51 13 91 13T131 35V96Q131 115 91 116T51 96Z',steel(id),'#b6d7df',1.8)}
 ${path('M60 35Q60 22 91 22T122 35V98Q122 108 91 109T60 98Z','#0b293b','#568298',1.4)}
 <rect class="scada-nuclear-water" x="62" y="${waterTop}" width="58" height="${110-waterTop}" fill="#2496ad" opacity=".3"/>
 <path d="M67 36h48m-48 6h48" stroke="#8ca9b7" stroke-width="3"/>
 ${[72,85,98,111].map(x=>path(`M${x-4} 47h8l-2 13h-4Z`,'#4e7b8d','#a9d5dc',1)).join('')}
 ${[bubble(74,65,0),bubble(89,57,1),bubble(107,65,2),bubble(95,34,3)].join('')}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-secondary" d="M91 58V30H128" fill="none" stroke-width="2.4" stroke-dasharray="4 7"/>
 ${core(72,77,39,29)}${rodBank(state.rodPosition,{x:78,y:105,w:27,h:29,travel:28,bottom:true})}
 <path d="M57 115H124M73 123h37" stroke="#a7c8d2" stroke-width="4"/>
 ${pipe('M53 87H32V111H53','primary',6)}${pipe('M131 87H151V111H129','primary',6)}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M55 87H65V99H69M114 99H119V72H61" fill="none" stroke-width="2.2" stroke-dasharray="4 7"/>
 ${bolts([[53,53],[129,53],[53,97],[129,97]])}${indicator(145,19)}`;}

function phwrCalandria(id,state){return `${shadow(90,127,75)}
 ${feet([50,128],111,11)}
 ${path('M56 36H124Q151 37 153 73T124 111H56Z',steel(id),'#b4d2dc',1.7)}
 <path d="M78 39v70m45-69v69" stroke="#709eb3" stroke-width="5"/>
 <ellipse cx="56" cy="74" rx="31" ry="37" fill="#153b50" stroke="#a9d6dc" stroke-width="2"/>
 <defs><clipPath id="${id}-moderator-fill"><ellipse cx="56" cy="74" rx="26" ry="32"/></clipPath></defs><rect class="scada-nuclear-water" x="29" y="${106-64*pct(state.level)/100}" width="54" height="${64*pct(state.level)/100}" fill="#2795ac" opacity=".35" clip-path="url(#${id}-moderator-fill)"/>
 ${[0,1,2].flatMap(row=>[0,1,2,3].map(col=>{const x=41+col*10,y=59+row*15;return `<circle cx="${x}" cy="${y}" r="4.2" fill="#1d2d3e" stroke="#a5c7c9" stroke-width="1.1"/><circle class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" cx="${x}" cy="${y}" r="2.7" fill="#ffd497"/>`;})).join('')}
 <path d="M87 52h51v43H87Z" fill="#0a2b3d" stroke="#5d99aa"/>
 ${[58,70,82,93].map(y=>`<path d="M89 ${y}h47" stroke="#c0c9b3" stroke-width="3"/><path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M89 ${y}h47" stroke-width="1.5" stroke-dasharray="3 5"/>`).join('')}
 <path class="scada-nuclear-motion scada-nuclear-production" d="M98 57v36m16-36v36m16-36v36" stroke="#ffd29a" stroke-width="1.2" stroke-dasharray="2 5"/>
 ${pipe('M12 51H25V101H33','primary',6)}${pipe('M152 51H167V101H150','primary',6)}
 <path d="M92 110v13H73M115 36V18h18" fill="none" stroke="#456e94" stroke-width="7"/><path d="M92 110v13H73M115 36V18h18" fill="none" stroke="#9dbddd" stroke-width="2"/>
 <path class="scada-nuclear-rods" d="M92 23v${17+58*pct(state.rodPosition)/100}m12-${17+58*pct(state.rodPosition)/100}v${17+58*pct(state.rodPosition)/100}" stroke="#8fabc7" stroke-width="3"/>
 <path d="M86 23h24" stroke="#c0d2df" stroke-width="4"/>
 ${instrument(130,16,state.heat,{width:30})}${indicator(143,114)}`;}

function gasCooledReactor(id,state){return `${shadow()}
 ${feet([61,122],111,12)}${pipe('M11 92H48','primary',10)}${pipe('M135 75H169','primary',10)}
 ${path('M45 44Q45 21 91 21T137 44V95Q137 119 91 120T45 95Z','#365b70','#9fc8d6',1.8)}
 ${path('M53 44Q53 30 91 30T129 44V96Q129 111 91 112T53 96Z',steel(id),'#bdd4dc',1.1)}
 ${path('M63 48Q63 40 91 40T119 48V99H63Z','#0b293b','#739bb0',1.5)}
 <rect class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" x="66" y="51" width="51" height="47" rx="8" fill="#ffbd76"/>
 ${[0,1,2,3].flatMap(row=>[0,1,2].map(col=>{const x=76+col*14,y=58+row*11;return path(`M${x-6} ${y-3}l6-4 6 4v7l-6 4-6-4Z`,'#38575c','#94b4ab',1);})).join('')}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M48 92H58V49H65M117 49H124V75H137M75 95V53M104 95V53" fill="none" stroke-width="2.2" stroke-dasharray="4 8"/>
 <path class="scada-nuclear-motion scada-nuclear-production" d="M72 62h38m-38 13h38m-38 13h38" stroke="#ffd29a" stroke-width="1.1" stroke-dasharray="2 5"/>
 ${rodBank(state.rodPosition,{x:79,y:15,w:24,h:38,travel:45})}
 <path d="M57 44H125" stroke="#c2d6db" stroke-width="5"/><path d="M72 26V13h39v13" fill="#294b63" stroke="#9bbfce" stroke-width="2"/>
 ${instrument(139,34,state.heat,{width:29})}${indicator(35,49)}${bolts([[49,49],[133,49],[49,92],[133,92]])}`;}

function sodiumVessel(id,state){const level=pct(state.level),waterTop=113-50*level/100;return `${shadow(90,127,72)}
 ${feet([46,135],114,10)}${path('M30 54Q30 43 91 43T153 54V102Q153 121 91 122T30 102Z',steel(id),'#a9cfd9',1.7)}
 ${path('M39 58Q39 53 91 53T144 58V103Q144 113 91 114T39 103Z','#142e3c','#678f9f',1.2)}
 <rect class="scada-nuclear-water" x="41" y="${waterTop}" width="101" height="${114-waterTop}" fill="#9eb4a2" opacity=".28"/>
 <path class="scada-nuclear-motion scada-nuclear-surface" d="M43 ${waterTop+1}q12-3 24 0t24 0t24 0t24 0" fill="none" stroke="#c7d4b5" stroke-width="1.5"/>
 ${core(72,78,37,28)}
 ${rodBank(state.rodPosition,{x:79,y:23,w:23,h:42,travel:41})}
 <path d="M52 25v72m-8-38h16m-16 10h16m-16 10h16m-16 10h16" stroke="#a1bdc5" stroke-width="3"/>
 <rect x="43" y="19" width="19" height="24" rx="3" fill="${steel(id)}" stroke="#b6d0d9"/><path d="M47 23h11m-11 5h11m-11 5h11" stroke="#355b73" stroke-width="2"/>
 ${pipe('M13 65H39','primary',8)}${pipe('M144 65H169','primary',8)}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M40 65H53V104H91V82M110 83H130V65H145" fill="none" stroke-width="2.4" stroke-dasharray="4 7"/>
 <path d="M31 54H152" stroke="#b5d0d7" stroke-width="7"/><path d="M31 54H152" stroke="#527b8d" stroke-width="2"/>
 <rect x="76" y="15" width="29" height="16" rx="3" fill="#29495e" stroke="#a6c6d2"/>${indicator(135,43)}${instrument(118,19,state.heat,{width:32})}`;}

function moltenSaltReactor(id,state){const level=pct(state.level),top=107-52*level/100;return `${shadow()}
 ${feet([57,124],114,9)}
 ${path('M51 36L67 22H115L131 36V101L117 117H65L51 101Z',steel(id),'#b5d0db',1.8)}
 ${path('M61 43L72 34H110L121 43V98L111 107H71L61 98Z','#142a40','#7eafbd',1.3)}
 <rect class="scada-nuclear-water" x="63" y="${top}" width="56" height="${107-top}" fill="#7589b1" opacity=".38"/>
 <rect class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" x="69" y="59" width="45" height="43" rx="7" fill="#ffbc7c"/>
 ${[0,1,2].flatMap(row=>[0,1,2].map(col=>{const x=78+col*13,y=67+row*12;return path(`M${x-5} ${y-3}l5-3 5 3v6l-5 3-5-3Z`,'#3e5668','#b7c8ce',1);})).join('')}
 <path class="scada-nuclear-motion scada-nuclear-production" d="M70 65h42m-42 13h42m-42 13h42" stroke="#ffd5a6" stroke-width="1.1" stroke-dasharray="3 5"/>
 ${pipe('M11 92H51','primary',8)}${pipe('M131 52H169','primary',8)}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M52 92H65V102H118V52H132M65 91V55" fill="none" stroke-width="2.4" stroke-dasharray="4 7"/>
 ${rodBank(state.rodPosition,{x:79,y:13,w:25,h:36,travel:48})}
 <path d="M66 35H116" stroke="#b6cbd8" stroke-width="5"/><rect x="73" y="10" width="36" height="14" rx="3" fill="#344e68" stroke="#afcad7"/>
 ${instrument(136,91,state.heat,{width:30})}${indicator(37,36)}${bolts([[55,45],[127,45],[55,99],[127,99]])}`;}

function nuclearSteamGenerator(id,state){const level=pct(state.level),waterTop=110-67*level/100;return `${shadow()}
 ${feet([62,117],115,9)}
 ${path('M50 34Q50 15 89 15T129 34V103Q129 120 89 121T50 103Z',steel(id),'#b7d6de',1.8)}
 ${path('M59 36Q59 26 89 26T120 36V105Q120 112 89 112T59 105Z','#0b2c3f','#729daf',1.3)}
 <rect class="scada-nuclear-water" x="61" y="${waterTop}" width="57" height="${111-waterTop}" fill="#2a9da7" opacity=".28"/>
 <path d="M60 96H119" stroke="#a7bbc2" stroke-width="5"/>
 ${[0,1,2,3].map(i=>`<path d="M${67+i*4} 96V${63-i*6}Q89 ${37-i*2} ${111-i*4} ${63-i*6}V96" fill="none" stroke="#648e9f" stroke-width="3.2"/><path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M${67+i*4} 96V${63-i*6}Q89 ${37-i*2} ${111-i*4} ${63-i*6}V96" fill="none" stroke-width="1.4" stroke-dasharray="3 6"/>`).join('')}
 <path d="M59 96v14h30V98m0 12h31" fill="none" stroke="#44687f" stroke-width="4"/>
 ${pipe('M12 100H65','primary',7)}${pipe('M12 114H105V100','primary',7)}
 ${pipe('M120 82H168','secondary',7)}${pipe('M119 32H168','secondary',8)}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-secondary" d="M119 82H114V47H119V32" fill="none" stroke-width="2" stroke-dasharray="4 7"/>
 ${[bubble(67,48,0),bubble(91,37,1),bubble(108,44,2)].join('')}
 <path class="scada-nuclear-motion scada-nuclear-residual" d="M78 81q-4-8 0-15m12 16q4-8 0-16m11 17q-4-7 0-14" fill="none" stroke="#ffc783" stroke-width="1.6"/>
 ${indicator(141,62)}${bolts([[53,50],[126,50],[53,92],[126,92]])}`;}

/** Dished vertical vessel with clipped inventory, immersed heater bank,
 * top spray nozzle, relief path and bottom surge connection. Indices are visual. */
function pressurizer(id,state){
 const level=pct(state.level),top=114-84*level/100,heaterOk=state.damage!=='heater-fault';
 const inner='M59 36C59 28 69 24 83 24S107 28 107 36V102C107 109 97 114 83 114S59 109 59 102Z';
 return `${shadow(90,128,63)}${feet([62,104],115,10)}
 <defs><clipPath id="${id}-pressurizer-water"><path d="${inner}"/></clipPath></defs>
 <g class="scada-pressurizer-spray-line"><path d="M9 29H36V10H77V24" fill="none" stroke="#24485c" stroke-width="8" stroke-linejoin="round"/><path d="M9 29H36V10H77V24" fill="none" stroke="#8bb7c6" stroke-width="4.5" stroke-linejoin="round"/></g>
 <g class="scada-pressurizer-relief-line"><path d="M97 22V10H145V29H169" fill="none" stroke="#24485c" stroke-width="8" stroke-linejoin="round"/><path d="M97 22V10H145V29H169" fill="none" stroke="#a1c3ce" stroke-width="4.5" stroke-linejoin="round"/><path d="M141 20h8m-4-5v10" stroke="#b6d2db" stroke-width="1.5"/></g>
 <path class="scada-pressurizer-shell" d="M50 35C50 24 64 15 83 15S116 24 116 35V103C116 114 102 121 83 121S50 114 50 103Z" fill="${steel(id)}" stroke="#b5d7e0" stroke-width="1.7"/>
 ${path(inner,'#092c3e','#75a5b7',1.3)}
 <g clip-path="url(#${id}-pressurizer-water)">
   <rect class="scada-nuclear-water" x="58" y="${top}" width="50" height="${114-top}" fill="#239db0" opacity=".44"/>
   ${level>0?`<path class="scada-nuclear-motion scada-nuclear-surface scada-pressurizer-surface" d="M57 ${top+1}q9-2 18 0t18 0t18 0" fill="none" stroke="#a7f4e7" stroke-width="1.4"/>`:''}
   <path class="scada-nuclear-motion scada-nuclear-residual" d="M71 82q-4-7 0-14m12 14q4-7 0-15m12 15q-4-7 0-14" fill="none" stroke="#e0e9d7" stroke-width="1.3"/>
   <g class="scada-pressurizer-heaters" data-heater-available="${heaterOk}" fill="none" stroke-linecap="round"><path d="M68 110V94a4 4 0 0 1 8 0v16m3 0V94a4 4 0 0 1 8 0v16m3 0V94a4 4 0 0 1 8 0v16" stroke="#937e64" stroke-width="3"/>
     ${heaterOk?'<path class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" d="M68 110V94a4 4 0 0 1 8 0v16m3 0V94a4 4 0 0 1 8 0v16m3 0V94a4 4 0 0 1 8 0v16" stroke="#ffd18d" stroke-width="1.8"/>':''}</g>
 </g>
 <path class="scada-pressurizer-nozzle" d="M77 24v10m-5 1h10m-5 0-6 8m6-8v9m0-9 6 8" fill="none" stroke="#9bbfca" stroke-width="1.5"/>
 <path d="M54 42v58M112 42v58" stroke="#d0e5e7" stroke-width=".8" opacity=".45"/>
 <path d="M69 117h28" stroke="#789cae" stroke-width="4"/>
 <g class="scada-pressurizer-surge">${pipe('M83 121V129H134','primary',6)}</g>
 <path d="M116 62H127" stroke="#98bfcb" stroke-width="3"/>
 <circle cx="144" cy="62" r="16" fill="#0f2c40" stroke="#98c1ce" stroke-width="1.5"/>
 <path d="M133 67a12 12 0 0 1 22 0M133 67l2-2m9-13v3m11 12-2-2" fill="none" stroke="#608ca4" stroke-width="1.4"/>
 <path class="scada-pressurizer-pressure-needle" d="M144 65V51" stroke="#c0f1dc" stroke-width="2" transform="rotate(${-65+130*pct(state.pressure)/100} 144 65)"/><circle cx="144" cy="65" r="2.2" fill="#a4dace"/>
 ${instrument(127,84,state.pressure,{width:34})}${indicator(157,98)}`;
}

function containment(id,state){const integrity=pct(state.integrity,100);return `${shadow(90,127,77)}
 ${path('M22 118V68Q22 12 90 12T158 68V118Z','#39566a','#9dbecb',1.9)}
 ${path('M31 117V69Q31 22 90 22T149 69V117Z','#0e2b3f','#638da6',1.3)}
 <path d="M24 70H156M49 31v86m82-86v86" stroke="#466b83" stroke-width="2"/>
 <path d="M32 117V70Q32 27 90 27T148 70" fill="none" stroke="#b9dde0" stroke-width="1.1" opacity=".45"/>
 <path d="M35 114H145" stroke="#9ebbc6" stroke-width="5"/>
 ${path('M53 73Q53 59 73 59T93 73V107H53Z','#315d74','#88bdcc',1.4)}
 <rect class="scada-nuclear-heat scada-nuclear-motion scada-nuclear-residual" x="61" y="79" width="24" height="26" rx="5" fill="#ffba72"/>
 <path d="M63 106V82h20v24m-13-26V68m7 12V68" fill="none" stroke="#abc5ca" stroke-width="2"/>
 ${path('M108 75Q108 63 120 63T132 75V107H108Z','#284e66','#80afc1',1.2)}
 <path d="M96 87h12m-15 13h15" stroke="#74a8b8" stroke-width="4"/>
 ${pipe('M11 71H31','primary',6)}${pipe('M149 71H170','primary',6)}
 <path class="scada-nuclear-motion scada-nuclear-flow scada-nuclear-primary" d="M32 71V50H145V71" fill="none" stroke-width="1.8" stroke-dasharray="4 8"/>
 <path d="M36 119v11H16" fill="none" stroke="#7eabbc" stroke-width="5"/>
 <path class="scada-nuclear-integrity-crack" d="M132 29l-7 12 9 10-5 13m4-15 11 2M34 82l9 8-6 11" fill="none" stroke="#efb6bf" stroke-width="2" opacity="${(100-integrity)/100}"/>
 ${instrument(109,88,state.pressure,{width:28})}${indicator(90,39)}`;}

const DRAWINGS=Object.freeze({
 'pwr-reactor-vessel':pwrVessel,'bwr-reactor-vessel':bwrVessel,'phwr-calandria':phwrCalandria,
 'gas-cooled-reactor':gasCooledReactor,'sodium-reactor-vessel':sodiumVessel,'molten-salt-reactor':moltenSaltReactor,
 'nuclear-steam-generator':nuclearSteamGenerator,pressurizer,'containment-structure':containment,
 'used-fuel-pool':usedFuelPool,'control-rod-drive':controlRodDrive,'neutron-monitor':neutronMonitor,'radiation-monitor':radiationMonitor
});
const VESSELS=['pwr-reactor-vessel','bwr-reactor-vessel','phwr-calandria','sodium-reactor-vessel','molten-salt-reactor'];
const DAMAGE=Object.freeze({
 ...Object.fromEntries(VESSELS.map(type=>[type,['none','leaking','cooling-loss','overheated']])),
 'gas-cooled-reactor':['none','leaking','circulator-fault','overheated'],
 'nuclear-steam-generator':['none','tube-leak','fouled','corroded'],
 pressurizer:['none','leaking','heater-fault','relief-stuck'],
 'containment-structure':['none','leaking','cracked','ventilation-fault'],
 'used-fuel-pool':['none','leaking','fouled','cooling-loss'],
 'control-rod-drive':['none','jammed','worn','power-loss'],
 'neutron-monitor':['none','drift','broken','disconnected'],
 'radiation-monitor':['none','drift','broken','disconnected']
});

function damageArt(type,damage){
 if(damage==='none')return '';
 const x=type==='used-fuel-pool'?143:type==='containment-structure'?151:type==='pressurizer'?115:125;
 const leak=`<g class="scada-nuclear-leak-mark"><path d="M${x-3} 90l5 5-4 6 6 5" fill="none" stroke="#f5b4c5" stroke-width="1.7"/><ellipse cx="${x+12}" cy="125" rx="18" ry="2.8" fill="#77d3d1" opacity=".45"/><path class="scada-nuclear-motion scada-nuclear-drip" d="M${x+4} 104q-4 7 0 9t0-9m8 7q-4 6 0 8t0-8" fill="#b7eee1"/></g>`;
 if(damage==='leaking')return ['gas-cooled-reactor','containment-structure'].includes(type)?`<g class="scada-nuclear-gas-leak-mark"><path d="M${x-3} 84l5 5-4 7" fill="none" stroke="#f5b4c5" stroke-width="1.7"/><path class="scada-nuclear-motion scada-nuclear-drip scada-nuclear-gas-leak" d="M${x+2} 91q9-6 17-1m-16 5q9-1 16 5m-15-3q4 9 12 11" fill="none" stroke="#b7dce4" stroke-width="1.8"/></g>`:leak;
 if(damage==='tube-leak')return `<g class="scada-nuclear-tube-leak"><path d="M95 77l6-5 6 7m-7-12 5 4" fill="none" stroke="#ffb0c3" stroke-width="2"/><path d="M99 76l9 8m-8-6 12 2" stroke="#ffd38a" stroke-width="1.6"/><circle cx="101" cy="76" r="10" fill="none" stroke="#e7b1bb" stroke-width="1.1" stroke-dasharray="2 3"/><g class="scada-nuclear-motion scada-nuclear-drip" fill="#b3eee0"><circle cx="109" cy="84" r="1.7"/><circle cx="113" cy="89" r="1.3"/></g></g>`;
 if(['cooling-loss','circulator-fault','ventilation-fault'].includes(damage))return `<g class="scada-nuclear-cooling-loss"><path d="M14 61h18v19H14Z" fill="#19394c" stroke="#ffd38a" stroke-width="1.4"/><path d="M18 65l10 11m0-11-10 11" stroke="#ffd8a1" stroke-width="2"/><path d="M39 51q-6-9 0-17m8 16q6-8 0-16" class="scada-nuclear-motion scada-nuclear-residual" fill="none" stroke="#ffd0a1" stroke-width="1.7"/></g>`;
 if(damage==='overheated')return `<g class="scada-nuclear-overheat-mark"><g transform="translate(-125 -47)"><path d="M143 91V66q0-5 5-5t5 5v25a9 9 0 1 1-10 0Z" fill="#472f32" stroke="#f3b7a2" stroke-width="1.4"/><path d="M148 69v27" stroke="#ffb877" stroke-width="3"/><circle cx="148" cy="99" r="5" fill="#ffb877"/></g><path d="M39 40q-5-8 0-18m8 16q5-8 0-17" class="scada-nuclear-motion scada-nuclear-residual" fill="none" stroke="#ffd4a8" stroke-width="1.8"/></g>`;
 if(damage==='fouled')return `<g class="scada-nuclear-fouling" fill="#8a9d79" stroke="#bbc6a0" stroke-width=".7" opacity=".85">${[[68,83],[80,101],[111,88],[95,60],[107,103],[60,70]].map(([x,y],i)=>`<path d="M${x} ${y}l${4+i%3}-3 5 4-3 5-5-1Z"/>`).join('')}</g>`;
 if(damage==='corroded'||damage==='worn')return `<g class="scada-nuclear-wear" fill="none" stroke="#d0b18d" stroke-width="1.6"><path d="M53 82l8-7m-5 13 9-8m48 14 7-5m-9-3 7-6M99 40l8-6"/></g>`;
 if(damage==='heater-fault')return `<g class="scada-nuclear-heater-fault"><path d="M81 96l8 8m0-8-8 8" stroke="#ffafc7" stroke-width="2"/><path d="M77 100h4m9 0h6" stroke="#102b3b" stroke-width="4"/><path d="M134 112l5-8 5 8Z" fill="#422c39" stroke="#ffc3d1"/></g>`;
 if(damage==='relief-stuck')return `<g class="scada-nuclear-relief-stuck"><path d="M139 18h15v21h-15Z" fill="#573c42" stroke="#ffd29e"/><path d="M142 23l9 10m0-10-9 10" stroke="#ffd29e" stroke-width="1.8"/></g>`;
 if(damage==='cracked')return `<path class="scada-nuclear-structure-crack" d="M129 28l-8 12 10 10-7 14 8 13m-5-25 14 2m-14 10-11 4" fill="none" stroke="#ffc1ca" stroke-width="2.4" stroke-linejoin="round"/>`;
 if(damage==='jammed')return `<g class="scada-nuclear-drive-jam"><path d="M100 64l10-6 10 9-6 12-11-4Z" fill="#623649" stroke="#ffc3d0" stroke-width="1.3"/><path d="M106 64l7 9m1-9-8 9" stroke="#ffd6df" stroke-width="1.7"/></g>`;
 if(damage==='power-loss')return `<g class="scada-nuclear-power-loss"><path d="M132 59h18v14h-18Z" fill="#172e3e" stroke="#92a3b1"/><path d="M137 58v-5m8 5v-5m-9 13 11 0" stroke="#acbbc7" stroke-width="2"/><path d="M135 62l12 9" stroke="#ffd38a" stroke-width="2"/></g>`;
 if(damage==='drift')return `<g class="scada-nuclear-drift" fill="none" stroke="#ffd38a" stroke-width="1.5"><path d="M39 86l10-5 8 7 8-10 8 4 10-9 11 5" stroke-dasharray="3 2"/><path d="M111 16l8 13h-16Z" fill="#3b3640"/><path d="M111 20v4m0 2v1"/></g>`;
 if(damage==='broken')return `<g class="scada-nuclear-monitor-break"><path d="M59 48l7 12-6 8 15 8-4 13m-5-27 12-6m-5 21 12 2" fill="none" stroke="#f9b2c4" stroke-width="1.9"/><path d="M133 82l12 12m0-12-12 12" stroke="#ffb2c8" stroke-width="2.5"/></g>`;
 if(damage==='disconnected')return `<g class="scada-nuclear-disconnection"><path d="M125 93h18v9h-18Z" fill="#0a2132"/><path d="M122 91h9v8h-9Zm17 12h9v8h-9Z" fill="#527289" stroke="#b0c7d1"/><path d="M134 90l4-4m-1 13 5-2" stroke="#ffd4a0" stroke-width="1.7"/></g>`;
 return '';
}

/** Consume normalized visual state only. The wrapper's active flag never masks
 * explicitly supplied coolant flow, residual heat, inventory or a leak. */
export function renderNuclearArt(type,{id='scada-nuclear',state={}}={}){
 const draw=Object.hasOwn(DRAWINGS,type)?DRAWINGS[type]:null;if(!draw)return '';
 const prefix=String(id).replace(/[^A-Za-z0-9_-]/g,'-');
 const damage=DAMAGE[type].includes(state.damage)?state.damage:'none';
 const online=state.status!=='offline',running=state.running!==false,fault=state.fault===true,active=state.active!==false;
 const valid=online&&!fault&&state.connected!==false&&!['broken','disconnected'].includes(damage)&&(!['neutron-monitor','radiation-monitor'].includes(type)||active);
 const source=(VESSELS.includes(type)||type==='gas-cooled-reactor')&&active&&!fault&&online;
 const primary=pct(state.primaryFlow??state.flow),secondary=pct(state.secondaryFlow??(type==='bwr-reactor-vessel'?state.flow:0));
 const heat=pct(state.heat),load=pct(state.load),moving=state.moving===true&&pct(state.speed)>0&&active&&!fault&&online&&!['jammed','power-loss'].includes(damage);
 const leak=['leaking','tube-leak'].includes(damage),monitor=active&&valid&&damage!=='power-loss';
 const attrs={'source':source,'primary':primary>0,'secondary':secondary>0,'heat':heat>0,'moving':moving,'monitor':monitor,'leaking':leak,'valid':valid,'running':running,'online':online,'fault':fault,'warning':state.status==='warning'};
 const style=`--scada-nuclear-primary-duration:${(4.5-primary*.035).toFixed(2)}s;--scada-nuclear-secondary-duration:${(4.5-secondary*.035).toFixed(2)}s;--scada-nuclear-source-duration:${(4.8-load*.028).toFixed(2)}s;--scada-nuclear-drive-duration:${(3.5-pct(state.speed)*.025).toFixed(2)}s;--scada-nuclear-heat-opacity:${(heat*.0075).toFixed(3)};--scada-nuclear-load-opacity:${(load*.01).toFixed(3)};--scada-nuclear-primary-opacity:${(primary*.009).toFixed(3)};--scada-nuclear-secondary-opacity:${(secondary*.009).toFixed(3)}`;
 return `<g class="scada-nuclear-art scada-nuclear-${type}" data-nuclear-damage="${damage}" ${Object.entries(attrs).map(([key,value])=>`data-nuclear-${key}="${value}"`).join(' ')} style="${style}">${draw(prefix,state,valid)}${damageArt(type,damage)}</g>`;
}
