import {validateSTL,validateModel,transferBuffers,UNITS_MM,MAX_FILE_BYTES} from './file-geometry.js';
const asset=path=>{const url=new URL(path,import.meta.url);url.search=new URL(import.meta.url).search;return url.href;};
function zipBudget(bytes){
  const d=new DataView(bytes);let end=-1;
  for(let at=d.byteLength-22;at>=Math.max(0,d.byteLength-65557);at--)if(d.getUint32(at,true)===0x06054b50&&at+22+d.getUint16(at+20,true)===d.byteLength){end=at;break;}
  if(end<0)throw new Error('The downloaded file is not a readable 3MF ZIP archive.');
  const count=d.getUint16(end+10,true),size=d.getUint32(end+12,true),start=d.getUint32(end+16,true);
  if(!count||count>10000||d.getUint16(end+4,true)||d.getUint16(end+6,true)||count!==d.getUint16(end+8,true)||start+size!==end)throw new Error('This 3MF uses an unsupported ZIP layout.');
  let at=start,expanded=0;
  for(let i=0;i<count;i++){
    if(at+46>end||d.getUint32(at,true)!==0x02014b50)throw new Error('The 3MF ZIP directory is damaged.');
    const length=d.getUint32(at+24,true);expanded+=length;
    if(length===0xffffffff||expanded>MAX_FILE_BYTES)throw new Error('This 3MF archive exceeds the preview expansion limit.');
    at+=46+d.getUint16(at+28,true)+d.getUint16(at+30,true)+d.getUint16(at+32,true);
  }
  if(at!==end)throw new Error('The 3MF ZIP directory is damaged.');
}
function materialData(material){return{color:material.color?.toArray()||[.68,.73,.77],opacity:material.opacity??1};}
onmessage=async({data})=>{
  try{
    let meshes,warnings=[],unit=data.unit||'millimeter',unitNote;
    if(data.format==='stl'){
      validateSTL(data.buffer);postMessage({phase:'Reading the original STL triangles…'});
      const {STLLoader}=await import(asset('./vendor/file-parsers/STLLoader.js'));
      const geometry=new STLLoader().parse(data.buffer);geometry.computeVertexNormals();
      const scale=UNITS_MM[unit];if(!scale)throw new Error('Choose a supported STL unit.');geometry.scale(scale,scale,scale);
      meshes=[{name:data.name,positions:geometry.attributes.position?.array,normals:geometry.attributes.normal?.array,colors:geometry.attributes.color?.array,indices:geometry.index?.array}];
      unitNote=`STL has no unit metadata; interpreted as ${unit}`;
    }else{
      zipBudget(data.buffer);postMessage({phase:'Reading the original 3MF components…'});
      const [{DOMParser,parseHTML},{ThreeMFLoader},{unzipSync,strFromU8},{Texture,TextureLoader}]=await Promise.all([
        import(asset('./vendor/linkedom/worker.js')),import(asset('./vendor/file-parsers/3MFLoader.js')),import(asset('./vendor/file-parsers/fflate.module.js')),import(asset('./vendor/three/three.module.min.js'))]);
      globalThis.DOMParser=DOMParser;globalThis.document=parseHTML('<html></html>').document;
      // Geometry preview only: do not start DOM image loads in this isolated worker.
      // The official loader still constructs texture-backed surfaces; maps are omitted
      // from our geometry packet, with a visible limitation whenever one is present.
      TextureLoader.prototype.load=function(url,onLoad){const texture=new Texture();if(onLoad)onLoad(texture);return texture;};
      let zip=unzipSync(new Uint8Array(data.buffer),{filter:file=>/\.model$/i.test(file.name)});
      const names=Object.keys(zip).filter(name=>/\.model$/i.test(name));if(!names.length)throw new Error('The 3MF archive has no model document.');
      const units=new Set();
      for(const name of names){
        const xml=new DOMParser().parseFromString(strFromU8(zip[name]),'application/xml'),model=xml.querySelector('model');
        if(!model)throw new Error('The 3MF model XML is invalid.');
        units.add(model.getAttribute('unit')||'millimeter');
        const required=model.getAttribute('requiredextensions');
        if(required?.trim())throw new Error('This 3MF requires extensions that this geometry viewer cannot reproduce: '+required+'. Download the original for its authoring tool.');
        if(model.querySelector('texture2d'))warnings.push('Texture images are omitted in this geometry preview; inspect the original for its exact appearance.');
      }
      zip=null;
      if(units.size!==1)throw new Error('This 3MF contains mixed model units; use its authoring tool to inspect it.');
      unit=[...units][0];const scale=UNITS_MM[unit];if(!scale)throw new Error('This 3MF declares an unsupported unit: '+unit+'.');
      const group=new ThreeMFLoader().parse(data.buffer);if(!group)throw new Error('The 3MF reader could not build this file.');
      group.updateMatrixWorld(true);meshes=[];
      group.traverse(object=>{
        if(!object.isMesh)return;
        if(!object.matrixWorld.elements.every(Number.isFinite))throw new Error('A 3MF component has a non-finite transform.');
        const geometry=object.geometry.clone();geometry.applyMatrix4(object.matrixWorld);geometry.scale(scale,scale,scale);
        // Baking a reflected instance removes Three's matrix-based culling flip.
        if(object.matrixWorld.determinant()<0){
          const index=geometry.index?.array;
          if(index)for(let i=0;i<index.length;i+=3)[index[i+1],index[i+2]]=[index[i+2],index[i+1]];
          else for(const attribute of Object.values(geometry.attributes))for(let i=0;i<attribute.count;i+=3)for(let k=0;k<attribute.itemSize;k++){
            const a=(i+1)*attribute.itemSize+k,b=(i+2)*attribute.itemSize+k;[attribute.array[a],attribute.array[b]]=[attribute.array[b],attribute.array[a]];
          }
        }
        geometry.computeVertexNormals();
        meshes.push({name:object.name,positions:geometry.attributes.position?.array,normals:geometry.attributes.normal?.array,colors:geometry.attributes.color?.array,
          indices:geometry.index?.array,materials:[].concat(object.material).map(materialData),groups:geometry.groups});
      });
      unitNote=`3MF ${unit} units converted to millimeters`;
    }
    const model=validateModel({meshes,format:data.format.toUpperCase(),unit,unitNote,warnings:[...new Set(warnings)]});
    postMessage({model},transferBuffers(model));
  }catch(error){postMessage({error:error?.message||'The model file could not be decoded.'});}
};
