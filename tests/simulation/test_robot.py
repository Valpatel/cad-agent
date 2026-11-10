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


def _stage_xml(tmp_path, *, floor=True, floating=True, timestep=.002, offset_x=0, pedestal=False):
    link = r.Link("loose", r.box_body(.1, (.02, .02, .02), center=(offset_x, 0, .03 if pedestal else .01)),
                  collisions=[r.Collision("box", (.02, .02, .02), xyz=(offset_x, 0, .03 if pedestal else .01), name="loose_geom")])
    path = r.write_mjcf(tmp_path / "stage.xml", "analytic stage", [link], [], floor=floor,
                        floating=floating, timestep=timestep)
    root = ET.parse(path).getroot()
    if pedestal:
        ET.SubElement(root.find("worldbody"), "geom", name="pedestal", type="box", size=".005 .02 .01", pos="0 0 .01")
    return ET.tostring(root)


def _stage_settle(xml, fixtures=("floor",), **kwargs):
    return r.settle_stage(xml, monitored_bodies=["loose"], fixture_geoms=list(fixtures),
                          scenario="Analytic synthetic fixture; no physical product qualification", **kwargs)


def test_stage_supported_box_stays_put_and_contact_force_balances_weight(tmp_path):
    pytest.importorskip("mujoco")
    report = _stage_settle(_stage_xml(tmp_path))
    assert report["pass"], report["findings"]
    row = report["bodies"]["loose"]
    assert row["max_com_translation_mm"] < .2 and row["max_rotation_deg"] < 1e-3
    assert row["supported_by"] == ["fixture:floor"]
    assert sum(c["normal_force_n"] for c in report["final_contacts"]) == pytest.approx(.981, rel=.02)
    assert report["completed_steps"] == 500 and report["solver_warning_counts"] and not any(report["solver_warning_counts"])
    assert report["physical_fit_verified"] is False and not report["limits"]["physical_assembly_verified"]
    assert report["effective_settings"]["rigid_bodies"][0]["mass_kg"] == .1


def test_stage_supported_classification_and_force_balance_survive_smaller_timestep(tmp_path):
    pytest.importorskip("mujoco")
    a = _stage_settle(_stage_xml(tmp_path, timestep=.002))
    b = _stage_settle(_stage_xml(tmp_path, timestep=.001))
    c = _stage_settle(_stage_xml(tmp_path, timestep=.0005))
    assert a["pass"] and b["pass"] and c["pass"]
    assert b["completed_steps"] == 1000 and c["completed_steps"] == 2000
    # The coarse .002 s transient overshoots by .0607 mm versus .001 s; do not call it converged.
    # The next refinement changes the peak by less than .02 mm, well below the .5 mm classification criterion.
    assert abs(b["bodies"]["loose"]["max_com_translation_mm"] - c["bodies"]["loose"]["max_com_translation_mm"]) < .02
    assert sum(c["normal_force_n"] for c in b["final_contacts"]) == pytest.approx(.981, rel=.02)
    assert a["inputs"]["mjcf_sha256"] != b["inputs"]["mjcf_sha256"]


def test_stage_support_removal_produces_analytic_freefall_and_preserves_failed_report(tmp_path):
    pytest.importorskip("mujoco")
    failed = _stage_settle(_stage_xml(tmp_path, floor=False), fixtures=())
    assert not failed["pass"]
    row = failed["bodies"]["loose"]
    assert row["max_com_translation_mm"] == pytest.approx(4914.81, abs=.01)
    assert row["final_linear_speed_mm_s"] == pytest.approx(9810, abs=.01)
    assert row["supported_by"] == []
    assert failed["completed_steps"] == 500 and not any(failed["solver_warning_counts"])
    supported = _stage_settle(_stage_xml(tmp_path))
    assert supported["pass"] and failed["bodies"]["loose"] == row
    assert failed["inputs"]["mjcf_sha256"] != supported["inputs"]["mjcf_sha256"]


