"""Mesh control in cadagent.simulation.fea (#144): local refinement, the mesher's identity, how well the mesh resolves
the design peak, slivers before meshing and the mesher's refusals. Meshes stay small so the suite stays fast."""
import gc
import math
import platform
import re
import warnings
import weakref

import numpy as np
import pytest

cq = pytest.importorskip('cadquery')
gmsh = pytest.importorskip('gmsh')
pytest.importorskip('skfem')

from cadagent.simulation.fea import (MAX_ELEMENT_OVER_RADIUS, MIN_ELEMENTS_ACROSS, Material, MeshRefusal,  # noqa: E402
                                     MeshWarning, Study, parse_gmsh_refusal, plane_at)

STEEL = Material('steel', 200000, 0.3, 250, 7.85)


def _edges(st, sel):
    """Mean edge length of the selected tetrahedra."""
    P, T = st.points, st.tets[sel]
    return float(np.mean([np.linalg.norm(P[T[:, i]] - P[T[:, j]], axis=1).mean() for i in range(4) for j in range(i + 1, 4)]))


def _edges_at(st, point):
    """Mean edge length of the tetrahedra round the mesh node nearest a point."""
    node = int(np.argmin(np.linalg.norm(st.points - np.asarray(point, float), axis=1)))
    return _edges(st, (st.tets == node).any(axis=1))


def _bracket(t=4.0, leg=20.0, w=2.0, fillet=0.0):
    """An L-bracket in the XZ plane, `w` thick along Y, with its inside corner at (t, *, t), sharp or filleted."""
    s = cq.Workplane('XZ').polyline([(0, 0), (leg, 0), (leg, t), (t, t), (t, leg), (0, leg)]).close().extrude(-w)
    if fillet:
        s = s.edges('|Y').edges(cq.selectors.NearestToPointSelector((t, w / 2, t))).fillet(fillet)
    return s


def _slit(gap):
    """A round block with a thin annular slit (inner wall R5, outer wall R5 + gap) from its top, the two walls'
    seams 9° apart, so their surface meshes do not line up: at a 0.02 mm gap the triangles of one cut the other."""
    base = cq.Workplane('XY').circle(10).extrude(20)
    outer = cq.Workplane('XY').workplane(offset=10).circle(5 + gap).extrude(11).rotate((0, 0, 0), (0, 0, 1), 9)
    inner = cq.Workplane('XY').workplane(offset=9).circle(5).extrude(13)
    return base.cut(outer.cut(inner))


def _step(fillet):
    """A 10 mm wide bar 12 mm deep stepping down to 8 mm at x = 15, with an inside fillet at the step."""
    s = cq.Workplane('XZ').polyline([(0, 0), (40, 0), (40, 8), (15, 8), (15, 12), (0, 12)]).close().extrude(-10)
    return s.edges('|Y').edges(cq.selectors.NearestToPointSelector((15, 5, 8))).fillet(fillet)


# --- local refinement
def test_refine_makes_the_mesh_fine_near_the_point_and_leaves_the_rest():
    """A Ball field of 0.5 mm round one corner of a 4 mm mesh: the elements there come out near 0.5 mm, and beyond
    the ball and its transition the mesh is the unrefined one (the global floor is kept there by the size callback)."""
    shape = cq.Workplane('XY').box(40, 20, 10)
    p, r, s, mesh = np.array([20.0, 10.0, 5.0]), 3.0, 0.5, 4.0
    plain = Study(shape, STEEL, mesh_mm=mesh, name='box')
    fine = Study(shape, STEEL, mesh_mm=mesh, name='box', refine=[(p, r, s)])
    reach = r + 2 * (mesh - s)                        # the ball and its transition

    def zones(st):
        d = np.linalg.norm(st.points[st.tets].mean(axis=1) - p, axis=1)
        return d < r, d > reach + mesh
    near_p, far_p = zones(plain)
    near_f, far_f = zones(fine)
    assert _edges_at(fine, p) < 2 * s < _edges_at(plain, p) / 2
    assert near_f.sum() > 20 * max(near_p.sum(), 1)
    assert _edges(fine, far_f) == pytest.approx(_edges(plain, far_p), rel=0.05)
    assert far_f.sum() == pytest.approx(far_p.sum(), rel=0.15)
    assert fine.refine == [((20.0, 10.0, 5.0), 3.0, 0.5)]


