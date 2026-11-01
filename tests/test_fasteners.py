import pytest
from cadagent.mechanical.fasteners import blind_insert_stack
from cadagent.mechanical.fasteners import filleted_wall_rib


def test_blind_stack_recessed_lid():
    assert blind_insert_stack(head_seat=23.5, screw_length=20, insert_top=7.3,
                              insert_length=4.3, hole_bottom=2.3) == {
        'tip_z_mm': 3.5, 'engagement_mm': 3.8, 'tip_clearance_mm': 1.2,
        'insert_bottom_clearance_mm': .5}


def test_bottomed_and_short_screws_are_visible():
    args = dict(head_seat=23.5, insert_top=7.3, insert_length=4.3, hole_bottom=2.3)
    assert blind_insert_stack(screw_length=25, **args)['tip_clearance_mm'] < 0
    assert blind_insert_stack(screw_length=10, **args)['engagement_mm'] == 0
    with pytest.raises(ValueError):
        blind_insert_stack(screw_length=20, **{**args, 'hole_bottom': 5})


def test_wall_rib_has_real_curved_roots_and_positive_wall_overlap():
    cq = pytest.importorskip('cadquery')
    rib = filleted_wall_rib(thickness=3.2, reach=8, height=12,
                            root_radius=1.6, overlap=.3)
    wall = cq.Solid.makeBox(20, 2, 12, cq.Vector(-10, 8, 0))
    assert rib.isValid() and len(rib.Solids()) == 1
    assert rib.intersect(wall).Volume() > 20
    assert len(rib.fuse(wall).Solids()) == 1
    assert any(edge.geomType() == 'CIRCLE' for edge in rib.Edges())
    assert rib.BoundingBox().ymax == pytest.approx(8.3)
    with pytest.raises(ValueError):
        filleted_wall_rib(thickness=3, reach=1, height=12, root_radius=2, overlap=.3)
