"""McMaster-Carr parts: the manufacturer's CAD (STEP) and the product data for one part number, in a frame a CAD
build can place.

Bought hardware in a design (bearings, screws, nuts, washers, inserts, pins, standoffs, rod ends, grommets) should be a
real part with a part number, not an envelope. McMaster-Carr publishes a STEP model and a full specification table for
almost every part it sells. This module gets both, the way an engineer does while working:

* one product page at a time, in a real browser (Playwright driving the system Chrome, ``channel="chrome"``);
* a pause between pages (``delay_s``, 3 s by default and never less than ``MIN_DELAY_S``) and only the product pages
  of the parts being chosen: a part number must look like one (``PN_RE``), so category, search and other URLs
  cannot be fetched;
* no crawling, no scraping of search or category pages, no parallel requests.

The files stay local. McMaster-Carr CAD is provided for design use; it is not ours to redistribute, so keep the
download folder out of version control (track only ``SOURCE.txt``, which ``write_source`` writes).

What it gives you
-----------------
``fetch(pn, out_dir)``
    Opens ``https://www.mcmaster.com/<PN>/``, reads the page (title, price and pack quantity, every row of the
    specification table, the option choices the page offers) into ``<PN>.page.json``, then picks "3-D STEP" in the
    CAD menu and saves the download as ``<PN>.step`` once it has checked that it is a STEP file. Returns the STEP
    path. ``Session`` does the same for several part numbers with one browser. A page with no specification table
    raises RuntimeError; when McMaster showed a login prompt instead (``login_gate``), it raises ``LoginRequired``,
    whose message says the part number may be fine and where else to read the part's data.
``normalise(step_path, kind)``
    Finds the part's axis from its cylindrical faces and moves it into the frame for its kind (``FRAMES``), writes
    ``<PN>.norm.step`` and returns ``(path, info)`` with the axis found, the bounding box, the volume and a mass.
``catalog_entry(page, info, ...)``
    The catalogue record: part number, description, URL, price, pack quantity, key dimensions, material, mass
    (McMaster's listed weight when the page gives one, else volume x density, and which), the normalised CAD path, the
    frame, and the whole specification table (``specs.raw`` label -> value strings, ``specs.parsed`` numbers in mm, g,
    N, MPa or deg C where the unit is unambiguous).

Install: ``pip install playwright`` into the environment that runs this, and Google Chrome (then no
``playwright install`` is needed). The CAD steps need CadQuery (the ``cad`` extra); the page parsing and the
catalogue helpers need neither.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import shutil
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import MissingDependency, require
from cadagent.geometry import export_step

BASE_URL = "https://www.mcmaster.com"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")
PLAYWRIGHT_HINT = ("McMaster downloads need Playwright: pip install playwright (into the environment that runs "
                   "cad-agent). With Google Chrome installed, `playwright install` is not needed.")
CHROME_HINT = ("McMaster downloads drive the system Google Chrome (Playwright channel 'chrome'), which could not be "
               "started: install Google Chrome, or run `playwright install chrome`.")
SOURCE_NOTE = "McMaster-Carr CAD, for design use; not redistributed."
MIN_DELAY_S = 2.0            # the pause between product pages is never shorter than this
# McMaster-Carr part numbers: digits, one to three letters, digits (5972K82, 91290A242, 9307K884, 1061T17)
PN_RE = re.compile(r"^\d{1,6}[A-Z]{1,3}\d{1,6}$")

# Frame conventions, one per kind of part. The axis is always +Z and passes through the origin.
_ROUND = ("axis +Z, centred on the axis; the larger end (flange, head, collar) at z = 0 and the part on +z; "
          "when both ends are the same size, the heavier end at z = 0")
FRAMES = {
    "bearing": _ROUND,
    "washer": _ROUND,
    "nut": _ROUND,
    "insert": _ROUND,
    "standoff": _ROUND,
    "spacer": _ROUND,
    "pin": _ROUND,
    "grommet": _ROUND,
    "rod": _ROUND,
    "screw": ("axis +Z, centred on the axis, head on +z and shank towards -z; z = 0 at the underside of the head "
              "(socket, button, pan, hex and flanged heads) or at the top face of a countersunk (flat) head"),
    "shoulder_screw": "axis +Z, centred on the axis, underside of the head at z = 0, head on +z, shoulder and thread "
                      "towards -z",
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
# spec labels that are the part's own weight (not a load rating such as 'Weight Capacity')
WEIGHT_LABELS = ("weight", "net weight", "part weight", "approximate weight", "weight per piece")


# ----------------------------------------------------------------------------------- the product page

def validate_pn(pn: str) -> str:
    """A McMaster-Carr part number, upper case, or ValueError. Only product pages are fetched, so anything else
    (a category path, a search term, a URL, '../x') is refused before it reaches a URL or a file path."""
    p = (pn or "").strip().upper()
    if not PN_RE.match(p):
        raise ValueError(f"{pn!r} is not a McMaster-Carr part number (like 91290A242); only product pages are fetched")
    return p


def product_url(pn: str) -> str:
    return f"{BASE_URL}/{validate_pn(pn)}/"


# ----------------------------------------------------------------------------------- pages that are not product pages

# What McMaster shows in place of the product detail when it wants the session to sign in ("Log in to view Product
# Detail", seen 2026-10-29 and 2026-10-31). Only the phrase counts: every McMaster page has a "Log in" link in its
# header, so a page that merely links to the login is not a login gate.
LOGIN_GATE_RE = re.compile(r"\b(?:log ?in|sign ?in) to (?:view|see|continue)\b[^.!?\n]{0,40}", re.I)


class LoginRequired(RuntimeError):
    """McMaster showed a login prompt instead of the product page. The part number may be fine; this session cannot
    read the page."""


class _Text(HTMLParser):
    """The visible text of an HTML page, a line per block element: everything outside ``<script>``, ``<style>``,
    ``<noscript>`` and ``<template>``."""
    _SKIP = {"script", "style", "noscript", "template"}
    _BLOCK = {"address", "article", "aside", "blockquote", "br", "button", "dd", "dialog", "div", "dl", "dt",
              "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
              "hr", "li", "main", "nav", "ol", "option", "p", "pre", "section", "table", "td", "th", "tr", "ul"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in self._SKIP:
            self._skip = max(self._skip - 1, 0)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data) -> None:
        if not self._skip:
            self.parts.append(re.sub(r"\s+", " ", data))     # a line break in the source is a space


def page_text(html: str) -> str:
    """The visible text of a page's HTML: one line per block element, spaces collapsed (no browser needed)."""
    parser = _Text()
    parser.feed(html or "")
    parser.close()
    lines = (re.sub(r" +", " ", line).strip() for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def login_gate(html: str) -> Optional[str]:
    """The login prompt a page shows in place of the product detail (e.g. "Log in to view Product Detail"), or None.
    ``html`` is the page's HTML; only its visible text is searched."""
    m = LOGIN_GATE_RE.search(page_text(html))
    return m.group(0).strip(" ,;:-") if m else None


def page_error(pn: str, url: str, html: str = "") -> RuntimeError:
    """Why the page at ``url`` is not a product page this session can read, as the exception to raise: a
    ``LoginRequired`` when McMaster asked for a login (the part number may be fine), else a plain RuntimeError
    saying there is no specification table (a wrong or retired part number, or a page that did not load)."""
    prompt = login_gate(html)
    if prompt:
        return LoginRequired(
            f"{pn}: McMaster asked for a login (\"{prompt}\" at {url}) instead of showing the product page, so the "
            "part number may be fine; nothing was read or downloaded. Retry later from a new session, once. By hand, "
            f"McMaster's public search page ({BASE_URL}/<trade number or size>/, e.g. {BASE_URL}/6301-2RS/) gives "
            "the part number and price, and the maker's datasheet gives the ratings and dimensions the search table "
            "leaves out (such as a bearing's static load rating).")
    return RuntimeError(f"{pn}: {url} is not a product page (no specification table)")


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
    force = any(k in lab for k in ("load", "capacity", "force", "strength", "pull", "thrust", "torque", "rating"))
    if u in ("lb", "lbs", "lbf"):
        if force:                                       # 'Weight Capacity' is a load, not the part's weight
            return x * 4.4482216, "N"
        if "weight" in lab or "mass" in lab:
            return x * 453.59237, "g"
        return None                                     # lb of what: not unambiguous
    if u == "oz":
        return (x * 28.349523, "g") if ("weight" in lab or "mass" in lab) and not force else None
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


def listed_weight_g(parsed: Mapping[str, Mapping[str, Any]]) -> Optional[float]:
    """The part's own weight in g when the page lists one under a weight label (never a 'Weight Capacity')."""
    for k, p in parsed.items():
        if k.split(" (")[0].strip().lower() in WEIGHT_LABELS and p.get("unit") == "g" and "value" in p:
            return p["value"]
    return None


def page_data(pn: str, d: Mapping[str, Any], final_url: str = "") -> Dict[str, Any]:
    """The page record from what ``_PAGE_JS`` read off a product page."""
    raw, parsed = parse_specs(d["rows"])
    price, pack = parse_price(d["price_text"])
    return {"pn": pn, "url": product_url(pn), "final_url": final_url, "title": d["title"],
            "subtitle": d["subtitle"], "description": ", ".join(t for t in (d["title"], d["subtitle"]) if t),
            "price_text": d["price_text"], "price_usd": price, "pack_qty": pack,
            "listed_weight_g": listed_weight_g(parsed), "options": d["options"], "breadcrumbs": d["breadcrumbs"],
            "specs": {"raw": raw, "parsed": parsed}, "read": _dt.date.today().isoformat()}


def accept_download(tmp: Path, out: Path, suggested: str = "") -> Path:
    """Keep a downloaded file as ``out`` only if it is a STEP file (``ISO-10303-21`` header), taking the STEP out
    of a zip if that is what came. Anything else is deleted and raises RuntimeError, so a bad download never sits
    under the STEP's name (where a later run would take it as already downloaded)."""
    tmp, out = Path(tmp), Path(out)
    data: Optional[bytes] = None
    try:
        if zipfile.is_zipfile(tmp):
            with zipfile.ZipFile(tmp) as z:
                names = [n for n in z.namelist() if n.lower().endswith((".step", ".stp"))]
                if names:
                    data = z.read(names[0])
        else:
            data = tmp.read_bytes()
        if data is None or not data.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"ISO-10303-21"):
            raise RuntimeError(f"the download {suggested or tmp.name!r} is not a STEP file; nothing was kept")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return out
    finally:
        tmp.unlink(missing_ok=True)


