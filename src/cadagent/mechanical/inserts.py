"""Heat-set threaded inserts and compression limiters in printed parts: the insert data with their sources, the hole
and boss to print for them, how each load direction is carried, and one check of a whole joint.

    from cadagent.mechanical.inserts import check_joint
    check_joint(insert="mcmaster-94459A140", material="pla-bambu-basic", axis="upright", boss_outside_mm=8,
                recess_mm=0.0, torque_nm=0.4, pull_n=150)
    # verdict pass / warn / fail, each check's value and limit, the capacities with their bands, the limits

``cad-agent inserts joints.yaml`` runs the same check on a file of joints (docs/inserts.md).

**What is data and what is model.** The inserts' dimensions are the makers' (each row names its page and the date it
was read). Their strengths are a shear model (:func:`cadagent.formulas.insert_shear_force`) calibrated to the
published tests in :data:`TESTS`; :func:`calibration` shows the fit. The plastic's strength is the cautious datasheet
value across the layers (:mod:`cadagent.mechanical.compliant.allowables`), as for a screw boss
(:mod:`cadagent.mechanical.bosses`). Nothing here proves a joint holds: the coupon plan (:func:`coupon_plan`) says
what to print and measure.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from cadagent import formulas as fx
from cadagent.review.gates.fasteners import COARSE_PITCH_MM          # ISO 261 coarse pitches
from cadagent._deps import require
from cadagent.mechanical.compliant.allowables import PRINTED, STATUS
from cadagent.mechanical.compliant.snapfit import POISSON_PLASTICS

MM = 1e-3
AXES = ("upright", "lying")       # the insert's axis along the build direction (Z), or in the layer plane


@dataclass(frozen=True)
class Insert:
    """One heat-set insert, as its maker lists it. Lengths in mm; ``None`` where the maker gives no value."""
    key: str
    maker: str
    part: str
    thread: str                      # "M3"
    diameter_mm: float               # the thread's nominal diameter
    pitch_mm: float
    length_mm: float                 # installed length
    outer_mm: Optional[float]        # the knurl's crests
    hole_mm: Optional[float]         # the maker's hole (its largest, where it gives a range)
    min_material_mm: Optional[float]  # the least material thickness the maker asks for (the hole's depth, blind)
    source: str                      # where each number was read, and when
    drill: str = ""
    volume_mm3: Optional[float] = None   # the metal's volume, from the maker's CAD
    cad_bore_mm: Optional[float] = None  # the bore the maker's CAD leaves empty
    hole_bottom_mm: Optional[float] = None   # a tapered hole's small end, where the maker gives one
    min_wall_mm: Optional[float] = None      # the least wall round the insert the maker asks for
    material: str = "brass"
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


_MC = "https://www.mcmaster.com/{}/"
_MC_READ = ("McMaster-Carr, Heat-Set Threaded Inserts for Plastic, product page {pn} ({url}), its specification table "
            "read with cadagent.mechanical.mcmaster on {date}")
_MC_CAD = "; outside diameter, volume and bore measured on McMaster-Carr's STEP model of {pn} (normalised, {date})"
_BDW = ("bd_warehouse (Apache-2.0, vendored at e6ae6e7), src/bd_warehouse/data/heatset_nut_parameters.csv, its "
        "McMaster-Carr columns for {pn}: outside diameter s, length m, minimum material thickness and drill; not "
        "re-read from McMaster (its pages asked this session for a login on 2026-11-01)")


def _mc(pn: str, date: str, cad: bool = False) -> str:
    return _MC_READ.format(pn=pn, url=_MC.format(pn), date=date) + (_MC_CAD.format(pn=pn, date=date) if cad else "")


# McMaster-Carr 94459A, brass, knurled, open end. "22 Ga." on the page is a No. 22 number drill (0.157 in); V and
# No. 30 are 0.377 in and 0.1285 in (number and letter drill sizes as bd_warehouse's drill_sizes.csv lists them).
INSERTS: Dict[str, Insert] = {i.key: i for i in (
    Insert("mcmaster-94459A120", "McMaster-Carr", "94459A120", "M2", 2.0, 0.4, 4.0, 3.6, 3.26, 4.7,
           _BDW.format(pn="94459A120") + "; the length and thread also in the part's title as read on 2026-10-27; "
           "the hole is the No. 30 drill (0.1285 in) bd_warehouse lists", drill="No. 30 (3.26 mm)"),
    Insert("mcmaster-94459A130", "McMaster-Carr", "94459A130", "M3", 3.0, 0.5, 4.3, 4.7, 4.0, 5.1,
           _mc("94459A130", "2026-10-27") + "; knurl diameter 4.7 mm from bd_warehouse's McMaster-Carr column s "
           "(vendored at e6ae6e7)", drill="No. 22 (3.99 mm)"),
    Insert("mcmaster-94459A140", "McMaster-Carr", "94459A140", "M3", 3.0, 0.5, 5.7, 4.72, 4.0, 6.5,
           _mc("94459A140", "2026-10-26", cad=True), drill="No. 22 (3.99 mm)", volume_mm3=42.13, cad_bore_mm=2.35),
    Insert("mcmaster-94459A160", "McMaster-Carr", "94459A160", "M4", 4.0, 0.7, 6.4, None, 5.6, 7.1,
           _mc("94459A160", "2026-10-27"), drill="7/32 in (5.56 mm)"),
    Insert("mcmaster-94459A775", "McMaster-Carr", "94459A775", "M5", 5.0, 0.8, 7.9, 7.11, 6.4, 8.6,
           _mc("94459A775", "2026-10-26", cad=True), drill="6.4 mm", volume_mm3=129.82, cad_bore_mm=3.96),
    Insert("mcmaster-94459A778", "McMaster-Carr", "94459A778", "M8", 8.0, 1.25, 12.7, None, 9.6, 13.5,
           _mc("94459A778", "2026-10-26"), drill="V (9.58 mm)"),
)}
MISSING = ("McMaster-Carr 94459A in M2.5 and M6, and the 93365A family: not read. McMaster's pages asked this session "
           "for a login on 2026-11-01 (cadagent.mechanical.mcmaster raised LoginRequired), so their rows wait for a "
           "session that can read them; nothing here is guessed for them")


def insert(key: str) -> Insert:
    if key not in INSERTS:
        raise ValueError(f"insert must be one of {sorted(INSERTS)}, not {key!r}")
    return INSERTS[key]


# ----------------------------------------------------------------------------- coupons: what to print and pull

COUPON_TESTS = ("pull", "torque", "clamp")


def coupon_side(ins: Insert) -> float:
    """The coupon block's side, mm: three knurl diameters and 2 mm, at least 12 mm, rounded up to a millimetre."""
    outer = ins.outer_mm or ins.hole_mm
    return float(max(12.0, math.ceil(3.0 * outer + 2.0)))


def coupon_block(ins: Insert, axis: str = "upright", hole_mm: Optional[float] = None,
                 depth_mm: Optional[float] = None, side_mm: Optional[float] = None, floor_mm: float = 3.0):
    """A test coupon for one insert, in its print orientation (+Z is the build direction): a square block with the
    insert's hole in the middle of one face. ``upright`` puts the hole in the top face (the insert's axis along Z);
    ``lying`` stands the same block on its side, so the axis lies in the layer plane. The same block serves the
    pull-out and the torque-out tests (its flats go in a vise). Returns a CadQuery solid; dimensions in mm."""
    cq = require("cadquery", "insert coupons")
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
    design = hole_design(ins, axis)
    hole = hole_mm if hole_mm is not None else design["diameter_mm"]
    depth = depth_mm if depth_mm is not None else design["depth_mm"]
    side = side_mm if side_mm is not None else coupon_side(ins)
    height = depth + floor_mm
    block = cq.Workplane("XY").box(side, side, height, centered=(True, True, False))
    block = block.faces(">Z").workplane().hole(hole, depth)
    solid = block.val()
    if axis == "lying":
        solid = solid.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90).translate(cq.Vector(0, 0, side / 2))
    return solid


def clamp_plate(thickness_mm: float, hole_mm: float, side_mm: float = 20.0):
    """The clamped part of a preload coupon: a square printed plate with one hole through it, for a compression
    limiter (the hole sized for its press fit) or for the screw alone (a clearance hole). +Z is the build direction."""
    cq = require("cadquery", "insert coupons")
    if not (0 < hole_mm < side_mm and thickness_mm > 0):
        raise ValueError("need 0 < hole_mm < side_mm and a positive thickness")
    return cq.Workplane("XY").box(side_mm, side_mm, thickness_mm, centered=(True, True, False)) \
        .faces(">Z").workplane().hole(hole_mm).val()


# ----------------------------------------------------------------------------- the material and its family

FAMILIES = {"pla": "pla", "petg": "petg", "asa": "asa", "copa": "nylon", "pa6": "nylon"}
SHEAR_FROM_TENSILE = 0.5             # maximum-shear-stress criterion (Shigley 10th ed., Section 5-4), as bosses.py


def family(material: str) -> str:
    """The polymer family of a datasheet filament (its key's first word): pla, petg, asa or nylon."""
    if material not in PRINTED:
        raise ValueError(f"material must be one of {sorted(PRINTED)}, not {material!r}")
    return FAMILIES[material.split("-")[0]]


def shear_strength(material: str) -> float:
    """The plastic's shear strength round an insert, Pa: half the lowest datasheet tensile strength across the layers.
    The knurl's shear cylinder crosses the layers whichever way the insert stands (as a screw boss's thread does)."""
    family(material)
    return SHEAR_FROM_TENSILE * PRINTED[material].strength("across") * 1e6


def _row(check: str, value: Any, limit: Any, verdict: str, detail: str, source: str = "") -> Dict[str, Any]:
    return {"check": check, "value": value, "limit": limit, "verdict": verdict, "detail": detail,
            **({"source": source} if source else {})}


def _worst(rows: List[Dict[str, Any]]) -> str:
    verdicts = {r["verdict"] for r in rows}
    return "fail" if "fail" in verdicts else "warn" if "warn" in verdicts else "pass"


# ----------------------------------------------------------------------------- where the rules and the tests come from

