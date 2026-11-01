"""The layer check and the material record of cadagent.simulation.fea against hand-computed cases (#144).

numpy only, so it runs in the core CI job: the layer check is checked on stress tensors written out by hand, and
Study.layer_check() on a two-element stand-in for a solved study. tests/test_fea.py solves a real printed bar.

Hand cases (sigma in MPa; S_xy, S_z the in-plane and across-layer allowables; S_s = S_z / sqrt 3 unless given):
* uniaxial tension sigma along x, layers normal to the load (n = x): sigma_n = sigma, tau_n = 0, so bond = sigma / S_z
  and bulk = sigma / S_xy; layers parallel to the load (n = z): sigma_n = tau_n = 0, so bond = 0, bulk = sigma / S_xy;
* pure shear tau on the layer plane (sigma_xz): sigma_n = 0, tau_n = tau, bond = sqrt(3) tau / S_z (= tau / S_s);
* the uniaxial bar with n turned by theta from the load in the x-z plane: sigma_n = sigma cos^2, tau_n = sigma sin cos,
  bond = sigma sqrt(cos^4 + 3 sin^2 cos^2) / S_z, which peaks at theta = 30 deg (cos^2 = 3/4) at sqrt(9/8) sigma / S_z.

The two criteria and the two bulk stresses (criterion=, bulk_stress=), on corners with n = z, S_z = 20, S_xy = 30 and
S_s = 20 / sqrt 3 MPa (docs/toolkit.md's table):
* sigma_n 10, tau_n 5: combined sqrt(1/4 + 3/16) = 0.6614; max-stress max(10/20, 5 sqrt 3/20) = 0.5; full von Mises
  sqrt(100 + 75) = 13.23 MPa (0.441); in-plane 0;
* sigma_n 10, tau_n 10/sqrt 3 (the two terms equal): combined sqrt(1/2) = 0.7071, max-stress 0.5, sqrt 2 apart;
* sigma_11 20, tau_n 5: combined = max-stress = 0.4330; full sqrt(400 + 75) = 21.79 MPa (0.7265), in-plane 20 (0.6667);
* sigma_11 -32, sigma_n -12 (layers squeezed, the plane compressed harder): bond 0 either way; full von Mises
  sqrt(1024 + 144 - 384) = 28 MPa (0.9333, a pass), in-plane 32 MPa (1.0667, a fail);
* sigma_11 30, sigma_n 10 (layers pulled, the plane pulled harder): bond 0.5 either way; full von Mises
  sqrt(900 + 100 - 300) = 26.46 MPa (0.8819), in-plane 30 MPa (1.0): the full one is the lower in tension too.
"""
import dataclasses
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from cadagent.simulation.fea import (BULK_STRESSES, LAYER_ASSUMPTIONS, LAYER_CRITERIA, LAYER_MODES,
                                     LAYER_SHEAR_ASSUMPTION, MATERIALS, LayerCheck, Study, _weighted_percentile,
                                     in_plane_von_mises, layer_allowables, layer_modes, layer_stresses,
                                     layer_utilisation, material_changes, material_record, von_mises)

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


# --- the two criteria and the two bulk stresses (criterion=, bulk_stress=)

def tensor(**c):
    """A stress tensor from its named components (xx, yy, zz, xy, xz, yz), MPa."""
    sig = np.zeros((3, 3))
    for name, v in c.items():
        i, j = ('xyz'.index(name[0]), 'xyz'.index(name[1]))
        sig[i, j] = sig[j, i] = v
    return sig


# corner, combined bond, max-stress (tension, shear), full bulk, in-plane bulk: the module docstring's hand values
HAND_CORNERS = [
    (tensor(zz=10, xz=5), math.sqrt(0.25 + 0.1875), (0.5, 5 * math.sqrt(3) / 20), math.sqrt(175) / 30, 0.0),
    (tensor(zz=10, xz=10 / math.sqrt(3)), math.sqrt(0.5), (0.5, 0.5), math.sqrt(200) / 30, 0.0),
    (tensor(xx=20, xz=5), 5 * math.sqrt(3) / 20, (0.0, 5 * math.sqrt(3) / 20), math.sqrt(475) / 30, 20 / 30),
    (tensor(xx=-32, zz=-12), 0.0, (0.0, 0.0), 28 / 30, 32 / 30),
    (tensor(xx=30, zz=10), 0.5, (0.5, 0.0), math.sqrt(700) / 30, 1.0),
]


