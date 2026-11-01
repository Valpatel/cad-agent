"""The layer check and the material record of cadagent.simulation.fea against hand-computed cases (#144).

numpy only, so it runs in the core CI job: the layer check is checked on stress tensors written out by hand, and
Study.layer_check() on a two-element stand-in for a solved study. tests/test_fea.py solves a real printed bar.

Hand cases (sigma in MPa; S_xy, S_z the in-plane and across-layer allowables; S_s = S_z / sqrt 3 unless given):
* uniaxial tension sigma along x, layers normal to the load (n = x): sigma_n = sigma, tau_n = 0, so bond = sigma / S_z
  and bulk = sigma / S_xy; layers parallel to the load (n = z): sigma_n = tau_n = 0, so bond = 0, bulk = sigma / S_xy;
* pure shear tau on the layer plane (sigma_xz): sigma_n = 0, tau_n = tau, bond = sqrt(3) tau / S_z (= tau / S_s);
* the uniaxial bar with n turned by theta from the load in the x-z plane: sigma_n = sigma cos^2, tau_n = sigma sin cos,
  bond = sigma sqrt(cos^4 + 3 sin^2 cos^2) / S_z, which peaks at theta = 30 deg (cos^2 = 3/4) at sqrt(9/8) sigma / S_z.
"""
import dataclasses
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.simulation.fea import (LAYER_SHEAR_ASSUMPTION, MATERIALS, LayerCheck, Study, layer_allowables,
                                     layer_stresses, layer_utilisation, material_changes, material_record, von_mises)

SXY, SZ = 30.0, 20.0                        # round allowables for the hand cases


def uniaxial(s, axis=0):
    sig = np.zeros((3, 3))
    sig[axis, axis] = s
    return sig


def shear(t, i=0, j=2):
    sig = np.zeros((3, 3))
    sig[i, j] = sig[j, i] = t
    return sig


def test_uniaxial_tension_layers_normal_to_the_load():
    bond, bulk = layer_utilisation(uniaxial(10.0), (1, 0, 0), SXY, SZ)
    assert bond == pytest.approx(10 / 20) and bulk == pytest.approx(10 / 30)
    assert 1 / max(bond, bulk) == pytest.approx(2.0)                 # the bond governs, at S_z / sigma


@pytest.mark.parametrize('normal', [(0, 0, 1), (0, 1, 0), (0, 3, 4)])
def test_uniaxial_tension_layers_parallel_to_the_load(normal):
    bond, bulk = layer_utilisation(uniaxial(10.0), normal, SXY, SZ)
    assert bond == pytest.approx(0.0, abs=1e-12) and bulk == pytest.approx(10 / 30)
    assert 1 / max(bond, bulk) == pytest.approx(3.0)                 # the bulk governs, at S_xy / sigma


