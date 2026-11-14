"""Capture each real Industry Lab overview from the reusable package example.

The model is reset and paused through its actual controls before capture. No
synthetic artwork or image resizing is used. Source and JPEG hashes make stale
committed screenshots detectable with --check; manifests contain no timestamps.
"""
import argparse
import ast
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import shutil
import sys
from urllib.parse import unquote, urlparse

from PIL import Image
from playwright.sync_api import sync_playwright
from scenario_gallery_docs import gallery_index, asset_gallery_maps
# Reuse the browser capture helper; it has no production dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scada_paths import REPO, UI, SIM, TOOLS, scenario_asset_path, scenario_sector_groups
CAPTURE_HELPER = TOOLS / 'ui/browser_capture.py'
sys.path.insert(0, str(CAPTURE_HELPER.parent))
from browser_capture import fitted_camera_coverage, freeze_animation_frame

PACKAGE = SIM
MANIFEST = PACKAGE / 'metadata/thumbnails.json'
THUMBNAILS = PACKAGE / 'img/thumbnails'
BASE = 'https://scenario-thumbnails.test'
ENTRY = 'software/cadagent/webkit/scada/explorer/index.html'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
parser.add_argument('--indexes-only', action='store_true', help='Validate existing captures and refresh only Markdown maps')
parser.add_argument('--chromium', default=shutil.which('chromium'))
args = parser.parse_args()
catalog = json.loads((PACKAGE / 'scenarios/index.json').read_text())['scenarios']
scenario_sector_groups(catalog)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    roots = [PACKAGE / folder for folder in ('src', 'scenarios', 'examples')]
    roots.append(REPO / 'software/cadagent/webkit/scada/explorer')
    roots.append(UI / 'src')
    return {path.relative_to(REPO).as_posix(): sha(path)
            for root in roots for path in sorted(root.rglob('*'))
            if path.suffix in ('.mjs', '.css', '.html', '.json')}


def image_info(path):
    data = path.read_bytes()
    assert data[:3] == b'\xff\xd8\xff', path
    with Image.open(path) as image:
        width, height = image.size
    return {'path': path.relative_to(PACKAGE).as_posix(), 'width': width, 'height': height, 'bytes': len(data), 'sha256': sha(path)}





def capture_fingerprint(source):
    """Hash capture semantics independently of Markdown and CLI/check plumbing.

    Imports, capture constants/helpers and the entire capture loop are included;
    prose templates and this provenance checker cannot change screenshot bytes.
    """
    nodes = ast.parse(source).body
    selected = []
    capturing = False
    for node in nodes:
        statement = ast.unparse(node)
        if statement.startswith('THUMBNAILS.mkdir('):
            capturing = True
        if statement.startswith('MANIFEST.parent.mkdir('):
            break
        include = True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            include = statement != 'import ast' and not (isinstance(node, ast.ImportFrom) and node.module == 'scenario_gallery_docs')
        elif isinstance(node, ast.FunctionDef):
            include = node.name not in {'gallery_index', 'capture_fingerprint', 'check_capture', 'check', 'write_indexes', 'gallery_outputs'}
        elif isinstance(node, ast.Assign):
            include = capturing or not any(isinstance(target, ast.Name) and target.id in {'parser', 'args'} for target in node.targets)
        elif isinstance(node, ast.If) and not capturing:
            include = ast.unparse(node.test) not in {'args.check', 'args.indexes_only'}
        elif isinstance(node, ast.Expr) and not capturing:
            include = not isinstance(node.value, ast.Constant) and not statement.startswith(("parser.add_argument('--check'", "parser.add_argument('--indexes-only'"))
        if include:
            selected.append(ast.dump(node, include_attributes=False))
    if not capturing:
        raise RuntimeError('Capture implementation boundary is missing')
    return hashlib.sha256('\n'.join(selected).encode()).hexdigest()


def check_capture(manifest):
    assert manifest['source_hashes'] == source_hashes(), 'Source changed; regenerate scenario thumbnails.'
    if 'capture_implementation_sha256' in manifest:
        assert manifest['capture_implementation_sha256'] == capture_fingerprint(Path(__file__).read_text()), 'Capture implementation changed; regenerate scenario thumbnails.'
    else:
        assert manifest['generator_sha256'] == sha(Path(__file__)), 'Generator changed; regenerate scenario thumbnails.'
    assert manifest['capture_helper_sha256'] == sha(CAPTURE_HELPER)
    assert [entry['id'] for entry in manifest['scenarios']] == [entry['id'] for entry in catalog]
    for entry in manifest['scenarios']:
        assert entry['path'] == scenario_asset_path('thumbnails', entry), entry['id']
    for entry in manifest['scenarios'] + [manifest['contact_sheet']]:
        actual = image_info(PACKAGE / entry['path'])
        assert all(actual[key] == entry[key] for key in ('width', 'height', 'bytes', 'sha256')), entry['path']
        assert actual['width'] >= 900 and actual['height'] >= 300


