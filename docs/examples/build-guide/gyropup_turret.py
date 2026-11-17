"""Convert Gyropup's authored turret assembly order into the assembly reader's example guide.

    python docs/examples/build-guide/gyropup_turret.py --gyropup <clean Gyropup checkout>
    python docs/examples/build-guide/gyropup_turret.py --check                      # committed bytes match their receipt
    python docs/examples/build-guide/gyropup_turret.py --check --gyropup <checkout>  # and regenerate byte-for-byte

Reads, and never writes or runs, three things from the checkout's committed HEAD (`git show`, so uncommitted edits
cannot leak in): the turret's authored assembly order (`STEPS` in `hardware/cad/turret/turret_assembly.py`, read as a
Python literal with `ast.literal_eval`; the file is never imported or executed), the turret's browser scene
(`hardware/exports/sim/turret_box/manifest.json`) and that scene's STL meshes. Gyropup's own `docs/turret-assembly.md`
is written from the same `STEPS`.

Each step keeps Gyropup's title, instruction text, the parts it adds, how far each new part is drawn back along the
way it goes in (its insertion offset) and the camera direction of Gyropup's own step picture. Each mesh is only
translated from its moving group's frame into the turret's neutral pose (zero pan and tilt, the turret's mounting face
at z = 0), then all are packed into one `cad-agent-model/1` model with cad-agent's `pack_view` (welded and quantised to
16-bit steps across the turret's box, about 0.004 mm; display geometry, not dimensions). Scene parts that no authored
step adds are left out and listed in the receipt.

The instruction text is Gyropup's, with three explicit rules applied (TEXT_RULES): its design-log codes (D42, D48) and
version tags (v1) are dropped and its repository paths are named as Gyropup's. Every edit is recorded in the receipt
with its position, so the original text can be restored exactly and checked against its recorded SHA-256.

This is presentation of an authored sequence. It does not check that the parts can go together in that order, that
they fit, or that a tool can reach a fastener; Gyropup is a work-in-progress prototype.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATOR = "docs/examples/build-guide/gyropup_turret.py"
DEFAULT_OUT = ROOT / "software/cadagent/webkit/assembly/examples/gyropup-turret"
RECIPE = "hardware/cad/turret/turret_assembly.py"
SCENE_DIR = "hardware/exports/sim/turret_box"
SCENE = SCENE_DIR + "/manifest.json"
LICENSE = "LICENSE"
# The turret's moving groups in the scene (the J501 box and its adapter are a different assembly).
GROUPS = ("base", "pinion", "pan", "tilt", "dial", "wheel_l", "wheel_r", "flap")
# Stages of the build, shown as the guide's subassemblies. The authored recipe has twelve steps; these stages group
# them for reading and do not change their order.
STAGES = (("base", "Base", "the pan base, its servo and pinion, the DT12 socket and the base-board module", 1, 3),
          ("turntable", "Turntable", "the pan bearing and clamp, the turntable and the slip ring", 4, 6),
          ("tilt", "Tilt", "the tilt yoke and board bay, the tilt servo and cradle, and the laser", 7, 9),
          ("cartridge", "Cartridge", "the launcher cartridge, the barrel and hopper, and its thumbscrew", 10, 12))
MODEL = "model"            # pack_view writes model.json and model.bin
# Gyropup's codes mean nothing to a visitor: D<n> numbers a decision in its design log, v<n> a later prototype version.
# Each rule: (name, pattern, replacement, why). Applied in order; every match is recorded so the original is restorable.
CODE = r"(?:D\d+|v\d+)"
TEXT_RULES = (
    ("code-only-parenthesis", r" ?\(" + CODE + r"\)", "",
     "A parenthesis holding only a design-log code or version tag, such as ' (D48)' or ' (v1)', is dropped."),
    ("code-ending-parenthesis", r", ?" + CODE + r"(?=\))", "",
     "A code that ends a parenthesised list, such as ', D42' in '(no bumper on the bench, D42)', is dropped."),
    ("repository-path", r"(?<![\w/'])(?=docs/[\w./-]+\.md)", "Gyropup's ",
     "A path into Gyropup's repository, such as 'docs/turret-wiring.md', is named as Gyropup's."),
)
QUALIFICATION = ("Example sequence from a work-in-progress prototype, not a verified build procedure. A CAD step order "
                 "does not prove the parts can physically be assembled in that order, or that they fit.")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=1) + "\n").encode()


def clean_text(text: str):
    """(text with TEXT_RULES applied, edits) where each edit is {rule, at, old, new} on the text as it then stood."""
    edits = []
    for name, pattern, replacement, _ in TEXT_RULES:
        out, last = [], 0
        for match in re.finditer(pattern, text):
            out.append(text[last:match.start()])
            edits.append({"rule": name, "at": sum(map(len, out)), "old": match.group(0), "new": replacement})
            out.append(replacement)
            last = match.end()
        text = "".join(out) + text[last:]
    left = re.findall(r"\b" + CODE + r"\b", text)
    if left:
        raise ValueError(f"design-log codes no rule covers: {left}; add an explicit rule")
    return text, edits


def restore_text(text: str, edits) -> str:
    """The original text from the cleaned one and its recorded edits (undone last first)."""
    for edit in reversed(edits):
        at = edit["at"]
        if text[at:at + len(edit["new"])] != edit["new"]:
            raise ValueError(f"edit at {at} does not match the text")
        text = text[:at] + edit["old"] + text[at + len(edit["new"]):]
    return text


def git(checkout: Path, *args, text=True):
    out = subprocess.run(["git", "-C", str(checkout), *args], check=True, capture_output=True, text=text).stdout
    return out.strip() if text else out


def authored_steps(recipe: bytes):
    """The recipe's literal STEPS: [(title, added parts, offsets, camera direction, instruction text)]."""
    tree = ast.parse(recipe)
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "STEPS" for t in node.targets)]
    if len(values) != 1:
        raise ValueError(f"{RECIPE}: expected one literal STEPS list")
    rows = ast.literal_eval(values[0])
    if not isinstance(rows, list) or len(rows) != STAGES[-1][4]:
        raise ValueError(f"{RECIPE}: expected {STAGES[-1][4]} steps, found {len(rows) if isinstance(rows, list) else '?'}")
    for k, row in enumerate(rows, 1):
        if not (isinstance(row, tuple) and len(row) == 5 and isinstance(row[0], str) and isinstance(row[4], str)
                and isinstance(row[1], list) and row[1] and isinstance(row[2], dict) and len(row[3]) == 3):
            raise ValueError(f"{RECIPE}: step {k} is not (title, parts, offsets, view, text)")
    return rows


