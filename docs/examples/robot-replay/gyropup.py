"""Convert Gyropup's recorded simulation snapshot into the replay viewer's portable example.

    python docs/examples/robot-replay/gyropup.py --gyropup <clean Gyropup checkout>
    python docs/examples/robot-replay/gyropup.py --check                      # committed bytes match their receipt
    python docs/examples/robot-replay/gyropup.py --check --gyropup <checkout>  # and regenerate byte-for-byte

Reads, and never writes, the checkout's `hardware/exports/sim/v2/`: the recorded MuJoCo joint frames of each chosen
scenario (`<scenario>.json`), the run summary (`summary.json`) and the browser rig (`rig/manifest.json` and its STL
meshes), the same files gyropup.com's own simulator replays. Each frame's joint positions become world poses of the
robot's rigid bodies through the rig's own forward kinematics (the five-bar legs and the turret's pan and tilt, as
Gyropup's `software/site/designer/robot_v2.js` poses them). The meshes are packed with cad-agent's `pack_view`.

This converts recorded solver output; it does not simulate. MuJoCo is not needed and not run. The poses are those the
snapshot recorded every 33 solver steps of 1 ms (Gyropup's scenarios.py samples round(1 / (30 fps x 0.001 s))
steps; its nominal "30 fps" is 30.3 per second), stamped here at that true 33 ms interval so durations and event times
read in solver time; the browser interpolates between them. Pass verdicts and motor torques are
the snapshot's own numbers, copied from its summary, not a cad-agent verification. Gyropup's README calls the snapshot
a historical demo of a work-in-progress prototype, not a validation of the latest CAD or of physical hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.publish.view import pack_view  # noqa: E402

GENERATOR = "docs/examples/robot-replay/gyropup.py"
DEFAULT_OUT = ROOT / "software/cadagent/webkit/simulation/examples/gyropup-v2"
SNAPSHOT = "hardware/exports/sim/v2"
# Chosen for what a visitor can see happen (#798): the body drops off a kerb and the legs take the landing; one wheel
# climbs a plank while the body stays level; the robot is shoved and rolls back to balance; it is dropped and catches
# itself. Order is the viewer's.
SCENARIOS = ("kerb_drop", "side_kerb", "push", "landing")
LEG_JOINTS = ("motor_f", "knee_f", "motor_r", "knee_r", "wheel")
ARTIFACTS = ("robot.json", "robot.bin", "index.json", "LICENSE.txt", *(f"{name}.json" for name in SCENARIOS))
# Gyropup's actuator keys (software/simulation/robot_v2.py at 41c5c26: the frame is x forward, y left; leg motor
# "motor_<f|r>_<l|r>" sits at x = +D/2 (front) or -D/2 (rear) on the left or the mirrored right; "wheel_<l|r>" is a
# wheel's hub motor). An unknown key stops the conversion rather than show a guessed name.
MOTOR_NAMES = {"motor_f_l": "front-left leg motor", "motor_r_l": "rear-left leg motor", "motor_f_r": "front-right leg motor",
               "motor_r_r": "rear-right leg motor", "wheel_l": "left wheel motor", "wheel_r": "right wheel motor"}
# Where the frame interval comes from: the solver timestep in the generated MJCF and the sampling rule of the run loop.
TIMESTEP_SOURCE, SAMPLING_SOURCE = "software/simulation/robot_v2.py", "software/simulation/scenarios.py"
SAMPLING_RULE = "frame_every = max(1, int(round(1 / (FPS * dt))))"
LIMITS = ("Replay of recorded solver output from a dated snapshot of a work-in-progress prototype. The browser "
          "interpolates the recorded poses; nothing is recomputed. Pass verdicts and torques are the snapshot's own "
          "numbers, not a cad-agent verification. The snapshot predates Gyropup's current CAD; CAD and simulation do "
          "not prove physical fit, strength or control safety.")


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=1) + "\n").encode()


def compact(value) -> bytes:
    """A recording: one frame per line, no indentation (the frames are most of the bytes)."""
    head = {k: v for k, v in value.items() if k != "frames"}
    lines = [json.dumps(f, ensure_ascii=False, allow_nan=False, separators=(",", ":")) for f in value["frames"]]
    text = json.dumps(head, ensure_ascii=False, allow_nan=False, separators=(",", ":"))[:-1]
    return (text + ',"frames":[\n' + ",\n".join(lines) + "\n]}\n").encode()


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------------------------------- rotations

def quat_mul(a, b):
    """Hamilton product of xyzw quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def quat_axis(axis, angle):
    s = math.sin(angle / 2)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(angle / 2))