def test_pure_shear_on_the_layer_plane():
    sn, tau = layer_stresses(shear(5.0), (0, 0, 1))
    assert sn == pytest.approx(0.0, abs=1e-12) and tau == pytest.approx(5.0)
    bond, bulk = layer_utilisation(shear(5.0), (0, 0, 1), SXY, SZ)
    assert bond == pytest.approx(math.sqrt(3) * 5 / 20)              # 0.4330: tau against S_z / sqrt 3
    assert bulk == pytest.approx(math.sqrt(3) * 5 / 30)              # von Mises of pure shear is sqrt 3 tau
    # a measured interlayer shear strength replaces the assumption: bond = tau / S_s
    bond, _ = layer_utilisation(shear(5.0), (0, 0, 1), SXY, SZ, strength_shear=8.0)
    assert bond == pytest.approx(5 / 8)
    # the same shear seen from a plane it does not act on (n = y): nothing crosses or slides on the layers
    bond, _ = layer_utilisation(shear(5.0), (0, 1, 0), SXY, SZ)
    assert bond == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize('theta, sn, tau, bond', [
    (0, 10.0, 0.0, 0.5),
    (30, 7.5, 4.330127, 0.530330),        # 10 sqrt(9/8) / 20: the worst angle under the assumed shear strength
    (45, 5.0, 5.0, 0.5),                  # 10 sqrt(1/4 + 3/4) / 20
    (60, 2.5, 4.330127, 0.395285),        # 10 sqrt(1/16 + 9/16) / 20
    (90, 0.0, 0.0, 0.0),
])
def test_a_rotated_layer_normal(theta, sn, tau, bond):
    t = math.radians(theta)
    n = (math.cos(t), 0.0, math.sin(t))
    got_sn, got_tau = layer_stresses(uniaxial(10.0), n)
    assert got_sn == pytest.approx(sn, abs=1e-6) and got_tau == pytest.approx(tau, abs=1e-6)
    got_bond, got_bulk = layer_utilisation(uniaxial(10.0), n, SXY, SZ)
    assert got_bond == pytest.approx(bond, abs=1e-6)
    assert got_bond == pytest.approx(10 * math.sqrt(math.cos(t) ** 4 + 3 * (math.sin(t) * math.cos(t)) ** 2) / 20)
    assert got_bulk == pytest.approx(10 / 30)                        # von Mises does not see the layers


def test_the_check_does_not_depend_on_the_frame():
    rng = np.random.default_rng(144)
    a = rng.normal(size=(3, 3))
    sig = a + a.T
    n = rng.normal(size=3)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))                     # a rotation (or reflection) of the whole case
    for x, y in zip(layer_utilisation(sig, n, SXY, SZ), layer_utilisation(q @ sig @ q.T, q @ n, SXY, SZ)):
        assert x == pytest.approx(y, rel=1e-12)
    # the normal's length and sign do not matter
    for x, y in zip(layer_utilisation(sig, n, SXY, SZ), layer_utilisation(sig, -7.5 * n, SXY, SZ)):
        assert x == pytest.approx(y, rel=1e-12)


def test_compression_across_the_layers_does_not_open_them_and_hydrostatic_tension_does():
    bond, bulk = layer_utilisation(uniaxial(-10.0), (1, 0, 0), SXY, SZ)
    assert bond == pytest.approx(0.0, abs=1e-12) and bulk == pytest.approx(10 / 30)
    # equal tension every way: von Mises is zero, but the layers are pulled apart
    bond, bulk = layer_utilisation(np.eye(3) * 5.0, (0, 0, 1), SXY, SZ)
    assert bond == pytest.approx(5 / 20) and bulk == pytest.approx(0.0, abs=1e-12)


def test_arrays_of_tensors_and_von_mises():
    sig = np.stack([uniaxial(10.0), shear(5.0), np.eye(3)]).reshape(3, 1, 3, 3).repeat(4, axis=1)   # (3 el, 4 corners)
    bond, bulk = layer_utilisation(sig, (1, 0, 0), SXY, SZ)
    assert bond.shape == bulk.shape == (3, 4)
    assert von_mises(sig)[:, 0] == pytest.approx([10.0, 5 * math.sqrt(3), 0.0], abs=1e-12)


@pytest.mark.parametrize('normal', [(0, 0, 0), (1, 0), (float('nan'), 0, 1)])
def test_a_layer_normal_must_be_a_direction(normal):
    with pytest.raises(ValueError, match='layer normal'):
        layer_stresses(np.zeros((3, 3)), normal)


