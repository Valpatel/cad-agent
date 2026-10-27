# Align a PCB STEP with a proper rotation, never a reflection

2026-10-26: KiCad's native two-port STEP has board bounds X0…93, Y−65…0, Z0…1.51. The old enclosure import used `mirror('XZ')` to make Y positive. That reflection has determinant −1 and reverses handedness. A symmetric outline and collision check can pass while an asymmetric ribbon/header position belongs to a mirrored board.

Correction: rotate the original STEP 180 degrees around Z, then translate by `(board_width, 0, board_z)`. This is determinant +1 and maps native `(x,−y,z)` to housing `(width−x,y,z+board_z)`. Apply that same coordinate mapping to connector port centers, the ribbon clamp, header envelope and lid port names. Rebuild both variants, drawings and assembly checks. The clamp center consequently moves from `width/2−10` to `width/2+10` in housing coordinates.

Limits: a proper transform fixes handedness; it does not validate the manufacturer's generic 3D model, connector seating or hardware fit. Old A0 enclosure exports should be treated as superseded engineering artifacts, not print-ready mating proof.
