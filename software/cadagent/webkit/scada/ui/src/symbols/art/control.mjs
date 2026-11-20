/** Industrial automation illustrations for the shared SCADA component library.
 * Returns SVG inner markup for a 180 × 136 viewBox. The caller supplies matching
 * id-steel/glass/liquid/glow definitions and owns accessible labels and motion.
 * Indicators are illustrative state presentation, never simulated PLC logic. */
const finiteLoad = value => Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
const led = (x,y,delay=0,r=2.2) => `<circle class="scada-led" cx="${x}" cy="${y}" r="${r}" fill="#456575" style="--scada-phase:${delay}s"/>`;
const screws = points => points.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="1.4" fill="#a9cbd6"/><path d="M${x-1} ${y}h2" stroke="#234456" stroke-width=".7"/>`).join('');
const shade = (cy=121,rx=69) => `<ellipse cx="90" cy="${cy}" rx="${rx}" ry="7" fill="#030c16" opacity=".6"/>`;
const terminal = (x,y,width=16) => `<rect x="${x}" y="${y}" width="${width}" height="13" rx="1.5" fill="#183b37" stroke="#68b3a2" stroke-width=".8"/>${Array.from({length:Math.max(2,Math.floor(width/5))},(_,i)=>`<rect x="${x+3+i*4.5}" y="${y+4}" width="2.5" height="5" rx=".5" fill="#b2d5bc"/>`).join('')}`;
const port = (x,y,width=19,height=15) => `<path d="M${x} ${y}h${width}v${height}h-${width}Z" fill="#071522" stroke="#6a95a8" stroke-width="1"/><path d="M${x+3} ${y+height-3}h${width-6}v-4h-${width-6}Z" fill="#314a59"/>${[0,1,2,3].map(i=>`<path d="M${x+4+i*(width-8)/3} ${y+2}v4" stroke="#cbbd83" stroke-width="1"/>`).join('')}`;

function rack(id,load){return `${shade()}
 <path d="M12 109H169V118H12Z" fill="#376071" stroke="#79adbf"/><path d="M21 113h9m17 0h9m17 0h9m17 0h9m17 0h9m17 0h9" stroke="#0a2433" stroke-width="3"/>
 <path d="M15 28L22 20H164L169 28Z" fill="#598797" stroke="#93c6d2"/><rect x="15" y="28" width="154" height="81" rx="3" fill="#102b3e" stroke="#6ea9bd"/>
 <rect x="21" y="33" width="23" height="71" rx="2" fill="url(#${id}-steel)" stroke="#91c2ce"/>
 <rect x="25" y="39" width="15" height="23" rx="1" fill="#102132"/>${led(32.5,45,-.2)}<path d="M29 52h7m-7 4h7" stroke="#618b9d"/>
 <path d="M34 68l-7 11h6l-3 10 9-13h-6Z" fill="#ffd38a"/>
 <rect x="49" y="28" width="38" height="77" rx="2.5" fill="#244c62" stroke="#a2d6df" stroke-width="1.2"/><path d="M53 32H83" stroke="#7ee9e7" stroke-width="3"/>
 <rect x="54" y="40" width="28" height="26" rx="2" fill="#071b2b" stroke="#477d94"/>
 <path class="scada-scan" d="M57 47h22M57 53h22" stroke="#62ffbc" stroke-width="2" stroke-dasharray="8 4"/>
 <rect x="57" y="59" width="22" height="3" rx="1" fill="#24495b"/><rect class="scada-load-bar" x="57" y="59" width="${22*load/100}" height="3" rx="1" fill="#00e5e9"/>
 ${port(57,73,22,16)}${led(58,96,-.3)}${led(68,96,-.7)}<path d="M77 93v6" stroke="#b0d5df" stroke-width="2"/>
 ${[0,1,2,3].map(i=>{const x=92+i*18;return `<rect x="${x}" y="33" width="15" height="71" rx="1.5" fill="url(#${id}-steel)" stroke="#72abbf"/><path d="M${x+3} 38h9" stroke="${i%2?'#ffd38a':'#62ffbc'}" stroke-width="3"/><rect x="${x+3}" y="45" width="9" height="20" rx="1" fill="#0a2132"/>${led(x+7.5,50,-i*.2,1.7)}${led(x+7.5,58,-i*.25-.3,1.7)}${terminal(x+2,72,11)}${terminal(x+2,89,11)}`}).join('')}
 ${screws([[18,31],[165,31],[18,105],[165,105]])}`;}

function cpu(id,load){return `${shade(123,52)}
 <path d="M47 27L59 16H133L121 27Z" fill="#6096a8" stroke="#a8d7e2"/><path d="M121 27L133 16V108L121 119Z" fill="#193d55" stroke="#70afc4"/>
 <rect x="47" y="27" width="74" height="92" rx="3" fill="url(#${id}-steel)" stroke="#a4d7e1" stroke-width="1.4"/>
 <rect x="54" y="33" width="60" height="25" rx="2" fill="#0c2638" stroke="#4a7f94"/><rect x="59" y="38" width="21" height="15" rx="1.5" fill="#183d50"/>
 <path class="scada-scan" d="M62 42h14m-14 6h14" fill="none" stroke="#62ffbc" stroke-width="2" stroke-dasharray="6 4"/>
 ${led(88,41,-.1)}${led(98,41,-.5)}${led(108,41,-.8)}<path d="M86 49h24" stroke="#3a6379" stroke-width="4"/><path class="scada-load-bar" d="M86 49h${24*load/100}" stroke="#00e5e9" stroke-width="4"/>
 <path d="M55 66h39m-39 5h39m-39 5h39" stroke="#294a5f" stroke-width="2.5"/><rect x="102" y="65" width="10" height="16" rx="2" fill="#122f42" stroke="#78aabd"/><path d="M107 69v8" stroke="#ffd38a" stroke-width="2"/>
 ${port(56,88,25,18)}${terminal(87,89,25)}<path d="M56 113h54" stroke="#21475c" stroke-width="2"/>
 <path d="M127 36v10m0 7v10m0 7v10m0 7v10" stroke="#75b0c3" stroke-width="2"/>
 ${screws([[51,31],[117,31],[51,115],[117,115]])}`;}

function remoteIo(id){return `${shade(120,71)}
 <path d="M17 101H164V116H17Z" fill="#1a433d" stroke="#71ac9d"/>
 <path d="M20 38L29 28H151L160 38Z" fill="#527e90" stroke="#94c8d5"/><rect x="20" y="38" width="140" height="63" rx="4" fill="url(#${id}-steel)" stroke="#9ad0dc" stroke-width="1.3"/>
 <rect x="27" y="45" width="31" height="47" rx="3" fill="#0d293b" stroke="#50869e"/>${led(35,53,-.1)}${led(48,53,-.6)}${port(32,65,21,18)}
 <path d="M63 43V96" stroke="#2b5267" stroke-width="2"/>
 ${[0,1,2,3].map(i=>{const x=69+i*21;return `<rect x="${x}" y="45" width="16" height="47" rx="2" fill="#153547" stroke="#5f94a7"/><circle cx="${x+8}" cy="57" r="5.2" fill="#061c2c" stroke="#92b9c4"/><circle cx="${x+8}" cy="57" r="1.5" fill="#d1c58d"/>${led(x+8,72,-i*.3,1.9)}<path d="M${x+4} 80h8m-8 5h8" stroke="#6391a3"/>${terminal(x,101,16)}`}).join('')}
 <path d="M13 55H20M13 81H20" stroke="#74b6c9" stroke-width="5"/><path class="scada-traffic" d="M5 55H18M5 81H18" stroke="#62ffbc" stroke-width="2" stroke-dasharray="3 4"/>
 ${screws([[24,42],[156,42],[24,97],[156,97]])}`;}

function hmi(id,load){return `${shade(126,66)}
 <path d="M79 108V119H65V125H116V119H102V108" fill="#2d5369" stroke="#81b3c6" stroke-width="1.2"/>
 <path d="M25 20L32 14H159L165 21V103L158 110H25Z" fill="#16394f" stroke="#76aec2" stroke-width="1.2"/>
 <rect x="19" y="20" width="139" height="90" rx="6" fill="url(#${id}-steel)" stroke="#a8d3df" stroke-width="1.6"/>
 <rect x="28" y="29" width="119" height="66" rx="3" fill="#071a2a" stroke="#385e76" stroke-width="1.2"/>
 <path d="M33 35H142" stroke="#27506a" stroke-width="1"/><rect x="34" y="39" width="33" height="43" rx="2" fill="#102c3c"/>
 <path d="M42 48V72Q49 77 57 72V48Z" fill="#164e59" stroke="#7dd3d7"/><ellipse cx="49.5" cy="48" rx="7.5" ry="3" fill="#6c9ba9"/><path class="scada-screen-pulse" d="M43 63Q49 59 56 63V71Q49 75 43 71Z" fill="#62ffbc" opacity=".65"/>
 <path d="M57 66H76V55H100" fill="none" stroke="#376b80" stroke-width="3"/><path class="scada-traffic" d="M57 66H76V55H100" fill="none" stroke="#62ffbc" stroke-width="1.5" stroke-dasharray="3 5"/>
 <circle cx="109" cy="55" r="10" fill="#183d54" stroke="#65c4d1"/><path d="M110 47l-6 9h6l-2 7 8-12h-6Z" fill="#ffd38a"/>
 <rect x="78" y="74" width="61" height="11" rx="2" fill="#163447"/><path class="scada-screen-pulse" d="M81 81h7l5-5 7 7 5-5 7 2 5-4 5 5h14" fill="none" stroke="#00e5e9" stroke-width="1.5"/>
 <rect x="34" y="88" width="105" height="2" fill="#244a5f"/><rect class="scada-load-bar" x="34" y="88" width="${105*load/100}" height="2" fill="#00e5e9"/>
 ${led(89,102,-.2,2.3)}${screws([[24,25],[152,25],[24,104],[152,104]])}`;}

function server(id,load){return `${shade(126,52)}
 <path d="M48 18L59 9H137L126 18Z" fill="#547c91" stroke="#a1cad7"/><path d="M126 18L137 9V113L126 123Z" fill="#16344d" stroke="#6c9eb8"/>
 <rect x="48" y="18" width="78" height="105" rx="3" fill="url(#${id}-steel)" stroke="#92c4d5" stroke-width="1.4"/>
 ${[0,1,2].map(i=>{const y=27+i*28;return `<rect x="54" y="${y}" width="66" height="24" rx="2" fill="#0d2437" stroke="#578ba4"/><circle cx="64" cy="${y+12}" r="6" fill="#132f42" stroke="#668fa4"/><path d="M60 ${y+8}l8 8m0-8-8 8" stroke="#81acbb" stroke-width="1.3"/><path d="M76 ${y+6}h25m-25 5h25m-25 5h25" stroke="#426c82" stroke-width="1.6"/>${led(111,y+7,-i*.3,2)}${led(111,y+16,-i*.3-.5,1.7)}<path class="scada-scan" d="M76 ${y+20}h25" stroke="#00e5e9" stroke-width="1.5" stroke-dasharray="7 4"/>`}).join('')}
 <rect x="57" y="114" width="58" height="3" rx="1" fill="#183b4d"/><rect class="scada-load-bar" x="57" y="114" width="${58*load/100}" height="3" rx="1" fill="#62ffbc"/>
 <path d="M131 28v15m0 8v15m0 8v15m0 8v15" stroke="#4d7b96" stroke-width="2"/>
 ${screws([[51,22],[122,22],[51,119],[122,119]])}`;}

function networkSwitch(id,load){return `${shade(113,78)}
 <path d="M14 54L29 35H163L152 54Z" fill="#547f94" stroke="#9bcbd8" stroke-width="1.3"/><path d="M152 54L163 35V87L152 104Z" fill="#163a53" stroke="#75abc0"/>
 <rect x="14" y="54" width="138" height="50" rx="3" fill="url(#${id}-steel)" stroke="#9dcfda" stroke-width="1.4"/>
 <rect x="26" y="43" width="87" height="3" rx="1" fill="#254f64"/><rect class="scada-load-bar" x="26" y="43" width="${87*load/100}" height="3" rx="1" fill="#00e5e9"/>
 <path d="M122 41h25m-25 5h25" stroke="#234b62" stroke-width="2"/>
 ${[0,1,2,3,4,5,6,7].map(i=>{const x=23+i*15.3;return `${led(x+5.5,64,-i*.16,1.7)}${port(x,72,11,17)}`}).join('')}
 <path d="M25 96h9m7 0h9m7 0h9m7 0h9m7 0h9m7 0h9m7 0h9" stroke="#24485e" stroke-width="2"/>
 <path d="M44 88V113H9M119 88V113H169" fill="none" stroke="#32576b" stroke-width="3" stroke-linejoin="round"/><path class="scada-traffic" d="M44 88V113H9M119 88V113H169" fill="none" stroke="#62ffbc" stroke-width="1.5" stroke-dasharray="4 6"/>
 ${screws([[18,58],[148,58],[18,100],[148,100]])}`;}

function radio(id){return `${shade(125,61)}
 <path d="M71 112L90 26 111 112M80 72h21M75 94h31M83 49h14M81 72l23 22M100 72L77 94M83 49l18 23M97 49L81 72" fill="none" stroke="#6a9eb3" stroke-width="2" stroke-linejoin="round"/>
 <path d="M90 17V44" stroke="#c0e6ed" stroke-width="3" stroke-linecap="round"/><circle cx="90" cy="16" r="4" fill="#00e5e9" stroke="#c9fcff"/>
 <g class="scada-traffic" fill="none" stroke="#00e5e9" stroke-width="2" stroke-linecap="round"><path d="M77 17q-11 11 0 23M103 17q11 11 0 23"/><path d="M65 8q-22 21 0 42M115 8q22 21 0 42"/></g>
 <rect x="54" y="97" width="72" height="26" rx="3" fill="url(#${id}-steel)" stroke="#97c9d7" stroke-width="1.3"/>
 <rect x="62" y="102" width="27" height="15" rx="2" fill="#0c273b"/>${led(68,109,-.1)}${led(79,109,-.6)}<path class="scada-scan" d="M95 105h22m-22 6h22m-22 6h22" stroke="#62ffbc" stroke-width="1.4" stroke-dasharray="7 4"/>
 <path d="M49 108H54M126 108h8" stroke="#68a1b7" stroke-width="5"/>
 ${screws([[58,101],[122,101],[58,119],[122,119]])}`;}

const DRAWINGS = Object.freeze({'plc-rack':rack,'plc-cpu':cpu,'remote-io':remoteIo,hmi,'scada-server':server,'network-switch':networkSwitch,radio});

export function renderControlArt(type,{id='scada-control',state={}}={}){
 const drawing = Object.hasOwn(DRAWINGS,type) ? DRAWINGS[type] : null;
 if(!drawing)return '';
 const prefix=String(id).replace(/[^a-zA-Z0-9_-]/g,'-');
 return `<g class="scada-control-art scada-control-${type}">${drawing(prefix,finiteLoad(state?.load))}</g>`;
}
