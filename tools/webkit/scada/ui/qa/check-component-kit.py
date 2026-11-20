"""Render the downloaded component kit independently of all application CSS/JS."""
import argparse
from contextlib import ExitStack
import json
import mimetypes
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import shutil
import tempfile
from urllib.parse import unquote, urlparse
import zipfile
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
source = parser.add_mutually_exclusive_group()
source.add_argument('--archive', type=Path)
source.add_argument('--root', type=Path)
parser.add_argument('--widths', default='1440,900,390')
parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('component-kit-browser'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []
with ExitStack() as stack:
    if args.root:
        root = args.root.resolve()
        entry = 'examples/components/index.html'
    else:
        tmp = stack.enter_context(tempfile.TemporaryDirectory(prefix='scada-kit-'))
        if not args.archive:
            parser.error('Provide --root for the installed UI package or --archive for an explicit kit ZIP.')
        archive = stack.enter_context(zipfile.ZipFile(args.archive))
        for name in archive.namelist():
            assert '..' not in Path(name).parts and not name.startswith('/')
        archive.extractall(tmp)
        root = Path(tmp) / 'scada-components'
        entry = 'index.html'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
        for width in map(int, args.widths.split(',')):
            page = browser.new_page(viewport={'width': width, 'height': 900})
            errors, missing = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def serve(route):
                name = unquote(urlparse(route.request.url).path).lstrip('/') or 'index.html'
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    missing.append(name)
                    return route.fulfill(status=404, body='Missing kit asset')
                route.fulfill(status=200, body=path.read_bytes(), content_type='text/javascript' if name.endswith('.mjs') else mimetypes.guess_type(name)[0] or 'application/octet-stream')
            page.route('**/*', serve)
            page.goto('https://component-kit.test/' + entry, wait_until='networkidle')
            options = page.locator('#component option').evaluate_all('(options) => options.map(option => option.value)')
            registry = page.evaluate("async()=>{const m=await import('/src/index.mjs');return m.SCADA_COMPONENTS.map(c=>({type:c.type,category:c.category,variants:(c.variants||[]).map(v=>v.id)}))}")
            assert sorted(options) == sorted(component['type'] for component in registry)
            variant_count = 0
            for component in options:
                page.locator('#component').select_option(component)
                assert page.locator('#error').inner_text() == '', component
                assert page.locator('#preview svg').is_visible(), component
                assert page.locator('#description').inner_text().strip(), component
                assert page.locator('#support').inner_text().strip(), component
                assert page.locator('#example-code').inner_text().find(component) >= 0
                assert page.evaluate('document.documentElement.scrollWidth') == width, component
                expected_variants = next(item['variants'] for item in registry if item['type'] == component)
                choices = page.locator('#variant option').evaluate_all('(options)=>options.map(option=>option.value).filter(Boolean)')
                assert choices == expected_variants
                for variant in choices:
                    page.locator('#variant').select_option(variant)
                    assert page.locator('#error').inner_text() == '', (component, variant)
                    assert page.locator('#preview svg').is_visible(), (component, variant)
                    assert variant in page.locator('#example-code').inner_text()
                    assert page.evaluate('document.documentElement.scrollWidth') == width, (component, variant)
                    variant_count += 1
            for component in ('pump', 'generator', 'plc-rack'):
                assert component in options, component
                page.locator('#component').select_option(component)
                page.locator('#active').uncheck()
                page.locator('#running').uncheck()
                page.locator('#fault').check()
                assert page.locator('#error').inner_text() == ''
                page.screenshot(path=str(args.output / f'{component}-fault-{width}.png'), full_page=True)
                page.locator('#fault').uncheck()
                page.locator('#active').check()
                page.locator('#running').check()
                page.screenshot(path=str(args.output / f'{component}-active-{width}.png'), full_page=True)
            page.locator('#search').fill('diesel')
            assert 'generator' in page.locator('#component option').evaluate_all('(options)=>options.map(o=>o.value)')
            page.locator('#search').fill('no-equipment-with-this-name')
            assert page.locator('#component option').count() == 0
            assert all(page.locator('#'+key).is_disabled() for key in ('active','running','fault'))
            assert page.locator('#error').inner_text() == ''
            page.locator('#search').fill('')
            page.locator('#category').select_option('nuclear')
            assert page.locator('#component option').count() == sum(c['category']=='nuclear' for c in registry)
            page.locator('#component').select_option('pwr-reactor-vessel')
            page.screenshot(path=str(args.output/f'nuclear-{width}.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth') == width
            page.emulate_media(reduced_motion='reduce')
            active_animations = page.locator('#preview').evaluate('(root) => root.getAnimations({subtree:true}).filter(animation => animation.playState === "running").length')
            assert active_animations == 0, active_animations
            assert not errors, errors
            assert not missing, missing
            results.append({'width':width, 'components':len(options), 'variants':variant_count, 'discovery':True, 'states':'active / off / paused / fault', 'reduced_motion':True, 'errors':errors, 'missing_assets':missing})
            page.close()
        browser.close()
(args.output / 'component-kit-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
