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
    assert md.count("\n# ") + md.startswith("# ") == 1 and "<strong>Limits.</strong>" in md and "pie showData" in md
    assert "`www.dhondt.de`" in md and "`url:http://www.dhondt.de/`" in md      # flagged links stay unlinked on the site
    assert "/home/" not in md and str(tmp_path) not in json.dumps(a)


def test_repo_offline_report_has_no_high_findings():
    """What CI's supply-chain job enforces on the whole checkout: nothing high or critical, offline."""
    r = ra.build(ROOT, AS_OF, None, npm_audit=False, accepted=ra.load_accepted(ROOT / ra.ACCEPTED)).to_json()
    assert not ra.failing(r, "high"), [(f["check"], f["subject"], f["title"]) for f in ra.failing(r, "high")]
    assert r["inventory"]["vendored"] and r["inventory"]["webkit"] and len(r["inventory"]["links"]) > 50


# ------------------------------------------------------------------------------------------------------------ online
DOWN = object()          # a recorded answer that never came (time-out)


class FakeNet(ra.Net):
    """Recorded answers instead of the network: http[url] -> JSON (or DOWN), files[url] -> bytes, gh[path] -> JSON,
    probes[url] -> (chain, error)."""

    def __init__(self, http=None, gh=None, probes=None, osv=None, files=None):
        super().__init__(workers=2)
        self.token = self.gh = None
        self.http, self.ghr, self.probes, self.osv, self.files = http or {}, gh or {}, probes or {}, osv, files or {}

    def json(self, url, data=None, headers=None):
        if url.endswith("/querybatch"):
            if self.osv is None:
                return 0, None, "timed out"
            return 200, {"results": [{"vulns": [{"id": i} for i in self.osv(q)]} for q in data["queries"]]}, ""
        v = self.http.get(url)
        return (404, None, "") if v is None else (0, None, "timed out") if v is DOWN else (200, v, "")

    def request(self, url, data=None, headers=None):
        v = self.files.get(url)
        return (404, b"", "") if v is None else (200, v, "")

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
    return FakeNet(http=http, gh=gh, probes=over.pop("probes", probes), osv=over.pop("osv", osv), files=over.pop("files", {}))


def test_online_checks_from_recorded_answers(tmp_path):
    r = run(checkout(tmp_path), online_net(tmp_path))
    by = {(f["check"], f["subject"]): f for f in r["findings"]}
    npm = by[("advisory", "npm:marked")]
    assert npm["severity"] == "high" and "GHSA-aaaa" in npm["evidence"] and ">=17.0.0" in npm["action"]
    pil = by[("advisory", "pypi:pillow")]       # only the lowest allowed release is affected, but critically: medium
    assert pil["severity"] == "medium" and "10.0.0" in pil["title"] and ">=10.2.0" in pil["action"]
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
    tag = ra.scope_tag("repo-archived")
    assert [p[0][:2] for p in plan] == [["issue", "create"]] and f"fps={'a' * 16}~{tag} -->" in plan[0][1]
    mine = {"number": 7, "author": {"login": "app/github-actions"}, "body": f"x\n<!-- cad-supply-chain-report fps={'a' * 16}~{tag} -->"}
    assert ra.plan_issue(r, [mine], "o/r", "T")[0] == []             # unchanged (info findings do not count)
    old_style = dict(mine, body=f"x\n<!-- cad-supply-chain-report fps={'a' * 16} -->")   # a marker from before scope tags
    assert ra.plan_issue(r, [old_style], "o/r", "T")[0] == []
    r2 = report_with(("medium", "repo-archived", "a" * 16), ("high", "repo-gone", "c" * 16))
    plan, note = ra.plan_issue(r2, [mine], "o/r", "T")
    assert [p[0][:3] for p in plan] == [["issue", "edit", "7"], ["issue", "comment", "7"]] and "1 new, 0 resolved" in note
    spoof = dict(mine, author={"login": "someone"})                 # a marker in someone else's issue is ignored
    assert ra.plan_issue(r2, [spoof], "o/r", "T")[0][0][0][:2] == ["issue", "create"]
    plan, _ = ra.plan_issue(report_with(), [mine], "o/r", "T")
    assert plan[-1][0][:3] == ["issue", "close", "7"]


