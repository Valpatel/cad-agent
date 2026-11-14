"""Check targeted failure/repair animation semantics against canonical SCADA source.

Requires Python Playwright and Chromium. Writes evidence only to --output.
The host owns fault and repair transitions; this checks supplied visual states.
"""
import argparse,hashlib,json,mimetypes,shutil
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
from urllib.parse import unquote,urlparse
from playwright.sync_api import sync_playwright

FIXTURE='''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"><style>body{background:#081621;color:#def;font:14px system-ui}main{display:grid;grid-template-columns:repeat(5,240px);gap:12px}.card{padding:12px;background:#102635;border:1px solid #355665;border-radius:9px}h2{font-size:13px}</style><main></main><script type="module">import {renderScadaComponent} from '/index.mjs';window.draw=cases=>{document.querySelector('main').innerHTML=cases.map((c,i)=>`<article class="card" data-case="${i}"><h2>${c.type} · ${c.name}</h2>${renderScadaComponent(c.type,{id:'fault-'+i,state:c.state})}</article>`).join('')};window.ready=true;</script>'''
CONTROL_SELECTORS={'plc-rack':'.scada-scan','plc-cpu':'.scada-scan','remote-io':'.scada-traffic','hmi':'.scada-screen-pulse','scada-server':'.scada-scan','network-switch':'.scada-traffic','radio':'.scada-traffic'}
FAILURES=[*[{'type':t,'selector':s,'damage':'power-loss'} for t,s in CONTROL_SELECTORS.items()],{'type':'pressure-transmitter','selector':'.scada-sensor-pulse','damage':'broken'},{'type':'gas-analyzer','selector':'.scada-trace','damage':'broken'},{'type':'electrical-meter','selector':'.twin-art-charge-orbit','damage':'broken'},{'type':'cyclone','selector':'.scada-process-swirl','damage':'blocked'},{'type':'fuel-cell','selector':'.scada-process-cell','damage':'fuel-starved'},{'type':'aeroponic-chamber','selector':'.scada-agri-mist','damage':'nozzle-fault'},{'type':'current-transformer','selector':'.scada-power-signal','damage':'insulation-fault'},{'type':'voltage-transformer','selector':'.scada-power-signal','damage':'insulation-fault'}]
CASES=[]
for f in FAILURES:
 for name,damage in [('healthy','none'),('failure',f['damage']),('repaired','none')]:CASES.append({**f,'name':name,'state':{'damage':damage},'expectMoving':name!='failure'})
CASES += [{'type':'separator','name':'leak while stopped','selector':'.scada-damage-leak','state':{'active':False,'damage':'leaking'},'expectMoving':True},{'type':'pressurizer','name':'retained heat after fault','selector':'.scada-nuclear-residual','state':{'fault':True,'heat':55},'expectMoving':True}]
CASES += [{'type':'flow-meter','name':name,'selector':'.scada-flow','state':{'value':value},'expectMoving':value!=0} for name,value in [('forward flow',12),('zero flow',0),('reverse flow',-12)]]
CASES += [{'type':'biofilter','name':name,'selector':'.scada-agri-bubble','state':{'level':level},'expectMoving':level>0,'allowAbsent':level==0} for name,level in [('wet inventory',55),('empty inventory',0),('refilled inventory',55)]]
CASES += [{'type':'biofilter','name':'empty exterior flow','selector':'.scada-agri-flow','state':{'level':0},'expectMoving':True},{'type':'biofilter','name':'dry settled media','selector':'.scada-agri-media','state':{'level':0},'expectMoving':False}]
SAMPLE='''cases=>cases.map((c,i)=>{const root=document.querySelector(`[data-case="${i}"] .scada-component`),els=[...root.querySelectorAll(c.selector)];return {type:c.type,name:c.name,active:root.dataset.active,readingValid:root.dataset.readingValid??null,readings:[...root.querySelectorAll('[data-scada-reading]')].map(e=>e.textContent),animations:els.flatMap(e=>e.getAnimations().map(a=>{const s=getComputedStyle(e);return {name:a.animationName,time:a.currentTime,state:a.playState,direction:s.animationDirection,visibility:s.visibility,opacity:s.opacity}}))}})'''
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--static-root',type=Path,default=UI/'src');parser.add_argument('--output',type=Path,default=REPO / '.cache/scada' / Path('fault-semantics'));args=parser.parse_args();root=args.static_root.resolve();args.output.mkdir(parents=True,exist_ok=True);errors=[];hashes={}
 def serve(route):
  name=unquote(urlparse(route.request.url).path).lstrip('/')
  if not name:route.fulfill(body=FIXTURE,content_type='text/html');return
  path=(root/name).resolve()
  if not path.is_relative_to(root) or not path.is_file():errors.append('missing '+name);route.fulfill(status=404,body='missing');return
  body=path.read_bytes();hashes[name]=hashlib.sha256(body).hexdigest();route.fulfill(body=body,content_type='text/javascript' if path.suffix=='.mjs' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1300,'height':1000});page.route('**/*',serve);page.on('pageerror',lambda e:errors.append(str(e)));page.goto('https://fault-semantics.test/');page.wait_for_function('window.ready');page.evaluate('draw',CASES);page.wait_for_timeout(100);a=page.evaluate(SAMPLE,CASES);page.wait_for_timeout(250);b=page.evaluate(SAMPLE,CASES);rows=[]
  for c,x,y in zip(CASES,a,b):
   assert y['animations'] or c.get('allowAbsent'),(c,'no target animations; update selector to match actual equipment')
   moving=any(v['time']>u['time']+10 and v['visibility']!='hidden' for u,v in zip(x['animations'],y['animations']))
   assert moving==c['expectMoving'],(c,x,y)
   if c['type']=='flow-meter' and c['state']['value']!=0:assert all(a['direction']==('reverse' if c['state']['value']<0 else 'normal') for a in y['animations']),(c,y)
   rows.append({**c,**y,'moving':moving})
  # Every failure is still legible with motion disabled; no CSS clock runs.
  page.emulate_media(reduced_motion='reduce');assert page.locator('main').evaluate('e=>e.getAnimations({subtree:true}).length')==0
  page.evaluate('cases=>draw(cases.filter(c=>c.name===\'failure\'))',CASES);page.screenshot(path=str(args.output/'failure-cards.png'),full_page=True)
  (args.output/'report.json').write_text(json.dumps({'browser':browser.version,'cases':rows,'reducedMotionAnimations':0,'errors':errors,'servedHashes':hashes},indent=2)+'\n');browser.close()
 assert not errors,errors
 print(json.dumps({'cases':len(rows),'passed':True,'errors':errors}))
if __name__=='__main__':main()
