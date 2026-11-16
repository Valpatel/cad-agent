**Fixed**
- `<cad-model>`: Explode no longer throws `Invalid explode factor` when the browser's first animation frame is timestamped slightly before the click or Enter press; the tween clamps its progress at both ends (#680).
