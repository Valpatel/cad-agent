"""The CadQuery bodies: each one registers on its footprint (seat, pins in holes, terminals on pads), matches its
datasheet's envelope, and writes the same coloured STEP bytes twice. Needs the ``cad`` extra."""
from __future__ import annotations

import hashlib

import pytest

pytest.importorskip('cadquery')

from cadagent.library import audit, bodies, footprints as F, hardware, parts  # noqa: E402


def pads_of(fp):
    return audit._footprint(audit.S.parse(F.to_kicad_mod(fp)), ref='')['pads']


@pytest.mark.parametrize('key', [k for k, p in parts.PARTS.items() if p.body])
def test_every_body_registers_on_its_footprint(key):
    p = parts.PARTS[key]
    assert audit.registration(pads_of(p.footprint()), bodies.boxes(p.body())) == []


def _box(assy, name):
    return next(b for b in bodies.boxes(assy) if b['name'] == name)


def test_holder_body_is_the_datasheet_envelope():
    ds = parts.PARTS['fuseholder_mini_fl1'].datasheet
    a = bodies.fuseholder_mini_fl1()
    b = _box(a, 'body')
    assert b['max'][0] - b['min'][0] == pytest.approx(ds['body_length'][0])
    assert b['max'][1] - b['min'][1] == pytest.approx(ds['body_width'][0])
    assert b['max'][2] == pytest.approx(ds['body_height'][0])
    lowest = min(x['min'][2] for x in bodies.boxes(a))
    assert b['max'][2] - lowest == pytest.approx(ds['overall_height'][0])


def test_shunt_body_is_the_datasheet_envelope():
    ds = parts.PARTS['shunt_css2h_3920'].datasheet
    bx = bodies.boxes(bodies.shunt_css2h_3920())
    xs = [v for b in bx for v in (b['min'][0], b['max'][0])]
    assert max(xs) - min(xs) == pytest.approx(ds['body_length'][0])
    assert max(b['max'][2] for b in bx) == pytest.approx(ds['height_max_1L00'][0])
    t1 = next(b for b in bx if b['name'] == 'terminal1')
    assert t1['max'][0] - t1['min'][0] == pytest.approx(ds['terminal_length'][0])


@pytest.mark.parametrize('size', ['M4', 'M6'])
def test_stud_stack_heights_come_from_the_hardware_tables(size):
    a = bodies.lug_stud(size, 12.0, board=1.6)
    lug, head, nut = (_box(a, n) for n in ('lug', 'head', 'nut'))
    assert head['min'][2] == pytest.approx(lug['max'][2])
    assert head['max'][2] - head['min'][2] == pytest.approx(hardware.row('socket_head', size)['k'])
    assert head['max'][0] - head['min'][0] == pytest.approx(hardware.row('socket_head', size)['dk'])
    assert nut['max'][2] == pytest.approx(-1.6)
    assert nut['max'][2] - nut['min'][2] == pytest.approx(hardware.row('nyloc_nut', size)['m'])
    shank = _box(a, 'pin1')
    assert shank['max'][2] - shank['min'][2] == pytest.approx(12.0)
    assert shank['min'][2] < nut['min'][2]              # the screw reaches through the nut


def test_fuse_colours_and_refusal():
    assert _box(bodies.mini_fuse(10), 'fuse')['min'][2] > 0
    with pytest.raises(ValueError):
        bodies.mini_fuse(11)


def test_step_is_reproducible_and_coloured(tmp_path):
    a = tmp_path / 'a' / 'Holder.step'
    b = tmp_path / 'b' / 'Holder.step'
    bodies.write_step(bodies.fuseholder_mini_fl1(), a)
    bodies.write_step(bodies.fuseholder_mini_fl1(), b)
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    text = a.read_text()
    assert 'COLOUR_RGB' in text and "'pin1'" in text


def test_build_writes_the_models_the_footprints_name(tmp_path):
    w = parts.build(tmp_path, fuses=(10,))
    assert 'MiniFuse_10A.step' in w['models']
    r = audit.model_audit(tmp_path / 'cad-agent.pretty', waivers={'Slot_*': 'a hole'}, use_os_env=False)
    assert r['pass'], r['findings']