# --------------------------------------------------------------------------------- the review of #138, point by point
def test_release_pr_and_main_push_get_the_whole_repo_check_only(repo_with_base, capsys):
    """The blocker: into main, what dev gained since the last release is not "what the change adds". It came through
    PRs into dev, each gated with its rows, so a release PR (no rows) and the push to main (no body) must pass."""
    root = repo_with_base
    text = (root / "pyproject.toml").read_text().replace('dev = ["pytest"]', 'dev = ["pytest"]\nexplore = ["optuna>=3.4"]')
    write(root, "pyproject.toml", text)
    write(root, f"{ra.KIT}/fonts/new.woff2", b"\x00")             # new, unhashed: medium on a change into dev
    assert gate(root, "Release v9.9.9: no rows here", ["--into", "main"]) == 0
    out = capsys.readouterr().out
    assert "whole-repository check only" in out and "pypi:optuna" not in out
    assert gate(root, None, ["--into", "main"]) == 0                 # the push to main: no body at all
    assert gate(root, "no rows here", ["--into", "dev"]) == 1        # the same change into dev is judged
    assert ra.gate_scope("dev") == "change" and ra.gate_scope("main") == "repo" and ra.gate_scope("feat/x") == "repo"
    write(root, "vendor/stray/x.py", "x = 1\n")                      # a high finding fails everywhere
    assert gate(root, None, ["--into", "main"]) == 1
    assert "vendor/stray is not in vendor/manifest.json" in capsys.readouterr().out


def test_ci_job_passes_the_target_branch_and_reads_only():
    """ci.yml's supply-chain job tells the gate where the change goes (a PR's base, else the pushed branch)."""
    yaml = pytest.importorskip("yaml")
    job = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["supply-chain"]
    assert job["permissions"] == {"contents": "read"}
    step = next(s for s in job["steps"] if "resource_audit.py gate" in s.get("run", ""))
    assert step["env"]["INTO"] == "${{ github.base_ref || github.ref_name }}"
    assert step["run"].count('--into "$INTO"') == 2 and "--pr-body-env PR_BODY" in step["run"]
    weekly = yaml.safe_load((ROOT / ".github/workflows/supply-chain.yml").read_text())
    assert weekly["permissions"] == {}
    report, issue = weekly["jobs"]["report"], weekly["jobs"]["issue"]
    assert report["permissions"] == {"contents": "read"} and issue["permissions"] == {"contents": "read", "issues": "write"}
    assert issue["needs"] == "report" and "default_branch" in report["if"]
    runs = [s.get("run", "") for s in report["steps"]]
    assert any("report --online" in r for r in runs) and not any("--repo" in r for r in runs)   # GITHUB_TOKEN can't read settings
    assert [s.get("run", "") for s in issue["steps"] if "resource_audit" in s.get("run", "")] == [
        'python3 tools/resource_audit.py issue --report build/security-report.json --repo "$GITHUB_REPOSITORY" --post']


@pytest.mark.parametrize("body,ok", [
    ("| `pypi:optuna` | Python dependency (explore) | >=3.4 | MIT | no findings |", True),
    ("  |`pypi:optuna`| row with tight cells |", True),
    ("We considered `pypi:optuna-dashboard` but dropped it.", False),
    ("Supply chain: None (pypi:optuna is just a mention)", False),
    ("| `pypi:optuna-dashboard` | a different package |", False),
    ("| x | `pypi:optuna` | not the first cell |", False),
])
def test_a_row_is_a_table_row_whose_first_cell_is_the_id(body, ok):
    assert ra.has_row(body, "pypi:optuna") is ok


def test_url_ids_that_are_prefixes_need_their_own_row():
    body = "| `url:https://github.com/a/bc` | catalogue link |"
    assert ra.has_row(body, "url:https://github.com/a/bc") and not ra.has_row(body, "url:https://github.com/a/b")


def test_an_unread_advisory_record_fails_closed(tmp_path):
    """OSV names an advisory, then its record cannot be read: it must not look milder than the record would."""
    def osv(q):
        return ["GHSA-gone"] if q.get("package", {}).get("name") == "marked" else []
    net = online_net(tmp_path, osv=osv, http={f"{ra.OSV}/vulns/GHSA-gone": DOWN})
    r = run(checkout(tmp_path), net)
    f = next(f for f in r["findings"] if f["check"] == "advisory" and f["subject"] == "npm:marked")
    assert f["severity"] == "high" and "record not read" in f["evidence"] and "No fixed release" not in f["action"]
    assert "GHSA-gone" in f["action"] and ra.failing(r, "high")
    note = next(f for f in r["findings"] if f["check"] == "osv-unverified")
    assert note["severity"] == "info" and "GHSA-gone" in note["evidence"]


