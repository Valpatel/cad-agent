import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {projectProcessLayout} from '../../../../software/cadagent/webkit/scada/ui/src/viewer/process-layout.mjs';
import {normalizeViewerDefinition} from '../../../../software/cadagent/webkit/scada/ui/src/viewer/viewer.mjs';
const scenario = id => normalizeViewerDefinition(JSON.parse(fs.readFileSync(new URL(`../../../../software/cadagent/webkit/scada/sim/scenarios/${id}/system.json`,import.meta.url)))).views[0];
const viewport = {width:3320,height:950,fitMaxZoom:1.5};
const point = (node,id) => {const port=node.ports.find(item=>item.id===id);return{x:node.x+(port.side==='right'?node.w:0),y:node.y+node.h*(port.offset??.5)};};
function checkRoutes(view){
  for(const edge of view.edges){
    assert.deepEqual(edge.points[0],point(view.nodes.find(node=>node.id===edge.from.component),edge.from.port));
    assert.deepEqual(edge.points.at(-1),point(view.nodes.find(node=>node.id===edge.to.component),edge.to.port));
    for(let i=1;i<edge.points.length;i++){
      const a=edge.points[i-1],b=edge.points[i];assert.ok(a.x===b.x||a.y===b.y,'orthogonal route');
      for(const n of view.nodes){
        const crosses=a.x===b.x?a.x>n.x&&a.x<n.x+n.w&&Math.max(a.y,b.y)>n.y&&Math.min(a.y,b.y)<n.y+n.h:
          a.y>n.y&&a.y<n.y+n.h&&Math.max(a.x,b.x)>n.x&&Math.min(a.x,b.x)<n.x+n.w;
        assert.equal(crosses,false,`${edge.id} crosses ${n.id}`);
      }
    }
  }
}
test('wide winery and wastewater projections preserve model identities, ports and readable card sizes',()=>{
  for(const [id,columns,rows] of [['winery',5,2],['wastewater-digester',6,1]]){
    const original=scenario(id),before=structuredClone(original),next=projectProcessLayout(original,viewport);
    assert.deepEqual(original,before);assert.deepEqual(next,projectProcessLayout(original,viewport));
    assert.deepEqual(next.layoutProjection,{kind:'process-chain',columns,rows});
    assert.deepEqual(next.nodes.map(n=>n.id).sort(),original.nodes.map(n=>n.id).sort());
    assert.deepEqual(next.edges.map(({points,...edge})=>edge),original.edges.map(({points,...edge})=>edge));
    for(const node of next.nodes){const source=original.nodes.find(n=>n.id===node.id);assert.equal(node.w,source.w);assert.equal(node.h,source.h);assert.deepEqual(node.ports,source.ports);}
    const scale=Math.min(1.5,(viewport.width-24)/next.width,(viewport.height-76)/next.height);
    const span=Math.max(...next.nodes.map(n=>n.x+n.w))-Math.min(...next.nodes.map(n=>n.x));
    assert.ok(scale>1);assert.ok(span*scale/viewport.width>.6,`${id}: insufficient real equipment span`);
    checkRoutes(next);
  }
});
test('authored complex, annotated and unsupported port diagrams remain untouched',()=>{
  const view=scenario('winery');
  for(const invalid of [scenario('hydroponics-ebb-flow'),{...view,labels:[{x:0,y:0,text:'Keep here'}]},
    {...view,edges:[...view.edges,{...view.edges[0],id:'branch'}]},
    {...view,nodes:view.nodes.map((node,i)=>i?node:{...node,ports:node.ports.map(p=>p.id==='outlet'?{...p,side:'bottom'}:p)})},
    {...view,edges:view.edges.map((edge,i)=>i?edge:{...edge,to:{...edge.to,component:edge.from.component}})}]){
    assert.equal(projectProcessLayout(invalid,viewport),invalid);
  }
  for(const size of [{width:390,height:844},{width:0,height:900},{width:NaN,height:900}])assert.equal(projectProcessLayout(view,{...size,fitMaxZoom:1.5}),view);
});
