// A dedicated classic worker allows OCCT's unmodified LGPL build to be replaced.
// Terminating this worker cancels parsing and releases its WASM memory.
onmessage=async({data})=>{
  try{
    const asset=path=>{const url=new URL(path,self.location.href);url.search=new URL(self.location.href).search;return url.href;};
    const {validateModel,transferBuffers,MAX_TRIANGLES}=await import(asset('./file-geometry.js'));
    postMessage({phase:'Loading the STEP reader…'});
    importScripts(asset('./vendor/occt-import-js/occt-import-js.js'));
    const occt=await occtimportjs({locateFile:name=>asset('./vendor/occt-import-js/'+name),print:()=>{},printErr:()=>{}});
    postMessage({phase:'Triangulating the original STEP surfaces…'});
    const result=occt.ReadStepFile(new Uint8Array(data.buffer),{linearUnit:'millimeter',linearDeflectionType:'bounding_box_ratio',linearDeflection:.001,angularDeflection:.2});
    if(!result?.success||!result.meshes?.length)throw new Error('The STEP reader could not find displayable surfaces in this file.');
    const meshes=result.meshes.map(mesh=>{
      const materials=[{color:mesh.color||[.68,.73,.77],opacity:1}],groups=[];
      const indices=mesh.index?.array;
      if(!indices?.length||indices.length%3||indices.length>MAX_TRIANGLES*3)throw new Error('The STEP surface exceeds the preview triangle limit or has invalid indices.');
      const triangleMaterials=new Uint32Array(indices.length/3);
      for(const face of mesh.brep_faces||[]){
        if(!face.color)continue;
        let index=materials.findIndex(m=>m.color.every((n,i)=>n===face.color[i]));
        if(index<0){index=materials.length;materials.push({color:face.color,opacity:1});}
        if(!Number.isInteger(face.first)||!Number.isInteger(face.last)||face.first<0||face.last<face.first||face.last>=triangleMaterials.length)throw new Error('The STEP reader returned invalid face ranges.');
        triangleMaterials.fill(index,face.first,face.last+1);
      }
      if(materials.length>1){let start=0;for(let i=1;i<=triangleMaterials.length;i++)if(i===triangleMaterials.length||triangleMaterials[i]!==triangleMaterials[start]){groups.push({start:start*3,count:(i-start)*3,materialIndex:triangleMaterials[start]});start=i;}}
      return{name:mesh.name,positions:mesh.attributes?.position?.array,normals:mesh.attributes?.normal?.array,indices,materials,groups};
    });
    const model=validateModel({meshes,format:'STEP',unit:'millimeter',unitNote:'STEP units converted to millimeters',warnings:[]});
    postMessage({model},transferBuffers(model));
  }catch(error){postMessage({error:error?.message||'The STEP file could not be decoded.'});}
};