def test_transitive_python_dependencies_are_checked(tmp_path):
    """deps.dev's resolved graph of a direct dependency's newest release: OSV is asked about every package in it."""
    graph = {"nodes": [{"versionKey": {"system": "PYPI", "name": "pyyaml", "version": "6.0.3"}, "relation": "SELF"},
                       {"versionKey": {"system": "PYPI", "name": "Deep_Lib", "version": "1.2.0"}, "relation": "INDIRECT"}]}

    def osv(q):
        return ["GHSA-deep"] if q.get("package", {}).get("name") == "deep-lib" else []
    net = online_net(tmp_path, osv=osv, http={
        "https://api.deps.dev/v3/systems/pypi/packages/pyyaml/versions/6.0.3:dependencies": graph,
        f"{ra.OSV}/vulns/GHSA-deep": vuln("GHSA-deep", "HIGH", "1.3.0", "PyPI", "deep-lib")})
    r = run(checkout(tmp_path), net)
    f = next(f for f in r["findings"] if f["subject"] == "pypi:deep-lib")
    assert f["severity"] == "high" and "transitive" in f["title"] and "through pyyaml" in f["title"]
    assert ">=1.3.0" in f["action"] and f["scope"] == "deps.dev"
    assert {"name": "deep-lib", "version": "1.2.0", "via": ["pyyaml"]} in r["extra"]["python_transitive"]
    assert any("transitive" in limit.lower() for limit in r["limits"])


def test_acceptances_need_a_fingerprint_for_advisories_and_never_cover_critical(tmp_path):
    bad = write(tmp_path, "accepted.yaml", "- {check: advisory, subject: 'npm:x', reason: moderate, accepted: 2026-11-01}\n")
    with pytest.raises(SystemExit, match="needs its fp"):
        ra.load_accepted(bad)
    ok = write(tmp_path, "ok.yaml", "- {check: npm-install-script, subject: 'npm:fsevents', reason: macOS only}\n")
    assert ra.load_accepted(ok)[0]["subject"] == "npm:fsevents"
    mal = {"severity": "critical", "check": "advisory", "subject": "npm:x", "fp": "f" * 16}
    assert ra.accepted_reason([{"check": "advisory", "subject": "npm:x", "fp": "f" * 16, "reason": "r"}], mal) is None
    moderate = dict(mal, severity="medium")
    assert ra.accepted_reason([{"check": "advisory", "subject": "npm:x", "fp": "f" * 16, "reason": "r"}], moderate)


