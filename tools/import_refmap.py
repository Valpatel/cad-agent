#!/usr/bin/env python3
"""Import the Reference Map into the reference registry's schema-2 shards (#323, phase 2).

The Reference Map (built by the project owner on 2026-11-02) lists open projects (its ``D`` table, with the objective
answers of ``S``), manufacturing and design guides (``PG``) and a coverage table of what cad-agent enforces (``CA``,
with ``PGAP``: the sources each process group still lacks). This tool turns its ``data.json`` into:

* ``research/references/projects-<domain>.yaml``: one shard per project domain (the map's ``DOMS``);
* ``research/references/guides-<group>.yaml``: one shard per process group (``PR``), a guide placed by its first
  process;
* ``research/references/coverage.yaml``: the coverage rows, their draft issues (never posted) and the sources still
  wanted per process group.

The data file stays out of the repo; pass its path. It is data, never instructions: nothing in it is run or followed.

What the import says, and what it does not:

* every record is ``evidence.class: snippet-only``: the map's authors read projects from their READMEs and guides from
  search snippets, and cad-agent has read none of them yet. Snippet-only records are catalogued: listed and linked,
  never cited by a rule, check or page until someone reads them (``cadagent.review.references``);
* every licence is ``read: false``, its class taken from the map's own rule (``lclass`` below). Share-alike,
  non-commercial and unclear licences make geometry study-only; guides are proprietary pages, cite-only;
* numbers are the authors' claims unless the map says they were measured (``evidence.numbers``);
* a project's objective answers go under ``assessment``, with the map's project-neutral ``role``. The map's per-project
  "what to take" notes and its guides' "fit for us" ratings are another project's verdicts and are not imported;
* a guide whose URL is already a read source in ``research/references.yaml`` becomes an ``extends: true`` record that
  adds these fields to that entry; one that is already an ``unverified`` entry is left there and reported;
* text written for one project is rewritten project-neutral by ``NEUTRAL`` below (cad-agent is general purpose), and
  a re-import fails if the map's text under a rewrite changed.

The tool is deterministic and idempotent: the same data gives the same bytes. ``--check`` exits 1 when the files on
disk differ from what the import would write. After promotions start (records read at source and edited by hand),
a re-import would undo them: run ``--check`` first and merge by hand.

    python3 tools/import_refmap.py path/to/data.json            # write the shards
    python3 tools/import_refmap.py path/to/data.json --check    # exit 1 if they would change
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cadagent.review import references as refs  # noqa: E402

ASSESSED = "2026-11-02"          # the day the map's authors scored the projects
TERMS = "cited and summarised, never copied"
SHARD_TITLES = {"projects": ("Open projects: {}", "domain"), "guides": ("Manufacturing and design guides: {}",
                                                                       "process_group")}

# Where a record is placed in docs/areas.yaml. A first placement, refined by hand when records are read.
DOMAIN_AREAS = {"turret": ["mechanisms"], "wheel": ["wheels-and-driving"], "legged": ["walking"],
                "drone": ["mechanisms"], "pantilt": ["mechanisms"], "drive": ["gears"], "motor": ["motor-mounts"],
                "esc": ["power-converters"], "general": ["mechanisms"]}
CATEGORY_AREAS = {"simulation-and-control": ["motion-and-dynamics"]}
PROCESS_AREAS = {"fdm": "fdm", "sla": "resin-and-powder", "sls": "resin-and-powder", "mjf": "resin-and-powder",
                 "metal-am": "3d-printing", "sheet": "sheet-metal", "bending": "sheet-metal", "laser": "laser-cutting",
                 "waterjet": "laser-cutting", "cnc-mill": "cnc-machining", "cnc-turn": "cnc-machining",
                 "injection": "moulded-part-design", "casting": "mould-making", "urethane": "urethane-casting",
                 "snap-fit": "snap-fits", "inserts": "threaded-inserts", "fasteners": "fasteners",
                 "joining": "fasteners-and-hardware", "pcb": "circuit-boards", "general": "design-process"}
GROUP_AREAS = {"print": ["3d-printing"], "sheet": ["sheet-metal", "laser-cutting"], "cnc": ["cnc-machining"],
               "mould": ["mould-design", "mould-making"], "inserts": ["fasteners-and-hardware"],
               "pcb": ["circuit-boards"], "winding": ["motor-mounts"], "general": ["design-process"]}
# The coverage rows, by the number that starts their topic.
COVERAGE_AREAS = {"1": ["threaded-inserts"], "2": ["screw-bosses"], "3": ["3d-printing"], "4": ["fdm"],
                  "5": ["sheet-metal"], "6": ["laser-cutting"], "7": ["clinch-fasteners", "clinch-hardware"],
                  "8": ["snap-fits", "living-hinges"], "9": ["moulded-part-design"], "10": ["cnc-machining"],
                  "11a": ["joints-and-bearings", "rolling-bearings"], "11b": ["design-process"],
                  "12": ["design-process"], "13": ["circuit-boards"], "14": ["3d-printing"],
                  "15": ["review-and-evidence"]}
# A non-project row's kind, from the licence column, where the map writes what the source is instead.
KIND_HINTS = {"paper": "paper", "thesis": "paper", "whitepaper": "paper", "article": "article", "blog": "article",
              "log": "article", "forum": "forum-thread", "talk": "video", "guide": "guide", "docs": "guide",
              "vendor guide": "guide", "patent": "patent"}
GUIDE_KINDS = {"standard": "standard", "academic": "paper"}       # by the map's publisher type; else guide
CATEGORY_CODES = None            # filled from vocab.yaml: map letter -> category slug
NUMBERS = {"yes": "claimed", "some": "some", "no": "none", "unknown": "unknown",       # a guide's `numbers`
           "none": "none", "claimed": "claimed", "measured": "measured", "C": "claimed", "M": "measured", "": "unknown"}
SPDX = re.compile(r"^(MIT|Apache-2\.0|BSD-[23]-Clause|GPL-[23]\.0|AGPL-3\.0|LGPL-[23]\.[01]|CC0-1\.0|CC-BY(-SA)?-4\.0|"
                  r"CERN-OHL-[SWP]-2\.0|Unlicense)$")
# Guides whose licence the core registry already states (its `terms`); the map gives none for guides.
LICENCE_OVERRIDES = {
    "https://github.com/shaise/FreeCAD_SheetMetal": ("LGPL-2.1-only", "share-alike",
                                                     "LGPL-2.1, as research/references.yaml states; text not read"),
    "https://github.com/shaise/FreeCAD_FastenersWB": ("GPL-2.0-or-later", "share-alike",
                                                      "GPL-2.0-or-later, as research/references.yaml states; text "
                                                      "not read")}
# Text the map wrote for one project, made project-neutral: verdicts against that project's target ("off-target for a
# balancing robot") or its chosen motor ("far below RS-04"). Facts about what a project uses stay. Keyed by (table,
# row, field): (the map's text, ours). A key whose text no longer matches stops the import, so a changed row is looked
# at again.
NEUTRAL: Dict[Tuple[str, str, str], Tuple[str, str]] = {
    ("D", "115", "note"): ("Includes a torque test stand (Arduino and Python); no results published. Reusable for our "
                           "own tests.",
                           "Includes a torque test stand (Arduino and Python); no results published. The stand is "
                           "reusable for other actuator tests."),
    ("D", "158", "note"): ("Python SDK for RobStride actuators, relevant to our RS-04. Software only.",
                           "Python SDK for RobStride actuators. Software only."),
    ("S", "39", "caveat"): ("No speed or flight numbers in README; NonCommercial licence; drone is off-target.",
                             "No speed or flight numbers in README; NonCommercial licence."),
    ("S", "41", "caveat"): ("Drone frame; off-target for a wheel-legged robot.",
                             "Drone frame."),
    ("S", "42", "caveat"): ("Carbon frame and 12s parts; off-target, and cost is only implied.",
                             "Carbon frame and 12s parts; cost is only implied."),
    ("S", "52", "caveat"): ("Racing quad frame; off-target for a balancing robot.",
                             "Racing quad frame."),
    ("S", "53", "caveat"): ("Giant racing frame; off-target.",
                             "Giant racing frame."),
    ("S", "54", "caveat"): ("Micro racing frame; off-target.",
                             "Micro racing frame."),
    ("S", "55", "caveat"): ("Weights are estimates; micro drone frame; off-target.",
                             "Weights are estimates; micro drone frame."),
    ("S", "56", "caveat"): ("Off-target drone frame; carbon plates are the main structure, prints are accessories only.",
                             "Drone frame; carbon plates are the main structure, prints are accessories only."),
    ("S", "71", "caveat"): ("Spring dart blaster, off-target for a balancing robot; CC BY-NC-SA licence.",
                             "Spring dart blaster; CC BY-NC-SA licence."),
    ("S", "135", "caveat"): ("Belt module is lower torque than RS-04; README itself gives no numbers.",
                             "Belt module; README itself gives no torque numbers."),
    ("S", "158", "caveat"): ("Software only, last pushed July 2024; no mention of RS-04 specifically.",
                             "Software only, last pushed July 2024."),
    ("S", "204", "caveat"): ("Hobby servos are far weaker than RS-04; useful for BOM and assembly style, not actuation.",
                             "Hobby servos; useful for BOM and assembly style, not for high-torque actuation."),
    ("S", "206", "caveat"): ("Desktop arm, off-target for balancing; README gives no accuracy or payload numbers.",
                             "Desktop arm; README gives no accuracy or payload numbers."),
    ("S", "215", "caveat"): ("Unitree A1 and DJI 3508 actuators with serial or CAN links, not an RS-04 class design.",
                             "Unitree A1 and DJI 3508 actuators with serial or CAN links."),
    ("S", "268", "caveat"): ("Actuators are 2.5 N.m rated class, far below RS-04; no measured torque or gait data.",
                             "Actuators are 2.5 N.m rated class; no measured torque or gait data."),
    ("S", "322", "caveat"): ("Licence is CC BY-NC-SA; CLN17 handles only 4.5A peak, far below an RS-04.",
                             "Licence is CC BY-NC-SA; CLN17 handles only 4.5 A peak."),
    ("S", "325", "caveat"): ("Tiny low-voltage board (2-5.5 V, 2 A); far below RS-04 power class.",
                             "Tiny low-voltage board (2-5.5 V, 2 A)."),
    ("S", "351", "caveat"): ("README missing; off-target to drivers; only our note describes it.",
                             "README missing; listed with drivers but does not fit that category; only the summary describes it."),
    ("S", "40", "caveat"): ("Frame is carbon cut, not printed; drone-specific and far from our robot.",
                            "Frame is carbon cut, not printed; drone-specific."),
    ("S", "222", "caveat"): ("Balances only for a few seconds; servo legs and stepper wheels, not Gyropup class.",
                             "Balances only for a few seconds; servo legs and stepper wheels."),
    ("S", "244", "caveat"): ("Hobby servos and L298N are far from Gyropup's actuators; no balance results or numbers "
                             "given.",
                             "Hobby servos and L298N drivers; no balance results or numbers given."),
    ("S", "305", "caveat"): ("Arm for education, off-target for Gyropup; README gives no payload or accuracy numbers.",
                             "Arm for education; README gives no payload or accuracy numbers."),
    ("S", "335", "caveat"): ("Not FOC; Hall-sensor 6-step with no tests, so it contradicts our foc topic.",
                             "Not FOC; Hall-sensor 6-step with no tests, though the map tagged it FOC."),
}
OUR_NOTE = re.compile(r"\bour note\b")          # the map's one-line note is the record's summary here


# ----------------------------------------------------------------------------- small helpers

def slug(text: str, limit: int = 60) -> str:
    """Kebab-case, ASCII, cut at a word boundary within ``limit`` characters."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower().replace("&", " and ")).split()
    out = ""
    for w in words:
        if out and len(out) + 1 + len(w) > limit:
            break
        out = f"{out}-{w}" if out else w[:limit]
    return out or "record"