class Session:
    """One browser for a few part numbers, one product page at a time with a pause between pages.

        with Session() as s:
            step = s.fetch("5972K82", "vendor/mcmaster/5972K82")

    ``delay_s`` is clamped to at least ``MIN_DELAY_S``; ``timeout_s`` applies to every page action."""

    def __init__(self, delay_s: float = 3.0, headless: bool = True, timeout_s: float = 60.0):
        self.delay_s = max(float(delay_s), MIN_DELAY_S)
        self.headless, self.timeout_ms = headless, int(timeout_s * 1000)
        self._pw = self._browser = self._ctx = self.page = None
        self._last = 0.0

    def __enter__(self) -> "Session":
        self._pw = _playwright()().start()
        try:
            self._browser = self._pw.chromium.launch(channel="chrome", headless=self.headless,
                                                     args=["--disable-blink-features=AutomationControlled"])
        except Exception as exc:                          # Chrome missing: stop the driver, explain, no traceback
            self.__exit__()
            raise MissingDependency(f"{CHROME_HINT} ({str(exc).splitlines()[0] if str(exc) else exc!r})") from exc
        self._ctx = self._browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 1000},
                                              user_agent=USER_AGENT)
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._browser, self._pw):
            if closer is None:
                continue
            try:
                closer.stop() if closer is self._pw else closer.close()
            except Exception:
                pass
        self._browser = self._pw = None

    def _open(self, pn: str) -> None:
        url = product_url(pn)                             # validates the part number
        wait = self.delay_s - (time.monotonic() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)                              # the pause between pages
        self.page.goto(url, wait_until="domcontentloaded")
        self._last = time.monotonic()
        try:
            self.page.wait_for_selector('tr[class*="product-detail-spec-table-row"]')
        except Exception:
            try:
                html = self.page.content()
            except Exception:
                html = ""
            raise page_error(pn, self.page.url, html) from None
        self.page.wait_for_timeout(1500)

    def read(self, pn: str, reload: bool = True) -> Dict[str, Any]:
        """The product page's data (title, price, pack, every spec row, the option choices)."""
        pn = validate_pn(pn)
        if reload:
            self._open(pn)
        return page_data(pn, self.page.evaluate(_PAGE_JS), self.page.url)

    def choose(self, options: Sequence[str]) -> List[str]:
        """Click option choices on the open product page (e.g. "Right Hand" for a rod end's thread direction), in
        order. Some parts offer their CAD only after every choice is made."""
        done = []
        for text in options or ():
            loc = self.page.get_by_text(text, exact=True)
            if not loc.count():
                raise RuntimeError(f"no option {text!r} on {self.page.url}; offered: "
                                   f"{'; '.join(self.page.evaluate(_PAGE_JS)['options']) or 'none'}")
            loc.first.click()
            self.page.wait_for_timeout(2500)
            done.append(text)
        return done

    def download_step(self, pn: str, out: Path) -> Path:
        """Pick '3-D STEP' in the CAD menu of the open product page, download it with that menu's own Download
        button, check it is a STEP file and save it as ``out``."""
        pg = self.page
        menu = pg.locator('[aria-label="Select CAD file type"]')
        if not menu.count():
            raise RuntimeError(f"{pn}: no CAD menu on the product page")
        menu = menu.first
        if menu.get_attribute("aria-disabled") == "true":
            raise RuntimeError(f"{pn}: the CAD menu is disabled until an option is chosen; pass the option text "
                               f"(choose=[...], --choose {pn}:OPTION), one of the page's choices: "
                               f"{'; '.join(pg.evaluate(_PAGE_JS)['options']) or 'see the page'}")
        # the CAD control: the nearest block round the menu that holds a Download button (not a PDF link elsewhere)
        control = menu.locator("xpath=ancestor::*[.//button[normalize-space(.)='Download']][1]")
        button = control.locator("xpath=.//button[normalize-space(.)='Download']").first
        menu.click()
        pg.wait_for_timeout(800)
        options = pg.get_by_role("option")
        offered = [t.strip() for t in options.all_inner_texts()] if options.count() else []
        step = options.filter(has_text=re.compile(r"^\s*3-D STEP\s*$"))
        if not step.count():
            step = pg.get_by_text("3-D STEP", exact=True)
        if not step.count():
            raise RuntimeError(f"{pn}: no 3-D STEP on this page; CAD types offered: {', '.join(offered) or 'none'}")
        step.first.click()
        pg.wait_for_timeout(800)
        href = control.locator("xpath=.//a[@href]").first
        if href.count():
            h = (href.get_attribute("href") or "").lower()
            if h and not re.search(r"\.(step|stp|zip)(\?|$)", h):
                raise RuntimeError(f"{pn}: choosing 3-D STEP did not switch the download (it points at {h})")
        with pg.expect_download() as dl:
            button.click()
        tmp = out.with_name(f".{out.name}.download")
        out.parent.mkdir(parents=True, exist_ok=True)
        dl.value.save_as(str(tmp))
        return accept_download(tmp, out, dl.value.suggested_filename)

    def fetch(self, pn: str, out_dir, choose: Optional[Sequence[str]] = None, write_page: bool = True) -> Path:
        """Read the product page and download its STEP: ``<out_dir>/<PN>.step`` and ``<PN>.page.json``, and add the
        part to ``SOURCE.txt``. ``choose`` lists option texts to click first (a part with variants). Returns the
        STEP path."""
        pn = validate_pn(pn)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        page = self.read(pn)
        if choose:
            options = page["options"]
            self.choose(choose)
            page = self.read(pn, reload=False)                # price and specs of the chosen variant
            page["options_offered"], page["chosen"] = options, list(choose)
        step = self.download_step(pn, out_dir / f"{pn}.step")
        page["step"] = step.name
        if write_page:
            (out_dir / f"{pn}.page.json").write_text(json.dumps(page, indent=1, ensure_ascii=False) + "\n")
        write_source(out_dir, pn, page.get("description", ""))
        return step


