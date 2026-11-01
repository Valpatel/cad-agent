#!/usr/bin/env python3
"""Regenerate docs/img/cfd/fan-faces.webp and the two recorded runs it is drawn from (tests/fixtures/cfd_runs/
exhaust-under-opening and exhaust-ducted): where the air through an exhaust fan goes, and the heat it carries.

    PYTHONPATH=src python3 tools/cfd_fan_figure.py <work dir>          # runs both cases, records them, draws (~5 min)
    PYTHONPATH=src python3 tools/cfd_fan_figure.py <work dir> --draw   # redraws from the runs already in <work dir>

Running needs OpenFOAM v2512 or Docker (the opencfd/openfoam-default:2512 image), drawing needs PyVista, and both need
CadQuery. The case: a vented box (80 x 80 x 60 mm, 4 mm walls, a 50 x 8 mm vent low in two opposite sides) on a table
in still 25 °C room air, a 20 W evenly heated block inside, and an exhaust fan (50 mm, 20 mm hub, straight-line curve,
20 Pa / 30 m3/h) blowing up through the opening in its top. Twice: the fan 3 mm under a 52 mm opening, and the fan in
a short duct that is the box's only way out, with its hub a solid plug. 1500 iterations each on 6 processes.

The recorded runs keep every function object's output but the residuals (500 KB a run) and the wall heat flux, and
their solver logs are cut to the last 40 lines (read_results reads only the end), so tests read them without OpenFOAM.
"""
from __future__ import annotations

import json
import shutil
import io
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "img" / "cfd" / "fan-faces.webp"
FIXTURES = ROOT / "tests" / "fixtures" / "cfd_runs"
CASES = {"exhaust-under-opening": False, "exhaust-ducted": True}      # name: ducted
ITERATIONS, NP = 1500, 6
KEEP = ("T_inlet_fan", "T_outlet_fan", "mass_inlet_fan", "mass_outlet_fan", "massGross_inlet_fan", "massGross_outlet_fan",
        "zone_fan", "zone_heater", "flux_T", "flux_mass", "T_max_domain0")
LOG_TAIL = 40
FACES = "#2a78d6"                                    # simviz's first series colour: the measuring faces
WALL = "#c9d1c6"


def make(ducted: bool, iterations: int = ITERATIONS):
    """The vented box with an exhaust fan (see the module docstring), as a ThermalCase."""
    import cadquery as cq

    from cadagent.simulation.cfd import Fan, ThermalCase
    box = cq.Workplane().box(80, 80, 60, centered=False).translate((0, 0, 10))
    box = box.cut(cq.Workplane().box(72, 72, 52, centered=False).translate((4, 4, 14)))
    if ducted:                        # a tube from the top down to z 52 round the fan: its annulus is the only way out
        box = box.union(cq.Workplane().circle(29).circle(25).extrude(16).translate((40, 40, 52)))
    box = box.cut(cq.Workplane().circle(25 if ducted else 26).extrude(10).translate((40, 40, 64)))
    for x in (-3, 73):
        box = box.cut(cq.Workplane().box(10, 50, 8, centered=False).translate((x, 15, 18)))
    c = ThermalCase("exhaust-ducted" if ducted else "exhaust-under-opening", domain=((-50, -50, 0), (130, 130, 170)),
                    cell_mm=8, ambient_c=25, iterations=iterations)
    c.wall("box", box, level=(2, 2))
    if ducted:                        # the fan's hub as a solid plug through the duct: no air comes back through it
        c.wall("hub", cq.Workplane().circle(10).extrude(20).translate((40, 40, 51)), level=(2, 2))
    c.porous_box("heater", (20, 20, 24), (60, 60, 44), d=(2e5, 2e5, 2e5), f=(0, 0, 0), heat_w=20.0)
    c.fan(Fan("fan", centre=(40, 40, 60), axis=(0, 0, 1), d_outer=50, d_hub=20, thickness=6, dp0_pa=20, q_free_m3h=30))
    c.refine((8, 8, 48), (72, 72, 76), 2)
    return c


