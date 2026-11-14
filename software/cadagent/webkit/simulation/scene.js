/** Display primitives and recorded world poses on the existing metre-based, Y-up stage. */
import * as THREE from 'three';

export function createPoseScene(stage,recording) {
  const root=new THREE.Group(),groups=[];
  root.name='recorded-z-up-world';root.rotation.x=-Math.PI/2;stage.root.add(root);
  let disposed=false;
  const localCorners=[];
  for(const body of recording.bodies){
    const group=new THREE.Group();group.name=body.id;root.add(group);groups.push(group);
    for(const g of body.geometry){
      let geometry;
      if(g.shape==='box')geometry=new THREE.BoxGeometry(...g.size);
      else if(g.shape==='sphere')geometry=new THREE.SphereGeometry(g.size[0],24,16);
      else{geometry=new THREE.CylinderGeometry(g.size[0],g.size[0],g.size[1],32);geometry.rotateX(Math.PI/2);}
      const material=new THREE.MeshStandardMaterial({color:g.color,metalness:.25,roughness:.32});
      const mesh=new THREE.Mesh(geometry,material);mesh.position.fromArray(g.position);mesh.quaternion.fromArray(g.quaternion);
      mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);
    }
    const box=new THREE.Box3();
    for(const mesh of group.children){mesh.geometry.computeBoundingBox();mesh.updateMatrix();box.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrix));}
    localCorners.push([0,1,2,3,4,5,6,7].map(i=>new THREE.Vector3(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z)));
  }
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
  return {root,groups,bounds,height:Math.max(.01,size.x,size.y,size.z),
    apply(poses){if(disposed)throw new Error('Pose scene is disposed');poses.forEach((pose,i)=>{groups[i].position.fromArray(pose.position);groups[i].quaternion.fromArray(pose.quaternion);});root.updateMatrixWorld(true);},
    fit(){if(disposed)throw new Error('Pose scene is disposed');stage.fitView(bounds,{margin:1.12,direction:new THREE.Vector3(1,.7,1.8)});},
    dispose(){if(disposed)return;disposed=true;root.removeFromParent();root.traverse(object=>{object.geometry?.dispose();object.material?.dispose();});},
  };
}
