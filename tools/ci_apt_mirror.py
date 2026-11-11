#!/usr/bin/env python3
"""Remove the hanging Azure HTTP mirror from the hosted Ubuntu runner mirror list.

The runner image supplies Canonical HTTPS archive/security fallbacks. Keep those
and all apt source/signature settings; fail rather than guessing a new layout.
"""
from pathlib import Path
import sys

AZURE = "http://azure.archive.ubuntu.com/ubuntu/"
ARCHIVE = "https://archive.ubuntu.com/ubuntu/"


def configure(path: Path) -> None:
    original = path.read_text()
    lines = original.splitlines(keepends=True)
    entries = [line.split()[0] for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if ARCHIVE not in entries:
        raise ValueError("runner mirror list lacks the expected Canonical HTTPS archive")
    updated = "".join(line for line in lines if not line.strip() or line.split()[0] != AZURE)
    if updated != original:
        path.write_text(updated)
    print("Ubuntu apt mirror: Canonical HTTPS archive available; Azure HTTP entry absent")


if __name__ == "__main__":
    configure(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("/etc/apt/apt-mirrors.txt"))
