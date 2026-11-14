"""Compare exported SVG images with full CSS and exercise image-mode motion."""
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
from io import BytesIO
import argparse
import importlib.util
import json
import mimetypes
import shutil
from urllib.parse import unquote, urlparse, parse_qs
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops

PACKAGE = UI
SPEC = importlib.util.spec_from_file_location('gallery_generator', TOOLS / 'ui/generate-gallery.py')
generator = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(generator)
BASE = 'https://scada-gallery-qa.test'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gallery-root', type=Path, default=PACKAGE, help='Package-shaped gallery output to verify')
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('gallery-browser'))
args = parser.parse_args()
root = args.gallery_root.resolve(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
generator.check(root)
manifest = json.loads((root / 'metadata/gallery.json').read_text())
assets = manifest['symbols'] + manifest['states']
references = {}
report = {'method': 'Real Chromium SVG img documents; same-position full-CSS/subset comparisons. No live model.',
          'source_hashes': manifest['source_hashes'], 'comparisons': [], 'motion': [], 'errors': []}
fixture = '<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#08131d}img{display:block;width:480px;height:360px}</style><script type="module" src="/tools/webkit/scada/ui/gallery/exporter.mjs"></script>'
def serve(route):
    url = urlparse(route.request.url)
    if url.netloc != urlparse(BASE).netloc:
        raise RuntimeError('Unexpected gallery request: ' + route.request.url)
    if url.path == '/fixture.html':
        return route.fulfill(content_type='text/html', body=fixture)
    name = unquote(url.path).lstrip('/')
    if name.startswith('full/'):
        data = references[name[5:]].encode(); mime = 'image/svg+xml'
    else:
        path = (root / name) if name.startswith('img/') else (REPO / name)
        path = path.resolve()
        if not (path.is_relative_to(root) or path.is_relative_to(PACKAGE) or path.is_relative_to(TOOLS)) or not path.is_file():
            raise RuntimeError('Missing gallery dependency: ' + str(path))
        data = path.read_bytes(); mime = 'text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(path)[0] or 'application/octet-stream'
    query = parse_qs(url.query)
    if 'frame' in query:
        frame = int(query['frame'][0]); at = data.rfind(b'</svg>')
        if at < 0: raise RuntimeError('Frame requested for a non-SVG asset')
        data = data[:at] + f'<style>*{{animation-play-state:paused!important;animation-delay:-{frame}ms!important;transition:none!important}}</style>'.encode() + data[at:]
    route.fulfill(body=data, content_type=mime)

def display(page, url):
    page.evaluate('src=>{document.body.innerHTML="";const image=new Image();image.src=src;document.body.append(image)}', url)
    page.wait_for_function('document.images.length===1&&document.images[0].complete&&document.images[0].naturalWidth===480')
    page.wait_for_timeout(30)

def capture(page):
    return Image.open(BytesIO(page.screenshot(animations='allow'))).convert('RGB')

def difference(a, b):
    diff = ImageChops.difference(a, b)
    return {'changedPixelsOver2': sum(1 for pixel in diff.getdata() if max(pixel) > 2), 'bbox': diff.getbbox()}

def image_key(asset):
    # Nested type folders deliberately reuse default.svg and variant names.
    # Preserve the full identity in diagnostic captures and contact sheets.
    return str(Path(asset['path']).with_suffix('')).replace('/', '--')

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
    report['browser'] = browser.version
    context = browser.new_context(viewport={'width': 480, 'height': 360}, reduced_motion='no-preference')
    context.route('**/*', serve); page = context.new_page(); page.on('pageerror', lambda error: report['errors'].append(str(error)))
    page.goto(BASE + '/fixture.html'); page.wait_for_function('!!window.scadaGallery')
    import subprocess
    css = json.loads(subprocess.check_output(['node', str(TOOLS / 'ui/gallery/css-source-tree.mjs')], cwd=PACKAGE))['css']
    for asset in assets:
        selection = {key: asset[key] for key in ['type', 'variant', 'state', 'sample', 'stateLabel']}
        result = page.evaluate('({selection,css})=>window.scadaGallery.exportCard(selection,css,{subset:false})', {'selection': selection, 'css': css})
        references[asset['path']] = result['svg']
    browser.close()
    for motion in ['no-preference', 'reduce']:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True,
            args=['--no-sandbox'] + (['--force-prefers-reduced-motion'] if motion == 'reduce' else []))
        context = browser.new_context(viewport={'width': 480, 'height': 360}, reduced_motion=motion)
        context.route('**/*', serve); page = context.new_page(); page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.goto(BASE + '/fixture.html')
        for asset in assets:
            frames = [400, 1200] if asset['sample'] and motion == 'no-preference' else [1200]
            for frame in frames:
                suffix = '?frame=' + str(frame) if motion == 'no-preference' else ''
                display(page, BASE + '/full/' + asset['path'] + suffix); full = capture(page)
                display(page, BASE + '/' + asset['path'] + suffix); subset = capture(page)
                result = {'path': asset['path'], 'motion': motion, 'frameMs': frame if suffix else None, **difference(full, subset)}
                report['comparisons'].append(result)
                if result['changedPixelsOver2'] or asset['sample'] or motion == 'no-preference':
                    filename = image_key(asset) + '-' + motion + '-' + str(frame) + '.png'
                    subset.save(output / filename); result['screenshot'] = filename
        # No forced timeline in this pass: sample actual image motion over time.
        for asset in manifest['states']:
            display(page, BASE + '/' + asset['path']); page.wait_for_timeout(120); a = capture(page)
            page.wait_for_timeout(550); b = capture(page)
            filename = image_key(asset) + '-' + motion + '-motion.png'; b.save(output / filename)
            report['motion'].append({'path': asset['path'], 'motion': motion, 'state': asset['state'], 'expectedMotion': asset['expectedMotion'], 'screenshot': filename, **difference(a, b)})
        browser.close()
# Reviewable overview plus full-resolution cards, never a substitute for
# individual state/inspector/diagram inspection of changed equipment.
columns, thumb_width, thumb_height = 6, 240, 180
rows = (len(manifest['symbols']) + columns - 1) // columns
sheet = Image.new('RGB', (columns * thumb_width, rows * thumb_height), '#08131d')
for index, asset in enumerate(manifest['symbols']):
    source = output / (image_key(asset) + '-no-preference-1200.png')
    with Image.open(source) as card:
        card.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        sheet.paste(card, ((index % columns) * thumb_width, (index // columns) * thumb_height))
sheet.save(output / 'symbol-contact-sheet.jpg', quality=90)
report['contactSheet'] = 'symbol-contact-sheet.jpg'
report['sourceStable'] = manifest['source_hashes'] == generator.source_hashes()
report['differences'] = [row for row in report['comparisons'] if row['changedPixelsOver2']]
(output / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
assert report['sourceStable'], 'Source changed during gallery QA'
assert not report['errors'], report['errors']
assert not report['differences'], f"{len(report['differences'])} full-CSS comparison differences; inspect acceptance.json"
assert all(row['changedPixelsOver2'] == 0 for row in report['motion'] if row['motion'] == 'reduce'), 'Reduced-motion SVG images must remain still'
for row in report['motion']:
    if row['motion'] != 'no-preference':
        continue
    assert row['expectedMotion'] in ['animated', 'still'], row['path']
    observed = 'animated' if row['changedPixelsOver2'] > 0 else 'still'
    assert observed == row['expectedMotion'], f"{row['path']}: expected {row['expectedMotion']}, observed {observed}"
print(json.dumps({'comparisons': len(report['comparisons']), 'motion_checks': len(report['motion']), 'errors': report['errors']}))
