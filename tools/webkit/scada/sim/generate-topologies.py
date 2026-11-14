"""Generate compact static scenario process maps using canonical UI symbols.

This is a developer-only dependency on the sibling UI library. The model runtime
remains headless. SVGs describe the selected first view, never sampled telemetry.
"""
import argparse
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS, scenario_asset_path, scenario_sector_groups
sys.path.insert(0, str(TOOLS / "explorer"))
from scenario_gallery_docs import asset_gallery_maps
import re
import shutil
import sys
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

PACKAGE = SIM

SUPPORT = Path(__file__).resolve().parent / 'topology'
sys.path.insert(0, str(SUPPORT))
from layout import layout, validate_layout

BASE = 'https://topology-export.test'
FORMAT = 'scada-scenario-topologies'
COLORS = {'solids': '#dfbc78', 'fluid': '#63ded6', 'liquid': '#63ded6',
          'product': '#b0baff', 'electricity': '#ffd16d', 'gas': '#fbab7b',
          'air': '#a3d8ed', 'steam': '#e6eaf4', 'measurement': '#d1a1ee',
          'data': '#c894e3', 'heat': '#ff8e8e', 'mechanical': '#a3d397',
          'chemical': '#dca8f2', 'thermal-fluid': '#ff8f9f', 'material': '#c0d69a',
          'optical': '#8ab4ff', 'slurry': '#b9a788'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def catalog():
    return json.loads((PACKAGE / 'scenarios/index.json').read_text())['scenarios']


def source_hashes():
    paths = [PACKAGE / 'scenarios/index.json', Path(__file__).resolve(), TOOLS / 'scada_paths.py', TOOLS / 'explorer/scenario_gallery_docs.py']
    paths += [PACKAGE / 'scenarios' / entry['system'] for entry in catalog()]
    paths += [p for p in SUPPORT.rglob('*') if p.suffix in ('.py', '.mjs')]
    paths += [p for p in (REPO / 'software/cadagent/webkit/scada/ui/src').rglob('*') if p.is_file() and p.suffix != '.md']
    return {p.relative_to(REPO).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}


def selection(entry):
    system = json.loads((PACKAGE / 'scenarios' / entry['system']).read_text())
    view = system['views'][0]
    components = {component['id']: component for component in system['components']}
    connections = {connection['id']: connection for connection in system['connections']}
    nodes = [components[placement['component']] for placement in view['placements']]
    edges = [connections[route['connection']] for route in view['routes']]
    assert all(edge['medium'] in COLORS for edge in edges), 'Define an explicit topology color for each new medium'
    ids = {node['id'] for node in nodes}
    assert len(ids) == len(nodes)
    assert all(edge[end]['component'] in ids for edge in edges for end in ('from', 'to'))
    return system, view, nodes, edges


def text(x, y, value, size=14, **attributes):
    attrs = {'x': x, 'y': y, 'font-size': size, **attributes}
    return '<text ' + ' '.join(f'{name}="{html.escape(str(value), quote=True)}"' for name, value in attrs.items()) + '>' + html.escape(str(value)) + '</text>'


def render(entry, icons, labels):
    system, view, components, edges = selection(entry)
    node_height = 132 + max(0, max(len(labels[node['id']]) for node in components) - 2) * 18
    graph = layout(system, view, node_height=node_height)
    assert not validate_layout(graph, system, view)['crossings'], 'Crossed routes require an explicit layout review'
    nodes = {node['id']: node for node in graph['nodes']}
    bottom = max([node['y'] + node['height'] for node in graph['nodes']] +
                 [point['y'] for route in graph['routes'] for point in route['points']])
    width, height = 900, bottom + 58
    title = system['system']['label']
    description = f"{view['label']}. {len(components)} equipment references and {len(edges)} declared directed connections. Static illustrative symbols; arrows do not show instantaneous flow. This selected view does not include every plant connection."
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="topology-title topology-description">',
             '<title id="topology-title">' + html.escape(title + ' — ' + view['label']) + '</title>',
             '<desc id="topology-description">' + html.escape(description) + '</desc>',
             f'<rect width="{width}" height="{height}" rx="20" fill="#091824"/>',
             '<style>text{font-family:Arial,sans-serif;fill:#dcecf1}.topology-edge{stroke-linejoin:round;stroke-linecap:round}</style>',
             text(26, 35, title, 25, **{'font-weight': 700, 'data-heading': 'true'}),
             text(26, 59, view['label'] + ' · declared connections · illustrative equipment symbols', 14)]
    routes = {route['id']: route for route in graph['routes']}
    for index, edge in enumerate(edges):
        route = routes[edge['id']]
        color = COLORS.get(edge['medium'], '#a3cad8')
        arrow = 'arrow-' + str(index)
        points = route['points']
        path = 'M' + 'L'.join(f'{point["x"]} {point["y"]}' for point in points)
        identity = edge['from']['component'] + ':' + edge['from']['port'] + ' → ' + edge['to']['component'] + ':' + edge['to']['port'] + ' (' + edge['medium'] + ')'
        parts += [f'<defs><marker id="{arrow}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 1L8 5L0 9Z" fill="{color}"/></marker></defs>',
                  f'<g data-edge="{html.escape(edge["id"], quote=True)}"><title>{html.escape(identity)}</title>',
                  f'<path class="topology-edge" d="{path}" fill="none" stroke="#091824" stroke-width="7"/>',
                  f'<path class="topology-edge" d="{path}" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#{arrow})"/></g>']
    for component in components:
        node = nodes[component['id']]
        identifier = html.escape(component['id'], quote=True)
        parts += [f'<g data-node="{identifier}" transform="translate({node["x"]} {node["y"]})"><title>{html.escape(component["label"] + " — " + component["id"] + " / " + component["type"])}</title>',
                  f'<rect width="180" height="{node_height}" rx="12" fill="#102735" stroke="#315363"/>',
                  f'<g transform="translate(36 0) scale(.6)">{icons[component["id"]]}</g>']
        for index, line in enumerate(labels[component['id']]):
            parts.append(text(90, 98 + index * 18, line, 14, **{'text-anchor': 'middle', 'font-weight': 600, 'data-label': component['id']}))
        parts.append('</g>')
    legend_x = 26
    for medium in sorted({edge['medium'] for edge in edges}):
        color = COLORS.get(medium, '#a3cad8')
        parts.append(f'<path d="M{legend_x} {bottom+19}h20" stroke="{color}" stroke-width="3"/>')
        parts.append(text(legend_x+28, bottom+24, medium, 14))
        legend_x += 42 + len(medium) * 8
    parts.append(text(26, bottom + 46, 'Arrows show declared direction, not instantaneous flow. Open the shared model for live state.', 13))
    parts.append('</svg>')
    svg = '\n'.join(line.rstrip() for part in parts for line in part.splitlines()) + '\n'
    validate_svg(svg, [node['id'] for node in components], [edge['id'] for edge in edges])
    record = {'id': entry['id'], 'title': title, 'sector': entry['sector'], 'view': view['id'],
              'system': entry['system'], 'path': scenario_asset_path('topologies', entry),
              'width': width, 'height': height, 'nodes': [{'id': node['id'], 'type': node['type'], 'variant': node.get('variant'), 'label': node['label']} for node in components],
              'edges': [{'id': edge['id'], 'from': edge['from'], 'to': edge['to'], 'medium': edge['medium']} for edge in edges],
              'layout': graph, 'bytes': len(svg.encode()), 'sha256': digest(svg.encode())}
    return svg, record


