"""Deterministic compact orthogonal layouts for declared scenario views.

The authored row/column positions remain recognizable. Routes join equipment
cards, not measured physical pipe positions, and preserve the full connection
identity. No process model, SVG renderer or external layout program is used.
"""
from heapq import heappop, heappush
from itertools import count

SIDES = ('right', 'bottom', 'left', 'top')
OFFSETS = (0, -14, 14, -28, 28, -42, 42, -56, 56)
CLEARANCE = 8


def _pair(point):
    return (point['x'], point['y'])


def _segment_hits_box(a, b, box, inset=0):
    x0, y0 = box['x'] + inset, box['y'] + inset
    x1, y1 = box['x'] + box['width'] - inset, box['y'] + box['height'] - inset
    if a[0] == b[0]:
        return x0 < a[0] < x1 and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1)
    return y0 < a[1] < y1 and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1)


def _intersection(a, b, c, d):
    """Return ('overlap'|'cross', point) or None for axis-aligned segments."""
    av, cv = a[0] == b[0], c[0] == d[0]
    if av == cv:
        axis, other = (1, 0) if av else (0, 1)
        if a[other] != c[other]:
            return None
        lo = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        hi = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        return ('overlap', None) if lo < hi else None
    vertical, horizontal = ((a, b), (c, d)) if av else ((c, d), (a, b))
    x, y = vertical[0][0], horizontal[0][1]
    if min(vertical[0][1], vertical[1][1]) <= y <= max(vertical[0][1], vertical[1][1]) and min(horizontal[0][0], horizontal[1][0]) <= x <= max(horizontal[0][0], horizontal[1][0]):
        return ('cross', (x, y))
    return None


def _simplify(points):
    out = []
    for p in points:
        if out and p == out[-1]:
            continue
        if len(out) > 1 and ((out[-2][0] == out[-1][0] == p[0]) or (out[-2][1] == out[-1][1] == p[1])):
            out[-1] = p
        else:
            out.append(p)
    return out


def _anchor(node, side, offset):
    x, y, w, h = node['x'], node['y'], node['width'], node['height']
    if side == 'right':
        return (x + w, y + h / 2 + offset), (x + w + CLEARANCE, y + h / 2 + offset)
    if side == 'left':
        return (x, y + h / 2 + offset), (x - CLEARANCE, y + h / 2 + offset)
    if side == 'bottom':
        return (x + w / 2 + offset, y + h), (x + w / 2 + offset, y + h + CLEARANCE)
    return (x + w / 2 + offset, y), (x + w / 2 + offset, y - CLEARANCE)


def _side_bias(node, other, side):
    dx, dy = other['x'] - node['x'], other['y'] - node['y']
    direction = {'right': dx, 'left': -dx, 'bottom': dy, 'top': -dy}[side]
    return 0 if direction > 0 else 12 if direction == 0 else 35


