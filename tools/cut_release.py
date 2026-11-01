#!/usr/bin/env python3
"""Cut a cad-agent release: date the CHANGELOG's Unreleased entry and bump the version in pyproject.toml.

Shipping to `main` is part of the development loop (CONTRIBUTING.md#releases): when `dev` has merged, user-visible
work, cut a release. This script makes the file edits of the release branch and checks them against the same release
gate CI runs (`release_gate` in tools/ci_gates.py). It prints the git and gh steps instead of running them.

    python3 tools/cut_release.py --minor                 # 0.5.0 -> 0.6.0: projects must change something
    python3 tools/cut_release.py --patch                 # 0.5.0 -> 0.5.1: fixes, docs and the site only
    python3 tools/cut_release.py --version 1.0.0 --date 2026-11-01 --dry-run

New work goes in the CHANGELOG under `## Unreleased` (an older `## vX.Y.Z (unreleased)` heading is accepted too).
The script renames that heading to `## vX.Y.Z (YYYY-MM-DD)` and opens a new, empty `## Unreleased` above it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import pathlib
import re
import subprocess
import sys
from typing import Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNRELEASED = re.compile(r"^## (?:Unreleased|v[0-9]+(?:\.[0-9]+)* \(unreleased\))[ \t]*$", re.M)
PROJECT_VERSION = re.compile(r'^(version\s*=\s*")([0-9]+(?:\.[0-9]+)*)("\s*)$', re.M)


def _gates():
    """tools/ci_gates.py, the copy next to this file, for its parse_version and release_gate."""
    spec = importlib.util.spec_from_file_location("ci_gates", pathlib.Path(__file__).with_name("ci_gates.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def next_version(current: Tuple[int, ...], bump: str) -> str:
    """The next version after `current`: `minor` gives X.(Y+1).0, `patch` gives X.Y.(Z+1)."""
    major, minor, patch = (tuple(current) + (0, 0, 0))[:3]
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump {bump!r}: use minor or patch")


def bump_pyproject(pyproject: str, version: str) -> str:
    """pyproject.toml with the [project] table's version set to `version`; every other table is left alone."""
    table = re.search(r"^\[project\][ \t]*\n(.*?)(?=^\[|\Z)", pyproject, re.M | re.S)
    if not table:
        raise ValueError("pyproject.toml has no [project] table")
    body, n = PROJECT_VERSION.subn(lambda m: f"{m.group(1)}{version}{m.group(3)}", table.group(1), count=1)
    if n != 1:
        raise ValueError('no version = "X.Y.Z" in the [project] table of pyproject.toml')
    return pyproject[:table.start(1)] + body + pyproject[table.end(1):]


def date_changelog(changelog: str, version: str, date: str) -> str:
    """The CHANGELOG with its one Unreleased entry renamed to `## v<version> (<date>)` and a new empty Unreleased."""
    found = list(UNRELEASED.finditer(changelog))
    if len(found) != 1:
        raise ValueError(f"CHANGELOG.md needs exactly one '## Unreleased' heading, found {len(found)}")
    head = found[0]
    following = re.compile(r"^## ", re.M).search(changelog, head.end())
    body = changelog[head.end():following.start() if following else len(changelog)]
    if not body.strip():
        raise ValueError("the Unreleased entry is empty: nothing to release")
    rest = changelog[:head.start()] + changelog[head.end():]  # the Unreleased heading may itself name the version
    if re.search(rf"^## v{re.escape(version)} \(", rest, re.M):
        raise ValueError(f"CHANGELOG.md already has an entry for v{version}")
    return changelog[:head.start()] + f"## Unreleased\n\n## v{version} ({date})" + changelog[head.end():]


def cut(pyproject: str, changelog: str, *, bump: Optional[str] = None, version: Optional[str] = None,
        date: Optional[str] = None) -> Tuple[str, str, str]:
    """(new pyproject, new changelog, version), checked against CI's release gate; raises ValueError otherwise."""
    gates = _gates()
    current = gates.parse_version(pyproject)
    if (bump is None) == (version is None):
        raise ValueError("give exactly one of --minor, --patch or --version")
    version = version or next_version(current, bump)
    date = date or dt.date.today().isoformat()
    dt.date.fromisoformat(date)  # an impossible date fails here, before the gate
    new_pyproject = bump_pyproject(pyproject, version)
    new_changelog = date_changelog(changelog, version, date)
    ok, why = gates.release_gate(new_pyproject, pyproject, new_changelog)
    if not ok:
        raise ValueError(f"the release gate would fail: {why}")
    return new_pyproject, new_changelog, version


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--minor", dest="bump", action="store_const", const="minor")
    which.add_argument("--patch", dest="bump", action="store_const", const="patch")
    which.add_argument("--version", help="an explicit X.Y.Z")
    ap.add_argument("--date", help="the release date, YYYY-MM-DD (default today)")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT, help="the repository root (default: this checkout)")
    ap.add_argument("--dry-run", action="store_true", help="check and print, write nothing")
    args = ap.parse_args(argv)
    py_path, cl_path = args.root / "pyproject.toml", args.root / "CHANGELOG.md"
    try:
        new_py, new_cl, version = cut(py_path.read_text(encoding="utf-8"), cl_path.read_text(encoding="utf-8"),
                                      bump=args.bump, version=args.version, date=args.date)
    except ValueError as exc:
        print(f"cut_release: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"v{version}: pyproject.toml and CHANGELOG.md would change (dry run, nothing written)")
        return 0
    py_path.write_text(new_py, encoding="utf-8")
    cl_path.write_text(new_cl, encoding="utf-8")
    branch = subprocess.run(["git", "-C", str(args.root), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()
    print(f"v{version}: pyproject.toml and CHANGELOG.md updated on {branch or 'a detached HEAD'}. Next:\n"
          f"  git commit -am 'Release v{version}' && git push -u origin HEAD\n"
          f"  gh pr create --base dev --title 'Release v{version}: version and CHANGELOG'   # review, merge\n"
          f"  gh pr create --base main --head dev --title 'Release v{version}'              # review, merge (merge commit)\n"
          f"release.yml then tags v{version}, publishes the GitHub release and deploys the site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
