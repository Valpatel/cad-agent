"""The part cache (#250): built parts stored as BREP under a hash of their sources, checked on load.

The key tests run without cadquery; the build and load tests skip cleanly when it is missing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cadagent.geometry import cache as C
from cadagent.geometry.cache import PartCache


@pytest.fixture
def project(tmp_path):
    cad = tmp_path / "cad"
    cad.mkdir()
    (cad / "parameters.json").write_text('{"w": 10}')
    (cad / "common.py").write_text("W = 10\n")
    (cad / "arm.py").write_text("ARM = 1\n")
    (cad / "bucket.py").write_text("BUCKET = 1\n")
    return tmp_path


def _cache(root: Path, **kw) -> PartCache:
    return PartCache(root / ".cadagent-cache" / "parts", sources=[root / "cad" / "parameters.json",
                                                                   root / "cad" / "common.py"], **kw)


# keys: no cadquery needed

def test_the_key_follows_the_sources_and_the_extra_values(project):
    first = _cache(project).key()
    assert len(first) == C.KEY_LENGTH and _cache(project).key() == first           # stable across instances
    assert _cache(project, key_extra={"variant": "a"}).key() != first
    assert _cache(project, key_extra={"b": 1, "a": 2}).key() == _cache(project, key_extra={"a": 2, "b": 1}).key()
    (project / "cad" / "common.py").write_text("W = 11\n")
    assert _cache(project).key() != first


def test_deps_change_only_their_own_key(project):
    cache = _cache(project)
    arm, bucket, shared = cache.key([project / "cad" / "arm.py"]), cache.key([project / "cad" / "bucket.py"]), cache.key()
    assert len({arm, bucket, shared}) == 3
    (project / "cad" / "arm.py").write_text("ARM = 2\n")
    assert cache.key([project / "cad" / "arm.py"]) != arm
    assert cache.key([project / "cad" / "bucket.py"]) == bucket and cache.key() == shared


def test_a_folder_source_covers_its_files_but_not_bytecode(project):
    key = PartCache(project / "c", sources=[project / "cad"]).key()
    (project / "cad" / "__pycache__").mkdir()
    (project / "cad" / "__pycache__" / "common.cpython-312.pyc").write_bytes(b"x")
    assert PartCache(project / "c", sources=[project / "cad"]).key() == key
    (project / "cad" / "new.py").write_text("N = 1\n")
    assert PartCache(project / "c", sources=[project / "cad"]).key() != key


def test_a_missing_source_or_a_bad_name_is_an_error(project):
    with pytest.raises(FileNotFoundError, match="nope.py"):
        PartCache(project / "c", sources=[project / "cad" / "nope.py"])
    cache = _cache(project)
    with pytest.raises(FileNotFoundError, match="dependency"):
        cache.key([project / "cad" / "gone.py"])
    for bad in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            cache.path(bad)


def test_the_cache_folder_does_not_date_outputs(project, monkeypatch):
    """Under exports/ it is an output, so committing it does not move source_time (the reproducibility date)."""
    from cadagent import project as P

    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args, date):
        subprocess.run(["git", "-C", str(project), "-c", "user.name=T", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                       env={**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})

    git("init", "-q", date="2001-01-01T00:00:00+00:00")
    git("add", ".", date="2001-01-01T00:00:00+00:00")
    git("commit", "-qm", "src", date="2001-01-01T00:00:00+00:00")
    (project / "exports" / ".partcache" / "0123456789abcdef").mkdir(parents=True)
    (project / "exports" / ".partcache" / "0123456789abcdef" / "arm.brep").write_text("x")
    git("add", "-f", ".", date="2002-01-01T00:00:00+00:00")
    git("commit", "-qm", "cache", date="2002-01-01T00:00:00+00:00")
    assert P.source_time(project)[0].year == 2001


def test_the_review_package_skips_a_tagged_cache(project):
    from cadagent.package import in_cache_dir

    folder = project / "exports" / ".partcache" / "0123456789abcdef"
    folder.mkdir(parents=True)
    brep = folder / "arm.brep"
    brep.write_text("x")
    assert not in_cache_dir(brep, project)
    (project / "exports" / ".partcache" / C.CACHE_TAG).write_text(C.CACHE_TAG_TEXT)
    assert in_cache_dir(brep, project)
    assert not in_cache_dir(project / "exports" / "arm.step", project)


# build and load: cadquery

def _builders(cq, calls):
    def make(name, size):
        def build():
            calls.append(name)
            return cq.Workplane().box(size, size, size)
        return build
    return make


def test_unchanged_sources_reuse_the_stored_part(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    cache = _cache(project)
    first = cache.get_or_build("arm", make("arm", 2))
    assert calls == ["arm"] and cache.misses == 1 and abs(first.Volume() - 8) < 1e-9
    assert cache.get_or_build("arm", make("arm", 2)) is first                     # same process: the same object
    brep = cache.path("arm")
    assert brep.is_file() and brep.with_suffix(".json").is_file()
    assert (cache.root / C.CACHE_TAG).read_text().startswith("Signature: 8a477f597d28d172789f06886806bc55")
    again = _cache(project)                                                       # a new run
    loaded = again.get_or_build("arm", make("arm", 2))
    assert calls == ["arm"] and again.hits == 1 and again.misses == 0
    assert abs(loaded.Volume() - 8) < 1e-9 and loaded.isValid()
    assert not [p for p in brep.parent.iterdir() if p.name.endswith(".tmp")]     # no temporary file left


def test_a_changed_source_rebuilds(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    _cache(project).get_or_build("arm", make("arm", 2))
    (project / "cad" / "parameters.json").write_text('{"w": 11}')
    _cache(project).get_or_build("arm", make("arm", 2))
    assert calls == ["arm", "arm"]


def test_per_part_deps_rebuild_only_their_part(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    arm_py, bucket_py = project / "cad" / "arm.py", project / "cad" / "bucket.py"
    builders = {"arm": (make("arm", 2), [arm_py]), "bucket": (make("bucket", 3), [bucket_py]), "pin": make("pin", 1)}
    parts = _cache(project).get_all(builders)
    assert list(parts) == ["arm", "bucket", "pin"] and calls == ["arm", "bucket", "pin"]
    arm_py.write_text("ARM = 2\n")
    parts = _cache(project).get_all(builders)
    assert calls == ["arm", "bucket", "pin", "arm"]
    assert abs(parts["bucket"].Volume() - 27) < 1e-9


def test_a_corrupt_brep_is_rebuilt(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    cache = _cache(project)
    cache.get_or_build("arm", make("arm", 2))
    brep = cache.path("arm")
    brep.write_text("not a brep")                                                 # damaged: the sha256 differs
    again = _cache(project)
    assert abs(again.get_or_build("arm", make("arm", 2)).Volume() - 8) < 1e-9
    assert calls == ["arm", "arm"] and again.rebuilt == {"arm": "brep sha256 differs"}
    record = json.loads(brep.with_suffix(".json").read_text())                   # damaged and its record rewritten
    brep.write_text("not a brep")
    record["brep_sha256"] = C._sha256(brep)
    brep.with_suffix(".json").write_text(json.dumps(record))
    third = _cache(project)
    third.get_or_build("arm", make("arm", 2))
    assert calls == ["arm", "arm", "arm"] and third.rebuilt == {"arm": "brep does not import"}
    brep.with_suffix(".json").write_text("{")                                     # unreadable record
    fourth = _cache(project)
    fourth.get_or_build("arm", make("arm", 2))
    assert fourth.rebuilt == {"arm": "record unreadable"} and len(calls) == 4
    _cache(project).get_or_build("arm", make("arm", 2))
    assert len(calls) == 4                                                        # the rebuilt part is reused


def test_a_volume_or_validity_mismatch_is_rebuilt(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    cache = _cache(project)
    cache.get_or_build("arm", make("arm", 2))
    brep = cache.path("arm")
    other = cq.Workplane().box(2, 2, 3).val()                                     # a different solid, sha matching
    other.exportBrep(str(brep))
    record = json.loads(brep.with_suffix(".json").read_text())
    record["brep_sha256"] = C._sha256(brep)
    brep.with_suffix(".json").write_text(json.dumps(record))
    again = _cache(project)
    assert abs(again.get_or_build("arm", make("arm", 2)).Volume() - 8) < 1e-9
    assert again.rebuilt == {"arm": "volume differs"} and calls == ["arm", "arm"]
    record = json.loads(brep.with_suffix(".json").read_text())
    record["valid"] = False
    brep.with_suffix(".json").write_text(json.dumps(record))
    third = _cache(project)
    third.get_or_build("arm", make("arm", 2))
    assert third.rebuilt == {"arm": "validity differs"} and len(calls) == 3


def test_clear_and_the_size_cap(project):
    cq = pytest.importorskip("cadquery")
    calls = []
    make = _builders(cq, calls)
    cache = _cache(project)
    cache.get_or_build("arm", make("arm", 2))
    old = cache.path("arm").parent
    os.utime(old, (1, 1))                                                         # long unused
    (project / "cad" / "common.py").write_text("W = 12\n")
    capped = _cache(project, max_bytes=1)                                         # smaller than any part
    capped.get_or_build("arm", make("arm", 2))
    assert not old.exists()                                                       # the old folder went
    assert capped.path("arm").is_file()                                           # this run's own stays
    assert capped.size() > 0 and capped.prune(0) == []
    (capped.root / "notes.txt").write_text("mine")
    capped.clear()
    assert not capped.path("arm").exists() and (capped.root / "notes.txt").is_file()
    assert not (capped.root / C.CACHE_TAG).exists()
    capped.get_or_build("arm", make("arm", 2))
    assert len(calls) == 3                                                        # cleared: built again


def test_a_builder_must_return_a_shape(project):
    pytest.importorskip("cadquery")
    with pytest.raises(TypeError, match="not a cadquery Shape"):
        _cache(project).get_or_build("arm", lambda: 42)


def test_the_cache_lives_out_of_exports_and_is_never_committed(project, monkeypatch):
    """The default root is beside the gates' pair cache, and any root ignores itself in git."""
    cq = pytest.importorskip("cadquery")
    assert C.DEFAULT_ROOT == Path(".cadagent-cache") / "parts" and PartCache().root == C.DEFAULT_ROOT
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(project), "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, env=env)
    cache = PartCache(project / "exports" / "anywhere", sources=[project / "cad" / "common.py"])
    cache.get_or_build("arm", lambda: cq.Workplane().box(1, 1, 1))
    status = subprocess.run(["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
                            check=True, capture_output=True, text=True, env=env).stdout
    assert "cad/common.py" in status and "anywhere" not in status
    assert (cache.root / ".gitignore").read_text() == C.GITIGNORE_TEXT


def test_clear_keeps_markers_it_did_not_write(project):
    cq = pytest.importorskip("cadquery")
    cache = _cache(project)
    cache.root.mkdir(parents=True)
    (cache.root / ".gitignore").write_text("*.brep\n")                           # the project's own
    cache.get_or_build("arm", lambda: cq.Workplane().box(1, 1, 1))
    assert (cache.root / ".gitignore").read_text() == "*.brep\n"                  # never overwritten
    cache.clear()
    assert (cache.root / ".gitignore").read_text() == "*.brep\n"
    assert not (cache.root / C.CACHE_TAG).exists() and not cache.path("arm").exists()
