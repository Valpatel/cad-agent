#!/usr/bin/env python3
"""Pictures of the gate bench's review packets, for the docs (#122, #179).

    PYTHONPATH=src python3 tools/site-packet-pictures.py          # needs the cad extra: CadQuery, VTK, Pillow
    PYTHONPATH=src python3 tools/site-packet-pictures.py --only thin_wall     # one scenario again, keep the rest
    PYTHONPATH=src python3 tools/site-packet-pictures.py --list    # what it would make, without a CAD kernel

The gate bench (tests/fixtures/gate_bench/) is the repo's own test assembly: a hopper of loose balls under a screwed
lid, a bracket on a boss and an arm on a pin that swings under a frame. Its build can seed one defect per gate
(``SEEDS`` in its build.py). For the clean bench and for each seed named in ``SCENARIOS`` below, this copies the
bench to a temporary folder, runs ``cad-agent gates --build`` there and ``cad-agent review-packet`` for the sections
it needs, then writes the views named below into docs/img/packets/ as WebP:

    <scenario>-<section>-<view>.webp      e.g. clean-store-exploded.webp, ball_through_wall-store-findings.webp

The renders are the packet's own (its caption bar, section hash and note are part of each image). With them it writes
docs/img/packets/SOURCE.json: the toolkit's version, the kernel and renderer versions, and for each scenario the
cad-agent commit it ran on, the seed's words and every gate's status, counts and failing checks, so a caption on the
site can be held to the run that drew the picture (tests/test_packet_pictures.py). A seeded picture shows a defect put there on purpose;
its caption says so. Renders are for diagnosis, not proof: the gates measure, the pictures show what they measured.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tests" / "fixtures" / "gate_bench"
OUT = ROOT / "docs" / "img" / "packets"
SIZE = (1400, 1000)          # the packet's default: on the docs column (860 CSS px) it is sharp at 1.6x
QUALITY = 82

# scenario: the bench's seed (None: the bench as built), and per section the packet views to keep
SCENARIOS: dict[str, dict] = {
    "clean": {"seed": None, "views": {
        "S-store": ["solid-iso", "xray-iso", "cut-cavity-hopper_cavity", "cut-cavity-hopper_cavity-plan",
                    "cut-fastener-screw_0", "access-from-top", "exploded"],
        "S-arm": ["solid-iso", "pose-I-pin-arm-min", "pose-I-pin-arm-max", "cut-joint-I-pin-arm"],
    }},
    "ball_through_wall": {"seed": "ball_through_wall", "views": {
        "S-store": ["findings", "cut-cavity-hopper_cavity-plan"]}},
    "thin_wall": {"seed": "thin_wall", "views": {"S-store": ["cut-cavity-hopper_cavity-plan"]}},
    "screw_too_long": {"seed": "screw_too_long", "views": {"S-store": ["cut-fastener-screw_0"]}},
    "flap_hits_frame": {"seed": "flap_hits_frame", "views": {"S-arm": ["pose-I-pin-arm-max"]}},
    "lid_before_board": {"seed": "lid_before_board", "views": {"S-store": ["findings", "exploded"]}},
    "bracket_floats": {"seed": "bracket_floats", "views": {"S-bracket": ["findings"]}},
    "gusset_over_screw": {"seed": "gusset_over_screw", "views": {"S-store": ["access-from-top"]}},
}


def picture_name(scenario: str, section: str, view: str) -> str:
    return f"{scenario}-{section.removeprefix('S-')}-{view}.webp"


def planned() -> list[str]:
    return [picture_name(s, sec, v) for s, spec in SCENARIOS.items() for sec, views in spec["views"].items() for v in views]


def _seeds() -> dict:
    sys.path.insert(0, str(BENCH))
    try:
        import build as bench_build                  # tests/fixtures/gate_bench/build.py
    finally:
        sys.path.pop(0)
    return bench_build.SEEDS


def _gates(root: Path) -> dict:
    """Each verdict's status, counts and failing or warning checks (id and message), by gate."""
    out = {}
    for f in sorted((root / "exports" / "gates").glob("*.json")):
        v = json.loads(f.read_text())
        out[v.get("gate", f.stem)] = {"status": v["status"], "counts": v["counts"],
                                     "findings": [{"id": c["id"], "status": c["status"], "message": c["message"]}
                                                  for c in v.get("findings", [])]}
    return out


