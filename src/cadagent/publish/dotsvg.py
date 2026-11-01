"""Graphviz DOT to SVG without Graphviz: a small parser for the DOT the toolkit writes and a layered layout.

The connectivity gate writes its graph as DOT (``exports/gates/connectivity.dot``,
``cadagent.review.gates.connectivity.to_dot``). The review site draws it as SVG. When Graphviz's ``dot`` is
installed it is used (``engine="auto"``); otherwise, or with ``engine="python"``, this module lays the graph out
itself:

- **Parser.** The DOT subset ``to_dot`` and simple hand-written graphs use: ``graph``/``digraph``, ``subgraph``
  (``cluster_*`` subgraphs become boxes with their ``label``), node statements with attributes, edge chains
  (``a -- b -- c``, ``->``), ``graph``/``node``/``edge`` default attributes, ``key=value`` statements, quoted
  strings and comments. Ports, HTML labels and nested attribute semantics are not supported.
- **Layout.** Each cluster is laid out on its own: its connected components (over the edges inside the cluster)
  are layered by breadth-first distance from a root (a node drawn with ``peripheries=2``, i.e. grounded, else the
  node with most links), left to right, the order inside a layer settled by a few barycentre sweeps. Components
  and clusters are stacked top to bottom. Edges are straight, or curved when they are parallel or join two nodes
  of one layer. It is a readable picture of who touches whom, not Graphviz's crossing minimisation.

Styles read: node ``shape`` (box, ellipse), ``style`` (rounded, dashed, dotted, bold), ``peripheries=2``, ``color``,
``fontcolor``, ``label``; edge ``style``, ``color``, ``label``. Colours map onto the site's CSS variables
(``--ink``, ``--muted``, ``--fail``, ``--warn``, ...) with fallbacks, so the SVG follows the page's light and dark
themes inline and still renders as a standalone file.
"""

from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = ["DotGraph", "parse_dot", "dot_to_svg", "layout"]


# ----------------------------------------------------------------------------------------------------- parsing

@dataclass
class DotGraph:
    directed: bool = False
    attrs: Dict[str, str] = field(default_factory=dict)
    nodes: Dict[str, Dict[str, str]] = field(default_factory=dict)          # id -> attributes (insertion order)
    node_cluster: Dict[str, str] = field(default_factory=dict)              # id -> cluster id ("" = none)
    clusters: Dict[str, Dict[str, str]] = field(default_factory=dict)       # cluster id -> attributes (label, ...)
    edges: List[Tuple[str, str, Dict[str, str]]] = field(default_factory=list)


_TOKEN = re.compile(r'''
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/|\#[^\n]*)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<edge>--|->)
  | (?P<punct>[{}\[\];,=:])
  | (?P<id>[A-Za-z_\x80-￿][\w\x80-￿.]*|-?(?:\.\d+|\d+(?:\.\d*)?))
''', re.S | re.X)


