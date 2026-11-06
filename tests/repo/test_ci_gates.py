"""The merge gates in tools/ci_gates.py: branch flow, review verdicts, release versions."""
import importlib.util
import base64
import json
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ci_gates", Path(__file__).parents[2] / "tools" / "ci_gates.py")
gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gates)

HEAD = "a188011" + "0" * 33
OLD = "1234567" + "0" * 33
MAIN = "b" * 40
PUBLISHED = "## v0.4.2 (2026-10-31)\n\n**Fixed**\n- Shipped fix.\n\n## v0.4.1 (2026-10-30)\n\n- Earlier fix.\n"
LOG = "# Changelog\n\n## Unreleased\n\n" + PUBLISHED
WRITERS = {"mvalancy", "reviewer-bot"}
can_review = WRITERS.__contains__
_ids = iter(range(1000, 10**6))


def review(verdict, sha=HEAD, who="mvalancy", state="COMMENTED", before="Summary.", after=""):
    body = f"{before}\n<!-- cad-review verdict={verdict} sha={sha} -->{after}"
    return {"id": next(_ids), "state": state, "user": {"login": who}, "body": body}


def gate(reviews, head=HEAD):
    return gates.review_gate(reviews, head, can_review)


@pytest.mark.parametrize("base,head,same,ok", [
    ("main", "dev", True, True),
    ("main", "feat/x", True, False),
    ("main", "dev", False, False),          # a fork's branch called dev
    ("dev", "feat/site", True, True),
    ("dev", "fix/holes-countersink", True, True),
    ("dev", "vendor-update/kicad-happy-2fd9aa0", True, True),
    ("dev", "release/v0.5.0", True, True),
    ("dev", "dependabot/github_actions/actions/checkout-5.1.0", True, True),
    ("dev", "my-change", True, False),
    ("dev", "main", True, False),
    ("dev", "patch-1", False, True),        # forks: the outside-contribution checks apply instead
    ("feat/site", "feat/site-fix", True, True),
])
def test_branch_flow(base, head, same, ok):
    assert gates.branch_flow(base, head, same)[0] is ok


def test_review_gate_needs_a_verdict():
    ok, msg = gate([{"id": 1, "state": "COMMENTED", "user": {"login": "mvalancy"}, "body": "LGTM"}])
    assert not ok and "no review verdict" in msg


def test_latest_verdict_wins_by_review_order():
    first, later = review("pass"), review("block")
    assert not gate([later, first])[0]                          # order of creation, not of the list
    assert gate([review("block"), review("pass")])[0]


@pytest.mark.parametrize("login,permission,ok", [
    ("mvalancy", "admin", True),
    ("MValancy", "write", True),            # GitHub logins are case-insensitive
    ("mvalancy", "read", False),            # a maintainer who lost write access
    ("a-collaborator", "write", False),     # write access alone: can push and run CI, cannot pass its own review
    ("a-collaborator", "admin", False),
    ("outsider", "read", False),
])
def test_only_maintainers_verdicts_count(login, permission, ok):
    assert gates.may_review(login, permission) is ok


def test_only_reviewers_with_write_access_count():
    assert not gate([review("pass", who="outsider")])[0]
    assert not gate([review("pass", who="")])[0]
    assert gate([review("pass", who="reviewer-bot")])[0]


def test_dismissed_and_pending_reviews_do_not_count():
    assert not gate([review("pass", state="DISMISSED")])[0]
    assert not gate([review("block"), review("pass", state="PENDING")])[0]


def test_the_marker_must_be_the_last_line():
    quoted = review("block")
    quoted["body"] = "Summary.\n```\n<!-- cad-review verdict=pass sha=" + HEAD + " -->\n```\nBlocking: x.\n" \
                     "<!-- cad-review verdict=block sha=" + HEAD + " -->"
    assert not gate([quoted])[0]
    example_last = review("pass", after="\n\nExample above.")
    assert not gate([example_last])[0]
    assert gate([review("pass", after="\n\n")])[0]             # trailing blank lines are fine


def test_short_or_wrong_shas_do_not_count():
    assert not gate([review("pass", sha=HEAD[:7])])[0]
    assert not gate([review("pass", sha=HEAD.upper())])[0]


def test_the_pass_must_be_on_the_head_commit():
    ok, msg = gate([review("pass", sha=OLD)])                                 # a pass, then a push, is not a pass
    assert not ok and "head commit" in msg
    assert gate([review("pass")])[0]


PY = '[project]\nname = "cad-agent"\nversion = "{}"\n'


