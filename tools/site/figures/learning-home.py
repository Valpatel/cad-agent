"""Original homepage SVG narrative and charts derived only from committed evidence.
No CAD, solver, browser, network or dependency installation. Run with Python3.
"""
from pathlib import Path
import json, hashlib, math, sys
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/img/hero'
sys.path.insert(0, str(ROOT/'software'))
from cadagent.publish.anim.svg import REDUCED_MOTION
FONT='Inter,system-ui,sans-serif'
def text(x,y,s,size=22,cls='',anchor='start'):
 return f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'
def cinematic_hero(mobile=False):
 w,h=(1000,1000) if mobile else (1440,640)
 # Composed scene, not boxes: human at a bench, useful objects and an evolving memory overhead.
 person=(30,380) if mobile else (90,120)
 bench=(185,410,.92) if mobile else (480,100,.9)
 network=(365,80) if mobile else (850,15)
 docs=(55,75) if mobile else (310,38)
 s=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="title desc"><title id="title">Your idea becomes something useful — and helps the next person</title><desc id="desc">A person and a capable articulated machine work together at one engineering bench. The person sketches a need; the machine constructs a first part and hands it over. Human testing finds blocked access, feedback updates shared knowledge, and the machine produces a visibly revised second part. Real examples and a MANUFACTURER GUIDE contribute source, edition, limits. A messy knowledge lattice organizes into a topic tree. Wireframe objects become an enclosure, bracket and thermal device, checked before making. Human-reviewed feedback returns to improve the next design. Original conceptual artwork, not a hardware simulation or automatic model training.</desc><defs><radialGradient id="space"><stop stop-color="#1d3c51"/><stop offset="1" stop-color="#08131f"/></radialGradient><linearGradient id="glass" x2="1" y2="1"><stop stop-color="#3d8897" stop-opacity=".45"/><stop offset="1" stop-color="#0d263c" stop-opacity=".8"/></linearGradient><linearGradient id="metal"><stop stop-color="#cae2e5"/><stop offset="1" stop-color="#477786"/></linearGradient><linearGradient id="robot-metal" x2="1" y2="1"><stop stop-color="#e0edf2"/><stop offset=".45" stop-color="#789caa"/><stop offset="1" stop-color="#284f67"/></linearGradient><radialGradient id="idea"><stop stop-color="#fff3c7"/><stop offset=".3" stop-color="#ffc879"/><stop offset="1" stop-color="#d88c31" stop-opacity="0"/></radialGradient><filter id="glow"><feGaussianBlur stdDeviation="5"/></filter><pattern id="grid" width="70" height="70" patternUnits="userSpaceOnUse"><path d="M70 0H0V70" fill="none" stroke="#73b7bb" stroke-opacity=".1"/></pattern></defs><style>text{{font-family:Inter,system-ui,sans-serif;fill:#d8e9ee}}.flow{{stroke-dasharray:3 13;animation:current 6s linear infinite}}.draw{{stroke-dasharray:1400;animation:draw 8s ease-in-out infinite}}.solid{{animation:solid 8s ease-in-out infinite}}.lid{{animation:assemble 8s ease-in-out infinite}}.orb{{animation:breathe 5s ease-in-out infinite}}.still{{display:none}}@keyframes current{{to{{stroke-dashoffset:-192}}}}@keyframes draw{{0%,10%{{stroke-dashoffset:1400;opacity:.2}}48%,72%{{stroke-dashoffset:0;opacity:1}}95%,100%{{stroke-dashoffset:0;opacity:.8}}}}@keyframes solid{{0%,32%{{opacity:.7}}62%,100%{{opacity:1}}}}@keyframes assemble{{0%,25%{{transform:translateY(-85px)}}62%,82%{{transform:translateY(0)}}100%{{transform:translateY(-85px)}}}}@keyframes breathe{{0%,100%{{opacity:.5}}50%{{opacity:1}}}}.learned{{fill:#8cf5d5;animation:knowledge-gain 8s ease-in-out infinite}}@keyframes knowledge-gain{{0%,50%{{fill:#ffce88}}70%,100%{{fill:#8cf5d5}}}}.human-gesture{{animation:human-test 8s ease-in-out infinite;transform-origin:226px 191px}}@keyframes human-test{{0%,25%{{transform:rotate(-4deg)}}38%,55%{{transform:rotate(3deg)}}75%,100%{{transform:rotate(0)}}}}.robotarm{{transform-origin:128px 165px;animation:partner-work 8s ease-in-out infinite}}.handoff{{animation:handoff 8s ease-in-out infinite;transform:translate(var(--dx),var(--dy))}}.first-version{{animation:first-version 8s linear infinite}}.revised-version{{animation:revised-version 8s linear infinite;opacity:0}}@keyframes partner-work{{0%,12%{{transform:rotate(-8deg)}}24%,42%{{transform:rotate(0)}}54%{{transform:rotate(-10deg)}}72%,100%{{transform:rotate(0)}}}}@keyframes handoff{{0%,15%{{transform:translate(var(--dx),var(--dy))}}32%,50%{{transform:translate(0,0)}}68%,100%{{transform:translate(var(--dx),var(--dy))}}}}@keyframes first-version{{0%,50%{{opacity:1}}60%,100%{{opacity:0}}}}@keyframes revised-version{{0%,50%{{opacity:0}}66%,100%{{opacity:1}}}}@media(prefers-reduced-motion:reduce){{.handoff{{transform:translate(calc(var(--dx)*.5),calc(var(--dy)*.5))}}.first-version{{display:none}}.revised-version{{opacity:1}}*{{animation:none!important}}.moving{{display:none}}.still{{display:inline}}.solid{{opacity:1}}.draw{{stroke-dashoffset:0;opacity:1}}}}</style><rect width="{w}" height="{h}" rx="30" fill="url(#space)"/><ellipse cx="{w*.58}" cy="{h*.74}" rx="{w*.45}" ry="{h*.28}" fill="#183345" opacity=".45"/><path d="M0 {h*.73}L{w} {h*.57}V{h}H0Z" fill="url(#grid)"/>'''
 # Quiet depth cues, not filler particles: a technical horizon and a returning feedback orbit.
 s+=f'<ellipse cx="{w*.58}" cy="{h*.68}" rx="{w*.42}" ry="{h*.23}" fill="none" stroke="#6de3d1" stroke-opacity=".12"/>'
 s+=f'<path class="flow" d="M{w-90} {h-210}C{w-40} {h-30} 130 {h+30} 125 {h-250}" fill="none" stroke="#edbd74" stroke-width="3"/>'
 s+=f'<path class="flow" d="M{person[0]+245} {person[1]+135}Q{w*.35} 90 {network[0]+180} {network[1]+30}" fill="none" stroke="#86dfd2" stroke-width="2" opacity=".5"/>'
 # Person silhouette, facing the object: warm face/light and a purposeful hand at the workbench.
 x,y=person
 s+=f'<g transform="translate({x} {y})"><ellipse cx="88" cy="385" rx="120" ry="24" fill="#020b14" opacity=".55"/><path d="M28 150Q80 112 125 152L160 300 38 320Z" fill="#24495a" stroke="#7197a4" stroke-width="2"/><path d="M45 305L15 402M125 302l38 99" stroke="#314e60" stroke-width="25" stroke-linecap="round"/><path d="M34 166L-5 247 45 285M115 160l72 62 70-40" fill="none" stroke="#648796" stroke-width="24" stroke-linecap="round"/><path class="human-gesture" d="M226 191l31-10" stroke="#ffd5a3" stroke-width="15" stroke-linecap="round"/><path d="M64 48Q120 20 130 70L122 110 102 136 66 124 50 82Z" fill="#d3a984"/><path d="M46 78Q30 22 83 17q54-12 55 53l-25-20-58 42Z" fill="#152433"/><path d="M70 120l-1 28 35 10 2-30" fill="#ad8067"/><circle cx="246" cy="135" r="52" fill="url(#idea)" class="orb"/><path d="M239 135v-13a10 10 0 1 1 14 0v13m-13 6h12m-9 6h6" fill="none" stroke="#ffe3ad" stroke-width="3"/></g>'
 s+=f'<g transform="translate({x} {y})"><path d="M64 51q33-17 54 10l-2 40-20 25-22-9" fill="#f5c99e" opacity=".7"/><ellipse cx="57" cy="85" rx="6" ry="10" fill="#c29270"/><path d="M116 77l-1 16 7 3-10 5M114 72h7" fill="none" stroke="#795e4e" stroke-width="2"/><path d="M48 165l17 114 57-9-8-93M75 157l15 115" fill="none" stroke="#82a3ad" stroke-opacity=".6" stroke-width="2"/><path d="M-1 408h33M148 407h35" stroke="#102132" stroke-width="15" stroke-linecap="round"/></g>'
 # Evidence pages float behind the workbench. They are supporting resources, not the headline.
 x,y=docs
 s+=f'<g transform="translate({x} {y}) rotate(-10)"><rect width="130" height="170" rx="9" fill="#172f43" stroke="#809fae"/><path d="M20 30h70M20 48h90M20 66h75M20 120h84M20 137h60" stroke="#7aa3b4" stroke-width="3"/><path d="M22 86l26-12 30 14-28 13Z" fill="none" stroke="#83e0cb" stroke-width="2"/><path d="M20 153h68" stroke="#79e5d0" stroke-width="2"/></g>'
 # The lattice really changes geometry into a tree, with a useful static final counterpart.
 nx,ny=network
 messy=[(215+205*math.cos(j*2.399)*(.4+.6*(j%7)/6),110+100*math.sin(j*2.399)) for j in range(25)]
 tree=[]
 for j in range(25):
  level=int(math.log2(j+1));col=j-(2**level-1);tree.append(((col+.5)*430/2**level,level*52))
 edges=[((j-1)//2,j) for j in range(1,25)]
 s+=f'<g transform="translate({nx} {ny})"><g class="moving">'
 for a,b in edges:
  ma,mb=messy[a],messy[b];ta,tb=tree[a],tree[b]
  initial=f'M{ma[0]} {ma[1]}L{mb[0]} {mb[1]}';final=f'M{ta[0]} {ta[1]}L{tb[0]} {tb[1]}'
  s+=f'<path d="{initial}" stroke="#77d4ce" stroke-width="2" opacity=".7"><animate attributeName="d" values="{initial};{initial};{final};{final};{initial}" keyTimes="0;.15;.5;.85;1" dur="8s" repeatCount="indefinite"/></path>'
 for j,(m,t) in enumerate(zip(messy,tree)):
  s+=f'<circle cx="{m[0]}" cy="{m[1]}" r="{4 if j else 10}" fill="{["#ffc879","#7fe6d2"][bool(j)]}" stroke="#c5fff1" stroke-width="1"><animate attributeName="cx" values="{m[0]};{m[0]};{t[0]};{t[0]};{m[0]}" keyTimes="0;.15;.5;.85;1" dur="8s" repeatCount="indefinite"/><animate attributeName="cy" values="{m[1]};{m[1]};{t[1]};{t[1]};{m[1]}" keyTimes="0;.15;.5;.85;1" dur="8s" repeatCount="indefinite"/></circle>'
 s+='</g><g class="still">'
 for a,b in edges:s+=f'<path d="M{tree[a][0]} {tree[a][1]}L{tree[b][0]} {tree[b][1]}" stroke="#79e5d0" stroke-width="2"/>'
 for a,b in tree:s+=f'<circle cx="{a}" cy="{b}" r="7" fill="#79e5d0"/>'
 s+='</g></g>'
 # The machine partner stands across the same bench, with an articulated gripper and knowledge-lit head.
 rx,ry,rscale=(670,350,.78) if mobile else (1050,28,.95)
 s+=f'<g transform="translate({rx} {ry}) scale({rscale})"><path d="M150 300l-20 140h165l-40-140" fill="#16374c" stroke="#84afc0" stroke-width="3"/><path d="M145 142l-20 130 44 43h88l35-44-25-128Z" fill="url(#robot-metal)" stroke="#b8d8df" stroke-width="3"/><path d="M168 153h73v87h-73Z" fill="#133245" stroke="#91cbbf" stroke-width="2"/><path d="M181 170h45M181 183h45M181 196h30" stroke="#7cead0" stroke-width="3"/><circle class="learned" cx="205" cy="223" r="7" fill="#8cf5d5"/><path d="M176 112v30h53v-30" fill="#25485c" stroke="#80afba" stroke-width="3"/><rect x="140" y="10" width="120" height="108" rx="28" fill="url(#robot-metal)" stroke="#ceebed" stroke-width="3"/><path d="M155 38q44-21 90 0v42q-44 22-90 0Z" fill="#0a2031" stroke="#5a9aa8" stroke-width="2"/><path d="M170 58h20M210 58h20" stroke="#91ffe0" stroke-width="7" stroke-linecap="round"/><path d="M182 90h37" stroke="#517a8e" stroke-width="3"/><circle cx="135" cy="62" r="8" fill="#d1ab74"/><circle cx="266" cy="62" r="8" fill="#d1ab74"/><g class="robotarm"><path d="M128 165L40 240-100 280" fill="none" stroke="#123247" stroke-width="43" stroke-linecap="round"/><path d="M128 165L40 240-100 280" fill="none" stroke="url(#robot-metal)" stroke-width="28" stroke-linecap="round"/><circle cx="128" cy="165" r="27" fill="#335f73" stroke="#a6e6dd" stroke-width="4"/><circle cx="40" cy="240" r="22" fill="#315c70" stroke="#b5d9de" stroke-width="3"/><circle cx="40" cy="240" r="9" fill="#ddba7e"/><circle cx="-100" cy="280" r="17" fill="#274d64" stroke="#a5dfdf" stroke-width="3"/><path d="M-109 266l-38-8-17 23M-108 293l-37 11-19-23" fill="none" stroke="#bed5df" stroke-width="8" stroke-linejoin="round"/><path d="M-164 277v9" stroke="#7dffe2" stroke-width="5"/></g><path d="M274 171l54 102-82 75" fill="none" stroke="#22495f" stroke-width="40" stroke-linecap="round"/><path d="M274 171l54 102-82 75" fill="none" stroke="url(#robot-metal)" stroke-width="25" stroke-linecap="round"/><circle cx="328" cy="273" r="22" fill="#335e74" stroke="#a2d0da" stroke-width="3"/><path d="M245 338l-24 8-10 22M253 351l-15 22-26-5" fill="none" stroke="#c6dce4" stroke-width="8"/></g>'
 # Human sketch pad and a test tool make the collaboration visible without reading labels.
 hx,hy=(280,555) if mobile else (350,300)
 s+=f'<g transform="translate({hx} {hy})"><path d="M-30-5L95-24 140 19 8 47Z" fill="#173e55" stroke="#94d9df" stroke-width="2"/><path class="draw" d="M0 5L45-4 48 19 92 10 100-3 115 12 101 31 22 43Z" fill="none" stroke="#91ffe1" stroke-width="3"/><path d="M-18 54h110M-8 47v18M57 45v21M-8 57l12 14M57 57l-12 14" fill="none" stroke="#c0d9de" stroke-width="4"/></g>'
 # A luminous bench. Source-like geometry stays visibly illustrative, never passed off as product CAD.
 bx,by,k=bench
 s+=f'<g transform="translate({bx} {by}) scale({k})"><ellipse cx="380" cy="330" rx="390" ry="105" fill="#6de5d0" opacity=".08" filter="url(#glow)"/><path d="M-20 325L540 215 825 355 230 500Z" fill="#142d3d" stroke="#698b9a" stroke-width="3"/><path d="M230 500v30L825 385v-30M230 530L-20 355v-30" fill="#0b1d2b" stroke="#34596d" stroke-width="2"/><path d="M70 395v180M700 420v130" stroke="#1b3548" stroke-width="28"/>'
 # CAD workspace depth: faint projection, a scanning plane and patterned technical grid.
 s+='<path d="M115 50L600-42 710 24 220 125Z" fill="#214d64" fill-opacity=".28" stroke="#6ec3cc" stroke-opacity=".5"/><path class="draw" d="M120 55L602-35 700 23 223 118Z" fill="none" stroke="#a5ebef" stroke-width="2"/>'
 for j in range(11):
  s+=f'<path d="M{40+j*44} {337-j*8.6}l240 133" stroke="#39708a" stroke-opacity=".42" stroke-width="1"/>'
 for j in range(7):
  s+=f'<path d="M{-8+j*34} {330+j*22}l560-109" stroke="#39708a" stroke-opacity=".42" stroke-width="1"/>'
 # Enclosure: illustrative isometric construction, with the board visibly revealed by the moving lid.
 s+='<g transform="translate(170 120)"><path d="M0 100L220 60 330 120 100 170Z" fill="#2a766c" stroke="#95d7be" stroke-width="2" class="solid"/><g stroke="#e3c77d" stroke-width="3"><path d="M70 105h65v30M170 90v30h60M130 143h80" fill="none"/></g><path d="M115 95l55-10 35 19-55 11Z" fill="#1c2d3a" stroke="#a1b9bd"/><path d="M128 96l40-7 24 13-40 7Z" fill="#314957"/><path d="M50 173v42l53 35M120 255l180-39v-63" fill="none" stroke="#90c7d0" stroke-width="3"/><path d="M0 100v105l100 70V170M100 275l230-50V120" fill="#327e91" stroke="#c4fff1" stroke-width="2.5" class="solid"/><g class="lid"><path d="M-8 91L220 42 340 108 100 166Z" fill="url(#metal)" opacity=".85" stroke="#b7eff1" stroke-width="2"/><path d="M32 94l190-40M49 106l190-40M66 118l190-40" stroke="#386b7b" stroke-width="3"/></g><path class="draw" d="M0 100L220 60 330 120 100 170 0 100V205L100 275 330 225V120M100 170v105M0 205l230-45" fill="none" stroke="#a1fff0" stroke-width="3"/></g>'
 s+='<g transform="translate(170 120)" class="solid">'
 for x,y in [(26,110),(217,76),(301,124),(103,154)]:
  s+=f'<ellipse cx="{x}" cy="{y}" rx="7" ry="4" fill="#ffd794" stroke="#8b6746"/><path d="M{x-3} {y}h6" stroke="#74543d"/>'
 for j in range(9):
  s+=f'<path d="M{82+j*6} {109-j*1.05}l-8 2m{113+j*6} {123-j*1.05}l8-2" stroke="#f5cf80" stroke-width="2"/>'
 s+='</g>'
 # Two other useful objects: a mounting bracket and a compact finned thermal device.
 s+='<g transform="translate(535 165)" class="solid"><path d="M0 60L80 42 80-15 112-23V88L0 112Z" fill="url(#metal)" stroke="#c1e7ea" stroke-width="2"/><ellipse cx="32" cy="86" rx="9" ry="5" fill="#183b4d"/><ellipse cx="96" cy="12" rx="5" ry="9" fill="#183b4d"/></g><g transform="translate(70 290)" class="solid"><path d="M0 20L75 4 132 33 54 52Z" fill="#416b7b" stroke="#8ac8ce"/>'
 for j in range(7):s+=f'<path d="M{j*10} {18-j*2}v-46l55 29v46" fill="#6097a5" stroke="#abdedf" stroke-width="1"/>'
 s+='</g>'
 # The orange obstruction is diagnosed; the revised rib leaves access open.
 s+='<g transform="translate(170 120)"><path d="M118 189l156-32v30l-156 33Z" fill="#122d3e" stroke="#b6e5ed" stroke-width="2"/><path d="M140 185v29M172 179v29M204 172v29M236 166v29" stroke="#91cbd8" stroke-width="2"/><path d="M120 197l156-32" class="moving" stroke="#ff9b72" stroke-width="13" opacity="0"><animate attributeName="opacity" values="0;0;.95;.95;0;0" keyTimes="0;.3;.38;.52;.66;1" dur="8s" repeatCount="indefinite"/></path><g class="solid"><path d="M108 224l14 24 178-37-12-26Z" fill="#67c9b7" fill-opacity=".7" stroke="#aaffdf" stroke-width="2"/><circle cx="130" cy="242" r="4" fill="#122c39"/><circle cx="286" cy="209" r="4" fill="#122c39"/></g></g>'
 s+='<path class="flow" d="M-10 330Q300 235 720 350" fill="none" stroke="#8cead5" stroke-width="2"/></g>'
 # One tangible part travels between partners: first obstructed, then revised with clear access and a rib.
 px,py=(330,610) if mobile else (410,340)
 dx,dy=(238,-42) if mobile else (500,-46)
 s+=f'<g transform="translate({px} {py})"><g class="handoff" style="--dx:{dx}px;--dy:{dy}px"><ellipse cx="25" cy="48" rx="62" ry="15" fill="#07121d" opacity=".65"/><g class="first-version"><path d="M-28-16l65-13 38 27-67 17Z M-28-16v44l36 27V15 M8 55l67-15V-2" fill="#bd9369" stroke="#ffe4b2" stroke-width="3"/><path d="M5 30l46-10" stroke="#fd8b70" stroke-width="10"/></g><g class="revised-version"><path d="M-28-16l65-13 38 27-67 17Z M-28-16v44l36 27V15 M8 55l67-15V-2" fill="#4bada5" stroke="#c1ffdf" stroke-width="3"/><path d="M16 24l43-9v14l-43 10Z" fill="#143a4a" stroke="#b9ffdf" stroke-width="2"/><path d="M11 44l48-10 8 8-50 11Z" fill="#a2e1cc"/><path d="M-10-8l12 8 25-20" fill="none" stroke="#d5ffe2" stroke-width="4"/></g></g></g>'
 # Feedback enters the machine's knowledge, rather than merely circling the page.
 feedback=f'M{px} {py-20}Q{w*.53} {h*.1} {rx+195*rscale} {ry+55*rscale}'
 s+=f'<path d="{feedback}" class="flow" fill="none" stroke="#ffce87" stroke-width="2" opacity=".6"/><circle class="moving" r="7" fill="#ffe1a3" opacity="0"><animateMotion path="{feedback}" dur="8s" repeatCount="indefinite" keyPoints="0;0;1;1" keyTimes="0;.48;.68;1" calcMode="linear"/><animate attributeName="opacity" values="0;0;1;0;0" keyTimes="0;.47;.5;.7;1" dur="8s" repeatCount="indefinite"/></circle>'
 s+=f'<g transform="translate({w-240} {h-170})"><circle r="32" fill="#123a39" stroke="#80e9ce" stroke-width="2"/><path d="M-14 0l10 11 21-25" fill="none" stroke="#a5fbe0" stroke-width="5"/></g>'
 # The human story is in readable HTML, not tiny labels inside phone artwork.
 s+='<path d="M30 0H{0}" fill="none" opacity="0"/>'.format(w)
 return s.replace('<style>', '<style>'+REDUCED_MOTION, 1)+'</svg>\n'

def trace_chart():
 source=ROOT/'tests/fixtures/cfd_runs/exhaust-under-opening/postProcessing/domain0/zone_heater/0/volFieldValue.dat'
 samples=[(float(line.split()[0]),float(line.split()[-1])-273.15) for line in source.read_text().splitlines() if line and not line.startswith('#')]
 pts=' '.join(f'{70+t/1500*620:.2f},{250-(v-30)/12*180:.2f}' for t,v in samples)
 style='<style>text{font-family:system-ui,sans-serif;fill:#eaf3f7}.line{stroke-dasharray:1600;animation:draw 10s ease-in-out infinite}@keyframes draw{0%{stroke-dashoffset:1600}75%,100%{stroke-dashoffset:0}}@media(prefers-reduced-motion:reduce){.line{animation:none}}</style>'
 s='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 390" width="760" height="390" role="img" aria-label="Recorded 20 watt box CFD heater-zone temperature over 1500 solver iterations">'+style+'<rect width="760" height="390" rx="20" fill="#102332"/>'+text(34,42,'THERMAL / RECORDED SOLVER TRACE',21)+text(34,75,'20 W box · heater-zone average, °C',19)
 for v in [30,34,38,42]:
  y=250-(v-30)/12*180;s+=f'<path d="M70 {y}H700" stroke="#385062"/>'+text(32,y+6,str(v),15)
 s+=f'<polyline class="line" points="{pts}" fill="none" stroke="#ffcb83" stroke-width="3"/>'+text(70,284,'0',16)+text(660,284,'1500',16)+text(350,313,'solver iterations — not seconds',18)+text(34,350,f'Final sample {samples[-1][1]:.2f} °C · simulation, not a measurement',19)
 return s.replace('<style>', '<style>'+REDUCED_MOTION, 1)+'</svg>\n',{'input':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'samples':len(samples),'final_c':samples[-1][1]}
def balance_chart():
 p=ROOT/'docs/img/cfd/SOURCE.json';d=json.loads(p.read_bytes());s='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 390" width="760" height="390" role="img" aria-label="Recorded airflow comparison retains the ducted case failed balance and steady criteria"><style>text{font-family:system-ui,sans-serif;fill:#edf4f8}.bar{transform-box:fill-box;transform-origin:left;animation:grow 9s ease-in-out infinite}@keyframes grow{0%{transform:scaleX(.03)}55%,100%{transform:scaleX(1)}}@media(prefers-reduced-motion:reduce){.bar{animation:none}}</style><rect width="760" height="390" rx="20" fill="#102332"/>'+text(32,42,'AIRFLOW / CHECK THE BALANCE',22)
 for j,(key,label) in enumerate([('exhaust-under-opening','Fan under opening'),('exhaust-ducted','Ducted fan')]):
  f=d['facts'][key];y=90+j*130;s+=text(32,y,label,22)+text(32,y+30,f"{f['mass_flow_g_s']:.2f} g/s · {f['heat_out_w']:.2f} W out / 20 W in",19)+f'<rect class="bar" x="32" y="{y+47}" width="{f["heat_out_w"]/20*640:.2f}" height="22" rx="5" fill="{["#79e5d0","#ffcb83"][j]}"/>'+text(32,y+96,f"Balance {f['energy_balance_pct']:+.1f}% · "+('steady, energy check passes' if f['steady'] else 'not steady; energy check fails'),18)
 s+=text(32,372,'Recorded OpenFOAM cases · not a tested cooling guarantee',18)
 return s.replace('<style>', '<style>'+REDUCED_MOTION, 1)+'</svg>\n',{'input':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'facts':d['facts']}
if __name__=='__main__':
 for mobile in [False,True]:(OUT/('learning-loop-mobile.svg' if mobile else 'learning-loop.svg')).write_text(cinematic_hero(mobile))
 records={}
 for name,fn in [('thermal-history',trace_chart),('airflow-balance',balance_chart)]:
  svg,record=fn();(OUT/(name+'.svg')).write_text(svg);records[name]=record
 (OUT/'learning-evidence.json').write_text(json.dumps({'illustration':'learning-loop variants are conceptual process artwork, not an engineering result','generated_by':'tools/site/figures/learning-home.py','figures':records},indent=2)+'\n')
