"""Content hashes are bound to the platform that made them (#144): ``cadagent.review.evidence``.

``hash_platform`` names that platform and the geometry record carries it under ``hash``, a key every release leaves
out of the gates' digest, so recording it voids no verdict, under this release or an earlier one.
``geometry_identity`` is the optional platform-stable identity (volume, centre of mass, inertia, rounded, with its
tolerance), checked here against closed forms, against placement and against golden values that an x86-64 and an
aarch64 host both produced while their content hashes for the same solids differed. The tests without CadQuery run in
the core CI job.
"""

from __future__ import annotations

import copy
import math
import sys
import types

import pytest

from cadagent.review import evidence as ev
from cadagent.review.gates.verdict import VOLATILE_TOP, bind_inputs, geometry_digest, stale_reason, verdict

X86 = {"machine": "x86_64", "system": "Linux", "libc": "glibc 2.39", "ocp": "7.9.3.1",
       "ocp_package": "cadquery-ocp 7.9.3.1.1"}
ARM = dict(X86, machine="aarch64")


# ------------------------------------------------------------------------------------- the platform (no CadQuery)

def test_hash_platform_names_the_machine_and_the_ocp_build(monkeypatch):
    monkeypatch.setitem(sys.modules, "OCP", types.SimpleNamespace(__version__="7.9.3.1"))
    monkeypatch.setattr(ev.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(ev.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ev.platform, "libc_ver", lambda: ("glibc", "2.39"))
    found = {"cadquery-ocp-novtk": "7.9.3.1.1"}

    def version(name):
        if name not in found:
            raise ev.PackageNotFoundError(name)
        return found[name]

    monkeypatch.setattr(ev, "version", version)
    assert ev.hash_platform() == {"machine": "aarch64", "system": "Linux", "libc": "glibc 2.39", "ocp": "7.9.3.1",
                                  "ocp_package": "cadquery-ocp-novtk 7.9.3.1.1"}
    found.clear()                                           # a conda or source build: no distribution to name
    assert ev.hash_platform()["ocp_package"] == "unknown"
    monkeypatch.setitem(sys.modules, "OCP", None)            # no OCP at all: import fails
    assert ev.hash_platform()["ocp"] == "unknown"
    monkeypatch.setattr(ev.platform, "libc_ver", lambda: ("", ""))     # e.g. a musl or non-Linux system
    assert ev.hash_platform()["libc"] == "unknown"
    assert tuple(ev.hash_platform()) == ev.PLATFORM_KEYS


def test_a_geometry_record_says_where_its_hashes_were_made():
    assert ev.record_hash_platform({"hash": {"recipe": "r", "platform": X86}}) == X86
    for older in ({"hash": "r"}, {}, {"hash": {"recipe": "r"}}, None, "x"):     # before #144, or not a record
        assert ev.record_hash_platform(older) == {}


def test_the_note_says_when_two_platforms_differ(monkeypatch):
    monkeypatch.setattr(ev, "hash_platform", lambda: pytest.fail("the note must not ask this process"))
    assert ev.hash_platform_note(X86, dict(X86)) is None
    for legacy in (None, {}, "x86_64"):                       # a record written before hash_platform existed
        assert ev.hash_platform_note(legacy, X86) is None
        assert ev.hash_platform_note(X86, legacy) is None     # never falls back to the host running the check
    note = ev.hash_platform_note(ARM, X86)
    assert note.startswith("the recorded hashes were made on aarch64 Linux (glibc 2.39), OCP 7.9.3.1 "
                           "(cadquery-ocp 7.9.3.1.1) and the current ones on x86_64 Linux (glibc 2.39)")
    assert "need not be a change of geometry" in note
    assert ev.hash_platform_note(X86, dict(X86, ocp_package="unknown"))     # another OCP build counts too
    assert ev.hash_platform_note(X86, dict(X86, libc="glibc 2.35"))         # and another C library


# --------------------------------------------------------------- recording it changes no digest and voids no verdict

def _record(platform=None):
    """A geometry record as a toolkit before #144 wrote it (``hash`` the recipe string), or with ``platform``."""
    rec = {"schema": "cad-agent.dossier-geometry/1", "units": "mm", "hash": "recipe", "actor": "a",
           "parts": {"p": {"sha256": "a" * 64, "count": 1,
                           "instances": [{"key": "p", "sha256": "a" * 64, "volume_mm3": 1.0}]}},
           "cavities": {}, "joints": {}, "fasteners": {}, "assembly": {"steps": []}, "physical_fit_verified": False}
    if platform is not None:
        rec["hash"] = {"recipe": "recipe", "platform": platform}
    return rec


# VOLATILE_TOP before #144: what an earlier release leaves out of the digest. Nothing #144 records may be outside it.
EARLIER_VOLATILE_TOP = frozenset({"actor", "parameters", "shapes_dir", "out_dir", "hash"})


def test_the_platform_is_outside_the_geometry_digest_of_every_release():
    assert VOLATILE_TOP == EARLIER_VOLATILE_TOP           # no new key: an earlier release digests the record the same
    assert set(_record(X86)) == set(_record())             # the platform added no top-level key
    before = _record()                                     # written by a toolkit without hash_platform
    assert geometry_digest(_record(X86)) == geometry_digest(before) == geometry_digest(_record(ARM))
    v = bind_inputs(verdict("wall", [], assumptions=["a"]), before)
    assert stale_reason(v, _record(X86)) is None           # a rebuild on the new toolkit keeps the verdict current
    changed = _record(X86)
    changed["parts"]["p"]["instances"][0]["sha256"] = "b" * 64
    assert "1 shape(s) changed: p" in stale_reason(v, changed)   # the hashes themselves are still compared


# ------------------------------------------------------------------- comparing identities (hand-written records)

def _identity(**changes):
    rec = {"schema": ev.IDENTITY_SCHEMA, "volume_mm3": 6000.0, "centre_mm": [1.0, 2.0, 3.0],
           "inertia_mm5": [[650000.0, 0.0, 0.0], [0.0, 500000.0, 0.0], [0.0, 0.0, 250000.0]],
           "principal_mm5": [250000.0, 500000.0, 650000.0],
           "tolerance": {"relative": 1e-6, "volume_mm3": 0.006, "length_mm": 1.82e-05, "inertia_mm5": 0.65,
                         "principal_mm5": [0.25, 0.5, 0.65]},
           "method": ev.IDENTITY_METHOD}
    rec.update(changes)
    return rec


def test_identities_match_within_the_looser_tolerance():
    a = _identity()
    assert ev.identity_mismatches(a, copy.deepcopy(a)) == []
    assert ev.identity_mismatches(a, _identity(volume_mm3=6000.005)) == []          # inside 0.006
    far = ev.identity_mismatches(a, _identity(volume_mm3=6000.007, centre_mm=[1.0, 2.0, 3.0001]))
    assert far == ["volume_mm3: 6000.0 and 6000.007 differ by 0.007, more than 0.006",
                   "centre_mm[2]: 3.0 and 3.0001 differ by 0.0001, more than 1.82e-05"]
    loose = _identity(volume_mm3=6000.007, tolerance=dict(a["tolerance"], volume_mm3=0.06))
    assert ev.identity_mismatches(a, loose) == [] == ev.identity_mismatches(loose, a)
    turned = copy.deepcopy(a)
    turned["inertia_mm5"][0][1] = turned["inertia_mm5"][1][0] = 3.0     # same moments, other axes
    assert ev.identity_mismatches(a, turned) == ["inertia_mm5[0][1]: 0.0 and 3.0 differ by 3, more than 0.65"]
    small = copy.deepcopy(a)                               # each principal moment against its own tolerance
    small["principal_mm5"][0] = 250000.3
    assert ev.identity_mismatches(a, small) == ["principal_mm5[0]: 250000.0 and 250000.3 differ by 0.3, more than 0.25"]


@pytest.mark.parametrize("other, says", [
    ({"schema": "other"}, "not a cadagent.geometry-identity/1"),
    (_identity(centre_mm=[1.0, 2.0]), "not three numbers"),
    (_identity(inertia_mm5=[[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]), "not three numbers"),
    (_identity(tolerance={}), "malformed geometry identity"),
    (_identity(tolerance={**_identity()["tolerance"], "principal_mm5": [1.0]}), "not three numbers"),
    (_identity(volume_mm3="big"), "malformed geometry identity"),
    (_identity(volume_mm3=float("nan")), "volume_mm3"),
    ("not a record", "not a geometry identity"),
])
def test_identities_that_cannot_be_compared_say_why(other, says):
    out = ev.identity_mismatches(_identity(), other)
    assert out and says in out[0]


# --------------------------------------------------------------------------------------- the identity (CadQuery)

@pytest.fixture
def cq():
    return pytest.importorskip("cadquery")


def _solids(cq):
    """Public test solids whose content hashes differ between x86-64 and aarch64 (cadquery-ocp 7.9.3.1.1)."""
    plate = (cq.Workplane().box(60, 40, 6).edges("|Z").fillet(5)
             .faces(">Z").workplane().rarray(40, 20, 2, 2).hole(4.2).edges(">Z").fillet(0.8).val())
    ball = (cq.Workplane().sphere(12).cut(cq.Workplane("YZ").circle(4).extrude(30, both=True))
            .cut(cq.Workplane("XZ").circle(3).extrude(30, both=True)).val())
    return {"plate": plate,
            "ball_placed": ball.rotate((0, 0, 0), (1, 2, 3), 37.5).translate((123.4, -56.7, 89.01))}


# geometry_identity of _solids() on an x86-64 and an aarch64 host, 2026-11-01, cadquery 2.8.0 and cadquery-ocp
# 7.9.3.1.1 from PyPI on both: the same values on both, while both solids' content hashes differed between them.
# The per-moment tolerances (principal_mm5) came later; they round these moments to the same places as before.
GOLDEN = {
    "plate": {"volume_mm3": 13904.731, "centre_mm": [0.0, 0.0, -0.006901],
              "inertia_mm5": [[1873710.9, 0.0, 0.0], [0.0, 4103999.3, 0.0], [0.0, 0.0, 5894622.4]],
              "principal_mm5": [1873710.9, 4103999.3, 5894622.4],
              "tolerance": {"relative": 1e-06, "volume_mm3": 0.0139, "length_mm": 2.4e-05, "inertia_mm5": 5.89,
                            "principal_mm5": [1.87, 4.1, 5.89]}},
    "ball_placed": {"volume_mm3": 5607.0538, "centre_mm": [123.4, -56.7, 89.01],
                    "inertia_mm5": [[365766.36, 8930.82, -14356.27], [8930.82, 362083.23, -837.04],
                                    [-14356.27, -837.04, 333670.02]],
                    "principal_mm5": [328006.93, 357031.87, 376480.82],
                    "tolerance": {"relative": 1e-06, "volume_mm3": 0.00561, "length_mm": 1.78e-05,
                                  "inertia_mm5": 0.376, "principal_mm5": [0.328, 0.357, 0.376]}},
}


def test_identity_of_closed_forms(cq):
    a, b, c = 10.0, 20.0, 30.0
    box = ev.geometry_identity(cq.Workplane().box(a, b, c).val().translate(cq.Vector(5, -7, 11)))
    m = a * b * c
    assert box["schema"] == ev.IDENTITY_SCHEMA and box["volume_mm3"] == pytest.approx(m, rel=1e-9)
    assert box["centre_mm"] == pytest.approx([5, -7, 11], abs=1e-9)
    assert box["inertia_mm5"] == [[pytest.approx(m * (b * b + c * c) / 12, rel=1e-9), 0.0, 0.0],
                                  [0.0, pytest.approx(m * (a * a + c * c) / 12, rel=1e-9), 0.0],
                                  [0.0, 0.0, pytest.approx(m * (a * a + b * b) / 12, rel=1e-9)]]
    assert box["principal_mm5"] == sorted(box["principal_mm5"])
    assert box["tolerance"] == {"relative": 1e-6, "volume_mm3": 0.006, "length_mm": 1.82e-05, "inertia_mm5": 0.65,
                                "principal_mm5": [0.25, 0.5, 0.65]}
    r, h = 4.0, 25.0
    cyl = ev.geometry_identity(cq.Workplane().circle(r).extrude(h).val())
    m = math.pi * r * r * h
    assert cyl["volume_mm3"] == pytest.approx(m, rel=1e-6)
    assert cyl["centre_mm"] == pytest.approx([0, 0, h / 2], abs=1e-6)
    assert cyl["principal_mm5"] == pytest.approx([m * r * r / 2, m * (3 * r * r + h * h) / 12,
                                                  m * (3 * r * r + h * h) / 12], rel=1e-6)
    r = 7.0
    sphere = ev.geometry_identity(cq.Workplane().sphere(r).val())
    m = 4 / 3 * math.pi * r ** 3
    assert sphere["volume_mm3"] == pytest.approx(m, rel=1e-6)
    assert sphere["principal_mm5"] == pytest.approx([0.4 * m * r * r] * 3, rel=1e-6)


def test_identity_moves_with_placement_and_geometry_but_not_with_noise(cq):
    shape = cq.Workplane().box(10, 20, 30).edges("|Z").fillet(2).val()
    here = ev.geometry_identity(shape)
    nudge = lambda dx: ev.geometry_identity(shape.translate(cq.Vector(dx, 0, 0)))
    assert ev.identity_mismatches(here, nudge(1e-7)) == []            # far below the 1e-6 relative tolerance
    assert [m.split(":")[0] for m in ev.identity_mismatches(here, nudge(1e-3))] == ["centre_mm[0]"]
    turned = ev.geometry_identity(shape.rotate((0, 0, 0), (0, 0, 1), 30))
    assert {m.split(":")[0] for m in ev.identity_mismatches(here, turned)} == \
        {"inertia_mm5[0][0]", "inertia_mm5[0][1]", "inertia_mm5[1][1]"}         # same moments, turned axes
    longer = ev.geometry_identity(cq.Workplane().box(10, 20, 30.01).edges("|Z").fillet(2).val())
    assert "volume_mm3" in ev.identity_mismatches(here, longer)[0]


def test_a_slender_part_is_told_apart_by_its_own_small_moment(cq):
    """A 1 x 1 x 1000 mm square rod and a round one of the same area: the same volume and centre, long moments
    5e-8 apart (inside their tolerance), the moment about the axis 4.5 % apart. Compared against a tolerance set by
    the largest moment (83 mm^5, as every inertia term was before), they would match; that moment's own tolerance is
    the floor, a thousandth of that (0.083 mm^5), and tells them apart."""
    square = ev.geometry_identity(cq.Workplane().box(1, 1, 1000).val())
    round_ = ev.geometry_identity(cq.Workplane().circle(math.sqrt(1 / math.pi)).extrude(1000)
                                  .translate((0, 0, -500)).val())
    assert square["principal_mm5"][0] == pytest.approx(1000 / 6, abs=1e-3)          # m a^2 / 6, a = 1 mm
    assert round_["principal_mm5"][0] == pytest.approx(1000 / (2 * math.pi), abs=1e-3)   # m r^2 / 2
    assert [m.split(":")[0] for m in ev.identity_mismatches(square, round_)] == ["principal_mm5[0]"]
    t = square["tolerance"]
    assert t["inertia_mm5"] == 83.3 and t["principal_mm5"] == [0.0833, 83.3, 83.3]      # the floor, then its own
    box = ev.geometry_identity(cq.Workplane().box(10, 20, 30).val())     # moments within 1000x: each its own
    assert box["tolerance"]["principal_mm5"] == [round(1e-6 * v, 9) for v in (250000, 500000, 650000)]


def test_identity_survives_a_read_back_that_need_not_keep_the_hash(cq, tmp_path):
    """A shape read back from its BREP or STEP is not guaranteed to hash the same (shape_content_hash's note); its
    identity matches. This stands in for another platform's last-digit differences."""
    for name, shape in _solids(cq).items():
        brep, step = tmp_path / f"{name}.brep", tmp_path / f"{name}.step"
        shape.exportBrep(str(brep))
        cq.exporters.export(cq.Workplane(obj=shape), str(step), exportType="STEP")
        here = ev.geometry_identity(shape)
        for again in (cq.Shape.importBrep(str(brep)), cq.importers.importStep(str(step)).val()):
            assert ev.identity_mismatches(here, ev.geometry_identity(again)) == [], name


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_identity_matches_the_values_two_architectures_made(cq, name):
    got = ev.geometry_identity(_solids(cq)[name])
    golden = dict(GOLDEN[name], schema=ev.IDENTITY_SCHEMA, method=ev.IDENTITY_METHOD)
    assert ev.identity_mismatches(golden, got) == []


def test_identity_needs_a_solid_and_a_sane_tolerance(cq):
    face = cq.Workplane().rect(10, 10).val()
    with pytest.raises(ValueError, match="positive volume"):
        ev.geometry_identity(face)
    box = cq.Workplane().box(1, 1, 1).val()
    for bad in (0, -1e-6, 1, "1e-6", float("nan")):
        with pytest.raises(ValueError, match="rel_tol"):
            ev.geometry_identity(box, rel_tol=bad)
    loose = ev.geometry_identity(box, rel_tol=1e-3)
    assert loose["tolerance"]["relative"] == 1e-3 and loose["tolerance"]["volume_mm3"] == 1e-3
