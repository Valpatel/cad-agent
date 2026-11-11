#!/usr/bin/env python3
"""Correct only the pinned hosted Ubuntu runner apt mirror/source contract.

Prefer the registered Pilot Fiber HTTPS mirror outside Canonical's DNS failure
scope. Keep Canonical fallbacks and all source/signature settings; reject unknown
mirror priorities or an inactive mirror file before writing anything.
"""
from pathlib import Path
import sys
import platform

AZURE = "http://azure.archive.ubuntu.com/ubuntu/"
ARCHIVE = "https://archive.ubuntu.com/ubuntu/"
SECURITY = "https://security.ubuntu.com/ubuntu/"
MIRROR = "mirror+file:/etc/apt/apt-mirrors.txt"
# Ubuntu Official Archive Mirrors: /ubuntu/+mirror/mirror.pilotfiber.com-archive.
PREFERRED = "https://mirror.pilotfiber.com/ubuntu/"
EXPECTED = {AZURE: "priority:1", PREFERRED: "priority:1", ARCHIVE: "priority:2", SECURITY: "priority:3"}


def runner_codename(release: dict) -> str:
    if (release.get("ID"), release.get("VERSION_ID"), release.get("VERSION_CODENAME")) != ("ubuntu", "24.04", "noble"):
        raise ValueError("expected the workflow's Ubuntu 24.04 noble runner")
    return release["VERSION_CODENAME"]


def validate_source(text: str, codename: str) -> None:
    expected_suites = {codename, *(codename + "-" + suffix for suffix in ("updates", "backports", "security"))}
    seen_suites = set()
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
        if not fields:
            continue
        allowed = {"types", "uris", "suites", "components", "signed-by", "enabled"}
        if set(fields) - allowed or fields.get("enabled", "yes").lower() != "yes":
            raise ValueError("unsupported Ubuntu source fields or enabled state")
        if fields.get("uris", "").split() != [MIRROR]:
            raise ValueError("active Ubuntu source must use the expected mirror file")
        suites = fields.get("suites", "").split()
        components = fields.get("components", "").split()
        if (fields.get("types", "").split() != ["deb"] or
                fields.get("signed-by") != "/usr/share/keyrings/ubuntu-archive-keyring.gpg" or
                set(components) != {"main", "universe", "restricted", "multiverse"} or len(components) != 4 or
                not suites or len(set(suites)) != len(suites) or
                not set(suites) <= expected_suites or seen_suites.intersection(suites)):
            raise ValueError("unsupported Ubuntu runner source values")
        seen_suites.update(suites)
        active += 1
    if not active or seen_suites != expected_suites:
        raise ValueError("expected the complete active Ubuntu runner suite set")


def configure(path: Path, source: Path, codename: str = "noble") -> None:
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
    if seen not in ({AZURE, ARCHIVE, SECURITY}, {PREFERRED, ARCHIVE, SECURITY}):
        raise ValueError("runner mirror list lacks the expected Canonical HTTPS fallbacks")
    validate_source(source.read_text(), codename)
    updated = "".join(line.replace(AZURE, PREFERRED, 1) if line.strip() and line.split()[0] == AZURE else line
                      for line in lines)
    if updated != original:
        path.write_text(updated)
    print("Ubuntu apt source/profile verified; registered HTTPS mirror preferred, Canonical fallbacks retained")


if __name__ == "__main__":
    if len(sys.argv) not in (1, 3):
        raise SystemExit("usage: apt_mirror.py [MIRROR_FILE UBUNTU_SOURCES]")
    paths = tuple(map(Path, sys.argv[1:])) if len(sys.argv) == 3 else (
        Path("/etc/apt/apt-mirrors.txt"), Path("/etc/apt/sources.list.d/ubuntu.sources"))
    configure(*paths, codename=runner_codename(platform.freedesktop_os_release()))
