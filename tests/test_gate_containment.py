"""Containment gate (T5): contents inside their container's registered cavity, per pose.

The plan's tests (docs/design-process-plan.md §4.3): 40 balls in a cone pass; one moved 5 mm
through the wall fails with the right volume outside; a ball tangent to the wall passes; a
declaration with no registered cavity is a lint finding; a mesh-only item takes the sample-only
path. Plus: a ball 0.5 mm through a curved wall, against a Monte Carlo estimate of its volume
outside; wall piercing, interpenetration, count, support, poses, the cache and the verdict file.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.gates import Assembly, PairCache, Tolerances, relate_pair
from cadagent.gates.containment import Contains, containment_gate, contains_declarations, instances

try:
    import cadquery as cq
except ImportError:  # core CI: the declaration and lint-path tests still run
    cq = None
needs_cad = pytest.mark.skipif(cq is None, reason="needs cadquery (the cad extra)")

# A cone cavity opening upwards: radius R0 at the floor (z=0), growing SLOPE per mm, H tall.
R0, SLOPE, H, R = 20.0, 2.0 / 3.0, 60.0, 4.0
COS = 1.0 / math.hypot(1.0, SLOPE)          # cos of the wall's angle from vertical
SIN = SLOPE * COS


def ball(r, centre):
    """A full sphere (cq.Solid.makeSphere defaults to a hemisphere)."""
    return cq.Solid.makeSphere(r, cq.Vector(*centre), angleDegrees1=-90)


def cone_cavity():
    return cq.Solid.makeCone(R0, R0 + SLOPE * H, H)


def cone_hopper():
    """The container: a block around the cone with the cone removed (cavity and container share the wall)."""
    return cq.Solid.makeCylinder(R0 + SLOPE * H + 5, H + 3, cq.Vector(0, 0, -3)).cut(cone_cavity()).clean()


def cone_rho_tangent(z, r=R):
    """Radial position at which a ball of radius r centred at height z touches the cone wall."""
    return R0 + SLOPE * z - r / COS


def forty_centres():
    """Columns of two or three balls standing on the cone floor, 0.2 mm apart sideways: 40 balls."""
    s = 2 * R + 0.2
    floor = [(s * (i + 0.5 * (j % 2)), s * j * math.sqrt(3) / 2) for j in range(-4, 5) for i in range(-4, 5)]
    floor = sorted((p for p in floor if math.hypot(*p) <= cone_rho_tangent(R) - 0.05),
                   key=lambda p: (round(math.hypot(*p), 6), p))
    cols = [(x, y, R) for x, y in floor] + [(x, y, 3 * R) for x, y in floor]
    cols += [(x, y, 5 * R) for x, y in floor[:40 - len(cols)]]
    assert len(cols) == 40, len(cols)
    return cols


def cone_assembly(centres, cavity=True, meshes=None):
    asm = Assembly()
    asm.add("hopper", cone_hopper())
    if cavity:
        asm.add_cavity("cone", cone_cavity(), part="hopper")
    for i, c in enumerate(centres):
        asm.add(f"ball#{i}", ball(R, c))
    return asm


CONE = {"container": "hopper", "cavity": "cone", "what": "ball"}


def by_id(v):
    return {c["id"]: c for c in v["checks"]}


def mc_outside(centre, r, inside, n=400_000, seed=1):
    """Monte Carlo volume of a ball outside a region (``inside(points) -> bool array``), and its standard error."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(-r, r, (n, 3))
    p = p[(p ** 2).sum(axis=1) <= r * r] + np.asarray(centre)
    frac = float((~inside(p)).mean())
    vol = 4 / 3 * math.pi * r ** 3
    return vol * frac, vol * math.sqrt(frac * (1 - frac) / len(p))


def in_cone(p):
    return (p[:, 2] >= 0) & (p[:, 2] <= H) & (np.hypot(p[:, 0], p[:, 1]) <= R0 + SLOPE * p[:, 2])


# ----------------------------------------------------------------------------- no CAD kernel needed

def test_declarations_coerce_from_mappings_dataclasses_and_dossier_cards():
    d = Contains.coerce({"container": "hopper", "cavity": "hopper_cavity", "what": "ball", "count": 8, "free": True})
    assert d == Contains("hopper", "hopper_cavity", "ball", 8, True)
    card = SimpleNamespace(contains=[SimpleNamespace(what="ball", count=40, cavity="cone", free=True)])
    assert contains_declarations(SimpleNamespace(parts={"hopper": card})) == [Contains("hopper", "cone", "ball", 40,
                                                                                        True)]
    with pytest.raises(ValueError):
        Contains("hopper", "cone", "")
    with pytest.raises(ValueError):
        Contains("hopper", "cone", "ball", count=-1)


