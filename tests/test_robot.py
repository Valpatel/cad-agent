"""Robot export: mass properties, body arithmetic, URDF writing and checking."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from cadagent import robot as r


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
