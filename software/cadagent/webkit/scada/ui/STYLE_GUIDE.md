# SCADA UI visual and behavior guide

Read [README.md](./README.md) for the API and component map, and [CONTRIBUTING.md](./CONTRIBUTING.md) for source ownership and checks. This guide describes the existing visual system; it does not define equipment physics or an operating standard.

## Design language

Use recognizable equipment silhouettes, restrained metallic depth and translucent teal surfaces. A pump should read as a pump before motion starts. A PLC rack, CPU, remote IO unit and HMI must remain distinguishable at card size and without color. Prefer original SVG geometry to a generic box decorated with a different label.

The hierarchy is equipment shape, current value/state, then context. Keep primary names and controls in HTML at readable sizes; tiny SVG labels are supplementary. Keep process maps compact and put detailed controls in the shared native dialog. A visual component has no private simulation, process timer or hardware connection.

## Palette and tokens

These values describe the current implementation. Reuse them for additions instead of introducing a separate theme per family.

| Role | Current colors / treatment |
| --- | --- |
| Deep surface | `#0b131e`, `#0e1421`, `#101722` |
| Raised controls | `#14202e`, `#172231` with visible `#3c5065` borders |
| Primary text | `#e8edf5`, `#d4e6f3`; supporting text `#a9bfd0` |
| Steel | Gradient through `#16374a`, `#659bae`, `#acd5de`, `#396a81`, `#122e42` |
| Glass | Low-opacity cyan highlights over dark blue, with visible outlines |
| Liquid / normal activity | `#57ffd0`, `#62ffbc`, `#68ffe1`, deep `#087a92` |
| Electrical / warm flow | `#ffd38a` |
| Focus / selection | Cyan `#00d7e4` or `#73eff6`, with an outline rather than color alone |
| Warning | Amber `#ffd38a` and a triangular exclamation symbol |
| Fault | Pink `#ff77ac` and an octagonal X symbol |
| Inactive / offline | Reduced saturation and opacity while retaining the equipment silhouette |

`scada-workspace.css` exposes `--scada-line`, `--scada-surface`, `--scada-raised`, `--scada-ink`, `--scada-muted` and `--scada-accent` on `.scada-workspace`. Its optional `--sim-*` fallbacks support the host app. The component stylesheet uses local variables such as `--scada-activity-duration`, `--scada-level` and `--scada-load`; render state is the public way to supply values. Do not make consumers set private transform/offset variables to achieve ordinary state changes.

Keep CSS within `.scada-component`, `.scada-workspace` or the viewer's own namespace. Do not add global `button`, `svg`, `input` or heading rules. Workspace styling works beneath a neutral `.scada-workspace` root; consumers do not need the reference app’s `#main` container.

## Geometry and sizing

- Custom equipment uses a `180 × 136` SVG viewBox. Keep the primary shape inside the viewBox and reserve space for connectors, indicators and ground shadow.
- Typical outlines are about 1–2 SVG units. Layered process pipes use a dark outer stroke, a lighter metal stroke and a separate animated flow stroke. Thin internal lines must not become the only identifying feature.
- Preserve aspect ratio. The standalone wrapper is `210` CSS pixels wide and reserves `136` pixels for artwork plus declared gauge rows; hosts may resize it. Shared twin artwork has its own established sizing and must be inspected when embedded in a new host.
- Level/load gauges occupy a separate lower row. Artwork must fit the remaining content height; never paint a gauge through liquid, a rotor or a label. Check small cards as well as the large preview.
- Use instance-prefixed SVG IDs for gradients, clips and filters. Do not place type-only IDs in a renderer that can appear more than once.
- Ports describe connection roles. Their metadata is not a declaration of screen coordinates or verified plant piping/wiring. Layout and route geometry belong to the system view.

Compare additions with the [thumbnail contact sheet](./img/thumbnails/contact-sheet.jpg) and inspect at least one small card, a large modal preview and the actual system view. A clean large screenshot does not prove the small version is legible.

## State is explicit

Use the [per-component coverage review](./docs/STATE_COVERAGE.md) as the current
baseline, including its known gaps. For additions, define relevant normal,
inactive, low/high, unavailable, damage and repair behavior before drawing effects.
Test declared damage alone and through the model adapter; do not rely on the host
also setting a generic fault flag. A settled switch need not animate, and a
retained-heat or leak effect need not stop with its motor. Record model limitations
and update the source-bound review after changing the covered behavior.

Declare all accepted visual fields in the component descriptor. Keep units, defaults, bounds and select options in that metadata so the catalog and documentation stay consistent. The normalizer rejects unsupported keys/types and non-finite values; finite numeric inputs are clamped to declared bounds. Do not silently interpret arbitrary source tags or configuration strings.