SRC = {
    "cnck-poster": "CNC Kitchen (TwoChefs GmbH), Heat-Set Insert Dimensions and Design Guidelines, poster PDF of "
                   "2025-06-30, p. 2, metric table (hole D2, minimum wall W; a blind hole at least L + 1 mm deep): "
                   "https://www.cnckitchen.com/s/CNCKitchen_Heat-Set-Insert-Dimensions-and-Design-Guidelines.pdf",
    "ruthex": "ruthex, the size table on its RX-M3x5.7 product page, read 2026-11-01 (hole d3, minimum wall W, hole "
              "depth L + 1 mm min.; the same walls as CNC Kitchen's): https://www.ruthex.de/products/"
              "ruthex-gewindeeinsatz-m3-100-stuck-rx-m3x5-7-messing-gewindebuchsen",
    "pem-si": "PennEngineering, SI Threaded Inserts for Plastics, bulletin SI of 2026-07-16: pp. SI-5 and SI-6 "
              "(holes; minimum hole depth 0.76 mm past the insert), p. SI-10 (pull-out and torque-out in ABS and "
              "polycarbonate), pp. SI-25 and SI-26 (boss 2 x the insert diameter; installed flush or up to 0.13 mm "
              "above the plastic; installed below the surface, an insert is subjected to jack-out)",
    "spirol-inserts": "SPIROL International, Inserts for Plastics Design Guide, edition 05/26, printed p. 5 (hole "
                      "depth the insert length plus two thread pitches; a straight hole tapers at most 1 degree "
                      "included; boss 2-3 x the insert diameter; flush, at most 0.13 mm proud) and pp. 20-21 "
                      "(performance in nylon 6/6): https://www.spirol.com/assets/files/"
                      "ins-threaded-inserts-design-guide-us.pdf",
    "spirol-3dp": "SPIROL International (K. Ionkin), How to Select a Threaded Insert for Your 3D Printed Assembly, "
                  "edition 04/26, p. 2 (a boss at least 1.5 x the knurl diameter in FDM, full performance from 2 x) "
                  "and p. 5 (wall loops at least the metric size; install at the heat-deflection temperature + "
                  "65 degC): https://www.spirol.com/assets/files/inserts-for-3d-printed-assemblies-us.pdf",
    "cnck-tips": "CNC Kitchen, Tips & Tricks for Heat-Set Inserts used in 3D printing (2021-10-01, read 2026-11-01): "
                 "an iron 10-20 degC above the print temperature (PLA about 225, PETG 245, ABS 265 degC); melt to "
                 "about 90 % of the depth, then press flush with a flat tool and hold; straight holes, no chamfer; "
                 "a horizontal hole may print small at its top: "
                 "https://www.cnckitchen.com/blog/tips-and-tricks-for-heat-set-inserts",
    "ruthex-tip": "ruthex, soldering-tip set LOE-SET-012 product page, read 2026-11-01: install at 10-15 degC above "
                  "the filament's hotend temperature",
    "cnck-2026": "CNC Kitchen, Are Our Heat-Set Insert Datasheets Wrong? (2026-03-28, read 2026-11-01): CNC Kitchen "
                 "M3x5.7 in Polymaker PolySonic PLA held about 1400 N at the small holes (3 per hole size); printed "
                 "holes came out about 0.25 mm under their CAD size, 4.2 mm in CAD was the sweet spot (about 90 % of "
                 "the maximum) and 0.2-0.3 mm over the maker's hole for small inserts; drilled true to size, the "
                 "major drop came between 4.1 and 4.2 mm: "
                 "https://www.cnckitchen.com/blog/are-our-heat-set-insert-datasheets-wrong",
    "cnck-2019": "CNC Kitchen, Threaded Inserts for 3D Prints - Cheap VS Expensive (2019-12-07, read 2026-11-01): "
                 "ruthex M3 in Prusament PLA at 100 % infill pulled out at 181 kg on average; bolt heads sheared off "
                 "at about 3 to 4 N m before any insert turned: "
                 "https://www.cnckitchen.com/blog/threaded-inserts-for-3d-prints-cheap-vs-expensive",
    "cnck-2020": "CNC Kitchen, Helicoils, Threaded Insets and Embedded Nuts in 3D Prints - Strength & Strength "
                 "Assessment (2020-05-30, read 2026-11-01): ruthex M3 in PETG, 4 perimeters, 100 % infill, 3 "
                 "samples: 119 kg pull-out on average, 3 N m until the insert started to rotate: "
                 "https://www.cnckitchen.com/blog/helicoils-threaded-insets-and-embedded-nuts-in-3d-prints-strength-"
                 "amp-strength-assessment",
    "laszlo-2026": "K. Laszlo, B. F. Szivos and V. Nemes, Mechanical Performance of Heat-Set Threaded Inserts in "
                   "FDM-Printed PLA Components, Engineering Proceedings 157 (2026) 40, doi:10.3390/"
                   "engproc2026157040: ruthex RX-M3x5.7 in eSun PLA, a 4.2 mm CAD hole, 40 % infill, 6 wall lines "
                   "in the sleeve, n = 3 per cell; pull-out by sleeve wall and infill pattern",
    "kastner-2023": "T. Kastner, J. Troschitz, C. Vogel, T. Behnisch, M. Gude and N. Modler, Investigation of the "
                    "Pull-Out Behaviour of Metal Threaded Inserts in Thermoplastic Fused-Layer Modelling (FLM) "
                    "Components, Journal of Manufacturing and Materials Processing 7 (2023) 42, doi:10.3390/"
                    "jmmp7010042: inserts along Z pulled out harder and more predictably than inserts in the layer "
                    "plane (a preliminary test, no numbers given); 30 to 70 % infill raised pull-out about 2.5 x; a "
                    "wall of 1.2 to 2.4 mm raised it from 1.0 to 1.5 kN and 3.2 mm no further",
    "materials-2025": "Assessment of the Drone Arm's Plastic-Metal Joint Mechanical Resistance Following Natural and "
                      "Artificial Aging of the 3D-Printed Plastic Component, Materials 18 (2025) 2591, doi:10.3390/"
                      "ma18112591, Table 3: brass inserts in PLA kept 26-55 % of their pull-out after a year of "
                      "natural ageing and 13-29 % after 44 days of UV, infrared and humidity cycling",
    "spirol-cl-2021": "SPIROL International, Compression Limiters Design Guide, edition 04/21: p. 3 (the limiter at "
                      "most the plastic's minimum thickness; 3-5 % compression a safe limit, 5-7 % safe for most "
                      "plastics), p. 4 (a torque gives its preload to +/- 25 %), p. 6 (formulas 1 to 3: the "
                      "plastic compressed under 5 % of its thickness, the seating force at most 75 % of the proof "
                      "load), p. 7 (the head or washer reaches over the limiter onto the plastic) and p. 14 "
                      "(standard lengths 3, 4, 5, 6 and 8 mm, L +0/-0.15): "
                      "https://www.spirol.com/library/main_catalogs/cmpl_us.pdf",
    "spirol-cl-2026": "SPIROL International, Compression Limiters Design Guide, edition 05/26 (Canada): p. 6 (boss "
                      "about 2 x the limiter diameter) and pp. 15-16 (CL6000 aluminium and CL8000 brass, M3-M10: "
                      "bore A, body B, knurl C, head H, hole; rated for 10.9 screws, p. 3 of the 04/21 edition): "
                      "https://ca.spirol.com/assets/files/cmpl-compression-limiter-design-guide-ca.pdf",
    "bulten-cl": "Bulten AB, Compression Limiters & Captive Bolt Assemblies (PDF of 2024-08-01): a boss wall of at "
                 "least 50 % of the bolt diameter; knurled limiters longer than the plastic isolate it from the "
                 "joint: https://www.bulten.com/media/luvfra41/compression-limiters-bulten.pdf",
    "spirol-wp-2022": "SPIROL International (C. L. Jones), How To Properly Mate Compression Limiters and Threaded "
                      "Inserts in Plastic Assemblies (2022): the limiter abuts the insert, its bore larger than the "
                      "screw and smaller than the insert's face, to avoid jack-out",
    "rothbart": "Shigley's Mechanical Engineering Design (8th ed., 2008) after Rothbart, Mechanical Design and "
                "Systems Handbook (2nd ed., 1985): a steel screw in a brass nut 0.15-0.19 dry, 0.10-0.15 with "
                "machine oil, as AmesWeb reproduces it (read 2026-11-01): "
                "https://amesweb.info/Screws/screw-nut-collar-friction-table.aspx",
    "vdi2230-friction": "Bossard, Friction and friction coefficients (01-2025), p. 57, after VDI 2230 (2015): "
                        "classes B (0.08-0.16) and C (0.14-0.24) cover bright and black-oxide steel from oiled to "
                        "as delivered (lightly oiled)",
    "bossard-proof": "Bossard, Screws property class 4.6 to 12.9 (01-2025), p. 12, after ISO 898-1: stress under "
                     "proof load 580 MPa (8.8), 830 MPa (10.9) and 970 MPa (12.9); its tables start at M3",
    "bossard-head": "Bossard, Surface pressure when mounted (01-2025), p. 55: an ISO 4762 head's least bearing "
                    "diameter dw and its hole dh, M4 6.53/4.5, M5 8.03/5.5, M6 9.38/6.6, M8 12.33/9 mm; p. 53: VDI "
                    "2230 Table A9 lists no plastics",
    "iso273": "ISO 273:1979, clearance holes for bolts and screws, medium series: M2 2.4, M2.5 2.9, M3 3.4, M4 4.5, "
              "M5 5.5, M6 6.6, M8 9 mm",
    "amza-2021": "C. G. Amza, A. Zapciu, F. Baciu, M. I. Vasile and A. I. Nicoara, Accelerated Aging Effect on "
                 "Mechanical Properties of Common 3D-Printing Polymers, Polymers 13 (2021) 4132, doi:10.3390/"
                 "polym13234132, Table 4: an M6 bolt with washers on printed PLA and PETG plates at 40.9 MPa under "
                 "the washer lost 3.3 % (PLA) and 11.5 % (PETG) of its untightening torque in 7 days; compressive "
                 "strength 78.06 MPa (PLA) and 65.94 MPa (PETG)",
    "liber-knec-2025": "A. Liber-Knec and S. Lagan, Effect of Mass Reduction of 3D-Printed PLA on Load Transfer "
                       "Capacity - A Circular Economy Perspective, Materials 18 (2025) 3262, doi:10.3390/ma18143262, "
                       "Table 5: printed PLA held at 2 % strain for 1 h kept 0.85 (100 % infill) and 0.78 (75 % and "
                       "25 %) of its stress",
    "covestro-pmd": "Covestro LLC, Engineering Polymers Part and Mold Design - Thermoplastics, A Design Guide (PDF "
                    "of 2015-10), p. 59 (a safety factor of at least 2.0) and p. 75, Table 3-7 (polycarbonate at "
                    "1.2 % strain and 40 degC kept 0.75 of its stress after a month, 0.67 after a year and 0.59 "
                    "after six)",
    "brass": "Smiths Metal Centres, C36000 brass datasheet (2023): yield 124-310 MPa by temper (typical values)",
}


def sources() -> Dict[str, str]:
    """Every outside document this module takes a number from, by key."""
    return dict(SRC)


# ----------------------------------------------------------------------------- the makers' hole and boss rules