def validate_svg(svg, node_ids, edge_ids):
    root = ET.fromstring(svg)
    all_ids = []
    for element in root.iter():
        name = element.tag.split('}')[-1]
        assert name not in {'script', 'foreignObject', 'image', 'animate', 'animateTransform', 'animateMotion', 'set'}, name
        all_ids += [element.attrib['id']] if 'id' in element.attrib else []
        assert not any(key.lower().startswith('on') for key in element.attrib)
        assert not any(key.split('}')[-1] in {'href', 'src'} and not value.startswith('#') for key, value in element.attrib.items())
    assert len(all_ids) == len(set(all_ids)), 'Duplicate SVG definition IDs'
    assert [e.get('data-node') for e in root.iter() if e.get('data-node')] == node_ids
    assert [e.get('data-edge') for e in root.iter() if e.get('data-edge')] == edge_ids
    assert 'https:' not in svg and 'http:' not in svg.replace('http://www.w3.org/2000/svg', ''), 'External SVG resource'
    assert '@import' not in svg and '@font-face' not in svg
    references = re.findall(r'url\(\s*[\"\']?([^\"\'\)]+)', html.unescape(svg))
    assert all(reference.startswith('#') and reference[1:] in all_ids for reference in references), 'Nonlocal or unresolved SVG style resource'


