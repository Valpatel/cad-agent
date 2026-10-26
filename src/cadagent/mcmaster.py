"""McMaster-Carr parts: the manufacturer's CAD (STEP) and the product data for one part number, in a frame a CAD
build can place.

Bought hardware in a design (bearings, screws, nuts, washers, inserts, pins, standoffs, rod ends, grommets) should be a
real part with a part number, not an envelope. McMaster-Carr publishes a STEP model and a full specification table for
almost every part it sells. This module gets both, the way an engineer does while working:

* one product page at a time, in a real browser (Playwright driving the system Chrome, ``channel="chrome"``);
* a pause between pages (``delay_s``, 3 s by default) and only the pages for the parts being chosen;
* no crawling, no scraping of search or category pages, no parallel requests.

The files stay local. McMaster-Carr CAD is provided for design use; it is not ours to redistribute, so keep the
download folder out of version control (track only ``SOURCE.txt``, which ``write_source`` writes).

What it gives you
-----------------
``fetch(pn, out_dir)``
    Opens ``https://www.mcmaster.com/<PN>/``, reads the page (title, price and pack quantity, every row of the
    specification table, the option choices the page offers) into ``<PN>.page.json``, then picks "3-D STEP" in the
    CAD menu and saves the download as ``<PN>.step``. Returns the STEP path. ``Session`` does the same for several
    part numbers with one browser.
``normalise(step_path, kind)``
    Finds the part's axis from its cylindrical faces and moves it into the frame for its kind (``FRAMES``), writes
    ``<PN>.norm.step`` and returns ``(path, info)`` with the axis found, the bounding box, the volume and a mass.
``catalog_entry(page, info, ...)``
    The catalogue record: part number, description, URL, price, pack quantity, key dimensions, material, mass
    (McMaster's listed weight when the page gives one, else volume x density, and which), the normalised CAD path, the
    frame, and the whole specification table (``specs.raw`` label -> value strings, ``specs.parsed`` numbers in mm, g,
    N, MPa or deg C where the unit is unambiguous).

Install: ``pip install playwright`` into the environment that runs this. With Google Chrome installed nothing else is
needed (no ``playwright install``); the CAD steps need CadQuery (the ``cad`` extra).
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import MissingDependency, require

BASE_URL = "https://www.mcmaster.com"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")
PLAYWRIGHT_HINT = ("McMaster downloads need Playwright: pip install playwright (into the environment that runs "
                   "cad-agent). With Google Chrome installed, `playwright install` is not needed.")
SOURCE_NOTE = "McMaster-Carr CAD, for design use; not redistributed."

# Frame conventions, one per kind of part. The axis is always +Z.
FRAMES = {
    "bearing": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "washer": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "nut": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "insert": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "standoff": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "spacer": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "pin": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "grommet": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "rod": "axis +Z, centred on the axis, bottom face at z = 0, part on +z",
    "screw": "axis +Z, underside of the head at z = 0, head on +z, shank towards -z",
    "shoulder_screw": "axis +Z, underside of the head at z = 0, head on +z, shoulder and thread towards -z",
    "rod_end": "ball centre at the origin, ball bore along +Y, threaded shank along -Z",
}
KINDS = tuple(FRAMES)
HEADED = ("screw", "shoulder_screw")

# g/cm3, matched against the page's Material row (first match wins)
DENSITY = [
    ("stainless", 8.0), ("brass", 8.5), ("bronze", 8.8), ("aluminum", 2.7), ("aluminium", 2.7), ("titanium", 4.5),
    ("nylon", 1.15), ("acetal", 1.41), ("ptfe", 2.2), ("silicone", 1.2), ("neoprene", 1.3), ("buna", 1.3),
    ("epdm", 1.3), ("rubber", 1.3), ("zinc", 7.1), ("steel", 7.85), ("iron", 7.2),
]


# ----------------------------------------------------------------------------------- the product page

def product_url(pn: str) -> str:
    return f"{BASE_URL}/{pn.strip().upper()}/"


def parse_price(text: str) -> Tuple[Optional[float], Optional[int]]:
    """'$10.91 each' -> (10.91, 1); '$13.96 per pack of 100' -> (13.96, 100). Unknown -> (None, None)."""
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text or "")
    if not m:
        return None, None
    price = float(m.group(1).replace(",", ""))
    pack = re.search(r"pack(?:age)? of\s*([\d,]+)", text, re.I)
    if pack:
        return price, int(pack.group(1).replace(",", ""))
    if re.search(r"\beach\b", text, re.I):
        return price, 1
    return price, None


_FRACTION = re.compile(r"^(?:(\d+)\s+)?(\d+)/(\d+)$")


def _num(s: str) -> Optional[float]:
    s = s.strip().replace(",", "").replace("−", "-")
    m = _FRACTION.match(s.lstrip("-"))
    if m:
        v = (int(m.group(1) or 0) + int(m.group(2)) / int(m.group(3)))
        return -v if s.startswith("-") else v
    try:
        return float(s)
    except ValueError:
        return None


_QTY = r"(-?(?:\d+\s+)?\d[\d,]*(?:\.\d+)?(?:/\d+)?|-?\.\d+)"
_UNIT = r"(mm|cm|m|in\.?|\"|ft\.?|lb\.?|lbs\.?|lbf|oz\.?|g|kg|psi|ksi|°\s*F|°\s*C|N|kN|rpm)"
_VALUE = re.compile(rf"^{_QTY}\s*{_UNIT}$")


def _convert(x: float, unit: str, label: str) -> Optional[Tuple[float, str]]:
    u = unit.replace(" ", "").rstrip(".").lower()
    lab = label.lower()
    if u == "mm":
        return x, "mm"
    if u == "cm":
        return x * 10, "mm"
    if u == "m":
        return x * 1000, "mm"
    if u in ("in", '"'):
        return x * 25.4, "mm"
    if u == "ft":
        return x * 304.8, "mm"
    if u in ("lb", "lbs", "lbf"):
        if "weight" in lab or "mass" in lab:
            return x * 453.59237, "g"
        if any(k in lab for k in ("load", "capacity", "force", "strength", "pull", "thrust")):
            return x * 4.4482216, "N"
        return None                                     # lb of what: not unambiguous
    if u == "oz":
        return (x * 28.349523, "g") if ("weight" in lab or "mass" in lab) else None
    if u == "g":
        return x, "g"
    if u == "kg":
        return x * 1000, "g"
    if u == "psi":
        return x * 0.00689476, "MPa"
    if u == "ksi":
        return x * 6.89476, "MPa"
    if u == "°f":
        return (x - 32) * 5 / 9, "degC"
    if u == "°c":
        return x, "degC"
    if u == "n":
        return x, "N"
    if u == "kn":
        return x * 1000, "N"
    if u == "rpm":
        return x, "rpm"
    return None


def parse_value(label: str, value: str) -> Optional[Dict[str, Any]]:
    """A spec value as a number in mm, g, N, MPa, deg C or rpm when its unit is unambiguous, else None.
    Ranges ('-0.12 mm to 0 mm', '0.002 to 0.008 mm') give {'min', 'max', 'unit'}."""
    v = (value or "").strip()
    if not v:
        return None
    rng = re.match(rf"^{_QTY}\s*{_UNIT}?\s+to\s+{_QTY}\s*{_UNIT}$", v)
    if rng:
        a, ua, b, ub = rng.groups()
        ca, cb = _convert(_num(a) or 0.0, ua or ub, label), _convert(_num(b) or 0.0, ub, label)
        if ca and cb and _num(a) is not None and _num(b) is not None:
            return {"min": round(ca[0], 6), "max": round(cb[0], 6), "unit": cb[1]}
        return None
    m = _VALUE.match(v)
    if m:
        x = _num(m.group(1))
        c = _convert(x, m.group(2), label) if x is not None else None
        if c:
            return {"value": round(c[0], 6), "unit": c[1]}
    thread = re.match(r"^M(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm$", v)
    if thread:
        return {"thread": f"M{thread.group(1)}x{thread.group(2)}", "d": float(thread.group(1)), "pitch": float(thread.group(2)), "unit": "mm"}
    return None


def parse_specs(rows: Sequence[Sequence[str]]) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    """Rows of (label, value, indented) from the specification table -> (raw, parsed). An indented row belongs to the
    group row above it, so 'Temperature Range' + 'Minimum' becomes 'Temperature Range Minimum'."""
    raw: Dict[str, str] = {}
    group = ""
    for row in rows:
        label, value = (row[0] or "").strip(), (row[1] or "").strip()
        indented = bool(row[2]) if len(row) > 2 else False
        if not label:
            continue
        if not indented:
            group = label if not value else ""
            if not value:
                continue
            key = label
        else:
            key = f"{group} {label}".strip()
        n, k = 2, key
        while k in raw:
            k = f"{key} ({n})"
            n += 1
        raw[k] = value
    parsed = {k: p for k, v in raw.items() if (p := parse_value(k, v))}
    return raw, parsed


_PAGE_JS = r"""
() => {
  const txt = e => (e ? e.innerText.replace(/\s+/g, ' ').trim() : '');
  const q = s => document.querySelector(s);
  const rows = [];
  for (const tr of document.querySelectorAll('tr[class*="product-detail-spec-table-row"]')) {
    const lab = tr.querySelector('[class*="spec-row-label"]');
    const val = tr.querySelector('[class*="spec-row-value"]');
    if (!lab) continue;
    const vals = val ? Array.from(val.querySelectorAll('p')).map(txt).filter(Boolean) : [];
    rows.push([txt(lab.querySelector('span') || lab), vals.join('; '), /indented/.test(tr.className)]);
  }
  const price = q('[class*="_price_"]');
  const options = [];
  for (const g of document.querySelectorAll('[role="radiogroup"], [class*="ChoiceGroup"], [class*="choiceGroup"], [class*="SpecChoice"], [class*="specChoice"]')) {
    const t = txt(g);
    if (t && t.length < 400 && !options.includes(t)) options.push(t);
  }
  const crumbs = Array.from(document.querySelectorAll('nav ol li')).map(txt).filter(Boolean);
  return {title: txt(q('h1[class*="productDetailHeaderPrimary"]') || q('h1')),
          subtitle: txt(q('h3[class*="productDetailHeaderSecondary"]')),
          price_text: txt(price), rows, options, breadcrumbs: crumbs};
}
"""


def _playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise MissingDependency(f"{PLAYWRIGHT_HINT} ({exc})") from exc
    return sync_playwright


class Session:
    """One browser for a few part numbers, one page at a time with a pause between pages.

        with Session() as s:
            step = s.fetch("5972K82", "vendor/mcmaster/5972K82")
    """

    def __init__(self, delay_s: float = 3.0, headless: bool = True, timeout_s: float = 60.0):
        self.delay_s, self.headless, self.timeout_ms = delay_s, headless, int(timeout_s * 1000)
        self._pw = self._browser = self._ctx = self.page = None
        self._last = 0.0

    def __enter__(self) -> "Session":
        self._pw = _playwright()().start()
        self._browser = self._pw.chromium.launch(channel="chrome", headless=self.headless,
                                                 args=["--disable-blink-features=AutomationControlled"])
        self._ctx = self._browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 1000},
                                              user_agent=USER_AGENT)
        self.page = self._ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._browser, self._pw):
            try:
                if closer is self._pw:
                    closer.stop()
                elif closer is not None:
                    closer.close()
            except Exception:
                pass

    def _open(self, pn: str) -> None:
        wait = self.delay_s - (time.monotonic() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)                              # the pause between pages
        self.page.goto(product_url(pn), wait_until="domcontentloaded", timeout=self.timeout_ms)
        self._last = time.monotonic()
        try:
            self.page.wait_for_selector('tr[class*="product-detail-spec-table-row"]', timeout=self.timeout_ms)
        except Exception:
            self.page.wait_for_timeout(5000)
        self.page.wait_for_timeout(1500)

    def read(self, pn: str, reload: bool = True) -> Dict[str, Any]:
        """The product page's data (title, price, pack, every spec row, the option choices)."""
        if reload:
            self._open(pn)
        d = self.page.evaluate(_PAGE_JS)
        raw, parsed = parse_specs(d["rows"])
        price, pack = parse_price(d["price_text"])
        weight = next((parsed[k] for k in parsed if "weight" in k.lower() and parsed[k].get("unit") == "g"), None)
        return {"pn": pn.upper(), "url": product_url(pn), "final_url": self.page.url, "title": d["title"],
                "subtitle": d["subtitle"], "description": ", ".join(t for t in (d["title"], d["subtitle"]) if t),
                "price_text": d["price_text"], "price_usd": price, "pack_qty": pack,
                "listed_weight_g": weight["value"] if weight and "value" in weight else None,
                "options": d["options"], "breadcrumbs": d["breadcrumbs"], "specs": {"raw": raw, "parsed": parsed},
                "read": _dt.date.today().isoformat()}

    def choose(self, options: Sequence[str]) -> List[str]:
        """Click option choices on the open product page (e.g. "Right Hand" for a rod end's thread direction), in
        order. Some parts offer their CAD only after every choice is made."""
        done = []
        for text in options or ():
            loc = self.page.get_by_text(text, exact=True)
            if not loc.count():
                raise RuntimeError(f"no option {text!r} on {self.page.url}")
            loc.first.click()
            self.page.wait_for_timeout(2500)
            done.append(text)
        return done

    def download_step(self, pn: str, out: Path) -> Path:
        """Pick '3-D STEP' in the CAD menu of the open product page and save the download as ``out``."""
        pg = self.page
        menu = pg.locator('[aria-label="Select CAD file type"]')
        if not menu.count():
            menu = pg.get_by_text("3-D Solidworks", exact=False)
        if not menu.count():
            raise RuntimeError(f"{pn}: no CAD menu on the product page")
        if menu.first.get_attribute("aria-disabled") == "true":
            raise RuntimeError(f"{pn}: the CAD menu is disabled until an option is chosen; pass the option text "
                               f"(choose=[...], --choose), e.g. one of the page's choices: "
                               f"{'; '.join(self.page.evaluate(_PAGE_JS)['options']) or 'see the page'}")
        menu.first.click()
        pg.wait_for_timeout(800)
        pg.get_by_text("3-D STEP", exact=True).first.click()
        pg.wait_for_timeout(800)
        with pg.expect_download(timeout=self.timeout_ms) as dl:
            pg.locator('button:has-text("Download"), a:has-text("Download")').first.click()
        out.parent.mkdir(parents=True, exist_ok=True)
        dl.value.save_as(str(out))
        return out

    def fetch(self, pn: str, out_dir, choose: Optional[Sequence[str]] = None, write_page: bool = True) -> Path:
        """Read the product page and download its STEP: ``<out_dir>/<PN>.step`` and ``<PN>.page.json``, plus
        ``SOURCE.txt``. ``choose`` lists option texts to click first (a part with variants). Returns the STEP path."""
        pn = pn.strip().upper()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        page = self.read(pn)
        if choose:
            options = page["options"]
            self.choose(choose)
            page = self.read(pn, reload=False)                # price and specs of the chosen variant
            page["options_offered"], page["chosen"] = options, list(choose)
        if write_page:
            (out_dir / f"{pn}.page.json").write_text(json.dumps(page, indent=1, ensure_ascii=False) + "\n")
        write_source(out_dir, pn, page.get("description", ""))
        step = self.download_step(pn, out_dir / f"{pn}.step")
        page["step"] = step.name
        if write_page:
            (out_dir / f"{pn}.page.json").write_text(json.dumps(page, indent=1, ensure_ascii=False) + "\n")
        return step


