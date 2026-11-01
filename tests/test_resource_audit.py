"""The supply-chain report in tools/resource_audit.py (#117): offline checks on a fixture checkout, online checks
against recorded answers (no network), the PR gate in a scratch git repository, and the weekly issue plan."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("resource_audit", ROOT / "tools" / "resource_audit.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

AS_OF = ra.dt.date(2026, 10, 31)
SHA = "a" * 40
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n"
APACHE = "                                 Apache License\n                           Version 2.0, January 2004\n"


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text) if isinstance(text, bytes) else p.write_text(text)
    return p


def lock(packages):
    return json.dumps({"name": "x", "lockfileVersion": 3, "packages": {
        "": {"name": "x", "devDependencies": {"marked": "16.4.1"}}, **packages}})


def good_pkg(name, version, **kw):
    return {f"node_modules/{name}": {"version": version, "resolved": f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz",
                                     "integrity": "sha512-abc", "license": "MIT", "dev": True, **kw}}


def checkout(root: Path):
    """A small, clean checkout: every offline check passes on it."""
    write(root, "pyproject.toml", '[project]\nname = "x"\ndependencies = ["pyyaml>=6.0", "numpy>=1.24"]  # core\n'
                                  '[project.optional-dependencies]\ncad = [\n    "cadquery[ocp]>=2.4",  # the kernel\n'
                                  '    "pillow>=10.0",\n]\ndev = ["pytest"]\n')
    write(root, "package.json", json.dumps({"devDependencies": {"marked": "16.4.1"}}))
    write(root, "package-lock.json", lock(good_pkg("marked", "16.4.1")))
    write(root, "vendor/manifest.json", json.dumps({"projects": [
        {"name": "tool", "url": "https://github.com/someone/tool", "license": "MIT", "sha": SHA, "imported": "2026-10-24",
         "report": "vendor/reports/tool.md", "exclude": [".github"]}]}))
    write(root, "vendor/tool/LICENSE", MIT)
    write(root, "vendor/tool/src/a.py", "print('a')\n")
    write(root, "vendor/tool/skills/x/SKILL.md", "---\nname: x\n---\n")
    write(root, "vendor/baselines/tool.json", json.dumps({"project": "tool", "sha": SHA, "fingerprints": []}))
    write(root, "vendor/reports/tool.md", "# scan\n")
    write(root, "THIRD_PARTY_NOTICES.md",
          "| Project | Licence | Upstream | Pinned commit | Imported |\n|---|---|---|---|---|\n"
          f"| tool | MIT | https://github.com/someone/tool | `{SHA[:12]}` | 2026-10-24 |\n\n"
          "## Web kit\n\n| Project | Licence | Version | Licence file in the kit |\n|---|---|---|---|\n"
          "| Mermaid | MIT | 11.4.1 | `mermaid/LICENSE` |\n")
    mjs = b"/* mermaid 11.4.1 */"
    write(root, f"{ra.KIT}/mermaid/mermaid.min.js", mjs)
    write(root, f"{ra.KIT}/mermaid/LICENSE", MIT)
    write(root, f"{ra.KIT}/mermaid/SOURCE.json", json.dumps({"package": "mermaid", "version": "11.4.1", "files": {
        "mermaid.min.js": hashlib.sha256(mjs).hexdigest(), "LICENSE": hashlib.sha256(MIT.encode()).hexdigest()}}))
    write(root, f"{ra.KIT}/file-viewer-sources.json", "{}")
    write(root, "upstreams/registry.yaml", "- name: someone/tool\n  url: https://github.com/someone/tool\n  license: MIT\n"
                                           "  last_push: 2026-10-01\n  status: trial\n")
    write(root, "research/landscape.json", json.dumps({"projects": [], "libraries": [
        {"name": "gumyr/build123d", "license_spdx": "Apache-2.0", "last_push": "2026-10-23"}], "benchmarks": []}))
    write(root, "docs/guide.md", "# Guide\n\nSee [the docs](https://docs.someone.dev/x) and https://example.com/demo.\n\n"
                                 "```bash\ncurl http://localhost:8000/ && uvx --from cadgen==0.7.26 cadgen mcp\n```\n")
    write(root, ".github/dependabot.yml", "version: 2\nupdates:\n  - package-ecosystem: npm\n  - package-ecosystem: pip\n"
                                          "  - package-ecosystem: github-actions\n")
    return root


def run(root, net=None, **kw):
    return ra.build(root, AS_OF, net, npm_audit=False, **kw).to_json()


def checks(r, severity=None):
    return {(f["check"], f["subject"]) for f in r["findings"] if severity is None or f["severity"] == severity}


# ----------------------------------------------------------------------------------------------------------- parsing
def test_mini_toml_reads_our_pyproject_like_tomllib():
    tomllib = pytest.importorskip("tomllib")
    text = (ROOT / "pyproject.toml").read_text()
    want, got = tomllib.loads(text)["project"], ra.mini_toml(text)["project"]
    assert got["dependencies"] == want["dependencies"]
    assert got["optional-dependencies"] == want["optional-dependencies"]


def test_versions_floors_and_lowest_release():
    assert ra.vkey("1.10.2") > ra.vkey("1.9") > ra.vkey("1.9rc1")
    assert ra.vkey("0.160.0") > ra.vkey("0.16.0")
    assert ra.spec_floor(">=3.7,<4") == (">=", "3.7") and ra.spec_floor("") is None and ra.spec_floor("<2") is None
    releases = {"9.9": [{}], "10.0.0": [{"yanked": True}], "10.0.1": [{}], "10.1.0b1": [{}], "11.0": [{}]}
    assert ra.lowest_release(releases, (">=", "10.0")) == "10.0.1"            # yanked and pre-releases skipped
    assert ra.lowest_release(releases, (">", "10.0.1")) == "11.0"
    assert ra.lowest_release(releases, ("==", "9.9")) == "9.9"


@pytest.mark.parametrize("tool,args,pkg", [
    ("npx", "--yes wrangler@4.86.0 pages deploy", None),
    ("npx", "-y some-mcp", "some-mcp"),
    ("npx", "pkg@latest", "pkg@latest"),
    ("uvx", "--no-config --python 3.13 --from cadgen==0.7.26 cadgen mcp", None),
    ("uvx", "kicad-mcp-pro", "kicad-mcp-pro"),
    ("uvx", "ruff==0.6.0 check", None),
    ("pipx run", "./local.py", None),
])
def test_unpinned_runner(tool, args, pkg):
    assert ra.unpinned_runner(tool, args) == pkg


def test_urls_in_code_are_not_links_and_parentheses_stay():
    text = "A [paper](https://a.org/x%20(1).pdf).\n\n`https://in.code/x`\n\n```\nhttps://fenced.org/\n```\n"
    assert [u for _, u in ra.prose_urls(text)] == ["https://a.org/x%20(1).pdf"]


# ----------------------------------------------------------------------------------------------------------- offline
def test_clean_checkout_has_nothing_above_info(tmp_path):
    r = run(checkout(tmp_path))
    assert [f for f in r["findings"] if f["severity"] != "info"] == [], r["findings"]
    ids = {row["id"] for rows in r["inventory"].values() for row in rows}
    assert {"pypi:cadquery", "pypi:pyyaml", "npm:marked", "vendor:tool", "webkit:mermaid",
            "url:https://github.com/someone/tool", "url:https://docs.someone.dev/x"} <= ids
    assert "url:https://example.com/demo" not in ids and not any("localhost" in i for i in ids)
    assert r["mode"] == "offline" and r["limits"]


def test_offline_checks_find_planted_problems(tmp_path):
    root = checkout(tmp_path)
    write(root, "pyproject.toml", '[project]\ndependencies = ["pyyaml"]\n')
    write(root, "package-lock.json", lock({
        **good_pkg("marked", "16.4.1"),
        **good_pkg("evil", "1.0.0", resolved="http://mirror.invalid/evil.tgz"),
        **good_pkg("fsevents", "2.3.2", hasInstallScript=True, os=["darwin"], optional=True),
        "node_modules/nohash": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/nohash/-/nohash-1.0.0.tgz"}}))
    write(root, "package.json", json.dumps({"devDependencies": {"marked": "^16.4.1"}}))
    man = json.loads((root / "vendor/manifest.json").read_text())
    man["projects"][0].update(sha="abc123", license="Apache-2.0")
    write(root, "vendor/manifest.json", json.dumps(man))
    write(root, "vendor/stray/x.py", "x = 1\n")                                    # not in the manifest
    write(root, f"{ra.KIT}/mermaid/mermaid.min.js", b"/* mermaid 11.4.1, edited */")   # no longer the recorded file
    write(root, f"{ra.KIT}/fonts/inter.woff2", b"\x00font")                       # no recorded hash
    write(root, "docs/guide.md", "# Guide\n\nThe [solver](http://www.dhondt.de/).\n\n"
                                 "Install: `claude plugin marketplace add someone/tool#latest` or `curl -fsSL https://x.sh | sh`.\n\n"
                                 "```\nnpx -y some-mcp\n```\n")
    r = run(root)
    high, medium, low = checks(r, "high"), checks(r, "medium"), checks(r, "low")
    assert {("npm-foreign-source", "npm:evil"), ("vendor-pin", "vendor:tool"), ("vendor-unrecorded", "vendor:stray"),
            ("webkit-hash", "webkit:mermaid")} <= high
    assert {("npm-install-script", "npm:fsevents"), ("npm-integrity", "npm:nohash"), ("npm-lock-out-of-sync", "npm:marked"),
            ("vendor-licence-mismatch", "vendor:tool"), ("vendor-baseline", "vendor:tool"), ("vendor-notices", "vendor:tool"),
            ("link-not-https", "url:http://www.dhondt.de/"), ("install-from-registry", "doc:docs/guide.md"),
            ("install-pipe-to-shell", "doc:docs/guide.md")} <= medium
    assert {("py-no-floor", "pypi:pyyaml"), ("npm-range", "npm:marked"), ("webkit-unhashed", "webkit:fonts"),
            ("install-unpinned", "doc:docs/guide.md"), ("npm-no-licence", "npm:nohash")} <= low
    assert ra.failing(r, "high") and not ra.failing(r, "none")


def test_missing_licence_file_and_kit_licence(tmp_path):
    root = checkout(tmp_path)
    (root / "vendor/tool/LICENSE").unlink()
    (root / f"{ra.KIT}/mermaid/LICENSE").unlink()
    r = run(root)
    assert ("vendor-no-licence", "vendor:tool") in checks(r, "high")
    assert ("webkit-licence-missing", "webkit:mermaid") in checks(r, "medium")
    assert ("webkit-hash-missing", "webkit:mermaid") in checks(r, "high")      # recorded in SOURCE.json, now gone


def test_accepted_findings_do_not_fail(tmp_path):
    root = checkout(tmp_path)
    write(root, "vendor/stray/x.py", "x = 1\n")
    accepted = [{"check": "vendor-unrecorded", "subject": "vendor:stray", "reason": "fixture", "accepted": "2026-10-31"}]
    r = ra.build(root, AS_OF, None, npm_audit=False, accepted=accepted).to_json()
    f = next(f for f in r["findings"] if f["check"] == "vendor-unrecorded")
    assert f["accepted"].startswith("fixture") and not ra.failing(r, "high") and r["summary"]["accepted"] == 1


def test_report_is_deterministic_and_markdown_is_one_page(tmp_path):
    root = checkout(tmp_path)
    write(root, "docs/guide.md", "# G\n\nA [b|c](http://www.dhondt.de/).\n")
    a, b = run(root), run(root)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    md = ra.to_markdown(a)
    assert md.count("\n# ") + md.startswith("# ") == 1 and "**Limits.**" in md and "pie showData" in md
    assert "/home/" not in md and str(tmp_path) not in json.dumps(a)


def test_repo_offline_report_has_no_high_findings():
    """What CI's supply-chain job enforces on the whole checkout: nothing high or critical, offline."""
    r = ra.build(ROOT, AS_OF, None, npm_audit=False, accepted=ra.load_accepted(ROOT / ra.ACCEPTED)).to_json()
    assert not ra.failing(r, "high"), [(f["check"], f["subject"], f["title"]) for f in ra.failing(r, "high")]
    assert r["inventory"]["vendored"] and r["inventory"]["webkit"] and len(r["inventory"]["links"]) > 50