def _tokens(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"DOT: unexpected character {text[pos]!r} at offset {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        value = m.group(kind)
        if kind == "str":
            value = re.sub(r'\\(.)', lambda x: "\n" if x.group(1) in "nlr" else x.group(1), value[1:-1])
            kind = "id"
        out.append((kind, value))
    return out


def parse_dot(text: str) -> DotGraph:
    """Parse a DOT graph (the subset described in the module docstring). Raises ``ValueError`` on a syntax error."""
    toks = _tokens(text)
    g = DotGraph()
    i = 0

    def peek(k: int = 0) -> Tuple[str, str]:
        return toks[i + k] if i + k < len(toks) else ("eof", "")

    def take(value: Optional[str] = None) -> Tuple[str, str]:
        nonlocal i
        t = peek()
        if value is not None and t[1] != value:
            raise ValueError(f"DOT: expected {value!r}, got {t[1]!r}")
        i += 1
        return t

    def attr_list() -> Dict[str, str]:
        out: Dict[str, str] = {}
        while peek()[1] == "[":
            take("[")
            while peek()[1] != "]":
                if peek()[0] == "eof":
                    raise ValueError("DOT: unterminated attribute list")
                key = take()[1]
                val = "true"
                if peek()[1] == "=":
                    take("=")
                    val = take()[1]
                out[key] = val
                if peek()[1] in (",", ";"):
                    take()
            take("]")
        return out

    def node_id() -> str:
        t = take()
        if t[0] != "id":
            raise ValueError(f"DOT: expected a node id, got {t[1]!r}")
        if peek()[1] == ":":            # a port (a:p or a:p:n): kept off the id
            take(":")
            take()
            if peek()[1] == ":":
                take(":")
                take()
        return t[1]

    def add_node(nid: str, attrs: Dict[str, str], cluster: str, defaults: Dict[str, str]) -> None:
        if nid not in g.nodes:
            g.nodes[nid] = dict(defaults)
            g.node_cluster[nid] = cluster
        g.nodes[nid].update(attrs)

    def stmts(cluster: str, node_defaults: Dict[str, str], edge_defaults: Dict[str, str],
              sub_attrs: Dict[str, str]) -> None:
        node_defaults, edge_defaults = dict(node_defaults), dict(edge_defaults)
        while peek()[1] != "}":
            kind, value = peek()
            if kind == "eof":
                raise ValueError("DOT: missing '}'")
            if value == ";":
                take()
                continue
            if value in ("graph", "node", "edge") and peek(1)[1] == "[":
                take()
                attrs = attr_list()
                {"graph": sub_attrs, "node": node_defaults, "edge": edge_defaults}[value].update(attrs)
                continue
            if value == "subgraph" or value == "{":
                sub_id = ""
                if value == "subgraph":
                    take()
                    if peek()[1] != "{":
                        sub_id = take()[1]
                take("{")
                is_cluster = sub_id.startswith("cluster")
                inner = cluster
                attrs: Dict[str, str] = {}
                if is_cluster:
                    inner = sub_id
                    g.clusters.setdefault(sub_id, {})
                    attrs = g.clusters[sub_id]
                stmts(inner, node_defaults, edge_defaults, attrs)
                take("}")
                continue
            if kind == "id" and peek(1)[1] == "=":
                take()
                take("=")
                sub_attrs[value] = take()[1]
                continue
            first = node_id()
            chain = [first]
            while peek()[0] == "edge":
                if take()[1] == "->":
                    g.directed = True
                chain.append(node_id())
            attrs = attr_list()
            if len(chain) == 1:
                add_node(first, attrs, cluster, node_defaults)
            else:
                for n in chain:
                    add_node(n, {}, cluster, node_defaults)
                for a, b in zip(chain, chain[1:]):
                    g.edges.append((a, b, {**edge_defaults, **attrs}))

    if peek()[1] == "strict":
        take()
    head = take()[1]
    if head not in ("graph", "digraph"):
        raise ValueError(f"DOT: expected 'graph' or 'digraph', got {head!r}")
    g.directed = head == "digraph"
    if peek()[1] != "{":
        take()
    take("{")
    stmts("", {}, {}, g.attrs)
    take("}")
    return g


# ----------------------------------------------------------------------------------------------------- layout

NODE_H = 26.0
ROW_GAP = 10.0
COL_GAP = 70.0
PAD = 14.0
CLUSTER_GAP = 22.0
LABEL_H = 18.0


def _label(nid: str, attrs: Dict[str, str]) -> str:
    lab = attrs.get("label", nid)
    return nid if lab in ("\\N", "") else lab


def _width(text: str) -> float:
    return max(52.0, 6.6 * max(len(line) for line in text.split("\n")) + 22.0)


@dataclass
class _Box:
    x: float
    y: float
    w: float
    h: float


def layout(g: DotGraph) -> Tuple[Dict[str, _Box], Dict[str, _Box], float, float]:
    """Positions: ``({node: box}, {cluster: box}, width, height)``. Deterministic for a given graph."""
    adj: Dict[str, List[str]] = {n: [] for n in g.nodes}
    for a, b, _ in g.edges:
        if a != b and b not in adj[a]:
            adj[a].append(b)
            adj[b].append(a)
    for n in adj:
        adj[n].sort()
    order = list(g.clusters) + ([""] if any(c == "" for c in g.node_cluster.values()) else [])
    boxes: Dict[str, _Box] = {}
    cboxes: Dict[str, _Box] = {}
    y = PAD
    width = 0.0
    for cid in order:
        members = [n for n in g.nodes if g.node_cluster.get(n, "") == cid]
        if not members:
            continue
        top = y
        inner_y = y + (LABEL_H + 6 if cid else 0)
        x0 = PAD + (PAD if cid else 0)
        right = x0
        for comp in _components(members, adj):
            placed, w, h = _layer_component(comp, adj, g)
            # a component linked to nodes already drawn starts under them, so the links run short and downwards
            linked = [boxes[m] for n in comp for m in adj[n] if m in boxes]
            shift = 0.0
            if linked:
                first = [n for n, (dx, _) in placed.items() if dx == 0.0]
                half = max(_width(_label(n, g.nodes[n])) for n in first) / 2
                shift = max(0.0, sum(b.x + b.w / 2 for b in linked) / len(linked) - half - x0)
            for n, (dx, dy) in placed.items():
                boxes[n] = _Box(x0 + shift + dx, inner_y + dy, _width(_label(n, g.nodes[n])), NODE_H)
            right = max(right, x0 + shift + w)
            inner_y += h + ROW_GAP * 2
        inner_y -= ROW_GAP * 2
        if cid:
            cboxes[cid] = _Box(PAD, top, right - PAD + PAD, inner_y - top + PAD)
            y = inner_y + PAD + CLUSTER_GAP
            width = max(width, right + PAD)
        else:
            y = inner_y + CLUSTER_GAP
            width = max(width, right)
    for c in cboxes.values():                     # every cluster box as wide as the widest
        c.w = max(c.w, width - PAD)
    return boxes, cboxes, width + PAD, y - CLUSTER_GAP + PAD


def _components(members: List[str], adj: Dict[str, List[str]]) -> List[List[str]]:
    inside = set(members)
    seen: set = set()
    comps: List[List[str]] = []
    for n in members:
        if n in seen:
            continue
        comp, stack = [], [n]
        seen.add(n)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for m in adj[cur]:
                if m in inside and m not in seen:
                    seen.add(m)
                    stack.append(m)
        comps.append(sorted(comp, key=members.index))
    comps.sort(key=lambda c: -len(c))             # the largest (usually the grounded frame) first
    return comps


def _layer_component(comp: List[str], adj: Dict[str, List[str]], g: DotGraph
                     ) -> Tuple[Dict[str, Tuple[float, float]], float, float]:
    inside = set(comp)
    grounded = [n for n in comp if g.nodes[n].get("peripheries") == "2"]
    root = grounded[0] if grounded else max(comp, key=lambda n: (sum(m in inside for m in adj[n]), -comp.index(n)))
    rank = {root: 0}
    queue = [root]
    for cur in queue:
        for m in adj[cur]:
            if m in inside and m not in rank:
                rank[m] = rank[cur] + 1
                queue.append(m)
    layers: List[List[str]] = [[] for _ in range(max(rank.values()) + 1)]
    for n in comp:
        layers[rank[n]].append(n)
    pos = {n: i for layer in layers for i, n in enumerate(layer)}

    def sweep(seq: List[int], ref_offset: int) -> None:
        for li in seq:
            ref = li + ref_offset
            if ref < 0 or ref >= len(layers):
                continue
            ref_set = set(layers[ref])

            def bary(n: str) -> float:
                ns = [pos[m] for m in adj[n] if m in ref_set]
                return sum(ns) / len(ns) if ns else pos[n]
            layers[li].sort(key=lambda n: (bary(n), n))
            for i, n in enumerate(layers[li]):
                pos[n] = i

    for _ in range(3):
        sweep(list(range(1, len(layers))), -1)
        sweep(list(range(len(layers) - 2, -1, -1)), +1)
    col_w = [max(_width(_label(n, g.nodes[n])) for n in layer) for layer in layers]
    tallest = max(len(layer) for layer in layers)
    height = tallest * NODE_H + (tallest - 1) * ROW_GAP
    placed: Dict[str, Tuple[float, float]] = {}
    x = 0.0
    for li, layer in enumerate(layers):
        h = len(layer) * NODE_H + (len(layer) - 1) * ROW_GAP
        y0 = (height - h) / 2
        for i, n in enumerate(layer):
            placed[n] = (x, y0 + i * (NODE_H + ROW_GAP))
        x += col_w[li] + COL_GAP
    return placed, x - COL_GAP, height


# ----------------------------------------------------------------------------------------------------- drawing

_COLOURS = {
    "red": "var(--fail,#d1453b)", "orange": "var(--warn,#c98700)", "blue": "var(--link,#2f6fdf)",
    "gray60": "var(--muted,#686c75)", "grey60": "var(--muted,#686c75)", "gray": "var(--muted,#686c75)",
    "grey": "var(--muted,#686c75)", "black": "var(--ink,#202227)", "green": "var(--ok,#2f9e6e)",
}
_INK = "var(--ink,#202227)"


def _colour(value: Optional[str], default: str = _INK) -> str:
    if not value:
        return default
    if value in _COLOURS:
        return _COLOURS[value]
    return value if re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-z]+", value) else default


