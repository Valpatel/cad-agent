"""Browser regression for the standalone, manifest-driven Explorer.

Serves repository/package assets without the production app. Exercises real
native dialogs and downloads, and compares saved sessions for exact replay.
Timer and visibility probes observe the host clock without replacing physics.
"""
import argparse
import base64
import html
import hashlib
import json
import mimetypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scada_paths import REPO, UI, SIM, TOOLS
import shutil
import subprocess
from urllib.parse import unquote, urlencode, urlparse

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path)
parser.add_argument('--entry', default='software/cadagent/webkit/scada/explorer/index.html')
parser.add_argument('--url', default='https://scada-lab.test')
parser.add_argument('--via-curl', action='store_true')
parser.add_argument('--widths', default='1440,900,390')
parser.add_argument('--scenario-only', action='store_true', help='Run scenario checks while skipping the separately reported shared catalog/clock/deep-link suite.')
parser.add_argument('--resume', action='store_true', help='Reuse completed per-scenario checkpoints; always rerun global filter/clock/link assertions. Reports carried-forward evidence explicitly.')
parser.add_argument('--expect-scenarios', type=int, help='Assert candidate manifest scenario count.')
parser.add_argument('--expect-types', type=int, help='Assert candidate distinct component type count.')
parser.add_argument('--expect-views', type=int, help='Assert candidate total declared view count.')
parser.add_argument('--scenarios', help='Optional comma-separated focused subset; default checks all manifest entries.')
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('scenario-browser'))
parser.add_argument('--chromium', default=shutil.which('chromium'))
args = parser.parse_args()
assert not (args.root and args.via_curl), 'Choose local assets or published curl delivery.'
ROOT = (args.root or REPO).resolve() if not args.via_curl else None
BASE = args.url.rstrip('/')
PARTS = urlparse(BASE)
PREFIX = PARTS.path.rstrip('/') + '/'
ENTRY = args.entry.lstrip('/')
OUT = args.output
OUT.mkdir(parents=True, exist_ok=True)
PROBE = r"""(() => {
  const set=window.setInterval.bind(window), clear=window.clearInterval.bind(window), records=new Map();
  const minutes=()=>parseFloat(document.querySelector('[data-kpi=time]')?.textContent??'0');
  window.__labClock={created:0,summary:()=>({created:__labClock.created,active:[...records.values()].filter(r=>r.active).length,ticks:[...records.values()].reduce((sum,r)=>sum+r.ticks,0),samples:[...records.values()].flatMap(r=>r.samples)})};
  window.setInterval=(callback,delay,...args)=>{const record={active:true,ticks:0,samples:[]};const id=set(typeof callback==='function'?(...values)=>{record.ticks++;const before=minutes(),running=document.querySelector('#industry-lab')?.dataset.running==='true',hidden=document.hidden;const result=callback(...values);record.samples.push({before,after:minutes(),running,hidden});return result;}:callback,delay,...args);records.set(id,record);__labClock.created++;return id;};
  window.clearInterval=id=>{if(records.has(id))records.get(id).active=false;return clear(id);};
})();"""


def command_matches(snapshot, command):
    """Check observable exported state, without running a second model oracle."""
    arg = command.get('arguments', {})
    target, value = arg.get('equipment', command.get('component')), arg.get('value')
    action, version = command['action'], snapshot['version']
    config, state = snapshot['model'], snapshot['state']
    if action == 'setParameter':
        actual = config['components'][target]['parameters'][arg['key']]
    elif action == 'setCircuitParameter':
        actual = config['components'][target]['circuits'][arg['circuit']]['parameters'][arg['key']]
    elif action == 'setEnergyParameter':
        actual = config['components'][target]['energy'][arg['key']]
    elif action == 'setEnvironment':
        actual = config['environment'][arg['key']]
    elif action == 'setZoneValue':
        actual = state['zones'][arg['zone']][arg['key']]
    elif action == 'setMeasurement':
        actual = config['components'][target]['measurement']
    elif action == 'setTracer':
        circuit = state['circuits'][target][arg['circuit']]
        actual = circuit['tracers'][arg['key']] / circuit['amount'] * 100
    elif action == 'setLevel' and version == 2:
        circuit = arg.get('circuit', next(iter(config['components'][target]['circuits'])))
        actual = state['circuits'][target][circuit]['amount'] / config['components'][target]['circuits'][circuit]['parameters']['stockScale']
    elif action == 'setFault' and version == 2:
        actual = state['components'][target]['faultMode']
        if isinstance(value, bool):
            assert (actual != 'none') == value, (command, actual)
            return
    elif action == 'setFault' and isinstance(value, str):
        actual = state['components'][target]['mode']
    else:
        key = {'setEnabled': 'enabled', 'setOpen': 'open', 'setLoad': 'load', 'setFault': 'failed', 'setMode': 'mode', 'setRodPosition': 'rodPosition', 'setDamage': 'damage', 'setLevel': 'level'}[action]
        actual = state['components'][target][key]
    assert abs(actual - value) < 1e-9 if isinstance(value, (int, float)) and not isinstance(value, bool) else actual == value, (command, actual)