def test_allowables_default_to_the_printed_material():
    m = MATERIALS['petg_cf']
    xy, z, ss, basis = layer_allowables(m)
    assert (xy, z) == m.layer_strengths_mpa and z == m.strength_mpa
    assert ss == pytest.approx(z / math.sqrt(3)) and basis == LAYER_SHEAR_ASSUMPTION
    assert 'no filament data sheet' in basis
    xy, z, ss, basis = layer_allowables(m, strength_z=15.0, strength_shear=6.0)
    assert (xy, z, ss) == (m.layer_strengths_mpa[0], 15.0, 6.0) and basis == 'interlayer shear allowable given'
    # the humid PA6-CF rows share one pair: each row's own strength, whichever row the study used
    assert MATERIALS['pa6_cf_xy'].layer_strengths_mpa == MATERIALS['pa6_cf_z'].layer_strengths_mpa == (
        MATERIALS['pa6_cf_xy'].strength_mpa, MATERIALS['pa6_cf_z'].strength_mpa)


def test_an_isotropic_material_needs_both_strengths():
    with pytest.raises(ValueError, match='pass strength_xy and strength_z'):
        layer_allowables(MATERIALS['steel'])
    with pytest.raises(ValueError, match='pass strength_xy and strength_z'):
        layer_allowables(MATERIALS['steel'], strength_xy=200.0)
    assert layer_allowables(MATERIALS['steel'], 200.0, 150.0)[:2] == (200.0, 150.0)


@pytest.mark.parametrize('bad', [0, -1.0, float('nan'), float('inf'), True, '20'])
def test_allowables_must_be_positive_numbers(bad):
    with pytest.raises(ValueError, match='positive number of MPa'):
        layer_allowables(MATERIALS['pla'], strength_z=bad)
    with pytest.raises(ValueError, match='positive number of MPa'):
        layer_allowables(MATERIALS['pla'], strength_shear=bad)


def _solved_stand_in(material, sigs, touches=None):
    """A Study with only what layer_check() reads: two tetrahedra, each with one stress tensor at its four corners."""
    st = object.__new__(Study)
    st.material = material
    st.sig_corner = np.stack([np.repeat(s[None], 4, axis=0) for s in sigs])        # (n elements, 4, 3, 3)
    st.vm_corner = von_mises(st.sig_corner)
    st._touches_bc = np.zeros(len(sigs), bool) if touches is None else np.asarray(touches)
    p = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], float).T
    st._m = SimpleNamespace(p=p, t=np.array([[0, 1, 2, 3], [1, 2, 3, 4]]).T)
    return st


def test_study_layer_check_on_known_stresses():
    m = MATERIALS['petg_cf']
    xy, z = m.layer_strengths_mpa                                    # 26.55, 22
    st = _solved_stand_in(m, [uniaxial(10.0), shear(3.0)])
    across = st.layer_check((1, 0, 0))                               # the bar's load crosses the layers
    assert isinstance(across, LayerCheck)
    assert across.bond == pytest.approx([10 / z, math.sqrt(3) * 3 / z])
    assert across.bulk == pytest.approx([10 / xy, math.sqrt(3) * 3 / xy])
    assert list(across.mode) == ['bond', 'bond'] and across.governed_by == 'bond'
    assert across.safety_factor == pytest.approx(z / 10) and across.safety_factor_bulk == pytest.approx(xy / 10)
    assert across.factor == pytest.approx([z / 10, z / (math.sqrt(3) * 3)])
    w = across.worst
    assert w['element'] == 0 and w['mode'] == 'bond' and w['sigma_n_mpa'] == 10.0 and w['tau_n_mpa'] == 0.0
    assert w['corner_mm'] in ([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1])
    assert w['element_centre_mm'] == [0.25, 0.25, 0.25]
    along = st.layer_check((0, 0, 1))                                # layers along the bar: the bulk governs it
    assert along.bond[0] == pytest.approx(0.0, abs=1e-12) and along.mode[0] == 'bulk'
    assert along.safety_factor == pytest.approx(xy / 10) and along.governed_by == 'bulk'
    d = along.as_dict()
    json.dumps(d)
    assert d['safety_factor'] == round(xy / 10, 2) and d['governed_by'] == 'bulk'
    assert d['allowables_mpa'] == {'xy': round(xy, 3), 'z': 22.0, 'shear': round(22 / math.sqrt(3), 3)}
    assert d['shear_basis'] == LAYER_SHEAR_ASSUMPTION and 'not a qualification' in d['assumptions']
    assert d['judged_elements'] == 2