# ------------------------------------------------------------------------------------------------------------ online
class FakeNet(ra.Net):
    """Recorded answers instead of the network: http[url] -> JSON, gh[path] -> JSON, probes[url] -> (chain, error)."""

    def __init__(self, http=None, gh=None, probes=None, osv=None):
        super().__init__(workers=2)
        self.token = self.gh = None
        self.http, self.ghr, self.probes, self.osv = http or {}, gh or {}, probes or {}, osv

    def json(self, url, data=None, headers=None):
        if url.endswith("/querybatch"):
            if self.osv is None:
                return 0, None, "timed out"
            return 200, {"results": [{"vulns": [{"id": i} for i in self.osv(q)]} for q in data["queries"]]}, ""
        v = self.http.get(url)
        return (404, None, "") if v is None else (200, v, "")

    def github(self, path):
        v = self.ghr.get(path)
        return (404, {"message": "Not Found"}, "") if v is None else (200, v, "")

    def graphql(self, query):
        return 0, None, "offline"

    def probe(self, url):
        return self.probes.get(url, ([], "timed out"))


def vuln(vid, severity="HIGH", fixed="2.0.0", eco="npm", name="marked"):
    return {"id": vid, "summary": f"{vid} summary", "aliases": [], "database_specific": {"severity": severity},
            "affected": [{"package": {"ecosystem": eco, "name": name}, "ranges": [{"type": "ECOSYSTEM", "events": [
                {"introduced": "0"}, {"fixed": fixed}]}]}]}