# The least wall round the hole, by thread: CNC Kitchen's poster and ruthex's table print the same values.
MIN_WALL_MM = {"M2": 1.3, "M2.5": 1.6, "M3": 1.6, "M4": 2.1, "M5": 2.6, "M6": 3.3, "M8": 4.5, "M10": 6.0}
BOSS_FLOOR = 1.5                     # x the knurl diameter: SPIROL's least boss in FDM (spirol-3dp p. 2)
BOSS_FULL = 2.0                      # x the knurl diameter: full performance (spirol-3dp p. 2; pem-si SI-25)
PROUD_OK_MM = 0.13                   # proud by up to this still counts as flush (pem-si SI-25; spirol-inserts p. 5)
CAD_ALLOWANCE_MM = (0.2, 0.3)        # added to the maker's hole in CAD for a printed hole (cnck-2026)
STRAIGHT_TAPER_DEG = 1.0             # a straight hole's most included taper (spirol-inserts p. 5)
CLEARANCE_MM = {"M2": 2.4, "M2.5": 2.9, "M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0}   # iso273
HEAD_BEARING_MM = {"M4": 6.53, "M5": 8.03, "M6": 9.38, "M8": 12.33}                            # bossard-head
PROOF_STRENGTH_PA = {"8.8": 580e6, "10.9": 830e6, "12.9": 970e6}                               # bossard-proof
MARGIN = 2.0                         # kept under each insert and plastic limit (covestro-pmd p. 59)


def _knurl(ins: Insert) -> Tuple[float, str]:
    """The diameter the insert's knurl shears the plastic on, mm, and what it is."""
    if ins.outer_mm:
        return ins.outer_mm, "the knurl's crests"
    return ins.hole_mm, ("the maker's hole: the knurl's diameter was not read, so the shear cylinder is taken at the "
                         "hole, smaller than the knurl (the capacity comes out low, the boss rule a floor)")


def hole_design(ins: Insert, axis: str = "upright", through: bool = False,
                allowance_mm: float = CAD_ALLOWANCE_MM[0]) -> Dict[str, Any]:
    """The hole to print for an insert: its CAD diameter (the maker's hole plus the printed-hole allowance), straight,
    and deep enough for the melt; the plastic the insert pushes aside and the pocket below it. Lengths in mm."""
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
    if not (isinstance(allowance_mm, (int, float)) and 0.0 <= allowance_mm <= 1.0):
        raise ValueError(f"allowance_mm must be between 0 and 1 mm, not {allowance_mm!r}")
    maker = ins.hole_mm
    L, p = ins.length_mm, ins.pitch_mm
    rules = {"maker's least material thickness": ins.min_material_mm, "L + 1 mm (ruthex, CNC Kitchen)": L + 1.0,
             "L + 2 pitches (SPIROL)": L + 2.0 * p}
    rules = {k: v for k, v in rules.items() if v is not None}
    depth = L if through else max(rules.values())
    out: Dict[str, Any] = {
        "insert": ins.key, "axis": axis, "through": through, "maker_mm": maker,
        "diameter_mm": round(maker + allowance_mm, 3), "allowance_mm": allowance_mm, "taper_deg": 0.0,
        "taper_max_deg": STRAIGHT_TAPER_DEG, "chamfer": "none", "depth_mm": round(depth, 3),
        "depth_rules_mm": {k: round(v, 3) for k, v in rules.items()},
        "why": [f"the maker's hole is {maker:g} mm; a printed hole comes out about 0.25 mm small, so CAD takes "
                f"{allowance_mm:g} mm more (CNC Kitchen 2026: 0.2-0.3 mm for small inserts)",
                "straight, not tapered, and no chamfer (CNC Kitchen tips; SPIROL: a straight hole tapers at most "
                "1 degree included)",
                ("a through hole needs no extra depth (CNC Kitchen tips)" if through else
                 f"blind: {depth:g} mm deep, the deepest of the makers' rules, so the melt the insert pushes down has "
                 f"somewhere to go")],
    }
    if axis == "lying":
        out["why"].append("lying in the layer plane, the hole's top sags and prints small (CNC Kitchen tips): "
                          "measure it with a pin gauge, or print it as a teardrop (NopSCADlib's insert_hole does) "
                          "and open it out")
    if ins.volume_mm3 and ins.cad_bore_mm:
        displaced = fx.insert_displaced_volume(ins.volume_mm3 * MM ** 3, maker * MM, ins.cad_bore_mm * MM, L * MM)
        pocket = fx.overflow_volume(maker * MM, depth * MM, L * MM) if not through else 0.0
        out["displaced_mm3"] = round(displaced / MM ** 3, 3)
        out["overflow_mm3"] = round(pocket / MM ** 3, 3)
    return out


def boss_design(ins: Insert, line_mm: float = 0.42) -> Dict[str, Any]:
    """The boss to print round an insert: its least and its full-performance outside diameter, the wall, and how many
    perimeters to print it with. Lengths in mm; ``line_mm`` is the slicer's line width."""
    if not (isinstance(line_mm, (int, float)) and 0.1 <= line_mm <= 2.0):
        raise ValueError(f"line_mm must be a line width between 0.1 and 2 mm, not {line_mm!r}")
    knurl, basis = _knurl(ins)
    wall = MIN_WALL_MM.get(ins.thread)
    if wall is None:
        raise ValueError(f"no maker gives a wall for {ins.thread}")
    least = max(ins.hole_mm + 2.0 * wall, BOSS_FLOOR * knurl)
    full = max(least, BOSS_FULL * knurl)
    size = float(ins.thread[1:])
    loops = max(math.ceil((full - ins.hole_mm) / 2.0 / line_mm - 1e-9), math.ceil(size))
    return {"insert": ins.key, "least_outside_mm": round(least, 3), "outside_mm": round(full, 3),
            "least_wall_mm": wall, "wall_mm": round((full - ins.hole_mm) / 2.0, 3), "perimeters": loops,
            "line_mm": line_mm, "knurl_mm": knurl, "knurl_basis": basis,
            "why": [f"wall at least {wall:g} mm round the hole (CNC Kitchen poster; ruthex)",
                    f"outside at least {BOSS_FLOOR:g} x the knurl diameter, full performance from {BOSS_FULL:g} x "
                    "(SPIROL's 3D-printing paper; PEM: boss 2 x the insert diameter)",
                    f"print the boss solid: {loops} perimeters out to its outside, at least as many as the metric "
                    "size (SPIROL); pull-out rose about 2.5 x from 30 % to 70 % infill (Kastner 2023)",
                    "no maker gives an edge distance: keep at least the wall to any free face"]}


# ----------------------------------------------------------------------------- published tests and the calibration

G = 9.80665


@dataclass(frozen=True)
class Test:
    """One published pull-out (and torque-out) result: the insert, the host, the values as printed (mean), and which
    datasheet stands in for a printed host when the table has no sheet for that exact filament."""
    key: str
    source: str
    insert: str
    outer_mm: float
    length_mm: float
    host: str
    family: str
    printed: bool
    pull_n: Optional[float]
    torque_nm: Optional[float] = None
    torque_at_least: bool = False    # the torque is a lower bound (something else broke first)
    n: Optional[int] = None
    stand_in: Optional[str] = None   # a PRINTED key; None for a moulded host (no printed datasheet applies)
    note: str = ""


_RX = "ruthex RX-M3x5.7 (knurl 4.6 mm, length 5.7 mm: ruthex's table)"
_RX19 = ("ruthex M3 (the post names no length: ruthex's standard M3 is 5.7 mm, knurl 4.6 mm, and that is assumed)")
_LASZLO = [(1.28, "adaptive cubic", 1428.2, 3), (1.28, "cross-zag", 1353.6, 3), (1.28, "gyroid", 1467.2, 3),
           (1.60, "adaptive cubic", 1497.5, 3), (1.60, "cross-zag", 1416.9, 3), (1.60, "gyroid", 1488.7, 3),
           (1.92, "adaptive cubic", 1551.5, 3), (1.92, "cross-zag", 1520.9, 2), (1.92, "gyroid", 1526.1, 2)]
TESTS: Tuple[Test, ...] = (
    *(Test(f"laszlo-2026-{w:.2f}-{pat.split()[-1]}", SRC["laszlo-2026"] + f"; sleeve wall {w:.2f} mm, {pat} infill",
           _RX, 4.6, 5.7, "eSun PLA", "pla", True, f, n=n, stand_in="pla-polymaker") for w, pat, f, n in _LASZLO),
    Test("cnck-2026", SRC["cnck-2026"], "CNC Kitchen M3x5.7 (knurl 4.6 mm, length 5.7 mm: its poster)", 4.6, 5.7,
         "Polymaker PolySonic PLA", "pla", True, 1400.0, n=3, stand_in="pla-polymaker",
         note="'around 1400 N' as printed: the chart's points carry no values"),
    Test("cnck-2019", SRC["cnck-2019"], _RX19, 4.6, 5.7, "Prusament PLA", "pla", True, 181 * G, 3.0,
         torque_at_least=True, stand_in="pla-polymaker",
         note="181 kg x 9.80665; the screw broke first, so the torque-out is at least 3 N m"),
    Test("cnck-2020", SRC["cnck-2020"], _RX19, 4.6, 5.7, "PETG (maker not named)", "petg", True, 119 * G, 3.0, n=3,
         stand_in="petg-polymaker", note="119 kg x 9.80665"),
    # moulded hosts: not used to fit c (no printed datasheet applies), only for how torque-out scales with pull-out
    Test("spirol-ins19-m3", SRC["spirol-inserts"] + "; INS 19 long, M3 (4-40 row)", "SPIROL INS 19 long M3 (A 4.75, "
         "L 5.74 mm)", 4.75, 5.74, "nylon 6/6, moulded, drilled hole", "nylon", False, 1445.0, 3.0),
    Test("spirol-ins19-m5", SRC["spirol-inserts"] + "; INS 19 long, M5", "SPIROL INS 19 long M5 (A 7.16, L 9.53 mm)",
         7.16, 9.53, "nylon 6/6, moulded, drilled hole", "nylon", False, 3800.0, 14.0),
    Test("spirol-ins19-m8", SRC["spirol-inserts"] + "; INS 19 long, M8", "SPIROL INS 19 long M8 (A 10.34, L 12.70 mm)",
         10.34, 12.70, "nylon 6/6, moulded, drilled hole", "nylon", False, 5800.0, 33.0),
    Test("pem-iut-m3-abs", SRC["pem-si"] + "; IUT M3 in ABS", "PEM IUT M3 (E 4.55, A 5.74 mm)", 4.55, 5.74,
         "ABS, moulded, ultrasonic", "abs", False, 730.0, 1.6),
    Test("pem-iut-m5-abs", SRC["pem-si"] + "; IUT M5 in ABS", "PEM IUT M5 (E 6.93, A 9.52 mm)", 6.93, 9.52,
         "ABS, moulded, ultrasonic", "abs", False, 1197.0, 5.4),
    Test("pem-iut-m8-abs", SRC["pem-si"] + "; IUT M8 in ABS", "PEM IUT M8 (E 10.34, A 12.7 mm)", 10.34, 12.7,
         "ABS, moulded, ultrasonic", "abs", False, 3566.0, 26.0),
    Test("pem-iut-m3-pc", SRC["pem-si"] + "; IUT M3 in polycarbonate", "PEM IUT M3 (E 4.55, A 5.74 mm)", 4.55, 5.74,
         "polycarbonate, moulded, ultrasonic", "pc", False, 823.0, 1.8),
    Test("pem-iut-m5-pc", SRC["pem-si"] + "; IUT M5 in polycarbonate", "PEM IUT M5 (E 6.93, A 9.52 mm)", 6.93, 9.52,
         "polycarbonate, moulded, ultrasonic", "pc", False, 1691.0, 7.7),
    Test("pem-iut-m8-pc", SRC["pem-si"] + "; IUT M8 in polycarbonate", "PEM IUT M8 (E 10.34, A 12.7 mm)", 10.34, 12.7,
         "polycarbonate, moulded, ultrasonic", "pc", False, 4098.0, 26.0),
)
STAND_IN = ("a printed test's filament is rarely in the datasheet table, so the strongest sheet of its family stands "
            "in for it (PolyLite PLA, PolyLite PETG): c comes out at its lowest, and a weaker filament's capacity "
            "comes out lower than its tests would give")


def _median(v: List[float]) -> float:
    v = sorted(v)
    return v[len(v) // 2] if len(v) % 2 else 0.5 * (v[len(v) // 2 - 1] + v[len(v) // 2])


def calibration() -> Dict[str, Any]:
    """The shear model fitted to the published tests. For each test: the mean shear stress on the knurl's cylinder,
    q = F / (pi D L), and for a printed one c = q / tau, tau being half the stand-in datasheet's strength across the
    layers. c is fitted per polymer family; torque-out goes through the ratio of the two shears, r = 2 T / (F D),
    which the printed and the moulded tests both give."""
    rows, fits, ratios = [], {}, []
    for t in TESTS:
        q = t.pull_n / (math.pi * t.outer_mm * t.length_mm) if t.pull_n else None          # N / mm^2 = MPa
        row = {"key": t.key, "host": t.host, "family": t.family, "printed": t.printed, "insert": t.insert,
               "pull_n": t.pull_n, "torque_nm": t.torque_nm, "torque_at_least": t.torque_at_least, "n": t.n,
               "q_mpa": round(q, 3) if q else None, "source": t.source, "note": t.note}
        if t.printed and t.stand_in:
            tau = shear_strength(t.stand_in) / 1e6
            row.update(stand_in=t.stand_in, tau_mpa=tau, c=round(q / tau, 4))
            fits.setdefault(t.family, []).append(q / tau)
        if t.pull_n and t.torque_nm:
            r = 2.0 * t.torque_nm * 1e3 / (t.pull_n * t.outer_mm)
            row["torque_ratio"] = round(r, 4)
            if not t.torque_at_least:
                ratios.append((r, t.printed, t.key))
        rows.append(row)
    pull = {fam: {"low": min(c), "mid": _median(c), "high": max(c), "cells": len(c),
                  "tests": [t.key for t in TESTS if t.family == fam and t.printed]} for fam, c in fits.items()}
    every = [c for cs in fits.values() for c in cs]
    pull["pooled"] = {"low": min(every), "mid": _median(every), "high": max(every), "cells": len(every),
                      "tests": [t.key for t in TESTS if t.printed]}
    r_all = [r for r, _, _ in ratios]
    return {"pull": pull,
            "torque_ratio": {"low": min(r_all), "mid": _median(r_all), "high": max(r_all),
                             "printed": [round(r, 4) for r, printed, _ in ratios if printed],
                             "tests": [k for _, _, k in ratios]},
            "confidence": {"pla": f"medium: {pull['pla']['cells']} results from three publications by two groups, "
                                  "M3 x 5.7 inserts only",
                           "petg": "low: one result (3 samples), the insert's length assumed",
                           "pooled": "none for this family: no printed test was found; the lowest c of any family"},
            "stand_in": STAND_IN, "rows": rows}


# Pull-out kept after ageing, PLA only (materials-2025, Table 3: as installed to a year of natural ageing).
AGED_SHARE = {"pla": (0.26, 0.55)}


def capacity(ins: Insert, material: str, axis: str = "upright") -> Dict[str, Any]:
    """An insert's pull-out, push-out and torque-out in one printed material, each a band {low, mid, high} from the
    calibrated shear model. The low end is what a check holds a load to. ``axis`` is recorded but changes nothing:
    no published test gives a number for an insert lying in the layer plane."""
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
    fam = family(material)
    tau = shear_strength(material)
    D, basis = _knurl(ins)
    cal = calibration()
    fit_on = fam if fam in cal["pull"] else "pooled"
    c, r = cal["pull"][fit_on], cal["torque_ratio"]
    D_m, L_m = D * MM, ins.length_mm * MM
    pull = {k: fx.insert_shear_force(D_m, L_m, tau, c[k]) for k in ("low", "mid", "high")}
    torque = {k: fx.insert_shear_torque(D_m, L_m, tau, c[k] * r[k]) for k in ("low", "mid", "high")}
    return {"insert": ins.key, "material": material, "family": fam, "axis": axis,
            "pull_out": pull, "push_out": dict(pull), "torque_out": torque,
            "shear_strength_pa": tau, "diameter_mm": D, "diameter_basis": basis, "length_mm": ins.length_mm,
            "c": {k: c[k] for k in ("low", "mid", "high")}, "torque_ratio": {k: r[k] for k in ("low", "mid", "high")},
            "calibrated_on": fit_on, "confidence": cal["confidence"].get(fit_on, ""),
            "aged_share": AGED_SHARE.get(fam),
            "notes": ["push-out: no published test; the pull-out model is taken as is (low confidence)",
                      "lying: no published number; Kastner 2023 found inserts along Z stronger and more predictable"]}


# ----------------------------------------------------------------------------- installing

INSTALL = {
    "pla": "iron about 225 degC (CNC Kitchen tips: 10-20 degC over the print temperature; ruthex: 10-15 degC over "
           "it). The PLA tests used 190 degC with 15 s to preheat and 15 s to hold (Laszlo 2026), 210 degC (CNC "
           "Kitchen 2019), 230 degC (Materials 2025) and 240 degC with a straightener (CNC Kitchen 2026)",
    "petg": "iron about 245 degC (CNC Kitchen tips: 10-20 degC over the print temperature)",
    "asa": "no source gives ASA: 10-20 degC over its print temperature (CNC Kitchen tips); CNC Kitchen gives ABS "
           "about 265 degC",
    "nylon": "no source gives printed nylon: 10-20 degC over the print temperature (CNC Kitchen tips), or the "
             "heat-deflection temperature + 65 degC (SPIROL's 3D-printing paper)",
}
INSTALL_ALL = ("melt it in to about 90 % of its depth with the tip, then press it flush with a flat tool and hold it "
               "while it sets (CNC Kitchen tips); heat installation needs little force, generally under 220 N "
               "(SPIROL); flush, or proud by no more than 0.13 mm (PEM; SPIROL): never below the face, where the "
               "screw jacks it out")


def install_notes(material: str) -> Dict[str, str]:
    """How to set an insert into one printed material: the iron's temperature from the published rules and the tests
    that used it, and how to press it."""
    return {"material": material, "temperature": INSTALL[family(material)], "how": INSTALL_ALL}


# Printed compressive strength, measured (amza-2021, Table 4); other families take their datasheet strength along
# the layers, which is below the measured compressive strength of the two that were measured.
COMPRESSIVE_MPA = {"pla": 78.06, "petg": 65.94}
BEARING_BASIS = {"pla": "printed PLA's measured compressive strength, Amza 2021",
                 "petg": "printed PETG's measured compressive strength, Amza 2021",
                 "asa": "no printed compressive figure: the datasheet strength along the layers stands in, below it",
                 "nylon": "no printed compressive figure: the datasheet strength along the layers stands in, below it"}


def bearing_strength(material: str) -> float:
    """The pressure a printed material bears under a head, a flange or a limiter's end before it crushes, Pa."""
    fam = family(material)
    if fam in COMPRESSIVE_MPA:
        return COMPRESSIVE_MPA[fam] * 1e6
    return PRINTED[material].strength("along") * 1e6


# ----------------------------------------------------------------------------- friction, relaxation, limiters

THREAD_FRICTION = (0.10, 0.19)       # steel in brass, oiled to dry (rothbart)
COLLAR_ON_METAL = (0.08, 0.24)       # head on a steel or brass face, VDI 2230 classes B and C (vdi2230-friction)
COLLAR_ON_PLASTIC = (0.20, 0.65)     # head on plastic: the band bosses.py takes from Covestro's Table 3

# The share of a held stress a printed plastic keeps, measured, by family; and the moulded long-term reference.
RELAXATION = {
    "pla": {"hours": (0.78, 0.85), "hours_source": "liber-knec-2025", "joint_7d": 0.967, "joint_source": "amza-2021"},
    "petg": {"joint_7d": 0.885, "joint_source": "amza-2021"},
}
LONG_TERM_REFERENCE = (0.59, 0.67)   # moulded polycarbonate, 40 degC, 1-6 years (covestro-pmd Table 3-7)


@dataclass(frozen=True)
class Limiter:
    """A compression limiter, as its maker lists it. Diameters in mm: ``bore`` the largest bore, ``body`` the
    smallest body (its wall's outside), ``knurl`` the knurl's nominal (pressed into the hole), ``head`` a headed
    limiter's flange (0 when it has none), ``hole`` the maker's hole (min, max). Length tolerance +0/-tol."""
    key: str
    thread: str
    material: str                    # aluminium, brass or steel
    bore_mm: float
    body_mm: float
    knurl_mm: float
    head_mm: float
    hole_mm: Tuple[float, float]
    tolerance_mm: float
    modulus_pa: float
    rated_class: str                 # the screw class the maker rates it for; "" when it has no rating
    source: str
    yield_pa: Optional[float] = None    # its wall's yield, for a limiter with no maker's rating


_CL6000 = {"M3": (4.15, 5.42, 5.83, 7.35, (5.61, 5.69)), "M4": (5.15, 6.95, 7.38, 8.95, (7.14, 7.22)),
           "M5": (6.15, 8.47, 8.88, 10.55, (8.64, 8.72)), "M6": (7.15, 10.00, 10.43, 12.15, (10.19, 10.27)),
           "M8": (9.15, 13.36, 13.78, 15.35, (13.54, 13.62))}
_CL8000 = {"M3": (4.15, 6.03, 6.45, 7.75, (6.22, 6.30)), "M4": (5.15, 7.56, 7.97, 9.35, (7.73, 7.81)),
           "M5": (6.15, 9.09, 9.50, 10.95, (9.26, 9.34)), "M6": (7.15, 10.92, 11.34, 13.35, (11.10, 11.18)),
           "M8": (9.15, 14.58, 15.01, 17.35, (14.77, 14.85))}
LIMITERS: Dict[str, Limiter] = {}
for _series, _table, _mat, _E in (("cl6000", _CL6000, "aluminium", 69e9), ("cl8000", _CL8000, "brass", 97e9)):
    for _thread, (_a, _b, _c, _h, _hole) in _table.items():
        _k = f"spirol-{_series}-{_thread.lower()}"
        LIMITERS[_k] = Limiter(_k, _thread, _mat, _a, _b, _c, _h, _hole, 0.15, _E, "10.9",
                               SRC["spirol-cl-2026"] + "; modulus from p. 6 of the 04/21 edition (Table 2); "
                               "length tolerance +0/-0.15 (04/21, p. 14)")
LIMITER_LENGTHS_MM = (3.0, 4.0, 5.0, 6.0, 8.0)      # spirol-cl-2021 p. 14
POISSON_METAL = {"aluminium": 0.333, "brass": 0.324, "steel": 0.292}   # Shigley 10th ed., Table A-5
LIMITER_COMPRESSION = (0.05, 0.07)   # the plastic squeezed at most 5 % (safe), 7 % (safe for most): spirol-cl-2021
SEATING_SHARE = 0.75                 # the seating force at most 75 % of the proof load (spirol-cl-2021 p. 6)
SHEAR_OVER_YIELD = 0.577            # shear yield over tensile yield, distortion energy (shigley Section 5-5)
BRASS_YIELD_PA = (124e6, 310e6)      # the insert's face, by temper (brass)
CLAMP_PLATE_MM = 5.1                 # the coupon's clamped plate: 0.1 mm over a 5 mm limiter, the stack's slack
CLAMP_PLATE_TOL_MM = 0.05            # its thickness, printed and measured, to +/- this


def limiter(key: str) -> Limiter:
    if key not in LIMITERS:
        raise ValueError(f"limiter must be one of {sorted(LIMITERS)}, not {key!r}")
    return LIMITERS[key]


METAL_MODULUS_PA = {"aluminium": 71.7e9, "brass": 106.0e9, "steel": 207.0e9}   # shigley Table A-5


def own_limiter(thread: str, outside_mm: float, bore_mm: float, material: str = "steel",
                yield_pa: Optional[float] = None, head_mm: float = 0.0, tolerance_mm: float = 0.05) -> Limiter:
    """A limiter that is not a catalogue part: a sleeve, a bushing or a spacer pressed or slid into the clamped part
    (diameters in mm; ``outside`` is its outside where it meets the plastic). Give its wall's ``yield_pa`` for the
    wall check; without it the wall is reported, not judged."""
    for nm, v in (("outside_mm", outside_mm), ("bore_mm", bore_mm), ("head_mm", head_mm),
                  ("tolerance_mm", tolerance_mm)):
        if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0):
            raise ValueError(f"{nm} must be a finite size of at least 0, not {v!r}")
    if not 0 < bore_mm < outside_mm:
        raise ValueError(f"the bore ({bore_mm!r}) must be above 0 and smaller than the outside ({outside_mm!r})")
    if material not in METAL_MODULUS_PA:
        raise ValueError(f"material must be one of {sorted(METAL_MODULUS_PA)}, not {material!r}")
    if yield_pa is not None and not (isinstance(yield_pa, (int, float)) and not isinstance(yield_pa, bool)
                                     and yield_pa > 0):
        raise ValueError(f"yield_pa must be above 0, not {yield_pa!r}")
    return Limiter("own", thread, material, float(bore_mm), float(outside_mm), float(outside_mm), float(head_mm),
                   (float(outside_mm), float(outside_mm)), float(tolerance_mm), METAL_MODULUS_PA[material], "",
                   "the caller's own part; modulus Shigley Table A-5", yield_pa)


def limiter_for(ins: Insert, material: str = "aluminium") -> Optional[Dict[str, Any]]:
    """The catalogue limiter for an insert's thread (SPIROL CL6000 aluminium by default), at the coupon plate's
    length: {key, length_mm, hole_mm (the CAD hole: the maker's largest)}; None where none is listed."""
    series = {"aluminium": "cl6000", "brass": "cl8000"}[material]
    key = f"spirol-{series}-{ins.thread.lower()}"
    if key not in LIMITERS:
        return None
    return {"key": key, "length_mm": 5.0, "hole_mm": LIMITERS[key].hole_mm[1]}


# ----------------------------------------------------------------------------- the joint check

LIMITS = (
    "the strengths are a shear model calibrated to published pull-out tests of M3 x 5.7 inserts in PLA (and one in "
    "PETG); other sizes scale by the knurl's area, which the moulded makers' tables support, and other families take "
    "the lowest fit: a starting point to test (coupon_plan), not a rating",
    "torque-out comes from pull-out through the ratio r = 2 T / (F D) the published tests give (printed and "
    "moulded); its low end is taken",
    "push-out has no published test, and an insert lying in the layer plane has no published number: both are "
    "flagged, not modelled",
    "static, short-term, room temperature: a held load creeps; PLA inserts kept 26-55 % of their pull-out after a "
    "year of natural ageing (Materials 2025)",
    "the boss is printed solid round the insert (the tests were); infill and perimeters change the capacity by up to "
    "2.5 x (Kastner 2023)",
    "the clamped part's face on a flush insert's end is not checked: it shares the clamp with the boss face",
    "preload relaxation: printed PLA was measured for an hour and printed joints for a week; the long-term figure is "
    "moulded polycarbonate's, and PLA, nearer its glass transition, will keep less",
    "CAD and closed forms do not prove a joint holds: print the coupons and measure",
)


def _band(lo: float, hi: float) -> Dict[str, float]:
    return {"low": lo, "high": hi}


def _graded(value: float, limit: float, ceiling: float) -> str:
    return "pass" if value <= limit else "warn" if value <= ceiling else "fail"


def _clamp_rows(rows: List[Dict[str, Any]], thread: str, d_mm: float, p_mm: float, lim: Optional["Limiter"],
                clamped: Dict[str, Any], cmat: str, preload: Dict[str, float], Fp: float, head: Optional[float],
                clear: Optional[float], head_area: Optional[float], margin: float,
                limiter_length_mm: Optional[float], limiter_hole_mm: Optional[float],
                insert: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The clamped part's rows, for any screw joint: the plastic under the head, the limiter (its length against the
    plastic, the seating force, the head over it, its rating or wall, its press fit and boss, and, into an insert, its
    end on the insert's face) and the preload the joint keeps. Appends to ``rows``; returns the preload kept."""
    d, p = d_mm * MM, p_mm * MM
    # the head on the clamped part
    if lim is None and cmat != "metal":
        if head_area:
            sigma = fx.annulus_stress(preload["high"], head * MM, clear * MM)
            strength = bearing_strength(cmat)
            v = _graded(sigma, strength / margin * (1 + 1e-9), strength)
            rows.append(_row("head bearing", round(sigma / 1e6, 2), round(strength / margin / 1e6, 2), v,
                             f"the preload on the plastic under the head or washer (MPa, {head:g} mm on a {clear:g} mm "
                             f"hole) against its compressive strength / {margin:g} ({BEARING_BASIS[family(cmat)]}); "
                             "a washer spreads it"))
        else:
            rows.append(_row("head bearing", None, None, "warn",
                             f"not checked: no head bearing diameter for {thread}; give head_mm and clearance_mm"))

    # the limiter
    kept = None
    if lim is not None:
        if lim.thread and lim.thread != thread:
            raise ValueError(f"limiter {lim.key} is for {lim.thread}, the screw is {thread}")
        t_nom = clamped.get("thickness_mm")
        if t_nom is None:
            raise ValueError("a limiter needs clamped={'thickness_mm': ...}: the plastic it goes through")
        t_tol = float(clamped.get("tolerance_mm", 0.1))
        L_lim = float(limiter_length_mm if limiter_length_mm is not None else t_nom)
        # length +0/-tol: centre it so the formula's symmetric tolerance spans the maker's band
        stack = fx.limiter_stack((L_lim - lim.tolerance_mm / 2) * MM, t_nom * MM, lim.tolerance_mm / 2 * MM,
                                 t_tol * MM)
        t_max, t_min = t_nom + t_tol, t_nom - t_tol
        squeeze = max(-stack["standout"]["low"] / MM, 0.0) / t_max
        E_c = PRINTED[cmat].secant_upper_bound("across") * 1e6 if cmat != "metal" else None
        yield_strain = PRINTED[cmat].strength("across") / PRINTED[cmat].secant_upper_bound("across") \
            if cmat != "metal" else None
        if stack["standout"]["high"] > 0:
            v = "warn"
            why = ("the limiter can stand proud of the plastic: the part may move about it (SPIROL); use one no "
                   "longer than the plastic's least thickness, or a knurled one made to stand proud (Bulten)")
        else:
            v = ("pass" if squeeze <= LIMITER_COMPRESSION[0] else "warn" if squeeze <= LIMITER_COMPRESSION[1]
                 else "fail")
            why = f"the plastic squeezed at most {squeeze * 100:.1f} % before the head lands (SPIROL: 5 % safe, 7 % " \
                  "safe for most plastics)"
            if yield_strain is not None and squeeze > yield_strain:
                v = "warn" if v == "pass" else v
                why += f"; past {yield_strain * 100:.1f} %, the printed plastic's strength over its modulus: it " \
                       "yields and relaxes"
        rows.append(_row("limiter length", round(L_lim, 3), {"plastic_min_mm": round(t_min, 3),
                                                              "squeeze_max": LIMITER_COMPRESSION[0]}, v, why))
        # the seating force: the plastic's share before the head lands on the limiter. SPIROL's formula 3 takes the
        # plastic under the head as a column; when the head overhangs the limiter by a narrow ring on thick plastic
        # the pressure spreads and the plastic is stiffer than that, so Shigley's cone (two frusta, one from each
        # face) gives the high end, which the verdict uses
        head_c = max(head or 0.0, lim.head_mm) or lim.body_mm
        plastic_load = 0.0
        seat_band = None
        if E_c is not None:
            A_p = math.pi / 4.0 * (max(head_c, lim.knurl_mm) ** 2 - lim.knurl_mm ** 2) * MM ** 2
            seat = 0.0
            if A_p > 0 and squeeze > 0:
                shortfall = squeeze * t_max * MM
                k_col = E_c * A_p / (t_max * MM)                        # SPIROL formula 3, elastic
                k_cone = fx.frustum_stiffness(E_c, t_max / 2.0 * MM, head_c * MM, lim.knurl_mm * MM) / 2.0
                k_p = max(k_col, k_cone)
                seat_band = _band(k_col * shortfall, k_p * shortfall)
                seat = seat_band["high"]
                crush = bearing_strength(cmat) * A_p
                plastic_load = fx.limiter_plastic_load(shortfall, k_p, min(preload["low"], crush))
            ring = seat / A_p if A_p > 0 else 0.0
            if seat < preload["low"] and seat <= SEATING_SHARE * Fp and ring <= bearing_strength(cmat) / margin:
                v, why = "pass", "the head lands on the limiter with preload to spare"
            elif plastic_load < preload["low"] and seat < preload["low"]:
                v, why = "warn", (f"the head lands on the limiter, but the plastic round it then bears {ring / 1e6:.0f} "
                                  f"MPa, over its compressive strength / {margin:g} "
                                  f"({bearing_strength(cmat) / margin / 1e6:.0f} MPa): it creeps or crushes there. "
                                  "Make the limiter as long as the plastic, or relieve the face round it")
            elif plastic_load < preload["low"]:
                v, why = "warn", ("the plastic under the head crushes before the head lands: the limiter then takes "
                                  "the clamp, but the plastic is damaged")
            else:
                v, why = "fail", ("the plastic takes the whole preload and the head never reaches the limiter: it "
                                  "does nothing. Make the limiter as long as the plastic (measure the printed part), "
                                  "or use a knurled one made to stand proud (Bulten)")
            band = (f" ({seat_band['low']:.0f} as SPIROL's column, {seat_band['high']:.0f} as Shigley's cone)"
                    if seat_band and seat_band["high"] > seat_band["low"] * 1.01 else "")
            rows.append(_row("seating force", round(seat, 1), round(min(SEATING_SHARE * Fp, preload["low"]), 1), v,
                             "the force that squeezes the plastic until the head reaches the limiter, N" + band +
                             " (SPIROL formula 3: at most 75 % of the proof load, and below the preload): " + why))
        # the head over the limiter and onto the plastic
        reach = head_c > lim.knurl_mm
        rows.append(_row("head over limiter", round(head_c, 3), round(lim.knurl_mm, 3), "pass" if reach else "warn",
                         "the head, washer or the limiter's own flange reaches past it onto the plastic (SPIROL)"
                         if reach else "the head or washer covers only the limiter: the plastic round it is loose; "
                                       "add a washer or use a headed limiter"))
        # the limiter on the insert's face (it must abut it)
        if insert is None:
            pass
        elif not (lim.bore_mm < insert["knurl"] and insert["path"] != "jack-out"):
            rows.append(_row("limiter on insert", round(lim.bore_mm, 3), round(insert["knurl"], 3), "fail",
                             "the limiter must abut the insert, its bore smaller than the insert's face, or the screw "
                             "jacks the insert out (SPIROL 2022)"))
        elif insert.get("face") is not None:
            face = insert["face"]
            sigma = preload["high"] / (face["area_mm2"] * MM ** 2)
            v = _graded(sigma, BRASS_YIELD_PA[0], BRASS_YIELD_PA[1])
            rows.append(_row("insert face", round(sigma / 1e6, 1), round(BRASS_YIELD_PA[0] / 1e6, 1), v,
                             f"the preload on the ring of the insert's end under the limiter ({face['area_mm2']:.2f} "
                             "mm^2) against brass's yield (124-310 MPa by temper): over it the face embeds and the "
                             "preload falls"))
        # the wall: the maker rates the series for a screw class; a limiter of your own, by its yield
        sigma_w = fx.annulus_stress(preload["high"], lim.body_mm * MM, lim.bore_mm * MM)
        if lim.rated_class:
            rated = fx.proof_load(d, p, PROOF_STRENGTH_PA[lim.rated_class])
            v = _graded(preload["high"], SEATING_SHARE * rated, rated)
            rows.append(_row("limiter rating", round(preload["high"], 1), round(SEATING_SHARE * rated, 1), v,
                             f"the maker rates this series for class {lim.rated_class} (its clamp load, 75 % of "
                             f"proof); the wall carries {sigma_w / 1e6:.0f} MPa at the high preload"))
        elif lim.yield_pa:
            v = _graded(sigma_w, lim.yield_pa / margin, lim.yield_pa)
            rows.append(_row("limiter wall", round(sigma_w / 1e6, 1), round(lim.yield_pa / margin / 1e6, 1), v,
                             f"the preload on the limiter's wall (MPa) against its yield / {margin:g}"))
        else:
            rows.append(_row("limiter wall", round(sigma_w / 1e6, 1), None, "warn",
                             "no rating and no yield given for this limiter: give yield_pa"))
        # the press fit in the printed hole: the hoop stress it raises
        if E_c is not None:
            cad_lim_hole = float(limiter_hole_mm if limiter_hole_mm is not None else lim.hole_mm[1])
            interference = max(lim.knurl_mm - cad_lim_hole, 0.0)
            outside = clamped.get("outside_mm")
            hub = float(outside) if outside else 10.0 * lim.knurl_mm
            if interference > 0 and hub > lim.knurl_mm:
                pr = fx.press_fit_pressure(interference * MM, lim.knurl_mm * MM, hub * MM,
                                           PRINTED[cmat].retention_modulus("along") * 1e6, POISSON_PLASTICS,
                                           lim.modulus_pa, POISSON_METAL[lim.material], lim.bore_mm * MM)
                hoop = fx.boss_hoop_stress(pr, lim.knurl_mm * MM, hub * MM)
                strength = PRINTED[cmat].strength("along") * 1e6
                v = _graded(hoop, strength / margin, strength)
                rows.append(_row("limiter press fit", round(hoop / 1e6, 2), round(strength / margin / 1e6, 2), v,
                                 f"the hoop stress (MPa) the knurl's {interference:.2f} mm interference raises in the "
                                 "printed hole, smooth-fit Lame, against the plastic's strength along the layers / "
                                 f"{margin:g}; the knurl cuts in rather than stretching the hole, so this is high"))
            if outside:
                bwall = (float(outside) - lim.knurl_mm) / 2.0
                v = "fail" if bwall < 0.5 * d_mm else "warn" if float(outside) < 2 * lim.knurl_mm else "pass"
                rows.append(_row("limiter boss", round(bwall, 3), round(0.5 * d_mm, 3), v,
                                 "plastic round the limiter: at least half the screw's diameter (Bulten), the boss "
                                 "about 2 x the limiter (SPIROL)"))
    # preload kept
    if cmat == "metal" and lim is None:
        kept = {"basis": "metal clamped part: no plastic in the clamp path", "low": 1.0, "high": 1.0}
    elif cmat != "metal":
        rel = RELAXATION.get(family(cmat), {})
        lo_lt, hi_lt = LONG_TERM_REFERENCE
        if lim is None:
            kept = {"basis": "plastic in the clamp path: it relaxes", "low": lo_lt, "high": hi_lt,
                    "hours": rel.get("hours"), "joint_7d": rel.get("joint_7d")}
            rows.append(_row("preload kept", f"{lo_lt:.2f}-{hi_lt:.2f}", "a limiter", "warn",
                             "the clamped plastic relaxes and takes the preload with it: "
                             + (f"printed PLA kept {rel['hours'][0]:.2f}-{rel['hours'][1]:.2f} of a held stress "
                                f"after 1 h (Liber-Knec 2025); " if rel.get("hours") else "")
                             + (f"a printed joint kept {rel['joint_7d']:.3f} of its untightening torque after 7 days "
                                f"(Amza 2021); " if rel.get("joint_7d") else "")
                             + f"moulded polycarbonate keeps {lo_lt:.2f}-{hi_lt:.2f} over 1-6 years (Covestro); no "
                               "long-term printed figure was found. A compression limiter keeps the clamp in metal"))
        else:
            share = plastic_load / preload["low"] if preload["low"] > 0 else 0.0
            k_lo_kept = fx.preload_retained_limited(plastic_load, preload["low"], lo_lt)
            kept = {"basis": "limiter: only the plastic's share relaxes", "low": k_lo_kept, "high": 1.0,
                    "plastic_share": share}
            v = "pass" if k_lo_kept >= 0.9 else "warn"
            rows.append(_row("preload kept", round(k_lo_kept, 3), 0.9, v,
                             f"the plastic carries {share * 100:.1f} % of the preload; if it relaxes to "
                             f"{lo_lt:.2f} (moulded PC over years, Covestro: no printed figure) the joint keeps "
                             f"{k_lo_kept:.3f}"))

    return kept


def check_joint(insert: str, material: str, axis: str = "upright", boss_outside_mm: Optional[float] = None,
                edge_mm: Optional[float] = None, hole_mm: Optional[float] = None,
                hole_depth_mm: Optional[float] = None, through: bool = False, recess_mm: float = 0.0,
                installed_from: str = "joint face", screw_class: str = "12.9", torque_nm: Optional[float] = None,
                pull_n: float = 0.0, push_n: float = 0.0, turn_nm: float = 0.0,
                head_mm: Optional[float] = None, clearance_mm: Optional[float] = None,
                clamped: Optional[Dict[str, Any]] = None, limiter_key: Optional[str] = None,
                limiter_length_mm: Optional[float] = None, limiter_hole_mm: Optional[float] = None,
                screw_depth_mm: Optional[float] = None, margin: float = MARGIN,
                name: Optional[str] = None) -> Dict[str, Any]:
    """Check one screw joint into a heat-set insert in a printed part, with or without a compression limiter in the
    clamped part. Returns verdict (pass / warn / fail: the worst row), each check's value, limit, verdict and why,
    the insert's capacities, the most to tighten to and the limits. Lengths in mm, forces in N, torques in N m.

    ``recess_mm`` is how far the insert's end sits below the joint face (negative: proud); with ``installed_from``
    'far side' it is the shoulder of boss in front of it. ``clamped`` describes the part the screw clamps:
    {material (a PRINTED key or 'metal'), thickness_mm, tolerance_mm (+/-), outside_mm (round the hole)}.
    ``screw_depth_mm`` is how far the screw's tip reaches below the joint face."""
    ins = INSERTS.get(insert) if isinstance(insert, str) else None
    if ins is None:
        raise ValueError(f"insert must be one of {sorted(INSERTS)}, not {insert!r}")
    fam = family(material)
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
    if screw_class not in PROOF_STRENGTH_PA:
        raise ValueError(f"screw_class must be one of {sorted(PROOF_STRENGTH_PA)}, not {screw_class!r}")
    for nm, v in (("pull_n", pull_n), ("push_n", push_n), ("turn_nm", turn_nm), ("recess_mm", recess_mm)):
        if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)):
            raise ValueError(f"{nm} must be a finite number, not {v!r}")
    if min(pull_n, push_n, turn_nm) < 0:
        raise ValueError("pull_n, push_n and turn_nm are sizes: give them at least 0")
    if not (isinstance(margin, (int, float)) and margin >= 1.0):
        raise ValueError(f"margin must be at least 1, not {margin!r}")
    clamped = dict(clamped or {})
    cmat = clamped.get("material", material)
    if cmat != "metal":
        family(cmat)
    rows: List[Dict[str, Any]] = []
    hd = hole_design(ins, axis, through)
    bd = boss_design(ins)
    cap = capacity(ins, material, axis)
    d, p = ins.diameter_mm * MM, ins.pitch_mm * MM

    # the hole
    cad_hole = hd["diameter_mm"] if hole_mm is None else float(hole_mm)
    knurl, _ = _knurl(ins)
    lo, hi = ins.hole_mm - 0.1, ins.hole_mm + CAD_ALLOWANCE_MM[1]
    v = ("pass" if lo <= cad_hole <= hi else "fail" if cad_hole >= knurl else "warn")
    rows.append(_row("hole diameter", round(cad_hole, 3), [round(lo, 3), round(hi, 3)], v,
                     "in CAD; the maker's hole plus 0.2-0.3 mm prints to size (CNC Kitchen 2026)" if v == "pass" else
                     ("no smaller than the knurl's crests will grip" if v == "fail" else
                      ("smaller than the maker's: more plastic to push aside, and the insert may not seat" if
                       cad_hole < lo else "larger: the knurl bites less; drilled true to size, CNC Kitchen's M3 lost "
                                          "most of its strength between 4.1 and 4.2 mm"))))
    if not through:
        depth = hd["depth_mm"] if hole_depth_mm is None else float(hole_depth_mm)
        need = hd["depth_mm"]
        v = "pass" if depth >= need - 1e-9 else "warn" if depth > ins.length_mm else "fail"
        rows.append(_row("hole depth", round(depth, 3), round(need, 3), v,
                         "deep enough for the melt below the insert (the makers' rules)" if v == "pass" else
                         "short of the makers' depth: the melt has less room (see the melt volume) and the insert "
                         "may sit proud" if v == "warn" else
                         f"no deeper than the insert ({ins.length_mm:g} mm): it cannot seat flush"))
        if ins.volume_mm3 and ins.cad_bore_mm:
            displaced = fx.insert_displaced_volume(ins.volume_mm3 * MM ** 3, ins.hole_mm * MM,
                                                   ins.cad_bore_mm * MM, ins.length_mm * MM) / MM ** 3
            pocket = fx.overflow_volume(ins.hole_mm * MM, depth * MM, ins.length_mm * MM) / MM ** 3
            v = "pass" if displaced <= pocket else "warn"
            rows.append(_row("melt volume", round(displaced, 2), round(pocket, 2), v,
                             "the plastic the insert pushes aside (mm^3) fits the pocket below it" if v == "pass" else
                             "more melt than the pocket holds: it wells up round the insert; deepen the hole"))
    # the screw's tip: past the hole's floor it bottoms and pulls the insert out instead of clamping; past the
    # insert's end it reaches the room the makers leave for the melt, which may have filled it
    engaged = None
    if screw_depth_mm is not None:
        tip = float(screw_depth_mm)
        if not (math.isfinite(tip) and tip > 0):
            raise ValueError(f"screw_depth_mm must be a depth above 0, not {screw_depth_mm!r}")
        end = max(recess_mm, 0.0) + ins.length_mm
        engaged = max(min(tip, end) - max(recess_mm, 0.0), 0.0)
        if through:
            v, why = "pass", "a through hole: the tip cannot bottom"
        else:
            floor = hd["depth_mm"] if hole_depth_mm is None else float(hole_depth_mm)
            clear = floor - tip
            v = "fail" if clear <= 0 else "warn" if tip > end else "pass"
            why = (f"{clear:.2f} mm above the hole's floor" if v == "pass" else
                   f"past the insert's end by {tip - end:.2f} mm, into the room left for the melt below it, which "
                   "may have filled it: the screw can bottom on it and jack the insert out (SPIROL)" if v == "warn"
                   else f"{-clear:.2f} mm past the hole's floor: the screw bottoms and jacks the insert out instead of "
                        "clamping (SPIROL). Use a shorter screw or deepen the hole")
        rows.append(_row("screw tip", round(tip, 3), round(end if through else floor, 3), v,
                         why + f"; {engaged:.2f} of the insert's {ins.length_mm:g} mm of thread engaged"))
    # the boss
    walls = []
    if boss_outside_mm is not None:
        walls.append((float(boss_outside_mm) - cad_hole) / 2.0)
    if edge_mm is not None:
        walls.append(float(edge_mm))
    if walls:
        wall = min(walls)
        outside = cad_hole + 2.0 * wall
        v = ("fail" if wall < bd["least_wall_mm"] or outside < BOSS_FLOOR * knurl else
             "warn" if outside < BOSS_FULL * knurl else "pass")
        rows.append(_row("boss wall", round(wall, 3), {"least_wall_mm": bd["least_wall_mm"],
                                                        "least_outside_mm": bd["least_outside_mm"],
                                                        "full_outside_mm": bd["outside_mm"]}, v,
                         {"pass": "the full-performance boss (2 x the knurl)",
                          "warn": "above the makers' least wall but under 2 x the knurl: weaker than the tests",
                          "fail": "under the makers' least wall (or 1.5 x the knurl): the boss can split"}[v]))
    else:
        rows.append(_row("boss wall", None, bd["least_wall_mm"], "warn",
                         "not given: say boss_outside_mm (or edge_mm, the least plastic to a free face)"))
    if axis == "lying":
        rows.append(_row("insert axis", axis, "upright", "warn",
                         "lying in the layer plane: no published number; Kastner 2023 found inserts along Z stronger "
                         "and more predictable. The coupon plan measures it"))
    if fam not in calibration()["pull"]:
        rows.append(_row("calibration", fam, sorted(k for k in calibration()["pull"] if k != "pooled"), "warn",
                         "no published printed test in this family: the lowest c of any family is taken"))

    # the clamp path and the torque
    path = fx.insert_clamp_path(recess_mm * MM, PROUD_OK_MM * MM, installed_from)
    hole_c = clearance_mm or CLEARANCE_MM.get(ins.thread)
    if path["path"] == "through-insert" and hole_c and hole_c >= knurl and limiter_key is None:
        path = {"path": "jack-out", "knurl_preload": 1.0,
                "why": f"the clamped part's hole ({hole_c:g} mm) is as wide as the insert ({knurl:g} mm): the part "
                       "bears on the plastic round the insert, and the screw pulls the insert out (SPIROL)",
                "instead": "make the clamped part's hole smaller than the insert's face, so it bears on the brass"}
    lim = limiter(limiter_key) if limiter_key else None
    collar = COLLAR_ON_METAL if (lim is not None or cmat == "metal") else COLLAR_ON_PLASTIC
    Fp = fx.proof_load(d, p, PROOF_STRENGTH_PA[screw_class])
    pull_lo, torque_lo = cap["pull_out"]["low"], cap["torque_out"]["low"]
    lt = fx.insert_limited_torque(d, p, path["path"], pull_lo, torque_lo, Fp, THREAD_FRICTION, collar, margin)
    allowed, governed = lt["torque"], lt["governed_by"]
    k_lo, k_hi = lt["nut_factor"]["low"], lt["nut_factor"]["high"]
    # what else caps the preload, each as the most preload it passes: the plastic under the head, the shoulder in
    # front of a far-side insert, the insert's end under a limiter. Each becomes a torque ceiling at the least
    # friction (the most preload a torque gives).
    caps: Dict[str, float] = {}
    head = head_mm or HEAD_BEARING_MM.get(ins.thread)
    clear = clearance_mm or CLEARANCE_MM.get(ins.thread)
    head_area = (math.pi / 4.0 * (head ** 2 - clear ** 2) * MM ** 2) if head and clear and head > clear else None
    if lim is None and cmat != "metal" and head_area:
        caps["head_bearing"] = bearing_strength(cmat) / margin * head_area
    shoulder = None
    if path["path"] == "seat":
        shoulder = fx.insert_shear_force(knurl * MM, recess_mm * MM, cap["shear_strength_pa"], 1.0)
        caps["shoulder"] = shoulder / margin
    # the insert's own thread: the length the screw engages (all of it unless screw_depth_mm says otherwise)
    engaged_len = ins.length_mm if engaged is None else engaged
    strip = (fx.thread_strip_force(d, p, engaged_len * MM, SHEAR_OVER_YIELD * BRASS_YIELD_PA[0], "internal")
             if engaged_len > 0 else 0.0)
    if strip / margin > pull_n:
        caps["insert_thread"] = strip / margin - pull_n
    face = None
    if lim is not None:
        face_od = min(lim.body_mm, knurl)
        area = math.pi / 4.0 * (face_od ** 2 - lim.bore_mm ** 2) * MM ** 2
        if area > 0:
            face = {"area_mm2": area / MM ** 2, "load_pass": BRASS_YIELD_PA[0] * area}
            caps["insert_face"] = face["load_pass"]
    ceilings = dict(lt["ceilings"])
    for cap_name, F_max in caps.items():
        ceilings[cap_name] = k_lo * d * F_max
        if ceilings[cap_name] < allowed:
            allowed, governed = ceilings[cap_name], cap_name
    v_path = {"seat": "pass", "through-insert": "pass" if recess_mm >= -PROUD_OK_MM else "warn",
              "jack-out": "warn"}[path["path"]]
    rows.append(_row("clamp path", path["path"], "seat or through-insert", v_path,
                     path["why"] + ("" if v_path == "pass" else "; instead: " + path["instead"])))
    T = allowed if torque_nm is None else float(torque_nm)
    if T <= 0:
        raise ValueError(f"torque_nm must be above 0, not {torque_nm!r}")
    preload = _band(T / (k_hi * d), T / (k_lo * d))
    v = _graded(T, allowed * (1 + 1e-9), allowed * margin)
    rows.append(_row("tightening torque", round(T, 4), round(allowed, 4), v,
                     f"the most is {allowed:.3g} N m, set by {governed.replace('_', ' ')}" +
                     ("" if v == "pass" else f"; over it by {T / allowed:.2f} x" +
                      (" (inside the margin)" if v == "warn" else ""))))
    # the insert's own thread, over the length the screw engages
    F_t = preload["high"] + pull_n
    if engaged_len <= 0:
        rows.append(_row("insert thread", 0.0, round(ins.length_mm, 3), "fail",
                         "the screw does not reach the insert's thread"))
    else:
        v = _graded(F_t, strip / margin, strip)
        rows.append(_row("insert thread", round(F_t, 1), round(strip / margin, 1), v,
                         f"the preload and the separating load on the {engaged_len:.2f} mm of the insert's thread the "
                         "screw engages" + (" (all of it: give screw_depth_mm)" if engaged is None else "") +
                         f", against the force that strips it ({strip:.0f} N: the ISO 68 internal shear area at "
                         f"brass's shear yield, {SHEAR_OVER_YIELD} x 124 MPa, the softest temper) / {margin:g}"))
    # service loads on the knurl
    knurl_pull = pull_n + (preload["high"] if path["path"] == "jack-out" else 0.0)
    if path["path"] != "seat" and knurl_pull > 0:
        v = _graded(knurl_pull, pull_lo / margin, pull_lo)
        rows.append(_row("pull-out", round(knurl_pull, 1), round(pull_lo / margin, 1), v,
                         ("the separating load" + (" plus the preload (jack-out)" if path["path"] == "jack-out"
                                                   else "") +
                          f" against the low pull-out {pull_lo:.0f} N / {margin:g}")))
    if shoulder is not None:
        F_sh = preload["high"] + pull_n
        v = _graded(F_sh, shoulder / margin, shoulder)
        hole_sh = clear or ins.diameter_mm
        if hole_sh >= knurl:
            v = "fail"
        rows.append(_row("shoulder", round(F_sh, 1), round(shoulder / margin, 1), v,
                         f"the preload and the separating load push the insert against {recess_mm:g} mm of boss in "
                         f"front of it: the plug it would punch out (shear on the knurl's cylinder, uncalibrated, "
                         f"c = 1) over {margin:g}" +
                         ("; the hole in the shoulder must be smaller than the insert" if hole_sh >= knurl else "")))
    if push_n > 0:
        v = _graded(push_n, cap["push_out"]["low"] / margin, cap["push_out"]["low"])
        rows.append(_row("push-out", round(push_n, 1), round(cap["push_out"]["low"] / margin, 1),
                         v,
                         "against the pull-out model taken as push-out (no published push-out test)" +
                         ("" if through else "; a blind hole's floor also carries it")))
    if turn_nm > 0:
        v = _graded(turn_nm, torque_lo / margin, torque_lo)
        rows.append(_row("torque-out", round(turn_nm, 4), round(torque_lo / margin, 4), v,
                         f"a turning load on the insert against its low torque-out {torque_lo:.3g} N m / {margin:g}"))

    kept = _clamp_rows(rows, ins.thread, ins.diameter_mm, ins.pitch_mm, lim, clamped, cmat, preload, Fp, head, clear,
                       head_area, margin, limiter_length_mm, limiter_hole_mm,
                       insert={"knurl": knurl, "path": path["path"], "face": face})

    return {"verdict": _worst(rows), "name": name or f"{ins.thread} {ins.part} in {material}",
            "insert": ins.as_dict(), "material": {"key": material, "name": PRINTED[material].name, "family": fam,
                                                  "shear_strength_pa": cap["shear_strength_pa"], "status": STATUS},
            "axis": axis, "clamp": path, "screw_class": screw_class, "proof_load_n": Fp,
            "torque": {"allowed_nm": allowed, "governed_by": governed, "used_nm": T,
                       "ceilings": ceilings, "preload_caps_n": caps,
                       "preload_n": preload, "thread_share": lt["thread_share"], "nut_factor": lt["nut_factor"],
                       "friction": {"thread": list(THREAD_FRICTION), "collar": list(collar)}},
            "capacity": cap, "hole": hd, "boss": bd, "limiter": asdict(lim) if lim else None, "preload_kept": kept,
            "install": install_notes(material), "checks": rows, "margin": margin, "limits": list(LIMITS)}


