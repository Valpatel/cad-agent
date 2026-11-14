"""Real Chromium consumer tests for the portable SCADA package.

Only assets inside --root are served. The example uses its actual UtilityModel;
clock instrumentation observes real timers rather than replacing model behavior.
The separate lifecycle fixture also imports the public package and example API.
"""
import argparse
import json
import mimetypes
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path)
parser.add_argument('--entry', default='examples/viewer/index.html')
parser.add_argument('--url', default='https://scada-consumer.test')
parser.add_argument('--via-curl', action='store_true')
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('scada-viewer-browser'))
parser.add_argument('--widths', default='1440,900,390')
parser.add_argument('--chromium', default=shutil.which('chromium'))
args = parser.parse_args()
assert not (args.root and args.via_curl), 'Choose package-root assets or published curl delivery.'
ROOT = (args.root or UI).resolve() if not args.via_curl else None
ENTRY = args.entry.lstrip('/')
BASE = args.url.rstrip('/')
BASE_PARTS = urlparse(BASE)
PREFIX = BASE_PARTS.path.rstrip('/') + '/'
OUT = args.output
OUT.mkdir(parents=True, exist_ok=True)

CLOCK_PROBE = r"""(() => {
  const nativeSet = window.setInterval.bind(window), nativeClear = window.clearInterval.bind(window);
  const records = new Map();
  window.__consumerClock = {created:0, records, summary:() => ({
    created:window.__consumerClock.created,
    active:[...records.values()].filter(item=>item.active).length,
    ticks:[...records.values()].reduce((sum,item)=>sum+item.ticks,0),
    intervals:[...records.values()].map(({delay,active,ticks})=>({delay,active,ticks})),
    samples:[...records.values()].flatMap(record=>record.samples)
  })};
  window.setInterval = (callback, delay, ...args) => {
    const record={delay:Number(delay),active:true,ticks:0,samples:[]};
    const read=()=>{const text=document.querySelector('[data-demo-status]')?.textContent??'';return {minutes:Number(text.match(/^\d+/)?.[0]??0),running:text.includes('· Running ·'),hidden:document.hidden};};
    const id=nativeSet(typeof callback==='function' ? (...values)=>{record.ticks++;const before=read(),result=callback(...values),after=read();record.samples.push({...before,after:after.minutes});return result;} : callback,delay,...args);
    records.set(id,record); window.__consumerClock.created++; return id;
  };
  window.clearInterval = id => {if(records.has(id)) records.get(id).active=false;return nativeClear(id);};
})();"""

