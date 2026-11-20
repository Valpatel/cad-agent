# Equipment illustration references

The symbols are original pictorial SCADA artwork. References inform recognizable
parts and flow paths; they do not establish vendor dimensions, engineering
performance or standards compliance. These illustrations are not IEC/ANSI wiring
symbols or operating instructions. Values supplied by the example models remain
editable assumptions.

Review the real renderer at card size, as a large preview and inside the shared
viewer. Check active, stopped, paused, unavailable and relevant damage states.
Use the [style guide](../STYLE_GUIDE.md) and [gallery](../img/README.md); image
previews do not replace interaction or model tests.

## Pump, solar and separation

| Equipment | Reference and design consequence | Deliberate simplification |
| --- | --- | --- |
| Submersible pump | [Xylem Flygt N-pump brochure](https://www.xylem.com/siteassets/brand/flygt/resources/brochure/flygt-n-pump-brochure-896876.pdf), pages 5–6: connected lifting handle, separate cable entry, upright motor and lower impeller/casing | Original cutaway, blade count, intake strainer and discharge arrangement; no product rating or installation dimension |
| Solar array | [DOE photovoltaic cell basics](https://www.energy.gov/cmei/systems/solar-photovoltaic-cell-basics): incident light and collected electric current are different paths | Grid, sun rays, glint and DC cadence illustrate the supplied load; no irradiance, temperature or IV-curve prediction |
| Three-phase separator | [SLB multiphase separators](https://www.slb.com/products-and-services/innovating-in-oil-and-gas/well-production/processing-and-separation/oil-treatment/multiphase-separators), separation explanation: gas exits above; water settles below oil and has a separate outlet | Supplied level changes visible inventory. Oil/water proportions are fixed illustrative fractions, not separation physics. The flash-water variant shows steam/water and drain, without an oil phase |

The pump's cable and handle attach to different physical features. Solar current
stops at zero load and in unavailable or failed states. Separator phase colors,
short labels and arrowheads distinguish its outlets; empty liquid inventory hides
liquid discharge motion. A warning badge occupies free space rather than covering
the top outlet.

## Electrical protection and pressurizer

| Equipment | Reference inspected | Illustration boundary |
| --- | --- | --- |
| Current transformer | [Hammond CT Series](https://www.hammfg.com/electronics/transformers/instrument/ct) and its [data sheet](https://www.hammfg.com/electronics/transformers/instrument/ct.pdf), page 1 | Toroidal window, primary conductor and separate secondary leads. Winding exposure and proportions are original; no ratio or rating is implied |
| Protection relay | [SEL-751 data sheet](https://selinc.com/api/download/10734/?lang=en), retrieved edition 2026-09-10, features and Figure 36 | Generic protection cue, dedicated trip-output indicator and contact. It is not an SEL rendering or protection algorithm |
| Pressurizer | [DOE-HDBK-1018/2-93, Mechanical Science Volume 2](https://www.energy.gov/sites/default/files/2026-04/DOE-HDBK-1018-93_VOL2.pdf), module ME-05 pages 31–32, Figure 15 | Vertical dished vessel, lower heater/surge path and upper spray connection. Heat, level and pressure are supplied illustrative indices; no real plant settings or thermal equations |

The relay's static `TRIP OUT` label names a function; its separate indicator shows
the supplied output state. Failure is not treated as proof of a successful trip.
Unavailable observed readings use a dash on the device, numeric gauge and
accessible description. Command values on other controllers keep their own meaning.
The pressurizer's heater-fault cue does not erase supplied retained heat.

## Controlled-environment agriculture

| Equipment | Reference inspected | Illustration boundary |
| --- | --- | --- |
| Nutrient-film channel | [Virginia Cooperative Extension SPES-463NP](https://www.pubs.ext.vt.edu/SPES/spes-463/spes-463.html), introduction, setup, supports, reservoir, irrigation input and channels | Continuous sloping cutaway, attached feed and gravity return, roots within the channel and supports on one baseline. No specified channel slope, nutrient recipe or hydraulic prediction |
| Greenhouse vent | [UMass Extension: Ventilation for Greenhouses](https://www.umass.edu/agriculture-food-environment/greenhouse-floriculture/fact-sheets/ventilation-for-greenhouses), natural ventilation, roof openings and maintenance | Glazed roof panel with a ridge hinge, attached telescopic actuator and air through the aperture. Geometry is illustrative, not a roof mechanism or structural design |

Closed vent geometry matches the roof opening. Its actuator endpoint follows the
panel throughout travel. Airflow is a curved visual path, distinct from metal
framing. The nutrient film, roots and return follow one channel coordinate system.
Closed, stopped and paused production cues remain still; reduced motion preserves
recognizable equipment and state without cycling effects.

## Crushing, screening and production machinery

| Equipment | Reference inspected | Illustration boundary |
| --- | --- | --- |
| Jaw crusher | [Metso Nordberg C Series](https://www.metso.com/portfolio/nordberg-c-series/), production/reduction and options sections | Tapered jaw chamber, distinct moving jaw, flywheel and connected drive. This explanatory cutaway is not a guard arrangement or assembly drawing |
| Vibrating screen | [Metso installation guide](https://www.metso.com/insights/blog/aggregates/tips-for-vibrating-equipment-installation/), feed and support sections | Moving decks above a stationary spring-supported base, separate coarse and fines outlets. No structural resonance or screening-efficiency model |
| Conveyor oven | [Metos CTX G26 manual](https://www.metos.com/pdf/prods/userguide/EN/4133322.pdf), PDF pages 9–11, and [Grieve electric belt oven](https://www.grievecorp.com/news/500f-electrically-heated-belt-conveyor-oven-from-grieve/) | Upper/lower radiant elements around a continuous metal belt. Coils are original generic geometry; dimensions, wattage and belt speed are not taken from these products |
| Rack / batch oven | [Grieve shelf ovens](https://www.grievecorp.com/product-category/shelf-loading-ovens/shelf-ovens/), front-loading shelf concept | Stationary trays, opening door and retained thermal glow. The example accepts explicit electrical input and cools a thermal store; its 0–100 heat index is not degrees Celsius |
| Tablet press | [Fette i Series](https://www.fette-compacting.com/en/production-solutions/tablet-presses/i-series), turret/compression description, and [US20190039270A1](https://patents.google.com/patent/US20190039270A1/en), rotor, punches, die, filling and ejection description | Generic transparent enclosure, rotating turret in its tilted plane, separate tooling and tablet chute. No formulation, process settings or production-rate prediction |

The existing `oven` identifier keeps its ports and v1 contract; its display name
is Conveyor oven. The new `rack-oven` is a separate v2 type. Its door command
changes presentation only: no door interlock, convection, recipe, product chemistry
or physical seal-loss equation is implemented. Element fault, overheating and
door-seal damage have distinct visual details and use the shared model's editable
health rules. Isolation stops energy input without instantly erasing stored heat.

## Verification and future additions

Focused UI tests protect meaningful geometry, phase labeling, reading validity and
state handling. Browser checks inspect real animation progress and fixed frames,
including reduced motion. The gallery exporter retains canonical SVG art and
uses an explicit CSS subset checked against the full stylesheet; it is not a
second drawing implementation.

Add primary sources and explain what was adopted, what was simplified and which
states were actually checked. Do not copy vendor artwork, invent a compliance
claim, or infer a complete simulation from animated pipes. Source and model
versions, browser evidence, package contents and live publication are separate
verification results.
