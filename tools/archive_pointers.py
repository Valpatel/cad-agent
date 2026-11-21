#!/usr/bin/env python3
"""Add offline-mirror ``archive`` pointers to the reference registry from a mirror manifest (#323).

An offline mirror of the registry's sources is kept outside this repo. Its manifest is a JSONL file, one object per
line: ``{"url": ..., "sha256": <64 hex>, "fetched": "YYYY-MM-DD", "kind": "pdf" | "html" | ...}``. This tool gives every
registry record whose ``url`` is a manifest url (exactly, or equal once the ``#fragment`` is dropped) the pointer the
registry already supports::

    archive:
      sha256: <the mirrored bytes' SHA256>
      kind: pdf
      fetched: 'YYYY-MM-DD'
      redistribute: false

It is a pointer, never a path or a host: the manifest itself stays out of the repo. ``redistribute`` is always false
(the registry's terms: cited, never copied or redistributed). Rules:

* a record that already has an ``archive`` is never changed. A different sha256 in the manifest is reported as a
  mismatch for a person (the page changed since, or the mirror holds other bytes);
* a manifest line that is not valid (bad JSON, a non-http url, a sha256 that is not 64 hex digits, a date that is not
  ``YYYY-MM-DD``, a kind that is not a short lowercase word) is skipped and counted. Of two lines for one url the later
  ``fetched`` wins; two different sha256 values on the same day are a conflict and neither is used. Distinct usable URLs sharing a digest are listed for review;
* the pointer goes right after the record's ``verified`` or ``summary`` (whichever comes later), else at its end, as
  the existing pointers sit;
* schema-2 shards (``docs/research/references/*.yaml``) are rewritten through ``tools/import_refmap.py``'s ``dump``, so
  the exact parse/dump round-trip that ``tools/references_health_apply.py`` needs still holds (a shard not in that
  layout is left alone and reported). The hand-formatted core file (``docs/research/references.yaml``, its ``sources``
  only) is edited by inserting lines, keeping its comments; the result is parsed again and must equal the old data
  plus the pointers, or nothing is written.

Nothing is fetched. Rerun it with a fresh manifest whenever the mirror grows, as a resource update PR::

    python3 tools/archive_pointers.py --manifest <outside-the-repo>/manifest.jsonl          # dry run: counts per file
    python3 tools/archive_pointers.py --manifest <outside-the-repo>/manifest.jsonl --write  # apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urldefrag

from yaml import YAMLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))
from cadagent.review import references as refs  # noqa: E402


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ir = _tool("import_refmap")            # the shards' writer
ha = _tool("references_health_apply")  # split_head / editable: the round-trip the weekly bot needs
CORE = "docs/research/references.yaml"
KIND = re.compile(r"[a-z][a-z0-9-]{0,15}")
NOT_PLAIN = {"null", "true", "false", "yes", "no", "on", "off", "y", "n"}   # YAML would read these as other types
AFTER = ("verified", "summary")


# ----------------------------------------------------------------------------- the manifest

def _entry(line: str) -> Optional[Dict[str, str]]:
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    url, sha, fetched, kind = (d.get(k) for k in ("url", "sha256", "fetched", "kind"))
    if not (isinstance(url, str) and url.startswith(("https://", "http://")) and not any(c.isspace() for c in url)):
        return None
    if not (isinstance(sha, str) and refs.SHA256.fullmatch(sha)):
        return None
    try:
        if not (isinstance(fetched, str) and dt.date.fromisoformat(fetched).isoformat() == fetched):
            return None
    except ValueError:
        return None
    if not (isinstance(kind, str) and KIND.fullmatch(kind) and kind not in NOT_PLAIN):
        return None
    return {"url": url, "sha256": sha, "fetched": fetched, "kind": kind}


def read_manifest(path: Path) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Any]]:
    """({url: entry}, counts: lines, malformed, and the conflicting urls). Blank lines are ignored; malformed ones are
    counted, never fatal."""
    by_url: Dict[str, Dict[str, str]] = {}
    conflicts: set = set()
    counts: Dict[str, Any] = {"lines": 0, "malformed": 0, "conflicting": []}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        counts["lines"] += 1
        e = _entry(line)
        if e is None:
            counts["malformed"] += 1
            continue
        old = by_url.get(e["url"])
        if old is None or e["fetched"] > old["fetched"]:
            by_url[e["url"]] = e
            conflicts.discard(e["url"])
        elif e["fetched"] == old["fetched"] and e["sha256"] != old["sha256"]:
            conflicts.add(e["url"])
    for url in conflicts:
        del by_url[url]
    counts["conflicting"] = sorted(conflicts)
    return by_url, counts


def matcher(by_url: Dict[str, Dict[str, str]]):
    """url -> manifest entry: the exact url first, else the one equal once both lose their #fragment."""
    defrag: Dict[str, Optional[Dict[str, str]]] = {}
    for url, e in by_url.items():
        key = urldefrag(url)[0]
        if key in defrag and defrag[key] is not None and defrag[key]["sha256"] != e["sha256"]:
            defrag[key] = None                     # two different fragments, two different files: ambiguous
        else:
            defrag.setdefault(key, e)

    def match(url: Any) -> Optional[Dict[str, str]]:
        if not isinstance(url, str):
            return None
        return by_url.get(url) or defrag.get(urldefrag(url)[0])
    return match


