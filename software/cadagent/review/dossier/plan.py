"""Bounded manufacturing intent in the existing dossier: serial rigid translations only.

Normalization validates declarations, not their physical truth. Consumers bind this resource's bytes;
geometry and independently inspected intent are separate evidence.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Mapping

PLAN_SCHEMA = "cad-agent.assembly-plan/1"
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def normalize_plan(value: Any, *, mesh_hashes: Mapping[str, str] | None = None):
    """Return an isolated JSON plan; reject unsupported semantics rather than flatten/fallback."""
    def fields(obj, allowed, required=None):
        if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required or allowed) - set(obj):
            raise ValueError("assembly plan: missing or unsupported fields")

    def text(v):
        return isinstance(v, str) and bool(v.strip()) and len(v) <= 2000

    def finite(v):
        return type(v) in (int, float) and abs(v) <= 1e9 and math.isfinite(v)

    def vector(v):
        return isinstance(v, list) and len(v) == 3 and all(finite(n) for n in v)

    def refs(v, allowed, nonempty=False):
        if (not isinstance(v, list) or (nonempty and not v) or len(v) > 2000
                or any(not isinstance(n, str) or n not in allowed for n in v) or len(set(v)) != len(v)):
            raise ValueError("assembly plan: unknown, duplicate or missing members")

    fields(value, ("schema", "units", "frame", "source", "fixed", "operations", "clearance_mm"))
    if value["schema"] != PLAN_SCHEMA or value["units"] != "mm" or value["frame"] != "assembly-home/z-up":
        raise ValueError("assembly plan: unsupported schema/units/frame")
    if not finite(value["clearance_mm"]) or value["clearance_mm"] < 0:
        raise ValueError("assembly plan: finite nonnegative clearance allowance required")
    source = value["source"]
    fields(source, ("revision", "closure_sha256", "producer", "instances", "tooling_sha256"))
    if (not isinstance(source["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", source["revision"])
            or not isinstance(source["closure_sha256"], str) or not _HASH.fullmatch(source["closure_sha256"])
            or not isinstance(source["tooling_sha256"], str) or not _HASH.fullmatch(source["tooling_sha256"])
            or not text(source["producer"]) or not isinstance(source["instances"], dict)
            or not 1 <= len(source["instances"]) <= 2000):
        raise ValueError("assembly plan: exact source closure/producer required")
    names = set(source["instances"])
    for name, entry in source["instances"].items():
        fields(entry, ("mesh_sha256", "brep_sha256", "matrix"))
        if not text(name) or len(name) > 200 or any(not isinstance(entry[k], str) or not _HASH.fullmatch(entry[k])
                                                 for k in ("mesh_sha256", "brep_sha256")):
            raise ValueError("assembly plan: invalid source instance")
        m = entry["matrix"]
        if not isinstance(m, list) or len(m) != 12 or not all(finite(n) for n in m):
            raise ValueError("assembly plan: invalid placement")
        rows = [m[i:i + 3] for i in (0, 4, 8)]
        if any(abs(sum(a * b for a, b in zip(rows[i], rows[j])) - (i == j)) > 1e-7
               for i in range(3) for j in range(3)):
            raise ValueError("assembly plan: nonrigid placement")
        a, b, c = rows
        if abs(a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])-1) > 1e-7:
            raise ValueError("assembly plan: reflected placement")
    if mesh_hashes is not None and (set(mesh_hashes) != names or any(
            source["instances"][n]["mesh_sha256"] != h for n, h in mesh_hashes.items())):
        raise ValueError("assembly plan: stale or ambiguous mesh/source membership")
    refs(value["fixed"], names, True)
    owned, seen, previous = set(value["fixed"]), set(), None
    operations = value["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 2000:
        raise ValueError("assembly plan: needs serial operations")
    for op in operations:
        fields(op, ("id", "type", "members", "requires", "path_mm", "intent", "tools"))
        if not isinstance(op["id"], str) or not _ID.fullmatch(op["id"]) or op["id"] in seen or op["type"] != "translate":
            raise ValueError("assembly plan: duplicate identity or unsupported operation")
        refs(op["requires"], seen)
        if previous is not None and previous not in op["requires"]:
            raise ValueError("assembly plan: serial predecessor dependency required")
        refs(op["members"], names, True)
        if owned.intersection(op["members"]):
            raise ValueError("assembly plan: overlapping rigid ownership")
        owned.update(op["members"])
        path = op["path_mm"]
        if (not isinstance(path, list) or not 2 <= len(path) <= 256 or not all(vector(v) for v in path)
                or path[-1] != [0, 0, 0] or not any(path[0])
                or any(a == b for a, b in zip(path, path[1:]))):
            raise ValueError("assembly plan: finite nonzero piecewise path to home required")
        if not text(op["intent"]):
            raise ValueError("assembly plan: independent intent reference required")
        if not isinstance(op["tools"], list) or len(op["tools"]) > 32:
            raise ValueError("assembly plan: invalid tool references")
        tool_ids = set()
        for tool in op["tools"]:
            fields(tool, ("fastener", "tool", "approach_mm"))
            if (tool["fastener"] not in op["members"] or not text(tool["tool"])
                    or tool["fastener"] in tool_ids or not finite(tool["approach_mm"]) or tool["approach_mm"] <= 0):
                raise ValueError("assembly plan: tool needs moving fastener and finite axial approach")
            tool_ids.add(tool["fastener"])
        seen.add(op["id"])
        previous = op["id"]
    if owned != names:
        raise ValueError("assembly plan: exact checked/fixed instance closure required")
    return copy.deepcopy(value)


def plan_state(plan, position: float):
    """Absolute offsets at installation time [0, operation count]; removal uses count - time.

    Segment durations are proportional to their lengths, preserving authored corners. No prior pose is read.
    """
    n = len(plan["operations"])
    if type(position) not in (int, float) or not math.isfinite(position) or not 0 <= position <= n:
        raise ValueError("assembly plan: invalid seek")
    offsets = {name: [0, 0, 0] for name in plan["fixed"]}
    for index, op in enumerate(plan["operations"]):
        path = op["path_mm"]
        lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
        distance = min(1, max(0, position - index)) * sum(lengths)
        offset = list(path[-1])
        for a, b, length in zip(path, path[1:], lengths):
            if distance <= length:
                offset = [a[k] + (b[k] - a[k]) * distance / length for k in range(3)]
                break
            distance -= length
        for name in op["members"]:
            offsets[name] = list(offset)
    return offsets
