"""No tracked file names a private predecessor tool (#135).

The toolkit began inside a private tool. Its name means nothing outside the project, so no tracked file, path or
line may carry it, in any case and with or without a ``-``, ``_``, ``.`` or space between its two halves. The pattern
is built from pieces, so this file does not match it. ``ALLOWED`` lists the paths that may match, each with its
reason; it is empty, and an entry that no longer matches fails, so the list cannot go stale.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_HEAD, _TAIL = "vp", "test"
PATTERN = f"{_HEAD}[-_. ]?{_TAIL}"          # POSIX ERE and Python re alike; matched case-insensitively
ALLOWED: dict = {}                           # {"path/from/repo/root": "why it may carry the name"}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, errors="replace")


@pytest.fixture(scope="module")
def checkout():
    if shutil.which("git") is None or _git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        pytest.skip("not a git checkout: the tracked files are unknown")
    return ROOT


def _hits() -> dict:
    """``{path: ["line 12", ...]}`` for every tracked file whose path or content matches, binary files included.

    Locations only, never the matched text, so a failing run does not write the name into the CI log."""
    proc = _git("grep", "-a", "-n", "-i", "-E", "-e", PATTERN, "--", ".")
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed: {proc.stderr.strip()}")
    hits: dict = {}
    for line in proc.stdout.splitlines():
        path, _, rest = line.partition(":")
        hits.setdefault(path, []).append(f"line {rest.partition(':')[0]}")
    for path in _git("ls-files", "-z").stdout.split("\0"):
        if path and re.search(PATTERN, path, re.IGNORECASE):
            hits.setdefault(path, []).insert(0, "the path itself")
    return hits


def test_the_pattern_catches_every_form_and_skips_this_file():
    for form in ("", "-", "_", ".", " "):
        for name in (f"{_HEAD}{form}{_TAIL}", f"{_HEAD}{form}{_TAIL}".upper(), f"{_HEAD.title()}{form}{_TAIL.title()}"):
            assert re.search(PATTERN, f"x {name}.yaml", re.IGNORECASE), name
    for other in ("vp/test", "vpn-test", "v-ptest", "vp  test"):
        assert not re.search(PATTERN, other, re.IGNORECASE), other
    assert not re.search(PATTERN, Path(__file__).read_text(), re.IGNORECASE)


def test_no_tracked_file_names_the_private_tool(checkout):
    hits = {p: h for p, h in _hits().items() if p not in ALLOWED}
    if hits:                                 # pytest.fail, not assert: the assertion rewrite would echo the dict
        report = "\n".join(f"  {p}: {', '.join(h)}" for p, h in sorted(hits.items()))
        pytest.fail("a private predecessor tool's name is back in tracked files; reword each passage without it "
                    f"(or, with a reason, add the path to ALLOWED):\n{report}", pytrace=False)


def test_every_allowed_path_still_matches(checkout):
    stale = sorted(set(ALLOWED) - set(_hits()))
    if stale:
        pytest.fail(f"ALLOWED lists paths that no longer match; remove them: {stale}", pytrace=False)
