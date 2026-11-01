"""Closed-loop planar linkages (#187): four-bars and five-bars swept over their inputs, with the locks, the edges of
reach and the branch flips found on the way, and the dyad solver that moves a linkage measured from CAD along a path.

A closed loop has fewer free joints than joints: a four-bar has one input, a five-bar two, and the other joint angles
follow from the link lengths. Sampling every joint over its own range, as a serial chain, gives poses the linkage cannot
reach. Here the inputs are swept and the rest is solved.

* **Driven by its cranks.** ``sweep_fourbar`` turns the input crank (``cadagent.formulas.fourbar_angles``, Norton's
  algebraic solution of Freudenstein's equation). ``sweep_fivebar`` moves both cranks along a path of angle pairs, and
  ``fivebar_workspace`` samples them on a grid (``cadagent.formulas.fivebar_point``).
* **Driven by a point.** ``sweep_fivebar_tip`` moves a five-bar's tip along a path and solves its cranks
  (``cadagent.formulas.fivebar_inputs``). ``Linkage`` solves any chain of dyads measured from CAD, joint by joint, as
  the README hero does (it moved here from ``cadagent.publish.anim.linkage``).

At each step the sweeps report the joint angles, the transmission angle and both Jacobian determinants
(``cadagent.formulas.fivebar_jacobians``; Gosselin and Angeles' two kinds of singularity):

* ``det_direct`` is 0 where the distal links (a four-bar's coupler and rocker) fall into one line. There the
  assemblies meet and a crank-driven linkage locks: its input cannot turn further. Its sign is the assembly.
* ``det_inverse`` is 0, for each arm, where its crank and distal link fall into one line. For a four-bar that is the
  rocker's extreme: it stops and turns back, and it would be a dead point if the rocker drove. For a five-bar driven
  by its tip it is the edge of that arm's reach. Its sign is the arm's working mode.

Between two steps that straddle an event, the event is found by bisection: the edge of reach (a lock, or an arm in
line), a determinant changing sign, and a branch flip. ``track="hold"`` keeps the assembly (or working modes) declared;
``track="nearest"`` takes the solution nearest the previous pose, as a real linkage tends to, and flags each flip.

Lengths in any one unit (mm in CAD); angles in degrees; the frame has the ground pivots at A = (0, 0) and B = (d, 0),
angles counter-clockwise from A to B. Limits are in ``LIMITS``: rigid links, ideal pins, planar, position only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent import formulas as fx

Point = Tuple[float, float]

LIMITS = [
    "Rigid links on ideal pin joints in one plane, position only: no velocity, force, dynamics, compliance, backlash or "
    "joint clearance. A printed pin has play, so a printed linkage reaches its locks early or late and rattles there.",
    "Sampled inputs, not a continuous motion: an event between two samples is found by bisection only where the samples "
    "straddle it (a determinant changing sign, or the edge of reach). One that starts and ends between two samples is "
    "missed, so keep steps small next to the travel.",
    "Which assembly a linkage leaves a lock on is not modelled: 'hold' keeps the declared one, 'nearest' takes the one "
    "nearest the last pose. A real linkage can take either.",
    "The 40 degree transmission-angle guideline (Norton) is a rule for smooth running, not a force check. Kinematics and "
    "closed forms do not prove fit or strength; collisions between the links are not checked here.",
]
GUIDELINE_DEG = 40.0          # Norton's usual lowest transmission angle for a linkage that must run smoothly
LOCK_DEG = 1.0                # within this of a singularity (folded angle) counts as at it
_BISECT = 48                  # halvings of a step: 2^-48 of it, well under any CAD tolerance
TRACKS = ("hold", "nearest")


# ----------------------------------------------------------------------------- shared pieces

def _deg(rad: float) -> float:
    return math.degrees(rad)


def _fold(det: Optional[float]) -> Optional[float]:
    """A normalised determinant (the sine of the angle between two links) as the acute angle, in degrees."""
    return None if det is None else _deg(math.asin(min(1.0, abs(det))))


def _sign(v: float) -> int:
    return 1 if v > 0 else -1 if v < 0 else 0


def _lerp(x0: Sequence[float], x1: Sequence[float], t: float) -> Tuple[float, ...]:
    return tuple(a + (b - a) * t for a, b in zip(x0, x1))


def _bisect(inside: Callable[[float], bool], lo: float = 0.0, hi: float = 1.0) -> float:
    """The edge between ``inside(lo)`` and not ``inside(hi)``, to 2^-_BISECT of the interval."""
    for _ in range(_BISECT):
        mid = 0.5 * (lo + hi)
        if inside(mid):
            lo = mid
        else:
            hi = mid
    return lo


def _check(track: str, guideline_deg: float, lock_deg: float) -> None:
    if track not in TRACKS:
        raise ValueError(f"track = {track!r}: one of {TRACKS}")
    if not 0 <= lock_deg < guideline_deg <= 90:
        raise ValueError("need 0 <= lock_deg < guideline_deg <= 90")


@dataclass
class _Pose:
    """One solved pose: its assembly (or, for a tip-driven five-bar, its working modes), the moving pins, the angles
    (radians, absolute), and the normalised determinants."""
    mode: Any
    pins: Dict[str, Point]
    angles: Dict[str, float]
    direct: float
    inverse: List[Optional[float]]

    def distance(self, other: "_Pose") -> float:
        return max(math.dist(p, other.pins[k]) for k, p in self.pins.items())


def _unwrap(seq: List[Optional[float]]) -> List[Optional[float]]:
    """Degrees made continuous along each run of reachable steps (a turn through 180 does not jump by 360)."""
    out, prev = [], None
    for v in seq:
        if v is None:
            out.append(None)
            prev = None
            continue
        if prev is not None:
            v = prev + math.remainder(v - prev, 360.0)
        out.append(v)
        prev = v
    return out


def _runs(flags: Sequence[bool]) -> List[Tuple[int, int]]:
    """Index ranges [first, last] of consecutive True values."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def _report(kind: str, links: Mapping[str, float], inputs: Sequence[Tuple[float, ...]], input_names: Sequence[str],
            poses: Sequence[Optional[_Pose]], events: List[Dict[str, Any]], *, mode_name: Callable[[Any], Any],
            track: str, guideline_deg: float, lock_deg: float, fail_in_line: bool,
            arm_names: Sequence[str], extra: Optional[Dict[str, Any]] = None, input_key: str = "inputs_deg",
            branch_key: str = "branch") -> Dict[str, Any]:
    """The JSON-safe sweep report: steps, events, summary, verdict and limits. ``input_key`` names what a step's
    inputs are (crank angles in degrees, or a tip's position), ``branch_key`` what its branch is."""
    steps, problems = [], []
    prev: Optional[_Pose] = None
    flips = 0
    for i, (x, pose) in enumerate(zip(inputs, poses)):
        row: Dict[str, Any] = {"step": i, input_key: {n: v for n, v in zip(input_names, x)}}
        if pose is None:
            row.update(reachable=False, flags=["unreachable"])
            steps.append(row)
            continue
        mu = _fold(pose.direct)
        arms = [_fold(v) for v in pose.inverse]
        flags = []
        if mu < lock_deg:
            flags.append("lock")
        elif mu < guideline_deg:
            flags.append("below-guideline")
        if any(a is not None and a < lock_deg for a in arms):
            flags.append("in-line")
        flip = prev is not None and pose.mode != prev.mode
        if flip:
            flags.append("flip")
            flips += 1
        row.update({"reachable": True, branch_key: mode_name(pose.mode)})
        row.update(
                   angles_deg={k: _deg(v) for k, v in pose.angles.items()},
                   pins={k: [p[0], p[1]] for k, p in pose.pins.items()},
                   transmission_deg=mu, det_direct=pose.direct,
                   det_inverse={a: v for a, v in zip(arm_names, pose.inverse) if v is not None},
                   in_line_deg={a: v for a, v in zip(arm_names, arms) if v is not None}, flags=flags)
        steps.append(row)
        prev = pose
    ok = [p is not None for p in poses]
    reached = [s for s in steps if s["reachable"]]
    angle_names = list(reached[0]["angles_deg"]) if reached else []
    ranges = {}
    for n in angle_names:
        seq = _unwrap([s["angles_deg"][n] if s["reachable"] else None for s in steps])
        vals = [v for v in seq if v is not None]
        ranges[n] = [min(vals), max(vals)]
    summary: Dict[str, Any] = {
        "steps": len(steps), "reachable_steps": len(reached),
        "unreachable_steps": [s["step"] for s in steps if not s["reachable"]],
        "reachable_runs": [list(r) for r in _runs(ok)],
        "input_ranges": {n: [min(s[input_key][n] for s in reached), max(s[input_key][n] for s in reached)]
                         for n in input_names} if reached else {},
        "angle_ranges_deg": ranges, "flips": flips,
    }
    if reached:
        worst = min(reached, key=lambda s: s["transmission_deg"])
        summary.update(min_transmission_deg=worst["transmission_deg"], min_transmission_step=worst["step"])
        margins = {a: min(s["in_line_deg"][a] for s in reached) for a in arm_names if a in reached[0]["in_line_deg"]}
        summary["in_line_margin_deg"] = margins
        summary["below_guideline_steps"] = [s["step"] for s in reached if "below-guideline" in s["flags"]]
        summary["lock_steps"] = [s["step"] for s in reached if "lock" in s["flags"]]
        summary["in_line_steps"] = [s["step"] for s in reached if "in-line" in s["flags"]]
    if summary["unreachable_steps"]:
        problems.append(f"{len(summary['unreachable_steps'])} of {len(steps)} steps cannot close: the inputs leave the "
                        "linkage's reach")
    if summary.get("lock_steps"):
        problems.append(f"{len(summary['lock_steps'])} steps within {lock_deg:g} deg of a lock (the distal links in "
                        "one line): the input cannot drive the linkage there")
    if fail_in_line and summary.get("in_line_steps"):
        problems.append(f"{len(summary['in_line_steps'])} steps within {lock_deg:g} deg of an arm's crank and distal "
                        "link in one line: the edge of its reach, where the cranks must turn without bound")
    if flips:
        problems.append(f"{flips} branch flips: the linkage changes assembly between steps, through or near a lock")
    warnings = []
    if summary.get("below_guideline_steps"):
        warnings.append(f"{len(summary['below_guideline_steps'])} steps with a transmission angle under "
                        f"{guideline_deg:g} deg (lowest {summary['min_transmission_deg']:.1f} deg): it may bind")
    status = "fail" if problems else "warn" if warnings else "pass"
    out = {"schema_version": 1, "kind": kind, "links": dict(links), "track": track,
           "guideline_deg": guideline_deg, "lock_deg": lock_deg, **(extra or {}), "steps": steps, "events": events,
           "summary": summary, "status": status, "problems": problems, "warnings": warnings, "limits": LIMITS}
    return out