def _dash(style: str) -> str:
    if "dashed" in style:
        return ' stroke-dasharray="6 4"'
    if "dotted" in style:
        return ' stroke-dasharray="1.5 3.5"'
    return ""


def _e(v: str) -> str:
    return html.escape(v, quote=True)


Point = Tuple[float, float]


def _route(a: _Box, b: _Box, off: float) -> Tuple[Point, Point, Point, Point]:
    """A cubic Bezier between two boxes: side to side with horizontal tangents when one lies left of the other,
    top to bottom with vertical tangents when they overlap in x, and an arc out of the right sides when they share
    a column. ``off`` separates parallel edges."""
    if a is b:                                                # a self-loop: a small arc out of the right side
        x, y = a.x + a.w, a.y + a.h / 2
        r = 18.0 + abs(off)
        return (x, y - 6), (x + r, y - r), (x + r, y + r), (x, y + 6)
    if a.x > b.x + b.w:                                       # a right of b: route b to a, then reverse
        p3, c2, c1, p0 = _route(b, a, -off)
        return p0, c1, c2, p3
    acx, acy, bcx, bcy = a.x + a.w / 2, a.y + a.h / 2, b.x + b.w / 2, b.y + b.h / 2
    if b.x > a.x + a.w:                                       # b right of a
        p0, p3 = (a.x + a.w, acy + off / 3), (b.x, bcy + off / 3)
        dx = max(20.0, (p3[0] - p0[0]) / 2)
        return p0, (p0[0] + dx, p0[1] + off), (p3[0] - dx, p3[1] + off), p3
    if abs(acx - bcx) < 1.0 or abs(a.x - b.x) < 1.0:          # one column: bow out to the right
        p0, p3 = (a.x + a.w, acy), (b.x + b.w, bcy)
        bow = 24.0 + 0.12 * abs(bcy - acy) + abs(off)
        right = max(p0[0], p3[0]) + bow
        return p0, (right, p0[1]), (right, p3[1]), p3
    upper, lower = (a, b) if acy <= bcy else (b, a)            # overlapping in x: vertical tangents
    p0 = (upper.x + upper.w / 2 + off, upper.y + upper.h)
    p3 = (lower.x + lower.w / 2 + off, lower.y)
    dy = max(20.0, (p3[1] - p0[1]) / 2)
    pts = (p0, (p0[0], p0[1] + dy), (p3[0], p3[1] - dy), p3)
    return pts if upper is a else (pts[3], pts[2], pts[1], pts[0])


