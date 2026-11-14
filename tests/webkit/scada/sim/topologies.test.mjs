import {SIM, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=SIM;
function python(source){
  const result=spawnSync('python',['-c',source],{cwd:root,encoding:'utf8'});
  assert.ifError(result.error);
  assert.equal(result.status,0,result.stderr||result.stdout);
}
const setup=`import sys,json,copy,importlib.util
from pathlib import Path
package=Path('.')
tools=Path(${JSON.stringify(TOOLS)})
sys.path.insert(0,str(tools/'sim/topology'))
from layout import layout,validate_layout
`;
test('every scenario topology preserves routed identities and avoids cards, shared lines and crossings',()=>python(setup+`
for entry in json.loads((package/'scenarios/index.json').read_text())['scenarios']:
 system=json.loads((package/'scenarios'/entry['system']).read_text())
 for height in [132,150,168]:
  graph=layout(system,node_height=height)
  report=validate_layout(graph,system)
  assert not report['crossings'],entry['id']
`));
test('topology validation rejects a changed connection and a route entering equipment',()=>python(setup+`
system=json.loads((package/'scenarios/winery/system.json').read_text())
graph=layout(system)
changed=copy.deepcopy(graph)
changed['routes'][0]['to']['component']='aging'
try:validate_layout(changed,system)
except AssertionError:pass
else:raise AssertionError('Changed endpoint was accepted')
changed=copy.deepcopy(graph)
node=changed['nodes'][1]
changed['routes'][0]['points'][-1]={'x':node['x']+20,'y':node['y']+20}
try:validate_layout(changed,system)
except AssertionError:pass
else:raise AssertionError('Route entering a card was accepted')
`));
test('topology SVG validation rejects active content, raster images and external styling',()=>python(setup+`
spec=importlib.util.spec_from_file_location('topology_generator',tools/'sim/generate-topologies.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for content in ['<script/>','<image href="data:image/png;base64,x"/>','<foreignObject/>','<animate/>','<rect style="fill:url(data:image/png;base64,x)"/>']:
 try:module.validate_svg('<svg xmlns="http://www.w3.org/2000/svg">'+content+'</svg>',[],[])
 except AssertionError:pass
 else:raise AssertionError('Unsupported SVG content was accepted: '+content)
`));
test('scenario gallery paths are safe, deterministic and reject sector collisions',()=>python(setup+`
sys.path.insert(0,str(tools))
from scada_paths import scenario_asset_path,scenario_sector_groups
assert scenario_asset_path('thumbnails',{'id':'demo','sector':None})=='img/thumbnails/uncategorized/demo/preview.jpg'
assert scenario_asset_path('topologies',{'id':'demo','sector':' Water & utilities '})=='img/topologies/water-utilities/demo/topology.svg'
for entries in [[{'id':'a','sector':'A + B'},{'id':'b','sector':'A B'}],[{'id':'a','sector':'é'},{'id':'b','sector':'e'}]]:
 try:scenario_sector_groups(entries)
 except ValueError:pass
 else:raise AssertionError('Ambiguous sector folders were accepted')
for identifier in ['../outside','/outside','a/b','UPPER']:
 try:scenario_asset_path('topologies',{'id':identifier})
 except ValueError:pass
 else:raise AssertionError('Unsafe scenario path was accepted')
`));
test('generated gallery paths resolve through sector and scenario maps without flat aliases',()=>python(setup+`
sys.path.insert(0,str(tools))
from scada_paths import scenario_asset_path
for kind in ['topologies','thumbnails']:
 manifest=json.loads((package/'metadata'/f'{kind}.json').read_text())
 for entry in manifest['scenarios']:
  assert entry['path']==scenario_asset_path(kind,entry),entry['id']
  image=package/entry['path']
  assert image.is_file()
  assert (image.parent/'README.md').is_file()
  assert (image.parent.parent/'README.md').is_file()
  assert not (package/'img'/kind/(entry['id']+image.suffix)).exists()
 for folder in [package/'img'/kind,*[p for p in (package/'img'/kind).rglob('*') if p.is_dir()]]:
  assert (folder/'README.md').is_file(),str(folder)
  assert len([p for p in folder.iterdir() if p.is_file()])<=20,str(folder)
`));
