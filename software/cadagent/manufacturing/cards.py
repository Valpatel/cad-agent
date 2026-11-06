"""Rule cards and decision cards: referenced design practice in one call and about 2 KB (#323 phase 7b).

    cad-agent rules insert-hole --process fdm --material petg-cf     # the rules for one feature, one line each
    cad-agent rules insert-hole --why fdm-insert-hole-cad-offset-cnckitchen     # one rule and its sources
    cad-agent choose joining --load 200 --cycles 50 --material petg --process fdm

    from cadagent.manufacturing import cards
    cards.card("insert-hole", process="fdm", material="petg-cf")     # a dict; render_card() gives the text
    cards.choose("joining", load=200, cycles=50, material="petg", process="fdm")

The goal is an experienced engineer beside a junior one: the rule, its numbers, **when** it holds and when it does not
(and what to use then), whether it is **non-negotiable** or a guideline with wiggle room, what holding it tighter
**costs**, how far the evidence goes, what code enforces it, and the source.

**One source of truth.** Nothing here is hand-written copy. A rule card is generated from
``docs/research/process-profiles.yaml`` (the rule, its numbers, ``applies`` and the ``when``/``not_when``/``strictness``/
``wiggle``/``cost`` fields, :class:`cadagent.manufacturing.process.Rule`), the reference registry
(:mod:`cadagent.review.references`: the source's evidence class gives the confidence, and every ``[ref:<id>]`` must be
a read record) and the encoded functions (the rule's ``applied_by``). A card is a profile feature (``hole``, ``insert``,
``thread``) or a name in the file's ``cards``, which gathers rules across features by their ``cards:`` field.

**Refused, not guessed.** A rule whose source is not a read record, or whose text cites one that is not, is refused:
the card raises :class:`CardError` rather than serve it. A rule marked ``u`` (not verified) is left out and counted.
Where no source says when, how strict or what it costs, the file says ``unstated`` and the card prints ``?``.

**Decision tables** (``decisions`` in the same file) encode a judgement call as rows evaluated in order; the first row
whose ``if`` holds wins and the last has no ``if``. The format, so later decisions (process, tolerance allocation,
simplification) reuse it:

* ``inputs``: name -> ``{choices: [...]}`` or ``{units, default, help}`` (numbers); ``required: true`` instead of a
  default when no value is safe to assume (the load: assuming 0 would choose a clip);
* ``facts``: values computed by an encoded function (``by``, from the inputs named in ``from``), such as whether an
  insert carries the load; a fact may be ``None`` (not computable here), which no condition matches. Its other fields
  fill text as ``{fact.field}`` (``{insert_fits.why}``) and appear in the JSON as ``detail[fact]``;
* ``unused``: an input no row reads, and why (a gap in the sources, said in the output);
* ``options``: id -> ``{name, cards, check}``: the rule cards each relies on, and the ``cad-agent`` command that sizes it;
* ``rows``: ``{id, if, needs, choose, because, rules, by, runner_up, wins_when, gap}``. ``if`` maps an input to a list
  of values or ``{min, max}`` (inclusive), or a fact to true or false. ``needs`` lists the facts the row's choice
  relies on: when the row is reached and one of them is None, the card answers **not decided** and says what is
  missing, rather than choose unchecked. Every ``because`` line carries ``[ref:<id>]`` tags
  or fills a computed fact with the row's ``by`` naming the function; ``wins_when`` is cited, names a ``cad-agent``
  command or a computed fact, or is ``unstated`` with a ``gap``.

**Budget.** Every card's text fits :data:`CARD_BYTES` and its JSON :data:`JSON_BYTES`; lines past it are dropped by
priority (non-negotiable rules first, then enforced ones) and named by id in a closing line (``more`` in the JSON).

A card says what published sources and tested code say. It does not prove a part fits or holds: a coupon on your
printer, or a test, governs.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent.manufacturing import process as pp

CARD_BYTES = 2048                  # one card or one decision, as text: the owner's 1-2 KB per answer (#323)
JSON_BYTES = 4096                  # the same card as compact JSON (the lines the text keeps, the rest by id)
MORE_IDS = 400                     # bytes of left-out ids a closing line names before it counts the rest
STRICTNESS = ("non-negotiable", "guideline", "unstated")
UNSTATED = "unstated"
WHEN_FIELDS = ("when", "not_when", "wiggle", "cost")
from cadagent.review.references import TAG as REF   # the registry's one tag pattern
FACT = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)?)\}")     # {input}, {fact} or {fact.field}
DECISION_SCHEMA = "cadagent.decision-card/1"
COMMAND = re.compile(r"`cad-agent [a-z][a-z0-9-]*")
_RANK = {"non-negotiable": 0, "guideline": 2, "unstated": 3, "": 3}


class CardError(ValueError):
    """A card or decision that cannot be served: an unknown name or input, or a rule or reason that is not cited."""


# ----------------------------------------------------------------------------- data

@lru_cache(maxsize=4)
def _raw(path: Path, mtime: float) -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def data(path: Any = None) -> Dict[str, Any]:
    """The process-profile file as read (its ``cards`` and ``decisions`` sections; rules come typed from
    :func:`cadagent.manufacturing.process.load`)."""
    p = pp.data_path(path).resolve()
    return _raw(p, p.stat().st_mtime)


def registry(path: Any = None):
    """The reference registry beside the profile file (cached until it or a shard changes)."""
    core = pp.data_path(path).resolve().parent / "references.yaml"
    files = [core] + sorted(core.with_suffix("").glob("*.yaml"))
    return _registry(core, tuple(f.stat().st_mtime for f in files if f.is_file()))


@lru_cache(maxsize=2)
def _registry(core: Path, mtimes: Tuple[float, ...]):
    from cadagent.review import references
    return references.load(core)


def _rules(path: Any = None) -> List[pp.Rule]:
    return pp.load(path).rules()


def card_names(path: Any = None) -> Dict[str, str]:
    """Every card: the profile features (titled by their processes) and the file's ``cards``."""
    out = {name: str(title) for name, title in (data(path).get("cards") or {}).items()}
    for r in _rules(path):
        out.setdefault(r.feature, f"{r.feature} rules")
    return dict(sorted(out.items()))