@pytest.mark.parametrize('sig, combined, max_stress, full, in_plane', HAND_CORNERS)
def test_the_criteria_on_hand_corners(sig, combined, max_stress, full, in_plane):
    c = layer_modes(sig, (0, 0, 1), SXY, SZ)
    assert set(c) == set(LAYER_MODES['combined']) == {'bond', 'bulk'}
    assert c['bond'] == pytest.approx(combined, abs=1e-12) and c['bulk'] == pytest.approx(full, abs=1e-12)
    m = layer_modes(sig, (0, 0, 1), SXY, SZ, criterion='max-stress')
    assert tuple(m) == LAYER_MODES['max-stress'] == ('tension', 'shear', 'bulk')
    assert (m['tension'], m['shear']) == pytest.approx(max_stress, abs=1e-12) and m['bulk'] == pytest.approx(full)
    assert layer_modes(sig, (0, 0, 1), SXY, SZ, bulk_stress='in-plane')['bulk'] == pytest.approx(in_plane, abs=1e-12)
    # layer_utilisation's (bond, bulk): the max-stress bond is the larger of its two checks
    bond, bulk = layer_utilisation(sig, (0, 0, 1), SXY, SZ, criterion='max-stress', bulk_stress='in-plane')
    assert bond == pytest.approx(max(max_stress), abs=1e-12) and bulk == pytest.approx(in_plane, abs=1e-12)


def test_which_criterion_is_more_cautious_where():
    """With one S_s the combined bond is never below the max-stress one, and at most sqrt 2 above it (where the two
    terms are equal); the full von Mises is below the in-plane one exactly where sigma_n (s11 + s22 - sigma_n) >
    3 tau_n^2."""
    rng = np.random.default_rng(144)
    a = rng.normal(scale=10, size=(4000, 3, 3))
    sig = a + np.swapaxes(a, 1, 2)
    n = (0.2, -0.4, 0.9)
    comb, _ = layer_utilisation(sig, n, SXY, SZ)
    most, _ = layer_utilisation(sig, n, SXY, SZ, criterion='max-stress')
    assert np.all(comb >= most - 1e-12) and np.all(comb <= math.sqrt(2) * most + 1e-12)
    sn, tau = layer_stresses(sig, n)
    in_plane_sum = np.trace(sig, axis1=1, axis2=2) - sn                  # s11 + s22, in any in-plane axes
    full, inp = von_mises(sig), in_plane_von_mises(sig, n)
    assert full ** 2 == pytest.approx(inp ** 2 + sn ** 2 - sn * in_plane_sum + 3 * tau ** 2, rel=1e-9, abs=1e-9)
    lower = sn * (in_plane_sum - sn) > 3 * tau ** 2
    assert lower.any() and (~lower).any()
    assert np.all((full < inp)[lower]) and np.all((full >= inp - 1e-9)[~lower])
    assert (lower & (sn > 0)).any() and (lower & (sn < 0)).any()      # pulled or squeezed: both halves happen