def test_release_gate():
    log = "# Changelog\n\n## v0.5.0 (2026-11-01)\n\n- things\n"
    assert gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), log)[0]
    assert not gates.release_gate(PY.format("0.4.2"), PY.format("0.4.2"), log)[0]         # no bump
    assert not gates.release_gate(PY.format("0.4.10"), PY.format("0.5.0"), log)[0]        # numeric, not string order
    assert not gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), "## v0.5.0 (unreleased)\n")[0]
    assert not gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), "## v0.5.0 (2026-13-45)\n")[0]


def test_version_comes_from_the_project_table():
    tool_first = '[tool.x]\nversion = "9.9.9"\n\n[project]\nname = "x"\nversion = "0.5.0"\n'
    assert gates.parse_version(tool_first) == (0, 5, 0)
    with pytest.raises(ValueError):
        gates.parse_version("[project]\n")


def test_repo_version_parses():
    gates.parse_version((Path(__file__).parents[2] / "pyproject.toml").read_text())


def test_cli_version(capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[2])
    assert gates.main(["version"]) == 0
    assert capsys.readouterr().out.strip().count(".") >= 1


class FakeGitHub:
    """Stands in for `gh`: answers the PR, reviews, permission and PR-list calls, and records status posts."""
    def __init__(self, prs, reviews=(), fail=(), store=lambda d: d, main_log=LOG, head_log=LOG):
        self.prs, self.reviews, self.fail, self.posts, self.posts_full = prs, list(reviews), set(fail), [], []
        self.store = store                  # what GitHub might do to a description when it stores it
        self.main_log, self.head_log, self.calls = main_log, head_log, []

    def __call__(self, *args):
        path = next(a for a in args if a.startswith("repos/"))
        self.calls.append(path)
        if path in self.fail:
            raise subprocess.CalledProcessError(1, "gh")
        if "-X" in args:
            fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("repos/"))
            self.posts.append((path.rsplit("/", 1)[1], fields["context"], fields["state"]))
            self.posts_full.append((path.rsplit("/", 1)[1], fields["context"], fields["state"], self.store(fields["description"])))
            return "{}"
        if "/commits/" in path and "/status" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            latest = {}
            for s_sha, c, st, d in self.posts_full:
                if s_sha == sha:
                    latest[c] = (st, d)
            return json.dumps({"statuses": [{"context": c, "state": st, "description": d} for c, (st, d) in latest.items()]})
        if path.endswith("/reviews"):
            return "\n".join(json.dumps(r) for r in self.reviews)
        if path.endswith("/commits/main"):
            return MAIN
        if "/contents/CHANGELOG.md?ref=" in path:
            raw = (self.main_log if path.endswith(MAIN) else self.head_log).encode("utf-8")
            return json.dumps({"type": "file", "encoding": "base64", "size": len(raw),
                               "content": base64.b64encode(raw).decode("ascii")})
        if "/collaborators/" in path:
            return json.dumps({"permission": "admin" if "/mvalancy/" in path else "read"})
        if "pulls?state=open" in path:
            return "\n".join(str(n) for n, pr in self.prs.items() if pr["base"]["ref"] in ("dev", "main"))
        n = int(path.rsplit("/", 1)[1])
        if n in self.fail:
            raise subprocess.CalledProcessError(1, "gh")
        return json.dumps(self.prs[n])


def pr(n, base="dev", ref="feat/x", sha=HEAD):
    return {"number": n, "base": {"ref": base}, "head": {"ref": ref, "sha": sha, "repo": {"full_name": "o/r"}}}