def fetch(pn: str, out_dir, delay_s: float = 3.0, choose: Optional[Sequence[str]] = None) -> Path:
    """One part: read its product page into ``<PN>.page.json`` and download its STEP into ``out_dir``. Returns the
    STEP path. For several parts use one ``Session`` (one browser, a pause between pages)."""
    with Session(delay_s=delay_s) as s:
        return s.fetch(pn, out_dir, choose=choose)


def write_source(folder, pn: str, description: str = "", when: Optional[str] = None) -> Path:
    """Add (or update) this part's entry in the folder's SOURCE.txt: what it is, where it came from, when, and the
    terms it is used under. Entries for other parts in the same folder are kept."""
    pn = validate_pn(pn)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "SOURCE.txt"
    header = (f"McMaster-Carr parts. {SOURCE_NOTE}\n"
              "Files per part: <PN>.step (as downloaded), <PN>.norm.step (moved into the frame for its kind), "
              "<PN>.page.json (the product page's data).")
    entry = (f"{pn} {description}".rstrip() + "\n"
             f"URL: {product_url(pn)}\n"
             f"Downloaded: {when or _dt.date.today().isoformat()}")
    blocks = [b.strip("\n") for b in p.read_text().split("\n\n")] if p.exists() else []
    blocks = [b for b in blocks if b and not b.startswith("McMaster-Carr parts.")
              and b.split(None, 1)[0] != pn and not b.startswith(f"{pn}\n")]
    p.write_text("\n\n".join([header] + blocks + [entry]) + "\n")
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