def gallery_index(records):
    return asset_gallery_maps(records, 'topologies')['img/topologies/README.md']


def check(target):
    manifest = json.loads((target / 'metadata/topologies.json').read_text())
    assert manifest['format'] == FORMAT and manifest['version'] == 1
    assert manifest['source_hashes'] == source_hashes(), 'Topology sources changed; run npm --prefix tools/webkit/scada run topologies:generate'
    assert [record['id'] for record in manifest['scenarios']] == [entry['id'] for entry in catalog()]
    for entry, record in zip(catalog(), manifest['scenarios']):
        system, view, nodes, edges = selection(entry)
        assert not validate_layout(record['layout'], system, view)['crossings']
        assert record['view'] == view['id']
        assert record['nodes'] == [{'id': node['id'], 'type': node['type'], 'variant': node.get('variant'), 'label': node['label']} for node in nodes]
        assert record['edges'] == [{'id': edge['id'], 'from': edge['from'], 'to': edge['to'], 'medium': edge['medium']} for edge in edges]
        data = (target / record['path']).read_bytes()
        assert record['sha256'] == digest(data) and record['bytes'] == len(data)
        validate_svg(data.decode(), [node['id'] for node in nodes], [edge['id'] for edge in edges])
    for name, content in asset_gallery_maps(manifest['scenarios'], 'topologies').items():
        assert (target / name).read_text() == content, name
    actual = {p.relative_to(target).as_posix() for p in (target / 'img/topologies').rglob('*') if p.is_file()}
    assert actual == set(manifest['outputs'])
    for path, expected in manifest['outputs'].items():
        assert digest((target / path).read_bytes()) == expected
    print(json.dumps({'checked': len(manifest['scenarios']), 'files': len(actual)}))