def rotate(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + y * tz - z * ty, v[1] + w * ty + z * tx - x * tz, v[2] + w * tz + x * ty - y * tx)


def compose(parent, offset, rotation):
    """World pose of a child at `offset` (in the parent's frame), turned by `rotation` about its own origin."""
    p, q = parent
    o = rotate(q, offset)
    return (p[0] + o[0], p[1] + o[1], p[2] + o[2]), quat_mul(q, rotation)


Y, Z, IDENTITY = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0)


def pose_json(pose):
    p, q = pose
    n = math.sqrt(sum(c * c for c in q))
    q = [c / n for c in q]
    if q[3] < 0:                                   # one canonical sign; the viewer takes the shortest path either way
        q = [-c for c in q]
    return {"position": [round(c, 5) + 0.0 for c in p], "quaternion": [round(c, 6) + 0.0 for c in q]}


# ---------------------------------------------------------------------------------------------------- the rig

def body_layout(manifest):
    """[(body id, label, [(part name, source files, mirrored, colour, opacity)])]: the rig's moving groups, each with
    its meshes in its own frame, merged per colour so a body draws as few meshes as possible."""
    def groups(entries, mirror, prefix):
        merged = {}
        for p in entries:
            key = (p["color"].lower(), float(p.get("opacity", 1.0)))
            merged.setdefault(key, []).append(p["file"])
        out = []
        for k, ((colour, opacity), files) in enumerate(sorted(merged.items())):
            out.append((f"{prefix}{'_m' if mirror else ''}_{k}", files, mirror, colour, opacity))
        return out
    links = manifest["links"]
    bodies = [("base", "Body, hip modules and turret base", groups(manifest["body"], False, "base")),
              ("turret_pan", "Turret pan", groups(manifest["turret"]["pan"], False, "turret_pan")),
              ("turret_tilt", "Turret tilt", groups(manifest["turret"]["tilt"], False, "turret_tilt"))]
    names = {"upper": "upper link", "front": "front lower link", "wheel_link": "wheel link", "wheel": "wheel"}
    for side, word in (("l", "left"), ("r", "right")):
        mirror = side == "r"
        for body, key, end in (("upper_f", "upper", "front "), ("lower_f", "front", ""), ("upper_r", "upper", "rear "),
                               ("lower_r", "wheel_link", ""), ("wheel", "wheel", "")):
            bodies.append((f"{body}_{side}", f"{word.capitalize()} {end}{names[key]}", groups(links[key], mirror, key)))
    return bodies


def poses(manifest, qpos, layout):
    """World poses (metres, xyzw) of every body for one recorded frame, in body_layout's order."""
    fv, M = manifest["fivebar"], 0.001
    ref = fv["ref"]
    base = ((qpos[0], qpos[1], qpos[2]), (qpos[4], qpos[5], qpos[6], qpos[3]))     # MuJoCo free joint: xyz, wxyz
    pan_mm, tilt_mm = manifest["turret"]["pan_mm"], manifest["turret"]["tilt_mm"]
    angle = lambda name: qpos[layout[name]] if name in layout else 0.0
    pan = compose(base, tuple(c * M for c in pan_mm), quat_axis(Z, angle("turret_pan")))
    tilt = compose(pan, tuple((t - p) * M for t, p in zip(tilt_mm, pan_mm)), quat_axis(Y, angle("turret_tilt")))
    out = [base, pan, tilt]
    l1, l2, half, y_off = fv["l1_mm"] * M, fv["l2_mm"] * M, fv["D_mm"] / 2 * M, fv["y_off_mm"] * M
    for side, sign in (("l", 1), ("r", -1)):
        j = {name: angle(f"{name}_{side}") for name in LEG_JOINTS}
        # The rig's link frames: x along the link; each joint turns about the robot's y, as robot_v2.js setLeg does.
        upper_f = compose(base, (half, sign * y_off, 0.0), quat_axis(Y, -(ref["phi1"] + j["motor_f"])))
        lower_f = compose(upper_f, (l1, 0.0, 0.0), quat_axis(Y, -((ref["af"] - ref["phi1"]) + j["knee_f"])))
        upper_r = compose(base, (-half, sign * y_off, 0.0), quat_axis(Y, -(ref["phi2"] + j["motor_r"])))
        lower_r = compose(upper_r, (l1, 0.0, 0.0), quat_axis(Y, -((ref["aw"] - ref["phi2"]) + j["knee_r"])))
        wheel = compose(lower_r, (l2, 0.0, 0.0), quat_axis(Y, j["wheel"]))
        out += [upper_f, lower_f, upper_r, lower_r, wheel]
    return out


