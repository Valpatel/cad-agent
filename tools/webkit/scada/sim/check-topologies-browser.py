"""Inspect generated topology SVGs as documents and image-mode previews."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import shutil
from playwright.sync_api import sync_playwright

PACKAGE = SIM
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('topology-browser'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
manifest_path = PACKAGE / 'metadata/topologies.json'
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
errors, checked = [], []
assets = {record['path']: PACKAGE / record['path'] for record in manifest['scenarios']}
for path in assets.values():
    assert path.resolve().is_relative_to((PACKAGE / 'img/topologies').resolve()) and path.is_file(), str(path)
BASE = 'https://topology-browser.test'
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 900, 'height': 800}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    def serve(route):
        if not route.request.url.startswith(BASE + '/'):
            errors.append('Unexpected resource request')
            return route.abort()
        name = route.request.url.removeprefix(BASE + '/')
        path = assets.get(name)
        if path is None:
            return route.fulfill(status=404, body='Unknown topology')
        route.fulfill(body=path.read_bytes(), content_type='image/svg+xml')
    page.route('**/*', serve)
    for record in manifest['scenarios']:
        page.set_viewport_size({'width': int(record['width']), 'height': int(record['height'])})
        page.goto(BASE + '/' + record['path'])
        report = page.evaluate('''()=>{
          const errors=[],width=document.documentElement.viewBox.baseVal.width;
          for(const label of document.querySelectorAll('[data-label]')){
            const box=label.getBBox(),card=label.parentElement.querySelector('rect');
            if(box.x<8||box.x+box.width>Number(card.getAttribute('width'))-8||box.y<83||box.y+box.height>Number(card.getAttribute('height'))-8)errors.push({label:label.textContent,box:{x:box.x,y:box.y,width:box.width,height:box.height}});
            if(parseFloat(getComputedStyle(label).fontSize)<14)errors.push({label:label.textContent,small:true});
          }
          for(const heading of document.querySelectorAll('[data-heading]')){const box=heading.getBBox();if(box.x<20||box.x+box.width>width-20)errors.push({heading:heading.textContent,overflow:true});}
          return {errors,nodes:document.querySelectorAll('[data-node]').length,edges:document.querySelectorAll('[data-edge]').length,animated:document.getAnimations().length};
        }''')
        assert not report['errors'] and report['animated'] == 0, (record['id'], report)
        assert report['nodes'] == len(record['nodes']) and report['edges'] == len(record['edges'])
        page.screenshot(path=str(args.output / (record['id'] + '.png')), animations='allow')
        checked.append({'id': record['id'], **report})
    # Image mode is what Markdown uses; no document-level CSS or script can leak
    # into these files. Every image must decode at the declared natural size.
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', serve)
    cards = ''.join('<figure><figcaption>' + record['id'] + '</figcaption><img src="' + BASE + '/' + record['path'] + '"></figure>' for record in manifest['scenarios'])
    page.set_content('<style>body{margin:0;padding:18px;background:#06121c;color:#dcecf1;font:16px Arial}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}figcaption{padding:8px}img{display:block;width:100%;height:auto}</style><div class="grid">' + cards + '</div>')
    decoded = page.evaluate('async()=>{await Promise.all([...document.images].map(image=>image.decode()));return [...document.images].map(image=>({width:image.naturalWidth,height:image.naturalHeight}));}')
    assert len(decoded) == len(checked) and all(image['width'] == record['width'] and image['height'] == record['height'] for image, record in zip(decoded, manifest['scenarios']))
    page.screenshot(path=str(args.output / 'contact-sheet.jpg'), type='jpeg', quality=85, full_page=True)
    for start in range(0, len(checked), 12):
        page.evaluate('start=>[...document.querySelectorAll("figure")].forEach((figure,index)=>figure.style.display=index>=start&&index<start+12?"":"none")', start)
        page.screenshot(path=str(args.output / f'contact-sheet-{start//12+1:02d}.jpg'), type='jpeg', quality=85, full_page=True)
    assert not errors, errors
    source_stable = all(hashlib.sha256((REPO / path).read_bytes()).hexdigest() == expected for path, expected in manifest['source_hashes'].items())
    assert source_stable and manifest_path.read_bytes() == manifest_bytes, 'Topology sources or output manifest changed during browser QA'
    result = {'browser': browser.version, 'scenarios': len(checked), 'image_decode_count': len(decoded), 'label_min_px': 14, 'sourceStable': source_stable, 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'checks': checked, 'errors': errors}
    (args.output / 'acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print(json.dumps({'checked': len(checked), 'decoded': len(decoded), 'errors': errors}))
