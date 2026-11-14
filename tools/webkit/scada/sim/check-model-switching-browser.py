#!/usr/bin/env python3
"""Exercise the real equation bench through Chromium; no fake model or patched UI.

Requires Python Playwright and Chromium. The default serves the checkout's sibling
packages on an ephemeral local port. --url selects an already served source,
extracted kit or deployed entry; the receipt records that distinction.
"""
import argparse
from contextlib import contextmanager
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import subprocess
import tempfile
import threading
from urllib.parse import urljoin, urlsplit
from playwright.sync_api import sync_playwright
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=REPO, help='Cad-agent repository root containing the owned SCADA libraries.')
parser.add_argument('--url', help='Existing complete model-switching entry URL; skips the local server.')
parser.add_argument('--via-curl', action='store_true', help='Fetch actual same-origin HTTPS responses with curl using inherited proxy and CA trust, then fulfill them to Chromium; requires HTTPS --url.')
parser.add_argument('--output', type=Path, help='Evidence directory; defaults to root/work/model-switching-browser.')
parser.add_argument('--chromium', default='/usr/bin/chromium', help='Chromium executable path.')
parser.add_argument('--sizes', default='1280x800,1440x1000,1024x768,844x390,768x1024,390x844', help='Comma-separated WIDTHxHEIGHT viewports; the first is the main interaction size.')
parser.add_argument('--timeout-ms', type=int, default=15000)
args = parser.parse_args()
if args.via_curl:
    try:
        parsed_entry = urlsplit(args.url or '')
        valid_entry = parsed_entry.scheme == 'https' and parsed_entry.hostname and not parsed_entry.username and not parsed_entry.password
        parsed_entry.port
    except ValueError:
        valid_entry = False
    if not valid_entry:
        parser.error('--via-curl requires an absolute HTTPS --url without credentials.')
ROOT = args.root.resolve()
OUT = (args.output or ROOT / '.cache/scada/model-switching-browser').resolve()
OUT.mkdir(parents=True, exist_ok=True)
try:
    sizes = [tuple(map(int, size.split('x'))) for size in args.sizes.split(',')]
    if not sizes or any((len(size) != 2 or min(size) < 300 for size in sizes)):
        raise ValueError()
except ValueError:
    parser.error('--sizes must contain WIDTHxHEIGHT entries with both dimensions >= 300.')
if args.timeout_ms < 1000:
    parser.error('--timeout-ms must be at least 1000.')

served_sha256, missing, curl_cache = {}, [], {}
delivery_label = ('actual same-origin HTTPS bytes fetched by curl with inherited TLS/proxy trust and fulfilled to Chromium'
                  if args.via_curl else 'direct browser requests to the supplied entry URL' if args.url
                  else 'canonical local packages served by this command')


def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected an HTTPS URL without credentials.')
    return parsed.scheme, parsed.hostname.lower(), parsed.port or 443


def curl_response(url, expected_origin):
    """Follow only explicit same-origin HTTPS redirects; curl validates TLS normally."""
    current = url
    for _attempt in range(6):
        if origin(current) != expected_origin:
            raise ValueError('Blocked a request or redirect outside the entry origin.')
        with tempfile.TemporaryDirectory(prefix='scada-bench-curl-') as directory:
            body_path = Path(directory) / 'body'
            header_path = Path(directory) / 'headers'
            result = subprocess.run([
                'curl', '--silent', '--show-error', '--max-time', '30', '--proto', '=https',
                '--output', str(body_path), '--dump-header', str(header_path),
                '--write-out', '%{http_code}\n%{content_type}', current,
            ], capture_output=True, timeout=35, check=True)
            metadata = result.stdout.decode('utf-8', errors='replace').split('\n', 1)
            status = int(metadata[0])
            content_type = metadata[1].strip() if len(metadata) > 1 else ''
            headers = header_path.read_text(errors='replace').splitlines()
            body = body_path.read_bytes()
        if status in (301, 302, 303, 307, 308):
            locations = [line.split(':', 1)[1].strip() for line in headers if line.lower().startswith('location:')]
            if not locations:
                raise ValueError('Redirect response has no Location header.')
            current = urljoin(current, locations[-1])
            continue
        if not 200 <= status < 300:
            raise ValueError(f'HTTPS response returned status {status}.')
        if not content_type:
            path = urlsplit(current).path
            content_type = 'text/javascript' if path.endswith('.mjs') else mimetypes.guess_type(path)[0] or 'application/octet-stream'
        return body, content_type, status
    raise ValueError('Too many same-origin HTTPS redirects.')