def test_post_names_statuses_after_the_base_and_goes_pending_first(monkeypatch):
    fake = FakeGitHub({5: pr(5)}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.run("o/r", 5, do_post=True) == 0
    assert fake.posts[:2] == [(HEAD, "cad-gates/dev/branch-flow", "pending"), (HEAD, "cad-gates/dev/review", "pending")]
    assert fake.posts[2:] == [(HEAD, "cad-gates/dev/branch-flow", "success"), (HEAD, "cad-gates/dev/review", "success")]
    assert gates.contexts("main") == ["cad-gates/main/branch-flow", "cad-gates/main/review", "cad-gates/main/release"]


def test_a_failing_gate_is_a_failure_status_not_an_error(monkeypatch):
    fake = FakeGitHub({5: pr(5, ref="my-change")}, [review("block")])
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.run("o/r", 5, do_post=True) == 0
    assert {(c, s) for _, c, s in fake.posts[2:]} == {("cad-gates/dev/branch-flow", "failure"), ("cad-gates/dev/review", "failure")}
    assert gates.run("o/r", 5, do_post=False) == 1                           # the pre-merge check exits 1


@pytest.mark.parametrize("changed", [
    LOG.replace("Shipped fix.", "A change that never shipped."),
    LOG.replace("2026-10-31", "2026-11-01"),
    LOG.replace("v0.4.2", "v0.4.3"),
    LOG.replace("- Shipped fix.", "- Shipped fix. \t"),
    "# Changelog\n\n## Unreleased\n",
    LOG + "\n## v0.3.0 (2026-10-29)\n\n- Added underneath published history.\n",
    LOG.replace("## v0.4.1", "## Appendix\n\nExtra section.\n\n## v0.4.1"),
    LOG.replace("## v0.4.1", "## v0.4.15 (2026-10-30)\n\n- Inserted.\n\n## v0.4.1"),
    LOG.replace("v0.4.1 (2026-10-30)", "v0.4.2 (2026-10-30)"),
    LOG.replace("v0.4.2 (2026-10-31)", "v0.4.2 (2026-13-31)"),
    LOG.replace("v0.4.2 (2026-10-31)", "v0.4.2 (2026-10)"),
], ids=["body", "date", "version", "meaningful-whitespace", "deleted", "appended", "extra-heading",
        "inserted-release", "duplicate-version", "impossible-date", "malformed-date"])
def test_historical_changes_fail_the_existing_gate_despite_a_valid_review(monkeypatch, changed):
    fake = FakeGitHub({5: pr(5)}, [review("pass")], head_log=changed)
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.main(["all", "--repo", "o/r", "--pr", "5"]) == 1
    assert gates.run("o/r", 5, do_post=True) == 0
    assert fake.posts[-2:] == [(HEAD, "cad-gates/dev/branch-flow", "failure"),
                              (HEAD, "cad-gates/dev/review", "success")]
    assert fake.calls.count(f"repos/o/r/contents/CHANGELOG.md?ref={MAIN}") == 2
    assert fake.calls.count(f"repos/o/r/contents/CHANGELOG.md?ref={HEAD}") == 2


def test_released_entries_cannot_be_reordered(monkeypatch):
    latest, earlier = PUBLISHED.split("## v0.4.1", 1)
    changed = "# Changelog\n\n## Unreleased\n\n## v0.4.1" + earlier + "\n" + latest
    fake = FakeGitHub({5: pr(5)}, [review("pass")], head_log=changed)
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.main(["all", "--repo", "o/r", "--pr", "5"]) == 1


def test_unreleased_and_real_cut_release_output_preserve_history(monkeypatch):
    spec = importlib.util.spec_from_file_location("cut_release", Path(__file__).parents[2] / "tools/cut_release.py")
    cutter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cutter)
    fragment = ("docs/changelog.d/123-fix.md", "**Fixed**\n- A newly shipped fix.\n")
    _, released, version = cutter.cut(PY.format("0.4.2"), LOG, bump="patch", date="2026-11-01",
                                      fragments=[fragment])
    assert version == "0.4.3"
    for candidate in (LOG, LOG.replace("## Unreleased", "## Unreleased\n\n**Fixed**\n- Pending fix."), released):
        fake = FakeGitHub({5: pr(5)}, [review("pass")], head_log=candidate)
        monkeypatch.setattr(gates, "_gh", fake)
        assert gates.main(["all", "--repo", "o/r", "--pr", "5"]) == 0


