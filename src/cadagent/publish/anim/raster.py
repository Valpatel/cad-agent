"""2D raster helpers for drawing solids as flat shapes: a triangle z-buffer, region outlines by marching squares, and
Douglas-Peucker simplification. numpy only, deterministic.

A drawn part needs a filled silhouette behind its edges, so that a nearer part hides what lies behind it while the
parts move (painter's order). The silhouette is the union of the part's projected triangles. Polygon union of
thousands of triangles needs a geometry library, so the triangles are rasterised instead, and the region's outline
is traced and simplified. At a cell of half a drawn pixel the outline is within a pixel of the exact one.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

Grid = Tuple[float, float, float]          # x0, y0, cell: cell (i, j) covers x0 + i*cell .. x0 + (i+1)*cell


def _split(tri: np.ndarray, z: np.ndarray, limit: float) -> Tuple[np.ndarray, np.ndarray]:
    """Split triangles (in cell units) into four at their edge midpoints until each spans at most ``limit`` cells."""
    out_t, out_z = [], []
    while len(tri):
        span = (tri.max(axis=1) - tri.min(axis=1)).max(axis=1)
        small = span <= limit
        out_t.append(tri[small])
        out_z.append(z[small])
        t, zz = tri[~small], z[~small]
        if not len(t):
            break
        m = (t + np.roll(t, -1, axis=1)) / 2                     # midpoints of edges 01, 12, 20
        mz = (zz + np.roll(zz, -1, axis=1)) / 2
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        ab, bc, ca = m[:, 0], m[:, 1], m[:, 2]
        za, zb, zc = zz[:, 0], zz[:, 1], zz[:, 2]
        zab, zbc, zca = mz[:, 0], mz[:, 1], mz[:, 2]
        tri = np.concatenate([np.stack(q, axis=1) for q in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
        z = np.concatenate([np.stack(q, axis=1) for q in ((za, zab, zca), (zab, zb, zbc), (zca, zbc, zc), (zab, zbc, zca))])
    return np.concatenate(out_t), np.concatenate(out_z)


def zbuffer(tris: np.ndarray, depth: np.ndarray, grid: Grid, shape: Tuple[int, int],
            values: np.ndarray = None) -> Tuple[np.ndarray, np.ndarray]:
    """Rasterise triangles ``tris`` (N, 3, 2) with per-vertex ``depth`` (N, 3), larger nearer the viewer, onto a
    ``shape`` (rows, cols) grid. A cell is covered when its centre is inside a triangle (edges included). Returns
    the nearest depth per cell (``-inf`` where empty) and, if ``values`` (N,) is given, the nearest triangle's value
    (``nan`` where empty)."""
    x0, y0, cell = grid
    rows, cols = shape
    zb = np.full(shape, -np.inf)
    vb = np.full(shape, np.nan) if values is not None else None
    if not len(tris):
        return zb, vb
    t = (np.asarray(tris, float) - (x0, y0)) / cell
    z = np.asarray(depth, float)
    if values is not None:
        # carry each triangle's value through the split as a constant third coordinate of its depth
        idx = np.repeat(np.arange(len(t))[:, None], 3, axis=1).astype(float)
        t2, zz = _split(np.concatenate([t, idx[:, :, None]], axis=2), z, 3.0)
        t, ids = t2[:, :, :2], t2[:, 0, 2].astype(int)
        z = zz
    else:
        t, z = _split(t, z, 3.0)
        ids = None
    lo = np.floor(t.min(axis=1) - 0.5).astype(int)                   # first candidate cell (i, j)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    keep = np.abs(area) > 1e-12
    a, b, c, lo, z, area = a[keep], b[keep], c[keep], lo[keep], z[keep], area[keep]
    if ids is not None:
        ids = ids[keep]
    for di in range(5):
        for dj in range(5):
            i, j = lo[:, 0] + di, lo[:, 1] + dj
            px, py = i + 0.5, j + 0.5
            w0 = ((b[:, 0] - px) * (c[:, 1] - py) - (b[:, 1] - py) * (c[:, 0] - px)) / area
            w1 = ((c[:, 0] - px) * (a[:, 1] - py) - (c[:, 1] - py) * (a[:, 0] - px)) / area
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9) & (i >= 0) & (j >= 0) & (i < cols) & (j < rows)
            if not inside.any():
                continue
            zz = (w0 * z[:, 0] + w1 * z[:, 1] + w2 * z[:, 2])[inside]
            ii, jj = i[inside], j[inside]
            if vb is None:
                np.maximum.at(zb, (jj, ii), zz)
            else:
                order = np.argsort(zz, kind="stable")          # nearest last: its value wins the assignment
                jj, ii, zz, vv = jj[order], ii[order], zz[order], values[ids[inside]][order]
                nearer = zz >= zb[jj, ii]
                zb[jj[nearer], ii[nearer]] = zz[nearer]
                vb[jj[nearer], ii[nearer]] = vv[nearer]
    return zb, vb


# ----------------------------------------------------------------------------------------------------- outlines

# marching squares on a boolean grid: corner bits (top-left 8, top-right 4, bottom-right 2, bottom-left 1) give the
# crossings, as pairs of cell edges (0 top, 1 right, 2 bottom, 3 left), oriented with the region on the left
_CASES: Dict[int, List[Tuple[int, int]]] = {
    1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(1, 0)], 5: [(3, 0), (1, 2)], 6: [(2, 0)], 7: [(3, 0)],
    8: [(0, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(0, 1)], 12: [(1, 3)], 13: [(1, 2)], 14: [(2, 3)],
}
_MID = {0: (0.5, 0.0), 1: (1.0, 0.5), 2: (0.5, 1.0), 3: (0.0, 0.5)}


def outlines(mask: np.ndarray) -> List[List[Tuple[float, float]]]:
    """Closed outlines of the True region of ``mask`` (rows = y), in cell coordinates: cell (i, j) spans i..i+1,
    j..j+1, and the outline runs through the midpoints between cell centres. Outer boundaries and holes alike; fill
    them with the even-odd rule."""
    m = np.pad(mask.astype(bool), 1)
    tl, tr, br, bl = m[:-1, :-1], m[:-1, 1:], m[1:, 1:], m[1:, :-1]
    code = tl * 8 + tr * 4 + br * 2 + bl * 1
    nxt: Dict[Tuple[float, float], Tuple[float, float]] = {}
    for j, i in zip(*np.nonzero((code > 0) & (code < 15))):
        for e0, e1 in _CASES[int(code[j, i])]:
            # the square's corners are the centres of cells (i-1..i, j-1..j) of the unpadded mask
            p = (i - 0.5 + _MID[e0][0], j - 0.5 + _MID[e0][1])
            q = (i - 0.5 + _MID[e1][0], j - 0.5 + _MID[e1][1])
            nxt[p] = q
    loops = []
    while nxt:
        start = min(nxt)                         # deterministic: start every loop at its smallest point
        loop, p = [start], nxt.pop(start)
        while p != start:
            loop.append(p)
            p = nxt.pop(p)
        loops.append(loop)
    return loops


def simplify(points: Sequence[Tuple[float, float]], tol: float, closed: bool = False) -> List[Tuple[float, float]]:
    """Douglas-Peucker: the fewest of ``points`` that stay within ``tol`` of the original line."""
    p = np.asarray(points, float)
    if len(p) < 3:
        return [tuple(v) for v in p]
    if closed:
        far = int(np.argmax(((p - p[0]) ** 2).sum(axis=1)))
        a = simplify(list(p[:far + 1]), tol)
        b = simplify(list(p[far:]) + [tuple(p[0])], tol)
        return a[:-1] + b[:-1]
    keep = np.zeros(len(p), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]
        ab = b - a
        n = np.hypot(*ab)
        seg = p[i + 1:j] - a
        d = np.abs(ab[0] * seg[:, 1] - ab[1] * seg[:, 0]) / n if n > 1e-12 else np.hypot(seg[:, 0], seg[:, 1])
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [tuple(v) for v in p[keep]]


def loop_area(loop: Sequence[Tuple[float, float]]) -> float:
    """Signed area (shoelace)."""
    p = np.asarray(loop, float)
    return float((p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]).sum() / 2)


def region(mask: np.ndarray, grid: Grid, tol: float, min_area: float = 0.0) -> List[List[Tuple[float, float]]]:
    """The True region of ``mask`` as simplified closed loops in drawing coordinates, dropping loops smaller than
    ``min_area`` (drawing units squared)."""
    x0, y0, cell = grid
    out = []
    for loop in outlines(mask):
        pts = [(x0 + x * cell, y0 + y * cell) for x, y in loop]
        if abs(loop_area(pts)) < max(min_area, 1e-9):
            continue
        s = simplify(pts, tol, closed=True)
        if len(s) >= 3:
            out.append(s)
    return out