def install_transport(context, entry_url):
    if not args.via_curl:
        return
    expected_origin = origin(entry_url)

    def serve(route):
        url = route.request.url
        try:
            if route.request.method != 'GET' or origin(url) != expected_origin:
                raise ValueError('Only same-origin HTTPS GET responses are allowed.')
            if url not in curl_cache:
                curl_cache[url] = curl_response(url, expected_origin)
            body, content_type, status = curl_cache[url]
            served_sha256[url] = hashlib.sha256(body).hexdigest()
            route.fulfill(status=status, body=body, content_type=content_type)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            reason = str(error)
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                reason = error.stderr.decode('utf-8', errors='replace').strip()
            missing.append({'url': url, 'reason': reason})
            (OUT / 'transport-failure.json').write_text(json.dumps({'delivery': delivery_label, 'missing': missing, 'served_sha256': served_sha256}, indent=2) + '\n')
            route.fulfill(status=502, body='Verified HTTPS delivery unavailable')

    context.route('**/*', serve)

class QuietHandler(SimpleHTTPRequestHandler):

    def log_message(self, *_args):
        pass

@contextmanager
def delivery(root, url):
    if url:
        yield url
        return
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root / 'software/cadagent/webkit/scada')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/sim/examples/model-switching/'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
checks = []

def check(name, value, detail=None):
    if not value:
        (OUT / 'failure.json').write_text(json.dumps({'failed': name, 'detail': detail, 'completed': checks}, indent=2) + '\n')
        raise AssertionError(f'{name}: {detail}')
    checks.append({'name': name, 'pass': True, 'detail': detail})
