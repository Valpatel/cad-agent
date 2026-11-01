"""Allowable snap-fit strain for printed (FDM) parts, by print direction, from manufacturer datasheets.

The moulding guides (Covestro/Bayer, DuPont, BASF) give permissible strains for injection-moulded resin. A printed part
is weaker across its layers than along them, and much more so in **strain to failure** than in strength: across the
layers the datasheets below keep 40-89 % of the in-plane strength but only 10-61 % of the in-plane elongation at break
(Allum et al., Addit. Manuf. 34 (2020) 101297: the inter-layer bond reaches bulk strength; the grooves between
filaments act as notches). Those ranges are for PLA, PETG, ASA and CoPA (the current editions); Polymaker's
carbon-filled PA6 keeps 90-96 % of its elongation, because the fibre already limits it in-plane (Bambu's PA6-CF, not
an entry here, keeps 64 %). Snap fits are limited by strain, so the direction matters more than strength data
suggest.

**Rule** (derived; research/compliant-mechanisms.md section 6). For each direction, from one sheet's values:

* single joining: ``min(0.7 * UTS / E, 0.5 * elongation_at_break)``. 0.7 x yield strain is the guide's rule for
  amorphous resin, with UTS/E as a lower bound on the strain at maximum stress; half the elongation at break is the
  guide's rule for materials without a yield point (Fig. 13);
* repeated joining: 0.6 x single (Table 2 note);
* across the layers: the smaller of the Z and XY values; and never above the moulded value for the same polymer family
  where a moulding guide gives one.

**Editions** (#156). A maker reissues its sheet, sometimes with new numbers for the same filament and sometimes for a
new formulation sold under the old name (Bambu PETG Basic V3.0). A spool does not say which edition it matches, so
every edition read is kept, each as a complete set of values (the rule never mixes UTS from one sheet with E from
another), and the cautious edition is taken per quantity:

* the allowable strain is the **lowest** any edition gives (a lower allowable is the cautious choice);
* the mating force takes the **highest** modulus any edition gives, and the retention (separation) force the
  **lowest**: a stiffer arm is harder to push on and holds harder. Both stand in for the secant modulus at the design
  strain, which is lower than either, so the mating force stays an upper bound and the retention force is still
  optimistic, by less. (The root strain at a given deflection is geometry only and does not depend on E.)

:meth:`PrintedMaterial.derivation` names the edition that governs each.

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

_DUP_PA66 = "DuPont, General Design Principles - Module I, Table 10.06 (Zytel 101 PA66)"
_DUP_PAGF = ("DuPont, General Design Principles - Module I, Table 10.06 (Zytel GR glass-filled PA66, lower end); "
             "the nearest moulded family for fibre-filled nylon")


@dataclass(frozen=True)
class Sheet:
    """One edition of one maker's technical data sheet, as read on 2026-10-31.

    Values are (X-Y, Z): in the layer plane and across the layers, ISO 527 tension, test bars at 100 % infill.
    ``date`` is the PDF's creation date, since the sheets carry none of their own. ``url`` links the maker's copy where
    the maker serves one; the PDFs are linked, never copied into this repository.
    """
    maker: str
    title: str
    edition: str
    date: str
    where: str                            # the page and table the values are on
    url: str
    e_mpa: Tuple[float, float]            # tensile modulus XY, Z
    uts_mpa: Tuple[float, float]          # tensile strength XY, Z
    break_pct: Tuple[float, float]        # elongation at break XY, Z (percent)
    bars: str = ""                        # how the sheet says its test bars were conditioned ("" if it does not)
    formulation: str = ""                 # set where the maker changed the filament but kept the product name

    @property
    def label(self) -> str:
        return f"{self.maker} {self.title} {self.edition}"

    @property
    def citation(self) -> str:
        return f"{self.label} (PDF of {self.date}), {self.where}: {self.url}"

    def rule(self, axis: int) -> Tuple[float, str]:
        """Single-joining strain for one axis (0 = XY, 1 = Z) of this sheet, and which of the two limits governed."""
        from_yield = AMORPHOUS_YIELD_FACTOR * self.uts_mpa[axis] / self.e_mpa[axis]
        from_break = NO_YIELD_BREAK_FACTOR * self.break_pct[axis] / 100.0
        return (from_yield, "0.7 x UTS/E") if from_yield <= from_break else (from_break, "0.5 x elongation at break")


@dataclass(frozen=True)
class PrintedMaterial:
    """One filament: every edition of its data sheet read (current first), and how its allowable is capped."""
    name: str
    sheets: Tuple[Sheet, ...]
    condition: str = ""                   # the material state the entry describes (dry, water-saturated, annealed)
    moulded_cap: Optional[float] = None   # permissible single-joining strain of the moulded family, if a guide has one
    cap_source: str = ""
    friction: Optional[float] = None      # against steel, Covestro Table 3 mid-range, where the family is listed
    friction_same_factor: float = 1.0
    note: str = ""                        # why these editions, where they differ in more than their numbers

    def __post_init__(self):
        if not self.sheets or not all(isinstance(s, Sheet) for s in self.sheets):
            raise ValueError(f"{self.name}: give at least one Sheet")

    @property
    def source(self) -> str:
        """Every edition read, current first, with where its values are."""
        return "; ".join(s.citation for s in self.sheets)

    def _direction(self, direction: str) -> int:
        if direction not in DIRECTIONS:
            raise ValueError(f"orientation must be one of {DIRECTIONS}: bending stress along the layers (arm in XY) "
                             "or across them (arm built along Z)")
        return DIRECTIONS.index(direction)

    def rule(self, axis: int) -> Tuple[float, str, Sheet]:
        """The lowest single-joining strain any edition gives for one axis (0 = XY, 1 = Z), its limit and its sheet."""
        return min(((*s.rule(axis), s) for s in self.sheets), key=lambda r: r[0])

    def single(self, direction: str) -> float:
        d = self._direction(direction)
        eps = self.rule(0)[0] if d == 0 else min(self.rule(0)[0], self.rule(1)[0])
        return min(eps, self.moulded_cap) if self.moulded_cap is not None else eps

    def allowable(self, direction: str, repeated: bool = False) -> float:
        return self.single(direction) * (REPEATED_USE_FACTOR if repeated else 1.0)

    def modulus_sheet(self, direction: str, lowest: bool = False) -> Sheet:
        """The edition with the highest tensile modulus for the direction, which the mating force is taken from; with
        ``lowest``, the edition with the lowest, which the retention force is taken from. On a tie, the current one."""
        d = self._direction(direction)
        return (min if lowest else max)(self.sheets, key=lambda s: s.e_mpa[d])

    def secant_upper_bound(self, direction: str) -> float:
        """The highest datasheet tensile modulus any edition gives for the direction, for the mating force. The secant
        modulus at the design strain is lower, so a mating force from it is an upper bound (the cautious side)."""
        return self.modulus_sheet(direction).e_mpa[self._direction(direction)]

    def retention_modulus(self, direction: str) -> float:
        """The lowest datasheet tensile modulus any edition gives for the direction, for the retention force: the
        cautious edition there. It is still above the secant modulus at the design strain, so the retention force
        from it is still optimistic, by less than from the highest."""
        return self.modulus_sheet(direction, lowest=True).e_mpa[self._direction(direction)]

    def mu(self, same_material: bool = True) -> Optional[float]:
        if self.friction is None:
            return None
        return self.friction * (self.friction_same_factor if same_material else 1.0)

    def strength_sheet(self, direction: str) -> Sheet:
        """The edition with the lowest tensile strength for the direction (across: the lower of its X-Y and Z values),
        which :meth:`strength` is taken from. On a tie, the current one."""
        d = self._direction(direction)
        return min(self.sheets, key=lambda s: s.uts_mpa[0] if d == 0 else min(s.uts_mpa))

    def strength(self, direction: str) -> float:
        """The lowest datasheet tensile strength (MPa) any edition gives for the direction: along the layers the X-Y
        value, across them the lower of X-Y and Z, as the allowable strain is taken. For a screw boss: the thread's
        shear and a lying boss's hoop stress cross the layers, an upright boss's hoop stress runs along them
        (cadagent.mechanical.bosses). A short-term strength of 100 % infill bars; a held load creeps below it."""
        s = self.strength_sheet(direction)
        return s.uts_mpa[0] if self._direction(direction) == 0 else min(s.uts_mpa)

    def derivation(self, direction: str, repeated: bool = False) -> Dict[str, Any]:
        xy, xy_by, xy_sheet = self.rule(0)
        z, z_by, z_sheet = self.rule(1)
        hi, lo = self.modulus_sheet(direction), self.modulus_sheet(direction, lowest=True)
        return {"material": self.name, "source": self.source, "condition": self.condition,
                "orientation": direction, "repeated": repeated,
                "editions": [s.label for s in self.sheets], "note": self.note or None,
                "xy": {"strain": xy, "governed_by": xy_by, "sheet": xy_sheet.label},
                "z": {"strain": z, "governed_by": z_by, "sheet": z_sheet.label},
                "modulus": {"mating": {"mpa": self.secant_upper_bound(direction), "sheet": hi.label},
                            "retention": {"mpa": self.retention_modulus(direction), "sheet": lo.label}},
                "moulded_cap": self.moulded_cap, "cap_source": self.cap_source or None,
                "allowable": self.allowable(direction, repeated), "status": STATUS}


# --------------------------------------------------------------------------- the sheets, as read on 2026-10-31
# Bambu Lab serves its sheets from its store (store.bblcdn.com, linked from each product page); the V2.0 copies are a
# reseller's (Additive-X), kept because Bambu no longer serves them and older spools were sold under them.
_BBL = "https://store.bblcdn.com/"
_AX = "https://www.additive-x.com/shop/mpattachments/file/viewonline/id/{}/product_id/{}"
_PM = "https://cdn.shopify.com/s/files/1/0548/7299/7945/files/"
_P2 = "p. 2, Mechanical Properties"


def _bambu(title, edition, date, url, e, uts, brk, bars, formulation=""):
    return Sheet("Bambu Lab", title, edition, date, _P2, url, e, uts, brk, bars, formulation)


PLA_BASIC_V3 = _bambu("PLA Basic Technical Data Sheet", "V3.0", "2025-04-25",
                      _BBL + "s1/default/58b85d0f3db94878854a28fdb8a0006e/Bambu_PLA_Basic_Technical_Data_Sheet.pdf",
                      (2580, 2060), (35, 31), (12.2, 7.5), "annealed and dried 55 degC / 8 h")
PLA_BASIC_V2 = _bambu("PLA Basic Technical Data Sheet", "V2.0", "2023-03-11", _AX.format(494, 2236),
                      (2680, 2160), (39, 35), (12.2, 7.5), "annealed and dried 55 degC / 8 h")
PLA_MATTE_V3 = _bambu("PLA Matte Technical Data Sheet", "V3.0", "2025-04-25",
                      _BBL + "s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf",
                      (1960, 1670), (30, 22), (14.8, 4.8), "annealed and dried 55 degC / 8 h")
PLA_MATTE_V2 = _bambu("PLA Matte Technical Data Sheet", "V2.0", "2023-05-10", _AX.format(513, 2261),
                      (1960, 1670), (32, 25), (32.8, 4.8), "annealed and dried 55 degC / 8 h")
PETG_BASIC_V3 = _bambu("PETG Basic Technical Data Sheet", "V3.0", "2026-01-25",
                       _BBL + "s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf",
                       (2780, 2550), (51, 35), (9.5, 5.2),
                       "not said to be annealed (the sheet advises against annealing PETG Basic)",
                       formulation="the reformulated filament: \"The all-new Bambu Lab PETG Basic ... The refined "
                                   "formula\"")
PETG_BASIC_V2 = _bambu("PETG Basic Technical Data Sheet", "V2.0", "2023-06-26", _AX.format(580, 2330),
                       (1460, 1120), (48, 39), (11.2, 5.7), "annealed and dried 65 degC / 8 h",
                       formulation="the earlier filament")
PETG_HF_V1 = _bambu("PETG HF Technical Data Sheet", "V1.0", "2024-07-18",
                    _BBL + "3a230e260a3a47c2b0db0156e07eef91.pdf",
                    (1810, 1540), (34, 23), (8.6, 5.1), "annealed and dried 75 degC / 8 h")
PETG_CF_V3 = _bambu("PETG-CF Technical Data Sheet", "V3.0", "2023-08-29", _BBL + "626e4f424bf345ae965ad0ddfcaf2459.pdf",
                    (2460, 1340), (35, 29), (10.4, 4.7), "annealed and dried 65 degC / 8 h")
PETG_CF_V2 = _bambu("PETG-CF Technical Data Sheet", "V2.0", "2023-03-11", _AX.format(596, 2346),
                    (2460, 1340), (59, 38), (10.4, 4.7), "annealed and dried 65 degC / 8 h")
ASA_V3 = _bambu("ASA Technical Data Sheet", "V3.0", "2023-09-19", _BBL + "ad7b08230c164e72856cffbe06bb7dc9.pdf",
                (2450, 2120), (37, 31), (9.2, 4.6), "annealed and dried 80 degC / 12 h")
ASA_V2 = _bambu("ASA Technical Data Sheet", "V2.0", "2023-07-26", _AX.format(612, 2399),
                (2450, 2120), (52, 35), (9.2, 4.6), "annealed and dried 80 degC / 12 h")

POLYLITE_PLA_V54 = Sheet("Polymaker", "PolyLite PLA Technical Data Sheet", "V5.4", "2024-04-29",
                         "p. 4, Mechanical Properties", _PM + "PolyLite_PLA_TDS_EN_V5.4.pdf",
                         (3426.9, 3064.9), (52.3, 40.5), (6.3, 1.8))
POLYLITE_PETG_V54 = Sheet("Polymaker", "PolyLite PETG Technical Data Sheet", "V5.4", "2024-04-22",
                          "p. 4, Mechanical Properties", _PM + "PolyLite_PETG_TDS_EN_V5.4.pdf",
                          (2116.8, 1898.7), (50.8, 42.8), (8.4, 3.3))
# Served at the V5.4 address, the sheet is now V6.0 for "Polymaker ASA" ("based on testing with Polymaker PolyLite ASA");
# its mechanical values are V5.4's.
POLYMAKER_ASA_V60 = Sheet("Polymaker", "ASA Technical Data Sheet", "V6.0", "2025-12-02",
                          "p. 1, Mechanical Properties", _PM + "PolyLite_ASA_TDS_EN_V5.4.pdf",
                          (2379, 1965), (43.8, 32), (6.7, 1.65))
_COPA = ("Polymaker", "PolyMide CoPA Technical Data Sheet", "V5.4", "2024-04-14")
COPA_DRY_V54 = Sheet(*_COPA, "p. 4, Mechanical Properties (Dry Status)", _PM + "PolyMide_CoPA_TDS_V5.4.pdf",
                     (2703, 2209), (78.0, 45.8), (12.7, 1.3), "annealed 80 degC / 6 h and dried 48 h")
COPA_WET_V54 = Sheet(*_COPA, "p. 4, Mechanical Properties (Wet Status)", _PM + "PolyMide_CoPA_TDS_V5.4.pdf",
                     (724, 660), (34.3, 13.7), (13.2, 1.7),
                     "annealed 80 degC / 6 h, then in water at 60 degC for 48 h: 6.16 % moisture")
_PA6CF = ("Polymaker", "Fiberon PA6-CF20 Technical Data Sheet", "V1.1", "2024-12-08")
PA6_CF20_DRY_V11 = Sheet(*_PA6CF, "p. 1, Mechanical Properties - Dry Status", _PM + "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf",
                         (8636.5, 3759.5), (109.3, 54.0), (2.1, 1.9), "annealed 100 degC / 16 h")
PA6_CF20_WET_V11 = Sheet(*_PA6CF, "p. 1, Mechanical Properties - Wet Status", _PM + "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf",
                         (2508.1, 1056.1), (54.7, 25.5), (7.0, 6.7),
                         "annealed 100 degC / 16 h, then in water at 60 degC for 48 h: 5.30 % moisture")

_PETG_BASIC_NOTE = ("V3.0 describes a reformulated filament sold under the same name, its bars not said to be "
                    "annealed; V2.0's were. A spool does not say which it is, so both are kept and the cautious one "
                    "taken per quantity: here V3.0 for both (allowable 0.96-1.28 % against V2.0's 2.3 %, modulus 2780 / "
                    "2550 MPa against 1460 / 1120). A printed coupon (#94) should record which filament it used.")

PRINTED: Dict[str, PrintedMaterial] = {
    "pla-bambu-basic": PrintedMaterial("Bambu PLA Basic", (PLA_BASIC_V3, PLA_BASIC_V2)),
    "pla-bambu-matte": PrintedMaterial("Bambu PLA Matte", (PLA_MATTE_V3, PLA_MATTE_V2)),
    "pla-polymaker": PrintedMaterial("Polymaker PolyLite PLA", (POLYLITE_PLA_V54,)),
    "petg-bambu-basic": PrintedMaterial("Bambu PETG Basic", (PETG_BASIC_V3, PETG_BASIC_V2), note=_PETG_BASIC_NOTE),
    "petg-bambu-hf": PrintedMaterial("Bambu PETG HF", (PETG_HF_V1,)),
    "petg-cf-bambu": PrintedMaterial("Bambu PETG-CF", (PETG_CF_V3, PETG_CF_V2)),
    "petg-polymaker": PrintedMaterial("Polymaker PolyLite PETG", (POLYLITE_PETG_V54,)),
    "asa-bambu": PrintedMaterial("Bambu ASA", (ASA_V3, ASA_V2), condition="annealed and dried 80 degC / 12 h",
                                 friction=0.575, friction_same_factor=1.2),
    "asa-polymaker": PrintedMaterial("Polymaker PolyLite ASA", (POLYMAKER_ASA_V60,), friction=0.575,
                                     friction_same_factor=1.2),
    "copa-polymaker-dry": PrintedMaterial("Polymaker PolyMide CoPA (dry)", (COPA_DRY_V54,),
                                          condition="dry, annealed 80 degC / 6 h", moulded_cap=0.04,
                                          cap_source=_DUP_PA66 + ", dry", friction=0.35, friction_same_factor=1.5),
    "copa-polymaker-wet": PrintedMaterial("Polymaker PolyMide CoPA (wet)", (COPA_WET_V54,),
                                          condition="water-saturated (6.16 % moisture)", moulded_cap=0.06,
                                          cap_source=_DUP_PA66 + ", 50 % RH", friction=0.35, friction_same_factor=1.5),
    "pa6-cf20-polymaker-dry": PrintedMaterial("Polymaker Fiberon PA6-CF20 (dry)", (PA6_CF20_DRY_V11,),
                                              condition="dry, annealed 100 degC / 16 h", moulded_cap=0.008,
                                              cap_source=_DUP_PAGF + ", dry", friction=0.35, friction_same_factor=1.5),
    "pa6-cf20-polymaker-wet": PrintedMaterial("Polymaker Fiberon PA6-CF20 (wet)", (PA6_CF20_WET_V11,),
                                              condition="water-saturated", moulded_cap=0.015,
                                              cap_source=_DUP_PAGF + ", 50 % RH (the nearest stated condition)",
                                              friction=0.35, friction_same_factor=1.5),
}
