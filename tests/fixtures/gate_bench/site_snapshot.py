"""Refresh ``site_snapshot/``: the clean gate bench's exports (geometry record, gate verdicts, dossier status), so
the review-site tests (``tests/test_site_review.py``) build the pages in core CI without CadQuery.

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


def main() -> int:
    from cadagent.cli import main as cli
    with tempfile.TemporaryDirectory() as tmp:
        bench = Path(tmp) / "gate_bench"
        shutil.copytree(HERE, bench, ignore=shutil.ignore_patterns("__pycache__", "site_snapshot", "exports", "site"))
        code = cli(["gates", "--project", str(bench / "project"), "--build", "--jobs", "2"])
        if code != 0:
            print("the clean bench must pass every gate", file=sys.stderr)
            return 1
        exports = bench / "project" / "exports"
        shutil.rmtree(OUT, ignore_errors=True)
        for src in [exports / "dossier-geometry.json", exports / "dossier-status.json",
                    *sorted((exports / "gates").glob("*"))]:
            dst = OUT / src.relative_to(exports)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix == ".json":
                dst.write_text(json.dumps(json.loads(src.read_text()), separators=(",", ":")) + "\n")
            else:
                shutil.copy(src, dst)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