def test_instances_are_the_part_or_its_numbered_keys_in_index_order():
    names = ["ball#10", "ball#2", "ball", "ballast", "ball#x", "big_ball#1", "screw_0"]
    assert instances(names, "ball") == ["ball", "ball#2", "ball#10"]
    assert instances(["a.b#0", "aXb#0"], "a.b") == ["a.b#0"]


def test_a_declaration_without_a_registered_cavity_is_a_lint_finding_without_the_kernel():
    v = containment_gate(Assembly(), [{"container": "hopper", "cavity": "derived", "what": "ball", "count": 2}])
    assert v["pass"] is False
    lint = by_id(v)["contains:derived:ball:cavity"]
    assert lint["status"] == "fail" and lint["evidence"]["lint"] == "unknown-cavity" and "derived" in lint["message"]
    assert by_id(v)["contains:derived:ball:count"]["status"] == "fail"
    v = containment_gate(Assembly(), [{"container": "hopper", "what": "ball"}])
    assert by_id(v)["contains:?:ball:cavity"]["evidence"]["lint"] == "unknown-cavity"


def test_bad_options_are_refused():
    with pytest.raises(ValueError):
        containment_gate(Assembly(), [CONE], support="sometimes")
    with pytest.raises(ValueError):
        containment_gate(Assembly(), [CONE], exclusions=[{"parts": ["ball#0"], "reason": "x"}])


# ----------------------------------------------------------------------------- the plan's tests

@pytest.fixture(scope="module")
def forty():
    return forty_centres()


@needs_cad
def test_forty_balls_in_a_cone_pass_with_no_finding(forty):
    v = containment_gate(cone_assembly(forty), [{**CONE, "count": 40}])
    assert v["pass"] is True and v["findings"] == [], v["findings"]
    checks = by_id(v)
    assert sum(1 for k in checks if k.endswith(":inside")) == 40
    assert checks["contains:cone:ball:count"]["evidence"] == {"declared": 40, "found": 40, "brep": 40, "mesh": 0}
    assert checks["contains:cone:ball:support"]["evidence"]["unsupported"] == []
    assert v["declarations"][0]["inside"] == 40 and v["physical_fit_verified"] is False


@needs_cad
def test_a_ball_moved_5_mm_through_the_cone_wall_fails_with_the_right_volume_outside(forty):
    centres = list(forty)
    i = max(range(40), key=lambda k: (forty[k][2], math.hypot(*forty[k][:2])))   # an outer ball, top layer
    x, y, z = centres[i]
    phi = math.atan2(y, x)
    rho = cone_rho_tangent(z)                                    # put it on the wall first, then 5 mm out
    n = (COS * math.cos(phi), COS * math.sin(phi), -SIN)         # the wall's outward normal
    c = tuple(p + 5.0 * d for p, d in zip((rho * math.cos(phi), rho * math.sin(phi), z), n))
    centres[i] = c
    v = containment_gate(cone_assembly(centres), [{**CONE, "count": 40}])
    assert v["pass"] is False
    f = by_id(v)[f"contains:cone:ball#{i}:inside"]
    assert f["status"] == "fail" and f["parts"] == [f"ball#{i}", "hopper"]
    expected, se = mc_outside(c, R, in_cone)
    assert f["evidence"]["outside_mm3"] == pytest.approx(expected, rel=0.02, abs=4 * se)
    assert f["evidence"]["depth_mm"] == pytest.approx(5.0, abs=0.02)   # the ball's far pole, 5 mm past the wall
    assert by_id(v)[f"contains:cone:ball#{i}:wall"]["status"] == "fail"
    others = [x for x in v["findings"] if f"ball#{i}" not in x.get("parts", [])]
    assert all(x["id"].endswith(":support") for x in others), others