def read_stl(data: bytes, name: str):
    """(n, 3, 3) float64 triangles (mm) from binary STL bytes, checked against their own triangle count."""
    if len(data) < 84:
        raise ValueError(f"{name}: not a binary STL")
    n = int.from_bytes(data[80:84], "little")
    if len(data) != 84 + 50 * n:
        raise ValueError(f"{name}: {len(data)} bytes for {n} triangles")
    rows = np.frombuffer(data, dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
    tri = rows["v"].astype(np.float64)
    if not np.isfinite(tri).all():
        raise ValueError(f"{name}: nonfinite vertex")
    return tri


def write_stl(path: Path, tri) -> None:
    tri = np.asarray(tri, dtype="<f4")
    rows = np.zeros(len(tri), dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]))
    rows["v"] = tri
    path.write_bytes(b"\0" * 80 + len(tri).to_bytes(4, "little") + rows.tobytes())


def scenery(props):
    """MuJoCo geoms the scenario added (kerbs, planks) as fixed world primitives; boxes only (what the chosen runs use)."""
    out = []
    for p in props:
        if p.get("type") != 6:
            raise ValueError(f"prop {p.get('name')}: only MuJoCo boxes (type 6) are converted")
        w, x, y, z = p["quat"]
        r, g, b, a = p["rgba"]
        item = {"shape": "box", "size": [round(2 * s, 6) for s in p["size"]], "position": [round(c, 6) + 0.0 for c in p["pos"]],
                "quaternion": [x, y, z, w], "color": "#" + "".join(f"{round(255 * c):02x}" for c in (r, g, b))}
        if a < 1:
            item["opacity"] = round(a, 3)
        out.append(item)
    return out


def summary_block(entry, events):
    """The snapshot's own verdict and numbers, as plain labelled text for the viewer."""
    motors = entry["motors"]
    name, worst = max(motors.items(), key=lambda kv: kv[1]["of_peak"])
    if name not in MOTOR_NAMES:
        raise ValueError(f"motor {name}: not a known Gyropup actuator key")
    # Against the motor's peak-torque limit (its control range) only: the snapshot's pass criteria include no torque
    # test, so a figure against the continuous rating beside its PASS would read as a verdict the snapshot never made.
    metrics = [{"label": "Peak motor torque",
                "value": f"{worst['peak_torque_nm']:.1f} N·m, {MOTOR_NAMES[name]}: {round(100 * worst['of_peak'])}% of its "
                         f"peak-torque limit"},
               {"label": "Largest lean", "value": f"{entry['max_theta_deg']:.1f}°"}]
    if events:
        metrics.append({"label": "Events", "value": ", ".join(f"{e['type']} at {e['t']:.1f} s" for e in events)})
    verdict = {"pass": bool(entry["pass"]), "label": "pass" if entry["pass"] else "fail"}
    if entry.get("reasons"):
        verdict["reasons"] = [str(r) for r in entry["reasons"]][:8]
    return {"title": "From the snapshot's own summary", "verdict": verdict, "metrics": metrics,
            "note": "Gyropup's recorded numbers, not a cad-agent verification."}


# ---------------------------------------------------------------------------------------------------- the conversion

def git(checkout: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True).stdout.strip()


