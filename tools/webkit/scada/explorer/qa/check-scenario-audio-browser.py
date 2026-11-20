"""Measure opt-in Industry Lab audio through Chromium's real output graph.

The analyser observes real Web Audio samples; this is signal verification, not
subjective listening. Visibility changes are deterministic DOM lifecycle probes.
"""
import argparse
import sys
import json
import mimetypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scada_paths import REPO, UI, SIM, TOOLS
import shutil
import subprocess
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=REPO)
parser.add_argument('--entry', default='software/cadagent/webkit/scada/explorer/index.html')
parser.add_argument('--url', default='https://industry-audio.test')
parser.add_argument('--via-curl', action='store_true')
parser.add_argument('--widths', default='1440,900,390')
parser.add_argument('--scenarios', default='winery,hydroponics-nft', help='Comma-separated v1/v2 scenario IDs to exercise through the public Explorer UI.')
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('scenario-audio-browser'))
args = parser.parse_args()
root = args.root.resolve()
out = args.output
out.mkdir(parents=True, exist_ok=True)
base = args.url.rstrip('/')
base_parts = urlparse(base)
prefix = base_parts.path.rstrip('/') + '/'
sys.path.insert(0, str(TOOLS / 'explorer/qa'))
from audio_probe import INSTRUMENT as instrument