def fetch(pn: str, out_dir, delay_s: float = 3.0, choose: Optional[Sequence[str]] = None) -> Path:
    """One part: read its product page into ``<PN>.page.json`` and download its STEP into ``out_dir``. Returns the
    STEP path. For several parts use one ``Session`` (one browser, a pause between pages)."""
    with Session(delay_s=delay_s) as s:
        return s.fetch(pn, out_dir, choose=choose)


def write_source(folder, pn: str, description: str = "", when: Optional[str] = None) -> Path:
    """SOURCE.txt: where the files in this folder came from and the terms they are used under."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "SOURCE.txt"
    p.write_text(f"{pn} {description}".rstrip() + "\n"
                 f"URL: {product_url(pn)}\n"
                 f"Downloaded: {when or _dt.date.today().isoformat()}\n"
                 f"{SOURCE_NOTE}\n"
                 "Files: <PN>.step (as downloaded), <PN>.norm.step (moved into the frame for its kind), "
                 "<PN>.page.json (the product page's data).\n")
    return p


# ----------------------------------------------------------------------------------- normalising the frame

def _vec(v) -> Tuple[float, float, float]:
    return (v.x, v.y, v.z) if hasattr(v, "x") else tuple(float(c) for c in v)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cylinders(shape) -> List[Dict[str, Any]]:
    """Every cylindrical face: axis direction, a point on the axis, radius, area, and its extent along its axis."""
    out = []
    for f in shape.Faces():
        if f.geomType() != "CYLINDER":
            continue
        try:
            cyl = f._geomAdaptor().Cylinder()
        except Exception:
            continue
        ax = cyl.Axis()
        d = _unit((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()))
        p = (ax.Location().X(), ax.Location().Y(), ax.Location().Z())
        ts = [_dot(_vec(v.toTuple()), d) for v in f.Vertices()] or [0.0]
        out.append({"dir": d, "loc": p, "r": cyl.Radius(), "area": f.Area(), "t": (min(ts), max(ts)), "face": f})
    return out


def _spheres(shape) -> List[Dict[str, Any]]:
    out = []
    for f in shape.Faces():
        if f.geomType() != "SPHERE":
            continue
        try:
            s = f._geomAdaptor().Sphere()
        except Exception:
            continue
        c = s.Location()
        out.append({"centre": (c.X(), c.Y(), c.Z()), "r": s.Radius(), "area": f.Area()})
    return out


def _group_dirs(cyls) -> List[Tuple[Tuple[float, float, float], float]]:
    """Cylinder axis directions grouped up to sign, with the summed area of each group, largest first."""
    groups: List[List[Any]] = []
    for c in cyls:
        for g in groups:
            if abs(_dot(g[0], c["dir"])) > 0.999:
                g[1] += c["area"]
                break
        else:
            groups.append([c["dir"], c["area"]])
    return sorted(((tuple(g[0]), g[1]) for g in groups), key=lambda g: -g[1])


def _principal_axis(shape) -> Tuple[float, float, float]:
    """Fallback for parts with no cylinders: the principal axis of inertia whose moment differs most from the others
    (the symmetry axis of a body of revolution)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    pp = props.PrincipalProperties()
    moments = pp.Moments()
    axes = [pp.FirstAxisOfInertia(), pp.SecondAxisOfInertia(), pp.ThirdAxisOfInertia()]
    m = list(moments)
    odd = max(range(3), key=lambda i: min(abs(m[i] - m[j]) for j in range(3) if j != i))
    a = axes[odd]
    return _unit((a.X(), a.Y(), a.Z()))


