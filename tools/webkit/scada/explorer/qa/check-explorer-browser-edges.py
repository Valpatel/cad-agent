"""Independent Explorer deep-link, variant identity and filter persistence QA.

Loads real local package bytes at an HTTPS test origin. It neither imports the
model into the test process nor substitutes commands, clock or physics.
"""
import argparse
import hashlib
import json
import mimetypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scada_paths import REPO, UI, SIM, TOOLS
from urllib.parse import urlencode, unquote, urlparse
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=REPO)
parser.add_argument('--output',type=Path,default=REPO / '.cache/scada' / Path('release9-explorer/edges'))
parser.add_argument('--widths',default='1440,900,390')
args=parser.parse_args();root=args.root.resolve();out=args.output;out.mkdir(parents=True,exist_ok=True)
origin='https://scada-edge.test';entry='/software/cadagent/webkit/scada/explorer/index.html'
scenario_root=root/'software/cadagent/webkit/scada/sim/scenarios'
catalog=json.loads((scenario_root/'index.json').read_text())['scenarios']
types=sorted({kind for item in catalog for kind in item['componentTypes']})
variants=sorted({(item['type'],item['variant']) for scenario in catalog for item in scenario.get('componentVariants',[])})
representatives={'pump','plc-rack','pwr-reactor-vessel','reversible-pump-turbine','battery','nft-channel','water-quality-probe','power-inverter'}
results=[]
with sync_playwright() as runtime:
 browser=runtime.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in map(int,args.widths.split(',')):
  context=browser.new_context(viewport={'width':width,'height':1000 if width>500 else 844},accept_downloads=True)
  page=context.new_page();errors=[];denied=[];hashes={}
  page.on('pageerror',lambda error:errors.append(str(error)))
  def serve(route):
   parsed=urlparse(route.request.url);name=unquote(parsed.path).lstrip('/');target=(root/name).resolve()
   if parsed.netloc!='scada-edge.test' or not target.is_relative_to(root) or not target.is_file():
    denied.append(route.request.url);return route.abort('blockedbyclient')
   data=target.read_bytes();hashes.setdefault(name,set()).add(hashlib.sha256(data).hexdigest())
   route.fulfill(status=200,body=data,content_type='text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')
  page.route('**/*',serve)
  def navigate(query):
   page.goto(origin+entry+'?'+urlencode(query),wait_until='domcontentloaded')
   page.locator('#industry-lab[aria-busy=false]').wait_for()
   assert page.locator('[data-scenario-title]').inner_text()
   assert page.evaluate('document.documentElement.scrollWidth')==width
   assert not errors,errors
  def close():
   if page.locator('dialog[open]').count():page.locator('dialog[open] [data-scada-close]').click()
  def selected(expected,kind,variant=None):
   assert page.locator('[data-scenario-title]').inner_text()==expected['title']
   assert urlparse(page.url).query.find('scenario='+expected['id'])>=0
   inspector=page.locator('#lab-viewer dialog[open]');assert inspector.count()==1
   assert inspector.evaluate('el=>el.matches(":modal")&&el.contains(document.activeElement)')
   system=json.loads((scenario_root/expected['system']).read_text());model=json.loads((scenario_root/expected['model']).read_text())
   equipment_id=page.locator('[data-scada-picker]').input_value();equipment=next(item for item in system['components'] if item['id']==equipment_id)
   assert equipment['type']==kind,(kind,equipment)
   if variant is not None:assert equipment.get('variant',model['components'][equipment_id].get('variant'))==variant,(kind,variant,equipment_id)
   assert page.locator('[data-lab-message]').is_hidden(),page.locator('[data-lab-message]').inner_text()
   return equipment_id
  checks=[]
  for kind in types if width==1440 else [kind for kind in types if kind in representatives]:
   expected=next(item for item in catalog if kind in item['componentTypes']);navigate({'componentType':kind})
   checks.append({'type':kind,'scenario':expected['id'],'equipment':selected(expected,kind)})
  variant_checks=[]
  for kind,variant in variants if width==1440 else [pair for pair in variants if pair[0] in representatives]:
   expected=next(item for item in catalog if {'type':kind,'variant':variant} in item.get('componentVariants',[]));navigate({'componentType':kind,'variant':variant})
   variant_checks.append({'type':kind,'variant':variant,'scenario':expected['id'],'equipment':selected(expected,kind,variant)})
  # Real observer faults invalidate telemetry without disabling a healthy PLC.
  observer_checks=[]
  for kind in ('neutron-monitor','water-quality-probe'):
   expected=next(item for item in catalog if kind in item['componentTypes']);navigate({'componentType':kind});observer=page.locator('[data-scada-picker]').input_value();close()
   if page.locator('#industry-lab').get_attribute('data-running')=='true':page.locator('[data-action=running]').click()
   system=json.loads((scenario_root/expected['system']).read_text());plc=next(item['id'] for item in system['components'] if item['type']=='plc-rack')
   def node(equipment):
    view=next(view for view in system['views'] if any(item['component']==equipment for item in view['placements']))
    page.locator('[data-scada-view-choice="'+view['id']+'"]').click()
    return page.locator('[data-scada-equipment="'+equipment+'"] .scada-component')
   assert node(plc).get_attribute('data-active')=='true'
   # Drift remains a degraded, available observation. Exercise an actual
   # outage explicitly instead of depending on failure-mode display order.
   page.locator('[data-scada-open=faults]').click();faults=page.locator('[data-scada-dialog=faults]');faults.locator('[data-fault-equipment]').select_option(observer);faults.locator('[data-fault=disconnected]').click();close()
   assert node(plc).get_attribute('data-active')=='true'
   assert node(observer).get_attribute('data-active')=='false'
   page.locator('[data-scada-open=session]').click()
   with page.expect_download() as download:page.locator('[data-scada-dialog=session] [data-action=export]').click()
   saved=out/f'observer-{kind}-{width}.json';download.value.save_as(saved);state=json.loads(saved.read_text())['state'];close()
   assert state['components'][observer]['valid'] is False
   assert state['components'][observer]['faultMode']!='none'
   assert state['components'][plc]['enabled'] is True and state['components'][plc]['faultMode']=='none'
   observer_checks.append({'scenario':expected['id'],'observer':observer,'plc':plc,'invalid_telemetry_healthy_plc':True})
  # Explicit scenario wins; unsupported type/variant and removed scenarios explain fallback.
  explicit=catalog[0];navigate({'scenario':explicit['id'],'componentType':'pwr-reactor-vessel'})
  assert page.locator('[data-scenario-title]').inner_text()==explicit['title'];assert 'not present' in page.locator('[data-lab-message]').inner_text()
  navigate({'componentType':'pump','variant':'absent-fixture-variant'});assert 'not available' in page.locator('[data-lab-message]').inner_text();close()
  navigate({'scenario':'absent-fixture-scenario'});assert 'not found' in page.locator('[data-lab-message]').inner_text()
  # URL filters are applied on load, compose, and survive reload through real controls.
  target=next(item for item in catalog if item.get('technologies') and item.get('facility'))
  query={'q':target['id'],'sector':target['sector'],'technology':target['technologies'][0],'facility':target['facility']}
  navigate(query);page.locator('[data-scada-open=scenarios]').click();dialog=page.locator('[data-scada-dialog=scenarios]')
  assert dialog.locator('[data-scenario]').count()==1;assert dialog.locator('[data-scenario]').get_attribute('data-scenario')==target['id']
  assert dialog.locator('[data-scenario-search]').input_value()==target['id']
  dialog.locator('[data-action=clear-filters]').click();assert dialog.locator('[data-scenario]').count()==len(catalog)
  assert all(name+'=' not in urlparse(page.url).query for name in ('q','sector','technology','facility'))
  dialog.locator('[data-scenario-search]').fill('nuclear');assert 'q=nuclear' in page.url;close();page.reload(wait_until='domcontentloaded');page.locator('#industry-lab[aria-busy=false]').wait_for();page.locator('[data-scada-open=scenarios]').click()
  assert dialog.locator('[data-scenario-search]').input_value()=='nuclear';assert dialog.locator('[data-scenario]').count()>0
  dialog.screenshot(path=str(out/f'persisted-filter-{width}.png'))
  assert not errors and not denied,(errors,denied)
  results.append({'width':width,'type_deep_links':checks,'variant_deep_links':variant_checks,'fallback_messages':True,'observer_outages':observer_checks,'filter_url_roundtrip':True,'page_errors':errors,'denied_assets':denied,'asset_sha256':{name:sorted(values) for name,values in hashes.items()}})
  (out/'explorer-edge-results.json').write_text(json.dumps(results,indent=2));print(json.dumps({'width':width,'type_links':len(checks),'variant_links':len(variant_checks)}),flush=True)
  context.close()
 browser.close()
