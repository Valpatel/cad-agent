"""Compare rendered landmarks with independent CAD joint intent, without a CAD kernel.

All points/axes are in the assembly's home frame, in mm; angles are right-handed degrees.
Child axes ride on ancestors. Observations come from the rendered scene, not this oracle.
This verifies sampled kinematics, not collisions, continuous motion or physical safety.

Joints form a tree. A closed loop (a four-bar or five-bar) is declared on top of it (#187): cut the loop at one pin,
give each joint its parent as a tree, and list the loop under ``loops`` with the two joints that meet at the pin
and the joints that drive it. Its other joints follow from the link lengths (``cadagent.mechanical.linkages``), so
the required poses sample the inputs only, and each sample's loop must close where the solver closes it.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from typing import Any, Mapping, Optional

import numpy as np

from cadagent import formulas as fx

SCHEMA_VERSION = 1
FRAME = "assembly-home"
LIMITS = [
    "Reference datums and component ownership must be independent of the renderer under test; "
    "matching an incorrect shared manifest proves nothing about mechanical intent.",
    "Only supplied landmarks and sampled joint poses are checked. This is not a swept-volume, "
    "collision, force, speed, timing, hardware safety or physical-fit validation.",
    "Four affinely independent points identify a rigid transform, but do not prove the right "
    "mesh, complete geometry, or correct reference coordinates were captured.",
    "A declared loop is solved as rigid links on ideal pins in one plane, on the assembly it has at home; "
    "the renderer's loop must match that solution, and a loop that changes assembly at a lock fails.",
]


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: expected a finite number")
    return float(value)


def _vector(value: Any, where: str, size: int = 3) -> np.ndarray:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{where}: expected {size} numbers")
    return np.array([_number(v, where) for v in value])


def _mapping(value: Any, where: str, *, empty: bool = False) -> Mapping:
    if not isinstance(value, dict) or (not empty and not value):
        raise ValueError(f"{where}: expected a {'possibly empty ' if empty else 'nonempty '}mapping")
    if any(not isinstance(k, str) or not k for k in value):
        raise ValueError(f"{where}: keys must be nonempty strings")
    return value


def _header(data: Mapping, provenance: str) -> None:
    if data.get("schema_version") != SCHEMA_VERSION or isinstance(data.get("schema_version"), bool):
        raise ValueError("schema_version must be 1")
    if data.get("length_unit") != "mm" or data.get("frame") != FRAME:
        raise ValueError("length_unit must be 'mm' and frame must be 'assembly-home'; convert captures explicitly")
    if not isinstance(data.get(provenance), str) or not data[provenance].strip():
        raise ValueError(f"{provenance}: describe the source and revision of this evidence")


def _points(value: Any, where: str, *, reference: bool = False) -> np.ndarray:
    if not isinstance(value, list) or len(value) < 4:
        raise ValueError(f"{where}: at least four ordered landmark points are required")
    result = np.array([_vector(v, where) for v in value])
    if reference and np.linalg.matrix_rank(result - result[0]) != 3:
        raise ValueError(f"{where}: landmarks must be affinely independent (not coplanar)")
    return result


def _contract(data: Mapping) -> tuple[dict, dict, list[str]]:
    _mapping(data, "contract")
    _header(data, "reference")
    joints = {}
    for name, raw in _mapping(data.get("joints"), "joints").items():
        _mapping(raw, f"joint {name}")
        axis = _vector(raw.get("axis"), f"joint {name} axis")
        norm = float(np.linalg.norm(axis))
        if not math.isfinite(norm) or norm < 1e-12:
            raise ValueError(f"joint {name}: axis must be nonzero")
        lo, hi = _vector(raw.get("range_deg"), f"joint {name} range_deg", 2)
        if not lo <= 0 <= hi or lo >= hi:
            raise ValueError(f"joint {name}: range must be increasing, nonzero and include home (0 degrees)")
        if "parent" not in raw:
            raise ValueError(f"joint {name}: declare parent explicitly (null for the root)")
        parent = raw["parent"]
        if parent is not None and (not isinstance(parent, str) or parent not in data["joints"]):
            raise ValueError(f"joint {name}: unknown parent {parent!r}")
        joints[name] = {"parent": parent, "pivot": _vector(raw.get("pivot"), f"joint {name} pivot"),
                        "axis": axis / norm, "range": (float(lo), float(hi))}
    order, active = [], set()

    def visit(name):
        if name in active:
            raise ValueError(f"joint hierarchy has a cycle at {name}: give the joints a tree of parents and declare "
                             "the closed loop under loops")
        if name in order:
            return
        active.add(name)
        parent = joints[name]["parent"]
        if parent is not None:
            visit(parent)
        active.remove(name)
        order.append(name)

    for name in joints:
        visit(name)
    components = {}
    for name, raw in _mapping(data.get("components"), "components").items():
        _mapping(raw, f"component {name}")
        if "joint" not in raw:
            raise ValueError(f"component {name}: declare joint explicitly (null for stationary assembly frame)")
        owner = raw["joint"]
        if owner is not None and (not isinstance(owner, str) or owner not in joints):
            raise ValueError(f"component {name}: unknown owning joint {owner!r}")
        components[name] = {"joint": owner, "points": _points(raw.get("points"), f"component {name}", reference=True)}
    carried = {c["joint"] for c in components.values()}
    for name in list(carried - {None}):
        while joints[name]["parent"] is not None:
            name = joints[name]["parent"]
            carried.add(name)
    if set(joints) - carried:
        raise ValueError(f"joints have no captured components: {sorted(set(joints) - carried)}")
    return joints, components, order


def _loops(data: Mapping, joints: dict) -> dict:
    """The ``loops`` section: ``{name: {"closes": [joint, joint], "pin": [x, y, z], "inputs": [joint, ...]}}``.

    The two closing joints' links meet at ``pin`` (home coordinates). Each runs back through its parents to where the
    two chains meet (a shared parent, or the fixed frame), in one or two joints: a four-bar has two and one, a five-bar
    two and two. The first joint of a two-joint chain is an input. Every joint of a loop turns about parallel axes."""
    raw = data.get("loops")
    if raw is None:
        return {}
    _mapping(raw, "loops", empty=True)
    out, used = {}, {}

    def lineage(j):
        chain = []
        while j is not None:
            chain.append(j)
            j = joints[j]["parent"]
        return chain

    for name, spec in raw.items():
        _mapping(spec, f"loop {name}")
        closes, inputs = spec.get("closes"), spec.get("inputs")
        if (not isinstance(closes, list) or len(closes) != 2 or closes[0] == closes[1]
                or any(not isinstance(j, str) or j not in joints for j in closes)):
            raise ValueError(f"loop {name}: closes must name two different joints")
        if not isinstance(inputs, list) or any(not isinstance(j, str) for j in inputs) or len(set(inputs)) != len(inputs):
            raise ValueError(f"loop {name}: inputs must list its driving joints once each")
        pin = _vector(spec.get("pin"), f"loop {name} pin")
        l1, l2 = lineage(closes[0]), lineage(closes[1])
        shared = set(l1) & set(l2)
        if closes[0] in shared or closes[1] in shared:
            raise ValueError(f"loop {name}: one closing joint carries the other; a loop needs two chains that meet at "
                             "the pin")
        chains = [[j for j in l if j not in shared][::-1] for l in (l1, l2)]       # from the shared frame outwards
        frame = next((j for j in l1 if j in shared), None)
        if any(not 1 <= len(c) <= 2 for c in chains) or len(chains[0]) + len(chains[1]) < 3:
            raise ValueError(f"loop {name}: each chain from where they meet to the pin must have one or two joints, "
                             "three or four in all (a four-bar or a five-bar)")
        want = [c[0] for c in chains if len(c) == 2]
        if sorted(inputs) != sorted(want):
            raise ValueError(f"loop {name}: its inputs are the first joint of each two-joint chain, {want}; drive a "
                             "four-bar from its other end by rebuilding the tree from that end")
        members = chains[0] + chains[1]
        for j in members:
            if j in used:
                raise ValueError(f"loop {name}: joint {j} is in loop {used[j]} too; one loop per joint")
            used[j] = name
        n = joints[chains[0][0]]["axis"]
        signs = {}
        for j in members:
            axis = joints[j]["axis"]
            if np.linalg.norm(np.cross(axis, n)) > 1e-9:
                raise ValueError(f"loop {name}: joint {j}'s axis is not parallel to {chains[0][0]}'s; a loop here is "
                                 "planar")
            signs[j] = 1.0 if float(axis @ n) > 0 else -1.0
        # a basis (u, v) of the plane, right-handed about n, with u from the first chain's pivot to the second's
        origin = joints[chains[0][0]]["pivot"]

        def flat(p):
            q = p - origin
            return q - (q @ n) * n

        gap = flat(joints[chains[1][0]]["pivot"])
        if np.linalg.norm(gap) > 1e-9:
            u = gap / np.linalg.norm(gap)
        else:
            helper = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
            u = np.cross(n, helper)
            u /= np.linalg.norm(u)
        v = np.cross(n, u)

        def plane(p):
            q = flat(p)
            return (float(q @ u), float(q @ v))

        P = plane(pin)
        arms = []
        for c in chains:
            pivot = plane(joints[c[0]]["pivot"])
            knee = plane(joints[c[1]]["pivot"]) if len(c) == 2 else pivot
            a, b = math.dist(pivot, knee), math.dist(knee, P)
            if len(c) == 2 and a < 1e-6:
                raise ValueError(f"loop {name}: joints {c[0]} and {c[1]} share a pivot; a crank needs a length")
            if b < 1e-6:
                raise ValueError(f"loop {name}: the pin lies on joint {c[-1]}'s axis")
            theta0 = math.atan2(knee[1] - pivot[1], knee[0] - pivot[0]) if len(c) == 2 else 0.0
            arms.append({"chain": c, "pivot": pivot, "knee": knee, "a": a, "b": b, "theta0": theta0,
                         "phi0": math.atan2(P[1] - knee[1], P[0] - knee[0])})
        k1, k2 = arms[0]["knee"], arms[1]["knee"]
        side = (k2[0] - k1[0]) * (P[1] - k1[1]) - (k2[1] - k1[1]) * (P[0] - k1[0])
        if abs(side) <= 1e-9 * arms[0]["b"] * arms[1]["b"]:
            raise ValueError(f"loop {name}: at home its last two links are in one line (a lock); build it in a pose "
                             "where they are not")
        out[name] = {"chains": chains, "frame": frame, "inputs": list(inputs),
                     "dependent": [j for j in members if j not in inputs], "joints": members, "signs": signs,
                     "arms": arms, "d": arms[1]["pivot"][0], "mode": 1 if side > 0 else -1, "pin": P,
                     "kind": "four-bar" if len(members) == 3 else "five-bar"}
    return out


def _loop_solve(loop: dict, joints: dict, angles: Mapping[str, float]) -> Optional[dict]:
    """The loop's dependent joint angles (degrees from home) for its inputs in ``angles``, on its home assembly, each
    put in its joint's range where a turn of 360 degrees allows; None where the inputs cannot close the loop."""
    arms, s = loop["arms"], loop["signs"]
    thetas = [arm["theta0"] + (s[arm["chain"][0]] * math.radians(angles[arm["chain"][0]])
                               if len(arm["chain"]) == 2 else 0.0) for arm in arms]
    tip = fx.fivebar_point(arms[0]["a"], arms[0]["b"], arms[1]["a"], arms[1]["b"], loop["d"], thetas[0], thetas[1],
                           loop["mode"])
    if tip is None:
        return None
    out = {}
    for arm, theta in zip(arms, thetas):
        pivot = arm["pivot"]
        knee = (pivot[0] + arm["a"] * math.cos(theta), pivot[1] + arm["a"] * math.sin(theta))
        turn = math.atan2(tip[1] - knee[1], tip[0] - knee[0]) - arm["phi0"]        # the last link's turn in the plane
        last = arm["chain"][-1]
        rel = turn - (theta - arm["theta0"]) if len(arm["chain"]) == 2 else turn
        deg = math.remainder(s[last] * math.degrees(rel), 360.0)
        lo, hi = joints[last]["range"]
        out[last] = next((x for x in (deg, deg + 360.0, deg - 360.0) if lo - 1e-8 <= x <= hi + 1e-8), deg)
    return out