def clean_url(url: str) -> str:
    """The URL as a record keeps it: spaces percent-encoded (three vendor PDFs have them), nothing else changed."""
    return url.strip().replace(" ", "%20")


def norm_url(url: str) -> str:
    """A URL as compared for duplicates: no scheme, no www., no fragment, no trailing slash, lower case."""
    u = re.sub(r"^https?://(www\.)?", "", url.strip().lower())
    return u.split("#", 1)[0].rstrip("/")


def lclass(text: str) -> str:
    """The map's licence classifier, as its page has it: '' for a non-licence (a paper, a forum), else open,
    copyleft, nc or unclear."""
    if re.fullmatch(r"-?", text) or (re.search(r"paper|thesis|log|talk|article|forum|docs|blog|guide|vendor|"
                                               r"whitepaper|patent", text) and not re.search(r"GPL|MIT", text)):
        return ""
    if re.search(r"none|NOASSERTION|unverified|not seen|conflict", text, re.I):
        return "unclear"
    if re.search(r"NC", text):
        return "nc"
    if re.search(r"GPL|SA|CERN", text):
        return "copyleft"
    return "open"


def neutral(table: str, row: str, field: str, text: str) -> str:
    key = (table, row, field)
    if key in NEUTRAL:
        theirs, ours = NEUTRAL[key]
        if text != theirs:
            raise SystemExit(f"{table}[{row}].{field} changed in the map since its project-neutral rewrite: "
                             f"{text!r}; review NEUTRAL in tools/import_refmap.py")
        text = ours
    return OUR_NOTE.sub("the summary", text)


