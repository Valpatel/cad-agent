# 01 — Verify from source

Board facts that the design depends on (connector side, voltages, designators, threads, which button is which) must
come from a primary source: the schematic, datasheet photos or the vendor's 3D model. They should not come from the
user's recollection or from the agent's assumptions. In this session the user's assumptions and the agent's were each
wrong at least once.

### Confirm which side of the board a connector is on, from photos
- **Rule:** Before designing a cable route, confirm the board side and mating direction of each connector from datasheet
  photos or drawings. Treat generic-height bodies in a vendor STEP as placeholders.
- **Incident:** The user asked how to "connect the cables to the top side of the board where we see sata and sata power
  connectors". In the STEP, no single solid matched a SATA connector, and the SATA bodies found were "3.81 mm-tall
  generic placeholders". The agent rendered the datasheet's top and bottom board photos at high resolution. The result:
  both SATA ports and their power headers are *vertical connectors on the underside* and plug in from below. The whole
  storage design (floor opening, chimney, trays under the unit) follows from this.
- **Check:** Every connector entry in the parameters has a `basis` that names its evidence (photo, STEP solid IDs,
  schematic sheet), for example "Two vertical SATA 7-pin receptacles on the underside (5063/5064; datasheet photo)". Flag
  any body whose height is a library default (3.81 mm here) as non-authoritative. J26 is an example: its placeholder
  was replaced by a 13.85 mm envelope.
- **Source:** 2026-10-24T17:33, 17:36, 17:39; 2026-10-25T00:36; `cad/parameters.json` (`underside_envelopes`), `README.md`.

### Read supply voltages off the schematic image, pin by pin
- **Rule:** When a voltage matters, render the schematic sheet as an image and read the net name on each pin. Do not
  rely on text extraction, and do not take the user's word for it. Then trace the rail back through the power tree.
- **Incident:** The user said: "12V won't come from some external connector, the 12V connector is next to the sata
  connector, one for each sata port on the pcb, review the schematic." The agent rendered sheet 27. On J22 (and
  identically J23), pin 1 is not connected, pins 2–3 are ground and pin 4 is SATA_5V. SATA_5V is switched by Q59, with a
  2 A bead per port. The power tree on sheet 3 shows that VDD_12V feeds only the camera expansion connector. The first
  crop cut off the SATA_5V net label, so the agent widened it. The answer was "no 12 V on its SATA power connectors".
  The crops went on the website, and the agent offered to redesign if a photo showed a 12 V header that is missing from
  the v1.0 schematic (dated 2024-05-29).
- **Check:** For each power pin used, record the sheet, pin and net, plus the upstream rail. Publish the crop with the
  net label visible.
- **Source:** 2026-10-25T01:27, 01:28, 01:29, 01:30; `cad/parameters.json` (SATA power `basis`).

### Re-derive designators from the schematic; name by position when the model can't tell
- **Rule:** Check every reference designator in docs and BOMs against the schematic. If the 3D model does not say which
  physical part is which designator, write the instruction by position and list the designator mapping as unverified.
- **Incident:** The agent had J23 and J24 swapped. Per the schematic, data is J21 (port 0) and J24 (port 1), and power
  is J22 and J23. The STEP does not record which physical connector is J21, so the wiring rule now says "the 3.5 in
  drive takes the **front** SATA connector". The parameters tell the builder to check the SATA1/SATA2 silkscreen.
- **Check:** Search the docs, BOM and diagrams for each designator and compare against the schematic. Each
  designator-to-location mapping carries a field-verification note (silkscreen or photo).
- **Source:** 2026-10-25T01:29, 01:30; `cad/parameters.json` (`cables.wiring_rule`).

### Infer the thread from hole sizes when nobody can tell you
- **Rule:** If the thread of a mating part is unknown, infer it from the clearance holes in the vendor model, and state
  the inference.
- **Incident:** The user: "The screw thread you should get approximately from the screw hole size, but M3 sounds right."
  The NVIDIA module model has Ø3.5 holes through the module PCB and Ø3.7 holes through the thermal plate. Both are M3
  clearance holes, so M3 was adopted for the tie-down screws.
- **Check:** Measure the hole diameters in the STEP and compare them with a clearance-hole table for candidate threads.
  Record both diameters in the fastener's `basis` ("M3 from the module holes: D3.5 PCB, D3.7 thermal plate").
- **Source:** 2026-10-25T00:37, 00:38; `cad/parameters.json` (`heatsink_screw`).

### Say what the sources do not tell you, and keep the label provisional
- **Rule:** When the sources leave a fact open, say so, use a neutral label and ask the user one specific question. Do
  not guess.
- **Incident:** The schematic shows SW1 = FORCE_RECOVERY and SW2 = power/reset, both Alps SKQJLBA010 right-angle tact
  switches. The STEP does not record which actuator is SW1, and Seeed's docs did not say either. The rear plate was
  labelled "RST/REC", and the user was asked which one is closer to the board corner. The question was repeated later
  and is still unanswered in the transcript.
- **Check:** Keep an open-questions list on the progress page. Every feature that depends on an open question has a
  provisional marker.
- **Source:** 2026-10-24T16:35, 17:10; 2026-10-25T00:36; `cad/parameters.json` (button `basis`).

### Use vendor-model bodies as proxies for missing data, and say they are proxies
- **Rule:** When the board model lacks copper and drill data, look for bodies that stand in for it, such as mount-pad
  proxies. Use their size, label it an assumption, and ask for one measurement.
- **Incident:** The carrier STEP has no copper or drilled holes. It does have a body at each mounting hole that matches
  the pad: Ø6.9 at the four board holes and Ø7.14 at the four cooler holes (solids 5155–5162). The agent took those as
  the pad sizes, assumed the underside pads are the same, and asked the user to "measure one with calipers".
- **Check:** The parameter `landing_basis` names the solid IDs and the assumption. Physical measurement stays on the
  pre-print checklist.
- **Source:** 2026-10-24T16:39, 17:10; `cad/parameters.json` (`landing_basis`).
