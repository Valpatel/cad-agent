"""tools/references_health_apply.py (#323 phase 4): the weekly bot PR's edits from a health report. Each rule (lower a
dead record one rung, follow a permanent same-site move, unconfirm a claim whose only corroborator changed) on a copy
of the registry, its idempotence, and the cases it leaves for a person. Offline."""
import datetime as dt
import difflib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("references_health_apply", ROOT / "tools" / "references_health_apply.py")
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)
ra, ir, refs = app.ra, app.ir, app.refs

AS_OF = dt.date(2026, 11, 16)
SHARD = "research/references/guides-inserts.yaml"


@pytest.fixture
def root(tmp_path):
    for rel in ("research/references.yaml", "docs/areas.yaml", "research/process-profiles.yaml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    shutil.copytree(ROOT / "research/references", tmp_path / "research/references")
    return tmp_path


def shard(root, rel=SHARD):
    head, body = app.split_head((root / rel).read_text())
    return head, refs._yaml(body)


def save(root, head, doc, rel=SHARD):
    (root / rel).write_text(head + ir.dump(doc))


def recs(doc):
    return doc["sources"]


def promote(root, i=0, **extra):
    """Make the i-th record of the inserts shard a read source; return its id and url."""
    head, doc = shard(root)
    r = recs(doc)[i]
    r["evidence"]["class"] = "read"
    r["verified"] = "2026-11-01: read the page at source"
    r.pop("confidence", None)
    r.update(extra)
    save(root, head, doc)
    return r["id"], r["url"]


def entry(url, status, runs, since="2026-11-09", **kw):
    down = dict(down_since=since, down_runs=runs) if status in ra.DOWN else {}
    return dict(url=url, checked=AS_OF.isoformat(), status=status, streak=dict(key=status, status=status, since=since, runs=runs),
                **{**down, **kw})


def health(**records):
    return {"schema": ra.HEALTH_SCHEMA, "as_of": AS_OF.isoformat(), "revision": "f" * 40, "records": records}


def apply(root, h, accepted=(), cited=()):
    files, p = app.build(root, h, list(accepted), AS_OF, set(cited))
    for rel, text in files.items():
        (root / rel).write_text(text)
    return files, p


def record(root, rid):
    return refs.load(root / "research/references.yaml").entries[rid]


def test_a_dead_link_lowers_the_class_once_per_outage(root):
    rid, url = promote(root)
    files, p = apply(root, health(**{rid: entry(url, "gone", 2, http=[404])}))
    assert list(files) == [SHARD] and [r[0] for r in p.rows] == [rid]
    ev = record(root, rid).get("evidence")
    assert ev["class"] == "snippet-only" and ev["lowered"]["from"] == "read" and ev["lowered"]["date"] == AS_OF.isoformat()
    assert "gone: gone or unreachable on 2 checks in a row since 2026-11-09 (HTTP 404)" == ev["lowered"]["why"]
    assert not [x for x in refs.load(root / "research/references.yaml").problems(root=root) if x.startswith(rid)]
    # the next week, still gone: already lowered for this outage
    files, p = apply(root, health(**{rid: entry(url, "gone", 3, http=[404])}))
    assert files == {} and p.rows == []


def test_the_rest_of_the_shard_is_untouched(root):
    rid, url = promote(root)
    before = (root / SHARD).read_text().splitlines()
    apply(root, health(**{rid: entry(url, "unreachable", 2)}))
    after = (root / SHARD).read_text().splitlines()
    changed = [ln for ln in difflib.unified_diff(before, after, lineterm="", n=0) if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    assert changed and all("class:" in ln or "lowered" in ln or "from:" in ln or "date:" in ln or "why:" in ln for ln in changed)


@pytest.mark.parametrize("runs, status", [(1, "gone"), (2, "blocked"), (2, "ok")])
def test_one_check_or_a_blocked_host_changes_nothing(root, runs, status):
    rid, url = promote(root)
    files, p = apply(root, health(**{rid: entry(url, status, runs)}))
    assert files == {} and p.rows == []


def test_an_accepted_soft_404_is_not_dead(root):
    rid, url = promote(root)
    e = entry(url, "gone", 2, soft404=["title"])
    f = ra.soft404_finding(rid, "title")
    acc = [dict(check=f["check"], subject=f["subject"], fp=f["fp"], reason="fine", accepted="2026-11-09")]
    assert apply(root, health(**{rid: e}), accepted=acc)[0] == {}
    assert apply(root, health(**{rid: e}))[1].rows                     # not accepted: lowered


def test_snippet_only_core_and_cited_records_are_left_for_a_person(root):
    _, doc = shard(root)
    snip = recs(doc)[1]
    rid, url = promote(root)
    core = next(r for r in refs.load(root / "research/references.yaml").entries.values()
                if r.file == "research/references.yaml" and r.kind == "source" and r.get("url"))
    h = health(**{rid: entry(url, "gone", 2), snip["id"]: entry(snip["url"], "gone", 2),
                  core.id: entry(core["url"], "gone", 2)})
    files, p = apply(root, h, cited={rid})
    assert files == {} and p.rows == []
    notes = dict(p.notes)
    assert "cited" in notes[rid] and "core entry" in notes[core.id] and snip["id"] not in notes


def test_an_edit_that_would_fail_the_registry_check_is_left_out(root):
    # read -> snippet-only with used_for outside research/ breaks the ladder rule: the bot must not write it
    rid, url = promote(root, used_for=["docs/inserts.md"])
    files, p = apply(root, health(**{rid: entry(url, "gone", 2)}))
    assert files == {} and p.rows == [] and "left out" in dict(p.notes)[rid]


def test_a_permanent_same_site_move_updates_the_link(root):
    head, doc = shard(root)
    r = recs(doc)[0]
    rid, old = r["id"], r["url"]
    new = f"https://{ra.host(old)}/blog/heat-set-inserts-moved"
    files, p = apply(root, health(**{rid: entry(old, "moved", 2, final_url=new, permanent=True)}))
    got = record(root, rid)
    assert got["url"] == new and got["mirrors"] == [old] and p.rows[0][1].startswith("url -> ")
    # once moved, the old report describes another link: nothing more to do
    assert apply(root, health(**{rid: entry(old, "moved", 3, final_url=new, permanent=True)}))[0] == {}


@pytest.mark.parametrize("final, permanent, why", [
    ("https://elsewhere.example.org/page", True, "same site"),
    ("http://{host}/page", True, "https"),
    ("https://{host}/other", False, "permanent")])
def test_other_moves_are_listed_not_applied(root, final, permanent, why):
    _, doc = shard(root)
    r = recs(doc)[0]
    final = final.format(host=ra.host(r["url"]))
    files, p = apply(root, health(**{r["id"]: entry(r["url"], "moved", 2, final_url=final, permanent=permanent)}))
    assert files == {} and why in dict(p.notes)[r["id"]]


def test_a_changed_page_unconfirms_the_claims_it_alone_corroborates(root):
    head, doc = shard(root)
    # catalogued records: the shard's promoted ones (#323 sweeps) are not this rule's case
    x, z, w = [r for r in recs(doc) if r["evidence"].get("class") == "snippet-only"][:3]
    z["claims"] = [{"text": "Hole 4.0 mm for M3", "status": "corroborated", "evidence": "x agrees", "corroborated_by": [x["id"]]},
                   {"text": "Depth 2 d", "status": "corroborated", "corroborated_by": [x["id"], w["id"]]}]
    save(root, head, doc)
    h = health(**{x["id"]: entry(x["url"], "ok", 1, changed_on="2026-11-16", sha256="a" * 64)})
    files, p = apply(root, h)
    claims = record(root, z["id"]).get("claims")
    assert claims[0]["status"] == "unconfirmed" and "2026-11-16: the page of " + x["id"] + " changed" in claims[0]["evidence"]
    assert claims[1]["status"] == "corroborated"                      # two corroborators: not this rule's case
    assert record(root, x["id"]).get("evidence")["class"] == "snippet-only"    # the class stays
    # corroborated again after a re-read: the same change does not undo it
    head, doc = shard(root)
    next(r for r in recs(doc) if r["id"] == z["id"])["claims"][0]["status"] = "corroborated"
    save(root, head, doc)
    assert apply(root, h)[0] == {}


def test_a_hand_styled_shard_is_left_alone(root):
    rid, url = promote(root)
    (root / SHARD).write_text((root / SHARD).read_text().replace("schema: 2\n", "schema: 2   # hand edit\n", 1))
    files, p = apply(root, health(**{rid: entry(url, "gone", 2)}))
    assert files == {} and "importer's layout" in dict(p.notes)[rid]


def test_every_real_shard_is_editable():
    for f in sorted((ROOT / "research/references").glob("*.yaml")):
        if f.name not in refs.NOT_SHARDS:
            assert app.editable(f.read_text()), f.name


def test_lowered_is_validated(root):
    rid, url = promote(root)
    head, doc = shard(root)
    r = next(r for r in recs(doc) if r["id"] == rid)
    r["evidence"]["lowered"] = {"from": "snippet-only", "date": "2026-11-16", "why": "x"}
    save(root, head, doc)
    probs = [x for x in refs.load(root / "research/references.yaml").problems(root=root) if x.startswith(rid)]
    assert any("lowered.from snippet-only is not above" in x for x in probs)


def test_the_cli_writes_the_body_and_mentions_nobody(root, tmp_path):
    rid, url = promote(root)
    hp = tmp_path / "h.json"
    hp.write_text(json.dumps(health(**{rid: entry(url, "gone", 2, http=[404])})))
    body = tmp_path / "pr.md"
    assert app.main(["--health", str(hp), "--root", str(root), "--write", "--body", str(body)]) == 0
    text = body.read_text()
    assert f"`{rid}`" in text and "evidence.class read -> snippet-only" in text and SHARD in text
    assert record(root, rid).get("evidence")["class"] == "snippet-only"


def test_once_per_outage_is_counted_from_the_last_good_check(root):
    """The streak restarted (a blocked or unreachable check in between), but the outage did not: no second rung."""
    rid, url = promote(root)
    apply(root, health(**{rid: entry(url, "gone", 2, since="2026-11-02")}))
    assert record(root, rid).get("evidence")["class"] == "snippet-only"
    head, doc = shard(root)
    r = next(r for r in recs(doc) if r["id"] == rid)
    r["evidence"]["class"], r["evidence"]["lowered"]["from"] = "read", "verified-at-source"    # as if it had fallen from v-a-s
    r["evidence"]["lowered"]["date"] = "2026-11-16"
    save(root, head, doc)
    e = entry(url, "gone", 2, since="2026-11-30", down_since="2026-11-02", down_runs=5)   # new streak, same outage
    assert apply(root, health(**{rid: e}))[0] == {}
    e = entry(url, "gone", 2, since="2026-11-30", down_since="2026-11-30", down_runs=2)   # a new outage after an ok check
    assert apply(root, health(**{rid: e}))[1].rows


@pytest.mark.parametrize("path", ["/", "", "/search?q=x"])
def test_a_move_to_a_home_or_search_page_is_never_applied(root, path):
    _, doc = shard(root)
    r = recs(doc)[0]
    final = f"https://{ra.host(r['url'])}{path}"
    files, p = apply(root, health(**{r["id"]: entry(r["url"], "moved", 2, final_url=final, permanent=True)}))
    assert files == {} and "home or search page" in dict(p.notes)[r["id"]]


def test_a_claim_re_read_after_the_change_is_left_alone(root):
    head, doc = shard(root)
    x, z = recs(doc)[0], recs(doc)[1]
    z["claims"] = [{"text": "Hole 4.0 mm", "status": "corroborated", "evidence": "re-read, still agrees",
                    "corroborated_by": [x["id"]]}]
    z["verified"] = "2026-11-17: re-read both pages"           # a person's date, after the change
    save(root, head, doc)
    h = health(**{x["id"]: entry(x["url"], "ok", 1, changed_on="2026-11-16")})
    assert apply(root, h)[0] == {}