@needs_cad
@pytest.mark.parametrize("where", ["cone wall", "cone floor", "floor and wall"])
def test_a_ball_tangent_to_the_cavity_reads_contained(where):
    if where == "cone wall":
        z, phi = 30.0, 0.3
        c = (cone_rho_tangent(z) * math.cos(phi), cone_rho_tangent(z) * math.sin(phi), z)
    elif where == "cone floor":
        c = (0.0, 0.0, R)
    else:                                   # in the corner: on the floor and against the wall
        c = (cone_rho_tangent(R) * math.cos(1.0), cone_rho_tangent(R) * math.sin(1.0), R)
    asm = cone_assembly([c])
    rel = relate_pair(asm, "ball#0", "cone")
    assert rel.state == "contains" and rel.contained == "a_in_b" and rel.a_outside_b_mm3 <= 1e-3
    assert rel.wall_mm == pytest.approx(0.0, abs=1e-6)
    v = containment_gate(asm, [{**CONE, "count": 1}], support="fail")
    assert v["pass"] is True and v["findings"] == [], v["findings"]
    checks = by_id(v)
    assert checks["contains:cone:ball#0:wall"]["evidence"]["relation"]["state"] == "touching"
    probe = checks["contains:cone:ball#0:inside"]["evidence"]["probe"]
    assert probe["probe_outside"] == 0 and probe["probe_points"] > 100


@needs_cad
def test_a_shallow_crossing_the_boolean_misses_is_caught_by_the_contact_probe():
    """A ball pushed 0.03-0.07 mm through the cone wall: OCCT's Common/Cut read 0 mm3 outside at some
    positions (seen at this one), so the vertex probe has to catch it."""
    z, phi = 30.0, 0.3
    rho = cone_rho_tangent(z)
    for dz in (0.05, 0.12):                           # down by dz = dz * SIN into the wall
        c = (rho * math.cos(phi), rho * math.sin(phi), z - dz)
        v = containment_gate(cone_assembly([c]), [CONE], support="off")
        f = by_id(v)["contains:cone:ball#0:inside"]
        assert f["status"] == "fail", f
        assert f["evidence"]["depth_mm"] == pytest.approx(dz * SIN, abs=0.004)
    off = containment_gate(cone_assembly([c]), [CONE], support="off", probe=False)
    assert off["limits"]["contact_probe"] is False


@needs_cad
def test_a_ball_half_a_millimetre_through_a_curved_wall_is_caught_with_its_volume():
    rc, r = 30.0, 5.0
    cavity = cq.Solid.makeCylinder(rc, 40)
    tube = cq.Solid.makeCylinder(rc + 3, 43, cq.Vector(0, 0, -3)).cut(cavity).clean()
    phi = 0.7
    rho = rc - r + 0.5                                         # its surface 0.5 mm past the wall
    c = (rho * math.cos(phi), rho * math.sin(phi), 20.0)
    asm = Assembly()
    asm.add("tube", tube)
    asm.add_cavity("bore", cavity, part="tube")
    asm.add("ball", ball(r, c))
    v = containment_gate(asm, [{"container": "tube", "cavity": "bore", "what": "ball", "count": 1}])
    f = by_id(v)["contains:bore:ball:inside"]
    assert v["pass"] is False and f["status"] == "fail"

    def in_bore(p):
        return (np.hypot(p[:, 0], p[:, 1]) <= rc) & (p[:, 2] >= 0) & (p[:, 2] <= 40)
    # sample only the slab of the ball the cap can be in (local frame: x along the ball's radial direction)
    n = 1_000_000
    rng = np.random.default_rng(3)
    lo, hi = np.array([rc - 0.1 - rho, -r, -r]), np.array([r, r, r])
    pts = rng.uniform(lo, hi, (n, 3))
    pts = pts[(pts ** 2).sum(axis=1) <= r * r]
    world = np.column_stack([pts[:, 0] * math.cos(phi) - pts[:, 1] * math.sin(phi),
                             pts[:, 0] * math.sin(phi) + pts[:, 1] * math.cos(phi), pts[:, 2]]) + np.asarray(c)
    hits = int((~in_bore(world)).sum())
    estimate = float(np.prod(hi - lo)) * hits / n
    se = estimate / math.sqrt(hits)
    assert se / estimate < 0.01
    assert 3.0 < estimate < 4.5                                  # about a 0.5 mm cap of a 5 mm ball
    assert f["evidence"]["outside_mm3"] == pytest.approx(estimate, rel=0.05)
    assert f["evidence"]["depth_mm"] == pytest.approx(0.5, abs=0.01)
    assert by_id(v)["contains:bore:ball:wall"]["status"] == "fail"