def generate(target, only=None):
    from playwright.sync_api import sync_playwright
    scenario_sector_groups(catalog())
    initial = source_hashes()
    files, records, errors = {}, [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 900, 'height': 800})
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            parsed = urlparse(route.request.url)
            if parsed.netloc != urlparse(BASE).netloc:
                return route.abort()
            if parsed.path == '/index.html':
                return route.fulfill(content_type='text/html', body='<link rel="stylesheet" href="/software/cadagent/webkit/scada/ui/src/styles.css"><style>*{animation:none!important;transition:none!important}</style><script type="module">import{exportSymbol}from"/tools/webkit/scada/sim/topology/symbol-exporter.mjs";window.exportSymbol=exportSymbol</script>')
            path = (REPO / unquote(parsed.path).lstrip('/')).resolve()
            if not path.is_relative_to(REPO) or not path.is_file():
                return route.fulfill(status=404, body='Missing canonical dependency')
            return route.fulfill(body=path.read_bytes(), content_type='text/javascript' if path.suffix == '.mjs' else mimetypes.guess_type(path)[0] or 'application/octet-stream')
        page.route('**/*', serve)
        page.goto(BASE + '/index.html')
        page.wait_for_function('!!window.exportSymbol')
        for entry in catalog():
            if only and entry['id'] != only:
                continue
            _, _, nodes, _ = selection(entry)
            icons, labels = {}, {}
            for node in nodes:
                icons[node['id']] = page.evaluate('({type,variant,id})=>exportSymbol(type,variant,id)', {'type': node['type'], 'variant': node.get('variant'), 'id': 'topology-' + entry['id'] + '-' + node['id']})
                labels[node['id']] = page.evaluate('''label=>{const canvas=document.createElement('canvas');const ctx=canvas.getContext('2d');ctx.font='600 14px Arial';const lines=[''];for(const word of label.split(/\\s+/)){let joined=(lines.at(-1)+' '+word).trim();if(ctx.measureText(joined).width>160&&lines.at(-1))lines.push(word);else lines[lines.length-1]=joined;}if(lines.some(line=>ctx.measureText(line).width>160))throw Error('Unbreakable equipment label: '+label);return lines;}''', node['label'])
            svg, record = render(entry, icons, labels)
            files[record['path']] = svg.encode()
            records.append(record)
        assert records and not errors, errors
        browser_version = browser.version
        browser.close()
    files.update({name: content.encode() for name, content in asset_gallery_maps(records, 'topologies').items()})
    manifest = {'format': FORMAT, 'version': 1, 'purpose': 'Static declared first-view topology, not instantaneous flow or sampled simulation state.',
                'icon_state': {'active': True, 'running': False, 'status': 'normal', 'fault': False, 'damage': 'none', 'unspecified_fields': 'Canonical UI descriptor defaults; illustrative appearance only.'},
                'browser': browser_version, 'source_hashes': initial, 'scenarios': records,
                'outputs': {name: digest(data) for name, data in sorted(files.items())}}
    assert initial == source_hashes(), 'Topology sources changed during generation; no outputs written'
    files['metadata/topologies.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    for name in files:
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert name == 'metadata/topologies.json' or name.startswith('img/topologies/')
        path = target / relative
        assert all(not ancestor.is_symlink() for ancestor in [path, *path.parents]), 'Output symlink rejected'
        assert not path.exists() or path.is_file(), 'Output file path is a directory'
        assert all(not ancestor.exists() or ancestor.is_dir() for ancestor in path.parents), 'Output directory path is a file'
    owned = target / 'img/topologies'
    previous_manifest = target / 'metadata/topologies.json'
    previous_outputs = set(json.loads(previous_manifest.read_text()).get('outputs', {})) if previous_manifest.exists() else set()
    if owned.exists():
        actual = {path.relative_to(target).as_posix() for path in owned.rglob('*') if path.is_file()}
        assert actual <= previous_outputs | set(files), 'Unowned files in topology gallery'
        assert not any(path.is_symlink() for path in owned.rglob('*')), 'Output symlink rejected'
        for name in previous_outputs - set(files):
            if not name.startswith('img/topologies/') or '..' in Path(name).parts:
                raise ValueError('Unsafe previous output claim')
            (target / name).unlink(missing_ok=True)
        for directory in sorted((path for path in owned.rglob('*') if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps({'generated': len(records), 'svg_bytes': sum(record['bytes'] for record in records), 'output': str(target)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, default=PACKAGE)
    parser.add_argument('--scenario', help='Preview one scenario only in an explicit separate output directory')
    args = parser.parse_args()
    if args.scenario and (args.output.absolute() == PACKAGE or args.check):
        parser.error('--scenario requires a separate --output and cannot be checked as the complete catalog')
    if args.check:
        check(args.output.absolute())
    else:
        generate(args.output.absolute(), args.scenario)