with delivery(ROOT, args.url) as URL, sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': sizes[0][0], 'height': sizes[0][1]}, device_scale_factor=1, accept_downloads=True)
    install_transport(page.context, URL)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_default_timeout(args.timeout_ms)
    page.goto(URL)
    page.wait_for_function('Boolean(window.equationBench)')
    snap = lambda: page.evaluate('equationBench.model.exportSnapshot()')
    metric = lambda: page.evaluate('(()=>{const m=equationBench.metrics();return {flow:m.flowM3s,power:m.electricalPowerW,potential:m.potential.flowM3s,state:m.state,minutes:m.snapshot.minutes,provider:m.selected.id}})()')
    check('one host owns clock', page.evaluate('!equationBench.model.clockStarted && !equationBench.model.getSnapshot().running'))
    a = metric()
    page.locator('#step').click()
    before = snap()
    page.locator('#provider').select_option('engineering.pump.linear')
    b = metric()
    after = snap()
    check('live swap changes real accepted flow and power', abs(a['flow'] - b['flow']) > 1e-05 and abs(a['power'] - b['power']) > 1, {'quadratic': a, 'linear': b})
    check('swap keeps time and core inventories', before['state']['minutes'] == after['state']['minutes'] and before['state']['circuits'] == after['state']['circuits'])
    check('swap initializes provider state', b['state']['elapsedS'] == 0)
    page.locator('#parameters').click()
    page.locator('[name="motorEfficiency"]').fill('0.65')
    page.locator('#parameter-form button[type=submit]').click()
    c = metric()
    check('edited efficiency affects actual core power', c['power'] > b['power'] and abs(c['flow'] - b['flow']) < 1e-08, {'beforeW': b['power'], 'afterW': c['power']})
    page.locator('#parameters').click()
    before = snap()
    page.locator('[name="pumpEfficiency"]').fill('0')
    page.locator('#parameter-form button[type=submit]').click()
    check('invalid parameter rejected atomically', bool(page.locator('#parameter-error').inner_text()) and before == snap())
    page.keyboard.press('Escape')
    check('parameter dialog restores focus', page.evaluate('document.activeElement.id==="parameters"'))
    page.locator('[data-scada-equipment="pump"]').click()
    page.locator('[data-scada-control="pumpLoad"]').evaluate("e=>{e.value='85';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}")
    page.keyboard.press('Escape')
    page.locator('#step').click()
    check('shaft state evolves through real provider', metric()['state']['speedRatio'] > 0.6)
    before = snap()
    page.locator('[data-scada-view-choice="drive"]').click()
    check('views share exact session state', before == snap())
    page.screenshot(path=str(OUT / 'drive.png'))
    page.locator('[data-scada-equipment="power"]').click()
    page.locator('[data-scada-control="powerEnable"]').click()
    page.keyboard.press('Escape')
    check('explicit supply loss gates real power and flow', metric()['power'] == 0 and metric()['flow'] == 0)
    page.locator('[data-scada-equipment="power"]').click()
    page.locator('[data-scada-control="powerEnable"]').click()
    page.keyboard.press('Escape')
    check('supply restoration recovers allocation', metric()['power'] > 0 and metric()['flow'] > 0)
    page.locator('[data-scada-view-choice="hydraulics"]').click()
    page.locator('[data-scada-equipment="valve"]').click()
    page.locator('[data-scada-control="valveOpen"]').click()
    page.keyboard.press('Escape')
    check('closed valve limits allocated pump outlet', metric()['flow'] == 0 and metric()['potential'] > 0)
    page.locator('[data-scada-equipment="valve"]').click()
    page.locator('[data-scada-control="valveOpen"]').click()
    page.keyboard.press('Escape')
    page.locator('[data-scada-equipment="pump"]').click()
    page.locator('[data-scada-control="pumpsetFault"]').click()
    page.keyboard.press('Escape')
    check('fault injection updates shared state', page.evaluate('equationBench.model.getSnapshot().controls.pump.fault'))
    page.screenshot(path=str(OUT / 'fault.png'))
    page.locator('[data-scada-equipment="pump"]').click()
    page.locator('[data-scada-control="pumprepair"]').click()
    page.keyboard.press('Escape')
    check('repair restores shared healthy state', not page.evaluate('equationBench.model.getSnapshot().controls.pump.fault'))
    page.locator('#rate').select_option('1')
    t = metric()['minutes']
    page.locator('#run').click()
    page.wait_for_timeout(1100)
    page.locator('#run').click()
    delta = (metric()['minutes'] - t) * 60
    check('single run clock advances expected simulated seconds', 0.5 < delta < 2, delta)
    saved = page.evaluate('equationBench.saveData()')
    with page.expect_download() as download:
        page.locator('#save').click()
    dl = download.value
    dl.save_as(str(OUT / 'saved-session.json'))
    check('file export contains provider identity', json.loads((OUT / 'saved-session.json').read_text())['session']['equationState']['components']['pump']['id'] == 'engineering.pump.linear')
    page.locator('#provider').select_option('engineering.pump.quadratic')
    page.locator('#step').click()
    page.locator('#session-file').set_input_files(str(OUT / 'saved-session.json'))
    page.wait_for_timeout(100)
    restored = snap()
    check('file restore reinstates law, parameters, time and provider state', restored['model'] == saved['session']['model'] and restored['equationState'] == saved['session']['equationState'] and (restored['state']['minutes'] == saved['session']['state']['minutes']))
    check('restored session opens paused', not page.evaluate('equationBench.model.getSnapshot().running'))
    before = snap()
    invalid = json.loads(json.dumps(saved))
    invalid['session']['equationState']['components']['pump']['stateVersion'] = 999
    (OUT / 'invalid-session.json').write_text(json.dumps(invalid))
    page.locator('#session-file').set_input_files(str(OUT / 'invalid-session.json'))
    page.wait_for_timeout(100)
    check('invalid provider state import rejects without mutation', before == snap() and 'rejected' in page.locator('#status').inner_text().lower())
    replay = page.evaluate('(()=>{const model=equationBench.model, s=model.exportSnapshot();model.step(.1);const expected=JSON.stringify(model.exportSnapshot());model.importSnapshot(s);model.step(.1);return expected===JSON.stringify(model.exportSnapshot())})()')
    check('core provider snapshot deterministically replays', replay)
    page.locator('[data-scada-zoom="in"]').click()
    z = page.evaluate('equationBench.viewer.zoom')
    vp = page.locator('.scada-diagram-scroll')
    box = vp.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.wheel(0, -300)
    page.wait_for_timeout(100)
    check('wheel zoom changes contained camera', page.evaluate('equationBench.viewer.zoom') > z)
    page.locator('[data-scada-camera-fit]').click()
    check('pinned fit remains usable', page.locator('[data-scada-camera-fit]').is_visible())
    check('canvas has no native scroll navigation', vp.evaluate("e=>getComputedStyle(e).overflowX==='clip'&&getComputedStyle(e).overflowY==='clip'&&e.scrollLeft===0&&e.scrollTop===0"))
    page.locator('#reset').click()
    check('reset retains selected law and parameters', metric()['provider'] == 'engineering.pump.linear' and snap()['model']['equations']['components']['pump']['parameters']['motorEfficiency'] == 0.65 and (metric()['minutes'] == 0))
    page.screenshot(path=str(OUT / 'desktop.png'))
    for w, h in sizes:
        page.set_viewport_size({'width': w, 'height': h})
        page.wait_for_timeout(100)
        page.locator('[data-scada-camera-fit]').click()
        check(f'no horizontal page overflow {w}x{h}', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        check(f'canvas scrollbar-free {w}x{h}', page.locator('.scada-diagram-scroll').evaluate('e=>e.scrollLeft===0&&e.scrollTop===0&&getComputedStyle(e).overflowX==="clip"'))
        page.screenshot(path=str(OUT / f'viewport-{w}x{h}.png'), full_page=True)
    page.emulate_media(reduced_motion='reduce')
    page.locator('#run').click()
    page.wait_for_timeout(100)
    check('reduced motion stops component and pipe animations', page.evaluate('document.querySelector("#viewer").getAnimations({subtree:true}).filter(a=>a.playState==="running").length===0'))
    page.locator('#run').click()
    check('no browser runtime errors', not errors, errors)
    check('no missing or rejected HTTPS responses', not missing, missing)
    receipt = {'browser': browser.version, 'url': URL, 'delivery': delivery_label, 'checks': checks, 'errors': errors, 'missing': missing, 'served_sha256': served_sha256, 'local_reference_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'software/cadagent/webkit/scada/sim/examples/model-switching').glob('*') if p.is_file()}}
    (OUT / 'browser-review.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': len(checks), 'errors': errors}))
    browser.close()