def _events(inputs: Sequence[Tuple[float, ...]], poses: Sequence[Optional[_Pose]], solve: Callable,
            input_names: Sequence[str], arm_names: Sequence[str], *, edge_kind: Callable[[Tuple[float, ...], Any], Dict],
            direct_kind: Optional[str], at_key: str = "at_deg") -> List[Dict[str, Any]]:
    """Events between consecutive steps, located by bisection on the straight line between their inputs (degrees):

    * the edge of reach, where one step closes and the next does not (``edge_kind`` names it);
    * an arm's ``det_inverse`` changing sign on one branch (``in-line``);
    * ``det_direct`` changing sign on one branch (``direct_kind``, for a tip-driven five-bar: it crosses a lock);
    * a branch flip (the next pose is on another branch)."""
    out: List[Dict[str, Any]] = []

    def at(x0, x1, t):
        return {n: v for n, v in zip(input_names, _lerp(x0, x1, t))}

    for i in range(len(inputs) - 1):
        x0, x1, p0, p1 = inputs[i], inputs[i + 1], poses[i], poses[i + 1]
        if (p0 is None) != (p1 is None):
            mode = (p0 or p1).mode
            inside = (lambda t, m=mode: solve(_lerp(x0, x1, t), m) is not None) if p0 else \
                     (lambda t, m=mode: solve(_lerp(x0, x1, 1.0 - t), m) is not None)
            t = _bisect(inside)
            t = t if p0 else 1.0 - t
            edge = solve(_lerp(x0, x1, t), mode)
            ev = {"between": [i, i + 1], at_key: at(x0, x1, t), **edge_kind(_lerp(x0, x1, t), mode)}
            if edge is not None:
                ev["transmission_deg"] = _fold(edge.direct)
            out.append(ev)
            continue
        if p0 is None:
            continue
        if p0.mode != p1.mode:
            out.append({"kind": "flip", "between": [i, i + 1], "from": p0.mode, "to": p1.mode,
                        "note": "the next pose is on another branch: the linkage passed through or near a lock"})
            continue
        checks = [(k, "in-line", arm_names[k]) for k in range(len(p0.inverse))
                  if p0.inverse[k] is not None and _sign(p0.inverse[k]) * _sign(p1.inverse[k]) < 0]
        if direct_kind and _sign(p0.direct) * _sign(p1.direct) < 0:
            checks.append((None, direct_kind, None))
        for k, kind, arm in checks:
            def same(t, k=k):
                p = solve(_lerp(x0, x1, t), p0.mode)
                if p is None:
                    return True                      # cannot happen between two reachable steps of one branch
                v = p.direct if k is None else p.inverse[k]
                return _sign(v) == _sign(p0.direct if k is None else p0.inverse[k])
            t = _bisect(same)
            ev = {"kind": kind, "between": [i, i + 1], at_key: at(x0, x1, t)}
            if arm:
                ev["arm"] = arm
            out.append(ev)
    return out


