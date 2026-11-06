#!/usr/bin/env python3
"""Import the Reference Map into the reference registry's schema-2 shards (#323, phase 2).

The Reference Map (built by the project owner on 2026-11-02) lists open projects (its ``D`` table, with the objective
answers of ``S``), manufacturing and design guides (``PG``) and a coverage table of what cad-agent enforces (``CA``,
with ``PGAP``: the sources each process group still lacks). This tool turns its ``data.json`` into:

* ``docs/research/references/projects-<domain>.yaml``: one shard per project domain (the map's ``DOMS``);
* ``docs/research/references/guides-<group>.yaml``: one shard per process group (``PR``), a guide placed by its first
  process;
* ``docs/research/references/coverage.yaml``: the coverage rows, their draft issues (never posted) and the sources still
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
* a guide whose URL is already a read source in ``docs/research/references.yaml`` becomes an ``extends: true`` record that
  adds these fields to that entry; one that is already an ``unverified`` entry is left there and reported;
* text written for one project is rewritten project-neutral by ``NEUTRAL`` below (cad-agent is general purpose), and
  a re-import fails if the map's text under a rewrite changed.

The import reconciles, so it is the one source of truth for what the map says and never undoes a person's work.
Each record it writes ends with ``imported:``, a digest of the record's own text. In a shard it wrote, it keeps a
record **as written, byte for byte**, when either:

* someone has worked on it (``touched``): its text no longer matches its digest, so any edit counts, by a person or a
  tool (a promotion, a summary fixed by hand, ``tools/references_health_apply.py`` withdrawing a claim or moving a
  url, a comment added under it). A record with no digest counts as worked on unless it is exactly what the map makes;
* the map does not make it: a record added by hand, or one the map has since dropped. It is kept and reported, never
  deleted; delete a dropped one by hand.

Every other record is rewritten from the map, so a later change to a record nobody has touched still applies. A kept
record stays in the shard it is in, where the import would put it. The tool is deterministic and idempotent: the same
data and shards give the same bytes. ``--check`` exits 1 when the files on disk differ from what the import would
write.

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
sys.path.insert(0, str(ROOT / "software"))
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
    "https://github.com/shaise/FreeCAD_SheetMetal": (None, "share-alike", "LGPL-2.1 (only or later not stated), as "
                                                                        "docs/research/references.yaml states; text not read"),
    "https://github.com/shaise/FreeCAD_FastenersWB": ("GPL-2.0-or-later", "share-alike",
                                                      "GPL-2.0-or-later, as docs/research/references.yaml states; text "
                                                      "not read")}
# Text the map wrote against one project's target, made project-neutral: verdicts such as "off-target for a balancing
# robot", "far below" one project's chosen motor, "not wheel-legged" or "relevance to the robot". Facts about what a
# project uses stay. Keyed by (table, row, field): (the first 16 hex digits of the sha256 of the map's text, our text).
# The map's own wording is not kept here; a key whose text no longer hashes the same stops the import, so a changed row
# is looked at again.
NEUTRAL: Dict[Tuple[str, str, str], Tuple[str, str]] = {
    ("D", "0", "note"): ("74bd9025be70f4c4",
                         "Printed remote weapon station: 4 worm-gear axes on NEMA17, printed azimuth bearing, "
                         "separate camera gimbal. STEP folder and design handbook."),
    ("D", "115", "note"): ("f7bf16a07129c3ab",
                           "Includes a torque test stand (Arduino and Python); no results published. The stand is "
                           "reusable for other actuator tests."),
    ("D", "158", "note"): ("22502faed7641917",
                           "Python SDK for RobStride actuators. Software only."),
    ("S", "39", "caveat"): ("b33a6313cafcafae",
                            "No speed or flight numbers in README; NonCommercial licence."),
    ("S", "40", "caveat"): ("a0568b14401a13d5",
                            "Frame is carbon cut, not printed; drone-specific."),
    ("S", "41", "caveat"): ("a07cda91463257a2",
                            "Drone frame."),
    ("S", "42", "caveat"): ("12a78649b2883a06",
                            "Carbon frame and 12s parts; cost is only implied."),
    ("S", "52", "caveat"): ("9c9e8f1ec99d272c",
                            "Racing quad frame."),
    ("S", "53", "caveat"): ("46e7026fa80687a4",
                            "Giant racing frame."),
    ("S", "54", "caveat"): ("6d08733b73fb8b4f",
                            "Micro racing frame."),
    ("S", "55", "caveat"): ("cbe415a6e01cea06",
                            "Weights are estimates; micro drone frame."),
    ("S", "56", "caveat"): ("96691165149406d1",
                            "Drone frame; carbon plates are the main structure, prints are accessories only."),
    ("S", "71", "caveat"): ("421fb7e29f217022",
                            "Spring dart blaster; CC BY-NC-SA licence."),
    ("S", "135", "caveat"): ("a62aa2f839fea9da",
                             "Belt module; README itself gives no torque numbers."),
    ("S", "158", "caveat"): ("1bd9f4d217966c8b",
                             "Software only, last pushed July 2024."),
    ("S", "165", "caveat"): ("b0adad1ddc3531c4",
                             "Quadruped; no validation against hardware stated."),
    ("S", "204", "caveat"): ("28e8e688468005f7",
                             "Hobby servos; useful for BOM and assembly style, not for high-torque actuation."),
    ("S", "206", "caveat"): ("a19708e5a07a0ddd",
                             "Desktop arm; README gives no accuracy or payload numbers."),
    ("S", "207", "caveat"): ("e7f9d135caf2c4d8",
                             "ROS1 launch only, a humanoid without wheels, no licence file match and no arm."),
    ("S", "215", "caveat"): ("3c6fb2be265e9a1b",
                             "Unitree A1 and DJI 3508 actuators with serial or CAN links."),
    ("S", "222", "caveat"): ("8787edf998905417",
                             "Balances only for a few seconds; servo legs and stepper wheels."),
    ("S", "225", "caveat"): ("309fce4cde9b11e8",
                             "Ballbot with omniwheels; MATLAB code is the main content and the hardware is heavy."),
    ("S", "244", "caveat"): ("eefb91f6de64dcb1",
                             "Hobby servos and L298N drivers; no balance results or numbers given."),
    ("S", "268", "caveat"): ("be1f18c066ae123a",
                             "Actuators are 2.5 N.m rated class; no measured torque or gait data."),
    ("S", "305", "caveat"): ("25338b04aa7be4a2",
                             "Arm for education; README gives no payload or accuracy numbers."),
    ("S", "322", "caveat"): ("a341fda8408b6331",
                             "Licence is CC BY-NC-SA; CLN17 handles only 4.5 A peak."),
    ("S", "325", "caveat"): ("fac4b34ab29ee21d",
                             "Tiny low-voltage board (2-5.5 V, 2 A)."),
    ("S", "335", "caveat"): ("a0aa79312adc681b",
                             "Not FOC; Hall-sensor 6-step with no tests, though the map tagged it FOC."),
    ("S", "351", "caveat"): ("4a4fc45d5f3f4cdd",
                             "README missing; listed with drivers but does not fit that category; only the summary "
                             "describes it."),
    ("PG", "136", "note"): ("7e1e804e3e6c2015",
                            "PDF is gated; PolyJet moulds."),
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


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def neutral(table: str, row: str, field: str, text: str) -> str:
    key = (table, row, field)
    if key in NEUTRAL:
        theirs, ours = NEUTRAL[key]
        if text_hash(text) != theirs:
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


def guide_fields(j: int, g: Dict[str, Any], vocab: Dict[str, Any], notes: bool = True) -> Dict[str, Any]:
    """The schema-2 fields of guide ``j``, without its id (shared by a new record and an extension). The map's note says
    how its snippet looked; ``notes=False`` (a source the core registry has read) keeps it only in the evidence of the
    map's claim, never in the record's summary, where it would contradict the reading."""
    g = {k: neutral("PG", str(j), k, v) if isinstance(v, str) and k in ("gist", "rule", "note") else v
         for k, v in g.items()}
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
        if not notes and g.get("note"):        # on a read source, the map's snippet note describes this claim only
            head = claim["evidence"].rstrip()
            head += "" if head.endswith((".", "!", "?", ")")) else " [cut off in the map]."
            claim["evidence"] = f"{head} As the map saw it: {g['note']}"
        claims.append(claim)
    summary = g["gist"] + (f" Note: {g['note']}" if notes and g.get("note") else "")
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


def guide_record(j: int, g: Dict[str, Any], vocab: Dict[str, Any], ids: Ids) -> Dict[str, Any]:
    fields = guide_fields(j, g, vocab)
    publisher = slug(g["publisher"].split(" (")[0])        # "Hubs (Protolabs Network)" -> hubs
    base = slug(g["title"])
    base = base if base.startswith(publisher) else slug(f"{publisher} {g['title']}")
    head = {"id": ids(base), "kind": fields.pop("kind"), "category": fields.pop("category"), "title": g["title"],
            "authors": [], "org": g["publisher"], "year": None, "url": clean_url(g["url"]), "access": "free",
            "terms": TERMS}
    return {**head, **fields, "used_for": []}


def extension(core_id: str, g: Optional[Tuple[int, Dict[str, Any]]], d_row: Optional[Tuple[int, List[str]]],
              data: Dict[str, Any], vocab: Dict[str, Any]) -> Dict[str, Any]:
    """An ``extends: true`` record adding the map's fields to a core read source (guide and/or project row). The
    map's snippet notes are left out: the core entry was read, and its ``verified`` note says what was."""
    rec: Dict[str, Any] = {"id": core_id, "extends": True}
    if g is not None:
        fields = guide_fields(g[0], g[1], vocab, notes=False)
        fields["evidence"].pop("class")          # the core entry was read: its class stays `read`
        rec.update(fields)
    if d_row is not None:
        i, row = d_row
        rec.setdefault("kind", "project" if row[2] != "G" else KIND_HINTS.get(row[4], "article"))
        rec.setdefault("category", CATEGORY_CODES[row[2]])
        rec["domains"] = [row[3]]
        if g is None:                            # a guide's process areas place it better than a project domain
            rec["areas"] = list(DOMAIN_AREAS[row[3]])
        if "summary" not in rec:
            rec["summary"] = neutral("D", str(i), "note", row[7])
        if "evidence" not in rec:
            rec["evidence"] = {"numbers": NUMBERS[row[6]]}
    return rec


