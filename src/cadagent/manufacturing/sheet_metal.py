"""Sheet-metal bends from the process profile: K-factor, bend allowance and deduction, flat length, and the shortest
flange and relief, each with the rule or shop row it came from (#99).

    from cadagent.manufacturing import sheet_metal as sm
    b = sm.bend("5052", 1.6)                       # SendCutSend's 1.6 mm 5052: R 0.889, K 0.42, flange >= 7.696 mm
    b["allowance_mm"], b["deduction_mm"], b["k"]["source"]
    sm.flat_length([20, 30, 20], "mild-steel", 1.519, angles=[90, 90], shop=False)   # a U channel, generic rules
    sm.bend("5052", 2.0, radius_mm=2.0)            # no shop row: the generic K table and the strictest generic flange

**Order of the numbers** (research/process-profiles.yaml asks a check to read the chosen shop's table before any generic
rule):

1. a value the caller gives (``radius_mm``, ``k``);
2. the shop's row for the material and thickness (``shop_tables``; its K and minimum flange are for its own radius, so a
   different ``radius_mm`` drops to step 3 for K, flange and relief);
3. the generic rules: the inside radius is the largest verified ``sm-bend-radius-min`` (T for 5052 and mild steel);
   K is the Protolabs Network air-bending table, by the material's hardness class and R / T (``sm-k-air-*-hubs``:
   0 to T, T to 3T, above 3T; on a boundary the lower band, so R = T takes "0 to T"); the minimum flange and relief depth are the strictest verified rule, every one listed.

**The equations.** Bend allowance, the neutral line's arc: ``BA = pi (R + K T) A / 180`` (the profile's formula
``sm-bend-allowance``, from SolidWorks' K-factor page), A the bend angle in degrees (how far the flange turns from flat,
90 for a right angle). Outside setback ``OSSB = (R + T) tan(A / 2)``, and bend deduction ``BD = 2 OSSB - BA``: the
geometry that turns BA into the length to take off the outside dimensions, so the flat blank is the sum of the legs
measured to the outside mould lines less one BD per bend.

**Limits.** K depends on the material lot, the tooling and the bending method (air bending here); a shop's K is for its
own press brake. The flat length is a starting point: the shop's own CAD or a test bend sets the final blank, and bend
angles are held to about +/- 1 degree (``sm-bend-angle-tolerance-*``). Minimum flanges are measured from different
datums by different sources (most do not say); the shop's is its own. None of this predicts cracking on the outside of
a tight bend in a hard temper or across the grain.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from cadagent.manufacturing import process as pp

BENDING = "air bending"


def _num(name: str, v: Any, positive: bool = True) -> float:
    if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and (v > 0 if positive
                                                                                           else v >= 0)):
        raise ValueError(f"{name} must be a finite number {'above' if positive else 'of at least'} 0, not {v!r}")
    return float(v)


def _value(value: float, rule: str, source: str, verified: bool, how: str) -> Dict[str, Any]:
    return {"value": round(float(value), 6), "rule": rule, "source": source, "verified": verified, "how": how,
            "flag": "" if verified else pp.UNVERIFIED}


def k_rule_id(hardness: str, radius_mm: float, thickness_mm: float) -> str:
    """The generic K-table row for a hardness class (soft, medium, hard) and R / T: R up to T, T to 3T, above 3T.
    The table's bands meet at R = T and R = 3T; a radius on a boundary takes the lower band (R = T: "0 to T"), which is
    where every generic bend with the minimum radius T lands."""
    ratio = radius_mm / thickness_mm
    if ratio > 3.0:
        return "sm-k-air-r-gt-3t-hubs"
    return f"sm-k-air-{hardness}-r-{'le-t' if ratio <= 1.0 else 't-3t'}-hubs"


def _strictest(prof: pp.Profile, compare: str, env: Dict[str, float], excludes: Sequence[str]) -> Dict[str, Any]:
    lims = [l for l in prof.limits(compare=compare, exclude=excludes, **env) if l.verified and l.min is not None]
    if not lims:
        raise pp.ProfileDataError(f"no verified {compare} rule for {env}")
    top = max(lims, key=lambda l: (l.max if l.max is not None and not l.window else l.min))
    need = top.max if top.max is not None and not top.window else top.min
    out = _value(need, top.rule, top.source, top.verified, f"the strictest of {len(lims)} verified rules")
    out["all"] = [l.as_dict() for l in lims]
    return out


def bend(material: str, thickness_mm: float, angle_deg: float = 90.0, *, radius_mm: Optional[float] = None,
         k: Optional[float] = None, shop: bool = True, path: Any = None) -> Dict[str, Any]:
    """One bend in ``material`` (``5052`` or ``mild-steel``) of ``thickness_mm``, turned ``angle_deg`` from flat
    (0 < A < 180). Returns the radius, K, bend allowance, outside setback, bend deduction, the shortest flange and the
    relief depth, each with where it came from."""
    t = _num("thickness_mm", thickness_mm)
    a = _num("angle_deg", angle_deg)
    if a >= 180.0:
        raise ValueError(f"angle_deg must be below 180 (a hem is not a bend this computes), not {angle_deg!r}")
    prof = pp.profile("sheet-metal", path)
    mat = prof.material(material)
    stock = mat.stock(t) if shop else None
    if radius_mm is not None:
        r = _num("radius_mm", radius_mm)
        radius = _value(r, "given", "caller", True, "given")
        if stock is not None and abs(r - stock.R) > 1e-6:
            stock = None
    elif stock is not None:
        radius = _value(stock.R, stock.cite(), stock.source, stock.verified, "the shop's tooling for this stock")
    else:
        radius = _strictest(prof, "sm-bend-radius-min", {"T": t}, mat.excludes)
        radius["how"] = "the generic minimum inside radius, " + radius["how"]
    r = radius["value"]
    if k is not None:
        kf = _num("k", k)
        if not 0.0 < kf <= 0.5:
            raise ValueError(f"k must be above 0 and at most 0.5 (the neutral line lies in the sheet's inner half), not {k!r}")
        kv = _value(kf, "given", "caller", True, "given")
    elif stock is not None:
        kv = _value(stock.K, stock.cite(), stock.source, stock.verified, "the shop's K for this stock and radius")
    else:
        rid = k_rule_id(mat.hardness, r, t)
        rule = prof.verified_rule(rid)          # a (u) K row never sets a flat length
        lim = rule.limit()
        kv = _value(lim.value, rid, rule.source, rule.verified,
                    f"the generic {BENDING} table, {mat.hardness} metal ({mat.why.split(';')[0]}), R/T {r / t:.3g}")
    kf = kv["value"]
    formula = prof.formulas["sm-bend-allowance"]
    ba = pp.evaluate(formula["expr"], {"R": r, "K": kf, "T": t, "A": a})
    ossb = (r + t) * math.tan(math.radians(a) / 2.0)
    bd = 2.0 * ossb - ba
    env = {"T": t, "R": r}
    if stock is not None:
        flange = _value(stock.min_flange, stock.cite(), stock.source, stock.verified, "the shop's shortest flange")
        relief = _value(stock.relief_depth, stock.cite(), stock.source, stock.verified, "the shop's relief depth")
    else:
        flange = _strictest(prof, "sm-flange-min", env, mat.excludes)
        relief = _strictest(prof, "sm-relief-depth", env, mat.excludes)
    return {"material": mat.name, "thickness_mm": t, "angle_deg": a, "stock": stock.sku if stock else None,
            "radius_mm": radius, "k": kv, "allowance_mm": round(ba, 6), "setback_mm": round(ossb, 6),
            "deduction_mm": round(bd, 6), "min_flange_mm": flange, "relief_depth_mm": relief,
            "formula": {"id": formula["id"], "expr": formula["expr"], "source": formula["source"]},
            "sources": {s: prof.source(s).credit for s in sorted({x["source"] for x in (radius, kv, flange, relief)
                                                                    if x["source"] != "caller"} | {formula["source"]})},
            "limits": ["K depends on the lot, tooling and method (air bending); a shop's K is for its own press brake",
                       "a starting blank: the shop's CAD or a test bend sets the final one; angles hold to about 1 deg",
                       "minimum flanges are measured from datums most sources do not state",
                       "does not predict cracking at a tight radius, a hard temper or a bend across the grain"]}


def flat_length(legs_mm: Sequence[float], material: str, thickness_mm: float,
                angles: Union[float, Iterable[float]] = 90.0, **kw: Any) -> Dict[str, Any]:
    """The flat blank of a part with ``len(legs_mm) - 1`` bends: the legs measured to the outside mould lines, less one
    bend deduction per bend. ``angles`` is one angle for every bend or one per bend; ``kw`` goes to :func:`bend`.
    Each leg is also checked against the shortest flange (the end legs and every leg between bends)."""
    legs = [_num("a leg", x) for x in legs_mm]
    if len(legs) < 2:
        raise ValueError("give at least two legs (one bend)")
    n = len(legs) - 1
    angs = [float(angles)] * n if isinstance(angles, (int, float)) else [float(x) for x in angles]
    if len(angs) != n:
        raise ValueError(f"{n} bends need {n} angles, not {len(angs)}")
    bends = [bend(material, thickness_mm, a, **kw) for a in angs]
    total = sum(legs) - sum(b["deduction_mm"] for b in bends)
    need = max(b["min_flange_mm"]["value"] for b in bends)
    short = [i for i, x in enumerate(legs) if x + 1e-9 < need]
    return {"flat_mm": round(total, 6), "legs_mm": legs, "bends": bends,
            "short_legs": short, "min_flange_mm": bends[0]["min_flange_mm"],
            "verdict": "fail" if short else "pass",
            "detail": (f"legs {short} are shorter than the {need:.4g} mm flange ({bends[0]['min_flange_mm']['rule']})"
                       if short else f"every leg is at least the {need:.4g} mm flange")}