def test_an_unstressed_part_has_no_governing_check():
    lc = _solved_stand_in(MATERIALS['petg_cf'], [np.zeros((3, 3)), np.zeros((3, 3))]).layer_check((0, 0, 1))
    assert lc.safety_factor is None and lc.governed_by is None and lc.worst['mode'] is None
    assert list(lc.mode) == ['none', 'none'] and np.all(np.isinf(lc.factor))
    d = lc.as_dict()
    assert d['safety_factor'] is None and d['governed_by'] is None
    # an element with stress keeps its mode beside an unstressed one
    lc = _solved_stand_in(MATERIALS['petg_cf'], [np.zeros((3, 3)), uniaxial(10.0)]).layer_check((1, 0, 0))
    assert list(lc.mode) == ['none', 'bond'] and lc.governed_by == 'bond'


def test_study_layer_check_judges_like_the_safety_factor():
    m = MATERIALS['petg_cf']
    # element 0 touches a clamp: its stress is left out, as the safety factor leaves it out
    st = _solved_stand_in(m, [uniaxial(30.0), uniaxial(10.0)], touches=[True, False])
    lc = st.layer_check((1, 0, 0))
    assert lc.safety_factor == pytest.approx(22 / 10) and lc.worst['element'] == 1
    assert lc.factor[0] == pytest.approx(22 / 30)                    # still there per element
    # a mask of your own: here only the clamped element
    assert st.layer_check((1, 0, 0), judge=[True, False]).safety_factor == pytest.approx(22 / 30)
    with pytest.raises(ValueError, match='one bool per element'):
        st.layer_check((1, 0, 0), judge=[False, False])
    with pytest.raises(ValueError, match='one bool per element'):
        st.layer_check((1, 0, 0), judge=[True])
    with pytest.raises(ValueError, match='pass strength_xy and strength_z'):
        _solved_stand_in(MATERIALS['al6061'], [uniaxial(10.0), uniaxial(1.0)]).layer_check((0, 0, 1))
    with pytest.raises(RuntimeError, match='solve'):
        object.__new__(Study).layer_check((0, 0, 1))


# --- the material data a result records

# constants_hash of every built-in row. A change here is a change to a built-in material's numbers, which changes the
# results of every study that uses the row, so a pin that fails here needs a **Projects must change** fragment in
# changelog.d/ (which rows, which numbers, by how much) before it is updated. It also pins the hash recipe, so a record
# made on one toolkit stays comparable with one made on another.
HASHES = {
    'pla': '2c78726c6d49d34f',
    'petg': 'ed9743067b05442c',
    'petg_cf': '244de599e3497672',
    'pa_cf': '946edeb2a6fbcfdc',
    'pa6_cf_xy': 'b0989f2b1b1c8bdc',
    'pa6_cf_z': '813009441363f213',
    'tpu95': '8e630e19769ea451',
    'al6061': 'aeee977f95934faf',
    'al7075': '029bccd017d81deb',
    'steel': '112dad8a9452cba9',
    'cf_tube': '89a62946b4e6c3d2',
}


def test_built_in_material_numbers_are_pinned():
    got = {k: material_record(m)['constants_hash'] for k, m in MATERIALS.items()}
    changed = sorted(k for k in set(got) | set(HASHES) if got.get(k) != HASHES.get(k))
    assert not changed, (f'built-in material numbers changed for {changed}: that changes the results of every study '
                         'that uses them. Add a **Projects must change** fragment to changelog.d/ (which rows, which '
                         'numbers, how much deflections, safety factors or masses move), then update HASHES')