def test_the_token_never_follows_a_redirect(monkeypatch):
    """urllib copies plain headers to a redirect's target, whatever its host: the token goes in as unredirected."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"] = req
        raise ra.urllib.error.URLError("offline")
    monkeypatch.setattr(ra.urllib.request, "urlopen", fake_urlopen)
    net = ra.Net()
    net.token, net.gh = "t0ken", None
    net.github("repos/a/b")
    req = seen["req"]
    assert req.unredirected_hdrs.get("Authorization") == "Bearer t0ken" and "Authorization" not in req.headers
    redirected = ra.urllib.request.HTTPRedirectHandler().redirect_request(req, None, 302, "Found", {}, "https://elsewhere.invalid/")
    assert "Authorization" not in redirected.headers and "Authorization" not in redirected.unredirected_hdrs


def test_a_flagged_vendored_upstream_is_not_linked(tmp_path):
    root = checkout(tmp_path)
    r = run(root, online_net(tmp_path, gh={"repos/someone/tool": repo("other/tool")}))
    assert ("repo-moved", "vendor:tool") in checks(r)
    md = ra.to_markdown(r)
    assert "[tool](https://github.com/someone/tool)" not in md and "`https://github.com/someone/tool`" in md
    clean = ra.to_markdown(run(checkout(tmp_path / "c")))
    assert "[tool](https://github.com/someone/tool)" in clean


def test_our_own_plugin_at_a_release_is_not_registry_advice(tmp_path):
    root = checkout(tmp_path)
    write(root, "docs/contributing-agents.md", "# Agents\n\n```bash\nclaude plugin marketplace add Valpatel/cad-agent#v0.8.0\n"
                                               "claude plugin install cad-agent@valpatel\n```\n")
    assert not [f for f in run(root)["findings"] if f["check"] == "install-from-registry"]
    write(root, "docs/contributing-agents.md", "# Agents\n\n```bash\nclaude plugin marketplace add Valpatel/cad-agent\n"
                                               "claude plugin install cad-agent@valpatel\n```\n")     # unpinned: still advice
    assert len([f for f in run(root)["findings"] if f["check"] == "install-from-registry"]) == 2
    write(root, "docs/contributing-agents.md", "# Agents\n\n```bash\nclaude plugin marketplace add someone/else#v1.0\n```\n")
    assert [f for f in run(root)["findings"] if f["check"] == "install-from-registry"]


def test_repo_settings_need_an_admin_token(tmp_path):
    """A 404 on vulnerability-alerts means "off" only to an admin; GitHub says 404 to everyone else too."""
    class Settings(FakeNet):
        def __init__(self, admin):
            super().__init__(osv=lambda q: [])
            self.admin = admin

        def github(self, path):
            if path == "repos/o/r":       # security_and_analysis comes only with admin rights
                sa = {"secret_scanning": {"status": "enabled"}, "dependabot_security_updates": {"status": "enabled"}}
                return 200, {"full_name": "o/r", "permissions": {"admin": self.admin},
                             **({"security_and_analysis": sa} if self.admin else {})}, ""
            return 404, {"message": "Not Found"}, ""
    for admin in (False, True):
        r = run(checkout(tmp_path / str(admin)), Settings(admin), repo="o/r")
        assert (("repo-dependabot-alerts", "repo:o/r") in checks(r)) is admin
        row = next(x for x in r["inventory"]["repo"] if x["id"] == "repo:o/r")
        assert row["dependabot_alerts"] == ("disabled" if admin else "not verified (needs admin)")
        assert ("repo:o/r" in r["unverified"]) is not admin


def test_a_private_repository_is_reported_as_gone_with_nothing_about_it(tmp_path):
    net = online_net(tmp_path, gh={"repos/gumyr/build123d": repo("gumyr/build123d", private=True, description="secret plans")})
    r = run(checkout(tmp_path), net)
    assert ("repo-gone", "url:https://github.com/gumyr/build123d") in checks(r, "high")
    assert "secret plans" not in json.dumps(r)
    row = next(x for x in r["inventory"]["links"] if x["id"] == "url:https://github.com/gumyr/build123d")
    assert row["github"]["state"] == "gone" and row["github"]["full_name"] is None


# ------------------------------------------------------------------------------------------- the web kit's receipts
def tgz(files):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), 0
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def integrity(data):
    import base64
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


MJS = b'/* mermaid 11.17.2 */ t.version="3.4.12"; katex:"0.16.47"'


def receipt_checkout(root, mjs=MJS, bundled=None, tarball_mjs=None):
    """The fixture with a Mermaid receipt as #192 writes them, and the npm tarball it names."""
    checkout(root)
    write(root, f"{ra.KIT}/mermaid/mermaid.min.js", mjs)
    pkg = tgz({"package/dist/mermaid.min.js": tarball_mjs or mjs, "package/LICENSE": MIT.encode()})
    url = "https://registry.npmjs.org/mermaid/-/mermaid-11.17.2.tgz"
    write(root, f"{ra.KIT}/mermaid/SOURCE.json", json.dumps({
        "package": "mermaid", "version": "11.17.2", "source": url, "npm_integrity": integrity(pkg), "license": "MIT",
        "files": {"mermaid.min.js": hashlib.sha256(mjs).hexdigest(), "LICENSE": hashlib.sha256(MIT.encode()).hexdigest()},
        "paths_in_package": {"mermaid.min.js": "package/dist/mermaid.min.js", "LICENSE": "package/LICENSE"},
        "bundled": bundled or {"dompurify": "3.4.12", "katex": "0.16.47", "note": "inlined"}}))
    write(root, "THIRD_PARTY_NOTICES.md", (root / "THIRD_PARTY_NOTICES.md").read_text().replace("11.4.1", "11.17.2"))
    return root, url, pkg


def test_kit_components_come_from_the_receipts(tmp_path):
    root, _url, _pkg = receipt_checkout(tmp_path)
    write(root, f"{ra.KIT}/file-viewer-sources.json", json.dumps({
        "three": {"tag": "r160", "source": "https://github.com/mrdoob/three.js/tree/r160/examples/jsm"},
        "fflate": {"version": "0.8.3", "repository": "https://github.com/101arrowz/fflate/tree/v0.8.3"}}))
    comps = ra.webkit_components(root)
    assert comps["file-parsers"]["packages"] == [("three", "0.160.0"), ("fflate", "0.8.3")]
    assert comps["file-parsers"]["repos"] == ["101arrowz/fflate", "mrdoob/three.js"]
    assert comps["mermaid"]["bundled"] == [("dompurify", "3.4.12"), ("katex", "0.16.47")]
    r = run(root)
    row = next(w for w in r["inventory"]["webkit"] if w["name"] == "mermaid")
    assert row["bundled"] == ["dompurify@3.4.12", "katex@0.16.47"] and row["hashed"] == 2
    assert not [f for f in r["findings"] if f["severity"] != "info"], r["findings"]