STAMP = "imported"                       # the last key of a record the import wrote: the digest of its text
_STAMP_LINE = re.compile(rf"(?m)^  {STAMP}: .*\n")


def text_digest(text: str) -> str:
    """The digest of a record's text, its ``imported`` line left out (16 hex digits)."""
    return hashlib.sha256(_STAMP_LINE.sub("", text).encode("utf-8")).hexdigest()[:16]


def stamped(rec: Dict[str, Any]) -> str:
    """A record as the import writes it: its text, ending with the digest of that text."""
    body = {k: v for k, v in rec.items() if k != STAMP}
    return dump([{**body, STAMP: text_digest(dump([body]))}])


def touched(text: str, made: Dict[str, Any]) -> bool:
    """True when the record written as ``text`` was worked on since the import wrote it: its text no longer matches
    its digest. Without a digest (a shard from before digests, or a hand-made line), it was worked on unless it is
    exactly what the map makes (``made``, the record without its derived confidence)."""
    rec = yaml.safe_load(text)[0]
    if STAMP in rec:
        return text_digest(text) != str(rec[STAMP])
    return {k: v for k, v in rec.items() if k != "confidence"} != made


def build(data: Dict[str, Any], core: refs.Registry, vocab: Dict[str, Any],
          existing: Optional[Dict[str, Tuple[str, str]]] = None) -> Dict[str, Any]:
    """The shards (name -> list of records), the coverage file and a report, from the map's data. ``existing`` is
    every record in the shards an earlier import wrote (id -> (shard name, its text)): the touched ones and those the
    map does not make are kept in their shard (``result["kept"]``) instead of the map's version."""
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
    for j, g in enumerate(data["PG"]):
        ref = by_url.get(norm_url(g["url"]))
        if ref is not None:
            if ref.kind == "unverified":
                report["left-unverified"].append((g["url"], ref.id))
                continue
            pending.setdefault(ref.id, {"g": None, "d": None})
            pending[ref.id]["g"] = (j, g)
            continue
        rec = guide_record(j, g, vocab, ids)
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
    # reconcile with the shards on disk: a kept record replaces the map's, in the shard it is in
    existing = existing or {}
    made = {r["id"]: r for recs in shards.values() for r in recs}
    kept = {i: name for i, (name, text) in existing.items() if i not in made or touched(text, made[i])}
    as_kept = {i: yaml.safe_load(existing[i][1])[0] for i in kept}
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for name, recs in shards.items():
        merged[name] = [as_kept[r["id"]] if r["id"] in kept else r for r in recs
                        if kept.get(r["id"], name) == name]
    for i, name in kept.items():              # added by hand, dropped by the map, or placed elsewhere by it
        if not any(r["id"] == i for r in merged.get(name, [])):
            merged.setdefault(name, []).append(as_kept[i])
    shards = merged
    report["kept"] = sorted(i for i in kept if i in made)
    report["not-in-map"] = sorted(i for i in kept if i not in made)
    # derived confidence, from the registry as it will load; a kept record keeps its own
    reg = refs.Registry(core.data, core.path, [refs.Shard(f"docs/research/references/{n}.yaml", {"schema": 2,
                                                                                         "sources": recs})
                                               for n, recs in shards.items()], vocab, core.core_file)
    for recs in shards.values():
        for rec in recs:
            if rec["id"] in kept:
                continue
            ref = reg.resolve(rec["id"])
            if isinstance(ref.get("evidence"), dict):
                _insert_after(rec, "evidence", "confidence", refs.confidence(ref, reg))
    titles = {}
    for name in shards:
        kind, key = name.split("-", 1)
        text, words = SHARD_TITLES[kind]
        titles[name] = text.format(vocab[words][key])
    return {"shards": dict(sorted(shards.items())), "titles": titles, "coverage": coverage(data), "report": report,
            "kept": kept}


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
              "# (docs/research/references/README.md). Licences are as the map states them, not read. A re-import keeps\n"
              "# as written every record edited since (its text no longer matches `imported`), and every one the map\n"
              "# does not make.\n")