def repo(full_name, **kw):
    return {"full_name": full_name, "archived": False, "disabled": False, "license": {"spdx_id": "MIT"},
            "pushed_at": "2026-10-20T00:00:00Z", "default_branch": "main", "stargazers_count": 1, **kw}


def online_net(tmp_path, **over):
    tool_tree = {"tree": [
        {"path": "LICENSE", "type": "blob", "mode": "100644", "sha": ra.git_blob_sha(MIT.encode())},
        {"path": "src/a.py", "type": "blob", "mode": "100644", "sha": ra.git_blob_sha(b"print('upstream')\n")},
        {"path": "skills/x/SKILL.md", "type": "blob", "mode": "100644", "sha": ra.git_blob_sha(b"---\nname: x\n---\n")},
        {"path": ".github/ci.yml", "type": "blob", "mode": "100644", "sha": "0" * 40},       # excluded in the manifest
        {"path": "docs/new.md", "type": "blob", "mode": "100644", "sha": "1" * 40}]}            # not vendored, not excluded
    gh = {"repos/someone/tool": repo("someone/tool"), "repos/gumyr/build123d": repo("gumyr/build123d", archived=True, license={"spdx_id": "GPL-3.0"}),
          f"repos/someone/tool/git/trees/{SHA}?recursive=1": tool_tree,
          f"repos/someone/tool/compare/{SHA}...main": {"ahead_by": 3},
          "repos/someone/tool/security-advisories?state=published&per_page=100": [],
          "repos/mermaid-js/mermaid": repo("mermaid-js/mermaid")}
    gh.update(over.pop("gh", {}))
    http = {"https://pypi.org/pypi/pyyaml/json": {"info": {"version": "6.0.3", "license": "MIT", "classifiers": []},
                                                    "releases": {"6.0": [{"upload_time": "2021-10-13T00:00:00"}],
                                                                 "6.0.3": [{"upload_time": "2025-09-25T00:00:00"}]}},
            "https://pypi.org/pypi/pillow/json": {"info": {"version": "12.0.0", "license_expression": "MIT-CMU", "classifiers": []},
                                                    "releases": {"10.0.0": [{"upload_time": "2023-07-01T00:00:00"}],
                                                                 "12.0.0": [{"upload_time": "2026-10-01T00:00:00"}]}},
            f"{ra.OSV}/vulns/GHSA-aaaa": vuln("GHSA-aaaa", fixed="17.0.0"), f"{ra.OSV}/vulns/MAL-2026-1": vuln("MAL-2026-1", None, name="evil"),
            f"{ra.OSV}/vulns/GHSA-pill": vuln("GHSA-pill", "CRITICAL", "10.2.0", "PyPI", "pillow"),
            f"{ra.OSV}/vulns/GHSA-merm": vuln("GHSA-merm", "MODERATE", "11.10.0", name="mermaid")}
    http.update(over.pop("http", {}))

    def osv(q):
        p, v = q.get("package", {}), q.get("version")
        return {("npm", "marked", "16.4.1"): ["GHSA-aaaa"], ("PyPI", "pillow", "10.0.0"): ["GHSA-pill"],
                ("npm", "mermaid", "11.4.1"): ["GHSA-merm"]}.get((p.get("ecosystem"), p.get("name"), v), [])
    probes = {"https://docs.someone.dev/x": ([(301, "https://docs.someone.dev/x"), (200, "https://parked.invalid/landing")], "")}
    return FakeNet(http=http, gh=gh, probes=over.pop("probes", probes), osv=over.pop("osv", osv))


