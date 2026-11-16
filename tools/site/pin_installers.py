"""Pin the install guide's checked installer blocks to a commit (#799).

docs/practice/agent-workflow.md downloads each installer from an immutable raw.githubusercontent.com URL at a commit
and checks it against a SHA-256 kept in the guide. After a change to tools/site/assets/install.sh or install.ps1 is
committed and pushed, run this with that commit: it reads both files from Git at that commit (the blob, not a checkout
that may have converted line endings), requires them to equal HEAD's, and rewrites each block's URL and hash. The
hash is never typed by hand. tests/cli/test_installer.py checks the result against HEAD.

    python3 tools/site/pin_installers.py <commit>     # rewrite the guide
    python3 tools/site/pin_installers.py --check      # exit 1 if the guide's hashes are not HEAD's installers
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "practice" / "agent-workflow.md"
INSTALLERS = {"posix": ("sh", "tools/site/assets/install.sh"),
              "powershell": ("powershell", "tools/site/assets/install.ps1")}
URL = r"https://raw\.githubusercontent\.com/Valpatel/cad-agent/)([0-9a-f]{40})(/"


def _blob(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True, capture_output=True).stdout


def _block(text: str, platform: str) -> re.Match:
    language = INSTALLERS[platform][0]
    found = list(re.finditer(r"<!-- checked-installer:" + platform + r" -->\n```" + language + r"\n(.*?)\n```", text, re.S))
    if len(found) != 1:
        raise SystemExit(f"{GUIDE}: expected one checked {platform} block, found {len(found)}")
    return found[0]


def pin(text: str, commit: str) -> str:
    for platform, (_, path) in INSTALLERS.items():
        data = _blob(commit, path)
        if data != _blob("HEAD", path):
            raise SystemExit(f"{path} at {commit} is not HEAD's: commit the change, then pin that commit")
        m = _block(text, platform)
        body = re.sub("(" + URL + re.escape(path) + ")", lambda u: u.group(1) + commit + u.group(3), m.group(1))
        body, n = re.subn(r"\b[0-9a-f]{64}\b", hashlib.sha256(data).hexdigest(), body)
        if n != 1 or commit not in body:
            raise SystemExit(f"{GUIDE}: the {platform} block needs one pinned URL and one SHA-256")
        text = text[:m.start(1)] + body + text[m.end(1):]
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("commit", nargs="?", help="the pushed commit that holds the installers")
    ap.add_argument("--check", action="store_true", help="only check the guide's hashes against HEAD")
    args = ap.parse_args(argv)
    text = GUIDE.read_text()
    if args.check:
        bad = [p for p, (_, path) in INSTALLERS.items()
               if hashlib.sha256(_blob("HEAD", path)).hexdigest() not in _block(text, p).group(1)]
        for p in bad:
            print(f"{GUIDE.name}: the {p} block's SHA-256 is not HEAD's {INSTALLERS[p][1]}", file=sys.stderr)
        return 1 if bad else 0
    if not args.commit:
        ap.error("give the commit to pin, or --check")
    commit = subprocess.run(["git", "rev-parse", "--verify", args.commit + "^{commit}"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    GUIDE.write_text(pin(text, commit))
    print(f"pinned both installers at {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
