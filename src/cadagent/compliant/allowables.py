"""Allowable snap-fit strain for printed (FDM) parts, by print direction, from manufacturer datasheets.

The moulding guides (Covestro/Bayer, DuPont, BASF) give permissible strains for injection-moulded resin. A printed part
is weaker across its layers than along them, and much more so in **strain to failure** than in strength: across the
layers the datasheets below keep 40-90 % of the in-plane strength but only 10-61 % of the in-plane elongation at break
(Allum et al., Addit. Manuf. 34 (2020) 101297: the inter-layer bond reaches bulk strength; the grooves between
filaments act as notches). Those ranges are for PLA, PETG, ASA and CoPA; carbon-filled PA6 keeps 90-96 % of its
elongation, because the fibre already limits it in-plane. Snap fits are limited by strain, so the direction matters
more than strength data suggest.

**Rule** (derived; research/compliant-mechanisms.md section 6). For each direction, from the datasheet values:

* single joining: ``min(0.7 * UTS / E, 0.5 * elongation_at_break)``. 0.7 x yield strain is the guide's rule for
  amorphous resin, with UTS/E as a lower bound on the strain at maximum stress; half the elongation at break is the
  guide's rule for materials without a yield point (Fig. 13);
* repeated joining: 0.6 x single (Table 2 note);
* across the layers: the smaller of the Z and XY values; and never above the moulded value for the same polymer family
  where a moulding guide gives one.

Every value is a **hypothesis until a coupon is measured** (a printed cantilever pulled to failure in both directions,
cad-agent #94). The datasheet specimens are 100 % infill, so a part with fewer perimeters or sparse infill at the root
is weaker still. Datasheets are for one printer and profile; a different machine, nozzle or drying state changes them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

REPEATED_USE_FACTOR = 0.6
AMORPHOUS_YIELD_FACTOR = 0.7
NO_YIELD_BREAK_FACTOR = 0.5
DIRECTIONS = ("along", "across")   # bending stress along the layers (arm lies in XY) or across them (arm built in Z)
STATUS = "derived from the datasheet; a hypothesis until a printed coupon is measured"

_PM = "https://wiki.polymaker.com/polymaker-products/more-about-our-products/documents/technical-data-sheets/"
_AX = "https://www.additive-x.com/shop/mpattachments/file/viewonline/id/{}/product_id/{}"
_DUP_PA66 = "DuPont, General Design Principles - Module I, Table 10.06 (Zytel 101 PA66)"
_DUP_PAGF = ("DuPont, General Design Principles - Module I, Table 10.06 (Zytel GR glass-filled PA66, lower end); "
             "the nearest moulded family for fibre-filled nylon")


@dataclass(frozen=True)
class PrintedMaterial:
    """Datasheet values for one filament, in-plane (XY) and across the layers (Z), ISO 527 at 100 % infill."""
    name: str
    source: str
    e_mpa: Tuple[float, float]            # tensile modulus XY, Z
    uts_mpa: Tuple[float, float]          # tensile strength XY, Z
    break_pct: Tuple[float, float]        # elongation at break XY, Z (percent)
    condition: str = ""
    moulded_cap: Optional[float] = None   # permissible single-joining strain of the moulded family, if a guide has one
    cap_source: str = ""
    friction: Optional[float] = None      # against steel, Covestro Table 3 mid-range, where the family is listed
    friction_same_factor: float = 1.0

    def _direction(self, direction: str) -> int:
        if direction not in DIRECTIONS:
            raise ValueError(f"orientation must be one of {DIRECTIONS}: bending stress along the layers (arm in XY) "
                             "or across them (arm built along Z)")
        return DIRECTIONS.index(direction)

    def rule(self, axis: int) -> Tuple[float, str]:
        """Single-joining strain for one datasheet axis (0 = XY, 1 = Z) and which of the two limits governed."""
        from_yield = AMORPHOUS_YIELD_FACTOR * self.uts_mpa[axis] / self.e_mpa[axis]
        from_break = NO_YIELD_BREAK_FACTOR * self.break_pct[axis] / 100.0
        return (from_yield, "0.7 x UTS/E") if from_yield <= from_break else (from_break, "0.5 x elongation at break")

    def single(self, direction: str) -> float:
        d = self._direction(direction)
        eps = self.rule(0)[0] if d == 0 else min(self.rule(0)[0], self.rule(1)[0])
        return min(eps, self.moulded_cap) if self.moulded_cap is not None else eps

    def allowable(self, direction: str, repeated: bool = False) -> float:
        return self.single(direction) * (REPEATED_USE_FACTOR if repeated else 1.0)

    def secant_upper_bound(self, direction: str) -> float:
        """The datasheet tensile modulus for the direction. The secant modulus at the design strain is lower, so
        forces from it are upper bounds: conservative for mating force, optimistic for retention."""
        return self.e_mpa[self._direction(direction)]

    def mu(self, same_material: bool = True) -> Optional[float]:
        if self.friction is None:
            return None
        return self.friction * (self.friction_same_factor if same_material else 1.0)

    def derivation(self, direction: str, repeated: bool = False) -> Dict[str, Any]:
        xy, xy_by = self.rule(0)
        z, z_by = self.rule(1)
        return {"material": self.name, "source": self.source, "condition": self.condition,
                "orientation": direction, "repeated": repeated,
                "xy": {"strain": xy, "governed_by": xy_by}, "z": {"strain": z, "governed_by": z_by},
                "moulded_cap": self.moulded_cap, "cap_source": self.cap_source or None,
                "allowable": self.allowable(direction, repeated), "status": STATUS}


PRINTED: Dict[str, PrintedMaterial] = {
    "pla-bambu-basic": PrintedMaterial("Bambu PLA Basic", "Bambu Lab TDS V2.0 " + _AX.format(494, 2236),
                                       (2680, 2160), (39, 35), (12.2, 7.5)),
    "pla-bambu-matte": PrintedMaterial("Bambu PLA Matte", "Bambu Lab TDS V2.0 " + _AX.format(513, 2261),
                                       (1960, 1670), (32, 25), (32.8, 4.8)),
    "pla-polymaker": PrintedMaterial("Polymaker PolyLite PLA", "Polymaker TDS V5.4 " + _PM + "pla/polylite-tm-pla",
                                     (3427, 3065), (52.3, 40.5), (6.3, 1.8)),
    "petg-bambu-basic": PrintedMaterial("Bambu PETG Basic", "Bambu Lab TDS V2.0 " + _AX.format(580, 2330),
                                        (1460, 1120), (48, 39), (11.2, 5.7)),
    "petg-bambu-hf": PrintedMaterial("Bambu PETG HF", "Bambu Lab TDS V1.0 "
                                     "https://botland.com.pl/img/art/inne/25540_karta_produktu.pdf",
                                     (1810, 1540), (34, 23), (8.6, 5.1)),
    "petg-cf-bambu": PrintedMaterial("Bambu PETG-CF", "Bambu Lab TDS V2.0 " + _AX.format(596, 2346),
                                     (2460, 1340), (59, 38), (10.4, 4.7)),
    "petg-polymaker": PrintedMaterial("Polymaker PolyLite PETG", "Polymaker TDS V5.4 " + _PM + "petg-pet/polylite-tm-petg",
                                      (2117, 1899), (50.8, 42.8), (8.4, 3.3)),
    "asa-bambu": PrintedMaterial("Bambu ASA", "Bambu Lab TDS V2.0 " + _AX.format(612, 2399),
                                 (2450, 2120), (52, 35), (9.2, 4.6), condition="annealed and dried 80 degC / 12 h",
                                 friction=0.575, friction_same_factor=1.2),
    "asa-polymaker": PrintedMaterial("Polymaker PolyLite ASA", "Polymaker TDS V5.4 " + _PM + "abs-asa/polylite-tm-asa",
                                     (2379, 1965), (43.8, 32), (6.7, 1.65), friction=0.575, friction_same_factor=1.2),
    "copa-polymaker-dry": PrintedMaterial("Polymaker PolyMide CoPA (dry)", "Polymaker TDS V5.4 " + _PM
                                          + "nylon/polymide-tm-copa", (2703, 2209), (78.0, 45.8), (12.7, 1.3),
                                          condition="dry, annealed 80 degC / 6 h", moulded_cap=0.04,
                                          cap_source=_DUP_PA66 + ", dry", friction=0.35, friction_same_factor=1.5),
    "copa-polymaker-wet": PrintedMaterial("Polymaker PolyMide CoPA (wet)", "Polymaker TDS V5.4 " + _PM
                                          + "nylon/polymide-tm-copa", (724, 660), (34.3, 13.7), (13.2, 1.7),
                                          condition="water-saturated (6.16 % moisture)", moulded_cap=0.06,
                                          cap_source=_DUP_PA66 + ", 50 % RH", friction=0.35, friction_same_factor=1.5),
    "pa6-cf20-polymaker-dry": PrintedMaterial("Polymaker Fiberon PA6-CF20 (dry)", "Polymaker TDS V1.1 "
                                              "https://cdn.shopify.com/s/files/1/0548/7299/7945/files/"
                                              "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf", (8637, 3760), (109.3, 54.0),
                                              (2.1, 1.9), condition="dry, annealed 100 degC / 16 h",
                                              moulded_cap=0.008, cap_source=_DUP_PAGF + ", dry",
                                              friction=0.35, friction_same_factor=1.5),
    "pa6-cf20-polymaker-wet": PrintedMaterial("Polymaker Fiberon PA6-CF20 (wet)", "Polymaker TDS V1.1 "
                                              "https://cdn.shopify.com/s/files/1/0548/7299/7945/files/"
                                              "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf", (2508, 1056), (54.7, 25.5),
                                              (7.0, 6.7), condition="water-saturated", moulded_cap=0.015,
                                              cap_source=_DUP_PAGF + ", 50 % RH (the nearest stated condition)",
                                              friction=0.35, friction_same_factor=1.5),
}
