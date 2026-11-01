"""Robot export: mass properties, body arithmetic, URDF writing and checking."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from cadagent.simulation import robot as r


def test_box_inertia_matches_the_textbook():
    b = r.box_body(12.0, (1.0, 2.0, 3.0))
    assert b.inertia[0][0] == pytest.approx(13.0) and b.inertia[1][1] == pytest.approx(10.0)
    assert b.inertia[2][2] == pytest.approx(5.0)


def test_hollow_cylinder_axial_inertia():
    b = r.cylinder_body(2.0, 0.1, 0.05, axis="y", hollow_radius=0.05)
    assert b.inertia[1][1] == pytest.approx(2.0 * (0.01 + 0.0025) / 2)


def test_combine_uses_the_parallel_axis_theorem():
    a = r.point_body(1.0, (-1.0, 0.0, 0.0))
    b = r.point_body(1.0, (1.0, 0.0, 0.0))
    c = a + b
    assert c.mass == 2.0 and c.com == pytest.approx((0, 0, 0))
    assert c.inertia[1][1] == pytest.approx(2.0) and c.inertia[2][2] == pytest.approx(2.0)
    assert c.inertia[0][0] == pytest.approx(0.0)


def test_rotation_moves_the_long_axis():
    b = r.box_body(1.0, (0.1, 0.1, 1.0)).rotated(r.rot_x(90))
    assert b.inertia[1][1] == pytest.approx(1.0 * (0.01 + 0.01) / 12)  # the long axis now lies along y
    assert b.inertia[2][2] == pytest.approx(1.0 * (0.01 + 1.0) / 12)


def test_printed_fill_is_solid_for_thin_parts_and_sparse_for_thick_ones():
    assert r.printed_fill(1000.0, 10000.0) == pytest.approx(1.0)
    thick = r.printed_fill(1_000_000.0, 60_000.0, wall_mm=1.6, infill=0.15)
    assert 0.15 < thick < 0.4


def test_inertia_problems_catch_bad_tensors():
    assert r.inertia_problems(1.0, ((1, 0, 0), (0, 1, 0), (0, 0, 1))) == []
    assert any("triangle" in p for p in r.inertia_problems(1.0, ((1, 0, 0), (0, 1, 0), (0, 0, 3))))
    assert any("positive definite" in p for p in r.inertia_problems(1.0, ((1, 0, 0), (0, 0, 0), (0, 0, 1))))
    assert any("mass" in p for p in r.inertia_problems(0.0, ((1, 0, 0), (0, 1, 0), (0, 0, 1))))


def test_tree_problems_reject_loops_and_two_parents():
    links = ["base", "a", "b"]
    assert r.tree_problems(links, [("base", "a", "j1"), ("a", "b", "j2")]) == []
    two = r.tree_problems(links, [("base", "a", "j1"), ("base", "b", "j2"), ("a", "b", "j3")])
    assert any("two parents" in p for p in two)


def _robot(tmp_path, mesh=True):
    (tmp_path / "meshes").mkdir()
    if mesh:
        (tmp_path / "meshes" / "base.stl").write_text("solid x\nendsolid x\n")
    links = [r.Link("base", r.box_body(2.0, (0.2, 0.2, 0.1)), [r.Visual("meshes/base.stl", rgba=(1, 0.5, 0, 1), material="orange")],
                    [r.Collision("box", (0.2, 0.2, 0.1))]),
             r.Link("wheel", r.cylinder_body(0.5, 0.08, 0.04, axis="y"), [], [r.Collision("cylinder", (0.08, 0.04), rpy=(1.5708, 0, 0))])]
    joints = [r.Joint("wheel_joint", "continuous", "base", "wheel", xyz=(0, 0.12, -0.1), axis=(0, 1, 0), effort=5.0, velocity=40.0)]
    return r.write_urdf(tmp_path / "bot.urdf", "bot", links, joints, comment="test")


def test_write_and_check_urdf(tmp_path):
    path = _robot(tmp_path)
    res = r.check_urdf(path)
    assert res["pass"] is True, res["problems"]
    assert res["total_mass_kg"] == pytest.approx(2.5) and res["moving_joints"] == 1
    root = ET.parse(path).getroot()
    assert root.find("joint/limit").get("effort") == "5"
    assert root.find("material/color").get("rgba") == "1 0.5 0 1"


def test_check_urdf_reports_a_missing_mesh(tmp_path):
    res = r.check_urdf(_robot(tmp_path, mesh=False))
    assert res["pass"] is False and any("missing" in p for p in res["problems"])


def test_write_urdf_refuses_a_closed_loop(tmp_path):
    links = [r.Link("base", r.point_body(1.0)), r.Link("a", r.point_body(1.0)), r.Link("b", r.point_body(1.0))]
    joints = [r.Joint("j1", "fixed", "base", "a"), r.Joint("j2", "fixed", "base", "b"), r.Joint("j3", "fixed", "a", "b")]
    with pytest.raises(ValueError, match="closed loop"):
        r.write_urdf(tmp_path / "x.urdf", "x", links, joints)


def test_solid_mass_properties_of_a_cad_box():
    cq = pytest.importorskip("cadquery")
    shape = cq.Workplane().box(100, 20, 10).val().translate((50, 0, 0))
    b = r.solid_mass_properties(shape, density_g_cm3=1.24)
    assert b.mass == pytest.approx(0.0248)  # 20 cm^3 of PLA at 1.24 g/cm^3
    assert b.com == pytest.approx((0.05, 0, 0), abs=1e-9)
    assert b.inertia[2][2] == pytest.approx(0.0248 * (0.1 ** 2 + 0.02 ** 2) / 12, rel=1e-6)
    printed, rep = r.printed_part_body(shape, 1.24, wall_mm=1.6, infill=0.15)
    assert rep["estimate"] is True and printed.mass < b.mass


def test_rpy_to_quat_matches_known_rotations():
    assert r.rpy_to_quat((0, 0, 0)) == pytest.approx((1, 0, 0, 0))
    q = r.rpy_to_quat((r.math.pi / 2, 0, 0))
    assert q == pytest.approx((r.math.sqrt(0.5), r.math.sqrt(0.5), 0, 0))


def test_mjcf_loads_in_mujoco_with_the_same_mass(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    links = [r.Link("base", r.box_body(2.0, (0.2, 0.2, 0.1)), [], [r.Collision("box", (0.2, 0.2, 0.1))]),
             r.Link("wheel", r.cylinder_body(0.5, 0.08, 0.04, axis="y"), [], [r.Collision("cylinder", (0.08, 0.04), rpy=(r.math.pi / 2, 0, 0))])]
    joints = [r.Joint("wheel_joint", "continuous", "base", "wheel", xyz=(0, 0.12, -0.1), axis=(0, 1, 0), effort=5.0,
                      velocity=40.0, armature=0.001, damping=0.01)]
    path = r.write_mjcf(tmp_path / "bot.xml", "bot", links, joints, [r.Motor("wheel_joint", 5.0)], imu_link="base")
    m = mujoco.MjModel.from_xml_path(str(path))
    assert sum(m.body_mass) == pytest.approx(2.5)
    assert m.nu == 1 and m.actuator_ctrlrange[0] == pytest.approx([-5, 5])
    assert m.dof_armature[-1] == pytest.approx(0.001)
    d = mujoco.MjData(m)
    mujoco.mj_step(m, d)
    assert d.sensor("imu_quat").data.shape == (4,)


def test_mjcf_collision_filtering_and_friction(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    links = [r.Link("base", r.box_body(1.0, (0.1, 0.1, 0.1)), [], [r.Collision("box", (0.1, 0.1, 0.1), contype=2, conaffinity=1)]),
             r.Link("wheel", r.cylinder_body(0.5, 0.05, 0.02, axis="y"), [], [r.Collision("cylinder", (0.05, 0.02), friction=(1.2, 0.01, 0.001))])]
    joints = [r.Joint("w", "continuous", "base", "wheel", xyz=(0, 0.1, 0), axis=(0, 1, 0), effort=1.0)]
    m = mujoco.MjModel.from_xml_path(str(r.write_mjcf(tmp_path / "b.xml", "b", links, joints)))
    assert m.geom("base_col0").contype == 2 and m.geom("base_col0").conaffinity == 1
    assert m.geom("wheel_col0").friction[0] == pytest.approx(1.2)


def test_primitive_visuals_in_urdf_and_mjcf(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    links = [r.Link("base", r.box_body(1.0, (0.1, 0.1, 0.1)), [r.Visual(kind="box", size=(0.1, 0.2, 0.3), rgba=(1, 0, 0, 1)),
                                                                 r.Visual(kind="cylinder", size=(0.05, 0.1), rpy=(1.5708, 0, 0))],
                    [r.Collision("box", (0.1, 0.1, 0.1))])]
    u = r.write_urdf(tmp_path / "v.urdf", "v", links, [])
    root = ET.parse(u).getroot()
    assert root.find("link/visual/geometry/box").get("size") == "0.1 0.2 0.3"
    assert r.check_urdf(u)["pass"] is True
    m = mujoco.MjModel.from_xml_path(str(r.write_mjcf(tmp_path / "v.xml", "v", links, [])))
    vis = [i for i in range(m.ngeom) if m.geom_group[i] == 1]
    assert len(vis) == 2 and m.geom_size[vis[0]][2] == pytest.approx(0.15)
    assert m.geom_rgba[vis[0]][0] == pytest.approx(1.0) and m.geom_contype[vis[0]] == 0


def test_mjcf_sites(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    links = [r.Link("base", r.box_body(1.0, (0.1, 0.1, 0.1)), sites=[("muzzle", (0.2, 0, 0.1))])]
    m = mujoco.MjModel.from_xml_path(str(r.write_mjcf(tmp_path / "s.xml", "s", links, [])))
    assert m.site("muzzle").pos == pytest.approx([0.2, 0, 0.1])


# ----------------------------------------------------------------------------- closed loops (#187)

def _bar(name, length):
    return r.Link(name, r.box_body(0.01, (length, 0.004, 0.004), center=(length / 2, 0, 0)))


def _fourbar(a=0.04, b=0.12, c=0.08, d=0.10, home_deg=40.0):
    """Norton's Example 4-1 in metres as a tree (ground, crank, coupler on the crank, rocker) built in its open pose at
    home_deg, and the pin between coupler and rocker that closes it."""
    from cadagent.mechanical import linkages as L
    ang = L.sweep_fourbar(a, b, c, d, [home_deg])["steps"][0]["angles_deg"]
    t2, t3, t4 = (math.radians(ang[k]) for k in ("theta2", "theta3", "theta4"))
    links = [r.Link("ground", r.box_body(1.0, (0.01, 0.01, 0.01))), _bar("crank", a), _bar("coupler", b), _bar("rocker", c)]
    joints = [r.Joint("crank_j", "continuous", "ground", "crank", rpy=(0, 0, t2), damping=0.002),
              r.Joint("coupler_j", "continuous", "crank", "coupler", xyz=(a, 0, 0), rpy=(0, 0, t3 - t2), damping=0.002),
              r.Joint("rocker_j", "continuous", "ground", "rocker", xyz=(d, 0, 0), rpy=(0, 0, t4), damping=0.002)]
    return links, joints, r.LoopClosure("coupler", "rocker", (b, 0, 0), other_anchor=(c, 0, 0), name="pin"), (t2, t3, t4)


def _settle(mujoco, path, held):
    """Load an MJCF without gravity, hold each joint in ``held`` at its value (rad from home) with a joint equality, and
    let MuJoCo's constraint solver move the rest. Returns the model and data."""
    root = ET.parse(path).getroot()
    eq = root.find("equality")
    for j in held:
        ET.SubElement(eq, "joint", joint1=j, polycoef="0 0 0 0 0")
    m = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
    m.opt.gravity[:] = 0
    m.opt.timestep = 0.0005
    return m, mujoco.MjData(m)