def neutral_translation(group: str, pivots: dict) -> list[float]:
    """Where a group's vertices go at zero pan and tilt, with the turret's mounting face at z = 0.

    The scene stores base and pinion vertices in the box frame, pan vertices relative to the pan pivot, tilt vertices
    relative to the pan and tilt pivots, and the dial, flywheels and flap relative to their own pivot inside the tilt
    group (the manifest's `frame` note; Gyropup's viewer nests them so). At zero angles each nesting is a translation.
    """
    pan, tilt = pivots["pan"], pivots["tilt"]
    if group in ("base", "pinion"):
        return [-v for v in pan]
    if group == "pan":
        return [0.0, 0.0, 0.0]
    if group == "tilt":
        return [float(v) for v in tilt]
    return [a + b for a, b in zip(tilt, pivots[group])]


def translate_stl(data: bytes, offset, name: str):
    """The same binary STL with every vertex moved by `offset`; header, normals and attributes are kept."""
    if len(data) < 84 or len(data) != 84 + 50 * struct.unpack_from("<I", data, 80)[0]:
        raise ValueError(f"{name}: not an exact-length binary STL")
    out, lo, hi = bytearray(data), [math.inf] * 3, [-math.inf] * 3
    for start in range(84, len(data), 50):
        values = struct.unpack_from("<12f", data, start)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"{name}: non-finite value")
        for vertex in range(3):
            at = start + 12 + 12 * vertex
            struct.pack_into("<3f", out, at, *(values[3 + 3 * vertex + axis] + offset[axis] for axis in range(3)))
            for axis, value in enumerate(struct.unpack_from("<3f", out, at)):
                lo[axis], hi[axis] = min(lo[axis], value), max(hi[axis], value)
    if not math.isfinite(lo[0]):
        raise ValueError(f"{name}: no triangles")
    return bytes(out), [round(v, 4) + 0.0 for v in lo + hi]