def test_online_checks_from_recorded_answers(tmp_path):
    r = run(checkout(tmp_path), online_net(tmp_path))
    by = {(f["check"], f["subject"]): f for f in r["findings"]}
    npm = by[("advisory", "npm:marked")]
    assert npm["severity"] == "high" and "GHSA-aaaa" in npm["evidence"] and ">=17.0.0" in npm["action"]
    pil = by[("advisory", "pypi:pillow")]                         # only the lowest allowed release is affected: low
    assert pil["severity"] == "low" and "10.0.0" in pil["title"] and ">=10.2.0" in pil["action"]
    assert by[("advisory", "webkit:mermaid")]["severity"] == "medium"
    assert by[("vendor-drift", "vendor:tool")]["severity"] == "high" and "src/a.py" in by[("vendor-drift", "vendor:tool")]["evidence"]
    assert "docs/new.md" in by[("vendor-incomplete", "vendor:tool")]["evidence"]
    assert ".github/ci.yml" not in by[("vendor-incomplete", "vendor:tool")]["evidence"]
    lib = "url:https://github.com/gumyr/build123d"
    assert by[("repo-archived", lib)]["severity"] == "medium" and by[("licence-changed", lib)]["severity"] == "medium"
    assert by[("link-redirect-domain", "url:https://docs.someone.dev/x")]["severity"] == "medium"
    vend = next(v for v in r["inventory"]["vendored"] if v["name"] == "tool")
    assert vend["behind"] == 3 and vend["drift"]["changed"] == 1
    assert r["mode"] == "online" and r["sources"]["osv"].startswith("osv.dev")


