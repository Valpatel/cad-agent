"""Minimum features by process: walls, holes, pins, gaps, bridges and overhangs, flanges and hole-to-bend distances,
checked against every cited source in the process profile (#99).

    from cadagent.manufacturing import dfm
    r = dfm.check("fdm", [dfm.Feature("lid wall", "wall", 1.0),
                          dfm.Feature("latch arm", "wall", 1.6, stress_dir=(0, 0, 1), flexes=True),
                          dfm.Feature("vent roof", "bridge", 8.0)],
                  material="petg-bambu-basic", nozzle_mm=0.4)
    r["verdict"], [(f["name"], f["verdict"]) for f in r["features"]]
    dfm.check("sheet-metal", [dfm.Feature("side flange", "flange", 6.0)], material="5052", thickness_mm=1.6)

**How a feature is judged.** Sources disagree (an FDM wall: Prusa 0.45 mm for one 0.4 mm extrusion, Protolabs Network
0.8 mm, Xometry 1.2-1.5 mm on industrial machines), so a feature is held against every verified source that limits it
and the spread is reported:

* each rule gives a lower limit (a wall, a hole, a flange) or an upper one (a bridge, an overhang). A rule with a range
  (``0.75-1.0 mm``, supported to unsupported) passes above its strict end, warns inside it and fails beyond its lenient
  end; a rule with ``window`` must hold both ends;
* the feature **passes** when every verified rule passes; it **fails** when it is beyond the lenient end of every
  verified rule (no source would accept it); and it **warns** in between (some sources accept it, or it is inside a
  source's range), naming the rules it does not fully meet;
* a ``gap`` is checked as a minimum only: a fit's band (a sliding fit's 0.2-0.3 mm) is held at its lower end, because
  the fit types differ (snap, hinge, sliding, assembled after printing) and a gap looser than one source's band is not
  a manufacturing limit. Whether a fit is too loose is for the fit coupons (``fit_coupons``) to find;
* rules marked ``u`` (not verified in their source) are listed as advisory, with ``(u)``, and never decide;
* a rule whose expression needs a number the call did not give (``T``, ``R``, ``nozzle``) is listed under ``skipped``;
* sheet metal: with a shop's tooling row for the material and thickness (``shop_tables``, read first, as the profile
  asks), that row decides the minimum flange, the relief depth and the inside radius (its tooling), and the generic
  rules are shown beside it.

**Orientation (FDM).** With ``stress_dir`` (the direction of the feature's bending or pulling stress, in the part's
frame) and ``build`` (the layer normal), the check says whether the stress crosses the layers. Across them, the
material's data sheet factors (Z over XY) for strength and strain to failure are given, or without a material the
profile's range over PLA, PETG, ASA and CoPA (``fdm-orientation-z-*-ratio-tds``). A flexing feature (``flexes``: a snap
arm, a living hinge, a clip) whose stress crosses the layers warns: its strain to failure there is 0.10-0.61 of
in-plane.

**Limits.** Published design rules are for typical machines and settings, and their ``applies`` text (machine,
material, part size) is shown, not parsed: a reader must still judge which apply. Sizes are what the caller measured
or declared; this module does not measure a model (``cadagent.review.gates.wall`` does, by rays). A pass says no cited
source expects trouble making the feature; it does not prove the part prints, bends or holds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from cadagent.manufacturing import process as pp

VERDICTS = ("pass", "warn", "fail")
FLAT_DEG = 10.0     # a stress within this of the layer plane runs along the layers (as cadagent.mechanical.printed_joints)
LIMITS = (
    "published design rules for typical machines and settings, not a measurement of this printer or shop; each rule's "
    "`applies` text says where it holds and is not parsed",
    "sizes are the caller's, not measured from the model (cadagent.review.gates.wall measures walls by rays)",
    "rules marked (u) are not verified in their source: shown as advisory, never used to pass or fail",
    "a pass means no cited source expects trouble making the feature; it does not prove the part prints, bends or holds",
)


@dataclass(frozen=True)
class Kind:
    """What a feature kind is checked against: rules a selector picks, a lower (``min``) or upper (``max``) limit."""
    sense: str
    units: str
    pick: Callable[[pp.Rule], bool]
    says: str
    floor_only: bool = False      # hold a rule with a band at its lower end only (a fit's clearance band)


def _compare(*keys: str) -> Callable[[pp.Rule], bool]:
    return lambda r: r.compare in keys


def _ids(*ids: str) -> Callable[[pp.Rule], bool]:
    return lambda r: r.id in ids


KINDS: Dict[str, Kind] = {
    "wall": Kind("min", "mm", lambda r: r.compare == "min-wall" or r.id == "fdm-wall-min-nozzle-xometry-eu",
                 "wall thickness"),
    "hole": Kind("min", "mm", _compare("min-hole", "sm-hole-min"), "hole diameter"),
    "pin": Kind("min", "mm", _compare("min-pin"), "pin diameter"),
    "gap": Kind("min", "mm", lambda r: r.compare == "clearance-fit" or (r.feature == "clearance" and not r.compare),
                "clearance between parts or faces", floor_only=True),
    "rib": Kind("min", "mm", lambda r: r.feature == "rib" and not r.compare, "rib thickness"),
    "slot": Kind("min", "mm", lambda r: r.feature == "slot", "slot width"),
    "text": Kind("min", "mm", lambda r: r.feature == "text" and r.process == "fdm", "embossed or engraved text size"),
    "bridge": Kind("max", "mm", _compare("bridge-max"), "unsupported bridge length"),
    "overhang": Kind("max", "deg", lambda r: r.compare == "overhang-max" and r.process == "fdm",
                     "overhang angle from vertical"),
    "flange": Kind("min", "mm", _compare("sm-flange-min"), "flange length"),
    "bend-radius": Kind("min", "mm", _compare("sm-bend-radius-min"), "inside bend radius"),
    "hole-to-bend": Kind("min", "mm", _compare("sm-hole-to-bend"), "hole to bend distance"),
    "slot-to-bend": Kind("min", "mm", _ids("sm-slot-to-bend-min-paulsen"), "slot to bend distance"),
    "hole-to-edge": Kind("min", "mm", _compare("sm-hole-to-edge"), "hole to edge distance"),
    "hole-spacing": Kind("min", "mm", _compare("sm-hole-spacing"), "hole to hole distance"),
    "relief-depth": Kind("min", "mm", _compare("sm-relief-depth"), "bend relief depth"),
    "relief-width": Kind("min", "mm", _compare("sm-relief-width"), "bend relief width"),
    "hem": Kind("min", "mm", _compare("sm-hem-return"), "hem return length"),
}
SHOP_DECIDES = {"flange": "min_flange", "relief-depth": "relief_depth", "bend-radius": "R"}


@dataclass(frozen=True)
class Feature:
    """A feature of the part: ``kind`` one of :data:`KINDS`, ``size`` in mm (degrees from vertical for an overhang).
    ``stress_dir`` (FDM): the direction its bending or pulling stress runs in, in the part's frame; ``flexes``: it is
    meant to bend (a snap arm, a clip, a living hinge)."""
    name: str
    kind: str
    size: float
    stress_dir: Optional[Sequence[float]] = None
    flexes: bool = False

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {sorted(KINDS)}, not {self.kind!r}")
        if not (isinstance(self.size, (int, float)) and not isinstance(self.size, bool) and math.isfinite(self.size)
                and self.size >= 0):
            raise ValueError(f"{self.name}: size must be a finite number of at least 0, not {self.size!r}")


def _ends(lim: pp.Limit, sense: str) -> Tuple[Optional[float], Optional[float]]:
    """(lenient, strict) ends of a rule's limit for a lower-limit (``min``) or upper-limit (``max``) kind."""
    if lim.value is not None:
        return None, None
    lo, hi = lim.min, lim.max
    if lo is None:
        lo = hi
    if hi is None:
        hi = lo
    return (lo, hi) if sense == "min" else (hi, lo)


