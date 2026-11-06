"""Sheet-metal bends from the process profile: K-factor, bend allowance and deduction, flat length, and the shortest
flange and relief, each with the rule or shop row it came from (#99).

    from cadagent.manufacturing import sheet_metal as sm
    b = sm.bend("5052", 1.6)                       # SendCutSend's 1.6 mm 5052: R 0.889, K 0.42, flange >= 7.696 mm
    b["allowance_mm"], b["deduction_mm"], b["k"]["source"]
    sm.flat_length([20, 30, 20], "mild-steel", 1.519, angles=[90, 90], shop=False)   # a U channel, generic rules
    sm.bend("5052", 2.0, radius_mm=2.0)            # no shop row: the generic K table and the strictest generic flange

**Order of the numbers** (docs/research/process-profiles.yaml asks a check to read the chosen shop's table before any generic
rule):

1. a value the caller gives (``radius_mm``, ``k``);
2. the shop's row for the material and thickness (``shop_tables``; its K and minimum flange are for its own radius, so a
   different ``radius_mm`` drops to step 3 for K, flange and relief);
3. the generic rules: the inside radius is the largest verified ``sm-bend-radius-min`` (T for 5052 and mild steel);
   K is the Protolabs Network air-bending table, by the material's hardness class and R / T (``sm-k-air-*-hubs``:
   0 to T, T to 3T, above 3T; on a boundary the lower band, so R = T takes "0 to T"); the minimum flange and relief
   depth are the strictest verified rule, every one listed.

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
    """One bend in ``material`` (a key of ``process.SHEET_MATERIALS``: ``5052``, ``mild-steel``, ``g90``, ``304`` or
    ``316``) of ``thickness_mm``, turned ``angle_deg`` from flat (0 < A < 180). Returns the radius, K, bend
    allowance, outside setback, bend deduction, the shortest flange and the relief depth, each with where it came
    from."""
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


# ----------------------------------------------------------------------------- features near a bend, and shop limits

ORDER = {"pass": 0, "warn": 1, "fail": 2}


def _check(name: str, verdict: str, value: Any, limit: str, rule: str, source: str, detail: str) -> Dict[str, Any]:
    return {"check": name, "verdict": verdict, "value": value, "limit": limit, "rule": rule, "source": source,
            "detail": detail}


def feature_to_bend(material: str, thickness_mm: float, edge_to_tangent_mm: float, angle_deg: float = 90.0, *,
                    radius_mm: Optional[float] = None, shop: bool = True, path: Any = None) -> Dict[str, Any]:
    """A hole or cut-out near a bend, against every generic hole-to-bend rule (``compare: sm-hole-to-bend``), each on its
    own datum. ``edge_to_tangent_mm`` is measured on the flat from the feature's nearest edge to the bend's tangent
    line (where the bend radius starts), the datum Hubs and Davis use. Century Tywood measures to the inside face of
    the other leg; this takes that as the inside mould line, the inside setback R tan(A/2) further on (R at 90
    degrees, where the two are the same), and never more than R, so a bend sharper than 90 degrees earns no extra
    distance. Where a rule does not state its datum, the tangent is assumed and the result says so: a feature that
    clears every rule with a stated datum but not one of those gets a warning, not a fail."""
    d = _num("edge_to_tangent_mm", edge_to_tangent_mm, positive=False)
    b = bend(material, thickness_mm, angle_deg, radius_mm=radius_mm, shop=shop, path=path)
    t, r, a = b["thickness_mm"], b["radius_mm"]["value"], b["angle_deg"]
    prof = pp.profile("sheet-metal", path)
    mat = prof.material(material)
    inside = min(r * math.tan(math.radians(a) / 2.0), r)      # never more credit than at 90 degrees
    rows, worst = [], "pass"
    for lim in prof.limits(compare="sm-hole-to-bend", exclude=mat.excludes, T=t, R=r):
        if not lim.verified or lim.min is None:
            continue
        datum = prof.rule(lim.rule).datum or "not stated"
        if "inside" in datum:
            have, on, stated = d + inside, "the inside face of the other leg", True
        else:
            stated = "tangent" in datum or "start of the bend radius" in datum
            have, on = d, "the tangent" + ("" if stated else " (assumed: the rule states no datum)")
        ok = have + 1e-9 >= lim.min
        v = "pass" if ok else ("fail" if stated else "warn")
        worst = max(worst, v, key=ORDER.get)
        rows.append({"rule": lim.rule, "source": lim.source, "datum": datum, "measured_from": on,
                     "distance_mm": round(have, 4), "min_mm": round(lim.min, 4), "verdict": v})
    if not rows:
        raise pp.ProfileDataError("no verified sm-hole-to-bend rule")
    return {"verdict": worst, "material": b["material"], "thickness_mm": t, "radius_mm": r, "angle_deg": a,
            "stock": b["stock"], "rules": rows,
            "limits": ["the sources measure from different datums; the conversions assume a sharp flat pattern with the "
                       "tangent line at the start of the bend radius",
                       "a shop's own distance (SendCutSend: half its die width from the bend centre line) needs that "
                       "shop's die width, which its tables here do not give: ask the shop"]}


def _shop_rule(rules: Dict[str, Any], key: str, **env: float) -> Optional[Dict[str, Any]]:
    if key not in rules:
        return None
    lim = rules[key].limit(**env)
    return {"lim": lim, "rule": key, "source": rules[key].source, "applies": rules[key].applies or ""}


def _at_least(name: str, have: float, need: Dict[str, Any], generic: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fail below ``need`` (the shop's row or rule, else the strictest generic rule). Warn when ``need`` came from a
    shop and ``have`` clears it but not the strictest generic rule: the shop's tooling may make it, others may not."""
    if have + 1e-9 < need["value"]:
        return _check(name, "fail", have, f"at least {need['value']:.3f} mm", need["rule"], need["source"], need["how"])
    if generic is not None and have + 1e-9 < generic["value"]:
        return _check(name, "warn", have, f"at least {generic['value']:.3f} mm", generic["rule"], generic["source"],
                      f"meets {need['rule']} ({need['value']:.3f} mm) but not the strictest generic rule")
    return _check(name, "pass", have, f"at least {need['value']:.3f} mm", need["rule"], need["source"], need["how"])


