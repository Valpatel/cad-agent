"""Pack captured J501 assembly STLs plus incorporated original antenna context; no CAD rebuild.
Run: PYTHONPATH=software python tools/site/figures/pack-j501.py <captured-checkout> <antenna-checkout> <incorporated-main>
The two clean inputs remain read-only. Render-only simplification never changes product geometry.
"""
from pathlib import Path
import hashlib,json,math,subprocess,sys,tempfile
import numpy as np
from cadagent.publish.view import _read_stl,_write_stl,pack_view
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(product,*args):return subprocess.check_output(['git','-C',str(product),*args])
def css_rgb(rgb):
 if not isinstance(rgb,(list,tuple)) or len(rgb)!=3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in rgb):raise RuntimeError('Expected three finite normalized RGB channels')
 return '#'+''.join(f'{round(v*255):02x}' for v in rgb)
def collect(product,accessories,main):
 revision=git(product,'rev-parse','HEAD').decode().strip()
 for checkout in [product,accessories]:
  if git(checkout,'status','--porcelain').strip():raise RuntimeError('Input checkout must be clean')
 # A full immutable main identity and ancestry bind the optional recipe to delivered product source.
 if len(main)!=40 or git(accessories,'rev-parse',main).decode().strip()!=main:raise RuntimeError('Exact incorporated main required')
 subprocess.run(['git','-C',str(accessories),'merge-base','--is-ancestor','HEAD',main],check=True)
 cad_tree=git(product,'rev-parse',revision+':cad').decode().strip()
 if cad_tree!=git(accessories,'rev-parse',main+':cad').decode().strip():raise RuntimeError('Captured CAD inputs differ from incorporated main')
 antenna_manifest=accessories/'exports/showcase-antennas/manifest.json';antenna=json.loads(antenna_manifest.read_bytes())
 for source,digest in antenna['source_sha256'].items():
  if hashlib.sha256(git(accessories,'show',main+':'+source)).hexdigest()!=digest:raise RuntimeError('Antenna source does not match incorporated main: '+source)
 manifest=product/'exports/view/view.json';data=json.loads(manifest.read_bytes());parts=[];inputs={};derived={};cell=.4
 board_file=product/'references/hardware/carrier-full.stl'
 board_source=_read_stl(board_file); board_export=_read_stl(manifest.parent/'carrier_board.stl')
 if board_source.shape != board_export.shape or not np.allclose(board_source+np.array([15,15,20]), board_export, rtol=0, atol=2e-5):raise RuntimeError('Carrier board differs from real source at configured assembly offset')
 selected=[(p,manifest.parent/p['file'],'captured-view') for p in data['parts'] if p.get('visible') is not False and p['name']!='agx_module']
 for p in antenna['parts']:
  f=antenna_manifest.parent/p['file']
  if sha(f)!=p['sha256']:raise RuntimeError('Antenna mesh hash mismatch')
  q=dict(p);q['bounds_mm']=np.array(p['bounds_mm']).reshape(-1).tolist();q['explode']=[-1,0,0]
  q['color']=css_rgb(p['color'])  # Shared viewer consumes CSS colors, not numeric arrays; raw source retained below.
  selected.append((q,f,'incorporated-original-context'))
 with tempfile.TemporaryDirectory(prefix='cad-j501-pack-') as tmp:
  tmp=Path(tmp)
  for p,f,context in selected:
   tri=_read_stl(f);v=tri.reshape(-1,3);keys=np.floor(v/cell).astype(np.int64);_,inverse=np.unique(keys,axis=0,return_inverse=True);n=int(inverse.max())+1
   centres=np.zeros((n,3));counts=np.bincount(inverse);np.add.at(centres,inverse,v);centres/=counts[:,None];faces=inverse.reshape(-1,3);keep=(faces[:,0]!=faces[:,1])&(faces[:,1]!=faces[:,2])&(faces[:,0]!=faces[:,2]);reduced=centres[faces[keep]]
   q=dict(p);q['visible']=True;parts.append(q);_write_stl(tmp/p['file'],reduced)
   inputs[context+'/'+p['file']]={'sha256':sha(f),'bytes':f.stat().st_size}
   derived[p['name']]={'original_triangles':len(tri),'display_triangles':len(reduced),'max_vertex_move_mm':float(np.linalg.norm(centres[inverse]-v,axis=1).max()),'source_bounds_mm':p['bounds_mm']}
  if not any(p['name']=='carrier_board' for p in parts):raise RuntimeError('Real carrier board missing')
  source={'repo':'https://github.com/mvalancy/j501-agx-orin','revision':main,'captured_geometry_revision':revision,'cad_tree':cad_tree,'collection_context':'Legacy captured assembly meshes have no embedded export producer revision. Their CAD source tree equals incorporated main; no new CAD regeneration claimed. Optional antenna context generated separately by the incorporated source recipe.', 'generator':{'file':'tools/site/figures/pack-j501.py','sha256':sha(Path(__file__))},'board_geometry_check':{'source':'references/hardware/carrier-full.stl','sha256':sha(board_file),'offset_mm':[15,15,20],'max_allowed_coordinate_difference_mm':2e-5},'manifest':{'file':'exports/view/view.json','sha256':sha(manifest)},'inputs':inputs,'display_only':{'method':'0.4 mm vertex-cell centroid clustering; degenerate display triangles omitted','limits':'Render-only simplification, not dimension or fit evidence; lid fitted initially; use Explode to inspect the real board. Original optional antenna shapes are not RF, purchase, manufacturing or physical-fit evidence.','parts':derived},'board_reference':json.loads((ROOT/'tools/site/assets/models/j501-board-source.json').read_bytes()),'omitted_parts':{'agx_module':'Separate NVIDIA vendor mesh omitted: no independent redistribution basis established.'},'antenna_context':{'manifest_sha256':sha(antenna_manifest),'manifest':antenna}}
  (tmp/'view.json').write_text(json.dumps({**data,'parts':parts}))
  out=ROOT/'tools/site/assets/models/j501';m=pack_view(tmp/'view.json',out,source=source,view={'azimuth':-35,'elevation':38})
  (out.parent/'j501-source.json').write_text(json.dumps({'source':source,'model_sha256':sha(out.with_suffix('.json')),'binary_sha256':m['sha256'],'triangles':m['triangles'],'bytes':m['bytes']},indent=2)+'\n')
  print(json.dumps({'parts':len(m['parts']),'triangles':m['triangles'],'compressed_bytes':m['bytes'],'revision':main,'captured_geometry_revision':revision}))
if __name__=='__main__':collect(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),sys.argv[3])