# ----------------------------------------------------------------------------- four-bar, crank driven

def sweep_fourbar(a: float, b: float, c: float, d: float, inputs_deg: Sequence[float], *, branch: str = "open",
                  track: str = "hold", guideline_deg: float = GUIDELINE_DEG, lock_deg: float = LOCK_DEG) -> Dict[str, Any]:
    """Turn a four-bar's input crank through ``inputs_deg`` (theta2, from the ground link) and report each pose.

    ``a`` crank, ``b`` coupler, ``c`` rocker, ``d`` ground (Norton's naming); ``branch`` 'open' or 'crossed', the
    assembly to start on (and keep, with ``track='hold'``). Angles per step: theta2, theta3 (coupler) and theta4
    (rocker). Events: ``lock`` where the input runs out of travel (coupler and rocker in line), ``in-line`` where crank
    and coupler line up (the rocker's extreme), ``flip`` where ``track='nearest'`` changes branch. The report also
    carries the Grashof class and the exact input limits from ``cadagent.formulas``, to set the sampled ones against."""
    _check(track, guideline_deg, lock_deg)
    if branch not in ("open", "crossed"):
        raise ValueError(f"branch = {branch!r}: 'open' or 'crossed'")
    if min(a, b, c, d) <= 0:
        raise ValueError("every link must be longer than 0")

    def solve(x, mode) -> Optional[_Pose]:
        t2 = math.radians(x[0])
        r = fx.fourbar_angles(a, b, c, d, t2, crossed=mode < 0)
        if r is None:
            return None
        t3, t4 = r
        # open is the branch with sin(theta4 - theta3) > 0: det_direct = sin(theta4 - theta3), det_inverse = sin(theta3
        # - theta2), as fivebar_jacobians gives for the same linkage (a1 = a, b1 = b, a2 = 0, b2 = c)
        return _Pose(mode, {"B": (a * math.cos(t2), a * math.sin(t2)), "C": (d + c * math.cos(t4), c * math.sin(t4))},
                     {"theta2": t2, "theta3": t3, "theta4": t4}, math.sin(t4 - t3), [math.sin(t3 - t2)])

    inputs = [(float(v),) for v in inputs_deg]
    poses = _track(solve, inputs, 1 if branch == "open" else -1, track)

    def edge(x, mode):
        return {"kind": "lock", "note": "coupler and rocker in one line: the input cannot turn further, and both "
                                        "assemblies meet here"}

    events = _events(inputs, poses, solve, ["theta2"], ["crank"], edge_kind=edge, direct_kind=None)
    for ev in events:
        if ev["kind"] == "in-line":
            ev["note"] = "crank and coupler in one line: the rocker's extreme, where it stops and turns back"
    lim = fx.fourbar_input_limits(a, b, c, d)
    extra = {"grashof": fx.grashof(a, b, c, d),
             "input_limits_deg": {"closes": lim["closes"], "full_turn": lim["full_turn"],
                                  "folded": None if lim["folded"] is None else _deg(lim["folded"]),
                                  "stretched": None if lim["stretched"] is None else _deg(lim["stretched"])}}
    return _report("four-bar", {"a": a, "b": b, "c": c, "d": d}, inputs, ["theta2"], poses, events,
                   mode_name=lambda m: "open" if m > 0 else "crossed", track=track, guideline_deg=guideline_deg,
                   lock_deg=lock_deg, fail_in_line=False, arm_names=["crank"], extra=extra)