def material_family(process: str, material: Optional[str]) -> Optional[str]:
    """The family a material belongs to, for a rule's ``materials``: an fdm filament key or family
    (``petg-cf-bambu`` or ``petg-cf`` -> ``petg-cf``), or a sheet alloy key. None when no material is given. An
    unknown material raises CardError listing the known ones; other processes keep the name as given."""
    if material is None:
        return None
    if process == "fdm":
        families = {fam for fam, _ in pp.FDM_MATERIALS.values()}
        if material in pp.FDM_MATERIALS:
            return pp.FDM_MATERIALS[material][0]
        if material in families:
            return material
        raise CardError(f"fdm material {material!r} is not known: give a family ({', '.join(sorted(families))}) or a "
                        f"filament ({', '.join(sorted(pp.FDM_MATERIALS))})")
    if process == "sheet-metal":
        if material not in pp.SHEET_MATERIALS:
            raise CardError(f"sheet material {material!r} is not known: {', '.join(sorted(pp.SHEET_MATERIALS))}")
        return material
    return material


def _known(process: str, material: Optional[str]) -> bool:
    """True when ``material`` is None or names a material of ``process`` (any name, for a process with no table)."""
    try:
        material_family(process, material)
        return True
    except CardError:
        return False


# ----------------------------------------------------------------------------- citations

def _read_problem(key: str, reg) -> Optional[str]:
    """Why ``key`` may not back a card line, or None when it is a read source."""
    if key not in reg:
        return f"{key!r} is not in the reference registry"
    ref = reg.resolve(key)
    if ref.kind != "source":
        return f"{key!r} is a {ref.evidence_class or ref.kind} record, not a read source"
    return None


def rule_problems(rule: pp.Rule, reg, datasets: Sequence[str] = ()) -> List[str]:
    """Why a rule may not be served on a card: its source, or a [ref:<id>] in its card fields, is not a read record."""
    out = []
    if rule.source.startswith("dataset:"):
        if rule.source.split(":", 1)[1] not in datasets:
            out.append(f"{rule.id}: cites {rule.source}, which the file's datasets do not list")
    else:
        why = _read_problem(rule.source, reg)
        if why:
            out.append(f"{rule.id}: its source {why}")
    for f in WHEN_FIELDS:
        for key in REF.findall(getattr(rule, f)):
            why = _read_problem(key, reg)
            if why:
                out.append(f"{rule.id}: {f} cites {why}")
    return out


def confidence(source: str, reg) -> str:
    """The level #143 derives from the source record's evidence: high, medium, low or unknown (dataset for a
    dataset kept on another research page)."""
    if source.startswith("dataset:"):
        return "dataset"
    from cadagent.review.references import confidence as level
    return level(reg.resolve(source), reg)["level"]


# ----------------------------------------------------------------------------- rule cards

def _num(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, (int, float)) else str(v)


def numbers(rule: pp.Rule) -> str:
    """``0.2-0.3 mm``, ``at least sqrt(D*D + track*track) mm``: the rule's numbers, an expression left as written."""
    if not rule.variables:
        return rule.limit().text
    u = "" if rule.units in ("ratio", "count") else (" %" if rule.units == "percent" else f" {rule.units}")
    if rule.value is not None:
        return f"{_num(rule.value)}{u}"
    if rule.min is not None and rule.max is not None:
        return f"{_num(rule.min)} to {_num(rule.max)}{u}"
    return f"at least {_num(rule.min)}{u}" if rule.min is not None else f"at most {_num(rule.max)}{u}"


def _tag(key: str) -> str:
    return "[ref" + f":{key}]"          # split so the registry's tag scan does not read this line as a citation