| State | Required visual behavior |
| --- | --- |
| Active / normal | Recognizable normal art; appropriate flow, rotor, scan or inventory activity when animation is enabled. |
| Inactive | Production stops; the equipment remains visible and named. Explicit coolant flow, retained heat and environmental motion can remain independently supplied. |
| `running: false` | Decoration freezes without altering the supplied reading or implying a physical model step. |
| Warning | Visible amber symbol plus accessible warning text, including equipment without an LED. |
| Fault | Visible fault symbol and text; activity responds to the supplied fault state. A renderer does not create or repair damage. |
| Offline | Inactive presentation and an accessible offline description. |
| Disconnected | PLC/network activity stops and the description remains truthful. A picture does not open a network connection. |
| Open / closed | A meaningful geometric distinction. An open valve permits its indicated path; an open breaker interrupts its electrical path. |
| Valve opening | Gate, control and butterfly valve position interpolates from 0–100%, with proportional flow highlighting. Closed overrides the supplied position; the old boolean-only open state remains fully open. |
| Numeric state | Visible level/load/readout where declared, with units or an explicit illustrative label. Bounds remain a UI contract, not equipment ratings. |
| Speed | Driven motion stops at zero and changes cadence across low, middle and high values. Status lights and monitoring displays are separate from production motion. |
| Damage | Type-specific physical detail: a leak, fracture, wear marks, blockage, heat plume, lost signal or failed device part. Keep generic fault symbols in addition to, not in place of, this detail. |

State combinations need deliberate precedence. A disconnected PLC must not be captioned “Active”; a fault should remain visible when motion is paused. Do not rely on a changed CSS variable alone if the device has no visible feature using it.

Use the `damage` options declared by the registry. A stopped drive may still have an animated spill or heat plume; gate production and incident motion separately. A jam, seized rotor or lost power must not keep its mechanism running. Wear, corrosion and fouling have persistent static marks, and every damage option remains distinguishable with reduced motion. Numeric temperature, speed, load and inventory values stay readable while those effects move. The separate headless model owns any trip, escalation or repair rule.

## Animation

Use CSS animation for decoration. Render functions create markup and never start intervals, request animation frames, audio, fetches or model sessions. The host model/adapter owns changing values and the clock. Multiple views of the same system must share that host state rather than replaying independent local simulations.

Reuse the established motion vocabulary: rotary movement for machinery, directional dashes for flow, gentle waves/bubbles for vessels, separate scan/link indicators for controls, and slow intensity changes for electrical or inventory activity. Different devices should not all blink the same way. Motion must reinforce state, not obscure values.

Honor `prefers-reduced-motion`, `.motion-paused` and the component's `running` state. Preserve visible warning/fault/readout information when motion is disabled. Avoid rapid flashes, page-wide shaking or continuous large-scale zoom. Test actual browser animation clocks; a class name or an `animation-name` declaration alone does not prove motion starts or stops correctly.

The existing twin's `hostState: true` mode deliberately defers to parent activity, buffer-fill and incident state. Do not add standalone defaults, gauges or style variables that override that parent. A renderer reused in the live app must not reset or replay a previous incident on navigation.

## Accessibility and interaction

Default equipment has one `role="img"` description containing its label and relevant state. Internal SVG content is hidden from duplicate announcements. Use `decorative: true` inside a native button/card that already names the equipment. Do not turn a decorative SVG group into an inaccessible click target.

Use native controls with at least 44 px targets, visible focus, associated labels and explicit units. Main dialog controls should use roughly 15–16 px text; supporting copy should remain readable at phone widths. Color alone is not a state description. Keyboard and reduced-motion users must be able to inspect the same information.

Dialogs use `ScadaWorkspace` for top-layer behavior, focus containment, Escape/backdrop dismissal and focus return. Keep controls mounted during live value updates; do not replace the whole modal on each tick. Destroy the view/dialog controller before removing its root, while preserving the externally owned system session.

Contained diagram viewers use a camera, not scrollbars, to navigate their 2D or
3D content. Size the viewport to the available host/window, keep **Zoom to fit**
visible outside the transformed scene, and support mouse/touch pan and zoom plus
keyboard equivalents. Fit is an overview, not a claim that every small label is
readable: provide readable zoom and equipment inspection. Preserve the camera
during model updates and keep focused equipment reachable. Normal top-level page
scrolling and long inspector forms may scroll; do not disable document scrolling
or merely hide bars on an oversized, unreachable canvas.

## Reuse boundaries