def _track(solve: Callable, inputs: Sequence[Tuple[float, ...]], mode: Any, track: str,
           modes: Optional[Callable[[Any], Sequence[Any]]] = None) -> List[Optional[_Pose]]:
    """Solve each step: on ``mode`` throughout ('hold'), or on whichever branch is nearest the last pose ('nearest').
    ``modes(current)`` lists the branches to try, the current one first (default: it and its negative)."""
    modes = modes or (lambda m: (m, -m))
    poses: List[Optional[_Pose]] = []
    last: Optional[_Pose] = None
    current = mode
    for x in inputs:
        if track == "hold":
            pose = solve(x, mode)
        else:
            found = [p for p in (solve(x, m) for m in modes(current)) if p is not None]
            # min() keeps the first of equals, so a tie (at a lock, where branches meet) stays on the current branch
            pose = min(found, key=last.distance) if found and last is not None else (found[0] if found else None)
        poses.append(pose)
        if pose is not None:
            last, current = pose, pose.mode
    return poses


# ----------------------------------------------------------------------------- five-bar, crank driven

def _fivebar_check(a1: float, b1: float, a2: float, b2: float, d: float) -> None:
    if min(a1, b1, a2, b2) <= 0 or d < 0:
        raise ValueError("cranks and distal links must be longer than 0, and the ground 0 or more")