def test_patched_files_are_not_drift(tmp_path):
    root = checkout(tmp_path)
    write(root, "vendor/patches/tool/0001-x.patch", "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n")
    r = run(root, online_net(tmp_path))
    assert ("vendor-drift", "vendor:tool") not in checks(r)


def test_malicious_package_is_critical_and_moved_or_gone_repos(tmp_path):
    root = checkout(tmp_path)
    write(root, "package-lock.json", lock({**good_pkg("marked", "16.4.1"), **good_pkg("evil", "1.0.0")}))
    write(root, "upstreams/registry.yaml", "- name: a/moved\n  url: https://github.com/a/moved\n  license: MIT\n"
                                           "- name: a/gone\n  url: https://github.com/a/gone\n  license: MIT\n")

    def osv(q):
        return ["MAL-2026-1"] if q.get("package", {}).get("name") == "evil" else []
    r = run(root, online_net(tmp_path, osv=osv, gh={"repos/a/moved": repo("b/moved")}))
    by = {(f["check"], f["subject"]): f for f in r["findings"]}
    assert by[("advisory", "npm:evil")]["severity"] == "critical" and "Malicious" in by[("advisory", "npm:evil")]["action"]
    assert by[("repo-moved", "url:https://github.com/a/moved")]["severity"] == "medium"
    assert by[("repo-gone", "url:https://github.com/a/gone")]["severity"] == "high"


def test_network_failures_are_info_never_failures(tmp_path):
    """No answer from OSV, PyPI, GitHub or a site: reported as not verified, and the exit code does not change."""
    class Down(FakeNet):
        def json(self, url, data=None, headers=None):
            return 0, None, "timed out"

        def github(self, path):
            return 0, None, "timed out"
    r = run(checkout(tmp_path), Down(osv=None))
    assert not ra.failing(r, "low"), ra.failing(r, "low")
    assert ("osv-unverified", "osv.dev") in checks(r, "info") and r["sources"]["osv"].startswith("not verified")
    assert any(f["check"] == "link-unverified" for f in r["findings"])