def _basis_from_z(z):
    """Any right-handed (x, y, z) basis with the given z."""
    ref = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
    x = _unit(_cross(ref, z))
    y = _cross(z, x)
    return x, y, z


def _transform(shape, ex, ey, ez, origin):
    """Move a shape so the source frame (ex, ey, ez at origin) becomes the world frame."""
    import cadquery as cq
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf
    del ey                                               # gp_Ax3 completes the right-handed frame from z and x
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Pnt(*origin), gp_Dir(*ez), gp_Dir(*ex)))
    return cq.Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, t, True).Shape())


def _bbox(shape) -> Dict[str, Any]:
    b = shape.BoundingBox()
    r = lambda v: round(v, 4)
    return {"min": [r(b.xmin), r(b.ymin), r(b.zmin)], "max": [r(b.xmax), r(b.ymax), r(b.zmax)],
            "size": [r(b.xlen), r(b.ylen), r(b.zlen)]}


def material_of(raw: Mapping[str, str]) -> str:
    """The part's material from its spec rows ('Material', else 'Finished Material', 'Body Material'...)."""
    if raw.get("Material"):
        return raw["Material"]
    for k, v in raw.items():
        kl = k.lower()
        if kl.endswith("material") and not any(w in kl for w in ("ball", "cage", "seal", "insert", "shield", "lubric")):
            return v
    return ""