def convert(checkout: Path, out: Path) -> dict:
    """Write every artifact into `out` (which must exist) from a clean checkout; returns the receipt written."""
    checkout = Path(checkout).resolve()
    if git(checkout, "status", "--porcelain", "--", SNAPSHOT, "hardware/exports/sim/README.md", "LICENSE",
           TIMESTEP_SOURCE, SAMPLING_SOURCE):
        raise ValueError(f"{SNAPSHOT} has uncommitted changes in the Gyropup checkout")
    revision, committed = git(checkout, "rev-parse", "HEAD"), git(checkout, "show", "-s", "--format=%cI", "HEAD")
    snap = checkout / SNAPSHOT
    sources = {}

    def read(rel: str) -> bytes:
        path = (checkout / rel).resolve()
        if not path.is_relative_to(checkout) or path.is_symlink():
            raise ValueError(f"{rel}: outside the checkout")
        data = path.read_bytes()
        sources[rel] = sha(data)
        return data

    manifest = json.loads(read(f"{SNAPSHOT}/rig/manifest.json"))
    if manifest.get("units") != "mm":
        raise ValueError("rig manifest must be in millimetres")
    summary = json.loads(read(f"{SNAPSHOT}/summary.json"))
    notice = read("hardware/exports/sim/README.md").decode()
    licence = read("LICENSE")
    if b"MIT License" not in licence:
        raise ValueError("expected Gyropup's MIT licence")

    # The true frame interval: the run loop keeps one frame every round(1 / (fps x timestep)) solver steps.
    timestep = re.search(r'<option timestep="([0-9.]+)"', read(TIMESTEP_SOURCE).decode())
    if not timestep or SAMPLING_RULE not in read(SAMPLING_SOURCE).decode():
        raise ValueError(f"cannot confirm the frame interval from {TIMESTEP_SOURCE} and {SAMPLING_SOURCE}")
    dt = float(timestep.group(1))

    bodies = body_layout(manifest)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts, cache = [], {}
        for _, _, groups in bodies:
            for name, files, mirror, colour, opacity in groups:
                if any(p["name"] == name for p in parts):      # the front and rear upper links share one mesh
                    continue
                tri = []
                for file in files:
                    if "/" in file or "\\" in file or not file.endswith(".stl"):
                        raise ValueError(f"rig mesh {file}: not a plain STL name")
                    if file not in cache:
                        cache[file] = read_stl(read(f"{SNAPSHOT}/rig/{file}"), file)
                    tri.append(cache[file])
                tri = np.concatenate(tri)
                if mirror:                         # the right side: y -> -y, two corners swapped to keep faces outward
                    tri = tri[:, [0, 2, 1], :] * np.array([1.0, -1.0, 1.0])
                write_stl(tmp / f"{name}.stl", tri)
                parts.append({"name": name, "file": f"{name}.stl", "color": colour})
        (tmp / "view.json").write_text(json.dumps({"title": "Gyropup v2 rig", "units": "mm", "up": "z", "parts": parts}))
        pack_view(tmp / "view.json", tmp / "robot", title="Gyropup v2 rig (recorded snapshot)",
                  source={"project": "Valpatel/gyropup", "revision": revision, "license": "MIT",
                          "files": f"{SNAPSHOT}/rig/manifest.json and the STL meshes it names",
                          "frames": "each part in its own body's frame (mm)"})
        shutil.copyfile(tmp / "robot.json", out / "robot.json")
        shutil.copyfile(tmp / "robot.bin", out / "robot.bin")

    geometry = {body: [{"shape": "mesh", "part": name, "position": [0, 0, 0], "quaternion": [0, 0, 0, 1], "color": colour,
                        **({"opacity": opacity} if opacity < 1 else {})}
                       for name, _, _, colour, opacity in groups] for body, _, groups in bodies}
    index = {"schema": "cad-agent.replay-index/1", "title": "Gyropup v2: recorded scenarios",
             "meshes": {"file": "robot.json", "sha256": sha((out / "robot.json").read_bytes())}, "scenarios": []}
    for scenario in SCENARIOS:
        run = json.loads(read(f"{SNAPSHOT}/{scenario}.json"))
        entry = summary["scenarios"][scenario]
        frames, layout = run["frames"], run["qpos_layout"]
        if run["scenario"] != scenario or entry["title"] != run["title"] or entry["pass"] != run["pass"]:
            raise ValueError(f"{scenario}: the run and the summary disagree")
        every = max(1, round(1 / (frames["fps"] * dt)))
        interval = every * dt
        if "seconds" in run and len(frames["qpos"]) != math.ceil(round(run["seconds"] / dt) / every):
            raise ValueError(f"{scenario}: {len(frames['qpos'])} frames do not fit {run['seconds']} s at one per {every} steps")
        recording = {
            "schema": "cad-agent.pose-recording/1", "title": f"Gyropup v2: {run['title']}",
            "convention": {"length": "m", "up": "z", "handedness": "right", "quaternion": "xyzw"},
            "bodies": [{"id": body, "label": label, "geometry": geometry[body]} for body, label, _ in bodies],
            "scenery": scenery(run.get("props", [])),
            # A run that drives metres is followed; one that stays near its start is framed whole, so a push shows.
            "view": {**({"follow": "base"} if max(abs(q[0]) for q in frames["qpos"]) > 1.0 else {}), "direction": [0.55, -1.0, 0.42]},
            "frames": [{"time_s": round(i * interval, 6), "poses": [pose_json(p) for p in poses(manifest, q, layout)]}
                       for i, q in enumerate(frames["qpos"])],
        }
        data = compact(recording)
        (out / f"{scenario}.json").write_bytes(data)
        index["scenarios"].append({"id": scenario, "label": run["title"], "file": f"{scenario}.json", "sha256": sha(data),
                                   "summary": summary_block(entry, run.get("events", []))})
    (out / "index.json").write_bytes(encoded(index))
    (out / "LICENSE.txt").write_bytes(licence)
    # The notice's own dated sentence (when the snapshot was generated and captured), whole.
    prose = " ".join(" ".join(line for line in notice.splitlines() if not line.startswith("#")).split())
    dated = next((m.group(0).strip() for m in re.finditer(r"[^.]*\d{4}-\d{2}-\d{2}[^.]*\.", prose)), "")
    receipt = {
        "schema": "cad-agent.replay-receipt/1",
        "project": "Valpatel/gyropup", "repository": "https://github.com/Valpatel/gyropup", "license": "MIT",
        "revision": revision, "committed": committed,
        "snapshot": {"path": SNAPSHOT, "design": summary.get("name"), "passed": summary.get("passed"), "total": summary.get("total"),
                     "physical_test": summary.get("physical_test"), "estimates": summary.get("estimates", []),
                     "statement": " ".join(notice.split()),
                     "dated": dated},
        "method": ("Recorded MuJoCo joint frames (qpos, one every 33 solver steps of 1 ms: the snapshot's nominal 30 fps "
                   "under scenarios.py's sampling rule), stamped at that 33 ms interval so times are solver time (each frame "
                   "is taken after its step, 1 ms later than its stamp), through the rig's own forward kinematics: the free "
                   "joint poses the base; the five-bar links and the turret turn about their recorded joint angles as "
                   "Gyropup's software/site/designer/robot_v2.js poses them. No physics is run."),
        "generator": {"path": GENERATOR, "sha256": sha((ROOT / GENERATOR).read_bytes())},
        "sources": dict(sorted(sources.items())),
        "artifacts": {name: sha((out / name).read_bytes()) for name in ARTIFACTS},
        "limits": LIMITS,
    }
    (out / "receipt.json").write_bytes(encoded(receipt))
    return receipt


