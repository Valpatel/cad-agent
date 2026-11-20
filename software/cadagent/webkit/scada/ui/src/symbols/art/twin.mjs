/** Decorative process illustrations. Motion is driven by the simulation host;
 * tank liquid height is illustrative, except for the modeled gas-buffer fill. */
const safeId=value=>String(value||'equipment').replace(/[^a-zA-Z0-9_-]/g,'-');

function definitions(id){return `<defs>
 <linearGradient id="${id}-steel" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#112d3c"/><stop offset=".25" stop-color="#548d9f"/><stop offset=".46" stop-color="#b1dce8"/><stop offset=".7" stop-color="#3b6a7f"/><stop offset="1" stop-color="#102b39"/></linearGradient>
 <linearGradient id="${id}-glass" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#00f0ff" stop-opacity=".15"/><stop offset=".3" stop-color="#c5f4ff" stop-opacity=".1"/><stop offset=".7" stop-color="#4eb0c8" stop-opacity=".04"/><stop offset="1" stop-color="#080e19" stop-opacity=".5"/></linearGradient>
 <linearGradient id="${id}-liquid" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#05ffa1" stop-opacity=".82"/><stop offset=".35" stop-color="#1ba894" stop-opacity=".66"/><stop offset="1" stop-color="#15546b" stop-opacity=".6"/></linearGradient>
 <linearGradient id="${id}-dome" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#b3e3eb"/><stop offset=".4" stop-color="#568fa4"/><stop offset="1" stop-color="#213b51"/></linearGradient>
 <linearGradient id="${id}-fire" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffe6a2"/><stop offset=".3" stop-color="#ffbe57"/><stop offset=".72" stop-color="#ff7b37"/><stop offset="1" stop-color="#d6462c"/></linearGradient>
 <radialGradient id="${id}-warm"><stop stop-color="#ffac45" stop-opacity=".42"/><stop offset=".5" stop-color="#ff7d37" stop-opacity=".14"/><stop offset="1" stop-color="#ff7933" stop-opacity="0"/></radialGradient>
 <radialGradient id="${id}-cool"><stop stop-color="#00f0ff" stop-opacity=".23"/><stop offset="1" stop-color="#00f0ff" stop-opacity="0"/></radialGradient>
 <radialGradient id="${id}-fault"><stop stop-color="#ff2a6d" stop-opacity=".42"/><stop offset=".5" stop-color="#ff2a6d" stop-opacity=".15"/><stop offset="1" stop-color="#ff2a6d" stop-opacity="0"/></radialGradient>
 <radialGradient id="${id}-blast"><stop stop-color="#fff9d8"/><stop offset=".24" stop-color="#ffd379" stop-opacity=".95"/><stop offset=".56" stop-color="#ff7e38" stop-opacity=".65"/><stop offset="1" stop-color="#ff2a6d" stop-opacity="0"/></radialGradient>
 </defs>`;}

const bolts=(cx,cy,r=24)=>[0,60,120,180,240,300].map(a=>`<circle cx="${cx}" cy="${cy-r}" r="1.6" fill="#d4edf2" transform="rotate(${a} ${cx} ${cy})"/>`).join('');
const bubbles=()=>[[-23,0,3.2,-.4],[-7,11,2.2,-2.8],[17,7,3,-1.6],[29,-3,1.8,-3.7],[4,-5,2.6,-.9],[-30,13,1.7,-2]].map(([x,y,r,delay],i)=>`<circle class="twin-art-bubble" cx="${90+x}" cy="${108+y}" r="${r}" style="--bubble-delay:${delay}s;--bubble-duration:${3.2+i*.3}s"/>`).join('');

