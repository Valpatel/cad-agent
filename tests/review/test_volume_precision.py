"""Public analytic controls for volume cancellation, topology and uncertain decisions."""

import math

import pytest

from cadagent.review.gates import relations as rel

cq = pytest.importorskip("cadquery")


def curved_solid(thickness=None):
    """Revolve r(t)=1+6t-3t², z(t)=10t; optional inner radius r(t)-d.

    Analytic volumes and first moments come from integrating these polynomials,
    independently of any BREP mass calculation. Asymmetry makes CGFlag observable.
    """
    v = cq.Vector
    outer = cq.Edge.makeBezier([v(1, 0, 0), v(4, 0, 5), v(4, 0, 10)])
    if thickness is None:
        edges = [cq.Edge.makeLine(v(), v(1, 0, 0)), outer,
                 cq.Edge.makeLine(v(4, 0, 10), v(0, 0, 10)),
                 cq.Edge.makeLine(v(0, 0, 10), v())]
        volume, z = 98 * math.pi, 45 / 7
    else:
        d = thickness
        inner = cq.Edge.makeBezier([v(4-d, 0, 10), v(4-d, 0, 5), v(1-d, 0, 0)])
        edges = [outer, cq.Edge.makeLine(v(4, 0, 10), v(4-d, 0, 10)), inner,
                 cq.Edge.makeLine(v(1-d, 0, 0), v(1, 0, 0))]
        volume = 10 * math.pi * (6*d - d*d)
        z = 10 * (3.5 - 0.5*d) / (6 - d)
    return cq.Solid.revolve(cq.Wire.assembleEdges(edges), [], 360, v(), v(0, 0, 1)), volume, z


@pytest.mark.parametrize("thickness", [None, 0.01, 0.00001])
@pytest.mark.parametrize("moved", [False, True])
def test_curved_solid_and_thin_shell_match_analytic_volume(thickness, moved):
    shape, volume, z = curved_solid(thickness)
    expected = cq.Vector(0, 0, z)
    if moved:
        loc = cq.Location(cq.Vector(1000, -2000, 3000), cq.Vector(1, 2, 3), 31)
        shape = shape.moved(loc)
        expected = expected.transform(cq.Matrix(loc.wrapped.Transformation()))
    measured = rel._measure_volume(shape.wrapped)
    assert abs(measured.value - volume) <= measured.error + 1e-9
    assert measured.value == pytest.approx(volume, rel=1e-7, abs=1e-9)
    assert measured.error < 0.001  # the estimate still resolves the existing overlap threshold
    witness = rel._overlap_centroid(shape.wrapped)
    if "overlap_centroid" in witness:
        assert witness["overlap_centroid"] == pytest.approx(expected.toTuple(), abs=1e-5)
    else:
        assert "refinements disagree" in witness["overlap_centroid_estimate"]["unavailable"]


def test_optional_centroid_is_computed_and_unconverged_witness_is_omitted():
    # Asymmetric polyhedron: an 8mm³ cube plus a 1mm³ cube, with independent first moments.
    shape = cq.Solid.makeBox(2, 2, 2).fuse(cq.Solid.makeBox(1, 1, 1, cq.Vector(2, 0, 0)))
    expected = ((8 + 2.5) / 9, (8 + 0.5) / 9, (8 + 0.5) / 9)
    witness = rel._overlap_centroid(shape.wrapped)
    assert witness["overlap_centroid"] == pytest.approx(expected, abs=1e-6)
    curved, _, _ = curved_solid()
    witness = rel._overlap_centroid(curved.wrapped)
    assert "overlap_centroid" not in witness
    assert witness["overlap_centroid_estimate"]["refinement_delta_mm"] > 1e-6


def test_inverted_but_topologically_valid_solid_cannot_pass_broad_phase():
    inverted = cq.Shape.cast(cq.Solid.makeBox(2, 2, 2).wrapped.Reversed())
    assert inverted.isValid()
    with pytest.raises(ValueError, match="inverted, unbounded"):
        rel.Assembly({"inverted": inverted, "far": cq.Solid.makeBox(1, 1, 1, cq.Vector(100, 0, 0))})
    result = rel.relate(inverted, cq.Solid.makeBox(1, 1, 1, cq.Vector(4, 0, 0)))
    assert result.state == "unknown" and "inverted, unbounded" in result.error


def open_solid():
    box = cq.Solid.makeBox(2, 2, 2)
    return cq.Solid.makeSolid(cq.Shell.makeShell(box.Faces()[:-1]))


def test_open_solid_is_rejected_before_broad_phase_or_trusted_volume_can_pass():
    broken = open_solid()
    assert not broken.isValid()
    with pytest.raises(ValueError, match="invalid BREP"):
        rel.Assembly({"broken": broken, "far": cq.Solid.makeBox(1, 1, 1, cq.Vector(100, 0, 0))})
    for supplied in (None, (8.0, 1.0)):
        result = rel.relate(broken, cq.Solid.makeBox(1, 1, 1, cq.Vector(4, 0, 0)), volumes=supplied)
        assert result.state == "unknown" and "invalid BREP" in result.error
    with pytest.raises(ValueError, match="invalid BREP"):
        rel._measure_volume(broken.wrapped)


