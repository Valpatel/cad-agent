#!/usr/bin/env python3
"""Correct only observed hosted Ubuntu runner apt mirror/source profiles.

Prefer the registered Pilot Fiber HTTPS mirror outside Canonical's DNS failure
scope. Keep Canonical fallbacks and all source/signature settings; reject unknown
mirror priorities or an inactive mirror file before writing anything.
"""
from pathlib import Path
import json
import re
import sys
import platform
import hashlib
from urllib.parse import urlsplit

AZURE = "http://azure.archive.ubuntu.com/ubuntu/"
# Captured by the rejection diagnostic in hosted full job 131436221538 (2026-11-12).
# Exact observed URI only: other regions or cloud-branded hosts are not inferred.
EC2 = "http://us-east-2.ec2.archive.ubuntu.com/ubuntu/"
ARCHIVE = "https://archive.ubuntu.com/ubuntu/"
SECURITY = "https://security.ubuntu.com/ubuntu/"
MIRROR = "mirror+file:/etc/apt/apt-mirrors.txt"
# Ubuntu Official Archive Mirrors: /ubuntu/+mirror/mirror.pilotfiber.com-archive.
PREFERRED = "https://mirror.pilotfiber.com/ubuntu/"
EXPECTED = {AZURE: "priority:1", EC2: "priority:1", PREFERRED: "priority:1",
            ARCHIVE: "priority:2", SECURITY: "priority:3"}


def mirror_profile(text: str) -> str:
    """Bounded rejection evidence: omit credentials, queries and nonstandard paths."""
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tokens = line.split()
        try:
            url = urlsplit(tokens[0])
            host = (url.hostname or "<missing-host>")[:253]
            port = f":{url.port}" if url.port is not None else ""
            path = url.path if url.path in ("", "/", "/ubuntu", "/ubuntu/") else "<other-path>"
            uri = f"{url.scheme[:16]}://{host}{port}{path}"
        except ValueError:
            uri = "<malformed-uri>"
        priority = tokens[1] if len(tokens) > 1 and re.fullmatch(r"priority:[0-9]{1,6}", tokens[1]) else "<invalid-priority>"
        entries.append({"line": number, "uri": uri, "priority": priority, "fields": len(tokens)})
        if len(entries) == 12:
            break
    return json.dumps(entries, sort_keys=True)


def runner_codename(release: dict) -> str:
    if (release.get("ID"), release.get("VERSION_ID"), release.get("VERSION_CODENAME")) != ("ubuntu", "24.04", "noble"):
        raise ValueError("expected the workflow's Ubuntu 24.04 noble runner")
    return release["VERSION_CODENAME"]


def source_profile(text: str) -> str:
    """Failure evidence only: bounded known fields, no credentials or arbitrary values."""
    visible_paths = {"/etc/apt/apt-mirrors.txt", "/etc/apt/mirrors/ubuntu.list",
                     "/etc/apt/mirrors/ubuntu.sources"}  # Visibility, NOT accepted source URIs.
    words = {"types": {"deb", "deb-src"}, "suites": {"noble", "noble-updates", "noble-backports", "noble-security"},
             "components": {"main", "universe", "restricted", "multiverse"},
             "enabled": {"yes", "no"}, "trusted": {"yes", "no"}}
    result = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "fields": [], "truncated": False}
    current = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        continuation = line[0].isspace() and current is not None
        if continuation:
            key, value = current, line.strip()
        else:
            key, separator, value = line.partition(":")
            key = key.lower() if separator else "<malformed-field>"
            current = key
        tokens = value.split()
        values = []
        for token in tokens[:8]:
            if key == "uris":
                try:
                    uri = urlsplit(token)
                    if uri.scheme in ("file", "mirror+file"):
                        values.append(uri.scheme + ":" + (uri.path if uri.path in visible_paths else "<other-path>"))
                    else:
                        profile = json.loads(mirror_profile(token + " priority:1"))
                        values.append(profile[0]["uri"] if profile else "<malformed-uri>")
                except ValueError:
                    values.append("<malformed-uri>")
            elif key == "signed-by":
                values.append(token if token == "/usr/share/keyrings/ubuntu-archive-keyring.gpg" else "<other-keyring>")
            elif key in words:
                values.append(token if token in words[key] else "<other-value>")
        record = {"line": number, "field": key if key in {*words, "uris", "signed-by"} else "<other-field>",
                  "continuation": bool(continuation), "tokens": len(tokens), "values": values}
        candidate = {**result, "fields": result["fields"] + [record]}
        if len(result["fields"]) == 24 or len(json.dumps(candidate)) > 8000:
            result["truncated"] = True
            break
        result = candidate
    return json.dumps(result, sort_keys=True)


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
            raise ValueError("unexpected hosted runner mirror entry or priority; observed=" + mirror_profile(original))
        seen.add(tokens[0])
    if seen not in ({AZURE, ARCHIVE, SECURITY}, {EC2, ARCHIVE, SECURITY}, {PREFERRED, ARCHIVE, SECURITY}):
        raise ValueError("runner mirror list lacks the expected Canonical HTTPS fallbacks; observed=" + mirror_profile(original))
    source_text = source.read_text()
    try:
        validate_source(source_text, codename)
    except ValueError:
        print("Rejected Ubuntu source; observed=" + source_profile(source_text), file=sys.stderr)
        raise
    primary = next(uri for uri in (AZURE, EC2, PREFERRED) if uri in seen)
    updated = "".join(line.replace(primary, PREFERRED, 1) if line.strip() and line.split()[0] == primary else line
                      for line in lines)
    if updated != original:
        path.write_text(updated)
    print(f"Ubuntu apt source/profile verified (input primary: {primary}); "
          "registered HTTPS mirror preferred, Canonical fallbacks retained")


if __name__ == "__main__":
    if len(sys.argv) not in (1, 3):
        raise SystemExit("usage: apt_mirror.py [MIRROR_FILE UBUNTU_SOURCES]")
    paths = tuple(map(Path, sys.argv[1:])) if len(sys.argv) == 3 else (
        Path("/etc/apt/apt-mirrors.txt"), Path("/etc/apt/sources.list.d/ubuntu.sources"))
    configure(*paths, codename=runner_codename(platform.freedesktop_os_release()))