def _short(name: str) -> str:
    return ".".join(name.split(".")[-2:])


def _q(text: str) -> str:
    return "?" if text == UNSTATED else text


def line(rule: pp.Rule, reg) -> Dict[str, Any]:
    """One card line as data: the rule, its numbers and every when-field, confidence, what applies it, its source."""
    return {"rule": rule.id, "process": rule.process, "quantity": rule.quantity, "numbers": numbers(rule),
            "when": rule.when or rule.applies, "not_when": rule.not_when, "instead": list(rule.instead),
            "strictness": rule.strictness or "", "wiggle": rule.wiggle, "cost": rule.cost,
            "unstated": [f for f in ("when", "not_when", "strictness", "wiggle", "cost") if getattr(rule, f) == UNSTATED],
            "confidence": confidence(rule.source, reg), "applied_by": list(rule.applied_by), "source": rule.source,
            "cite": shortest_key(rule.source, reg)}


def shortest_key(key: str, reg) -> str:
    """The shortest id or alias of a record, the one a card prints (``cnck-2026`` for cnckitchen-heat-set-hole-size)."""
    if key.startswith("dataset:") or key not in reg:
        return key
    ref = reg.resolve(key)
    return min([ref.id] + [a for a in ref.get("aliases") or [] if isinstance(a, str)], key=lambda k: (len(k), k))


def render_line(ln: Mapping[str, Any]) -> str:
    """A card line as text, three short lines: the rule and its numbers, how strict and how sure, and its source;
    when and when not (and what instead); its wiggle room, cost and what applies it. ``?`` marks what no source
    says."""
    strict = {"non-negotiable": "MUST", "guideline": "guide", "unstated": "", "": ""}[ln["strictness"]]
    src = _tag(ln["cite"]) if not ln["source"].startswith("dataset:") else ln["source"]
    head = f"- {ln['rule']}: {ln['quantity']}: {ln['numbers']} | " + " ".join(x for x in (strict, f"conf {ln['confidence']}", src) if x)
    when = f"  when {ln['when']}" if ln["when"] != UNSTATED else "  when ?"
    if ln["not_when"] and ln["not_when"] != UNSTATED:
        when += f"; not: {ln['not_when']}" + (f" -> {', '.join(ln['instead'])}" if ln["instead"] else "")
    tail = [ln["wiggle"] if ln["wiggle"] != UNSTATED else "",
            f"cost: {ln['cost']}" if ln["cost"] and ln["cost"] != UNSTATED else "",
            ("by " + ", ".join(_short(n) for n in ln["applied_by"])) if ln["applied_by"] else "",
            ("? " + ", ".join(f.replace("_", "-") for f in ln["unstated"])) if ln["unstated"] else ""]
    tail = [t for t in tail if t]
    return "\n".join([head, when] + (["  " + "; ".join(tail)] if tail else []))


def card(name: str, process: Optional[str] = None, material: Optional[str] = None, path: Any = None) -> Dict[str, Any]:
    """The rule card for a feature or a named card: every verified, generic rule it gathers, as :func:`line` data,
    ordered non-negotiable first, then enforced (``applied_by``), then the rest in file order. ``process`` keeps one
    process's rules; ``material`` leaves out rules written for other material families. Raises CardError for an
    unknown card, process or material, and for a rule that is not cited by a read record."""
    names = card_names(path)
    if name not in names:
        import difflib
        near = difflib.get_close_matches(name, list(names), n=3)
        raise CardError(f"no card {name!r}" + (f"; did you mean {', '.join(near)}?" if near else "") +
                        f" (cards: {', '.join(names)})")
    profiles = pp.load(path)
    if process is not None and process not in profiles.profiles:
        raise CardError(f"no process {process!r}; there are {', '.join(profiles.profiles)}")
    if material is not None:
        if process is not None:
            material_family(process, material)              # an unknown material is refused, not ignored
        elif not any(_known(p, material) for p in ("fdm", "sheet-metal")):
            material_family("fdm", material)
    reg = registry(path)
    datasets = [d["id"] for d in data(path).get("datasets") or []]
    picked, unverified, other = [], [], []
    for i, r in enumerate(_rules(path)):
        if not (r.feature == name or name in r.cards) or r.shop or (process and r.process != process):
            continue
        if not r.verified:
            unverified.append(r.id)
            continue
        fam = material_family(r.process, material) if _known(r.process, material) else "?"
        if material is not None and r.process in ("fdm", "sheet-metal") and fam == "?":
            other.append(r.id)                              # a rule of a process this material is not made in
            continue
        if fam is not None and r.materials and fam not in r.materials:
            other.append(r.id)
            continue
        bad = rule_problems(r, reg, datasets)
        if bad:
            raise CardError("refused, not cited by a read source: " + "; ".join(bad))
        picked.append((_RANK[r.strictness] - (1 if r.applied_by and r.strictness != "non-negotiable" else 0), i, r))
    picked.sort(key=lambda t: t[:2])
    return {"card": name, "title": names[name], "process": process, "material": material,
            "family": material_family(process, material) if process and material else None,
            "lines": [line(r, reg) for _, _, r in picked], "unverified_left_out": unverified,
            "other_materials_left_out": other}