def pointer(e: Dict[str, str]) -> Dict[str, Any]:
    return {"sha256": e["sha256"], "kind": e["kind"], "fetched": e["fetched"], "redistribute": False}


def with_archive(rec: Dict[str, Any], arch: Dict[str, Any]) -> Dict[str, Any]:
    """The record with ``archive`` after its later ``verified``/``summary`` key, else at its end."""
    keys = list(rec)
    at = max((keys.index(k) for k in AFTER if k in rec), default=len(keys) - 1)
    out: Dict[str, Any] = {}
    for i, k in enumerate(keys):
        out[k] = rec[k]
        if i == at:
            out["archive"] = arch
    return out


# ----------------------------------------------------------------------------- planning

class Report:
    def __init__(self):
        self.files: Dict[str, Dict[str, int]] = {}
        self.mismatches: List[Tuple[str, str, str, str]] = []    # (file, id, registry sha, manifest sha)
        self.notes: List[str] = []

    def count(self, f: str, what: str) -> None:
        row = self.files.setdefault(f, {"added": 0, "already": 0, "mismatch": 0})
        row[what] += 1


def _plan(records: List[Any], match, f: str, rep: Report) -> Dict[str, Dict[str, Any]]:
    """{record id: pointer to add} for one file's records."""
    out = {}
    for r in records:
        if not isinstance(r, dict) or r.get("extends") or not isinstance(r.get("id"), str):
            continue
        e = match(r.get("url"))
        if e is None:
            continue
        old = r.get("archive")
        if old is not None:
            if isinstance(old, dict) and old.get("sha256") == e["sha256"]:
                rep.count(f, "already")
            else:
                rep.count(f, "mismatch")
                rep.mismatches.append((f, r["id"], str((old or {}).get("sha256") if isinstance(old, dict) else old),
                                       e["sha256"]))
            continue
        out[r["id"]] = pointer(e)
        rep.count(f, "added")
    return out


def shard_text(text: str, adds: Dict[str, Dict[str, Any]]) -> str:
    head, body = ha.split_head(text)
    doc = refs._yaml(body)
    doc["sources"] = [with_archive(r, adds[r["id"]]) if isinstance(r, dict) and r.get("id") in adds else r
                      for r in doc.get("sources") or []]
    return head + ir.dump(doc)


# ----------------------------------------------------------------------------- the hand-formatted core file

RECORD = re.compile(r"^(\s*)- id:\s*(\S+)\s*$")


