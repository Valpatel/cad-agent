"""Explicit owners for transferred SCADA development tooling."""
from pathlib import Path
import re
import unicodedata
TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
UI = REPO / "software/cadagent/webkit/scada/ui"
SIM = REPO / "software/cadagent/webkit/scada/sim"
TESTS = REPO / "tests/webkit/scada"


def sector_label(value):
    """Missing sector metadata has one explicit, deterministic gallery home."""
    return value.strip() if isinstance(value, str) and value.strip() else "Uncategorized"


def sector_slug(value):
    text = unicodedata.normalize("NFKD", sector_label(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "uncategorized"


def scenario_asset_path(kind, entry):
    names = {"thumbnails": "preview.jpg", "topologies": "topology.svg"}
    if kind not in names or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", entry["id"]):
        raise ValueError("A known gallery kind and safe stable scenario ID are required")
    return f"img/{kind}/{sector_slug(entry.get('sector'))}/{entry['id']}/{names[kind]}"


def scenario_sector_groups(entries):
    """Reject ambiguous labels rather than merging two sectors by accident."""
    groups, labels = {}, {}
    for entry in entries:
        label = sector_label(entry.get("sector"))
        slug = sector_slug(label)
        if slug in labels and labels[slug] != label:
            raise ValueError(f"Sector path collision: {labels[slug]!r} and {label!r} both use {slug!r}")
        labels[slug] = label
        groups.setdefault(slug, []).append(entry)
    return [(slug, labels[slug], groups[slug]) for slug in sorted(groups)]
