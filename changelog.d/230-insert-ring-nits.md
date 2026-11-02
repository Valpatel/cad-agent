**Fixed**
- `cadagent.mechanical.inserts.check_joint`, the `clamped on insert` row: the advice now names the washer that helps,
  a metal one between the printed part and the insert (not under the head), or a limiter. It also says that the
  whole clamp is taken on the insert's ring (the cautious bound), and that once the plastic yields the boss face
  takes some, which the check does not size. The page and the limits say the same (#230).
- `check_joint` with `installed_from="far side"`: `r["hole"]["overflow_mm3"]` is 0, since the hole is the insert's
  length; it used to report a joint-face blind hole's pocket (#230).
