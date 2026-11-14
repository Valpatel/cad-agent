"""Render deterministic package thumbnails from canonical SCADA UI source.

Requires Python Playwright and Chromium. No application modules, server, drawing
substitutes, or image-generation service are used. CSS animation clocks freeze at
a fixed frame; the manifest contains no timestamps. Use --check to verify the
committed images against the current registry and manifest without rewriting.
"""
import argparse
import hashlib
import html
import json
import mimetypes
import math
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import shutil
import sys
from urllib.parse import unquote, urlparse
from PIL import Image
from playwright.sync_api import sync_playwright
# Reuse the browser capture helper; it has no production dependency.
from browser_capture import fitted_camera_coverage, freeze_animation_frame
sys.path.insert(0, str(Path(__file__).with_name("gallery")))
from asset_maps import asset_maps

PACKAGE = UI
CAPTURE_HELPER = Path(__file__).with_name('browser_capture.py')
BASE = 'https://scada-thumbnails.test'
FRAME_MS = 1200
JPEG_QUALITY = 85
WIDTH, HEIGHT = 480, 360
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--check', action='store_true')
parser.add_argument('--viewer-path', default='examples/viewer/index.html', help='Package-relative standalone viewer HTML.')
args = parser.parse_args()
THUMBS = PACKAGE / 'img/thumbnails'
MANIFEST = PACKAGE / 'metadata' / 'thumbnails.json'
VARIANT_MAP = PACKAGE / 'docs' / 'VARIANTS.md'

