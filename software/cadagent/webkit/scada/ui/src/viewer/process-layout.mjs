/** Presentation-only projection of an explicit, unbranched right-to-left process
 * chain. Authored geometry remains the fallback for every unsupported diagram.
 * This module has no DOM, adapter, model, clock or persisted-layout dependency. */
export function projectProcessLayout(view, {width, height, fitMaxZoom = 1} = {}) {
  if (![width,height,fitMaxZoom].every(value => Number.isFinite(value) && value > 0)) return view;
  const nodes = view.nodes ?? [], edges = view.edges ?? [];
  if (width < 1000 || nodes.length < 2 || edges.length !== nodes.length - 1 ||
      ['labels','junctions','portals','overlays'].some(key => view[key]?.length)) return view;
  const byId = new Map(nodes.map(node => [node.id,node])), outgoing = new Map(), incoming = new Set();
  if (byId.size !== nodes.length || nodes.some(node => ![node.w,node.h].every(value => Number.isFinite(value) && value > 0))) return view;
  const port = (node, id) => (Array.isArray(node.ports) ? node.ports : Object.values(node.ports ?? {})).find(item => item.id === id);
  for (const edge of edges) {
    if (edge.path) return view;
    const from = byId.get(edge.from?.component), to = byId.get(edge.to?.component);
    if (!from || !to || from === to || outgoing.has(from.id) || incoming.has(to.id)) return view;
    const outlet = port(from,edge.from.port), inlet = port(to,edge.to.port);
    if (outlet?.side !== 'right' || inlet?.side !== 'left' ||
        [outlet,inlet].some(item => !Number.isFinite(item.offset ?? .5) || (item.offset ?? .5) < 0 || (item.offset ?? .5) > 1)) return view;
    outgoing.set(from.id,edge); incoming.add(to.id);
  }
  const heads = nodes.filter(node => !incoming.has(node.id));
  if (heads.length !== 1) return view;
  const ordered = [], visited = new Set();
  let current = heads[0];
  while (current && !visited.has(current.id)) {
    ordered.push(current); visited.add(current.id);
    current = byId.get(outgoing.get(current.id)?.to.component);
  }
  if (ordered.length !== nodes.length) return view;
  const margin = 60, gapX = 100, gapY = 90;
  const cellWidth = Math.max(...nodes.map(node => node.w)), cellHeight = Math.max(...nodes.map(node => node.h));
  const scale = (w,h) => Math.min(fitMaxZoom,Math.max(1,width-24)/w,Math.max(1,height-76)/h);
  const authoredScale = scale(view.width,view.height);
  let best;
  for (let desiredRows = 1; desiredRows <= nodes.length; desiredRows++) {
    const columns = Math.ceil(nodes.length / desiredRows), rows = Math.ceil(nodes.length / columns);
    const worldWidth = margin*2 + columns*cellWidth + (columns-1)*gapX;
    const worldHeight = margin*2 + rows*cellHeight + (rows-1)*gapY;
    const zoom = scale(worldWidth,worldHeight), occupiedWidth = (worldWidth-margin*2)*zoom;
    if (!best || zoom > best.zoom + .001 || (Math.abs(zoom-best.zoom) <= .001 && occupiedWidth > best.occupiedWidth)) {
      best = {columns,rows,width:worldWidth,height:worldHeight,zoom,occupiedWidth};
    }
  }
  // Do not rearrange a readable authored view merely to move its empty margins.
  const originalSpan = Math.max(...nodes.map(node => node.x+node.w))-Math.min(...nodes.map(node => node.x));
  if (best.zoom < authoredScale - .001 || (best.zoom < authoredScale + .01 && best.occupiedWidth < originalSpan*authoredScale*1.2)) return view;
  const projectedNodes = ordered.map((node,index) => ({...node,
    x:margin + (index%best.columns)*(cellWidth+gapX),
    y:margin + Math.floor(index/best.columns)*(cellHeight+gapY)}));
  const placed = new Map(projectedNodes.map(node => [node.id,node]));
  const projectedEdges = edges.map(edge => {
    const from = placed.get(edge.from.component), to = placed.get(edge.to.component);
    const start = [from.x+from.w,from.y+from.h*(port(from,edge.from.port).offset ?? .5)];
    const end = [to.x,to.y+to.h*(port(to,edge.to.port).offset ?? .5)];
    let points;
    if (from.y === to.y) {
      const middle = (start[0]+end[0])/2;
      points = [start,[middle,start[1]],[middle,end[1]],end];
    } else {
      const right = best.width-margin/2, left = margin/2, between = from.y+cellHeight+gapY/2;
      points = [start,[right,start[1]],[right,between],[left,between],[left,end[1]],end];
    }
    return {...edge,points:points.map(([x,y]) => ({x,y}))};
  });
  return {...view,width:best.width,height:best.height,canvas:{...view.canvas,width:best.width,height:best.height},
    nodes:projectedNodes,edges:projectedEdges,
    ...(view.placements ? {placements:view.placements.map(item => {const node=placed.get(item.component);return {...item,x:node.x,y:node.y};})} : {}),
    ...(view.routes ? {routes:view.routes.map(item => ({...item,points:projectedEdges.find(edge => edge.id === item.connection).points}))} : {}),
    layoutProjection:{kind:'process-chain',columns:best.columns,rows:best.rows}};
}