def test_a_receipt_that_disagrees_with_its_file_is_found_offline(tmp_path):
    root, _url, _pkg = receipt_checkout(tmp_path, bundled={"dompurify": "3.9.9", "note": "x"})
    src = json.loads((root / f"{ra.KIT}/mermaid/SOURCE.json").read_text())
    src.update(source="https://example.invalid/mermaid.tgz")
    write(root, f"{ra.KIT}/mermaid/SOURCE.json", json.dumps(src))
    by = {(f["check"], f["title"]) for f in run(root)["findings"]}
    assert any(c == "webkit-version" and "bundles dompurify 3.9.9" in t for c, t in by)
    assert any(c == "webkit-receipt" and "does not name the npm tarball" in t for c, t in by)
    write(root, f"{ra.KIT}/mermaid/SOURCE.json", "[not json")
    assert ("webkit-receipt", "webkit:mermaid") in checks(run(root), "high")


def test_bundled_libraries_are_asked_about_and_files_checked_against_their_package(tmp_path):
    root, url, pkg = receipt_checkout(tmp_path)

    def osv(q):
        return ["GHSA-dom"] if q.get("package", {}).get("name") == "dompurify" else []
    net = online_net(tmp_path, osv=osv, files={url: pkg},
                     http={f"{ra.OSV}/vulns/GHSA-dom": vuln("GHSA-dom", "MODERATE", "3.4.17", name="dompurify")})
    r = run(root, net)
    f = next(f for f in r["findings"] if f["check"] == "advisory" and f["subject"] == "webkit:mermaid")
    assert "dompurify 3.4.12, bundled inside a vendored file" in f["title"] and "dompurify >=3.4.17" in f["action"]
    row = next(w for w in r["inventory"]["webkit"] if w["name"] == "mermaid")
    assert row["receipts"]["mermaid"] == {"files": 2, "identical": 2, "differ": [], "missing": []}
    assert not [f for f in r["findings"] if f["check"].startswith("webkit-") and f["severity"] != "info"]


def test_a_file_that_differs_from_its_package_is_drift(tmp_path):
    root, url, pkg = receipt_checkout(tmp_path, tarball_mjs=MJS + b" upstream")
    r = run(root, online_net(tmp_path, files={url: pkg}))
    assert ("webkit-drift", "webkit:mermaid") in checks(r, "high")
    root2, url2, pkg2 = receipt_checkout(tmp_path / "b")
    r2 = run(root2, online_net(tmp_path, files={url2: pkg2 + b"tampered"}))      # the registry serves other bytes
    assert ("webkit-receipt-integrity", "webkit:mermaid") in checks(r2, "high")
    r3 = run(root2, online_net(tmp_path))                                        # no answer: not verified, not a failure
    assert ("webkit-receipt-unverified", "webkit:mermaid") in checks(r3, "info") and "webkit:mermaid" in r3["unverified"]


def test_the_repo_receipts_match_their_files_offline():
    """The real kit: every receipt reads, every bundled version is in its file, every receipt names its tarball."""
    r = ra.build(ROOT, AS_OF, None, npm_audit=False).to_json()
    bad = [f for f in r["findings"] if f["check"] in ("webkit-receipt", "webkit-version", "webkit-hash", "webkit-hash-missing")]
    assert not bad, bad
    mer = next(w for w in r["inventory"]["webkit"] if w["name"] == "mermaid")
    assert mer["bundled"] and all("@" in b for b in mer["bundled"])


# --------------------------------------------------------------------------------------------- the weekly issue
def test_an_unanswered_week_keeps_its_findings_open():
    """A finding whose scope did not answer this week is "not re-checked", not resolved: no close-and-reopen churn."""
    gone, kept = "a" * 16, "b" * 16
    marker = f"fps={gone}~{ra.scope_tag('url:https://x.org/')},{kept}~{ra.scope_tag('deps.dev')}"
    mine = {"number": 7, "author": {"login": "app/github-actions"}, "body": f"x\n<!-- cad-supply-chain-report {marker} -->"}
    r = report_with()
    r["unverified"] = ["deps.dev"]                       # deps.dev did not answer; the link was re-checked and is fine
    plan, note = ra.plan_issue(r, [mine], "o/r", "T")
    assert "1 resolved, 1 not re-checked" in note and [p[0][1] for p in plan] == ["edit", "comment"]
    assert f"fps={kept}~{ra.scope_tag('deps.dev')} -->" in plan[0][1] and "could not be re-checked" in plan[0][1]


