"""Fan curves from manufacturers' datasheets, for :func:`cadagent.formulas.fan_operating_point` and the site's
fan-curve explorer (``webkit/fan-curve.js``).

    from cadagent import formulas as fx
    from cadagent.thermal.fans import FANS
    fan = FANS["w2g115-ad15-13-12v"]
    k = fx.system_coefficient(12.0, 100 / 3600)          # the enclosure needs 12 Pa at 100 m3/h
    op = fx.fan_operating_point(fan.curve(), k)
    op["flow"] * 3600, op["pressure"], op["stall"]        # m3/h, Pa, whether the fan runs in its stall region

Each curve is the datasheet's own marked points on its air-performance chart, read from the vector drawing in the PDF
(the chart's lines and markers are stored as coordinates, so no picture is digitised by eye): to about 1 m3/h and
1 Pa. The datasheet also tabulates a few measured values at each voltage, rounded to 5 m3/h and 1 Pa, where the fan
meets three published system curves (``table``); tests/test_formulas.py solves those operating points from ``points``
and the system curves and finds the table again.

Limits: the maker's test rig (ISO 5801, installation category A: free inlet, ducted outlet) at the chart's air
density. A fan behind a grille, a finger guard or a board a few millimetres away loses pressure the chart does not
show, so measure the real installation, or model it (cadagent.simulation.cfd). Add a fan here only with its datasheet's
item number, revision and page, and read its points from the datasheet, not from a picture of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

_W2G115 = ("ebm-papst Mulfingen, data sheet W2G115-AD15-13 (EC axial compact fan, 115 mm, 7 blades), item no. "
           "50788-5-9980, change 88913, approved 2016-05-09, p. 5 (Curves: Air performance, pfs for rho = 1.2 kg/m3, "
           "measured to ISO 5801 installation category A; Measured values); the marked points read from the PDF's "
           "vector chart: https://static.chipdip.ru/lib/297/DOC044297989.pdf (a distributor's copy of the maker's PDF)")


@dataclass(frozen=True)
class DatasheetFan:
    """One fan at one supply voltage: its curve as the datasheet draws it, and what the datasheet tabulates."""
    key: str
    name: str
    voltage: float                              # V DC
    speed: float                                # rpm at free air (the table)
    power: float                                # W at free air (the table)
    points: Tuple[Tuple[float, float], ...]     # (m3/h, Pa): the chart's marked points, low flow first
    table: Tuple[Tuple[float, float], ...]      # (m3/h, Pa): the datasheet's measured values, as printed (rounded)
    density: float                              # kg/m3 the pressures are for
    source: str

    def curve(self) -> List[Tuple[float, float]]:
        """The curve in SI, as cadagent.formulas takes it: [(Q m3/s, dp Pa)]."""
        return [(q / 3600.0, p) for q, p in self.points]


def _w2g115(volts: float, speed: float, power: float, points, table) -> DatasheetFan:
    return DatasheetFan(f"w2g115-ad15-13-{volts:g}v", f"ebm-papst W2G115-AD15-13 at {volts:g} V", volts, speed, power,
                        tuple(points), tuple(table), 1.2, _W2G115)


# The three curves on p. 5, one per supply voltage (8 to 16 V; 12 V is nominal). Flow in m3/h, pressure in Pa.
FANS: Dict[str, DatasheetFan] = {f.key: f for f in (
    _w2g115(8, 1855, 1.80,
            [(0.0, 40.6), (24.6, 32.2), (48.0, 20.8), (54.7, 18.7), (61.6, 14.5), (69.3, 13.4), (75.9, 12.4),
             (89.2, 13.4), (93.8, 12.4), (104.9, 10.3), (116.9, 5.2), (128.9, 0.0)],
            [(130, 0), (120, 4), (110, 9), (90, 13)]),
    _w2g115(12, 2870, 4.5,
            [(0.0, 83.0), (20.2, 72.6), (54.3, 62.3), (73.4, 46.7), (93.4, 33.2), (94.7, 32.1), (102.1, 30.0),
             (107.2, 31.1), (118.1, 31.1), (132.2, 31.1), (143.6, 29.0), (152.4, 26.0), (162.8, 20.7),
             (181.1, 10.4), (197.3, 0.0)],
            [(195, 0), (180, 10), (165, 20), (140, 30)]),
    _w2g115(16, 3690, 8.9,
            [(0.0, 135.5), (54.9, 104.2), (84.7, 83.5), (112.1, 63.7), (121.9, 54.2), (126.2, 52.1), (143.8, 52.1),
             (153.1, 53.2), (163.7, 52.1), (171.7, 51.1), (182.1, 49.0), (195.9, 42.8), (216.1, 32.3),
             (236.8, 15.7), (260.5, 0.0)],
            [(260, 0), (235, 16), (210, 34), (180, 50)]),
)}