def convert(checkout: Path, out: Path) -> dict:
    """Write every artifact into `out` from a clean checkout's HEAD; returns the receipt written."""
    checkout = Path(checkout).resolve()
    if git(checkout, "status", "--porcelain", "--", RECIPE, SCENE_DIR, LICENSE):
        raise SystemExit(f"{checkout}: the recipe, scene or licence has uncommitted changes; convert a clean checkout")
    revision, committed = git(checkout, "rev-parse", "HEAD"), git(checkout, "show", "-s", "--format=%cI", "HEAD")
    sources = {}

    def read(rel: str) -> bytes:
        data = git(checkout, "show", f"{revision}:{rel}", text=False)
        sources[rel] = sha(data)
        return data

    license_text = read(LICENSE)
    if not license_text.startswith(b"MIT License"):
        raise SystemExit(f"{LICENSE}: expected Gyropup's MIT licence")
    rows = authored_steps(read(RECIPE))
    scene = json.loads(read(SCENE))
    entries = [p for p in scene["parts"] if p["group"] in GROUPS]
    by_part = {}
    for entry in entries:
        by_part.setdefault(entry["part"], []).append(entry)
    added = [part for row in rows for part in row[1]]
    if len(added) != len(set(added)):
        raise ValueError("a part is added by two steps")
    unknown = [p for p in added if p not in by_part]
    if unknown:
        raise ValueError(f"steps add parts the scene does not have: {unknown}")
    excluded = sorted(e["name"] for e in entries if e["part"] not in set(added))

    meshes, parts, steps, shown, text_edits = {}, [], [], [], {}
    for number, (title, adds, lifts, camera, authored) in enumerate(rows, 1):
        stage = next(s for s in STAGES if s[3] <= number <= s[4])
        if set(lifts) - set(adds):
            raise ValueError(f"step {number}: offsets for parts it does not add")
        highlight, offsets = [], {}
        for logical in adds:
            for entry in by_part[logical]:            # a logical part's instances, in the scene's order
                data = read(f"{SCENE_DIR}/{entry['file']}")
                if sha(data) != entry["sha256"]:
                    raise ValueError(f"{entry['file']}: does not match the scene's recorded SHA-256")
                mesh, bounds = translate_stl(data, neutral_translation(entry["group"], scene["pivots"]), entry["file"])
                meshes[entry["name"]] = mesh
                parts.append({"name": entry["name"], "file": f"{entry['name']}.stl", "sha256": sha(mesh),
                              "bounds_mm": bounds, "color": entry["color"], "step": number})
                highlight.append(entry["name"])
                lift = lifts.get(logical, 0)
                offsets[entry["name"]] = [0.0, 0.0, float(lift)] if isinstance(lift, (int, float)) else [float(v) for v in lift]
        shown += highlight
        step_id = f"step-{number:02d}"
        text, edits = clean_text(authored)
        assert restore_text(text, edits) == authored
        text_edits[step_id] = {"original_sha256": sha(authored.encode()), "edits": edits}
        steps.append({"id": step_id, "title": title, "text": text, "subassembly": stage[0],
                      "parts": list(shown), "highlight": highlight, "offsets_mm": offsets,
                      "camera": {"direction": [float(v) for v in camera]},
                      **({"requires": [f"step-{number - 1:02d}"]} if number > 1 else {})})

    # One packed model: the translated meshes go through cad-agent's own pack_view, in a scratch folder.
    sys.path.insert(0, str(ROOT / "software"))
    from cadagent.publish.view import pack_view
    files = {}
    with tempfile.TemporaryDirectory(prefix="cad-agent-turret-meshes-") as tmp:
        scratch = Path(tmp)
        for part in parts:
            (scratch / part["file"]).write_bytes(meshes[part["name"]])
        (scratch / "view.json").write_bytes(encoded({"title": "Gyropup turret", "units": "mm", "up": "z",
            "parts": [{k: p[k] for k in ("name", "file", "sha256", "bounds_mm", "color")} for p in parts]}))
        pack_view(scratch / "view.json", scratch / MODEL, title="Gyropup turret",
                  source={"project": "Valpatel/gyropup", "revision": revision, "license": "MIT",
                          "converter": GENERATOR})
        for suffix in (".json", ".bin"):
            files[MODEL + suffix] = (scratch / (MODEL + suffix)).read_bytes()
    guide = {"schema": "cad-agent.assembly-guide/1",
             "snapshot": {"id": f"gyropup-turret-{revision[:12]}", "revision": f"Gyropup turret {revision[:7]}",
                          "status": "wip", "source_commit": revision},
             "model": {"file": MODEL + ".json", "sha256": sha(files[MODEL + ".json"])},
             "source": {"project": "Valpatel/gyropup", "repository": "https://github.com/Valpatel/gyropup",
                        "license": "MIT", "recipe": RECIPE, "qualification": QUALIFICATION},
             "subassemblies": [{"id": s[0], "title": f"{s[1]}: {s[2]}",
                                "parts": [p["name"] for p in parts if s[3] <= p["step"] <= s[4]]} for s in STAGES],
             "steps": steps}
    files["guide.json"] = encoded(guide)
    files["LICENSE.txt"] = license_text

    for rel, data in files.items():
        (out / rel).write_bytes(data)
    receipt = {
        "schema": "cad-agent.build-guide-receipt/1",
        "project": "Valpatel/gyropup", "repository": "https://github.com/Valpatel/gyropup", "license": "MIT",
        "revision": revision, "committed": committed,
        "generator": {"path": GENERATOR, "sha256": sha((ROOT / GENERATOR).read_bytes())},
        "method": ("Gyropup's literal STEPS (titles, parts, insertion offsets, camera directions and instruction text) "
                   "copied in order; each scene mesh translated from its group's frame into the neutral pose (zero pan "
                   "and tilt, mounting face at z = 0), triangles unchanged, then packed by cad-agent's pack_view into "
                   "one cad-agent-model/1 model (welded, quantised to 16-bit steps across the turret's box). No CAD is "
                   "imported, rebuilt or simplified, and no vendor source CAD is read or shipped: the scene's bought "
                   "parts are Gyropup's own envelope meshes. Instruction text: the text_rules below, every edit listed "
                   "under text_edits with its position; undoing them restores the original, whose SHA-256 is recorded."),
        "text_rules": [{"rule": n, "pattern": pat, "replacement": rep, "why": why} for n, pat, rep, why in TEXT_RULES],
        "text_edits": text_edits,
        "meshes": {p["name"]: p["sha256"] for p in parts},
        "steps": len(steps), "parts": len(parts),
        "excluded": {"parts": excluded, "reason": "In the turret scene, but no authored step adds it."},
        "limits": QUALIFICATION,
        "sources": dict(sorted(sources.items())),
        "artifacts": {rel: sha(data) for rel, data in sorted(files.items())},
    }
    (out / "receipt.json").write_bytes(encoded(receipt))
    return receipt


