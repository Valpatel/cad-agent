"""Compare rendered landmarks with independent CAD joint intent, without a CAD kernel.

All points/axes are in the assembly's home frame, in mm; angles are right-handed degrees.
Child axes ride on ancestors. Observations come from the rendered scene, not this oracle.
This verifies sampled kinematics, not collisions, continuous motion or physical safety.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np

SCHEMA_VERSION = 1
FRAME = "assembly-home"
LIMITS = [
    "Reference datums and component ownership must be independent of the renderer under test; "
    "matching an incorrect shared manifest proves nothing about mechanical intent.",
    "Only supplied landmarks and sampled joint poses are checked. This is not a swept-volume, "
    "collision, force, speed, timing, hardware safety or physical-fit validation.",
    "Four affinely independent points identify a rigid transform, but do not prove the right "
    "mesh, complete geometry, or correct reference coordinates were captured.",
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
            raise ValueError(f"joint hierarchy has a cycle at {name}")
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


def _required(joints: dict) -> list[dict[str, float]]:
    home = dict.fromkeys(joints, 0.0)
    poses = [home]
    for name, joint in joints.items():
        lo, hi = joint["range"]
        count = max(4, math.ceil((hi - lo) / 90))
        if count > 4096:
            raise ValueError(f"joint {name}: range requires more than 4096 intervals; validate bounded cycles")
        values = [lo + i * (hi - lo) / count for i in range(count + 1)]
        for value in values:
            poses.append({**home, name: value})
        # A full turn at either endpoint can look identical to home. Exercise a nontrivial
        # orientation with each ancestor, not only independent joints at home.
        turn = max(values, key=lambda a: abs(math.sin(math.radians(a) / 2)))
        parent = joint["parent"]
        while parent is not None:
            a, b = joints[parent]["range"]
            n = max(4, math.ceil((b - a) / 90))
            if n > 4096:
                raise ValueError(f"joint {parent}: range requires more than 4096 intervals; validate bounded cycles")
            other = max((a + i * (b - a) / n for i in range(n + 1)),
                        key=lambda angle: abs(math.sin(math.radians(angle) / 2)))
            poses.append({**home, name: turn, parent: other})
            parent = joints[parent]["parent"]
    unique = {}
    for pose in poses:
        unique[tuple(pose.values())] = pose
    return list(unique.values())


def required_poses(contract: Mapping) -> list[dict[str, float]]:
    """Home, at least five range samples (at most 90 degrees apart), and ancestor/child poses.

    Use these as input poses for the renderer capture. They are coverage requirements, not
    predicted observations. Add actual firing/transition trajectories to the same trace.
    """
    joints, _, _ = _contract(contract)
    return _required(joints)


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
    _mapping(trace, "trace")
    _header(trace, "capture_source")
    samples = trace.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples: expected a nonempty list")
    ids, observed_poses, failures = set(), [], []
    summary = {name: {"points": len(c["points"]), "joint": c["joint"], "max_error_mm": 0.,
                      "max_anchor_error_mm": 0., "max_radius_error_mm": 0., "worst_sample": None}
               for name, c in components.items()}
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
    required = _required(joints)
    missing = [p for p in required if not any(all(abs(q[n] - v) <= 1e-7 for n, v in p.items())
                                             for q in observed_poses)]
    if missing:
        failures.append({"check": "pose-coverage", "missing_poses_deg": missing})
    for name, row in summary.items():
        if row["max_error_mm"] > tolerance_mm:
            failures.append({"check": "rendered-landmarks", "component": name, **row})
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
            "components": summary, "failures": failures, "limits": LIMITS}
