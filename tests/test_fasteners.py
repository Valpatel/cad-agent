import pytest
from cadagent.fasteners import blind_insert_stack


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
