"""Regenerate the tiny native assembly bench; no product source or dependencies are installed.

Run with PYTHONPATH=software <existing CAD python> tests/fixtures/assembly-plan/build.py.
Native BREP inputs are returned to tests in memory; browser assets are deterministic derivatives.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).parent

def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(out):
    import cadquery as cq
    from cadagent.publish.view import pack_view
    from cadagent.publish.guides import collect_guides
    from cadagent.review.gates.relations import Assembly
    from cadagent.review.evidence import shape_brep_text, hash_platform
    from cadagent.review.gates.playback import bind_playback_breps
    from cadagent.review.gates.fasteners import FastenerSpec
    from cadagent.review.gates.verdict import digest_of
    from dataclasses import asdict
    data = json.loads((ROOT / "fixture.json").read_bytes())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    assembly, parts, breps = Assembly(), [], {}
    for name, boxes in data["boxes"].items():
        solids = [cq.Solid.makeBox(*box[3:], cq.Vector(*box[:3])) for box in boxes]
        shape = solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)
        assembly.add(name, shape)
        breps[name] = shape_brep_text(shape.wrapped)
        cq.exporters.export(shape, str(out / f"{name}.stl"), exportType="STL")
        b = shape.BoundingBox()
        parts.append({"name": name, "file": f"{name}.stl", "sha256": sha((out / f"{name}.stl").read_bytes()),
                      "bounds_mm": [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax], "color": "#487ca8"})
    write = lambda path, value: (out / path).write_text(json.dumps(value, indent=1) + "\n")
    write("view.json", {"title": "Serial native rail bench", "units": "mm", "up": "z", "parts": parts})
    closure = sha((ROOT / "fixture.json").read_bytes() + Path(__file__).read_bytes())
    identity = [1,0,0,0,0,1,0,0,0,0,1,0]
    spec = FastenerSpec("fastener", "plate", "base", axes=[((0,0,3),(0,0,-1))],
                        instances=["fastener"], diameter_mm=1.2, head_h_mm=2, drive="hex-test")
    plan = {"schema":"cad-agent.assembly-plan/1", "units":"mm", "frame":"assembly-home/z-up", "clearance_mm":0,
            "source":{"revision":"1"*40,"closure_sha256":closure,"producer":"native assembly-plan bench/1",
                "tooling_sha256":digest_of({"tools":{"ordinary-driver":data["tool"]},"fastener_specs":[asdict(spec)]}),
                "instances":{p["name"]:{"mesh_sha256":p["sha256"],"brep_sha256":sha(breps[p["name"]]),"matrix":identity}
                             for p in parts}}, "fixed":data["fixed"],"operations":data["operations"]}
    write("plan.json", plan)
    guide = {"schema":"cad-agent.assembly-guide/1", "snapshot":{"id":"serial-bench","revision":"native-bench/1","status":"wip","source_commit":"1"*40},
             "model":{"file":"view.json","sha256":sha((out / "view.json").read_bytes())},
             "assembly_plan":{"file":"plan.json","sha256":sha((out / "plan.json").read_bytes())},
             "subassemblies":[{"id":"bench","title":"Native rail bench","parts":list(data["boxes"])}],
             "steps":[{"id":op["id"],"title":f"Install {op['id']}","text":op["intent"],"subassembly":"bench",
                       "parts":list(data["boxes"]),"highlight":op["members"],"offsets_mm":{}} for op in data["operations"]]}
    write("guide.json", guide)
    pack_view(out / "view.json", out / "mini", assembly_plan=out / "plan.json")
    bundle = collect_guides(out, ["guide.json"])[0]
    binding = bind_playback_breps(bundle, breps, producer_hash_platform=hash_platform(),
                                 source_closure_sha256=closure, producer=plan["source"]["producer"])
    return assembly, bundle, binding, breps, spec, data["tool"]


if __name__ == "__main__":
    import sys
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)
