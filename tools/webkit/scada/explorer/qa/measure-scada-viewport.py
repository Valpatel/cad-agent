"""Measure canonical Explorer geometry without modifying source or production DOM styles.

This probe records local Chromium delivery, not live deployment or physical touch.
New evidence defaults to ignored .cache/scada/; the historical architecture baseline is
never overwritten by running this script.
"""
import argparse
import hashlib
import json
import mimetypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scada_paths import REPO, UI, SIM, TOOLS
import re
import shutil
from urllib.parse import unquote, urlencode, urlparse

REPO_ROOT = REPO
ORIGIN = 'https://scada-viewport-study.test'

MEASURE = r'''() => {
 const dims = element => {
  if(!element)return null;
  const rect=element.getBoundingClientRect(),style=getComputedStyle(element);
  return {tag:element.tagName,id:element.id,className:element.className,
   clientWidth:element.clientWidth,clientHeight:element.clientHeight,
   scrollWidth:element.scrollWidth,scrollHeight:element.scrollHeight,
   scrollLeft:element.scrollLeft,scrollTop:element.scrollTop,
   rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height,bottom:rect.bottom},
   viewportVisibleHeight:Math.max(0,Math.min(rect.bottom,innerHeight)-Math.max(rect.top,0)),
   overflowX:style.overflowX,overflowY:style.overflowY,
   display:style.display,position:style.position,minHeight:style.minHeight,maxHeight:style.maxHeight,
   hasVerticalOverflow:element.scrollHeight>element.clientHeight+1,
   hasHorizontalOverflow:element.scrollWidth>element.clientWidth+1};
 };
 const selectors={root:'html',body:'body',workspace:'#industry-lab',heading:'.lab-heading',tools:'#lab-tools',toolbar:'.lab-toolbar',kpis:'.lab-kpis',viewerHost:'#lab-viewer',viewer:'.scada-viewer',tabs:'.scada-viewer-tabs',viewerToolbar:'.scada-viewer-toolbar',diagram:'[data-scada-scroll]',stage:'[data-scada-stage]',canvas:'[data-scada-canvas]',viewerStatus:'.scada-viewer-status',footer:'.lab-footer'};
 const elements=Object.fromEntries(Object.entries(selectors).map(([key,value])=>[key,dims(document.querySelector(value))]));
 const canvas=document.querySelector('[data-scada-canvas]');
 const transform=getComputedStyle(canvas).transform;
 const scale=new DOMMatrixReadOnly(transform).a;
 const labels=[...document.querySelectorAll('.scada-viewer-equipment-label')];
 const open=document.querySelector('dialog[open]');
 return {viewport:{width:innerWidth,height:innerHeight,devicePixelRatio,scrollX,scrollY},
   document:{clientWidth:document.documentElement.clientWidth,clientHeight:document.documentElement.clientHeight,scrollWidth:document.scrollingElement.scrollWidth,scrollHeight:document.scrollingElement.scrollHeight},
   view:document.querySelector('[data-scada-view-choice][aria-current="page"]')?.textContent,
   zoom:{button:document.querySelector('[data-scada-zoom="reset"]')?.textContent,scale,transform,scaleNote:document.querySelector('[data-scada-scale-note]')?.textContent},
   equipment:{count:labels.length,firstLabel:labels[0]?.textContent,fontSize:parseFloat(getComputedStyle(labels[0]).fontSize),effectiveLabelPixels:parseFloat(getComputedStyle(labels[0]).fontSize)*scale,
    buttonWidths:[...document.querySelectorAll('.scada-viewer-equipment')].map(e=>Math.round(e.getBoundingClientRect().width*100)/100)},
   elements,
   modal:open?{dialog:dims(open),header:dims(open.querySelector('.scada-dialog-header')),body:dims(open.querySelector('.scada-dialog-body')),footer:dims(open.querySelector('.scada-dialog-footer'))}:null,
   actualScrollers:[...document.querySelectorAll('*')].filter(e=>{const s=getComputedStyle(e);return /(auto|scroll)/.test(s.overflowY)&&e.scrollHeight>e.clientHeight+1&&e.getClientRects().length;}).map(dims)
 };
}'''

def stable(page):
    page.evaluate('async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO_ROOT,
                        help='Cad-agent repository root containing the SCADA library and Explorer.')
    parser.add_argument('--output', type=Path,
                        help='Evidence directory; defaults to ROOT/.cache/scada/viewport-study.')
    parser.add_argument('--scenario', default='winery', help='Scenario directory ID.')
    parser.add_argument('--viewports', default='1440x1000,390x844',
                        help='Comma-separated WIDTHxHEIGHT CSS-pixel viewports at DPR 1.')
    parser.add_argument('--chromium', default=shutil.which('chromium'),
                        help='Chromium executable; otherwise use Playwright installed Chromium.')
    parser.add_argument('--no-screenshots', action='store_true', help='Write measurements only.')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.scenario):
        parser.error('--scenario must be a directory ID, not a path.')
    try:
        args.sizes = [tuple(map(int, value.lower().split('x'))) for value in args.viewports.split(',')]
        if any(len(size) != 2 or min(size) < 1 for size in args.sizes):
            raise ValueError
    except ValueError:
        parser.error('--viewports must contain positive WIDTHxHEIGHT pairs.')
    args.root = args.root.resolve()
    args.output = (args.output or args.root/'.cache/scada/viewport-study').resolve()
    if args.output.is_relative_to(REPO_ROOT/'docs'):
        parser.error('Write new measurements to .cache/scada/ or another evidence directory; preserve committed baselines.')
    return args