def record(case: Path, dest: Path):
    """Copy what read_results needs from a finished case into a fixture folder (see the module docstring)."""
    shutil.rmtree(dest, ignore_errors=True)
    for name in KEEP:
        shutil.copytree(case / "postProcessing" / "domain0" / name, dest / "postProcessing" / "domain0" / name)
    shutil.copy(case / "cadagent-case.json", dest / "cadagent-case.json")
    sizes = [l.strip() for l in (case / "log.topoSet").read_text().splitlines() if " now size " in l]
    (dest / "log.topoSet").write_text("\n".join(sizes) + "\n")
    tail = (case / "log.solve").read_text(errors="replace").splitlines()[-LOG_TAIL:]
    (dest / "log.solve").write_text("\n".join(tail) + "\n")


def section(case: Path, y=0.04, x=(-0.01, 0.09), z=(0.005, 0.11), n=(201, 211)):
    """Temperature (°C) and the in-plane velocity on the vertical plane through the fan's axis, NaN in the walls."""
    import numpy as np
    import pyvista as pv
    grid = pv.read(sorted((case / "VTK" / "domain0").glob("case_*/internal.vtu"))[-1])
    X, Z = np.meshgrid(np.linspace(*x, n[0]), np.linspace(*z, n[1]))
    s = pv.PolyData(np.c_[X.ravel(), np.full(X.size, y), Z.ravel()]).sample(grid)
    ok = np.asarray(s.point_data["vtkValidPointMask"]).astype(bool).reshape(X.shape)
    U = np.asarray(s.point_data["U"])
    t, ux, uz = (np.where(ok, a.reshape(X.shape), np.nan) for a in (np.asarray(s.point_data["T"]) - 273.15, U[:, 0], U[:, 2]))
    return X * 1000, Z * 1000, t, ux, uz


def facts(case: Path) -> dict:
    from cadagent.simulation.cfd import read_results
    r = read_results(case)
    f = r["fans"]["fan"]
    heat = [p[1] for p in r["monitors"]["heat_out_w"]["points"] if p[0] >= r["convergence_window"][0]]
    return {"mass_flow_g_s": round(f["outlet_kg_s"] * 1000, 2), "inlet_c": f["inlet_c"], "outlet_c": f["outlet_c"],
            "zone_by_volume_c": f["air_through_fan_c"], "heat_carried_w": f["heat_carried_w"], "heat_input_w": r["heat_input_w"],
            "heat_out_w": r["heat_out_w"], "energy_balance_pct": r["energy_balance_pct"], "heat_out_window_w": [round(min(heat), 1), round(max(heat), 1)],
            "window": r["convergence_window"], "energy_conserved": r["energy_conserved"], "steady": r["steady"]}