# steel in steel or aluminium: VDI 2230's friction classes B and C cover the thread and the head alike
THREAD_FRICTION_METAL = COLLAR_ON_METAL


def _metric(thread: str) -> Tuple[float, float]:
    """(diameter, pitch) in mm of an ISO metric coarse thread named like 'M5'."""
    text = str(thread).upper()
    try:
        dia = float(text[1:]) if text.startswith("M") else None
    except ValueError:
        dia = None
    if dia not in COARSE_PITCH_MM:
        raise ValueError(f"thread must be an ISO metric coarse size such as 'M5', not {thread!r}")
    return dia, COARSE_PITCH_MM[dia]


def check_clamp(thread: str, material: str, thickness_mm: float, tolerance_mm: float = 0.1,
                outside_mm: Optional[float] = None, screw_class: str = "12.9", torque_nm: Optional[float] = None,
                head_mm: Optional[float] = None, clearance_mm: Optional[float] = None,
                limiter_key: Optional[str] = None, limiter: Optional[Dict[str, Any]] = None,
                limiter_length_mm: Optional[float] = None, limiter_hole_mm: Optional[float] = None,
                margin: float = MARGIN, name: Optional[str] = None) -> Dict[str, Any]:
    """Check printed plastic clamped by a screw that does not thread into it: into tapped metal, a nut, or a metal
    part's own thread. The rows: the most to tighten to (the screw's proof load and, with no limiter, the plastic under
    the head), the head's bearing on the plastic, a limiter's length against the plastic, its seating force, the head
    over it, its rating or wall, its press fit and boss, and the preload the joint keeps.

    ``thickness_mm`` +/- ``tolerance_mm`` is the plastic in the clamp; ``outside_mm`` the plastic round a limiter.
    A limiter is a catalogue key (``limiter_key``) or your own part (``limiter``: own_limiter's arguments, without
    the thread). A limiter that sits below the plastic's face is one shorter than the plastic: give its
    ``limiter_length_mm``. Lengths in mm, torques in N m."""
    d_mm, p_mm = _metric(thread)
    family(material)
    if screw_class not in PROOF_STRENGTH_PA:
        raise ValueError(f"screw_class must be one of {sorted(PROOF_STRENGTH_PA)}, not {screw_class!r}")
    if not (isinstance(margin, (int, float)) and margin >= 1.0):
        raise ValueError(f"margin must be at least 1, not {margin!r}")
    for nm, v in (("thickness_mm", thickness_mm), ("tolerance_mm", tolerance_mm)):
        if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0):
            raise ValueError(f"{nm} must be a finite size of at least 0, not {v!r}")
    if thickness_mm <= tolerance_mm:
        raise ValueError(f"thickness_mm ({thickness_mm!r}) must be more than its tolerance ({tolerance_mm!r})")
    if limiter_key and limiter:
        raise ValueError("give limiter_key (a catalogue limiter) or limiter (your own), not both")
    tag = str(thread).upper()
    if limiter_key:
        lim = globals()["limiter"](limiter_key)
    elif limiter:
        if not isinstance(limiter, dict):
            raise ValueError(f"limiter must be a mapping of own_limiter's arguments, not {limiter!r}")
        lim = own_limiter(tag, **limiter)
    else:
        lim = None
    d, p = d_mm * MM, p_mm * MM
    collar = COLLAR_ON_METAL if lim is not None else COLLAR_ON_PLASTIC
    k_lo = fx.nut_factor(d, p, THREAD_FRICTION_METAL[0], collar[0])
    k_hi = fx.nut_factor(d, p, THREAD_FRICTION_METAL[1], collar[1])
    Fp = fx.proof_load(d, p, PROOF_STRENGTH_PA[screw_class])
    ceilings = {"screw": k_lo * d * Fp}
    caps: Dict[str, float] = {}
    head = head_mm or HEAD_BEARING_MM.get(tag)
    clear = clearance_mm or CLEARANCE_MM.get(tag)
    head_area = (math.pi / 4.0 * (head ** 2 - clear ** 2) * MM ** 2) if head and clear and head > clear else None
    if lim is None and head_area:
        caps["head_bearing"] = bearing_strength(material) / margin * head_area
        ceilings["head_bearing"] = k_lo * d * caps["head_bearing"]
    governed = min(ceilings, key=ceilings.get)
    allowed = ceilings[governed]
    T = allowed if torque_nm is None else torque_nm
    if not (isinstance(T, (int, float)) and not isinstance(T, bool) and math.isfinite(T) and T > 0):
        raise ValueError(f"torque_nm must be above 0, not {torque_nm!r}")
    T = float(T)
    preload = _band(T / (k_hi * d), T / (k_lo * d))
    rows: List[Dict[str, Any]] = []
    v = _graded(T, allowed * (1 + 1e-9), allowed * margin)
    rows.append(_row("tightening torque", round(T, 4), round(allowed, 4), v,
                     f"the most is {allowed:.3g} N m, set by {governed.replace('_', ' ')}" +
                     ("" if v == "pass" else f"; over it by {T / allowed:.2f} x" +
                      (" (inside the margin)" if v == "warn" else ""))))
    clamped = {"material": material, "thickness_mm": thickness_mm, "tolerance_mm": tolerance_mm,
               "outside_mm": outside_mm}
    kept = _clamp_rows(rows, tag, d_mm, p_mm, lim, clamped, material, preload, Fp, head, clear, head_area, margin,
                       limiter_length_mm, limiter_hole_mm)
    return {"verdict": _worst(rows), "name": name or f"{tag} clamping {thickness_mm:g} mm of {material}",
            "thread": tag, "material": {"key": material, "name": PRINTED[material].name, "family": family(material),
                                         "status": STATUS},
            "screw_class": screw_class, "proof_load_n": Fp,
            "torque": {"allowed_nm": allowed, "governed_by": governed, "used_nm": T, "ceilings": ceilings,
                       "preload_caps_n": caps, "preload_n": preload,
                       "nut_factor": {"low": k_lo, "high": k_hi},
                       "friction": {"thread": list(THREAD_FRICTION_METAL), "collar": list(collar)}},
            "limiter": asdict(lim) if lim else None, "preload_kept": kept, "checks": rows, "margin": margin,
            "limits": LIMITS}


