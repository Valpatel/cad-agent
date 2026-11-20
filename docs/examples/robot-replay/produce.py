"""Original MuJoCo arm example: editable inputs -> actual solver poses + bound receipt.

Requires the existing cad-agent robot extra. No browser physics and no external assets.
Run from any directory; --out writes a portable bundle and --check verifies committed bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "software/cadagent/webkit/simulation/examples/two-link-arm"
REFERENCES = [
    "https://mujoco.readthedocs.io/en/3.3.7/APIreference/APIfunctions.html#mj-step",
    "https://mujoco.readthedocs.io/en/3.3.7/APIreference/APIfunctions.html#mj-forward",
    "https://mujoco.readthedocs.io/en/3.3.7/APIreference/APItypes.html#mjdata",
    "https://mujoco.readthedocs.io/en/3.3.7/XMLreference.html#body-inertial",
]


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def numbers(values):
    return " ".join(format(n, ".12g") for n in values)


def validate_config(c):
    """Reject nonfinite/unbounded runs before invoking the native solver."""
    scalars = {"duration_s": (0.1, 60), "timestep_s": (0.0001, 0.01), "sample_hz": (1, 200),
               "base_radius_m": (0.01, 2), "base_height_m": (0.01, 2), "shoulder_height_m": (0.01, 3)}
    vectors = {"gravity_m_s2": (3, -30, 30), "link_lengths_m": (2, .01, 3),
               "link_widths_m": (2, .005, 1), "link_depths_m": (2, .005, 1),
               "link_masses_kg": (2, .001, 100), "joint_damping_nms_rad": (2, 0, 100),
               "joint_range_rad": (2, -math.pi, math.pi), "initial_joint_rad": (2, -math.pi, math.pi),
               "target_offset_rad": (2, -math.pi, math.pi), "target_amplitude_rad": (2, 0, math.pi),
               "target_frequency_hz": (2, 0, 5), "target_phase_rad": (2, -math.tau, math.tau),
               "kp_nm_rad": (2, 0, 1000), "kd_nms_rad": (2, 0, 100), "torque_limit_nm": (2, .01, 1000)}
    def bounded(v, lo, hi):
        return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi
    for key, (lo, hi) in scalars.items():
        if not bounded(c.get(key), lo, hi):
            raise ValueError(f"{key} outside [{lo}, {hi}]")
    for key, (n, lo, hi) in vectors.items():
        v = c.get(key)
        if not isinstance(v, list) or len(v) != n or not all(bounded(x, lo, hi) for x in v):
            raise ValueError(f"{key} requires {n} finite bounded values")
    if c["joint_range_rad"][0] >= c["joint_range_rad"][1]:
        raise ValueError("joint range must increase")
    if not isinstance(c.get("title"), str) or not 1 <= len(c["title"]) <= 160:
        raise ValueError("title required")
    if not isinstance(c.get("assumptions"), list) or not c["assumptions"] or not all(isinstance(s, str) and 0 < len(s) <= 500 for s in c["assumptions"]):
        raise ValueError("explicit bounded assumptions required")
    steps = c["duration_s"] / c["timestep_s"]
    stride = 1 / (c["sample_hz"] * c["timestep_s"])
    if abs(steps-round(steps)) > 1e-7 or abs(stride-round(stride)) > 1e-7 or stride < 1 or round(steps) % round(stride):
        raise ValueError("duration and sampling interval must be whole solver steps")
    if steps > 100000 or steps / stride > 20000:
        raise ValueError("run exceeds step/sample budget")
    return round(steps), round(stride)


def build_model(c):
    validate_config(c)
    root = ET.Element("mujoco", model="original_two_link_arm")
    ET.SubElement(root, "compiler", angle="radian", inertiafromgeom="false")
    ET.SubElement(root, "option", timestep=str(c["timestep_s"]), gravity=numbers(c["gravity_m_s2"]),
                  integrator="implicitfast", solver="Newton", iterations="50", tolerance="1e-10")
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "geom", name="floor", type="plane", size="2 2 .1", rgba=".2 .2 .2 1")
    base = ET.SubElement(world, "body", name="base")
    ET.SubElement(base, "geom", name="base_shape", type="cylinder", size=numbers([c["base_radius_m"], c["base_height_m"]/2]),
                  pos=numbers([0, 0, c["base_height_m"]/2]), rgba=".22 .32 .44 1")
    parent = base
    for i, name in enumerate(("upper", "forearm")):
        length, width, depth, mass = (c[key][i] for key in ("link_lengths_m", "link_widths_m", "link_depths_m", "link_masses_kg"))
        body = ET.SubElement(parent, "body", name=name,
                             pos=numbers([0, 0, c["shoulder_height_m"] if i == 0 else c["link_lengths_m"][0]]))
        inertia = [mass*(depth*depth+length*length)/12, mass*(width*width+length*length)/12, mass*(width*width+depth*depth)/12]
        ET.SubElement(body, "inertial", pos=numbers([0, 0, length/2]), mass=str(mass), diaginertia=numbers(inertia))
        ET.SubElement(body, "joint", name=name+"_hinge", type="hinge", axis="0 1 0", limited="true",
                      range=numbers(c["joint_range_rad"]), damping=str(c["joint_damping_nms_rad"][i]))
        ET.SubElement(body, "geom", name=name+"_shape", type="box", size=numbers([width/2, depth/2, length/2]),
                      pos=numbers([0, 0, length/2]), rgba=".04 .75 .84 1" if i == 0 else "1 .45 .13 1")
        ET.SubElement(body, "geom", name=name+"_joint", type="sphere", size=".052", rgba=".6 .69 .8 1", contype="0", conaffinity="0")
        if i == 1:
            ET.SubElement(body, "geom", name="tool_marker", type="sphere", size=".04", pos=numbers([0, 0, length]),
                          rgba=".18 .85 .5 1", contype="0", conaffinity="0")
        parent = body
    actuators = ET.SubElement(root, "actuator")
    for i, name in enumerate(("upper", "forearm")):
        limit = c["torque_limit_nm"][i]
        ET.SubElement(actuators, "motor", name=name+"_motor", joint=name+"_hinge", gear="1", ctrllimited="true", ctrlrange=numbers([-limit, limit]))
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def produce(config_path, out, check=False):
    import mujoco as mj
    import numpy as np
    config_bytes = Path(config_path).read_bytes()
    c = json.loads(config_bytes)
    steps, stride = validate_config(c)
    xml = build_model(c)
    model = mj.MjModel.from_xml_string(xml.decode())
    data = mj.MjData(model)
    joints = [model.joint(name+"_hinge") for name in ("upper", "forearm")]
    qpos = [j.qposadr[0] for j in joints]
    dofs = [j.dofadr[0] for j in joints]
    data.qpos[qpos] = c["initial_joint_rad"]
    mj.mj_forward(model, data)
    body_ids = [model.body(name).id for name in ("base", "upper", "forearm")]
    def xyzw(q):
        return [float(q[1]), float(q[2]), float(q[3]), float(q[0])]
    bodies = []
    for body in body_ids:
        geometry = []
        for geom in range(model.ngeom):
            if model.geom_bodyid[geom] != body:
                continue
            kind = int(model.geom_type[geom])
            if kind == int(mj.mjtGeom.mjGEOM_BOX):
                shape, size = "box", (2*model.geom_size[geom]).tolist()
            elif kind == int(mj.mjtGeom.mjGEOM_CYLINDER):
                shape, size = "cylinder", [float(model.geom_size[geom][0]), float(2*model.geom_size[geom][1])]
            elif kind == int(mj.mjtGeom.mjGEOM_SPHERE):
                shape, size = "sphere", [float(model.geom_size[geom][0])]
            else:
                raise ValueError("unsupported recording primitive")
            color = "#" + "".join(f"{round(float(v)*255):02x}" for v in model.geom_rgba[geom][:3])
            geometry.append({"shape": shape, "size": size, "position": model.geom_pos[geom].tolist(),
                             "quaternion": xyzw(model.geom_quat[geom]), "color": color})
        name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body)
        bodies.append({"id": name, "label": {"base": "Fixed base", "upper": "Upper arm", "forearm": "Forearm and tool"}[name], "geometry": geometry})
    frames = []
    peak_torque = np.zeros(2)
    max_speed = np.zeros(2)
    max_target_error = np.zeros(2)
    def capture():
        frames.append({"time_s": round(float(data.time), 12), "poses": [
            {"position": data.xpos[b].tolist(), "quaternion": xyzw(data.xquat[b])} for b in body_ids]})
    capture()
    for step in range(1, steps+1):
        target = np.array(c["target_offset_rad"]) + np.array(c["target_amplitude_rad"]) * np.sin(
            math.tau*np.array(c["target_frequency_hz"])*data.time + np.array(c["target_phase_rad"]))
        error = target-data.qpos[qpos]
        torque = np.array(c["kp_nm_rad"])*error-np.array(c["kd_nms_rad"])*data.qvel[dofs]
        limits = np.array(c["torque_limit_nm"])
        data.ctrl[:] = np.clip(torque, -limits, limits)
        peak_torque = np.maximum(peak_torque, np.abs(data.ctrl))
        max_target_error = np.maximum(max_target_error, np.abs(error))
        mj.mj_step(model, data)
        mj.mj_forward(model, data)  # body world poses must correspond to the integrated qpos/time
        max_speed = np.maximum(max_speed, np.abs(data.qvel[dofs]))
        if not all(np.isfinite(v).all() for v in (data.qpos, data.qvel, data.xpos, data.xquat)):
            raise ValueError("nonfinite solver state")
        if np.any(data.warning.number):
            raise ValueError("solver warning: recording refused")
        if step % stride == 0:
            capture()
    recording = {"schema": "cad-agent.pose-recording/1", "title": c["title"],
                 "convention": {"length": "m", "up": "z", "handedness": "right", "quaternion": "xyzw"},
                 "bodies": bodies, "frames": frames}
    recording_bytes = encoded(recording)
    source_key = "docs/examples/robot-replay/produce.py"
    try:
        config_key = Path(config_path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        config_key = "external-config-input"  # no private filesystem path in a portable receipt
    receipt = {"schema": "cad-agent.simulation-receipt/1", "kind": "recorded simulation replay",
               "engine": {"name": "MuJoCo", "version": mj.__version__},
               "sources": {source_key: sha(Path(__file__).read_bytes()), config_key: sha(config_bytes)},
               "artifacts": {"model.xml": sha(xml), "recording.json": sha(recording_bytes)},
               "configuration": c, "references": REFERENCES,
               "effective_settings": {"timestep_s": float(model.opt.timestep), "gravity_m_s2": model.opt.gravity.tolist(),
                                      "integrator": "implicitfast", "solver": "Newton", "iterations": int(model.opt.iterations),
                                      "tolerance": float(model.opt.tolerance), "sample_hz": c["sample_hz"], "completed_steps": steps,
                                      "duration_s": float(frames[-1]["time_s"]), "frame_count": len(frames),
                                      "randomness": "none; deterministic sinusoidal joint PD targets"},
               "observations": {"peak_applied_torque_nm": peak_torque.tolist(), "max_joint_speed_rad_s": max_speed.tolist(),
                                "max_target_error_rad": max_target_error.tolist(), "solver_warning_counts": data.warning.number.tolist()},
               "limits": c["assumptions"]}
    payloads = {"model.xml": xml, "recording.json": recording_bytes, "receipt.json": encoded(receipt)}
    out = Path(out)
    if check:
        different = [name for name, data_bytes in payloads.items() if not (out/name).is_file() or (out/name).read_bytes() != data_bytes]
        if different:
            raise ValueError("generated outputs differ: " + ", ".join(different))
    else:
        out.mkdir(parents=True, exist_ok=True)
        for name, data_bytes in payloads.items():
            (out/name).write_bytes(data_bytes)
    return recording, receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    recording, receipt = produce(args.config, args.out, args.check)
    print(f"MuJoCo {receipt['engine']['version']}: {len(recording['frames'])} actual pose samples, {receipt['effective_settings']['completed_steps']} solver steps")
