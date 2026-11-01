"""Planar linkage poses for animation: joints solved by circle intersection, bodies moved rigidly between poses.

A linkage moves in one plane (two world axes, e.g. x and z), and every joint axis is perpendicular to it. Ground
joints are fixed. The driven joint follows a path. Every other joint is solved from two joints already known and
its distances to them, the links' lengths, as an intersection of two circles. Of the two intersections, the one
nearest the joint's previous position is taken. The pose therefore moves continuously from the reference pose (the
pose the CAD was built in) and never jumps to the other assembly branch. That covers four-bars driven by an output
point, five-bars, and chains of dyads.

Limits: kinematics only (no forces, no compliance); a path point that no pose can reach raises ``ValueError``; the
continuity rule needs path steps small next to the links.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Sequence, Tuple

Point = Tuple[float, float]


def circles(p: Point, r1: float, q: Point, r2: float) -> List[Point]:
    """The intersections of circle (p, r1) and circle (q, r2): two points, one where they touch, none apart."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy)
    if d < 1e-12 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    mx, my = p[0] + a * dx / d, p[1] + a * dy / d
    return [(mx - h * dy / d, my + h * dx / d), (mx + h * dy / d, my - h * dx / d)]


@dataclass
class Linkage:
    """``ground``: fixed joints {name: (u, v)}; ``links``: {body: (joint, joint)}; ``reference``: every joint in
    the pose the CAD was built in; ``solve``: [(joint, from_a, from_b)] in order, each joint from two known ones."""
    ground: Mapping[str, Point]
    links: Mapping[str, Tuple[str, str]]
    reference: Mapping[str, Point]
    solve: Sequence[Tuple[str, str, str]]
    lengths: Dict[Tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self):
        for body, (a, b) in self.links.items():
            for j in (a, b):
                if j not in self.reference:
                    raise ValueError(f"link {body}: joint {j} has no reference position")
            d = math.dist(self.reference[a], self.reference[b])
            self.lengths[(a, b)] = self.lengths[(b, a)] = d
        for g, p in self.ground.items():
            if math.dist(p, self.reference[g]) > 1e-6:
                raise ValueError(f"ground joint {g} moved between ground and reference")

    def length(self, a: str, b: str) -> float:
        try:
            return self.lengths[(a, b)]
        except KeyError:
            raise ValueError(f"no link joins {a} and {b}") from None

    def pose(self, driven: Mapping[str, Point], previous: Mapping[str, Point]) -> Dict[str, Point]:
        """Every joint, with ``driven`` joints placed and the rest solved nearest ``previous``."""
        j: Dict[str, Point] = {**self.ground, **driven}
        for name, a, b in self.solve:
            pts = circles(j[a], self.length(a, name), j[b], self.length(b, name))
            if not pts:
                raise ValueError(f"{name} cannot be placed from {a} and {b}: the path leaves the linkage's reach")
            j[name] = min(pts, key=lambda p: math.dist(p, previous[name]))
        return j

    def sweep(self, driven: str, path: Sequence[Point]) -> List[Dict[str, Point]]:
        """Poses along ``path`` for the ``driven`` joint, starting from the reference pose."""
        prev, out = dict(self.reference), []
        for p in path:
            prev = self.pose({driven: p}, prev)
            out.append(prev)
        return out

    def body_motion(self, body: str, pose: Mapping[str, Point]) -> Tuple[float, Point, Point]:
        """How ``body`` moves from the reference pose to ``pose``: (turn in radians, counter-clockwise in the plane's
        (u, v) axes, about its first joint; that joint's reference position; its position in ``pose``)."""
        a, b = self.links[body]
        r0, r1 = self.reference[a], self.reference[b]
        p0, p1 = pose[a], pose[b]
        turn = math.atan2(p1[1] - p0[1], p1[0] - p0[0]) - math.atan2(r1[1] - r0[1], r1[0] - r0[0])
        turn = (turn + math.pi) % (2 * math.pi) - math.pi
        return turn, r0, p0

    def angle_at(self, pose: Mapping[str, Point], joint: str, a: str, b: str) -> float:
        """The angle at ``joint`` between the bars to ``a`` and ``b``, degrees in 0..180."""
        j = pose[joint]
        u = (pose[a][0] - j[0], pose[a][1] - j[1])
        v = (pose[b][0] - j[0], pose[b][1] - j[1])
        c = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def ellipse_path(centre: Point, radii: Tuple[float, float], start_deg: float, samples: int) -> List[Point]:
    """``samples`` points once round an ellipse, from ``start_deg``, the last point back at the first."""
    out = []
    for i in range(samples + 1):
        a = math.radians(start_deg + 360.0 * i / samples)
        out.append((centre[0] + radii[0] * math.cos(a), centre[1] + radii[1] * math.sin(a)))
    return out
