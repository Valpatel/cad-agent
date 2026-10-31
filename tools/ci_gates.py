#!/usr/bin/env python3
"""Merge gates for cad-agent pull requests (stdlib only), run by .github/workflows/gates.yml.

    python tools/ci_gates.py all --repo Valpatel/cad-agent --pr 116           # every gate's result, read live; exit 1 if any fails
    python tools/ci_gates.py all --repo Valpatel/cad-agent --pr 116 --post    # and set them as commit statuses
    python tools/ci_gates.py sweep --repo Valpatel/cad-agent --post           # every open PR into dev or main (scheduled)
    python tools/ci_gates.py version                                            # the pyproject.toml version

Gates, for PRs into dev and main (CONTRIBUTING.md "Gates"):

- branch-flow: main takes this repo's dev only; dev takes feat/ fix/ ci/ docs/ research/ test/ refactor/ release/
  vendor-update/ dependabot/ branches of this repo, or a fork's PR (the outside-contribution checks, #111, apply).
- review: the latest verdict from a reviewer with write access must be pass, on the PR's head commit (a push after the
  pass needs a new verdict, so everything that reaches dev or main was reviewed as it is). The verdict is the last line
  of a review: ``<!-- cad-review verdict=pass sha=<40-character head commit> -->`` (or ``verdict=block``).
- release (main only): the pyproject.toml version is above main's and CHANGELOG.md has ``## vX.Y.Z (YYYY-MM-DD)``.

Why statuses and not job results: the workflow runs on ``pull_request_target``, so the default branch's (dev's) copy of
this file decides, never the PR's (a PR that edits the gates cannot pass them), and it reads the PR only as data. PRs
into main come from dev, so dev's gates judge them too. Each result is
posted as a commit status on the PR's head commit with the base in its name (``cad-gates/main/review``), so a PR into
one branch cannot supply another branch's required check. A fork's own workflows get a read-only token and cannot post
statuses. Anyone with write access can, which is why write access is the trust boundary throughout.

Reviews do not trigger workflows that can post statuses, so a verdict posted after the last run is read by the next
one: the reviewer's re-run (``workflow_dispatch``), the scheduled sweep (every 15 minutes), or a push. Just before
merging, run ``all`` without ``--post``: it reads the reviews live and must exit 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from typing import Callable, Dict, Iterable, List, Optional, Tuple

FEATURE_BRANCH = re.compile(
    r"^(feat|fix|ci|docs|research|test|refactor|release|vendor-update|dependabot)/[A-Za-z0-9._/-]+$")
MARKER = re.compile(r"^<!--\s*cad-review\s+verdict=(pass|block)\s+sha=([0-9a-f]{40})\s*-->$")
WRITERS = {"admin", "maintain", "write"}
GATED = ("dev", "main")

Result = Tuple[bool, str]


def branch_flow(base: str, head_ref: str, same_repo: bool) -> Result:
    if base == "main":
        if same_repo and head_ref == "dev":
            return True, "release PR: dev -> main"
        return False, f"PRs into main come from this repo's dev branch only, not {'a fork' if not same_repo else repr(head_ref)}"
    if base == "dev":
        if not same_repo:
            return True, "fork PR into dev: the outside-contribution checks apply"
        if FEATURE_BRANCH.match(head_ref):
            return True, f"{head_ref} -> dev"
        return False, (f"branch {head_ref!r} cannot merge into dev: branch off dev as feat/ fix/ ci/ docs/ research/ "
                       "test/ refactor/ release/ (git branch -m)")
    return True, f"PR into {base!r}: no branch rule"


def marker(body: Optional[str]) -> Optional[Tuple[str, str]]:
    """(verdict, sha) when the review's last non-empty line is a verdict marker, else None (a marker quoted earlier in
    the text, an example in a code block, does not count)."""
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    m = MARKER.match(lines[-1]) if lines else None
    return (m.group(1), m.group(2)) if m else None


def verdicts(reviews: Iterable[dict], can_write: Callable[[str], bool]) -> List[Tuple[int, str, str, str]]:
    """(review id, verdict, sha, reviewer) for every live review with a marker by someone with write access, in the
    order GitHub created them (ids increase; timestamps can tie)."""
    out = []
    for r in reviews:
        if r.get("state") in ("DISMISSED", "PENDING"):
            continue
        found = marker(r.get("body"))
        login = (r.get("user") or {}).get("login") or ""
        if found and login and can_write(login):
            out.append((int(r["id"]), found[0], found[1], login))
    return sorted(out)


def review_gate(reviews: Iterable[dict], base: str, head_sha: str, same_repo: bool,
                can_write: Callable[[str], bool]) -> Result:
    marked = verdicts(reviews, can_write)
    if not marked:
        return False, "no review verdict yet: the reviewer's summary review ends with <!-- cad-review verdict=... sha=... -->"
    _, verdict, sha, who = marked[-1]
    if verdict != "pass":
        return False, f"latest verdict is block ({who}, {sha[:7]}): fix, then ask for a re-review"
    if sha != head_sha:
        return False, f"needs a pass on the head commit {head_sha[:7]}; the latest pass is on {sha[:7]}"
    return True, f"verdict pass by {who} on {sha[:7]}"


def parse_version(pyproject: str) -> Tuple[int, ...]:
    """The [project] table's version (not the first version line anywhere in the file)."""
    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", pyproject, re.M | re.S)
    m = section and re.search(r'^version\s*=\s*"([0-9]+(?:\.[0-9]+)*)"\s*$', section.group(1), re.M)
    if not m:
        raise ValueError('no version = "X.Y.Z" in the [project] table of pyproject.toml')
    return tuple(int(p) for p in m.group(1).split("."))