checks = []
with delivery(ROOT, args.url) as URL, sync_playwright() as p:
    b = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
    page = b.new_page(viewport={'width': sizes[0][0], 'height': sizes[0][1]})
    install_transport(page.context, URL)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_default_timeout(args.timeout_ms)
    page.goto(URL)
    page.wait_for_function('Boolean(window.equationBench)')
    page.locator('#rate').select_option('1')
    page.locator('#run').click()
    before = page.evaluate('equationBench.model.getSnapshot().minutes')
    page.locator('#provider').select_option('engineering.pump.linear')
    page.wait_for_timeout(300)
    check('swap during a running session keeps the live clock', page.evaluate('equationBench.model.getSnapshot().running && equationBench.model.getSnapshot().minutes') > before)
    page.locator('#parameters').click()
    field = page.locator('[name="motorEfficiency"]')
    field.fill('.7')
    page.wait_for_timeout(300)
    check('live snapshots preserve parameter draft and input focus', field.input_value() == '.7' and field.evaluate('e=>e===document.activeElement'))
    page.locator('#parameter-form button[type="submit"]').click()
    check('live parameter apply keeps running', page.evaluate('equationBench.model.getSnapshot().running'))
    card = page.locator('[data-scada-equipment="pump"]')
    img1 = card.screenshot()
    page.wait_for_timeout(300)
    img2 = card.screenshot()
    check('running pump visibly changes across rendered frames', img1 != img2)
    page.locator('#run').click()
    page.wait_for_timeout(100)
    animation1 = page.evaluate('document.querySelector("#viewer").getAnimations({subtree:true}).map(a=>a.currentTime)')
    page.wait_for_timeout(250)
    animation2 = page.evaluate('document.querySelector("#viewer").getAnimations({subtree:true}).map(a=>a.currentTime)')
    check('pause freezes viewer animation time', animation1 == animation2)
    vp = page.locator('.scada-diagram-scroll')
    vp.focus()
    state1 = page.evaluate('equationBench.viewer.camera.state')
    page.keyboard.press('ArrowLeft')
    state2 = page.evaluate('equationBench.viewer.camera.state')
    check('keyboard pans camera', state1['x'] != state2['x'])
    page.keyboard.press('Home')
    check('Home fits camera', page.evaluate('equationBench.viewer.camera.state.fitted'))
    box = vp.bounding_box()
    page.mouse.move(box['x'] + 100, box['y'] + 100)
    page.mouse.down()
    page.mouse.move(box['x'] + 170, box['y'] + 140, steps=5)
    page.mouse.up()
    check('mouse drag pans without opening equipment modal', not page.evaluate('equationBench.viewer.camera.state.fitted') and page.locator('dialog[open]').count() == 0)
    page.locator('#parameters').click()
    page.keyboard.press('Tab')
    check('native dialog contains keyboard focus', page.evaluate('document.activeElement.closest("dialog")?.open===true'))
    page.keyboard.press('Escape')
    check('Escape returns focus to opener', page.evaluate('document.activeElement.id==="parameters"'))
    mobile = b.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    install_transport(mobile, URL)
    touch = mobile.new_page()
    touch.goto(URL)
    touch.wait_for_function('Boolean(window.equationBench)')
    tvp = touch.locator('.scada-diagram-scroll')
    tvp.scroll_into_view_if_needed()
    box = tvp.bounding_box()
    cx = box['x'] + box['width'] / 2
    cy = box['y'] + box['height'] / 2
    cdp = mobile.new_cdp_session(touch)

    def points(x1, x2):
        return [{'x': x1, 'y': cy, 'id': 1}, {'x': x2, 'y': cy, 'id': 2}]
    z = touch.evaluate('equationBench.viewer.zoom')
    sy = touch.evaluate('scrollY')
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': points(cx - 35, cx + 35)})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': points(cx - 65, cx + 65)})
    touch.wait_for_timeout(80)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    check('two-finger pinch zooms contained viewer', touch.evaluate('equationBench.viewer.zoom') > z)
    check('pinch does not scroll page', touch.evaluate('scrollY') == sy)
    state = touch.evaluate('equationBench.viewer.camera.state')
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': cx, 'y': cy, 'id': 1}]})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': cx + 50, 'y': cy + 25, 'id': 1}]})
    touch.wait_for_timeout(80)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    check('one-finger touch pans viewer', touch.evaluate('equationBench.viewer.camera.state.x') != state['x'])
    touch.wait_for_timeout(350)
    touch.locator('[data-scada-camera-fit]').tap()
    touch.wait_for_timeout(100)
    check('touch fit recovers full diagram', touch.evaluate('equationBench.viewer.camera.state.fitted'))
    touch.locator('[data-scada-zoom="reset"]').tap()
    touch.screenshot(path=str(OUT / 'phone-detail.png'))
    check('phone detail scale remains contained', tvp.evaluate('e=>e.scrollTop===0&&e.scrollLeft===0'))
    check('no interaction runtime errors', not errors, errors)
    check('no missing or rejected interaction HTTPS responses', not missing, missing)
    receipt = {'browser': b.version, 'url': URL, 'delivery': delivery_label, 'checks': checks, 'errors': errors, 'missing': missing, 'served_sha256': served_sha256, 'local_reference_sha256': {'software/cadagent/webkit/scada/sim/examples/model-switching/main.mjs': hashlib.sha256((ROOT / 'software/cadagent/webkit/scada/sim/examples/model-switching/main.mjs').read_bytes()).hexdigest()}}
    (OUT / 'interaction-review.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': len(checks)}))
    b.close()
