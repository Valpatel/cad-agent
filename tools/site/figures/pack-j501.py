"""Pack existing J501 assembly-coordinate STL outputs; no CAD rebuild or source writes.
Run: PYTHONPATH=software python tools/site/figures/pack-j501.py <clean-j501-checkout>
Render-only vertex clustering is explicit; manufactured geometry stays in the product.
"""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile
import numpy as np
from cadagent.publish.view import _read_stl,_write_stl,pack_view
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def collect(product):
 revision=subprocess.check_output(['git','-C',str(product),'rev-parse','HEAD'],text=True).strip()
 if subprocess.check_output(['git','-C',str(product),'status','--porcelain'],text=True).strip():raise RuntimeError('Product checkout must be clean')
 manifest=product/'exports/view/view.json';data=json.loads(manifest.read_bytes());parts=[];inputs={};derived={};cell=.4
 with tempfile.TemporaryDirectory(prefix='cad-j501-pack-') as tmp:
  tmp=Path(tmp)
  for p in data['parts']:
   if p.get('visible') is False:continue
   f=manifest.parent/p['file'];tri=_read_stl(f);v=tri.reshape(-1,3);keys=np.floor(v/cell).astype(np.int64);_,inverse=np.unique(keys,axis=0,return_inverse=True);n=int(inverse.max())+1
   centres=np.zeros((n,3));counts=np.bincount(inverse);np.add.at(centres,inverse,v);centres/=counts[:,None];faces=inverse.reshape(-1,3);keep=(faces[:,0]!=faces[:,1])&(faces[:,1]!=faces[:,2])&(faces[:,0]!=faces[:,2]);reduced=centres[faces[keep]]
   q=dict(p);q['visible']=p['name']!='cover';parts.append(q);_write_stl(tmp/p['file'],reduced)
   inputs[str(f.relative_to(product))]={'sha256':sha(f),'bytes':f.stat().st_size}
   derived[p['name']]={'original_triangles':len(tri),'display_triangles':len(reduced),'max_vertex_move_mm':float(np.linalg.norm(centres[inverse]-v,axis=1).max()),'source_bounds_mm':p['bounds_mm']}
  if not any(p['name']=='carrier_board' for p in parts):raise RuntimeError('Real carrier board missing')
  source={'repo':'https://github.com/mvalancy/j501-agx-orin','revision':revision,'manifest':{'file':'exports/view/view.json','sha256':sha(manifest)},'inputs':inputs,'display_only':{'method':'0.4 mm vertex-cell centroid clustering; degenerate display triangles omitted','limits':'Render-only simplification, not dimension or fit evidence; lid hidden initially to reveal board. No CAD reconstruction.','parts':derived},'board_reference':json.loads((product/'references/sources.json').read_bytes())[0]}
  (tmp/'view.json').write_text(json.dumps({**data,'parts':parts}))
  out=ROOT/'tools/site/assets/models/j501';m=pack_view(tmp/'view.json',out,source=source,view={'azimuth':35,'elevation':38})
  (out.parent/'j501-source.json').write_text(json.dumps({'source':source,'model_sha256':sha(out.with_suffix('.json')),'binary_sha256':m['sha256'],'triangles':m['triangles'],'bytes':m['bytes']},indent=2)+'\n')
  print(json.dumps({'parts':len(m['parts']),'triangles':m['triangles'],'compressed_bytes':m['bytes'],'revision':revision}))
if __name__=='__main__':collect(Path(sys.argv[1]).resolve())