def core_text(text: str, adds: Dict[str, Dict[str, Any]]) -> str:
    """The core file with each pointer inserted as lines inside its record of ``sources``; everything else, comments
    included, byte for byte. Raises ValueError when the result would not parse to the old data plus the pointers."""
    lines = text.splitlines(True)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == "sources:") + 1
    except StopIteration:
        raise ValueError("no top-level `sources:` in the core file")
    end = next((i for i in range(start, len(lines)) if re.match(r"[A-Za-z_]", lines[i])), len(lines))
    starts = [(i, m.group(1), m.group(2)) for i in range(start, end) for m in [RECORD.match(lines[i])] if m]
    inserts: List[Tuple[int, str]] = []
    for n, (i, indent, rid) in enumerate(starts):
        if rid not in adds:
            continue
        stop = starts[n + 1][0] if n + 1 < len(starts) else end
        field = indent + "  "
        keys: Dict[str, Tuple[int, int]] = {}                       # key -> (first line, line after its value)
        last = i + 1
        k = i + 1
        while k < stop:
            m = re.match(re.escape(field) + r"([A-Za-z_][\w-]*):", lines[k])
            if m:
                j = k + 1
                while j < stop and lines[j].strip() and not lines[j].lstrip().startswith("#") and (
                        len(lines[j]) - len(lines[j].lstrip(" ")) > len(field)
                        or lines[j].startswith(field + "- ")):
                    j += 1
                keys[m.group(1)] = (k, j)
                last = j
                k = j
            else:
                k += 1
        after = [keys[k2] for k2 in AFTER if k2 in keys]
        at = max(after)[1] if after else last
        block = ir.dump({"archive": adds[rid]})
        inserts.append((at, "".join(field + ln + "\n" for ln in block.splitlines())))
    for at, block in sorted(inserts, reverse=True):
        lines.insert(at, block)
    new = "".join(lines)
    # the proof: the new file parses to the old data with exactly these pointers added, at the right place
    old_doc = refs._yaml(text)
    try:
        new_doc = refs._yaml(new)
    except YAMLError as err:
        raise ValueError("inserting the pointers would produce invalid YAML") from err
    want = dict(old_doc)
    want["sources"] = [with_archive(r, adds[r["id"]]) if isinstance(r, dict) and r.get("id") in adds else r
                       for r in old_doc.get("sources") or []]
    if new_doc != want or [list(r) for r in new_doc["sources"] if isinstance(r, dict)] != [
            list(r) for r in want["sources"] if isinstance(r, dict)]:
        raise ValueError("inserting the pointers into the core file would change more than the pointers")
    return new


# ----------------------------------------------------------------------------- the run

def build(root: Path, by_url: Dict[str, Dict[str, str]]) -> Tuple[Dict[str, str], Report]:
    """({repo-relative path: new text} for every file that gains a pointer, the report)."""
    rep, out = Report(), {}
    match = matcher(by_url)
    core = root / CORE
    if core.is_file():
        text = core.read_text(encoding="utf-8")
        adds = _plan(refs._yaml(text).get("sources") or [], match, CORE, rep)
        if adds:
            try:
                out[CORE] = core_text(text, adds)
            except ValueError as err:
                rep.notes.append(f"{CORE}: left alone, {err}")
                rep.files[CORE]["added"] = 0
    folder = refs.shard_folder(core)
    for path in sorted(folder.glob("*.yaml")) if folder.is_dir() else []:
        if path.name in refs.NOT_SHARDS:
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        doc = refs._yaml(ha.split_head(text)[1]) or {}
        adds = _plan(doc.get("sources") or [] if isinstance(doc, dict) else [], match, rel, rep)
        if not adds:
            continue
        if not ha.editable(text):
            rep.notes.append(f"{rel}: not in the importer's layout, so its {len(adds)} pointer(s) were left out")
            rep.files[rel]["added"] = 0
            continue
        out[rel] = shard_text(text, adds)
    return out, rep


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path, help="the mirror's JSONL manifest (kept out of the repo)")
    ap.add_argument("--root", type=Path, default=ROOT, help="the cad-agent checkout to edit (default: this one)")
    ap.add_argument("--write", action="store_true", help="write the pointers (default: a dry run that prints counts)")
    a = ap.parse_args(argv)
    by_url, counts = read_manifest(a.manifest)
    files, rep = build(a.root, by_url)
    print(f"manifest: {counts['lines']} lines, {len(by_url)} urls usable, {counts['malformed']} malformed (skipped), "
          f"{len(counts['conflicting'])} with conflicting sha256 on one day (skipped)")
    for url in counts["conflicting"]:
        print(f"conflict: {url} has two sha256 values fetched on the same day; neither is used")
    urls_by_sha: Dict[str, List[str]] = {}
    for url, record in by_url.items():
        urls_by_sha.setdefault(record["sha256"], []).append(url)
    for sha, urls in sorted(urls_by_sha.items()):
        if len(urls) > 1:
            print(f"shared sha256 {sha}: {', '.join(sorted(urls))}")
    total = {"added": 0, "already": 0, "mismatch": 0}
    for f, row in sorted(rep.files.items()):
        print(f"{f}: {row['added']} added, {row['already']} already archived, {row['mismatch']} mismatched")
        for k in total:
            total[k] += row[k]
    for f, rid, old, new in rep.mismatches:
        print(f"mismatch {f} {rid}: the registry has {old}, the manifest {new}; left as it is, for a person")
    for note in rep.notes:
        print(f"note: {note}")
    if a.write:
        for rel, text in files.items():
            (a.root / rel).write_text(text, encoding="utf-8")
    print(f"{total['added']} pointer(s) in {len(files)} file(s); {total['already']} already archived, "
          f"{total['mismatch']} mismatched" + ("" if a.write or not files else " (dry run: --write to apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
