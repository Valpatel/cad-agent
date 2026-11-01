"""Reproducible outputs beyond part STEP files (#150): the review package zip, report pages and the date they record.

Each output is built twice in a fresh process, the second time with the wall clock moved by more than a year (a
``sitecustomize`` shifts ``datetime``, ``date`` and ``time``), after the files' modification times and modes have
changed as they do in another checkout; the bytes must be the same. A real change to an input must still change them.
The dates come from ``SOURCE_DATE_EPOCH``, else the last commit (``cadagent.project.source_time``): the test project's
commits are dated 2001, so a wall-clock date would show. The assembly STEP file is tested in ``test_step_export.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from cadagent import project as P
from cadagent.cli import main

from .test_report import make_project

SRC = Path(__file__).resolve().parents[1] / "src"
FIRST = "2001-02-03T04:05:06+00:00"          # the test project's first commit
LATER = "2002-03-04T05:06:07+00:00"
SHIFT_S = 400 * 86400 + 5 * 3600 + 7 * 60     # the second build's clock: 400 days, 5 h and 7 min later

# Run before the build in the child process: every way Python reads the clock returns the time SHIFT seconds on.
SITECUSTOMIZE = '''
import datetime as _dt, os as _os, time as _t
_shift = float(_os.environ.get("CAD_TEST_CLOCK_SHIFT", "0"))
_real_time, _real_ns, _real_local, _real_gm = _t.time, _t.time_ns, _t.localtime, _t.gmtime
_t.time = lambda: _real_time() + _shift
_t.time_ns = lambda: _real_ns() + int(_shift * 1e9)
_t.localtime = lambda s=None: _real_local(_t.time() if s is None else s)
_t.gmtime = lambda s=None: _real_gm(_t.time() if s is None else s)
_RealDT, _RealD = _dt.datetime, _dt.date
class _DT(_RealDT):
    @classmethod
    def now(cls, tz=None):
        return _RealDT.fromtimestamp(_t.time(), tz)
    @classmethod
    def utcnow(cls):
        return _RealDT.fromtimestamp(_t.time(), _dt.timezone.utc).replace(tzinfo=None)
    @classmethod
    def today(cls):
        return _RealDT.fromtimestamp(_t.time())
class _D(_RealD):
    @classmethod
    def today(cls):
        return _RealD.fromtimestamp(_t.time())
_dt.datetime, _dt.date = _DT, _D
'''

# The child: every output this test covers, from the project at argv[1].
BUILD = '''
import os, sys
from pathlib import Path
root = Path(sys.argv[1])
os.chdir(root)
from cadagent.cli import main
assert main(["report", "--project", str(root)]) == 0
assert main(["package", "--project", str(root)]) == 0          # after the report: it packages the results JSON
from cadagent.publish import site
site.build_site(root, {"title": "Demo", "pages": ["README.md", "docs/*.md"]}, "Demo")
from cadagent.simulation.simreport import write_report
write_report(root / "preview" / "simulation.html", "Demo", [{"id": "a", "title": "A", "summary": "s"}])
import datetime, time
print(datetime.datetime.now().year, time.time())
'''

OUTPUTS = ["exports/demo-review.zip", "exports/demo-review-manifest.json", "exports/cad-agent-results.json",
           "docs/cad-agent-report.html", "site/index.html", "site/pages/readme-md.html", "preview/simulation.html"]


def _git(root: Path, *args: str, date: str = FIRST) -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True,
                          env=env).stdout


def _commit(root: Path, message: str, date: str, *paths: str) -> None:
    _git(root, "add", "--", *(paths or ["."]), date=date)
    _git(root, "commit", "-q", "-m", message, date=date)


def _project(tmp_path: Path) -> Path:
    root = make_project(tmp_path / "demo")
    with open(root / "cad-agent.yaml", "a") as fh:
        fh.write("  package: {name: demo-review, include: ['exports/*.stl', 'exports/*.json', 'cad/*.py', "
                 "'README.md']}\n")
    (root / "cad").mkdir()
    (root / "cad" / "build.py").write_text("print('box')\n")
    (root / "README.md").write_text("# Demo\n\nA box.\n")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "plan.md").write_text("# Plan\n\nBuild it.\n")
    _git(root, "init", "-q")
    _commit(root, "first", FIRST)
    return root


def _build(root: Path, tmp_path: Path, shift: float = 0) -> dict:
    """Build every output in a fresh process with the clock moved ``shift`` seconds; return their bytes."""
    hook = tmp_path / "clock"
    hook.mkdir(exist_ok=True)
    (hook / "sitecustomize.py").write_text(SITECUSTOMIZE)
    env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
    env.update(PYTHONPATH=os.pathsep.join([str(hook), str(SRC)]), CAD_TEST_CLOCK_SHIFT=str(shift),
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    r = subprocess.run([sys.executable, "-c", BUILD, str(root)], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    year, clock = r.stdout.split()[-2:]
    import time
    assert abs(float(clock) - time.time() - shift) < 120, "the child's clock was not moved"
    return {rel: (root / rel).read_bytes() for rel in OUTPUTS}


def _as_another_checkout(root: Path) -> None:
    """New modification times and modes, as a fresh clone or another machine gives the same files."""
    for i, p in enumerate(sorted(q for q in root.rglob("*") if q.is_file() and ".git" not in q.parts)):
        os.utime(p, (1_500_000_000 + i * 7919, 1_500_000_000 + i * 7919))
        p.chmod(0o600 if i % 2 else 0o664)


def test_every_output_is_the_same_bytes_with_another_clock_and_checkout(tmp_path):
    pytest.importorskip("markdown")
    pytest.importorskip("yaml")
    root = _project(tmp_path)
    first = _build(root, tmp_path)
    _as_another_checkout(root)
    second = _build(root, tmp_path, shift=SHIFT_S)
    for rel in OUTPUTS:
        assert second[rel] == first[rel], f"{rel} changed with the wall clock or the checkout"

    stamp = "2001-02-03 04:05 UTC (last commit)"
    results = json.loads(first["exports/cad-agent-results.json"])
    assert results["header_meta"]["generated"] == stamp
    assert stamp.encode() in first["docs/cad-agent-report.html"]
    assert f"as of {stamp}".encode() in first["site/index.html"]
    assert b"<code>docs/plan.md</code> \xc2\xb7 2001-02-03" in first["site/index.html"]   # the commit's date
    assert stamp.encode() in first["preview/simulation.html"]
    with zipfile.ZipFile(root / "exports/demo-review.zip") as z:
        infos = z.infolist()
    names = [i.filename for i in infos]
    assert names == sorted(names) and "exports/demo-review-manifest.json" in names and "cad/build.py" in names
    assert {i.date_time for i in infos} == {(2001, 2, 3, 4, 5, 6)}
    assert {i.external_attr >> 16 for i in infos} == {0o100644} and {i.create_system for i in infos} == {3}


def test_a_real_change_still_changes_the_outputs_and_committing_them_does_not(tmp_path):
    pytest.importorskip("markdown")
    pytest.importorskip("yaml")
    root = _project(tmp_path)
    before = _build(root, tmp_path)
    # Committing the outputs themselves (a project that keeps its report and site in git) changes none of them: not
    # their date, and not the site's "Recent changes" table, which lists the commits that changed a source.
    _commit(root, "outputs", LATER, *OUTPUTS)
    again = _build(root, tmp_path)
    assert again == before
    assert b"<td>first</td>" in again["site/index.html"] and b"<td>outputs</td>" not in again["site/index.html"]

    (root / "exports" / "box.stl").write_text("a changed mesh")              # an input changes, uncommitted
    changed = _build(root, tmp_path)
    assert changed["exports/demo-review.zip"] != before["exports/demo-review.zip"]
    manifest = json.loads(changed["exports/demo-review-manifest.json"])
    assert manifest["exports/box.stl"] == P_sha256(b"a changed mesh")

    _commit(root, "new mesh", LATER, "exports/box.stl")                     # a committed output: same date
    assert _build(root, tmp_path)["exports/demo-review.zip"] == changed["exports/demo-review.zip"]
    (root / "cad" / "build.py").write_text("print('a bigger box')\n")
    _commit(root, "bigger box", LATER, "cad/build.py")                       # a committed source: the date moves
    after = _build(root, tmp_path)
    assert json.loads(after["exports/cad-agent-results.json"])["header_meta"]["generated"] == \
        "2002-03-04 05:06 UTC (last commit)"
    for rel in OUTPUTS:                     # a rendered Markdown page shows no date; the manifest: build.py's hash
        if rel != "site/pages/readme-md.html":
            assert after[rel] != changed[rel], f"{rel} kept the old commit's date"
    assert b"<td>bigger box</td>" in after["site/index.html"]


def P_sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------ the date helpers

def test_source_date_epoch_is_read_and_a_malformed_value_is_an_error(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert P.source_date_epoch() is None
    monkeypatch.setenv("SOURCE_DATE_EPOCH", " ")
    assert P.source_date_epoch() is None
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert P.source_date_epoch() == 1700000000
    for bad in ("-1", "1.5", "1e9", "soon", "１２", "99999999999999999999"):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", bad)
        with pytest.raises(P.SourceDateEpochError, match="SOURCE_DATE_EPOCH"):
            P.source_date_epoch()


def test_source_time_prefers_source_date_epoch_then_the_last_commit(tmp_path, monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    root = tmp_path / "repo"
    (root / "proj" / "out").mkdir(parents=True)
    (root / "other").mkdir()
    assert P.source_time(root) is None                                       # not a git checkout
    assert P.source_stamp(root) == "undated (no commit; set SOURCE_DATE_EPOCH)"
    _git(root, "init", "-q")
    assert P.source_time(root) is None                                       # nothing committed yet
    (root / "proj" / "a.txt").write_text("a")
    _commit(root, "a", FIRST)
    when, origin = P.source_time(root / "proj")
    assert when.isoformat() == FIRST and origin == "last commit"
    (root / "other" / "b.txt").write_text("b")                              # another folder of the repository
    (root / "proj" / "out" / "page.html").write_text("p")                   # and the project's own output
    _commit(root, "b", LATER)
    assert P.source_time(root / "proj", outputs=["out"])[0].isoformat() == FIRST
    assert P.source_time(root / "proj", outputs=[root / "proj" / "out" / "page.html"])[0].isoformat() == FIRST
    assert P.source_time(root / "proj")[0].isoformat() == LATER
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert P.source_stamp(root / "proj") == "2023-11-14 22:13 UTC (SOURCE_DATE_EPOCH)"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "tomorrow")
    with pytest.raises(P.SourceDateEpochError):
        P.source_time(root)


def test_zip_dates_are_clamped_to_what_a_zip_can_hold():
    import datetime
    from cadagent.package import ZIP_DATE, zip_date

    utc = datetime.timezone.utc
    assert zip_date(None) == ZIP_DATE
    assert zip_date(datetime.datetime(1970, 1, 1, tzinfo=utc)) == ZIP_DATE
    assert zip_date(datetime.datetime(2001, 2, 3, 4, 5, 7, tzinfo=utc)) == (2001, 2, 3, 4, 5, 6)   # 2 s steps
    assert zip_date(datetime.datetime(2001, 2, 3, 5, 5, 6, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))) \
        == (2001, 2, 3, 4, 5, 6)                                             # UTC, whatever the zone
    assert zip_date(datetime.datetime(2200, 1, 1, tzinfo=utc)) == (2107, 12, 31, 23, 59, 58)


def test_the_package_follows_source_date_epoch(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert main(["package", "--project", str(root)]) == 0
    with zipfile.ZipFile(root / "exports/demo-review.zip") as z:
        assert {i.date_time for i in z.infolist()} == {(2023, 11, 14, 22, 13, 20)}


def test_a_malformed_source_date_epoch_stops_package_report_and_release(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1.5")
    for command in ("package", "report", "release"):
        assert main([command, "--project", str(root)]) == 2, command
        assert "SOURCE_DATE_EPOCH='1.5' is not a whole number" in capsys.readouterr().err
    assert not (root / "exports" / "demo-review.zip").exists()
    assert not (root / "exports" / "demo-review-manifest.json").exists()


def test_a_malformed_source_date_epoch_leaves_the_package_and_site_as_they_were(tmp_path, monkeypatch):
    """The date is read before anything is written: no manifest that no longer matches its zip, no half a site."""
    pytest.importorskip("markdown")
    from cadagent.publish import site

    root = _project(tmp_path)
    assert main(["package", "--project", str(root)]) == 0
    built = {rel: (root / rel).read_bytes() for rel in ("exports/demo-review.zip", "exports/demo-review-manifest.json")}
    (root / "README.md").write_text("# Demo\n\nA bigger box.\n")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1.5")
    assert main(["package", "--project", str(root)]) == 2
    assert {rel: (root / rel).read_bytes() for rel in built} == built
    with pytest.raises(P.SourceDateEpochError):
        site.build_site(root, {"title": "Demo", "pages": ["README.md"]}, "Demo")
    assert not (root / "site").exists()


def test_a_document_card_dates_a_page_whose_name_is_not_ascii(tmp_path):
    """git quotes such paths in its output unless told not to (core.quotePath)."""
    from cadagent.publish import site

    root = _project(tmp_path)
    (root / "docs" / "Gehäuse.md").write_text("# Gehäuse\n")
    _commit(root, "housing", LATER, "docs/Gehäuse.md")
    assert site.committed_dates(root, ["docs/Gehäuse.md", "docs/plan.md", "docs/none.md"]) == \
        {"docs/Gehäuse.md": "2002-03-04", "docs/plan.md": "2001-02-03"}


def test_a_simulation_page_is_dated_by_its_project_wherever_the_script_runs(tmp_path, monkeypatch):
    from cadagent.simulation.simreport import write_report

    root = _project(tmp_path)
    (root / "sim").mkdir()
    (root / "sim" / "run.py").write_text("print('run')\n")
    _commit(root, "simulation", LATER, "sim/run.py")
    (root / "cad" / "build.py").write_text("print('a bigger box')\n")
    _commit(root, "bigger box", "2003-01-01T00:00:00+00:00", "cad/build.py")   # sim/'s own history ends earlier
    pages = []
    for where in (root, root / "sim", tmp_path):                                # root, a subfolder, outside it
        monkeypatch.chdir(where)
        pages.append(write_report(root / "preview" / "sim.html", "Sim", [{"id": "a", "title": "A"}]).read_bytes())
    assert pages[0] == pages[1] == pages[2] and b"2003-01-01 00:00 UTC (last commit)" in pages[0]


def test_the_comparison_and_the_review_bundle_are_dated_by_the_source(tmp_path, monkeypatch):
    from cadagent.simulation.explore.compare import comparison
    from cadagent.simulation.explore.config import ExploreConfig

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert comparison([], ExploreConfig(root=tmp_path, title="T"))["generated"] == \
        "2023-11-14 22:13 UTC (SOURCE_DATE_EPOCH)"
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert comparison([], ExploreConfig(root=tmp_path, title="T"))["generated"].startswith("undated")
    from cadagent.review.dossier.review import _source_iso
    root = _project(tmp_path)
    assert _source_iso(root, root / "exports" / "review-bundle") == "2001-02-03T04:05:06Z"


def test_the_generated_paths_are_where_cad_agent_writes(tmp_path):
    from cadagent.publish import report, site

    assert site.SITE_DIR in P.GENERATED and "release" in P.GENERATED and report.REPORT_NAME == P.REPORT_PAGE
    root = _project(tmp_path)
    with open(root / "cad-agent.yaml", "a") as fh:
        fh.write("  exports_dir: out\n  docs_dir: pages\n")
    assert [p.relative_to(root).as_posix() for p in P.generated_paths(root)] == \
        ["out", "preview", "site", "release", "pages/cad-agent-report.html"]
    (root / "cad-agent.yaml").write_text("cad: [not, a, mapping]\n")       # unreadable: the default places
    assert [p.relative_to(root).as_posix() for p in P.generated_paths(root)] == \
        ["exports", "preview", "site", "release", "docs/cad-agent-report.html"]
