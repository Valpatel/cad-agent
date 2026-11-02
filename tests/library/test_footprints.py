"""The library's footprints against their datasheets (golden vectors) and the KiCad file format.

Each part's numbers are in ``cadagent.library.parts.PARTS[...].datasheet`` with the page they come from. The tests
read the written ``.kicad_mod`` text back (``cadagent.library.sexp``), so they check the file KiCad loads, not the
Python objects. Standard library only: they run in the core suite.
"""
from __future__ import annotations

import math

import pytest

from cadagent.library import audit, footprints as F, parts, sexp as S


def written(fp, model_dir='${KIPRJMOD}/cad-agent.3dshapes'):
    tree = S.parse(F.to_kicad_mod(fp, model_dir))
    return tree, audit._footprint(tree, ref='')


def pads(fp, number=None, kind=None):
    return [p for p in written(fp)[1]['pads'] if (number is None or p['number'] == number)
            and (kind is None or p['kind'] == kind)]


def ds(key, name):
    return parts.PARTS[key].datasheet[name][0]


def test_mini_fl1_hole_pattern_matches_the_datasheet():
    fp = F.fuseholder_mini_fl1()
    (p1,), (p2,) = pads(fp, '1'), pads(fp, '2')
    pitch = p2['at'][0] - p1['at'][0]
    assert pitch == pytest.approx(ds('fuseholder_mini_fl1', 'terminal_pitch'))
    assert p1['at'][1] == p2['at'][1] == 0.0
    assert p1['drill'] == p2['drill'] == (ds('fuseholder_mini_fl1', 'terminal_hole'),) * 2
    assert p1['kind'] == p2['kind'] == 'thru_hole'
    (peg,) = pads(fp, kind='np_thru_hole')
    # the peg (2.7 hole) sits 0.8 off the terminals' line on an unstated side: the slot must take it on either side
    d, off = ds('fuseholder_mini_fl1', 'peg_hole'), ds('fuseholder_mini_fl1', 'peg_offset')
    w, h = peg['drill']
    assert w == pytest.approx(d)
    assert h / 2 >= off + d / 2 - 1e-9
    # and still leave copper web to the terminals' pads (holder pads 3.2)
    assert abs(p1['at'][0]) - p1['size'][0] / 2 - w / 2 > 0.5


def test_mini_fl1_body_outline_is_the_datasheet_body():
    tree, _ = written(F.fuseholder_mini_fl1())
    fab = [ln for ln in S.find(tree, 'fp_line') if S.first(ln, 'layer')[1] == 'F.Fab']
    xs = [v for ln in fab for v in (S.nums(S.first(ln, 'start'), 2)[0], S.nums(S.first(ln, 'end'), 2)[0])]
    ys = [v for ln in fab for v in (S.nums(S.first(ln, 'start'), 2)[1], S.nums(S.first(ln, 'end'), 2)[1])]
    assert max(xs) - min(xs) == pytest.approx(ds('fuseholder_mini_fl1', 'body_length'))
    assert max(ys) - min(ys) == pytest.approx(ds('fuseholder_mini_fl1', 'body_width'))


def test_css2h_3920_pads_are_bourns_recommended_layout():
    k = 'shunt_css2h_3920'
    fp = F.shunt_bourns_css2h_3920_kelvin()
    (p1,), (p4,) = pads(fp, '1'), pads(fp, '4')
    assert p1['size'] == (ds(k, 'pad_length'), ds(k, 'pad_width')) == p4['size']
    outer = (p4['at'][0] + p4['size'][0] / 2) - (p1['at'][0] - p1['size'][0] / 2)
    assert outer == pytest.approx(ds(k, 'pad_outer_span'))
    (t2,), (t3,) = pads(fp, '2'), pads(fp, '3')
    assert t3['at'][0] - t2['at'][0] == pytest.approx(ds(k, 'sense_points'))
    # the taps are inside the current pads' span and off their copper (the net tie joins them)
    assert abs(t2['at'][1]) > p1['size'][1] / 2
    tree, _ = written(fp)
    assert S.first(tree, 'net_tie_pad_groups')[1:] == ['1, 2', '3, 4']
    assert S.first(tree, 'attr')[1] == 'smd'