def test_fork_changelog_uses_its_own_repository_at_the_reviewed_sha(monkeypatch):
    fork = pr(5)
    fork["head"]["repo"]["full_name"] = "contributor/fork"
    fake = FakeGitHub({5: fork}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.run("o/r", 5, do_post=False) == 0
    assert f"repos/contributor/fork/contents/CHANGELOG.md?ref={HEAD}" in fake.calls
    assert f"repos/o/r/contents/CHANGELOG.md?ref={HEAD}" not in fake.calls


@pytest.mark.parametrize("baseline", ["", "# Changelog\n\n## Unreleased\n", LOG.replace("2026-10-31", "yesterday"),
                                      LOG + "\n## Appendix\nNo dated history here.\n"])
def test_an_empty_or_malformed_baseline_cannot_pass_vacuously(monkeypatch, baseline):
    fake = FakeGitHub({5: pr(5)}, [review("pass")], main_log=baseline)
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.run("o/r", 5, do_post=False) == 1


@pytest.mark.parametrize("response", [
    {"type": "symlink", "encoding": "base64", "size": 0, "content": ""},
    {"type": "file", "encoding": "none", "size": 2**21, "content": ""},
    {"type": "file", "encoding": "base64", "size": 2**21, "content": ""},
    {"type": "file", "encoding": "base64", "size": 1, "content": "?"},
    {"type": "file", "encoding": "base64", "size": 1, "content": "/w=="},
    {"type": "file", "encoding": "base64", "size": 2, "content": "YQ=="},
], ids=["not-a-file", "unsupported-encoding", "oversized", "invalid-base64", "invalid-utf8", "truncated"])
def test_unreadable_history_supersedes_an_old_green_with_pending(monkeypatch, response):
    fake = FakeGitHub({5: pr(5)}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fake)
    assert gates.run("o/r", 5, do_post=True) == 0
    def broken(*args):
        if f"repos/o/r/contents/CHANGELOG.md?ref={HEAD}" in args:
            return json.dumps(response)
        return fake(*args)
    monkeypatch.setattr(gates, "_gh", broken)
    with pytest.raises(ValueError):
        gates.run("o/r", 5, do_post=True)
    assert fake.posts[-2:] == [(HEAD, "cad-gates/dev/branch-flow", "pending"),
                              (HEAD, "cad-gates/dev/review", "pending")]


def test_missing_history_and_unresolved_main_sha_fail_closed(monkeypatch):
    fake = FakeGitHub({5: pr(5)}, [review("pass")], fail={f"repos/o/r/contents/CHANGELOG.md?ref={HEAD}"})
    monkeypatch.setattr(gates, "_gh", fake)
    with pytest.raises(subprocess.CalledProcessError):
        gates.run("o/r", 5, do_post=True)
    assert [state for _, _, state in fake.posts] == ["pending", "pending"]
    def missing_sha(*args):
        return "main" if "repos/o/r/commits/main" in args else fake(*args)
    monkeypatch.setattr(gates, "_gh", missing_sha)
    with pytest.raises(ValueError, match="full commit SHA"):
        gates.run("o/r", 5, do_post=False)


def test_only_blank_section_separators_may_change():
    separated = LOG.replace("\n\n## v0.4.1", "\n \t\n\n\n## v0.4.1") + "\n\t \n"
    assert gates.changelog_history(separated, LOG)[0]
    assert not gates.changelog_history(LOG.replace("- Earlier fix.", "  - Earlier fix."), LOG)[0]


def test_a_crash_leaves_the_statuses_pending(monkeypatch):
    fake = FakeGitHub({5: pr(5)})
    def reviews_fail(*args):
        if any(a.endswith("/reviews") for a in args):
            raise subprocess.CalledProcessError(1, "gh")
        return fake(*args)
    monkeypatch.setattr(gates, "_gh", reviews_fail)
    with pytest.raises(subprocess.CalledProcessError):
        gates.run("o/r", 5, do_post=True)
    assert [s for _, _, s in fake.posts] == ["pending", "pending"]


def test_sweep_covers_every_open_pr_into_dev_and_main_and_reports_errors(monkeypatch, capsys):
    # the PR that fails to load comes first, so a sweep that stopped at an error would miss the others
    fake = FakeGitHub({8: pr(8), 5: pr(5), 6: pr(6, base="main", ref="dev"), 7: pr(7, base="feat/site")}, [review("pass")], fail={8})
    monkeypatch.setattr(gates, "_gh", fake)
    monkeypatch.setattr(gates, "evaluate", lambda repo, n, p=None: (p, {"branch-flow": (True, "ok"), "review": (True, "ok")}))
    assert gates.sweep("o/r", do_post=True) == 1                             # #8 failed to load
    assert {c.split("/")[1] for _, c, s in fake.posts if s == "success"} == {"dev", "main"}
    assert "ERROR #8" in capsys.readouterr().err


def test_the_sweep_posts_only_changes_and_never_pending(monkeypatch):
    """GitHub keeps at most 1000 statuses per commit and name: a sweep every 15 minutes that re-posted everything would
    freeze an unchanged head's statuses within days (review of #116). A later block must still turn the review red."""
    fake = FakeGitHub({5: pr(5)}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fake)
    for _ in range(500):
        gates.sweep("o/r", do_post=True)
    assert len(fake.posts) == 2 and all(s == "success" for _, _, s in fake.posts)        # posted once, never pending
    fake.reviews.append(review("block"))
    assert gates.sweep("o/r", do_post=True) == 0                     # a failing gate is a status, not a job failure
    assert fake.posts[-1] == (HEAD, "cad-gates/dev/review", "failure")
    assert gates.sweep("o/r", do_post=False) == 1                    # without --post, a failing gate exits 1
    assert len(fake.posts) == 3


@pytest.mark.parametrize("store", [lambda d: d, str.strip, lambda d: " ".join(d.split())],
                         ids=["verbatim", "trimmed", "collapsed"])
def test_the_sweep_is_not_fooled_by_how_github_stores_descriptions(monkeypatch, store):
    """Review 4 of #116: a description cut at 139 characters on a space may come back changed; the sweep must still
    see it as current, or it re-posts every time and the 1000-status limit returns. (Doubled spaces can't occur in what
    _status posts; statuses stored raw, from before describe(), are the raw-text test's job.)"""
    # a branch name whose failure text, cut at 139 characters, ends on a space; no verdict yet on the review gate
    ref = next("x" * n for n in range(5, 120) if gates.branch_flow("dev", "x" * n, True)[1][:139].endswith(" "))
    fake = FakeGitHub({5: pr(5, ref=ref)}, [], store=store)
    monkeypatch.setattr(gates, "_gh", fake)
    for _ in range(50):
        gates.sweep("o/r", do_post=True)
    per_name = {}
    for _, context, _ in fake.posts:
        per_name[context] = per_name.get(context, 0) + 1
    assert per_name and all(n == 1 for n in per_name.values()), per_name


def test_the_sweep_repairs_a_pending_left_by_a_crashed_run_and_posts_a_new_description(monkeypatch):
    fake = FakeGitHub({5: pr(5)}, [review("pass", sha=OLD)])
    monkeypatch.setattr(gates, "_gh", fake)
    for context in gates.contexts("dev"):                     # a per-PR run that crashed after its pending step
        gates._status("o/r", HEAD, context, "pending", "evaluating")
    gates.sweep("o/r", do_post=True)
    assert [s for _, _, s in fake.posts[-2:]] == ["success", "failure"]      # branch-flow passes; review: old pass
    before = len(fake.posts)
    fake.reviews.append(review("block", sha=HEAD))           # still failing, for a different reason
    gates.sweep("o/r", do_post=True)
    assert len(fake.posts) == before + 1 and fake.posts_full[-1][3].startswith("latest verdict is block")


def test_describe_collapses_whitespace_cuts_at_139_and_is_stable():
    """Review of #129: these hold for describe() itself, not only through the sweep (gate texts rarely carry whitespace)."""
    assert gates.describe("a  b\nc\t d ") == "a b c d"
    assert gates.describe("  x\u00a0\u2003y  ") == "x y"                    # any Unicode whitespace
    long = ("word " * 60).strip()
    assert len(gates.describe(long)) <= 139 and not gates.describe(long).endswith(" ")
    assert len(gates.describe("x" * 300)) == 139                         # the cut is at 139, not merely within it
    for text in ("a  b\nc", long, " lead", "trail ", "x" * 300, "é\u0301  ü"):
        assert gates.describe(gates.describe(text)) == gates.describe(text)


def test_the_sweep_reads_older_raw_descriptions_as_current(monkeypatch):
    """A status posted before describe() existed (doubled spaces, a trailing space) is the same status, not a change:
    current() must normalise what it reads, or the first sweeps after an upgrade re-post everything."""
    fresh = FakeGitHub({5: pr(5)}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fresh)
    gates.sweep("o/r", do_post=True)
    old = FakeGitHub({5: pr(5)}, [review("pass")])
    old.posts_full = [(sha, c, st, d.replace(" ", "  ") + " ") for sha, c, st, d in fresh.posts_full]   # as raw text
    monkeypatch.setattr(gates, "_gh", old)
    gates.sweep("o/r", do_post=True)
    assert old.posts == [], old.posts


def test_a_run_for_one_pr_counts_its_pending_posts(monkeypatch, capsys):
    fake = FakeGitHub({5: pr(5)}, [review("pass")])
    monkeypatch.setattr(gates, "_gh", fake)
    gates.run("o/r", 5, do_post=True)
    assert f"posted {len(fake.posts)} statuses (2 of them pending first)" in capsys.readouterr().out


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main",
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def origin_with_a_pr(tmp_path):
    """A local 'origin' with three commits on main and a pull-request head ref, as GitHub serves them."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q")
    for i in range(3):
        (origin / "f.txt").write_text(str(i))
        _git(origin, "add", "f.txt")
        _git(origin, "commit", "-q", "-m", f"c{i}")
    _git(origin, "update-ref", "refs/pull/7/head", "HEAD")
    return origin


def test_the_release_fetch_keeps_a_full_clone_full(origin_with_a_pr, tmp_path, monkeypatch):
    """Running the gates locally on a release PR must not make the clone shallow: every worktree shares its history,
    and the site's --release build refuses a shallow repository (it did so twice on 2026-11-01)."""
    full = tmp_path / "full"
    _git(tmp_path, "clone", "-q", f"file://{origin_with_a_pr}", str(full))
    monkeypatch.chdir(full)
    assert "--depth=1" not in gates.release_fetch(7)
    subprocess.run(gates.release_fetch(7), check=True, capture_output=True)
    assert _git(full, "rev-parse", "--is-shallow-repository") == "false"
    assert _git(full, "rev-list", "--count", "origin/main") == "3"
    assert _git(full, "rev-parse", "origin/pr-head") == _git(origin_with_a_pr, "rev-parse", "refs/pull/7/head")


def test_the_release_fetch_stays_shallow_in_a_shallow_checkout(origin_with_a_pr, tmp_path, monkeypatch):
    """CI checks out with fetch-depth: 1; there the fetch stays one commit deep."""
    ci = tmp_path / "ci"
    _git(tmp_path, "clone", "-q", "--depth=1", f"file://{origin_with_a_pr}", str(ci))
    for i in (3, 4):  # main and the PR move on after the checkout, so the fetch has history it could pull
        (origin_with_a_pr / "f.txt").write_text(str(i))
        _git(origin_with_a_pr, "commit", "-qam", f"c{i}")
    _git(origin_with_a_pr, "update-ref", "refs/pull/7/head", "HEAD")
    monkeypatch.chdir(ci)
    assert "--depth=1" in gates.release_fetch(7)
    subprocess.run(gates.release_fetch(7), check=True, capture_output=True)
    assert _git(ci, "rev-parse", "--is-shallow-repository") == "true"
    assert _git(ci, "rev-list", "--count", "origin/main") == "1"
    assert _git(ci, "rev-list", "--count", "origin/pr-head") == "1"
    assert _git(ci, "rev-parse", "origin/pr-head") == _git(origin_with_a_pr, "rev-parse", "refs/pull/7/head")


@pytest.mark.parametrize("rewrite_history", [False, True], ids=["new-release", "rewritten-history"])
def test_main_release_gate_uses_one_fetched_baseline_and_rejects_historical_edits(
        origin_with_a_pr, tmp_path, monkeypatch, rewrite_history):
    origin = origin_with_a_pr
    (origin / "CHANGELOG.md").write_text(LOG)
    (origin / "pyproject.toml").write_text(PY.format("0.4.2"))
    _git(origin, "add", "CHANGELOG.md", "pyproject.toml")
    _git(origin, "commit", "-qm", "Released baseline")
    baseline = _git(origin, "rev-parse", "HEAD")
    _git(origin, "checkout", "-qb", "dev")
    new_log = LOG.replace("## Unreleased", "## Unreleased\n\n## v0.4.3 (2026-11-01)\n\n- New fix.")
    if rewrite_history:
        new_log = new_log.replace("Shipped fix.", "This never shipped.")
    (origin / "CHANGELOG.md").write_text(new_log)
    (origin / "pyproject.toml").write_text(PY.format("0.4.3"))
    _git(origin, "commit", "-qam", "Release candidate")
    head = _git(origin, "rev-parse", "HEAD")
    _git(origin, "update-ref", "refs/pull/7/head", head)
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", "-q", f"file://{origin}", str(checkout))
    monkeypatch.chdir(checkout)
    fake = FakeGitHub({7: pr(7, base="main", ref="dev", sha=head)}, [review("pass", sha=head)])
    monkeypatch.setattr(gates, "_gh", fake)
    reads, real_show = [], gates._git_show
    def record_show(rev_path):
        reads.append(rev_path)
        return real_show(rev_path)
    monkeypatch.setattr(gates, "_git_show", record_show)
    _, results = gates.evaluate("o/r", 7)
    assert results["review"][0] and results["release"][0]
    assert results["branch-flow"][0] is not rewrite_history
    assert f"{baseline}:CHANGELOG.md" in reads and f"{baseline}:pyproject.toml" in reads
    assert not any(path.startswith("origin/main:") for path in reads)
