#!/usr/bin/env python3
"""Merge gates for cad-agent pull requests, run by .github/workflows/gates.yml (stdlib only).

    python tools/ci_gates.py branch-flow     # base main <- dev only; base dev <- feat/ fix/ ci/ docs/ ... branches
    python tools/ci_gates.py review-gate     # an independent review's latest verdict is pass (on the head for main)
    python tools/ci_gates.py release-gate    # version above main's, dated CHANGELOG entry

Each reads the GitHub event (GITHUB_EVENT_PATH) and prints one line saying why it passed or failed; exit 1 fails the
check. The rules are documented in CONTRIBUTING.md ("Gates").

The review verdict is a marker at the end of a reviewer's summary review:

    <!-- cad-review verdict=pass sha=<head commit> -->      or      verdict=block

Only reviews by the repository's owner, members or collaborators count (anyone can post a review on a public PR). Every
agent here works through the owner's account, so GitHub cannot tell the author from the reviewer; the marker is the
reviewer agent's declaration, and the skill that writes it (skills/cad-pr-review) says when it may say pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple

FEATURE_BRANCH = re.compile(r"^(feat|fix|ci|docs|research|test|refactor|release|vendor-update)/[A-Za-z0-9._/-]+$")
MARKER = re.compile(r"<!--\s*cad-review\s+verdict=(pass|block)\s+sha=([0-9a-f]{7,40})\s*-->")
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
VERSION = re.compile(r'^version\s*=\s*"([0-9]+(?:\.[0-9]+)*)"', re.M)

Result = Tuple[bool, str]


def branch_flow(base: str, head_ref: str, same_repo: bool) -> Result:
    """main takes releases from dev only; dev takes feature branches of this repo (or any fork branch, which the
    fork checks in #111 cover); anything else (a PR into a feature branch) is free."""
    if base == "main":
        if same_repo and head_ref == "dev":
            return True, "release PR: dev -> main"
        return False, f"PRs into main come from this repo's dev branch only, not {'a fork' if not same_repo else head_ref!r}"
    if base == "dev":
        if head_ref in ("main", "dev"):
            return False, f"{head_ref!r} cannot merge into dev; branch off dev as feat/<topic>"
        if not same_repo:
            return True, "fork PR into dev (outside-contribution checks apply)"
        if FEATURE_BRANCH.match(head_ref):
            return True, f"{head_ref} -> dev"
        return False, (f"branch {head_ref!r} does not match feat/ fix/ ci/ docs/ research/ test/ refactor/ "
                       "release/ vendor-update/ (rename it: git branch -m)")
    return True, f"PR into {base!r}: no branch rule"


def verdicts(reviews: Iterable[dict]) -> List[Tuple[str, str, str]]:
    """(submitted_at, verdict, sha) for every marked review by a trusted account, oldest first."""
    out = []
    for r in reviews:
        if r.get("author_association") not in TRUSTED or not r.get("submitted_at"):
            continue
        found = MARKER.findall(r.get("body") or "")
        if found:
            verdict, sha = found[-1]
            out.append((r["submitted_at"], verdict, sha))
    return sorted(out)


def review_gate(reviews: Iterable[dict], base: str, head_sha: str) -> Result:
    marked = verdicts(reviews)
    if not marked:
        return False, ("no review verdict yet: an independent reviewer (cad-pr-reviewer) ends its summary review with "
                       "<!-- cad-review verdict=pass|block sha=<head> -->")
    when, verdict, sha = marked[-1]
    if verdict != "pass":
        return False, f"latest review verdict is {verdict} ({when}, {sha[:7]}): fix, then ask for a re-review"
    if base == "main" and not head_sha.startswith(sha):
        return False, f"release PRs need a pass on the head commit {head_sha[:7]}; the latest pass is on {sha[:7]}"
    return True, f"review verdict pass ({when}, {sha[:7]})"


def parse_version(pyproject: str) -> Tuple[int, ...]:
    m = VERSION.search(pyproject)
    if not m:
        raise ValueError("no version = \"X.Y.Z\" line in pyproject.toml")
    return tuple(int(p) for p in m.group(1).split("."))


def release_gate(head_pyproject: str, main_pyproject: str, changelog: str) -> Result:
    head, main = parse_version(head_pyproject), parse_version(main_pyproject)
    v = ".".join(map(str, head))
    if head <= main:
        return False, f"version {v} is not above main's {'.'.join(map(str, main))}: bump pyproject.toml"
    if not re.search(rf"^## v{re.escape(v)} \(\d{{4}}-\d{{2}}-\d{{2}}\)\s*$", changelog, re.M):
        return False, f"CHANGELOG.md has no dated entry '## v{v} (YYYY-MM-DD)'"
    return True, f"release v{v} (main is {'.'.join(map(str, main))})"


def _event() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise SystemExit("GITHUB_EVENT_PATH is not set: this runs in GitHub Actions (or set it to a saved event)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _reviews(repo: str, number: int) -> List[dict]:
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/pulls/{number}/reviews",
                          "--jq", ".[] | {author_association, body, submitted_at, commit_id}"],
                         check=True, capture_output=True, text=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _git_show(ref_path: str) -> str:
    return subprocess.run(["git", "show", ref_path], check=True, capture_output=True, text=True).stdout


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("gate", choices=["branch-flow", "review-gate", "release-gate"])
    args = ap.parse_args(argv)
    pr = _event()["pull_request"]
    base, head = pr["base"], pr["head"]
    if args.gate == "branch-flow":
        same = (head.get("repo") or {}).get("full_name") == base["repo"]["full_name"]
        ok, msg = branch_flow(base["ref"], head["ref"], same)
    elif args.gate == "review-gate":
        ok, msg = review_gate(_reviews(base["repo"]["full_name"], pr["number"]), base["ref"], head["sha"])
    else:
        with open("pyproject.toml", encoding="utf-8") as f:
            head_py = f.read()
        changelog = open("CHANGELOG.md", encoding="utf-8").read() if os.path.exists("CHANGELOG.md") else ""
        ok, msg = release_gate(head_py, _git_show("origin/main:pyproject.toml"), changelog)
    print(("PASS " if ok else "FAIL ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