def _fivebar_pose(a1, b1, a2, b2, d, t1, t2, mode) -> Optional[_Pose]:
    """The pose at crank angles t1, t2 (radians) on assembly ``mode``, from ``cadagent.formulas``."""
    j = fx.fivebar_jacobians(a1, b1, a2, b2, d, t1, t2, mode)
    return None if j is None else _fivebar_at(a1, a2, d, t1, t2, j["tip"], mode, j["direct"], list(j["inverse"]))


def _fivebar_at(a1, a2, d, t1, t2, p, mode, direct, inverse) -> _Pose:
    c1 = (a1 * math.cos(t1), a1 * math.sin(t1))
    c2 = (d + a2 * math.cos(t2), a2 * math.sin(t2))
    p1 = math.atan2(p[1] - c1[1], p[0] - c1[0])
    p2 = math.atan2(p[1] - c2[1], p[0] - c2[0])
    return _Pose(mode, {"C1": c1, "C2": c2, "P": (p[0], p[1])},
                 {"theta1": t1, "theta2": t2, "phi1": p1, "phi2": p2,
                  "knee1": math.remainder(p1 - t1, 2 * math.pi), "knee2": math.remainder(p2 - t2, 2 * math.pi)},
                 direct, inverse)


def sweep_fivebar(a1: float, b1: float, a2: float, b2: float, d: float, inputs_deg: Sequence[Tuple[float, float]], *,
                  mode: int = 1, track: str = "hold", guideline_deg: float = GUIDELINE_DEG,
                  lock_deg: float = LOCK_DEG) -> Dict[str, Any]:
    """Move a five-bar's two cranks along a path of angle pairs (theta1 at A, theta2 at B, degrees) and report each
    pose: the tip, the angles (theta1, theta2, the distal links' phi1 and phi2, and each knee's phi - theta), the
    transmission angle between the distal links, and both determinants.

    ``mode`` is the assembly (+1: the tip left of the line from knee 1 to knee 2, as in ``fivebar_point``). Events:
    ``lock`` where the path leaves the reach (the distal links in one line), ``in-line`` where an arm's crank and distal
    link line up on the way, ``flip`` where ``track='nearest'`` changes assembly."""
    _check(track, guideline_deg, lock_deg)
    _fivebar_check(a1, b1, a2, b2, d)
    if mode not in (1, -1):
        raise ValueError(f"mode = {mode!r}: +1 or -1")
    inputs = [(float(t1), float(t2)) for t1, t2 in inputs_deg]

    def solve(x, m):
        return _fivebar_pose(a1, b1, a2, b2, d, math.radians(x[0]), math.radians(x[1]), m)

    poses = _track(solve, inputs, mode, track)

    def edge(x, m):
        return {"kind": "lock", "note": "the distal links in one line: the cranks cannot move the tip further this "
                                        "way, and both assemblies meet here"}

    events = _events(inputs, poses, solve, ["theta1", "theta2"], ["arm1", "arm2"], edge_kind=edge, direct_kind=None)
    return _report("five-bar", {"a1": a1, "b1": b1, "a2": a2, "b2": b2, "d": d}, inputs, ["theta1", "theta2"], poses,
                   events, mode_name=lambda m: m, track=track, guideline_deg=guideline_deg, lock_deg=lock_deg,
                   fail_in_line=False, arm_names=["arm1", "arm2"],
                   extra={"reach": fivebar_reach(a1, b1, a2, b2, d)})