def check(out: Path, checkout: Path | None = None) -> list[str]:
    """Problems with the committed example: the receipt's generator and artifact hashes, the guide's own bindings,
    and, given a checkout, any byte that differs from a fresh conversion."""
    problems = []
    receipt = json.loads((out / "receipt.json").read_bytes())
    if receipt["generator"]["sha256"] != sha((ROOT / GENERATOR).read_bytes()):
        problems.append(f"{GENERATOR}: changed since the receipt; regenerate")
    for rel, expected in receipt["artifacts"].items():
        path = out / rel
        if not path.is_file() or sha(path.read_bytes()) != expected:
            problems.append(f"{rel}: does not match its receipt")
    listed = set(receipt["artifacts"]) | {"receipt.json", "README.md"}
    stray = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and str(p.relative_to(out)) not in listed)
    problems += [f"{rel}: not in the receipt" for rel in stray]
    guide = json.loads((out / "guide.json").read_bytes())
    model = json.loads((out / guide["model"]["file"]).read_bytes())
    if guide["model"]["sha256"] != sha((out / guide["model"]["file"]).read_bytes()):
        problems.append("guide.json: its model hash is not the model's")
    if not (out / model["bin"]).is_file() or sha((out / model["bin"]).read_bytes()) != model["sha256"]:
        problems.append(f"{guide['model']['file']}: {model['bin']} does not match its hash")
    for step in guide["steps"]:
        record = receipt["text_edits"].get(step["id"])
        try:
            original = restore_text(step["text"], record["edits"]) if record else None
        except ValueError:
            original = None
        if original is None or sha(original.encode()) != record["original_sha256"]:
            problems.append(f"guide.json: {step['id']} text does not restore to Gyropup's recorded original")
    if checkout is not None:
        with tempfile.TemporaryDirectory(prefix="cad-agent-build-guide-") as tmp:
            fresh = convert(checkout, Path(tmp))
            for rel in (*fresh["artifacts"], "receipt.json"):
                if (Path(tmp) / rel).read_bytes() != (out / rel).read_bytes():
                    problems.append(f"{rel}: differs from a fresh conversion of {fresh['revision'][:7]}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gyropup", type=Path, help="a clean Gyropup checkout (read only)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify the committed example instead of writing it")
    args = parser.parse_args(argv)
    if args.check:
        problems = check(args.out, args.gyropup)
        for problem in problems:
            print(problem, file=sys.stderr)
        if not problems:
            print("Gyropup turret guide matches its receipt" + (" and a fresh conversion." if args.gyropup else "."))
        return 1 if problems else 0
    if not args.gyropup:
        parser.error("--gyropup is required to convert")
    for stage in STAGES:                               # meshes from before the packed model must not survive
        shutil.rmtree(args.out / stage[0], ignore_errors=True)
    args.out.mkdir(parents=True, exist_ok=True)
    receipt = convert(args.gyropup, args.out)
    total = sum((args.out / rel).stat().st_size for rel in receipt["artifacts"])
    print(f"Converted Gyropup {receipt['revision'][:7]}: {receipt['steps']} steps, {receipt['parts']} parts, "
          f"{total:,} bytes; left out {len(receipt['excluded']['parts'])} scene parts no step adds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