def _route(edge, nodes, grid_x, grid_y, used_ports, previous):
    start, finish = nodes[edge['from']['component']], nodes[edge['to']['component']]
    if start['id'] == finish['id']:
        raise ValueError('Self-loop needs an explicit topology layout: ' + edge['id'])
    candidates = []
    for node, other in [(start, finish), (finish, start)]:
        choices = []
        for side in SIDES:
            limit = (node['height'] if side in ('left', 'right') else node['width']) / 2 - 18
            free = [offset for offset in OFFSETS if abs(offset) <= limit and (node['id'], side, offset) not in used_ports][:3]
            for offset in free:
                anchor, stub = _anchor(node, side, offset)
                choices.append({'side': side, 'offset': offset, 'anchor': anchor, 'stub': stub, 'bias': _side_bias(node, other, side) + abs(offset) * .15})
        if not choices:
            raise ValueError('No free topology card port: ' + node['id'])
        candidates.append(choices)
    sources, targets = candidates
    xs = sorted(set(grid_x) | {p['stub'][0] for p in sources + targets})
    ys = sorted(set(grid_y) | {p['stub'][1] for p in sources + targets})
    xindex, yindex = {x: i for i, x in enumerate(xs)}, {y: i for i, y in enumerate(ys)}
    goals = {(xindex[p['stub'][0]], yindex[p['stub'][1]]): p for p in targets}
    blocked = set()
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            if any(n['x'] - CLEARANCE < x < n['x'] + n['width'] + CLEARANCE and n['y'] - CLEARANCE < y < n['y'] + n['height'] + CLEARANCE for n in nodes.values()):
                blocked.add((ix, iy))
    serial = count()
    queue, costs, back, origin = [], {}, {}, {}
    def heuristic(ix, iy):
        return min(abs(xs[ix] - x) + abs(ys[iy] - y) + target['bias'] for (gx, gy), target in goals.items() for x, y in [(xs[gx], ys[gy])])
    def penalty(a, b):
        amount = 0
        for old in previous:
            for c, d in zip(old['points'], old['points'][1:]):
                hit = _intersection(a, b, c, d)
                if hit and hit[0] == 'overlap':
                    return None
                if hit:
                    amount += 1000
        return amount
    for p in sources:
        ix, iy = xindex[p['stub'][0]], yindex[p['stub'][1]]
        direction = 0 if p['side'] in ('left', 'right') else 1
        extra = penalty(p['anchor'], p['stub'])
        if extra is None:
            continue
        state = (ix, iy, direction)
        value = p['bias'] + extra
        costs[state] = value
        origin[state] = p
        heappush(queue, (value + heuristic(ix, iy), next(serial), state))
    terminal, terminal_cost = None, float('inf')
    while queue:
        score, _, state = heappop(queue)
        if score >= terminal_cost:
            break
        ix, iy, direction = state
        if score > costs[state] + heuristic(ix, iy) + .0001:
            continue
        if (ix, iy) in goals:
            target = goals[(ix, iy)]
            final_penalty = penalty(target['stub'], target['anchor'])
            if final_penalty is not None:
                total = costs[state] + target['bias'] + final_penalty
                if total < terminal_cost:
                    terminal, terminal_cost = state, total
        for nx, ny, nd in [(ix - 1, iy, 0), (ix + 1, iy, 0), (ix, iy - 1, 1), (ix, iy + 1, 1)]:
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)) or (nx, ny) in blocked:
                continue
            a, b = (xs[ix], ys[iy]), (xs[nx], ys[ny])
            # Grid points alone are insufficient: a step can cross a narrow box.
            if any(_segment_hits_box(a, b, n, -CLEARANCE + .01) for n in nodes.values()):
                continue
            extra = penalty(a, b)
            if extra is None:
                continue
            value = costs[state] + abs(a[0] - b[0]) + abs(a[1] - b[1]) + (10 if nd != direction else 0) + extra
            next_state = (nx, ny, nd)
            if value < costs.get(next_state, float('inf')):
                costs[next_state] = value
                back[next_state] = state
                origin[next_state] = origin[state]
                heappush(queue, (value + heuristic(nx, ny), next(serial), next_state))
    if terminal is None:
        raise ValueError('No non-overlapping topology route: ' + edge['id'])
    source, target = origin[terminal], goals[terminal[:2]]
    points, current = [], terminal
    while True:
        points.append((xs[current[0]], ys[current[1]]))
        if current not in back:
            break
        current = back[current]
    points = _simplify([source['anchor'], *reversed(points), target['anchor']])
    used_ports.add((start['id'], source['side'], source['offset']))
    used_ports.add((finish['id'], target['side'], target['offset']))
    return {**edge, 'points': points, 'from_side': source['side'], 'to_side': target['side']}


def _diagnostics(nodes, routed):
    collisions, overlaps, crossings = [], [], []
    for i, route in enumerate(routed):
        for a, b in zip(route['points'], route['points'][1:]):
            if a[0] != b[0] and a[1] != b[1]:
                raise AssertionError('Non-orthogonal topology segment')
            for n in nodes.values():
                if _segment_hits_box(a, b, n):
                    collisions.append({'edge': route['id'], 'node': n['id']})
            for earlier in routed[:i]:
                for c, d in zip(earlier['points'], earlier['points'][1:]):
                    hit = _intersection(a, b, c, d)
                    if hit:
                        record = {'edge': route['id'], 'other_edge': earlier['id'], 'point': hit[1]}
                        if hit[0] == 'overlap':
                            overlaps.append(record)
                        elif record not in crossings:
                            crossings.append(record)
    if collisions or overlaps:
        raise AssertionError({'node_collisions': collisions, 'edge_overlaps': overlaps})
    return {'node_collisions': collisions, 'edge_overlaps': overlaps, 'crossings': crossings}