The component registry, workspace shell, viewer and versioned system definition form presentation infrastructure. Their model adapter supplies values, subscriptions and commands. Keep process equations, application authorization, PLC IO, historian access and session clocks outside the reusable package.

`modelSupport.kind: "shared-model"` means artwork is reused by the digester twin; it does not embed a model. Use the readable label **Twin artwork** and keep the full explanation available. New art defaults to `visual-only` unless its actual host integration justifies the descriptor. State/port metadata and screenshots are not engineering validation.

Record provenance for original geometry or any explicitly authorized external asset. Do not present generic PLC art as a verified vendor module or a site photograph. Keep generated thumbnails synchronized with canonical source and list the state used in their manifest.

## Power, nuclear and growing-system distinctions

Separate physical role, technology, industry, medium and variant metadata. A packaged genset, shaft-driven alternator, motor, converter, breaker, disconnector and earthing switch are distinct roles. Fuel, enclosure and capacity choices must not create dozens of duplicate physical type IDs. Use the catalog API and explicit variants; preserve default legacy art when no variant was supplied.

PWR, BWR, PHWR, gas-cooled, sodium-cooled and selected salt-cooled vessels have different structures. An SMR label describes selected technology plus modular arrangement, not a universal coolant or new physics class. Keep primary, secondary, moderator, intermediate and cooling circuits visibly separate. The selected salt drawing represents solid fuel and salt coolant; it does not claim to depict all liquid-fuel-salt designs. Nuclear `heat`, `pressure` and monitor readings are fictional indices. Residual thermal effects and supplied circulation do not disappear merely because production is disabled. Never turn a generic vessel rupture into a nuclear detonation.

A grow bed, fish tank, nutrient-film channel, deep-water raft, aeroponic chamber and climate device should remain identifiable without their labels. Irrigation phase, water inventory, aeration, moisture and light are separate supplied visual states. Sensor identities do not convert an illustrative index into real pH, EC, dissolved oxygen, humidity or PAR.

Give every declared field a visible effect or reading and every declared damage option anchored physical evidence. Readouts and generic gauges must agree about validity: unavailable instruments show a dash, while drift retains explicit warning context. Short gauge labels such as PRI/SEC/RODS prevent collisions; the accessible description and field editor retain the full name. Allow enough host height for all gauge rows instead of compressing a complex silhouette into a narrow strip.

Workspace styles use class-only scopes. Do not import host IDs into `:is()` selectors: their specificity would affect every standalone consumer. Keep any legacy application compatibility rule in that application. Verify a neutral host and an ordinary consumer class override in a real browser.

## Gallery ownership and portable image previews

Keep this library's gallery under `img/`: `symbols/<family>/` for animated default/variant previews, `states/` for selected state comparisons, and `thumbnails/` for static equipment and real workspace/viewer captures. Another library owns another `img/`; do not move reusable images into the host app or a repository-wide bucket.

Generate SVG previews through the canonical renderer. Preserve its geometry and instance IDs; adapt only the surrounding card and HTML readouts to native SVG. Keep titles, state text and gauge rows clear of artwork, with no external fonts, scripts, images or `foreignObject`. A preview must remain recognizable with animation disabled. Respect reduced motion inside the image itself, since a Markdown page cannot reach an SVG image's internal styles. Do not assume a platform's GIF pause control also pauses CSS inside SVG.

Category Markdown indexes use relative links and descriptive alt text, so the gallery transfers with the package. List the exact supplied illustrative state in `metadata/gallery.json`; a picture is not a second simulation or a new physical model. After changing art/state, regenerate both SVG previews and affected JPEG captures, run their freshness checks, and inspect the image in actual `<img>` mode. Direct SVG tabs, thumbnails and computed style declarations alone do not prove animation or interactive behavior.

## Visual review of physical connections

Every line needs a visible purpose. Connect it to a meaningful port, handle, cable, actuator or schematic boundary; remove unexplained floating strokes. Material paths use consistent, distinguishable colors and short labels or directional arrows when the path is otherwise ambiguous. Color complements geometry and labels rather than becoming the only explanation.

A silhouette must communicate function: a conveyor oven has a continuous product path, a rack/batch oven has a chamber and door, and a pump must remain distinct from a generator. Decorative movement follows supplied activity, position, speed and damage state. Keep those distinctions visible with reduced motion, including the evidence of a leak, blockage or failed part.

Inspect each revised element at card, inspector and diagram size separately. Follow the visible material or electrical path from inlet to outlet, check that controls and readouts do not collide, and inspect inactive, operating, warning and relevant damage states. A contact sheet is an index for review, not a substitute for examining an individual device.