def _judge(size: float, lim: pp.Limit, sense: str, floor_only: bool = False) -> Tuple[str, str]:
    """(verdict, why) of one rule; ``info`` for a typical value that sets no limit."""
    if lim.value is not None:
        return "info", f"typical {lim.text}: a nominal figure, not a limit"
    if floor_only and lim.min is not None:
        ok = size >= lim.min
        return ("pass" if ok else "fail"), f"{'at least' if ok else 'below'} the band's lower end, {lim.min:.4g} " \
                                          f"{lim.units} ({lim.text})"
    if lim.window:
        ok = lim.min <= size <= lim.max
        return ("pass" if ok else "fail"), f"{'inside' if ok else 'outside'} the window {lim.text}"
    lenient, strict = _ends(lim, sense)
    beyond = (lambda a, b: a < b) if sense == "min" else (lambda a, b: a > b)
    if not beyond(size, strict):
        return "pass", f"meets {lim.text}"
    if not beyond(size, lenient):
        return "warn", f"inside the range {lim.text}: the source's own conditions decide (see applies)"
    return "fail", f"{'below' if sense == 'min' else 'above'} {lim.text}"


def _unit(v: Sequence[float], name: str) -> Tuple[float, float, float]:
    vals = [float(x) for x in v]
    n = math.sqrt(sum(x * x for x in vals)) if len(vals) == 3 and all(math.isfinite(x) for x in vals) else 0.0
    if n == 0.0:
        raise ValueError(f"{name} is three finite numbers, not all zero: {v!r}")
    return tuple(x / n for x in vals)  # type: ignore[return-value]