def _ids(ids: Sequence[str], limit: int = MORE_IDS) -> str:
    """Left-out ids for a closing line, at most ``limit`` bytes of them, then how many others."""
    out: List[str] = []
    for i, k in enumerate(ids):
        if len(", ".join(out + [k]).encode()) > limit:
            return ", ".join(out) + f" and {len(ids) - i} others"
        out.append(k)
    return ", ".join(out)


def _fit(head: List[str], body: List[Tuple[str, str]], budget: int, more: str) -> Tuple[str, int]:
    """``head`` and as many ``body`` blocks (id, text) as fit ``budget`` bytes, then one line naming the rest; and
    how many blocks were kept."""
    out, size = list(head), sum(len(h.encode()) + 1 for h in head)
    limit = max(0, min(MORE_IDS, budget - size - len(more.format(n=999, ids=" and 999 others").encode()) - 1))
    left = list(body)
    while left:
        text = left[0][1]
        rest = [i for i, _ in left[1:]]
        reserve = len(more.format(n=len(rest), ids=_ids(rest, limit)).encode()) + 1 if rest else 0
        if size + len(text.encode()) + 1 + reserve > budget:
            break
        out.append(text)
        size += len(text.encode()) + 1
        left.pop(0)
    if left:
        out.append(more.format(n=len(left), ids=_ids([i for i, _ in left], limit)))
    return "\n".join(out), len(body) - len(left)


MORE = "  +{n} more (narrow with --process or --material; --why <rule> expands one): {ids}"


def render_card(c: Mapping[str, Any], budget: int = CARD_BYTES) -> str:
    """The card as text, within ``budget`` bytes."""
    return _render_card(c, budget)[0]


def card_json(c: Mapping[str, Any], budget: int = CARD_BYTES) -> Dict[str, Any]:
    """The card for ``--json``: the lines the text keeps, and the ids of the rest under ``more``."""
    kept = _render_card(c, budget)[1]
    while True:              # its keys cost bytes the text does not, so a line more may go
        out = dict(c, lines=list(c["lines"][:kept]), more=[ln["rule"] for ln in c["lines"][kept:]])
        if kept == 0 or len(as_json(out).encode()) <= JSON_BYTES:
            return out
        kept -= 1


def _render_card(c: Mapping[str, Any], budget: int) -> Tuple[str, int]:
    where = " | ".join(x for x in (c["process"] or "every process", c["material"]) if x)
    n = len(c["lines"])
    head = [f"rules {c['card']}: {c['title']} | {where} | {n} rule{'s' if n != 1 else ''} "
            "(MUST: non-negotiable; guide: has wiggle room; ?: no source says)"]
    if not c["lines"]:
        head.append("  no verified rule for this card here")
    left = c["unverified_left_out"] + c["other_materials_left_out"]
    tail = f"  left out: {len(c['unverified_left_out'])} unverified, {len(c['other_materials_left_out'])} for " \
           f"other materials" if left else ""
    text, kept = _fit(head, [(ln["rule"], render_line(ln)) for ln in c["lines"]],
                      budget - (len(tail.encode()) + 1 if tail else 0), MORE)
    return text + ("\n" + tail if tail else ""), kept


def why(rule_id: str, path: Any = None, budget: int = CARD_BYTES) -> Dict[str, Any]:
    """One rule expanded to its sources: the rule, its note, the source's citation and evidence, the claims read
    in it, and every other record whose ``rules`` names this rule. Refused like a card line if not cited."""
    rules = {r.id: r for r in _rules(path)}
    if rule_id not in rules:
        import difflib
        near = difflib.get_close_matches(rule_id, list(rules), n=3)
        raise CardError(f"no rule {rule_id!r}" + (f"; did you mean {', '.join(near)}?" if near else ""))
    r, reg = rules[rule_id], registry(path)
    bad = rule_problems(r, reg, [d["id"] for d in data(path).get("datasets") or []])
    if bad:
        raise CardError("refused, not cited by a read source: " + "; ".join(bad))
    out = dict(line(r, reg), applies=r.applies, note=r.note, status=r.status, verified=r.verified_on, sources=[])
    keys = [r.source] if not r.source.startswith("dataset:") else []
    keys += [k for f in WHEN_FIELDS for k in REF.findall(getattr(r, f)) if k not in keys]
    keys += [ref.id for ref in reg.entries.values() if rule_id in (ref.get("rules") or []) and ref.id not in keys]
    for k in keys:
        ref = reg.resolve(k)
        claims = [f"{c.get('text')} ({c.get('status')})" for c in ref.get("claims") or [] if isinstance(c, dict)]
        out["sources"].append({"id": ref.id, "citation": ref.citation(), "evidence": ref.evidence_class,
                               "confidence": confidence(ref.id, reg), "claims": claims})
    return out