results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
    for scenario_id, width in [(scenario, int(width)) for scenario in args.scenarios.split(',') for width in args.widths.split(',')]:
        context = browser.new_context(viewport={'width': width, 'height': 1000 if width > 500 else 844})
        page = context.new_page()
        errors, missing, readings = [], [], {}
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script(instrument)

        def serve(route):
            parsed = urlparse(route.request.url)
            if parsed.netloc != base_parts.netloc or not parsed.path.startswith(prefix):
                missing.append(route.request.url)
                return route.abort('blockedbyclient')
            name = unquote(parsed.path[len(prefix):])
            if args.via_curl:
                data = subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--location', route.request.url], timeout=40)
            else:
                path = (root / name).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    missing.append(name)
                    return route.fulfill(status=404, body='Missing local asset')
                data = path.read_bytes()
            route.fulfill(status=200, body=data, content_type='text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')

        page.route('**/*', serve)
        page.goto(base + '/' + args.entry + '?scenario=' + scenario_id, wait_until='networkidle')
        page.locator('#lab-viewer [data-scada-picker]').wait_for(state='visible')

        def close():
            if page.locator('dialog[open]').count():
                page.keyboard.press('Escape')

        def tool(name):
            close()
            page.locator('[data-scada-open=' + name + ']').click()
            dialog = page.locator('[data-scada-dialog=' + name + ']')
            dialog.wait_for(state='visible')
            assert dialog.evaluate('element=>element.matches(":modal")')
            assert dialog.evaluate('element=>element.scrollWidth<=element.clientWidth+1')
            return dialog

        def running(value):
            close()
            current = page.locator('#industry-lab').get_attribute('data-running') == 'true'
            if current != value:
                page.locator('[data-action=running]').click()
            assert page.locator('#industry-lab').get_attribute('data-running') == str(value).lower()

        def sample(label, audible, delay=0, duration=700):
            if delay:
                page.wait_for_timeout(delay)
            result = page.evaluate('ms=>__audioQA.signal(ms)', duration)
            readings[label] = result
            if audible:
                assert result['maxRms'] > .00001, (label, result)
                assert result['maxPeak'] < .98, (label + ' clips', result)
            else:
                assert result['maxRms'] < .000001, (label, result)
            return result

        def save_session():
            tool('session')
            with page.expect_download() as pending:
                page.locator('[data-action=export]').click()
            return json.loads(Path(pending.value.path()).read_text())

        def restore_session(saved):
            tool('session')
            page.locator('[data-import-file]').set_input_files({'name': scenario_id + '-audio.json', 'mimeType': 'application/json', 'buffer': json.dumps(saved).encode()})
            page.wait_for_function("document.querySelector('[data-dialog-message=session]').textContent.includes('Saved session restored')")

        def photo(label):
            dialog = tool('sound')
            dialog.screenshot(path=str(out / f'scenario-sound-{scenario_id}-{label}-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth') == width

        running(False)
        initial_session = save_session()
        assert page.evaluate('__audioQA.snapshot().contexts') == 0
        tool('faults')
        page.locator('[data-fault]').first.click()
        assert page.evaluate('__audioQA.snapshot().contexts') == 0, 'Muted fault operation initialized audio'
        page.locator('[data-action=repair]').click()
        photo('off')
        assert page.locator('[data-action=sound-enabled]').get_attribute('aria-pressed') == 'false'
        running(True)
        tool('sound')
        page.locator('[data-action=sound-enabled]').click()
        page.wait_for_function('__audioQA.snapshot().contexts===1 && __audioQA.snapshot().states[0]==="running"')
        sample('machinery', True, delay=400)
        photo('enabled')
        running(False)
        sample('paused', False, delay=1500)
        running(True)
        sample('resumed', True, delay=350)

        # Browser interruptions require a fresh user gesture and must not
        # allocate a second synthesis graph or claim output is still active.
        tool('sound')
        page.evaluate('__audioQA.contexts[0].context.suspend()')
        sample('browser_suspended', False, duration=300)
        page.wait_for_function("document.querySelector('[data-action=sound-enabled]').textContent.includes('Resume')")
        page.locator('[data-action=sound-enabled]').click()
        sample('gesture_resumed', True, delay=350)
        assert page.evaluate('__audioQA.snapshot().contexts') == 1
        assert page.evaluate('__audioQA.snapshot().states') == ['running']

        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
        hidden_time = page.locator('[data-kpi=time]').inner_text()
        sample('hidden', False, delay=1500, duration=1300)
        assert page.locator('[data-kpi=time]').inner_text() == hidden_time
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
        sample('visible', True, delay=350)

        # Isolate alarms from the continuous machinery signal.
        tool('sound')
        page.locator('[data-sound-ambience]').select_option('off')
        sample('ambience_off', False, delay=1500)
        tool('faults')
        buttons = page.locator('[data-fault]')
        assert buttons.count() >= 2
        fault1, fault2 = buttons.nth(0).get_attribute('data-fault'), buttons.nth(1).get_attribute('data-fault')
        page.evaluate('() => { window.__alarmProbe=__audioQA.signal(1800); }')
        buttons.nth(0).click()
        measured = page.evaluate('window.__alarmProbe')
        readings['fault_alarm'] = measured
        assert measured['maxRms'] > .00001, {'signal': measured, 'errors': errors,
            'fault': page.locator('[data-dialog-message=faults]').inner_text(),
            'sound': page.locator('[data-dialog-message=sound]').inner_text(),
            'alarms': page.locator('[data-sound-alarms]').inner_text(),
            'running': page.locator('#industry-lab').get_attribute('data-running')}
        # Current conditions intentionally repeat, while event history never
        # creates a separate playback queue or another synthesis graph.
        repeated = sample('unacknowledged_condition_repeats', True, duration=7200)
        assert repeated['oscillatorStarts'] > measured['oscillatorStarts']
        photo('fault')
        assert page.locator('[data-sound-alarms]').inner_text().strip()
        ack = page.locator('[data-action=sound-ack]')
        assert not ack.is_disabled()
        ack.click()
        assert ack.is_disabled()
        acknowledged = sample('acknowledged', False, delay=1500)
        acknowledged_starts = acknowledged['oscillatorStarts']
        sample('acknowledged_across_repeat_period', False, duration=6500)
        assert page.evaluate('__audioQA.snapshot().oscillatorStarts') == acknowledged_starts
        # Hide/resume and mute/re-enable preserve acknowledgement and do not
        # replay the condition as a one-shot historical event.
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
        sample('acknowledged_hidden', False, duration=300)
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
        page.locator('[data-action=sound-enabled]').click()
        sample('acknowledged_muted', False, duration=300)
        page.locator('[data-action=sound-enabled]').click()
        sample('acknowledged_resume_no_replay', False, delay=350)
        assert page.evaluate('__audioQA.snapshot().oscillatorStarts') == acknowledged_starts
        assert 'Acknowledged' in page.locator('[data-sound-alarms]').inner_text()
        tool('faults')
        page.locator('[data-fault="' + fault2 + '"]').click()
        tool('sound')
        assert not page.locator('[data-action=sound-ack]').is_disabled()
        sample('new_condition_rearmed', True, duration=7200)
        page.locator('[data-action=sound-ack]').click()
        sample('reacknowledged', False, delay=1500)
        tool('faults')
        page.locator('[data-action=repair]').click()
        tool('sound')
        assert page.locator('[data-action=sound-ack]').is_disabled()
        running(False)
        historical = save_session()
        assert historical['state']['events'], 'Fixture must retain real fault/repair history'
        restore_session(historical)
        history_starts = page.evaluate('__audioQA.snapshot().oscillatorStarts')
        running(True)
        sample('restored_repaired_history_no_replay', False, delay=1500, duration=6500)
        assert page.evaluate('__audioQA.snapshot().oscillatorStarts') == history_starts

        # Replacing the scenario retains one opted-in graph and no old alarms.
        tool('scenarios')
        page.locator('[data-scenario=brewery]').click()
        page.wait_for_function("document.querySelector('[data-scenario-title]').textContent==='Brewery'")
        assert page.evaluate('__audioQA.snapshot().contexts') == 1
        tool('sound')
        assert page.locator('[data-action=sound-ack]').is_disabled()
        sample('scenario_reset_no_historical_alarm', False, delay=1500)
        page.locator('[data-sound-ambience]').select_option('on')
        sample('new_scenario_machinery', True, delay=350)
        page.locator('[data-action=sound-enabled]').click()
        sample('muted', False, delay=1500)
        page.reload(wait_until='networkidle')
        page.locator('#lab-viewer [data-scada-picker]').wait_for(state='visible')
        assert page.evaluate('__audioQA.snapshot().contexts') == 0
        tool('sound')
        assert page.locator('[data-action=sound-enabled]').get_attribute('aria-pressed') == 'false'
        assert not errors and not missing, (errors, missing)
        results.append({'scenario': scenario_id, 'version': initial_session['version'], 'width': width, 'readings': readings, 'alarm_conditions': [fault1, fault2], 'runtime_errors': errors, 'missing_assets': missing})
        (out / 'scenario-audio-browser-results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps({'scenario': scenario_id, 'version': initial_session['version'], 'width': width, 'signal_checks': len(readings), 'passed': True}), flush=True)
        context.close()
    browser.close()
