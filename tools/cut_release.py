#!/usr/bin/env python3
"""Cut a cad-agent release: date the CHANGELOG's Unreleased entry and bump the version in pyproject.toml.

Shipping to `main` is part of the development loop (CONTRIBUTING.md#releases): when `dev` has merged, user-visible
work, cut a release. This script makes the file edits of the release branch and checks them against the same release
gate CI runs (`release_gate` in tools/ci_gates.py). It prints the git and gh steps instead of running them.

    python3 tools/cut_release.py --minor                 # 0.5.0 -> 0.6.0: projects must change something
    python3 tools/cut_release.py --patch                 # 0.5.0 -> 0.5.1: fixes, docs and the site only
    python3 tools/cut_release.py --version 1.0.0 --date 2026-11-01 --dry-run

Each PR adds its CHANGELOG lines as a fragment, `changelog.d/<issue>-<slug>.md`: bullets under `**New**`, `**Changed**`,
`**Fixed**` or `**Projects must change**`. Fragments never conflict, where PRs editing CHANGELOG.md side by side do.
The script folds every fragment into the `## Unreleased` entry (an older `## vX.Y.Z (unreleased)` heading is accepted
too), each bullet under its section, deletes the fragments, renames the heading to `## vX.Y.Z (YYYY-MM-DD)` and opens
a new, empty `## Unreleased` above it. Lines written straight under `## Unreleased` are kept as they are.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import pathlib
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNRELEASED = re.compile(r"^## (?:Unreleased|v(?P<named>[0-9]+(?:\.[0-9]+)*) \(unreleased\))[ \t]*$", re.M)
VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
# Lines that are not a change: sub-headings such as "**New**" or "### Fixed", and HTML comments.
_NOT_A_CHANGE = re.compile(r"<!--.*?-->|^[ \t]*(?:#{3,6}[^\n]*|\*\*[^*\n]+\*\*:?)[ \t]*$", re.M | re.S)
PROJECT_VERSION = re.compile(r'^(version\s*=\s*")([0-9]+(?:\.[0-9]+)*)("\s*)$', re.M)


FRAGMENTS = "changelog.d"
SECTIONS = ("New", "Changed", "Fixed", "Projects must change")
_SECTION = re.compile(r"^\*\*(?P<name>[^*\n]+?):?\*\*:?[ \t]*$", re.M)
# A section opened by a paragraph, "**Projects must change:** write STEP files ...": the form the CHANGELOG used up to
# v0.5.0. Only a known section name counts, so a bold lead-in such as "**Note:** ..." stays part of its section.
_SECTION_LEAD = re.compile(r"^\*\*(?P<name>[^*\n]+?):?\*\*:?[ \t]+\S")


def _opens(line: str) -> Optional[str]:
    """The section a line of the Unreleased entry opens: a heading line, or a known section's lead-in paragraph."""
    m = _SECTION.match(line)
    if m:
        return m.group("name").strip()
    m = _SECTION_LEAD.match(line)
    return m.group("name").strip() if m and m.group("name").strip() in SECTIONS else None


def read_fragment(name: str, text: str) -> Dict[str, List[str]]:
    """{section: its lines} of one fragment; every line sits under a known section heading, and each section has a
    bullet."""
    found: Dict[str, List[str]] = {}
    section = None
    for line in text.replace("\r\n", "\n").split("\n"):
        head = _SECTION.match(line)
        if head:
            section = head.group("name").strip()
            if section not in SECTIONS:
                raise ValueError(f"{name}: unknown section **{section}** (use {', '.join(SECTIONS)})")
            found.setdefault(section, [])
        elif line.lstrip().startswith("#"):
            raise ValueError(f"{name}: a Markdown heading ({line.strip()[:40]!r}) would split the CHANGELOG entry; "
                             "use **New**, **Changed**, **Fixed** or **Projects must change**")
        elif line.strip():
            if section is None:
                raise ValueError(f"{name}: text before the first section heading (**New**, **Fixed**, ...)")
            found[section].append(line.rstrip())
    if not found:
        raise ValueError(f"{name}: no section heading and no bullets")
    for section, lines in found.items():
        if not any(line.lstrip().startswith("- ") for line in lines):
            raise ValueError(f"{name}: **{section}** has no '- ' bullet")
    return found


def fold_fragments(changelog: str, fragments: Sequence[Tuple[str, str]]) -> str:
    """The CHANGELOG with each fragment's bullets added to its section of the one Unreleased entry, in the fragments'
    order. A section the entry lacks is added in the order of SECTIONS."""
    if not fragments:
        return changelog
    found = list(UNRELEASED.finditer(changelog))
    if len(found) != 1:
        raise ValueError(f"CHANGELOG.md needs exactly one '## Unreleased' heading, found {len(found)}")
    head = found[0]
    following = re.compile(r"^## ", re.M).search(changelog, head.end())
    end = following.start() if following else len(changelog)
    body = changelog[head.end():end].strip("\n")
    adds: Dict[str, List[str]] = {}
    for name, text in fragments:
        for section, lines in read_fragment(name, text).items():
            adds.setdefault(section, []).extend(lines)
    lines = body.split("\n") if body else []
    for section in SECTIONS:
        if section not in adds:
            continue
        heads = [i for i, line in enumerate(lines) if _opens(line) == section]
        if heads:
            start = heads[0] + 1
            stop = next((i for i in range(start, len(lines)) if _opens(lines[i])), len(lines))
            while stop > start and not lines[stop - 1].strip():
                stop -= 1
            # after a paragraph (a lead-in, or prose under the heading), a blank line starts the list
            prev = lines[stop - 1]
            in_list = prev.lstrip().startswith("- ") or prev.startswith("  ") or bool(_SECTION.match(prev))
            lines[stop:stop] = ([] if in_list else [""]) + adds[section]
        else:
            later = [i for i, line in enumerate(lines) if _opens(line) in SECTIONS[SECTIONS.index(section) + 1:]]
            at = later[0] if later else len(lines)
            block = [f"**{section}**"] + adds[section]
            block = ([""] if at and lines[at - 1].strip() else []) + block + ([""] if at < len(lines) else [])
            lines[at:at] = block
    return changelog[:head.end()] + "\n\n" + "\n".join(lines).strip("\n") + "\n\n" + changelog[end:].lstrip("\n")