def density_for(material: str) -> Optional[float]:
    m = (material or "").lower()
    return next((d for k, d in DENSITY if k in m), None)


def _head_underside_z(shape) -> float:
    """For a headed part already on +Z with its head up: z of the underside of the head. That is the lowest circular
    edge perpendicular to the axis whose radius is at least 0.8 x the head's (the largest cylinder's) radius: below
    the head there is only the shank (well under 0.8), and it skips the bearing-face steps and fillets some models
    put under the head."""
    cyls = [c for c in _cylinders(shape) if abs(c["dir"][2]) > 0.999]
    if not cyls:
        raise ValueError("no cylinders along the axis: cannot find the head")
    rmax = max(c["r"] for c in cyls)
    zs = []
    for e in shape.Edges():
        if e.geomType() != "CIRCLE":
            continue
        bb = e.BoundingBox()
        if bb.zlen > 1e-4:
            continue
        try:
            r = e.radius()
        except Exception:
            continue
        if r >= 0.8 * rmax:
            zs.append(bb.zmin)
    if zs:
        return min(zs)
    return min(c["face"].BoundingBox().zmin for c in cyls if c["r"] > rmax - 0.05)


def normalise(step_path, kind: str, density: Optional[float] = None, out_path=None,
              material: str = "") -> Tuple[Path, Dict[str, Any]]:
    """Move a part into the frame for its kind (``FRAMES``) and write ``<name>.norm.step`` next to it.

    The axis comes from the cylindrical faces (the direction carrying the most cylinder area), or from the principal
    axes of inertia when there are none. Returns (path, info): the axis found in the original file, the origin used,
    the bounding box after the move, the volume (mm3) and the mass (g) for ``density`` (g/cm3; from ``material`` when
    not given)."""
    if kind not in FRAMES:
        raise ValueError(f"unknown kind {kind!r}; kinds: {', '.join(KINDS)}")
    cq = require("cadquery", "normalising a McMaster STEP")
    step_path = Path(step_path)
    objs = cq.importers.importStep(str(step_path)).vals()
    shape = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)
    cyls = _cylinders(shape)
    groups = _group_dirs(cyls)
    centre = _vec(cq.Shape.centerOfMass(shape))
    info: Dict[str, Any] = {"kind": kind, "frame": FRAMES[kind], "source": step_path.name}

    if kind == "rod_end":
        spheres = sorted(_spheres(shape), key=lambda s: -s["area"])
        if spheres:
            ball = spheres[0]["centre"]
            info["ball_d"] = round(2 * spheres[0]["r"], 3)
        else:                                           # no sphere: the bore's centre
            big = max(cyls, key=lambda c: c["area"])
            ball = big["loc"]
        # candidate axes through the ball centre; the shank is the one the part reaches far along on one side only
        verts = [_vec(v.toTuple()) for v in shape.Vertices()]
        best = None
        for d, _area in groups:
            proj = [_dot(_sub(p, ball), d) for p in verts] or [0.0]
            lo, hi = min(proj), max(proj)
            asym = abs(hi + lo)
            if best is None or asym > best[0]:
                best = (asym, d, lo, hi)
        if best is None:
            raise ValueError(f"{step_path.name}: no cylindrical faces, cannot find the rod end's axes")
        _, shank, lo, hi = best
        shank = shank if hi > -lo else tuple(-c for c in shank)      # from the ball towards the shank's end
        perp = [d for d, _a in groups if abs(_dot(d, shank)) < 0.05]
        if perp:
            bore = perp[0]
        else:
            bore = _basis_from_z(shank)[0]
        ez = tuple(-c for c in shank)                # the shank runs along -Z
        ey = _unit(_sub(bore, tuple(_dot(bore, ez) * c for c in ez)))
        ex = _cross(ey, ez)
        moved = _transform(shape, ex, ey, ez, ball)
        info.update({"axis_found": [round(c, 6) for c in shank], "bore_axis_found": [round(c, 6) for c in bore],
                     "origin_found": [round(c, 4) for c in ball]})
    else:
        axis = groups[0][0] if groups else _principal_axis(shape)
        ex, ey, ez = _basis_from_z(axis)
        moved = _transform(shape, ex, ey, ez, centre)        # axis on +Z through the centre of mass
        if kind in HEADED:
            # the head is the end with the largest-radius cylinder
            cz = [c for c in _cylinders(moved) if abs(c["dir"][2]) > 0.999]
            rmax = max(c["r"] for c in cz)
            head_z = sum(c["face"].BoundingBox().center.z for c in cz if c["r"] > rmax - 0.05) / max(
                1, sum(1 for c in cz if c["r"] > rmax - 0.05))
            bb = moved.BoundingBox()
            if head_z < (bb.zmin + bb.zmax) / 2:
                moved = moved.rotate((0, 0, 0), (1, 0, 0), 180)
            z0 = _head_underside_z(moved)
            moved = moved.translate((0, 0, -z0))
            info["head_d"] = round(2 * rmax, 3)
        else:
            moved = moved.translate((0, 0, -moved.BoundingBox().zmin))
        info.update({"axis_found": [round(c, 6) for c in axis], "origin_found": [round(c, 4) for c in centre]})

    info["bbox_mm"] = _bbox(moved)
    vol = moved.Volume()
    info["volume_mm3"] = round(vol, 3)
    rho = density if density is not None else density_for(material)
    info["density_g_cm3"] = rho
    info["mass_g_est"] = round(vol * rho / 1000.0, 3) if rho else None
    out = Path(out_path) if out_path else step_path.with_name(step_path.stem.split(".")[0] + ".norm.step")
    cq.exporters.export(cq.Workplane(obj=moved), str(out), exportType="STEP")
    info["norm"] = out.name
    return out, info


