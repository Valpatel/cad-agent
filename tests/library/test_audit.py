"""The model audit and the registration check, on planted mistakes as well as on the library's own footprints.

Standard library only: bodies are given as boxes (what ``cadagent.library.bodies.boxes`` reports), so each rule is
shown to catch its mistake without CadQuery. ``test_bodies.py`` runs the same check on the real CadQuery bodies.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cadagent.library import audit, footprints as F, parts

BOARD = """(kicad_pcb (version 20241229) (generator "pcbnew")
  (footprint "Lib:Part" (layer "F.Cu") (at 10 10)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))
    (model "${KIPRJMOD}/models/part.step" (offset (xyz 0 0 0))))
  (footprint "Lib:TestPoint" (layer "F.Cu") (at 20 10)
    (property "Reference" "TP1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" thru_hole circle (at 0 0) (size 2 2) (drill 1) (layers "*.Cu")))
  (footprint "Lib:Hidden" (layer "F.Cu") (at 30 10)
    (property "Reference" "R9" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))
    (model "${KIPRJMOD}/models/r.step" (hide yes)))
  (footprint "Lib:Stock" (layer "F.Cu") (at 40 10)
    (property "Reference" "C1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))
    (model "${KICAD99_3DMODEL_DIR}/C.step"))
)
"""


@pytest.fixture()
def board(tmp_path):
    p = tmp_path / 'b.kicad_pcb'
    p.write_text(BOARD)
    return p


def checks(result):
    return sorted((f['check'], f['footprint'].split()[0]) for f in result['findings'])


def test_audit_flags_missing_models_hidden_models_and_unset_variables(board):
    r = audit.model_audit(board, use_os_env=False)
    assert not r['pass'] and r['footprints'] == 4 and r['with_model'] == 2
    assert checks(r) == [('missing_model', 'U1'), ('no_model', 'R9'), ('no_model', 'TP1'), ('unresolved_var', 'C1')]


def test_audit_passes_when_models_resolve_and_waivers_give_reasons(board, tmp_path):
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models' / 'part.step').write_text('ISO-10303-21;')
    (tmp_path / 'stock').mkdir()
    (tmp_path / 'stock' / 'C.wrl').write_text('#VRML')                  # KiCad swaps .step <-> .wrl: accepted
    r = audit.model_audit(board, env={'KICAD99_3DMODEL_DIR': str(tmp_path / 'stock')},
                          waivers={'TP*': 'bare test pad', 'Lib:Hidden': 'not fitted', 'J*': 'unused'},
                          use_os_env=False)
    assert r['pass'], r['findings']
    assert {w['reason'] for w in r['waived']} == {'bare test pad', 'not fitted'}
    assert r['unused_waivers'] == ['J*']
    with pytest.raises(ValueError):
        audit.model_audit(board, waivers={'TP*': ' '}, use_os_env=False)


def test_audit_flags_an_absolute_model_path(tmp_path):
    p = tmp_path / 'x.kicad_mod'
    p.write_text('(footprint "X" (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")) (model "/opt/x.step"))')
    assert {f['check'] for f in audit.model_audit(p, use_os_env=False)['findings']} == {'absolute_path',
                                                                                        'missing_model'}


def test_kiprjmod_of_a_library_is_the_folder_holding_the_pretty(tmp_path):
    lib = tmp_path / 'lib'
    F.write_pretty([F.lug_stud('M4')], lib / 'cad-agent.pretty', '${KIPRJMOD}/cad-agent.3dshapes')
    (lib / 'cad-agent.3dshapes').mkdir()
    (lib / 'cad-agent.3dshapes' / 'LugStud_M4.step').write_text('ISO-10303-21;')
    assert audit.model_audit(lib / 'cad-agent.pretty', use_os_env=False)['pass']
    assert audit.model_audit(next((lib / 'cad-agent.pretty').iterdir()), use_os_env=False)['pass']


# ----------------------------------------------------------------------------------------------- registration

def holder_pads():
    tree = audit.S.parse(F.to_kicad_mod(F.fuseholder_mini_fl1()))
    return audit._footprint(tree, ref='')['pads']


def box(name, x0, y0, z0, x1, y1, z1, through=None):
    return {'name': name, 'min': (x0, y0, z0), 'max': (x1, y1, z1), 'through': through}


def good_holder():
    return [box('body', -7.1, -3, 0, 7.1, 3, 15.6),
            box('pin1', -4.5, -0.25, -3.3, -3.5, 0.25, 0.5, ((-4.5, -0.25), (-3.5, 0.25))),
            box('pin2', 3.5, -0.25, -3.3, 4.5, 0.25, 0.5, ((3.5, -0.25), (4.5, 0.25))),
            box('peg', -1.2, -0.4, -4.4, 1.2, 2.0, 0.5, ((-1.2, -0.4), (1.2, 2.0)))]


def test_registration_passes_a_seated_holder():
    assert audit.registration(holder_pads(), good_holder()) == []


def test_registration_catches_a_floating_body_a_missed_hole_and_a_stray_solid():
    b = good_holder()
    b[0] = box('body', -7.1, -3, 0.5, 7.1, 3, 16.1)
    assert [f['check'] for f in audit.registration(holder_pads(), b)] == ['seat']
    b = good_holder()
    b[1] = box('pin1', -5.5, -0.25, -3.3, -4.5, 0.25, 0.5, ((-5.5, -0.25), (-4.5, 0.25)))     # 1 mm off pad 1
    assert [f['detail'] for f in audit.registration(holder_pads(), b)] == ["pin1 does not pass through pad 1's hole"]
    b = good_holder() + [box('clip', 6, -1, -2, 7, 1, 1, ((6, -1), (7, 1)))]
    assert [f['check'] for f in audit.registration(holder_pads(), b)] == ['pins']
    b = good_holder()
    b[3] = box('peg', -1.2, -2.0, -4.4, 1.2, 0.4, 0.5, ((-1.2, -2.0), (1.2, 0.4)))           # the other side: fits
    assert audit.registration(holder_pads(), b) == []
    b[3] = box('peg', -1.6, -1.2, -4.4, 1.6, 2.0, 0.5, ((-1.6, -1.2), (1.6, 2.0)))           # too fat for 2.7
    assert [f['check'] for f in audit.registration(holder_pads(), b)] == ['pins']


def test_registration_catches_a_turned_smd_body():
    tree = audit.S.parse(F.to_kicad_mod(F.shunt_bourns_css2h_3920_kelvin()))
    p = audit._footprint(tree, ref='')['pads']
    right = [box('terminal1', -5, -2.6, 0, -2, 2.6, 0.93), box('element', -2, -2.6, 0, 2, 2.6, 0.93),
             box('terminal4', 2, -2.6, 0, 5, 2.6, 0.93)]
    assert audit.registration(p, right) == []
    turned = [dict(right[0], name='terminal4'), right[1], dict(right[2], name='terminal1')]
    found = audit.registration(p, turned)
    assert {f['check'] for f in found} == {'terminals'} and len(found) == 4
    sunk = [dict(b, min=(b['min'][0], b['min'][1], -0.5)) for b in right]
    assert 'seat' in {f['check'] for f in audit.registration(p, sunk)}


def test_parts_build_footprints_only_needs_no_cadquery(tmp_path):
    w = parts.build(tmp_path, models=False)
    assert len(w['footprints']) == len(parts.PARTS) and w['models'] == []
    assert parts.fp_lib_table_entry().startswith('  (lib (name "cad-agent")')
    with pytest.raises(KeyError):
        parts.build(tmp_path, keys=['nope'], models=False)
