import assert from 'node:assert/strict';
import test from 'node:test';
import {normalizeMesh,validateModel,validateSTL,MAX_TRIANGLES} from '../src/cadagent/webkit/file-geometry.js';
import {fileURL} from '../src/cadagent/webkit/file-loader.js';
const triangle=()=>({positions:[0,0,0,10,0,0,0,20,0],indices:[0,1,2]});
test('original URL permits only same-origin supported originals',()=>{
  assert.equal(fileURL('/part.STEP?revision=1','https://example.test/kit/viewer').format,'step');
  for(const url of ['https://other.test/a.stl','javascript:a.stl','/a.png','https://u:p@example.test/a.stl'])assert.throws(()=>fileURL(url,'https://example.test/'));
});
test('geometry contract rejects invalid vertices, indices and materials before scene construction',()=>{
  assert.equal(validateModel({meshes:[triangle()]}).triangles,1);
  for(const change of [m=>m.positions[0]=NaN,m=>m.positions[0]=1e90,m=>m.indices[2]=3,m=>m.indices[1]=1.5,m=>m.positions.fill(0),m=>m.normals=[0],m=>m.colors=Array(9).fill(2),m=>m.groups=[{start:0,count:6,materialIndex:0}],m=>m.materials=[{color:[0,0,0],opacity:NaN}]]){const m=triangle();change(m);assert.throws(()=>normalizeMesh(m));}
  assert.throws(()=>validateModel({meshes:[]}));
});
test('STL guard matches the official binary classifier without trusting an attacker face count',()=>{
  const valid=new ArrayBuffer(134);new DataView(valid).setUint32(80,1,true);assert.doesNotThrow(()=>validateSTL(valid));
  const html=new TextEncoder().encode('<html>'+'.'.repeat(100)).buffer;assert.throws(()=>validateSTL(html));
  const broken=valid.slice(0);new DataView(broken).setUint32(80,MAX_TRIANGLES+1,true);assert.throws(()=>validateSTL(broken));
  const ascii=new TextEncoder().encode('solid block\n'+' '.repeat(100)+'\nendsolid block').buffer;assert.doesNotThrow(()=>validateSTL(ascii));
  for(const value of ['SOLID block','     solid block'])assert.throws(()=>validateSTL(new TextEncoder().encode(value+' '.repeat(100)).buffer));
});