# ----------------------------------------------------------------------------------- the catalogue entry

DIM_KEYS = {
    # page label (lower case, contains) -> our dims_mm key
    "for shaft diameter": "id", "id": "id", "for housing id": "od", "od": "od", "width": "width",
    "length": "length", "shoulder diameter": "shoulder_d", "shoulder length": "shoulder_length",
    "head diameter": "head_d", "head height": "head_height", "thread length": "thread_length",
    "thread size": "thread", "diameter": "d", "thickness": "thickness", "height": "height",
    "hex width": "hex", "installed length": "installed_length", "drill bit size": "hole",
    "for hole diameter": "hole_d", "for material thickness": "panel_thickness", "center to end length": "centre_to_end",
    "ball width": "ball_width", "overall width": "overall_width",
}


def key_dims(parsed: Mapping[str, Mapping[str, Any]], raw: Mapping[str, str]) -> Dict[str, Any]:
    """The usual dimensions (mm) and the thread from the parsed spec table, under short keys."""
    dims: Dict[str, Any] = {}
    for label, p in parsed.items():
        lab = label.lower().split(" (")[0]
        key = DIM_KEYS.get(lab)
        if not key:
            continue
        if p.get("unit") == "mm" and "value" in p:
            dims.setdefault(key, p["value"])
        elif "thread" in p:
            dims.setdefault("thread", p["thread"])
    for label, v in raw.items():
        if label.lower().startswith("thread size") and "thread" not in dims:
            dims["thread"] = v
    return dims