def github_owner(url: str) -> Optional[Tuple[str, str]]:
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", url)
    return (m.group(1), m.group(2).removesuffix(".git")) if m else None


class Ids:
    """Unique, stable ids: the first record to want an id gets it, later ones a numeric suffix."""

    def __init__(self, taken):
        self.taken = set(taken)

    def __call__(self, base: str) -> str:
        rid, n = base, 2
        while rid in self.taken:
            rid, n = f"{base}-{n}", n + 1
        self.taken.add(rid)
        return rid


# ----------------------------------------------------------------------------- the import

def _licence(raw: str, kind: str, cad: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    cls = {"open": "open", "copyleft": "share-alike", "nc": "non-commercial", "unclear": "unclear",
           "": "unclear"}[lclass(raw)]
    spdx = raw if SPDX.match(raw) else None
    note = f"The map states {raw!r}; the licence text was not read." if raw and raw != "-" else \
        "No licence stated in the map; the licence text was not read."
    if kind != "project" or cad == "N":
        geometry = "none"
    elif cls in ("share-alike", "non-commercial", "unclear"):
        geometry = "study-only"
    else:
        geometry = "adapt-with-attribution"
    return {"spdx": spdx, "class": cls, "read": False, "note": note}, {"text": "cite-only", "geometry": geometry}


def project_record(i: int, row: List[str], data: Dict[str, Any], vocab: Dict[str, Any], ids: Ids) -> Dict[str, Any]:
    name, url, cat, dom, lic, cad, ev, note = row
    category = CATEGORY_CODES[cat]
    gh = github_owner(url)
    kind = "project" if cat != "G" else KIND_HINTS.get(lic, "article")
    rid = ids(slug(f"{gh[0]}-{gh[1]}") if gh else slug(name, 50))
    org = gh[0] if gh else re.sub(r"^www\.", "", url.split("/")[2])
    licence, reuse = _licence(lic, kind, cad)
    s = data["S"].get(str(i))
    numbers = NUMBERS[s["evid"]] if s else NUMBERS[ev]
    areas = list(DOMAIN_AREAS[dom])
    areas += [a for a in CATEGORY_AREAS.get(category, []) if a not in areas]
    rec: Dict[str, Any] = {"id": rid, "kind": kind, "category": category, "title": name, "authors": [], "org": org,
                           "year": None, "url": clean_url(url), "access": "free", "terms": TERMS, "licence": licence,
                           "reuse": reuse, "areas": areas, "domains": [dom]}
    groups = data["PT"].get(str(i))
    if groups:
        rec["process_groups"] = list(groups)
    rec["evidence"] = {"class": "snippet-only", "numbers": numbers}
    rec["summary"] = neutral("D", str(i), "note", note)
    assessment: Dict[str, Any] = {}
    if s:
        assessment = {"built": s["built"], "supply": s["supply"], "cost": s["cost"], "make": s["make"],
                      "docs": s["docs"], "activity": s["act"], "role": s["role"]}
    if cad in vocab["cad_seen"]:
        assessment["cad"] = {"seen": cad}
    if s:
        assessment["answers"] = {k: neutral("S", str(i), f"cq.{k}", v) for k, v in s["cq"].items()}
        assessment["caveat"] = neutral("S", str(i), "caveat", s["caveat"])
        assessment["assessed"] = {"date": ASSESSED, "from": s["src"]}
    if assessment:
        rec["assessment"] = assessment
    rec["used_for"] = []
    return rec


def guide_fields(g: Dict[str, Any], vocab: Dict[str, Any]) -> Dict[str, Any]:
    """The schema-2 fields of one guide, without its id (shared by a new record and an extension)."""
    procs = [p for p in g["proc"] if p in vocab["process"]]
    groups = []
    for p in procs:
        grp = vocab["process"][p]["group"]
        if grp not in groups:
            groups.append(grp)
    areas = []
    for p in procs:
        if PROCESS_AREAS[p] not in areas:
            areas.append(PROCESS_AREAS[p])
    spdx, cls, note = LICENCE_OVERRIDES.get(g["url"], (None, "proprietary", "A publisher's page; its terms were not "
                                                                            "read. Cited, never copied."))
    claims = []
    if g.get("rule"):
        chk = g.get("chk") or {}
        claim = {"text": g["rule"], "status": chk.get("status", "unconfirmed")}
        claim["evidence"] = chk.get("evidence") or "No second source checked."
        claims.append(claim)
    summary = g["gist"] + (f" Note: {g['note']}" if g.get("note") else "")
    out: Dict[str, Any] = {"kind": GUIDE_KINDS.get(g["ptype"], "guide"), "category": "manufacturing-guides",
                           "licence": {"spdx": spdx, "class": cls, "read": False, "note": note},
                           "reuse": {"text": "cite-only", "geometry": "none"}, "areas": areas or ["design-process"],
                           "processes": procs, "process_groups": groups or ["general"],
                           "evidence": {"class": "snippet-only", "numbers": NUMBERS[g["numbers"]],
                                        "tested": g["tested"], "authority": g["authority"]}}
    if claims:
        out["claims"] = claims
    out["summary"] = summary
    return out


def guide_record(g: Dict[str, Any], vocab: Dict[str, Any], ids: Ids) -> Dict[str, Any]:
    fields = guide_fields(g, vocab)
    publisher = slug(g["publisher"].split(" (")[0])        # "Hubs (Protolabs Network)" -> hubs
    base = slug(g["title"])
    base = base if base.startswith(publisher) else slug(f"{publisher} {g['title']}")
    head = {"id": ids(base), "kind": fields.pop("kind"), "category": fields.pop("category"), "title": g["title"],
            "authors": [], "org": g["publisher"], "year": None, "url": clean_url(g["url"]), "access": "free",
            "terms": TERMS}
    return {**head, **fields, "used_for": []}


def extension(core_id: str, g: Optional[Dict[str, Any]], d_row: Optional[Tuple[int, List[str]]],
              data: Dict[str, Any], vocab: Dict[str, Any]) -> Dict[str, Any]:
    """An ``extends: true`` record adding the map's fields to a core read source (guide and/or project row)."""
    rec: Dict[str, Any] = {"id": core_id, "extends": True}
    if g is not None:
        fields = guide_fields(g, vocab)
        fields["evidence"].pop("class")          # the core entry was read: its class stays `read`
        rec.update(fields)
    if d_row is not None:
        i, row = d_row
        rec.setdefault("kind", "project" if row[2] != "G" else KIND_HINTS.get(row[4], "article"))
        rec.setdefault("category", CATEGORY_CODES[row[2]])
        rec["domains"] = [row[3]]
        if g is None:                            # a guide's process areas place it better than a project domain
            rec["areas"] = list(DOMAIN_AREAS[row[3]])
        note = neutral("D", str(i), "note", row[7])
        rec["summary"] = f"{rec['summary']} {note}" if rec.get("summary") else note
        if "evidence" not in rec:
            rec["evidence"] = {"numbers": NUMBERS[row[6]]}
    return rec


def build(data: Dict[str, Any], core: refs.Registry, vocab: Dict[str, Any]) -> Dict[str, Any]:
    """The shards (name -> list of records), the coverage file and a report, from the map's data."""
    global CATEGORY_CODES
    CATEGORY_CODES = {v["code"]: k for k, v in vocab["category"].items()}
    by_url: Dict[str, refs.Reference] = {}
    for ref in core.entries.values():
        if ref.get("url") and ref.kind in ("source", "unverified"):
            by_url.setdefault(norm_url(ref["url"]), ref)
    ids = Ids(list(core.entries) + list(core.aliases))
    shards: Dict[str, List[Dict[str, Any]]] = {}
    report: Dict[str, Any] = {"extended": [], "left-unverified": [], "projects": 0, "guides": 0}
    pending: Dict[str, Dict[str, Any]] = {}            # core id -> its extension's parts
    for g in data["PG"]:
        ref = by_url.get(norm_url(g["url"]))
        if ref is not None:
            if ref.kind == "unverified":
                report["left-unverified"].append((g["url"], ref.id))
                continue
            pending.setdefault(ref.id, {"g": None, "d": None})
            pending[ref.id]["g"] = g
            continue
        rec = guide_record(g, vocab, ids)
        shards.setdefault(f"guides-{rec['process_groups'][0]}", []).append(rec)
        report["guides"] += 1
    for i, row in enumerate(data["D"]):
        ref = by_url.get(norm_url(row[1]))
        if ref is not None:
            if ref.kind == "unverified":
                report["left-unverified"].append((row[1], ref.id))
                continue
            pending.setdefault(ref.id, {"g": None, "d": None})
            pending[ref.id]["d"] = (i, row)
            continue
        rec = project_record(i, row, data, vocab, ids)
        shards.setdefault(f"projects-{row[3]}", []).append(rec)
        report["projects"] += 1
    for core_id, parts in pending.items():
        rec = extension(core_id, parts["g"], parts["d"], data, vocab)
        group = (rec.get("process_groups") or ["general"])[0]
        name = f"guides-{group}" if parts["g"] is not None else f"projects-{parts['d'][1][3]}"
        shards.setdefault(name, []).append(rec)
        report["extended"].append(core_id)
    # derived confidence, from the registry as it will load
    reg = refs.Registry(core.data, core.path, [refs.Shard(f"research/references/{n}.yaml", {"schema": 2,
                                                                                         "sources": recs})
                                               for n, recs in shards.items()], vocab, core.core_file)
    for recs in shards.values():
        for rec in recs:
            ref = reg.resolve(rec["id"])
            if isinstance(ref.get("evidence"), dict):
                _insert_after(rec, "evidence", "confidence", refs.confidence(ref, reg))
    titles = {}
    for name in shards:
        kind, key = name.split("-", 1)
        text, words = SHARD_TITLES[kind]
        titles[name] = text.format(vocab[words][key])
    return {"shards": dict(sorted(shards.items())), "titles": titles, "coverage": coverage(data), "report": report}


def _insert_after(rec: Dict[str, Any], after: str, key: str, value: Any) -> None:
    items = list(rec.items())
    at = [k for k, _ in items].index(after) + 1
    rec.clear()
    rec.update(items[:at] + [(key, value)] + [(k, v) for k, v in items[at:] if k != key])


def coverage(data: Dict[str, Any]) -> Dict[str, Any]:
    """The map's coverage table: what cad-agent enforces per topic and its gaps, with the drafted issue each row
    carried (never posted), and the sources each process group still lacks."""
    rows = []
    for r in data["CA"]:
        number, topic = r["topic"].split(" ", 1)
        row = {"id": f"ca-{number}-{slug(topic, 40)}", "number": number, "topic": topic, "status": r["status"],
               "areas": COVERAGE_AREAS[number], "where": r["where"], "defaults": r["defaults"],
               "sources": r["source"], "gap": r["gap"]}
        if r.get("issue_title"):
            row["draft_issue"] = {"title": r["issue_title"], "body": r.get("issue_body", ""), "posted": False}
        rows.append(row)
    wanted = [{"group": k, "title": data["PR"][k], "areas": GROUP_AREAS[k], "text": v} for k, v in data["PGAP"].items()]
    return {"schema": 2, "observed": ASSESSED,
            "note": "The map's coverage table: what cad-agent enforced per topic on the day the map was made, where "
                    "(file:line as of then; lines drift), and the gaps. Each draft_issue is the issue the map's "
                    "authors drafted for the gap; none was posted. `wanted` lists, per process group, the sources "
                    "the map's search did not find.",
            "rows": rows, "wanted": wanted}


# ----------------------------------------------------------------------------- writing

class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"' if "\n" in value else None)


_Dumper.add_representer(str, _str)


def dump(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120, default_flow_style=False)


GENERATED = "# Generated by tools/import_refmap.py from the Reference Map's data.json (sha256 {digest}).\n"
SHARD_HEAD = ("# Every new record here is catalogued: snippet-only until someone reads the source and promotes it\n"
              "# (research/references/README.md). Licences are as the map states them, not read. Edit records by\n"
              "# hand when you read a source; a re-import would undo that (run the tool with --check first).\n")
COVERAGE_HEAD = "# The map's coverage rows and the sources it still wants. Its drafted issues were never posted.\n"


def render(result: Dict[str, Any], digest: str) -> Dict[str, str]:
    """File name -> text, for every file the import owns."""
    first = GENERATED.format(digest=digest[:16])
    out = {}
    for name, recs in result["shards"].items():
        doc = {"schema": 2, "title": result["titles"][name], "sources": recs}
        out[f"{name}.yaml"] = first + SHARD_HEAD + dump(doc)
    out[refs.COVERAGE] = first + COVERAGE_HEAD + dump(result["coverage"])
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data", type=Path, help="the Reference Map's data.json (kept out of the repo)")
    ap.add_argument("--root", type=Path, default=ROOT, help="the cad-agent checkout to write into")
    ap.add_argument("--check", action="store_true", help="exit 1 if the files would change; write nothing")
    args = ap.parse_args(argv)
    raw = args.data.read_bytes()
    data = json.loads(raw)
    folder = refs.shard_folder(args.root / "research" / "references.yaml")
    vocab = yaml.safe_load((folder / refs.VOCAB).read_text(encoding="utf-8"))
    full = refs.load(args.root / "research" / "references.yaml")
    owned = {f.name for f in folder.glob("*.yaml") if f.name != refs.VOCAB}      # shards and coverage.yaml
    # the core alone: shards this tool wrote before are replaced, not merged with themselves
    core = refs.Registry(full.data, full.path, [s for s in full.shards if Path(s.file).name not in owned], vocab,
                         full.core_file)
    result = build(data, core, vocab)
    files = render(result, hashlib.sha256(raw).hexdigest())
    changed = [n for n, text in files.items() if not (folder / n).is_file() or (folder / n).read_text("utf-8") != text]
    stale = sorted(owned - set(files) - {"README.md"})
    rep = result["report"]
    print(f"{rep['projects']} projects and {rep['guides']} guides as catalogued records, {len(rep['extended'])} "
          f"extensions of read sources, in {len(result['shards'])} shards; {len(result['coverage']['rows'])} coverage "
          f"rows")
    for url, rid in rep["left-unverified"]:
        print(f"left as unverified in research/references.yaml: {rid} ({url})")
    if args.check:
        for n in changed + stale:
            print(f"would change: research/references/{n}")
        return 1 if changed or stale else 0
    for n in changed:
        (folder / n).write_text(files[n], encoding="utf-8")
    for n in stale:
        print(f"not written by this import, left in place: research/references/{n}")
    print(f"wrote {len(changed)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