def test_in_plane_von_mises_on_hand_cases_and_in_any_frame():
    assert in_plane_von_mises(uniaxial(10.0), (0, 0, 1)) == pytest.approx(10.0)          # along the layers
    assert in_plane_von_mises(uniaxial(10.0), (1, 0, 0)) == pytest.approx(0.0, abs=1e-12)  # across them: the bond's
    assert in_plane_von_mises(shear(5.0, 0, 1), (0, 0, 1)) == pytest.approx(5 * math.sqrt(3))
    assert in_plane_von_mises(shear(5.0, 0, 2), (0, 0, 1)) == pytest.approx(0.0, abs=1e-12)  # interlayer shear: bond
    t = math.radians(30)                                                   # a bar's tilted layers: sigma sin^2
    assert in_plane_von_mises(uniaxial(10.0), (math.cos(t), 0, math.sin(t))) == pytest.approx(10 * math.sin(t) ** 2)
    rng = np.random.default_rng(7)
    a = rng.normal(size=(3, 3))
    sig, n = a + a.T, rng.normal(size=3)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    assert in_plane_von_mises(q @ sig @ q.T, q @ n) == pytest.approx(in_plane_von_mises(sig, -3 * n), rel=1e-12)
    for criterion in LAYER_CRITERIA:
        for bulk in BULK_STRESSES:
            x = layer_modes(sig, n, SXY, SZ, criterion=criterion, bulk_stress=bulk)
            y = layer_modes(q @ sig @ q.T, -2 * (q @ n), SXY, SZ, criterion=criterion, bulk_stress=bulk)
            assert all(x[k] == pytest.approx(y[k], rel=1e-12) for k in x)


def _a_project_layer_aware(sig, n, along, across, shear_allow):
    """A project's own layer-aware check, written out as Gyropup's cad/turret_studies.py layer_aware does it: the
    stress in a frame (e1, e2, n) built from the normal, then three maximum-stress checks, each against its allowable:
    the in-plane von Mises, the tension across, the interlaminar shear. Here to show the toolkit's options give the
    same numbers, so a project can keep one implementation."""
    n = np.asarray(n, float) / np.linalg.norm(n)
    e1 = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    pr = lambda u, v: np.einsum('i,...ij,j->...', u, sig, v)
    snn, t1, t2, s11, s22, s12 = pr(n, n), pr(e1, n), pr(e2, n), pr(e1, e1), pr(e2, e2), pr(e1, e2)
    return {'bulk': np.sqrt(s11 ** 2 - s11 * s22 + s22 ** 2 + 3 * s12 ** 2) / along,
            'tension': np.maximum(snn, 0.0) / across, 'shear': np.sqrt(t1 ** 2 + t2 ** 2) / shear_allow}


def test_max_stress_with_the_in_plane_bulk_is_a_projects_three_checks():
    rng = np.random.default_rng(29)
    a = rng.normal(scale=15, size=(500, 4, 3, 3))
    sig = a + np.swapaxes(a, -1, -2)
    xy, z = MATERIALS['pa6_cf_xy'].layer_strengths_mpa
    for n in [(0, 0, 1), (1, 0, 0), (0.3, 0.8, -0.5)]:
        theirs = _a_project_layer_aware(sig, n, xy, z, 0.5 * z)
        ours = layer_modes(sig, n, xy, z, 0.5 * z, criterion='max-stress', bulk_stress='in-plane')
        for k in theirs:
            assert ours[k] == pytest.approx(theirs[k], rel=1e-9, abs=1e-12), (n, k)


@pytest.mark.parametrize('kw', [{'criterion': 'max_stress'}, {'criterion': 'Combined'}, {'criterion': None},
                                {'bulk_stress': 'inplane'}, {'bulk_stress': ['full']}])
def test_an_unknown_option_is_refused(kw):
    with pytest.raises(ValueError, match='is one of'):
        layer_modes(uniaxial(1.0), (0, 0, 1), SXY, SZ, **kw)
    st = _solved_stand_in(MATERIALS['petg_cf'], [uniaxial(10.0), shear(3.0)])
    with pytest.raises(ValueError, match='is one of'):
        st.layer_check((0, 0, 1), **kw)


def _stand_in_of_tets(material, sigs, scales):
    """A stand-in study with one separate tetrahedron per stress, each scaled (its volume is scale^3 / 6 mm^3)."""
    st = _solved_stand_in(material, sigs)
    unit = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    pts = np.concatenate([unit * s + [10.0 * i, 0, 0] for i, s in enumerate(scales)])
    st._m = SimpleNamespace(p=pts.T, t=np.arange(4 * len(sigs)).reshape(-1, 4).T)
    return st