def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


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
        ts = [_dot(_vec(v.toTuple()), d) for v in f.Vertices()] or [_dot(p, d)]
        out.append({"dir": d, "loc": p, "r": cyl.Radius(), "area": f.Area(), "t": (min(ts), max(ts))})
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


def _axes(cyls) -> List[Dict[str, Any]]:
    """Cylinder axis lines, grouped by direction (up to sign) and then by line, largest total area first. Each has
    ``dir``, ``point`` (the point of the line nearest the origin), ``area``, ``t`` (extent of its faces along it) and
    ``group_area`` (the area of every cylinder in that direction)."""
    lines: List[Dict[str, Any]] = []
    for c in cyls:
        d = c["dir"]
        q = _add(c["loc"], d, -_dot(c["loc"], d))
        for ln in lines:
            if abs(_dot(ln["dir"], d)) > 0.999 and math.dist(ln["point"], q) < 0.01:
                ln["area"] += c["area"]
                sgn = 1.0 if _dot(ln["dir"], d) > 0 else -1.0
                ln["t"] = (min(ln["t"][0], min(sgn * c["t"][0], sgn * c["t"][1])),
                           max(ln["t"][1], max(sgn * c["t"][0], sgn * c["t"][1])))
                break
        else:
            lines.append({"dir": d, "point": q, "area": c["area"], "t": c["t"]})
    for ln in lines:
        ln["group_area"] = sum(o["area"] for o in lines if abs(_dot(o["dir"], ln["dir"])) > 0.999)
    return sorted(lines, key=lambda ln: (-ln["group_area"], -ln["area"]))