results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
    for width in map(int, args.widths.split(',')):
        height = 1000 if width > 500 else 844
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        errors, denied, loaded = [], [], set()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script(CLOCK_PROBE)

        def serve(route):
            parsed = urlparse(route.request.url)
            path = unquote(parsed.path)
            if parsed.netloc != BASE_PARTS.netloc or not path.startswith(PREFIX):
                denied.append(route.request.url)
                return route.abort('blockedbyclient')
            name = path[len(PREFIX):]
            # A package consumer may use examples, src and documentation only.
            if not name or any(part in ('..', 'dist', 'node_modules') for part in Path(name).parts):
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
            route.fulfill(status=200, body=data,
                          content_type='text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')

        page.route('**/*', serve)
        page.goto(BASE + '/' + ENTRY, wait_until='networkidle')
        editable, monitor = page.locator('#utility-viewer'), page.locator('#utility-monitor')
        editable.locator('[data-scada-picker]').wait_for(state='visible')
        status = page.locator('[data-demo-status]')
        if 'Running' in status.inner_text():
            page.locator('[data-demo-action=running]').click()
        assert 'Paused' in status.inner_text()
        assert editable.locator('[data-scada-viewer]').get_attribute('data-readonly') == 'false'
        assert monitor.locator('[data-scada-viewer]').get_attribute('data-readonly') == 'true'
        assert page.evaluate('__consumerClock.summary().created') == 1
        assert page.evaluate('__consumerClock.summary().active') == 1
        assert page.evaluate('document.documentElement.scrollWidth') == width

        def close():
            if page.locator('dialog[open]').count():
                page.keyboard.press('Escape')
            assert page.locator('dialog[open]').count() == 0

        def dialog_bounds(dialog):
            assert dialog.evaluate('el=>el.open && el.matches(":modal")')
            assert dialog.get_attribute('aria-modal') == 'true'
            box = dialog.bounding_box()
            assert box and box['x'] >= -1 and box['y'] >= -1, box
            assert box['x'] + box['width'] <= width + 1 and box['y'] + box['height'] <= height + 1, box
            assert dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
            assert page.evaluate('document.documentElement.scrollWidth') == width
            assert dialog.locator('[data-scada-close]').bounding_box()['height'] >= 43
            assert dialog.evaluate('el=>el.contains(document.activeElement)')

        def inspect(root, equipment):
            close()
            root.locator('[data-scada-picker]').select_option(equipment)
            dialog = root.locator('[data-scada-dialog=inspector]')
            dialog.wait_for(state='visible')
            dialog_bounds(dialog)
            return dialog

        def view(root, name):
            close()
            root.locator('[data-scada-view-choice=' + name + ']').click()
            assert root.locator('[data-scada-view-choice=' + name + ']').get_attribute('aria-current') == 'page'

        def flow(root, name):
            return root.locator('[data-scada-connection=' + name + ']').get_attribute('data-active') == 'true'

        def machine(root, name):
            return root.locator('[data-scada-equipment=' + name + '] .scada-component')

        def readings(dialog):
            return dialog.locator('.scada-viewer-readings').evaluate('el=>Object.fromEntries([...el.children].map(row=>[row.querySelector("dt").textContent,row.querySelector("dd").textContent]))')

        def photo(label, dialog=None):
            if dialog:
                dialog.locator('[data-scada-dialog-body]').evaluate('el=>el.scrollTop=0')
                dialog.screenshot(path=str(OUT / f'viewer-{label}-{width}.png'))
            else:
                page.evaluate('window.scrollTo({top:0,left:0,behavior:"instant"})')
                page.screenshot(path=str(OUT / f'viewer-{label}-{width}.png'), full_page=True)

        photo('two-viewers')
        expected_equipment = {'tank', 'pump', 'valve', 'meter', 'generator'}
        for root in (editable, monitor):
            assert set(root.locator('[data-scada-picker] option').evaluate_all('els=>els.map(el=>el.value)')) == expected_equipment
            for equipment in sorted(expected_equipment):
                dialog = inspect(root, equipment)
                assert dialog.locator('[data-scada-dialog-title]').inner_text().strip()
                if root == monitor:
                    assert all(dialog.locator('[data-scada-control]').nth(i).is_disabled() for i in range(dialog.locator('[data-scada-control]').count()))
                close()
                assert root.locator('[data-scada-picker]').evaluate('el=>el===document.activeElement')

        # Native keyboard focus stays within each open inspector and returns to its opener.
        dialog = inspect(editable, 'pump')
        dialog.locator('[data-scada-control=demand]').focus()
        page.keyboard.press('Tab')
        assert dialog.locator('[data-scada-close]').evaluate('el=>el===document.activeElement')
        page.keyboard.press('Shift+Tab')
        assert dialog.locator('[data-scada-control=demand]').evaluate('el=>el===document.activeElement')
        photo('pump-controls', dialog)
        close()
        editable.locator('[data-scada-inspect]').focus()
        page.keyboard.press('Enter')
        dialog_bounds(editable.locator('dialog[open]'))
        page.mouse.click(1, 1)
        assert not page.locator('dialog[open]').count()
        assert editable.locator('[data-scada-inspect]').evaluate('el=>el===document.activeElement')

        # Commands modify the host model, reflected by both viewers and views.
        for root in (editable, monitor):
            view(root, 'water')
            assert flow(root, 'pumpedWater')
        dialog = inspect(editable, 'pump')
        dialog.locator('[data-scada-control=pumpSwitch]').click()
        assert dialog.locator('[data-scada-control=pumpSwitch]').get_attribute('aria-pressed') == 'false'
        close()
        for root in (editable, monitor):
            assert not flow(root, 'pumpedWater')
            assert machine(root, 'pump').get_attribute('data-active') == 'false'
            view(root, 'power')
            assert not flow(root, 'pumpPower')
        readonly = inspect(monitor, 'pump')
        assert readonly.locator('[data-scada-control=pumpSwitch]').get_attribute('aria-pressed') == 'false'
        assert readonly.locator('[data-scada-control=pumpSwitch]').is_disabled()
        photo('readonly-pump', readonly)
        dialog = inspect(editable, 'pump')
        dialog.locator('[data-scada-control=pumpSwitch]').click()
        demand = dialog.locator('[data-scada-control=demand]')
        demand.press('End')
        assert demand.input_value() == '100'
        close()
        readonly = inspect(monitor, 'pump')
        assert readonly.locator('[data-scada-control=demand]').input_value() == '100'
        close()
        for root in (editable, monitor):
            view(root, 'water')
            meter = inspect(root, 'meter')
            assert readings(meter)['value'] == '70'
            close()
        dialog = inspect(editable, 'valve')
        dialog.locator('[data-scada-control=valveSwitch]').click()
        close()
        for root in (editable, monitor):
            assert not flow(root, 'deliveredWater')
            assert machine(root, 'pump').get_attribute('data-active') == 'true'
            assert machine(root, 'valve').get_attribute('data-open') == 'false'
        dialog = inspect(editable, 'valve')
        dialog.locator('[data-scada-control=valveSwitch]').click()
        close()
        for root in (editable, monitor):
            view(root, 'power')
        dialog = inspect(editable, 'generator')
        dialog.locator('[data-scada-control=breakGenerator]').click()
        assert readings(dialog)['fault'] == 'true'
        photo('generator-fault', dialog)
        close()
        for root in (editable, monitor):
            assert machine(root, 'generator').get_attribute('data-failed') == 'true'
            assert machine(root, 'pump').get_attribute('data-status') == 'offline'
            assert not flow(root, 'pumpPower')
        dialog = inspect(editable, 'generator')
        dialog.locator('[data-scada-control=repairGenerator]').click()
        close()
        for root in (editable, monitor):
            assert machine(root, 'generator').get_attribute('data-failed') == 'false'
            assert flow(root, 'pumpPower')

        # Zoom is local presentation state; neither it nor view changes adds model clocks.
        for root in (editable, monitor):
            root.locator('[data-scada-zoom=reset]').click()
            root.locator('[data-scada-zoom=in]').click()
            assert root.locator('[data-scada-zoom=reset]').inner_text() == '125%'
            assert root.locator('[data-scada-canvas]').evaluate('el=>getComputedStyle(el).transform').startswith('matrix(1.25')
            root.locator('[data-scada-zoom=fit]').click()
            assert root.locator('[data-scada-scroll]').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        photo('fit-power')
        assert page.evaluate('__consumerClock.summary().created') == 1
        paused_status = status.inner_text()
        page.wait_for_timeout(1150)
        assert status.inner_text() == paused_status
        before_minutes = int(re.match(r'\d+', paused_status).group())
        page.locator('[data-demo-action=step]').click()
        assert int(re.match(r'\d+', status.inner_text()).group()) == before_minutes + 1
        assert 'Paused' in status.inner_text()
        page.locator('[data-demo-action=running]').click()
        clock_before = page.evaluate(r'({minutes:Number(document.querySelector("[data-demo-status]").textContent.match(/^\d+/)[0]),ticks:__consumerClock.summary().ticks})')
        page.wait_for_function('ticks => __consumerClock.summary().ticks >= ticks + 2', arg=clock_before['ticks'])
        page.locator('[data-demo-action=running]').click()
        clock_after = page.evaluate(r'({minutes:Number(document.querySelector("[data-demo-status]").textContent.match(/^\d+/)[0]),ticks:__consumerClock.summary().ticks})')
        samples = page.evaluate('__consumerClock.summary().samples')[clock_before['ticks']:clock_after['ticks']]
        assert all(sample['after'] - sample['minutes'] == (1 if sample['running'] and not sample['hidden'] else 0) for sample in samples), samples
        assert clock_after['minutes'] - clock_before['minutes'] == sum(sample['after'] - sample['minutes'] for sample in samples)
        assert page.evaluate('__consumerClock.summary().active') == 1
        # Reset intentionally resumes the example. Pause its real control in the
        # same event turn so a valid timer tick cannot race this zero-time check.
        page.evaluate('''() => {
          document.querySelector('[data-demo-action=reset]').click();
          document.querySelector('[data-demo-action=running]').click();
        }''')
        assert status.inner_text().startswith('0 illustrative minutes · Paused · reservoir 62.0%')
        for root in (editable, monitor):
            assert machine(root, 'generator').get_attribute('data-failed') == 'false'
            assert flow(root, 'pumpPower')

        # Public lifecycle fixture: a third viewer, a real independent model, and
        # observable adapter accounting. Viewer destruction does not own its clock.
        page.evaluate('''async () => {
          const {ScadaViewer}=await import('../../src/viewer/viewer.mjs');
          const {UtilityModel}=await import('./utility-model.mjs');
          const {createUtilityAdapter}=await import('./utility-adapter.mjs');
          const definition=await fetch('./system.json').then(r=>r.json());
          const model=new UtilityModel(); model.dispatch({action:'set',arguments:{key:'running',value:false}}); model.start();
          const base=createUtilityAdapter(model), counts={subscriptions:0,dispatches:0,updates:0}, root=document.createElement('div');
          root.id='lifecycle-viewer'; document.querySelector('main').append(root);
          const state={model,counts,root,reject:false};
          const adapter={getSnapshot:base.getSnapshot,subscribe:listener=>{counts.subscriptions++;const off=base.subscribe(listener);return ()=>{counts.subscriptions--;off();};},dispatch:command=>{counts.dispatches++;if(state.reject)return Promise.reject(new Error('Host adapter rejected this command.'));return base.dispatch(command);}};
          state.viewer=new ScadaViewer({definition,adapter,scope:'lifecycle-fixture',hooks:{update:()=>counts.updates++}}).mount(root);
          window.__viewerFixture=state;
        }''')
        fixture = page.locator('#lifecycle-viewer')
        assert page.evaluate('__viewerFixture.counts.subscriptions') == 1
        dialog = inspect(fixture, 'pump')
        dialog.locator('[data-scada-control=pumpSwitch]').click()
        assert page.evaluate('__viewerFixture.model.getSnapshot().pumpOn') is False
        assert page.evaluate('__viewerFixture.counts.dispatches') == 1
        page.evaluate('__viewerFixture.reject=true')
        dialog.locator('[data-scada-control=pumpSwitch]').click()
        rejection = dialog.locator('[data-scada-viewer-dialog-error]')
        rejection.wait_for(state='visible')
        assert 'Host adapter rejected' in rejection.inner_text()
        dialog_bounds(dialog)
        assert page.evaluate('__viewerFixture.model.getSnapshot().pumpOn') is False
        photo('host-rejection', dialog)
        lifecycle = page.evaluate('''() => {
          const f=__viewerFixture,oldControl=f.root.querySelector('[data-scada-control=pumpSwitch]');
          const activeBefore=__consumerClock.summary().active;
          f.viewer.destroy();
          const html=f.root.innerHTML,dispatches=f.counts.dispatches,updates=f.counts.updates,minutes=f.model.getSnapshot().minutes;
          oldControl.click();
          f.model.dispatch({action:'step'});
          const result={subscriptions:f.counts.subscriptions,modalClosed:!f.root.querySelector('dialog[open]'),staleControlDetached:f.counts.dispatches===dispatches,domStopped:f.root.innerHTML===html,updatesStopped:f.counts.updates===updates,modelStillUsable:f.model.getSnapshot().minutes===minutes+1,externalClockRetained:__consumerClock.summary().active===activeBefore,viewerRootReleased:f.viewer.root===null};
          f.model.stop();f.root.remove();delete window.__viewerFixture;return result;
        }''')
        assert all(value for key, value in lifecycle.items() if key != 'subscriptions'), lifecycle
        # Subscription count is expected to be zero, unlike the boolean assertions.
        assert lifecycle['subscriptions'] == 0
        assert page.evaluate('__consumerClock.summary().active') == 1
        assert page.evaluate('document.documentElement.style.overflow') == ''
        assert not errors, errors
        assert not denied, denied
        assert 'src/viewer/viewer.mjs' in loaded and 'examples/viewer/utility-model.mjs' in loaded
        result = {'width': width, 'package_root': str(ROOT) if ROOT else BASE, 'loaded_assets': sorted(loaded),
                  'equipment_per_viewer': sorted(expected_equipment), 'shared_commands_and_flows': True,
                  'read_only_adapter': True, 'native_focus_escape_backdrop': True,
                  'single_model_clock': True, 'step_pause_reset': True, 'fit_zoom': True,
                  'host_rejection_inside_modal': True, 'lifecycle': lifecycle, 'errors': errors, 'denied_assets': denied}
        results.append(result)
        (OUT / 'scada-viewer-browser-results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)
        context.close()
    browser.close()