@pytest.mark.parametrize('size,pad,drill', [('M4', 7.0, 4.3), ('M6', 12.0, 6.4)])
def test_lug_stud_hole_is_iso_273_medium_and_vias_ring_the_hole(size, pad, drill):
    fp = F.lug_stud(size)
    ps = pads(fp, '1')
    main = [p for p in ps if p['size'][0] == pad]
    vias = [p for p in ps if p['size'][0] == 0.95]
    assert len(main) == 1 and main[0]['drill'] == (drill, drill)
    assert drill == ds(f'lug_stud_{size.lower()}', 'hole')
    assert len(vias) == 8
    radii = {round(math.hypot(*p['at']), 4) for p in vias}
    assert len(radii) == 1
    r = radii.pop()
    assert drill / 2 < r - 0.95 / 2 and r + 0.95 / 2 < pad / 2    # every via is inside the pad's copper, off the hole


def test_bond_hole_and_slot():
    (main,) = [p for p in pads(F.bonded_mounting_hole()) if p['size'][0] == 10.0]
    assert main['drill'] == (5.3, 5.3)
    (slot,) = pads(F.npth_slot(), kind='np_thru_hole')
    assert slot['drill'] == (4.0, 10.0) and slot['shape'] == 'oval'
    assert F.npth_slot().model is None and parts.PARTS['slot_4x10'].no_body


def test_written_file_is_kicad_9_format_with_stable_uuids_and_the_model_path():
    fp = F.lug_stud('M4')
    a, b = F.to_kicad_mod(fp, '${KIPRJMOD}/lib/cad-agent.3dshapes'), F.to_kicad_mod(F.lug_stud('M4'),
                                                                                   '${KIPRJMOD}/lib/cad-agent.3dshapes')
    assert a == b
    tree = S.parse(a)
    assert tree[0] == 'footprint' and S.first(tree, 'version')[1] == str(F.FORMAT_VERSION)
    uuids = [u[1] for u in S.walk(tree, 'uuid')]
    assert len(uuids) == len(set(uuids))
    (model,) = S.find(tree, 'model')
    assert model[1] == '${KIPRJMOD}/lib/cad-agent.3dshapes/LugStud_M4.step'
    assert not S.find(S.parse(F.to_kicad_mod(fp)), 'model')       # no folder given: no model line


def test_every_part_writes_a_footprint_that_parses_and_names_its_model():
    for key, p in parts.PARTS.items():
        fp = p.footprint()
        _, info = written(fp)
        assert info['pads'], key
        assert (fp.model is None) == (p.body is None), key
        assert (p.body is None) == bool(p.no_body), key
        assert p.source and p.licence, key


def test_pad_validation():
    with pytest.raises(ValueError):
        F.Pad('1', 'smd', 'rect', (0, 0), (1, 1), drill=0.5)
    with pytest.raises(ValueError):
        F.Pad('1', 'thru_hole', 'circle', (0, 0), (1, 1))
    with pytest.raises(ValueError):
        F.lug_stud('M3')
    with pytest.raises(ValueError):
        F.lug_stud('M4', pad=4.0, drill=4.3)


def test_sexp_round_trip_and_errors():
    text = '(a "b \\"c\\"" (d 1 2.5) (e))'
    tree = S.parse(text)
    assert tree == ['a', 'b "c"', ['d', '1', '2.5'], ['e']]
    assert S.parse(S.dump(tree)) == tree
    with pytest.raises(ValueError):
        S.parse('(a (b)')
    with pytest.raises(ValueError):
        S.parse('(a))')
