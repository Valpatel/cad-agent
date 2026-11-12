"""Original homepage SVG narrative and charts derived only from committed evidence.
No CAD, solver, browser, network or dependency installation. Run with Python3.
"""
from pathlib import Path
import json, hashlib
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/img/hero'
FONT='Inter,system-ui,sans-serif'
def text(x,y,s,size=22,cls='',anchor='start'):
 return f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'
def cinematic_hero(mobile=False):
 w,h=(1000,1000) if mobile else (1440,820)
 # Composed scene, not boxes: human at a bench, useful objects and an evolving memory overhead.
 person=(30,380) if mobile else (90,250)
 bench=(185,410,.92) if mobile else (480,240,1)
 network=(365,80) if mobile else (685,55)
 docs=(55,75) if mobile else (300,105)
 s=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="title desc"><title id="title">Your idea becomes something useful — and helps the next person</title><desc id="desc">A person brings an idea to an AI-assisted engineering workbench. Real examples and a MANUFACTURER GUIDE contribute source, edition, limits. A messy knowledge lattice organizes into a topic tree. Wireframe objects become an enclosure, bracket and thermal device, checked before making. Human-reviewed feedback returns to improve the next design. Original conceptual artwork, not a hardware simulation or automatic model training.</desc><defs><radialGradient id="space"><stop stop-color="#1d3c51"/><stop offset="1" stop-color="#08131f"/></radialGradient><linearGradient id="glass" x2="1" y2="1"><stop stop-color="#3d8897" stop-opacity=".45"/><stop offset="1" stop-color="#0d263c" stop-opacity=".8"/></linearGradient><linearGradient id="metal"><stop stop-color="#cae2e5"/><stop offset="1" stop-color="#477786"/></linearGradient><radialGradient id="idea"><stop stop-color="#fff3c7"/><stop offset=".3" stop-color="#ffc879"/><stop offset="1" stop-color="#d88c31" stop-opacity="0"/></radialGradient><filter id="glow"><feGaussianBlur stdDeviation="5"/></filter><pattern id="grid" width="70" height="70" patternUnits="userSpaceOnUse"><path d="M70 0H0V70" fill="none" stroke="#73b7bb" stroke-opacity=".1"/></pattern></defs><style>text{{font-family:Inter,system-ui,sans-serif;fill:#d8e9ee}}.flow{{stroke-dasharray:3 13;animation:current 6s linear infinite}}.draw{{stroke-dasharray:1400;animation:draw 14s ease-in-out infinite}}.solid{{animation:solid 14s ease-in-out infinite}}.lid{{animation:assemble 14s ease-in-out infinite}}.orb{{animation:breathe 5s ease-in-out infinite}}.still{{display:none}}@keyframes current{{to{{stroke-dashoffset:-192}}}}@keyframes draw{{0%,10%{{stroke-dashoffset:1400;opacity:.2}}48%,72%{{stroke-dashoffset:0;opacity:1}}95%,100%{{stroke-dashoffset:0;opacity:.25}}}}@keyframes solid{{0%,32%{{opacity:.12}}62%,100%{{opacity:1}}}}@keyframes assemble{{0%,25%{{transform:translateY(-85px)}}62%,82%{{transform:translateY(0)}}100%{{transform:translateY(-85px)}}}}@keyframes breathe{{0%,100%{{opacity:.5}}50%{{opacity:1}}}}@media(prefers-reduced-motion:reduce){{*{{animation:none!important}}.moving{{display:none}}.still{{display:inline}}.solid{{opacity:1}}.draw{{stroke-dashoffset:0;opacity:1}}}}</style><rect width="{w}" height="{h}" rx="30" fill="url(#space)"/><ellipse cx="{w*.58}" cy="{h*.74}" rx="{w*.45}" ry="{h*.28}" fill="#183345" opacity=".45"/><path d="M0 {h*.73}L{w} {h*.57}V{h}H0Z" fill="url(#grid)"/>'''
 # Quiet depth cues, not filler particles: a technical horizon and a returning feedback orbit.
 s+=f'<ellipse cx="{w*.58}" cy="{h*.68}" rx="{w*.42}" ry="{h*.23}" fill="none" stroke="#6de3d1" stroke-opacity=".12"/>'
 s+=f'<path class="flow" d="M{w-90} {h-210}C{w-40} {h-30} 130 {h+30} 125 {h-250}" fill="none" stroke="#edbd74" stroke-width="3"/>'
 s+=f'<path class="flow" d="M{person[0]+245} {person[1]+135}Q{w*.35} 90 {network[0]+180} {network[1]+30}" fill="none" stroke="#86dfd2" stroke-width="2" opacity=".5"/>'
 # Person silhouette, facing the object: warm face/light and a purposeful hand at the workbench.
 x,y=person
 s+=f'<g transform="translate({x} {y})"><ellipse cx="88" cy="385" rx="120" ry="24" fill="#020b14" opacity=".55"/><path d="M28 150Q80 112 125 152L160 300 38 320Z" fill="#24495a" stroke="#7197a4" stroke-width="2"/><path d="M45 305L15 402M125 302l38 99" stroke="#314e60" stroke-width="25" stroke-linecap="round"/><path d="M34 166L-5 247 45 285M115 160l72 62 70-40" fill="none" stroke="#648796" stroke-width="24" stroke-linecap="round"/><path d="M226 191l31-10" stroke="#ffd5a3" stroke-width="15" stroke-linecap="round"/><path d="M64 48Q120 20 130 70L122 110 102 136 66 124 50 82Z" fill="#d3a984"/><path d="M46 78Q30 22 83 17q54-12 55 53l-25-20-58 42Z" fill="#152433"/><path d="M70 120l-1 28 35 10 2-30" fill="#ad8067"/><circle cx="246" cy="135" r="52" fill="url(#idea)" class="orb"/><path d="M239 135v-13a10 10 0 1 1 14 0v13m-13 6h12m-9 6h6" fill="none" stroke="#ffe3ad" stroke-width="3"/></g>'
 # Evidence pages float behind the workbench. They are supporting resources, not the headline.
 x,y=docs
 s+=f'<g transform="translate({x} {y}) rotate(-10)"><rect width="130" height="170" rx="9" fill="#172f43" stroke="#809fae"/><path d="M20 30h70M20 48h90M20 66h75M20 120h84M20 137h60" stroke="#7aa3b4" stroke-width="3"/><path d="M22 86l26-12 30 14-28 13Z" fill="none" stroke="#83e0cb" stroke-width="2"/><text x="20" y="158" font-size="12">GUIDES + EXAMPLES</text></g>'
 # The lattice really changes geometry into a tree, with a useful static final counterpart.
 nx,ny=network
 messy=[(0,58),(90,0),(165,90),(245,20),(305,115),(90,165),(215,185),(350,30),(375,185)]
 tree=[(180,0),(80,65),(280,65),(20,140),(120,140),(230,140),(330,140),(280,215),(380,215)]
 edges=[(0,1),(0,2),(1,3),(1,4),(2,5),(2,6),(6,7),(6,8)]
 s+=f'<g transform="translate({nx} {ny})"><g class="moving">'
 for a,b in edges:
  ma,mb=messy[a],messy[b];ta,tb=tree[a],tree[b]
  initial=f'M{ma[0]} {ma[1]}L{mb[0]} {mb[1]}';final=f'M{ta[0]} {ta[1]}L{tb[0]} {tb[1]}'
  s+=f'<path d="{initial}" stroke="#77d4ce" stroke-width="2" opacity=".7"><animate attributeName="d" values="{initial};{initial};{final};{final};{initial}" keyTimes="0;.15;.5;.85;1" dur="14s" repeatCount="indefinite"/></path>'
 for j,(m,t) in enumerate(zip(messy,tree)):
  s+=f'<circle cx="{m[0]}" cy="{m[1]}" r="{7 if j else 12}" fill="{["#ffc879","#7fe6d2"][bool(j)]}" stroke="#c5fff1" stroke-width="1"><animate attributeName="cx" values="{m[0]};{m[0]};{t[0]};{t[0]};{m[0]}" keyTimes="0;.15;.5;.85;1" dur="14s" repeatCount="indefinite"/><animate attributeName="cy" values="{m[1]};{m[1]};{t[1]};{t[1]};{m[1]}" keyTimes="0;.15;.5;.85;1" dur="14s" repeatCount="indefinite"/></circle>'
 s+='</g><g class="still">'
 for a,b in edges:s+=f'<path d="M{tree[a][0]} {tree[a][1]}L{tree[b][0]} {tree[b][1]}" stroke="#79e5d0" stroke-width="2"/>'
 for a,b in tree:s+=f'<circle cx="{a}" cy="{b}" r="7" fill="#79e5d0"/>'
 s+='</g></g>'
 # A luminous bench. Source-like geometry stays visibly illustrative, never passed off as product CAD.
 bx,by,k=bench
 s+=f'<g transform="translate({bx} {by}) scale({k})"><ellipse cx="380" cy="330" rx="390" ry="105" fill="#6de5d0" opacity=".08" filter="url(#glow)"/><path d="M-20 325L540 215 825 355 230 500Z" fill="#142d3d" stroke="#698b9a" stroke-width="3"/><path d="M230 500v30L825 385v-30M230 530L-20 355v-30" fill="#0b1d2b" stroke="#34596d" stroke-width="2"/><path d="M70 395v180M700 420v130" stroke="#1b3548" stroke-width="28"/>'
 # Enclosure: real-looking isometric construction, with the board visibly revealed by the moving lid.
 s+='<g transform="translate(170 120)"><path d="M0 100L220 60 330 120 100 170Z" fill="#2a766c" stroke="#95d7be" stroke-width="2" class="solid"/><g stroke="#e3c77d" stroke-width="3"><path d="M70 105h65v30M170 90v30h60M130 143h80" fill="none"/></g><path d="M115 95l55-10 35 19-55 11Z" fill="#1c2d3a" stroke="#a1b9bd"/><path d="M0 100v105l100 70V170M100 275l230-50V120" fill="url(#glass)" stroke="#84d8dd" stroke-width="2" class="solid"/><g class="lid"><path d="M-8 91L220 42 340 108 100 166Z" fill="url(#metal)" opacity=".85" stroke="#b7eff1" stroke-width="2"/><path d="M32 94l190-40M49 106l190-40M66 118l190-40" stroke="#386b7b" stroke-width="3"/></g><path class="draw" d="M0 100L220 60 330 120 100 170 0 100V205L100 275 330 225V120M100 170v105M0 205l230-45" fill="none" stroke="#a1fff0" stroke-width="3"/></g>'
 # Two other useful objects: a mounting bracket and a compact finned thermal device.
 s+='<g transform="translate(535 165)" class="solid"><path d="M0 60L80 42 80-15 112-23V88L0 112Z" fill="url(#metal)" stroke="#c1e7ea" stroke-width="2"/><ellipse cx="32" cy="86" rx="9" ry="5" fill="#183b4d"/><ellipse cx="96" cy="12" rx="5" ry="9" fill="#183b4d"/></g><g transform="translate(70 290)" class="solid"><path d="M0 20L75 4 132 33 54 52Z" fill="#416b7b" stroke="#8ac8ce"/>'
 for j in range(7):s+=f'<path d="M{j*10} {18-j*2}v-46l55 29v46" fill="#6097a5" stroke="#abdedf" stroke-width="1"/>'
 s+='</g><path class="flow" d="M-10 330Q300 235 720 350" fill="none" stroke="#8cead5" stroke-width="2"/></g>'
 s+=f'<g transform="translate({w-240} {h-170})"><circle r="32" fill="#123a39" stroke="#80e9ce" stroke-width="2"/><path d="M-14 0l10 11 21-25" fill="none" stroke="#a5fbe0" stroke-width="5"/></g>'
 s+=text(42,h-40,'YOUR IDEA. USEFUL HARDWARE. A BETTER NEXT ROUND.',19 if mobile else 22,'')
 return s+'</svg>\n'

def trace_chart():
 source=ROOT/'tests/fixtures/cfd_runs/exhaust-under-opening/postProcessing/domain0/zone_heater/0/volFieldValue.dat'
 samples=[(float(line.split()[0]),float(line.split()[-1])-273.15) for line in source.read_text().splitlines() if line and not line.startswith('#')]
 pts=' '.join(f'{70+t/1500*620:.2f},{250-(v-30)/12*180:.2f}' for t,v in samples)
 style='<style>text{font-family:system-ui,sans-serif;fill:#eaf3f7}.line{stroke-dasharray:1600;animation:draw 10s ease-in-out infinite}@keyframes draw{0%{stroke-dashoffset:1600}75%,100%{stroke-dashoffset:0}}@media(prefers-reduced-motion:reduce){.line{animation:none}}</style>'
 s='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 390" width="760" height="390" role="img" aria-label="Recorded 20 watt box CFD heater-zone temperature over 1500 solver iterations">'+style+'<rect width="760" height="390" rx="20" fill="#102332"/>'+text(34,42,'THERMAL / RECORDED SOLVER TRACE',21)+text(34,75,'20 W box · heater-zone average, °C',19)
 for v in [30,34,38,42]:
  y=250-(v-30)/12*180;s+=f'<path d="M70 {y}H700" stroke="#385062"/>'+text(32,y+6,str(v),15)
 s+=f'<polyline class="line" points="{pts}" fill="none" stroke="#ffcb83" stroke-width="3"/>'+text(70,284,'0',16)+text(660,284,'1500',16)+text(350,313,'solver iterations — not seconds',18)+text(34,350,f'Final sample {samples[-1][1]:.2f} °C · simulation, not a measurement',19)
 return s+'</svg>\n',{'input':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'samples':len(samples),'final_c':samples[-1][1]}
def balance_chart():
 p=ROOT/'docs/img/cfd/SOURCE.json';d=json.loads(p.read_bytes());s='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 390" width="760" height="390" role="img" aria-label="Recorded airflow comparison retains the ducted case failed balance and steady criteria"><style>text{font-family:system-ui,sans-serif;fill:#edf4f8}.bar{transform-box:fill-box;transform-origin:left;animation:grow 9s ease-in-out infinite}@keyframes grow{0%{transform:scaleX(.03)}55%,100%{transform:scaleX(1)}}@media(prefers-reduced-motion:reduce){.bar{animation:none}}</style><rect width="760" height="390" rx="20" fill="#102332"/>'+text(32,42,'AIRFLOW / CHECK THE BALANCE',22)
 for j,(key,label) in enumerate([('exhaust-under-opening','Fan under opening'),('exhaust-ducted','Ducted fan')]):
  f=d['facts'][key];y=90+j*130;s+=text(32,y,label,22)+text(32,y+30,f"{f['mass_flow_g_s']:.2f} g/s · {f['heat_out_w']:.2f} W out / 20 W in",19)+f'<rect class="bar" x="32" y="{y+47}" width="{f["heat_out_w"]/20*640:.2f}" height="22" rx="5" fill="{["#79e5d0","#ffcb83"][j]}"/>'+text(32,y+96,f"Balance {f['energy_balance_pct']:+.1f}% · "+('steady, energy check passes' if f['steady'] else 'not steady; energy check fails'),18)
 s+=text(32,372,'Recorded OpenFOAM cases · not a tested cooling guarantee',18)
 return s+'</svg>\n',{'input':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'facts':d['facts']}
if __name__=='__main__':
 for mobile in [False,True]:(OUT/('learning-loop-mobile.svg' if mobile else 'learning-loop.svg')).write_text(cinematic_hero(mobile))
 records={}
 for name,fn in [('thermal-history',trace_chart),('airflow-balance',balance_chart)]:
  svg,record=fn();(OUT/(name+'.svg')).write_text(svg);records[name]=record
 (OUT/'learning-evidence.json').write_text(json.dumps({'illustration':'learning-loop variants are conceptual process artwork, not an engineering result','generated_by':'tools/site/figures/learning-home.py','figures':records},indent=2)+'\n')
