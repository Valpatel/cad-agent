# Recorded simulation tests

These checks distinguish recorded solver poses from interpolated presentation.

```mermaid
flowchart TD
  P[Known poses] --> T[Transform checks]
  R[Real recording] --> B[Browser controls]
  T --> C[Playback contract]
  B --> C
```

| File | Evidence |
| --- | --- |
| [replay.test.mjs](replay.test.mjs) | Invalid inputs, analytic rotations, time boundaries and clock disposal. |

[Webkit tests](../README.md)