def _versions() -> dict:
    import cadquery
    import OCP
    import vtk
    from cadagent.review.gates.verdict import _toolkit_version
    ocp = str(getattr(OCP, "__version__", "unknown"))
    return {"toolkit": _toolkit_version(), "cadquery": cadquery.__version__, "ocp": ocp,
            "vtk": vtk.vtkVersion.GetVTKVersion()}


def _commit() -> str:
    """The cad-agent commit the pictures were made from (uncommitted changes are not recorded: commit first)."""
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def make(tmp: Path, only: list[str] | None = None) -> dict:
    from PIL import Image

    from cadagent.cli import main as cli
    from cadagent.publish.render import review_packet

    seeds = _seeds()
    record: dict = {"regenerate": "PYTHONPATH=src python3 tools/site-packet-pictures.py", "size": list(SIZE),
                    **_versions(), "scenarios": {}, "pictures": {}}
    if only:                                           # keep the other scenarios' pictures and records as they are
        old = json.loads((OUT / "SOURCE.json").read_text())
        if any(old.get(k) != record[k] for k in ("size", "toolkit", "cadquery", "ocp", "vtk")):
            raise SystemExit("the toolkit, kernel or renderer changed since SOURCE.json: run every scenario again")
        record["scenarios"] = {k: v for k, v in old["scenarios"].items() if k not in only and k in SCENARIOS}
        record["pictures"] = {k: v for k, v in old["pictures"].items() if v["scenario"] not in only
                              and v["scenario"] in SCENARIOS}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in SCENARIOS.items():
        if only and name not in only:
            continue
        bench = tmp / name
        shutil.copytree(BENCH, bench, ignore=shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site"))
        root = bench / "project"
        (root / "cad" / "parameters.json").write_text(json.dumps({"seed": spec["seed"]}))
        code = cli(["gates", "--project", str(root), "--build"])
        gates = _gates(root)
        if (code == 0) != (spec["seed"] is None):
            raise SystemExit(f"{name}: cad-agent gates exited {code}; the clean bench must pass and a seed must fail")
        seed = seeds.get(spec["seed"], {})
        record["scenarios"][name] = {"commit": _commit(), "seed": spec["seed"], "what": seed.get("what"), "seeded_gate": seed.get("gate"),
                                     "gates": gates}
        for section, views in spec["views"].items():
            manifest = review_packet(section, root=root, size=SIZE)
            by_id = {v["id"]: v for v in manifest["views"]}
            folder = root / "exports" / "review" / section
            for view in views:
                v = by_id.get(view)
                if not v or not v.get("file"):
                    raise SystemExit(f"{name}: the {section} packet has no {view} view (it has {sorted(by_id)})")
                pic = picture_name(name, section, view)
                buf = io.BytesIO()
                Image.open(folder / v["file"]).convert("RGB").save(buf, "WEBP", quality=QUALITY, method=6)
                (OUT / pic).write_bytes(buf.getvalue())
                record["pictures"][pic] = {
                    "scenario": name, "section": section, "view": view, "caption": v["caption"], "note": v["note"],
                    "section_hash": manifest["section_hash"][:12],
                    "findings": [{"id": f["id"], "gate": f["gate"], "check": f["check"], "status": f["status"]}
                                 for f in manifest["findings"] if view == "findings"],
                }
                print(f"docs/img/packets/{pic}: {len(buf.getvalue()) // 1024} KB", flush=True)
    stale = sorted(p.name for p in OUT.glob("*.webp") if p.name not in record["pictures"])
    for p in stale:
        (OUT / p).unlink()
    text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    if str(tmp) in text or "/home/" in text or "/Users/" in text:
        raise SystemExit("SOURCE.json names a local path")
    (OUT / "SOURCE.json").write_text(text)
    return record


def main(argv: list[str]) -> int:
    if "--list" in argv:
        print("\n".join(planned()))
        return 0
    only = argv[argv.index("--only") + 1:] if "--only" in argv else None
    if only is not None and (not only or set(only) - set(SCENARIOS)):
        raise SystemExit(f"--only takes scenario names: {', '.join(SCENARIOS)}")
    with tempfile.TemporaryDirectory(prefix="cad-agent-packets-") as tmp:
        cwd = os.getcwd()
        try:
            os.chdir(tmp)                              # the CLI's caches and logs land in the temporary folder
            make(Path(tmp), only)
        finally:
            os.chdir(cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
