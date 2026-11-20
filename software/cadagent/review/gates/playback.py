"""Finite guide trajectories through the existing assembly insertion engine.

The pure rules use SequenceWorld; source-bound entry points consume captured guide
assets and exact BREP bytes emitted from the same source shapes as the meshes.
This validates declared presentation paths, never physical assembly readiness.
"""
from __future__ import annotations

import hashlib
import json
import math
import posixpath
from dataclasses import asdict
from typing import Any, Callable, Mapping, Sequence

from cadagent.publish.guides import GuideBundle
from cadagent.review.gates.assembly import AccessOptions, AssemblySequenceWorld, SequenceWorld, sweep_pair
from cadagent.review.gates.relations import Tolerances
from cadagent.review.gates.verdict import Check, digest_of, verdict, _jsonable

BINDING_SCHEMA = "cad-agent.playback-geometry/1"
ASSUMPTIONS = [
    "Finite rigid translations from authored CAD-mm offsets to zero; previous instances stay at their final "
    "poses and future instances are absent, following the existing ordered guide player.",
    "Offsets are presentation trajectories unless the producer separately authors manufacturing intent. "
    "A zero-offset operation checks its final pose only; it establishes no insertion path.",
    "Source CAD-to-mesh correspondence is declared by the exporter which emitted both from the same shapes. "
    "Hashes verify the captured inputs, not a mathematical equivalence of BREP and tessellation.",
    "The existing conservative-advancement sweep samples near obstacles; thinner crossings between samples "
    "can be missed. Touching is allowed, without tolerance stack, deformation, shrink, hands or fixtures.",
    "Fastener engagement, tools, retention, internal assembly of compound instances, gravity and support "
    "stability are not checked. Use the separate fastener and qualified-subassembly gates where applicable.",
]


PROGRESS_SCHEMA = "cad-agent.playback-progress/1"


class _ProgressError(RuntimeError):
    pass


def _emit(callback, event):
    if callback is None:
        return
    try:
        # Round-trip both isolates mutable nested data and rejects unsupported/nonfinite JSON.
        snapshot = json.loads(json.dumps(_jsonable({"schema": PROGRESS_SCHEMA, **event}), allow_nan=False))
        result = callback(snapshot)
        from inspect import isasyncgen, isawaitable, iscoroutine, isgenerator
        if isawaitable(result) or isgenerator(result) or isasyncgen(result):
            if iscoroutine(result) or isgenerator(result):
                result.close()
            raise TypeError("on_progress must complete synchronously without yielding")
    except Exception as exc:
        error = _ProgressError(f"progress callback failed: {type(exc).__name__}: {exc}")
        error.context = {key: event[key] for key in ("event", "phase", "state", "instance", "operation_index",
                                                    "pair_index", "obstacle") if key in event}
        raise error from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mesh_bytes(bundle: GuideBundle, guide: Mapping[str, Any], part: Mapping[str, Any]):
    from urllib.parse import unquote
    model_path = posixpath.normpath(posixpath.join(posixpath.dirname(bundle.path), unquote(guide["model"]["file"])))
    mesh_path = posixpath.normpath(posixpath.join(posixpath.dirname(model_path), unquote(part["file"])))
    return bundle.files[mesh_path]


def _captured(bundle: GuideBundle):
    """Read captured bytes, not paths which could have changed since collection."""
    guide_bytes = bundle.files[bundle.path]
    guide = json.loads(guide_bytes)
    model_path = posixpath.normpath(posixpath.join(posixpath.dirname(bundle.path), guide["model"]["file"]))
    # Collector uses decoded relative paths in its capture map.
    from urllib.parse import unquote
    model_path = unquote(model_path)
    model_bytes = bundle.files[model_path]
    if _sha(model_bytes) != guide["model"]["sha256"]:
        raise ValueError("captured guide/model hash mismatch")
    manifest = json.loads(model_bytes)
    if manifest.get("units") != "mm" or manifest.get("up") != "z" or manifest.get("skipped"):
        raise ValueError("playback geometry requires complete mm/z-up model")
    for part in manifest["parts"]:
        if _sha(_mesh_bytes(bundle, guide, part)) != part["sha256"]:
            raise ValueError(f"captured mesh hash mismatch: {part['name']}")
    return guide, manifest, {"guide_sha256": _sha(guide_bytes), "model_sha256": _sha(model_bytes),
                             "source_commit": guide["snapshot"]["source_commit"], "units": "mm", "up": "z"}