def test_mjcf_closes_a_four_bar_and_mujoco_moves_it_as_the_solver_does(tmp_path):
    # An independent check of cadagent.mechanical.linkages: MuJoCo's constraint solver turns the crank and finds the
    # coupler and rocker itself, and they land where sweep_fourbar puts them.
    mujoco = pytest.importorskip("mujoco")
    from cadagent.mechanical import linkages as L
    links, joints, loop, (t2, t3, t4) = _fourbar()
    path = r.write_mjcf(tmp_path / "fourbar.xml", "fourbar", links, joints, floating=False, floor=False, loops=[loop])
    assert '<connect body1="coupler" body2="rocker" anchor="0.12 0 0" name="pin"' in path.read_text()
    m, d = _settle(mujoco, path, ["crank_j"])
    eq = [k for k in range(m.neq) if m.eq_type[k] == mujoco.mjtEq.mjEQ_JOINT][0]
    q = {n: m.joint(n).qposadr[0] for n in ("crank_j", "coupler_j", "rocker_j")}
    # MuJoCo's pin on the rocker, from the home pose: the rocker's tip, to the 6 digits the file carries
    assert m.eq_data[0][3:6] == pytest.approx([0.08, 0, 0], abs=1e-6)
    for target in (60, 90, 150, 220, 300, 400):
        m.eq_data[eq][0] = math.radians(target) - t2
        for _ in range(4000):
            mujoco.mj_step(m, d)
        want = L.sweep_fourbar(0.04, 0.12, 0.08, 0.10, [target % 360])["steps"][0]["angles_deg"]
        got4 = math.degrees(t4 + d.qpos[q["rocker_j"]])
        got3 = math.degrees(t3 + d.qpos[q["crank_j"]] + d.qpos[q["coupler_j"]])
        # the file's 6 digits leave the pin about 1e-7 m open: a few 1e-5 degrees here
        assert math.remainder(got4 - want["theta4"], 360) == pytest.approx(0, abs=1e-4), target
        assert math.remainder(got3 - want["theta3"], 360) == pytest.approx(0, abs=1e-4), target


