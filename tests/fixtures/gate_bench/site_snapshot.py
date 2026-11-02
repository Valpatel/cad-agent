"""Refresh ``site_snapshot/``: the clean gate bench's exports (geometry record, gate verdicts, dossier status), so
the review-site tests (``tests/publish/test_site_review.py``) build the pages in core CI without CadQuery.

Run it after a change to the bench, its dossier or the gates (needs the ``cad`` extra)::

    python tests/fixtures/gate_bench/site_snapshot.py

It copies the bench to a temporary directory, runs ``cad-agent gates --build`` there and copies back the files the
site reads (JSON compacted; the BREP shapes are not needed and not kept).
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "site_snapshot"


def generate(out: Path, jobs: int = 2) -> int:
    """Build the clean bench in a temporary copy, run every gate and write the site's inputs to ``out``. Returns the
    ``cad-agent gates`` exit code (0: every gate passed); ``out`` is written only then."""
    from cadagent.cli import main as cli
    with tempfile.TemporaryDirectory() as tmp:
        bench = Path(tmp) / "gate_bench"
        shutil.copytree(HERE, bench, ignore=shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site"))
        code = cli(["gates", "--project", str(bench / "project"), "--build", "--jobs", str(jobs)])
        if code != 0:
            return code
        exports = bench / "project" / "exports"
        shutil.rmtree(out, ignore_errors=True)
        for src in [exports / "dossier-geometry.json", exports / "dossier-status.json",
                    *sorted((exports / "gates").glob("*"))]:
            dst = Path(out) / src.relative_to(exports)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix == ".json":
                dst.write_text(json.dumps(json.loads(src.read_text()), separators=(",", ":")) + "\n")
            else:
                shutil.copy(src, dst)
    return 0


def summary(folder: Path) -> dict:
    """What the snapshot means, without the content hashes (an OCCT upgrade changes those, not the meaning): each
    verdict's status and check ids with their states, and every status in the dossier status file."""
    folder = Path(folder)
    out = {"gates": {}, "files": sorted(p.name for p in (folder / "gates").iterdir())}
    for p in sorted((folder / "gates").glob("*.json")):
        v = json.loads(p.read_text())
        out["gates"][p.stem] = {"status": v.get("status"), "pass": v.get("pass"),
                                "checks": sorted((c.get("id"), c.get("status")) for c in v.get("checks") or [])}
    st = json.loads((folder / "dossier-status.json").read_text())
    out["status"] = {kind: {k: x.get("status") for k, x in st.get(kind, {}).items()}
                     for kind in ("sections", "parts", "requirements", "decisions")}
    out["pass"] = st.get("pass")
    return out


def main() -> int:
    code = generate(OUT)
    if code != 0:
        print("the clean bench must pass every gate", file=sys.stderr)
        return 1
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
