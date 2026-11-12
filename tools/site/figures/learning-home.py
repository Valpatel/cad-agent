"""Original homepage SVG narrative and charts derived only from committed evidence.
No CAD, solver, browser, network or dependency installation. Run with Python3.
"""
from pathlib import Path
import json, hashlib, math, sys, re, argparse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/img/hero'
RESULT_OUT=OUT/'result-stills'
sys.path.insert(0, str(ROOT/'software'))
from cadagent.publish.anim.svg import REDUCED_MOTION
FONT='Inter,system-ui,sans-serif'
def text(x,y,s,size=22,cls='',anchor='start'):
 return f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'
from workshop_scene import render as cinematic_hero

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
def finished_still(svg):
    # Explicit image-consumer fallback: parent media emulation need not reach SVG image CSS.
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    root=ET.fromstring(svg)
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit('}',1)[-1] in {'animate','animateMotion','animateTransform'}:
                parent.remove(child)
    finished_rules=[]
    for existing in root.findall('{http://www.w3.org/2000/svg}style'):
        css=existing.text or ''
        # Promote each author's own finished reduced-motion pose into unconditional still CSS.
        for match in re.finditer(r'@media\s*\(prefers-reduced-motion\s*:\s*reduce\)',css):
            opening=css.index('{',match.end());depth=1;end=opening+1
            while depth and end<len(css):
                depth += (css[end]=='{')-(css[end]=='}');end+=1
            finished_rules.append(css[opening+1:end-1])
        while '@keyframes' in css:
            start=css.index('@keyframes'); opening=css.index('{',start); depth=1; end=opening+1
            while depth and end<len(css):
                depth += (css[end]=='{')-(css[end]=='}'); end+=1
            css=css[:start]+css[end:]
        existing.text=re.sub(r'\banimation(?:-[a-z-]+)?\s*:[^;}]*;?', '', css)
    style=ET.SubElement(root,'{http://www.w3.org/2000/svg}style')
    style.text=REDUCED_MOTION+'*{animation:none!important}.moving{display:none!important}.still{display:inline!important}.first-version{display:none!important}.revised-version,.solid{opacity:1!important}.draw{stroke-dashoffset:0!important;opacity:1!important}.lid{transform:none!important}.handoff{transform:translate(calc(var(--dx)*.5),calc(var(--dy)*.5))!important}'
    style.text+=''.join(finished_rules)
    return ET.tostring(root,encoding='unicode')+'\n'

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--hero',action='store_true',help='Explicitly regenerate hero art; coordinate with its owner first')
 args=parser.parse_args()
 for mobile in ([False,True] if args.hero else []):
  name='learning-loop-mobile' if mobile else 'learning-loop'
  svg=cinematic_hero(mobile)
  (OUT/(name+'.svg')).write_text(svg)
  (OUT/(name+'-still.svg')).write_text(finished_still(svg))
 records={}
 for name,fn in [('thermal-history',trace_chart),('airflow-balance',balance_chart)]:
  svg,record=fn();(OUT/(name+'.svg')).write_text(svg);records[name]=record
 sources=['docs/img/fea/mesh-convergence.svg']+[f'docs/img/motion/{n}.svg' for n in ['rib-in-counterbore','connector-window','hinge-sweep','module-insertion','search-front']]+['docs/img/hero/thermal-history.svg','docs/img/hero/airflow-balance.svg']
 records['result_stills']={}
 for source in sources:
  original=ROOT/source;name=original.stem+'-still.svg';(RESULT_OUT/name).write_text(finished_still(original.read_text()))
  records['result_stills'][name]={'input':source,'output':str((RESULT_OUT/name).relative_to(ROOT)),'sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'method':'Unconditional authored reduced-motion pose; animation declarations removed'}
 (OUT/'learning-evidence.json').write_text(json.dumps({'illustration':'learning-loop variants are conceptual process artwork, not an engineering result','generated_by':'tools/site/figures/learning-home.py','figures':records},indent=2)+'\n')