def release_gate(head_pyproject: str, main_pyproject: str, changelog: str) -> Result:
    head, main = parse_version(head_pyproject), parse_version(main_pyproject)
    v = ".".join(map(str, head))
    if head <= main:
        return False, f"version {v} is not above main's {'.'.join(map(str, main))}: bump pyproject.toml"
    m = re.search(rf"^## v{re.escape(v)} \((\d{{4}}-\d{{2}}-\d{{2}})\)\s*$", changelog, re.M)
    if not m:
        return False, f"CHANGELOG.md has no dated entry '## v{v} (YYYY-MM-DD)'"
    try:
        dt.date.fromisoformat(m.group(1))
    except ValueError:
        return False, f"CHANGELOG.md entry for v{v} has an impossible date {m.group(1)}"
    return True, f"release v{v} (main is {'.'.join(map(str, main))})"


# ------------------------------------------------------------------------------------------------- GitHub plumbing
def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _git_show(rev_path: str) -> str:
    return subprocess.run(["git", "show", rev_path], check=True, capture_output=True, text=True).stdout


def contexts(base: str) -> List[str]:
    """The status names a PR into ``base`` gets."""
    return [f"cad-gates/{base}/{g}" for g in ("branch-flow", "review") + (("release",) if base == "main" else ())]


def fetch_pr(repo: str, number: int) -> dict:
    return json.loads(_gh("api", f"repos/{repo}/pulls/{number}"))


