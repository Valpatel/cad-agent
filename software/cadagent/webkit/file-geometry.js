// Plain data contract shared by cancellable parsers and the page. Coordinates are mm.
export const MAX_TRIANGLES = 2_000_000;
export const MAX_FILE_BYTES = 128 * 1024 * 1024;
export const UNITS_MM = Object.freeze({millimeter:1,centimeter:10,meter:1000,micron:.001,inch:25.4,foot:304.8});
export function validateSTL(bytes) {
  if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < 84) throw new Error('This file has no usable STL geometry.');
  const data=new Uint8Array(bytes),solid=[115,111,108,105,100],count=new DataView(bytes).getUint32(80,true);
  const binary=84+count*50===bytes.byteLength;
  // Match r160 STLLoader's exact classifier, before it allocates a binary face count.
  const ascii=[0,1,2,3,4].some(offset=>solid.every((value,index)=>data[offset+index]===value));
  if(!binary&&!ascii)throw new Error('The downloaded file is not valid STL data.');
  if(binary&&(count<1||count>MAX_TRIANGLES))throw new Error('The STL is empty or exceeds the preview triangle limit.');
}
export function normalizeMesh(source) {
  const positions=source.positions;
  if(!(Array.isArray(positions)||ArrayBuffer.isView(positions))||positions.length<9||positions.length%3||positions.length>MAX_TRIANGLES*9)throw new Error('A surface has an invalid vertex count.');
  if(!positions.every(Number.isFinite))throw new Error('A surface contains non-finite vertices.');
  const p=positions instanceof Float32Array?positions:new Float32Array(positions);
  if(!p.every(Number.isFinite))throw new Error('A surface contains out-of-range vertices.');
  let indices=null;
  if(source.indices){
    const a=source.indices;
    if(!(Array.isArray(a)||ArrayBuffer.isView(a))||!a.length||a.length%3||a.length>MAX_TRIANGLES*3||!a.every(i=>Number.isInteger(i)&&i>=0&&i<p.length/3))throw new Error('A surface has invalid triangle indices.');
    indices=a instanceof Uint32Array?a:new Uint32Array(a);
  }else if(p.length%9)throw new Error('A surface has incomplete triangles.');
  const total=indices?indices.length:p.length/3;
  let area=false;const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<p.length;i++){const axis=i%3;lo[axis]=Math.min(lo[axis],p[i]);hi[axis]=Math.max(hi[axis],p[i]);}
  for(let i=0;i<total&&!area;i+=3){
    const a=(indices?indices[i]:i)*3,b=(indices?indices[i+1]:i+1)*3,c=(indices?indices[i+2]:i+2)*3;
    const u=[p[b]-p[a],p[b+1]-p[a+1],p[b+2]-p[a+2]],v=[p[c]-p[a],p[c+1]-p[a+1],p[c+2]-p[a+2]];
    area=Math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])>0;
  }
  if(!area)throw new Error('The file contains no non-degenerate surface triangles.');
  const normals=source.normals?new Float32Array(source.normals):null,colors=source.colors?new Float32Array(source.colors):null;
  if(normals&&(normals.length!==p.length||!normals.every(Number.isFinite)))throw new Error('A surface has invalid normals.');
  if(colors&&(colors.length!==p.length||!colors.every(n=>Number.isFinite(n)&&n>=0&&n<=1)))throw new Error('A surface has invalid vertex colors.');
  const materials=source.materials||[{color:[.68,.73,.77],opacity:1}];
  if(!materials.length||!materials.every(m=>Array.isArray(m.color)&&m.color.length===3&&m.color.every(n=>Number.isFinite(n)&&n>=0&&n<=1)&&Number.isFinite(m.opacity)&&m.opacity>=0&&m.opacity<=1))throw new Error('A surface has invalid material data.');
  const groups=source.groups||[];
  if(!groups.every(g=>Number.isInteger(g.start)&&Number.isInteger(g.count)&&g.start>=0&&g.count>0&&g.start%3===0&&g.count%3===0&&g.start+g.count<=total&&Number.isInteger(g.materialIndex)&&g.materialIndex>=0&&g.materialIndex<materials.length))throw new Error('A surface has invalid material groups.');
  return {name:String(source.name||'Surface'),positions:p,indices,normals,colors,materials,groups,bounds:[...lo,...hi],triangles:total/3};
}
export function validateModel(model) {
  if(!model||!Array.isArray(model.meshes)||!model.meshes.length)throw new Error('The file contains no displayable surfaces.');
  model.meshes=model.meshes.map(normalizeMesh);
  const triangles=model.meshes.reduce((sum,m)=>sum+m.triangles,0);
  if(triangles>MAX_TRIANGLES)throw new Error('This model exceeds the two-million-triangle preview limit. Download the original to inspect it in a desktop CAD tool.');
  return {...model,triangles,warnings:Array.isArray(model.warnings)?model.warnings.map(String):[]};
}
export function transferBuffers(model) {
  return [...new Set(model.meshes.flatMap(m=>['positions','indices','normals','colors'].flatMap(key=>m[key]?[m[key].buffer]:[])))];
}