def test_issue_text_mentions_nobody():
    text = "Thanks @someone and @org/team, see #123 and x/y#4; `@scope/pkg` and `#5` in code; mail a@b.c; &#39;"
    out = ra.no_mentions(text)
    assert "@someone" not in out and "@org/team" not in out and "#123" not in out and "x/y#4" not in out
    assert "`@scope/pkg`" in out and "`#5`" in out and "a@b.c" in out and "&#39;" in out
    r = report_with(("high", "advisory", "c" * 16))
    r["findings"][0]["evidence"] = "GHSA-x: reported by @attacker in #1"
    body = ra.plan_issue(r, [], "o/r", "T")[0][0][1]
    assert "@attacker" not in body and "#1 " not in body


# ------------------------------------------------------------------------------------------ the page and the figure
def test_published_pages_match_the_site_build():
    """published() must pick the same Markdown files as tools/build-site.mjs's SECTIONS (both are read from the source)."""
    import re
    src = (ROOT / "tools/build-site.mjs").read_text()
    block = src[src.index("const SECTIONS = ["):src.index("];", src.index("const SECTIONS = ["))]
    patterns = [re.compile(p.replace("\\/", "/")) for p in re.findall(r"/(\^.*?\$)/\.test\(f\)", block)]
    files = set(re.findall(r"f === '([^']+)'", block))
    assert len(patterns) == len(ra.PUBLISHED) and files == set(ra.PUBLISHED_FILES)
    assert [p.pattern for p in patterns] == [p.pattern for p in ra.PUBLISHED]
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    for f in tracked:
        want = (f in files or any(p.match(f) for p in patterns)) and not re.search(r"(?:^|/)(?:AGENTS|CLAUDE)\.md$", f)
        assert ra.published(f, report=True) == want, f


def test_figure_is_deterministic_and_says_what_it_leaves_out(tmp_path):
    r = run(checkout(tmp_path))
    r["findings"] += [dict(severity="high", check="advisory", subject="pypi:x", title="t", evidence="", action="", fp="1" * 16),
                      dict(severity="low", check="link-dead", subject="url:https://x.org/", title="t", evidence="",
                           action="", fp="2" * 16, accepted="fine (2026-11-01)")]
    a, b = ra.findings_svg(r), ra.findings_svg(r)
    assert a == b and a.startswith("<svg") and "Python dependencies: 1 high" in a
    assert "Links and catalogue: none" in a                     # the accepted finding is not drawn
    assert "/home/" not in a and str(tmp_path) not in a



def test_committed_page_and_figure_match_committed_report():
    """research/security-report.md and docs/img/supply-chain/findings.svg are rendered from research/security-report.json,
    so neither can disagree with it."""
    assert ra.main(["render", "--check"]) == 0


def test_the_page_folds_all_but_critical_and_high(tmp_path):
    r = run(checkout(tmp_path))
    r["findings"] += [dict(severity=s, check=c, subject="pypi:x", title=c, evidence="", action="", fp=str(i) * 16)
                      for i, (s, c) in enumerate([("high", "advisory"), ("medium", "link-dead"), ("low", "repo-stale")])]
    md = ra.to_markdown(r, figure="f.svg")
    high, medium = md.index("### High (1)"), md.index("### Medium (1)")
    assert "<details>" not in md[high:medium] and "<details><summary>1 medium: 1 link-dead</summary>" in md
    assert md.index("<details><summary><strong>Limits.") < md.index("## Findings") and md.count("<details>") == md.count("</details>")


def test_committed_report_is_clean_and_dated():
    """The committed report came from a committed tree (no uncommitted changes) and has no private details."""
    r = json.loads((ROOT / "research/security-report.json").read_text())
    assert r["schema"] == ra.SCHEMA and r["dirty"] is False and r["mode"] == "online"
    text = (ROOT / "research/security-report.json").read_text() + (ROOT / "research/security-report.md").read_text()
    home = str(Path.home())          # whichever machine runs it: no account name is written down here
    assert not any(p in text for p in ("/home/", "/Users/")) and (len(home) < 2 or home not in text)
