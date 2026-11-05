#!/usr/bin/env python3
"""Turn a reference health report into the weekly bot PR's edits (#323 phase 4).

`tools/resource_audit.py references` writes the registry's link health to a CI artifact (never to git: #323, Q5).
This tool reads that JSON and writes into the schema-2 shards (research/references/*.yaml) only the changes that are
evidence, each by a fixed rule:

* **gone or unreachable on two checks in a row** (an accepted soft-404 does not count): the record's
  ``evidence.class`` falls one rung of the ladder (``verified-at-source`` -> ``read``, ``read`` -> ``snippet-only``)
  and ``evidence.lowered`` says from what, when and why. It falls once per outage: a record whose ``lowered.date`` is on
  or after the day the outage started is left alone. A snippet-only record has no rung to fall;
* **moved on two checks in a row**, by permanent redirects only (301/308) to an https page on the same site: ``url``
  becomes the new address and the old one goes to ``mirrors``;
* **a page that changed** (its normalised text's hash): a claim corroborated by that record alone goes back to
  ``unconfirmed``, with a dated note in its ``evidence``; its class stays.

A stored ``confidence`` is re-derived after the edits (``confidence()``), and an edit that would add a problem to
``python -m cadagent.review.references --check``, or leave a cited record below ``read``, is left out and listed for a
person instead. Entries of the hand-written core file (research/references.yaml) are never edited here: they are
listed. Nothing here fetches anything; the same report and checkout give the same edits.

    python3 tools/references_health_apply.py --health build/references-health.json                 # print the plan
    python3 tools/references_health_apply.py --health build/references-health.json --write --body build/pr.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cadagent.review import references as refs  # noqa: E402


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ra = _tool("resource_audit")           # the health report's own rules (effective status, sites, acceptances)
ir = _tool("import_refmap")            # the shards' writer, so an edit changes only the lines it means to
DOWN = ra.DOWN
CORE = "research/references.yaml"


def split_head(text: str) -> Tuple[str, str]:
    """(the comment lines at the top, the YAML after them)."""
    lines = text.splitlines(True)
    n = 0
    while n < len(lines) and lines[n].startswith("#"):
        n += 1
    return "".join(lines[:n]), "".join(lines[n:])


def editable(text: str) -> bool:
    """A shard the tool can rewrite without touching other lines: its YAML is exactly what the importer's writer
    gives for its data (a shard edited by hand into another style is listed for a person instead)."""
    _, body = split_head(text)
    return ir.dump(refs._yaml(body)) == body


class Plan:
    def __init__(self):
        self.edits: Dict[str, List[Tuple[str, str, Any]]] = {}     # record id -> [(what, why, fn(record dict))]
        self.notes: List[Tuple[str, str]] = []                     # (record id, what a person should do)
        self.rows: List[Tuple[str, str, str]] = []                 # (record id, change, why) for the PR body

    def edit(self, rid, what, why, fn):
        self.edits.setdefault(rid, []).append((what, why, fn))

    def note(self, rid, text):
        self.notes.append((rid, text))


def plan(health: Dict[str, Any], reg: refs.Registry, accepted: List[Dict[str, Any]], as_of: dt.date,
         cited: set) -> Plan:
    p = Plan()
    urls = {r.get("url"): r.id for r in reg.entries.values() if r.get("url")}
    for rid, e in sorted((health.get("records") or {}).items()):
        ref = reg.entries.get(rid)
        if ref is None or e.get("url") != ref.get("url"):
            continue                                   # gone from the registry, or its link changed since
        streak = e.get("streak") or {}
        status = ra.effective_status(rid, e, accepted)
        runs, since = int(streak.get("runs") or 0), str(streak.get("since") or "")
        core = ref.file == CORE
        down_runs, down_since = int(e.get("down_runs") or 0), str(e.get("down_since") or "")
        if status in DOWN and down_runs >= 2 and down_since:
            why = (f"{status}: gone or unreachable on {down_runs} checks in a row since {down_since}"
                   + (f" (HTTP {' -> '.join(map(str, e['http']))})" if e.get("http") else "")
                   + (f" ({', '.join(e['soft404'])})" if e.get("soft404") else ""))
            cls = ref.evidence_class
            lowered = (ref.get("evidence") or {}).get("lowered") if isinstance(ref.get("evidence"), dict) else None
            if core:
                p.note(rid, f"{why}: a cited core entry; link a live copy (an archive.org snapshot, said so) or a successor")
            elif cls not in refs.LADDER or not isinstance(ref.get("evidence"), dict):
                p.note(rid, f"{why}: no evidence class to lower")
            elif isinstance(lowered, dict) and str(lowered.get("date") or "") >= down_since:
                pass                                   # lowered already for this outage
            elif refs.LADDER.index(cls) == 0:
                pass                                   # snippet-only: no rung to fall (the issue lists it)
            else:
                new = refs.LADDER[refs.LADDER.index(cls) - 1]
                if new == refs.LADDER[0] and ({rid} | set(ref.get("aliases") or [])) & cited:
                    p.note(rid, f"{why}: cited by code or a page, so it cannot fall below read by itself; replace the link")
                else:
                    def lower(d, new=new, cls=cls, why=why):
                        d["evidence"]["class"] = new
                        d["evidence"]["lowered"] = {"from": cls, "date": as_of.isoformat(), "why": why}
                    p.edit(rid, f"evidence.class {cls} -> {new}", why, lower)
        final = e.get("final_url")
        if status == "moved" and streak.get("status") == "moved" and runs >= 2 and final:
            why = f"moved on {runs} checks in a row since {since}"
            old = ref.get("url")
            same_site = ra.site(ra.host(old)) == ra.site(ra.host(final)) and ra.host(old) not in ra.RESOLVERS
            fin = ra.urllib.parse.urlsplit(final)
            if fin.path in ("", "/") or ra.SEARCHY.search(fin.path + ("?" + fin.query if fin.query else "")):
                p.note(rid, f"{why} to {final}, a home or search page: the page is probably gone; check by hand")
            elif not (e.get("permanent") and final.startswith("https://") and same_site and not any(c.isspace() for c in final)):
                p.note(rid, f"{why} to {final}, but not by permanent redirects to https on the same site: check by hand")
            elif final in urls and urls[final] != rid:
                p.note(rid, f"{why} to {final}, which is already the link of {urls[final]}: merge the two by hand")
            elif core:
                p.note(rid, f"{why} to {final}: a core entry; update its url by hand")
            else:
                def move(d, final=final, old=old):
                    d["url"] = final
                    mirrors = list(d.get("mirrors") or [])
                    if old not in mirrors:
                        mirrors.append(old)
                    d["mirrors"] = mirrors
                p.edit(rid, f"url -> {final} (the old link kept in mirrors)", why, move)
    # a changed page: claims that rest on it alone are no longer confirmed
    changed = {rid: e["changed_on"] for rid, e in (health.get("records") or {}).items()
               if e.get("changed_on") and rid in reg.entries and e.get("url") == reg.entries[rid].get("url")}
    for ref in sorted(reg.entries.values(), key=lambda r: r.id):
        for i, claim in enumerate(ref.get("claims") or []):
            if not isinstance(claim, dict) or claim.get("status") != "corroborated":
                continue
            by = [reg.resolve(k).id for k in claim.get("corroborated_by") or [] if isinstance(k, str) and k in reg]
            if len(by) != 1 or by[0] not in changed or by[0] == ref.id:
                continue
            mark = f"{changed[by[0]]}: the page of {by[0]} changed; re-read it before corroborating again"
            if mark in str(claim.get("evidence") or "") or str(ref.get("verified") or "")[:10] >= changed[by[0]]:
                continue                               # done already, or the record was read again since the change
            if ref.file == CORE:
                p.note(ref.id, f"claim {i} rests on {by[0]}, whose page changed on {changed[by[0]]}: re-read it")
                continue

            def unconfirm(d, i=i, mark=mark):
                c = d["claims"][i]
                c["status"] = "unconfirmed"
                c["evidence"] = (str(c.get("evidence") or "").rstrip() + " " if c.get("evidence") else "") + mark
            p.edit(ref.id, f"claims[{i}] corroborated -> unconfirmed", f"{by[0]} changed on {changed[by[0]]}", unconfirm)
    return p


def _records(doc) -> Dict[str, Dict[str, Any]]:
    return {r["id"]: r for r in doc.get("sources") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)}


def render(root: Path, reg: refs.Registry, p: Plan, skip: set) -> Dict[str, str]:
    """{shard path: new text} for the plan's edits (minus `skip`), with stored confidences re-derived."""
    by_file: Dict[str, List[str]] = {}
    for rid in p.edits:
        if rid not in skip:
            by_file.setdefault(reg.entries[rid].file, []).append(rid)
    out = {}
    for f, ids in sorted(by_file.items()):
        text = (root / f).read_text(encoding="utf-8")
        if not editable(text):
            for rid in ids:
                p.note(rid, f"{f} is not in the importer's layout, so the bot leaves it alone: "
                            + "; ".join(w for w, _, _ in p.edits[rid]))
                skip.add(rid)
            continue
        head, body = split_head(text)
        doc = refs._yaml(body)
        recs = _records(doc)
        for rid in ids:
            for _, _, fn in p.edits[rid]:
                fn(recs[rid])
        out[f] = head + ir.dump(doc)
    return out


