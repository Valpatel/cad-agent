"""Export package-owned SVG previews from canonical artwork, with no live model.

Generation uses Chromium's native selectors and animation styles, and original
CSS source slices. --check is read-only and requires no browser. Every output is
owned by img/symbols, img/states, their indexes, or metadata/gallery.json.
"""
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import argparse
import hashlib
import html
import json
import mimetypes
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

PACKAGE = UI
TOOLS = Path(__file__).resolve().parent / 'gallery'
sys.path.insert(0, str(TOOLS))
from asset_maps import asset_maps

BASE = 'https://scada-gallery.test'
FORMAT = 'scada-ui-svg-gallery'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    # Prose maps cannot affect artwork. Keep all other source inputs covered,
    # including any future local image/font assets introduced by the renderer.
    paths = [p for p in (PACKAGE / 'src').rglob('*') if p.is_file() and p.suffix != '.md']
    paths += [Path(__file__).resolve(), REPO / 'tools/webkit/scada/scada_paths.py', REPO / 'tools/webkit/scada/paths.mjs'] + [p for p in TOOLS.rglob('*') if p.is_file() and p.suffix in ('.mjs', '.json', '.py')]
    return {str(p.relative_to(REPO)): sha(p.read_bytes()) for p in sorted(paths)}


def check(root):
    manifest = json.loads((root / 'metadata/gallery.json').read_text())
    if manifest['format'] != FORMAT or manifest['version'] != 1:
        raise RuntimeError('Unsupported gallery manifest')
    if manifest['source_hashes'] != source_hashes():
        raise RuntimeError('Gallery source changed; regenerate with npm --prefix tools/webkit/scada run gallery:generate')
    inventory = json.loads(subprocess.check_output(['node', str(TOOLS / 'inventory.mjs')], cwd=PACKAGE))
    expected_symbols = [row for row in inventory if row['sample'] is None]
    expected_states = [row for row in inventory if row['sample'] is not None]
    for group, rows in [('symbols', expected_symbols), ('states', expected_states)]:
        actual_rows = manifest[group]
        if len(actual_rows) != len(rows):
            raise RuntimeError('Gallery manifest catalog coverage changed: ' + group)
        for expected_row, actual_row in zip(rows, actual_rows):
            if any(actual_row.get(key) != value for key, value in expected_row.items()):
                raise RuntimeError('Gallery manifest state/catalog mismatch: ' + expected_row['path'])
            data = (root / expected_row['path']).read_bytes()
            if actual_row['sha256'] != sha(data) or actual_row['bytes'] != len(data):
                raise RuntimeError('Gallery image record differs from its output: ' + expected_row['path'])
    expected = set(manifest['outputs'])
    actual = {str(p.relative_to(root)) for owner in ['img/symbols', 'img/states'] for p in (root / owner).rglob('*') if p.is_file()}
    actual.add('img/README.md')
    if expected != actual:
        raise RuntimeError(f'Gallery output paths differ: {sorted(expected ^ actual)}')
    for name, digest in manifest['outputs'].items():
        if sha((root / name).read_bytes()) != digest:
            raise RuntimeError(f'Gallery output changed: {name}')
    print(json.dumps({'checked': len(expected), 'symbols': len(manifest['symbols']), 'states': len(manifest['states'])}))


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


