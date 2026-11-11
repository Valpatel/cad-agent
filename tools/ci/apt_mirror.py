#!/usr/bin/env python3
"""Correct only the pinned hosted Ubuntu runner apt mirror/source contract.

Keep Canonical HTTPS fallbacks and all source/signature settings; reject unknown
mirror priorities or an inactive mirror file before writing anything.
"""
from pathlib import Path
import sys

AZURE = "http://azure.archive.ubuntu.com/ubuntu/"
ARCHIVE = "https://archive.ubuntu.com/ubuntu/"
SECURITY = "https://security.ubuntu.com/ubuntu/"
MIRROR = "mirror+file:/etc/apt/apt-mirrors.txt"
EXPECTED = {AZURE: "priority:1", ARCHIVE: "priority:2", SECURITY: "priority:3"}


def validate_source(text: str) -> None:
    active = 0
    for stanza in text.split("\n\n"):
        fields = {}
        current = None
        for line in stanza.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line[0].isspace() and current:
                fields[current] += " " + line.strip()
            else:
                key, separator, value = line.partition(":")
                if not separator or key.lower() in fields:
                    raise ValueError("unexpected Ubuntu deb822 source shape")
                current = key.lower()
                fields[current] = value.strip()
        if not fields or fields.get("enabled", "yes").lower() == "no":
            continue
        if fields.get("uris", "").split() != [MIRROR]:
            raise ValueError("active Ubuntu source must use the expected mirror file")
        if not fields.get("types") or not fields.get("suites") or not fields.get("signed-by"):
            raise ValueError("unexpected Ubuntu deb822 source shape")
        active += 1
    if not active:
        raise ValueError("no active Ubuntu mirror-file source")


def configure(path: Path, source: Path) -> None:
    original = path.read_text()
    lines = original.splitlines(keepends=True)
    seen = set()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tokens = line.split()
        if len(tokens) != 2 or EXPECTED.get(tokens[0]) != tokens[1] or tokens[0] in seen:
            raise ValueError("unexpected hosted runner mirror entry or priority")
        seen.add(tokens[0])
    if seen not in ({AZURE, ARCHIVE, SECURITY}, {ARCHIVE, SECURITY}):
        raise ValueError("runner mirror list lacks the expected Canonical HTTPS fallbacks")
    validate_source(source.read_text())
    updated = "".join(line for line in lines if not line.strip() or line.split()[0] != AZURE)
    if updated != original:
        path.write_text(updated)
    print("Ubuntu apt source uses verified mirror list; Azure HTTP entry absent")


if __name__ == "__main__":
    if len(sys.argv) not in (1, 3):
        raise SystemExit("usage: apt_mirror.py [MIRROR_FILE UBUNTU_SOURCES]")
    configure(*(map(Path, sys.argv[1:]) if len(sys.argv) == 3 else
                (Path("/etc/apt/apt-mirrors.txt"), Path("/etc/apt/sources.list.d/ubuntu.sources"))))
