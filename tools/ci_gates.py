#!/usr/bin/env python3
"""Merge gates for cad-agent pull requests (stdlib only), run by .github/workflows/gates.yml.

    python tools/ci_gates.py all --repo Valpatel/cad-agent --pr 116           # print every gate's result
    python tools/ci_gates.py all --repo Valpatel/cad-agent --pr 116 --post    # and set them as commit statuses
    python tools/ci_gates.py version                                            # the pyproject.toml version

Gates, for PRs into dev and main (CONTRIBUTING.md "Gates"):

- branch-flow: main takes this repo's dev only; dev takes feat/ fix/ ci/ docs/ research/ test/ refactor/ release/
  vendor-update/ dependabot/ branches of this repo, or a fork's PR (the outside-contribution checks, #111, apply).
- review: the latest verdict from a reviewer with write access must be pass. The verdict is the last line of a review:
  ``<!-- cad-review verdict=pass sha=<40-character head commit> -->`` (or ``verdict=block``). For main, and for fork PRs,
  the pass must be on the head commit; for this repo's own branches into dev, a pass on an earlier commit stands
  (anyone who can push here can already merge).
- release (main only): the pyproject.toml version is above main's and CHANGELOG.md has ``## vX.Y.Z (YYYY-MM-DD)``.

Why statuses and not job results: the workflow runs on ``pull_request_target``, so the base branch's copy of this file
decides, never the PR's (a PR that edits the gates cannot pass them), and it reads the PR only as data. Each result is
posted as a commit status on the PR's head commit with the base in its name (``cad-gates/main/review``), so a PR into
one branch cannot supply another branch's required check. A fork's own workflows get a read-only token and cannot post
statuses. Anyone with write access can, which is why write access is the trust boundary throughout.
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
    if (base == "main" or not same_repo) and sha != head_sha:
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


def evaluate(repo: str, number: int) -> Tuple[dict, Dict[str, Result]]:
    pr = json.loads(_gh("api", f"repos/{repo}/pulls/{number}"))
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
        subprocess.run(["git", "fetch", "-q", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main",
                        f"+refs/pull/{number}/head:refs/remotes/origin/pr-head"], check=True)
        try:
            log = _git_show(f"{head['sha']}:CHANGELOG.md")
        except subprocess.CalledProcessError:
            log = ""
        results["release"] = release_gate(_git_show(f"{head['sha']}:pyproject.toml"),
                                          _git_show("origin/main:pyproject.toml"), log)
    return pr, results


def post(repo: str, pr: dict, results: Dict[str, Result]) -> None:
    base, sha = pr["base"]["ref"], pr["head"]["sha"]
    run = os.environ.get("GITHUB_SERVER_URL", "https://github.com") + f"/{repo}/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "")
    for gate, (ok, msg) in results.items():
        _gh("api", "-X", "POST", f"repos/{repo}/statuses/{sha}", "-f", f"state={'success' if ok else 'failure'}",
            "-f", f"context=cad-gates/{base}/{gate}", "-f", f"description={msg[:139]}", "-f", f"target_url={run}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("all", help="evaluate every gate for a PR")
    a.add_argument("--repo", required=True)
    a.add_argument("--pr", type=int, required=True)
    a.add_argument("--post", action="store_true", help="set the results as commit statuses on the PR's head")
    sub.add_parser("version", help="print the pyproject.toml version")
    args = ap.parse_args(argv)
    if args.cmd == "version":
        with open("pyproject.toml", encoding="utf-8") as f:
            print(".".join(map(str, parse_version(f.read()))))
        return 0
    pr, results = evaluate(args.repo, args.pr)
    if pr["base"]["ref"] not in GATED:
        print(f"PR into {pr['base']['ref']!r}: not gated")
        return 0
    for gate, (ok, msg) in results.items():
        print(f"{'PASS' if ok else 'FAIL'} cad-gates/{pr['base']['ref']}/{gate}: {msg}")
    if args.post:
        post(args.repo, pr, results)
    return 0 if all(ok for ok, _ in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