def test_the_record_carries_the_constants_used():
    m = MATERIALS['pa6_cf_z']
    r = material_record(m)
    json.dumps(r)
    assert r['key'] == 'pa6_cf_z' and r['name'] == m.name
    assert (r['E_mpa'], r['E_direction'], r['nu'], r['strength_mpa'], r['density_g_cm3']) == (
        m.E_mpa, 'Z', m.nu, m.strength_mpa, m.density_g_cm3)
    assert (r['strength_xy_mpa'], r['strength_z_mpa']) == m.layer_strengths_mpa
    assert r['source'] == 'bambu-pa6-cf-tds' and 'TDS V3.0' in r['note']          # the sheet and its edition
    steel = material_record(MATERIALS['steel'])
    assert steel['E_direction'] is None and steel['strength_xy_mpa'] is None and steel['strength_z_mpa'] is None
    # a changed copy of a row is not that row
    assert material_record(dataclasses.replace(m, E_mpa=1042.0))['key'] is None
    # the hash covers the numbers only: a reworded note keeps it
    assert material_record(dataclasses.replace(m, note='reworded'))['constants_hash'] == r['constants_hash']


def test_material_changes_between_two_toolkits():
    """#144 entry 11: pa6_cf_z between Gyropup's pin and later toolkits looked like a design change."""
    now = MATERIALS['pa6_cf_z']
    before_157 = dataclasses.replace(now, E_mpa=2170 * 0.48, strength_mpa=48 * 0.48)   # the x0.6 x0.8 row of v0.5.0
    old = {'material': before_157.name, 'material_data': material_record(before_157)}
    changes = {c['field']: c for c in material_changes(old, now)}
    assert set(changes) == {'E_mpa', 'strength_mpa', 'key'}
    assert changes['E_mpa']['recorded'] == pytest.approx(1041.6) and changes['E_mpa']['now'] == now.E_mpa
    assert 1 / changes['E_mpa']['ratio'] == pytest.approx(2.14, abs=0.01)           # deflections read 2.14x
    assert changes['strength_mpa']['ratio'] == pytest.approx(0.79, abs=0.01)        # safety factors read 0.79x
    assert changes['key'] == {'field': 'key', 'recorded': None, 'now': 'pa6_cf_z'}
    assert material_changes(now, {'material_data': material_record(now)}) == []
    assert material_changes(material_record(now), now) == []
    # a whole export_viewer() file keeps the result (and its material_data) under 'result'
    viewer = {'format': 'cadagent-fea-viewer', 'material': {'name': now.name},
              'result': {'material': now.name, 'material_data': material_record(before_157)}}
    assert {c['field'] for c in material_changes(viewer, now)} == {'E_mpa', 'strength_mpa', 'key'}
    # a result from before results recorded the data says so, rather than guessing, and says what to do instead
    for old_style in ({'material': now.name, 'material_source': now.source},
                      {'format': 'cadagent-fea-viewer', 'material': {'name': now.name}, 'result': {'material': now.name}}):
        with pytest.raises(ValueError, match='before results recorded the constants') as err:
            material_changes(old_style, now)
        assert repr(now.name) in str(err.value) and 'as a Material' in str(err.value)
    with pytest.raises(TypeError):
        material_changes('pa6_cf_z', now)


def test_the_docs_table_gives_the_layer_allowables_in_the_code():
    """docs/toolkit.md's printed-materials table lists each row's (X-Y, Z) layer-check allowables to 0.1 MPa."""
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / 'docs' / 'toolkit.md').read_text(encoding='utf-8')
    fmt = lambda v: f'{v:.1f}'.removesuffix('.0')
    for key, m in MATERIALS.items():
        if m.layer_strengths_mpa is None:
            continue
        row = next(line for line in text.splitlines() if line.startswith(f'| `{key}` |'))
        assert f'| {fmt(m.layer_strengths_mpa[0])} / {fmt(m.layer_strengths_mpa[1])} |' in row, (key, row)