function digester(id){return `<ellipse cx="90" cy="126" rx="59" ry="8" fill="#05050d" opacity=".65"/>
 <defs><clipPath id="${id}-vessel"><path d="M41 39V108C41 129 139 129 139 108V39Z"/></clipPath></defs>
 <path d="M41 39V108C41 129 139 129 139 108V39Z" fill="#0d2435" stroke="#75b7cb" stroke-width="1.5"/>
 <g clip-path="url(#${id}-vessel)">
  <path class="twin-art-wave twin-art-wave-back" d="M-30 72Q-10 62 10 72T50 72T90 72T130 72T170 72T210 72T250 72V145H-30Z" fill="#05ffa1" opacity=".32"/>
  <path class="twin-art-wave" d="M-30 80Q-10 70 10 80T50 80T90 80T130 80T170 80T210 80T250 80V145H-30Z" fill="url(#${id}-liquid)"/>
  <path d="M90 44V112" stroke="#c2e8ee" stroke-width="2.4" opacity=".55"/>
  <g class="twin-art-mixer" fill="#bbf0f0" opacity=".78"><ellipse cx="90" cy="96" rx="25" ry="4"/><path d="M72 96l-7-7 16 3M108 96l7 7-16-3"/></g>
  <g fill="#a7ffdf">${bubbles()}</g>
  <path d="M41 39V108C41 129 139 129 139 108V39Z" fill="url(#${id}-glass)"/>
  <path d="M51 48V108" stroke="#d0f7ff" stroke-width="3" opacity=".22"/>
  <path d="M129 46V108" stroke="#75dae6" opacity=".17"/>
 </g>
 <path d="M41 39C41 6 139 6 139 39Q90 62 41 39Z" fill="url(#${id}-dome)" stroke="#73becd" stroke-width="1.3"/>
 <ellipse cx="90" cy="39" rx="49" ry="14" fill="none" stroke="#9edee5" stroke-width="1.2" opacity=".7"/>
 <path d="M54 28Q66 16 84 16" fill="none" stroke="#d2faff" stroke-width="2.5" stroke-linecap="round" opacity=".38"/>
 <path d="M84 15V5H96V15" fill="#477b91" stroke="#a4d1df"/><ellipse cx="90" cy="5" rx="6" ry="2" fill="#9dd1e3"/>
 <path d="M41 106Q90 130 139 106" fill="none" stroke="#73bdc7" stroke-width="1.2" opacity=".66"/>
 <path d="M142 42V118M150 42V115M142 52H150M142 63H150M142 74H150M142 85H150M142 96H150M142 107H150" fill="none" stroke="#4f98ac" stroke-width="1.4"/>
 <circle cx="120" cy="58" r="8" fill="#091522" stroke="#75c7d2"/><path class="twin-art-needle" d="M120 58l4-4" stroke="#05ffa1" stroke-width="1.6"/>
 <path d="M24 90H41M139 88H158" stroke="url(#${id}-steel)" stroke-width="8"/><path d="M26 86V94M156 84V92" stroke="#a7d3e0" stroke-width="2"/>`;}

function storage(id){return `<ellipse cx="90" cy="102" rx="50" ry="7" fill="#05050d" opacity=".65"/>
 <defs><clipPath id="${id}-buffer"><path d="M48 24V84C48 105 132 105 132 84V24Z"/></clipPath></defs>
 <path d="M48 24V84C48 105 132 105 132 84V24Z" fill="#0b2032" stroke="#78bfc9" stroke-width="1.4"/>
 <g clip-path="url(#${id}-buffer)"><rect class="twin-art-buffer-fill" data-twin-buffer-liquid x="48" y="28" width="84" height="70" fill="url(#${id}-liquid)"/><path d="M48 24V84C48 105 132 105 132 84V24Z" fill="url(#${id}-glass)"/><path d="M58 34V84" stroke="#b2f5ff" stroke-width="3" opacity=".25"/></g>
 <ellipse cx="90" cy="24" rx="42" ry="13" fill="url(#${id}-dome)" stroke="#9ad5df"/>
 <path d="M48 84Q90 108 132 84M48 63Q90 84 132 63M48 43Q90 66 132 43" fill="none" stroke="#6cc5d0" opacity=".32"/>
 <path d="M86 11V4H94V11" fill="#549eb1"/>
 <path d="M140 33h8M140 46h5M140 59h8M140 72h5M140 85h8" stroke="#70d0df" stroke-width="1.6"/>
 <path d="M31 73H48M132 73H148" stroke="url(#${id}-steel)" stroke-width="7"/>`;}

function rotor(cx,cy,className='twin-art-rotor'){return `<g class="${className}" style="transform-origin:${cx}px ${cy}px">${[0,60,120,180,240,300].map(a=>`<path d="M${cx-3} ${cy-4}C${cx-18} ${cy-8} ${cx-21} ${cy-20} ${cx-14} ${cy-21}Q${cx-1} ${cy-20} ${cx+2} ${cy-7}Z" fill="#b4eff5" transform="rotate(${a} ${cx} ${cy})"/>`).join('')}<circle cx="${cx}" cy="${cy}" r="6" fill="#296d83" stroke="#c9f6ff" stroke-width="1.5"/></g>`;}