def test_mjcf_closes_a_five_bar_driven_by_both_cranks(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    from cadagent.mechanical import linkages as L
    a1, b1, a2, b2, dg = 0.10, 0.15, 0.09, 0.14, 0.08
    home = L.sweep_fivebar(a1, b1, a2, b2, dg, [(120, 60)])["steps"][0]["angles_deg"]
    t1, t2, p1, p2 = (math.radians(home[k]) for k in ("theta1", "theta2", "phi1", "phi2"))
    links = [r.Link("ground", r.box_body(1.0, (0.01, 0.01, 0.01))), _bar("crank1", a1), _bar("distal1", b1), _bar("crank2", a2),
             _bar("distal2", b2)]
    joints = [r.Joint("hip1", "continuous", "ground", "crank1", rpy=(0, 0, t1), damping=0.002),
              r.Joint("knee1", "continuous", "crank1", "distal1", xyz=(a1, 0, 0), rpy=(0, 0, p1 - t1), damping=0.002),
              r.Joint("hip2", "continuous", "ground", "crank2", xyz=(dg, 0, 0), rpy=(0, 0, t2), damping=0.002),
              r.Joint("knee2", "continuous", "crank2", "distal2", xyz=(a2, 0, 0), rpy=(0, 0, p2 - t2), damping=0.002)]
    loop = r.LoopClosure("distal1", "distal2", (b1, 0, 0), other_anchor=(b2, 0, 0))
    path = r.write_mjcf(tmp_path / "fivebar.xml", "fivebar", links, joints, floating=False, floor=False, loops=[loop])
    m, d = _settle(mujoco, path, ["hip1", "hip2"])
    eqs = [k for k in range(m.neq) if m.eq_type[k] == mujoco.mjtEq.mjEQ_JOINT]
    q = {n: m.joint(n).qposadr[0] for n in ("hip1", "knee1", "hip2", "knee2")}
    for target in ((110, 70), (100, 50), (135, 80), (95, 95)):
        m.eq_data[eqs[0]][0] = math.radians(target[0]) - t1
        m.eq_data[eqs[1]][0] = math.radians(target[1]) - t2
        for _ in range(4000):
            mujoco.mj_step(m, d)
        want = L.sweep_fivebar(a1, b1, a2, b2, dg, [target])["steps"][0]["angles_deg"]
        got1 = math.degrees(p1 + d.qpos[q["hip1"]] + d.qpos[q["knee1"]])
        got2 = math.degrees(p2 + d.qpos[q["hip2"]] + d.qpos[q["knee2"]])
        assert math.remainder(got1 - want["phi1"], 360) == pytest.approx(0, abs=1e-4), target
        assert math.remainder(got2 - want["phi2"], 360) == pytest.approx(0, abs=1e-4), target


def test_a_loop_closure_must_close_at_home(tmp_path):
    links, joints, loop, _ = _fourbar()
    assert r.loop_gaps(links, joints, [loop])["pin"] < 1e-6
    frames = r.home_frames(links, joints)
    assert frames["coupler"][1] == pytest.approx((0.04 * math.cos(math.radians(40)), 0.04 * math.sin(math.radians(40)), 0))
    wrong = r.LoopClosure("coupler", "rocker", (0.12, 0, 0), other_anchor=(0.081, 0, 0), name="pin")
    with pytest.raises(ValueError, match="1 mm apart at home"):
        r.write_mjcf(tmp_path / "x.xml", "x", links, joints, floating=False, loops=[wrong])
    with pytest.raises(ValueError, match="unknown link"):
        r.write_mjcf(tmp_path / "x.xml", "x", links, joints, loops=[r.LoopClosure("coupler", "frame", (0, 0, 0))])
    with pytest.raises(ValueError, match="with itself"):
        r.write_mjcf(tmp_path / "x.xml", "x", links, joints, loops=[r.LoopClosure("coupler", "coupler", (0, 0, 0))])
    # without other_anchor, nothing to check: MuJoCo takes the pin on the other link from the home pose
    r.write_mjcf(tmp_path / "y.xml", "y", links, joints, loops=[r.LoopClosure("coupler", "rocker", (0.12, 0, 0))])
    # two closures that the check (and MuJoCo) cannot tell apart are refused, the open one with them
    with pytest.raises(ValueError, match="each needs its own name"):
        r.write_mjcf(tmp_path / "z.xml", "z", links, joints, loops=[loop, wrong])


@pytest.mark.parametrize("scale", [1, 10, 30])
def test_a_closed_loop_is_accepted_at_any_home_angle_and_size(tmp_path, scale):
    # The check measures the model as given, so an exactly built loop passes whatever the file's rounding: Norton's
    # four-bar at 0.12 m to 3.6 m links, built at 52 home angles.
    for home in range(1, 360, 7):
        links, joints, loop, _ = _fourbar(*(v * scale for v in (0.04, 0.12, 0.08, 0.10)), home_deg=home + 0.123456)
        assert r.loop_gaps(links, joints, [loop])["pin"] < 1e-12 * scale
        r.write_mjcf(tmp_path / "x.xml", "x", links, joints, floating=False, floor=False, loops=[loop])
