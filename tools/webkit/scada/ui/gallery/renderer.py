"""Browser export of canonical equipment artwork, independent of prose maps.

The owning generator hashes this complete module and every renderer input.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scada_paths import REPO, UI
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

PACKAGE = UI
TOOLS = Path(__file__).resolve().parent
BASE = 'https://scada-gallery.test'
FORMAT = 'scada-ui-svg-gallery'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_svg(data, result):
    root = ET.fromstring(data)
    if not result['artContentPreserved']:
        raise RuntimeError('Equipment artwork changed during image adaptation')
    for element in root.iter():
        if element.tag.split('}')[-1] in ['script', 'foreignObject', 'image']:
            raise RuntimeError('Nonportable SVG element')
        for key, value in element.attrib.items():
            if key.split('}')[-1].lower().startswith('on'):
                raise RuntimeError('Event handler in gallery SVG')
            if key.split('}')[-1] in ('href', 'src') and not value.startswith('#'):
                raise RuntimeError('External resource in gallery SVG')
    if '@import' in data or 'http:' in data.replace('http://www.w3.org/2000/svg', '') or 'https:' in data:
        raise RuntimeError('External resource in gallery SVG')
    for match in re.finditer(r'url\(\s*[\"\']?([^\"\'\)]+)', data):
        if not match.group(1).startswith('#'):
            raise RuntimeError('Nonlocal CSS URL in gallery SVG')
    if result['subsetReport']['selectorFailures'] or result['subsetReport']['unknownRuleTypes']:
        raise RuntimeError('Unsupported CSS in gallery')


def render_gallery(initial_hashes):
    from playwright.sync_api import sync_playwright
    payload = json.loads(subprocess.check_output(['node', str(TOOLS / 'css-source-tree.mjs')], cwd=PACKAGE))
    samples = json.loads((TOOLS / 'samples.json').read_text())
    inventory = json.loads(subprocess.check_output(['node', str(TOOLS / 'inventory.mjs')], cwd=PACKAGE))
    paths = {(row['type'], row['variant'], row['sample']): row['path'] for row in inventory}
    files = {}
    manifest = {'format': FORMAT, 'version': 1, 'package': '@valpatel/scada-ui',
                'purpose': 'Fixed illustrative visual states; no process simulation or executable image code.',
                'source_hashes': initial_hashes,
                'generator': 'tools/webkit/scada/ui/generate-gallery.py', 'css_parser': 'rrweb-cssom 0.8.0; original source slices',
                'symbols': [], 'states': []}
    errors = []
    fixture = '<!doctype html><meta charset="utf-8"><style>body{margin:0}</style><script type="module" src="/tools/webkit/scada/ui/gallery/exporter.mjs"></script>'
    def serve(route):
        url = urlparse(route.request.url)
        if url.netloc != urlparse(BASE).netloc:
            raise RuntimeError('Gallery attempted external request: ' + route.request.url)
        if url.path == '/export.html':
            return route.fulfill(content_type='text/html', body=fixture)
        if url.path.lstrip('/') in files:
            return route.fulfill(content_type='image/svg+xml', body=files[url.path.lstrip('/')])
        path = (REPO / unquote(url.path).lstrip('/')).resolve()
        if not (path.is_relative_to(PACKAGE) or path.is_relative_to(TOOLS)) or not path.is_file():
            raise RuntimeError('Missing or escaped gallery dependency: ' + str(path))
        return route.fulfill(body=path.read_bytes(), content_type='text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(path)[0] or 'application/octet-stream')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
        manifest['browser'] = browser.version
        context = browser.new_context(viewport={'width': 480, 'height': 360}, reduced_motion='no-preference')
        context.route('**/*', serve)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE + '/export.html')
        page.wait_for_function('!!window.scadaGallery')
        selections = page.evaluate('window.scadaGallery.selections')
        categories = page.evaluate('window.scadaGallery.categories')
        for selection in selections + samples:
            if 'sample' in selection and selection.get('expectedMotion') not in ['animated', 'still']:
                raise RuntimeError('State example must declare expectedMotion')
            result = page.evaluate('({selection,css,sourceTree})=>window.scadaGallery.exportCard(selection,css,{sourceTree})', {'selection': selection, **payload})
            svg = result.pop('svg')
            validate_svg(svg, result)
            name = paths[(selection['type'], selection.get('variant'), selection.get('sample'))]
            if name in files:
                raise RuntimeError('Duplicate gallery output: ' + name)
            files[name] = (svg + '\n').encode()
            result.update({'path': name, 'bytes': len(files[name]), 'sha256': sha(files[name]), 'sample': selection.get('sample'), 'stateLabel': selection.get('stateLabel', 'Active illustrative preview'), 'expectedMotion': selection.get('expectedMotion')})
            manifest['states' if 'sample' in selection else 'symbols'].append(result)
        loaded = page.evaluate('''async paths=>{for(const path of paths){const image=new Image();image.src=path;await image.decode();if(image.naturalWidth!==480||image.naturalHeight!==360)throw new Error(path);}return paths.length;}''', [BASE + '/' + name for name in files])
        manifest['image_decode_count'] = loaded
        if errors:
            raise RuntimeError(str(errors))
        browser.close()
    return files, manifest