function machine(id,kind){const feed=kind==='feed';return `<g class="twin-art-pump-body"><ellipse cx="88" cy="100" rx="64" ry="7" fill="#05050d" opacity=".6"/>
 <path d="M12 61H38M125 61H168" stroke="#326f82" stroke-width="13"/><path d="M12 61H38M125 61H168" stroke="#05ffa1" stroke-width="2.5" class="twin-art-stream"/>
 <path d="M35 89H136V97H35Z" fill="#23485f" stroke="#71b9cc"/><path d="M49 81V90M119 81V90" stroke="#6cb9ca" stroke-width="5"/>
 <rect x="71" y="30" width="63" height="57" rx="7" fill="url(#${id}-steel)" stroke="#88c7d5"/>
 <path d="M105 37V80M114 37V80M123 37V80" stroke="#102b39" stroke-width="3" opacity=".6"/>
 <circle cx="65" cy="58" r="31" fill="#15334b" stroke="#6dcada" stroke-width="2"/>
 <path d="M57 29C31 34 25 64 42 80C62 97 92 84 97 62" fill="none" stroke="#8ad7df" stroke-width="3" opacity=".72"/>
 <circle cx="65" cy="58" r="23" fill="#080e1d" stroke="#2c768f"/>
 ${rotor(65,58)}${bolts(65,58,27)}
 <rect x="96" y="20" width="23" height="11" rx="3" fill="#2b667a" stroke="#71c6d2"/>
 <circle class="twin-art-status-light" cx="108" cy="25.5" r="2.5"/>
 ${feed?'<path d="M17 52v18M155 52v18" stroke="#99dce6" stroke-width="3"/>':''}</g>`;}

/** A packaged generator has a cabinet silhouette, cooling grille, exhaust and
 * electrical output. It deliberately does not reuse the pump/volute body. */
function generator(id){return `<g class="twin-art-generator-enclosure">
 <ellipse cx="90" cy="102" rx="67" ry="7" fill="#05050d" opacity=".65"/>
 <path d="M42 88V98M126 88V98" stroke="#6a9aad" stroke-width="7"/>
 <path d="M29 95H149V102H29Z" fill="#173549" stroke="#5e94ab" stroke-width="1.2"/>
 <path d="M50 26V12Q50 9 54 9H70V16H59V26" fill="url(#${id}-steel)" stroke="#a2d7e0" stroke-width="1.2"/>
 <path d="M68 7V18" stroke="#d8edf0" stroke-width="3"/>
 <g class="twin-art-generator-heat" fill="none" stroke="#c5d9e4" stroke-width="1.5" stroke-linecap="round"><path d="M73 12q7-4 5-9"/><path d="M78 17q10-3 10-11"/></g>
 <path d="M32 30L48 20H149L134 30Z" fill="#588b9f" stroke="#9ed7e2" stroke-width="1.2"/>
 <path d="M134 30L149 20V82L134 93Z" fill="#15364e" stroke="#70b2c8" stroke-width="1.3"/>
 <path d="M32 30H134V93H32Z" fill="url(#${id}-steel)" stroke="#9bd6df" stroke-width="1.4"/>
 <path d="M36 34H130" stroke="#c4eef2" stroke-width="1.5" opacity=".7"/>
 <rect x="40" y="40" width="45" height="43" rx="3" fill="#0a1e2e" stroke="#74b8cc" stroke-width="1.4"/>
 <g transform="translate(24 26) scale(.6)">${rotor(65,58,'twin-art-rotor twin-art-generator-fan')}</g>
 <path d="M44 46H81M44 53H81M44 60H81M44 67H81M44 74H81M44 80H81" stroke="#6395a9" stroke-width="3"/>
 <rect x="91" y="39" width="35" height="45" rx="3" fill="#0a192b" stroke="#4b7895" stroke-width="1.2"/>
 <rect x="96" y="43" width="25" height="10" rx="2" fill="#102b3a" stroke="#6099a8"/>
 <path class="twin-art-generator-meter" d="M99 48h4l2-3 3 5 3-4 2 2h5" fill="none" stroke="#80f5ff" stroke-width="1.6" stroke-linejoin="round"/>
 <path class="twin-art-generator-electric" d="M111 57L99 72H108L104 84L120 66H111Z" fill="#ffd186" stroke="#fff0b6" stroke-width=".7" stroke-linejoin="round"/>
 <circle class="twin-art-status-light" cx="121" cy="89" r="2.2"/>
 <path d="M141 36V69M145 34V66" stroke="#75b4c8" stroke-width="1.3" opacity=".6"/>
 <path d="M15 78H31" stroke="#ac9b77" stroke-width="5"/><path d="M20 73V83" stroke="#d7c69d" stroke-width="2"/>
 <path d="M146 75H158V92H170" fill="none" stroke="#45637b" stroke-width="4.5" stroke-linejoin="round"/>
 <path class="twin-art-generator-current" d="M146 75H158V92H170" fill="none" stroke="#ffd186" stroke-width="2" stroke-linejoin="round"/>
 <circle cx="145" cy="75" r="3" fill="#ffe3aa" stroke="#9d6f38"/>
 <path d="M37 87H83" stroke="#163548" stroke-width="2"/>
 </g>`;}