def fivebar_reach(a1: float, b1: float, a2: float, b2: float, d: float) -> List[Dict[str, Any]]:
    """Where a five-bar's tip can be: inside both arms' annuli, |a_i - b_i| <= |P - pivot_i| <= a_i + b_i (Liu, Wang
    and Pritschow). The edges are where an arm's crank and distal link fall into one line."""
    return [{"arm": "arm1", "pivot": [0.0, 0.0], "inner": abs(a1 - b1), "outer": a1 + b1},
            {"arm": "arm2", "pivot": [float(d), 0.0], "inner": abs(a2 - b2), "outer": a2 + b2}]


def fivebar_workspace(a1: float, b1: float, a2: float, b2: float, d: float, theta1_deg: Tuple[float, float],
                      theta2_deg: Tuple[float, float], *, samples: Tuple[int, int] = (73, 73), mode: int = 1,
                      guideline_deg: float = GUIDELINE_DEG, lock_deg: float = LOCK_DEG,
                      cells: bool = False) -> Dict[str, Any]:
    """Sample both cranks of a five-bar on a grid over their ranges (both ends included) on assembly ``mode``, and
    summarise: how much of the grid closes, the ranges each input reaches, the box the tip covers, the lowest
    transmission angle and where, and how many samples are within ``lock_deg`` of a lock or of an arm in line.
    ``cells=True`` adds every sample (for a figure)."""
    _check("hold", guideline_deg, lock_deg)
    _fivebar_check(a1, b1, a2, b2, d)
    n1, n2 = (int(v) for v in samples)
    if n1 < 2 or n2 < 2:
        raise ValueError("samples must be at least 2 along each input")
    grid, worst = [], None
    for i in range(n1):
        t1 = theta1_deg[0] + (theta1_deg[1] - theta1_deg[0]) * i / (n1 - 1)
        for k in range(n2):
            t2 = theta2_deg[0] + (theta2_deg[1] - theta2_deg[0]) * k / (n2 - 1)
            p = _fivebar_pose(a1, b1, a2, b2, d, math.radians(t1), math.radians(t2), mode)
            row: Dict[str, Any] = {"theta1": t1, "theta2": t2, "reachable": p is not None}
            if p is not None:
                row.update(tip=list(p.pins["P"]), transmission_deg=_fold(p.direct),
                           in_line_deg=[_fold(v) for v in p.inverse])
                if worst is None or row["transmission_deg"] < worst["transmission_deg"]:
                    worst = row
            grid.append(row)
    ok = [r for r in grid if r["reachable"]]
    out: Dict[str, Any] = {"schema_version": 1, "kind": "five-bar workspace",
                           "links": {"a1": a1, "b1": b1, "a2": a2, "b2": b2, "d": d}, "mode": mode,
                           "samples": [n1, n2], "theta1_deg": list(theta1_deg), "theta2_deg": list(theta2_deg),
                           "reach": fivebar_reach(a1, b1, a2, b2, d),
                           "reachable": len(ok), "cells_total": len(grid), "limits": LIMITS}
    if ok:
        xs, ys = [r["tip"][0] for r in ok], [r["tip"][1] for r in ok]
        out.update(input_ranges_deg={"theta1": [min(r["theta1"] for r in ok), max(r["theta1"] for r in ok)],
                                     "theta2": [min(r["theta2"] for r in ok), max(r["theta2"] for r in ok)]},
                   tip_box=[min(xs), min(ys), max(xs), max(ys)],
                   min_transmission_deg=worst["transmission_deg"],
                   min_transmission_at_deg={"theta1": worst["theta1"], "theta2": worst["theta2"]},
                   near_lock=sum(r["transmission_deg"] < lock_deg for r in ok),
                   below_guideline=sum(lock_deg <= r["transmission_deg"] < guideline_deg for r in ok),
                   near_in_line=[sum(r["in_line_deg"][k] < lock_deg for r in ok) for k in (0, 1)])
    if cells:
        out["cells"] = grid
    return out