result_path = OUT / 'scenario-browser-results.json'
results = json.loads(result_path.read_text()) if args.resume and result_path.exists() else []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
    for width in map(int, args.widths.split(',')):
        height = 1000 if width > 500 else 844
        context = browser.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
        page = context.new_page()
        errors, denied, loaded, asset_hashes = [], [], set(), {}
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script(PROBE)

        def serve(route):
            parsed = urlparse(route.request.url)
            path = unquote(parsed.path)
            if parsed.netloc != PARTS.netloc or not path.startswith(PREFIX):
                denied.append(route.request.url)
                return route.abort('blockedbyclient')
            name = path[len(PREFIX):]
            if not name or '..' in Path(name).parts:
                denied.append(name)
                return route.abort('blockedbyclient')
            if ROOT:
                target = (ROOT / name).resolve()
                if not target.is_relative_to(ROOT) or not target.is_file():
                    denied.append(name)
                    return route.abort('blockedbyclient')
                data = target.read_bytes()
            else:
                data = subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--location', route.request.url], timeout=40)
            loaded.add(name)
            asset_hashes.setdefault(name, set()).add(hashlib.sha256(data).hexdigest())
            route.fulfill(status=200, body=data, content_type='text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')

        page.route('**/*', serve)
        page.goto(BASE + '/' + ENTRY, wait_until='networkidle')
        page.locator('#industry-lab[aria-busy=false]').wait_for()
        manifest = page.evaluate("async()=>fetch(new URL('../sim/scenarios/index.json',location.href)).then(r=>r.json())")
        catalog = manifest['scenarios']
        assert catalog and len({item['id'] for item in catalog}) == len(catalog), 'Manifest IDs must be unique.'
        manifest_counts = {'scenarios': len(catalog), 'types': len({kind for item in catalog for kind in item['componentTypes']}), 'views': sum(len(item['views']) for item in catalog)}
        for metric, expected in [('scenarios', args.expect_scenarios), ('types', args.expect_types), ('views', args.expect_views)]:
            if expected is not None:
                assert manifest_counts[metric] == expected, (metric, manifest_counts[metric], expected)
        chosen = [item for item in catalog if not args.scenarios or item['id'] in args.scenarios.split(',')]
        assert chosen, 'No matching scenarios selected.'
        if args.scenarios:
            assert {item['id'] for item in chosen} == set(args.scenarios.split(',')), 'Unknown requested scenario.'
        viewer = page.locator('#lab-viewer')
        lab = page.locator('#industry-lab')

        def close():
            if page.locator('dialog[open]').count():
                page.keyboard.press('Escape')
            assert not page.locator('dialog[open]').count()

        def bounds(dialog=None):
            assert page.evaluate('document.documentElement.scrollWidth') == width
            if dialog:
                assert dialog.evaluate('el=>el.open && el.matches(":modal")')
                box = dialog.bounding_box()
                assert box and box['x'] >= -1 and box['y'] >= -1, box
                assert box['x'] + box['width'] <= width + 1 and box['y'] + box['height'] <= height + 1, box
                assert dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                assert dialog.locator('[data-scada-dialog-body]').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                assert dialog.locator('[data-scada-close]').bounding_box()['height'] >= 43
                assert dialog.evaluate('el=>el.contains(document.activeElement)')

        def tool(name):
            close()
            page.locator('[data-scada-open=' + name + ']').click()
            dialog = page.locator('#lab-tools [data-scada-dialog=' + name + ']')
            dialog.wait_for(state='visible')
            bounds(dialog)
            return dialog

        def inspect(equipment):
            close()
            viewer.locator('[data-scada-picker]').select_option(equipment)
            dialog = viewer.locator('[data-scada-dialog=inspector]')
            dialog.wait_for(state='visible')
            bounds(dialog)
            return dialog

        def pause():
            close()
            if lab.get_attribute('data-running') == 'true':
                page.locator('[data-action=running]').click()
            assert lab.get_attribute('data-running') == 'false'

        def step(count=1):
            pause()
            for _ in range(count):
                page.locator('[data-action=step]').click()

        def minutes():
            return float(page.locator('[data-kpi=time]').inner_text().split()[0])

        def choose(entry):
            dialog = tool('scenarios')
            dialog.locator('[data-scenario-search]').fill('')
            dialog.locator('[data-action=clear-filters]').click()
            dialog.locator('[data-scenario=' + entry['id'] + ']').click()
            page.wait_for_function('(title)=>document.querySelector("#industry-lab").getAttribute("aria-busy")==="false"&&document.querySelector("[data-scenario-title]").textContent===title', arg=entry['title'])
            assert page.locator('dialog[open]').count() == 0
            pause()

        def select_view(name):
            close()
            viewer.locator('[data-scada-view-choice=' + name + ']').click()
            assert viewer.locator('[data-scada-view-choice=' + name + ']').get_attribute('aria-current') == 'page'

        def save(label, action='export'):
            dialog = tool('session')
            with page.expect_download() as download:
                dialog.locator('[data-action=' + action + ']').click()
            path = OUT / f'{current_id}-{label}-{width}.json'
            download.value.save_as(path)
            close()
            return path, json.loads(path.read_text())

        def restore(path):
            dialog = tool('session')
            page.evaluate('''() => {
              window.__importObserved=false;
              const node=document.querySelector('[data-dialog-message=session]');
              const observer=new MutationObserver(()=>{if(node.textContent.includes('Saved session restored')){window.__importObserved=true;observer.disconnect();}});
              observer.observe(node,{childList:true,subtree:true,characterData:true});
            }''')
            dialog.locator('[data-import-file]').set_input_files(path)
            page.wait_for_function('window.__importObserved===true')
            assert dialog.locator('[data-import-file]').input_value() == ''
            close()

        def reset():
            dialog = tool('session')
            dialog.locator('[data-action=reset]').click()
            assert 'Edited parameters are preserved' in dialog.locator('[data-dialog-message=session]').inner_text()
            close()
            pause()
            assert minutes() == 0

        facet_checks = {}
        if not args.scenario_only:
            # Catalog filtering and native modal keyboard boundaries are real user interactions.
            pause()
            chooser = tool('scenarios')
            assert chooser.locator('[data-scenario]').count() == len(catalog)
            chooser.locator('[data-scenario-search]').fill('fortune')
            assert chooser.locator('[data-scenario]').count() == 1
            assert chooser.locator('[data-scenario]').get_attribute('data-scenario') == 'fortune-cookies'
            chooser.locator('[data-scenario-search]').fill('no-such-process-zz')
            assert chooser.locator('[data-scenario]').count() == 0
            chooser.locator('[data-scenario-search]').fill('')
            sector = catalog[0]['sector']
            chooser.locator('[data-scenario-sector]').select_option(sector)
            assert chooser.locator('[data-scenario]').count() == sum(item['sector'] == sector for item in catalog)
            chooser.locator('[data-scenario-sector]').select_option('')
            assert all(isinstance(item.get('facility', ''), str) for item in catalog), 'Facility facet must be a string.'
            facet_checks = {}
            for facet, field in [('technology', 'technologies'), ('facility', 'facility')]:
                values = sorted({value for item in catalog for value in (item.get(field, []) if facet == 'technology' else [item.get(field)]) if value})
                if facet == 'facility' and values:
                    chooser.locator('.lab-filter-details > summary').click()
                for value in values:
                    chooser.locator('[data-scenario-' + facet + ']').select_option(value)
                    expected_ids = {item['id'] for item in catalog if (value in item.get(field, []) if facet == 'technology' else item.get(field) == value)}
                    assert set(chooser.locator('[data-scenario]').evaluate_all('els=>els.map(el=>el.dataset.scenario)')) == expected_ids
                chooser.locator('[data-scenario-' + facet + ']').select_option('')
                facet_checks[facet] = len(values)
            if chooser.locator('.lab-filter-details[open]').count():
                chooser.locator('.lab-filter-details > summary').click()
            chooser.locator('[data-scenario]').last.focus()
            page.keyboard.press('Tab')
            assert chooser.locator('[data-scada-close]').evaluate('el=>el===document.activeElement')
            page.keyboard.press('Shift+Tab')
            assert chooser.locator('[data-scenario]').last.evaluate('el=>el===document.activeElement')
            chooser.locator('[data-scada-dialog-body]').evaluate('el=>el.scrollTop=0')
            chooser.screenshot(path=str(OUT / f'scenario-chooser-{width}.png'))
            close()
            assert page.locator('[data-scada-open=scenarios]').evaluate('el=>el===document.activeElement')
        checks = []
        progress_path = OUT / f'progress-{width}.json'
        previous = json.loads(progress_path.read_text()) if args.resume and progress_path.exists() else {}
        if previous:
            assert previous['manifest_counts'] == manifest_counts, 'Cannot resume a different manifest scope.'
        completed = {check['id']:check for check in previous.get('scenarios', [])}
        for entry in chosen:
            current_id = entry['id']
            if current_id in completed:
                check = completed[current_id]
                assert check['layouts'] == [view['id'] for view in entry['views']]
                assert all((OUT / f'{current_id}-{view["id"]}-{width}.png').exists() for view in entry['views'])
                checks.append({**check, 'resumed_evidence': True})
                print(json.dumps({'width':width,'scenario':current_id,'resumed':True}),flush=True)
                continue
            choose(entry)
            definitions = page.evaluate('''async entry => {
              const root=new URL('../sim/scenarios/',location.href);
              const system=await fetch(new URL(entry.system,root)).then(r=>r.json()),model=await fetch(new URL(entry.model,root)).then(r=>r.json());
              const {getModelDescriptor}=await import(new URL('../sim/src/index.mjs',location.href));
              return {system,model,descriptors:Object.fromEntries(system.components.map(item=>[item.id,getModelDescriptor(item.type,{version:model.version,variant:model.components[item.id].variant??item.variant})]))};
            }''', entry)
            system = definitions['system']
            assert set(viewer.locator('[data-scada-picker] option').evaluate_all('els=>els.map(el=>el.value)')) == {item['id'] for item in system['components']}
            assert [view['id'] for view in system['views']] == [view['id'] for view in entry['views']]
            start = minutes()
            step()
            assert minutes() == start + 1
            assert all('NaN' not in page.locator('[data-kpi=' + key + ']').inner_text() for key in ('time', 'active', 'flow', 'health'))
            layouts, route_obstacles = [], []
            for view in system['views']:
                select_view(view['id'])
                viewer.locator('[data-scada-zoom=fit]').click()
                bounds()
                nodes = viewer.locator('[data-scada-equipment]')
                assert set(nodes.evaluate_all('els=>els.map(el=>el.dataset.scadaEquipment)')) == {item['component'] for item in view['placements']}
                bad = nodes.evaluate_all('''els=>els.flatMap(el=>{
                  const box=el.getBoundingClientRect(),canvas=el.closest('[data-scada-canvas]').getBoundingClientRect(),label=el.querySelector('.scada-viewer-equipment-label');
                  return box.x<canvas.x-1||box.y<canvas.y-1||box.right>canvas.right+1||box.bottom>canvas.bottom+1||label.scrollHeight>label.clientHeight+1?[el.dataset.scadaEquipment]:[];
                })''')
                viewer.screenshot(path=str(OUT / f'{current_id}-{view["id"]}-{width}.png'))
                assert not bad, (current_id, view['id'], bad)
                overlap = nodes.evaluate_all('''els=>els.flatMap((a,i)=>els.slice(i+1).flatMap(b=>{const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();return Math.min(x.right,y.right)-Math.max(x.left,y.left)>2&&Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top)>2?[[a.dataset.scadaEquipment,b.dataset.scadaEquipment]]:[]}))''')
                assert not overlap, (current_id, view['id'], 'equipment overlaps', overlap)
                obstacles = viewer.evaluate("""(root,edges)=>{
                  const nodes=[...root.querySelectorAll('[data-scada-equipment]')].map(node=>({id:node.dataset.scadaEquipment,box:node.getBoundingClientRect()})),found=[];
                  for(const path of root.querySelectorAll('.scada-diagram-pipe')){
                    const id=path.closest('[data-scada-connection]').dataset.scadaConnection,edge=edges.find(edge=>edge.id===id),matrix=path.getScreenCTM(),length=path.getTotalLength();
                    for(const node of nodes){
                      if(node.id===edge?.from.component||node.id===edge?.to.component)continue;
                      for(let lengthAt=0;lengthAt<=length;lengthAt+=4){const p=path.getPointAtLength(lengthAt).matrixTransform(matrix),b=node.box;if(p.x>b.left+3&&p.x<b.right-3&&p.y>b.top+3&&p.y<b.bottom-3){found.push({edge:id,equipment:node.id});break;}}
                    }
                  }return found;
                }""", system['connections'])
                route_obstacles.extend({'view': view['id'], **obstacle} for obstacle in obstacles)
                layouts.append(view['id'])
            occurrences = {item['id']: sum(any(node['component'] == item['id'] for node in view['placements']) for view in system['views']) for item in system['components']}
            control = next(item for item in system['controls'] if item['kind'] == 'toggle' and item.get('binding', '').endswith('/enabled') and occurrences[item['component']] > 1)
            target = control['component']
            dialog = inspect(target)
            switch = dialog.locator('[data-scada-control="' + control['id'] + '"]')
            assert switch.get_attribute('aria-pressed') == 'true'
            switch.click()
            assert switch.get_attribute('aria-pressed') == 'false'
            for view in system['views']:
                select_view(view['id'])
                node = viewer.locator('[data-scada-equipment=' + target + '] .scada-component')
                if node.count():
                    assert node.get_attribute('data-active') == 'false'
                dialog = inspect(target)
                assert dialog.locator('[data-scada-control="' + control['id'] + '"]').get_attribute('aria-pressed') == 'false'
            dialog.locator('[data-scada-control="' + control['id'] + '"]').click()
            close()
            deep = width == 1440 or current_id in ('winery', 'fortune-cookies', 'pharma-oral-liquid', 'hydroponics-nft', 'aquaponics-dwc', 'power-nuclear-pwr', 'power-pumped-storage')
            extended_commands, equipment_commands = [], []
            if deep:
                for binding, kind, action in [('/load','range','setLoad'), ('/open','toggle','setOpen')]:
                    control_choice = next((item for item in system['controls'] if item['kind'] == kind and item.get('binding', '').endswith(binding)), None)
                    if not control_choice:
                        continue
                    panel = inspect(control_choice['component'])
                    field = panel.locator('[data-scada-control="' + control_choice['id'] + '"]')
                    if kind == 'range':
                        field.focus()
                        field.press('Home')
                        field.press('ArrowRight')
                        value = float(field.input_value())
                    else:
                        value = field.get_attribute('aria-pressed') != 'true'
                        field.click()
                    equipment_commands.append({'action':action,'arguments':{'equipment':control_choice['component'],'value':value}})
                _, commanded = save('equipment-commands')
                for equipment_command in equipment_commands:
                    command_matches(commanded, equipment_command)
                reset()
                faults = tool('faults')
                faults.locator('[data-fault-equipment]').select_option(target)
                first_fault = faults.locator('[data-fault]').first
                mode = first_fault.get_attribute('data-fault')
                first_fault.click()
                assert first_fault.get_attribute('aria-pressed') == 'true'
                _, broken = save('broken')
                if broken['version'] == 1:
                    assert broken['state']['components'][target]['failed'] is True
                    assert broken['state']['components'][target]['mode'] == mode
                else:
                    assert broken['state']['components'][target]['faultMode'] == mode
                faults = tool('faults')
                faults.locator('[data-fault-equipment]').select_option(target)
                faults.locator('[data-action=repair]').click()
                _, repaired = save('repaired')
                assert (repaired['state']['components'][target]['failed'] is False if repaired['version'] == 1 else repaired['state']['components'][target]['faultMode'] == 'none')
                assert repaired['state']['components'][target]['enabled'] is True
                model = tool('model')
                model.locator('[data-model-equipment]').select_option(target)
                field = model.locator('[data-parameter]').first
                key, initial = field.get_attribute('data-parameter'), float(field.input_value())
                low, high = float(field.get_attribute('min')), float(field.get_attribute('max'))
                edited = initial + min(1, (high - initial) / 2) if initial < high else initial - min(1, (initial - low) / 2)
                assert edited != initial
                field.fill(str(edited))
                apply = model.locator('[data-apply-parameters]')
                assert apply.is_visible()
                assert apply.bounding_box()['y'] + apply.bounding_box()['height'] <= height + 1
                apply.click()
                assert 'Parameter edits applied' in model.locator('[data-dialog-message=model]').inner_text()
                model.screenshot(path=str(OUT / f'{current_id}-model-{width}.png'))
                reset()
                _, changed = save('edited-reset')
                assert changed['model']['components'][target]['parameters'][key] == edited
                model = tool('model')
                model.locator('[data-model-equipment]').select_option(target)
                assert float(model.locator('[data-parameter=' + key + ']').input_value()) == edited
                model.locator('[data-action=parameter-defaults]').click()
                assert float(model.locator('[data-parameter=' + key + ']').input_value()) == initial
                close()
                if definitions['model']['version'] == 2:
                    config = definitions['model']['components']

                    def editor(equipment):
                        dialog = tool('model')
                        dialog.locator('[data-model-equipment]').select_option(equipment)
                        return dialog

                    def reveal(field):
                        # Open real disclosure widgets in outer-to-inner order.
                        for detail in field.locator('xpath=ancestor::details[not(@open)]').all():
                            detail.locator(':scope > summary').click()

                    def different(field):
                        initial = float(field.input_value())
                        low, high = float(field.get_attribute('min')), float(field.get_attribute('max'))
                        value = initial + min(1, (high-initial)/2) if initial < high else initial - min(1, (initial-low)/2)
                        assert value != initial
                        return value

                    for equipment, item in config.items():
                        if item.get('energy', {}).get('modes'):
                            panel = editor(equipment)
                            field = panel.locator('[data-editor-mode]')
                            reveal(field)
                            modes = list(item['energy']['modes'])
                            chosen_mode = next(mode for mode in modes if mode != field.input_value())
                            field.select_option(chosen_mode)
                            extended_commands.append({'action':'setMode','arguments':{'equipment':equipment,'value':chosen_mode}})
                        if 'rodPosition' in definitions['descriptors'][equipment].get('visualFields', {}):
                            panel = editor(equipment)
                            field = panel.locator('[data-editor-rods]')
                            if field.count():
                                reveal(field)
                                field.fill('37')
                                field.press('Tab')
                                extended_commands.append({'action':'setRodPosition','arguments':{'equipment':equipment,'value':37}})
                    circuit_equipment = max(config, key=lambda item: (len(config[item].get('circuits', {})), sum(circuit['amount'] for circuit in changed['state']['circuits'][item].values())))
                    for circuit in config[circuit_equipment].get('circuits', {}):
                        panel = editor(circuit_equipment)
                        select = panel.locator('[data-editor-circuit]')
                        reveal(select)
                        select.select_option(circuit)
                        for kind, action in [('circuit','setCircuitParameter'), ('tracer','setTracer')]:
                            if kind == 'tracer' and changed['state']['circuits'][circuit_equipment][circuit]['amount'] <= 0:
                                continue
                            form = panel.locator('[data-model-editor-form=' + kind + ']')
                            field = form.locator('[data-editor-field]').first
                            reveal(field)
                            value, key = different(field), field.get_attribute('data-editor-field')
                            field.fill(str(value))
                            form.locator('[type=submit]').click()
                            extended_commands.append({'action':action,'arguments':{'equipment':circuit_equipment,'circuit':circuit,'key':key,'value':value}})
                    energy_equipment = next((item for item in config if config[item].get('energy')), None)
                    groups = [('energy',energy_equipment,'setEnergyParameter'), ('zone',target,'setZoneValue'), ('environment',target,'setEnvironment')]
                    for kind, equipment, action in groups:
                        if equipment is None:
                            continue
                        panel = editor(equipment)
                        form = panel.locator('[data-model-editor-form=' + kind + ']')
                        if not form.count():
                            continue
                        field = form.locator('[data-editor-field]').first
                        reveal(field)
                        value, key = different(field), field.get_attribute('data-editor-field')
                        arguments = {'key':key,'value':value}
                        if kind == 'energy':
                            arguments['equipment'] = equipment
                        if kind == 'zone':
                            arguments['zone'] = panel.locator('[data-editor-zone]').input_value()
                        field.fill(str(value))
                        form.locator('[type=submit]').click()
                        extended_commands.append({'action':action,'arguments':arguments})
                    measurement_equipment = next((item for item in config if config[item].get('measurement')), None)
                    if measurement_equipment:
                        panel = editor(measurement_equipment)
                        field = panel.locator('[data-editor-measurement]')
                        reveal(field)
                        choices = field.locator('option').evaluate_all('els=>els.map(el=>el.value)')
                        value = next(value for value in choices if value != field.input_value())
                        field.select_option(value)
                        extended_commands.append({'action':'setMeasurement','arguments':{'equipment':measurement_equipment,'value':value}})
                    _, edited_extended = save('extended-edits')
                    for edited_command in extended_commands:
                        command_matches(edited_extended, edited_command)
                    reset()

                for experiment in entry['experiments']:
                    faults = tool('faults')
                    assert faults.locator('[data-experiment]').count() == len(entry['experiments'])
                    faults.locator('[data-experiment=' + experiment['id'] + ']').click()
                    _, experiment_state = save('experiment-' + experiment['id'])
                    for command in experiment['commands']:
                        command_matches(experiment_state, command)
                    reset()
                # An actual download/upload restores RNG, commands, parameters,
                # elapsed time and event sequence, so future steps match exactly.
                step(2)
                saved_path, saved = save('saved')
                step(2)
                _, continued = save('continued')
                for repeat in range(2):
                    restore(saved_path)
                    _, restored = save('restored-' + str(repeat))
                    assert restored == saved, (current_id, 'session restoration differs')
                step(2)
                _, replayed = save('replayed')
                assert replayed == continued, (current_id, 'continuation differs')
                _, system_export = save('system', 'system-json')
                assert system_export == system
                _, model_export = save('model', 'model-json')
                assert model_export == replayed['model']
            assert page.evaluate('__labClock.summary().created') == 1
            assert page.evaluate('__labClock.summary().active') == 1
            assert not errors, errors
            checks.append({'id': current_id, 'layouts': layouts, 'shared_equipment': target, 'pause_step': True, 'shared_command': True, 'deep_fault_parameter_replay': deep, 'equipment_commands': equipment_commands, 'extended_commands': extended_commands, 'route_obstacles': route_obstacles})
            (OUT / f'progress-{width}.json').write_text(json.dumps({'width':width,'manifest_counts':manifest_counts,'scenarios':checks,'errors':errors,'denied_assets':denied,'asset_sha256':{name:sorted(values) for name,values in asset_hashes.items()}},indent=2))
            print(json.dumps({'width': width, 'scenario': current_id, 'layouts': len(layouts), 'deep': deep}), flush=True)

        clock_samples, deep_links = [], []
        if not args.scenario_only:
            # One host-owned timer advances by selected speed; hidden tabs do not step.
            pause()
            before = minutes()
            page.wait_for_timeout(1100)
            assert minutes() == before
            page.locator('[data-speed]').select_option('4')
            page.locator('[data-action=running]').click()
            clock_before = page.evaluate('__labClock.summary().samples.length')
            page.wait_for_function('index=>__labClock.summary().samples.slice(index).filter(sample=>sample.running&&!sample.hidden).length>=2', arg=clock_before)
            page.locator('[data-action=running]').click()
            clock_samples = page.evaluate('index=>__labClock.summary().samples.slice(index)', clock_before)
            active_samples = [sample for sample in clock_samples if sample['running'] and not sample['hidden']]
            assert len(active_samples) >= 2
            assert all(sample['after'] == sample['before'] + 4 for sample in active_samples), active_samples
            assert all(sample['after'] == sample['before'] for sample in clock_samples if not sample['running'] or sample['hidden']), clock_samples
            page.locator('[data-action=running]').click()
            page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
            hidden_minutes = minutes()
            page.wait_for_timeout(1150)
            assert minutes() == hidden_minutes
            assert page.locator('[data-session-state]').inner_text() == 'Clock suspended'
            page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
            pause()
            assert page.evaluate('__labClock.summary().created') == 1

            # Old/new machinery and PLC deep links resolve to an industry containing
            # that type; an explicit scenario remains authoritative.
            deep_links = []
            for kind in ('pump', 'tablet-press', 'plc-rack', 'pwr-reactor-vessel', 'hydro-turbine', 'battery', 'nft-channel', 'water-quality-probe'):
                if not any(kind in entry['componentTypes'] for entry in catalog):
                    continue
                expected = next(item for item in catalog if kind in item['componentTypes'])
                page.goto(BASE + '/' + ENTRY + '?' + urlencode({'componentType': kind}), wait_until='networkidle')
                page.locator('#industry-lab[aria-busy=false]').wait_for()
                assert page.locator('[data-scenario-title]').inner_text() == expected['title']
                assert page.locator('#lab-viewer dialog[open]').count() == 1
                selected_id = viewer.locator('[data-scada-picker]').input_value()
                types = page.evaluate("async()=>fetch(new URL('../sim/scenarios/'+new URL(location.href).searchParams.get('scenario')+'/system.json',location.href)).then(r=>r.json()).then(s=>Object.fromEntries(s.components.map(c=>[c.id,c.type])))")
                assert types[selected_id] == kind
                bounds(viewer.locator('dialog[open]'))
                close()
                deep_links.append(kind)
            explicit = catalog[-1]
            page.goto(BASE + '/' + ENTRY + '?' + urlencode({'scenario': explicit['id'], 'componentType': 'pump'}), wait_until='networkidle')
            page.locator('#industry-lab[aria-busy=false]').wait_for()
            assert page.locator('[data-scenario-title]').inner_text() == explicit['title']
            close()
            bounds()
            assert not errors, errors
            assert not denied, denied
        result = {'width': width, 'manifest_counts': manifest_counts, 'scenarios': checks, 'catalog_filters': not args.scenario_only, 'facet_checks': facet_checks, 'clock_speed_pause_hidden': not args.scenario_only, 'clock_samples': clock_samples,
                  'deep_links': deep_links, 'explicit_scenario_wins': not args.scenario_only, 'loaded_assets': sorted(loaded), 'asset_sha256': {name: sorted(values) for name,values in asset_hashes.items()},
                  'errors': errors, 'denied_assets': denied}
        results = [previous for previous in results if previous['width'] != width] + [result]
        results.sort(key=lambda item:item['width'],reverse=True)
        result_path.write_text(json.dumps(results, indent=2))
        # Browser-rendered contact sheets preserve screenshots as source images;
        # no application assets or test interactions are altered to create them.
        captures = [(entry, view) for entry in chosen for view in entry['views']]
        for start in range(0, len(captures), 6):
            sheet = browser.new_page(viewport={'width': 1600, 'height': 1000})
            cards = []
            for entry, view in captures[start:start + 6]:
                encoded = base64.b64encode((OUT / f'{entry["id"]}-{view["id"]}-{width}.png').read_bytes()).decode()
                cards.append(f'<figure><figcaption>{html.escape(entry["title"])} · {html.escape(view["label"])} · {width}px</figcaption><img src="data:image/png;base64,{encoded}"></figure>')
            sheet.set_content('<html><style>body{margin:0;padding:18px;background:#07111d;color:#e8f6ff;font:18px system-ui}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}figure{margin:0}figcaption{padding:8px}img{display:block;width:100%;height:auto}</style><main>' + ''.join(cards) + '</main></html>')
            sheet.screenshot(path=str(OUT / f'contact-{width}-{start // 6 + 1}.png'), full_page=True)
            sheet.close()
        context.close()
    browser.close()