def check_bends(material: str, thickness_mm: float, flanges_mm: Sequence[float],
                angles: Union[float, Iterable[float]] = 90.0, *, relief_depth_mm: Optional[float] = None,
                relief_width_mm: Optional[float] = None, box: bool = False, hardware: bool = False,
                channel_base_mm: Optional[float] = None, shop: Optional[str] = None, radius_mm: Optional[float] = None,
                rows: bool = True, path: Any = None) -> Dict[str, Any]:
    """A bent part's bends, each verdict with its rule and source:

    - each flange (``flanges_mm``, to the outside mould line) at least the shortest flange: the shop's row for the
      stock, else the strictest generic rule;
    - the relief depth (``relief_depth_mm``, past the bend line as the sources measure it; SendCutSend from the bend
      line) at least the row's depth, else the strictest generic rule, and with ``shop`` named at least the shop's own
      rule as well (its feed and its article can differ);
    - the relief width at least the strictest generic rule;
    - with ``shop`` named, its own limits: the bend angles it can make (its ``sm-bend-angle-*`` rules; SendCutSend:
      5 to 130 degrees, and at most 90 with ``hardware``), the longest flange of a four-sided ``box`` (shorter with
      ``hardware``), and a channel's base (``channel_base_mm``) at least twice its flange.

    A value that clears only a shop's number (its row or its own rule) and not the strictest generic rule warns. The
    shop's rows (radius, K, flange, relief depth) are read by default, as in ``bend()``; ``rows=False`` drops them.
    """
    prof = pp.profile("sheet-metal", path)
    flanges = [_num("a flange", x) for x in flanges_mm]
    if not flanges:
        raise ValueError("give at least one flange")
    angs = [float(angles)] * len(flanges) if isinstance(angles, (int, float)) else [float(x) for x in angles]
    if len(angs) != len(flanges):
        raise ValueError(f"{len(flanges)} flanges need {len(flanges)} angles, not {len(angs)}")
    base = None if channel_base_mm is None else _num("channel_base_mm", channel_base_mm)
    rules = {r.id: r for r in prof.rules_for(shop=shop)} if shop else {}
    mat = prof.material(material)
    checks: List[Dict[str, Any]] = []
    notes: List[str] = []
    for i, (f, a) in enumerate(zip(flanges, angs)):
        b = bend(material, thickness_mm, a, radius_mm=radius_mm, shop=rows, path=path)
        env = {"T": b["thickness_mm"], "R": b["radius_mm"]["value"]}
        generic = _strictest(prof, "sm-flange-min", env, mat.excludes) if b["stock"] else None
        checks.append(_at_least(f"flange {i + 1}", f, b["min_flange_mm"], generic))
        for key, hw, tag in ((f"sm-bend-angle-max-{shop}", False, ""), (f"sm-bend-angle-min-{shop}", False, " (min)"),
                             (f"sm-bend-angle-max-hardware-{shop}", True, " (hardware)")):
            sr = _shop_rule(rules, key)
            if not sr or (hw and not hardware):
                continue
            lim = sr["lim"]
            ok = (lim.min is None or a + 1e-9 >= lim.min) and (lim.max is None or a <= lim.max + 1e-9)
            bound = f"at least {lim.min:g} deg" if lim.min is not None else f"at most {lim.max:g} deg"
            checks.append(_check(f"angle {i + 1}{tag}", "pass" if ok else "fail", a, bound, key, sr["source"],
                                 sr["applies"]))
    b = bend(material, thickness_mm, angs[0], radius_mm=radius_mm, shop=rows, path=path)
    t, r = b["thickness_mm"], b["radius_mm"]["value"]
    if relief_depth_mm is not None:
        dep = _num("relief_depth_mm", relief_depth_mm)
        need = dict(b["relief_depth_mm"])
        sr = _shop_rule(rules, f"sm-relief-depth-min-{shop}", T=t, R=r)
        if sr and sr["lim"].min > need["value"] + 1e-9:
            need = _value(sr["lim"].min, sr["rule"], sr["source"], True,
                          f"{shop}'s own rule, deeper than " + ("its row" if b["stock"] else "the generic rules"))
        generic = _strictest(prof, "sm-relief-depth", {"T": t, "R": r}, mat.excludes) if b["stock"] else None
        checks.append(_at_least("relief depth", dep, need, generic))
    if relief_width_mm is not None:
        w = _num("relief_width_mm", relief_width_mm)
        lims = [l for l in prof.limits(compare="sm-relief-width", exclude=mat.excludes, shop=shop, T=t, R=r)
                if l.verified and l.min is not None]
        generic_w = [l for l in lims if not prof.rule(l.rule).shop]
        own = [l for l in lims if prof.rule(l.rule).shop]
        top = max(generic_w, key=lambda l: l.min)
        if w + 1e-9 >= top.min:
            v, why = "pass", f"at least the strictest generic width ({top.rule})"
        elif own and w + 1e-9 >= max(l.min for l in own):
            v, why = "warn", f"meets {shop}'s own width but not the strictest generic one ({top.rule})"
        else:
            v, why = "fail", "narrower than every rule"
        checks.append(_check("relief width", v, w, f"at least {top.min:.3f} mm", top.rule, top.source, why))
    sr = _shop_rule(rules, f"sm-box-flange-max{'-hardware' if hardware else ''}-{shop}") if box else None
    if sr:
        top, longest = sr["lim"].max, max(flanges)
        checks.append(_check("box flange", "pass" if longest <= top + 1e-9 else "fail", longest, f"at most {top:g} mm",
                             sr["rule"], sr["source"], f"a four-sided box {'with' if hardware else 'without'} hardware"))
    sr = _shop_rule(rules, f"sm-channel-base-{shop}") if base is not None else None
    if sr:
        ratio = sr["lim"].min
        need_b = ratio * max(flanges)
        checks.append(_check("channel base", "pass" if base + 1e-9 >= need_b else "fail", base,
                             f"at least {need_b:.3f} mm ({ratio:g} x the flange)", sr["rule"], sr["source"],
                             "a U channel's base must clear the tooling between its flanges"))
    if not shop and (box or hardware or base is not None):
        notes.append("box, hardware and channel_base_mm are a shop's limits: name the shop to check them; no generic "
                     "rule covers them")
    verdict = max((c["verdict"] for c in checks), key=ORDER.get)
    return {"verdict": verdict, "material": b["material"], "thickness_mm": t, "stock": b["stock"], "checks": checks,
            "notes": notes,
            "limits": ["a shop's limits apply only when that shop is named; its tooling rows (radius, K, flange, relief "
                       "depth) are read by default, as in bend() (rows=False drops them)",
                       "flanges are measured to the outside mould line; most sources do not state a datum",
                       "not checked: a flange's width (SendCutSend: 88.9-127 mm flanges at least 27.94 mm wide), "
                       "boxes that close in on themselves, and the shop's die width near holes"]}
