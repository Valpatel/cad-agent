"""Build a small unsliced numbered fit-coupon plate; never contact or drive a printer."""
from pathlib import Path
import argparse
import csv
import io
import hashlib
from importlib.metadata import version
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.manufacturing import experiments as ex, fit_coupons as fc, plates
from cadagent.geometry import export_print_stl, export_step
from cadagent.project import CadProject, Printer

SOURCE_PATHS = [
    "docs/examples/numbered-coupons/build.py", "software/cadagent/manufacturing/experiments.py",
    "software/cadagent/manufacturing/fit_coupons.py", "software/cadagent/mechanical/markings.py",
    "software/cadagent/manufacturing/process.py", "software/cadagent/manufacturing/plates.py",
    "software/cadagent/manufacturing/slicer.py", "software/cadagent/manufacturing/mesh3mf.py",
    "software/cadagent/geometry/__init__.py", "software/cadagent/geometry/_assembly_step.py",
    "software/cadagent/geometry/cache.py", "software/cadagent/project.py",
    "software/cadagent/__init__.py", "pyproject.toml", "docs/research/process-profiles.yaml",
]


def build(registry, output, native_settings, *, count=2):
    """Allocate NEW physical IDs. Existing output/identity/observation bytes are untouched."""
    registry, output = Path(registry).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("output already exists; use a fresh destination and new IDs for a deliberate reprint")
    if count < 1 or count > 12:
        raise ValueError("this small fixture accepts 1..12 uniquely numbered coupons")
    if registry.is_relative_to(output):
        raise ValueError("keep the persistent version-controlled registry outside generated output")
    source = ex.source_snapshot(ROOT, SOURCE_PATHS[0], SOURCE_PATHS,
                                repository="https://github.com/Valpatel/cad-agent")
    settings = json.loads(native_settings)
    if (not isinstance(settings, dict) or plates.application(settings) == plates.APPLICATION
            or any(not isinstance(settings.get(k), str) or not settings[k].strip()
                   for k in ("printer_settings_id", "print_settings_id"))
            or not isinstance(settings.get("filament_settings_id"), list)
            or len(settings["filament_settings_id"]) != 1 or not settings["filament_settings_id"][0]
            or not settings.get("printable_area")):
        raise ValueError("supply actual native printer/process/one-filament/printable-area settings")
    area, _ = plates.printable_area(settings, (256, 256))
    bed = (area[2]-area[0], area[3]-area[1], 256.0)  # Z is a stated fixture bound, not a device readback.
    settings_hash = hashlib.sha256(native_settings).hexdigest()
    fit = fc.Fit("5 mm sliding pin", 5.0, "slide", count=3)
    parameters = {"fit": fc.plan([fit])[0], "label": fc.label_layout(fit)}
    process = {"project_settings_sha256": settings_hash, "native_printer": settings["printer_settings_id"],
               "native_process": settings["print_settings_id"], "design_assumptions": {"nozzle_mm": 0.4},
               "runtime": {"python": sys.version.split()[0],
                           **{name: version(name) for name in ("cadquery", "cadquery-ocp", "numpy", "trimesh")}}}
    material = {"profile_id": settings["filament_settings_id"][0], "design_assumption": "PLA",
                "remaining_material": "unknown", "device_readiness": "not checked"}
    allocated = [ex.allocate(registry, source=source, parameters=parameters, process=process, material=material)
                 for _ in range(count)]
    stamps = [r["identity"]["short_id"] for r in allocated]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".numbered-coupons-", dir=output.parent) as scratch:
        stage = Path(scratch) / "project"
        exports = stage / "exports"
        exports.mkdir(parents=True)
        geometry = {}
        for stamp in stamps:
            shape, label = fc.labelled_coupon(fit, stamp)
            export_step(shape, exports / (stamp + ".step"), name=stamp)
            geometry[stamp] = export_print_stl(shape, exports / (stamp + ".stl"))
            (exports / (stamp + ".label.svg")).write_text(label.pop("svg"))
            (exports / (stamp + ".label.json")).write_text(json.dumps(label, indent=2) + "\n")
        (exports / "geometry-checks.json").write_text(json.dumps(geometry, indent=2) + "\n")
        with (stage / "fit-measurements.csv").open("w", newline="") as stream:
            rows = list(csv.DictReader(io.StringIO(fc.sheet([fit]))))
            writer = csv.DictWriter(stream, fieldnames=["specimen_uuid", "short_id", *rows[0]])
            writer.writeheader()
            for allocated_row in allocated:
                for row in rows:
                    writer.writerow({"specimen_uuid": allocated_row["identity"]["uuid"],
                                     "short_id": allocated_row["identity"]["short_id"], **row})
        project = CadProject(root=stage, name="numbered-coupons", exports_dir=exports,
                             parts_file=exports / "geometry-checks.json",
                             printer=Printer(settings["printer_settings_id"], bed),
                             slicer={"printer": settings["printer_settings_id"],
                                     "process": settings["print_settings_id"],
                                     "filament": settings["filament_settings_id"][0]},
                             plates={"parts": {s: {"quantity": 1, "filament": material["profile_id"]}
                                               for s in stamps}}, release={"parts": stamps})
        plates.export_plates(project, known_parts=stamps, settings_bytes=native_settings,
                                       use_slicer=False, require_project_settings=True)
        # Final paths are relative; no temporary directory is recorded as source identity.
        os.rename(stage, output)
    for stamp in stamps:
        ex.bind_artifacts(registry, stamp, output,
                           ["exports/" + stamp + suffix for suffix in (".step", ".stl", ".label.svg", ".label.json")])
    plate = ex.bind_plate(registry, stamps, output, "exports/numbered-coupons-plates.3mf")
    (output / "batch.json").write_text(json.dumps(plate, indent=2) + "\n")
    return plate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True, help="persistent version-controlled specimen records")
    parser.add_argument("--out", type=Path, required=True, help="new output directory; previous output is never replaced")
    parser.add_argument("--settings", type=Path, required=True, help="native Bambu project settings; not a guessed preset")
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args()
    result = build(args.registry, args.out, args.settings.read_bytes(), count=args.count)
    print(json.dumps({"batch_uuid": result["batch_uuid"], "specimens": len(result["specimens"]),
                      "project": result["project"], "sliced": False, "ready_to_submit": False}, indent=2))