def main():
    args = parse_args()
    # Keep --help usable without the optional browser dependency installed.
    from playwright.sync_api import sync_playwright

    root, output = args.root, args.output
    entry = '/software/cadagent/webkit/scada/explorer/index.html?' + urlencode({'scenario': args.scenario})
    sources = [
        'software/cadagent/webkit/scada/explorer/index.html',
        'software/cadagent/webkit/scada/explorer/styles.css',
        'software/cadagent/webkit/scada/explorer/main.mjs',
        'software/cadagent/webkit/scada/ui/src/viewer/viewer.css',
        'software/cadagent/webkit/scada/ui/src/viewer/viewer.mjs',
        'software/cadagent/webkit/scada/ui/src/workspace/workspace.css',
        f'software/cadagent/webkit/scada/sim/scenarios/{args.scenario}/system.json',
    ]
    hashes = lambda names: {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
    report = {
        'format': 'scada-viewport-study', 'scenario': args.scenario,
        'delivery': 'Chromium requests fulfilled from canonical repository bytes; no source or production DOM styles edited',
        'entry': entry, 'sourceHashes': hashes(sources), 'viewports': [],
    }
    output.mkdir(parents=True, exist_ok=True)
    served_hashes = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
        report['browser'] = browser.version
        for width, height in args.sizes:
            context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
            page = context.new_page()
            errors, requests = [], set()
            page.on('pageerror', lambda error: errors.append(str(error)))

            def fulfill(route):
                parsed = urlparse(route.request.url)
                if parsed.scheme != 'https' or parsed.netloc != urlparse(ORIGIN).netloc:
                    errors.append('Unexpected external request: ' + route.request.url)
                    route.abort()
                    return
                path = (root/unquote(parsed.path).lstrip('/')).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    errors.append('Missing resource: ' + parsed.path)
                    route.fulfill(status=404, body='Not found')
                    return
                name = path.relative_to(root).as_posix()
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if name in served_hashes and served_hashes[name] != digest:
                    errors.append('Resource changed between requests: ' + name)
                served_hashes[name] = digest
                requests.add(name)
                kind = 'text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                route.fulfill(status=200, body=data, content_type=kind)

            page.route('**/*', fulfill)
            page.goto(ORIGIN+entry, wait_until='networkidle')
            page.wait_for_function("document.querySelector('#industry-lab')?.getAttribute('aria-busy')==='false' && document.querySelector('[data-scada-equipment]')")
            stable(page)
            result = {'viewport': {'width': width, 'height': height}, 'states': {}, 'errors': errors}

            def capture(name, full=False):
                stable(page)
                result['states'][name] = page.evaluate(MEASURE)
                if not args.no_screenshots:
                    page.screenshot(path=str(output/f'{args.scenario}-{width}x{height}-{name}.png'), full_page=full)

            capture('initial', full=True)
            page.locator('[data-scada-zoom="fit"]').click()
            page.evaluate('window.scrollTo(0,0)')
            capture('fit', full=True)
            page.locator('[data-scada-zoom="reset"]').click()
            page.evaluate('window.scrollTo(0,0)')
            capture('readable-100', full=True)
            page.locator('[data-scada-open="scenarios"]').click()
            capture('scenario-modal')
            page.locator('dialog[open] [data-scada-close]').click()
            page.locator('[data-scada-inspect]').click()
            capture('equipment-modal')
            result['servedResourceCount'] = len(requests)
            report['viewports'].append(result)
            context.close()
        browser.close()

    report['servedResourceHashes'] = dict(sorted(served_hashes.items()))
    report['sourceHashesUnchanged'] = report['sourceHashes'] == hashes(sources)
    report['servedResourceHashesUnchanged'] = served_hashes == hashes(served_hashes)
    (output/'measurements.json').write_text(json.dumps(report, indent=2)+'\n')
    for item in report['viewports']:
        for name, state in item['states'].items():
            diagram, modal = state['elements']['diagram'], state['modal']
            print(json.dumps({
                'viewport': item['viewport'], 'state': name, 'document': state['document'],
                'diagramClient': [diagram['clientWidth'], diagram['clientHeight']],
                'diagramScroll': [diagram['scrollWidth'], diagram['scrollHeight']],
                'diagramY': diagram['rect']['y'], 'scale': state['zoom']['scale'],
                'effectiveLabelPixels': state['equipment']['effectiveLabelPixels'],
                'modalBody': None if modal is None else [modal['body']['clientHeight'], modal['body']['scrollHeight']],
            }))
    if not report['sourceHashesUnchanged'] or not report['servedResourceHashesUnchanged']:
        raise SystemExit('Source changed during measurement; rerun against stable files.')
    if any(item['errors'] for item in report['viewports']):
        raise SystemExit(f'Browser/resource errors recorded in {output / "measurements.json"}.')


if __name__ == '__main__':
    main()