# -------------------------------------------------------------------------------------------------------------- gate
def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo_with_base(tmp_path):
    root = checkout(tmp_path / "r")
    git(root, "init", "-q", "-b", "dev")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
    return root


def gate(root, body=None, extra=()):
    args = ["gate", "--root", str(root), "--base", "HEAD", "--as-of", "2026-10-31", "--no-npm-audit", *extra]
    if body is not None:
        f = root.parent / "body.md"
        f.write_text(body)
        args += ["--pr-body-file", str(f)]
    return ra.main(args)


def test_gate_needs_a_row_for_each_added_item(repo_with_base, capsys):
    root = repo_with_base
    assert gate(root, "") == 0                                        # nothing added
    text = (root / "pyproject.toml").read_text().replace('dev = ["pytest"]', 'dev = ["pytest"]\nexplore = ["optuna>=3.4"]')
    write(root, "pyproject.toml", text)
    write(root, "upstreams/registry.yaml", (root / "upstreams/registry.yaml").read_text() +
          "- name: new/thing\n  url: https://github.com/new/thing\n  license: MIT\n  status: candidate\n")
    write(root, f"{ra.KIT}/fonts/new.woff2", b"\x00")
    assert gate(root, "no rows here") == 1
    out = capsys.readouterr().out
    assert "pypi:optuna" in out and "url:https://github.com/new/thing" in out and "webkit:fonts" in out
    ids, _ = ra.added_items(root, "HEAD")
    assert ids == ["pypi:optuna", "url:https://github.com/new/thing", "webkit:fonts"]
    rows = "| `pypi:optuna` |\n| `url:https://github.com/new/thing` |\n| `webkit:fonts` |"
    assert gate(root, rows) == 1                                      # the new font has no recorded hash (medium)
    assert "new vendored files in fonts have no recorded hash" in capsys.readouterr().out
    assert gate(root, rows, ["--fail-on", "high"]) == 0
    assert ra.main(["rows", "--root", str(root), "--base", "HEAD", "--no-npm-audit"]) == 0
    assert "| `pypi:optuna` | Python dependency (explore) | >=3.4 |" in capsys.readouterr().out


def test_gate_fails_on_a_high_finding_anywhere(repo_with_base, capsys):
    write(repo_with_base, "vendor/stray/x.py", "x = 1\n")
    assert gate(repo_with_base, "| `vendor:stray` |", ["--fail-on", "critical"]) == 1
    assert "vendor/stray is not in vendor/manifest.json" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------------------- issue
def report_with(*fs):
    return {"as_of": "2026-10-31", "revision": "f" * 40, "mode": "online", "limits": ["x"], "sources": {},
            "summary": {**{s: 0 for s in ra.SEVERITIES}, "accepted": 0, "items": {}}, "inventory": {}, "extra": {},
            "findings": [dict(severity=s, check=c, subject=c, title=c, evidence="", action="", fp=fp) for s, c, fp in fs]}


def test_issue_plan_opens_updates_and_leaves_alone():
    r = report_with(("medium", "repo-archived", "a" * 16), ("info", "link-unverified", "b" * 16))
    plan, _ = ra.plan_issue(r, [], "o/r", "T")
    assert [p[0][:2] for p in plan] == [["issue", "create"]] and f"fps={'a' * 16} -->" in plan[0][1]
    mine = {"number": 7, "author": {"login": "app/github-actions"}, "body": f"x\n<!-- cad-supply-chain-report fps={'a' * 16} -->"}
    assert ra.plan_issue(r, [mine], "o/r", "T")[0] == []             # unchanged (info findings do not count)
    r2 = report_with(("medium", "repo-archived", "a" * 16), ("high", "repo-gone", "c" * 16))
    plan, note = ra.plan_issue(r2, [mine], "o/r", "T")
    assert [p[0][:3] for p in plan] == [["issue", "edit", "7"], ["issue", "comment", "7"]] and "1 new, 0 resolved" in note
    spoof = dict(mine, author={"login": "someone"})                 # a marker in someone else's issue is ignored
    assert ra.plan_issue(r2, [spoof], "o/r", "T")[0][0][0][:2] == ["issue", "create"]
    plan, _ = ra.plan_issue(report_with(), [mine], "o/r", "T")
    assert plan[-1][0][:3] == ["issue", "close", "7"]