def gallery_outputs(manifest):
    outputs = {'img/README.md': gallery_index(manifest)}
    outputs.update(asset_gallery_maps(manifest['scenarios'], 'thumbnails'))
    lines = ['# Scenario diagram gallery', '',
             'These previews show the actual reusable Explorer after reset, pause and Zoom to fit. All quantities and responses are illustrative and editable.', '',
             '[Browse sector folders](../img/thumbnails/README.md) · [Complete contact sheet](../img/thumbnails/contact-sheet.jpg) · [Capture manifest](../metadata/thumbnails.json)', '',
             '| Scenario | Initial view | Definitions |', '| --- | --- | --- |']
    for entry in manifest['scenarios']:
        image = '../' + entry['path']
        title = html.escape(entry['title'], quote=True)
        lines.append(f'| {title} | <a href="{image}"><img src="{image}" width="320" alt="{title} initial diagram"></a> | [System JSON](../scenarios/{entry["system"]}) · [Model JSON](../scenarios/{entry["model"]}) |')
    lines += ['', 'Generate with `npm --prefix tools/webkit/scada run thumbnails:scenarios`; use `-- --check` to verify source and image freshness.', '']
    outputs['docs/scenario-gallery.md'] = '\n'.join(lines)
    return outputs


def write_indexes(manifest):
    outputs = gallery_outputs(manifest)
    for name in outputs:
        path = PACKAGE / name
        assert all(not ancestor.is_symlink() for ancestor in [path, *path.parents]), 'Gallery maps must not follow symlinks.'
        assert not path.exists() or path.is_file(), 'Gallery map path is not a file.'
    for name, content in outputs.items():
        path = PACKAGE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def check(manifest):
    check_capture(manifest)
    outputs = gallery_outputs(manifest)
    for name, content in outputs.items():
        assert (PACKAGE / name).read_text() == content, f'Scenario gallery map is stale: {name}'
    expected = {entry['path'] for entry in manifest['scenarios']} | {manifest['contact_sheet']['path']}
    expected |= {name for name in outputs if name.startswith('img/thumbnails/')}
    actual = {path.relative_to(PACKAGE).as_posix() for path in THUMBNAILS.rglob('*') if path.is_file()}
    assert actual == expected, f'Unlisted or missing thumbnail gallery files: {actual ^ expected}'



if args.indexes_only:
    if args.check:
        parser.error('--check and --indexes-only cannot be combined')
    manifest = json.loads(MANIFEST.read_text())
    check_capture(manifest)
    write_indexes(manifest)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    check(manifest)
    print(json.dumps({'checked': True, 'indexes_refreshed': len(gallery_outputs(manifest)), 'captures_reused': len(catalog)}))
    raise SystemExit(0)


if args.check:
    check(json.loads(MANIFEST.read_text()))
    print(json.dumps({'checked': True, 'scenarios': len(catalog)}))
    raise SystemExit(0)

THUMBNAILS.mkdir(parents=True, exist_ok=True)
previous = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'scenarios': []}
for entry in previous['scenarios']:
    assert image_info(PACKAGE / entry['path'])['sha256'] == entry['sha256'], 'Existing capture changed outside its generator'