def validate(root: Path, files: Dict[str, str]) -> Tuple[refs.Registry, List[str]]:
    """Load the registry with `files` in place (in a scratch copy) and return it with its problems."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / CORE).parent.mkdir(parents=True)
        shutil.copy2(root / CORE, tmp / CORE)
        shutil.copytree(root / "research" / "references", tmp / "research" / "references")
        for rel, text in files.items():
            (tmp / rel).write_text(text, encoding="utf-8")
        reg = refs.load(tmp / CORE)
        return reg, reg.problems(root=root)        # areas, profiles and used_for paths are read from the checkout


def rederive(root: Path, files: Dict[str, str]) -> Dict[str, str]:
    """Write every stored confidence that the edits changed, in every editable shard (a demotion can change the
    confidence of the records it corroborated, too)."""
    reg, _ = validate(root, files)
    changed = dict(files)
    for shard in reg.shards:
        stale = {r["id"] for r in shard.records if isinstance(r, dict) and r.get("confidence") is not None
                 and r.get("id") in reg.entries and r["confidence"] != refs.confidence(reg.entries[r["id"]], reg)}
        if not stale:
            continue
        text = changed.get(shard.file) or (root / shard.file).read_text(encoding="utf-8")
        if not editable(text):
            continue                                   # check() will say so; the problem diff in build() drops the edit
        head, body = split_head(text)
        doc = refs._yaml(body)
        for rid, d in _records(doc).items():
            if rid in stale:
                d["confidence"] = refs.confidence(reg.entries[rid], reg)
        changed[shard.file] = head + ir.dump(doc)
    return changed


def build(root: Path, health: Dict[str, Any], accepted, as_of: dt.date, cited=None) -> Tuple[Dict[str, str], Plan]:
    """The new texts of the shards the evidence changes, and the plan with its rows and notes."""
    reg = refs.load(root / CORE)
    if cited is None:
        cited = {c.key for c in refs.citations(root)}
    p = plan(health, reg, accepted, as_of, cited)
    if not p.edits:
        return {}, p
    _, before = validate(root, {})
    before = set(before)
    skip: set = set()
    for _ in range(len(p.edits) + 1):
        files = rederive(root, render(root, reg, p, skip))
        _, after = validate(root, files)
        new = [x for x in after if x not in before]
        if not new:
            break
        blamed = {rid for rid in p.edits if rid not in skip and any(x.startswith(f"{rid}:") for x in new)}
        if not blamed:                                 # a problem we cannot pin on one record: change nothing
            blamed = {rid for rid in p.edits if rid not in skip}
        for rid in sorted(blamed):
            p.note(rid, "left out: the edit would make the registry check fail ("
                        + "; ".join(x for x in new if x.startswith(f"{rid}:"))[:300] + ")")
        skip |= blamed
    else:
        files = {}
    for rid in sorted(p.edits):
        if rid not in skip:
            for what, why, _ in p.edits[rid]:
                p.rows.append((rid, what, why))
    return files, p


def body(health: Dict[str, Any], files: Dict[str, str], p: Plan) -> str:
    out = ["Weekly reference health: the evidence changes the link checks support (#323). Generated by "
           "`tools/references_health_apply.py` from the report of " + str(health.get("as_of")) + " at revision `"
           + str(health.get("revision") or "")[:12] + "`. Health itself is not kept in git: the full report is the "
           "workflow's `references-health` artifact.", "",
           "Each change follows a fixed rule (the tool's docstring): a link gone or unreachable on two checks in a row "
           "lowers the record's evidence class one rung; a permanent same-site move updates the link and keeps the old one "
           "in `mirrors`; a changed page sends a claim it alone corroborates back to unconfirmed.", ""]
    if p.rows:
        out += ["| Record | Change | Why |", "|---|---|---|"]
        out += [f"| `{rid}` | {ra.inert(what)} | {ra.inert(why)} |" for rid, what, why in p.rows]
        out += ["", "Files: " + ", ".join(f"`{f}`" for f in sorted(files)), ""]
    else:
        out += ["No changes this week.", ""]
    if p.notes:
        out += ["### For a person", "", "The bot does not change these; each needs someone to read the source.", ""]
        out += [f"- `{rid}`: {ra.inert(text)}" for rid, text in p.notes]
        out += [""]
    out += ["Review: the diff touches only the records above. `python -m cadagent.review.references --check` passes on it "
            "(the tool checks before it writes).", ""]
    return ra.no_mentions("\n".join(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--health", required=True, help="the JSON `resource_audit.py references` wrote")
    ap.add_argument("--root", type=Path, default=ROOT, help="the checkout to edit (default: this one)")
    ap.add_argument("--accepted", help="accepted findings (default research/security-accepted.yaml)")
    ap.add_argument("--as-of", help="the date written into evidence.lowered (default: the report's date)")
    ap.add_argument("--write", action="store_true", help="write the edited shards (default: print the plan)")
    ap.add_argument("--body", help="write the PR description here")
    a = ap.parse_args(argv)
    health = json.loads(Path(a.health).read_text(encoding="utf-8"))
    if health.get("schema") != ra.HEALTH_SCHEMA:
        print(f"{a.health}: not a {ra.HEALTH_SCHEMA} report", file=sys.stderr)
        return 2
    accepted = ra.load_accepted(a.accepted or a.root / ra.ACCEPTED)
    as_of = dt.date.fromisoformat(a.as_of or health["as_of"])
    files, p = build(a.root, health, accepted, as_of)
    for rid, what, why in p.rows:
        print(f"change {rid}: {what} ({why})")
    for rid, text in p.notes:
        print(f"for a person {rid}: {text}")
    if a.write:
        for rel, text in files.items():
            (a.root / rel).write_text(text, encoding="utf-8")
    if a.body:
        Path(a.body).parent.mkdir(parents=True, exist_ok=True)
        Path(a.body).write_text(body(health, files, p), encoding="utf-8")
    print(f"{len(p.rows)} change(s) in {len(files)} file(s); {len(p.notes)} for a person"
          + ("" if a.write or not files else " (dry run: --write to apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
