"""Geometry-only path measurements for routed PCB evidence, without KiCad.

Inputs must come from native copper, with pad centers and layer-aware via nodes.
These measurements are not an impedance solver or signal-integrity simulation.
"""
import heapq
import math


def point_segment_distance(point, a, b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length2=dx*dx+dy*dy
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length2)) if length2 else 0
    return math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy)


def copper_graph(segments, vias, *, via_length=1.6):
    """Split same-layer segments at touching endpoints, then add via barrel edges.

    Nodes are (x_mm, y_mm, layer_name); inputs use a/b/width/layer keys.
    Connectivity through a pad not touched at a shared point is caller supplied.
    """
    def node(p,layer):return (round(p[0],5),round(p[1],5),layer)
    nodes={node(s[k],s['layer']) for s in segments for k in ('a','b')}
    nodes.update(node(v['xy'],layer) for v in vias for layer in v['layers'])
    graph={n:{} for n in nodes}
    def edge(a,b,d,width):
        graph[a][b]=(d,width);graph[b][a]=(d,width)
    for s in segments:
        touching=[n for n in nodes if n[2]==s['layer'] and point_segment_distance(n,s['a'],s['b'])<2e-5]
        touching.sort(key=lambda n:math.dist(n[:2],s['a']))
        for a,b in zip(touching,touching[1:]):edge(a,b,math.dist(a[:2],b[:2]),s['width'])
    for v in vias:
        layers=v['layers']
        for a,b in zip(layers,layers[1:]):edge(node(v['xy'],a),node(v['xy'],b),via_length,0)
    return graph


def shortest_path(graph,start,end):
    if start not in graph or end not in graph:raise ValueError('Missing copper endpoint')
    queue=[(0,start)];distance={start:0};previous={}
    while queue:
        d,node=heapq.heappop(queue)
        if d!=distance[node]:continue
        if node==end:
            path=[end]
            while path[-1]!=start:path.append(previous[path[-1]])
            return d,list(reversed(path))
        for nxt,(length,_) in graph[node].items():
            nd=d+length
            if nd<distance.get(nxt,float('inf')):
                distance[nxt]=nd;previous[nxt]=node;heapq.heappush(queue,(nd,nxt))
    raise ValueError('Disconnected copper endpoints')


def path_segments(graph,path):
    return [{'a':a[:2],'b':b[:2],'layer':a[2],'width':graph[a][b][1]}
            for a,b in zip(path,path[1:]) if a[2]==b[2]]


def sample_segments(segments,step=.2):
    """Yield midpoint samples and represented length; never duplicate endpoints."""
    for s in segments:
        count=max(1,math.ceil(math.dist(s['a'],s['b'])/step))
        length=math.dist(s['a'],s['b'])/count
        for i in range(count):
            t=(i+.5)/count
            yield (s['a'][0]+t*(s['b'][0]-s['a'][0]),s['a'][1]+t*(s['b'][1]-s['a'][1])),s,length


def pair_geometry(high,low,*,window=None,step=.2):
    """Measure both sides' distance to the opposite main path, in the same layer.

    An optional rectangular window (xmin,ymin,xmax,ymax) isolates the paired
    trunk from documented connector/TVS fanouts. Reports missing-layer samples.
    """
    gaps=[];straight_gaps=[];measured=0;missing=0
    for first,second in [(high,low),(low,high)]:
        for q,s,length in sample_segments(first,step):
            if window and not (window[0]<=q[0]<=window[2] and window[1]<=q[1]<=window[3]):continue
            peers=[other for other in second if other['layer']==s['layer']]
            if not peers:missing+=length;continue
            gap=min(point_segment_distance(q,t['a'],t['b'])-(s['width']+t['width'])/2 for t in peers);gaps.append(gap);measured+=length
            if min(math.dist(q,s['a']),math.dist(q,s['b']))>.75:straight_gaps.append(gap)
    return {'edge_gap_min_mm':min(gaps) if gaps else None,'edge_gap_max_mm':max(gaps) if gaps else None,
            'straight_edge_gap_max_mm':max(straight_gaps) if straight_gaps else None,'measured_both_sides_mm':measured,'missing_peer_layer_mm':missing,'sample_step_mm':step}