function conditioning(id){return `<ellipse cx="87" cy="100" rx="63" ry="7" fill="#05050d" opacity=".6"/>
 <path d="M12 70H40M67 70H109M136 70H168" stroke="#367e95" stroke-width="8"/><path d="M12 70H40M67 70H109M136 70H168" stroke="#05ffa1" stroke-width="2.5" class="twin-art-stream"/>
 ${[40,107].map((x,i)=>`<g><rect x="${x}" y="20" width="32" height="73" rx="13" fill="url(#${id}-steel)" stroke="#88c4d3"/><ellipse cx="${x+16}" cy="25" rx="15" ry="6" fill="url(#${id}-dome)"/><rect x="${x+8}" y="38" width="16" height="39" rx="4" fill="#0a182b"/><path class="twin-art-filter-stream" style="animation-delay:${i*-.5}s" d="M${x+16} 73V42" stroke="#05ffa1" stroke-width="3" stroke-linecap="round"/><path d="M${x+5} 82H${x+27}" stroke="#85c9d8"/><path d="M${x+7} 94V101M${x+25} 94V101" stroke="#4c879d" stroke-width="3"/></g>`).join('')}
 <path d="M70 33H110" stroke="#3c8297" stroke-width="6"/>
 <circle cx="88" cy="33" r="10" fill="#0b2034" stroke="#7ed9de"/><path class="twin-art-needle" d="M88 33l4-5" stroke="#05ffa1" stroke-width="2"/><circle cx="88" cy="33" r="2" fill="#05ffa1"/>`;}

function fire(id){return `<g class="twin-art-fire">
 <ellipse class="twin-art-fire-halo" cx="90" cy="48" rx="53" ry="49" fill="url(#${id}-warm)"/>
 <g class="twin-art-fire-size"><path class="twin-art-flame-outer" d="M90 75C63 63 71 43 83 29C83 44 96 38 94 9C121 33 123 61 90 75Z" fill="url(#${id}-fire)"/>
 <path class="twin-art-flame-middle" d="M91 74C74 64 80 49 89 40C89 52 100 44 99 31C114 49 111 65 91 74Z" fill="#ffd279"/>
 <path class="twin-art-flame-core" d="M90 74C82 66 85 60 91 53C92 62 99 59 99 55C105 66 97 71 90 74Z" fill="#fff4c1"/>
 </g>
 <g fill="#ffd99a"><circle class="twin-art-ember" cx="75" cy="40" r="1.5" style="--ember-delay:-.2s"/><circle class="twin-art-ember" cx="106" cy="28" r="1.2" style="--ember-delay:-1.2s"/><circle class="twin-art-ember" cx="92" cy="20" r="1.1" style="--ember-delay:-.7s"/></g>
 </g>`;}

function flare(id){return `<ellipse cx="90" cy="104" rx="44" ry="6" fill="#05050d" opacity=".65"/>
 ${fire(id)}
 <path d="M82 76V99Q90 104 98 99V76Z" fill="url(#${id}-steel)" stroke="#8ab9cb"/>
 <ellipse cx="90" cy="75" rx="13" ry="4" fill="#162638" stroke="#e2bf87" stroke-width="1.5"/>
 <path d="M82 91L68 102M98 91l14 11" stroke="#508a9f" stroke-width="3"/>
 <path d="M42 93H82" stroke="#607b91" stroke-width="7"/><path d="M42 93H82" class="twin-art-stream" stroke="#ffd09a" stroke-width="2"/>`;}

