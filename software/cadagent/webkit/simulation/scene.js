/** Display primitives, packed meshes and recorded world poses on the existing metre-based, Y-up stage. */
import * as THREE from 'three';
import {creasedNormals} from '../model/model.js';

const toStage=(point,out=new THREE.Vector3())=>out.set(point.x,point.z,-point.y);

/** `meshes` is a mesh library from loadMeshLibrary (part -> metres); a recording's mesh parts draw from it. */
export function createPoseScene(stage,recording,{meshes}={}) {
  const root=new THREE.Group(),groups=[],shared=new Map();
  root.name='recorded-z-up-world';root.rotation.x=-Math.PI/2;stage.root.add(root);
  let disposed=false;
  const meshGeometry=part=>{
    if(!shared.has(part)){
      const source=meshes?.get(part);if(!source)throw new Error(`Mesh part ${part} is not loaded`);
      const {positions,normals}=creasedNormals(source.positions,source.index),geometry=new THREE.BufferGeometry();
      geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('normal',new THREE.BufferAttribute(normals,3));
      shared.set(part,geometry);
    }
    return shared.get(part);
  };
  const primitive=g=>{
    let geometry;
    if(g.shape==='mesh')geometry=meshGeometry(g.part);
    else if(g.shape==='box')geometry=new THREE.BoxGeometry(...g.size);
    else if(g.shape==='sphere')geometry=new THREE.SphereGeometry(g.size[0],24,16);
    else{geometry=new THREE.CylinderGeometry(g.size[0],g.size[0],g.size[1],32);geometry.rotateX(Math.PI/2);}
    const opacity=g.opacity??1,material=new THREE.MeshStandardMaterial({color:g.color,metalness:g.shape==='mesh'?.15:.25,roughness:g.shape==='mesh'?.5:.32,
      transparent:opacity<1,opacity,depthWrite:opacity>=1});
    const mesh=new THREE.Mesh(geometry,material);mesh.position.fromArray(g.position);mesh.quaternion.fromArray(g.quaternion);
    mesh.castShadow=opacity>=1;mesh.receiveShadow=true;return mesh;
  };
  const localCorners=[];
  for(const body of recording.bodies){
    const group=new THREE.Group();group.name=body.id;root.add(group);groups.push(group);
    for(const g of body.geometry)group.add(primitive(g));
    const box=new THREE.Box3();
    for(const mesh of group.children){if(!mesh.geometry.boundingBox)mesh.geometry.computeBoundingBox();mesh.updateMatrix();box.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrix));}
    localCorners.push([0,1,2,3,4,5,6,7].map(i=>new THREE.Vector3(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z)));
  }
  const fixed=new THREE.Group();fixed.name='recorded-scenery';root.add(fixed);
  for(const g of recording.scenery??[])fixed.add(primitive(g));
  // Fit the complete recorded motion, including geometry; moving links stay in view after Fit.
  const bounds=new THREE.Box3(),point=new THREE.Vector3(),rotation=new THREE.Quaternion(),position=new THREE.Vector3();
  const bodyBounds=groups.map(()=>new THREE.Box3()),padding=groups.map(()=>0),radii=localCorners.map(corners=>Math.max(...corners.map(p=>p.length())));
  for(const [frameIndex,frame] of recording.frames.entries())frame.poses.forEach((pose,i)=>{
    rotation.fromArray(pose.quaternion);position.fromArray(pose.position);
    for(const corner of localCorners[i]){point.copy(corner).applyQuaternion(rotation).add(position);const {x,y,z}=point;bodyBounds[i].expandByPoint(point.set(x,z,-y));}
    if(frameIndex){
      const previous=recording.frames[frameIndex-1].poses[i].quaternion;
      const dot=Math.min(1,Math.abs(previous.reduce((sum,n,k)=>sum+n*pose.quaternion[k],0))),theta=2*Math.acos(dot);
      // Rotation R(t)p has |f''(t)| <= radius*theta^2. Linear interpolation's remainder is
      // <= max|f''|/8 on [0,1]; translation is already linear. Expand endpoint bounds by
      // that conservative error so sparse rotations cannot escape Fit between samples.
      padding[i]=Math.max(padding[i],radii[i]*(theta*theta/8+1e-10)); // unit-normalization/near-coincident roundoff margin
    }
  });
  bodyBounds.forEach((box,i)=>bounds.union(box.expandByScalar(padding[i])));
  root.updateMatrixWorld(true);
  const size=bounds.getSize(new THREE.Vector3());
  // A followed body (a robot driving metres): Fit frames every body where it is now, and playback carries the camera
  // with that body across the floor, so it stays the size the reader chose. Height changes are not followed.
  const view=recording.view,follow=view?.follow?recording.bodies.findIndex(b=>b.id===view.follow):-1;
  const direction=view?.direction?toStage({x:view.direction[0],y:view.direction[1],z:view.direction[2]}).normalize():new THREE.Vector3(1,.7,1.8);
  const tracked=new THREE.Vector3(),moved=new THREE.Vector3();let trackedSet=false;
  const reach=follow<0?null:Math.max(...localCorners.flatMap(corners=>corners.map(p=>p.length())));
  const current=()=>{const box=new THREE.Box3();root.updateMatrixWorld(true);for(const group of groups)for(const mesh of group.children){if(!mesh.geometry.boundingBox)mesh.geometry.computeBoundingBox();box.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));}return box;};
  return {root,groups,bounds,height:Math.max(.01,size.x,size.y,size.z),follow:follow<0?null:recording.bodies[follow].id,reach,
    apply(poses){
      if(disposed)throw new Error('Pose scene is disposed');
      poses.forEach((pose,i)=>{groups[i].position.fromArray(pose.position);groups[i].quaternion.fromArray(pose.quaternion);});root.updateMatrixWorld(true);
      if(follow>=0){
        const at=toStage({x:poses[follow].position[0],y:poses[follow].position[1],z:0});
        if(trackedSet){moved.subVectors(at,tracked);stage.camera.position.add(moved);stage.controls.target.add(moved);}
        tracked.copy(at);trackedSet=true;
      }
    },
    fit(){if(disposed)throw new Error('Pose scene is disposed');stage.fitView(follow>=0?current():bounds,{margin:1.12,direction});},
    dispose(){if(disposed)return;disposed=true;root.removeFromParent();const seen=new Set();root.traverse(object=>{if(object.geometry&&!seen.has(object.geometry)){seen.add(object.geometry);object.geometry.dispose();}object.material?.dispose();});},
  };
}
