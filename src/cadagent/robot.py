"""Robot description export: mass properties from CAD, links and joints, URDF writing and checking.

Mass properties come from the CAD solids, so a simulator (Isaac Sim, MuJoCo, Gazebo) sees the robot as designed:

- A **printed** part's mass is its solid volume times the filament density times an effective fill: the perimeters
  and skins are solid and the core is at the infill fraction (``printed_fill``). The inertia is the solid's inertia
  scaled to that mass, which assumes the fill is uniform. That is an estimate; weigh the printed part.
- A **bought** part (motor, battery, sensor) is a box or cylinder of its catalogue mass, placed where it sits.
- ``Body`` holds mass, centre of mass and inertia about the centre of mass, in kg, m and kg m^2. Bodies add with the
  parallel-axis theorem, so a link is the sum of everything bolted to it.

URDF cannot describe closed kinematic loops (a five-bar leg). Export such a leg as an equivalent serial chain and
keep the loop in the controller's actuator mapping, or add the loop in the simulator.

All lengths taken from CAD are in mm and converted here; everything written out is SI.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cadagent._deps import require

Vec = Tuple[float, float, float]
Mat = Tuple[Vec, Vec, Vec]

ZERO3: Mat = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


# --------------------------------------------------------------------------- bodies

@dataclass(frozen=True)
class Body:
    """Rigid body: mass (kg), centre of mass (m) and inertia about the centre of mass (kg m^2), in one frame."""

    mass: float
    com: Vec = (0.0, 0.0, 0.0)
    inertia: Mat = ZERO3
    name: str = ""

    def __add__(self, other: "Body") -> "Body":
        return combine([self, other])

    def translated(self, d: Vec) -> "Body":
        return Body(self.mass, _add(self.com, d), self.inertia, self.name)

    def rotated(self, r: Mat) -> "Body":
        """Rotate about the frame origin by the 3x3 rotation matrix ``r``."""
        return Body(self.mass, _mv(r, self.com), _mm(_mm(r, self.inertia), _t(r)), self.name)

    def inertia_about(self, point: Vec) -> Mat:
        """Inertia about ``point`` (parallel-axis theorem)."""
        return _add_m(self.inertia, _point_inertia(self.mass, _sub(self.com, point)))

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "mass_kg": round(self.mass, 6), "com_m": [round(v, 6) for v in self.com],
                "inertia_kg_m2": [[round(v, 9) for v in row] for row in self.inertia]}


def combine(bodies: Iterable[Body], name: str = "") -> Body:
    """Sum of bodies in a common frame: total mass, combined centre of mass, inertia about it."""
    bodies = [b for b in bodies if b.mass > 0]
    m = sum(b.mass for b in bodies)
    if m <= 0:
        return Body(0.0, name=name)
    com = tuple(sum(b.mass * b.com[i] for b in bodies) / m for i in range(3))
    inertia = ZERO3
    for b in bodies:
        inertia = _add_m(inertia, b.inertia_about(com))
    return Body(m, com, inertia, name)


def box_body(mass: float, size: Vec, center: Vec = (0.0, 0.0, 0.0), name: str = "") -> Body:
    """Uniform box; ``size`` and ``center`` in metres, edges along the frame axes."""
    x, y, z = size
    k = mass / 12.0
    return Body(mass, center, ((k * (y * y + z * z), 0, 0), (0, k * (x * x + z * z), 0), (0, 0, k * (x * x + y * y))), name)


def cylinder_body(mass: float, radius: float, length: float, axis: str = "z",
                  center: Vec = (0.0, 0.0, 0.0), hollow_radius: float = 0.0, name: str = "") -> Body:
    """Uniform (optionally hollow) cylinder along ``axis``; metres."""
    r2 = radius * radius + hollow_radius * hollow_radius
    ia = mass * r2 / 2.0
    it = mass * (3.0 * r2 + length * length) / 12.0
    d = {"x": (ia, it, it), "y": (it, ia, it), "z": (it, it, ia)}[axis]
    return Body(mass, center, ((d[0], 0, 0), (0, d[1], 0), (0, 0, d[2])), name)


def point_body(mass: float, at: Vec = (0.0, 0.0, 0.0), name: str = "") -> Body:
    return Body(mass, at, ZERO3, name)


# --------------------------------------------------------------------------- from CAD

def printed_fill(volume_mm3: float, area_mm2: float, wall_mm: float = 1.6, infill: float = 0.15) -> float:
    """Effective solid fraction of a printed part.

    The outer ``wall_mm`` (perimeters and top/bottom skins, taken as one thickness over the whole surface) is solid,
    and the rest is at ``infill``. Thin parts come out solid. An estimate: real slicers vary skins by face angle.
    """
    if volume_mm3 <= 0:
        return 0.0
    shell = min(volume_mm3, area_mm2 * wall_mm)
    return (shell + infill * (volume_mm3 - shell)) / volume_mm3


def solid_mass_properties(shape: Any, density_g_cm3: float, fill: float = 1.0, name: str = "") -> Body:
    """Mass properties of a cadquery/OCP solid in mm, as a ``Body`` in SI.

    ``fill`` scales a solid part to a printed one (see ``printed_fill``); the inertia is scaled with it.
    """
    gprop = require("OCP.GProp", "mass properties")
    brep = require("OCP.BRepGProp", "mass properties")
    props = gprop.GProp_GProps()
    brep.BRepGProp.VolumeProperties_s(getattr(shape, "wrapped", shape), props)
    vol_mm3 = props.Mass()
    if vol_mm3 <= 0:
        raise ValueError(f"{name or 'shape'} has no volume")
    c = props.CentreOfMass()
    m = props.MatrixOfInertia()  # about the centre of mass, for unit density, mm^5
    rho = density_g_cm3 * fill * 1e-6  # kg/mm^3
    inertia = tuple(tuple(m.Value(i, j) * rho * 1e-6 for j in (1, 2, 3)) for i in (1, 2, 3))  # kg m^2
    return Body(vol_mm3 * rho, (c.X() * 1e-3, c.Y() * 1e-3, c.Z() * 1e-3), inertia, name)


def printed_part_body(shape: Any, density_g_cm3: float, wall_mm: float = 1.6, infill: float = 0.15,
                      name: str = "") -> Tuple[Body, Dict[str, Any]]:
    """``Body`` for a printed part plus a report of how its mass was estimated."""
    vol = shape.Volume()
    area = shape.Area()
    fill = printed_fill(vol, area, wall_mm, infill)
    body = solid_mass_properties(shape, density_g_cm3, fill, name)
    return body, {"volume_cm3": round(vol / 1000, 3), "area_cm2": round(area / 100, 2), "wall_mm": wall_mm,
                  "infill": infill, "effective_fill": round(fill, 3), "mass_g": round(body.mass * 1000, 1),
                  "estimate": True}


# --------------------------------------------------------------------------- URDF

@dataclass
class Visual:
    mesh: str                      # path relative to the URDF file
    xyz: Vec = (0.0, 0.0, 0.0)
    rpy: Vec = (0.0, 0.0, 0.0)
    scale: float = 0.001           # meshes are written in mm
    rgba: Optional[Tuple[float, float, float, float]] = None
    material: str = ""


@dataclass
class Collision:
    """Primitive collision shape: ("box", (x, y, z)), ("cylinder", (radius, length)), ("sphere", (r,)), or
    ("mesh", path). Simple primitives keep the physics fast and stable."""

    kind: str
    size: Any
    xyz: Vec = (0.0, 0.0, 0.0)
    rpy: Vec = (0.0, 0.0, 0.0)


@dataclass
class Link:
    name: str
    body: Body = field(default_factory=lambda: Body(0.0))
    visuals: List[Visual] = field(default_factory=list)
    collisions: List[Collision] = field(default_factory=list)


@dataclass
class Joint:
    name: str
    type: str                     # revolute, continuous, prismatic, fixed
    parent: str
    child: str
    xyz: Vec = (0.0, 0.0, 0.0)
    rpy: Vec = (0.0, 0.0, 0.0)
    axis: Vec = (0.0, 0.0, 1.0)
    lower: Optional[float] = None
    upper: Optional[float] = None
    effort: Optional[float] = None    # N m (peak torque the actuator can give)
    velocity: Optional[float] = None  # rad/s
    damping: float = 0.0
    friction: float = 0.0
    armature: Optional[float] = None  # rotor inertia reflected through the gearbox, kg m^2 (written as a comment)


def write_urdf(path: Path, robot: str, links: Sequence[Link], joints: Sequence[Joint],
               comment: str = "") -> Path:
    """Write a URDF. Raises ``ValueError`` if the link/joint graph is not a tree."""
    problems = tree_problems([l.name for l in links], [(j.parent, j.child, j.name) for j in joints])
    if problems:
        raise ValueError("; ".join(problems))
    root = ET.Element("robot", name=robot)
    if comment:
        root.append(ET.Comment(f" {comment} "))
    colors = {}
    for l in links:
        for v in l.visuals:
            if v.rgba and v.material and v.material not in colors:
                colors[v.material] = v.rgba
    for name, rgba in colors.items():
        ET.SubElement(ET.SubElement(root, "material", name=name), "color", rgba=_fmt(rgba))
    for l in links:
        le = ET.SubElement(root, "link", name=l.name)
        if l.body.mass > 0:
            ine = ET.SubElement(le, "inertial")
            ET.SubElement(ine, "origin", xyz=_fmt(l.body.com), rpy="0 0 0")
            ET.SubElement(ine, "mass", value=f"{l.body.mass:.6g}")
            i = l.body.inertia
            ET.SubElement(ine, "inertia", ixx=f"{i[0][0]:.6g}", ixy=f"{i[0][1]:.6g}", ixz=f"{i[0][2]:.6g}",
                          iyy=f"{i[1][1]:.6g}", iyz=f"{i[1][2]:.6g}", izz=f"{i[2][2]:.6g}")
        for v in l.visuals:
            ve = ET.SubElement(le, "visual")
            ET.SubElement(ve, "origin", xyz=_fmt(v.xyz), rpy=_fmt(v.rpy))
            ET.SubElement(ET.SubElement(ve, "geometry"), "mesh", filename=v.mesh, scale=_fmt((v.scale,) * 3))
            if v.material:
                ET.SubElement(ve, "material", name=v.material)
        for c in l.collisions:
            ce = ET.SubElement(le, "collision")
            ET.SubElement(ce, "origin", xyz=_fmt(c.xyz), rpy=_fmt(c.rpy))
            g = ET.SubElement(ce, "geometry")
            if c.kind == "box":
                ET.SubElement(g, "box", size=_fmt(c.size))
            elif c.kind == "cylinder":
                ET.SubElement(g, "cylinder", radius=f"{c.size[0]:.6g}", length=f"{c.size[1]:.6g}")
            elif c.kind == "sphere":
                ET.SubElement(g, "sphere", radius=f"{c.size[0]:.6g}")
            elif c.kind == "mesh":
                ET.SubElement(g, "mesh", filename=str(c.size), scale="0.001 0.001 0.001")
            else:
                raise ValueError(f"unknown collision kind {c.kind!r} on {l.name}")
    for j in joints:
        je = ET.SubElement(root, "joint", name=j.name, type=j.type)
        if j.armature is not None:
            je.append(ET.Comment(f" armature_kg_m2={j.armature:.6g} "))
        ET.SubElement(je, "parent", link=j.parent)
        ET.SubElement(je, "child", link=j.child)
        ET.SubElement(je, "origin", xyz=_fmt(j.xyz), rpy=_fmt(j.rpy))
        if j.type != "fixed":
            ET.SubElement(je, "axis", xyz=_fmt(j.axis))
            lim = {}
            if j.type in ("revolute", "prismatic"):
                lim.update(lower=f"{j.lower:.6g}", upper=f"{j.upper:.6g}")
            if j.effort is not None:
                lim["effort"] = f"{j.effort:.6g}"
            if j.velocity is not None:
                lim["velocity"] = f"{j.velocity:.6g}"
            if lim:
                ET.SubElement(je, "limit", **lim)
            if j.damping or j.friction:
                ET.SubElement(je, "dynamics", damping=f"{j.damping:.6g}", friction=f"{j.friction:.6g}")
    ET.indent(root)
    path = Path(path)
    path.write_text('<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
    return path


def tree_problems(links: Sequence[str], edges: Sequence[Tuple[str, str, str]]) -> List[str]:
    """Problems that stop a link/joint graph being a tree: unknown links, two parents, loops, several roots."""
    names = set(links)
    out = []
    parent_of: Dict[str, str] = {}
    for p, c, j in edges:
        for n in (p, c):
            if n not in names:
                out.append(f"joint {j} names unknown link {n}")
        if c in parent_of:
            out.append(f"link {c} has two parents ({parent_of[c]}, {p}); URDF cannot hold a closed loop")
        parent_of[c] = p
    roots = [n for n in links if n not in parent_of]
    if len(roots) != 1:
        out.append(f"expected one root link, found {roots}")
    for n in links:
        seen, cur = set(), n
        while cur in parent_of:
            if cur in seen:
                out.append(f"loop through {n}")
                break
            seen.add(cur)
            cur = parent_of[cur]
    return out


def inertia_problems(mass: float, inertia: Mat, name: str = "", tol: float = 1e-9) -> List[str]:
    """Physical-validity problems with an inertia tensor (what a simulator rejects or misbehaves on)."""
    np = require("numpy", "inertia check")
    out = []
    if not mass > 0:
        out.append(f"{name}: mass {mass} is not positive")
    i = np.asarray(inertia, dtype=float)
    if not np.allclose(i, i.T, atol=tol):
        out.append(f"{name}: inertia is not symmetric")
    ev = np.linalg.eigvalsh((i + i.T) / 2)
    if ev.min() <= 0:
        out.append(f"{name}: inertia is not positive definite (principal moments {ev.round(9).tolist()})")
    a, b, c = sorted(ev)
    if a + b < c * (1 - 1e-6):
        out.append(f"{name}: principal moments break the triangle inequality ({a:.3g} + {b:.3g} < {c:.3g})")
    return out


def check_urdf(path: Path) -> Dict[str, Any]:
    """Load-free URDF check: tree structure, inertias, mesh files, joint limits. ``pass`` is a boolean."""
    path = Path(path)
    root = ET.parse(path).getroot()
    problems: List[str] = []
    links = [l.get("name") for l in root.findall("link")]
    edges = [(j.find("parent").get("link"), j.find("child").get("link"), j.get("name")) for j in root.findall("joint")]
    problems += tree_problems(links, edges)
    total = 0.0
    for l in root.findall("link"):
        n = l.get("name")
        ine = l.find("inertial")
        if ine is None:
            continue
        m = float(ine.find("mass").get("value"))
        total += m
        a = {k: float(v) for k, v in ine.find("inertia").attrib.items()}
        mat = ((a["ixx"], a["ixy"], a["ixz"]), (a["ixy"], a["iyy"], a["iyz"]), (a["ixz"], a["iyz"], a["izz"]))
        problems += inertia_problems(m, mat, n)
        for mesh in l.iter("mesh"):
            f = mesh.get("filename")
            if f and "://" not in f and not (path.parent / f).exists():
                problems.append(f"{n}: mesh {f} is missing")
    moving = 0
    for j in root.findall("joint"):
        t = j.get("type")
        if t == "fixed":
            continue
        moving += 1
        lim = j.find("limit")
        if t in ("revolute", "prismatic"):
            if lim is None or float(lim.get("lower")) >= float(lim.get("upper")):
                problems.append(f"joint {j.get('name')}: lower limit must be below upper")
        if lim is None or float(lim.get("effort", 0)) <= 0:
            problems.append(f"joint {j.get('name')}: no positive effort limit")
    return {"pass": not problems, "problems": problems, "links": len(links), "joints": len(edges),
            "moving_joints": moving, "total_mass_kg": round(total, 4), "physical_fit_verified": False}


# --------------------------------------------------------------------------- MJCF (MuJoCo)

@dataclass
class Motor:
    """A torque motor on a joint. ``effort`` (N m) becomes the control range; the controller applies the
    torque-speed limit itself, because MuJoCo motors have none."""

    joint: str
    effort: float
    name: str = ""


def write_mjcf(path: Path, robot: str, links: Sequence[Link], joints: Sequence[Joint], motors: Sequence[Motor] = (),
               floating: bool = True, floor: bool = True, timestep: float = 0.002, imu_link: Optional[str] = None,
               ground_friction: Tuple[float, float, float] = (1.0, 0.005, 0.0001), comment: str = "") -> Path:
    """Write a MuJoCo model of the same tree ``write_urdf`` writes, with motors, an IMU and an optional floor.

    Collision primitives become geoms; visual meshes become non-colliding geoms in group 1. Joint ``armature``,
    ``damping`` and ``friction`` (as frictionloss) carry over, which URDF cannot express.
    """
    problems = tree_problems([l.name for l in links], [(j.parent, j.child, j.name) for j in joints])
    if problems:
        raise ValueError("; ".join(problems))
    by_name = {l.name: l for l in links}
    children: Dict[str, List[Joint]] = {}
    for j in joints:
        children.setdefault(j.parent, []).append(j)
    root_name = next(l.name for l in links if all(j.child != l.name for j in joints))

    m = ET.Element("mujoco", model=robot)
    if comment:
        m.append(ET.Comment(f" {comment} "))
    ET.SubElement(m, "compiler", angle="radian", autolimits="true")
    ET.SubElement(m, "option", timestep=f"{timestep:g}", integrator="implicitfast")
    default = ET.SubElement(m, "default")
    ET.SubElement(ET.SubElement(default, "default", **{"class": "visual"}), "geom", contype="0", conaffinity="0",
                  group="1", density="0")
    asset = ET.SubElement(m, "asset")
    meshes: Dict[str, str] = {}
    world = ET.SubElement(m, "worldbody")
    if floor:
        ET.SubElement(asset, "texture", name="grid", type="2d", builtin="checker", rgb1=".82 .80 .76",
                      rgb2=".72 .70 .66", width="512", height="512")
        ET.SubElement(asset, "material", name="grid", texture="grid", texrepeat="8 8", reflectance="0.05")
        ET.SubElement(world, "light", pos="0 0 4", dir="0 0 -1", diffuse=".8 .8 .8")
        ET.SubElement(world, "geom", name="floor", type="plane", size="0 0 0.05", material="grid",
                      friction=_fmt(ground_friction))

    def add_body(parent_el, link: Link, joint: Optional[Joint]):
        attrs = {"name": link.name}
        if joint is not None:
            attrs["pos"] = _fmt(joint.xyz)
            attrs["quat"] = _fmt(rpy_to_quat(joint.rpy))
        el = ET.SubElement(parent_el, "body", **attrs)
        if joint is None and floating:
            ET.SubElement(el, "freejoint", name=f"{link.name}_free")
        elif joint is not None and joint.type != "fixed":
            ja = {"name": joint.name, "type": "slide" if joint.type == "prismatic" else "hinge", "axis": _fmt(joint.axis)}
            if joint.type in ("revolute", "prismatic"):
                ja["range"] = f"{joint.lower:.6g} {joint.upper:.6g}"
            if joint.damping:
                ja["damping"] = f"{joint.damping:.6g}"
            if joint.friction:
                ja["frictionloss"] = f"{joint.friction:.6g}"
            if joint.armature:
                ja["armature"] = f"{joint.armature:.6g}"
            ET.SubElement(el, "joint", **ja)
        b = link.body
        if b.mass > 0:
            i = b.inertia
            ET.SubElement(el, "inertial", pos=_fmt(b.com), mass=f"{b.mass:.6g}",
                          fullinertia=_fmt((i[0][0], i[1][1], i[2][2], i[0][1], i[0][2], i[1][2])))
        for k, c in enumerate(link.collisions):
            ga = {"name": f"{link.name}_col{k}", "pos": _fmt(c.xyz), "quat": _fmt(rpy_to_quat(c.rpy))}
            if c.kind == "box":
                ga.update(type="box", size=_fmt(v / 2 for v in c.size))
            elif c.kind == "cylinder":
                ga.update(type="cylinder", size=f"{c.size[0]:.6g} {c.size[1] / 2:.6g}")
            elif c.kind == "sphere":
                ga.update(type="sphere", size=f"{c.size[0]:.6g}")
            else:
                raise ValueError(f"MJCF export supports box, cylinder and sphere collisions, not {c.kind!r}")
            ga["rgba"] = "0.5 0.5 0.5 0"  # collision shapes are invisible; meshes show the part
            ET.SubElement(el, "geom", **ga)
        for k, v in enumerate(link.visuals):
            mesh_name = meshes.setdefault(v.mesh, f"mesh{len(meshes)}")
            if len(meshes) > len(asset.findall("mesh")):
                ET.SubElement(asset, "mesh", name=mesh_name, file=v.mesh, scale=_fmt((v.scale,) * 3))
            ga = {"class": "visual", "type": "mesh", "mesh": mesh_name, "pos": _fmt(v.xyz), "quat": _fmt(rpy_to_quat(v.rpy))}
            if v.rgba:
                ga["rgba"] = _fmt(v.rgba)
            ET.SubElement(el, "geom", **ga)
        if link.name == imu_link:
            ET.SubElement(el, "site", name="imu", pos=_fmt(b.com))
        for cj in children.get(link.name, []):
            add_body(el, by_name[cj.child], cj)

    add_body(world, by_name[root_name], None)
    if motors:
        act = ET.SubElement(m, "actuator")
        for mo in motors:
            ET.SubElement(act, "motor", name=mo.name or mo.joint, joint=mo.joint,
                          ctrlrange=f"{-mo.effort:.6g} {mo.effort:.6g}")
    if imu_link:
        sen = ET.SubElement(m, "sensor")
        ET.SubElement(sen, "framequat", name="imu_quat", objtype="site", objname="imu")
        ET.SubElement(sen, "gyro", name="imu_gyro", site="imu")
        ET.SubElement(sen, "accelerometer", name="imu_acc", site="imu")
    ET.indent(m)
    path = Path(path)
    path.write_text(ET.tostring(m, encoding="unicode") + "\n")
    return path


def rpy_to_quat(rpy: Vec) -> Tuple[float, float, float, float]:
    """URDF roll-pitch-yaw (fixed axes x, y, z) to a MuJoCo quaternion (w, x, y, z)."""
    r, p, y = (a / 2 for a in rpy)
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return (cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy)


# --------------------------------------------------------------------------- small linear algebra

def _fmt(v: Iterable[float]) -> str:
    return " ".join(f"{x:.6g}" for x in v)


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_m(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(a[i][j] + b[i][j] for j in range(3)) for i in range(3))


def _t(a: Mat) -> Mat:
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))


def _mm(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _mv(a: Mat, v: Vec) -> Vec:
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


def _point_inertia(m: float, d: Vec) -> Mat:
    x, y, z = d
    return ((m * (y * y + z * z), -m * x * y, -m * x * z),
            (-m * x * y, m * (x * x + z * z), -m * y * z),
            (-m * x * z, -m * y * z, m * (x * x + y * y)))


def rot_x(deg: float) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def rot_y(deg: float) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rot_z(deg: float) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))
