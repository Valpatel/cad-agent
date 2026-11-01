**New**
- `cadagent.mechanical.inserts`: heat-set inserts and compression limiters in printed parts. `check_joint` checks a
  screw into an insert: the makers' hole (CAD allowance included) and boss, the melt's room, the screw's tip against
  the hole's floor, where the clamp goes (through the insert, a far-side shoulder, or jack-out when the insert is
  recessed or the clamped hole is as wide as it), pull-out, torque-out and push-out from a shear model calibrated to
  published tests (13 PLA results and three PETG, M3 and M6, SPIROL's read off its charts), the insert's own thread,
  the plastic under the head, a SPIROL limiter and the preload kept (the screw, limiter and plastic as springs). It
  returns pass, warn or fail per row and the most to tighten to, which passes every row the preload loads: the
  screw at 75 % of its proof load, the limiter's rating, the insert and the plastic. `check_clamp`
  does the same for printed plastic clamped by a screw into metal or a nut, with a catalogue limiter or your own
  sleeve or spacer. `hole_design`, `boss_design`, `capacity`, `calibration`, `install_notes` and `coupon_plan` give
  the parts on their own, and every number names its document (#230).
- `cad-agent inserts joints.yaml`: checks every joint in a YAML or JSON file; exits 1 on a fail, 2 on a bad file (#230).
- `cadagent.formulas`: fifteen formulas for inserts and limiters, each with its source and golden tests:
  `insert_displaced_volume`, `overflow_volume`, `insert_shear_force`, `insert_shear_torque`, `insert_clamp_path`,
  `insert_limited_torque`, `proof_load`, `annulus_stress`, `limiter_stack`, `limiter_plastic_load`,
  `frustum_stiffness` (Shigley's clamped-member cone), `press_fit_pressure`, `press_fit_force`, `preload_retained`
  and `preload_retained_limited` (#230).
- `docs/inserts.md` with five figures drawn from the module, and `tools/insert_coupons.py`, which writes the test
  coupons as STEP and STL in their print orientation (#230).

**Fixed**
- Kit `<cad-nav>`: on a wide screen, at the end of a long page, the sticky page tree no longer slides up under the header. It shrinks to the room its column leaves, so its filter stays in view and typing in it no longer scrolls the page. Adding a page to the site's tree had pushed it under (#230).

**Changed**
- `cadagent.formulas.nut_factor` refuses a flank angle outside 0 to π/2 radians. 60 passed as degrees used to give
  about three times the nut factor without complaint (#230).

**Projects must change**
- Pass `flank_angle` to `nut_factor` in radians (`math.radians(60.0)`, the default). A call that passed degrees now
  raises `ValueError` instead of returning a wrong number (#230).