function usefulGas(id){return `<ellipse cx="90" cy="104" rx="54" ry="6" fill="#05050d" opacity=".6"/>
 <path d="M52 20H128V99H52Z" fill="url(#${id}-steel)" stroke="#71bbc9"/>
 <path d="M52 20Q90 1 128 20" fill="url(#${id}-dome)" stroke="#71bbc9"/>
 <path d="M116 11V2H132V25" fill="#3f768e" stroke="#7ac4cf"/>
 <rect x="62" y="29" width="56" height="56" rx="15" fill="#0b1323" stroke="#5c9fb6"/>
 <g transform="translate(29 28) scale(.67)">${fire(id)}</g>
 <path d="M14 92H52M128 92H163" stroke="#537f97" stroke-width="8"/><path d="M14 92H52" class="twin-art-stream" stroke="#f8d190" stroke-width="2.4"/>
 <path d="M67 94h46" stroke="#173447" stroke-width="3"/>`;}

function net(id){return `<ellipse cx="90" cy="58" rx="71" ry="49" fill="url(#${id}-cool)"/>
 <circle cx="90" cy="55" r="39" fill="#0b1c32" stroke="#00bfdb" stroke-width="1.5"/>
 <circle class="twin-art-charge-orbit" cx="90" cy="55" r="32" fill="none" stroke="#00f0ff" stroke-width="2.5" stroke-dasharray="24 11 5 11"/>
 <path class="twin-art-bolt" d="M94 27L70 58H88L83 82L110 48H93Z" fill="#05ffa1"/>
 <path d="M5 56H43M137 56H175" stroke="#246c89" stroke-width="5"/><path d="M5 56H43M137 56H175" class="twin-art-stream" stroke="#00f0ff" stroke-width="2.5"/>
 <path d="M61 103H119" stroke="#4d9fba" stroke-width="3" stroke-linecap="round"/>`;}

/** Fault overlays are fictional scenario effects. The host owns the numerical
 * state and readable status; these never define engineering thresholds. */
function pressureEffects(id,kind){const cy=kind==='digester'?70:57,ry=kind==='digester'?57:46;return `<g class="twin-art-pressure-effects">
 <ellipse class="twin-art-pressure-glow" cx="90" cy="${cy}" rx="73" ry="${ry+8}" fill="url(#${id}-fault)"/>
 <ellipse class="twin-art-pressure-ring" cx="90" cy="${cy}" rx="61" ry="${ry}" fill="none" stroke-width="1.5" stroke-dasharray="17 5 3 5"/>
 <path class="twin-art-pressure-wave" d="M23 ${cy-16}Q15 ${cy} 23 ${cy+16}M157 ${cy-16}Q165 ${cy} 157 ${cy+16}" fill="none" stroke-width="2.3" stroke-linecap="round"/>
 </g>`;}

function machineFault(id){return `<g class="twin-art-fault-effects">
 <ellipse class="twin-art-fault-halo" cx="92" cy="55" rx="69" ry="43" fill="url(#${id}-fault)"/>
 <path class="twin-art-fracture" d="M112 32L103 44l8 7-12 12 7 17" fill="none" stroke="#ff2a6d" stroke-width="2.5" stroke-linejoin="round"/>
 <g class="twin-art-fault-sparks" fill="none" stroke="#ffcc87" stroke-width="2" stroke-linecap="round"><path d="M112 24l4-8M120 29l8-3M112 34l8 4M105 26l-5-6"/><circle cx="112" cy="28" r="2.3" fill="#ffe2b1" stroke="none"/></g>
 <g class="twin-art-fault-smoke" fill="none" stroke="#a79abf" stroke-width="4" stroke-linecap="round"><path class="twin-art-smoke" d="M108 27C95 18 117 13 107 5"/><path class="twin-art-smoke twin-art-smoke-two" d="M116 28C128 15 110 13 122 1"/></g>
 </g><g class="twin-art-overload-effects" fill="none" stroke="#ffbd69" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
 <circle class="twin-art-overload-ring" cx="65" cy="58" r="35" stroke-dasharray="12 6"/>
 <path d="M145 29l-8 15h8l-10 20M23 36l-7 13h7l-6 10"/>
 </g>`;}