def test_the_default_check_is_the_one_before_the_options():
    """Existing results do not change: on random stresses the default check is, number for number, the formula it
    used before criterion= and bulk_stress= existed (written out here), and the explicit defaults are the same."""
    rng = np.random.default_rng(203)
    a = rng.normal(scale=8, size=(300, 3, 3))
    sigs = list(a + np.swapaxes(a, 1, 2))
    m = MATERIALS['petg_cf']
    xy, z = m.layer_strengths_mpa
    st = _stand_in_of_tets(m, sigs, rng.uniform(0.5, 2.0, size=len(sigs)))
    st.sig_corner = st.sig_corner + rng.normal(scale=2, size=st.sig_corner.shape)   # four different corners
    st.sig_corner = 0.5 * (st.sig_corner + np.swapaxes(st.sig_corner, -1, -2))
    st.vm_corner = von_mises(st.sig_corner)
    n = (0.1, 0.7, 0.7)
    sn, tau = layer_stresses(st.sig_corner, n)
    before_bond = np.sqrt((np.maximum(sn, 0.0) / z) ** 2 + (tau / (z / math.sqrt(3))) ** 2)
    before_bulk = st.vm_corner / xy
    for lc in (st.layer_check(n), st.layer_check(n, criterion='combined', bulk_stress='full')):
        assert np.array_equal(lc.bond, before_bond.max(axis=1)) and np.array_equal(lc.bulk, before_bulk.max(axis=1))
        u = np.maximum(before_bond, before_bulk)
        e, k = np.unravel_index(np.argmax(u), u.shape)
        assert (lc.worst['element'], lc.worst['bond'], lc.worst['bulk']) == (
            e, round(float(before_bond[e, k]), 4), round(float(before_bulk[e, k]), 4))
        assert lc.worst['mode'] == ('bond' if before_bond[e, k] >= before_bulk[e, k] else 'bulk')
        assert list(lc.mode) == list(np.where(before_bond.max(1) >= before_bulk.max(1), 'bond', 'bulk'))
        d = lc.as_dict()
        assert d['assumptions'] == LAYER_ASSUMPTIONS and (d['criterion'], d['bulk_stress']) == ('combined', 'full')
        assert 'tension' not in d['worst'] and 'in_plane_von_mises_mpa' not in d['worst']
        assert d['worst']['resolution'] is None                      # a stand-in has no mesh faces to measure


def test_study_layer_check_under_the_max_stress_criterion():
    m = MATERIALS['petg_cf']
    xy, z = m.layer_strengths_mpa
    ss = z / math.sqrt(3)
    st = _solved_stand_in(m, [tensor(zz=10, xz=5), tensor(xx=-32, zz=-12)])
    lc = st.layer_check((0, 0, 1), criterion='max-stress', bulk_stress='in-plane', strength_shear=0.5 * z)
    assert set(lc.modes) == {'tension', 'shear', 'bulk'} and lc.criterion == 'max-stress'
    assert lc.modes['tension'] == pytest.approx([10 / z, 0.0]) and lc.modes['shear'] == pytest.approx([10 / z, 0.0])
    assert lc.modes['bulk'] == pytest.approx([0.0, 32 / xy])
    assert lc.bond == pytest.approx([10 / z, 0.0])                       # the larger of tension and shear
    assert list(lc.mode) == ['tension', 'bulk']                         # a tie goes to the earlier check
    assert lc.governed_by == 'bulk' and lc.safety_factor == pytest.approx(xy / 32)
    w = lc.worst
    assert w['element'] == 1 and w['in_plane_von_mises_mpa'] == 32.0 and w['von_mises_mpa'] == 28.0
    assert (w['tension'], w['shear']) == (0.0, 0.0)
    d = lc.as_dict()
    json.dumps(d)
    assert d['allowables_mpa']['shear'] == round(0.5 * z, 3) and d['shear_basis'] == 'interlayer shear allowable given'
    assert 'separate maximum-stress checks' in d['assumptions'] and 'in-plane stress alone' in d['assumptions']
    assert set(d['stats']) == {'utilisation', 'tension', 'shear', 'bulk'}
    # the same corners under the defaults: the bond is the quadratic one, the bulk the full von Mises (28, a pass)
    lc = st.layer_check((0, 0, 1))
    assert lc.bond[0] == pytest.approx(math.sqrt((10 / z) ** 2 + (5 / ss) ** 2)) and lc.bulk[1] == pytest.approx(28 / xy)