STYLE = '''
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Arial,sans-serif;color:#dcecf1;background:#08131d}
body{width:480px;height:360px;overflow:hidden}.thumbnail-stage{height:100%;padding:18px;background:radial-gradient(ellipse at 45% 48%,#17525c44,transparent 70%),linear-gradient(140deg,#102635,#0b1724);border:1px solid #355665;border-radius:14px;position:relative;display:flex;flex-direction:column;gap:4px}
.thumb-heading{margin:0;min-height:55px;flex:0 0 auto}.thumb-family{font-size:10px;letter-spacing:1.1px;text-transform:uppercase;color:#7acfc9;margin-bottom:7px}.thumb-heading h1{font-size:22px;line-height:1.2;letter-spacing:-.3px;margin:0;font-weight:650}
.thumb-art{display:flex;align-items:center;justify-content:center;flex:1;min-height:0;padding:7px 0 9px}.thumb-art>.scada-component{display:flex;width:330px;height:100%;max-height:220px;max-width:100%}.thumb-art>.scada-component[data-scada-host-state=false]>.twin-equipment-art{width:100%;height:100%;max-width:100%;max-height:100%}
.thumb-caption{flex:0 0 auto;display:flex;justify-content:space-between;gap:12px;font-size:11px;line-height:1.4;color:#9dbcc7}.thumb-caption strong{color:#bdeee6;font-weight:550}.thumb-caption code{font-size:10px;color:#7ca4b6}
.thumb-workspace{display:flex;align-items:center;justify-content:center;height:225px}.thumb-workspace>.scada-workspace{width:100%}.thumb-dialog-art{width:118px;height:78px;display:flex;align-items:center;justify-content:center}.thumb-dialog-art>.scada-component{width:100%;height:100%}.thumb-dialog-art .twin-equipment-art{width:100%!important;height:100%!important}.thumb-dialog-content{display:flex;align-items:center;justify-content:space-between;gap:18px}.thumb-dialog-control{display:grid;gap:6px;font-size:14px}.thumb-dialog-control span{color:#abc9d4}.thumb-dialog-control strong{font-size:22px;color:#7ff3d4}
.scada-dialog .scada-dialog-header{padding:15px 18px 12px}.scada-dialog .scada-dialog-body{padding:13px 18px}.scada-dialog .scada-dialog-footer{padding:10px 18px}.scada-dialog .scada-dialog-heading h2{font-size:22px}.scada-dialog .scada-dialog-heading p{font-size:12px;margin-top:5px}.scada-dialog{max-height:calc(100vh - 24px)!important}.scada-workspace{font-family:Arial,sans-serif}
*,*::before,*::after{transition:none!important}
'''
FIXTURE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCADA package thumbnail renderer</title><link rel="stylesheet" href="/software/cadagent/webkit/scada/ui/src/styles.css"><style>''' + STYLE + '''</style><main class="thumbnail-stage"></main><script type="module">
import {SCADA_COMPONENTS,SCADA_CATEGORIES,getScadaComponent,getScadaVariants,normalizeScadaState,renderScadaComponent} from '/software/cadagent/webkit/scada/ui/src/symbols/index.mjs';
import {ScadaWorkspace,renderScadaDialog,renderScadaToolbar} from '/software/cadagent/webkit/scada/ui/src/workspace/workspace.mjs';
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stage=document.querySelector('main');let workspace=null;
const heading=(family,label)=>`<header class="thumb-heading"><div class="thumb-family">${esc(family)}</div><h1>${esc(label)}</h1></header>`;
const caption=(label,id)=>`<footer class="thumb-caption"><strong>${esc(label)}</strong><code>${esc(id)}</code></footer>`;
function clean(){workspace?.destroy();workspace=null;}
window.thumbnailRegistry={components:SCADA_COMPONENTS,categories:SCADA_CATEGORIES,variants:SCADA_COMPONENTS.flatMap(component=>getScadaVariants(component.type).map(variant=>{const descriptor=getScadaComponent(component.type,{variant:variant.id});return {type:component.type,variant:variant.id,label:variant.label,componentLabel:descriptor.label,description:variant.description??descriptor.description,circuits:descriptor.circuits??[],ports:descriptor.ports,state:normalizeScadaState(component.type,{}, {variant:variant.id}),fuel:variant.fuel,enclosure:variant.enclosure}}))};
window.renderComponentThumbnail=({type,variant,state={},caption:customCaption})=>{
 clean();const options=variant?{variant}:{},descriptor=getScadaComponent(type,options),normalized=normalizeScadaState(type,{...descriptor.defaultState,...state},options),family=SCADA_CATEGORIES.find(item=>item.id===descriptor.category).label;
 const status=customCaption??(normalized.fault?'Fault preview':normalized.status==='warning'?'Warning preview':normalized.status==='offline'?'Offline preview':!normalized.active?'Inactive preview':!normalized.running?'Paused preview':'Active preview');
 stage.innerHTML=heading(family,variant?descriptor.label+' · '+descriptor.selectedVariant.label:descriptor.label)+`<div class="thumb-art">${renderScadaComponent(type,{id:'thumbnail-'+type,label:descriptor.label,...options,state:normalized})}</div>`+caption(status,variant?type+' / '+variant:type);
 return normalized;
};
window.renderWorkspaceThumbnail=kind=>{
 clean();let markup;
 if(kind==='toolbar')markup=renderScadaToolbar({label:'Example workspace toolbar',content:'<button class="scada-toolbutton is-primary">▸ Run</button><button class="scada-toolbutton">Equipment</button><button class="scada-toolbutton">Trends</button><button class="scada-toolbutton">Alarms <span class="scada-toolbadge" data-severity="warning">2</span></button>'});
 else if(kind==='buttons')markup='<div class="scada-actions"><button class="scada-toolbutton">Default</button><button class="scada-toolbutton is-primary">Primary</button><button class="scada-toolbutton" aria-pressed="true">Selected</button></div><div class="scada-actions"><button class="scada-toolbutton is-danger">Fault</button><button class="scada-toolbutton" disabled>Disabled</button></div><div class="scada-actions"><span>Warning <span class="scada-toolbadge" data-severity="warning">2</span></span><span>Critical <span class="scada-toolbadge" data-severity="critical">1</span></span></div>';
 else if(kind==='panels')markup='<section class="scada-panel-section"><h3>Equipment settings</h3><p class="scada-panel-note">Group related controls in a clear, bounded surface.</p><div class="scada-actions"><button class="scada-toolbutton is-primary">Apply</button><button class="scada-toolbutton">Reset</button></div></section>';
 else if(kind==='metrics')markup='<div class="scada-metric-strip"><div>Flow<strong>42.0</strong>m³/h · example</div><div>Pressure<strong>2.4</strong>bar · example</div><div>Load<strong>65</strong>% · example</div></div>';
 else if(kind==='statusbar')markup='<div class="scada-statusbar"><span><strong>System connected</strong><br>Illustrative status surface</span><span>Cycle <strong>120 ms</strong></span></div>';
 else markup=renderScadaToolbar({content:'<button class="scada-toolbutton" data-scada-open="equipment">Equipment controls</button>'})+renderScadaDialog({id:'equipment',scope:'thumbnail',title:'Feed pump',subtitle:'Reusable equipment dialog',kind:'equipment',body:`<div class="thumb-dialog-content"><div class="thumb-dialog-art">${renderScadaComponent('pump',{id:'thumbnail-dialog-pump',decorative:true})}</div><div class="thumb-dialog-control"><span>Illustrative speed</span><strong>65%</strong></div><button class="scada-toolbutton" aria-pressed="true">On</button></div>`,footer:'<button class="scada-toolbutton" data-scada-close>Close controls</button>'});
 const label={toolbar:'Workspace toolbar',statusbar:'Workspace status bar',dialog:'Equipment dialog',buttons:'Buttons & alarm badges',panels:'Panel & action groups',metrics:'Metric strip'}[kind];
 stage.innerHTML=heading('Workspace primitives',label)+`<div class="thumb-workspace"><section class="scada-workspace">${markup}</section></div>`+caption('Native package UI',{statusbar:'.scada-statusbar',toolbar:'renderScadaToolbar',dialog:'renderScadaDialog',buttons:'.scada-toolbutton',panels:'.scada-panel-section',metrics:'.scada-metric-strip'}[kind]);
 if(kind==='dialog'){workspace=new ScadaWorkspace(stage.querySelector('.scada-workspace'));workspace.open('equipment');}
};
window.thumbnailReady=true;
</script></html>'''


def serve(route):
    parsed = urlparse(route.request.url)
    if parsed.netloc != urlparse(BASE).netloc:
        raise AssertionError('Unexpected external thumbnail dependency: ' + route.request.url)
    if parsed.path == '/thumbnail.html':
        return route.fulfill(status=200, body=FIXTURE, content_type='text/html')
    name = unquote(parsed.path).lstrip('/')
    assert name.startswith('software/cadagent/webkit/scada/ui/'), 'Asset must belong to this package: ' + name
    path = (PACKAGE / name.removeprefix('software/cadagent/webkit/scada/ui/')).resolve()
    assert path.is_relative_to(PACKAGE), path
    assert path.is_file(), 'Missing canonical asset: ' + str(path)
    route.fulfill(status=200, body=path.read_bytes(), content_type='text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(path)[0] or 'application/octet-stream')


def image_info(path):
    data = path.read_bytes()
    assert path.suffix == '.jpg' and data[:3] == b'\xff\xd8\xff', path
    with Image.open(path) as image:
        assert image.format == 'JPEG', path
        width, height = image.size
        image.verify()
    return {'path': path.relative_to(PACKAGE).as_posix(), 'width': width, 'height': height,
            'format': 'jpeg', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def capture(page, path, locator=None):
    page.mouse.move(0, 0)
    freeze_animation_frame(page, FRAME_MS)
    assert page.evaluate('document.documentElement.scrollWidth') == page.viewport_size['width']
    if page.locator('.thumb-art').count():
        assert page.locator('.thumbnail-stage').evaluate('''stage=>{
          const header=stage.querySelector('.thumb-heading').getBoundingClientRect(),art=stage.querySelector('.thumb-art').getBoundingClientRect(),footer=stage.querySelector('.thumb-caption').getBoundingClientRect();
          return header.bottom<=art.top+1 && art.bottom<=footer.top+1 && footer.bottom<=stage.getBoundingClientRect().bottom-12;
        }'''), 'Thumbnail label, artwork and caption must not overlap.'
    path.parent.mkdir(parents=True, exist_ok=True)
    target=page.locator(locator) if locator else page
    target.screenshot(path=str(path), type='jpeg', quality=JPEG_QUALITY, animations='allow', caret='hide')
    return image_info(path)


def source_hashes():
    return {path.relative_to(PACKAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(list((PACKAGE / 'src').rglob('*')) + list((PACKAGE / 'examples').rglob('*')))
            if path.suffix in ('.mjs', '.css', '.html', '.json')}


def variant_map(registry, manifest):
    def safe(value):
        return html.escape(str(value), quote=True).replace('|', '&#124;').replace('\n', ' ')
    images={(entry['type'],entry['variant']):entry['path'] for entry in manifest['variants']}
    lines=['# Equipment variant previews', '',
           f"Generated from the canonical registry: **{len(registry['variants'])} explicit variants** across **{len(set(item['type'] for item in registry['variants']))} component types**. These supplement the **{len(registry['components'])} base equipment symbols** in the [main catalog](../README.md#equipment-catalog).", '',
           'Select a variant with `renderScadaComponent(type, { variant, state })` or the `variant` field of a system component. The [API](API.md) and [system format](SYSTEM_FORMAT.md) describe validation. Each preview records its exact normalized state in the [thumbnail manifest](../metadata/thumbnails.json).', '',
           'Variants may change the silhouette, supported fluid, ports or connection roles. A shared silhouette does not imply shared or mixed circuits. These declarations are presentation contracts; the external model supplies operating assumptions and state.', '',
           '| Preview | Type and variant | Meaning from the descriptor |',
           '| --- | --- | --- |']
    for item in registry['variants']:
        path='../'+images[(item['type'],item['variant'])]
        meaning=safe(item['description'])
        details=[]
        if item.get('fuel'):
            details.append('Fuel: '+safe(item['fuel'])+'.')
        if item.get('enclosure'):
            details.append('Form: '+safe(item['enclosure'])+'.')
        if item['circuits']:
            details.append('Circuits: '+ '; '.join(safe(circuit['id'])+' = '+safe(circuit.get('fluid','declared carrier')) for circuit in item['circuits'])+'.')
        details.append('Ports: '+ '; '.join(safe(port['id'])+' ('+safe(port['medium'])+', '+safe(port['direction'])+')' for port in item['ports'])+'.')
        lines.append(f'| <a href="{path}"><img src="{path}" alt="{safe(item["componentLabel"])} — {safe(item["label"])}" width="160"></a> | **{safe(item["label"])}**<br>`{safe(item["type"])}`<br>`{safe(item["variant"])}` | '+meaning+'<br><br>'+' '.join(details)+' |')
    lines += ['', 'Generated by `tools/webkit/scada/ui/generate-thumbnails.py` from canonical SVG in Chromium at JPEG quality 85. Do not edit this map or the images by hand.', '']
    return '\n'.join(lines)


def thumbnail_indexes(manifest, registry):
    entries = manifest['components'] + manifest['variants'] + manifest['workspace'] + manifest['states']
    entries += [{**manifest['contact_sheet'], 'label': 'All equipment contact sheet'}]
    if manifest.get('viewer'):
        entries.append({**manifest['viewer'], 'label': 'Generic shared-system viewer'})
    labels = {category['id']: category['label'] for category in registry['categories']}
    labels.update({item['type']: item['label'] for item in registry['components']})
    return asset_maps(entries, 'img/thumbnails', 'Static UI previews', labels)


def check_manifest(manifest, registry):
    assert manifest['source_hashes'] == source_hashes(), 'Canonical source changed; regenerate thumbnails.'
    assert manifest['generator']['sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Generator changed; regenerate thumbnails.'
    assert manifest['generator']['capture_helper_sha256'] == hashlib.sha256(CAPTURE_HELPER.read_bytes()).hexdigest(), 'Capture helper changed; regenerate thumbnails.'
    assert manifest['capture']['format'] == 'jpeg' and manifest['capture']['quality'] == JPEG_QUALITY
    assert manifest.get('viewer'), 'The standalone viewer thumbnail is required.'
    types = [component['type'] for component in registry['components']]
    assert [entry['type'] for entry in manifest['components']] == types
    assert len(set(entry['path'] for entry in manifest['components'])) == len(types)
    assert [(entry['type'],entry['variant']) for entry in manifest['variants']] == [(entry['type'],entry['variant']) for entry in registry['variants']]
    for entry,descriptor in zip(manifest['variants'],registry['variants']):
        assert entry['state'] == descriptor['state'], (entry['type'],entry['variant'],'default visual state')
    entries = manifest['components'] + manifest['variants'] + manifest['workspace'] + manifest['states'] + [manifest['contact_sheet']]
    if manifest.get('viewer'):
        entries.append(manifest['viewer'])
    for entry in entries:
        actual = image_info(PACKAGE / entry['path'])
        for key in ('width', 'height', 'format', 'bytes', 'sha256'):
            assert actual[key] == entry[key], (entry['path'], key)
        if entry in manifest['components'] + manifest['variants'] + manifest['workspace'] + manifest['states']:
            assert (entry['width'], entry['height']) == (WIDTH, HEIGHT)
    assert len({entry['path'] for entry in entries}) == len(entries)
    assert {path.relative_to(PACKAGE).as_posix() for path in THUMBS.rglob('*.jpg')} == {entry['path'] for entry in entries}, 'Unexpected or missing generated JPEG preview.'
    for path, data in thumbnail_indexes(manifest, registry).items():
        assert (PACKAGE / path).read_bytes() == data, 'Thumbnail folder map changed; regenerate: ' + path
    assert VARIANT_MAP.read_text() == variant_map(registry, manifest), 'Variant map changed; regenerate thumbnails.'
    assert {entry['id'] for entry in manifest['workspace']} == {'toolbar', 'dialog', 'statusbar', 'buttons', 'panels', 'metrics'}
    assert len(manifest['states']) == 6
    assert not list(THUMBS.rglob('*.png')), 'Distributed thumbnails must not retain duplicate PNG files.'


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox', '--disable-gpu', '--force-color-profile=srgb'])
    page = browser.new_page(viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=1, color_scheme='dark', reduced_motion='no-preference')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', serve)
    page.goto(BASE + '/thumbnail.html', wait_until='networkidle')
    page.wait_for_function('window.thumbnailReady')
    registry = page.evaluate('window.thumbnailRegistry')
    if args.check:
        check_manifest(json.loads(MANIFEST.read_text()), registry)
    else:
        THUMBS.mkdir(parents=True, exist_ok=True)
        manifest = {'format':'scada-ui-thumbnails','version':1,'package':'@valpatel/scada-ui',
                    'source':'src/index.mjs','source_hashes':source_hashes(),'generator':{'path':'tools/webkit/scada/ui/generate-thumbnails.py','sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'capture_helper_sha256':hashlib.sha256(CAPTURE_HELPER.read_bytes()).hexdigest()},'capture':{'renderer':'Chromium','format':'jpeg','quality':JPEG_QUALITY,'viewport':{'width':WIDTH,'height':HEIGHT},'device_scale_factor':1,'animation_frame_ms':FRAME_MS,'font':'Arial, sans-serif'},
                    'components':[], 'variants':[], 'workspace':[], 'states':[]}
        for descriptor in registry['components']:
            kind = descriptor['type']
            state = page.evaluate('options=>window.renderComponentThumbnail(options)', {'type':kind})
            info = capture(page, THUMBS / 'equipment' / descriptor['category'] / kind / 'default.jpg')
            manifest['components'].append({'type':kind,'label':descriptor['label'],'category':descriptor['category'],'state':state,**info})
        for descriptor in registry['variants']:
            kind,variant=descriptor['type'],descriptor['variant']
            state=page.evaluate('options=>window.renderComponentThumbnail(options)',{'type':kind,'variant':variant})
            category = next(item['category'] for item in registry['components'] if item['type'] == kind)
            info=capture(page,THUMBS/'equipment'/category/kind/(variant+'.jpg'))
            manifest['variants'].append({'type':kind,'variant':variant,'label':descriptor['label'],'componentLabel':descriptor['componentLabel'],'state':state,**info})
        for kind, exports in (('toolbar',['renderScadaToolbar']),('dialog',['renderScadaDialog','ScadaWorkspace']),('statusbar',[]),('buttons',[]),('panels',[]),('metrics',[])):
            page.evaluate('kind=>window.renderWorkspaceThumbnail(kind)', kind)
            if kind == 'toolbar':
                assert page.locator('.scada-toolbar').evaluate('el=>getComputedStyle(el).display') == 'flex', 'Toolbar CSS must work without an app-specific #main host.'
            if kind == 'statusbar':
                assert page.locator('.scada-statusbar').evaluate('el=>getComputedStyle(el).display') == 'flex', 'Statusbar CSS must work without an app-specific #main host.'
            if kind == 'dialog':
                assert page.locator('dialog').evaluate('el=>el.matches(":modal")')
            manifest['workspace'].append({'id':kind,'exports':exports,'css_class':{'toolbar':'.scada-toolbar','dialog':'.scada-dialog','statusbar':'.scada-statusbar','buttons':'.scada-toolbutton','panels':'.scada-panel-section','metrics':'.scada-metric-strip'}[kind],**capture(page,THUMBS / 'workspace' / (kind+'.jpg'))})
        examples = [('pump-running','pump',{},'Running'),('pump-stopped','pump',{'active':False,'running':False},'Stopped'),
                    ('tank-empty','tank',{'level':0},'Empty · illustrative level 0%'),('tank-full','tank',{'level':100},'Full · illustrative level 100%'),
                    ('plc-warning','plc-rack',{'status':'warning'},'Warning'),('plc-fault','plc-rack',{'fault':True},'Fault')]
        for name,kind,state,label in examples:
            normalized=page.evaluate('options=>window.renderComponentThumbnail(options)',{'type':kind,'state':state,'caption':label})
            manifest['states'].append({'id':name,'type':kind,'label':label,'state':normalized,**capture(page,THUMBS/'states'/(name+'.jpg'))})
        # A browser-rendered contact sheet uses the exact generated JPEG files.
        sheet_rows=math.ceil(len(manifest['components'])/5)
        sheet_height=math.ceil(sheet_rows*((1520-80-4*16)/5*.75)+(sheet_rows-1)*16+155)
        page.set_viewport_size({'width':1520,'height':sheet_height})
        cards=''.join('<img src="/software/cadagent/webkit/scada/ui/'+entry['path']+'" alt="'+entry['label']+'">' for entry in manifest['components'])
        sheet='''<!doctype html><meta charset="utf-8"><title>SCADA UI contact sheet</title><style>*{box-sizing:border-box}body{margin:0;background:#07131d;color:#dcecf1;font:16px Arial,sans-serif;padding:35px 40px}h1{margin:0 0 9px;font-size:30px}p{margin:0 0 27px;color:#8db7c1}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}img{display:block;width:100%;height:auto;border-radius:10px}</style><h1>SCADA UI · {len(manifest['components'])} reusable components</h1><p>Original SVG artwork · seven families · fixed animation frame · illustrative visual states</p><div class="grid">'''+cards+'</div>'
        sheet=sheet.replace("{len(manifest['components'])}",str(len(manifest['components']))).replace('seven families',str(len(registry['categories']))+' families')
        page.set_content(sheet)
        page.evaluate('async()=>Promise.all([...document.images].map(image=>image.decode()))')
        manifest['contact_sheet']=capture(page,THUMBS/'contact-sheet.jpg')
        if args.viewer_path:
            viewer_path=(PACKAGE/args.viewer_path).resolve()
            assert viewer_path.is_relative_to(PACKAGE) and viewer_path.is_file()
            page.set_viewport_size({'width':1280,'height':800})
            page.goto(BASE+'/software/cadagent/webkit/scada/ui/'+viewer_path.relative_to(PACKAGE).as_posix(),wait_until='networkidle')
            page.locator('#utility-viewer [data-scada-viewer]').wait_for(state='visible')
            page.evaluate("()=>{document.querySelector('[data-demo-action=reset]').click();document.querySelector('[data-demo-action=running]').click()}")
            assert page.locator('[data-demo-status]').inner_text().startswith('0 illustrative minutes · Paused')
            page.locator('#utility-viewer [data-scada-zoom=fit]').click()
            freeze_animation_frame(page, FRAME_MS)
            definition=json.loads(viewer_path.with_name('system.json').read_text())
            active_id=page.locator('#utility-viewer [data-scada-view-choice][aria-current=page]').get_attribute('data-scada-view-choice')
            active_view=next(view for view in definition['views'] if view['id']==active_id)
            coverage=fitted_camera_coverage(page,'#utility-viewer',[placement['component'] for placement in active_view['placements']],active_view['canvas'])
            manifest['viewer']={'id':'generic-viewer','entrypoint':viewer_path.relative_to(PACKAGE).as_posix(),'camera_coverage':coverage,**capture(page,THUMBS/'workspace'/'generic-viewer.jpg',locator='#utility-viewer')}
        # Remove obsolete generated previews after every replacement capture
        # succeeds. Reviewed originals remain in ignored work/.
        entries=manifest['components']+manifest['variants']+manifest['workspace']+manifest['states']+[manifest['contact_sheet']]
        if manifest.get('viewer'):
            entries.append(manifest['viewer'])
        expected_paths={entry['path'] for entry in entries}
        for obsolete in THUMBS.rglob('*'):
            if obsolete.suffix in ('.png','.jpg') and obsolete.relative_to(PACKAGE).as_posix() not in expected_paths:
                obsolete.unlink()
        indexes = thumbnail_indexes(manifest, registry)
        for obsolete in THUMBS.rglob('README.md'):
            if obsolete.relative_to(PACKAGE).as_posix() not in indexes:
                obsolete.unlink()
        for path, data in indexes.items():
            (PACKAGE / path).parent.mkdir(parents=True, exist_ok=True)
            (PACKAGE / path).write_bytes(data)
        for directory in sorted(THUMBS.rglob('*'), key=lambda path: len(path.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        MANIFEST.parent.mkdir(parents=True,exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        VARIANT_MAP.parent.mkdir(parents=True,exist_ok=True)
        VARIANT_MAP.write_text(variant_map(registry,manifest))
        check_manifest(manifest,registry)
    assert not errors, errors
    browser.close()
print(json.dumps({'checked':True,'generated':not args.check,'components':len(registry['components']),'variants':len(registry['variants']),'workspace':6,'state_examples':6,'manifest':str(MANIFEST.relative_to(PACKAGE)),'errors':errors}))