def _loop_error(loop: dict, angles: Mapping[str, float]) -> float:
    """How far (mm) the loop's pins, carried by each chain at ``angles``, are from where the solver puts them for the
    same inputs: 0 for a closed loop on the home assembly. Infinite where the inputs cannot close it."""
    arms, s = loop["arms"], loop["signs"]
    thetas = [arm["theta0"] + (s[arm["chain"][0]] * math.radians(angles[arm["chain"][0]])
                               if len(arm["chain"]) == 2 else 0.0) for arm in arms]
    tip = fx.fivebar_point(arms[0]["a"], arms[0]["b"], arms[1]["a"], arms[1]["b"], loop["d"], thetas[0], thetas[1],
                           loop["mode"])
    if tip is None:
        return math.inf
    worst = 0.0
    for arm, theta in zip(arms, thetas):
        pivot, c = arm["pivot"], arm["chain"]
        knee = (pivot[0] + arm["a"] * math.cos(theta), pivot[1] + arm["a"] * math.sin(theta))
        turn = (theta - arm["theta0"]) + s[c[-1]] * math.radians(angles[c[-1]]) if len(c) == 2 else \
            s[c[0]] * math.radians(angles[c[0]])
        r0 = (loop["pin"][0] - arm["knee"][0], loop["pin"][1] - arm["knee"][1])
        carried = (knee[0] + r0[0] * math.cos(turn) - r0[1] * math.sin(turn),
                   knee[1] + r0[0] * math.sin(turn) + r0[1] * math.cos(turn))
        worst = max(worst, math.dist(carried, tip))
    return worst