def test_refine_entries_are_checked_before_meshing():
    box = cq.Workplane('XY').box(10, 10, 10)
    for bad, match in (([((0, 0, 0), 2, 3.0)], 'not under mesh_mm'), ([((0, 0), 2, 1)], 'a 3D point'),
                       ([((0, 0, 0), -1, 1)], 'radius > 0'), ([(0, 0)], 'refine takes')):
        with pytest.raises(ValueError, match=match):
            Study(box, STEEL, mesh_mm=3.0, refine=bad)
    with pytest.raises(ValueError, match='slivers must be'):
        Study(box, STEEL, mesh_mm=3.0, slivers='loud')


def test_a_refined_study_is_not_kept_alive_by_the_size_callback():
    """gmsh's Python module keeps the last size callback in a global after finalize(): it holds the refine zones, not
    the Study, so a dropped Study (its mesh and solution) is freed."""
    st = Study(cq.Workplane('XY').box(20, 10, 10), STEEL, mesh_mm=5.0, name='box', refine=[((0, 0, 0), 2.0, 2.0)])
    ref = weakref.ref(st)
    del st
    gc.collect()
    assert ref() is None


def _corner_peaks(fillet):
    """The design peak of the bracket (one leg clamped, 100 N on the other) at a 2 mm mesh, then with the corner
    refined to 0.5 and 0.25 mm."""
    corner = (4 + fillet * (1 - math.sqrt(0.5)), 1.0, 4 + fillet * (1 - math.sqrt(0.5)))
    out = []
    for size in (None, 0.5, 0.25):
        st = Study(_bracket(fillet=fillet), STEEL, mesh_mm=2.0, name='bracket',
                   refine=[(corner, 1.5, size)] if size else None)
        st.fix(plane_at(0, 0.0)).force(plane_at(0, 20.0), (0, 0, -100.0))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', MeshWarning)      # the unrefined runs are under 3 elements: expected
            r = st.solve()
        out.append((r['von_mises_design_mpa'], r['mesh']['peak']))
    return out


def test_a_sharp_corner_keeps_rising_and_a_filleted_corner_converges():
    """The textbook difference, through refine=. A sharp 270° inside corner is singular: Williams (1952) gives the
    stress there as r^(λ-1), with λ the root of sin(3πλ/2) = λ (0.5445), so halving the element size multiplies the
    peak by about 2^0.455 = 1.37, and it never settles. The bounds below show a peak that keeps rising, not that rate
    as such (at the coarser meshes the peak sits where the corner meets a side face, a 3D vertex with its own
    exponent). An R1.5 fillet at the same corner stays within a few percent:
    a corner-node peak carries about 2 % of mesh noise (moving the ball's centre by 1e-5 mm moves it that much)."""
    from scipy.optimize import brentq
    lam = brentq(lambda x: math.sin(1.5 * math.pi * x) - x, 0.3, 0.9)
    assert lam == pytest.approx(0.5445, abs=1e-4)
    sharp = _corner_peaks(0.0)
    s0, s1, s2 = (v for v, _ in sharp)
    assert s1 > 1.3 * s0 and s2 > 1.2 * s1               # still rising at 0.25 mm
    assert 1.2 < s2 / s1 < 1.6                           # near the Williams rate 2^(1-λ) = 1.37 for a halving
    for _, peak in sharp:
        assert 'sharp inside corner' in peak['where']
    assert 'singular' in sharp[-1][1]['note'] and sharp[-1][1]['wall_resolved']   # resolved, and still not a result
    fil = _corner_peaks(1.5)
    f0, f1, f2 = (v for v, _ in fil)
    assert max(f0, f1, f2) / min(f0, f1, f2) < 1.05 and abs(f2 / f1 - 1) < 0.03
    assert all('R1.5 inside fillet' in peak['where'] for _, peak in fil)
    assert fil[-1][1]['note'] == ''


