"""FEA results for drawing: the surface field cad-agent's FEA viewer reads (``"format": "cadagent-fea-viewer"``,
written by ``cadagent.fea``), decoded to numpy.

The field's surface triangles carry nodal von Mises stress. A drawing colours them by stress as a fraction of the
material's strength, capped at the design stress the FEA reports. That cap leaves out the artificial spikes at
idealised clamps and load patches, as the FEA's own safety factor does. The numbers it states (peak, strength,
first-failure factor) are the FEA's own, copied, never recomputed here.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np


def _array(spec: Dict[str, Any]) -> np.ndarray:
    a = np.frombuffer(base64.b64decode(spec["b64"]), dtype=np.dtype(spec["dtype"]).newbyteorder("<"))
    return a.reshape(spec["shape"])


def read_viewer_field(path: Path) -> Dict[str, Any]:
    """The surface (positions, triangles, nodal von Mises) and the headline numbers of an FEA viewer file."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("format") != "cadagent-fea-viewer" or d.get("version") != 1:
        raise ValueError(f"{path}: not a cadagent-fea-viewer v1 file")
    s = d["surface"]
    failure = d.get("failure", {})
    return {
        "name": d.get("name", ""),
        "positions": _array(s["positions"]).astype(float),
        "triangles": _array(s["index"]).astype(np.int64),
        "von_mises": _array(s["von_mises"]).astype(float),
        "strength_mpa": float(d["material"]["strength_mpa"]),
        "material": d["material"].get("name", ""),
        "design_mpa": float(failure.get("design_stress_mpa", d["result"].get("von_mises_design_mpa"))),
        "cap_mpa": float(failure.get("capped_at_mpa", failure.get("design_stress_mpa"))),
        "first_failure_factor": failure.get("first_failure_factor"),
        "safety_factor": d["result"].get("safety_factor"),
        "load_from": d["result"].get("load_from", ""),
        "assumptions": d.get("assumptions", d["result"].get("assumptions", "")),
        "hot_spots": d.get("hot_spots", []),
        "mesh": d["result"].get("mesh", {}),
    }


def triangle_fraction(field: Dict[str, Any]) -> np.ndarray:
    """Per surface triangle: the mean of its nodes' stress, capped at the design stress, over the strength."""
    vm = np.minimum(field["von_mises"], field["cap_mpa"])
    return vm[field["triangles"]].mean(axis=1) / field["strength_mpa"]