@needs_cad
def test_a_registered_cavity_on_another_part_is_a_lint_finding():
    asm = cone_assembly([(0, 0, R)])
    asm.add("lid", cq.Solid.makeBox(10, 10, 2, cq.Vector(0, 0, 70)))
    v = containment_gate(asm, [{"container": "lid", "cavity": "cone", "what": "ball"}])
    f = by_id(v)["contains:cone:ball:cavity"]
    assert f["status"] == "fail" and f["evidence"]["lint"] == "cavity-wrong-part"


@needs_cad
def test_mesh_only_items_take_the_sample_only_path():
    trimesh = pytest.importorskip("trimesh")
    asm = cone_assembly([(0, 0, R)])
    inside = trimesh.creation.icosphere(subdivisions=3, radius=R).apply_translation((12, 0, R + 1))
    rho = cone_rho_tangent(30) + 2.0                          # 2 mm through the wall
    escaped = trimesh.creation.icosphere(subdivisions=3, radius=R).apply_translation((rho, 0, 30))
    v = containment_gate(asm, [{**CONE, "count": 3}], meshes={"ball#1": inside, "ball#2": escaped})
    checks = by_id(v)
    assert checks["contains:cone:ball:count"]["evidence"] == {"declared": 3, "found": 3, "brep": 1, "mesh": 2}
    ok, bad = checks["contains:cone:ball#1:inside"], checks["contains:cone:ball#2:inside"]
    assert ok["status"] == "pass" and ok["evidence"]["method"] == "sample-only" and "sample-only" in ok["message"]
    assert bad["status"] == "fail" and bad["evidence"]["method"] == "sample-only"
    assert bad["evidence"]["depth_mm"] == pytest.approx(2.0 * COS, abs=0.05)   # 2 mm radially
    assert bad["evidence"]["outside_mm3"] > 3 * bad["evidence"]["outside_se_mm3"] > 0
    assert checks["contains:cone:ball#2:wall"]["status"] == "fail"
    assert checks["contains:cone:ball#1:wall"]["status"] == "pass"
    # mesh items are left out of the pairwise checks: only the one B-rep ball, so no interpenetration check
    assert "contains:cone:ball:interpenetration" not in checks
    assert any("sample-only" in a for a in v["assumptions"])


# ----------------------------------------------------------------------------- the other findings

@needs_cad
def test_a_cavity_drawn_over_the_wall_still_fails_on_the_wall_check():
    """The inverse case: inside the (wrong) cavity, but in the container's material."""
    shell = cq.Solid.makeBox(40, 40, 30).cut(cq.Solid.makeBox(35.2, 35.2, 30, cq.Vector(2.4, 2.4, 2.4)))
    asm = Assembly()
    asm.add("box", shell)
    asm.add_cavity("too_big", cq.Solid.makeBox(40, 40, 30), part="box")      # includes the walls
    asm.add("ball", ball(5, (5.5, 20, 7.4)))                                  # 2.6 mm into the -X wall
    v = containment_gate(asm, [{"container": "box", "cavity": "too_big", "what": "ball"}], support="off")
    checks = by_id(v)
    assert checks["contains:too_big:ball:inside"]["status"] == "pass"
    wall = checks["contains:too_big:ball:wall"]
    assert wall["status"] == "fail" and wall["evidence"]["relation"]["overlap_mm3"] > 10
    v = containment_gate(asm, [{"container": "box", "cavity": "too_big", "what": "ball"}], support="off",
                         exclusions=[{"parts": ["ball", "box"], "reason": "test: a declared intended overlap"}])
    assert v["pass"] is True and v["exclusions"][0]["reason"].startswith("test")


@needs_cad
def test_interpenetrating_balls_are_reported_per_pair_with_their_overlap():
    centres = [(0, 0, R), (2 * R - 1.0, 0, R), (-12, 0, R)]          # ball#0 and ball#1 share 1 mm
    v = containment_gate(cone_assembly(centres), [CONE])
    f = by_id(v)["contains:cone:ball:interpenetration"]
    assert f["status"] == "fail" and f["parts"] == ["ball#0", "ball#1"]
    (row,) = f["evidence"]["overlaps"]
    dist = 2 * R - 1.0
    lens = math.pi * (4 * R + dist) * (2 * R - dist) ** 2 / 12
    assert row["pair"] == ["ball#0", "ball#1"] and row["overlap_mm3"] == pytest.approx(lens, rel=1e-4)


@needs_cad
def test_count_mismatch_is_a_finding():
    v = containment_gate(cone_assembly([(0, 0, R), (10, 0, R)]), [{**CONE, "count": 3}])
    f = by_id(v)["contains:cone:ball:count"]
    assert f["status"] == "fail" and f["evidence"]["found"] == 2 and "3 declared" in f["message"]