def bind_playback_breps(bundle: GuideBundle, breps: Mapping[str, bytes], *,
                        producer_hash_platform: Mapping[str, str],
                        placements: Mapping[str, Sequence[float]] | None = None,
                        source_closure_sha256: str | None = None, producer: str | None = None):
    """Bind ORIGINAL producer BREP bytes without importing or reserializing shapes.

    The producer's receipt must assert these and the guide meshes came from the
    same source shapes. Pass the original producer platform, never the consumer's.
    Placements are exact name -> twelve row-major rigid matrix entries; omitted
    placements mean the BREP shapes are already in the assembly frame.
    """
    from cadagent.review.evidence import brep_content_hash
    _, manifest, inputs = _captured(bundle)
    names = {p["name"] for p in manifest["parts"]}
    if set(breps) != names or (placements is not None and set(placements) != names):
        raise ValueError("BREP bytes and placements must cover the exact guide instance set")
    if (not isinstance(producer_hash_platform, Mapping) or not producer_hash_platform
            or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in producer_hash_platform.items())):
        raise ValueError("original producer hash platform is required")
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
    instances = {}
    for part in manifest["parts"]:
        name = part["name"]
        payload = breps[name]
        if not isinstance(payload, bytes) or not payload:
            raise ValueError(f"original BREP payload must be nonempty bytes: {name}")
        matrix = list(placements[name]) if placements is not None else list(identity)
        if len(matrix) != 12 or any(type(v) not in (int, float) or not math.isfinite(v) for v in matrix):
            raise ValueError(f"invalid CAD placement: {name}")
        instances[name] = {"brep_sha256": _sha(payload), "shape_sha256": brep_content_hash(payload),
                           "mesh_sha256": part["sha256"], "matrix": matrix}
    return {"schema": BINDING_SCHEMA, **inputs, "instances": instances,
            "hash_platform": dict(producer_hash_platform),
            **({"source_closure_sha256": source_closure_sha256, "producer": producer} if source_closure_sha256 is not None else {})}


def bind_playback_geometry(assembly: Any, bundle: GuideBundle):
    """Return (binding, BREP bytes) beside mesh export from the SAME source Assembly.

    Save both with the export's source/runtime receipt. The helper cannot detect
    unrelated same-named shapes; playback_gate additionally rejects frame/bounds
    mismatches against the actual captured STL vertices.
    """
    from cadagent.review.evidence import shape_brep_text, hash_platform
    _, manifest, _ = _captured(bundle)
    if {p["name"] for p in manifest["parts"]} != set(assembly.names):
        raise ValueError("CAD assembly must cover the exact guide instance set")
    breps = {name: shape_brep_text(assembly[name].shape) for name in assembly.names}
    placements = {name: list(assembly[name].matrix) for name in assembly.names}
    return bind_playback_breps(bundle, breps, placements=placements, producer_hash_platform=hash_platform()), breps