# ----------------------------------------------------------------------------- five-bar, tip driven

def sweep_fivebar_tip(a1: float, b1: float, a2: float, b2: float, d: float, path: Sequence[Point], *,
                      working: Tuple[int, int] = (-1, 1), track: str = "hold", guideline_deg: float = GUIDELINE_DEG,
                      lock_deg: float = LOCK_DEG) -> Dict[str, Any]:
    """Move a five-bar's tip along ``path`` (points in the frame A = (0, 0), B = (d, 0)) and solve its cranks on the
    ``working`` modes (each arm +1 where its distal link turns counter-clockwise from its crank; the default (-1, +1)
    has both knees out, with the tip above the ground). This is how a leg is driven by its foot's path.

    Events: ``in-line`` where an arm reaches the edge of its reach (out of the path's reach beyond it, or crossing
    into the other working mode with ``track='nearest'``), ``lock`` where the path crosses a lock (the distal links in
    line: the cranks cannot hold the tip there, and the assembly changes), and ``flip``. A step within ``lock_deg`` of
    either kind fails: there the cranks must turn without bound, or cannot hold the tip."""
    _check(track, guideline_deg, lock_deg)
    _fivebar_check(a1, b1, a2, b2, d)
    if len(working) != 2 or any(w not in (1, -1) for w in working):
        raise ValueError(f"working = {working!r}: two signs, each +1 or -1")
    inputs = [(float(x), float(y)) for x, y in path]

    def cross(u, v):
        return u[0] * v[1] - u[1] * v[0]

    def solve(x, w) -> Optional[_Pose]:
        th = fx.fivebar_inputs(a1, b1, a2, b2, d, x[0], x[1], w)
        if th is None:
            return None
        c1 = (a1 * math.cos(th[0]), a1 * math.sin(th[0]))
        c2 = (d + a2 * math.cos(th[1]), a2 * math.sin(th[1]))
        # the determinants as fivebar_jacobians defines them, at the tip the path puts there
        direct = cross((c2[0] - c1[0], c2[1] - c1[1]), (x[0] - c1[0], x[1] - c1[1])) / (b1 * b2)
        inverse = [cross(c1, (x[0] - c1[0], x[1] - c1[1])) / (a1 * b1),
                   cross((c2[0] - d, c2[1]), (x[0] - c2[0], x[1] - c2[1])) / (a2 * b2)]
        return _fivebar_at(a1, a2, d, th[0], th[1], x, tuple(w), max(-1.0, min(1.0, direct)),
                           [max(-1.0, min(1.0, v)) for v in inverse])

    def modes(cur):
        w1, w2 = cur
        return [(w1, w2), (-w1, w2), (w1, -w2), (-w1, -w2)]

    poses = _track(solve, inputs, tuple(working), track, modes)
    reach = fivebar_reach(a1, b1, a2, b2, d)

    def edge(x, w):
        # the arm whose annulus the edge point lies on
        gaps = []
        for r in reach:
            dist = math.dist(x, r["pivot"])
            gaps.append((min(abs(dist - r["inner"]), abs(dist - r["outer"])), r["arm"]))
        return {"kind": "in-line", "arm": min(gaps)[1],
                "note": "the edge of the arm's reach: its crank and distal link in one line"}

    events = _events(inputs, poses, solve, ["x", "y"], ["arm1", "arm2"], edge_kind=edge, direct_kind="lock",
                     at_key="at")
    for ev in events:
        if ev["kind"] == "lock":
            ev["note"] = "the path crosses a lock: the distal links in one line, where the cranks cannot hold the tip"
        elif ev["kind"] == "in-line" and "note" not in ev:
            ev["note"] = "an arm passes its crank and distal link in one line"
        elif ev["kind"] == "flip":
            ev["note"] = "an arm changes working mode between the steps: it passed its crank and distal link in line"
    rep = _report("five-bar, tip driven", {"a1": a1, "b1": b1, "a2": a2, "b2": b2, "d": d}, inputs, ["x", "y"], poses,
                  events, mode_name=lambda w: list(w), track=track, guideline_deg=guideline_deg, lock_deg=lock_deg,
                  fail_in_line=True, arm_names=["arm1", "arm2"], extra={"reach": reach}, input_key="tip",
                  branch_key="working")
    for s in rep["steps"]:
        if s["reachable"]:
            s["assembly"] = _sign(s["det_direct"])    # follows the path; it changes where the path crosses a lock
    return rep


# ----------------------------------------------------------------------------- dyads measured from CAD

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
    """A planar linkage measured from CAD, moved along a path joint by joint.

    ``ground``: fixed joints {name: (u, v)}; ``links``: {body: (joint, joint)}; ``reference``: every joint in the pose
    the CAD was built in; ``solve``: [(joint, from_a, from_b)] in order, each joint from two known ones as an
    intersection of two circles (a dyad). Of the two intersections, the one nearest the joint's previous position is
    taken, so the pose moves continuously from the reference pose and never jumps to the other branch. That covers
    four-bars driven by an output point, five-bars driven by their tip, and chains of dyads. A path point no pose can
    reach raises ``ValueError``; the continuity rule needs path steps small next to the links."""
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

    def sides(self, pose: Mapping[str, Point]) -> Dict[str, int]:
        """Each solved joint's branch: +1 where it lies left of the line from its first known joint to its second, -1
        right, 0 in line. A change between poses is a branch flip; the nearest rule should never make one."""
        out = {}
        for name, a, b in self.solve:
            pa, pb, pj = pose[a], pose[b], pose[name]
            out[name] = _sign((pb[0] - pa[0]) * (pj[1] - pa[1]) - (pb[1] - pa[1]) * (pj[0] - pa[0]))
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