def generate(target):
    from playwright.sync_api import sync_playwright
    initial_hashes = source_hashes()
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
    lines = ['# SCADA UI image gallery', '', '[Package owner](../README.md) · [Equipment map](symbols/README.md) · [Interactive example](../examples/components/index.html) · [State examples](states/README.md) · [UI snapshots](thumbnails/README.md)', '',
             'Each library owns its own `img/` directory. This package owns equipment artwork, visual states and viewer/workspace previews. [Simulation scenario previews](../../sim/img/README.md) belong to the separate model package.', '',
             '```mermaid', 'flowchart TD', '  UI["scada-ui / img"] --> Symbols["symbols / equipment families"]', '  UI --> States["states / selected visual comparisons"]', '  UI --> Captures["thumbnails / equipment and workspace JPEGs"]', '  Model["scada-sim / img"] --> Scenarios["model-owned scenario previews"]', '  UI -. "sibling library link" .-> Model', '```', '',
             f"The catalog contains {len(manifest['symbols'])} generated SVG previews. SVG images contain the canonical equipment artwork, native SVG text/readouts and inline CSS animation; no scripts, external styles, fonts or images. GitHub and other Markdown renderers can display them using ordinary relative image links. Animation support depends on the renderer; the first frame remains useful. The live examples provide interactive state controls.", '',
             'All displayed values and selected states are illustrative, editable rendering inputs. An animated picture is not a process model. Read [the style guide](../STYLE_GUIDE.md) and [contribution guide](../CONTRIBUTING.md) before adding assets.', '',
             '| Folder | Contents and use |', '| --- | --- |',
             '| [symbols/](symbols/README.md) | Every default type and declared variant, grouped by equipment family. |',
             f"| [states/](states/README.md) | {len(manifest['states'])} illustrative comparisons for motion, availability, damage and retained inventory. |",
             '| [thumbnails/](thumbnails/README.md) | Static equipment, variant, state and reusable UI captures. |', '',
             'Generate SVGs and these maps with `npm --prefix tools/webkit/scada run gallery:generate`; verify with `npm --prefix tools/webkit/scada run gallery:check`. See the [export contract](../docs/GALLERY_EXPORT.md) and [gallery manifest](../metadata/gallery.json) for provenance and checks.', '',
             '| Family | Previews | Sample |', '| --- | --- | --- |']
    labels = {category['id']: category['label'] for category in categories}
    labels.update({row['type']: row['label'] for row in manifest['symbols'] if not row['variant']})
    for category in categories:
        assets = [row for row in manifest['symbols'] if row['category'] == category['id']]
        if not assets:
            continue
        preview = assets[0]['path'].removeprefix('img/')
        label = html.escape(category['label'])
        lines.append(f'| [{label}](symbols/{category["id"]}/README.md) | {len(assets)} | <img src="{preview}" alt="{label} example" width="160"> |')
    files['img/README.md'] = ('\n'.join(lines) + '\n').encode()
    files.update(asset_maps(manifest['symbols'], 'img/symbols', 'Equipment previews', labels))
    files.update(asset_maps(manifest['states'], 'img/states', 'Visual state examples', labels))
    manifest['outputs'] = {name: sha(data) for name, data in sorted(files.items())}
    # Preflight completely before replacing any owned output. Never prune sibling captures.
    if manifest['source_hashes'] != source_hashes():
        raise RuntimeError('Gallery source changed during generation; no outputs were replaced')
    for candidate in [target, *target.parents]:
        if candidate.is_symlink():
            raise RuntimeError('Symlink in gallery output root: ' + str(candidate))
    # Validate all paths before pruning any managed subtree. A capture directory
    # or a symlink must never redirect this writer into another output owner.
    for name in [*files, 'metadata/gallery.json', 'img/symbols', 'img/states']:
        relative = Path(name)
        if name not in ['img/README.md', 'metadata/gallery.json', 'img/symbols', 'img/states'] and not name.startswith(('img/symbols/', 'img/states/')):
            raise RuntimeError('Output outside gallery ownership: ' + name)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid gallery output path: ' + name)
        path = target / relative
        for candidate in [path, *path.parents]:
            if candidate == target:
                break
            if candidate.is_symlink():
                raise RuntimeError('Symlink in gallery output path: ' + str(candidate))
    for directory in [target, target / 'img', target / 'metadata', target / 'img/symbols', target / 'img/states']:
        if directory.exists() and not directory.is_dir():
            raise RuntimeError('File blocks gallery output directory: ' + str(directory))
    for name in ['img/README.md', 'metadata/gallery.json']:
        path = target / name
        if path.exists() and not path.is_file():
            raise RuntimeError('Directory blocks gallery output file: ' + str(path))
    target.mkdir(parents=True, exist_ok=True)
    for owner in ['img/symbols', 'img/states']:
        path = target / owner
        if path.exists():
            shutil.rmtree(path)
    for name, data in files.items():
        path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    (target / 'metadata').mkdir(exist_ok=True)
    (target / 'metadata/gallery.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'symbols': len(manifest['symbols']), 'states': len(manifest['states']), 'decoded': loaded, 'svg_bytes': sum(a['bytes'] for a in manifest['symbols'] + manifest['states'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only source and generated-output hash verification; no browser required')
    parser.add_argument('--output', type=Path, default=PACKAGE, help='Package-shaped output root (use work/ for a study)')
    args = parser.parse_args()
    if args.check:
        check(args.output.resolve())
    else:
        generate(args.output.absolute())