def _frame_evidence(world: SequenceWorld, bundle: GuideBundle, guide: Mapping[str, Any],
                    manifest: Mapping[str, Any], tolerance_mm: float, evidence: list, on_progress=None):
    from io import BytesIO
    import numpy as np
    import trimesh
    for part in manifest["parts"]:
        phase = {"event": "phase", "phase": "frame", "instance": part["name"]}
        _emit(on_progress, {**phase, "state": "starting"})
        mesh = trimesh.load(BytesIO(_mesh_bytes(bundle, guide, part)), file_type="stl", force="mesh", process=False)
        if not len(mesh.vertices) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
            raise ValueError(f"captured mesh has no finite triangles: {part['name']}")
        mesh_bounds = np.concatenate((mesh.vertices.min(axis=0), mesh.vertices.max(axis=0))).tolist()
        cad_bounds = list(world.box(part["name"]))
        model_error = max(abs(a - b) for a, b in zip(mesh_bounds, part["bounds_mm"]))
        cad_error = max(abs(a - b) for a, b in zip(mesh_bounds, cad_bounds))
        evidence.append({"instance": part["name"], "cad_bounds_mm": cad_bounds, "mesh_bounds_mm": mesh_bounds,
                         "model_bounds_mm": part["bounds_mm"], "cad_mesh_max_error_mm": cad_error,
                         "mesh_model_max_error_mm": model_error})
        if model_error > tolerance_mm + 0.01:
            raise ValueError(f"captured mesh/model world bounds mismatch: {part['name']} ({model_error:.6g} mm)")
        if cad_error > tolerance_mm:
            raise ValueError(f"CAD/mesh world bounds mismatch: {part['name']} ({cad_error:.6g} mm)")
        _emit(on_progress, {**phase, "state": "complete", "result": evidence[-1]})


def _validate_numeric_settings(options: AccessOptions, tol: Tolerances, bounds_tolerance_mm: float):
    # Revalidate deserialized/forged option objects before any native input is loaded.
    AccessOptions(**asdict(options))
    for name, value in asdict(tol).items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"tolerance {name} must be finite and nonnegative")
    Tolerances(**asdict(tol))
    if (type(bounds_tolerance_mm) not in (int, float) or not math.isfinite(bounds_tolerance_mm)
            or not 0 <= bounds_tolerance_mm <= 1):
        raise ValueError("bounds_tolerance_mm must be finite and in 0..1 mm")


def playback_operations(guide: Mapping[str, Any], install_order_by_step: Mapping[str, Any],
                        reference_step_ids: Sequence[str] = ()):
    """The existing player's monotone installed sets and explicit exact-instance order."""
    steps = guide["steps"]
    ids = [s["id"] for s in steps]
    if len(ids) != len(set(ids)) or not isinstance(install_order_by_step, Mapping):
        raise ValueError("playback needs unique steps and an installation-order mapping")
    if (isinstance(reference_step_ids, (str, bytes)) or len(set(reference_step_ids)) != len(reference_step_ids)
            or any(i not in ids for i in reference_step_ids)):
        raise ValueError("unknown or duplicate playback reference step")
    refs = set(reference_step_ids)
    if any(i not in ids or i in refs for i in install_order_by_step):
        raise ValueError("unknown or reference installation order")
    prior, operations = [], []
    for step in steps:
        if step["id"] in refs:
            continue
        members = step["parts"]
        if (not isinstance(members, list) or len(members) != len(set(members))
                or any(n not in members for n in prior)):
            raise ValueError("playback requires unique monotone installed membership")
        added = [n for n in members if n not in prior]
        order = install_order_by_step.get(step["id"])
        if (not isinstance(order, list) or not added or len(order) != len(added)
                or len(set(order)) != len(order) or set(order) != set(added)):
            raise ValueError("installation order must cover each new instance exactly once")
        installed = list(prior)
        for name in order:
            offset = step["offsets_mm"].get(name, [0, 0, 0])
            if (not isinstance(offset, list) or len(offset) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e9 for v in offset)):
                raise ValueError("playback offsets must be finite CAD-mm vectors")
            operations.append({"step_id": step["id"], "instance": name,
                               "installed": list(installed), "offset_mm": list(offset)})
            installed.append(name)
        prior = list(members)
    if not operations:
        raise ValueError("playback needs an installation step")
    return operations