@needs_cad
def test_support_is_reported_and_failing_on_it_is_configurable():
    centres = [(0, 0, R), (0, 0, 3 * R), (12, 0, R + 1.0), (12, 0, 3 * R + 1.0)]   # a column on the floor;
    asm = cone_assembly(centres)                                                   # one hovering 1 mm, plus
    v = containment_gate(asm, [CONE])                                              # the ball resting on it
    f = by_id(v)["contains:cone:ball:support"]
    assert v["pass"] is True and f["status"] == "warn"
    assert f["evidence"]["unsupported"] == ["ball#2", "ball#3"] and f["parts"] == ["ball#2", "ball#3"]
    assert f["evidence"]["rests_on"] == {"ball#1": ["ball#0"], "ball#3": ["ball#2"]}
    assert f["evidence"]["on_cavity"] == ["ball#0"]
    strict = containment_gate(asm, [CONE], support="fail")
    assert strict["pass"] is False and by_id(strict)["contains:cone:ball:support"]["status"] == "fail"
    off = containment_gate(asm, [CONE], support="off")
    assert off["pass"] is True and "contains:cone:ball:support" not in by_id(off)
    sideways = containment_gate(asm, [CONE], down=(1, 0, 0))     # "down" is +X: nothing rests that way
    assert set(by_id(sideways)["contains:cone:ball:support"]["evidence"]["unsupported"]) >= {"ball#0", "ball#1"}


@needs_cad
def test_a_container_that_moves_away_from_its_contents_is_caught_in_that_pose():
    """The incident's shape: the container is posed (a turret turned), its contents are modelled in place."""
    shell = cq.Solid.makeBox(40, 40, 30, cq.Vector(20, -20, 0)).cut(
        cq.Solid.makeBox(35.2, 35.2, 30, cq.Vector(22.4, -17.6, 2.4)))
    asm = Assembly()
    asm.add("hopper", shell, body="turret")
    asm.add_cavity("void", cq.Solid.makeBox(35.2, 35.2, 30, cq.Vector(22.4, -17.6, 2.4)), part="hopper")
    for i, x in enumerate((30.0, 42.0)):
        asm.add(f"ball#{i}", ball(5, (x, 0, 7.4)))
    turned = cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90)
    v = containment_gate(asm, [{"container": "hopper", "cavity": "void", "what": "ball", "count": 2}],
                         poses={"home": {}, "turned": {"turret": turned}})
    checks = by_id(v)
    assert checks["home/contains:void:ball#0:inside"]["status"] == "pass"
    gone = checks["turned/contains:void:ball#0:inside"]
    assert gone["status"] == "fail" and "wholly outside" in gone["message"]
    assert gone["evidence"]["outside_mm3"] == pytest.approx(4 / 3 * math.pi * 125, rel=1e-6)
    assert [d["pose"] for d in v["declarations"]] == ["home", "turned"]
    assert [d["status"] for d in v["declarations"]] == ["pass", "fail"]
    assert v["limits"]["poses"]["home"] == {} and set(v["limits"]["poses"]["turned"]) == {"turret"}


@needs_cad
def test_the_cache_makes_a_rerun_free_and_identical(tmp_path, forty):
    cache = PairCache(tmp_path / "cache")
    asm = cone_assembly(forty[:6])
    first = containment_gate(asm, [CONE], cache=cache)
    misses = cache.misses
    second = containment_gate(cone_assembly(forty[:6]), [CONE], cache=PairCache(tmp_path / "cache"))
    strip = lambda v: json.dumps(v, sort_keys=True).replace('"cached": true', '"cached": false')  # noqa: E731
    assert strip(first) == strip(second) and misses > 0


@needs_cad
def test_the_verdict_file_is_written_and_stable(tmp_path):
    asm = cone_assembly([(0, 0, R)])
    a = tmp_path / "a" / "containment.json"
    b = tmp_path / "b" / "containment.json"
    containment_gate(asm, [CONE], out=a, tol=Tolerances())
    containment_gate(asm, [CONE], out=b)
    data = json.loads(a.read_text())
    assert a.read_bytes() == b.read_bytes()
    assert data["schema"] == "cadagent.gate/1" and data["gate"] == "containment" and data["pass"] is True
    assert data["limits"]["contain_mm3"] == 1e-3 and data["assumptions"]