def fragment_files(root: pathlib.Path) -> List[pathlib.Path]:
    """The fragments in root/changelog.d, sorted by name; its README is not one."""
    folder = root / FRAGMENTS
    return sorted(p for p in folder.glob("*.md") if p.name.lower() != "readme.md") if folder.is_dir() else []


def _gates():
    """tools/ci_gates.py, the copy next to this file, for its parse_version and release_gate."""
    spec = importlib.util.spec_from_file_location("ci_gates", pathlib.Path(__file__).with_name("ci_gates.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_today() -> str:
    """Today's date in UTC, as GitHub dates its tags and releases (a local evening is already tomorrow in UTC)."""
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


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
    if not _NOT_A_CHANGE.sub("", body).strip():
        raise ValueError("the Unreleased entry is empty: nothing to release")
    if head.group("named") and head.group("named") != version:
        raise ValueError(f"the CHANGELOG's heading names v{head.group('named')}, not v{version}: "
                         f"use --version {head.group('named')}, or rename the heading to '## Unreleased'")
    rest = changelog[:head.start()] + changelog[head.end():]  # the Unreleased heading may itself name the version
    if re.search(rf"^## v{re.escape(version)} \(", rest, re.M):
        raise ValueError(f"CHANGELOG.md already has an entry for v{version}")
    return changelog[:head.start()] + f"## Unreleased\n\n## v{version} ({date})" + changelog[head.end():]


def cut(pyproject: str, changelog: str, *, bump: Optional[str] = None, version: Optional[str] = None,
        date: Optional[str] = None, fragments: Sequence[Tuple[str, str]] = ()) -> Tuple[str, str, str]:
    """(new pyproject, new changelog, version), with `fragments` ((name, text) pairs) folded into the Unreleased entry
    first, checked against CI's release gate; raises ValueError otherwise."""
    gates = _gates()
    current = gates.parse_version(pyproject)
    if (bump is None) == (version is None):
        raise ValueError("give exactly one of --minor, --patch or --version")
    if version is not None and not VERSION.match(version):
        raise ValueError(f"--version takes X.Y.Z digits, without a leading v: got {version!r}")
    version = version or next_version(current, bump)
    date = date or utc_today()
    dt.date.fromisoformat(date)  # an impossible date fails here, before the gate
    new_pyproject = bump_pyproject(pyproject, version)
    new_changelog = date_changelog(fold_fragments(changelog, fragments), version, date)
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
    ap.add_argument("--date", help="the release date, YYYY-MM-DD (default: today in UTC)")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT, help="the repository root (default: this checkout)")
    ap.add_argument("--dry-run", action="store_true", help="check and print, write nothing")
    args = ap.parse_args(argv)
    py_path, cl_path = args.root / "pyproject.toml", args.root / "CHANGELOG.md"
    try:
        frags = fragment_files(args.root)
        new_py, new_cl, version = cut(py_path.read_text(encoding="utf-8"), cl_path.read_text(encoding="utf-8"),
                                      bump=args.bump, version=args.version, date=args.date,
                                      fragments=[(f"{FRAGMENTS}/{p.name}", p.read_text(encoding="utf-8"))
                                                 for p in frags])
    except (OSError, ValueError) as exc:
        print(f"cut_release: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"v{version}: pyproject.toml and CHANGELOG.md would change, folding {len(frags)} fragment(s) "
              "(dry run, nothing written)")
        return 0
    py_path.write_text(new_py, encoding="utf-8")
    cl_path.write_text(new_cl, encoding="utf-8")
    for p in frags:
        p.unlink()
    branch = subprocess.run(["git", "-C", str(args.root), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()
    print(f"v{version}: pyproject.toml and CHANGELOG.md updated on {branch or 'a detached HEAD'}, "
          f"{len(frags)} fragment(s) folded in and deleted. Next:\n"
          f"  git add -A && git commit -m 'Release v{version}' && git push -u origin HEAD\n"
          f"  gh pr create --base dev --title 'Release v{version}: version and CHANGELOG'   # review, merge\n"
          f"  gh pr create --base main --head dev --title 'Release v{version}'              # review, merge (merge commit)\n"
          f"release.yml then tags v{version} and publishes the GitHub release. It deploys the site only if the owner\n"
          f"has set the production environment's deploy secret; otherwise its site job warns and skips, and the site\n"
          f"is deployed by hand from main (CONTRIBUTING.md#releases).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