def check(out: Path, checkout: Path | None = None) -> list[str]:
    """Problems with the committed example: its receipt's generator and artifact hashes, the index's own hashes, and,
    with a checkout, a byte-for-byte regeneration. An empty list means it matches."""
    problems = []
    receipt = json.loads((out / "receipt.json").read_bytes())
    if receipt["generator"]["sha256"] != sha((ROOT / GENERATOR).read_bytes()):
        problems.append(f"{GENERATOR} changed since the example was generated: regenerate it")
    for name, expected in receipt["artifacts"].items():
        path = out / name
        if not path.is_file() or sha(path.read_bytes()) != expected:
            problems.append(f"{name}: does not match its receipt")
    index = json.loads((out / "index.json").read_bytes())
    if sha((out / index["meshes"]["file"]).read_bytes()) != index["meshes"]["sha256"]:
        problems.append("index.json: mesh library hash differs")
    model = json.loads((out / "robot.json").read_bytes())
    if sha((out / model["bin"]).read_bytes()) != model["sha256"]:
        problems.append("robot.json: packed mesh hash differs")
    for scenario in index["scenarios"]:
        if sha((out / scenario["file"]).read_bytes()) != scenario["sha256"]:
            problems.append(f"index.json: {scenario['file']} hash differs")
    if checkout is not None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = convert(checkout, Path(tmp))
            for name in (*fresh["artifacts"], "receipt.json"):
                if (Path(tmp) / name).read_bytes() != (out / name).read_bytes():
                    problems.append(f"{name}: differs from a fresh conversion of {fresh['revision'][:7]}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gyropup", type=Path, help="a clean Gyropup checkout (read only)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify the committed example instead of writing it")
    args = parser.parse_args(argv)
    if args.check:
        problems = check(args.out, args.gyropup)
        for problem in problems:
            print(problem, file=sys.stderr)
        if not problems:
            print("Gyropup replay example matches its receipt" + (" and a fresh conversion." if args.gyropup else "."))
        return 1 if problems else 0
    if args.gyropup is None:
        parser.error("--gyropup <checkout> is required to convert")
    args.out.mkdir(parents=True, exist_ok=True)
    receipt = convert(args.gyropup, args.out)
    sizes = {name: (args.out / name).stat().st_size for name in receipt["artifacts"]}
    print(f"Converted Gyropup {receipt['revision'][:7]}: " + ", ".join(f"{k} {v:,} B" for k, v in sizes.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