def layout(system, view=None, *, node_width=180, node_height=132, width=900, top=78, row_gap=34):
    """Return compact nodes/routes, exact edge identity and geometric diagnostics."""
    view = view or system['views'][0]
    placements = view['placements']
    xs, ys = sorted({p['x'] for p in placements}), sorted({p['y'] for p in placements})
    if not placements or len(xs) > 4:
        raise ValueError('Review topology layout for an empty or wider-than-four-column view')
    if node_width <= 0 or node_height <= 0 or row_gap < 2 * CLEARANCE + 4 or width < len(xs) * node_width + (len(xs) - 1) * 20 + 24:
        raise ValueError('Topology dimensions leave insufficient routing clearance')
    column_step = min(223, (width - 52 - node_width) / max(1, len(xs) - 1))
    left = (width - (node_width + (len(xs) - 1) * column_step)) / 2
    nodes = {p['component']: {'id': p['component'], 'x': left + xs.index(p['x']) * column_step, 'y': top + ys.index(p['y']) * (node_height + row_gap), 'width': node_width, 'height': node_height, 'index': index + 1} for index, p in enumerate(placements)}
    if len(nodes) != len(placements):
        raise ValueError('Duplicate topology placement')
    if len({(n['x'], n['y']) for n in nodes.values()}) != len(nodes):
        raise ValueError('Topology equipment cards occupy the same authored position')
    edges_by_id = {e['id']: e for e in system['connections']}
    edges = [edges_by_id[r['connection']] for r in view['routes']]
    if len({e['id'] for e in edges}) != len(edges):
        raise ValueError('Duplicate topology route')
    bottom = max(n['y'] + n['height'] for n in nodes.values())
    grid_x, grid_y = {12, width - 12}, {top - 10, bottom + 18}
    for n in nodes.values():
        grid_x.update([n['x'] - CLEARANCE, n['x'] + n['width'] + CLEARANCE])
        grid_y.update([n['y'] - CLEARANCE, n['y'] + n['height'] + CLEARANCE])
        for offset in OFFSETS:
            if abs(offset) <= node_width / 2 - 18:
                grid_x.add(n['x'] + node_width / 2 + offset)
            if abs(offset) <= node_height / 2 - 18:
                grid_y.add(n['y'] + node_height / 2 + offset)
    # A central corridor and near-card lanes provide distinct paths at branches.
    for y in sorted({n['y'] for n in nodes.values()})[:-1]:
        grid_y.add(y + node_height + row_gap / 2)
    for x in sorted({n['x'] for n in nodes.values()})[:-1]:
        grid_x.add(x + node_width + (column_step - node_width) / 2)
    for edge in edges:
        if edge['from']['component'] not in nodes or edge['to']['component'] not in nodes:
            raise ValueError('Topology connection endpoint is outside the selected view: ' + edge['id'])
    def distance(edge):
        a, b = nodes[edge['from']['component']], nodes[edge['to']['component']]
        return abs(a['x'] - b['x']) + abs(a['y'] - b['y'])
    attempts = [edges, list(reversed(edges)), sorted(edges, key=distance), sorted(edges, key=distance, reverse=True)]
    # A join can trap an unplaced return line if its enclosing branch is routed
    # first. Rotate the stable declaration order before accepting a crossing.
    attempts += [edges[index:] + edges[:index] for index in range(1, len(edges))]
    attempts += [list(reversed(order)) for order in attempts[4:]]
    routed, diagnostics = None, None
    for ordering in attempts:
        used, candidate = set(), []
        for edge in ordering:
            candidate.append(_route(edge, nodes, grid_x, grid_y, used, candidate))
        order_by_id = {edge['id']: index for index, edge in enumerate(edges)}
        candidate.sort(key=lambda route: order_by_id[route['id']])
        report = _diagnostics(nodes, candidate)
        if diagnostics is None or len(report['crossings']) < len(diagnostics['crossings']):
            routed, diagnostics = candidate, report
        if not report['crossings']:
            break
    for route in routed:
        route['points'] = [{'x': x, 'y': y} for x, y in route['points']]
    return {'nodes': list(nodes.values()), 'routes': routed, 'width': width, 'height': bottom + 38,
            'bounds': {'left': left, 'top': top, 'right': width - left, 'bottom': bottom},
            'diagnostics': diagnostics}


def validate_layout(graph, system, view=None):
    """Assert geometry plus complete node/edge/port/medium identity against JSON."""
    view = view or system['views'][0]
    assert [n['id'] for n in graph['nodes']] == [p['component'] for p in view['placements']], 'Topology node inventory differs from its selected view'
    assert [r['id'] for r in graph['routes']] == [r['connection'] for r in view['routes']], 'Topology edge inventory differs from its selected view'
    edges = {e['id']: e for e in system['connections']}
    nodes = {n['id']: n for n in graph['nodes']}
    for index, node in enumerate(graph['nodes']):
        assert node['width'] > 0 and node['height'] > 0, 'Topology card has invalid dimensions'
        assert 0 <= node['x'] <= node['x'] + node['width'] <= graph['width'] and 0 <= node['y'] <= node['y'] + node['height'] <= graph['height'], 'Topology card leaves its image bounds'
        for other in graph['nodes'][:index]:
            overlap_x = max(node['x'], other['x']) < min(node['x'] + node['width'], other['x'] + other['width'])
            overlap_y = max(node['y'], other['y']) < min(node['y'] + node['height'], other['y'] + other['height'])
            assert not (overlap_x and overlap_y), 'Topology cards overlap'
    tuples = []
    for route in graph['routes']:
        for key in ['from', 'to', 'medium']:
            assert route[key] == edges[route['id']][key], 'Topology connection identity changed: ' + route['id']
        points = [_pair(p) for p in route['points']]
        assert len(points) >= 2 and all(a != b for a, b in zip(points, points[1:])), 'Topology route needs distinct endpoints and nonzero segments'
        for endpoint, key in [(points[0], 'from'), (points[-1], 'to')]:
            n = nodes[route[key]['component']]
            x, y = endpoint
            on_vertical = (abs(x - n['x']) < .001 or abs(x - n['x'] - n['width']) < .001) and n['y'] <= y <= n['y'] + n['height']
            on_horizontal = (abs(y - n['y']) < .001 or abs(y - n['y'] - n['height']) < .001) and n['x'] <= x <= n['x'] + n['width']
            assert on_vertical or on_horizontal, 'Topology endpoint misses its equipment card'
        assert all(0 <= x <= graph['width'] and 0 <= y <= graph['height'] for x, y in points), 'Topology route leaves its image bounds'
        tuples.append({**route, 'points': points})
    return _diagnostics(nodes, tuples)
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