def test_stats_say_how_far_past_the_worst_corner_the_stress_reaches():
    """100 equal tetrahedra with bond utilisations 0.0125, 0.025, ... 1.25 (the load crosses the layers): 20 are past
    1 (the one at exactly 1 is not), and p99 is numpy's inverted-CDF percentile."""
    m = MATERIALS['petg_cf']
    z = m.layer_strengths_mpa[1]
    u = np.arange(1, 101) / 80.0
    st = _stand_in_of_tets(m, [uniaxial(v * z) for v in u], np.full(100, 2.0))
    lc = st.layer_check((1, 0, 0))
    s = lc.stats
    assert set(s) == {'utilisation', 'bond', 'bulk'}
    b = s['bond']
    assert b['max'] == pytest.approx(1.25) and b['over_1'] == 20
    assert b['p99'] == pytest.approx(float(np.percentile(u, 99, method='inverted_cdf')))
    assert b['over_1_volume_mm3'] == pytest.approx(20 * 8 / 6) and b['over_1_volume_share'] == pytest.approx(0.2)
    assert s['utilisation'] == b                                        # S_z < S_xy: the bond governs everywhere
    xy = m.layer_strengths_mpa[0]
    assert s['bulk']['over_1'] == int(np.sum(u * z / xy > 1)) == 4       # past S_xy = 26.55 MPa from u = 1.2125
    # a judge leaves elements out of the stats as it leaves them out of the safety factor
    keep = u <= 1.0
    s = st.layer_check((1, 0, 0), judge=keep).stats['bond']
    assert s['over_1'] == 0 and s['max'] == pytest.approx(1.0)
    d = lc.as_dict()['stats']['bond']
    assert d == {'max': 1.25, 'p99': round(b['p99'], 4), 'over_1': 20, 'over_1_volume_mm3': round(20 * 8 / 6, 3),
                 'over_1_volume_share': 0.2}


def test_p99_is_weighted_by_volume_so_a_finer_mesh_round_a_peak_does_not_raise_it():
    """One big element at 0.3 and fifty small ones at a peak, 1.2: 50 of the 51 elements are past 1, but 0.005 % of
    the volume. By count the 99th percentile would read 1.2; by volume it reads 0.3. The volume past 1 is the same
    however finely the peak is cut."""
    m = MATERIALS['petg_cf']
    z = m.layer_strengths_mpa[1]
    sigs = [uniaxial(0.3 * z)] + [uniaxial(1.2 * z)] * 50
    st = _stand_in_of_tets(m, sigs, [10.0] + [0.1] * 50)
    s = st.layer_check((1, 0, 0)).stats['bond']
    assert s['p99'] == pytest.approx(0.3) and s['over_1'] == 50
    assert s['over_1_volume_mm3'] == pytest.approx(50 * 0.001 / 6)
    finer = _stand_in_of_tets(m, [uniaxial(0.3 * z)] + [uniaxial(1.2 * z)] * 400, [10.0] + [0.05] * 400)
    t = finer.layer_check((1, 0, 0)).stats['bond']
    assert t['over_1'] == 400 and t['over_1_volume_mm3'] == pytest.approx(s['over_1_volume_mm3'])
    assert t['p99'] == pytest.approx(0.3)
    # without volumes (a LayerCheck made by hand), the percentile counts elements
    lc = st.layer_check((1, 0, 0))
    bare = dataclasses.replace(lc, volume=None)
    assert bare.stats['bond']['p99'] == pytest.approx(1.2) and bare.stats['bond']['over_1_volume_mm3'] is None


@pytest.mark.parametrize('q', [0, 1, 50, 90, 99, 99.5, 100])
def test_the_weighted_percentile_with_equal_weights_is_numpys(q):
    v = np.random.default_rng(int(q * 10)).normal(size=257)
    assert _weighted_percentile(v, np.ones_like(v), q) == float(np.percentile(v, q, method='inverted_cdf'))


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