def test_invalid_boolean_result_is_unknown(monkeypatch):
    real = rel._boolean
    broken = open_solid().wrapped
    monkeypatch.setattr(rel, "_boolean", lambda kind, a, b: broken if kind == "common" else real(kind, a, b))
    result = rel.relate(cq.Solid.makeBox(2, 2, 2), cq.Solid.makeBox(2, 2, 2, cq.Vector(1, 0, 0)))
    assert result.state == "unknown" and "invalid BREP" in result.error


def test_free_faces_cannot_pollute_volume_and_empty_or_surface_common_has_zero_volume():
    box = cq.Solid.makeBox(2, 2, 2)
    face = cq.Face.makePlane(3, 3, cq.Vector(20, 0, 0))
    mixed = cq.Compound.makeCompound([box, face])
    assert mixed.isValid()  # validity alone does not guarantee a closed surface integral
    with pytest.raises(ValueError, match="outside its solids"):
        rel.Assembly({"mixed": mixed})
    for shape in (rel._compound([]), face.wrapped):
        measured = rel._measure_volume(shape)
        assert measured.value == measured.error == 0
    with pytest.raises(ValueError, match="no solid"):
        rel.Assembly({"face": face})


def test_missing_analytic_surface_is_rejected():
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Face
    face = TopoDS_Face()
    BRep_Builder().MakeFace(face)
    with pytest.raises(ValueError, match="invalid BREP|no exact geometric surface"):
        rel._measure_volume(face)


@pytest.mark.parametrize("volume,reported", [(1e-18, 0.1), (2.0, 0.05)])
def test_gk_absolute_error_branch_is_not_lost_at_tiny_mass(monkeypatch, volume, reported):
    """Exercise the two documented kernel return units, independently of tiny CAD tolerance."""
    from OCP.BRepGProp import BRepGProp
    class Props:
        def Mass(self):
            return volume
    class GProp:
        GProp_GProps = Props
    original = rel.require
    monkeypatch.setattr(rel, "require", lambda name, purpose: GProp if name == "OCP.GProp" else original(name, purpose))
    monkeypatch.setattr(BRepGProp, "VolumePropertiesGK_s", lambda *args: reported)
    result = rel._measure_volume(cq.Solid.makeBox(1, 1, 1).wrapped)
    assert result.error == pytest.approx(0.1)


@pytest.mark.parametrize("value,error", [(math.nan, 0), (math.inf, 0), (1, math.nan), (1, math.inf), (1, -1), (-1, 0)])
def test_invalid_integration_results_cannot_become_relations(monkeypatch, value, error):
    from OCP.BRepGProp import BRepGProp
    class Props:
        def Mass(self):
            return value
    class GProp:
        GProp_GProps = Props
    original = rel.require
    monkeypatch.setattr(rel, "require", lambda name, purpose: GProp if name == "OCP.GProp" else original(name, purpose))
    monkeypatch.setattr(BRepGProp, "VolumePropertiesGK_s", lambda *args: error)
    result = rel.relate(cq.Solid.makeBox(1, 1, 1), cq.Solid.makeBox(1, 1, 1))
    assert result.state == "unknown" and "invalid value/error" in result.error


def test_uncertainty_consumes_conservation_budget_and_near_threshold_stays_unknown(monkeypatch, tmp_path):
    from dataclasses import replace
    from cadagent.review.gates import PairCache, relation_table
    real = rel._measure_volume
    boxes = {"a": cq.Solid.makeBox(1, 1, 1), "b": cq.Solid.makeBox(1, 1, 1, cq.Vector(0.5, 0, 0))}
    asm = rel.Assembly(boxes)
    monkeypatch.setattr(rel, "_measure_volume", lambda shape: replace(real(shape), error=0.004))
    cache = PairCache(tmp_path)
    result = relation_table(asm, cache=cache).get("a", "b")
    assert result.state == "unknown" and "volumes disagree" in result.error
    assert not list(tmp_path.rglob("*.json"))
    monkeypatch.setattr(rel, "_measure_volume", lambda shape: replace(real(shape), error=0.00001))
    result = rel.relate(*boxes.values(), rel.Tolerances(overlap_mm3=0.5))
    assert result.state == "unknown" and "straddles" in result.error
    monkeypatch.setattr(rel, "_measure_volume", real)
    assert rel.relate(*boxes.values(), rel.Tolerances(overlap_mm3=0.49)).state == "overlapping"
    assert rel.relate(*boxes.values(), rel.Tolerances(overlap_mm3=0.51)).state == "touching"


def test_measurement_algorithm_version_invalidates_previous_relation_cache(monkeypatch, tmp_path):
    from cadagent.review.gates import PairCache, relation_table
    asm = rel.Assembly({"a": cq.Solid.makeBox(1, 1, 1), "b": cq.Solid.makeBox(1, 1, 1, cq.Vector(1, 0, 0))})
    cache = PairCache(tmp_path)
    current = rel.RELATIONS_VERSION
    monkeypatch.setattr(rel, "RELATIONS_VERSION", "2")
    relation_table(asm, cache=cache)
    monkeypatch.setattr(rel, "RELATIONS_VERSION", current)
    result = relation_table(asm, cache=cache)
    assert result.stats["cache_hits"] == 0 and result.stats["kernel_queries"] == 1