def _samples(name: str, joint: dict) -> list[float]:
    lo, hi = joint["range"]
    count = max(4, math.ceil((hi - lo) / 90))
    if count > 4096:
        raise ValueError(f"joint {name}: range requires more than 4096 intervals; validate bounded cycles")
    return [lo + i * (hi - lo) / count for i in range(count + 1)]


def _far(values) -> float:
    """The sample farthest from home as an orientation (a full turn looks like home)."""
    return max(values, key=lambda a: abs(math.sin(math.radians(a) / 2)))


def _required(joints: dict, loops: Optional[dict] = None) -> list[dict[str, float]]:
    loops = loops or {}
    home = dict.fromkeys(joints, 0.0)
    poses = [home]
    loop_of = {j: name for name, lp in loops.items() for j in lp["joints"]}
    far_loop = {}
    # A loop's inputs are sampled together (every input sample against every other) and its other joints solved; a
    # combination the loop cannot close is not a pose.
    for name, lp in loops.items():
        best = None
        for combo in itertools.product(*(_samples(j, joints[j]) for j in lp["inputs"])):
            angles = {**home, **dict(zip(lp["inputs"], combo))}
            dep = _loop_solve(lp, joints, angles)
            if dep is None:
                continue
            for j, v in dep.items():
                lo, hi = joints[j]["range"]
                if not lo - 1e-8 <= v <= hi + 1e-8:
                    raise ValueError(f"loop {name}: at inputs {dict(zip(lp['inputs'], combo))} joint {j} is at "
                                     f"{v:.6g} degrees, outside its range: widen the range or narrow the inputs")
            pose = {**angles, **dep}
            poses.append(pose)
            score = sum(abs(math.sin(math.radians(pose[j]) / 2)) for j in lp["joints"])
            if best is None or score > best[0]:
                best = (score, {j: pose[j] for j in lp["joints"]})
        if best is None:
            raise ValueError(f"loop {name}: no sampled input closes the loop")
        far_loop[name] = best[1]

    def with_ancestors(base: dict, parent) -> None:
        # each ancestor at a nontrivial orientation with the joint (or loop) it carries; a loop ancestor moves as
        # its loop, never alone
        while parent is not None:
            if parent in loop_of:
                lp = loops[loop_of[parent]]
                poses.append({**home, **base, **far_loop[loop_of[parent]]})
                parent = lp["frame"]
                continue
            poses.append({**home, **base, parent: _far(_samples(parent, joints[parent]))})
            parent = joints[parent]["parent"]

    for name, joint in joints.items():
        if name in loop_of:
            continue
        values = _samples(name, joint)
        for value in values:
            poses.append({**home, name: value})
        # A full turn at either endpoint can look identical to home. Exercise a nontrivial
        # orientation with each ancestor, not only independent joints at home.
        with_ancestors({name: _far(values)}, joint["parent"])
    for name, lp in loops.items():
        with_ancestors(far_loop[name], lp["frame"])
    unique = {}
    for pose in poses:
        # a solved joint at home comes back as round-off (1e-15 degrees), not 0: the same pose
        unique.setdefault(tuple(round(v, 9) + 0.0 for v in pose.values()), pose)
    return list(unique.values())


