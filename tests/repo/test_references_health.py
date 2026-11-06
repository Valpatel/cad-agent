"""The reference health check (#323 phase 4): `tools/resource_audit.py references` against a local HTTP fixture server
(200, 304, 404, soft-404s, redirect chains, 403 and 429 with backoff, a changed body, a PDF) and a GitHub API stub.
Nothing here reaches the internet: every URL is 127.0.0.1."""
import datetime as dt
import importlib.util
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("resource_audit", ROOT / "tools" / "resource_audit.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

DAY1, DAY2, DAY3 = dt.date(2026, 11, 9), dt.date(2026, 11, 16), dt.date(2026, 11, 23)
PAGE = ("<!doctype html><html><head><title>{title}</title><script>var t = {noise};</script></head><body>"
        "<nav>Menu {noise}</nav><h1>{h1}</h1><p>{text}</p>" + "<p>Steady text for the size test.</p>" * 80 +
        "<footer>(c) {noise}</footer></body></html>")


def page(title="Heat-set inserts", h1="Heat-set inserts", text="Hole 4.0 mm for M3.", noise=0):
    return PAGE.format(title=title, h1=h1, text=text, noise=noise).encode()


class Site:
    """Routes: path -> callable(handler) -> (status, headers, body). `hits` counts requests per path."""

    def __init__(self):
        self.hits, self.version, self.times = {}, 1, []
        self.routes = {
            "/ok": self.ok,
            "/gone": lambda h: (404, {}, b"no"),
            "/old": lambda h: (301, {"Location": "/new"}, b""),
            "/new": lambda h: (200, {}, page(title="New home")),
            "/chain": lambda h: (302, {"Location": "/chain2"}, b""),
            "/chain2": lambda h: (301, {"Location": "/ok"}, b""),
            "/temp": lambda h: (302, {"Location": "/new"}, b""),
            "/to-root": lambda h: (301, {"Location": "/"}, b""),
            "/": lambda h: (304, {"ETag": '"home"'}, b"") if h.headers.get("If-None-Match") == '"home"'
                 else (200, {"ETag": '"home"'}, page(title="Welcome")),
            "/notfound-etag": lambda h: (304, {"ETag": '"nf"'}, b"") if h.headers.get("If-None-Match") == '"nf"'
                              else (200, {"ETag": '"nf"'}, page(title="Page not found", h1="Oops")),
            "/maintenance": lambda h: (503, {"Retry-After": "7200"}, b""),
            "/to-search": lambda h: (302, {"Location": "/search?q=inserts"}, b""),
            "/search": lambda h: (200, {}, page(title="Search")),
            "/soft": lambda h: (200, {}, page(title="Page not found", h1="Oops")),
            "/to-tiny": lambda h: (301, {"Location": "/tiny"}, b""),
            "/tiny": lambda h: (200, {"Content-Type": "text/html"}, b"<html><body>hi</body></html>"),
            "/forbidden": lambda h: (403, {}, b"no robots"),
            "/forbidden2": lambda h: (403, {}, b"no robots"),
            "/limited": self.limited,
            "/hard-limit": lambda h: (429, {"Retry-After": "3600"}, b""),
            "/flaky": lambda h: (503, {}, b""),
            "/doc.pdf": lambda h: (200, {"Content-Type": "application/pdf"}, b"%PDF-1.7\n" + b"x" * 5000),
        }

    def ok(self, h):
        etag = f'"v{self.version}"'
        if h.headers.get("If-None-Match") == etag:
            return 304, {"ETag": etag}, b""
        return 200, {"ETag": etag, "Last-Modified": "Tue, 14 May 2024 10:21:00 GMT", "Content-Type": "text/html; charset=utf-8"}, \
            page(text=f"Hole {3 + self.version}.0 mm for M3.", noise=self.version * 7)

    def limited(self, h):
        if self.hits["/limited"] == 1:               # the first request: wait a second, please
            return 429, {"Retry-After": "1"}, b""
        return 200, {}, page(title="Limited but fine")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        site = self.server.site
        path = self.path.split("?")[0]
        site.hits[path] = site.hits.get(path, 0) + 1
        site.times.append((path, time.monotonic()))
        status, headers, body = site.routes.get(path, lambda h: (404, {}, b""))(self)
        self.send_response(status)
        headers.setdefault("Content-Type", "text/html; charset=utf-8")
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class GitHubStub(BaseHTTPRequestHandler):
    """repos/o/live (fine), repos/o/old (renamed to o/new), repos/o/gone (404), repos/o/arch (archived, Apache-2.0)."""
    LIMITED = "o/limited"             # answers 403 "API rate limit exceeded", as GitHub does
    REPOS = {
        "o/live": dict(full_name="o/live", archived=False, pushed_at="2026-10-01T00:00:00Z", license={"spdx_id": "MIT"}),
        "o/old": dict(full_name="o/new", archived=False, pushed_at="2026-10-01T00:00:00Z", license={"spdx_id": "MIT"}),
        "o/arch": dict(full_name="o/arch", archived=True, pushed_at="2023-01-01T00:00:00Z", license={"spdx_id": "Apache-2.0"}),
    }

    def do_GET(self):  # noqa: N802
        self.server.site.hits[self.path] = self.server.site.hits.get(self.path, 0) + 1
        assert self.headers.get("Authorization") == "Bearer test-token"
        parts = self.path.strip("/").split("/")
        body, status = None, 404
        if parts[0] == "repos" and len(parts) == 3 and f"{parts[1]}/{parts[2]}" == self.LIMITED:
            status, body = 403, {"message": "API rate limit exceeded"}
        elif parts[0] == "repos" and len(parts) == 3:
            r = self.REPOS.get(f"{parts[1]}/{parts[2]}")
            if r:
                status, body = 200, dict(r, private=False, disabled=False, default_branch="main", stargazers_count=1)
        elif parts[0] == "repos" and parts[3:] == ["git", "ref", "heads", "main"]:
            status, body = 200, {"object": {"sha": "c" * 40}}
        data = json.dumps(body or {"message": "Not Found"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.site = Site()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture(scope="module")
def servers():
    web, api = serve(_Handler), serve(GitHubStub)
    yield web, api
    web.shutdown()
    api.shutdown()


@pytest.fixture
def site(servers):
    web, _ = servers
    web.site.__init__()
    return web


def base(srv):
    return f"http://127.0.0.1:{srv.server_address[1]}"


def net_for(api_srv):
    net = ra.Net(timeout=5)
    net.token, net.gh, net.api = "test-token", None, base(api_srv)
    return net


class FakeClock:
    """A pacer clock that never sleeps for real: sleep() moves time on."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def recs(srv, *paths, gh=()):
    out = [dict(id=f"r{p.strip('/').replace('/', '-').replace('.', '-') or 'root'}", url=base(srv) + p, file="docs/research/references/x.yaml",
                kind="catalogued", evidence="snippet-only", activity=None, spdx=None, claims=False) for p in paths]
    out += [dict(id=f"gh-{s.replace('/', '-')}", url=f"https://github.com/{s}", file="docs/research/references/p.yaml",
                 kind="catalogued", evidence="snippet-only", activity="active", spdx=lic, claims=False) for s, lic in gh]
    return out


def run(servers, records, state, as_of=DAY1, limit=100, pacer=None):
    web, api = servers
    return ra.check_references(net_for(api), records, state, as_of, limit, pacer or ra.Pacer(0.01), workers=4)


def test_statuses_from_the_fixture_server(servers, site):
    rs = recs(site, "/ok", "/gone", "/old", "/chain", "/temp", "/flaky", "/doc.pdf")
    st = run(servers, rs, {})["records"]
    by = {r["url"].rsplit("/", 1)[1]: st[r["id"]] for r in rs}
    assert by["ok"]["status"] == "ok" and by["ok"]["etag"] == '"v1"' and len(by["ok"]["sha256"]) == 64
    assert by["gone"]["status"] == "gone" and by["gone"]["http"] == [404]
    assert by["old"]["status"] == "moved" and by["old"]["permanent"] is True and by["old"]["final_url"].endswith("/new")
    # a 302 then a 301: moved, but not permanently (the bot PR leaves it to a person)
    assert by["chain"]["status"] == "moved" and by["chain"]["permanent"] is False and by["chain"]["http"] == [302, 301, 200]
    assert by["temp"]["status"] == "ok" and by["temp"]["final_url"].endswith("/new")      # temporary only: not moved
    assert by["flaky"]["status"] == "unknown" and by["flaky"]["http"] == [503]     # the server's trouble: not counted
    assert by["doc.pdf"]["kind"] == "pdf" and by["doc.pdf"]["bytes"] == 5009


def test_conditional_request_gets_304_and_keeps_the_hash(servers, site):
    rs = recs(site, "/ok")
    state = run(servers, rs, {}, DAY1)
    first = dict(state["records"][rs[0]["id"]])
    state = run(servers, rs, state, DAY2)
    again = state["records"][rs[0]["id"]]
    assert again["http"] == [304] and again["status"] == "ok"
    assert again["sha256"] == first["sha256"] and again["etag"] == first["etag"] and again["checked"] == DAY2.isoformat()
    assert again["streak"] == dict(key="ok", status="ok", since=DAY1.isoformat(), runs=2)


def test_noise_is_normalised_away_but_a_changed_text_is_seen(servers, site):
    rs = recs(site, "/ok")
    state = run(servers, rs, {}, DAY1)
    sha = state["records"][rs[0]["id"]]["sha256"]
    # the same visible text with other script, nav and footer noise hashes the same
    assert ra.content_hash(page(text="Hole 4.0 mm for M3.", noise=99), "text/html")[1] == sha
    site.site.version = 2                        # new ETag and new text
    state = run(servers, rs, state, DAY2)
    e = state["records"][rs[0]["id"]]
    assert e["status"] == "changed" and e["changed_on"] == DAY2.isoformat() and e["sha256"] != sha
    state = run(servers, rs, state, DAY3)       # 304 now: unchanged since, but the change date stays
    e = state["records"][rs[0]["id"]]
    assert e["status"] == "ok" and e["changed_on"] == DAY2.isoformat()


@pytest.mark.parametrize("path, reason", [("/to-root", "root"), ("/to-search", "search"), ("/soft", "title"),
                                          ("/to-tiny", "tiny")])
def test_soft_404s(servers, site, path, reason):
    rs = recs(site, path)
    e = run(servers, rs, {})["records"][rs[0]["id"]]
    assert e["status"] == "gone" and reason in e["soft404"]


def test_a_soft_404_finding_can_be_accepted_by_fingerprint(servers, site):
    rs = recs(site, "/soft")
    state = run(servers, rs, {})
    r = ra.health_report(ROOT, rs, state, DAY1, [], "online")
    f = next(f for f in r["findings"] if f["check"] == "ref-soft-404")
    assert r["records"][rs[0]["id"]]["effective"] == "gone"
    acc = [dict(check=f["check"], subject=f["subject"], fp=f["fp"], reason="the page is fine", accepted="2026-11-09")]
    r2 = ra.health_report(ROOT, rs, state, DAY1, acc, "online")
    f2 = next(f for f in r2["findings"] if f["check"] == "ref-soft-404")
    assert f2["accepted"] and r2["records"][rs[0]["id"]]["effective"] == "ok"
    assert ra.effective_status(rs[0]["id"], state["records"][rs[0]["id"]], acc) == "ok"


def test_politeness_one_request_a_second_per_host(servers, site):
    rs = recs(site, "/ok", "/gone", "/new", "/old")         # /old redirects: two requests
    clock = FakeClock()
    pacer = ra.Pacer(1.0, clock=clock, sleep=clock.sleep)
    run(servers, rs, {}, pacer=pacer)
    times = sorted(t for h, t in pacer.log if h == "127.0.0.1")
    assert len(times) == 5
    assert all(b - a >= 1.0 - 1e-9 for a, b in zip(times, times[1:]))


def test_real_clock_spacing_and_retry_after_is_honoured(servers, site):
    rs = recs(site, "/limited")
    t0 = time.monotonic()
    e = run(servers, rs, {}, pacer=ra.Pacer(0.2))["records"][rs[0]["id"]]
    assert e["status"] == "ok" and time.monotonic() - t0 >= 0.95
    assert site.site.hits["/limited"] == 2


def test_a_long_retry_after_defers_the_host_for_this_run(servers, site):
    rs = recs(site, "/hard-limit", "/ok")
    rs[0]["id"] = "a-first"                     # checked first on its host
    state = run(servers, rs, {})
    assert state["records"]["a-first"]["status"] == "blocked" and state["records"]["a-first"]["http"] == [429]
    assert rs[1]["id"] not in state["records"] and state["deferred"] == ["127.0.0.1"]
    assert site.site.hits.get("/ok") is None and state["hosts"] == {}      # deferred this run, not blocked for 30 days


def test_403_blocks_the_host_for_30_days_and_is_not_retried(servers, site):
    rs = recs(site, "/forbidden", "/forbidden2")
    state = run(servers, rs, {}, DAY1)
    assert state["hosts"]["127.0.0.1"]["blocked_until"] == (DAY1 + dt.timedelta(days=30)).isoformat()
    hits = dict(site.site.hits)
    assert hits == {"/forbidden": 1}                               # one 403, no retry; the host is left alone this run too
    assert state["deferred"] == ["127.0.0.1"] and rs[1]["id"] not in state["records"]
    state = run(servers, rs, state, DAY2)
    assert site.site.hits == hits and state["checked"] == [] and sorted(state["held"]) == sorted(r["id"] for r in rs)
    assert state["records"][rs[0]["id"]]["checked"] == DAY1.isoformat()    # kept, with its date
    state = run(servers, rs, state, DAY1 + dt.timedelta(days=31))
    assert sum(site.site.hits.values()) == 2                       # 30 days on: checked again (the never-checked one first)
    assert state["records"][rs[1]["id"]]["status"] == "blocked"


def test_rotation_checks_the_longest_unchecked_first(servers, site):
    rs = recs(site, "/ok", "/new", "/gone", "/doc.pdf")
    state = run(servers, rs, {}, DAY1, limit=2)
    first = list(state["checked"])
    assert len(first) == 2 and first == sorted(r["id"] for r in rs)[:2]
    state = run(servers, rs, state, DAY2, limit=2)
    assert set(state["checked"]).isdisjoint(first) and len(state["records"]) == 4
    state = run(servers, rs, state, DAY3, limit=2)
    assert state["checked"] == first


def test_github_repositories_through_the_api_stub(servers, site):
    rs = recs(site, gh=[("o/live", "MIT"), ("o/old", None), ("o/gone", None), ("o/arch", "MIT")])
    state = run(servers, rs, {})
    st = {r["id"]: state["records"][r["id"]] for r in rs}
    assert st["gh-o-live"]["status"] == "ok" and st["gh-o-live"]["github"]["head"] == "c" * 40
    assert st["gh-o-old"]["status"] == "moved" and st["gh-o-old"]["final_url"] == "https://github.com/o/new"
    assert st["gh-o-gone"]["status"] == "gone"
    assert st["gh-o-arch"]["github"]["archived"] is True
    r = ra.health_report(ROOT, rs, state, DAY1, [], "online")
    checks = {(f["check"], f["subject"]) for f in r["findings"]}
    assert ("ref-gone", "ref:gh-o-gone") in checks and ("ref-moved", "ref:gh-o-old") in checks
    assert ("ref-repo-archived", "ref:gh-o-arch") in checks and ("ref-licence-changed", "ref:gh-o-arch") in checks
    assert ("ref-repo-stale", "ref:gh-o-arch") not in checks       # archived says it already


def refused():
    """A record whose host refuses the connection (nothing listens on port 1): unreachable."""
    return dict(id="refused", url="http://127.0.0.1:1/x", file="docs/research/references/x.yaml", kind="catalogued",
                evidence="snippet-only", activity=None, spdx=None, claims=False)


def test_streaks_and_fingerprints_are_stable(servers, site):
    rs = recs(site, "/gone", "/soft") + [refused()]
    s1 = run(servers, rs, {}, DAY1)
    r1 = ra.health_report(ROOT, rs, s1, DAY1, [], "online")
    s2 = run(servers, rs, json.loads(json.dumps(s1)), DAY2)
    r2 = ra.health_report(ROOT, rs, s2, DAY2, [], "online")
    gone = s2["records"][rs[0]["id"]]["streak"]
    assert gone == dict(key="gone", status="gone", since=DAY1.isoformat(), runs=2)
    fp1 = {f["fp"] for f in r1["findings"] if f["check"] != "ref-unverified"}
    fp2 = {f["fp"] for f in r2["findings"] if f["check"] != "ref-unreachable"}
    assert fp1 == fp2                       # the same problems, the same fingerprints, a week later
    # one unanswered check is info (not re-checked); two in a row is a low finding
    assert any(f["check"] == "ref-unverified" for f in r1["findings"])
    assert any(f["check"] == "ref-unreachable" and f["severity"] == "low" for f in r2["findings"])


def test_state_round_trips_and_the_report_is_deterministic(servers, site, tmp_path):
    rs = recs(site, "/ok", "/gone", "/old")
    state = run(servers, rs, {})
    r = ra.health_report(ROOT, rs, state, DAY1, [], "online")
    p = tmp_path / "h.json"
    p.write_text(json.dumps(r))
    again = ra.load_state(p)
    assert again["records"] == state["records"]
    r2 = ra.health_report(ROOT, rs, again, DAY1, [], "offline")
    assert [f["fp"] for f in r2["findings"]] == [f["fp"] for f in r["findings"]]
    assert ra.health_markdown(r2) == ra.health_markdown(dict(r2))


def test_a_changed_link_starts_afresh(servers, site):
    rs = recs(site, "/gone")
    state = run(servers, rs, {}, DAY1)
    rs[0]["url"] = base(site) + "/ok"
    assert ra.last_check(state, rs[0]) is None
    r = ra.health_report(ROOT, rs, state, DAY1, [], "offline")
    assert not [f for f in r["findings"] if f["subject"] == f"ref:{rs[0]['id']}"]
    state = run(servers, rs, state, DAY2)
    assert state["records"][rs[0]["id"]]["streak"]["runs"] == 1


def test_lychee_report_becomes_findings(tmp_path):
    lj = tmp_path / "lychee.json"
    lj.write_text(json.dumps({"error_map": {
        "./docs/a.md": [{"url": "https://gone.invalid/x", "status": {"text": "404 Not Found", "code": 404}},
                        {"url": "https://ok.invalid/p#nope", "status": {"text": "Cannot find fragment"}}],
        str(tmp_path / "docs/b.md"): [{"url": "file:///w/docs/missing.md", "status": {"text": "Cannot find file"}},
                                      {"url": "https://slow.invalid/", "status": {"text": "Timeout"}}]}}))
    errs = ra.lychee_errors(lj, tmp_path)
    assert ("docs/a.md", "https://gone.invalid/x", 404, "404 Not Found") in errs and errs[-1][0] == "docs/b.md"
    r = ra.health_report(ROOT, [], {"records": {}}, DAY1, [], "online", errs)
    checks = sorted((f["check"], f["severity"]) for f in r["findings"])
    assert checks == [("md-link-anchor", "low"), ("md-link-dead", "medium"), ("md-link-dead", "medium"),
                      ("md-link-unverified", "info")]


def test_issue_plan_uses_the_health_page_and_its_own_title(servers, site):
    rs = recs(site, "/gone")
    state = run(servers, rs, {})
    r = ra.health_report(ROOT, rs, state, DAY1, [], "online")
    plan, note = ra.plan_issue(r, [], "o/r", "Reference health: open findings")
    (args, body), = plan
    assert args[:2] == ["issue", "create"] and "Reference health: open findings" in args
    assert body.startswith("# Reference health") and "cad-supply-chain-report fps=" in body
    assert "127.0.0.1" in body and "`http://127.0.0.1" in body       # grouped by host; URLs inert (not linked)


def test_the_registry_records_load_and_the_command_runs_offline(tmp_path, capsys):
    rs = ra.registry_records(ROOT)
    assert len(rs) > 500 and all(r["url"].startswith("http") for r in rs)
    assert len({r["id"] for r in rs}) == len(rs)
    out = tmp_path / "h.json"
    assert ra.main(["references", "--json", str(out), "--md", str(tmp_path / "h.md"), "--as-of", "2026-11-09"]) == 0
    r = json.loads(out.read_text())
    assert r["schema"] == ra.HEALTH_SCHEMA and r["summary"]["never_checked"] == len(rs) and r["mode"] == "offline"


def test_interval_below_one_second_is_refused():
    with pytest.raises(SystemExit):
        ra.main(["references", "--interval", "0.5"])


def test_retry_after_parses_numbers_and_dates():
    now = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)
    assert ra.retry_after("5") == 5 and ra.retry_after(None) is None and ra.retry_after("soon") is None
    assert ra.retry_after("Mon, 09 Nov 2026 12:00:30 GMT", now) == 30


def test_the_weekly_jobs_keep_tokens_apart_and_only_they_go_online():
    """references reads only; the issue job runs the stdlib alone; the PR job runs no Python and applies only shard
    edits; lychee is pinned and paced; and CI's own jobs never run the online check."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/supply-chain.yml").read_text())
    jobs = wf["jobs"]
    ref, issue, pr = jobs["references"], jobs["references-issue"], jobs["references-pr"]
    assert wf["permissions"] == {} and "default_branch" in ref["if"]
    assert ref["permissions"] == {"contents": "read", "actions": "read"}
    assert issue["permissions"] == {"contents": "read", "issues": "write"} and issue["needs"] == "references"
    assert pr["permissions"] == {"contents": "write", "pull-requests": "write"} and pr["needs"] == "references"
    assert ref["steps"][0]["with"] == {"ref": "dev", "persist-credentials": False}
    lychee = next(s for s in ref["steps"] if "lychee-action" in s.get("uses", ""))
    assert ra.re.fullmatch(r"lycheeverse/lychee-action@[0-9a-f]{40}", lychee["uses"])
    assert "--host-request-interval 1s" in lychee["with"]["args"] and "--host-concurrency 1" in lychee["with"]["args"]
    runs = "\n".join(s.get("run", "") for s in ref["steps"])
    assert "references --online" in runs and "references_health_apply.py" in runs and "--state" in runs
    assert not any("pip" in s.get("run", "") or "setup-python" in s.get("uses", "") for s in issue["steps"] + pr["steps"])
    assert not any("python" in s.get("run", "") for s in pr["steps"])
    pr_run = "\n".join(s.get("run", "") for s in pr["steps"])
    assert "git apply --numstat" in pr_run and r"^docs/research/references/[a-z0-9-]+\.yaml$" in pr_run and "--base dev" in pr_run
    for other in (".github/workflows/ci.yml", ".github/workflows/gates.yml", ".github/workflows/webkit.yml",
                  ".github/workflows/release.yml"):
        assert "references --online" not in (ROOT / other).read_text() and "lychee" not in (ROOT / other).read_text()


def test_a_304_keeps_a_soft_404_and_never_makes_it_a_move(servers, site):
    """A dead deep link that 301s to the home page, whose ETag then gives 304, stays gone (root) and is never `moved`;
    a "not found" page with an ETag stays gone on its 304 too, so its streak grows."""
    rs = recs(site, "/to-root", "/notfound-etag")
    for day in (DAY1, DAY2, DAY3):
        state = run(servers, rs, {} if day == DAY1 else state, day)
        root, nf = (state["records"][r["id"]] for r in rs)
        assert root["status"] == "gone" and root["soft404"] == ["root"], (day, root)
        assert nf["status"] == "gone" and nf["soft404"] == ["title"] and nf["title"] == "Page not found", (day, nf)
    assert root["http"] == [301, 304] and nf["http"] == [304]
    assert root["streak"]["runs"] == 3 and nf["streak"]["runs"] == 3 and nf["down_runs"] == 3


def test_a_long_503_is_unknown_and_defers_the_host(servers, site):
    rs = recs(site, "/maintenance", "/ok", "/new")
    rs[0]["id"] = "a-first"
    state = run(servers, rs, {})
    e = state["records"]["a-first"]
    assert e["status"] == "unknown" and e["http"] == [503] and "down_since" not in e
    assert state["deferred"] == ["127.0.0.1"] and len(state["records"]) == 1 and state["hosts"] == {}


def test_a_github_api_failure_is_unknown_not_unreachable(servers, site):
    rs = recs(site, gh=[("o/limited", None)])
    e = run(servers, rs, {})["records"]["gh-o-limited"]
    assert e["status"] == "unknown" and e["github"] == {"state": "unverified"} and "down_runs" not in e


def test_an_outage_is_counted_from_the_last_good_check():
    """gone, gone, blocked, unknown, unreachable: one outage since the first gone (blocked and unknown neither end nor
    extend it); an ok check ends it."""
    prev = None
    for day, status in enumerate(["ok", "gone", "gone", "blocked", "unknown", "unreachable"], start=1):
        e = ra.down_track(prev, dict(status=status, checked=f"2026-11-{day:02d}"))
        prev = e
    assert prev["down_since"] == "2026-11-02" and prev["down_runs"] == 3
    assert "down_since" not in ra.down_track(prev, dict(status="ok", checked="2026-11-07"))


def _pr_guard():
    """The PR job's patch guard, as the workflow runs it: from `# guard:` to `# end guard`."""
    yaml = pytest.importorskip("yaml")
    run_ = "\n".join(s.get("run", "") for s in yaml.safe_load(
        (ROOT / ".github/workflows/supply-chain.yml").read_text())["jobs"]["references-pr"]["steps"])
    lines = run_.splitlines()
    a = next(i for i, ln in enumerate(lines) if ln.strip().startswith("# guard:"))
    b = next(i for i, ln in enumerate(lines) if ln.strip() == "# end guard")
    import textwrap
    return textwrap.dedent("\n".join(lines[a:b]))


@pytest.mark.parametrize("probe, ok", [("edit", True), ("rename", False), ("symlink", False), ("create", False),
                                       ("delete", False), ("mode", False), ("outside", False)])
def test_the_pr_job_applies_only_in_place_shard_edits(tmp_path, probe, ok):
    import shutil
    import subprocess
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    repo = tmp_path / "r"
    sh = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True, text=True).stdout   # noqa: E731
    repo.mkdir()
    sh("git", "init", "-q")
    (repo / "docs/research/references").mkdir(parents=True)
    (repo / "docs/research/references/a.yaml").write_text("schema: 2\nsources: []\n")
    (repo / "tools").mkdir()
    (repo / "tools/ci_gates.py").write_text("print('gate')\n")
    (repo / "top.txt").write_text("secret-ish\n")
    sh("git", "add", "-A")
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    shard, gate = repo / "docs/research/references/a.yaml", repo / "tools/ci_gates.py"
    if probe == "edit":
        shard.write_text("schema: 2\nsources: [x]\n")
    elif probe == "rename":
        sh("git", "mv", "tools/ci_gates.py", "docs/research/references/b.yaml")
    elif probe == "symlink":
        shard.unlink()
        shard.symlink_to("../../top.txt")
    elif probe == "create":
        (repo / "docs/research/references/new.yaml").write_text("schema: 2\n")
        sh("git", "add", "-N", "docs/research/references/new.yaml")
    elif probe == "delete":
        shard.unlink()
    elif probe == "mode":
        shard.chmod(0o755)
    elif probe == "outside":
        gate.write_text("print('owned')\n")
    patch = tmp_path / "p.patch"
    patch.write_text(sh("git", "diff", "-M", "HEAD", "--binary"))
    sh("git", "reset", "-q", "--hard")
    sh("git", "clean", "-qfd")
    res = subprocess.run(["bash", "-ec", f'patch="{patch}"\n' + _pr_guard() + "\necho GUARD-PASSED"], cwd=repo,
                         capture_output=True, text=True)
    assert ("GUARD-PASSED" in res.stdout) is ok, (probe, res.stdout, res.stderr)
    if not ok:
        assert res.returncode == 1 and "::error::" in res.stdout
        assert sh("git", "status", "--porcelain") == ""              # refused before anything was applied


def test_the_state_comes_only_from_the_weekly_runs_and_stale_bot_prs_close_anyway():
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load((ROOT / ".github/workflows/supply-chain.yml").read_text())["jobs"]
    state = next(s for s in jobs["references"]["steps"] if s.get("name") == "The last run's state")
    assert '--branch "$DEFAULT"' in state["run"] and '.event == "schedule"' in state["run"]
    assert state["env"]["DEFAULT"] == "${{ github.event.repository.default_branch }}"
    pr_run = "\n".join(s.get("run", "") for s in jobs["references-pr"]["steps"])
    assert "exit 0" not in pr_run                                   # no early exit before the clean-up loop
    assert pr_run.index("git ls-remote --heads origin") > pr_run.index("No evidence changes this week")