def why_json(w: Mapping[str, Any], budget: int = JSON_BYTES) -> Dict[str, Any]:
    """:func:`why` for ``--json``, within ``budget`` bytes: claims, then whole sources, are dropped from the end (the
    rule's own source last) and named under ``more``."""
    out = json.loads(as_json(w))
    out["more"] = []
    while len(as_json(out).encode()) > budget:
        srcs = out["sources"]
        last = srcs[-1] if srcs else None
        if last is None:
            break
        if last["claims"]:
            last["claims"].pop()
            if not out["more"] or out["more"][-1] != f"{last['id']} claims":
                out["more"].append(f"{last['id']} claims")
        elif len(srcs) > 1:
            gone = srcs.pop()["id"]
            out["more"] = [m for m in out["more"] if m != f"{gone} claims"] + [gone]
        else:
            break
    return out


def render_why(w: Mapping[str, Any], budget: int = CARD_BYTES) -> str:
    head = [render_line(w), f"  applies: {w['applies']}", f"  read {w['verified']}" +
            (f"; note: {w['note']}" if w["note"] else "")]
    body = []
    for s in w["sources"]:
        text = f"{_tag(s['id'])} {s['evidence']}, conf {s['confidence']}: {s['citation']}"
        body.append((s["id"], text))
        body += [(s["id"] + " claim", f"  claim: {c}") for c in s["claims"]]
    return _fit(head, body, budget, "+{n} more (--json lists every source)")[0]


# ----------------------------------------------------------------------------- decision cards

FACTS: Dict[str, Any] = {}          # fact name -> function, filled by @_fact


def _fact(fn):
    FACTS[fn.__name__] = fn
    return fn


@_fact
def insert_for_load(process: str, material: Optional[str], load: float) -> Dict[str, Any]:
    """Whether a catalogued heat-set insert carries ``load`` (N) in ``material``: the smallest insert of
    :data:`cadagent.mechanical.inserts.INSERTS` whose low-band pull-out (:func:`cadagent.mechanical.inserts.capacity`),
    over the kit's margin :data:`cadagent.mechanical.inserts.MARGIN`, is at least the load, in the weakest data sheet
    of the material's family. ``fits`` is None where no calibrated model is (a process other than fdm, or no
    material), so no condition matches it and the card says why."""
    if process != "fdm" or material is None:
        why = ("no material given: give --material for the insert's capacity" if process == "fdm" else
               f"no capacity model for {process}: the insert model is calibrated on FDM prints only; size the joint "
               f"from a test or a cited source for {process} and record it as a decision")
        return {"fits": None, "why": why}
    from cadagent.mechanical import inserts
    fam = material_family("fdm", material)
    keys = [material] if material in pp.FDM_MATERIALS else \
        sorted(k for k, (f, _) in pp.FDM_MATERIALS.items() if f == fam)
    best = None
    for ins in sorted(inserts.INSERTS.values(), key=lambda i: (i.diameter_mm, i.length_mm)):
        low = min((inserts.capacity(ins, k)["pull_out"]["low"], k) for k in keys)
        allowed = low[0] / inserts.MARGIN
        best = (ins, low, allowed)
        if allowed >= load:
            break
    ins, (pull, key), allowed = best
    conf = inserts.capacity(ins, key)["confidence"].split(":")[0]
    what = (f"{ins.thread} x {ins.length_mm:g} insert ({ins.maker} {ins.part}): pull-out {pull:.0f} N low band in "
            f"{key}, the weakest {fam} sheet, over margin {inserts.MARGIN:g} = {allowed:.0f} N")
    fits = allowed >= load
    return {"fits": fits, "insert": ins.key, "pull_n": round(pull), "allowed_n": round(allowed), "material_key": key,
            "why": (f"{what} >= {load:g} N (model confidence {conf})" if fits else
                    f"the largest catalogued, {what} < {load:g} N (model confidence {conf})")}


def decisions(path: Any = None) -> Dict[str, Dict[str, Any]]:
    return {d["id"]: d for d in data(path).get("decisions") or []}