def _svg_python(g: DotGraph, title: str) -> str:
    boxes, cboxes, width, height = layout(g)
    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="dotgraph" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{_e(title)}">',
        f"<title>{_e(title)}</title>",
        "<style>.dotgraph text{font:11px system-ui,-apple-system,'Segoe UI',sans-serif;fill:var(--ink,#202227)}"
        ".dotgraph .el{font-size:9px;fill:var(--muted,#686c75);paint-order:stroke;stroke:var(--card,#fff);"
        "stroke-width:3px}.dotgraph .cl{font-size:10px;fill:var(--muted,#686c75)}</style>",
        '<defs><marker id="dotarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="var(--muted,#686c75)"/></marker></defs>',
    ]
    for cid, c in cboxes.items():
        attrs = g.clusters.get(cid, {})
        out.append(f'<g class="cluster"><rect x="{c.x:.1f}" y="{c.y:.1f}" width="{c.w:.1f}" height="{c.h:.1f}" '
                   f'rx="10" fill="none" stroke="{_colour(attrs.get("color"), "var(--line,#e4e0d7)")}"/>'
                   f'<text class="cl" x="{c.x + 10:.1f}" y="{c.y + 15:.1f}">{_e(attrs.get("label", cid))}</text></g>')
    pair_count: Dict[Tuple[str, str], int] = {}
    for a, b, _ in g.edges:
        key = tuple(sorted((a, b)))
        pair_count[key] = pair_count.get(key, 0) + 1
    pair_seen: Dict[Tuple[str, str], int] = {}
    labels: List[str] = []
    labelled: set = set()                 # (node, label): a label repeated on edges into one node is drawn once
    for a, b, attrs in g.edges:
        if a not in boxes or b not in boxes:
            continue
        key = tuple(sorted((a, b)))
        k = pair_seen.get(key, 0)
        pair_seen[key] = k + 1
        off = (k - (pair_count[key] - 1) / 2) * 16.0
        p0, c1, c2, p3 = _route(boxes[a], boxes[b], off)
        style = attrs.get("style", "")
        stroke = _colour(attrs.get("color"), "var(--ink,#202227)")
        sw = "2.2" if "bold" in style else "1.2"
        arrow = ' marker-end="url(#dotarrow)"' if g.directed else ""
        tip = _e(f"{a} – {b}" + (f": {attrs['label']}" if attrs.get("label") else ""))
        d = (f"M{p0[0]:.1f},{p0[1]:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} "
             f"{p3[0]:.1f},{p3[1]:.1f}")
        out.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}"{_dash(style)}{arrow}>'
                   f"<title>{tip}</title></path>")
        lab = attrs.get("label")
        if lab and not ({(a, lab), (b, lab)} & labelled):
            labelled |= {(a, lab), (b, lab)}
            lx = (p0[0] + 3 * c1[0] + 3 * c2[0] + p3[0]) / 8
            ly = (p0[1] + 3 * c1[1] + 3 * c2[1] + p3[1]) / 8
            colour = _colour(attrs.get("fontcolor") or attrs.get("color"), "")
            fill = f' style="fill:{colour}"' if colour else ""
            labels.append(f'<text class="el" x="{lx:.1f}" y="{ly - 3:.1f}" text-anchor="middle"{fill}>'
                          f'{_e(lab)}</text>')
    out += labels
    for nid, box in boxes.items():
        attrs = g.nodes[nid]
        style = attrs.get("style", "")
        stroke = _colour(attrs.get("color"))
        fcol = _colour(attrs.get("fontcolor"), "")
        dash = _dash(style)
        sw = "2.2" if "bold" in style else "1.2"
        fill = "var(--card,#fff)"
        shape = attrs.get("shape", "box")
        lab = _label(nid, attrs)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        parts = [f'<g class="node"><title>{_e(nid)}</title>']
        if shape in ("ellipse", "oval", "circle"):
            parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{box.w / 2:.1f}" ry="{box.h / 2:.1f}" '
                         f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
            if attrs.get("peripheries") == "2":
                parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{box.w / 2 + 3:.1f}" ry="{box.h / 2 + 3:.1f}" '
                             f'fill="none" stroke="{stroke}" stroke-width="{sw}"/>')
        else:
            rx = 7 if "rounded" in style or shape == "box" else 0
            if attrs.get("peripheries") == "2":
                parts.append(f'<rect x="{box.x - 3:.1f}" y="{box.y - 3:.1f}" width="{box.w + 6:.1f}" '
                             f'height="{box.h + 6:.1f}" rx="{rx + 3}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')
            parts.append(f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{box.w:.1f}" height="{box.h:.1f}" rx="{rx}" '
                         f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
        text_style = f' style="fill:{fcol}"' if fcol else ""
        parts.append(f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle"{text_style}>{_e(lab)}</text></g>')
        out.append("".join(parts))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _svg_graphviz(text: str) -> Optional[str]:
    exe = shutil.which("dot")
    if not exe:
        return None
    try:
        res = subprocess.run([exe, "-Tsvg"], input=text, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0 or "<svg" not in res.stdout:
        return None
    svg = res.stdout[res.stdout.index("<svg"):]
    # Graphviz paints a white page behind the graph; drop it so the page's background shows. Its other colours are
    # literal (black text and lines), so in a dark theme the built-in layout reads better.
    svg = re.sub(r'(<g id="graph0" class="graph"[^>]*>\s*(?:<title>[^<]*</title>\s*)?<polygon) fill="white"',
                 r'\1 fill="none"', svg, count=1)
    return svg.replace("<svg ", '<svg class="dotgraph" ', 1)


def dot_to_svg(text: str, *, engine: str = "auto", title: str = "graph") -> Tuple[str, str]:
    """``(svg, engine_used)`` for a DOT graph. ``engine``: ``auto`` (Graphviz's ``dot`` when installed, else the
    built-in layout), ``graphviz`` (falls back to ``python`` when Graphviz is missing or fails) or ``python``.
    Raises ``ValueError`` when the DOT cannot be parsed by the built-in parser and Graphviz did not draw it."""
    if engine not in ("auto", "graphviz", "python"):
        raise ValueError(f"engine must be auto, graphviz or python, not {engine!r}")
    if engine != "python":
        svg = _svg_graphviz(text)
        if svg:
            return svg, "graphviz"
    return _svg_python(parse_dot(text), title), "python"