def _layers(f: Feature, prof: pp.Profile, material: Optional[str], build: Sequence[float]) -> Optional[Dict[str, Any]]:
    """The layer row of an FDM feature with a stress direction."""
    if f.stress_dir is None:
        return None
    s, b = _unit(f.stress_dir, "stress_dir"), _unit(build, "build")
    off_plane = math.degrees(math.asin(min(1.0, abs(sum(x * y for x, y in zip(s, b))))))
    across = off_plane > FLAT_DEG
    row: Dict[str, Any] = {"check": "layers", "off_plane_deg": round(off_plane, 2),
                           "direction": "across the layers" if across else "along the layers"}
    if material is not None:
        m = prof.material(material)
        row["factors"] = {q: {"value": fa.value, "source": fa.source, "citation": fa.citation, "verified": fa.verified}
                          for q, fa in m.factors.items() if q in ("strength", "strain")}
        row["material"] = m.name
        strength, strain = m.factor("strength").value, m.factor("strain").value
        span = f"strength x{strength:.2f} and strain to failure x{strain:.2f} of in-plane ({m.source})"
    else:
        lims = {q: prof.rule(f"fdm-orientation-z-{q}-ratio-tds").limit() for q in ("strength", "strain")}
        row["factors"] = {q: l.as_dict() for q, l in lims.items()}
        span = (f"strength x{lims['strength'].text} and strain to failure x{lims['strain'].text} of in-plane over PLA, "
                f"PETG, ASA and CoPA data sheets ({lims['strength'].rule}, {lims['strain'].rule}); give material for one "
                "filament's")
    if not across:
        row.update(verdict="pass", detail=f"the stress runs within {FLAT_DEG:g} deg of the layer plane: in-plane "
                                          "allowables apply")
    elif f.flexes:
        row.update(verdict="warn", detail=f"a flexing feature bends across the layers: {span}. Lay it in the layer "
                                          "plane, or size it to the across-layer strain "
                                          "(cadagent.mechanical.compliant.allowables)")
    else:
        row.update(verdict="pass", detail=f"the stress crosses the layers: use the across-layer allowables, {span}")
    return row


def _feature(f: Feature, prof: pp.Profile, env: Dict[str, float], excludes: Iterable[str],
             stock: Optional[pp.Stock]) -> Dict[str, Any]:
    kind = KINDS[f.kind]
    skip = set(excludes)
    rules = [r for r in prof.rules if kind.pick(r) and r.units == kind.units and r.id not in skip]
    rows, skipped, advisory = [], [], []
    for r in rules:
        missing = [v for v in r.variables if v not in env]
        if missing:
            skipped.append({"rule": r.id, "source": r.source, "needs": missing})
            continue
        lim = r.limit(**env)
        verdict, why = _judge(f.size, lim, kind.sense, kind.floor_only)
        row = {**lim.as_dict(), "verdict": verdict, "why": why, "cite": lim.cite()}
        (rows if r.verified else advisory).append(row)
    shop = None
    if stock is not None and f.kind in SHOP_DECIDES:
        need = getattr(stock, SHOP_DECIDES[f.kind])
        if f.kind == "bend-radius":
            # the shop's tooling gives one inside radius per stock: another radius is another shop or another tool
            ok = abs(f.size - need) <= 0.01
            shop = {"rule": stock.cite(), "source": stock.source, "verified": stock.verified, "value": need,
                    "units": "mm", "text": f"{need:.4g} mm", "verdict": "pass" if ok else "warn",
                    "why": f"the shop bends {stock.sku} ({stock.T:g} mm) at {need:.4g} mm"
                           + ("" if ok else f", not {f.size:g} mm: ask for other tooling or another shop")}
        else:
            ok = f.size >= need - 1e-9
            shop = {"rule": stock.cite(), "source": stock.source, "verified": stock.verified, "min": need,
                    "units": "mm", "text": f"at least {need:.4g} mm", "verdict": "pass" if ok else "fail",
                    "why": f"{'meets' if ok else 'below'} the shop's {need:.4g} mm for {stock.sku} ({stock.T:g} mm)"}
    limits = [r for r in rows if r["verdict"] != "info"]
    if shop is not None:
        verdict = shop["verdict"]
        detail = f"{shop['why']}; the shop's table decides, the generic rules are shown beside it"
    elif not limits:
        verdict, detail = "warn", "no verified rule limits this feature for this process: not checked"
    else:
        passed = [r["rule"] for r in limits if r["verdict"] == "pass"]
        short = [r["rule"] for r in limits if r["verdict"] != "pass"]
        inside = [r["rule"] for r in limits if r["verdict"] == "warn"]
        if not short:
            verdict, detail = "pass", f"meets all {len(limits)} verified rules"
        elif not passed and not inside:
            verdict, detail = "fail", f"beyond all {len(limits)} verified rules"
        else:
            verdict = "warn"
            detail = f"meets {len(passed)} of {len(limits)} verified rules" + \
                (f", inside the range of {', '.join(inside)}" if inside else "") + \
                (f"; beyond {', '.join(r for r in short if r not in inside)}" if len(short) > len(inside) else "")
    strict = None
    if limits:
        ends = [_ends(pp.Limit(r["rule"], "", "", "", True, min=r.get("min"), max=r.get("max")), kind.sense)[1]
                for r in limits]
        strict = (max if kind.sense == "min" else min)(ends)
    return {"name": f.name, "kind": f.kind, "says": kind.says, "size": f.size, "units": kind.units,
            "sense": kind.sense, "verdict": verdict, "detail": detail, "strictest": strict, "shop": shop,
            "rules": rows, "advisory": advisory, "skipped": skipped}