CLAMP_KEYS = {"name", "thread", "material", "thickness_mm", "tolerance_mm", "outside_mm", "screw_class", "torque_nm",
              "head_mm", "clearance_mm", "limiter_key", "limiter", "limiter_length_mm", "limiter_hole_mm", "margin"}
SPEC_KEYS = {"name", "insert", "material", "axis", "boss_outside_mm", "edge_mm", "hole_mm", "hole_depth_mm",
             "through", "recess_mm", "installed_from", "screw_class", "torque_nm", "pull_n", "push_n", "turn_nm",
             "head_mm", "clearance_mm", "clamped", "limiter_key", "limiter_length_mm", "limiter_hole_mm",
             "screw_depth_mm", "margin"}


def check_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Every joint of a spec ({'joints': [...]}, plus defaults for all of them under 'defaults'): {verdict (the
    worst), joints: [each result]}. A joint with an ``insert`` is check_joint's arguments; one with a ``thread`` and
    no insert (a screw into metal or a nut, clamping printed plastic) is check_clamp's. A default goes only to the
    joints whose check takes it."""
    if not isinstance(spec, dict) or not isinstance(spec.get("joints"), list) or not spec["joints"]:
        raise ValueError("a spec is {'joints': [{insert, material, ...}, ...]} with at least one joint")
    defaults = dict(spec.get("defaults") or {})
    unknown = set(defaults) - SPEC_KEYS - CLAMP_KEYS
    if unknown:
        raise ValueError(f"defaults: unknown keys {sorted(unknown)}")
    out = []
    for i, j in enumerate(spec["joints"]):
        if not isinstance(j, dict):
            raise ValueError(f"joint {i} must be a mapping, not {j!r}")
        if ("insert" in j) == ("thread" in j):
            raise ValueError(f"joint {i}: give an insert (a screw into a heat-set insert) or a thread (a screw "
                             "into metal or a nut), not both or neither")
        keys, check = (SPEC_KEYS, check_joint) if "insert" in j else (CLAMP_KEYS, check_clamp)
        unknown = set(j) - keys
        if unknown:
            raise ValueError(f"joint {i}: unknown keys {sorted(unknown)} (known: {sorted(keys)})")
        args = {**{k: v for k, v in defaults.items() if k in keys}, **j}
        out.append(check(**args))
    return {"verdict": _worst([{"verdict": r["verdict"]} for r in out]), "joints": out}


# ----------------------------------------------------------------------------- the coupon test plan

PLAN_COUNT = 5                       # specimens per cell: enough for a mean and a spread, few enough to print
RECORD = ("filament (maker, product, colour, lot) and whether it was dried", "printer, nozzle, layer height, "
          "perimeters, infill and the slicer profile", "the hole as printed (pin gauge or caliper, top and bottom)",
          "the iron and its tip temperature, the time to seat, and the insert's height against the face afterwards "
          "(depth gauge: flush, proud or recessed, to 0.05 mm)", "the room temperature and humidity on test day",
          "the failure mode: insert pulled out with a plug, boss split along a layer, insert turned, thread stripped, "
          "screw broke")
MEASURE = {
    "pull": "the peak force pulling the insert straight out (N) and the force-displacement curve: a screw through a "
            "steel pull plate into the insert, the coupon held down by a reaction plate whose hole clears the boss "
            "by at least one insert diameter, pulled at 2 mm/min",
    "torque": "the peak torque that turns the insert in the boss (N m): the coupon's flats in a vise, a screw "
              "jammed in the insert against a nut, turned with a torque wrench or a torque sensor, slowly, until it "
              "turns",
    "clamp": "the preload over time (N): the screw through a load washer (or a calibrated bolt-load sensor), the "
             "clamp plate (with and without a limiter) on the insert coupon, tightened to the check's torque; read "
             "at 0, 1 h, 24 h and 168 h at room temperature, then 24 h at 50 degC",
}


def coupon_plan(keys: Optional[Tuple[str, ...]] = None, material: str = "pla-bambu-basic") -> Dict[str, Any]:
    """What to print and measure to calibrate the model for real: for each insert, a coupon printed upright and one
    lying, pulled out and turned out, and a clamped-joint coupon with and without a compression limiter. Each cell
    gives the model's predicted band, so a result inside it confirms the calibration and one outside it refits c.
    Nothing is bought or tested by this function: it is the plan."""
    keys = tuple(keys) if keys is not None else tuple(INSERTS)
    cells = []
    for key in keys:
        ins = insert(key)
        for axis in AXES:
            cap = capacity(ins, material, axis)
            for test, band in (("pull", cap["pull_out"]), ("torque", cap["torque_out"])):
                cells.append({"id": f"{ins.thread}x{ins.length_mm:g}-{axis}-{test}", "insert": key, "axis": axis,
                              "test": test, "count": PLAN_COUNT, "measure": MEASURE[test],
                              "predicted": band, "unit": "N" if test == "pull" else "N m"})
            lim = limiter_for(ins)
            for limited in (False, True) if lim else (False,):
                j = check_joint(key, material, axis, boss_outside_mm=coupon_side(ins),
                                clamped={"material": material, "thickness_mm": CLAMP_PLATE_MM,
                                         "tolerance_mm": CLAMP_PLATE_TOL_MM},
                                limiter_key=lim["key"] if limited else None,
                                limiter_length_mm=lim["length_mm"] if limited else None,
                                head_mm=None if limited else HEAD_BEARING_MM.get(ins.thread, 2.0 * ins.diameter_mm),
                                clearance_mm=CLEARANCE_MM.get(ins.thread))
                cells.append({"id": f"{ins.thread}x{ins.length_mm:g}-{axis}-clamp-{'limiter' if limited else 'plastic'}",
                              "insert": key, "axis": axis, "test": "clamp", "limiter": lim["key"] if limited else None,
                              "count": PLAN_COUNT, "measure": MEASURE["clamp"],
                              "predicted": {"preload_kept": j["preload_kept"], "torque_nm": j["torque"]["allowed_nm"],
                                            "preload_n": j["torque"]["preload_n"]},
                              "unit": "share of the preload kept, at the check's torque"})
    return {"material": material, "cells": cells, "record": list(RECORD),
            "coupons": "coupon_block(insert, axis) and clamp_plate(...) make the CAD; tools/insert_coupons.py exports "
                       "every coupon as STEP and STL"}