def required_poses(contract: Mapping) -> list[dict[str, float]]:
    """Home, at least five range samples (at most 90 degrees apart), and ancestor/child poses.

    A declared loop's inputs are sampled together and its other joints solved, so every pose closes the loop.
    Use these as input poses for the renderer capture. They are coverage requirements, not
    predicted observations. Add actual firing/transition trajectories to the same trace.
    """
    joints, _, _ = _contract(contract)
    return _required(joints, _loops(contract, joints))


def _rotation(pivot: np.ndarray, axis: np.ndarray, degrees: float) -> np.ndarray:
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    angle = math.radians(degrees)
    r = np.eye(3) + math.sin(angle) * skew + (1 - math.cos(angle)) * (skew @ skew)
    result = np.eye(4)
    result[:3, :3] = r
    result[:3, 3] = pivot - r @ pivot
    return result


def _matrices(joints: dict, order: list[str], angles: dict) -> dict:
    mats = {None: np.eye(4)}
    for name in order:
        joint = joints[name]
        mats[name] = mats[joint["parent"]] @ _rotation(joint["pivot"], joint["axis"], angles[name])
    return mats


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def _digest(data: Mapping) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_motion_trace(contract: Mapping, trace: Mapping, *, tolerance_mm: float = .01) -> dict:
    """Return a JSON-safe verdict; malformed evidence raises ValueError, mismatches fail.

    The report binds the supplied reference and capture with content hashes. It cannot certify
    their independence or truth: that is an evidence-review requirement, not a JSON property.
    """
    tolerance_mm = _number(tolerance_mm, "tolerance_mm")
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm must be positive")
    joints, components, order = _contract(contract)
    loops = _loops(contract, joints)
    _mapping(trace, "trace")
    _header(trace, "capture_source")
    samples = trace.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples: expected a nonempty list")
    ids, observed_poses, failures = set(), [], []
    summary = {name: {"points": len(c["points"]), "joint": c["joint"], "max_error_mm": 0.,
                      "max_anchor_error_mm": 0., "max_radius_error_mm": 0., "worst_sample": None}
               for name, c in components.items()}
    loop_rows = {name: {"kind": lp["kind"], "inputs": lp["inputs"], "dependent": lp["dependent"],
                        "links_mm": [{"crank": arm["a"], "link": arm["b"]} for arm in lp["arms"]],
                        "ground_mm": abs(lp["d"]), "max_pose_error_mm": 0., "worst_sample": None,
                        "unreachable_samples": []}
                 for name, lp in loops.items()}
    for sample in samples:
        _mapping(sample, "sample")
        sid = sample.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError("sample ids must be nonempty and unique")
        ids.add(sid)
        raw_angles = _mapping(sample.get("angles_deg"), f"sample {sid} angles_deg")
        if set(raw_angles) != set(joints):
            raise ValueError(f"sample {sid}: angles_deg must name every joint exactly once")
        angles = {name: _number(v, f"sample {sid} angle {name}") for name, v in raw_angles.items()}
        for name, angle in angles.items():
            lo, hi = joints[name]["range"]
            if not lo - 1e-8 <= angle <= hi + 1e-8:
                raise ValueError(f"sample {sid}: {name} angle outside reference range")
        observed_poses.append(angles)
        for name, lp in loops.items():
            err, row = _loop_error(lp, angles), loop_rows[name]
            if math.isinf(err):
                row["unreachable_samples"].append(sid)
            elif row["worst_sample"] is None or err > row["max_pose_error_mm"]:
                row.update(max_pose_error_mm=err, worst_sample=sid)
        observed = _mapping(sample.get("components"), f"sample {sid} components")
        if set(observed) != set(components):
            raise ValueError(f"sample {sid}: components must name every component exactly once")
        matrices = _matrices(joints, order, angles)
        for name, component in components.items():
            actual = _points(observed[name], f"sample {sid} component {name}")
            home, owner = component["points"], component["joint"]
            if actual.shape != home.shape:
                raise ValueError(f"sample {sid} component {name}: landmark count differs from reference")
            expected = _apply(matrices[owner], home)
            errors = np.linalg.norm(actual - expected, axis=1)
            error = float(np.max(errors))
            row = summary[name]
            if row["worst_sample"] is None or error > row["max_error_mm"]:
                row.update(max_error_mm=error, worst_sample=sid, worst_point=int(np.argmax(errors)))
            if owner is not None:
                joint = joints[owner]
                # Infer the actual affine map from independently specified home landmarks.
                # The full point comparison above remains the verdict; these diagnose pivot/orbit drift.
                fit, *_ = np.linalg.lstsq(np.column_stack((home, np.ones(len(home)))), actual, rcond=None)
                actual_pivot = np.append(joint["pivot"], 1) @ fit
                parent_matrix = matrices[joint["parent"]]
                expected_pivot = _apply(parent_matrix, joint["pivot"])
                anchor_error = float(np.linalg.norm(actual_pivot - expected_pivot))
                local = _apply(np.linalg.inv(parent_matrix), actual) - joint["pivot"]
                rest = home - joint["pivot"]
                radius = lambda p: np.linalg.norm(p - np.outer(p @ joint["axis"], joint["axis"]), axis=1)
                radius_error = float(np.max(np.abs(radius(local) - radius(rest))))
                row["max_anchor_error_mm"] = max(row["max_anchor_error_mm"], anchor_error)
                row["max_radius_error_mm"] = max(row["max_radius_error_mm"], radius_error)
    required = _required(joints, loops)
    # a loop's dependent joints follow from its inputs, and the loop-pose check holds them to the solution
    solved = {j for lp in loops.values() for j in lp["dependent"]}
    missing = [p for p in required if not any(all(abs(q[n] - v) <= 1e-7 for n, v in p.items() if n not in solved)
                                             for q in observed_poses)]
    if missing:
        failures.append({"check": "pose-coverage", "missing_poses_deg": missing})
    for name, row in summary.items():
        if row["max_error_mm"] > tolerance_mm:
            failures.append({"check": "rendered-landmarks", "component": name, **row})
    for name, row in loop_rows.items():
        if row["unreachable_samples"] or row["max_pose_error_mm"] > tolerance_mm:
            failures.append({"check": "loop-pose", "loop": name, **row})
    # Report sample spacing, including its limits. Time/rotation speed are not inferred from these poses.
    spacing = {}
    for name, joint in joints.items():
        values = sorted(set(p[name] for p in observed_poses))
        spacing[name] = {"sampled_angles_deg": values,
                         "max_gap_deg": max((b - a for a, b in zip(values, values[1:])), default=0.)}
    return {"schema_version": 1, "status": "fail" if failures else "pass", "tolerance_mm": tolerance_mm,
            "reference": contract["reference"], "capture_source": trace["capture_source"],
            "contract_sha256": _digest(contract), "trace_sha256": _digest(trace),
            "sample_count": len(samples), "required_pose_count": len(required), "coverage": spacing,
            "components": summary, **({"loops": loop_rows} if loops else {}), "failures": failures, "limits": LIMITS}