function bufferIncident(id){return `<g class="twin-art-buffer-damage">
 <path d="M123 51l-7 11 11 5-8 14 13-8 2-10-8-4Z" fill="#07101b" stroke="#db8e80" stroke-width="1.3" stroke-linejoin="round"/>
 <path class="twin-art-buffer-scar" d="M107 31l-7 13 12 10-5 19 13 10M69 28l5 13-8 12" fill="none" stroke="#e58c68" stroke-width="1.5" stroke-linecap="round"/>
 </g>
 <g class="twin-art-leak-effects"><g class="twin-art-leak-size">
  <path class="twin-art-leak-haze" d="M129 72C141 67 143 48 166 34C170 49 162 67 133 77Z" fill="#a3e7f0" opacity=".15"/>
  <g class="twin-art-leak-jets" fill="none" stroke-linecap="round"><path d="M130 72Q147 69 163 43"/><path d="M131 74Q151 75 172 62"/><path d="M132 70Q141 62 147 44"/></g>
  <g class="twin-art-vapor-clouds" fill="#aedfe8">
   <path class="twin-art-vapor" style="--vapor-delay:0s" d="M139 65c-8-4-3-13 4-12-3-9 12-14 15-5 10-1 14 12 5 16-6 6-17 8-24 1Z"/>
   <path class="twin-art-vapor" style="--vapor-delay:-.8s" d="M139 65c-8-4-3-13 4-12-3-9 12-14 15-5 10-1 14 12 5 16-6 6-17 8-24 1Z"/>
   <path class="twin-art-vapor" style="--vapor-delay:-1.6s" d="M139 65c-8-4-3-13 4-12-3-9 12-14 15-5 10-1 14 12 5 16-6 6-17 8-24 1Z"/>
  </g>
 </g></g>
 <g class="twin-art-incident-fire">
 <path class="twin-art-incident-pipe" d="M132 73h13l5 7" fill="none" stroke="#ff2a6d" stroke-width="4" stroke-linecap="round"/>
 <g class="twin-art-leak-flame-size"><g transform="translate(90 31) scale(.65)">${fire(id)}</g></g>
 </g>
 <g class="twin-art-after-smoke" fill="#857d95"><path class="twin-art-smoke" d="M101 36c-16-4-20-15-9-22-6-10 8-17 17-10 13-7 27 7 17 17 12 12-6 21-25 15Z"/><path class="twin-art-smoke twin-art-smoke-two" d="M105 38c-9-6-2-16 7-13-1-11 17-14 20-2 14 4 5 19-8 16Z"/></g>
 <g class="twin-art-burst-effects">
  <ellipse class="twin-art-burst-flash" cx="103" cy="58" rx="72" ry="50" fill="url(#${id}-blast)"/>
  <ellipse class="twin-art-burst-ring" cx="103" cy="58" rx="45" ry="29" fill="none" stroke="#ffe4a0" stroke-width="2.4"/>
  <ellipse class="twin-art-burst-ring twin-art-burst-ring-two" cx="103" cy="58" rx="37" ry="24" fill="none" stroke="#ff8c54" stroke-width="1.3"/>
  <g class="twin-art-burst-rays" fill="none" stroke="#ffc66d" stroke-width="2" stroke-linecap="round"><path d="M91 44l-8-12M113 43l7-14M123 53l17-6M122 65l17 8M108 72l5 16M92 70l-9 13M82 57H64"/></g>
  ${[[102,56,-43,-21,-100],[105,60,39,21,130],[100,57,-26,28,-140],[107,54,31,-29,170],[100,53,-9,-37,-70]].map(([x,y,dx,dy,turn],i)=>`<path class="twin-art-burst-debris" style="--debris-x:${dx}px;--debris-y:${dy}px;--debris-turn:${turn}deg;--debris-delay:${i*.025}s" d="M${x-3} ${y-2}l7-2 2 4-6 3Z" fill="${i%2?'#a7c0c9':'#ffc188'}" stroke="#fff1c7" stroke-width=".6"/>`).join('')}
 </g>`;}

/** All visuals are decorative; the parent button provides the value and name. */
export function equipmentArt(node={}){
 const id=`twin-art-${safeId(node.id)}`;
 const kind=node.id==='othergas'?'othergas':node.kind;
 const drawings={digester,storage,feed:id=>machine(id,'feed'),pump:id=>machine(id,'pump'),turbine:generator,conditioning,flare,othergas:usefulGas,net};
 const draw=drawings[kind]||conditioning;
 const height=kind==='digester'?136:112;
 const vessel=kind==='digester'||kind==='storage';
 const machinery=['feed','pump','turbine','conditioning','net'].includes(kind);
 return `<span class="twin-equipment-art twin-equipment-art-${safeId(kind)}" aria-hidden="true"><svg viewBox="0 0 180 ${height}" focusable="false" aria-hidden="true">${definitions(id)}${vessel?pressureEffects(id,kind):''}<g class="${vessel?'twin-art-vessel':'twin-art-body'}">${draw(id)}</g>${machinery?machineFault(id):''}${kind==='storage'?bufferIncident(id):''}</svg></span>`;
}
