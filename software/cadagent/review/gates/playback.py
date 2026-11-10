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
from typing import Any, Mapping, Sequence

from cadagent.publish.guides import GuideBundle
from cadagent.review.gates.assembly import AccessOptions, AssemblySequenceWorld, SequenceWorld, sweep_pair
from cadagent.review.gates.relations import Tolerances
from cadagent.review.gates.verdict import Check, digest_of, verdict

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
                        placements: Mapping[str, Sequence[float]] | None = None):
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
            "hash_platform": dict(producer_hash_platform)}


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
                    manifest: Mapping[str, Any], tolerance_mm: float, evidence: list):
    from io import BytesIO
    import numpy as np
    import trimesh
    for part in manifest["parts"]:
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
                          tol: Tolerances = Tolerances()):
    """Kernel-free adapter rules. No source/asset identity is established by this lower-level API."""
    _validate_numeric_settings(options, tol, 0)
    operations = playback_operations(guide, install_order_by_step, reference_step_ids)
    fitted = {o["instance"] for o in operations}
    if fitted != set(world.names):
        raise ValueError("playback must install the exact geometry instance set")
    checks, rows = [], []
    for index, operation in enumerate(operations):
        name, offset = operation["instance"], operation["offset_mm"]
        travel = math.sqrt(sum(c * c for c in offset))
        direction = tuple(-c / travel for c in offset) if travel else (0.0, 0.0, 1.0)
        pairs = []
        for other in operation["installed"]:
            try:
                pair = sweep_pair(world, name, direction, other, options=options, tol=tol, travel_mm=travel)
            except Exception as exc:
                # One undecidable pair must not erase earlier collisions or later operations.
                pair = {"part": other, "state": "unknown", "error": f"{type(exc).__name__}: {exc}"}
            pairs.append(pair)
        failed = [p for p in pairs if p["state"] != "clear"]
        evidence = {**operation, "operation_index": index, "travel_mm": travel, "pairs": pairs,
                    "path_checked": bool(travel and operation["installed"]),
                    "final_pose_checked": bool(operation["installed"])}
        checks.append(Check(f"operation:{index}:insert", "fail" if failed else "pass",
                            f"{name}: {len(failed)} blocked or undecided pair(s)" if failed else
                            f"{name}: no interference found against {len(pairs)} installed instance(s)",
                            [name] + [p["part"] for p in failed], evidence))
        if not travel:
            checks.append(Check(f"operation:{index}:path", "warn", "zero offset: no insertion path declared", [name]))
        rows.append(evidence)
    return {"checks": checks, "operations": rows}


def _load_world(binding: Mapping[str, Any], breps: Mapping[str, bytes], tol: Tolerances):
    from io import BytesIO
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    from cadagent.review.gates.relations import Assembly
    assembly = Assembly()
    for name, entry in binding["instances"].items():
        shape = TopoDS_Shape()
        BRepTools.Read_s(shape, BytesIO(breps[name]), BRep_Builder())
        matrix = entry["matrix"]
        assembly.add(name, shape, location=[matrix[0:4], matrix[4:8], matrix[8:12]],
                     content_hash=entry["shape_sha256"])
    return AssemblySequenceWorld(assembly, tol)


def playback_gate(bundle: GuideBundle, binding: Mapping[str, Any] | None, breps: Mapping[str, bytes], *,
                  install_order_by_step: Mapping[str, Any] | None = None,
                  reference_step_ids: Sequence[str] = (), options: AccessOptions = AccessOptions(),
                  tol: Tolerances = Tolerances(), bounds_tolerance_mm: float = 0.5):
    """Source-bound finite playback check over frozen BREP inputs from the guide producer.

    collect_guides(root, [guide_path]) supplies the captured bundle. Missing/stale
    geometry evidence produces a failing report before importing or querying CAD.
    No intended-overlap exemptions are inferred from animation or grouped meshes.
    """
    checks, rows, inputs, stats, frames = [], [], {}, {}, []
    try:
        from cadagent.review.evidence import brep_content_hash
        _validate_numeric_settings(options, tol, bounds_tolerance_mm)
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
        # Validate declarations before loading native inputs.
        playback_operations(guide, order, reference_step_ids)
        world = _load_world(binding, breps, tol)
        _frame_evidence(world, bundle, guide, manifest, bounds_tolerance_mm, frames)
        result = run_playback_sequence(world, guide, order, reference_step_ids=reference_step_ids,
                                       options=options, tol=tol)
        checks = [Check("inputs", "pass", "captured guide, mesh and BREP hashes match the producer binding")]
        checks += result["checks"]
        rows, stats = result["operations"], world.stats
        from cadagent.review.evidence import hash_platform
        inputs.update(binding_digest=digest_of(binding), install_order_digest=digest_of(order),
                      options_digest=digest_of({**asdict(options), "bounds_tolerance_mm": bounds_tolerance_mm}),
                      tolerances_digest=digest_of(asdict(tol)),
                      reference_step_ids=list(reference_step_ids),
                      producer_hash_platform=binding.get("hash_platform", {}), runtime_hash_platform=hash_platform())
    except (ValueError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        checks = [Check("inputs", "fail", f"playback validation not completed: {exc}")]
    checks.append(Check("support-stability", "warn", "unknown: gravity, retention and fixture support not simulated"))
    limits = {**asdict(options), "touch_mm": tol.touch_mm, "overlap_mm3": tol.overlap_mm3,
              "bounds_tolerance_mm": bounds_tolerance_mm, "model_bounds_rounding_allowance_mm": 0.01,
              "finite_paths": True, "support_stability_verified": False,
              "physical_assembly_verified": False, "cad_mesh_correspondence": "producer-declared"}
    # Invalid numeric inputs still need a JSON-safe failing report.
    limits = {k: repr(v) if type(v) is float and not math.isfinite(v) else v for k, v in limits.items()}
    return verdict("assembly-playback", checks, assumptions=ASSUMPTIONS,
                   limits=limits,
                   extra={"operations": rows, "inputs": inputs, "world_stats": stats, "frames": frames,
                          "support_stability": {"status": "unknown", "reason": "no stage physics inputs"}})