def evaluate(repo: str, number: int, pr: Optional[dict] = None) -> Tuple[dict, Dict[str, Result]]:
    pr = pr or fetch_pr(repo, number)
    base, head = pr["base"]["ref"], pr["head"]
    same = (head.get("repo") or {}).get("full_name") == repo
    results: Dict[str, Result] = {"branch-flow": branch_flow(base, head["ref"], same)}
    reviews = [json.loads(line) for line in _gh(
        "api", "--paginate", f"repos/{repo}/pulls/{number}/reviews",
        "--jq", ".[] | {id, state, body, user: {login: .user.login}}").splitlines() if line.strip()]
    cache: Dict[str, bool] = {}

    def can_write(login: str) -> bool:
        if login not in cache:
            try:
                cache[login] = json.loads(_gh("api", f"repos/{repo}/collaborators/{login}/permission"))["permission"] in WRITERS
            except subprocess.CalledProcessError:
                cache[login] = False
        return cache[login]

    results["review"] = review_gate(reviews, base, head["sha"], same, can_write)
    if base == "main":
        # The PR's files are read as data from its head commit (fetched, never checked out or run).
        # gh's credential helper, so the fetch also works for a private repo (the checkout keeps no credentials).
        subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
                        "fetch", "-q", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main",
                        f"+refs/pull/{number}/head:refs/remotes/origin/pr-head"], check=True)
        try:
            log = _git_show(f"{head['sha']}:CHANGELOG.md")
        except subprocess.CalledProcessError:
            log = ""
        results["release"] = release_gate(_git_show(f"{head['sha']}:pyproject.toml"),
                                          _git_show("origin/main:pyproject.toml"), log)
    return pr, results


def _status(repo: str, sha: str, context: str, state: str, msg: str) -> None:
    run = os.environ.get("GITHUB_SERVER_URL", "https://github.com") + f"/{repo}/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "")
    _gh("api", "-X", "POST", f"repos/{repo}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={context}",
        "-f", f"description={msg[:139]}", "-f", f"target_url={run}")


def post(repo: str, pr: dict, results: Dict[str, Result]) -> None:
    base, sha = pr["base"]["ref"], pr["head"]["sha"]
    for gate, (ok, msg) in results.items():
        _status(repo, sha, f"cad-gates/{base}/{gate}", "success" if ok else "failure", msg)


def run(repo: str, number: int, do_post: bool) -> int:
    """Evaluate one PR and print (and with ``do_post`` set) its gates. With ``do_post`` the statuses go to pending first,
    so a run that crashes leaves the PR blocked (fail closed) instead of keeping an older green; gate failures are
    statuses, not errors. Exit: 0 posted (or all passed), 1 a gate failed (without --post), and an error raises."""
    pr = fetch_pr(repo, number)
    base = pr["base"]["ref"]
    if base not in GATED:
        print(f"#{number} into {base!r}: not gated")
        return 0
    if do_post:
        for context in contexts(base):
            _status(repo, pr["head"]["sha"], context, "pending", "evaluating")
    pr, results = evaluate(repo, number, pr)
    for gate, (ok, msg) in results.items():
        print(f"{'PASS' if ok else 'FAIL'} #{number} cad-gates/{base}/{gate}: {msg}")
    if do_post:
        post(repo, pr, results)
        return 0
    return 0 if all(ok for ok, _ in results.values()) else 1


def sweep(repo: str, do_post: bool) -> int:
    """Every open PR into dev or main, so a verdict posted since the last run is read within one schedule."""
    numbers = [int(n) for n in _gh("api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100",
                                   "--jq", f'.[] | select(.base.ref == "dev" or .base.ref == "main") | .number').split()]
    errors = 0
    for n in numbers:
        try:
            run(repo, n, do_post)
        except (subprocess.CalledProcessError, KeyError, ValueError) as e:
            errors += 1
            print(f"ERROR #{n}: {e}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("all", help="evaluate every gate for a PR")
    a.add_argument("--repo", required=True)
    a.add_argument("--pr", type=int, required=True)
    a.add_argument("--post", action="store_true", help="set the results as commit statuses on the PR's head")
    s = sub.add_parser("sweep", help="evaluate every open PR into dev or main")
    s.add_argument("--repo", required=True)
    s.add_argument("--post", action="store_true")
    sub.add_parser("version", help="print the pyproject.toml version")
    args = ap.parse_args(argv)
    if args.cmd == "version":
        with open("pyproject.toml", encoding="utf-8") as f:
            print(".".join(map(str, parse_version(f.read()))))
        return 0
    if args.cmd == "sweep":
        return sweep(args.repo, args.post)
    return run(args.repo, args.pr, args.post)


if __name__ == "__main__":
    sys.exit(main())