def run_playback_sequence(world: SequenceWorld, guide: Mapping[str, Any], install_order_by_step: Mapping[str, Any],
                          *, reference_step_ids: Sequence[str] = (), options: AccessOptions = AccessOptions(),
                          tol: Tolerances = Tolerances(), on_progress: Callable | None = None):
    """Kernel-free rules; optional isolated progress. No source identity is established.

    A callback failure stops immediately and returns failing checks plus preserved
    completed and partial operation evidence (``complete: false``).
    """
    _validate_numeric_settings(options, tol, 0)
    if on_progress is not None and not callable(on_progress):
        raise ValueError("on_progress must be callable or None")
    operations = playback_operations(guide, install_order_by_step, reference_step_ids)
    fitted = {o["instance"] for o in operations}
    if fitted != set(world.names):
        raise ValueError("playback must install the exact geometry instance set")
    checks, rows, current = [], [], None
    try:
        for index, operation in enumerate(operations):
            name, offset = operation["instance"], operation["offset_mm"]
            travel = math.sqrt(sum(c * c for c in offset))
            direction = tuple(-c / travel for c in offset) if travel else (0.0, 0.0, 1.0)
            pairs = []
            current = {**operation, "operation_index": index, "travel_mm": travel, "pairs": pairs,
                       "path_checked": bool(travel and operation["installed"]),
                       "final_pose_checked": bool(operation["installed"])}
            context = {"operation_index": index, "step_id": operation["step_id"], "instance": name}
            _emit(on_progress, {"event": "operation", "state": "starting", **context})
            for pair_index, other in enumerate(operation["installed"]):
                pair_context = {"event": "pair", **context, "pair_index": pair_index, "obstacle": other}
                _emit(on_progress, {**pair_context, "state": "starting"})
                try:
                    pair = sweep_pair(world, name, direction, other, options=options, tol=tol, travel_mm=travel)
                except Exception as exc:
                    # One undecidable pair must not erase earlier collisions or later operations.
                    pair = {"part": other, "state": "unknown", "error": f"{type(exc).__name__}: {exc}"}
                pairs.append(pair)
                _emit(on_progress, {**pair_context, "state": "complete", "result": pair})
            failed = [p for p in pairs if p["state"] != "clear"]
            checks.append(Check(f"operation:{index}:insert", "fail" if failed else "pass",
                                f"{name}: {len(failed)} blocked or undecided pair(s)" if failed else
                                f"{name}: no interference found against {len(pairs)} installed instance(s)",
                                [name] + [p["part"] for p in failed], current))
            if not travel:
                checks.append(Check(f"operation:{index}:path", "warn", "zero offset: no insertion path declared", [name]))
            rows.append(current)
            current = None
            _emit(on_progress, {"event": "operation", "state": "complete", **context, "result": rows[-1]})
    except _ProgressError as exc:
        if current is not None:
            current["complete"] = False
            current["unchecked_pairs"] = current["installed"][len(current["pairs"]):]
            rows.append(current)
            failed = [p for p in current["pairs"] if p["state"] != "clear"]
            checks.append(Check(f"operation:{current['operation_index']}:insert", "fail" if failed else "warn",
                                "progress interrupted; recorded pair results are partial, remaining pairs unchecked",
                                [current["instance"]] + [p["part"] for p in failed], current))
        checks.append(Check("progress", "fail", str(exc), evidence=exc.context))
        return {"checks": checks, "operations": rows, "complete": False}
    return {"checks": checks, "operations": rows}


def _load_world(binding: Mapping[str, Any], breps: Mapping[str, bytes], tol: Tolerances, on_progress=None):
    from io import BytesIO
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    from cadagent.review.gates.relations import Assembly
    assembly = Assembly()
    for name, entry in binding["instances"].items():
        phase = {"event": "phase", "phase": "load", "instance": name}
        _emit(on_progress, {**phase, "state": "starting"})
        shape = TopoDS_Shape()
        BRepTools.Read_s(shape, BytesIO(breps[name]), BRep_Builder())
        matrix = entry["matrix"]
        assembly.add(name, shape, location=[matrix[0:4], matrix[4:8], matrix[8:12]],
                     content_hash=entry["shape_sha256"])
        _emit(on_progress, {**phase, "state": "complete"})
    _emit(on_progress, {"event": "phase", "phase": "world-bounds", "state": "starting"})
    world = AssemblySequenceWorld(assembly, tol)
    _emit(on_progress, {"event": "phase", "phase": "world-bounds", "state": "complete"})
    return world