def check(process: str, features: Iterable[Feature], *, material: Optional[str] = None,
          nozzle_mm: Optional[float] = None, thickness_mm: Optional[float] = None, radius_mm: Optional[float] = None,
          shop: bool = True, build: Sequence[float] = (0.0, 0.0, 1.0), exclude: Iterable[str] = (),
          path: Any = None) -> Dict[str, Any]:
    """Check features against the process profile. ``material``: an FDM filament (a key of
    :data:`cadagent.manufacturing.process.FDM_MATERIALS`) for its layer factors, or a sheet alloy (``5052``,
    ``mild-steel``) for its rules and the shop's table. ``nozzle_mm`` (FDM), ``thickness_mm`` and ``radius_mm`` (sheet;
    the radius defaults to the shop's for the stock) fill the rules' expressions. ``shop=False`` ignores the shop table.
    ``exclude``: rule ids the caller judges do not apply (say which, and why, in the design's record)."""
    prof = pp.profile(process, path)
    features = list(features)
    if not features:
        raise ValueError("give at least one Feature to check")
    if material is not None and process not in ("fdm", "sheet-metal"):
        raise ValueError(f"material is read for fdm (layer factors) and sheet-metal (rules, shop table), not {process}")
    env: Dict[str, float] = {}
    excludes = list(exclude)
    stock = None
    if nozzle_mm is not None:
        env["nozzle"] = float(nozzle_mm)
    if process == "sheet-metal":
        if thickness_mm is None:
            raise ValueError("sheet metal needs thickness_mm")
        env["T"] = float(thickness_mm)
        if material is not None:
            sm = prof.material(material)
            excludes += list(sm.excludes)
            stock = sm.stock(thickness_mm) if shop else None
        if radius_mm is None and stock is not None:
            radius_mm = stock.R
        if radius_mm is not None:
            env["R"] = float(radius_mm)
        if stock is not None and abs(env.get("R", stock.R) - stock.R) > 1e-6:
            stock = None                 # the shop's minimum flange and relief are for its own radius
    elif material is not None and process == "fdm":
        prof.material(material)
    out =[_feature(f, prof, env, excludes, stock) for f in features]
    if process == "fdm":
        for f, row in zip(features, out):
            lay = _layers(f, prof, material, build)
            if lay is not None:
                row["layers"] = lay
                if VERDICTS.index(lay["verdict"]) > VERDICTS.index(row["verdict"]):
                    row["verdict"] = lay["verdict"]
    verdict = max((r["verdict"] for r in out), key=VERDICTS.index) if out else "pass"
    used = sorted({x["source"] for r in out for x in r["rules"] + r["advisory"]} |
                  ({stock.source} if stock is not None and any(r["shop"] for r in out) else set()))
    return {"check": "process features", "process": process, "title": prof.title, "material": material,
            "env": env, "stock": stock.sku if stock is not None else None, "excluded": excludes, "verdict": verdict,
            "features": out, "sources": {s: prof.source(s).credit for s in used}, "limits": list(LIMITS)}
