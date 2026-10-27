"""Evaluator for the two-wheel-legged example: textbook estimates, not a robot model.

cad-agent calls ``evaluate(candidate)`` for every design (``cad: explore: evaluator:`` in cad-agent.yaml). The
candidate carries the parts picked for each slot (``candidate.part(slot)``, ``candidate.spec(slot, key)``), the
design's parameters (``candidate.param("leg.length_mm")``) and the bill of materials of the catalogue parts
(``candidate.bom``). Everything below is a rule of thumb, so the metrics are marked as estimates.
"""

from __future__ import annotations

import math

G = 9.81
DYNAMIC = 2.5             # standing up fast or landing a hop, over the static load (rule of thumb)
CROUCH_LEVER = 0.6        # knee lever arm in a deep crouch, as a fraction of the leg length (estimate)
EFFICIENCY = 0.85         # battery energy that reaches the loads (estimate)
SPEED_FACTOR = 0.8        # loaded speed over no-load speed (estimate)
PRINTED_G_PER_MM = 2.2    # printed leg links per mm of leg length, both legs (estimate)
PLA_USD_PER_KG = 20.0


def _range_check(checks, slot_label, rng, v_min, v_max, cid, level="fail"):
    """The battery's voltage window must fit inside a part's accepted range."""
    if rng and (v_max > rng[1] or v_min < rng[0]):
        checks.append({"id": cid, "level": level,
                       "text": f"The battery runs {v_min:g}–{v_max:g} V; the {slot_label} accept {rng[0]}–{rng[1]} V."})


def evaluate(c):
    checks, metrics = [], {}
    leg_mm = float(c.param("leg.length_mm", 160))
    shell_g = float(c.param("body_shell_g", 900))

    # printed parts are not in the catalogue: the evaluator adds them as a BOM line
    printed_g = PRINTED_G_PER_MM * leg_mm * 2 + shell_g
    lines = [{"name": "Printed legs and body shell (PLA)", "qty": 1, "group": "Structure", "estimate": True,
              "price_usd": round(printed_g / 1000 * PLA_USD_PER_KG, 2), "mass_g": round(printed_g)}]
    mass_kg = c.bom["totals"]["mass_kg"] + printed_g / 1000           # the catalogue parts plus the printed ones
    wheels_kg = c.qty("wheel_motor") * (c.spec("wheel_motor", "mass_g", 0) / 1000)

    # battery window and the parts it feeds
    v_nom = c.spec("battery", "voltage_nominal_v")
    v_min, v_max = c.spec("battery", "voltage_min_v", v_nom), c.spec("battery", "voltage_max_v", v_nom)
    if v_min is None or v_max is None:
        checks.append({"id": "volts", "level": "warn", "text": "The battery has no voltage specs: voltages not checked."})
    else:
        _range_check(checks, "wheel motors", c.spec("wheel_motor", "voltage_range_v"), v_min, v_max, "volts-wheels")
        _range_check(checks, "leg actuators", c.spec("leg_actuator", "voltage_range_v"), v_min, v_max, "volts-legs")
        _range_check(checks, "computer", c.spec("compute", "input_voltage_range_v"), v_min, v_max, "volts-compute")

    # wheels: top speed and the lean the wheels can still catch
    dia_mm = c.spec("wheel_motor", "tyre_diameter_mm")
    rpm, rpm_v = c.spec("wheel_motor", "no_load_speed_rpm"), c.spec("wheel_motor", "voltage_nominal_v")
    if dia_mm and rpm and rpm_v and v_nom:
        speed = rpm * (v_nom / rpm_v) * SPEED_FACTOR * math.pi * dia_mm / 1000 / 60      # m/s; BLDC speed ∝ voltage
        metrics["top_speed_kmh"] = {"value": round(speed * 3.6, 1), "estimate": True}
    peak = c.spec("wheel_motor", "peak_torque_nm")
    if dia_mm and peak:
        accel = c.qty("wheel_motor") * peak / (dia_mm / 2000) / mass_kg
        lean = math.degrees(math.atan(accel / G))
        metrics["catch_lean_deg"] = {"value": round(lean, 1), "label": "lean it can catch", "estimate": True}
        if lean < 25:
            checks.append({"id": "balance", "level": "warn", "text": f"The wheels can only catch a {lean:.0f}° lean."})

    # legs: torque in a deep crouch, with a margin for standing up fast
    leg_peak = c.spec("leg_actuator", "peak_torque_nm")
    if leg_peak:
        per_leg_n = (mass_kg - wheels_kg) * G / 2
        needed = per_leg_n * CROUCH_LEVER * leg_mm / 1000 * DYNAMIC
        margin = leg_peak / needed
        metrics["leg_torque_margin_x"] = {"value": round(margin, 2), "label": "leg torque margin", "estimate": True}
        if margin < 1:
            checks.append({"id": "legs", "level": "fail",
                           "text": f"Standing up fast needs about {needed:.1f} N·m per actuator; peak is {leg_peak} N·m."})
        elif margin < 1.5:
            checks.append({"id": "legs", "level": "warn", "text": f"Only {margin:.1f}× the torque a fast stand needs."})

    # energy: average draw grows with the mass the legs hold and the wheels balance
    wh = c.spec("battery", "energy_wh")
    sensors_w = sum(c.spec(s, "power_typical_w", 0) for s in ("compute", "camera"))
    average_w = sensors_w + 4 * (2 + 0.5 * (mass_kg - wheels_kg)) + 1.5 * mass_kg
    metrics["average_power_w"] = {"value": round(average_w, 1), "label": "average power", "estimate": True}
    if wh:
        metrics["runtime_min"] = {"value": round(wh * EFFICIENCY / average_w * 60), "label": "runtime", "estimate": True}

    summary = (f"{c.part('wheel_motor')['name']} wheels, {c.part('leg_actuator')['name']} legs, "
               f"{c.part('battery')['name']}; {leg_mm:.0f} mm legs.")
    return {"metrics": metrics, "checks": checks, "lines": lines, "summary": summary}