def _principal_axis(shape) -> Tuple[float, float, float]:
    """Fallback for parts with no cylinders: the principal axis of inertia whose moment differs most from the others
    (the symmetry axis of a body of revolution)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    pp = props.PrincipalProperties()
    m = list(pp.Moments())
    axes = [pp.FirstAxisOfInertia(), pp.SecondAxisOfInertia(), pp.ThirdAxisOfInertia()]
    odd = max(range(3), key=lambda i: min(abs(m[i] - m[j]) for j in range(3) if j != i))
    a = axes[odd]
    return _unit((a.X(), a.Y(), a.Z()))


def _basis_from_z(z):
    """Any right-handed (x, y, z) basis with the given z."""
    ref = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
    x = _unit(_cross(ref, z))
    y = _cross(z, x)
    return x, y, z


def _transform(shape, ex, ez, origin):
    """Move a shape so the source frame (x along ex, z along ez, at origin) becomes the world frame."""
    import cadquery as cq
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Pnt(*origin), gp_Dir(*ez), gp_Dir(*ex)))
    return cq.Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, t, True).Shape())


def _flip(shape):
    return shape.rotate((0, 0, 0), (1, 0, 0), 180)


def _bbox(shape) -> Dict[str, Any]:
    b = shape.BoundingBox()
    r = lambda v: round(v, 4) + 0.0                        # + 0.0: no -0.0
    return {"min": [r(b.xmin), r(b.ymin), r(b.zmin)], "max": [r(b.xmax), r(b.ymax), r(b.zmax)],
            "size": [r(b.xlen), r(b.ylen), r(b.zlen)]}


def _profile(shape, samples: int = 12) -> List[Tuple[float, float]]:
    """(z, distance from the Z axis) at points along every edge of a part lying on the Z axis: its outline as seen
    from the side, whatever surfaces the head or flange is made of (planes, cones, tori, spheres)."""
    pts = [(v.z, math.hypot(v.x, v.y)) for v in (vv.Center() for vv in shape.Vertices())]
    for e in shape.Edges():
        for i in range(samples + 1):
            try:
                p = e.positionAt(i / samples)
            except Exception:
                continue
            pts.append((p.z, math.hypot(p.x, p.y)))
    return pts


def _end_radii(pts, frac: float = 0.15) -> Tuple[float, float, float, float]:
    """(radius near the bottom end, radius near the top end, zmin, zmax): the largest distance from the axis within
    ``frac`` of the length from each end."""
    zmin, zmax = min(z for z, _ in pts), max(z for z, _ in pts)
    slab = max(frac * (zmax - zmin), 1e-3)
    rb = max((r for z, r in pts if z <= zmin + slab), default=0.0)
    rt = max((r for z, r in pts if z >= zmax - slab), default=0.0)
    return rb, rt, zmin, zmax


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


def _seat_headed(shape, kind: str, info: Dict[str, Any]):
    """A headed part on the Z axis: head up, z = 0 at the underside of the head (the top face of a countersunk
    head). Raises ValueError when no end is clearly wider than the other (a set screw, a stud: use another kind)."""
    pts = _profile(shape)
    rb, rt, zmin, zmax = _end_radii(pts)
    if rb > rt:                                          # head at the bottom: turn it up
        shape = _flip(shape)
        pts = [(-z, r) for z, r in pts]
        rb, rt, zmin, zmax = rt, rb, -zmax, -zmin
    head_r, shank_r = rt, rb
    if head_r < 1.15 * shank_r:
        raise ValueError(f"no head wider than the shank (ends {2 * shank_r:.2f} and {2 * head_r:.2f} mm across): "
                         f"not a {kind} this module can seat")
    threshold = shank_r + 0.5 * (head_r - shank_r)
    z_under = min(z for z, r in pts if r > threshold)    # lowest point of the head
    z_wide = min(z for z, r in pts if r >= 0.98 * head_r)  # lowest point at the head's full width
    countersunk = kind == "screw" and (z_wide - z_under) > 0.5 * (zmax - z_under)
    z0 = zmax if countersunk else z_under
    info.update({"head": "countersunk" if countersunk else "flat underside", "head_d": round(2 * head_r, 3),
                 "shank_d": round(2 * shank_r, 3)})
    return shape.translate((0, 0, -z0))


def _seat_round(shape, info: Dict[str, Any]):
    """A round part on the Z axis: the larger end down (or the heavier end, when both are the same size), z = 0
    there."""
    pts = _profile(shape)
    rb, rt, zmin, zmax = _end_radii(pts, 0.1)
    if abs(rt - rb) > 0.01 * max(rt, rb):
        flip, why = rt > rb, "larger end"
    else:                                                 # same size ends: the centre of mass is at z = 0
        mid = (zmin + zmax) / 2
        flip = mid < -1e-3 * (zmax - zmin)
        why = "heavier end" if abs(mid) > 1e-3 * (zmax - zmin) else "symmetric"
    if flip:
        shape = _flip(shape)
    info["end_down"] = why
    return shape.translate((0, 0, -shape.BoundingBox().zmin))


def _seat_rod_end(shape, cyls, info: Dict[str, Any]):
    """Rod end: the ball centre at the origin, the bore along +Y, the shank along -Z."""
    axes = _axes(cyls)
    if not axes:
        raise ValueError("no cylindrical faces: cannot find a rod end's bore and shank")
    verts = [_vec(v.Center()) for v in shape.Vertices()]

    def extent(d):
        ts = [_dot(p, d) for p in verts]
        return max(ts) - min(ts)

    dirs: List[Tuple[float, float, float]] = []
    for ln in axes:
        if all(abs(_dot(ln["dir"], d)) < 0.999 for d in dirs):
            dirs.append(ln["dir"])
    shank = max(dirs, key=extent)                         # a rod end is longest along its shank
    across = [ln for ln in axes if abs(_dot(ln["dir"], shank)) < 0.05]
    if not across:
        raise ValueError("no cylinder across the shank: cannot find a rod end's ball bore")
    bore_ln = max(across, key=lambda ln: ln["area"])
    bore = bore_ln["dir"]
    spheres = sorted(_spheres(shape), key=lambda s: -s["area"])
    if spheres:
        ball, info["ball_d"], info["centre_from"] = spheres[0]["centre"], round(2 * spheres[0]["r"], 3), "ball sphere"
    else:                                                 # the middle of the bore's faces along the bore axis
        ball = _add(bore_ln["point"], bore, (bore_ln["t"][0] + bore_ln["t"][1]) / 2)
        info["ball_d"], info["centre_from"] = None, "bore midpoint (no sphere in the model)"
    ts = [_dot(_sub(p, ball), shank) for p in verts]
    if max(ts) < -min(ts):
        shank = tuple(-c for c in shank)                  # from the ball towards the shank's end
    ez = tuple(-c for c in shank)                         # the shank runs along -Z
    ey = _unit(_add(bore, ez, -_dot(bore, ez)))
    ex = _cross(ey, ez)
    info.update({"axis_found": [round(c, 6) for c in shank], "bore_axis_found": [round(c, 6) for c in bore],
                 "origin_found": [round(c, 4) for c in ball]})
    return _transform(shape, ex, ez, ball)


def normalise(step_path, kind: str, density: Optional[float] = None, out_path=None,
              material: str = "") -> Tuple[Path, Dict[str, Any]]:
    """Move a part into the frame for its kind (``FRAMES``) and write ``<name>.norm.step`` next to it
    (``geometry.export_step``: the same bytes on every run).

    The axis comes from the cylindrical faces (the direction carrying the most cylinder area, through the line of
    the largest coaxial set), or from the principal axes of inertia when there are none; the part is centred on
    that line, not on its centre of mass. Which end goes to z = 0 is decided from the geometry (the part's outline
    along the axis), so it does not depend on how the vendor modelled the part. Returns (path, info): the axis and
    origin found in the original file, how the part was seated, the bounding box after the move, the volume (mm3) and
    the mass (g) for ``density`` (g/cm3; from ``material`` when not given)."""
    if kind not in FRAMES:
        raise ValueError(f"unknown kind {kind!r}; kinds: {', '.join(KINDS)}")
    cq = require("cadquery", "normalising a McMaster STEP")
    step_path = Path(step_path)
    objs = cq.importers.importStep(str(step_path)).vals()
    if not objs:
        raise ValueError(f"{step_path.name}: no shapes in the STEP file")
    shape = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)
    cyls = _cylinders(shape)
    com = _vec(cq.Shape.centerOfMass(shape))
    info: Dict[str, Any] = {"kind": kind, "frame": FRAMES[kind], "source": step_path.name}

    if kind == "rod_end":
        moved = _seat_rod_end(shape, cyls, info)
    else:
        axes = _axes(cyls)
        if axes:
            axis, point = axes[0]["dir"], axes[0]["point"]
            origin = _add(point, axis, _dot(_sub(com, point), axis))     # on the axis line, level with the COM
            info["axis_from"] = "cylinders"
        else:
            axis, origin = _principal_axis(shape), com
            info["axis_from"] = "principal axes of inertia (no cylinders)"
        ex, _, ez = _basis_from_z(axis)
        moved = _transform(shape, ex, ez, origin)
        moved = _seat_headed(moved, kind, info) if kind in HEADED else _seat_round(moved, info)
        info.update({"axis_found": [round(c, 6) for c in axis], "origin_found": [round(c, 4) for c in origin]})

    info["bbox_mm"] = _bbox(moved)
    vol = moved.Volume()
    info["volume_mm3"] = round(vol, 3)
    rho = density if density is not None else density_for(material)
    info["density_g_cm3"] = rho
    info["mass_g_est"] = round(vol * rho / 1000.0, 3) if rho else None
    out = Path(out_path) if out_path else step_path.with_name(step_path.stem.split(".")[0] + ".norm.step")
    export_step(moved, out)                               # same bytes for the same part on every run (#91)
    info["norm"] = out.name
    return out, info


# ----------------------------------------------------------------------------------- the catalogue entry

DIM_KEYS = {
    # page label, lower case, matched exactly (a ' (2)' de-duplication suffix is ignored) -> our dims_mm key
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