errors, missing = [], []
manifest = {'format': 'scada-scenario-thumbnails', 'version': 1,
            'source_hashes': source_hashes(), 'generator_sha256': sha(Path(__file__)),
            'capture_helper_sha256': sha(CAPTURE_HELPER),
            'capture': {'renderer': 'Chromium software rendering, sRGB', 'format': 'jpeg', 'quality': 85, 'viewport': {'width': 1440, 'height': 1600}, 'model_minutes': 0, 'running': False, 'animation_frame_ms': 1200, 'crop': 'Actual contained viewer after Zoom to fit; overview scale depends on the viewport and declared diagram bounds.'},
            'scenarios': []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb'])
    page = browser.new_page(viewport=manifest['capture']['viewport'], device_scale_factor=1, color_scheme='dark')
    page.on('pageerror', lambda error: errors.append(str(error)))

    def serve(route):
        parsed = urlparse(route.request.url)
        path = (REPO / unquote(parsed.path).lstrip('/')).resolve()
        if parsed.netloc != urlparse(BASE).netloc or not path.is_relative_to(REPO) or not path.is_file():
            missing.append(route.request.url)
            return route.fulfill(status=404, body='Missing canonical dependency')
        route.fulfill(status=200, body=path.read_bytes(), content_type='text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(path)[0] or 'application/octet-stream')

    page.route('**/*', serve)
    for entry in catalog:
        page.goto(BASE + '/' + ENTRY + '?scenario=' + entry['id'], wait_until='networkidle')
        page.locator('#lab-viewer [data-scada-picker]').wait_for(state='visible')
        page.locator('[data-scada-open=session]').click()
        # Both commands run in one event-loop turn: a real timer cannot advance
        # between resetting the process and pausing its model.
        page.evaluate("""() => {
          document.querySelector('[data-action=reset]').click();
          if(document.querySelector('#industry-lab').dataset.running==='true')document.querySelector('[data-action=running]').click();
        }""")
        page.keyboard.press('Escape')
        assert page.locator('[data-kpi=time]').inner_text().startswith('0.0')
        assert page.locator('#industry-lab').get_attribute('data-running') == 'false'
        assert page.locator('[data-scenario-title]').inner_text() == entry['title']
        page.locator('#lab-viewer [data-scada-zoom=fit]').click()
        page.mouse.move(0, 0)
        freeze_animation_frame(page)
        assert page.evaluate('document.documentElement.scrollWidth') == 1440
        viewer = page.locator('#lab-viewer .scada-viewer')
        assert viewer.evaluate('element=>element.scrollWidth<=element.clientWidth+1')
        system = json.loads((PACKAGE / 'scenarios' / entry['system']).read_text())
        active_view = page.locator('#lab-viewer [data-scada-view-choice][aria-current=page]').get_attribute('data-scada-view-choice')
        view_definition = next(view for view in system['views'] if view['id'] == active_view)
        coverage = fitted_camera_coverage(page, '#lab-viewer', [placement['component'] for placement in view_definition['placements']], view_definition['canvas'])
        path = PACKAGE / scenario_asset_path('thumbnails', entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        viewer.screenshot(path=str(path), type='jpeg', quality=85, animations='allow', caret='hide')
        manifest['scenarios'].append({'id': entry['id'], 'title': entry['title'], 'sector': entry['sector'], 'view': active_view,
                                      'system': entry['system'], 'model': entry['model'], 'components': len(system['components']), 'camera_coverage': coverage, **image_info(path)})
        print(json.dumps({'scenario': entry['id'], 'captured': True}), flush=True)
    # This index uses the exact JPEGs at their own aspect ratios; the individual
    # files retain the complete fitted diagram and toolbar at overview scale.
    cards = ''.join('<figure><figcaption>' + entry['title'] + '</figcaption><img src="/software/cadagent/webkit/scada/sim/' + entry['path'] + '"></figure>' for entry in manifest['scenarios'])
    page.set_viewport_size({'width': 2000, 'height': 1000})
    page.set_content('<!doctype html><style>*{box-sizing:border-box}body{margin:0;padding:26px;background:#07131d;color:#dcecf1;font:18px Arial,sans-serif}h1{font-size:28px;margin:0 0 22px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}figure{margin:0;padding:10px;border:1px solid #355665;border-radius:10px;background:#102635}figcaption{margin-bottom:10px;font-weight:600}img{display:block;width:100%;height:auto}</style><h1>' + str(len(catalog)) + ' reusable control rooms · illustrative initial models</h1><div class="grid">' + cards + '</div>')
    page.evaluate('async()=>Promise.all([...document.images].map(image=>image.decode()))')
    contact = THUMBNAILS / 'contact-sheet.jpg'
    page.screenshot(path=str(contact), type='jpeg', quality=85, full_page=True, animations='disabled')
    manifest['contact_sheet'] = image_info(contact)
    assert not errors and not missing, (errors, missing)
    browser.close()
MANIFEST.parent.mkdir(parents=True, exist_ok=True)
manifest['capture_implementation_sha256'] = capture_fingerprint(Path(__file__).read_text())
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
write_indexes(manifest)
current_paths = {entry['path'] for entry in manifest['scenarios']}
for entry in previous['scenarios']:
    if entry['path'] not in current_paths:
        relative = Path(entry['path'])
        assert entry['path'].startswith('img/thumbnails/') and '..' not in relative.parts
        (PACKAGE / relative).unlink()
check(manifest)
print(json.dumps({'checked': True, 'generated': len(catalog), 'manifest': MANIFEST.relative_to(REPO).as_posix(), 'runtime_errors': errors}))
