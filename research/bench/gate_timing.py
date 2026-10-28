"""Timing benchmark for the integrity-gate primitives on a synthetic ~100-part assembly (research/design-workflows.md §4.1).

Run with a Python that has cadquery: ``python research/bench/gate_timing.py [N]``. Synthetic boxes, cylinders and
spheres only; real parts with filleted or shelled faces cost more per pair (unmeasured here). Seeded, so runs compare.

Measures, on OCP via CadQuery:
  * AABB broad phase over all pairs
  * BRepExtrema_DistShapeShape (min gap) on candidate pairs
  * BRepAlgoAPI_Common volume (exact intersection) on candidate pairs
  * containment: common-volume == inner volume, and BRepClass3d_SolidClassifier point sampling
  * connectivity graph (touching = gap <= tol) and components
"""
import random, time, itertools, sys
import cadquery as cq
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON

random.seed(1)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
parts = {}
# a 'frame' of touching boxes along X plus random small parts, some touching, some floating
x = 0.0
for i in range(N // 2):
    w = random.uniform(10, 30)
    parts[f"frame{i}"] = cq.Workplane().box(w, 20, 20).translate((x + w / 2, 0, 0)).val()
    x += w
for i in range(N - N // 2):
    cx = random.uniform(0, x)
    kind = random.random()
    if kind < 0.5:   # sitting on the frame top (touching)
        parts[f"boss{i}"] = cq.Workplane().cylinder(8, 4).translate((cx, 0, 10 + 4)).val()
    elif kind < 0.8: # floating above
        parts[f"float{i}"] = cq.Workplane().box(6, 6, 6).translate((cx, 0, 30)).val()
    else:            # buried inside a frame box (contained)
        parts[f"inner{i}"] = cq.Workplane().sphere(3).translate((cx, 0, 0)).val()
names = list(parts)
print(f"parts: {len(names)}")

t0 = time.perf_counter()
bb = {n: parts[n].BoundingBox() for n in names}
tol = 1e-3
cands = []
for a, b in itertools.combinations(names, 2):
    A, B = bb[a], bb[b]
    if (A.xmin - tol <= B.xmax and B.xmin - tol <= A.xmax and A.ymin - tol <= B.ymax and B.ymin - tol <= A.ymax
            and A.zmin - tol <= B.zmax and B.zmin - tol <= A.zmax):
        cands.append((a, b))
t1 = time.perf_counter()
print(f"broad phase: {len(list(itertools.combinations(names, 2)))} pairs -> {len(cands)} candidates in {t1-t0:.3f}s")

gaps = {}
for a, b in cands:
    d = BRepExtrema_DistShapeShape(parts[a].wrapped, parts[b].wrapped)
    d.Perform()
    gaps[(a, b)] = d.Value()
t2 = time.perf_counter()
print(f"min gap on candidates: {t2-t1:.3f}s ({(t2-t1)/max(1,len(cands))*1000:.1f} ms/pair)")

vols = {}
for a, b in cands:
    vols[(a, b)] = parts[a].intersect(parts[b]).Volume()
t3 = time.perf_counter()
print(f"exact common volume on candidates: {t3-t2:.3f}s ({(t3-t2)/max(1,len(cands))*1000:.1f} ms/pair)")

# containment by volume
contained = [(a, b) for (a, b), v in vols.items() if v > 0 and abs(v - min(parts[a].Volume(), parts[b].Volume())) < 1e-6 * max(1.0, v)]
print(f"contained pairs (common == smaller volume): {len(contained)} e.g. {contained[:3]}")

# containment by point classification (sample 20 vertices+centre of inner)
t4 = time.perf_counter()
n_cls = 0
for a, b in contained[:10]:
    inner, outer = (a, b) if parts[a].Volume() < parts[b].Volume() else (b, a)
    cls = BRepClass3d_SolidClassifier(parts[outer].wrapped)
    pts = [v.toTuple() for v in parts[inner].Vertices()][:20] + [parts[inner].Center().toTuple()]
    for p in pts:
        cls.Perform(gp_Pnt(*p), 1e-6)
        n_cls += 1
t5 = time.perf_counter()
print(f"point classification: {n_cls} points in {t5-t4:.3f}s")

# connectivity: touching edges; components
adj = {n: set() for n in names}
for (a, b), g in gaps.items():
    if g <= 1e-3 or vols[(a, b)] > 0:
        adj[a].add(b); adj[b].add(a)
seen, comps = set(), []
for n in names:
    if n in seen: continue
    stack, comp = [n], []
    while stack:
        u = stack.pop()
        if u in seen: continue
        seen.add(u); comp.append(u); stack.extend(adj[u] - seen)
    comps.append(comp)
floating = [c for c in comps if not any(m.startswith("frame") for m in c)]
print(f"components: {len(comps)}; floating components: {len(floating)} e.g. {[c[0] for c in floating[:5]]}")
print(f"total {t5-t0:.2f}s")