def _conds(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return row.get("if") or {}


def decision_problems(dec: Mapping[str, Any], reg, card_list: Sequence[str], rule_ids: Sequence[str]) -> List[str]:
    """Every way a decision table is malformed or uncited (the profiles check and ``references --check`` run it)."""
    did = dec.get("id", "?")
    out: List[str] = []
    inputs, facts, options = dec.get("inputs") or {}, dec.get("facts") or {}, dec.get("options") or {}
    rows, unused = dec.get("rows") or [], dec.get("unused") or {}

    def cited(text: str, where: str) -> None:
        for key in REF.findall(text):
            why = _read_problem(key, reg)
            if why:
                out.append(f"{did}: {where} cites {why}")

    for name, spec in inputs.items():
        if spec.get("required") and "default" in spec:
            out.append(f"{did}: input {name} is required and has a default; give one or the other")

    def names_ok(text: str, where: str) -> None:
        for n in FACT.findall(text):
            head, _, field = n.partition(".")
            if not (head in facts if field else (n in inputs or n in facts)):
                out.append(f"{did}: {where} fills {{{n}}}, which is not an input, a fact or a fact's field")

    for name, f in facts.items():
        by = str(f.get("by", ""))
        if by != f"{__name__}.{by.rsplit('.', 1)[-1]}" or by.rsplit(".", 1)[-1] not in FACTS:
            out.append(f"{did}: fact {name}: `by` {by!r} is not a fact function of {__name__}")
        out += [f"{did}: fact {name} reads {i!r}, not an input" for i in f.get("from") or [] if i not in inputs]
    for oid, o in options.items():
        out += [f"{did}: option {oid} links card {c!r}, which is not a card" for c in o.get("cards") or []
                if c not in card_list]
    for k, why_unused in unused.items():
        if k not in inputs:
            out.append(f"{did}: unused names {k!r}, not an input")
        cited(str(why_unused), f"unused.{k}")
    read = {k for row in rows for k in _conds(row)} | {i for f in facts.values() for i in f.get("from") or []}
    out += [f"{did}: input {k} is read by no row or fact; list it under `unused` with why" for k in inputs
            if k not in read and k not in unused]
    out += [f"{did}: input {k} is listed unused but a row or fact reads it" for k in unused if k in read]
    used_options = set()
    for i, row in enumerate(rows):
        rid = row.get("id", f"row {i}")
        conds = _conds(row)
        if (i == len(rows) - 1) == bool(conds):
            out.append(f"{did}: {rid}: " + ("the last row has no `if` (it catches every case)" if conds else
                                             "only the last row may have no `if`"))
        for k, v in conds.items():
            if k in facts:
                if not isinstance(v, bool):
                    out.append(f"{did}: {rid}: fact {k} is matched with true or false")
            elif k not in inputs:
                out.append(f"{did}: {rid}: if names {k!r}, not an input or a fact")
            elif "choices" in inputs[k]:
                if not (isinstance(v, list) and set(v) <= set(inputs[k]["choices"])):
                    out.append(f"{did}: {rid}: {k} must be a list of {inputs[k]['choices']}")
            elif not (isinstance(v, dict) and v and set(v) <= {"min", "max"}):
                out.append(f"{did}: {rid}: {k} takes {{min, max}}")
        for key in ("choose", "runner_up"):
            if row.get(key) not in options:
                out.append(f"{did}: {rid}: {key} {row.get(key)!r} is not an option")
            used_options.add(row.get(key))
        if row.get("choose") == row.get("runner_up"):
            out.append(f"{did}: {rid}: the runner-up is the choice")
        because = row.get("because") or []
        if not because:
            out.append(f"{did}: {rid}: no `because`: a choice says why")
        for j, b in enumerate(because):
            b = str(b)
            facts_named = FACT.findall(b)
            names_ok(b, f"{rid}.because[{j}]")
            if not REF.search(b) and not (facts_named and row.get("by")):
                out.append(f"{did}: {rid}: because[{j}] is uncited: give a [ref:<id>] or fill a computed fact with "
                           "`by` naming the function")
            cited(b, f"{rid}.because[{j}]")
        wins = str(row.get("wins_when") or "")
        if not wins:
            out.append(f"{did}: {rid}: no `wins_when`: say when the runner-up wins, or `unstated` with a gap")
        elif wins == UNSTATED and not row.get("gap"):
            out.append(f"{did}: {rid}: wins_when is unstated, so the row needs a `gap` saying no source covers it")
        elif wins != UNSTATED and not (REF.search(wins) or COMMAND.search(wins) or row.get("by")):
            out.append(f"{did}: {rid}: wins_when is uncited: give a [ref:<id>], a `cad-agent` command or `by`")
        cited(wins, f"{rid}.wins_when")
        cited(str(row.get("gap") or ""), f"{rid}.gap")
        names_ok(wins, f"{rid}.wins_when")
        names_ok(str(row.get("gap") or ""), f"{rid}.gap")
        out += [f"{did}: {rid}: needs {k!r}, which is not a fact" for k in row.get("needs") or [] if k not in facts]
        for rule in row.get("rules") or []:
            if rule not in rule_ids:
                out.append(f"{did}: {rid}: rule {rule!r} is not a rule id")
    out += [f"{did}: option {o} is never chosen nor runner-up" for o in options if o not in used_options]
    return out


def problems(path: Any = None, reg=None) -> List[str]:
    """Every problem with the cards and decisions of the profile file: the when-fields of each rule (strictness
    words, ``instead`` and ``cards`` names, material families, [ref:<id>] tags to read records) and each decision table
    (:func:`decision_problems`). The process-profiles tests and ``python -m cadagent.review.references --check`` run it."""
    reg = reg if reg is not None else registry(path)
    d = data(path)
    named = d.get("cards") or {}
    rules = _rules(path)
    ids = {r.id for r in rules}
    cards_all = set(named) | {r.feature for r in rules}
    fdm_families = {fam for fam, _ in pp.FDM_MATERIALS.values()}
    out = [f"cards: {n!r} is not a kebab-case name" for n in named if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", n)]
    out += [f"cards: {n} gathers no rule" for n in named if not any(n in r.cards for r in rules)]
    for r in rules:
        if r.strictness and r.strictness not in STRICTNESS:
            out.append(f"{r.id}: strictness {r.strictness!r} is not one of {', '.join(STRICTNESS)}")
        if r.strictness and not r.wiggle and r.strictness != UNSTATED:
            out.append(f"{r.id}: a {r.strictness} rule says its wiggle room (or `unstated`)")
        out += [f"{r.id}: instead {x!r} is not a rule id or a card" for x in r.instead if x not in ids | cards_all]
        out += [f"{r.id}: cards {x!r} is not in `cards`" for x in r.cards if x not in named]
        known = fdm_families if r.process == "fdm" else set(pp.SHEET_MATERIALS) if r.process == "sheet-metal" else None
        out += [f"{r.id}: materials {m!r} is not a {r.process} material family" for m in r.materials
                if known is not None and m not in known]
        if any(getattr(r, f) for f in ("when", "not_when", "strictness", "wiggle", "cost")) or r.cards:
            out += rule_problems(r, reg, [x["id"] for x in d.get("datasets") or []])
    for dec in d.get("decisions") or []:
        out += decision_problems(dec, reg, sorted(cards_all), sorted(ids))
    return out


def _holds(cond: Any, value: Any) -> bool:
    if isinstance(cond, bool):
        return value is cond
    if isinstance(cond, list):
        return value in cond
    return value is not None and cond.get("min", value) <= value <= cond.get("max", value)


def _reads(row: Mapping[str, Any], facts: Mapping[str, Any]) -> set:
    """The facts a row reads: in its ``if``, its ``needs`` or the text it fills."""
    texts = [str(t) for t in (row.get("because") or [])] + [str(row.get("wins_when") or ""), str(row.get("gap") or "")]
    named = {n.partition(".")[0] for t in texts for n in FACT.findall(t)}
    return {k for k in set(_conds(row)) | set(row.get("needs") or []) | named if k in facts}


def _option_cards(options: Mapping[str, Any], oid: str, env: Mapping[str, Any], path: Any) -> Tuple[List[str], List[str]]:
    """The ``cad-agent`` commands an option relies on, and the names of its cards that hold no verified rule for the
    process and material (so the card says so rather than send an agent to an empty card)."""
    flags = " ".join(f"--{k} {env[k]}" for k in ("process", "material") if env.get(k) is not None)
    run, empty = [], []
    procs = pp.load(path).profiles
    for c in options[oid].get("cards") or []:
        proc = env.get("process")
        has = proc in procs if proc else True
        if has:
            has = bool(card(c, process=proc, material=env.get("material"), path=path)["lines"])
        (run if has else empty).append(f"cad-agent rules {c} {flags}".strip() if has else c)
    if options[oid].get("check"):
        run.append(f"cad-agent {options[oid]['check']}")
    return run, empty


def choose(decision: str, path: Any = None, **given: Any) -> Dict[str, Any]:
    """Evaluate a decision table: the choice, the deciding reasons, the runner-up and when it would win, the gaps,
    and the rule cards it relies on. ``given`` holds the inputs (``load=200, cycles=50, material="petg"``); a missing
    one takes its default, and a missing required one is refused. When the row reached ``needs`` a fact that is not
    computed here (``None``), the result is **not decided** (``decided`` false, ``choice`` None) and ``missing`` says
    why, rather than a choice made without the check. Numeric inputs must be finite and nonnegative. Raises
    CardError for an unknown decision or invalid input, and for a table that is not cited."""
    tables = decisions(path)
    if decision not in tables:
        raise CardError(f"no decision {decision!r}; there are {', '.join(tables) or 'none'}")
    dec, reg = tables[decision], registry(path)
    bad = decision_problems(dec, reg, list(card_names(path)), [r.id for r in _rules(path)])
    if bad:
        raise CardError("refused, the decision table is not cited: " + "; ".join(bad))
    inputs = dec.get("inputs") or {}
    stray = sorted(set(given) - set(inputs))
    if stray:
        raise CardError(f"{decision} takes {', '.join(inputs)}, not {', '.join(stray)}")
    env: Dict[str, Any] = {}
    for k, spec in inputs.items():
        v = given.get(k)
        v = spec.get("default") if v is None else v
        if v is None and spec.get("required"):
            raise CardError(f"{decision} needs {k} (--{k}"
                            + (f", {spec['units']}" if spec.get("units") else "") + f"): {spec.get('help', '')}")
        if "choices" in spec and v not in spec["choices"]:
            raise CardError(f"{decision}: {k} {v!r} is not covered; the table covers {', '.join(spec['choices'])}")
        if "units" in spec and v is not None:
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or (isinstance(v, float) and not math.isfinite(v)) or v < 0):
                raise CardError(f"{decision}: {k} must be a finite number of at least 0, not {v!r}")
        env[k] = v
    if env.get("process") and env.get("material") is not None:
        material_family(env["process"], env["material"])            # refuse an unknown material early
    facts = dec.get("facts") or {}
    computed: Dict[str, Any] = {}
    detail: Dict[str, Dict[str, Any]] = {}     # each fact's other fields, keyed by the full fact name
    for name, f in facts.items():
        res = FACTS[f["by"].rsplit(".", 1)[-1]](**{i: env[i] for i in f.get("from") or []})
        computed[name] = res["fits"] if isinstance(res, dict) and "fits" in res else res
        if isinstance(res, dict):
            detail[name] = {k: v for k, v in res.items() if k != "fits"}
    values = {**env, **computed, **{f"{n}.{k}": v for n, d in detail.items() for k, v in d.items()}}
    rows = dec["rows"]
    at = next(i for i, r in enumerate(rows) if all(_holds(c, values.get(k)) for k, c in _conds(r).items()))
    row = rows[at]
    fill = lambda s: " ".join(FACT.sub(lambda m: _num(values[m.group(1)]) if m.group(1) in values else m.group(0),  # noqa: E731
                                       str(s)).split())
    missing = {k: fill(detail.get(k, {}).get("why") or "not computed here")
               for k in row.get("needs") or [] if computed.get(k) is None}
    read = set().union(*(_reads(r, facts) for r in rows[:at + 1]))
    gaps = [fill(row["gap"])] if row.get("gap") and not missing else []
    gaps += [f"{name} not computed: " + fill(detail.get(name, {}).get("why") or "")
             for name in computed if computed[name] is None and name in read and name not in missing]
    out: Dict[str, Any] = {"schema": DECISION_SCHEMA, "decision": decision, "inputs": env, "facts": computed,
                           "detail": detail, "row": row["id"], "decided": not missing, "missing": missing,
                           "gaps": gaps, "unused": {k: fill(v) for k, v in (dec.get("unused") or {}).items()}}
    if missing:
        return dict(out, choice=None, choice_name=None)
    options = dec["options"]
    cards_run, cards_empty = _option_cards(options, row["choose"], env, path)
    ru_run, ru_empty = _option_cards(options, row["runner_up"], env, path)
    return dict(out, choice=row["choose"], choice_name=options[row["choose"]]["name"],
                because=[fill(b) for b in row["because"]], rules=list(row.get("rules") or []),
                by=list(row.get("by") or []), runner_up=row["runner_up"],
                runner_up_name=options[row["runner_up"]]["name"], wins_when=fill(row["wins_when"]),
                cards=cards_run, cards_empty=cards_empty, runner_up_cards=ru_run, runner_up_cards_empty=ru_empty)


def render_choice(c: Mapping[str, Any], budget: int = CARD_BYTES) -> str:
    """The decision card as text, within ``budget`` bytes."""
    inp = ", ".join(f"{k} {v}" for k, v in c["inputs"].items() if v is not None)
    head = [f"choose {c['decision']} | {inp}"]
    proc = c["inputs"].get("process")
    if not c["decided"]:
        head.append(f"choice: not decided (row {c['row']} needs {', '.join(c['missing'])}, which is not computed "
                    "here; the table does not choose without that check)")
        body = [(f"missing {k}", f"missing: {k}: {why}") for k, why in c["missing"].items()]
    else:
        head += [f"choice: {c['choice_name']} (row {c['row']})", "because:"]
        body = [(f"because {i}", f"- {b}") for i, b in enumerate(c["because"])]
        if c["rules"]:
            body.append(("rules", "  rules: " + ", ".join(c["rules"])))
        if c["by"]:
            body.append(("by", "  computed by: " + ", ".join(c["by"])))
        body.append(("runner-up", f"runner-up: {c['runner_up_name']}; wins when: {_q(c['wins_when'])}"))
    body += [(f"gap {i}", f"gap: {g}") for i, g in enumerate(c["gaps"])]
    body += [(f"unused {k}", f"unused: {k}: {v}") for k, v in c["unused"].items()]
    if c["decided"]:
        for key, label in (("cards", "cards"), ("runner_up_cards", "runner-up cards")):
            parts = list(c[key])
            if c[key + "_empty"]:
                parts.append(", ".join(c[key + "_empty"]) + f": no verified rule for {proc} yet")
            body.append((label, f"{label}: " + ("; ".join(parts) or "none")))
    return _fit(head, body, budget, "+{n} more (--json has them): {ids}")[0]


def as_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