def test_stage_box_tips_when_its_com_is_outside_a_real_narrow_support(tmp_path):
    pytest.importorskip("mujoco")
    stable = _stage_settle(_stage_xml(tmp_path, floor=False, pedestal=True), fixtures=("pedestal",))
    tipped = _stage_settle(_stage_xml(tmp_path, floor=False, pedestal=True, offset_x=.014), fixtures=("pedestal",))
    assert stable["pass"], stable["findings"]
    assert not tipped["pass"] and tipped["bodies"]["loose"]["max_rotation_deg"] > 30
    assert tipped["bodies"]["loose"]["max_com_translation_mm"] > 100


@pytest.mark.parametrize("mutation, text", [
    (lambda root: root.find("option").set("gravity", "0 0 0"), "gravity differs"),
    (lambda root: ET.SubElement(root.find("option"), "flag", contact="disable"), "must be enabled"),
    (lambda root: ET.SubElement(root.find("option"), "flag", gravity="disable"), "must be enabled"),
    (lambda root: ET.SubElement(root.find("option"), "flag", constraint="disable"), "must be enabled"),
    (lambda root: root.find("worldbody/body").remove(root.find("worldbody/body/freejoint")), "static bodies"),
    (lambda root: root.find("worldbody/body").set("gravcomp", "1"), "gravity compensation"),
    (lambda root: ET.SubElement(ET.SubElement(root, "equality"), "weld", body1="loose"), "equality/tendon"),
    (lambda root: ET.SubElement(root, "include", file="ambient.xml"), "without includes"),
    (lambda root: ET.SubElement(root.find("asset"), "mesh", name="external", file="ambient.stl"), "captured asset"),
])
def test_stage_false_stability_and_ambient_input_controls_reject_before_integration(tmp_path, mutation, text):
    pytest.importorskip("mujoco")
    root = ET.fromstring(_stage_xml(tmp_path))
    mutation(root)
    report = _stage_settle(ET.tostring(root))
    assert not report["pass"] and text in report["findings"][0]["message"]
    assert report["completed_steps"] == 0 and report["inputs"]["mjcf_sha256"]


@pytest.mark.parametrize("fixtures", [(), ("unknown",), ("floor", "loose_geom")])
def test_stage_requires_exact_explicit_fixed_fixture_coverage(tmp_path, fixtures):
    pytest.importorskip("mujoco")
    report = _stage_settle(_stage_xml(tmp_path), fixtures=fixtures)
    assert not report["pass"] and report["completed_steps"] == 0


def test_stage_stacked_free_groups_need_a_force_path_through_each_other_to_the_fixture(tmp_path):
    import copy
    pytest.importorskip("mujoco")
    root = ET.fromstring(_stage_xml(tmp_path))
    upper = copy.deepcopy(root.find("worldbody/body"))
    upper.set("name", "upper"); upper.set("pos", "0 0 .02")
    upper.find("freejoint").set("name", "upper_free")
    upper.find("geom").set("name", "upper_geom")
    root.find("worldbody").append(upper)
    report = r.settle_stage(ET.tostring(root), monitored_bodies=["loose", "upper"], fixture_geoms=["floor"],
                            scenario="Synthetic stacked independent rigid bodies")
    assert report["pass"], report["findings"]
    assert report["bodies"]["upper"]["supported_by"] == ["fixture:floor"]
    assert report["bodies"]["loose"]["supported_by"] == ["fixture:floor"]
    missing = _stage_settle(ET.tostring(root))
    assert not missing["pass"] and "cover every dynamic" in missing["findings"][0]["message"]