def playback_gate(bundle: GuideBundle, binding: Mapping[str, Any] | None, breps: Mapping[str, bytes], *,
                  install_order_by_step: Mapping[str, Any] | None = None,
                  reference_step_ids: Sequence[str] = (), options: AccessOptions = AccessOptions(),
                  tol: Tolerances = Tolerances(), bounds_tolerance_mm: float = 0.5,
                  preflight_only: bool = False, on_progress: Callable | None = None,
                  tools=None, fastener_specs=(), reverse: bool = False):
    """Source-bound finite playback check over frozen BREP inputs from the guide producer.

    collect_guides(root, [guide_path]) supplies the captured bundle. Missing/stale
    geometry evidence produces a failing report before importing or querying CAD.
    No intended-overlap exemptions are inferred from animation or grouped meshes.
    preflight_only runs the same input/frame checks but returns a DISTINCT gate
    with paths_checked=false. Optional progress callbacks receive isolated JSON
    snapshots; their storage failure stops the run and fails the report.
    """
    checks, rows, inputs, stats, frames = [], [], {}, {}, []
    progress_complete, paths_checked, world = False, False, None
    try:
        from cadagent.review.evidence import brep_content_hash
        if type(reverse) is not bool:
            raise ValueError("reverse must be boolean")
        if type(preflight_only) is not bool or (on_progress is not None and not callable(on_progress)):
            raise ValueError("preflight_only must be boolean and on_progress callable or None")
        _emit(on_progress, {"event": "phase", "phase": "inputs", "state": "starting"})
        _validate_numeric_settings(options, tol, bounds_tolerance_mm)
        fastener_specs = tuple(fastener_specs)
        guide, manifest, inputs = _captured(bundle)
        if (not isinstance(binding, Mapping) or binding.get("schema") != BINDING_SCHEMA
                or any(binding.get(k) != v for k, v in inputs.items())):
            raise ValueError("missing or stale guide/CAD geometry binding")
        instances = binding["instances"]
        parts = {p["name"]: p for p in manifest["parts"]}
        if set(instances) != set(parts) or set(breps) != set(parts):
            raise ValueError("BREP binding must cover the exact guide instance set")
        for name, part in parts.items():
            entry, payload = instances[name], breps[name]
            if (not isinstance(payload, bytes) or entry["brep_sha256"] != _sha(payload)
                    or entry["shape_sha256"] != brep_content_hash(payload)
                    or entry["mesh_sha256"] != part["sha256"]):
                raise ValueError(f"stale BREP/mesh geometry binding: {name}")
            matrix = entry["matrix"]
            if (not isinstance(matrix, list) or len(matrix) != 12
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in matrix)):
                raise ValueError(f"invalid CAD placement: {name}")
        order = install_order_by_step
        if order is None:
            order = guide.get("source", {}).get("install_order_by_step")
            if isinstance(order, Mapping):
                # Product metadata may carry explicit empty reference entries; the player filters those too.
                order = {k: v for k, v in order.items() if not (k in reference_step_ids and v == [])}
        # Validate canonical intent before native loading; no legacy fallback for declared plans.
        plan = None
        if "assembly_plan" in guide:
            from cadagent.review.dossier.plan import normalize_plan
            from urllib.parse import unquote
            ref = guide["assembly_plan"]
            payload = bundle.files[posixpath.normpath(posixpath.join(posixpath.dirname(bundle.path), unquote(ref["file"])))]
            if _sha(payload) != ref["sha256"]:
                raise ValueError("stale assembly plan bytes")
            plan = normalize_plan(json.loads(payload), mesh_hashes={name: p["sha256"] for name, p in parts.items()})
            source = plan["source"]
            if (source["revision"] != inputs["source_commit"] or source["closure_sha256"] != binding.get("source_closure_sha256")
                    or source["producer"] != binding.get("producer")
                    or any(source["instances"][name] != {k: entry[k] for k in ("mesh_sha256", "brep_sha256", "matrix")}
                           for name, entry in instances.items())):
                raise ValueError("stale assembly plan source/BREP/placement/producer binding")
            if source["tooling_sha256"] != digest_of({"tools": tools or {}, "fastener_specs": [asdict(s) for s in fastener_specs]}):
                raise ValueError("stale assembly plan tooling/axis declarations")
            if ([s["id"] for s in guide["steps"]] != [op["id"] for op in plan["operations"]]
                    or any(s["offsets_mm"] for s in guide["steps"])):
                raise ValueError("guide must project exact plan operations without authored offsets")
            inputs["assembly_plan_sha256"] = ref["sha256"]
        else:
            operations = playback_operations(guide, order, reference_step_ids)
            if {o["instance"] for o in operations} != set(parts):
                raise ValueError("playback must install the exact geometry instance set")
        from cadagent.review.evidence import hash_platform
        inputs.update(binding_digest=digest_of(binding), install_order_digest=digest_of(order),
                      options_digest=digest_of({**asdict(options), "bounds_tolerance_mm": bounds_tolerance_mm}),
                      tolerances_digest=digest_of(asdict(tol)),
                      reference_step_ids=list(reference_step_ids),
                      producer_hash_platform=binding.get("hash_platform", {}))
        _emit(on_progress, {"event": "phase", "phase": "inputs", "state": "complete", "inputs": inputs})
        _emit(on_progress, {"event": "phase", "phase": "load", "state": "starting"})
        inputs["runtime_hash_platform"] = hash_platform()
        world = _load_world(binding, breps, tol, on_progress)
        _emit(on_progress, {"event": "phase", "phase": "load", "state": "complete"})
        _emit(on_progress, {"event": "phase", "phase": "frame", "state": "starting"})
        _frame_evidence(world, bundle, guide, manifest, bounds_tolerance_mm, frames, on_progress)
        _emit(on_progress, {"event": "phase", "phase": "frame", "state": "complete"})
        checks = [Check("inputs", "pass", "captured guide, mesh and BREP hashes match the producer binding")]
        _emit(on_progress, {"event": "preflight", "state": "complete", "inputs": inputs, "frames": frames})
        if preflight_only:
            checks.append(Check("paths", "warn", "input/frame preflight only: no insertion paths checked"))
            progress_complete = True
        else:
            result = (run_plan_sequence(world, plan, options=options, tol=tol, tools=tools,
                                       fastener_specs=fastener_specs, reverse=reverse, on_progress=on_progress)
                      if plan else run_playback_sequence(world, guide, order, reference_step_ids=reference_step_ids,
                                                        options=options, tol=tol, on_progress=on_progress))
            checks += result["checks"]
            rows = result["operations"]
            progress_complete = result.get("complete", True)
            paths_checked = progress_complete
        stats = world.stats
    except _ProgressError as exc:
        checks.append(Check("progress", "fail", str(exc), evidence=exc.context))
    except (ValueError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        checks = [Check("inputs", "fail", f"playback validation not completed: {exc}")]
    if world is not None:
        stats = world.stats
    if "assembly_plan_sha256" in inputs:
        inputs["direction"] = "remove" if reverse else "install"
    checks.append(Check("support-stability", "warn", "unknown: gravity, retention and fixture support not simulated"))
    limits = {**asdict(options), "touch_mm": tol.touch_mm, "overlap_mm3": tol.overlap_mm3,
              "bounds_tolerance_mm": bounds_tolerance_mm, "model_bounds_rounding_allowance_mm": 0.01,
              "finite_paths": True, "support_stability_verified": False,
              "physical_assembly_verified": False, "cad_mesh_correspondence": "producer-declared"}
    # Invalid numeric inputs still need a JSON-safe failing report.
    limits = {k: repr(v) if type(v) is float and not math.isfinite(v) else v for k, v in limits.items()}
    if preflight_only or on_progress is not None:
        limits.update(paths_checked=paths_checked, progress_complete=progress_complete)
    gate = "assembly-playback-preflight" if preflight_only is True else "assembly-playback"
    assumptions = (list(ASSUMPTIONS[2:4]) + [
        "Canonical serial piecewise translations with explicit occupied parked instances; reverse order and path.",
        "Ordinary axial tool paths and engaged swing are separately sampled when declared; no hands, support, retention or process qualification.",
        "Rigid-module internal assembly remains separately unverified; no whole-pair contact waivers."]
        if "assembly_plan_sha256" in inputs else list(ASSUMPTIONS))
    if preflight_only is True:
        assumptions.append("Input/frame preflight only: no insertion pair was evaluated; this is not a clearance verdict.")
    return verdict(gate, checks, assumptions=assumptions,
                   limits=limits,
                   extra={"operations": rows, "inputs": inputs, "world_stats": stats, "frames": frames,
                          "support_stability": {"status": "unknown", "reason": "no stage physics inputs"}})


class _PlanSegmentWorld(SequenceWorld):
    """Translate a finite segment's endpoint and each stationary stage obstacle independently."""
    def __init__(self, world, offsets):
        self.world, self.offsets, self.names = world, offsets, world.names

    def box(self, key):
        return tuple(v + self.offsets[key][i % 3] for i, v in enumerate(self.world.box(key)))

    def relate_at(self, key, shift, other):
        # Common obstacle translation removed for the existing one-moving-body query.
        from dataclasses import replace
        delta = tuple(shift[i] + self.offsets[key][i] - self.offsets[other][i] for i in range(3))
        rel = self.world.relate_at(key, delta, other)
        witness = dict(rel.witness)
        for k in ("point_a", "point_b", "overlap_centroid"):
            if witness.get(k) is not None:
                witness[k] = [v + self.offsets[other][i] for i, v in enumerate(witness[k])]
        return replace(rel, witness=witness)


def run_plan_sequence(world: SequenceWorld, plan, *, options: AccessOptions = AccessOptions(),
                      tol: Tolerances = Tolerances(), tools=None, fastener_specs=(), reverse=False,
                      on_progress=None):
    """Finite occupied-stage paths; kernel-independent geometry rules and native existing tool checks.

    This entry point alone establishes no source identity. playback_gate binds the captured resource.
    Internal module qualification, support, retention/process and physical build remain unknown.
    """
    from cadagent.review.dossier.plan import normalize_plan, plan_state
    plan = normalize_plan(plan)
    _validate_numeric_settings(options, tol, 0)
    if not options.tool_access:
        raise ValueError("canonical plan tool checks cannot be disabled")
    if set(world.names) != set(plan["source"]["instances"]):
        raise ValueError("assembly plan must cover exact geometry instances")
    if type(reverse) is not bool:
        raise ValueError("reverse must be boolean")
    specs = {s.instance_key(i): (s, i) for s in fastener_specs for i in range(len(s.axes))}
    checks, rows, n = [], [], len(plan["operations"])
    initial = plan_state(plan, n if reverse else 0)
    initial_world = _PlanSegmentWorld(world, initial)
    ownership = {name: op["id"] for op in plan["operations"] for name in op["members"]}
    # Rigid members are not re-qualified internally here. All other initial occupied pairs are checked.
    for i, name in enumerate(world.names):
        for other in world.names[i + 1:]:
            if ownership.get(name) is not None and ownership.get(name) == ownership.get(other):
                continue
            rel = initial_world.relate_at(name, (0, 0, 0), other)
            if rel.interferes or rel.state in ("unknown", "unchecked"):
                checks.append(Check(f"initial:{name}:{other}", "fail", "initial occupied-stage conflict or unknown",
                                    [name, other], {"state": rel.state, "overlap_mm3": rel.overlap_mm3}))
    for index in (range(n - 1, -1, -1) if reverse else range(n)):
        op = plan["operations"][index]
        try:
            _emit(on_progress, {"event": "operation", "state": "starting", "operation_index": index, "instance": op["id"]})
        except _ProgressError as exc:
            checks.append(Check("progress", "fail", str(exc), evidence={"unchecked_operation": op["id"], **exc.context}))
            return {"checks": checks, "operations": rows, "complete": False}
        occupied = plan_state(plan, index)
        path = list(reversed(op["path_mm"])) if reverse else op["path_mm"]
        pairs, tool_rows = [], []
        for segment, (start, end) in enumerate(zip(path, path[1:])):
            length = math.dist(start, end)
            direction = tuple((b - a) / length for a, b in zip(start, end))
            offsets = dict(occupied)
            offsets.update({name: end for name in op["members"]})
            stage = _PlanSegmentWorld(world, offsets)
            for name in op["members"]:
                for other in world.names:
                    if other in op["members"]:
                        continue
                    try:
                        pair = sweep_pair(stage, name, direction, other, options=options, tol=tol, travel_mm=length)
                    except Exception as exc:
                        pair = {"part": other, "state": "unknown", "error": f"{type(exc).__name__}: {exc}"}
                    if pair["state"] == "clear" and plan["clearance_mm"] > 0:
                        measured, bound = pair.get("min_gap_mm"), pair.get("gap_lower_bound_mm")
                        if measured is not None and measured < plan["clearance_mm"]:
                            pair["state"] = "insufficient-clearance"
                        elif bound is None or bound < plan["clearance_mm"]:
                            pair["state"] = "clearance-unresolved"
                    pairs.append({"moving": name, "segment": segment, "start_mm": start, "end_mm": end, **pair})
        tool_offsets = plan_state(plan, index + 1)  # before removal / after insertion: identical physical stage
        for ref in op["tools"]:
            if ref["fastener"] not in specs or not hasattr(world, "staged"):
                result = {"state": "unknown", "reason": "native fastener/tool declaration unavailable"}
            else:
                from cadagent.review.gates.fasteners import axial_tool_path
                spec, axis = specs[ref["fastener"]]
                try:
                    if hasattr(world, "tool_sweeps"):
                        world.tool_sweeps += 1
                    result = axial_tool_path(world.staged(tool_offsets), spec, axis, ref["tool"],
                        (tools or {}).get(ref["tool"]), world.names, ref["approach_mm"],
                        max_step_mm=options.max_step_mm, max_samples=options.max_samples, tol=tol)
                except Exception as exc:
                    result = {"state": "unknown", "reason": f"{type(exc).__name__}: {exc}"}
            if result["state"] == "sampled-clear" and plan["clearance_mm"] > 0:
                result = {**result, "state": "clearance-unverified", "reason": "tool envelope allowance not measured by existing tool owner"}
            tool_rows.append({**ref, **result})
        missing = [name for name in op["members"] if name in specs and name not in {t["fastener"] for t in op["tools"]}]
        tool_rows.extend({"fastener": name, "state": "unchecked", "reason": "no tool operation declared"} for name in missing)
        failed = [p for p in pairs if p["state"] != "clear"]
        tool_failed = [t for t in tool_rows if t["state"] != "sampled-clear"]
        row = {"id": op["id"], "operation_index": index, "direction": "remove" if reverse else "install",
               "pairs": pairs, "insertion": "blocked-or-undecided" if failed else "sampled-clear",
               "tools": tool_rows, "tool_access": "blocked-or-undecided" if tool_failed else "sampled-clear" if tool_rows else "unchecked",
               "support": "unknown", "retention_process": "unknown", "internal_qualification": "unknown" if len(op["members"]) > 1 else "not-applicable"}
        rows.append(row)
        checks.append(Check(f"operation:{op['id']}:insert", "fail" if failed else "pass",
                            "finite occupied-stage path " + row["insertion"], op["members"], row))
        if tool_rows:
            checks.append(Check(f"operation:{op['id']}:tools", "fail" if tool_failed else "pass",
                                "ordinary axial tool path " + row["tool_access"], op["members"], {"tools": tool_rows}))
        try:
            _emit(on_progress, {"event": "operation", "state": "complete", "operation_index": index, "result": row})
        except _ProgressError as exc:
            checks.append(Check("progress", "fail", str(exc), evidence=exc.context))
            return {"checks": checks, "operations": rows, "complete": False}
    return {"checks": checks, "operations": rows}
