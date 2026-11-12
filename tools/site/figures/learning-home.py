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
def hero(mobile=False):
 w,h=(720,1590) if mobile else (1440,790)
 panels=[(28,150),(28,610),(28,1070)] if mobile else [(36,140),(512,140),(988,140)]
 pw,ph=(664,420) if mobile else (416,480)
 s=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="title desc"><title id="title">From shared evidence to better hardware</title><desc id="desc">Examples and manufacturer guides enter a messy knowledge graph, become organized topics and cited rules, then inform design, checks, simulation and printing. Results return through human-reviewed contributions. Conceptual process illustration, not a hardware simulation or automatic model training.</desc><defs><pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="#233549" stroke-width="1"/></pattern><linearGradient id="panel" x2="0.6" y2="1"><stop stop-color="#142439"/><stop offset="1" stop-color="#0b1625"/></linearGradient><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="none" stroke="#79e5d0"/></marker></defs><style>text{{font-family:{FONT};fill:#edf4f8}}.muted{{fill:#a9bbcd}}.cyan{{fill:#79e5d0}}.amber{{fill:#ffcb83}}.mono{{font-family:ui-monospace,monospace}}.wire{{fill:none;stroke:#79e5d0;stroke-width:2;stroke-dasharray:5 9;animation:flow 4s linear infinite}}.node{{fill:#0c2634;stroke:#79e5d0;stroke-width:2}}.pulse{{animation:pulse 6s ease-in-out infinite}}.trace{{fill:none;stroke:#79e5d0;stroke-width:3;stroke-dasharray:900;animation:trace 9s ease-in-out infinite}}@keyframes flow{{to{{stroke-dashoffset:-140}}}}@keyframes pulse{{0%,100%{{opacity:.35}}50%{{opacity:1}}}}@keyframes trace{{0%{{stroke-dashoffset:900}}55%,100%{{stroke-dashoffset:0}}}}@media(prefers-reduced-motion:reduce){{*{{animation:none!important}}.trace{{stroke-dashoffset:0}}.pulse{{opacity:1}}}}</style><rect width="100%" height="100%" rx="28" fill="#091422"/><rect width="100%" height="100%" rx="28" fill="url(#grid)" opacity=".6"/>'''
 s+=text(38,58,'YOUR NEED. SHARED KNOWLEDGE. BETTER HARDWARE.',22,'cyan mono')+text(38,100,'Anyone. Any useful thing.',32)
 labels=[('01','START WITH A NEED','Learn from examples and original guides.'),('02','ORGANIZE','Topics. Provenance. Cited rules.'),('03','BUILD + LEARN','Design → check → make → report.')]
 for i,((x,y),(n,label,sub)) in enumerate(zip(panels,labels)):
  s+=f'<g transform="translate({x} {y})"><rect width="{pw}" height="{ph}" rx="20" fill="url(#panel)" stroke="#314459"/>'+text(24,40,n,19,'amber mono')+text(68,40,label,23)+text(24,77,sub,20,'muted')
  if i==0:
   cw=220 if mobile else 250
   for k,(a,b,c) in enumerate([('YOUR NEED','A useful thing','A person sets the requirements'),('MANUFACTURER GUIDE','PEM · Covestro','Source, edition, limits')]):
    yy=108+k*142;s+=f'<g transform="translate(28 {yy})"><path d="M0 0H{cw-32}L{cw} 30V120H0Z" fill="#1e3046" stroke="#738ba4"/><path d="M{cw-32} 0V30H{cw}" fill="none" stroke="#738ba4"/>'+text(16,31,a,16,'cyan mono')+text(16,65,b,23)+text(16,93,c,14,'muted')+'</g>'
   s+=text(28,ph-24,'Real examples + checks guide the AI.',17,'muted')
   xx=360 if mobile else 338
   s+=f'<g transform="translate({xx-14} 110)"><circle cx="14" cy="0" r="13" fill="none" stroke="#edf4f8" stroke-width="3"/><path d="M-6 52V32q20-30 40 0v20M-6 35l-12 22M34 35l12 22" fill="none" stroke="#edf4f8" stroke-width="3"/></g>'
   for j in range(7):s+=f'<circle cx="{xx}" cy="{200+j*25}" r="{4+j%3}" fill="#ffcb83" class="pulse" style="animation-delay:{j*.4}s"/>'
   s+=f'<path class="wire" d="M{cw+36} 200H{pw-20}"/>'
  elif i==1:
   # Left: unstructured links. Right: a stable cited tree, not an evidence score.
   pts=[(32,145),(105,111),(174,166),(48,238),(144,265),(82,340),(201,332),(220,210)]
   for j,(a,b) in enumerate(pts):
    for k in [j+2,j+3]:
     c,d=pts[k%len(pts)];s+=f'<path d="M{a} {b}L{c} {d}" stroke="#62768e" stroke-width="1" opacity=".55"/>'
   for j,(a,b) in enumerate(pts):s+=f'<circle cx="{a}" cy="{b}" r="{5+j%3}" fill="#ffcb83" opacity=".8"/>'
   sx=330 if mobile else 290
   s+=f'<path class="trace" d="M{sx} 130V320M{sx} 180h-35v60M{sx} 180h45v60M{sx} 280h45v60"/>'
   for a,b in [(sx,130),(sx-35,240),(sx+45,240),(sx+45,340)]:s+=f'<rect class="node" x="{a-12}" y="{b-12}" width="24" height="24" rx="5"/>'
   if mobile:
    s+=text(415,150,'TOPIC TREE',21,'cyan')+text(415,210,'Source-linked',21)+text(415,245,'Material limits',21)+text(415,280,'Worked examples',21)+text(415,315,'Rule + test',21)
   else:s+=text(24,420,'Messy inputs → reusable knowledge',18,'muted')
  else:
   ox=32; yy=112
   for j,(label,detail) in enumerate([('DESIGN','real CAD'),('CHECK','fit + access'),('SIMULATE','stated assumptions'),('MAKE','reviewed release')]):
    px=ox+(j%2)*(300 if mobile else 190);py=yy+(j//2)*120
    s+=f'<g transform="translate({px} {py})"><rect width="{276 if mobile else 166}" height="96" rx="12" fill="#172d3e" stroke="#496479"/>'+text(14,34,label,20,'cyan mono')+text(14,65,detail,16,'muted')+'</g>'
   s+=text(26,395,'Useful objects. Honest feedback. Better next time.',16,'amber')
  s+='</g>'
 if mobile:
  for y in [580,1040]:s+=f'<path class="wire" d="M360 {y-6}v28" marker-end="url(#arrow)"/>'
  s+=text(360,1540,'Human-reviewed feedback → the next design',21,'cyan','middle')
 else:
  for x in [462,938]:s+=f'<path class="wire" d="M{x} 380h36" marker-end="url(#arrow)"/>'
  s+='<path class="wire" d="M1200 640v55H240v-55" marker-end="url(#arrow)"/>'+text(720,741,'RESULTS → HUMAN REVIEW → SHARED IMPROVEMENT',22,'cyan mono','middle')
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
 for mobile in [False,True]:(OUT/('learning-loop-mobile.svg' if mobile else 'learning-loop.svg')).write_text(hero(mobile))
 records={}
 for name,fn in [('thermal-history',trace_chart),('airflow-balance',balance_chart)]:
  svg,record=fn();(OUT/(name+'.svg')).write_text(svg);records[name]=record
 (OUT/'learning-evidence.json').write_text(json.dumps({'illustration':'learning-loop variants are conceptual process artwork, not an engineering result','generated_by':'tools/site/figures/learning-home.py','figures':records},indent=2)+'\n')