def test_stage_solver_warning_or_reset_cannot_become_an_apparent_stage_settle(tmp_path, monkeypatch):
    mj = pytest.importorskip("mujoco")
    original = mj.mj_step

    def warning(model, data):
        original(model, data)
        data.warning[0].number += 1

    monkeypatch.setattr(mj, "mj_step", warning)
    report = _stage_settle(_stage_xml(tmp_path))
    assert not report["pass"] and "solver warning" in report["findings"][-1]["message"]
    assert report["completed_steps"] == 1 and report["solver_warning_counts"][0] == 1
    assert report["bodies"]["loose"]["initial_com_m"] == [0, 0, .01]

    def reset(model, data):
        original(model, data)
        data.time = 0

    monkeypatch.setattr(mj, "mj_step", reset)
    report = _stage_settle(_stage_xml(tmp_path))
    assert not report["pass"] and "time reset" in report["findings"][-1]["message"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, .01, 11])
def test_stage_invalid_duration_is_a_json_safe_failure_without_optional_simulator(value):
    import json
    report = _stage_settle(b"<mujoco/>", duration_s=value)
    assert not report["pass"] and report["completed_steps"] == 0
    json.dumps(report, allow_nan=False)


def test_stage_undeclared_mesh_collision_cannot_fill_a_bore_and_claim_support(tmp_path):
    pytest.importorskip("mujoco")
    root = ET.fromstring(_stage_xml(tmp_path))
    ET.SubElement(root.find("asset"), "mesh", name="tetra", vertex="0 0 0  .01 0 0  0 .01 0  0 0 .01")
    geom = root.find("worldbody/body/geom")
    geom.set("type", "mesh"); geom.set("mesh", "tetra"); geom.attrib.pop("size")
    report = _stage_settle(ET.tostring(root))
    assert not report["pass"] and "mesh hulls" in report["findings"][0]["message"]
    assert report["completed_steps"] == 0


def test_stage_missing_optional_simulator_and_insufficient_budget_stay_unchecked(tmp_path, monkeypatch):
    from cadagent._deps import MissingDependency
    original = r.require

    def missing(module, purpose):
        if module == "mujoco":
            raise MissingDependency("optional simulator unavailable")
        return original(module, purpose)

    monkeypatch.setattr(r, "require", missing)
    report = _stage_settle(b"<mujoco/>")
    assert not report["pass"] and "unavailable" in report["findings"][0]["message"]
    assert report["completed_steps"] == 0
    monkeypatch.setattr(r, "require", original)
    pytest.importorskip("mujoco")
    report = _stage_settle(_stage_xml(tmp_path), max_steps=10)
    assert not report["pass"] and "step budget" in report["findings"][0]["message"]
    assert report["completed_steps"] == 0


def test_stage_records_original_captured_asset_bytes_and_rejects_ambient_callbacks(tmp_path, monkeypatch):
    import hashlib
    mj = pytest.importorskip("mujoco")
    asset = b"synthetic ancillary provenance only"
    report = _stage_settle(_stage_xml(tmp_path), assets={"provenance.txt": asset})
    assert report["pass"] and report["inputs"]["assets_sha256"] == {"provenance.txt": hashlib.sha256(asset).hexdigest()}
    monkeypatch.setattr(mj, "get_mjcb_passive", lambda: object())
    rejected = _stage_settle(_stage_xml(tmp_path))
    assert not rejected["pass"] and "ambient MuJoCo callbacks" in rejected["findings"][0]["message"]
    assert rejected["completed_steps"] == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_stage_limits_cannot_hide_drift_with_nonfinite_or_invalid_thresholds(value):
    with pytest.raises(ValueError):
        r.SettleLimits(translation_mm=value)


def test_stage_complete_window_retains_initial_penetration_before_relaxation():
    pytest.importorskip("mujoco")
    xml = b'''<mujoco><option timestep=".01" gravity="0 0 -9.81"/><worldbody>
      <geom name="floor" type="plane" size="1 1 .1"/>
      <body name="loose" pos="0 0 .0094"><freejoint/>
        <inertial pos="0 0 0" mass=".1" diaginertia=".0000066667 .0000066667 .0000066667"/>
        <geom name="box" type="box" size=".01 .01 .01"/>
      </body></worldbody></mujoco>'''
    report = _stage_settle(xml)
    assert not report["pass"]
    row = report["bodies"]["loose"]
    assert row["initial_penetration_mm"] == pytest.approx(.6)
    assert row["max_penetration_mm"] >= .6 - 1e-9
    assert any("max_penetration_mm" in c["message"] for c in report["findings"])


