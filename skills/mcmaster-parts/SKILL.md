---
name: mcmaster-parts
description: Use for any bought hardware in a CAD design (bearings, screws, nuts, washers, heat-set inserts, dowel and shoulder pins, standoffs and spacers, rod ends, threaded rod, grommets). Always choose a real McMaster-Carr part with a part number and place its manufacturer STEP model, normalised into a known frame, instead of drawing an envelope; record the part, its full specification table, price and mass in the project's hardware catalogue.
---

# McMaster-Carr parts

Bought hardware is a real part: a part number, its manufacturer's model, its specification. McMaster-Carr publishes
a STEP model and a full specification table (material, finish, strength class, thread, dimensions and tolerances,
load and speed ratings, temperature range, compliance) for almost everything it sells. Use them.

The tools: `cadagent.make.mcmaster` (Python) and `cad-agent mcmaster` (CLI). They read one product page at a time in the
system Chrome (Playwright), with a pause between pages. That is the same traffic as an engineer choosing parts, and
it must stay that way.

## Rules

- **Download like an engineer, not a crawler.** One part at a time, a pause between pages (default 3 s; the tool
  never goes below 2 s), only the product pages of the parts you are choosing. The tool accepts only McMaster part
  numbers (`PN_RE`, e.g. 91290A242), never a category, search or other URL. No bulk downloads, no parallel sessions.
  A part already downloaded is reused offline (no browser); download it again only when you need to (`--force`).
- **Keep the files local.** McMaster-Carr CAD is for design use; do not redistribute it. Gitignore the vendor folder
  and track only `SOURCE.txt`:

      references/vendor/**
      !references/vendor/**/
      !references/vendor/**/SOURCE.txt

- **Strong, but few parts.** Prefer one family per fastener type: for example, black-oxide alloy steel class 12.9
  socket head screws (91290A) with a minimal set of lengths; 18-8 stainless where corrosion matters; class 10 nyloc
  nuts; one washer family per size. When a computed length is not stocked, move the seat or the pilot depth so a
  stocked length fits (lesson 04) before adding another SKU. Report the number of distinct SKUs and the total part
  count.
- **Size from the CAD, then check against the page.** The stack comes from the CAD: grip, thread depth, insert pilot
  depth. Thread engagement is length minus grip. Check the chosen length against the depth actually available, and
  check the normalised model's bounding box against the catalogue dimensions.
- **Report what McMaster does not stock**, with the closest stocked alternative (for example, a 61812-2RS is not
  stocked; 6812-2Z is), and any CAD dimension that should move to a stocked size.

## Process

1. **Pick the part like an engineer.** Open the category page (e.g. `https://www.mcmaster.com/products/ball-bearings/`),
   filter it (System of Measurement → Metric, then size, material, thread) and read the table. Choose by function
   (load, fit, material, strength class) and by the SKUs you already use. Only then open the product page
   `https://www.mcmaster.com/<PN>/`.
2. **Download and normalise.**

       cad-agent mcmaster 91290A242 --kind screw --out references/vendor/mcmaster \
           --catalog catalog/hardware.json --key screw_m5x20

   This writes `OUT/<PN>/<PN>.step` (the download, kept only if it is a STEP file), `<PN>.page.json` (title, price,
   pack quantity, every spec row, option choices), `<PN>.norm.step`, `<PN>.norm.json` (axis found, how it was
   seated, bbox, volume, mass) and an entry in `SOURCE.txt`. Kinds and their frames (`cadagent.make.mcmaster.FRAMES`)
   all put the axis on +Z, through the origin (the cylinders' axis line, not the centre of mass); which end goes
   down is decided from the part's shape, not from how the vendor modelled it:
   - `bearing`, `washer`, `nut`, `insert`, `standoff`, `spacer`, `pin`, `grommet`, `rod`: the larger end (flange,
     collar, head) at z = 0 and the part on +z; when both ends are the same size, the heavier end down
     (`info["end_down"]` says which rule decided).
   - `screw`: head on +z, shank towards -z. z = 0 is the underside of the head for socket, button, pan, hex and
     flanged heads, and the top face for a countersunk (flat) head (`info["head"]`). A part with no head wider than
     its shank (set screw, stud) is refused: use `pin` or `rod`.
   - `shoulder_screw`: the underside of the head at z = 0, head on +z, shoulder and thread towards -z.
   - `rod_end`: the ball centre at the origin, ball bore along +Y, threaded shank along -Z (without a modelled ball,
     the middle of the bore).

   A part with variants (a rod end's thread direction, a choice of finish) offers its CAD only after the choice.
   Give the option text after the part numbers, one `--choose` per option, prefixed with the part it is for:

       cad-agent mcmaster 59935K53 91290A242 --choose "59935K53:Right Hand" --out references/vendor/mcmaster

   (the `PN:` prefix may be left out when there is one part number). In Python: `Session.fetch(pn, out,
   choose=["Right Hand"])`. The page data records what was offered and what was chosen.

   Playwright: `pip install playwright` into the environment that runs it, plus Google Chrome (then nothing else is
   needed; without Chrome the command stops with an install hint).
3. **Record the catalogue entry.** `catalog_entry()` / `--catalog` gives: `mcmaster` (PN), `description`, `url`,
   `price_usd`, `pack_qty`, `dims_mm`, `material`, `mass_g` with `mass_basis` (McMaster's listed weight when the
   page gives one, otherwise CAD volume x density, which it says), `cad` (the normalised STEP path), `frame`, and
   `specs.raw` (label → value) with `specs.parsed` (mm, g, N, MPa, deg C). Add what only the project knows:
   `used_for`, the quantity, and notes (stack and engagement arithmetic, CAD changes needed). Fields you add are kept
   when the entry is refreshed.
4. **Check the model.** Compare `bbox_mm` with the page's dimensions (a bearing's OD and width, a screw's length below
   the head, a rod end's centre-to-end length). A mismatch means the wrong frame or the wrong part.
5. **Place it in the assembly.** Import `<PN>.norm.step` and move it to the seat: for a screw, origin on the seat face
   and +Z out of the hole; for a bearing, the bottom face on the shoulder. Run the clash and tool-access checks
   (lesson 04) with the real heads, nuts and washers in place, not envelopes.

## Python

```python
import json

from cadagent import mcmaster as mc

with mc.Session(delay_s=3) as s:                    # one browser, one page at a time
    step = s.fetch("5972K82", "references/vendor/mcmaster/5972K82")
norm, info = mc.normalise(step, "bearing", material="Steel")
page = json.loads((step.parent / "5972K82.page.json").read_text())
mc.update_catalog("catalog/hardware.json", "bearing_6001",
                  mc.catalog_entry(page, info, cad=str(norm)) | {"used_for": "knee", "qty": 4})
```