# --- the mesher's identity and the peak's resolution
def test_result_names_the_mesher_and_the_platform():
    st = Study(cq.Workplane('XY').box(30, 10, 10).translate((15, 0, 0)), STEEL, mesh_mm=5.0, name='bar')
    st.fix(plane_at(0, 0.0)).force(plane_at(0, 30.0), (0, 0, -10.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', MeshWarning)
        mesh = st.solve()['mesh']
    who = mesh['mesher']
    assert who['gmsh'] == gmsh.__version__
    assert who['occ'] is None or re.fullmatch(r'\d+\.\d+(\.\d+)*', who['occ'])
    assert who['platform']['machine'] == platform.machine() and who['platform']['system'] == platform.system()
    lib = who['library']
    assert lib['file'] is None or ('/' not in lib['file'] and '\\' not in lib['file'])   # a name, never a path
    assert lib['sha256_16'] is None or re.fullmatch(r'[0-9a-f]{16}', lib['sha256_16'])
    assert 'host' not in str(who['build']).lower()
    assert mesh['refine'] == [] and mesh['slivers'] == {'faces': [], 'edges': []}


@pytest.mark.parametrize('thick, mesh, resolved', [(2.0, 2.0, False), (10.0, 2.0, True)])
def test_a_peak_in_a_thin_wall_is_flagged(thick, mesh, resolved):
    """A cantilever's root peak: the wall found by the rays is the beam's depth, and a 2 mm plate meshed at 2 mm puts
    one element across it, which is flagged (a MeshWarning and wall_resolved False); a 10 mm beam at 2 mm is not."""
    st = Study(cq.Workplane('XY').box(40, 10, thick).translate((20, 0, 0)), STEEL, mesh_mm=mesh, name='beam')
    st.fix(plane_at(0, 0.0)).force(plane_at(0, 40.0), (0, 0, -10.0))
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter('always')
        peak = st.solve()['mesh']['peak']
    flagged = [w for w in got if w.category is MeshWarning]
    assert peak['wall_mm'] == pytest.approx(thick, rel=0.02)
    assert peak['elements_across'] == pytest.approx(thick / peak['element_mm'], abs=0.06)
    assert peak['wall_resolved'] is resolved and (peak['elements_across'] >= MIN_ELEMENTS_ACROSS) is resolved
    assert peak['at_mm'][0] < 10 and abs(abs(peak['at_mm'][2]) - thick / 2) < 1e-6   # at the root, on the surface
    if resolved:
        assert not flagged and peak['note'] == ''
    else:
        assert len(flagged) == 1 and 'not a result' in str(flagged[0].message) and 'not a result' in peak['note']


def test_a_peak_on_a_fillet_with_elements_larger_than_its_radius_is_flagged():
    """The wall count passes a fillet the mesh does not resolve: at 4 mm, the step's R0.5 fillet peak has 5 elements
    across its 8 mm wall but 1.5 mm elements on a 0.5 mm radius, and reads about 9 % low (604 MPa against about 660
    refined). One 0.75 x step moves it only 2.3 %, so the radius check flags it, and converge() does not call two
    under-resolved meshes converged. Refined to elements under the radius, an R1 fillet passes both."""
    def study(fillet, mesh, size=None):
        mid = (15 + fillet * (1 - math.sqrt(0.5)), 5.0, 8 + fillet * (1 - math.sqrt(0.5)))
        st = Study(_step(fillet), STEEL, mesh_mm=mesh, name='step', refine=[(mid, 2.5, size)] if size else None)
        return st.fix(plane_at(0, 0.0)).force(plane_at(0, 40.0), (0, 0, -1000.0))
    coarse = study(0.5, 4.0)
    with pytest.warns(MeshWarning, match='larger than the radius'):
        peak = coarse.solve()['mesh']['peak']
    assert 'R0.5 inside fillet' in peak['where'] and peak['wall_resolved'] and peak['radius_mm'] == pytest.approx(0.5)
    assert peak['element_mm'] > MAX_ELEMENT_OVER_RADIUS * 0.5 and peak['radius_resolved'] is False
    assert 'refine=' in peak['note'] and 'settles' in peak['note']
    with pytest.warns(MeshWarning, match='does not resolve it either'):
        rec = coarse.converge()
    assert abs(rec['change']) < rec['tolerance'] and not rec['converged']
    fine = study(1.0, 4.0, 0.5)
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter('always')
        peak = fine.solve()['mesh']['peak']
    assert peak['radius_mm'] == pytest.approx(1.0) and peak['radius_resolved'] and peak['note'] == ''
    assert not [w for w in got if w.category is MeshWarning]


def test_a_rounded_outside_edge_is_not_a_radius_to_resolve():
    """Round a convex edge the bending stress is linear in the distance from the neutral axis, which P2 elements carry:
    a cantilever with R1 rounded edges at a 4 mm mesh (1.2 mm elements on them) peaks on a rounded edge and is not
    flagged."""
    beam = cq.Workplane('XY').box(30, 8, 8).translate((15, 0, 0)).edges('|X').fillet(1.0)
    st = Study(beam, STEEL, mesh_mm=4.0, name='beam').fix(plane_at(0, 0.0)).force(plane_at(0, 30.0), (0, 0, -100.0))
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter('always')
        peak = st.solve()['mesh']['peak']
    assert 'rounded edge' in peak['where'] and peak['radius_mm'] is None and peak['radius_resolved'] is None
    assert not [w for w in got if w.category is MeshWarning]


def test_the_wall_at_a_hole_edge_is_the_plate_not_a_ray_along_the_hole():
    """A 12 mm plate bent across four Ø8 holes peaks at a hole's top edge. A ray from a hole-wall facet near that edge
    tilts with the facet and runs out through the top face 4 mm on; it went along the wall, not across it. The rays go
    along the CAD face's normal, and a grazing exit does not count, so the wall is the plate's 12 mm."""
    plate = (cq.Workplane('XY').box(120, 40, 12).faces('>Z').workplane()
             .pushPoints([(x, 0) for x in (-40, -15, 15, 40)]).hole(8).edges('|Z').fillet(3))
    st = Study(plate, STEEL, mesh_mm=4.0, name='plate')
    st.fix(plane_at(0, -60.0)).force(plane_at(0, 60.0), (0, 0, -200.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', MeshWarning)
        peak = st.solve()['mesh']['peak']
    assert 'hole' in peak['where'] and abs(peak['at_mm'][2]) == pytest.approx(6.0)
    assert peak['wall_mm'] == pytest.approx(12.0, rel=0.01)


def test_converge_compares_a_finer_mesh():
    """converge(): the same loads on a mesh 0.75 x as fine. The filleted corner holds (converged, no warning); the
    sharp one rises by more than 5 % (not converged, a MeshWarning that names the singular corner)."""
    def study(fillet):
        corner = (4 + fillet * (1 - math.sqrt(0.5)), 1.0, 4 + fillet * (1 - math.sqrt(0.5)))
        st = Study(_bracket(fillet=fillet), STEEL, mesh_mm=2.0, name='bracket', refine=[(corner, 1.5, 0.5)])
        st.fix(plane_at(0, 0.0)).force(plane_at(0, 20.0), (0, 0, -100.0))
        return st
    fil = study(1.5)
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter('always')
        rec = fil.converge()
    assert rec['converged'] and abs(rec['change']) < 0.02 and rec['mesh_mm'] == [2.0, 1.5]
    assert rec['tets'][1] > rec['tets'][0] and fil.result['mesh']['convergence'] is rec
    assert fil.finer.mesh_mm == 1.5 and fil.finer.refine[0][2] == pytest.approx(0.375)
    assert fil.finer.fixed == fil.fixed and [ld.faces for ld in fil.finer.loads] == [ld.faces for ld in fil.loads]
    assert not [w for w in got if w.category is MeshWarning]
    sharp = study(0.0)
    with pytest.warns(MeshWarning, match='not converged.*sharp re-entrant corner'):
        rec = sharp.converge()
    assert not rec['converged'] and rec['change'] > 0.05
    with pytest.raises(ValueError, match='between 0 and 1'):
        sharp.converge(factor=1.5)


def test_converge_never_passes_a_sharp_corner_whose_two_meshes_agree():
    """Two meshes of a singular corner can agree by chance. Refined to 0.25 mm, the L-bracket's sharp corner read 1094
    MPa, and 1114 MPa (+1.8 %) at 0.1875 mm on gmsh 4.15.2, and converge() called it converged; at 0.125 mm it reads
    1448 (#167). So a peak at a sharp inside corner never passes, whatever the change. With the tolerance at 100 % the
    change always passes, on any gmsh build, and the finer mesh resolves the 0.5 mm refined peak: only the corner rule
    can fail it."""
    st = Study(_bracket(), STEEL, mesh_mm=2.0, name='bracket', refine=[((4.0, 1.0, 4.0), 1.5, 0.5)])
    st.fix(plane_at(0, 0.0)).force(plane_at(0, 20.0), (0, 0, -100.0))
    with pytest.warns(MeshWarning, match='by chance.*sharp re-entrant corner'):
        rec = st.converge(tolerance=1.0)
    assert 'sharp inside corner' in st.result['mesh']['peak']['where']
    fine = st.finer.result['mesh']['peak']
    assert fine['wall_resolved'] is not False and fine['radius_resolved'] is not False
    assert abs(rec['change']) <= rec['tolerance'] and not rec['converged']


# --- slivers before meshing
def test_sliver_faces_and_edges_are_found_before_meshing():
    """Two 20 mm blocks stacked 0.003 mm out of line leave 0.003 mm wide strip faces (0.06 mm², under (3/10)² = 0.09)
    and 0.003 mm edges: listed in Study.slivers, a MeshWarning by default, a MeshRefusal on request, nothing when
    ignored. A refine ball round a strip's centre leaves the rest of the strip at 3 mm, so the strip still counts."""
    strip = cq.Workplane('XY').box(20, 20, 10).union(cq.Workplane('XY').box(20, 20, 10).translate((0.003, 0, 10)))
    with pytest.raises(MeshRefusal) as caught:
        Study(strip, STEEL, mesh_mm=3.0, name='strip', slivers='raise')
    err = caught.value
    assert err.what == 'slivers' and len(err.faces) == 2 and len(err.edges) == 4
    assert all(f['area_mm2'] == pytest.approx(0.06, rel=1e-3) and f['under_mm2'] == pytest.approx(0.09) for f in err.faces)
    assert all(f['why'] == 'small' and f['width_mm'] == pytest.approx(0.003, rel=1e-2) for f in err.faces)
    assert all(e['length_mm'] == pytest.approx(0.003, rel=1e-3) for e in err.edges)
    assert 'sliver face' in str(err) and f"face {err.faces[0]['tag']}" in str(err)
    with pytest.warns(MeshWarning, match='2 sliver face'):
        st = Study(strip, STEEL, mesh_mm=3.0, name='strip')
    assert len(st.slivers['faces']) == 2 and st.tets.shape[0] > 0
    with warnings.catch_warnings():
        warnings.simplefilter('error', MeshWarning)
        quiet = Study(strip, STEEL, mesh_mm=3.0, name='strip', slivers='ignore')
        assert len(quiet.slivers['edges']) == 4                     # still recorded
        clean = Study(cq.Workplane('XY').box(20, 20, 10), STEEL, mesh_mm=3.0, name='block', slivers='raise')
        assert clean.slivers == {'faces': [], 'edges': []}
    local = Study(strip, STEEL, mesh_mm=3.0, name='strip', slivers='ignore',     # balls round the strips' centres only
                  refine=[((-9.998, 0, 5), 0.5, 0.5), ((10.002, 0, 5), 0.5, 0.5)])
    assert len(local.slivers['faces']) == 2 and len(local.slivers['edges']) == 4


def test_a_small_feature_inside_a_refine_ball_is_not_a_sliver():
    """A 0.25 mm cube on a block: its faces (0.0625 mm²) and edges are slivers for a 3 mm mesh. Inside a 0.5 mm refine
    ball that covers all of it, the cut is (0.5/10)² and 0.05 mm, so it meshes without a word."""
    boss = cq.Workplane('XY').box(20, 20, 10).union(cq.Workplane('XY').box(0.25, 0.25, 0.25).translate((0, 0, 5.125)))
    with pytest.raises(MeshRefusal) as caught:
        Study(boss, STEEL, mesh_mm=3.0, name='boss', slivers='raise')
    assert len(caught.value.faces) == 5 and len(caught.value.edges) == 12
    st = Study(boss, STEEL, mesh_mm=3.0, name='boss', slivers='raise', refine=[((0, 0, 5.125), 1.0, 0.5)])
    assert st.slivers == {'faces': [], 'edges': []}


def test_a_narrow_face_is_a_sliver_too():
    """The 0.02 mm slit's floor is a ring 0.02 mm wide and 0.63 mm² (over the 0.09 mm² cut): area alone passes it. Its
    width, 2 x area / perimeter, is 0.02 mm, under 3/10, so slivers='raise' stops there, before gmsh refuses it."""
    with pytest.raises(MeshRefusal) as caught:
        Study(_slit(0.02), STEEL, mesh_mm=3.0, name='slit', slivers='raise')
    (ring,) = caught.value.faces
    assert caught.value.what == 'slivers' and ring['why'] == 'narrow' and ring['area_mm2'] > ring['under_mm2']
    assert ring['width_mm'] == pytest.approx(0.02, rel=0.01) and '0.02 mm wide' in str(caught.value)


def test_a_small_compact_face_is_not_narrow():
    """Narrow means thin and long (perimeter² / 4π·area over 3). The corner triangles of 0.5 mm chamfers on every edge
    are 0.22 mm² (over the 0.09 mm² cut at 3 mm) and 0.2 mm "wide", but compact (1.65): they mesh normally, so the
    part is clean, even with slivers='raise'."""
    st = Study(cq.Workplane('XY').box(40, 20, 10).edges().chamfer(0.5), STEEL, mesh_mm=3.0, name='box', slivers='raise')
    assert st.slivers == {'faces': [], 'edges': []} and len(st.tets) > 0


# --- the mesher's refusals
RECORDED = [   # gmsh 4.15.2 (PyPI, x86-64) on _slit(0.02) at a 3 mm mesh, with errors logged rather than thrown
    'Info:  - Recovering boundary',
    'Error: PLC Error:  A segment and a facet intersect at point',
    'Info:  (0.910726,-4.90883,12.3041).',
    'Info:   Segment: [838,837] #-1 (0)',
    'Info:   Facet:   [528,529,532] #6',
    'Error: Invalid boundary mesh (segment-facet intersection) on surface 6, intersection (0.910726,-4.90883,12.3041)',
    'Progress: Meshing 3D...',
    'Warning: No elements in volume 1',
]


def test_the_refusal_parser_reads_gmsh_logs():
    why = parse_gmsh_refusal(RECORDED)
    assert why['what'] == 'segment-facet intersection'
    assert why['point'] == [0.910726, -4.90883, 12.3041] and why['surfaces'] == [6] and why['curves'] == []
    assert why['message'] == 'PLC Error:  A segment and a facet intersect at point' and len(why['log']) == 5
    thrown = parse_gmsh_refusal(['Error: PLC Error:  A segment and a facet intersect at point'])   # what gmsh throws
    assert thrown['point'] is None and thrown['what'] == 'A segment and a facet intersect'
    inline = parse_gmsh_refusal(['Error: PLC Error:  Two segments intersect at point (1,-2.5,3e-1).'])
    assert inline['point'] == [1.0, -2.5, 0.3] and inline['what'] == 'Two segments intersect'
    both = parse_gmsh_refusal(['Error: Invalid boundary mesh (overlapping facets) on surface 3 surface 8 curve 12'])
    assert both['what'] == 'overlapping facets' and both['surfaces'] == [3, 8] and both['curves'] == [12]
    assert both['point'] is None
    assert parse_gmsh_refusal(['Info: Meshing 3D...', 'Error: Unable to recover the edge 4']) is None
    gave_up = parse_gmsh_refusal(['Info:  - Recovering boundary', 'Error: Could not recover boundary mesh: error 2'])
    assert gave_up['what'] == 'boundary recovery failed' and gave_up['point'] is None
    assert gave_up['message'] == 'Could not recover boundary mesh: error 2' and len(gave_up['log']) == 1


def test_a_recorded_refusal_names_the_nearest_faces():
    """The recorded log on the same block with a 0.5 mm slit, which meshes (same faces, same tags): the point is
    0.007 mm from the R5 inner wall, which gmsh named, and 0.5 mm from the R5.5 outer wall (less to its surface
    triangles: their chords cut inside the circle by up to 3²/(8 x 5.5) = 0.2 mm)."""
    st = Study(_slit(0.5), STEEL, mesh_mm=3.0, name='slit')
    with pytest.raises(MeshRefusal) as caught:
        st._refuse([m for m in RECORDED if m.startswith('Error')], RECORDED)
    err = caught.value
    assert err.what == 'segment-facet intersection' and err.point == [0.910726, -4.90883, 12.3041]
    first, second = err.faces[:2]
    assert (first['tag'], first['kind'], first['named_by_gmsh']) == (6, 'Cylinder', True)
    assert first['radius_mm'] == pytest.approx(5.0) and first['area_mm2'] == pytest.approx(math.pi * 10 * 10, rel=1e-4)
    assert first['distance_mm'] < 0.05 and second['tag'] == 4 and 0.5 - 0.21 < second['distance_mm'] < 0.51
    assert len(err.edges) == 3 and all(e['length_mm'] > 0 for e in err.edges)
    msg = str(err)
    assert 'face 6 (Cylinder, 314.159 mm²' in msg and 'named by gmsh' in msg and 'refine=' in msg
    assert st.faces_near(err.point, k=2) == [{k: v for k, v in f.items() if k != 'named_by_gmsh'} for f in err.faces[:2]]


def test_a_live_refusal_names_the_two_walls():
    """gmsh refuses the 0.02 mm slit (its surface meshes cut each other); the Study says where, and which faces: the
    slit's two walls, R5 and R5.02, both at the point. gmsh 4.15.2 (PyPI, x86-64) refuses it with a segment-facet
    intersection. A build that meshes it, refuses it with no point, or fails it another way skips: the recorded-log
    tests cover the parser and the lookup."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', MeshWarning)        # the slit's floor ring: a narrow face, listed first
            Study(_slit(0.02), STEEL, mesh_mm=3.0, name='slit')
    except MeshRefusal as err:
        if err.point is None:
            pytest.skip(f'gmsh {gmsh.__version__} refuses the 0.02 mm slit without a point ({err.what})')
        assert {f['tag'] for f in err.faces[:2]} == {4, 6}
        assert sorted(f['radius_mm'] for f in err.faces[:2]) == pytest.approx([5.0, 5.02])
        assert all(f['distance_mm'] < 0.05 for f in err.faces[:2]) and 'Nearest faces: face' in str(err)
        if err.what == 'segment-facet intersection':
            assert 'PLC Error' in str(err) and any('PLC Error' in line for line in err.log)
            assert any(f['named_by_gmsh'] for f in err.faces)
    except Exception as exc:                                    # gmsh's own errors are bare Exceptions
        if type(exc) not in (Exception, RuntimeError):
            raise
        pytest.skip(f'gmsh {gmsh.__version__} fails the 0.02 mm slit another way: {str(exc)[:120]}')
    else:
        pytest.skip(f'gmsh {gmsh.__version__} meshes the 0.02 mm slit on this build')


def test_a_shelled_box_too_thin_for_its_mesh_is_a_refusal():
    """A 2 mm shell with R1 inside corners at a 4 mm mesh: gmsh 4.15.2 throws 'Could not recover boundary mesh: error
    2' (sometimes the PLC line instead), which used to reach the caller as gmsh's bare Exception. It is a MeshRefusal
    now, with the faces when gmsh gives a point. A build that meshes it skips."""
    box = cq.Workplane('XY').box(60, 40, 30).edges().fillet(3).faces('>Z').shell(-2)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', MeshWarning)
            Study(box, STEEL, mesh_mm=4.0, name='shell')
    except MeshRefusal as err:
        assert 'would not mesh the volume' in str(err) and 'mesh finer there' in str(err)
        assert (err.point is None) == (err.faces == []) and err.log
    else:
        pytest.skip(f'gmsh {gmsh.__version__} meshes the 2 mm shell at 4 mm on this build')


def test_a_retry_that_meshes_is_used_with_a_warning(monkeypatch):
    """gmsh's boundary recovery is not always repeatable on a marginal part: when the first try throws and the logged
    second try meshes, the study uses that mesh and says so, with the warning on the caller's Study(...) line."""
    real, calls = gmsh.model.mesh.generate, []
    def flaky(dim=3):
        calls.append(dim)
        if len(calls) == 1:
            raise Exception('Could not recover boundary mesh: error 2')
        return real(dim)
    monkeypatch.setattr(gmsh.model.mesh, 'generate', flaky)
    with pytest.warns(MeshWarning, match='second try') as got:
        st = Study(cq.Workplane('XY').box(10, 10, 10), STEEL, mesh_mm=5.0, name='cube')
    assert len(calls) == 2 and len(st.tets) > 0
    assert [w.filename for w in got if w.category is MeshWarning] == [__file__]