def draw(work: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    from cadagent.simulation.simviz import INK, MUTED, PAPER, TEMP_RAMP, cmap
    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    got = {name: (section(work / name), facts(work / name)) for name in CASES}
    top = max(float(np.nanpercentile(s[2], 99.5)) for s, _ in got.values())
    vmax = float(np.ceil(top))
    ramp = cmap(TEMP_RAMP)
    ramp.set_bad(WALL)
    fig = plt.figure(figsize=(10.2, 7.3), facecolor=PAPER)
    axs = [fig.add_axes((0.065, 0.27, 0.39, 0.62)), fig.add_axes((0.535, 0.27, 0.39, 0.62))]
    titles = {"exhaust-under-opening": "The fan 3 mm under the opening",
              "exhaust-ducted": "The fan in a duct, its hub plugged"}
    for ax, (name, ((X, Z, t, ux, uz), f)) in zip(axs, got.items()):
        ax.set_facecolor(PAPER)
        im = ax.imshow(t, origin="lower", extent=(X[0, 0], X[0, -1], Z[0, 0], Z[-1, 0]), cmap=ramp, vmin=25, vmax=vmax,
                       interpolation="bilinear", rasterized=True)
        ax.streamplot(X, Z, np.nan_to_num(ux), np.nan_to_num(uz), color=INK, density=1.2, linewidth=0.55, arrowsize=0.6,
                      broken_streamlines=True)
        for x0 in (15, 55):                       # the fan zone either side of its hub, and its two measuring faces
            ax.add_patch(plt.Rectangle((x0, 57), 10, 6, fill=False, ec=INK, lw=0.9, ls=(0, (2, 1.5)), zorder=3))
            for zf in (57, 63):
                ax.plot([x0, x0 + 10], [zf, zf], color=FACES, lw=2.4, solid_capstyle="butt", zorder=4)
        for words, to, at in (("outlet", (64, 63.6), (69, 77)), ("inlet", (64, 56.4), (69, 46))):
            ax.annotate(words, to, at, color=INK, fontsize=8.5, zorder=5, va="center",
                        bbox=dict(boxstyle="round,pad=0.2", fc=PAPER, ec="none", alpha=0.9),
                        arrowprops=dict(arrowstyle="-", color=INK, lw=0.8, shrinkA=0, shrinkB=0))
        ax.set_xlim(X[0, 0], X[0, -1])
        ax.set_ylim(Z[0, 0], Z[-1, 0])
        ax.set_aspect("equal")
        ax.set_title(titles[name], loc="left", color=INK, fontsize=11)
        ax.set_xlabel("across the box through the fan's axis (mm)", color=MUTED)
        ax.set_ylabel("height above the table (mm)", color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(MUTED)
        u = "\u00a0"                              # a number and its unit never part at a line end
        pct = f"{f['energy_balance_pct']:+.1f}".replace("-", "−")
        note = (f"The fan moves {f['mass_flow_g_s']:.2f}{u}g/s. Its air is {f['inlet_c']:.2f}{u}°C in and "
                f"{f['outlet_c']:.2f}{u}°C out, mass-flow-weighted, and {f['zone_by_volume_c']:.2f}{u}°C by volume over "
                f"its zone. It carries {f['heat_carried_w']:.2f}{u}W above the room, for {f['heat_input_w']:g}{u}W put in. "
                f"{f['heat_out_w']:.2f}{u}W leave the room ({pct}{u}%"
                + ("): energy conserved." if f["energy_conserved"] else f", past 5{u}%): flagged, energy not conserved."))
        box = ax.get_position()
        fig.text(box.x0, 0.175, textwrap.fill(note, 72, break_on_hyphens=False), va="top", ha="left", color=INK, fontsize=8.6, linespacing=1.4)
    bar = fig.colorbar(im, cax=fig.add_axes((0.94, 0.33, 0.012, 0.48)))
    bar.set_label("air temperature (°C)", color=MUTED)
    bar.ax.tick_params(colors=MUTED, labelsize=8)
    bar.outline.set_edgecolor(MUTED)
    fig.text(0.015, 0.965, "A 20 W box with an exhaust fan: where the air through the fan goes", ha="left", va="top",
             color=INK, fontsize=13)
    lo = min(f["heat_out_window_w"][0] for _, f in got.values())
    hi = max(f["heat_out_window_w"][1] for _, f in got.values())
    foot = (f"Recorded runs of cadagent.simulation.cfd (OpenFOAM v2512, steady RANS, {ITERATIONS} iterations), a section "
            "through the fan's axis. Blue: the fan's inlet and outlet faces; dashed: its zone, either side of the hub. "
            f"Neither run is steady: over the last fifth of the run the plume above the box swings the heat leaving it "
            f"between {lo:g} and {hi:g} W.")
    fig.text(0.015, 0.06, textwrap.fill(foot, 160), ha="left", va="top", color=MUTED, fontsize=7.8, linespacing=1.35)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    png = io.BytesIO()                            # a field section is a picture: WebP, a tenth of the size of an SVG
    fig.savefig(png, format="png", facecolor=PAPER, dpi=140)
    plt.close(fig)
    from PIL import Image
    Image.open(png).convert("RGB").save(OUT, "WEBP", quality=88, method=6)
    rev = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = json.loads((work / "exhaust-ducted" / "cadagent-case.json").read_text())
    (OUT.parent / "SOURCE.json").write_text(json.dumps({
        "figure": "fan-faces.webp", "regenerate": "PYTHONPATH=src python3 tools/cfd_fan_figure.py <work dir>",
        "cad_agent_revision": rev, "solver": meta["solver"], "image": "opencfd/openfoam-default:2512",
        "iterations": ITERATIONS, "processes": NP, "recorded_runs": [f"tests/fixtures/cfd_runs/{n}" for n in CASES],
        "facts": {n: f for n, (_, f) in got.items()}}, indent=1) + "\n")
    print("wrote", OUT)


def main(argv):
    work = Path(argv[0]).resolve()
    if "--draw" not in argv:
        work.mkdir(parents=True, exist_ok=True)
        for name, ducted in CASES.items():
            c = make(ducted)
            c.write(work / name, np_procs=NP)
            if c.run(work / name) != 0:
                raise SystemExit(f"{name}: the run failed; see {work / name}")
            record(work / name, FIXTURES / name)
    draw(work)


if __name__ == "__main__":
    main(sys.argv[1:])
