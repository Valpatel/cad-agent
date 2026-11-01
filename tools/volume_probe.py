"""Hold Boolean BREPs fixed while comparing volume integrations.

Prepare once from two STEP files; measure that private bundle using each method.
The bundle contains licensed input-derived geometry: do not commit it. Numerical
receipts contain only basenames/hashes, transforms, versions and measurements.
This diagnostic neither waives interference nor qualifies physical fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity():
    import OCP
    from cadagent.review.gates import relations
    return {"toolkit_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "relations_source_sha256": sha(Path(relations.__file__)), "probe_source_sha256": sha(Path(__file__)),
            "ocp_version": OCP.__version__, "python": sys.version.split()[0],
            "machine": platform.machine()}      # BREP bytes, like content hashes, differ by CPU architecture (#144)


def write_json(path, value):
    path.with_suffix(".tmp").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    path.with_suffix(".tmp").replace(path)


def prepare(args):
    import cadquery as cq
    from OCP.TopLoc import TopLoc_Location
    from cadagent.review.gates.relations import _boolean, _trsf, _matrix, _validate_volume_shape
    args.directory.mkdir(parents=True, exist_ok=False)
    inputs, shapes = {}, {}
    for name in ("a", "b"):
        path = getattr(args, name)
        placement = _trsf(json.loads(getattr(args, f"location_{name}")))
        before = sha(path)
        shape = cq.importers.importStep(str(path)).val().wrapped.Moved(TopLoc_Location(placement))
        _validate_volume_shape(shape, require_solid=True)
        if sha(path) != before:
            raise RuntimeError(f"input {name} changed during import")
        inputs[name] = {"file": path.name, "sha256": before, "transform": _matrix(placement)}
        shapes[name] = shape
    for name, kind, a, b in (("common", "common", "a", "b"), ("cut_a", "cut", "a", "b"),
                              ("cut_b", "cut", "b", "a")):
        print(f"START Boolean {name}", flush=True)
        shapes[name] = _boolean(kind, shapes[a], shapes[b])
        _validate_volume_shape(shapes[name])
    files = {}
    for name, shape in shapes.items():
        path = args.directory / f"{name}.brep"
        cq.Shape.cast(shape).exportBrep(str(path))
        files[name] = {"file": path.name, "sha256": sha(path)}
    receipt = {"schema": "cadagent.volume-probe-inputs/1", "runtime": identity(), "inputs": inputs, "breps": files,
               "physical_fit_verified": False}
    write_json(args.directory / "inputs.json", receipt)
    print(json.dumps(receipt), flush=True)


def measure(args):
    import cadquery as cq
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from cadagent.review.gates.relations import _measure_volume, _validate_volume_shape
    bundle = json.loads((args.directory / "inputs.json").read_text())
    out = {"schema": "cadagent.volume-probe/1", "runtime": identity(), "inputs": bundle["inputs"],
           "breps": bundle["breps"], "preparation_runtime": bundle["runtime"], "method": args.method,
           "volumes": {}, "physical_fit_verified": False}
    started = time.perf_counter()
    for name, entry in bundle["breps"].items():
        path = args.directory / entry["file"]
        if sha(path) != entry["sha256"]:
            raise RuntimeError(f"fixed BREP {name} changed")
        shape = cq.Shape.importBrep(str(path)).wrapped
        _validate_volume_shape(shape)
        print(f"START measure {name} method={args.method}", flush=True)
        t0 = time.perf_counter()
        if args.method == "gk":
            m = _measure_volume(shape)
            row = {"volume_mm3": m.value, "estimated_error_mm3": m.error,
                   "refinement_delta_mm3": m.refinement_delta, "reported_error": m.reported_error}
        else:
            props = GProp_GProps()
            returned = BRepGProp.VolumeProperties_s(shape, props, *(() if args.method == "default" else (1e-8,)))
            row = {"volume_mm3": props.Mass(), "returned_face_relative_error": returned,
                   "estimated_error_mm3": None}  # no justified aggregate error estimate
        row["seconds"] = time.perf_counter() - t0
        out["volumes"][name] = row
        print(json.dumps({name: row}), flush=True)
    v = {name: row["volume_mm3"] for name, row in out["volumes"].items()}
    check = 0.01 + 1e-6 * max(v["a"], v["b"])
    out["unchanged_conservation_budget_mm3"] = check
    for name in ("a", "b"):
        residual = v[name] - v["common"] - v[f"cut_{name}"]
        out[f"residual_{name}_mm3"] = residual
        if args.method == "gk":
            consumed = abs(residual) + sum(out["volumes"][k]["estimated_error_mm3"] for k in (name, "common", f"cut_{name}"))
            out[f"budget_consumed_{name}_mm3"] = consumed
            out[f"conservation_{name}_pass"] = consumed <= check
    out["seconds"] = time.perf_counter() - started
    write_json(args.directory / f"{args.method}.json", out)
    print(json.dumps(out), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("directory", type=Path)
    for name in ("a", "b"):
        prep.add_argument(f"--{name}", type=Path, required=True)
        prep.add_argument(f"--location-{name}", default="[0,0,0]", help="JSON translation or rigid 3x4/4x4 matrix")
    measured = sub.add_parser("measure")
    measured.add_argument("directory", type=Path)
    measured.add_argument("--method", choices=("default", "gauss", "gk"), required=True)
    args = parser.parse_args()
    (prepare if args.command == "prepare" else measure)(args)


if __name__ == "__main__":
    main()