ITEM = re.compile(r"(?m)^(?=- )")         # a record starts a line in a dumped shard; its text never does


def records_as_written(text: str) -> List[Tuple[str, str]]:
    """A shard's records as (id, exact text), in file order."""
    body = text.split("\nsources:\n", 1)[1]
    parts = [p for p in ITEM.split(body) if p]
    recs = yaml.safe_load(body) or []
    if len(parts) != len(recs):
        raise SystemExit("a shard's records could not be told apart; keep each record starting `- ` at the line start")
    return [(r["id"], t) for r, t in zip(recs, parts)]
COVERAGE_HEAD = "# The map's coverage rows and the sources it still wants. Its drafted issues were never posted.\n"


def render(result: Dict[str, Any], digest: str, written: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """File name -> text, for every file the import owns. A kept record is its text in ``written`` (id -> text)."""
    first = GENERATED.format(digest=digest[:16])
    out = {}
    for name, recs in result["shards"].items():
        doc = dump({"schema": 2, "title": result["titles"][name], "sources": recs})
        head = doc.split("\nsources:\n", 1)[0] + "\nsources:\n"
        body = "".join(written[r["id"]] if r["id"] in result["kept"] else stamped(r) for r in recs)
        out[f"{name}.yaml"] = first + SHARD_HEAD + head + body
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
    folder = refs.shard_folder(args.root / "docs" / "research" / "references.yaml")
    vocab = yaml.safe_load((folder / refs.VOCAB).read_text(encoding="utf-8"))
    full = refs.load(args.root / "docs" / "research" / "references.yaml")
    # the files an earlier import wrote: they carry its first line. A hand-written shard never does, so it is kept, read
    # as part of the registry the import deduplicates against, and never rewritten or reported as stale.
    owned = {f.name for f in folder.glob("*.yaml")
             if f.name != refs.VOCAB and f.read_text(encoding="utf-8").startswith(GENERATED.split("{")[0])}
    # the core alone: shards this tool wrote before are replaced, not merged with themselves
    core = refs.Registry(full.data, full.path, [s for s in full.shards if Path(s.file).name not in owned], vocab,
                         full.core_file)
    existing, written = {}, {}
    for name in sorted(owned - set(refs.NOT_SHARDS)):
        text = (folder / name).read_text(encoding="utf-8")
        for rid, rec_text in records_as_written(text):
            existing[rid] = (name[:-len(".yaml")], rec_text)
            written[rid] = rec_text
    result = build(data, core, vocab, existing)
    files = render(result, hashlib.sha256(raw).hexdigest(), written)
    changed = [n for n, text in files.items() if not (folder / n).is_file() or (folder / n).read_text("utf-8") != text]
    stale = sorted(owned - set(files))
    rep = result["report"]
    print(f"{rep['projects']} projects and {rep['guides']} guides as catalogued records, {len(rep['extended'])} "
          f"extensions of read sources, in {len(result['shards'])} shards; {len(result['coverage']['rows'])} coverage "
          f"rows")
    for url, rid in rep["left-unverified"]:
        print(f"left as unverified in docs/research/references.yaml: {rid} ({url})")
    if rep["kept"]:
        print(f"kept as written ({len(rep['kept'])} edited since the import): {', '.join(rep['kept'])}")
    for rid in rep["not-in-map"]:
        print(f"not in the map, kept as written: {rid} (added by hand, or dropped by the map: delete it by hand)")
    if args.check:
        for n in changed + stale:
            print(f"would change: docs/research/references/{n}")
        return 1 if changed or stale else 0
    for n in changed:
        (folder / n).write_text(files[n], encoding="utf-8")
    for n in stale:
        print(f"written by an earlier import but not by this one, left in place: docs/research/references/{n}")
    print(f"wrote {len(changed)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