def catalog_entry(page: Mapping[str, Any], info: Optional[Mapping[str, Any]] = None, cad: Optional[str] = None,
                  extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The catalogue record for one part from its page data (``Session.read``) and its ``normalise`` info."""
    raw = page.get("specs", {}).get("raw", {})
    parsed = page.get("specs", {}).get("parsed", {})
    material = material_of(raw)
    if raw.get("Finish"):
        material = f"{material}, {raw['Finish']}" if material else raw["Finish"]
    e: Dict[str, Any] = {
        "mcmaster": page.get("pn"),
        "description": page.get("description"),
        "url": page.get("url"),
        "price_usd": page.get("price_usd"),
        "pack_qty": page.get("pack_qty"),
        "price_text": page.get("price_text"),
        "dims_mm": key_dims(parsed, raw),
        "material": material or None,
    }
    if page.get("listed_weight_g"):
        e["mass_g"], e["mass_basis"] = page["listed_weight_g"], "McMaster listed weight"
    elif info and info.get("mass_g_est") is not None:
        e["mass_g"] = info["mass_g_est"]
        e["mass_basis"] = f"CAD volume x density {info.get('density_g_cm3')} g/cm3 (estimate)"
    else:
        e["mass_g"], e["mass_basis"] = None, "unknown"
    if cad:
        e["cad"] = cad
    if info:
        e["frame"] = info.get("frame")
        e["kind"] = info.get("kind")
        e["bbox_mm"] = info.get("bbox_mm")
        e["volume_mm3"] = info.get("volume_mm3")
    if page.get("options"):
        e["options"] = page["options"]
    e["specs"] = {"raw": raw, "parsed": parsed}
    e["page_read"] = page.get("read")
    if extra:
        e.update(extra)
    return e


def update_catalog(path, key: str, entry: Mapping[str, Any], source: Optional[str] = None) -> Dict[str, Any]:
    """Merge one entry into a catalogue JSON and return the merged entry. Two layouts are understood:

    * an object ``{"source": ..., "items": {key: entry}}`` (the default for a new file);
    * a list of items, each with an ``"id"`` (the entry with ``id == key`` is updated, or appended).

    Fields already in the file that the new entry does not set (used_for, qty, notes...) are kept."""
    path = Path(path)
    cat: Any = json.loads(path.read_text()) if path.exists() else {}
    if isinstance(cat, list):
        old = next((it for it in cat if it.get("id") == key), None)
        merged = dict(old or {"id": key})
        merged.update({k: v for k, v in entry.items() if v is not None or k not in merged})
        if old is None:
            cat.append(merged)
        else:
            cat[cat.index(old)] = merged
    else:
        cat.setdefault("source", source or f"McMaster-Carr product pages and CAD ({BASE_URL}); {SOURCE_NOTE}")
        items = cat.setdefault("items", {})
        merged = dict(items.get(key, {}))
        merged.update({k: v for k, v in entry.items() if v is not None or k not in merged})
        items[key] = merged
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    return merged