@pytest.mark.parametrize("kind", ["plane", "mesh"])
def test_stage_explicit_mask_zero_contact_pair_cannot_supply_undeclared_support(kind):
    asset = b'' if kind == "plane" else b'''<asset><mesh name="slab" vertex="-.1 -.1 -.02 .1 -.1 -.02 .1 .1 -.02
      -.1 .1 -.02 -.1 -.1 0 .1 -.1 0 .1 .1 0 -.1 .1 0"/></asset>'''
    geom = (b'<geom name="undeclared" type="plane" size="1 1 .1" contype="0" conaffinity="0"/>'
            if kind == "plane" else b'<geom name="undeclared" type="mesh" mesh="slab" contype="0" conaffinity="0"/>')
    xml = b'''<mujoco><option timestep=".002" gravity="0 0 -9.81"/>''' + asset + b'''<worldbody>
      <geom name="floor" type="plane" size="1 1 .1"/>''' + geom + b'''
      <body name="loose" pos="0 0 .01"><freejoint/>
        <inertial pos="0 0 0" mass=".1" diaginertia=".0000066667 .0000066667 .0000066667"/>
        <geom name="box" type="box" size=".01 .01 .01"/>
      </body></worldbody><contact><pair geom1="box" geom2="undeclared"/></contact></mujoco>'''
    report = _stage_settle(xml)
    assert not report["pass"] and "explicit contact pairs" in report["findings"][0]["message"]
    assert report["completed_steps"] == 0 and report["bodies"] == {}


def test_stage_nested_model_asset_cannot_read_uncaptured_ambient_includes(tmp_path):
    import hashlib
    # The independent original control passed with different effective masses but identical captured input hashes.
    # Keep the same real MJCF route and change only the uncaptured dependency; reject before native compilation.
    ambient = tmp_path / "ambient.xml"
    child = f'<mujoco><include file="{ambient}"/></mujoco>'.encode()
    xml = b'''<mujoco><option timestep=".002" gravity="0 0 -9.81"/>
      <asset><model name="child" file="child.xml"/></asset><worldbody>
      <geom name="floor" type="plane" size="1 1 .1"/>
      <attach model="child" prefix="attached-"/></worldbody></mujoco>'''
    reports = []
    for mass in (".1", ".2"):
        ambient.write_text(f'''<mujocoinclude><worldbody><body name="loose" pos="0 0 .01"><freejoint/>
          <inertial pos="0 0 0" mass="{mass}" diaginertia=".0000066667 .0000066667 .0000066667"/>
          <geom name="box" type="box" size=".01 .01 .01"/>
          </body></worldbody></mujocoinclude>''')
        report = r.settle_stage(xml, monitored_bodies=["attached-loose"], fixture_geoms=["floor"],
                                scenario="Synthetic nested-resource counterexample", assets={"child.xml": child})
        assert not report["pass"] and "nested model assets" in report["findings"][0]["message"]
        assert report["completed_steps"] == 0 and report["bodies"] == {}
        reports.append(report)
    assert reports[0]["inputs"] == reports[1]["inputs"]
    assert reports[0]["inputs"]["assets_sha256"]["child.xml"] == hashlib.sha256(child).hexdigest()


def test_stage_initial_forward_warnings_are_rejected_before_any_integration(tmp_path, monkeypatch):
    mj = pytest.importorskip("mujoco")
    forward = mj.mj_forward

    def initial_warning(model, data):
        forward(model, data)
        data.warning[0].number += 1

    monkeypatch.setattr(mj, "mj_forward", initial_warning)
    report = _stage_settle(_stage_xml(tmp_path))
    assert not report["pass"] and "solver warning" in report["findings"][0]["message"]
    assert report["completed_steps"] == 0 and report["solver_warning_counts"][0] == 1
