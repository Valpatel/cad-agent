"""Pin the install guide's checked installer blocks to a commit (#799).

docs/practice/agent-workflow.md downloads each installer from an immutable raw.githubusercontent.com URL at a commit
and checks it against a SHA-256 kept in the guide. After a change to tools/site/assets/install.sh or install.ps1 is
committed and pushed, run this with that commit: it reads both files from Git at that commit (the blob, not a checkout
that may have converted line endings), requires them to equal HEAD's and the commit to be an ancestor of HEAD (so it
stays reachable once the branch merges), and rewrites each block's URL and hash. The hash is never typed by hand.

    python3 tools/site/pin_installers.py <commit>     # rewrite the guide
    python3 tools/site/pin_installers.py --check      # exit 1 unless the guide pins HEAD's installers

`--check` requires each block's SHA-256 to be HEAD's installer, and its URL's commit to hold that same file and to be
an ancestor of HEAD. In a shallow clone that lacks the URL's commit (CI's checkout), the commit cannot be checked
there and is reported as not checked; the hash is still checked. tests/cli/test_installer.py runs both.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
GUIDE = Path("docs") / "practice" / "agent-workflow.md"
INSTALLERS = {"posix": ("sh", "tools/site/assets/install.sh"),
              "powershell": ("powershell", "tools/site/assets/install.ps1")}
URL = r"(https://raw\.githubusercontent\.com/Valpatel/cad-agent/)([0-9a-f]{40})(/"


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True)


def _blob(root: Path, commit: str, path: str) -> Optional[bytes]:
    out = _git(root, "show", f"{commit}:{path}", check=False)
    return out.stdout if out.returncode == 0 else None


def _block(text: str, platform: str) -> re.Match:
    language = INSTALLERS[platform][0]
    found = list(re.finditer(r"<!-- checked-installer:" + platform + r" -->\n```" + language + r"\n(.*?)\n```", text, re.S))
    if len(found) != 1:
        raise SystemExit(f"{GUIDE}: expected one checked {platform} block, found {len(found)}")
    return found[0]


def commit_problems(root: Path, commit: str, path: str) -> List[str]:
    """Why ``commit`` cannot serve HEAD's ``path``: it does not hold the same bytes, or it is not an ancestor of HEAD.
    Empty when it can. ``["not checked: ..."]`` when this clone does not have the commit and is shallow."""
    if _git(root, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode:
        shallow = _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == b"true"
        return [f"not checked: {commit[:12]} is not in this shallow clone"] if shallow else \
            [f"{commit[:12]} is not a commit in this repository"]
    problems = []
    if _blob(root, commit, path) != _blob(root, "HEAD", path):
        problems.append(f"{path} at {commit[:12]} is not HEAD's: the download would fail its checksum")
    if _git(root, "merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode:
        problems.append(f"{commit[:12]} is not an ancestor of HEAD: it may stop resolving once its branch is gone")
    return problems


def pin(text: str, commit: str, root: Path = ROOT) -> str:
    for platform, (_, path) in INSTALLERS.items():
        refused = [p for p in commit_problems(root, commit, path) if not p.startswith("not checked")]
        if refused or _blob(root, commit, path) is None:
            raise SystemExit("; ".join(refused) or f"{commit} is not in this clone")
        m = _block(text, platform)
        body = re.sub(URL + re.escape(path) + ")", lambda u: u.group(1) + commit + u.group(3), m.group(1))
        body, n = re.subn(r"\b[0-9a-f]{64}\b", hashlib.sha256(_blob(root, commit, path)).hexdigest(), body)
        if n != 1 or commit not in body:
            raise SystemExit(f"{GUIDE}: the {platform} block needs one pinned URL and one SHA-256")
        text = text[:m.start(1)] + body + text[m.end(1):]
    return text


def check(text: str, root: Path = ROOT) -> List[str]:
    """What is wrong with the guide's pins against HEAD, plus "not checked" notes; empty when all is right."""
    out = []
    for platform, (_, path) in INSTALLERS.items():
        body = _block(text, platform).group(1)
        if hashlib.sha256(_blob(root, "HEAD", path) or b"").hexdigest() not in body:
            out.append(f"the {platform} block's SHA-256 is not HEAD's {path}")
        urls = re.findall(URL + re.escape(path) + ")", body)
        if len(urls) != 1:
            out.append(f"the {platform} block needs one pinned URL for {path}")
            continue
        out += [f"the {platform} block's URL: {p}" for p in commit_problems(root, urls[0][1], path)]
    return out


def main(argv=None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("commit", nargs="?", help="the pushed commit that holds the installers")
    ap.add_argument("--check", action="store_true", help="only check the guide's pins against HEAD")
    args = ap.parse_args(argv)
    guide = root / GUIDE
    text = guide.read_text()
    if args.check:
        found = check(text, root)
        for line in found:
            print(f"{GUIDE.name}: {line}", file=sys.stderr)
        return 1 if any(not line.split(": ", 1)[-1].startswith("not checked") for line in found) else 0
    if not args.commit:
        ap.error("give the commit to pin, or --check")
    commit = _git(root, "rev-parse", "--verify", args.commit + "^{commit}").stdout.decode().strip()
    guide.write_text(pin(text, commit, root))
    print(f"pinned both installers at {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
